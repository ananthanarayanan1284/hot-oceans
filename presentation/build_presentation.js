// Builds the project presentation (16:9, PowerPoint) with pptxgenjs.
//   node presentation/build_presentation.js [out.pptx]
// Needs: pptxgenjs, react, react-dom, react-icons, sharp (NODE_PATH), figures in report/figures,
// presentation/assets/hero_2024.png (presentation/make_hero_map.py) and the pptx skill's apply_theme.js (APPLY_THEME env).
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa6");
const gi = require("react-icons/gi");
const { applyTheme } = require(process.env.APPLY_THEME);

const ROOT = path.resolve(__dirname, "..");
const FIG = (f) => path.join(ROOT, "report", "figures", f);
const OUT = process.argv[2] ? path.resolve(process.argv[2]) : path.join(__dirname, "Hot_Oceans_Presentation_253318.pptx");

// ---------------------------------------------------------------- theme
const T = {
  dk1: "1A1D21", lt1: "FFFFFF", dk2: "0B2545", lt2: "EEF3F7",
  accent1: "E4572E", accent2: "F2A541", accent3: "1B6A8C", accent4: "8DA9C4", accent5: "5C6B7A", accent6: "9E1B1B",
  hlink: "1B6A8C", folHlink: "5C6B7A",
};
const THEME = { name: "Hot Oceans", headFontFace: "Cambria", bodyFontFace: "Calibri", colors: T };
const HEAD = "+mj-lt";               // theme heading font (Cambria) for big numbers
const RULE_GREY = "8A96A3";          // persistence rule in charts
const W = 13.333, X0 = 0.6, CW = 12.133, XR = X0 + CW;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "Ananthanarayanan B";
pres.company = "Digital University Kerala";
pres.title = "Hot Oceans: marine heatwaves in the Indian Ocean";
const C = pres.SchemeColor;

// ---------------------------------------------------------------- icons
const iconCache = new Map();
async function icon(Comp, hex, size = 256) {
  const key = `${Comp.name}-${hex}`;
  if (!iconCache.has(key)) {
    const svg = renderToStaticMarkup(React.createElement(Comp, { color: `#${hex}`, size: String(size) }));
    const png = await sharp(Buffer.from(svg)).png().toBuffer();
    iconCache.set(key, "image/png;base64," + png.toString("base64"));
  }
  return iconCache.get(key);
}

// ---------------------------------------------------------------- layouts
const FOOTER = "Hot Oceans  |  Ananthanarayanan B (253318)  |  Spatial Big Data";
pres.defineSlideMaster({
  title: "TITLE_DARK", background: { color: T.dk2 },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 1.95, w: 5.0, h: 1.15, fontSize: 60, bold: true,
      color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "subtitle", type: "body", x: X0, y: 3.2, w: 5.25, h: 1.1, fontSize: 20,
      color: C.accent4, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "CONTENT", background: { color: T.lt1 },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: X0, y: 0.3, w: CW, h: 0.3, fontSize: 12, bold: true,
      color: C.accent1, charSpacing: 2, valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.6, w: CW, h: 0.75, fontSize: 36, bold: true,
      color: C.text2, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOTER, options: { x: X0, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.accent5, margin: 0, valign: "middle" } } },
  ],
  slideNumber: { x: XR - 0.6, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: T.accent5, align: "right" },
});
pres.defineSlideMaster({
  title: "DARK", background: { color: T.dk2 },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: X0, y: 0.3, w: CW, h: 0.3, fontSize: 12, bold: true,
      color: C.accent2, charSpacing: 2, valign: "middle", margin: 0 }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: X0, y: 0.6, w: CW, h: 0.75, fontSize: 36, bold: true,
      color: C.background1, valign: "middle", align: "left", margin: 0 }, text: "" } },
    { text: { text: FOOTER, options: { x: X0, y: 7.0, w: 8, h: 0.3, fontSize: 10, color: C.accent4, margin: 0, valign: "middle" } } },
  ],
  slideNumber: { x: XR - 0.6, y: 7.0, w: 0.6, h: 0.3, fontSize: 10, color: T.accent4, align: "right" },
});

// ---------------------------------------------------------------- helpers
const shadow = () => ({ type: "outer", color: "1A1D21", opacity: 0.14, blur: 8, offset: 2, angle: 90 });
let SECTION = "";
function section(title) { pres.addSection({ title }); SECTION = title; }
function contentSlide(kicker, title, master = "CONTENT") {
  const s = pres.addSlide({ masterName: master, sectionTitle: SECTION });
  s.addText(kicker, { placeholder: "kicker" });
  s.addText(title, { placeholder: "title" });
  return s;
}
function card(s, x, y, w, h, name, o = {}) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, objectName: name,
    fill: o.fill || { color: C.background2 }, line: { color: C.background2, width: 0, transparency: 100 },
    shadow: o.shadow ? shadow() : undefined });
}
async function iconCircle(s, Comp, x, y, d, fill, fg = T.lt1, name = "icon") {
  s.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill, width: 0, transparency: 100 }, objectName: `${name} circle` });
  const k = d * 0.52;
  s.addImage({ data: await icon(Comp, fg), x: x + (d - k) / 2, y: y + (d - k) / 2, w: k, h: k, altText: name, objectName: `${name} icon` });
}
function numCircle(s, n, x, y, d, fill = C.accent1, name = "step") {
  s.addText(String(n), { shape: pres.shapes.OVAL, x, y, w: d, h: d, fill: { color: fill }, line: { color: fill, width: 0, transparency: 100 },
    color: C.background1, bold: true, fontSize: Math.round(d * 30), align: "center", valign: "middle", margin: 0, objectName: `${name} number`, fontFace: HEAD });
}
function text(s, t, o) { s.addText(t, { isTextBox: true, margin: 0, valign: "top", color: C.text1, fontSize: 14, ...o }); }
function image(s, file, x, y, w, alt, name) {
  const b = fs.readFileSync(file); const iw = b.readUInt32BE(16), ih = b.readUInt32BE(20);
  const h = w * ih / iw;
  s.addImage({ path: file, x, y, w, h, altText: alt, objectName: name });
  return h;
}
function stat(s, x, y, w, big, label, o = {}) {
  text(s, big, { x, y, w, h: o.bigH || 0.75, fontSize: o.size || 40, bold: true, color: o.color || C.accent1, fontFace: HEAD, valign: "bottom", objectName: `${label} value` });
  text(s, label, { x, y: y + (o.bigH || 0.75) + 0.05, w, h: o.labelH || 0.6, fontSize: o.labelSize || 14, color: o.labelColor || C.text1, objectName: `${label} label` });
}
const chartBase = () => ({
  catAxisLabelColor: T.accent5, valAxisLabelColor: T.accent5, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  catAxisLabelFontSize: 12, valAxisLabelFontSize: 12, valGridLine: { color: "DDE3EA", size: 0.75 }, catGridLine: { style: "none" },
  catAxisLineShow: true, catAxisLineColor: "C9D1D9", valAxisLineShow: false,
  dataLabelFontFace: "+mn-lt", dataLabelFontSize: 12, dataLabelColor: T.dk1,
  showTitle: true, titleFontFace: "+mn-lt", titleFontSize: 14, titleColor: T.dk2,
  legendFontFace: "+mn-lt", legendFontSize: 12, legendColor: T.dk1,
});

// ---------------------------------------------------------------- data
const YEARS = [1982, 1983, 1984, 1985, 1986, 1987, 1988, 1989, 1990, 1991, 1992, 1993, 1994, 1995, 1996, 1997, 1998, 1999, 2000, 2001, 2002,
  2003, 2004, 2005, 2006, 2007, 2008, 2009, 2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025];
