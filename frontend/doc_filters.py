from __future__ import annotations


def compute_doc_filter_state(*, include_unassigned: bool, only_unassigned: bool) -> tuple[bool, bool]:
    if only_unassigned:
        return True, True
    return bool(include_unassigned), False


def filter_docs(docs: list[dict], *, only_unassigned: bool) -> list[dict]:
    if not only_unassigned:
        return docs
    return [d for d in docs if not (d.get("project_id") or "")]

