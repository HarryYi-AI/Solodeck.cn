from __future__ import annotations

import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

from src.agent_orchestrator import find_synthetic_data_dir, run_agent_suite
from src.business_collab import campaign_dashboard, campaign_risk_alerts
from src.causal_experiment import analyze_ab_test, design_ab_test
from src.data_loader import load_all
from src.incremental_effect import fixed_effect_estimate
from src.knowledge_graph import graph_rag_answer, plot_knowledge_graph
from src.llm_agent import extract_records_from_uploads, model_status
from src.mock_data import generate_all
from src.product_feedback import classify_feedback, feedback_to_roadmap
from src.revenue_analysis import content_commercial_value, pending_payment_summary, platform_revenue_summary, topic_business_summary
from src.series_analysis import content_series_performance
from src.similarity_engine import detect_content_overlap
from src.strategy_analysis import platform_strategy_analysis, title_style_analysis, topic_strategy_analysis, weekly_topic_plan


st.set_page_config(page_title="SoloDeck", page_icon="▰", layout="wide", initial_sidebar_state="expanded")


def render_html(markup: str) -> None:
    html = str(markup).strip()
    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(html, unsafe_allow_html=True)


PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "bilibili": "B站",
    "douyin": "抖音",
    "wechat": "公众号/视频号",
    "zhihu": "知乎",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "substack": "Substack",
    "x": "X / Twitter",
}

STYLE_LABELS = {
    "pain_point": "痛点标题",
    "tutorial": "教程标题",
    "number": "数字清单",
    "story": "故事型",
    "contrast": "对比型",
    "result_oriented": "结果导向",
    "question": "提问型",
}

FEATURE_LABELS = {
    "emotion_companion": "情绪陪伴",
    "voice_interaction": "语音互动",
    "desktop_decoration": "桌面摆件",
    "study_planner": "学习规划",
    "auto_reply": "自动回复",
    "workflow": "流程自动化",
    "analytics": "数据分析",
    "template": "模板",
}

METRIC_LABELS = {
    "views": "播放量",
    "favorite_rate": "收藏率",
    "follow_rate": "转粉率",
    "conversion_rate": "转化率",
    "revenue": "收入",
    "consultations": "咨询量",
    "converted": "成交",
    "retained_7d": "7日留存",
    "activated": "激活",
    "rating": "评分",
}

ISSUE_LABELS = {
    "pricing": "价格",
    "performance": "性能",
    "usability": "易用性",
    "feature_request": "功能请求",
    "design": "设计",
    "trust": "信任",
    "quality": "质量",
    "emotional_value": "情绪价值",
}


def load_demo_data():
    synthetic = find_synthetic_data_dir(ROOT.parent)
    data_dir = synthetic or ROOT / "data"
    if not (data_dir / "mock_contents.csv").exists():
        generate_all(data_dir)
    return load_all(data_dir)


TABLE_NAMES = {
    "contents": "内容",
    "revenues": "收入",
    "campaigns": "商务",
    "ab_tests": "实验",
    "products": "产品",
    "feedback": "反馈",
    "beta_tests": "内测",
}


def init_workspace_state() -> None:
    if "modern_uploads" not in st.session_state:
        st.session_state.modern_uploads = {key: [] for key in TABLE_NAMES}
    if "modern_upload_notice" not in st.session_state:
        st.session_state.modern_upload_notice = ""


def read_uploaded_table(file) -> pd.DataFrame:
    name = getattr(file, "name", "").lower()
    data = file.getvalue()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(BytesIO(data))
    return pd.read_csv(BytesIO(data))


def infer_table_key(df: pd.DataFrame, filename: str = "") -> str:
    cols = {str(c).lower() for c in df.columns}
    name = filename.lower()
    if "experiment_id" in cols or "ab" in name:
        return "ab_tests"
    if "test_group" in cols or "beta" in name:
        return "beta_tests"
    if "feedback_text" in cols or "issue_type" in cols or "feedback" in name:
        return "feedback"
    if "product_id" in cols or "feature_tags" in cols or "product" in name:
        return "products"
    if "campaign_id" in cols or "brand_name" in cols or "payment_status" in cols or "campaign" in name:
        return "campaigns"
    if "revenue_id" in cols or "revenue_type" in cols or ("amount" in cols and "date" in cols) or "revenue" in name:
        return "revenues"
    return "contents"


def append_workspace_table(table_key: str, df: pd.DataFrame) -> None:
    init_workspace_state()
    if df is None or df.empty:
        return
    st.session_state.modern_uploads.setdefault(table_key, []).append(df.copy())


def workspace_data():
    init_workspace_state()
    base = list(load_demo_data())
    key_order = ["contents", "revenues", "campaigns", "ab_tests", "products", "feedback", "beta_tests"]
    for index, key in enumerate(key_order):
        uploads = st.session_state.modern_uploads.get(key, [])
        if uploads:
            base[index] = pd.concat([base[index], *uploads], ignore_index=True, sort=False)
    return tuple(base)


def platform_name(value: str) -> str:
    return PLATFORM_LABELS.get(str(value), str(value))


def feature_name(value: str) -> str:
    parts = [p.strip() for p in str(value).replace("|", ",").split(",") if p.strip()]
    if not parts:
        return str(value)
    return "、".join(FEATURE_LABELS.get(p, p) for p in parts)


def metric_name(value: str) -> str:
    return METRIC_LABELS.get(str(value), str(value))


def issue_name(value: str) -> str:
    return ISSUE_LABELS.get(str(value), str(value))


def cn_text(value) -> str:
    text = str(value)
    for raw, label in {**PLATFORM_LABELS, **STYLE_LABELS, **FEATURE_LABELS, **METRIC_LABELS, **ISSUE_LABELS}.items():
        text = text.replace(raw, label)
    text = text.replace("growth", "拉新").replace("engagement", "互动").replace("conversion", "转化").replace("monetization", "变现")
    text = text.replace("high", "高").replace("medium", "中").replace("low", "低")
    return text


def pct(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.0%}"