const MHW_DAYS = [11.5, 21.3, 6.6, 3.6, 2.7, 14.1, 16.9, 3.8, 6.6, 8.7, 5.2, 3.3, 4.7, 6.1, 6.5, 12.6, 43.8, 11.0, 8.7, 11.4, 17.3,
  12.0, 9.6, 19.5, 14.4, 14.7, 13.1, 21.5, 46.5, 24.5, 27.4, 19.6, 30.3, 66.9, 75.3, 28.9, 21.0, 61.9, 67.2, 34.4, 43.2, 78.7, 133.3, 61.3];
function linearTrend(x, y) {
  const n = x.length, mx = x.reduce((a, b) => a + b) / n, my = y.reduce((a, b) => a + b) / n;
  const b = x.reduce((a, xi, i) => a + (xi - mx) * (y[i] - my), 0) / x.reduce((a, xi) => a + (xi - mx) ** 2, 0);
  return { slope: b, fit: x.map((xi) => +(my + b * (xi - mx)).toFixed(2)) };
}
const TREND = linearTrend(YEARS, MHW_DAYS);
const PER_YEAR = { years: ["2019", "2020", "2021", "2022", "2023", "2024", "2025"],
  model: [0.614, 0.616, 0.539, 0.592, 0.661, 0.692, 0.603], rule: [0.578, 0.582, 0.511, 0.579, 0.647, 0.690, 0.591] };
const FEATURES = [["Neighbour heat, 7×7 box", 0.258, true], ["Neighbour heat, 8 cells", 0.173, true], ["Neighbour heat, 21×21 box", 0.137, true],
  ["Hottest neighbour, 7×7", 0.099, true], ["Days since above threshold", 0.067, false], ["Share above threshold, 21×21", 0.033, true],
  ["Own heat, 30-day mean", 0.032, false]];

