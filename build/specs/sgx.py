# -*- coding: utf-8 -*-
"""SGX（新加坡交易所）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/sgx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页的看点：SGX 卖的是「别人家的标的」━━
SGX 衍生品的头部产品全部是**离岸挂牌的他国标的**，与 JPX / HKEX 是同标的头对头：

    2026-06 实测（占当月 SGX 衍生品总成交 34,315,225 张的比重）
      FTSE 中国 A50 期货    11,724,378 张   34.2%   ← 与 HKEX 的 A 股衍生品同赛道
      外汇期货合计          10,268,040 张   29.9%   （USD/CNH + INR/USD 为主）
      铁矿石衍生品           5,354,979 张   15.6%
      日経225 期货              748,048 张    2.2%   ← 与 JPX 的旗舰合约同标的

所以 A50 与日経225 两条线在本页必须单列、不许并进「股指期货合计」里看不见 ——
它们是判断 SGX 竞争位置的直接读数。

━━ 为什么按「共同起点」分组 ━━
本页三档起点：2015-01（主体，含换手率）、2020-07（FTSE 台湾）、2025-11（加密）。
（换手率原本是第四档「2018-03 起」，那不是源的边界而是解析的边界：官方 2018-03 之前
把它印在月报 p8 的 `Turnover Velocity` 表里而不是 p2 的 At-A-Glance，抓取器只读 p2。
2026-08 给 fetch/sgx.py 加了 p8 兜底后回补 38 个月，这一列与主体同起点 ——
两处来源逐格等价、接缝不产生断点，证据见 fetch/sgx.py 口径坑 18。）
同组混起点会逼底座二选一：砍成最短窗口，或给平滑类图型喂 null
（gs_line 会 null.toFixed() 抛 TypeError，整张卡片之后的 exhibit 全不渲染，
见 docs/CHART_KINDS.md §1.2）。所以起点不同的列一律各成一组。

━━ 量价分解的口径核查（2026-08-07，结论：✅ 同口径，可分解）━━
恒等式 `成交额 ≡ 成交股数 × 加权平均成交价`，均价 = sec_turnover_sgdmn ÷ sec_turnover_mnshares。
这是定义式，没有假设、没有误差；**唯一要证的是分子分母同口径**。四条证据：

1. **同表同段相邻两行**。两列都出自月报 p2 的 SGX Statistics At A Glance，
   实测 2026-06 与 2015-01 两期的行序完全一样：
   `Turnover Volume (Million Shares)` 在第 7 行、`Turnover Value ($Million)` 在第 10 行
   （中间夹的是各自的上月/本月两个数）。两行都**没有脚注记号**，官方没有给它们不同的覆盖口径。
2. **改名逐代同步**。把 138 期 PDF 的这两行标签全扫一遍，共 9 个世代
   （大小写反复横跳 + 2025-12 起 `Securities Market` → `Stock Market`），
   **每一代都是两行一起改**，没有任何一期出现「一行改了另一行没改」——
   覆盖范围若变过，只会同时作用于分子与分母，比值不受污染。
3. **粒度一致，且金额那一行可反算验证**。两列都是**当月总量**（不是日均）。
   金额列满足 `sec_turnover_sgdmn / sec_trading_days = sdav_sgdmn`，
   全 138 个月最大相对误差 0.051%（= SDAV 取整到 S$mn 的舍入）。
   ⚠ 对照组：衍生品那一侧这个恒等式**不成立**（见下方 notes 第 3 条），所以证券侧成立是有信息量的。
4. **12 个月滚动块可与官方 FYTD 对账**。用月度序列自己滚 FY2026（Jul-25–Jun-26）
   得 455,679 S$mn，官方报告 p3 的 FYTD = 455,677、新闻稿写 "S$455.7 billion" ——
   差 2（12 个整数月度值的舍入），相对差 0.0004%。衍生品 FYTD 更是逐位相同
   （363,489,920）。说明月度序列完整无缺、可安全聚合成年度块。

**均价序列有没有口径跳变？没有。** 逐月对数变动只有 2016-03 一个月 |z|>3（-44.7%），
而那一个月是**分母在动**（成交股数 22,750 → 46,539 百万股翻倍，金额只涨 13%），
是仙股放量、不是口径换代；把跳变前后各 6 个月的几何均价一比，前五大跳变全部回归、不留台阶。
唯一留下台阶的是 2024-05 之后（前 6 月均价 0.749 → 后 6 月 1.011），
但那不是某一个月的断点，而是 2024-2026 大盘股行情驱动的**连续 12 个月的爬升**
（12 个月滚动中位数 0.75 → 0.94 → 1.08 逐级抬升，不是一次跃迁），
且与 2025-12 的官方改名相差 19 个月，时间对不上。

⚠ **「价」是什么、不是什么**：这里的均价 = 成交额 ÷ 成交股数 = **成交量加权平均成交价**，
它同时含（a）市场涨跌与（b）成交结构变化（仙股 vs 大盘股的成交占比此消彼长）。
本仓没有 STI 点位序列，**分不开 a 与 b**，所以任何图注都不许把它说成指数收益率。
（对照：TMX 的 series 里有 `tsx_composite_close`，那一家才拆得开。）

━━ 有意不上页面的列，以及理由 ━━
· sec_trading_days —— 分母。而且它是**证券市场**的交易日数，
  拿去除衍生品月量得不到 DDAV（实测 2026-06 反推 21.19 天、官方写 21），
  上页面只会诱导别人做错误的除法。
· deriv_swaps_vol_contracts —— 掉期，2026-06 = 7,662 张，占总量 0.02%，
  与期货同框会被压成一条贴地线。
· vol_msci_taiwan_futures_contracts —— **已停发的死列**：2021-11 之后无值，
  2021-01 还有一个内部空洞，2021-02 起全是 0。既不能进平滑图型，
  留在页面上也只是一条归零线。台湾敞口改看 FTSE 那条（2020-07 起）。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'sgx.csv')


# ── 断点能读 CSV 就读 ──────────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。这个函数只做
# 「列 → 第一个有值的月份」的字典查询，不含统计口径。
# 读不到就返回 None —— 缺文件不许在 import 期抛异常。
def _first_present(col):
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if col in r and r[col].strip():
                    return r['month']
    except OSError:
        pass
    return None


# GIFT Nifty 的计数口径断点月。这一条**只能写死** —— CSV 里没有任何标记列能
# 指出它，依据是官方报告脚注「For periods prior to June 2023, volumes are
# computed based on higher of buy and sell lots」（见 docs/verify/sgx.md 口径坑 3）。
# 抽成常数：_breaks() 与页尾口径说明里的污染期算术都从它推，不各写一份。
_NIFTY_BREAK = '2023-07'


def _madd(m, k):
    """'YYYY-MM' + k 个月。断点月的衍生日期（+11 / +23）用它算，不手写第二份日期。"""
    y, mo = int(m[:4]), int(m[5:7]) + k
    return f'{y + (mo - 1) // 12:04d}-{(mo - 1) % 12 + 1:02d}'


def _yoy_gap(col):
    """一列的单月同比 vs 12 个月滚动合计同比，全期逐月对比（全部从 CSV 现算）。

    页尾口径说明引用的分歧数字都出自这里，一个数字不写死。本页的月总量列都是
    当月合计口径，滚动合计 = 12 个月直加，无需交易日权重。「符号相反」与
    tools/check_yoy_caliber.py 同一条死区：两侧 |同比| ≥ 0.5pp 才计
    （贴零的正负是舍入不是方向分歧）。
    返回 (可比月数, 符号相反月数, 分歧最大的月份, 该月单月%, 该月滚动%,
          最新有滚动同比的月份, 该月滚动%)；算不出返回 (None,) * 7。
    """
    try:
        with open(_CSV, encoding='utf-8') as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return (None,) * 7
    months = [r['month'] for r in rows]           # series/*.csv 按月升序、逐月连续
    vals = []
    for r in rows:
        v = (r.get(col) or '').strip()
        try:
            vals.append(float(v) if v else None)
        except ValueError:
            vals.append(None)
    mom, ttm = {}, {}
    for i, m in enumerate(months):
        a = vals[i]
        if i >= 12 and a is not None and vals[i - 12] not in (None, 0.0) \
                and a * vals[i - 12] > 0:
            mom[m] = (a / vals[i - 12] - 1) * 100.0
        if i >= 23 and all(v is not None for v in vals[i - 23:i + 1]):
            s1, s0 = sum(vals[i - 11:i + 1]), sum(vals[i - 23:i - 11])
            if s0 != 0 and s1 * s0 > 0:
                ttm[m] = (s1 / s0 - 1) * 100.0
    both = sorted(m for m in mom if m in ttm)
    if not both:
        return (None,) * 7
    flips = [m for m in both
             if mom[m] * ttm[m] < 0 and abs(mom[m]) >= 0.5 and abs(ttm[m]) >= 0.5]
    worst = max(both, key=lambda m: abs(mom[m] - ttm[m]))
    last = max(ttm)
    return (len(both), len(flips), worst, mom[worst], ttm[worst], last, ttm[last])


# 页尾口径说明用的两组实测（FTSE 台湾、新债券挂牌）。GIFT Nifty 不算这组数 ——
# 它的全期 mom/ttm 对比会跨 2023-07 计数断点，两种口径都被污染，
# 算出来的「分歧」混着断点效应，不能当口径论据（那张的理由是污染期算术，见 notes）。
_GT = _yoy_gap('vol_ftse_taiwan_futures_contracts')
_GB = _yoy_gap('new_bond_listings')


# ══ 名词释义要用的几组结构性实测（全部从 series/sgx.csv 现算）════════════════
# 与上面那两组同一条规矩：释义里出现的数一个都不写死。这几个函数只做算术，
# 不含任何当月判断 —— 释义是「这些词是什么意思」，一年到头是同一段。
def _rows():
    """series/sgx.csv 的全部行；读不到返回空表（import 期不许因缺文件抛异常）。"""
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, c):
    v = (r.get(c) or '').strip()
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _sdav_identity():
    """证券侧恒等式 `当月成交额 ÷ 当月证券交易日数 = SDAV` 的实测偏差。

    返回 (可算月数, 最大相对差%)；算不出返回 (None, None)。
    这条是 fetch/sgx.py 的解析自检（_crosscheck）用的同一条恒等式。
    """
    e = []
    for r in _rows():
        t, d, s = (_num(r, 'sec_turnover_sgdmn'), _num(r, 'sec_trading_days'),
                   _num(r, 'sdav_sgdmn'))
        if t and d and s:
            e.append(abs(t / d / s - 1) * 100.0)
    return (len(e), max(e)) if e else (None, None)


def _ddav_days():
    """衍生品侧那条恒等式**不成立**的实测（fetch/sgx.py 口径坑 6）。

    用官方两个数反算隐含交易日数 `当月成交合计 ÷ DDAV`，再与当月**证券市场**
    交易日数比。返回 (可算月数, 与证券交易日不等的月数, 隐含天数下界, 上界,
    误用证券交易日的相对差中位%, 最大%)；算不出返回 (None,) * 6。
    """
    imp, ne, rel = [], 0, []
    for r in _rows():
        v, dd, d = (_num(r, 'deriv_vol_contracts'), _num(r, 'ddav_contracts'),
                    _num(r, 'sec_trading_days'))
        if v and dd and d:
            x = v / dd
            imp.append(x)
            if abs(x - d) > 0.005:            # 官方交易日是整数，半天以内算相等
                ne += 1
            rel.append(abs(v / d / dd - 1) * 100.0)
    if not imp:
        return (None,) * 6
    rel.sort()
    return (len(imp), ne, min(imp), max(imp), rel[len(rel) // 2], max(rel))


def _swaps_gap():
    """「当月成交合计 = 期货 + 期权 + 掉期」与掉期的占比。

    掉期不上页面（见文件抬头），所以页上两条「其中」相加必然比合计少一点点 ——
    释义里要把这个缺口点名，不然读者会以为漏了数。
    返回 (可算月数, 三项逐位相加等于合计的月数, 最大残差张数,
          掉期占合计中位%, 最大%)；算不出返回 (None,) * 5。
    """
    sh, exact, res = [], 0, []
    for r in _rows():
        tot, fu, op, sw = (_num(r, 'deriv_vol_contracts'),
                           _num(r, 'deriv_futures_vol_contracts'),
                           _num(r, 'deriv_options_vol_contracts'),
                           _num(r, 'deriv_swaps_vol_contracts'))
        if tot and None not in (fu, op, sw):
            sh.append(sw / tot * 100.0)
            d = abs(fu + op + sw - tot)
            res.append(d)
            if d < 0.5:
                exact += 1
    if not sh:
        return (None,) * 5
    sh.sort()
    return (len(sh), exact, max(res), sh[len(sh) // 2], max(sh))


def _eqix_share():
    """本页单列的指数产品占「股指期货合计」多少 —— 证明合计**不是**它们的和。

    返回 (同组三条的中位占比%, 再加上另两组里 GIFT Nifty 与 FTSE 台湾的中位占比%)；
    算不出返回 (None, None)。缺值按 0 计（那两条各有自己的起点，缺的月份本就没有量）。
    """
    a, b = [], []
    for r in _rows():
        tot = _num(r, 'vol_equity_index_futures_contracts')
        if not tot:
            continue
        p3 = [_num(r, c) for c in ('vol_a50_futures_contracts',
                                   'vol_nikkei225_futures_contracts',
                                   'vol_msci_singapore_futures_contracts')]
        if any(x is None for x in p3):
            continue
        p2 = [_num(r, c) or 0.0 for c in ('vol_nifty50_futures_contracts',
                                          'vol_ftse_taiwan_futures_contracts')]
        a.append(sum(p3) / tot * 100.0)
        b.append((sum(p3) + sum(p2)) / tot * 100.0)
    if not a:
        return (None, None)
    a.sort()
    b.sort()
    return (a[len(a) // 2], b[len(b) // 2])


def _velocity_stats():
    """换手率：印刷精度，以及「拿本页两列反推」为什么不成立。

    返回 (月数, 整数月数, 读数下界, 上界, 与「当月成交额 ÷ 月末总市值」之比的
          下界 / 中位 / 上界)；算不出返回 (None,) * 7。
    倍数不是常数正是论据本身：官方脚注说明分子分母都只取 primary listed
    securities，而本页那两列是全市场口径。
    """
    v, mult = [], []
    for r in _rows():
        x = _num(r, 'turnover_velocity_pct')
        t, m = _num(r, 'sec_turnover_sgdmn'), _num(r, 'mktcap_sgdmn')
        if x:
            v.append(x)
            if t and m:
                mult.append(x / (t / m * 100.0))
    if not v or not mult:
        return (None,) * 7
    mult.sort()
    return (len(v), sum(1 for x in v if x == int(x)), min(v), max(v),
            min(mult), mult[len(mult) // 2], max(mult))


def _rto_only_months():
    """家数 = 0 而募资额 > 0 的月数 —— 「募资额含 RTO、家数不含」的直接证据。"""
    n = 0
    for r in _rows():
        c, f = _num(r, 'ipos_count'), _num(r, 'ipo_funds_sgdmn')
        if c == 0 and f and f > 0:
            n += 1
    return n


def _fx_share():
    """本页单列的两条外汇产品占「外汇期货合计」多少 —— 同 `_eqix_share()` 的用途。

    Ex15 与汇总表把「合计 + 两条分项」画在同一根轴上，读者会去相加对账；
    两条各有自己的合约边界（USD/CNH 不含 Mini / FlexC、INR/USD 不含 FlexC，
    见 fetch/sgx.py 的列口径表），相加必然少一块。
    返回 (可算月数, 占比下界%, 中位%, 上界%)；算不出返回 (None,) * 4。
    """
    s = []
    for r in _rows():
        tot = _num(r, 'vol_fx_futures_contracts')
        a, b = (_num(r, 'vol_usdcnh_futures_contracts'),
                _num(r, 'vol_inrusd_futures_contracts'))
        if tot and a is not None and b is not None:
            s.append((a + b) / tot * 100.0)
    if not s:
        return (None,) * 4
    s.sort()
    return (len(s), s[0], s[len(s) // 2], s[-1])


def _iron_share():
    """铁矿石占「商品合计」的中位比重；算不出返回 None。"""
    s = sorted(_num(r, 'vol_iron_ore_contracts') / _num(r, 'vol_commodities_contracts')
               * 100.0
               for r in _rows()
               if _num(r, 'vol_commodities_contracts') and _num(r, 'vol_iron_ore_contracts'))
    return s[len(s) // 2] if s else None


def _price_range():
    """加权平均成交价（当月成交额 ÷ 当月成交股数）的全期区间；算不出返回 (None, None)。"""
    p = [_num(r, 'sec_turnover_sgdmn') / _num(r, 'sec_turnover_mnshares')
         for r in _rows()
         if _num(r, 'sec_turnover_mnshares') and _num(r, 'sec_turnover_sgdmn')]
    return (min(p), max(p)) if p else (None, None)


_SD = _sdav_identity()
_DD = _ddav_days()
_SW = _swaps_gap()
_EQ = _eqix_share()
_FX = _fx_share()
_VE = _velocity_stats()
_RTO = _rto_only_months()
_IO = _iron_share()
_PR = _price_range()
# 加密永续那一节的首月（实测 2025-11）。同 _breaks() 的做法：能读 CSV 就读，不写死。
_CRYPTO0 = _first_present('vol_crypto_contracts')


def _breaks():
    out = []
    # 台指授权换手：MSCI Taiwan 合约到期不再续约，SGX 改挂 FTSE Taiwan。
    # 从 CSV 读 FTSE 那条的首月（实测 2020-07），不写死。
    m = _first_present('vol_ftse_taiwan_futures_contracts')
    if m:
        out.append({'month': m, 'zh': '台指授权由 MSCI 换为 FTSE，两条序列不可直连'})
    # GIFT Nifty：GIFT Connect 迁移，同时改了计数口径（月份常数的依据见其定义处）。
    out.append({'month': _NIFTY_BREAK,
                'zh': 'GIFT Connect 迁移，Nifty 计数由「买卖孰高」改为双边合计'})
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 统一按月份排。
    return sorted(out, key=lambda b: b['month'])


# ── 页尾原来有两张「水平值 + 12 个月滚动同比」，2026-09 全部删掉 ────────────
# 那两张画的是 `sec_turnover_mnshares` 与 `sec_turnover_sgdmn`，用途是「一整年在不在
# 长」，与「证券市场成交」组图里同名的两张（单月同比）分工。全站同比按页面所有者的
# 指令统一成单月之后，两边变成**同一列、同一窗口、同一口径** —— 组图那三列各占一个
# 单位桶（S$mn/day、S$mn/month、mn shares/month），底座本来就把它们各画成一张
# gs_bar + 次轴单月同比，页尾再画一遍是一字不差的重复。
# 底座对此有硬护栏（build/single.py 的 `ex_level_yoy`：撞上 SpecError），
# 所以 `_TTM_YOY`、`_ttm_names_zh()`、`_ttm_deriv_zh()` 三样一并删除，不留死代码。
# 「衍生品那一侧一张滚动图都没有」那句提醒也随之作废：现在全页只有一种口径，
# 证券与衍生品两侧读的是同一种同比。


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（SPEC 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图这个月该怎么读」（含当月读数、当月实测的毛刺量）；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**。
# 出现的数只有两类：把定义钉住的结构性量（恒等式的实测偏差、掉期占多大、
# 单列产品占合计多少、换手率反推倍数的浮动区间）与恒等式本身；**一个都不写死**，
# 全部在 import 期从 series/sgx.csv 现算（同本文件其余图注的做法）。
# 唯一的两个字面常数是官方文件里的：GIFT Nifty 两处口径的 FY2026 读数
# （20,699,069 / 24,357,137，出处 fetch/sgx.py 口径坑 2 与 docs/verify/sgx.md，
# 那两个数印在报告里、不随本仓的月份走）与铁矿石的 Dec-2015 对账值 988,532
# （SGX 新闻稿原文 "Iron Ore Derivatives volume was 988,532"，同一处出处）。
#
# ━━ 为什么是这 14 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头里，而且
# **不看定义就会读错**。按「读错会出什么事」分四类：
#   ① 缩写与它的分母   SDAV / DDAV / 张（contracts）—— 本页两条头条都是「日均」，
#      而证券侧的恒等式成立、衍生品侧**不成立**（交易日那一行是证券市场口径）。
#      不点破，读者会拿交易日去反推衍生品月量；张数不点破，读者会拿本页的
#      日経225 张数直接去比 JPX 的日経225 张数 —— 那正是 build/notional.py 与
#      series/contract_specs.csv 明文说不可比的那种比法（根因是合约乘数）。
#   ② 「合计」不是页上那几条的和   当月成交合计（含不上页面的掉期）、
#      股指期货合计（单列产品只占中位七成）、外汇期货合计（不含 FX 期权，
#      单列两条又各去掉 Mini / FlexC）—— 页面上同时画着合计与几条分项，
#      相加对不上是本页最容易被当成「数据错了」的一处。
#   ③ 同名不同数 / 派生量   GIFT Nifty 50（官方另一节同名行是 NSE-IX 全市场口径）、
#      铁矿石（本仓跨小节自己汇总的一条）、加权平均成交价（分解图里轧出来的，
#      不是公司披露的数）—— 读串的代价是整条线系统性偏高或偏低而图形完全正常。
#   ④ 口径边界   换手率（官方只算 primary listed securities，且只印整数 pp）、
#      上市证券只数（不含债券，且数的是证券不是公司）、上市家数 / 募资额
#      （家数不含 RTO、募资额含 RTO）、未平仓（OI，月末截面）、永续期货
#      （无到期日，且不计入商品合计）。
# **有意不收**：
#   · m/m、y/y、3Y %ile、pp/bp —— 全站通用读图约定，summary.note 已逐条讲过；
#   · 「口径断点」「慢腿」「存量 vs 流量」的**总则**、按千 / 按百万的显示缩放、
#     单月同比的代价 —— 页尾 notes 第 2、3、5、7 条与逐张图注讲的就是这几件事在
#     本页的落点，释义板再讲一遍就是两处各写一份（未平仓单列一条是因为 OI 这个
#     **词**本身要解释：它含掉期、是月末截面，总则不重复）；
#   · 成交额 / 市值 / IPO 这类本页没有特殊口径的常识词；
#   · 页面上根本不出现的列（sec_trading_days、掉期、MSCI 台湾）—— 它们只在
#     真正用得上的那一条释义里被顺带点名，不各占一条。
# ══════════════════════════════════════════════════════════════════════════════
_GLOSSARY = [
    ('SDAV',
     '官方缩写 Securities Daily Average：证券市场当月成交<b>金额</b>的日均值'
     '（S$mn/day），是 SGX 财报与新闻稿引用最多的那个数，本页头条第一格与'
     '「日均成交额 SDAV」画的都是它。证券这一侧恒等式成立：'
     '<code>当月成交额 ÷ 当月证券市场交易日数 = SDAV</code>'
     + (f'（{_SD[0]} 个月现算，最大相对差 {_SD[1]:.3f}%，量级就是 SDAV 取整到 '
        f'S$mn 的舍入）' if _SD[0] else '')
     + ' ⇒ 「当月成交额」与「日均成交额 SDAV」<b>不是两个指标</b>，'
       '只差一个当月开市天数。⚠️ 这条恒等式<b>只在证券侧成立</b>，衍生品侧见下一条。'),

    ('DDAV',
     '官方缩写 Derivatives Daily Average Volume：衍生品当月成交的日均<b>张数</b>'
     '（contracts/day），也是与 HKEX / CME 跨所可比的那一条。'
     '⚠️ <b>不能</b>用「当月成交合计 ÷ 交易日数」反推：官方那一行交易日数括号里写的是 '
     '(Stock Market) / (Securities)，是<b>证券市场</b>的交易日，'
     '衍生品的假期表与夜盘归属日都不一样'
     + (f' —— 用官方两个数反算出来的隐含天数在 {_DD[2]:.1f}–{_DD[3]:.1f} 天之间，'
        f'{_DD[0]} 个月里<b>没有一个月</b>等于当月证券交易日数'
        f'（硬拿证券交易日去除，相对差中位 {_DD[4]:.1f}%、最大 {_DD[5]:.1f}%）'
        if _DD[0] else '')
     + '。所以本页月总量与日均两条都直接取官方值，谁也不从谁推。'),

    # 「不做千张换算」的主语是**入库**（出处 fetch/sgx.py：「本模块不做任何换算」），
    # 不是「本页」—— 本页有 11 张图做了按千 / 按百万的**显示**缩放（页尾说明第 7 条），
    # 写成「本页」就与那一条打架。
    # 「单边计数」出处 fetch/sgx.py 的列口径表；**计数惯例一致 ≠ 张数可比**：
    # 张数跨所不可比的根因是合约乘数，见 build/notional.py 的模块 docstring 与
    # series/contract_specs.csv（JPX_N225_MINI 一行：JPX 官方产品页写明 mini 是
    # 大板的 1/10、micro 是 1/100；CME_EQUITY_INDEX 一行：ES $50/点 vs MES $5/点）。
    # 本仓连 SGX 一条合约的乘数都没有实测（同表 SGX_DERIV 一行「乘数零个实测」），
    # 更无从断言它与 JPX / HKEX 的同标的合约等大。
    ('张（contracts）',
     '衍生品各列的单位，官方新闻稿里写作 "lots"，与本页的「张」是同一个东西。'
     '<b>入库、汇总表与末尾核对表</b>一律用官方原值、不做千张 / 万张换算'
     '（图上另有按千 / 按百万的<b>显示</b>缩放，只作用于图、不作用于表，'
     '见页尾说明第 7 条）。'
     'SGX 的成交张数按<b>单边</b>计（一手买 ＋ 一手卖记 1 张），与 CME / HKEX 是'
     '同一种计数惯例 —— 同一笔成交在哪一家都不会被记两次。'
     '⚠️ 但<b>计数惯例一致不等于张数能直接比大小</b>：那还要看合约乘数'
     '（JPX 的日経225 mini 是大板的 1/10、micro 是 1/100，CME 的 ES 是 $50/点、'
     'MES 是 $5/点），本仓也没有 SGX 任何一条合约的乘数实测。'
     '⇒ 跨所比规模走 <code>build/notional.py</code> 的定基美元名义额，<b>不比张数</b>。'
     '<b>单边计数本身还有一个例外是 GIFT Nifty</b>：'
     f'{_NIFTY_BREAK} 之前官方按「买卖腿孰高」计量、之后才改成买卖双边合计，'
     '断点两侧不是同一把尺子（见下面那条与页尾口径说明）。'),

    ('换手率',
     '官方行名 Overall Turnover Velocity（年化换手率）。本页原样入库，'
     '只保留官方印出的<b>整数百分点</b>'
     # 全是整数与「有几个不是」两种说法都留着：官方哪天开始印小数，这句会自己改口。
     + ((f'（{_VE[0]} 个月全部是整数，读数区间 {_VE[2]:.0f}–{_VE[3]:.0f}%）'
         if _VE[1] == _VE[0] else
         f'（{_VE[0]} 个月里 {_VE[1]} 个是整数，读数区间 {_VE[2]:.0f}–{_VE[3]:.0f}%）')
        if _VE[0] else '')
     + ' ⇒ 这一行的变化一律是整 pp。⚠️ 它<b>算不出来</b>：官方脚注写明分子（成交额）'
       '与分母（市值）都只取 primary listed securities，而本页的「当月成交额」与'
       '「月末总市值」是全市场口径 —— 拿这两列相除去反推'
     + (f'，倍数在 {_VE[4]:.1f}–{_VE[6]:.1f} 之间浮动（中位 {_VE[5]:.1f}），'
        f'<b>不是一个常数</b>。' if _VE[0] else '，得不到官方那条线。')),

    ('上市证券只数',
     '月末在册的上市<b>证券只数</b>（存量），官方脚注<b>不含</b> GDR、对冲基金与'
     '<b>债券</b>。两处别接错：① 它数的是<b>证券</b>、不是公司，'
     '与「当月新上市家数 / 当月退市家数」（companies）不是同一套计数，'
     '两者不能相减去对账；② 「当月新债券挂牌数」再多也<b>不会</b>加进这一条 —— '
     '债券本来就不在它的口径里。'),

    ('当月成交合计',
     '衍生品当月成交总张数 ＝ <b>期货 ＋ 期权 ＋ 掉期</b>（官方三节各自的 Total）。'
     '本页只画前两条：掉期与期货同框会被压成一条贴地线'
     + (f'（占合计全期中位 {_SW[3]:.3f}%、最大 {_SW[4]:.2f}%）' if _SW[0] else '')
     + '，所以不上页面 ⇒ <b>「其中：期货」＋「其中：期权」比合计少的那一点就是掉期</b>，'
       '不是漏了数。'
     + (f'（{_SW[0]} 个月现算：{_SW[1]} 个月三项相加与合计逐位相等，'
        f'其余最大差 {_SW[2]:.0f} 张，是官方自己的印刷差。）' if _SW[0] else '')),

    ('未平仓（OI）',
     'open interest：<b>月末</b>仍未了结的合约张数，产品范围与「当月成交合计」相同'
     '（同样含掉期），但<b>不是同一类量</b> —— 成交是当月累计发生的流量，'
     '未平仓是某一天的<b>截面（存量）</b>。⇒ 两者不能相加、也不宜直接比大小；'
     '把 12 个月末快照加起来不指代任何真实的量，所以它的同比只能走点对点'
     '（月末 vs 去年同月月末）。'),

    ('股指期货合计',
     '官方 Equity Index Futures 小节的 <code>Total</code>，<b>不是</b>本页单列那几条'
     '产品的和：'
     + (f'A50 ＋ 日経225 ＋ MSCI 新加坡三条全期中位只占它 {_EQ[0]:.0f}%，'
        f'把另外两组里的 GIFT Nifty 与 FTSE 台湾也算进来才 {_EQ[1]:.0f}%，'
        if _EQ[0] else '')
     + '剩下的是官方另行分列的其它指数合约。⇒ 单列的那几条是<b>挑出来看的</b>'
       '（A50 对着 HKEX、日経225 对着 JPX），不是合计的穷举，'
       '别拿它们相加去凑合计、也别把它们当成合计的分部拆解。'
       '⚠️ 另一处：「日経225 期货」只含标准合约，<b>不含</b> Mini / USD / Micro / TR / '
       'ESG-REIT 那几个变体（官方各自单列）。'),

    ('GIFT Nifty 50',
     '本页这一条是 <b>SGX-ICI 成交、SGX 自己清算</b>的口径。'
     '⚠️ 官方同一份报告里<b>另有一节</b>（GIFT Nifty Overall Market Volume）印着'
     '同名的一行，那是 NSE-IX <b>整个市场</b>的量、不全归 SGX：'
     '官方 FY2026 两处分别是 20,699,069 与 24,357,137 张，差 18% —— '
     '拿错那一节会把本页这条整体抬高。'
     f'另：{_NIFTY_BREAK} 起计数口径由「买卖腿孰高」改为买卖双边合计，'
     '断点两侧不可直连（页尾口径说明里有断点两侧水平差为什么不做归因）。'),

    # 与「股指期货合计」同一形状的坑，出处 fetch/sgx.py 的列口径表三行：
    # vol_fx_futures_contracts「不含 FX 期权」、vol_usdcnh「不含 Mini / FlexC」、
    # vol_inrusd「不含 FlexC」。Ex15 与汇总表把合计与两条分项画在同一根轴上，
    # 相加对不上是本页第二处最容易被当成「数据错了」的地方（第一处是掉期）。
    ('外汇期货合计',
     '官方 Foreign Exchange <u>Futures</u> Volume 小节的 <code>Total</code>，'
     '<b>不含 FX 期权</b> ⇒ 它<b>不是</b> SGX 全部外汇衍生品的量，'
     '跨所对外汇业务规模时先看对面那个数含不含期权。'
     '与「股指期货合计」同一个坑：单列的两条各有自己的合约边界 —— '
     '「USD/CNH 期货」只含标准合约、<b>不含</b> Mini 与 FlexC，'
     '「INR/USD 期货」<b>不含</b> FlexC（官方各自单列）'
     # 上界给一位小数：整数会印成「100%」，读成「有的月份两条就是全部」，
     # 而实测最大 99.5%，never 到 100 —— 那一位小数正是这条释义的论据。
     + (f'，两条相加占合计全期中位 {_FX[2]:.1f}%（{_FX[0]} 个月现算，'
        f'区间 {_FX[1]:.1f}–{_FX[3]:.1f}%）' if _FX[0] else '')
     + '，剩下的是官方另行分列的其它货币对与合约变体。'
       '⇒ 画在同一根轴上的三条<b>相加对不上</b>，不是漏了数。'),

    ('铁矿石',
     '<b>本仓自己汇总的一条</b>，不是官方某一行的 Total：把各成交量小节里行名含 '
     '"Iron Ore" 的行（62% / 65% / 58% / IODEX / Lump Premium，'
     '<b>期货 ＋ 期权 ＋ 掉期</b>，含 OTC 清算腿）全部相加。'
     '口径与官方对得上 —— <code>fetch/sgx.py</code> 拿 SGX 新闻稿逐位核过'
     '（Dec-2015 ＝ 988,532）。它落在「商品合计」里面'
     + (f'，是那一档里最大的一块（全期中位占 {_IO:.0f}%）。' if _IO else '。')),

    ('永续期货',
     'perpetual futures：<b>没有到期日</b>、不按月 / 按季到期换月的期货合约。'
     '本页这一列 ＝ Bitcoin ＋ Ethereum 两只永续期货的合计，'
     + (f'官方从 {_CRYPTO0} 那期起才印这一节' if _CRYPTO0 else '官方近年才新增这一节')
     + '（左边那一大段空白是产品还没上线，<b>不是 0</b>）。'
       '⚠️ 它<b>不计入</b>「商品合计」—— 官方的 Commodities 定义里没有加密，'
       '页尾口径说明里有逐项对账。'),

    ('上市家数 / 募资额',
     '发行那一组的几行<b>分母互不相同</b>：「当月新上市家数」＝ Mainboard ＋ Catalist 的 '
     'IPO 家数，<b>不含</b> RTO（借壳上市，官方单列一行）；而「IPO / RTO 募资额」'
     '<b>含</b> RTO，且官方脚注写明不含超额配售权（若行使）。'
     '⇒ 两行相除得不到「平均每家募到多少」'
     + (f' —— 实测有 {_RTO} 个月家数是 0、募资额却大于 0（那几个月只有 RTO）'
        if _RTO else '')
     + '。「当月退市家数」同样只数 Mainboard ＋ Catalist。'),

    ('加权平均成交价',
     '<b>不是公司披露的数</b>，是量价分解那张图里本页自己轧出来的派生量：'
     '<code>当月成交额 ÷ 当月成交股数</code>（S$/股'
     + (f'，全期实测 {_PR[0]:.2f}–{_PR[1]:.2f}' if _PR[0] else '')
     + '）。它同时含两件事：市场本身的涨跌，以及<b>成交结构变化</b>'
       '（单价高的标的成交占比上升，即使每只票都没涨，这个数也会被抬高）。'
       '⇒ 它<b>不是</b>股价指数的收益率，本仓也没有 STI 点位序列可以把两者分开。'),
]


SPEC = {
    'ticker': 'sgx',
    'name': 'Singapore Exchange',
    'title': '新加坡交易所（SGX）月度经营指标',
    'csv': 'sgx.csv',
    'ccy': 'SGD',
    'source': ('Source: SGX Monthly Statistics Report (official PDF, via SGX CMS API); '
               'format after Goldman Sachs GIR'),

    # 头条：证券与衍生品各一条。两者同出一份 PDF、同一天发布，
    # 2015-01 起逐月无洞（实测 138/138）。
    # SDAV 是 SGX 自家财报与新闻稿引用最多的单一数字；DDAV 是跨所可比的那条。
    'headline': [
        {'col': 'sdav_sgdmn', 'zh': '证券市场 SDAV',
         'unit': 'S$mn/day', 'fmt': 'f0c'},
        {'col': 'ddav_contracts', 'zh': '衍生品 DDAV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        # 三列三个单位 ⇒ 三个单桶 ⇒ 三张 gs_bar，次轴都是**单月同比**（全站唯一口径）。
        # 代价照实说：tools/check_yoy_caliber.py 实测当月成交额 / 成交股数各有 2 / 6
        # 个月与 12 个月滚动口径符号相反（如 2024-07 成交额单月 +23.3% vs 滚动 −3.6%）。
        # 契约要求单月口径写进标题（CONTRACT.md §6）⇒ 口径写进组名。
        # 当月总量两张是**对账视图**（官方月报 At-A-Glance 的原样数字）。
        # ⚠️ 2026-09 之前页尾另有两张同列的 12 个月滚动同比图回答「一整年在不在长」；
        # 改单月口径后与这里的后两张完全重复，已删（见本文件上方那段说明）。
        {'zh': '证券市场成交（次轴：单月同比）', 'cols': [
            {'col': 'sdav_sgdmn', 'zh': '日均成交额 SDAV',
             'unit': 'S$mn/day', 'fmt': 'f0c'},
            {'col': 'sec_turnover_sgdmn', 'zh': '当月成交额',
             'unit': 'S$mn/month', 'fmt': 'f0c'},
            {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
             'unit': 'mn shares/month', 'fmt': 'f0c'},
        ]},

        {'zh': '市值与上市证券数', 'cols': [
            {'col': 'mktcap_sgdmn', 'zh': '月末总市值',
             'unit': 'S$mn', 'fmt': 'f0c', 'stock': True},
            {'col': 'listed_securities', 'zh': '月末上市证券只数',
             'unit': 'listings', 'fmt': 'f0', 'stock': True},
        ]},

        # 与主体同起点（2015-01），但单位是 % —— 与任何一组都不同桶，
        # 合进别的组也只会自己一张图，所以仍旧单列一组。
        # （2026-08 之前这里写「2018-03 起」，是解析边界不是数据边界，见文件抬头。）
        {'zh': '换手率', 'cols': [
            {'col': 'turnover_velocity_pct', 'zh': '整体换手率',
             'unit': '%', 'fmt': 'pct0'},
        ]},

        # DDAV 从「衍生品成交与未平仓」拆出来单独成组，理由与新债券挂牌数那一组同型：
        # 它是原组里唯一的 contracts/day 列，天然单桶 ⇒ gs_bar + 次轴**单月同比**，
        # 而 CONTRACT §6.6 的自动判据要求单月同比写进标题（R4，不写就报 🟡）、
        # ex_single 的标题 = 组名 + 列名
        # ⇒ 只能写进组名。原组的组名不能加那句话：同组还有 3 列画折线的 Exhibit
        # （没有次轴）与一张存量柱图（点对点同比），加上去对那两张是假话。
        # 拆组不改图号：contracts/day 桶本来就排在 contracts/month 与存量桶之前，
        # 拆之前拆之后的出图顺序逐张一致（改完复跑 single.py 逐图核过）。
        {'zh': '衍生品日均成交（次轴：单月同比）', 'cols': [
            {'col': 'ddav_contracts', 'zh': '日均成交 DDAV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '衍生品成交与未平仓', 'cols': [
            {'col': 'deriv_vol_contracts', 'zh': '当月成交合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_futures_vol_contracts', 'zh': '其中：期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_options_vol_contracts', 'zh': '其中：期权',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'deriv_oi_contracts', 'zh': '月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # 头对头的两个产品必须在这里被看见（见文件抬头）。
        {'zh': '股指期货：与 HKEX / JPX 的头对头', 'cols': [
            {'col': 'vol_equity_index_futures_contracts', 'zh': '股指期货合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_a50_futures_contracts', 'zh': 'FTSE 中国 A50 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_nikkei225_futures_contracts', 'zh': '日経225 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_msci_singapore_futures_contracts', 'zh': 'MSCI 新加坡期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # GIFT Nifty 有 2023-07 的计数口径断点，单列一组便于配断点线。
        # 单桶 ⇒ gs_bar + 次轴**单月同比**，口径写进组名（CONTRACT.md §6）。
        # 这张**特意不换滚动口径**：断点让滚动的污染期比单月长将近一倍
        # （单月只有断点后 12 次比较跨口径，滚动要 23 个月后两窗才都落进新口径），
        # 算术写在页尾口径说明，日期由 _NIFTY_BREAK 推导。
        {'zh': 'GIFT Nifty 50 期货（2023-07 计数口径断点；次轴：单月同比）', 'cols': [
            {'col': 'vol_nifty50_futures_contracts', 'zh': 'GIFT Nifty 50 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2020-07 起（起点与主体差 66 个月），单独一组。单桶 ⇒ 次轴**单月同比**，
        # 口径写进组名；与滚动口径的分歧实测和「方向以滚动为准」的现算读数
        # 都在页尾口径说明（_GT，从 CSV 现算）。
        {'zh': 'FTSE 台湾指数期货（2020-07 起；次轴：单月同比）', 'cols': [
            {'col': 'vol_ftse_taiwan_futures_contracts', 'zh': 'FTSE 台湾期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '外汇期货', 'cols': [
            {'col': 'vol_fx_futures_contracts', 'zh': '外汇期货合计',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_usdcnh_futures_contracts', 'zh': 'USD/CNH 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_inrusd_futures_contracts', 'zh': 'INR/USD 期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '商品与利率', 'cols': [
            {'col': 'vol_commodities_contracts', 'zh': '商品合计（不含加密）',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_iron_ore_contracts', 'zh': '其中：铁矿石',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'vol_rates_futures_contracts', 'zh': '利率期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 2025-11 才上线，单独一组。
        {'zh': '加密货币永续期货（2025-11 起）', 'cols': [
            {'col': 'vol_crypto_contracts', 'zh': 'BTC / ETH 永续期货',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        {'zh': '发行与上市', 'cols': [
            {'col': 'ipos_count', 'zh': '当月新上市家数',
             'unit': 'companies', 'fmt': 'f0'},
            {'col': 'delistings_count', 'zh': '当月退市家数',
             'unit': 'companies', 'fmt': 'f0'},
            {'col': 'ipo_funds_sgdmn', 'zh': 'IPO / RTO 募资额',
             'unit': 'S$mn', 'fmt': 'f0c'},
            {'col': 'bond_funds_sgdmn', 'zh': '债券募资额',
             'unit': 'S$mn', 'fmt': 'f0c'},
        ]},

        # 新债券挂牌数从「发行与上市」拆出来单独成组：它是原组里唯一的
        # listings/month 列，天然单桶 ⇒ gs_bar + 次轴**单月同比**，契约要求单月
        # 口径写进标题（CONTRACT.md §6），而 ex_single 的标题 = 组名 + 列名
        # ⇒ 口径写进组名。拆组不改图号：原组的 companies / S$mn 两桶在前、
        # listings 桶在后，与拆之前的出图顺序逐张一致。
        {'zh': '当月新债券挂牌数（次轴：单月同比）', 'cols': [
            {'col': 'new_bond_listings', 'zh': '当月新债券挂牌数',
             'unit': 'listings', 'fmt': 'f0'},
        ]},
    ],

    # 本页所有列出自同一份月报 PDF，同一天发布 —— 没有慢腿。
    'slow_cols': [],

    'breaks': _breaks(),

    # ── 量价分解：成交额 ≡ 成交股数 × 加权平均成交价 ──────────────────────
    # SGX 有真正「金额 × 股数」同口径的一对，所以这张走 kind='share_price'。
    # ⚠️ **别在这里写「build/specs/ 里有几家、哪几家也有 decomp」** —— 那句话已经错过两轮：
    # 先是「八家里唯一的一家」（自己带着反例「TMX / MIAX 也有」，还漏了 jpx），
    # 后是「10 家里 4 家 share_price」（当天是对的，但目录里加一个 spec 就少一个）。
    # 本文件管不到别家，写在这里的任何家数都只能靠人肉维护。要看当期实况就现跑：
    #   for f in build/specs/*.py; do python3 -c "import importlib.util as u,sys; \
    #     s=u.spec_from_file_location('m','$f'); m=u.module_from_spec(s); \
    #     s.loader.exec_module(m); \
    #     print('$f', [d.get('kind') for d in (m.SPEC.get('decomp') or [])])"; done
    # 口径核查见文件抬头「量价分解的口径核查」一节 —— 那四条证据是这张图成立的全部前提。
    'decomp': [{
        'zh': '证券市场成交额',
        # 派生量是**成交量加权平均成交价**，不是每笔均额、也不是费率。
        # 底座据 kind 生成「它不是什么」那段话，spec 不许自己改措辞。
        'kind': 'share_price',
        # 两列本身就是当月合计（月报 p2 At-A-Glance 的相邻两行），不是日均。
        # ⇒ 不给 weight_col：声明 monthly_total 又给 weight_col 是硬失败，
        #   而且真乘上去会把年度合计放大二十几倍，图形却照常画得出来。
        'granularity': 'monthly_total',
        'value': {'col': 'sec_turnover_sgdmn', 'zh': '当月成交额',
                  'unit': 'S$mn/month', 'fmt': 'f0c'},
        'qty': {'col': 'sec_turnover_mnshares', 'zh': '当月成交股数',
                'unit': 'mn shares/month', 'fmt': 'f0c'},
        # 价 = 金额 ÷ 数量，由底座算。**不许另找一列冒充价** —— series/sgx.csv 里
        # 没有任何一列是成交价，turnover_velocity_pct 是换手率、不是价。
        # S$百万 ÷ 百万股 = S$/股，两边的 1e6 自己抵掉 ⇒ price_scale 用缺省 1.0。
        'price_zh': '加权平均成交价',
        'price_unit': 'S$/share',
        'price_fmt': 'f3',          # 实测区间 0.44–1.49，f2 在低位只剩两位有效数字
        # ━━ 图已按用户指令（2026-08-07）改**日历年**，FY 对账基准见本注释 ━━
        # 改日历年的理由：四家分解图统一 Jan–Dec、4 根完整年柱 + 1 根当年 YTD，
        # 跨页可比；「用日历年会丢掉 2026 上半年」的旧顾虑由 YTD 桶补上
        # （底座自动追加，两侧月份对齐去年同期）。
        # 原财年选择的**对账证据保留如下**（它仍是「月度序列可安全聚合成年度块」的
        # 证明，与横轴用哪种年无关，详见文件抬头口径核查第 4 条）：
        #   · SGX 财年 = Jul–Jun，按**结束**年命名（FY2026 = 2025-07…2026-06）；
        #     财年制下这里曾写 'year_start_month': 7, 'year_label': 'end', 'years': 10。
        #   · 用月度序列自己滚 FY2026（Jul-25–Jun-26）得 455,679 S$mn，
        #     官方报告 p3 的 FYTD = 455,677、新闻稿写 "S$455.7 billion" ——
        #     差 2（12 个整数月度值的舍入），相对差 0.0004%；
        #     衍生品 FYTD 更是逐位相同（363,489,920）。
        #   · docs/SINGLE_SPEC.md 的回归基准仍按财年配置写（FY2021/FY2025/FY2026
        #     三组读数）——那是**底座**的回归测试口径，拿本 spec 临时改回上面三个
        #     字段即可复现，不影响本页按日历年出图。
        # 日历年下 year_label 只能留空或 'start'（底座对日历年 + 'end' 硬失败）。
        'year_start_month': 1,
        # 4 根完整年柱（数据允许时取最近 4 个）+ 1 根 YTD，同 JPX / TMX / MIAX。
        'years': 4,
    }],

    # 名词释义：排在所有 exhibit 之前。选词的判断与「有意不收哪些词」写在 _GLOSSARY
    # 上面那一段注释里（为什么是这 13 个词、按「读错会出什么事」分的四类）。
    'glossary': _GLOSSARY,

    # ── 量本身：水平值 + 次轴同比（2026-09 起本页已无 level_yoy，见上面那段）──
    'notes': [
        'SGX 的头部衍生品产品全部是离岸挂牌的他国标的。2026-06 实测：'
        'FTSE 中国 A50 期货 11,724,378 张（占当月衍生品总成交 34.2%）、'
        '外汇期货合计 10,268,040 张（29.9%）、铁矿石 5,354,979 张（15.6%）、'
        '日経225 期货 748,048 张（2.2%）。A50 与日経225 分别对着 HKEX 与 JPX 的同标的合约，'
        '本页把两者单列而不是并进「股指期货合计」。',

        'GIFT Nifty 在 2023-07 有计数口径断点。官方报告脚注写明 "For periods prior to '
        'June 2023, volumes are computed based on higher of buy and sell lots"，'
        '之后改为买卖双边合计。**本页不对断点两侧的水平差做任何归因**：'
        'series/sgx.csv 里 2023-06 = 1,696,663 张、2023-07 = 1,330,907 张，'
        '是降不是升，说明同期还有 GIFT Connect 迁移的量在动，'
        '单看这条序列分不出「口径变了」和「份额丢了」。',

        '衍生品的 DDAV 不能用「当月总量 ÷ 交易日数」反推。sec_trading_days 那一行'
        '官方括号里写的是 (Stock Market) / (Securities)，是**证券市场**的交易日；'
        '实测 2026-06 用 34,315,225 ÷ 1,619,444 反推得 21.19 天，而官方写的交易日是 21。'
        '所以本页月总量与日均两条都直接取官方值，谁也不从谁推。',

        '「商品合计」按官方定义**不含加密**。实测口径校验：SICOM 3,895,114 + Energy 493,152 '
        '+ Metal&DryBulk 73,586,973 + Dairy 期货 688,923 + Dairy 期权 104,742 + '
        'Energy Metals 2,640 = 78,771,544 张，恰好等于官方新闻稿的 FY2026 "78.8 million lots"；'
        '把 Crypto 加进去就对不上。所以加密单列一组。',

        '台湾指数敞口在 2020-07 换了授权方：MSCI Taiwan 停发（series/sgx.csv 里该列 '
        '2021-11 之后无值、2021-02 起全是 0、2021-01 还有一个内部空洞），改挂 FTSE Taiwan。'
        '本页只画 FTSE 那条，MSCI 那条不上页面 —— 一条带空洞的归零序列进平滑类图型会画出假线。',

        '证券成交额是暂定数：官方脚注写明月末临近的撤单可能来不及计入、'
        '调整顺延到下个月的报告。fetch/sgx.py 按「已有值永不覆盖、只填空」处理，'
        '差异另记 cache。实测 2026-04/05/06 三期的重叠月 8 个数据点逐位相同，'
        '近月重述不是常态。',

        '本页全部金额为新元。跨币种比较由 build/notional.py 统一换算：'
        '流量（SDAV、成交额、募资额）配月均汇率，存量（月末市值、月末未平仓）配月末汇率。',

        '未上页面的月频列：sec_trading_days（分母，且是证券市场口径）、'
        'deriv_swaps_vol_contracts（2026-06 = 7,662 张，占总量 0.02%）、'
        'vol_msci_taiwan_futures_contracts（已停发的死列，见上）。',

        # 逐图的一句话交代（2026-09 之前这是 §6.1 第 2 条要的「用单月必须说明为什么」；
        # 全站统一成单月之后那条要求整个消失，新 §6.1 第 3 条要的是**代价**，
        # 所以下面这条注的重心从「为什么用单月」挪到了「这几张单月线各自有多毛刺」）。
        # 逐图的口径分类由底座的「同比口径」自动条目从 yoy_log 现算点名，本条只补
        # 底座给不出的那半。分歧数字全部现算
        # （_GT / _GB / _madd），没有一个写死的数据数字。
        #
        # ⚠️ **本条一律按图的标题点名，不写 Exhibit 号。**
        # 图号是分组顺序的函数：往中间插一组，后面所有图号整体位移，而这条注不会跟着动。
        # 上一版这里写死了 6、7、8、13、14、20 —— 底座那条自动条目现算出来是
        # 4、5、6、7、8、10、13、14、20，两处当场对不上（漏的那张 DDAV 当时既没有理由、
        # 组名里也没有单月声明）。这一轮把 DDAV 拆成自己一组、并把漏掉的几张补进下面，
        # 同时把图号换成标题：标题印在图上，读者按名字找得到，而且不会因为加一组图就失效。
        # 加图 / 拆组之后仍请重跑 single.py，拿页面上那条自动条目逐张对一遍**有没有漏**
        # （对号靠的是图名，不是图号）。
        '<b>单月口径为什么保留（逐图的口径分类以上文「同比口径」那条为准，'
        '它由底座从口径账本现算；本条补的是「为什么」）。</b>'
        '逐张交代 —— <b>按图的标题点名，不写 Exhibit 号</b>'
        '（图号会随分组增删整体位移，标题不会）：'
        '<b>头条同比图</b>（「证券市场 SDAV：单月同比」与「衍生品 DDAV：单月同比」）'
        '是页顶数据条与汇总表 y/y 列的图形版，标题里已写明「单月同比」，'
        '用途就是逐月核对当月读数。'
        '<b>「证券市场成交」那一组的三张</b>（日均成交额 SDAV / 当月成交额 / 当月成交股数）'
        '画的是官方月报 At-A-Glance 的<b>原样数字</b>（SDAV 是日均，后两条是当月总量），'
        '本页拿它与官方披露逐格对账，单月同比与柱逐月对得上。'
        '⚠️ <b>页尾原来还有两张同列的 12 个月滚动同比图（当月成交额、当月成交股数），'
        '2026-09 已删</b> —— 改单月口径之后它们与这一组的后两张完全重复。'
        '<b>「衍生品日均成交」那张（DDAV）</b>与 SDAV 那张同型：'
        '官方月报 At-A-Glance 印的日均数，与页顶数据条第二格同一条序列、同一个读数。'
        '跨年趋势请回到「衍生品成交与未平仓」那张当月合计的折线图上看。'
        f'<b>「GIFT Nifty 50 期货」那张</b>：{_NIFTY_BREAK} 有计数口径断点'
        f'（"买卖孰高" 改成买卖双边合计）。单月口径在这里反而是较干净的一侧 —— '
        f'跨断点的比较只有 {_NIFTY_BREAK} 至 {_madd(_NIFTY_BREAK, 11)} 这 12 个月，'
        f'而 12 个月滚动合计要到 {_madd(_NIFTY_BREAK, 23)} 起两个窗口才都落进新口径，'
        f'污染期长将近一倍。'
        + (f'<b>「FTSE 台湾指数期货」那张</b>：本页把它与 GIFT、A50 那两条线同窗对照，'
           f'读的是逐月的竞争动态。⚠️ 单月口径毛刺大 —— 全期实测有 {_GT[1]} 个月'
           f'（{_GT[0]} 个可比月）与 12 个月滚动口径符号相反，分歧最大的 {_GT[2]} '
           f'单月 {_GT[3]:+.1f}% vs 滚动 {_GT[4]:+.1f}%；'
           f'对照读数：{_GT[5]} 的滚动同比 {_GT[6]:+.1f}%（现算，页上不画）。'
           if _GT[0] else
           '<b>「FTSE 台湾指数期货」那张</b>：与同页 GIFT、A50 同窗对照，'
           '读的是逐月的竞争动态。')
        + (f'<b>「当月新债券挂牌数」那张</b>：逐月的发行事件计数，单月同比天生毛刺最大 —— '
           f'全期实测与滚动口径符号相反 {_GB[1]} 个月（{_GB[0]} 个可比月）；'
           f'对照读数：{_GB[5]} 的滚动同比 {_GB[6]:+.1f}%（现算，页上不画）。'
           if _GB[0] else
           '<b>「当月新债券挂牌数」那张</b>：逐月的发行事件计数，单月同比毛刺最大。')
        + '<b>这两处的滚动读数只作对照、页上一张滚动图都没有</b>'
          '（全站单月口径，页面所有者指定）—— 引在这里是为了让读者知道'
          '自己在读的这条线有多毛刺，不是让人拿它去改结论。'
          '「符号相反」的统计与 tools/check_yoy_caliber.py 同一条死区：'
          '两侧 |同比| ≥ 0.5pp 才计。',
    ],
}
