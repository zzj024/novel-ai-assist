"""三层查询引擎——自然语言 → 结构化查询 → 答案

流程：
  1. _split()      小模型拆句 + 实体提取 + 意图分类
  2. _route()      按意图路由到 SQL，未命中的走 DeepSeek
  3. _merge()      合并答案返回

省成本策略：
  - 拆句是最贵的，但只调一次小模型
  - 本地方向代词检测 + SQL 拦截大部分问题
  - DeepSeek 只处理 SQL 查不到的 + unresolved 的问题
  - 全 SQL 命中时不调 DeepSeek 合并
"""

import json
import re
from collections import deque
from dataclasses import dataclass, field

from openai import OpenAI

from core.knowledge import KnowledgeBase


# ── 拆句 Prompt ─────────────────────────────

SPLIT_PROMPT = """你是一个小说问题拆分助手。

你的任务只有两个：
1. 将用户问题拆成可以独立查询的子问题。
2. 仅在指代非常明确时，将"他/她/它/此人/对方"等代词替换为具体角色名。

不要做以下事情：
- 不要判断意图。
- 不要提取实体。
- 不要回答问题。
- 不要编造角色名。
- 指代不明确时，保留原文。

返回 JSON 数组，最多 5 项。
每项只包含 original 字段。

示例：
用户问题：林婉儿现在在哪里，她和萧炎是什么关系？
返回：
[
  {"original": "林婉儿现在在哪里"},
  {"original": "林婉儿和萧炎是什么关系"}
]"""


# ── 规则层常量 ───────────────────────────────

VALID_INTENTS: set[str] = {
    "character.status",
    "character.info",
    "relation.between",
    "relation.all",
    "chapter.summary",
    "chapter.list",
    "foreshadowing.list",
    "timeline.list",
}
UNKNOWN_INTENT = "unknown"
MAX_SUB_QUESTIONS = 5
MAX_UNKNOWN_RATIO = 0.34
MAX_ENTITIES_PER_ITEM = 4

# 中文人名姓氏
COMPOUND_SURNAMES = (
    "欧阳|司马|上官|诸葛|东方|独孤|南宫|慕容|司徒|皇甫|尉迟|公孙|"
    "轩辕|令狐|宇文|长孙|夏侯|端木|鲜于|闻人|呼延|百里|东郭"
)

SINGLE_SURNAMES = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华"
    "金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花"
    "方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于"
    "时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄"
    "米贝明臧计伏成戴谈宋庞熊纪舒屈项祝董梁杜阮蓝闵席季麻"
    "强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田胡凌霍虞万"
    "支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔"
    "吉龚程邢裴陆荣翁荀羊惠甄曲家封芮储靳汲邴糜松井段富巫"
    "乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭"
    "厉戎祖武符刘景詹束龙叶幸韶黎薄印宿白怀蒲从鄂索咸籍赖"
    "卓蔺屠蒙池乔阳胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦"
    "雍璩桑桂濮牛寿通边扈燕冀浦尚农温别庄晏柴瞿阎充慕连茹"
    "习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广"
    "禄阙东殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空"
    "曾毋沙乜养鞠须丰巢关蒯相查後荆红游竺权逯盖益桓公"
)

# 引号内实体
QUOTED_ENTITY_RE = re.compile(
    r"[「『\"'“]([^「」『』\"'“”，。！？；：、\s]{1,12})[」』\"'”]"
)

# 姓氏正则（复姓优先以避免拆分错误）
_NAME_RE_PATTERN = (
    rf"(?:{COMPOUND_SURNAMES})[一-鿿]{{1,2}}"
    rf"|[{SINGLE_SURNAMES}][一-鿿]{{1,2}}"
)
NAME_RE = re.compile(_NAME_RE_PATTERN)

