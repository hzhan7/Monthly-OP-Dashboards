# -*- coding: utf-8 -*-
"""bridge — 「经营量 x 费率 = 隐含收入」的共用工具。

设计原则（这几条决定了图上必须写什么）：
  1. 费率来自季报，是**季度值**；月度图上用的是「该月所属季度的费率」，
     最新季度之后沿用最后一个已知季度费率 —— 这一步是假设，必须在图注里写明。
  2. 凡是公司自己披露了对应收入的，都配一张「隐含 vs 实际（季度）」验证图。
     桥搭得准不准，看这张图，不看嘴上说。
  3. 任何一张桥出来的图，标题都带 "implied"，图注都以 "Assumption:" 开头。
"""
import os
import numpy as np
import pandas as pd

D = os.path.dirname(os.path.abspath(__file__))


def load_rates(company=None):
    d = pd.read_csv(os.path.join(D, 'data', 'fee_rates.csv'))
    if company:
        d = d[d['company'] == company]
    return d


# 单位换算表：把 fee_rates.csv 里五花八门的单位统一到目标单位。
# 这层是必要的 —— LPL 的收入用「千美元」、MSCI 用「百万美元」，
# 不做归一化就会出现「隐含 450 vs 实际 456,945」这种量级错位。
_SCALE = {
    ('USD_k', 'mn'): 1e-3, ('USD_mn', 'mn'): 1.0, ('USD_bn', 'mn'): 1e3,
    ('HKD_mn', 'mn'): 1.0, ('HKD_bn', 'mn'): 1e3,
    ('USD_k', 'bn'): 1e-6, ('USD_mn', 'bn'): 1e-3, ('USD_bn', 'bn'): 1.0,
    ('HKD_mn', 'bn'): 1e-3, ('HKD_bn', 'bn'): 1.0,
}


def rate_series(company, metric, to=None):
    """取某公司某参数的季度序列，索引为 PeriodIndex(freq='Q')。

    to='mn' / 'bn' 时按 unit 列做单位归一化；单位不在换算表里会直接报错，
    不会静默按原值返回（静默是这类 bug 的温床）。
    """
    d = load_rates(company)
    d = d[d['metric'] == metric].copy()
    if not len(d):
        raise KeyError(f'{company}/{metric} 不在 fee_rates.csv 里')
    d['q'] = pd.PeriodIndex(d['period'].str.replace('-', ''), freq='Q')
    out = d.set_index('q')['value'].astype(float).sort_index()
    if to:
        units = set(d['unit'].dropna())
        if len(units) != 1:
            raise ValueError(f'{company}/{metric} 单位不唯一: {units}')
        u = units.pop()
        if (u, to) not in _SCALE:
            raise ValueError(f'{company}/{metric} 单位 {u} 无法换算到 {to}')
        out = out * _SCALE[(u, to)]
    return out


def to_monthly(rate_q, month_index):
    """季度费率 → 月度：当季各月用该季费率；最新季之后沿用最后一个已知值。"""
    q = pd.PeriodIndex(month_index).asfreq('Q')
    out = pd.Series([rate_q.get(qq, np.nan) for qq in q], index=month_index, dtype=float)
    return out.ffill()


def last_rate_note(rate_q, unit, name):
    """生成图注里那句「费率取自哪一期、是多少、之后如何延用」。"""
    last_q, last_v = rate_q.index[-1], rate_q.iloc[-1]
    return (f'{name} is taken from the quarterly report ({last_q} = {last_v:,.4g} {unit}) '
            f'and held flat for months after that quarter')


def quarterly(s_monthly, how='sum'):
    """月度序列汇总到季度。"""
    g = s_monthly.dropna().groupby(pd.PeriodIndex(s_monthly.dropna().index).asfreq('Q'))
    return (g.sum() if how == 'sum' else g.mean())


def complete_quarters(s_monthly):
    """只保留满 3 个月的季度（不满的季度不能和实际季度收入比）。"""
    cnt = pd.Series(1, index=s_monthly.dropna().index).groupby(
        pd.PeriodIndex(s_monthly.dropna().index).asfreq('Q')).sum()
    return cnt[cnt == 3].index
