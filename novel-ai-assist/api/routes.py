"""API 路由注册
职责：
    - 定义所有 REST 端点的 URL 路径与方法
    - 调用 KnowledgeBase 获取数据 + ok()/err() 包装返回
    - 参数校验由 FastAPI 通过类型注解自动处理
"""

import json
import logging
import time

from fastapi import APIRouter, Depends, Query, Request

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
    QueryRequest,
    QueryResponse,
    QueryExplainResponse,
)
from core.knowledge import KnowledgeBase
from api.deps import get_db



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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("first_appeared"),
    sort_order: str = Query("asc"),
    kb: KnowledgeBase = Depends(get_db),
):
    characters, total = kb.list_characters(
        name=name, page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )
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
    return ok(data=CharacterListResponse(items=items, total=total))

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
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("chapter"),
    sort_order: str = Query("asc"),
    kb: KnowledgeBase = Depends(get_db),
):
    relations, total = kb.list_relations(
        char_a=char_a, char_b=char_b,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )
    items = [
        RelationResponse(
            char_a=r["char_a"], char_b=r["char_b"],
            relation=r["relation"], detail=r.get("detail", ""),
            chapter=r["chapter"],
        )
        for r in relations
    ]
    return ok(data=RelationListResponse(items=items, total=total))

@router.get("/timeline", response_model=TimelineListResponse)
def list_timeline(
    chapter: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("narrative_order"),
    sort_order: str = Query("asc"),
    kb: KnowledgeBase = Depends(get_db),
):
    events,total = kb.list_timeline(
        chapter=chapter,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )
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
    return ok(data=TimelineListResponse(items=items, total=total))

@router.get("/foreshadowings", response_model=ForeshadowingListResponse)
def list_foreshadowings(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("laid_chapter"),
    sort_order: str = Query("asc"),
    kb: KnowledgeBase = Depends(get_db),
):
    items_list, total = kb.list_foreshadowings(
        status=status,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )
    recovered = sum(1 for f in items_list if f.get("status") == "recovered")
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
        for f in items_list
    ]
    return ok(data=ForeshadowingListResponse(
        items=foreshadowings, total=total,
        recovered=recovered, unrecovered=unrecovered,
    ))


# ── 对话查询 ──────────────────────────────────


from functools import cache

from openai import OpenAI as _OpenAI


@cache
def _get_cheap_client() -> _OpenAI:
    """缓存小模型客户端（qwen2.5:7b，本地）"""
    from config import load_config
    cfg = load_config()
    return _OpenAI(api_key="", base_url=cfg.query_cheap_base)


@cache
def _get_expensive_client() -> _OpenAI:
    """缓存大模型客户端（DeepSeek）"""
    from config import load_config
    cfg = load_config()
    return _OpenAI(api_key=cfg.api_key, base_url=cfg.api_base)


@router.post("/query", response_model=QueryResponse)
def query_question(
    req: QueryRequest,
    kb: KnowledgeBase = Depends(get_db),
):
    """对话式查询——自然语言问任何已记录的信息"""
    from core.query import QueryEngine

    engine = QueryEngine(kb, _get_cheap_client(), _get_expensive_client())
    result = engine.run(req.question, debug=req.debug)
    return ok(data=QueryResponse(
        answer=result.get("answer", ""),
        source=result.get("source", "unknown"),
        debug_trace=result.get("debug_trace"),
    ))


@router.post("/query/debug", response_model=QueryExplainResponse)
def query_explain(
    req: QueryRequest,
    kb: KnowledgeBase = Depends(get_db),
):
    """查询路由解释——展示 query 引擎内部决策过程"""
    from core.query import QueryEngine

    engine = QueryEngine(kb, _get_cheap_client(), _get_expensive_client())
    engine.run(req.question, debug=True)
    trace = engine._debug_trace or []

    sub_questions = []
    for entry in trace:
        sub_questions.append({
            "original": entry.get("original", ""),
            "entities": entry.get("entities_after", []),
            "intent": entry.get("intent_after", ""),
            "intent_scores": entry.get("intent_scores", {}),
        })

    return ok(data=QueryExplainResponse(
        question=req.question,
        sub_questions=sub_questions,
        debug_trace=trace,
    ))


