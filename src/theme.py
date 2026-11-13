"""theme.py - all visual styling. Goes in src/ next to app.py. No new installs needed."""
import json
import os
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

INK, INK_SOFT, LINE = "#0F1F3D", "#5B6B85", "#E1E6EF"
BRAND, BRAND_DARK = "#0E8F7E", "#0A6B5E"
LOW, MODERATE, ELEVATED = "#1FA971", "#F2A33A", "#E5484D"
BAND_COLORS = {"Low": LOW, "Moderate": MODERATE, "Elevated": ELEVATED}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Public+Sans:wght@400;500;600&display=swap');
:root{--ink:#0F1F3D;--soft:#5B6B85;--line:#E1E6EF;--brand:#0E8F7E;--brand-dark:#0A6B5E;--paper:#F2F5FA;}
@property --n{syntax:'<integer>';initial-value:0;inherits:false}

html,body,[class*="css"],.stApp{font-family:'Public Sans',sans-serif;color:var(--ink)}
.stApp{background:var(--paper)}
h1,h2,h3,h4{font-family:'Sora',sans-serif!important;color:var(--ink);letter-spacing:-.02em}
h3{font-size:1.15rem!important;margin-top:1.6rem!important}
#MainMenu{visibility:hidden}.stAppDeployButton{display:none}footer{visibility:hidden}
header[data-testid="stHeader"]{background:transparent}
.block-container{padding-top:2rem;max-width:1250px}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:linear-gradient(180deg,#0F1F3D 0%,#142C55 100%)}
[data-testid="stSidebar"] *{color:#DCE4F2!important}
[data-testid="stSidebar"] .stRadio label{padding:11px 14px;border-radius:12px;margin-bottom:4px;transition:all .2s;cursor:pointer}
[data-testid="stSidebar"] .stRadio label:hover{background:rgba(255,255,255,.09);transform:translateX(3px)}
[data-testid="stSidebar"] .stRadio label:has(input:checked){background:var(--brand);box-shadow:0 6px 18px rgba(14,143,126,.35)}
[data-testid="stSidebar"] .stRadio label:has(input:checked) *{color:#fff!important;font-weight:600}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"]>label>div:first-child{display:none}
[data-testid="stSidebar"] .stButton button{background:transparent;border:1px solid rgba(255,255,255,.28);color:#fff!important;width:100%}
[data-testid="stSidebar"] .stButton button:hover{border-color:#fff;background:rgba(255,255,255,.08)}
.brand{font-family:'Sora',sans-serif;font-weight:700;font-size:1.25rem;color:#fff!important;display:flex;align-items:center;gap:10px;margin:4px 0 18px}
.brand-mark{width:30px;height:30px;border-radius:9px;background:linear-gradient(135deg,#0E8F7E,#5ED3C0);display:inline-block;animation:pulse 3s ease-in-out infinite}
.userchip{background:rgba(255,255,255,.08);border-radius:14px;padding:12px 14px;margin-bottom:18px;font-size:.85rem;line-height:1.4}

/* ---------- hero banner ---------- */
.hero{position:relative;overflow:hidden;border-radius:24px;padding:30px 38px;margin-bottom:1.6rem;color:#fff;
 background:linear-gradient(120deg,#0F1F3D,#17407A,#0E8F7E,#0F1F3D);background-size:300% 300%;animation:flow 16s ease infinite}
.hero::before{content:"";position:absolute;right:-60px;top:-80px;width:260px;height:260px;border-radius:50%;background:rgba(255,255,255,.07)}
.hero::after{content:"";position:absolute;right:120px;bottom:-110px;width:200px;height:200px;border-radius:50%;background:rgba(94,211,192,.14)}
.hero h1{color:#fff!important;font-size:2rem;margin:0}
.hero p{color:#C4D2EA;margin:6px 0 0;font-size:1rem}

/* ---------- KPI cards ---------- */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:1.2rem}
.kpi{background:#fff;border:1px solid var(--line);border-radius:20px;padding:18px 20px;position:relative;overflow:hidden;
 transition:transform .25s,box-shadow .25s}
.kpi:hover{transform:translateY(-4px);box-shadow:0 14px 30px rgba(15,31,61,.10)}
.kpi::before{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:var(--c,var(--brand))}
.kpi-label{color:var(--soft);font-size:.85rem}
.kpi-num{font-family:'Sora',sans-serif;font-size:2rem;font-weight:700;margin-top:4px;--n:var(--t);animation:countup 1.1s ease-out both;counter-reset:num var(--n)}
.kpi-num::after{content:counter(num)}
.kpi-text{font-family:'Sora',sans-serif;font-size:2rem;font-weight:700;margin-top:4px}

/* ---------- report gauge ---------- */
.gauge-card{background:#fff;border:1px solid var(--line);border-radius:24px;padding:22px;text-align:center}
.gauge{width:100%;max-width:210px}
.ring{animation:ring 1.3s cubic-bezier(.2,.8,.2,1) both}
.g-num{font:700 26px 'Sora',sans-serif;fill:var(--ink)}
.g-sub{font:500 9px 'Public Sans',sans-serif;fill:var(--soft)}
.pill{display:inline-block;padding:5px 16px;border-radius:999px;color:#fff;font-weight:600;font-size:.85rem}
.delta{color:var(--soft);font-size:.85rem;margin-top:8px}
.spectrum-wrap{position:relative}
.spectrum{height:14px;border-radius:999px;overflow:hidden;display:flex;margin:26px 0 8px}
.spectrum div{height:100%}
.marker{position:absolute;top:-9px;width:4px;height:32px;background:var(--ink);border-radius:3px;box-shadow:0 0 0 3px #fff;animation:slidein 1s ease-out both}
.spec-labels{display:flex;justify-content:space-between;font-size:.78rem;color:var(--soft)}

/* ---------- controls ---------- */
.stButton button,.stDownloadButton button,.stFormSubmitButton button{border-radius:12px;font-weight:600;border:1px solid var(--line);transition:all .2s}
.stButton button:hover,.stDownloadButton button:hover{transform:translateY(-2px);box-shadow:0 8px 18px rgba(15,31,61,.10);border-color:var(--brand)}
.stButton button[kind="primary"],.stFormSubmitButton button{background:linear-gradient(135deg,#0E8F7E,#0A6B5E);color:#fff;border:none}
.stTextInput input,.stNumberInput input,.stTextArea textarea,[data-baseweb="select"]>div{border-radius:12px!important;background:#fff}
:focus-visible{outline:2px solid var(--brand)!important;outline-offset:2px}
[data-testid="stForm"]{background:#fff;border:1px solid var(--line);border-radius:22px;padding:26px}
[data-testid="stExpander"]{background:#fff;border:1px solid var(--line);border-radius:16px}
[data-testid="stDataFrame"],[data-testid="stDataEditor"]{border:1px solid var(--line);border-radius:16px;overflow:hidden;background:#fff}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px 18px}

/* pill-style horizontal radios in the main area */
[data-testid="stMain"] .stRadio div[role="radiogroup"]{gap:8px;flex-wrap:wrap}
[data-testid="stMain"] .stRadio label{background:#fff;border:1px solid var(--line);border-radius:999px;padding:6px 18px;transition:all .2s;cursor:pointer}
[data-testid="stMain"] .stRadio label:hover{border-color:var(--brand)}
[data-testid="stMain"] .stRadio label:has(input:checked){background:var(--ink);border-color:var(--ink)}
[data-testid="stMain"] .stRadio label:has(input:checked) *{color:#fff!important}
[data-testid="stMain"] .stRadio div[role="radiogroup"]>label>div:first-child{display:none}

/* ---------- login ---------- */
.login-art{position:relative;overflow:hidden;border-radius:28px;min-height:520px;padding:40px;
 background:linear-gradient(140deg,#0F1F3D,#17407A 55%,#0E8F7E);background-size:200% 200%;animation:flow 14s ease infinite}
.login-art .brand{font-size:1.5rem}
.login-art .bars{position:absolute;left:40px;right:40px;bottom:36px;height:260px;display:flex;align-items:flex-end;gap:14px}
.login-art .bars i{flex:1;border-radius:12px 12px 4px 4px;height:var(--h);background:linear-gradient(180deg,var(--c),rgba(255,255,255,.08));
 animation:rise 1.4s cubic-bezier(.2,.8,.2,1) both,bob 6s ease-in-out infinite;animation-delay:var(--d),calc(var(--d) + 1.4s)}
.login-art .orb{position:absolute;border-radius:50%;filter:blur(50px);opacity:.5;animation:bob 9s ease-in-out infinite}

.login-art{min-height:620px;background-image:radial-gradient(rgba(255,255,255,.10) 1px,transparent 1px),linear-gradient(140deg,#0F1F3D,#17407A 55%,#0E8F7E);background-size:26px 26px,200% 200%}
.login-art .headline{position:relative;z-index:2;font-family:'Sora',sans-serif;font-weight:700;color:#fff;font-size:2.9rem;line-height:1.08;margin:60px 0 14px;max-width:440px;animation:fadeup .9s .2s both}
.login-art .headline span{background:linear-gradient(90deg,#5ED3C0,#F2A33A);-webkit-background-clip:text;background-clip:text;color:transparent}
.login-art .sub{position:relative;z-index:2;color:#C4D2EA;font-size:1.15rem;max-width:380px;animation:fadeup .9s .45s both}
.login-art .bars{height:200px;opacity:.9}
.chip{position:absolute;z-index:3;background:rgba(255,255,255,.12);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,.28);border-radius:18px;padding:12px 18px;color:#DCE8FA;font-size:.8rem;animation:fadeup .9s .8s both,bob 7s ease-in-out 1.7s infinite}
.chip b{display:block;font-family:'Sora',sans-serif;font-size:1.3rem;color:#fff}
.chip i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}
@keyframes fadeup{from{opacity:0;transform:translateY(18px)}}
@keyframes flow{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
@keyframes countup{from{--n:0}}
@keyframes ring{from{stroke-dashoffset:339.3}}
@keyframes slidein{from{left:0}}
@keyframes rise{from{height:0}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-8px)}}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(94,211,192,.5)}50%{box-shadow:0 0 0 8px rgba(94,211,192,0)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
"""


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def greeting():
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def page_header(title, subtitle=""):
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(f'<div class="hero"><h1>{title}</h1>{sub}</div>', unsafe_allow_html=True)


def sidebar_brand(role_label):
    st.sidebar.markdown('<div class="brand"><span class="brand-mark"></span>Credit Risk DSS</div>', unsafe_allow_html=True)
    st.sidebar.markdown(f'<div class="userchip">{greeting()}<br><b>{role_label}</b></div>', unsafe_allow_html=True)


def kpi_cards(items):
    """items: list of (label, value, colour). Integers count up on load; strings are shown as they are."""
    html = ""
    for label, value, colour in items:
        if isinstance(value, (int, float)) and float(value).is_integer():
            body = f'<div class="kpi-num" style="--t:{int(value)}"></div>'
        else:
            body = f'<div class="kpi-text">{value}</div>'
        html += f'<div class="kpi" style="--c:{colour}"><div class="kpi-label">{label}</div>{body}</div>'
    st.markdown(f'<div class="kpis">{html}</div>', unsafe_allow_html=True)


def band_pill(band):
    return f'<span class="pill" style="background:{BAND_COLORS.get(band, INK_SOFT)}">{band} risk</span>'


def gauge(score, band, delta_text=""):
    circ = 339.3
    off = circ * (1 - min(max(score, 0), 1))
    colour = BAND_COLORS.get(band, BRAND)
    st.markdown(
        f'<div class="gauge-card"><svg viewBox="0 0 140 140" class="gauge">'
        f'<circle cx="70" cy="70" r="54" fill="none" stroke="#E7ECF4" stroke-width="14"/>'
        f'<circle class="ring" cx="70" cy="70" r="54" fill="none" stroke="{colour}" stroke-width="14" stroke-linecap="round" '
        f'stroke-dasharray="{circ}" stroke-dashoffset="{off:.1f}" transform="rotate(-90 70 70)"/>'
        f'<text x="70" y="72" text-anchor="middle" class="g-num">{score * 100:.0f}%</text>'
        f'<text x="70" y="90" text-anchor="middle" class="g-sub">chance of default</text></svg>'
        f'<div>{band_pill(band)}</div><div class="delta">{delta_text}</div></div>', unsafe_allow_html=True)


def risk_spectrum(score, thresholds_path="models/risk_thresholds.json", scale_max=0.6):
    low_max, high_min = 0.328, 0.484
    if os.path.exists(thresholds_path):
        with open(thresholds_path) as f:
            t = json.load(f)
        low_max, high_min = t["low_max"], t["high_min"]
    w1, w2 = low_max / scale_max * 100, (high_min - low_max) / scale_max * 100
    pos = min(max(score / scale_max, 0.01), 0.99) * 100
    st.markdown(
        f'<div class="spectrum-wrap"><div class="spectrum"><div style="width:{w1}%;background:{LOW}"></div>'
        f'<div style="width:{w2}%;background:{MODERATE}"></div><div style="width:{100 - w1 - w2}%;background:{ELEVATED}"></div></div>'
        f'<div class="marker" style="left:calc({pos}% - 2px)"></div></div>'
        f'<div class="spec-labels"><span>Low</span><span>Moderate</span><span>Elevated</span></div>', unsafe_allow_html=True)


def login_art(headline='Every business deserves a <span>fair look.</span>', sub="Know the risk before you say yes."):
    bars = [("38%", "#5ED3C0", "0s"), ("62%", "#5ED3C0", ".12s"), ("48%", "#F2A33A", ".24s"),
            ("80%", "#5ED3C0", ".36s"), ("58%", "#F2A33A", ".48s"), ("92%", "#E5484D", ".6s"), ("70%", "#5ED3C0", ".72s")]
    b = "".join(f'<i style="--h:{h};--c:{c};--d:{d}"></i>' for h, c, d in bars)
    st.markdown(
        '<div class="login-art">'
        '<div class="orb" style="width:260px;height:260px;background:#5ED3C0;top:-70px;right:-50px"></div>'
        '<div class="orb" style="width:200px;height:200px;background:#F2A33A;bottom:60px;left:-60px;opacity:.25"></div>'
        '<div class="brand"><span class="brand-mark"></span>Credit Risk DSS</div>'
        f'<div class="headline">{headline}</div><div class="sub">{sub}</div>'
        f'<div class="chip" style="top:150px;right:34px"><i style="background:#1FA971"></i>Low risk<b>14%</b></div>'
        f'<div class="chip" style="top:285px;right:110px;animation-delay:1.1s,2s"><i style="background:#5ED3C0"></i>Approved<b>KES 2.4M</b></div>'
        f'<div class="bars">{b}</div></div>', unsafe_allow_html=True)


# ---------------- charts ----------------
def _style(chart):
    return (chart.configure_view(strokeWidth=0)
            .configure_axis(labelColor=INK_SOFT, titleColor=INK_SOFT, gridColor=LINE, domainColor=LINE)
            .configure_legend(labelColor=INK, titleColor=INK_SOFT))


def contribution_chart(top_features_json):
    try:
        df = pd.DataFrame(json.loads(top_features_json))
    except (ValueError, TypeError):
        st.write(top_features_json or "")
        return
    value_col = [c for c in df.columns if c != "feature"][0]
    df = df.rename(columns={value_col: "value"})
    df["direction"] = df["value"].apply(lambda v: "Raises risk" if v > 0 else "Lowers risk")
    chart = (alt.Chart(df).mark_bar(cornerRadiusEnd=6, size=22)
             .encode(x=alt.X("value:Q", title=None), y=alt.Y("feature:N", sort="-x", title=None),
                     color=alt.Color("direction:N", legend=alt.Legend(title=None, orient="bottom"),
                                     scale=alt.Scale(domain=["Raises risk", "Lowers risk"], range=[ELEVATED, LOW])),
                     tooltip=["feature", "value"]).properties(height=max(120, 48 * len(df))))
    st.altair_chart(_style(chart), use_container_width=True)


def band_donut(counts):
    df = pd.DataFrame([{"Band": b, "Applications": counts.get(b, 0)} for b in BAND_COLORS])
    if df["Applications"].sum() == 0:
        st.info("No scored applications yet.")
        return
    chart = (alt.Chart(df).mark_arc(innerRadius=70, outerRadius=110)
             .encode(theta="Applications:Q",
                     color=alt.Color("Band:N", scale=alt.Scale(domain=list(BAND_COLORS), range=list(BAND_COLORS.values())),
                                     legend=alt.Legend(title=None, orient="bottom")), tooltip=["Band", "Applications"])
             .properties(height=280))
    st.altair_chart(_style(chart), use_container_width=True)


def per_day_chart(rows):
    df = pd.DataFrame(rows, columns=["Date", "Applications"])
    chart = (alt.Chart(df).mark_area(line={"color": BRAND}, opacity=.45, color=BRAND)
             .encode(x=alt.X("Date:N", title=None), y=alt.Y("Applications:Q", title=None), tooltip=["Date", "Applications"])
             .properties(height=260))
    st.altair_chart(_style(chart), use_container_width=True)


def model_comparison_chart(path="models/model_comparison_nn.csv"):
    if not os.path.exists(path):
        st.info("Run compare_nn.py to generate the model comparison.")
        return
    df = pd.read_csv(path)[["Model", "ROC-AUC"]]
    df["Chosen"] = df["Model"].eq("Random Forest")
    bars = (alt.Chart(df).mark_bar(cornerRadiusEnd=6, size=32)
            .encode(x=alt.X("ROC-AUC:Q", scale=alt.Scale(domain=[0.5, 0.75]), title=None),
                    y=alt.Y("Model:N", sort="-x", title=None),
                    color=alt.Color("Chosen:N", legend=None, scale=alt.Scale(domain=[True, False], range=[BRAND, "#B8C3D9"])),
                    tooltip=["Model", "ROC-AUC"]))
    labels = bars.mark_text(align="left", dx=6, color=INK).encode(text=alt.Text("ROC-AUC:Q", format=".3f"))
    st.altair_chart(_style((bars + labels).properties(height=200)), use_container_width=True)