def test_init_db_creates_all_tables(tmp_db_path):
    """初始化后数据库中应存在6张核心表"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    conn = kb.get_conn()
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    assert "chapters" in tables
    assert "characters" in tables
    assert "relations" in tables
    assert "timeline_events" in tables
    assert "foreshadowings" in tables
    assert "llm_parse_logs" in tables

def test_init_db_is_idempotent(tmp_db_path):
    """连续两次init——db不应抛出异常"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    # 第二次调用不应抛异常
    kb.init_db()

    # 再次验证 5 张表仍在
    conn = kb.get_conn()
    cursor = conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table'"
    )
    count = cursor.fetchone()[0]
    assert count >= 5

def test_wal_mode_on_connection(tmp_db_path):
    """数据库连接应启用WAL模式"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    conn = kb.get_conn()
    cursor = conn.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]

    assert mode == "wal"

def test_foreign_keys_enabled(tmp_db_path):
    """数据库连接应默认开启外键约束"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    conn = kb.get_conn()
    cursor = conn.execute("PRAGMA foreign_keys")
    mode = cursor.fetchone()[0]
    assert mode == 1
    # PRAGMA foreign_keys 返回 0 或 1：
    #     - 1 = 开启
    #     - 0 = 关闭

def test_thread_local_connections(tmp_db_path):
    """多线程环境下各线程应获取不同的连接对象"""
    import threading
    from core.knowledge import KnowledgeBase
    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    connections = {}

    def get_conn_for_thread(thread_id):
        conn = kb.get_conn()
        connections[thread_id] = id(conn)

    threads = [
        threading.Thread(target=get_conn_for_thread, args=(i,))
          for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert connections[0] != connections[1]

def test_chapter_default_status_pending(tmp_db_path):
    """chapters表的status列默认值应为pending"""
    from core.knowledge import KnowledgeBase
    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    conn = kb.get_conn()
    # 查询 status 列的默认值
    cursor = conn.execute("PRAGMA table_info(chapters)")
    columns = cursor.fetchall()

    # (cid, name, type, notnull, default_value, pk)
    # 列编号，列名，列类型，是否不能为空，默认值，是否主键
    # 例：(3, "status", "TEXT", 0, "'pending'", 0) 
    # 0指不为空，不为主键
    status_col = [col for col in columns if col[1] == "status"]
    assert len(status_col) == 1

    default_value = status_col[0][4]  # 第5列是 default
    assert default_value == "'pending'"
    
def test_list_chapters_empty(tmp_db_path):
    """数据库无章节时返回空列表"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    chapters = kb.list_chapters()
    assert chapters == []

def test_list_chapters_with_data(tmp_db_path):
    """插入3章后 list_chapters 应全部返回，按num升序"""
    from core.knowledge import KnowledgeBase
    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()
    conn = kb.get_conn()

    # 插入 3 章（故意乱序插，验证排序）
    conn.execute(
        "INSERT INTO chapters (num, filename, title, status) VALUES (?, ?, ?, ?)",
        (3, "第3章.md", "秘境探险", "parsed"),
    )
    conn.execute("INSERT INTO chapters (num, filename, title,status) VALUES (?, ?, ?, ?)",
        (1, "第1章.md", "青云之始", "parsed"),
    )
    conn.execute("INSERT INTO chapters (num, filename, status) VALUES (?, ?, ?)",
        (2, "第2章.md", "pending"),
    )
    conn.commit()

    chapters = kb.list_chapters()

    assert len(chapters) == 3
    assert chapters[0]["num"] == 1   # 按 num 升序
    assert chapters[1]["num"] == 2
    assert chapters[2]["num"] == 3
    assert chapters[0]["title"] == "青云之始"

def test_list_chapters_filter_by_status(tmp_db_path):
    """传入 status 参数后只返回匹配状态的章节"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()
    conn = kb.get_conn()

    conn.execute("INSERT INTO chapters (num, filename, status) VALUES (?, ?, ?)",
        (1, "第1章.md", "parsed"),
    )
    conn.execute("INSERT INTO chapters (num, filename, status) VALUES (?, ?, ?)",
        (2, "第2章.md", "pending"),
    )
    conn.execute("INSERT INTO chapters (num, filename, status) VALUES (?, ?, ?)",
        (3, "第3章.md", "parsed"),
    )
    conn.commit()

    parsed = kb.list_chapters(status="parsed")
    assert len(parsed) == 2
    assert all(c["status"] == "parsed" for c in parsed)

    pending = kb.list_chapters(status="pending")
    assert len(pending) == 1
    assert pending[0]["num"] == 2

def test_list_chapters_pagination(tmp_db_path):
    """page 和 page_size 参数控制分页"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()
    conn = kb.get_conn()

    for i in range(1, 6):
        conn.execute(
            "INSERT INTO chapters (num, filename) VALUES(?, ?)",
            (i, f"第{i}章.md"),
        )
    conn.commit()

    # 第 2 页，每页 2 条
    page = kb.list_chapters(page=2, page_size=2)
    assert len(page) == 2
    assert page[0]["num"] == 3
    assert page[1]["num"] == 4

    # page 超出范围时返回空
    empty = kb.list_chapters(page=10, page_size=2)
    assert empty == []

    # page=1, page_size=100 超过总数也只返回全部
    all_chapters = kb.list_chapters(page=1,page_size=100)
    assert len(all_chapters) == 5


def test_get_chapter_exists(tmp_db_path):
    """存在的章节返回完整字段"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()
    conn = kb.get_conn()

    conn.execute(
        "INSERT INTO chapters (num, filename, title, word_count, status, summary) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (1, "第1章.md", "青云之始", 3521, "parsed","林婉儿突破金丹期"),
    )
    conn.commit()

    chapter = kb.get_chapter(1)
    assert chapter is not None
    assert chapter["num"] == 1
    assert chapter["title"] == "青云之始"
    assert chapter["word_count"] == 3521
    assert chapter["status"] == "parsed"
    assert chapter["summary"] == "林婉儿突破金丹期"

def test_get_chapter_not_found(tmp_db_path):
    """不存在的章节返回 None"""
    from core.knowledge import KnowledgeBase

    kb = KnowledgeBase(tmp_db_path)
    kb.init_db()

    chapter = kb.get_chapter(999)
    assert chapter is None



