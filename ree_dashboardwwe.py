"""
REE Email Performance — single-page HTML dashboard generator.

Setup (one-time):
    pip install pandas openpyxl

Usage:
    python ree_dashboard.py REE_Data.xlsx

Output:
    REE_Data_dashboard.html

Logic:
  - "Delivered"  = rows where STATUS == "delivered"  (case-insensitive)
  - "Bounced"    = rows where STATUS == "bounced"     (case-insensitive)
  - "Dropped"    = rows where STATUS == "dropped"     (case-insensitive)
  - Opens        = sum of 'Opens'  column on delivered rows only
  - Clicks       = sum of 'Clicks' column on delivered rows only
  - OR %  = Opens  / Delivered × 100
  - CTR % = Clicks / Delivered × 100
"""

import pandas as pd
import sys
import os
import json
from pathlib import Path

# ── COLUMN NAMES ────────────────────────────────────────────────────────
COL_STATUS   = "STATUS"
COL_MONTH    = "Month"
COL_CAMPAIGN = "Campaign"
COL_TA       = "TA"
COL_MARKET   = "MARKET"
COL_OPENS    = "Opens"
COL_CLICKS   = "Clicks"
COL_SENT_DATE = "SENT DATE (UTC)"   # fallback source for deriving Month when the Month field itself is malformed

STATUS_DELIVERED = "delivered"
STATUS_BOUNCED   = "bounced"
STATUS_DROPPED   = "dropped"

MONTH_ORDER = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

# Exact campaign names to exclude from campaign ranking (case-insensitive)
EXCLUDED_CAMPAIGNS = {"ksa", "zoom", "veeva", "engage", "engagement", "ksa zoom engage", "ksa zoom veeva engage"}

MIN_DELIVERED_FOR_RANKING = 50   # minimum delivered for best campaign by OR%
TOP_N_CAMPAIGNS = 10
# ────────────────────────────────────────────────────────────────────────


def load_and_clean(path):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()

    # Normalise STATUS
    if COL_STATUS in df.columns:
        df[COL_STATUS] = df[COL_STATUS].astype(str).str.strip().str.lower()

    # Numeric cols
    for col in [COL_OPENS, COL_CLICKS]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # String cols — strip whitespace. Blanks/NaN are bucketed downstream
    # (as "Unassigned") instead of being dropped from the whole dataset,
    # so a missing Campaign/TA/Market never costs you a valid delivered row.
    for col in [COL_CAMPAIGN, COL_TA, COL_MARKET]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()

    # ── Normalise Month robustly (no hardcoded value list of "bad" strings) ──
    # Case/whitespace differences ("january", " January ") are fixed by
    # title-casing. If a value still isn't a real month name (blank,
    # abbreviated, numeric, etc.), it's derived automatically from the
    # SENT DATE (UTC) column already present in the data — so a malformed
    # Month field never silently deletes a valid delivered/opened/clicked
    # row from the totals.
    if COL_MONTH in df.columns:
        df[COL_MONTH] = df[COL_MONTH].astype(str).str.strip().str.title()
        unrecognized = ~df[COL_MONTH].isin(MONTH_ORDER)
        if unrecognized.any() and COL_SENT_DATE in df.columns:
            derived = pd.to_datetime(
                df.loc[unrecognized, COL_SENT_DATE], errors="coerce"
            ).dt.month_name()
            df.loc[unrecognized, COL_MONTH] = derived

    return df


