// Builds the short (max 10 pages) project report: Introduction, Methodology, Results, Discussion.
//   node report/build_short_report.js       (needs the npm package "docx"; figures from report/make_figures.py)
// Then run report/finalize_report.ps1 -Docx report/Hot_Oceans_Report_253318.docx to update fields and export a PDF.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, AlignmentType, HeadingLevel, Footer, PageNumber,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType, LevelFormat, SequentialIdentifier, VerticalAlign,
} = require("docx");

const HERE = __dirname;
const FIG = path.join(HERE, "figures");
const OUT = process.argv[2] ? path.resolve(process.argv[2]) : path.join(HERE, "Hot_Oceans_Report_253318.docx");
const FONT = "Times New Roman";

const STUDENT = "Ananthanarayanan B";
const REG = "253318";
const DEGREE = "M. Sc. in Data Analytics and Geoinformatics";
const COURSE = "Spatial Big Data";
const SUPERVISOR = "Manoj Kumar";
const MONTH_YEAR = "NOVEMBER 2026";
const TITLE_1 = "Hot Oceans: Detection, Tracking and Prediction of";
const TITLE_2 = "Marine Heatwaves in the Indian Ocean (1982–2025)";
const SUBTITLE = "Using Apache Spark, Apache Sedona, PostGIS and Spark MLlib";

// ---------------------------------------------------------------- helpers
const pngSize = (file) => { const b = fs.readFileSync(file); return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) }; };

// Inline markup: **bold**, *italic*, `code`, _{sub}, ^{sup}
function runs(text, base = {}) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|_\{[^}]+\}|\^\{[^}]+\})/g);
  const out = [];
  parts.forEach((p, i) => {
    if (!p) return;
    if (i % 2 === 0) out.push(new TextRun({ ...base, text: p }));
    else if (p.startsWith("**")) out.push(new TextRun({ ...base, text: p.slice(2, -2), bold: true }));
    else if (p.startsWith("`")) out.push(new TextRun({ ...base, text: p.slice(1, -1), font: "Consolas", size: 19 }));
    else if (p.startsWith("_{")) out.push(new TextRun({ ...base, text: p.slice(2, -1), subScript: true }));
    else if (p.startsWith("^{")) out.push(new TextRun({ ...base, text: p.slice(2, -1), superScript: true }));
    else out.push(new TextRun({ ...base, text: p.slice(1, -1), italics: true }));
  });
  return out;
}

const H1 = (t) => ({ k: "h1", t });
const H2 = (t) => ({ k: "h2", t });
const P = (t) => ({ k: "p", t });
const BUL = (items) => ({ k: "bul", items });
const EQ = (t) => ({ k: "eq", t });
const FIGB = (key, file, caption, width = 5.6) => ({ k: "fig", key, file, caption, width });
const TAB = (key, caption, head, rows, widths, align = []) => ({ k: "tab", key, caption, head, rows, widths, align });

function numberBlocks(blocks) {
  const fig = {}, tab = {};
  let f = 0, t = 0;
  for (const b of blocks) { if (b.k === "fig") fig[b.key] = ++f; if (b.k === "tab") tab[b.key] = ++t; }
  return (s) => s.replace(/\{fig:([\w-]+)\}/g, (_, k) => { if (!(k in fig)) throw new Error(`unknown figure ${k}`); return `Figure ${fig[k]}`; })
                 .replace(/\{tab:([\w-]+)\}/g, (_, k) => { if (!(k in tab)) throw new Error(`unknown table ${k}`); return `Table ${tab[k]}`; });
}

const border = (sz = 4, color = "000000") => ({ style: BorderStyle.SINGLE, size: sz, color });
const L_ = AlignmentType.LEFT, R_ = AlignmentType.RIGHT, C_ = AlignmentType.CENTER;

function cell(text, w, { head = false, align = L_ } = {}) {
  return new TableCell({
    width: { size: w, type: WidthType.DXA }, verticalAlign: VerticalAlign.CENTER,
    shading: head ? { type: ShadingType.CLEAR, color: "auto", fill: "E7E6E6" } : undefined,
    margins: { top: 30, bottom: 30, left: 80, right: 80 },
    children: [new Paragraph({ alignment: align, spacing: { line: 240, before: 0, after: 0 },
      children: runs(String(text), { size: 19, bold: head || undefined }) })],
  });
}

