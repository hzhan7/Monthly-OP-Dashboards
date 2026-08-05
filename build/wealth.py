# -*- coding: utf-8 -*-
"""财富 / 券商组横截面：SCHW / LPLA / IBKR（+ HOOD，仅在口径可比的图上）。

移植自 build/build_group_wealth.py（matplotlib → PDF），产出 data/wealth.js。

## 横截面页与单票页的三条不同规矩

1. **发布门槛取「共同最新月」，不是各家自己的最新月。**
   各家披露节奏散在次月 1–20 日：IBKR 次月首个交易日、SCHW 次月 12–14 日、
   LPLA 次月中下旬。若每家都画到自己的最新月，同一张图上 IBKR 到 7 月、LPL 到 5 月，
   末端那两个月的「谁强谁弱」全是披露时点造成的假象。所以整页统一截到
   **成员中最慢的那一家**，页脚点名短板是谁、它自己更新到哪个月 ——
   不写这一条，读者会以为整页都是最新的。

2. **共同最新月算不出来时，不写半张页。** 有成员还没建好（CSV 缺失 / 缺列 / 全空）
   就打印说明并**以退出码 0 正常结束**：monthly_run.py 的 build_cross() 会在成员齐了
   之后重跑，这不是失败。

3. **不可比就不入图。** 一张图里少一家，图注必须写清楚为什么少 ——
   横截面页的全部价值就在「这几个数真的能并排放」，硬塞一个口径不同的数比缺一家更糟。

## HOOD 的取舍（本次新增成员）

入图（口径确实可比）：
  · 客户资产 —— HOOD total platform assets ⇄ SCHW/LPL total client assets ⇄ IBKR client equity
  · 净流入   —— HOOD net deposits ⇄ SCHW core NNA ⇄ LPL organic NNA（都是客户净转入，
                都按「当月流量 x 12 / 上月末资产」年化，HOOD 自家披露口径也是这个）
  · 日均交易 —— HOOD DATs（股票+期权+加密之和）⇄ SCHW DATs ⇄ IBKR total client DARTs
                （IBKR 披露的总量口径，含未在 IBKR 清算的客户 —— 与另两家的客户总成交
                笔数可比；IBKR 单页那条 implied cleared DARTs 是另一个更窄的推导口径）
  · 融资余额 —— HOOD margin book ⇄ SCHW month-end margin ⇄ IBKR margin loans

不入图：
  · 客户现金 —— HOOD 把客户现金拆成 cash sweep（扫到合作银行，表外）与 cash and
                deposits（留在券商）两条线，不发布同一口径的合计；取任一条与 LPL 的
                client cash（ICA + MMF + DCA 合计）、IBKR 的 client credits 并排，
                不是漏计就是重复计。故该图仍只有 LPL 与 IBKR 两家。
  · 2018 起的长历史 —— HOOD 的月度经营指标自 2023-04 才有，进不了 2018 基期的重定基图；
                另出一张 2023-04 基期的四家图。

数据源：series/{schw,lpla,ibkr,hood}.csv，均由各家自己的 fetch 模块维护，本脚本只读不写。
所有数值与格式化都在这里算完，页面不做任何计算。构建日期只写文件首行注释，不进 payload。
"""
import datetime
import json
import os
import sys

import numpy as np
import pandas as pd

import payload_guard

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

SRC = ('Source: company monthly disclosures (Schwab Monthly Activity Report, '
       'LPL monthly activity report, IBKR brokerage metrics, Robinhood monthly operating data)')

# 成员定义：ticker → (显示名, 颜色, 该家「有没有数据」的判定列, 是否必需)
# 必需 = 缺了就不出页；HOOD 是后加的成员，缺了就退回原来的三家。
MEMBERS = [
    ('schw', 'Schwab',    'NAVY',  'total_client_assets_usdbn',   True),
    ('lpla', 'LPL',       'RED',   'total_assets_usdbn',          True),
    ('ibkr', 'IBKR',      'MBLUE', 'equity',                      True),
    ('hood', 'Robinhood', 'GREEN', 'total_platform_assets_usdbn', False),
]

# LPL 有机口径：官方在同一页披露的 Acquired NNA，与 build/lpla.py 的 ACQ 表逐条一致。
# 它不是 series/lpla.csv 的一列（月报正文里的一次性说明），所以两处都硬编码，改一处要改两处。
ACQ = {'2023-01': 3.2, '2023-03': 0.5, '2024-04': 5.0, '2024-08': 0.3, '2024-09': 0.3,
       '2024-10': 88.3, '2024-11': 0.8, '2024-12': 0.3, '2025-01': 0.1, '2025-02': 0.7,
       '2025-03': 7.1, '2025-08': 275.0, '2025-12': 2.0}

# 结构性断点：ACQ 里两笔整体并表 —— Atria（2024-10，+$88.3bn，约当月资产的 6%）与
# Commonwealth（2025-08，+$275.0bn，约 14%）。凡是画「as-reported LPL 客户资产」的图
# 都要把它画出来（CONTRACT.md §5.2：口径断点必须画出来，不能靠图注文字提一句就算数）。
# 与 ACQ 挨着放，是因为它们是同一件事的两种用法 —— 改一处必须改另一处。
# 标签点名 LPL：单票页上整幅红线天然只指 LPL，横截面页上四条线并排，不点名会被读成
# 「四家在这里都换了口径」。
ACQ_BREAKS = [(pd.Period('2024-10', 'M'), 'LPL Atria'),
              (pd.Period('2025-08', 'M'), 'LPL Commonwealth')]


def brks(idx, drawn=None, n=None):
    """把结构性断点映射到给定窗口的 x 索引，返回可直接展开进 exhibit dict 的片段。

    窗口盖不到的断点自动省略（各图窗口起点不同、dense_win 还会随披露变动，
    硬编码索引下个月就错位）；一个都盖不到就返回空 dict，图上不画、图注也不会
    声称画了 —— drawn 收集真正画上的 exhibit 编号，图注文案由它生成。"""
    lst = list(idx)
    at = [lst.index(p) for p, _ in ACQ_BREAKS if p in lst]
    lb = [label for p, label in ACQ_BREAKS if p in lst]
    if not at:
        return {}
    if drawn is not None and n is not None:
        drawn.append(n)
    return {'break_at': at, 'break_label': lb}


BRK_DRAWN = []          # 真正画上断点线的 exhibit 编号，供口径说明引用


