from nicegui import ui
from typing import Optional, Any
from decimal import Decimal
import math
import inspect
import datetime

from .panel.card import panel 
from utils.utils import colorize_numbers
         
                
def goals_bullet_card(
    title,
    rev_target_year,   
    exp_budget_year,  
    rev_actual_ytd,  
    exp_actual_ytd,  
    month_index=None, 
    ytd_share=None,   
    unit=' PLN',
    stretch=True,
    full_bleed=True,
    on_click: Optional[callable] = None
):
    if ytd_share is None:
        if month_index is None:
            month_index = datetime.date.today().month - 1
        ytd_share = (month_index + 1) / 12.0

    rev_target_ytd = rev_target_year * ytd_share
    exp_budget_ytd = exp_budget_year * ytd_share

    rev_ok = rev_actual_ytd >= rev_target_ytd
    exp_ok = exp_actual_ytd <= exp_budget_ytd

    bg_data = [
        {'value': rev_target_ytd, 'itemStyle': {'color': '#9CA3AF', 'borderColor': '#6B7280', 'borderWidth': 1}},
        {'value': exp_budget_ytd, 'itemStyle': {'color': '#9CA3AF', 'borderColor': '#6B7280', 'borderWidth': 1}},
    ]
    actual_data = [
        {'value': rev_actual_ytd, 'itemStyle': {'color': '#21BA45' if rev_ok else '#F59E0B'}},
        {'value': exp_actual_ytd, 'itemStyle': {'color': '#21BA45' if exp_ok else '#C10015'}},
    ]

    with panel() as card:
        if on_click:
            card.classes('cursor-pointer')
            
            async def _click_handler(_: Any) -> None:
                result = on_click() 
                if inspect.isawaitable(result):
                    await result

            card.on('click', _click_handler)
            
        if stretch:
            card.classes('w-full max-w-none').style('width:100%')
        if full_bleed:
            card.classes('p-0')

        ui.label(title).classes('text-sm font-semibold').style('padding-left:15px;padding-top:6px')

        ui.echart({
            'legend': {'top': 0, 'data': ['Cel/Budżet YTD', 'Stan YTD']},
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}, 'confine': True},

            'xAxis': {
                'type': 'value',
                'axisLabel': {
                    'formatter': f"{{value}}{unit}",  
                    'hideOverlap': True,
                    'margin': 4
                },
                'splitLine': {'show': True}
            },
            'yAxis': {
                'type': 'category',
                'axisTick': {'show': False},
                'data': ['Przychody', 'Wydatki'] 
            },

            'grid': {'left': 48, 'right': 40, 'top': 28, 'bottom': 10, 'containLabel': True},

            'series': [
                {
                    'name': 'Cel/Budżet YTD',
                    'type': 'bar',
                    'data': bg_data,
                    'barWidth': 26,      
                    'silent': True,
                    'z': 1,
                    'barBorderRadius': 4
                },

                {
                    'name': 'Stan YTD',
                    'type': 'bar',
                    'data': actual_data,
                    'barWidth': 16,
                    'barGap': '-100%',     
                    'z': 3,
                    'label': {
                        'show': True,
                        'position': 'insideRight',
                        'formatter': f"{{c}}{unit}",
                        'color': '#ffffff'
                    },
                    'barBorderRadius': 4
                },
            ],
        }).classes('w-full h-48').style('width:100%;display:block')
     
        
