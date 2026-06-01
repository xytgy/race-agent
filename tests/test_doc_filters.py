from pathlib import Path
import sys


def _import_frontend_doc_filters():
    root = Path(__file__).resolve().parents[1]
    frontend_dir = root / "frontend"
    sys.path.insert(0, str(frontend_dir))
    try:
        import doc_filters  # type: ignore
        return doc_filters
    finally:
        sys.path.pop(0)


def test_compute_doc_filter_state_only_unassigned_forces_include_unassigned():
    doc_filters = _import_frontend_doc_filters()
    include_unassigned, only_unassigned = doc_filters.compute_doc_filter_state(
        include_unassigned=False, only_unassigned=True
    )
    assert include_unassigned is True
    assert only_unassigned is True


def test_filter_docs_only_unassigned():
    doc_filters = _import_frontend_doc_filters()
    docs = [
        {"id": "a", "project_id": "conv_x"},
        {"id": "b", "project_id": ""},
        {"id": "c"},
    ]
    filtered = doc_filters.filter_docs(docs, only_unassigned=True)
    assert [d["id"] for d in filtered] == ["b", "c"]