function render(blocks, R) {
  const out = [];
  for (const b of blocks) {
    switch (b.k) {
      case "h1": out.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: runs(b.t) })); break;
      case "h2": out.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: runs(b.t) })); break;
      case "p": out.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED, children: runs(R(b.t)) })); break;
      case "bul":
        b.items.forEach((it) => out.push(new Paragraph({ alignment: AlignmentType.JUSTIFIED,
          numbering: { reference: "bullets", level: 0 }, spacing: { after: 40 }, children: runs(R(it)) })));
        break;
      case "eq":
        out.push(new Paragraph({ alignment: C_, spacing: { before: 40, after: 80 }, children: runs(b.t, { italics: true }) }));
        break;
      case "fig": {
        const file = path.join(FIG, b.file);
        const { w, h } = pngSize(file);
        const wpx = b.width * 96;
        out.push(new Paragraph({ alignment: C_, keepNext: true, spacing: { before: 100, after: 40, line: 240 },
          children: [new ImageRun({ type: "png", data: fs.readFileSync(file), transformation: { width: wpx, height: wpx * h / w } })] }));
        out.push(new Paragraph({ style: "FigCaption",
          children: [new TextRun({ text: "Figure ", bold: true }), new SequentialIdentifier("Figure"), ...runs(`: ${R(b.caption)}`)] }));
        break;
      }
      case "tab": {
        const tw = b.widths.reduce((a, c) => a + c, 0);
        out.push(new Paragraph({ style: "TabCaption",
          children: [new TextRun({ text: "Table ", bold: true }), new SequentialIdentifier("Table"), ...runs(`: ${R(b.caption)}`)] }));
        out.push(new Table({
          width: { size: tw, type: WidthType.DXA }, columnWidths: b.widths, alignment: C_,
          borders: { top: border(6), bottom: border(6), left: border(4, "7F7F7F"), right: border(4, "7F7F7F"),
            insideHorizontal: border(2, "A6A6A6"), insideVertical: border(2, "A6A6A6") },
          rows: [
            new TableRow({ tableHeader: true, children: b.head.map((h, i) => cell(h, b.widths[i], { head: true, align: b.align[i] })) }),
            ...b.rows.map((r) => new TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, b.widths[i], { align: b.align[i] })) })),
          ],
        }));
        out.push(new Paragraph({ spacing: { after: 60 }, children: [] }));
        break;
      }
      default: throw new Error(`unknown block ${b.k}`);
    }
  }
  return out;
}

