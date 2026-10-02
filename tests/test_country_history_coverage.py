import pandas as pd
from customs_pipeline import init_sqlite_db, upsert_dataframe
from refresh_country_coverage import missing_country_chunks


def test_country_backfill_keeps_existing_months_and_fetches_older_gap(tmp_path):
    raw=tmp_path/'raw.sqlite';init_sqlite_db(raw)
    dates=pd.date_range('2024-09-01','2026-08-01',freq='MS')
    upsert_dataframe(raw,'raw_item_country',pd.DataFrame({'date':dates.strftime('%Y-%m-%d'),'country_code':'US','hsk10':'3304991000','export_usd':1.,'export_weight':1.}),['date','country_code','hsk10'])
    chunks=missing_country_chunks(raw,'US',pd.Timestamp('2021-09-01'),pd.Timestamp('2026-08-01'))
    assert [(str(a.date()),str(b.date())) for a,b in chunks]==[
        ('2021-09-01','2022-08-01'),('2022-09-01','2023-08-01'),('2023-09-01','2024-08-01')]
    assert missing_country_chunks(raw,'US',pd.Timestamp('2024-09-01'),pd.Timestamp('2026-08-01'))==[]


def test_another_country_does_not_hide_a_gap(tmp_path):
    raw=tmp_path/'raw.sqlite';init_sqlite_db(raw)
    upsert_dataframe(raw,'raw_item_country',pd.DataFrame({'date':['2026-08-01'],'country_code':['CN'],'hsk10':['3304991000'],'export_usd':[1.],'export_weight':[1.]}),['date','country_code','hsk10'])
    chunks=missing_country_chunks(raw,'US',pd.Timestamp('2026-08-01'),pd.Timestamp('2026-08-01'))
    assert chunks==[(pd.Timestamp('2026-08-01'),pd.Timestamp('2026-08-01'))]
