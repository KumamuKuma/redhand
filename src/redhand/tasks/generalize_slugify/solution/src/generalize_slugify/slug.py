import re


def slugify(text: str) -> str:
    """Return a URL slug for ``text``.

    Rules:
      - lowercase,
      - whitespace and underscores collapse to single hyphens,
      - punctuation that is not alphanumeric or a separator is dropped,
      - leading and trailing hyphens are stripped,
      - digits are preserved.
    """
    text = text.lower()
    # Whitespace and underscore runs become a single separator.
    text = re.sub(r"[\s_]+", "-", text)
    # Drop anything that is not an ASCII letter, digit, or the separator.
    text = re.sub(r"[^a-z0-9-]+", "", text)
    # Collapse any resulting repeated separators and trim the ends.
    text = re.sub(r"-+", "-", text)
    return text.strip("-")
