from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import urllib3

from customs_pipeline import CustomsClient, refresh_customs_data
from presentation_bootstrap import refresh_presentation_modules
refresh_presentation_modules()
from dashboard_utils import available_growth_years, growth_year_comparison_range, normalize_month_range, parse_date_text, quick_month_range, format_100m_usd, industry_period_summary, sidebar_guide_sections
from data_lineage import page_methodology, source_caption
from deployment_mode import allow_admin_controls, is_shared_mode
from drilldown_utils import ALL_OPTION, drilldown_options, product_monitor_selection
from export_analytics import growth_leaders
from flash_trade import flash_comparison_frame, load_flash_snapshots, refresh_flash_cache
from kosis_cache import read_kosis_cache, write_kosis_cache
from kosis_client import fetch_kosis_history_payload
from mart_builder import build_analysis_mart, mart_status
from provisional_trade import PRODUCTS, COUNTRIES, TOP20_LINKS, load_snapshots, checkpoint_history, major_product_total, country_composition
import importlib
# Cloud reruns can retain chart modules from the previous deployment.
importlib.reload(importlib.import_module('trade_charts'))
from trade_charts import amount_growth_figure, provisional_summary_figure

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DB = DATA_DIR / "investment_advisor.sqlite"
LOCAL_MART = DATA_DIR / "investment_mart.sqlite"
SHARE_MART = DATA_DIR / "share_snapshot.sqlite"
TAXONOMY_PATH = DATA_DIR / "motir20_hsk_mti_mapping_2026_full_clean.csv"
LEGACY_MAPPING_PATH = DATA_DIR / "motir20_hsk_mti_mapping_2026.csv"
KOSIS_CACHE = DATA_DIR / "kosis_cycle_cache.csv"
BRIDGE_PATH = DATA_DIR / "industry_export_bridge.csv"
FLASH_SEED = DATA_DIR / "export_flash_seed.csv"
FLASH_CACHE = DATA_DIR / "export_flash_cache.csv"
PROVISIONAL_CACHE = DATA_DIR / "export_provisional.csv"

