"""DataLoader —— 从 KnowledgeBase 一次性加载全量数据到 RuleContext

所有规则共享此数据，避免各自查库。
"""

import json
import logging

from core.knowledge import KnowledgeBase
from core.contradiction.models import RuleContext

logger = logging.getLogger(__name__)


class DataLoader:
    """数据加载器

    用法：
        loader = DataLoader(kb, config={...})
        ctx = loader.load()
    """

    # 全量查询时的 page_size（足够大以覆盖所有数据）
    BULK_PAGE_SIZE = 9999

    def __init__(self, kb: KnowledgeBase, config: dict | None = None) -> None:
        self.kb = kb
        self.config = config or {}

    def load(self) -> RuleContext:
        """从 KnowledgeBase 加载所有数据，构建 RuleContext"""
        # 1. 角色
        characters, _ = self.kb.list_characters(page=1, page_size=self.BULK_PAGE_SIZE)
        status_by_char = self._build_status_by_char(characters)

        # 2. 时间线事件
        events, _ = self.kb.list_timeline(page=1, page_size=self.BULK_PAGE_SIZE)
        timeline_by_story_time = self._group_by(events, "story_time")
        timeline_by_chapter: dict[int, list[dict]] = {}
        for evt in events:
            ch = evt.get("chapter", 0)
            if ch:
                timeline_by_chapter.setdefault(ch, []).append(evt)

        # 3. 关系
        relations, _ = self.kb.list_relations(page=1, page_size=self.BULK_PAGE_SIZE)
        relations_by_pair = self._build_relations_by_pair(relations)

        # 4. 伏笔
        foreshadowings, _ = self.kb.list_foreshadowings(
            page=1, page_size=self.BULK_PAGE_SIZE
        )

        # 5. 章节
        chapters = self.kb.list_chapters(page=1, page_size=self.BULK_PAGE_SIZE)

        # 6. 最大已解析章节
        max_parsed = self.kb.get_max_parsed_chapter()

        return RuleContext(
            characters=characters,
            status_by_char=status_by_char,
            timeline_events=events,
            timeline_by_story_time=timeline_by_story_time,
            timeline_by_chapter=timeline_by_chapter,
            relations=relations,
            relations_by_pair=relations_by_pair,
            foreshadowings=foreshadowings,
            max_parsed_chapter=max_parsed,
            chapters=chapters,
            config=self.config,
        )

    # ── 内部工具 ──────────────────────────────────

    def _parse_status_history(self, char: dict) -> list[dict]:
        """解析角色的 status_history JSON，按 chapter 排序"""
        raw = char.get("status_history", "[]")
        if not raw or raw == "[]":
            return []
        try:
            history = json.loads(raw)
            history.sort(key=lambda h: h.get("chapter", 0))
            return history
        except (json.JSONDecodeError, TypeError):
            logger.warning("角色 %s status_history 解析失败", char.get("name", "?"))
            return []

    def _build_status_by_char(
        self, characters: list[dict]
    ) -> dict[str, list[dict]]:
        """构建 角色名 → status_history 的映射"""
        result: dict[str, list[dict]] = {}
        for char in characters:
            history = self._parse_status_history(char)
            if history:
                result[char["name"]] = history
        return result

    def _build_relations_by_pair(
        self, relations: list[dict]
    ) -> dict[tuple[str, str], list[dict]]:
        """构建 (char_a, char_b) 排序对 → relation 列表的映射"""
        result: dict[tuple[str, str], list[dict]] = {}
        for rel in relations:
            pair = tuple(sorted([rel["char_a"], rel["char_b"]]))
            result.setdefault(pair, []).append(rel)
        return result

    @staticmethod
    def _group_by(
        items: list[dict], key: str
    ) -> dict[str, list[dict]]:
        """按字段分组"""
        result: dict[str, list[dict]] = {}
        for item in items:
            k = str(item.get(key, "") or "")
            result.setdefault(k, []).append(item)
        return result
