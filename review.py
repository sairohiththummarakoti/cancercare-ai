"""Session-level review actions; no signatures, orders, or database writes."""
from copy import deepcopy

PENDING = "AI-Generated Draft — Pending Oncologist Review"
APPROVED = "Approved for documentation in this session"
REJECTED = "Rejected in this session"


def set_review(result, action, notes=""):
    if action not in {"approve", "reject", "edit"}:
        raise ValueError("Unknown review action.")
    updated = deepcopy(result)
    updated["review_status"] = {"approve": APPROVED, "reject": REJECTED, "edit": PENDING}[action]
    updated["review_notes"] = notes.strip()
    if action == "edit":
        updated["clinician_edit"] = notes.strip()
    return updated


def export_result(result):
    """The browser download is explicit; nothing is written by this function."""
    return {
        "application": "Oncology Care AI",
        "notice": "Research demonstration only. Not validated for clinical use. Final treatment decisions require qualified oncology professionals.",
        "mode": result["mode"],
        "filename": result["filename"],
        "elapsed_seconds": result["elapsed"],
        "findings": result["findings"].model_dump(),
        "assessment": result["assessment"].model_dump(),
        "evidence": result["chunks"],
        "review_status": result["review_status"],
        "review_notes": result.get("review_notes", ""),
        "clinician_edit": result.get("clinician_edit", ""),
        "review_scope": "Session-level documentation review only; not a signed oncology plan or treatment order.",
    }
