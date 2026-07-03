def split_evenly(total, n):
    if n <= 0:
        raise ValueError("n must be positive")
    base, rem = divmod(total, n)
    return [base + (1 if i < rem else 0) for i in range(n)]


def allocate(total, weights):
    if not weights:
        raise ValueError("weights must be non-empty")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be non-negative")
    s = sum(weights)
    if s == 0:
        raise ValueError("total weight must be positive")
    floors = [total * w // s for w in weights]
    remainder = total - sum(floors)
    order = sorted(range(len(weights)), key=lambda i: (-((total * weights[i]) % s), i))
    for k in range(remainder):
        floors[order[k]] += 1
    return floors
