"""API Schema 模型测试"""
from datetime import datetime


class TestStatusResponse:
    """健康检查响应模型"""

    def test_default_values(self):
        """StatusResponse 有合理的默认值"""
        from api.schemas import StatusResponse

        resp = StatusResponse()
        assert resp.status == "ok"
        assert resp.version == "0.1.0"
        assert resp.db_size_bytes == 0
        assert resp.chapters_total == 0
        assert resp.chapters_parsed == 0

    def test_custom_values(self):
        """传入自定义值覆盖默认值"""
        from api.schemas import StatusResponse

        resp = StatusResponse(
            status="error",
            chapters_total=10,
            chapters_parsed=5,
        )
        assert resp.status == "error"
        assert resp.chapters_total == 10
        assert resp.chapters_parsed == 5


class TestChapterSchemas:
    """章节响应模型"""

    def test_list_item_minimal(self):
        """ChapterListItem 只要有 num 就能创建"""
        from api.schemas import ChapterListItem

        item = ChapterListItem(num=1)
        assert item.num == 1
        assert item.title == ""
        assert item.status == "pending"
        assert item.summary == ""

    def test_list_item_num_must_be_positive(self):
        """num < 1 时 Pydantic 应拒绝"""
        from api.schemas import ChapterListItem

        try:
            ChapterListItem(num=0)
            assert False, "应抛 ValidationError"
        except Exception as e:
            assert "num" in str(e).lower()

    def test_list_response_structure(self):
        """ChapterListResponse 包含 items 和 total"""
        from api.schemas import ChapterListResponse, ChapterListItem

        items = [ChapterListItem(num=i) for i in range(1, 4)]
        resp = ChapterListResponse(items=items, total=3)
        assert len(resp.items) == 3
        assert resp.total == 3
        assert resp.items[0].num == 1

    def test_chapter_response_fields(self):
        """ChapterResponse 包含所有展示字段"""
        from api.schemas import ChapterResponse

        now = datetime.now().isoformat()
        resp = ChapterResponse(
            num=1,
            title="青云之始",
            status="parsed",
            word_count=3521,
            summary="林婉儿突破金丹期",
            error_msg="",
            created_at=now,
            updated_at=now,
        )
        assert resp.num == 1
        assert resp.title == "青云之始"
        assert resp.word_count == 3521


class TestCharacterSchemas:
    """角色响应模型"""

    def test_list_item_defaults(self):
        """CharacterListItem 必填字段后有合理的默认值"""
        from api.schemas import CharacterListItem

        item = CharacterListItem(name="林婉儿", first_appeared=1, last_seen=1)
        assert item.name == "林婉儿"
        assert item.aliases == []
        assert item.physical == ""
        assert item.location == ""

    def test_list_response_empty(self):
        """CharacterListResponse 支持空列表"""
        from api.schemas import CharacterListResponse

        resp = CharacterListResponse(items=[], total=0)
        assert len(resp.items) == 0
        assert resp.total == 0

    def test_character_response_accepts_status_dict(self):
        """CharacterResponse 的 current_status 接受 dict"""
        from api.schemas import CharacterResponse

        resp = CharacterResponse(
            name="林婉儿",
            first_appeared=1,
            last_seen=3,
            current_status={"physical": "金丹期", "location": "天剑山"},
        )
        assert resp.current_status["physical"] == "金丹期"
        assert resp.current_status["location"] == "天剑山"


class TestRelationSchemas:
    """关系响应模型"""

    def test_relation_response(self):
        """RelationResponse 正确映射关系数据"""
        from api.schemas import RelationResponse

        r = RelationResponse(
            char_a="林婉儿",
            char_b="顾长歌",
            relation="师徒",
            detail="天剑宗掌门弟子",
            chapter=1,
        )
        assert r.char_a == "林婉儿"
        assert r.relation == "师徒"

    def test_list_response(self):
        """RelationListResponse 包含 items 和 total"""
        from api.schemas import RelationListResponse, RelationResponse

        items = [
            RelationResponse(char_a="林婉儿", char_b="顾长歌", relation="师徒", chapter=1),
            RelationResponse(char_a="林婉儿", char_b="赵无极", relation="敌对", chapter=3),
        ]
        resp = RelationListResponse(items=items, total=2)
        assert resp.total == 2


class TestTimelineSchemas:
    """时间线响应模型"""

    def test_timeline_response_defaults(self):
        """TimelineResponse 有合理的默认值"""
        from api.schemas import TimelineResponse

        t = TimelineResponse(chapter=1, event="突破金丹期")
        assert t.story_time == ""
        assert t.narrative_order == 1
        assert t.characters == []
        assert t.is_anomaly is False

    def test_timeline_list_response(self):
        """TimelineListResponse 包含 items 和 total"""
        from api.schemas import TimelineListResponse, TimelineResponse

        items = [
            TimelineResponse(chapter=1, event="突破", narrative_order=1),
            TimelineResponse(chapter=1, event="对话", narrative_order=2),
        ]
        resp = TimelineListResponse(items=items, total=2)
        assert resp.total == 2


class TestForeshadowingSchemas:
    """伏笔响应模型"""

    def test_foreshadowing_defaults(self):
        """ForeshadowingResponse 有合理的默认值"""
        from api.schemas import ForeshadowingResponse

        f = ForeshadowingResponse(
            description="神秘人现身",
            laid_chapter=1,
        )
        assert f.status == "unrecovered"
        assert f.recovered_at is None
        assert f.confidence == 1.0

    def test_foreshadowing_recovered(self):
        """已回收伏笔有回收章号"""
        from api.schemas import ForeshadowingResponse

        f = ForeshadowingResponse(
            description="神秘人现身",
            laid_chapter=1,
            recovered_at=10,
            status="recovered",
        )
        assert f.recovered_at == 10
        assert f.status == "recovered"

    def test_list_response_with_counts(self):
        """ForeshadowingListResponse 包含回收统计"""
        from api.schemas import ForeshadowingListResponse, ForeshadowingResponse

        items = [
            ForeshadowingResponse(description="伏笔1", laid_chapter=1, status="recovered"),
            ForeshadowingResponse(description="伏笔2", laid_chapter=2, status="unrecovered"),
            ForeshadowingResponse(description="伏笔3", laid_chapter=3, status="recovered"),
        ]
        resp = ForeshadowingListResponse(
            items=items, total=3, recovered=2, unrecovered=1,
        )
        assert resp.recovered == 2
        assert resp.unrecovered == 1


class TestErrorResponse:
    """错误响应模型"""

    def test_error_response(self):
        """ErrorResponse 包含错误描述"""
        from api.schemas import ErrorResponse

        e = ErrorResponse(detail="章节不存在")
        assert e.detail == "章节不存在"