// ---------------------------------------------------------------- body
// Written in the first person, in plain language, for a reader who knows GIS but not marine heatwaves.
const body = [
  H1("1. Introduction"),
  P("The ocean is getting warmer, but the warming does not arrive evenly. Every few years a patch of sea becomes unusually hot and stays that way for days, weeks or even months. Such an episode is called a **marine heatwave** (MHW). The standard definition, by Hobday et al. (2016), says that a marine heatwave occurs when the sea surface temperature (SST) at a place stays above its usual ‘hot’ level for that time of year for at least five days in a row. The ‘hot’ level is the 90th percentile: in a normal year, the water is warmer than this on only about one day in ten. Marine heatwaves bleach corals, kill fish and seagrass, and hurt the coastal communities that depend on them, and they have become longer and more frequent as the ocean warms (Oliver et al., 2018; Frölicher et al., 2018)."),
  P("I chose the Indian Ocean because it is the ocean on our doorstep and because it is changing fast. The tropical Indian Ocean has warmed faster than the other tropical oceans (Roxy et al., 2014), its heatwaves have increased sharply since the 1980s (Saranya et al., 2022), and in 2023–2024 it was part of the fourth global coral bleaching event (NOAA, 2024). For a close-up example I followed one place near Kerala, the Lakshadweep islands."),
  P("Studying heatwaves over a whole ocean is a **big-data problem**. The NOAA OISST v2.1 dataset (Huang et al., 2021) gives one temperature value per day for every 0.25° square of ocean, about 28 km across. I call each square a *cell*. My study box (30°S–30°N, 30°E–120°E; {fig:study}) contains 58,334 ocean cells, and the record covers 16,071 days from 1982 to 2025. That makes **937.5 million cell-days**. Every cell needs its own 30-year ‘normal’ for each day of the year, every day needs its hot cells grouped into patches, and every patch has to be followed from one day to the next. A desktop GIS cannot do this in a reasonable time, so I used a distributed big-data stack."),
  FIGB("study", "fig01_study_area.png", "Study area: the Indian Ocean box with land masked, the six sectors used in the analysis, the small sample box I used for development on my laptop, and the Lakshadweep case-study cell", 4.9),
  P("My aim was to build a single pipeline, called **Hot Oceans**, that turns 44 years of daily satellite data into two things: a catalogue of every Indian Ocean heatwave, and a warning that says whether a place is likely to be in a heatwave within the next seven days. In detail, I set out to:"),
  BUL([
    "build a clean, partitioned data lake with automatic quality checks;",
    "detect and grade heatwaves in every cell with the Hobday method;",
    "group hot cells into events, draw their outlines and track them through time with Apache Sedona;",
    "see how events relate to the season, the region and two climate modes, the Indian Ocean Dipole (IOD) and El Niño (ENSO);",
    "train a seven-day warning model with Spark MLlib and test honestly how far it can be trusted; and",
    "share the results through a PostGIS database and an interactive dashboard.",
  ]),

  H1("2. Methodology"),
  H2("2.1. Data and Tools"),
  P("I used four free datasets ({tab:data})."),
  TAB("data", "The four datasets used in this project",
    ["Dataset", "What it gives", "Source"], [
      ["**NOAA OISST v2.1**", "Daily SST on a 0.25° grid, 1982–2025 (about 1.6 GB of NetCDF)", "NOAA PSL, by OPeNDAP"],
      ["**Marine Ecoregions of the World** (MEOW)", "232 coastal and shelf ecoregion polygons", "Spalding et al. (2007)"],
      ["**Dipole Mode Index** (DMI)", "Monthly strength of the Indian Ocean Dipole", "NOAA PSL"],
      ["**Oceanic Niño Index** (ONI)", "Monthly strength of El Niño and La Niña", "NOAA CPC"],
    ], [2900, 4300, 2400], [L_, L_, L_]),
  P("The whole pipeline is written in Python. **Apache Spark 3.5** spreads the work over many processor cores; **Apache Sedona 1.6** (which grew out of GeoSpark; Yu et al., 2015) adds spatial SQL to Spark, such as point-in-polygon tests and polygon overlaps; and **Spark MLlib** provides the clustering and machine-learning models. The final tables go into **PostgreSQL 13 with PostGIS 3.4**, and the dashboard is built with **Streamlit** and **pydeck** maps. I first built and debugged everything on my laptop (16 threads, 16 GB RAM) using a small sample box off south-west India (5–15°N, 65–80°E; 31.7 million cell-days). Once it worked, I ran the full basin on the university’s **NVIDIA DGX server**, giving Spark 48 cores and 200 GB of memory. Moving from the laptop to the DGX needed only one configuration setting to change."),
  P("The pipeline has seven stages, A to G ({fig:arch}). Each stage reads from the data lake and writes its result back, records how many rows it produced and how long it took, and can be restarted from where it stopped if something fails."),
  FIGB("arch", "fig02_architecture.png", "Architecture of the Hot Oceans pipeline. Stages A–G run on the DGX with Spark, Sedona and MLlib; the small final results are copied to my PC for PostGIS, the dashboard and this report", 5.3),
  H2("2.2. Building a Clean Data Lake (Stage A)"),
  P("I downloaded the data one month at a time and turned it into a long table with one row per ocean cell per day. Each cell gets a fixed number from its position on the global grid, `cell_id = row × 1440 + col`. The table is saved as Parquet files split into 64 groups (`cell_id mod 64`), so that the full 44-year history of any cell sits in one partition. This makes the next stage much faster."),
  P("Quality control turned out to matter more than I expected. My first download sent several requests at the same time, and on 162 days the server quietly returned arrays that were only half filled. Nothing crashed, so the problem was easy to miss. Because the OISST land mask never changes, every complete day must have exactly 58,334 valid ocean cells, all between −2 °C and 40 °C. I turned this into an automatic check. It caught every bad day; I downloaded those years again, one at a time, and the final lake has **937,485,714 rows with no gaps and no duplicates**. Finally, each cell was tagged with its marine ecoregion through a Sedona point-in-polygon join (`ST_Contains`)."),
  H2("2.3. Detecting Heatwaves (Stage B)"),
  P("To say whether a day is unusually hot, each cell first needs its own idea of ‘normal’. Following Hobday et al. (2016), for every cell and every calendar day *d* I collected all values from 1991–2020 that fall within five days of *d*. Their average is the **climatology** (the normal temperature) and their 90th percentile is the **threshold** (the ‘hot’ level). Both are smoothed with a 31-day moving average. For each day *t* I then work out the anomaly *A* and the intensity ratio *R*:"),
  EQ("A(t) = SST(t) − clim(d),     R(t) = A(t) / (thresh(d) − clim(d))"),
  P("*R* says how far above normal the water is, measured in steps of the gap between ‘normal’ and ‘hot’: *R* = 1 means the water is exactly at the threshold. A heatwave is a run of at least five days above the threshold, and two runs separated by two days or less are joined into one. Each heatwave day is graded as in Hobday et al. (2018): **Moderate** when 1 ≤ *R* < 2, **Strong** when 2 ≤ *R* < 3, **Severe** when 3 ≤ *R* < 4 and **Extreme** when *R* ≥ 4. {fig:detect} shows the method at work in the Lakshadweep cell."),
  FIGB("detect", "fig03_detection.png", "Heatwave detection at the Lakshadweep cell, May 2023 to June 2024: daily SST (black), the climatology (grey), the 90th-percentile threshold (blue dashes) and the heatwave days, coloured by category", 5.3),
  P("In Spark, I grouped the rows by cell and ran this calculation with `groupBy(\"cell_id\").applyInPandas`, so that the 48 cores could work on different cells at the same time. Small unit tests with made-up temperature series check the five-day rule and the joining of gaps."),
  H2("2.4. Tracking Heatwave Events (Stages C–D)"),
  P("A heatwave in a single cell is only part of the story, because real heatwaves cover large areas and move. To find these patches, on each day I grouped neighbouring heatwave cells with **DBSCAN** (Ester et al., 1996), a clustering method that joins points lying close together (here within 1.5 cells, with at least 4 cells per group). For every patch of 20 cells or more, Sedona draws an outline polygon, which I call a **footprint**, by merging the cell centres, taking their convex hull and adding a small buffer (`ST_Union_Aggr`, `ST_ConvexHull`, `ST_Buffer`). It also gives each footprint’s area and centre point."),
  P("To follow a patch through time, I joined each day’s footprints to the next day’s wherever they overlap (`ST_Intersects`). A chain of overlapping footprints that lasts at least five days becomes one **event**; a union-find algorithm collects the chains. I then sorted the events into types with **K-Means** clustering (the number of types chosen by the silhouette score) and used **FP-Growth** association rules to look for patterns linking an event’s strength and length to its sector, season and climate phase."),
  H2("2.5. The Seven-day Warning Model (Stage E)"),
  P("**The question.** The model answers a simple, practical question: *if this cell is not in a heatwave yet, will it be in one at some point in the next seven days?* I ask it only for cell-days that are not already in a confirmed heatwave, that is, days when the water has been above the threshold for fewer than five days in a row. Once a heatwave is confirmed there is nothing left to forecast, so those days are left out."),
  P("**What the model sees.** I built 23 input features, and every one of them uses only information available on the forecast day. Some describe the cell itself: how hot it is today compared with its threshold, its 7- and 30-day averages, whether it is warming or cooling, how many recent days were above the threshold, and how much warming it still needs to cross it. The rest describe **its neighbourhood**: the average and the maximum heat of the eight surrounding cells and of boxes of 7 × 7 and 21 × 21 cells, and the share of those cells already above the threshold. I computed the neighbourhood features for the whole grid one day at a time, using image filters (`scipy.ndimage` inside `groupBy(\"date\").applyInPandas`). I deliberately left out latitude, longitude, season and climate indices, so that the model has to learn from the warm water itself rather than memorise places or dates."),
  P("**A mistake I found and fixed.** My first version of the model scored surprisingly well. When I looked closely, I found that some features used the final heatwave flag, which can only be known a few days later, because a heatwave needs five days to be confirmed. In other words, the model was quietly peeking into the future. This is called **look-ahead leakage**. I rebuilt the features so that they use only the past, and wrote a **leakage audit**: it cuts the data off at the forecast day, recomputes everything from scratch and compares the result with the stored features. On 6,000 random cell-days and 16 inputs it found **0 differences**, and a unit test now repeats this check every time. The honest scores were lower than the leaky ones, and they are the only scores reported here."),
  P("**Training and testing.** I split the data by time, in the same way a real forecast would be used: the years up to 2014 to train, 2015–2018 to tune (the number of trees, the warning threshold and the choice of model), and **2019–2025 only for the final test**, kept untouched until the end. For training I used a thinned sample (3% of the rows that turned into heatwaves and 0.4% of the rest), with weights so that the model still learns the true balance. The test set is a 25% random sample of all test cell-days, which is still **32.1 million rows**. In Spark MLlib I trained a **Gradient-Boosted Trees** model (GBT; Friedman, 2001; up to 400 trees of depth 6, with early stopping) and a **Random Forest** (Breiman, 2001; 150 trees of depth 10). Both were compared with a simple **persistence rule**: *the hotter the water is today, the higher the risk*. A model is only worth having if it beats this rule."),
  P("**How I measured success.** Only 13.9% of the test rows turned into heatwaves, so accuracy is misleading: a lazy model that always says ‘no heatwave’ is already 86% accurate. I therefore used the area under the precision–recall curve (**PR-AUC**; Saito & Rehmsmeier, 2015) as the main score. It rewards a model for finding the rare heatwave cases without raising too many false alarms; a random guess scores 0.139 and a perfect model 1. I also report precision, recall and F1 at the warning threshold that gave the best F1 on the tuning years:"),
  EQ("precision = TP / (TP + FP),   recall = TP / (TP + FN),   F1 = 2 · precision · recall / (precision + recall)"),
  P("Here TP is the number of correct warnings, FP the false alarms and FN the missed heatwaves."),
  P("**Trust checks.** One good score on one test set is not enough to trust a model, so, following Roberts et al. (2017), I added five more checks: (i) *spatial cross-validation*, in which whole groups of ecoregions are held out, to see whether the model works in places it never trained on; (ii) separate scores for every test year and every region; (iii) a *block bootstrap* (1,000 resamples of year × region blocks) to get 95% confidence intervals; (iv) a *calibration* check, to see whether a ‘30% risk’ really means about 30%, with isotonic regression fitted on the tuning years to correct it; and (v) *lead time*, the number of days between the first warning and the start of a heatwave, measured on 30,806 heatwave starts in a regular subset of 1,145 cells."),
  H2("2.6. Case Study, Database and Dashboard (Stages F–G)"),
  P("To test the model on a real event it had never seen, Stage F follows the cell containing Kavaratti, Lakshadweep (10.57°N, 72.64°E), through the heatwave of May 2023. Stage G exports the spatial results (the cells, 291,272 daily footprints and 14,472 events) as GeoParquet. On my PC these are loaded into PostGIS with spatial (GiST) indexes, so a question such as *‘which ecoregions did heatwave footprints touch in April–May 2024?’* is answered in SQL within seconds. A Streamlit dashboard with pydeck maps shows the daily heatwave map, the event catalogue and tracks, the trends, the seven-day risk map and the case study."),

  H1("3. Results"),
  H2("3.1. Processing at Scale"),
  P("Once the pipeline was correct, the full run on the DGX was quick. Loading the 937.5 million rows took 11 minutes, Hobday detection for all 58,334 cells 3.3 minutes, and the daily clustering, footprints and tracking 2.1 minutes. The model stage was the slowest at 82 minutes, because it builds features for all 937.5 million cell-days, trains both models and runs the spatial cross-validation; the trust checks took 3 minutes. Each stage shrinks the data: 937.5 million cell-days → 66.5 million heatwave cell-days → 291,272 daily footprints → **14,472 events**."),
  H2("3.2. Heatwaves Have Become Six Times More Common"),
  P("This is the clearest result of the project. In 1982–1991 an average ocean cell spent **9.6 days a year** in a heatwave; in 2016–2025 it spent **60.5 days**, more than six times as many. The linear trend is **+14.9 days per decade** ({fig:trend}). The peaks match strong El Niño and positive IOD years (1998, 2010, 2016, 2023). **2024 was the record year, with 133 days**: the typical cell was in a heatwave for more than a third of the year. On 6 February 2024, **55.6% of the ocean area** in my box was in a heatwave at the same time. In 2024 the Bay of Bengal (173 days) and the Arabian Sea (165 days) were the hardest-hit sectors ({fig:days})."),
  FIGB("trend", "fig05_trend.png", "Average number of marine heatwave days per ocean cell in each year, 1982–2025, with the linear trend", 5.3),
  FIGB("days", "fig06_days_2023_2024.png", "Number of heatwave days in each 0.25° cell in 2023 and 2024", 5.6),
  H2("3.3. Events, Event Types and Climate Drivers"),
  P("The catalogue holds 14,472 events. Most are short and small: half last 7 days or less, and half have a peak area below about 35,000 km², a little less than the area of Kerala. But 560 events lasted 30 days or more, and the largest ones, in 1997–98, 2014–16, 2018–21 and 2023–25, lasted one to three years (these very long events are partly a side effect of my linking rule; see Section 4). K-Means found three types of event, *short and mild*, *short and intense* and *long and large*, with a silhouette score of 0.26, which means the types overlap quite a lot. The mix of types changed only a little between IOD and ENSO phases, and the strongest FP-Growth rule had a lift of only 1.21. So the season, the region and the climate phase on their own say little about how strong an event will become."),
  H2("3.4. How Well Does the Warning Work?"),
  P("{tab:model} and {fig:model} show the scores on the test years 2019–2025. Both models beat the persistence rule. The GBT, which I chose on the tuning years, reaches a **PR-AUC of 0.625**, against 0.598 for the rule and 0.139 for a random guess, and its ROC-AUC is 0.884; the Random Forest scored the same PR-AUC. The hardest case is when the water is still below the threshold today. Here both methods are much weaker (0.276 for the model and 0.260 for the rule). As expected, accuracy is no help in comparing them: it is about 88% for both the model and the rule, against 86% for always answering ‘no’."),
  TAB("model", "Warning scores on the test years 2019–2025 (32.1 million cell-days, 13.9% of which turned into heatwaves)",
    ["Method", "PR-AUC", "PR-AUC (below threshold today)", "ROC-AUC", "Precision", "Recall", "F1"], [
      ["Random guess", "0.139", "0.084", "0.500", "–", "–", "–"],
      ["Persistence rule", "0.598", "0.260", "–", "0.574", "0.546", "0.560"],
      ["Random Forest", "0.625", "0.276", "0.883", "0.556", "0.579", "0.567"],
      ["**GBT (chosen)**", "**0.625**", "**0.276**", "**0.884**", "0.562", "0.568", "0.565"],
    ], [1900, 900, 1600, 950, 1000, 900, 800], [L_, R_, R_, R_, R_, R_, R_]),
  FIGB("model", "fig12_model.png", "Test PR-AUC of the models compared with a random guess and the persistence rule (left), and the ten most important GBT features (right)", 5.6),
  P("The feature importance ({fig:model}, right) tells an interesting story. The four most important features all describe the **surrounding water**: the average heat in the 7 × 7 box (importance 0.26), in the eight neighbouring cells (0.17) and in the 21 × 21 box (0.14), and the hottest neighbour (0.10). In other words, heatwaves usually spread into a cell from warm water next to it. This is exactly the kind of signal a spatial pipeline can capture and a single-cell time-series model would miss."),
  H2("3.5. Can the Warning Be Trusted?"),
  BUL([
    "**In places it never saw:** when whole groups of ecoregions were held out of training, PR-AUC stayed between 0.585 and 0.616 (mean 0.606), about the same as on the tuning years (0.607). The model is not just memorising places.",
    "**In every year and region:** the model beat the rule in **all 7 test years** and in **49 of 51 regions** ({fig:trust}, left). The only two exceptions, the East China Sea and Shark Bay, are small regions at the edge of the box.",
    "**Is the gain real?** The bootstrap gives a PR-AUC of 0.625 (95% CI 0.612–0.636) for the model and 0.598 (0.584–0.610) for the rule. The **gain lies between +0.022 and +0.032**, and it was positive in all 1,000 resamples.",
    "**Can the risk be read as a probability?** The raw scores slightly understate the risk. After isotonic calibration the average calibration error fell from 3.0% to **0.9%** ({fig:trust}, right), so a calibrated ‘30% risk’ really means about a 30% chance.",
    "**How early does it warn?** Over 30,806 heatwave starts, the model warned **at least 3 days ahead in 48%** of cases (rule 44%) and at least 5 days ahead in 35% (rule 31%). When it did warn, the typical (median) lead time was 5 days, against 4 days for the rule.",
  ]),
  FIGB("trust", "fig15_trust.png", "Trust checks: PR-AUC of the model and the persistence rule in each test year (left), and calibration of the risk scores before and after isotonic calibration (right)", 5.6),
  H2("3.6. Lakshadweep 2023: A Five-day Warning"),
  P("At the Lakshadweep cell the heatwave began on **12 May 2023** ({fig:case}). The model’s risk crossed the warning threshold of 0.23 on **7 May**, peaked at 0.40 on 8 May, dipped just below the threshold on 9–11 May and rose again on the day of onset. That is a **warning five days ahead** for an event the model had never seen. The cell then stayed in heatwave conditions for most of the following year (330 of the 427 days up to June 2024; see also {fig:detect})."),
  FIGB("case", "fig13_case_warning.png", "Early warning at the Lakshadweep cell before the 12 May 2023 onset: the GBT risk score, the warning threshold chosen on the tuning years and the first warning on 7 May", 5.6),

  H1("4. Discussion"),
  P("This project showed me that a spatial big-data stack can turn a billion-row satellite record into a heatwave catalogue, long-term trends and a tested warning in under three hours of computing. Spark’s grouped pandas functions let me write the per-cell and per-day calculations in ordinary pandas and still run them on 48 cores. Sedona let me write footprint building and tracking as short spatial SQL queries, and MLlib trained the models on millions of rows."),
  P("The biggest lesson, though, was about **trusting the data and the model**. Twice, something went wrong without any error message: the half-empty downloads and the look-ahead leak. Both would have given me results that looked convincing but were wrong, and I caught them only because I wrote explicit checks (the land-mask check and the leakage audit). In future projects I will write such checks from the start, not only after something looks suspicious."),
  P("The warning results also need an honest reading. The model is better than the persistence rule in every test year, in almost every region and in every bootstrap resample, but the **gain is small** (+0.027 PR-AUC). Most of what makes a heatwave predictable is simply that the water is already warm. When the water is still below its threshold, both methods are weak (PR-AUC about 0.27), because sudden heatwaves are often triggered by calm winds and changes in ocean mixing, which surface temperature alone cannot show. The model’s real value is that it **warns earlier**, and its strongest clue, the warmth of the surrounding water, is a spatial one."),
  P("**Limitations.** (i) I used a fixed 1991–2020 baseline, so part of the rise in heatwave days reflects long-term warming rather than more frequent short extremes (Amaya et al., 2023). (ii) My tracking links any footprints that overlap, so neighbouring patches can chain together into very long, basin-wide events. (iii) A 0.25° cell (about 28 km) is too coarse to show small atolls such as those of Lakshadweep properly. (iv) The model sees only surface temperature, and the persistence rule still gives slightly more warnings at least one day ahead (65% of onsets against 60%)."),
  P("**Future work.** With more time, I would (i) add subsurface ocean heat content, winds, mixed-layer depth and air–sea heat flux, which drive the sudden onsets that SST cannot foresee; (ii) use a detrended baseline to separate long-term warming from short extremes; (iii) link footprints only when they overlap by a minimum share; (iv) try spatio-temporal deep learning, such as a ConvLSTM, on the daily maps; and (v) update the data automatically every day, so that the dashboard could work as a real heatwave monitor for the Indian Ocean."),
  P("To sum up: Indian Ocean heatwaves have become about six times more common since the 1980s, 2024 was the worst year on record, and a model built mainly on the warmth of neighbouring water can give a modest but reliable head start of a few days. All of this was possible only because the data were handled at full scale and checked carefully at every step."),
];

