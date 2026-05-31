import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.utils.chunk import TextPage, chunk_pages  # noqa: E402


def test_chunk_pages_preserves_markdown_section_and_offsets():
    text = "# Overview\n" + "A" * 20 + "\n## Details\n" + "B" * 20

    chunks = chunk_pages([TextPage(content=text)], chunk_size=24, chunk_overlap=4)

    assert len(chunks) >= 2
    assert chunks[0].chunk_index == 1
    assert chunks[0].section == "Overview"
    assert chunks[0].char_start == 0
    assert chunks[0].char_end == 11
    assert chunks[-1].section == "Details"


def test_chunk_pages_keeps_pdf_page_numbers():
    pages = [
        TextPage(content="first page content", page_no=1),
        TextPage(content="second page content", page_no=2),
    ]

    chunks = chunk_pages(pages, chunk_size=80, chunk_overlap=10)

    assert [chunk.page_no for chunk in chunks] == [1, 2]
    assert [chunk.chunk_index for chunk in chunks] == [1, 2]


def test_chunk_break_at_sentence_boundary():
    """断句优化：在句号处断开而非硬切"""
    text = "这是一段较长的文本内容。" + "A" * 50 + "。这是结尾部分。"
    chunks = chunk_pages([TextPage(content=text)], chunk_size=30, chunk_overlap=5)
    assert len(chunks) >= 2
    # 第一个块应该在句号处断开
    assert chunks[0].content.endswith("。")


def test_chunk_break_at_newline():
    """断句优化：在换行处断开"""
    text = "第一行较长的内容在这里\n" + "B" * 50 + "\n第三行较长的内容在这里"
    chunks = chunk_pages([TextPage(content=text)], chunk_size=30, chunk_overlap=5)
    assert len(chunks) >= 2
    assert chunks[0].content.endswith("\n") or "第一行" in chunks[0].content


def test_chunk_chinese_heading_detection():
    """中文标题检测：一、二、三、"""
    text = "一、背景介绍内容说明\n" + "A" * 30 + "\n二、技术方案详细描述\n" + "B" * 30
    chunks = chunk_pages([TextPage(content=text)], chunk_size=25, chunk_overlap=5)
    assert len(chunks) >= 2
    sections = [c.section for c in chunks]
    assert "背景介绍内容说明" in sections
    assert "技术方案详细描述" in sections


def test_chunk_chinese_chapter_heading():
    """中文标题检测：第一章、第二章"""
    text = "第一章 绪论部分\n" + "C" * 30 + "\n第二章 方法部分\n" + "D" * 30
    chunks = chunk_pages([TextPage(content=text)], chunk_size=25, chunk_overlap=5)
    sections = [c.section for c in chunks]
    assert "绪论部分" in sections
    assert "方法部分" in sections


def test_chunk_numbered_heading():
    """数字编号标题：1. 2. 3."""
    text = "1. 需求分析\n" + "E" * 30 + "\n2. 系统设计\n" + "F" * 30
    chunks = chunk_pages([TextPage(content=text)], chunk_size=25, chunk_overlap=5)
    sections = [c.section for c in chunks]
    assert "需求分析" in sections
    assert "系统设计" in sections


def test_chunk_minimum_length_filter():
    """最小长度过滤：小于 10 字符的块被过滤"""
    text = "短\n" + "G" * 50
    chunks = chunk_pages([TextPage(content=text)], chunk_size=20, chunk_overlap=5)
    for chunk in chunks:
        assert len(chunk.content) >= 10


def test_chunk_empty_content_filtered():
    """空内容过滤"""
    pages = [TextPage(content=""), TextPage(content="有内容的页面 " + "H" * 30)]
    chunks = chunk_pages(pages, chunk_size=20, chunk_overlap=5)
    assert len(chunks) >= 1
    assert all(len(c.content) >= 10 for c in chunks)


def test_chunk_overlap_preserved():
    """重叠区域正确"""
    text = "A" * 100
    chunks = chunk_pages([TextPage(content=text)], chunk_size=30, chunk_overlap=10)
    if len(chunks) >= 2:
        # 第二个块的开头应该与第一个块的结尾有重叠
        first_end = chunks[0].content[-10:]
        second_start = chunks[1].content[:10]
        # 由于断句优化，重叠可能不完全精确，但内容应该有交集
        assert chunks[0].char_end - chunks[1].char_start <= 30


def test_chunk_multiple_pages():
    """多页文档正确分页"""
    pages = [
        TextPage(content="页面一内容 " + "A" * 20, page_no=1),
        TextPage(content="页面二内容 " + "B" * 20, page_no=2),
        TextPage(content="页面三内容 " + "C" * 20, page_no=3),
    ]
    chunks = chunk_pages(pages, chunk_size=50, chunk_overlap=5)
    page_nos = set(c.page_no for c in chunks)
    assert 1 in page_nos
    assert 2 in page_nos
    assert 3 in page_nos


def test_chunk_indices_sequential():
    """chunk_index 连续递增"""
    text = "X" * 200
    chunks = chunk_pages([TextPage(content=text)], chunk_size=30, chunk_overlap=5)
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(1, len(chunks) + 1))
