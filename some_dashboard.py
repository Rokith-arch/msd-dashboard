"""
SoMe Social Media Dashboard — HTML generator.

Setup (one-time):
    pip install pandas openpyxl

Usage:
    python some_dashboard.py SoMe_Data.xlsx

Output:
    SoMe_Data_dashboard.html

Sheet layout expected:
  Sheet 1 (2025 baseline):
    A1=Social Media  B1=Followers  C1=Impressions  D1=Engagement
    A2=Instagram     A3=LinkedIn   A4=(optional 3rd row)
    B2:D4 = numbers

  Sheet 2 (2026 monthly):
    A1=Month
    B1=FB Followers  C1=FB Impressions  D1=FB Engagement
    E1=IG Followers  F1=IG Impressions  G1=IG Engagement
    H1=LI Followers  I1=LI Impressions  J1=LI Engagement
    B2:J6 = numbers (up to 5 months but will handle any row count)
"""

import pandas as pd
import sys
import os
import json
from pathlib import Path


# ── CONFIG ────────────────────────────────────────────────────────────────
# Sheet indices (0-based) or sheet names
SHEET_2025 = 0
SHEET_2026 = 1

# Column positions in Sheet 1 (0-based): A=0 B=1 C=2 D=3
S1_PLATFORM_COL = 0
S1_FOL_COL      = 1
S1_IMP_COL      = 2
S1_ENG_COL      = 3

# Column positions in Sheet 2 (0-based)
S2_MONTH_COL    = 0
S2_FB_FOL_COL   = 1
S2_FB_IMP_COL   = 2
S2_FB_ENG_COL   = 3
S2_IG_FOL_COL   = 4
S2_IG_IMP_COL   = 5
S2_IG_ENG_COL   = 6
S2_LI_FOL_COL   = 7
S2_LI_IMP_COL   = 8
S2_LI_ENG_COL   = 9
# ─────────────────────────────────────────────────────────────────────────


def load_2025(xl):
    """Read Sheet 1 baseline. Returns dict keyed by lowercased platform name."""
    df = xl.parse(SHEET_2025, header=0)
    df.columns = range(len(df.columns))   # force numeric column index
    result = {}
    for _, row in df.iterrows():
        plat = str(row[S1_PLATFORM_COL]).strip().lower()
        if plat in ('nan', ''):
            continue
        result[plat] = {
            'fol': _num(row[S1_FOL_COL]),
            'imp': _num(row[S1_IMP_COL]),
            'eng': _num(row[S1_ENG_COL]),
        }
    # Try to normalise keys to 'facebook'/'instagram'/'linkedin'
    normalised = {}
    for k, v in result.items():
        if 'face' in k or 'fb' in k:
            normalised['facebook'] = v
        elif 'insta' in k or 'ig' in k:
            normalised['instagram'] = v
        elif 'linked' in k or 'li' in k:
            normalised['linkedin'] = v
        else:
            normalised[k] = v
    return normalised


def load_2026(xl):
    """Read Sheet 2 monthly data. Returns month list + per-platform series."""
    df = xl.parse(SHEET_2026, header=0)
    df.columns = range(len(df.columns))

    months = [str(m).strip() for m in df.iloc[:, S2_MONTH_COL].tolist() if str(m).strip() not in ('nan', '')]

    def series(col):
        return [_num(v) for v in df.iloc[:len(months), col].tolist()]

    return {
        'months': months,
        'fb': {'fol': series(S2_FB_FOL_COL), 'imp': series(S2_FB_IMP_COL), 'eng': series(S2_FB_ENG_COL)},
        'ig': {'fol': series(S2_IG_FOL_COL), 'imp': series(S2_IG_IMP_COL), 'eng': series(S2_IG_ENG_COL)},
        'li': {'fol': series(S2_LI_FOL_COL), 'imp': series(S2_LI_IMP_COL), 'eng': series(S2_LI_ENG_COL)},
    }


