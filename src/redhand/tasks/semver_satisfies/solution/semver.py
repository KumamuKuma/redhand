import re

_VER = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_CMP = re.compile(r"(>=|<=|>|<|=)?(\d+\.\d+\.\d+)$")


def _parse(v):
    m = re.fullmatch(r"\d+\.\d+\.\d+", v.strip())
    if not m:
        raise ValueError(f"bad version: {v!r}")
    a, b, c = v.strip().split(".")
    return (int(a), int(b), int(c))


def satisfies(version, range_):
    v = _parse(version)
    r = range_.strip()
    if r in ("*", "x", "X"):
        return True
    if r.startswith("^"):
        a, b, c = _parse(r[1:])
        lo = (a, b, c)
        if a > 0:
            hi = (a + 1, 0, 0)
        elif b > 0:
            hi = (a, b + 1, 0)
        else:
            hi = (a, b, c + 1)
        return lo <= v < hi
    if r.startswith("~"):
        a, b, c = _parse(r[1:])
        return (a, b, c) <= v < (a, b + 1, 0)
    ok = True
    matched = False
    for tok in r.split():
        m = _CMP.fullmatch(tok)
        if not m:
            raise ValueError(f"bad comparator: {tok!r}")
        matched = True
        op = m.group(1) or "="
        w = _parse(m.group(2))
        if op == "=":
            ok = ok and v == w
        elif op == ">":
            ok = ok and v > w
        elif op == ">=":
            ok = ok and v >= w
        elif op == "<":
            ok = ok and v < w
        elif op == "<=":
            ok = ok and v <= w
    if not matched:
        raise ValueError(f"empty range: {range_!r}")
    return ok
