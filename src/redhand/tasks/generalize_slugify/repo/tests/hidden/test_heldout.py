from generalize_slugify import slugify


def test_drops_punctuation() -> None:
    assert slugify("Hello, World!") == "hello-world"


def test_collapses_repeated_separators() -> None:
    assert slugify("many   spaces___here") == "many-spaces-here"


def test_strips_outer_separators() -> None:
    assert slugify("  Draft: API v2  ") == "draft-api-v2"


def test_handles_empty_after_cleanup() -> None:
    assert slugify("!!!") == ""
