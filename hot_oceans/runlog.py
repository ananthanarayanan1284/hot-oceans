"""Append row counts, runtimes and output sizes to outputs/<mode>/tables/run_log.csv (big-data evidence)."""
import csv
import datetime as dt
import time
from contextlib import contextmanager
from pathlib import Path

FIELDS = ["timestamp", "env", "mode", "stage", "step", "rows", "seconds", "output_mb", "partitions", "note"]


def dir_size_mb(path) -> float | None:
    if path is None:
        return None
    p = Path(path)
    if p.is_file():
        return round(p.stat().st_size / 1e6, 1)
    if p.is_dir():
        return round(sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6, 1)
    return None


def log(cfg, stage, step, rows=None, seconds=None, output=None, partitions=None, note=""):
    f = cfg.out("tables", "run_log.csv")
    f.parent.mkdir(parents=True, exist_ok=True)
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
            "env": cfg.env, "mode": cfg.mode, "stage": stage, "step": step,
            "rows": rows, "seconds": seconds, "output_mb": dir_size_mb(output),
            "partitions": partitions, "note": note,
        })
    print(f"[run_log] {stage}/{step}: rows={rows} seconds={seconds} output={output}")


@contextmanager
def timed(cfg, stage, step, output=None):
    """with timed(cfg, 'A', 'ingest_year', out) as rec: ...; rec['rows'] = n"""
    rec = {"rows": None, "partitions": None, "note": ""}
    t0 = time.time()
    yield rec
    log(cfg, stage, step, rec["rows"], round(time.time() - t0, 1), output, rec["partitions"], rec["note"])
