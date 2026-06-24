"""Phase 3 API 端点集成测试"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_kb(tmp_path):
    """创建带测试数据的 KnowledgeBase"""
    from core.knowledge import KnowledgeBase
    import json

    db_path = tmp_path / "agent_data" / "novel.db"
    kb = KnowledgeBase(db_path)
    kb.init_db()

    conn = kb.get_conn()

    # 插入测试章节
    conn.execute(
        "INSERT INTO chapters (num, filename, title, word_count, status, summary) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, "第1章.md", "青云之始", 3521, "parsed", "林婉儿突破金丹期"),
    )
    conn.execute(
        "INSERT INTO chapters (num, filename, title, word_count, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (2, "第2章.md", "秘境探险", 2890, "pending"),
    )

    # 插入测试角色
    conn.execute(
        "INSERT INTO characters (name, aliases, first_appeared, last_seen, "
        "current_status, description) VALUES (?, ?, ?, ?, ?, ?)",
        ("林婉儿", json.dumps(["婉儿", "林师妹"]), 1, 2,
         json.dumps({"physical": "金丹期", "emotional": "坚定", "location": "天剑山"}),
         "天剑宗弟子"),
    )
    conn.execute(
        "INSERT INTO characters (name, aliases, first_appeared, last_seen, "
        "current_status, description) VALUES (?, ?, ?, ?, ?, ?)",
        ("顾长歌", json.dumps(["掌门", "顾师叔"]), 1, 2,
         json.dumps({"physical": "元婴期", "emotional": "沉稳", "location": "天剑山"}),
         "天剑宗掌门"),
    )

    # 插入测试关系
    conn.execute(
        "INSERT INTO relations (char_a, char_b, relation, chapter, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        ("林婉儿", "顾长歌", "师徒", 1, "天剑宗掌门弟子"),
    )

    # 插入测试时间线
    conn.execute(
        "INSERT INTO timeline_events (chapter, story_time, event, narrative_order, "
        "characters, location) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "清晨", "林婉儿突破金丹期", 1,
         json.dumps(["林婉儿"]), "天剑山"),
    )
    conn.execute(
        "INSERT INTO timeline_events (chapter, story_time, event, narrative_order, "
        "characters, location) VALUES (?, ?, ?, ?, ?, ?)",
        (1, "突破后", "顾长歌现身护法", 2,
         json.dumps(["林婉儿", "顾长歌"]), "天剑山"),
    )

    # 插入测试伏笔
    conn.execute(
        "INSERT INTO foreshadowings (description, laid_chapter, status, "
        "related_chars, confidence, confidence_label) VALUES (?, ?, ?, ?, ?, ?)",
        ("神秘黑衣人", 1, "unrecovered", json.dumps(["顾长歌"]), 0.8, "high"),
    )

    conn.commit()
    return kb


@pytest.fixture
def client(test_kb, tmp_path):
    """创建带测试数据库的 FastAPI TestClient"""
    from main import create_app
    from api.deps import get_db

    app = create_app(base_dir=tmp_path)

    # 覆盖依赖注入：路由使用测试数据库
    # get_db 是 generator，覆盖也必须用 generator
    def override_get_db():
        yield test_kb

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c


class TestStatusEndpoint:
    """GET /api/status"""

    def test_status_returns_ok(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["status"] == "ok"
        assert data["data"]["chapters_total"] == 2
        assert data["data"]["chapters_parsed"] == 1


class TestChaptersEndpoint:
    """GET /api/chapters"""

    def test_list_chapters(self, client):
        resp = client.get("/api/chapters")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert len(data["data"]["items"]) == 2
        assert data["data"]["total"] == 2

    def test_list_chapters_pagination(self, client):
        resp = client.get("/api/chapters?page=1&page_size=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1

    def test_chapter_detail_exists(self, client):
        resp = client.get("/api/chapters/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["data"]["num"] == 1
        assert data["data"]["title"] == "青云之始"

    def test_chapter_detail_404(self, client):
        resp = client.get("/api/chapters/999")
        assert resp.status_code == 404
        data = resp.json()
        assert data["ok"] is False
        assert "不存在" in data["error"]


class TestCharactersEndpoint:
    """GET /api/characters"""

    def test_list_characters(self, client):
        resp = client.get("/api/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 2

    def test_list_characters_search(self, client):
        resp = client.get("/api/characters?name=婉儿")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) >= 1

    def test_character_detail_exists(self, client):
        resp = client.get("/api/characters/林婉儿")
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["name"] == "林婉儿"
        assert "金丹期" in str(data["data"]["current_status"])

    def test_character_detail_404(self, client):
        resp = client.get("/api/characters/不存在的人")
        assert resp.status_code == 404


class TestRelationsEndpoint:
    """GET /api/relations"""

    def test_list_relations(self, client):
        resp = client.get("/api/relations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1

    def test_list_relations_with_filter(self, client):
        resp = client.get("/api/relations?char_a=林婉儿")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["items"][0]["char_b"] == "顾长歌"


class TestTimelineEndpoint:
    """GET /api/timeline"""

    def test_list_timeline(self, client):
        resp = client.get("/api/timeline")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 2

    def test_list_timeline_with_chapter_filter(self, client):
        resp = client.get("/api/timeline?chapter=1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 2
        for item in data["data"]["items"]:
            assert item["chapter"] == 1


class TestForeshadowingsEndpoint:
    """GET /api/foreshadowings"""

    def test_list_foreshadowings(self, client):
        resp = client.get("/api/foreshadowings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1
        assert data["data"]["unrecovered"] == 1
        assert data["data"]["recovered"] == 0

    def test_list_foreshadowings_filter_by_status(self, client):
        resp = client.get("/api/foreshadowings?status=unrecovered")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]["items"]) == 1
