"""SQLite 数据库连接管理 + 表结构初始化

KnowledgeBase 是数据库访问的入口，职责：
- 线程安全的连接管理（threading.local）
- 5 张核心表的幂等建表
- WAL 模式 / 外键约束 / busy_timeout 的 PRAGMA 设置
"""
import sqlite3
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """SQLite 数据库连接管理与表结构初始化

    - __init__ 只存储路径，不打开连接（延迟初始化）
    - get_conn() 使用 threading.local() 实现线程级连接缓存
    - init_db() 幂等创建 5 张核心表
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.local = threading.local()

    # ── 连接管理 ──────────────────────────────────────

    def get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接（线程隔离，延迟创建）"""
        if not hasattr(self.local, "conn") or self.local.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")

            self.local.conn = conn
        return self.local.conn

    # ── 建表 ──────────────────────────────────────────

    def init_db(self) -> None:
        """创建 5 张核心表 + 索引（幂等，可重复调用）"""
        conn = self.get_conn()

        conn.executescript("""
            -- chapters：章节索引
            CREATE TABLE IF NOT EXISTS chapters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                num         INTEGER UNIQUE NOT NULL,
                filename    TEXT NOT NULL,
                title       TEXT,
                word_count  INTEGER DEFAULT 0,
                status      TEXT DEFAULT 'pending',
                raw_text    TEXT,
                summary     TEXT,
                error_msg   TEXT,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_size   INTEGER DEFAULT 0,    -- 文件大小（字节）
                file_hash TEXT DEFAULT ''      -- MD5 哈希
            );
            CREATE INDEX IF NOT EXISTS idx_chapters_num ON chapters(num);
            CREATE INDEX IF NOT EXISTS idx_chapters_status ON chapters(status);

            -- characters：人物 + 状态快照
            CREATE TABLE IF NOT EXISTS characters (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                name            TEXT NOT NULL UNIQUE,
                aliases         TEXT DEFAULT '[]',
                first_appeared  INTEGER NOT NULL,
                last_seen       INTEGER NOT NULL,
                current_status  TEXT DEFAULT '{}',
                status_history  TEXT DEFAULT '[]',
                description     TEXT DEFAULT '',
                updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(name);
            CREATE INDEX IF NOT EXISTS idx_characters_last_seen ON characters(last_seen);

            -- relations：人物关系
            CREATE TABLE IF NOT EXISTS relations (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                char_a      TEXT NOT NULL,
                char_b      TEXT NOT NULL,
                relation    TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                detail      TEXT DEFAULT '',
                UNIQUE(char_a, char_b, relation)
            );
            CREATE INDEX IF NOT EXISTS idx_relations_char_a ON relations(char_a);
            CREATE INDEX IF NOT EXISTS idx_relations_char_b ON relations(char_b);

            -- timeline_events：时间线事件
            CREATE TABLE IF NOT EXISTS timeline_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter     INTEGER NOT NULL,
                story_time  TEXT,
                event       TEXT NOT NULL,
                characters  TEXT DEFAULT '[]',
                is_anomaly  INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_timeline_chapter ON timeline_events(chapter);

            -- foreshadowings：伏笔
            CREATE TABLE IF NOT EXISTS foreshadowings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                description     TEXT NOT NULL,
                laid_chapter    INTEGER NOT NULL,
                recovered_at    INTEGER,
                status          TEXT DEFAULT 'unrecovered',
                related_chars   TEXT DEFAULT '[]',
                confidence      REAL DEFAULT 1.0
            );
            CREATE INDEX IF NOT EXISTS idx_foreshadowings_status ON foreshadowings(status);
            CREATE INDEX IF NOT EXISTS idx_foreshadowings_laid ON foreshadowings(laid_chapter);
        """)
