import pandas as pd
import sys
import os
import json
from pathlib import Path

# ── CONFIG ──────────────────────────────────────────────────────────────
COL_BINDER      = "Binder Name"
COL_SLIDE       = "Slide Name"
COL_TOTAL_USE   = "Total Use (CLM)"
COL_UTILIZATION = "Slide Utilization"
COL_AVG_DUR     = "Avg. CLM Slide Duration"
# ────────────────────────────────────────────────────────────────────────

def clean_slide_name(raw):
    if not raw or str(raw).strip() == '':
        return ''
    parts = str(raw).strip().split('_')
    if len(parts) <= 3:
        return str(raw).strip()
    parts = parts[3:]
    br_idx = None
    for i, p in enumerate(parts):
        if p.upper() == 'BR':
            br_idx = i
            break
    if br_idx is not None:
        parts = parts[:br_idx]
    return '_'.join(parts)

def duration_to_seconds(series):
    """
    Convert the Avg. CLM Slide Duration column to exact seconds.

    Excel stores this column in a time format (e.g. 00:01:18.86). Depending
    on the file, pandas can parse this column several different ways:
      - a full datetime64 (Timestamp) column
      - a column of individual datetime.time objects
      - a column of strings like "00:01:18.86"
      - plain numeric values (already seconds, or an Excel day-fraction)

    None of these are ever rounded here. Every path converts via
    pd.to_timedelta(...).total_seconds(), which preserves the exact
    fractional-second value, instead of letting pandas treat the value
    as an absolute Timestamp (which is what caused 78.86 -> 78.9).
    """
    import datetime as _dt

    s = series.copy()

    def normalize(v):
        # datetime64 (Timestamp) cell -> "HH:MM:SS.ffffff" string
        if isinstance(v, pd.Timestamp):
            return v.strftime('%H:%M:%S.%f')
        # datetime.time cell -> "HH:MM:SS.ffffff" string
        if isinstance(v, _dt.time):
            return f"{v.hour:02d}:{v.minute:02d}:{v.second:02d}.{v.microsecond:06d}"
        # already a timedelta -> leave as-is, to_timedelta passes it through
        if isinstance(v, _dt.timedelta):
            return v
        return v

    s = s.map(normalize)

    # pd.to_timedelta interprets bare numbers as nanoseconds by default,
    # which is wrong for this column (a bare number here means seconds).
    # Route plain numeric values through unit='s' explicitly so they don't
    # get silently mis-scaled.
    is_numeric_mask = s.map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool))
    td = pd.Series(pd.NaT, index=s.index, dtype='timedelta64[ns]')
    if is_numeric_mask.any():
        td.loc[is_numeric_mask] = pd.to_timedelta(s[is_numeric_mask], unit='s', errors='coerce')
    if (~is_numeric_mask).any():
        td.loc[~is_numeric_mask] = pd.to_timedelta(s[~is_numeric_mask], errors='coerce')

    seconds = td.dt.total_seconds()

    # Anything that still failed to parse (NaT) -> fall back to treating
    # the original raw value as a plain numeric seconds value.
    missing = seconds.isna()
    if missing.any():
        fallback = pd.to_numeric(series[missing], errors='coerce')
        seconds.loc[missing] = fallback

    return seconds.fillna(0.0)



