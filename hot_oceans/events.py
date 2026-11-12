"""Daily hot-cell clustering and day-to-day event linking."""
import numpy as np
from scipy import ndimage


def cluster_day(rows, cols, eps=1.5, min_samples=4) -> np.ndarray:
    """DBSCAN on grid indices (eps measured in cells), implemented directly on the grid.

    A cell is a core point when at least `min_samples` hot cells (itself included) lie within `eps`.
    Core points within `eps` of each other form one cluster; non-core hot cells within `eps` of a core
    point join that cluster (border points); the rest are noise (-1). With 1 <= eps < 2 the eps-ball on
    an integer grid is exactly the 8 surrounding cells, so connected components of the core cells give
    the DBSCAN clusters. Used instead of scikit-learn, whose thread probing crashes on some Windows setups.
    """
    rows, cols = np.asarray(rows, dtype=np.int64), np.asarray(cols, dtype=np.int64)
    if len(rows) == 0:
        return np.array([], dtype=np.int32)
    if not 1 <= eps < 2:
        raise ValueError("grid DBSCAN supports 1 <= eps < 2 (the 8-neighbourhood)")
    r, c = rows - rows.min() + 1, cols - cols.min() + 1          # 1-cell pad on every side
    hot = np.zeros((r.max() + 2, c.max() + 2), dtype=bool)
    hot[r, c] = True
    ring = np.ones((3, 3), dtype=bool)
    counts = ndimage.convolve(hot.astype(np.int32), ring.astype(np.int32), mode="constant")
    core = hot & (counts >= min_samples)
    lab, _ = ndimage.label(core, structure=ring)
    # Border points take the smallest neighbouring core label (deterministic).
    big = np.iinfo(np.int32).max
    cand = np.where(lab > 0, lab, big)
    neigh_min = ndimage.minimum_filter(cand, footprint=ring, mode="constant", cval=big)
    out = np.where(core, lab, np.where(hot & (neigh_min < big), neigh_min, 0))
    labels = out[r, c].astype(np.int32) - 1                      # clusters 0..n-1, noise -1
    return labels


class UnionFind:
    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def link(nodes, edges) -> dict:
    """nodes: iterable of hashable footprint keys; edges: pairs that intersect on consecutive days.
    Returns {node: event_index} with indices 0..n-1."""
    uf = UnionFind()
    for n in nodes:
        uf.find(n)
    for a, b in edges:
        uf.union(a, b)
    roots: dict = {}
    return {n: roots.setdefault(uf.find(n), len(roots)) for n in nodes}
