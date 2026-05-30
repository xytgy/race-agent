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
    assert chunks[0].char_end == 24
    assert chunks[-1].section == "Details"


def test_chunk_pages_keeps_pdf_page_numbers():
    pages = [
        TextPage(content="first page content", page_no=1),
        TextPage(content="second page content", page_no=2),
    ]

    chunks = chunk_pages(pages, chunk_size=80, chunk_overlap=10)

    assert [chunk.page_no for chunk in chunks] == [1, 2]
    assert [chunk.chunk_index for chunk in chunks] == [1, 2]
