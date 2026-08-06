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

import brief as B                   # 顶部 brief 的规则库（R1-R6），只算事实、不产文字
from monthlab import mlab   # x 轴月份标签 Jul-26 的唯一实现
import payload_guard
import pctile                       # 3Y %ile 的唯一实现，各页不许各写各的（CONTRACT §2）
import repo                         # 仓库定位 + 发布日台账入口

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

# ────────────────────────── 结构性断点登记表 ──────────────────────────
# 一条序列在哪个月换了口径 / 并了表，在这里登记一次；每张图按它画的是哪几条序列
# 引用对应的清单。CONTRACT.md §5.2：口径断点必须画出来，不能靠图注文字提一句就算数；
# 反过来也成立 —— **图注声称画了线，图上就必须真有线**，所以下面的图注文案也由同一个
# 登记表生成（brk_note），断点滚出窗口时线和文案一起消失，不会剩下一句假话。
#
# 标签点名公司：单票页上整幅红线天然只指那一家，横截面页上四条线并排，不点名会被读成
# 「四家在这里都换了口径」。竖排标签越短越好（引擎从画布顶往下排，字多会压住相邻标注）。
LPL_ACQ_BRK = [(pd.Period('2024-10', 'M'), 'LPL Atria'),          # +$88.3bn，约当月资产 6%
               (pd.Period('2025-08', 'M'), 'LPL Commonwealth')]   # +$275.0bn，约 14%
# Schwab core NNA：单一客户异常流入的剔除门槛 2025-01 起从 $10bn 提到 $25bn，月报不重述
# 历史（口径与月份同 build/schw.py 的 BRK，改一处要改两处）。
SCHW_NNA_BRK = [(pd.Period('2025-01', 'M'), 'SCHW $10→$25bn')]
# Robinhood：口径与月份同 build/hood.py 的 BK_ND / BK_CUST / BK_TPA。
HOOD_ND_BRK = [(pd.Period('2025-06', 'M'), 'HOOD Bitstamp'),
               (pd.Period('2026-03', 'M'), 'HOOD TradePMR'),
               (pd.Period('2026-06', 'M'), 'HOOD WonderFi')]
HOOD_CUST_BRK = [(pd.Period('2025-06', 'M'), 'HOOD Bitstamp'),
                 (pd.Period('2026-06', 'M'), 'HOOD WonderFi')]
HOOD_TPA_BRK = [(pd.Period('2026-06', 'M'), 'HOOD WonderFi')]

# 「客户资产」这一族图（重定基与 y/y）同时受 LPL 的两次并表与 Robinhood 的 WonderFi 影响，
# 所以三张图引用同一个合集，不各拼各的。
ASSET_BRK = LPL_ACQ_BRK + HOOD_TPA_BRK

# 每个断点在图注里的说法。键就是上面的 Period，保证「画了哪条线」与「图注说了哪条」
# 出自同一个来源。
BRK_TXT = {
    pd.Period('2024-10', 'M'): 'LPL 2024-10 并入 Atria（Acquired NNA +$88.3bn）',
    pd.Period('2025-08', 'M'): 'LPL 2025-08 并入 Commonwealth（Acquired NNA +$275.0bn）',
    pd.Period('2025-01', 'M'): 'Schwab 2025-01 起把单一客户流入的剔除门槛从 $10bn 提到 $25bn'
                               '（月报不重述历史）',
    pd.Period('2025-06', 'M'): 'Robinhood 2025-06 起把 Bitstamp 并入净流入与客户数',
    pd.Period('2026-03', 'M'): 'Robinhood 2026-03 起把 TradePMR 顾问资产的流量并入净流入',
    pd.Period('2026-06', 'M'): 'Robinhood 2026-06 并入 WonderFi（带进约 30 万 funded customers）',
}


def _hit(idx, events):
    """窗口内真正盖得到的断点：[(x 索引, 竖排标签, Period), …]，按 x 升序。"""
    lst = list(idx)
    return sorted(((lst.index(p), lab, p) for p, lab in events if p in lst),
                  key=lambda h: h[0])


def brks(idx, events):
    """把结构性断点映射到给定窗口的 x 索引，返回可直接展开进 exhibit dict 的片段。

    窗口盖不到的断点自动省略（各图窗口起点不同、dense_win 还会随披露变动，
    硬编码索引下个月就错位）；一个都盖不到就返回空 dict，图上不画、图注也不会声称画了。
    这是「优雅降级」而不是硬失败：断点终会滚出 25 个月窗口，那天页面要照常出
    （build/lpla.py 在同一处 raise SystemExit，2025-08 滚出窗口那天 LPLA 页会永久停更）。

    「哪几张图真的画了线」不在这里累计，由 drawn_for() 从建好的 payload 现读 ——
    累计器和图注各写一份，早晚会出现「图注说画了、图上没有」。"""
    h = _hit(idx, events)
    if not h:
        return {}
    return {'break_at': [i for i, _l, _p in h],
            'break_label': [lab for _i, lab, _p in h]}


def jump_txt(idx, events, cname, lead='并表当月的环比：', d=1):
    """断点当月这条序列跳了多少 —— 现算，不写死。

    「不可比」是个定性说法，读者真正需要的是量级；而写死的数字在补历史或修数之后
    就变成第二处口径谎言（本项目在 schw「过去 32 个季度单边降」上已经付过一次代价）。"""
    s = df[cname] if cname in df.columns else None
    if s is None:
        return ''
    out = []
    for _i, _l, p in _hit(idx, events):
        if p not in s.index or (p - 1) not in s.index:
            continue
        a, b = float(s.loc[p]), float(s.loc[p - 1])
        if not (np.isfinite(a) and np.isfinite(b)) or b == 0:
            continue
        out.append(f'{mlab(p)} {signed((a / b - 1) * 100, d, "%")}')
    return (lead + '、'.join(out) + '。') if out else ''


def dilution_txt(idx, events, cname):
    """比率图专用：断点当月这条比率掉了多少 bp，占全窗口总变动的多少。

    「不可比」对比率图还不够 —— 分子分母跳的幅度不同时，比率会**机械地**掉一截，
    读者会把它读成基本面。给出 bp 与占比，他才知道该把多少归给并购。"""
    s = df[cname] if cname in df.columns else None
    if s is None:
        return ''
    parts, jump = [], 0.0
    for _i, _l, p in _hit(idx, events):
        if p not in s.index or (p - 1) not in s.index:
            continue
        a, b = float(s.loc[p]), float(s.loc[p - 1])
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        parts.append(f'{mlab(p)} 单月 {signed((a - b) * 100, 0, "bp")}')
        jump += a - b
    if not parts:
        return ''
    lo, hi = float(s.reindex(idx).iloc[0]), float(s.reindex(idx).iloc[-1])
    txt = '、'.join(parts)
    if np.isfinite(lo) and np.isfinite(hi) and abs(hi - lo) > 1e-9:
        txt += (f'，{len(parts)} 个并表月合计 {signed(jump * 100, 0, "bp")}；'
                f'而全窗口 {mlab(idx[0])}→{mlab(idx[-1])} 一共才动了 '
                f'{signed((hi - lo) * 100, 0, "bp")} —— '
                f'并表这一块占了约 {abs(jump / (hi - lo)) * 100:.0f}%')
    return txt + '。'


def brk_note(idx, events, lead='<b>红色竖虚线 = 口径断点</b>：', tail=''):
    """图注里那句「红色竖虚线 = …」只在**真画出线**时才写，且逐条只列画出来的那几个。"""
    h = _hit(idx, events)
    if not h:
        return ''
    return lead + '；'.join(BRK_TXT[p] for _i, _l, p in h) + '。' + tail


def drawn_for(exhibits, events):
    """哪几张图上真的画了这一组断点 —— 从建好的 exhibit 列表现读，不另设累计器。"""
    labs = {lab for _p, lab in events}
    return sorted({e['n'] for e in exhibits if set(e.get('break_label') or []) & labs})


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


# ────────────────────── Exhibit 编号：先排好，再让图注引用变量 ──────────────────────
# 写死编号的代价这一页已经付过：图注里的「见 Exhibit 5」「Exhibit 14 热力矩阵」
# 在中间插一张图之后会全部指错，而那种错没有任何自动检查拦得住。编号只在这里生成一次，
# 正文一律引用常量；成员或某条序列缺席时它那张图不出，编号往前接，不留空号。
def _live(cname):
    return cname in df.columns and bool(np.isfinite(df[cname].values.astype(float)).any())