def render_top5_table_observer(rows, tone: str | None = None, top: int = 5):

    data = sorted(rows, key=lambda r: r.get('pl_pct', 0.0), reverse=True)[:top]

    prepared = []
    for i, r in enumerate(data, start=1):
        pl = float(r.get('pl_pct', 0.0))
        pl_act = float(r.get('pl_abs', 0.0))
        prepared.append({
            'rank': i,
            'sym': r.get('sym', ''),
            'pl_pct': pl,
            'pl_abs': pl_act,
            'pl_pct_fmt': f"{pl} PLN",
            'pl_abs_fmt': f"{pl_act} PLN ",
        })

    pl_col_classes = 'num'
    if tone == 'positive':
        pl_col_classes += ' bias-pos'
    elif tone == 'negative':
        pl_col_classes += ' bias-neg'

    cols = [
        {'name': 'rank', 'label': '#', 'field': 'rank', 'align': 'left', 'style': 'width:40px', 
         'headerStyle': 'font-weight:700'},
        {'name': 'sym', 'label': 'Ticker', 'field': 'sym', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'pl_pct_fmt', 'label': 'P/B (PLN)', 'field': 'pl_pct_fmt', 'align': 'right', 'classes': pl_col_classes, 
         'style': 'width:110px', 'headerStyle': 'font-weight:700'},
        {'name': 'pl_abs_fmt', 'label': 'P/A (PLN)', 'field': 'pl_abs_fmt', 'align': 'right', 'classes': 'num',
         'style': 'width:140px', 'headerStyle': 'font-weight:700'},
    ]

    t = ui.table(
        columns=cols,
        rows=prepared,
        row_key='sym',
    ).props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]') \
     .classes('top4-table q-mt-none') \
     .style('margin-top:-6px')

    t.add_slot('body-cell-pl_pct_fmt', """
    <q-td :props="props"
        :class="[
            'num',
            props.row.pl_pct < props.row.pl_abs ? 'text-positive' : '',
            props.row.pl_pct > props.row.pl_abs ? 'text-negative' : ''
        ]">
    {{ props.row.pl_pct_fmt }}
    </q-td>
    """)
    
    
def render_top5_table(rows, tone: str | None = None, top: int = 5, reverse=True, currency="PLN"):
    data = sorted(rows, key=lambda r: r.get('pl_pct', 0.0), reverse=reverse)[:top]

    prepared = []
    for i, r in enumerate(data, start=1):
        pl = float(r.get('pl_pct', 0.0) or 0.0)
        prepared.append({
            'rank': i,
            'sym': r.get('sym', ''),
            'pl_pct': pl,
            'pl_pct_fmt': f"{pl:+.2f}%",
            'pl_abs_fmt': f"{r.get('pl_abs', 0.0):+,.0f} {currency}".replace(',', ' '),
        })

    pl_col_classes = 'num'
    if tone == 'positive':
        pl_col_classes += ' bias-pos'
    elif tone == 'negative':
        pl_col_classes += ' bias-neg'

    cols = [
        {'name': 'rank', 'label': '#', 'field': 'rank', 'align': 'left', 'style': 'width:40px', 
         'headerStyle': 'font-weight:700'},
        {'name': 'sym', 'label': 'Ticker', 'field': 'sym', 'align': 'left', 'headerStyle': 'font-weight:700'},
        {'name': 'pl_pct_fmt', 'label': 'P/L %', 'field': 'pl_pct_fmt', 'align': 'right',
         'classes': pl_col_classes, 'style': 'width:110px', 'headerStyle': 'font-weight:700'},
        {'name': 'pl_abs_fmt', 'label': f'P/L ({currency})', 'field': 'pl_abs_fmt', 'align': 'right',
         'classes': 'num', 'style': 'width:140px', 'headerStyle': 'font-weight:700'},
    ]

    t = ui.table(
        columns=cols,
        rows=prepared,
        row_key='sym',
    ).props('flat dense separator=horizontal hide-bottom hide-pagination rows-per-page-options=[5]') \
     .classes('top4-table q-mt-none') \
     .style('margin-top:-6px')

    t.add_slot('body-cell-pl_pct_fmt', """
    <q-td :props="props"
          :class="(props.row.pl_pct > 0 ? 'text-positive' : (props.row.pl_pct < 0 ? 'text-negative' : '')) + ' num'">
      {{ props.row.pl_pct_fmt }}
    </q-td>
    """)
    

