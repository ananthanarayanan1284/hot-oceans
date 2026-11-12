"""Climate indices (DMI, ONI), phases, and simple basin sectors."""
import numpy as np
import pandas as pd

ONI_SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                     "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}


def read_dmi(path) -> pd.DataFrame:
    """NOAA PSL format: header line, then 'year v1 ... v12' rows; -9999 marks missing."""
    rows = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        tok = line.split()
        if len(tok) == 13 and tok[0].isdigit():
            year = int(tok[0])
            for m, v in enumerate(tok[1:], start=1):
                val = float(v)
                if val > -99:
                    rows.append((year, m, val))
    return pd.DataFrame(rows, columns=["year", "month", "dmi"])


def read_oni(path) -> pd.DataFrame:
    """NOAA CPC oni.ascii.txt: SEAS YR TOTAL ANOM; each 3-month season is assigned to its centre month."""
    df = pd.read_csv(path, sep=r"\s+")
    df["month"] = df["SEAS"].map(ONI_SEASON_CENTER)
    df["year"] = df["YR"]
    # NDJ centred on December belongs to the YR shown; DJF centred on January too.
    return df[["year", "month"]].assign(oni=df["ANOM"].astype(float))


def climate_monthly(dmi_path, oni_path, iod_thr=0.4, enso_thr=0.5) -> pd.DataFrame:
    df = read_dmi(dmi_path).merge(read_oni(oni_path), on=["year", "month"], how="outer")
    df["iod_phase"] = np.select([df.dmi >= iod_thr, df.dmi <= -iod_thr], ["IOD+", "IOD-"], "IOD0")
    df["enso_phase"] = np.select([df.oni >= enso_thr, df.oni <= -enso_thr], ["ElNino", "LaNina"], "ENSO0")
    return df.sort_values(["year", "month"]).reset_index(drop=True)


def sector(lat, lon) -> str:
    """Coarse basin sector used as an FP-Growth item and a dashboard filter."""
    if lat > 5:
        return "Arabian Sea" if lon < 78 else ("Bay of Bengal" if lon < 100 else "Andaman/SCS edge")
    if lat >= -5:
        return "Equatorial"
    return "South-west" if lon < 80 else "South-east"


def season(month: int) -> str:
    return {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM",
            6: "JJA", 7: "JJA", 8: "JJA"}.get(month, "SON")
