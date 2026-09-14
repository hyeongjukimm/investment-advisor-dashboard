from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import urllib3

from customs_pipeline import CustomsClient, refresh_customs_data
from dashboard_utils import normalize_month_range, quick_month_range, format_100m_usd, industry_period_summary, sidebar_guide_sections
from data_lineage import page_methodology, source_caption
from deployment_mode import allow_admin_controls, is_shared_mode
from export_analytics import growth_leaders
from flash_trade import flash_comparison_frame, load_flash_snapshots, refresh_flash_cache
from kosis_cache import read_kosis_cache, write_kosis_cache
from kosis_client import fetch_kosis_history_payload
from mart_builder import build_analysis_mart, mart_status

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

PAGES = ["종합 현황", "산업 스크리너", "산업 상세", "수출 성장", "품목 모니터", "종목 후보", "최근 수출", "데이터 점검"]
page = st.radio("페이지", PAGES, horizontal=True, label_visibility="collapsed", key="page")

available_start, available_end = mart_bounds()
if "period_start_input" not in st.session_state or "period_end_input" not in st.session_state:
    a, b = quick_month_range(available_end, "5Y", available_start)
    st.session_state.period_start_input = a.date(); st.session_state.period_end_input = b.date()

with st.container(border=True):
    r1, r2, r3, r4 = st.columns([1.0, 1.2, 1.2, 1.1])
    quick = r1.selectbox("빠른 기간", ["직접", "1Y", "3Y", "5Y", "10Y", "전체"], key="quick_range")
    last = st.session_state.get("_quick_last")
    if quick != "직접" and quick != last:
        a, b = quick_month_range(available_end, quick, available_start)
        st.session_state.period_start_input = a.date(); st.session_state.period_end_input = b.date()
    st.session_state["_quick_last"] = quick
    start_date = r2.date_input("기간 시작", key="period_start_input", min_value=available_start.date(), max_value=available_end.date())
    end_date = r3.date_input("기간 종료", key="period_end_input", min_value=available_start.date(), max_value=available_end.date())
    period_start, period_end = normalize_month_range(start_date, end_date)
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
    agg = top20.groupby("date", as_index=False)["export_usd"].sum().sort_values("date")
    agg["top20_yoy"] = agg["export_usd"].pct_change(12, fill_method=None) * 100
    total_latest = total[total["date"] == total["date"].max()].iloc[-1] if not total.empty else None
    latest_signal = signal[signal["date"] == signal["date"].max()].copy() if not signal.empty else pd.DataFrame()
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("한국 총수출", usd100m(total_latest["total_export_usd"] if total_latest is not None else np.nan), pct(total_latest["total_yoy_pct"] if total_latest is not None else np.nan))
    k2.metric("Top20 합계", usd100m(snap["export_usd"].sum()), pct(agg.iloc[-1]["top20_yoy"] if not agg.empty else np.nan))
    k3.metric("수출 증가 품목", f"{int((snap['yoy_pct']>0).sum())}/20")
    k4.metric("실물·수출 동반개선", f"{int(((latest_signal['export_yoy']>0)&(latest_signal['inventory_cycle']>0)).sum())}/{len(latest_signal)}" if not latest_signal.empty else "KOSIS 필요")

    c1,c2=st.columns(2)
    with c1:
        a=agg.copy(); a["Top20_억달러"]=a["export_usd"]/1e8
        fig=go.Figure(); fig.add_trace(go.Scatter(x=a["date"],y=a["Top20_억달러"],name="Top20"))
        if not total.empty: fig.add_trace(go.Scatter(x=total["date"],y=total["total_export_usd"]/1e8,name="총수출"))
        fig.update_layout(title="① 한국 총수출 vs Top20")
        render_chart(fig_layout(fig,330,"억달러"),source_key="mapping",csv_df=a,csv_name="overview_total_vs_top20",key="ov1")
    with c2:
        fig=go.Figure(); fig.add_trace(go.Scatter(x=agg["date"],y=agg["top20_yoy"],name="Top20 YoY"))
        if not total.empty: fig.add_trace(go.Scatter(x=total["date"],y=total["total_yoy_pct"],name="총수출 YoY"))
        fig.add_hline(y=0,line_dash="dash"); fig.update_layout(title="② 수출 모멘텀")
        render_chart(fig_layout(fig,330,"YoY (%)"),source_key="customs_item",csv_df=agg,csv_name="overview_export_yoy",key="ov2")

    c3,c4=st.columns(2)
    with c3:
        p=snap.sort_values("yoy_pct"); fig=px.bar(p,y="item20",x="yoy_pct",orientation="h",title=f"③ Top20 최신 YoY · {latest:%Y.%m}",labels={"item20":"","yoy_pct":"YoY (%)"}); fig.add_vline(x=0,line_dash="dash")
        render_chart(fig_layout(fig,420,"YoY (%)",False),source_key="customs_item",csv_df=p,csv_name="overview_top20_yoy",key="ov3")
    with c4:
        p=snap.copy(); p["수출_억달러"]=p["export_usd"]/1e8; p["bubble"]=p["수출_억달러"].clip(lower=.2)
        fig=px.scatter(p,x="수출_억달러",y="yoy_pct",size="bubble",text="item20",title="④ 규모 × 성장",labels={"수출_억달러":"억달러","yoy_pct":"YoY (%)"}); fig.add_hline(y=0,line_dash="dash"); fig.update_traces(textposition="top center")
        render_chart(fig_layout(fig,420,"YoY (%)",False),source_key="customs_item",csv_df=p,csv_name="overview_size_growth",key="ov4")

    c5,c6=st.columns(2)
    with c5:
        if not kosis.empty:
            ka=kosis.groupby("date",as_index=False)[["production_yoy","shipment_yoy","inventory_yoy"]].mean()
            fig=go.Figure()
            for col,name in [("production_yoy","생산"),("shipment_yoy","출하"),("inventory_yoy","재고")]: fig.add_trace(go.Scatter(x=ka["date"],y=ka[col],name=name))
            fig.add_hline(y=0,line_dash="dash"); fig.update_layout(title="⑤ KOSIS 연결업종 평균")
            render_chart(fig_layout(fig,330,"YoY (%)"),source_key="kosis_cycle",csv_df=ka,csv_name="overview_kosis",key="ov5")
        else: st.info("⑤ KOSIS 캐시가 없습니다.")
    with c6:
        if not latest_signal.empty:
            p=latest_signal.sort_values("fundamental_score"); fig=px.bar(p,y="item20",x="fundamental_score",orientation="h",title="⑥ Fundamental Score",labels={"item20":"","fundamental_score":"Score"},hover_data=["export_momentum_score","inventory_cycle_score","real_activity_score","breadth_score","persistence_score","score_note"])
            render_chart(fig_layout(fig,420,"Score",False),source_key="customs_kosis",csv_df=p,csv_name="overview_fundamental_score",key="ov6")
        else: st.info("⑥ Fundamental Score는 KOSIS 연결 후 생성됩니다.")

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


