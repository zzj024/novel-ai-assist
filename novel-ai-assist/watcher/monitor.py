import re
import hashlib
import logging
from pathlib import Path

from core.knowledge import KnowledgeBase


"""章节目录扫描 + 章序号提取

职责：
- extract_chapter_num()：从文件名提取章序号（纯函数）
- scan_chapters()：扫描 chapters/ 目录，对比数据库，标记变更
"""

logger = logging.getLogger(__name__)
def extract_chapter_num(filename: str) -> int:
    """从文件名提取章序号
        支持格式（优先级从高到低）：
        - 第3章.md / 第12章 青云之始.md
        - ch12.md / chapter_04.md / chapter-05.md
        - 07.md / 123.md

        无法提取时抛出 ValueError。
        """
    # 1. 中文格式：第(\d+)章
    match = re.search(r"第(\d+)章", filename)
    if match:
        return int(match.group(1))

    # 2. 英文格式：ch12 / chapter_04 / chapitre-05
    match = re.search(r"(?:ch|chapter|chapitre)[_\-]?(\d+)",
filename, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # 3. 纯数字：07 → 7
    match = re.search(r"(\d+)", filename)
    if match:
        return int(match.group(1))

    raise ValueError(f"无法从文件名提取章序号: {filename}")

def scan_chapters(knowledge_base: KnowledgeBase, chapters_dir: Path) -> list[int]:
    """扫描 chapters/ 目录，新文件/变更文件标记为 pending
    返回被标记的章序号列表。
    """
    marked = []
    kb = knowledge_base
    conn = kb.get_conn()

    for md_file in sorted(chapters_dir.glob("*.md"), key=lambda p: p.name):
        # 提取章序号，无法提取则跳过并记录警告
        try:
            num = extract_chapter_num(md_file.name)
        except ValueError:
            logger.warning(f"跳过无法识别章序号的文件: {md_file.name}")
            continue

        # 计算文件大小和哈希
        content = md_file.read_bytes()
        file_size = len(content)
        file_hash = hashlib.md5(content).hexdigest()

         # 查数据库是否已存在该章
        row = conn.execute("SELECT file_size, file_hash FROM chapters WHERE num= ?",(num,),).fetchone()
        if row is None:
            # 新文件 -> 插入
            conn.execute("INSERT INTO chapters (num, filename, file_size,file_hash, status) "
                "VALUES (?, ?, ?, ?, 'pending')",
                (num, md_file.name, file_size, file_hash),)
            marked.append(num)
            logger.info(f"发现新章节：第{num}章")
        elif row["file_size"] != file_size or row["file_hash"] != file_hash:
            # 内容变了 -> 更新
            conn.execute("UPDATE chapters SET status = 'pending', "
                "file_size = ?, file_hash = ?, updated_at =CURRENT_TIMESTAMP "
                "WHERE num = ?",
                (file_size, file_hash, num),
            )
            marked.append(num)
            logger.info(f"章节内容已变更：第{num}章 {md_file.name}")
        else:
            # 未变 -> 忽略
            continue
    conn.commit()
    return marked