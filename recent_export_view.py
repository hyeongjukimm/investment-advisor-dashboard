"""Monthly actuals with a separate current-month cumulative provisional bar."""
import pandas as pd
from provisional_trade import checkpoint_history


def recent_series(snapshots, dimension, category, *, monthly=None, confirmed_through, current_month):
    limit=pd.Timestamp(confirmed_through).to_period('M').to_timestamp()
    current=pd.Timestamp(current_month).to_period('M').to_timestamp()
    historic=checkpoint_history(snapshots,dimension,'month_end',category)
    # A completed month's provisional full total must remain visible while
    # the monthly final mart still lags behind (e.g. September on October 1).
    historic=historic[historic.date<=max(limit,current-pd.DateOffset(months=1))].copy()
    historic['status']='월말 잠정'
    historic['source_kind']='잠정 API 월말'
    if monthly is not None and not monthly.empty:
        actual=monthly[['date','export_usd']].copy()
        actual['date']=pd.to_datetime(actual.date)
        actual=actual[actual.date<=limit].sort_values('date').drop_duplicates('date')
        values=actual.set_index('date').export_usd
        for offset,column in [(12,'yoy_pct'),(1,'mom_pct')]:
            prior=(actual.date-pd.DateOffset(months=offset)).map(values).replace(0,float('nan'))
            actual[column]=(actual.export_usd/prior-1)*100
        actual['status']='확정'
        actual['source_kind']='월간 HS 통계'
        historic=pd.concat([historic[~historic.date.isin(actual.date)],actual],ignore_index=True)
    historic=historic.sort_values('date')
    historic['period_label']=historic.apply(lambda r:f'{r.date:%Y.%m} · 월 전체 {r.status}',axis=1)
    historic['is_current']=False
    for column in ['amount_10','amount_20_increment','amount_end_increment','amount_unsplit']:
        historic[column]=float('nan')
    historic['amount_month']=historic.export_usd
    available=snapshots[(snapshots.dimension==dimension)&(snapshots.category==category)&(snapshots.date==current)]
    if available.empty or current<=limit:
        return historic.reset_index(drop=True)
    last=available.sort_values('checkpoint_day').iloc[-1]
    observation=checkpoint_history(snapshots,dimension,last.checkpoint,category)
    row=observation[observation.date==current].iloc[-1].copy()
    row['status']='잠정';row['source_kind']='10일 단위 잠정 API';row['is_current']=True
    row['period_label']=f'{current:%Y.%m} · 1~{int(last.checkpoint_day)}일 잠정'
    amounts=available.set_index('checkpoint').export_usd.to_dict()
    row['amount_month']=float('nan')
    for column in ['amount_10','amount_20_increment','amount_end_increment','amount_unsplit']:
        row[column]=float('nan')
    checkpoints=[c for c in ['10','20','month_end'] if c in amounts]
    ordered=[amounts[c] for c in checkpoints]
    if not checkpoints or checkpoints[0]!='10' or any(b<a for a,b in zip(ordered,ordered[1:])):
        # Missing checkpoints or downward revisions cannot be manufactured as zero/positive segments.
        row['amount_unsplit']=row.export_usd
    else:
        row['amount_10']=amounts['10']
        if '20' in amounts:row['amount_20_increment']=amounts['20']-amounts['10']
        if 'month_end' in amounts:
            if '20' in amounts:row['amount_end_increment']=amounts['month_end']-amounts['20']
            else:
                row['amount_10']=float('nan');row['amount_unsplit']=row.export_usd
    return pd.concat([historic,pd.DataFrame([row])],ignore_index=True).sort_values('date').reset_index(drop=True)
