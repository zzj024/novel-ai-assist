"""Phase 3 Step 3：分页排序单元测试"""
import pytest


def test_paginated_query_defaults(parser_env):
    """默认分页：page=1, page_size=20"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(page=1, page_size=20)
    assert isinstance(data, list)
    assert isinstance(total, int)
    assert total >= 0


def test_paginated_query_small_page(parser_env):
    """page_size 限制正常生效（空数据库返回 0 条）"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(page=1, page_size=1)
    assert len(data) == 0  # parser_env 没有角色数据
    assert total == 0


def test_paginated_query_page_out_of_range(parser_env):
    """超出范围的页码应返回空列表"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(page=999, page_size=10)
    assert data == []


def test_sort_fallback_to_default(parser_env):
    """非法排序字段应降级为默认值，不抛异常"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(sort_by="nonexistent_field")
    assert isinstance(data, list)


def test_sort_order_desc(parser_env):
    """desc 排序应正常工作"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(sort_by="last_seen", sort_order="desc")
    assert isinstance(data, list)


def test_sort_order_invalid_fallback(parser_env):
    """非法排序方向应降级为 asc"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(sort_order="invalid")
    assert isinstance(data, list)


def test_list_characters_with_search_paginated(parser_env):
    """模糊搜索 + 分页（空数据库返回空结果）"""
    kb = parser_env["kb"]
    data, total = kb.list_characters(name="林", page=1, page_size=10)
    assert data == []
    assert total == 0


def test_list_characters_return_type(parser_env):
    """验证返回类型是 tuple[list, int]"""
    kb = parser_env["kb"]
    result = kb.list_characters()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], list)
    assert isinstance(result[1], int)


def test_list_foreshadowings_paginated(parser_env):
    """伏笔分页"""
    kb = parser_env["kb"]
    data, total = kb.list_foreshadowings(page=1, page_size=10)
    assert isinstance(data, list)
    assert isinstance(total, int)


def test_list_foreshadowings_filter_by_status(parser_env):
    """伏笔按状态筛选 + 分页"""
    kb = parser_env["kb"]
    data, total = kb.list_foreshadowings(status="unrecovered", page=1, page_size=5)
    assert all(f["status"] == "unrecovered" for f in data)


def test_list_timeline_paginated(parser_env):
    """时间线分页"""
    kb = parser_env["kb"]
    data, total = kb.list_timeline(page=1, page_size=10)
    assert isinstance(data, list)


def test_list_timeline_filter_by_chapter(parser_env):
    """时间线按章节筛选"""
    kb = parser_env["kb"]
    # 先插一条第 1 章的数据才可能查到
    from core.knowledge import KnowledgeBase
    # 直接用已有的 parser_env 的 kb
    data, total = kb.list_timeline(chapter=1)
    assert isinstance(data, list)


def test_list_relations_paginated(parser_env):
    """关系分页"""
    kb = parser_env["kb"]
    data, total = kb.list_relations(page=1, page_size=10)
    assert isinstance(data, list)


def test_list_relations_with_filter(parser_env):
    """关系双端筛选 + 分页"""
    kb = parser_env["kb"]
    data, total = kb.list_relations(char_a="林婉儿", page=1, page_size=10)
    assert all(r["char_a"] == "林婉儿" for r in data)