_seq = iter(range(2, 99))
N_REB18 = next(_seq)                                  # 2018 基期重定基
N_REB23 = next(_seq)                                  # 2023-04 基期重定基（四家同基期）
N_YOY = next(_seq)                                    # 客户资产 y/y
N_ORG = next(_seq)                                    # 年化有机增速：Schwab vs LPL
N_ORG_HOOD = next(_seq) if _live('hood_org') else None   # 年化有机增速：Robinhood（另一量级）
N_ACCT = next(_seq)                                   # 账户增速
N_MGN = next(_seq)                                    # 融资余额
N_CASH = next(_seq)                                   # 客户现金
N_DATS = next(_seq)                                   # 日均交易
N_REB19 = next(_seq)                                  # 2019 基期资产负债表重定基
N_MGNPCT = next(_seq)                                 # 融资余额 / 客户资产
N_CASHPCT = next(_seq)                                # 客户现金 / 客户资产
# 热力矩阵：某家的 y/y 全空时那张图根本建不出来（heat() 返回 None），编号也不该占。
N_HEAT = {t: next(_seq) for t in ('schw', 'lpla', 'ibkr', 'hood')
          if t in HAS and _live(f'{t}_yoy')}
N_TABLE = next(_seq)                                  # 页尾核对表


# ────────────────────────────── 格式化零件 ──────────────────────────────


def comma(v, d=0):
    return f'{_nz(v, d):,.{d}f}'


def _nz(v, d):
    """四舍五入到 d 位之后正好是 0 的负数回正 —— 否则印出「-0」「-0.0%」「-0bp」。

    Python 的 f-string 是先取符号再四舍五入的：f'{-0.004:+.1f}%' → '-0.0%'。
    读者看到的是一个带负号的零，会当成「跌了一点点」，而它其实是「没动」。"""
    v = float(v)
    return 0.0 if round(v, d) == 0 else v


def signed(v, d, suffix):
    """带正负号的数。四舍五入后正好是零时连符号一起去掉 —— 「+0bp」同样是假消息，
    它宣称的是一个方向，而这个数只是「没动」。"""
    v = _nz(v, d)
    return f'{v:+,.{d}f}{suffix}' if v else f'{0:,.{d}f}{suffix}'


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


def acq_roll12(idx):
    """LPL 各月的滚动 12 个月 Acquired NNA（含当月），$bn。

    还原口径在本模块只有这一处定义：y/y 用它剔分子月的并购、客户现金占比用它剔分母 ——
    两处各写各的，就会出现「同一句话在两种还原约定下结论相反」而没人发现。
    """
    s = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(idx).fillna(0.0)
    return s.rolling(12, min_periods=1).sum()


def lp_yoy_ex(d, cur):
    """LPL 客户资产 y/y 的剔并购口径 →（y/y%, 该月滚动 12 个月 Acquired NNA）。

    传 d/cur 而不是读全局，是为了能把序列截到历史任一个月重放：t12 跟着那个月的
    12 个月窗口自己变，不是写死的 $277.0bn（并表滚出窗口那天它必须自己归零）。
    算不出来（缺月、分母为零）返回 (None, None)，由调用方决定这句写不写。
    """
    yag = cur - 12
    try:
        now, ago = float(d['lpla_assets'].loc[cur]), float(d['lpla_assets'].loc[yag])
    except (KeyError, TypeError, ValueError):
        return None, None
    if not B.need(now, ago) or ago == 0:
        return None, None
    t12 = sum(v for k, v in ACQ.items() if yag < pd.Period(k, 'M') <= cur)
    return ((now - t12) / ago - 1) * 100, t12


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
    exq, t12 = lp_yoy_ex(df, CUR)
    raw = (lp_now / lp_ago - 1) * 100
    txt = (f'{mlab(CUR)} 的 LPL 读数为 <b>{raw:+.1f}%</b>，剔掉滚动 12 个月的 Acquired NNA'
           f'（${t12:,.1f}bn）之后是 <b>{exq:+.1f}%</b>，'
           + (f'<b>低于</b> Schwab 的 {sc:+.1f}% —— 名次是反的。'
              if exq < sc else f'仍高于 Schwab 的 {sc:+.1f}%。'))
    return txt, exq


LP_RANK_TXT, LP_YOY_EX = _lp_rank_txt()
_LP_YOY_S = df['lpla_yoy'].dropna() if 'lpla_yoy' in df.columns else pd.Series(dtype=float)
_LP_YOY_NOW = float(_LP_YOY_S.iloc[-1]) if len(_LP_YOY_S) else None


def cell(v, d, kind):
    """水平值单元格。三种 kind 都走 comma()，负零才不会从某一条支路漏出去。"""
    if v is None or not np.isfinite(v):
        return '—'
    return money(v, d) if kind == '$' else (comma(v, d) + ('%' if kind == '%' else ''))


def _v0(cname, d=1, kind=''):
    """某一列的当期读数（已格式化）。图注里引用别的图的数字时用它，别再手抄一遍。"""
    s = df[cname].dropna() if cname in df.columns else pd.Series(dtype=float)
    return '—' if not len(s) else cell(float(s.iloc[-1]), d, kind)


def chg(a, b, mode, d, kind):
    """m/m、y/y 单元格。比率类用 pp/bp（GS LPLA 规矩 2），不用百分比变化。"""
    if a is None or b is None or not (np.isfinite(a) and np.isfinite(b)):
        return {'v': ''}
    if mode == 'pp':
        v = a - b
        # CONTRACT §2：abs(v) < 1 用 bp，否则用 pp。分档看的是四舍五入前的真值。
        txt = signed(v * 100, 0, 'bp') if abs(v) < 1 else signed(v, 2, 'pp')
        shown = round(v * 100, 0) if abs(v) < 1 else round(v, 2)
    else:
        if b == 0 or a * b < 0:
            return {'v': ''}
        v = a / b - 1
        txt = signed(v * 100, 1, '%')
        shown = round(v * 100, 1)
    # 颜色跟着**印出来的那个数**走：印成 +0.0% 就不涂色，否则读者会看到一个
    # 绿色的零，以为是四舍五入吃掉了一个正数。
    return {'v': txt, 'cls': 'pos' if shown > 0 else ('neg' if shown < 0 else '')}


def pctile_cell(s):
    """3Y %ile 单元格。判据与全部 14 个生成器共用 build/pctile.py，本页不自己写。

    旧实现是「36 个月里 ≥90% 月环比不降就留空」的代理判据，拦不住「上下波动但分位
    常年钉 100」的行（Schwab margin balances、IBKR client credits、Robinhood margin
    book），也与 /lpla/ 对同一条 LPL total client assets 的判定相反。"""
    v, cls = pctile.cell(_ser(s))
    return {'v': v, 'cls': cls} if v else {'v': ''}


def _ser(s):
    """pandas Series → pctile.py 吃的 [float | None] 列表（按月升序，缺月写 None）。"""
    return [None if not np.isfinite(v) else float(v) for v in s.values]


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

srows, PCT_BLANK = [], []       # PCT_BLANK：分位留空的行，表注里点名，免得被当成漏算
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
    pc = pctile_cell(s)
    if not pc['v']:
        PCT_BLANK.append(lab)
    srows.append({'label': lab, 'cells': [
        {'v': cell(c, d, kind)}, {'v': cell(p1, d, kind)}, {'v': cell(p12, d, kind)},
        chg(c, p1, mode, d, kind), chg(c, p12, mode, d, kind), pc]})

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
             '判据同全站（<code>build/pctile.py</code>，14 个生成器共用一份）：'
             '把该行的分位在<b>近 24 个月里逐月回放</b>，若 ≥70% 的月份都钉在端点（100 或 0），'
             '这一列对这一行就没有区分度，留空。'
             + (f'本轮留空的是：{"、".join(PCT_BLANK)} —— 这几行的分位近两年几乎恒为 100，'
                '印出来只会让人误以为「刚刚创下新高」。' if PCT_BLANK else '本轮没有行触发留空。')
             + '仍显示 100 的行是回放里真的下过来过的，读到 100 时也只是说'
             '「当月是近三年最高」，不代表动能。'),
}


# ────────────────────────────── Exhibit 2..N ──────────────────────────────
ex = []
GATE = (f'本页所有图统一截到共同最新月 {mlab(LATEST)}；'
        f'{LAG} 是短板，其余各家更新更早的月份本页不画。')


