# -*- coding: utf-8 -*-
"""CME Group (CME) 月度成交量 —— 网页看板数据生成器（build/build_cme.py 的移植）。

原 deck：build/build_cme.py（matplotlib → PDF）。本文件把它的每一张 exhibit
重新实现成 data/cme.js 里的一个 payload 对象，页面（assets/page.js + charts.js）
只负责画，不做任何计算。

模版来源（照抄原 deck 的 docstring）：
  · Goldman Sachs「IBKR Monthly」成对图法（水平柱 + 次轴 y/y 折线 ⇄ 变化率曲线）
    与 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法
  · Barclays「IBKR July Monthly Metrics」的 day-count 调整 —— 该报告因交易日数差异，
    把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径反转。CME 官方 xlsx 里
    直接给了每月交易日数，故本页用 Exhibit 3 显式呈现总量口径与按日口径的差。
数据源：CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），
        次月第 1-2 个工作日。费率取 series/fee_rates.csv 里的季度 RPC。

读取：  series/cme.csv、series/fee_rates.csv（唯一数据源，不读 build/data/）
输出：  data/cme.js

幂等：payload 里不放构建日期（只写文件首行注释），不用随机数，窗口一律从数据
      最新月倒推 —— 同一份 CSV 重复跑，输出逐字节相同（除首行）。
"""
import datetime
import importlib.util
import json
import os

import numpy as np
import pandas as pd

import payload_guard
import pctile
import yoy as YOY                       # 同比口径的唯一实现，见 build/yoy.py 的模块头

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
OUT = os.path.join(ROOT, 'data', 'cme.js')

# 发布日台账在仓库根，不在 build/ —— `python3 build/cme.py` 时 sys.path 上只有 build/，
# 裸 import 找不到，只能按路径加载。
_sd_spec = importlib.util.spec_from_file_location(
    'source_dates', os.path.join(ROOT, 'source_dates.py'))
source_dates = importlib.util.module_from_spec(_sd_spec)
_sd_spec.loader.exec_module(source_dates)

SRC = 'Source: CME Group monthly volume reports; format after Goldman Sachs GIR / Barclays'

# 资产类别 →（CSV 列, 图例名, 引擎色名）。
# 原 deck 的金属用 gsx.GOLD(#BF9000)，charts.js 的 C.* 里没有金色（engine_kinds.md
# 明确说了这一点）—— 后来在 charts.js 的 C.* 里补上了 GOLD(#BF9000)，与 gsx.py 同色，
# 所以金属恢复用 GOLD。不能拿 RED 当数据色：RED 在这套语言里是断点与离群值的专用色，
# 一根红柱到底是「金属品种」还是「这个点被截轴了」会分不清。
CLS = [('adv_rates_kcontracts', 'Interest rates', 'NAVY'),
       ('adv_equity_kcontracts', 'Equity index', 'MBLUE'),
       ('adv_energy_kcontracts', 'Energy', 'BLUE'),
       ('adv_ag_kcontracts', 'Agricultural', 'GRAY'),
       ('adv_fx_kcontracts', 'FX', 'GREEN'),
       ('adv_metals_kcontracts', 'Metals', 'GOLD')]

# 原 Exhibit 5「ADV by asset class」把六个品种画在同一根轴上。利率品种的峰值 21,327
# 独自定死了 0–25,000 的量程，能源 / 农产品 / 外汇 / 金属四条线全被压进 0–3,000 那条
# 窄带里互相叠着，浅蓝 / 灰 / 绿 / 金四色在那个厚度下分不出走势 —— 整张图实际只读得出
# 利率和股指两条。
# 这里按量级拆成两张：不同量级本来就不该共用一根轴。不用 ycap 的原因是截轴是给「少数
# 几个离群点」用的 —— 这里要截掉的是整整两条序列的 25 个点，那不是标注离群值，
# 是把两条主力序列全画成红圈。
CLS_MAJOR = CLS[:2]     # 利率 + 股指：5,500 – 21,300
CLS_MINOR = CLS[2:]     # 能源 / 农产品 / 外汇 / 金属：540 – 5,100

# 品种曲线图（原 Exhibit 5）拆成两张后，后面所有 exhibit 号整体后移一位。号码写死在
# 十几处图注与说明里，靠人肉数是要出错的（原 PDF 的汇总表脚注就把 Exhibit 3 写成了
# Exhibit 4），所以统一在这里定名，正文一律引用常量。
EX_ADV, EX_DAYCOUNT, EX_MIX = 2, 3, 4
EX_MAJORS, EX_MINORS = 5, 6          # 品种曲线：两大品种 / 四小品种，见下方拆图说明
EX_HIST, EX_QTR, EX_OI = 7, 8, 9
EX_RATES, EX_EQUITY, EX_ENERGY = 10, 11, 12
EX_REV, EX_RPC = 13, 14
EX_FX, EX_METALS, EX_AG = 15, 16, 17
EX_HEAT_YOY, EX_HEAT_SHARE = 18, 19
# 20/21 是后加的两张（量价分解与 TTM 量），一律**追加在末尾**，前面的号一个都没动；
# 核对表因此由 20 顺延到 22 —— 它本来就排在所有图之后，号跟着走才不会出现
# 「18、19、22、20、21」这种读者以为漏图的序列。全文引用一律走这些常量。
EX_DECOMP, EX_TTMVOL = 20, 21
EX_TABLE = 22

WIN_BAR = 13     # gs_bar 类近期图：契约 §5.4「近期图固定 13 个月」
WIN_LINE = 25    # 曲线类图：照搬原 deck 的 win=25
WIN_QTR = 14     # 季度柱：照搬原 deck 的 win=14
HEAT_YEARS = 10  # 热力矩阵：照搬原 deck 的 n_years=10
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ZH_MONTH = '一二三四五六七八九十十一十二'


def mlab(p):
    """与 gsx.mlab 一致：Period('2026-07') → 'Jul-26'。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def qlab(q):
    """季度 Period → '2026-Q2'，与 series/fee_rates.csv 的 period 写法一致。

    pandas 的 str(Period) 给的是 '2026Q2'，和费率表里的 '2026-Q2' 差一个连字符；
    图注要让读者能拿着这个季度号回 CSV 里直接 grep，所以统一成 CSV 的写法。
    """
    return f'{q.year}-Q{q.quarter}'


def num(v, dec=0):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def pct(v, dec=1):
    """带符号的百分比变化，正负号交给 f-string 的 + 标志。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+,.{dec}f}%'


def pp(v, dec=1):
    """百分点差（比率类指标的差异一律用 pp）。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


# ══════════════════════════ 1. 读数据（只读 series/*.csv）══════════════════════════
def load():
    p = os.path.join(SERIES, 'cme.csv')
    df = pd.read_csv(p)
    need = ['month', 'adv_total_kcontracts', 'oi_total_contracts', 'trading_days'] + \
           [c for c, _, _ in CLS]
    miss = [c for c in need if c not in df.columns]
    if miss:                                     # 失败要响：绝不静默写 NaN 上线
        raise SystemExit(f'series/cme.csv 缺列 {miss}')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
    if set(gaps) != {1}:
        bad = [str(df.index[i]) for i in range(1, len(df)) if (df.index[i] - df.index[i - 1]).n != 1]
        raise SystemExit(f'series/cme.csv 月份不连续，断在 {bad}')
    for c in need[1:]:
        if df[c].isna().any():
            raise SystemExit(f'series/cme.csv 的 {c} 有缺值，无法画连续序列')
    return df.astype(float)


def rpc_quarterly(metrics):
    """从 series/fee_rates.csv 取 CME 的季度 RPC（$/张）。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[d['company'] == 'CME']
    out = {}
    for key, metric in metrics:
        s = d[d['metric'] == metric]
        if not len(s):
            raise SystemExit(f'fee_rates.csv 里没有 CME/{metric}')
        u = set(s['unit'].dropna())
        if u != {'USD_per_contract'}:
            raise SystemExit(f'CME/{metric} 单位不是 USD_per_contract：{u}')
        q = pd.PeriodIndex(s['period'].str.replace('-', ''), freq='Q')
        out[key] = pd.Series(s['value'].astype(float).values, index=q).sort_index()
    return out


def to_monthly(rate_q, month_index):
    """季度费率 → 月度：当季各月用该季费率；最新季之后沿用最后一个已知值（同 bridge.to_monthly）。"""
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(qq, np.nan) for qq in q], index=month_index, dtype=float).ffill()


# ══════════════════════════ 2. 派生序列（照抄原 deck 的算法）══════════════════════════
df = load()
adv = df['adv_total_kcontracts']
days = df['trading_days']
LATEST = df.index[-1]

df['total_vol_mn'] = adv * days / 1000.0                    # 月度总成交量 = ADV x 交易日（百万张）
df['adv_mn'] = adv / 1000.0
df['oi_total_mn'] = df['oi_total_contracts'] / 1e6
df['vol_yoy'] = df['total_vol_mn'].pct_change(12) * 100
df['adv_yoy'] = adv.pct_change(12) * 100
df['daycount_effect'] = df['vol_yoy'] - df['adv_yoy']       # 两者之差 = 交易日数贡献
df['rates_share'] = df['adv_rates_kcontracts'] / adv * 100


