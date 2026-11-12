"""Draw the "Tracking event" picture (like fig10) for any event, using the full-run results on the PC.

  python report/plot_event.py --list                   # show good candidate events (moving, 15–120 days)
  python report/plot_event.py --list --year 2023       # candidates that start in 2023
  python report/plot_event.py E-2022-199 E-2016-123    # draw these events
  python report/plot_event.py --top 10                 # draw the 10 events that move the farthest

Pictures go to report/figures/events/<event_id>.png"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_figures as mf  # noqa: E402  (palette, base_map, save; does not draw anything on import)

gpd, np, pd, plt, wkt = mf.gpd, mf.np, mf.pd, mf.plt, mf.wkt
(mf.OUT / "events").mkdir(parents=True, exist_ok=True)


def movement(r):
    """(total displacement in degrees, largest single-day jump) of the centroid track."""
    if not r.track_wkt:
        return 0.0, 99.0
    tr = np.array(wkt.loads(r.track_wkt).coords)
    if len(tr) < 2:
        return 0.0, 0.0
    return float(np.hypot(*(tr[-1] - tr[0]))), float(np.hypot(*np.diff(tr, axis=0).T).max())


def candidates(ev, year=None, min_days=15, max_days=120):
    c = ev[ev.duration_days.between(min_days, max_days)].copy()
    if year:
        c = c[pd.to_datetime(c.start).dt.year == year]
    mv = c.apply(movement, axis=1, result_type="expand")
    c["moved_deg"], c["max_jump_deg"] = mv[0], mv[1]
    c = c[c.max_jump_deg < 1.5]                      # smooth tracks only (no sudden jumps from merging)
    return c.sort_values("moved_deg", ascending=False)


def draw(row, fp, groups):
    g = groups
    hit = g[(g.start == pd.Timestamp(row.start)) & (g.end == pd.Timestamp(row.end)) & (g.n == row.duration_days)]
    if hit.empty:
        print("  no footprints found for", row.event_id); return
    days = fp[fp.event == hit.index[0]].sort_values("date")
    day_no = (days.date - days.date.min()).dt.days.to_numpy()
    x0, y0, x1, y1 = days.total_bounds
    ext = [max(30, x0 - 3), min(120, x1 + 3), max(-30, y0 - 3), min(30, y1 + 3)]
    fig, ax = plt.subplots(figsize=(mf.W, 4.0))
    fig.subplots_adjust(left=0.09, right=0.88, top=0.92, bottom=0.09)
    mf.base_map(ax, extent=ext, ticks=5)
    ramp = mf.ListedColormap(["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"])
    norm = plt.Normalize(0, max(day_no.max(), 1))
    step = max(1, int(np.ceil(len(days) / 15)))      # at most ~15 outlines so the map stays readable
    for (_, d), k in zip(days.iterrows(), day_no):
        if k % step == 0 or k == day_no.max():
            gpd.GeoSeries([d.geometry]).boundary.plot(ax=ax, color=ramp(norm(k)), linewidth=0.9, zorder=2)
    tr = np.array(wkt.loads(row.track_wkt).coords)
    ax.plot(tr[:, 0], tr[:, 1], color=mf.ORANGE, lw=1.6, zorder=5)
    ax.plot(*tr[0], marker="o", ms=7, color=mf.ORANGE, mec="white", zorder=6)
    ax.plot(*tr[-1], marker="s", ms=7, color=mf.INK, mec="white", zorder=6)
    cax = fig.add_axes([0.9, 0.15, 0.022, 0.7])
    cb = fig.colorbar(plt.cm.ScalarMappable(cmap=ramp, norm=norm), cax=cax)
    cb.set_label("Day of the event", fontsize=7.5, color=mf.INK2)
    cb.ax.tick_params(labelsize=6.8); cb.outline.set_edgecolor(mf.AXIS)
    s, e = pd.Timestamp(row.start), pd.Timestamp(row.end)
    ax.legend(handles=[plt.Line2D([], [], color="#3987e5", lw=1, label=f"Daily footprint (every {step}{'st' if step == 1 else 'th' if step > 3 else 'nd' if step == 2 else 'rd'} day)"),
                       plt.Line2D([], [], color=mf.ORANGE, lw=1.6, label="Centroid track"),
                       plt.Line2D([], [], color=mf.ORANGE, marker="o", lw=0, label=f"Start {s:%d %b %Y}"),
                       plt.Line2D([], [], color=mf.INK, marker="s", lw=0, label=f"End {e:%d %b %Y}")],
              loc="best", fontsize=7, frameon=True, framealpha=0.92, edgecolor="none")
    ax.set_title(f"Tracking event {row.event_id}: {int(row.duration_days)} days, peak "
                 f"{row.peak_area_km2 / 1e3:,.0f} thousand km², moved {movement(row)[0]:.1f}°", fontsize=8.6)
    mf.save(fig, f"events/{row.event_id}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("events", nargs="*", help="event ids, e.g. E-2022-199")
    ap.add_argument("--list", action="store_true", help="print candidate events")
    ap.add_argument("--top", type=int, default=0, help="draw the N farthest-moving candidates")
    ap.add_argument("--year", type=int, help="only events starting in this year")
    a = ap.parse_args()

    ev = gpd.read_file(mf.FULL / "dashboard" / "events.geojson")
    if a.list or a.top:
        c = candidates(ev, a.year)
        if a.list:
            cols = ["event_id", "start", "duration_days", "peak_area_km2", "max_category", "moved_deg"]
            print(c[cols].head(30).to_string(index=False, float_format="%.1f"))
        rows = list(c.head(a.top).itertuples()) if a.top else []
    else:
        rows = []
    for eid in a.events:
        m = ev[ev.event_id == eid]
        if m.empty:
            print("unknown event:", eid)
        else:
            rows.append(next(m.itertuples()))
    if not rows:
        return
    fp = gpd.read_parquet(mf.FULL / "postgis" / "mhw_footprints.parquet")
    fp["date"] = pd.to_datetime(fp.date)
    groups = fp.groupby("event").agg(start=("date", "min"), end=("date", "max"), n=("date", "nunique"))
    for r in rows:
        draw(r, fp, groups)


if __name__ == "__main__":
    main()