# 重定基图的画布高度。不是审美选择：kind:'lines' 的末点标签画在点上方 7px，而引擎的
# 竖向避让在「最高的那个标签顶到画布上沿」时会把**整列**标签压到顶端顺排 —— 于是
# 三条线的指数值全叠在右上角、与各自的线脱钩（382 看着像在标 660 那条线）。
# 该分支的上留白恒为量程的 1/22（y1 = max + 5%×极差），与数据无关，所以只要绘图区
# 高度 ≥ 约 308px，最高的标签就够不到上沿。取 340 留出余量。
REB_H = 340


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
    'n': N_REB18, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I18),
    'xstep': max(1, len(I18) // 14), 'end_label': True, 'height': REB_H,
    'title': f'Client assets since {mlab(B18)}, rebased to 100',
    'ylab': f'index, {mlab(B18)} = 100',
    'series': s2,
    **brks(I18, ASSET_BRK),
    'note': (firms_note(inc2, exc2,
                        'Robinhood 的月度经营指标自 2023-04 才有，进不了 2018 基期的图 —— '
                        '把它从自己的首月当 100 起画，会与另外三家比出一个纯属基期不同的假斜率；'
                        '四家同基期的版本见下一张。')
             + brk_note(I18, ASSET_BRK, tail='断点右侧那条线与左侧不可比，其余各家不受影响。'
                                          '重定基图上并购是<b>永久抬升</b>的 —— '
                                          '断点右侧的全部水平差里有一块不是自己长出来的。')
             + f'各条线右端的粗体数字是当期指数值（{mlab(B18)} = 100）。' + GATE),
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
    'n': N_REB23, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I23),
    'xstep': max(1, len(I23) // 14), 'end_label': True, 'height': REB_H,
    'title': f'Client assets since {mlab(B23)}, rebased to 100 —— 四家同基期',
    'ylab': f'index, {mlab(B23)} = 100',
    'series': s3,
    **brks(I23, ASSET_BRK),
    'note': (firms_note(inc3, exc3)
             + f'基期取 {mlab(B23)}（Robinhood 月度经营指标的首月），四家从同一天起跑，'
             '斜率之差才是真的增长之差。口径：Schwab / LPL 为 total client assets，'
             'IBKR 为 client equity，Robinhood 为 total platform assets —— '
             '都是「客户放在这家平台上的资产总额」，可直接并排。'
             + brk_note(I23, ASSET_BRK, tail='断点右侧那条线与另外三家的斜率差里有一块是买来的，'
                                          '不是长出来的。')
             + f'右端粗体数字为当期指数值。有机口径见 Exhibit {N_ORG}。' + GATE),
})

# ── Exhibit 4：客户资产 y/y ──
_i4 = dense_win([(t, f'{t}_yoy', '') for t in ('schw', 'lpla', 'ibkr', 'hood')])
s4, inc4, exc4 = sr([(t, f'{t}_yoy', NAME.get(t, t.upper()))
                     for t in ('schw', 'lpla', 'ibkr', 'hood')], _i4)
ex.append({
    'n': N_YOY, 'kind': 'lines_endlabels', 'fmt': 'pct0', 'xlabels': xls(_i4), 'xstep': 2,
    'title': 'Client asset growth, y/y', 'ylab': '% y/y', 'zero_line': True,
    # 四条线的两端各要标一个数，其中两对（左端 23%/20%、右端 49%/48%）本来就只差 1pp。
    # 引擎的竖向避让有 9.6px 的最小行距，画布越矮就越多标签被推到「刚好不叠字」的距离上，
    # 读者只能靠颜色反推是哪家。加高画布是唯一在 payload 侧能给的解药：同样的 1pp 在
    # 更高的画布上本来就占更多像素，避让根本不必启动。
    'height': 330,
    'series': s4,
    **brks(_i4, ASSET_BRK),
    'note': (firms_note(inc4, exc4)
             + brk_note(_i4, ASSET_BRK,
                        tail='并进来的资产不是有机增长，跳升起的 12 个月里那条线的 y/y '
                             '与同图其余各家不可比。')
             + LP_RANK_TXT + f'有机口径见 Exhibit {N_ORG}。' + win_note(_i4) + GATE),
})

# ── Exhibit 5：年化有机增速（Schwab vs LPL）──
# 原来这张图把 Robinhood 也放进来，纵轴被它的 20–49% 定死，Schwab（0.3–8%）与 LPL
# 近一年的读数全压在最底下那条带里，headline 写的「Schwab 4.8% / LPL 4.3%」在图上根本
# 读不出来。同一单位但差一个量级的序列不该共用一根轴，所以拆成两张（Robinhood 见下一张）。
# 拆完之后 LPL 2024-11–2025-02 那四个月的尖峰（15.8–24.5%）还是会把轴撑到 25%，
# 这一段用截轴处理 —— **截轴不删点**：超界的点画成空心红圈、真值竖排标在图上。
_IT5 = [('schw', 'schw_org', 'Schwab core NNA'),
        ('lpla', 'lpla_org', 'LPL organic NNA')]
_i5 = dense_win(_IT5)
s5, inc5, exc5 = sr(_IT5, _i5)
EX5_CAP = 12.0
_over5 = [(nm['name'], _i5[k], v) for nm in s5
          for k, v in enumerate(nm['values']) if v is not None and v > EX5_CAP]
ex.append({
    'n': N_ORG, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'yfmt': 'pct0',
    # label_fmt 要显式给：截轴真值标注的格式器优先取 yfmt（pct0），会把 24.5% 印成
    # 25%，与本图注里逐个列出的真值差一位小数 —— 同一张图上两个数对不上。
    'label_fmt': 'pct1',
    'xlabels': xls(_i5), 'xstep': 2,
    'title': 'Annualised organic growth: Schwab vs. LPL',
    'ylab': '% annualised', 'zero_line': True,
    'series': s5,
    # yfloor 必须与 ycap 一起给：lines_endlabels 的默认下界是 mn − 0.20×极差，
    # 极差是按**未截轴的**数据算的，只给 ycap 会在零线下面留一大片空白。
    **({'ycap': EX5_CAP, 'yfloor': 0.0,
        'cap_note': f'axis capped at {EX5_CAP:.0f}% — true values shown in red'}
       if _over5 else {}),
    **brks(_i5, SCHW_NNA_BRK),
    'note': (firms_note(inc5, exc5,
                        'IBKR 不披露净新增资产，只披露净新增账户，所以它的增速看 '
                        f'Exhibit {N_ACCT}；Robinhood 的量级差一档（当前 '
                        f'{_v0("hood_org", 1)}% vs Schwab {_v0("schw_org", 1)}% / '
                        f'LPL {_v0("lpla_org", 1)}%），与这两家同轴会把它们压成一条带，'
                        f'单独画在 Exhibit {N_ORG_HOOD}。' if N_ORG_HOOD else
                        'IBKR 不披露净新增资产，只披露净新增账户，所以它的增速看 '
                        f'Exhibit {N_ACCT}。')
             + '两家都是<b>当月净流入 x 12 ÷ 上月末客户资产</b>（GS LPLA 版式的流量口径规矩：'
             '流量类不算环比百分比，分母是上个月的流量、一个月的噪音会被放大成趋势）。'
             'LPL 已按官方同页披露的 Acquired NNA 剔除并购转入。'
             + (f'纵轴截在 0–{EX5_CAP:.0f}%：'
                + '；'.join(
                    nm + ' ' + '、'.join(f'{mlab(p)} {v:.1f}%'
                                         for n2, p, v in _over5 if n2 == nm)
                    for nm in dict.fromkeys(n2 for n2, _p, _v in _over5))
                + '（LPL 大型机构渠道集中上线的几个月，官方未列入 Acquired NNA，'
                '所以留在有机口径里）会把其余月份压成贴零的平线。'
                '<b>截轴不删点</b> —— 超界的点画成空心红圈、真值竖排标在图上，'
                '表格视图里也是真值。' if _over5 else '')
             + brk_note(_i5, SCHW_NNA_BRK,
                        tail='两家的剔除规则本来就各自不同，断点标的是 Schwab 这一条线'
                             '自己前后不可比的那个位置。')
             + win_note(_i5) + GATE),
})

