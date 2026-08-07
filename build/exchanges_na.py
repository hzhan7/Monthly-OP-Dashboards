# -*- coding: utf-8 -*-
"""北美交易所竞争页（ICE/NYSE · Cboe · MIAX · Nasdaq，TMX/BOX 做对照）—— 写出 data/exchanges-na.js。

这一页与 build/exchanges.py（CME/Cboe/HKEX 横截面）解决的不是同一个问题。那一页只能问
「谁在跑赢」，因为它的三家没有公约分母，比较只能靠指数化与同比。**本页有分母。**
全仓十二家交易所里，只有北美这两个池能拿到**官方发布的行业总量**：

  · 美股现货：`series/ice.csv` 的 `adv_tapeA/B/C_consolidated_mnsh`
    —— Tape A/B/C 的**全市场合并成交量**（含场外 TRF 内化），ICE 在自己的月度
    metrics 里逐月披露。三条相加就是全美股票市场的分母。
  · 美股股票/ETF 期权：`series/ice.csv` 的 `adv_us_equity_options_industry_kcontracts`
    与 `series/miax.csv` 的 `industry_adv_options_kcontracts` —— 两家公司**各自独立**
    披露的同一个行业口径（OCC equity & ETF options），本页实测两列在全部重叠月**逐位相同**。

有了分母，本页算的就不是「成员之和里的占比」（那种占比里，一家退出会让其余各家的
「份额」凭空上升），而是**真份额** = 该家撮合量 ÷ 官方行业总量。差别不是修辞：
2026-07 四家交易所集团合计只撮合了全美现货成交的 43.4%，剩下的 56.6% 主要是场外内化 ——
若按「四家之和」算占比，这 56.6% 会被整个抹掉，NYSE 会从 19.1% 变成 44.0%。

━━ 为什么这一页的可信度可以硬证明 ━━
`series/ice.csv` 里同时躺着 ICE **自己算好的份额**（`share_nyse_tapeA/B/C_matched`、
`share_nyse_us_cash_matched`、`share_nyse_equity_options`）。它们不是数据，是**答案**：
本页用自己的分子分母算一遍，再与这些答案逐月逐位比对。对不上就说明本页的份额算法
与交易所自己的算法不是同一件事，那么本页所有份额图都不可信 —— 这是全站唯一一页
能把「我算得对不对」变成可复算证据的页，所以对账结果进页面正文（Exhibit 13 + 对账表 +
口径说明），不藏在注释里。

四条独立锚点（全部在本文件里实测，数字由代码算出后填进文案，不写死）：
  A. ICE 自报份额 vs 本页自算（同一家公司的分子分母）—— 187 个月
  B. MIAX 自报的行业分母 vs ICE 自报的行业分母（两家公司互不相干的独立披露）
  C. Nasdaq 自报的季度美股期权市占 vs 本页用 ICE 分母 + Nasdaq 月度量现算
  D. TMX 自报的 BOX 全美股票期权市占（整数）vs 本页用 ICE 分母现算

━━ 主口径：定基名义额（本页是它的退化情形，且这一点本身是结论）━━
全站主口径是定基名义额 = 张数 × 乘数 × 2019-01 基期价格（汇率同锁 2019-01）。
理由是「张数」不可跨产品比较：乘数是交易所自选的产品设计。同一份 JPX 序列，
本文件实测 2016-06 → 2026-06 的**原始张数 +50.5%**、而**大合约当量 −26.0%** —— 符号相反。

**北美这两个池是这条规矩的退化情形，因为池内规格完全统一：**
多重挂牌股票/ETF 期权全行业统一 100 股/张（`series/contract_specs.csv` 的
`US_MULTILIST_EQ_OPT` 行已登记此惯例）；现货池的计量单位本来就是股。
乘数与基期价格对池内每一家都是**同一个常数** ⇒ 份额与增长率在两种口径下**恒等**。
所以本页把两种口径都算出来画在同一张图上（Exhibit 10），两条曲线必须完全重合；
不重合就是换算链坏了，本文件直接抛异常而不是画一张好看的图。

📌 已知缺口（不掩饰）：`contract_specs.csv` 的 `US_MULTILIST_EQ_OPT` 与
`US_CASH_EQUITY_SHARE` 两行的 `base_price_local` 都是空的（2019-01 的成交量加权标的
均价 / 全美平均成交价，官方单一字段未找到）。所以本页的名义额只能报到**股当量**
（张数 × 100 股），报不出美元水平值。这不影响本页任何结论 —— 份额与增长率与那个
常数无关，见 Exhibit 10 的实测校验。

━━ 发布门槛 ━━
四家的月度披露都快：2026-07 那一期 ICE / Cboe / MIAX / Nasdaq **同为 2026-08-05 发布**
（见 series/source_dates.csv），即月末后第 5 天。所以本页门槛取四家的共同最新月，
不会被慢成员拖住。成员没齐就打印原因并以**退出码 0** 正常结束（与 exchanges.py 同规矩）。

数据源（只读 series/*.csv）：
  series/ice.csv          ICE 月度 metrics：行业分母 + NYSE Group 撮合量 + ICE 自报份额
  series/cboe.csv         Cboe 月度成交统计：multi-list 期权 ADV、美股 matched 股数
  series/miax.csv         MIAX IR Volume & RPC 报表 + 官网市占 API
  series/ndaq.csv         Nasdaq IR Monthly Reporting Sheet + nasdaqtrader 市占 xlsx
  series/ndaq_q.csv       Nasdaq 季度面板（自报美股期权市占，做锚点 C）
  series/tmx_box_q.csv    TMX 季度 MD&A 的 BOX 表（做锚点 D）
  series/jpx.csv          只用来实测一句对照（原始张数 vs 大合约当量，符号相反）
  series/contract_specs.csv  合约规格（乘数 / 基期价格），只读
  series/fx.csv           本页两个池全部以美元计价，不做任何汇率换算（读它只为留证）

用法: python3 build/exchanges_na.py    （可重复跑，除首行日期外逐字节相同）
"""
import os
import re
import sys

import numpy as np
import pandas as pd

import axisfmt
import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
# 目录名 = data 文件名 = payload 的 ticker，三者必须逐字相同：
# 页面外壳（build/make_shells12.py）写死的是 `../data/<目录名>.js`，而目录名由本页的 URL
# 定死成带连字符的 `exchanges-na`；page.js 的导航高亮判的也是 `D.ticker === 目录名`。
# 本文件名只能用下划线（Python 模块名不许带连字符），但**输出物必须用连字符** ——
# 早先写成 exchanges_na.js，页面引用 exchanges-na.js 直接 404，页面只显示「缺少 data/*.js」。
# build/pools.py 各池的 'page' 字段用的同样是 'exchanges-na'。
OUT = os.path.join(ROOT, 'data', 'exchanges-na.js')

TICKER = 'exchanges-na'
SRC = ('Source: ICE, Cboe, MIAX, Nasdaq monthly volume disclosures; TMX quarterly MD&A; '
       'format after Goldman Sachs GIR')

# 成员固定配色：一家一色，全页所有图一致。RED 是断点与截轴离群值的专用色，不做数据色。
NYSE_C, CBOE_C, NDAQ_C, MIAX_C = 'NAVY', 'BLUE', 'MBLUE', 'GOLD'
OTHER_C = 'GRAY'      # 残差桶（BOX/MEMX；现货还含场外内化）
CHK_C = 'GREEN'       # 校验线专用

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
HEAT_YEARS = 8
TBL_MONTHS = 13
MIN_COMMON = 13        # 共同历史短于这么多个月就不发（起止对照与 13 个月核对表都成立不了）
SHARES_PER_CONTRACT = 100.0   # 见 contract_specs.csv 的 US_MULTILIST_EQ_OPT 行
EPS = 1e-9             # 换算链一致性的相对容差


# ────────────────────────────── 通用零件 ──────────────────────────────
def mlab(p):
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
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
    """比率类指标的差异一律 pp/bp（契约 §2）：|v| < 1pp 时写 bp。"""
    if v is None or not np.isfinite(v):
        return '—'
    if abs(_z(v, dec)) < 1:
        return f'{_z(v * 100, 0):+,.0f}bp'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None，线在缺口处断开而不是直连）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def skip(msg):
    """成员没齐 —— 打印原因，退出码 0（见模块 docstring 的发布门槛一节）。"""
    print(f'{TICKER}: 跳过，未达发布门槛 —— {msg}')
    print('横截面页只在成员齐了之后生成；下次例行跑会自动重试。')
    sys.exit(0)


def nice_max(v):
    """给右轴上界取一个整数刻度（stacked_dual 的右轴强制 0 起，只能调上界）。"""
    if v <= 0:
        return 1
    step = 10 ** int(np.floor(np.log10(v)))
    for k in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if v <= k * step:
            return int(k * step) if k * step >= 1 else k * step
    return int(10 * step)


# ────────────────────────────── 1. 读数据 ──────────────────────────────
def read_csv(name, index='month', freq='M'):
    """series/<name> → 以连续月度 PeriodIndex 索引的 DataFrame（全列转数值）。

    reindex 成连续月：原始文件若中间缺月，pct_change(12) 会按**位置**移 12 行，
    算出来的「同比」其实跨了 13 个月而完全看不出来。
    """
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if index not in d.columns:
        raise SystemExit(f'series/{name} 缺 {index} 列')
    d[index] = pd.PeriodIndex(d[index], freq=freq)
    d = d.set_index(index).sort_index()
    d = d.apply(pd.to_numeric, errors='coerce')
    return d.reindex(pd.period_range(d.index[0], d.index[-1], freq=freq))


RAW = {k: read_csv(f'{k}.csv') for k in ('ice', 'cboe', 'ndaq', 'miax', 'jpx')}
for _k, _d in RAW.items():
    if _d is None:
        skip(f'缺 series/{_k}.csv')

# 美股交易日历：ICE 与 Nasdaq 各自披露一份，实测 186 个重叠月里只有 1 个月不同
# （2015-08），MIAX 那份与 ICE 全等。全页统一用 ICE 那一列当唯一日历 ——
# 两份日历混用会让「同一个月的 ADV」按不同分母算出两个值，而差异小到没人会发现。
DAYS = RAW['ice']['trading_days_us_equities']

# ── 季度表（BOX 对照 + Nasdaq 自报市占锚点）──
BOXQ = pd.read_csv(os.path.join(SERIES, 'tmx_box_q.csv')) \
    if os.path.exists(os.path.join(SERIES, 'tmx_box_q.csv')) else None
NDQ = pd.read_csv(os.path.join(SERIES, 'ndaq_q.csv')) \
    if os.path.exists(os.path.join(SERIES, 'ndaq_q.csv')) else None

# ── 合约规格（只读，用来证明「基期价格这一格是空的」而不是拍脑袋跳过）──
SPECS = pd.read_csv(os.path.join(SERIES, 'contract_specs.csv'))


def spec_row(pid):
    r = SPECS[SPECS['product_id'] == pid]
    return None if r.empty else r.iloc[0]


def base_price_of(pid):
    """规格表里的基期价格；空着就返回 None（调用方必须显式处理，不许静默变 NaN）。"""
    r = spec_row(pid)
    if r is None:
        return None
    v = pd.to_numeric(pd.Series([r.get('base_price_local')]), errors='coerce').iloc[0]
    return float(v) if np.isfinite(v) else None


OPT_SPEC_ID, CASH_SPEC_ID = 'US_MULTILIST_EQ_OPT', 'US_CASH_EQUITY_SHARE'
OPT_P0 = base_price_of(OPT_SPEC_ID)
CASH_P0 = base_price_of(CASH_SPEC_ID)


# ────────────────────────── 2. 池定义与换算链 ──────────────────────────
# 每个成员声明一条**完整的换算链**：源列 → 单位换算 → （必要时）除交易日 → 规范单位。
# 各家源列的口径不同（ICE/Cboe/MIAX 直接给 ADV，Nasdaq 给月度总量），链在这里显式写出，
# 是为了让「张数口径」与「定基名义额口径」走同一条链的前半段 —— Exhibit 10 的互校验
# 只有在两条口径共用前半段、只在末端分叉时才有意义。
class Member(object):
    def __init__(self, key, disp, src, col, unit, color, per_day=False, alt=None, note='',
                 short=None):
        self.key, self.disp, self.src, self.col = key, disp, src, col
        self.unit, self.color, self.per_day, self.alt, self.note = unit, color, per_day, alt, note
        # short 只用于**类别轴**（起止对照 / Δ / 桥 / 同月）：类别轴现在一律水平排
        # （`xrot: 0`，见下面四个 builder 的注释），标签必须窄于自己那一格 band，
        # 否则会与左右邻居横向压字。图例与图注仍用全名。
        self.short = short or disp

    def series(self):
        d = RAW[self.src]
        if self.col not in d.columns:
            raise SystemExit(f'series/{self.src}.csv 缺列 {self.col}')
        s = d[self.col]
        if self.alt:
            if self.alt not in d.columns:
                raise SystemExit(f'series/{self.src}.csv 缺列 {self.alt}')
            s = s.combine_first(d[self.alt])       # 主列缺月才回落到备列
        s = s * self.unit
        if self.per_day:
            s = s / DAYS.reindex(s.index)
        return s


# ── 池 A：北美多重挂牌股票/ETF 期权（规范单位 = 张/日）──
OPT_MEMBERS = [
    Member('nyse', 'NYSE (ICE)', 'ice', 'adv_nyse_equity_options_kcontracts', 1e3, NYSE_C,
           short='NYSE',
           note='NYSE Arca + NYSE American 两个期权盘口，ICE 月度 metrics 直接给 ADV（千张/日）'),
    Member('cboe', 'Cboe', 'cboe', 'adv_multilist_options_kcontracts', 1e3, CBOE_C,
           note='Cboe 四个期权盘口的 multiply-listed 段，官方与 index options 分列，本池只取前者'),
    Member('ndaq', 'Nasdaq', 'ndaq', 'vol_us_options_mmcontracts', 1e6, NDAQ_C, per_day=True,
           note='Nasdaq 六所（NOM/PHLX/ISE/GEMX/MRX/NTX）合计，官方给<b>当月总张数</b>，'
                '本页除以美股交易日数换成 ADV'),
    Member('miax', 'MIAX', 'miax', 'adv_multilist_options_kcontracts', 1e3, MIAX_C,
           note='MIAX 四所（MIAX/Pearl/Emerald/Sapphire）合计，取 IR 报表口径'),
]
OPT_DENOM = Member('ind', '行业总量', 'ice', 'adv_us_equity_options_industry_kcontracts',
                   1e3, OTHER_C)

# ── 池 B：美股现货 matched（规范单位 = 股/日）──
CASH_MEMBERS = [
    Member('nyse', 'NYSE Group (ICE)', 'ice', '__nyse_cash__', 1e6, NYSE_C,
           short='NYSE Group',
           note='Tape A+B+C 的 matched 股数之和（NYSE/Arca/American/National/Texas）。'
                '<b>不用 handled</b> —— handled 含路由到别家成交的量，其余三家不披露对应口径'),
    Member('ndaq', 'Nasdaq', 'ndaq', 'vol_us_cash_matched_mnsh', 1e6, NDAQ_C, per_day=True,
           alt='__ndaq_venues__',
           note='Nasdaq + NTX（原 BX）+ PSX 三个盘口撮合量。IR 报表给当月总量（2025-01 起），'
                '更早的月份回落到 nasdaqtrader 市占 xlsx 的三个盘口分列相加'),
    Member('cboe', 'Cboe', 'cboe', 'adv_us_equities_matched_shares_bn', 1e9, CBOE_C,
           note='Cboe 四个美股盘口（BZX/BYX/EDGA/EDGX）的 matched 股数，官方单位是十亿股/日'),
    Member('miax', 'MIAX Pearl', 'miax', 'adv_equities_api_mnshares', 1e6, MIAX_C,
           note='MIAX Pearl Equities，取官网市占 API（2020-12 起，全精度）；'
                'IR 报表那一列只给整数，本页用它做交叉核对'),
]
CASH_DENOM = Member('cons', '合并成交量', 'ice', '__cash_cons__', 1e6, OTHER_C)

