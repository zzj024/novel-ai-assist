def test_init_db_creates_all_tables(tmp_db_path):
    """初始化后数据库中应存在5张核心表"""
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
    





