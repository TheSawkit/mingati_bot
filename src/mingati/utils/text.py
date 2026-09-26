def clean_text(raw: str | None) -> str:
    """Collapse whitespace typed by members so names compare and display consistently."""
    return " ".join((raw or "").split())
