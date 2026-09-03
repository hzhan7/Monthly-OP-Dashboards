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
   `decomp` 一旦同时给 `weight_col` 与 `*_total_col`，底座会逐月对账，
   相对偏差 > 1e-6 就整页硬失败（退出码 1）。实测残差：
   Tradeweb `ADV × blended 天数 vs 月成交额` 2.5e-4、
   orderbook `ADV × 交易日 vs 月合计` 9.1e-4 —— 两条腿都远超阈值。
   原因是官方自己就把 £m 四舍五入到整数、把 blended 天数印到 2 位小数。
   所以本文件的 `level_yoy` 三条**都只用列本身**（2026-09 改单月口径后，
   那三个还原用的键已从 spec 里删除，见 CONTRACT §6.4），
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
       方向在安全侧（`ttm()` 会抛 CaliberError 而不是给错数）。
       ⚠️ 2026-09 全站改单月口径之后这一条的**后果变小了**：`mom_yoy()` 对 FLOW 与
       STOCK 是同一个算式（本期 ÷ 去年同期 − 1），错分只影响图注措辞与
       `ttm()` 那条已经不上页面的对照线，不再影响画出来的数。RATIO 那一条仍然要命 ——
       它走 `v − base`，会把 +47% 印成「+562pp」而且不报错。
   **不许改 build/yoy.py** —— `classify()` 自己的 docstring 就写着它只是默认建议、
   不是权威，有疑问时由调用方显式传 kind（出处是 build/yoy.py，不是 CONTRACT §6：
   §6 从头到尾没提过 classify）。

D. **LCH 的短历史是官方滚动窗口，不是起点设窄。**
   ForexClear 的 CSV 末行原文 `Row Count: 24`；SwapClear 两个 datatable JSON 各 12 行；
   RepoClear 页面里 3 张月度 grid 各 12 行（而同页年度 grid 有 28 行、回溯到 1999，
   证明官方有更深历史但**只以年度形式公开**）。官方每期只发这么一个窗口，
   本仓入库后永不删除，所以序列自己每个月长一期。
   ⚠️ **上一版这里那句反推按 2026-09 之前的滚动口径算，已经作废。**
   原文是「12 期连 13 期的点对点同比都算不出，24 期的 TTM 同比只有一个点、不成线，
   所以 LCH 的 18 列本轮一律只画水平值，跑满一年后自然长到 24 期」——
   24 / 25 期是 12 个月滚动同比的门槛（第一个点要 24 期、连成线要 25 期）。
   全站改单月之后门槛只剩 **13 期**，18 列现在全部过线（2026-09 本机实测：
   ForexClear 25 期、RepoClear 14 期、SwapClear 13 期），页面上单列成桶的那四张
   （ForexClear 名义额 / 笔数、RepoClear 两个法人的清算边数）确实带着次轴单月同比，
   只是每张只有 2–13 个点、斜率不要外推。**仍然成立的是另一半：LCH 一列都不进
   headline** —— 底座的发布门槛要 ≥24 个月共同历史（SINGLE_SPEC §3），与同比无关。

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
import re

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


def _win_from():
    """底座钉死的窗口左端 —— 现读 `build/single.py` 的 `WIN_FROM`，本文件不存第二份。

    2026-08-18 底座把 `WIN_LONG = 25`（最后 25 个月）换成了 `WIN_FROM = '2016-01'`，
    而本文件里那份复制品没跟着改：于是标题与页注上「本序列近 25 个月实测…」
    是拿一段**图上没有画**的窗口量出来的数，而同一张图的横轴写着 Jan-16–Jul-26。
    读者往下滚到页注第 13 条还会读到「本页窗口从最近 25 期拉到 2016-01 起之后」——
    同一页自己把自己证伪。写死一次就会这样过期一次，所以这里改成现读。

    为什么不 `import single`：本文件正是被 single.py 在 import 期加载的，反过来把
    整个底座再执行一遍（numpy / pandas / mrwin / payload_guard 全跟着跑）只为拿一个
    字符串常量，代价与风险都不划算。读不到就返回 None，`_drawn_window` 退回
    「不裁左端」= 整条 CSV —— 那是本页的现状（series/lseg.csv 首月就是 2016-01），
    不会凭空造出一段图上没有的窗口。
    """
    try:
        with open(os.path.join(_ROOT, 'build', 'single.py'), encoding='utf-8') as fh:
            for line in fh:
                m = re.match(r"WIN_FROM\s*=\s*'(\d{4}-\d{2})'", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


_WIN_FROM = _win_from()


def _drawn_window(col):
    """底座给这一列画出来的那段横轴（`Page.win_long()` 的复算）。

    左端 = max(CSV 首月, `WIN_FROM`)，只往右让不往左借；
    **右端是该列自己最后一个有值的月**（`ex_single` 用 `self.last_month(c)`），
    不是本页数据月 —— 慢腿的图右端比头条早两三周，用错窗口报出来的实测是图外的事。
    """
    idx = [r['month'] for r in _ROWS]
    got = [r['month'] for r in _ROWS if _num(r, col) is not None]
    if not got:
        return None
    i = idx.index(got[-1])
    lo = 0
    if _WIN_FROM:
        while lo < i and idx[lo] < _WIN_FROM:
            lo += 1
    return idx[lo:i + 1]


def _win_zh(col):
    """图上那段窗口的人话 —— 「2016-01–2026-07 共 127 个月」。

    不写「近 N 个月」：窗口左端是钉死的 `WIN_FROM` 不是滚动近端，
    底座 `Page.win_zh()` 出于同一个理由也不那么写。
    """
    win = _drawn_window(col)
    if not win:
        return '图上窗口'
    return '%s–%s 共 %d 个月' % (win[0], win[-1], len(win))


def _win_left():
    """全页共用的窗口左端 = max(CSV 首月, WIN_FROM)。读不到 CSV 就退回 WIN_FROM。"""
    first = _ROWS[0]['month'] if _ROWS else None
    if first and _WIN_FROM:
        return max(first, _WIN_FROM)
    return first or _WIN_FROM or '序列首月'


_WIN_LEFT = _win_left()


# ── 近零基数列：判据与实现都在 build/yoy.py，本文件只报结果 ────────────────
# CONTRACT §6.1 第 5 条：近零基数的序列不画同比、画水平值。
# 本页的落实方式是**排版**而不是开关：这些列一律放进 2–5 列同单位的组，
# 底座对多列桶画 lines（只有水平值、没有次轴同比），于是那条会跳到几百个百分点的
# 同比线根本不会被画出来。下面这个函数只负责把「哪几列」现算出来写进图注。
#
# ⚠️ 2026-08-07 修正：`win` 必须给**图上真正画出来的那段窗口**，原先漏了这个参数。
# `yoy.near_zero_base` 的 docstring 明写：「有几个月不可读」只能数图上画出来的那些月 ——
# 一条 2010 年近零、现在早已正常的序列，拿全历史计数就会永远背着这个标签，那是制造噪声。
# ⚠️ 2026-08-19 再修一次：`_drawn_window` 当时把「图上画出来的」写死成最后 25 个月，
# 而底座早已改成 `WIN_FROM`。窗口一改命中集合就跟着改（本轮实测有列进、有列出）——
# 这正说明「命中哪几列」不能写死在任何地方：它是窗口的函数，窗口是底座的常量。
# 命中几条、是哪几条一律由 `_near_zero_cols()` 现算，本注释与页注都不写死；
# 想看当期名单就 import 本模块打印 `_NEAR_ZERO`，页注里那条报的是同一个对象。
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
      · `_near_zero_cols()` 判的是**整条序列**该不该画同比线（§6.1 第 5 条，
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
        # 只数**图上那段窗口**内（`_drawn_window`，左端 = WIN_FROM）：窗外算得出
        # 同比也没人看得见，而窗内一个点都没有时底座会退成 bars_labeled。
        win = _drawn_window(col)
        if win:
            y = y.reindex(win)
        return bool(np.isfinite(y.values.astype(float)).any())
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
    """本序列自己实测的两种同比口径差异 —— CONTRACT §6.1 第 3 条要的那份证据。

    第 3 条明写：代价「请用 `yoy.describe(yoy.caliber_diff(s, kind, win))` 生成 ——
    它拿**这条序列自己**实测，不引别家的例子」。这里就是那一步，两个参数都不能马虎：

      · `kind` 必须与图上那条金线一致。比率列走 RATIO（百分点差），其余走 FLOW（%）。
        写错的代价是报出来的标准差与读者看到的线不是一回事。
      · `win` 必须是**图上真正画出来的那段窗口**（`_drawn_window`），不是全历史。
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
    # 不写「近 N 个月」：窗口左端是钉死的 WIN_FROM，不是滚动近端窗口
    # （底座 `Page.win_zh()` 出于同一个理由也不那么写）。
    span = ('%s–%s 共 %d 个月' % (win[0], win[-1], len(win))) if win else '图上窗口'
    sm, st = _fin(d.get('std_mom')), _fin(d.get('std_ttm'))
    if ratio:
        return ('；本序列在图上这段窗口（%s）实测单月同比逐月标准差 %.1fpp，'
                '滚动口径对比率非法、没有可比数' % (span, sm)) if sm is not None else ''
    if ttm_meaningless:
        return ('；本序列在图上这段窗口（%s）实测单月同比逐月标准差 %.1fpp，'
                '滚动口径不报数：把 12 个月的换算率加起来不指代任何量'
                % (span, sm)) if sm is not None else ''
    floor = getattr(_yoy(), 'MIN_DIAG_MONTHS', 12)
    if (d.get('n') or 0) < floor:
        return ('；本序列实测两种口径都有值的月份只有 %d 个（< %d），量不出差异'
                % (d.get('n') or 0, floor))
    if sm is None or st is None:
        return ''
    return ('；本序列在图上这段窗口（%s）实测单月同比逐月标准差 %.1fpp、'
            '12 个月滚动 %.1fpp，符号相反 %d 个月'
            % (span, sm, st, d.get('opposite_n') or 0))


def _ev_long(col, ratio=False, ttm_meaningless=False):
    """页尾口径说明里那一整段实测 —— 与末尾三张 `level_yoy` 图注里底座那段同源。

    「同源」到什么程度要说准：同一条序列、同样先取两种口径的**交集**再比、同一段
    窗口（本页 CSV 首月就是 `WIN_FROM`，所以底座那段的全序列 = 图上那段窗口）。
    **差别在相邻月跳变这一项**：底座报的是最大值（`np.nanmax`），这里报的是中位数
    （`caliber_diff` 的 `medjump_*`）。别写成「同一套统计量」——两个数不一样。
    图号不写死：`level_yoy` 那几张排在页尾，加一组图就会整体后移。

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
                '滚动侧<b>没有数可比</b>（%s），所以这一行只有单月这一列数。'
                % (span,
                   '—' if sm is None else '%.2f' % sm,
                   '—' if _fin(d.get('medjump_mom')) is None else '%.2f' % d['medjump_mom'],
                   d.get('reason') or '比率不做滚动合计也不做滚动均值'))
    floor = getattr(_yoy(), 'MIN_DIAG_MONTHS', 12)
    if n < floor:
        return ('实测（%s）：与滚动口径都有值的月份只有 <b>%d</b> 个（< %d），'
                '<b>差异量不出来</b> —— 这条腿短到连对照口径都排不出一条线，'
                '图上那条单月同比本身也只有很少几个点。'
                % (span, n, floor))
    head = ('实测（%s，其中 %d 个月两种口径都有值）：单月同比逐月标准差 <b>%s pp</b>，'
            % (span, n, '—' if sm is None else '%.1f' % sm))
    if ttm_meaningless:
        return (head + '滚动侧<b>故意不报</b>：把 12 个月的换算率加起来不指代任何量，'
                       '给它报一个标准差等于给不存在的东西报精度。'
                       '这条序列的合法口径本来就只有点对点一种。')
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
    """组名后缀：声明单月口径 + 一句这条序列自己的实测。

    ⚠️ **2026-09 之前 `why` 是一条辩护**：全站默认口径是 12 个月滚动合计的同比，
    当时的 §6.1 第 2 条要求用单月必须「标题里写明」并「在图注说明为什么这里该用单月」。
    页面所有者已把全站口径统一成单月，那条「为什么」不再需要逐图给
    （新 §6.1 只剩第 3 条要求逐图印**代价**）——
    但**声明**与**实测代价**两件事都留着，而且比从前更该留：全页一种口径的时候，
    读者更容易忘记单月同比会被基数和日历推着走。

    声明为什么写进组名而不是图注：单列桶画出来的 `gs_bar`，其 `note` 整段由
    build/single.py 的 `ex_single()` 拼装，spec 侧一个字都插不进去 ——
    `COL_KEYS` 与 `groups` 的允许键里都没有 note 这一项（见 build/single.py 里
    `COL_KEYS` 的定义与 `_check_keys()` 的调用处）。组名会原样印进图标题，
    是这张图上**唯一**由本文件控制的字符串。页尾 `_NOTE_MOM_WHY` 再逐图列一遍。

    `why` 现在写的是「这条序列有什么脾气」，不是「为什么不用滚动」。仍然不许写
    「看着更灵敏」这类说法 —— 那不是关于数据的断言，核不了。本文件里的几类：
      · 比率列 —— 比率不做滚动合计也不做滚动均值（§6.1 第 4 条，与本轮改口径无关）；
      · 短历史腿（LCH）—— 可比月很少，斜率不要外推；
      · 命题本身就是「一个月之内会怎样」（交易日数、月报自印的换算率）。

    2026-08-07 补上的那半句在新契约里对应 **§6.1 第 3 条**：代价不能只是定性的一句话，
    该条要求「用 `yoy.describe(yoy.caliber_diff(s, kind, win))` 生成 ——
    它拿这条序列自己实测」。所以 `_ev_short()` 现算的实测数跟着理由一起进标题，
    完整段落进页尾 `_NOTE_MOM_WHY`。一个数都不写死：换个月、换条数据全跟着变。
    """
    if not _mom_drawn(col, ratio):
        return ''
    what = '单月同比，百分点差' if ratio else '单月同比'
    return '（次轴：%s —— %s%s）' % (what, why,
                                    _ev_short(col, ratio, ttm_meaningless))