def fmt(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(int(round(n)))


def pct(num, den):
    return round(num / den * 100, 1) if den else 0.0


def split_by_status(df):
    delivered = df[df[COL_STATUS] == STATUS_DELIVERED].copy()
    bounced   = df[df[COL_STATUS] == STATUS_BOUNCED].copy()
    dropped   = df[df[COL_STATUS] == STATUS_DROPPED].copy()
    return delivered, bounced, dropped


def build_dashboard(df, output_path):

    # ── Embed full raw dataset for client-side filtering ────────────────
    raw_cols = [c for c in [COL_STATUS, COL_MONTH, COL_CAMPAIGN, COL_TA, COL_MARKET, COL_OPENS, COL_CLICKS] if c in df.columns]
    raw_df = df[raw_cols].copy()
    # Fill NaN so JSON serialises cleanly
    for col in [COL_OPENS, COL_CLICKS]:
        if col in raw_df.columns:
            raw_df[col] = raw_df[col].fillna(0).astype(int)
    for col in [COL_STATUS, COL_MONTH, COL_CAMPAIGN, COL_TA, COL_MARKET]:
        if col in raw_df.columns:
            raw_df[col] = raw_df[col].fillna("").astype(str)
    raw_json = raw_df.to_json(orient="records")

    # ── All unique months + campaigns + TAs for dropdowns ───────────────
    all_months = [m for m in MONTH_ORDER if COL_MONTH in df.columns and m in df[COL_MONTH].values]
    if COL_CAMPAIGN in df.columns:
        all_campaigns_raw = sorted(df[COL_CAMPAIGN].dropna().unique().tolist())
        all_campaigns = [c for c in all_campaigns_raw
                         if str(c).strip().lower() not in ['nan','','unassigned'] + list(EXCLUDED_CAMPAIGNS)]
    else:
        all_campaigns = []
    if COL_TA in df.columns:
        all_ta = sorted([t for t in df[COL_TA].dropna().unique().tolist()
                         if str(t).strip().lower() not in ['nan','','unassigned']])
    else:
        all_ta = []

    delivered_df, bounced_df, dropped_df = split_by_status(df)

    # ── Summary KPIs ────────────────────────────────────────────────────
    total_delivered = len(delivered_df)
    total_opens     = int(delivered_df[COL_OPENS].sum())  if COL_OPENS  in delivered_df.columns else 0
    total_clicks    = int(delivered_df[COL_CLICKS].sum()) if COL_CLICKS in delivered_df.columns else 0
    total_bounced   = len(bounced_df)
    total_dropped   = len(dropped_df)
    or_rate         = pct(total_opens,  total_delivered)
    ctr_rate        = pct(total_clicks, total_delivered)

    # ── Monthly trend ────────────────────────────────────────────────────
    if COL_MONTH in delivered_df.columns:
        m_grp = delivered_df.groupby(COL_MONTH).agg(
            Delivered=(COL_STATUS, "count"),
            Opens=(COL_OPENS,  "sum"),
            Clicks=(COL_CLICKS, "sum")
        ).reset_index()
        m_grp = m_grp[m_grp[COL_MONTH].isin(MONTH_ORDER)]
        m_grp = m_grp[m_grp["Delivered"] > 0]
        m_grp["_order"] = m_grp[COL_MONTH].apply(lambda m: MONTH_ORDER.index(m))
        m_grp = m_grp.sort_values("_order")
        trend_labels    = m_grp[COL_MONTH].tolist()
        trend_delivered = [int(v) for v in m_grp["Delivered"].tolist()]
        trend_or        = [pct(o, d) for o, d in zip(m_grp["Opens"],  m_grp["Delivered"])]
        trend_ctr       = [pct(c, d) for c, d in zip(m_grp["Clicks"], m_grp["Delivered"])]
        present = [m for m in MONTH_ORDER if m in trend_labels]
        month_range = f"{present[0]} – {present[-1]} 2025" if present else "2025"
    else:
        trend_labels = trend_delivered = trend_or = trend_ctr = []
        month_range = "2025"

    # ── Bounce + Drop stacked ────────────────────────────────────────────
    bounce_counts = {}
    drop_counts   = {}
    if COL_MONTH in bounced_df.columns:
        bounce_counts = bounced_df.groupby(COL_MONTH).size().to_dict()
    if COL_MONTH in dropped_df.columns:
        drop_counts = dropped_df.groupby(COL_MONTH).size().to_dict()
    trend_bounced = [bounce_counts.get(m, 0) for m in trend_labels]
    trend_dropped = [drop_counts.get(m, 0)   for m in trend_labels]

    # ── Campaign performance ─────────────────────────────────────────────
    if COL_CAMPAIGN in delivered_df.columns:
        c_grp = delivered_df.groupby(COL_CAMPAIGN).agg(
            Delivered=(COL_STATUS, "count"),
            Opens=(COL_OPENS,  "sum"),
            Clicks=(COL_CLICKS, "sum")
        ).reset_index()
        # Remove nan / blank / unassigned campaign names
        c_grp = c_grp[~c_grp[COL_CAMPAIGN].str.lower().isin(['nan', '', 'unassigned'])]
        # Exclude specific campaign names (exact match, case-insensitive)
        c_grp = c_grp[~c_grp[COL_CAMPAIGN].str.lower().isin(EXCLUDED_CAMPAIGNS)]
        c_grp = c_grp[c_grp["Delivered"] >= MIN_DELIVERED_FOR_RANKING]
        c_grp["OR"]  = c_grp.apply(lambda r: pct(r["Opens"],  r["Delivered"]), axis=1)
        c_grp["CTR"] = c_grp.apply(lambda r: pct(r["Clicks"], r["Delivered"]), axis=1)
        c_top = c_grp.sort_values("OR", ascending=False).head(TOP_N_CAMPAIGNS)
        camp_labels = c_top[COL_CAMPAIGN].tolist()
        camp_or     = c_top["OR"].tolist()
        camp_ctr    = c_top["CTR"].tolist()
        camp_rows   = [
            (r[COL_CAMPAIGN], int(r["Delivered"]), int(r["Opens"]), r["OR"], int(r["Clicks"]), r["CTR"])
            for _, r in c_top.iterrows()
        ]
    else:
        camp_labels = camp_or = camp_ctr = camp_rows = []

    # ── TA performance ───────────────────────────────────────────────────
    if COL_TA in delivered_df.columns:
        ta_grp = delivered_df.groupby(COL_TA).agg(
            Delivered=(COL_STATUS, "count"),
            Opens=(COL_OPENS,  "sum"),
            Clicks=(COL_CLICKS, "sum")
        ).reset_index()
        # Remove nan / blank / unassigned TA names
        ta_grp = ta_grp[~ta_grp[COL_TA].str.lower().isin(['nan', '', 'unassigned'])]
        ta_grp = ta_grp[ta_grp["Delivered"] > 0]
        ta_grp["OR"]  = ta_grp.apply(lambda r: pct(r["Opens"],  r["Delivered"]), axis=1)
        ta_grp["CTR"] = ta_grp.apply(lambda r: pct(r["Clicks"], r["Delivered"]), axis=1)
        ta_grp = ta_grp.sort_values("Delivered", ascending=False)
        ta_labels    = ta_grp[COL_TA].tolist()
        ta_delivered = [int(v) for v in ta_grp["Delivered"].tolist()]
        ta_or        = ta_grp["OR"].tolist()
        ta_ctr       = ta_grp["CTR"].tolist()
        ta_rows      = [
            (r[COL_TA], int(r["Delivered"]), int(r["Opens"]), r["OR"], int(r["Clicks"]), r["CTR"])
            for _, r in ta_grp.iterrows()
        ]
    else:
        ta_labels = ta_delivered = ta_or = ta_ctr = ta_rows = []

    # ── Market performance (excluded markets already filtered in load_and_clean) ──
    if COL_MARKET in delivered_df.columns:
        mkt_grp = delivered_df.groupby(COL_MARKET).agg(
            Delivered=(COL_STATUS, "count"),
            Opens=(COL_OPENS,  "sum"),
            Clicks=(COL_CLICKS, "sum")
        ).reset_index()
        # Remove nan / blank / unassigned market names
        mkt_grp = mkt_grp[~mkt_grp[COL_MARKET].str.lower().isin(['nan', '', 'unassigned'])]
        mkt_grp = mkt_grp[mkt_grp["Delivered"] > 0]
        mkt_grp["OR"]  = mkt_grp.apply(lambda r: pct(r["Opens"],  r["Delivered"]), axis=1)
        mkt_grp["CTR"] = mkt_grp.apply(lambda r: pct(r["Clicks"], r["Delivered"]), axis=1)
        mkt_grp = mkt_grp.sort_values("Delivered", ascending=False).head(12)
        mkt_labels    = mkt_grp[COL_MARKET].tolist()
        mkt_delivered = [int(v) for v in mkt_grp["Delivered"].tolist()]
        mkt_or        = mkt_grp["OR"].tolist()
    else:
        mkt_labels = mkt_delivered = mkt_or = []

    # ── Delivery health donut ────────────────────────────────────────────
    health_data   = [total_delivered, total_bounced, total_dropped]
    health_labels = ["Delivered", "Bounced", "Dropped"]

    # ── Gradient colours for campaign bar ───────────────────────────────
    n_camp = max(len(camp_or), 1)
    camp_colors = []
    for i in range(len(camp_or)):
        t = i / max(n_camp - 1, 1)
        r = int(0x00 + t * (0xB7 - 0x00))
        g = int(0x85 + t * (0xDD - 0x85))
        b = int(0x7B + t * (0xD8 - 0x7B))
        camp_colors.append(f"rgb({r},{g},{b})")

    ta_donut_colors = ["#00857B","#0A2540","#1A6FAF","#1B8A4E","#0EA5A0","#7C5CBF","#C2410C","#D97706","#059669"]
    mkt_bar_colors  = ["#00857B","#1A6FAF","#0EA5A0","#1B8A4E","#7C5CBF","#C2410C","#D97706","#059669","#0A2540","#64748B","#F59E0B","#6366F1"]

    # Compute right-axis suggestedMax for combo chart (give labels breathing room)
    all_rates = trend_or + trend_ctr
    max_rate  = max(all_rates) if all_rates else 10
    suggested_max_rate = round(max_rate * 2.2, 1)

    # ── HTML table helpers ───────────────────────────────────────────────
    def camp_table_rows():
        html = ""
        for i, (camp, deliv, opens, orr, clicks, ctr) in enumerate(camp_rows, 1):
            html += f"""<tr>
              <td><span class="rank">{i}</span>{camp}</td>
              <td>{deliv:,}</td>
              <td>{opens:,}</td>
              <td class="rate">{orr}%</td>
              <td>{clicks:,}</td>
              <td class="rate">{ctr}%</td>
            </tr>"""
        return html

    def ta_table_rows():
        html = ""
        for ta, deliv, opens, orr, clicks, ctr in ta_rows:
            html += f"""<tr>
              <td>{ta}</td>
              <td>{deliv:,}</td>
              <td>{opens:,}</td>
              <td class="rate">{orr}%</td>
              <td>{clicks:,}</td>
              <td class="rate">{ctr}%</td>
            </tr>"""
        return html

    rows_camp = camp_table_rows()
    rows_ta   = ta_table_rows()

    # ─────────────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>REE Email Performance Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Raleway:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  /* Base — Raleway for all body/word text */
  body {{
    font-family: 'Raleway', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #EDF2F7; padding: 24px; min-width: 1100px;
  }}
  .dash {{ max-width: 1280px; margin: 0 auto; }}

  /* ── Header ── */
  .dash-header {{
    background: linear-gradient(135deg, #0A2540 0%, #0D3259 60%, #1A4A7A 100%);
    color: #fff; padding: 20px 30px;
    display: flex; align-items: center; justify-content: space-between;
    border-radius: 14px 14px 0 0;
  }}
  .dash-title-row {{ display: flex; align-items: center; gap: 12px; }}
  .dash-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 21px; font-weight: 600; letter-spacing: -0.3px;
  }}
  .dash-badge {{
    background: #00857B; color: #fff;
    font-family: 'Raleway', sans-serif;
    font-size: 11px; padding: 4px 12px; border-radius: 20px; font-weight: 500;
  }}
  .month-pill {{
    background: rgba(255,255,255,0.12); color: #fff;
    font-family: 'Raleway', sans-serif;
    font-size: 12px; padding: 6px 16px; border-radius: 20px;
    border: 1px solid rgba(255,255,255,0.2);
  }}
  .note-pill {{
    background: rgba(0,133,123,0.25); color: #7EDDD6;
    font-family: 'Raleway', sans-serif;
    font-size: 10.5px; padding: 4px 12px; border-radius: 20px;
    border: 1px solid rgba(0,133,123,0.35); margin-top: 8px; display: inline-block;
  }}

  .dash-body {{ background: #F0F4F8; padding: 22px; border-radius: 0 0 14px 14px; }}

  /* ── KPI cards ── */
  .metric-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 22px; }}
  .metric-card {{ background: #fff; border-radius: 10px; padding: 16px 18px; border-top: 3px solid transparent; }}
  .metric-card.c1 {{ border-color: #00857B; }}
  .metric-card.c2 {{ border-color: #0A2540; }}
  .metric-card.c3 {{ border-color: #1A6FAF; }}
  .metric-card.c4 {{ border-color: #1B8A4E; }}
  .metric-card.c5 {{ border-color: #E53E3E; }}
  .metric-card.c6 {{ border-color: #D97706; }}

  /* Raleway for label words, Montserrat for numbers */
  .metric-label {{
    font-family: 'Raleway', sans-serif;
    font-size: 10px; color: #64748B; margin-bottom: 6px;
    letter-spacing: 0.5px; text-transform: uppercase; font-weight: 600;
  }}
  .metric-value {{
    font-family: 'Montserrat', sans-serif;
    font-size: 26px; font-weight: 700; color: #0A2540; line-height: 1;
  }}
  .metric-sub {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #94A3B8; margin-top: 4px;
  }}

  /* Section labels — Montserrat */
  .section-label {{
    font-family: 'Montserrat', sans-serif;
    font-size: 12px; font-weight: 700; color: #475569;
    margin: 6px 0 10px 2px; text-transform: uppercase; letter-spacing: 0.6px;
  }}

  /* ── Chart grid ── */
  .charts-row  {{ display: grid; gap: 16px; margin-bottom: 18px; }}
  .r1  {{ grid-template-columns: 1fr; }}
  .r2  {{ grid-template-columns: 1.15fr 0.85fr; }}
  .r3  {{ grid-template-columns: 1fr 1fr 1fr; }}
  .r2b {{ grid-template-columns: 0.85fr 1.15fr; }}
  .chart-card  {{ background: #fff; border-radius: 10px; padding: 18px; }}

  /* Montserrat for card headings */
  .card-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 13px; font-weight: 600; color: #0A2540; margin-bottom: 2px;
  }}
  /* Raleway for subtitles */
  .card-sub {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 14px;
  }}
  .chart-wrap  {{ position: relative; }}

  /* ── Tables ── */
  .table-card  {{ background: #fff; border-radius: 10px; padding: 18px; }}
  .tbl {{ width: 100%; font-size: 12px; border-collapse: collapse; }}
  .tbl thead tr {{ background: #0A2540; color: #fff; }}
  .tbl thead th {{
    font-family: 'Montserrat', sans-serif;
    padding: 9px 10px; text-align: left; font-weight: 600; white-space: nowrap;
  }}
  .tbl thead th:not(:first-child) {{ text-align: right; }}
  .tbl tbody tr:nth-child(even) {{ background: #F8FAFC; }}
  .tbl tbody tr:hover {{ background: #EFF8F7; }}
  .tbl tbody td {{
    font-family: 'Raleway', sans-serif;
    padding: 7px 10px; color: #334155; border-bottom: 0.5px solid #E2E8F0;
  }}
  .tbl tbody td:not(:first-child) {{ text-align: right; }}
  .tbl tbody td.rate {{
    font-family: 'Montserrat', sans-serif;
    color: #00857B; font-weight: 600;
  }}
  .rank {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; border-radius: 50%;
    background: #00857B; color: #fff;
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    margin-right: 7px; flex-shrink: 0;
  }}

  /* ── Insight box ── */
  .insight-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 18px; }}
  .insight-card {{
    background: linear-gradient(135deg, #00857B08, #1A6FAF0A);
    border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 16px;
  }}
  .insight-icon {{ font-size: 18px; margin-bottom: 6px; }}
  .insight-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 700; color: #0A2540;
    text-transform: uppercase; letter-spacing: 0.4px; margin-bottom: 4px;
  }}
  .insight-text {{
    font-family: 'Raleway', sans-serif;
    font-size: 12px; color: #475569; line-height: 1.5;
  }}
  .insight-text strong {{ color: #00857B; font-family: 'Montserrat', sans-serif; }}
</style>
</head>
<body>
<div class="dash">

  <!-- ── Header ─────────────────────────────────────────────────────── -->
  <div class="dash-header">
    <div>
      <div class="dash-title-row">
        <span class="dash-title">REE Email Performance Dashboard</span>
        <span class="dash-badge">Delivered Emails Only</span>
      </div>
      <span class="note-pill">📊 Opens &amp; Clicks reflect delivered-status rows only · Bounced &amp; Dropped from STATUS column</span>
    </div>
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
      <span class="month-pill">📅 {month_range}</span>
      <select id="filterMonth" onchange="applyFilters()" style="background:#1A3A5C;color:#fff;border:1.5px solid rgba(255,255,255,0.45);border-radius:20px;padding:6px 32px 6px 14px;font-family:'Raleway',sans-serif;font-size:12px;cursor:pointer;outline:none;appearance:auto;-webkit-appearance:auto;">
        <option value="" style="background:#1A3A5C;color:#fff;">📅 All Months</option>
        {''.join(f'<option value="{m}" style="background:#1A3A5C;color:#fff;">{m}</option>' for m in all_months)}
      </select>
      <select id="filterCampaign" onchange="applyFilters()" style="background:#1A3A5C;color:#fff;border:1.5px solid rgba(255,255,255,0.45);border-radius:20px;padding:6px 32px 6px 14px;font-family:'Raleway',sans-serif;font-size:12px;cursor:pointer;outline:none;appearance:auto;-webkit-appearance:auto;max-width:220px;">
        <option value="" style="background:#1A3A5C;color:#fff;">📣 All Campaigns</option>
        {''.join(f'<option value="{c}" style="background:#1A3A5C;color:#fff;">{c}</option>' for c in all_campaigns)}
      </select>
      <select id="filterTA" onchange="applyFilters()" style="background:#1A3A5C;color:#fff;border:1.5px solid rgba(255,255,255,0.45);border-radius:20px;padding:6px 32px 6px 14px;font-family:'Raleway',sans-serif;font-size:12px;cursor:pointer;outline:none;appearance:auto;-webkit-appearance:auto;max-width:180px;">
        <option value="" style="background:#1A3A5C;color:#fff;">🧬 All TAs</option>
        {''.join(f'<option value="{t}" style="background:#1A3A5C;color:#fff;">{t}</option>' for t in all_ta)}
      </select>
    </div>
  </div>

  <div class="dash-body">

    <!-- ── KPI Row ──────────────────────────────────────────────────── -->
    <p class="section-label">Summary KPIs</p>
    <div class="metric-grid">
      <div class="metric-card c1">
        <div class="metric-label">Total Delivered</div>
        <div class="metric-value" id="kpi-delivered">—</div>
        <div class="metric-sub">Emails delivered</div>
      </div>
      <div class="metric-card c2">
        <div class="metric-label">Total Opens</div>
        <div class="metric-value" id="kpi-opens">—</div>
        <div class="metric-sub">On delivered only</div>
      </div>
      <div class="metric-card c3">
        <div class="metric-label">Open Rate</div>
        <div class="metric-value" id="kpi-or">—</div>
        <div class="metric-sub">Opens / Delivered</div>
      </div>
      <div class="metric-card c4">
        <div class="metric-label">Total Clicks</div>
        <div class="metric-value" id="kpi-clicks">—</div>
        <div class="metric-sub">On delivered only</div>
      </div>
      <div class="metric-card c5">
        <div class="metric-label">Bounced</div>
        <div class="metric-value" id="kpi-bounced">—</div>
        <div class="metric-sub">STATUS = bounced</div>
      </div>
      <div class="metric-card c6">
        <div class="metric-label">Dropped</div>
        <div class="metric-value" id="kpi-dropped">—</div>
        <div class="metric-sub">STATUS = dropped</div>
      </div>
    </div>

    <!-- ── Insights ─────────────────────────────────────────────────── -->
    <p class="section-label">Key Insights</p>
    <div class="insight-grid">
      <div class="insight-card">
        <div class="insight-icon">📬</div>
        <div class="insight-title">Delivery Health</div>
        <div class="insight-text" id="insight-health">—</div>
      </div>
      <div class="insight-card">
        <div class="insight-icon">👁️</div>
        <div class="insight-title">Engagement</div>
        <div class="insight-text" id="insight-engagement">—</div>
      </div>
      <div class="insight-card">
        <div class="insight-icon">🏆</div>
        <div class="insight-title">Top Campaign</div>
        <div class="insight-text" id="insight-topcampaign">—</div>
      </div>
    </div>

    <!-- ── Row 1: Monthly Trend ──────────────────────────────────────── -->
    <p class="section-label">Monthly Performance Trend</p>
    <div class="charts-row r1">
      <div class="chart-card">
        <div class="card-title">Delivered Emails · OR% · CTR% by Month</div>
        <div class="card-sub">Bar = Delivered (left axis) · Lines = Rates (right axis) · delivered-status rows only</div>
        <div class="chart-wrap" style="height:280px">
          <canvas id="trendChart"></canvas>
        </div>
      </div>
    </div>

    <!-- ── Row 2: Bounce/Drop stacked + Delivery health donut ────────── -->
    <div class="charts-row r2">
      <div class="chart-card">
        <div class="card-title">Bounce &amp; Drop by Month</div>
        <div class="card-sub">Stacked — from STATUS column (not delivered rows)</div>
        <div class="chart-wrap" style="height:230px">
          <canvas id="bdChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-title">Delivery Health</div>
        <div class="card-sub">Share of total records by STATUS</div>
        <div class="chart-wrap" style="height:230px">
          <canvas id="healthDonut"></canvas>
        </div>
      </div>
    </div>

    <!-- ── Row 3: Campaign ranking + TA donut + TA radar ─────────────── -->
    <p class="section-label">Campaign &amp; TA Performance</p>
    <div class="charts-row r3">
      <div class="chart-card">
        <div class="card-title">Top {TOP_N_CAMPAIGNS} Campaigns by Open Rate</div>
        <div class="card-sub">Min {MIN_DELIVERED_FOR_RANKING} delivered · gradient = rank</div>
        <div class="chart-wrap" style="height:260px">
          <canvas id="campChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-title">TA — Delivered Share</div>
        <div class="card-sub">By Therapeutic Area</div>
        <div class="chart-wrap" style="height:260px">
          <canvas id="taDonutChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-title">TA — OR vs CTR</div>
        <div class="card-sub">Radar: engagement profile per TA</div>
        <div class="chart-wrap" style="height:260px">
          <canvas id="taRadarChart"></canvas>
        </div>
      </div>
    </div>

    <!-- ── Row 4: Market bar chart ───────────────────────────────────── -->
    <p class="section-label">Market Breakdown</p>
    <div class="charts-row r2b">
      <div class="chart-card">
        <div class="card-title">Delivered by Market</div>
        <div class="card-sub">Top markets · delivered rows only</div>
        <div class="chart-wrap" style="height:240px">
          <canvas id="mktChart"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <div class="card-title">Market Open Rate</div>
        <div class="card-sub">OR % per market</div>
        <div class="chart-wrap" style="height:240px">
          <canvas id="mktOrChart"></canvas>
        </div>
      </div>
    </div>

    <!-- ── Campaign Table ────────────────────────────────────────────── -->
    <p class="section-label">Campaign Detail — Top by OR%</p>
    <div class="table-card" style="margin-bottom:18px">
      <table class="tbl">
        <thead><tr>
          <th>Campaign</th><th>Delivered</th><th>Opens</th>
          <th>OR %</th><th>Clicks</th><th>CTR %</th>
        </tr></thead>
        <tbody id="campTableBody"></tbody>
      </table>
    </div>

    <!-- ── TA Table ──────────────────────────────────────────────────── -->
    <p class="section-label">Therapeutic Area Detail</p>
    <div class="table-card">
      <table class="tbl">
        <thead><tr>
          <th>TA</th><th>Delivered</th><th>Opens</th>
          <th>OR %</th><th>Clicks</th><th>CTR %</th>
        </tr></thead>
        <tbody id="taTableBody"></tbody>
      </table>
    </div>

  </div><!-- .dash-body -->
</div><!-- .dash -->

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-datalabels/2.2.0/chartjs-plugin-datalabels.min.js"></script>
<script>
Chart.register(ChartDataLabels);

const MONTSERRAT = 'Montserrat, sans-serif';
const RALEWAY    = 'Raleway, sans-serif';

// ── Raw data from Python ─────────────────────────────────────────────────
const RAW_DATA      = {raw_json};
const MONTH_ORDER   = {json.dumps(MONTH_ORDER)};
const EXCLUDED_CAMP = {json.dumps(list(EXCLUDED_CAMPAIGNS))};
const MIN_DELIVERED = {MIN_DELIVERED_FOR_RANKING};
const TOP_N         = {TOP_N_CAMPAIGNS};
const STATUS_DEL    = "delivered";
const STATUS_BNC    = "bounced";
const STATUS_DRP    = "dropped";
const COL_STATUS    = "{COL_STATUS}";
const COL_MONTH     = "{COL_MONTH}";
const COL_CAMPAIGN  = "{COL_CAMPAIGN}";
const COL_TA        = "{COL_TA}";
const COL_MARKET    = "{COL_MARKET}";
const COL_OPENS     = "{COL_OPENS}";
const COL_CLICKS    = "{COL_CLICKS}";

// ── Helpers ──────────────────────────────────────────────────────────────
function fmt(n) {{
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return Math.round(n).toString();
}}
function pct(num, den) {{ return den ? Math.round(num/den*1000)/10 : 0.0; }}

// ── Chart instances ──────────────────────────────────────────────────────
let chartTrend, chartBD, chartHealth, chartCamp, chartTADonut, chartTARadar, chartMkt, chartMktOR;

function getOrCreate(id, config) {{
  const el = document.getElementById(id);
  const existing = Chart.getChart(el);
  if (existing) existing.destroy();
  return new Chart(el, config);
}}

// ── Core: filter + recompute + redraw ────────────────────────────────────
function applyFilters() {{
  const selMonth    = document.getElementById('filterMonth').value;
  const selCampaign = document.getElementById('filterCampaign').value;
  const selTA       = document.getElementById('filterTA').value;

  // Filter rows
  let rows = RAW_DATA;
  if (selMonth)    rows = rows.filter(r => r[COL_MONTH]    === selMonth);
  if (selCampaign) rows = rows.filter(r => r[COL_CAMPAIGN] === selCampaign);
  if (selTA)       rows = rows.filter(r => r[COL_TA]       === selTA);

  const delivered = rows.filter(r => r[COL_STATUS] === STATUS_DEL);
  const bounced   = rows.filter(r => r[COL_STATUS] === STATUS_BNC);
  const dropped   = rows.filter(r => r[COL_STATUS] === STATUS_DRP);

  // ── KPIs ──────────────────────────────────────────────────────────────
  const totDel  = delivered.length;
  const totOpen = delivered.reduce((s,r) => s + (r[COL_OPENS]||0), 0);
  const totClk  = delivered.reduce((s,r) => s + (r[COL_CLICKS]||0), 0);
  const totBnc  = bounced.length;
  const totDrp  = dropped.length;
  const orRate  = pct(totOpen, totDel);
  const ctrRate = pct(totClk,  totDel);
  const ctoRate = pct(totClk,  totOpen);
  const total   = totDel + totBnc + totDrp;

  document.getElementById('kpi-delivered').textContent = fmt(totDel);
  document.getElementById('kpi-opens').textContent     = fmt(totOpen);
  document.getElementById('kpi-or').textContent        = orRate + '%';
  document.getElementById('kpi-clicks').textContent    = fmt(totClk);
  document.getElementById('kpi-bounced').textContent   = fmt(totBnc);
  document.getElementById('kpi-dropped').textContent   = fmt(totDrp);

  // ── Insights ──────────────────────────────────────────────────────────
  document.getElementById('insight-health').innerHTML =
    `<strong>${{fmt(totDel)}}</strong> emails successfully delivered. ` +
    `Bounce rate: <strong>${{pct(totBnc,total)}}%</strong> · Drop rate: <strong>${{pct(totDrp,total)}}%</strong>`;
  document.getElementById('insight-engagement').innerHTML =
    `Open rate of <strong>${{orRate}}%</strong> with CTR of <strong>${{ctrRate}}%</strong>. ` +
    `Click-to-open ratio: <strong>${{ctoRate}}%</strong>`;

  // ── Monthly trend ─────────────────────────────────────────────────────
  const monthMap = {{}};
  for (const r of delivered) {{
    const m = r[COL_MONTH];
    if (!MONTH_ORDER.includes(m)) continue;
    if (!monthMap[m]) monthMap[m] = {{del:0,open:0,clk:0}};
    monthMap[m].del++;
    monthMap[m].open += r[COL_OPENS]||0;
    monthMap[m].clk  += r[COL_CLICKS]||0;
  }}
  const trendMonths = MONTH_ORDER.filter(m => monthMap[m] && monthMap[m].del > 0);
  const trendDel  = trendMonths.map(m => monthMap[m].del);
  const trendOR   = trendMonths.map(m => pct(monthMap[m].open, monthMap[m].del));
  const trendCTR  = trendMonths.map(m => pct(monthMap[m].clk,  monthMap[m].del));

  const bncMap = {{}}, drpMap = {{}};
  for (const r of bounced) {{ bncMap[r[COL_MONTH]] = (bncMap[r[COL_MONTH]]||0)+1; }}
  for (const r of dropped) {{ drpMap[r[COL_MONTH]] = (drpMap[r[COL_MONTH]]||0)+1; }}
  const trendBnc = trendMonths.map(m => bncMap[m]||0);
  const trendDrp = trendMonths.map(m => drpMap[m]||0);

  const allRates = [...trendOR,...trendCTR];
  const sugMax   = allRates.length ? Math.round(Math.max(...allRates)*2.2*10)/10 : 10;

  // ── Campaign grouping ─────────────────────────────────────────────────
  const campMap = {{}};
  for (const r of delivered) {{
    const c = (r[COL_CAMPAIGN]||'').trim();
    if (!c || c.toLowerCase() === 'nan' || c.toLowerCase() === 'unassigned') continue;
    if (EXCLUDED_CAMP.includes(c.toLowerCase())) continue;
    if (!campMap[c]) campMap[c] = {{del:0,open:0,clk:0}};
    campMap[c].del++;
    campMap[c].open += r[COL_OPENS]||0;
    campMap[c].clk  += r[COL_CLICKS]||0;
  }}
  const campArr = Object.entries(campMap)
    .filter(([,v]) => v.del >= MIN_DELIVERED)
    .map(([name,v]) => ({{name, del:v.del, open:v.open, clk:v.clk,
      or:pct(v.open,v.del), ctr:pct(v.clk,v.del)}}))
    .sort((a,b) => b.or - a.or)
    .slice(0, TOP_N);

  const campLabels = campArr.map(c=>c.name);
  const campOR     = campArr.map(c=>c.or);
  const campCTR    = campArr.map(c=>c.ctr);
  const nCamp = Math.max(campArr.length,1);
  const campColors = campArr.map((_,i) => {{
    const t = i/Math.max(nCamp-1,1);
    const r = Math.round(0x00 + t*(0xB7-0x00));
    const g = Math.round(0x85 + t*(0xDD-0x85));
    const b = Math.round(0x7B + t*(0xD8-0x7B));
    return `rgb(${{r}},${{g}},${{b}})`;
  }});

  // Top campaign insight
  if (campArr.length) {{
    const top = campArr[0];
    document.getElementById('insight-topcampaign').innerHTML =
      `<strong>${{top.name}}</strong> leads with <strong>${{top.or}}%</strong> open rate (${{top.del.toLocaleString()}} delivered)`;
  }} else {{
    document.getElementById('insight-topcampaign').innerHTML = 'No campaign data for this selection';
  }}

  // ── TA grouping ───────────────────────────────────────────────────────
  const taMap = {{}};
  for (const r of delivered) {{
    const t = (r[COL_TA]||'').trim();
    if (!t || t.toLowerCase()==='nan' || t.toLowerCase()==='unassigned') continue;
    if (!taMap[t]) taMap[t] = {{del:0,open:0,clk:0}};
    taMap[t].del++;
    taMap[t].open += r[COL_OPENS]||0;
    taMap[t].clk  += r[COL_CLICKS]||0;
  }}
  const taArr = Object.entries(taMap)
    .filter(([,v]) => v.del > 0)
    .map(([name,v]) => ({{name, del:v.del, open:v.open, clk:v.clk,
      or:pct(v.open,v.del), ctr:pct(v.clk,v.del)}}))
    .sort((a,b) => b.del - a.del);
  const taLabels    = taArr.map(t=>t.name);
  const taDel       = taArr.map(t=>t.del);
  const taOR        = taArr.map(t=>t.or);
  const taCTR       = taArr.map(t=>t.ctr);
  const taDonutColors = ["#00857B","#0A2540","#1A6FAF","#1B8A4E","#0EA5A0","#7C5CBF","#C2410C","#D97706","#059669"];

  // ── Market grouping ───────────────────────────────────────────────────
  const mktMap = {{}};
  for (const r of delivered) {{
    const m = (r[COL_MARKET]||'').trim();
    if (!m || m.toLowerCase()==='nan' || m.toLowerCase()==='unassigned') continue;
    if (!mktMap[m]) mktMap[m] = {{del:0,open:0,clk:0}};
    mktMap[m].del++;
    mktMap[m].open += r[COL_OPENS]||0;
    mktMap[m].clk  += r[COL_CLICKS]||0;
  }}
  const mktArr = Object.entries(mktMap)
    .filter(([,v]) => v.del > 0)
    .map(([name,v]) => ({{name, del:v.del, or:pct(v.open,v.del)}}))
    .sort((a,b) => b.del - a.del)
    .slice(0, 12);
  const mktLabels = mktArr.map(m=>m.name);
  const mktDel    = mktArr.map(m=>m.del);
  const mktOR     = mktArr.map(m=>m.or);
  const mktBarColors = ["#00857B","#1A6FAF","#0EA5A0","#1B8A4E","#7C5CBF","#C2410C","#D97706","#059669","#0A2540","#64748B","#F59E0B","#6366F1"];

  // ── Tables ────────────────────────────────────────────────────────────
  document.getElementById('campTableBody').innerHTML = campArr.map((c,i) =>
    `<tr><td><span class="rank">${{i+1}}</span>${{c.name}}</td>
     <td>${{c.del.toLocaleString()}}</td><td>${{c.open.toLocaleString()}}</td>
     <td class="rate">${{c.or}}%</td><td>${{c.clk.toLocaleString()}}</td>
     <td class="rate">${{c.ctr}}%</td></tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:#94A3B8;padding:16px">No campaigns meet the minimum delivered threshold for this filter</td></tr>';

  document.getElementById('taTableBody').innerHTML = taArr.map(t =>
    `<tr><td>${{t.name}}</td>
     <td>${{t.del.toLocaleString()}}</td><td>${{t.open.toLocaleString()}}</td>
     <td class="rate">${{t.or}}%</td><td>${{t.clk.toLocaleString()}}</td>
     <td class="rate">${{t.ctr}}%</td></tr>`).join('') || '<tr><td colspan="6" style="text-align:center;color:#94A3B8;padding:16px">No data for this filter</td></tr>';

  // ── Charts ────────────────────────────────────────────────────────────

  // 1. Trend combo
  chartTrend = getOrCreate('trendChart', {{
    data: {{
      labels: trendMonths,
      datasets: [
        {{
          type:'bar', label:'Delivered', data:trendDel,
          backgroundColor:'#CFE3F0', borderRadius:6, borderSkipped:false,
          yAxisID:'y', order:2,
          datalabels:{{ anchor:'center', align:'center', color:'#0A2540',
            font:{{size:10,weight:'600',family:MONTSERRAT}},
            formatter:v => v>=1000?(v/1000).toFixed(1)+'K':v }}
        }},
        {{
          type:'line', label:'OR %', data:trendOR,
          borderColor:'#00857B', backgroundColor:'#00857B', tension:0,
          pointRadius:5, pointBackgroundColor:'#00857B', borderWidth:2.5,
          yAxisID:'y1', order:1,
          datalabels:{{ align:'top', anchor:'end', offset:6,
            color:'#00857B', font:{{size:10,weight:'600',family:MONTSERRAT}},
            formatter:v=>v+'%' }}
        }},
        {{
          type:'line', label:'CTR %', data:trendCTR,
          borderColor:'#1A6FAF', backgroundColor:'#1A6FAF', tension:0,
          pointRadius:5, pointBackgroundColor:'#1A6FAF', borderWidth:2.5,
          yAxisID:'y1', order:1,
          datalabels:{{ align:'bottom', anchor:'end', offset:6,
            color:'#1A6FAF', font:{{size:10,weight:'600',family:MONTSERRAT}},
            formatter:v=>v+'%' }}
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
          ticks:{{color:'#64748B',font:{{size:10,family:MONTSERRAT}},callback:v=>v>=1000?(v/1000).toFixed(0)+'K':v}},
          title:{{display:true,text:'Delivered',color:'#94A3B8',font:{{size:10,family:RALEWAY}}}}}},
        y1:{{position:'right',min:0,suggestedMax:sugMax,grid:{{display:false}},
          ticks:{{color:'#64748B',font:{{size:10,family:MONTSERRAT}},callback:v=>v+'%'}},
          title:{{display:true,text:'Rate %',color:'#94A3B8',font:{{size:10,family:RALEWAY}}}}}}
      }}
    }}
  }});

  // 2. Bounce + Drop stacked
  chartBD = getOrCreate('bdChart', {{
    type:'bar',
    data:{{
      labels:trendMonths,
      datasets:[
        {{
          label:'Bounced', data:trendBnc,
          backgroundColor:'#E53E3E', borderRadius:4, borderSkipped:false, stack:'bd',
          datalabels:{{anchor:'center',align:'center',color:'#fff',
            font:{{size:10,weight:'600',family:MONTSERRAT}},
            formatter:(v,ctx)=>{{
              const total=ctx.chart.data.datasets.reduce((s,ds)=>s+(ds.data[ctx.dataIndex]||0),0);
              return total>0&&v>0?v:'';
            }}}}
        }},
        {{
          label:'Dropped', data:trendDrp,
          backgroundColor:'#D97706', borderRadius:4, borderSkipped:false, stack:'bd',
          datalabels:{{anchor:'center',align:'center',color:'#fff',
            font:{{size:10,weight:'600',family:MONTSERRAT}},
            formatter:v=>v>0?v:''}}
        }}
      ]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      layout:{{padding:{{top:10}}}},
      plugins:{{
        legend:{{position:'top',align:'end',
          labels:{{color:'#334155',font:{{size:11,family:RALEWAY}},boxWidth:12,usePointStyle:true}}}},
        tooltip:{{bodyFont:{{family:MONTSERRAT,size:12}},titleFont:{{family:RALEWAY,size:12}}}}
      }},
      scales:{{
        x:{{stacked:true,grid:{{display:false}},ticks:{{color:'#64748B',font:{{size:11,family:RALEWAY}}}}}},
        y:{{stacked:true,grid:{{color:'rgba(0,0,0,0.05)'}},
          ticks:{{color:'#64748B',font:{{size:10,family:MONTSERRAT}}}}}}
      }}
    }}
  }});

  // 3. Health donut
  chartHealth = getOrCreate('healthDonut', {{
    type:'doughnut',
    data:{{
      labels:['Delivered','Bounced','Dropped'],
      datasets:[{{
        data:[totDel,totBnc,totDrp],
        backgroundColor:['#00857B','#E53E3E','#D97706'],
        borderColor:'#fff', borderWidth:2
      }}]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false, cutout:'62%',
      plugins:{{
        legend:{{position:'bottom',
          labels:{{color:'#334155',font:{{size:11,family:RALEWAY}},boxWidth:10,padding:10}}}},
        datalabels:{{
          color:'#fff', font:{{size:11,weight:'700',family:MONTSERRAT}},
          formatter:(v,ctx)=>{{
            const tot=ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);
            const p=tot?(v/tot*100):0;
            return p>=5?p.toFixed(1)+'%':'';
          }}
        }}
      }}
    }}
  }});

  // 4. Campaign bar
  chartCamp = getOrCreate('campChart', {{
    type:'bar',
    data:{{
      labels:campLabels,
      datasets:[{{
        data:campOR, backgroundColor:campColors,
        borderRadius:5, borderSkipped:false
      }}]
    }},
    options:{{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      layout:{{padding:{{right:40}}}},
      plugins:{{
        legend:{{display:false}},
        datalabels:{{anchor:'end',align:'end',
          color:'#0A2540',font:{{size:10,weight:'600',family:MONTSERRAT}},
          formatter:v=>v+'%'}}
      }},
      scales:{{
        x:{{display:false}},
        y:{{grid:{{display:false}},ticks:{{color:'#334155',font:{{size:10,family:RALEWAY}}}}}}
      }}
    }}
  }});

  // 5. TA donut
  chartTADonut = getOrCreate('taDonutChart', {{
    type:'doughnut',
    data:{{
      labels:taLabels,
      datasets:[{{
        data:taDel,
        backgroundColor:taDonutColors.slice(0,taLabels.length),
        borderColor:'#fff', borderWidth:2
      }}]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false, cutout:'58%',
      plugins:{{
        legend:{{position:'bottom',
          labels:{{color:'#334155',font:{{size:10,family:RALEWAY}},boxWidth:10,padding:8}}}},
        datalabels:{{
          color:'#fff', font:{{size:10,weight:'600',family:MONTSERRAT}},
          formatter:(v,ctx)=>{{
            const tot=ctx.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);
            const p=tot?(v/tot*100):0;
            return p>=5?p.toFixed(0)+'%':'';
          }}
        }}
      }}
    }}
  }});

  // 6. TA radar
  chartTARadar = getOrCreate('taRadarChart', {{
    type:'radar',
    data:{{
      labels:taLabels,
      datasets:[
        {{
          label:'OR %', data:taOR,
          borderColor:'#00857B', backgroundColor:'rgba(0,133,123,0.15)',
          pointBackgroundColor:'#00857B', borderWidth:2,
          datalabels:{{display:false}}
        }},
        {{
          label:'CTR %', data:taCTR,
          borderColor:'#1A6FAF', backgroundColor:'rgba(26,111,175,0.12)',
          pointBackgroundColor:'#1A6FAF', borderWidth:2,
          datalabels:{{display:false}}
        }}
      ]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      plugins:{{
        legend:{{position:'top',align:'end',
          labels:{{color:'#334155',font:{{size:11,family:RALEWAY}},boxWidth:10,usePointStyle:true}}}},
        datalabels:{{display:false}}
      }},
      scales:{{r:{{
        angleLines:{{color:'#E2E8F0'}}, grid:{{color:'#E2E8F0'}},
        pointLabels:{{color:'#334155',font:{{size:10,family:RALEWAY}}}},
        ticks:{{display:false,backdropColor:'transparent'}},
        suggestedMin:0
      }}}}
    }}
  }});

  // 7. Market delivered bar
  chartMkt = getOrCreate('mktChart', {{
    type:'bar',
    data:{{
      labels:mktLabels,
      datasets:[{{
        label:'Delivered', data:mktDel,
        backgroundColor:mktBarColors.slice(0,mktLabels.length),
        borderRadius:5, borderSkipped:false,
        datalabels:{{anchor:'end',align:'top',
          color:'#0A2540',font:{{size:9,weight:'600',family:MONTSERRAT}},
          formatter:v=>v>=1000?(v/1000).toFixed(1)+'K':v}}
      }}]
    }},
    options:{{
      responsive:true, maintainAspectRatio:false,
      layout:{{padding:{{top:20}}}},
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{grid:{{display:false}},ticks:{{color:'#334155',font:{{size:10,family:RALEWAY}},maxRotation:30,minRotation:20}}}},
        y:{{grid:{{color:'rgba(0,0,0,0.05)'}},
          ticks:{{color:'#64748B',font:{{size:10,family:MONTSERRAT}},callback:v=>v>=1000?(v/1000).toFixed(0)+'K':v}}}}
      }}
    }}
  }});

  // 8. Market OR bar
  chartMktOR = getOrCreate('mktOrChart', {{
    type:'bar',
    data:{{
      labels:mktLabels,
      datasets:[{{
        data:mktOR,
        backgroundColor:'#00857B80', borderColor:'#00857B',
        borderWidth:1.5, borderRadius:5, borderSkipped:false,
        datalabels:{{anchor:'end',align:'end',
          color:'#00857B',font:{{size:9,weight:'600',family:MONTSERRAT}},
          formatter:v=>v+'%'}}
      }}]
    }},
    options:{{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      layout:{{padding:{{right:36}}}},
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{display:false}},
        y:{{grid:{{display:false}},ticks:{{color:'#334155',font:{{size:10,family:RALEWAY}}}}}}
      }}
    }}
  }});
}}

// ── Boot ─────────────────────────────────────────────────────────────────
applyFilters();
</script>
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard saved: {output_path}")


# ── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ree_dashboard.py <your_excel_file.xlsx>")
        print("Example: python ree_dashboard.py REE_Data.xlsx")
        sys.exit(1)

    excel_path = sys.argv[1]
    if not os.path.exists(excel_path):
        print(f"Error: File not found — {excel_path}")
        sys.exit(1)

    html_out = str(Path(excel_path).stem) + "_dashboard.html"
    df = load_and_clean(excel_path)
    build_dashboard(df, html_out)
