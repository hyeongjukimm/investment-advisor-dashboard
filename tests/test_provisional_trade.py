import pandas as pd
import pytest

from provisional_trade import parse_provisional_xml, checkpoint_history, major_product_total, country_composition, save_snapshots


def xml(month, period, values):
    fields=''.join(f'<itemUsdAmt{i:02}>{v}</itemUsdAmt{i:02}>' for i,v in enumerate(values))
    return f'<response><header><resultCode>00</resultCode></header><body><items><item>{fields}<priodMon>{month}</priodMon><priodDt>{period}</priodDt></item></items><totalCount>1</totalCount></body></response>'


def test_xml_converts_thousand_dollars_and_preserves_month_end():
    df=parse_provisional_xml(xml('202602','01~28',['1,234']+[10]*10),'product')
    assert df.iloc[0].export_usd==1234000
    assert set(df.checkpoint)=={'month_end'}
    assert set(df.checkpoint_day)=={28}
    assert set(df.status)=={'잠정'}


def test_missing_amount_is_not_zero_and_unknown_schema_rejected():
    df=parse_provisional_xml(xml('202609','01~20',['100','']+[10]*9),'product')
    assert pd.isna(df[df.category=='반도체'].iloc[0].export_usd)
    with pytest.raises(ValueError):
        parse_provisional_xml('<response><header><resultCode>00</resultCode></header><body><items><item><other>10</other></item></items></body></response>','country')


def test_growth_joins_same_checkpoint_and_exact_months():
    df=pd.concat([parse_provisional_xml(xml(m,p,[v]+[10]*10),'product') for m,p,v in [('202508','01~31',100),('202608','01~31',150),('202509','01~20',40),('202609','01~20',80)]])
    h=checkpoint_history(df,'product','20','전체')
    assert h.iloc[-1].yoy_pct==100
    assert pd.isna(h.iloc[-1].mom_pct)
    h=checkpoint_history(df,'product','month_end','전체')
    assert h.iloc[-1].yoy_pct==50


def test_major_total_requires_all_ten_categories():
    df=parse_provisional_xml(xml('202609','01~20',[100]+[10]*10),'product')
    assert major_product_total(df).iloc[0].export_usd==100000
    assert major_product_total(df[df.category!='반도체']).empty


def test_composition_uses_world_total_and_fixed_top_five():
    totals=pd.DataFrame({'date':pd.to_datetime(['20260801','20260901']), 'export_usd':[100,120]})
    countries=pd.DataFrame([{'date':d,'country_code':c,'export_usd':v} for d in totals.date for c,v in zip('ABCDEF',[30,20,10,8,6,4])])
    result=country_composition(totals,countries,5)
    assert len([c for c in result.columns if c not in ['date','Others']])==5
    assert result.iloc[0].Others==26
    assert result.iloc[1].Others==46
    assert result.drop(columns='date').sum(axis=1).tolist()==[100,120]
    countries.loc[countries.country_code=='A','export_usd']=130
    with pytest.raises(ValueError):country_composition(totals,countries,5)


def test_revision_keeps_observations_but_current_uses_latest(tmp_path):
    path=tmp_path/'current.csv';a=parse_provisional_xml(xml('202609','01~20',[100]+[10]*10),'product')
    save_snapshots(a,path)
    b=parse_provisional_xml(xml('202609','01~20',[110]+[10]*10),'product')
    save_snapshots(b,path)
    assert pd.read_csv(path).query("category == '전체'").iloc[0].export_usd==110000
    assert len(pd.read_csv(path.with_name('current_history.csv')))==12