# ══════════════════ 同比口径：次轴一律画 12 个月滚动合计同比 ══════════════════
# 单月同比 = 本月 ÷ 去年同月 − 1，它把「去年那**一个**月碰巧是什么样」整个塞进分母。
# 去年同月若是异常低点，今年一个平淡的月份也能印出三位数的增速；反过来同理。后果不是
# 「噪声大一点」，而是**方向会反**：同一条序列的单月同比与 12 个月滚动合计同比经常符号
# 相反，图上讲的是反的故事，而读者从图上完全看不出来。本页的实测数字由 caliber_stats()
# 现算（见 NOTES 的口径条与各图图注），一个都没有写死。
#
# 因此本页所有 gs_bar 的次轴金色折线改画「12 个月滚动合计同比」：
#     最近 12 个月合计 ÷ 上一个 12 个月合计 − 1
# 实现上取滚动**均值**再相比 —— 窗口固定 12 个月，除以 12 是同一个常数，所以
# 「滚动均值同比」与「滚动合计同比」逐点严格相等；用均值的好处是对 ADV 这类日均值源列
# 单位不变（仍是「千张/日」），读者不必在脑子里换算。
#
# 要不要乘交易日数？**不乘。** 本页 Exhibit EX_DAYCOUNT 的既定立场是「ADV 已按交易日
# 中性化」，而实测（DAYCOUNT_STATS）显示交易日效应在 12 个月窗口里基本自抵：日均口径与
# 交易日加权口径的滚动同比标准差只差零点几个百分点、符号相反的月份集合完全相同。为这点
# 差别在同一页里引入第二套聚合口径，代价远大于收益 —— 而「同一页两套同比口径」正是读者
# 会把不可比的数放在一起读的地方。
# ⚠ **存量序列不适用**。month-end OI 这类期末快照走的是点对点同比（YOY.mom_yoy）：
# 把 12 个月末的 OI 加起来不是任何东西 —— 既不是「一年的量」（存量不累积），也不是
# 「平均水平」（没除以 12）。而且存量本来就不吃日历效应，单月同比在它上面稳得多
# （本页实测 OI 的两种口径标准差只差 1.2 倍，成交量类差 2 倍以上）。
# 判据与实现都在 build/yoy.py，本文件只负责说清「这一列是流量还是存量」。
ROLL = 12


def roll_yoy(s):
    """12 个月滚动合计同比（%），**流量序列专用**。委托给 build/yoy.py。

    前 23 个点必然为 NaN：12 个月填窗 + 12 个月比较。
    滚动合计与滚动均值的同比逐点严格相等（除以 12 是同一个常数），所以对 ADV 这类
    日均值源列，读者可以把它读成「近 12 个月的平均 ADV 相对上一个 12 个月」。
    """
    return YOY.ttm_yoy(pd.Series(s), YOY.FLOW)


