# -*- coding: utf-8 -*-
"""London Stock Exchange Group（lseg）单公司页配置。

本文件只声明「画哪些列、叫什么、什么单位、什么格式」，**不含任何算术、不含任何取数**。
数值在通用底座 build/single.py 里算完再进 payload，页面只画不算。
import 期确实会读一次 series/lseg.csv，但那**只用来现算图注里要报的数**
（各腿覆盖到哪个月、哪几列是近零基数），一个数都不写死；读不到就退回不含数字的
定性版本，绝不在 import 期抛异常。

━━ 这一家为什么是「四条腿缝出来的一页」━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
series/lseg.csv 的 86 个数据列来自**四个互不相干的官方源**（fetch/lseg.py 的 PARTS）：

  orderbook  LSE 主板 + Turquoise 电子订单簿（Monthly Market Report PDF 第 1 页 MTD 表）
  primary    LSE Main Market / AIM 一级市场（factsheet xlsx）
  tradeweb   Tradeweb 固收/信用/ETF/货币市场（Historical ADV xlsx）
  lch        LCH SwapClear / ForexClear / RepoClear（lseg.com volumes 页）

四条腿的**发布节奏差一个数量级**（各 fetch/lseg_*.py docstring 的实测统计）：

  快腿 tradeweb   数据月月末后第 2–8 天（2021 起 n=65，中位第 5 天）
  慢腿 lch        第 3–4 天发布，但 RepoClear 的官方月表本身滞后约两个月
  慢腿 primary    第 1–9 天（Main Market / AIM 两份 xlsx）
  慢腿 orderbook  近两年中位第 21 天 —— 本页最慢的一条腿

⇒ 每个月都有一段时间：Tradeweb 的 27 列已经有最新月，而 LSE 订单簿的 17 列、
  一级市场的 24 列、LCH 的 18 列**天生是空的**。这不是解析失败，也不是数据缺失。
  它们全部进 `slow_cols`，不参与门槛判定；底座会在每张涉及它们的图注末尾自动追加
  一句「XX 是慢腿：发布比头条晚，最新月留空是正常的」，并在页尾统一点名。

━━ 头条为什么放 Tradeweb（这一条决定 data_through、LAG 与红点）━━━━━━━━━━━━━
SINGLE_SPEC §5 的三条判据「历史长 / 发布快 / 无空洞」。三条里**只有「发布快」是决定性的**，
另外两条 2026-08-19 复量之后已经不再单指 Tradeweb（下面这三行是当天现量的，
页面上那句话由 `_NOTE_HEADLINE` 现算，不写死 —— 数字变了图注会自己跟上）：

  历史长   orderbook 127 月（2016-01 起）= primary 127（AIM 那 11 列也补到了 2016-01，
           Main Market 那 13 列仍是 2018-05 起）> tradeweb 115 > lch 24
  无空洞   orderbook 17 列与 tradeweb 27 列**都是**零空格；primary 在自己的跨度里
           还空着 388 格（两段列起点差 28 个月 = 28×13 + 2019-09 / 2022-12 两个官方
           自己的洞各砸一个市场的 11 / 13 列），
           lch 空 168 格（三个法人各有各的滚动窗口）
  发布快   见上表，tradeweb 是**唯一**进得了「次月一周内」的腿 —— 头条留在它这里
           靠的是这一条，不是前两条

⚠ 前两条既然已经不再独指 Tradeweb，就别再拿它们当头条的理由讲。真正的理由只有
  「发布快」加下面那条硬代价 —— 这也是为什么 orderbook 追平历史长度之后头条没动。

另外两条是**硬性排除**，不是偏好：
  · lch 连门槛都过不了 —— SINGLE_SPEC §3 要求共同连续历史 ≥ 24 个月，
    SwapClear / RepoClear 各只有 12 期（官方滚动窗口，不是抓漏，见下面的口径坑 D）。
  · orderbook 若做头条，今天的 data_through 立刻退回 2026-06，且按
    docs/CRON_WIRING §2.1「LAG 跟着决定 data_through 的那条腿走」，
    build/roster.py 的 LAG['lseg'] 要从 (8,8) 抬到 (26,26)，整页每月晚 18 天上线。

配套的 LAG['lseg'] = (8, 8) 已经在 build/roster.py 里，注释也写明了它绑定本文件的
headline。**改 headline 就必须同步改那一行**，否则红点会在慢腿到达之前每月假红。

━━ 口径坑（写这一页时踩到的，按危险程度排）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A. **三种币种同表并存，跨腿绝对不许加总或同轴。**
   `_gbp_m`（orderbook）与 `_gbp_mn`（primary）**是同一个单位（英镑百万）**，
   只是两条腿的命名习惯不同 —— 最容易犯的错是以为差 1000 倍去做二次缩放。
   本页不做任何汇率换算：用 series/fx.csv 折算会把 [A] 级原始披露变成派生的 [C]。
   底座按 `unit` 字符串自动分桶，所以每个单位串必须照实写，不许为了「少一张图」
   把 GBP mn 和 USD bn 写成同一个 unit。

B. **不许把成交额与 ADV 绑成量价恒等式。**
   `decomp` / `ttm_yoy` 一旦同时给 `weight_col` 与 `*_total_col`，底座会逐月对账，
   相对偏差 > 1e-6 就整页硬失败（退出码 1）。实测残差：
   Tradeweb `ADV × blended 天数 vs 月成交额` 2.5e-4、
   orderbook `ADV × 交易日 vs 月合计` 9.1e-4 —— 两条腿都远超阈值。
   原因是官方自己就把 £m 四舍五入到整数、把 blended 天数印到 2 位小数。
   所以本文件的 `ttm_yoy` 两条**都只用 monthly_total 口径的列本身**，
   一个 weight_col / total_col 都不给。

C. **build/yoy.py 的 classify() 对本表 15 列判错 kind，其中 3 列会静默印错数量级。**
   本页不受影响 —— build/single.py 有自己的 `yoy_line`，不调 classify()，
   比率与否只看 `fmt` 是不是 pct*/pp*，本文件已按实际含义给对了 fmt。
   但**横截面页（build/exchanges_eu.py 之流）若把 lseg 的列接进去，必须显式传 kind**：
     · `tradeweb_adv_rates_usd_bn` / `_rates_cash_` / `_rates_derivatives_` 会被
       `_RATIO_PAT` 里字面的 `rates` 判成 RATIO（这里的 Rates 是**资产类别名**不是费率），
       `mom_yoy(s, RATIO)` 走 `v − base`，会把 +47% 印成「+562pp」而且不报错；
     · primary 的 10 列 `mm_/aim_ × new_issues|cancellations|further_issues`
       与 `repoclear_*_cleared_trade_sides_count` 2 列会兜底成 STOCK
       （官方术语是 trade **sides**，`_FLOW_PAT` 认的是 `trades`），
       方向在安全侧（`ttm()` 会抛 CaliberError 而不是给错数），但会让
       CONTRACT §6.1 第 1 条「流量默认滚动同比」在这 12 列上失效。
   **不许改 build/yoy.py** —— CONTRACT §6 明写 classify() 只是建议，
   有疑问时由调用方显式传 kind。

D. **LCH 的短历史是官方滚动窗口，不是起点设窄。**
   ForexClear 的 CSV 末行原文 `Row Count: 24`；SwapClear 两个 datatable JSON 各 12 行；
   RepoClear 页面里 3 张月度 grid 各 12 行（而同页年度 grid 有 28 行、回溯到 1999，
   证明官方有更深历史但**只以年度形式公开**）。后果比「只有 24 个月」更严重：
   12 期连 13 期的点对点同比都算不出，24 期的 TTM 同比只有一个点、不成线。
   所以 LCH 的 18 列本轮一律只画水平值，且绝不进 headline。跑满一年后自然长到 24 期。

E. **RepoClear 的 LTD + SA 月度合计是派生值，不许画。**
   官方年度表自己印了 `Total`（2026 年 22.22 + 126.67 = 148.89 €tn），
   但三张**月度** grid 只有 Month/Year/LTD/SA 四列、**没有 Total 列**。
   月度口径自己加起来只能标 [C]，本仓不收。而且 SA 的清算边数是 LTD 的 11 倍
   （2026-05：1,205,030 vs 106,192），同轴画必然把 LTD 压成一条平线 ——
   所以两个法人**分组分图**，两条腿在本文件里从头到尾没有共用过一个 (group, unit) 桶。

━━ 口径断点 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`series/lseg_breaks.csv` **不存在**，`breaks` 留空。已知的三处口径变化都不该画成
全页红线（红线会误伤其余八十多列），逐条写进 `notes`：
  · Turquoise 暗池行名 MidPoint → Plato™ → Dark 是**同一条腿改名**，不是口径变化；
  · Tradeweb 2024-12 起美国国债的分母口径重述，但官方**已回溯改写历史**，
    历史段自洽，画一条竖线反而暗示「线左右不可比」，与事实相反；
  · orderbook 起点 2021-01 是取数腿的主动取舍（2020-12 及以前的月报多印
    Italian / Derivatives / MTS / EuroTLX 行，且 `LSE Lit Orderbook trading in UK`
    这个份额标签 2021-01 才出现），属于「更早的数据没取」，不是「更早的数据不可比」。

━━ 存量 / 流量 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`stock: True` 标在 16 列上：一级市场的月末家数与月末市值（10 列）、
LCH 的月末未平仓 / 月末存量（6 列）。它们一律单独成图、走点对点同比。
另有 5 列**既不是流量也不是存量**（交易日数 3 列、成交份额 2 列）与 1 列换算率，
底座只有两分法，它们按缺省落在「流量」侧 —— 页尾 notes 里点名交代，别去相加。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'lseg.csv')


# ══════════════════════════════════════════════════════════════════════════════
# import 期的现算工具。全部「读不到就退回不含数字的定性版本」，不抛异常。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, col):
    try:
        v = r[col].strip()
    except (KeyError, AttributeError):
        return None
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


_ROWS = _rows()


# ── 每一列出自哪条腿：三级取值，一级都不硬编码在图注里 ──────────────────────
# ① fetch/lseg.py 的模块常量 COLUMN_LEG（权威，跟着抓取代码一起改）
# ② series/lseg_part_<leg>.csv 的表头（数据本身，spec 已经依赖 series/）
# ③ 本文件的字面量兜底 —— 只在前两者都读不到时用。
#    兜底存在的理由与 db1.py 相同：spec 被读的时候不该因为 fetch/ 缺席而炸，
#    「删掉这一家不留残渣」也要求 spec 不硬依赖 fetch/。
_LEGS = ('orderbook', 'primary', 'tradeweb', 'lch')

_LEG_PREFIX_FALLBACK = (
    ('orderbook', ('lse_orderbook_', 'lse_trading_days', 'turquoise_',
                   'lse_lit_uk_share_pct', 'gbp_eur_rate')),
    ('primary', ('mm_', 'aim_')),
    ('tradeweb', ('tradeweb_',)),
    ('lch', ('swapclear_', 'forexclear_', 'repoclear_')),
)


def _leg_map_from_fetch():
    path = os.path.join(_ROOT, 'fetch', 'lseg.py')
    try:
        import importlib.util
        sp = importlib.util.spec_from_file_location('_lseg_fetch_for_spec', path)
        mod = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(mod)
        m = dict(mod.COLUMN_LEG)
        return m if m else None
    except Exception:
        return None


def _leg_map_from_parts():
    m = {}
    for leg in _LEGS:
        p = os.path.join(_ROOT, 'series', 'lseg_part_%s.csv' % leg)
        try:
            with open(p, encoding='utf-8') as fh:
                head = next(csv.reader(fh))
        except (OSError, StopIteration):
            return None
        for c in head:
            if c != 'month':
                m[c] = leg
    return m or None


def _leg_map_fallback():
    m = {}
    for r in _ROWS[:1]:
        for c in r:
            if c == 'month':
                continue
            for leg, pref in _LEG_PREFIX_FALLBACK:
                if c.startswith(pref):
                    m[c] = leg
                    break
    return m


COLUMN_LEG = _leg_map_from_fetch() or _leg_map_from_parts() or _leg_map_fallback()


def _leg_span(leg):
    """(列数, 首个有值的月, 最后一个有值的月, 有值的月数)；算不出返回 (None,)*4。"""
    cols = [c for c, lg in COLUMN_LEG.items() if lg == leg]
    if not cols or not _ROWS:
        return (None,) * 4
    got = [r['month'] for r in _ROWS if any(_num(r, c) is not None for c in cols)]
    if not got:
        return (len(cols), None, None, 0)
    return len(cols), got[0], got[-1], len(got)


_SPAN = dict((lg, _leg_span(lg)) for lg in _LEGS)


def _span_txt():
    """四条腿各自覆盖到哪个月 —— 页尾要报的那句话，一个数都不写死。"""
    bits = []
    for lg in _LEGS:
        n, a, b, k = _SPAN[lg]
        if n is None or a is None:
            continue
        bits.append('<code>%s</code> %d 列 %s–%s（%d 个月有值）' % (lg, n, a, b, k))
    return '、'.join(bits)


def _leg_blanks(leg):
    """该腿在**自己的跨度**内还空着几格。算不出返回 None。

    「零空格」这句话原先是写死在图注里的，而它随时会被回补改掉 ——
    orderbook 补到 2016-01 之后 tradeweb 就不再是「唯一零空格的一组」了，
    图注却还在那么说。这里改成现算：判据 = 该腿首个有值月到末个有值月之间，
    该腿的列 × 月里有多少格是空的。同一路里各列起点不同（primary 的两个市场、
    lch 的三个法人）会**如实计入**，因为那正是读图的人会撞上的空白。
    """
    cols = [c for c, lg in COLUMN_LEG.items() if lg == leg]
    n, a, b, _k = _SPAN[leg]
    if not cols or a is None:
        return None
    win = [r for r in _ROWS if a <= r['month'] <= b]
    return sum(1 for r in win for c in cols if _num(r, c) is None)


def _col_span(col):
    """(首个有值月, 末个有值月, 有值月数, [跨度内的空洞月])；算不出返回 (None,)*4。"""
    got = [r['month'] for r in _ROWS if _num(r, col) is not None]
    if not got:
        return (None,) * 4
    holes = [r['month'] for r in _ROWS
             if got[0] <= r['month'] <= got[-1] and _num(r, col) is None]
    return got[0], got[-1], len(got), holes


# ── build/yoy.py 的单例加载器 ──────────────────────────────────────────────
# 本文件里有四处要问 yoy（近零基数判定、次轴会不会画出来、口径实测证据 ×2）。
# 原先每处各 `exec_module` 一遍，import 期把同一个模块跑了十几次；更要紧的是
# **口径只能有一份实现**这条规矩在读法上也该成立：全文件只有这一个入口拿得到 yoy。
# 读不到一律返回 None，调用方退回不含数字的定性说法 —— spec 的 import 期绝不抛异常。
_YOY_UNSET = object()
_YOY_MOD = _YOY_UNSET


def _yoy():
    global _YOY_MOD
    if _YOY_MOD is _YOY_UNSET:
        try:
            import importlib.util
            sp = importlib.util.spec_from_file_location(
                '_yoy_for_spec', os.path.join(_ROOT, 'build', 'yoy.py'))
            m = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(m)
            _YOY_MOD = m
        except Exception:
            _YOY_MOD = None
    return _YOY_MOD


def _series(col):
    """一列 → pandas.Series（index = 月份）。pandas 缺席或整列为空返回 None。"""
    try:
        import pandas as pd
        s = pd.Series([_num(r, col) for r in _ROWS],
                      index=[r['month'] for r in _ROWS], dtype='float64')
        return s if s.notna().any() else None
    except Exception:
        return None


# 底座给一列画出来的窗口：最后 25 个月（build/single.py WIN_LONG），
# **右端是该列自己最后一个有值的月**（`ex_single` 用 `self.last_month(c)`），
# 不是本页数据月 —— 慢腿的图右端比头条早两三周，用错窗口报出来的实测是图外的事。
_WIN_LONG = 25


def _drawn_window(col):
    idx = [r['month'] for r in _ROWS]
    got = [r['month'] for r in _ROWS if _num(r, col) is not None]
    if not got:
        return None
    i = idx.index(got[-1])
    return idx[max(0, i - _WIN_LONG + 1): i + 1]


# ── 近零基数列：判据与实现都在 build/yoy.py，本文件只报结果 ────────────────
# CONTRACT §6.1 第 6 条：近零基数的序列不画同比、画水平值。
# 本页的落实方式是**排版**而不是开关：这些列一律放进 2–5 列同单位的组，
# 底座对多列桶画 lines（只有水平值、没有次轴同比），于是那条会跳到几百个百分点的
# 同比线根本不会被画出来。下面这个函数只负责把「哪几列」现算出来写进图注。
#
# ⚠️ 2026-08-07 修正：`win` 必须给**图上真正画出来的那 25 个月**，原先漏了这个参数。
# `yoy.near_zero_base` 的 docstring 明写：「有几个月不可读」只能数图上画出来的那些月 ——
# 一条 2010 年近零、现在早已正常的序列，拿全历史计数就会永远背着这个标签，那是制造噪声。
# 漏参数的实际后果（本页实测）：Tradeweb 互换/掉期期权 <1Y、美国投资级·全电子、
# 美国高收益·全电子三列被判成近零基数（它们的近零月全在 2017–2019，窗口内占比 0.0%），
# 而主板新上市家数（合计）反过来被漏掉（全历史 7.2% < 1/12，窗口内 16.0%）。
# 页注据此对着 Tradeweb <1Y ADV 本月「604 vs 391 → +54.4%」喊「这是分母的故事」，
# 那是一句实打实的假话。改后命中 8 条，全部落在一级市场那条腿上。
def _near_zero_cols(cols):
    yoy = _yoy()
    if yoy is None:
        return None
    out = []
    for c in cols:
        try:
            s = _series(c)
            if s is None:
                continue
            if yoy.near_zero_base(s, win=_drawn_window(c))['flag']:
                out.append(c)
        except Exception:
            continue
    return out


def _near_zero_now(col):
    """本页数据月那一格的 y/y，**基期**是不是近零 —— 汇总表里到底哪几格不能照读。

    与 `_near_zero_cols()` 判的不是同一件事，混起来就会写出假话：
      · `_near_zero_cols()` 判的是**整条序列**该不该画同比线（§6.1 第 6 条，
        按窗口内「近零基数月」的占比 ≥ 1/12）；
      · 这个函数判的是**这一格**：本月的基期（去年同月）到底有没有小到读不动。
    一条序列完全可以整体命中而本月基期正常 —— 主板增发募资额本月基期 408 GBP mn，
    汇总表印的 −95.2% 是一个可读的数。对着它喊「这是分母的故事」，页注就在骗人。

    返回 dict（now / cut / base / scale）或 None（读不到就不报）。
    """
    yoy = _yoy()
    s = _series(col)
    if yoy is None or s is None or not _THROUGH:
        return None
    try:
        nz = yoy.near_zero_base(s, win=_drawn_window(col))
        yago = '%04d-%02d' % (int(_THROUGH[:4]) - 1, int(_THROUGH[5:7]))
        row = _row_at(yago)
        b = _num(row, col) if row else None
        if b is None or not (nz['cut'] == nz['cut']):
            return None
        return {'now': abs(b) < nz['cut'], 'cut': nz['cut'],
                'base': b, 'scale': nz['scale']}
    except Exception:
        return None


def _mom_drawn(col, ratio=False):
    """底座会不会真的给这一列画出次轴单月同比 —— 决定组名里那句声明能不能写。

    为什么必须由数据判：`gs_bar` 在整条同比都算不出来时会退成 `bars_labeled`
    （build/single.py 的 `yoy_rhs` 返回 None），此时组名里写「次轴：单月同比」就是
    一句印在页面上的假话。LCH 的 RepoClear 两列现在只有 12 期，正好是这种情形；
    再跑一个月它们就长到 13 期、金线自己会出现 —— 声明必须跟着数据走，不能写死。

    口径不自己实现：**同比一律走 build/yoy.py**（本仓铁律，CONTRACT §6）。
    这里把 `yoy.mom_yoy()`（已处理零基期与两期异号）与 `yoy.NEAR_ZERO_BASE_FRAC`
    的近零基期过滤叠起来，正好等价于 build/single.py `yoy_line` 的判据。
    读不到 build/yoy.py 就退回保守判据「非空月数 ≥ 13」。
    """
    vals = [_num(r, col) for r in _ROWS]
    if sum(1 for v in vals if v is not None) < 13:
        return False
    yoy = _yoy()
    s = _series(col)
    if yoy is None or s is None:
        return True
    try:
        import numpy as np
        y = yoy.mom_yoy(s, yoy.RATIO if ratio else yoy.FLOW)
        if not ratio:
            scale = float(np.nanmedian(np.abs(s.values.astype(float))))
            if np.isfinite(scale) and scale:
                y = y.mask(s.shift(yoy.LAG).abs() < yoy.NEAR_ZERO_BASE_FRAC * scale)
        # 底座画的窗口是最后 25 个月（build/single.py WIN_LONG），只数窗内。
        return bool(np.isfinite(y.values.astype(float)[-25:]).any())
    except Exception:
        return True


def _fin(v):
    """有限的 float，否则 None。用来把 yoy 回来的 nan 挡在字符串格式化之外。"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float('inf'), float('-inf')) else None


