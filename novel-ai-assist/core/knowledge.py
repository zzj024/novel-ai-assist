"""
SQLite 数据库连接管理 + 表结构初始化 + 事务写入
KnowledgeBase 是数据库访问的入口，职责：
    - 线程安全的连接管理（threading.local）
    - 6 张核心表的幂等建表（含 Schema 迁移）
    - 事务性覆盖写入（Parser 调用入口）
"""

import sqlite3
import threading
import logging
from pathlib import Path
from typing import Optional
from core.models import ChapterExtract

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """SQLite 数据库连接管理与表结构初始化

    - __init__ 只存储路径，不打开连接（延迟初始化）
    - get_conn() 使用 threading.local() 实现线程级连接缓存
    - init_db() 幂等创建 6 张核心表
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.local = threading.local()

    def close(self) -> None:
        """关闭当前线程的数据库连接（解决 Windows 临时文件清理问题）"""
        if hasattr(self.local, "conn") and self.local.conn is not None:
            self.local.conn.close()
            self.local.conn = None

    # ── Phase 3：读方法 ──────────────────────────────
    def list_chapters(self, page: int = 1, page_size: int = 10, status: Optional[str] = None,) -> list[dict]:
        """章节分页列表，按 num 升序
        参数：
            page:     页码（从 1 开始）
            page_size: 每页条数
            status:   按状态过滤（None=全部）
        返回：
            list[dict]: 每项含 chapters 表全部字段
        """
        conn = self.get_conn()
        offset = (page - 1) * page_size

        if(status):
            rows = conn.execute(
                "SELECT * FROM chapters WHERE status = ?"
                "ORDER BY num LIMIT ? OFFSET ?",
                (status, page_size, offset),
            )
        else:
            rows = conn.execute(
                "SELECT * FROM chapters ORDER BY num LIMIT ? OFFSET ?",
                (page_size, offset),
            )
        return [dict(r) for r in rows.fetchall()]

    def get_chapter(self, num: int) -> Optional[dict]:
        """按章序号查询单章完整信息
        参数：
            num: 章序号
        返回：
            dict: chapters 表全部字段
            None: 章节不存在
        """
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM chapters WHERE num = ?",(num,)).fetchone()
        return dict(row) if row else None

    def get_character(self, name: str) -> Optional[dict]:
        """按角色名查询完整信息
        参数：
            name: 角色名（精确匹配）

        返回：
            dict: characters 表全部字段
            None: 角色不存在
        """
        conn = self.get_conn()
        row = conn.execute("SELECT * FROM characters WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

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

    def _paginated_query(
                self,
                table: str,
                where_clause: str,
                params: list,
                sort_by: str,
                sort_order: str,
                page: int,
                page_size: int,
                allowed_sorts: list[str],
        ) -> tuple[list[dict], int]:
            """通用分页排序查询
            参数：
                table:         表名
                where_clause:  WHERE 子句（无筛选时传 "1=1"）
                params:        WHERE 参数列表
                sort_by:       排序字段（不在白名单则降级为allowed_sorts[0]）
                sort_order:    排序方向（"asc" 或 "desc"）
                page:          页码（从 1 开始）
                page_size:     每页条数
                allowed_sorts: 排序字段白名单
    
            返回：
                (list[dict], total_count)
              """
    
            conn = self.get_conn()
    
            # 安全校验：排序字段必须在白名单内
            if sort_by not in allowed_sorts:
                sort_by = allowed_sorts[0]
    
            # 安全校验：排序方向只允许asc / desc
            if sort_order not in ("asc", "desc"):
                sort_order = "asc"
    
            # 计数查询
            count_row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {where_clause}",
                params,
            ).fetchone()[0]
    
            # 分页数据查询
            offset = (page - 1) * page_size
            order_sql = f"{sort_by} {sort_order}"
            rows = conn.execute(
                f"SELECT * FROM {table} WHERE {where_clause} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()

            return [dict(r) for r in rows], count_row
    
    def count_chapters(self, status: str | None = None) -> int:
        """统计章节总数
        参数：status: 按状态筛选（None=全部，'parsed'=已解析等）
        返回：int: 符合条件的章节数
        """
        conn = self.get_conn()
        if status:
            row = conn.execute("SELECT COUNT(*) FROM chapters WHERE status = ?",(status,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM chapters").fetchone()
        return row[0]

    def list_characters(
        self,
        name: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "first_appeared",
        sort_order: str = "asc",
    ) -> tuple[list[dict], int]:
        """
        角色列表，支持模糊搜索 + 分页排序
        返回 (数据列表, 总数)
        """
        allowed_sorts = ["name", "first_appeared", "last_seen"]
        if name:
            return self._paginated_query(
                "characters", "name LIKE ?", [f"%{name}%"],
                sort_by, sort_order, page, page_size, allowed_sorts,
            )
        return self._paginated_query(
            "characters", "1=1", [],
            sort_by, sort_order, page, page_size, allowed_sorts,
        )

    def list_relations(
        self,
        char_a: str | None = None,
        char_b: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "chapter",
        sort_order: str = "asc",
    ) -> tuple[list[dict], int]:
        """
        人物关系列表，支持双端筛选 + 分页排序
        返回 (数据列表, 总数)
        """
        conditions: list[str] = []
        params: list[str] = []
        if char_a:
            conditions.append("char_a = ?")
            params.append(char_a)
        if char_b:
            conditions.append("char_b = ?")
            params.append(char_b)
        where = " AND ".join(conditions) if conditions else "1=1"
        allowed_sorts = ["char_a", "char_b", "relation","chapter"]
        return self._paginated_query(
            "relations", where, params,
            sort_by, sort_order, page, page_size, allowed_sorts,
        )

    def list_timeline(
        self,
        chapter: int | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "narrative_order",
        sort_order: str = "asc",
    ) -> tuple[list[dict], int]:
        """
        时间线事件列表，支持按章节筛选 + 分页排序
        返回 (数据列表, 总数)
        """
        allowed_sorts = ["chapter", "story_time","narrative_order"]
        if chapter is not None:
            return self._paginated_query(
                "timeline_events", "chapter = ?", [chapter],
                sort_by, sort_order, page, page_size,allowed_sorts,
            )
        return self._paginated_query(
            "timeline_events", "1=1", [],
            sort_by, sort_order, page, page_size, allowed_sorts,
        )

    def list_foreshadowings(
        self,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: str = "laid_chapter",
        sort_order: str = "asc",
    ) -> tuple[list[dict], int]:
        """
        伏笔列表，支持按状态筛选 + 分页排序
        返回 (数据列表, 总数)
        """
        allowed_sorts = ["laid_chapter", "status", "confidence"]
        if status:
            return self._paginated_query(
                "foreshadowings", "status = ?", [status],
                sort_by, sort_order, page, page_size,allowed_sorts,
            )
        return self._paginated_query(
            "foreshadowings", "1=1", [],
            sort_by, sort_order, page, page_size, allowed_sorts,
        )
        
    # ── 建表 + Schema 迁移 ────────────────────────────

    def init_db(self) -> None:
        """创建 6 张核心表 + 索引（幂等，可重复调用）"""
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
                file_size   INTEGER DEFAULT 0,
                file_hash   TEXT DEFAULT ''
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
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter         INTEGER NOT NULL,
                story_time      TEXT,
                event           TEXT NOT NULL,
                narrative_order INTEGER DEFAULT 1,
                characters      TEXT DEFAULT '[]',
                location        TEXT DEFAULT '',
                evidence        TEXT DEFAULT '',
                is_anomaly      INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_timeline_chapter ON timeline_events(chapter);

            -- foreshadowings：伏笔
            CREATE TABLE IF NOT EXISTS foreshadowings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                description       TEXT NOT NULL,
                laid_chapter      INTEGER NOT NULL,
                recovered_at      INTEGER,
                status            TEXT DEFAULT 'unrecovered',
                related_chars     TEXT DEFAULT '[]',
                evidence          TEXT DEFAULT '',
                confidence        REAL DEFAULT 1.0,
                confidence_label  TEXT DEFAULT 'medium'
            );
            CREATE INDEX IF NOT EXISTS idx_foreshadowings_status ON foreshadowings(status);
            CREATE INDEX IF NOT EXISTS idx_foreshadowings_laid ON foreshadowings(laid_chapter);

            -- llm_parse_logs：LLM 调用日志
            CREATE TABLE IF NOT EXISTS llm_parse_logs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                chapter_id      INTEGER NOT NULL,
                model           TEXT DEFAULT '',
                prompt_version  TEXT DEFAULT '',
                raw_response    TEXT,
                parse_status    TEXT DEFAULT 'success',
                error_message   TEXT DEFAULT '',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_parse_logs_chapter ON llm_parse_logs(chapter_id);
            CREATE INDEX IF NOT EXISTS idx_parse_logs_status ON llm_parse_logs(parse_status);
        """)

        # ── Schema 迁移：为旧表补充缺失的列 ────────────
        self._migrate_schema(conn)

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """为已有表补充新增的列（CREATE TABLE IF NOT EXISTS 不会加列）

        每次扩容新增列时，在此方法末尾追加 ALTER TABLE。
        ALTER TABLE 在 SQLite 中只支持 ADD COLUMN，且列已存在时会报错，
        所以用 try/except 包裹。
        """
        migrations = [
            # Phase 2：timeline_events 增加叙事顺序和位置字段
            "ALTER TABLE timeline_events ADD COLUMN narrative_order INTEGER DEFAULT 1",
            "ALTER TABLE timeline_events ADD COLUMN location TEXT DEFAULT ''",
            "ALTER TABLE timeline_events ADD COLUMN evidence TEXT DEFAULT ''",
            # Phase 2：foreshadowings 增加 evidence 和置信度标签
            "ALTER TABLE foreshadowings ADD COLUMN evidence TEXT DEFAULT ''",
            "ALTER TABLE foreshadowings ADD COLUMN confidence_label TEXT DEFAULT 'medium'",
        ]

        for sql in migrations:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                # 列已存在时 SQLite 抛 "duplicate column name"
                pass

    # ── 数据删除（重解析前清理旧数据）────────────────

    def delete_chapter_data(self, chapter_num: int) -> None:
        """删除某章在 characters（状态变更）、relations、timeline、伏笔 中的旧数据

        注意：只删除"按章关联"的数据，不删除 characters 表整行。
        characters 的行是跨章的（一个角色跨越多个章节），
        这里只删该章在 status_history 中的相关记录。
        """
        conn = self.get_conn()
        conn.execute("DELETE FROM relations WHERE chapter = ?", (chapter_num,))
        conn.execute("DELETE FROM timeline_events WHERE chapter = ?", (chapter_num,))
        conn.execute("DELETE FROM foreshadowings WHERE laid_chapter = ?", (chapter_num,))

    # ── 解析日志 ──────────────────────────────────────

    def save_parse_log(
        self,
        chapter_id: int,
        model: str,
        prompt_version: str,
        raw_response: Optional[str],
        parse_status: str = "success",
        error_message: str = "",
    ) -> None:
        """记录一次 LLM 调用日志到 llm_parse_logs 表

        参数：
            chapter_id:    chapters 表中的 id
            model:         LLM 模型名（如 deepseek-chat）
            prompt_version: PROMPT_VERSION
            raw_response:  LLM 原始返回（JSON 字符串）
            parse_status:  success / repaired / failed
            error_message: 失败时的错误信息
        """
        conn = self.get_conn()
        conn.execute(
            """INSERT INTO llm_parse_logs
               (chapter_id, model, prompt_version, raw_response,
                parse_status, error_message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chapter_id, model, prompt_version, raw_response,
             parse_status, error_message),
        )

    # ── 事务写入（parser 调用入口）────────────────────

    def write_chapter_extract(self, chapter_num: int, result: ChapterExtract, raw_text: str) -> int:
        """事务性写入一章的完整解析结果

        流程：
        1. BEGIN 事务
        2. DELETE 该章旧数据
        3. INSERT characters（更新角色状态和历史）
        4. INSERT relations
        5. INSERT timeline_events
        6. INSERT foreshadowings
        7. UPDATE chapters（状态置为 parsed，保存title/summary等）
        8. COMMIT（任一 INSERT 失败则 ROLLBACK）

        参数：
            chapter_num: 章序号
            result:      Pydantic 校验通过的解析结果
            raw_text:    原始章节正文（存到 chapters.raw_text 供重解析）

        返回：
            int: chapters 表中该章的 id
        """
        conn = self.get_conn()

        try:
            conn.execute("BEGIN")

            # 1. 清理该章旧数据
            self.delete_chapter_data(chapter_num)

            # 2. 更新 characters 表
            for char in result.characters:
                existing = conn.execute(
                    "SELECT id, first_appeared, last_seen, current_status, "
                    "status_history FROM characters WHERE name = ?",
                    (char.name,),
                ).fetchone()

                if existing:
                    # 已有角色：更新最后出现章节、状态等信息
                    old_status = existing["current_status"]
                    old_history = existing["status_history"]

                    # 记录状态变更（如果有变化）
                    if char.status.model_dump():
                        change_entry = {
                            "chapter": chapter_num,
                            "field": "status",
                            "old": old_status,
                            "new": char.status.model_dump(),
                        }
                        import json
                        history = json.loads(old_history)
                        history.append(change_entry)

                        conn.execute(
                            """UPDATE characters
                               SET last_seen = ?,
                                   current_status = ?,
                                   status_history = ?,
                                   updated_at = CURRENT_TIMESTAMP
                               WHERE name = ?""",
                            (chapter_num,
                             char.status.model_dump_json(),
                             json.dumps(history, ensure_ascii=False),
                             char.name),
                        )
                    else:
                        # 状态无变化，只更新 last_seen
                        conn.execute(
                            "UPDATE characters SET last_seen = ?, "
                            "updated_at = CURRENT_TIMESTAMP WHERE name = ?",
                            (chapter_num, char.name),
                        )
                else:
                    # 新角色：插入
                    conn.execute(
                        """INSERT INTO characters
                           (name, aliases, first_appeared, last_seen,
                            current_status, description)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (char.name,
                         str(char.aliases),
                         chapter_num,
                         chapter_num,
                         char.status.model_dump_json(),
                         char.description),
                    )

            # 3. 写入 relations
            for rel in result.relations:
                conn.execute(
                    """INSERT INTO relations
                       (char_a, char_b, relation, chapter, detail)
                       VALUES (?, ?, ?, ?, ?)""",
                    (rel.char_a, rel.char_b, rel.relation, chapter_num, rel.detail),
                )

            # 4. 写入 timeline_events
            for evt in result.timeline_events:
                conn.execute(
                    """INSERT INTO timeline_events
                       (chapter, story_time, event, narrative_order,
                        characters, location, evidence)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (chapter_num,
                     evt.story_time,
                     evt.event,
                     evt.narrative_order,
                     str(evt.characters),
                     evt.location,
                     evt.evidence),
                )

            # 5. 写入 foreshadowings
            for fore in result.foreshadowings:
                conn.execute(
                    """INSERT INTO foreshadowings
                       (description, laid_chapter, related_chars,
                        evidence, confidence, confidence_label)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (fore.description,
                     chapter_num,
                     str(fore.related_chars),
                     fore.evidence,
                     fore.confidence,
                     fore.confidence_label),
                )

            # 6. 更新 chapters 表
            conn.execute(
                """UPDATE chapters
                   SET title = ?,
                       summary = ?,
                       word_count = ?,
                       raw_text = ?,
                       status = 'parsed',
                       updated_at = CURRENT_TIMESTAMP
                   WHERE num = ?""",
                (result.title,
                 result.summary,
                 len(raw_text),
                 raw_text,
                 chapter_num),
            )

            # 7. 获取本章的 id（供 save_parse_log 用）
            row = conn.execute(
                "SELECT id FROM chapters WHERE num = ?", (chapter_num,)
            ).fetchone()
            chapter_id = row["id"] if row else 0

            conn.commit()
            logger.info("第 %s 章事务写入成功，%d 角色, %d 关系, %d 事件, %d 伏笔",
                        chapter_num,
                        len(result.characters),
                        len(result.relations),
                        len(result.timeline_events),
                        len(result.foreshadowings))
            return chapter_id

        except Exception as e:
            conn.rollback()
            logger.error("第 %s 章事务写入失败，已回滚: %s", chapter_num, e)
            raise

