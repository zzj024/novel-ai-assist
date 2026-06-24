"""API 路由注册
职责：
    - 定义所有 REST 端点的 URL 路径与方法
    - 调用 KnowledgeBase 获取数据 + ok()/err() 包装返回
    - 参数校验由 FastAPI 通过类型注解自动处理
"""

from fastapi import APIRouter, Depends, Query

from api.responses import err, ok
from api.schemas import (
    ChapterListResponse,
    ChapterListItem,
    ChapterResponse,
    CharacterListResponse,
    CharacterListItem,
    CharacterResponse,
    RelationListResponse,
    RelationResponse,
    StatusResponse,
    TimelineListResponse,
    TimelineResponse,
    ForeshadowingListResponse,
    ForeshadowingResponse,
)
from core.knowledge import KnowledgeBase
from api.deps import get_db
import json

router = APIRouter(prefix="/api")


# ── 工具函数 ──────────────────────────────────

def _parse_json_list(raw: str) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_json_dict(raw: str) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _parse_status_field(raw: str, field: str) -> str:
    d = _parse_json_dict(raw)
    return d.get(field, "")


# ── 健康检查 ──────────────────────────────────

@router.get("/status", response_model=StatusResponse)
def get_status(kb: KnowledgeBase = Depends(get_db)):
    """服务状态 + 数据库统计"""
    total = kb.count_chapters()
    parsed = kb.count_chapters(status="parsed")
    return ok(data=StatusResponse(
        status="ok",
        chapters_total=total,
        chapters_parsed=parsed,
    ))

@router.get("/chapters", response_model=ChapterListResponse)
def list_chapters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    kb: KnowledgeBase = Depends(get_db),
):
    chapters = kb.list_chapters(page=page, page_size=page_size)
    items = [
        ChapterListItem(
            num=c["num"],
            title=c.get("title", ""),
            status=c.get("status", "pending"),
            word_count=c.get("word_count", 0),
            summary=(c.get("summary", "") or "")[:200],
            updated_at=c.get("updated_at", ""),
        )
        for c in chapters
    ]
    return ok(data=ChapterListResponse(items=items, total=len(items)))

@router.get("/chapters/{num}", response_model=ChapterResponse)
def get_chapter(num: int, kb: KnowledgeBase = Depends(get_db)):
    chapter = kb.get_chapter(num)
    if chapter is None:
        return err("章节不存在", status_code=404)
    return ok(data=ChapterResponse(
        num=chapter["num"], title=chapter.get("title", ""),
        status=chapter.get("status", "pending"),
        word_count=chapter.get("word_count", 0),
        summary=chapter.get("summary", ""),
        error_msg=chapter.get("error_msg") or "",
        created_at=chapter.get("created_at", ""),
        updated_at=chapter.get("updated_at", ""),
    ))

@router.get("/characters", response_model=CharacterListResponse)
def list_characters(
    name: str | None = Query(None),
    kb: KnowledgeBase = Depends(get_db),
):
    characters = kb.list_characters(name=name)
    items = [
        CharacterListItem(
            name=c["name"],
            aliases=_parse_json_list(c.get("aliases", "[]")),
            first_appeared=c["first_appeared"],
            last_seen=c["last_seen"],
            physical=_parse_status_field(c.get("current_status","{}"), "physical"),
            location=_parse_status_field(c.get("current_status","{}"), "location"),
        )
        for c in characters
    ]
    return ok(data=CharacterListResponse(items=items, total=len(items)))

@router.get("/characters/{name}", response_model=CharacterResponse)
def get_character(name: str, kb: KnowledgeBase = Depends(get_db)):
    char = kb.get_character(name)
    if char is None:
        return err("角色不存在", status_code=404)
    return ok(data=CharacterResponse(
        name=char["name"],
        aliases=_parse_json_list(char.get("aliases", "[]")),
        first_appeared=char["first_appeared"],
        last_seen=char["last_seen"],
        current_status=_parse_json_dict(char.get("current_status","{}")),
        description=char.get("description", ""),
        updated_at=char.get("updated_at", ""),
    ))

@router.get("/relations", response_model=RelationListResponse)
def list_relations(
    char_a: str | None = Query(None),
    char_b: str | None = Query(None),
    kb: KnowledgeBase = Depends(get_db),
):
    relations = kb.list_relations(char_a=char_a, char_b=char_b)
    items = [
        RelationResponse(
            char_a=r["char_a"], char_b=r["char_b"],
            relation=r["relation"], detail=r.get("detail", ""),
            chapter=r["chapter"],
        )
        for r in relations
    ]
    return ok(data=RelationListResponse(items=items, total=len(items)))

@router.get("/timeline", response_model=TimelineListResponse)
def list_timeline(
    chapter: int | None = Query(None, ge=1),
    kb: KnowledgeBase = Depends(get_db),
):
    events = kb.list_timeline(chapter=chapter)
    items = [
        TimelineResponse(
            chapter=e["chapter"], 
            story_time=e.get("story_time", ""),
            event=e["event"],
            narrative_order=e.get("narrative_order", 1),
            characters=_parse_json_list(e.get("characters","[]")),
            location=e.get("location", ""),
            evidence=e.get("evidence", ""),
            is_anomaly=bool(e.get("is_anomaly", 0)),
        )
        for e in events
    ]
    return ok(data=TimelineListResponse(items=items, total=len(items)))

@router.get("/foreshadowings", response_model=ForeshadowingListResponse)
def list_foreshadowings(
    status: str | None = Query(None),
    kb: KnowledgeBase = Depends(get_db),
):
    items = kb.list_foreshadowings(status=status)
    total = len(items)
    recovered = sum(1 for f in items if f.get("status") == "recovered")
    unrecovered = total - recovered
    foreshadowings = [
        ForeshadowingResponse(
            description=f["description"],
            laid_chapter=f["laid_chapter"],
            recovered_at=f.get("recovered_at"),
            status=f.get("status", "unrecovered"),
            related_chars=_parse_json_list(f.get("related_chars","[]")),
            evidence=f.get("evidence", ""),
            confidence=f.get("confidence", 1.0),
            confidence_label=f.get("confidence_label", "medium"),
        )
        for f in items
    ]
    return ok(data=ForeshadowingListResponse(
        items=foreshadowings, total=total,
        recovered=recovered, unrecovered=unrecovered,
    ))