// ================================================================ slides
async function build() {
  // ---------------------------------------------------------- 1. title
  section("Introduction");
  {
    const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: SECTION });
    s.addImage({ path: path.join(__dirname, "assets", "hero_2024.png"), x: W - 8.2, y: 1.0, w: 8.2, h: 8.2 / 1.5,
      altText: "Map of marine heatwave days per ocean cell in 2024 across the Indian Ocean", objectName: "Hero map 2024" });
    text(s, "SPATIAL BIG DATA  ·  COURSE PROJECT", { x: X0, y: 1.45, w: 5, h: 0.35, fontSize: 14, bold: true, color: C.accent2, charSpacing: 2, objectName: "Kicker" });
    s.addText("Hot Oceans", { placeholder: "title" });
    s.addText("Detecting, tracking and predicting marine heatwaves in the Indian Ocean, 1982–2025", { placeholder: "subtitle" });
    text(s, [
      { text: "Ananthanarayanan B", options: { bold: true, fontSize: 18, color: C.background1, breakLine: true } },
      { text: "Reg. No 253318  ·  M.Sc. Data Analytics and Geoinformatics", options: { fontSize: 14, color: C.background2, breakLine: true } },
      { text: "Supervisor: Manoj Kumar", options: { fontSize: 14, color: C.background2, breakLine: true } },
      { text: "School of Digital Sciences  ·  November 2026", options: { fontSize: 14, color: C.background2 } },
    ], { x: X0, y: 4.55, w: 4.9, h: 1.3, paraSpaceAfter: 3, objectName: "Presenter" });
    card(s, X0, 6.05, 2.1, 0.9, "Logo card", { fill: { color: C.background1 } });
    s.addImage({ path: path.join(ROOT, "report", "assets", "duk_logo.png"), x: X0 + 0.15, y: 6.05 + 0.1, w: 1.8, h: 1.8 * 127 / 296,
      altText: "Digital University Kerala logo", objectName: "DUK logo" });
    text(s, "Map: heatwave days per 0.25° cell in 2024, the record year (dark blue = few, pale yellow = 300+)",
      { x: W - 6.6, y: 6.75, w: 6.2, h: 0.3, fontSize: 10, color: C.accent4, align: "right", objectName: "Map caption" });
    s.addNotes("Good morning. My project is called Hot Oceans. I studied marine heatwaves in the Indian Ocean over 44 years, from 1982 to 2025, using big-data tools: Apache Spark, Apache Sedona, PostGIS and Spark MLlib. The map behind me is real output from my pipeline: it shows how many days each part of the ocean spent in a heatwave in 2024. Yellow means more than 300 days. My supervisor is Manoj Kumar Sir.");
  }

  // ---------------------------------------------------------- 2. at a glance
  {
    const s = contentSlide("OVERVIEW", "The project at a glance");
    text(s, "I turned 44 years of daily satellite temperatures into a catalogue of heatwaves and a seven-day warning, using Spark, Sedona and MLlib.",
      { x: X0, y: 1.5, w: CW, h: 0.7, fontSize: 18, italic: true, color: C.text2, objectName: "Lead" });
    const items = [
      [fa.FaDatabase, "937.5 M", "cell-days processed", "58,334 ocean cells × 16,071 days (1982–2025) on a 48-core DGX server", C.accent3, T.accent3],
      [fa.FaTemperatureArrowUp, "6×", "more heatwave days", "9.6 days a year in 1982–1991 → 60.5 in 2016–2025. 2024 set the record: 133 days", C.accent1, T.accent1],
      [fa.FaBell, "5 days", "early warning", "before the May 2023 Lakshadweep heatwave, from a model that never saw 2019–2025", C.text2, T.dk2],
    ];
    for (const [i, [Ic, big, label, detail, col, hex]] of items.entries()) {
      const x = X0 + i * 4.15, y = 2.45, w = 3.85;
      card(s, x, y, w, 4.1, `Card ${label}`, { shadow: true });
      await iconCircle(s, Ic, x + 0.3, y + 0.3, 0.75, hex, T.lt1, label);
      text(s, big, { x: x + 0.3, y: y + 1.2, w: w - 0.6, h: 0.95, fontSize: 54, bold: true, color: col, fontFace: HEAD, valign: "bottom", objectName: `${label} value` });
      text(s, label, { x: x + 0.3, y: y + 2.2, w: w - 0.6, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: `${label} label` });
      text(s, detail, { x: x + 0.3, y: y + 2.65, w: w - 0.6, h: 1.25, fontSize: 14, color: C.accent5, objectName: `${label} detail` });
    }
    s.addNotes("Here is the whole project on one slide. First, scale: I processed 937 and a half million daily records, one for every ocean cell on every day. Second, the main finding: an average spot in the Indian Ocean now spends about six times more days in a heatwave than in the 1980s. Third, prediction: my model warned five days before a real heatwave at Lakshadweep in May 2023. The rest of the talk explains how I got these numbers.");
  }

  // ---------------------------------------------------------- 3. what is an MHW
  {
    const s = contentSlide("INTRODUCTION", "What is a marine heatwave?");
    card(s, X0, 1.55, 5.6, 1.9, "Definition card");
    text(s, [
      { text: "A marine heatwave is when the sea surface stays hotter than its usual ‘hot’ level for that time of year (the 90th percentile) for ", options: { fontSize: 18 } },
      { text: "at least 5 days in a row.", options: { fontSize: 18, bold: true, color: C.accent1 } },
    ], { x: X0 + 0.3, y: 1.75, w: 5.0, h: 1.2, objectName: "Definition" });
    text(s, "Hobday et al. (2016)", { x: X0 + 0.3, y: 3.0, w: 5.0, h: 0.3, fontSize: 12, color: C.accent5, objectName: "Definition source" });
    text(s, "Why it matters", { x: X0, y: 3.7, w: 5.6, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "Why header" });
    const rows = [
      [gi.GiCoral, "Bleaches coral reefs: the 4th global bleaching event (2023–24) reached the Indian Ocean"],
      [gi.GiFishingBoat, "Hurts fish stocks and the coastal families who depend on them"],
      [fa.FaTemperatureArrowUp, "The tropical Indian Ocean is warming faster than the other tropical oceans"],
    ];
    for (const [i, [Ic, t]] of rows.entries()) {
      const y = 4.25 + i * 0.8;
      await iconCircle(s, Ic, X0, y, 0.6, T.accent1, T.lt1, `Why ${i + 1}`);
      text(s, t, { x: X0 + 0.8, y, w: 4.8, h: 0.6, fontSize: 14, valign: "middle", objectName: `Why ${i + 1} text` });
    }
    const h = image(s, FIG("fig03_detection.png"), 6.65, 1.75, 6.08, "Sea surface temperature at the Lakshadweep cell with the climatology, threshold and heatwave days", "Detection example");
    text(s, "Example from my data: the Lakshadweep cell, May 2023 – June 2024. The orange areas are heatwave days, when the water (black) stays above the blue threshold.",
      { x: 6.65, y: 1.75 + h + 0.12, w: 6.08, h: 0.55, fontSize: 12, color: C.accent5, objectName: "Detection caption" });
    s.addNotes("A marine heatwave is like a heatwave on land, but in the sea. The standard definition from Hobday and others in 2016 says: the sea surface must stay above its normal hot level, the 90th percentile for that time of year, for at least five days in a row. On the right is a real example from my data at Lakshadweep. The black line is the temperature, the blue dashed line is the hot level, and the orange parts are heatwave days. Heatwaves bleach corals, hurt fisheries, and the Indian Ocean is warming fast, so this matters for us.");
  }

  // ---------------------------------------------------------- 4. big data
  {
    const s = contentSlide("INTRODUCTION", "Why this is a big-data problem");
    stat(s, X0, 1.55, 2.5, "58,334", "ocean cells (0.25°, about 28 km)", { color: C.text2, size: 36, labelH: 0.5 });
    text(s, "×", { x: X0 + 2.55, y: 1.65, w: 0.5, h: 0.7, fontSize: 32, color: C.accent5, align: "center", valign: "middle", objectName: "Times" });
    stat(s, X0 + 3.1, 1.55, 2.5, "16,071", "days (1982–2025)", { color: C.text2, size: 36, labelH: 0.5 });
    s.addText([
      { text: "= 937.5 million ", options: { fontSize: 32, bold: true, fontFace: HEAD } },
      { text: "cell-days", options: { fontSize: 20 } },
    ], { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.08, x: X0, y: 3.0, w: 5.6, h: 0.95, fill: { color: C.accent1 },
      line: { color: C.accent1, width: 0, transparency: 100 }, color: C.background1, margin: 12, valign: "middle", objectName: "Total" });
    const rows = [
      [fa.FaLayerGroup, "A 30-year ‘normal’ for every cell and every day of the year"],
      [fa.FaShapes, "Grouping hot cells into patches, every single day"],
      [fa.FaRoute, "Following each patch from one day to the next"],
    ];
    text(s, "Each record needs three kinds of work:", { x: X0, y: 4.25, w: 5.6, h: 0.4, fontSize: 16, bold: true, color: C.text2, objectName: "Work header" });
    for (const [i, [Ic, t]] of rows.entries()) {
      const y = 4.8 + i * 0.68;
      await iconCircle(s, Ic, X0, y, 0.52, T.accent3, T.lt1, `Work ${i + 1}`);
      text(s, t, { x: X0 + 0.72, y, w: 4.9, h: 0.52, fontSize: 14, valign: "middle", objectName: `Work ${i + 1} text` });
    }
    const h = image(s, FIG("fig01_study_area.png"), 6.65, 1.55, 6.08, "Map of the Indian Ocean study box with sectors, sample box and case-study cell", "Study area");
    text(s, "Study box 30°S–30°N, 30°E–120°E, with the six sectors, the small laptop sample box and the Lakshadweep case-study cell.",
      { x: 6.65, y: 1.55 + h + 0.12, w: 6.08, h: 0.55, fontSize: 12, color: C.accent5, objectName: "Study caption" });
    s.addNotes("Why do we need big-data tools? My study box covers the Indian Ocean from 30 degrees south to 30 degrees north. Satellites give one temperature for every 0.25-degree square, which I call a cell. There are 58,334 ocean cells and 16,071 days, so 937 and a half million rows. For every row I need a 30-year normal, every day the hot cells must be grouped into patches, and the patches must be followed through time. A normal desktop GIS cannot do this in a reasonable time.");
  }

  // ---------------------------------------------------------- 5. objectives
  {
    const s = contentSlide("INTRODUCTION", "Aim and objectives");
    text(s, [
      { text: "Aim: ", options: { bold: true, color: C.accent1 } },
      { text: "one scalable pipeline, from raw satellite data to a heatwave catalogue and a seven-day warning." },
    ], { x: X0, y: 1.5, w: CW, h: 0.5, fontSize: 18, color: C.text2, objectName: "Aim" });
    const obj = [
      [fa.FaDatabase, "Clean data lake", "Partitioned Parquet lake with automatic quality checks"],
      [fa.FaMagnifyingGlass, "Detect", "Find and grade heatwaves in every cell (Hobday method)"],
      [fa.FaRoute, "Track", "Outline and follow heatwave events with Sedona spatial SQL"],
      [fa.FaGlobe, "Explain", "Relate events to season, region and the IOD and ENSO climate modes"],
      [fa.FaBell, "Predict", "Seven-day warning with Spark MLlib, tested for trust"],
      [fa.FaMapLocationDot, "Share", "PostGIS database and an interactive dashboard"],
    ];
    for (const [i, [Ic, t, d]] of obj.entries()) {
      const x = X0 + (i % 3) * 4.15, y = 2.3 + Math.floor(i / 3) * 2.25, w = 3.85;
      card(s, x, y, w, 2.0, `Objective ${i + 1}`, { shadow: true });
      await iconCircle(s, Ic, x + 0.3, y + 0.3, 0.65, i === 4 ? T.accent1 : T.accent3, T.lt1, `Objective ${i + 1}`);
      text(s, [{ text: `0${i + 1}  `, options: { color: C.accent1, bold: true } }, { text: t, options: { bold: true, color: C.text2 } }],
        { x: x + 1.15, y: y + 0.3, w: w - 1.4, h: 0.65, fontSize: 18, valign: "middle", objectName: `Objective ${i + 1} title` });
      text(s, d, { x: x + 0.3, y: y + 1.1, w: w - 0.6, h: 0.8, fontSize: 14, color: C.accent5, objectName: `Objective ${i + 1} text` });
    }
    s.addNotes("My aim was to build one pipeline that goes all the way from raw satellite files to useful answers. It has six objectives: build a clean data lake, detect heatwaves in every cell, track heatwave events through space and time with Sedona, explain them using season, region and climate modes like the Indian Ocean Dipole and El Niño, predict them a week ahead with machine learning, and share everything through PostGIS and a dashboard.");
  }

  // ---------------------------------------------------------- 6. architecture
  section("Methodology");
  {
    const s = contentSlide("METHODOLOGY", "Seven stages, from raw files to answers");
    image(s, FIG("fig02_architecture.png"), X0, 1.5, 6.6, "Architecture diagram of stages A to G on the DGX and the PC", "Architecture");
    const cards = [
      [fa.FaSatellite, "Data", ["NOAA OISST v2.1: daily SST, 0.25°, 1.6 GB NetCDF", "MEOW ecoregions: 232 polygons", "DMI (IOD) and ONI (ENSO) monthly indices"]],
      [fa.FaGears, "Tools", ["Apache Spark 3.5 · Apache Sedona 1.6 · MLlib", "PostgreSQL 13 + PostGIS 3.4", "Streamlit + pydeck dashboard"]],
      [fa.FaServer, "Compute", ["Built and tested on my laptop with a small sample box", "Full run on the NVIDIA DGX: 48 cores, 200 GB", "Switching between them = one setting"]],
    ];
    for (const [i, [Ic, head, lines]] of cards.entries()) {
      const x = 7.55, y = 1.5 + i * 1.75, w = XR - 7.55;
      card(s, x, y, w, 1.6, `${head} card`);
      await iconCircle(s, Ic, x + 0.25, y + 0.22, 0.5, T.accent3, T.lt1, head);
      text(s, head, { x: x + 0.9, y: y + 0.22, w: w - 1.1, h: 0.5, fontSize: 18, bold: true, color: C.text2, valign: "middle", objectName: `${head} header` });
      text(s, lines.map((l, j) => ({ text: l, options: { bullet: { indent: 14 }, breakLine: j < lines.length - 1 } })),
        { x: x + 0.25, y: y + 0.78, w: w - 0.45, h: 0.78, fontSize: 14, paraSpaceAfter: 2, objectName: `${head} list` });
    }
    s.addNotes("This is the architecture. The heavy work runs on the university's DGX server in seven stages, A to G: ingest and clean, detect, build events, find regimes and rules, the warning model, the case study, and export. Only small results come back to my PC for PostGIS, the dashboard and the report. I used four free datasets: NOAA satellite temperatures, marine ecoregion polygons and two climate indices. I developed everything on my laptop first, with a small sample, and then ran the full ocean on the DGX by changing one setting.");
  }

  // ---------------------------------------------------------- 7. stage A
  {
    const s = contentSlide("METHODOLOGY  ·  STAGE A", "Building a clean data lake");
    const steps = [
      ["Download month by month", "OPeNDAP from NOAA PSL, 44 years of NetCDF"],
      ["One row per cell per day", "Each cell gets a fixed key: cell_id = row × 1440 + col"],
      ["Parquet in 64 buckets", "cell_id mod 64 keeps each cell’s 44 years in one partition"],
    ];
    for (const [i, [t, d]] of steps.entries()) {
      const y = 1.65 + i * 1.3;
      numCircle(s, i + 1, X0, y, 0.62, C.accent3, `Step ${i + 1}`);
      text(s, [{ text: t, options: { bold: true, fontSize: 18, color: C.text2, breakLine: true } }, { text: d, options: { fontSize: 14, color: C.accent5 } }],
        { x: X0 + 0.85, y: y - 0.02, w: 5.1, h: 1.0, objectName: `Step ${i + 1} text` });
    }
    await iconCircle(s, fa.FaDrawPolygon, X0, 5.6, 0.62, T.accent2, T.dk2, "Ecoregion join");
    text(s, [{ text: "Then: ", options: { bold: true } }, { text: "each cell is tagged with its marine ecoregion by a Sedona point-in-polygon join (ST_Contains)." }],
      { x: X0 + 0.85, y: 5.6, w: 5.1, h: 0.75, fontSize: 14, valign: "middle", objectName: "Ecoregion text" });
    card(s, 6.85, 1.55, XR - 6.85, 5.1, "QC card");
    text(s, "Quality control caught a silent error", { x: 7.15, y: 1.75, w: 5.3, h: 0.45, fontSize: 20, bold: true, color: C.text2, objectName: "QC header" });
    const qc = [
      ["162 days", "came back half-filled from parallel downloads, with no error message", C.accent1],
      ["58,334", "valid cells every day, between −2 and 40 °C: an automatic check, because the land mask never changes", C.accent3],
      ["0 gaps", "after re-downloading: 937,485,714 rows, no duplicates", C.accent3],
    ];
    for (const [i, [big, d, col]] of qc.entries()) {
      const y = 2.45 + i * 1.35;
      text(s, big, { x: 7.15, y, w: 2.3, h: 1.0, fontSize: 36, bold: true, color: col, fontFace: HEAD, valign: "middle", objectName: `QC ${i + 1} value` });
      text(s, d, { x: 9.55, y, w: 2.95, h: 1.0, fontSize: 14, valign: "middle", objectName: `QC ${i + 1} text` });
    }
    s.addNotes("Stage A builds the data lake. I downloaded the data month by month and turned it into a long table, one row per cell per day. The table is stored as Parquet in 64 buckets so that each cell's full history sits together. The most important part was quality control. When I downloaded in parallel, 162 days came back half empty, without any error. I noticed that every complete day must have exactly 58,334 ocean cells, so I made that an automatic check. It caught every bad day, and after re-downloading the final lake has no gaps.");
  }

  // ---------------------------------------------------------- 8. stage B
  {
    const s = contentSlide("METHODOLOGY  ·  STAGE B", "Detecting heatwaves in every cell");
    const steps = [
      ["Normal and hot levels", "For each cell and day of year, from 1991–2020: the mean (climatology) and the 90th percentile (threshold)"],
      ["Heatwave = 5+ days above the threshold", "Short breaks of up to 2 days are joined"],
      ["Grade by intensity", "R = (SST − climatology) / (threshold − climatology)"],
    ];
    for (const [i, [t, d]] of steps.entries()) {
      const y = 1.55 + i * 1.1;
      numCircle(s, i + 1, X0, y, 0.55, C.accent1, `Detect ${i + 1}`);
      text(s, [{ text: t, options: { bold: true, fontSize: 16, color: C.text2, breakLine: true } }, { text: d, options: { fontSize: 14, color: C.accent5 } }],
        { x: X0 + 0.75, y: y - 0.03, w: 5.3, h: 1.0, objectName: `Detect ${i + 1} text` });
    }
    const cats = [["Moderate", "1 ≤ R < 2", "E08C1E"], ["Strong", "2 ≤ R < 3", "D0531F"], ["Severe", "3 ≤ R < 4", "A8221E"], ["Extreme", "R ≥ 4", "5C0F10"]];
    for (const [i, [n, r, hex]] of cats.entries()) {
      s.addText([{ text: n, options: { bold: true, fontSize: 14, breakLine: true } }, { text: r, options: { fontSize: 12 } }],
        { shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.06, x: X0 + i * 1.5, y: 4.95, w: 1.38, h: 0.75, fill: { color: hex },
          line: { color: hex, width: 0, transparency: 100 }, color: C.background1, align: "center", valign: "middle", margin: 0, objectName: `Category ${n}` });
    }
    text(s, [{ text: "In Spark: ", options: { bold: true } }, { text: "groupBy(cell_id).applyInPandas ran all 58,334 cells on 48 cores in 3.3 minutes." }],
      { x: X0, y: 5.95, w: 5.95, h: 0.7, fontSize: 14, objectName: "Spark note" });
    const h = image(s, FIG("fig07_snapshot_2024-02-06.png"), 6.85, 1.55, XR - 6.85, "Map of heatwave categories on 6 February 2024", "Category map");
    text(s, "Output for a single day: 6 February 2024, when 55.6% of the ocean area was in a heatwave.",
      { x: 6.85, y: 1.55 + h + 0.12, w: XR - 6.85, h: 0.5, fontSize: 12, color: C.accent5, objectName: "Category caption" });
    s.addNotes("Stage B detects heatwaves. For every cell and every day of the year, I calculate the normal temperature and the hot level, the 90th percentile, using 1991 to 2020 as the baseline. If the water stays above the hot level for five days or more, it is a heatwave. Then I grade each day as moderate, strong, severe or extreme depending on how far above normal it is. In Spark I grouped the data by cell, so 48 cores worked on different cells at the same time. All 58 thousand cells took only 3.3 minutes. The map shows the result for one day in February 2024.");
  }

  // ---------------------------------------------------------- 9. stages C–D
  {
    const s = contentSlide("METHODOLOGY  ·  STAGES C–D", "Tracking heatwave events with Sedona");
    const flow = [
      ["Cluster hot cells", "DBSCAN every day (radius 1.5 cells, at least 4 cells)"],
      ["Draw footprints", "ST_Union_Aggr → ST_ConvexHull → ST_Buffer"],
      ["Link day to day", "ST_Intersects spatial self-join"],
      ["Build events", "Union-find; chains lasting 5+ days"],
    ];
    for (const [i, [t, d]] of flow.entries()) {
      const x = X0 + i * 3.1, w = 2.85;
      card(s, x, 1.55, w, 1.45, `Flow ${i + 1}`);
      text(s, [{ text: `${i + 1}  `, options: { color: C.accent1, bold: true } }, { text: t, options: { bold: true, color: C.text2, breakLine: true } },
        { text: d, options: { fontSize: 13, color: C.accent5 } }], { x: x + 0.2, y: 1.7, w: w - 0.4, h: 1.2, fontSize: 16, objectName: `Flow ${i + 1} text` });
      if (i < 3) s.addShape(pres.shapes.CHEVRON, { x: x + w + 0.05, y: 2.12, w: 0.15, h: 0.3, fill: { color: C.accent1 }, line: { color: C.accent1, width: 0, transparency: 100 }, objectName: `Arrow ${i + 1}` });
    }
    image(s, FIG("fig10_event_track.png"), X0, 3.25, 5.3, "Footprints and centroid track of one 37-day heatwave event in November–December 2022", "Event track");
    const tiles = [["291,272", "daily footprints"], ["14,472", "heatwave events"], ["7 days", "median event length"], ["560", "events lasting 30+ days"]];
    for (const [i, [big, label]] of tiles.entries()) {
      const x = 6.3 + (i % 2) * 3.27, y = 3.25 + Math.floor(i / 2) * 1.4;
      card(s, x, y, 3.07, 1.25, `Tile ${label}`);
      stat(s, x + 0.25, y + 0.1, 2.6, big, label, { size: 32, bigH: 0.65, labelH: 0.35, color: i === 1 ? C.accent1 : C.text2 });
    }
    text(s, "K-Means found 3 event types (short-mild, short-intense, long-large). The strongest FP-Growth rule had a lift of only 1.21, so season and climate phase alone say little about how strong an event will be.",
      { x: 6.3, y: 6.1, w: XR - 6.3, h: 0.7, fontSize: 13, color: C.accent5, objectName: "Regimes note" });
    s.addNotes("A heatwave covers a big area and moves, so Stages C and D follow it. Every day I cluster neighbouring hot cells with DBSCAN. Sedona then draws an outline, called a footprint, around each cluster. Footprints that overlap from one day to the next are linked with a spatial join, and chains of five days or more become events. The picture shows one event in 2022 that lasted 37 days and drifted south-west. In total I found 14,472 events. Most are short, about a week, but 560 lasted more than a month.");
  }

  // ---------------------------------------------------------- 10. stage E
  {
    const s = contentSlide("METHODOLOGY  ·  STAGE E", "A seven-day heatwave warning");
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: X0, y: 1.5, w: CW, h: 0.9, rectRadius: 0.08, fill: { color: C.text2 }, line: { color: C.text2, width: 0, transparency: 100 }, objectName: "Question band" });
    await iconCircle(s, fa.FaBell, X0 + 0.25, 1.65, 0.6, T.accent2, T.dk2, "Question");
    text(s, "The question: if this cell is not in a heatwave yet, will it be in one within the next 7 days?",
      { x: X0 + 1.05, y: 1.5, w: CW - 1.3, h: 0.9, fontSize: 20, italic: true, color: C.background1, valign: "middle", objectName: "Question" });
    text(s, "23 features, all known on the forecast day", { x: X0, y: 2.6, w: 6.2, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "Features header" });
    for (let r = 0; r < 7; r++) for (let c = 0; c < 7; c++) {
      const ring = Math.max(Math.abs(r - 3), Math.abs(c - 3));
      const col = ring === 0 ? C.accent1 : ring === 1 ? C.accent2 : C.accent4;
      s.addShape(pres.shapes.RECTANGLE, { x: X0 + c * 0.29, y: 3.15 + r * 0.29, w: 0.25, h: 0.25, fill: { color: col, transparency: ring > 1 ? 45 : 0 },
        line: { color: col, width: 0, transparency: 100 }, objectName: `Grid ${r}-${c}` });
    }
    text(s, "the cell, its 8 neighbours and the 7 × 7 box", { x: X0, y: 5.2, w: 2.1, h: 0.45, fontSize: 11, color: C.accent5, objectName: "Grid caption" });
    text(s, [
      { text: "Own cell: ", options: { bold: true, color: C.accent1 } }, { text: "heat today, 7- and 30-day means, trend, days above the threshold", options: { breakLine: true } },
      { text: "Neighbours: ", options: { bold: true, color: C.accent2 } }, { text: "8 cells, 7 × 7 and 21 × 21 boxes (mean, max, share above)", options: { breakLine: true } },
      { text: "Left out on purpose: ", options: { bold: true, color: C.accent5 } }, { text: "latitude, longitude, season, climate indices" },
    ], { x: 2.85, y: 3.1, w: 3.95, h: 2.4, fontSize: 14, paraSpaceAfter: 8, objectName: "Feature list" });
    card(s, 7.1, 2.6, XR - 7.1, 2.9, "Models card");
    text(s, "Models and score", { x: 7.35, y: 2.75, w: 5.1, h: 0.4, fontSize: 18, bold: true, color: C.text2, objectName: "Models header" });
    text(s, [
      { text: "Gradient-Boosted Trees (GBT) and Random Forest in Spark MLlib", options: { bullet: { indent: 14 }, breakLine: true } },
      { text: "Baseline to beat: persistence rule, ‘the hotter today, the higher the risk’", options: { bullet: { indent: 14 }, breakLine: true } },
      { text: "Main score: PR-AUC, because only 13.9% of rows become heatwaves and accuracy would mislead", options: { bullet: { indent: 14 } } },
    ], { x: 7.35, y: 3.25, w: 5.15, h: 2.2, fontSize: 14, paraSpaceAfter: 6, objectName: "Models list" });
    const segs = [["Train  ·  1982–2014", 33, C.accent3], ["Tune\n2015–18", 4, C.accent2], ["Test\n2019–25", 7, C.accent1]];
    let x = X0;
    for (const [t, yrs, col] of segs) {
      const w = CW * yrs / 44;
      s.addText(t, { shape: pres.shapes.RECTANGLE, x, y: 5.75, w: w - 0.04, h: 0.65, fill: { color: col }, line: { color: col, width: 0, transparency: 100 },
        color: col === C.accent2 ? C.text2 : C.background1, bold: true, fontSize: 12, align: "center", valign: "middle", margin: 0, objectName: `Split ${t}` });
      x += w;
    }
    text(s, "Split by time, like a real forecast. The test years (32.1 million rows) were never used for training or tuning.",
      { x: X0, y: 6.45, w: CW, h: 0.35, fontSize: 12, color: C.accent5, objectName: "Split caption" });
    s.addNotes("Stage E is the warning model. It answers one practical question: if a place is not in a heatwave yet, will it be in one within the next seven days? The model gets 23 features. Some describe the cell itself, like how hot it is today. Others describe the neighbouring water: the 8 cells around it and bigger boxes of 7 by 7 and 21 by 21 cells. I trained Gradient-Boosted Trees and a Random Forest in Spark MLlib and compared them with a simple rule: the hotter the water today, the higher the risk. I split the data by time: train up to 2014, tune on 2015 to 2018, and test only on 2019 to 2025.");
  }

  // ---------------------------------------------------------- 11. leakage
  {
    const s = contentSlide("METHODOLOGY  ·  STAGE E", "A mistake I caught: look-ahead leakage");
    const cols = [
      [fa.FaTriangleExclamation, "Before", T.accent1, C.accent1, [
        "Some features used the final heatwave flag",
        "That flag needs up to 4 future days to be confirmed",
        "So the model was quietly peeking into the future, and its scores looked too good"]],
      [fa.FaCircleCheck, "After", T.accent3, C.accent3, [
        "Features rebuilt from past data only",
        "Leakage audit: cut the data at day t, recompute everything, compare",
        "6,000 cell-days × 16 inputs → 0 mismatches",
        "A unit test now repeats the check every time"]],
    ];
    for (const [i, [Ic, head, hex, col, lines]] of cols.entries()) {
      const x = X0 + i * 6.23, w = 5.9;
      card(s, x, 1.55, w, 3.95, `${head} card`, { fill: { color: col, transparency: 90 } });
      await iconCircle(s, Ic, x + 0.35, 1.85, 0.65, hex, T.lt1, head);
      text(s, head, { x: x + 1.2, y: 1.85, w: 3, h: 0.65, fontSize: 24, bold: true, color: col, fontFace: HEAD, valign: "middle", objectName: `${head} header` });
      text(s, lines.map((l, j) => ({ text: l, options: { bullet: { indent: 16 }, breakLine: j < lines.length - 1 } })),
        { x: x + 0.35, y: 2.8, w: w - 0.7, h: 2.55, fontSize: 16, paraSpaceAfter: 8, objectName: `${head} list` });
    }
    s.addShape(pres.shapes.CHEVRON, { x: X0 + 5.95, y: 3.3, w: 0.2, h: 0.45, fill: { color: C.accent5 }, line: { color: C.accent5, width: 0, transparency: 100 }, objectName: "Before-after arrow" });
    card(s, X0, 5.75, CW, 0.95, "Lesson card", { fill: { color: C.text2 } });
    await iconCircle(s, fa.FaLightbulb, X0 + 0.25, 5.9, 0.65, T.accent2, T.dk2, "Lesson");
    text(s, "Lesson: the honest scores were lower, and they are the only scores I report.",
      { x: X0 + 1.1, y: 5.75, w: CW - 1.3, h: 0.95, fontSize: 20, italic: true, color: C.background1, valign: "middle", objectName: "Lesson text" });
    s.addNotes("I want to share one mistake I made, because I learned a lot from it. My first model scored surprisingly well. When I checked carefully, I found that some features used the final heatwave flag. But that flag can only be known a few days later, because a heatwave needs five days to be confirmed. So the model was secretly looking into the future. This is called look-ahead leakage. I rebuilt the features using only past data and wrote an audit that recomputes everything with the data cut off at the forecast day. It found zero mismatches. The honest scores were lower, and those are the only ones I report.");
  }

  // ---------------------------------------------------------- 12. trend
  section("Results");
  {
    const s = contentSlide("RESULTS", "Heatwave days have grown six-fold");
    s.addChart([
      { type: pres.charts.BAR, data: [{ name: "Mean heatwave days per ocean cell", labels: YEARS.map(String), values: MHW_DAYS }],
        options: { barDir: "col", chartColors: [T.accent1], barGapWidthPct: 35 } },
      { type: pres.charts.LINE, data: [{ name: `Linear trend (+${(TREND.slope * 10).toFixed(1)} days per decade)`, labels: YEARS.map(String), values: TREND.fit }],
        options: { chartColors: [T.dk2], lineSize: 2, lineDataSymbol: "none", lineDash: "dash" } },
    ], { x: X0, y: 1.5, w: 8.3, h: 5.1, ...chartBase(), title: "Average heatwave days per ocean cell, 1982–2025", showLegend: true, legendPos: "t",
      catAxisLabelFrequency: 4, valAxisMinVal: 0, valAxisMaxVal: 140, valAxisMajorUnit: 20, objectName: "Trend chart",
      altText: "Column chart of mean heatwave days per cell per year from 1982 to 2025 with a rising linear trend" });
    const stats = [
      ["9.6 → 60.5", "heatwave days a year, 1982–91 vs 2016–25", C.accent1],
      [`+${(TREND.slope * 10).toFixed(1)}`, "days per decade (linear trend)", C.text2],
      ["133 days", "in 2024, the record: over a third of the year", C.accent1],
    ];
    for (const [i, [big, label, col]] of stats.entries()) stat(s, 9.25, 1.6 + i * 1.6, XR - 9.25, big, label, { size: 36, color: col, labelH: 0.6 });
    text(s, "Peaks match strong El Niño and positive IOD years: 1998, 2010, 2016, 2023–24.",
      { x: 9.25, y: 6.05, w: XR - 9.25, h: 0.6, fontSize: 12, color: C.accent5, objectName: "Peaks note" });
    s.addNotes("Now the results. This chart is the clearest finding of the project. In the 1980s, an average ocean cell spent about 10 days a year in a heatwave. In the last ten years it was about 60 days, more than six times as many. The dashed line shows the trend: about 15 more heatwave days every decade. The tall bars are El Niño and positive Indian Ocean Dipole years. 2024 was the record, with 133 days, more than a third of the year.");
  }

  // ---------------------------------------------------------- 13. 2024
  {
    const s = contentSlide("RESULTS", "2024: the record year");
    const h = image(s, FIG("fig06_days_2023_2024.png"), X0, 1.55, 8.3, "Maps of heatwave days per cell in 2023 and 2024", "Days 2023 2024");
    text(s, "Heatwave days in each 0.25° cell: 2023 (left) and 2024 (right). Darker = more days.",
      { x: X0, y: 1.55 + h + 0.12, w: 8.3, h: 0.4, fontSize: 12, color: C.accent5, objectName: "Days caption" });
    const tiles = [["55.6%", "of the ocean area was in a heatwave on 6 February 2024", C.accent1],
      ["173 days", "in the Bay of Bengal in 2024", C.text2], ["165 days", "in the Arabian Sea in 2024", C.text2]];
    for (const [i, [big, label, col]] of tiles.entries()) {
      const y = 1.55 + i * 1.72;
      card(s, 9.25, y, XR - 9.25, 1.55, `Tile ${big}`);
      stat(s, 9.5, y + 0.12, XR - 9.75, big, label, { size: 36, color: col, bigH: 0.7, labelH: 0.6 });
    }
    s.addNotes("These two maps compare 2023 and 2024. In 2024 almost the whole basin turned dark, which means many heatwave days everywhere. On one day, the 6th of February 2024, more than half of the ocean area was in a heatwave at the same time. The Bay of Bengal had 173 heatwave days and the Arabian Sea 165, the two hardest-hit sectors close to India.");
  }

  // ---------------------------------------------------------- 14. model results
  {
    const s = contentSlide("RESULTS", "The model beats the simple rule");
    s.addChart(pres.charts.BAR, [{ name: "PR-AUC", labels: ["Random guess", "Persistence rule", "Random Forest", "GBT (chosen)"], values: [0.139, 0.598, 0.625, 0.625] }],
      { x: X0, y: 1.5, w: 5.8, h: 4.3, ...chartBase(), barDir: "col", chartColors: ["C9D1D9", RULE_GREY, T.accent3, T.accent1], barGapWidthPct: 45,
        title: "PR-AUC on the test years 2019–2025 (higher is better)", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.000",
        valAxisMinVal: 0, valAxisMaxVal: 0.7, valAxisMajorUnit: 0.1, valAxisLabelFormatCode: "0.0", showLegend: false, objectName: "Score chart",
        altText: "Column chart: random guess 0.139, persistence rule 0.598, random forest 0.625, GBT 0.625" });
    s.addChart(pres.charts.BAR, [{ name: "Importance", labels: FEATURES.map((f) => f[0]), values: FEATURES.map((f) => f[1]) }],
      { x: 6.75, y: 1.5, w: XR - 6.75, h: 4.3, ...chartBase(), barDir: "bar", chartColors: FEATURES.map((f) => (f[2] ? T.accent1 : RULE_GREY)), barGapWidthPct: 40,
        title: "What the GBT relies on most (orange = neighbours)", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.00",
        catAxisOrientation: "maxMin", valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 0.3, valGridLine: { style: "none" }, showLegend: false,
        objectName: "Feature chart", altText: "Bar chart of feature importance; the top four features all describe neighbouring water" });
    card(s, X0, 6.0, CW, 0.75, "Accuracy note");
    text(s, [{ text: "Why not accuracy? ", options: { bold: true, color: C.accent1 } },
      { text: "Always answering ‘no heatwave’ is already 86% accurate; the model and the rule both score about 88%. PR-AUC shows the real difference." }],
      { x: X0 + 0.25, y: 6.0, w: CW - 0.5, h: 0.75, fontSize: 14, valign: "middle", objectName: "Accuracy text" });
    s.addNotes("On the test years 2019 to 2025, both machine-learning models beat the simple rule. GBT and Random Forest reach a PR-AUC of 0.625, against 0.598 for the rule and 0.139 for a random guess. I chose GBT because it was best on the tuning years. I do not use accuracy, because only 14 percent of cases become heatwaves: a lazy model that always says no is already 86 percent accurate. On the right you can see what the model relies on: the top four features all describe the neighbouring water. Heatwaves spread into a place from warm water nearby, and that is a spatial signal.");
  }

  // ---------------------------------------------------------- 15. trust
  {
    const s = contentSlide("RESULTS", "Can the warning be trusted?");
    s.addChart(pres.charts.BAR, [
      { name: "Persistence rule", labels: PER_YEAR.years, values: PER_YEAR.rule },
      { name: "GBT model", labels: PER_YEAR.years, values: PER_YEAR.model },
    ], { x: X0, y: 1.5, w: 6.4, h: 4.6, ...chartBase(), barDir: "col", barGrouping: "clustered", chartColors: [RULE_GREY, T.accent1], barGapWidthPct: 60,
      title: "PR-AUC in each test year", showLegend: true, legendPos: "t", valAxisMinVal: 0.4, valAxisMaxVal: 0.75, valAxisMajorUnit: 0.05,
      valAxisLabelFormatCode: "0.00", objectName: "Per-year chart", altText: "Clustered columns: the GBT model beats the persistence rule in every year from 2019 to 2025" });
    const tiles = [
      ["7 / 7", "test years won"], ["49 / 51", "regions won"],
      ["+0.022 to +0.032", "PR-AUC gain, 95% bootstrap interval"], ["0.606", "on regions never seen (spatial CV)"],
      ["3.0% → 0.9%", "calibration error after isotonic fix"], ["48% vs 44%", "onsets warned 3+ days ahead (model vs rule)"],
    ];
    for (const [i, [big, label]] of tiles.entries()) {
      const x = 7.3 + (i % 2) * 2.77, y = 1.5 + Math.floor(i / 2) * 1.57;
      card(s, x, y, 2.6, 1.42, `Tile ${label}`);
      stat(s, x + 0.2, y + 0.1, 2.25, big, label, { size: big.length > 10 ? 20 : 28, bigH: 0.6, labelH: 0.6, labelSize: 12, color: i % 2 ? C.text2 : C.accent1 });
    }
    text(s, "Honest reading: the gain is small but it holds everywhere. Most of the skill comes from the water already being warm.",
      { x: X0, y: 6.3, w: CW, h: 0.45, fontSize: 14, italic: true, color: C.text2, objectName: "Trust note" });
    s.addNotes("One good score is not enough, so I tested the model in five more ways. It beat the rule in all seven test years and in 49 of 51 regions. A bootstrap with 1,000 resamples shows the gain is real: between plus 0.022 and plus 0.032. On regions it never saw in training it still scored 0.606, so it is not memorising places. After calibration, a 30 percent risk really means about 30 percent. And it gives earlier warnings: 48 percent of heatwaves were warned at least three days ahead, against 44 percent for the rule. To be honest, the gain is small, but it is consistent.");
  }

  // ---------------------------------------------------------- 16. Lakshadweep
  {
    const s = contentSlide("RESULTS", "Lakshadweep 2023: warned five days ahead");
    const h = image(s, FIG("fig13_case_warning.png"), X0, 1.5, 8.3, "Model risk score before the 12 May 2023 heatwave at Lakshadweep, crossing the warning threshold on 7 May", "Case warning");
    card(s, X0, 1.5 + h + 0.25, 8.3, 1.25, "Lead card", { fill: { color: C.accent1, transparency: 88 } });
    text(s, "5 days", { x: X0 + 0.3, y: 1.5 + h + 0.25, w: 2.3, h: 1.25, fontSize: 44, bold: true, color: C.accent1, fontFace: HEAD, valign: "middle", objectName: "Lead value" });
    text(s, "of warning, for a heatwave in a test year the model had never seen", { x: X0 + 2.6, y: 1.5 + h + 0.25, w: 5.4, h: 1.25, fontSize: 18, color: C.text2, valign: "middle", objectName: "Lead text" });
    const tl = [["7 May", "Risk crosses the warning threshold (0.23): first warning", C.accent2],
      ["8 May", "Risk peaks at 0.40", C.accent2], ["12 May", "Heatwave begins", C.accent1],
      ["Next year", "330 of the following 427 days were in a heatwave", C.accent6]];
    s.addShape(pres.shapes.LINE, { x: 9.45, y: 1.85, w: 0, h: 3.9, line: { color: C.accent4, width: 2 }, objectName: "Timeline line" });
    for (const [i, [d, t, col]] of tl.entries()) {
      const y = 1.65 + i * 1.3;
      s.addShape(pres.shapes.OVAL, { x: 9.3, y: y + 0.05, w: 0.3, h: 0.3, fill: { color: col }, line: { color: C.background1, width: 2 }, objectName: `Timeline dot ${i + 1}` });
      text(s, [{ text: d, options: { bold: true, fontSize: 18, color: C.text2, breakLine: true } }, { text: t, options: { fontSize: 14 } }],
        { x: 9.85, y, w: XR - 9.85, h: 1.15, objectName: `Timeline ${i + 1}` });
    }
    s.addNotes("This is a real test on a place close to home: the Kavaratti cell in Lakshadweep. The heatwave began on the 12th of May 2023. My model's risk crossed the warning line on the 7th of May, five days earlier, and 2023 was a test year that the model had never seen. After that, the cell stayed in a heatwave for most of the following year: 330 out of 427 days.");
  }

  // ---------------------------------------------------------- 17. dashboard
  {
    const s = contentSlide("RESULTS  ·  STAGE G", "Sharing the results: PostGIS and a dashboard");
    image(s, FIG("fig14c_dashboard_map.png"), X0, 1.5, 7.4, "Screenshot of the Hot Oceans Streamlit dashboard showing the daily heatwave map", "Dashboard screenshot");
    text(s, "Six dashboard tabs (Streamlit + pydeck)", { x: 8.35, y: 1.5, w: XR - 8.35, h: 0.45, fontSize: 18, bold: true, color: C.text2, objectName: "Tabs header" });
    const tabs = [[fa.FaMap, "Daily heatwave map"], [fa.FaRoute, "Event catalogue and tracks"], [fa.FaChartLine, "Trends and climate drivers"],
      [fa.FaBell, "Seven-day risk map"], [fa.FaLocationDot, "Lakshadweep 2023–24"], [fa.FaSliders, "Model scores and rules"]];
    for (const [i, [Ic, t]] of tabs.entries()) {
      const y = 2.05 + i * 0.52;
      await iconCircle(s, Ic, 8.35, y, 0.4, T.accent3, T.lt1, t);
      text(s, t, { x: 8.9, y, w: XR - 8.9, h: 0.4, fontSize: 14, valign: "middle", objectName: `Tab ${i + 1}` });
    }
    card(s, 8.35, 5.3, XR - 8.35, 1.4, "PostGIS card");
    text(s, [{ text: "PostGIS 3.4 with GiST indexes", options: { bold: true, fontSize: 16, color: C.text2, breakLine: true } },
      { text: "291,272 footprints and 14,472 events. Questions like ‘which ecoregions did heatwaves touch in April–May 2024?’ answer in seconds.", options: { fontSize: 13 } }],
      { x: 8.55, y: 5.42, w: XR - 8.75, h: 1.2, objectName: "PostGIS text" });
    s.addNotes("Results are only useful if people can see them. Stage G exports small files from the DGX. On my PC, the events and footprints go into a PostGIS database with spatial indexes, so spatial questions are answered in seconds. I also built a Streamlit dashboard with six tabs: the daily heatwave map, the events and their tracks, trends, the seven-day risk map, the Lakshadweep case study, and the model scores. I can show it live if there is time.");
  }

  // ---------------------------------------------------------- 18. what I learned
  section("Discussion");
  {
    const s = contentSlide("DISCUSSION", "What worked and what I learned");
    s.addChart(pres.charts.BAR, [{ name: "Minutes", labels: ["Ingest and QC (A)", "Detection (B)", "Events (C)", "Warning model (E)", "Trust checks"], values: [11, 3.3, 2.1, 82, 3] }],
      { x: X0, y: 1.5, w: 5.9, h: 4.2, ...chartBase(), barDir: "bar", chartColors: [T.accent3], barGapWidthPct: 45, catAxisOrientation: "maxMin",
        title: "Full-basin run time on the DGX (minutes)", showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0",
        valAxisHidden: true, valAxisMinVal: 0, valAxisMaxVal: 95, valGridLine: { style: "none" }, showLegend: false, objectName: "Runtime chart",
        altText: "Bar chart of run time per stage: ingest 11, detection 3.3, events 2.1, model 82, trust checks 3 minutes" });
    text(s, "937.5 million rows to 14,472 events in about 100 minutes of computing.", { x: X0, y: 5.85, w: 5.9, h: 0.6, fontSize: 14, color: C.accent5, objectName: "Runtime note" });
    const rows = [
      [fa.FaBolt, "Spark and Sedona scale simply", "applyInPandas ran ordinary pandas code per cell and per day on 48 cores; Sedona made tracking a few lines of spatial SQL."],
      [fa.FaShieldHalved, "Checks beat luck", "The half-empty downloads and the look-ahead leak gave no error. Only explicit checks caught them."],
      [fa.FaScaleBalanced, "Read results honestly", "The model's gain is small (+0.027 PR-AUC). When the water is still cool, both methods are weak (about 0.27)."],
    ];
    for (const [i, [Ic, t, d]] of rows.entries()) {
      const y = 1.55 + i * 1.65;
      card(s, 6.85, y, XR - 6.85, 1.5, `Lesson ${i + 1}`);
      await iconCircle(s, Ic, 7.1, y + 0.3, 0.65, i === 1 ? T.accent1 : T.accent3, T.lt1, t);
      text(s, [{ text: t, options: { bold: true, fontSize: 16, color: C.text2, breakLine: true } }, { text: d, options: { fontSize: 14 } }],
        { x: 7.95, y: y + 0.15, w: XR - 8.15, h: 1.25, objectName: `Lesson ${i + 1} text` });
    }
    s.addNotes("What did I learn? First, Spark and Sedona really do scale: the full run took about 100 minutes, and most of that was the model stage. Second, checks beat luck: two serious problems gave no error message, and I only caught them because I wrote explicit checks. Third, results must be read honestly: the model is better than the rule, but only a little, and heatwaves that start from cool water are still hard to predict from surface temperature alone.");
  }

  // ---------------------------------------------------------- 19. limitations & future
  {
    const s = contentSlide("DISCUSSION", "Limitations and future work");
    const cols = [
      [fa.FaTriangleExclamation, "Limitations", T.accent1, [
        "Fixed 1991–2020 baseline: part of the rise is long-term warming, not just more extremes",
        "Any overlap links footprints, so some events chain together for years",
        "0.25° cells (about 28 km) blur small atolls like Lakshadweep",
        "Only surface temperature: winds and ocean mixing are not seen"]],
      [fa.FaRocket, "Future work", T.accent3, [
        "Add ocean heat content, winds, mixed-layer depth and heat flux",
        "A detrended baseline to separate warming from extremes",
        "Stricter event linking with a minimum overlap",
        "Spatio-temporal deep learning such as ConvLSTM",
        "Daily automatic updates for a live heatwave monitor"]],
    ];
    for (const [i, [Ic, head, hex, lines]] of cols.entries()) {
      const x = X0 + i * 6.23, w = 5.9;
      card(s, x, 1.55, w, 4.3, `${head} card`, { shadow: true });
      await iconCircle(s, Ic, x + 0.35, 1.8, 0.65, hex, T.lt1, head);
      text(s, head, { x: x + 1.2, y: 1.8, w: 4, h: 0.65, fontSize: 22, bold: true, color: C.text2, fontFace: HEAD, valign: "middle", objectName: `${head} header` });
      text(s, lines.map((l, j) => ({ text: l, options: { bullet: { indent: 16 }, breakLine: j < lines.length - 1 } })),
        { x: x + 0.35, y: 2.75, w: w - 0.7, h: 2.95, fontSize: 16, paraSpaceAfter: 10, objectName: `${head} list` });
    }
    card(s, X0, 6.05, CW, 0.7, "Next step card", { fill: { color: C.accent3, transparency: 88 } });
    text(s, [{ text: "Most promising next step: ", options: { bold: true, color: C.accent3 } },
      { text: "see below the surface (ocean heat content, mixing and winds), which drive the onsets that SST alone cannot foresee." }],
      { x: X0 + 0.25, y: 6.05, w: CW - 0.5, h: 0.7, fontSize: 14, valign: "middle", objectName: "Next step text" });
    s.addNotes("Every project has limits. I used a fixed baseline, so part of the increase is simply long-term warming. My tracking links any overlapping footprints, which can chain events together for years. The grid is too coarse for small islands. And the model only sees surface temperature. With more time, I would add data from below the surface and winds, use a detrended baseline, make event linking stricter, try deep learning like ConvLSTM, and update the data every day so the dashboard becomes a live monitor.");
  }

  // ---------------------------------------------------------- 20. conclusion
  {
    const s = contentSlide("CONCLUSION", "Three take-aways", "DARK");
    const pts = [
      "Indian Ocean heatwaves are now about six times more common than in the 1980s, and 2024 was the worst year on record.",
      "A spatial model, driven by the warmth of neighbouring water, warns earlier than the simple rule: reliably, but modestly.",
      "At a billion rows, careful checks matter as much as the algorithms.",
    ];
    for (const [i, t] of pts.entries()) {
      const x = X0 + i * 4.15, w = 3.85;
      card(s, x, 1.9, w, 4.1, `Takeaway ${i + 1}`, { fill: { color: C.background1, transparency: 92 } });
      numCircle(s, i + 1, x + 0.35, 2.25, 0.8, C.accent1, `Takeaway ${i + 1}`);
      text(s, t, { x: x + 0.35, y: 3.35, w: w - 0.7, h: 2.5, fontSize: 22, color: C.background1, objectName: `Takeaway ${i + 1} text` });
    }
    s.addNotes("To conclude, three take-aways. One: heatwaves in the Indian Ocean are now about six times more common than in the 1980s. Two: a spatial model, which mainly looks at the warmth of the neighbouring water, can warn a few days earlier than a simple rule. The gain is modest but reliable. Three: when you work with a billion rows, careful checks are as important as the algorithms.");
  }

  // ---------------------------------------------------------- 21. thank you
  {
    const s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: SECTION });
    s.addImage({ path: path.join(__dirname, "assets", "hero_2024.png"), x: W - 8.2, y: 1.0, w: 8.2, h: 8.2 / 1.5,
      altText: "Map of marine heatwave days per ocean cell in 2024", objectName: "Closing map" });
    s.addText("Thank you", { placeholder: "title" });
    s.addText("Questions and suggestions are welcome", { placeholder: "subtitle" });
    text(s, [
      { text: "Ananthanarayanan B  ·  Reg. No 253318", options: { bold: true, fontSize: 16, color: C.background1, breakLine: true } },
      { text: "Supervisor: Manoj Kumar", options: { fontSize: 14, color: C.background2, breakLine: true } },
      { text: "Digital University Kerala", options: { fontSize: 14, color: C.background2 } },
    ], { x: X0, y: 4.55, w: 4.9, h: 1.1, paraSpaceAfter: 3, objectName: "Contact" });
    s.addNotes("Thank you for listening. I am happy to take questions, and I can also show the dashboard live.");
  }

  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log(`wrote ${OUT}  (trend slope ${(TREND.slope * 10).toFixed(2)} days/decade)`);
}

build().catch((e) => { console.error(e); process.exit(1); });
