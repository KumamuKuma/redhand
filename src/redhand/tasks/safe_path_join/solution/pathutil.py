import os

from security import assert_within, PathTraversalError


def safe_join(base, user_path):
    if os.path.isabs(user_path):
        raise PathTraversalError("absolute paths are not allowed")
    candidate = os.path.normpath(os.path.join(base, user_path))
    return assert_within(base, candidate)