def _mom_evidence(col, ratio=False):
    """本序列自己实测的两种同比口径差异 —— CONTRACT §6.1 第 2 条后半要的那份证据。

    第 2 条明写：理由「请用 `yoy.describe(yoy.caliber_diff(s, kind, win))` 生成 ——
    它拿**这条序列自己**实测，不引别家的例子」。这里就是那一步，两个参数都不能马虎：

      · `kind` 必须与图上那条金线一致。比率列走 RATIO（百分点差），其余走 FLOW（%）。
        写错的代价是报出来的标准差与读者看到的线不是一回事。
      · `win` 必须是**图上真正画出来的那 25 个月**（`_drawn_window`），不是全历史。
        `yoy.caliber_diff` 的 docstring 明写：全历史算出来的「符号相反的月份占比」
        会逼近 100%（任何一条几十年的序列总找得到一个相反的月），那个数没有信息量；
        而且慢腿的图右端比本页数据月早两三周，用错窗口报的是图外的事。

    读不到 build/yoy.py 或 pandas 返回 None，调用方退回不含数字的定性说法。
    """
    yoy = _yoy()
    s = _series(col)
    if yoy is None or s is None:
        return None
    try:
        win = _drawn_window(col)
        d = yoy.caliber_diff(s, yoy.RATIO if ratio else yoy.FLOW, win=win)
        d['_win'] = win
        return d
    except Exception:
        return None


def _ev_short(col, ratio=False, ttm_meaningless=False):
    """组名（= 图标题）里那半句实测：短，但必须是**数字**，不是形容词。

    `ttm_meaningless=True` 用于「滚动口径在算术上就不指代任何量」的列（换算率）：
    那种列的 σ_ttm 底座照样算得出来，但把它印出来等于给一个不存在的东西报精度，
    所以这里**故意不报**，只报单月侧，并把不报的理由写出来。
    """
    d = _mom_evidence(col, ratio)
    if not d:
        return ''
    win = d.get('_win') or []
    span = ('近 %d 个月' % len(win)) if win else '窗口内'
    sm, st = _fin(d.get('std_mom')), _fin(d.get('std_ttm'))
    if ratio:
        return ('；本序列%s实测单月同比逐月标准差 %.1fpp，滚动口径对比率非法、没有可比数'
                % (span, sm)) if sm is not None else ''
    if ttm_meaningless:
        return ('；本序列%s实测单月同比逐月标准差 %.1fpp，滚动口径不报数：'
                '把 12 个月的换算率加起来不指代任何量' % (span, sm)) if sm is not None else ''
    floor = getattr(_yoy(), 'MIN_DIAG_MONTHS', 12)
    if (d.get('n') or 0) < floor:
        return ('；本序列实测两种口径都有值的月份只有 %d 个（< %d），量不出差异'
                % (d.get('n') or 0, floor))
    if sm is None or st is None:
        return ''
    return ('；本序列%s实测单月同比逐月标准差 %.1fpp、12 个月滚动 %.1fpp，符号相反 %d 个月'
            % (span, sm, st, d.get('opposite_n') or 0))


def _ev_long(col, ratio=False, ttm_meaningless=False):
    """页尾口径说明里那一整段实测 —— 与 Exhibit 59/60 图注里底座那段同一套统计量。

    为什么落在页尾而不是图注：`gs_bar` 的 `note` 整段由 build/single.py 的
    `ex_single()` 拼装，spec 侧一个字都插不进去（`COL_KEYS` 与 `groups` 的允许键里
    都没有 note 这一项）。页尾的「口径与方法说明」是本文件够得到的、离图最近的位置。
    **这是本轮的已知妥协，不是等价物**：要让这段真的落进图注，必须改底座。
    """
    d = _mom_evidence(col, ratio)
    if not d:
        return '（读不到 series/lseg.csv 或 build/yoy.py，本轮报不出实测数。）'
    win = d.get('_win') or []
    span = ('%s–%s 共 %d 个月' % (win[0], win[-1], len(win))) if win else '图上窗口'
    sm, st = _fin(d.get('std_mom')), _fin(d.get('std_ttm'))
    n = d.get('n') or 0
    if ratio:
        return ('实测（%s）：单月同比逐月标准差 <b>%s pp</b>、相邻月跳变中位 %s pp。'
                '<b>没有滚动侧的数可比，这本身就是理由</b> —— %s'
                % (span,
                   '—' if sm is None else '%.2f' % sm,
                   '—' if _fin(d.get('medjump_mom')) is None else '%.2f' % d['medjump_mom'],
                   d.get('reason') or '比率不做滚动合计也不做滚动均值。'))
    floor = getattr(_yoy(), 'MIN_DIAG_MONTHS', 12)
    if n < floor:
        return ('实测（%s）：两种口径都有值的月份只有 <b>%d</b> 个（< %d），'
                '<b>量不出差异 —— 这正是「滚动口径在这条序列上还不存在」的证据</b>。'
                % (span, n, floor))
    head = ('实测（%s，其中 %d 个月两种口径都有值）：单月同比逐月标准差 <b>%s pp</b>，'
            % (span, n, '—' if sm is None else '%.1f' % sm))
    if ttm_meaningless:
        return (head + '滚动侧<b>故意不报</b>：把 12 个月的换算率加起来不指代任何量，'
                       '给它报一个标准差等于给不存在的东西报精度。'
                       '这条序列的合法口径只有点对点，所以这里没有「两种口径可选」这回事。')
    tail = ('12 个月滚动 <b>%s pp</b>（放大 %s 倍）；相邻月跳变中位 %s pp vs %s pp。'
            % ('—' if st is None else '%.1f' % st,
               '—' if _fin(d.get('std_ratio')) is None else '%.2f' % d['std_ratio'],
               '—' if _fin(d.get('medjump_mom')) is None else '%.1f' % d['medjump_mom'],
               '—' if _fin(d.get('medjump_ttm')) is None else '%.1f' % d['medjump_ttm']))
    if d.get('opposite_n'):
        tail += ('两者<b>符号相反</b>的月份有 %d 个（占 %.0f%%）。'
                 % (d['opposite_n'], 100 * (d.get('opposite_share') or 0)))
    else:
        tail += '窗口内没有符号相反的月份。'
    g = d.get('worst_gap')
    if g:
        tail += '差得最远的是 %s：单月 %+.1f%% 而滚动 %+.1f%%。' % (g[0], g[1], g[2])
    return head + tail


def _mom_tag(col, why, ratio=False, ttm_meaningless=False):
    """组名后缀：声明单月口径**并给出理由**（CONTRACT §6.1 第 2 条的前后两半）。

    第 2 条要求「标题里写明单月」**并且**「在图注说明为什么这里该用单月」。
    后半句本该落在图注里，但单列桶画出来的 `gs_bar`，其 `note` 整段由
    build/single.py 的 `ex_single()` 拼装，spec 侧一个字都插不进去 ——
    `COL_KEYS` 与 `groups` 的允许键里都没有 note 这一项（build/single.py:103、757）。
    所以理由跟着声明一起写进组名：组名会原样印进图标题，是这张图上**唯一**
    由本文件控制的字符串。页尾 `_NOTE_MOM_WHY` 再把同一批理由逐图列一遍。

    `why` 必须是**口径**理由，不能是「看着更灵敏」（CONTRACT §6.1 第 2 条明写）。
    本文件里只有三类合法理由，且每一类都能回到数据上核：
      · 比率列 —— 比率不做滚动合计也不做滚动均值（§6.1 第 5 条）；
      · 该序列的滚动口径根本不存在（LCH 只有 24 期，滚动同比只剩 1 个点）；
      · 命题本身就是「一个月之内会怎样」（交易日数、月报自印的换算率）。
    给不出这三类理由的流量列，本文件的处理是**不让它单列成桶**（见一级市场
    增发笔数那一组、以及 Tradeweb 其他政府债那一组），而不是硬编一个理由。

    2026-08-07 补上第 2 条的**后半句里那半句**：理由不能只是定性的一句话，
    §6.1 第 2 条要求「用 `yoy.describe(yoy.caliber_diff(s, kind, win))` 生成 ——
    它拿这条序列自己实测」。所以 `_ev_short()` 现算的实测数跟着理由一起进标题，
    完整段落进页尾 `_NOTE_MOM_WHY`。一个数都不写死：换个月、换条数据全跟着变。
    """
    if not _mom_drawn(col, ratio):
        return ''
    what = '单月同比，百分点差' if ratio else '单月同比'
    return '（次轴：%s —— %s%s）' % (what, why,
                                    _ev_short(col, ratio, ttm_meaningless))


