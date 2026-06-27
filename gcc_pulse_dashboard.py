import pandas as pd
import sys
import os
import json
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────
COL_MONTH       = "Month"
COL_SESSIONS    = "Sessions"
COL_ACTIVE      = "Active users"
COL_NEW_USERS   = "New users"
COL_ENG_TIME    = "Engagement Time"
COL_TA          = "TA"
COL_LANDING     = "Landing page"
COL_PLATFORM    = "Platform"

MONTH_ORDER = ["January","February","March","April","May","June",
               "July","August","September","October","November","December"]

PLATFORMS = ["LinkedIn", "Instagram", "Facebook"]
# ────────────────────────────────────────────────────────────────────────

def load_and_clean(path):
    df = pd.read_excel(path)
    df.columns = df.columns.str.strip()

    def normalize_ta(val):
        v = str(val).strip().lower()
        if v.startswith("dia"):   return "Diabetes"
        if v.startswith("hac"):   return "HAC"
        if v.startswith("onc"):   return "Oncology"
        if v.startswith("vacc"):  return "Vaccines"
        return str(val).strip()

    if COL_TA in df.columns:
        df[COL_TA] = df[COL_TA].astype(str).str.strip()
        df[COL_TA] = df[COL_TA].apply(normalize_ta)
        # Replace 'nan' string with empty string — keep these rows
        df[COL_TA] = df[COL_TA].apply(lambda x: '' if x.lower() == 'nan' else x)

    # Normalize Platform column
    if COL_PLATFORM in df.columns:
        df[COL_PLATFORM] = df[COL_PLATFORM].astype(str).str.strip()
        df[COL_PLATFORM] = df[COL_PLATFORM].apply(
            lambda x: next((p for p in PLATFORMS if p.lower() in x.lower()), x) if x and x.lower() != 'nan' else 'Unknown'
        )
    else:
        df[COL_PLATFORM] = 'Unknown'

    for col in [COL_SESSIONS, COL_ACTIVE, COL_NEW_USERS, COL_ENG_TIME]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    numeric_cols = [c for c in [COL_SESSIONS, COL_ACTIVE, COL_NEW_USERS, COL_ENG_TIME] if c in df.columns]
    df = df.dropna(subset=numeric_cols, how='all')

    for col in numeric_cols:
        df[col] = df[col].fillna(0)

    if COL_MONTH in df.columns:
        df = df[df[COL_MONTH].notna()]
        df = df[df[COL_MONTH].isin(MONTH_ORDER)]

    return df

def sort_months(months):
    return sorted(months, key=lambda m: MONTH_ORDER.index(m) if m in MONTH_ORDER else 99)

def fmt(n):
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(int(round(n)))