# ── WebSocket ──────────────────────────────────


from fastapi import WebSocket, WebSocketDisconnect


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 实时推送——接收解析状态变更通知"""
    manager = ws.app.state.ws_manager
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── 手动触发解析 ──────────────────────────────




@router.post("/reparse/{num}")
async def reparse_chapter(num: int, kb: KnowledgeBase = Depends(get_db)):
    """手动触发某章的 LLM 解析，完成后广播 WebSocket"""
    from core.parser import ChapterParser
    from config import load_config
    from pathlib import Path

    chapter = kb.get_chapter(num)
    if not chapter:
        return err("章节不存在", status_code=404)

    if not chapter.get("raw_text"):
        return err(f"第{num}章没有正文（raw_text 为空），无法解析", status_code=400)

    settings = load_config(Path("agent_data") / "config.json")
    parser = ChapterParser(settings, kb)

    # 注入广播器
    manager = ws.app.state.ws_manager

    def broadcaster(result: dict):
        manager.broadcast({
            "type": "chapter_parsed",
            "data": {
                "num": result["chapter_num"],
                "status": "ok" if result["ok"] else "error",
                "error": result.get("error"),
            },
        })

    parser.broadcaster = broadcaster
    result = parser.parse_and_store(
        chapter_text=chapter["raw_text"],
        chapter_num=num,
        filename=chapter.get("filename", f"第{num}章.md"),
    )

    if not result["ok"]:
        return err(f"解析失败：{result.get('error', '未知错误')}", status_code=500)

    return ok(data={"num": num, "status": "parsed"})


# ── 矛盾检测 ─────────────────────────────────


from core.contradiction.engine import ContradictionEngine


@router.post("/contradictions/scan")
async def scan_contradictions(
    request: Request,
    kb: KnowledgeBase = Depends(get_db),
):
    """触发全量矛盾扫描"""
    engine = ContradictionEngine(kb)
    result = engine.scan_all()

    # WebSocket 广播
    try:
        manager = request.app.state.ws_manager
        manager.broadcast({
            "type": "contradiction_scan_complete",
            "data": {
                "total": result.summary.total,
                "critical_count": result.summary.by_severity.get("critical", 0),
                "warning_count": result.summary.by_severity.get("warning", 0),
                "open_count": result.summary.open_count,
                "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
        })
    except Exception:
        pass

    return ok(data={
        "summary": {
            "total": result.summary.total,
            "by_severity": result.summary.by_severity,
            "by_issue_type": result.summary.by_issue_type,
            "by_contradiction_type": result.summary.by_contradiction_type,
            "open_count": result.summary.open_count,
            "dismissed_count": result.summary.dismissed_count,
            "duration_ms": result.summary.duration_ms,
        },
    })


@router.get("/contradictions")
def list_contradictions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: str | None = Query(None, alias="type"),
    severity: str | None = Query(None, alias="severity"),
    issue_type: str | None = Query(None, alias="issue_type"),
    sort_by: str = Query("severity"),
    sort_order: str = Query("desc"),
    include_dismissed: bool = Query(False),
    kb: KnowledgeBase = Depends(get_db),
):
    """获取矛盾检测结果列表，支持筛选和分页"""
    engine = ContradictionEngine(kb)
    items, total, summary = engine.get_paginated_results(
        page=page,
        page_size=page_size,
        type_filter=type,
        severity_filter=severity,
        issue_type_filter=issue_type,
        sort_by=sort_by,
        sort_order=sort_order,
        include_dismissed=include_dismissed,
    )

    contradiction_items = [
        {
            "fingerprint": r.fingerprint,
            "issue_type": r.issue_type.value,
            "kind": r.kind.value,
            "severity": r.severity.value,
            "contradiction_type": r.contradiction_type.value,
            "rule_name": r.rule_name,
            "description": r.description,
            "detail": r.detail,
            "evidence": r.evidence,
            "chapter_range": [r.chapter_range[0], r.chapter_range[1]],
            "related_chars": r.related_chars,
            "score": r.score,
            "status": r.status,
            "explained": r.explained,
        }
        for r in items
    ]

    return ok(data={
        "items": contradiction_items,
        "total": total,
        "summary": {
            "total": summary.total,
            "by_severity": summary.by_severity,
            "by_issue_type": summary.by_issue_type,
            "by_contradiction_type": summary.by_contradiction_type,
            "open_count": summary.open_count,
            "dismissed_count": summary.dismissed_count,
            "duration_ms": summary.duration_ms,
        },
    })


@router.get("/contradictions/summary")
def get_contradiction_summary(kb: KnowledgeBase = Depends(get_db)):
    """获取矛盾检测摘要"""
    engine = ContradictionEngine(kb)
    cached = engine.get_cached()
    if not cached:
        result = engine.scan_all()
        summary = result.summary
    else:
        summary = cached.summary

    return ok(data={
        "total": summary.total,
        "by_severity": summary.by_severity,
        "by_issue_type": summary.by_issue_type,
        "by_contradiction_type": summary.by_contradiction_type,
        "open_count": summary.open_count,
        "dismissed_count": summary.dismissed_count,
        "duration_ms": summary.duration_ms,
    })


# ── 矛盾检测审查管理 ──────────────────────────

from pydantic import BaseModel as _ReviewBase


class _ReviewAction(_ReviewBase):
    """审查操作请求"""
    reason: str = ""
    note: str = ""


@router.post("/contradictions/{fingerprint}/dismiss")
def dismiss_contradiction(
    fingerprint: str,
    body: _ReviewAction,
    kb: KnowledgeBase = Depends(get_db),
):
    """忽略一条检测结果"""
    engine = ContradictionEngine(kb)
    cached = engine.get_cached()
    if not cached:
        cached = engine.scan_all()
    target = next((r for r in cached.results if r.fingerprint == fingerprint), None)
    if not target:
        return err("fingerprint 不存在", status_code=404)
    kb.save_review(
        fingerprint=fingerprint,
        rule_name=target.rule_name,
        rule_version=target.rule_version,
        type_str=target.contradiction_type.value,
        kind=target.kind.value,
        severity=target.severity.value,
        status="dismissed",
        reason=body.reason,
    )
    return ok(data={"fingerprint": fingerprint, "status": "dismissed"})


@router.post("/contradictions/{fingerprint}/confirm")
def confirm_contradiction(
    fingerprint: str,
    body: _ReviewAction,
    kb: KnowledgeBase = Depends(get_db),
):
    """确认一条检测结果"""
    engine = ContradictionEngine(kb)
    cached = engine.get_cached()
    if not cached:
        cached = engine.scan_all()
    target = next((r for r in cached.results if r.fingerprint == fingerprint), None)
    if not target:
        return err("fingerprint 不存在", status_code=404)
    kb.save_review(
        fingerprint=fingerprint,
        rule_name=target.rule_name,
        rule_version=target.rule_version,
        type_str=target.contradiction_type.value,
        kind=target.kind.value,
        severity=target.severity.value,
        status="confirmed",
        reason=body.reason,
    )
    return ok(data={"fingerprint": fingerprint, "status": "confirmed"})


@router.delete("/contradictions/{fingerprint}/review")
def reset_contradiction_review(
    fingerprint: str,
    kb: KnowledgeBase = Depends(get_db),
):
    """取消审查状态（重置为 open）"""
    existing = kb.get_review(fingerprint)
    if not existing:
        return err("该结果尚未被审查", status_code=404)
    kb.save_review(
        fingerprint=fingerprint,
        rule_name=existing["rule_name"],
        rule_version=existing.get("rule_version", ""),
        type_str=existing["type"],
        kind=existing["kind"],
        severity=existing["severity"],
        status="open",
        reason="",
    )
    return ok(data={"fingerprint": fingerprint, "status": "open"})

