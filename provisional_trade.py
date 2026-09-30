"""Official ten-day export snapshots; amounts are normalized to raw USD."""
from __future__ import annotations

import calendar
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PRODUCTS = ['전체', '반도체', '철강제품', '승용차', '석유제품', '무선통신기기', '선박', '자동차부품', '컴퓨터주변기기', '정밀기기', '가전제품']
COUNTRIES = ['전체', '중국', '미국', '유럽연합', '베트남', '홍콩', '일본', '대만', '인도', '싱가포르', '말레이시아']
SERVICES = {'product': ('prlstMmUtPrviExpAcrs', 'getPrlstMmUtPrviExpAcrs'), 'country': ('cntyMmUtPrviExpAcrs', 'getCntyMmUtPrviExpAcrs')}
# These links express industry relevance, not statistical equivalence.
TOP20_LINKS = {
    '반도체': ('반도체', '관세청 주요품목 기준'),
    '철강': ('철강제품', '관세청 철강제품 기준'),
    '철강제품': ('철강제품', '관세청 철강제품 기준'),
    '자동차': ('승용차', '자동차 중 승용차만 제공'),
    '석유제품': ('석유제품', '관세청 주요품목 기준'),
    '무선통신기기': ('무선통신기기', '관세청 주요품목 기준'),
    '선박': ('선박', '관세청 주요품목 기준'),
    '자동차부품': ('자동차부품', '관세청 주요품목 기준'),
    '컴퓨터': ('컴퓨터주변기기', '컴퓨터 중 주변기기 기준'),
    '컴퓨터주변기기': ('컴퓨터주변기기', '관세청 주요품목 기준'),
    '가전': ('가전제품', '관세청 가전제품 기준'),
    '가전제품': ('가전제품', '관세청 가전제품 기준'),
}
COLUMNS = ['date', 'checkpoint', 'checkpoint_day', 'dimension', 'category', 'export_usd', 'status', 'fetched_at']


def parse_provisional_xml(payload: str | bytes, dimension: str) -> pd.DataFrame:
    root = ET.fromstring(payload)
    for el in root.iter():
        el.tag = el.tag.rsplit('}', 1)[-1]
    code = root.findtext('.//resultCode')
    if code != '00':
        reason = root.findtext('.//resultMsg') or root.findtext('.//returnAuthMsg') or root.findtext('.//errMsg') or '정상 응답이 아닙니다'
        raise ValueError(f'관세청 잠정치 오류 {code or "gateway"}: {reason}')
    rows = root.findall('.//item')
    count = int(root.findtext('.//totalCount') or len(rows))
    if count > len(rows):
        raise ValueError('API 응답이 잘렸습니다. 조회 기간을 줄이세요.')
    names = PRODUCTS if dimension == 'product' else COUNTRIES
    # Both official services return itemUsdAmt00..10; labels depend on service.
    stems = ['itemUsdAmt']
    now = datetime.now(timezone.utc).isoformat(timespec='microseconds')
    out = []
    for item in rows:
        fields = {el.tag: (el.text or '').strip() for el in item}
        stem = next((s for s in stems if f'{s}00' in fields), None)
        if stem is None:
            raise ValueError(f'잠정치 {dimension} 응답 필드 확인 필요: {sorted(fields)}')
        month = re.sub(r'\D', '', fields.get('priodMon', ''))
        date = pd.to_datetime(month, format='%Y%m', errors='raise')
        days = re.findall(r'\d+', fields.get('priodDt', ''))
        if len(days) != 2 or int(days[0]) != 1:
            raise ValueError('잠정치 집계 기간 형식 오류')
        day = int(days[-1])
        checkpoint = str(day) if day in (10, 20) else 'month_end'
        if checkpoint == 'month_end' and day != calendar.monthrange(date.year, date.month)[1]:
            raise ValueError('알 수 없는 잠정치 집계 종료일')
        for i, name in enumerate(names):
            field = f'{stem}{i:02}'
            if field not in fields:
                raise ValueError(f'잠정치 응답 필드 누락: {field}')
            value = pd.to_numeric(fields[field].replace(',', ''), errors='coerce')
            if pd.notna(value) and value < 0:
                raise ValueError('음수 수출금액')
            out.append(dict(date=date, checkpoint=checkpoint, checkpoint_day=day,
                            dimension=dimension, category=name, export_usd=value * 1000,
                            status='잠정', fetched_at=now))
    return pd.DataFrame(out, columns=COLUMNS)


def load_snapshots(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, dtype={'checkpoint': str})
    df['date'] = pd.to_datetime(df['date'])
    return df


def save_snapshots(new: pd.DataFrame, path: str | Path) -> None:
    if new.empty:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    history_path = path.with_name(path.stem + '_history.csv')
    keys = ['date', 'checkpoint', 'dimension', 'category']
    old = load_snapshots(path)
    # Record only new/revised values; unchanged daily reads do not inflate history.
    prior = old.set_index(keys)['export_usd'].to_dict() if not old.empty else {}
    changed = new.apply(lambda r: tuple(r[k] for k in keys) not in prior or not (
        (pd.isna(r.export_usd) and pd.isna(prior[tuple(r[k] for k in keys)])) or
        r.export_usd == prior[tuple(r[k] for k in keys)]), axis=1)
    previous_history = load_snapshots(history_path)
    history = pd.concat([f for f in [previous_history, new.loc[changed]] if not f.empty], ignore_index=True)
    current = pd.concat([f for f in [old, new] if not f.empty], ignore_index=True).drop_duplicates(keys, keep='last').sort_values(keys)
    for target, frame in [(history_path, history), (path, current)]:
        temp = target.with_suffix('.tmp')
        frame.to_csv(temp, index=False)
        os.replace(temp, target)


