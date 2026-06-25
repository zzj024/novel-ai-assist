"""LLM 章节解析调度器 —— 调用 LLM → 校验 JSON → 事务写入

职责：
1. 接收章节正文，调用 LLM 提取结构化数据
2. 解析 LLM 返回的 JSON，通过 Pydantic 校验
3. 校验通过 → 事务性写入 SQLite
4. 校验失败 → 自动重试 1 次

企业级原则覆盖：
- 技能管理 → 四层兜底（JSON 提取 → Pydantic 校验 → 重试）
- 精打细算 → 低 temperature 稳定输出，减少无谓重试
- 安全合规 → LLM 超时 120s + 重试 1 次，失败不崩溃
- 知识积累 → 校验通过才写入，脏数据不落地
"""

import json
import logging
from typing import Optional

from openai import OpenAI
from core.models import ChapterExtract
from core.extract_prompt import build_extract_messages, PROMPT_VERSION

logger = logging.getLogger(__name__)


class ChapterParser:
    """章节解析调度器

    用法：
        parser = ChapterParser(settings, knowledge_base)
        result = parser.parse_and_store("正文内容...", 3, "第3章.md")
    """

    def __init__(self, config, knowledge_base) -> None:
        self.config = config
        self.kb = knowledge_base
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.api_base,
        )
        self.broadcaster = None

    # ── LLM 调用 ──────────────────────────────────────

    def _call_llm(self, messages: list[dict]) -> Optional[str]:
        """调用 LLM 并返回原始 JSON 字符串

        参数：
            messages: build_extract_messages() 生成的 message 列表

        返回：
            str: LLM 返回的原始内容
            None: 调用失败（超时/网络错误等）
        """
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=0.1,   # 低温度，让输出更稳定
                timeout=300,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            return None

    # ── JSON 解析 + Pydantic 校验 ─────────────────────

    def _parse_response(self, raw: str) -> Optional[ChapterExtract]:
        """解析 LLM 原始返回 → Pydantic 校验

        四层兜底：
        1. 尝试直接 json.loads
        2. 尝试提取代码块中的 JSON（LLM 偶尔会包在 ```json 里）
        3. Pydantic model_validate 校验
        4. 以上都失败 → 返回 None，触发重试

        参数：
            raw: LLM 返回的原始字符串

        返回：
            ChapterExtract: 校验通过的解析结果
            None: 解析失败
        """
        # 第一层：直接解析 JSON
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # 第二层：尝试从 ```json 代码块中提取
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    logger.warning("代码块中的 JSON 也无法解析")
                    return None
            else:
                logger.warning("LLM 返回的不是合法 JSON")
                return None

        # 第三层：Pydantic 校验
        try:
            return ChapterExtract.model_validate(data)
        except Exception as e:
            logger.warning("Pydantic 校验失败: %s", e)
            return None

    # ── 主入口 ────────────────────────────────────────

    def parse_and_store(
        self, chapter_text: str, chapter_num: int, filename: str
    ) -> dict:
        """解析章节并写入数据库（对外唯一入口）

        流程：
        1. 组装 prompt → 调用 LLM（最多重试 1 次）
        2. 解析 JSON → Pydantic 校验
        3. 校验通过 → knowledge.py 事务写入
        4. 记录解析日志到 llm_parse_logs
        5. 更新 chapters 表状态

        参数：
            chapter_text: 章节正文
            chapter_num:  章序号
            filename:     文件名

        返回：
            dict: {"ok": bool, "chapter_num": int, "error": str or None}
        """
        messages = build_extract_messages(chapter_text)
        raw_response: Optional[str] = None
        parsed: Optional[ChapterExtract] = None

        # ── 最多重试 1 次（共 2 次尝试） ──────────────
        for attempt in range(2):
            raw = self._call_llm(messages)
            if raw is None:
                continue  # 网络错误，直接重试

            raw_response = raw
            parsed = self._parse_response(raw)
            if parsed is not None:
                break  # 校验通过，跳出重试循环
            logger.warning("第 %s 章解析失败，重试中...", chapter_num)

        # ── 最终结果处理 ──────────────────────────────
        conn = self.kb.get_conn()

        if parsed is None:
            # 两次都失败 → 标记 error
            conn.execute(
                "UPDATE chapters SET status='error', error_msg=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE num=?",
                ("LLM 解析失败（重试后仍失败）", chapter_num),
            )
            conn.commit()

            # 记录失败日志（如果有原始响应）
            if raw_response:
                chapter_row = conn.execute(
                    "SELECT id FROM chapters WHERE num = ?", (chapter_num,)
                ).fetchone()
                if chapter_row:
                    self.kb.save_parse_log(
                        chapter_id=chapter_row["id"],
                        model=self.config.model,
                        prompt_version=PROMPT_VERSION,
                        raw_response=raw_response,
                        parse_status="failed",
                        error_message="重试后仍失败",
                    )

            logger.error("第 %s 章解析失败，已标记 error", chapter_num)
            return {"ok": False, "chapter_num": chapter_num, "error": "LLM 解析失败"}

        # ── 校验通过 → 事务写入 ───────────────────────
        try:
            chapter_id = self.kb.write_chapter_extract(
                chapter_num=chapter_num,
                result=parsed,
                raw_text=chapter_text,
            )

            # 记录成功日志
            self.kb.save_parse_log(
                chapter_id=chapter_id,
                model=self.config.model,
                prompt_version=PROMPT_VERSION,
                raw_response=raw_response,
                parse_status="success",
            )

            logger.info("第 %s 章解析成功", chapter_num)

            # WebSocket 广播
            if self.broadcaster:
                self.broadcaster({"ok": True, "chapter_num": chapter_num, "error": None})

            return {"ok": True, "chapter_num": chapter_num, "error": None}

        except Exception as e:
            logger.error("第 %s 章事务写入异常: %s", chapter_num, e)
            return {"ok": False, "chapter_num": chapter_num, "error": str(e)}
