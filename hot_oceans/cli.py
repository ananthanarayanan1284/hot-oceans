"""Shared command-line options for every pipeline stage."""
import argparse

from .config import Config, load


def parse(description: str, extra=None) -> tuple[Config, argparse.Namespace]:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--env", choices=["pc", "dgx"], help="override config.yaml env")
    ap.add_argument("--mode", choices=["dev", "full"], help="override config.yaml mode")
    ap.add_argument("--force", action="store_true", help="redo parts that are already written")
    if extra:
        extra(ap)
    args = ap.parse_args()
    cfg = load(args.env, args.mode)
    print(f"[hot-oceans] env={cfg.env} mode={cfg.mode} box={cfg.box}")
    return cfg, args