def caliber_stats(s, kind=YOY.FLOW):
    """单月同比 vs 12 个月滚动合计同比的实测对比（图注里引用的数字全由此现算）。

    只做键名适配：真正的统计（样本对齐、相邻月跳变、符号相反的月份）全部走
    build/yoy.py 的 caliber_diff —— 那是全站唯一实现，各页各写一份正是同一条序列
    在两页被判定相反的原因。样本对齐这一步尤其不能自己重写：滚动同比比单月同比少
    12 个月历史，不取交集就会把「样本不同」读成「口径不同」。
    """
    d = YOY.caliber_diff(pd.Series(s), kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {
        'n': d['n'], 'first': d['months'][0], 'last': d['months'][-1],
        'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
        'jump_m': d['maxjump_mom'][0], 'jump_m_at': d['maxjump_mom'][2],
        'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
        'n_opp': d['opposite_n'], 'opp': opp,
    }


CALIB = caliber_stats(adv)                       # 总 ADV：全页的口径样本（流量）
CALIB_OI = caliber_stats(df['oi_total_contracts'], YOY.STOCK)   # 月末未平仓：存量对照样本
# 交易日加权 vs 日均：同一条量在两种聚合口径下的滚动同比差多少（决定「要不要乘交易日」）
DAYCOUNT_STATS = caliber_stats(df['total_vol_mn'])
_c_adv, _c_vol = roll_yoy(adv), roll_yoy(df['total_vol_mn'])
_c_both = pd.concat([_c_adv, _c_vol], axis=1, keys=['a', 'v']).dropna()
DC_MAXGAP = float((_c_both['a'] - _c_both['v']).abs().max())
DC_SAME_SIGN = bool(((_c_both['a'] * _c_both['v']) > 0).all())

# 每张改口径的图都要自己说清楚新口径与理由；完整实测放在 NOTES 里，这里给一句压缩版。
YOY_CAL = (f'<b>次轴 = 12 个月滚动合计同比</b>（最近 12 个月合计 ÷ 上一个 12 个月合计 − 1），'
           f'不是单月同比。理由是本页自己的实测：总 ADV 的单月同比在 {CALIB["n"]} 个可比月里'
           f'有 {CALIB["n_opp"]} 个月（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）'
           f'与滚动口径<b>符号相反</b>，相邻月最大跳变 {CALIB["jump_m"]:.0f}pp'
           f'（滚动口径 {CALIB["jump_r"]:.0f}pp）。折线要等 24 个月才有第一个点'
           f'（12 个月填窗 + 12 个月比较），窗口左端因此可能没有线。')

# 存量图（月末未平仓合约）的对应说明：它**不改**口径，但必须说清为什么不改，
# 否则读者会以为漏改了一张，或者把它的折线和别的图的滚动折线放在一起比。
STOCK_CAL = (f'<b>次轴 = 单月同比</b>（本月 ÷ 去年同月 − 1），与本页成交量各图的 '
             f'12 个月滚动合计同比<b>不是一个口径</b>，两者不要放在一起比高低。'
             f'这里之所以不改：未平仓合约是<b>存量</b>（月末快照），'
             f'把 12 个月末的存量加起来不是任何东西 —— 既不是「一年的量」（存量不累积），'
             f'也不是「平均水平」（没除以 12）；而且存量不吃日历效应（不像成交量要看'
             f'当月有几个交易日），单月同比在它上面本来就稳得多。'
             f'本页实测：未平仓合约的单月同比标准差 {CALIB_OI["sd_m"]:.1f}pp、'
             f'相邻月最大跳变 {CALIB_OI["jump_m"]:.0f}pp，而总 ADV 是 '
             f'{CALIB["sd_m"]:.1f}pp 与 {CALIB["jump_m"]:.0f}pp —— 差着一个量级，'
             f'所以成交量非平滑不可，存量不必。判据与实现见 <code>build/yoy.py</code>。')

RPC = rpc_quarterly([('total', 'rpc_total'), ('rates', 'rpc_interest_rates'),
                     ('equity', 'rpc_equity_indexes'), ('energy', 'rpc_energy'),
                     ('metals', 'rpc_metals')])
rpc_m = to_monthly(RPC['total'], df.index)
df['implied_txn_rev_usdmn'] = df['total_vol_mn'] * rpc_m    # 百万张 x $/张 = $mn
RPC_Q, RPC_V = RPC['total'].index[-1], float(RPC['total'].iloc[-1])

# ══════════════════ TTM 序列（量价分解与 Exhibit EX_TTMVOL 共用）══════════════════
# 均价一律用「合计 ÷ 合计」定义，绝不用「逐月 RPC 的均值」——
# 后者对每个月等权，而各月的成交量差着一倍以上；更要命的是均值之积 ≠ 积之均值，
# 拿它做分解，两块相加就对不上总增长，而图上完全看不出来。
df['ttm_vol_mn'] = YOY.ttm(df['total_vol_mn'], YOY.FLOW)           # 近 12 个月成交合约数
df['ttm_rev_usdmn'] = YOY.ttm(df['implied_txn_rev_usdmn'], YOY.FLOW)
df['ttm_rpc_usd'] = df['ttm_rev_usdmn'] / df['ttm_vol_mn']         # 近 12 个月混合 RPC

# ══════════ 费率期间披露 ══════════
# 成交量按月往前走，RPC 一个季度才更新一次 —— 所以「最新一两个月的隐含值用的是上一季
# 费率」是本页的常驻口径，不是 bug。但页面此前只说了「最新季之后沿用」，没说清本月究竟
# 挂在哪一季上，读者无从判断这个隐含收入落后多少。下面几行把期间算出来写进图注。
#
# 季度号一个都不许写死：写死的话下季度这句话就自动变成假话（本仓踩过 schw「过去 32 个
# 季度单边降」、cost「Exhibit 4 画了红线」两次同类坑）。全部由 df.index 与
# fee_rates.csv 现算，随数据自动滚动。
CUR_Q = LATEST.asfreq('Q')            # 本页最新数据月所在的季度
RPC_LAG = (CUR_Q - RPC_Q).n           # 费率比数据月落后几个季度；正常节奏 = 1
# 落在最新可得费率季度之后的月份 —— 这些月的隐含值是拿上一季费率外推出来的
CARRY = [p for p in df.index if p.asfreq('Q') > RPC_Q]
# 统一收尾在中文字上（「…这 N 个月」），后面无论接「尚无」还是「的隐含值」都不留半角缝
_CARRY_TXT = ('' if not CARRY else
              f'{mlab(CARRY[0])} 这 1 个月' if len(CARRY) == 1 else
              f'{mlab(CARRY[0])}–{mlab(CARRY[-1])} 这 {len(CARRY)} 个月')

# 正常节奏（RPC_LAG == 1，本季用上一季费率）只陈述期间；落后两季及以上要显式示警。
RATE_PERIOD = (
    f'<b>费率期间</b>：本页数据截至 {mlab(LATEST)}（{qlab(CUR_Q)}），费率取 CME 季报披露的 '
    f'{qlab(RPC_Q)} 值（总 RPC ${RPC_V:.3f}），这是目前可得的最新一季。'
    + (f'{qlab(RPC_Q)} 及以前各月用其所属季度的实际披露费率；{_CARRY_TXT}尚无对应季度费率，'
       f'沿用 {qlab(RPC_Q)} 的 ${RPC_V:.3f} 推算。' if CARRY else
       f'本页每个月都落在已披露费率的季度内，没有任何一个月是沿用上一季费率。'))

RATE_STALE = ('' if RPC_LAG < 2 else
              f'<b>⚠ 费率已过期</b>：按正常节奏，{qlab(CUR_Q)} 的月份至少应当能用上 '
              f'{qlab(CUR_Q - 1)} 的费率，但 fee_rates.csv 里最新只到 {qlab(RPC_Q)}，'
              f'比正常节奏又老了 {RPC_LAG - 1} 个季度（多半是官方季报延迟）。'
              f'{_CARRY_TXT}的隐含值因此建立在 {RPC_LAG} 个季度以前的费率上；'
              f'期间若发生品种结构位移或定价调整，本图会系统性偏离，'
              f'费率补齐后这些月份的数值会被改写。')

BR_NOTE = ('Assumption: monthly transaction revenue = contracts traded x average rate per contract '
           f'({qlab(RPC_Q)} = ${RPC_V:.3f}, held flat after). CME derives RPC from reported revenue, so '
           'closed quarters reconstruct a known total — the value is the current quarter. '
           '费率是季度值，当季各月共用该季 RPC，最新季之后沿用；品种结构变化会让混合 RPC 偏离，'
           f'见 Exhibit {EX_RPC}。'
           + RATE_PERIOD + RATE_STALE)

W13 = df.index[-WIN_BAR:]
W25 = df.index[-WIN_LINE:]
XL13 = [mlab(p) for p in W13]
XL25 = [mlab(p) for p in W25]
XL_LONG = [mlab(p) for p in df.index]


def win(col, n):
    return df[col].iloc[-n:].values


# ══════════════════════════ 3. Exhibit 1：汇总表 ══════════════════════════
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12

# 第 5 个字段 cal=True → 纯日历行：m/m 与 y/y 不着色、分位整格留空。
# 交易日数是月历的产物（22 天 vs 21 天纯粹因为 7 月比 6 月多一个工作日），不是经营结果：
# 「+4.8% 涂绿、分位 69 涂绿」等于说多一个交易日是好消息，与本表注
# 「ADV is already day-count neutral」的立场自相矛盾。数值仍然要给 —— 读者要拿它复核
# Exhibit 3 的 day-count 口径差 —— 只是不做好坏判断。
SUM_ROWS = [
    ('group', 'Average daily volume (k contracts)', None, None, False),
    ('row', 'Total ADV', 'adv_total_kcontracts', 0, False),
    ('row', 'Interest rates', 'adv_rates_kcontracts', 0, False),
    ('row', 'Equity index', 'adv_equity_kcontracts', 0, False),
    ('row', 'Energy', 'adv_energy_kcontracts', 0, False),
    ('row', 'Agricultural', 'adv_ag_kcontracts', 0, False),
    ('row', 'FX', 'adv_fx_kcontracts', 0, False),
    ('row', 'Metals', 'adv_metals_kcontracts', 0, False),
    ('group', 'Volume and open interest', None, None, False),
    ('row', 'Total contracts traded (mn)', 'total_vol_mn', 1, False),
    ('row', 'Month-end open interest (mn)', 'oi_total_mn', 1, False),
    ('row', 'Trading days', 'trading_days', 0, True),
]

BLANK_PCTILE = []      # summary() 里逐行记下留空原因，供表注引用


def summary():
    """3Y %ile 一律走 build/pctile.py（全站唯一实现）。

    本文件原先自带一份 `pctile36()`，判据是「逐月不降的月份占比 ≥ 90% 就留空」。
    那个代理量测的是序列形状，不是分位列本身有没有区分度，所以既拦不住「上下波动但
    分位常年钉 100」的行，各页各写一份还会让同一条序列在两页判定相反。分位是口径，
    口径只能有一处定义 —— 这里只负责「本页自己的口径原因」（交易日数是日历产物）。
    """
    rows = []
    for kind, label, col, dec, cal in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        s = df[col]
        c, p1, p12 = float(s[CUR]), float(s[PRV]), float(s[YAG])
        mm = (c / p1 - 1) * 100 if p1 else np.nan
        yy = (c / p12 - 1) * 100 if p12 else np.nan

        def sign(v):
            if cal:                       # 日历行不做好坏判断
                return ''
            return 'pos' if v > 0 else ('neg' if v < 0 else '')

        cells = [{'v': num(c, dec)}, {'v': num(p1, dec)}, {'v': num(p12, dec)},
                 {'v': pct(mm), 'cls': sign(mm)}, {'v': pct(yy), 'cls': sign(yy)}]
        if cal:
            cells.append({'v': ''})
            BLANK_PCTILE.append((label, '交易日数由月历决定，与 CME 的经营无关，'
                                        '其分位只是在 0 与 91 之间随月长震荡'))
        else:
            q, cls = pctile.cell(L(s.values), -1)
            cells.append({'v': q, 'cls': cls})
            if not q:
                BLANK_PCTILE.append((label, pctile.why_blank(L(s.values)) or '样本不足'))
        rows.append({'label': label, 'cells': cells})

    blank = '；'.join(f'{lab} —— {why}' for lab, why in BLANK_PCTILE)
    return {
        'title': f'CME Group monthly volume summary — {mlab(CUR)}',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': (
                 # 表的三列就是三个具体月份（本月 / 上月 / 去年同月），y/y 只能是这两个
                 # 具名月份之比 —— 换成 12 个月滚动值，列头写的月份与格里的数就对不上了。
                 # 所以这一列保留单月口径，但必须点名，否则读者会拿它和各图次轴的滚动同比
                 # 直接对照，那是两个不同的量。
                 '<b>本表的 y/y 是单月同比</b>（本月 ÷ 去年同月 − 1），'
                 f'与各图次轴的 12 个月滚动合计同比不是一个口径：本表三列写死的就是'
                 f'「本月 / 上月 / 去年同月」这三个具名月份，滚动值放进来与列头自相矛盾。'
                 f'单月同比有多毛：本页总 ADV 的实测是 {CALIB["n"]} 个可比月里 '
                 f'{CALIB["n_opp"]} 个月与滚动口径符号相反。要判趋势请看各图的次轴金色折线'
                 f'与 Exhibit {EX_TTMVOL}，本表回答的是「本月相对上月与去年同月的水平」。'
                 'ADV is already day-count neutral; total contracts traded is not. '
                 f'Exhibit {EX_DAYCOUNT} isolates the difference.（原 PDF 此处误写作 '
                 f'Exhibit 4 —— 汇总表本身占 Exhibit 1，day-count 图是 Exhibit '
                 f'{EX_DAYCOUNT}。）'
                 '3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，判据见'
                 '「口径与方法说明」第 7 条。'
                 + (f'本表留空的行：{blank}。' if blank else '本表没有留空的分位。')
                 + '「Trading days」行的 m/m 与 y/y 只给数字、不着色，理由同上。'
                 '全部为 CME 官方披露值，无推导。'),
    }


# ══════════════════════════ 4. Exhibit 2..19 ══════════════════════════
def yoy_line(col, win_n=WIN_BAR, kind=YOY.FLOW):
    """次轴折线的数值。流量走 12 个月滚动合计同比，存量走点对点同比（见 ROLL 那一段）。

    引擎不替我们算同比 ——「这一点的同比有没有意义」是口径判断，只能在 Python 侧做。
    """
    s = YOY.ttm_yoy(df[col], kind) if kind == YOY.FLOW else YOY.mom_yoy(df[col], kind)
    return L(s.values[-win_n:])