// ---------------------------------------------------------------- references
const REFS = [
  "Amaya, D. J., et al. (2023). Marine heatwaves need clear definitions so coastal communities can adapt. *Nature, 616*, 29–32.",
  "Breiman, L. (2001). Random forests. *Machine Learning, 45*(1), 5–32.",
  "Ester, M., Kriegel, H.-P., Sander, J., & Xu, X. (1996). A density-based algorithm for discovering clusters in large spatial databases with noise. *Proc. KDD-96*, 226–231.",
  "Friedman, J. H. (2001). Greedy function approximation: A gradient boosting machine. *Annals of Statistics, 29*(5), 1189–1232.",
  "Frölicher, T. L., Fischer, E. M., & Gruber, N. (2018). Marine heatwaves under global warming. *Nature, 560*, 360–364.",
  "Hobday, A. J., et al. (2016). A hierarchical approach to defining marine heatwaves. *Progress in Oceanography, 141*, 227–238.",
  "Hobday, A. J., et al. (2018). Categorizing and naming marine heatwaves. *Oceanography, 31*(2), 162–173.",
  "Huang, B., et al. (2021). Improvements of the Daily Optimum Interpolation Sea Surface Temperature (DOISST) Version 2.1. *Journal of Climate, 34*(8), 2923–2939.",
  "NOAA. (2024, April 15). *NOAA confirms 4th global coral bleaching event* [Press release].",
  "Oliver, E. C. J., et al. (2018). Longer and more frequent marine heatwaves over the past century. *Nature Communications, 9*, 1324.",
  "Roberts, D. R., et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. *Ecography, 40*(8), 913–929.",
  "Roxy, M. K., Ritika, K., Terray, P., & Masson, S. (2014). The curious case of Indian Ocean warming. *Journal of Climate, 27*(22), 8501–8509.",
  "Saito, T., & Rehmsmeier, M. (2015). The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets. *PLoS ONE, 10*(3), e0118432.",
  "Saranya, J. S., Roxy, M. K., Dasgupta, P., & Anand, A. (2022). Genesis and trends in marine heatwaves over the tropical Indian Ocean and their interaction with the Indian summer monsoon. *JGR: Oceans, 127*, e2021JC017427.",
  "Spalding, M. D., et al. (2007). Marine ecoregions of the world: A bioregionalization of coastal and shelf areas. *BioScience, 57*(7), 573–583.",
  "Yu, J., Wu, J., & Sarwat, M. (2015). GeoSpark: A cluster computing framework for processing large-scale spatial data. *Proc. ACM SIGSPATIAL 2015*, Article 70.",
];

