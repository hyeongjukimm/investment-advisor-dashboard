"""Expand the monitored monthly destinations without changing world totals."""
from pathlib import Path
import os
import json
import sqlite3
import pandas as pd
from customs_pipeline import CustomsClient, iter_month_chunks, normalize_item_country, upsert_dataframe, _update_meta
from mart_builder import build_analysis_mart, make_share_snapshot
from validate_snapshot import promote_snapshot

DESTINATIONS = 'US,CN,VN,JP,HK,TW,SG,IN,MY,DE,NL,PL,FR,GB,MX,ID,TH,CA,AU,IT,ES'.split(',')


def missing_country_chunks(raw, country, start, end):
    with sqlite3.connect(raw) as con:
        rows=con.execute('SELECT DISTINCT date FROM raw_item_country WHERE country_code=? AND date>=? AND date<=?',
            (country,str(start.date()),str(end.date()))).fetchall()
    present={pd.Timestamp(r[0]).to_period('M').to_timestamp() for r in rows}
    missing=[d for d in pd.date_range(start,end,freq='MS') if d not in present]
    if not missing:return []
    ranges=[];first=previous=missing[0]
    for month in missing[1:]:
        if month!=previous+pd.DateOffset(months=1):
            ranges.extend(iter_month_chunks(first,previous,12));first=month
        previous=month
    ranges.extend(iter_month_chunks(first,previous,12))
    return ranges


def expand_country_coverage(root: Path):
    data = root / 'data'
    raw = data / 'investment_advisor.sqlite'
    key = os.environ.get('CUSTOMS_SERVICE_KEY', '')
    if not key:
        raise RuntimeError('CUSTOMS_SERVICE_KEY 미설정')
    with sqlite3.connect(raw) as con:
        latest = con.execute('SELECT MAX(date) FROM raw_item').fetchone()[0]
    end = pd.Timestamp(latest)
    months=int(os.environ.get('CUSTOMS_ITEM_COUNTRY_MONTHS','60'))
    if not 15<=months<=120:raise ValueError('국가별 수집 범위는 15~120개월이어야 합니다')
    start = end - pd.DateOffset(months=months-1)
    client = CustomsClient(key, timeout=90)
    report = {'start': str(start.date()), 'end': str(end.date()), 'countries': {}}
    for country in DESTINATIONS:
        chunks=missing_country_chunks(raw,country,start,end)
        if not chunks:
            report['countries'][country] = f'기존 {months}개월 사용'
            continue
        received = 0
        for a, b in chunks:
            rows = client.fetch('item_country', a, b, country_code=country)
            frame = normalize_item_country(rows)
            if frame.empty:
                raise RuntimeError(f'{country} 월별 품목 응답이 비어 있습니다')
            upsert_dataframe(raw, 'raw_item_country', frame, ['date','country_code','hsk10'])
            received += len(frame)
        with sqlite3.connect(raw) as con:
            count = con.execute('SELECT COUNT(*) FROM raw_item_country WHERE country_code=?', (country,)).fetchone()[0]
        _update_meta(raw, f'item_country:{country}', end, count, f'country coverage: {start:%Y-%m}..{end:%Y-%m}')
        report['countries'][country] = received
        print(f'{country}: {received:,}개 월·HS10 관측치 수집')
    candidate = data / 'investment_mart.coverage.sqlite'
    share = data / 'share_snapshot.coverage.sqlite'
    report['build'] = build_analysis_mart(raw, candidate, data/'motir20_hsk_mti_mapping_2026_full_clean.csv', data/'kosis_cycle_cache.csv', data/'industry_export_bridge.csv')
    make_share_snapshot(candidate, share)
    report['validation'] = promote_snapshot(share, data/'share_snapshot.sqlite')
    candidate.unlink(missing_ok=True)
    (data/'country_coverage_status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    return report


if __name__ == '__main__':
    try:
        print(json.dumps(expand_country_coverage(Path(__file__).resolve().parent), ensure_ascii=False, indent=2, default=str))
    except Exception as exc:
        # Do not print requests URLs containing service keys.
        print(f'월별 국가 수집 실패: {type(exc).__name__}')
        raise SystemExit(1)