# ── Exhibit 6：年化有机增速（Robinhood，另一个量级）──
if N_ORG_HOOD:
    _IT6H = [('hood', 'hood_org', 'Robinhood net deposits')]
    _i6h = dense_win(_IT6H)
    s6h, inc6h, exc6h = sr(_IT6H, _i6h)
    ex.append({
        'n': N_ORG_HOOD, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'yfmt': 'pct0',
        'xlabels': xls(_i6h), 'xstep': 2,
        'title': 'Annualised organic growth: Robinhood',
        'ylab': '% annualised', 'zero_line': True,
        'series': s6h,
        **brks(_i6h, HOOD_ND_BRK),
        'note': ('口径与 Exhibit ' + str(N_ORG) + ' 完全相同（当月净流入 x 12 ÷ 上月末客户资产），'
                 '<b>只是纵轴不同</b>：Robinhood 这条线常年在 '
                 f'{min(v for v in s6h[0]["values"] if v is not None):.0f}–'
                 f'{max(v for v in s6h[0]["values"] if v is not None):.0f}% 之间，'
                 f'与 Schwab / LPL 的 {_v0("schw_org", 1)}% / {_v0("lpla_org", 1)}% 差一个量级，'
                 '同轴画会把那两条压成一条贴零的带（这正是拆图的原因）。'
                 '两张图的百分比可以直接比大小，但<b>不要把两张图的线形叠着看</b>。'
                 'net deposits 是客户净转入（含现金与证券转入），与 Schwab 的 core NNA、'
                 'LPL 的 organic NNA 是同一个经济含义，但三家的剔除规则各自不同。'
                 + brk_note(_i6h, HOOD_ND_BRK,
                            tail='并入的流量不是有机获客，断点右侧与左侧不可直读。')
                 + win_note(_i6h) + GATE),
    })

# ── Exhibit 7：账户数增速（只有 IBKR 与 HOOD 披露存量账户数）──
_IT6 = [('ibkr', 'ibkr_acct_yoy', 'IBKR accounts'),
        ('hood', 'hood_acct_yoy', 'Robinhood funded customers')]
_i6 = dense_win(_IT6)
s6, inc6, exc6 = sr(_IT6, _i6)
ex.append({
    'n': N_ACCT, 'kind': 'lines_endlabels', 'fmt': 'pct1', 'yfmt': 'pct0',
    'xlabels': xls(_i6), 'xstep': 2,
    'title': 'Account growth, y/y: IBKR vs. Robinhood', 'ylab': '% y/y',
    'series': s6,
    **brks(_i6, HOOD_CUST_BRK),
    'note': (firms_note(inc6, exc6,
                        'Schwab 只披露当月<b>新开</b>经纪账户（流量），不披露账户存量；'
                        'LPL 披露的是投顾人数（advisor count）而不是账户数 —— '
                        '两者都不能与「账户存量的 y/y」并排，所以不入图。')
             + 'IBKR 的口径是 total accounts，Robinhood 是 funded customers（有入金的客户数），'
             '一个数账户、一个数人，绝对水平不可比，但增速的方向与幅度可比。'
             + brk_note(_i6, HOOD_CUST_BRK,
                        tail='并进来的客户不是自然获客，断点之后的 12 个月里 Robinhood 的 y/y '
                             '含这块一次性增量，与 IBKR 不 like-for-like。')
             + win_note(_i6) + GATE),
})

# ── Exhibit 7：融资余额 ──
_IT7 = [('schw', 'schw_margin', 'Schwab month-end margin'),
        ('ibkr', 'ibkr_margin', 'IBKR margin loans'),
        ('hood', 'hood_margin', 'Robinhood margin book')]
_i7 = dense_win(_IT7)
s7, inc7, exc7 = sr(_IT7, _i7)
_schw_mgn0 = df['schw_margin'].dropna()
ex.append({
    'n': N_MGN, 'kind': 'lines_endlabels', 'fmt': 'usd0', 'xlabels': xls(_i7), 'xstep': 2,
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
    'n': N_CASH, 'kind': 'lines_endlabels', 'fmt': 'usd0', 'xlabels': xls(_i8), 'xstep': 2,
    'title': 'Client cash: LPL vs. IBKR', 'ylab': '$bn',
    'series': s8,
    # LPL 的 client cash 同样是并表转入的（2024-10 45.8→48.3、2025-08 49.5→52.7，
    # 后者是 2018 年以来最大的一个 8 月）—— 画 as-reported LPL 的图都要带断点线。
    **brks(_i8, LPL_ACQ_BRK),
    'note': (firms_note(inc8, exc8)
             + '<b>为什么少两家：</b>Schwab 的月报根本不单列客户现金；'
             'Robinhood 把客户现金拆成 cash sweep（扫到合作银行、表外）与 cash and deposits'
             '（留在券商）两条线，不发布同一口径的合计 —— 取任一条与 LPL 的 client cash'
             '（ICA + 货基 + DCA 合计）、IBKR 的 client credits 并排，不是漏计就是重复计，'
             '所以宁可这张图只有两家。这两条线都是净利息收入的核心驱动。'
             + brk_note(_i8, LPL_ACQ_BRK,
                        tail='并表把被并方的客户现金一次性转入，那一跳不是客户在加现金 —— '
                             + jump_txt(_i8, LPL_ACQ_BRK, 'lpla_cash',
                                        lead='LPL client cash 在断点当月的环比为 '))
             + win_note(_i8) + GATE),
})

# ── Exhibit 9：日均交易笔数 ──
_IT9 = [('schw', 'schw_dats', 'Schwab DATs'),
        ('ibkr', 'ibkr_dats', 'IBKR total client DARTs'),
        ('hood', 'hood_dats', 'Robinhood DATs')]