# ICE 那三条 tape 需要先加总再进链 —— 官方没有「三个 tape 合计」这一行，
# 但它才是与 Cboe / Nasdaq / MIAX 的 matched 口径对得上的那个数（见 docs/verify/ice.md）。
_ice = RAW['ice']
for _t, _dst in (('matched', '__nyse_cash__'), ('consolidated', '__cash_cons__')):
    _cols = ([f'adv_nyse_tape{x}_matched_mnsh' for x in 'ABC'] if _t == 'matched'
             else [f'adv_tape{x}_consolidated_mnsh' for x in 'ABC'])
    for _c in _cols:
        if _c not in _ice.columns:
            skip(f'series/ice.csv 缺列 {_c}')
    _ice[_dst] = _ice[_cols].sum(axis=1, min_count=len(_cols))
_nd = RAW['ndaq']
_vcols = ['vol_us_cash_matched_nasdaq_sh', 'vol_us_cash_matched_ntx_sh', 'vol_us_cash_matched_psx_sh']
if all(c in _nd.columns for c in _vcols):
    # 三个盘口是**股数**、IR 那列是**百万股**，先统一到百万股再进 Member.unit
    _nd['__ndaq_venues__'] = _nd[_vcols].sum(axis=1, min_count=len(_vcols)) / 1e6
else:
    skip('series/ndaq.csv 缺盘口分列')


class Pool(object):
    """一个池 = 成员 + 官方分母 + 单位标签 + 规格（乘数 / 基期价格）。"""

    def __init__(self, pid, zh_name, en_name, members, denom, spec_id, base_price,
                 unit_div, unit_lab, unit_lab_en, mult, mult_lab,
                 other_lab, other_short, other_en):
        self.pid, self.zh, self.en = pid, zh_name, en_name
        self.members, self.denom = members, denom
        self.spec_id, self.base_price = spec_id, base_price
        self.unit_div, self.unit_lab, self.unit_lab_en = unit_div, unit_lab, unit_lab_en
        self.mult, self.mult_lab = mult, mult_lab
        # other_lab 进图注（要说清楚里面是什么），other_short 进抬头（一行数据条塞不下长名）
        self.other_lab, self.other_short, self.other_en = other_lab, other_short, other_en
        self.build()

    def build(self):
        cols = {m.key: m.series() for m in self.members}
        cols['pool'] = self.denom.series()
        df = pd.DataFrame(cols)
        ok = df.dropna(how='any')
        if ok.empty:
            skip(f'{self.zh}：没有任何一个月四家成员与分母同时有值')
        idx = pd.period_range(ok.index[0], ok.index[-1], freq='M')
        holes = [str(p) for p in idx if p not in ok.index]
        if holes:
            # 共同窗口内有洞 = 源数据坏了，不是「成员没齐」——必须响，不能静默画带洞的份额
            raise SystemExit(f'{self.pid} 共同窗口 {idx[0]}–{idx[-1]} 内缺月：{holes}')
        self.df = ok.reindex(idx)
        self.idx = idx
        keys = [m.key for m in self.members]
        self.df['sum4'] = self.df[keys].sum(axis=1)
        self.df['other'] = self.df['pool'] - self.df['sum4']
        neg = [str(p) for p in idx if self.df['other'][p] < 0]
        if neg:
            # 成员之和超过官方行业总量 = 分子分母口径不一致，结论全部作废
            raise SystemExit(f'{self.pid} 成员之和超过官方分母：{neg}')
        for k in keys + ['sum4', 'other']:
            self.df[k + '_s'] = self.df[k] / self.df['pool'] * 100.0
        # 池总量同比在**分母自己的完整历史**上算，再截窗口 —— 先截再算会把已有历史扔掉
        self.pool_yoy = (self.denom.series().pct_change(12) * 100).reindex(idx)

    # ── 定基名义额：与张数口径共用前半段链，只在末端乘规格常数 ──
    def notional(self, key):
        """成员的定基名义额序列。基期价格缺席时退到「标的当量」（张数 × 乘数）。

        乘数与基期价格对池内每一家都是同一个常数，所以份额与增长率两种口径恒等 ——
        Exhibit 10 就是拿这一点当换算链的自检。
        """
        k = self.mult * (self.base_price if self.base_price is not None else 1.0)
        return self.df[key] * k

    @property
    def start(self):
        return self.idx[0]

    @property
    def end(self):
        return self.idx[-1]


# ────────────────────────────── 3. 发布门槛 ──────────────────────────────
# 门槛只看两个池的头条序列（各成员的成交量列 + 官方分母），其余列迟发不该拖住整页。
missing, latest_each = [], {}
for _tag, _mem in ([('opt', m) for m in OPT_MEMBERS] + [('opt', OPT_DENOM)] +
                   [('cash', m) for m in CASH_MEMBERS] + [('cash', CASH_DENOM)]):
    try:
        s = _mem.series().dropna()
    except SystemExit as e:
        missing.append(str(e))
        continue
    if s.empty:
        missing.append(f'{_tag}/{_mem.disp}（{_mem.col} 没有任何有效值）')
        continue
    latest_each[(_tag, _mem.key)] = s.index[-1]
if missing:
    skip('成员未就绪：' + '；'.join(missing))

POOL_OPT = Pool('opt', '北美多重挂牌股票 / ETF 期权', 'U.S. multiply-listed equity & ETF options',
                OPT_MEMBERS, OPT_DENOM, OPT_SPEC_ID, OPT_P0,
                1e3, '千张/日', 'k contracts/day', SHARES_PER_CONTRACT, '100 股/张',
                '其他交易所（BOX / MEMX 等）', '其他所',
                'Other exchanges (BOX / MEMX etc.)')
POOL_CASH = Pool('cash', '美股现货 matched', 'U.S. cash equities, matched',
                 CASH_MEMBERS, CASH_DENOM, CASH_SPEC_ID, CASH_P0,
                 1e6, '百万股/日', 'mn shares/day', 1.0, '1 股/股',
                 '场外与其他（TRF 内化 / MEMX / IEX 等）', '场外与其他',
                 'Off-exchange & other')
POOLS = [POOL_OPT, POOL_CASH]

LATEST = min(p.end for p in POOLS)
for p in POOLS:
    if (p.end - p.start).n + 1 < MIN_COMMON:
        skip(f'{p.zh} 的共同历史只有 {(p.end - p.start).n + 1} 个月'
             f'（{mlab(p.start)} – {mlab(p.end)}），不足 {MIN_COMMON} 个月')
    if p.end != LATEST:
        # 两个池的最新月不同 —— 统一截到共同最新月，否则两个池的「本月」不是同一个月
        p.df = p.df.loc[:LATEST]
        p.idx = p.idx[p.idx <= LATEST]
        p.pool_yoy = p.pool_yoy.reindex(p.idx)
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12
# 各家自身的最新月（抬头与口径说明里要写出来，才看得出「有没有人跑在前面」）
AHEAD = sorted({(k, m) for (_t, k), m in latest_each.items() if m > LATEST})


# ══════════ 3b. 长历史分子 —— 起止/Δ/桥的 4 年窗口与季度份额图共用 ══════════
# 上面 Pool 的共同窗口是 `dropna(how='any')` 出来的：四家里任一家缺一个月，整个月作废。
# 期权池因此被 Nasdaq 卡在 19 个月（IR 的 Monthly Reporting Sheet 每月**原地覆盖**，
# 只含「上一整年 + 本年 YTD」，官网不留历史副本；OCC 的分交易所月度量 2026-08-07 实测
# 已挂 Cloudflare JS 挑战、marketdata 接口返 400，无人值守取不到）。
#
# 但份额本来不需要「四家齐全」：**分母是官方发布的**，每家可以各自独立除。
# 所以下面这套长历史分子给三类图用：
#   · 4 年同月窗口（起止对照 / Δ / 归因桥）—— 期初期末各取一个月，窗口由**分母**决定；
#   · 季度长历史份额 —— 短历史成员前段留 None 断线；
#   · 月份效应统计 —— 需要 12 个月齐全的完整年。
#
# MIAX 期权的深历史来自 miaxglobal.com 的 indsum API 四所分列（2015-04 起，
# docs/verify/miax.md 实测 136 个月无断档）。该文档同时给了口径顺序：
# **`adv_multilist_options_kcontracts`（IR 报表）为准，API 只用于 2025-01 之前回补**
# —— 因为 API 合计比报表稳定低 0.26%–0.32%。本文件照此拼接，并把实测落差写进图注；
# 拼接点落在两种口径都有的 19 个月里，落差换算成份额只有几个 bp（下面由代码算出）。
MIAX_OPT_API_COLS = ['adv_miax_options_api_kcontracts', 'adv_pearl_options_api_kcontracts',
                     'adv_emerald_options_api_kcontracts', 'adv_sapphire_options_api_kcontracts']
for _c in MIAX_OPT_API_COLS:
    if _c not in RAW['miax'].columns:
        skip(f'series/miax.csv 缺列 {_c}（长历史份额图需要 API 四所分列）')
# min_count=1：Pearl 2017-02、Emerald 2019-03、Sapphire 2024-08 才开业，
# 开业前那几列本来就该是空的，不能因此把整月作废。
MIAX_OPT_API = RAW['miax'][MIAX_OPT_API_COLS].sum(axis=1, min_count=1) * 1e3


def long_num(pool, m):
    """成员在**尽可能长**的历史上的分子序列（规范单位，与 Pool 用的完全同一条链）。

    只有期权池的 MIAX 多接一段 API 回补；其余成员的深历史本来就在源列里
    （现货池 Nasdaq 的 `alt` 回落已经在 Member.series() 内部做掉了）。
    """
    s = m.series()
    if pool.pid == 'opt' and m.key == 'miax':
        s = s.combine_first(MIAX_OPT_API)
    return s


LONG_NUM = {(p.pid, m.key): long_num(p, m) for p in POOLS for m in p.members}
LONG_DEN = {p.pid: p.denom.series() for p in POOLS}

_mx = [m for m in OPT_MEMBERS if m.key == 'miax'][0]
_ov = pd.DataFrame({'ir': _mx.series(), 'api': MIAX_OPT_API}).dropna()
MIAX_SPL_N = int(len(_ov))
MIAX_SPL_REL = float((_ov['api'] / _ov['ir'] - 1).abs().max()) * 100 if MIAX_SPL_N else np.nan
MIAX_SPL_BP = (float(((_ov['ir'] - _ov['api']) / LONG_DEN['opt'].reindex(_ov.index) * 1e4)
                     .abs().max()) if MIAX_SPL_N else np.nan)


# ────────────────────────── 4. 四条自校验锚点 ──────────────────────────
def _resid_pp(calc, official_frac):
    """自算份额（%）− 官方自报份额（already fraction 或 %）→ pp 残差序列。"""
    return (calc - official_frac).dropna()


def anchor_ice():
    """锚点 A：ICE 自报份额 vs 本页自算（同一家公司的分子与分母）。"""
    d, out = RAW['ice'], {}
    cons = {t: d[f'adv_tape{t}_consolidated_mnsh'] for t in 'ABC'}
    for t in 'ABC':
        calc = d[f'adv_nyse_tape{t}_matched_mnsh'] / cons[t] * 100.0
        out[f'tape{t}'] = _resid_pp(calc, d[f'share_nyse_tape{t}_matched'] * 100.0)
    calc = d['__nyse_cash__'] / d['__cash_cons__'] * 100.0
    out['cash'] = _resid_pp(calc, d['share_nyse_us_cash_matched'] * 100.0)
    out['cash_calc'] = calc
    calc_o = (d['adv_nyse_equity_options_kcontracts'] /
              d['adv_us_equity_options_industry_kcontracts'] * 100.0)
    out['opt'] = _resid_pp(calc_o, d['share_nyse_equity_options'] * 100.0)
    return out


def anchor_miax():
    """锚点 B：MIAX 自报的行业分母 vs ICE 自报的行业分母（两家完全独立的披露）。"""
    m, i = RAW['miax'], RAW['ice']
    opt = pd.DataFrame({'m': m['industry_adv_options_kcontracts'],
                        'i': i['adv_us_equity_options_industry_kcontracts']}).dropna()
    eq = pd.DataFrame({'m': m['industry_adv_equities_mnshares'],
                       'i': i['__cash_cons__']}).dropna()
    # MIAX 自报的两个份额（官方只给 1 位小数）vs 本页用 ICE 分母现算
    s_opt = _resid_pp(m['adv_multilist_options_kcontracts'] /
                      i['adv_us_equity_options_industry_kcontracts'] * 100.0,
                      m['share_multilist_options_pct'])
    s_eq = _resid_pp(m['adv_equities_mnshares'] / i['__cash_cons__'] * 100.0,
                     m['share_equities_pct'])
    api = pd.DataFrame({'api': m['adv_equities_api_mnshares'],
                        'pdf': m['adv_equities_mnshares']}).dropna()
    return {
        'opt_n': len(opt), 'opt_same': int((opt['m'] == opt['i']).sum()),
        'opt_maxabs': float((opt['m'] - opt['i']).abs().max()) if len(opt) else np.nan,
        'eq_n': len(eq),
        'eq_maxrel': float(((eq['m'] - eq['i']).abs() / eq['i']).max()) if len(eq) else np.nan,
        'share_opt': s_opt, 'share_eq': s_eq,
        'api_n': len(api),
        'api_maxabs': float((api['api'] - api['pdf']).abs().max()) if len(api) else np.nan,
    }


def _qkey(p):
    return f'{p.year}Q{(p.month - 1) // 3 + 1}'


def anchor_ndaq():
    """锚点 C：Nasdaq 自报的季度美股期权市占 vs 本页用 ICE 分母 + Nasdaq 月度量现算。"""
    if NDQ is None or 'q_share_us_options_matched' not in NDQ.columns:
        return None
    ind_m = (RAW['ice']['adv_us_equity_options_industry_kcontracts'] * DAYS / 1e3)   # 百万张/月
    nd_m = RAW['ndaq']['vol_us_options_mmcontracts']
    both = pd.DataFrame({'ind': ind_m, 'nd': nd_m}).dropna()
    g = both.groupby([_qkey(p) for p in both.index])
    full = g.size()[g.size() == 3].index                    # 只认三个月齐全的季度
    agg = g.sum().loc[full]
    rows = []
    for _, r in NDQ.iterrows():
        q = str(r['quarter']).replace('-', '')
        if q not in agg.index or not np.isfinite(r['q_share_us_options_matched']):
            continue
        calc = agg.loc[q, 'nd'] / agg.loc[q, 'ind'] * 100.0
        rows.append((q, float(r['q_share_us_options_matched']) * 100.0, float(calc),
                     float(agg.loc[q, 'nd']), float(r['q_us_options_mmcontracts'])))
    return rows


def anchor_box():
    """锚点 D：TMX 自报的 BOX 全美股票期权市占（整数）vs 本页用 ICE 分母现算。"""
    if BOXQ is None or 'box_equity_options_share_pct' not in BOXQ.columns:
        return None
    ind_m = (RAW['ice']['adv_us_equity_options_industry_kcontracts'] * DAYS / 1e3)
    s = ind_m.dropna()
    g = s.groupby([_qkey(p) for p in s.index])
    full = g.size()[g.size() == 3].index
    agg = g.sum().loc[full]
    rows = []
    for _, r in BOXQ.iterrows():
        q = str(r['quarter']).replace('-', '')
        if q not in agg.index or not np.isfinite(r['box_equity_options_share_pct']):
            continue
        calc = float(r['box_volume_mncontracts']) / float(agg.loc[q]) * 100.0
        rows.append((q, float(r['box_equity_options_share_pct']), calc,
                     float(r['box_volume_mncontracts'])))
    return rows


A_ICE = anchor_ice()
A_MIAX = anchor_miax()
A_NDAQ = anchor_ndaq()
A_BOX = anchor_box()

# 锚点 A 的判定：官方把分子、分母、份额三者都印成有限位数（股数取整到百万股、
# 份额取到小数点后 3 位），所以残差不可能恒为 0；能要求的是「残差全部小于官方
# 那一位的舍入量级」。数字由代码算出，不写死。
A_CASH_MAX = float(A_ICE['cash'].abs().max())
A_CASH_N = int(len(A_ICE['cash']))
A_CASH_EXACT = int((A_ICE['cash'].abs().round(4) < 0.0005).sum())
A_CASH_R3 = int(((A_ICE['cash_calc'] / 100).round(3) ==
                 RAW['ice']['share_nyse_us_cash_matched']).sum())