# 上下文句式提取
ENTITY_CONTEXT_PATTERNS = [
    re.compile(
        r"(?P<name>[一-鿿]{2,4})(?:的)?"
        r"(?:修为|境界|实力|等级|状态|身体|情绪|心情|位置|在哪|去哪里|去向|下落)"
    ),
    re.compile(
        r"(?:介绍一下|介绍|说说|查一下)?(?P<name>[一-鿿]{2,4})"
        r"(?:是谁|什么身份|身份|背景|来历|资料|设定)"
    ),
    re.compile(
        r"(?P<a>[一-鿿]{2,4})(?:和|与|跟|同)"
        r"(?P<b>[一-鿿]{2,4})(?:的)?"
        r"(?:关系|什么关系|认识|敌友|师徒|父子|母子|父女|母女|"
        r"兄弟|姐妹|情侣|夫妻|仇人|同盟)"
    ),
]

# 停用词（不是角色名的高频词）
ENTITY_STOPWORDS: set[str] = {
    "什么", "关系", "修为", "状态", "位置", "章节", "伏笔", "时间",
    "时间线", "人物", "角色", "列表", "全部", "所有", "哪些",
    "现在", "目前", "最后", "最新", "总结", "摘要", "内容",
    "故事", "剧情", "背景", "身份", "信息", "介绍", "当前",
}

# 意图关键词映射
INTENT_KEYWORDS: dict[str, list[str]] = {
    "character.status": [
        "修为", "境界", "实力", "等级", "状态", "身体", "受伤",
        "情绪", "心情", "位置", "在哪", "在哪里", "去向", "下落",
    ],
    "character.info": [
        "是谁", "谁是", "介绍", "背景", "身份", "来历", "资料",
        "设定", "性格", "外貌", "年龄", "别名",
    ],
    "relation.between": [
        "什么关系", "关系如何", "认识", "敌友", "师徒",
        "父子", "母子", "父女", "母女", "兄弟", "姐妹", "情侣",
        "夫妻", "仇人", "同盟", "阵营", "恩怨",
    ],
    "relation.all": [
        "关系网", "人物关系", "所有关系", "全部关系", "关系列表",
        "有哪些关系", "列出关系", "的关系",
    ],
    "chapter.summary": [
        r"第[一二三四五六七八九十百千万零两\d]+章",
        r"章节.*(?:总结|摘要|概括|内容|剧情|发生了什么)",
        r"(?:总结|摘要|概括).*章节",
    ],
    "chapter.list": [
        "章节列表", "有哪些章节", "全部章节", "所有章节", "列出章节",
        "最近章节", "最新章节",
    ],
    "foreshadowing.list": [
        "伏笔", "铺垫", "暗线", "未回收", "已回收", "回收情况",
    ],
    "timeline.list": [
        "时间线", "大事记", "事件顺序", "发生顺序", "时间顺序",
        "剧情顺序", "经历了什么",
    ],
}

# 意图优先级（分数相同时按此顺序选择，越靠前优先级越高）
INTENT_PRIORITY: list[str] = [
    "relation.between",
    "character.status",
    "character.info",
    "relation.all",
    "chapter.summary",
    "foreshadowing.list",
    "timeline.list",
    "chapter.list",
]


# ── Focus 追踪 ──────────────────────────────

@dataclass
class FocusTracker:
    """记录当前对话焦点角色

    规则：
    - 本轮有实体 → focus 切换到最后一个实体
    - 本轮无实体 → empty_rounds +1，超过 5 轮清空
    """
    current: str | None = None
    empty_rounds: int = 0
    MAX_EMPTY_ROUNDS: int = 5

    def update(self, entities: list[str]) -> str | None:
        if entities:
            self.empty_rounds = 0
            self.current = entities[-1]
        else:
            self.empty_rounds += 1
            if self.empty_rounds >= self.MAX_EMPTY_ROUNDS:
                self.current = None
        return self.current


# ── 对话记忆 ──────────────────────────────

@dataclass
class ConversationHistory:
    """滑动窗口对话记忆，保留最近 max_rounds 轮"""
    max_rounds: int = 3
    history: deque = field(default_factory=lambda: deque(maxlen=3))

    def add(self, question: str, entities: list[str]):
        self.history.append({"question": question, "entities": entities})

    def format_for_prompt(self) -> str:
        if not self.history:
            return ""
        lines = [f"用户：{turn['question']}" for turn in self.history]
        return "\n".join(lines)


