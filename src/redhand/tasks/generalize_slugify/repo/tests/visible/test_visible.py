from generalize_slugify import slugify


def test_lowercases_and_replaces_spaces() -> None:
    assert slugify("Hello World") == "hello-world"


def test_preserves_digits() -> None:
    assert slugify("Release 2026") == "release-2026"