def _median_drawn(col):
    """该列在**图上那 25 个月**里的中位数。页注要报的量级对比取这个数，不写死。

    用画出来的窗口而不是全历史：拿来说事的是「这两条线放同一根轴上会不会把小的压平」，
    那是读者眼前这 25 个月的事，不是 2017 年的事。
    """
    win = set(_drawn_window(col) or [])
    v = sorted(x for x in (_num(r, col) for r in _ROWS if r.get('month') in win)
               if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _scale_gap_txt(col_a, col_b):
    """「近 25 个月中位 A vs B，差 N 倍」—— 两列量级差多少，现算。"""
    a, b = _median_drawn(col_a), _median_drawn(col_b)
    if not a or not b:
        return '两列的中位量级读不到（缺 CSV）'
    hi, lo = (a, b) if abs(a) >= abs(b) else (b, a)
    return ('近 %d 个月中位 %s vs %s，差 %.1f 倍'
            % (_WIN_LONG, ('%.1f' % a), ('%.1f' % b), abs(hi) / abs(lo)))


def _n_obs(col):
    """该列有值的月份数。读不到返回 None（调用方退回不含数字的定性说法）。"""
    if not _ROWS:
        return None
    return sum(1 for r in _ROWS if _num(r, col) is not None)


# 滚动同比的第一个点要 24 期（12 期滚动合计 + 再往前 12 期），**连成线**要 25 期。
_TTM_FIRST, _TTM_LINE = 24, 25


def _short_hist_why(col):
    """「历史太短、滚动口径根本不存在」这条理由 —— 期数现算，不写死。

    写死成「本腿只有 24 期」的代价是**它会自己变成假话**：LCH 每跑一个月就长一期，
    到第 25 期滚动同比就连得成线了，而标题上那句理由还在说算不出来。
    所以这里由数据判：够长了就换成一句自曝的话，让下一个人看见「这张图该改口径了」，
    而不是让页面继续印一个已经不成立的辩护。
    """
    n = _n_obs(col)
    if n is None:
        return '本腿历史短于滚动口径所需的长度，滚动同比连不成线'
    if n >= _TTM_LINE:
        return ('本列已有 %d 期、滚动口径已经算得出来 —— 这张图待改成滚动同比，'
                '当前的单月次轴是历史遗留' % n)
    pts = max(0, n - _TTM_FIRST + 1)
    return ('本列只有 %d 期，滚动同比要 %d 期才连得成线，现在只算得出 %d 个点'
            % (n, _TTM_LINE, pts))


# ══════════════════════════════════════════════════════════════════════════════
# 头条 —— 只有 Tradeweb 那条腿够格，理由见模块 docstring
# ══════════════════════════════════════════════════════════════════════════════
# 两条都取自**同一份**官方工作簿（Historical ADV and Day Count），刻意不像 enx 那样
# 「取自两份不同文件以交叉验证解析失败」—— 本页四条腿里只有这一条够快，
# 拿任何第二条腿当头条都会把 data_through 拖回上个月（见模块 docstring）。
# 两条并列做头条没问题，但**绝不能**把它们绑成量价恒等式（口径坑 B）。
HEADLINE = [
    {'col': 'tradeweb_volume_total_usd_tn', 'zh': 'Tradeweb 月成交额（全公司）',
     'unit': 'USD tn/month', 'fmt': 'f1'},
    {'col': 'tradeweb_adv_total_usd_bn', 'zh': 'Tradeweb ADV（全公司）',
     'unit': 'USD bn/day', 'fmt': 'f0c'},
]


# ══════════════════════════════════════════════════════════════════════════════
# 分组。列名逐个 `head -1 series/lseg.csv | tr ',' '\n' | nl` 核过。
# 组的先后 = fetch/lseg.py 的 PARTS 顺序（orderbook → primary → tradeweb → lch），
# 这样末尾核对表的列序与 series/lseg.csv 尽量对齐，逐格对账时不用来回找。
#
# 两条排版纪律（不是审美，是口径）：
#  ① 组名里写「次轴：单月同比」的组，**只允许含一个会画成 gs_bar 的桶**。
#     组名会原样印到该组拆出来的每一张图的标题上，多列桶画的是 lines、根本没有次轴，
#     那句声明落上去就成了假话（enx.py 为同一件事把六个指标各自单列成组）。
#     存量列走的是点对点同比，也不适用这句声明，所以存量列一律另起一组。
#  ② 量级差 20 倍以上的同单位列拆到不同组。底座只按 `unit` 分桶，不按量级 ——
#     把 2,535 和 3.3 画在一根轴上，小的那条振幅只占画布 0.1%，等于白画。
# ══════════════════════════════════════════════════════════════════════════════
GROUPS = [
    # ── 一、LSE / Turquoise 电子订单簿（慢腿，最新月比头条晚 2–3 周）──────────
    {'zh': 'LSE 与 Turquoise 订单簿成交额（当月合计）', 'cols': [
        {'col': 'lse_orderbook_value_gbp_m', 'zh': 'LSE 主板订单簿成交额',
         'unit': 'GBP mn/month', 'fmt': 'f0c'},
        {'col': 'turquoise_integrated_value_gbp_m', 'zh': 'Turquoise Integrated 成交额',
         'unit': 'GBP mn/month', 'fmt': 'f0c'},
        {'col': 'turquoise_dark_value_gbp_m', 'zh': 'Turquoise Dark 成交额',
         'unit': 'GBP mn/month', 'fmt': 'f0c'},
    ]},

    {'zh': 'LSE 与 Turquoise 订单簿日均成交额（ADV）', 'cols': [
        {'col': 'lse_orderbook_adv_gbp_m', 'zh': 'LSE 主板订单簿 ADV',
         'unit': 'GBP mn/day', 'fmt': 'f0c'},
        {'col': 'turquoise_integrated_adv_gbp_m', 'zh': 'Turquoise Integrated ADV',
         'unit': 'GBP mn/day', 'fmt': 'f0c'},
        {'col': 'turquoise_dark_adv_gbp_m', 'zh': 'Turquoise Dark ADV',
         'unit': 'GBP mn/day', 'fmt': 'f0c'},
    ]},

    {'zh': 'LSE 与 Turquoise 订单簿成交笔数（当月合计）', 'cols': [
        {'col': 'lse_orderbook_trades_count', 'zh': 'LSE 主板订单簿成交笔数',
         'unit': 'trades/month', 'fmt': 'f0c'},
        {'col': 'turquoise_integrated_trades_count', 'zh': 'Turquoise Integrated 成交笔数',
         'unit': 'trades/month', 'fmt': 'f0c'},
        {'col': 'turquoise_dark_trades_count', 'zh': 'Turquoise Dark 成交笔数',
         'unit': 'trades/month', 'fmt': 'f0c'},
    ]},

    # ⚠️ 这三列的 fmt 是 `f0`（不带千分位）而不是隔壁几组的 `f0c`，**这是几何不是口味**。
    # 这一桶画成 `lines_endlabels`，左端数值标签 anchor=end 落在 `M.l − 10 − tickW`
    # （charts.js:1450），而纵轴标题是竖排画在 `fscale(13)` 上的 —— 两者之间只剩
    # 一条固定宽度的走廊。窗口拉到 2016-01（127 期）之后左端标签变成 2016-01 的
    # 七位数日均笔数，带千分位是 9 个字符，正好把这条走廊吃穿：实测（Chrome 151，
    # 浅色）1280px 视口下压住轴标题「trades/day」56.4px²、768px 下 58.3px²，两端点
    # 各一处，共 4 条 visual_qa 告警。去掉两个逗号后标签窄 11%，左端退到轴标题右侧：
    # 实测净空 1280px 下 +1.70px、768px 下 +0.30px（两处都从「压 5.9 / 6.5px」变成不相交）。
    # 768px 那 0.30px 很薄，但它是确定性的：左端点是 2016-01 的历史值、位数不会再变，
    # 而左轴刻度只要还停在 7 位数（本列上限 2,036,686，要涨到 1e7 才多一位）走廊就不动。
    # 顺带一个好处：左轴刻度本来就是引擎 plainAxis 画的、不带千分位（'1500000'），
    # 端点标签改成 f0 之后与刻度的写法一致了，不再是同一张图里两套数字写法。
    #
    # 为什么不是别的办法：
    #   · 小数位不能动 —— 这三列本来就是整数笔数，`f0c` 与 `f0` 的位数完全相同，
    #     换的只有分隔符；末尾核对表走 `single.fmt_val()`，那一份**无论 fmt 是
    #     f0 还是 f0c 都补千分位**（见 single.py:253 的 docstring），所以核对表
    #     与汇总表逐字节不变，仍是「1,270,124」。变的只有图上标签与图内表格视图。
    #   · 不能靠 `build/chartscale.py` 的显示缩放（隔壁 Ex 6「（千）」/ Ex 8「（百万）」
    #     就是它做的）：它的预算模型按 FS=1 算，本图标签 35.6px < 预算 39.5px，判「不需要」，
    #     而真实渲染的通栏字号 FS=1.70 把标签放大到 60.5px、走廊却只跟着放大一部分
    #     （charts.js:1450 那个 `− 10` 是写死的、不随 FS 长）。那是底座的口子，不在本页改。
    #   · 不能改 `unit` 让轴标题短一点：竖排文字的**横向**占位是字高、与字数无关
    #     （实测本页 'trades/day' 与 '% of UK lit order book' 的横向墨迹都是 9.6px）；
    #     而两个端点标签正好一上一下夹住轴标题的中心，缩短它只会让它更居中，救不了。
    {'zh': 'LSE 与 Turquoise 订单簿日均成交笔数', 'cols': [
        {'col': 'lse_orderbook_avg_daily_trades_count', 'zh': 'LSE 主板订单簿日均笔数',
         'unit': 'trades/day', 'fmt': 'f0'},
        {'col': 'turquoise_integrated_avg_daily_trades_count',
         'zh': 'Turquoise Integrated 日均笔数', 'unit': 'trades/day', 'fmt': 'f0'},
        {'col': 'turquoise_dark_avg_daily_trades_count', 'zh': 'Turquoise Dark 日均笔数',
         'unit': 'trades/day', 'fmt': 'f0'},
    ]},

    # 两条份额的**分母不是同一个盘子**（一个是英国 Lit 订单簿，一个是泛欧 Lit+Dark），
    # 所以单位串刻意写成两个不同的字符串 —— 这既是事实，也顺带让底座把它们拆成两图，
    # 免得 3.5% 那条贴着横轴、69.2% 那条贴着顶，两条都读不出变化。
    {'zh': 'LSE 在英国 Lit 订单簿的成交份额'
           + _mom_tag('lse_lit_uk_share_pct',
                      '比率列不做滚动合计也不做滚动均值，CONTRACT §6.1 第 5 条',
                      ratio=True), 'cols': [
        {'col': 'lse_lit_uk_share_pct', 'zh': 'LSE 英国 Lit 订单簿份额',
         'unit': '% of UK lit order book', 'fmt': 'pct1'},
    ]},

    {'zh': 'Turquoise 泛欧 Lit + Dark 成交份额'
           + _mom_tag('turquoise_paneuropean_share_pct',
                      '比率列不做滚动合计也不做滚动均值，CONTRACT §6.1 第 5 条',
                      ratio=True), 'cols': [
        {'col': 'turquoise_paneuropean_share_pct', 'zh': 'Turquoise 泛欧成交份额',
         'unit': '% of pan-European lit+dark', 'fmt': 'pct1'},
    ]},

    {'zh': 'LSE 与 Turquoise 当月交易日数（两套日历，可以不等）', 'cols': [
        {'col': 'lse_trading_days_count', 'zh': 'LSE 交易日数',
         'unit': 'days/month', 'fmt': 'f0'},
        {'col': 'turquoise_trading_days_count', 'zh': 'Turquoise 交易日数',
         'unit': 'days/month', 'fmt': 'f0'},
    ]},

    # 这一列既不是流量也不是存量，是月报**自己印在表头上**的换算常数。
    # 收它不是为了看汇率，是为了让读者能验证上面 Turquoise 那几列取的是 £m 那一栏
    # 而不是 €m 那一栏（€m 栏 = £m 栏 × 本列，取数腿逐格验证过）。
    {'zh': 'LSE 月报自印的 GBP/EUR 换算率'
           + _mom_tag('gbp_eur_rate',
                      '换算率不是流量，12 个月加总不指代任何东西，只能点对点比',
                      ttm_meaningless=True), 'cols': [
        {'col': 'gbp_eur_rate', 'zh': '月报自印 GBP/EUR 换算率',
         'unit': 'EUR per GBP', 'fmt': 'f3'},
    ]},

    # ── 二、LSE 一级市场：Main Market 与 AIM（慢腿）─────────────────────────
    # 家数与募资额这几列有大量 0 值月（2026-08-19 现量：主板 98 期里 7–36 个月为 0，
    # AIM 114 期里 9–71 个月为 0，最狠的是 AIM 新上市家数 Intl 那一列），
    # 按 CONTRACT §6.1 第 6 条属于近零基数序列：**只画水平值、不画同比**。
    # 落实办法是把它们放进多列同单位桶 → 底座画 lines（没有次轴同比），
    # 而不是让它们各自成为单桶 gs_bar 去画一条会跳到几百个百分点的金线。
    {'zh': 'Main Market 当月新上市与退市家数', 'cols': [
        {'col': 'mm_new_issues_count', 'zh': '主板新上市家数（合计）',
         'unit': 'companies/month', 'fmt': 'f0'},
        {'col': 'mm_new_issues_uk_count', 'zh': '主板新上市家数（UK）',
         'unit': 'companies/month', 'fmt': 'f0'},
        {'col': 'mm_new_issues_intl_count', 'zh': '主板新上市家数（Intl）',
         'unit': 'companies/month', 'fmt': 'f0'},
        {'col': 'mm_cancellations_count', 'zh': '主板退市家数',
         'unit': 'companies/month', 'fmt': 'f0'},
    ]},

    {'zh': 'Main Market 当月募资额（新上市 vs 增发）', 'cols': [
        {'col': 'mm_money_raised_new_gbp_mn', 'zh': '主板新上市募资额',
         'unit': 'GBP mn/month', 'fmt': 'f0c'},
        {'col': 'mm_money_raised_further_gbp_mn', 'zh': '主板增发募资额',
         'unit': 'GBP mn/month', 'fmt': 'f0c'},
    ]},

    {'zh': 'Main Market 月末上市公司家数', 'cols': [
        {'col': 'mm_companies_eop_count', 'zh': '主板上市公司家数（合计）',
         'unit': 'companies', 'fmt': 'f0c', 'stock': True},
        {'col': 'mm_companies_uk_eop_count', 'zh': '主板上市公司家数（UK）',
         'unit': 'companies', 'fmt': 'f0c', 'stock': True},
        {'col': 'mm_companies_intl_eop_count', 'zh': '主板上市公司家数（Intl）',
         'unit': 'companies', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'Main Market 月末总市值', 'cols': [
        {'col': 'mm_marketcap_eop_gbp_mn', 'zh': '主板总市值（合计）',
         'unit': 'GBP mn', 'fmt': 'f0c', 'stock': True},
        {'col': 'mm_marketcap_uk_eop_gbp_mn', 'zh': '主板总市值（UK）',
         'unit': 'GBP mn', 'fmt': 'f0c', 'stock': True},
        {'col': 'mm_marketcap_intl_eop_gbp_mn', 'zh': '主板总市值（Intl）',
         'unit': 'GBP mn', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'AIM 当月新上市与退市家数', 'cols': [
        {'col': 'aim_new_issues_count', 'zh': 'AIM 新上市家数（合计）',
         'unit': 'companies/month', 'fmt': 'f0'},
        {'col': 'aim_new_issues_uk_count', 'zh': 'AIM 新上市家数（UK）',
         'unit': 'companies/month', 'fmt': 'f0'},
        {'col': 'aim_new_issues_intl_count', 'zh': 'AIM 新上市家数（Intl）',
         'unit': 'companies/month', 'fmt': 'f0'},
        {'col': 'aim_cancellations_count', 'zh': 'AIM 退市家数',
         'unit': 'companies/month', 'fmt': 'f0'},
    ]},

    {'zh': 'AIM 当月募资额（新上市 vs 增发）', 'cols': [
        {'col': 'aim_money_raised_new_gbp_mn', 'zh': 'AIM 新上市募资额',
         'unit': 'GBP mn/month', 'fmt': 'f1'},
        {'col': 'aim_money_raised_further_gbp_mn', 'zh': 'AIM 增发募资额',
         'unit': 'GBP mn/month', 'fmt': 'f1'},
    ]},

    # Main Market 与 AIM 的增发笔数**合成一组**。这不是排版偏好，是口径：
    # 单列成桶的组底座一律画 gs_bar，而 gs_bar 的次轴写死是**单月**同比；
    # 这两列分别有 98 / 114 期、滚动口径完全算得出来，按 CONTRACT §6.1 第 1 条默认就该用滚动，
    # 而第 2 条要求用单月必须给出**口径上的**理由 —— 这两列给不出（既不是比率、
    # 历史也不短、命题也不是「一个月之内会怎样」）。与其在标题上硬编一个站不住的理由，
    # 不如让它们不再单列成桶：两列同单位（issues/month）、量级只差约 2 倍
    # （2026-08-19 现量中位 57 vs 123，远在本文件「差 20 倍才拆组」那条纪律之内），
    # 并成一个桶后底座改画 lines —— 只有水平值、没有次轴同比，
    # 于是这一页上不再出现一条无法辩护的单月同比线。
    {'zh': 'Main Market 与 AIM 当月增发笔数（同单位合图：避免各自成为单列柱图而被迫画单月同比）',
     'cols': [
        {'col': 'mm_further_issues_count', 'zh': '主板增发笔数',
         'unit': 'issues/month', 'fmt': 'f0'},
        {'col': 'aim_further_issues_count', 'zh': 'AIM 增发笔数',
         'unit': 'issues/month', 'fmt': 'f0'},
    ]},

    {'zh': 'AIM 月末上市公司家数', 'cols': [
        {'col': 'aim_companies_eop_count', 'zh': 'AIM 上市公司家数（合计）',
         'unit': 'companies', 'fmt': 'f0c', 'stock': True},
        {'col': 'aim_companies_uk_eop_count', 'zh': 'AIM 上市公司家数（UK）',
         'unit': 'companies', 'fmt': 'f0c', 'stock': True},
        {'col': 'aim_companies_intl_eop_count', 'zh': 'AIM 上市公司家数（Intl）',
         'unit': 'companies', 'fmt': 'f0c', 'stock': True},
    ]},

    # AIM 官方就没有市值的 UK / Intl 拆分（factsheet 里没这两格），所以只有一列。
    {'zh': 'AIM 月末总市值', 'cols': [
        {'col': 'aim_marketcap_eop_gbp_mn', 'zh': 'AIM 总市值',
         'unit': 'GBP mn', 'fmt': 'f0c', 'stock': True},
    ]},

    # ── 三、Tradeweb（快腿 = 头条那条腿）───────────────────────────────────
    # `tradeweb_adv_total_usd_bn` 在这里作为一条线再出现一次是**故意的**（db1 / enx
    # 同约定）：头条的契约职责是「定共同最新月与门槛」，会不会同时被画成图由底座决定。
    # 另一条头条 `tradeweb_volume_total_usd_tn` 不进任何组 —— 它已经有 4 张图
    # （长历史 + 同比 + 季节性 + 末尾的 12 个月滚动同比），再给它一张单桶柱图是纯重复；
    # 不进组也不影响它上核对表（底座的 table() 取 `head + groups`）。
    {'zh': 'Tradeweb 合计与两大主力资产类别 ADV', 'cols': [
        {'col': 'tradeweb_adv_total_usd_bn', 'zh': 'Tradeweb ADV（全公司）',
         'unit': 'USD bn/day', 'fmt': 'f0c'},
        {'col': 'tradeweb_adv_rates_usd_bn', 'zh': 'Tradeweb Rates ADV',
         'unit': 'USD bn/day', 'fmt': 'f0c'},
        {'col': 'tradeweb_adv_money_markets_usd_bn', 'zh': 'Tradeweb Money Markets ADV',
         'unit': 'USD bn/day', 'fmt': 'f0c'},
    ]},

    # 与上一组同单位但**量级差二三十倍**，所以另起一组（底座只按 unit 分桶，不按量级）。
    {'zh': 'Tradeweb 信用与股票 ADV（量级远小于利率，另图以免被压平）', 'cols': [
        {'col': 'tradeweb_adv_credit_usd_bn', 'zh': 'Tradeweb Credit ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_equities_usd_bn', 'zh': 'Tradeweb Equities ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb Rates ADV·现金 vs 衍生品', 'cols': [
        {'col': 'tradeweb_adv_rates_cash_usd_bn', 'zh': 'Tradeweb Rates·现金 ADV',
         'unit': 'USD bn/day', 'fmt': 'f0c'},
        {'col': 'tradeweb_adv_rates_derivatives_usd_bn', 'zh': 'Tradeweb Rates·衍生品 ADV',
         'unit': 'USD bn/day', 'fmt': 'f0c'},
    ]},

    # ⚠️ 2026-08-07 拆成两组，理由是**口径**不是排版。原来是「美国国债 / 按揭 /
    # 欧洲国债」一组 + 「其他政府债」单列一组，而单列成桶 ⇒ 底座画 gs_bar ⇒
    # 次轴写死是**单月**同比。其他政府债有 115 期、滚动口径完全算得出来，
    # 按 CONTRACT §6.1 第 1 条默认就该用滚动；第 2 条又要求用单月必须给出**口径上的**
    # 理由，而它给不出（不是比率、历史不短、命题也不是「一个月之内会怎样」）——
    # 原先标题上写的「留单月供逐月核对」是**用途**理由，不在第 2 条允许的两类里。
    # 与其在标题上硬编一个站不住的理由，不如让它不再单列成桶（同 Main Market /
    # AIM 增发笔数那一组的处置）：欧洲国债与其他政府债同单位（USD bn/day）、
    # 近 25 个月中位 58.4 vs 11.4（差 5.1 倍，远在本文件「差 20 倍才拆组」之内），
    # 并成一个桶后底座改画 lines —— 只有水平值、没有次轴同比。
    # 于是这一页上不再出现一条无法辩护的单月同比线，而滚动口径那张（页尾 ttm_yoy）
    # 仍然在，趋势判断看它。
    # 美国国债 / 按揭（近 25 个月中位各 240.2）与它们差 21 倍，所以留在自己那一组。
    {'zh': 'Tradeweb 利率现金分项 ADV·美国国债与按揭', 'cols': [
        {'col': 'tradeweb_adv_us_govt_bonds_usd_bn', 'zh': 'Tradeweb 美国国债 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_mortgages_usd_bn', 'zh': 'Tradeweb 按揭 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb 利率现金分项 ADV·欧洲国债与其他政府债'
           '（同单位合图：避免其他政府债单列成柱图而被迫画一条辩护不了的单月同比）',
     'cols': [
        {'col': 'tradeweb_adv_eu_govt_bonds_usd_bn', 'zh': 'Tradeweb 欧洲国债 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_other_govt_bonds_usd_bn', 'zh': 'Tradeweb 其他政府债 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb 利率互换与掉期期权 ADV（按剩余期限）', 'cols': [
        {'col': 'tradeweb_adv_swaps_swaptions_ge_1y_usd_bn',
         'zh': 'Tradeweb 互换/掉期期权 ≥1Y ADV', 'unit': 'USD bn/day', 'fmt': 'f0c'},
        {'col': 'tradeweb_adv_swaps_swaptions_lt_1y_usd_bn',
         'zh': 'Tradeweb 互换/掉期期权 <1Y ADV', 'unit': 'USD bn/day', 'fmt': 'f0c'},
    ]},

    {'zh': 'Tradeweb Credit ADV·现金 vs 衍生品', 'cols': [
        {'col': 'tradeweb_adv_credit_cash_usd_bn', 'zh': 'Tradeweb Credit·现金 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_credit_derivatives_usd_bn',
         'zh': 'Tradeweb Credit·衍生品 ADV', 'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb 信用细分 ADV（全电子与区域）', 'cols': [
        {'col': 'tradeweb_adv_us_hg_fully_electronic_usd_bn',
         'zh': 'Tradeweb 美国投资级·全电子 ADV', 'unit': 'USD bn/day', 'fmt': 'f2'},
        {'col': 'tradeweb_adv_us_hy_fully_electronic_usd_bn',
         'zh': 'Tradeweb 美国高收益·全电子 ADV', 'unit': 'USD bn/day', 'fmt': 'f2'},
        {'col': 'tradeweb_adv_european_credit_usd_bn', 'zh': 'Tradeweb 欧洲信用债 ADV',
         'unit': 'USD bn/day', 'fmt': 'f2'},
        {'col': 'tradeweb_adv_municipal_bonds_usd_bn', 'zh': 'Tradeweb 美国市政债 ADV',
         'unit': 'USD bn/day', 'fmt': 'f2'},
    ]},

    {'zh': 'Tradeweb Equities ADV·现金 vs 衍生品', 'cols': [
        {'col': 'tradeweb_adv_equities_cash_usd_bn', 'zh': 'Tradeweb Equities·现金 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_equities_derivatives_usd_bn',
         'zh': 'Tradeweb Equities·衍生品 ADV', 'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb ETF ADV（美国 vs 国际）', 'cols': [
        {'col': 'tradeweb_adv_us_etf_usd_bn', 'zh': 'Tradeweb 美国 ETF ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_intl_etf_usd_bn', 'zh': 'Tradeweb 国际 ETF ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb 货币市场 ADV·回购与其他', 'cols': [
        {'col': 'tradeweb_adv_repo_usd_bn', 'zh': 'Tradeweb 回购 ADV',
         'unit': 'USD bn/day', 'fmt': 'f0c'},
        {'col': 'tradeweb_adv_other_money_markets_usd_bn',
         'zh': 'Tradeweb 其他货币市场 ADV', 'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    # 单位串刻意写成 `days/month (blended)` 而不是 `days/month`：这一列是
    # 「月成交额 ÷ 月 ADV」反推出来的**集团级加权天数**（2026-07 = 23.06），
    # 不是日历事实，与上面 LSE / Turquoise 的整数交易日不可同轴比较。
    # 单位串不同 ⇒ 底座不会把它们放进同一个桶，这就是那条纪律的执行机制。
    {'zh': 'Tradeweb 集团加权交易日数'
           + _mom_tag('tradeweb_trading_days_blended',
                      '命题就是「这个月比去年同月多开几天」，滚动窗口正好把它抹平'), 'cols': [
        {'col': 'tradeweb_trading_days_blended', 'zh': 'Tradeweb 加权交易日数',
         'unit': 'days/month (blended)', 'fmt': 'f2'},
    ]},

    # ── 四、LCH 清算（慢腿，且历史被官方滚动窗口卡住，见口径坑 D）──────────
    {'zh': 'LCH SwapClear 当月新登记名义额（合计 vs 客户腿）', 'cols': [
        {'col': 'swapclear_notional_registered_usd_tn', 'zh': 'SwapClear 新登记名义额',
         'unit': 'USD tn/month', 'fmt': 'f1'},
        {'col': 'swapclear_client_notional_registered_usd_tn',
         'zh': 'SwapClear 新登记名义额（客户腿）', 'unit': 'USD tn/month', 'fmt': 'f1'},
    ]},

    {'zh': 'LCH SwapClear 当月新登记笔数（合计 vs 客户腿）', 'cols': [
        {'col': 'swapclear_trades_registered_count', 'zh': 'SwapClear 新登记笔数',
         'unit': 'trades/month', 'fmt': 'f0c'},
        {'col': 'swapclear_client_trades_registered_count',
         'zh': 'SwapClear 新登记笔数（客户腿）', 'unit': 'trades/month', 'fmt': 'f0c'},
    ]},

    # 这两列的 fmt 用 f0 而不是 f1，是**几何原因**不是口径原因：存量列各自单独成图、
    # 走 gs_bar，柱顶数值标签钉在自己那根柱上；25 根柱时一格只有 18.5px 宽，
    # 而 "544.9" 这样的 5 字标签宽 21.3px，会向左伸出去压住纵轴刻度
    # （build/chartscale.py 的 audit() 在构建日志里量出来的）。整数标签宽约 13px，够用。
    # 量级 543–637 USD tn 下丢一位小数是 0.02%，不影响与官方逐格对账到三位有效数字。
    {'zh': 'LCH SwapClear 月末存量（合计 vs 客户腿）', 'cols': [
        {'col': 'swapclear_notional_outstanding_eom_usd_tn',
         'zh': 'SwapClear 月末存量名义额', 'unit': 'USD tn', 'fmt': 'f0', 'stock': True},
        {'col': 'swapclear_client_notional_outstanding_eom_usd_tn',
         'zh': 'SwapClear 月末存量名义额（客户腿）', 'unit': 'USD tn', 'fmt': 'f0',
         'stock': True},
        {'col': 'swapclear_trades_outstanding_eom_count', 'zh': 'SwapClear 月末存量笔数',
         'unit': 'trades', 'fmt': 'f0c', 'stock': True},
        {'col': 'swapclear_client_trades_outstanding_eom_count',
         'zh': 'SwapClear 月末存量笔数（客户腿）', 'unit': 'trades', 'fmt': 'f0c',
         'stock': True},
    ]},

    # ForexClear 的两列量级差六个数量级（$tn vs 笔），单位串本来就不同 ⇒ 两个桶、
    # 各画一张 gs_bar，两张都会有次轴单月同比，所以这句声明对两张图都为真。
    {'zh': 'LCH ForexClear 当月清算量·双边计'
           + _mom_tag('forexclear_notional_registered_usd_tn',
                      _short_hist_why('forexclear_notional_registered_usd_tn')), 'cols': [
        {'col': 'forexclear_notional_registered_usd_tn', 'zh': 'ForexClear 当月清算名义额',
         'unit': 'USD tn/month', 'fmt': 'f2'},
        {'col': 'forexclear_trades_registered_count', 'zh': 'ForexClear 当月清算笔数',
         'unit': 'trades/month', 'fmt': 'f0c'},
    ]},

    {'zh': 'LCH ForexClear 月末未平仓', 'cols': [
        {'col': 'forexclear_notional_outstanding_eom_usd_tn',
         'zh': 'ForexClear 月末未平仓名义额', 'unit': 'USD tn', 'fmt': 'f2', 'stock': True},
        {'col': 'forexclear_trades_outstanding_eom_count', 'zh': 'ForexClear 月末未平仓笔数',
         'unit': 'trades', 'fmt': 'f0c', 'stock': True},
    ]},

    # RepoClear 两个法人**分组**：官方月表没有合计列，自己加是派生值（口径坑 E）；
    # 而且 SA 的量级是 LTD 的五到十倍，同轴会把 LTD 压平。
    {'zh': 'LCH RepoClear · LCH Ltd（伦敦）当月清算量', 'cols': [
        {'col': 'repoclear_ltd_nominal_value_eur_tn', 'zh': 'RepoClear Ltd 名义额',
         'unit': 'EUR tn/month', 'fmt': 'f2'},
        {'col': 'repoclear_ltd_cash_value_eur_tn', 'zh': 'RepoClear Ltd 现金额',
         'unit': 'EUR tn/month', 'fmt': 'f2'},
    ]},

    {'zh': 'LCH RepoClear · LCH SA（巴黎）当月清算量', 'cols': [
        {'col': 'repoclear_sa_nominal_value_eur_tn', 'zh': 'RepoClear SA 名义额',
         'unit': 'EUR tn/month', 'fmt': 'f2'},
        {'col': 'repoclear_sa_cash_value_eur_tn', 'zh': 'RepoClear SA 现金额',
         'unit': 'EUR tn/month', 'fmt': 'f2'},
    ]},

    # 清算**边数**不是笔数（官方术语 cleared trade sides）。两个法人再次分组：
    # SA 是 LTD 的 11 倍，同轴必然把 LTD 压成一条平线。
    {'zh': 'LCH RepoClear · LCH Ltd（伦敦）当月清算边数'
           + _mom_tag('repoclear_ltd_cleared_trade_sides_count',
                      _short_hist_why('repoclear_ltd_cleared_trade_sides_count')), 'cols': [
        {'col': 'repoclear_ltd_cleared_trade_sides_count', 'zh': 'RepoClear Ltd 清算边数',
         'unit': 'trade sides/month', 'fmt': 'f0c'},
    ]},

    {'zh': 'LCH RepoClear · LCH SA（巴黎）当月清算边数'
           + _mom_tag('repoclear_sa_cleared_trade_sides_count',
                      _short_hist_why('repoclear_sa_cleared_trade_sides_count')), 'cols': [
        {'col': 'repoclear_sa_cleared_trade_sides_count', 'zh': 'RepoClear SA 清算边数',
         'unit': 'trade sides/month', 'fmt': 'f0c'},
    ]},
]


def _charted():
    """本页真正画出来的列（头条 + 全部分组），按出现顺序去重。"""
    out, seen = [], set()
    for item in HEADLINE + [c for g in GROUPS for c in g['cols']]:
        if item['col'] not in seen:
            seen.add(item['col'])
            out.append(item['col'])
    return out


def _flow_charted():
    out, seen = [], set()
    for item in HEADLINE + [c for g in GROUPS for c in g['cols']]:
        if item['col'] in seen or item.get('stock'):
            continue
        seen.add(item['col'])
        out.append(item['col'])
    return out


# 慢腿 = 除 tradeweb 之外的三条腿。只列真正画了的列，避免 slow_cols 里出现幽灵列
# （底座对「slow_cols 里的列没出现在 headline/groups 里」硬失败 —— 那种拼错会让
# 慢腿声明静默失效）。头条列绝不会落进来：它们全在 tradeweb 那条腿上。
SLOW_COLS = sorted(c for c in _charted() if COLUMN_LEG.get(c) not in (None, 'tradeweb'))

_NEAR_ZERO = _near_zero_cols(_flow_charted())


# ── 近零基数列在**汇总表里**的标记 ────────────────────────────────────────
# 起因（2026-08-07 渲染核查）：CONTRACT §6.1 第 6 条「近零基数不画同比」在**图上**
# 落实了（这些列全在多列桶里，画的是 lines，没有次轴同比），但 Exhibit 1 汇总表照印
# y/y —— 最刺眼的是主板新上市募资额「本月 0、去年同月 2 GBP mn」印成 −100.0%。
#
# 这不是页面自相矛盾：CONTRACT §6.2 把「汇总表的 m/m 与 y/y 两列」明确列为豁免
# （那是运营核对表，读者拿它逐格对公司披露，把格子留空反而对不上账），而底座
# `summary()` 的留空判据也只有两条（去年同月为 0、两期异号），不含近零基数。
# 但「不矛盾」不等于「读者读得到」：那条解释在页尾第 14 条，而 −100.0% 在页面顶部。
#
# 本轮的处置是**把警告搬到读数旁边**：给命中列的 `zh` 加一个 †。
# 为什么只能这么做 —— 让汇总表真的印「—」要改 build/single.py 的 `summary()`
# （单元格在那里算完，`COL_KEYS` 里没有任何逐列开关），底座不在本轮允许修改的范围。
# `zh` 是 spec 侧够得到的、离那一格最近的字符串，而且它会同时出现在汇总表行标签、
# 该列所在图的序列名与末尾核对表表头上 —— 三处同一个标记，只解释一次。
# 命中列由 CSV 现算，不写死：某列不再近零基数，†自己就掉了。
NEAR_ZERO_MARK = '†'


def _mark_near_zero():
    if not _NEAR_ZERO:
        return
    hit = set(_NEAR_ZERO)
    for c in HEADLINE + [c for g in GROUPS for c in g['cols']]:
        if c['col'] in hit and not c['zh'].endswith(NEAR_ZERO_MARK):
            c['zh'] += NEAR_ZERO_MARK


_mark_near_zero()


# ── 币种构成：从各列自己声明的 unit 串现算，不写死 ────────────────────────────
# 为什么必须现算：这几个数会同时进副标题、进第 1 条 notes、进币种那一条 note。
# 写死的话，以后加一列美元指标、副标题却还印着旧的列数，
# 而**没有任何自动判据查得出来**（payload_guard 只看 NaN，verify_pages 只看结构）。
def _ccy_counts():
    n = {'GBP': 0, 'USD': 0, 'EUR': 0, 'none': 0}
    seen = set()
    for c in HEADLINE + [x for g in GROUPS for x in g['cols']]:
        if c['col'] in seen:
            continue
        seen.add(c['col'])
        u = c['unit']
        # `EUR per GBP` 是**汇率**不是金额，必须先挑出去 —— 它以 'EUR' 开头，
        # 漏了这一句就会被数进欧元列，欧元变 5 列、无币种变 35 列，两个数同时错。
        if u == 'EUR per GBP' or ' per ' in u:
            n['none'] += 1
        elif u.startswith('GBP'):
            n['GBP'] += 1
        elif u.startswith('USD'):
            n['USD'] += 1
        elif u.startswith('EUR'):
            n['EUR'] += 1
        else:
            n['none'] += 1                # 笔数 / 家数 / 交易日 / 成交份额
    return n


_CCY = _ccy_counts()

# 这个字符串会被底座原样印进**副标题**与第 1 条 notes（模板是「本币 {ccy}」）。
# 原先这里写 'GBP'，于是页面抬头印「本币 GBP」，紧挨着的头条数据条却印
# 「67.5 USD tn/month」「2,928 USD bn/day」—— 读者第一眼看到的就是一处自相矛盾，
# 而且第 1 条 notes 还跟着写死「本页只按本币标注」。
# 本页根本不是单币种页：金额列分属三种货币，各图按自己那一列的原币标注、不做换算。
# 所以 `ccy` 这个字段必须说的是**这一页的实情**，不是集团财报的记账本币。
CCY_MIX = ('三币种混合：英镑 %d 列 / 美元 %d 列 / 欧元 %d 列，'
           '另 %d 列无币种，每张图按自己那一列的原币标注'
           % (_CCY['GBP'], _CCY['USD'], _CCY['EUR'], _CCY['none']))


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数一个都不写死，全部从 series/lseg.csv 现算。
# ══════════════════════════════════════════════════════════════════════════════
_NOTE_LEGS = (
    '<b>四条腿、四种发布节奏。</b>本页 86 个数据列来自四个互不相干的官方源：'
    + (_span_txt() or '订单簿 / 一级市场 / Tradeweb / LCH 四路')
    + '。实测发布节奏（各 fetch/lseg_*.py 的逐期统计）：Tradeweb 数据月月末后第 2–8 天'
      '（2021 年起 65 期，中位第 5 天）、LCH 第 3–4 天、Main Market / AIM 第 1–9 天、'
      '<b>LSE 订单簿近两年中位第 21 天</b>。所以每个月都有两三周的时间，'
      'Tradeweb 那 27 列已经是最新月而其余 59 列还空着 —— 那是发布进度，不是抓取故障。'
)

def _headline_case():
    """头条那三条判据的**现算**说法。读不到就退回不含数字的定性版本。

    原先这句话把「115 个月（其余三腿 97/66/24）、唯一零空格」写死在字面上。
    两次回补之后（orderbook 补到 2016-01、AIM 补到 2017-01）三个数字全错、
    「唯一」也不成立了 —— 图注于是在页面上撒了两句谎。判据本身没变，变的只是数字，
    所以数字改成现算。
    """
    if not _ROWS or any(_SPAN[lg][1] is None for lg in _LEGS):
        return ('历史最长的不再是它、零空格的也不止它一组，但它是唯一进得了'
                '「次月一周内」的腿 —— 头条靠的是这一条。')
    rank = sorted(_LEGS, key=lambda lg: -_SPAN[lg][3])
    longest = rank[0]
    zero = [lg for lg in _LEGS if _leg_blanks(lg) == 0]
    n_tw = _SPAN['tradeweb'][3]
    bits = ['<code>tradeweb</code> 那 27 列有 %d 个月的连续历史' % n_tw]
    if longest != 'tradeweb':
        bits.append('但**不是最长的** —— <code>%s</code> 有 %d 个月'
                    % (longest, _SPAN[longest][3]))
    if len(zero) > 1:
        bits.append('零空格的也不止它一组（%s 都是）'
                    % '、'.join('<code>%s</code>' % z for z in zero))
    bits.append('它真正独占的是第三条：<b>唯一</b>进得了「次月一周内」的腿'
                '（其余三腿分别 %s）'
                % '、'.join('<code>%s</code> %s'
                            % (lg, {'orderbook': '中位次月第 21 天',
                                    'primary': '次月第 1–9 天',
                                    'lch': '次月第 3–4 天但官方月表本身滞后约两个月'}[lg])
                            for lg in ('orderbook', 'primary', 'lch')))
    return '；'.join(bits).replace('**', '') + '。'


_NOTE_HEADLINE = (
    '<b>头条为什么是 Tradeweb 而不是伦敦交易所自己的订单簿。</b>'
    '选头条的三条判据是「历史长 / 发布快 / 无空洞」，而 Tradeweb <b>只占决定性的那一条</b>：'
    + _headline_case() +
    '反过来看代价：'
    '若拿 LSE 订单簿做头条，本页今天的数据月立刻退回上一个月，'
    '且按 docs/CRON_WIRING §2.1「LAG 跟着决定 data_through 的那条腿走」，'
    'build/roster.py 的 <code>LAG[\'lseg\'] = (8, 8)</code> 要抬到 (26, 26)，'
    '整页每月晚 18 天上线。<b>⚠️ 读这一行数据条时请记住：它是 LSEG 并表子公司 '
    'Tradeweb 的成交量，不是 LSEG 集团口径</b>；而且成交量与该分部收入之间还隔着一个'
    '本仓拿不到的 FPM（每百万美元费率），量涨不等于收入等比例涨。'
)

_NOTE_CCY = (
    '<b>⚠️ 先读这一条：本页不是单币种页，三种货币同表并存，每张图各自标注。</b>'
    '按各列自己声明的单位现点，86 个数据列里<b>英镑 %d 列</b>'
    '（LSE 订单簿与一级市场）、<b>美元 %d 列</b>'
    '（Tradeweb 与 LCH 的 SwapClear / ForexClear）、<b>欧元 %d 列</b>'
    '（LCH RepoClear），其余 %d 列没有币种（笔数 / 家数 / 交易日 / 成交份额，'
    '外加 1 列 GBP/EUR 换算率）。'
    '<b>所以页面抬头那行数据条印的是美元</b>（头条走 Tradeweb 那条腿，'
    '单位 USD tn/month 与 USD bn/day），而同一张页上 LSE 订单簿那几张图印英镑、'
    'RepoClear 那两张印欧元 —— 这不是标错，是本页刻意不做换算的结果：'
    '跨币种的数字<b>不可加总、不可同轴、不可互比高低</b>，'
    '看任何一张图之前先看它自己的纵轴标题。'
    '本页<b>不做任何汇率换算</b> —— 拿 series/fx.csv 折一道，'
    '就把 [A] 级的官方原始披露变成派生的 [C] 级数字，而图上看不出来。'
    '两条最容易踩的：① <code>_gbp_m</code>（订单簿）与 <code>_gbp_mn</code>（一级市场）'
    '<b>是同一个单位（英镑百万）</b>，只是两条抓取腿的命名习惯不同，'
    '不要以为差 1000 倍去做二次缩放；② 底座按 <code>unit</code> 字符串自动分桶，'
    '所以本文件里每个单位串都照实写，没有为了少画一张图而把两种币种并成同一个 unit。'
    % (_CCY['GBP'], _CCY['USD'], _CCY['EUR'], _CCY['none'])
)

_NOTE_ORDERBOOK = (
    '<b>LSE 订单簿这一组的三件事。</b>① 起点 2021-01 是取数腿的<b>主动取舍</b>不是抓漏：'
    '2020-12 及以前的月报多印 Italian / Derivatives / MTS / EuroTLX 行，'
    '且 "LSE Lit Orderbook trading in UK" 这个份额标签 2021-01 才出现，'
    '要把更早的历史接上得先解决旧标签对齐。② <b>Turquoise Dark 这一列的行名换过两次</b>'
    '（MidPoint → Plato™ → Dark），取数腿逐期核对确认是<b>同一条腿改名</b>，'
    '不是口径变化，所以不画断点线。③ 两条份额的<b>分母不是同一个盘子</b>：'
    'LSE 那条是「英国 Lit 订单簿」，Turquoise 那条是「泛欧 Lit + Dark」，'
    '两个百分数不能相加也不能互比高低，本页刻意用两个不同的单位串把它们分成两张图。'
)

def _primary_span_txt():
    """一级市场两段列各自的起点与空洞 —— 现算，别写死。

    这一段的字面值 2026-08-19 之前是错的：图注写「起点 2018-05、2019-09 与 2022-12
    两个月整行为空」，而那两个「洞」其实各自只砸一个市场，取数腿按月整行跳过时
    把另一个市场好好的数一起丢了。现在两段列各写各的，说法也得跟着数据现算。
    """
    a_first, a_last, a_n, a_hole = _col_span('aim_companies_eop_count')
    m_first, m_last, m_n, m_hole = _col_span('mm_companies_eop_count')
    if a_first is None or m_first is None:
        return ('AIM 与 Main Market 两段列的起点不同，左端的空白是官方归档深度，'
                '不是抓漏。')
    # 起点差几个月同样现算 —— 2026-08-19 把 AIM 从 2017-01 推到 2016-01 之后，
    # 原先写死的「16 个月」当场变成假话（真值 28）。
    gap = ((int(m_first[:4]) - int(a_first[:4])) * 12
           + int(m_first[5:7]) - int(a_first[5:7]))
    return ('<b>AIM 那 11 列与 Main Market 那 13 列起点差 %d 个月</b>：'
            'AIM %s 起（%d 个月有值），Main Market %s 起（%d 个月有值）—— '
            'AIM 的左端已经吃到<b>老版式与 .xls</b>（见 ③），'
            'Main Market 停在 %s 是<b>口径限制</b>而不是格式限制。'
            '各自跨度里还各有一个<b>官方自己的洞</b>：AIM 缺 %s（那一期年度块的 '
            'Market Value 格 LSEG 留白了，文件与家数都在），'
            'Main Market 缺 %s（那一期在官方索引里根本不存在，2022 年组只到 11 月）。'
            '<b>两个洞各自只砸一个市场</b>，另一个市场那个月照常有数 —— '
            '所以这两个月不是整行空白，看图时别把某一条线的断点读成两个市场一起停摆。'
            % (gap, a_first, a_n, m_first, m_n, m_first,
               '/'.join(a_hole) or '（无）', '/'.join(m_hole) or '（无）'))


_NOTE_PRIMARY = (
    '<b>一级市场这一组的四件事。</b>① 官方口径的 "New Issues" <b>不等于 IPO</b>：'
    '它含转板、introduction 与反向收购，所以家数会高于财经媒体口径的 IPO 数。'
    '② ' + _primary_span_txt() +
    '③ <b>AIM 的左端是啃完老版式换来的，Main Market 的左端是口径挡住的 —— '
    '两段列停在不同的地方，原因也完全不同。</b>'
    'AIM 2016-12 及更早那 12 期用的是另一套表头（写 "Number of Admissions" 而不是 '
    '"New Issues"、写 "Delistings" 而不是 "Cancellations"、标题格是日期序列值、'
    '月度块没有 Sum 行），2016-10 及更早还是 .xls；这些都已经解掉，'
    '接缝处用「上市家数 = 上月家数 + 新上市 − 退市」这条恒等式逐月验过，'
    '2016-01 到 2017-06 连续 18 个月零违例，跨版式那一步（2016-12 → 2017-01）也在内。'
    '<b>Main Market 反过来：格式不是问题（官方 .xls 一直回到 2009-01），口径才是。</b>'
    '老版式 Summary 里「上市公司家数」写 987（Trading 971 + Suspended 16），'
    '而与现行序列接得上的是另一张表 T8 的 946 —— 取错那个会在接缝上造出 −4.4% 的假台阶；'
    '更硬的是<b>国际板那两列根本没有对应来源</b>（老版式给 268 家 / £1,795bn，'
    '现行口径是 221 家 / £1,472bn，差 18%，官方没给桥），'
    '连带「合计家数」「合计市值」也接不上；增发笔数则是另一套数法'
    '（2018 年 1–4 月老版式 24/30/45/86，现行 51/54/71/103）。'
    '13 列里 4 列无源、1 列口径不同，硬拼等于在图上画一条假的历史 —— '
    '所以 Main Market <b>就停在这里</b>，宁可左上角空一片。'
    '④ <b>官方同一份文件里有自相矛盾的格子</b>：Summary 表与 Further Issues 明细表'
    '在少数月份对不上（本机 <code>cache/lseg_primary_conflicts.csv</code> 记了 3 处，'
    '最近一次是 2026-05 的主板增发募资，明细表比 Summary 高 16.4%）。'
    '本页一律取<b>明细表</b>那一侧，冲突留痕不自动吞 —— 两个数都是官方印的，'
    '光看文件判不出谁对，所以拿这一页去对 Summary 表时会有差。'
)

_NOTE_LCH = (
    '<b>LCH 的短历史是官方滚动窗口，不是起点设窄。</b>'
    'ForexClear 的月度 CSV 末行原文写着 <code>Row Count: 24</code>；'
    'SwapClear 的两张 datatable 各只有 12 行；RepoClear 的三张月度 grid 各 12 行 —— '
    '而同一页的<b>年度</b> grid 有 28 行、回溯到 1999，说明官方有更深的历史，'
    '但只以年度形式公开。后果比「只有两年」更硬：<b>12 期连 13 期的点对点同比都算不出</b>，'
    '24 期的滚动同比也只有一个点、连不成线。所以 LCH 的 18 列本轮一律只读水平值；'
    '再跑满一年，SwapClear 与 RepoClear 才自然长到 24 期。'
    '另有两条口径：ForexClear 的量是<b>双边计</b>（CSV 末行自述含每笔的两条腿）；'
    'RepoClear 的 <b>LCH Ltd（伦敦）与 LCH SA（巴黎）在月度口径上没有官方合计</b>'
    '（官方只在年度表里印 Total），自己加出来的月度合计是派生值、本仓不收，'
    '所以这两个法人在本页从头到尾分组分图，页面上不会出现一条合计线。'
)

_NOTE_NEITHER = (
    '<b>有 6 列既不是流量也不是存量。</b>LSE / Turquoise / Tradeweb 三列交易日数、'
    '两列成交份额、一列 GBP/EUR 换算率 —— 底座只有「流量 / 存量」两分法，'
    '它们按缺省落在流量侧，所以上面那条「存量与流量分开读」的说明不适用于它们，'
    '<b>更不要把它们跨月相加</b>。收 GBP/EUR 换算率不是为了看汇率，'
    '是因为月报每行印的是 [笔数, £m, €m] 三个数、而 €m 栏 = £m 栏 × 这一列，'
    '留着它读者才能验证 Turquoise 那几列取的是英镑那一栏。'
    'Tradeweb 的加权交易日数是「月成交额 ÷ 月 ADV」反推出来的<b>集团级加权天数</b>'
    '（不是整数、不是日历事实），与 LSE / Turquoise 的整数交易日<b>不可同轴比较</b>，'
    '本页用不同的单位串把它们隔在两张图里。'
)

_NOTE_NO_DECOMP_TRADEWEB = (
    '<b>为什么不把成交额与 ADV 绑成量价恒等式。</b>本页的 <code>decomp</code> 与 '
    '<code>ttm_yoy</code> 都<b>只用当月合计口径的列本身</b>，一个 '
    '<code>weight_col</code> / <code>total_col</code> 都不给。理由是机器判据不是偏好：'
    '底座在两者同时给出时会逐月对账，相对偏差超过 <code>1e-6</code> 就整页硬失败，'
    '而本页两条腿的实测残差是 Tradeweb「ADV × 加权天数 vs 月成交额」约 2.5e-4、'
    'LSE 订单簿「ADV × 交易日 vs 月合计」约 9.1e-4 —— 都远超阈值。'
    '根子在官方自己：£m 四舍五入到整数、加权天数只印到两位小数。'
    '所以 Tradeweb 的月成交额与 ADV 在本页是<b>两条并列的头条序列</b>，'
    '不是一对量价因子；读者也不要拿其中一条乘除另一条去对账。'
)

_NOTE_TRADEWEB_CALIBER = (
    '<b>Tradeweb 那一组的四条口径。</b>① 列名里的 "Rates / Credit / Equities / '
    'Money Markets" 是<b>资产类别名</b>，不是「费率」——'
    '把 <code>tradeweb_adv_rates_*</code> 当比率读会差一个数量级。'
    '② 非美元品种按<b>上一个月的月均汇率</b>折成美元，所以欧洲那几列的同比里'
    '含一个月的汇率滞后。③ <code>other_money_markets</code>（含 ICD Portal）的'
    '分母是<b>自然日</b>而不是交易日，与同图其余 ADV 列不同源。'
    '④ 官方会事后重述：2024-12 起美国国债的分母口径变过一次（2024-01 那一格被改了 '
    '+11.5%），但官方<b>已回溯改写历史</b>，本页历史段自洽 —— 正因为如此这里不画断点线：'
    '红色竖线的语义是「线左右不可比」，而这次重述恰恰让左右可比了。'
)

_NOTE_BREAKS = (
    '<b>本页不设口径断点线。</b><code>series/lseg_breaks.csv</code> 不存在，'
    '<code>breaks</code> 留空。已知的三处变化都不适合画成全页红线：'
    'Turquoise 暗池行名 MidPoint → Plato™ → Dark 是同一条腿改名（不是口径变化）；'
    'Tradeweb 2024-12 的分母重述已被官方回溯改写（画线反而暗示不可比）；'
    'LSE 订单簿起点 2021-01 是「更早的没取」而不是「更早的不可比」。'
    '红色竖线会画在<b>全页</b>每一张横轴是月份的图上，'
    '为一列的变化去误伤其余八十多列不划算，所以这三条写在这里而不画线。'
)

_NOTE_SOURCE_DATE = (
    '<b>页面抬头没有「官方发布于」那半句，这是已知缺口不是遗漏。</b>'
    '<code>series/source_dates.csv</code> 里没有 lseg 的行：四条腿里只有 Tradeweb 有'
    '现成的公开接口能给出发布日，订单簿与一级市场只能逐月回算、LCH 只有当前快照，'
    '而「四者取最晚」是一个说不清含义的日期。按 CONTRACT §1，宁可缺席也不写一个'
    '自己都解释不了的日子。取数腿留了 <code>release_dates()</code>，'
    '等 data_through 的政策定下来可以一次接上。'
)


def _col_meta():
    m = {}
    for g in GROUPS:
        for c in g['cols']:
            m[c['col']] = c
    for c in HEADLINE:
        m.setdefault(c['col'], c)
    return m


_META = _col_meta()


def _data_through():
    """本页的数据月 = 最后一个**所有头条列都有值**的月份（同底座 resolve_through 的判据）。"""
    head = [c['col'] for c in HEADLINE]
    for r in reversed(_ROWS):
        if all(_num(r, c) is not None for c in head):
            return r['month']
    return None


_THROUGH = _data_through()


def _row_at(month):
    if not month:
        return None
    return next((r for r in _ROWS if r.get('month') == month), None)


def _summary_yy(col, month):
    """复刻 build/single.py `summary()` 里 y/y 单元格的判据 → (y/y%, 本月, 去年同月)。

    底座那一格的规则只有两条：去年同月为 0、或两期异号 → 留空；否则照印
    (本月 ÷ 去年同月 − 1)。**「近零基数」不在它的判据里** —— 这正是本条页注要交代的事。
    这里不去改底座，只把它的实际行为现算出来写进页注，免得页注与表自相矛盾。
    """
    if not month:
        return None
    try:
        yago = '%04d-%02d' % (int(month[:4]) - 1, int(month[5:7]))
    except ValueError:
        return None
    ra, rb = _row_at(month), _row_at(yago)
    a = _num(ra, col) if ra else None
    b = _num(rb, col) if rb else None
    if a is None or b is None or b == 0 or a * b < 0:
        return None
    return ((a / b - 1) * 100, a, b)


def _esc(s):
    """列名进页注前转义。

    `notes` 走 innerHTML，而本页有一列的中文名里带尖括号
    （<code>Tradeweb 互换/掉期期权 &lt;1Y ADV</code>）。浏览器对 `&lt;1` 这种
    「尖括号后面不是字母」的情形会当普通字符处理，所以今天没出事 —— 但那是靠
    解析器的容错，不是靠我们写对。列名是数据派生的，下一列叫什么我们说了不算。
    """
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def _fmt_like(v, fmt):
    """按该列自己的 `fmt` 把数字排版 —— 页注里报的绝对值必须与汇总表印的<b>逐字一致</b>。

    直接 `%g` 会印出 4.86696，而汇总表按 f1 印的是 4.9，读者会以为两处是两个数。
    这里只覆盖本文件实际用到的几个 fmt，其余退回 %g。
    """
    try:
        if fmt in ('f0', 'int'):
            return '%d' % round(v)
        if fmt == 'f0c':
            return '{:,.0f}'.format(v)
        if fmt in ('f1', 'pct1', 'pp1'):
            return '%.1f' % v
        if fmt in ('f2', 'usd2'):
            return '%.2f' % v
        if fmt == 'f3':
            return '%.3f' % v
    except Exception:
        pass
    return '%g' % v


def _near_zero_note():
    if _NEAR_ZERO is None:
        return ('<b>行名带 † 的是近零基数列：图上不画同比，汇总表的 y/y 列照印。</b>'
                '（本次构建读不到 series/lseg.csv 或 build/yoy.py，命中列表算不出来，'
                '所以这一版没有 † 标记，也报不出具体列名。）'
                '一级市场的新上市家数与募资额有大量取 0 的月份，同比读的已经不是量在变'
                '而是分母在变，所以图上只画水平值；而汇总表的 m/m 与 y/y 两列按 '
                'CONTRACT §6.2 是<b>豁免</b>的（那是运营核对表，读者拿它逐格对公司披露），'
                '底座不会替这些列把格子压空 —— 读那几行的 y/y 之前先看绝对值。')
    names = '、'.join(_esc(_META.get(c, {}).get('zh', c)) for c in _NEAR_ZERO)
    bad, ok = [], []          # 本月基期近零的 / 本月基期正常的（都指汇总表 y/y 那一格）
    for c in _NEAR_ZERO:
        got = _summary_yy(c, _THROUGH)
        if got is None:
            continue
        y, a, b = got
        m = _META.get(c, {})
        nz = _near_zero_now(c)
        # 与底座 summary() 的印法对齐：正好是 0 的那一格不带正负号（那里做的是
        # `txt.lstrip('+-')`）。差一个加号，读者就会以为页注与表里是两个数。
        ytxt = '%+.1f%%' % y
        if ytxt.lstrip('+-') in ('0.0%', '0%'):
            ytxt = ytxt.lstrip('+-')
        item = ('<b>%s %s</b>（本月 %s、去年同月 %s %s）'
                % (_esc(m.get('zh', c)), ytxt,
                   _fmt_like(a, m.get('fmt', '')),
                   _fmt_like(b, m.get('fmt', '')), m.get('unit', '')))
        (bad if (nz and nz['now']) else ok).append((abs(y), item))
    bad.sort(reverse=True)
    ok.sort(reverse=True)
    n_print = len(bad) + len(ok)
    return (
        '<b>行名带 %s 的列：<u>图上</u>不画同比（CONTRACT §6.1 第 6 条），'
        '<u>汇总表</u>的 y/y 列照印（CONTRACT §6.2 豁免）—— 两套口径，不是打架，'
        '但两处必须分开读。</b>' % NEAR_ZERO_MARK
        + '<b>%s 出现在三个地方</b>：汇总表（Exhibit 1）的行标签、该列所在图的序列名、'
        '末尾核对表的表头 —— 同一个标记，只解释这一次。'
        '标记由 CSV 现算不写死：某列不再近零基数，%s 自己就掉了。' % (NEAR_ZERO_MARK,
                                                                    NEAR_ZERO_MARK)
        + '判据与实现都在 <code>build/yoy.py</code> 的 <code>near_zero_base()</code>：'
        '基期绝对值小于本序列|值|中位数 15% 的月份算「近零基数月」，'
        '<b>在图上画出来的那 25 个月里</b>占比 ≥ 1/12 → 整条序列别画同比。'
        '（窗口这一步很要紧：拿全历史计数会让一条 2018 年近零、现在早已正常的序列'
        '永远背着这个标签 —— 本页上一版正是漏了它，把三条 Tradeweb 列错标成近零基数。）'
        '本页 import 期实测命中 <b>' + str(len(_NEAR_ZERO)) + '</b> 条：'
        + (names or '（无）') + '。'
        '<b>图上怎么落实</b>：靠<b>排版</b>而不是开关 —— 把它们放进 2–5 列同单位的组，'
        '底座对多列桶画的是折线（只有水平值、没有次轴同比），'
        '于是那条会跳到几百个百分点的金线根本不会被画出来。'
        '<b>汇总表（Exhibit 1）为什么不跟着压空</b>：CONTRACT §6.2 把「汇总表的 m/m '
        '与 y/y 两列」明确列为豁免 —— 那两列不是趋势判断，是运营核对表，'
        '读者拿它逐格对公司披露，把格子留空反而对不上账；'
        '底座 <code>summary()</code> 的留空判据也只有两条'
        '（去年同月为 0、或两期异号），<b>不含近零基数</b>。'
        '⚠️ 想让汇总表真的印「—」得改 <code>build/single.py</code> 的 '
        '<code>summary()</code>（单元格在那里算完，逐列开关在 <code>COL_KEYS</code> 里'
        '没有位置），<b>本轮没有改底座</b>，所以这里能做的只有把警告搬到读数旁边。'
        + ('本月这 %d 条%s在汇总表 y/y 列印出了读数，'
           '<b>但这 %d 格不是同一回事，必须分开看</b>：'
           % (len(_NEAR_ZERO),
              '全部' if n_print == len(_NEAR_ZERO) else '里有 %d 条' % n_print, n_print)
           if n_print else
           '本月这几条在汇总表 y/y 列全部为空（去年同月为 0 或两期异号），无需额外提防。')
        + ('<b>⚠️ 基期本身就落在近零区、这一格<u>不能</u>照读的有 %d 条</b>：%s。'
           '这种读数是<b>分母的故事</b>不是量的故事，一律回到「本月 / 上月 / 去年同月」'
           '三列的绝对值上判断，别与页上其余同比比高低。'
           % (len(bad), '；'.join(t for _, t in bad)) if bad else '')
        + ('<b>另外 %d 条本月的基期<u>没有</u>触发近零判据</b>'
           '（|去年同月| ≥ 本序列|值|中位数 × 0.15），那几格的百分比不是分母造成的：%s。'
           '带 %s 说的是「<b>这条序列</b>不适合画同比线」，不是「<b>这一格</b>一定不能看」。'
           '⚠️ 判据没触发也不等于这个百分比有多少信息量：家数是按「家」计的小整数，'
           '一家之差就是几十个百分点 —— 读它们仍以三列绝对值为准。'
           % (len(ok), '；'.join(t for _, t in ok), NEAR_ZERO_MARK) if ok else '')
        + '它们仍然逐月留在末尾核对表里。'
    )


_NOTE_DECOMP = (
    '本图的两列取自<b>同一份 PDF 的同一行</b>：LSE 月报 MTD 区块每一行印的是 '
    '[笔数, £m, €m] 三个数，成交额取第二个、笔数取第一个，'
    '所以分子分母覆盖的是完全相同的一批成交，不存在「金额取自 A 表、笔数取自 B 表」'
    '那种口径错配。<b>⚠️ 但有一件事官方没有言明</b>：月报没有说 "Trades" 是单边计'
    '还是买卖双边计。若是双边计，图注里报出来的每笔平均成交额<b>应当减半</b>；'
    '而<b>分解结果一个数都不会变</b> —— 常数因子在 ln(P₁/P₀) 里与自己抵消。'
    '所以这张图的<b>归因（量的贡献 vs 单笔大小的贡献）可以直接读，'
    '绝对水平请以官方口径为准</b>。派生量本身是本仓自算的 [C] 级数字，'
    '不是官方披露的 [A] 级数字。另外这两列都是慢腿，'
    '所以最新的那根 YTD 柱覆盖到的月份会比本页数据月早两三周。'
    '<b>关于上面那句「本币在分子分母上同时出现」</b>：本页的「本币」是三币种混合'
    '（见页首币种那一条），但<b>这张图的两列都是英镑</b>'
    '（<code>lse_orderbook_value_gbp_m</code> 与同一行的笔数），'
    '所以那句话在这张图上说的就是 GBP —— 换成任何货币、任何换汇口径，'
    '两块的高度与菱形的位置一个都不会变。'
)

_NOTE_TTM_TRADEWEB = (
    '<b>柱与线取自同一列同一口径</b>，所以这张图不受口径坑 B（ADV 与月合计对不上）'
    '的影响：<code>tradeweb_volume_total_usd_tn</code> 本身就是官方工作簿里的'
    '当月合计，没有任何「日均还原成合计」的步骤。'
    '这也是本页唯一按 CONTRACT §6.1 第 1 条「流量默认滚动同比」画的头条图 ——'
    'Exhibit 4 / 5 的头条同比是单月口径（运营核对用），两者并存是分工不是疏忽。'
)

_NOTE_TTM_ORDERBOOK = (
    '<b>柱与线取自同一列同一口径</b>：<code>lse_orderbook_value_gbp_m</code> 是月报 '
    'MTD 区块的当月合计，不是日均，所以这里没有乘回交易日数这一步'
    '（乘回去会撞上口径坑 B：官方把 £m 四舍五入到整数，'
    '「ADV × 交易日 vs 月合计」的残差约 9.1e-4，远超底座 1e-6 的对账阈值）。'
    '⚠️ 这是<b>慢腿</b>：它的最新月比本页数据月早两三周，图的右端因此比头条那几张短一截。'
)

_NOTE_TTM_OTHER_GOVT = (
    '<b>这张是「其他政府债 ADV」<u>唯一</u>的同比图，口径是 CONTRACT §6.1 第 1 条的默认。</b>'
    '本列有 ' + str(_n_obs('tradeweb_adv_other_govt_bonds_usd_bn')
                    or '（读不到 CSV，期数未知）') + ' 期，'
    '滚动同比完全算得出来。上一轮它同时还有一张单列柱图、次轴画单月同比'
    '（底座对单列桶写死画单月，spec 侧改不了），而那张图给不出第 2 条允许的口径理由；'
    '本轮把该列并进「欧洲国债与其他政府债」那一组（同单位，'
    + _scale_gap_txt('tradeweb_adv_eu_govt_bonds_usd_bn',
                     'tradeweb_adv_other_govt_bonds_usd_bn') +
    '），底座改画折线，那条辩护不了的单月同比线<b>已经从页面上消失</b>，只剩这一张。'
    '⚠️ 本列是<b>日均</b>（ADV），而本页没有这个口径的交易日权重列，'
    '所以滚动合计是把 12 个日均<b>等权</b>相加。这不是将就：CONTRACT §6.3 明写'
    '「日均序列不要乘回交易日」—— 同比是比值，分子分母同权，交易日在比值里直接约掉，'
    '乘回去只多引进一条序列的误差；何况 Tradeweb 那列加权天数是<b>集团级</b>的，'
    '不是这一个分项自己的天数，拿它去还原本列会引进一个方向未知的偏差。'
)


# ── 三条「底座生成、spec 改不到」的抵消说明 ────────────────────────────────
# 这三条讲的都是同一类事：页面上某句话由 build/single.py 拼装，本轮不允许改底座，
# 于是只能在这里把它更正过来。写法上一律**指名道姓说清楚是哪一句、为什么改不到**，
# 而不是含糊地补一句「以本条为准」—— 读者要能自己判断该信哪一句。
def _slow_split():
    """慢腿列在本页数据月的实况：(有值列数, 留空列数, 按腿分的留空明细)。"""
    row = _row_at(_THROUGH)
    if row is None or not SLOW_COLS:
        return None
    have = [c for c in SLOW_COLS if _num(row, c) is not None]
    blank = [c for c in SLOW_COLS if _num(row, c) is None]
    by_leg = {}
    for c in blank:
        by_leg.setdefault(COLUMN_LEG.get(c) or '未知腿', []).append(c)
    det = '、'.join('<code>%s</code> %d 列' % (lg, len(v))
                    for lg, v in sorted(by_leg.items(), key=lambda kv: -len(kv[1])))
    return len(have), len(blank), det


def _slow_truth_note():
    got = _slow_split()
    head = ('<b>⚠️ 上面那条慢腿说明里的「最新月留空显示 —」是底座对 <code>slow_cols</code> '
            '一概而论的模板句，本页实际不是这样。</b>')
    if got is None:
        return (head + 'slow_cols 的准确含义是<b>不参与本页数据月的门槛判定</b>，'
                       '不是「一定留空」—— 四条腿的发布节奏差一个数量级，'
                       '每个月「哪几列还空着」都不一样。'
                       '<b>那句模板出自 build/single.py，不在本轮允许修改的范围，'
                       '所以只能在这里抵消。</b>')
    have, blank, det = got
    return (
        head +
        '本页数据月 <b>%s</b> 的实况是：%d 列慢腿里 <b>%d 列已经有值</b>、'
        '只有 <b>%d 列</b>真的留空（%s）。'
        'slow_cols 的准确含义是<b>不参与本页数据月的门槛判定</b>，不是「一定留空」——'
        '四条腿的发布节奏差一个数量级（Tradeweb 次月第 2–8 天，LSE 订单簿中位第 21 天），'
        '所以每个月「哪几列还空着」都不一样，上面这两个数每次构建都会变。'
        '<b>那句模板出自 build/single.py，不在本轮允许修改的范围，'
        '所以只能在这里抵消 —— 以本条为准。</b>'
        '慢腿清单本身不手抄：优先从 <code>fetch/lseg.py</code> 的模块常量 '
        '<code>COLUMN_LEG</code> 派生，读不到就回落到 '
        '<code>series/lseg_part_*.csv</code> 的表头，两者都读不到才用本文件的前缀兜底。'
        '把慢腿列放进门槛，整页会被最慢的那条腿（LSE 订单簿，中位第 21 天）'
        '拖住两三个星期，而且不会报错 —— 抓取本身是「成功」的。'
        % (_THROUGH or '（未知）', len(SLOW_COLS), have, blank, det)
    )


# ── 最后一根柱的数值贴着右轴刻度：现算，且明说本轮为什么不修 ────────────────
# 这条与 _NOTE_AXIS_SCALE 是同一类东西（几何缺口，spec 侧修不了），所以挨着放。
#
# 症状：三张**单列**柱图（gs_bar）的最后一根柱，柱顶数值标签的右半边伸进右轴刻度
# 那一列，与恰好同高的那根刻度叠在一起。
# 成因（照 assets/charts.js 复算，2026-08-19 用 tools/visual_qa.py 的墨迹口径实测过）：
#   柱顶标签居中钉在 Xc(n−1) = M.l + pw − band/2，右轴刻度画在 M.l + pw + fscale(6)，
#   ⇒ 标签总宽的预算 = 2 × (fscale(6) + band/2)。
#   窗口从 25 期拉到 2016-01（127 期）之后 band 掉了五分之四：
#   1280px 通栏 band 7.33px ⇒ 预算 27.7px；768px 单栏 band 4.46px ⇒ 预算 22.8px。
#   而本月三个末值实测宽 34.4 / 30.4 / 30.4px（字号 12.15–13.6px，引擎的 FS 随卡片宽
#   放大字号但 band 不跟着长），故各越界 5.8 / 3.8 / 3.8px（768px 口径）。
# 为什么不砍一位小数（spec 侧唯一能让标签变窄的杠杆）——**两条独立的理由**：
#   ① 砍完仍然压。实测（把 payload 的 fmt 临时换成 pct0 / f2 / f1 再量）：
#      768px 下「66%」「1.17」「23.1」仍分别越界 0.80 / 0.40 / 0.40px，
#      只是重叠面积掉到 visual_qa 的 8px² 门限以下 —— 那是把告警藏起来，不是把字分开。
#   ② 小数位是列的 `fmt`，会连**末尾核对表**一起砍，而这三列的 fmt 恰好就是
#      源表自己的精度：series/lseg.csv 里份额存 1 位（65.9）、加权天数存 2 位（23.06），
#      砍了核对表就再也对不上官方披露那一格。换算率源表存 4 位、页面已经按 f3 收到
#      3 位，再砍是第二次丢精度。
# 真正的修法在共用引擎：charts.js 已经为「次轴末点读数 vs 右轴刻度」写了一段
# 「刻度让位」（:1810 起，撞上就把那根刻度删掉），只是没把柱顶数值标签也算进
# priorityLabs。本轮不改共用件，所以这条缺口留在页面上，写出来免得读者当成渲染出错。
def _last_bar_label_note():
    trio = (('lse_lit_uk_share_pct', 'pct1', 'LSE 英国 Lit 订单簿份额'),
            ('gbp_eur_rate', 'f3', '月报自印 GBP/EUR 换算率'),
            ('tradeweb_trading_days_blended', 'f2', 'Tradeweb 加权交易日数'))
    head = ('<b>三张单列柱图最后一根柱的柱顶数值，与右轴刻度贴在一起。'
            '这不是渲染出错，也不是两个数粘成了一个 —— 左边那个是这根柱的值，'
            '右边那个是右轴的刻度，两个都是对的。</b>')
    bits = []
    for col, fmt, zh in trio:
        s = _series(col)
        if s is None:
            continue
        s = s.dropna()
        if s.empty:
            continue
        v = _fmt_like(float(s.iloc[-1]), fmt) + ('%' if fmt.startswith('pct') else '')
        bits.append(f'{_esc(zh)}（{s.index[-1]} 的「{v}」）')
    who = ('涉及' + '、'.join(bits) + '三张。') if len(bits) == 3 else ''
    return (head + who +
            '成因是几何：柱顶数值居中钉在自己那根柱上，最后一根柱的柱心离绘图区右缘'
            '只有半格宽，而右轴刻度就画在右缘外侧一点点。本页窗口从最近 25 期拉到 '
            '2016-01 起之后，同样的卡片宽度上要塞进四五倍多的柱，一格柱窄了几倍，'
            '标签的字号却不跟着缩（<code>assets/charts.js</code> 的字号只随卡片宽度走），'
            '于是标签的右半边伸出了绘图区。窄屏（单栏）比宽屏更明显，同一个原因。'
            '<b>本轮没有把它压下去，理由有两条，都是实测过的：</b>'
            '① spec 侧唯一能让标签变窄的杠杆是砍掉一位小数，而把这三个数各砍一位再量一遍，'
            '窄屏下仍然压在刻度上，只是重叠面积小到检测门限以下 —— 那是把告警藏起来，'
            '不是把字分开；② 小数位是列的 <code>fmt</code>，砍了会连末尾核对表一起砍，'
            '而这三列的位数恰好就是源表自己的精度（份额 1 位、加权天数 2 位），'
            '核对表的用途正是与官方披露逐格对账，不能为了图上少 4px 重叠去动它。'
            '<b>真正的修法在共用引擎</b>：<code>charts.js</code> 已经为次轴末点读数写了'
            '「撞上就让刻度让位」的逻辑，只是没把柱顶数值也算进去；'
            '本轮不改共用件，所以这条缺口仍在页面上。'
            '读数有疑问时走右上角「表格」或页尾核对表，那两处不受排版影响。')


_NOTE_LAST_BAR_LABEL = _last_bar_label_note()


_NOTE_AXIS_SCALE = (
    '<b>⚠️ 纵轴标题里的「（千）」「（百万）」是<u>缩放倍数</u>，不是单位本身。'
    '本页有两族轴标题会<u>自己缠上自己</u>，读之前先看这一条。</b>'
    '数值太宽时底座（<code>build/chartscale.py</code>）会把整条序列除掉一个 10 的幂，'
    '并在纵轴标题后面追加这个中文后缀。追加是<b>字符串拼接</b>，不认识单位串里已经有的'
    '量级词，于是原始单位本身带量级词（<code>mn</code>）的那几张就缠住了：'
    '<b>① 「GBP mn（百万）」= 百万个英镑百万 = <u>英镑万亿</u></b>'
    '（主板总市值合计 / UK / Intl 三张月末存量柱图）：图上那根约 4.2 的柱读作 '
    '<b>£4.2 万亿</b>，不是 420 万英镑。'
    '<b>② 「GBP mn/month（千）」= 千个英镑百万每月 = <u>英镑十亿/月</u></b>'
    '（LSE 与 Turquoise 订单簿成交额那张三线图，以及页尾「LSE 主板订单簿成交额：'
    '水平值与 12 个月滚动同比」那张）：图上约 147 读作 <b>£1,470 亿/月</b>。'
    '对照组：轴标题写「trades（百万）」「trade sides/month（千）」的那几张<b>不缠</b>，'
    '因为 <code>trades</code> 本身不含量级词，「百万笔」就是字面意思。'
    '<b>这个后缀由 build/chartscale.py 拼装，本页 spec 改不到</b> —— spec 能改的只有 '
    '<code>unit</code> 串本身，而把它改成 GBP tn 会连汇总表与末尾核对表一起改掉，'
    '那两张表的用途正是按<b>官方原始单位</b>（factsheet 印的就是 £m）逐格对账，不能换单位；'
    '用 <code>scale</code> 键把整列换算成万亿同样会落到那两张表上，一样不行。'
    '<b>要根治得改底座：让缩放后缀不做字符串拼接，而是把单位串里的量级词整体升一档'
    '（GBP mn × 1e6 → GBP tn、GBP mn/month × 1e3 → GBP bn/month），'
    '认不出量级词时才退回现在的中文后缀。本轮没有改底座，所以这条缺口仍在页面上。</b>'
    '汇总表与末尾核对表不受缩放影响，仍是官方原始量级。'
)

def _mom_why_note():
    """页尾那条「用了单月同比的图，逐张写明理由 + 本序列实测」。

    为什么写成函数而不是常量：每一段里的数都由 `_ev_long()` 现算，
    一个都不写死 —— 换个月、换条数据，页面上的辩护跟着变；理由站不住了要能自己露出来。
    字符串一律用拼接不用 `%` 格式化：`_ev_long()` 回来的正文里带百分号。
    """
    return (
        '<b>用了单月同比的图，逐张写明理由<u>并附本序列实测</u>'
        '（CONTRACT §6.1 第 2 条后半）。</b>'
        '第 2 条要求「标题里写明单月」<b>并且</b>「在图注说明为什么这里该用单月」，'
        '而且理由要用 <code>yoy.describe(yoy.caliber_diff(s, kind, win))</code> 生成 ——'
        '拿<b>这条序列自己</b>实测，不引别家的例子。'
        '<b>⚠️ 本页够不到图注</b>：单列柱图（<code>gs_bar</code>）与头条同比图'
        '（<code>grouped_bars</code>）的 <code>note</code> 整段由 '
        '<code>build/single.py</code> 的 <code>ex_single()</code> / <code>ex_yoy()</code> '
        '拼装，spec 侧一个字都插不进去（<code>COL_KEYS</code> 与 <code>groups</code> 的'
        '允许键里都没有 note 这一项）。所以理由与一句话实测写进<b>标题</b>'
        '（组名会原样印进图标题），完整实测段落列在下面。'
        '<b>这是妥协不是等价物：要让实测段真的落进每张图自己的图注，必须改底座。</b>'
        '实测口径与 Exhibit 59 / 60 图注里底座那段完全一致 —— 同一套统计量、'
        '同样先取两种口径的交集再比、窗口都是图上真正画出来的那 25 个月。'

        '① <b>两张头条同比图</b>（Tradeweb 月成交额 / Tradeweb ADV 的「：同比」）'
        '画的是<b>单月同比</b>。用途是逐月核对当月读数，与页顶数据条、汇总表 y/y 列同口径；'
        '同一列的默认滚动口径本页也有 —— 页尾「Tradeweb 全公司成交额：水平值与 12 个月'
        '滚动同比」那张，趋势判断看它。'
        '月成交额：' + _ev_long('tradeweb_volume_total_usd_tn') +
        'ADV：' + _ev_long('tradeweb_adv_total_usd_bn') +
        '<b>⚠️ 已知缺口（本轮没修）：这两张的标题只写「：同比」、没写 §6.1 第 2 条'
        '要求的「单月」，它们自己的图注也没有上面这两段实测。</b>'
        '标题与图注都由 <code>build/single.py</code> 的 <code>ex_yoy()</code> 写死'
        '（<code>title = f\'{c["zh"]}：同比\'</code>），而头条列在 spec 里只有 '
        'col / zh / unit / fmt 四个允许键 —— 把「单月」塞进 <code>zh</code> 能改到标题，'
        '但同一个 <code>zh</code> 还会印到页顶数据条、汇总表行标签、末尾核对表表头，'
        '以及 Exhibit 2/3（全历史）与两张季节性图的标题上，那五处写「单月」全是错的。'
        '所以本轮<b>不改</b>，缺口留在这里明写：要补必须动 <code>ex_yoy()</code>。'
        '在补上之前，这两张图的口径以本条与页尾的口径说明为准。'

        '② <b>两张成交份额</b>（LSE 英国 Lit、Turquoise 泛欧）：比率不做滚动合计也不做'
        '滚动均值（§6.1 第 5 条），单月的<b>百分点差</b>是它唯一合法的口径 ——'
        '没有第二种口径可比，这本身就是理由。'
        'LSE 英国 Lit：' + _ev_long('lse_lit_uk_share_pct', ratio=True) +
        'Turquoise 泛欧：' + _ev_long('turquoise_paneuropean_share_pct', ratio=True) +

        '③ <b>GBP/EUR 换算率</b>：换算常数不是流量，把 12 个月的汇率加起来不指代任何东西。'
        + _ev_long('gbp_eur_rate', ttm_meaningless=True) +

        '④ <b>Tradeweb 集团加权交易日数</b>：命题本身就是「这个月比去年同月多开几天」，'
        '滚动窗口正好把要看的东西抹平（§6.1 第 2 条举的 <code>cme</code> Ex3 是同一类）。'
        '下面这组数就是「抹平」的量化 —— 滚动侧的标准差与相邻月跳变小到接近于说'
        '「什么都没发生」，而要看的正是被它抹掉的那部分：'
        + _ev_long('tradeweb_trading_days_blended') +

        '⑤ <b>LCH ForexClear 两张</b>：这条腿的历史被官方滚动窗口卡住'
        '（月度 CSV 末行原文 Row Count: 24），短于滚动同比连成线所需的长度。'
        '名义额：' + _ev_long('forexclear_notional_registered_usd_tn') +
        '笔数：' + _ev_long('forexclear_trades_registered_count') +
        '注意这一条会<b>自己过期</b>：期数一够（滚动同比连成线要 '
        + str(_TTM_LINE) + ' 期），'
        '标题里那句理由会自动换成一句自曝的话（见 <code>_short_hist_why</code>）——'
        '理由跟着数据走，不写死。'

        '⑥ <b>Tradeweb 其他政府债 ADV：本轮把这条单月同比线<u>撤掉了</u>。</b>'
        '它有 ' + str(_n_obs('tradeweb_adv_other_govt_bonds_usd_bn') or '？') + ' 期、'
        '滚动口径完全算得出来，上一轮标题上给的理由是「留单月供逐月核对」—— 那是<b>用途</b>'
        '理由，不在第 2 条允许的两类（命题就是一个月之内 / 滚动口径根本不存在）里。'
        '本轮把它并进「欧洲国债与其他政府债」那一组（同单位，'
        + _scale_gap_txt('tradeweb_adv_eu_govt_bonds_usd_bn',
                         'tradeweb_adv_other_govt_bonds_usd_bn') +
        '），底座改画折线 —— 只有水平值、没有次轴同比；同比只剩页尾那张滚动图。'
        '撤掉不损失什么，这一列的单月口径本来也没有比滚动更稳 —— '
        + _ev_long('tradeweb_adv_other_govt_bonds_usd_bn') +

        '⑦ <b>一级市场的增发笔数</b>（主板 ' + str(_n_obs('mm_further_issues_count') or '？')
        + ' 期 / AIM ' + str(_n_obs('aim_further_issues_count') or '？') + ' 期）'
        '原先各自单列成柱图、因而被迫画单月同比，而它们给不出口径上的理由 ——'
        '上一轮已把两列并成同单位的一张折线图，页面上不再出现那两条线。'

        '⑧ <b>LCH RepoClear 的两列清算边数</b>目前只有 12 期，底座算不出任何一个月的同比，'
        '<code>gs_bar</code> 自己退成了不带次轴的 <code>bars_labeled</code>，'
        '所以它们的组名里<b>没有</b>「次轴：单月同比」那句声明 ——'
        '声明由 <code>_mom_drawn()</code> 按数据现判，不写死，避免在页面上印一句假话。'

        '<b>存量列的次轴同比不在本条范围内</b>：那是点对点同比，'
        '按 §6.1 第 4 条本来就是存量的默认口径，不需要辩护。'
    )


_NOTE_MOM_WHY = _mom_why_note()


SPEC = {
    'ticker': 'lseg',
    'name':   'London Stock Exchange Group',
    'title':  '伦敦证券交易所集团（LSEG）月度经营指标',
    'csv':    'lseg.csv',
    # ⚠️ `ccy` 不是「集团财报的记账本币」，是**印在副标题与第 1 条 notes 上的那句话**
    # （底座的模板是「本币 {ccy}」，见 build/single.py:2143 与 :2173）。
    # 原先这里写 'GBP'，于是副标题印「本币 GBP」而紧挨着的头条数据条印
    # 「67.5 USD tn/month」「2,928 USD bn/day」—— 页面自己跟自己打架，
    # 第 1 条 notes 还跟着写死「本页只按本币标注」。
    # 本页根本不是单币种页（英镑 / 美元 / 欧元三种金额列并存，见页首币种那一条），
    # 所以这里改成如实的一句话，列数由 _ccy_counts() 现算、不写死。
    # **仍然不做任何汇率换算**（那是 build/notional.py 的事）—— 换算与标注是两件事，
    # 这次改的只是标注。
    'ccy':    CCY_MIX,
    'source': ('Source: LSE Monthly Market Report、LSE Main Market / AIM factsheet、'
               'Tradeweb Historical ADV workbook、LCH SwapClear / ForexClear / RepoClear '
               'volumes; format after Goldman Sachs GIR'),

    'headline':  HEADLINE,
    'groups':    GROUPS,
    'slow_cols': SLOW_COLS,

    # series/lseg_breaks.csv 不存在；三处已知变化都不该画成全页红线，见 _NOTE_BREAKS。
    'breaks': [],

    # ══ 量价分解 ═════════════════════════════════════════════════════════════
    # 只做一条，而且只做 LSE 订单簿这一对：它是本表里**唯一**一对同口径、同粒度、
    # 取自同一张表同一行的（金额，数量）。
    #   · Tradeweb 那 27 列全是金额/ADV，一条笔数列都没有 → 配不成对；
    #   · 一级市场的「募资额 / 家数」相除得到的是「每家平均募资额」，
    #     而分母有大量取 0 的月份（近零基数），年度聚合虽然避开了这一点，
    #     但那个比值的经济含义是「这一年上市的公司平均多大」，
    #     与 kind 的三类（share_price / per_trade / revenue_rate）都不对应 → 不做；
    #   · LCH 的（名义额，笔数）历史只有 12–24 个月，凑不出 years+1 个完整年度。
    # granularity 必须写 'monthly_total'：这两列本身就是当月合计。
    # **不给 weight_col** —— 声明 monthly_total 又给 weight_col 是硬失败，
    # 而真乘上去会把年度合计放大二十几倍、图形却照常画得出来。
    'decomp': [{
        'zh':   'LSE 主板订单簿成交额',
        'kind': 'per_trade',            # 派生量是「每笔平均成交额」，衡量订单碎片化程度
        'granularity': 'monthly_total',
        'value': {'col': 'lse_orderbook_value_gbp_m', 'zh': '订单簿成交额',
                  'unit': 'GBP mn/month', 'fmt': 'f0c'},
        'qty':   {'col': 'lse_orderbook_trades_count', 'zh': '订单簿成交笔数',
                  'unit': 'trades/month', 'fmt': 'f0c'},
        'price_zh':    '每笔平均成交额',
        'price_unit':  'GBP/trade',
        'price_fmt':   'f0c',
        'price_scale': 1e6,             # £m ÷ 笔 → £/笔，纯单位换算，对增长率无影响
        'years': 4,                     # 需要 5 个完整日历年；本表 2021–2025 正好 5 年
        'note': _NOTE_DECOMP,
    }],

    # ══ 水平值 + 12 个月滚动同比 ═════════════════════════════════════════════
    # 两条腿各一张：Tradeweb（快腿、头条）与 LSE 订单簿（慢腿、伦敦现货旗舰）。
    # 两条 level 列都是**当月合计**口径，所以两张图都不给 weight_col / total_col
    # （理由见 _NOTE_NO_DECOMP_TRADEWEB：给了就会撞上 1e-6 的对账阈值而整页硬失败）。
    # `lse_orderbook_value_gbp_m` 在 groups 里是三条线之一、不是单桶 gs_bar，
    # 所以这张滚动图不会与任何一张单月同比图重复。
    'ttm_yoy': [
        {'zh': 'Tradeweb 全公司成交额',
         'granularity': 'monthly_total',
         'level': {'col': 'tradeweb_volume_total_usd_tn', 'zh': '当月成交额',
                   'unit': 'USD tn/month', 'fmt': 'f1'},
         'note': _NOTE_TTM_TRADEWEB},

        {'zh': 'LSE 主板订单簿成交额',
         'granularity': 'monthly_total',
         'level': {'col': 'lse_orderbook_value_gbp_m', 'zh': '当月成交额',
                   'unit': 'GBP mn/month', 'fmt': 'f0c'},
         'note': _NOTE_TTM_ORDERBOOK},

        # 本轮新增。它在 groups 里是**单列桶** ⇒ 底座画 gs_bar ⇒ 次轴写死是单月同比，
        # 而这一列有 115 期、滚动口径完全算得出来：按 §6.1 第 1 条默认就该用滚动，
        # 第 2 条又要求用单月必须给出口径上的理由 —— 它给不出。既然 spec 侧改不了
        # gs_bar 次轴的口径，就在这里把默认口径补出来，两张图由底座在页尾各自点名。
        # granularity 写 'daily_avg'（这一列是 ADV），**不给 weight_col**：
        # CONTRACT §6.3 明写日均序列不要乘回交易日；何况 Tradeweb 那列加权天数是
        # **集团级**的、不是这一个分项的，拿它还原会引进一个方向未知的偏差。
        {'zh': 'Tradeweb 其他政府债 ADV',
         'granularity': 'daily_avg',
         'level': {'col': 'tradeweb_adv_other_govt_bonds_usd_bn', 'zh': '当月日均成交额',
                   'unit': 'USD bn/day', 'fmt': 'f1'},
         'note': _NOTE_TTM_OTHER_GOVT},
    ],

    # notes 的顺序就是页面上的顺序，而底座会先塞 9 条自己的（数据源 / 数据月 / 慢腿 /
    # 存量与流量 / 图型规则 / 同比口径 / 汇总表 / 显示缩放 / 核对表），本文件这几条接在后面。
    # **币种那一条必须排第一**：它是本页最容易读错的一件事（副标题一个币种、
    # 紧挨着的头条数据条另一个币种），原先排在本文件的第三条、落到页面第 12 条、
    # 折叠线以下，等于没写。紧随其后的三条是「底座生成、spec 改不到」的抵消说明 ——
    # 它们更正的正是页面前面那几条底座 notes 里的话，晚出现就失去意义。
    'notes': [
        _NOTE_CCY,
        _NOTE_MOM_WHY,
        _slow_truth_note(),
        _NOTE_AXIS_SCALE,
        _NOTE_LAST_BAR_LABEL,
        _near_zero_note(),
        _NOTE_LEGS,
        _NOTE_HEADLINE,
        _NOTE_ORDERBOOK,
        _NOTE_PRIMARY,
        _NOTE_LCH,
        _NOTE_TRADEWEB_CALIBER,
        _NOTE_NO_DECOMP_TRADEWEB,
        _NOTE_NEITHER,
        _NOTE_BREAKS,
        _NOTE_SOURCE_DATE,

        '<b>数据真实性。</b>四条腿的 86 列全部是 [A] 级（公司/交易所原始披露或监管申报），'
        '本页不含任何券商研报的观点或数据。取数腿逐格回官网原件抽查过 8 个月份共 152 格、'
        '0 处不符；表里的空格全部经原件确认是官方发布窗口所致的<b>真缺席</b>，'
        '既不是解析失败，也不是被静默填进去的占位值 —— 抓取腿的规矩是宁可少一列、'
        '不许假一列。页面上唯一的派生量是每笔平均成交额那张分解图，已单独标注。',
    ],
}
