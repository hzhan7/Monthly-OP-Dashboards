# -*- coding: utf-8 -*-
"""亚太交易所横截面（HKEX / JPX / SGX / ASX）—— 写出 data/exchanges-apac.js。

═══════════════════════════════════════════════════════════════════════════
这一页与 /exchanges-na/ 的根本区别：**它不画份额，一个字都不画**
═══════════════════════════════════════════════════════════════════════════
北美页能说「市场份额」，是因为 ICE 逐月披露官方行业总量（tape A/B/C 合并成交量、
全美期权 ADV），四家争的是同一批订单流，分母是外部给的。

亚太没有这个东西，而且**不是「暂时缺一个分母」，是这四家压根不在同一个池子里抢单**：
HKEX / JPX / SGX / ASX 是法域隔离的市场，几乎零替代性 —— 想买澳洲股票的资金不会
因为 HKEX 费率低就流去香港，想买日本股票的资金也不会因为 SGX 便宜就改买新加坡股票。
把四家的成交额相加当分母，会得到一个**没有外部指涉**的数字：加进一家台湾或韩国，
所有人的「份额」立刻全变；拿掉 ASX，其余三家又全变。那个比值唯一反映的是
「谁碰巧长得快」，而这件事用增长率讲更直接、也不会被读成「谁抢了谁的单」。

所以本页的口径是：
  · **增长对比**（定基名义额指数化，锁 2019-01 汇率）—— 回答「谁在长」；
  · **产品级头对头**（同标的双挂牌）—— 回答「谁抢了谁」。这才是亚太真正的零和：
    日经 225 期货在 SGX 与大阪（JPX）双挂牌，同一个指数、同一批套利者，
    一边多一张另一边就少一张。这是本页唯一能说「争夺」的地方。

**页面上不出现「市场份额」四个字**，注 1 把上面这段话写给读者。

═══════════════════════════════════════════════════════════════════════════
汇率：锁基期，不锁就是把日元贬值读成「日本成交量萎缩」
═══════════════════════════════════════════════════════════════════════════
四家的原始披露是四种货币（HK$bn / ¥tn / S$mn / A$bn），要放进一张图必须折美元。
主口径一律用 **2019-01 的月均汇率**折算（series/fx.csv 的 fx_avg_*usd），此后汇率是常数
⇒ 每条线的增长率与它本币口径的增长率**完全相同**，汇率波动进不了增长结论。
另算一条「当期汇率」口径只做对照（Exhibit 4 / 6），不进任何增长结论 ——
日元 2019-01 以来对美元累计跌三成，当期汇率口径会把 JPX 的七年半增长凭空削掉一大截。

⚠ 头条源列都是**成交金额**（股数 × 当期价格）⇒ 主口径那四条线只能剔汇率、
**剔不掉标的涨跌**（pools.py 的 deflator='fx_only'）。港股或日股一轮大涨会抬高这条线，
那不是成交活跃度全部的涨幅。图注逐张写明。

但「剔不掉」这件事**四家并不一样**（本轮逐列核过 series/*.csv 的表头）：
  · JPX / SGX **披露成交股数** ⇒ 均价 = 成交额 ÷ 股数 能算出来，成交额的增长
    可以拆成「量的贡献」与「价的贡献」（Exhibit 15–17，见下方第 6b 节）；
  · HKEX 月报**只有金额**（adt_hkdbn），没有任何量的列 ⇒ 拆不了，Exhibit 15 那一列留空；
  · ASX 没有股数，只有成交**笔数**与每笔均值 ⇒ 只能做「笔数 × 每笔均值」这**另一种**
    恒等式，与前两家不是同一种分解，图上用红虚线隔在一边。
⚠ 拆出来的「价」是**加权平均成交价**（成交额 ÷ 股数），它同时含市场涨跌**与成交结构变化**
（贵的股票交易占比上升也会抬高它），**不是指数收益率**，不能读成「大盘涨了多少」。
所以主口径那四条线仍然只剔汇率，分解只在能算的两家、且只在图注写清含义的前提下出现。

═══════════════════════════════════════════════════════════════════════════
衍生品：只有张数，没有基期价格 ⇒ 各自指数化，水平值不可跨所比
═══════════════════════════════════════════════════════════════════════════
series/contract_specs.csv 里四家衍生品篮子的 base_price_local **凑不齐**，定基名义额
算不出来。⚠️ **这一段不许写死「谁有、谁没有」的名单**：填没填是 CSV 里的一格，随时会变，
写进散文就得有人每月来核。缺谁一律由 `bp_txt()` 在构建期现读 contract_specs.csv 算出来，
正文与图注都只印它的返回值。判据也别写成「一家都没有」（那句已经被表本身证伪过一次），
真正成立的是「**缺一家就没有共同口径**」——`bp_txt()` 说的就是这一句。
所以衍生品这一段**各家用自己的张数指数化**，只比增速、不比水平 —— 张数的单张大小是
各所自己选的产品设计参数（JPX 的 mini 是大板的 1/10、micro 是 1/100），
跨所比水平值等于比谁把合约切得更碎。
Exhibit 9 把这件事直接画出来：JPX 的原始张数与它自己的「大合约当量」差几倍
由页上那句现算（`DERIV['jpx'][CUR] ÷ JPX_LGEQ[CUR]`）。
⚠️ **这里不许抄那个倍数**：它逐月在变，抄一次下个月就与同一页上的数打架 ——
上一版抄过 4.5，被当期读数证伪；改写时又顺手抄了一次当期值，同一个坑踩了两遍。

═══════════════════════════════════════════════════════════════════════════
数据源（只读 series/*.csv）
═══════════════════════════════════════════════════════════════════════════
  series/hkex.csv  HKEX Monthly Market Highlights
  series/jpx.csv   JPX 月度统计（现货 + 大阪衍生品分产品）
  series/sgx.csv   SGX Monthly Volume Statistics（分产品是**当月总量**，不是日均）
  series/asx.csv   ASX Monthly Activity Report
  series/fx.csv    月均与月末汇率

用法: python3 build/exchanges_apac.py   （可重复跑，除首行构建日期外逐字节相同）
门槛算不出就打印原因并以退出码 0 结束。
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

import axisfmt
import glossary as gloss   # 名词释义的版式层与护栏，全站共用
import payload_guard
import pctile
import pools
import yoy as YOY   # 同比口径的**唯一实现**（build/yoy.py）：单月同比与口径对比诊断一律走它，
                    # 不自己写 pct_change(12)。别写成 `import yoy` —— 本文件里有个同名的
                    # 局部函数 yoy()（汇总表那四行的单月同比），会把模块整个盖掉。

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

TICKER = 'exchanges-apac'
OUT = os.path.join(ROOT, 'data', f'{TICKER}.js')
PAGE_DIR = os.path.join(ROOT, TICKER)

SRC = ('Source: HKEX / JPX / SGX / ASX monthly volume disclosures; FX from series/fx.csv; '
       'format after Goldman Sachs GIR')

# 成员固定配色（与 build/pools.py 的 apac_cash / apac_deriv 逐字一致 —— 同一家在两张页上
# 换色，读者跨页对照就全废了）。RED 是断点专用色，不做数据色。
C_HK, C_JP, C_SG, C_AX = 'GOLD', 'NAVY', 'MBLUE', 'GREEN'

BASE_M = '2019-01'          # 全仓唯一基期（= build/notional.py BASE_MONTH）
WIN_LINE = 25               # 短窗口 x 轴
LINE_H = 360                # 开了 end_label 的长历史线图必须 ≥360，见 CHART_KINDS §3.9
TBL_MONTHS = 13
MIN_COMMON = 24
HEAT_QTRS = 24              # 季度同比矩阵的列数
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# HKEX 推出 MSCI 中国 A50 互联互通期货的月份。日期来自 HKEX 官方新闻稿
# 《HKEX Launches MSCI China A 50 Connect Index Futures》(2021-10-18)，
# URL 路径本身带日期：hkex.com.hk/News/News-Release/2021/211018news
A50_RIVAL_M = '2021-10'
A50_RIVAL_TXT = 'HKEX 推出 MSCI 中国 A50 互联互通期货（2021-10-18）'


# ────────────────────────────── 通用零件 ──────────────────────────────
def mlab(p):
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def qlab(q):
    return f'{q.quarter}Q{q.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def num(v, dec=0):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'


def pct(v, dec=1):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+,.{dec}f}%'


def pp(v, dec=1):
    """比率类指标的差异一律 pp/bp（契约 §2：|v| < 1pp 时写 bp）。"""
    if v is None or not np.isfinite(v):
        return '—'
    if abs(_z(v, dec)) < 1:
        return f'{_z(v * 100, 0):+,.0f}bp'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None，线在缺口处断开而不是直连）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6)
            for v in a]


def skip(msg):
    """成员没齐 —— 打印原因，退出码 0（monthly_run 下次例行跑会自动重试）。"""
    print(f'{TICKER}: 跳过，未达发布门槛 —— {msg}')
    print('横截面页只在成员齐了之后生成；这不是失败，退出码 0。')
    sys.exit(0)


def read_csv(name):
    """series/<name> → 连续月度 PeriodIndex 的 DataFrame（全列转数值）。

    reindex 成连续月：原文件若中间缺月，pct_change(12) 会按**位置**移 12 行，
    算出来的「同比」其实跨了 13 个月而完全看不出来。
    """
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if 'month' not in d.columns:
        raise SystemExit(f'series/{name} 缺 month 列')
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    d = d.set_index('month').sort_index()
    d = d.apply(pd.to_numeric, errors='coerce')
    return d.reindex(pd.period_range(d.index[0], d.index[-1], freq='M'))


def load_source_dates():
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────────── 1. 读数据 ──────────────────────────────
# (key, 显示名, csv, 头条现货列, 官方原始单位, 币种, 折美元 bn 的乘数, 颜色)
#   折算式：USD bn/day = 原始列 × scale × fx_<ccy>usd
HEAD = [
    ('hkex', 'HKEX',      'hkex.csv', 'adt_hkdbn',              'HK$bn/day', 'hkd', 1.0,      C_HK),
    ('jpx',  'JPX（东证）', 'jpx.csv',  'adt_cash_total_jpytn',   '¥tn/day',   'jpy', 1000.0,   C_JP),
    ('sgx',  'SGX',       'sgx.csv',  'sdav_sgdmn',             'S$mn/day',  'sgd', 1 / 1000.0, C_SG),
    ('asx',  'ASX',       'asx.csv',  'adt_cash_onmarket_audbn', 'A$bn/day',  'aud', 1.0,      C_AX),
]
KEYS = [k for k, *_ in HEAD]
DISP = {k: d for k, d, *_ in HEAD}
COLOR = {k: c for k, *_r, c in HEAD}

RAW = {k: read_csv(csv) for k, _, csv, _, _, _, _, _ in HEAD}
FX = read_csv('fx.csv')


def rawcol(key, name):
    """RAW[key] 的某一列；列不在就返回一条全 NaN 的同索引序列（不抛，让调用处判空）。"""
    d = RAW[key]
    if name in d.columns:
        return d[name]
    return pd.Series(np.nan, index=d.index, dtype=float)


def _fin(s):
    """去掉 NaN/inf 的 Series；空的返回空 Series（调用处一律要判空）。"""
    return s.replace([np.inf, -np.inf], np.nan).dropna() if s is not None else pd.Series(dtype=float)


def _rng(s, unit, dec=1):
    """min–max（区间两端 + 中位 + 覆盖区间），供图注直接嵌。空序列返回 None。"""
    s = _fin(s)
    if not len(s):
        return None
    return (f'{s.min():.{dec}f}{unit}–{s.max():.{dec}f}{unit}'
            f'（{mlab(s.index[0])}–{mlab(s.index[-1])} 全区间共 {len(s)} 个月，'
            f'中位 {s.median():.{dec}f}{unit}）')


missing, latest_each = [], {}
if FX is None:
    skip('缺 series/fx.csv —— 四种货币折不成美元，本页每一张图都要它')
for key, disp, csvname, col, _u, _c, _s, _col in HEAD:
    d = RAW[key]
    if d is None:
        missing.append(f'{disp}（缺 series/{csvname}）')
        continue
    if col not in d.columns:
        missing.append(f'{disp}（series/{csvname} 缺列 {col}）')
        continue
    s = d[col].dropna()
    if s.empty:
        missing.append(f'{disp}（{col} 没有任何有效值）')
        continue
    latest_each[key] = s.index[-1]
if missing:
    skip('成员未就绪：' + '；'.join(missing))

LATEST = min(latest_each.values())
START = max(RAW[k][c].dropna().index[0] for k, _, _, c, _, _, _, _ in HEAD)
BASE = pd.Period(BASE_M, freq='M')
if START > BASE:
    # 共同起点晚于全仓基期时，基期改成共同起点 —— 否则指数化会在没有数据的月份取基数。
    BASE = START
if START >= LATEST or (LATEST - START).n + 1 < MIN_COMMON:
    skip(f'共同历史只有 {max(0, (LATEST - START).n + 1)} 个月'
         f'（{mlab(START)} – {mlab(LATEST)}），不足 {MIN_COMMON} 个月')
if FX.index[-1] < LATEST or BASE not in FX.index:
    skip(f'series/fx.csv 覆盖 {FX.index[0]}–{FX.index[-1]}，'
         f'盖不住基期 {BASE} 或共同最新月 {LATEST}')

IDX = pd.period_range(START, LATEST, freq='M')
XL_LONG = [mlab(p) for p in IDX]
XL25 = [mlab(p) for p in IDX[-WIN_LINE:]]
LAG = [DISP[k] for k in KEYS if latest_each[k] == LATEST]
AHEAD = [(DISP[k], latest_each[k]) for k in KEYS if latest_each[k] > LATEST]
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12

# ── 谁有「现货交易日数」这一列：现读 series/*.csv，不在散文里断言 ────────────────
# ⚠ 本页从前有六处写着「四家里只有三家有交易日列（HKEX 没有）」，并拿它当
#   「所有滚动合计与季度值一律等权相加、不做交易日加权」的**理由**。2026-09 现读实测：
#   这句话不成立 —— hkex.csv 有 `trading_days_cash`，而且在本页窗口里一格不缺。
#   两件事要分开处理：
#     · **文案**：那句理由撤掉，改由这里现算的名单说话（本轮撤的就是它）。
#     · **口径**：等权这一条**不动**。Exhibit 5 / 15 在 CONTRACT.md §6.2 的保留名单上，
#       换加权方式会动它们的读数，那是页面所有者的决定，不是文案修订能顺手做的。
#       等权与日加权差多少一直是实测印出来的（QW_DEV / TTM_QW_DEV / DEC_DW_DEV），
#       现在这三个数覆盖到**所有有交易日列的成员**，不再漏掉 HKEX。
_DAY_EXCL = ('futures', 'eto', 'deriv', 'options')


def _daycol(k):
    """该家的现货交易日列名；没有或认不准就返回 None（不猜）。"""
    cands = [c for c in RAW[k].columns
             if 'trading_days' in c and not any(x in c for x in _DAY_EXCL)]
    cands = [c for c in cands if RAW[k][c].reindex(IDX).notna().all()]
    if len(cands) == 1:
        return cands[0]
    if len(cands) > 1:
        raise SystemExit(f'{DISP[k]} 有多列长得像现货交易日数（{cands}）—— '
                         f'本页要拿它算日加权对照，认不准就不许猜，先在这里点名选哪一列')
    return None


DAYCOL = {k: _daycol(k) for k in KEYS}
DAYW_HAVE = [k for k in KEYS if DAYCOL[k]]
DAYW_NONE = [k for k in KEYS if not DAYCOL[k]]
DAYW_TXT = (f'{len(KEYS)} 家里 {len(DAYW_HAVE)} 家有可用的现货交易日列，'
            f'缺的是 {"、".join(DISP[k] for k in DAYW_NONE)}'
            if DAYW_NONE else f'{len(KEYS)} 家都有可用的现货交易日列')
if not DAYW_HAVE:
    skip('四家都没有现货交易日列 —— 等权与日加权的实测对照这一轮做不了')

# 基期汇率：锁死一次，之后全页只用这四个常数
FXCOL = {k: f'fx_avg_{c}usd' for k, _, _, _, _, c, _, _ in HEAD}
for k, c in FXCOL.items():
    if c not in FX.columns:
        skip(f'series/fx.csv 缺列 {c}（{DISP[k]} 折不成美元）')
FX_BASE = {k: float(FX[FXCOL[k]][BASE]) for k in KEYS}
# 币种代码（HKD / JPY / SGD / AUD）。汇率图的图例只能用它，不能用 UNIT_RAW ——
# 后者是**成交额的计量单位**（HK$bn、¥tn、S$mn），在一张纵轴是「% vs Jan-19」的
# 汇率变动图上写「SGX（S$mn）」，读者会以为那条线的单位是百万新元。
CCY = {k: c.upper() for k, _, _, _, _, c, _, _ in HEAD}
SCALE = {k: s for k, _, _, _, _, _, s, _ in HEAD}
UNIT_RAW = {k: u for k, _, _, _, u, _, _, _ in HEAD}
HEADCOL = {k: c for k, _, _, c, _, _, _, _ in HEAD}


def usd_base(key):
    """某家现货成交额 → US$bn/日，**锁 2019-01 汇率**。返回该家自己的完整历史。"""
    return RAW[key][HEADCOL[key]] * SCALE[key] * FX_BASE[key]


def usd_cur(key):
    """同上，但用**当期**月均汇率 —— 只做对照，不进任何增长结论。"""
    return RAW[key][HEADCOL[key]] * SCALE[key] * FX[FXCOL[key]]


CASH = {k: usd_base(k) for k in KEYS}          # 各家完整历史（不截共同窗口）
CASH_CUR = {k: usd_cur(k) for k in KEYS}

# 失败要响：共同窗口内头条序列有洞 = 源数据坏了，不是「成员没齐」
for k in KEYS:
    holes = [str(p) for p in IDX if not np.isfinite(float(CASH[k].get(p, np.nan)))]
    if holes:
        raise SystemExit(f'{DISP[k]} 现货序列在共同窗口 {mlab(START)}–{mlab(LATEST)} '
                         f'内缺值：{holes}')


def clip(s):
    return s.reindex(IDX)


def yoy(s):
    """同比先在该家**自己的完整历史**上算，再截共同窗口（先截再算会白扔 12 个月）。"""
    return (s.pct_change(12) * 100).reindex(IDX)


def ttm(s):
    """12 个月滚动合计。

    源列是**日均值**（ADT / ADV），这里按本页既有做法做**等权**合计（不乘交易日），
    与 Exhibit 3 的季度值口径一致。⚠ 从前这里给的理由是「四家里只有三家有交易日列
    （HKEX 没有）」—— 现读实测不成立，见 `DAYCOL` 那一段；口径不动（§6.2 保留名单），
    撤掉的是那句理由，代价改由覆盖全部有交易日列成员的 QW_DEV / TTM_QW_DEV 实测。因为分子分母都恰好是 12 个月，「合计的同比」与「均值的同比」
    逐位相同（Σ12/Σ12′ 里的除数约掉，只剩浮点尾差），所以写成 sum 还是 mean
    不影响任何读数。⚠ 这里从前写死过一个「本轮实测最大差 3e-14pp」——
    那个数没有任何东西每轮重算它，别再往回加。
    `rolling` 默认 min_periods = 窗口长度 ⇒ 窗口内有一个 NaN 就整段作废，
    不会拿 11 个月冒充 12 个月。
    """
    return s.rolling(12).sum()


def ttm_yoy(s):
    """12 个月滚动合计的同比（%）。**本页现在只有 Exhibit 5 这一路用它**
    （页顶数据条里那串标着「年度口径」的现货 y/y 与 Exhibit 5 的柱是同一个数）。

    ⚠ **Exhibit 15 的菱形不走这个函数，也不等于 Exhibit 5 那根柱。** 它同样是
    「12 个月滚动合计的同比」、窗口逐字相同，但底料是 `_decomp()` 里那批**更窄的列**
    （为了让分子分母同口径：JPX 换 `adt_cash_stocks_jpytn`、ASX 换含场外报告的总额），
    所以两个数不一样。差多少由 `_gap_txt` / `_gap_max` **逐家现算**并印在 Exhibit 15
    的图注里 —— 别在别处写成「菱形就是那根柱」，CONTRACT.md §6.2 逐字禁止这个说法。

    **hub 行不用它** —— 那句会被抄进首页卡片，只准出现单月读数。

    ⚠ 别再写「本页同比一律用这个口径」：Exhibit 17 已按页面所有者的指令改成**单月同比**
    （走 `yoy.mom_yoy`），本页因此**并存两种口径**，页尾「口径与方法说明」里逐处点名。
    这个函数是历史遗留的本地实现，保留它是因为 Exhibit 5 的三根柱还在用；
    新增的同比一律走 `build/yoy.py`。"""
    return ttm(s).pct_change(12) * 100


def idx100(s, base=None):
    b = float(s[base or BASE])
    if not np.isfinite(b) or b == 0:
        raise SystemExit(f'指数化基期 {base or BASE} 无有效值')
    return s / b * 100


# ────────────────────────── 2. 衍生品（张数口径，各自指数化）──────────────────────────
DERIV = {
    'hkex': RAW['hkex']['derivatives_adv_contracts'],
    # JPX 用**原始张数**（= 官方新闻稿口径）；大合约当量另画一张（Exhibit 9）
    'jpx': RAW['jpx']['adv_deriv_total_raw_kcontracts'] * 1000.0,
    # ⚠ SGX 存的是裸张数（不是千张），实测 2026-06 = 1,619,444 即官方 DDAV 原值
    'sgx': RAW['sgx']['ddav_contracts'],
    # ASX 三条腿：ASX24 期货与期货期权合计 + 个股期权 + 指数期权
    'asx': (RAW['asx']['adv_futures_and_options_contracts']
            + RAW['asx']['adv_single_stock_options_contracts']
            + RAW['asx']['adv_index_options_contracts']),
}
JPX_LGEQ = RAW['jpx']['adv_deriv_total_lgeq_kcontracts'] * 1000.0
for k in KEYS:
    if not np.isfinite(float(DERIV[k].get(BASE, np.nan))):
        skip(f'{DISP[k]} 的衍生品 ADV 在基期 {mlab(BASE)} 无值，指数化做不了')

# ── 「为什么只能指数化」那句话的判据：现读 contract_specs.csv，不写死 ──────────
# 旧文案写的是「四家的衍生品篮子 base_price_local **全是空的**」，被表本身证伪。
# 真正成立的判据是**四家里只要有一家缺，池就折不出定基名义额** —— 所以这里算
# 「缺的是谁」，措辞跟着算出来的名单走。
# 篮子成员也**不在本文件抄一份**：直接读 build/pools.py 的 apac_deriv，那才是唯一的
# 定义处。抄一份的后果是静默的 —— pools 那边加一条腿，本页照旧宣称「都齐了」。
_APAC_DERIV_POOL = next((_p for _p in pools.POOLS if _p['id'] == 'apac_deriv'), None)
if _APAC_DERIV_POOL is None:
    raise SystemExit('build/pools.py 里找不到 apac_deriv 池 —— '
                     '本页的衍生品篮子名单以它为唯一定义处，找不到就不能发')
_DERIV_BASKETS = {_m['key']: [_c['product'] for _c in _m['chain']]
                  for _m in _APAC_DERIV_POOL['members']}
if set(_DERIV_BASKETS) != set(KEYS):
    raise SystemExit(f'apac_deriv 的成员 {sorted(_DERIV_BASKETS)} 与本页的四家 '
                     f'{sorted(KEYS)} 对不上 —— 页上「缺基期价格的是谁」那句话'
                     f'就会漏算或多算，先把两处对齐再发')


def _base_prices():
    """product_id -> base_price_local（空串/缺行都算「没有」）。读不到表就返回 None，
    调用方退回不带名单的定性措辞，不抛异常。"""
    path = os.path.join(SERIES, 'contract_specs.csv')
    try:
        t = pd.read_csv(path, dtype=str).fillna('')
    except Exception:                                    # noqa: BLE001
        return None
    return {r['product_id']: r['base_price_local'].strip() for _, r in t.iterrows()}


_BP = _base_prices()
if _BP is None:
    BP_MISS, BP_HAVE = None, None
else:
    BP_MISS = [(k, pid) for k in KEYS for pid in _DERIV_BASKETS[k] if not _BP.get(pid)]
    BP_HAVE = [(k, pid) for k in KEYS for pid in _DERIV_BASKETS[k] if _BP.get(pid)]


def _spec_mults():
    """product_id -> 「乘数 + 单位」的人话字符串。读不到表返回 None（调用方退回定性措辞）。"""
    path = os.path.join(SERIES, 'contract_specs.csv')
    try:
        t = pd.read_csv(path, dtype=str).fillna('')
    except Exception:                                    # noqa: BLE001
        return None
    out = {}
    for _, r in t.iterrows():
        m, u = r.get('multiplier', '').strip(), r.get('mult_unit', '').strip()
        if m:
            out[r['product_id'].strip()] = f'{float(m):,.0f} {u}' if u else f'{float(m):,.0f}'
    return out


_SPEC_MULT = _spec_mults()
# 日经三档的乘数：**现读那张表**，而不是在散文里抄一份。
# ⚠ 这里从前写的是「三者的乘数已实测入库 series/contract_specs.csv：大板 ¥1,000/点、
#   mini ¥100、micro ¥10」—— 前半句对表里那两行成立，对 micro **不成立**：
#   contract_specs.csv 至今没有 JPX_N225_MICRO 这一行（micro 的 ÷100 折算核在
#   fetch/jpx.py 的 _DIVISORS 上，那里逐档对过官方 Contract Specifications 页）。
#   所以措辞跟着表算：表里有的逐个印出来，没有的点名它在哪儿核的。
_N225_TIERS = [('JPX_N225_FUT_LARGE', '大板'), ('JPX_N225_MINI', 'mini'),
               ('JPX_N225_MICRO', 'micro')]
if _SPEC_MULT is None:
    N225_MULT_TXT = ('series/contract_specs.csv 读不到，三档乘数这一轮无从现读；'
                     '折算系数本身核在 <code>fetch/jpx.py</code> 的 <code>_DIVISORS</code> 上')
else:
    _n_have = [(lab, pid) for pid, lab in _N225_TIERS if pid in _SPEC_MULT]
    _n_miss = [(lab, pid) for pid, lab in _N225_TIERS if pid not in _SPEC_MULT]
    N225_MULT_TXT = (
        ('已入库 <code>series/contract_specs.csv</code> 的是 '
         + '、'.join(f'{lab} {_SPEC_MULT[pid]}' for lab, pid in _n_have)
         if _n_have else '<code>series/contract_specs.csv</code> 里这三档一行都没有')
        + (f'；{"、".join(lab for lab, _p in _n_miss)} 那 {len(_n_miss)} 档<b>不在这张表里</b>，'
           f'它的折算系数核在 <code>fetch/jpx.py</code> 的 <code>_DIVISORS</code> 上'
           f'（那里逐档对过官方 Contract Specifications 页）' if _n_miss else ''))


def todo_tried(product_id):
    """待办台账里某个合约「上次尝试取规格」的日期 —— 现读 contract_specs_todo.csv。

    图注里从前写的是「rulebook 直链**本轮实测** 404」。本页从来不发那个请求，
    所以「本轮实测」是一句谎：真正做过那次尝试的是 fetch 侧，日期记在台账的
    `last_tried` 列上。这里现读它，读不到就整句不写日期（别自己编一个）。
    """
    path = os.path.join(SERIES, 'contract_specs_todo.csv')
    try:
        t = pd.read_csv(path, dtype=str).fillna('')
    except Exception:                                    # noqa: BLE001
        return None
    row = t[t['product_id'].str.strip() == product_id]
    if row.empty or 'last_tried' not in t.columns:
        return None
    return (row.iloc[0]['last_tried'] or '').strip() or None


SGX_NK_TRIED = todo_tried('SGX_NK_NIKKEI225')
SGX_NK_TRIED_TXT = (f'台账 <code>last_tried</code> 记的上次尝试是 {SGX_NK_TRIED}'
                    if SGX_NK_TRIED else '台账没记上次尝试的日期')


def bp_txt():
    """「基期价格缺在哪」的一句话，全部现算。"""
    if _BP is None:
        return ('series/contract_specs.csv 读不到，衍生品篮子有没有基期价格无从判断，'
                '本页按最保守的口径处理：只指数化。')
    if not BP_MISS:
        return ('series/contract_specs.csv 里四家的衍生品篮子基期价格都齐了 —— '
                '这段措辞本该跟着改，出现即说明文案没跟上数据。')
    miss = '、'.join(f'<code>{pid}</code>' for _k, pid in BP_MISS)
    have = '、'.join(f'<code>{pid}</code>' for _k, pid in BP_HAVE)
    return (f'series/contract_specs.csv 里衍生品篮子的 <code>base_price_local</code> '
            f'还缺 {len(BP_MISS)} 个（{miss}）'
            + (f'；已填上的是 {have}' if BP_HAVE else '')
            + '。定基名义额要四家都有基期常数才折得出来，缺一个这张图就没有共同口径 —— '
              '所以这一段只剩张数。')

# ────────────────────────── 3. 产品级：日经 225 双挂牌 ──────────────────────────
# SGX 的分产品列是**当月总量**，不是日均 ⇒ 必须除以交易日才能与 JPX 的 ADV 同轴。
# 用 deriv_vol ÷ ddav 反推的**隐含衍生品交易日**，不用 sec_trading_days ——
# 后者是证券市场的日历，实测两者最大差 3.27 天（docs/verify/sgx.md 口径坑 4）。
SG_DAYS = RAW['sgx']['deriv_vol_contracts'] / RAW['sgx']['ddav_contracts']
SG_DAYS_DEV = float((SG_DAYS - RAW['sgx']['sec_trading_days']).abs().max())


def sgx_adv(col):
    return RAW['sgx'][col] / SG_DAYS


NK_SG = sgx_adv('vol_nikkei225_futures_contracts')
# JPX 侧用官方的「大合约当量」：large + mini/10 + micro/100。
# 不用原始张数 —— 那是把 mini 与 micro 当成整张来数，2023-05 micro 上市当月就会跳一级。
NK_JP = RAW['jpx']['adv_n225_lgeq_kcontracts'] * 1000.0
# 这条恒等式的残差**现算**（从前图注里写的是「实测逐位相符」—— 一句不带数、
# 也没有任何东西会在它不再成立时报警的话）。单位是千张/日，与官方印数同量级。
_nk_id = _fin(rawcol('jpx', 'adv_n225_futures_kcontracts')
              + rawcol('jpx', 'adv_n225_mini_kcontracts') / 10.0
              + rawcol('jpx', 'adv_n225_micro_kcontracts').fillna(0) / 100.0
              - rawcol('jpx', 'adv_n225_lgeq_kcontracts')).abs()
NK_LGEQ_MAXERR = float(_nk_id.max()) if len(_nk_id) else float('nan')
NK_LGEQ_N = len(_nk_id)
NK_JP_RAW = ((RAW['jpx']['adv_n225_futures_kcontracts']
              + RAW['jpx']['adv_n225_mini_kcontracts']
              + RAW['jpx']['adv_n225_micro_kcontracts'].fillna(0)) * 1000.0)

NK_START = max(NK_SG.dropna().index[0], NK_JP.dropna().index[0])
NK_IDX = pd.period_range(NK_START, LATEST, freq='M')
NK_XL = [mlab(p) for p in NK_IDX]
NK_SG_W, NK_JP_W = NK_SG.reindex(NK_IDX), NK_JP.reindex(NK_IDX)
NK_RATIO = NK_SG_W / NK_JP_W                      # 张数比值（乘数未归一）
NK_SHARE = NK_SG_W / (NK_SG_W + NK_JP_W) * 100    # 张数口径的分流比例
NK_RATIO_IDX = NK_RATIO / float(NK_RATIO.iloc[0]) * 100
NK_RATIO_R12 = NK_RATIO.rolling(12).mean() / float(NK_RATIO.iloc[0]) * 100

# ────────────────────────── 4. 产品级：中国 A50 与台湾指数授权迁移 ──────────────────────────
A50_SG = sgx_adv('vol_a50_futures_contracts')
A50_IDX = pd.period_range(max(A50_SG.dropna().index[0], NK_START), LATEST, freq='M')
A50_XL = [mlab(p) for p in A50_IDX]
A50_W = A50_SG.reindex(A50_IDX)
_riv = pd.Period(A50_RIVAL_M, freq='M')
A50_BRK = int(list(A50_IDX).index(_riv)) if _riv in A50_IDX else None
# 竞品上线前后各 24 个月的均值 —— 图注里那句话的数字从这里算，不写死
A50_PRE = float(A50_W.loc[_riv - 24:_riv - 1].mean()) if A50_BRK else float('nan')
A50_POST = float(A50_W.loc[_riv:_riv + 23].mean()) if A50_BRK else float('nan')
A50_L24 = float(A50_W.iloc[-24:].mean())

# SGX 台湾指数期货：2020 年 MSCI 授权到期改挂 FTSE，是本页唯一一次**可观测的产品级替代**
TW_MSCI, TW_FTSE = sgx_adv('vol_msci_taiwan_futures_contracts'), sgx_adv('vol_ftse_taiwan_futures_contracts')
TW_IDX = pd.period_range('2019-01', '2022-12', freq='M')
TW_XL = [mlab(p) for p in TW_IDX]
TW_M_W, TW_F_W = TW_MSCI.reindex(TW_IDX), TW_FTSE.reindex(TW_IDX)
_tw_first_f = TW_FTSE.dropna()
TW_F_FIRST = _tw_first_f.index[0] if not _tw_first_f.empty else None
TW_BRK = int(list(TW_IDX).index(TW_F_FIRST)) if TW_F_FIRST in TW_IDX else None
# 线在哪几格断笔 —— **现算**（从前图注里写死「2021-01 那一格」）。只报序列内部的缺口：
# 两端的空白是「还没上线 / 已经归零」，那不是断笔，写进去会把读者引到相反的结论上。
_tw_ok = TW_M_W.dropna()
TW_GAPS = ([p for p in TW_IDX if _tw_ok.index[0] < p < _tw_ok.index[-1] and pd.isna(TW_M_W[p])]
           if len(_tw_ok) else [])
TW_GAP_TXT = (f'MSCI 那条线在 {"、".join(mlab(p) for p in TW_GAPS)} 缺值'
              f'（共 {len(TW_GAPS)} 格），线在那里断笔。'
              if TW_GAPS else 'MSCI 那条线在图窗内没有内部缺口，中间不断笔。')

# ────────────────────────── 5. HKEX 南向（互联互通）──────────────────────────
SB = RAW['hkex']['southbound_adt_hkdbn']
SB_RATIO = (SB / RAW['hkex']['adt_hkdbn'] * 100).reindex(IDX)
SB_HOLE = [p for p in IDX if not np.isfinite(float(SB_RATIO.get(p, np.nan)))]


def _runs(missing, idx):
    """把缺月压成**连续段**。旧写法只印 first – last + 总数，读者会把它读成一整段空白，
    而中间那些有值的月份在同一张图上就看得见 —— 图注当场被图证伪。
    ⚠️ 这里不许写「本轮缺 N 个月、分 M 段」之类的实测数：段与月数逐月在变，
    要看当轮是几段几个月，读页上 `SB_HOLE_TXT` 的输出，别在注释里抄一份。"""
    pos = {p: i for i, p in enumerate(idx)}
    out = []
    for p in missing:
        if out and pos[p] == pos[out[-1][-1]] + 1:
            out[-1].append(p)
        else:
            out.append([p])
    return out


SB_RUNS = _runs(SB_HOLE, list(IDX))
SB_HOLE_TXT = ('、'.join(f'{mlab(r[0])} – {mlab(r[-1])}（{len(r)} 个月）' if len(r) > 1
                        else f'{mlab(r[0])}（1 个月）' for r in SB_RUNS)
               + (f'，共 {len(SB_HOLE)} 个月，中间各段有值'
                  if len(SB_RUNS) > 1 else '')
               if SB_HOLE else '无缺口')
# 第一段若紧贴窗口左端，那不是「停发」而是「本页窗口早于这一列的起点」——
# 两件事在图上长得一样（都是左边没线），但归因完全不同，措辞按现算的判据分岔。
SB_LEAD_GAP = bool(SB_RUNS) and SB_RUNS[0][0] == IDX[0]
SB_HOLE_WORD = '官方停发／窗口早于本列起点' if SB_LEAD_GAP else '官方停发'

# ────────────────────────── 6. 季度序列（长历史）──────────────────────────
def quarterly(s, upto=LATEST):
    """月度日均 → 季度日均，**只保留三个月都齐的整季**（半季会被读成暴跌）。"""
    s = s.dropna()
    s = s[s.index <= upto]
    if s.empty:
        return s
    g = s.groupby(s.index.asfreq('Q'))
    return g.mean()[g.size() == 3]


QCASH = {k: quarterly(CASH[k]) for k in KEYS}
for k in KEYS:
    if QCASH[k].empty:
        skip(f'{DISP[k]} 没有任何一个整季，季度长历史图画不出来')
QBASE = BASE.asfreq('Q')
if any(QBASE not in QCASH[k].index for k in KEYS):
    skip(f'基期季 {QBASE} 不是四家共有的整季，季度指数化没有公共基准')
QFIRST = min(QCASH[k].index[0] for k in KEYS)
QLAST = min(QCASH[k].index[-1] for k in KEYS)
QIDX = pd.period_range(QFIRST, QLAST, freq='Q')
QXL = [qlab(q) for q in QIDX]
QYEARS = (len(QIDX) - 1) / 4.0

# 季度值用**等权月均**（三个月的日均直接平均），不做交易日加权。
# ⚠ 这里从前写的理由是「HKEX 没有交易日列，四家里只有三家能加权」—— 现读实测不成立
# （见上方 DAYCOL 那一段）。口径本身不动（Exhibit 5 / 15 在 CONTRACT.md §6.2 的保留
# 名单上，换加权方式是页面所有者的决定），撤掉的是那句理由。
# 代价照旧实测，而且现在覆盖**所有有交易日列的成员**：逐季比日加权与等权，最大差 QW_DEV%。
_qw = []
for k, dc in ((k_, DAYCOL[k_]) for k_ in DAYW_HAVE):
    s, dd = CASH[k].dropna(), RAW[k][dc]
    s = s[s.index <= LATEST]
    q = s.index.asfreq('Q')
    fr = pd.DataFrame({'v': s.values, 'd': dd.reindex(s.index).values}, index=q)
    g = fr.groupby(level=0)
    ew, cnt = g['v'].mean(), g.size()
    dw = g.apply(lambda x: (x['v'] * x['d']).sum() / x['d'].sum())
    ok = cnt == 3
    _qw.append(float(((dw[ok] / ew[ok] - 1) * 100).abs().max()))
QW_DEV = max(_qw)

QYOY = {k: (QCASH[k] / QCASH[k].shift(4) * 100 - 100) for k in KEYS}
QHEAT = QIDX[-HEAT_QTRS:]

# ────────────── 6b. 12 个月滚动同比：ex5 的口径，以及「为什么不用单月同比」的实证 ──────────────
# 单月同比的问题不是「噪音大一点」，是**方向都可能是反的**：一个基期的坑或一个交割日
# 就能把某一个月的读数推到与趋势相反的一侧。下面这些数字全部由代码算出，图注直接引用。
_MO_YY = {k: (CASH[k].pct_change(12) * 100) for k in KEYS}    # 旧口径：单月同比
_TTM_YY = {k: ttm_yoy(CASH[k]) for k in KEYS}                 # 新口径：12 个月滚动合计同比

# ⚠ 两个口径的可用月份不一样（滚动同比要多 12 个月历史），必须**对齐到同一批月份**再比，
# 否则算出来的标准差差异里混着样本差异，不能全部归给口径。
EVID = {}
for k in KEYS:
    _fr = pd.DataFrame({'m': _MO_YY[k], 't': _TTM_YY[k]}).reindex(IDX).dropna()
    EVID[k] = {
        'n': len(_fr), 'first': _fr.index[0], 'last': _fr.index[-1],
        'sd_m': float(_fr['m'].std()), 'sd_t': float(_fr['t'].std()),
        'jump_m': float(_fr['m'].diff().abs().max()),
        'jump_t': float(_fr['t'].diff().abs().max()),
        # 符号相反 = 两个口径对「在涨还是在跌」给出相反答案。用乘积判号而不是 np.sign
        # 相减：sign(0) = 0 会把「其中一个恰好为 0」误判成不同号。
        'flip': int((_fr['m'] * _fr['t'] < 0).sum()),
    }

# ex5 的三根柱：截至这三个月的 12 个月，正好是三个互不重叠的完整年
_y3 = [CUR - 24, CUR - 12, CUR]
TTM_WIN = {m: (m - 11, m) for m in _y3}          # 每根柱代表的 12 个月区间
TTM_FIRST = _y3[0] - 23                          # 全图最早触及的月份 = 最早那根柱的同比基期

# 图注里的「符号相反」实例：只在**三根柱所在的月份**里找，找不到才退而求其次。
# 写死「HKEX 的 Jun-24」是不行的 —— 下个月重跑，那个例子可能就不在窗口里了。
_FLIP = next(((k, m) for m in _y3 for k in KEYS
              if np.isfinite(float(_MO_YY[k].get(m, np.nan)))
              and np.isfinite(float(_TTM_YY[k].get(m, np.nan)))
              and float(_MO_YY[k][m]) * float(_TTM_YY[k][m]) < 0), None)
# 倍数最离谱的实例（同号但单月读数是趋势的几倍）：|t| 太小的不算，否则分母趋零会刷出
# 一个没有意义的「几百倍」。
_RATIO = max(((k, m, abs(float(_MO_YY[k][m]) / float(_TTM_YY[k][m])))
              for m in _y3 for k in KEYS
              if np.isfinite(float(_MO_YY[k].get(m, np.nan)))
              and np.isfinite(float(_TTM_YY[k].get(m, np.nan)))
              and abs(float(_TTM_YY[k][m])) >= 5.0
              and float(_MO_YY[k][m]) * float(_TTM_YY[k][m]) > 0),
             # ⚠ 要的是**最大**的倍数。写成 key=lambda t: -t[2] 会静默取到最小那个，
             # 于是图注上印出「单月读数是趋势的 0.0 倍」这种自我否定的句子（本轮真踩过）。
             key=lambda t: t[2], default=None)

# 等权（不乘交易日）的代价，按 12 个月窗口重算一遍 —— Exhibit 3 那个 QW_DEV 是季度窗口的，
# 换成 12 个月窗口后数字不同，图注引用哪个就得算哪个。成员名单同样现读 DAYCOL。
_tw = []
for k, dc in ((k_, DAYCOL[k_]) for k_ in DAYW_HAVE):
    _s = CASH[k][CASH[k].index <= LATEST]
    _d = RAW[k][dc].reindex(_s.index)
    _ew = _s.rolling(12).sum()
    _dw = (_s * _d).rolling(12).sum() / _d.rolling(12).sum() * 12
    _tw.append(float(((_dw.pct_change(12) - _ew.pct_change(12)) * 100).reindex(IDX).abs().max()))
TTM_QW_DEV = max(_tw)


# ────────────── 6c. 量价分解：成交额 ≡ 成交量 × 均价 ──────────────
# 恒等式是**定义式、零假设**：均价 ≡ 成交额 ÷ 成交量，所以「成交额 ≡ 量 × 均价」恒成立，
# 没有任何模型假设。能不能做完全取决于官方月报里**有没有量那一列**：
#   JPX  adt_cash_stocks_jpytn ÷ adv_cash_dom_shares_mn → 真·量价分解
#   SGX  sec_turnover_sgdmn    ÷ sec_turnover_mnshares  → 真·量价分解
#   HKEX 只有 adt_hkdbn，**一列量都没有**               → 做不了，Exhibit 15 该列留空
#   ASX  没有股数，只有 adt_cash_trades（笔数）与 avg_value_per_trade_aud
#        → 只能做「笔数 × 每笔均值」这**另一种**恒等式
#
# ⚠ 分子分母必须同口径，否则算出来的「均价」是个混合物（下面三处「实测」的数
#   一律由 DEC 下方那段代码当场算，不写死 —— 见那里的注释）：
#   · JPX 的头条列 adt_cash_total **含 ETF/REIT**（占比由 JPX_ETF_TXT 现算，逐月在变），
#     而股数列是 domestic 股票的股数。拿含 ETF 的金额除以不含 ETF 的股数，
#     ETF 占比一波动就会被读成「涨价」。所以这里改用 adt_cash_stocks_jpytn
#     （stocks + etfreit ≡ total 这道恒等式的残差由 JPX_ID_MAXERR 现算）。代价：它分解的
#     **不是头条口径**，两者的同比差多少由代码算出写进图注，不藏。
#   · ASX 的 avg_value_per_trade_aud 对应的是**总成交额**（含场外报告成交），不是头条的
#     on-market：两条路各算一遍（ASX_PT_TOT / ASX_PT_ONM），贴得紧的那条才是它的分母，
#     翻面就当场停机。所以 ASX 这一列分解的是总口径，同样写进图注。
DEC = {
    'hkex': {'why': 'HKEX 月度披露只有成交金额（adt_hkdbn），没有股数、也没有笔数'},
    'jpx': {'why': None, 'days': 'trading_days',
            'v': RAW['jpx']['adt_cash_stocks_jpytn'],
            'q': RAW['jpx']['adv_cash_dom_shares_mn'],
            'qname': '成交股数', 'scope': '现货股票，不含 ETF/REIT（头条列含）'},
    'sgx': {'why': None, 'days': 'sec_trading_days',
            # 除以交易日换成日均：本页所有滚动合计都按「日均值等权相加」来做，
            # SGX 的两列原始值是**当月总量**，不换算就成了唯一一家按交易日加权的。
            'v': RAW['sgx']['sec_turnover_sgdmn'] / RAW['sgx']['sec_trading_days'],
            'q': RAW['sgx']['sec_turnover_mnshares'] / RAW['sgx']['sec_trading_days'],
            'qname': '成交股数', 'scope': '证券市场全口径，与头条 SDAV 同源'},
    'asx': {'why': None, 'days': 'trading_days_cash', 'alt': True,
            'v': RAW['asx']['adt_cash_total_audbn'],
            'q': RAW['asx']['adt_cash_trades'],
            'qname': '成交笔数', 'scope': '现货总成交额，含场外报告成交（头条列是 on-market）'},
}


# ── 上面那两条「换列」的举证：全部**现算**，不写死 ──────────────────────────
# 从前这三个数是写在注释与图注里的字面量（ETF/REIT 占 4.2%–16.4%、每笔均值差
# 0.49 与 967 澳元）。它们都随数据走：本轮重算，总口径那一项已经不是 0.49 了。
# 写死的举证比没有举证更糟 —— 它看上去可核对，实际上核不动。
# JPX 头条列里 ETF/REIT 占多少 —— 这就是「不能拿含 ETF 的金额除以不含 ETF 的股数」的举证。
JPX_ETF_TXT = _rng(rawcol('jpx', 'adt_cash_etfreit_jpytn')
                   / rawcol('jpx', 'adt_cash_total_jpytn') * 100, '%')
# stocks + etfreit ≡ total 这道恒等式的实测残差（换列换得对不对，靠它兜底）。
_jpx_id = _fin(rawcol('jpx', 'adt_cash_stocks_jpytn')
               + rawcol('jpx', 'adt_cash_etfreit_jpytn')
               - rawcol('jpx', 'adt_cash_total_jpytn')).abs()
JPX_ID_MAXERR = float(_jpx_id.max()) if len(_jpx_id) else float('nan')
# ASX 官方那列每笔均值到底对着哪一个成交额口径：两条路各算一遍，差小的那条才是它的分母。
_asx_trades = rawcol('asx', 'adt_cash_trades')
_asx_off = rawcol('asx', 'avg_value_per_trade_aud')
_asx_pt = {n: _fin((rawcol('asx', c) * 1e9 / _asx_trades - _asx_off).abs())
           for n, c in (('total', 'adt_cash_total_audbn'),
                        ('onmkt', 'adt_cash_onmarket_audbn'))}
ASX_PT_TOT = float(_asx_pt['total'].max()) if len(_asx_pt['total']) else float('nan')
ASX_PT_ONM = float(_asx_pt['onmkt'].max()) if len(_asx_pt['onmkt']) else float('nan')
# 护栏：DEC['asx'] 选的是**总**成交额列，理由就是官方每笔均值贴着它。这个判定一旦翻面，
# 那句理由与那一列的选择同时失效 —— 当场停机，不要带着一句失效的举证出页。
if np.isfinite(ASX_PT_TOT) and np.isfinite(ASX_PT_ONM) and ASX_PT_TOT >= ASX_PT_ONM:
    raise SystemExit(
        'ASX 每笔均值的分母判定翻面了：官方 avg_value_per_trade 不再更贴总成交额'
        f'（总口径最大差 {ASX_PT_TOT:,.2f} 澳元 ≥ on-market 的 {ASX_PT_ONM:,.2f} 澳元）。'
        'DEC["asx"] 选的是总成交额列，先核对口径再发。')


# 对数权重分解的权重分母下限。|ln(V1/V0)| 趋零时，两段贡献相对净额会放大到读不出意思
# （「量 +300pp / 价 −298pp / 净 +2pp」这种柱，读者只会读错段高），此时**整根柱留空**，
# 不印一个被放大的数。阈值 0.01 ≈ 12 个月增长 ±1%：再往下两段绝对值就会超过净额 30 倍。
# 本轮各家实测的 |ln(V1/V0)| 由代码算出印进图注，够不够得着阈值不靠记忆。
LOGW_EPS = 0.01
DEC_BLANK = {}          # key → 留空原因（只由本币那一路记录，图注点名用）


def _decomp(key, end, usd=False):
    """截至 end 的 12 个月 vs 前 12 个月，把成交额增长拆成量与价。

    ⚠ 图上画的是**对数权重分解**，全仓统一口径（与 build/specs/sgx.py 的
    `'method': 'log'` 一致）。做法：ln(V1/V0) = ln(Q1/Q0) + ln(P1/P0) 天然可加、
    零残差，再按 w = g_V / ln(V1/V0) 把两块**重标定回百分点**，于是相加逐列等于总增长。

    为什么不用算术分解（g_V = g_Q + g_P + g_Q·g_P，把交叉项并进价那一块）：
    交叉项在量与价**反向**的年份会大到吃掉整个读数（另一页曾实测交叉项占总增长中位
    10.5%、最大 362.8% —— 量 +35.5% / 价 −24.4% 几乎完全对冲、净增长只有 +2.4% 的那一年；
    ⚠ 这一组是**别家页面某一轮的存档读数**，本页不重算它，引用时别读成当期实测）。
    并进价里就等于把「价的贡献」污染成一个读不出意思的数。

    ⚠ **本窗口有没有反向的列，是每轮由数据当场判的**（`_same_dir` / `_opp_dir`），
    两法差多少由 `_ar_dev` 当场算，二者都逐轮写进 Exhibit 15 的图注 —— 这里不写死
    「几家同向」「只差 X pp」，那种话换一个月就可能翻面，而它一旦翻面没有任何东西会报警。
    而且**口径要按最坏情形定，不能按当期数据碰巧好看来定**：就算某一轮四家全部同向，
    算术分解也照样不用。算术分解仍然照算，差异写进图注。

    usd=True 走「× SCALE × 基期汇率」这条路：定基汇率是常数，增长率本不该变，
    这个分支存在的唯一目的就是把「本不该变」真的跑一遍验出来（见下方硬护栏 ②）。
    """
    d = DEC[key]
    if d['why']:
        return None
    w1 = pd.period_range(end - 11, end, freq='M')
    w0 = pd.period_range(end - 23, end - 12, freq='M')
    v, q = d['v'], d['q']
    if usd:
        v = v * SCALE[key] * FX_BASE[key]
    # ⚠ Series.sum() 默认跳过 NaN ⇒ 缺一个月会**静默**变成 11 个月合计，
    # 与另一侧的 12 个月直接比，凭空造出一个增长率。必须先查满不满。
    for w in (w1, w0):
        if not (v.reindex(w).notna().all() and q.reindex(w).notna().all()):
            if not usd:
                DEC_BLANK[key] = f'{mlab(w[0])}–{mlab(w[-1])} 有缺月，12 个月合计凑不满'
            return None
    V1, V0 = float(v.reindex(w1).sum()), float(v.reindex(w0).sum())
    Q1, Q0 = float(q.reindex(w1).sum()), float(q.reindex(w0).sum())
    if not all(np.isfinite(x) and x > 0 for x in (V1, V0, Q1, Q0)):
        if not usd:
            DEC_BLANK[key] = '窗口内合计出现非正或非有限值'
        return None
    gV, gQ = (V1 / V0 - 1) * 100, (Q1 / Q0 - 1) * 100
    P1, P0 = V1 / Q1, V0 / Q0
    gP = (P1 / P0 - 1) * 100
    cross = gQ * gP / 100.0
    # ── 对数权重分解（上图的那一种）──
    lV_raw = float(np.log(V1 / V0))
    if abs(lV_raw) < LOGW_EPS:
        # 分母趋零 ⇒ 两段贡献相对净额被放大，段高不再可读。留空，不印放大后的数。
        if not usd:
            DEC_BLANK[key] = (f'|ln(V1/V0)| = {abs(lV_raw):.4f} 低于阈值 {LOGW_EPS}，'
                              f'对数权重的分母趋零、两段贡献会被放大到读不出意思')
        return None
    lV = lV_raw * 100
    # lQ 与 lP 各自独立算，不用 lP = lV − lQ —— 后者让「可加」变成恒真，
    # 下面那道 lQ + lP == lV 的护栏就测不出任何东西了。
    lQ, lP = float(np.log(Q1 / Q0) * 100), float(np.log(P1 / P0) * 100)
    w = gV / lV          # 重标定：把对数点换回百分点，使两块相加逐列等于总增长
    return {'gV': gV, 'gQ': gQ, 'gP': gP, 'cross': cross,
            'lV': lV, 'lQ': lQ, 'lP': lP, 'lV_raw': lV_raw, 'w': w,
            'vol': lQ * w, 'prc': lP * w,           # ← 上图的两段：对数权重重标定
            'vol_ar': gQ, 'prc_ar': gP + cross,     # ← 只做对照：算术，交叉项并入价
            'P1': P1, 'P0': P0, 'w1': w1, 'w0': w0}


# 分解窗口 = ex5 最新那根柱的窗口，两张图必须落在同一段时间，否则读者会拿
# 「最近 12 个月同比 +X%」去解释一张其实画的是别的窗口的分解图。
DEC_END = CUR
DECOMP = {k: _decomp(k, DEC_END) for k in KEYS}
DECOMP_USD = {k: _decomp(k, DEC_END, usd=True) for k in KEYS}
DEC_OK = [k for k in KEYS if DECOMP[k] is not None]
DEC_NO = [k for k in KEYS if DECOMP[k] is None]
if not DEC_OK:
    skip('四家没有一家能做量价分解（都缺量的列），Exhibit 15 无内容')

# ── 硬护栏 ①：两块相加必须逐列等于总增长 ──
# 堆叠柱的全部意义就是这个恒等式。对不上而照画，等于在页面上摆一个假的加总关系，
# 而引擎不会报错（CHART_KINDS §3.15：「net 与 Σstacks 对不上时引擎不会告诉你」）。
# 三样都查：① 上图那两段（对数权重重标定）② 纯对数的可加性 ③ 算术那一路（只进图注，
# 但它进了图注就同样不能错）。任何一条对不上都拒绝出页。
_bad = []
for k in DEC_OK:
    r = DECOMP[k]
    for lab, e in (('对数权重两段', abs(r['vol'] + r['prc'] - r['gV'])),
                   ('纯对数可加性', abs(r['lQ'] + r['lP'] - r['lV'])),
                   ('算术（交叉项并入价）', abs(r['vol_ar'] + r['prc_ar'] - r['gV']))):
        if e > 1e-9:
            _bad.append(f'{DISP[k]} {lab}：残差 {e:.3e}（量 {r["vol"]:.9f} + 价 {r["prc"]:.9f} '
                        f'vs 总 {r["gV"]:.9f}）')
if _bad:
    raise SystemExit('量价分解恒等式自检失败：\n  · ' + '\n  · '.join(_bad))
DEC_ID_MAXERR = max(max(abs(DECOMP[k]['vol'] + DECOMP[k]['prc'] - DECOMP[k]['gV']),
                        abs(DECOMP[k]['lQ'] + DECOMP[k]['lP'] - DECOMP[k]['lV']),
                        abs(DECOMP[k]['vol_ar'] + DECOMP[k]['prc_ar'] - DECOMP[k]['gV']))
                    for k in DEC_OK)
DEC_LNV_MIN = min(abs(DECOMP[k]['lV_raw']) for k in DEC_OK)   # 离权重下限还有多远

# ── 硬护栏 ②：汇率对增长率没有影响 ──
# 定基汇率是常数 ⇒ 本币口径与定基美元口径的分解必须逐位相同。这件事本页从第一天起就
# 写在图注里，但「写着」和「验过」是两回事：这里真的两条路各算一遍再比。
_fxbad = []
for k in DEC_OK:
    a, b = DECOMP[k], DECOMP_USD[k]
    if b is None:
        _fxbad.append(f'{DISP[k]}：定基美元口径这一路算不出来')
        continue
    for f in ('gV', 'gQ', 'gP', 'vol', 'prc'):
        if abs(a[f] - b[f]) > 1e-9:
            _fxbad.append(f'{DISP[k]}.{f}：本币 {a[f]:.12f} vs 定基美元 {b[f]:.12f}')
if _fxbad:
    raise SystemExit('汇率不变性自检失败（定基汇率是常数，增长率本不该变）：\n  · '
                     + '\n  · '.join(_fxbad))
DEC_FX_MAXDEV = max(abs(DECOMP[k][f] - DECOMP_USD[k][f])
                    for k in DEC_OK for f in ('gV', 'gQ', 'gP', 'vol', 'prc'))

# 等权（不乘交易日）在这张分解图上的代价 —— 能分解的这几家都有交易日列，所以这一项
# 可以真的算出来，不用估。仍然选等权，理由只剩一条能站住的：Exhibit 3 / 5 已经是等权，
# 这里换了就成了同一页三套口径，而 Exhibit 5 / 15 在 CONTRACT.md §6.2 的保留名单上。
# ⚠ 「HKEX 没有交易日列所以做不到四家一致」那条旧理由已撤 —— 现读实测它不成立（见 DAYCOL）。
#
# ⚠ 这一项还有跨页含义：单公司页（build/specs/sgx.py）是把**当月总量直接相加**，
# 即交易日加权。所以即便两页都改用对数权重分解，SGX 那一列的读数仍不会逐位相同 ——
# 差的不是方法，是聚合权重。下面把日加权那一路的对数权重分解也算出来，
# 图注里直接给对账数，读者拿两页对照时不用猜谁算错了。
DEC_DW = {}
for k in DEC_OK:
    _d, _days = DEC[k], RAW[k][DEC[k]['days']]
    _w1, _w0 = DECOMP[k]['w1'], DECOMP[k]['w0']

    # ⚠ 必须是**当月总量直接相加**（日均 × 当月交易日，再逐月求和），
    # 不能写成「日加权均值 × 12」—— 两个窗口的交易日总数并不相等（本轮 W1/W0 就差好几天），
    # 归一化之后算出来的比值既不是本页口径也不是单公司页口径，是第三个数。
    # 本轮实测：写成归一化版本时 SGX 量贡献 +31.98pp，而单公司页的实际口径是 +32.52pp。
    def _agg(s, w, _dd=_days):
        return float((s * _dd).reindex(w).sum())
    _V1, _V0 = _agg(_d['v'], _w1), _agg(_d['v'], _w0)
    _Q1, _Q0 = _agg(_d['q'], _w1), _agg(_d['q'], _w0)
    _gV = (_V1 / _V0 - 1) * 100
    _lV, _lQ = np.log(_V1 / _V0) * 100, np.log(_Q1 / _Q0) * 100
    _w = _gV / _lV
    DEC_DW[k] = {'gV': _gV, 'gQ': (_Q1 / _Q0 - 1) * 100,
                 'vol': _lQ * _w, 'prc': (_lV - _lQ) * _w}
DEC_DW_DEV = max(max(abs(DEC_DW[k]['gV'] - DECOMP[k]['gV']),
                     abs(DEC_DW[k]['gQ'] - DECOMP[k]['gQ']),
                     abs(DEC_DW[k]['vol'] - DECOMP[k]['vol']),
                     abs(DEC_DW[k]['prc'] - DECOMP[k]['prc'])) for k in DEC_OK)

# ── 量本身（Exhibit 16 / 17）：只有披露股数的两家 ──
# ASX 的「量」是笔数不是股数，不进这两张图：同一批股票被切成更多笔，笔数就上去了，
# 与股数不是一回事 —— 这正是本页 Exhibit 9 对衍生品张数讲过的同一件事。
QTY_KEYS = [k for k in DEC_OK if not DEC[k].get('alt')]
QTY = {k: DEC[k]['q'] for k in QTY_KEYS}
for k in QTY_KEYS:
    if not np.isfinite(float(QTY[k].get(BASE, np.nan))):
        skip(f'{DISP[k]} 的成交股数在基期 {mlab(BASE)} 无值，Exhibit 16 指数化做不了')
# 均价只为把「一股在两地根本不是一回事」量出来，不进任何增长结论。
# 单位换算：SCALE[k] × 1e9 就是该家金额列那一个「单位」值多少本币（¥tn → 1e12，S$mn → 1e6，
# 因为 SCALE 的定义就是「单位 ÷ 1e9 后再乘汇率得到 US$bn」），股数列一律是百万股。
QTY_PX_LOC = {k: DECOMP[k]['P1'] * SCALE[k] * 1e9 / 1e6 for k in QTY_KEYS}
QTY_PX_USD = {k: QTY_PX_LOC[k] * FX_BASE[k] for k in QTY_KEYS}


# ────────────── 6d. Exhibit 17 的口径：单月同比（当月 ÷ 去年同月 − 1）──────────────
# 换口径的**理由是一条可核对的事实**：页面所有者要求全站的同比折线统一成单月口径
# （原话：「我就需要直接的月度数据 yoy 同比折线图，不要给我搞 12 月滚动合计同比」，
# CONTRACT.md §6 抬头逐字引了它）。
# **不是**「单月看着更灵敏 / 更及时」—— 那种说法 CONTRACT.md §6.1 第 3 条明令禁止。
# Exhibit 5 的三根柱**不跟着改**：它是 §6.2 点名保留滚动口径的两处例外之一
# （另一处是 exchanges12 Ex4/7/8），命题是「一整年 vs 前一整年」、三段互不重叠、
# 横轴不是月。于是本页成了全仓唯一一页两种口径并存的页 ⇒ §6.2 要求的逐处点名写在
# 页尾与本图图注（图号由 CAL_MOM_EX / CAL_TTM_EX 现读 payload 给出，不手写）。
#
# 代价不藏，也不引别页的例子：下面拿**这两条股数序列自己**实测。文案直接用
# yoy.describe(yoy.caliber_diff(...))（§6.1 第 3 条指定的生成方式，全仓共用一份措辞），
# 它印的正是要报的三样：逐月标准差、相邻月最大跳变（带月份）、符号相反的月份数。
QYOY_MOM = {k: YOY.mom_yoy(QTY[k], YOY.FLOW).reindex(IDX) for k in QTY_KEYS}
# ⚠ 把索引换成本页的月份标签（Feb-20 而不是 2020-02）再送进诊断：describe() 会把
#   最大跳变的两个月份**原样印进图注**，索引长什么样图注就长什么样。同一页上两种
#   月份写法会让读者以为在说两批月份。换标签不动数值，诊断结果逐位不变。
# win 给的是**图上真正画出来的那一段**（Exhibit 17 的 x 轴就是 IDX）——
# 全历史算出来的「符号相反月数」读者在图上根本核不了。
_QLAB_WIN = [mlab(p) for p in IDX]


def _relabel(s):
    out = s.copy()
    out.index = [mlab(p) for p in s.index]
    return out


QDIFF = {k: YOY.caliber_diff(_relabel(QTY[k]), YOY.FLOW, win=_QLAB_WIN) for k in QTY_KEYS}
# 近零基数会让同比读的是分母不是量（CONTRACT §6.1 第 5 条），而单月口径下这一条比
# 从前更要紧 —— 滚动合计原本还能压一压，现在没有那层缓冲。两条股数序列都不该触发，
# 但触发了就得知道：静悄悄画一条读的是分母的线，比不画更糟。
QDIFF_NZ = [k for k in QTY_KEYS if QDIFF[k]['near_zero']['flag']]


def _mom_decomp(key, m):
    """**单月**量价分解：把当月对去年同月的成交额增长拆成量与价。

    与 `_decomp()` 那个 12 个月窗口的分解是**两个不同的问题**，不是同一个数的两种精度：
    这里问「这一个月与去年同一个月相比，多出来的成交额里有多少是股数、多少是均价」；
    那里问「这一整年与前一整年相比」。两边的读数不可互换、也不该相减。

    恒等式仍然是定义式：均价 ≡ 成交额 ÷ 股数 ⇒ (1+g量)(1+g价) = (1+g额)，逐位可验，
    下面 MOM_DEC 那道护栏就验它。三条同比全部走 `yoy.mom_yoy`（本仓唯一实现）。
    """
    d = DEC[key]
    v, q = d['v'], d['q']
    # 均价按月算完再取同比。SGX 的 v / q 都已经除过同一列交易日，商里直接约掉，
    # 所以「日均口径的均价」与「当月总量口径的均价」逐位相同。
    p = v / q
    g = {n: float(YOY.mom_yoy(s, YOY.FLOW).get(m, np.nan))
         for n, s in (('gV', v), ('gQ', q), ('gP', p))}
    if not all(np.isfinite(x) for x in g.values()):
        return None
    g['cross'] = g['gQ'] * g['gP'] / 100.0
    g['month'] = m
    return g


MOM_DEC = {k: _mom_decomp(k, CUR) for k in QTY_KEYS}
MOM_DEC_OK = [k for k in QTY_KEYS if MOM_DEC[k] is not None]
# 护栏：乘法恒等式对不上就别印那句「两者的商就是均价」。图注里那句话的全部依据就是它。
_mbad = [f'{DISP[k]}：残差 {abs((1 + MOM_DEC[k]["gQ"] / 100) * (1 + MOM_DEC[k]["gP"] / 100) - (1 + MOM_DEC[k]["gV"] / 100)):.3e}'
         for k in MOM_DEC_OK
         if abs((1 + MOM_DEC[k]['gQ'] / 100) * (1 + MOM_DEC[k]['gP'] / 100)
                - (1 + MOM_DEC[k]['gV'] / 100)) > 1e-9]
if _mbad:
    raise SystemExit('单月量价分解恒等式自检失败（(1+g量)(1+g价) 应当等于 1+g额）：\n  · '
                     + '\n  · '.join(_mbad))
MOM_DEC_MAXERR = max((abs((1 + MOM_DEC[k]['gQ'] / 100) * (1 + MOM_DEC[k]['gP'] / 100)
                          - (1 + MOM_DEC[k]['gV'] / 100)) for k in MOM_DEC_OK),
                     default=float('nan'))


# ────────────────────────────── 7. Exhibit 1：汇总表 ──────────────────────────────
# (kind, 标签, 序列, 小数位, 模式)
#   num    水平值，m/m 与 y/y 用百分比变化
#   share  比率（已是 %），差异用 pp/bp
#   growth 同比读数（已是 %，带符号），差异用 pp
SUM_ROWS = [
    ('group', '现货成交额 — 定基 2019-01 汇率折美元（US$bn/日）', None, None, None),
] + [
    # ASX 那一行的名字带上 on-market：见核对表那一列上方的说明（/asx/ 单页同名列是含场外报告的总额）。
    ('row', f'{DISP[k]} 现货 ADT' + ('（on-market）' if k == 'asx' else ''),
     clip(CASH[k]), 3 if k == 'sgx' else 2, 'num') for k in KEYS
] + [
    ('group', '现货成交额同比 —— <b>单月</b>同比（%，定基汇率口径 = 本币口径；'
              '平滑口径见 Exhibit 5）', None, None, None),
] + [
    ('row', f'{DISP[k]} 现货 ADT' + ('（on-market）' if k == 'asx' else '') + ' y/y（单月）',
     yoy(CASH[k]), 1, 'growth') for k in KEYS
] + [
    ('group', '衍生品 ADV — 各家原始张数（张/日，<b>水平值不可跨所比</b>）', None, None, None),
] + [
    ('row', f'{DISP[k]} 衍生品 ADV', clip(DERIV[k]), 0, 'num') for k in KEYS
] + [
    ('row', 'JPX 衍生品 ADV（大合约当量）', clip(JPX_LGEQ), 0, 'num'),
    ('group', '产品级头对头：日经 225 期货（张/日）', None, None, None),
    ('row', 'SGX 日经 225 期货 ADV', clip(NK_SG), 0, 'num'),
    ('row', '大阪（JPX）日经 225 期货 ADV，大合约当量', clip(NK_JP), 0, 'num'),
    # 「未做规格归一」这个旧写法把两侧说成对称的，其实不是：JPX 那一侧**已经**按大合约当量
    # 归一（乘数已核实入库），SGX 那一侧是原始张数（规格没取到）。一边归一一边没归一，
    # 这个百分比连纯张数口径都算不上 —— 标签必须把不对称写出来，否则读者会当它是可比的。
    ('row', 'SGX 占两所之和（%，<b>SGX 原始张数 ÷ JPX 大合约当量，两侧未同口径</b>）',
     clip(NK_SHARE), 1, 'share'),
    ('group', '其他产品级读数', None, None, None),
    ('row', 'SGX 富时中国 A50 期货 ADV（张/日）', clip(A50_SG), 0, 'num'),
    ('row', 'HKEX 南向 ADT ÷ 现货总 ADT（%，<b>口径不对齐，见注</b>）', SB_RATIO, 1, 'share'),
]


def ser_of(s):
    """pandas Series → pctile.py 吃的「按月升序、缺失为 None」的 float 列表。

    NaN 不能直接喂：pctile 里 `v is not None` 会把 NaN 当有效样本收进 hist，
    而 NaN 的比较恒为 False，分位会被悄悄压低。
    """
    return [None if v is None or not np.isfinite(float(v)) else float(v) for v in s.values]


def lvl(v, dec, mode):
    if v is None or not np.isfinite(v):
        return '—'
    if mode == 'growth':
        return f'{_z(v, dec):+,.{dec}f}%'
    if mode == 'share':
        return f'{v:,.{dec}f}%'
    return f'{v:,.{dec}f}'


def cls_of(v):
    if v is None or not np.isfinite(v):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


def summary():
    rows, blank_why = [], []
    for kind, label, s, dec, mode in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        c = float(s.get(CUR, np.nan))
        p1 = float(s.get(PRV, np.nan))
        p12 = float(s.get(YAG, np.nan))
        if mode == 'num':
            mm = (c / p1 - 1) * 100 if np.isfinite(c) and np.isfinite(p1) and p1 else np.nan
            yy = (c / p12 - 1) * 100 if np.isfinite(c) and np.isfinite(p12) and p12 else np.nan
            dm, dy = pct(mm), pct(yy)
        else:
            mm = c - p1 if np.isfinite(c) and np.isfinite(p1) else np.nan
            yy = c - p12 if np.isfinite(c) and np.isfinite(p12) else np.nan
            dm, dy = pp(mm), pp(yy)
        cells = [{'v': lvl(c, dec, mode)}, {'v': lvl(p1, dec, mode)}, {'v': lvl(p12, dec, mode)},
                 {'v': dm, 'cls': cls_of(mm)}, {'v': dy, 'cls': cls_of(yy)}]
        ser = ser_of(s)
        txt_, cls_ = pctile.cell(ser)
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label, pctile.why_blank(ser)))
        rows.append({'label': label, 'cells': cells})
    blank_txt = ('本轮留空：' + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    return {
        'title': f'亚太四家 — {mlab(CUR)}（共同最新月）',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('<b>本表没有任何一行是「份额」。</b>四家是法域隔离的市场，把它们的量相加当分母'
                 '得到的比值没有外部指涉（加减一家所有人的数字就变），本页一律不算 —— '
                 '唯一出现的两个百分比是<b>同一标的双挂牌的两所之间</b>（日经 225）'
                 '与<b>同一家内部的构成</b>（HKEX 南向），都不是跨市场的占比。<br>'
                 '现货四行已按 <b>2019-01 月均汇率</b>折成美元（此后汇率是常数，'
                 '所以这四行的同比与各自本币口径的同比完全相同）；'
                 '⚠ 源列是成交<b>金额</b>，只剔掉了汇率，<b>没剔掉标的涨跌</b>。<br>'
                 '衍生品四行是各家自己的张数，单张大小由各所的产品设计决定，'
                 '<b>行与行之间不能比大小</b>（JPX 那两行的差距就是同一个市场的两种数法）。<br>'
                 '⚠ 同比那四行是<b>单月</b>同比（本月 vs 去年同月），它是这张表的性质决定的'
                 '（表的三列就是本月 / 上月 / 去年同月），也是全站现在的统一口径；'
                 '<b>页顶数据条打头那一串现货 y/y 与这四行是同一个数</b>（构建期逐位对账，'
                 '对不上就停机）。同一条数据条后半段还印了一串标着'
                 '<b>「Exhibit 5 的年度口径」</b>的读数，那是 12 个月滚动合计、'
                 '回答的是「一整年比前一整年」—— <b>与这四行不是同一个问题，不要比高低</b>。<br>'
                 '3Y %ile = 该读数在最近 36 个月里高于多少百分比的观测，判据与留空规则'
                 '由全站唯一实现 <code>build/pctile.py</code> 给出。' + blank_txt),
    }


# ────────────────────────────── 8. Exhibit 2..14 ──────────────────────────────
ex = []


def ttm_ex_nums():
    """本页画「12 个月滚动合计的同比」那几张图的编号 —— **现读已经建好的 exhibit**。

    手写图号在插图 / 换口径之后就是一句指着别人说话的假话。调用时机决定它看得到
    几张图：Exhibit 15 的图注在自己被 append 之前调一次（那时 Exhibit 5 已经在
    `ex` 里），页尾口径说明在全部图建完之后再调一次，两处共用这一个判据。
    """
    return [e['n'] for e in ex
            if '12 个月滚动合计' in (e.get('title') or '')
            or '12 个月滚动合计' in (e.get('ylab') or '')]


def ttm_ex_txt(where):
    nums = ttm_ex_nums()
    if not nums:
        raise SystemExit(f'口径点名（{where}）：本页找不到任何一张 12 个月滚动合计同比的图，'
                         '但图注要按「两种口径并存」来写 —— 先核对口径再发。')
    return '、'.join(str(n) for n in nums)


_idx_now = {k: float(idx100(CASH[k])[CUR]) for k in KEYS}
_rank_idx = sorted(_idx_now.items(), key=lambda kv: -kv[1])

ex.append({
    'n': 2, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0', 'zero_base': True,
    'title': f'现货成交额，定基汇率折美元后指数化（{mlab(BASE)} = 100）',
    'ylab': f'指数，{mlab(BASE)} = 100',
    'series': [{'name': DISP[k], 'color': COLOR[k],
                'values': L(idx100(CASH[k]).reindex(IDX).values)} for k in KEYS],
    'src_extra': (f'Each exchange rebased to 100 at {mlab(BASE)}; FX locked at the '
                  f'{mlab(BASE)} monthly average, so growth here equals growth in local currency'),
    'note': ('四条线比的是<b>各自相对自己基期的增长</b>，与谁的体量大无关 —— '
             '体量在汇总表里，那里的水平值也只是量级参考。'
             f'汇率锁在 {mlab(BASE)}：折算常数不随月份变，'
             '所以这张图上<b>没有一个百分点来自汇率</b>（汇率的贡献单独画在 Exhibit 4 与 6）。'
             '⚠ 源列是成交金额 = 股数 × 当期价格，官方不披露成交股数，'
             '<b>标的涨跌剔不掉</b>：一轮牛市会同时抬高成交额与这条线。'),
})

ex.append({
    'n': 3, 'kind': 'lines', 'full': True, 'height': LINE_H,
    'xlabels': QXL, 'fmt': 'f0', 'yfmt': 'f0', 'xstep': 4, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0', 'zero_base': True,
    'title': (f'季度口径的长历史：现货成交额指数化（{qlab(QBASE)} = 100，'
              f'{qlab(QIDX[0])} – {qlab(QIDX[-1])}）'),
    'ylab': f'指数，{qlab(QBASE)} = 100',
    # ⚠ 必须先指数化再 reindex —— 直接把 QCASH（US$bn/日 的水平值）喂进来，
    # 轴标题写着「指数 = 100」而画的是水平值，四条线会按体量排开而不是按增速，
    # 且不报任何错。本轮浏览器实测末点标签印出 114/37/6/2（正是四家的美元水平值）
    # 才发现，故留此注。
    'series': [{'name': DISP[k], 'color': COLOR[k],
                'values': L(idx100(QCASH[k], QBASE).reindex(QIDX).values)} for k in KEYS],
    'src_extra': (f'Quarterly averages of the monthly daily-average turnover; only quarters with '
                  f'all three months present are plotted. Rebased to 100 at {qlab(QBASE)}'),
    'note': (f'<b>月度太吵，季度才看得出结构性趋势</b>，所以这张图与 Exhibit 2 并存而不是替代它。'
             f'跨度 <b>{qlab(QIDX[0])} – {qlab(QIDX[-1])}（{len(QIDX)} 个季度，约 {QYEARS:.1f} 年）</b>，'
             f'是四家里最长的那条能画多长就画多长（'
             # 起点逐家从数据读，不写死 —— 写死的话哪天某家补了历史，图注就成了假话
             + '；'.join(f'{DISP[k]} 自 {qlab(QCASH[k].index[0])} 起'
                         for k in sorted(KEYS, key=lambda x: QCASH[x].index[0]))
             + '），各条线在自己的起点之前留空，不外推。'
             f'基期统一在 {qlab(QBASE)}（四家都有整季的最早共同季），'
             f'所以起点早于基期的两家在图左侧可以低于也可以高于 100。<br>'
             f'季度值 = 三个月日均的<b>等权平均</b>，没做交易日加权。'
             f'代价实测很小 —— 对有交易日列的成员（{DAYW_TXT}）逐季比过，'
             f'日加权与等权的最大偏差 <b>{QW_DEV:.2f}%</b>。'
             f'⚠ 只保留三个月都齐的整季，半季会被读成一次暴跌。'),
})

_cur_idx = {k: float(idx100(CASH_CUR[k])[CUR]) for k in KEYS}
ex.append({
    'n': 4, 'kind': 'grouped_bars', 'xlabels': [DISP[k] for k in KEYS],
    'fmt': 'f0', 'yfmt': 'f0', 'xrot': 0, 'bar_labels': True,
    'title': f'汇率口径对照：同一批数据的当期指数（{mlab(BASE)} = 100）',
    'ylab': f'指数，{mlab(BASE)} = 100',
    'groups': [
        {'name': f'定基汇率（锁 {mlab(BASE)}，本页主口径）', 'color': 'NAVY',
         'values': [round(_idx_now[k], 3) for k in KEYS]},
        {'name': '当期汇率（对照，不进任何增长结论）', 'color': 'GRAY',
         'values': [round(_cur_idx[k], 3) for k in KEYS]},
    ],
    'note': ('两根柱之间的落差<b>全部来自汇率</b>，与成交活跃度无关。'
             f'{mlab(BASE)} 以来日元对美元累计 '
             f'{pct(float(FX[FXCOL["jpx"]][CUR]) / FX_BASE["jpx"] * 100 - 100)}，'
             '所以 JPX 的当期汇率柱比定基柱矮一大截 —— '
             '<b>如果本页用当期汇率，日本市场七年半的增长会被汇率削掉一大块，'
             '而那一块并不是成交量的变化。</b>本页所有增长结论一律用左柱那一口径。'
             '这道缺口是怎么一个月一个月累出来的，画在 <b>Exhibit 6</b>。'),
})

# ⚠ 这三根柱是**12 个月滚动合计的同比**，不是单月同比。换口径的理由不是「平滑一点更好看」，
# 而是单月同比在这四家身上**连方向都会反**（下面 _FLIP 那个实例由代码找出来）。
# 三段窗口正好互不重叠、各为一个完整年，所以并排读它们等于读三个连续年度的增速。
_ev_txt = '；'.join(
    f'{DISP[k]} {EVID[k]["sd_m"]:.1f} → {EVID[k]["sd_t"]:.1f}' for k in KEYS)
_jump_txt = '；'.join(
    f'{DISP[k]} {EVID[k]["jump_m"]:.1f}pp → {EVID[k]["jump_t"]:.1f}pp' for k in KEYS)
_win_txt = '；'.join(f'{mlab(m)} 柱 = {mlab(a)}–{mlab(b)}' for m, (a, b) in TTM_WIN.items())
if _FLIP:
    _fk, _fm = _FLIP
    _flip_txt = (f'<b>{DISP[_fk]} 的 {mlab(_fm)} 就是现成的反例</b>：单月同比 '
                 f'{pct(float(_MO_YY[_fk][_fm]))}，而同一时点的 12 个月滚动同比是 '
                 f'{pct(float(_TTM_YY[_fk][_fm]))} —— <b>一个说在涨，一个说在跌，'
                 f'差 {abs(float(_MO_YY[_fk][_fm]) - float(_TTM_YY[_fk][_fm])):.1f}pp 且符号相反</b>。'
                 f'若按单月读，会得出「{DISP[_fk]} 那年在增长」的结论，而它当时'
                 f'整整一年的成交额比前一年少了 {abs(float(_TTM_YY[_fk][_fm])):.1f}%。')
else:
    _flip_txt = ('本轮三根柱所在的月份里，两个口径恰好没有出现符号相反的实例 —— '
                 f'但整个共同窗口内符号相反的月份仍有 '
                 + '、'.join(f'{DISP[k]} {EVID[k]["flip"]} 个月' for k in KEYS) + '。')
if _RATIO:
    _rk, _rm, _rv = _RATIO
    _ratio_txt = (f'即便符号一致，倍数也常常离谱：{DISP[_rk]} 的 {mlab(_rm)} 单月同比 '
                  f'{pct(float(_MO_YY[_rk][_rm]))}，滚动同比 {pct(float(_TTM_YY[_rk][_rm]))}，'
                  f'单月读数是趋势的 <b>{_rv:.1f} 倍</b>。')
else:
    _ratio_txt = ''
ex.append({
    'n': 5, 'kind': 'grouped_bars', 'xlabels': [DISP[k] for k in KEYS],
    'fmt': 'f1', 'yfmt': 'f0', 'xrot': 0, 'bar_labels': True,
    'title': (f'12 个月滚动合计的同比，连排三年（{mlab(_y3[0])} / {mlab(_y3[1])} / '
              f'{mlab(_y3[2])}，三段互不重叠）'),
    'ylab': '% y/y，12 个月滚动合计',
    'groups': [{'name': f'{mlab(m)} 止 12 个月 y/y', 'color': col,
                'values': [round(float(_TTM_YY[k].get(m, np.nan)), 3)
                           if np.isfinite(float(_TTM_YY[k].get(m, np.nan))) else None
                           for k in KEYS]}
               for m, col in zip(_y3, ('GRAY', 'MBLUE', 'NAVY'))],
    'src_extra': ('Each bar compares a full 12-month window with the 12 months before it; '
                  'the three windows do not overlap'),
    'note': (f'每根柱是<b>一整年 vs 前一整年</b>，不是某一个月比某一个月：{_win_txt}。'
             f'三段互不重叠，各自与紧邻它前面的 12 个月比，所以并排读就是三个连续年度的增速。'
             f'全图最早触及的月份是 <b>{mlab(TTM_FIRST)}</b>（最早那根柱的同比基期起点）。<br>'
             f'<b>为什么不用单月同比：它连方向都可能是反的。</b>{_flip_txt}{_ratio_txt}<br>'
             f'把两个口径<b>各自对齐到同一批月份</b>后实测（'
             + '；'.join(f'{DISP[k]} {mlab(EVID[k]["first"])}–{mlab(EVID[k]["last"])}，'
                         f'{EVID[k]["n"]} 个月' for k in KEYS)
             + f'）：同比读数的标准差 {_ev_txt}；相邻月最大跳变 {_jump_txt}。'
             f'两个口径给出相反符号的月份数：'
             + '、'.join(f'{DISP[k]} {EVID[k]["flip"]}' for k in KEYS) + ' 个月。<br>'
             f'⚠ 「12 个月滚动合计」= 12 个月<b>日均值的等权合计</b>，没乘交易日 —— '
             f'沿用本页 Exhibit 3 的做法（等权，全页一个约定；{DAYW_TXT}）。'
             f'分子分母都恰好 12 个月，所以「合计的同比」与「均值的同比」逐位相同；'
             f'实测代价：对有交易日列的那几家，日加权与等权的滚动同比最大差 '
             f'<b>{TTM_QW_DEV:.2f}pp</b>。<br>'
             f'柱高是<b>增长率</b>不是份额 —— 四家各自与自己的前一年比，'
             f'四根柱之间不构成任何加总关系。'),
})

_fx_cum = {k: (FX[FXCOL[k]] / FX_BASE[k] * 100 - 100).reindex(IDX) for k in KEYS}
ex.append({
    'n': 6, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f1', 'zero_line': True,
    # ⚠ 这里原来写的是「上一张图那道缺口」—— 但排在 Exhibit 6 前面的是 Exhibit 5（同比图），
    # 而这张图要解释的缺口是 Exhibit 4 两根柱之间的落差。指代必须写死到图号上，
    # 「上一张 / 下一张」这种相对说法，只要中间插进任何一张图就会变成假话。
    'title': f'Exhibit 4 那道缺口的来源：本币兑美元累计变动（vs {mlab(BASE)}）',
    'ylab': f'% vs {mlab(BASE)}',
    'series': [{'name': f'{DISP[k]}（{CCY[k]}/USD）', 'color': COLOR[k],
                'values': L(_fx_cum[k].values)} for k in KEYS],
    'src_extra': 'Monthly average spot rates, series/fx.csv',
    'note': ('线在 0 以下 = 该货币相对美元比基期便宜。'
             '<b>Exhibit 4 里「定基汇率」与「当期汇率」两根柱之间的落差，就是这四条线累出来的</b>。'
             # ⚠️ 别写「本页唯一一处汇率会影响读数的地方」：上一张图的「当期汇率」柱
             #    按它自己的图注就是**全部来自汇率**，同一页当场把「唯一」证伪。
             #    这里只说本页主口径为什么干净 —— 那是锁基期汇率带来的，自明。
             f'<b>本页主口径的成交额一律按 {mlab(BASE)} 的汇率折美元</b>，'
             '此后汇率是常数、进不了那些图的增长结论；这四条线画的就是被锁掉的那一部分。'
             '港元挂钩美元，所以那条线基本贴着 0。'),
})

ex.append({
    'n': 7, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
    'title': f'季度同比矩阵：四家 × 近 {len(QHEAT)} 个季度（{qlab(QHEAT[0])} – {qlab(QHEAT[-1])}）',
    'rows': [DISP[k] for k in KEYS],
    'cols': [qlab(q) for q in QHEAT],
    'matrix': [L(QYOY[k].reindex(QHEAT).values) for k in KEYS],
    'legend': '现货成交额季度同比（定基汇率口径）',
    'cell_h': 24, 'row_lab_w': 62, 'row_head': '交易所',
    'src_extra': ('Green = faster growth. The colour scale is computed within this matrix only '
                  '(5th–95th percentile of its own cells)'),
    'note': ('绿 = 增长更快。<b>色标只在本图内可比</b>（按本图自己的 5/95 分位定），'
             '不要拿它与别的矩阵对色。这张图回答的是「谁与区域脱钩」：'
             '同一个季度里四家颜色不一致，说明那一段行情是某一个法域自己的事，'
             '不是「亚太整体」的事 —— 这正是不该把四家算成一个池的理由之一。'),
})

_dv_now = {k: float(idx100(DERIV[k])[CUR]) for k in KEYS}
ex.append({
    'n': 8, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0', 'zero_base': True,
    'title': f'衍生品 ADV，各家用自己的张数指数化（{mlab(BASE)} = 100）',
    'ylab': f'指数，{mlab(BASE)} = 100',
    'series': [{'name': DISP[k], 'color': COLOR[k],
                'values': L(idx100(DERIV[k]).reindex(IDX).values)} for k in KEYS],
    'src_extra': ('Contract counts, each rebased to its own 2019-01 level. Levels are NOT '
                  'comparable across exchanges — contract size is a product-design choice'),
    'note': ('<b>为什么只能指数化：这一段凑不齐基期价格。</b>'
             + bp_txt() +
             '而张数<b>不可跨所比水平值</b> —— '
             '单张合约的大小是各所自己选的产品设计参数，把合约切碎张数就上去了，'
             '市场上并没有多一分钱的风险转移。所以这张图只读<b>各条线自己的斜率</b>，'
             '<b>不读线之间的高低</b>。下一张图把这件事在 JPX 身上直接量出来。'),
})

_JW = pd.period_range(NK_START, LATEST, freq='M')
ex.append({
    'n': 9, 'kind': 'lines', 'full': True, 'height': 300,
    'xlabels': [mlab(p) for p in _JW],
    'fmt': 'f0', 'yfmt': 'f0c', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0c', 'zero_base': True,
    'title': '为什么张数不可跨所比：JPX 衍生品 ADV 的两种数法',
    'ylab': '张/日',
    'series': [
        {'name': '原始张数（官方新闻稿口径）', 'color': 'NAVY',
         'values': L(DERIV['jpx'].reindex(_JW).values)},
        {'name': '大合约当量（mini 记 1/10、micro 记 1/100）', 'color': 'BLUE',
         'values': L(JPX_LGEQ.reindex(_JW).values)},
    ],
    'src_extra': 'Both series are JPX’s own disclosures for the same set of trades',
    'note': (f'<b>同一批成交，同一家交易所，两条线差 '
             f'{float(DERIV["jpx"][CUR]) / float(JPX_LGEQ[CUR]):.1f} 倍</b>'
             f'（{mlab(CUR)}：{num(float(DERIV["jpx"][CUR]))} vs {num(float(JPX_LGEQ[CUR]))} 张/日）。'
             '差的全部是「合约被切成多小」：mini 与 micro 各按大板的 1/10、1/100 记 —— '
             f'乘数不在这里抄一份，现读入库那张表：{N225_MULT_TXT}。'
             '两条线的<b>斜率也不一样</b> —— 原始张数这些年一路上行，大合约当量却基本走平，'
             '意思是 JPX 名义上的「成交量增长」有相当一部分来自散户把仓位拆成更小的合约，'
             '不是多出来的风险转移。'
             '<b>这就是本页拒绝拿张数比水平值的实证依据，也是拒绝把四家张数相加的理由。</b>'),
})

ex.append({
    'n': 10, 'kind': 'lines', 'full': True, 'height': LINE_H, 'xlabels': NK_XL,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0', 'zero_base': True,
    'title': (f'产品级头对头 ①：日经 225 期货，SGX vs 大阪（JPX）'
              f'—— 各自指数化（{mlab(NK_START)} = 100）'),
    'ylab': f'指数，{mlab(NK_START)} = 100',
    'series': [
        {'name': 'SGX 日经 225 期货 ADV', 'color': C_SG,
         'values': L(idx100(NK_SG_W, NK_START).values)},
        {'name': '大阪（JPX）日经 225 期货 ADV，大合约当量', 'color': C_JP,
         'values': L(idx100(NK_JP_W, NK_START).values)},
    ],
    'src_extra': ('Same underlying index, dual-listed. SGX monthly volume divided by implied '
                  'derivatives trading days (deriv_vol ÷ DDAV); JPX in large-contract equivalents'),
    'note': ('<b>这是亚太唯一真正的零和争夺：同一个指数、同一批套利者、两个挂牌地。</b>'
             '一边多成交一张，另一边就少一张 —— 与 Exhibit 2 那种「各长各的」完全不同。'
             f'{mlab(NK_START)} 至 {mlab(CUR)}：SGX 侧 ADV 从 {num(float(NK_SG_W.iloc[0]))} '
             f'到 {num(float(NK_SG_W[CUR]))} 张/日（{pct(float(NK_SG_W[CUR]) / float(NK_SG_W.iloc[0]) * 100 - 100)}），'
             f'大阪侧从 {num(float(NK_JP_W.iloc[0]))} 到 {num(float(NK_JP_W[CUR]))} 张/日'
             f'（{pct(float(NK_JP_W[CUR]) / float(NK_JP_W.iloc[0]) * 100 - 100)}）。<br>'
             '⚠ 两处口径：(a) SGX 的分产品列是<b>当月总量</b>，这里除以'
             '「deriv_vol ÷ DDAV」反推的隐含衍生品交易日换成日均 —— 不用证券市场交易日，'
             f'两者实测最大差 {SG_DAYS_DEV:.2f} 天；'
             '(b) SGX 侧<b>不含</b>它的 Mini / USD 计价日经合约（CSV 无分列），'
             'SGX 被系统性低估，低估幅度未知；'
             '(c) <b>两条线的「张」不是同一种张</b> —— 大阪那条已按官方大合约当量归一'
             f'（乘数现读入库：{N225_MULT_TXT}），SGX 那条是<b>原始张数</b>'
             f'（该合约规格没取到，登记在 <code>contract_specs_todo.csv</code>；'
             f'{SGX_NK_TRIED_TXT}）。'
             '<b>所以这张图只能读两条线各自的斜率，两条线之间的高低没有意义</b> —— '
             '正因为如此才各自指数化到 100，而不是把两条画在同一个绝对刻度上。'),
})

ex.append({
    'n': 11, 'kind': 'lines', 'full': True, 'height': 300, 'xlabels': NK_XL,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0', 'zero_base': True,
    'title': f'产品级头对头 ②：日经 225 的分流趋势（SGX ÷ 大阪，{mlab(NK_START)} = 100）',
    'ylab': f'比值指数，{mlab(NK_START)} = 100',
    'series': [
        {'name': '月度比值', 'color': 'GRAY', 'values': L(NK_RATIO_IDX.values)},
        {'name': '12 个月滚动平均', 'color': 'NAVY', 'values': L(NK_RATIO_R12.values)},
    ],
    'src_extra': ('Ratio of the two ADV series, rebased. Any constant contract-size difference '
                  'cancels out in a rebased ratio, so this trend does not depend on the multipliers'),
    'note': ('<b>这是本页唯一一个完全不依赖合约规格的结论。</b>'
             '📌 未取到 SGX 日经合约的官方规格（sgx.com 是单页应用、rulebook 直链取不到，'
             f'{SGX_NK_TRIED_TXT}；第三方行情站按本仓规矩不采用），'
             '所以两所的单张名义额之比未知，'
             f'<b>Exhibit 1 里那个「SGX 占两所之和 {float(NK_SHARE[CUR]):.1f}%」只是张数口径，'
             '不能读作名义额分流比例</b>。'
             '但比值一旦指数化，<b>那个未知的乘数常数被完全约掉</b> —— '
             '只要两所的乘数在窗口内没变过，这条线的形状就是精确的。'
             f'读数：{mlab(NK_START)} = 100 → {mlab(CUR)} = {float(NK_RATIO_IDX[CUR]):.0f}，'
             f'即 SGX 相对大阪的位置只剩当年的 {float(NK_RATIO_IDX[CUR]) / 100:.2f} 倍。'
             '⚠ 前 11 个月没有 12 月滚动值，那条线从第 12 点起才有。'),
})

_a50 = {'n': 12, 'kind': 'lines', 'full': True, 'height': LINE_H, 'xlabels': A50_XL,
        'fmt': 'f0c', 'yfmt': 'f0c', 'xstep': 6, 'xrot': 90, 'markers': False,
        'end_label': True, 'label_fmt': 'f0c', 'zero_base': True,
        'title': '产品级头对头 ③：中国 A50 —— 只有 SGX 这一侧可测',
        'ylab': '张/日',
        'series': [{'name': 'SGX 富时中国 A50 指数期货 ADV', 'color': C_SG,
                    'values': L(A50_W.values)}],
        'src_extra': ('HKEX does not break out its MSCI China A50 Connect futures volume in the '
                      'monthly highlights, so the other side of this contest is not measurable here'),
        'note': ('HKEX 2021 年推出 MSCI 中国 A50 互联互通期货，公开目标就是抢 SGX 这块。'
                 '<b>但 HKEX 的月度披露不单列这个产品</b>（series/hkex.csv 只有衍生品张数合计），'
                 '所以这场争夺我们只能量出 SGX 一侧 —— <b>不能算分流比例，也不能说谁赢了</b>。'
                 f'能说的只有一句：竞品上线前 24 个月 SGX 的 A50 日均 {num(A50_PRE)} 张，'
                 f'上线后 24 个月 {num(A50_POST)} 张，最近 24 个月 {num(A50_L24)} 张 —— '
                 f'{"没有出现下滑" if A50_POST >= A50_PRE * 0.95 else "出现了下滑"}。'
                 '要判断 HKEX 拿走了多少，必须等 HKEX 分列披露，或找到第三方的双边成交数据。')}
if A50_BRK is not None:
    _a50['break_at'] = A50_BRK
    _a50['break_label'] = A50_RIVAL_TXT
ex.append(_a50)

_tw = {'n': 13, 'kind': 'lines', 'height': 260, 'xlabels': TW_XL,
       'fmt': 'f0c', 'yfmt': 'f0c', 'xstep': 6, 'xrot': 90, 'markers': False,
       'zero_base': True,
       'title': '产品级替代长什么样：SGX 台湾指数期货的授权迁移',
       'ylab': '张/日',
       'series': [
           {'name': 'MSCI 台湾指数期货', 'color': 'GRAY', 'values': L(TW_M_W.values)},
           {'name': '富时台湾指数期货', 'color': C_SG, 'values': L(TW_F_W.values)},
       ],
       'note': ('放这张图不是为了排名，是为了给「产品级竞争」一个可见的样子：'
                'SGX 的 MSCI 台湾合约在半年里归零，同一批持仓迁到它自己新挂的富时台湾合约上。'
                '<b>这类替代在亚太是逐个产品发生的，不是整个市场此消彼长</b> —— '
                '这正是本页用产品级头对头、而不用跨市场占比的原因。'
                '⚠ 争夺的另一方（台湾期交所）不在本仓，只能看到 SGX 这一侧；'
                + TW_GAP_TXT)}
if TW_BRK is not None:
    _tw['break_at'] = TW_BRK
    _tw['break_label'] = f'富时台湾合约上线（{mlab(TW_F_FIRST)}）'
ex.append(_tw)

ex.append({
    'n': 14, 'kind': 'lines', 'x': 'long', 'height': 260,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f1', 'zero_base': True,
    'title': 'HKEX 独有的结构变量：南向 ADT ÷ 现货总 ADT',
    'ylab': '%',
    'series': [{'name': '南向 ADT ÷ 总 ADT', 'color': C_HK, 'values': L(SB_RATIO.values)}],
    'src_extra': 'Both series from HKEX Monthly Market Highlights',
    'note': ('互联互通南向资金是 HKEX 独有的结构变量，别的三家没有对应物 —— '
             '所以它只能单独画，不能进任何横向比较。'
             '<b>⚠ 两条列的计数基准不一致：</b>HKEX 表内注明「ADT for Stock Connect includes '
             'buy and sell trades」（南向含买卖双边），而现货总 ADT 未注明双边。'
             '<b>所以这条线不是「南向占比」，它是一个上界</b> —— 若总 ADT 是单边计数，'
             '真实占比约为图上读数的一半。<b>只可读走势与拐点，不可读水平值。</b>'
             f'⚠ 图上有 {len(SB_RUNS)} 段没有线（{SB_HOLE_WORD}）：{SB_HOLE_TXT}，'
             '断开处不外推。'),
})

# ────────────── 8b. Exhibit 15–17：量价分解与量本身 ──────────────
# 新图一律**追加在末尾**：插在中间会让后面每一张图的编号级联位移，而正文与图注里
# 那些「Exhibit 4 那道缺口」「Exhibit 9 把这件事量出来了」的交叉引用全部变成假话。
_DW1, _DW0 = DECOMP[DEC_OK[0]]['w1'], DECOMP[DEC_OK[0]]['w0']
_win_lab = f'{mlab(_DW1[0])}–{mlab(_DW1[-1])} vs {mlab(_DW0[0])}–{mlab(_DW0[-1])}'

# 做不了的那几家：图上留空，图注点名，不用近似值顶上。原因分两类 ——
# 结构性缺列（DEC[k]['why']）与本轮窗口算不出来（DEC_BLANK[k]，含权重分母触底）。
_no_txt = '；'.join(
    f'<b>{DISP[k]}</b>：{DEC[k].get("why") or DEC_BLANK.get(k, "本窗口算不出来")}'
    for k in DEC_NO) or '本轮四家都能分解'
# 算术分解的对照读数（图上不画它，只写进图注）
_ar_txt = '；'.join(
    f'{DISP[k]} 量 {pp(DECOMP[k]["vol_ar"])} / 价 {pp(DECOMP[k]["prc_ar"])}'
    f'（交叉项 {pp(DECOMP[k]["cross"], 2)}，占总增长 '
    f'{abs(DECOMP[k]["cross"] / DECOMP[k]["gV"]) * 100:.1f}%）' for k in DEC_OK)
# 两法在本窗口的最大差异 —— 差多少由代码算，不说「差不多」
_ar_dev = max(max(abs(DECOMP[k]['vol'] - DECOMP[k]['vol_ar']),
                  abs(DECOMP[k]['prc'] - DECOMP[k]['prc_ar'])) for k in DEC_OK)
# 量与价**同向还是反向** —— 也由数据当场判，别写死家数。
# 判据用算术分解的两个纯增长率 gQ / gP：交叉项恰好是 gQ·gP/100，所以「反向」
# （异号）与「交叉项为负、且可以大到吃掉整个读数」说的是同一件事。
# ⚠ 从前这里连同图注一起写死成「本窗口三家都同向」，而同一段图注自印的算术读数
#   就是反例（某一家量正价负）。写死的定性断言没有任何东西会在它翻面时报警。
_same_dir = [k for k in DEC_OK if DECOMP[k]['gQ'] * DECOMP[k]['gP'] > 0]
_opp_dir = [k for k in DEC_OK if DECOMP[k]['gQ'] * DECOMP[k]['gP'] < 0]
_nil_dir = [k for k in DEC_OK if k not in _same_dir and k not in _opp_dir]


def _names(ks):
    return '、'.join(DISP[k] for k in ks)


if _opp_dir:
    _dir_txt = (
        f'本窗口画得出的 {len(DEC_OK)} 家里有 {len(_same_dir)} 家量与价同向'
        + (f'（{_names(_same_dir)}）' if _same_dir else '')
        + f'、{len(_opp_dir)} 家<b>反向</b> —— '
        + '；'.join(
            f'{DISP[k]} 量 {pct(DECOMP[k]["gQ"])} / 价 {pct(DECOMP[k]["gP"])}，'
            f'交叉项 {pp(DECOMP[k]["cross"], 2)}、占总增长 '
            f'{abs(DECOMP[k]["cross"] / DECOMP[k]["gV"]) * 100:.1f}%'
            for k in _opp_dir)
        + '，正是这一条要防的那种情形')
else:
    _dir_txt = (f'本窗口画得出的 {len(DEC_OK)} 家量与价<b>全部同向</b>'
                f'（{_names(DEC_OK)}），交叉项都是正的'
                + (f'；{_names(_nil_dir)} 有一侧恰好为零，不分同向反向' if _nil_dir else ''))
# 跨页对账：单公司页把当月总量直接相加（= 交易日加权），本页是日均值等权相加
_dw_txt = '；'.join(
    f'{DISP[k]} 量 {pp(DEC_DW[k]["vol"])} / 价 {pp(DEC_DW[k]["prc"])} / 总 {pct(DEC_DW[k]["gV"])}'
    for k in DEC_OK)
_scope_txt = '；'.join(f'<b>{DISP[k]}</b> {DEC[k]["scope"]}' for k in DEC_OK)
# 分解口径与头条口径的同比差 —— 差多少直接写出来，别让读者以为柱高就是 Exhibit 5 那个数
_gap_txt = '；'.join(
    f'{DISP[k]} 分解口径 {pct(DECOMP[k]["gV"])} vs 头条口径 {pct(float(_TTM_YY[k][CUR]))}'
    f'（差 {pp(DECOMP[k]["gV"] - float(_TTM_YY[k][CUR]), 2)}）' for k in DEC_OK)
# 这个差的**最大值与它落在哪一家** —— 供别处（Exhibit 17 图注、页尾口径说明）点名
# 「菱形不等于 Exhibit 5 那根柱」时引用，一样现算，不写死。
_gap = {k: DECOMP[k]['gV'] - float(_TTM_YY[k][CUR]) for k in DEC_OK}
_gap_worst = max(_gap, key=lambda k: abs(_gap[k]))
_gap_max = abs(_gap[_gap_worst])
_gap_min = min(abs(v) for v in _gap.values())
_alt = [k for k in DEC_OK if DEC[k].get('alt')]
# 被分解的那张图的图号：现读已经建好的 exhibit（此刻 Exhibit 5 已在 `ex` 里），不手写。
_ttm_ref = ttm_ex_txt('Exhibit 15 图注')
_ex15 = {
    'n': 15, 'kind': 'bridge_bar', 'xlabels': [DISP[k] for k in KEYS],
    'fmt': 'pp1', 'yfmt': 'f0', 'xrot': 0, 'height': 300,
    'title': f'成交额的增长拆成量与价（{_win_lab}）',
    'ylab': '对成交额增长的贡献（百分点）',
    'stacks': [
        {'name': (f'量的贡献 — {DEC[QTY_KEYS[0]]["qname"]}'
                  + (f'（{DISP[_alt[0]]} 那列是{DEC[_alt[0]]["qname"]}）' if _alt else '')),
         'color': 'NAVY',
         'values': [round(DECOMP[k]['vol'], 3) if DECOMP[k] else None for k in KEYS]},
        {'name': (f'价的贡献 — 成交额÷量'
                  + (f'（{DISP[_alt[0]]} 那列是每笔均值）' if _alt else '')),
         'color': 'MBLUE',
         'values': [round(DECOMP[k]['prc'], 3) if DECOMP[k] else None for k in KEYS]},
    ],
    'net': {'name': '成交额增长（12 个月滚动合计 y/y）',
            'values': [round(DECOMP[k]['gV'], 3) if DECOMP[k] else None for k in KEYS]},
    'net_color': 'INK',
    'src_extra': (f'Identity: turnover value ≡ quantity × average price, where average price is '
                  f'defined as value ÷ quantity. Same 12-month window as the latest '
                  f'bar of Exhibit {_ttm_ref}, but computed on the narrower columns listed in '
                  f'the note — the diamonds are NOT the bars of Exhibit {_ttm_ref}'),
    'note': ('<b>恒等式，不是模型：</b>均价 ≡ 成交额 ÷ 成交量，所以「成交额 ≡ 量 × 均价」'
             f'恒成立，零假设。窗口与 Exhibit {_ttm_ref} 最新那根柱完全相同：'
             f'<b>{_win_lab}</b>，菱形 = 该家<b>分解所用那一列</b>成交额的 12 个月滚动'
             f'合计同比 —— <b>窗口一样，底料不一样，所以它不是 Exhibit {_ttm_ref} '
             f'那根柱的读数</b>（差多少在下面「⚠ 口径」那一段逐家列出，'
             f'本轮最大 {_gap_max:.2f}pp、在 {DISP[_gap_worst]}）。<br>'
             f'<b>📌 画不出来的：</b>{_no_txt} —— 留空，不拿近似值顶上。<br>'
             + (f'<b>⚠ {DISP[_alt[0]]} 那一列是另一种恒等式</b>（红虚线右侧）：'
                f'它没有股数，只有成交<b>笔数</b>与每笔均值，拆出来的是'
                f'「笔数 × 每笔均值」，与 {"、".join(DISP[k] for k in QTY_KEYS)} 的'
                f'「股数 × 每股均价」<b>不是同一种分解</b>，'
                f'两者的柱高不可直接比较。顺带说，'
                f'{DISP[_alt[0]]} 这一列本身就是个例子：笔数贡献 '
                f'{pp(DECOMP[_alt[0]]["vol"])}、每笔均值贡献 {pp(DECOMP[_alt[0]]["prc"])} —— '
                f'成交被切成更多、更小的笔，与本页 Exhibit 9 讲的合约切碎是同一件事。<br>'
                if _alt else '')
             + '<b>⚠ 这里的「价」是加权平均成交价（成交额 ÷ 成交量），不是指数收益率。</b>'
             '它同时含<b>市场涨跌</b>与<b>成交结构变化</b> —— 贵的股票交易占比上升，'
             '一分钱没涨也会把它抬高。<b>不能读成「大盘涨了多少」。</b><br>'
             '<b>分解方式：对数权重</b>（全仓统一，与单公司页同一口径）。'
             'ln(额) = ln(量) + ln(价) 天然可加、零残差，再按 '
             '<code>w = 总增长 ÷ ln(额比)</code> 把两块重标定回百分点，'
             f'于是相加<b>逐列等于</b>总增长（本轮三道恒等式实测最大残差 {DEC_ID_MAXERR:.1e}pp，'
             f'超 1e-9 直接拒绝出页）。权重分母有下限：|ln(额比)| 低于 <b>{LOGW_EPS}</b> 就'
             f'<b>整根柱留空</b>，因为分母趋零时两段会被放大到读不出段高；'
             f'本轮最小 {DEC_LNV_MIN:.4f}，离下限还远。<br>'
             f'<b>为什么不用算术分解</b>（g额 = g量 + g价 + g量·g价，交叉项并进价）：'
             f'交叉项在<b>量与价反向</b>的年份会大到吃掉整个读数，'
             f'并进价里就把「价的贡献」污染成一个读不出意思的数。'
             f'<b>同向还是反向由数据当场判，不是一句写死的话</b> —— {_dir_txt}。'
             f'本窗口两法最大差 {_ar_dev:.2f}pp（算术读数：{_ar_txt}）；'
             f'差多差少都不改结论，<b>口径要按最坏情形定，不能按当期数据碰巧好看来定</b>。<br>'
             f'<b>⚠ 口径：</b>{_scope_txt}。分解口径与本页头条口径不完全重合的地方，'
             f'同比差多少直接列出 —— {_gap_txt}。'
             f'12 个月合计按<b>日均值等权相加</b>（与 Exhibit 3 / 5 一致；本页四家里 HKEX '
             f'没有交易日列，日加权在这一页做不到四家一致）。'
             f'<b>📌 跨页对账</b>：单公司页把当月总量直接相加（= 交易日加权），'
             f'所以同一家同一窗口两页读数不会逐位相同，差的是<b>聚合权重不是方法</b>。'
             f'同一批数据换成日加权是：{_dw_txt}，与本图最大差 {DEC_DW_DEV:.2f}pp。<br>'
             f'<b>✓ 汇率自检：</b>本币口径与「锁 {mlab(BASE)} 汇率折美元」口径各算了一遍，'
             f'两条路的每一项差 {DEC_FX_MAXDEV:.1e}pp —— 定基汇率是常数，'
             f'对增长率与分解结果<b>没有任何影响</b>，这一点是算出来的，不是说出来的。'),
}
if _alt:
    _ex15['break_at'] = KEYS.index(_alt[0])
    _ex15['break_label'] = f'{DISP[_alt[0]]}：笔数 × 每笔均值（另一种恒等式）'
ex.append(_ex15)

_qty_no = [k for k in KEYS if k not in QTY_KEYS]
_px_txt = '、'.join(f'{DISP[k]} 约 {QTY_PX_LOC[k]:,.2f} {CCY[k]}/股 ≈ ${QTY_PX_USD[k]:,.2f}'
                    for k in QTY_KEYS)
_px_ratio = ((max(QTY_PX_USD.values()) / min(QTY_PX_USD.values()))
             if len(QTY_KEYS) > 1 else float('nan'))
ex.append({
    'n': 16, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f0', 'zero_base': True,
    'title': f'量本身：成交股数指数化（{mlab(BASE)} = 100）',
    'ylab': f'指数，{mlab(BASE)} = 100',
    'series': [{'name': f'{DISP[k]} 成交股数（百万股/日）', 'color': COLOR[k],
                'values': L(idx100(QTY[k]).reindex(IDX).values)} for k in QTY_KEYS],
    'src_extra': ('Share counts, each rebased to its own 2019-01 level. Levels are NOT comparable '
                  'across exchanges — a share is a different economic object in each market'),
    'note': ('<b>为什么这张图也只能指数化。</b>两家的单位字面上都是「百万股/日」，'
             '但<b>一股在两地根本不是一回事</b>：'
             f'本窗口（{_win_lab.split(" vs ")[0]}）的加权平均成交价 = 成交额 ÷ 股数，'
             f'{_px_txt}（美元一列按锁 {mlab(BASE)} 的汇率折算）'
             + (f'，相差 <b>{_px_ratio:.0f} 倍</b>' if np.isfinite(_px_ratio) else '')
             + '。跨所比股数的水平值，等于比谁家的股票面额更碎 —— '
               '与本页 Exhibit 9 拒绝跨所比合约张数是同一条理由。'
               '所以这张图只读<b>各条线自己的斜率</b>，不读线之间的高低。<br>'
             + (f'<b>📌 画不出来的：</b>'
                + '；'.join(f'<b>{DISP[k]}</b>：'
                            + ('月度披露一列量都没有（只有金额）' if k not in DEC_OK
                               else '只有成交笔数、没有股数，笔数与股数不是一回事'
                                    '（同一批股票被切成更多笔，笔数就上去了）')
                            for k in _qty_no)
                + ' —— 这两家不在图上，也不用别的量顶替。<br>' if _qty_no else '')
             + '⚠ 股数只剔掉了价格，<b>剔不掉拆股与面值变更</b>：一次 1 拆 5 会让股数凭空翻五倍，'
               '而成交额一分钱没变。这张图读的是趋势方向，不是精确的活跃度倍数。'),
})

# ── Exhibit 17：股数的**单月**同比 ────────────────────────────────────────────
# 口径见上面 6d 节。图号不手写：新图一律追加在末尾，编号 = 上一张 + 1，
# 这样下面图注里点名的那个「Exhibit N」永远指着这张图自己（EX_CLASS 的登记表
# 会在图号真的变了的时候当场停机）。
_n17 = ex[-1]['n'] + 1
# 口径点名（CONTRACT.md §6.2）里滚动那一侧的图号 **现读已经建好的 exhibit**，
# 不手写 —— 手写的图号在插图 / 换口径之后就是一句指着别人说话的假话。
CAL_TTM_EX = ttm_ex_nums()
CAL_MOM_EX = [_n17]
CAL_MOM_TXT = '、'.join(str(n) for n in CAL_MOM_EX)
CAL_TTM_TXT = ttm_ex_txt('页尾口径说明')      # 空名单在这里当场停机

_qy = QYOY_MOM                      # ← 单月同比（yoy.mom_yoy），见上面 6d 节
_qty_scope = '；'.join(f'{DISP[k]} {DEC[k]["scope"]}' for k in QTY_KEYS)
# 均价分解**在单月口径上重做一遍**：这张图既然画的是单月，就不能再拿 Exhibit 5 那个
# 12 个月滚动的成交额同比来做商 —— 乘法分解要求两侧同口径，一边单月一边滚动，
# 算出来的「均价」不指代任何东西。数字全部现算，不抄上一版。
_qy_txt = ('；'.join(
    f'{DISP[k]} 股数 {pct(MOM_DEC[k]["gQ"])}、成交额 {pct(MOM_DEC[k]["gV"])}，'
    f'两者的<b>商</b>就是均价 {pct(MOM_DEC[k]["gP"])}' for k in MOM_DEC_OK)
    or '本月两家的分解列都有缺月，单月分解这一轮算不出来')
_qy_no = [k for k in QTY_KEYS if k not in MOM_DEC_OK]
# 与 Exhibit 15 那个年度视角的对照：同一家、同一个月，两个问题两套答案。
_qy_vs_ttm = '；'.join(
    f'{DISP[k]} 股数 单月 {pct(MOM_DEC[k]["gQ"])} vs 滚动 {pct(DECOMP[k]["gQ"])}、'
    f'均价 单月 {pct(MOM_DEC[k]["gP"])} vs 滚动 {pct(DECOMP[k]["gP"])}'
    for k in MOM_DEC_OK)
# 口径代价：CONTRACT §6.1 第 3 条指定的生成方式 —— yoy.describe(yoy.caliber_diff(...))，
# 拿**这条序列自己**实测，全仓共用一份措辞（三样：逐月标准差、相邻月最大跳变带月份、
# 符号相反的月份数）。逐条印，因为两家的代价并不一样大。
_qd_txt = '<br>'.join(f'· <b>{DISP[k]}</b>（{QDIFF[k]["n"]} 个月）：' + YOY.describe(QDIFF[k])
                      for k in QTY_KEYS)
ex.append({
    'n': _n17, 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 6, 'xrot': 90, 'markers': False,
    'end_label': True, 'label_fmt': 'f1', 'zero_line': True,
    # ⚠ 图题与轴标题是纯文本区（HTML 只在 note / notes / footer / summary.note 里生效），
    #   所以「单月」用直角引号强调，不要放 <b>。
    'title': '量的增速：成交股数的「单月」同比（当月 ÷ 去年同月 − 1）',
    'ylab': '% y/y，单月（当月 vs 去年同月）',
    'series': [{'name': f'{DISP[k]} 成交股数 y/y（单月）', 'color': COLOR[k],
                'values': L(_qy[k].values)} for k in QTY_KEYS],
    'src_extra': ('Single-month y/y on share counts: this month vs the same month a year '
                  'earlier. NOT the rolling 12-month convention used in Exhibit '
                  + CAL_TTM_TXT + ' — the two are different questions and their readings '
                  'must not be compared'),
    'note': ('<b>⚠ 本页并存两种同比口径，这张图是「单月」那一侧。</b>'
             f'<b>Exhibit {CAL_MOM_TXT}（本图）：单月同比</b>（当月 ÷ 去年同月 − 1）'
             '，汇总表的 y/y 四行也是单月；'
             f'<b>Exhibit {CAL_TTM_TXT}：12 个月滚动合计的同比</b> —— '
             'CONTRACT.md §6.2 点名保留滚动口径的例外之一。'
             f'（<b>Exhibit 15 与它同在那张名单上</b>：它是 Exhibit {CAL_TTM_TXT} 最新'
             f'那根柱的量价分解，<b>窗口逐字相同</b>（{_win_lab}），所以只能跟着它走 —— '
             '分解的两侧与被分解的总量不同口径，相加就不再等于净额。'
             f'<b>⚠ 但它的菱形不是 Exhibit {CAL_TTM_TXT} 那根柱的读数</b>：'
             '为了让分子分母同口径，分解换用了更窄的底料列，'
             f'本轮两者的差在 {_gap_min:.2f}–{_gap_max:.2f}pp 之间（绝对值，'
             f'最大那家是 {DISP[_gap_worst]}），<b>带符号的逐家读数在 Exhibit 15 的'
             '图注里逐家列出</b>。'
             '页顶数据条里标着「年度口径」的那一串现货 y/y 与那根柱同口径、同窗口 —— '
             '同一行打头的那一串是单月，两者在行内已分开标明。）'
             f'<b>不要拿这张图的读数去解释 Exhibit {CAL_TTM_TXT}，也不要反过来，'
             '两者更不能相减</b> —— '
             '它们不是同一个量的两种精度，是两个问题：'
             f'这张图问「这一个月比去年同一个月」，Exhibit {CAL_TTM_TXT} 问'
             '「这一整年比前一整年」。<br>'
             '<b>为什么这张图用单月：页面所有者要求本站的同比折线统一成单月口径。</b>'
             '这就是理由的全部 —— 不是「单月更灵敏」（那种说法本仓明令禁止）。'
             '<b>代价用这两条股数序列自己实测</b>（两种口径先对齐到都有值的月份再比）：<br>'
             + _qd_txt
             + '<br>（上面这段是全仓共用的措辞，其中「页上一条线都不画」说的是<b>折线</b>：'
               f'本页保留的滚动读数在 Exhibit {CAL_TTM_TXT} 的柱与 Exhibit 15 的菱形上，'
               '见本条开头的点名。这张图没有柱，与它同源的水平值在 Exhibit 16。）<br>'
             + f'<b>均价分解也在单月口径上重做</b>（{mlab(CUR)} 比 {mlab(CUR - 12)}）：'
             + f'{_qy_txt}。'
             + (f'<b>⚠ 与 Exhibit 15 那个「一整年 vs 前一整年」的窗口（{_win_lab}）对读，'
                f'会得到两套答案</b>：{_qy_vs_ttm}（这里的「滚动」是那个窗口的<b>增长率本身</b>，'
                f'不是 Exhibit 15 的段高 —— 段高的刻度见下一段）—— '
                f'这不是谁算错了，是两个不同的问题，'
                f'要哪一个取决于你问的是这一个月还是这一整年。' if _qy_vs_ttm else '')
             + '<b>⚠ 三者是乘法关系不是减法</b>：(1+股数增长)×(1+均价增长) = (1+成交额增长)'
               f'（本轮实测残差 {MOM_DEC_MAXERR:.1e}，超 1e-9 直接拒绝出页），'
               '所以「成交额同比 − 股数同比」并不等于均价同比，那个差里含一个交叉项。'
               'Exhibit 15 那两段柱高之所以能直接相加，是因为先取对数（ln 可加、零残差）'
               '再按总增长重标定回百分点 —— 那两段的高度<b>不等于</b>这里的任何一个读数，'
               '既不同刻度也不同窗口。<br>'
             + (f'📌 {"、".join(DISP[k] for k in _qy_no)} 本月的单月分解算不出来'
                f'（分解列在当月或去年同月有缺），线照画，分解不印。<br>' if _qy_no else '')
             + f'⚠ 两家的股数覆盖范围本来就不一样（{_qty_scope}），'
               '上面那个单月分解用的成交额列与 Exhibit 15 是同一批列（<b>不是本页头条列</b>，'
               '与头条口径差多少在 Exhibit 15 的图注里逐家列出）。所以这张图同样'
               '<b>只比各自的斜率、不比两条线之间的高低</b>；'
               '<b>股数也剔不掉拆股与面值变更</b>（一次 1 拆 5 让股数翻五倍，成交额一分没变）。'
             + (f'<br>⚠ 近零基数自检触发：{"、".join(DISP[k] for k in QDIFF_NZ)} '
                '的基期偏小，这条线上的部分读数反映的是分母不是量（CONTRACT.md §6.1 第 5 条）。'
                if QDIFF_NZ else '')),
})

# ────────────────────────── 9. 核对表（官方原始单位）──────────────────────────
TBL_COLS = [
    ('HKEX 现货 ADT (HK$bn)', 'hk_adt', lambda p: RAW['hkex']['adt_hkdbn'].get(p, np.nan), 3),
    ('JPX 现货 ADT (¥tn)', 'jp_adt', lambda p: RAW['jpx']['adt_cash_total_jpytn'].get(p, np.nan), 3),
    ('SGX SDAV (S$mn)', 'sg_adt', lambda p: RAW['sgx']['sdav_sgdmn'].get(p, np.nan), 1),
    # ⚠️ 名字必须带 on-market：/asx/ 单页的头条「现货 ADT」是**含场外报告**的总额
    #    （Jul-26 7.86 A$bn/day），本页这一列是 `adt_cash_onmarket_audbn`（同月 6.645）——
    #    同一个名字给两个数，读者跨页对不上还以为哪边算错了。口径差此前只在 Exhibit 15
    #    的图注深处交代过一次，光靠那一处够不到抬头与表头。
    ('ASX 现货 ADT · on-market (A$bn)', 'ax_adt',
     lambda p: RAW['asx']['adt_cash_onmarket_audbn'].get(p, np.nan), 3),
    ('HKEX 衍生品 ADV (张)', 'hk_dv', lambda p: DERIV['hkex'].get(p, np.nan), 0),
    ('JPX 衍生品 ADV，原始 (张)', 'jp_dv', lambda p: DERIV['jpx'].get(p, np.nan), 0),
    ('JPX 衍生品 ADV，大合约当量 (张)', 'jp_lg', lambda p: JPX_LGEQ.get(p, np.nan), 0),
    ('SGX DDAV (张)', 'sg_dv', lambda p: DERIV['sgx'].get(p, np.nan), 0),
    ('ASX 期货+期权 ADV (张)', 'ax_dv', lambda p: DERIV['asx'].get(p, np.nan), 0),
    ('SGX 日经 225 当月总量 (张)', 'sg_nkv',
     lambda p: RAW['sgx']['vol_nikkei225_futures_contracts'].get(p, np.nan), 0),
    ('SGX 日经 225 ADV (张/日)', 'sg_nk', lambda p: NK_SG.get(p, np.nan), 0),
    ('大阪日经 225 ADV，大合约当量 (张/日)', 'jp_nk', lambda p: NK_JP.get(p, np.nan), 0),
    ('SGX A50 ADV (张/日)', 'sg_a50', lambda p: A50_SG.get(p, np.nan), 0),
    ('HKEX 南向 ADT (HK$bn)', 'hk_sb', lambda p: SB.get(p, np.nan), 3),
]
W13 = IDX[-TBL_MONTHS:]
# 核对表由 page.js 渲染在**所有 exhibit 之后**（page.js 先跑 `D.exhibits.forEach`、
# 之后才是 `var T = D.table`；按符号 grep，不写行号 —— 行号一改动就漂）,
# 所以它的编号必须永远是「最后一张图 + 1」。写死数字的话，每次在末尾追加一张图，
# 页面上就会出现「Exhibit 17 之后跟着 Exhibit 15」，而没有任何东西会报错。
table = {
    'n': ex[-1]['n'] + 1,
    'title': f'近 {TBL_MONTHS} 个月原始指标核对表（各家官方原始单位与币种，未折美元、未指数化）',
    'idx': '月份',
    'cols': [[h, k] for h, k, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(fn(p)), d) for _, k, fn, d in TBL_COLS})
             for p in W13],
}

# ────────────────────────────── 10. 口径与方法说明 ──────────────────────────────
# ── 「本页所有图表一律截到此月」这句话的现算判据 ─────────────────────────────
# 旧文案是一句无条件的全称断言，而本页有画历史片段的图（右端停在过去某个月），
# 那句话在它身上就是假的。所以这里逐张现算右端，例外名单由代码给出 ——
# 以后再加一张历史片段图，这句话会自己跟着改，不需要有人记得回来改文案。
def _xl_of(e):
    if e.get('xlabels'):
        return e['xlabels']
    return XL_LONG if e.get('x') == 'long' else XL25


def _is_mlab(lab):
    lab = str(lab)
    return len(lab) == 6 and lab[3] == '-' and lab[:3] in MONTHS


_CUR_LAB = mlab(LATEST)
TRUNC_EXC = [(e['n'], _xl_of(e)[-1]) for e in ex
             if _xl_of(e) and _is_mlab(_xl_of(e)[-1]) and _xl_of(e)[-1] != _CUR_LAB]
# 例外可能不止一张 —— 措辞按现算的条数分岔，不能用「只有 X 例外」硬套：
# 两张例外时那句会印成「只有 A 例外、只有 B 例外」，自己跟自己打架。
_exc_txt = '、'.join(f'Exhibit {n}（止于 {lab}）' for n, lab in TRUNC_EXC)
TRUNC_TXT = ('—— 本页凡是以月为横轴的图，右端一律截到此月。' if not TRUNC_EXC else
             '—— 本页以月为横轴的图，右端截到此月，'
             + (f'只有 {_exc_txt}例外' if len(TRUNC_EXC) == 1
                else f'例外是 {_exc_txt} 这 {len(TRUNC_EXC)} 张')
             + '：画的是已经结束的历史片段，不跟着门槛往前走。'
             ) + f'（季度图落在 {qlab(QIDX[-1])} 那一季，类别轴的图没有时间右端。）'

# ── 「身份色的例外是哪几张」也现算 ───────────────────────────────────────────
# 旧文案手点了一张图号，而同形态的还有别的图：成员身份挂在 x 轴上时，
# NAVY / MBLUE / GRAY 编码的是口径或年份，不是哪一家。判据是「x 轴标签就是成员名单」，
# 由代码比对，不靠作者记得住有几张。
_MEMBER_XL = [DISP[k] for k in KEYS]
IDENT_X_EX = [e['n'] for e in ex if list(_xl_of(e)) == _MEMBER_XL]
_COLOR_OWNER = {COLOR[k]: DISP[k] for k in KEYS}


def _ident_lines(e):
    """这张图是不是「一条线一家、颜色 = 身份」。判据不是图号：
    ① 成员名单已经在 x 轴上的先排除 —— 那里颜色编的是别的维度；
    ② 其余图要求每条线的颜色都是四家的身份色**且互不重复**。
    一家之内拆多条线的图会用到 BLUE / GRAY 这类非身份色，或把身份色重复用在
    同一家的两条线上，因此自动落选。"""
    if list(_xl_of(e)) == _MEMBER_XL:
        return False
    cols = [s.get('color') for s in (e.get('series') or [])]
    return bool(cols) and all(c in _COLOR_OWNER for c in cols) and len(set(cols)) == len(cols)


IDENT_LINE_EX = [e['n'] for e in ex if _ident_lines(e)]
# 单家多线的图：线之间分的是产品或口径，不是家 —— 同样不能按身份色读。
INTRA_EX = [e['n'] for e in ex
            if (e.get('series') and len(e['series']) > 1 and not _ident_lines(e)
                and list(_xl_of(e)) != _MEMBER_XL)]

# ── 「本页的图分几类」：登记在代码里，漏一张就停机 ─────────────────────────
# 前几版是把图号手写进散文（先写两类、后来改成三类），加一张图就得有人回来改这句话，
# 而漏改不会报错 —— 页上直接多一句假话。这里改成登记表 + 构建期断言：
# 每一张 exhibit 都必须恰好落进一类，漏登记或重复登记当场 raise，发不出去。
# ⚠️ 类目描述只讲这一类是什么，**不许点名某张图画的是哪个产品** —— 那种句子又会
#    退回「加图就得有人记得改」的老路。
EX_CLASS = [
    ('横向对比', [2, 3, 4, 5, 6, 7, 8, 15, 16, 17],
     '把有数据的几家放在同一根轴上对读增长趋势 —— 汇率口径对照、汇率本身、'
     '以及把增长拆成量与价，都归在这一类'),
    ('产品级头对头', [10, 11],
     '同一个标的在两所双挂牌，一边多一张另一边就少一张，那才是真零和'),
    ('只有一侧可测的产品对', [12, 13],
     '对手方要么不单列这个产品的量、要么根本不在本仓，'
     '所以画的是一侧的量、<b>不是分流比例</b>，别当头对头读'),
    ('单家的内部结构', [9, 14],
     '整张图都在一家之内，不与别家比'),
]
_cls_all = [n for _lab, ns, _d in EX_CLASS for n in ns]
_ex_all = [e['n'] for e in ex]
if sorted(_cls_all) != sorted(_ex_all):
    raise SystemExit(
        f'EX_CLASS 与本页实际的 exhibit 对不上：登记 {sorted(_cls_all)}、'
        f'实际 {sorted(_ex_all)}。页尾第一条要按这张表点名图号，'
        f'对不上就会印出假话 —— 先把新图归类再发。')
if len(set(_cls_all)) != len(_cls_all):
    raise SystemExit(f'EX_CLASS 里有图号被登记了不止一次：{sorted(_cls_all)}')


def _exrange(ns):
    """把图号压成 2–8 这样的连续段，纯排版，不改变名单。"""
    ns, out, i = sorted(ns), [], 0
    while i < len(ns):
        j = i
        while j + 1 < len(ns) and ns[j + 1] == ns[j] + 1:
            j += 1
        out.append(f'{ns[i]}–{ns[j]}' if j - i >= 2 else '、'.join(str(x) for x in ns[i:j + 1]))
        i = j + 1
    return 'Exhibit ' + '、'.join(out)


_CLS_TXT = '；'.join(
    f'{mark} <b>{lab}</b> —— {_exrange(ns)}，{desc}'
    for mark, (lab, ns, desc) in zip('①②③④⑤⑥⑦⑧⑨', EX_CLASS))

# 「哪几张画了红虚线」同样现读 payload：断点滚出某张图的窗口、或某张图换了窗口长度，
# 手写的编号就成了一句指着不存在的线说话的假话，而没有任何东西会报错。
BRK_DRAWN = [e['n'] for e in ex if e.get('break_at') is not None]

_ahead_txt = ('；'.join(f'{d} 自身已更新至 {mlab(m)}' for d, m in AHEAD)
              if AHEAD else '本期四家的最新月恰好一致，无人跑在前面')
_rank_txt = '、'.join(f'{DISP[k]} {v:,.0f}' for k, v in _rank_idx)
# ── 抬头（页顶数据条）与 hub 行（= 首页卡片那句）引用的现货 y/y ──────────────
# 两者都以**单月**读数打头。这不是排版偏好，是页面所有者的指令：全站同比一律单月，
# 而 hub 行会被 data/roster.js 抄进首页卡片 —— 首页是他扫全部公司的地方，
# 那里不该出现一个要翻到本页页尾才解释得清的口径。所以：
#   · hub_line：**只有单月**，一个「滚动 / 12 个月」的字样都不出现；
#   · headline：单月打头，滚动那一串留着但**必须在同一行里标明它是 Exhibit 5 的年度口径**，
#     让读者当场知道那是两个问题，不是两种精度。
# 单月现货同比走全站唯一实现 yoy.mom_yoy（不写第二份 pct_change(12)），
# 并当场与汇总表那四行对账 —— 抬头与表格是同一批序列同一个月，漂了必须停机，
# 不能指望有人在页面上用眼睛比。
_MO_NOW = {k: float(YOY.mom_yoy(CASH[k], YOY.FLOW).reindex(IDX)[CUR]) for k in KEYS}
_mo_bad = [f'{DISP[k]}：抬头 {_MO_NOW[k]:.9f}% vs 汇总表 {float(yoy(CASH[k])[CUR]):.9f}%'
           for k in KEYS
           if not np.isfinite(_MO_NOW[k])
           or abs(_MO_NOW[k] - float(yoy(CASH[k])[CUR])) > 1e-9]
if _mo_bad:
    raise SystemExit('抬头的单月现货同比与汇总表那四行对不上（同一批序列、同一个月，'
                     '两处印不同的数就是页面自相矛盾）：\n  · ' + '\n  · '.join(_mo_bad))
_mo_rank = sorted(_MO_NOW.items(), key=lambda kv: -kv[1])

# 滚动读数照算，但从今往后**只在 headline 里作带标注的补充**出现（Exhibit 5 的年度口径）。
# ⚠ 别把它挪回 hub_line：那句会原样进首页卡片。
_yy_now = {k: float(_TTM_YY[k][CUR]) for k in KEYS}
_yy_rank = sorted(_yy_now.items(), key=lambda kv: -kv[1])

# 口径点名要用的第三种：季度同比矩阵（本季 vs 去年同季）。既不是单月也不是 12 个月滚动，
# 横轴是季度、滚动 12 个月无从对齐 —— CONTRACT.md §6.3 的图型豁免。图号现读，不手写。
CAL_QTR_EX = [e['n'] for e in ex if e['kind'] == 'heat_matrix']
CAL_QTR_TXT = '、'.join(str(n) for n in CAL_QTR_EX)
# 「两种口径不能跨图比高低」这句话要有本页现成的例子，而且是**算出来的**：
# 优先挑同一家、同一个月两种口径符号相反的那条股数读数；没有就退而求其次挑差最远的。
_cal_eg = next(((k, MOM_DEC[k]['gQ'], DECOMP[k]['gQ']) for k in MOM_DEC_OK
                if MOM_DEC[k]['gQ'] * DECOMP[k]['gQ'] < 0), None)
if _cal_eg:
    _cal_eg_txt = (f'本页现成的例子：{DISP[_cal_eg[0]]} 的 {mlab(CUR)} 成交股数同比，'
                   f'单月 {pct(_cal_eg[1])}、12 个月滚动 {pct(_cal_eg[2])} —— '
                   f'<b>一个说在跌、一个说在涨</b>。这不是哪张图算错了：'
                   f'前者说的是这一个月，后者说的是这一整年。')
elif MOM_DEC_OK:
    _eg_k = max(MOM_DEC_OK, key=lambda k: abs(MOM_DEC[k]['gQ'] - DECOMP[k]['gQ']))
    _cal_eg_txt = (f'本页现成的例子：{DISP[_eg_k]} 的 {mlab(CUR)} 成交股数同比，'
                   f'单月 {pct(MOM_DEC[_eg_k]["gQ"])}、12 个月滚动 '
                   f'{pct(DECOMP[_eg_k]["gQ"])} —— 差 '
                   f'{pp(MOM_DEC[_eg_k]["gQ"] - DECOMP[_eg_k]["gQ"])}，'
                   f'前者说的是这一个月，后者说的是这一整年。')
else:
    _cal_eg_txt = '本轮两家的单月分解都算不出来，例子这一轮留空。'

NOTES = [
    '<b>第一条，也是本页最重要的一条：这一页不画跨市场占比，一个都不画。</b>'
    'HKEX / JPX / SGX / ASX 是<b>法域隔离</b>的市场，彼此几乎零替代性 —— '
    '想买澳洲股票的资金不会因为 HKEX 费率低就流去香港，想买日本股票的资金也不会因为 '
    'SGX 便宜就改买新加坡股票。把四家的量相加当分母，'
    '得到的比值<b>没有任何外部指涉</b>：加进一家台湾或韩国，所有人的数字立刻全变；'
    '拿掉 ASX，其余三家又全变。那个数字唯一反映的是「谁碰巧长得快」，'
    '而这件事用增长率讲更直接、也不会被误读成「谁抢了谁的单」。'
    f'所以本页的图分 <b>{len(EX_CLASS)} 类</b>（名单由代码逐张归类给出，'
    f'新增的图没归类就构建停机，不会悄悄漏在句子外面）：{_CLS_TXT}。'
    '与 <code>/exchanges-na/</code> 对照着读会更清楚：那一页能说份额，'
    '是因为 ICE 逐月披露官方行业总量、四家争的是同一批订单流；这里两个条件一个都不成立。',

    f'<b>发布门槛：共同最新月。</b>全页统一截到 <b>{mlab(LATEST)}</b>，即四家中最慢那家的最新月。'
    f'本期短板是 <b>{"、".join(LAG)}</b>；{_ahead_txt}。'
    '门槛存在的理由：四家披露节奏不同，若各画各的最新月，读者会拿一家的 7 月比另一家的 6 月，'
    '看到的「谁跑赢」里有一整个月是口径造出来的。'
    '<b>跑在前面那家的最新月不在本页任何一张图、任何一行表里</b>，要看它请去它的单公司页。',

    f'<b>汇率锁在 {mlab(BASE)}，这是增长结论能成立的前提。</b>'
    f'四家的原始披露是四种货币（{"、".join(UNIT_RAW[k] for k in KEYS)}），'
    f'要放进一张图必须折美元。主口径一律用 series/fx.csv 的 {mlab(BASE)} 月均汇率，'
    '此后折算是常数 ⇒ <b>每条线的增长率与它本币口径的增长率完全相同</b>，'
    '汇率波动一个百分点都进不了增长结论。当期汇率口径只在 Exhibit 4 做对照、Exhibit 6 做拆解，'
    '<b>不进任何增长结论</b>。',

    '<b>现货主口径的硬伤：剔得掉汇率，剔不掉标的涨跌。</b>'
    '四家的头条源列都是成交<b>金额</b>（股数 × 当期价格），主口径（Exhibit 2/3/5/7）'
    '只做了汇率定基，价格项还在里面。这对应 <code>build/pools.py</code> 的 '
    '<code>deflator=\'fx_only\'</code>。后果：一轮牛市会同时抬高成交额与那几条增长线，'
    '<b>「成交额增长」不等于「交易活跃度增长」</b>。'
    '<br><b>但「剔不掉」四家并不一样</b>（本轮逐列核过 series/*.csv 表头，见下一条）：'
    'JPX 与 SGX 披露成交股数，所以对这两家可以把价格项单独量出来（Exhibit 15–17）；'
    'HKEX 月报一列量都没有，ASX 只有成交笔数。<b>能拆的两家不改变主口径</b> —— '
    '主口径要四家可比，而只有两家能拆。',

    '<b>量价分解（Exhibit 15–17）：恒等式是定义，可得性才是问题。</b>'
    '均价 ≡ 成交额 ÷ 成交量 ⇒「成交额 ≡ 量 × 均价」恒成立，没有模型假设。'
    '真正的约束在数据：'
    'JPX <code>adv_cash_dom_shares_mn</code>、SGX <code>sec_turnover_mnshares</code> 有股数，'
    '可以做真·量价分解；<b>HKEX 只有 <code>adt_hkdbn</code>，一列量都没有，图上留空</b>；'
    'ASX 没有股数、只有成交笔数与每笔均值，只能做「笔数 × 每笔均值」这<b>另一种</b>恒等式，'
    '在 Exhibit 15 里用红虚线隔在右侧，与左侧两家不可直接比较。'
    '<br><b>⚠ 分子分母必须同口径，否则「均价」是个混合物。</b>'
    'JPX 的头条列 <code>adt_cash_total_jpytn</code> 含 ETF/REIT'
    + (f'（占比现算：{JPX_ETF_TXT}，逐月在变）' if JPX_ETF_TXT else '（占比这一轮算不出来）')
    + '，而股数列只是 domestic 股票 —— 拿含 ETF 的金额除以不含 ETF 的股数，ETF 占比一波动'
    '就会被读成「涨价」，所以分解改用 <code>adt_cash_stocks_jpytn</code>'
    + (f'（换列换得对不对有恒等式兜底：stocks + etfreit ≡ total，实测最大残差 '
       f'{JPX_ID_MAXERR:.1e} 万亿日元）' if np.isfinite(JPX_ID_MAXERR) else '')
    + '；ASX 的每笔均值对应<b>总</b>成交额（含场外报告成交）而不是头条的 on-market —— '
    + (f'两条路各算一遍：total ÷ 笔数与官方每笔均值最大差 <b>{ASX_PT_TOT:,.2f} 澳元</b>，'
       f'on-market ÷ 笔数差到 <b>{ASX_PT_ONM:,.0f} 澳元</b>，贴得紧的那条才是它的分母'
       f'（这个判定翻面会当场停机）。' if np.isfinite(ASX_PT_TOT) and np.isfinite(ASX_PT_ONM)
       else '这一轮两条路都算不出来，判定留白。')
    + '这两处与头条口径的同比差多少，Exhibit 15 图注里逐家列出。'
    '<br><b>⚠ 拆出来的「价」是加权平均成交价，不是指数收益率。</b>'
    '它同时含市场涨跌与<b>成交结构变化</b>（贵的股票交易占比上升也会抬高它），'
    '<b>不能读成「大盘涨了多少」</b>。同理股数<b>剔不掉拆股与面值变更</b>。'
    '<br><b>分解用对数权重法，全仓统一</b>（与 <code>build/specs/sgx.py</code> 的 '
    '<code>method: log</code> 同一口径）：ln 可加、零残差，再按总增长重标定回百分点，'
    f'两块相加逐列等于总增长（三道恒等式实测最大残差 {DEC_ID_MAXERR:.1e}pp，'
    f'超 1e-9 直接拒绝出页）。不用算术分解是因为它的交叉项在<b>量与价反向</b>的年份'
    f'会大到吃掉整个读数，把「价的贡献」污染成读不出意思的数。'
    f'<b>本页当期同向还是反向，由数据当场判、不写死</b>：{_dir_txt}；'
    f'本窗口两法最大差 {_ar_dev:.2f}pp。差多差少都不改口径 —— 口径按最坏情形定。'
    f'算术读数仍照算并写在 Exhibit 15 图注里。'
    f'<br>权重分母有下限（|ln(额比)| < {LOGW_EPS} 整根柱留空，本轮最小 {DEC_LNV_MIN:.4f}）；'
    f'汇率不变性也是算出来的：本币口径与锁 {mlab(BASE)} 汇率的美元口径各跑一遍，'
    f'每一项差 {DEC_FX_MAXDEV:.1e}pp。'
    f'<br>📌 与单公司页对读时注意：那边把当月总量直接相加（交易日加权），本页是'
    f'日均值等权相加（全页一个约定；{DAYW_TXT}，等权与日加权的实测差见页尾），'
    f'所以同一家同一窗口两页读数差 {DEC_DW_DEV:.2f}pp 以内 —— '
    f'<b>差的是聚合权重，不是分解方法</b>，两页的方法现在是同一个。',

    '<b>四家现货口径的覆盖范围本来就不一样，水平值只能当量级参考。</b>'
    'ASX 用 on-market 口径、不含场外报告成交，而 Cboe Australia 约占澳洲市场两成且不在这个数里；'
    'JPX 含 ETF/REIT 与场内大宗；HKEX 含南向；SGX 含 ETF、结构化权证与 DLC。'
    '本页因此<b>从不对四家的水平值排名</b>，汇总表里列出水平值只为逐条与官方披露核对。',

    '<b>衍生品只能各自指数化，因为凑不齐基期价格。</b>'
    + bp_txt() +
    '而张数<b>不可跨所比水平值</b>：'
    '单张合约的大小是各所自己选的产品设计参数。Exhibit 9 把这件事量出来了 —— '
    'JPX 同一批成交按原始张数与按大合约当量相差 '
    f'{float(DERIV["jpx"][CUR]) / float(JPX_LGEQ[CUR]):.1f} 倍。'
    '所以 Exhibit 8 只读各条线自己的斜率，不读线之间的高低。',

    '<b>产品级头对头的三条口径，逐条读：</b>'
    '<br>① <b>日经 225（Exhibit 10 / 11）</b>：SGX 与大阪双挂牌，同一个指数，真零和。'
    'JPX 侧用官方的<b>大合约当量</b>（large + mini/10 + micro/100）'
    + (f'—— 这条恒等式的残差现算：{NK_LGEQ_N} 个月里最大 {NK_LGEQ_MAXERR:.1e} 千张/日，'
       f'即官方印数四舍五入的量级；'
       if np.isfinite(NK_LGEQ_MAXERR) else '；')
    + 'SGX 侧是当月总量除以「deriv_vol ÷ DDAV」反推的隐含衍生品交易日 —— '
    f'不用证券市场交易日，两者实测最大差 {SG_DAYS_DEV:.2f} 天。'
    '<b>📌 两侧的规格核实程度不一样，别当成对称的。</b>'
    f'JPX 侧的乘数<b>可逐个回源</b>（{N225_MULT_TXT}），'
    '所以那一侧是<b>已按大合约当量归一过的</b>；'
    'SGX 日经合约的官方规格<b>没取到</b>（sgx.com 是单页应用、rulebook 直链取不到，'
    '第三方行情站按本仓规矩不采用，已登记在 <code>series/contract_specs_todo.csv</code> 的 '
    f'<code>SGX_NK_NIKKEI225</code>；{SGX_NK_TRIED_TXT} —— 这个日期由那张台账现读，'
    '本页自己不发那个请求，所以不写成「本轮实测」），那一侧仍是<b>原始张数</b>。'
    '两侧一边归一、一边没归一，所以「SGX 占两所之和」那个百分比'
    '<b>连纯张数口径都算不上，更不是名义额份额</b> —— 只能读它的<b>方向</b>，不能读水平值；'
    '要读趋势请用 Exhibit 11 那条<b>比值指数</b>，它把两个未知/已知的乘数常数一起约掉了。'
    '另外 SGX 侧不含它的 Mini / USD 日经合约（CSV 无分列），SGX 被系统性低估，幅度未知。'
    '<br>② <b>中国 A50（Exhibit 12）</b>：HKEX 2021-10 推出 MSCI 中国 A50 互联互通期货来抢这块，'
    '<b>但 HKEX 不单列这个产品的量</b>，所以只有 SGX 一侧可测，不能算分流比例。'
    '<br>③ <b>铁矿石（SGX vs 大商所）没有画</b>：大商所不在本仓，只有一侧的数不构成头对头。'
    'MSCI 亚洲系列里可测的只有 Exhibit 13 那一组（SGX 自己的授权迁移），'
    '对手方台湾期交所同样不在本仓。',

    '<b>季度图为什么与月度图并存（Exhibit 3 vs Exhibit 2）。</b>月度序列噪音大，'
    '结构性趋势要季度才看得出来；月度图则保留了拐点的时间精度，两者互补。'
    f'季度图跨 <b>{qlab(QIDX[0])} – {qlab(QIDX[-1])}，共 {len(QIDX)} 个季度（约 {QYEARS:.1f} 年）</b>，'
    '各家有多长画多长、起点之前留空不外推。季度值 = 三个月日均的等权平均，'
    f'没做交易日加权（{DAYW_TXT}），实测代价：日加权与等权最大差 {QW_DEV:.2f}%。'
    '<b>只保留三个月都齐的整季</b> —— 半季会被读成一次暴跌。',

    '<b>本页并存两种同比口径，逐处点名（CONTRACT.md §6.2 要求的可核对形式）。</b>'
    '全站的同比现在一律是<b>单月</b>（当月 ÷ 去年同月 − 1），这是页面所有者定的；'
    f'本页的单月同比在：<b>Exhibit {CAL_MOM_TXT}</b>（成交股数，走全站唯一实现 '
    f'<code>build/yoy.py</code> 的 <code>mom_yoy</code>），以及汇总表（Exhibit 1）'
    f'里那四行 y/y。'
    f'<b>Exhibit {CAL_TTM_TXT}：12 个月滚动合计的同比</b> —— '
    f'CONTRACT.md §6.2 点名保留滚动口径的例外之一（另一处在 '
    f'<code>/exchanges12/</code>）。'
    f'<b>Exhibit 15 与它同在那张名单上</b>：它是 Exhibit {CAL_TTM_TXT} 最新那根柱的'
    f'量价分解 —— 柱 = 把那根柱的命题拆成量与价，<b>窗口逐字相同</b>（{_win_lab}），'
    f'所以只能跟着它走（分解的两侧与被分解的总量不同口径，相加就不再等于净额）。'
    f'<b>⚠ 但 Exhibit 15 的菱形不等于 Exhibit {CAL_TTM_TXT} 那根柱</b>：'
    f'为了让分子分母同口径，分解换用了更窄的底料列（逐家换的是哪一列、覆盖到哪里，'
    f'见上一条与 Exhibit 15 图注的「⚠ 口径」一段），所以两个数只是同窗口、不是同一个数 —— '
    f'本轮逐家差 {_gap_min:.2f}–{_gap_max:.2f}pp（绝对值，最大那家是 {DISP[_gap_worst]}），'
    f'带符号的逐家读数在 Exhibit 15 的图注里列出。'
    f'<b>页面抬头（页顶数据条）两种口径都印，并当场逐处标明</b>：打头那一串是'
    f'<b>单月</b>（{mlab(CUR)} 比 {mlab(YAG)}），后面那一串标着'
    f'「Exhibit {CAL_TTM_TXT} 的年度口径」的才是 12 个月滚动合计。'
    f'<b>hub 行（也就是首页卡片上那句）只印单月</b> —— '
    f'首页是一次扫全部公司的地方，不该出现一个要翻到这里才解释得清的口径。'
    + (f'另有既不属于这两者的一种：<b>Exhibit {CAL_QTR_TXT}</b> 的季度同比矩阵'
       f'（本季 vs 去年同季）—— 横轴是季度，12 个月滚动窗口无从对齐，'
       f'CONTRACT.md §6.3 把这类图型列为豁免。' if CAL_QTR_EX else '')
    + '<br><b>⚠ 两种口径的读数不能跨图比高低，也不能相减。</b>'
    + _cal_eg_txt
    + f'<br><b>Exhibit {CAL_MOM_TXT} 用单月，理由是页面所有者的指令</b> —— '
      '本站的同比折线统一改成单月口径。理由就到此为止：'
      '本仓不许拿「单月更灵敏 / 更及时」当理由，也不许反过来替页上不存在的口径背书'
      '（CONTRACT.md §6.1 第 3 条）。'
      f'换口径的代价用那两条序列自己实测（逐月标准差、相邻月最大跳变、'
      f'两种口径符号相反的月份数），印在 Exhibit {CAL_MOM_TXT} 的图注里。'
      f'<b>Exhibit {CAL_TTM_TXT} 不跟着改</b>：它的命题是「一整年 vs 前一整年」、'
      '三段窗口互不重叠、横轴根本不是月，本来就不是一条逐月的线，理由见下一条。',

    '<b>Exhibit 5 连排的是三个 12 个月滚动合计的同比，不是三个单月同比。</b>'
    '改口径的理由不是「平滑一点好看」，而是<b>单月同比在这四家身上连方向都会反</b>：'
    + (f'{DISP[_FLIP[0]]} 的 {mlab(_FLIP[1])} 单月同比 {pct(float(_MO_YY[_FLIP[0]][_FLIP[1]]))}，'
       f'同一时点的 12 个月滚动同比却是 {pct(float(_TTM_YY[_FLIP[0]][_FLIP[1]]))} —— '
       f'一个说在涨、一个说在跌，而后者才是那一整年真实发生的事。'
       if _FLIP else
       '本轮三根柱所在的月份恰好没撞上符号相反的实例，但共同窗口内仍有'
       + '、'.join(f'{DISP[k]} {EVID[k]["flip"]} 个月' for k in KEYS) + '符号相反。')
    + f'逐家对齐同一批月份后实测，同比读数的标准差从 '
    + '、'.join(f'{DISP[k]} {EVID[k]["sd_m"]:.1f}→{EVID[k]["sd_t"]:.1f}' for k in KEYS)
    + '，相邻月最大跳变从 '
    + '、'.join(f'{DISP[k]} {EVID[k]["jump_m"]:.0f}pp→{EVID[k]["jump_t"]:.0f}pp' for k in KEYS)
    + '。'
    + f'三根柱的窗口互不重叠、各为一个完整年（'
    + '；'.join(f'{mlab(m)} 柱 = {mlab(a)}–{mlab(b)}' for m, (a, b) in TTM_WIN.items())
    + f'），全图最早触及 <b>{mlab(TTM_FIRST)}</b>。'
    '滚动合计按<b>日均值等权相加</b>、不乘交易日（与 Exhibit 3 同一约定）。'
    f'⚠ 这个选择从前印的理由是「四家里只有三家有交易日列」，<b>现读实测不成立</b>：'
    f'{DAYW_TXT} —— 那句理由已撤，口径本身不动（Exhibit 5 在 CONTRACT.md §6.2 的保留'
    f'名单上，换加权方式会动它的读数，那是页面所有者的决定）。'
    f'代价照实测并覆盖全部有交易日列的成员：日加权与等权的滚动同比最大差 {TTM_QW_DEV:.2f}pp。'
    '柱高是<b>增长率</b>不是份额，四根柱之间不构成任何加总关系。',

    '<b>HKEX 南向那张图（Exhibit 14）的水平值不可信，走势可信。</b>'
    'HKEX 表内注明「ADT for Stock Connect includes buy and sell trades」（南向含买卖双边），'
    '而现货总 ADT 未注明双边 ⇒ 两列计数基准不一致，比值是一个<b>上界</b>；'
    '若总 ADT 为单边计数，真实占比约为图上读数的一半。'
    f'另外图上有 {len(SB_RUNS)} 段没有线（{SB_HOLE_WORD}）：{SB_HOLE_TXT}，'
    '断开处不外推 —— 段与段之间的月份是有值的，别把首尾两头连起来当成一整段空白。',

    '<b>颜色是身份，不是数值 —— 但只在「一条线一家」的那些图上。</b>'
    'HKEX 金、JPX 深蓝、SGX 中蓝、ASX 绿，与 <code>build/pools.py</code> 里 '
    'apac_cash / apac_deriv 的定义逐字相同 —— 同一家在不同页换色，跨页对照就全废了。'
    f'本轮真正「一条线一家」的是 Exhibit {"、".join(str(n) for n in IDENT_LINE_EX)}，'
    '只有这几张能按身份色读。<b>两类不能：</b>'
    f'① 把成员身份放在 x 轴、让颜色去编码别的维度（口径、年份窗口、分解项）的 '
    f'Exhibit {"、".join(str(n) for n in IDENT_X_EX)}；'
    f'② 线与线之间分的不是家、而是产品或口径的 '
    f'Exhibit {"、".join(str(n) for n in INTRA_EX)}。'
    '这两类图上的 NAVY / MBLUE / GRAY <b>不是</b>某一家。'
    '（三份名单都由代码逐条线核颜色算出，不靠人记得住有几张。）'
    '红色在本站是<b>结构性断点与截轴离群值的专用色</b>，不做数据色，'
    + (f'所以 Exhibit {"、".join(str(n) for n in BRK_DRAWN)} 里的红虚线是断点或'
       '口径分界标记，不是某一家。' if BRK_DRAWN else
       '本轮没有任何一张图画红虚线。'),

    f'<b>核对表（Exhibit {table["n"]}）用的是各家官方原始单位与币种</b>，没折美元也没指数化，'
    '就是为了让人拿官方新闻稿逐位对账。'
    'SGX 那两列一起给了「当月总量」与「ADV」，除数就是本页反推的隐含交易日，'
    '这样反推对不对也能被查。',
]

# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（payload 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图**这个月**该怎么读」（含当月读数、当月实测的毛刺量）；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**。
# 出现的数只有两类：把定义钉住的**结构性**量（隐含交易日与证券交易日差几天、
# 等权与日加权差几个百分点、日经三档的合约乘数、对数权重的分母下限）与恒等式本身 ——
# 且**一个都不写死**，全部引用本文件上游那些现算出来的量（SG_DAYS_DEV / TTM_QW_DEV /
# N225_MULT_TXT / _bp_gloss() / DAYW_TXT / LOGW_EPS），同本页其余图注的做法。
# 图号也不写死，走 gex()：图序一改，句子跟着改；找不到就整个半句不写。
#
# ━━ 为什么是这 15 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 核对表列头 /
# 副标题 / 图注 / 页尾说明里，而且**不看定义就会读错**。
# ⚠️ 后半截（副标题 / 图注 / 页尾说明）不是凑上去的：本板 15 个词里有 5 个**只**在那里
# 出现 —— 「共同最新月」（副标题与 notes[1]；汇总表那处是标题不是行头）、「定基名义额」
# （Exhibit 8 图注与 notes[6]）、「隐含衍生品交易日」（Exhibit 10 图注与 notes[7]①）、
# 「加权平均成交价」（Exhibit 15 / 16 图注与 notes[4]；Exhibit 15 的纵轴写的是
# 「对成交额增长的贡献（百分点）」）、「对数权重分解」（Exhibit 15 图注写作「分解方式：
# 对数权重」）。判据从前只写到「核对表列头」，照那句去删词会把本页最该解释的几个删掉。
# 这是一张**横截面页**，四家的数放在同一根轴上，
# 所以坑的分布与单公司页很不一样 —— 按「读错会出什么事」分五类：
#   ① 这一页自己造的口径（读者在别处见不到，必须点明分母/基期是什么）
#      共同最新月、定基汇率、指数化（基期 = 100）、定基名义额、SGX 占两所之和。
#      最要紧的是最后一个：那个百分比的分母是**池内两家之和**，不是市场份额 ——
#      本页正文一个跨市场占比都不画，唯独这一个比值在汇总表里露了脸，
#      不点破就是把它送去当「份额」读。
#   ② 分母与单位   ADT、ADV、SDAV / DDAV、隐含衍生品交易日 —— 四家四种币种、
#      四套交易日，SGX 的分产品列还是**当月总量**而不是日均。不点破，读者会拿
#      一家的天数去反推另一家的月总量，或把「当月总量」与「ADV」直接比大小。
#   ③ 同一件事的两个口径   原始张数 / 大合约当量、on-market / 含场外报告、
#      12 个月滚动合计 —— 两条口径都在页面上，读串的代价是整条线系统性偏高或偏低、
#      甚至同比符号相反，而图形完全正常，看不出来。on-market 那条还跨页：
#      /asx/ 单页头条是含场外的总额，同一个名字给两个数。
#   ④ 派生量的含义   加权平均成交价、对数权重分解 —— 量价分解那三张图上「价」这个字
#      最容易被读成「大盘涨了多少」，而它同时装着成交结构的变化。
#   ⑤ 只有一家有的结构变量   南向 ADT —— 计数基准与它的分母不一致，比值是**上界**。
# **有意不收**：m/m、y/y、3Y %ile、pp/bp（全站通用读图约定，summary.note 已逐条讲过）；
# 「跨市场占比 / 法域隔离」（页尾 notes 第 0 条整条在讲本页为什么一个份额都不画，
# 释义板再讲一遍就是两处各写一份 —— 这里只在「SGX 占两所之和」里点出那个分母）；
# 成交额 / 市值 / 交易日这类本页没有特殊口径的常识词。
# ══════════════════════════════════════════════════════════════════════════════
def gex(sub):
    """按图题里的一段字找图号；找不到返回 None，让引用它的那半句话整个不写。

    图号**不写死**：本页的图序改过不止一次（页面所有者按主题重排），
    写死的「见 Exhibit 9」在重排后会指向另一张图，而没有任何东西会报错。
    """
    hit = [e['n'] for e in ex if sub in (e.get('title') or '')]
    return hit[0] if len(hit) == 1 else None


def _ref(sub, fmt='（见 Exhibit {n}）'):
    n = gex(sub)
    return '' if n is None else fmt.format(n=n)


def _exl(*subs, fmt='（Exhibit {n}）'):
    """一次点名几张图，连成「（Exhibit 2 / 3）」；一张都没找到就整个不写。

    与 _ref() 同一个规矩（图号不写死，走 gex()），只是这里一句话要同时指几张图 ——
    句子在缺图号时也读得通，所以少一个号只少一个括号，不会留下悬空的指代。
    """
    ns = [n for n in (gex(s) for s in subs) if n is not None]
    return fmt.format(n=' / '.join(str(n) for n in ns)) if ns else ''


def _bp_gloss():
    """「基期价格缺在哪」，写成释义板读得通的一句 —— 判据与 bp_txt() 同源、现算。

    不直接调 bp_txt()：那句话是给 Exhibit 8 的图注写的，末尾指代「这张图」，
    搬进释义板就成了一个没有先行词的指代（释义板里根本没有图）。
    共用的是**判据**（_BP / BP_MISS，唯一定义处仍是 series/contract_specs.csv），
    不是那串措辞 —— 名单一变两处一起变，指代各说各的。
    """
    if _BP is None:
        return ('series/contract_specs.csv 读不到，衍生品篮子有没有基期价格无从判断，'
                '本页按最保守的口径处理：只指数化。')
    if not BP_MISS:
        return ('series/contract_specs.csv 里四家的衍生品篮子基期价格都齐了 —— '
                '这段措辞本该跟着改，出现即说明文案没跟上数据。')
    return (f'series/contract_specs.csv 里衍生品篮子的 <code>base_price_local</code> '
            f'还缺 {len(BP_MISS)} 个'
            f'（{"、".join(f"<code>{pid}</code>" for _k, pid in BP_MISS)}）'
            + (f'，已填上的是 {"、".join(f"<code>{pid}</code>" for _k, pid in BP_HAVE)}'
               if BP_HAVE else '')
            + '。<b>缺一家就没有共同口径</b>（要四家都有基期常数才折得出来）—— '
              '所以本页衍生品那一段只剩<b>张数</b>，只能各自指数化。')


GLOSSARY = [
    # ① 本页自己造的口径 —— 分母、基期、门槛，读者在别处见不到
    ('共同最新月',
     f'本页的<b>发布门槛</b>：全页统一截到<b>四家中最慢那家</b>的最新月，'
     f'这个月之后的数据一格都不进页面。定住这个门槛的那家（或那几家）本页叫'
     f'<b>短板</b>。⇒ <b>跑在前面那家已经发布的月份不在本页任何一张图、任何一行表里</b>，'
     f'要看它请去它的单公司页。理由：四家披露节奏不同，若各画各的最新月，'
     f'读者会拿一家的这个月去比另一家的上个月，「谁跑赢」里就凭空多出一整个月的口径差。'),

    ('定基汇率',
     f'四家的原始披露是四种货币（{"、".join(CCY[k] for k in KEYS)}），'
     f'放进同一张图必须折美元。本页主口径一律用 series/fx.csv 里 <b>{mlab(BASE)}</b> '
     f'的月均汇率，<b>此后折算是一个常数</b> ⇒ 每条线的增长率与它'
     f'<b>本币口径的增长率完全相同</b>，汇率波动一个百分点都进不了增长结论。'
     f'与它对照的是<b>当期汇率</b>（逐月实际汇率）口径 —— 本页只用它做对照与拆解，'
     f'<b>不进任何增长结论</b>；两者之间的落差<b>全部来自汇率</b>，与成交活跃度无关。'),

    # ⚠️ 2026-09 审出来的：这条从前把「只读斜率、不读线之间的高低」写成了对**所有**
    #    指数化图的通则，而本页自己的头条第三段（「自 BASE 累计指数：…」）做的就是把
    #    Exhibit 2 那四条线的高低排一个名次 —— 释义板与页顶数据条当场打架。
    #    Exhibit 2 的图注禁的是把线高读成**体量**，并没有禁读线间高低。
    #    「不读线之间的高低」在本页只对张数 / 股数 / 双挂牌两侧的「张」成立，
    #    理由是**底层单位不可跨所比**，而现货成交额折美元后不存在这个问题。
    ('指数化（基期 = 100）',
     f'每条线各自除以<b>它自己</b>在基期那一格的值再乘 100 ⇒ 线高读的是'
     f'<b>各自相对自己基期的累计增长</b>，<b>不是体量</b>'
     f'（体量在汇总表里，那里的水平值也只是量级参考）。'
     f'⚠ <b>线与线之间的高低能不能读，看底料可不可比，这不是一条通则</b>：'
     f'现货成交额那两张{_exl("定基汇率折美元后指数化", "季度口径的长历史")}折美元后'
     f'四家是同一种量纲的钱，线高就是各自的累计增长，<b>可以互相排名</b>'
     f'（页顶数据条那串「累计指数」排的就是它；不可排名的是汇总表里的<b>水平值</b>，'
     f'四家的现货口径覆盖范围本来就不一样）。而衍生品张数'
     f'{_exl("各家用自己的张数指数化")}、成交股数{_exl("量本身")}与日经 225 那两侧的「张」'
     f'{_exl("产品级头对头 ①")}，<b>底层单位本来就不是同一种东西</b>'
     f'（单张合约多大、一股多大都是各市场自己定的），'
     f'那几张<b>只读各条线自己的斜率，不读线之间的高低</b>。'
     f'基期逐图而定（现货月度 {mlab(BASE)}、'
     f'季度长历史 {qlab(QBASE)}、日经 225 那两张 {mlab(NK_START)}）。'
     f'⚠ 起点早于基期的序列在图左侧<b>可以低于也可以高于 100</b>，各条线在自己的'
     f'起点之前留空、不外推。'),

    ('定基名义额',
     f'把合约张数换算成「按<b>基期那一年的价格</b>折算的名义金额」的口径：'
     f'乘数 × 基期价格是常数 ⇒ 折出来的增长里<b>不含价格变动</b>，不同设计的合约'
     f'也才能放到同一根刻度上。<b>本页的衍生品折不出这个数：</b>{_bp_gloss()}'),

    ('SGX 占两所之和',
     f'汇总表里那个百分比：分母是 <b>SGX + 大阪两所之和</b>，'
     f'<b>不是</b>市场份额，也<b>不是</b>名义额的分流比例。'
     f'两侧口径并没有对齐 —— JPX 那一侧已按官方<b>大合约当量</b>归一，'
     f'SGX 那一侧仍是<b>原始张数</b>（该合约的官方规格没取到，登记在 '
     f'<code>series/contract_specs_todo.csv</code>）⇒ <b>只能读它的方向，'
     f'不能读水平值</b>。要读趋势请用那条<b>比值指数</b>{_ref("分流趋势", "（{n} 号图）")}：'
     f'比值一旦指数化，两边的乘数常数（不论已知未知）被<b>完全约掉</b>，'
     f'只要窗口内乘数没变过，那条线的形状就是精确的。'),

    # ② 分母与单位
    ('ADT',
     f'现货<b>日均成交额</b>（average daily turnover）：'
     f'<code>当月成交额 ÷ 当月现货交易日数</code>。四家的原始单位与币种各不相同'
     f'（{"、".join(UNIT_RAW[k] for k in KEYS)}），本页折美元后才同轴；'
     f'核对表（Exhibit {table["n"]}）给的则是<b>各家官方原始单位与币种的原值</b>，'
     f'没折美元也没指数化，就是为了拿官方新闻稿逐位对账。'
     f'⚠ 源列是成交<b>金额</b>（股数 × 当期价格），主口径只剔掉了汇率，'
     f'<b>没剔掉标的涨跌</b>。'),

    ('SDAV / DDAV',
     f'SGX 官方月报<b>自己的两个口径名</b>，核对表里 SGX 那两列直接沿用：'
     f'<b>SDAV</b>（Securities Daily Average）是证券市场的日均成交<b>金额</b>，'
     f'本页 SGX 那一行现货 ADT 用的就是它；<b>DDAV</b>（Derivatives Daily Average '
     f'Volume）是衍生品的日均<b>张数</b>，本页 SGX 那一行衍生品 ADV 用的就是它。'
     f'⇒ 两个名字指的是别家叫 ADT / ADV 的同一类东西，不是 SGX 多出来的两个指标。'),

    ('ADV',
     f'<b>日均成交张数</b>（average daily volume）：'
     f'<code>当月总张数 ÷ 该市场当月交易日数</code>。'
     f'⚠ <b>张数的水平值不可跨所比</b> —— 单张合约多大是各所自己选的<b>产品设计参数</b>，'
     f'把合约切碎张数就上去了，而市场上并没有多一分钱的风险转移。'
     f'⇒ 衍生品那几张图<b>只读各条线自己的斜率，不读线之间的高低</b>，'
     f'四家的张数更<b>不能相加</b>。'),

    ('隐含衍生品交易日',
     f'SGX 的分产品列（日经 225、A50、台湾指数）官方给的是<b>当月总量</b>、不是日均，'
     f'要与别家的 ADV 同轴必须先除以交易日。本页除的是 <code>deriv_vol ÷ DDAV</code> '
     f'反推出来的<b>隐含衍生品交易日</b>，<b>不用</b>证券市场交易日 —— '
     f'两者实测最大差 <b>{SG_DAYS_DEV:.2f} 天</b>。核对表把 SGX 的「当月总量」与「ADV」'
     f'两列都印出来，就是为了让这道反推自己也能被查。'),

    # ③ 同一件事的两个口径
    ('原始张数 / 大合约当量',
     f'<b>同一批成交的两种数法</b>，本页在 JPX 身上并排画出来'
     f'{_ref("两种数法", "（{n} 号图）")}：<b>原始张数</b>是官方新闻稿口径，'
     f'mini 与 micro 各按<b>一张</b>数；<b>大合约当量</b>把它们按大板的 1/10、1/100 '
     f'折回去（large + mini/10 + micro/100）。乘数不在这里抄一份，现读入库那张表：'
     f'{N225_MULT_TXT}。⚠ 两条线<b>不只是差一个倍数，斜率也不一样</b> —— '
     f'名义上的「成交量增长」有一部分来自合约被切得更小，<b>不是</b>多出来的风险转移。'),

    ('on-market / 含场外报告',
     f'ASX 现货成交额的<b>两套官方口径</b>：<b>on-market</b>（官方行名 '
     f'<code>On-market value</code>）＝ 连续竞价 ＋ 集合竞价 ＋ Centre Point，'
     f'<b>不含</b>场外成交事后报告；<b>含场外报告</b>（<code>Total cash market value</code>）'
     f'＝ on-market ＋ 场外报告。本页的头条、汇总表与核对表的 ASX 现货一律是 '
     f'<b>on-market</b>，而 <code>/asx/</code> 单页头条是<b>含场外</b>的总额 —— '
     f'<b>同一个名字给两个数</b>，跨页对不上不是谁算错了。'
     f'⚠ 本页把 ASX 的成交额拆成量与价的那一列用的又是<b>含场外</b>的总额'
     f'（官方的每笔均值对应的是它），差多少在那张图的图注里逐家列出。'),

    ('12 个月滚动合计',
     f'把连续 12 个月的<b>日均值等权相加</b>（<b>不乘交易日</b>）。'
     f'它的同比问的是「<b>一整年比前一整年</b>」，与本页另一处同比（这一个月比去年同一个月）'
     f'<b>是两个问题：不能比高低，更不能相减</b> —— 本页两种口径并存，'
     f'哪张图是哪一种在页尾逐处点名。⚠ 等权是全页一个约定（{DAYW_TXT}）；'
     f'代价实测：日加权与等权的滚动同比最大差 <b>{TTM_QW_DEV:.2f}pp</b>。'),

    # ④ 派生量的含义
    ('加权平均成交价',
     f'量价分解里的那个「价」：<code>成交额 ÷ 成交量</code> —— <b>定义式，不是模型</b>'
     f'（所以「成交额 ≡ 量 × 均价」恒成立，零假设）。'
     f'⚠ 它同时含<b>市场涨跌</b>与<b>成交结构变化</b>：贵的股票交易占比上升，'
     f'价格一分钱没涨也会把它抬高 ⇒ <b>不能读成「大盘涨了多少」</b>。'
     # ⚠️ 2026-09 审出来的：这半句从前把「量」一口咬定为成交股数，而本页画得出分解的
     #    三家里有一家（DEC 里带 alt 的那家）根本没有股数 —— 它拆的是「笔数 × 每笔均值」，
     #    页尾 notes[4] 与 Exhibit 15 图注（红虚线右侧）都专门警告过这一处。
     #    名单不写死：QTY_KEYS / _alt 由 DEC 现算，哪家有股数一变，这两句跟着变。
     + (f'⚠ <b>这条说的是有股数的那几家</b>（{_names(QTY_KEYS)}）：它们拆的是'
        f'「股数 × 每股均价」，而与均价相乘的那个<b>股数剔不掉拆股与面值变更</b> —— '
        f'一次 1 拆 5 会让股数凭空翻五倍，而成交额一分钱没变。'
        if QTY_KEYS else '')
     + (f'<b>{_names(_alt)} 没有股数</b>，那一列拆的是'
        f'「{DEC[_alt[0]]["qname"]} × 每笔均值」，它的「价」是<b>每笔</b>均值、'
        f'<b>不是每股均价</b>，与上面那几家<b>不是同一种分解</b>，柱高也不可直接比较'
        + _ref('拆成量与价', '（见 Exhibit {n} 图注红虚线右侧）') + '。'
        if _alt else '')),

    ('对数权重分解',
     f'把成交额的增长分成「量」与「价」两段所用的方法（全仓统一）：'
     f'<code>ln(额) = ln(量) + ln(价)</code> 天然可加、零残差，再按 '
     f'<code>w = 总增长 ÷ ln(额比)</code> 把两段重标定回百分点，'
     f'于是<b>两段相加逐列等于总增长</b>。<b>不用</b>算术分解'
     f'（g额 = g量 + g价 + 交叉项）是因为交叉项在<b>量与价反向</b>的年份'
     f'会大到吃掉整个读数，并进「价」里就把价的贡献污染成一个读不出意思的数。'
     f'⚠ 权重的分母有下限：<code>|ln(额比)|</code> 低于 <b>{LOGW_EPS}</b> '
     f'就<b>整根柱留空</b> —— 分母趋零时两段会被放大到读不出段高。'),

    # ⑤ 只有一家有的结构变量
    ('南向 ADT',
     f'HKEX 互联互通<b>南向</b>成交的日均金额，是 HKEX <b>独有的结构变量</b>，'
     f'另外三家没有对应物 ⇒ 只能单独画{_ref("南向", "（{n} 号图）")}，'
     f'<b>不进任何横向比较</b>。⚠ HKEX 表内注明南向<b>含买卖双边</b>'
     f'（表注原文 ADT for Stock Connect includes buy and sell trades），'
     f'而现货总 ADT 未注明双边 ⇒ 两列的计数基准不一致，'
     f'<b>「南向 ÷ 总 ADT」不是「南向占比」，而是它的上界</b>'
     f'（若总 ADT 是单边计数，真实占比约为图上读数的一半）。'
     f'⇒ <b>只可读走势与拐点，不可读水平值。</b>'),
]

# ────────────────────────────── 11. payload ──────────────────────────────
SOURCE_DATE = load_source_dates().latest_of(SERIES, KEYS, {k: LATEST for k in KEYS})

payload = {
    'ticker': TICKER,
    'tracker': 'Asia-Pacific Exchanges — HKEX / JPX / SGX / ASX',
    'title': f'亚太交易所横截面（HKEX / JPX / SGX / ASX）：增长与产品级争夺 — {zh(LATEST)}',
    'data_through': str(LATEST),
    'through_label': f'{zh(LATEST)}（共同最新月）',
    'subtitle': (f'数据源：四家官方月度披露 · 共同窗口 {mlab(START)} – {mlab(LATEST)}'
                 f'（{len(IDX)} 个月）；季度长历史 {qlab(QIDX[0])} – {qlab(QIDX[-1])}'
                 f'（{len(QIDX)} 季）· 发布门槛取共同最新月，短板 {"、".join(LAG)} · '
                 f'现货折美元一律锁 {mlab(BASE)} 汇率 · '
                 # ⚠ subtitle / headline 由 page.js 的 set() 用 textContent 写入（搜 `set('sub'`），
                 # 里面放 HTML 标签会原样印在页面上。允许 HTML 的只有 notes / footer /
                 # summary.note / exhibit.note 四处。本轮浏览器实测撞过一次，故留此注。
                 '本页不画跨市场占比：四家法域隔离、几乎零替代性，'
                 '分母只能是我们自己圈的 · 版式仿 Goldman Sachs GIR · 仅图，无评论'),
    # ⚠️ ASX 那一格必须点明 on-market：/asx/ 单页的头条「现货 ADT」是**含场外报告**的总额，
    #    同月同比 +9.9%，而本页这一格是 on-market、+11.6%。同一个名字给两个数，
    #    读者跨页对不上只会以为哪边算错了。口径差此前只在 Exhibit 15 图注深处交代过一次。
    'headline': (f'现货 y/y（单月：{mlab(CUR)} 比 {mlab(YAG)}，定基汇率；'
                 f'ASX 为 on-market，不含场外报告成交 —— /asx/ 单页头条是含场外的总额，两者不同）：'
                 + '、'.join(f'{DISP[k]} {pct(v)}' for k, v in _mo_rank)
                 + f' · 同一批序列换成 Exhibit {CAL_TTM_TXT} 的年度口径'
                   f'（12 个月滚动合计，一整年比前一整年 —— 与上面是两个问题，不可比高低）：'
                 + '、'.join(f'{DISP[k]} {pct(v)}' for k, v in _yy_rank)
                 + f' · 自 {mlab(BASE)} 累计指数：{_rank_txt}'
                 + f' · 产品级：日经 225 的 SGX ÷ 大阪比值只剩 {mlab(NK_START)} 的 '
                   f'{float(NK_RATIO_IDX[CUR]) / 100:.2f} 倍'
                 + f' · SGX A50 最近 24 个月日均 {num(A50_L24)} 张，'
                   f'竞品上线前 24 个月 {num(A50_PRE)} 张'),
    # 名词释义：页面上排在所有 exhibit 之前。选词判断与「有意不收哪些词」写在
    # GLOSSARY 上方那一块注释里；版式与四道护栏在 build/glossary.py（全站共用）。
    'glossary': gloss.render(GLOSSARY, where='exchanges-apac glossary'),
    # ⚠ 这一句会被 build/roster.py 抄进首页卡片：**只准出现单月读数**。
    #   写「12 个月滚动 / TTM / rolling」进来，首页上就会冒出一个当场解释不了的口径。
    'hub_line': (f'共同最新月 {mlab(LATEST)}（短板 {"、".join(LAG)}）；'
                 f'现货单月 y/y（{mlab(CUR)} 比 {mlab(YAG)}）领先 '
                 f'{DISP[_mo_rank[0][0]]} {pct(_mo_rank[0][1])}；'
                 f'本页不算跨市场占比'),
    'source': SRC,
    'xlabels': XL25,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.5% 步长整列印成重复数字，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    'exhibits': axisfmt.fix_all(ex),
    'table': table,
    'notes': NOTES,
    'footer': (f'亚太交易所横截面 · HKEX / JPX / SGX / ASX · '
               f'<b>发布门槛：共同最新月 {mlab(LATEST)}</b>，本期短板 '
               f'{"、".join(f"{DISP[k]}（{mlab(latest_each[k])}）" for k in KEYS if latest_each[k] == LATEST)} '
               + TRUNC_TXT
               + (f'跑在前面的 {"、".join(f"{d}（已更新至 {mlab(m)}）" for d, m in AHEAD)} '
                  f'的最新月未纳入本页。' if AHEAD else '本期四家最新月一致。')
               + f'各家最新披露：{" · ".join(f"{DISP[k]} 更新至 {mlab(latest_each[k])}" for k in KEYS)} · '
                 '<b>本页不计算、不显示跨市场占比</b> —— 四家法域隔离，分母没有外部指涉；'
                 '两所之间的分流比例只在同标的双挂牌的产品级图里以张数口径出现，且已标明规格未归一 · '
                 'charts only, no commentary · personal research use'),
}
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE


# ────────────────────────────── 12. 写出 ──────────────────────────────
def write_shell():
    """写 /exchanges-apac/index.html。

    模板从 build/make_shells.py 导入，不复制 —— 复制出来的第二份迟早与第一份分叉。
    不改 make_shells.py / make_shells12.py：那两个文件由别的页共用，
    本页自己写自己的壳，互不干扰。内容只跟 ticker 有关，重跑幂等。
    """
    spec = importlib.util.spec_from_file_location(
        'make_shells', os.path.join(HERE, 'make_shells.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = os.path.join(PAGE_DIR, 'index.html')
    html = mod.SHELL.format(t=TICKER)

    # 内容没变就**不落盘**。这个页壳写在 PUBLISH（= ['data','series']）之外，而
    # guard_dirty_tree() 跑在构建之前 —— 白写一次的后果是：本轮发不出去，下一轮
    # 因工作树脏而 FAILED。重跑幂等（内容只跟 TICKER 有关），所以正常情况下
    # 这里永远命中 return，只有模板真改了才写。
    try:
        with open(p, encoding='utf-8') as f:
            if f.read() == html:
                return p
    except Exception:                                # noqa: BLE001 —— fail-open，宁可多写
        pass

    os.makedirs(PAGE_DIR, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(html)
    return p


def selfcheck_page():
    """凡是纵轴写着「= 100」的图，基期那一格必须真的是 100。

    本轮真的踩过：Exhibit 3 的 series 直接喂了 US$bn/日 的水平值，
    轴标题却写着「指数，1Q19 = 100」—— 引擎不会报错，图看上去也很正常
    （四条线按体量排开，像极了一张「谁体量大」的图），只有末点标签的数量级不对。
    所以这道自检不是可选的：它是这一类错误的**唯一**机器拦截点。
    """
    bad = []
    for e in payload['exhibits']:
        ylab = e.get('ylab', '')
        if '= 100' not in ylab or e.get('kind') != 'lines':
            continue
        xl = e.get('xlabels') or (XL_LONG if e.get('x') == 'long' else XL25)
        # 轴标题里「X = 100」的 X 就是基期标签，回到 xlabels 里找它的位置
        want = ylab.split('，')[-1].split('=')[0].strip()
        if want not in xl:
            bad.append(f'Exhibit {e["n"]}：轴标题的基期 {want!r} 不在本图 xlabels 里')
            continue
        j = xl.index(want)
        # 基期为 None 的序列放过：滚动均值、晚上线的腿天然在基期没有值。
        # 但**至少要有一条**序列在基期等于 100，否则整张图就不是指数图。
        hit = 0
        for s in e['series']:
            v = s['values'][j]
            if v is None:
                continue
            if abs(v - 100.0) > 0.01:
                bad.append(f'Exhibit {e["n"]} 的「{s["name"]}」在基期 {want} 上是 {v}，不是 100')
            else:
                hit += 1
        if not hit:
            bad.append(f'Exhibit {e["n"]}：基期 {want} 上没有任何一条序列等于 100')
    # page.js 的 set() 用 **textContent** 写 title / subtitle / headline（搜 `set('sub'`），
    # 放 HTML 进去会把标签原样印在抬头上。
    # ⚠ through_label 走的是**另一条路**：它拼进 `el('meta').innerHTML`（搜 `数据截至`），
    #   那里 HTML 其实会被解释。这里仍然一并拦下 —— 抬头那一行是纯文本区，
    #   混进标签同样不该发生。但别再把它记成「textContent 写入」，那是句错的机制描述。
    for f in ('subtitle', 'headline', 'through_label', 'hub_line', 'title'):
        if '<' in payload.get(f, ''):
            bad.append(f'payload["{f}"] 里有 HTML 标签，但这个字段由 page.js 按纯文本写入')
    if bad:
        raise SystemExit('页面自检失败：\n  · ' + '\n  · '.join(bad))
    return sum(1 for e in payload['exhibits']
               if '= 100' in e.get('ylab', '') and e.get('kind') == 'lines')


def main():
    n_rebased = selfcheck_page()
    shell = write_shell()
    payload_guard.write_dash(OUT, payload, TICKER)
    print(f'指数化自检：{n_rebased} 张「= 100」图的基期格全部等于 100 ✓')
    print(f'共同最新月 {LATEST} | 各家: '
          + ', '.join(f'{DISP[k]}={latest_each[k]}' for k in KEYS))
    print(f'短板 {"、".join(LAG)} | 月度共同窗口 {START} → {LATEST}（{len(IDX)} 个月）')
    print(f'季度长历史 {QIDX[0]} → {QIDX[-1]}（{len(QIDX)} 季，约 {QYEARS:.1f} 年）'
          f' | 日经头对头窗口 {NK_START} → {LATEST}（{len(NK_IDX)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'Exhibit 5 口径 = 12 个月滚动合计同比 | 三段窗口 '
          + '、'.join(f'{mlab(a)}–{mlab(b)}' for _m, (a, b) in TTM_WIN.items())
          + f' | 最早触及 {mlab(TTM_FIRST)} | 等权 vs 日加权最大差 {TTM_QW_DEV:.2f}pp')
    print('单月同比 → TTM 同比（标准差 / 相邻月最大跳变 / 符号相反月数）：'
          + '，'.join(f'{DISP[k]} {EVID[k]["sd_m"]:.1f}→{EVID[k]["sd_t"]:.1f}'
                      f' / {EVID[k]["jump_m"]:.1f}→{EVID[k]["jump_t"]:.1f}pp'
                      f' / {EVID[k]["flip"]}' for k in KEYS))
    print(f'Exhibit {CAL_MOM_TXT} 口径 = 单月同比（yoy.mom_yoy，页面所有者指令）'
          f' | 滚动口径仍在 Exhibit {CAL_TTM_TXT}'
          + (f' | 季度同比矩阵 Exhibit {CAL_QTR_TXT}' if CAL_QTR_EX else ''))
    print('  股数序列实测代价（对齐后月数 / 标准差 单月 vs 滚动 / 相邻月最大跳变 / 符号相反月数）：'
          + '，'.join(f'{DISP[k]} {QDIFF[k]["n"]} / {QDIFF[k]["std_mom"]:.1f} vs '
                      f'{QDIFF[k]["std_ttm"]:.1f}pp / {QDIFF[k]["maxjump_mom"][0]:.0f} vs '
                      f'{QDIFF[k]["maxjump_ttm"][0]:.0f}pp / {QDIFF[k]["opposite_n"]}'
                      for k in QTY_KEYS))
    print(f'  单月量价分解（{mlab(CUR)} 比 {mlab(CUR - 12)}）：'
          + '，'.join(f'{DISP[k]} 股数{MOM_DEC[k]["gQ"]:+.2f}% × 均价{MOM_DEC[k]["gP"]:+.2f}%'
                      f' = 成交额{MOM_DEC[k]["gV"]:+.2f}%' for k in MOM_DEC_OK)
          + f' | 乘法恒等式最大残差 {MOM_DEC_MAXERR:.1e} ✓（阈值 1e-9）'
          + (f' | 算不出来：{"、".join(DISP[k] for k in QTY_KEYS if k not in MOM_DEC_OK)}'
             if len(MOM_DEC_OK) < len(QTY_KEYS) else ''))
    print(f'量价分解（对数权重，全仓统一）窗口 {mlab(_DW1[0])}–{mlab(_DW1[-1])} vs '
          f'{mlab(_DW0[0])}–{mlab(_DW0[-1])} | '
          + '，'.join(f'{DISP[k]} 量{DECOMP[k]["vol"]:+.2f}pp 价{DECOMP[k]["prc"]:+.2f}pp '
                      f'= 总{DECOMP[k]["gV"]:+.2f}%' for k in DEC_OK)
          + (f' | 做不了：{"、".join(DISP[k] for k in DEC_NO)}' if DEC_NO else ''))
    print('  算术分解（只进图注做对照）：'
          + '，'.join(f'{DISP[k]} 量{DECOMP[k]["vol_ar"]:+.2f}pp 价{DECOMP[k]["prc_ar"]:+.2f}pp '
                      f'（交叉项{DECOMP[k]["cross"]:+.2f}pp = 总增长的 '
                      f'{abs(DECOMP[k]["cross"] / DECOMP[k]["gV"]) * 100:.1f}%）' for k in DEC_OK)
          + f' | 两法最大差 {_ar_dev:.2f}pp')
    print('  跨页对账（单公司页的交易日加权口径）：'
          + '，'.join(f'{DISP[k]} 量{DEC_DW[k]["vol"]:+.2f}pp 价{DEC_DW[k]["prc"]:+.2f}pp '
                      f'= 总{DEC_DW[k]["gV"]:+.2f}%' for k in DEC_OK))
    print(f'分解自检：三道恒等式最大残差 {DEC_ID_MAXERR:.3e}pp ✓（阈值 1e-9）| '
          f'汇率不变性最大偏差 {DEC_FX_MAXDEV:.3e}pp ✓（本币 vs 定基美元两条路各算一遍）| '
          f'权重分母 |ln(额比)| 最小 {DEC_LNV_MIN:.4f} ✓（下限 {LOGW_EPS}）| '
          f'等权 vs 日加权 {DEC_DW_DEV:.2f}pp')
    print(f'写出 {shell}')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
