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


def expand_country_coverage(root: Path):
    data = root / 'data'
    raw = data / 'investment_advisor.sqlite'
    key = os.environ.get('CUSTOMS_SERVICE_KEY', '')
    if not key:
        raise RuntimeError('CUSTOMS_SERVICE_KEY 미설정')
    with sqlite3.connect(raw) as con:
        latest = con.execute('SELECT MAX(date) FROM raw_item').fetchone()[0]
    end = pd.Timestamp(latest)
    start = end - pd.DateOffset(months=23)
    client = CustomsClient(key, timeout=90)
    report = {'start': str(start.date()), 'end': str(end.date()), 'countries': {}}
    for country in DESTINATIONS:
        with sqlite3.connect(raw) as con:
            count = con.execute('SELECT COUNT(DISTINCT date) FROM raw_item_country WHERE country_code=? AND date>=? AND date<=?',
                (country, str(start.date()), str(end.date()))).fetchone()[0]
        if count >= 24:
            report['countries'][country] = '기존 24개월 사용'
            continue
        received = 0
        for a, b in iter_month_chunks(start, end, 12):
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