def gs_bar(n, col, title, ylab, fmt, legend, note=None, src_extra=None, kind=YOY.FLOW):
    """← gsx.lvl_bar：浅蓝柱 + **次轴金色 y/y 折线**。窗口 13 个月（契约 §5.4）。

    次轴画的是同比而不是 12 个月滚动均线 —— gsx.lvl_bar 的 docstring 写死了这条理由：
    「均线只是把柱子再平滑一遍、不带新信息，同比才回答『相对去年这个月是好是坏』」。
    本页九张 gs_bar 全部由 build_cme.py 的 gsx.lvl_bar 移植而来，所以与 deck 对齐：
    给 yoy 就不画均线（引擎侧自动），同时不再需要左上角那个 y/y 气泡。

    2026-08 改口径：**流量**序列那条折线由单月同比改为 12 个月滚动合计同比。轴标题与
    图例名一并改掉 —— 只改数不改名，读者会拿一条已经被平滑过的线当单月同比读，
    那比不改更糟。每张图的 note 都追加对应的压缩版口径说明（带本页实测数字）。

    kind=STOCK 的图（月末未平仓合约）**不改**：存量不可加总，且它本来就不吃日历效应，
    单月同比在它上面已经足够稳（判据与实现见 build/yoy.py）。这类图的轴名写「单月」，
    与滚动口径的图区分开。
    """
    roll = (kind == YOY.FLOW)
    ex = {'n': n, 'kind': 'gs_bar', 'title': title, 'fmt': fmt, 'ylab': ylab,
          'ylab2': '% y/y, 12M roll.' if roll else '% y/y, single month',
          'legend': legend, 'values': L(win(col, WIN_BAR)),
          'yoy': {'name': '12M rolling y/y (RHS)' if roll else 'y/y, single month (RHS)',
                  'color': 'GOLD', 'yfmt': 'pct0',
                  'values': yoy_line(col, kind=kind)}}
    cal = YOY_CAL if roll else STOCK_CAL
    ex['note'] = (note + ' ' + cal) if note else cal
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


ex = []

ex.append(gs_bar(EX_ADV, 'adv_mn', 'Total average daily volume', 'mn contracts / day', 'f1',
                 'Total ADV'))

ex.append({
    'n': EX_DAYCOUNT, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL25,
    'title': 'Total volume vs. ADV growth: the day-count gap',
    'ylab': '% y/y', 'zero_line': True,
    'series': [
        {'name': 'Total contracts y/y', 'color': 'GRAY', 'values': L(win('vol_yoy', WIN_LINE))},
        {'name': 'ADV y/y (day-count neutral)', 'color': 'NAVY',
         'values': L(win('adv_yoy', WIN_LINE))},
    ],
    'src_extra': ('Gap between the two lines is purely the change in trading days — '
                  'the Barclays adjustment'),
    'note': (f'{mlab(CUR)}：总成交 {pct(df["vol_yoy"][CUR])} y/y，按日 {pct(df["adv_yoy"][CUR])} y/y，'
             f'交易日数贡献 {pp(float(df["daycount_effect"][CUR]))}'
             f'（{days[CUR]:.0f} 天 vs 去年同月 {days[YAG]:.0f} 天）。'
             # 全页只有这一张（外加热力矩阵 EX_HEAT_YOY）保留单月同比。理由不是习惯，
             # 是这张图的命题本身：day-count 效应是**单月现象**，平滑掉它这张图就空了。
             f'<b>本图是全页唯一保留单月同比的折线图</b>（其余图的次轴已改 12 个月滚动合计同比）：'
             f'这张图的全部命题就是「交易日数差异能在<b>一个月</b>之内把成交量的方向读反」'
             f'（Barclays 调整）。改成滚动口径这张图会自己消失 —— 实测：滚动口径下'
             f'两条线的逐月标准差是 {CALIB["sd_r"]:.1f}pp（按日）vs {DAYCOUNT_STATS["sd_r"]:.1f}pp'
             f'（总量），最大差 {DC_MAXGAP:.1f}pp，'
             + ('且逐月符号完全一致' if DC_SAME_SIGN else '仍有符号不一致的月份')
             + f'，12 个月窗口里交易日效应基本自抵。单月口径下同一对序列的标准差是 '
             f'{CALIB["sd_m"]:.1f}pp vs {DAYCOUNT_STATS["sd_m"]:.1f}pp。'
             f'读这两条线时请记住它们与其余各图的次轴<b>口径不同</b>，不要跨图比高低。'),
})

_stack13 = {c: win(c, WIN_BAR) for c, _, _ in CLS}
_share13 = (win('adv_rates_kcontracts', WIN_BAR) + win('adv_equity_kcontracts', WIN_BAR)) \
    / win('adv_total_kcontracts', WIN_BAR) * 100
# 右轴上界取 10 的整数倍：占比线要压在堆叠柱之上，太高会掉进柱子里
_ymax = float(np.ceil(np.nanmax(_share13) / 10.0) * 10)
if np.nanmax(_share13) / _ymax > 0.995:
    _ymax += 10
ex.append({
    'n': EX_MIX, 'kind': 'stacked_dual', 'fmt': 'f0c', 'xlabels': XL13,
    'title': 'ADV mix by asset class',
    'ylab': 'k contracts / day', 'ylab2': '% rates + equity',
    'stacks': [{'name': nm, 'color': cl, 'values': L(_stack13[c])} for c, nm, cl in CLS],
    'line': {'name': '% rates + equity (RHS)', 'color': 'GREEN',
             'values': L(_share13), 'ymax': _ymax, 'yfmt': 'pct0'},
    'note': ('六个品种加总即披露的 Total ADV（CME 的品种划分是穷尽且互斥的）。'
             '右轴是利率 + 股指两大品种占总 ADV 的比重 —— 体量与结构同框，'
             f'总量持平但结构位移一样会改变混合费率（见 Exhibit {EX_RPC}）。'),
})

_SPLIT_NOTE = (f'原 PDF 把六个品种画在同一根轴上，利率品种的峰值 '
               f'{df["adv_rates_kcontracts"].iloc[-WIN_LINE:].max():,.0f} 独自定死了量程，'
               f'能源 / 农产品 / 外汇 / 金属四条线被压成底部一条带、彼此分不开。'
               f'这里按量级拆成 Exhibit {EX_MAJORS}（两大品种）与 Exhibit {EX_MINORS}'
               f'（四个小品种）两张，窗口、口径、配色一律不变，一个点也没有删；'
               f'两张图的纵轴刻度不同，跨图比高度是没有意义的，要比绝对量请回 '
               f'Exhibit {EX_MIX} 的堆叠柱或末尾核对表。')

ex.append({
    'n': EX_MAJORS, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV by asset class: rates and equity index',
    'ylab': 'k contracts / day',
    'series': [{'name': nm, 'color': cl, 'values': L(win(c, WIN_LINE))}
               for c, nm, cl in CLS_MAJOR],
    'note': _SPLIT_NOTE,
})

ex.append({
    'n': EX_MINORS, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV by asset class: energy, ag, FX and metals',
    'ylab': 'k contracts / day',
    'series': [{'name': nm, 'color': cl, 'values': L(win(c, WIN_LINE))}
               for c, nm, cl in CLS_MINOR],
    'note': (f'与 Exhibit {EX_MAJORS} 同一份数据、同一个 {WIN_LINE} 个月窗口，'
             f'只是把量级差一个数量级的四个小品种单独放到自己的轴上。'
             f'注意纵轴上界只有 Exhibit {EX_MAJORS} 的约五分之一。'),
})

ex.append({
    'n': EX_HIST, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'zero_line': True,
    'title': 'Full ADV history since 2008', 'ylab': 'mn contracts / day',
    'series': [{'name': 'Total ADV', 'color': 'NAVY', 'values': L(df['adv_mn'].values)}],
    'src_extra': f'Full disclosed history: {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）',
    'note': ('原 PDF 在末端画了一个红色虚线椭圆圈出最近 3 个月，网页引擎没有对应的注解图元，'
             f'故未移植；最近 {WIN_BAR} 个月的读数见 Exhibit {EX_ADV} 与末尾核对表。'),
})

_qs = df['total_vol_mn'].groupby(df.index.asfreq('Q')).agg(['sum', 'count'])
_qv = _qs['sum'].values
_qyoy = np.array([(_qv[i] / _qv[i - 4] - 1) * 100 if i >= 4 and _qv[i - 4] else np.nan
                  for i in range(len(_qv))])