def _leaders_source(level: str, top20: str | None, middle: str | None) -> tuple[pd.DataFrame,str,str]:
    if level=="Top20":
        return month_sql("mart_export_top20_monthly",available_start,period_end),"item20","Top20"
    if level=="리서치중분류":
        return month_sql("mart_export_middle_monthly",available_start,period_end,"AND item20=?",(top20,)),"middle_category","리서치중분류"
    return month_sql("mart_export_product_monthly",available_start,period_end,"AND item20=? AND middle_category=?",(top20,middle)),"product","대표품목"


def render_growth_leaders():
    st.session_state.setdefault("gl_top20",None); st.session_state.setdefault("gl_middle",None)
    mode_col,base_col=st.columns([1.7,1])
    mode=mode_col.radio("성장 기준",["구간 초→말 3M","선택기간 합계 vs 직전 동일기간"],horizontal=True)
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
    source,entity,label=_leaders_source(level,top20,middle)
    leaders=growth_leaders(source,entity,period_start,period_end,min_base_usd=min_base*1e8,mode="endpoint" if mode.startswith("구간") else "previous_period")
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


def render_product_monitor():
    dims=q("SELECT DISTINCT item20,middle_category,product FROM dim_product_taxonomy ORDER BY item20,middle_category,product")
    if dims.empty: st.info("Taxonomy 없음"); return
    c1,c2,c3=st.columns(3)
    item=c1.selectbox("Top20",dims["item20"].drop_duplicates().tolist(),key="pm_item")
    mids=dims[dims["item20"]==item]["middle_category"].drop_duplicates().tolist(); mid=c2.selectbox("리서치중분류",mids,key="pm_mid")
    prods=dims[(dims["item20"]==item)&(dims["middle_category"]==mid)]["product"].drop_duplicates().tolist(); product=c3.selectbox("대표품목",prods,key="pm_prod")
    hist=month_sql("mart_export_product_monthly",period_start,period_end,"AND item20=? AND middle_category=? AND product=?",(item,mid,product))
    if hist.empty: st.info("선택 기간 제품 데이터 없음"); return
    latest=hist.iloc[-1]; k1,k2,k3,k4=st.columns(4); k1.metric("수출",usd100m(latest["export_usd"]),pct(latest["yoy_pct"])); k2.metric("MoM",pct(latest["mom_pct"])); k3.metric("중량",f"{latest['export_weight']/1e6:.1f}M" if pd.notna(latest['export_weight']) else "-"); k4.metric("수출단가",f"${latest['unit_price_usd_per_kg']:,.1f}/kg" if pd.notna(latest['unit_price_usd_per_kg']) else "-")
    c4,c5=st.columns(2)
    with c4:
        p=hist.copy(); p["수출_억달러"]=p["export_usd"]/1e8; fig=px.line(p,x="date",y="수출_억달러",title=f"{product} · 수출액")
        render_chart(fig_layout(fig,350,"억달러",False),source_key="customs_item",csv_df=p,csv_name=f"{product}_export",key="pm1")
    with c5:
        fig=go.Figure(); fig.add_trace(go.Scatter(x=hist["date"],y=hist["yoy_pct"],name="YoY")); fig.add_trace(go.Scatter(x=hist["date"],y=hist["mom_pct"],name="MoM")); fig.add_hline(y=0,line_dash="dash"); fig.update_layout(title=f"{product} · 성장률")
        render_chart(fig_layout(fig,350,"%"),source_key="customs_item",csv_df=hist,csv_name=f"{product}_growth",key="pm2")
    country=month_sql("mart_product_country_monthly",period_start,period_end,"AND item20=? AND middle_category=? AND product=?",(item,mid,product))
    c6,c7=st.columns(2)
    with c6:
        if not country.empty:
            last=country[country["date"]==country["date"].max()].copy(); last["수출_억달러"]=last["export_usd"]/1e8; last=last.sort_values("수출_억달러")
            fig=px.bar(last,y="country_code",x="수출_억달러",orientation="h",title="추적국가별 수출 · 최신월")
            render_chart(fig_layout(fig,350,"억달러",False),source_key="customs_item_country",csv_df=last,csv_name=f"{product}_country",key="pm3")
        else: st.info("현재 DB에 이 대표품목의 국가별 데이터가 없습니다.")
    with c7:
        if not country.empty:
            countries=country["country_code"].drop_duplicates().tolist(); cc=st.selectbox("단가 국가",countries,key="pm_country"); cp=country[country["country_code"]==cc].copy()
            fig=px.line(cp,x="date",y="unit_price_usd_per_kg",title=f"{cc} · 수출단가",labels={"unit_price_usd_per_kg":"USD/kg"})
            render_chart(fig_layout(fig,350,"USD/kg",False),source_key="customs_item_country",csv_df=cp,csv_name=f"{product}_{cc}_unitprice",key="pm4")
    with st.expander("HS10 lineage",expanded=False):
        lin=q("SELECT hsk10,display_name,hs6,mti6,classification_status,classification_note FROM dim_product_taxonomy WHERE item20=? AND middle_category=? AND product=? ORDER BY hsk10",(item,mid,product))
        st.dataframe(lin,hide_index=True,width="stretch")
        st.caption("HS가 제품을 완전히 분리하지 못하는 경우 국가·중량·단가를 함께 보며 Proxy로 해석합니다.")



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
    flash=load_flash_snapshots(FLASH_SEED,FLASH_CACHE)
    if flash.empty: st.info("Flash seed/cache 없음"); return
    months=sorted(flash["month"].dropna().astype(str).unique()); month=st.selectbox("월",months,index=len(months)-1,key="flash_month")
    current=flash[flash["month"].astype(str)==month].copy(); current["checkpoint_day"]=pd.to_numeric(current["checkpoint_day"],errors="coerce"); current=current.dropna(subset=["checkpoint_day","export_usd_m"]).sort_values("checkpoint_day")
    if current.empty: st.info("선택한 월의 수출 속보 데이터가 없습니다."); return
    latest=current.iloc[-1]; status_label="확정" if int(latest["checkpoint_day"])>=28 or str(latest.get("status","")).strip()=="확정" else "집계중"
    k1,k2,k3,k4=st.columns(4); k1.metric("누적 수출",usd100m(latest["export_usd_m"]*1_000_000)); k2.metric("전년 대비",pct(latest.get("export_yoy_pct"))); k3.metric("누적 수입",usd100m(latest.get("import_usd_m")*1_000_000)); k4.metric("상태",f"{status_label} · 1~{int(latest['checkpoint_day'])}일")
    comp=flash_comparison_frame(flash,month,int(latest["checkpoint_day"])); c1,c2=st.columns(2)
    with c1:
        fig=px.line(current,x="checkpoint_day",y=current["export_usd_m"]/100,markers=True,title=f"{month} · 10일→20일→월말",labels={"checkpoint_day":"누적 일수","y":"억달러"})
        render_chart(fig_layout(fig,350,"억달러",False),source_key="flash",csv_df=current,csv_name=f"flash_{month}",key="flash1")
    with c2:
        if not comp.empty:
            comp=comp.copy(); comp["수출_억달러"]=comp["export_usd_m"]/100; fig=px.bar(comp,x="comparison",y="수출_억달러",title="전년·전월·5년평균 비교")
            render_chart(fig_layout(fig,350,"억달러",False),source_key="flash",csv_df=comp,csv_name=f"flash_compare_{month}",key="flash2")


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
elif page=="산업 스크리너": render_industry_scanner()
elif page=="산업 상세": render_industry_detail()
elif page=="수출 성장": render_growth_leaders()
elif page=="품목 모니터": render_product_monitor()
elif page=="종목 후보": render_stock_candidates()
elif page=="최근 수출": render_export_flash()
elif page=="데이터 점검": render_data_qc()

st.caption("Sources: KOSIS 광업제조업동향 · 관세청 수출입 OpenAPI · KITA HSK-MTI · 산업부 20대 품목 · 2026 fixed research taxonomy")
