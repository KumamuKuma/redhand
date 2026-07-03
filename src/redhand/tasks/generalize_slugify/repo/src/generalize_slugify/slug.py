def slugify(text: str) -> str:
    """Return a URL slug for text."""
    return text.lower().replace(" ", "-")