def _num(v):
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def fmt(n):
    n = int(round(n))
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def pct_delta(v26, v25):
    if v25 == 0:
        return "N/A"
    p = round((v26 - v25) / v25 * 100)
    arrow = "↑" if p >= 0 else "↓"
    cl    = "up"   if p >= 0 else "down"
    return f'<span class="{cl}">{arrow} {abs(p)}% vs 2025</span>'


def build_dashboard(d25, d26, output_path):
    months = d26['months']

    # Convenience
    fb25 = d25.get('facebook', {'fol': 0, 'imp': 0, 'eng': 0})
    ig25 = d25.get('instagram', {'fol': 0, 'imp': 0, 'eng': 0})
    li25 = d25.get('linkedin',  {'fol': 0, 'imp': 0, 'eng': 0})

    fb26 = d26['fb']
    ig26 = d26['ig']
    li26 = d26['li']

    def last(lst): return lst[-1] if lst else 0
    def total(lst): return sum(lst)

    fb_fol26 = last(fb26['fol']);  ig_fol26 = last(ig26['fol']);  li_fol26 = last(li26['fol'])
    fb_imp26 = total(fb26['imp']); ig_imp26 = total(ig26['imp']); li_imp26 = total(li26['imp'])
    fb_eng26 = total(fb26['eng']); ig_eng26 = total(ig26['eng']); li_eng26 = total(li26['eng'])

    tot_imp = fb_imp26 + ig_imp26 + li_imp26 or 1

    # Radar: normalise share per metric
    def norm_pct(fb, ig, li):
        t = fb + ig + li or 1
        return [round(fb/t*100), round(ig/t*100), round(li/t*100)]

    nFol = norm_pct(fb_fol26, ig_fol26, li_fol26)
    nImp = norm_pct(fb_imp26, ig_imp26, li_imp26)
    nEng = norm_pct(fb_eng26, ig_eng26, li_eng26)

    # Insights
    imp_leader = max([('Facebook', fb_imp26), ('Instagram', ig_imp26), ('LinkedIn', li_imp26)], key=lambda x: x[1])
    er_fb = round(fb_eng26 / fb_fol26 * 100, 2) if fb_fol26 else 0
    er_ig = round(ig_eng26 / ig_fol26 * 100, 2) if ig_fol26 else 0
    er_li = round(li_eng26 / li_fol26 * 100, 2) if li_fol26 else 0
    eng_leader = max([('Facebook', er_fb), ('Instagram', er_ig), ('LinkedIn', er_li)], key=lambda x: x[1])

    ins1 = (f'Facebook grew <strong>{round((fb_fol26-fb25["fol"])/(fb25["fol"] or 1)*100)}%</strong>, '
            f'LinkedIn <strong>{round((li_fol26-li25["fol"])/(li25["fol"] or 1)*100)}%</strong>, '
            f'Instagram <strong>{round((ig_fol26-ig25["fol"])/(ig25["fol"] or 1)*100)}%</strong> vs 2025 baseline.')
    ins2 = (f'<strong>{imp_leader[0]}</strong> leads 2026 impressions with <strong>{fmt(imp_leader[1])}</strong> total — '
            f'a major step up from the 2025 baseline.')
    ins3 = (f'<strong>{eng_leader[0]}</strong> achieves highest engagement rate at '
            f'<strong>{eng_leader[1]}%</strong> per follower across all platforms.')

    month_range = f"{months[0]} – {months[-1]} 2026" if months else "2026"

    # JSON blobs for JS
    j = json.dumps
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SoMe Social Media Dashboard</title>
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

  .dash-header {{
    background: linear-gradient(135deg, #0A2540 0%, #0D3259 60%, #1A4A7A 100%);
    color: #fff; padding: 20px 28px;
    display: flex; align-items: center; justify-content: space-between;
    border-radius: 14px 14px 0 0;
  }}
  .dash-title {{ font-family: 'Montserrat', sans-serif; font-size: 20px; font-weight: 600; color: #fff; letter-spacing: -0.3px; }}
  .dash-sub   {{ font-family: 'Raleway', sans-serif; font-size: 11px; color: rgba(255,255,255,0.6); margin-top: 3px; }}
  .month-pill {{ font-family: 'Raleway', sans-serif; background: rgba(255,255,255,0.12); color: #fff; font-size: 12px;
                 padding: 6px 16px; border-radius: 20px; border: 1px solid rgba(255,255,255,0.2); }}
  .dash-body  {{ background: #F0F4F8; padding: 22px; border-radius: 0 0 14px 14px; }}

  .kpi-row {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; margin-bottom: 20px; }}
  .kpi-card {{ background: #fff; border-radius: 10px; padding: 16px 18px; border-top: 3px solid #ccc; }}
  .kpi-card.fb {{ border-color: #0A2540; }}
  .kpi-card.ig {{ border-color: #00857B; }}
  .kpi-card.li {{ border-color: #1A6FAF; }}
  .kpi-plat   {{ font-family: 'Montserrat', sans-serif; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; color: #64748B; margin-bottom: 6px; }}
  .kpi-nums   {{ display: flex; gap: 12px; }}
  .kpi-num    {{ flex: 1; }}
  .kpi-val    {{ font-family: 'Montserrat', sans-serif; font-size: 21px; font-weight: 700; color: #0A2540; line-height: 1; }}
  .kpi-lbl    {{ font-family: 'Raleway', sans-serif; font-size: 10px; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.3px; margin: 3px 0 2px; }}
  .kpi-delta  {{ font-family: 'Raleway', sans-serif; font-size: 11px; font-weight: 500; }}
  .up   {{ color: #1B8A4E; }}
  .down {{ color: #DC2626; }}

  .sec-label {{ font-family: 'Montserrat', sans-serif; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;
                color: #475569; margin: 6px 0 10px 2px; }}

  .g1 {{ display: grid; grid-template-columns: 1fr;            gap: 14px; margin-bottom: 16px; }}
  .g2 {{ display: grid; grid-template-columns: 1fr 1fr;        gap: 14px; margin-bottom: 16px; }}
  .g3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr;    gap: 14px; margin-bottom: 16px; }}
  .g2r {{ display: grid; grid-template-columns: 0.9fr 1.1fr;   gap: 14px; margin-bottom: 16px; }}

  .chart-card {{ background: #fff; border-radius: 10px; padding: 16px 16px 12px; }}
  .card-title  {{ font-family: 'Montserrat', sans-serif; font-size: 13px; font-weight: 600; color: #0A2540; margin-bottom: 2px; }}
  .card-sub    {{ font-family: 'Raleway', sans-serif; font-size: 11px; color: #64748B; margin-bottom: 10px; }}
  .leg {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }}
  .leg-item {{ font-family: 'Raleway', sans-serif; display: flex; align-items: center; gap: 5px; font-size: 11px; color: #475569; }}
  .leg-sq  {{ width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}

  .insight-row {{ display: grid; grid-template-columns: repeat(3,1fr); gap: 12px; margin-bottom: 12px; }}
  .ins-card {{
    background: linear-gradient(135deg, #00857B08, #1A6FAF0A);
    border: 1px solid #E2E8F0; border-radius: 10px; padding: 14px 16px;
    border-left: 3px solid #00857B;
  }}
  .ins-title {{ font-family: 'Montserrat', sans-serif; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px;
                color: #0A2540; margin-bottom: 6px; }}
  .ins-text  {{ font-family: 'Raleway', sans-serif; font-size: 12px; color: #475569; line-height: 1.6; }}
  .ins-text strong {{ color: #00857B; font-family: 'Montserrat', sans-serif; }}
</style>
</head>
<body>
<div class="dash">

  <div class="dash-header">
    <div>
      <div class="dash-title">SoMe Social Media Dashboard</div>
      <div class="dash-sub">2026 Performance vs 2025 Baseline &middot; Facebook &middot; Instagram &middot; LinkedIn</div>
    </div>
    <span class="month-pill">&#128197; {month_range}</span>
  </div>

  <div class="dash-body">

    <p class="sec-label">Platform snapshot</p>
    <div class="kpi-row">
      <div class="kpi-card fb">
        <div class="kpi-plat">Facebook</div>
        <div class="kpi-nums">
          <div class="kpi-num">
            <div class="kpi-val">{fmt(fb_fol26)}</div>
            <div class="kpi-lbl">Followers</div>
            <div class="kpi-delta">{pct_delta(fb_fol26, fb25["fol"])}</div>
          </div>
          <div class="kpi-num">
            <div class="kpi-val">{fmt(fb_imp26)}</div>
            <div class="kpi-lbl">Impressions</div>
            <div class="kpi-delta">{pct_delta(fb_imp26, fb25["imp"])}</div>
          </div>
          <div class="kpi-num">
            <div class="kpi-val">{fmt(fb_eng26)}</div>
            <div class="kpi-lbl">Engagement</div>
            <div class="kpi-delta">{pct_delta(fb_eng26, fb25["eng"])}</div>
          </div>
        </div>
      </div>
      <div class="kpi-card ig">
        <div class="kpi-plat">Instagram</div>
        <div class="kpi-nums">
          <div class="kpi-num">
            <div class="kpi-val">{fmt(ig_fol26)}</div>
            <div class="kpi-lbl">Followers</div>
            <div class="kpi-delta">{pct_delta(ig_fol26, ig25["fol"])}</div>
          </div>
          <div class="kpi-num">
            <div class="kpi-val">{fmt(ig_imp26)}</div>
            <div class="kpi-lbl">Impressions</div>
            <div class="kpi-delta">{pct_delta(ig_imp26, ig25["imp"])}</div>
          </div>
          <div class="kpi-num">
            <div class="kpi-val">{fmt(ig_eng26)}</div>
            <div class="kpi-lbl">Engagement</div>
            <div class="kpi-delta">{pct_delta(ig_eng26, ig25["eng"])}</div>
          </div>
        </div>
      </div>
      <div class="kpi-card li">
        <div class="kpi-plat">LinkedIn</div>
        <div class="kpi-nums">
          <div class="kpi-num">
            <div class="kpi-val">{fmt(li_fol26)}</div>
            <div class="kpi-lbl">Followers</div>
            <div class="kpi-delta">{pct_delta(li_fol26, li25["fol"])}</div>
          </div>
          <div class="kpi-num">
            <div class="kpi-val">{fmt(li_imp26)}</div>
            <div class="kpi-lbl">Impressions</div>
            <div class="kpi-delta">{pct_delta(li_imp26, li25["imp"])}</div>
          </div>
          <div class="kpi-num">
            <div class="kpi-val">{fmt(li_eng26)}</div>
            <div class="kpi-lbl">Engagement</div>
            <div class="kpi-delta">{pct_delta(li_eng26, li25["eng"])}</div>
          </div>
        </div>
      </div>
    </div>

    <p class="sec-label">Followers growth — 2026 monthly</p>
    <div class="g3">
      <div class="chart-card">
        <div class="card-title">Facebook followers</div>
        <div class="card-sub">2026 monthly · dashed line = 2025 baseline</div>
        <div style="position:relative;height:200px"><canvas id="follFbChart" role="img" aria-label="Facebook followers trend">Facebook followers</canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">Instagram followers</div>
        <div class="card-sub">2026 monthly · dashed line = 2025 baseline</div>
        <div style="position:relative;height:200px"><canvas id="follIgChart" role="img" aria-label="Instagram followers trend">Instagram followers</canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">LinkedIn followers</div>
        <div class="card-sub">2026 monthly · dashed line = 2025 baseline</div>
        <div style="position:relative;height:200px"><canvas id="follLiChart" role="img" aria-label="LinkedIn followers trend">LinkedIn followers</canvas></div>
      </div>
    </div>

    <p class="sec-label">Impressions &amp; Engagement — 2026 monthly</p>
    <div class="g2">
      <div class="chart-card">
        <div class="card-title">Impressions by month</div>
        <div class="card-sub">Horizontal bars — FB / IG / LinkedIn, by month</div>
        <div class="leg">
          <span class="leg-item"><span class="leg-sq" style="background:#0A2540"></span>FB</span>
          <span class="leg-item"><span class="leg-sq" style="background:#00857B"></span>IG</span>
          <span class="leg-item"><span class="leg-sq" style="background:#1A6FAF"></span>LI</span>
        </div>
        <div style="position:relative;height:260px"><canvas id="impChart" role="img" aria-label="Monthly impressions">Impressions</canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">Engagement by month</div>
        <div class="card-sub">Horizontal bars — FB / IG / LinkedIn, by month</div>
        <div class="leg">
          <span class="leg-item"><span class="leg-sq" style="background:#0A2540"></span>FB</span>
          <span class="leg-item"><span class="leg-sq" style="background:#00857B"></span>IG</span>
          <span class="leg-item"><span class="leg-sq" style="background:#1A6FAF"></span>LI</span>
        </div>
        <div style="position:relative;height:260px"><canvas id="engChart" role="img" aria-label="Monthly engagement">Engagement</canvas></div>
      </div>
    </div>

    <p class="sec-label">2025 vs 2026 comparison</p>
    <div class="g3">
      <div class="chart-card">
        <div class="card-title">Followers comparison</div>
        <div class="card-sub">Baseline vs latest 2026</div>
        <div class="leg">
          <span class="leg-item"><span class="leg-sq" style="background:#CBD5E1"></span>2025</span>
          <span class="leg-item"><span class="leg-sq" style="background:#00857B"></span>2026</span>
        </div>
        <div style="position:relative;height:180px"><canvas id="cmpFol" role="img" aria-label="Followers 2025 vs 2026">Followers comparison</canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">Impressions comparison</div>
        <div class="card-sub">Baseline vs 2026 sum</div>
        <div class="leg">
          <span class="leg-item"><span class="leg-sq" style="background:#CBD5E1"></span>2025</span>
          <span class="leg-item"><span class="leg-sq" style="background:#1A6FAF"></span>2026</span>
        </div>
        <div style="position:relative;height:180px"><canvas id="cmpImp" role="img" aria-label="Impressions 2025 vs 2026">Impressions comparison</canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">Engagement comparison</div>
        <div class="card-sub">Baseline vs 2026 sum</div>
        <div class="leg">
          <span class="leg-item"><span class="leg-sq" style="background:#CBD5E1"></span>2025</span>
          <span class="leg-item"><span class="leg-sq" style="background:#0A2540"></span>2026</span>
        </div>
        <div style="position:relative;height:180px"><canvas id="cmpEng" role="img" aria-label="Engagement 2025 vs 2026">Engagement comparison</canvas></div>
      </div>
    </div>

    <p class="sec-label">Platform profile</p>
    <div class="g2r">
      <div class="chart-card">
        <div class="card-title">Platform metric radar</div>
        <div class="card-sub">Normalised share of followers · impressions · engagement</div>
        <div class="leg">
          <span class="leg-item"><span class="leg-sq" style="background:#0A2540"></span>FB</span>
          <span class="leg-item"><span class="leg-sq" style="background:#00857B"></span>IG</span>
          <span class="leg-item"><span class="leg-sq" style="background:#1A6FAF"></span>LI</span>
        </div>
        <div style="position:relative;height:260px"><canvas id="radarChart" role="img" aria-label="Platform radar">Radar</canvas></div>
      </div>
      <div class="chart-card">
        <div class="card-title">Impressions share — 2026 YTD</div>
        <div class="card-sub">Platform mix donut</div>
        <div style="position:relative;height:260px"><canvas id="donutChart" role="img" aria-label="Impressions share donut">Donut</canvas></div>
      </div>
    </div>

    <p class="sec-label">Key insights</p>
    <div class="insight-row">
      <div class="ins-card">
        <div class="ins-title">Follower growth</div>
        <div class="ins-text">{ins1}</div>
      </div>
      <div class="ins-card" style="border-color:#1A6FAF">
        <div class="ins-title">Impressions leader</div>
        <div class="ins-text">{ins2}</div>
      </div>
      <div class="ins-card" style="border-color:#0A2540">
        <div class="ins-title">Engagement champion</div>
        <div class="ins-text">{ins3}</div>
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

// Palette: dark navy / green-teal / light blue / teal accent
const C_FB   = '#0A2540';   // dark navy
const C_IG   = '#00857B';   // green / teal
const C_LI   = '#1A6FAF';   // light blue
const C_BASE = '#CBD5E1';   // 2025 baseline grey
const C_TEAL = '#0EA5A0';   // teal accent

const months   = {j(months)};
const fb26fol  = {j(fb26['fol'])};
const ig26fol  = {j(ig26['fol'])};
const li26fol  = {j(li26['fol'])};
const fb26imp  = {j(fb26['imp'])};
const ig26imp  = {j(ig26['imp'])};
const li26imp  = {j(li26['imp'])};
const fb26eng  = {j(fb26['eng'])};
const ig26eng  = {j(ig26['eng'])};
const li26eng  = {j(li26['eng'])};
const fb25fol  = {fb25['fol']};
const ig25fol  = {ig25['fol']};
const li25fol  = {li25['fol']};
const fb25imp  = {fb25['imp']};
const ig25imp  = {ig25['imp']};
const li25imp  = {li25['imp']};
const fb25eng  = {fb25['eng']};
const ig25eng  = {ig25['eng']};
const li25eng  = {li25['eng']};

const nFol = {j(nFol)};
const nImp = {j(nImp)};
const nEng = {j(nEng)};

const totImp = {int(fb_imp26 + ig_imp26 + li_imp26) or 1};

function fmt(n) {{
  if (n >= 1e6) return (n/1e6).toFixed(1)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return Math.round(n).toString();
}}

const baseOpts = {{ responsive:true, maintainAspectRatio:false }};

// 1,1b,1c — Followers trend, one clean chart per platform (small multiples)
// Each platform gets its own scale and color so nothing overlaps.
function followerTrendChart(id, data, baseline, color) {{
  new Chart(document.getElementById(id), {{
    data: {{
      labels: months,
      datasets: [
        {{
          type:'line', label:'2026', data, borderColor:color,
          backgroundColor: color + '1A', fill:true,
          tension:0.35, pointRadius:4, pointBackgroundColor:color, borderWidth:2.5,
          datalabels: {{
            align:'top', anchor:'end', offset:6,
            color: color, font:{{size:10, weight:'600', family:MONTSERRAT}},
            formatter: v => fmt(v)
          }}
        }},
        {{
          type:'line', label:'2025 baseline', data: months.map(()=>baseline),
          borderColor:C_BASE, borderWidth:1.5, borderDash:[5,4],
          pointRadius:0, fill:false, datalabels:{{display:false}}
        }}
      ]
    }},
    options: {{
      ...baseOpts,
      layout: {{ padding: {{ top: 22 }} }},
      plugins: {{
        legend:{{display:false}},
        tooltip:{{ mode:'index', intersect:false, bodyFont:{{family:MONTSERRAT, size:12}}, titleFont:{{family:RALEWAY, size:12}} }}
      }},
      scales: {{
        x: {{ grid:{{display:false}}, ticks:{{color:'#64748B', font:{{size:10, family:RALEWAY}}}} }},
        y: {{ grid:{{color:'rgba(0,0,0,0.04)'}}, ticks:{{color:'#64748B', font:{{size:9, family:MONTSERRAT}}, callback:v=>fmt(v)}} }}
      }}
    }}
  }});
}}
followerTrendChart('follFbChart', fb26fol, fb25fol, C_FB);
followerTrendChart('follIgChart', ig26fol, ig25fol, C_IG);
followerTrendChart('follLiChart', li26fol, li25fol, C_LI);

// 2 — Impressions by month, horizontal bars — label sits just past the bar end
// in the bar's own color, large enough to read at a glance, never overlapping.
new Chart(document.getElementById('impChart'), {{
  type:'bar',
  data: {{
    labels: months,
    datasets: [
      {{ label:'FB', data:fb26imp, backgroundColor:C_FB, borderRadius:4, borderSkipped:false,
         datalabels:{{anchor:'end', align:'end', offset:4, color:C_FB, font:{{size:11, weight:'700', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }},
      {{ label:'IG', data:ig26imp, backgroundColor:C_IG, borderRadius:4, borderSkipped:false,
         datalabels:{{anchor:'end', align:'end', offset:4, color:C_IG, font:{{size:11, weight:'700', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }},
      {{ label:'LI', data:li26imp, backgroundColor:C_LI, borderRadius:4, borderSkipped:false,
         datalabels:{{anchor:'end', align:'end', offset:4, color:C_LI, font:{{size:11, weight:'700', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }}
    ]
  }},
  options: {{
    ...baseOpts,
    indexAxis: 'y',
    layout: {{ padding: {{ right: 42 }} }},
    plugins: {{ legend:{{display:false}}, tooltip:{{mode:'index', intersect:false, bodyFont:{{family:MONTSERRAT, size:12}}, titleFont:{{family:RALEWAY, size:12}}}} }},
    scales: {{
      x: {{ display:false, grid:{{display:false}} }},
      y: {{ grid:{{display:false}}, ticks:{{color:'#334155', font:{{size:11, family:RALEWAY}}}} }}
    }}
  }}
}});

// 3 — Engagement by month, horizontal bars — same end-anchored label style as
// impressions so both charts in this row are equally easy to read.
new Chart(document.getElementById('engChart'), {{
  type:'bar',
  data: {{
    labels: months,
    datasets: [
      {{ label:'FB', data:fb26eng, backgroundColor:C_FB, borderRadius:4, borderSkipped:false,
         datalabels:{{anchor:'end', align:'end', offset:4, color:C_FB, font:{{size:11, weight:'700', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }},
      {{ label:'IG', data:ig26eng, backgroundColor:C_IG, borderRadius:4, borderSkipped:false,
         datalabels:{{anchor:'end', align:'end', offset:4, color:C_IG, font:{{size:11, weight:'700', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }},
      {{ label:'LI', data:li26eng, backgroundColor:C_LI, borderRadius:4, borderSkipped:false,
         datalabels:{{anchor:'end', align:'end', offset:4, color:C_LI, font:{{size:11, weight:'700', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }}
    ]
  }},
  options: {{
    ...baseOpts,
    indexAxis: 'y',
    layout: {{ padding: {{ right: 42 }} }},
    plugins: {{ legend:{{display:false}}, tooltip:{{mode:'index', intersect:false, bodyFont:{{family:MONTSERRAT, size:12}}, titleFont:{{family:RALEWAY, size:12}}}} }},
    scales: {{
      x: {{ display:false, grid:{{display:false}} }},
      y: {{ grid:{{display:false}}, ticks:{{color:'#334155', font:{{size:11, family:RALEWAY}}}} }}
    }}
  }}
}});

// 4,5,6 — comparison bars
function cmpBar(id, v25, v26, col) {{
  new Chart(document.getElementById(id), {{
    type:'bar',
    data: {{
      labels:['Facebook','Instagram','LinkedIn'],
      datasets:[
        {{ label:'2025', data:v25, backgroundColor:C_BASE, borderRadius:4, borderSkipped:false,
           datalabels:{{anchor:'end', align:'top', color:'#64748B', font:{{size:9, weight:'600', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }},
        {{ label:'2026', data:v26, backgroundColor:col,    borderRadius:4, borderSkipped:false,
           datalabels:{{anchor:'end', align:'top', color:col, font:{{size:9, weight:'600', family:MONTSERRAT}}, formatter:v=>fmt(v)}} }}
      ]
    }},
    options: {{
      ...baseOpts,
      layout: {{ padding: {{ top: 22 }} }},
      plugins: {{ legend:{{display:false}}, tooltip:{{mode:'index', intersect:false, bodyFont:{{family:MONTSERRAT, size:12}}, titleFont:{{family:RALEWAY, size:12}}}} }},
      scales: {{
        x: {{ grid:{{display:false}}, ticks:{{color:'#334155', font:{{size:10, family:RALEWAY}}}} }},
        y: {{ grid:{{color:'rgba(0,0,0,0.04)'}}, ticks:{{color:'#64748B', font:{{size:10, family:MONTSERRAT}}, callback:v=>fmt(v)}} }}
      }}
    }}
  }});
}}
cmpBar('cmpFol', [fb25fol, ig25fol, li25fol], [{int(fb_fol26)},{int(ig_fol26)},{int(li_fol26)}], C_IG);
cmpBar('cmpImp', [fb25imp, ig25imp, li25imp], [{int(fb_imp26)},{int(ig_imp26)},{int(li_imp26)}], C_LI);
cmpBar('cmpEng', [fb25eng, ig25eng, li25eng], [{int(fb_eng26)},{int(ig_eng26)},{int(li_eng26)}], C_FB);

// 7 — Radar
new Chart(document.getElementById('radarChart'), {{
  type:'radar',
  data: {{
    labels:['Followers','Impressions','Engagement'],
    datasets:[
      {{ label:'Facebook',  data:[nFol[0],nImp[0],nEng[0]], borderColor:C_FB, backgroundColor:C_FB+'1F', pointBackgroundColor:C_FB, borderWidth:2, datalabels:{{display:false}} }},
      {{ label:'Instagram', data:[nFol[1],nImp[1],nEng[1]], borderColor:C_IG, backgroundColor:C_IG+'1A', pointBackgroundColor:C_IG, borderWidth:2, datalabels:{{display:false}} }},
      {{ label:'LinkedIn',  data:[nFol[2],nImp[2],nEng[2]], borderColor:C_LI, backgroundColor:C_LI+'1A', pointBackgroundColor:C_LI, borderWidth:2, datalabels:{{display:false}} }}
    ]
  }},
  options: {{
    ...baseOpts,
    layout: {{ padding: {{ top: 4 }} }},
    plugins: {{
      legend:{{ position:'top', align:'center', labels:{{color:'#334155', font:{{size:11, family:RALEWAY}}, boxWidth:10, padding:14, usePointStyle:true}} }},
      datalabels:{{display:false}}
    }},
    scales: {{
      r: {{
        angleLines:{{color:'#E2E8F0'}}, grid:{{color:'#E2E8F0'}},
        pointLabels:{{color:'#334155', font:{{size:11, family:RALEWAY}}}},
        ticks:{{display:false, backdropColor:'transparent'}},
        suggestedMin:0, suggestedMax:100
      }}
    }}
  }}
}});

// 8 — Donut
new Chart(document.getElementById('donutChart'), {{
  type:'doughnut',
  data: {{
    labels:['Facebook','Instagram','LinkedIn'],
    datasets:[{{
      data:[{int(fb_imp26)},{int(ig_imp26)},{int(li_imp26)}],
      backgroundColor:[C_FB, C_IG, C_LI],
      borderColor:'#fff', borderWidth:3
    }}]
  }},
  options: {{
    ...baseOpts, cutout:'60%',
    plugins: {{
      legend:{{ position:'bottom', labels:{{color:'#334155', font:{{size:11, family:RALEWAY}}, boxWidth:10, padding:10}} }},
      tooltip:{{ callbacks:{{ label: ctx => ctx.label+': '+fmt(ctx.raw)+' ('+Math.round(ctx.raw/totImp*100)+'%)' }} }},
      datalabels: {{
        color:'#fff', font:{{size:11, weight:'700', family:MONTSERRAT}},
        formatter: v => Math.round(v/totImp*100)+'%'
      }}
    }}
  }}
}});
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard saved: {output_path}")


# ── MAIN ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python some_dashboard.py <your_excel_file.xlsx>")
        sys.exit(1)

    excel_path = sys.argv[1]
    if not os.path.exists(excel_path):
        print(f"Error: File not found — {excel_path}")
        sys.exit(1)

    xl      = pd.ExcelFile(excel_path)
    d25     = load_2025(xl)
    d26     = load_2026(xl)
    html_out = str(Path(excel_path).stem) + "_dashboard.html"
    build_dashboard(d25, d26, html_out)