_npart = int(_qs['count'].iloc[-1])
ex.append({
    'n': EX_QTR, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c',
    'xlabels': [str(p) for p in _qs.index[-WIN_QTR:]],
    'title': 'Contracts traded aggregated to quarters', 'ylab': 'mn contracts',
    'ylab2': '% y/y',
    'values': L(_qv[-WIN_QTR:]),
    'partial_months': _npart, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(_qyoy[-WIN_QTR:]),
             'yfmt': 'pct0'},
    'src_extra': 'Latest bar is quarter-to-date and not comparable to full quarters',
    'note': (f'季度合计 = 该季各月「ADV x 当月交易日」之和，在 Python 侧算好。'
             f'末柱 {_qs.index[-1]} 只含 {_npart} 个月（浅蓝），其右轴 y/y 已被作废 —— '
             '拿未满季去比上年完整季必然砸出一个假坑。'
             # 绿线末端那个读数的标签由引擎固定右移 5px，窄屏下会飘到 QTD 柱上方，
             # 容易被读成 QTD 那一期的同比。把它归属的季度写死在图注里，读者不必靠像素判断。
             f'因此绿线的最后一个读数 {pct(_qyoy[-2], 0)} 属于 {_qs.index[-2]}'
             f'（最后一个完整季），不是 {_qs.index[-1]}。'
             # 季度柱的右轴是**第三种**同比口径（3 个月合计 vs 上年同季）。柱是季度的，
             # 线就必须与柱同期，改成 12 个月滚动会让线与柱指的不是同一段时间。
             f'<b>右轴的同比口径与其余各图不同</b>：这里是「本季 3 个月合计 vs 上年同季 3 个月合计」，'
             f'既不是单月同比、也不是各 gs_bar 次轴的 12 个月滚动合计同比。柱是季度口径，'
             f'线只能与柱同期，否则线讲的是另一段时间。三个月的合计已经把单月毛刺压掉一部分，'
             f'但仍比 12 个月滚动口径敏感得多，跨图比高低没有意义。'),
})

ex.append(gs_bar(EX_OI, 'oi_total_mn', 'Month-end total open interest', 'mn contracts', 'f1',
                 'Month-end OI', kind=YOY.STOCK,
                 note='月末未平仓合约是存量口径（期末快照），与 ADV 这类流量口径不可直接相加。'))
ex.append(gs_bar(EX_RATES, 'adv_rates_kcontracts', 'Interest-rate complex ADV',
                 'k contracts / day', 'f0c', 'Interest rates ADV'))
ex.append(gs_bar(EX_EQUITY, 'adv_equity_kcontracts', 'Equity-index complex ADV',
                 'k contracts / day', 'f0c', 'Equity index ADV'))
ex.append(gs_bar(EX_ENERGY, 'adv_energy_kcontracts', 'Energy complex ADV',
                 'k contracts / day', 'f0c', 'Energy ADV'))
ex.append(gs_bar(EX_REV, 'implied_txn_rev_usdmn', 'Implied transaction revenue', '$mn / month',
                 'usd0', 'Implied transaction revenue', note=BR_NOTE))

_rq = RPC['total'].index[-WIN_QTR:]
# 四条品种曲线各自的最新可得季度未必与总 RPC 同步（某一季只补了一部分品种时会脱节），
# 脱节的那条曲线在末端会断开。差异现算，不写死品种名与季度号。
_RPC_ZH = {'total': '总 RPC', 'rates': '利率', 'equity': '股指', 'energy': '能源',
           'metals': '金属'}
_rpc_behind = [(k, RPC[k].index[-1]) for k in ('rates', 'equity', 'energy', 'metals')
               if RPC[k].index[-1] != RPC_Q]
_RPC_SYNC = ('' if not _rpc_behind else
             '注意四条曲线并未同步：'
             + '、'.join(f'{_RPC_ZH[k]}最新只到 {qlab(q)}' for k, q in _rpc_behind)
             + f'（其余为 {qlab(RPC_Q)}），末端断开处即缺该季披露。')
ex.append({
    'n': EX_RPC, 'kind': 'lines_endlabels', 'fmt': 'usd2',
    'xlabels': [mlab(q.asfreq('M', 'end')) for q in _rq],
    'title': 'Rate per contract by asset class', 'ylab': '$ per contract',
    'series': [
        {'name': 'Interest rates', 'color': 'NAVY', 'values': L(RPC['rates'].reindex(_rq).values)},
        {'name': 'Equity index', 'color': 'MBLUE', 'values': L(RPC['equity'].reindex(_rq).values)},
        {'name': 'Energy', 'color': 'BLUE', 'values': L(RPC['energy'].reindex(_rq).values)},
        {'name': 'Metals', 'color': 'GOLD', 'values': L(RPC['metals'].reindex(_rq).values)},
    ],
    'src_extra': ('RPC differs several-fold across complexes, so a volume mix shift moves blended '
                  'revenue even when total ADV is flat. This is the main uncertainty in the bridge '
                  'above.'),
    'note': (f'季度值，x 轴标的是各季末月（{mlab(_rq[0].asfreq("M", "end"))} = 1Q{_rq[0].year % 100:02d}，'
             f'最新为 {qlab(RPC_Q)}）。'
             f'{mlab(_rq[-1].asfreq("M", "end"))}：利率 ${RPC["rates"].iloc[-1]:.3f}、'
             f'股指 ${RPC["equity"].iloc[-1]:.3f}、能源 ${RPC["energy"].iloc[-1]:.3f}、'
             f'金属 ${RPC["metals"].iloc[-1]:.3f} —— 图上按 $0.01 显示（原 PDF 为 $0.001），'
             '第三位小数以此注为准。' + _RPC_SYNC
             # 本图本身只画季度费率、不跨月外推，但它是 EX_REV 那张隐含收入桥的费率来源，
             # 所以同一句期间披露在这里也要出现：读者看到曲线停在哪一季，就知道隐含收入
             # 那张图的最新一两个月是拿哪一季的费率算的。
             + f'本图曲线止于 {qlab(RPC_Q)}，Exhibit {EX_REV} 的隐含收入即以此季费率为准。'
             + RATE_PERIOD + RATE_STALE),
})

ex.append(gs_bar(EX_FX, 'adv_fx_kcontracts', 'FX complex ADV', 'k contracts / day', 'f0c', 'FX ADV'))
ex.append(gs_bar(EX_METALS, 'adv_metals_kcontracts', 'Metals complex ADV', 'k contracts / day', 'f0c',
                 'Metals ADV'))
ex.append(gs_bar(EX_AG, 'adv_ag_kcontracts', 'Agricultural complex ADV', 'k contracts / day', 'f0c',
                 'Agricultural ADV'))