def pie_card(title, series):
    with panel():
        
        filtered_series = [
            s for s in series 
            if float(s.get('value') or 0) > 0
        ]

        filtered_legend = [s.get('name', '') for s in filtered_series]
        
        ui.label(title).classes('text-sm font-semibold')
        ui.echart({
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c} ({d}%)'},
            'legend': {'bottom': 0, 'padding': [0, 0, 6, 0], 'data': filtered_legend},
            'series': [{
                'type': 'pie',
                'radius': ['48%', '68%'],
                'center': ['50%', '42%'],
                'data': filtered_series,
                'avoidLabelOverlap': True,
            }],
        }).classes('w-full h-52')
    
        
def line_card(
    title,
    x,
    y,
    infl_pct=None,
    cpi=None,
    base='first',
    y_suffix=' PLN',
    show_nominal=True,
    show_real=True,
    stretch: bool = True,
    full_bleed: bool = True,
    show_mom: bool = True,
    cpi_kind: str = "auto",
):

    def _series_to_list(series: Any) -> Optional[list]:
        if series is None:
            return None
        if isinstance(series, dict):
            return [series.get(k) for k in x]
        return list(series)

    cpi_list = _series_to_list(cpi)
    infl_list = _series_to_list(infl_pct)

    if cpi_kind == "auto" and infl_list is None and cpi_list is not None:
        vals = [float(v) for v in cpi_list if v not in (None, 0)]

        if vals and max(map(abs, vals)) < 50:
            infl_list = cpi_list
            cpi_list = None
            cpi_kind = "infl_yoy"

    if cpi_kind in ("infl_yoy", "infl_mom") and infl_list is None and cpi_list is not None:
        infl_list = cpi_list
        cpi_list = None

    cpi_index_list: Optional[list[Optional[float]]] = None

    if cpi_kind == "index":
        cpi_index_list = [None if v in (None, 0) else float(v) for v in (cpi_list or [])]

    elif infl_list is not None:
        cpi_index_list = []
        cur = 100.0
        for i in range(len(x)):
            p = infl_list[i] if i < len(infl_list) else None

            if i == 0:
                cpi_index_list.append(cur)
                continue

            if p in (None, 0):
                cpi_index_list.append(cpi_index_list[-1] if cpi_index_list else None)
                continue

            p = float(p)

            if cpi_kind == "infl_mom":
                factor = 1.0 + (p / 100.0)
            else:
                factor = math.pow(1.0 + (p / 100.0), 1.0 / 12.0)

            cur = cur * factor
            cpi_index_list.append(cur)

    base_cpi = None
    if cpi_index_list is not None:
        if isinstance(base, (int, float)):
            base_cpi = float(base)
        elif base == 'first':
            base_cpi = next((v for v in cpi_index_list if v not in (None, 0)), None)
        elif base == 'last':
            for v in reversed(cpi_index_list):
                if v not in (None, 0):
                    base_cpi = v
                    break
        else:
            try:
                base_cpi = cpi_index_list[x.index(base)]
            except Exception:
                base_cpi = None

    if infl_list is None and cpi_index_list is not None and base_cpi not in (None, 0):
        infl_list = [
            None if v in (None, 0) else round((float(v) / float(base_cpi) - 1) * 100.0, 2)
            for v in cpi_index_list
        ]

    source = []
    for i, xi in enumerate(x):
        yi = y[i] if i < len(y) else None
        row = {'Okres': xi, 'Assets': yi}

        if show_real and yi is not None and cpi_index_list and base_cpi and i < len(cpi_index_list):
            idx = cpi_index_list[i]
            if idx not in (None, 0) and base_cpi not in (None, 0):
                try:
                    factor = Decimal(str(idx)) / Decimal(str(base_cpi))
                    row['AssetsReal'] = (Decimal(str(yi)) / factor) if factor != 0 else None
                except Exception:
                    row['AssetsReal'] = None

        pi = infl_list[i] if (infl_list and i < len(infl_list)) else None
        if pi is not None:
            row['Inflacja%'] = float(pi)
            
        if show_mom and i > 0:
            prev = y[i - 1]
            try:
                prev_d = Decimal(str(prev)) if prev not in (None, "") else None
                cur_d = Decimal(str(yi)) if yi not in (None, "") else None
                if prev_d is not None and cur_d is not None and prev_d != 0:
                    row["MoM%"] = float(((cur_d / prev_d) - Decimal("1")) * Decimal("100"))
                else:
                    row["MoM%"] = None
            except Exception:
                row["MoM%"] = None

        source.append(row)

    series, legend = [], []

    if show_nominal:
        legend.append('Nominalnie')
        series.append({
            'name': 'Nominalnie',
            'type': 'line',
            'datasetId': 'ds_all',
            'showSymbol': True,
            'symbol': 'circle',
            'symbolSize': 6,
            'smooth': True,
            'connectNulls': True,
            'lineStyle': {'width': 2},
            'areaStyle': {'opacity': 0.12},
            'yAxisIndex': 0,
            'encode': {'x': 'Okres', 'y': 'Assets', 'itemName': 'Okres', 'tooltip': ['Assets']},
        })

    if show_real and any(r.get('AssetsReal') is not None for r in source):
        legend.append('Realnie (CPI)')
        series.append({
            'name': 'Realnie (CPI)',
            'type': 'line',
            'datasetId': 'ds_all',
            'showSymbol': True,
            'symbol': 'circle',
            'symbolSize': 6,
            'smooth': True,
            'connectNulls': True,
            'lineStyle': {'width': 2, 'type': 'dashed'},
            'yAxisIndex': 0,
            'encode': {'x': 'Okres', 'y': 'AssetsReal', 'itemName': 'Okres', 'tooltip': ['AssetsReal']},
        })

    has_infl = any(r.get('Inflacja%') is not None for r in source)
    if has_infl:
        name_infl = f"Inflacja % (baza: {base})"
        legend.append(name_infl)
        series.append({
            'name': name_infl,
            'type': 'line',
            'datasetId': 'ds_all',
            'showSymbol': True,
            'symbol': 'circle',
            'symbolSize': 6,
            'smooth': True,
            'connectNulls': True,
            'yAxisIndex': 1,
            'lineStyle': {'width': 2},
            'encode': {'x': 'Okres', 'y': 'Inflacja%', 'itemName': 'Okres', 'tooltip': ['Inflacja%']},
        })
        
    if show_mom:
        legend.append("Zmiana m/m")
        series.append({
            "name": "Zmiana m/m",
            "type": "line",
            "datasetId": "ds_all",
            "showSymbol": True,
            "symbol": "circle",
            "symbolSize": 6,
            "smooth": True,
            "connectNulls": True,
            "yAxisIndex": 2,
            "lineStyle": {"width": 2},
            "encode": {"x": "Okres", "y": "MoM%", "itemName": "Okres", "tooltip": ["MoM%"]},
        })

    with panel() as card:
        if stretch:
            card.classes('w-full max-w-none')
            card.style('width:100%')
        if full_bleed:
            card.classes('p-0')

        ui.label(title).classes('text-sm font-semibold').style('padding-left:25px;padding-top:15px')

        ui.echart({
            'dataset': [{'id': 'ds_all', 'source': source}],
            'legend': {'top': 0, 'data': legend},
            'tooltip': {'trigger': 'axis', 'confine': True, 'axisPointer': {'type': 'cross', 'snap': True}},
            'xAxis': {'type': 'category', 'boundaryGap': False, 'axisLabel': {'hideOverlap': True, 'margin': 6}},
            'yAxis': [
                {'type': 'value', 'axisLabel': {'formatter': f"{{{{value}}}}{y_suffix}"}},
                {'type': 'value', 'position': 'right', 'axisLabel': {'formatter': '{value}%'},
                 'splitLine': {'show': False}},
                {'type': 'value', 'position': 'right', 'offset': 56,
                 'axisLabel': {'formatter': '{value}%'},
                 'splitLine': {'show': False}},
            ],
            'grid': {'left': 40, 'right': 92, 'bottom': 36, 'top': 36, 'containLabel': True},
            'series': series,
        }).classes('w-full h-80').style('width:100%;display:block')
   
        
