"""Dependency-free Prometheus text-format metrics."""
import threading
from collections import defaultdict

_l = threading.Lock()
counters = defaultdict(float)
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5)
hist = defaultdict(lambda: [0] * (len(BUCKETS) + 1))
hsum = defaultdict(float)


def inc(name, labels="", v=1):
    with _l:
        counters[(name, labels)] += v


def observe(name, seconds, labels=""):
    with _l:
        h = hist[(name, labels)]
        for i, b in enumerate(BUCKETS):
            if seconds <= b:
                h[i] += 1
        h[-1] += 1
        hsum[(name, labels)] += seconds


def render():
    out = []
    with _l:
        for (n, lb), v in sorted(counters.items()):
            out.append(f"{n}{{{lb}}} {v}" if lb else f"{n} {v}")
        for (n, lb), h in sorted(hist.items()):
            pre = (lb + ",") if lb else ""
            for i, b in enumerate(BUCKETS):
                out.append(f'{n}_bucket{{{pre}le="{b}"}} {h[i]}')
            out.append(f'{n}_bucket{{{pre}le="+Inf"}} {h[-1]}')
            out.append(f"{n}_sum{{{lb}}} {hsum[(n, lb)]}")
            out.append(f"{n}_count{{{lb}}} {h[-1]}")
    return "\n".join(out) + "\n"
