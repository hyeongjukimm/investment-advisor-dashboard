import pandas as pd
import pytest
from recent_export_view import recent_series
from trade_charts import recent_export_figure


def observations():
    return pd.DataFrame([
        ['2026-08-01','month_end',31,'product','전체',900.,'잠정'],
        ['2026-09-01','10',10,'product','전체',30.,'잠정'],
        ['2026-09-01','20',20,'product','전체',80.,'잠정'],
        ['2025-09-01','20',20,'product','전체',40.,'잠정'],
        ['2026-08-01','20',20,'product','전체',50.,'잠정'],
    ],columns=['date','checkpoint','checkpoint_day','dimension','category','export_usd','status']).assign(date=lambda x:pd.to_datetime(x.date))


def test_past_uses_whole_confirmed_month_current_stacks_increments():
    monthly=pd.DataFrame({'date':pd.to_datetime(['2026-08-01']),'export_usd':[1000.]})
    out=recent_series(observations(),'product','전체',monthly=monthly,confirmed_through='2026-08-01',current_month='2026-09-01')
    assert out.export_usd.tolist()==[1000.,80.]
    assert out.status.tolist()==['확정','잠정']
    latest=out.iloc[-1]
    assert latest.amount_10==30 and latest.amount_20_increment==50
    assert latest.yoy_pct==100 and latest.mom_pct==pytest.approx(60)
    assert out.iloc[0].period_label=='2026.08 · 월 전체 확정'


def test_no_current_snapshot_stops_at_latest_confirmed_month():
    monthly=pd.DataFrame({'date':pd.to_datetime(['2026-08-01']),'export_usd':[1000.]})
    out=recent_series(observations().loc[lambda x:x.date!=pd.Timestamp('2026-09-01')],'product','전체',monthly=monthly,confirmed_through='2026-08-01',current_month='2026-09-01')
    assert len(out)==1 and out.date.max()==pd.Timestamp('2026-08-01')


def test_month_end_api_never_gets_relabelled_confirmed():
    out=recent_series(observations(),'product','전체',confirmed_through='2026-08-01',current_month='2026-09-01')
    assert out.iloc[0].status=='월말 잠정'


def test_current_increment_requires_both_observations():
    out=recent_series(observations().query('checkpoint != "10"'),'product','전체',confirmed_through='2026-08-01',current_month='2026-09-01')
    assert pd.isna(out.iloc[-1].amount_20_increment)
    assert out.iloc[-1].amount_unsplit==80


def test_chart_does_not_double_count_cumulative_twenty_day_value():
    monthly=pd.DataFrame({'date':pd.to_datetime(['2026-08-01']),'export_usd':[1000.]})
    out=recent_series(observations(),'product','전체',monthly=monthly,confirmed_through='2026-08-01',current_month='2026-09-01')
    fig=recent_export_figure([('전체',out)],title='전체')
    bars=[t for t in fig.data if t.type=='bar']
    assert sum(t.y[-1] for t in bars if pd.notna(t.y[-1]))==80/1e8
    assert all(t.customdata[-1][0]=='2026.09 · 1~20일 잠정' for t in bars)


def test_ten_day_only_has_no_twenty_day_segment():
    data=observations()
    data=data[~((data.date==pd.Timestamp('2026-09-01'))&(data.checkpoint=='20'))]
    out=recent_series(data,'product','전체',confirmed_through='2026-08-01',current_month='2026-09-01')
    assert out.iloc[-1].amount_10==30
    assert pd.isna(out.iloc[-1].amount_20_increment)
    assert out.iloc[-1].export_usd==30


def test_downward_revision_uses_latest_total_without_negative_stack():
    data=observations()
    data.loc[(data.date==pd.Timestamp('2026-09-01'))&(data.checkpoint=='20'),'export_usd']=20
    out=recent_series(data,'product','전체',confirmed_through='2026-08-01',current_month='2026-09-01')
    assert out.iloc[-1].amount_unsplit==20
    assert pd.isna(out.iloc[-1].amount_10)