def load_and_clean(path):
    df = pd.read_excel(path, header=0)
    df.columns = df.columns.str.strip()

    # ── Duration column (col E = index 4): convert to exact seconds via
    # pd.to_timedelta(...).total_seconds(), never treated as a Timestamp.
    # This preserves full precision (78.86 stays 78.86, no rounding).
    duration_seconds = duration_to_seconds(df.iloc[:, 4])

    # ── KPIs: always C2=col[2], D2=col[3], E2=col[4] — read by position ──
    raw = df.iloc[0]
    kpi_total_use = pd.to_numeric(raw.iloc[2], errors='coerce')
    kpi_util      = pd.to_numeric(str(raw.iloc[3]).replace('%', '').strip(), errors='coerce')
    kpi_avg_dur   = duration_seconds.iloc[0] if len(duration_seconds) else 0.0
    kpi_total_use = 0 if pd.isna(kpi_total_use) else float(kpi_total_use)
    kpi_util      = 0 if pd.isna(kpi_util)      else float(kpi_util)
    kpi_avg_dur   = 0 if pd.isna(kpi_avg_dur)   else float(kpi_avg_dur)
    # Excel stores % as decimals (0.322 = 32.2%) — scale up if needed
    if kpi_util <= 1.5:
        kpi_util = kpi_util * 100

    # Attach exact per-row durations (still aligned 1:1 with df, including
    # the totals row at index 0, before it gets dropped below).
    df['avg_dur_raw'] = duration_seconds

    # ── Drop totals row, then filter slide rows ──────────────────────────
    df = df.drop(index=0).reset_index(drop=True)
    df = df[df[COL_SLIDE].notna()]
    df = df[df[COL_SLIDE].astype(str).str.strip() != '']
    df = df[~df[COL_SLIDE].astype(str).str.lower().str.contains('total', na=False)]

    # Total Use
    df[COL_TOTAL_USE] = pd.to_numeric(df[COL_TOTAL_USE], errors='coerce').fillna(0)

    # Utilization: strip % sign then convert
    df[COL_UTILIZATION] = (
        df[COL_UTILIZATION]
        .astype(str)
        .str.replace('%', '', regex=False)
        .str.strip()
    )
    df[COL_UTILIZATION] = pd.to_numeric(df[COL_UTILIZATION], errors='coerce').fillna(0)
    # If stored as decimal (0.023 = 2.3%) scale up
    sample = df[COL_UTILIZATION][df[COL_UTILIZATION] > 0]
    if len(sample) and sample.median() < 1.5:
        df[COL_UTILIZATION] = df[COL_UTILIZATION] * 100

    # Drop blank/junk rows
    df = df[df[COL_TOTAL_USE] > 0]

    # Clean slide names
    df['slide_clean'] = df[COL_SLIDE].apply(clean_slide_name)
    df = df[df['slide_clean'] != '']

    return df, kpi_total_use, kpi_util, kpi_avg_dur

def aggregate(df):
    grp = df.groupby('slide_clean', as_index=False).agg(
        total_use=(COL_TOTAL_USE,    'sum'),
        utilization=(COL_UTILIZATION, 'sum'),
        avg_dur=('avg_dur_raw',      'mean')   # use positional column, not name-matched
    )
    grp['avg_dur'] = pd.to_numeric(grp['avg_dur'], errors='coerce').fillna(0)
    grp = grp.sort_values('total_use', ascending=False).reset_index(drop=True)
    return grp

def fmt_dur(seconds):
    """Format a duration in seconds without artificial rounding, the way
    Excel's General format would show it: full precision, trailing zeros
    trimmed, no thousands separators."""
    if seconds is None:
        return "—"
    s = repr(float(seconds))
    # Python repr gives full float precision; trim trailing zeros/dot
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s