def checkpoint_history(df: pd.DataFrame, dimension: str, checkpoint: str, category: str) -> pd.DataFrame:
    work = df[(df.dimension == dimension) & (df.checkpoint == checkpoint) & (df.category == category)].copy()
    work = work.sort_values('date').drop_duplicates('date', keep='last')
    values = work.set_index('date')['export_usd']
    for months, column in [(12, 'yoy_pct'), (1, 'mom_pct')]:
        previous = (work.date - pd.DateOffset(months=months)).map(values).replace(0, float('nan'))
        work[column] = (work.export_usd / previous - 1) * 100
    return work


def major_product_total(df: pd.DataFrame) -> pd.DataFrame:
    work = df[(df.dimension == 'product') & df.category.isin(PRODUCTS[1:])].copy()
    if work.empty:
        return pd.DataFrame(columns=COLUMNS)
    keys = ['date', 'checkpoint', 'checkpoint_day']
    grouped = work.groupby(keys, as_index=False).agg(export_usd=('export_usd', lambda s: s.sum(min_count=10)),
        categories=('category', 'nunique'), fetched_at=('fetched_at', 'max'))
    grouped = grouped[(grouped.categories == 10) & grouped.export_usd.notna()].drop(columns='categories')
    grouped['category'] = '주요 10개 품목 합계'
    grouped['dimension'] = 'product'
    grouped['status'] = '잠정'
    return grouped[COLUMNS]


def country_composition(total: pd.DataFrame, country: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    if total.empty or country.empty:
        return pd.DataFrame()
    top = country.groupby('country_code').export_usd.sum().nlargest(top_n).index.tolist()
    pivot = country[country.country_code.isin(top)].pivot_table(index='date', columns='country_code', values='export_usd', aggfunc='sum')
    result = total[['date', 'export_usd']].set_index('date').join(pivot).sort_index()
    # No missing observations are manufactured into zero exports.
    result['Others'] = result.export_usd - result[top].sum(axis=1, min_count=len(top))
    if (result.Others < -.01).any():
        raise ValueError('국가별 합계가 전세계 금액을 초과합니다. 집계 범위를 확인하세요.')
    return result.drop(columns='export_usd').reset_index()


def refresh_provisional(data_dir: str | Path, *, product_key: str, country_key: str, history_start='2016-01') -> dict:
    data = Path(data_dir)
    cache = data / 'export_provisional.csv'
    old = load_snapshots(cache)
    now = pd.Timestamp.now(tz='Asia/Seoul').tz_localize(None).to_period('M').to_timestamp()
    results = {}
    session = requests.Session()
    session.mount('https://', HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])))
    for dimension, key in [('product', product_key), ('country', country_key)]:
        if not key:
            results[dimension] = {'ok': False, 'error': '인증키 미설정'}
            continue
        have = old[old.dimension == dimension]
        start = pd.Timestamp(history_start) if have.empty else max(pd.Timestamp(history_start), now - pd.DateOffset(months=14))
        received = []
        try:
            svc, operation = SERVICES[dimension]
            for year in range(start.year, now.year + 1):
                a, b = max(start, pd.Timestamp(year, 1, 1)), min(now, pd.Timestamp(year, 12, 1))
                response = session.get(f'https://apis.data.go.kr/1220000/{svc}/{operation}',
                    params={'serviceKey': unquote(key), 'strtYymm': a.strftime('%Y%m'), 'endYymm': b.strftime('%Y%m')}, timeout=45)
                response.raise_for_status()
                received.append(parse_provisional_xml(response.content, dimension))
            new = pd.concat(received, ignore_index=True)
            if new.empty:
                raise ValueError('잠정치 응답에 데이터가 없습니다')
            save_snapshots(new, cache)
            results[dimension] = {'ok': True, 'rows': len(new), 'latest_month': str(new.date.max().date())}
        except requests.RequestException as exc:
            # requests exception strings can contain serviceKey in the URL.
            results[dimension] = {'ok': False, 'error': type(exc).__name__}
        except (ValueError, ET.ParseError) as exc:
            results[dimension] = {'ok': False, 'error': str(exc)}
    data.mkdir(parents=True, exist_ok=True)
    results['fetched_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    (data / 'provisional_status.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    return results


if __name__ == '__main__':
    common = os.getenv('CUSTOMS_SERVICE_KEY', '')
    result = refresh_provisional(Path(__file__).resolve().parent / 'data',
        product_key=os.getenv('CUSTOMS_PROVISIONAL_SERVICE_KEY', '') or common,
        country_key=os.getenv('CUSTOMS_PROVISIONAL_COUNTRY_KEY', '') or common)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result['product']['ok'] or not result['country']['ok']:
        raise SystemExit(1)
