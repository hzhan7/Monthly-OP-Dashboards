# -*- coding: utf-8 -*-
"""series/fee_rates.csv 的共享读取层：整表读一次 + 季度序列取值 + 季度→月度展开。

## 收敛前的状况

AXP / CME / SCHW / LPLA / HKEX 五页都靠这张表反解「隐含收入」与「有效费率」，
五处各写了一遍同样的六步：

    pd.read_csv(fee_rates.csv)
      → 筛 company == 'X'
      → 筛 metric == 'M'
      → 空了就 SystemExit
      → PeriodIndex(period.str.replace('-', ''), freq='Q')      # '2026-Q2' → 2026Q2
      → set_index('q')['value'].astype(float).sort_index()

而且这张表是 160KB / 1073 行、五页共用的**一张**表，`hkex.rate_series()` 却是
每调用一次就整表重读一次 —— 一次 build 里读了 5 遍（lpla 2 遍）。实测单次解析
约 1.1ms，在 150ms 的 build 里不值一提，所以**这不是为了性能**：五份各自 read_csv
意味着「这张表长什么样、period 列怎么解析、缺了该怎么响」这件事有五个答案，
哪天表结构变一次就要在五个地方各改一遍，而漏掉一处的表现是那一页数字悄悄不对。

## 刻意留在各页、没有收进来的东西

**单位换算与缩放**留在调用方，而且必须显式写出来：

    SCHW / HKEX   rate_series(metric, scale=…)   —— 各自的量纲缩放
    LPLA          rate_series(metric, to='mn')   —— USD_k / USD_mn / USD_bn → mn 的换算表
    CME           rpc_quarterly()                 —— 断言单位必须是 USD_per_contract
    AXP           net_interest_yield_newbasis     —— 季度 yield 直接展开成月度

这几条长得像「都能塞进一个 unit= 参数」，但它们不是同一件事：CME 那条是**断言**
（单位不对就该整页失败），LPLA 那条是**换算**（几种单位都接受、按表换），
SCHW/HKEX 那条是**纯量纲**（bp→% 之类，与 CSV 的 unit 列无关）。
把三种语义压进一个万能参数，下次只改一家就得先想清楚另外两家会不会被带着变 ——
那是把今天的成本挪到明天。所以这里只提供 `series()` 与 `unit()` 两块料，
怎么用是各页自己的口径，写在各页自己的文件里。

msci 也读这张表，但它全程不用 pandas（`csv.DictReader` + `'2026Q2'` 字符串当键，
整个模块没有 import pandas），且只读一次。把它接进来是重写而不是去重，故不动。
"""
import os

import numpy as np
import pandas as pd

import repo

PATH = os.path.join(repo.SERIES, 'fee_rates.csv')

_table = None


def table():
    """整张 fee_rates 表，进程内只读一次。

    读一次就够：这张表在一次 build 里是不变的输入，五页里最多的 hkex 原先读 5 遍
    拿到的是 5 份完全一样的数据。
    """
    global _table
    if _table is None:
        _table = pd.read_csv(PATH)
    return _table


def series(company, metric):
    """(company, metric) 的季度序列，索引 PeriodIndex(freq='Q')，值为 float 并按季升序。

    查不到就 SystemExit —— CONTRACT.md §5 第 5 条「失败要响」：费率缺了，
    这一页的隐含收入整列都是错的，宁可让 monthly_run 记这一家 FAIL。
    """
    d = _rows(company, metric)
    q = pd.PeriodIndex(d['period'].str.replace('-', '', regex=False), freq='Q')
    return pd.Series(d['value'].astype(float).values, index=q).sort_index()


def unit(company, metric):
    """该 (company, metric) 的单位；不唯一就 SystemExit。

    单位不唯一意味着同一条序列里混了两种量纲，任何换算都会算错一半 ——
    这种表必须当场响，不能挑一个用。
    """
    units = set(_rows(company, metric)['unit'].dropna())
    if len(units) != 1:
        raise SystemExit(f'fee_rates.csv 里 {company}/{metric} 单位不唯一: {units}')
    return units.pop()


def _rows(company, metric):
    d = table()
    d = d[(d['company'] == company) & (d['metric'] == metric)]
    if not len(d):
        raise SystemExit(f'fee_rates.csv 里没有 {company}/{metric}')
    return d


def to_monthly(rate_q, month_index):
    """季度序列 → 月度：当季各月用该季的值，最新季之后沿用最后一个已知值。

    「最新季之后沿用」是本仓的常驻口径而不是将就：成交量按月往前走，费率一个季度才
    更新一次，所以最新一两个月的隐含值必然是拿上一季费率外推的。各页把这个落后了
    几个月写进图注（cme 的 _CARRY_TXT、lpla 的 CARRY_M、axp 的 _CARRY 都是这么来的），
    而不是假装没发生。
    """
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(qq, np.nan) for qq in q],
                     index=month_index, dtype=float).ffill()