def _median_drawn(col):
    """该列在**图上那段窗口**里的中位数。页注要报的量级对比取这个数，不写死。

    用画出来的窗口（`_drawn_window`）而不是全历史：拿来说事的是「这两条线放同一根
    轴上会不会把小的压平」，那是读者眼前这张图的事 —— 窗口一改，这个数必须跟着改。
    """
    win = set(_drawn_window(col) or [])
    v = sorted(x for x in (_num(r, col) for r in _ROWS if r.get('month') in win)
               if x is not None)
    if not v:
        return None
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0


def _scale_gap_txt(col_a, col_b):
    """「图上这段窗口（…）中位 A vs B，差 N 倍」—— 两列量级差多少，现算。

    窗口取 `col_a` 的（同组同单位、右端同一个月），一并印出来 ——
    「中位数」离开窗口就没有定义，只报数字不报窗口正是上一版过期的原因。
    """
    a, b = _median_drawn(col_a), _median_drawn(col_b)
    if not a or not b:
        return '两列的中位量级读不到（缺 CSV）'
    hi, lo = (a, b) if abs(a) >= abs(b) else (b, a)
    return ('图上这段窗口（%s）中位 %s vs %s，差 %.1f 倍'
            % (_win_zh(col_a), ('%.1f' % a), ('%.1f' % b), abs(hi) / abs(lo)))


def _n_obs(col):
    """该列有值的月份数。读不到返回 None（调用方退回不含数字的定性说法）。"""
    if not _ROWS:
        return None
    return sum(1 for r in _ROWS if _num(r, col) is not None)


# 12 个月滚动同比的第一个点要 24 期（12 期滚动合计 + 再往前 12 期），连成线要 25 期。
# 页上**不再画滚动同比**（2026-09 全站改单月，页面所有者指定），这两个常数留下来
# 只做一件事：给 `_short_hist_why()` 一个「这条腿算长还是算短」的刻度，
# 以及页尾那条实测里「对照口径算不算得出来」的门槛。
_TTM_FIRST, _TTM_LINE = 24, 25


def _repo_sides_n_zh():
    """RepoClear 两列清算边数各有几期 —— 现算。

    写死成「12 期」会在官方那个滚动窗口一变长就成假话 —— 本仓入库后永不删除，
    这两列每个月都长一期（上一版拿它解释「为什么这两张退成了 bars_labeled」，
    而它们早已长过 13 期、金线自己出现了，见 `_repo_sides_mom_zh()`）。
    """
    ns = [n for n in (_n_obs('repoclear_ltd_cleared_trade_sides_count'),
                      _n_obs('repoclear_sa_cleared_trade_sides_count')) if n]
    if not ns:
        return '（期数读不到）'
    return f'{ns[0]} 期' if len(set(ns)) == 1 else '、'.join(f'{n} 期' for n in ns)


_REPO_SIDES_COLS = ('repoclear_ltd_cleared_trade_sides_count',
                    'repoclear_sa_cleared_trade_sides_count')


def _repo_sides_mom_zh():
    """RepoClear 两列清算边数：次轴那条金线到底画没画出来 —— 现判，不写死。

    ⚠️ 上一版这段写死成「底座算不出任何一个月的同比，`gs_bar` 退成了 `bars_labeled`，
    所以组名里没有『次轴：单月同比』那句声明」。那是这两列还只有 12 期时的实况。
    它们已经长过 13 期，金线自己出现了，于是这句话变成**被同一页当场证伪**的假话：
    页面上那两张确确实实是 `gs_bar`，标题里确确实实写着「次轴：单月同比」。
    ⇒ 改成拿 `_mom_drawn()` 现判，句子跟着数据走，长回去或再长都不会说错。
    """
    drawn = [c for c in _REPO_SIDES_COLS if _mom_drawn(c)]
    pts = [max(0, (_n_obs(c) or 0) - 12) for c in _REPO_SIDES_COLS]
    if not drawn:
        return ('底座算不出任何一个月的同比，'
                '<code>gs_bar</code> 自己退成了不带次轴的 <code>bars_labeled</code>，'
                '所以它们的组名里<b>没有</b>「次轴：单月同比」那句声明 ——'
                '声明由 <code>_mom_drawn()</code> 按数据现判，不写死，'
                '避免在页面上印一句假话。')
    n = pts[0] if len(set(pts)) == 1 else ' / '.join(str(p) for p in pts)
    head = '两张' if len(drawn) == 2 else '其中一张'
    return (f'扣掉同比要的 12 个月基期，图上只剩 <b>{n}</b> 个同比点 ——'
            f'{head}仍是 <code>gs_bar</code>、次轴那条金线在，'
            '组名里也照写着「次轴：单月同比」。<b>两三个点连出来的方向不是趋势，'
            '斜率不要外推。</b>这句声明由 <code>_mom_drawn()</code> 按数据现判、'
            '不写死：哪天这两列缩回 13 期以下，底座会把 <code>gs_bar</code> 退成 '
            '<code>bars_labeled</code>，声明也会自己从组名里消失。')


