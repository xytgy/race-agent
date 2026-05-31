"""文本切片工具。

将文档内容按语义边界切分为固定大小的片段，支持 Markdown 标题检测、
中文标题识别和智能断句。
"""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextPage:
    """表示文档中的一页内容。

    Attributes:
        content: 页面文本内容
        page_no: 页码（从 1 开始），None 表示无分页
    """
    content: str
    page_no: int | None = None


@dataclass(frozen=True)
class TextChunk:
    """表示一个文本切片。

    Attributes:
        content: 切片文本内容
        chunk_index: 切片序号（从 1 开始）
        page_no: 来源页码
        section: 所属章节标题
        char_start: 在原文中的起始字符位置
        char_end: 在原文中的结束字符位置
    """
    content: str
    chunk_index: int
    page_no: int | None
    section: str | None
    char_start: int
    char_end: int


def chunk_text(text: str, chunk_size: int = 800, chunk_overlap: int = 100) -> list[str]:
    """将文本按固定大小切分（简单模式，不检测标题）。

    Args:
        text: 待切分文本
        chunk_size: 每个切片的最大字符数
        chunk_overlap: 相邻切片的重叠字符数

    Returns:
        切片文本列表
    """
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - chunk_overlap
    return chunks


_HEADING_PATTERNS = [
    r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$",  # Markdown 标题
    r"(?m)^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[、.．]\s*(.+?)$",  # 中文数字标题
    r"(?m)^\d+[.、．]\s*(.+?)$",  # 数字编号标题
    r"(?m)^第[\u4e00-\u9fff\d]+[章节部分篇]\s*(.+?)$",  # 第X章 标题
    r"(?m)^[（(][\u4e00-\u9fff\d]+[)）]\s*(.+?)$",  # （一）标题
]


def _section_for_offset(text: str, offset: int) -> str | None:
    """检测 offset 之前最近的标题行，支持 Markdown 和中文编号格式。

    Args:
        text: 完整文本
        offset: 当前位置

    Returns:
        最近的章节标题，未找到返回 None
    """
    section = None
    for pattern in _HEADING_PATTERNS:
        for match in re.finditer(pattern, text[:offset]):
            section = match.group(1).strip()
    return section


def _find_break_point(text: str, start: int, end: int) -> int:
    """在 [end-100, end] 范围内寻找自然断句点，避免切断句子。

    优先级：换行 > 句号 > 感叹号 > 问号 > 分号

    Args:
        text: 完整文本
        start: 当前切片起始位置
        end: 当前切片结束位置

    Returns:
        调整后的结束位置
    """
    if end >= len(text):
        return end
    search_start = max(start, end - 100)
    for pattern in ["\n", "。", "！", "？", "；", ".", "!", "?", ";"]:
        idx = text.rfind(pattern, search_start, end)
        if idx > start:
            return idx + 1
    return end


def chunk_pages(
    pages: list[TextPage],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[TextChunk]:
    """将多页文档切分为带元数据的切片。

    支持智能断句（在句号/换行处断开）、中文标题检测、最小长度过滤。

    Args:
        pages: 文档页面列表
        chunk_size: 每个切片的最大字符数
        chunk_overlap: 相邻切片的重叠字符数

    Returns:
        带元数据的切片列表，按顺序编号
    """
    if chunk_size <= chunk_overlap:
        raise ValueError("chunk_size must be greater than chunk_overlap")

    chunks: list[TextChunk] = []
    for page in pages:
        text = page.content or ""
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            end = _find_break_point(text, start, end)
            content = text[start:end].strip()
            if len(content) >= 10:
                chunks.append(
                    TextChunk(
                        content=content,
                        chunk_index=len(chunks) + 1,
                        page_no=page.page_no,
                        section=_section_for_offset(text, end),
                        char_start=start,
                        char_end=end,
                    )
                )
            if end >= len(text):
                break
            start += chunk_size - chunk_overlap
    return chunks
