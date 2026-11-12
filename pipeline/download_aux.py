"""Download the DMI and ONI climate indices and check that the MEOW shapefile is in place."""
import requests

from hot_oceans import cli


def main():
    cfg, args = cli.parse(__doc__)
    aux = cfg.aux()
    aux.mkdir(parents=True, exist_ok=True)
    for name in ("dmi", "oni"):
        dest = aux / f"{name}.txt"
        if dest.exists() and not args.force:
            print(f"[aux] {dest.name} already present")
            continue
        r = requests.get(cfg["sources"][name], timeout=120)
        r.raise_for_status()
        dest.write_text(r.text, encoding="utf-8")
        print(f"[aux] saved {dest} ({len(r.text.splitlines())} lines)")

    meow = [*cfg.aux("meow").glob("*.shp"), *cfg.aux("meow").glob("*.geojson")] if cfg.aux("meow").exists() else []
    if meow:
        print(f"[aux] MEOW shapefile found: {meow[0].name}")
    else:
        print(f"[aux] MEOW missing. {cfg['sources']['meow']}")


if __name__ == "__main__":
    main()