// ---------------------------------------------------------------- cover
function centered(text, o = {}) {
  return new Paragraph({ alignment: C_, spacing: { before: o.before || 0, after: o.after ?? 120, line: 276 },
    children: [new TextRun({ text, bold: o.bold, italics: o.italics, size: o.size || 24 })] });
}

function coverPage() {
  const logo = path.join(HERE, "assets", "duk_logo.png");
  const { w, h } = pngSize(logo);
  const lw = 2.6 * 96;
  return [
    centered(TITLE_1, { bold: true, size: 36, before: 700, after: 60 }),
    centered(TITLE_2, { bold: true, size: 36, after: 200 }),
    centered(SUBTITLE, { italics: true, size: 26, after: 700 }),
    centered("Submitted By", { italics: true, after: 140 }),
    centered(STUDENT, { bold: true, size: 26, after: 100 }),
    centered(`Reg. No: ${REG}`, { bold: true, size: 26, after: 400 }),
    centered("Under the guidance of", { italics: true, after: 140 }),
    centered(SUPERVISOR, { bold: true, size: 26, after: 100 }),
    centered("School of Digital Sciences", { after: 400 }),
    centered(`${DEGREE}`, { after: 100 }),
    centered(`Course Project – ${COURSE}`, { after: 500 }),
    new Paragraph({ alignment: C_, spacing: { after: 500 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(logo), transformation: { width: lw, height: lw * h / w } })] }),
    centered("School of Digital Sciences", { bold: true, size: 26, after: 160 }),
    centered("KERALA UNIVERSITY OF DIGITAL SCIENCES, INNOVATION, AND TECHNOLOGY", { bold: true, size: 21, after: 100 }),
    centered("(DIGITAL UNIVERSITY KERALA)", { bold: true, size: 21, after: 100 }),
    centered(`TECHNOPARK PHASE-IV, THIRUVANANTHAPURAM ${MONTH_YEAR}`, { bold: true, size: 21, after: 0 }),
  ];
}

