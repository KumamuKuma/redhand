def resolve(document, pointer):
    """Resolve an RFC 6901 JSON Pointer against a decoded JSON document.

    Return the referenced value. Raise KeyError / IndexError for missing
    locations and ValueError for a malformed pointer.
    """
    raise NotImplementedError("resolve() is not implemented yet")
