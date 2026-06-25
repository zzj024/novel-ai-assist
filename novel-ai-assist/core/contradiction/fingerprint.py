
"""稳定 fingerprint 生成

基于结构化字段生成，不依赖自然语言描述。
内容不变 fingerprint 不变，支持稳定 dismiss。
"""

import hashlib


def make_fingerprint(
    rule_name: str,
    contradiction_type: str,
    chapter_start: int,
    chapter_end: int,
    related_chars: list[str],
    detail_key: str,
) -> str:
    """生成稳定的检测结果 fingerprint

    参数：
        rule_name:         规则名称
        contradiction_type: 矛盾类型
        chapter_start:     起始章节
        chapter_end:       结束章节
        related_chars:     相关角色（排序后参与 hash）
        detail_key:        细节关键字段（如 "筑基→元婴"）

    返回：
        64 字符的十六进制 SHA256 指纹
    """
    raw = "|".join([
        rule_name,
        contradiction_type,
        str(chapter_start),
        str(chapter_end),
        ",".join(sorted(set(related_chars))),
        detail_key,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()