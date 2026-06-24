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

SPLIT_PROMPT = """你是一个问题拆分助手。将用户的问题拆成单个子问题。

规则：
1. 每个子问题必须保留 original 原文
2. 如果原文有"他/她/它"等代词，根据对话历史替换为具体角色名
3. entities 列出所有提及的角色名
4. intent_hint 从下方列表中选择

intent_hint 可选值：
  character.status    — 角色修为/状态/位置
  character.info      — 角色是谁/背景描述
  relation.between    — 两个角色的关系
  relation.all        — 某个角色的所有关系
  chapter.summary     — 章节内容摘要
  chapter.list        — 章节列表
  foreshadowing.list  — 伏笔/悬念
  timeline.list       — 时间线事件
  unknown             — 以上都不匹配

返回格式（JSON 数组）：
[
  {"original": "林婉儿什么修为", "entities": ["林婉儿"], "intent_hint": "character.status"}
]"""


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

    # ── 外部入口 ──────────────────────────────────

    def run(self, question: str) -> dict:
        """对外唯一入口"""
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
        """调小模型拆句，返回子问题列表"""
        messages = self._build_context(question)
        response = self.cheap.chat.completions.create(
            model="qwen2.5:7b",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        if not raw:
            return [{"original": question, "entities": [], "intent_hint": "unknown"}]
        try:
            result = json.loads(raw)
            # 确保返回的是列表
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "questions" in result:
                return result["questions"]
            return [result]
        except (json.JSONDecodeError, TypeError):
            return [{"original": question, "entities": [], "intent_hint": "unknown"}]

    # ── 质量检查 + 降级 ─────────────────────────

    def _split_with_fallback(self, question: str) -> list[dict]:
        """拆句入口：qwen → 规则 → DeepSeek 三级降级"""
        # Level 0：qwen2.5:7b 拆句
        try:
            result = self._split(question)
            if self._split_quality_ok(result):
                return result
        except Exception:
            pass

        # Level 1：规则拆句
        try:
            result = self._rule_split(question)
            if self._split_quality_ok(result):
                return result
        except Exception:
            pass

        # Level 2：DeepSeek 强制拆句
        return self._deepseek_split(question)

    def _split_quality_ok(self, result: list[dict]) -> bool:
        """检查小模型拆句结果质量是否可接受"""
        if not isinstance(result, list) or not result:
            return False

        # 统计有效子问题数
        valid = 0
        for item in result:
            if not isinstance(item, dict):
                return False
            if not item.get("original"):
                return False
            if item.get("intent_hint") == "unknown":
                continue  # unknown 不计入有效，但不直接判失败
            valid += 1

        # 没有一条有效 → 拒绝
        if valid == 0:
            return False

        # 超过 5 条 → 大概率抽风
        if len(result) > 5:
            return False

        return True

    def _rule_split(self, question: str) -> list[dict]:
        """规则拆句：heuristic 兜底，不调任何模型"""
        result = []

        # 按标点拆句
        parts = re.split(r'[？?！!。；;]', question)
        parts = [p.strip() for p in parts if p.strip()]

        for part in parts:
            entities = []
            # 用正则找引号/书名号内的实体名（简单启发式）
            names = re.findall(r'[「」""『』《》](.+?)[「」""『』《》]', part)
            names = [n for n in names if len(n) <= 10]
            entities.extend(names)

            # 意图判断
            intent = self._heuristic_intent(part)
            result.append({
                "original": part,
                "entities": entities,
                "intent_hint": intent,
            })

        return result if result else [{
            "original": question,
            "entities": [],
            "intent_hint": "unknown",
        }]

    def _heuristic_intent(self, text: str) -> str:
        """关键词规则判断意图"""
        if re.search(r'修为|境界|伤势|状态|位置|在哪', text):
            return "character.status"
        if re.search(r'是谁|是.*什么人|背景|介绍', text):
            return "character.info"
        if re.search(r'关系|和谁|与谁|什么关系|敌对|师徒|盟友', text):
            return "relation.between"
        if re.search(r'(\d+)\s*章.*(讲|内容|摘要|发生)', text):
            return "chapter.summary"
        if re.search(r'有哪些章节|目录|清单', text):
            return "chapter.list"
        if re.search(r'伏笔|悬念|未回收|坑', text):
            return "foreshadowing.list"
        if re.search(r'时间线|事件|什么时候|那天|那天', text):
            return "timeline.list"
        return "unknown"

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
                    relations = self.kb.list_relations(char_a=name)
                    relations += self.kb.list_relations(char_b=name)
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
    relations = kb.list_relations(char_a=a, char_b=b)
    if not relations:
        relations = kb.list_relations(char_a=b, char_b=a)
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
    relations = kb.list_relations(char_a=name)
    relations += kb.list_relations(char_b=name)
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
    items = kb.list_foreshadowings()
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
    events = kb.list_timeline(chapter=int(m.group(1)) if m else None)
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
