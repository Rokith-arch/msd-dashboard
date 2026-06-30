import streamlit as st
import tempfile, os, importlib.util, sys, io
import pandas as pd
from pathlib import Path

MSD_LOGO_B64 = "iVBORw0KGgoAAAANSUhEUgAAAWAAAAEACAYAAACNlawWAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAEioSURBVHhe7d13vBT1vf/x13dmd0+vnMahc0CqFMUgYhewxIjGcsVc6zVFY9rV5KbYkhhL8rPf2HKvV6OxJkKixqhYUBABUQERkSL1wClwOP2c3Z35/v6YmWXPctqewp4Dn6ePEZiZ3Z2ZnX3vd7/z/X5Haa01QgghDjojdoYQQoiDQwJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAJYCCESRAK4E3TsDCGE6AFKa3145IsGFFiADZiAoVtJV2+essGEMGC08z3V9hIhhGjfYRHAGid4tRuYZiR43V1XUSsrG7QdmW+j3BWip/0kgIUQXXVYBLCXwNqyqLXC1GuLRjQGBrYFaI22tROtSqN8YGCTbJgElEG6P4Bhms4yaBHCEsBCiK7q1wHs1ipEag0AFBqFQmuwNNSFbHbW17Kjfh876qrZWl/D7qZGKi0L21I0NAWxbRtt29iAUpDmM0kC8jPSKcrIYrQvg7y0NIoyshiUlkxOkg9DRb+qEb0BQgjRKf0+gImEsPefga2hrAqWVe1m5Z5drKzYyeqacioaG7AsQEeVW1Uru6/3p6jSkKIURSmZDM8u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"

# ── Page config ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MSD Dashboard Launcher",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Inject custom CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700&family=Raleway:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Raleway', sans-serif;
}

