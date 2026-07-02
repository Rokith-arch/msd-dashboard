"""
SFMC Email Performance — single-page HTML dashboard generator.

Setup (one-time):
    pip install pandas openpyxl playwright
    playwright install chromium

Usage:
    python sfmc_dashboard.py SFMC_Data.xlsx

Output:
    SFMC_Data_dashboard.pdf   (preferred — falls back to .html if Playwright/Chromium isn't set up)
"""
import pandas as pd
import sys
import os
import json
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────
COL_MONTH       = "Month"
COL_CAMPAIGN    = "Campaign"
COL_TA          = "TA"
VALID_TA        = {"diabetes", "vaccines", "hac", "onco"}  # lowercase for case-insensitive match
COL_DELIVERED   = "Total Delivered"
COL_OPENS       = "Total Opens"
COL_CLICKS      = "Total Clicks"

MONTH_ORDER = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

MIN_DELIVERED_FOR_RANKING = 500
TOP_N_CAMPAIGNS = 10
# ────────────────────────────────────────────────────────────────────────

def load_and_clean(path):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()

    for col in [COL_DELIVERED, COL_OPENS, COL_CLICKS]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where all numeric cols are NaN
    numeric_cols = [c for c in [COL_DELIVERED, COL_OPENS, COL_CLICKS] if c in df.columns]
    df = df.dropna(subset=numeric_cols, how='all')
    for col in numeric_cols:
        df[col] = df[col].fillna(0)

    # Clean TA — normalize blanks to empty string, but keep them in df
    if COL_TA in df.columns:
        df[COL_TA] = df[COL_TA].astype(str).str.strip()
        df[COL_TA] = df[COL_TA].replace('nan', '')

    # Clean Campaign — remove nan strings
    if COL_CAMPAIGN in df.columns:
        df[COL_CAMPAIGN] = df[COL_CAMPAIGN].astype(str).str.strip()
        df = df[df[COL_CAMPAIGN].str.lower() != 'nan']
        df = df[df[COL_CAMPAIGN] != '']

    # Clean Month — keep only valid months
    # Excel sometimes auto-converts month name text to a date serial/datetime.
    # Recover the month name from whatever shape pandas returns.
    if COL_MONTH in df.columns:
        import datetime as _dt
        def _to_month_name(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            if isinstance(v, str):
                s = v.strip()
                # already a valid month name?
                if s in MONTH_ORDER:
                    return s
                # try parsing as date string
                try:
                    return pd.to_datetime(s).strftime("%B")
                except Exception:
                    return s
            if isinstance(v, (pd.Timestamp, _dt.datetime, _dt.date)):
                return pd.Timestamp(v).strftime("%B")
            return str(v).strip()
        df[COL_MONTH] = df[COL_MONTH].apply(_to_month_name)
        df = df[df[COL_MONTH].notna()]
        df = df[df[COL_MONTH].isin(MONTH_ORDER)]

    return df

def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(int(round(n)))

def pct(numerator, denominator):
    return round((numerator / denominator * 100), 1) if denominator else 0.0


def build_dashboard(df, output_path):
    # ── Summary KPIs
    total_delivered = int(df[COL_DELIVERED].sum())
    total_opens     = int(df[COL_OPENS].sum())
    total_clicks    = int(df[COL_CLICKS].sum())
    or_rate         = pct(total_opens, total_delivered)
    ctr_rate        = pct(total_clicks, total_delivered)

    # ── Monthly performance trend (filter nan months already done)
    m_df = df.groupby(COL_MONTH)[[COL_DELIVERED, COL_OPENS, COL_CLICKS]].sum().reset_index()
    m_df = m_df[m_df[COL_MONTH].isin(MONTH_ORDER)]
    m_df = m_df[m_df[COL_DELIVERED] > 0]
    m_df["_order"] = m_df[COL_MONTH].apply(lambda m: MONTH_ORDER.index(m))
    m_df = m_df.sort_values("_order")
    trend_labels    = m_df[COL_MONTH].tolist()
    trend_delivered = [int(v) for v in m_df[COL_DELIVERED].tolist()]
    trend_or        = [pct(o, d) for o, d in zip(m_df[COL_OPENS], m_df[COL_DELIVERED])]
    trend_ctr       = [pct(c, d) for c, d in zip(m_df[COL_CLICKS], m_df[COL_DELIVERED])]

    present = [m for m in MONTH_ORDER if m in trend_labels]
    month_range = f"{present[0]} – {present[-1]} 2025" if present else "2025"

    # ── Campaign performance (ranked by Open Rate)
    c_df = df.groupby(COL_CAMPAIGN)[[COL_DELIVERED, COL_OPENS, COL_CLICKS]].sum().reset_index()
    c_df = c_df[c_df[COL_DELIVERED] >= MIN_DELIVERED_FOR_RANKING]
    c_df["OR"]  = c_df.apply(lambda r: pct(r[COL_OPENS], r[COL_DELIVERED]), axis=1)
    c_df["CTR"] = c_df.apply(lambda r: pct(r[COL_CLICKS], r[COL_DELIVERED]), axis=1)
    c_df = c_df.sort_values("OR", ascending=False).head(TOP_N_CAMPAIGNS)
    camp_labels = c_df[COL_CAMPAIGN].tolist()
    camp_or     = c_df["OR"].tolist()
    camp_rows   = [
        (r[COL_CAMPAIGN], int(r[COL_DELIVERED]), int(r[COL_OPENS]), r["OR"], int(r[COL_CLICKS]), r["CTR"])
        for _, r in c_df.iterrows()
    ]

    # ── TA performance summary — exclude blank TA rows here only
    ta_df = df[df[COL_TA].str.lower().isin(VALID_TA)].groupby(COL_TA)[[COL_DELIVERED, COL_OPENS, COL_CLICKS]].sum().reset_index()
    ta_df = ta_df[ta_df[COL_DELIVERED] > 0]
    ta_df["OR"]  = ta_df.apply(lambda r: pct(r[COL_OPENS], r[COL_DELIVERED]), axis=1)
    ta_df["CTR"] = ta_df.apply(lambda r: pct(r[COL_CLICKS], r[COL_DELIVERED]), axis=1)
    ta_df = ta_df.sort_values(COL_DELIVERED, ascending=False)
    ta_labels    = ta_df[COL_TA].tolist()
    ta_delivered = [int(v) for v in ta_df[COL_DELIVERED].tolist()]
    ta_or        = ta_df["OR"].tolist()
    ta_ctr       = ta_df["CTR"].tolist()
    ta_rows      = [
        (r[COL_TA], int(r[COL_DELIVERED]), int(r[COL_OPENS]), r["OR"], int(r[COL_CLICKS]), r["CTR"])
        for _, r in ta_df.iterrows()
    ]

    # ── gradient color tiers for the campaign ranking bar
    n_camp = max(len(camp_or), 1)
    camp_colors = []
    for i in range(len(camp_or)):
        t = i / max(n_camp - 1, 1)
        r = int(0x00 + t * (0xB7 - 0x00))
        g = int(0x85 + t * (0xDD - 0x85))
        b = int(0x7B + t * (0xD8 - 0x7B))
        camp_colors.append(f"rgb({r},{g},{b})")

    def camp_table_rows():
        html = ""
        for i, (camp, deliv, opens, orr, clicks, ctr) in enumerate(camp_rows, 1):
            html += f"""<tr>
              <td><span class="rank">{i}</span>{camp}</td>
              <td>{deliv:,}</td>
              <td>{orr}%</td>
              <td>{ctr}%</td>
            </tr>"""
        return html

    def ta_table_rows():
        html = ""
        for ta, deliv, opens, orr, clicks, ctr in ta_rows:
            html += f"""<tr>
              <td>{ta}</td>
              <td>{deliv:,}</td>
              <td>{opens:,}</td>
              <td>{orr}%</td>
              <td>{clicks:,}</td>
              <td>{ctr}%</td>
            </tr>"""
        return html

    rows_camp = camp_table_rows()
    rows_ta   = ta_table_rows()

    ta_donut_colors = ["#00857B", "#0A2540", "#1A6FAF", "#1B8A4E", "#0EA5A0", "#7C5CBF", "#C2410C"]

    # Compute suggestedMax for right axis — give enough headroom so labels don't overlap
    all_rates = trend_or + trend_ctr
    max_rate  = max(all_rates) if all_rates else 10
    suggested_max = round(max_rate * 2.2, 1)

    # ── Pre-build filter option HTML (avoids backslash-in-f-string on Python <3.12)
    # Unique filter options (sorted) — must be defined before ta_options etc.
    all_ta        = sorted([t for t in df[COL_TA].dropna().unique().tolist() if t.lower() in VALID_TA])
    all_months    = [m for m in MONTH_ORDER if m in df[COL_MONTH].dropna().unique().tolist()]
    all_campaigns = sorted(df[COL_CAMPAIGN].dropna().unique().tolist())

    # Serialize raw rows for JS filtering engine
    raw_rows = df[[COL_TA, COL_MONTH, COL_CAMPAIGN, COL_DELIVERED, COL_OPENS, COL_CLICKS]].copy()
    raw_rows.columns = ["ta", "month", "campaign", "delivered", "opens", "clicks"]
    raw_json = raw_rows.to_json(orient="records")

    ta_options = "".join(
        '<label class="fd-item"><input type="checkbox" class="cb-TA" value="' + ta + '" onchange="cbChange(\'TA\')"> ' + ta + '</label>'
        for ta in all_ta
    )
    month_options = "".join(
        '<label class="fd-item"><input type="checkbox" class="cb-Month" value="' + m + '" onchange="cbChange(\'Month\')"> ' + m + '</label>'
        for m in all_months
    )
    campaign_options = "".join(
        '<label class="fd-item"><input type="checkbox" class="cb-Campaign" value="' + c + '" onchange="cbChange(\'Campaign\')"> ' + c + '</label>'
        for c in all_campaigns
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SFMC Email Performance Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Raleway:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  /* Base — Raleway for all body/word text */
  body {{
    font-family: 'Raleway', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #E8EEF4; padding: 24px; min-width: 1100px;
  }}
  .dash {{ max-width: 1240px; margin: 0 auto; }}

  /* Header */
  .dash-header {{
    background: #0A2540; color: #fff; padding: 18px 28px;
    display: flex; align-items: center; justify-content: space-between;
    border-radius: 12px 12px 0 0;
  }}
  .dash-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 20px; font-weight: 600; color: #fff;
  }}
  .dash-badge {{
    background: #00857B; color: #fff;
    font-family: 'Raleway', sans-serif;
    font-size: 11px; padding: 4px 12px; border-radius: 20px; margin-left: 14px;
  }}
  .month-pill {{
    background: rgba(255,255,255,0.12); color: #fff;
    font-family: 'Raleway', sans-serif;
    font-size: 12px; padding: 6px 16px; border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.2);
  }}
  .dash-body {{ background: #F0F4F8; padding: 22px; border-radius: 0 0 12px 12px; }}

  /* Metric cards */
  .metric-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 22px; }}
  .metric-card {{ background: #fff; border-radius: 10px; padding: 16px 18px; }}
  .metric-dot {{ width: 10px; height: 10px; border-radius: 50%; margin-bottom: 10px; }}
  .metric-card.c1 .metric-dot {{ background: #00857B; }}
  .metric-card.c2 .metric-dot {{ background: #0A2540; }}
  .metric-card.c3 .metric-dot {{ background: #1A6FAF; }}
  .metric-card.c4 .metric-dot {{ background: #1B8A4E; }}
  .metric-card.c5 .metric-dot {{ background: #0EA5A0; }}

  /* Raleway for label words, Montserrat for numbers */
  .metric-label {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 4px;
    letter-spacing: 0.3px; text-transform: uppercase;
  }}
  .metric-value {{
    font-family: 'Montserrat', sans-serif;
    font-size: 24px; font-weight: 600; color: #0A2540;
  }}

  /* Section labels — Montserrat headings */
  .section-label {{
    font-family: 'Montserrat', sans-serif;
    font-size: 13px; font-weight: 600; color: #0A2540;
    margin: 4px 0 10px 2px; text-transform: uppercase; letter-spacing: 0.4px;
  }}

  .charts-row {{ display: grid; gap: 16px; margin-bottom: 22px; }}
  .r1 {{ grid-template-columns: 1fr; }}
  .r2 {{ grid-template-columns: 1.1fr 0.9fr; }}
  .r3 {{ grid-template-columns: 1fr 1fr 1.2fr; }}
  .chart-card {{ background: #fff; border-radius: 10px; padding: 18px; }}

  /* Montserrat for card headings */
  .card-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 13px; font-weight: 600; color: #0A2540; margin-bottom: 2px;
  }}
  /* Raleway for subtitles/descriptions */
  .card-sub {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 14px;
  }}

  /* Tables */
  .table-card {{ background: #fff; border-radius: 10px; padding: 18px; }}
  .tbl {{ width: 100%; font-size: 12px; border-collapse: collapse; }}
  .tbl thead tr {{ background: #0A2540; color: #fff; }}
  .tbl thead th {{
    font-family: 'Montserrat', sans-serif;
    padding: 9px 10px; text-align: left; font-weight: 600;
  }}
  .tbl thead th:not(:first-child) {{ text-align: right; }}
  .tbl tbody tr:nth-child(even) {{ background: #F8FAFC; }}
  .tbl tbody td {{
    font-family: 'Raleway', sans-serif;
    padding: 7px 10px; color: #334155; border-bottom: 0.5px solid #E2E8F0;
  }}
  .tbl tbody td:not(:first-child) {{ text-align: right; }}
  .tbl tbody td:nth-child(3), .tbl tbody td:last-child {{
    font-family: 'Montserrat', sans-serif;
    font-weight: 600; color: #00857B;
  }}
  .rank {{ color: #94A3B8; font-size: 11px; width: 18px; display: inline-block; }}

  .legend-row {{ display: flex; gap: 18px; margin-bottom: 6px; }}
  .legend-item {{
    display: flex; align-items: center; gap: 6px;
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B;
  }}
  .legend-swatch {{ width: 10px; height: 10px; border-radius: 3px; }}

  /* ── Filter bar */
  .filter-bar {{
    background: #fff; border-radius: 0 0 10px 10px;
    padding: 12px 22px; display: flex; align-items: center; gap: 10px;
    flex-wrap: wrap; border-top: 1px solid #E2E8F0; margin-bottom: 0;
  }}
  .filter-label {{
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 600; color: #64748B;
    text-transform: uppercase; letter-spacing: 0.4px; white-space: nowrap;
  }}
  /* custom dropdown */
  .fd-wrap {{ position: relative; display: inline-block; }}
  .fd-btn {{
    font-family: 'Raleway', sans-serif; font-size: 12px; color: #0A2540;
    border: 1.5px solid #CBD5E1; border-radius: 7px;
    padding: 5px 28px 5px 10px; background: #F8FAFC;
    cursor: pointer; outline: none; min-width: 140px; text-align: left;
    white-space: nowrap; position: relative;
  }}
  .fd-btn::after {{
    content: '▾'; position: absolute; right: 9px; top: 50%;
    transform: translateY(-50%); color: #64748B; font-size: 11px;
  }}
  .fd-btn.active {{ border-color: #00857B; background: #F0FAF9; }}
  .fd-panel {{
    display: none; position: absolute; top: calc(100% + 4px); left: 0;
    background: #fff; border: 1.5px solid #CBD5E1; border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.10); z-index: 999;
    min-width: 180px; max-width: 260px; max-height: 240px;
    overflow-y: auto; padding: 6px 0;
  }}
  .fd-panel.open {{ display: block; }}
  .fd-item {{
    display: flex; align-items: center; gap: 8px;
    padding: 6px 14px; cursor: pointer;
    font-family: 'Raleway', sans-serif; font-size: 12px; color: #334155;
  }}
  .fd-item:hover {{ background: #F0FAF9; }}
  .fd-item input[type=checkbox] {{ accent-color: #00857B; width: 13px; height: 13px; cursor: pointer; }}
  .fd-divider {{ border: none; border-top: 1px solid #E2E8F0; margin: 4px 0; }}
  .filter-reset {{
    font-family: 'Raleway', sans-serif;
    font-size: 12px; color: #00857B; cursor: pointer;
    border: 1.5px solid #00857B; border-radius: 7px;
    padding: 5px 14px; background: transparent;
    white-space: nowrap; margin-left: auto;
  }}
  .filter-reset:hover {{ background: #00857B; color: #fff; }}
  .filter-sep {{ width: 1px; height: 22px; background: #E2E8F0; }}
</style>
</head>
<body>
<div class="dash">
  <div class="dash-header">
    <div style="display:flex;align-items:center;gap:10px;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#00857B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16v16H4z"/><path d="m4 6 8 7 8-7"/></svg>
      <span class="dash-title">SFMC Email Performance</span>
      <span class="dash-badge">MSD · SFMC</span>
    </div>
    <div class="month-pill">📅 {month_range}</div>
  </div>

  <!-- ── Filter bar ── -->
  <div class="filter-bar">
    <span class="filter-label">🔽 Filters</span>
    <div class="filter-sep"></div>

    <span class="filter-label">TA</span>
    <div class="fd-wrap" id="wrap-TA">
      <button class="fd-btn" id="btn-TA" onclick="toggleDropdown('TA')">All TAs</button>
      <div class="fd-panel" id="panel-TA">
        <label class="fd-item"><input type="checkbox" id="all-TA" checked onchange="allToggle('TA',this)"> All TAs</label>
        <hr class="fd-divider">
        {ta_options}
      </div>
    </div>

    <div class="filter-sep"></div>
    <span class="filter-label">Month</span>
    <div class="fd-wrap" id="wrap-Month">
      <button class="fd-btn" id="btn-Month" onclick="toggleDropdown('Month')">All Months</button>
      <div class="fd-panel" id="panel-Month">
        <label class="fd-item"><input type="checkbox" id="all-Month" checked onchange="allToggle('Month',this)"> All Months</label>
        <hr class="fd-divider">
        {month_options}
      </div>
    </div>

    <div class="filter-sep"></div>
    <span class="filter-label">Campaign</span>
    <div class="fd-wrap" id="wrap-Campaign">
      <button class="fd-btn" id="btn-Campaign" onclick="toggleDropdown('Campaign')">All Campaigns</button>
      <div class="fd-panel" id="panel-Campaign">
        <label class="fd-item"><input type="checkbox" id="all-Campaign" checked onchange="allToggle('Campaign',this)"> All Campaigns</label>
        <hr class="fd-divider">
        {campaign_options}
      </div>
    </div>

    <button class="filter-reset" onclick="resetFilters()">✕ Reset</button>
  </div>

  <div class="dash-body">
    <div class="metric-grid">
      <div class="metric-card c1">
        <div class="metric-dot"></div>
        <div class="metric-label">Total Delivered</div>
        <div class="metric-value" id="kpiDelivered">{fmt(total_delivered)}</div>
      </div>
      <div class="metric-card c2">
        <div class="metric-dot"></div>
        <div class="metric-label">Total Opens</div>
        <div class="metric-value" id="kpiOpens">{fmt(total_opens)}</div>
      </div>
      <div class="metric-card c3">
        <div class="metric-dot"></div>
        <div class="metric-label">Open Rate (OR)</div>
        <div class="metric-value" id="kpiOR">{or_rate}%</div>
      </div>
      <div class="metric-card c4">
        <div class="metric-dot"></div>
        <div class="metric-label">Total Clicks</div>
        <div class="metric-value" id="kpiClicks">{fmt(total_clicks)}</div>
      </div>
      <div class="metric-card c5">
        <div class="metric-dot"></div>
        <div class="metric-label">Click-Through Rate</div>
        <div class="metric-value" id="kpiCTR">{ctr_rate}%</div>
      </div>
    </div>

    <div class="section-label">Monthly Performance Trend</div>
    <div class="charts-row r1">
      <div class="chart-card">
        <div class="card-title">Delivered Volume vs. Open &amp; Click Rate</div>
        <div class="card-sub">Bars = total delivered (left axis) · Lines = OR% / CTR% (right axis)</div>
        <div style="position:relative;width:100%;height:260px;">
          <canvas id="trendChart"></canvas>
        </div>
      </div>
    </div>

    <div class="section-label">Campaign Performance</div>
    <div class="charts-row r2">
      <div class="chart-card">
        <div class="card-title">Top {TOP_N_CAMPAIGNS} Campaigns by Open Rate</div>
        <div class="card-sub">Ranked highest → lowest OR (min. {MIN_DELIVERED_FOR_RANKING:,} delivered)</div>
        <div style="position:relative;width:100%;height:260px;">
          <canvas id="campChart"></canvas>
        </div>
      </div>
      <div class="table-card">
        <div class="card-title">Campaign Breakdown</div>
        <div class="card-sub">Delivered · OR · CTR for the campaigns above</div>
        <table class="tbl">
          <thead><tr><th>Campaign</th><th>Delivered</th><th>OR</th><th>CTR</th></tr></thead>
          <tbody id="campTable">{rows_camp}</tbody>
        </table>
      </div>
    </div>

    <div class="section-label">Therapy Area (TA) Performance</div>
    <div class="charts-row r3">
      <div class="chart-card">
        <div class="card-title">Delivered Share by TA</div>
        <div class="card-sub">% of total delivered volume</div>
        <div style="position:relative;width:100%;height:210px;">
          <canvas id="taDonutChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-title">OR vs. CTR by TA</div>
        <div class="card-sub">Performance shape per division</div>
        <div class="legend-row">
          <div class="legend-item"><span class="legend-swatch" style="background:#00857B;"></span>Open Rate</div>
          <div class="legend-item"><span class="legend-swatch" style="background:#1A6FAF;"></span>CTR</div>
        </div>
        <div style="position:relative;width:100%;height:185px;">
          <canvas id="taRadarChart"></canvas>
        </div>
      </div>
      <div class="table-card">
        <div class="card-title">TA Breakdown</div>
        <div class="card-sub">Full division-level metrics</div>
        <table class="tbl">
          <thead><tr><th>TA</th><th>Delivered</th><th>Opens</th><th>OR</th><th>Clicks</th><th>CTR</th></tr></thead>
          <tbody id="taTable">{rows_ta}</tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-datalabels/2.2.0/chartjs-plugin-datalabels.min.js"></script>
<script>
Chart.register(ChartDataLabels);

const MONTSERRAT = 'Montserrat, sans-serif';
const RALEWAY    = 'Raleway, sans-serif';
const MONTH_ORDER = {json.dumps(MONTH_ORDER)};
const TA_DONUT_COLORS = {json.dumps(ta_donut_colors)};
const MIN_DELIVERED = {MIN_DELIVERED_FOR_RANKING};
const TOP_N = {TOP_N_CAMPAIGNS};

// ── Raw data (all rows from Excel)
const RAW = {raw_json};

// ── Helpers
function fmt(n) {{
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1000) return (n/1000).toFixed(1)+'K';
  return String(Math.round(n));
}}
function pct(num, den) {{ return den ? +((num/den)*100).toFixed(1) : 0; }}
function gradColor(i, n) {{
  const t = n <= 1 ? 0 : i / (n-1);
  const r = Math.round(0x00 + t*(0xB7-0x00));
  const g = Math.round(0x85 + t*(0xDD-0x85));
  const b = Math.round(0x7B + t*(0xD8-0x7B));
  return `rgb(${{r}},${{g}},${{b}})`;
}}
function groupBy(rows, key, cols) {{
  const map = {{}};
  rows.forEach(r => {{
    const k = r[key];
    if (!map[k]) map[k] = {{[key]:k, delivered:0, opens:0, clicks:0}};
    cols.forEach(c => map[k][c] += (r[c]||0));
  }});
  return Object.values(map);
}}

// ── Dropdown open/close
function toggleDropdown(name) {{
  const panel = document.getElementById('panel-'+name);
  const btn   = document.getElementById('btn-'+name);
  const isOpen = panel.classList.contains('open');
  document.querySelectorAll('.fd-panel').forEach(p => p.classList.remove('open'));
  document.querySelectorAll('.fd-btn').forEach(b => b.classList.remove('active'));
  if (!isOpen) {{ panel.classList.add('open'); btn.classList.add('active'); }}
}}
document.addEventListener('click', e => {{
  if (!e.target.closest('.fd-wrap')) {{
    document.querySelectorAll('.fd-panel').forEach(p => p.classList.remove('open'));
    document.querySelectorAll('.fd-btn').forEach(b => b.classList.remove('active'));
  }}
}});
function allToggle(name, cb) {{
  if (cb.checked) document.querySelectorAll('.cb-'+name).forEach(c => c.checked = false);
  updateBtnLabel(name); applyFilters();
}}
function cbChange(name) {{
  const checked = Array.from(document.querySelectorAll('.cb-'+name+':checked'));
  document.getElementById('all-'+name).checked = checked.length === 0;
  updateBtnLabel(name); applyFilters();
}}
function updateBtnLabel(name) {{
  const checked = Array.from(document.querySelectorAll('.cb-'+name+':checked'));
  const btn = document.getElementById('btn-'+name);
  const allLabel = name==='TA'?'All TAs': name==='Month'?'All Months':'All Campaigns';
  btn.textContent = checked.length===0 ? allLabel : checked.length===1 ? checked[0].value : checked.length+' selected';
}}
function getFilter(name) {{
  if (document.getElementById('all-'+name).checked) return null;
  const vals = Array.from(document.querySelectorAll('.cb-'+name+':checked')).map(c => c.value);
  return vals.length ? vals : null;
}}

// ── Filter raw data
function filterData() {{
  const ta   = getFilter('TA');
  const mon  = getFilter('Month');
  const camp = getFilter('Campaign');
  return RAW.filter(r =>
    (!ta   || ta.includes(r.ta))   &&
    (!mon  || mon.includes(r.month)) &&
    (!camp || camp.includes(r.campaign))
  );
}}

// ── Chart instances
let trendChart, campChart, taDonutChart, taRadarChart;

function buildTrendChart(rows) {{
  const mmap = {{}};
  rows.forEach(r => {{
    if (!MONTH_ORDER.includes(r.month)) return;
    if (!mmap[r.month]) mmap[r.month] = {{delivered:0,opens:0,clicks:0}};
    mmap[r.month].delivered += r.delivered;
    mmap[r.month].opens     += r.opens;
    mmap[r.month].clicks    += r.clicks;
  }});
  const labels  = MONTH_ORDER.filter(m => mmap[m] && mmap[m].delivered > 0);
  const deliv   = labels.map(m => mmap[m].delivered);
  const orArr   = labels.map(m => pct(mmap[m].opens, mmap[m].delivered));
  const ctrArr  = labels.map(m => pct(mmap[m].clicks, mmap[m].delivered));
  const allRates = [...orArr,...ctrArr];
  const sugMax  = allRates.length ? +(Math.max(...allRates)*2.2).toFixed(1) : 10;

  if (trendChart) {{
    trendChart.data.labels = labels;
    trendChart.data.datasets[0].data = deliv;
    trendChart.data.datasets[1].data = orArr;
    trendChart.data.datasets[2].data = ctrArr;
    trendChart.options.scales.y1.suggestedMax = sugMax;
    trendChart.update();
  }} else {{
    trendChart = new Chart(document.getElementById('trendChart'), {{
      data: {{
        labels,
        datasets: [
          {{
            type:'bar', label:'Delivered', data:deliv,
            backgroundColor:'#CFE3F0', borderRadius:6, borderSkipped:false,
            yAxisID:'y', order:2,
            datalabels:{{ anchor:'center', align:'center', color:'#0A2540',
              font:{{size:10,weight:'600',family:MONTSERRAT}},
              formatter: v => v>=1000?(v/1000).toFixed(1)+'K':v }}
          }},
          {{
            type:'line', label:'OR %', data:orArr,
            borderColor:'#00857B', backgroundColor:'#00857B', tension:0,
            pointRadius:5, pointBackgroundColor:'#00857B', borderWidth:2.5,
            yAxisID:'y1', order:1,
            datalabels:{{ align:'top', anchor:'end', offset:6, color:'#00857B',
              font:{{size:10,weight:'600',family:MONTSERRAT}}, formatter:v=>v+'%' }}
          }},
          {{
            type:'line', label:'CTR %', data:ctrArr,
            borderColor:'#1A6FAF', backgroundColor:'#1A6FAF', tension:0,
            pointRadius:5, pointBackgroundColor:'#1A6FAF', borderWidth:2.5,
            yAxisID:'y1', order:1,
            datalabels:{{ align:'bottom', anchor:'end', offset:6, color:'#1A6FAF',
              font:{{size:10,weight:'600',family:MONTSERRAT}}, formatter:v=>v+'%' }}
          }}
        ]
      }},
      options:{{
        responsive:true, maintainAspectRatio:false,
        layout:{{padding:{{top:30,bottom:16}}}},
        interaction:{{mode:'index',intersect:false}},
        plugins:{{
          legend:{{position:'top',align:'end',
            labels:{{color:'#334155',font:{{size:11,family:RALEWAY}},boxWidth:12,usePointStyle:true}}}},
          tooltip:{{enabled:true,bodyFont:{{family:MONTSERRAT,size:12}},titleFont:{{family:RALEWAY,size:12}}}}
        }},
        scales:{{
          x:{{grid:{{display:false}},ticks:{{color:'#64748B',font:{{size:11,family:RALEWAY}}}}}},
          y:{{position:'left',grid:{{color:'rgba(0,0,0,0.05)'}},
            ticks:{{color:'#64748B',font:{{size:10,family:MONTSERRAT}},
              callback:v=>v>=1000?(v/1000).toFixed(0)+'K':v}},
            title:{{display:true,text:'Delivered',color:'#94A3B8',font:{{size:10,family:RALEWAY}}}}}},
          y1:{{position:'right',min:0,suggestedMax:sugMax,grid:{{display:false}},
            ticks:{{color:'#64748B',font:{{size:10,family:MONTSERRAT}},callback:v=>v+'%'}},
            title:{{display:true,text:'Rate %',color:'#94A3B8',font:{{size:10,family:RALEWAY}}}}}}
        }}
      }}
    }});
  }}
}}

function buildCampChart(rows) {{
  const cmap = {{}};
  rows.forEach(r => {{
    if (!cmap[r.campaign]) cmap[r.campaign] = {{delivered:0,opens:0,clicks:0}};
    cmap[r.campaign].delivered += r.delivered;
    cmap[r.campaign].opens     += r.opens;
    cmap[r.campaign].clicks    += r.clicks;
  }});
  let camps = Object.entries(cmap)
    .filter(([,v]) => v.delivered >= MIN_DELIVERED)
    .map(([name,v]) => ({{name, ...v, or:pct(v.opens,v.delivered), ctr:pct(v.clicks,v.delivered)}}))
    .sort((a,b) => b.or - a.or).slice(0, TOP_N);

  const labels = camps.map(c => c.name);
  const orArr  = camps.map(c => c.or);
  const colors = camps.map((_,i) => gradColor(i, camps.length));

  // Update table
  let thtml = '';
  camps.forEach((c,i) => {{
    thtml += `<tr><td><span class="rank">${{i+1}}</span>${{c.name}}</td>
      <td>${{c.delivered.toLocaleString()}}</td><td>${{c.or}}%</td><td>${{c.ctr}}%</td></tr>`;
  }});
  document.querySelector('#campTable').innerHTML = thtml;

  if (campChart) {{
    campChart.data.labels = labels;
    campChart.data.datasets[0].data = orArr;
    campChart.data.datasets[0].backgroundColor = colors;
    campChart.update();
  }} else {{
    campChart = new Chart(document.getElementById('campChart'), {{
      type:'bar',
      data:{{ labels, datasets:[{{ data:orArr, backgroundColor:colors, borderRadius:6, borderSkipped:false }}] }},
      options:{{
        indexAxis:'y', responsive:true, maintainAspectRatio:false,
        layout:{{padding:{{right:36}}}},
        plugins:{{
          legend:{{display:false}},
          datalabels:{{anchor:'end',align:'end',color:'#0A2540',
            font:{{size:10,weight:'600',family:MONTSERRAT}},formatter:v=>v+'%'}}
        }},
        scales:{{
          x:{{display:false,grid:{{display:false}}}},
          y:{{grid:{{display:false}},ticks:{{color:'#334155',font:{{size:10.5,family:RALEWAY}}}}}}
        }}
      }}
    }});
  }}
}}

function buildTACharts(rows) {{
  const VALID_TA_JS = new Set(['diabetes','vaccines','hac','onco']);
  let tas = groupBy(rows,'ta',['delivered','opens','clicks'])
    .filter(t => t.delivered > 0 && VALID_TA_JS.has(t.ta.toLowerCase()))
    .map(t => ({{...t, or:pct(t.opens,t.delivered), ctr:pct(t.clicks,t.delivered)}}))
    .sort((a,b) => b.delivered - a.delivered);

  const labels  = tas.map(t => t.ta);
  const delivArr = tas.map(t => t.delivered);
  const orArr   = tas.map(t => t.or);
  const ctrArr  = tas.map(t => t.ctr);
  const bgColors = TA_DONUT_COLORS.slice(0, labels.length);

  // TA table
  let thtml = '';
  tas.forEach(t => {{
    thtml += `<tr><td>${{t.ta}}</td><td>${{t.delivered.toLocaleString()}}</td>
      <td>${{t.opens.toLocaleString()}}</td><td>${{t.or}}%</td>
      <td>${{t.clicks.toLocaleString()}}</td><td>${{t.ctr}}%</td></tr>`;
  }});
  document.querySelector('#taTable').innerHTML = thtml;

  if (taDonutChart) {{
    taDonutChart.data.labels = labels;
    taDonutChart.data.datasets[0].data = delivArr;
    taDonutChart.data.datasets[0].backgroundColor = bgColors;
    taDonutChart.update();
  }} else {{
    taDonutChart = new Chart(document.getElementById('taDonutChart'), {{
      type:'doughnut',
      data:{{ labels, datasets:[{{ data:delivArr, backgroundColor:bgColors, borderColor:'#fff', borderWidth:2 }}] }},
      options:{{
        responsive:true, maintainAspectRatio:false, cutout:'62%',
        plugins:{{
          legend:{{position:'bottom',labels:{{color:'#334155',font:{{size:10,family:RALEWAY}},boxWidth:10,padding:8}}}},
          datalabels:{{color:'#fff',font:{{size:10,weight:'600',family:MONTSERRAT}},
            formatter:(v,ctx)=>{{
              const tot=ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);
              const p=tot?(v/tot*100):0; return p>=6?p.toFixed(0)+'%':'';
            }}}}
        }}
      }}
    }});
  }}

  if (taRadarChart) {{
    taRadarChart.data.labels = labels;
    taRadarChart.data.datasets[0].data = orArr;
    taRadarChart.data.datasets[1].data = ctrArr;
    taRadarChart.update();
  }} else {{
    taRadarChart = new Chart(document.getElementById('taRadarChart'), {{
      type:'radar',
      data:{{ labels, datasets:[
        {{ label:'OR %', data:orArr, borderColor:'#00857B', backgroundColor:'rgba(0,133,123,0.15)',
           pointBackgroundColor:'#00857B', borderWidth:2 }},
        {{ label:'CTR %', data:ctrArr, borderColor:'#1A6FAF', backgroundColor:'rgba(26,111,175,0.12)',
           pointBackgroundColor:'#1A6FAF', borderWidth:2 }}
      ]}},
      options:{{
        responsive:true, maintainAspectRatio:false,
        plugins:{{ legend:{{display:false}}, datalabels:{{display:false}} }},
        scales:{{ r:{{
          angleLines:{{color:'#E2E8F0'}}, grid:{{color:'#E2E8F0'}},
          pointLabels:{{color:'#334155',font:{{size:10,family:RALEWAY}}}},
          ticks:{{display:false,backdropColor:'transparent'}}, suggestedMin:0
        }} }}
      }}
    }});
  }}
}}

function updateKPIs(rows) {{
  const deliv  = rows.reduce((s,r)=>s+r.delivered,0);
  const opens  = rows.reduce((s,r)=>s+r.opens,0);
  const clicks = rows.reduce((s,r)=>s+r.clicks,0);
  document.getElementById('kpiDelivered').textContent = fmt(deliv);
  document.getElementById('kpiOpens').textContent     = fmt(opens);
  document.getElementById('kpiOR').textContent        = pct(opens,deliv)+'%';
  document.getElementById('kpiClicks').textContent    = fmt(clicks);
  document.getElementById('kpiCTR').textContent       = pct(clicks,deliv)+'%';
}}

function applyFilters() {{
  const rows = filterData();
  updateKPIs(rows);
  buildTrendChart(rows);
  buildCampChart(rows);
  buildTACharts(rows);
}}

function resetFilters() {{
  ['TA','Month','Campaign'].forEach(name => {{
    document.getElementById('all-'+name).checked = true;
    document.querySelectorAll('.cb-'+name).forEach(c => c.checked = false);
    updateBtnLabel(name);
  }});
  applyFilters();
}}

// ── Initial render
applyFilters();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ── MAIN ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python sfmc_dashboard.py <your_excel_file.xlsx>")
        print("Example: python sfmc_dashboard.py SFMC_Data.xlsx")
        sys.exit(1)

    excel_path = sys.argv[1]
    if not os.path.exists(excel_path):
        print(f"Error: File not found - {excel_path}")
        sys.exit(1)

    html_out = str(Path(excel_path).stem) + "_dashboard.html"
    pdf_out  = str(Path(excel_path).stem) + "_dashboard.pdf"

    df = load_and_clean(excel_path)
    build_dashboard(df, html_out)

    try:
        from playwright.sync_api import sync_playwright
        abs_path = str(Path(html_out).resolve()).replace("\\", "/")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1460})
            page.goto(f"file:///{abs_path}")
            page.wait_for_timeout(2500)
            page.pdf(
                path=pdf_out,
                width="1280px",
                height="1460px",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"}
            )
            browser.close()
        os.remove(html_out)
        print(f"Dashboard saved: {pdf_out}")
    except Exception as e:
        print(f"Note: PDF export failed ({e}). HTML file saved: {html_out}")