def heat(n, col, title, src_extra, fmt='pct0', legend=None, note=None):
    s = df[col].dropna()
    yrs = sorted({p.year for p in s.index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    d = {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title, 'fmt': fmt,
         'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': M,
         'legend': legend or title, 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
         'src_extra': src_extra}
    if note:
        d['note'] = note
    return d


# fmt 用 pct0z 而不是 pct0：pct0 会把 −0.4% 印成「-0%」（一个不存在的数）。
# 当前 10 年窗口里恰好没有落在 ±0.5% 内的月份，但 y/y 序列每月都在动，这是迟早会命中的
# 格式坑，先按 pct0z 钉住（|v| < 0.5 → 0）。
#
# 这张矩阵**保留单月同比**，且标题里把「single-month」写进去。热力矩阵的用途就是逐格
# 看单月的季节性与异常月，把它换成 12 个月滚动值等于把相邻 12 格填成同一个数 —— 矩阵
# 会退化成一片同色，一格都读不出来。代价是本页出现第二种同比口径，所以标题、图例与图注
# 三处都显式点明，不靠读者自己猜。
ex.append(heat(EX_HEAT_YOY, 'adv_yoy', 'Total ADV y/y growth, single month (%)',
               'Green = faster y/y growth, red = slower. Single-month y/y — the only '
               'exhibit besides Exhibit 3 that is not on the 12-month rolling basis',
               fmt='pct0z', legend='Total ADV y/y (single month)',
               note=f'<b>本图的每一格是单月同比</b>（该月 ÷ 去年同月 − 1），'
                    f'与各 gs_bar 次轴的 12 个月滚动合计同比<b>不是一个口径</b>，'
                    f'两者不要放在一起读。这里之所以不平滑：热力矩阵的用途就是逐格看'
                    f'单月的季节性与异常月，换成滚动值会让相邻 12 格几乎填成同一个数、'
                    f'整张表退化成一片同色。代价是单月同比本身很毛：本页实测 '
                    f'{CALIB["n"]} 个可比月里有 {CALIB["n_opp"]} 个月与滚动口径符号相反'
                    f'（相邻月最大跳变 {CALIB["jump_m"]:.0f}pp，出现在 '
                    f'{mlab(CALIB["jump_m_at"])}）—— 所以这张表读的是「哪几个月不寻常」，'
                    f'不是「趋势往哪走」；趋势请看 Exhibit {EX_ADV} 的次轴与 Exhibit {EX_TTMVOL}。'))
ex.append(heat(EX_HEAT_SHARE, 'rates_share', 'Interest-rate share of total ADV (%)',
               'Rates is the largest and most rate-cycle-sensitive complex',
               legend='Rates share of ADV'))


# ══════════ Exhibit EX_DECOMP：收入增长的量／费率分解（**不是成交额的量价分解**）══════════
# 恒等式：收入 ≡ 成交合约数 × 每张平均费率。CME 不披露成交**金额**（期货的名义本金要靠
# 合约乘数逐品种推，本仓 series/contract_specs.csv 只覆盖一部分品种），所以「成交额 =
# 成交量 × 均价」那种分解在这一页做不到，做出来也是拿口径不全的名义本金去凑分母。
# 能做的是**收入**的量价分解：张数是量、RPC 是价。两者性质不同，标题和图注都必须写死这一点。
#
# 四条口径纪律：
# （1）均价一律用「合计 ÷ 合计」（TTM 收入 ÷ TTM 张数），不是「逐月 RPC 的均值」。
#      后者对每个月等权，而各月成交量差着一倍以上；更要命的是均值之积 ≠ 积之均值，
#      拿它做分解，两块相加就对不上总增长，而图上完全看不出来。
# （2）端点用 TTM12（截至该月的 12 个月合计）对比 12 个月前的 TTM12，不做点对点 ——
#      与本页所有次轴同比同口径，分解出来的两块才能和 Exhibit EX_ADV 那条金色线对上。
# （3）**用对数分解画图**。算术分解要选一个「交叉项归谁」的约定：量按旧价算、价按新量算，
#      交叉项就整个压进价那一段，于是价那一段既不是价、也不是交叉项，而是两者的和。
#      量与价方向相反、几乎对冲的年份，交叉项能大到净增长的数倍，那时算术堆叠柱画出来
#      是错的（全仓实测：交叉项占净增长中位 10.5%、最大 362.8%）。对数分解
#      ln(R1/R0) = ln(Q1/Q0) + ln(P1/P0) 天然可加、对称、无需选约定，所以图上用它。
#      算术分解仍然照算，两者的最大差写进图注。
# （4）单位是**对数点**（100 × ln），不是百分点。之所以不把对数贡献按总增长等比缩放回
#      百分点：那要除以 ln(R1/R0)，而净增长接近零的月份这个分母也接近零，同一个病
#      又回来了。小幅变化时对数点与百分点近似相等，大幅时不等，图注里给出该月的算术 %。
_dv = df[['ttm_vol_mn', 'ttm_rev_usdmn', 'ttm_rpc_usd']].dropna()
_q1, _q0 = _dv['ttm_vol_mn'], _dv['ttm_vol_mn'].shift(ROLL)
_p1, _p0 = _dv['ttm_rpc_usd'], _dv['ttm_rpc_usd'].shift(ROLL)
_r1, _r0 = _dv['ttm_rev_usdmn'], _dv['ttm_rev_usdmn'].shift(ROLL)

_dec = pd.concat({
    'tot': np.log(_r1 / _r0) * 100,              # 对数总增长（log points）
    'vol': np.log(_q1 / _q0) * 100,              # 量的对数贡献
    'rate': np.log(_p1 / _p0) * 100,             # 费率的对数贡献
    'arith_tot': (_r1 / _r0 - 1) * 100,          # 算术总增长（%），只进图注与对照
    'arith_vol': (_q1 / _q0 - 1) * 100,          # 算术：量按旧费率计价
    'arith_rate': (_p1 / _p0 - 1) * (_q1 / _q0) * 100,   # 算术：费率按新张数计量（含交叉项）
}, axis=1).dropna()

# 硬护栏：分解是恒等式，不是近似。对不上就说明上面某个 shift / 口径写错了，必须停在这里 ——
# 一张「两块加起来不等于总数」的分解图，读者是看不出来的。两种分解各查各的。
for _tag, _a, _b, _t in (('对数', 'vol', 'rate', 'tot'),
                         ('算术', 'arith_vol', 'arith_rate', 'arith_tot')):
    _resid = float((_dec[_a] + _dec[_b] - _dec[_t]).abs().max())
    if not np.isfinite(_resid) or _resid > 1e-9:
        raise SystemExit(f'Exhibit {EX_DECOMP} {_tag}分解不闭合：'
                         f'max|量+价−总| = {_resid:.3e}（上限 1e-9）')

# 两种分解的差距，以及「算术分解里交叉项占净增长多大」—— 后者正是不用算术分解的理由，
# 数字要现算，不能照抄别的页的实测值。
_log_gap = float((_dec['vol'] - _dec['arith_vol']).abs().max())
_log_gap_at = (_dec['vol'] - _dec['arith_vol']).abs().idxmax()
_cross = (_dec['arith_rate'] - (_p1 / _p0 - 1) * 100).reindex(_dec.index)   # 交叉项本身
_cross_sh = (_cross / _dec['arith_tot']).abs().replace([np.inf, -np.inf], np.nan).dropna() * 100
_CROSS_MED, _CROSS_MAX = float(_cross_sh.median()), float(_cross_sh.max())

_DW = _dec.index[-WIN_BAR:]
_dw = _dec.loc[_DW]
_lastq, _lastr = float(_dw['vol'].iloc[-1]), float(_dw['rate'].iloc[-1])
ex.append({
    'n': EX_DECOMP, 'kind': 'bridge_bar', 'fmt': 'f1', 'xlabels': [mlab(p) for p in _DW],
    'xrot': 0,
    'title': 'Implied revenue growth split: contracts vs. rate per contract '
             '(a revenue split, NOT a turnover split)',
    'ylab': 'log points of TTM revenue growth',
    'stacks': [
        {'name': 'Contracts traded', 'color': 'NAVY', 'values': L(_dw['vol'].values)},
        {'name': 'Rate per contract (RPC)', 'color': 'GOLD', 'values': L(_dw['rate'].values)},
    ],
    'net': {'name': 'TTM implied revenue growth', 'values': L(_dw['tot'].values)},
    'net_color': 'INK',
    'src_extra': 'Identity: revenue = contracts x rate per contract. This decomposes REVENUE, '
                 'not notional turnover — CME does not publish traded notional value',
    'note': (f'<b>这是收入的量价分解，不是成交额的量价分解。</b>恒等式是「隐含交易收入 = '
             f'成交合约数 × 每张平均费率(RPC)」；CME 不披露成交<b>金额</b>，所以'
             f'「成交额 = 成交量 × 均价」那种分解在本页<b>不具备数据条件</b>，本图也没有假装做到。'
             f'两者不可混为一谈，也不要和别的页上真正的量价分解并读：这里的「价」是 CME 向客户'
             f'收的<b>每张费率</b>，不是标的资产的成交价格。'
             f' <b>口径</b>：端点用 TTM12（截至该月的 12 个月合计）对比 12 个月前的 TTM12，'
             f'与本页各图次轴同比一致，不做点对点。'
             f' <b>用对数分解</b>：ln(收入比) = ln(张数比) + ln(费率比)，天然可加、对称，'
             f'不必选「交叉项归谁」。算术分解必须选一个约定，交叉项会整段压进费率那一块 —— '
             f'本页实测交叉项占净增长中位 {_CROSS_MED:.1f}%、最大 {_CROSS_MAX:.0f}%，'
             f'量与费率方向对冲的年份那一段画出来就是错的。'
             f'两种分解的「量」这一块最大相差 {_log_gap:.1f}（出现在 {mlab(_log_gap_at)}）。'
             f' <b>单位是对数点</b>（100 × ln），不是百分点：小幅变化时两者近似相等，大幅时不等。'
             f'{mlab(_DW[-1])}：张数 {_lastq:+.1f}、费率 {_lastr:+.1f}，'
             f'合计 {float(_dw["tot"].iloc[-1]):+.1f} 对数点，'
             f'对应算术总增长 {pct(float(_dw["arith_tot"].iloc[-1]))}。'
             f' <b>费率段读的是三重内容</b>：RPC 由 CME 从已披露收入倒算，所以它同时吸收了'
             f'品种结构位移（各品种 RPC 差数倍，见 Exhibit {EX_RPC}）、定价调整与折扣计划，'
             f'不是一个纯粹的「价」。' + RATE_PERIOD + RATE_STALE),
})

# ══════════ Exhibit EX_TTMVOL：量本身（TTM 水平值 + 同源增速曲线）══════════
# 为什么不是「月度 ADV + 滚动同比」——那张图就是 Exhibit EX_ADV，再画一遍是把同一份数据
# 在同一页上画两次。这里画的是分解图里那个「量」自己的水平值：近 12 个月成交合约数合计。
# 好处是柱与次轴的金色线**同源**：线上任一点的增速，就是柱子相对 12 根柱之前的涨幅，
# 读者不需要在两张图之间换算口径。
_tv = df['ttm_vol_mn'].dropna()
_tw = _tv.index[-WIN_BAR:]
_ttm_yoy = roll_yoy(df['total_vol_mn'])       # ≡ TTM 合计的同比（滚动均值同比与合计同比逐点相等）
ex.append({
    'n': EX_TTMVOL, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in _tw],
    'title': 'Contracts traded, trailing 12 months',
    'ylab': 'mn contracts, TTM', 'ylab2': '% y/y, 12M roll.',
    'legend': 'Trailing 12-month contracts',
    'values': L(_tv.loc[_tw].values),
    'yoy': {'name': '12M rolling y/y (RHS)', 'color': 'GOLD', 'yfmt': 'pct0',
            'values': L(_ttm_yoy.reindex(_tw).values)},
    'src_extra': 'The volume leg of Exhibit ' + str(EX_DECOMP) + ', shown as a level',
    'note': (f'柱 = 截至该月的近 12 个月成交合约数<b>合计</b>（= Σ「ADV × 当月交易日数」，'
             f'与汇总表「Total contracts traded」同一口径，只是累加 12 个月）；'
             f'金色线 = 该合计相对上一个 12 个月合计的同比，柱与线<b>同源</b> —— '
             f'线上任一点的读数就是这根柱相对 12 根柱之前的涨幅。'
             f'与 Exhibit {EX_ADV} 的区别：那张画的是月度 ADV（千张/日）的水平值，'
             f'本图画的是分解图 Exhibit {EX_DECOMP} 里「量」那一块自己的水平线。'
             f'{mlab(_tw[-1])} 为 {float(_tv.loc[_tw[-1]]):,.0f}mn 张，'
             f'{pct(float(_ttm_yoy.get(_tw[-1], np.nan)))} y/y。'
             f'单月成交量的毛刺在这条 TTM 曲线上看不到，这正是它的用处：'
             f'本页单月同比的相邻月最大跳变是 {CALIB["jump_m"]:.0f}pp，'
             f'TTM 口径只有 {CALIB["jump_r"]:.0f}pp。'),
})

# ══════════════════════════ 5. Exhibit 20：核对表（官方原始单位）══════════════════════════
TBL_COLS = [('Total ADV (k)', 'adv', 'adv_total_kcontracts', 3),
            ('Rates (k)', 'rates', 'adv_rates_kcontracts', 3),
            ('Equity (k)', 'eq', 'adv_equity_kcontracts', 3),
            ('Energy (k)', 'en', 'adv_energy_kcontracts', 3),
            ('Ag (k)', 'ag', 'adv_ag_kcontracts', 3),
            ('FX (k)', 'fx', 'adv_fx_kcontracts', 3),
            ('Metals (k)', 'me', 'adv_metals_kcontracts', 3),
            ('Open interest (contracts)', 'oi', 'oi_total_contracts', 0),
            ('Trading days', 'days', 'trading_days', 0)]
table = {
    'n': EX_TABLE, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
    'cols': [[h, k] for h, k, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(df[c][p]), d) for _, k, c, d in TBL_COLS})
             for p in W13],
}