# ────────────────────────────── 读数据 + 发布门槛 ──────────────────────────────
def load(t, key):
    """读一家的 series CSV。缺文件 / 缺列 / 全空都返回 None —— 由门槛逻辑决定怎么办。"""
    p = os.path.join(SERIES, f'{t}.csv')
    if not os.path.exists(p):
        return None, f'series/{t}.csv 不存在'
    d = pd.read_csv(p)
    if 'month' not in d.columns or key not in d.columns:
        return None, f'series/{t}.csv 缺列 month/{key}'
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    d = d.set_index('month').sort_index()
    for c in d.columns:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    if not len(d[key].dropna()):
        return None, f'series/{t}.csv 的 {key} 全为空'
    return d, None


RAW, LATEST_EACH, blocked, skipped = {}, {}, [], []
for t, name, color, key, need in MEMBERS:
    d, why = load(t, key)
    if d is None:
        (blocked if need else skipped).append((t, why))
        continue
    RAW[t] = d
    LATEST_EACH[t] = d[key].dropna().index[-1]

if blocked:
    # 规矩 2：不写半张页。这不是失败 —— monthly_run 会在成员齐了之后重跑，故退出码 0。
    print('wealth 横截面页跳过：必需成员未就绪 —— ' + '；'.join(f'{t}（{w}）' for t, w in blocked))
    print('已就绪：' + (', '.join(f'{t} → {LATEST_EACH[t]}' for t in RAW) or '无'))
    print('共同最新月无法确定，不生成 data/wealth.js（成员齐了之后 monthly_run 会重跑）')
    sys.exit(0)

LATEST = min(LATEST_EACH.values())
NAME = {t: n for t, n, _c, _k, _q in MEMBERS}
COLOR = {t: c for t, _n, c, _k, _q in MEMBERS}
LAGGARDS = sorted(t for t, p in LATEST_EACH.items() if p == LATEST)
HAS = set(RAW)


def col(t, c):
    """取某家的一列并截到共同最新月；该家不在场时返回全 NaN。"""
    if t not in RAW or c not in RAW[t].columns:
        return None
    return RAW[t][c].loc[:LATEST]


# ────────────────────────────── 组装可比序列 ──────────────────────────────
IDX = pd.period_range(min(RAW[t].index[0] for t in RAW), LATEST, freq='M')
df = pd.DataFrame(index=IDX)


def put(name, s):
    df[name] = s.reindex(IDX) if s is not None else np.nan


put('schw_assets', col('schw', 'total_client_assets_usdbn'))
put('lpla_assets', col('lpla', 'total_assets_usdbn'))
put('ibkr_assets', col('ibkr', 'equity'))
put('hood_assets', col('hood', 'total_platform_assets_usdbn'))

put('schw_flow', col('schw', 'core_nna_usdbn'))
_lp_nna = col('lpla', 'nna_total_usdbn')
if _lp_nna is not None:
    _acq = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(_lp_nna.index).fillna(0.0)
    put('lpla_flow', _lp_nna - _acq)
    put('lpla_nna_raw', _lp_nna)
    put('lpla_acq', _acq)
else:
    put('lpla_flow', None)
put('hood_flow', col('hood', 'net_deposits_usdbn'))

put('lpla_cash', col('lpla', 'client_cash_usdbn'))
put('ibkr_cash', col('ibkr', 'credits'))

put('schw_margin', col('schw', 'margin_balances_usdbn'))
put('ibkr_margin', col('ibkr', 'margin'))
put('hood_margin', col('hood', 'margin_book_usdbn'))

put('schw_dats', col('schw', 'dats_k'))
put('ibkr_dats', col('ibkr', 'darts'))
# HOOD 官方单位是 mn trades/day，三条分市场线；这里换成 k 与另外两家同轴
_he, _ho, _hc = (col('hood', 'dats_equity_mn'), col('hood', 'dats_options_mn'),
                 col('hood', 'dats_crypto_mn'))
put('hood_dats', (_he + _ho + _hc) * 1000.0 if _he is not None else None)
put('hood_dats_mn', (_he + _ho + _hc) if _he is not None else None)

put('ibkr_accounts', col('ibkr', 'accounts'))
put('hood_accounts', col('hood', 'funded_customers_mn'))

# 派生：年化有机增速（当月净流入 x 12 / 上月末资产）、资产 y/y、账户 y/y、
#       融资余额与客户现金占客户资产的比重
for t in ('schw', 'lpla', 'hood'):
    df[f'{t}_org'] = df[f'{t}_flow'] * 12 / df[f'{t}_assets'].shift(1) * 100
for t in ('schw', 'lpla', 'ibkr', 'hood'):
    df[f'{t}_yoy'] = df[f'{t}_assets'].pct_change(12) * 100
for t in ('ibkr', 'hood'):
    df[f'{t}_acct_yoy'] = df[f'{t}_accounts'].pct_change(12) * 100
for t in ('schw', 'ibkr', 'hood'):
    df[f'{t}_mgn_pct'] = df[f'{t}_margin'] / df[f'{t}_assets'] * 100
for t in ('lpla', 'ibkr'):
    df[f'{t}_cash_pct'] = df[f'{t}_cash'] / df[f'{t}_assets'] * 100


# ────────────────────────────── 格式化零件 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def comma(v, d=0):
    return f'{v:,.{d}f}'


def money(v, d=0):
    return '$' + comma(v, d)


