def process(events):
    seen = set()
    out = []
    for e in events:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append(e)
    return out