/* Hide default streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 1rem !important; }

/* Header banner */
.msd-header {
    background: linear-gradient(135deg, #0A2540 0%, #0D3259 60%, #1A4A7A 100%);
    border-radius: 14px;
    padding: 22px 30px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.msd-header-left { display: flex; align-items: center; gap: 14px; }
.msd-logo {
    width: 52px; height: 52px;
    background: #fff;
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    padding: 6px;
}
.msd-logo img { width: 100%; height: 100%; object-fit: contain; }
.msd-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 22px; font-weight: 700;
    color: #fff; margin: 0;
}
.msd-sub {
    font-family: 'Raleway', sans-serif;
    font-size: 12px; color: rgba(255,255,255,0.5);
    margin-top: 2px;
}
.msd-badge {
    background: #00857B; color: #fff;
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 600;
    padding: 5px 14px; border-radius: 20px;
}

/* Platform cards */
.plat-card {
    background: #fff;
    border: 2px solid #E2E8F0;
    border-radius: 14px;
    padding: 18px;
    cursor: pointer;
    transition: all 0.18s;
    text-align: center;
    height: 100%;
}
.plat-card.selected {
    border-color: #00857B;
    background: linear-gradient(135deg, #00857B08, #1A6FAF08);
    box-shadow: 0 4px 20px rgba(0,133,123,0.15);
}
.plat-icon { font-size: 28px; margin-bottom: 8px; }
.plat-name {
    font-family: 'Montserrat', sans-serif;
    font-size: 14px; font-weight: 700;
    color: #0A2540; margin-bottom: 4px;
}
.plat-desc {
    font-family: 'Raleway', sans-serif;
    font-size: 11px; color: #64748B; line-height: 1.5;
}

/* Info box */
.info-box {
    background: linear-gradient(135deg, #0A254008, #00857B08);
    border: 1px solid #E2E8F0;
    border-left: 3px solid #00857B;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 16px 0;
    font-family: 'Raleway', sans-serif;
    font-size: 13px; color: #475569;
}
.info-box b {
    font-family: 'Montserrat', sans-serif;
    color: #0A2540;
}

/* Step label */
.step-label {
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.6px;
    color: #94A3B8; margin-bottom: 6px;
}

/* Success box */
.success-box {
    background: linear-gradient(135deg, #00857B0A, #1B8A4E0A);
    border: 1px solid #00857B40;
    border-radius: 10px;
    padding: 14px 18px;
    font-family: 'Montserrat', sans-serif;
    font-size: 13px; color: #00857B; font-weight: 600;
    display: flex; align-items: center; gap: 8px;
}
</style>
""", unsafe_allow_html=True)

# ── Platform config ──────────────────────────────────────────────────────
PLATFORMS = {
    "SFMC": {
        "icon": "📧",
        "module": "sfmc_dashboard",
        "desc": "Salesforce Marketing Cloud email performance",
        "cols": "Month · Campaign · TA · Total Delivered · Total Opens · Total Clicks",
        "color": "#00857B"
    },
    "REE": {
        "icon": "📨",
        "module": "ree_dashboardwwe",
        "desc": "REE email — Delivered, Opens, Clicks, Bounced & Dropped",
        "cols": "STATUS · Month · Campaign · TA · MARKET · Opens · Clicks",
        "color": "#1A6FAF"
    },
    "SoMe": {
        "icon": "📱",
        "module": "some_dashboard",
        "desc": "Social Media: Facebook, Instagram & LinkedIn analytics",
        "cols": "Sheet 1 = 2025 baseline · Sheet 2 = 2026 monthly",
        "color": "#0A2540"
    },
    "GCC Pulse": {
        "icon": "📡",
        "module": "gcc_pulse_dashboard",
        "desc": "GCC Pulse website analytics by Month & Therapy Area",
        "cols": "Month · Sessions · Active users · New users · Engagement Time · TA",
        "color": "#7C5CBF"
    },
    "CLM": {
        "icon": "🖥️",
        "module": "clm_dashboard",
        "desc": "CLM slide analytics — Total Use, Utilization & Avg Duration",
        "cols": "Binder Name · Slide Name · Total Use (CLM) · Slide Utilization · Avg. CLM Slide Duration",
        "color": "#00857B"
    },
}

# Sheet positions in the consolidated Excel (0-based index)
# Sheet1=SFMC, Sheet2=REE, Sheet3=SoMe 2025, Sheet4=SoMe 2026, Sheet5=GCC Pulse
CONSOLIDATED_SHEET_IDX = {
    "SFMC":      0,
    "REE":       1,
    "GCC Pulse": 4,
    "SoMe":      (2, 3),  # 2025 at index 2, 2026 at index 3
}


def extract_platform_sheet(xl_bytes: bytes, platform_key: str) -> str:
    """Extract relevant sheet(s) from consolidated Excel bytes into a temp file."""
    xl = pd.ExcelFile(io.BytesIO(xl_bytes))

    if platform_key == "SoMe":
        idx_25, idx_26 = CONSOLIDATED_SHEET_IDX["SoMe"]
        df25 = pd.read_excel(xl, sheet_name=idx_25, header=None)
        df26 = pd.read_excel(xl, sheet_name=idx_26, header=None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        with pd.ExcelWriter(tmp.name, engine="openpyxl") as writer:
            df25.to_excel(writer, sheet_name="Sheet1", index=False, header=False)
            df26.to_excel(writer, sheet_name="Sheet2", index=False, header=False)
    else:
        df = pd.read_excel(xl, sheet_name=CONSOLIDATED_SHEET_IDX[platform_key], header=None)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.close()
        df.to_excel(tmp.name, index=False, header=False)

    return tmp.name

# ── Load dashboard module ────────────────────────────────────────────────
@st.cache_resource
def load_module(module_name):
    base = Path(__file__).parent / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(module_name, base)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def generate_dashboard(platform_key: str, excel_path: str) -> str:
    mod_name = PLATFORMS[platform_key]["module"]
    mod = load_module(mod_name)
    out_path = excel_path.replace(".xlsx", "_dashboard.html").replace(".xls", "_dashboard.html")

    if platform_key == "SoMe":
        xl  = pd.ExcelFile(excel_path)
        d25 = mod.load_2025(xl)
        d26 = mod.load_2026(xl)
        mod.build_dashboard(d25, d26, out_path)
    elif platform_key == "CLM":
        df, kpi_total_use, kpi_util, kpi_avg_dur = mod.load_and_clean(excel_path)
        mod.build_dashboard(df, kpi_total_use, kpi_util, kpi_avg_dur, out_path)
    else:
        df = mod.load_and_clean(excel_path)
        mod.build_dashboard(df, out_path)

    with open(out_path, "r", encoding="utf-8") as f:
        html = f.read()
    os.remove(out_path)
    return html

# ── Session state ────────────────────────────────────────────────────────
if "selected" not in st.session_state:
    st.session_state.selected = "SFMC"
if "dashboard_html" not in st.session_state:
    st.session_state.dashboard_html = None
if "dashboard_platform" not in st.session_state:
    st.session_state.dashboard_platform = None
if "consolidated_bytes" not in st.session_state:
    st.session_state.consolidated_bytes = None
if "consolidated_name" not in st.session_state:
    st.session_state.consolidated_name = None

# ── Header ───────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="msd-header">
  <div class="msd-header-left">
    <div class="msd-logo">
      <img src="data:image/png;base64,{MSD_LOGO_B64}" alt="MSD logo"/>
    </div>
    <div>
      <div class="msd-title">Analytics</div>
      <div class="msd-sub">Dashboard Launcher · GCC Region</div>
    </div>
  </div>
  <div class="msd-badge">MSD Internal</div>
</div>
""", unsafe_allow_html=True)

# ── Step 1: Platform selection ───────────────────────────────────────────
st.markdown('<div class="step-label">Step 1 — Select Platform</div>', unsafe_allow_html=True)

cols = st.columns(5)
for i, (name, cfg) in enumerate(PLATFORMS.items()):
    with cols[i]:
        is_sel = st.session_state.selected == name
        sel_class = "selected" if is_sel else ""
        check = "✅ " if is_sel else ""
        st.markdown(f"""
        <div class="plat-card {sel_class}">
          <div class="plat-icon">{cfg['icon']}</div>
          <div class="plat-name">{check}{name}</div>
          <div class="plat-desc">{cfg['desc']}</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"Select {name}", key=f"sel_{name}", use_container_width=True):
            st.session_state.selected = name
            st.session_state.dashboard_html = None
            st.rerun()

# ── Selected platform info ───────────────────────────────────────────────
sel = st.session_state.selected
cfg = PLATFORMS[sel]

st.markdown(f"""
<div class="info-box">
  <b>{cfg['icon']} {sel} selected</b> — {cfg['desc']}<br>
  <span style="font-size:11px;color:#94A3B8">Expected columns: {cfg['cols']}</span>
</div>
""", unsafe_allow_html=True)

# ── Step 2: Upload file ───────────────────────────────────────────────────
st.markdown('<div class="step-label">Step 2 — Upload Excel File</div>', unsafe_allow_html=True)

if sel == "CLM":
    # CLM always gets its own separate uploader
    clm_uploaded = st.file_uploader(
        "Drop your CLM Excel file here",
        type=["xlsx", "xls"],
        label_visibility="collapsed",
        key="clm_uploader"
    )
    if clm_uploaded:
        st.markdown(f"""
        <div class="success-box">
          ✓ &nbsp; <span style="color:#0A2540;font-weight:400">{clm_uploaded.name}</span>&nbsp; ready to process
        </div>
        """, unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="step-label">Step 3 — Generate Dashboard</div>', unsafe_allow_html=True)
        if st.button("▶  Generate CLM Dashboard", type="primary", use_container_width=True):
            with st.spinner(f"Processing {clm_uploaded.name}…"):
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
                tmp.write(clm_uploaded.read())
                tmp.close()
                try:
                    html = generate_dashboard(sel, tmp.name)
                    st.session_state.dashboard_html = html
                    st.session_state.dashboard_platform = sel
                except Exception as e:
                    st.error(f"⚠ Error processing file: {e}")
                finally:
                    try: os.unlink(tmp.name)
                    except: pass
            st.rerun()
else:
    # Consolidated file — upload once, reuse across all non-CLM platforms
    if st.session_state.consolidated_bytes:
        st.markdown(f"""
        <div class="success-box">
          ✓ &nbsp; <span style="color:#0A2540;font-weight:400">{st.session_state.consolidated_name}</span>
          &nbsp; loaded — switch platforms freely without re-uploading
        </div>
        """, unsafe_allow_html=True)
        if st.button("Replace file", key="replace_consolidated"):
            st.session_state.consolidated_bytes = None
            st.session_state.consolidated_name = None
            st.session_state.dashboard_html = None
            st.rerun()
    else:
        cons_uploaded = st.file_uploader(
            "Drop your consolidated Excel file here (all platforms in one workbook)",
            type=["xlsx", "xls"],
            label_visibility="collapsed",
            key="consolidated_uploader"
        )
        if cons_uploaded:
            st.session_state.consolidated_bytes = cons_uploaded.read()
            st.session_state.consolidated_name = cons_uploaded.name
            st.rerun()

    # Step 3 — only show once consolidated file is available
    if st.session_state.consolidated_bytes:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="step-label">Step 3 — Generate Dashboard</div>', unsafe_allow_html=True)
        if st.button(f"▶  Generate {sel} Dashboard", type="primary", use_container_width=True):
            with st.spinner(f"Processing {sel} data…"):
                tmp_path = None
                try:
                    tmp_path = extract_platform_sheet(st.session_state.consolidated_bytes, sel)
                    html = generate_dashboard(sel, tmp_path)
                    st.session_state.dashboard_html = html
                    st.session_state.dashboard_platform = sel
                except Exception as e:
                    st.error(f"⚠ Error processing file: {e}")
                finally:
                    if tmp_path:
                        try: os.unlink(tmp_path)
                        except: pass
            st.rerun()

# ── Dashboard output ─────────────────────────────────────────────────────
if st.session_state.dashboard_html:
    html = st.session_state.dashboard_html
    plat = st.session_state.dashboard_platform

    st.divider()

    col_title, col_dl = st.columns([3, 1])
    with col_title:
        st.markdown(f"### {PLATFORMS[plat]['icon']} {plat} Dashboard")
    with col_dl:
        st.download_button(
            label="⬇  Download HTML",
            data=html.encode("utf-8"),
            file_name=f"{plat.lower().replace(' ','_')}_dashboard.html",
            mime="text/html",
            use_container_width=True,
            type="primary"
        )

    # Render dashboard inline using Streamlit components
    import streamlit.components.v1 as components
    components.html(html, height=950, scrolling=True)

