import semver


def test_caret_match():
    assert semver.satisfies("1.2.5", "^1.2.0") is True


def test_caret_no_match():
    assert semver.satisfies("2.0.0", "^1.2.0") is False


def test_exact():
    assert semver.satisfies("1.0.0", "1.0.0") is True