_i9 = dense_win(_IT9)
s9, inc9, exc9 = sr(_IT9, _i9)
ex.append({
    'n': N_DATS, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': xls(_i9), 'xstep': 2,
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
             '所以本图窗口从那里起。'
             # 首页把「IBKR 2025-01 DARTs 口径变更」列为断点示例，本图却不画 —— 不解释
             # 就是又一处「两页说法不一致」。理由要写在图上，不是留给读者猜。
             '<b>关于 IBKR 单页那条 2025-01 断点：</b>它标在 IBKR 单页 Exhibit 18 上，'
             '指的是 cleared / non-cleared 这个<b>拆分比例</b>在 2025 年跳了一档'
             '（该页原文：疑似口径 / 分类变更，未经公司确认），而不是本图画的这条'
             '<b>披露总量</b>；何况本图窗口正好从 Jan-25 起（受 Schwab 的披露起点约束），'
             '断点落在第一期、左边没有可比的部分，画出来只是一条贴在纵轴上的红线，'
             '不带任何信息。所以本图不画这条线，改在这里写明。'
             + win_note(_i9) + GATE),
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
_LPL_IN_10 = any(s['name'] == 'LPL client cash' for s in s10)
ex.append({
    'n': N_REB19, 'kind': 'lines', 'fmt': 'f0', 'xlabels': xls(I19),
    'xstep': max(1, len(I19) // 14), 'end_label': True, 'height': REB_H,
    'title': f'Balance-sheet items since {mlab(B19)}, rebased to 100',
    'ylab': f'index, {mlab(B19)} = 100',
    'series': s10,
    # 这张图里有一条 as-reported 的 LPL client cash，重定基图上并购是永久抬升的
    # （本页 Exhibit 2 的图注自己就是这么论证的），断点必须画。
    **(brks(I19, LPL_ACQ_BRK) if _LPL_IN_10 else {}),
    'note': (firms_note(inc10, exc10)
             + '融资余额是周期项、客户现金是利率敏感项，重定基之后能看出两者的相位差。'
             'Schwab 的月末融资余额只有 2025-01 起的历史、Robinhood 只有 2023-04 起的历史，'
             f'都盖不到 {mlab(B19)} 的基期，硬画等于拿一个空值当分母，所以不入这张长历史图；'
             f'它们的近期水平见 Exhibit {N_MGN}。'
             + (brk_note(I19, LPL_ACQ_BRK,
                         tail='只影响 LPL client cash 这一条线：重定基图上并购是'
                              '<b>永久抬升</b>的，断点右侧它与另外两条的水平差里有一块'
                              '是并进来的。'
                              + jump_txt(I19, LPL_ACQ_BRK, 'lpla_cash',
                                         lead='断点当月环比 '))
                if _LPL_IN_10 else '')
             + '右端粗体数字为当期指数值。' + GATE),
})

# ── Exhibit 11：融资余额 / 客户资产（杠杆强度，横截面归一化）──
_IT11 = [('schw', 'schw_mgn_pct', 'Schwab'),
         ('ibkr', 'ibkr_mgn_pct', 'IBKR'),
         ('hood', 'hood_mgn_pct', 'Robinhood')]
_i11 = dense_win(_IT11)
s11, inc11, exc11 = sr(_IT11, _i11)
ex.append({
    'n': N_MGNPCT, 'kind': 'lines_endlabels', 'fmt': 'pct1',
    'xlabels': xls(_i11), 'xstep': 2,
    'title': 'Margin balances as % of client assets', 'ylab': '% of client assets',
    'series': s11,
    'note': (firms_note(inc11, exc11, 'LPL 不披露融资余额。')
             + '把融资余额按各自的客户资产归一化 —— 这是横截面页真正独有的读法：'
             '绝对额只说明谁大，占比说明<b>同样一块客户资产上，谁的客户加了更多杠杆</b>。'
             f'注意分母口径三家略有差异（见 Exhibit {N_REB23} 的说明），'
             '且 Schwab 的分子含 short credits，'
             '所以水平值有系统性偏差，趋势与相对位次才是要看的。' + win_note(_i11) + GATE),
})

# ── Exhibit 12：客户现金 / 客户资产（利率敏感度，横截面归一化）──
_IT12 = [('lpla', 'lpla_cash_pct', 'LPL'),
         ('ibkr', 'ibkr_cash_pct', 'IBKR')]
_i12 = dense_win(_IT12)
s12, inc12, exc12 = sr(_IT12, _i12)
ex.append({
    'n': N_CASHPCT, 'kind': 'lines_endlabels', 'fmt': 'pct1',
    'xlabels': xls(_i12), 'xstep': 2,
    'title': 'Client cash as % of client assets', 'ylab': '% of client assets',
    'series': s12,
    # 这张图的断点最不能省：分子（现金）与分母（客户资产）在并表月跳的幅度不同，
    # 占比会**机械地**掉一截，看上去像「客户把现金投出去了」，其实是并购摊薄。
    **brks(_i12, LPL_ACQ_BRK),
    'note': (firms_note(inc12, exc12)
             + '现金占比是净利息收入的敏感度指标：占比下行意味着客户把现金投出去了，'
             f'同样的利率环境下 NII 的基数在缩。少的两家与 Exhibit {N_CASH} 同因 —— '
             'Schwab 月报不单列客户现金，Robinhood 的客户现金拆成两条不可合计的线。'
             + brk_note(_i12, LPL_ACQ_BRK,
                        tail='<b>并表月的占比下滑有一部分是机械的</b>：分子（客户现金）'
                             '与分母（客户资产）跳的幅度不同，占比自己就会掉一截 —— '
                             + dilution_txt(_i12, LPL_ACQ_BRK, 'lpla_cash_pct')
                             + '把这一段整个读成「客户把现金投出去了」是错的。')
             + win_note(_i12) + GATE),
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


for _t, _title, _extra in [
    ('schw', 'Schwab client assets y/y (%)', ''),
    ('lpla', 'LPL client assets y/y (%)', '2024-10（Atria +$88.3bn）与 '
                                          '2025-08（Commonwealth +$275.0bn）起的 12 个格子带着并购转入，'
                                          '不是有机增长；热力矩阵这个图型画不了断点竖线，'
                                          f'带断点线的同口径图见 Exhibit {N_YOY}，'
                                          f'剔并购后的有机口径见 Exhibit {N_ORG}。'),
    ('ibkr', 'IBKR client equity y/y (%)', ''),
    ('hood', 'Robinhood platform assets y/y (%)', 'Robinhood 的月度披露自 2023-04 起，'
                                                  '所以 y/y 自 2024-04 才有，矩阵行数少于另外三家。'),
]:
    if _t not in N_HEAT:
        continue
    _h = heat(N_HEAT[_t], _t, _title, _extra)
    if _h:
        ex.append(_h)

# 编号是图注的骨架：断一个号，「见 Exhibit N」就集体指错，而这种错人眼扫不出来。
# 这一条是**结构**不变量（只随成员与序列有无变化，不随窗口滚动），所以在这里硬拦。
_NS = [1] + [e['n'] for e in ex] + [N_TABLE]
if _NS != list(range(1, len(_NS) + 1)):
    raise SystemExit(f'Exhibit 编号不连续：{_NS} —— 有图被跳过而编号没跟着回收')


# 汇总表画不了断点线（表格没有 x 轴），所以 LPL 那一行的并购口径只能写进表注。
# 放在这里而不是 summary 的字面量里，是因为 drawn_for 要等 exhibit 全部建完才读得到 ——
# 图注不能声称画了一条其实没画的线。
_LPL_DRAWN = drawn_for(ex, LPL_ACQ_BRK)
if LP_RANK_TXT:
    summary['note'] += (
        'LPL 那行是 as-reported 口径，含 Atria（2024-10 +$88.3bn）与 '
        'Commonwealth（2025-08 +$275.0bn）两次整体并表，表格画不出断点线：'
        + LP_RANK_TXT
        + (f'这两次并表在 Exhibit {"、".join(str(n) for n in _LPL_DRAWN)} 上都画了'
           '红色竖虚线（客户资产与客户现金两族图都受影响）；'
           if _LPL_DRAWN else '')
        + f'剔并购后的有机口径见 Exhibit {N_ORG}。')


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
    'n': N_TABLE,
    'title': f'近 13 个月跨公司核对表（各家官方原始单位，未换算，统一截至 {mlab(LATEST)}）',
    'idx': '月份',
    'cols': [[c[1], c[2]] for c in TCOLS],
    'rows': [dict({'xl': mlab(p)},
                  **{c[2]: tcell(r[c[3]], c[4]) for c in TCOLS})
             for p, r in T13.iterrows()],
}


# ────────────────────────────── 口径与方法说明 ──────────────────────────────
_v = _v0                         # 同一件事只留一份实现


def _exl(ns):
    return '、'.join(str(n) for n in ns)


# 「本页哪些图上真的有红色竖虚线」一律从建好的 payload 现读，不手写编号 ——
# 断点会随窗口滚动进出，写死的那句话正是本轮复查抓到的第一类错（图注说画了、图上没有）。
_DRAWN = sorted({e['n'] for e in ex if e.get('break_at')})
_NO_BRK = sorted({e['n'] for e in ex
                  if e['kind'] in ('lines', 'lines_endlabels') and not e.get('break_at')})
_SCHW_DRAWN = drawn_for(ex, SCHW_NNA_BRK)
_HOOD_DRAWN = sorted(set(drawn_for(ex, HOOD_ND_BRK)) | set(drawn_for(ex, HOOD_CUST_BRK))
                     | set(drawn_for(ex, HOOD_TPA_BRK)))
_HEAT_NS = sorted(N_HEAT.values())
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
    f'另出一张四家同基期（2023-04）的图（Exhibit {N_REB23}）。'
    + (f'<b>有机增速也单独占一张（Exhibit {N_ORG_HOOD}）</b>：它的年化净流入常年是另外两家的'
       '四到十倍，与它们同轴会把 Schwab 与 LPL 压成贴零的一条带（原来就是这样，'
       'headline 写的「Schwab / LPL 各几个点」在图上根本读不出来）。'
       '同一单位不等于同一量纲，拆图不是回避比较 —— 两张图的纵轴单位相同，'
       '数值可以直接比大小，只是不要把线形叠着看。' if N_ORG_HOOD else ''),

    '<b>「可比」不等于「相同」，各图注已逐条标出差异。</b>客户资产的三种叫法'
    '（client assets / client equity / platform assets）都是「客户放在这家平台上的资产」，'
    '可直接并排；但日均交易的「一笔」三家定义不同（Schwab 数成交笔数、'
    'IBKR 报的是 Total Client DARTs、含不在 IBKR 清算的客户、Robinhood 是三个市场之和），'
    '融资余额里 Schwab 含 short credits 而另两家不含，'
    '账户口径 IBKR 数账户、Robinhood 数「有入金的客户」。'
    '这些图的<b>水平值只能当量级读，方向与拐点才是可比的信息</b>。',

    '<b>流量类不算环比百分比。</b>净新增资产是流量，环比百分比的分母是上个月的流量，'
    '一个月的噪音会被放大成趋势。按 GS「LPLA monthly metrics」的规矩改用<b>年化有机增长率</b>'
    f'（当月净流入 × 12 ÷ 上月末客户资产），见 Exhibit {N_ORG}'
    + (f' 与 Exhibit {N_ORG_HOOD}' if N_ORG_HOOD else '') + '。'
    '比率序列的差异一律用<b>百分点（pp/bp）</b>，不是「百分比的百分比变化」；'
    '<code>abs(v) &lt; 1</code> 时用 bp，否则用 pp（CONTRACT §2）。'
    '四舍五入之后正好是零的负数一律回正 —— 不印「-0bp」「-0.0%」这种带负号的零。',

    '<b>口径断点：图注说画了，图上就必须真有。</b>本页登记在册的断点有四组 —— '
    'LPL 的两次整体并表（Atria 2024-10 $88.3bn、Commonwealth 2025-08 $275.0bn，'
    '来自官方月报同页披露的 Acquired NNA，逐条硬编码在本脚本与 <code>build/lpla.py</code>，'
    '不是 CSV 的一列，改一处要改两处）、Schwab 2025-01 起把单一客户流入的剔除门槛从 $10bn '
    '提到 $25bn、Robinhood 的 Bitstamp（2025-06 起并入净流入与客户数）与 TradePMR / WonderFi。'
    + (f'<b>本轮真正画出红色竖虚线的是 Exhibit {_exl(_DRAWN)}</b>'
       f'（其中 LPL 并表 {_exl(_LPL_DRAWN)}'
       + (f'、Schwab 门槛 {_exl(_SCHW_DRAWN)}' if _SCHW_DRAWN else '')
       + (f'、Robinhood {_exl(_HOOD_DRAWN)}' if _HOOD_DRAWN else '')
       + '），语义一律是「从这一期起<b>这一条线</b>与左侧不可比，同图的其他公司不受影响」。'
       if _DRAWN else '本轮没有任何断点落在各图窗口内，故一条竖虚线都不画。')
    + (f'没有断点线的折线图是 Exhibit {_exl(_NO_BRK)}：它们画的序列在各自窗口内没有登记在册的'
       '口径变化（或断点已滚出窗口）。' if _NO_BRK else '')
    + f'Exhibit 1 汇总表与 Exhibit {_exl(_HEAT_NS)} 热力矩阵的图型不支持断点线'
    '（表格与矩阵都没有连续 x 轴），改在各自的表注 / 图注里写明。'
    '断点一旦滚出窗口，线与图注文案会<b>一起</b>消失，不会剩下一句「红色竖虚线 = …」的空话。'
    + (f'LPL 当期的量级：{LP_RANK_TXT}' if LP_RANK_TXT else ''),

    f'<b>横截面页独有的两张归一化图。</b>Exhibit {N_MGNPCT}（融资余额 / 客户资产）与 '
    f'Exhibit {N_CASHPCT}（客户现金 / 客户资产）把余额按各自的客户资产归一化：'
    '绝对额只说明谁大，占比说明「同样一块客户资产上，谁的客户加了更多杠杆 / 留了更多现金」。'
    '分子分母的口径差异（见上）会造成系统性水平偏差，趋势与相对位次才是要看的。'
    f'并表月要特别小心：Exhibit {N_CASHPCT} 的分子与分母跳的幅度不同，占比会机械地掉一截，'
    '看着像「客户把现金投出去了」，其实是并购摊薄，图注里已给出 bp 与它占全窗口变动的比例。',

    '<b>缺的月份不补、不连。</b>Schwab 的月末融资余额与 DATs 都是 2026-01 的月报才开始披露'
    f'（滚动表回溯至 2025-01），所以它在 Exhibit {N_MGN}、{N_DATS} 的线在窗口左段是断的 —— '
    '那是没有披露，不是余额为零。所有非有限值一律写 <code>null</code>，图与表都断开，不画假点。',

    f'<b>纵轴。</b>重定基图（Exhibit {N_REB18}、{N_REB23}、{N_REB19}）沿用 deck 的自适应量程，'
    '各条线右端标出当期指数值 —— 长历史图上那是唯一的绝对水平锚点，没有它只能靠网格线目测；'
    '各条线本来就都从基期的 100 起画（图的左缘就是基准），故不再另画一条 100 的水平参考线。'
    f'Exhibit {N_ORG} 用了截轴（0–{EX5_CAP:.0f}%）：'
    '<b>截轴不删点</b> —— 超界的点画成空心红圈、真值竖排标在图上，表格视图里给的也是真值。'
    '本站没有对数轴，量级差太远的序列一律拆图而不是压缩坐标。',

    f'<b>窗口。</b>近期多线图 {WIN} 个月、核对表 13 个月、热力矩阵最多 7 年，'
    '全部从共同最新月倒推；重定基图从各自基期画到共同最新月。'
    '所有数值与格式化都在 Python 侧完成，页面不做任何计算 —— '
    '同一个数字在两个语言里各算一遍，迟早会出现图上与表里对不上而没人发现。'
    '汇总表的 3Y %ile 也一样：判据在 <code>build/pctile.py</code>，全站 14 个生成器共用一份 '
    '（回放近 24 个月，≥70% 的月份钉在端点就留空）。'
    '本页曾用「≥90% 的月环比不降」这个代理判据，结果同一条 LPL total client assets 在 '
    '/lpla/ 被判成噪音留空、在本页却印成绿色 100 —— 判据是口径，口径只能有一处定义。',
]

headline = (f'共同最新月 {mlab(LATEST)}（短板 {LAG}）'
            f' · 客户资产 Schwab {_v("schw_assets", 0, "$")}bn / LPL {_v("lpla_assets", 0, "$")}bn'
            f' / IBKR {_v("ibkr_assets", 0, "$")}bn'
            + (f' / Robinhood {_v("hood_assets", 0, "$")}bn' if 'hood' in HAS else '')
            + f' · 年化有机增速 Schwab {_v("schw_org", 1)}% / LPL {_v("lpla_org", 1)}%'
            + (f' / Robinhood {_v("hood_org", 1)}%' if 'hood' in HAS else '')
            # 头条只报 as-reported 的 LPL y/y 就是只报喜：那 +38% 里有一大块是买来的。
            # 有剔并购口径就把两个数一起给，没有（缺月）就一个都不给。
            + (f' · LPL 客户资产 y/y {signed(_LP_YOY_NOW, 1, "%")}'
               f'（剔并购 {signed(LP_YOY_EX, 1, "%")}）'
               if _LP_YOY_NOW is not None and LP_YOY_EX is not None else ''))


# ── 这里原来有一个 `_lp_cash_clause()`：brief 里 LPL 客户现金占比的那一句 ──
# 整句撤了（理由见 compose_brief 的「分寸」一节），函数跟着删掉 —— 留一个没人调用的
# 生成器，下一个人只会照它把句子接回去，而接回去的正是本轮要收的那一层。
#
# 它当年修对的两件事记在这里，谁要重写这一句必须一并带上：
#   1. 占比的**分母**被 2025-08 并入 Commonwealth（Acquired NNA +$275.0bn）机械摊薄，
#      极值断言（「N 个月最低」）必须先用 `acq_roll12()` 还原再判，还原后仍是最低才
#      许写「最低」—— 与客户资产 y/y 的剔并购是同一条约定，口径只能有一处定义。
#   2. 不许用「亦然」承接 IBKR 那句：IBKR 那句里有「绝对额创新高」与「摊薄非撤资」，
#      而 LPL 的现金绝对额离 2022-06 的自身峰值还差一大截，承接过来就是假话。
# 并表当月对这条比率的一次性摊薄仍在 Exhibit 12 的图注里现算（dilution_txt），
# 没有随这一句消失。


def compose_brief(df, latest):
    """横截面页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 /
    R4 单位恒等 / R5 标注 / R6 有效位），那边只算事实，句子在这里拼 ——
    措辞是口径的一部分，属于各家自己。每个数字都当场从序列算，**没有一处硬编码**：
    共同最新月、领先几个月、齐备几家、名次、「N 个月最高/最低」、峰值停在哪个月，
    下个月重跑全部自己变。

    ═══ 横截面页独有，单票页不能照抄 ═══
      · **第一句必须是「能不能比」，不是「谁更强」。** 单票页的读数就是那家的最新读数；
        本页统一定格在<b>共同最新月</b>（最慢的成员决定），各家自己往往已多披露 1-2 个月。
        不先说这一句，读者会拿本页的横比当「当下」，而它是一个被最慢那家钉住的旧截面。
      · **可比性是分层的，按指标族逐族点名。** 四家齐备的只有客户资产一族；客户现金
        （Schwab 不单列、Robinhood 拆成不可合计的两条）与账户存量（IBKR 数账户、
        Robinhood 数人）各只剩两家。把只有两家的族当成「四家横比」是本页最大的误读源。
      · **「谁创新高」在横截面上受序列长度左右**（R1 的横截面变体）。Schwab 的月末融资
        余额只有 2025-01 起的历史、Robinhood 只有 2023-04 起，IBKR 有 2016-01 起 ——
        在一条 17 个月的序列上「停在峰值」与在 125 个月上「峰值停在 2017 年」根本不是
        同一件事。单票页没有这个问题，所以这句话别家写不出来。
      · **LPL 的名次要按还原口径报**：as-reported 的客户资产 y/y 含 Atria 与
        Commonwealth 两次整体并表，剔掉滚动 12 个月的 Acquired NNA（`acq_roll12()`）
        之后名次会掉，句子里必带「（还原口径）」（R5）。这条约定对**任何**以 LPL 客户
        资产为分母的比率同样成立：分母被并表机械摊薄，极值断言（「N 个月最低」）必须
        先还原再判，还原后不成立就不许写「最低」。现金占比那一句本轮整句撤了
        （见下方「分寸」），约定留着 —— 谁要把它写回来，得连着还原一起写回来。
      · **R3（日历护栏）在本页全程不适用**：本页没有任何「当月合计量」列 —— 客户资产 /
        现金 / 融资余额都是月末时点值，DATs/DARTs 三家披露的本来就是<b>日均</b>笔数。
        再除一次交易日会造出一个根本不存在的修正（brief.py 开头点名的那个坑）。

    ═══ 措辞由当场算出的量决定分支，一个定性词都不许写死 ═══
      「只有 / 创新高 / 最低 / 却」这类词全部挂在当月算出的名次、占比、`peak_scan`
      的分组上：本月读着通顺的句子，下个月数字一变就会变成假话，而那种假话没有任何
      自动检查拦得住（历史重放是唯一能逮到它的手段）。同理，缺值月一律**该句不写**
      （`B.need`），不是让整页构建失败。

    ═══ 分寸：以 build/ibkr.py 的 compose_brief() 为准 ═══
    那一版是用户逐句验收过的标准，既是上限也是下限 —— 四句四层、一句一个意思、~300 字。
    本页此前是六句，且句句是三四个从句的串联：比样板花哨。收的办法不是砍字数，是砍层数。

    现在五句，比样板多的那一层是开头的「能不能比」（横截面页的身份，不能省）：

        能不能比（时点 + 覆盖）→ 谁领先（还原口径下名次会不会翻）
        → 基数（上月名次解释本月读数）→ 谁背离（绝对额与归一化占比同月一头一尾）
        → 峰值的可比性（「在自身峰值」在 17 个月和 125 个月的序列上不是同一件事）

    撤掉的是「LPL 客户现金占比亦为全样本最低，降幅 X% 来自 Commonwealth 并表当月」
    那一句。它不是错的（「极值先还原再判」那一层是对的，约定见上），是**逐家展开**：
    紧接着 IBKR 现金那句再讲第二家的同一个指标，读者拿到的是第二个例子而不是第二个
    层次；句尾「降幅的 X% 来自并表当月」还多压了一层贡献度拆解。跨公司比较写到
    「谁领先谁背离 + 口径可比性的边界」就够，再往下就是把横截面页写成四份单票页。
      （旁证：历史重放里它在 2018-2020 一路印出「LPL 占比排倒数前100%」—— 序列还短的
      月份里「倒数前 100%」等于没说，一句自己就撑不住的话不值得占掉整整一句的篇幅。）

    口径标注（推导值 / 还原口径 / 并购并表）一个都不因为收篇幅而删：那不是花哨，
    是诚实。被撤的是整句，不是某句的标注。
    """
    i = len(df.index) - 1
    MO = [str(p) for p in df.index]
    # 「两个月 / 两家」这条中文量词规矩已经由 brief.cn() 统管（序数写「第二」时传
    # ordinal=True），本页不再自己包一层 —— 同一条规矩在两处定义，早晚会分叉。
    cn = B.cn
    fin = lambda a: int(np.isfinite(np.asarray(a, float)).sum())

    # ── 边界一（时点）：本页的读数不是各家自己的最新读数 ──────────────────
    # 只点名跑得最快的那一家 + 领先几个月：四家逐一列月份会把这一句撑到整段的三分之一，
    # 而页脚已经逐家列过。这里要读者记住的是「本页不是当下」这一件事。
    # 「本页定格在共同最新月」抬头已经印过（headline / subtitle 各一次），这里不复述，
    # 只写抬头给不出的那一半：领先的那家多披露了几个月、而本页不取。
    ahead = [(t, (LATEST_EACH[t] - latest).n) for t in RAW if LATEST_EACH[t] > latest]
    if ahead:
        t0, gap = max(ahead, key=lambda x: (x[1], x[0]))
        ahead_txt = f'本页不取 {NAME[t0]} 多出的{cn(gap)}个月'
    else:
        ahead_txt = '各家最新月一致'

    # ── 边界二（覆盖）：可比性是分层的，逐族点名齐备几家 ────────────────────
    FAMS = [('客户资产', ['schw_assets', 'lpla_assets', 'ibkr_assets', 'hood_assets']),
            ('净流入', ['schw_flow', 'lpla_flow', 'hood_flow']),
            ('融资余额', ['schw_margin', 'ibkr_margin', 'hood_margin']),
            ('日均交易', ['schw_dats', 'ibkr_dats', 'hood_dats']),
            ('客户现金', ['lpla_cash', 'ibkr_cash']),
            ('账户存量', ['ibkr_accounts', 'hood_accounts'])]
    cnt = {nm: sum(1 for c in cs if c in df.columns and np.isfinite(df[c].loc[latest]))
           for nm, cs in FAMS}
    full = [nm for nm, k in cnt.items() if k == len(HAS)]
    kmin = min(cnt.values())
    # kmin == 成员数意味着六族全齐，那时「最窄的是谁」是个没有内容的句子，整句省掉
    narrow = [nm for nm, k in cnt.items() if k == kmin] if kmin < len(HAS) else []
    # 月份本身抬头已经印过（「共同最新月 May-26（短板 …）」），这里不再复述
    # 「只有」这类量词由 B.quant 按占比给：齐备的族数是当场数出来的，写死「只有」
    # 会在六族齐备的那个月印出「六族里齐备的只有六族」。
    if not full:
        s1 = f'能不能比：{ahead_txt}；{cn(len(FAMS))}族没有一族{cn(len(HAS))}家齐备。'
    else:
        s1 = (f'能不能比：{ahead_txt}；'
              f'{B.quant(len(full), len(FAMS), "族")}{cn(len(HAS))}家齐备'
              f'（<b>{"、".join(full)}</b>）'
              + (f'，{"、".join(narrow)}各{cn(kmin)}家。' if narrow else '。'))

    # ── 相对表现 + R5：名次一律按还原口径报 ─────────────────────────────
    # LP_YOY_EX 是当期的模块级常量，这里改成按 latest 现算 —— 否则把序列截到历史某月
    # 重放时，用的还是当期那个 t12，名次会算在一个不属于那个月的还原口径上。
    yy = {NAME[t]: float(df[f'{t}_yoy'].loc[latest]) for t in ('schw', 'lpla', 'ibkr', 'hood')
          if t in HAS and f'{t}_yoy' in df.columns and np.isfinite(df[f'{t}_yoy'].loc[latest])}
    order = sorted(yy, key=yy.get, reverse=True)
    lp_ex, _t12 = lp_yoy_ex(df, latest)
    s2 = ''
    if len(order) >= 2 and lp_ex is not None and NAME['lpla'] in yy:
        adj = dict(yy, **{NAME['lpla']: lp_ex})
        order2 = sorted(adj, key=adj.get, reverse=True)
        r0, r1 = order.index(NAME['lpla']) + 1, order2.index(NAME['lpla']) + 1
        # 完整位次留给 Exhibit 1 与 Exhibit 4 的端点标签，「谁居首」也留给它们 ——
        # 位次表本身不是解读（本页第一句的职责是「能不能比」而不是「谁更强」），
        # 只有 LPL 那一处**名次会翻**才是。
        a0, a1 = cn(r0, ordinal=True), cn(r1, ordinal=True)   # 序数写「第二」不是「第两」
        s2 = '客户资产 y/y 剔并购（还原口径）后 LPL '
        s2 += (f'从第{a0}掉到第{a1}、与 {order2[r1 - 2]} 换位。' if r1 > r0
               else f'仍居第{a1}。')
    else:
        # 早年的月份 y/y 根本凑不齐（Schwab 2018-05 起、LPL 2018-07 起、HOOD 2023-04 起，
        # 各自要满 12 个月才有分母）。那时这一句改说「谁还进不了这个横比」——
        # 这仍是「能不能比」，比硬凑一个两家的名次表有用。
        young = [NAME[t] for t in ('schw', 'lpla', 'ibkr', 'hood')
                 if t in HAS and NAME[t] not in yy]
        if young and yy:
            s2 = (f'客户资产 y/y 这个月只有{cn(len(yy))}家算得出，{"、".join(young)} '
                  f'的 12 个月前分母还缺，横比先看水平值。')
        elif len(order) >= 2:
            # 还原口径算不出来（缺 LPL 的分母）时，只报能报的两端，不写半句还原
            s2 = f'客户资产 y/y 里 {order[0]} 居首、{order[-1]} 垫底。'

    # ── R2 基数护栏：有机增速上月落在全样本底部，本月的环比要对着它读 ──────
    # 这里刻意不报环比（本页规矩：流量类不算环比百分比，比率类的 m/m 用 pp 且已在
    # Exhibit 1 里印过），只报**排名** —— 排名才是「环比看着猛」的解释。
    # 「跌到 / 回升」这类方向词一律不写：它们描述的是上上月→上月、上月→本月的走向，
    # 而句子里给的是名次，两者下个月未必同向（一家升一家跌时「同时跌到」就是假话）。
    ORG = [(t, f'{t}_org') for t in ('schw', 'lpla')
           if t in HAS and f'{t}_org' in df.columns and np.isfinite(df[f'{t}_org'].loc[latest])]
    rows = []
    for t, c in ORG:
        a = df[c].values
        n = fin(a)
        be = B.base_effect(a, i)
        if be['prev_rank'] is None or be['rank'] is None or n < 2:
            continue                       # 上月缺值：这一家不进句子，而不是让整页失败
        rows.append((NAME[t], n, be['prev_rank'], be['rank']))
    s3 = ''
    if rows:
        # 「第 65/96」把名次与样本长度绑成一个自足的词 —— 各家序列长度不同，
        # 光给名次没法比。名次与年化与否无关（同一条序列同乘 12），故省掉「年化」两个字。
        #
        # 排法从「公司名一串、上月名次一串、本月名次一串」改成**一家一段**：原来的
        # 「Schwab、LPL … 上月同落全样本倒数第 7、4，本月仍只第 65/96、77/94」要读者
        # 在三串并列之间来回 zip 才知道哪个数属于谁，是全段最难读的一句。
        # 两个月都用同向的「第 x/n」（不再上月说倒数、本月说正数）：一句话里换一次
        # 方向，读者就得先判断这个名次是从哪头数起。
        #
        # 句尾那个 all() 算出来的「仍只」一并去掉：一个词同时替两家下结论，
        # 一升一降的月份必然对其中一家失真，而「第 65/96」本身已经把高低说清楚了。
        s3 = ('基数：有机增速（推导值）的全样本名次，'
              + '；'.join(f'{nm} 上月第 {prv}/{n}、本月第 {cur}/{n}'
                          for nm, n, prv, cur in rows) + '。')

    # ── 口径背离（R1 + R4）：绝对额与归一化占比同月一个到顶、一个到底 ─────
    # 「创新高 / 却 / 最低」全部挂在当月名次上。绝对额未必每月都在最前、占比也未必
    # 每月都在最后，任何一个写死的方向词都会在某个月与它自己引用的数字打架。
    cash, ast = df['ibkr_cash'].values, df['ibkr_assets'].values
    cpct = df['ibkr_cash_pct'].values
    s4 = ''
    if i >= 12 and B.need(cash[i], cash[i - 12], ast[i], ast[i - 12], cpct[i]):
        pu = B.per_unit(cash, ast, i, scale=100.0)
        n_c, n_p = fin(cash), fin(cpct)
        r_hi, r_lo = B.rank_of(cash, i), B.rank_of(-cpct, i)
        # T3：绝对额若几乎只增不减，「N 个月最高」每月都成立，是噪音不是信息
        mono = B.is_monotonic(cash)
        top = f'创 {n_c} 个月新高' if (r_hi == 1 and not mono) else f'排{B.top_pct(r_hi, n_c)}'
        # 两条回溯长度相同才叫「同期」：那才准确说出「同一段历史里一个到顶、一个到底」
        bot = (('落到同期最低' if (r_hi == 1 and n_c == n_p and not mono)
                else f'落到 {n_p} 个月最低')
               if r_lo == 1 else f'在倒数{B.top_pct(r_lo, n_p)}')
        diverge = not mono and r_hi / n_c <= 1 / 3 and r_lo / n_p <= 1 / 3
        s4 = f'IBKR 现金绝对额{top}、占比{"却" if diverge else "则"}{bot}'
        # R4：只报两个增速之商，不做「一半分子一半分母」的比例拆分（那在数学上就是错的）
        if B.need(pu.get('yoy'), pu.get('num_yoy'), pu.get('den_yoy')):
            # 落点按**两个增速的大小关系**分支，不是只按分子的正负。
            # 原来写的是「分子涨就叫摊薄」：历史重放里 113 个可算月份中有 22 个
            # （2022 全年、2020-03/04 等）分母同比是负的，占比其实在升，句子却紧挨着
            # 「现金 +12.7% ÷ 资产 -18.9%」印出「摊薄非撤资」—— 定性词与它自己引用的
            # 两个数字打架。摊薄的定义就是分母跑得比分子快，判据只能是 den > num。
            n_yy, d_yy = pu['num_yoy'], pu['den_yoy']
            land = ('分子自己在缩' if n_yy <= 0 else
                    '摊薄非撤资' if d_yy > n_yy else '分子跑赢分母')
            s4 += (f'（推导值：现金 {B.pct(n_yy)} ÷ 资产 {B.pct(d_yy)}，'
                   f'<b>{land}</b>）')
        s4 += '。'
        # 这里曾经再接一句 LPL 的现金占比（「亦为全样本最低，降幅 X% 来自 Commonwealth
        # 并表当月」）。撤掉的理由见本函数 docstring 的「分寸」：同一个指标换第二家讲
        # 是逐家展开，读者拿到的是第二个例子而不是第二个层次。
        # **要写回来就得连着还原一起写回来**：LPL 的占比分母被并表机械摊薄，
        # 极值断言必须先用 acq_roll12() 剔掉滚动 12 个月的 Acquired NNA 再判，
        # 还原后不成立就不许写「最低」。

    # ── R1 的横截面变体：「谁在峰值」受各家披露起点长短左右 ──────────────
    MG = [(NAME[t], f'{t}_mgn_pct') for t in ('schw', 'ibkr', 'hood')
          if t in HAS and f'{t}_mgn_pct' in df.columns and np.isfinite(df[f'{t}_mgn_pct'].loc[latest])]
    pk = B.peak_scan(MO, [(nm, df[c].values) for nm, c in MG], i)
    ln = {nm: fin(df[c].values) for nm, c in MG}
    at, off = pk['at_peak'], pk['off_peak']
    # 分母用**真扫过的条数**，不是 len(MG)：被 skip_monotonic 剔掉的那条既不在 at_peak
    # 也不在 off_peak，拿 len(MG) 当分母会让「三条里只有一条」的三与实际扫描数对不上。
    n_scan = len(at) + len(off)
    # 被剔掉的必须点名。否则某家一旦越过 is_monotonic 的 0.9 阈值（Schwab 实测 0.875，
    # 只差 0.025），它会静悄悄从扫描里消失，而句子仍在替它下结论。
    skip = f'（{"、".join(pk["skipped"])} 几乎只增不减，未入扫描）' if pk['skipped'] else ''
    s5 = ''
    if at and off:
        nm_at = min(at, key=lambda x: ln[x])           # 历史最短的那条：「在峰值」最不值钱
        ref, refm = max(off, key=lambda x: ln[x[0]])
        s5 = (f'{cn(n_scan)}条融资余额占比（推导值）'
              f'{B.quant(len(at), n_scan, "条")}在自身峰值：{nm_at} 仅 {ln[nm_at]} 个月，'
              f'{ref} 的 {ln[ref]} 个月峰值在 {refm}{skip}。')
    elif off and n_scan == 1:
        # 只剩一条时不写「一条里无一条」：那句话读起来像模板没拼好
        ref, refm = off[0]
        s5 = (f'融资余额占比（推导值）本月只有 {ref} 一条有数{skip}，'
              f'它也不在自身峰值 —— 峰值停在 {refm}。')
    elif off:
        ref, refm = max(off, key=lambda x: ln[x[0]])
        s5 = (f'{cn(n_scan)}条融资余额占比（推导值）里无一条在自身峰值{skip}，'
              f'历史最长的 {ref} 峰值停在 {refm}。')
    elif at:
        nm_at = min(at, key=lambda x: ln[x])
        s5 = (f'{cn(n_scan)}条融资余额占比（推导值）本月全部在自身峰值{skip}，'
              f'但最短的 {nm_at} 只有 {ln[nm_at]} 个月历史 —— 长短不同不是同一件事。')

    return B.render([s1, s2, s3, s4, s5])


BRIEF = compose_brief(df, LATEST)

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
    # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': BRIEF,
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

# 官方发布日：取**实际入选本页的成员**里最晚的那一个 —— 本页统一截到共同最新月，
# 所以「这一页什么时候成立」等于最后发布那一家的日子（当前是 LPL，每月中旬才发）。
# 查的是 LATEST 这个共同月而不是各家自己的最新月，否则会把某家更新月份的发布日
# 安到本页画的旧月份上。用 HAS 而不是 MEMBERS：还没就绪的成员根本没画进来，
# 把它算进 max 会让日期凭空推后。任何一家查不到就整个字段省略。
SOURCE_DATE = repo.latest_source_date(sorted(HAS), {t: LATEST for t in HAS})
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE


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
