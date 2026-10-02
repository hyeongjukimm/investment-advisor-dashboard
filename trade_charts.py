from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def chart_dates(frame: pd.DataFrame):
    # Keep month keys for growth calculations; plot the actual provisional cutoff.
    dates = pd.to_datetime(frame.date)
    if 'checkpoint_day' in frame:
        return dates + pd.to_timedelta(frame.checkpoint_day.astype(int) - 1, unit='D')
    return dates


def amount_growth_figure(series: list[tuple[str, pd.DataFrame]], *, title: str, growth='yoy_pct', composition=None):
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    provisional = any('checkpoint_day' in frame for _, frame in series)
    colors = ['#2996de', '#65bb90']
    if composition is not None and not composition.empty:
        date_map = pd.Series(chart_dates(series[0][1]).to_numpy(), index=series[0][1].date)
        composition_dates = composition.date.map(date_map)
        for column in composition.columns:
            if column != 'date':
                color='#a0a7b3' if column=='세계 합계(국가 자료 미수집)' else '#e0b33d' if column=='Others' else None
                fig.add_trace(go.Bar(x=composition_dates, y=composition[column] / 1e8, name=column,
                    marker_color=color, offsetgroup='amount'), secondary_y=False)
    else:
        for i, (name, frame) in enumerate(series):
            fig.add_trace(go.Bar(x=chart_dates(frame), y=frame.export_usd / 1e8, name=f'{name} 수출액',
                marker_color=['#a0a7b3', '#82bbbc'][i % 2], offsetgroup=name), secondary_y=False)
    for i, (name, frame) in enumerate(series):
        if growth in frame:
            fig.add_trace(go.Scatter(x=chart_dates(frame), y=frame[growth], name=f'{name} {"YoY" if growth == "yoy_pct" else "MoM"}',
                mode='lines', line=dict(color=colors[i % 2], width=2.5, dash='solid' if i == 0 else 'dash')), secondary_y=True)
    fig.update_layout(title=title, height=420, barmode='relative' if composition is not None else 'group',
        hovermode='x unified', margin=dict(l=12, r=12, t=65, b=35), legend=dict(orientation='h', y=1.03, x=0))
    fig.update_yaxes(title_text='수출금액 (억달러)', secondary_y=False, rangemode='tozero')
    fig.update_yaxes(title_text='성장률 (%)', secondary_y=True, showgrid=False, zeroline=True)
    fig.update_xaxes(tickformat='%Y.%m', hoverformat='%Y년 %m월 1~%d일 잠정' if provisional else '%Y년 %m월')
    return fig


def provisional_summary_figure(total: pd.DataFrame, major: pd.DataFrame, products: dict[str, pd.DataFrame], *, growth="yoy_pct"):
    fig = amount_growth_figure([('전체', total), ('주요 10개 품목 합계', major)], title='전체 수출 vs 주요 10개 품목 누적 수출', growth=growth)
    # Group total beside the stacked major products, so the subset is not added to the total.
    fig.data = tuple(trace for trace in fig.data if trace.type != 'bar')
    fig.add_trace(go.Bar(x=chart_dates(total), y=total.export_usd / 1e8, name='전체 수출', marker_color='#a0a7b3', offsetgroup='total'), secondary_y=False)
    for name, frame in products.items():
        fig.add_trace(go.Bar(x=chart_dates(frame), y=frame.export_usd / 1e8, name=name, offsetgroup='major'), secondary_y=False)
    fig.update_layout(barmode='relative', height=500, margin=dict(l=12,r=12,t=55,b=120),
        legend=dict(orientation='h',yanchor='top',y=-.22,x=0))
    return fig


def recent_export_figure(series, *, title, growth='yoy_pct'):
    fig=make_subplots(specs=[[{'secondary_y':True}]])
    stages=[('amount_month','월 전체','#9ca7b6'),('amount_10','1~10일 누적','#278dc8'),
            ('amount_20_increment','11~20일 증가분','#80c9e9'),('amount_end_increment','21일~월말 증가분','#b3dde9'),
            ('amount_unsplit','최신 누적(중간 발표 미수집)','#278dc8')]
    for i,(name,frame) in enumerate(series):
        if frame.empty:continue
        custom=frame[['period_label','export_usd','source_kind']].copy()
        custom['export_usd']=custom.export_usd/1e8
        for column,label,color in stages:
            if not frame[column].notna().any():continue
            fig.add_trace(go.Bar(x=frame.date,y=frame[column]/1e8,name=f'{name} · {label}',
                marker_color=color,offsetgroup=name,customdata=custom.to_numpy(),
                hovertemplate='%{customdata[0]}<br>%{fullData.name}: %{y:.2f}억 달러<br>기간 합계: %{customdata[1]:.2f}억 달러<br>%{customdata[2]}<extra></extra>'),secondary_y=False)
        history=frame[~frame.is_current]
        color=['#2996de','#65bb90'][i%2]
        label='YoY' if growth=='yoy_pct' else 'MoM'
        fig.add_trace(go.Scatter(x=history.date,y=history[growth],name=f'{name} 월 전체 {label}',mode='lines',
            line=dict(color=color,width=2.5),customdata=history[['period_label']].to_numpy(),
            hovertemplate='%{customdata[0]}<br>'+label+': %{y:.1f}%<extra></extra>'),secondary_y=True)
        current=frame[frame.is_current]
        if not current.empty:
            fig.add_trace(go.Scatter(x=current.date,y=current[growth],name=f'{name} 잠정 {label}',mode='markers',
                marker=dict(color=color,size=9,symbol='diamond'),customdata=current[['period_label']].to_numpy(),
                hovertemplate='%{customdata[0]}<br>동일 누적기간 '+label+': %{y:.1f}%<extra></extra>'),secondary_y=True)
    fig.update_layout(title=title,height=450,barmode='relative',hovermode='x unified',
        margin=dict(l=12,r=12,t=65,b=100),legend=dict(orientation='h',y=-.22,yanchor='top',x=0))
    fig.update_xaxes(tickformat='%Y.%m',hoverformat='%Y년 %m월')
    fig.update_yaxes(title_text='수출금액 (억달러)',secondary_y=False,rangemode='tozero')
    fig.update_yaxes(title_text='성장률 (%)',secondary_y=True,showgrid=False)
    return fig