// ---------------------------------------------------------------- document
const R = numberBlocks(body);
const footer = new Footer({ children: [new Paragraph({ alignment: R_,
  children: [new TextRun({ children: [PageNumber.CURRENT], size: 20 })] })] });

const doc = new Document({
  creator: STUDENT, title: `${TITLE_1} ${TITLE_2}`, description: "Spatial Big Data course project report",
  styles: {
    default: {
      document: { run: { font: FONT, size: 22 }, paragraph: { spacing: { line: 264, after: 100 } } },
      heading1: { run: { font: FONT, size: 30, bold: true, color: "000000" },
        paragraph: { spacing: { before: 240, after: 140, line: 276 }, keepNext: true, outlineLevel: 0 } },
      heading2: { run: { font: FONT, size: 24, bold: true, color: "000000" },
        paragraph: { spacing: { before: 160, after: 80, line: 276 }, keepNext: true, outlineLevel: 1 } },
    },
    paragraphStyles: [
      { id: "FigCaption", name: "Figure Caption", basedOn: "Normal", run: { font: FONT, size: 19 },
        paragraph: { alignment: C_, spacing: { before: 20, after: 160, line: 240 }, indent: { left: 500, right: 500 } } },
      { id: "TabCaption", name: "Table Caption", basedOn: "Normal", run: { font: FONT, size: 19 },
        paragraph: { alignment: C_, spacing: { before: 100, after: 60, line: 240 }, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: L_,
      style: { paragraph: { indent: { left: 500, hanging: 280 } } } }] },
    { reference: "refs", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: L_,
      style: { paragraph: { indent: { left: 450, hanging: 450 } } } }] },
  ] },
  sections: [
    { properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
      children: coverPage() },
    { properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, right: 1134, bottom: 1134, left: 1134, footer: 500 },
        pageNumbers: { start: 1 } } },
      footers: { default: footer },
      children: [...render(body, R),
        new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("References")] }),
        ...REFS.map((t) => new Paragraph({ numbering: { reference: "refs", level: 0 }, spacing: { line: 240, after: 40 },
          children: runs(t, { size: 19 }) }))] },
  ],
});

Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log(`wrote ${OUT}`); });