def build_dashboard(df, output_path):
    # Serialize full raw data to JSON for client-side filtering
    raw_records = []
    for _, row in df.iterrows():
        raw_records.append({
            "month":   row.get(COL_MONTH, ""),
            "ta":      row.get(COL_TA, ""),
            "platform": row.get(COL_PLATFORM, "Unknown"),
            "active":  float(row.get(COL_ACTIVE, 0)),
            "new":     float(row.get(COL_NEW_USERS, 0)),
            "sessions":float(row.get(COL_SESSIONS, 0)),
            "eng":     float(row.get(COL_ENG_TIME, 0)),
            "landing": str(row.get(COL_LANDING, "")) if COL_LANDING in df.columns else ""
        })

    all_months = [m for m in MONTH_ORDER if m in df[COL_MONTH].unique()]
    KNOWN_TAS  = ["Diabetes", "HAC", "Oncology", "Vaccines"]
    all_tas    = [ta for ta in KNOWN_TAS if ta in df[COL_TA].values]
    all_platforms = sorted([p for p in df[COL_PLATFORM].unique() if p and p != 'nan'])

    raw_json       = json.dumps(raw_records)
    months_json    = json.dumps(all_months)
    tas_json       = json.dumps(all_tas)
    platforms_json = json.dumps(all_platforms)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GCC Pulse Analytics Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Raleway:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Raleway', -apple-system, BlinkMacSystemFont, sans-serif;
    background: #E8EEF4; padding: 24px; min-width: 1100px;
  }}
  .dash {{ max-width: 1200px; margin: 0 auto; }}

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

  /* ── FILTER BAR ── */
  .filter-bar {{
    background: #fff;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 18px;
    display: flex;
    align-items: flex-start;
    gap: 28px;
    flex-wrap: wrap;
    box-shadow: 0 1px 4px rgba(10,37,64,0.07);
  }}
  .filter-group {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    flex: 1;
    min-width: 200px;
  }}
  .filter-label {{
    font-family: 'Montserrat', sans-serif;
    font-size: 11px;
    font-weight: 600;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}
  .dropdown-select {{
    font-family: 'Raleway', sans-serif;
    font-size: 12px;
    font-weight: 500;
    padding: 8px 12px;
    border-radius: 6px;
    border: 1.5px solid #CBD5E1;
    background: #fff;
    color: #475569;
    cursor: pointer;
    transition: all 0.15s;
    min-width: 160px;
  }}
  .dropdown-select:hover {{
    border-color: #00857B;
    background: #F0FDF9;
  }}
  .dropdown-select:focus {{
    outline: none;
    border-color: #00857B;
    box-shadow: 0 0 0 3px rgba(0,133,123,0.1);
  }}
  .pill-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }}
  .pill {{
    font-family: 'Raleway', sans-serif;
    font-size: 12px;
    font-weight: 500;
    padding: 5px 13px;
    border-radius: 20px;
    border: 1.5px solid #CBD5E1;
    background: #F8FAFC;
    color: #475569;
    cursor: pointer;
    transition: all 0.15s;
    user-select: none;
    white-space: nowrap;
  }}
  .pill:hover {{
    border-color: #00857B;
    color: #00857B;
    background: #F0FDF9;
  }}
  .pill.active {{
    background: #0A2540;
    border-color: #0A2540;
    color: #fff;
    font-weight: 600;
  }}

  /* Reset button */
  .filter-reset-wrap {{
    display: flex;
    align-items: flex-end;
    padding-bottom: 2px;
    margin-left: auto;
  }}
  .reset-btn {{
    font-family: 'Raleway', sans-serif;
    font-size: 12px;
    font-weight: 600;
    padding: 7px 18px;
    border-radius: 20px;
    border: 1.5px solid #E2E8F0;
    background: #fff;
    color: #94A3B8;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
    white-space: nowrap;
  }}
  .reset-btn:hover {{
    border-color: #EF4444;
    color: #EF4444;
    background: #FFF5F5;
  }}
  .reset-btn svg {{ flex-shrink: 0; }}

  /* Active filter indicator in header */
  .filter-active-badge {{
    display: none;
    background: #EF4444;
    color: #fff;
    font-family: 'Montserrat', sans-serif;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 10px;
    margin-left: 8px;
    vertical-align: middle;
  }}

  /* Metric cards */
  .metric-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 14px; margin-bottom: 22px; }}
  .metric-card {{ background: #fff; border-radius: 10px; padding: 16px 18px; border-top: 3px solid; transition: box-shadow 0.2s; }}
  .metric-card.c1 {{ border-color: #00857B; }} .metric-card.c2 {{ border-color: #0A2540; }}
  .metric-card.c3 {{ border-color: #1A6FAF; }} .metric-card.c4 {{ border-color: #1B8A4E; }}
  .metric-card.c5 {{ border-color: #0EA5A0; }}
  .metric-icon {{ font-size: 20px; margin-bottom: 8px; }}
  .metric-label {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 4px;
  }}
  .metric-value {{
    font-family: 'Montserrat', sans-serif;
    font-size: 24px; font-weight: 600; color: #0A2540;
  }}

  /* Chart cards */
  .charts-row {{ display: grid; gap: 16px; margin-bottom: 18px; }}
  .r2 {{ grid-template-columns: 1fr 1fr; }}
  .r3 {{ grid-template-columns: 1fr 1fr 1fr; }}
  .chart-card {{ background: #fff; border-radius: 10px; padding: 18px; }}
  .card-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 13px; font-weight: 600; color: #0A2540; margin-bottom: 2px;
  }}
  .card-sub {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 16px;
  }}

  /* Tables */
  .tables-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .table-card {{ background: #fff; border-radius: 10px; padding: 18px; }}
  .tbl {{ width: 100%; font-size: 12px; border-collapse: collapse; }}
  .tbl thead tr {{ background: #0A2540; color: #fff; }}
  .tbl thead th {{
    font-family: 'Montserrat', sans-serif;
    padding: 9px 12px; text-align: left; font-weight: 600;
  }}
  .tbl thead th:last-child {{ text-align: right; }}
  .tbl tbody tr:nth-child(even) {{ background: #F8FAFC; }}
  .tbl tbody td {{
    font-family: 'Raleway', sans-serif;
    padding: 8px 12px; color: #334155; border-bottom: 0.5px solid #E2E8F0;
  }}
  .tbl tbody td:last-child {{
    font-family: 'Montserrat', sans-serif;
    text-align: right; font-weight: 600; color: #00857B;
  }}
  .rank {{ color: #94A3B8; font-size: 11px; width: 20px; display: inline-block; }}
  .bar-mini {{ display: inline-block; height: 6px; border-radius: 3px; vertical-align: middle; margin-left: 6px; opacity: 0.65; }}

  /* No data state */
  .no-data {{
    text-align: center; color: #94A3B8;
    font-family: 'Raleway', sans-serif;
    font-size: 12px; padding: 24px 0;
  }}
</style>
</head>
<body>
<div class="dash">
  <div class="dash-header">
    <div style="display:flex;align-items:center;gap:10px;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#00857B" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
      <span class="dash-title">GCC Pulse Analytics</span>
      <span class="dash-badge">MSD · GCC Pulse</span>
      <span class="filter-active-badge" id="filterBadge">Filtered</span>
    </div>
    <div class="month-pill" id="headerPill">📅 All Months · 2025</div>
  </div>

  <div class="dash-body">

    <!-- FILTER BAR -->
    <div class="filter-bar">
      <div class="filter-group">
        <div class="filter-label">Month</div>
        <select id="monthDropdown" class="dropdown-select" onchange="handleFilterChange()">
          <option value="">All Months</option>
        </select>
      </div>
      <div class="filter-group">
        <div class="filter-label">Therapy Area (TA)</div>
        <select id="taDropdown" class="dropdown-select" onchange="handleFilterChange()">
          <option value="">All TAs</option>
        </select>
      </div>
      <div class="filter-reset-wrap">
        <button class="reset-btn" id="resetBtn" onclick="resetFilters()">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><path d="M3.51 15a9 9 0 1 0 .49-3.77"></path></svg>
          Reset
        </button>
      </div>
    </div>

    <!-- KPI CARDS -->
    <div class="metric-grid" style="grid-template-columns: repeat(4, 1fr);">
      <div class="metric-card c1">
        <div class="metric-icon">👥</div>
        <div class="metric-label">Active Users</div>
        <div class="metric-value" id="kpi-active">—</div>
      </div>
      <div class="metric-card c5">
        <div class="metric-icon">🖥️</div>
        <div class="metric-label">Sessions</div>
        <div class="metric-value" id="kpi-sessions">—</div>
      </div>
      <div class="metric-card c2">
        <div class="metric-icon">🆕</div>
        <div class="metric-label">New Users</div>
        <div class="metric-value" id="kpi-new">—</div>
      </div>
      <div class="metric-card c4">
        <div class="metric-icon">⏱️</div>
        <div class="metric-label">Avg Engagement Time</div>
        <div class="metric-value" id="kpi-eng">—</div>
      </div>
    </div>

    <div class="charts-row r2" style="margin-bottom:18px;">
      <div class="chart-card">
        <div class="card-title">Active Users — Monthly Trend</div>
        <div class="card-sub">Sum of active users per month</div>
        <div style="position:relative;width:100%;height:220px;"><canvas id="trendChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">New Users — Monthly Trend</div>
        <div class="card-sub">Sum of new users per month</div>
        <div style="position:relative;width:100%;height:220px;"><canvas id="newUsersChart"></canvas></div>
      </div>
    </div>

    <div class="charts-row r3" style="margin-bottom:18px;">
      <div class="chart-card">
        <div class="card-title">TA by Active Users</div>
        <div class="card-sub">Total active users per therapy area</div>
        <div style="position:relative;width:100%;height:200px;"><canvas id="taUsersChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">TA by Sessions</div>
        <div class="card-sub">Total sessions per therapy area</div>
        <div style="position:relative;width:100%;height:200px;"><canvas id="taSessionsChart"></canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">Avg Engagement Time by TA</div>
        <div class="card-sub">Average engagement time per therapy area</div>
        <div style="position:relative;width:100%;height:200px;"><canvas id="taEngChart"></canvas></div>
      </div>
    </div>

    <div class="tables-row">
      <div class="table-card">
        <div class="card-title">Top Pages — Active Users</div>
        <div class="card-sub">Ranked by total active users</div>
        <table class="tbl">
          <thead><tr><th>Landing Page</th><th>Users</th></tr></thead>
          <tbody id="topUsersBody"></tbody>
        </table>
      </div>
      <div class="table-card">
        <div class="card-title">Top Pages — Sessions</div>
        <div class="card-sub">Ranked by total sessions</div>
        <table class="tbl">
          <thead><tr><th>Landing Page</th><th>Sessions</th></tr></thead>
          <tbody id="topSessionsBody"></tbody>
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

// ── Raw data from Python ──────────────────────────────────────────────
const RAW = {raw_json};
const ALL_MONTHS = {months_json};
const ALL_TAS    = {tas_json};
const ALL_PLATFORMS = {platforms_json};

// ── Filter state ──────────────────────────────────────────────────────
let selMonth = '';
let selTA    = '';

// ── Chart instances ───────────────────────────────────────────────────
let charts = {{}};

// ── Helpers ───────────────────────────────────────────────────────────
function fmtNum(n) {{
  if (n >= 1000) return (n/1000).toFixed(1) + 'K';
  return Math.round(n).toString();
}}

function filteredData() {{
  return RAW.filter(r => {{
    const mOk = !selMonth || r.month === selMonth;
    const tOk = !selTA    || r.ta    === selTA;
    return mOk && tOk;
  }});
}}

function groupBy(arr, key, valKey, agg='sum') {{
  const map = {{}};
  arr.forEach(r => {{
    const k = r[key];
    if (!k || k === 'nan' || k === '') return;
    if (!map[k]) map[k] = {{ vals: [], count: 0 }};
    map[k].vals.push(r[valKey]);
    map[k].count++;
  }});
  return Object.entries(map).map(([k, {{vals, count}}]) => {{
    const sum = vals.reduce((a,b) => a+b, 0);
    return {{ label: k, value: agg === 'avg' ? (count ? sum/count : 0) : sum }};
  }});
}}

// ── Chart factory ─────────────────────────────────────────────────────
function makeBarChart(id, labels, data, colors, isFloat) {{
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id);
  charts[id] = new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels,
      datasets: [{{ data, backgroundColor: colors, borderRadius: 6, borderSkipped: false }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      layout: {{ padding: {{ top: 28 }} }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{ label: ctx => ' ' + ctx.parsed.y.toLocaleString() }},
          bodyFont: {{ family: MONTSERRAT, size: 12 }},
          titleFont: {{ family: RALEWAY, size: 12 }}
        }},
        datalabels: {{
          anchor: 'end', align: 'end',
          color: '#0A2540',
          font: {{ size: 11, weight: '600', family: MONTSERRAT }},
          formatter: v => isFloat ? v.toFixed(1) : (v >= 1000 ? (v/1000).toFixed(1)+'K' : v)
        }}
      }},
      scales: {{
        x: {{
          grid: {{ display: false }},
          ticks: {{ color: '#64748B', font: {{ size: 11, family: RALEWAY }} }}
        }},
        y: {{
          grid: {{ color: 'rgba(0,0,0,0.05)' }},
          ticks: {{
            color: '#64748B',
            font: {{ size: 11, family: MONTSERRAT }},
            callback: v => v >= 1000 ? (v/1000).toFixed(1)+'K' : v
          }}
        }}
      }}
    }}
  }});
}}

// ── Table renderer ────────────────────────────────────────────────────
function renderTable(tbodyId, rows, color) {{
  const tbody = document.getElementById(tbodyId);
  if (!rows.length) {{
    tbody.innerHTML = '<tr><td colspan="2"><div class="no-data">No data for selected filters</div></td></tr>';
    return;
  }}
  const maxVal = rows[0][1] || 1;
  tbody.innerHTML = rows.map(([page, val], i) => {{
    const barW = Math.max(2, Math.round((val / maxVal) * 60));
    return `<tr>
      <td><span class="rank">${{i+1}}</span>${{page}}<span class="bar-mini" style="width:${{barW}}px;background:${{color}};"></span></td>
      <td>${{val.toLocaleString()}}</td>
    </tr>`;
  }}).join('');
}}

// ── Main update ───────────────────────────────────────────────────────
function updateDashboard() {{
  const df = filteredData();

  // KPIs
  const totalActive   = df.reduce((s,r) => s + r.active, 0);
  const totalNew      = df.reduce((s,r) => s + r.new, 0);
  const totalSessions = df.reduce((s,r) => s + r.sessions, 0);
  const avgEng        = df.length ? df.reduce((s,r) => s + r.eng, 0) / df.length : 0;

  document.getElementById('kpi-active').textContent   = fmtNum(totalActive);
  document.getElementById('kpi-sessions').textContent = fmtNum(totalSessions);
  document.getElementById('kpi-new').textContent      = fmtNum(totalNew);
  document.getElementById('kpi-eng').textContent      = avgEng.toFixed(1);

  // Monthly trend — Active Users
  const trendMap = {{}};
  df.forEach(r => {{
    if (!r.month || !MONTH_ORDER.includes(r.month)) return;
    trendMap[r.month] = (trendMap[r.month] || 0) + r.active;
  }});
  const trendMonths = MONTH_ORDER.filter(m => trendMap[m] > 0);
  const trendVals   = trendMonths.map(m => Math.round(trendMap[m]));
  const trendColors = trendVals.map((_, i) => i === 0 ? '#0A2540' : '#00857B');
  makeBarChart('trendChart', trendMonths, trendVals, trendColors, false);

  // Monthly trend — New Users
  const newMap = {{}};
  df.forEach(r => {{
    if (!r.month || !MONTH_ORDER.includes(r.month)) return;
    newMap[r.month] = (newMap[r.month] || 0) + r.new;
  }});
  const newMonths = MONTH_ORDER.filter(m => newMap[m] > 0);
  const newVals   = newMonths.map(m => Math.round(newMap[m]));
  const newColors = newVals.map((_, i) => i === 0 ? '#0A2540' : '#1B8A4E');
  makeBarChart('newUsersChart', newMonths, newVals, newColors, false);

  // TA charts
  const taActive = groupBy(df, 'ta', 'active').filter(r => r.value > 0).sort((a,b) => b.value - a.value);
  makeBarChart('taUsersChart',
    taActive.map(r => r.label), taActive.map(r => Math.round(r.value)),
    Array(taActive.length).fill('#1A6FAF'), false);

  const taSess = groupBy(df, 'ta', 'sessions').filter(r => r.value > 0).sort((a,b) => b.value - a.value);
  makeBarChart('taSessionsChart',
    taSess.map(r => r.label), taSess.map(r => Math.round(r.value)),
    Array(taSess.length).fill('#0EA5A0'), false);

  const taEng = groupBy(df, 'ta', 'eng', 'avg').filter(r => r.value > 0).sort((a,b) => b.value - a.value);
  makeBarChart('taEngChart',
    taEng.map(r => r.label), taEng.map(r => parseFloat(r.value.toFixed(1))),
    Array(taEng.length).fill('#00857B'), true);

  // Top pages — only rows with a known TA, exclude /reference* and /therapeutic* pages
  const pageUserMap = {{}};
  const pageSessMap = {{}};
  df.forEach(r => {{
    if (!r.ta || r.ta === '') return;
    if (!r.landing || r.landing === 'nan' || r.landing === '') return;
    const lc = r.landing.toLowerCase().replace(/^\//, '');
    if (lc.startsWith('reference') || lc.startsWith('therapeutic')) return;
    pageUserMap[r.landing] = (pageUserMap[r.landing] || 0) + r.active;
    pageSessMap[r.landing] = (pageSessMap[r.landing] || 0) + r.sessions;
  }});
  const topUsers = Object.entries(pageUserMap).filter(([,v]) => v>0)
    .sort((a,b) => b[1]-a[1]).slice(0,8).map(([p,v]) => [p, Math.round(v)]);
  const topSess  = Object.entries(pageSessMap).filter(([,v]) => v>0)
    .sort((a,b) => b[1]-a[1]).slice(0,8).map(([p,v]) => [p, Math.round(v)]);
  renderTable('topUsersBody', topUsers, '#00857B');
  renderTable('topSessionsBody', topSess, '#1A6FAF');

  // Header pill — only show if a filter is active
  if (selMonth || selTA) {{
    let pillText = '📅 ';
    if (selMonth) pillText += selMonth;
    if (selMonth && selTA) pillText += ' · ';
    if (selTA) pillText += selTA;
    document.getElementById('headerPill').style.display = 'block';
    document.getElementById('headerPill').textContent = pillText;
  }} else {{
    document.getElementById('headerPill').style.display = 'none';
  }}

  // Filter active badge
  const isFiltered = selMonth || selTA;
  document.getElementById('filterBadge').style.display = isFiltered ? 'inline-block' : 'none';
}}

// ── Handlers ──────────────────────────────────────────────────────────
function handleFilterChange() {{
  selMonth = document.getElementById('monthDropdown').value;
  selTA    = document.getElementById('taDropdown').value;
  updateDashboard();
}}

// ── Pill builders ─────────────────────────────────────────────────────
function buildPills() {{
  const mp = document.getElementById('monthDropdown');
  ALL_MONTHS.forEach(m => {{
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = m;
    mp.appendChild(opt);
  }});

  const tp = document.getElementById('taDropdown');
  ALL_TAS.forEach(ta => {{
    const opt = document.createElement('option');
    opt.value = ta;
    opt.textContent = ta;
    tp.appendChild(opt);
  }});
}}


function resetFilters() {{
  selMonth = '';
  selTA    = '';
  document.getElementById('monthDropdown').value = '';
  document.getElementById('taDropdown').value    = '';
  updateDashboard();
}}

// ── Init ──────────────────────────────────────────────────────────────
buildPills();
updateDashboard();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

# ── MAIN ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python gcc_pulse_dashboard.py <your_excel_file.xlsx>")
        print("Example: python gcc_pulse_dashboard.py GCC_Pulse_Data.xlsx")
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
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"file:///{abs_path}")
            page.wait_for_timeout(2500)
            page.pdf(
                path=pdf_out,
                width="1280px",
                height="900px",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"}
            )
            browser.close()
        os.remove(html_out)
        print(f"Dashboard saved: {pdf_out}")
    except Exception as e:
        print(f"Note: PDF export failed ({e}). HTML file saved: {html_out}")
