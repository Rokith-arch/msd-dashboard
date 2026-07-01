import streamlit as st
import tempfile, os, importlib.util, sys, io
import pandas as pd
from pathlib import Path


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

