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


def coverage_bounds(raw):
    with sqlite3.connect(raw) as con:
        earliest,latest=con.execute('SELECT MIN(date),MAX(date) FROM raw_item').fetchone()
    if earliest is None or latest is None:raise ValueError('월별 세계 수출 원본이 없습니다')
    return pd.Timestamp(earliest),pd.Timestamp(latest)


def expand_country_coverage(root: Path):
    data = root / 'data'
    raw = data / 'investment_advisor.sqlite'
    key = os.environ.get('CUSTOMS_SERVICE_KEY', '')
    if not key:
        raise RuntimeError('CUSTOMS_SERVICE_KEY 미설정')
    start,end=coverage_bounds(raw)
    limit=int(os.environ.get('CUSTOMS_COUNTRY_BATCH_CHUNKS','42'))
    if limit<1:raise ValueError('수집 배치는 1 이상이어야 합니다')
    client=CustomsClient(key,timeout=90)
    report={'start':str(start.date()),'end':str(end.date()),'countries':{},'errors':[]}
    pending=[(a,b,country) for country in DESTINATIONS for a,b in missing_country_chunks(raw,country,start,end)]
    # Collect the same historical years across destinations before the next year.
    pending.sort(key=lambda chunk:(chunk[0],chunk[2]))
    for a,b,country in pending[:limit]:
        try:
            frame=normalize_item_country(client.fetch('item_country',a,b,country_code=country))
            if frame.empty:raise ValueError('빈 응답')
            upsert_dataframe(raw,'raw_item_country',frame,['date','country_code','hsk10'])
            report['countries'][country]=report['countries'].get(country,0)+len(frame)
            print(f'{country} {a:%Y-%m}..{b:%Y-%m}: {len(frame):,}개 수집',flush=True)
        except Exception as exc:
            # Retain successful chunks; failed ranges remain pending for the next run.
            report['errors'].append({'country':country,'start':str(a.date()),'end':str(b.date()),'error':type(exc).__name__})
            print(f'{country} {a:%Y-%m}..{b:%Y-%m}: 재시도 예정 ({type(exc).__name__})',flush=True)
    report['remaining_chunks']=sum(len(missing_country_chunks(raw,country,start,end)) for country in DESTINATIONS)
    report['complete']=report['remaining_chunks']==0
    for country in DESTINATIONS:
        with sqlite3.connect(raw) as con:
            count=con.execute('SELECT COUNT(*) FROM raw_item_country WHERE country_code=?',(country,)).fetchone()[0]
        _update_meta(raw,f'item_country:{country}',end,count,f'full country history: {start:%Y-%m}..{end:%Y-%m}')
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
