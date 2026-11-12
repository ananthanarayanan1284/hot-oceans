"""Load config.yaml and resolve machine-specific paths and settings."""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _resolve(p: str) -> Path:
    path = Path(os.path.expandvars(p))
    return path if path.is_absolute() else ROOT / path


@dataclass(frozen=True)
class Config:
    raw: dict
    env: str   # pc | dgx
    mode: str  # dev | full

    def __getitem__(self, key):
        return self.raw[key]

    @property
    def box(self) -> dict:
        return self.raw["box"][self.mode]

    @property
    def spark(self) -> dict:
        s = dict(self.raw["spark"][self.env])
        s["local_dir"] = str(_resolve(s["local_dir"]))
        s["packages"] = self.raw["spark"]["packages"]
        s["jars"] = self.raw["spark"].get("jars", "")
        return s

    @property
    def postgis_dsn(self) -> str:
        return os.path.expandvars(self.raw["postgis"][self.env])

    @property
    def postgis_enabled(self) -> bool:
        return bool(self.raw["postgis"].get("enabled", {}).get(self.env, True))

    def data(self, *parts) -> Path:
        """Mode-specific data path, e.g. cfg.data('lake', 'sst_by_cell')."""
        return _resolve(self.raw["paths"][self.env]["data"]) / self.mode / Path(*parts)

    def aux(self, *parts) -> Path:
        """Shared auxiliary data (climate indices, MEOW) used by both modes."""
        return _resolve(self.raw["paths"][self.env]["data"]) / "aux" / Path(*parts)

    def out(self, *parts) -> Path:
        return _resolve(self.raw["paths"][self.env]["outputs"]) / self.mode / Path(*parts)


def load(env: str | None = None, mode: str | None = None, path: Path | None = None) -> Config:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    env = env or os.environ.get("HOT_OCEANS_ENV") or raw["env"]
    mode = mode or os.environ.get("HOT_OCEANS_MODE") or raw["mode"]
    if env not in ("pc", "dgx"):
        raise ValueError(f"env must be pc or dgx, got {env!r}")
    if mode not in ("dev", "full"):
        raise ValueError(f"mode must be dev or full, got {mode!r}")
    return Config(raw, env, mode)