def safe_rate(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def metric_lifts(contents: pd.DataFrame, revenues: pd.DataFrame, days: int) -> dict[str, dict]:
    df = contents.copy()
    df["publish_time"] = pd.to_datetime(df["publish_time"], errors="coerce")
    latest = df["publish_time"].max()
    if pd.isna(latest):
        latest = pd.Timestamp.today()
    current_start = latest - timedelta(days=days)
    previous_start = latest - timedelta(days=days * 2)
    current = df[df["publish_time"].between(current_start, latest)]
    previous = df[df["publish_time"].between(previous_start, current_start)]
    if current.empty:
        current = df.tail(max(1, min(len(df), days * 2)))
    if previous.empty:
        previous = df.head(max(1, min(len(df), days * 2)))

    cur_views = current["views"].sum()
    prev_views = previous["views"].sum()
    cur_consult = safe_rate(current["consultations"].sum(), cur_views)
    prev_consult = safe_rate(previous["consultations"].sum(), prev_views)
    cur_fav = safe_rate(current["favorites"].sum(), cur_views)
    prev_fav = safe_rate(previous["favorites"].sum(), prev_views)
    cur_revenue = float(current["revenue"].sum())
    prev_revenue = float(previous["revenue"].sum())

    return {
        "consult": {"label": "咨询率", "value": cur_consult, "lift": safe_rate(cur_consult - prev_consult, abs(prev_consult) or 1), "icon": "message"},
        "favorite": {"label": "收藏率", "value": cur_fav, "lift": safe_rate(cur_fav - prev_fav, abs(prev_fav) or 1), "icon": "bookmark"},
        "views": {"label": "播放量", "value": cur_views, "lift": safe_rate(cur_views - prev_views, abs(prev_views) or 1), "icon": "play"},
        "revenue": {"label": "收入", "value": cur_revenue, "lift": safe_rate(cur_revenue - prev_revenue, abs(prev_revenue) or 1), "icon": "yen"},
    }


def trend_frame(contents: pd.DataFrame) -> pd.DataFrame:
    df = contents.copy()
    df["publish_time"] = pd.to_datetime(df["publish_time"], errors="coerce")
    df = df.dropna(subset=["publish_time"])
    if df.empty:
        return pd.DataFrame()
    df["date"] = df["publish_time"].dt.date
    grouped = df.groupby("date", as_index=False).agg(
        views=("views", "sum"),
        favorites=("favorites", "sum"),
        consultations=("consultations", "sum"),
        conversions=("conversions", "sum"),
        revenue=("revenue", "sum"),
    )
    grouped["咨询率"] = grouped["consultations"] / grouped["views"].replace(0, pd.NA)
    grouped["收藏率"] = grouped["favorites"] / grouped["views"].replace(0, pd.NA)
    grouped["成交率"] = grouped["conversions"] / grouped["consultations"].replace(0, pd.NA)
    out = grouped.tail(8).copy()
    numeric_cols = ["views", "favorites", "consultations", "conversions", "revenue", "咨询率", "收藏率", "成交率"]
    out[numeric_cols] = out[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    return out


def svg_icon(kind: str) -> str:
    icons = {
        "message": '<path d="M5 6.5A6.5 6.5 0 0 1 11.5 0h1A6.5 6.5 0 0 1 19 6.5v1A6.5 6.5 0 0 1 12.5 14H9l-5 3v-4.2A6.5 6.5 0 0 1 0 7.5v-1A6.5 6.5 0 0 1 5 6.5Z" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="6.5" cy="7" r="1" fill="currentColor"/><circle cx="10" cy="7" r="1" fill="currentColor"/><circle cx="13.5" cy="7" r="1" fill="currentColor"/>',
        "bookmark": '<path d="M4 2.5A2.5 2.5 0 0 1 6.5 0h7A2.5 2.5 0 0 1 16 2.5V19l-6-3.7L4 19V2.5Z" fill="none" stroke="currentColor" stroke-width="1.8"/>',
        "play": '<circle cx="10" cy="10" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8 6.5 14 10l-6 3.5v-7Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
        "yen": '<circle cx="10" cy="10" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M6.5 5.5 10 10l3.5-4.5M10 10v5M7 10h6M7 13h6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    }
    return f'<svg viewBox="0 0 20 20" aria-hidden="true">{icons.get(kind, icons["message"])}</svg>'


def inject_css() -> None:
    render_html(
        """
        <style>
        :root { color-scheme: light; }
        #MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { display:none !important; }
        header[data-testid="stHeader"] {
            display: block !important;
            height: 0 !important;
            background: transparent !important;
        }
        .stApp {
            background: #eef4f1;
            color: #143126;
        }
        .block-container {
            max-width: 1440px;
            padding: 2.2rem 2.4rem 2.4rem;
            margin-top: 1rem;
            margin-bottom: 1rem;
            background:
              radial-gradient(circle at 92% 4%, rgba(95,165,140,.08), transparent 18%),
              linear-gradient(180deg, #ffffff 0%, #fbfdfc 100%);
            border: 1px solid rgba(202, 220, 214, .72);
            border-radius: 26px;
            box-shadow: 0 28px 70px rgba(18, 57, 48, .10);
        }
        [data-testid="stSidebar"] {
            background:
                radial-gradient(circle at 24% 7%, rgba(247, 210, 112, .18), transparent 20%),
                linear-gradient(168deg, #064b3d 0%, #07372f 48%, #061f1d 100%) !important;
            border-right: 1px solid rgba(255,255,255,.08);
            box-shadow: 18px 0 42px rgba(7, 47, 41, .18);
        }
        [data-testid="stSidebar"] > div {
            background: transparent !important;
            padding: 1.35rem 1rem 1.3rem;
        }
        [data-testid="stSidebar"] * {
            color: #f7fffb;
        }
        [data-testid="stSidebar"] [data-testid="stButton"] > button {
            min-height: 48px;
            border: 1px solid rgba(255,255,255,.10) !important;
            background: rgba(255,255,255,.08) !important;
            color: #f7fffb !important;
            justify-content: flex-start !important;
            padding: 12px 14px !important;
            border-radius: 14px !important;
            box-shadow: none !important;
            font-weight: 720;
        }
        [data-testid="stSidebar"] [data-testid="stButton"] > button:hover {
            background: rgba(255,255,255,.18) !important;
            color: #ffffff !important;
            transform: translateX(2px);
        }
        [data-testid="stSidebar"] [data-testid="stButton"] > button:focus:not(:active) {
            color: #ffffff !important;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.16) !important;
        }
        [data-testid="stSidebarCollapsedControl"] {
            position: fixed !important;
            top: 18px !important;
            left: 18px !important;
            z-index: 100000 !important;
            width: 42px !important;
            height: 42px !important;
            border-radius: 13px !important;
            background: #07372f !important;
            color: #ffffff !important;
            border: 1px solid rgba(255,255,255,.18) !important;
            box-shadow: 0 16px 36px rgba(7, 47, 41, .24) !important;
        }
        [data-testid="stSidebarCollapsedControl"] svg {
            color: #ffffff !important;
            stroke: #ffffff !important;
        }
        [data-testid="stVerticalBlock"] { gap: 0.75rem; }
        .block-container > div > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-of-type {
            position: sticky;
            top: 14px;
            align-self: flex-start;
            z-index: 5;
            height: calc(100vh - 36px);
            min-height: 760px;
            border-radius: 24px 0 0 24px;
            background:
                radial-gradient(circle at 30% 10%, rgba(111, 210, 177, .34), transparent 24%),
                linear-gradient(160deg, #0f765e 0%, #145845 48%, #0c4337 100%);
            padding: 26px 16px;
        }
        div[data-testid="column"]:has(.sd-sidebar-shell) {
            position: sticky !important;
            top: 14px !important;
            align-self: flex-start !important;
            z-index: 8 !important;
            height: calc(100vh - 36px) !important;
            min-height: 760px !important;
            border-radius: 24px 0 0 24px !important;
            background:
                radial-gradient(circle at 28% 9%, rgba(247, 210, 112, .18), transparent 18%),
                linear-gradient(160deg, #0b6b55 0%, #0d4f40 50%, #092f29 100%) !important;
            padding: 26px 16px !important;
            box-shadow: 18px 0 45px rgba(15, 84, 67, .18);
        }
        .block-container > div > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-of-type * {
            color: #f7fffb;
        }
        .sd-sidebar {
            height: calc(100vh - 36px);
            min-height: 760px;
            border-radius: 24px 0 0 24px;
            background:
                radial-gradient(circle at 30% 10%, rgba(111, 210, 177, .34), transparent 24%),
                linear-gradient(160deg, #0f765e 0%, #145845 48%, #0c4337 100%);
            color: #f7fffb;
            padding: 26px 16px;
        }
        .sd-sidebar-shell {
            color: #f7fffb;
            margin-bottom: 18px;
        }
        .sd-brand {
            display: flex;
            gap: 12px;
            align-items: center;
            font-weight: 850;
            font-size: 24px;
            margin-bottom: 8px;
            color: #ffffff !important;
            text-shadow: 0 1px 12px rgba(0,0,0,.18);
        }
        .sd-sidebar-subtitle {
            color: rgba(247,255,251,.68) !important;
            font-size: 12px;
            line-height: 1.45;
            margin: 0 0 18px 2px;
        }
        .sd-active-page {
            display:inline-flex;
            align-items:center;
            gap:8px;
            padding: 7px 10px;
            margin: 0 0 14px 0;
            border-radius: 999px;
            background: rgba(255,255,255,.14);
            color: #ffffff !important;
            font-size: 12px;
            font-weight: 760;
        }
        .sd-logo {
            width: 38px; height: 38px; border-radius: 12px;
            background: linear-gradient(135deg, #eafff4, #87d7b6);
            position: relative;
            box-shadow: inset 0 -5px 0 rgba(18, 92, 72, .22);
        }
        .sd-logo:after {
            content: "";
            position: absolute;
            width: 10px; height: 10px;
            right: -2px; top: 6px;
            border-radius: 99px;
            background: #f6ce6d;
        }
        .sd-nav-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 13px 14px;
            margin: 7px 0;
            border-radius: 12px;
            color: rgba(255,255,255,.84);
            font-weight: 650;
            font-size: 15px;
        }
        .sd-nav-item.active {
            background: rgba(255,255,255,.18);
            color: #fff;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.12);
        }
        .sd-nav-icon {
            width: 22px; height: 22px; border-radius: 7px;
            display:inline-flex; align-items:center; justify-content:center;
            border: 1.3px solid rgba(255,255,255,.76);
            font-size: 12px;
        }
        div[data-testid="stButton"] > button {
            width: 100%;
            background: #ffffff;
            color: #15362c !important;
            border: 1px solid #d9e5e0;
            justify-content: center;
            padding: 13px 14px;
            border-radius: 12px;
            font-weight: 650;
            font-size: 15px;
            margin: 3px 0;
            box-shadow: 0 8px 20px rgba(21, 78, 63, .06);
        }
        div[data-testid="stButton"] > button:hover {
            background: #eef8f4;
            color: #087b5b !important;
            border: 1px solid #bfd8cf;
        }
        div[data-testid="stButton"] > button:focus:not(:active) {
            color: #087b5b !important;
            box-shadow: inset 0 0 0 1px rgba(8,123,91,.15);
        }
        .block-container > div > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-of-type div[data-testid="stButton"] > button {
            border: 0;
            background: rgba(255,255,255,.12);
            color: #f7fffb !important;
            justify-content: flex-start;
            box-shadow: none;
        }
        div[data-testid="column"]:has(.sd-sidebar-shell) div[data-testid="stButton"] > button {
            border: 1px solid rgba(255,255,255,.10) !important;
            background: rgba(255,255,255,.10) !important;
            color: #f7fffb !important;
            justify-content: flex-start !important;
            min-height: 48px;
            box-shadow: none !important;
        }
        div[data-testid="column"]:has(.sd-sidebar-shell) div[data-testid="stButton"] > button:hover {
            background: rgba(255,255,255,.22) !important;
            color: #ffffff !important;
            transform: translateX(2px);
        }
        .block-container > div > div > div[data-testid="stHorizontalBlock"]:first-of-type > div[data-testid="column"]:first-of-type div[data-testid="stButton"] > button:hover {
            background: rgba(255,255,255,.22);
            color: #fff !important;
            border: 0;
        }
        .sd-page {
            min-height: calc(100vh - 36px);
            padding: 34px 38px 30px;
            border-radius: 24px;
            background:
              radial-gradient(circle at 88% 9%, rgba(95,165,140,.10), transparent 18%),
              linear-gradient(180deg, #ffffff 0%, #fbfdfc 100%);
            box-shadow: 0 28px 70px rgba(18, 57, 48, .13);
        }
        .sd-title-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 20px;
            margin-bottom: 26px;
        }
        .sd-title {
            font-size: 30px;
            line-height: 1.1;
            font-weight: 760;
            letter-spacing: 0;
            color: #12251e;
        }
        .sd-actions { display:flex; gap: 12px; align-items:center; }
        .sd-select, .sd-button {
            border: 1px solid #d9e5e0;
            background: #fff;
            border-radius: 10px;
            height: 42px;
            padding: 0 16px;
            display:inline-flex;
            align-items:center;
            gap:8px;
            font-weight: 680;
            color:#18382e;
            box-shadow: 0 8px 20px rgba(21, 78, 63, .06);
        }
        .sd-button.primary {
            color:#0b6d53;
        }
        .sd-card-grid {
            display:grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 18px;
            margin-bottom: 30px;
        }
        .sd-metric-card {
            border: 1px solid #dbe8e4;
            border-radius: 16px;
            padding: 20px 20px 18px;
            min-height: 156px;
            background: rgba(255,255,255,.86);
            box-shadow: 0 13px 35px rgba(18, 57, 48, .07);
        }
        .sd-metric-card svg {
            width: 38px;
            height: 38px;
            color: #0f7b5f;
            margin-bottom: 13px;
        }
        .sd-lift {
            font-size: 34px;
            line-height: 1;
            color: #087b5b;
            font-weight: 780;
            margin-bottom: 14px;
        }
        .sd-label {
            color: #18342b;
            font-size: 17px;
            font-weight: 710;
        }
        .sd-up {
            color: #0a8d67;
            font-weight: 780;
            padding-left: 4px;
        }
        .sd-section-title {
            font-size: 23px;
            font-weight: 760;
            color:#12251e;
            margin: 8px 0 10px;
        }
        .sd-panel {
            border: 1px solid #deebe7;
            border-radius: 18px;
            background: rgba(255,255,255,.88);
            padding: 18px;
            box-shadow: 0 16px 38px rgba(18, 57, 48, .07);
        }
        .sd-action-card {
            border: 1px solid #dfebe7;
            border-radius: 14px;
            padding: 15px 16px;
            background: #ffffff;
            margin-bottom: 12px;
        }
        .sd-action-card.urgent {
            border-left: 4px solid #ff4d55;
        }
        .sd-action-card.warning {
            border-left: 4px solid #d99618;
        }
        .sd-badge {
            display:inline-flex;
            align-items:center;
            border-radius: 999px;
            padding: 4px 9px;
            background:#edf8f3;
            color:#087b5b;
            font-size: 12px;
            font-weight: 760;
            margin-bottom: 7px;
        }
        .sd-action-title {
            color:#10251f;
            font-size: 16px;
            font-weight: 750;
            margin-bottom: 5px;
        }
        .sd-muted { color:#64746e; font-size: 13.5px; line-height:1.55; }
        .sd-mini-grid {
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
        }
        .sd-mini {
            border-radius: 14px;
            border: 1px solid #e1ebe8;
            padding: 14px;
            background: #fff;
        }
        .sd-mini-label { color:#62746d; font-size: 13px; }
        .sd-mini-value { color:#15362c; font-weight: 780; font-size: 21px; margin-top: 5px; }
        .sd-table-note { color:#64746e; font-size: 13px; margin: 4px 0 10px; }
        .sd-graph-summary {
            display:grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin: 14px 0;
        }
        .sd-graph-pill {
            border:1px solid #dce9e5;
            background:#fff;
            border-radius:14px;
            padding:13px 14px;
        }
        .sd-graph-pill strong { display:block; color:#12362c; font-size:15px; margin-bottom:4px; }
        .sd-graph-pill span { color:#687972; font-size:13px; }
        .stPlotlyChart {
            border-radius: 18px;
        }
        @media (max-width: 980px) {
            .sd-sidebar { height:auto; min-height: auto; border-radius: 20px 20px 0 0; }
            .sd-page { padding: 24px 20px; border-radius: 0 0 20px 20px; }
            .sd-card-grid, .sd-mini-grid { grid-template-columns: 1fr 1fr; }
        }
        </style>
        """,
    )


def render_sidebar(active: str) -> None:
    items = [
        ("上传数据", "+"),
        ("经营诊断", "⌂"),
        ("决策检查", "✓"),
        ("行动计划", "↗"),
    ]
    render_html(
        f"""
        <div class="sd-sidebar-shell">
          <div class="sd-brand"><span class="sd-logo"></span><span>SoloDeck</span></div>
          <div class="sd-sidebar-subtitle">by Northstar Labs<br/>判断发现是否可靠，并生成下一步低成本验证计划。</div>
          <div class="sd-active-page">当前：{active}</div>
        </div>
        """,
    )
    for label, icon in items:
        text = f"{icon}  {label}"
        if st.button(text, key=f"nav_{label}", use_container_width=True):
            st.session_state.modern_page = label
            st.rerun()


def render_metric_cards(lifts: dict[str, dict]) -> None:
    order = ["consult", "favorite", "views", "revenue"]
    html = ['<div class="sd-card-grid">']
    for key in order:
        item = lifts[key]
        html.append(
            f"""
            <div class="sd-metric-card">
              {svg_icon(item["icon"])}
              <div class="sd-lift">{pct(item["lift"])}</div>
              <div class="sd-label">{item["label"]}<span class="sd-up">↑</span></div>
            </div>
            """
        )
    html.append("</div>")
    render_html("".join(html))


def creator_kpis(contents: pd.DataFrame) -> dict[str, float]:
    if contents.empty:
        return {"总播放": 0, "收藏率": 0, "咨询率": 0, "收入": 0, "RPM": 0}
    views = pd.to_numeric(contents.get("views", 0), errors="coerce").fillna(0).sum()
    favorites = pd.to_numeric(contents.get("favorites", 0), errors="coerce").fillna(0).sum()
    consultations = pd.to_numeric(contents.get("consultations", 0), errors="coerce").fillna(0).sum()
    revenue = pd.to_numeric(contents.get("revenue", 0), errors="coerce").fillna(0).sum()
    return {
        "总播放": float(views),
        "收藏率": safe_rate(float(favorites), float(views)),
        "咨询率": safe_rate(float(consultations), float(views)),
        "收入": float(revenue),
        "RPM": safe_rate(float(revenue), float(views)) * 1000,
    }


def render_kpi_strip(kpis: dict[str, float]) -> None:
    items = [
        ("总播放", f"{kpis['总播放']:,.0f}"),
        ("收藏率", f"{kpis['收藏率']:.2%}"),
        ("咨询率", f"{kpis['咨询率']:.2%}"),
        ("收入", f"¥{kpis['收入']:,.0f}"),
        ("RPM", f"¥{kpis['RPM']:.1f}"),
    ]
    html = ['<div class="sd-mini-grid" style="grid-template-columns:repeat(5,minmax(0,1fr));">']
    for label, value in items:
        html.append(f'<div class="sd-mini"><div class="sd-mini-label">{label}</div><div class="sd-mini-value">{value}</div></div>')
    html.append("</div>")
    render_html("".join(html))


def mapping_summary(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests) -> dict[str, int]:
    return {
        "内容": len(contents),
        "收入": len(revenues),
        "商务": len(campaigns),
        "实验": len(ab_tests),
        "产品": len(products),
        "反馈": len(feedback),
        "内测": len(beta_tests),
    }


def diagnose_observations(contents: pd.DataFrame, revenues: pd.DataFrame) -> list[dict]:
    observations: list[dict] = []
    if not contents.empty and "platform" in contents.columns:
        platform = platform_strategy_analysis(contents, revenues)["table"]
        if not platform.empty:
            top = platform.sort_values("revenue_per_hour", ascending=False).iloc[0]
            observations.append({
                "title": f"平台模式：{platform_name(top['platform'])} 更接近转化阵地",
                "detail": f"单位时间收益约 ¥{top['revenue_per_hour']:,.0f}/小时，适合优先放咨询入口和产品入口。",
            })
    if not contents.empty and "title_style" in contents.columns:
        title = title_style_analysis(contents)["table"]
        if not title.empty:
            top = title.sort_values("conversion_rate", ascending=False).iloc[0]
            observations.append({
                "title": f"标题模式：{STYLE_LABELS.get(top['title_style'], top['title_style'])} 转化更强",
                "detail": f"转化率约 {top['conversion_rate']:.2%}。这只是观察结果，放大前需要同平台对照。",
            })
    series = content_series_performance(contents)
    if not series.empty:
        row = series.iloc[0]
        warn = "有疲劳迹象" if row.get("fatigue_warning") else "暂未看到明显疲劳"
        observations.append({
            "title": f"系列模式：{row['series_id']} {warn}",
            "detail": f"系列收入约 ¥{row['total_revenue']:,.0f}，最近趋势：{cn_text(row['recent_3_trend'])}。",
        })
    if len(observations) < 3:
        observations.append({"title": "数据完整度：可以先做小规模验证", "detail": "当前数据足够生成方向建议，但正式放大前仍建议补充实验记录。"})
    return observations[:3]


DECISION_QUESTIONS = {
    "痛点标题是否真的有效": {
        "treatment": "title_style",
        "treatment_value": "pain_point",
        "control": "非痛点标题",
        "outcome": "consultations",
        "covariates": ["platform", "topic", "followers_before", "production_hours"],
    },
    "哪个平台更适合转化": {
        "treatment": "platform",
        "treatment_value": None,
        "control": "其他平台",
        "outcome": "conversions",
        "covariates": ["topic", "title_style", "followers_before", "production_hours"],
    },
    "这个系列是否应该继续": {
        "treatment": "series_id",
        "treatment_value": None,
        "control": "其他系列",
        "outcome": "revenue",
        "covariates": ["platform", "topic", "title_style", "production_hours"],
    },
    "高收藏内容是否值得产品化": {
        "treatment": "title_style",
        "treatment_value": "tutorial",
        "control": "其他标题",
        "outcome": "revenue",
        "covariates": ["platform", "topic", "favorites", "production_hours"],
    },
}


def decision_check(contents: pd.DataFrame, question: str) -> dict:
    config = DECISION_QUESTIONS[question]
    df = contents.copy()
    treatment = config["treatment"]
    outcome = config["outcome"]
    if df.empty or treatment not in df.columns or outcome not in df.columns:
        return {
            "question": question,
            "treatment": treatment,
            "control": config["control"],
            "outcome": outcome,
            "naive": 0.0,
            "adjusted": 0.0,
            "ci_low": 0.0,
            "ci_high": 0.0,
            "sample_size": 0,
            "confidence": "低",
            "decision": "先补数据",
            "warnings": ["缺少可比较的数据。"],
        }
    if config["treatment_value"] is None:
        top_value = df.groupby(treatment)[outcome].mean().sort_values(ascending=False).index[0]
        treatment_value = top_value
    else:
        treatment_value = config["treatment_value"]
    df["_treatment_flag"] = df[treatment].eq(treatment_value).astype(int)
    treated = df[df["_treatment_flag"].eq(1)][outcome].astype(float)
    control = df[df["_treatment_flag"].eq(0)][outcome].astype(float)
    naive = float(treated.mean() - control.mean()) if len(treated) and len(control) else 0.0
    covariates = [c for c in config["covariates"] if c in df.columns]
    adjusted = fixed_effect_estimate(df, "_treatment_flag", outcome, [c for c in ["platform", "account_id"] if c in df.columns], covariates)
    low = float(adjusted.get("ci_low", 0.0) or 0)
    high = float(adjusted.get("ci_high", 0.0) or 0)
    effect = float(adjusted.get("effect_estimate", 0.0) or 0)
    warnings = list(adjusted.get("warnings", []))
    if len(df) < 50:
        warnings.append("样本偏少，建议只作为下周验证依据。")
    if low <= 0 <= high:
        decision = "验证"
        confidence = "中低"
    elif effect > 0:
        decision = "小幅放大"
        confidence = "中"
    else:
        decision = "暂停放大"
        confidence = "中"
    return {
        "question": question,
        "treatment": f"{treatment} = {cn_text(treatment_value)}",
        "control": config["control"],
        "outcome": metric_name(outcome),
        "naive": naive,
        "adjusted": effect,
        "ci_low": low,
        "ci_high": high,
        "sample_size": int(len(df)),
        "confidence": confidence,
        "decision": decision,
        "warnings": warnings[:3],
    }


def action_cards(contents: pd.DataFrame, revenues: pd.DataFrame, decision: dict) -> list[dict]:
    observations = diagnose_observations(contents, revenues)
    continue_title = observations[0]["title"] if observations else "保留当前最强方向"
    overlap = detect_content_overlap(contents).head(1) if not contents.empty else pd.DataFrame()
    reduce_detail = "先暂停重复度高、制作重但收益低的内容。"
    if not overlap.empty:
        row = overlap.iloc[0]
        reduce_detail = f"《{cn_text(row['title'])}》相似度/疲劳风险偏高，下一条换角度或合并进系列。"
    return [
        {
            "label": "继续",
            "title": continue_title,
            "evidence": observations[0]["detail"] if observations else "来自当前上传数据的最高收益方向。",
            "risk": "只是经营模式观察，不直接等同因果。",
            "next": "本周保留 1-2 条同方向内容，72 小时看咨询和成交。",
        },
        {
            "label": "减少",
            "title": "减少重复或低收益投入",
            "evidence": reduce_detail,
            "risk": "过度重复可能拉低新鲜感，也会占用制作时间。",
            "next": "把重复主题改成案例、清单或直播答疑，不再原样复刻。",
        },
        {
            "label": "验证",
            "title": f"下周验证：{decision['question']}",
            "evidence": f"调整后增量 {decision['adjusted']:.2f}，区间 [{decision['ci_low']:.2f}, {decision['ci_high']:.2f}]，结论：{decision['decision']}。",
            "risk": "区间穿过 0 时不要直接放大。",
            "next": "连续 10-14 天做 4-6 条同主题内容，每条只改一个变量，固定 72 小时记录结果。",
        },
    ]


def render_trend_chart(trend: pd.DataFrame) -> None:
    fig = go.Figure()
    if not trend.empty:
        x = pd.to_datetime(trend["date"]).dt.strftime("%-m/%-d")
        fig.add_trace(go.Scatter(
            x=x,
            y=trend["咨询率"] * 100,
            mode="lines+markers",
            name="咨询率",
            line=dict(color="#087b5b", width=3),
            marker=dict(size=8),
        ))
        fig.add_trace(go.Scatter(
            x=x,
            y=trend["收藏率"] * 100,
            mode="lines+markers",
            name="收藏率",
            line=dict(color="#087b5b", width=2.4, dash="dash"),
            marker=dict(size=7),
        ))
    fig.update_layout(
        height=315,
        margin=dict(l=8, r=8, t=8, b=8),
        template="plotly_white",
        legend=dict(orientation="h", y=1.12, x=0.62),
        xaxis=dict(showgrid=False),
        yaxis=dict(title="转化率", ticksuffix="%", range=[0, max(7, float((trend[["咨询率", "收藏率"]].max().max() * 120) if not trend.empty else 7))]),
        font=dict(family="Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", color="#18342b"),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_actions(cards: list[dict]) -> None:
    html = []
    for card in cards[:3]:
        title = card.get("title", "建议")
        reason = card.get("reason") or card.get("insight", "")
        action = card.get("action", "")
        html.append(
            f"""
            <div class="sd-action-card">
              <span class="sd-badge">建议</span>
              <div class="sd-action-title">{title}</div>
              <div class="sd-muted">{reason}</div>
              <div class="sd-muted">{action}</div>
            </div>
            """
        )
    render_html("".join(html))


def render_card_list(cards: list[dict], limit: int = 4, badge: str = "建议") -> None:
    html = []
    for card in cards[:limit]:
        priority = str(card.get("priority", "medium"))
        css = "urgent" if priority == "high" else "warning" if priority == "medium" else ""
        title = cn_text(card.get("title", "建议"))
        insight = cn_text(card.get("insight") or card.get("reason") or "")
        action = cn_text(card.get("action", ""))
        confidence = cn_text(card.get("confidence", ""))
        html.append(
            f"""
            <div class="sd-action-card {css}">
              <span class="sd-badge">{badge}</span>
              <div class="sd-action-title">{title}</div>
              <div class="sd-muted">{insight}</div>
              <div class="sd-muted">{action}</div>
              <div class="sd-muted">{confidence}</div>
            </div>
            """
        )
    render_html("".join(html) if html else '<div class="sd-panel"><div class="sd-muted">暂无可展示内容。</div></div>')


def render_dataframe(df: pd.DataFrame, columns: dict[str, str] | None = None, max_rows: int = 8) -> None:
    if df is None or df.empty:
        render_html('<div class="sd-panel"><div class="sd-muted">暂无明细数据。</div></div>')
        return
    out = df.copy().head(max_rows)
    if columns:
        keep = [c for c in columns if c in out.columns]
        out = out[keep].rename(columns=columns)
    for col in out.columns:
        if out[col].dtype == object:
            out[col] = out[col].map(cn_text)
    st.dataframe(out, use_container_width=True, hide_index=True)


def neo4j_label(node_type: str) -> str:
    return {
        "content": "Content",
        "product": "Product",
        "feature": "Feature",
        "platform": "Platform",
        "topic": "Topic",
        "series": "Series",
        "segment": "UserSegment",
        "issue": "FeedbackIssue",
        "experiment": "Experiment",
        "treatment": "Treatment",
        "outcome": "Outcome",
        "metric": "Metric",
        "account": "Account",
    }.get(str(node_type), "Entity")


def neo4j_relation(relation: str) -> str:
    raw = str(relation).upper().replace(" ", "_").replace("-", "_")
    return {
        "POSTED_ON": "POSTED_ON",
        "HAS_TOPIC": "HAS_TOPIC",
        "IN_SERIES": "IN_SERIES",
        "HAS_FEATURE": "HAS_FEATURE",
        "TARGETS_SEGMENT": "TARGETS_SEGMENT",
        "HAS_ISSUE": "HAS_ISSUE",
        "HAS_OUTCOME": "HAS_OUTCOME",
        "TESTS": "TESTS",
        "GENERATES_REVENUE": "GENERATES_REVENUE",
    }.get(raw, raw[:36] or "RELATED_TO")


def neo4j_cypher_preview(nodes: pd.DataFrame, edges: pd.DataFrame, limit: int = 10) -> str:
    lines: list[str] = []
    for _, row in nodes.head(limit).iterrows():
        node_id = str(row.get("id", "")).replace("\\", "\\\\").replace("'", "\\'")
        label = str(row.get("label", "")).replace("\\", "\\\\").replace("'", "\\'")
        nlabel = neo4j_label(row.get("type", "Entity"))
        lines.append(f"MERGE (n:{nlabel} {{id: '{node_id}'}}) SET n.name = '{label}';")
    for _, row in edges.head(limit).iterrows():
        source = str(row.get("source", "")).replace("\\", "\\\\").replace("'", "\\'")
        target = str(row.get("target", "")).replace("\\", "\\\\").replace("'", "\\'")
        rel = neo4j_relation(row.get("relation", "RELATED_TO"))
        lines.append(f"MATCH (a {{id: '{source}'}}), (b {{id: '{target}'}}) MERGE (a)-[:{rel}]->(b);")
    return "\n".join(lines)


def simplified_kg_figure(kg_agent: dict) -> go.Figure:
    platform_topic = kg_agent.get("platform_topic", pd.DataFrame())
    features = kg_agent.get("feature_combinations", pd.DataFrame())
    series = kg_agent.get("series_exploration", pd.DataFrame())
    feedback_df = pd.DataFrame()
    global_context = kg_agent.get("global_context", {})
    if isinstance(global_context, dict):
        feedback_df = global_context.get("feedback", pd.DataFrame())

    labels = ["上传数据", "平台/主题", "产品功能", "内容系列", "用户反馈", "下周动作"]
    sources = [0, 0, 0, 0, 1, 2, 3, 4]
    targets = [1, 2, 3, 4, 5, 5, 5, 5]
    values = [3, 3, 2, 2, 3, 3, 2, 2]

    detail = []
    if not platform_topic.empty:
        row = platform_topic.iloc[0]
        detail.append(f"平台/主题：{cn_text(row.get('平台', ''))} / {cn_text(row.get('主题', ''))}")
    if not features.empty:
        row = features.iloc[0]
        detail.append(f"产品功能：{cn_text(row.get('功能组合', ''))}")
    if not series.empty:
        row = series.iloc[0]
        detail.append(f"内容系列：{cn_text(row.get('series_id', '重点系列'))}")
    if feedback_df is not None and not feedback_df.empty:
        row = feedback_df.iloc[0]
        detail.append(f"反馈问题：{cn_text(row.get('问题', ''))}")

    fig = go.Figure(data=[go.Sankey(
        arrangement="fixed",
        node=dict(
            pad=20,
            thickness=18,
            line=dict(color="rgba(15,84,67,.16)", width=1),
            label=labels,
            color=["#16342b", "#5fa58c", "#d9a441", "#7aa6d9", "#ef6f6c", "#0f7b5f"],
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=["rgba(15,123,95,.18)", "rgba(217,164,65,.20)", "rgba(122,166,217,.20)", "rgba(239,111,108,.18)", "rgba(15,123,95,.28)", "rgba(15,123,95,.28)", "rgba(15,123,95,.22)", "rgba(15,123,95,.22)"],
        ),
    )])
    subtitle = "；".join(detail[:4]) or "从上传数据中抽取关键实体，再连接到可执行动作。"
    fig.update_layout(
        title=f"决策图谱：{subtitle}",
        template="plotly_white",
        height=360,
        margin=dict(l=10, r=10, t=55, b=10),
        font=dict(size=14, color="#17362d"),
    )
    return fig


def render_causal_summary(agent: dict) -> None:
    causal = agent["modules"].get("causal_estimator_agent", {})
    ate = causal.get("ate", [])

    render_html('<div class="sd-section-title">因果增量摘要</div>')
    if ate:
        cards = []
        for item in ate[:3]:
            question = str(item.get("question", "策略增量")).replace("title_style -> views", "标题风格影响播放").replace("same_content_cross_platform -> revenue", "同内容跨平台收入差异").replace("advanced_methods_available", "专业模型可用")
            effect = item.get("effect_estimate", item.get("mean_difference", item.get("effect", 0)))
            confidence = item.get("confidence", "探索性")
            cards.append(
                f"""
                <div class="sd-action-card">
                  <span class="sd-badge">因果估计</span>
                  <div class="sd-action-title">{question}</div>
                  <div class="sd-muted">估计增量：{float(effect or 0):,.2f}；可信度：{confidence}</div>
                </div>
                """
            )
        render_html("".join(cards))
    else:
        render_html(
            """
            <div class="sd-action-card">
              <span class="sd-badge">因果估计</span>
              <div class="sd-action-title">等待更多实验数据</div>
              <div class="sd-muted">系统会在有 AB Test、跨平台或内测数据后估计策略增量。</div>
            </div>
            """,
        )


def render_knowledge_graph_content(agent: dict, contents: pd.DataFrame, products: pd.DataFrame, feedback: pd.DataFrame, revenues: pd.DataFrame) -> None:
    kg_agent = agent["modules"].get("knowledge_graph_agent", {})
    kg_nodes = kg_agent.get("nodes", pd.DataFrame())
    kg_edges = kg_agent.get("edges", pd.DataFrame())
    if kg_nodes.empty:
        render_html('<div class="sd-panel"><div class="sd-muted">暂无图谱数据。</div></div>')
        return
    answer = graph_rag_answer("", "全局查询", kg_nodes, kg_edges, contents, products, feedback, revenues, "中文")
    node_labels = kg_nodes["type"].nunique() if "type" in kg_nodes.columns else 0
    rel_types = kg_edges["relation"].nunique() if "relation" in kg_edges.columns and not kg_edges.empty else 0
    render_html(
        f"""
        <div class="sd-panel">
          <span class="sd-badge">Neo4j 图谱</span>
          <div class="sd-action-title">实体 {len(kg_nodes)} 个，关系 {len(kg_edges)} 条，标签 {node_labels} 类，关系类型 {rel_types} 类</div>
          <div class="sd-muted">{answer["answer"]}</div>
          <div class="sd-muted">说明：图谱负责解释实体关系，因果结论仍以实验和增量估计为准。</div>
        </div>
        """
    )
    st.plotly_chart(simplified_kg_figure(kg_agent), use_container_width=True, config={"displayModeBar": False})

    tabs = st.tabs(["关键关系", "Neo4j 结构", "Cypher 示例", "完整图谱"])
    with tabs[0]:
        local = graph_rag_answer("情绪陪伴", "局部查询", kg_nodes, kg_edges, contents, products, feedback, revenues, "中文")
        render_html(f'<div class="sd-table-note">{local["answer"]}</div>')
        evidence = local.get("evidence")
        if isinstance(evidence, pd.DataFrame) and not evidence.empty:
            render_dataframe(evidence, max_rows=10)
    with tabs[1]:
        label_summary = kg_nodes.groupby("type", as_index=False).agg(实体数=("id", "count")) if "type" in kg_nodes.columns else pd.DataFrame()
        rel_summary = kg_edges.groupby("relation", as_index=False).agg(关系数=("source", "count")) if "relation" in kg_edges.columns and not kg_edges.empty else pd.DataFrame()
        left, right = st.columns(2)
        with left:
            render_html('<div class="sd-section-title">实体标签</div>')
            render_dataframe(label_summary, {"type": "Neo4j 标签", "实体数": "实体数"}, max_rows=12)
        with right:
            render_html('<div class="sd-section-title">关系类型</div>')
            render_dataframe(rel_summary, {"relation": "Neo4j 关系", "关系数": "关系数"}, max_rows=12)
    with tabs[2]:
        cypher = neo4j_cypher_preview(kg_nodes, kg_edges, limit=12)
        st.code(cypher, language="cypher")
        st.code(
            """MATCH (p:Product)-[:HAS_FEATURE]->(f:Feature)
RETURN f.name AS 功能, count(p) AS 产品数, sum(p.revenue) AS 收入
ORDER BY 收入 DESC LIMIT 10;

MATCH (c:Content)-[:POSTED_ON]->(pl:Platform), (c)-[:HAS_TOPIC]->(t:Topic)
RETURN pl.name AS 平台, t.name AS 主题, sum(c.revenue) AS 收入
ORDER BY 收入 DESC LIMIT 10;""",
            language="cypher",
        )
    with tabs[3]:
        render_html('<div class="sd-table-note">完整图谱用于排查实体关系，不作为默认决策界面。</div>')
        st.plotly_chart(plot_knowledge_graph(kg_nodes.head(60), kg_edges.head(120), "中文"), use_container_width=True, config={"displayModeBar": False})


def open_knowledge_graph_window(agent: dict, contents: pd.DataFrame, products: pd.DataFrame, feedback: pd.DataFrame, revenues: pd.DataFrame) -> None:
    if hasattr(st, "dialog"):
        @st.dialog("知识图谱")
        def _dialog():
            render_knowledge_graph_content(agent, contents, products, feedback, revenues)
        _dialog()
    else:
        with st.expander("知识图谱", expanded=True):
            render_knowledge_graph_content(agent, contents, products, feedback, revenues)


def render_knowledge_graph_page(agent: dict, contents: pd.DataFrame, products: pd.DataFrame, feedback: pd.DataFrame, revenues: pd.DataFrame) -> None:
    render_html(
        """
        <div class="sd-title-row">
          <div class="sd-title">知识图谱</div>
          <div class="sd-actions"><div class="sd-select">GraphRAG</div></div>
        </div>
        """
    )
    render_knowledge_graph_content(agent, contents, products, feedback, revenues)


def render_overview(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests) -> None:
    period = st.session_state.get("period", "7天")
    days = int(period.replace("天", ""))
    agent = run_agent_suite(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests, lang="中文")
    lifts = metric_lifts(contents, revenues, days)
    trend = trend_frame(contents)
    render_html(
        f"""
        <div class="sd-title-row">
          <div class="sd-title">策略效果总览</div>
          <div class="sd-actions">
            <div class="sd-select">{period}⌄</div>
            <div class="sd-button primary">＋ 新建策略</div>
          </div>
        </div>
        """,
    )
    render_metric_cards(lifts)

    left, right = st.columns([0.62, 0.38], gap="large")
    with left:
        render_html('<div class="sd-section-title">趋势分析</div>')
        render_trend_chart(trend)
    with right:
        render_html('<div class="sd-section-title">下一步行动</div>')
        render_actions(agent["cards"])

    status_col, action_col = st.columns([0.58, 0.42], gap="large")
    with status_col:
        render_html('<div class="sd-section-title">经营状态</div>')
        pending = pending_payment_summary(revenues, campaigns)
        revenue_by_platform = platform_revenue_summary(revenues)
        top_platform = platform_name(revenue_by_platform.iloc[0]["platform"]) if not revenue_by_platform.empty else "暂无"
        render_html(
            f"""
            <div class="sd-mini-grid">
              <div class="sd-mini"><div class="sd-mini-label">收入主阵地</div><div class="sd-mini-value">{top_platform}</div></div>
              <div class="sd-mini"><div class="sd-mini-label">待收款</div><div class="sd-mini-value">¥{pending["total_pending_amount"]:,.0f}</div></div>
              <div class="sd-mini"><div class="sd-mini-label">实验记录</div><div class="sd-mini-value">{len(ab_tests)}</div></div>
            </div>
            """,
        )
    with action_col:
        render_html('<div class="sd-section-title">知识图谱</div>')
        render_html(
            """
            <div class="sd-panel">
              <span class="sd-badge">独立窗口</span>
              <div class="sd-action-title">内容、功能、平台和反馈关系</div>
              <div class="sd-muted">首页不直接展示图谱。点击下方按钮打开单独窗口查看 GraphRAG 查询和实体关系。</div>
            </div>
            """
        )
        if st.button("打开知识图谱窗口", use_container_width=True):
            open_knowledge_graph_window(agent, contents, products, feedback, revenues)

    render_causal_summary(agent)


def render_content(contents, revenues) -> None:
    plan = weekly_topic_plan(contents, revenues, n=5, language="中文")
    render_html('<div class="sd-title-row"><div class="sd-title">内容分析</div><div class="sd-actions"><div class="sd-button primary">生成排期</div></div></div>')
    left, right = st.columns([0.52, 0.48], gap="large")
    with left:
        render_html('<div class="sd-section-title">本周内容计划</div>')
        cards = []
        for idx, item in enumerate(plan, start=1):
            title_style = STYLE_LABELS.get(item["suggested_title_style"], item["suggested_title_style"])
            objective = cn_text(item["objective"])
            cards.append(
                f"""
                <div class="sd-action-card">
                  <span class="sd-badge">{idx}｜{platform_name(item["suggested_platform"])}</span>
                  <div class="sd-action-title">{cn_text(item["sample_title"])}</div>
                  <div class="sd-muted">主题：{cn_text(item["suggested_topic"])}；标题：{title_style}；目标：{objective}</div>
                  <div class="sd-muted">发布后 72 小时记录收藏、咨询和成交，只比较同平台同主题内容。</div>
                </div>
                """,
            )
        render_html("".join(cards))
    with right:
        render_html('<div class="sd-section-title">高商业价值内容</div>')
        value = content_commercial_value(contents, revenues, language="中文")
        render_dataframe(value, {
            "title": "内容",
            "platform": "平台",
            "topic": "主题",
            "commercial_score": "商业评分",
            "revenue": "收入",
            "consultations": "咨询",
            "conversions": "成交",
            "insight": "判断",
        }, max_rows=6)

    topic = topic_business_summary(contents)
    if not topic.empty:
        fig = go.Figure(go.Bar(
            x=topic.head(8)["total_revenue"],
            y=topic.head(8)["topic"].map(cn_text),
            orientation="h",
            marker_color="#0f7b5f",
        ))
        fig.update_layout(template="plotly_white", height=300, margin=dict(l=8, r=8, t=8, b=8), xaxis_title="收入", yaxis_title="")
        render_html('<div class="sd-section-title">主题收入排序</div>')
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_audience(agent: dict, feedback: pd.DataFrame, products: pd.DataFrame, contents: pd.DataFrame) -> None:
    render_html('<div class="sd-title-row"><div class="sd-title">受众分析</div><div class="sd-actions"><div class="sd-select">反馈与人群</div></div></div>')
    feedback_agent = agent["modules"].get("feedback_analysis_agent", {})
    left, right = st.columns([0.44, 0.56], gap="large")
    with left:
        render_html('<div class="sd-section-title">先处理的问题</div>')
        render_card_list(feedback_agent.get("cards", []), limit=3, badge="反馈")
    with right:
        render_html('<div class="sd-section-title">Roadmap 优先级</div>')
        roadmap = feedback_agent.get("roadmap")
        if roadmap is None or roadmap.empty:
            roadmap = feedback_to_roadmap(classify_feedback(feedback), products, contents)
        if roadmap is not None and not roadmap.empty:
            roadmap = roadmap.copy()
            roadmap["issue"] = roadmap["issue"].map(issue_name)
            render_dataframe(roadmap, {
                "issue": "问题",
                "evidence_count": "反馈数",
                "affected_segment": "影响人群",
                "business_impact": "商业影响",
                "suggested_action": "动作",
                "priority": "优先级",
            }, max_rows=8)
    classified = feedback_agent.get("classified_feedback")
    if classified is None or classified.empty:
        classified = classify_feedback(feedback)
    if classified is not None and not classified.empty and "issue_type" in classified.columns:
        issue_counts = classified["issue_type"].map(issue_name).value_counts().reset_index()
        issue_counts.columns = ["问题", "反馈数"]
        fig = go.Figure(go.Bar(x=issue_counts["问题"], y=issue_counts["反馈数"], marker_color="#0f7b5f"))
        fig.update_layout(template="plotly_white", height=280, margin=dict(l=8, r=8, t=8, b=8), yaxis_title="反馈数", xaxis_title="")
        render_html('<div class="sd-section-title">反馈集中在哪里</div>')
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_channel(agent: dict, contents: pd.DataFrame, revenues: pd.DataFrame) -> None:
    render_html('<div class="sd-title-row"><div class="sd-title">渠道分析</div><div class="sd-actions"><div class="sd-select">平台经营效率</div></div></div>')
    revenue_agent = agent["modules"].get("revenue_analysis_agent", {})
    strategy = platform_strategy_analysis(contents, revenues)["table"]
    left, right = st.columns([0.45, 0.55], gap="large")
    with left:
        render_html('<div class="sd-section-title">渠道动作</div>')
        render_card_list(revenue_agent.get("cards", []), limit=3, badge="渠道")
    with right:
        render_html('<div class="sd-section-title">平台效率</div>')
        render_dataframe(strategy, {
            "platform": "平台",
            "content_count": "内容数",
            "consultations": "咨询",
            "conversions": "成交",
            "revenue": "收入",
            "revenue_per_hour": "单位时间收益",
            "commercial_efficiency": "商业效率",
        }, max_rows=8)
    if not strategy.empty:
        plot_df = strategy.sort_values("revenue", ascending=False).head(8)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=plot_df["platform"].map(platform_name), y=plot_df["revenue"], name="收入", marker_color="#0f7b5f"))
        fig.add_trace(go.Scatter(x=plot_df["platform"].map(platform_name), y=plot_df["conversions"], name="成交", yaxis="y2", mode="lines+markers", line=dict(color="#d99618", width=3)))
        fig.update_layout(
            template="plotly_white",
            height=310,
            margin=dict(l=8, r=8, t=8, b=8),
            yaxis=dict(title="收入"),
            yaxis2=dict(title="成交", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1),
        )
        render_html('<div class="sd-section-title">收入与成交对比</div>')
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def render_conversion(agent: dict, contents: pd.DataFrame, ab_tests: pd.DataFrame, beta_tests: pd.DataFrame) -> None:
    render_html('<div class="sd-title-row"><div class="sd-title">转化分析</div><div class="sd-actions"><div class="sd-select">实验与增量</div></div></div>')
    ab_agent = agent["modules"].get("ab_test_agent", {})
    causal_agent = agent["modules"].get("causal_estimator_agent", {})
    left, right = st.columns([0.46, 0.54], gap="large")
    with left:
        render_html('<div class="sd-section-title">可以执行的策略</div>')
        render_card_list(ab_agent.get("cards", []) + causal_agent.get("cards", []), limit=4, badge="实验")
    with right:
        render_html('<div class="sd-section-title">实验结果</div>')
        ab_result = ab_agent.get("ab_results")
        if ab_result is None or ab_result.empty:
            ab_result = analyze_ab_test(ab_tests, language="中文") if not ab_tests.empty else pd.DataFrame()
        if ab_result is not None and not ab_result.empty:
            ab_result = ab_result.copy()
            ab_result["outcome_metric"] = ab_result["outcome_metric"].map(metric_name)
            render_dataframe(ab_result, {
                "experiment_id": "实验",
                "outcome_metric": "指标",
                "treatment_mean": "实验组",
                "control_mean": "对照组",
                "absolute_lift": "净提升",
                "relative_lift": "相对提升",
                "ci_low": "区间下限",
                "ci_high": "区间上限",
                "conclusion": "结论",
            }, max_rows=8)

    ate = pd.DataFrame(causal_agent.get("ate", []))
    if not ate.empty:
        ate["question"] = ate["question"].map(cn_text)
        for col in ["effect_estimate", "effect", "mean_difference"]:
            if col in ate.columns:
                ate["增量估计"] = ate[col]
                break
        render_html('<div class="sd-section-title">因果增量估计</div>')
        render_dataframe(ate, {
            "question": "问题",
            "method": "方法",
            "增量估计": "增量估计",
            "ci_low": "区间下限",
            "ci_high": "区间上限",
            "sample_size": "样本量",
            "confidence": "可信度",
            "interpretation": "解释",
        }, max_rows=8)

    design = design_ab_test("提升咨询", "公众号/视频号", "桌面陪伴机器人", "结果导向标题", "教程标题", "咨询量", language="中文")
    render_html(
        f"""
        <div class="sd-panel">
          <span class="sd-badge">下次实验</span>
          <div class="sd-action-title">{design["hypothesis"]}</div>
          <div class="sd-muted">周期：{design["duration_suggestion"]}；样本：{design["minimum_sample_suggestion"]}</div>
          <div class="sd-muted">主指标：{design["primary_metric"]}；同时观察：{", ".join(design["secondary_metrics"][:3])}</div>
        </div>
        """
    )


def render_upload_page() -> None:
    render_html('<div class="sd-title-row"><div class="sd-title">资料导入</div><div class="sd-actions"><div class="sd-select">上传 / 粘贴 / 截图</div></div></div>')
    render_html(
        """
        <div class="sd-panel">
          <span class="sd-badge">上传后立即进入分析</span>
          <div class="sd-action-title">CSV / Excel 自动识别；截图和文字由大模型读取</div>
          <div class="sd-muted">支持内容后台、收入流水、商务合作、实验记录、产品、反馈和内测数据。上传后侧栏所有页面会自动刷新。</div>
        </div>
        """
    )
    target_label = st.selectbox("截图或文字写入哪里", ["内容", "收入", "商务"], index=0)
    target_map = {"内容": "contents", "收入": "revenues", "商务": "campaigns"}
    uploaded_files = st.file_uploader(
        "上传资料",
        type=["csv", "xlsx", "xls", "txt", "png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        help="CSV/Excel 会自动识别表类型；图片和文字会调用大模型读取。",
    )
    pasted_text = st.text_area("文字补充", placeholder="粘贴后台数据、订单截图里的文字、聊天报价、收款记录或待办事项...", height=110)
    if st.button("读取并加入当前工作区", use_container_width=True):
        added = {key: 0 for key in TABLE_NAMES}
        notes: list[str] = []
        llm_files = []
        for file in uploaded_files or []:
            name = getattr(file, "name", "").lower()
            if name.endswith((".csv", ".xlsx", ".xls")):
                try:
                    df = read_uploaded_table(file)
                    key = infer_table_key(df, name)
                    append_workspace_table(key, df)
                    added[key] += len(df)
                except Exception as exc:
                    notes.append(f"{getattr(file, 'name', '文件')} 读取失败：{exc}")
            else:
                llm_files.append(file)
        if llm_files or pasted_text.strip():
            try:
                result = extract_records_from_uploads(pasted_text, llm_files, target_map[target_label], language="中文")
                records = pd.DataFrame(result.get("records", []))
                if not records.empty:
                    append_workspace_table(target_map[target_label], records)
                    added[target_map[target_label]] += len(records)
                tasks = result.get("tasks", [])
                if tasks:
                    task_df = pd.DataFrame(tasks)
                    append_workspace_table("feedback", task_df.assign(feedback_text=task_df.get("detail", task_df.get("title", "")), issue_type="待办"))
                    added["feedback"] += len(task_df)
                if result.get("notes"):
                    notes.append(str(result["notes"]))
            except Exception as exc:
                notes.append(f"大模型读取失败：{exc}")
        summary = "，".join(f"{TABLE_NAMES[k]} {v}" for k, v in added.items() if v)
        st.session_state.modern_upload_notice = f"已加入：{summary or '0 条'}。" + ("；".join(notes) if notes else "")
        st.rerun()
    if st.session_state.get("modern_upload_notice"):
        st.success(st.session_state.modern_upload_notice)


def render_diagnose_page(contents: pd.DataFrame, revenues: pd.DataFrame, campaigns: pd.DataFrame, ab_tests: pd.DataFrame, products: pd.DataFrame, feedback: pd.DataFrame, beta_tests: pd.DataFrame) -> None:
    summary = mapping_summary(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests)
    render_html('<div class="sd-title-row"><div class="sd-title">经营诊断</div><div class="sd-actions"><div class="sd-select">只看关键结论</div></div></div>')
    render_kpi_strip(creator_kpis(contents))
    render_html(
        f"""
        <div class="sd-panel" style="margin-top:16px;">
          <span class="sd-badge">数据映射</span>
          <div class="sd-action-title">已识别：内容 {summary['内容']}、收入 {summary['收入']}、实验 {summary['实验']}、反馈 {summary['反馈']}</div>
          <div class="sd-muted">系统只展示映射摘要和经营结论，不在前台暴露原始明细。</div>
        </div>
        """
    )
    render_html('<div class="sd-section-title">三条观察</div>')
    cards = []
    for item in diagnose_observations(contents, revenues):
        cards.append(
            f"""
            <div class="sd-action-card">
              <span class="sd-badge">观察</span>
              <div class="sd-action-title">{item['title']}</div>
              <div class="sd-muted">{item['detail']}</div>
            </div>
            """
        )
    render_html("".join(cards))


def render_decision_page(contents: pd.DataFrame) -> dict:
    render_html('<div class="sd-title-row"><div class="sd-title">决策检查</div><div class="sd-actions"><div class="sd-select">可靠性优先</div></div></div>')
    question = st.selectbox("选择你要判断的问题", list(DECISION_QUESTIONS.keys()))
    result = decision_check(contents, question)
    render_html(
        f"""
        <div class="sd-panel">
          <span class="sd-badge">判断</span>
          <div class="sd-action-title">{result['decision']}：{result['question']}</div>
          <div class="sd-muted">策略：{result['treatment']}；对照：{result['control']}；结果指标：{result['outcome']}。</div>
        </div>
        <div class="sd-mini-grid" style="margin-top:14px;">
          <div class="sd-mini"><div class="sd-mini-label">直接差异</div><div class="sd-mini-value">{result['naive']:.2f}</div></div>
          <div class="sd-mini"><div class="sd-mini-label">调整后增量</div><div class="sd-mini-value">{result['adjusted']:.2f}</div></div>
          <div class="sd-mini"><div class="sd-mini-label">样本量</div><div class="sd-mini-value">{result['sample_size']}</div></div>
        </div>
        <div class="sd-panel" style="margin-top:14px;">
          <span class="sd-badge">置信区间</span>
          <div class="sd-action-title">[{result['ci_low']:.2f}, {result['ci_high']:.2f}]；可信度：{result['confidence']}</div>
          <div class="sd-muted">{'；'.join(result['warnings']) if result['warnings'] else '暂未发现主要风险。'}</div>
        </div>
        """
    )
    st.session_state.modern_decision_result = result
    return result


def render_action_plan_page(contents: pd.DataFrame, revenues: pd.DataFrame) -> None:
    render_html('<div class="sd-title-row"><div class="sd-title">行动计划</div><div class="sd-actions"><div class="sd-select">只保留 3 件事</div></div></div>')
    decision = st.session_state.get("modern_decision_result") or decision_check(contents, "痛点标题是否真的有效")
    cards = action_cards(contents, revenues, decision)
    html = []
    for card in cards:
        html.append(
            f"""
            <div class="sd-action-card urgent">
              <span class="sd-badge">{card['label']}</span>
              <div class="sd-action-title">{card['title']}</div>
              <div class="sd-muted">依据：{card['evidence']}</div>
              <div class="sd-muted">风险：{card['risk']}</div>
              <div class="sd-muted">下一步：{card['next']}</div>
            </div>
            """
        )
    render_html("".join(html))
    render_html("<!-- trace: mapping_summary -> creator_kpis -> diagnose_observations -> decision_check -> action_cards -->")


def render_settings(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests) -> None:
    render_html('<div class="sd-title-row"><div class="sd-title">设置</div><div class="sd-actions"><div class="sd-select">数据工作区</div></div></div>')
    data_dir = find_synthetic_data_dir(ROOT.parent) or ROOT / "data"
    dashboard = campaign_dashboard(campaigns)
    risks = campaign_risk_alerts(campaigns, language="中文")
    status = model_status()
    render_html(
        f"""
        <div class="sd-mini-grid">
          <div class="sd-mini"><div class="sd-mini-label">内容</div><div class="sd-mini-value">{len(contents)}</div></div>
          <div class="sd-mini"><div class="sd-mini-label">产品</div><div class="sd-mini-value">{len(products)}</div></div>
          <div class="sd-mini"><div class="sd-mini-label">反馈</div><div class="sd-mini-value">{len(feedback)}</div></div>
        </div>
        <div class="sd-mini-grid" style="margin-top:12px;">
          <div class="sd-mini"><div class="sd-mini-label">收入流水</div><div class="sd-mini-value">{len(revenues)}</div></div>
          <div class="sd-mini"><div class="sd-mini-label">商务合作</div><div class="sd-mini-value">{dashboard.get("total_campaigns", len(campaigns))}</div></div>
          <div class="sd-mini"><div class="sd-mini-label">风险提醒</div><div class="sd-mini-value">{len(risks)}</div></div>
        </div>
        <div class="sd-panel" style="margin-top:16px;">
          <span class="sd-badge">数据源</span>
          <div class="sd-action-title">{data_dir}</div>
          <div class="sd-muted">当前前端已接入内容、收入、商务、实验、产品、反馈、内测、因果估计和知识图谱后端模块。</div>
          <div class="sd-muted">大模型：基础模型 {'已配置' if status.get('basic_configured') else '未配置'}；高级模型 {'已配置' if status.get('advanced_configured') else '未配置'}。</div>
        </div>
        """
    )


def main() -> None:
    inject_css()
    contents, revenues, campaigns, ab_tests, products, feedback, beta_tests = workspace_data()
    agent = run_agent_suite(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests, lang="中文")
    if "modern_page" not in st.session_state:
        st.session_state.modern_page = "上传数据"
    if "period" not in st.session_state:
        st.session_state.period = "7天"

    with st.sidebar:
        render_sidebar(st.session_state.modern_page)

    if st.session_state.modern_page == "上传数据":
        render_upload_page()
    elif st.session_state.modern_page == "经营诊断":
        render_diagnose_page(contents, revenues, campaigns, ab_tests, products, feedback, beta_tests)
    elif st.session_state.modern_page == "决策检查":
        render_decision_page(contents)
    else:
        render_action_plan_page(contents, revenues)


if __name__ == "__main__":
    main()
