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
                fig.add_trace(go.Bar(x=composition_dates, y=composition[column] / 1e8, name=column, offsetgroup='amount'), secondary_y=False)
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