def _short_hist_why(col):
    """短历史腿的一句话交代 —— 期数现算，不写死。

    ⚠️ **2026-09 之前这个函数产出的是一条「辩护」**：全站默认口径是 12 个月滚动
    合计的同比，用单月必须给理由，而这两条 LCH 腿的理由是「历史太短、滚动同比连不成
    线」。页面所有者已把全站口径统一成单月，那条辩护整个失去对象 —— 单月不再需要
    理由，需要交代的反过来是**这条线本身有多短、读的时候要打几分折扣**。

    期数仍然现算：写死成「本腿只有 24 期」的代价是它会自己变成假话，LCH 每跑一个月
    就长一期。够 25 期（滚动同比连成线所需）时不再说「算不出滚动」，改说一句中性的
    长度描述 —— 页面上不留一句会随时间自己变假的话。
    """
    n = _n_obs(col)
    if n is None:
        return '本腿历史短，同比只有很少几个可比月，斜率不要外推'
    if n >= _TTM_LINE:
        return ('本列已有 %d 期、同比的可比月约 %d 个，够读趋势，'
                '但仍是本页最短的腿之一，斜率不要外推' % (n, max(0, n - 12)))
    return ('本列只有 %d 期，扣掉同比要的 12 个月基期，图上只有约 %d 个点，'
            '斜率不要外推' % (n, max(0, n - 12)))


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
    # （charts.js 里 `lines_endlabels` 端点标签那段的 `var lx = M.l - 10 - (tickW || 26)`），
    # 而纵轴标题是竖排画在 `fscale(13)` 上的 —— 两者之间只剩
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
    #     f0 还是 f0c 都补千分位**（见 `single.fmt_val()` 的 docstring），所以核对表
    #     与汇总表逐字节不变，仍是「1,270,124」。变的只有图上标签与图内表格视图。
    #   · 不能靠 `build/chartscale.py` 的显示缩放（隔壁 Ex 6「（千）」/ Ex 8「（百万）」
    #     就是它做的）：它的预算模型按 FS=1 算，本图标签 35.6px < 预算 39.5px，判「不需要」，
    #     而真实渲染的通栏字号 FS=1.70 把标签放大到 60.5px、走廊却只跟着放大一部分
    #     （上面那行 `M.l - 10` 里的 `− 10` 是写死的、不随 FS 长）。那是底座的口子，不在本页改。
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
                      '比率列不做滚动合计也不做滚动均值，CONTRACT §6.1 第 4 条',
                      ratio=True), 'cols': [
        {'col': 'lse_lit_uk_share_pct', 'zh': 'LSE 英国 Lit 订单簿份额',
         'unit': '% of UK lit order book', 'fmt': 'pct1'},
    ]},

    {'zh': 'Turquoise 泛欧 Lit + Dark 成交份额'
           + _mom_tag('turquoise_paneuropean_share_pct',
                      '比率列不做滚动合计也不做滚动均值，CONTRACT §6.1 第 4 条',
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
    # 按 CONTRACT §6.1 第 5 条属于近零基数序列：**只画水平值、不画同比**。
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

    # Main Market 与 AIM 的增发笔数**合成一组**。当初的理由是口径：单列成桶的组底座
    # 一律画 gs_bar、次轴写死单月同比，而当时全站默认是滚动口径、用单月要给理由。
    # 2026-09 全站统一成单月之后那条理由失效，**但这一组不拆回去** —— 留着的新理由
    # 见下一段：这两列是小整数计数序列，同比主要是分母的故事。
    # （历史存档：这两列分别有 98 / 114 期、滚动口径完全算得出来，按当时的 §6.1
    # 第 1 条默认就该用滚动，而第 2 条要求用单月必须给出**口径上的**理由 —— 给不出（既不是比率、
    # 历史也不短、命题也不是「一个月之内会怎样」）。与其在标题上硬编一个站不住的理由，
    # 不如让它们不再单列成桶：两列同单位（issues/month）、量级只差约 2 倍
    # （2026-08-19 现量中位 57 vs 123，远在本文件「差 20 倍才拆组」那条纪律之内），
    # 并成一个桶后底座改画 lines —— 只有水平值、没有次轴同比。
    # 2026-09 全站改单月口径后「被迫画单月同比」这条理由失效，但分组保留：
    # 这两列是小整数计数序列，同比在它们身上主要是分母的故事（§6.1 第 5 条同一类）。
    {'zh': 'Main Market 与 AIM 当月增发笔数（同单位合图；两列都是小整数计数，'
           '同比主要是分母的故事，不单画）',
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
    # （长历史 + 同比 + 季节性 + 末尾的「水平值与单月同比」），再给它一张单桶柱图是纯重复；
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

    # ⚠️ 2026-08-07 拆成两组，当时的理由是**口径**不是排版：单列成桶 ⇒ 底座画 gs_bar
    # ⇒ 次轴写死单月同比，而其他政府债给不出「为什么该用单月」的口径理由
    # （当时全站默认是 12 个月滚动）。2026-09 全站统一成单月，那条理由整个失效。
    # **但这个分组不改回去**，因为它现在有一条与口径无关、同样成立的理由：
    # 欧洲国债与其他政府债同单位（USD bn/day）、量级差远在本文件「差 20 倍才拆组」
    # 之内，本来就该同轴对读；而其他政府债的同比在页尾那张「水平值与单月同比」上
    # 一样看得到，不缺。
    # ⚠️ 这里有一处**必须一起看**的联动：页尾那张（`_LEVEL_YOY` 第三条）与本组
    # 若哪天被合并成单列桶，就会出现两张一模一样的 gs_bar —— 底座对此有硬护栏
    # （build/single.py 的 `ex_level_yoy`：撞上 SpecError）。
    # 美国国债 / 按揭与其他政府债的量级差超过 20 倍，所以留在自己那一组。
    # ⚠️ **这里一个中位数都不写**：拆组判据是「两列中位差 20 倍」，而中位数只在窗口里
    # 有定义，窗口一改（2026-08-18 就从「最近 25 期」改成 WIN_FROM 起）四个数全变一遍
    # —— 上一版与上上一版分别写死过 58.4 / 11.4 / 240.2 / 240.2 与 31.6 / 4.7 /
    # 119.4 / 178.9 两套，都过期了，而注释过期没有任何东西会报错。
    # 要复算就跑一次现算的那份（页面上印的也是它）：
    #   python3 -c "import importlib.util as u; s=u.spec_from_file_location('m','build/specs/lseg.py'); \
    #               m=u.module_from_spec(s); s.loader.exec_module(m); \
    #               print(m._scale_gap_txt('tradeweb_adv_eu_govt_bonds_usd_bn', \
    #                                      'tradeweb_adv_other_govt_bonds_usd_bn')); \
    #               print(m._median_drawn('tradeweb_adv_us_govt_bonds_usd_bn'), \
    #                     m._median_drawn('tradeweb_adv_mortgages_usd_bn'))"
    {'zh': 'Tradeweb 利率现金分项 ADV·美国国债与按揭', 'cols': [
        {'col': 'tradeweb_adv_us_govt_bonds_usd_bn', 'zh': 'Tradeweb 美国国债 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
        {'col': 'tradeweb_adv_mortgages_usd_bn', 'zh': 'Tradeweb 按揭 ADV',
         'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    {'zh': 'Tradeweb 利率现金分项 ADV·欧洲国债与其他政府债（同单位合图，同轴对读；'
           '其他政府债自己的同比见页尾「水平值与单月同比」那张）',
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
# 起因（2026-08-07 渲染核查）：CONTRACT §6.1 第 5 条「近零基数不画同比」在**图上**
# 落实了（这些列全在多列桶里，画的是 lines，没有次轴同比），但 Exhibit 1 汇总表照印
# y/y —— 最刺眼的是主板新上市募资额「本月 0、去年同月 2 GBP mn」印成 −100.0%。
#
# 这不是页面自相矛盾：CONTRACT §6.3 把「汇总表的 m/m 与 y/y 两列」明确列为豁免
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

# ── LCH 三条腿的历史长度与「图上到底有几条同比金线」：全部现算 ─────────────
# ⚠️ 上一版这段印的是「12 期连 13 期的点对点同比都算不出，24 期的滚动同比也只有
# 一个点、连不成线；所以 LCH 的 18 列本轮一律只读水平值；再跑满一年，SwapClear 与
# RepoClear 才自然长到 24 期」。24 / 25 期是 **12 个月滚动同比**的门槛，2026-09 全站
# 改单月之后按它反推出来的这几句全部作废（单月同比 13 期就有第一个点）；而「一律只读
# 水平值」当场被同一页证伪 —— ForexClear 与 RepoClear 那几张单列成桶的图上确确实实
# 画着次轴金线。所以整段改成现算：期数每个月都在长，写死的话下个月又是一句假话。
_LCH_LEGS = (('ForexClear', 'forexclear_notional_registered_usd_tn'),
             ('RepoClear', 'repoclear_ltd_cleared_trade_sides_count'),
             ('SwapClear', 'swapclear_notional_registered_usd_tn'))

_LCH_MOM_COLS = ('forexclear_notional_registered_usd_tn',
                 'forexclear_trades_registered_count',
                 'repoclear_ltd_cleared_trade_sides_count',
                 'repoclear_sa_cleared_trade_sides_count')


def _lch_hist_zh():
    """LCH 三条腿各有多少期、图上有几条同比金线 —— 一个数都不写死。"""
    legs = []
    for zh, col in _LCH_LEGS:
        n = _n_obs(col)
        legs.append(f'{zh} {n} 期' if n else f'{zh}（期数读不到）')
    drawn = sum(1 for c in _LCH_MOM_COLS if _mom_drawn(c))
    return ('<b>后果：这几条腿的同比线都很短。</b>单月同比要 <b>13 期</b>才有第一个点。'
            '本页实测 ' + '、'.join(legs) + ' —— '
            + (f'页面上单列成桶的 LCH 图里有 <b>{drawn}</b> 张真的画出了次轴单月同比，'
               '每张只有很少几个点（各有几个点写在那张图自己的标题里），'
               '<b>斜率不要外推</b>；'
               if drawn else '目前没有任何一张 LCH 图画得出次轴同比；')
            + '其余 LCH 列同单位合图走折线，本来就没有次轴。'
              '<b>LCH 一列都不进 headline</b>：底座的发布门槛要 ≥24 个月共同历史，'
              '那是发页门槛，与同比口径无关。')


_NOTE_LCH = (
    '<b>LCH 的短历史是官方滚动窗口，不是起点设窄。</b>'
    'ForexClear 的月度 CSV 末行原文写着 <code>Row Count: 24</code>；'
    'SwapClear 的两张 datatable 各只有 12 行；RepoClear 的三张月度 grid 各 12 行 —— '
    '而同一页的<b>年度</b> grid 有 28 行、回溯到 1999，说明官方有更深的历史，'
    '但只以年度形式公开。官方每期只发这么一个窗口，本仓入库后永不删除，'
    '所以序列自己每个月长一期。'
    + _lch_hist_zh() +
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
    '<code>level_yoy</code> 都<b>只用当月合计口径的列本身</b>，一个 '
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
                'CONTRACT §6.3 是<b>豁免</b>的（那是运营核对表，读者拿它逐格对公司披露），'
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
        '<b>行名带 %s 的列：<u>图上</u>不画同比（CONTRACT §6.1 第 5 条），'
        '<u>汇总表</u>的 y/y 列照印（CONTRACT §6.3 豁免）—— 两套口径，不是打架，'
        '但两处必须分开读。</b>' % NEAR_ZERO_MARK
        + '<b>%s 出现在四个地方</b>：页顶「名词释义」的词条、汇总表（Exhibit 1）的行标签、'
        '该列所在图的序列名、末尾核对表的表头 —— 释义板那条只说「图上不画同比」一句，'
        '<b>判据与命中名单只写在这里这一处</b>。'
        '标记由 CSV 现算不写死：某列不再近零基数，%s 自己就掉了。' % (NEAR_ZERO_MARK,
                                                                    NEAR_ZERO_MARK)
        + '判据与实现都在 <code>build/yoy.py</code> 的 <code>near_zero_base()</code>：'
        '基期绝对值小于本序列|值|中位数 15% 的月份算「近零基数月」，'
        '<b>在图上画出来的那段窗口里</b>（左端 = 底座钉死的 <code>WIN_FROM</code>，'
        '本页 ' + _WIN_LEFT + '；右端 = 该列自己最后一个有值的月）'
        '占比 ≥ 1/12 → 整条序列别画同比。'
        '（窗口这一步很要紧，而且它<b>跟着图窗走</b>：图窗一变，'
        '哪些近零月「读者看得见」就跟着变，这份名单也跟着变 —— '
        '那不是判据变了，是画出来的月份变了。拿全历史计数则相反：'
        '一条早年近零、如今早已正常的序列会永远背着这个标记。）'
        '本页 import 期实测命中 <b>' + str(len(_NEAR_ZERO)) + '</b> 条：'
        + (names or '（无）') + '。'
        '<b>图上怎么落实</b>：靠<b>排版</b>而不是开关 —— 把它们放进 2–5 列同单位的组，'
        '底座对多列桶画的是折线（只有水平值、没有次轴同比），'
        '于是那条会跳到几百个百分点的金线根本不会被画出来。'
        '<b>汇总表（Exhibit 1）为什么不跟着压空</b>：CONTRACT §6.3 把「汇总表的 m/m '
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
    '当月合计，没有任何「日均还原成合计」的步骤 —— 金线就是柱除以 12 根之前那根柱。'
    '⚠️ <b>2026-09 之前这张画的是 12 个月滚动合计的同比</b>，与头条那两张'
    '（「Tradeweb 月成交额（全公司）：单月同比」「Tradeweb ADV（全公司）：单月同比」）'
    '读数不可比；现在三张同口径，可以直接对上。'
    '⚠️ <b>但「三张」里只有月成交额那一张与本图同列</b>'
    '（<code>tradeweb_volume_total_usd_tn</code>）：那张的同比柱与本图的金线'
    '<b>逐点是同一条序列</b>，差别只剩版式 —— 那张只画同比，本图把水平值柱与'
    '同比线合在一张图上。ADV 那张画的是<b>另一列</b>'
    '（<code>tradeweb_adv_total_usd_bn</code>，日均），同口径但不是同一个数。'
)

_NOTE_TTM_ORDERBOOK = (
    '<b>柱与线取自同一列同一口径</b>：<code>lse_orderbook_value_gbp_m</code> 是月报 '
    'MTD 区块的当月合计，不是日均，所以这里没有乘回交易日数这一步'
    '（乘回去会撞上口径坑 B：官方把 £m 四舍五入到整数，'
    '「ADV × 交易日 vs 月合计」的残差约 9.1e-4，远超底座 1e-6 的对账阈值）。'
    '⚠️ 这是<b>慢腿</b>：它的最新月比本页数据月早两三周，图的右端因此比头条那几张短一截。'
)

_NOTE_TTM_OTHER_GOVT = (
    '<b>这张是「其他政府债 ADV」<u>唯一</u>的同比图。</b>'
    '本列有 ' + str(_n_obs('tradeweb_adv_other_govt_bonds_usd_bn')
                    or '（读不到 CSV，期数未知）') + ' 期。'
    '该列在「欧洲国债与其他政府债」那一组里与欧洲国债同单位合图（'
    + _scale_gap_txt('tradeweb_adv_eu_govt_bonds_usd_bn',
                     'tradeweb_adv_other_govt_bonds_usd_bn') +
    '），底座画折线 —— 只有水平值、没有次轴同比，所以同比只在本图上。'
    '⚠️ <b>2026-09 之前本图画的是 12 个月滚动合计的同比</b>；改成单月之后，'
    '本列是<b>日均</b>（ADV）这件事反而变成好处：日均口径本身已经把「这个月多开了'
    '几天市」除掉了，金线是日均除以去年同月的日均，<b>一步还原都不需要</b> ——'
    '从前的滚动合计要把 12 个日均等权相加，那一步在本页没有分项级的交易日权重列'
    '（Tradeweb 那列加权天数是<b>集团级</b>的，不是这一个分项自己的天数），'
    '始终是个近似。现在这个近似整个消失了。'
)


# ── 「水平值 + 次轴单月同比」那几张（底座 kind='level_yoy'，一律排在页尾）────────
# **必须定义在这里、而不是写在 SPEC 里**：页尾 `_NOTE_MOM_WHY` 要说「与页尾那几张
# 图注里底座那段同源」，而「那几张」是几张只能现数这个列表 —— 上一版在页注里写死
# 「三张」（再上一版写死「Exhibit 59 / 60」，当时页面上其实有 58/59/60 三张，
# 漏了一张）。列表长度是这一页唯一说得准的判据，所以把定义提到用它的地方之前。
#
# ⚠️ 这三张 2026-09 之前画的是 12 个月滚动同比（字段名当时叫 `ttm_yoy`）。改成单月
# 之后要防的是**与别处重复**：三条 level 列在 groups 里分别落在 3 列桶、3 列桶、
# 2 列桶里 —— 多列桶底座一律画折线组图（没有水平值柱、没有次轴同比），
# 所以这三张仍是各自那一列唯一的「柱 + 同比」。
# （若哪天有人把其中一列挪进**单列**桶，那个桶会画出一张一模一样的 gs_bar，
#  必须同时把这里对应的那条删掉。）
# ⚠️ **但「不与谁重复」只对「柱 + 同比」这个图型成立。** 第一条的 level 列
# `tradeweb_volume_total_usd_tn` 同时是**头条列**，而头条列自带一张
# `grouped_bars` 的「：单月同比」——2026-09 改口径之后那张的柱与本条金线
# **逐点是同一条序列**（改口径前一张单月、一张滚动，各有各的用处）。
# 底座 `ex_level_yoy` 的护栏只拦「level_yoy ∩ groups 单列桶」，拦不到头条这条路。
# 这件事已经写进 `_NOTE_TTM_TRADEWEB`，读者不会以为那是两个不同的数；
# 要不要合并成一张由页面所有者决定，spec 侧不擅自删图。
_LEVEL_YOY = [
    {'zh': 'Tradeweb 全公司成交额',
     'level': {'col': 'tradeweb_volume_total_usd_tn', 'zh': '当月成交额',
               'unit': 'USD tn/month', 'fmt': 'f1'},
     'note': _NOTE_TTM_TRADEWEB},

    {'zh': 'LSE 主板订单簿成交额',
     'level': {'col': 'lse_orderbook_value_gbp_m', 'zh': '当月成交额',
               'unit': 'GBP mn/month', 'fmt': 'f0c'},
     'note': _NOTE_TTM_ORDERBOOK},

    {'zh': 'Tradeweb 其他政府债 ADV',
     'level': {'col': 'tradeweb_adv_other_govt_bonds_usd_bn', 'zh': '当月日均成交额',
               'unit': 'USD bn/day', 'fmt': 'f1'},
     'note': _NOTE_TTM_OTHER_GOVT},
]


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


# ── 单列柱图两端那根柱的数值贴着轴刻度：只讲症状与成因，**不在页面上点名单** ──────
# 这条与 _NOTE_AXIS_SCALE 是同一类东西（几何缺口，spec 侧修不了），所以挨着放。
#
# 症状：单列柱图画在两端的那根柱，柱顶数值标签的一半伸进轴刻度那一列，
# 与恰好同高的那根刻度叠在一起（末柱压右轴、首柱压左轴）。
#
# ⚠️ **为什么这里不写「涉及哪几张」** —— 不是懒，是本文件算不准，任何名单都只能靠人肉维护：
#   · 权威判据是构建期 `chartscale.audit()` 打印的 ⚠️ 行，而 audit 量的是
#     `chartscale.fix_all()` **显示缩放跑完之后**的标签；缩放倍数按「列 ↔ 图」二部图的
#     **连通分量**定，是整页范围的计算，本文件（只看得见自己这一列）复现不了。
#   · 实测过这条路走不通：在本文件里用 `mrwin.layout()` + `mrwin.label_clash()`
#     逐列复算（与 audit 同一把尺子 `chartscale._budget`），2026-08-19 得到 5 张 gs_bar，
#     比构建期实报的 4 张多出「主板/AIM 总市值」那一张 —— 它在真实 payload 里被缩放成
#     「（千）」之后标签就够短了。同一把尺子、不同的输入，名单就分叉。
#   · 历史上这份名单已经过期两次（上一版写「三张」漏了 Turquoise 泛欧成交份额；
#     再上一版写死的是另外三张）。写死一次就会过期一次，而页面不会因此报错。
#   ⇒ 当期究竟命中哪几张，跑 `python3 build/single.py lseg` 看 ⚠️ 行 —— 那份名单
#     跟着数据走。页面上只讲「看见这个不是渲染出错」，那句话与图号无关，不会过期。
#
# 成因（照 assets/charts.js 复算）：柱顶标签居中钉在 Xc(i) 上，轴刻度画在绘图区边缘
# 外侧 fscale(6) 处 ⇒ 标签总宽的预算 = band + 12 − 2 × LAB_GAP（`chartscale._budget`）。
# 期数越多 band 越窄，而标签字号只随卡片宽度走、不随 band 缩，于是预算先被吃穿。
#
# 为什么不动小数位：spec 侧能把标签变短的杠杆都是「把数写短」这一类 —— 砍 `fmt` 的
# 小数位，或者给列加 `scale` 换个量级。两条都会连**末尾核对表**一起改掉，而这几列的
# fmt 恰好就是源表自己的精度（series/lseg.csv 里份额存 1 位、加权交易日数存 2 位），
# 核对表的用途正是与官方披露逐格对账，动了就对不上那一格。
# （上一版页面上还写着第二条理由「砍完仍然压，只是掉到检测门限以下」—— 那句话是对
#  **旧的那份三列名单**在 768px 下量的，名单换过之后没有人重量过；而按构建期那把尺子
#  复算，pct1→pct0 / f3→f2 / f2→f1 之后那几张都回到了预算之内。
#  一句没复算过的实测不留在页面上。）
# 真正的修法在共用引擎：charts.js 已经为「次轴末点读数 vs 右轴刻度」写了一段
# 「刻度让位」（`dropClashingTicks`，撞上就把那根刻度删掉），只是没把柱顶数值标签也算进
# priorityLabs。本轮不改共用件，所以这条缺口留在页面上，写出来免得读者当成渲染出错。
def _src_dec_zh():
    """「series/lseg.csv 里份额存 1 位、加权交易日数存 2 位」—— 位数现数 CSV，不写死。

    这是「不能砍小数位」那条理由的**依据**：说源表存几位，就得真去数源表存几位。
    数的是该列所有取值里小数位最多的那个（官方会把 65.0 印成 65，看单个值会数少）。
    """
    bits = []
    for col, zh in (('lse_lit_uk_share_pct', '份额'),
                    ('tradeweb_trading_days_blended', '加权交易日数')):
        d = 0
        for r in _ROWS:
            v = (r.get(col) or '').strip()
            if '.' in v:
                d = max(d, len(v.split('.', 1)[1]))
        bits.append('%s存 %d 位' % (zh, d))
    return '<code>series/lseg.csv</code> 里' + '、'.join(bits) if bits else '见 CSV'


def _last_bar_label_note():
    return (
        '<b>单列柱图<u>两端</u>那根柱的柱顶数值，会与轴刻度贴在一起。'
        '这不是渲染出错，也不是两个数粘成了一个 —— 一个是这根柱的值，'
        '另一个是轴刻度，两个都是对的。</b>'
        '成因是几何：柱顶数值居中钉在自己那根柱上，而两端那根柱的柱心离绘图区边缘'
        '只有半格宽，轴刻度就画在边缘外侧一点点（末柱对右轴、首柱对左轴，'
        '同一个算式的两头）。一张图上塞的期数越多，一格柱越窄，'
        '而标签的字号只随卡片宽度走、不跟着 band 缩'
        '（<code>assets/charts.js</code>），于是标签有一半伸出了绘图区；'
        '窄屏（单栏）比宽屏更明显，同一个原因。'
        '<b>本轮没有把它压下去</b>：spec 侧能把标签变短的杠杆都是「把数写短」这一类 ——'
        '砍列的 <code>fmt</code> 小数位，或者给列加 <code>scale</code> 换个量级；'
        '两条都会连<b>末尾核对表</b>一起改掉。而本页这类柱图的位数往往就是源表自己的精度'
        '（' + _src_dec_zh() + '），'
        '核对表的用途正是与官方披露逐格对账，动了就对不上那一格。'
        '<b>真正的修法在共用引擎</b>：<code>charts.js</code> 已经为次轴末点读数写了'
        '「撞上就让刻度让位」的逻辑（<code>dropClashingTicks</code>），'
        '只是没把柱顶数值也算进去；本轮不改共用件，所以这条缺口仍在页面上。'
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
    '水平值与单月同比」那张）：图上约 147 读作 <b>£1,470 亿/月</b>。'
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

def _level_yoy_count_zh():
    """「页尾 N 张『水平值与单月同比』」—— 张数现数 `_LEVEL_YOY`，不写死。

    上一版写死「三张」，再上一版写死「Exhibit 59 / 60」而页面上其实有三张 ——
    同一句话已经错过两轮。这里改成数列表：加一条 level_yoy 这句话自己跟着变。
    """
    n = len(_LEVEL_YOY)
    if n == 2:                       # 量词前用「两」不用「二」
        return '两张'
    return ('%s张' % '一二三四五六七八九十'[n - 1]) if 1 <= n <= 10 else ('%d 张' % n)


def _win_same_zh():
    """「底座那段与图上那段是不是同一段窗口」—— 现判，不假设。

    底座的 `level_yoy` 图注量的是**整条序列**（`self.df.index` 全长），本文件的
    `_ev_long()` 量的是 `_drawn_window()`（左端 = max(CSV 首月, WIN_FROM)）。
    两者相等**只在 CSV 首月不早于 WIN_FROM 时成立** —— 今天成立（两者都是 2016-01），
    但 series/lseg.csv 哪天补进更早的历史就不成立了，而页面不会因此报错。
    所以这里按 CSV 现判，两种情况各写各的话。
    """
    first = _ROWS[0]['month'] if _ROWS else None
    if not first or not _WIN_FROM:
        return '（窗口是否同一段本次判不了：读不到 CSV 首月或底座的 WIN_FROM。）'
    if first >= _WIN_FROM:
        return ('窗口也是同一段 —— 本页 CSV 首月（' + first + '）不早于底座钉死的 '
                '<code>WIN_FROM</code>（' + _WIN_FROM + '），'
                '所以底座量的整条序列与图上画出来的那段重合。')
    return ('<b>窗口不同</b> —— 本页 CSV 首月（' + first + '）早于底座钉死的 '
            '<code>WIN_FROM</code>（' + _WIN_FROM + '），底座量的是整条序列、'
            '下面量的只是图上画出来的那段（左端 ' + _WIN_LEFT + '），'
            '两侧的数因此不该互相印证。')


def _mom_why_note():
    """页尾那条「用了单月同比的图，逐张写明理由 + 本序列实测」。

    为什么写成函数而不是常量：每一段里的数都由 `_ev_long()` 现算，
    一个都不写死 —— 换个月、换条数据，页面上的辩护跟着变；理由站不住了要能自己露出来。
    字符串一律用拼接不用 `%` 格式化：`_ev_long()` 回来的正文里带百分号。
    """
    return (
        '<b>本页同比只有一种口径：单月</b>（当月对去年同月，本列除本列）——'
        '<b>页面所有者指定，全站统一</b>。'
        '2026-09 之前本页并存两种：页尾三张「水平值与 12 个月滚动同比」走滚动，'
        '其余走单月，页尾这一条当时的用途是<b>逐张替单月同比辩护</b>'
        '（CONTRACT §6.1 曾把滚动定为流量的默认）。'
        '现在辩护没有对象了，这一条改为做另一件事：'
        '<b>逐条报出用单月口径要付的代价，拿本序列自己实测</b> ——'
        '<code>yoy.describe(yoy.caliber_diff(s, kind, win))</code> 现算，不引别家的例子。'
        '<b>下面所有「12 个月滚动」的数都只是对照，页上一张滚动图都没有。</b>'
        '<b>⚠️ 本页够不到图注</b>：单列柱图（<code>gs_bar</code>）与头条同比图'
        '（<code>grouped_bars</code>）的 <code>note</code> 整段由 '
        '<code>build/single.py</code> 的 <code>ex_single()</code> / <code>ex_yoy()</code> '
        '拼装，spec 侧一个字都插不进去（<code>COL_KEYS</code> 与 <code>groups</code> 的'
        '允许键里都没有 note 这一项）。所以理由与一句话实测写进<b>标题</b>'
        '（组名会原样印进图标题），完整实测段落列在下面。'
        '<b>这是妥协不是等价物：要让实测段真的落进每张图自己的图注，必须改底座。</b>'
        '实测口径与页尾' + _level_yoy_count_zh() + '「水平值与单月同比」'
        '图注里底座那段<b>同源但不全同</b>：'
        '同一条序列、同样先取两种口径的<b>交集</b>再比；' + _win_same_zh() +
        '<b>还有一处差别在相邻月跳变这一项</b> —— 底座报的是最大值，下面报的是中位数，'
        '两个数不该互相印证。'

        '① <b>两张头条同比图</b>（Tradeweb 月成交额 / Tradeweb ADV 的「：单月同比」）：'
        '与页顶数据条、汇总表 y/y 列同口径，逐月核对当月读数用。'
        '月成交额那一列在页尾还有一张「水平值与单月同比」（柱 + 金线合一），'
        '两张<b>同口径、不同版式</b>，读数可以直接对上 ——'
        '2026-09 之前页尾那张画的是滚动口径，两张读数不可比。'
        '月成交额：' + _ev_long('tradeweb_volume_total_usd_tn') +
        'ADV：' + _ev_long('tradeweb_adv_total_usd_bn') +
        '<b>⚠️ 剩下的缺口（本轮没修）：这两张<u>标题里已经写了「单月」</u>'
        '（底座 <code>build/single.py</code> 的 <code>ex_yoy()</code> 现在写的是 '
        '<code>title = f\'{c["zh"]}：单月同比\'</code>），'
        '§6.6 自动判据里「单月同比没写进标题」那一条已经满足；缺的是 <b>§6.1 第 3 条</b>'
        '要的那一半 —— 每一张画同比的图都要<u>在自己的图注里</u>印出单月口径的代价，'
        '而这两张的图注里没有上面这两段实测。</b>那段图注同样由 <code>ex_yoy()</code> 拼装、spec 侧插不进字，'
        '而头条列在 spec 里只有 col / zh / unit / fmt 四个允许键：'
        '往 <code>zh</code> 里塞字能改到标题，但同一个 <code>zh</code> 还会印到'
        '页顶数据条、汇总表行标签、末尾核对表表头，以及同一列自己的'
        '「全历史与近 3 年分位带」与「与同月常态比」两张图的标题上 ——'
        '那几处画的都不是同比，不该带口径词。'
        '所以本轮<b>不改</b>，缺口留在这里明写：要补必须动 <code>ex_yoy()</code>。'
        '在补上之前，这两张图的实测以本条为准。'

        '② <b>两张成交份额</b>（LSE 英国 Lit、Turquoise 泛欧）：比率不做滚动合计也不做'
        '滚动均值（§6.1 第 4 条），单月的<b>百分点差</b>是它唯一合法的口径 ——'
        '这两张<b>不是本轮改的</b>，它们从来就是单月。'
        'LSE 英国 Lit：' + _ev_long('lse_lit_uk_share_pct', ratio=True) +
        'Turquoise 泛欧：' + _ev_long('turquoise_paneuropean_share_pct', ratio=True) +

        '③ <b>GBP/EUR 换算率</b>：换算常数不是流量，把 12 个月的汇率加起来不指代任何东西 ——'
        '同样不是本轮改的，它从来只有点对点这一种口径。'
        + _ev_long('gbp_eur_rate', ttm_meaningless=True) +

        '④ <b>Tradeweb 集团加权交易日数</b>：命题本身就是「这个月比去年同月多开几天」，'
        '滚动窗口正好把要看的东西抹平 —— 这一张<b>就算全站是滚动口径也得用单月</b>，'
        '所以它也不是本轮改的。'
        '下面这组数就是「抹平」的量化 —— 滚动侧的标准差与相邻月跳变小到接近于说'
        '「什么都没发生」，而要看的正是被它抹掉的那部分：'
        + _ev_long('tradeweb_trading_days_blended') +

        '⑤ <b>LCH ForexClear 两张</b>：这条腿的历史被官方滚动窗口卡住'
        '（月度 CSV 末行原文 Row Count: 24）—— 这在从前是「只能用单月」的理由，'
        '现在全页都是单月，它变成一句<b>关于线有多短</b>的提醒。'
        '名义额：' + _ev_long('forexclear_notional_registered_usd_tn') +
        '笔数：' + _ev_long('forexclear_trades_registered_count') +
        '标题里那句长度描述由 <code>_short_hist_why()</code> 按期数<b>现算</b>：'
        '官方窗口一变长它自己跟着变，不写死。'

        '⑥ <b>Tradeweb 其他政府债 ADV</b>（'
        + str(_n_obs('tradeweb_adv_other_govt_bonds_usd_bn') or '？') + ' 期）：'
        '它在「欧洲国债与其他政府债」那一组里与欧洲国债同单位合图（'
        + _scale_gap_txt('tradeweb_adv_eu_govt_bonds_usd_bn',
                         'tradeweb_adv_other_govt_bonds_usd_bn') +
        '），底座画折线 —— 只有水平值、没有次轴同比；<b>它的同比只在页尾那张'
        '「水平值与单月同比」上</b>（2026-09 之前那张画的是滚动口径）。'
        '这一列的单月口径毛刺不小，读的时候要连着柱高一起看 —— '
        + _ev_long('tradeweb_adv_other_govt_bonds_usd_bn') +

        '⑦ <b>一级市场的增发笔数</b>（主板 ' + str(_n_obs('mm_further_issues_count') or '？')
        + ' 期 / AIM ' + str(_n_obs('aim_further_issues_count') or '？') + ' 期）'
        '原先各自单列成柱图、各带一条同比线；上一轮已把两列并成同单位的一张折线图，'
        '页面上不再出现那两条同比线 —— 逐月的发行事件计数是小整数，'
        '同比在这种序列上主要是分母的故事。'

        '⑧ <b>LCH RepoClear 的两列清算边数</b>目前只有 ' + _repo_sides_n_zh() + '，'
        + _repo_sides_mom_zh() +

        '<b>存量列的次轴同比不在本条范围内</b>：那是点对点同比，'
        '按 §6.1 第 2 条本来就是存量的默认口径，不需要辩护。'
    )


_NOTE_MOM_WHY = _mom_why_note()


# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（payload 的 `glossary`，排在所有 exhibit 之前）
# ══════════════════════════════════════════════════════════════════════════════
# （原先这里有个 `_near_zero_thresholds()`，从 build/yoy.py 现取那两个门槛给 † 那一条用。
#  † 的判据现在只写在页尾 `_near_zero_note()` 里，释义板只留一句指路 ——
#  这个取数函数没有调用方了，一并删掉，免得留一段死代码。
#  两个门槛的唯一出处仍是 build/yoy.py 的 `NEAR_ZERO_BASE_FRAC` / `NEAR_ZERO_SERIES_SHARE`。）


def _primary_gap_zh():
    """「主板 / AIM」那一条里两段列的起点 —— 现算（同 `_primary_span_txt()` 的理由）。

    2026-08-19 把 AIM 从 2017-01 推到 2016-01 时，写死的「16 个月」当场变成假话。
    算不出就返回空串，那半句话整个不写（少一个数不是缺陷，写死一个才是）。
    """
    a_first = _col_span('aim_companies_eop_count')[0]
    m_first = _col_span('mm_companies_eop_count')[0]
    if not a_first or not m_first:
        return ''
    gap = ((int(m_first[:4]) - int(a_first[:4])) * 12
           + int(m_first[5:7]) - int(a_first[5:7]))
    return ('两段列的<b>起点差 %d 个月</b>（AIM %s 起、Main Market %s 起）：'
            % (gap, a_first, m_first))


def _glossary(page):
    """页顶「名词释义」。`page` 是 build/single.py 的 Page 对象（本函数只用来对齐签名）。

    与 brief 的分工（CONTRACT §1）：brief 说「**这个月**这组读数该怎么读」、每月重写；
    这里说「**这些词**是什么意思」、一年到头是同一段 ⇒ **一个当月读数都不出现**。

    正文里出现的数，逐个交代（把话说满会让下一个审的人不去核）：
      · **随月份变的数：一个都没有。**
      · **会随时间变、所以现算的：一个** —— 一级市场两段列的起点差，
        `_primary_gap_zh()` 从 series/lseg.csv 现算（2026-08-19 把 AIM 的起点
        从 2017-01 推到 2016-01 时，上一版写死的「16 个月」当场变成假话）。
      · **两处定值，照抄本页既有 note，不随月份变**：底座量价对账的硬失败阈值
        `1e-6`（出处 `_NOTE_NO_DECOMP_TRADEWEB`；机器上是 build/single.py 的
        `TOTAL_TOL`，那是底座常量，不随本页数据变）；
        Main Market 老版式「4 列根本没有对应来源」（出处 `_NOTE_PRIMARY` ③ 的
        「13 列里 4 列无源、1 列口径不同」）。两处都是历史事实/机器阈值，
        不会因为多取一个月而变；要核就核这两条 note。
      · † 那两个门槛（15%、1/12）**已经不在这一板里**了 —— 只写在页尾
        `_near_zero_note()` 一处，见下面那条的注释。

    ── 为什么是这 16 个词（选词的判断写在这里）────────────────────────────────
    判据只有一条：**不看定义就会把这一页读错**。本页 60 张图、86 列、四条互不相干的
    官方腿，最容易读错的不是生僻词，而是**同一个中文词在不同腿上口径不同**：

      · 三处 ADV 的分母不是同一种天数（整数交易日 / 反推的加权天数 / 自然日）
        ⇒ 「ADV」「交易日数」
      · 两条成交份额的分母不是同一个盘子（英国 lit vs 泛欧 lit+dark）
        ⇒ 「成交份额」；Turquoise 两行的官方行名换过两次 ⇒ 「Integrated / Dark」
      · Tradeweb 的 Rates 是**资产类别名**不是费率，全电子只是信用债的一个子集
        ⇒ 「Rates / Credit」「全电子」
      · LCH 三条腿的边数口径互不相同（双边 / 边数 / novation 后组合），
        客户腿不能拿合计减出来，月末存量不能跨月相加，两个法人没有官方月度合计
        ⇒ 「名义额」「双边计 / 清算边数」「客户腿」「月末存量 / 未平仓」「LCH Ltd / LCH SA」
      · 一级市场的 New Issues 不等于 IPO，两段列起点不同、各有一个官方的洞
        ⇒ 「新上市 / 增发」「主板 / AIM」
      · 页面上唯一的派生量 ⇒ 「每笔平均成交额」；一列不是拿来看汇率的换算率
        ⇒ 「GBP/EUR 换算率」；行名末尾那个记号 ⇒ 「†（近零基数）」

    **不收**的两类：① `m/m`、`y/y`、`3Y %ile`、pp/bp 这类全站通用读图约定 ——
    汇总表的 `summary.note` 已经逐条讲过，释义板再讲一遍就是两处各写一份，
    而两份迟早会不同步；② 本页没有特定口径的常识词（成交额、市值、上市公司家数）。

    每一条的口径都与本页既有的 notes / 图注**同源**（notes 是逐条核过的），
    出处逐条写在下面的注释里；查不到出处的断言一句都不写。
    """
    G = []                                   # (dt, dd) —— 顺序即页面上的顺序

    # ── 交易与份额（orderbook 腿 + Tradeweb 的分母）────────────────────────
    # 出处：fetch/lseg_orderbook.py 口径坑 5（日均 = 月合计 ÷ 各自交易日数）、
    #       _NOTE_NO_DECOMP_TRADEWEB（两条腿的实测残差与 1e-6 硬失败阈值）。
    G.append(('ADV',
              '日均成交额 / 日均成交量（average daily volume）。口径上是'
              '<code>当月合计 ÷ 当月交易日数</code>，但本页三处 ADV 的<b>分母不是同一种天数</b>'
              '（见下一条），Tradeweb 那条更是官方直接披露、天数反过来是<b>反推</b>出来的。'
              '⚠️ 官方把「当月合计」与「ADV」<b>分别披露</b>、各自四舍五入'
              '（LSE 月报的成交额只印到 £m 整数、Tradeweb 的加权天数只印到两位小数），'
              '所以本页把两者当<b>两条并列的序列</b>：'
              '<b>不把这两条绑成一对量价因子</b>，'
              '也<b>不要拿一条乘除另一条去对账</b> —— 实测残差远超底座 1e-6 的对账阈值，'
              '硬绑上去整页会构建失败。'
              '（本页那张「增长的量价分解」用的是<b>另一对列</b>：订单簿的成交额与成交笔数，'
              '与这里说的「合计 vs ADV」无关。）'))

    # 出处：fetch/lseg_orderbook.py 坑 5（两套日历）、fetch/lseg_tradeweb.py 坑 2
    #       （blended = 月成交额 ÷ 月 ADV，ICD Portal 按自然日）、页尾 _NOTE_NEITHER。
    G.append(('交易日数',
              '本页有<b>两种性质完全不同</b>的交易日数，<b>不可同轴比较</b>。'
              '① <b>LSE 与 Turquoise 各数各的</b>整数交易日 —— Turquoise 跟的是泛欧日历，'
              '同一个月两者可以不等；日均一律用<b>自己那一列</b>的天数去除，'
              '别拿 LSE 的天数去除 Turquoise 的成交额。'
              '② <b>Tradeweb 加权交易日数</b>（blended）是<code>月成交额 ÷ 月 ADV</code>'
              '<b>反推</b>出来的集团级加权天数，<b>不是整数、也不是日历事实</b>：'
              'Tradeweb 各产品的分母天生不同（其他货币市场按<b>自然日</b>平均余额、'
              '回购按抵押品名义额），集团级那个数是它们的加权结果。'
              '三列都<b>不要跨月相加</b>。'))

    # 出处：_NOTE_ORDERBOOK ③（两条份额的分母不是同一个盘子）。
    G.append(('成交份额',
              '本页两条份额的<b>分母不是同一个盘子</b>：LSE 那条的分母是「英国 Lit 订单簿」'
              '（<b>lit</b> = 盘上公开显示报价的可见订单簿，<b>不含暗池</b>），'
              'Turquoise 那条是「泛欧 Lit + Dark」（<b>把暗池也算进分母</b>）。'
              '地理范围（英国 / 泛欧）与含不含暗池<b>两处都不同</b>。'
              '⇒ 两个百分数<b>不能相加，也不能互比高低</b>，'
              '本页刻意用两个不同的单位串把它们分成两张图。'
              '两条都是<b>官方月报自印</b>的，本页不自算分母、也不做任何加总。'))

    # 出处：fetch/lseg_orderbook.py 首段与坑 2（Turquoise 分 Integrated 与暗池；
    #       暗池行名 MidPoint → Plato™ → Dark 是同一条腿改名）、_NOTE_BREAKS。
    G.append(('Integrated / Dark',
              '官方月报把 Turquoise 拆成 <b>Integrated</b>（订单簿）与 <b>Dark</b>（暗池）'
              '两行，本页照原样分列、<b>不合并</b>。'
              '⚠️ Dark 那一行的官方行名换过两次（MidPoint → Plato™ → Dark），'
              '取数腿逐期核对确认是<b>同一条腿改名</b>、不是口径变化，'
              '所以页面上<b>不画断点线</b> —— 红色竖线的语义是「线左右不可比」，'
              '用在这里恰好说反。'))

    # 出处：_NOTE_DECOMP（那张分解图自己的图注，本页唯一的派生量）。
    G.append(('每笔平均成交额',
              '本页<b>唯一</b>的派生量，<b>不是公司披露的数</b>：'
              '<code>订单簿成交额 ÷ 订单簿成交笔数</code>，只出现在那张量价分解图上。'
              '它衡量的是<b>订单碎片化程度</b>（一笔委托被拆成多少笔成交），'
              '<b>把它叫「价」是错的</b>：算法交易把大单拆细会让这个数一路走低，'
              '而同期标的价格完全可以在涨。'))

    # ── Tradeweb 腿 ────────────────────────────────────────────────────────
    # 出处：_NOTE_TRADEWEB_CALIBER ①（资产类别名不是费率）。
    G.append(('Rates / Credit',
              'Tradeweb 列名里的 Rates / Credit / Equities / Money Markets 是'
              '<b>资产类别名</b>，不是「费率」「信用」这类含义 —— '
              '把 <code>Rates ADV</code> 当成一个比率读会差一个数量级。'
              'Rates / Credit / Equities 三个类别下面再按「现金」（cash，现券/现货）与'
              '「衍生品」（derivatives）分成两支，Money Markets 则拆成回购与其他，'
              '本页按这个层级分图。'))

    # 出处：fetch/lseg_tradeweb.py 口径坑 5（Credit Total 与「全电子」口径不是一回事）。
    G.append(('全电子',
              'Tradeweb 把美国信用债的成交分成「<b>全电子</b>（fully electronic）」与'
              '「electronically processed」（线下成交后再上平台处理）两种，'
              '本页只收<b>全电子</b>那两列（美国投资级 / 美国高收益）。'
              '⇒ 这两列<b>加不出</b> Tradeweb Credit ADV：后者还装着现券的非全电子部分、'
              '信用衍生品与其他品种 —— 两处对不上<b>不是算错</b>。'))

    # ── LCH 腿 ─────────────────────────────────────────────────────────────
    # 出处：fetch/lseg_lch.py 口径坑 1（RepoClear 官方自述 "sum of contracts' bond
    #       nominal value cleared"）、fetch/lseg_tradeweb.py 坑 6（名义本金、
    #       按揭按 current face value、回购按抵押品名义额）。
    G.append(('名义额',
              '合约<b>面值</b>口径的规模度量，<b>不是</b>任何一方实际交付或结算的金额，'
              '也<b>不是</b>风险敞口。LCH 三条腿的规模都以名义额计'
              '（RepoClear 官方自述是「已清算合约的债券名义面值之和」，'
              '它另印一列并列的「现金额」，本页照原样分两列不合并）；'
              'Tradeweb 的成交额同样是<b>名义本金</b>口径'
              '（按揭按 current face value、回购按抵押品名义额）。'
              '⇒ 它与交易所的「成交金额」不是同一种量，跨家横比之前先对口径。'))

    # 出处：fetch/lseg_lch.py 口径坑 1（三条腿的官方原文各不相同）、
    #       spec 口径坑 C（官方术语是 trade sides，不是 trades）、_NOTE_LCH。
    G.append(('双边计 / 清算边数',
              'LCH 三条腿的边数口径<b>互不相同，横向相加没有意义</b>。'
              'ForexClear 的月度 CSV 自述「成交量含每笔已清算交易的<b>两条腿</b>」'
              '⇒ <b>双边计</b>；RepoClear 的名义额自述 double counted，'
              '它那两列「<b>清算边数</b>」（trade sides）数的是<b>边</b>不是笔 —— '
              '官方用的就是 sides 这个词，别当成成交笔数；'
              'SwapClear 的合计列则是 novation 之后的<b>组合</b>口径。'))

    # 出处：fetch/lseg_lch.py 口径坑 1（"Only the client side of each trade is
    #       included in the Client Clearing Volumes"，且 novation 口径下不做减法）。
    G.append(('客户腿',
              'SwapClear 的 Client Clearing Volumes：官方原文只把<b>每笔交易的客户那一边</b>'
              '算进去；与它并列的合计列是 novation 之后的<b>整个组合</b>口径。'
              '⇒ 两列<b>不是「总量」与「其中一部分」的包含关系</b>，'
              '<b>不能相减</b>去得「自营 = 合计 − 客户」—— novation 口径下这个减法'
              '没有定义，本页也不做。'))

    # 出处：fetch/lseg_lch.py 口径坑 3（Outstanding 是报告期末快照，ForexClear
    #       的 *AtMonthEnd 同理）、底座 notes「存量与流量分开读」那一条。
    G.append(('月末存量 / 未平仓',
              '同一件事的两个官方叫法：SwapClear 叫 outstanding（月末存量）、'
              'ForexClear 叫 open interest（月末未平仓），'
              '两者都是<b>报告期末的一张快照</b>（官方方法论原文）。'
              '与它们并列的「新登记 / 当月清算」才是<b>当月流量</b>。'
              '⚠️ 存量<b>绝不能跨月相加</b>：把 12 个月末快照加起来不指代任何真实的量。'
              '本页把存量列一律单独成图，不与流量列共轴。'))

    # 出处：fetch/lseg_lch.py 口径坑 2 与 spec 口径坑 E（月度 grid 只有 LTD/SA 两列，
    #       没有 Total；Total 只在年度表里）。
    G.append(('LCH Ltd / LCH SA',
              '两个<b>独立法人</b>，不是两条产品线：LCH Ltd（伦敦）清英国金边债与部分欧债，'
              'LCH SA（巴黎）清欧元区主权债，两者规模差好几倍。'
              '⚠️ 官方的<b>月度</b>表只印这两列、<b>没有 Total</b>'
              '（合计只在年度表里有），自己加出来的月度合计是派生值、本仓不收 —— '
              '所以本页从头到尾分组分图，页面上<b>不会出现一条月度合计线</b>。'))

    # ── 一级市场腿 ─────────────────────────────────────────────────────────
    # 出处：_NOTE_PRIMARY ②③（两段列起点不同、各有一个官方自己的洞，各自只砸一个市场）。
    G.append(('主板 / AIM',
              'London Stock Exchange 的两个市场，官方各出一份 factsheet，'
              '本页<b>各存各的列、谁也不并进谁</b>。'
              + _primary_gap_zh() +
              'Main Market 更早的老版式里有 4 列<b>根本没有对应来源</b>、'
              '增发笔数又是另一套数法，硬拼等于在图上画一段假历史。'
              '各自的跨度里还各有一个<b>官方自己的洞</b>，而且<b>各自只砸一个市场</b> —— '
              '看图时别把某一条线的断点读成两个市场一起停摆。'))

    # 出处：_NOTE_PRIMARY ①④（New Issues 含转板/introduction/反向收购；
    #       募资额取逐笔明细专表，与 Summary 表的冲突留痕不自动吞）。
    G.append(('新上市 / 增发',
              '官方口径的「新上市」（New Issues）<b>不等于 IPO</b>：'
              '它含从另一个板转板、introduction 与反向收购，'
              '所以家数会<b>高于</b>财经媒体口径的 IPO 数。'
              '「增发」（Further Issues）则是已上市公司的后续发行。'
              '⚠️ 募资额在官方同一份工作簿里有两处（Summary 表与逐笔明细专表），'
              '少数月份对不上，本页一律取<b>明细专表</b>那一侧并把冲突留痕 —— '
              '所以拿这一页去对 Summary 表时会有差。'))

    # ── 杂项 ───────────────────────────────────────────────────────────────
    # 出处：_NOTE_NEITHER（收这一列是为了验证取的是英镑那一栏）、_NOTE_CCY（不做换算）。
    G.append(('GBP/EUR 换算率',
              'LSE 月报<b>自印</b>的那一列。收它<b>不是为了看汇率</b>：'
              '月报每一行印的是 [笔数, £m, €m] 三个数，而 €m 栏 = £m 栏 × 这一列 —— '
              '留着它，读者才能验证本页取的是<b>英镑</b>那一栏。'
              '<b>本页不做任何汇率换算</b>（三种币种同表并存，每张图按自己那一列的原币标注）。'
              '它既不是流量也不是存量，<b>不要跨月相加</b>。'))

    # 这一条**只给一句指路**，判据（两个门槛）、命中名单与「汇总表为什么照印」
    # 全部只写在页尾 `_near_zero_note()` 里 —— 同一件事写两处，两份迟早不同步
    # （上一版这里把那三段整段复述了一遍，其中一句还与页尾近乎逐字重复）。
    G.append(('†（近零基数）',
              '行名末尾的 †：这一列在<b>图上画出来的那段窗口</b>里近零基数的月份太多，'
              '所以<b>图上不给它画同比线</b>'
              '（那种同比是把一个接近零的分母放大成三位数，不是信息）。'
              '判据、本页的命中名单，以及<b>汇总表的 y/y 列为什么照印不留空</b>，'
              '都写在<b>页尾说明</b>里，那里只讲一次。'))

    return G

SPEC = {
    'ticker': 'lseg',
    'name':   'London Stock Exchange Group',
    'title':  '伦敦证券交易所集团（LSEG）月度经营指标',
    'csv':    'lseg.csv',
    # ⚠️ `ccy` 不是「集团财报的记账本币」，是**印在副标题与第 1 条 notes 上的那句话**
    # （底座的模板是「本币 {ccy}」，见 build/single.py 里 subtitle 与 notes 第 1 条的拼装处）。
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

    # ══ 水平值 + 次轴单月同比 ════════════════════════════════════════════════
    # 名单与条数见 `_TTM_YOY`（定义在上面，页注要报「页尾有几张」时现数它，不写死）。
    'level_yoy': _LEVEL_YOY,

    # notes 的顺序就是页面上的顺序，而底座会先塞 9 条自己的（数据源 / 数据月 / 慢腿 /
    # 存量与流量 / 图型规则 / 同比口径 / 汇总表 / 显示缩放 / 核对表），本文件这几条接在后面。
    # **币种那一条必须排第一**：它是本页最容易读错的一件事（副标题一个币种、
    # 紧挨着的头条数据条另一个币种），原先排在本文件的第三条、落到页面第 12 条、
    # 折叠线以下，等于没写。紧随其后的三条是「底座生成、spec 改不到」的抵消说明 ——
    # 它们更正的正是页面前面那几条底座 notes 里的话，晚出现就失去意义。
    # 名词释义：排在所有 exhibit 之前（CONTRACT §1）。选词的判断与逐条出处写在
    # `_glossary()` 的 docstring 与它内部的注释里。传的是**函数本身**：
    # 那 16 条里有一处会随时间变的数（一级市场两段列的起点差）要现算，写死的那一天
    # 就是它开始变旧的那一天；另有两处定值（对账阈值 1e-6、Main Market 老版式 4 列无源）
    # 照抄本页既有 note，不随月份变 —— 逐条交代在 `_glossary()` 的 docstring 里。
    'glossary': _glossary,

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