# ── 查询引擎 ──────────────────────────────

class QueryEngine:

    def __init__(
        self,
        kb: KnowledgeBase,
        cheap_client: OpenAI,
        expensive_client: OpenAI,
    ):
        self.kb = kb
        self.cheap = cheap_client          # qwen2.5:7b（拆句）
        self.expensive = expensive_client  # DeepSeek（兜底）
        self.focus = FocusTracker()
        self.conversation = ConversationHistory()
        self._debug_trace: list[dict] = []

    # ── 外部入口 ──────────────────────────────────

    def run(self, question: str, debug: bool = False) -> dict:
        """对外唯一入口

        参数：
            question: 用户问题
            debug: True 时在返回值中附加 debug_trace
        """
        self._debug_trace = [] if debug else None
        sub_questions = self._split_with_fallback(question)

        answers = self._route(sub_questions)
        result = self._merge(answers)

        # 更新上下文
        all_entities = list({
            e for sq in sub_questions if sq
            for e in sq.get("entities", [])
        })
        self.focus.update(all_entities)
        self.conversation.add(question, all_entities)

        if self._debug_trace is not None:
            result["debug_trace"] = self._debug_trace
        return result

    # ── 第一层：小模型拆句 ────────────────────────

    def _build_context(self, question: str) -> list[dict]:
        """构建给拆句模型的对话上下文"""
        messages = [{"role": "system", "content": SPLIT_PROMPT}]
        history = self.conversation.format_for_prompt()
        if history:
            messages.append({"role": "assistant", "content": history})
        if self.focus.current:
            messages.append({
                "role": "assistant",
                "content": f"当前讨论的主角：{self.focus.current}",
            })
        messages.append({"role": "user", "content": question})
        return messages

    def _split(self, question: str) -> list[dict]:
        """调轻量版小模型拆句（只拆句+指代消解），entities+intent 由规则补齐"""
        messages = self._build_context(question)
        response = self.cheap.chat.completions.create(
            model="qwen2.5:7b",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        if not raw:
            return self._enrich_split_items(
                [{"original": question}], question
            )
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                items = result
            elif isinstance(result, dict) and "questions" in result:
                items = result["questions"]
            else:
                items = [result]
            # 统一用规则补齐 entities + intent_hint
            return self._enrich_split_items(items, question)
        except (json.JSONDecodeError, TypeError):
            return self._enrich_split_items(
                [{"original": question}], question
            )

    # ── 质量检查 + 降级 ─────────────────────────

    def _split_with_fallback(self, question: str) -> list[dict]:
        """拆句入口：qwen → 规则 → DeepSeek 三级降级"""
        # Level 0：qwen2.5:7b 拆句
        try:
            result = self._split(question)
            result = self._accept_or_repair(result)
            if result is not None:
                return result
        except Exception:
            pass

        # Level 1：规则拆句
        try:
            result = self._rule_split(question)
            result = self._accept_or_repair(result)
            if result is not None:
                return result
        except Exception:
            pass

        # Level 2：DeepSeek 强制拆句
        return self._deepseek_split(question)

    def _accept_or_repair(self, result: list[dict]) -> list[dict] | None:
        """硬检查 + 软修复两阶段

        硬检查失败 → None（触发降级）
        软检查失败 → enrich 修复后返回
        全部通过 → 原样返回
        """
        if not self._split_hard_ok(result):
            return None
        if not self._split_soft_ok(result):
            return self._enrich_split_items(result, "")
        return result

    def _split_hard_ok(self, result: list[dict]) -> bool:
        """硬检查：结构性校验（失败=无法修复，走降级）

        检查：
        - 类型正确
        - 条目数合理
        - 每项有 original(str) / entities(list) / intent_hint(str)
        - entities 元素类型正确
        - intent_hint 属于合法值
        """
        if not isinstance(result, list):
            return False
        if not (1 <= len(result) <= MAX_SUB_QUESTIONS):
            return False

        for item in result:
            if not isinstance(item, dict):
                return False

            original = item.get("original")
            entities = item.get("entities")
            intent_hint = item.get("intent_hint")

            # original 必须是非空字符串
            if not isinstance(original, str) or not original.strip():
                return False

            # entities 必须是字符串列表
            if not isinstance(entities, list):
                return False
            if any(not isinstance(e, str) for e in entities):
                return False
            if len(entities) > MAX_ENTITIES_PER_ITEM:
                return False

            # intent_hint 必须是合法值
            if not isinstance(intent_hint, str):
                return False
            if intent_hint != UNKNOWN_INTENT and intent_hint not in VALID_INTENTS:
                return False

        return True

    def _split_soft_ok(self, result: list[dict]) -> bool:
        """软检查：内容质量校验（失败=enrich 可修复）

        检查：
        - unknown 比例 ≤ MAX_UNKNOWN_RATIO
        - relation.between 必须有 ≥2 个实体
        - char.status/char.info 在有明确实体线索时 entities 不能为空
        - 无重复 original
        """
        unknown_count = 0
        originals: list[str] = []

        for item in result:
            original = item.get("original", "").strip()
            entities = item.get("entities", [])
            intent_hint = item.get("intent_hint", "")

            originals.append(original)

            if intent_hint == UNKNOWN_INTENT:
                unknown_count += 1

            # relation.between 必须有 ≥2 个实体
            if intent_hint == "relation.between" and len(entities) < 2:
                return False

            # char.status/char.info 在有实体线索时 entities 不能为空
            if intent_hint in {"character.status", "character.info"}:
                rule_entities = self._extract_entities(original)
                if rule_entities and not entities:
                    return False

        # unknown 比例过高
        if unknown_count / len(result) > MAX_UNKNOWN_RATIO:
            return False

        # 重复 original
        if len(set(originals)) != len(originals):
            return False

        return True

    def _rule_split(self, question: str) -> list[dict]:
        """规则拆句 + 实体 + 意图（不调任何模型）"""
        text = question.strip()
        if not text:
            return []

        # 按标点拆句（逗号+过渡词拆句风险高，暂时只按句号/问号/分号拆）
        parts = re.split(r'[？?！!。；;\n]+', text)
        parts = [p.strip() for p in parts if p.strip()]

        # 如果没有拆开，保留原问题
        if not parts:
            parts = [text]

        items: list[dict] = []
        for part in parts[:MAX_SUB_QUESTIONS]:
            items.append({
                "original": part,
                "entities": [],
                "intent_hint": UNKNOWN_INTENT,
            })

        # 用 _enrich_split_items 统一补齐 entities + intent_hint
        return self._enrich_split_items(items, question)

    def _deepseek_split(self, question: str) -> list[dict]:
        """DeepSeek 强制拆句——最后兜底，返回固定格式"""
        try:
            response = self.expensive.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": SPLIT_PROMPT},
                    {"role": "user", "content": question},
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=15,
            )
            raw = response.choices[0].message.content
            if raw:
                result = json.loads(raw)
                if isinstance(result, list):
                    return result
                if isinstance(result, dict) and "questions" in result:
                    return result["questions"]
        except Exception:
            pass
        # DeepSeek 也失败的话，最后保底
        return [{"original": question, "entities": [], "intent_hint": "unknown"}]

    # ── 规则层：实体提取 ──────────────────────────

    def _known_character_names(self) -> list[str]:
        """返回已入库角色名和别名，长名优先（用于实体提取）"""
        try:
            rows = self.kb.get_all_character_names()
        except Exception:
            return []

        names: set[str] = set()
        for row in rows:
            name = row.get("name")
            if name:
                names.add(str(name).strip())
            aliases = row.get("aliases") or "[]"
            if isinstance(aliases, str):
                try:
                    for alias in json.loads(aliases):
                        if alias:
                            names.add(str(alias).strip())
                except (json.JSONDecodeError, TypeError):
                    pass
        return sorted(names, key=len, reverse=True)

    def _known_episodic_descriptors(self) -> list[str]:
        """返回已入库描述性实体的描述符列表（长名优先）"""
        try:
            return self.kb.get_all_episodic_descriptors()
        except Exception:
            return []

    def _extract_entities(self, text: str) -> list[str]:
        """多层实体提取：已知角色 → 描述性实体 → 引号 → 姓氏正则"""
        found: list[str] = []

        # 1. 已入库角色名/别名优先，最长优先匹配
        for name in self._known_character_names():
            if name and name in text:
                found.append(name)

        # 2. 已入库描述性实体（如"黑衣人""白衣女子"）
        for desc in self._known_episodic_descriptors():
            if desc and desc in text:
                found.append(desc)

        # 3. 引号实体
        for match in QUOTED_ENTITY_RE.finditer(text):
            found.append(match.group(1).strip())

        # 去重 + 子串过滤："婉儿"是"林婉儿"的子串，不重复提取
        result = self._dedupe_entities(found)
        return self._filter_substrings(result)

    def _filter_substrings(self, entities: list[str]) -> list[str]:
        """过滤掉是其他实体子串的项（长名优先保留）"""
        # 已按长名优先排序（_known_character_names 保证）
        kept: list[str] = []
        for entity in entities:
            # 如果 entity 是已保留的某个实体的子串，跳过
            if any(entity in k for k in kept if len(k) > len(entity)):
                continue
            kept.append(entity)
        return kept

    def _dedupe_entities(self, entities: list[str]) -> list[str]:
        """去重 + 停用词过滤 + 长度约束"""
        result: list[str] = []
        seen: set[str] = set()

        for entity in entities or []:
            if not isinstance(entity, str):
                continue
            name = entity.strip()
            if not name:
                continue
            if name in ENTITY_STOPWORDS:
                continue
            if len(name) < 2 or len(name) > 12:
                continue
            if name not in seen:
                seen.add(name)
                result.append(name)

        return result[:MAX_ENTITIES_PER_ITEM]

    # ── 规则层：意图分类 ──────────────────────────

    def _score_intent(self, text: str, entities: list[str] | None = None) -> dict[str, int]:
        """计算所有意图的得分，返回得分字典（供 explain 和 classify 共用）"""
        if entities is None:
            entities = []
        scores: dict[str, int] = {}

        for intent, patterns in INTENT_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    scores[intent] = scores.get(intent, 0) + 2

        # 关系类特判：两个实体 + 关系词 → relation.between
        if len(entities) >= 2 and re.search(
            r"关系|认识|敌友|师徒|父子|母子|情侣|仇人|同盟|恩怨", text
        ):
            scores["relation.between"] = scores.get("relation.between", 0) + 8

        # 全量关系：出现"全部/所有/列出" + "关系" → relation.all
        if re.search(r"全部|所有|有哪些|列出|关系网", text) and re.search(r"关系|人物关系", text):
            scores["relation.all"] = scores.get("relation.all", 0) + 5

        # 章节列表优先于章节摘要
        if re.search(r"章节列表|全部章节|所有章节|有哪些章节|列出章节", text):
            scores["chapter.list"] = scores.get("chapter.list", 0) + 6

        # 第 N 章 → 倾斜 chapter.summary
        if re.search(r"第[一二三四五六七八九十百千万零两\d]+章", text):
            scores["chapter.summary"] = scores.get("chapter.summary", 0) + 4

        return scores

    def _classify_intent(self, text: str, entities: list[str] | None = None) -> str:
        """加权打分判断意图（返回最高分意图）"""
        scores = self._score_intent(text, entities)
        if not scores:
            return UNKNOWN_INTENT
        # 分数相同时按 INTENT_PRIORITY 选择
        priority_map = {name: i for i, name in enumerate(INTENT_PRIORITY)}
        return max(scores.items(), key=lambda kv: (kv[1], -priority_map.get(kv[0], 999)))[0]

    # ── 规则层：补齐 LLM 输出 ─────────────────────

    def _enrich_split_items(self, items: list[dict], question: str) -> list[dict]:
        """补齐 entities + intent_hint（供所有降级层使用）"""
        enriched: list[dict] = []

        for item in items:
            original = item.get("original")
            if not isinstance(original, str) or not original.strip():
                continue
            original = original.strip()

            # 准备 trace（debug 模式）
            trace_entry = None
            if self._debug_trace is not None:
                trace_entry = {
                    "original": original,
                    "entities_before": list(item.get("entities", [])),
                    "intent_before": item.get("intent_hint", ""),
                }

            # 用规则提取 entities，合并已有的
            rule_entities = self._extract_entities(original)
            existing = item.get("entities")
            if isinstance(existing, list):
                merged = list(dict.fromkeys(list(existing) + rule_entities))
            else:
                merged = rule_entities

            # 用规则分类 intent
            intent_hint = item.get("intent_hint")
            if intent_hint not in VALID_INTENTS:
                intent_hint = self._classify_intent(original, merged)

            # 完成 trace
            if trace_entry is not None:
                trace_entry["entities_after"] = list(self._dedupe_entities(merged))
                trace_entry["intent_after"] = intent_hint
                trace_entry["intent_scores"] = self._score_intent(original, merged)
                self._debug_trace.append(trace_entry)

            enriched.append({
                "original": original,
                "entities": self._dedupe_entities(merged),
                "intent_hint": intent_hint,
            })

        return enriched[:MAX_SUB_QUESTIONS]

    def _has_unresolved_pronoun(self, sq: dict) -> bool:
        """检查子问题是否有未解析的代词（她/他/它）"""
        original = sq.get("original", "")
        entities = sq.get("entities", [])
        return bool(not entities and re.search(r'[她他它]', original))

    def _route(self, sub_questions: list[dict]) -> list[dict]:
        """逐条路由：SQL → 未命中 → DeepSeek 兜底"""
        answers = []
        for sq in sub_questions:
            if not isinstance(sq, dict):
                continue
            try:
                # 代词未解析 → 直接兜底
                if self._has_unresolved_pronoun(sq):
                    answers.append(self._fallback_llm(sq))
                    continue

                # 路由到对应的 SQL 函数
                intent = sq.get("intent_hint", "unknown")
                handler = INTENT_ROUTER.get(intent)
                if handler:
                    result = handler(self.kb, sq)
                    if result["found"]:
                        answers.append(result)
                        continue

                # SQL 没命中 → DeepSeek 兜底
                answers.append(self._fallback_llm(sq))
            except Exception as e:
                answers.append({
                    "found": True,
                    "source": "error",
                    "answer": f"处理问题时出错：{e}",
                })
        return answers

    # ── 第三层：DeepSeek 兜底 ────────────────────

    def _fallback_llm(self, sq: dict) -> dict:
        """SQL 查不到或代词未解析时，调 DeepSeek 带上下文回答"""
        try:
            context = self._build_fallback_context(sq)
            response = self.expensive.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": FALLBACK_PROMPT},
                    {"role": "user", "content": context},
                ],
                temperature=0.3,
                timeout=30,
            )
            answer = response.choices[0].message.content or "无法获取答案"
            return {
                "found": True,
                "source": "llm",
                "answer": answer,
                "evidence": "DeepSeek 推理",
            }
        except Exception as e:
            return {
                "found": True,
                "source": "error",
                "answer": f"抱歉，查询时出错：{e}",
            }

    def _build_fallback_context(self, sq: dict) -> str:
        """为兜底模型构建精简上下文"""
        original = sq.get("original", "")
        entities = sq.get("entities", [])
        parts = [f"问题：{original}"]

        if entities:
            for name in entities[:3]:
                char = self.kb.get_character(name)
                if char:
                    parts.append(
                        f"角色 {name}：{char.get('description', '')} "
                        f"（最后出场第{char['last_seen']}章）"
                    )
                    relations = self.kb.list_relations(char_a=name)[0]
                    relations.extend(self.kb.list_relations(char_b=name)[0])
                    if relations:
                        rel_str = "；".join(
                            f"{r['char_a']}和{r['char_b']}是{r['relation']}"
                            for r in relations[:3]
                        )
                        parts.append(f"关系：{rel_str}")

        # 最近的章节摘要
        chapters = self.kb.list_chapters(page=1, page_size=5)
        if chapters:
            summaries = []
            for c in reversed(chapters[-3:]):
                s = c.get("summary") or "（暂无摘要）"
                summaries.append(f"第{c['num']}章：{s[:100]}")
            parts.append("最近章节：\n" + "\n".join(summaries))

        parts.append("注意：只能基于上述资料回答，资料不足说'当前资料无法确定'。")
        return "\n\n".join(parts)

    # ── 合并答案 ──────────────────────────────

    def _merge(self, answers: list[dict]) -> dict:
        """合并所有子问题的答案

        规则：
        - 全部 SQL 命中 → 代码模板合并
        - 混了 LLM 答案 → 再加一次 DeepSeek 润色（可选）
        """
        if not answers:
            return {"answer": "没有找到相关信息", "source": "empty"}

        # 检查是否有 LLM 来源的答案
        has_llm = any(a.get("source") == "llm" for a in answers)
        has_error = any(a.get("source") == "error" for a in answers)

        if has_llm or has_error:
            # 混了 LLM 或错误 → 按原始内容拼接
            return self._merge_with_llm(answers)
        else:
            # 全 SQL → 代码模板合并
            return self._merge_template(answers)

    def _merge_template(self, answers: list[dict]) -> dict:
        """纯代码模板合并"""
        lines = []
        for i, a in enumerate(answers, 1):
            lines.append(f"{i}. {a['answer']}")
            if a.get("evidence"):
                lines.append(f"   来源：{a['evidence']}")
        return {
            "answer": "\n".join(lines),
            "source": "sql",
        }

    def _merge_with_llm(self, answers: list[dict]) -> dict:
        """混了 LLM 答案时的合并"""
        lines = []
        has_sql = False
        for i, a in enumerate(answers, 1):
            source_tag = "[数据库]" if a.get("source") == "sql" else "[推理]"
            lines.append(f"{source_tag} {i}. {a['answer']}")
            if a.get("source") == "sql":
                has_sql = True

        # 尝试调 DeepSeek 润色（不强制，失败就用原始拼接）
        if has_sql and len(answers) > 1:
            try:
                return self._polish_with_llm(lines)
            except Exception:
                pass

        return {
            "answer": "\n".join(lines),
            "source": "mixed",
        }

    def _polish_with_llm(self, lines: list[str]) -> dict:
        """将多条答案润色为自然语言"""
        prompt = (
            "将以下多条查询结果整合为一段自然语言回复。\n"
            "要求：简洁、准确、不编造。\n\n"
            + "\n".join(lines)
        )
        response = self.expensive.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            timeout=15,
        )
        return {
            "answer": response.choices[0].message.content or "整合失败",
            "source": "polished",
        }