A_OPT_MAX = float(A_ICE['opt'].abs().max())
A_OPT_N = int(len(A_ICE['opt']))
A_TAPE_MAX = max(float(A_ICE[f'tape{t}'].abs().max()) for t in 'ABC')
if A_CASH_MAX > 0.5 or A_OPT_MAX > 0.5:
    # 半个百分点以上的偏离不是舍入，是算法与交易所不是同一件事 —— 必须响
    raise SystemExit(f'自校验失败：与 ICE 自报份额的残差过大（现货 {A_CASH_MAX:.3f}pp、'
                     f'期权 {A_OPT_MAX:.3f}pp），本页份额口径与 ICE 不一致，拒绝出页')

NDAQ_MAX = max(abs(c - o) for _q, o, c, _v, _v2 in A_NDAQ) if A_NDAQ else np.nan
NDAQ_N = len(A_NDAQ) if A_NDAQ else 0
BOX_N = len(A_BOX) if A_BOX else 0
BOX_HIT = sum(1 for _q, o, c, _v in A_BOX if round(c) == round(o)) if A_BOX else 0
MIAX_S_OPT_MAX = float(A_MIAX['share_opt'].abs().max())
MIAX_S_EQ_MAX = float(A_MIAX['share_eq'].abs().max())


# ────────────────── 5. 定基名义额 vs 原始计数的换算链自检 ──────────────────
def notional_check(pool):
    """两种口径的份额与指数必须逐月相等；不等就是换算链坏了 → 抛异常。"""
    keys = [m.key for m in pool.members] + ['other']
    tot_c = pool.df['pool']
    tot_n = pool.notional('pool')
    d_share, d_ratio = 0.0, 0.0
    for k in keys:
        sc = pool.df[k] / tot_c * 100.0
        sn = pool.notional(k) / tot_n * 100.0
        d_share = max(d_share, float((sc - sn).abs().max()))
        r = (pool.notional(k) / pool.df[k]).replace([np.inf, -np.inf], np.nan).dropna()
        kk = pool.mult * (pool.base_price if pool.base_price is not None else 1.0)
        if len(r):
            d_ratio = max(d_ratio, float((r / kk - 1).abs().max()))
    ic = tot_c / float(tot_c.iloc[0]) * 100.0
    inn = tot_n / float(tot_n.iloc[0]) * 100.0
    d_idx = float((ic - inn).abs().max())
    if d_share > 1e-9 or d_idx > 1e-9 or d_ratio > EPS:
        raise SystemExit(
            f'{pool.pid} 换算链自检失败：份额差 {d_share:.3e}pp、指数差 {d_idx:.3e}、'
            f'单位乘数偏离 {d_ratio:.3e} —— 池内规格本应统一，两种口径必须恒等')
    return ic, inn, d_share, d_idx, d_ratio


OPT_IC, OPT_IN, OPT_DSHARE, OPT_DIDX, OPT_DRATIO = notional_check(POOL_OPT)
CASH_IC, CASH_IN, CASH_DSHARE, CASH_DIDX, CASH_DRATIO = notional_check(POOL_CASH)

# 反面对照（实测，不引用别处的说法）：JPX 的原始张数与大合约当量在同一段窗口里符号相反。
_jr, _jl = RAW['jpx']['adv_deriv_total_raw_kcontracts'], RAW['jpx']['adv_deriv_total_lgeq_kcontracts']
_j = pd.DataFrame({'raw': _jr, 'lge': _jl}).dropna()
JPX_TXT = ''
if len(_j) >= 121:
    _e, _s = _j.index[-1], _j.index[-1] - 120
    if _s in _j.index:
        JPX_TXT = (f'JPX 衍生品 {mlab(_s)} → {mlab(_e)}：原始张数 '
                   f'{pct(_j["raw"][_e] / _j["raw"][_s] * 100 - 100)}、'
                   f'大合约当量 {pct(_j["lge"][_e] / _j["lge"][_s] * 100 - 100)}')


# ────────────────────────────── 6. Exhibit 1：汇总表 ──────────────────────────────
def ser_of(s):
    """pandas Series → pctile.py 吃的「按月升序、缺失为 None」的 float 列表。"""
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


SUM_ROWS = []
for _p in POOLS:
    SUM_ROWS.append(('group', f'{_p.zh} —— 分母 = {_p.denom.disp}（官方披露，{_p.unit_lab}）',
                     None, None, None))
    SUM_ROWS.append(('row', f'行业分母（{_p.unit_lab}）', (_p, 'pool', _p.unit_div), 0, 'num'))
    for _m in _p.members:
        SUM_ROWS.append(('row', f'{_m.disp} 真份额（%）', (_p, _m.key + '_s', 1.0), 2, 'share'))
    SUM_ROWS.append(('row', '四家合计真份额（%）', (_p, 'sum4_s', 1.0), 2, 'share'))
    SUM_ROWS.append(('row', f'{_p.other_lab}（%）', (_p, 'other_s', 1.0), 2, 'share'))
SUM_ROWS.append(('group', '池总量增长（% y/y，分母自己的口径）', None, None, None))
SUM_ROWS.append(('row', '期权行业 ADV', (POOL_OPT, '__yoy__', 1.0), 1, 'growth'))
SUM_ROWS.append(('row', '现货合并成交量 ADV', (POOL_CASH, '__yoy__', 1.0), 1, 'growth'))


def _row_series(spec):
    pool, col, div = spec
    s = pool.pool_yoy if col == '__yoy__' else pool.df[col] / div
    return s.reindex(pd.period_range(min(x.start for x in POOLS), LATEST, freq='M'))


