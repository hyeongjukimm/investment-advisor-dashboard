import pandas as pd
from trade_charts import amount_growth_figure, provisional_summary_figure


def frame(amount, growth=10):
    return pd.DataFrame({'date':pd.to_datetime(['2026-08-01']), 'export_usd':[amount], 'yoy_pct':[growth], 'mom_pct':[growth/2]})


def test_amount_and_growth_use_separate_axes_and_usd_conversion():
    fig=amount_growth_figure([('전체',frame(200000000))],title='수출')
    assert fig.data[0].y[0]==2
    assert fig.data[0].yaxis=='y'
    assert fig.data[1].yaxis=='y2'
    assert fig.data[1].y[0]==10


def test_total_is_grouped_beside_major_stack_and_each_growth_is_preserved():
    total,major=frame(1000000000,10),frame(600000000,25)
    fig=provisional_summary_figure(total,major,{'반도체':frame(400000000),'선박':frame(200000000)})
    bars=[t for t in fig.data if t.type=='bar']
    assert [t.offsetgroup for t in bars]==['total','major','major']
    lines=[t for t in fig.data if t.type=='scatter']
    assert [t.y[0] for t in lines]==[10,25]
    assert fig.layout.barmode=='relative'


def test_mom_choice_updates_both_growth_series():
    fig=provisional_summary_figure(frame(100),frame(60,20),{},growth='mom_pct')
    lines=[t for t in fig.data if t.type=='scatter']
    assert [t.y[0] for t in lines]==[5,10]
    assert all('MoM' in t.name for t in lines)


def test_provisional_hover_uses_actual_cutoff_for_every_summary_trace():
    data=frame(200000000)
    data['date']=pd.to_datetime(['2026-09-01'])
    data['checkpoint_day']=20
    fig=provisional_summary_figure(data,data,{'반도체':data})
    assert all(pd.Timestamp(t.x[0])==pd.Timestamp('2026-09-20') for t in fig.data)
    assert fig.layout.xaxis.hoverformat=='%Y년 %m월 1~%d일 잠정'
    assert data.date.iloc[0]==pd.Timestamp('2026-09-01')


def test_country_composition_and_growth_share_actual_month_end_date():
    data=frame(200000000)
    data['date']=pd.to_datetime(['2026-02-01'])
    data['checkpoint_day']=28
    composition=pd.DataFrame({'date':data.date, '중국':[100000000], 'Others':[100000000]})
    fig=amount_growth_figure([('전체',data)],title='국가',composition=composition)
    assert all(pd.Timestamp(t.x[0])==pd.Timestamp('2026-02-28') for t in fig.data)