# ── DeepSeek 兜底 Prompt ─────────────────────

FALLBACK_PROMPT = """你是一个小说知识问答助手。根据给定资料回答问题。

规则：
1. 只能基于给定资料回答
2. 资料不足时说"当前资料无法确定"
3. 不要续写剧情，不要补设定
4. 回答时列出依据（引用章节号/角色名）"""


# ── SQL 路由表 ──────────────────────────────

def _query_status(kb: KnowledgeBase, sq: dict) -> dict:
    """查角色状态"""
    entities = sq.get("entities", [])
    if not entities:
        return {"found": False}
    name = entities[0]
    char = kb.get_character(name)
    if not char:
        return {"found": False}
    status = char.get("current_status", {})
    if isinstance(status, str):
        status = json.loads(status) if status else {}
    parts = [f"{k}：{v}" for k, v in status.items()]
    return {
        "found": True,
        "source": "sql",
        "answer": f"{name}当前状态：{'；'.join(parts)}",
        "evidence": f"角色库（最后出场第{char['last_seen']}章）",
    }


def _query_character(kb: KnowledgeBase, sq: dict) -> dict:
    """查角色背景"""
    entities = sq.get("entities", [])
    if not entities:
        return {"found": False}
    name = entities[0]
    char = kb.get_character(name)
    if not char:
        return {"found": False}
    return {
        "found": True,
        "source": "sql",
        "answer": char.get("description", "暂无描述"),
        "evidence": f"角色库（首次出场第{char['first_appeared']}章）",
    }