def L(a):
    """序列 → JSON 数组；非有限值一律写 null（图与表都断开，不画假点）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def has(name, idx=None):
    """该列在（指定窗口的）范围内是否真有值。没有就不入图，而不是画一条空线。"""
    s = df[name] if idx is None else df[name].reindex(idx)
    return bool(np.isfinite(s.values.astype(float)).any())


def sr(items, idx):
    """把 (ticker, 列名, 图例名) 列表变成 series 数组，顺带返回入图 / 未入图的公司名。

    统一在这里做「空序列剔除」：某家在窗口内不是**逐点都有值**时不入图（原因见
    dense_win 的注释），并把它算进「未入图」，图注里点名。"""
    out, inc, exc = [], [], []
    for t, cname, legend in items:
        s = df[cname].reindex(idx) if (t in HAS and cname in df.columns) else None
        if s is None or not np.isfinite(s.values.astype(float)).all():
            exc.append(NAME.get(t, t.upper()))
            continue
        out.append({'name': legend, 'color': COLOR[t], 'values': L(s.values)})
        inc.append(NAME[t])
    return out, inc, exc


def dense_win(items, win=None):
    """`lines_endlabels` 能吃的最长窗口：从共同最新月往回，各线都逐点有值的那一段。

    这是图表引擎的硬约束，不是排版偏好：该图型两端要标数值（`values[0]` / `values[n-1]`
    直接进格式器）、线本身又是 Catmull-Rom 平滑插值的（`smooth()` 不跳空值），
    所以窗口里任何一条线缺一个点，整张图都画不出来（页面会在这里抛异常、
    后面所有 exhibit 一张都不渲染）。

    各家的披露起点并不齐 —— Schwab 的月末融资余额与 DATs 都是 2026-01 的月报才开始发、
    滚动表只回溯到 2025-01，而 IBKR 有 2016 年起的历史。所以窗口按**最晚开始披露的那条线**
    截，而不是把缺的月份补零（补零会画出一条「余额从 0 长起来」的假线）。
    在 LATEST 就没有值的列直接不入图。"""
    win = win or WIN
    cols = [c for t, c, _ in items
            if t in HAS and c in df.columns and np.isfinite(df[c].loc[LATEST])]
    if not cols:
        return IDX[-1:]
    k = 0
    for p in reversed(IDX[-win:]):
        if not all(np.isfinite(df[c].loc[p]) for c in cols):
            break
        k += 1
    return IDX[-max(k, 1):]


def win_note(idx):
    if len(idx) >= WIN:
        return ''
    return (f'窗口取 {mlab(idx[0])}–{mlab(idx[-1])}（{len(idx)} 个月，'
            f'短于本页默认的 {WIN} 个月）：本图型两端要标数值、线又是平滑插值的，'
            '窗口内任一条线缺一个点就整张画不出来，所以起点取「各线都已开始披露」的那个月。'
            '缺的是披露，不是零 —— 不补零、不外推。')


def firms_note(inc, exc, why=''):
    s = '本图含 ' + ' / '.join(inc) + '。'
    if exc:
        s += '未入图：' + ' / '.join(exc) + '。'
        if why:
            s += why
    return s


def xls(idx, step=None):
    return [mlab(p) for p in idx]


WIN = 25                                   # 近期多线图窗口（同原 deck 的 win=25）
XL = [mlab(p) for p in IDX[-13:]]
XL_LONG = [mlab(p) for p in IDX]
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── Exhibit 1：汇总表 ──────────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def _lp_rank_txt():
    """LPL as-reported y/y 与剔并购后的 y/y、以及它与 Schwab 的名次关系。

    断点线告诉读者「这里不可比」，但不告诉他不可比到什么程度。当期这两个数横跨
    Schwab 时，名次是反的 —— 这句话必须给出数字，否则读者只会照着端点标签读
    LPL +38% > Schwab +27%。算不出来（缺月、缺 Schwab）就返回空串，不写半句。"""
    try:
        lp_now, lp_ago = float(df['lpla_assets'].loc[CUR]), float(df['lpla_assets'].loc[YAG])
        sc = float(df['schw_yoy'].loc[CUR])
    except (KeyError, TypeError, ValueError):
        return '', None
    if not all(np.isfinite(v) for v in (lp_now, lp_ago, sc)) or lp_ago == 0:
        return '', None
    t12 = sum(v for k, v in ACQ.items() if YAG < pd.Period(k, 'M') <= CUR)
    raw, exq = (lp_now / lp_ago - 1) * 100, ((lp_now - t12) / lp_ago - 1) * 100
    txt = (f'{mlab(CUR)} 的 LPL 读数为 <b>{raw:+.1f}%</b>，剔掉滚动 12 个月的 Acquired NNA'
           f'（${t12:,.1f}bn）之后是 <b>{exq:+.1f}%</b>，'
           + (f'<b>低于</b> Schwab 的 {sc:+.1f}% —— 名次是反的。'
              if exq < sc else f'仍高于 Schwab 的 {sc:+.1f}%。'))
    return txt, exq


LP_RANK_TXT, LP_YOY_EX = _lp_rank_txt()


def cell(v, d, kind):
    if v is None or not np.isfinite(v):
        return '—'
    return money(v, d) if kind == '$' else (f'{v:,.{d}f}%' if kind == '%' else comma(v, d))


def chg(a, b, mode, d, kind):
    """m/m、y/y 单元格。比率类用 pp/bp（GS LPLA 规矩 2），不用百分比变化。"""
    if a is None or b is None or not (np.isfinite(a) and np.isfinite(b)):
        return {'v': ''}
    if mode == 'pp':
        v = a - b
        txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
    else:
        if b == 0 or a * b < 0:
            return {'v': ''}
        v = a / b - 1
        txt = f'{v * 100:+.1f}%'
    return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}


def pctile36(s):
    """近 36 个月分位。单调序列（几乎只增不减）留空 —— 分位恒为 100，是噪音不是信息。"""
    c = s.dropna()
    if not len(c):
        return {'v': ''}
    h = c.iloc[-36:]
    if len(h) < 8:
        return {'v': ''}
    cur = float(c.iloc[-1])
    dd = np.diff(h.values)
    if len(dd) and float((dd >= 0).sum()) / len(dd) >= 0.90:
        return {'v': ''}
    p = float((h.values < cur).sum()) / max(1, len(h) - 1) * 100
    return {'v': f'{p:.0f}', 'cls': 'hi' if p >= 66 else ('lo' if p <= 33 else '')}


SUM_ROWS = [
    ('group', 'Client assets ($bn) —— 同一单位，直接可比'),
    ('row', 'schw', 'Schwab total client assets', 'schw_assets', 0, '$', 'ratio'),
    ('row', 'lpla', 'LPL total client assets（含并购转入）', 'lpla_assets', 0, '$', 'ratio'),
    ('row', 'ibkr', 'IBKR client equity', 'ibkr_assets', 0, '$', 'ratio'),
    ('row', 'hood', 'Robinhood total platform assets', 'hood_assets', 0, '$', 'ratio'),
    ('group', 'Organic growth（%，年化）'),
    ('row', 'schw', 'Schwab core NNA growth', 'schw_org', 2, '%', 'pp'),
    ('row', 'lpla', 'LPL organic NNA growth', 'lpla_org', 2, '%', 'pp'),
    ('row', 'hood', 'Robinhood net deposit growth', 'hood_org', 2, '%', 'pp'),
    ('row', 'ibkr', 'IBKR account growth, y/y', 'ibkr_acct_yoy', 1, '%', 'pp'),
    ('group', 'Balance sheet ($bn)'),
    ('row', 'lpla', 'LPL client cash', 'lpla_cash', 1, '$', 'ratio'),
    ('row', 'ibkr', 'IBKR client credits', 'ibkr_cash', 1, '$', 'ratio'),
    ('row', 'schw', 'Schwab margin balances', 'schw_margin', 1, '$', 'ratio'),
    ('row', 'ibkr', 'IBKR margin loans', 'ibkr_margin', 1, '$', 'ratio'),
    ('row', 'hood', 'Robinhood margin book', 'hood_margin', 1, '$', 'ratio'),
    ('group', 'Activity（k trades / day）'),
    ('row', 'schw', 'Schwab DATs', 'schw_dats', 0, '', 'ratio'),
    ('row', 'ibkr', 'IBKR total client DARTs（含未清算）', 'ibkr_dats', 0, '', 'ratio'),
    ('row', 'hood', 'Robinhood DATs（股票+期权+加密）', 'hood_dats', 0, '', 'ratio'),
]

srows = []
for r in SUM_ROWS:
    if r[0] == 'group':
        srows.append({'kind': 'group', 'label': r[1]})
        continue
    _, t, lab, cname, d, kind, mode = r
    if t not in HAS or cname not in df.columns or not has(cname):
        continue
    s = df[cname]
    get = lambda p: (float(s.loc[p]) if p in s.index and np.isfinite(s.loc[p]) else None)
    c, p1, p12 = get(CUR), get(PRV), get(YAG)
    srows.append({'label': lab, 'cells': [
        {'v': cell(c, d, kind)}, {'v': cell(p1, d, kind)}, {'v': cell(p12, d, kind)},
        chg(c, p1, mode, d, kind), chg(c, p12, mode, d, kind), pctile36(s)]})

LAG = ' / '.join(NAME[t] for t in LAGGARDS)      # 短板：共同最新月就等于它自己的最新月
summary = {
    'title': f'Wealth and brokerage group —— {mlab(LATEST)}（共同最新月）',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': (f'整张表统一截到<b>共同最新月 {mlab(LATEST)}</b>，由最慢的成员 {LAG} 决定；'
             + '；'.join(f'{NAME[t]} 自身已更新到 {mlab(LATEST_EACH[t])}'
                         for t in RAW if LATEST_EACH[t] != LATEST)
             + '，这些更新的月份本页一律不画（见页脚）。'
             'Schwab 月报不单列客户现金、LPL 既不披露融资余额也不披露交易笔数、'
             'IBKR 不披露净新增资产（只披露净新增账户），故这些行只有披露该项的公司。'
             '比率类指标（年化有机增速、账户增速）的差异用 pp/bp，不用百分比变化；'
             'Robinhood DATs 官方单位为 mn，此处 x1,000 换成 k 与另两家同轴（核对表仍保留 mn 原始单位）。'
             'IBKR 那行是公司披露的 <b>Total Client DARTs</b>（含通过 IBKR 执行但不在 IBKR 清算的客户），'
             '与 Schwab / Robinhood 的客户总成交笔数同口径；公司另披露的 Cleared Avg. DART per Account '
             '推导出的 cleared DARTs 约为此值的 85%，见 IBKR 单页 Exhibit 4/18，两者不要混读。'
             '3Y %ile = 当月读数在最近 36 个月里高于多少个百分比的观测。'
             '判据同全站：36 个月里 ≥90% 的月环比不降就把该行分位留空 —— '
             '几乎只增不减的序列分位恒为 100，是噪音不是信息。'
             '存量类各行本轮未触发该判据（区间内有下跌月），分位照算，'
             '但读到 100 时要知道它只是说「当月是近三年最高」，不代表动能。'),
}


# ────────────────────────────── Exhibit 2..N ──────────────────────────────
ex = []
GATE = (f'本页所有图统一截到共同最新月 {mlab(LATEST)}；'
        f'{LAG} 是短板，其余各家更新更早的月份本页不画。')


def rebase(cname, base):
    """重定基到 100。基期本身缺值时整条不画 —— 拿一个 NaN 当分母会造出一整条假线。"""
    s = df[cname]
    if base not in s.index or not np.isfinite(s.loc[base]):
        return None
    return s / float(s.loc[base]) * 100


# ── Exhibit 2：客户资产 2018 基期重定基（HOOD 那时还没有月度披露）──
B18 = max(pd.Period('2018-07', 'M'), IDX[0])
I18 = pd.period_range(B18, LATEST, freq='M')
s2, inc2, exc2 = [], [], []
for t in ('schw', 'lpla', 'ibkr', 'hood'):
    r = rebase(f'{t}_assets', B18) if t in HAS else None
    if r is None or not np.isfinite(r.reindex(I18).values.astype(float)).any():
        exc2.append(NAME.get(t, t.upper()))
        continue
    s2.append({'name': NAME[t], 'color': COLOR[t], 'values': L(r.reindex(I18).values)})
    inc2.append(NAME[t])
ex.append({
    'n': 2, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I18),
    'xstep': max(1, len(I18) // 14),
    'title': f'Client assets since {mlab(B18)}, rebased to 100',
    'ylab': f'index, {mlab(B18)} = 100',
    'series': s2,
    **brks(I18, BRK_DRAWN, 2),
    'note': (firms_note(inc2, exc2,
                        'Robinhood 的月度经营指标自 2023-04 才有，进不了 2018 基期的图 —— '
                        '把它从自己的首月当 100 起画，会与另外三家比出一个纯属基期不同的假斜率；'
                        '四家同基期的版本见下一张。')
             + '<b>红色竖虚线 = LPL 的两次整体并表</b>（2024-10 Atria +$88.3bn、'
             '2025-08 Commonwealth +$275.0bn）：从那一期起 LPL 这条线与左侧不可比，'
             '另外三家不含并购、不受影响。重定基图上并购是<b>永久抬升</b>的 —— '
             '断点右侧的全部水平差里有一块不是自己长出来的。' + GATE),
})

# ── Exhibit 3：客户资产 2023-04 基期重定基（四家同基期）──
B23 = max(pd.Period('2023-04', 'M'), IDX[0])
I23 = pd.period_range(B23, LATEST, freq='M')
s3, inc3, exc3 = [], [], []
for t in ('schw', 'lpla', 'ibkr', 'hood'):
    r = rebase(f'{t}_assets', B23) if t in HAS else None
    if r is None or not np.isfinite(r.reindex(I23).values.astype(float)).any():
        exc3.append(NAME.get(t, t.upper()))
        continue
    s3.append({'name': NAME[t], 'color': COLOR[t], 'values': L(r.reindex(I23).values)})
    inc3.append(NAME[t])
ex.append({
    'n': 3, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I23),
    'xstep': max(1, len(I23) // 14),
    'title': f'Client assets since {mlab(B23)}, rebased to 100 —— 四家同基期',
    'ylab': f'index, {mlab(B23)} = 100',
    'series': s3,
    **brks(I23, BRK_DRAWN, 3),
    'note': (firms_note(inc3, exc3)
             + f'基期取 {mlab(B23)}（Robinhood 月度经营指标的首月），四家从同一天起跑，'
             '斜率之差才是真的增长之差。口径：Schwab / LPL 为 total client assets，'
             'IBKR 为 client equity，Robinhood 为 total platform assets —— '
             '都是「客户放在这家平台上的资产总额」，可直接并排。'
             '<b>红色竖虚线 = LPL 的两次整体并表</b>（2024-10 Atria +$88.3bn、'
             '2025-08 Commonwealth +$275.0bn），只影响 LPL 这一条线：'
             '断点右侧 LPL 与另外三家的斜率差里有一块是买来的，不是长出来的。'
             '有机口径见 Exhibit 5。' + GATE),
})

# ── Exhibit 4：客户资产 y/y ──
_i4 = dense_win([(t, f'{t}_yoy', '') for t in ('schw', 'lpla', 'ibkr', 'hood')])
s4, inc4, exc4 = sr([(t, f'{t}_yoy', NAME.get(t, t.upper()))
                     for t in ('schw', 'lpla', 'ibkr', 'hood')], _i4)
ex.append({
    'n': 4, 'kind': 'lines_endlabels', 'fmt': 'pct0', 'xlabels': xls(_i4), 'xstep': 2,
    'title': 'Client asset growth, y/y', 'ylab': '% y/y', 'zero_line': True,
    'series': s4,
    **brks(_i4, BRK_DRAWN, 4),
    'note': (firms_note(inc4, exc4)
             + '<b>红色竖虚线 = LPL 的两次整体并表</b>（2024-10 Atria +$88.3bn、'
             '2025-08 Commonwealth +$275.0bn），只影响 LPL 这一条线，另外三家不受影响。'
             '并购转入不是有机增长，跳升起的 12 个月里 LPL 的 y/y 与另外三家不可比。'
             + LP_RANK_TXT + '有机口径见 Exhibit 5。' + win_note(_i4) + GATE),
})

# ── Exhibit 5：年化有机增速（净流入口径三家）──
_IT5 = [('schw', 'schw_org', 'Schwab core NNA'),
        ('lpla', 'lpla_org', 'LPL organic NNA'),
        ('hood', 'hood_org', 'Robinhood net deposits')]
_i5 = dense_win(_IT5)
s5, inc5, exc5 = sr(_IT5, _i5)
ex.append({
    'n': 5, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'yfmt': 'pct0',
    'xlabels': xls(_i5), 'xstep': 2,
    'title': 'Annualised organic growth: Schwab vs. LPL vs. Robinhood',
    'ylab': '% annualised', 'zero_line': True,
    'series': s5,
    'note': (firms_note(inc5, exc5,
                        'IBKR 不披露净新增资产，只披露净新增账户，所以它的增速看下一张图。')
             + '三家都是<b>当月净流入 x 12 ÷ 上月末客户资产</b>（GS LPLA 版式的流量口径规矩：'
             '流量类不算环比百分比，分母是上个月的流量、一个月的噪音会被放大成趋势）。'
             'LPL 已按官方同页披露的 Acquired NNA 剔除并购转入；'
             'Robinhood 的 net deposits 是客户净转入（含现金与证券转入），'
             '与 Schwab 的 core NNA、LPL 的 organic NNA 是同一个经济含义，但三家的剔除规则各自不同'
             '（Schwab 2025 年把单一客户的剔除门槛从 $10bn 提到 $25bn）。' + win_note(_i5) + GATE),
})

# ── Exhibit 6：账户数增速（只有 IBKR 与 HOOD 披露存量账户数）──
_IT6 = [('ibkr', 'ibkr_acct_yoy', 'IBKR accounts'),
        ('hood', 'hood_acct_yoy', 'Robinhood funded customers')]
_i6 = dense_win(_IT6)
s6, inc6, exc6 = sr(_IT6, _i6)
ex.append({
    'n': 6, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'yfmt': 'pct0',
    'xlabels': xls(_i6), 'xstep': 2,
    'title': 'Account growth, y/y: IBKR vs. Robinhood', 'ylab': '% y/y',
    'series': s6,
    'note': (firms_note(inc6, exc6,
                        'Schwab 只披露当月<b>新开</b>经纪账户（流量），不披露账户存量；'
                        'LPL 披露的是投顾人数（advisor count）而不是账户数 —— '
                        '两者都不能与「账户存量的 y/y」并排，所以不入图。')
             + 'IBKR 的口径是 total accounts，Robinhood 是 funded customers（有入金的客户数），'
             '一个数账户、一个数人，绝对水平不可比，但增速的方向与幅度可比。' + win_note(_i6) + GATE),
})

# ── Exhibit 7：融资余额 ──
_IT7 = [('schw', 'schw_margin', 'Schwab month-end margin'),
        ('ibkr', 'ibkr_margin', 'IBKR margin loans'),
        ('hood', 'hood_margin', 'Robinhood margin book')]
_i7 = dense_win(_IT7)
s7, inc7, exc7 = sr(_IT7, _i7)
_schw_mgn0 = df['schw_margin'].dropna()
ex.append({
    'n': 7, 'kind': 'lines_endlabels', 'fmt': 'usd0', 'xlabels': xls(_i7), 'xstep': 2,
    'title': 'Margin balances: Schwab vs. IBKR vs. Robinhood', 'ylab': '$bn',
    'series': s7,
    'note': (firms_note(inc7, exc7, 'LPL 不披露融资余额。')
             + '三家都是客户融资余额（月末口径），但 Schwab 的数含 short credits、'
             '另两家不含。Schwab 自 2026-01 的月报才开始披露月末融资余额，其 13 个月滚动表回溯至 '
             f'{mlab(_schw_mgn0.index[0]) if len(_schw_mgn0) else "—"}，'
             '所以本图窗口从那里起。' + win_note(_i7) + GATE),
})

# ── Exhibit 8：客户现金（HOOD 口径不可比，只两家）──
_IT8 = [('lpla', 'lpla_cash', 'LPL client cash'),
        ('ibkr', 'ibkr_cash', 'IBKR client credits')]
_i8 = dense_win(_IT8)
s8, inc8, exc8 = sr(_IT8, _i8)
ex.append({
    'n': 8, 'kind': 'lines_endlabels', 'fmt': 'usd0', 'xlabels': xls(_i8), 'xstep': 2,
    'title': 'Client cash: LPL vs. IBKR', 'ylab': '$bn',
    'series': s8,
    'note': (firms_note(inc8, exc8)
             + '<b>为什么少两家：</b>Schwab 的月报根本不单列客户现金；'
             'Robinhood 把客户现金拆成 cash sweep（扫到合作银行、表外）与 cash and deposits'
             '（留在券商）两条线，不发布同一口径的合计 —— 取任一条与 LPL 的 client cash'
             '（ICA + 货基 + DCA 合计）、IBKR 的 client credits 并排，不是漏计就是重复计，'
             '所以宁可这张图只有两家。这两条线都是净利息收入的核心驱动。' + win_note(_i8) + GATE),
})

# ── Exhibit 9：日均交易笔数 ──
_IT9 = [('schw', 'schw_dats', 'Schwab DATs'),
        ('ibkr', 'ibkr_dats', 'IBKR total client DARTs'),
        ('hood', 'hood_dats', 'Robinhood DATs')]
_i9 = dense_win(_IT9)
s9, inc9, exc9 = sr(_IT9, _i9)
ex.append({
    'n': 9, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': xls(_i9), 'xstep': 2,
    'title': 'Daily average trades: Schwab vs. IBKR vs. Robinhood',
    'ylab': 'k trades / day',
    'series': s9,
    'note': (firms_note(inc9, exc9, 'LPL 不披露交易笔数。')
             + '<b>三家的「一笔」不是同一件事：</b>Schwab DATs 数客户成交笔数；'
             'IBKR 这条线用的是公司披露的 <b>Total Client DARTs</b>，'
             '含通过 IBKR 执行但不在 IBKR 清算的 introducing-broker 客户；'
             'Robinhood 是股票 + 期权 + 加密三个市场的 DATs 之和（官方单位 mn，此处 x1,000 换成 k）。'
             '所以水平值只能当量级读，方向与拐点才是可比的信息。'
             '<b>这里取总量是为了与另两家的客户总成交笔数可比</b> —— IBKR 另按 '
             'Cleared Avg. DART per Account 推导过一条更窄的 implied cleared DARTs'
             '（见 IBKR 单页 Exhibit 4/18），约为本图数值的 85%，两条线不要混读；'
             '「cleared」修饰的是账户（IBKR 自清算的账户），不是订单。'
             'Schwab 的 DATs 自 2026-01 的月报才有，滚动表回溯至 '
             f'{mlab(df["schw_dats"].dropna().index[0]) if has("schw_dats") else "—"}，'
             '所以本图窗口从那里起。' + win_note(_i9) + GATE),
})

# ── Exhibit 10：资产负债表项目 2019 基期重定基 ──
B19 = max(pd.Period('2019-01', 'M'), IDX[0])
I19 = pd.period_range(B19, LATEST, freq='M')
BS10 = [('ibkr', 'ibkr_margin', 'IBKR margin', 'MBLUE'),
        ('ibkr', 'ibkr_cash', 'IBKR credits', 'BLUE'),
        ('lpla', 'lpla_cash', 'LPL client cash', 'RED')]
s10, inc10, exc10 = [], [], []
for t, cname, legend, c in BS10:
    r = rebase(cname, B19) if t in HAS else None
    if r is None or not np.isfinite(r.reindex(I19).values.astype(float)).any():
        exc10.append(legend)
        continue
    s10.append({'name': legend, 'color': c, 'values': L(r.reindex(I19).values)})
    inc10.append(legend)
ex.append({
    'n': 10, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I19),
    'xstep': max(1, len(I19) // 14),
    'title': f'Balance-sheet items since {mlab(B19)}, rebased to 100',
    'ylab': f'index, {mlab(B19)} = 100',
    'series': s10,
    'note': (firms_note(inc10, exc10)
             + '融资余额是周期项、客户现金是利率敏感项，重定基之后能看出两者的相位差。'
             'Schwab 的月末融资余额只有 2025-01 起的历史、Robinhood 只有 2023-04 起的历史，'
             f'都盖不到 {mlab(B19)} 的基期，硬画等于拿一个空值当分母，所以不入这张长历史图；'
             '它们的近期水平见 Exhibit 7。' + GATE),
})

# ── Exhibit 11：融资余额 / 客户资产（杠杆强度，横截面归一化）──
_IT11 = [('schw', 'schw_mgn_pct', 'Schwab'),
         ('ibkr', 'ibkr_mgn_pct', 'IBKR'),
         ('hood', 'hood_mgn_pct', 'Robinhood')]
_i11 = dense_win(_IT11)
s11, inc11, exc11 = sr(_IT11, _i11)
ex.append({
    'n': 11, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'xlabels': xls(_i11), 'xstep': 2,
    'title': 'Margin balances as % of client assets', 'ylab': '% of client assets',
    'series': s11,
    'note': (firms_note(inc11, exc11, 'LPL 不披露融资余额。')
             + '把融资余额按各自的客户资产归一化 —— 这是横截面页真正独有的读法：'
             '绝对额只说明谁大，占比说明<b>同样一块客户资产上，谁的客户加了更多杠杆</b>。'
             '注意分母口径三家略有差异（见 Exhibit 3 的说明），且 Schwab 的分子含 short credits，'
             '所以水平值有系统性偏差，趋势与相对位次才是要看的。' + win_note(_i11) + GATE),
})

# ── Exhibit 12：客户现金 / 客户资产（利率敏感度，横截面归一化）──
_IT12 = [('lpla', 'lpla_cash_pct', 'LPL'),
         ('ibkr', 'ibkr_cash_pct', 'IBKR')]
_i12 = dense_win(_IT12)
s12, inc12, exc12 = sr(_IT12, _i12)
ex.append({
    'n': 12, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'xlabels': xls(_i12), 'xstep': 2,
    'title': 'Client cash as % of client assets', 'ylab': '% of client assets',
    'series': s12,
    'note': (firms_note(inc12, exc12)
             + '现金占比是净利息收入的敏感度指标：占比下行意味着客户把现金投出去了，'
             '同样的利率环境下 NII 的基数在缩。少的两家与 Exhibit 8 同因 —— '
             'Schwab 月报不单列客户现金，Robinhood 的客户现金拆成两条不可合计的线。' + win_note(_i12) + GATE),
})

# ── Exhibit 13..N：各家客户资产 y/y 的 月 x 年 热力矩阵 ──
def heat(n, t, title, extra=''):
    s = df[f'{t}_yoy'].dropna()
    if not len(s):
        return None
    yrs = sorted({p.year for p in s.index})[-7:]
    matrix = []
    for y in yrs:
        row = []
        for m in range(1, 13):
            p = pd.Period(f'{y}-{m:02d}', 'M')
            row.append(round(float(s.loc[p]), 6)
                       if p in s.index and np.isfinite(s.loc[p]) else None)
        matrix.append(row)
    return {
        'n': n, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0',
        'title': title, 'rows': [str(y) for y in yrs], 'cols': MONTHS,
        'matrix': matrix, 'legend': title, 'row_head': '年',
        'note': ('绿 = 增长更快。色标取全部有限值的 5/95 分位，一两个离群月不会把整表压平。'
                 + extra + GATE),
    }


_hn = 13
for _t, _title, _extra in [
    ('schw', 'Schwab client assets y/y (%)', ''),
    ('lpla', 'LPL client assets y/y (%)', '2024-10（Atria +$88.3bn）与 '
                                          '2025-08（Commonwealth +$275.0bn）起的 12 个格子带着并购转入，'
                                          '不是有机增长；热力矩阵这个图型画不了断点竖线，'
                                          '带断点线的同口径图见 Exhibit 4，剔并购后的有机口径见 Exhibit 5。'),
    ('ibkr', 'IBKR client equity y/y (%)', ''),
    ('hood', 'Robinhood platform assets y/y (%)', 'Robinhood 的月度披露自 2023-04 起，'
                                                  '所以 y/y 自 2024-04 才有，矩阵行数少于另外三家。'),
]:
    if _t not in HAS:
        continue
    _h = heat(_hn, _t, _title, _extra)
    if _h:
        ex.append(_h)
        _hn += 1


# 汇总表画不了断点线（表格没有 x 轴），所以 LPL 那一行的并购口径只能写进表注。
# 放在这里而不是 summary 的字面量里，是因为 BRK_DRAWN 要等 exhibit 全部建完才有值 ——
# 图注不能声称画了一条其实没画的线。
if LP_RANK_TXT:
    summary['note'] += (
        'LPL 那行是 as-reported 口径，含 Atria（2024-10 +$88.3bn）与 '
        'Commonwealth（2025-08 +$275.0bn）两次整体并表，表格画不出断点线：'
        + LP_RANK_TXT
        + (f'带断点线的同口径图见 Exhibit {"、".join(str(n) for n in BRK_DRAWN)}，'
           if BRK_DRAWN else '')
        + '剔并购后的有机口径见 Exhibit 5。')


# ────────────────────────────── 核对表 ──────────────────────────────
T13 = df.iloc[-13:]


def tcell(v, d=1):
    return None if v is None or not np.isfinite(v) else comma(float(v), d)


TCOLS = [
    ('schw', 'SCHW client assets ($bn)', 'sa', 'schw_assets', 1),
    ('lpla', 'LPL client assets ($bn)', 'la', 'lpla_assets', 1),
    ('ibkr', 'IBKR client equity ($bn)', 'ia', 'ibkr_assets', 1),
    ('hood', 'HOOD platform assets ($bn)', 'ha', 'hood_assets', 1),
    ('schw', 'SCHW core NNA ($bn)', 'sf', 'schw_flow', 1),
    ('lpla', 'LPL NNA total, as reported ($bn)', 'lf', 'lpla_nna_raw', 1),
    ('lpla', 'LPL acquired NNA ($bn)', 'lq', 'lpla_acq', 1),
    ('hood', 'HOOD net deposits ($bn)', 'hf', 'hood_flow', 1),
    ('schw', 'SCHW DATs (k)', 'sd', 'schw_dats', 0),
    ('ibkr', 'IBKR total client DARTs (k)', 'id', 'ibkr_dats', 0),
    ('hood', 'HOOD DATs (mn)', 'hd', 'hood_dats_mn', 1),
]
TCOLS = [c for c in TCOLS if c[0] in HAS and c[3] in df.columns and has(c[3])]

table = {
    'n': _hn,
    'title': f'近 13 个月跨公司核对表（各家官方原始单位，未换算，统一截至 {mlab(LATEST)}）',
    'idx': '月份',
    'cols': [[c[1], c[2]] for c in TCOLS],
    'rows': [dict({'xl': mlab(p)},
                  **{c[2]: tcell(r[c[3]], c[4]) for c in TCOLS})
             for p, r in T13.iterrows()],
}


# ────────────────────────────── 口径与方法说明 ──────────────────────────────
def _v(cname, d=1, kind=''):
    s = df[cname].dropna()
    if not len(s):
        return '—'
    return cell(float(s.iloc[-1]), d, kind)


_others = [t for t in RAW if LATEST_EACH[t] != LATEST]
notes = [
    f'<b>发布门槛：共同最新月，不是各家自己的最新月。</b>本页统一截到 <b>{mlab(LATEST)}</b>，'
    f'由成员中最慢的 {LAG} 决定。'
    + ('各家自身的最新月：'
       + '；'.join(f'{NAME[t]} {mlab(LATEST_EACH[t])}' for t in sorted(RAW)) + '。'
       if RAW else '')
    + ('其中 ' + '、'.join(f'{NAME[t]}（已到 {mlab(LATEST_EACH[t])}）' for t in _others)
       + ' 更新更早的月份<b>本页一律不画</b>——各家披露节奏散在次月 1–20 日，'
         '若每家都画到自己的最新月，末端那几个月的「谁强谁弱」全是披露时点造成的假象。'
       if _others else '本次四家的最新月一致，无短板。'),

    '<b>成员没齐就不出页。</b>必需成员（Schwab / LPL / IBKR）的 series CSV 缺失、缺列或全空时，'
    '本脚本打印说明并以退出码 0 正常结束，不写半张页 —— '
    '<code>monthly_run.py</code> 的 <code>build_cross()</code> 会在成员齐了之后重跑，这不是失败。'
    'Robinhood 是后加的成员，缺了会退回原来的三家，图注里会写明少了谁。',

    '<b>Robinhood 只进它口径真可比的图。</b>入图的四条轴：客户资产'
    '（total platform assets ⇄ Schwab/LPL 的 total client assets ⇄ IBKR 的 client equity）、'
    '净流入（net deposits ⇄ core NNA ⇄ organic NNA，都按「当月流量 × 12 ÷ 上月末资产」年化）、'
    '日均交易（股票+期权+加密 DATs 之和）、融资余额（margin book）。'
    '<b>不入图的：客户现金</b> —— Robinhood 把它拆成 cash sweep（扫到合作银行、表外）与 '
    'cash and deposits（留在券商）两条，不发布同一口径的合计，取任一条与 LPL 的 client cash、'
    'IBKR 的 client credits 并排都会错；<b>2018 起的长历史</b> —— 它的月度披露自 2023-04 才有，'
    '另出一张四家同基期（2023-04）的图（Exhibit 3）。',

    '<b>「可比」不等于「相同」，各图注已逐条标出差异。</b>客户资产的三种叫法'
    '（client assets / client equity / platform assets）都是「客户放在这家平台上的资产」，'
    '可直接并排；但日均交易的「一笔」三家定义不同（Schwab 数成交笔数、'
    'IBKR 报的是 Total Client DARTs、含不在 IBKR 清算的客户、Robinhood 是三个市场之和），'
    '融资余额里 Schwab 含 short credits 而另两家不含，'
    '账户口径 IBKR 数账户、Robinhood 数「有入金的客户」。'
    '这些图的<b>水平值只能当量级读，方向与拐点才是可比的信息</b>。',

    '<b>流量类不算环比百分比。</b>净新增资产是流量，环比百分比的分母是上个月的流量，'
    '一个月的噪音会被放大成趋势。按 GS「LPLA monthly metrics」的规矩改用<b>年化有机增长率</b>'
    '（当月净流入 × 12 ÷ 上月末客户资产），见 Exhibit 5。'
    '比率序列的差异一律用<b>百分点（pp/bp）</b>，不是「百分比的百分比变化」。',

    '<b>LPL 的并购转入已从有机口径里剔除。</b>Atria（2024-10，$88.3bn）与 '
    'Commonwealth（2025-08，$275.0bn）等 Acquired NNA 来自官方月报同页的披露，'
    '逐条硬编码在本脚本与 <code>build/lpla.py</code> 里（不是 CSV 的一列，改一处要改两处）。'
    'Exhibit 5 用的是剔除后的 organic NNA；Exhibit 2、3、4 与 Exhibit 14 画的是<b>含</b>并购的 '
    'as-reported 口径，所以那两次跳升之后的 12 个月里，LPL 与另外三家不可比。'
    + (f'<b>Exhibit {"、".join(str(n) for n in BRK_DRAWN)} 已在 2024-10 与 2025-08 的左缘'
       f'画出红色竖虚线并标 LPL Atria / LPL Commonwealth</b>（语义：该期起 LPL 这条线与左侧'
       '不可比，另外三家不受影响）。' if BRK_DRAWN else '')
    + 'Exhibit 5 已是剔除后的口径，本身连续可比，故不画断点；'
    'Exhibit 1 汇总表与 Exhibit 14 热力矩阵的图型都不支持断点线，改在各自的图注里写明。'
    + (f'当期的量级：{LP_RANK_TXT}' if LP_RANK_TXT else ''),

    '<b>横截面页独有的两张归一化图。</b>Exhibit 11（融资余额 / 客户资产）与 '
    'Exhibit 12（客户现金 / 客户资产）把余额按各自的客户资产归一化：'
    '绝对额只说明谁大，占比说明「同样一块客户资产上，谁的客户加了更多杠杆 / 留了更多现金」。'
    '分子分母的口径差异（见上）会造成系统性水平偏差，趋势与相对位次才是要看的。',

    '<b>缺的月份不补、不连。</b>Schwab 的月末融资余额与 DATs 都是 2026-01 的月报才开始披露'
    '（滚动表回溯至 2025-01），所以它在 Exhibit 7、9 的线在窗口左段是断的 —— '
    '那是没有披露，不是余额为零。所有非有限值一律写 <code>null</code>，图与表都断开，不画假点。',

    f'<b>窗口。</b>近期多线图 {WIN} 个月、核对表 13 个月、热力矩阵最多 7 年，'
    '全部从共同最新月倒推；重定基图从各自基期画到共同最新月。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算 —— '
    '同一个数字在两个语言里各算一遍，迟早会出现图上与表里对不上而没人发现。',
]

headline = (f'共同最新月 {mlab(LATEST)}（短板 {LAG}）'
            f' · 客户资产 Schwab {_v("schw_assets", 0, "$")}bn / LPL {_v("lpla_assets", 0, "$")}bn'
            f' / IBKR {_v("ibkr_assets", 0, "$")}bn'
            + (f' / Robinhood {_v("hood_assets", 0, "$")}bn' if 'hood' in HAS else '')
            + f' · 年化有机增速 Schwab {_v("schw_org", 1)}% / LPL {_v("lpla_org", 1)}%'
            + (f' / Robinhood {_v("hood_org", 1)}%' if 'hood' in HAS else ''))

payload = {
    'ticker': 'wealth',
    'tracker': 'Wealth & Brokerage Cross-Section',
    'title': ('财富与券商组横截面：'
              + ' / '.join(NAME[t] for t, *_ in [(m[0],) for m in MEMBERS] if t in HAS)
              + f' — {LATEST.year} 年 {LATEST.month} 月'),
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月（共同最新月）',
    'subtitle': (f'{len(HAS)} 家月度披露的横截面 · 统一截至共同最新月 {mlab(LATEST)}'
                 f'（短板 {LAG}）· 版式沿用 Goldman Sachs GIR 的 monthly-metrics 体例 · '
                 '仅图表，无观点'),
    'headline': headline,
    'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"/".join(NAME[t] for t in LAGGARDS)}）· '
                 f'{len(HAS)} 家 · {len(ex)} 张图'),
    'source': SRC,
    'xlabels': XL,
    'xlabels_long': XL_LONG,
    'summary': summary,
    'exhibits': ex,
    'table': table,
    'notes': notes,
    'footer': (f'<b>发布门槛：</b>本页统一截至共同最新月 <b>{mlab(LATEST)}</b>，'
               f'由最慢的成员 <b>{LAG}</b> 决定。各家自身最新月：'
               + '；'.join(f'{NAME[t]} <b>{mlab(LATEST_EACH[t])}</b>' for t in sorted(RAW))
               + '。' + ('更新更早的月份本页不画 —— 否则末端的强弱对比只是披露时点的错觉。'
                         if _others else '本次各家最新月一致。')
               + ' · 数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                 '仅供个人研究，不构成投资建议'),
}


def main():
    out_dir = os.path.join(ROOT, 'data')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'wealth.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(path, payload, 'wealth')
    print(f'共同最新月 {LATEST}（短板 {"/".join(NAME[t] for t in LAGGARDS)}）'
          f' | 各家: ' + ', '.join(f'{t}→{LATEST_EACH[t]}' for t in sorted(RAW))
          + (f' | 未就绪: {[t for t, _ in skipped]}' if skipped else ''))
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）'
          f' + Exhibit {table["n"]} 核对表')
    print(f'写出 data/wealth.js  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
