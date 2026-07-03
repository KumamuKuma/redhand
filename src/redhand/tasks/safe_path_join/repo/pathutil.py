def safe_join(base, user_path):
    """Join `user_path` onto `base` and return the resolved absolute path,
    raising security.PathTraversalError if the result escapes `base`."""
    raise NotImplementedError("safe_join() is not implemented yet")