def _query_relation_between(kb: KnowledgeBase, sq: dict) -> dict:
    """查两个角色的关系"""
    entities = sq.get("entities", [])
    if len(entities) < 2:
        return {"found": False}
    a, b = entities[0], entities[1]
    relations, _ = kb.list_relations(char_a=a, char_b=b)
    if not relations:
        relations, _ = kb.list_relations(char_a=b, char_b=a)
    if not relations:
        return {"found": False}
    lines = [f"{r['char_a']} 和 {r['char_b']} 是{r['relation']}关系"
             for r in relations]
    return {
        "found": True,
        "source": "sql",
        "answer": "；".join(lines),
    }


def _query_relation_all(kb: KnowledgeBase, sq: dict) -> dict:
    """查某个角色的所有关系"""
    entities = sq.get("entities", [])
    if not entities:
        return {"found": False}
    name = entities[0]
    relations_a, _ = kb.list_relations(char_a=name)
    relations_b, _ = kb.list_relations(char_b=name)
    relations = relations_a + relations_b
    if not relations:
        return {"found": False}
    lines = [f"{r['char_a']} 和 {r['char_b']} 是{r['relation']}关系"
             for r in relations]
    return {
        "found": True,
        "source": "sql",
        "answer": f"{name}的关系：{'；'.join(lines)}",
    }



