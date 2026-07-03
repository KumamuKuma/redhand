import heapq


def topo_sort(nodes, edges):
    indeg = {n: 0 for n in nodes}
    adj = {n: [] for n in nodes}
    for a, b in edges:
        if a not in indeg or b not in indeg:
            raise ValueError("edge references unknown node")
        adj[a].append(b)
        indeg[b] += 1
    heap = [n for n in nodes if indeg[n] == 0]
    heapq.heapify(heap)
    out = []
    while heap:
        n = heapq.heappop(heap)
        out.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                heapq.heappush(heap, m)
    if len(out) != len(nodes):
        raise ValueError("cycle detected")
    return out
