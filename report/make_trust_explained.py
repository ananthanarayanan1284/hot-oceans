"""One teaching picture per number in the dashboard's "Can the warning be trusted?" panel.
Run:  python report/make_trust_explained.py  ->  report/figures/trust_explained/01_…08_*.png
Data: outputs/full/tables (trust_checks.json, trust_by_year.csv, trust_by_region.csv, trust_lead_times.csv,
model_metrics.json) and outputs/full/dashboard/cells.parquet."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_figures as mf  # noqa: E402  (palette, base_map, frame; draws nothing on import)

np, pd, plt = mf.np, mf.pd, mf.plt
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402

T = mf.FULL / "tables"
OUT = mf.OUT / "trust_explained"
OUT.mkdir(parents=True, exist_ok=True)
MODEL, RULE, LOSE = mf.BLUE, "#9a988f", mf.ORANGE
INK, INK2, MUTED, GRIDC = mf.INK, mf.INK2, mf.MUTED, mf.GRIDC

trust = json.loads((T / "trust_checks.json").read_text())
metrics = json.loads((T / "model_metrics.json").read_text())
by_year = pd.read_csv(T / "trust_by_year.csv")
by_region = pd.read_csv(T / "trust_by_region.csv")
leads = pd.read_csv(T / "trust_lead_times.csv")
best = metrics["best_model"]
MODEL_AP, RULE_AP = trust["bootstrap"]["model_pr_auc"], trust["bootstrap"]["rule_pr_auc"]


def page(number, value, question, takeaway, height=4.4, ax_rect=(0.1, 0.24, 0.86, 0.56)):
    """Figure with a headline (the dashboard number), the question it answers, a chart area and a takeaway box."""
    fig = plt.figure(figsize=(mf.W, height))
    top = lambda inch: 1 - inch / height   # noqa: E731  header placed in inches from the top, any figure height
    fig.text(0.035, top(0.22), number, fontsize=8, color=MUTED, fontweight="bold", va="top")
    fig.text(0.035, top(0.42), value, fontsize=13, color=INK, fontweight="bold", va="top")
    fig.text(0.035, top(0.73), question, fontsize=8, color=INK2, va="top", style="italic")
    ax = fig.add_axes(ax_rect)
    box_h = 0.12 * 4.4 / height
    fig.patches.append(FancyBboxPatch((0.03, 0.025), 0.94, box_h, boxstyle="round,pad=0.004,rounding_size=0.01",
                                      transform=fig.transFigure, fc="#eef4fc", ec="none"))
    fig.text(0.05, 0.025 + box_h / 2, takeaway, fontsize=7.6, color=INK, va="center", linespacing=1.35)
    return fig, ax


def tidy(ax, grid_axis="x"):
    ax.grid(axis=grid_axis, color=GRIDC, lw=0.6); ax.set_axisbelow(True)


def legend_mr(ax, loc="lower right"):
    ax.legend(handles=[plt.Line2D([], [], marker="o", lw=0, color=MODEL, ms=6, label=f"Model ({best.upper()})"),
                       plt.Line2D([], [], marker="o", lw=0, color=RULE, ms=6, label="Rule (today's heat only)")],
              loc=loc, fontsize=7, frameon=True, framealpha=0.95, edgecolor="none")


# ------------------------------------------------------------------ 1. test years
def fig1():
    d = by_year.sort_values("year")
    fig, ax = page("1 · TEST YEARS MODEL WINS", f"{trust['years_model_better']} years",
                   "Question: in each year the model never saw (2019–2025), was it better than the simple rule?",
                   "Each row is one year. Blue dot (model) is to the right of the grey dot (rule) in every year → the model won\n"
                   "7 out of 7, including the record-hot 2024. Score = PR-AUC: how well real heatwave days are ranked first (higher = better).")
    y = np.arange(len(d))[::-1]
    for yi, (_, r) in zip(y, d.iterrows()):
        ax.plot([r.rule_pr_auc, r.model_pr_auc], [yi, yi], color=GRIDC, lw=3, zorder=1)
        ax.plot(r.rule_pr_auc, yi, "o", color=RULE, ms=7, zorder=2)
        ax.plot(r.model_pr_auc, yi, "o", color=MODEL, ms=7, zorder=3)
        ax.text(r.model_pr_auc + 0.004, yi, f"+{r.model_pr_auc - r.rule_pr_auc:.3f}", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y); ax.set_yticklabels(d.year.astype(str))
    ax.set_xlabel("PR-AUC score on that year (higher = better warnings)")
    ax.set_xlim(0.49, 0.72); tidy(ax); legend_mr(ax)
    mf.save(fig, "trust_explained/01_test_years.png")


# ------------------------------------------------------------------ 2. regions
def fig2():
    d = by_region.assign(gain=by_region.model_pr_auc - by_region.rule_pr_auc).sort_values("gain")
    fig, ax = page("2 · REGIONS MODEL WINS", f"{trust['regions_model_better']} regions",
                   "Question: is the model better everywhere, or only in some parts of the ocean? (51 marine ecoregions)",
                   "Each bar is one ecoregion: how much higher the model's score is than the rule's. Blue = model better (49),\n"
                   "orange = rule better (2, both tiny). So the gain is not from one lucky area: it holds almost everywhere.",
                   height=8.2, ax_rect=(0.36, 0.15, 0.6, 0.72))
    colors = [MODEL if g > 0 else LOSE for g in d.gain]
    ax.barh(np.arange(len(d)), d.gain, color=colors, height=0.72)
    ax.set_yticks(np.arange(len(d))); ax.set_yticklabels(d.region, fontsize=5.6)
    ax.axvline(0, color=INK2, lw=0.8)
    for i, (_, r) in enumerate(d.iterrows()):
        if r.gain <= 0:
            ax.text(0.001, i, f"{r.gain:+.3f}  (rule better)", ha="left", va="center", fontsize=6, color=LOSE, fontweight="bold")
    ax.set_xlabel("Model score − rule score (PR-AUC)")
    ax.set_ylim(-0.8, len(d) - 0.2); tidy(ax)
    mf.save(fig, "trust_explained/02_regions.png")


# ------------------------------------------------------------------ 3. bootstrap CI
def fig3():
    b = trust["bootstrap"]
    lo, hi = b["difference_ci95"]
    fig, ax = page("3 · GAIN OVER RULE (95% CI)", f"+{lo:.3f} to +{hi:.3f}",
                   f"Question: could the model's win be luck? Re-draw the test data {b['replicates']:,} times and see how much the gain moves.",
                   f"Bootstrap: cut the test period into {b['blocks']} blocks, draw blocks at random (with repeats) {b['replicates']:,} times, score both\n"
                   f"each time. The gain stayed between +{lo:.3f} and +{hi:.3f} in 95% of draws and never fell to 0 → the win is real, not luck.",
                   ax_rect=(0.1, 0.25, 0.86, 0.5))
    ax.axis("off"); ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    # top: the two scores with their own ranges
    sx = lambda v: 0.08 + (v - 0.57) / (0.65 - 0.57) * 0.55   # noqa: E731  score axis (left part)
    for yy, name, est, (a, z), col in ((0.78, "Model", b["model_pr_auc"], b["model_ci95"], MODEL),
                                       (0.58, "Rule", b["rule_pr_auc"], b["rule_ci95"], RULE)):
        ax.plot([sx(a), sx(z)], [yy, yy], color=col, lw=5, solid_capstyle="round", alpha=0.45)
        ax.plot(sx(est), yy, "o", color=col, ms=8)
        ax.text(0.07, yy, name, ha="right", va="center", fontsize=7.5, color=INK, fontweight="bold")
        ax.text(sx(z) + 0.01, yy, f"{est:.3f}  ({a:.3f}–{z:.3f})", va="center", fontsize=7, color=INK2)
    for v in (0.58, 0.60, 0.62, 0.64):
        ax.text(sx(v), 0.45, f"{v:.2f}", ha="center", fontsize=6.5, color=MUTED)
        ax.plot([sx(v)] * 2, [0.5, 0.88], color=GRIDC, lw=0.6, zorder=0)
    ax.text(0.08, 0.95, "Score of each (dot) and its 95% range over the re-draws (bar)", fontsize=7.2, color=INK2)
    # bottom: the difference axis with zero
    dx = lambda v: 0.08 + (v + 0.01) / 0.05 * 0.86   # noqa: E731  difference axis −0.01 … +0.04
    ax.plot([dx(-0.01), dx(0.04)], [0.18, 0.18], color=INK2, lw=0.8)
    for v in (-0.01, 0, 0.01, 0.02, 0.03, 0.04):
        ax.plot([dx(v)] * 2, [0.16, 0.2], color=INK2, lw=0.8)
        ax.text(dx(v), 0.07, f"{v:+.2f}" if v else "0", ha="center", fontsize=6.5, color=MUTED)
    ax.axvspan(dx(-0.01), dx(0), ymin=0.13, ymax=0.32, color="#fbe3d9", lw=0)
    ax.text((dx(-0.01) + dx(0)) / 2, 0.255, "rule better", ha="center", fontsize=6.3, color=LOSE)
    ax.plot([dx(lo), dx(hi)], [0.18, 0.18], color=MODEL, lw=7, solid_capstyle="round")
    ax.text((dx(lo) + dx(hi)) / 2, 0.27, f"gain +{lo:.3f} … +{hi:.3f}", ha="center", fontsize=7.2, color=MODEL,
            fontweight="bold")
    ax.text(0.08, 0.36, "Model − rule, 95% range of the gain (if the bar touched 0, the win could be chance)",
            fontsize=7.2, color=INK2)
    mf.save(fig, "trust_explained/03_gain_ci.png")


# ------------------------------------------------------------------ 4. calibration
def fig4():
    c = trust["calibration"]
    x, y = np.array(c["isotonic_x"]), np.array(c["isotonic_y"])
    fig, ax = page("4 · CALIBRATION ERROR", f"{c['ece_calibrated']:.1%}  (was {c['ece_raw']:.1%} before calibration)",
                   "Question: when the model says \"30% chance\", does a heatwave really follow about 30% of the time?",
                   f"Grey line = perfect honesty. Blue = what really happened for each score the raw model gave. Where blue is above\n"
                   f"the line the model was too shy; below, too confident. The average gap was {c['ece_raw']:.1%}; a fitted correction (isotonic\n"
                   f"regression) cuts it to {c['ece_calibrated']:.1%}, so the dashboard's percentages can be read as real chances.",
                   height=4.9, ax_rect=(0.12, 0.27, 0.5, 0.5))
    ax.plot([0, 1], [0, 1], color=RULE, lw=1.2, ls=(0, (4, 3)), label="Perfect: said = happened")
    ax.plot(x, y, color=MODEL, lw=1.8, label="Raw model: what really happened")
    ax.fill_between(x, x, y, color=MODEL, alpha=0.12, lw=0)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_aspect("equal")
    ax.set_xlabel("Chance the raw model said"); ax.set_ylabel("Share that really became a heatwave")
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}"); ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    tidy(ax, "both"); ax.legend(loc="upper left", fontsize=6.8, frameon=True, framealpha=0.95, edgecolor="none")
    # side: the two error bars
    bx = fig.add_axes([0.72, 0.36, 0.24, 0.36])
    vals = [c["ece_raw"], c["ece_calibrated"]]
    bx.bar([0, 1], vals, color=[RULE, MODEL], width=0.6)
    for i, v in enumerate(vals):
        bx.text(i, v + 0.001, f"{v:.1%}", ha="center", va="bottom", fontsize=8, fontweight="bold", color=INK)
    bx.set_xticks([0, 1]); bx.set_xticklabels(["before", "after\ncalibration"], fontsize=7)
    bx.set_yticks([]); bx.spines["left"].set_visible(False); bx.set_ylim(0, max(vals) * 1.3)
    bx.set_title("Average gap (ECE)", fontsize=7.5, loc="center")
    mf.save(fig, "trust_explained/04_calibration.png")


# ------------------------------------------------------------------ 5. spatial CV
def fig5():
    folds = metrics[best]["pr_auc_spatial_cv_folds"]
    mean = metrics[best]["pr_auc_spatial_cv_mean"]
    model_val, rule_val = metrics[best]["pr_auc_val"], metrics["persistence_baseline"]["pr_auc_val"]
    fig, ax = page("5 · UNSEEN REGIONS (SPATIAL CV)", f"{mean:.3f}",
                   "Question: does the model still work in a part of the ocean it was never trained on?",
                   f"Ecoregions are split into 5 groups. Each time, one group is hidden: the model trains on the other 4 (years 1982–2014)\n"
                   f"and is scored on the hidden group in 2015–2018. Average {mean:.3f}, almost the same as the model that saw every region\n"
                   f"({model_val:.3f}), and all 5 groups beat the rule ({rule_val:.3f}) → it learned general ocean behaviour, not just the places it saw.",
                   height=4.7, ax_rect=(0.1, 0.27, 0.5, 0.47))
    ax.bar(np.arange(1, 6), folds, color=MODEL, width=0.6)
    for i, v in enumerate(folds, 1):
        ax.text(i, v + 0.002, f"{v:.3f}", ha="center", va="bottom", fontsize=7, color=INK)
    for v, lab, col, ls, dy in ((model_val, f"all regions seen {model_val:.3f}", INK2, "-", 0.006),
                                (mean, f"hidden-region mean {mean:.3f}", MODEL, "--", -0.005),
                                (rule_val, f"rule {rule_val:.3f}", RULE, ":", 0)):
        ax.axhline(v, color=col, lw=1.1, ls=ls)
        ax.text(5.65, v + dy, lab, va="center", fontsize=6.4, color=col, clip_on=False)
    ax.set_xticks(range(1, 6)); ax.set_xticklabels([f"group {i}\nhidden" for i in range(1, 6)], fontsize=6.8)
    ax.set_ylim(0.53, 0.64); ax.set_xlim(0.4, 5.55); ax.set_ylabel("PR-AUC on the hidden regions (2015–18)"); tidy(ax, "y")
    # schematic of the folds
    sx = fig.add_axes([0.78, 0.33, 0.19, 0.4]); sx.axis("off"); sx.set_xlim(0, 5); sx.set_ylim(0, 5.6)
    for f in range(5):
        for g in range(5):
            sx.add_patch(Rectangle((g + 0.08, 4 - f + 0.12), 0.84, 0.76, fc=LOSE if g == f else "#d6e6f8", ec="white"))
    sx.text(2.5, 5.25, "5 runs × 5 region groups", ha="center", fontsize=6.6, color=INK2)
    sx.text(0, -0.35, "■", color="#d6e6f8", fontsize=9); sx.text(0.5, -0.3, "train", fontsize=6.3, color=INK2)
    sx.text(2.5, -0.35, "■", color=LOSE, fontsize=9); sx.text(3.0, -0.3, "test", fontsize=6.3, color=INK2)
    mf.save(fig, "trust_explained/05_spatial_cv.png")


# ------------------------------------------------------------------ lead-time helpers
def lead_groups(col):
    s = leads[col]
    return {"no warning": s.isna().sum(), "1–2 days": s.between(1, 2).sum(),
            "3–4 days": s.between(3, 4).sum(), "5–7 days": s.between(5, 7).sum()}


def fig6():
    lt = trust["lead_times"]
    m3, r3 = lt["model"]["warned_3d_or_more_share"], lt["rule"]["warned_3d_or_more_share"]
    fig, ax = page("6 · ONSETS WARNED ≥ 3 DAYS AHEAD", f"{m3:.0%} (rule {r3:.0%})",
                   "Question: for every heatwave start, did a warning come early enough (3+ days) to prepare?",
                   f"Each bar is all {lt['model']['onsets']:,} heatwave starts. Darker = earlier warning. The rule warns more often in total, but many of its\n"
                   f"warnings come only 1–2 days ahead (the heat is already building). The model gives 3+ days' notice for {m3:.0%} of starts vs\n"
                   f"{r3:.0%}: about {(m3 - r3) * lt['model']['onsets']:,.0f} more starts with useful time to act.",
                   height=4.3, ax_rect=(0.13, 0.33, 0.83, 0.38))
    cols = {"no warning": "#e1e0d9", "1–2 days": "#cde2fb", "3–4 days": "#6da7ec", "5–7 days": "#184f95"}
    for yi, (name, col) in enumerate((("Rule", "lead_days_rule"), (f"Model", "lead_days_model"))):
        g = lead_groups(col); n = sum(g.values()); left = 0
        for k, v in g.items():
            ax.barh(yi, v / n, left=left, color=cols[k], height=0.55, edgecolor="white", lw=1.5)
            if v / n > 0.06:
                ax.text(left + v / n / 2, yi, f"{v / n:.0%}", ha="center", va="center", fontsize=7.2,
                        color="white" if k in ("3–4 days", "5–7 days") else INK)
            left += v / n
        share3 = (g["3–4 days"] + g["5–7 days"]) / n
        ax.annotate("", xy=(1, yi + 0.36), xytext=(1 - share3, yi + 0.36),
                    arrowprops=dict(arrowstyle="<->", color=INK2, lw=0.8))
        ax.text(1 - share3 / 2, yi + 0.43, f"3+ days: {share3:.0%}", ha="center", va="bottom", fontsize=7, color=INK,
                fontweight="bold")
    ax.set_yticks([0, 1]); ax.set_yticklabels(["Rule", "Model"], fontsize=8)
    ax.set_xlim(0, 1); ax.set_ylim(-0.45, 2.25); ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0%}")
    ax.set_xlabel("Share of heatwave starts")
    ax.legend(handles=[Rectangle((0, 0), 1, 1, fc=c) for c in cols.values()], labels=list(cols),
              loc="upper center", bbox_to_anchor=(0.5, 1.02), ncol=4, fontsize=7, title="first warning came …", frameon=False,
              title_fontsize=7)
    mf.save(fig, "trust_explained/06_warned_3days.png")


def fig7():
    lt = trust["lead_times"]
    mm, rm = lt["model"]["median_lead_days_when_warned"], lt["rule"]["median_lead_days_when_warned"]
    fig, ax = page("7 · MEDIAN LEAD WHEN WARNED", f"{mm:.0f} days (rule {rm:.0f})",
                   "Question: when a warning did come, how many days before the heatwave started was it?",
                   f"Bars: how many warned starts got each lead time. The rule's biggest bar is 1 day (it only reacts once the sea is\n"
                   f"already hot); the model spreads earlier. The middle value (median) is {mm:.0f} days for the model vs {rm:.0f} for the rule.\n"
                   "7 days is the most we can measure, because the model looks one week ahead.",
                   height=4.9, ax_rect=(0.1, 0.27, 0.86, 0.38))
    days = np.arange(1, 8)
    m = leads.lead_days_model.value_counts().reindex(days, fill_value=0)
    r = leads.lead_days_rule.value_counts().reindex(days, fill_value=0)
    ax.bar(days - 0.19, r, width=0.36, color=RULE, label=f"Rule (median {rm:.0f} days)")
    ax.bar(days + 0.19, m, width=0.36, color=MODEL, label=f"Model (median {mm:.0f} days)")
    ax.set_xticks(days); ax.set_xticklabels([f"{d} day{'s' if d > 1 else ''}\nbefore" for d in days], fontsize=6.8)
    ax.set_ylabel("Warned heatwave starts"); ax.yaxis.set_major_formatter(lambda v, _: f"{v:,.0f}")
    ax.legend(loc="upper center", fontsize=7, frameon=False); tidy(ax, "y")
    # timeline sketch
    tx = fig.add_axes([0.1, 0.7, 0.86, 0.09]); tx.axis("off"); tx.set_xlim(-8.5, 2.5); tx.set_ylim(0, 1)
    tx.plot([-8, 2], [0.4, 0.4], color=INK2, lw=0.8)
    for d in range(-7, 2):
        tx.plot([d, d], [0.3, 0.5], color=INK2, lw=0.6)
    tx.text(0, 0.62, "heatwave starts\n(day 0)", ha="center", fontsize=6.5, color=LOSE, fontweight="bold")
    tx.plot(0, 0.4, "o", color=LOSE, ms=7)
    tx.plot(-5, 0.4, "v", color=MODEL, ms=8)
    tx.text(-5, 0.62, "first model warning", ha="center", fontsize=6.5, color=MODEL)
    tx.annotate("", xy=(-0.15, 0.12), xytext=(-5, 0.12), arrowprops=dict(arrowstyle="<->", color=MODEL, lw=0.9))
    tx.text(-2.5, -0.15, "lead time = 5 days", ha="center", fontsize=6.5, color=MODEL)
    mf.save(fig, "trust_explained/07_median_lead.png")


def fig8():
    lt = trust["lead_times"]
    n = lt["model"]["onsets"]
    per = leads.groupby("cell_id").size().rename("onsets").reset_index()
    cells = mf.cells.merge(per, on="cell_id")
    fig, ax = page("8 · ONSETS CHECKED", f"{n:,} heatwave starts",
                   f"Question: how big is the test of lead time? Every heatwave start in {lt['cells']:,} sample cells, 2019–2025.",
                   f"An onset = the first day of a heatwave in one cell. Instead of a few hand-picked cases, every onset in a regular sample of\n"
                   f"{lt['cells']:,} cells (every k-th ocean cell) was checked, {n:,} in total, about {n / lt['cells']:.0f} per cell. Dots: number of onsets in each sampled cell.",
                   height=5.0, ax_rect=(0.08, 0.22, 0.8, 0.58))
    mf.base_map(ax)
    sc = ax.scatter(cells.lon, cells.lat, c=cells.onsets, s=6, cmap=mf.HEAT, zorder=5, lw=0)
    cb = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.02, shrink=0.8)
    cb.set_label("Onsets in the cell (2019–25)", fontsize=7, color=INK2); cb.ax.tick_params(labelsize=6.5)
    mf.save(fig, "trust_explained/08_onsets_checked.png")


if __name__ == "__main__":
    for f in (fig1, fig2, fig3, fig4, fig5, fig6, fig7, fig8):
        f()