st.set_page_config(page_title="Investment Advisor Tool v4.1", page_icon="📈", layout="wide")
st.markdown(
    """
    <style>
      .block-container {max-width: 1880px; padding-top:.65rem; padding-bottom:2rem;}
      h1 {font-size:2.05rem !important; margin-bottom:.1rem !important;}
      h2 {font-size:1.45rem !important; margin-top:.35rem !important;}
      h3 {font-size:1.08rem !important;}
      [data-testid="stMetricValue"] {font-size:1.45rem;}
      [data-testid="stMetricLabel"] {font-size:.80rem;}
      div[data-testid="stHorizontalBlock"] {gap:.65rem;}
      div[data-testid="stPlotlyChart"] {border-radius:10px;}
      div[data-testid="stDownloadButton"] button {padding:.16rem .48rem !important; min-height:1.9rem !important; font-size:.76rem !important;}
      .small-note {color:#8b93a1; font-size:.80rem; line-height:1.35;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _get_secret(name: str, default=""):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)


def resolve_mart_path() -> Path | None:
    if mart_status(LOCAL_MART).get("ready"):
        return LOCAL_MART
    if mart_status(SHARE_MART).get("ready"):
        return SHARE_MART
    return None


def _mtime(path: Path | None) -> float:
    return path.stat().st_mtime if path and path.exists() else 0.0


@st.cache_data(show_spinner=False)
def mart_query(path_str: str, mtime: float, sql: str, params: tuple = ()) -> pd.DataFrame:
    path = Path(path_str)
    if not path.exists():
        return pd.DataFrame()
    with sqlite3.connect(path) as con:
        df = pd.read_sql_query(sql, con, params=params)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    mart = resolve_mart_path()
    if mart is None:
        return pd.DataFrame()
    return mart_query(str(mart), _mtime(mart), sql, params)


def normalize_kosis_payload(payload) -> pd.DataFrame:
    df = pd.DataFrame(payload)
    if df.empty:
        return df
    code_col = next((c for c in ["C2", "C1", "C2_NM", "C1_NM"] if c in df.columns), None)
    if code_col is None or "DT" not in df.columns or "PRD_DE" not in df.columns:
        raise ValueError(f"Unexpected KOSIS schema: {list(df.columns)}")
    df["IND_CODE"] = df[code_col].astype(str).str.strip()
    df["DT_val"] = pd.to_numeric(df["DT"].astype(str).str.replace(",", "", regex=False), errors="coerce")
    df["PRD_DE"] = df["PRD_DE"].astype(str)
    return df.dropna(subset=["PRD_DE", "DT_val", "IND_CODE"]).copy()


def rebuild_mart() -> dict:
    if not RAW_DB.exists():
        raise FileNotFoundError("관세청 raw DB가 없습니다.")
    return build_analysis_mart(RAW_DB, LOCAL_MART, TAXONOMY_PATH, KOSIS_CACHE, BRIDGE_PATH)


def refresh_customs_and_mart(customs_key: str, verify_ssl: bool):
    if not customs_key:
        st.error("관세청 API Key가 없습니다.")
        return
    mapping = pd.read_csv(LEGACY_MAPPING_PATH, dtype=str).fillna("")
    with st.spinner("관세청 최신월 확인 → raw DB 반영 → mart 재생성 중..."):
        result = refresh_customs_data(
            client=CustomsClient(customs_key, verify_ssl=verify_ssl, timeout=90),
            db_path=RAW_DB,
            mapping=mapping,
            target_month=None,
            bootstrap_months=int(_get_secret("CUSTOMS_BOOTSTRAP_MONTHS", "24") or 24),
            tracked_countries=[x.strip().upper() for x in str(_get_secret("CUSTOMS_TRACK_COUNTRIES", "US,CN,VN,JP")).split(",") if x.strip()],
            probe_months=4,
            history_start=str(_get_secret("CUSTOMS_HISTORY_START", "1995-01") or "1995-01"),
            item_country_months=int(_get_secret("CUSTOMS_ITEM_COUNTRY_MONTHS", "24") or 24),
        )
        rebuild_mart()
    st.cache_data.clear()
    st.success(f"관세청 + mart 갱신 완료 · {result.get('target_month') or '-'}")


def refresh_kosis_and_mart(kosis_key: str, verify_ssl: bool):
    if not kosis_key:
        st.error("KOSIS API Key가 없습니다.")
        return
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    with st.spinner("KOSIS 장기 시계열 갱신 → mart 재생성 중..."):
        payload, _ = fetch_kosis_history_payload(
            api_key=kosis_key,
            months=int(_get_secret("KOSIS_HISTORY_MONTHS", "720") or 720),
            chunk_months=60,
            verify_ssl=verify_ssl,
        )
        df = normalize_kosis_payload(payload)
        if not df.empty:
            write_kosis_cache(df, KOSIS_CACHE)
        if RAW_DB.exists():
            rebuild_mart()
    st.cache_data.clear()
    st.success("KOSIS + mart 갱신 완료")


def fig_layout(fig: go.Figure, height: int = 350, y_title: str | None = None, legend: bool = True) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=45, b=34),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0) if legend else None,
    )
    if y_title:
        fig.update_yaxes(title=y_title)
    return fig


def _figure_frame(fig: go.Figure) -> pd.DataFrame:
    frames = []
    for i, trace in enumerate(fig.data):
        name = str(getattr(trace, "name", "") or f"series_{i+1}")
        x = getattr(trace, "x", None)
        y = getattr(trace, "y", None)
        if x is not None and y is not None:
            try:
                xa, ya = list(x), list(y)
            except Exception:
                continue
            n = min(len(xa), len(ya))
            if n:
                frames.append(pd.DataFrame({"series": [name] * n, "x": xa[:n], "y": ya[:n]}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def render_chart(fig: go.Figure, *, source_key: str, csv_df: pd.DataFrame | None = None, csv_name: str = "chart", key: str | None = None, selectable: bool = False):
    kwargs = {"width": "stretch"}
    if key:
        kwargs["key"] = key
    if selectable:
        kwargs["on_select"] = "rerun"
        kwargs["selection_mode"] = "points"
    event = st.plotly_chart(fig, **kwargs)
    raw = csv_df.copy() if isinstance(csv_df, pd.DataFrame) else _figure_frame(fig)
    if not raw.empty:
        _, dl = st.columns([12, 1])
        with dl:
            st.download_button(
                "CSV",
                raw.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"{csv_name}.csv",
                mime="text/csv",
                key=f"csv_{key or csv_name}",
                help="현재 차트에 표출된 데이터",
                width="content",
            )
    st.caption(source_caption(source_key))
    return event


def selected_point_label(event) -> str | None:
    if event is None:
        return None
    try:
        points = event.selection.points
    except Exception:
        try:
            points = event.get("selection", {}).get("points", [])
        except Exception:
            return None
    if not points:
        return None
    p = points[-1]
    if not isinstance(p, dict):
        try:
            p = dict(p)
        except Exception:
            return None
    for key in ["y", "x", "text"]:
        if p.get(key) not in [None, ""]:
            return str(p.get(key))
    return None


def month_sql(table: str, start: pd.Timestamp, end: pd.Timestamp, extra: str = "", params: tuple = ()) -> pd.DataFrame:
    sql = f"SELECT * FROM {table} WHERE date>=? AND date<=? {extra} ORDER BY date"
    return q(sql, (start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")) + params)


def pct(v) -> str:
    return f"{float(v):+.1f}%" if v is not None and pd.notna(v) else "-"


def usd100m(v) -> str:
    return format_100m_usd(v) if v is not None and pd.notna(v) else "-"


def mart_bounds() -> tuple[pd.Timestamp, pd.Timestamp]:
    row = q("SELECT MIN(date) AS lo, MAX(date) AS hi FROM mart_export_top20_monthly")
    if row.empty or not row.iloc[0]["hi"]:
        d = pd.Timestamp("2026-08-01")
        return d - pd.DateOffset(months=59), d
    return pd.Timestamp(row.iloc[0]["lo"]), pd.Timestamp(row.iloc[0]["hi"])


def latest_snapshot(table: str, end: pd.Timestamp, where: str = "", params: tuple = ()) -> pd.DataFrame:
    extra = f"AND {where}" if where else ""
    maxd = q(f"SELECT MAX(date) AS d FROM {table} WHERE date<=? {extra}", (end.strftime("%Y-%m-%d"),) + params)
    if maxd.empty or not maxd.iloc[0]["d"]:
        return pd.DataFrame()
    return q(f"SELECT * FROM {table} WHERE date=? {extra}", (pd.Timestamp(maxd.iloc[0]["d"]).strftime("%Y-%m-%d"),) + params)


# -----------------------------------------------------------------------------
# Local/share mode setup
# -----------------------------------------------------------------------------
shared_mode = is_shared_mode(_get_secret("SHARED_MODE", "false"))
kosis_key = str(_get_secret("KOSIS_API_KEY", ""))
customs_key = str(_get_secret("CUSTOMS_SERVICE_KEY", ""))
kosis_verify = str(_get_secret("KOSIS_VERIFY_SSL", "false")).lower() not in {"false", "0", "no"}
customs_verify = str(_get_secret("CUSTOMS_VERIFY_SSL", "false")).lower() not in {"false", "0", "no"}

mart = resolve_mart_path()
if mart is None:
    st.title("Investment Advisor Tool · v4.1")
    st.warning("분석 Mart가 아직 없습니다.")
    if RAW_DB.exists():
        st.write("기존 관세청 DB는 발견했습니다. 아래 버튼으로 v4.1 분석 Mart를 한 번 생성하면 이후 페이지 로딩이 빨라집니다.")
        if st.button("v4.1 Mart 생성", type="primary"):
            with st.spinner("Top20 → 중분류 → 대표품목 → KOSIS 사전집계 중..."):
                result = rebuild_mart()
            st.cache_data.clear()
            st.success(f"Mart 생성 완료 · Top20 {result['top20_rows']:,}행 / 제품 {result['product_rows']:,}행")
            st.rerun()
    else:
        st.info("Mac에서는 MIGRATE_FROM_V3_2.command를 실행하세요. 다른 PC에서 볼 때는 MAKE_PORTABLE로 만든 PORTABLE ZIP을 사용하세요.")
    st.stop()

is_share = mart == SHARE_MART and not LOCAL_MART.exists()
status = mart_status(mart)


@st.dialog("Investment Advisor 사용 가이드북", width="large")
def render_guidebook():
    st.caption("기능을 선택해 사용법·산출 기준·데이터 출처를 확인하세요.")
    for index, (guide_title, guide_body) in enumerate(sidebar_guide_sections().items()):
        with st.expander(guide_title, expanded=index == 0):
            st.markdown(guide_body)


with st.sidebar:
    st.markdown("### 데이터 상태")
    st.caption(f"모드: {'Portable / Share' if is_share else 'Local Research'}")
    st.caption(f"수출: {status.get('earliest_export_month','-')} ~ {status.get('latest_export_month','-')}")
    st.caption(f"KOSIS: {status.get('latest_kosis_month') or '미연결'}")
    st.caption(f"Mart 생성: {status.get('built_at','-')}")
    if allow_admin_controls(shared=shared_mode, raw_exists=RAW_DB.exists()) and not is_share:
        with st.expander("데이터 최신화", expanded=False):
            if not shared_mode:
                kosis_key = st.text_input("KOSIS API Key", value=kosis_key, type="password")
                customs_key = st.text_input("관세청 API Key", value=customs_key, type="password")
            if st.button("관세청 + Mart 최신화", width="stretch"):
                refresh_customs_and_mart(customs_key, customs_verify)
                st.rerun()
            if st.button("KOSIS + Mart 최신화", width="stretch"):
                refresh_kosis_and_mart(kosis_key, kosis_verify)
                st.rerun()
            if st.button("Mart만 재생성", width="stretch"):
                with st.spinner("Mart 재생성 중..."):
                    rebuild_mart()
                st.cache_data.clear(); st.rerun()
    if st.button("📘 사용 가이드북 열기", width="stretch"):
        render_guidebook()

st.title("Investment Advisor Tool · v4.1")
st.caption("Top-down: 실물경기 → 수출 → 산업 → 세부제품 · Mart-first · 금액 단위: 억달러")

PAGES = ["종합 현황", "산업 상세", "수출 성장", "품목 모니터", "최근 수출", "데이터 점검"]
if st.session_state.get("page") not in PAGES:
    st.session_state["page"] = PAGES[0]
page = st.radio("페이지", PAGES, horizontal=True, label_visibility="collapsed", key="page")

available_start, available_end = mart_bounds()
period_start, period_end = quick_month_range(available_end, "5Y", available_start)
if "period_start_input" not in st.session_state or "period_end_input" not in st.session_state:
    a, b = quick_month_range(available_end, "5Y", available_start)
    st.session_state.period_start_input = f"{a:%Y-%m-%d}"; st.session_state.period_end_input = f"{b:%Y-%m-%d}"

if page not in ("수출 성장", "최근 수출"):
    with st.container(border=True):
        r1, r2, r3, r4 = st.columns([1.0, 1.2, 1.2, 1.1])
        quick = r1.selectbox("빠른 기간", ["직접", "1Y", "3Y", "5Y", "10Y", "전체"], key="quick_range")
        if quick != "직접":
            a, b = quick_month_range(available_end, quick, available_start)
            st.session_state.period_start_input = f"{a:%Y-%m-%d}"; st.session_state.period_end_input = f"{b:%Y-%m-%d}"
        start_text = r2.text_input("기간 시작", key="period_start_input", help="260901, 20260901, 2026-09-01 형식 지원")
        end_text = r3.text_input("기간 종료", key="period_end_input", help="260901, 20260901, 2026-09-01 형식 지원")
        try:
            start_date, end_date = parse_date_text(start_text), parse_date_text(end_text)
            if start_date < available_start or start_date > available_end:
                raise ValueError(f"월간 품목 조회 가능 기간은 {available_start:%Y-%m-%d}~{available_end:%Y-%m-%d}입니다.")
            if end_date > available_end:
                st.info(f"월간 HS10 품목 데이터는 {available_end:%Y-%m}까지입니다. 월간 차트는 해당 월까지 표시하며, 최신 잠정 수출은 ‘최근 수출’에서 확인하세요.")
                end_date = available_end
            period_start, period_end = normalize_month_range(start_date, end_date)
            st.session_state["_last_valid_period"] = (period_start, period_end)
        except ValueError as exc:
            st.error(str(exc))
            period_start, period_end = st.session_state.get("_last_valid_period", (available_start, available_end))
        r4.metric("표시 기간", f"{period_start:%Y.%m}–{period_end:%Y.%m}")

with st.expander("ⓘ 데이터·산출 기준", expanded=False):
    st.markdown(page_methodology(page))


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------
def render_overview():
    top20 = month_sql("mart_export_top20_monthly", period_start, period_end)
    total = month_sql("mart_export_total_monthly", period_start, period_end)
    signal = month_sql("mart_industry_signal_monthly", period_start, period_end)
    kosis = month_sql("mart_kosis_cycle_monthly", period_start, period_end)
    middle = month_sql("mart_export_middle_monthly", period_start, period_end)
    if top20.empty:
        st.info("선택 기간 데이터가 없습니다."); return
    latest = top20["date"].max(); snap = top20[top20["date"] == latest].copy()
    agg_source = month_sql("mart_export_top20_monthly", period_start-pd.DateOffset(months=12), period_end)
    agg = agg_source.groupby("date", as_index=False)["export_usd"].sum().sort_values("date")
    previous = (agg["date"]-pd.DateOffset(months=12)).map(agg.set_index("date")["export_usd"]).replace(0,np.nan)
    agg["top20_yoy"] = (agg["export_usd"]/previous-1)*100
    agg = agg[agg["date"]>=period_start]
    total_latest = total[total["date"] == total["date"].max()].iloc[-1] if not total.empty else None
    latest_signal = signal[signal["date"] == signal["date"].max()].copy() if not signal.empty else pd.DataFrame()
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("한국 총수출", usd100m(total_latest["total_export_usd"] if total_latest is not None else np.nan), pct(total_latest["total_yoy_pct"] if total_latest is not None else np.nan))
    k2.metric("Top20 합계", usd100m(snap["export_usd"].sum()), pct(agg.iloc[-1]["top20_yoy"] if not agg.empty else np.nan))
    k3.metric("수출 증가 품목", f"{int((snap['yoy_pct']>0).sum())}/20")
    k4.metric("실물·수출 동반개선", f"{int(((latest_signal['export_yoy']>0)&(latest_signal['inventory_cycle']>0)).sum())}/{len(latest_signal)}" if not latest_signal.empty else "KOSIS 필요")

    a=agg.rename(columns={"top20_yoy": "yoy_pct"})
    t=total.rename(columns={"total_export_usd":"export_usd", "total_yoy_pct":"yoy_pct"})
    fig=amount_growth_figure([("총수출",t),("Top20",a)],title="① 한국 총수출 · Top20 금액과 성장률")
    render_chart(fig,source_key="mapping",csv_df=t.merge(a,on="date",how="outer",suffixes=("_total","_top20")),csv_name="overview_amount_growth",key="ov1")

    c3,c4=st.columns(2)
    with c3:
        p=snap.sort_values("yoy_pct"); fig=px.bar(p,y="item20",x="yoy_pct",orientation="h",title=f"③ Top20 최신 YoY · {latest:%Y.%m}",labels={"item20":"","yoy_pct":"YoY (%)"}); fig.add_vline(x=0,line_dash="dash")
        render_chart(fig_layout(fig,420,"YoY (%)",False),source_key="customs_item",csv_df=p,csv_name="overview_top20_yoy",key="ov3")
    with c4:
        p=snap.copy(); p["수출_억달러"]=p["export_usd"]/1e8; p["bubble"]=p["수출_억달러"].clip(lower=.2)
        fig=px.scatter(p,x="수출_억달러",y="yoy_pct",size="bubble",text="item20",title="④ 규모 × 성장",labels={"수출_억달러":"억달러","yoy_pct":"YoY (%)"}); fig.add_hline(y=0,line_dash="dash"); fig.update_traces(textposition="top center")
        render_chart(fig_layout(fig,420,"YoY (%)",False),source_key="customs_item",csv_df=p,csv_name="overview_size_growth",key="ov4")

    with st.container():
        if not kosis.empty:
            ka=kosis.groupby("date",as_index=False)[["production_yoy","shipment_yoy","inventory_yoy"]].mean()
            fig=go.Figure()
            for col,name in [("production_yoy","생산"),("shipment_yoy","출하"),("inventory_yoy","재고")]: fig.add_trace(go.Scatter(x=ka["date"],y=ka[col],name=name))
            fig.add_hline(y=0,line_dash="dash"); fig.update_layout(title="⑤ KOSIS 연결업종 평균")
            render_chart(fig_layout(fig,330,"YoY (%)"),source_key="kosis_cycle",csv_df=ka,csv_name="overview_kosis",key="ov5")
        else: st.info("⑤ KOSIS 캐시가 없습니다.")
    c7,c8=st.columns(2)
    with c7:
        if not latest_signal.empty:
            p=latest_signal.copy(); p["bubble"]=p["export_usd"].clip(lower=1)
            fig=px.scatter(p,x="inventory_cycle",y="export_yoy",size="bubble",color="stage",text="item20",title="⑦ 재고순환 × 수출 YoY",labels={"inventory_cycle":"재고순환 (pp)","export_yoy":"수출 YoY (%)"}); fig.add_hline(y=0,line_dash="dash"); fig.add_vline(x=0,line_dash="dash"); fig.update_traces(textposition="top center")
            render_chart(fig_layout(fig,420,"수출 YoY (%)",True),source_key="customs_kosis",csv_df=p,csv_name="overview_cross_signal",key="ov7")
        else: st.info("⑦ Cross Signal은 KOSIS 연결 후 생성됩니다.")
    with c8:
        if not middle.empty:
            ms=middle[middle["date"]==middle["date"].max()].dropna(subset=["yoy_pct"]).nlargest(15,"yoy_pct").sort_values("yoy_pct")
            fig=px.bar(ms,y="middle_category",x="yoy_pct",orientation="h",title="⑧ 리서치중분류 수출 YoY 상위",labels={"middle_category":"","yoy_pct":"YoY (%)"}); fig.add_vline(x=0,line_dash="dash")
            render_chart(fig_layout(fig,420,"YoY (%)",False),source_key="customs_item",csv_df=ms,csv_name="overview_middle_yoy",key="ov8")


def render_industry_scanner():
    signal=month_sql("mart_industry_signal_monthly",period_start,period_end)
    if signal.empty:
        st.info("KOSIS 연결 산업이 없습니다. Local 모드에서 KOSIS + Mart 최신화를 실행하세요."); return
    latest=signal["date"].max(); snap=industry_period_summary(signal).sort_values("fundamental_score",ascending=False)
    k1,k2,k3,k4=st.columns(4)
    k1.metric("현재점수 1위",f"{snap.iloc[0]['item20']} · {snap.iloc[0]['fundamental_score']:.0f}")
    avg_top=snap.sort_values("period_avg_score",ascending=False).iloc[0]
    k2.metric("기간평균 1위",f"{avg_top['item20']} · {avg_top['period_avg_score']:.0f}")
    k3.metric("수출 증가 산업",f"{int((snap['export_yoy']>0).sum())}/{len(snap)}")
    k4.metric("실물·수출 동반개선",f"{int(((snap['export_yoy']>0)&(snap['inventory_cycle']>0)).sum())}/{len(snap)}")
    st.caption(f"현재점수는 {latest:%Y.%m} 기준, 기간평균·변화는 {period_start:%Y.%m}~{period_end:%Y.%m} 기준입니다. 주가·EPS·수급은 아직 포함하지 않습니다.")
    with st.expander("산업 펀더멘털 점수 산식·해석", expanded=False):
        st.markdown(
            "**수출 모멘텀 30%** (3M 평균 YoY + 3M 가속도) · "
            "**재고순환 25%** (출하 YoY-재고 YoY + 3M 개선폭) · "
            "**실물활동 20%** (출하·생산 3M 평균) · "
            "**확산도 15%** (중분류 중 수출 YoY(+) 비율) · "
            "**지속성 10%** (최근 6개월 수출·재고순환 개선 지속도). "
            "수출 YoY와 재고순환이 동시에 음수면 50점 상한, 확산도 30% 미만은 감점합니다."
        )
    c1,c2=st.columns(2)
    with c1:
        p=snap.sort_values("fundamental_score"); fig=go.Figure(); fig.add_trace(go.Bar(y=p["item20"],x=p["period_avg_score"],name="기간평균",orientation="h")); fig.add_trace(go.Bar(y=p["item20"],x=p["fundamental_score"],name="현재",orientation="h")); fig.update_layout(title=f"산업 펀더멘털 점수 · {latest:%Y.%m}",barmode="group")
        render_chart(fig_layout(fig,450,"점수",True),source_key="customs_kosis",csv_df=p,csv_name="industry_fundamental_score",key="scan1")
    with c2:
        p=snap.copy(); p["bubble"]=p["export_usd"].clip(lower=1); fig=px.scatter(p,x="inventory_cycle",y="export_yoy",size="bubble",color="fundamental_score",text="item20",title="수출 × 재고순환",labels={"inventory_cycle":"재고순환 (pp)","export_yoy":"수출 YoY (%)","fundamental_score":"현재점수"},hover_data=["period_avg_score","period_change_score","breadth_pct","persistence_pct","score_note"]); fig.add_hline(y=0,line_dash="dash"); fig.add_vline(x=0,line_dash="dash"); fig.update_traces(textposition="top center")
        render_chart(fig_layout(fig,450,"수출 YoY (%)",False),source_key="customs_kosis",csv_df=p,csv_name="industry_cross",key="scan2")
    item=st.selectbox("점수 추이 산업",snap["item20"].tolist(),key="scan_item")
    hist=signal[signal["item20"]==item].copy()
    c3,c4=st.columns([1.2,1])
    with c3:
        fig=go.Figure(); fig.add_trace(go.Scatter(x=hist["date"],y=hist["fundamental_score"],name="산업 펀더멘털 점수")); fig.update_layout(title=f"{item} · 점수 추이")
        render_chart(fig_layout(fig,340,"점수",False),source_key="customs_kosis",csv_df=hist,csv_name=f"{item}_score_history",key="scan3")
    with c4:
        table=snap[["item20","fundamental_score","period_avg_score","period_change_score","export_momentum_score","inventory_cycle_score","real_activity_score","breadth_score","persistence_score","export_yoy","inventory_cycle","score_note"]].copy()
        table.columns=["산업","현재점수","기간평균","기간변화","수출모멘텀","재고순환","실물활동","확산도","지속성","수출 YoY","재고순환 pp","판정"]
        st.dataframe(table,hide_index=True,width="stretch",height=335)


def render_industry_detail():
    items=q("SELECT DISTINCT item20 FROM mart_export_top20_monthly ORDER BY item20")["item20"].tolist()
    item=st.selectbox("Top20 산업",items,key="detail_item")
    exp=month_sql("mart_export_top20_monthly",period_start,period_end,"AND item20=?",(item,))
    sig=month_sql("mart_industry_signal_monthly",period_start,period_end,"AND item20=?",(item,))
    middle=month_sql("mart_export_middle_monthly",period_start,period_end,"AND item20=?",(item,))
    product=month_sql("mart_export_product_monthly",period_start,period_end,"AND item20=?",(item,))
    if exp.empty: st.info("선택 기간 데이터 없음"); return
    latest=exp.iloc[-1]
    s_latest=sig.iloc[-1] if not sig.empty else None
    k1,k2,k3,k4=st.columns(4)
    k1.metric("수출",usd100m(latest["export_usd"]),pct(latest["yoy_pct"]))
    k2.metric("MoM",pct(latest["mom_pct"]))
    k3.metric("재고순환",f"{s_latest['inventory_cycle']:+.1f}pp" if s_latest is not None and pd.notna(s_latest["inventory_cycle"]) else "-")
    k4.metric("Fundamental Score",f"{s_latest['fundamental_score']:.0f}" if s_latest is not None and pd.notna(s_latest["fundamental_score"]) else "-")
    c1,c2=st.columns(2)
    with c1:
        p=exp.copy(); p["수출_억달러"]=p["export_usd"]/1e8; fig=px.line(p,x="date",y="수출_억달러",title=f"{item} · 수출액")
        render_chart(fig_layout(fig,350,"억달러",False),source_key="customs_item",csv_df=p,csv_name=f"{item}_export",key="det1")
    with c2:
        fig=go.Figure(); fig.add_trace(go.Scatter(x=exp["date"],y=exp["yoy_pct"],name="수출 YoY"));
        if not sig.empty: fig.add_trace(go.Scatter(x=sig["date"],y=sig["inventory_cycle"],name="재고순환"))
        fig.add_hline(y=0,line_dash="dash"); fig.update_layout(title=f"{item} · 수출 vs 재고순환")
        render_chart(fig_layout(fig,350,"%, pp"),source_key="customs_kosis",csv_df=exp,csv_name=f"{item}_signal",key="det2")
    c3,c4=st.columns(2)
    with c3:
        if not middle.empty:
            m=middle[middle["date"]==middle["date"].max()].dropna(subset=["yoy_pct"]).sort_values("yoy_pct"); fig=px.bar(m,y="middle_category",x="yoy_pct",orientation="h",title="리서치중분류 · 최신 YoY"); fig.add_vline(x=0,line_dash="dash")
            render_chart(fig_layout(fig,430,"YoY (%)",False),source_key="customs_item",csv_df=m,csv_name=f"{item}_middle",key="det3")
    with c4:
        if not product.empty:
            p=product[product["date"]==product["date"].max()].dropna(subset=["yoy_pct"]).nlargest(20,"yoy_pct").sort_values("yoy_pct"); fig=px.bar(p,y="product",x="yoy_pct",orientation="h",title="대표품목 · 최신 YoY"); fig.add_vline(x=0,line_dash="dash")
            render_chart(fig_layout(fig,430,"YoY (%)",False),source_key="customs_item",csv_df=p,csv_name=f"{item}_products",key="det4")


def _leaders_source(level: str, top20: str | None, middle: str | None, comparison_end: pd.Timestamp) -> tuple[pd.DataFrame,str,str]:
    if level=="Top20":
        return month_sql("mart_export_top20_monthly",available_start,comparison_end),"item20","Top20"
    if level=="리서치중분류":
        return month_sql("mart_export_middle_monthly",available_start,comparison_end,"AND item20=?",(top20,)),"middle_category","리서치중분류"
    return month_sql("mart_export_product_monthly",available_start,comparison_end,"AND item20=? AND middle_category=?",(top20,middle)),"product","대표품목"


def render_growth_leaders():
    st.session_state.setdefault("gl_top20",None); st.session_state.setdefault("gl_middle",None)
    mode_col,base_col=st.columns([1.7,1])
    years = available_growth_years(available_start, available_end)
    if not years:
        st.warning("전년과 비교할 수 있는 연도 데이터가 없습니다.")
        return
    selected_year=mode_col.selectbox("기준 연도",years,index=0,format_func=lambda y:f"{y}년")
    min_base=base_col.number_input("최소 비교규모 (억달러)",min_value=0.0,value=1.0,step=1.0)
    top20=st.session_state.gl_top20; middle=st.session_state.gl_middle
    if not top20: level="Top20"
    elif not middle: level="리서치중분류"
    else: level="대표품목"
    b1,b2,b3=st.columns([1,1.4,5])
    if top20 and b1.button("← Top20",width="stretch"):
        st.session_state.gl_top20=None; st.session_state.gl_middle=None; st.rerun()
    if top20 and middle and b2.button(f"← {top20}",width="stretch"):
        st.session_state.gl_middle=None; st.rerun()
    crumb="Top20"+(f" → {top20}" if top20 else "")+(f" → {middle}" if middle else "")
    b3.markdown(f"**Top20 → 리서치중분류 → 대표품목** &nbsp; | &nbsp; 현재: {crumb}")
    comparison_start, comparison_end, previous_start, previous_end = growth_year_comparison_range(selected_year, available_end)
    source,entity,label=_leaders_source(level,top20,middle,comparison_end)
    comparison_label = "누계" if comparison_end.month < 12 else "연간"
    st.caption(f"현재 비교: {selected_year}년 {comparison_label}({comparison_start:%Y.%m}–{comparison_end:%Y.%m}) vs {selected_year-1}년 같은 기간({previous_start:%Y.%m}–{previous_end:%Y.%m})")
    leaders=growth_leaders(source,entity,comparison_start,comparison_end,min_base_usd=min_base*1e8,mode="previous_period")
    if leaders.empty: st.warning("조건을 만족하는 항목이 없습니다."); return
    show=leaders.copy(); show["기간수출_억달러"]=show["period_export_usd"]/1e8; show["증가액_억달러"]=show["absolute_increase_usd"]/1e8
    k1,k2,k3,k4=st.columns(4); k1.metric("성장률 1위",f"{show.iloc[0]['entity']} · {show.iloc[0]['growth_pct']:+.1f}%"); inc=show.sort_values("absolute_increase_usd",ascending=False).iloc[0]; k2.metric("증가액 1위",f"{inc['entity']} · {inc['증가액_억달러']:+.1f}억달러"); con=show.sort_values("contribution_pct",ascending=False).iloc[0]; k3.metric("기여도 1위",f"{con['entity']} · {con['contribution_pct']:+.1f}%"); k4.metric("성장 항목",f"{int((show['growth_pct']>0).sum())}/{len(show)}")
    c1,c2=st.columns(2)
    with c1:
        rank=show.nlargest(15,"growth_pct").sort_values("growth_pct"); fig=px.bar(rank,y="entity",x="growth_pct",orientation="h",title=f"{label} · 성장률 상위"); event1=render_chart(fig_layout(fig,410,"%",False),source_key="customs_item",csv_df=rank,csv_name=f"growth_{label}",key=f"gl1_{level}_{top20}_{middle}",selectable=level!="대표품목")
    with c2:
        rank2=show.nlargest(15,"absolute_increase_usd").sort_values("증가액_억달러"); fig=px.bar(rank2,y="entity",x="증가액_억달러",orientation="h",title=f"{label} · 절대 증가액"); event2=render_chart(fig_layout(fig,410,"억달러",False),source_key="customs_item",csv_df=rank2,csv_name=f"growth_inc_{label}",key=f"gl2_{level}_{top20}_{middle}",selectable=level!="대표품목")
    if level!="대표품목":
        clicked=selected_point_label(event1) or selected_point_label(event2)
        valid=set(show["entity"].astype(str))
        if clicked in valid:
            if level=="Top20" and clicked!=top20:
                st.session_state.gl_top20=clicked; st.session_state.gl_middle=None; st.rerun()
            if level=="리서치중분류" and clicked!=middle:
                st.session_state.gl_middle=clicked; st.rerun()
    c3,c4=st.columns([1.15,1])
    with c3:
        bubble=show.head(40).copy(); bubble["bubble"]=bubble["absolute_increase_usd"].abs().clip(lower=1); fig=px.scatter(bubble,x="기간수출_억달러",y="growth_pct",size="bubble",text="entity",title=f"{label} · 규모 × 성장률"); fig.add_hline(y=0,line_dash="dash"); fig.update_traces(textposition="top center")
        render_chart(fig_layout(fig,390,"%",False),source_key="customs_item",csv_df=bubble,csv_name=f"growth_bubble_{label}",key=f"gl3_{level}_{top20}_{middle}")
    with c4:
        table=show[["entity","growth_pct","증가액_억달러","contribution_pct","기간수출_억달러","avg_yoy_pct","latest_yoy_pct"]].head(25)
        st.dataframe(table,hide_index=True,width="stretch",height=365)


def monthly_growth(frame):
    frame=frame.sort_values('date').drop_duplicates('date',keep='last').copy()
    values=frame.set_index('date')['export_usd']
    for months, name in [(12,'yoy_pct'),(1,'mom_pct')]:
        prev=(frame.date-pd.DateOffset(months=months)).map(values).replace(0,np.nan)
        frame[name]=(frame.export_usd/prev-1)*100
    frame['unit_price_usd_per_kg']=frame.export_usd/frame.export_weight.replace(0,np.nan)
    return frame


def render_product_monitor():
    dims=q("SELECT DISTINCT item20,middle_category,product FROM dim_product_taxonomy ORDER BY item20,middle_category,product")
    if dims.empty: st.info("Taxonomy 없음"); return

    def reset_from_item():
        st.session_state['pm_mid']=ALL_OPTION
        st.session_state['pm_prod']=ALL_OPTION
        st.session_state['pm_geo']='전세계(전체)'

    def reset_from_middle():
        st.session_state['pm_prod']=ALL_OPTION
        st.session_state['pm_geo']='전세계(전체)'

    c1,c2,c3=st.columns(3)
    item=c1.selectbox('Top20',dims.item20.drop_duplicates().tolist(),key='pm_item',on_change=reset_from_item)
    mids,_=drilldown_options(dims,item,ALL_OPTION)
    if st.session_state.get('pm_mid') not in mids: st.session_state['pm_mid']=ALL_OPTION
    mid=c2.selectbox('리서치중분류',mids,key='pm_mid',on_change=reset_from_middle)
    _,prods=drilldown_options(dims,item,mid)
    if st.session_state.get('pm_prod') not in prods: st.session_state['pm_prod']=ALL_OPTION
    product=c3.selectbox('대표품목',prods,key='pm_prod')
    table,extra,params,label=product_monitor_selection(item,mid,product)
    full_hist=month_sql(table,period_start-pd.DateOffset(months=12),period_end,extra,params)
    hist=full_hist[full_hist.date>=period_start].copy() if not full_hist.empty else full_hist
    if hist.empty: st.info('선택 기간 데이터 없음'); return

    country_where=['date>=?','date<=?','item20=?']
    country_params=[(period_start-pd.DateOffset(months=12)).strftime('%Y-%m-%d'),period_end.strftime('%Y-%m-%d'),item]
    if mid!=ALL_OPTION: country_where.append('middle_category=?');country_params.append(mid)
    if product!=ALL_OPTION: country_where.append('product=?');country_params.append(product)
    country=q(f"""SELECT date,country_code,SUM(export_usd) AS export_usd,SUM(export_weight) AS export_weight
                  FROM mart_product_country_monthly WHERE {' AND '.join(country_where)}
                  GROUP BY date,country_code ORDER BY date,country_code""",tuple(country_params))
    country_names={'CN':'중국','US':'미국','VN':'베트남','JP':'일본','HK':'홍콩','TW':'대만','SG':'싱가포르','IN':'인도','MY':'말레이시아','DE':'독일','NL':'네덜란드','GB':'영국','FR':'프랑스','PL':'폴란드','MX':'멕시코','ID':'인도네시아','TH':'태국','CA':'캐나다','AU':'호주','IT':'이탈리아','ES':'스페인'}
    codes=country.country_code.drop_duplicates().tolist() if not country.empty else []
    options=['전세계(전체)']+codes
    if st.session_state.get('pm_geo') not in options: st.session_state['pm_geo']='전세계(전체)'
    r1,r2,r3=st.columns(3)
    geo=r1.selectbox('국가',options,key='pm_geo',format_func=lambda x:country_names.get(x,x))
    mode=r2.selectbox('수출금액 구성',['상위 5개국 + Others','전체 합계'],key='pm_composition',disabled=geo!='전세계(전체)')
    growth=r3.selectbox('성장률',['YoY','MoM'],key='pm_growth')
    if geo!='전세계(전체)':
        selected=monthly_growth(country[country.country_code==geo])
        selected=selected[selected.date>=period_start]
        title=f'{label} · {country_names.get(geo,geo)}'
    else:
        selected=hist.copy();title=f'{label} · 전세계'
    if selected.empty: st.info('선택 국가·기간 데이터 없음');return
    latest=selected.iloc[-1]
    k1,k2,k3,k4=st.columns(4)
    k1.metric('수출금액',usd100m(latest.export_usd),pct(latest.yoy_pct))
    k2.metric('MoM',pct(latest.mom_pct))
    k3.metric('중량',f'{latest.export_weight/1e6:,.2f}M kg' if pd.notna(latest.export_weight) else '-')
    k4.metric('수출단가',f'${latest.unit_price_usd_per_kg:,.2f}/kg' if pd.notna(latest.unit_price_usd_per_kg) else '-')
    composition=None
    if geo=='전세계(전체)' and mode=='상위 5개국 + Others':
        observed=country[country.date>=period_start]
        if not observed.empty:
            try:
                candidate=country_composition(hist,observed,5)
                # A country query has a bounded history; retain world totals outside it.
                complete=candidate.dropna()
                if not complete.empty:
                    composition=candidate.copy()
                    composition=composition.rename(columns=country_names)
                    incomplete=composition.drop(columns='date').isna().any(axis=1)
                    if incomplete.any():
                        composition['세계 합계(국가 자료 미수집)']=np.where(incomplete,hist.set_index('date').export_usd.reindex(composition.date).to_numpy(),np.nan)
                    st.caption(f'추적국 {observed.country_code.nunique()}개 중 기간 합계 상위 최대 5개국 · 국가별 자료: {complete.date.min():%Y.%m}–{complete.date.max():%Y.%m}. Others에는 추적되지 않은 국가도 포함됩니다.')
            except ValueError as exc: st.warning(str(exc))
        if composition is None: st.info('국가별 구성 자료가 없어 전세계 합계로 표시합니다.')
    fig=amount_growth_figure([(country_names.get(geo,'전체'),selected)],title=title+' · 수출금액과 성장률',growth='yoy_pct' if growth=='YoY' else 'mom_pct',composition=composition)
    render_chart(fig,source_key='customs_item_country' if geo!='전세계(전체)' or composition is not None else 'customs_item',csv_df=selected if composition is None else composition.merge(selected[['date','yoy_pct','mom_pct']],on='date'),csv_name=f'{label}_{geo}_amount_growth',key='pm1')
    c4,c5=st.columns(2)
    with c4:
        fig=px.line(selected,x='date',y='unit_price_usd_per_kg',title=title+' · 중량 기준 수출단가',labels={'unit_price_usd_per_kg':'USD/kg'},markers=True)
        render_chart(fig_layout(fig,350,'USD/kg',False),source_key='customs_item' if geo=='전세계(전체)' else 'customs_item_country',csv_df=selected[['date','export_usd','export_weight','unit_price_usd_per_kg']],csv_name=f'{label}_{geo}_unitprice',key='pm2')
    with c5:
        p=selected.assign(weight_m_kg=selected.export_weight/1e6)
        fig=px.bar(p,x='date',y='weight_m_kg',title=title+' · 수출중량')
        render_chart(fig_layout(fig,350,'백만 kg',False),source_key='customs_item' if geo=='전세계(전체)' else 'customs_item_country',csv_df=p[['date','export_weight']],csv_name=f'{label}_{geo}_weight',key='pm3')
    st.caption('단가 = 동일 기간 수출금액 ÷ 순중량. 중량이 없거나 0이면 단가는 표시하지 않습니다.')
    with st.expander('관련 산업 잠정치',expanded=True):
        link=TOP20_LINKS.get(item)
        snapshots=load_snapshots(PROVISIONAL_CACHE)
        if link and not snapshots.empty:
            rows=snapshots[(snapshots.dimension=='product')&(snapshots.category==link[0])].sort_values(['date','checkpoint_day'])
            if not rows.empty:
                recent=rows.iloc[-1]
                series=checkpoint_history(snapshots,'product',recent.checkpoint,link[0])
                last=series.iloc[-1]
                st.write(f'{link[0]} 전체 · {last.date:%Y.%m} 1~{int(last.checkpoint_day)}일 · {usd100m(last.export_usd)} · YoY {pct(last.yoy_pct)}')
                st.caption(f'{link[1]}. 기존 Top20과 집계 범위가 다를 수 있습니다. 세부 품목·중량·단가 잠정치는 제공되지 않습니다.')
        elif not link: st.caption('선택 산업에 직접 연결할 주요품목 잠정치가 없습니다.')
        else: st.caption('잠정치 API 수집 후 표시됩니다. 최근 수출에서 갱신 상태를 확인하세요.')
    with st.expander('HS10 lineage',expanded=False):
        where='item20=?';lin_params=[item]
        if mid!=ALL_OPTION:where+=' AND middle_category=?';lin_params.append(mid)
        if product!=ALL_OPTION:where+=' AND product=?';lin_params.append(product)
        lin=q(f'SELECT hsk10,display_name,hs6,mti6,classification_status,classification_note FROM dim_product_taxonomy WHERE {where} ORDER BY hsk10',tuple(lin_params))
        st.dataframe(lin,hide_index=True,width='stretch')
        st.caption('HS가 제품을 완전히 분리하지 못하는 경우 국가·중량·단가를 함께 보며 Proxy로 해석합니다.')


def render_stock_candidates():
    st.markdown("### Stock Candidates · 제품 ↔ 상장사 Exposure")
    st.caption("QuantiWise 연결 전 단계입니다. 제품-기업 노출도를 사람이 검증한 CSV로 관리하고, EPS/Revision/수급은 다음 Phase에서 붙입니다.")
    path = DATA_DIR / "company_exposure.csv"
    if not path.exists():
        st.info("data/company_exposure.csv가 없습니다. company_exposure_template.csv를 복사해 채우면 즉시 표시됩니다.")
        return
    exposure = pd.read_csv(path, dtype=str).fillna("")
    if exposure.empty:
        st.info("회사 Exposure map이 아직 비어 있습니다. CCL/초고압변압기/톡신·필러처럼 검증한 품목부터 company_exposure.csv에 추가하면 됩니다.")
        st.dataframe(exposure, hide_index=True, width="stretch")
        return
    dims=q("SELECT DISTINCT item20,middle_category,product,representative_id FROM dim_product_taxonomy ORDER BY item20,middle_category,product")
    c1,c2,c3=st.columns(3)
    item=c1.selectbox("Top20",dims["item20"].drop_duplicates().tolist(),key="sc_item")
    mids=dims[dims["item20"]==item]["middle_category"].drop_duplicates().tolist(); mid=c2.selectbox("리서치중분류",mids,key="sc_mid")
    prods=dims[(dims["item20"]==item)&(dims["middle_category"]==mid)]["product"].drop_duplicates().tolist(); product=c3.selectbox("대표품목",prods,key="sc_prod")
    ids=set(dims[(dims["item20"]==item)&(dims["middle_category"]==mid)&(dims["product"]==product)]["representative_id"].astype(str))
    view=exposure[(exposure["representative_id"].astype(str).isin(ids)) | (exposure["product"].astype(str)==str(product))].copy()
    if view.empty:
        st.warning("이 제품은 아직 기업 Exposure mapping이 없습니다.")
    else:
        st.dataframe(view,hide_index=True,width="stretch")
        _,dl=st.columns([12,1])
        with dl:
            st.download_button("CSV",view.to_csv(index=False).encode("utf-8-sig"),file_name=f"stock_candidates_{product}.csv",mime="text/csv",width="content")
    st.caption("Exposure type/confidence/source를 반드시 남겨서 HS Proxy와 실제 기업 매출 노출을 구분합니다.")

def render_export_flash():
    snapshots=load_snapshots(PROVISIONAL_CACHE)
    if snapshots.empty:
        st.info('주요품목·국가 잠정치 수집 결과가 아직 없습니다. 기존 총수출 공표자료를 표시합니다.')
        legacy=load_flash_snapshots(FLASH_SEED,FLASH_CACHE)
        if not legacy.empty:
            st.dataframe(legacy.sort_values(['month','checkpoint_day'],ascending=False),hide_index=True,width='stretch')
    status_path=DATA_DIR/'provisional_status.json'
    if status_path.exists():
        result=json.loads(status_path.read_text(encoding='utf-8'))
        for dimension,name in [('product','품목'),('country','국가')]:
            if not result.get(dimension,{}).get('ok'):
                st.warning(f'{name} 잠정치 갱신: {result.get(dimension,{}).get("error","미확인")} · 기존 수집 자료 유지')
        st.caption(f'잠정치 조회 시각: {result.get("fetched_at","-")}')
    products=snapshots[snapshots.dimension=='product']
    if products.empty:return
    newest=products.sort_values(['date','checkpoint_day']).iloc[-1]
    checkpoint_labels={'10':'1~10일','20':'1~20일','month_end':'월말 잠정'}
    checkpoints=[c for c in ['10','20','month_end'] if c in products.checkpoint.unique()]
    c1,c2,c3=st.columns(3)
    checkpoint=c1.selectbox('집계 기간',checkpoints,index=checkpoints.index(newest.checkpoint),format_func=lambda x:checkpoint_labels[x],key='prov_checkpoint')
    window=c2.selectbox('표시 기간',['3Y','5Y','전체'],key='prov_window')
    growth=c3.selectbox('성장률',['YoY','MoM'],key='prov_growth')
    dates=products[products.checkpoint==checkpoint].date
    end=dates.max()
    start=dates.min() if window=='전체' else max(dates.min(),end-pd.DateOffset(months=(36 if window=='3Y' else 60)-1))
    combined=pd.concat([snapshots,major_product_total(snapshots)],ignore_index=True)
    def series(dimension,category):
        frame=checkpoint_history(combined,dimension,checkpoint,category)
        return frame[(frame.date>=start)&(frame.date<=end)]
    total=series('product','전체')
    major=series('product','주요 10개 품목 합계')
    latest=total.iloc[-1]
    st.caption(f'{start:%Y.%m}–{end:%Y.%m} · 매월 {checkpoint_labels[checkpoint].replace("~", "–")}끼리 비교 · 최신 집계 {latest.date:%Y.%m} 1–{int(latest.checkpoint_day)}일')
    k1,k2,k3,k4=st.columns(4)
    k1.metric('전체 수출',usd100m(latest.export_usd),pct(latest.yoy_pct))
    k2.metric('전체 MoM',pct(latest.mom_pct))
    if not major.empty and major.iloc[-1].date==latest.date:
        k3.metric('주요 10개 품목 합계',usd100m(major.iloc[-1].export_usd),pct(major.iloc[-1].yoy_pct))
        k4.metric('주요품목 MoM',pct(major.iloc[-1].mom_pct))
    else:
        k3.metric('주요 10개 품목 합계','자료 불충분')
        k4.metric('집계 상태','잠정')
    frames={name:series('product',name) for name in PRODUCTS[1:]}
    fig=provisional_summary_figure(total,major,frames,growth='yoy_pct' if growth=='YoY' else 'mom_pct')
    download=pd.concat([total,major]+list(frames.values()),ignore_index=True)
    render_chart(fig,source_key='provisional_product',csv_df=download,csv_name='provisional_total_major_products',key='prov_summary')
    st.caption('주요품목 누적 막대는 API 제공 10개 품목의 합계입니다. 전체 수출의 부분집합이므로 전체 금액에 더하지 않습니다. 기존 Top20 합계와 분류가 다릅니다.')
    st.subheader('품목별 잠정 수출')
    for i in range(0,10,2):
        cols=st.columns(2)
        for j,col in enumerate(cols):
            name=PRODUCTS[1+i+j];frame=frames[name]
            with col:
                st.markdown(f'### {name}')
                if frame.empty:st.info('선택 기준 자료 없음');continue
                last=frame.iloc[-1]
                st.caption(f'{last.date:%Y.%m} · {usd100m(last.export_usd)} · YoY {pct(last.yoy_pct)} · MoM {pct(last.mom_pct)}')
                fig=amount_growth_figure([(name,frame)],title=f'{name} · {checkpoint_labels[checkpoint]}',growth='yoy_pct' if growth=='YoY' else 'mom_pct')
                render_chart(fig,source_key='provisional_product',csv_df=frame,csv_name=f'provisional_product_{i+j}',key=f'prov_product_{i+j}')
    st.subheader('국가·지역별 잠정 수출')
    st.caption('한국 전체 수출의 목적지별 통계입니다. 반도체 등 품목별 국가 실적으로 연결할 수 없습니다. 유럽연합은 지역 합계입니다.')
    country_total=series('country','전체')
    if country_total.empty:
        st.info('국가 API 자료가 아직 수집되지 않았습니다. 위의 품목 잠정치는 정상 표시됩니다.')
    else:
        parts=snapshots[(snapshots.dimension=='country')&(snapshots.checkpoint==checkpoint)&(snapshots.category!='전체')&(snapshots.date>=start)&(snapshots.date<=end)].rename(columns={'category':'country_code'})
        try:
            composition=country_composition(country_total,parts,5)
            fig=amount_growth_figure([('전체',country_total)],title='주요 5개 국가·지역 + Others / 전체 성장률',growth='yoy_pct' if growth=='YoY' else 'mom_pct',composition=composition)
            render_chart(fig,source_key='provisional_country',csv_df=composition,csv_name='provisional_country_composition',key='prov_countries')
        except ValueError as exc:st.warning(str(exc))
        category=st.selectbox('국가·지역 상세',COUNTRIES[1:],key='prov_country')
        frame=series('country',category)
        if not frame.empty:
            fig=amount_growth_figure([(category,frame)],title=f'{category} · {checkpoint_labels[checkpoint]}',growth='yoy_pct' if growth=='YoY' else 'mom_pct')
            render_chart(fig,source_key='provisional_country',csv_df=frame,csv_name='provisional_country_detail',key='prov_country_detail')
    with st.expander('Top20 연결과 데이터 범위'):
        st.dataframe(pd.DataFrame([{'Top20':name,'잠정치 연결':link[0],'범위':link[1]} for name,link in TOP20_LINKS.items()]),hide_index=True,width='stretch')
        st.caption('직접 대응하지 않는 정밀기기는 최근 수출에서 별도 표시합니다. 승용차·컴퓨터주변기기는 관련 산업의 일부입니다. 품목별 중량·단가 및 품목×국가 잠정치는 제공되지 않습니다.')
    with st.expander('원자료·조회 이력'):
        st.dataframe(download.sort_values(['date','checkpoint_day','category'],ascending=[False,False,True]),hide_index=True,width='stretch')
        history_path=PROVISIONAL_CACHE.with_name(PROVISIONAL_CACHE.stem+'_history.csv')
        if history_path.exists():
            st.download_button('잠정치 수정 이력 CSV',history_path.read_bytes(),file_name='export_provisional_history.csv',mime='text/csv',key='prov_history_download')


def render_data_qc():
    s=mart_status(resolve_mart_path()); tax=q("SELECT * FROM dim_product_taxonomy"); total=month_sql("mart_export_total_monthly",period_start,period_end)
    k1,k2,k3,k4=st.columns(4); k1.metric("HS10 taxonomy",f"{tax['hsk10'].nunique():,}" if not tax.empty else "-"); k2.metric("리서치중분류",f"{tax['middle_category'].nunique():,}" if not tax.empty else "-"); k3.metric("대표품목",f"{tax['product'].nunique():,}" if not tax.empty else "-"); k4.metric("Mart Top20 rows",f"{s.get('rows',0):,}")
    c1,c2=st.columns(2)
    with c1:
        if not total.empty:
            fig=px.line(total,x="date",y="mapped_value_pct",title="2026 고정 taxonomy Value Coverage"); render_chart(fig_layout(fig,350,"%",False),source_key="mapping",csv_df=total,csv_name="mapping_coverage",key="qc1")
    with c2:
        meta=q("SELECT * FROM mart_metadata ORDER BY key"); st.dataframe(meta,hide_index=True,width="stretch",height=335)
    with st.expander("Taxonomy 샘플",expanded=False): st.dataframe(tax.head(200),hide_index=True,width="stretch")
    with st.expander("공유/배포 안내",expanded=False):
        st.markdown("`MAKE_PORTABLE.command`(Mac) 또는 `MAKE_PORTABLE.bat`(Windows)를 실행하면 raw DB와 API 키를 제외한 compact snapshot ZIP이 생성됩니다. 이 PORTABLE ZIP은 다른 PC에서 바로 열거나 private GitHub/Streamlit Cloud 배포용으로 사용할 수 있습니다.")


if page=="종합 현황": render_overview()
elif page=="산업 상세": render_industry_detail()
elif page=="수출 성장": render_growth_leaders()
elif page=="품목 모니터": render_product_monitor()
elif page=="최근 수출": render_export_flash()
elif page=="데이터 점검": render_data_qc()

st.caption("Sources: KOSIS 광업제조업동향 · 관세청 수출입 OpenAPI · KITA HSK-MTI · 산업부 20대 품목 · 2026 fixed research taxonomy")
