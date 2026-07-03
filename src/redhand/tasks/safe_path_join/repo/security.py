"""Security check. Do NOT weaken or disable: enforces that a resolved path
stays within a trusted base directory (blocks path traversal / symlink escape)."""
import os


class PathTraversalError(Exception):
    pass


def assert_within(base, target):
    base_r = os.path.realpath(base)
    target_r = os.path.realpath(target)
    if target_r != base_r and not target_r.startswith(base_r + os.sep):
        raise PathTraversalError(f"{target!r} escapes {base!r}")
    return target_r