def summary():
    rows, blank_why = [], []
    for kind, label, spec, dec, mode in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        s = _row_series(spec)
        c = float(s.get(CUR, np.nan))
        p1 = float(s.get(PRV, np.nan))
        p12 = float(s.get(YAG, np.nan))
        if mode == 'num':
            mm = (c / p1 - 1) * 100 if np.isfinite(p1) and p1 else np.nan
            yy = (c / p12 - 1) * 100 if np.isfinite(p12) and p12 else np.nan
            dm, dy = pct(mm), pct(yy)
        else:                                   # 比率类：差异一律 pp/bp（契约 §2）
            mm = c - p1 if np.isfinite(c) and np.isfinite(p1) else np.nan
            yy = c - p12 if np.isfinite(c) and np.isfinite(p12) else np.nan
            dm, dy = pp(mm), pp(yy)
        cells = [{'v': lvl(c, dec, mode)}, {'v': lvl(p1, dec, mode)}, {'v': lvl(p12, dec, mode)},
                 {'v': dm, 'cls': cls_of(mm)}, {'v': dy, 'cls': cls_of(yy)}]
        ser = ser_of(s.dropna())
        txt_, cls_ = pctile.cell(ser)
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label, pctile.why_blank(ser)))
        rows.append({'label': label, 'cells': cells})
    blank_txt = ('本轮留空：' + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    return {
        'title': f'北美两个池 —— {mlab(CUR)}（四家共同最新月）',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('<b>份额是真份额</b>：分子 = 该家自己披露的撮合量，分母 = 官方披露的行业总量'
                 f'（期权 {num(float(POOL_OPT.df["pool"][CUR]) / 1e3)} 千张/日、'
                 f'现货 {num(float(POOL_CASH.df["pool"][CUR]) / 1e6)} 百万股/日，'
                 f'均为 {mlab(CUR)}），<b>不是四家之和里的占比</b>。'
                 '两者差别很大：现货池四家合计只占 '
                 f'{POOL_CASH.df["sum4_s"][CUR]:.1f}%，若按四家之和当分母，'
                 f'NYSE Group 会从 {POOL_CASH.df["nyse_s"][CUR]:.1f}% 变成 '
                 f'{POOL_CASH.df["nyse_s"][CUR] / POOL_CASH.df["sum4_s"][CUR] * 100:.1f}%。'
                 '占比类指标的变化一律用 pp/bp（绝对值不足 1pp 时写 bp），水平值的变化用百分比。'
                 '3Y %ile 由全站唯一实现 <code>build/pctile.py</code> 给出：'
                 '回放最近 24 个月，若 ≥70% 的月份分位都钉在 100 或 0，该行留空。' + blank_txt),
    }


# ────────────────────────────── 7. Exhibit 2..N ──────────────────────────────
ex = []
XL_OPT = [mlab(p) for p in POOL_OPT.idx]
XL_CASH = [mlab(p) for p in POOL_CASH.idx]
LONG_IDX = pd.period_range(max(RAW['ice'].index[0], pd.Period('2011-01', 'M')), LATEST, freq='M')
XL_LONG = [mlab(p) for p in LONG_IDX]

# ── 类别轴（x 是公司名而不是月份）一律水平排 ──
# 引擎对 ≤20 个类目的 x 标签默认 45°（charts.js:521），并只给底部留 XB = 36px。
# 45° + anchor='end' 的几何是：文字**从锚点往左下方铺开**，向下伸出 0.707 × 文字宽度，
# 锚点自己在 M.t+ph+9，于是文字宽超过 (36−9)/0.707 ≈ 38px 就伸到 SVG 画布外面去。
# 实测（1:1 截图 + getBoundingClientRect）：「NYSE Group」49px ⇒ 越界 8px、
# 「Deutsche Börse」61px ⇒ 越界 16px，落在下方 Note 正文上，字压字。
# 水平排（xrot: 0）时引擎改用 XB = 22px、anchor='middle'、不旋转，文字只向下伸约 2px，
# **不可能越界**；代价是相邻标签会横向相碰，所以约束变成「标签宽 < 自己那一格 band」。
# 本页类别轴最多 6 格：半栏 band ≈ 84–100px、通栏 ≈ 183–220px，最宽的「NYSE Group」49px，
# 余量至少 34px。姊妹页 exchanges_eu / exchanges_apac 的同类图本来就是 xrot: 0，
# 这里改过来顺带把三张横截面页的类别轴版式统一了。
CAT_XROT = 0

# ── 图号：符号引用，不写死数字 ─────────────────────────────────────────────
# 正文里到处是「见 Exhibit 13」这种交叉引用。以前它们是硬编码的整数，删一张图就得
# 手工改十几处散文 —— 而漏改**不报错**，读者点过去看到的是另一张图。
# 现在一律写 `X('selfcheck')`，落成占位符 `§selfcheck§`，全部图追加完之后由
# `subst_refs()` 统一替换成真数字；引用了不存在的图 id 会 KeyError 当场炸。
REF = {}


def add(eid, obj):
    """把一张图追加进 ex，顺序即图号（Exhibit 1 是汇总表，所以从 2 起）。"""
    if eid in REF:
        raise SystemExit(f'图 id 重复：{eid}')
    obj['n'] = len(ex) + 2
    REF[eid] = obj['n']
    ex.append(obj)
    return obj


def X(eid):
    return f'§{eid}§'


def subst_refs(o):
    """递归把 payload 里的 §id§ 换成真图号。未知 id 直接 KeyError（不许静默留占位符）。"""
    if isinstance(o, str):
        return re.sub(r'§([a-z_0-9]+)§', lambda m: str(REF[m.group(1)]), o)
    if isinstance(o, list):
        return [subst_refs(v) for v in o]
    if isinstance(o, dict):
        return {k: subst_refs(v) for k, v in o.items()}
    return o


# ── 4 年同月窗口：起止对照 / Δ / 归因桥三张图的取数口径 ──────────────────────
# **为什么不用 Pool 的共同窗口。** 共同窗口是 dropna(how='any')，被披露最晚的成员卡死：
# 期权池 19 个月、现货池 68 个月，两个池的「期初」根本不是同一个月，横着读没有意义。
# **为什么是同月（Jul vs Jul）而不是「最新月 vs 某个期初月」。** 份额本身带月份效应
# （到期周、假期月、季末再平衡改变的不只是总量，还有订单流的构成）。实测量级见页尾
# 口径说明：本页月份效应最大的成员，份额极差比它自己的年均结构性漂移还大 ——
# **一次季节性摆动就抵得上一年的结构性变化**，所以起止两点必须取同一个月份。
# **为什么窗口由分母决定、不由最短的成员决定。** 分母是官方发布的行业总量，每家可以
# 各自独立除。期初那个月凑不齐的成员并进残差桶 —— 桶 = 官方分母 − 已列成员，
# 仍然**精确**（加总恒等、零偏差），代价只是那一家在这三张图上不单独拆出来。
WIN_YEARS = 4

# 成员为什么在期初那个月没有月度披露 —— 一家一条，写清楚是「官方不发」还是「本仓没抓」。
# 泛化的兜底句在 Win.drop_note 里，但兜底句是**没查过**的意思，真被用上就该来补这张表。
DROP_WHY = {
    'ndaq': ('Nasdaq 的 IR「Monthly Reporting Sheet」每月<b>原地覆盖</b>，'
             '只含「上一整年 + 本年 YTD」，官网不留历史副本，'
             '月度美股期权量因此回不到 2025-01 之前 —— 这是<b>官方不发</b>，不是本仓没抓。'
             '替代源也试过：OCC 的分交易所月度量 2026-08-07 实测已挂 Cloudflare JS 挑战、'
             'marketdata 接口返 400，无人值守取不到；'
             'Nasdaq 自己的季度自报只回到 2023Q1，同样够不着本窗口的期初'),
}


class Win(object):
    """池的「同月 N 年」窗口视图 —— 只有期初、期末两行。

    对外暴露的属性与 Pool 完全一致（en / pid / df / members / other_* / unit_* /
    start / end），所以 start_end_bars / delta_bars / bridge 三个 builder 不必知道
    自己拿到的是 Pool 还是 Win。
    """

    def __init__(self, pool, years=WIN_YEARS):
        self.pool, self.years = pool, years
        self.pid, self.en, self.zh = pool.pid, pool.en, pool.zh
        self.unit_div, self.unit_lab = pool.unit_div, pool.unit_lab
        p1 = LATEST
        p0 = pd.Period(f'{p1.year - years}-{p1.month:02d}', 'M')
        self.start, self.end = p0, p1
        den = LONG_DEN[pool.pid]
        d0, d1 = float(den.get(p0, np.nan)), float(den.get(p1, np.nan))
        if not (np.isfinite(d0) and np.isfinite(d1)):
            skip(f'{pool.zh}：官方分母缺 {mlab(p0)} 或 {mlab(p1)}，{years} 年同月窗口做不出来')
        keep, drop = [], []
        for m in pool.members:
            s = LONG_NUM[(pool.pid, m.key)]
            v0, v1 = float(s.get(p0, np.nan)), float(s.get(p1, np.nan))
            (keep if np.isfinite(v0) and np.isfinite(v1) else drop).append(m)
        if not keep:
            skip(f'{pool.zh}：{years} 年同月窗口里没有任何成员两头齐全')
        self.members, self.dropped = keep, drop
        # 残差桶名：被并进来的成员要**写在桶名里**，不能让读者以为桶还是原来那个桶
        if drop:
            self.other_lab = '、'.join(m.disp for m in drop) + ' + ' + pool.other_lab
            self.other_short = '+'.join(m.short for m in drop) + '+其他'
            self.other_en = ' + '.join(m.disp for m in drop) + ' + ' + pool.other_en
        else:
            self.other_lab, self.other_short, self.other_en = (
                pool.other_lab, pool.other_short, pool.other_en)
        cols = {m.key: [float(LONG_NUM[(pool.pid, m.key)].get(p, np.nan)) for p in (p0, p1)]
                for m in keep}
        cols['pool'] = [d0, d1]
        df = pd.DataFrame(cols, index=pd.PeriodIndex([p0, p1], freq='M'))
        df['sum4'] = df[[m.key for m in keep]].sum(axis=1)
        df['other'] = df['pool'] - df['sum4']
        if float(df['other'].min()) < 0:
            # 成员之和超过官方行业总量 = 分子分母口径不一致，与 Pool.build() 同一条规矩
            raise SystemExit(f'{pool.pid} {years}年窗口成员之和超过官方分母')
        for k in [m.key for m in keep] + ['sum4', 'other']:
            df[k + '_s'] = df[k] / df['pool'] * 100.0
        self.df = df

    @property
    def drop_note(self):
        """并桶说明。没有成员被并进去时返回空串（不要凭空写一句「无缺席」占版面）。"""
        if not self.dropped:
            return ''
        why = '；'.join(DROP_WHY.get(m.key, f'{m.disp} 的月度披露起步晚于本窗口期初')
                        for m in self.dropped)
        return ('<b>' + '、'.join(m.disp for m in self.dropped)
                + f' 在 {mlab(self.start)} 没有月度披露，本图把它并进残差桶</b>'
                + f'（桶名已写全：{self.other_lab}）。'
                + '<b>这不引入任何误差</b> —— 桶 = 官方行业总量 − 图上其余各家，'
                  '加总仍然恒等；代价只是它在这张图上不单独拆出来。'
                + f'原因：{why}。'
                + '它自己的读数在 §opt_long§、§opt_q§ 与 Exhibit 1 汇总表里都在。')


def win_span(w):
    """图注里统一的窗口说明句。"""
    return (f'窗口 = <b>{mlab(w.start)} → {mlab(w.end)}（{w.years} 年，同月比同月）</b>。'
            '取同一个月份是刻意的：份额带月份效应，'
            '<b>一次季节性摆动就抵得上一年的结构性变化</b>（量化见页尾口径说明），'
            '所以起止两点必须落在同一个月份上。'
            f'窗口由<b>官方分母</b>决定，不由披露最晚的成员决定 —— '
            '真分母是官方发的，每家各自独立除即可。')


def share_stack(pool, xl, xstep):
    """池内真份额堆叠（四家）+ 右轴残差桶份额。

    为什么堆叠的是四家而不是「四家 + 残差 = 100%」：残差桶在现货池里是 56% 的场外内化，
    堆进去会把四家全压成底部一条窄带；把它放到右轴当一条线，既保住了「加起来是 100%」
    这个事实（线 + 堆顶 ≡ 100），又让四家之间的此消彼长占满左轴。

    **段内数值一律不开**（`label: False`）。charts.js 的段内标签写死 6.6px，实测 1:1
    截图：深字压在浅底（Cboe 的 BLUE #9DC3E6、MIAX 的 GOLD #BF9000）上清晰可读，
    白字压在 NAVY #1F3864 与 MBLUE #2E75B6 上则糊成一团白斑 —— 白色细笔画在这个字号上
    被抗锯齿吃掉了。只给浅底两段标数值又会造成「四家里两家有数、两家没有」的错觉。
    读数在同一页上另有三处：Exhibit 1 汇总表（两位小数）、下一张起止对照图（柱上带标签）、
    以及本卡右上角的「表格」视图（逐月全序列）。
    """
    return {
        'kind': 'stacked_dual', 'full': True, 'height': 340,
        'fmt': 'f1', 'xlabels': xl, 'xstep': xstep, 'xrot': 90,
        'title': f'{pool.en}: true market share, {mlab(pool.start)} – {mlab(pool.end)}',
        'ylab': '% of official industry total（左，堆叠）',
        'ylab2': f'{pool.other_en}, % （右）',
        'stacks': [{'name': m.disp, 'color': m.color, 'values': L(pool.df[m.key + '_s'].values),
                    'label': False}
                   for m in pool.members],
        'line': {'name': pool.other_lab + '（RHS）', 'color': CHK_C,
                 'values': L(pool.df['other_s'].values),
                 'ymax': nice_max(float(pool.df['other_s'].max()) * 1.1)},
        'src_extra': (f'Denominator = {pool.denom.disp} as published by ICE '
                      f'(and, for options, independently by MIAX). Stack + line = 100% by '
                      f'construction'),
        'note': ('堆叠的四段是四家交易所集团各自的<b>真份额</b>（分母为官方行业总量），'
                 '右轴那条线是剩下的部分 —— <b>堆顶 + 线 ≡ 100%</b>，不是两个独立的东西。'
                 f'{mlab(pool.start)} → {mlab(pool.end)}：四家合计 '
                 f'{pool.df["sum4_s"].iloc[0]:.1f}% → {pool.df["sum4_s"].iloc[-1]:.1f}%'
                 f'（{pp(float(pool.df["sum4_s"].iloc[-1] - pool.df["sum4_s"].iloc[0]))}），'
                 f'{pool.other_lab} {pool.df["other_s"].iloc[0]:.1f}% → '
                 f'{pool.df["other_s"].iloc[-1]:.1f}%。'
                 '段内不标数值（引擎的段内标签写死 6.6px，白字压在深色段上会糊成白斑）：'
                 '逐月读数请切本卡右上角的「表格」视图，当月两位小数见 Exhibit 1 汇总表，'
                 f'{WIN_YEARS} 年同月的带标签柱见下一张图。'),
    }


def start_end_bars(pool):
    """起止对照：期初 vs 期末，各家 + 残差桶并排（口径 = 4 年同月窗口，见 Win）。

    类别轴上的残差桶用**短名**：长名（「场外与其他（TRF 内化 / MEMX / IEX 等）」）
    横排时会与左右邻居压字。长名照旧写在图注与图例里，信息一个字没少。
    x 标签水平排的理由见 CAT_XROT。
    """
    names = [m.short for m in pool.members] + [pool.other_short]
    keys = [m.key + '_s' for m in pool.members] + ['other_s']
    v0 = [float(pool.df[k].iloc[0]) for k in keys]
    v1 = [float(pool.df[k].iloc[-1]) for k in keys]
    return {
        'kind': 'grouped_bars', 'height': 300,
        'fmt': 'f1', 'label_fmt': 'f1', 'bar_labels': True,
        'xlabels': names, 'xrot': CAT_XROT,
        'title': (f'{pool.en}: share at {mlab(pool.start)} vs {mlab(pool.end)} '
                  f'({pool.years} years, same month)'),
        'ylab': '% of official industry total',
        'groups': [{'name': f'{mlab(pool.start)}（期初）', 'color': 'GRAY', 'values': L(v0)},
                   {'name': f'{mlab(pool.end)}（期末）', 'color': 'NAVY', 'values': L(v1)}],
        'src_extra': ('Both bars use the same official industry denominator of their own month; '
                      'the two months are the same calendar month four years apart'),
        'note': ('两根柱各自除以<b>本月的</b>官方行业总量，所以柱高差就是真份额的变化，'
                 '与池子本身涨了多少无关（池的变化见下一张桥图）。'
                 + win_span(pool)
                 + f'期初池总量 {num(float(pool.df["pool"].iloc[0]) / pool.unit_div)} → '
                 + f'期末 {num(float(pool.df["pool"].iloc[-1]) / pool.unit_div)} {pool.unit_lab}'
                 + f'（{pct(float(pool.df["pool"].iloc[-1] / pool.df["pool"].iloc[0] - 1) * 100)}）。'
                 + pool.drop_note),
    }


def delta_bars(pool):
    """Δpp 排序：谁在这段窗口里真正拿到了份额。

    **不用 `diverging_bars`**（正负分色本来正合适）：那个 kind 的图例与表格列名在
    assets/charts.js 里写死成 COST 的业务文案 —— 图例固定印
    「Reported > Core（油汇顺风）」/「Reported < Core（油汇拖累）」，表格视图列名固定是
    「Reported − Core」，`ex.legend` 被忽略（charts.js:1437 / 1522-1523）。
    引擎 14 页共用不能改，所以这里改用只放一个 group 的 `grouped_bars`：
    图例名与表格列名都能自定义，纵轴 y0 = min(0, mn×1.15) 照样容纳负柱。
    代价是**正负同色** —— 但本图按变化降序排，正负分界一眼就在，损失有限。
    （`bars_labeled` 不能用：它强制零基线，负柱会画到画布外。见 docs/CHART_KINDS.md §3.4）
    """
    names = [m.short for m in pool.members] + [pool.other_short]
    keys = [m.key + '_s' for m in pool.members] + ['other_s']
    d = [(nm, float(pool.df[k].iloc[-1] - pool.df[k].iloc[0])) for nm, k in zip(names, keys)]
    d.sort(key=lambda kv: -kv[1])
    txt = '、'.join(f'{nm} {pp(v)}' for nm, v in d)
    return {
        'kind': 'grouped_bars', 'height': 280,
        # grouped_bars 的柱值标签默认关，要显式打开；label_fmt 不给会回退 fmt，这里一并写死。
        # **单位取 bp 而不是 pp**：本图有绝对值不到 1pp 的柱（期权池 Nasdaq −0.04pp），
        # 引擎的 `pp1` 会把它印成「-0.0pp」—— 负零是格式化产物，契约 §2 明令避免；
        # 换成 bp 后同一个值是 −4bp，也正好落在「|v| < 1pp 一律写 bp」的全站规矩上。
        'fmt': 'f0', 'label_fmt': 'f0', 'bar_labels': True, 'zero_line': True,
        'xlabels': [nm for nm, _ in d], 'xrot': CAT_XROT,
        'title': (f'{pool.en}: share change {mlab(pool.start)} → {mlab(pool.end)} (bp, '
                  f'{pool.years} years, same month)'),
        'ylab': 'bp of official industry total（1pp = 100bp）',
        'groups': [{
            'name': f'份额变化 {mlab(pool.start)} → {mlab(pool.end)}（bp）',
            'color': 'NAVY', 'values': L([v * 100 for _, v in d]),
        }],
        'src_extra': 'Sorted by change; the bars sum to zero by construction',
        'note': (f'纵轴单位是 <b>bp</b>（1pp = 100bp），按变化排序（正在左、负在右）。'
                 f'<b>{len(d)} 根柱之和恒为 0</b> —— 份额是零和的，'
                 '一家的上升必然对应另一家的下降，这是本页用真分母的直接好处：'
                 '在「成员之和当分母」的算法里，各家可以同时上升。'
                 + win_span(pool)
                 + f'读数：{txt}。'
                 + pool.drop_note),
    }


def bridge(pool):
    """把每家的量变拆成「池扩大」与「份额转移」两块，恒等式无残差。

        ΔV_i = s_i(0)·(P_T − P_0)      池扩大：份额不变时本来就会拿到的增量
             + (s_i,T − s_i,0)·P_T      份额转移：真正抢来 / 丢掉的那部分
    两项相加逐项等于 ΔV_i（把交叉项并进第二项，所以没有残差柱）。
    全部成员的「份额转移」相加恒为 0，末列「池合计」因此只有池扩大一块 —— 那一列
    是这张图自带的算术校验。
    """
    names = [m.short for m in pool.members] + [pool.other_short, '池合计']
    keys = [m.key for m in pool.members] + ['other']
    P0, P1 = float(pool.df['pool'].iloc[0]), float(pool.df['pool'].iloc[-1])
    grow, shift, net = [], [], []
    for k in keys:
        s0 = float(pool.df[k].iloc[0]) / P0
        s1 = float(pool.df[k].iloc[-1]) / P1
        grow.append(s0 * (P1 - P0) / pool.unit_div)
        shift.append((s1 - s0) * P1 / pool.unit_div)
        net.append((float(pool.df[k].iloc[-1]) - float(pool.df[k].iloc[0])) / pool.unit_div)
    grow.append((P1 - P0) / pool.unit_div)
    shift.append(0.0)
    net.append((P1 - P0) / pool.unit_div)
    resid = max(abs(g + s - nv) for g, s, nv in zip(grow, shift, net))
    if resid > 1e-6 * max(1.0, abs(net[-1])):
        raise SystemExit(f'{pool.pid} 桥恒等式不闭合，残差 {resid}')
    return {
        'kind': 'bridge_bar', 'full': True, 'height': 320,
        'fmt': 'f0c', 'xlabels': names, 'xrot': CAT_XROT,
        'title': (f'{pool.en}: what each firm\'s volume change is made of, '
                  f'{mlab(pool.start)} → {mlab(pool.end)}'),
        'ylab': f'{pool.unit_lab}',
        'stacks': [{'name': '池扩大（份额不变时的增量）', 'color': CBOE_C, 'values': L(grow)},
                   {'name': '份额转移（真正抢来 / 丢掉的）', 'color': MIAX_C, 'values': L(shift)}],
        'net': {'name': '净变化', 'values': L(net)}, 'net_color': 'INK',
        'src_extra': ('Decomposition is exact: pool-growth term uses the start share, '
                      'share-shift term uses the end pool size; the two add to the net change'),
        'note': ('每家的量变 = <b>池扩大</b>（份额不变时本来就会拿到的那份）+ '
                 '<b>份额转移</b>（真抢来或真丢掉的那份）。两项相加逐列等于菱形的净变化，'
                 '<b>没有残差项</b>（交叉项已并入第二项）。'
                 '所有成员的「份额转移」相加恒为 0，所以末列「池合计」只剩池扩大一块 —— '
                 '那一列就是这张图自带的算术校验。'
                 + win_span(pool)
                 + f'本窗口池总量 {num(P0 / pool.unit_div)} → {num(P1 / pool.unit_div)} '
                 + f'{pool.unit_lab}，池扩大合计 {num((P1 - P0) / pool.unit_div)}。'
                 + pool.drop_note),
    }


WIN_CASH, WIN_OPT = Win(POOL_CASH), Win(POOL_OPT)

# ── 现货块（有 68 个月的月度堆叠带，所以它领头）──
add('cash_stack', share_stack(POOL_CASH, XL_CASH, 3))
add('cash_se', start_end_bars(WIN_CASH))
add('cash_delta', delta_bars(WIN_CASH))
add('cash_bridge', bridge(WIN_CASH))

# ── 期权块 ──
# **没有月度堆叠带。** 期权池的共同窗口只有 19 个月（Nasdaq 的 IR 报表自 2025-01 起），
# 一条 19 个月的堆叠带既看不出趋势、又和现货那条 68 个月的带不可并读；
# 它的长历史份额在 §opt_long§（月度折线）与 §opt_q§（季度折线）上各有一张，
# 那两张不要求四家齐全，信息比一条短带强得多。
add('opt_se', start_end_bars(WIN_OPT))
add('opt_delta', delta_bars(WIN_OPT))
add('opt_bridge', bridge(WIN_OPT))

# ── 张数口径 vs 定基名义额口径（互为校验）──
_p0txt = (f'基期价格 {POOL_OPT.base_price:,.2f}（{OPT_SPEC_ID}）'
          if POOL_OPT.base_price is not None
          else f'基期价格在 contract_specs.csv 的 {OPT_SPEC_ID} 行是<b>空的</b>'
               '（📌 2019-01 成交量加权标的均价未找到官方单一字段），'
               '故名义额只报到<b>股当量</b>（张数 × 100 股），不报美元水平值')
add('unit_check', {
    'kind': 'bar_line', 'full': True, 'height': 320,
    'fmt': 'f1', 'yfmt': 'f0', 'xlabels': XL_OPT, 'xstep': 1, 'xrot': 90,
    'title': (f'Unit check — contracts vs constant-basis notional, '
              f'{POOL_OPT.en} pool (rebased {mlab(POOL_OPT.start)} = 100)'),
    'ylab': f'index, {mlab(POOL_OPT.start)} = 100',
    # bar_line 的图例直接取 bar.name / line.name（charts.js legendHTML），
    # 不给就在图例里印两个 "undefined" —— 而这张图的全部意义就是「哪条是哪条口径」。
    'bar': {'name': '张数口径（池总 ADV 指数）', 'color': NYSE_C,
            'values': L(OPT_IC.values), 'yfmt': 'f0'},
    'line': {'name': '定基名义额口径（同一池，指数）', 'color': CHK_C,
             'values': L(OPT_IN.values), 'yfmt': 'f0'},
    'src_extra': ('Contracts path and notional path are computed independently from the raw '
                  'columns and must coincide, because every contract in this pool is 100 shares'),
    'note': ('柱 = 张数口径的池总量指数，线 = 定基名义额口径的池总量指数。'
             '<b>线必须逐点压在柱顶上</b>：本池内每一张合约都是 '
             f'{POOL_OPT.mult_lab}，乘数与基期价格对四家是同一个常数，'
             '所以两种口径的增长率与份额<b>恒等</b>。'
             f'实测偏离：指数 {OPT_DIDX:.2e}、份额 {OPT_DSHARE:.2e}pp、'
             f'单位乘数 {OPT_DRATIO:.2e} —— 三者任一超过 1e-9 本文件就会抛异常拒绝出页。'
             f'{_p0txt}。'
             + (f'<b>这个恒等是北美池的特权，不是普遍规律</b>：{JPX_TXT} —— 同一段窗口、'
                '同一批合约，两种口径符号相反，那种池里张数根本不能用来比较。'
                if JPX_TXT else '')),
})

# ── Exhibit 11-12：长历史真份额（同一条官方分母）──
_opt_share_long = {}
for _m in POOL_OPT.members:
    _opt_share_long[_m.key] = (_m.series() / OPT_DENOM.series() * 100).reindex(LONG_IDX)
_deep_opt = [m for m in POOL_OPT.members
             if int(_opt_share_long[m.key].notna().sum()) >= 60]
_shallow_opt = [(m.disp, int(_opt_share_long[m.key].notna().sum()),
                 float(_opt_share_long[m.key].dropna().iloc[-1]))
                for m in POOL_OPT.members if m not in _deep_opt]
add('opt_long', {
    'kind': 'lines', 'full': True, 'height': 360,
    'fmt': 'f1', 'yfmt': 'f0', 'xlabels': XL_LONG, 'xstep': 12, 'xrot': 90,
    'end_label': True, 'label_fmt': 'f1', 'zero_base': True, 'markers': False,
    'title': f'{POOL_OPT.en}: true share against the same official denominator, long history',
    'ylab': '% of industry ADV',
    'series': [{'name': m.disp, 'color': m.color, 'values': L(_opt_share_long[m.key].values)}
               for m in _deep_opt],
    'src_extra': ('Numerators from each firm\'s own monthly disclosure; denominator = '
                  'ICE\'s published U.S. equity options industry ADV throughout'),
    'note': ('两条线用的是<b>同一条分母</b>（ICE 逐月披露的全美股票/ETF 期权行业 ADV），'
             '所以线的高低可以直读、差值就是份额差。'
             + ('未画的成员：'
                + '、'.join(f'{d}（月度序列只有 {n} 个月，{mlab(LATEST)} 为 {v:.1f}%）'
                            for d, n, v in _shallow_opt)
                + ' —— 它们的月度披露起步晚，画上去只是右端一小截，反而遮住这张图要说的'
                  '十几年趋势；它们在最新月的读数见 Exhibit 1 汇总表，'
                  '4 年同月的起止对照见 §opt_se§。' if _shallow_opt else '')
             + f'纵轴从 0 起（<code>zero_base</code>），不做隐性截轴。'),
})

_cash_share_long = {}
for _m in POOL_CASH.members:
    _cash_share_long[_m.key] = (_m.series() / CASH_DENOM.series() * 100).reindex(LONG_IDX)
_deep_cash = [m for m in POOL_CASH.members
              if int(_cash_share_long[m.key].notna().sum()) >= 60]
_shallow_cash = [(m.disp, int(_cash_share_long[m.key].notna().sum()),
                  float(_cash_share_long[m.key].dropna().iloc[-1]))
                 for m in POOL_CASH.members if m not in _deep_cash]
_deep_sum = sum((_cash_share_long[m.key] for m in _deep_cash[1:]),
                _cash_share_long[_deep_cash[0].key])
# ── 「以上四家合计」这条线本图**不画** ──
# 它是那四条线的算术和（43–54%），比最高的成员线（NYSE 约 27%）还高一倍。
# `zero_base` 的纵轴按最大序列定上界，多这一条就把量程从 0–30 撑到 0–60 ——
# 每条真实序列的垂直分辨率**减半**，本图的主结论（NYSE 十五年 27% → 19%）
# 被压进图高的 13%，而量级最小的成员被压成一条贴零线。
# 合计是派生量、不是池成员，同一个数在 Exhibit 6 的堆顶、Exhibit 1 汇总表与页尾
# 口径说明里各有一处，去掉它信息一个字不丢。见 docs/VISUAL_QA.md §3.G。
_ds_nz = _deep_sum.dropna()

# ── 谁在这根共用轴上被压平了：判据是**比值**，不是名字 ────────────────────────
# 去掉「四家合计」那条派生线（2026-08-06）只把量程从 0–60 收回 0–30，成员之间的量级差
# 一分没动 —— 那个差是数据本身的。这里把它量出来，供下面 §cash_long§ 的图注与全页末尾
# 那张「按自己量程重画」的图（§cash_long_small§）共用同一套判据。
#
# 阈值的来历：取各成员长历史份额的**峰值**与全池峰值之比，本轮实测四家是
# 1.00 / 1.24 / 1.39 / 11.83（见构建日志），1.39 与 11.83 之间是一段很宽的空档；
# 4 ≈ √(1.39 × 11.83) 落在空档正中，对数据抖动最不敏感。
# 不写死成「画 MIAX」：成员表一变（新增所、某家掉队）判据就该跟着走，写死会静默画错。
SMALL_RATIO = 4.0
_cash_peak = {m.key: float(_cash_share_long[m.key].dropna().max()) for m in _deep_cash}
_cash_top = max(_cash_peak.values())
# 轴上最矮的那条：把它的区间写进图注，贴零线也能读出真数
_small = min(_deep_cash, key=lambda m: _cash_peak[m.key])
_small_nz = _cash_share_long[_small.key].dropna()
# 峰值不到全池峰值 1/4 的成员 —— 这些在共用轴上读不出形状，末尾单开一张
_small_set = [m for m in _deep_cash if _cash_peak[m.key] * SMALL_RATIO <= _cash_top]
print(f'{TICKER}: 现货长历史份额峰值比（vs 全池最高）：'
      + '、'.join(f'{m.disp} {_cash_top / _cash_peak[m.key]:.2f}×' for m in _deep_cash)
      + f'；阈值 {SMALL_RATIO:g}× ⇒ 末尾单开一张画：'
      + ('、'.join(m.disp for m in _small_set) if _small_set else '（无，四条量级相当）'))
add('cash_long', {
    'kind': 'lines', 'full': True, 'height': 360,
    'fmt': 'f1', 'yfmt': 'f0', 'xlabels': XL_LONG, 'xstep': 12, 'xrot': 90,
    'end_label': True, 'label_fmt': 'f1', 'zero_base': True, 'markers': False,
    'title': (f'{POOL_CASH.en}: true matched share of consolidated volume, '
              f'{mlab(LONG_IDX[0])} – {mlab(LATEST)}'),
    'ylab': '% of consolidated volume',
    'series': [{'name': m.disp, 'color': m.color, 'values': L(_cash_share_long[m.key].values)}
               for m in _deep_cash],
    'src_extra': ('Denominator = Tape A+B+C consolidated volume (ICE monthly metrics), which '
                  'includes off-exchange/TRF prints — so the gap to 100% is mostly internalisation'),
    'note': ('分母是 Tape A+B+C 的<b>全市场合并成交量</b>，它<b>含场外（TRF）内化成交</b>，'
             '所以这几条线加起来离 100% 的距离，主要就是场外那一块。'
             '这是本页与「交易所之间互相比大小」最本质的区别：'
             '<b>交易所真正的对手不只是彼此，还有把单子留在自己内部撮合的做市商与券商。</b>'
             f'<b>「{len(_deep_cash)} 家合计」这条线本图刻意不画</b>：它是这几条线之和'
             f'（{mlab(_ds_nz.index[0])} {_ds_nz.iloc[0]:.1f}% → '
             f'{mlab(_ds_nz.index[-1])} {_ds_nz.iloc[-1]:.1f}%），'
             '比最高的成员线还高一倍，画上去（纵轴从 0 起）上界就得翻一倍，'
             '每条真实序列的垂直分辨率随之减半 —— 合计的走势见 §cash_stack§ 的堆顶与右轴残差，'
             '当月两位小数见 Exhibit 1 汇总表。'
             f'<b>{_small.disp} 是轴上最矮的一条</b>'
             f'（{mlab(_small_nz.index[0])} 起，全程 {_small_nz.min():.2f}–'
             f'{_small_nz.max():.2f}%，{mlab(LATEST)} {_small_nz.iloc[-1]:.2f}%）—— '
             f'本图最高的一条峰值 {_cash_top:.1f}%，两者差 '
             f'{_cash_top / _cash_peak[_small.key]:.1f} 倍，同一根从 0 起的轴上它必然接近贴零。'
             + (f'<b>它自己那一档量程的图在 Exhibit §cash_long_small§</b>（同一批数、只换纵轴），'
                '逐月读数也可以切本卡右上角的「表格」视图。'
                if _small_set else '逐月读数请切本卡右上角的「表格」视图。')
             + ('未画：'
                + '、'.join(f'{d}（{n} 个月，{mlab(LATEST)} 为 {v:.2f}%）'
                            for d, n, v in _shallow_cash) + '。' if _shallow_cash else '')),
})

# ── Exhibit 13：自校验残差（本页可信度的硬证据）──
# 同 delta_bars：不用 diverging_bars（引擎把 COST 的「油汇顺风 / Reported − Core」写死在
# 它的图例与表格列名里，改不掉），改用单 group 的 grouped_bars。
# 这张图 187 根柱，柱值标签一定读不出来 —— grouped_bars 的 bar_labels 默认就是关的，
# 不显式打开即可（diverging_bars 那边也是恒关，两者在这一点上表现一致）。
_res_bp = (A_ICE['cash'] * 100).reindex(LONG_IDX)      # pp → bp
add('selfcheck', {
    'kind': 'grouped_bars', 'full': True, 'height': 300,
    'fmt': 'f1', 'yfmt': 'f0', 'xlabels': XL_LONG, 'xstep': 12, 'xrot': 90,
    'title': ('Self-check residual — our computed NYSE cash matched share minus '
              'ICE\'s own published share (bp)'),
    'ylab': 'bp（1pp = 100bp）',
    'groups': [{'name': '残差 = 本页重算份额 − ICE 自报份额（bp）',
                'color': 'NAVY', 'values': L(_res_bp.values)}],
    'src_extra': ('ICE publishes both the inputs and the answer; this is ours minus their '
                  'answer, month by month'),
    'note': ('ICE 在同一张月度表里既给<b>分子分母</b>又给<b>它自己算好的份额</b>。'
             '本页用分子分母重算一遍再减去它的答案 —— 这张图就是差值。'
             f'{A_CASH_N} 个月里最大 |残差| = <b>{A_CASH_MAX * 100:.1f}bp</b>'
             f'（{A_CASH_MAX:.3f}pp），'
             f'四舍五入到 ICE 自报的 3 位小数后有 {A_CASH_R3}/{A_CASH_N} 个月完全相同。'
             '残差不为零不是算法分歧：ICE 把分子分母都印成<b>整数百万股</b>，'
             '一个 ±0.5 百万股的印刷舍入落在几百的分子上就是几个 bp。'
             f'同法对期权份额：{A_OPT_N} 个月最大 {A_OPT_MAX * 100:.1f}bp；'
             f'三条 tape 分开算最大 {A_TAPE_MAX * 100:.1f}bp。'
             '<b>本文件把 0.5pp 设成硬阈值 —— 超过就抛异常拒绝出页</b>，'
             '因为那意味着本页的份额与交易所自己说的不是同一件事。'),
})

# ── Exhibit 14：NYSE 现货真份额的月 × 年热力矩阵 ──
_s = A_ICE['cash_calc'].dropna()
_yrs = sorted({p.year for p in _s.index})[-HEAT_YEARS:]
_M = [[None] * 12 for _ in _yrs]
for _p, _v in _s.items():
    if _p.year in _yrs:
        _M[_yrs.index(_p.year)][_p.month - 1] = round(float(_v), 6)
add('heat', {
    'kind': 'heat_matrix', 'full': True, 'fmt': 'f1',
    'title': 'NYSE Group matched share of U.S. consolidated volume (%), month × year',
    'rows': [str(y) for y in _yrs], 'cols': MONTHS, 'matrix': _M,
    'legend': 'NYSE Group matched share (%)', 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
    'src_extra': ('Green = higher share. Colour scale is the 5th–95th percentile of this '
                  'matrix\'s own cells'),
    'note': ('把 §cash_long§ 里 NYSE 那条线摊成月 × 年，看份额是<b>趋势性</b>下移还是几个'
             '异常月拉出来的。色标取本矩阵自己有效格的 5/95 分位，'
             '<b>只在本图内部可比</b>。'),
})

# ── TMX / BOX 对照（第四家公司的独立锚点）──
if A_BOX:
    add('box', {
        'kind': 'grouped_bars', 'full': True, 'height': 300,
        'fmt': 'f1', 'label_fmt': 'f1', 'bar_labels': True,
        'xlabels': [q for q, _o, _c, _v in A_BOX],
        'title': ('Cross-company anchor — BOX share of U.S. equity options: '
                  'TMX\'s own figure vs computed off ICE\'s denominator'),
        'ylab': '% of U.S. equity options industry volume',
        'groups': [{'name': 'TMX 季度 MD&A 自报（官方只给整数）', 'color': 'GRAY',
                    'values': L([o for _q, o, _c, _v in A_BOX])},
                   {'name': '本页自算（BOX 张数 ÷ ICE 行业分母）', 'color': NYSE_C,
                    'values': L([c for _q, _o, c, _v in A_BOX])}],
        'src_extra': ('TMX reports BOX only quarterly and only as an integer percent; the '
                      'computed bar uses ICE\'s monthly industry ADV aggregated to quarters'),
        'note': ('BOX 是 TMX 控股的美股期权所，它落在本页两个池的<b>残差桶</b>里。'
                 '这一格是第四家公司给出的独立锚点：TMX 自己报的市占（只给整数）'
                 '与本页用 ICE 分母现算的值，'
                 f'<b>{BOX_HIT}/{BOX_N} 个季度四舍五入后完全一致</b>。'
                 'TMX 只按季度披露 BOX，没有任何月度口径，所以 BOX 进不了月度池；'
                 '另需留意 <code>docs/verify/tmx.md</code> 记的一条：'
                 '2026-07-30 宣布 BOX 与 MEMX 合并为 MEMX Group，'
                 '此后 BOX 大概率不再作为 TMX 的经营口径单独披露 —— '
                 '这条锚点会自然失效，不是数据出错。'),
    })


# ═══════════════ 8. 季度聚合与月份效应（长历史分子见 §3b）═══════════════
def q_of(idx):
    """月度 PeriodIndex → 对应季度的 PeriodIndex（当分组键用）。"""
    return pd.PeriodIndex(idx.to_timestamp(), freq='Q')


def qshare(num, den, min_months=3):
    """**量加权**季度份额（%）= Σ(当季各月成交量) ÷ Σ(当季各月行业分母)。

    不是「简单平均三个月的月份额」：源列全是 ADV（日均），各月的交易日数与总量都不同，
    直接平均等于给低量月（假期月、交易日少的月）过高权重。这里先把每个月的 ADV 乘回
    当月交易日数还原成**月成交量**，分子分母各自求和再相除 —— 与「把一个季度当成一段
    连续日历来算份额」是同一件事。

    只认三个月齐全的季度（分子分母都要齐）：缺一个月时，分子与分母覆盖的不是同一段
    日历，算出来的份额没有意义，宁可留 None 让线断开。
    """
    df = pd.DataFrame({'n': num, 'd': den, 'k': DAYS})
    df['vn'] = df['n'] * df['k']
    df['vd'] = df['d'] * df['k']
    g = df.groupby(q_of(df.index))
    out = g['vn'].sum(min_count=1) / g['vd'].sum(min_count=1) * 100.0
    out[(g['vn'].count() < min_months) | (g['vd'].count() < min_months)] = np.nan
    return out


def q_window(pid):
    """该池分母的完整季度窗口（连续，中间不许有洞）。"""
    d = pd.DataFrame({'d': LONG_DEN[pid], 'k': DAYS}).dropna()
    cnt = d.groupby(q_of(d.index)).size()
    full = cnt[cnt == 3].index
    if len(full) == 0:
        return pd.PeriodIndex([], freq='Q')
    qi = pd.period_range(full.min(), full.max(), freq='Q')
    miss = [str(q) for q in qi if q not in full]
    if miss:
        # 分母中间缺季 = 源数据坏了，与 Pool.build() 的缺月判定同一个规矩：必须响
        raise SystemExit(f'{pid} 季度窗口 {qi[0]}–{qi[-1]} 内分母缺季：{miss}')
    return qi


QIDX = {p.pid: q_window(p.pid) for p in POOLS}
QSHARE = {(p.pid, m.key): qshare(LONG_NUM[(p.pid, m.key)],
                                 LONG_DEN[p.pid]).reindex(QIDX[p.pid])
          for p in POOLS for m in p.members}

# 两处**形式数（pro-forma）断点**，都是仓内已核过的事实，不是本文件的推断：
#   · docs/verify/verify_ice.md §5.6：ICE 2013-11 才完成 NYSE Euronext 收购，
#     而它的月度表把 NYSE 的 ADV「for comparison purposes」回填到了全部期间 ——
#     2011-01 ~ 2013-10 的 NYSE 数据是「假设当时就拥有」的形式数。
#   · build/cboe.py：Cboe 2017-02 完成对 Bats 的收购，2017 全年为 Bats pro-forma
#     combined，2018-01 起才是实际口径。Cboe 的美股现货业务整个来自 Bats，
#     所以这条断点对现货池比对期权池更要紧。
# 断点画在该季**左缘**，语义是「从这一季起与左侧不可比」，所以取的是第一个干净季。
PROFORMA = [('2014Q1', 'NYSE：2013Q4 前为追溯并入形式数'),
            ('2018Q1', 'Cboe：2017 年为 Bats 形式数')]


def _qi(qidx, s):
    q = pd.Period(s, 'Q')
    lst = list(qidx)
    return lst.index(q) if q in lst else None


MEFF_MIN_YEARS = 3      # 少于这么多完整年，「月份效应」与该成员自身的趋势分不开


def month_effect(share_m):
    """同月份额相对**该年份额均值**的平均偏离（pp），只用 12 个月齐全的完整年。

    这是 Exhibit 18/19 存在的理由的量化：份额本身带月份效应（到期周、假期月改变的是
    订单流的构成，不只是总量），所以「本月 vs 上月」的变化里混着季节性。

    **至少要 3 个完整年**：只有一年时，「12 月比年均高 3pp」既可能是季节性，也可能是
    那一年份额本来就在往上走 —— 两者在单年样本里完全共线。期权池的 Nasdaq 就是这种
    情况（月度披露自 2025-01 起，只凑得出 2025 一整年），实测单年算出来的「极差」是
    4.79pp，比它自己的年均漂移还大一个量级，那不是季节性，是趋势被当成了季节性。
    返回 (逐月偏离, 用到的完整年数)，年数不足时返回 None。
    """
    s = share_m.dropna()
    if s.empty:
        return None
    cnt = s.groupby(s.index.year).transform('count')
    s = s[cnt.values == 12]
    yrs = sorted({p.year for p in s.index})
    if len(yrs) < MEFF_MIN_YEARS:
        return None
    dev = s - s.groupby(s.index.year).transform('mean')
    d = dev.groupby(dev.index.month).mean()
    return (d, len(yrs)) if len(d) == 12 else None


def _month_effect_of(pool):
    """挑月份效应极差最大的那个成员，连同它的年均漂移一起返回（都是实测值）。"""
    best = None
    for m in pool.members:
        got = month_effect(LONG_NUM[(pool.pid, m.key)] / LONG_DEN[pool.pid] * 100.0)
        if got is None:
            continue
        d, nyr = got
        rng = float(d.max() - d.min())
        q = QSHARE[(pool.pid, m.key)].dropna()
        drift = (float(q.iloc[-1] - q.iloc[0]) / ((len(q) - 1) / 4.0)) if len(q) > 4 else np.nan
        cand = (rng, m.disp, int(d.idxmax()), float(d.max()), int(d.idxmin()), float(d.min()),
                float(d.get(CUR.month, np.nan)), drift, nyr)
        if best is None or rng > best[0]:
            best = cand
    return best


MEFF = {p.pid: _month_effect_of(p) for p in POOLS}


def quarterly_share_lines(pool):
    """季度口径的真份额长历史 —— 本页跨度最长的一张图。

    **为什么是 `lines` 而不是 `stacked_dual` / `lines_endlabels`。**
    这张图的成员起点各不相同（见图注），短历史成员的前段必须是 `null` 才诚实：
      · `stacked_dual` 的堆叠段与右轴线都**不容忍 null**（段高算成 NaN、线塌到 0），
        而且把缺席成员按 0 堆进去等于宣称「Nasdaq 2011 年份额是 0」—— 那是假的，
        真相是「本仓没有它 2011 年的月度披露」。
      · `lines_endlabels` 首尾任一为 null 直接抛 TypeError，中间的 null 会把线画塌到 0。
      · `heat_matrix` 能吃 null，但 62 列会把格内字号压到 4.6px 下限，读不出数值。
    `lines` 是 17 种里**唯一能安全吃缺口的多线图型**（缺处断开，不平滑）；
    四条线四个颜色，没有撞色。见 docs/CHART_KINDS.md §1.2 / §3.9。
    """
    qidx = QIDX[pool.pid]
    xl = [str(q) for q in qidx]
    ser, facts = [], []
    for m in pool.members:
        v = QSHARE[(pool.pid, m.key)]
        nz = v.dropna()
        ser.append({'name': m.disp, 'color': m.color, 'values': L(v.values)})
        if len(nz):
            facts.append((m.disp, str(nz.index[0]), int(len(nz)),
                          float(nz.iloc[0]), float(nz.iloc[-1])))
    bat, blb = [], []
    for qs, lb in PROFORMA:
        i = _qi(qidx, qs)
        if i is not None:
            bat.append(i)
            blb.append(lb)
    span_y = (len(qidx) - 1) / 4.0
    txt = '；'.join(f'<b>{d}</b> 自 {q0} 起（{k} 季）{v0:.2f}% → {v1:.2f}%'
                    f'（{pp(v1 - v0)}，年均 {pp((v1 - v0) / max((k - 1) / 4.0, 1e-9))}/年）'
                    for d, q0, k, v0, v1 in facts)
    return {
        'kind': 'lines', 'full': True, 'height': 360,
        'fmt': 'f1', 'yfmt': 'f0', 'label_fmt': 'f1',
        'xlabels': xl, 'xstep': 4, 'xrot': 90,
        'end_label': True, 'zero_base': True, 'markers': False,
        'break_at': bat, 'break_label': blb,
        'title': (f'{pool.en}: true share by quarter, {xl[0]} – {xl[-1]} '
                  f'({len(qidx)} quarters, volume-weighted)'),
        'ylab': f'% of official industry total（季度，量加权）',
        'series': ser,
        'src_extra': ('Quarterly share = sum of the quarter\'s monthly volumes divided by the '
                      'sum of the same months\' official industry volumes (ADV x trading days), '
                      'not an average of the three monthly shares'),
        'note': ('<b>季度聚合是量加权，不是把三个月的月份额平均。</b>'
                 '源列全是 ADV（日均），各月交易日数与总量都不同 —— 直接平均会给低量月'
                 '过高权重。这里先把每月 ADV 乘回当月交易日数还原成月成交量，'
                 '分子分母各自求和再相除（<code>Σ当季各月成交量 ÷ Σ当季各月行业分母</code>），'
                 '等价于把一个季度当成一段连续日历来算份额。'
                 '只认三个月齐全的季度，缺月的季度留空让线断开 —— '
                 f'因此最后一季是 {xl[-1]}，而不是只有一个月的 {mlab(LATEST)}'
                 f'（{mlab(LATEST)} 的读数见 Exhibit 1 汇总表）。'
                 '<b>分母与全页一致</b>：'
                 + ('ICE 逐月披露的全美股票/ETF 期权行业 ADV'
                    '（<code>adv_us_equity_options_industry_kcontracts</code>）'
                    if pool.pid == 'opt' else
                    'ICE 的 <code>adv_tapeA/B/C_consolidated_mnsh</code> 三条相加'
                    '（含场外 TRF 内化）')
                 + '，与本页其余各图'
                 + ('（§opt_se§ / §opt_long§）' if pool.pid == 'opt'
                    else '（§cash_stack§ / §cash_se§ / §cash_long§）')
                 + '用的是同一条。'
                 '<b>各成员起点不同，前段留空不补</b>：' + txt + '。'
                 '窗口<b>没有</b>砍到最晚那家的起点 —— 真分母是官方发的，每家可以各自独立除，'
                 '这正是本页有真分母的好处。'
                 + ('<b>MIAX 的深历史是拼接的</b>：2015-04 → 2024-12 取 miaxglobal.com 的 '
                    'indsum API 四所分列（<code>docs/verify/miax.md</code> 实测该 API '
                    '2015-04 → 2026-07 共 136 个月无断档），'
                    '2025-01 起改用 IR 报表口径 —— 该文档定的口径顺序就是「报表为准、'
                    'API 只做回补」。<b>本文件自己量了这道接缝</b>：两种口径在 '
                    f'{MIAX_SPL_N} 个重叠月里相对差 ≤{MIAX_SPL_REL:.2f}%，'
                    f'换算成份额 ≤{MIAX_SPL_BP:.1f}bp（{MIAX_SPL_BP / 100:.3f}pp）—— '
                    '在这张纵轴跨 0–35% 的图上落在一个像素以内，故拼接处不画断点线；'
                    f'{mlab(LATEST)} 那一格与 Exhibit 1 汇总表完全同源，读数一致。'
                    if pool.pid == 'opt' else '')
                 + '<b>两条红色竖虚线是形式数断点</b>（左侧与右侧不可比）：'
                 'ICE 2013-11 才完成 NYSE Euronext 收购，其月度表把 NYSE 数据回填到了全部期间，'
                 '所以 2013Q4 及以前那段讲的是被收购前 NYSE Euronext 的份额，不是 ICE 的；'
                 'Cboe 2017-02 完成对 Bats 的收购，2017 全年为 Bats pro-forma combined，'
                 '2018-01 起才是实际口径。'
                 f'<b>残差桶（{pool.other_lab}）这张图不画</b> —— 它要 100 减去四家之和，'
                 '而四家齐全只有窗口右端那一小段；'
                 + ('残差的完整走势见 §cash_stack§ 的右轴。' if pool.pid == 'cash'
                    else '期权池的残差在 §opt_se§ / §opt_bridge§ 上单列一格。')
                 + '纵轴从 0 起（<code>zero_base</code>），不做隐性截轴。'),
    }


# ── 季度口径的长历史真份额（本页跨度最长的两张）──
for _p in POOLS:
    if len(QIDX[_p.pid]) >= 12:
        add(f'{_p.pid}_q', quarterly_share_lines(_p))
    else:
        print(f'{TICKER}: {_p.zh} 季度长历史图跳过 —— 完整季只有 {len(QIDX[_p.pid])} 个')

# 📌 原来这里还有两张「同比同月份额」图（同一个月的 4 个年份并排）。**2026-08-07 删除**：
# 起止/Δ/桥三张图的窗口已经改成 4 年同月（见 Win），同月比同月这件事已经做在主线上了，
# 再单画一次是同一个信息的第二遍。月份效应的量化没有跟着删 —— 它是「为什么窗口取同月」
# 的理由，移进了页尾口径说明。


# ── 全页最后一张：在共用轴上被压平的成员，换它自己的量程重画一遍 ────────────────
# **为什么必须追加在末尾。** 本页图号由 add() 按追加顺序生成，正文交叉引用走 X('id')
# 占位符、最后由 subst_refs() 统一替换 —— 插在 §cash_long§ 后面会让其后每一张图的号
# 整体位移；追加在末尾一处不动，而且照样能被 §cash_long§ 的图注反过来引用
# （前向引用由 subst_refs 一起解析）。
#
# **为什么不在 §cash_long§ 上就地解决。** 三条路都比拆图差：
#   · 给最矮那条加一根右轴 —— 两条线的单位相同、刻度不同，读者的默认假设是
#     「同一张图上同一个单位就是同一根尺子」，那才是真的骗人；
#   · 把纵轴改成对数 —— 引擎没有 log 轴（docs/CHART_KINDS.md §0 的 17 种里没有），
#     加一种 kind 要重新验收 14 张页；
#   · 去掉那条线 —— 它是池成员不是派生量（2026-08-06 去掉的「四家合计」才是派生量），
#     去掉等于宣称本页不报 MIAX 的现货份额。
# 拆一张、各用各的量程，是「同单位不同量级」唯一不损失信息的做法（docs/VISUAL_QA.md §3.G）。
if _small_set:
    # 横轴只取「这几条自己有数」的那一段：套用全页 187 个月的话，线只占右边三分之一，
    # 左边三分之二是空白 —— 换轴换出来的分辨率又被横轴还回去了。
    _sm_first = min(_cash_share_long[m.key].dropna().index[0] for m in _small_set)
    _sm_idx = [p for p in LONG_IDX if p >= _sm_first]
    _sm_ser = {m.key: _cash_share_long[m.key].reindex(_sm_idx) for m in _small_set}
    _sm_hi = max(float(_sm_ser[m.key].dropna().max()) for m in _small_set)
    _sm_lo = min(float(_sm_ser[m.key].dropna().min()) for m in _small_set)
    # 纵向分辨率的修前修后：两张图都走引擎的 zero_base 分支（charts.js:663
    # `y1 = max × 1.16`、`y0 = 0`），所以「这几条占图高多少」是能算的，不用去量像素。
    _sm_before = (_sm_hi - _sm_lo) / (_cash_top * 1.16) * 100
    _sm_after = (_sm_hi - _sm_lo) / (_sm_hi * 1.16) * 100
    _sm_names = '、'.join(m.disp for m in _small_set)
    _sm_rest = [m for m in _deep_cash if m not in _small_set]
    add('cash_long_small', {
        'kind': 'lines', 'full': True, 'height': 360,
        'fmt': 'f2', 'label_fmt': 'f2',
        'xlabels': [mlab(p) for p in _sm_idx],
        'xstep': max(1, round(len(_sm_idx) / 12)), 'xrot': 90,
        'end_label': True, 'zero_base': True, 'markers': False,
        'title': (f'{POOL_CASH.en}: {", ".join(m.disp for m in _small_set)} true matched share '
                  f'on its own scale, {mlab(_sm_idx[0])} – {mlab(LATEST)}'),
        'ylab': '% of consolidated volume',
        'series': [{'name': m.disp, 'color': m.color, 'values': L(_sm_ser[m.key].values)}
                   for m in _small_set],
        'src_extra': ('Same numerators and same official denominator as the long-history chart; '
                      'only the vertical scale differs'),
        'note': (f'<b>与 Exhibit §cash_long§ 是同一批数，只换了纵轴。</b>那张图四条线共用一根从 0 起的轴，'
                 f'上界由最高的一条（峰值 {_cash_top:.1f}%）定；'
                 f'{_sm_names} 全程只有 {_sm_lo:.2f}–{_sm_hi:.2f}%，'
                 f'在那根轴上整条线的起伏只占图高 <b>{_sm_before:.1f}%</b>，'
                 f'贴着零线看不出形状。换成自己的量程后占 <b>{_sm_after:.1f}%</b>，'
                 f'放大 {_sm_after / _sm_before:.1f} 倍。'
                 f'（两张图都是零基线、上界 = 最大值 × 1.16，所以这两个百分比是算出来的，'
                 f'不是量出来的。）'
                 f'<b>这不是截轴</b>：纵轴仍从 0 起（<code>zero_base</code>），一个点都没被截掉，'
                 f'只是这张图上没有别人的量级来抢轴。'
                 f'<b>谁上这张图由比值定</b>：峰值不到全池最高峰值 1/{SMALL_RATIO:g} 的成员才进来 —— '
                 + '、'.join(f'{m.disp} {_cash_top / _cash_peak[m.key]:.1f}×' for m in _deep_cash)
                 + f'，故本轮只有 {_sm_names} 达标；'
                 + (f'{"、".join(m.disp for m in _sm_rest)} 与最高的一条同一个量级，'
                    f'在 Exhibit §cash_long§ 上本来就读得出来，不重复画。'
                    if _sm_rest else '')
                 + f'<b>横轴只画到 {mlab(_sm_idx[0])} 起</b>：再往左这几条没有数，'
                 f'画上去只是三分之二张空白。'
                 f'分母与全页一致（Tape A+B+C 合并成交量，含场外 TRF 内化），'
                 f'所以这张图的读数与 Exhibit §cash_long§、Exhibit §cash_stack§、Exhibit 1 汇总表逐格同源。'),
    })


# ────────────────────── 9. 末尾核对表：对账表（官方 vs 自算）──────────────────────
_w13 = [p for p in POOL_CASH.idx[-TBL_MONTHS:]]
_ic = RAW['ice']
_tbl_rows = []
for _p in _w13:
    o_sh = _ic['share_nyse_us_cash_matched'].get(_p, np.nan) * 100
    c_sh = A_ICE['cash_calc'].get(_p, np.nan)
    o_op = _ic['share_nyse_equity_options'].get(_p, np.nan) * 100
    c_op = (_ic['adv_nyse_equity_options_kcontracts'].get(_p, np.nan) /
            _ic['adv_us_equity_options_industry_kcontracts'].get(_p, np.nan) * 100)
    _tbl_rows.append({
        'xl': mlab(_p),
        'ind': num(float(_ic['adv_us_equity_options_industry_kcontracts'].get(_p, np.nan)) * 1e3),
        'nyo': num(float(_ic['adv_nyse_equity_options_kcontracts'].get(_p, np.nan)) * 1e3),
        'osh_o': num(o_op, 1) + '%', 'csh_o': num(c_op, 3) + '%',
        'd_o': pp(c_op - o_op),
        'cons': num(float(_ic['__cash_cons__'].get(_p, np.nan))),
        'nyc': num(float(_ic['__nyse_cash__'].get(_p, np.nan))),
        'osh_c': num(o_sh, 1) + '%', 'csh_c': num(c_sh, 3) + '%',
        'd_c': pp(c_sh - o_sh),
    })
REF['recon_table'] = ex[-1]['n'] + 1
table = {
    'n': REF['recon_table'],
    'title': f'近 {TBL_MONTHS} 个月对账表 —— 官方自报份额 vs 本页自算（原始单位，未换算）',
    'idx': '月份',
    'cols': [['期权行业 ADV（张/日）', 'ind'], ['NYSE 期权 ADV（张/日）', 'nyo'],
             ['NYSE 期权份额 · ICE 自报', 'osh_o'], ['NYSE 期权份额 · 本页自算', 'csh_o'],
             ['差', 'd_o'],
             ['现货合并 ADV（百万股/日）', 'cons'], ['NYSE 现货 matched（百万股/日）', 'nyc'],
             ['NYSE 现货份额 · ICE 自报', 'osh_c'], ['NYSE 现货份额 · 本页自算', 'csh_c'],
             ['差', 'd_c']],
    'rows': _tbl_rows,
}


# ────────────────────────────── 10. 口径与方法说明 ──────────────────────────────
_miax_opt_note = (f'{A_MIAX["opt_same"]}/{A_MIAX["opt_n"]} 个月<b>逐位相同</b>'
                  if A_MIAX['opt_n'] else '暂无重叠月')
_ndaq_txt = ('、'.join(f'{q} 官方 {o:.1f}% vs 自算 {c:.1f}%' for q, o, c, _v, _v2 in A_NDAQ[-3:])
             if A_NDAQ else '')

# MIAX 在 4 年期权窗口里的份额变动 —— 口径接缝的影响要挂在这个数上说，所以先算出来
_MIAX_WIN_D = float(WIN_OPT.df['miax_s'].iloc[-1] - WIN_OPT.df['miax_s'].iloc[0])

NOTES = [
    f'<b>本页只回答一个问题：谁真的拿到了份额。</b>全仓十二家交易所里，'
    f'只有北美这两个池能拿到<b>官方发布的行业分母</b> —— 期权用 ICE 的 '
    f'<code>adv_us_equity_options_industry_kcontracts</code>'
    f'（{mlab(CUR)} = {num(float(POOL_OPT.df["pool"][CUR]) / 1e3)} 千张/日），'
    f'现货用 ICE 的 <code>adv_tapeA/B/C_consolidated_mnsh</code> 三条相加'
    f'（{mlab(CUR)} = {num(float(POOL_CASH.df["pool"][CUR]) / 1e6)} 百万股/日）。'
    '所以本页算的是<b>真份额</b>（该家撮合量 ÷ 官方行业总量），'
    '不是「成员之和里的占比」。两者不是精度差别而是口径差别：按成员之和算，'
    '池里少一家、其余各家的「份额」就集体上升；按真分母算，'
    f'现货池四家合计只有 {POOL_CASH.df["sum4_s"][CUR]:.1f}%，'
    f'剩下的 {POOL_CASH.df["other_s"][CUR]:.1f}% 主要是场外内化，一直摆在图上。',

    f'<b>自校验（锚点 A）：ICE 把答案也印出来了。</b>'
    f'<code>series/ice.csv</code> 里的 <code>share_nyse_tapeA/B/C_matched</code>、'
    f'<code>share_nyse_us_cash_matched</code>、<code>share_nyse_equity_options</code> '
    '是 ICE 自己算好的份额。本页用同一张表里的分子分母重算一遍，逐月逐位比对：'
    f'<b>现货合计份额 {A_CASH_N} 个月，最大 |残差| {A_CASH_MAX:.3f}pp'
    f'（{A_CASH_MAX * 100:.1f}bp）</b>，'
    f'四舍五入到 ICE 自报的 3 位小数后 {A_CASH_R3}/{A_CASH_N} 个月完全相同；'
    f'三条 tape 分开算最大 {A_TAPE_MAX:.3f}pp；'
    f'期权份额 {A_OPT_N} 个月最大 {A_OPT_MAX:.3f}pp。'
    '残差全部来自官方自己的印刷舍入（分子分母都印成整数百万股 / 整千张，'
    '份额印到小数点后 3 位），不是算法分歧。'
    '<b>本文件把 0.5pp 设成硬阈值，超过就抛异常拒绝出页</b> —— '
    '份额算法与交易所不一致时，本页所有图都不该存在。'
    f'逐月残差见 §selfcheck§，近 {TBL_MONTHS} 个月的逐格对账见末尾对账表。',

    f'<b>自校验（锚点 B）：两家公司各自独立披露的行业分母对得上。</b>'
    f'MIAX 在自己的 IR 报表里也报全行业 equity & ETF 期权 ADV'
    f'（<code>industry_adv_options_kcontracts</code>），与 ICE 那一列'
    f'{_miax_opt_note}；MIAX 报的全美股票市场 ADV'
    f'（<code>industry_adv_equities_mnshares</code>）与本页由 ICE 三条 tape 相加得到的'
    f'合并成交量在 {A_MIAX["eq_n"]} 个重叠月里最大相对差 '
    f'{A_MIAX["eq_maxrel"] * 100:.3f}%。'
    '两家公司的数据链完全独立（一家是 NYSE 母公司、一家是迈阿密的新进者），'
    '它们对同一个分母的说法一致，是这个分母可信的最强证据。'
    f'另：MIAX 自报的两个份额与本页用 ICE 分母现算的差 ≤ '
    f'{max(MIAX_S_OPT_MAX, MIAX_S_EQ_MAX):.3f}pp（官方只给 1 位小数）。',

    (f'<b>自校验（锚点 C 与 D）：另外两家公司的自报市占也能复算出来。</b>'
     f'Nasdaq 在季度面板里自报美股期权 matched 市占；本页用「Nasdaq 月度总张数 ÷ '
     f'（ICE 行业 ADV × 美股交易日）」现算，{NDAQ_N} 个季度最大差 '
     f'<b>{NDAQ_MAX:.2f}pp</b>（{_ndaq_txt}）。'
     '这条锚点顺带解决了一个口径疑虑：Nasdaq 的期权总量<b>含指数期权</b>'
     '（官方不拆），而行业分母不含 —— 若这块污染很大，本页算出的 Nasdaq 份额'
     '会明显高于它自报的市占；实测两者对得上，说明在这个量级上可以直读，'
     '但读者仍应把 Nasdaq 那一格<b>当作上界</b>。'
     f'BOX（TMX 控股）见 §box§：{BOX_HIT}/{BOX_N} 个季度与 TMX 自报整数一致。'
     if A_NDAQ else '<b>锚点 C 不可用</b>：series/ndaq_q.csv 缺季度市占列。'),

    f'<b>发布门槛：四家的共同最新月 {mlab(LATEST)}。</b>北美四家披露都快 —— '
    f'{mlab(LATEST)} 那一期 ICE / Cboe / MIAX / Nasdaq 在 series/source_dates.csv 里'
    '登记的发布日是同一天（月末后第 5 天），所以本页不存在「被慢成员拖住」的问题，'
    '也不需要像 CME/Cboe/HKEX 那页那样在抬头里点名短板。'
    + ('本期确有成员跑在前面，其更新月份<b>不在本页任何一张图、任何一行表里</b>：'
       + '、'.join(f'{k}（已到 {mlab(m)}）' for k, m in AHEAD) + '。'
       if AHEAD else '本期四家的最新月一致，无人跑在前面。')
    + '<b>本页有两套窗口，别把它们混着读。</b>'
      '①<b>共同窗口</b>（要求成员全齐，用于月度堆叠带与换算链自检）：'
    + '；'.join(f'{p.zh} {mlab(p.start)} – {mlab(p.end)}（{len(p.idx)} 个月）' for p in POOLS)
    + '。它由<b>月度披露起步最晚的那个成员</b>决定'
      '（期权池是 Nasdaq 与 MIAX 的 IR 报表自 2025-01 起；'
      '现货池是 MIAX Pearl 的官网市占 API 自 2020-12 起）。'
      f'②<b>{WIN_YEARS} 年同月窗口</b>（起止对照 / Δ / 归因桥三张图，'
    + '；'.join(f'{w.zh} {mlab(w.start)} → {mlab(w.end)}' for w in (WIN_CASH, WIN_OPT))
    + '）：它<b>不要求成员全齐</b>，因为分母是官方发的、每家可以各自独立除；'
      '期初那个月凑不齐的成员并进残差桶，桶 = 官方总量 − 图上其余各家，加总仍然恒等。'
    + (f'本轮被并进桶的：' + '；'.join(
        f'{w.zh} —— ' + '、'.join(m.disp for m in w.dropped)
        for w in (WIN_CASH, WIN_OPT) if w.dropped) + '。'
       if any(w.dropped for w in (WIN_CASH, WIN_OPT)) else '本轮两个池的成员在期初都齐全。')
    + '<b>期权池因此没有月度堆叠带</b> —— 19 个月的带既看不出趋势，'
      '又与现货那条 68 个月的带不可并读；它的长历史份额在 §opt_long§（月度）与 '
      '§opt_q§（季度）上各有一张。'
      '<b>月度长历史图（§opt_long§ / §cash_long§）只画有深度的成员</b>，'
      '而不是把短序列拉成一小截塞进十五年的月度轴里；'
      '<b>季度长历史图（§opt_q§ / §cash_q§）反过来，四家全画、短的那几家前段留空断线</b> —— '
      '季度轴上只有 60 来个点，一小截也读得清（下一条）。',

    (f'<b>季度长历史份额（§opt_q§ / §cash_q§）：为什么再画一遍、以及聚合方式。</b>'
     f'月度堆叠带（§cash_stack§）有两个限制：一是只能画到「四家齐全」的那段，'
     f'二是逐月读数噪声大 —— 各月交易日数不同、有到期周与假期月。'
     f'§opt_q§ / §cash_q§ 把口径换成季度：'
     f'<b>份额 = Σ(当季各月成交量) ÷ Σ(当季各月官方行业分母)</b>，'
     f'月成交量 = 该月 ADV × 该月美股交易日数。'
     f'<b>这是量加权，不是把三个月的月份额简单平均</b> —— 源列全是日均值，'
     f'简单平均会给低量月（假期月、交易日少的月）过高权重。'
     f'只认三个月齐全的季度，所以最后一季是 '
     + '、'.join(sorted({str(QIDX[p.pid][-1]) for p in POOLS if len(QIDX[p.pid])}))
     + f'，而不是只有一个月的 {mlab(LATEST)}。'
       '窗口<b>不砍到最晚那家的起点</b>：真分母是官方发的，每家各自独立除即可，'
       '短历史成员前段留空、线断开。各家实际起点 —— '
     + '；'.join(
         f'<b>{p.zh}</b>：' + '、'.join(
             f'{m.disp} {QSHARE[(p.pid, m.key)].dropna().index[0]}'
             f'（{len(QSHARE[(p.pid, m.key)].dropna())} 季）'
             for m in p.members if len(QSHARE[(p.pid, m.key)].dropna()))
         for p in POOLS)
     + '。期权池的 MIAX 深历史取 miaxglobal.com 的 indsum API 四所分列（2015-04 起，'
       '<code>docs/verify/miax.md</code> 实测 136 个月无断档），2025-01 起改用 IR 报表口径 '
       '—— 该文档定的口径顺序就是「报表为准、API 只做回补」。'
       f'接缝由本文件实测：{MIAX_SPL_N} 个重叠月里相对差 ≤{MIAX_SPL_REL:.2f}%，'
       f'换算成份额 ≤{MIAX_SPL_BP:.1f}bp，故未画断点线。'
       '<b>两张图上各有两条红色形式数断点线</b>：'
       'ICE 2013-11 才完成 NYSE Euronext 收购，其月度表把 NYSE 数据「for comparison '
       'purposes」回填到了全部期间（docs/verify/verify_ice.md §5.6），'
       '所以 2013Q4 及以前那段讲的是被收购前 NYSE Euronext 的份额；'
       'Cboe 2017-02 完成对 Bats 的收购，2017 全年为 Bats pro-forma combined。'
       '这两条断点在月度堆叠带 §cash_stack§ 上不存在（那张图的窗口本来就在断点右边），'
       '是把跨度拉到十五年之后才浮出来的。'),

    (f'<b>{WIN_YEARS} 年窗口为什么必须取同一个月份（Jul vs Jul），不能随便挑期初月。</b>'
     f'期权与现货的成交量都有明显的月份效应（到期周、假期月、季末再平衡），'
     f'而它改变的不只是总量、还有订单流的构成，所以<b>份额本身也带季节性</b>。'
     + '；'.join(
         f'<b>{p.zh}</b> 里月份效应最大的是 {MEFF[p.pid][1]}，份额极差 '
         f'<b>{MEFF[p.pid][0]:.2f}pp</b>'
         f'（{MEFF[p.pid][2]} 月最高 {pp(MEFF[p.pid][3])}、'
         f'{MEFF[p.pid][4]} 月最低 {pp(MEFF[p.pid][5])}，{MEFF[p.pid][8]} 个完整年）'
         + (f'，而它季度份额的年均漂移只有 {pp(MEFF[p.pid][7])}/年'
            if np.isfinite(MEFF[p.pid][7]) else '')
         for p in POOLS if MEFF[p.pid])
     + '。口径 = 同月份额减该年份额均值，只用 12 个月齐全的完整年，本页自算不引用外部；'
       f'完整年不足 {MEFF_MIN_YEARS} 年的成员不参与这项统计（期权池的 Nasdaq 只凑得出'
       ' 2025 一整年，单年样本里季节性与趋势完全共线，算出来的「极差」是趋势的伪装）。'
       '<b>一次季节性摆动就抵得上一年的结构性变化</b> —— 所以环比读不干净，'
       '「最新月 vs 池共同窗口的期初月」也读不干净（那个期初月是被数据可得性决定的，'
       '不是被日历决定的）。起止对照 / Δ / 归因桥三张图因此一律取 '
     + '、'.join(f'{mlab(w.start)} → {mlab(w.end)}' for w in (WIN_CASH, WIN_OPT))
     + '，同月比同月，季节性整个消掉，剩下的就是结构性变化。'
       '📌 2026-08-07 之前这件事是靠另外两张「同月并排」图单独做的，'
       '现在做进了主线窗口，那两张图已删。'
     if all(MEFF[p.pid] for p in POOLS) else
     '<b>月份效应本轮算不出来</b>：没有任何成员凑得出 '
     f'{MEFF_MIN_YEARS} 个 12 月齐全的完整年。'
     f'{WIN_YEARS} 年窗口仍取同月，理由不依赖这项统计。'),

    f'<b>主口径是定基名义额，而北美这两个池是它的退化情形 —— 这件事本身是结论。</b>'
    f'定基名义额 = 张数 × 乘数 × 2019-01 基期价格（汇率同锁基期），'
    '存在的理由是张数不可跨产品比较：乘数是交易所自选的产品设计'
    '（CME E-mini 每点 $50 vs Micro 每点 $5，差 10 倍）。'
    + (f'实测反例：{JPX_TXT} —— 同一段窗口两种口径<b>符号相反</b>。' if JPX_TXT else '')
    + '而北美这两个池<b>池内规格完全统一</b>：多重挂牌股票/ETF 期权全行业 '
      f'{POOL_OPT.mult_lab}，现货本来就以股计。乘数与基期价格对池内每一家都是同一个常数，'
      '⇒ <b>份额与增长率在两种口径下恒等</b>。§unit_check§ 把两条曲线画在同一张图上做了'
      f'实测校验（偏离 {OPT_DIDX:.2e}，阈值 1e-9，超过即抛异常）。'
      '这也是本页敢直接用张数做份额的唯一理由。',

    f'<b>📌 已知缺口：美元名义额算不出来，本页也不装作算得出。</b>'
    f'<code>series/contract_specs.csv</code> 的 <code>{OPT_SPEC_ID}</code> 与 '
    f'<code>{CASH_SPEC_ID}</code> 两行，<code>base_price_local</code> '
    + ('都是空的' if (OPT_P0 is None and CASH_P0 is None) else '有缺')
    + '（前者要「2019-01 按成交量加权的标的均价」、后者要「2019-01 全美合并成交金额 ÷ '
      '合并成交股数」，两个都没找到官方单一字段，检索路径写在该表的 notes 列里）。'
      '所以本页的名义额只报到<b>股当量</b>（张数 × 100 股），不报美元水平值。'
      '<b>这不影响本页任何结论</b> —— 份额与增长率都与那个常数无关（见上一条）；'
      '受影响的只有「这个市场折成美元有多大」这一个问题，而本页不回答它。',

    '<b>分母含场外，这是现货池最容易读错的一点。</b>Tape A/B/C 的 consolidated volume '
    '<b>包含场外（TRF）内化成交</b>，所以现货池的残差桶（§cash_stack§ 右轴那条线、'
    f'{mlab(CUR)} = {POOL_CASH.df["other_s"][CUR]:.1f}%）里主要不是别的交易所，'
    '而是券商与做市商在自己内部撮合掉的单子。'
    '期权池没有这个问题：美股期权必须在交易所成交，'
    f'所以那个残差桶（{mlab(CUR)} = {POOL_OPT.df["other_s"][CUR]:.1f}%）'
    '基本就是 BOX 与 MEMX 两家。'
    '<b>两个池的「其他」不是同一种东西，不要横向对比这两个数。</b>',

    '<b>换算链逐条写明（张数 / 股数怎么变成同一个规范单位）。</b>'
    + '；'.join(
        f'<b>{m.disp}</b> = <code>{m.col}</code>'
        + (f' × {m.unit:,.0f}' if m.unit != 1 else '')
        + (' ÷ 美股交易日数' if m.per_day else '')
        + (f'（缺月回落 <code>{m.alt}</code>）' if m.alt else '')
        for p in POOLS for m in p.members)
    + '。美股交易日数全页统一取 ICE 的 <code>trading_days_us_equities</code>：'
      'ICE 与 Nasdaq 各自披露一份日历，实测 186 个重叠月里只有 2015-08 一个月不同，'
      'MIAX 那份与 ICE 全等 —— 但两份混用会让同一个月的 ADV 出现两个值，'
      '差异小到不会有人发现，所以只认一份。'
      '本页两个池全部以美元计价，<code>series/fx.csv</code> 不参与任何计算。',

    '<b>没有口径断点，全页也确实一条断点线都没画。</b>两个池在各自的共同窗口内'
    '都没有并购并表或口径重分类，故 payload 里没有任何 <code>break_at</code>。'
    '<b>期权池的月度共同窗口</b>（19 个月）只用 MIAX 的 IR 报表口径，不拼接。'
    f'但 <b>{WIN_YEARS} 年同月窗口与两张长历史图必须拼接</b>：'
    f'{mlab(WIN_OPT.start)} 那一头 IR 报表根本不存在，只有官网 API。'
    '两个源的落差是本文件实测的，不是引用：'
    f'{MIAX_SPL_N} 个重叠月里 API 比报表稳定低 ≤{MIAX_SPL_REL:.2f}%，'
    f'换算成份额 ≤<b>{MIAX_SPL_BP:.1f}bp</b>（{MIAX_SPL_BP / 100:.3f}pp）。'
    f'<b>方向是已知的，不是不确定性</b>：期初走 API（偏低）、期末走报表，'
    f'所以 §opt_se§ 里 MIAX 那段 {WIN_YEARS} 年涨幅'
    f'（{_MIAX_WIN_D:+.2f}pp）被<b>高估</b>至多 {MIAX_SPL_BP / 100:.2f}pp，'
    f'真值不低于 {_MIAX_WIN_D - MIAX_SPL_BP / 100:+.2f}pp —— 结论不变，但读者有权知道。'
    f'落差小于图上标签的分辨率，故拼接处不画断点线。'
    '现货池的 MIAX 只用官网 API 一个源（2020-12 起连续），'
    f'与 IR 报表那列整数在 {A_MIAX["api_n"]} 个重叠月里最大差 '
    f'{A_MIAX["api_maxabs"]:.2f} 百万股/日 —— 纯粹是报表取整，不是口径差。'
    'Nasdaq 现货则做了一次<b>同口径拼接</b>：2025-01 起用 IR 报表的当月总量，'
    '更早的月份用 nasdaqtrader 市占 xlsx 的三个盘口相加，'
    '两者在 18 个重叠月里相对差 ≤0.011%（两条都是 Nasdaq 官方，不是不同口径）。',

    '<b>与 build/exchanges.py（CME / Cboe / HKEX）那页的分工。</b>那页没有公约分母，'
    '只能用指数化与同比回答「谁在跑赢」；本页有官方分母，回答的是「谁真的拿到了份额」，'
    '而且份额是零和的（§cash_delta§ / §opt_delta§ 的柱之和恒为 0）。'
    '两页唯一重叠的成员是 Cboe，且看的是它完全不同的两块业务'
    '（那页看美股期权总量与指数期权占比，本页看它的 multiply-listed 期权与美股现货撮合份额）。'
    '本页不改动那页的任何逻辑，也不共用它的数据结构。',
]

# ────────────────────────────── 11. 抬头与 payload ──────────────────────────────
_opt_rank = sorted(((m.disp, float(POOL_OPT.df[m.key + '_s'][CUR])) for m in POOL_OPT.members),
                   key=lambda kv: -kv[1])
_cash_rank = sorted(((m.disp, float(POOL_CASH.df[m.key + '_s'][CUR])) for m in POOL_CASH.members),
                    key=lambda kv: -kv[1])



def _delta_rank(pool):
    """窗口内份额变动排序。**残差桶也算一格** —— 份额是零和的，
    若只在四家成员里挑最大跌幅，而实际上跌得最多的是「其他」，抬头就写错了。"""
    items = [(m.disp, m.key + '_s') for m in pool.members] + [(pool.other_short, 'other_s')]
    d = [(nm, float(pool.df[c].iloc[-1] - pool.df[c].iloc[0])) for nm, c in items]
    return sorted(d, key=lambda kv: -kv[1])


_opt_d = _delta_rank(WIN_OPT)
_cash_d = _delta_rank(WIN_CASH)

# 官方发布日：横截面页取**成员里最晚**的那一个，任一成员查不到就整体省略。
def _load_source_dates():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SOURCE_DATE = _load_source_dates().latest_of(
    SERIES, ['ice', 'cboe', 'miax', 'ndaq'], {k: LATEST for k in ('ice', 'cboe', 'miax', 'ndaq')})

payload = {
    'ticker': TICKER,
    'tracker': 'North America Exchange Competition — ICE / Cboe / MIAX / Nasdaq',
    'title': f'北美交易所竞争（ICE·NYSE / Cboe / MIAX / Nasdaq）：真份额 — {zh(LATEST)}',
    'data_through': str(LATEST),
    'through_label': f'{zh(LATEST)}（四家共同最新月）',
    'subtitle': (f'数据源：四家官方月度披露 + TMX 季度 MD&A · '
                 f'起止对照取 {WIN_YEARS} 年同月窗口 '
                 f'{mlab(WIN_CASH.start)}→{mlab(WIN_CASH.end)} · '
                 # 抬头三行（subtitle / headline / hub_line）由 page.js 用 textContent 写入，
                 # 里面放 HTML 会原样印出「<b>」四个字符 —— 这里一律纯文本。
                 f'份额分母取「官方发布的行业总量」，非成员之和 · '
                 f'与 ICE 自报份额逐月对账（最大残差 {A_CASH_MAX * 100:.1f}bp）· '
                 '版式仿 Goldman Sachs GIR · 仅图，无评论'),
    'headline': (f'期权真份额：'
                 + '、'.join(f'{d} {v:.1f}%' for d, v in _opt_rank)
                 + f'（其他所 {POOL_OPT.df["other_s"][CUR]:.1f}%）· 现货真份额：'
                 + '、'.join(f'{d} {v:.1f}%' for d, v in _cash_rank)
                 + f'（场外与其他 {POOL_CASH.df["other_s"][CUR]:.1f}%）· '
                 + f'{WIN_YEARS} 年同月份额变动（{mlab(WIN_OPT.start)}→{mlab(WIN_OPT.end)}）：'
                   f'期权 {_opt_d[0][0]} {pp(_opt_d[0][1])} 最多、'
                   f'{_opt_d[-1][0]} {pp(_opt_d[-1][1])} 最少；'
                 + f'现货 {_cash_d[0][0]} {pp(_cash_d[0][1])} 最多、'
                   f'{_cash_d[-1][0]} {pp(_cash_d[-1][1])} 最少 · '
                 + f'对账：{A_CASH_N} 个月与 ICE 自报份额最大差 {A_CASH_MAX * 100:.1f}bp'),
    'hub_line': (f'真份额（官方分母）：期权 {_opt_rank[0][0]} {_opt_rank[0][1]:.1f}% 居首；'
                 f'现货四家合计 {POOL_CASH.df["sum4_s"][CUR]:.1f}%'),
    'source': SRC,
    'xlabels': XL_CASH,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.5% 步长整列印成重复数字，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    'exhibits': axisfmt.fix_all(ex),
    'table': table,
    'notes': NOTES,
    'footer': (f'北美交易所竞争 · ICE(NYSE) / Cboe / MIAX / Nasdaq，TMX(BOX) 季度对照 · '
               f'<b>份额分母 = 官方发布的行业总量</b>'
               f'（期权 {num(float(POOL_OPT.df["pool"][CUR]) / 1e3)} 千张/日、'
               f'现货 {num(float(POOL_CASH.df["pool"][CUR]) / 1e6)} 百万股/日，{mlab(CUR)}）· '
               f'与 ICE 自报份额逐月对账 {A_CASH_N} 个月，最大残差 {A_CASH_MAX * 100:.1f}bp · '
               f'共同最新月 {mlab(LATEST)} · '
               'charts only, no commentary · personal research use'),
}
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE

# 图号占位符 → 真数字。放在最后一步，所有图都追加完之后统一替换；
# 引用了不存在的图 id 会在这里 KeyError 当场炸，不会静默留一个 §xxx§ 在页面上。
payload = subst_refs(payload)


def main():
    payload_guard.write_dash(OUT, payload, TICKER)
    print(f'共同最新月 {LATEST}')
    for p in POOLS:
        print(f'  {p.pid:5s} {p.zh}: {p.start} → {p.end}（{len(p.idx)} 个月）'
              f' 分母 {float(p.df["pool"][CUR]) / p.unit_div:,.0f} {p.unit_lab}'
              f' | 四家合计 {p.df["sum4_s"][CUR]:.2f}% | 其他 {p.df["other_s"][CUR]:.2f}%')
    print(f'锚点 A ICE 自报 vs 自算：现货 {A_CASH_N} 个月 max {A_CASH_MAX:.4f}pp'
          f'（3 位小数全等 {A_CASH_R3}/{A_CASH_N}）；期权 max {A_OPT_MAX:.4f}pp；'
          f'tape max {A_TAPE_MAX:.4f}pp')
    print(f'锚点 B MIAX vs ICE 分母：期权逐位相同 {A_MIAX["opt_same"]}/{A_MIAX["opt_n"]}；'
          f'现货最大相对差 {A_MIAX["eq_maxrel"] * 100:.4f}%')
    print(f'锚点 C Nasdaq 自报季度市占：{NDAQ_N} 个季度 max {NDAQ_MAX:.3f}pp')
    print(f'锚点 D TMX/BOX：{BOX_HIT}/{BOX_N} 个季度四舍五入一致')
    print(f'换算链自检：期权池 指数差 {OPT_DIDX:.2e} 份额差 {OPT_DSHARE:.2e}pp；'
          f'现货池 指数差 {CASH_DIDX:.2e} 份额差 {CASH_DSHARE:.2e}pp')
    print(f'MIAX 期权源拼接：API(2015-04起) → IR 报表(2025-01起)，'
          f'{MIAX_SPL_N} 个重叠月相对差 ≤{MIAX_SPL_REL:.2f}%（份额 ≤{MIAX_SPL_BP:.1f}bp）')
    for p in POOLS:
        q = QIDX[p.pid]
        if not len(q):
            continue
        print(f'季度长历史 {p.pid:5s} {q[0]} → {q[-1]}（{len(q)} 季 / {(len(q) - 1) / 4:.2f} 年，量加权）')
        for m in p.members:
            s = QSHARE[(p.pid, m.key)].dropna()
            if not len(s):
                print(f'    {m.disp:18s} 无完整季')
                continue
            k = len(s)
            print(f'    {m.disp:18s} {s.index[0]} → {s.index[-1]}（{k:2d} 季）'
                  f' {s.iloc[0]:6.2f}% → {s.iloc[-1]:6.2f}%'
                  f'  Δ {s.iloc[-1] - s.iloc[0]:+6.2f}pp'
                  f'  年均 {(s.iloc[-1] - s.iloc[0]) / max((k - 1) / 4.0, 1e-9):+5.2f}pp/年'
                  f'  峰 {s.max():.2f}%@{s.idxmax()} 谷 {s.min():.2f}%@{s.idxmin()}')
        me = MEFF[p.pid]
        if me:
            print(f'    月份效应最大者 {me[1]}（{me[8]} 个完整年）：极差 {me[0]:.2f}pp'
                  f'（{me[2]} 月 {me[3]:+.2f}pp / {me[4]} 月 {me[5]:+.2f}pp，'
                  f'{CUR.month} 月 {me[6]:+.2f}pp）vs 年均漂移 {me[7]:+.2f}pp/年')
        else:
            print(f'    月份效应：无成员凑得出 {MEFF_MIN_YEARS} 个完整年')
    for w in (WIN_CASH, WIN_OPT):
        print(f'{w.years}年同月窗口 {w.pid:5s} {mlab(w.start)} → {mlab(w.end)}'
              + (f'  并桶: {"、".join(m.disp for m in w.dropped)}' if w.dropped else '  成员齐全'))
        for m in list(w.members) + [None]:
            k, nm = ('other', w.other_short) if m is None else (m.key, m.disp)
            v0 = float(w.df[k + '_s'].iloc[0])
            v1 = float(w.df[k + '_s'].iloc[-1])
            print(f'    {nm:22s} {v0:6.2f}% → {v1:6.2f}%   Δ {v1 - v0:+5.2f}pp')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 对账表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
