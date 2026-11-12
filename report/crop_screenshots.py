"""Trim the Streamlit header bar and empty margins from the dashboard screenshots and add a thin border."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

d = Path(__file__).resolve().parent / "figures"
for n in ("fig14_dashboard_map.png", "fig14_dashboard_events.png", "fig14_dashboard_case.png"):
    im = Image.open(d / n).convert("RGB")
    a = np.asarray(im)
    rows = np.where((a < 245).any(axis=(1, 2)))[0]
    top, bottom = 110, min(a.shape[0], rows.max() + 30)   # drop the "Deploy" bar and trailing white space
    im = ImageOps.expand(im.crop((60, top, a.shape[1] - 40, bottom)), border=3, fill=(90, 90, 90))
    im.save(d / n.replace("fig14_", "fig14c_"))
    print(n, im.size)