def kpi_card(title: str, value: str,  sub: str, on_click: Optional[callable] = None):
    with panel() as card:
        if on_click:
            card.classes('cursor-pointer')
            
            async def _click_handler(_: Any) -> None:
                result = on_click()  
                if inspect.isawaitable(result):
                    await result

            card.on('click', _click_handler)
        ui.label(title).classes('text-sm text-gray-500')
        value_label = ui.label(value).classes('text-xl font-semibold')
        ui.html(f'<div class="text-xs text-gray-500">{colorize_numbers(sub)}</div>')
    return value_label

        
def bar_card(title, x, inc, exp, cap=None, unit=' PLN',
             show_profit: bool = True, show_capital: bool = True,
             profit_includes_capital: bool = True,
             stretch: bool = True, full_bleed: bool = True,
             title_padding_left: int = 12):

    n = min(len(x), len(inc), len(exp), len(cap) if cap is not None else len(x))
    x = x[:n]
    inc = inc[:n] 
    exp = exp[:n]
    cap = (cap[:n] if cap is not None else [0]*n)

    exp_neg = [None if v is None else -abs(v) for v in exp]
    profit = [None if (i is None or e is None or c is None)
              else (i - e + (c if profit_includes_capital else 0))
              for i, e, c in zip(inc, exp, cap)]

    series = [
        {
            'name': 'Wydatki',
            'type': 'bar',
            'data': exp_neg,
            'label': {'show': False, 'position': 'inside', 'color': '#fff'},
            'emphasis': {'focus': 'series'},
            'itemStyle': {'color': '#C10015'}
        },
        {
            'name': 'Przychody',
            'type': 'bar',
            'data': inc,
            'label': {'show': False, 'position': 'inside', 'color': '#fff'},
            'emphasis': {'focus': 'series'}
        }
    ]
    legend = ['Wydatki', 'Przychody']

    if show_capital:
        series.append({
            'name': 'Kapitał',
            'type': 'bar',
            'data': cap,
            'label': {'show': False, 'position': 'inside', 'color': '#fff'},
            'emphasis': {'focus': 'series'}
        })
        legend.append('Kapitał')

    if show_profit:
        series.append({
            'name': 'Zysk',
            'type': 'bar',
            'data': profit,
            'label': {'show': False, 'position': 'inside', 'color': '#fff'},
            'emphasis': {'focus': 'series'}
        })
        legend.append('Zysk')

    with panel() as card:
        if stretch:
            card.classes('w-full max-w-none').style('width:100%')
        if full_bleed:
            card.classes('p-0')

        ui.label(title).classes('text-sm font-semibold').style(f'padding-left:{title_padding_left}px;padding-top:6px')

        ui.echart({
            'legend': {'data': legend, 'top': 4}, 
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'shadow'}, 'confine': True},
            'xAxis': {'type': 'category', 'data': x, 'axisTick': {'alignWithLabel': True}},
            'yAxis': {'type': 'value', 'axisLabel': {'formatter': f"{{{{value}}}}{unit}"}, 
                      'splitLine': {'show': True}, 'scale': True},
            'grid': {
                'left': 48, 'right': 24, 'bottom': 28, 'top': 40,
                'containLabel': True
            },
            'barCategoryGap': '10%',  
            'barGap': '8%',            
            'series': series,
        }).classes('w-full h-80').style('width:100%;display:block')