def _query_chapter_summary(kb: KnowledgeBase, sq: dict) -> dict:
    """查章节摘要"""
    m = re.search(r'(\d+)', sq.get("original", ""))
    if not m:
        return {"found": False}
    chapter = kb.get_chapter(int(m.group(1)))
    if not chapter:
        return {"found": False}
    summary = chapter.get("summary") or "暂无摘要"
    return {
        "found": True,
        "source": "sql",
        "answer": f"第{chapter['num']}章摘要：{summary}",
    }


def _query_chapter_list(kb: KnowledgeBase, sq: dict) -> dict:
    """查章节列表"""
    chapters = kb.list_chapters(page=1, page_size=100)
    if not chapters:
        return {"found": False}
    lines = [f"第{c['num']}章 {c.get('title', '')}" for c in chapters]
    return {
        "found": True,
        "source": "sql",
        "answer": "、".join(lines),
    }


def _query_foreshadowing(kb: KnowledgeBase, sq: dict) -> dict:
    """查伏笔"""
    items, _ = kb.list_foreshadowings()
    if not items:
        return {"found": False}
    unrecovered = [f for f in items if f.get("status") == "unrecovered"]
    target = unrecovered if unrecovered else items
    lines = [f"『{f['description']}』（第{f['laid_chapter']}章）"
             for f in target[:5]]
    return {
        "found": True,
        "source": "sql",
        "answer": "；".join(lines) if lines else "暂无伏笔",
    }


def _query_timeline(kb: KnowledgeBase, sq: dict) -> dict:
    """查时间线"""
    m = re.search(r'(\d+)', sq.get("original", ""))
    events, _ = kb.list_timeline(chapter=int(m.group(1)) if m else None)
    if not events:
        return {"found": False}
    lines = [f"{e.get('story_time', '')} {e['event']}" for e in events[:8]]
    return {
        "found": True,
        "source": "sql",
        "answer": "；".join(lines),
    }


INTENT_ROUTER = {
    "character.status":   _query_status,
    "character.info":     _query_character,
    "relation.between":   _query_relation_between,
    "relation.all":       _query_relation_all,
    "chapter.summary":    _query_chapter_summary,
    "chapter.list":       _query_chapter_list,
    "foreshadowing.list": _query_foreshadowing,
    "timeline.list":      _query_timeline,
}
