def satisfies(version, range_):
    """Return True if `version` satisfies the npm-style `range_`.

    Supports exact, caret (^), tilde (~), the `*` wildcard and a space-separated
    list of >,>=,<,<=,= comparators. Raise ValueError on a malformed range.
    """
    raise NotImplementedError("satisfies() is not implemented yet")