def build_dashboard(df, kpi_total_use, kpi_util, kpi_avg_dur, output_path):
    total_uses = int(kpi_total_use)
    total_util = float(kpi_util)
    avg_dur    = float(kpi_avg_dur)

    agg = aggregate(df)

    top_n       = min(10, max(5, len(agg)))
    table_rows  = agg.head(top_n)
    chart_rows  = agg.head(10).copy()

    table_json  = json.dumps(table_rows.to_dict(orient='records'))
    chart_json  = json.dumps(chart_rows.to_dict(orient='records'))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CLM Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Raleway:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Raleway', sans-serif;
    background: #E8EEF4;
    padding: 24px;
    min-width: 1100px;
  }}
  .dash {{ max-width: 1200px; margin: 0 auto; }}
  .dash-header {{
    background: #152548;
    color: #fff;
    padding: 18px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 12px 12px 0 0;
  }}
  .dash-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 20px; font-weight: 600; color: #fff;
  }}
  .dash-badge {{
    background: #00857B; color: #fff;
    font-family: 'Raleway', sans-serif;
    font-size: 11px; padding: 4px 12px;
    border-radius: 20px; margin-left: 14px;
  }}
  .dash-body {{ background: #F0F4F8; padding: 22px; border-radius: 0 0 12px 12px; }}
  .metric-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    margin-bottom: 22px;
  }}
  .metric-card {{
    background: #fff; border-radius: 10px;
    padding: 16px 18px; border-top: 3px solid;
  }}
  .metric-card.c1 {{ border-color: #152548; }}
  .metric-card.c2 {{ border-color: #00857B; }}
  .metric-card.c3 {{ border-color: #92D050; }}
  .metric-icon {{ font-size: 20px; margin-bottom: 8px; }}
  .metric-label {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 4px;
  }}
  .metric-value {{
    font-family: 'Montserrat', sans-serif;
    font-size: 24px; font-weight: 600; color: #152548;
  }}
  .table-card {{
    background: #fff; border-radius: 10px;
    padding: 20px; margin-bottom: 18px;
  }}
  .chart-card {{
    background: #fff; border-radius: 10px;
    padding: 20px;
  }}
  .card-title {{
    font-family: 'Montserrat', sans-serif;
    font-size: 13px; font-weight: 600; color: #152548; margin-bottom: 2px;
  }}
  .card-sub {{
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; margin-bottom: 16px;
  }}
  .tbl {{ width: 100%; font-size: 12px; border-collapse: collapse; }}
  .tbl thead tr {{ background: #152548; color: #fff; }}
  .tbl thead th {{
    font-family: 'Montserrat', sans-serif;
    padding: 10px 14px; text-align: left; font-weight: 600; font-size: 11px;
  }}
  .tbl thead th.right {{ text-align: right; }}
  .tbl tbody tr:nth-child(even) {{ background: #F8FAFC; }}
  .tbl tbody tr:hover {{ background: #F0FDF9; }}
  .tbl tbody td {{
    font-family: 'Raleway', sans-serif;
    padding: 9px 14px; color: #334155;
    border-bottom: 0.5px solid #E2E8F0;
    font-size: 12px;
  }}
  .tbl tbody td.num {{
    font-family: 'Montserrat', sans-serif;
    text-align: right; font-weight: 600;
  }}
  .tbl tbody td.num.hi {{ color: #00857B; }}
  .rank {{ color: #94A3B8; font-size: 11px; width: 22px; display: inline-block; }}
  .slide-name {{
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 500; color: #152548;
  }}
  .bar-bg {{
    display: inline-block;
    background: #E2E8F0; border-radius: 3px;
    height: 5px; width: 80px;
    vertical-align: middle; margin-left: 8px; overflow: hidden;
  }}
  .bar-fill {{
    display: block; height: 100%;
    background: #92D050; border-radius: 3px;
  }}
  .no-data {{
    text-align: center; color: #94A3B8;
    font-family: 'Raleway', sans-serif;
    font-size: 12px; padding: 32px 0;
  }}
</style>
</head>
<body>
<div class="dash">
  <div class="dash-header">
    <div style="display:flex;align-items:center;gap:10px;">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#92D050" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>
      </svg>
      <span class="dash-title">CLM Slide Analytics</span>
      <span class="dash-badge">MSD · CLM</span>
    </div>
    <div style="font-family:'Raleway',sans-serif;font-size:12px;color:rgba(255,255,255,0.5);">
      MSD Internal
    </div>
  </div>
  <div class="dash-body">
    <div class="metric-grid">
      <div class="metric-card c1">
        <div class="metric-icon">🖥️</div>
        <div class="metric-label">Total CLM Uses</div>
        <div class="metric-value">{total_uses:,}</div>
      </div>
      <div class="metric-card c2">
        <div class="metric-icon">📊</div>
        <div class="metric-label">Total Slide Utilization</div>
        <div class="metric-value">{fmt_dur(total_util)}%</div>
      </div>
      <div class="metric-card c3">
        <div class="metric-icon">⏱️</div>
        <div class="metric-label">Avg Slide Duration</div>
        <div class="metric-value">{fmt_dur(avg_dur)}s</div>
      </div>
    </div>
    <div class="table-card">
      <div class="card-title" style="margin-bottom:4px;">Slide Performance Table</div>
      <div class="card-sub">Sorted by Total Use (CLM) · Top {top_n} slides</div>
      <table class="tbl">
        <thead>
          <tr>
            <th>#</th>
            <th>Slide Name</th>
            <th class="right">Total Use (CLM)</th>
            <th class="right">Slide Utilization</th>
            <th class="right">Avg. Duration</th>
          </tr>
        </thead>
        <tbody id="slideTableBody"></tbody>
      </table>
    </div>
    <div class="chart-card" style="margin-top:18px;">
      <div class="card-title">Top Slides by Total CLM Use</div>
      <div class="card-sub">Top 10 slides ranked by usage count</div>
      <div style="position:relative;width:100%;height:300px;">
        <canvas id="clmChart"></canvas>
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
const TABLE_DATA = {table_json};
const CHART_DATA = {chart_json};

function fmtDur(seconds) {{
  // Full precision, no artificial rounding — matches Excel General format
  if (seconds == null) return '—';
  let s = String(seconds);
  if (s.includes('.')) s = s.replace(/0+$/, '').replace(/\\.$/, '');
  return s;
}}

function renderTable() {{
  const tbody = document.getElementById('slideTableBody');
  if (!TABLE_DATA.length) {{
    tbody.innerHTML = '<tr><td colspan="5"><div class="no-data">No data found</div></td></tr>';
    return;
  }}
  const maxUse = TABLE_DATA[0].total_use || 1;
  tbody.innerHTML = TABLE_DATA.map((r, i) => {{
    const barW = Math.max(2, Math.round((r.total_use / maxUse) * 80));
    const util = (r.utilization != null && r.utilization > 0) ? fmtDur(r.utilization) + '%' : '—';
    const dur  = (r.avg_dur != null && r.avg_dur > 0) ? fmtDur(r.avg_dur) + 's' : '—';
    return `<tr>
      <td><span class="rank">${{i+1}}</span></td>
      <td>
        <span class="slide-name">${{r.slide_clean}}</span>
        <span class="bar-bg"><span class="bar-fill" style="width:${{barW}}px"></span></span>
      </td>
      <td class="num hi">${{r.total_use.toLocaleString()}}</td>
      <td class="num">${{util}}</td>
      <td class="num">${{dur}}</td>
    </tr>`;
  }}).join('');
}}

function renderChart() {{
  const labels = CHART_DATA.map(r => r.slide_clean);
  const values = CHART_DATA.map(r => r.total_use);
  const colors = values.map((_, i) => i === 0 ? '#152548' : '#00857B');
  new Chart(document.getElementById('clmChart'), {{
    type: 'bar',
    data: {{
      labels,
      datasets: [{{ data: values, backgroundColor: colors, borderRadius: 6, borderSkipped: false }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      layout: {{ padding: {{ top: 28 }} }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{ label: ctx => '  Uses: ' + ctx.parsed.y.toLocaleString() }},
          bodyFont: {{ family: MONTSERRAT, size: 12 }},
          titleFont: {{ family: RALEWAY, size: 11 }}
        }},
        datalabels: {{
          anchor: 'end', align: 'end',
          color: '#152548',
          font: {{ size: 10, weight: '600', family: MONTSERRAT }},
          formatter: v => v >= 1000 ? (v/1000).toFixed(1) + 'K' : v
        }}
      }},
      scales: {{
        x: {{
          grid: {{ display: false }},
          ticks: {{ color: '#64748B', font: {{ size: 10, family: RALEWAY }}, maxRotation: 40, minRotation: 30 }}
        }},
        y: {{
          grid: {{ color: 'rgba(0,0,0,0.05)' }},
          ticks: {{
            color: '#64748B',
            font: {{ size: 11, family: MONTSERRAT }},
            callback: v => v >= 1000 ? (v/1000).toFixed(1) + 'K' : v
          }}
        }}
      }}
    }}
  }});
}}

renderTable();
renderChart();
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


# ── MAIN ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clm_dashboard.py <your_excel_file.xlsx>")
        sys.exit(1)

    excel_path = sys.argv[1]
    if not os.path.exists(excel_path):
        print(f"Error: File not found - {excel_path}")
        sys.exit(1)

    html_out = str(Path(excel_path).stem) + "_clm_dashboard.html"
    df, kpi_total_use, kpi_util, kpi_avg_dur = load_and_clean(excel_path)
    build_dashboard(df, kpi_total_use, kpi_util, kpi_avg_dur, html_out)

    try:
        from playwright.sync_api import sync_playwright
        abs_path = str(Path(html_out).resolve()).replace("\\", "/")
        pdf_out = html_out.replace(".html", ".pdf")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(f"file:///{abs_path}")
            page.wait_for_timeout(2500)
            page.pdf(
                path=pdf_out,
                width="1280px", height="900px",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"}
            )
            browser.close()
        os.remove(html_out)
        print(f"Dashboard saved: {pdf_out}")
    except Exception as e:
        print(f"Note: PDF export failed ({e}). HTML saved: {html_out}")