# ══════════════════════════ 6. 口径与方法说明 ══════════════════════════
NOTES = [
    f'<b>数据源与节奏。</b>CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），'
    f'次月第 1-2 个工作日发布。本页覆盖 {mlab(df.index[0])} – {mlab(LATEST)} 共 {len(df)} 个连续月，'
    f'无缺月；ADV、未平仓合约、交易日数三项均为公司直接披露，未经加工。',

    '<b>版式出处。</b>Goldman Sachs「IBKR Monthly」的成对图法（水平柱 + 次轴 y/y 折线）'
    '与其 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法；day-count 那张图取自 Barclays'
    '「IBKR July Monthly Metrics」。',

    # ── 同比口径：本页最容易被读反的一条，放在前面 ──
    f'<b>同比一律用 12 个月滚动合计，不是单月同比。</b>单月同比把「去年那<b>一个</b>月碰巧是'
    f'什么样」整个塞进分母，去年同月若是异常低点，今年一个平淡的月份也能印出三位数增速。'
    f'后果不是噪声大一点，而是<b>方向会反</b>。本页总 ADV 的实测（{CALIB["first"]} – '
    f'{CALIB["last"]}，{CALIB["n"]} 个两种口径都有值的月份）：'
    f'单月同比逐月标准差 <b>{CALIB["sd_m"]:.1f}pp</b>、相邻月最大跳变 '
    f'<b>{CALIB["jump_m"]:.0f}pp</b>（{mlab(CALIB["jump_m_at"])}）；'
    f'12 个月滚动合计同比标准差 <b>{CALIB["sd_r"]:.1f}pp</b>、最大跳变 '
    f'<b>{CALIB["jump_r"]:.1f}pp</b>；两者<b>符号相反</b>的月份有 {CALIB["n_opp"]} 个'
    f'（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）'
    + (('，最近几例：' + '、'.join(
        f'{mlab(p)}（单月 {pct(r["m"])}／滚动 {pct(r["r"])}）'
        for p, r in CALIB['opp'].tail(3).iterrows()) + '。')
       if CALIB['n_opp'] else '。')
    + f'滚动同比的算法是「最近 12 个月合计 ÷ 上一个 12 个月合计 − 1」；实现上取滚动均值再相比 —— '
    f'窗口固定 12 个月，除以 12 是同一个常数，两者逐点严格相等，而均值让 ADV 类源列的单位'
    f'保持「千张/日」不变。第一个有值的点要等 24 个月（12 个月填窗 + 12 个月比较），'
    f'所以近期图窗口的左端可能没有折线，那不是缺数。'
    f'<b>不乘交易日数</b>：本页立场是 ADV 已按交易日中性化，实测也支持 —— 日均口径与'
    f'交易日加权口径的滚动同比最大只差 {DC_MAXGAP:.1f}pp，'
    + ('逐月符号完全一致' if DC_SAME_SIGN else '仍有符号不一致的月份')
    + f'，交易日效应在 12 个月窗口里基本自抵；为这点差别引入第二套聚合口径不划算。',

    f'<b>本页有三种同比口径，已逐处点名，不要跨口径比高低。</b>'
    f'（a）各 gs_bar 次轴的金色折线与 Exhibit {EX_DECOMP} / {EX_TTMVOL}：12 个月滚动合计同比；'
    f'（b）Exhibit {EX_QTR} 的绿线：本季 3 个月合计 vs 上年同季（柱是季度的，线只能与柱同期）；'
    f'（c）Exhibit {EX_DAYCOUNT}、Exhibit {EX_OI}、Exhibit {EX_HEAT_YOY} 与汇总表的 y/y 列：单月同比。'
    f'（c）里这四处保留单月各有理由 —— day-count 那张图的命题就是「一个月之内交易日数能把'
    f'方向读反」，平滑掉图就空了；<b>未平仓合约是存量</b>（月末快照），把 12 个月末的存量'
    f'加起来不是任何东西，而且存量不吃日历效应、单月同比本来就稳（本页实测标准差 '
    f'{CALIB_OI["sd_m"]:.1f}pp vs 总 ADV 的 {CALIB["sd_m"]:.1f}pp，相邻月最大跳变 '
    f'{CALIB_OI["jump_m"]:.0f}pp vs {CALIB["jump_m"]:.0f}pp）；'
    f'热力矩阵的用途是逐格看季节性与异常月，滚动值会把相邻 12 格'
    f'填成几乎同一个数、整表退化成一片同色；汇总表三列写死的是「本月/上月/去年同月」三个'
    f'具名月份，放滚动值进去与列头自相矛盾。'
    f'「流量用滚动、存量用点对点」这条判据不是本页自订的，实现在全站唯一的 '
    f'<code>build/yoy.py</code> 里，对存量调滚动合计会直接抛错。',

    '<b>ADV 与总量的口径差（Barclays 调整）。</b>ADV 本身已按交易日中性化，总成交合约数没有。'
    'Barclays 那份报告因交易日数差异，把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径整个反转。'
    f'Exhibit {EX_DAYCOUNT} 把两条同比并排画出来，两线之差纯粹是交易日数的变化；'
    '月度总成交量 = ADV × 当月交易日数，这一步换算是本页做的，不是公司披露的单独口径。'
    '汇总表末行的「Trading days」同理只是月历读数，所以它的 m/m、y/y 不着色、3Y %ile 留空 —— '
    '多一个交易日既不是好消息也不是坏消息。',

    f'<b>唯一的推导值：Exhibit {EX_REV}。</b>Implied transaction revenue = 当月成交合约数 × '
    f'每张平均费率（RPC）。RPC 是季度值（CME 季报），当季各月共用该季费率，'
    f'最新季（{qlab(RPC_Q)} = ${RPC_V:.3f}）'
    '之后沿用。CME 的 RPC 本身是用已披露收入倒推的，所以已收官季度只是把一个已知总额重建一遍 —— '
    '这张图的价值全在<b>当前未收官的季度</b>。标题带 Implied 即表示非公司披露值。'
    # 「用的是哪一季费率」随每月新数据自动变化，所以这句由数据现算，不写死季度号。
    + RATE_PERIOD + RATE_STALE,

    f'<b>RPC 的口径风险。</b>各品种 RPC 相差数倍（Exhibit {EX_RPC}），因此总 ADV 不变、'
    f'只要品种结构位移，混合费率与隐含收入照样会动。这是上面那座桥最大的不确定性，'
    f'也是 Exhibit {EX_MIX} 把结构与体量画在同一张图里的原因。',

    f'<b>未满季不可直读。</b>Exhibit {EX_QTR} 的末柱是季度至今（{_qs.index[-1]} 目前只含 '
    f'{_npart} 个月），'
    '用浅蓝标出，其右轴 y/y 的最后一点被引擎强制作废 —— 拿未满季的累计去比上年完整季，'
    '必然砸出一个纯口径造成的假坑。',

    '<b>汇总表的 3Y %ile。</b>= 当月读数在最近 36 个月里高于多少百分比的观测，'
    '由全站唯一的一份实现（<code>build/pctile.py</code>）算出，本页不再自带判据 —— '
    '各页各写一份，正是同一条序列在两页判定相反的原因。'
    '留空的判据是「把这一列在过去 24 个月里逐月回放一遍，若 ≥70% 的月份都钉在 100 或 0，'
    '这一列对这一行没有区分度」；旧判据「≥90% 的月环比不降」测的是序列形状而不是分位列本身，'
    '拦不住「上下波动但分位常年钉 100」的行。'
    '本页另有一处按自己的口径留空：Trading days 是日历产物（见第 3 条）。'
    '比率类指标的差异一律用 pp/bp；本页汇总表里没有比率行，故全部是百分比变化。',

    '<b>口径断点：本页没有，图上也确实一条都没画。</b>CME 的 ADV / 未平仓合约 / 交易日口径'
    f'自 {mlab(df.index[0])} 至今保持一致，品种六分类穷尽且互斥，所以全页没有红色竖虚线断点，'
    '相邻期可以直读 —— 本页任何一处图注都没有声称过存在断点线，说的和画的一致。'
    '若日后出现并购并表或品种重分类，必须在这里登记、给对应 exhibit 传 break_at 画出竖线，'
    '并在断点滚出窗口后让图注文案一起消失，不能只靠图注文字提一句、也不能因为断点滚出窗口就报错停更。',

    '<b>与原 PDF 版的有意差异（四处）。</b>'
    '(a) gs_bar 类近期图的窗口由 25 个月收到 13 个月 —— 契约 §5.4 的规定；次轴那条金色 y/y '
    '折线画的是同比而不是 12 个月均线（deck 的 docstring：「均线只是把柱子再平滑一遍、'
    '不带新信息」），这一点与 deck 一致；但<b>口径与 deck 有意不同</b> —— deck 画的是'
    '<b>单月</b>同比，网页版改画 <b>12 个月滚动合计同比</b>，理由与实测见上面的同比口径条。'
    f'曲线类（Exhibit {EX_DAYCOUNT}/{EX_MAJORS}/{EX_MINORS}）与长历史图（Exhibit {EX_HIST}）'
    '的窗口一字未改。'
    f'(b) deck 的品种曲线图把六个品种画在一根轴上，利率品种的峰值把其余四条压成底部一条带；'
    f'网页版按量级拆成 Exhibit {EX_MAJORS} 与 Exhibit {EX_MINORS} 两张，数据、窗口、配色全同，'
    f'没有删点、没有截轴（详见两图图注）。'
    '(c) 金属品种在 deck 里用金色 #BF9000，网页引擎的调色板后来补齐了同一个金色，'
    '所以两边同色；红色在本站是断点与离群值的专用色，不拿来当数据色。'
    f'(d) Exhibit {EX_HIST} 的「最近 3 个月红色虚线圈」与 Exhibit {EX_RPC} 的第三位小数'
    '无对应实现，前者说明写进图注，后者的精确值写进图注。',

    f'<b>Exhibit {EX_DECOMP} 分的是收入，不是成交额。</b>恒等式「隐含交易收入 = 成交合约数 × '
    f'每张平均费率」两边都在本页有数，所以这张分解做得成；而「成交额 = 成交量 × 均价」'
    f'那种分解本页<b>不具备数据条件</b> —— CME 按月披露的是合约张数与未平仓合约，'
    f'从来没有披露过成交<b>金额</b>；要凑一个名义本金得逐品种乘合约乘数，本仓的 '
    f'<code>series/contract_specs.csv</code> 只覆盖一部分品种，拿它当分母算出来的「均价」'
    f'方向与大小都不可知，而且图上完全看不出来。宁可不做。'
    f'分解本身是恒等式而不是估算：两块相加逐月等于总增长，生成脚本对<b>对数与算术两种分解</b>'
    f'的残差都设了 1e-9 的硬门槛，超了直接退出、不出图。'
    f'图上画的是<b>对数分解</b>（ln 天然可加、对称，不必选交叉项归谁）；算术分解照算但只进图注 —— '
    f'算术版必须把交叉项整段压进费率那一块，本页实测交叉项占净增长中位 {_CROSS_MED:.1f}%、'
    f'最大 {_CROSS_MAX:.0f}%，量与费率方向对冲的年份画出来就是错的。'
    f'费率那一块要按「结构 + 定价」读，不能当纯价格 —— RPC 是 CME 从'
    f'已披露收入倒算的，各品种 RPC 相差数倍（Exhibit {EX_RPC}），品种结构一位移它就动。',

    f'<b>核对表（Exhibit {EX_TABLE}）用官方原始单位，不做任何换算</b>：ADV 为千张/日、'
    '未平仓合约为张、交易日为天，可直接与 CME 月度 xlsx 逐格对。'
    '图上的「百万张」「百万美元」都是本页换算后的口径，核对时请以核对表为准。',
]

# ══════════════════════════ 7. 抬头与 payload ══════════════════════════
_adv_yy = float(df['adv_yoy'][CUR])
# 抬头原先只写 y/y。7 月 ADV 是 +23.0% y/y 但 −11.9% m/m（一年里第二大的环比跌幅），
# 只报同比等于把「本月比上月掉了一成多」藏到表格里，读者不往下翻就得到一个纯正面的印象。
# 同比与环比同时给，哪一个难看都照写。
_adv_mm = (float(df['adv_mn'][CUR]) / float(df['adv_mn'][PRV]) - 1) * 100
_vol_yy = float(df['vol_yoy'][CUR])
_vol_mm = (float(df['total_vol_mn'][CUR]) / float(df['total_vol_mn'][PRV]) - 1) * 100
_dc = float(df['daycount_effect'][CUR])
_oi_yy = (float(df['oi_total_mn'][CUR]) / float(df['oi_total_mn'][YAG]) - 1) * 100
_share = float(df['rates_share'][CUR])
# 抬头原先只有单月 y/y 与 m/m。用户的核心诉求正是「单月同比未必反映真实趋势」——
# 而抬头是全页曝光最高的一行，把一个 33% 概率与趋势符号相反的数放在这里、
# 不给任何对照，是本页最容易被读反的地方。补上 TTM 口径，两个都写、哪个难看都照写。
_adv_ttm = float(roll_yoy(adv).get(CUR, np.nan))

payload = {
    'ticker': 'cme',
    'tracker': 'CME Monthly Volume Tracker',
    'title': f'CME Group (CME): 月度成交量跟踪 — {CUR.year}年{CUR.month}月',
    'data_through': str(CUR),
    'through_label': f'{CUR.year} 年 {CUR.month} 月',
    'subtitle': (f'数据源：CME Group IR 月度成交量报告（次月第 1-2 个工作日发布）· '
                 f'覆盖 {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）· '
                 f'版式仿 Goldman Sachs GIR「IBKR Monthly」与 Barclays day-count 调整 · 仅图，无评论'),
    'headline': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日（单月 {pct(_adv_yy)} y/y，'
                 f'{pct(_adv_mm)} m/m；TTM {pct(_adv_ttm)} y/y）· '
                 f'总成交 {df["total_vol_mn"][CUR]:,.0f}mn 张（单月 {pct(_vol_yy)} y/y，'
                 f'{pct(_vol_mm)} m/m，交易日贡献 {pp(_dc)}）· '
                 f'近 12 个月成交 {float(df["ttm_vol_mn"][CUR]):,.0f}mn 张 · '
                 f'月末未平仓 {df["oi_total_mn"][CUR]:,.1f}mn 张'
                 f'（单月 {pct(_oi_yy)} y/y）· 利率品种占 ADV {_share:.0f}% · '
                 f'隐含交易收入 ${df["implied_txn_rev_usdmn"][CUR]:,.0f}mn'),
    'hub_line': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日，TTM {pct(_adv_ttm)} y/y；'
                 f'单月 {pct(_adv_yy)} y/y、{pct(_adv_mm)} m/m'),
    'source': SRC,
    'xlabels': XL13,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    'exhibits': ex,
    'table': table,
    'notes': NOTES,
    'footer': 'CME Group (CME) · monthly volume reports · charts only, no commentary · '
              'personal research use',
}

# 抬头右侧那半句「官方发布于 X」是关于外部世界的事实断言，只能取台账里记下的、
# 由源头自己给出的日期（CME 这家是 xlsx 的 Last-Modified 与工作簿保存时间戳互证，
# 见 fetch/cme.py 的 _publish_date）。台账里没有就**整个字段不写** ——
# 页面判的是字段在不在，塞 None 会把那半句变成「官方发布于 None」。
_SOURCE_DATE = source_dates.lookup(SERIES, 'cme', str(CUR))
if _SOURCE_DATE:
    payload['source_date'] = _SOURCE_DATE


def main():
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cme')
    print(f'数据截至 {CUR} | 月份 {df.index[0]} → {LATEST}（{len(df)}）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
