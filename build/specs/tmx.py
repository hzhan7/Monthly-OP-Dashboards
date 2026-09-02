# -*- coding: utf-8 -*-
"""TMX Group 单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/tmx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页最容易犯的错：把几段起点不同的历史当成一段 ━━
series/tmx.csv 里躺着**几段互相独立的官方序列**（几段就是下面列了几条 —— 上一版这里
写「三段」而下面列了四条，页尾那条 notes 也跟着说了同一句假话；页尾那句现在由
`_seg_zh()` 数 CSV 现算，这里就不再写数字了），起点差得很远、每月到货也差几天
（下面每个起点本文件都用 `_first_present()` 从 CSV 现算，一个都不写死）：

    Montréal Exchange 衍生品（mx_*）        2002-01 起   m-x.ca 月度 xlsx
    月末指数点位（*_composite_close）       2001-12 起   TMX Money（历史）+ CTS 表格（增量）
    加拿大现货成交（tmx_all_/tsx_/tsxv_/alpha_）
                                            2015-01 起   CIRO（历史）+ CTS 新闻稿（增量）
    Alpha-X & Alpha DRK（alphax_drk_*）      2023-11 起   两个独立源都从这个月才有

两条结论直接来自这个事实：

  1. `headline` **只能放 MX 那条**。把现货放进头条，本页的共同最新月会被现货那半边
     拖慢一档（每月初都会出现「MX 已有上月、现货还没发」的正常状态），
     而且 2015-01 之前那 13 年 MX 历史会因为「共同历史」被整段砍掉。
  2. 全部 17 条现货列进 `slow_cols`。它们比 MX 晚一档发布，最新月留空是**正常状态**，
     不是解析失败，绝不能参与发布门槛判定。

━━ 现货那半边 2021-08 换过源，两条列要打断点 ━━
2021-08 之前 TMX 自己的月度明细只存在于 tmx.com/en/resource/<id> 的 PDF 里，
而整个 tmx.com 对本网络返回 CloudFront 403（curl / urllib / nscurl / curl_cffi /
本机真实 Chrome 实测全部 403），至今没有合规通道 —— 这一条没变。
变的是：那 79 个月改由**监管方** CIRO 的同口径月报补上了
（`build/basefill/tmx_ciro_2015.py`，一次性脚本；口径实测见 fetch/tmx.py 口径坑 16）。

两把尺子不完全一样。60 个重叠月（2021-08~2026-07）实测，接缝处的**纯口径台阶**：

    tsx_volume_shares      −1.62%   ← 画断点线
    tmx_all_volume_shares  −0.98%   ← 画断点线
    tsx / tmx_all / alpha 的成交额  +0.15% ~ +0.17%   ┐ 不画：跨这个月是可比的，
    笔数三列与 tsxv 三列          0.00% ~ −0.11%      ┘ 画了等于说假话

所以 `_breaks()` 里的换源断点**只绑那两条量的列**。同一条教训 asx.py 记过：
断点线的语义是「这张图上**这条**序列从这一期起与左侧不可比」，标错比不标更糟。

⚠ **2021 是拼接年**（1–7 月 CIRO、8–12 月 TMX 自报），所以三张分解图里跨 2021→2022
那一格带着一点口径失真：实测 tsx 成交股数增速被抬高 0.75pp、TMX 合计股数 0.35pp、
成交额一侧 ≤0.07pp。图注里照实说，不做剔除。

━━ BOX 期权：本页做不出来 ━━
TMX 官方**只按季度**披露 BOX（季度 MD&A 里的「最近八个季度」表），没有任何月度口径，
BOX 自己的站点也不发月度统计。它落在 series/tmx_box_q.csv（quarter 列，
实测 8 行：2024-Q3 → 2026-Q2），与本页契约的月频 groups 不兼容。
硬塞进来要么改契约、要么在底座里为 TMX 开一条季频分支 —— 两者都违背
「删掉不留残渣、不许 if ticker == 'tmx'」。要做就另起一页，不缠这一页。

━━ 量价分解：为什么三张图都画 TSX 主板，而不是 TMX 合计 ━━
本页现货侧有 TMX 合计 / TSX / TSXV / Alpha / Alpha-X&DRK 五档，每一档都有
**金额 + 股数 + 笔数**三列成对（全仓唯一一家）。三张分解图一律取 **TSX 主板**，两个理由：

  1. **只有 TSX 配得上指数。**series/tmx.csv 里的 `tsx_composite_close` 是
     S&P/TSX Composite —— 它的成分就是 TSX 主板的票。拿它去除 TMX 合计的均价，
     分母里混着 TSXV 的仙股（本文件 `_venue_price()` 现算：TSXV 均价中位数不到
     1 C$/股，TSX 是它的几十倍），得到的「结构效应」里有一大截只是 venue 混合比例。
  2. **TSX 自己没有口径断点。**TMX 合计在 2023-11 纳入 Alpha-X & Alpha DRK
     （见 `_breaks()`），TSX 那一列从头到尾同口径。

TMX 合计并没有因此消失：它是第三张图（三分法）的 **bench**，
「集团整体在动多少 / TSX 在集团里丢了多少份额 / TSX 的品种结构补回多少」正是那张图的读数。

━━ 三因子（笔数 × 每笔股数 × 均价）为什么是两张图不是一张 ━━
恒等式 `成交额 ≡ 笔数 × 每笔股数 × 均价` 成立且三项都有列，但底座的 `decomp`
只提供两种形状：两分法（量 × 派生量）与**三分法（bench 行业 / 份额 / 结构）**。
把「笔数」硬塞进 `bench_value`/`bench_qty` 在算术上确实能凑出这三块
（令 bench 两列同为笔数 ⇒ 行业块 = ln 笔数、份额块 = ln 每笔股数、结构块 = ln 均价），
但底座会据此在图注里印出三句**不成立**的话：「份额 ≡ 股数 ÷ 笔数」、
「结构 ≡ 自家均价 ÷ 行业均价」、以及「⚠️ 分子必须是分母的子集」——
股数不是笔数的子集，那句警告在这里是胡话。**图注说假话的代价高于少画一块柱**，
所以本页改成两张两分法：

    图 A  成交额 ≡ 成交股数 × 均价          （量的贡献 = ln 股数）
    图 B  成交额 ≡ 成交笔数 × 每笔平均金额  （量的贡献 = ln 笔数）

两张一并读就是三因子：ln(股数) − ln(笔数) = ln(每笔股数)，
而图 B 的「每笔金额」块 = 图 A 的「均价」块 + 每笔股数块。
逐年的三项实测数字由 `_three_factor()` 在 import 期从 CSV 现算，写进图 B 的图注，
一个都不写死。

━━ 图列：每一组都是「合计柱 + 分项 100% 占比堆叠」两张 ━━
2026-09 改版。用户给的两条原则：
  1. 月度数据尽量画**柱状图**，并在同一张图上叠一条同比折线；
  2. 像旧 Ex4 那样「合计 + 期货/期权」的组，先给合计一张柱 + 同比，再给分项一张占比图。

落地方式是底座新增的 `groups[].mix`（`build/single.py`，spec 驱动、不含任何
`if ticker == 'tmx'`）：声明 `total` 与 `parts` 两个**列名**，底座就出两张图 ——
合计那张是 `gs_bar` + 次轴同比，分项那张是 `stacked_dual` 的 100% 堆叠。
同比口径不是排版偏好，由列的性质定（CONTRACT §6.1）：
流量走 **12 个月滚动合计同比**（默认口径，无需在标题里辩护），
存量走**点对点同比**（12 个月末快照相加不指代任何量）。

于是本页除了三张年度量价分解（`decomp`）与季节性之外，**再没有多列折线对比图**：
原来那几张 `lines_endlabels` 全部变成「柱 + 占比」两张一对。
（**这里不数张数** —— 本文件抬头那段就记着「段数写死一次就要错一次」的教训，
改版前的张数要看 `git show HEAD~1:data/tmx.js`，不是看这句话。）

⚠️ 加总关系由底座**逐月复算**，spec 说了不算：分项之和超过合计直接硬失败；
少于合计而没给 `residual_zh` 也硬失败（那种图会声称「堆叠 = 100%」而实际不是）；
给了 `residual_zh` 而残差恒为 0 同样硬失败（一条恒为 0 的「其他」段会让读者
以为存在一块查不到的业务）。本页只有 MX 衍生品 ADV 那一条的残差恰为 0
（期货 + 期权 ≡ 合计），其余各条都必须给残差段。
**这里不写「本页有几条 mix」** —— 条数是数出来的，写死一次就要过期一次；
要当期数字就 `python3 -c "import …; print(sum(1 for g in SPEC['groups'] if g.get('mix')))"`。

⚠️ **有两条 mix 跨组引用了别处声明的列**，这是 `mix` 刻意允许的（total/parts 写的是
**列名**，列配置只在 `groups[].cols` 里声明一次 —— 写两份 unit/fmt 迟早分叉）：
  · 「MX 期权：个股与 ETF 构成」那组的**合计**是 `mx_adv_options_contracts`，
    它声明在最上面那组（在那里它是「期货 vs 期权」的一个分项）；
  · 「MX 月末未平仓」那组的五个**分项**分别声明在后面各自的组里。

⚠️ 跨组引用**不吃掉**被引用那一列在它自己那一组里的图：借它的数画结构，
不等于替它把水平值也讲了。所以 SXF / 个股期权 / ETF 期权三张存量柱照常出
（底座按「这一组真画出来了哪两张图」逐组算被吃掉的列，见 `Page.mix_pair`）。

━━ 有意不上页面的其他列 ━━
· mx_adv_index_options_contracts —— 最后一个非零月是 2020-10，此后逐月为 0
  （具体多少个月由 `_zero_tail()` 现算，写进页尾 notes）。一条归零五年多的死线不提供信息。

━━ BAX 未平仓：这一列照常声明，不在本文件里做特殊处理 ━━
mx_oi_bax_contracts 最后一个非零月是 2024-05（86,729 张），此后逐月为 0。
⚠ **「窗口内恒为 0」这句话跟着窗口走，别写死。** 本文件曾写着「2026-06 起整个图窗口
恒为 0」—— 那是图窗口还是「近 25 个月」时候的事；窗口改成 `build/single.py` 的
`WIN_FROM`（2016-01 起）之后，这条列在窗口里有八年多的非零段，图照常出。
恒为 0 的柱图会让引擎的纵轴量程（`0 .. 最大值×1.22`）上下界重合、坐标算成 0÷0，
把图画出卡片外 —— 但**这件事已由底座统一处理**
（`build/single.py` 的 `flat_zero()` / `flat0_skip()`：窗口内全零的图不出，
并在「口径与方法说明」里点名，而**该列仍留在末尾核对表里**）。
所以本文件按常规声明这一列即可，不要在这里摘列：摘了核对表也会跟着少一列，
而「官方报的就是 0」与「本页没有这个指标」是两回事。
· trading_days_rates / trading_days_equity —— 两套分母（不等的月份分布由
  `_tday_mismatch_zh()` 现算：实测集中在 11 月，9/10/12 月零星几次 —— 别写成
  「每年 9 月、11 月」，那是 2026-08-19 复核抓到的假话），
  ADV 官方直接给，本页不做除法。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'tmx.csv')


# ── 断点从 CSV 读，不写死 ──────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。两个函数都只做逐行扫描，
# 不含任何统计口径。读不到就返回 None —— 缺文件不许在 import 期抛异常。
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _first_present(col):
    for r in _rows():
        if col in r and r[col].strip():
            return r['month']
    return None


def _since(col, tail=''):
    """组名里那半句「（YYYY-MM 起）」—— 从 CSV 现算，不写死。

    写死过一次的教训就在本文件：四个现货组名写着「2021-08 起」，
    2026-08-18 把现货回补到 2015-01 之后，那四句话原地变成假的，而没有任何护栏会响
    （组名只是字符串）。凡是「从哪个月起」一律走这里。
    读不到列就退回不带月份的版本 —— 缺文件不许在 import 期抛异常。
    """
    m = _first_present(col)
    inner = (m + ' 起' + ('，' + tail if tail else '')) if m else tail
    return f'（{inner}）' if inner else ''


def _span_zh(col):
    """「YYYY-MM → YYYY-MM 实测 N 个月」——图注里描述一条列覆盖多长，同样现算。"""
    ms = [r['month'] for r in _rows() if col in r and r[col].strip()]
    if not ms:
        return '（本次未能从 CSV 读出覆盖区间）'
    return f'{ms[0]} → {ms[-1]}，实测 {len(ms)} 个月'


def _seg_zh(segs):
    """「本页有 N 段起点不同的历史」整段 —— 段数、名单、覆盖、谁最早，全部现算。

    ⚠️ 2026-08-19 复核抓到两处写死的假话，都在同一句里：
      · 「本页有**三段**起点不同的历史」，紧接着自己列了**四段**；
      · 「只有 MX 那条回得到 2002 年」，而同一句列出的月末指数点位是 2001-12，
        比 MX 还早一个月。
    ⚠️ 2026-08-19（复核的复核）再收一次口：上一版把**段数**改成了现算，
    但紧跟着的那份名单仍是 notes 里逐行写死的 `_span_zh(...)`。两者不同源 ——
    某一列哪天在 CSV 里空了，段数会自己减一，而名单照旧列四条，
    页面上又变成「三段」配四行。所以名单也从同一个 `segs` 生成：
    **段数就是这份名单的长度**，两半再也拆不开。

    段名后面那半句（「零断档」之类）跟着 segs 一起给，缺列时整条一起消失。
    """
    got = []
    for zh, col, extra in segs:
        ms = [r['month'] for r in _rows() if col in r and r[col].strip()]
        if ms:
            got.append((ms[0], zh, f'{zh} {ms[0]} → {ms[-1]}，实测 {len(ms)} 个月{extra}'))
    if not got:
        return ('本页有几段起点不同的历史，别把它们当成一段：'
                '（本次未能从 series/tmx.csv 读出任何一段的起点）')
    got.sort()
    n_zh = '一二三四五六七八九十'[len(got) - 1] if len(got) <= 10 else str(len(got))
    head = f'本页有<b>{n_zh}段起点不同的历史</b>，别把它们当成一段：'
    body = '；'.join(g[2] for g in got) + '。'

    # 「回得最早」的那一档：把与最早那段相差一年以内的都算进去。
    # 别按自然年切 —— 2001-12 与 2002-01 差一个月，按年份切会说成「只有一段回得到 2001」，
    # 读者拿着同一句话里列出的 MX（2002-01）就能反驳。
    def _mi(m):
        return int(m[:4]) * 12 + int(m[5:7])

    early = [f'{zh}（{m} 起）' for m, zh, _t in got if _mi(m) - _mi(got[0][0]) <= 12]
    late = got[-1]
    tail = ('任何「TMX 从 20xx 年以来如何」的说法都要按列限定 —— '
            f'回得最早的是{"、".join(early)}'
            + ('（相差不到一年，其余各段都晚得多）' if len(early) > 1 else '')
            + (f'，最晚的一段（{late[1]}）要到 {late[0]} 才起步。'
               if len(got) > 1 else '。'))
    return head + body + tail


def _lm(col):
    """`_last()` 的月份，缺失时给一句占位 —— 图注不许因为缺一列就在 import 期炸掉。"""
    return _last(col)[0] or '（最新月未知）'


def _lv(col):
    """`_last()` 的数值（千分位整数），缺失时给一句占位。

    ⚠ 别直接写 f'{_last(c)[1]:,.0f}'：缺列 / 缺文件时那是
    `TypeError: unsupported format string passed to NoneType.__format__`，
    而本文件顶上写着「缺文件 / 缺列不许在 import 期抛异常」——
    炸在这里会让 monthly_run 因为一张页的图注文案挂掉整批。
    """
    v = _last(col)[1]
    return f'{v:,.0f}' if v is not None else '（未能从 CSV 读出）'


def _last(col):
    """该列最后一个有值的 (月, float)；没有返回 (None, None)。

    图注里凡是「实测 2026-06 tsx_value_cad = …」这种举例数字都走这里 ——
    写死一次就要过期一次，而过期的图注没有任何护栏会喊。
    """
    hit = None
    for r in _rows():
        v = (r.get(col) or '').strip()
        if v:
            try:
                hit = (r['month'], float(v))
            except ValueError:
                pass
    return hit if hit else (None, None)


def _tday_mismatch_zh():
    """两条交易日列在哪些月份不等 —— 逐月现算，别写「每年 9 月、11 月」。

    2026-08-19 复核：那句话是假的 —— 实测两列都有值的月份里只有个位数百分比的月份不等，
    集中在 11 月（近乎每年），9 月只是零星几次，另外 10 月与 12 月各有过一次。
    「每年 9 月、11 月」既漏了 10/12 月，又把 9 月说成年年发生。
    这里改成现算：月份分布哪天变了，这句话自己跟着变。算不出返回空串，
    调用方退回不带数字的说法。**这段 docstring 里一个计数都不写** ——
    上一版在这里写「296 个月里 29 个月」，而实测是 295（自己算的函数印的也是 295），
    注释与函数当场对不上。要看当期数就 import 本模块打印 `_tday_mismatch_zh()`。
    """
    a, b = 'trading_days_rates', 'trading_days_equity'
    both = diff = 0
    by_mo = {}
    for r in _rows():
        x, y = (r.get(a) or '').strip(), (r.get(b) or '').strip()
        if not x or not y:
            continue
        both += 1
        if x != y:
            diff += 1
            by_mo[r['month'][5:7]] = by_mo.get(r['month'][5:7], 0) + 1
    if not both:
        return ''
    if not diff:
        return f'实测 {both} 个两列都有值的月份逐月相等'
    order = sorted(by_mo.items(), key=lambda kv: (-kv[1], kv[0]))
    det = '、'.join(f'{int(mo)} 月 {k} 次' for mo, k in order)
    return f'实测 {both} 个两列都有值的月份里 {diff} 个月两者不等（{det}）'


def _zero_tail(col):
    """该列末尾连续为 0 的月数 -> (最后一个非零月, 此后连续 0 的月数)。

    ⚠ 别拿 `_first_zero_after_nonzero()` 顶替这里：那个返回的是**第一次**转 0 的月份，
    序列中间有过零星 0 的时候（mx_adv_index_options_contracts 早年就有）
    它给的是 2020-01 而不是 2020-10，跟「此后一直是 0」不是一回事。
    """
    last_nz, n = None, 0
    for r in _rows():
        v = (r.get(col) or '').strip()
        if not v:
            continue
        try:
            f = float(v)
        except ValueError:
            continue
        if f == 0:
            n += 1
        else:
            last_nz, n = r['month'], 0
    return last_nz, n


def _first_zero_after_nonzero(col):
    """该列**由正数转为 0** 的第一个月（产品停发/迁移用这条）。"""
    seen = False
    for r in _rows():
        if col not in r or not r[col].strip():
            continue
        try:
            v = float(r[col])
        except ValueError:
            continue
        if v > 0:
            seen = True
        elif seen:
            return r['month']
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：全部在 import 期从 series/tmx.csv 现算，
# 再用 f-string 拼进下面三段 _*_NOTE（照 build/specs/jpx.py 的 _wedges()）。
# 任何一步算不出来就返回 None，对应的 note 退回**不含数字的定性版本** ——
# 缺文件 / 缺列不许在 import 期抛异常，否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
import math

#: 三张分解图各画几根完整年度柱。底座取 `run[-(years+1):]` 个完整年 ⇒ 至多 years 根柱
#: （外加最新年不完整时的 YTD 柱）。下面两个 note 函数**必须切到同样的年数**：
#: 现货回补到 2015-01 之后完整日历年从 4 个变成 11 个，不切的话图注会逐年报 10 组读数
#: 而图上只有 4 根柱，「可以直接对上」当场变成假话。
_DECOMP_YEARS = 4


def _num(r, col):
    """CSV 里一格 → float；空格子 / 非数返回 None（不拿 0 冒充缺失）。"""
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


def _cal_years(cols):
    """→ [(年份, {列: 该年 12 个月的合计}), …]，只保留 12 个月齐全且各列都有值的日历年。

    与底座 `Page._years(start_month=1, …)` 同一条规矩：缺月的年份整年丢掉，
    **不按 11 个月折算成 12 个月**（折算要假设缺的那个月与其余月同分布，
    而缺月最常见的原因恰恰是「那个月不正常」）。这里再算一遍是因为图注要报的
    「指数涨了多少」「三因子各占多少」底座并不算 —— 底座只认恒等式里那两列。
    """
    buckets = {}
    for r in _rows():
        m = (r.get('month') or '').strip()
        if len(m) != 7 or m[4] != '-':
            continue
        buckets.setdefault(m[:4], []).append(r)
    out = []
    for y in sorted(buckets):
        rows = buckets[y]
        if len(rows) != 12:
            continue
        agg = {}
        for c in cols:
            vals = [_num(r, c) for r in rows]
            if any(v is None for v in vals):
                agg = None
                break
            agg[c] = sum(vals)
        if agg is not None:
            agg['_n'] = 12
            out.append((y, agg))
    # 只保留末尾逐年连续的一段（同底座：中间断一年会把两个不相邻的年度画成相邻柱）
    run = out[-1:]
    for k in range(len(out) - 2, -1, -1):
        if int(out[k][0]) != int(run[0][0]) - 1:
            break
        run.insert(0, out[k])
    return run


def _index_split():
    """把 TSX 均价的增长拆成「市场涨跌」与「品种结构」两截 —— 全仓只有这一家做得到。

    均价 P ≡ 成交额 ÷ 成交股数，它同时含（a）市场涨跌与（b）成交结构变化
    （贵票 vs 便宜票的成交占比此消彼长）。JPX / SGX 两页的图注都只能说
    「均价里含结构效应，但本页拆不出它有多大」—— 因为那两家的 series 里没有指数列。
    TMX 有 `tsx_composite_close`，而且它的成分正是 TSX 主板的票，所以这里能写成

        ln(P₁/P₀) = ln(I₁/I₀) + ln[(P/I)₁ ÷ (P/I)₀]
                     └ 市场涨跌 ┘   └── 品种结构（成交在贵票/便宜票之间的迁移）──┘

    I 取**该年 12 个月末点位的平均**，不取 12 月那一个点：分子 P 是整整 12 个月的
    Σ金额÷Σ股数，拿单月末点位当年度指数水平，端点挑到一个异常月就能把归因说反。

    两块再乘上与图上同一个重标定权重 w = g_额 ÷ ln(V₁/V₀)，于是它们**逐年相加
    恰好等于图 A 里「均价的贡献」那一块**（单位同为百分点），读者可以直接对上。

    返回 [(年标签, 价的贡献pp, 市场涨跌pp, 品种结构pp), …]；算不出返回 []。
    """
    ys = _cal_years(['tsx_value_cad', 'tsx_volume_shares', 'tsx_composite_close'])
    out = []
    for (y1, a1), (y0, a0) in zip(ys[1:], ys[:-1]):
        try:
            V1, V0 = a1['tsx_value_cad'], a0['tsx_value_cad']
            Q1, Q0 = a1['tsx_volume_shares'], a0['tsx_volume_shares']
            I1, I0 = a1['tsx_composite_close'] / 12.0, a0['tsx_composite_close'] / 12.0
            if min(V1, V0, Q1, Q0, I1, I0) <= 0:
                continue
            lV = math.log(V1 / V0)
            if abs(lV) < 1e-6:          # 与底座 DECOMP_LN_MIN 同一条：w 此时是 0/0
                continue
            w = (V1 / V0 - 1.0) / lV
            lP = math.log((V1 / Q1) / (V0 / Q0))
            lI = math.log(I1 / I0)
            out.append((y1, w * lP * 100, w * lI * 100, w * (lP - lI) * 100))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    return out[-_DECOMP_YEARS:]          # 只报图上画得出的那几根柱，见 _DECOMP_YEARS


def _three_factor():
    """三因子实测：ln(成交额) = ln(笔数) + ln(每笔股数) + ln(均价)，重标定成百分点。

    底座画不了三块（理由见模块 docstring），但**数字可以在图注里报全**。
    与图 A / 图 B 用同一个权重 w，所以三项相加逐年等于那两张图菱形上的总增长。

    返回 [(年标签, 总增长%, 笔数pp, 每笔股数pp, 均价pp), …]；算不出返回 []。
    """
    ys = _cal_years(['tsx_value_cad', 'tsx_volume_shares', 'tsx_transactions'])
    out = []
    for (y1, a1), (y0, a0) in zip(ys[1:], ys[:-1]):
        try:
            V1, V0 = a1['tsx_value_cad'], a0['tsx_value_cad']
            Q1, Q0 = a1['tsx_volume_shares'], a0['tsx_volume_shares']
            T1, T0 = a1['tsx_transactions'], a0['tsx_transactions']
            if min(V1, V0, Q1, Q0, T1, T0) <= 0:
                continue
            lV = math.log(V1 / V0)
            if abs(lV) < 1e-6:
                continue
            w = (V1 / V0 - 1.0) / lV
            lT = math.log(T1 / T0)
            lS = math.log((Q1 / T1) / (Q0 / T0))
            lP = math.log((V1 / Q1) / (V0 / Q0))
            out.append((y1, (V1 / V0 - 1.0) * 100,
                        w * lT * 100, w * lS * 100, w * lP * 100))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    return out[-_DECOMP_YEARS:]          # 只报图上画得出的那几根柱，见 _DECOMP_YEARS


def _bench_wedge():
    """三分法的 bench（TMX 合计）在 2023-11 变大了多少 —— 份额那一块的口径楔子。

    合计口径自 Alpha-X & Alpha DRK 单列起纳入这两个盘口（见 `_breaks()`），
    于是「TSX 的股数份额」的**分母**在那个月一次性变大，份额被机械地压低一点点。
    这一点点有多大不靠形容词：这里量出 Alpha-X&DRK 占合计股数的最大值与最新值。

    返回 (最新月, 最新占比%, 全期最大占比%, 恒等式最大残差)；算不出全部返回 None。
    """
    cur, mx, res = None, 0.0, 0.0
    for r in _rows():
        tot = _num(r, 'tmx_all_volume_shares')
        ax = _num(r, 'alphax_drk_volume_shares')
        if not tot:
            continue
        parts = [_num(r, c) for c in ('tsx_volume_shares', 'tsxv_volume_shares',
                                      'alpha_volume_shares')]
        if all(p is not None for p in parts):
            res = max(res, abs(tot - (sum(parts) + (ax or 0.0))))
        if ax is None:
            continue
        s = ax / tot * 100.0
        mx = max(mx, s)
        cur = (r['month'], s)
    if cur is None:
        return (None,) * 4
    return cur[0], cur[1], mx, res


def _venue_price():
    """各 venue 的均价中位数（C$/股）—— 「品种结构」这件事的直接证据。

    返回 {venue: 中位均价}；算不出返回 {}。
    """
    out = {}
    for pref, zh in (('tsx', 'TSX'), ('tsxv', 'TSX Venture'),
                     ('alpha', 'TSX Alpha'), ('tmx_all', 'TMX 合计')):
        vs = []
        for r in _rows():
            v, q = _num(r, pref + '_value_cad'), _num(r, pref + '_volume_shares')
            if v and q:
                vs.append(v / q)
        if vs:
            vs.sort()
            out[zh] = vs[len(vs) // 2]
    return out


def _bond_oi_note():
    """国债期货月末未平仓那一组的口径交代 —— 恒等式闭不闭合，全部现算。

    ⚠️ 给下一个改这里的人：这一组在 2026-09 之前只有「合计 + CGB」两条列，
    于是合计与 CGB 之间那条越拉越宽的口子读起来像「其余合约」（2024 年起中位 41%）。
    **它从来不是官方的披露边界，是本仓的管道边界** —— `MONTH END OPEN INTEREST`
    在 m-x.ca 的 xlsx 里是横跨所有产品行的列块，CGF / CGZ 的格子一直都在，
    只是 `fetch/tmx.py` 的 `MX_SPEC` 当时没登记这两条（ADV 一侧四条一直是齐的）。
    补齐之后残差落到千分之几，剩下的只有 LGB 一个合约。

    所以这段话报的数只有一个用处：**证明恒等式现在真的闭合**。它必须现算 ——
    哪天官方在 Bond Futures 小节里新上一个合约，残差会自己变大，这段话跟着变，
    而写死的「只剩 LGB」会原地变成假话且没有护栏会喊。
    """
    got = []
    for r in _rows():
        tot = _num(r, 'mx_oi_bond_futures_contracts')
        parts = [_num(r, c) for c in ('mx_oi_cgb_contracts', 'mx_oi_cgf_contracts',
                                      'mx_oi_cgz_contracts')]
        if not tot or any(p is None for p in parts):
            continue
        d = tot - sum(parts)
        got.append((r['month'], d, d / tot * 100.0))
    head = ('<b>国债期货的 ADV 与月末未平仓现在都是「合计 + 三档」</b>：'
            'CGB（10 年）、CGF（5 年）、CGZ（2 年）。'
            # ⚠️ 上一版这里写「ADV 四条同轴画一张，未平仓是存量、每列各一张柱图」——
            # 那是 `groups[].mix` 进底座之前的画法，现在两侧同构，都是「合计柱 + 占比堆叠」
            # 两张一对。图注不许留着描述一套已经不存在的版式。
            '<b>两侧现在同构</b>：ADV 与未平仓各出「合计柱 + 三档占比堆叠」两张，'
            '差别只在口径（ADV 是当月日均的流量，未平仓是月末快照的存量）。'
            '要逐格对总量请看页尾核对表 —— 那里四列并排。'
            '官方 xlsx 的 Bond Futures 小节里只有这三档加一个 LGB（30 年），'
            '四条之和恰是小节的 Total，所以「合计」与三档之间那点差就是 LGB，'
            '不是一篮子说不清的东西。'
            '（小节的 Total 之<b>后</b>还印着一行 Bond Options - OGB，那是期权、'
            '不在 Total 里，别把它算进来。）')
    if not got:
        return head + '（本次未能从 series/tmx.csv 算出恒等式残差，此处不报数。）'
    pct = sorted(g[2] for g in got)
    med, mx = pct[len(pct) // 2], max(pct)
    worst = max(got, key=lambda g: g[2])
    lm, ld, lp = got[-1]
    n0 = sum(1 for g in got if abs(g[1]) < 0.5)
    return head + (
        f'实测 {len(got)} 个月逐月核过：合计 − 三档之和占合计的比例'
        f'中位 {med:.4f}%、最大 {mx:.4f}%（{worst[0]}，{worst[1]:,.0f} 张），'
        f'最新月 {lm} 是 {ld:,.0f} 张 = {lp:.4f}%；其中 {n0} 个月残差恰为 0。'
        f'<b>LGB 不单列</b>就是这个原因 —— 它多数月份未平仓为 0，'
        f'单画一条会是贴着零轴的死线。')


_IDX = _index_split()
_3F = _three_factor()
_BWM, _BWC, _BWX, _BWR = _bench_wedge()
_VP = _venue_price()
_NOTE_BOND_OI = _bond_oi_note()
_TDAY_MISMATCH = _tday_mismatch_zh()
# 段名、列、以及跟在覆盖后面的那半句附注 —— 名单与段数从这一份现算，不许在 notes 里
# 另写一份（上一版就是段数现算、名单写死，某列一空两半立刻对不上）。
_SEG = _seg_zh(
    (('MX 衍生品', 'mx_adv_contracts', '（零断档）'),
     ('月末指数点位', 'tsx_composite_close', ''),
     ('加拿大现货成交', 'tsx_value_cad', ''),
     ('Alpha-X & Alpha DRK', 'alphax_drk_volume_shares', '')))


def _pp(x):
    return f'{x:+.1f}pp'


# ── 现货换源（2021-08）：常量放这里，因为下面的图注与断点两处都要用 ──────────
# 这个月**及其之后**的现货 12 列是 TMX 自报（CTS 新闻稿），之前是监管方 CIRO。
# 与 fetch/tmx.py 的 `SPOT_START` / build/basefill/tmx_ciro_2015.py 的 `CTS_FROM`
# 是同一个月。**它不是能从 CSV 现算出来的量**（CSV 里不记每格的出处），所以只能写死；
# 但 `_breaks()` 会先确认 CSV 真有换源之前的数据才画线 —— 回补哪天被撤掉，
# 这条断点自己消失，不会留一条指着空气的红线。
_SRC_SWITCH = '2021-08'
# 只绑**纯口径台阶 ≥0.5%** 的两条列（实测 tsx −1.62% / TMX 合计 −0.98%）。
# 另外 10 条列的台阶在 0.00%~0.17% 之间，跨这个月是可比的，画线等于说假话。
# 台阶怎么量的、为什么不整段改用 CIRO：见 fetch/tmx.py 口径坑 16。
_SRC_COLS = ('tsx_volume_shares', 'tmx_all_volume_shares')
# 断点标签，长度与另外两条对齐（理由见下面「断点标签必须短」那段）。
_SRC_ZH = 'CIRO→TMX 换源'


def _splice_note():
    """三张分解图共用的一句：那根跨拼接年的柱带着多少口径失真。

    **只在拼接年真的落在图上时才出这句话。**换源发生在年中，所以只有那一个日历年
    （_SRC_SWITCH 所在的年）是「半年 CIRO + 半年 TMX 自报」；它今年还是首格柱的基期，
    明年就滑出 `_DECOMP_YEARS+1` 的窗口，那时这句话必须自己消失，不能留在图注里
    指着一根已经不存在的柱。图上画哪几年由 `_cal_years()` 的末尾连续段决定，
    与底座 `run[-(years+1):]` 同一套。

    失真的量（0.75pp / 0.35pp / ≤0.07pp）是 2026-08-18 拿 CIRO 那份工作簿把 2021 年
    8–12 月换成同源值重算出来的**一次性实测**：它描述的是 2021 这个固定的历史年份，
    不随新数据变化，所以写死在这里是对的（CSV 里没有 CIRO 的 2021-08~12，现算不出来）。
    """
    ys = [y for y, _a in _cal_years(['tsx_value_cad', 'tsx_volume_shares'])]
    if _SRC_SWITCH[:4] not in ys[-(_DECOMP_YEARS + 1):]:
        return ''
    return (f'<b>⚠️ {_SRC_SWITCH[:4]} 是拼接年。</b>现货 12 列在 {_SRC_SWITCH} 换过源'
            f'（此前 CIRO、此后 TMX 自报，见页尾「口径与方法说明」），'
            f'所以 {_SRC_SWITCH[:4]} 那一整年是半年一把尺子。实测把 8–12 月也换成 CIRO '
            f'重算，跨 {_SRC_SWITCH[:4]}→{int(_SRC_SWITCH[:4]) + 1} 那一格的'
            f'成交股数增速会低 0.75pp（TMX 合计口径 0.35pp），成交额一侧 ≤0.07pp。'
            f'本页照实说明、不做剔除 —— 剔除等于自造一条谁也没发过的序列。')


_NOTE_SPLICE = _splice_note()


# ── 图 A（量 × 价）的图注：把「价」再拆成市场涨跌与品种结构 ────────────────
_NOTE_PRICE = (
    '<b>本页是全仓唯一能把「市场涨跌」与「品种结构」拆开的一家。</b>'
    '均价 ≡ 成交额 ÷ 成交股数，它同时含（a）市场整体涨跌与（b）成交在贵票与便宜票之间的'
    '迁移。JPX 与 SGX 两页的同类图注只能写「均价里含结构效应，但本页拆不出它有多大」——'
    '因为那两家的 series 里没有指数列。'
    '<code>series/tmx.csv</code> 有 <code>tsx_composite_close</code>（S&P/TSX Composite '
    '月末点位），而它的成分正是 TSX 主板的票，所以这里能再写一层**定义式**：'
    'ln(P₁/P₀) = ln(I₁/I₀) + ln[(P/I)₁ ÷ (P/I)₀]，前者是市场涨跌、后者是品种结构。'
    'I 取该年 <b>12 个月末点位的平均</b>而不是 12 月那一个点 —— 分子是整整 12 个月的'
    'Σ金额÷Σ股数，拿单月点位当年度指数水平，挑到一个异常月就能把归因说反。'
    + (('两块乘上与本图同一个重标定权重 w，因此<b>逐年相加恰好等于上面「均价的贡献」'
        '那一块</b>，可以直接对上（单位同为百分点）：'
        + '；'.join(f'{y} 价 {_pp(p)} = 市场 {_pp(i)} + 结构 {_pp(m)}'
                    for y, p, i, m in _IDX)
        + '。以上逐年对账只覆盖<b>完整日历年</b>；末尾的 YTD 格窗口与此不同，'
          '其「均价的贡献」以图上读数为准，这里不另拆市场/结构。')
       if _IDX else
       '（本次未能从 CSV 算出逐年读数，此处只给方法不给数字。）')
    + '<b>⚠️ 这一层只对 TSX 成立。</b>S&P/TSX Composite 不含 TSX Venture，'
      '拿它去除 TMX 合计的均价，分母里混着仙股，算出来的「结构」有一大截只是 venue 混合比例。'
      '本页三张分解图因此一律画 TSX 主板，TMX 合计只作为第三张图的 bench 出现。'
    + _NOTE_SPLICE
)

# ── 图 B（笔数 × 每笔金额）的图注：三因子在这里报全 ────────────────────────
_NOTE_TRADE = (
    '<b>这张与上一张合起来就是三因子。</b>'
    '恒等式 成交额 ≡ 笔数 × 每笔股数 × 均价 三项都有列'
    '（<code>tsx_transactions</code> / <code>tsx_volume_shares</code> / '
    '<code>tsx_value_cad</code>），但底座的三分法是「行业 / 份额 / 结构」形状 ——'
    '把笔数塞进 bench 虽然凑得出三块，图注却会跟着印出「份额 ≡ 股数 ÷ 笔数」'
    '「结构 ≡ 自家均价 ÷ 行业均价」「⚠️ 分子必须是分母的子集」三句不成立的话。'
    '<b>图注说假话的代价高于少画一块柱</b>，所以拆成两张两分法，三项读数在这里报全'
    '（同一个重标定权重 w，三项相加逐年等于菱形上的总增长）：'
    + ('；'.join(f'{y} 总 {g:+.1f}% = 笔数 {_pp(t)} + 每笔股数 {_pp(s)} + 均价 {_pp(p)}'
                 for y, g, t, s, p in _3F)
       + '。以上三因子读数只覆盖<b>完整日历年</b>；末尾的 YTD 格不在此列，'
         '两张图各自 YTD 格的读数以图上为准。' if _3F else
       '（本次未能从 CSV 算出逐年读数。）')
    + '<b>⚠️「每笔平均成交额」不是价。</b>它衡量的是订单碎片化程度 —— '
      '同一笔母单被切成更多子单，笔数上升、每笔金额下降，而成交额与股价一点没变。'
      '要读价请看上一张图。'
    + _NOTE_SPLICE
)

# ── 图 C（三分法）的图注：子集关系与 2023-11 的口径楔子 ────────────────────
_NOTE_SHARE = (
    '<b>子集关系是精确成立的，不是近似。</b>SINGLE_SPEC §1.3.1 把「分子必须是分母的子集」'
    '列为 spec 作者的责任（底座验证不了）。本页的核实办法是撞恒等式：'
    'TMX 合计股数 ≡ TSX + TSXV + Alpha（+ 2023-11 起的 Alpha-X&DRK）'
    + (f'，全期最大残差 <b>{_BWR:.0f} 股</b>（即逐月分毫不差）。' if _BWR is not None
       else '，本次未能复算残差。')
    + '<b>⚠️ bench 在 2023-11 变大过一次。</b>合计口径自该月起纳入 Alpha-X & Alpha DRK，'
      '于是「TSX 股数份额」的**分母**一次性变大、份额被机械压低一点点。'
    + (f'这一点点有多大：Alpha-X&DRK 占合计股数最高只有 <b>{_BWX:.2f}%</b>'
       f'（{_BWM} 为 {_BWC:.2f}%），所以跨 2023 那一格的「份额」块里最多有 '
       f'{_BWX:.2f}pp 量级不是份额变化而是口径变化。' if _BWX else
       '本次未能量出它的幅度。')
    + '本页照实说明而不做剔除：把 Alpha-X&DRK 从合计里减掉等于自造一条官方没发过的序列。'
    + ('<b>「品种结构」这一块在读什么。</b>各 venue 的均价中位数实测：'
       + '、'.join(f'{k} {v:,.2f} C$/股' for k, v in _VP.items())
       + '。TSX 与 TSX Venture 差着一两个数量级（仙股主导），'
         '所以「TSX 均价相对集团」这一块量的就是成交在这两类票之间的迁移。'
       if _VP else '')
    + _NOTE_SPLICE
)

# ── ttm_yoy 两张图的图注 ──────────────────────────────────────────────────
# ⚠️ 这两条图注的**上一版讲的是 12 个月滚动同比**（柱与线怎么还原、为什么现货要看滚动）。
# 2026-09 全页次轴统一改成**单月同比**（页面所有者指定）之后那些话一句都不成立了，
# 所以整段重写，没有留半句。口径本身的实测代价由底座的 `mom_cost_zh()` 逐图现算，
# 这里只补它算不出来的那一半：这条序列自己的脾气。
_NOTE_TTM_MX = (
    '<b>本页最长、最快、最干净的一条序列。</b><code>mx_adv_contracts</code> 从 2002-01 起'
    '逐月无洞（实测 295/295），次月第 1–4 个工作日就发 —— 本页的数据月由它一条定。'
    '<b>⚠️ 它是当月<u>日均</u></b>（官方直接发布，不是本仓拿月合计除交易日算的）：'
    '交易日多的月份不会因此显得更热，但**月度形状仍在**（到期周、假期分布），'
    '这正是次轴那条单月同比毛刺的来源之一。'
    + '官方同时发布当月合计 <code>mx_volume_contracts</code>，本页把它单独画成一张柱图'
      '（组名「MX 当月成交总量」那张）—— 两条谁也不从谁推，'
      '想看「一个月一共做了多少」看那张，想看「开市那天有多热」看这张。'
)

_NOTE_TTM_SPOT = (
    '<b>这条是现货侧的主序列，但它与 MX 那条不是同一把尺子。</b>'
    '<code>tmx_all_volume_shares</code> 本身就是<b>当月合计</b>（不是日均），'
    '2015-01 起（' + _span_zh('tmx_all_volume_shares') + '），'
    '而且比 MX 晚一档发布 —— 每月初都会出现「MX 已有上月、现货还没发」的正常状态。'
    '<b>⚠️ 这条线上有两处口径断点，红色竖虚线标的就是它们</b>：'
    '2023-11 合计纳入 Alpha-X & Alpha DRK（分母一次性变大），'
    + _SRC_SWITCH + ' 数据源由 CIRO 换回 TMX 自报（纯口径台阶 −0.98%：TMX 自报的口径'
      '比 CIRO 低约 1%，与业务无关，见页尾「口径与方法说明」）。'
      '<b>跨这两个月读同比，读到的有一部分是口径不是业务</b> —— 单月口径尤其躲不开：'
      '断点当月与其后 11 个月的同比都跨着那道台阶。'
)


# ── groups[].mix 那几张 100% 占比图的图注 ──────────────────────────────────
# 底座的图注已经把「各段最新/窗口内极值」「残差最大占多少、在哪个月」这些**数**印全了
# （见 build/single.py 的 ex_mix_share），所以下面这几段只补底座**算不出来**的那一半：
# 那块残差到底是什么、为什么会有、读的时候容易在哪里读错。凡是要报数的地方一律现算。


def _idx_opt_lead():
    """股指期权在「期权合计 − 个股 − ETF」那一段里当主体的月份数 → (命中数, 可比月数)。

    这句话原来写的是「那一段里最大的一块是股指期权」—— **实测是假的**：
    窗口内只有个位数月份成立（下面这个函数现算的就是它）。写死一次就要错一次，
    所以改成现算，并且把「不是主体」这个结论直接印在图注里。
    算不出返回 (None, 0)，调用方退回不带数字的说法。
    """
    hit = tot_n = 0
    for r in _rows():
        if r.get('month', '') < '2016-01':
            continue
        t = _num(r, 'mx_adv_options_contracts')
        eq = _num(r, 'mx_adv_equity_options_contracts')
        etf = _num(r, 'mx_adv_etf_options_contracts')
        ix = _num(r, 'mx_adv_index_options_contracts')
        if None in (t, eq, etf, ix) or not t:
            continue
        tot_n += 1
        if ix >= (t - eq - etf) - ix:
            hit += 1
    return (hit, tot_n) if tot_n else (None, 0)


_IDX_OPT_LEAD = _idx_opt_lead()


#: 图窗左端。与 `build/single.py` 的 `WIN_FROM` 是同一个月 —— 本文件只拿它给**图注**
#: 定描述范围（哪个月起算残差），不参与任何绘图。两处不同步的后果是图注说的窗口
#: 与图上画的窗口对不上，所以改一处要看另一处。
_WIN_FROM = '2016-01'


def _resid_first_zh(tot, parts, tol=1e-6, since=_WIN_FROM):
    """**图窗内**残差（合计 − 各分项）第一次超出 `tol`（相对）的月份 → (月份, 窗口首月)。

    ⚠️ 两条都踩过：
      ① 原来扫的是**全序列**，于是对 MX 那几列返回 2002-01（序列的第一行），
         而图注紧接着写「在那之前合计恰等于各分项之和」—— 2002-01 之前一个月都没有，
         那是一句关于不存在的时段的断言。现在只扫图窗，并把窗口首月一起返回，
         由调用方判断「残差是不是一进窗口就在」。
      ② `tol` 与底座的 `MIX_RESID_TOL` 对齐（1e-6）。用更严的 1e-9 会让图注说
         「自 X 月起有残差」而底座那边压根不认为有 —— 同一页两个口径。
    """
    first = None
    for r in _rows():
        if r.get('month', '') < since:
            continue
        t = _num(r, tot)
        ps = [_num(r, c) for c in parts]
        if t is None or not t or any(p is None for p in ps):
            continue
        if first is None:
            first = r['month']
        if abs(t - sum(ps)) / abs(t) > tol:
            return r['month'], first
    return None, first


def _since_resid(tot, parts, tail):
    m, first = _resid_first_zh(tot, parts)
    if m and first and m > first:
        return (f'这一段自 <b>{m}</b> 才出现 —— 从图窗左端 {first} 到那之前，'
                f'合计逐月恰等于各分项之和；' + tail)
    if m:
        return f'这一段在整个图窗（{first or "起点未知"} 起）里一直在；' + tail
    return '官方没有说明这一段是什么，所以本页只叫它「其他」，不猜。' + tail


_NOTE_MIX_MX = (
    '<b>这是本页唯一一张不需要「其他」段的占比图。</b>m-x.ca 的月度表把 MX 的日均成交'
    '只分成期货与期权两栏，两栏之和逐月恰等于合计（底座在构建时逐月复算，对不上就不出图）。'
    '<b>两段互补的代价要记住</b>：期货占比抬头与期权占比回落是同一个事实的两种写法，'
    '不是两条独立的证据。'
)

_NOTE_MIX_STIR = (
    '<b>这张图就是 CDOR → CORRA 换代本身。</b>在两条绝对量线上只看得见「一条掉到 0、'
    '另一条长出来」；放进同一个 100% 的盘子里，才看得出这是一次<b>此消彼长的换手</b>，'
    '而不是短端利率业务归零又凭空长出一个新产品。'
    + _since_resid('mx_adv_stir_futures_contracts',
                   ('mx_adv_bax_contracts', 'mx_adv_cra_contracts'),
                   '官方在月度表里没有为它单开一栏，所以本页只叫它「其他短端利率合约」。')
)

_NOTE_MIX_STIR_OI = (
    '<b>与上面那张 ADV 占比图读法相同，但口径是存量。</b>ADV 那张回答「这个月的成交'
    '在哪个合约上」，这张回答「月末还挂着的仓位在哪个合约上」——'
    '换代期间后者滞后于前者（旧合约的仓位要等到期才消失），两张并读才看得出迁移的节奏。'
    + _since_resid('mx_oi_stir_futures_contracts',
                   ('mx_oi_bax_contracts', 'mx_oi_cra_contracts'),
                   '官方没有为它单开一栏，本页只叫它「其他短端利率合约」。')
)

_NOTE_MIX_BOND = (
    '<b>三档久期的此消彼长是这张图的全部内容。</b>CGB（10 年）/ CGF（5 年）/ CGZ（2 年）'
    '之和几乎就是国债期货合计，残差是官方未单列的其余合约（LGB 等）。'
    '⚠️ <b>张数占比不是利率风险占比。</b>本图按<b>张数</b>算，而'
    '<code>series/contract_specs.csv</code> 的 MX_BOND 行记着同一条：同样名义额下'
    '2 年期与 10 年期的 DV01 差 5 倍以上（久期约 1.9 年 vs 约 8 年）。'
    '所以这张图读的是「成交张数落在哪一档久期上」，不是「利率风险落在哪一档」——'
    '后者要 DV01 或久期加权，而月度成交报表里没有久期字段。'
)

_NOTE_MIX_BOND_OI = (
    '<b>这张图 2026-09 之前画不出来，值得说一句为什么。</b>那时 <code>series/tmx.csv</code> '
    '里只有 CGB 一条国债期货的未平仓列，合计与 CGB 之间那条越拉越宽的口子'
    '（2024 年起中位 41%）读起来像「其余合约」—— 而它其实是<b>本仓的管道边界</b>：'
    'm-x.ca 那份月度 xlsx 的 <code>MONTH END OPEN INTEREST</code> 是一个横跨所有产品行的'
    '<b>列块</b>，CGF / CGZ 的格子一直都在（本页正在用的 CGF / CGZ <b>ADV</b> 取的就是'
    '同一批行），只是 <code>fetch/tmx.py</code> 的 <code>MX_SPEC</code> 没为这两档登记 '
    'oi 那一格。两列补齐并回补历史之后，那四成的「其余」落到千分之几。'
    '<b>现在剩下的残差只有 LGB（30 年）一个合约</b> —— 官方在 Bond Futures 小节里'
    '不给它单开一栏，逐月核对与量级见页尾「口径与方法说明」里那一条（现算）。'
    '⚠️ 那一小节的 Total 之<b>后</b>还印着一行 Bond Options - OGB，那是期权、不进 Total，'
    '别把它算进这张图的分母。'
    '<b>三档的此消彼长才是这张图的读数</b>：ADV 那一侧（上面「国债期货 ADV」那一对）'
    '看的是「这个月的成交落在哪一档久期」，这一侧看的是「月末还挂着的仓位落在哪一档」，'
    '换代与展期期间后者滞后于前者，两张并读才看得出节奏。'
)

_NOTE_MIX_INDEX = (
    '<b>这张图的读数是「SXF 有多独占」，不是「谁在抢 SXF 的份额」。</b>'
    'SXF（S&P/TSX 60 期货）常年占股指期货 ADV 的九成以上，剩下那一小段是官方未单列的'
    '其余股指合约（SXM 迷你等）。占比高在这里只说明「加拿大的股指期货成交几乎全部集中在'
    '一张合约上」，不说明它打赢了谁 —— MX 是这些合约的唯一挂牌地。'
)

_NOTE_MIX_OPT = (
    '<b>分母是 MX 期权 ADV 合计，它同时是本页第一张占比图里的「期权」那一段。</b>'
    '两张图串起来读：第一张说期权在整个 MX 里占多少，这一张说期权内部个股与 ETF 各占多少。'
    '<b>「其他期权」那一段本页拆不开，而且它不是股指期权。</b>'
    'm-x.ca 的月度表在期权侧至少还有两节 ——「短端利率期权」'
    '（<code>Short-Term Interest Rate Options</code>，<code>fetch/tmx.py</code> 的 '
    '<code>MX_SECTIONS</code> 里登记着它）与「股指期权」，而 '
    '<code>series/tmx.csv</code> 只入库了后者。'
    + ((f'实测股指期权并不是这一段的主体：{_IDX_OPT_LEAD[1]} 个可比月里只有 '
        f'{_IDX_OPT_LEAD[0]} 个月它大过这一段的其余部分。')
       if _IDX_OPT_LEAD[0] is not None else
       '（本次未能从 CSV 算出它在这一段里的占比。）')
    + f'而它最后一个非零月是 {_zero_tail("mx_adv_index_options_contracts")[0] or "（未知）"}、'
      f'此后连续 {_zero_tail("mx_adv_index_options_contracts")[1]} 个月为 0，'
      '所以本页也没有为它单开一条线（一条归零多年的死线不提供信息）。'
      '⇒ 这一段是<b>本仓的管道边界</b>，不是官方的披露边界；'
      '它具体由哪几类期权构成，本页给不出来，别去估。'
)

_NOTE_MIX_FUT = (
    '<b>这张回答「MX 是一家做什么的交易所」。</b>它与第一张占比图（期货 vs 期权）'
    '是同一条线索的下一层：那张说期货占 MX 的量的多少，这张说期货那一块里'
    '利率（短端 + 国债）、股指、个股各占多少。'
    '<b>本页几乎每一张 MX 图都是这四块里某一块的放大</b>，先看这张再往下读会省不少力气。'
    '⚠️ <b>张数占比不是收入占比也不是风险占比</b>：不同合约的费率与合约乘数差着数量级'
    '（一张 CGB 期货的面值 C$100,000，一张个股期货是 100 股 × 股价），'
    '本图只按张数算。'
)

_NOTE_MIX_OI_ALL = (
    '<b>这张图回答「MX 的持仓压在哪个产品上」，而 Exhibit 里的合计柱只回答「一共多少」。</b>'
    '五段自下而上是两条利率腿（短端利率、国债期货）、股指期货 SXF，再往上是两条股票期权腿'
    '（个股期权、ETF 期权）—— 这条上下分界就是「利率 vs 股票」。'
    '<b>本页最值得看的结构位移在这张图上</b>：ETF 期权与个股期权这两段的相对高低'
    '在窗口内整个翻了过来（各段的窗口极值与出现月份见上一段，那些数逐月现算）。'
    '<b>⚠️ 未平仓是存量，跨产品直接比高低要小心</b>：不同合约的一张「未平仓」代表的'
    '经济敞口差着数量级（一张 CGB 期货的面值 C$100,000，一张个股期权的名义值是'
    '100 股 × 股价），本图只按<b>张数</b>算，读作「持仓张数落在哪个产品上」，'
    '不是「风险敞口落在哪个产品上」。'
    '<b>最上面那段残差是本仓没有单列的那几档</b>（个股期货、股指期权等）——'
    'm-x.ca 的月度表里 <code>MONTH END OPEN INTEREST</code> 是一个横跨所有产品行的列块，'
    '这几档的行就在那里，只是 <code>fetch/tmx.py</code> 的 <code>MX_SPEC</code> 没有'
    '为它们登记 oi 那一格。所以这一段同样是<b>本仓的管道边界</b>，不是官方的披露边界。'
)

_NOTE_MIX_SPOT = (
    '<b>残差那一段就是 Alpha-X & Alpha DRK，但「2023-11 之前它是 0」的含义要说清楚。</b>'
    '不是这两个盘口在那之前没有成交，而是 <b>TMX 合计这个口径当时不含它们</b>'
    '（合计自 2023-11 起才纳入，图上那条红色竖虚线标的就是这件事）。'
    '所以跨 2023-11 读这张图时，各段占比的<b>分母变大过一次</b>，'
    'TSX / TSXV / Alpha 三段会被机械地压低一点点 —— 压多少由那一段自己的高度给出。'
    '<b>这三档不是在抢同一批订单流。</b>TSX 是主板、TSXV 是创业板、Alpha 是另一个撮合盘口，'
    '标的与上市层级都不同；这张图读作「加拿大现货成交的场所构成」，不是市场份额之争。'
)


# 断点标签**必须短**：它竖排画在断点线上，而断点线的全长就是绘图区高度
# （charts.js：`y1 = M.t`、`y2 = M.t + ph`，标签再按 `fitVertical(bel, ph - 6, 7)` 收缩），
# 正中间还钉着柱值标签，上下两段各只剩其中一截。
# ⚠️ **这里不写 px 数**，写一次错一次，已经错过两轮：
#   · 上上版写「断点线全长只有 ~254px」—— 那是 FS 还等于 1 那会儿量的；
#   · 上一版改成「Exhibit 18/19/20 约 260px、Exhibit 6 约 235px」—— 260 那半对，
#     235 那半**是错的**：它按 `H = 268 + round(26×(FS−1))` 算，可 Exhibit 6 是
#     lines_endlabels、spec 侧给了 `height = LINE_H_ENDLABEL`（build/single.py），
#     `H = opt.height + …`，ph 实际在 327px 上下，比另外三张还高。
#     ⚠️ 这两处 Exhibit 号是**改版前**（2026-09 的 groups[].mix 之前）的编号，
#     记的是当时量到的证据，照新编号改一遍会让证据与它对应的图对不上 —— 别改。
# 要点是几何而不是某个数：`ph = H − M.t − M.b`，其中 H 随 `opt.height` 与字号 FS
# （assets/charts.js 的 FS_MIN/FS_MAX）变、M.t 随「有没有截轴」在 fscale(14) 与
# fscale(30) 之间跳。哪张图剩多少，照那三个式子现算，别抄一个数下来。
# 原来那句「CDOR 停用，短端利率合约由 BAX 迁至 CORRA（CRA）」竖排下来哪一段都塞不下，
# 引擎只能靠 z 序兜底保住数字可读，几何重叠仍在
# （改短之前 tools/visual_qa.py 实测的 🟡 全出自这一句）。
# ⇒ 标签的职责是**标记位置**，不是讲故事：缩到 10 个汉字以内，来龙去脉留给页尾 notes。
_BAX_ZH = 'BAX→CORRA 迁移'
_ALPHAX_ZH = 'TMX 合计口径扩容'
# 断点**逐列绑定**，不画成贯穿全页的红线。
# 不绑列的断点底座会画到本页每一张图上（`Page.breaks_for()` 里 b['col'] 为空就放行），
# 实测后果：「CDOR 停用…」这条利率合约迁移的红线出现在 S&P/TSX Composite 月末点位、
# Alpha-X 成交额、现货成交股数这些与它毫无关系的图上 —— 断点线的语义是
# 「这张图上这条序列从这一期起与左侧不可比」，标错比不标更糟（asx.py 记过同一条教训）。
_BAX_COLS = ('mx_adv_stir_futures_contracts', 'mx_adv_bax_contracts',
             'mx_adv_cra_contracts', 'mx_oi_stir_futures_contracts',
             'mx_oi_bax_contracts', 'mx_oi_cra_contracts')
# 口径扩容只改「TMX 合计」这三列的覆盖范围，外加 Alpha-X&DRK 自己那三列的起点。
# TSX / TSXV / Alpha 三档一列都没变，它们的图上不该出现这条线。
_ALPHAX_COLS = ('tmx_all_volume_shares', 'tmx_all_value_cad', 'tmx_all_transactions',
                'alphax_drk_volume_shares', 'alphax_drk_value_cad',
                'alphax_drk_transactions')


def _breaks():
    out = []
    # CDOR 停用 → 短端利率基准迁到 CORRA。BAX 的 ADV 转 0 的那个月就是迁移完成月。
    # 实测 = 2024-07（BAX 最后一个非零月是 2024-06，CRA 同月接棒）。
    # 只绑短端利率那六列：这是**产品替换**不是集团口径变化，
    # MX 合计跨这个月是连续的（BAX 掉多少 CRA 接多少），所以合计那几列不标。
    m = _first_zero_after_nonzero('mx_adv_bax_contracts')
    if m:
        out += [{'month': m, 'col': c, 'zh': _BAX_ZH} for c in _BAX_COLS]
    # tmx_all_* 的覆盖范围在 Alpha-X & Alpha DRK 单列之后变大。
    # 实测恒等式：2023-10 及之前 tmx_all = TSX + TSXV + Alpha（差恰为 0）；
    # 2023-11 起 tmx_all = 三家 + Alpha-X&DRK（差同样恰为 0，见 _bench_wedge()）。
    m = _first_present('alphax_drk_volume_shares')
    if m:
        out += [{'month': m, 'col': c, 'zh': _ALPHAX_ZH} for c in _ALPHAX_COLS]
    # 现货换源。**先确认 CSV 里真有换源之前的月份**：`build/basefill/tmx_ciro_2015.py`
    # 没跑过（或被撤掉）时序列就是从 _SRC_SWITCH 起的，那时候画这条线是指着序列左端
    # 说「左边不可比」—— 左边根本没有东西。
    first_spot = _first_present('tsx_volume_shares')
    if first_spot and first_spot < _SRC_SWITCH:
        out += [{'month': _SRC_SWITCH, 'col': c, 'zh': _SRC_ZH} for c in _SRC_COLS]
    # 两条断点的推导顺序与时间顺序不同（BAX 那条在前推出、月份却在后），
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 这里统一按月份排。
    return sorted(out, key=lambda b: (b['month'], b['col']))


SPEC = {
    'ticker': 'tmx',
    'name': 'TMX Group',
    'title': '多伦多交易所集团（TMX）月度经营指标',
    'csv': 'tmx.csv',
    'ccy': 'CAD',
    # 开篇图并成一张：全历史的水平值柱 + 次轴单月同比（页面所有者 2026-09 指定：
    # 「柱状图和 yoy 的折线图要在一个图里」）。代价是近 3 年 P10/P90 分位带那张图没了 ——
    # 引擎没有「柱 + 两条带 + 次轴线」这种图型，见 build/single.py 的 HEADLINE_STYLES。
    # 汇总表的「3Y %ile」列不受影响（它不靠那张图）。
    'headline_style': 'bar_yoy',
    'source': ('Source: Montréal Exchange monthly statistics (m-x.ca), TMX Group '
               'Consolidated Trading Statistics press releases, CIRO Report of '
               'Marketshare by Marketplace (historical, pre-Aug-2021 cash equities) '
               'and TMX Money (index history); format after Goldman Sachs GIR'),

    # 头条只有 MX 一条 —— 见文件抬头第 1 条。
    # 2002-01 起逐月无洞（实测 295/295），次月第 1–4 个工作日发布，是本页最快、最长的序列。
    'headline': [
        {'col': 'mx_adv_contracts', 'zh': 'MX 衍生品 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        # 合计与期货 / 期权三条同为 contracts/day，**必须放在同一组**。
        #
        # ⚠️ 这条约束还在，但**理由换过一次**，别照着旧理由改回去：
        # 旧理由（2026-09 之前）是「拆成两组的话，只剩一列的那组会走 gs_bar，
        # 而 gs_bar 的次轴是**单月同比** —— tools/check_yoy_caliber.py 实测本页
        # 「MX 日均成交」曾有 2 个月与 12 个月滚动口径**符号相反**（单月 −1.2% 而
        # 滚动 +17.0%），读者从图上看不出该信哪一个」。那条理由现在**不成立了**：
        # 下面这个 `mix` 让合计走的是「柱 + **12 个月滚动**同比」（口径由
        # `granularity` / `total_col` 决定，与原来末尾那张 ttm_yoy 专图逐字同源），
        # 单月同比根本不出现。
        # 新理由是加总关系：`mix` 的 total 与 parts 必须能逐月对得上账
        # （底座在 `ex_mix_share` 里复算，对不上就硬失败），而「同一组、同一单位」
        # 正是这条关系成立的前提 —— 分到两组等于把它们声明成彼此独立的序列。
        {'zh': 'MX 衍生品 ADV' + _since('mx_adv_contracts'), 'cols': [
            {'col': 'mx_adv_contracts', 'zh': '日均成交',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_futures_contracts', 'zh': '期货 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_options_contracts', 'zh': '期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'mx_adv_contracts',
            'parts': ['mx_adv_futures_contracts', 'mx_adv_options_contracts'],
            # 柱是当月日均（官方直接发布），次轴那条 12 个月滚动同比的合计取自
            'note': _NOTE_TTM_MX,
            'share_note': _NOTE_MIX_MX}},

        # 个股期货从「个股与 ETF 期权」里拆出来，落在这一组里 —— 它是**期货**不是期权，
        # 进不了那张期权占比图的分母，而在这里它正好是「期货 ADV」的四个分项之一。
        # 本组的合计 `mx_adv_futures_contracts` 声明在最上面那组（在那里它是
        # 「期货 vs 期权」的一个分项），跨组引用即可。
        #
        # 这一对与 Exhibit 4/5 是**同一条线索的下一层**：4/5 说 MX 的量里期货占多少，
        # 这一对说期货那一块里利率、股指、个股各占多少 —— 也就是「MX 到底是一家做什么的
        # 交易所」。四个分项之和与合计的残差实测在千分之二以内（官方未单列的其余期货）。
        {'zh': '期货 ADV：按产品拆', 'cols': [
            {'col': 'mx_adv_share_futures_contracts', 'zh': '个股期货 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'mx_adv_futures_contracts',
            # 顺序 = 自下而上：两条利率腿在下、股票腿在上，与「利率 vs 股票」对齐，
            # 和「MX 月末未平仓」那张的分段顺序是同一条业务分界。
            'parts': ['mx_adv_stir_futures_contracts', 'mx_adv_bond_futures_contracts',
                      'mx_adv_index_futures_contracts', 'mx_adv_share_futures_contracts'],
            'residual_zh': '其他期货（官方未单列）',
            'share_note': _NOTE_MIX_FUT}},

        # 当月合计单独一列、单位 contracts/month，本表里没有第二条同单位的列可以同轴，
        # 所以它注定是 gs_bar + 单月同比。**口径写进组名**（组名会进图题）：
        # 契约允许用单月同比，条件是标题里声明（CONTRACT.md §6）。
        # 这一组只有这一列，所以声明不会误标到别的图上。
        {'zh': 'MX 当月成交总量（次轴：单月同比）', 'cols': [
            {'col': 'mx_volume_contracts', 'zh': '当月成交',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 存量单列一组：点对点同比对期末口径是合法读法，这里保留它。
        # ⚠ 给下一个改这里的人：**「存量不能做滚动」是一句错话**。12 个月合计比恒等于
        #   12 个月均值比（除数 12 约掉，build/yoy.py 实测差 2.3e-14），所以存量序列
        #   画滚动窗口同比在数值上完全正确 —— 错的只是**把它叫「合计」**
        #   （12 个月末未平仓相加不指代任何真实的量）。要平滑就走
        #   `yoy.ttm_mean_yoy(s, kind)` 并写成「12 个月滚动**均值**同比」。
        # 本组只声明合计那一条列，五个分项都引用自后面各自的组 —— mix 的 total/parts
        # 写的是**列名**，跨组引用即可。五段 + 一段残差正好用满本仓全部 6 个数据色，
        # 是 `MIX_SEG_COLORS` 的硬上限；再多一档就得先在这里把小块并进残差。
        {'zh': 'MX 月末未平仓（存量，期末口径）', 'cols': [
            {'col': 'mx_oi_contracts', 'zh': '月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
         ], 'mix': {
            'total': 'mx_oi_contracts',
            # 顺序 = 自下而上的堆叠顺序：两条利率腿在下、股票期权两腿在上，
            # 与「利率 vs 股票」这条业务分界对齐，读者不用在图上跳着找。
            'parts': ['mx_oi_stir_futures_contracts', 'mx_oi_bond_futures_contracts',
                      'mx_oi_sxf_contracts', 'mx_oi_equity_options_contracts',
                      'mx_oi_etf_options_contracts'],
            'residual_zh': '其他（个股期货、股指期权等，本仓未单列）',
            'share_note': _NOTE_MIX_OI_ALL}},

        # 本页第二重要的一张：基准利率换代时旗舰合约的整体搬迁。
        {'zh': '短端利率 ADV：BAX → CORRA 迁移', 'cols': [
            {'col': 'mx_adv_stir_futures_contracts', 'zh': '短端利率合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_bax_contracts', 'zh': 'BAX（CDOR，已停）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cra_contracts', 'zh': 'CRA（CORRA）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'mx_adv_stir_futures_contracts',
            'parts': ['mx_adv_bax_contracts', 'mx_adv_cra_contracts'],
            'residual_zh': '其他短端利率合约（官方未单列）',
            'share_note': _NOTE_MIX_STIR}},

        {'zh': '短端利率月末未平仓', 'cols': [
            {'col': 'mx_oi_stir_futures_contracts', 'zh': '短端利率合计',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_bax_contracts', 'zh': 'BAX（CDOR，已停）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cra_contracts', 'zh': 'CRA（CORRA）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
         ], 'mix': {
            # 存量的 mix 不给 granularity / total_col / weight_col：那三个是给
            # 「12 个月滚动合计」用的，而 12 个月末快照相加不指代任何量（CONTRACT §6.1
            # 第 4 条）。存量柱的次轴走点对点同比，底座自己认得。
            'total': 'mx_oi_stir_futures_contracts',
            'parts': ['mx_oi_bax_contracts', 'mx_oi_cra_contracts'],
            'residual_zh': '其他短端利率合约（官方未单列）',
            'share_note': _NOTE_MIX_STIR_OI}},

        {'zh': '国债期货 ADV', 'cols': [
            {'col': 'mx_adv_bond_futures_contracts', 'zh': '国债期货合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgb_contracts', 'zh': 'CGB（10 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgf_contracts', 'zh': 'CGF（5 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgz_contracts', 'zh': 'CGZ（2 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'mx_adv_bond_futures_contracts',
            'parts': ['mx_adv_cgb_contracts', 'mx_adv_cgf_contracts',
                      'mx_adv_cgz_contracts'],
            'residual_zh': '其他国债期货（LGB 等，官方未单列）',
            'share_note': _NOTE_MIX_BOND}},

        # ⚠ 这一组曾经只有「合计 + CGB」两条，于是合计与 CGB 之间那条越拉越宽的口子
        #   读起来像「其余合约」（2024 年起中位 41%）。它不是 —— 那是本仓 MX_SPEC
        #   当时没登记 CGF / CGZ 的 OI 格子，是**管道边界**冒充官方的披露边界。
        #   两列补齐后三档与合计逐月闭合，剩下的只有 LGB（见 _NOTE_BOND_OI）。
        #   ⚠️ 上一版这条注释的末句写着「stock 列在底座里每列各出一张 gs_bar，所以
        #   『合计 vs 三档』要在页尾核对表上对，不在图上」—— 那句话在 `groups[].mix`
        #   进底座之后**不再成立**：下面这条 mix 就是把它画在图上，残差段只剩 LGB。
        {'zh': '国债期货月末未平仓', 'cols': [
            {'col': 'mx_oi_bond_futures_contracts', 'zh': '国债期货合计',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cgb_contracts', 'zh': 'CGB（10 年）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cgf_contracts', 'zh': 'CGF（5 年）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cgz_contracts', 'zh': 'CGZ（2 年）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
         ], 'mix': {
            'total': 'mx_oi_bond_futures_contracts',
            'parts': ['mx_oi_cgb_contracts', 'mx_oi_cgf_contracts',
                      'mx_oi_cgz_contracts'],
            # 残差就是 LGB（30 年），官方在 Bond Futures 小节里不给它单开一栏。
            # 三档补齐之前这一段占到四成上下，那时它是本页最大的一块未归属段；
            # 现在它落到千分之几 —— 图上看不见，图注会自己说破。
            'residual_zh': 'LGB（30 年，官方未在本表单列）',
            'share_note': _NOTE_MIX_BOND_OI}},

        {'zh': '股指期货', 'cols': [
            {'col': 'mx_adv_index_futures_contracts', 'zh': '股指期货合计 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_sxf_contracts', 'zh': 'SXF（S&P/TSX 60）ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_oi_sxf_contracts', 'zh': 'SXF 月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
         ], 'mix': {
            # SXF OI 是存量、不进这张流量占比图（单位与口径都不同），
            # 它照旧单独成一张存量柱图。
            'total': 'mx_adv_index_futures_contracts',
            'parts': ['mx_adv_sxf_contracts'],
            'residual_zh': '其他股指期货（SXM 迷你等，官方未单列）',
            # SXF 常年占九成半以上，两段的信息全在那一小段残差上，而它在 0–100 的堆叠里
            # 只有几个像素高 —— 右轴那条线就是把它换个刻度重画一遍。
            'rhs_share': 'residual',
            'share_note': _NOTE_MIX_INDEX}},

        # ⚠️ 组名说的是**分母**，不是这两条分项：本组的 mix 把整条「期权 ADV」当合计，
        # 而个股与 ETF 只是它的两个分项（另有一段拆不开的残差，见 _NOTE_MIX_OPT）。
        # 组名进图题，写成「个股与 ETF 期权」会让人以为期权合计 = 个股 + ETF。
        # 合计列 `mx_adv_options_contracts` 声明在最上面那组（它在那里是「期货 vs 期权」
        # 占比图的一个分项）—— mix 的 total/parts 写的是**列名**，引用即可，
        # 不在这里再写一份列配置（两份 unit/fmt 迟早分叉）。
        {'zh': 'MX 期权：个股与 ETF 构成', 'cols': [
            {'col': 'mx_adv_equity_options_contracts', 'zh': '个股期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_etf_options_contracts', 'zh': 'ETF 期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
         ], 'mix': {
            'total': 'mx_adv_options_contracts',
            'parts': ['mx_adv_equity_options_contracts', 'mx_adv_etf_options_contracts'],
            'residual_zh': '其他期权（本仓未入库的那几节）',
            'share_note': _NOTE_MIX_OPT}},

        # 两条期权未平仓单独成组：它们是存量，与上面那张 ADV 占比图不同口径也不同单位，
        # 而且官方没有发「期权未平仓合计」，凑不出分母，所以这一组不带 mix。
        {'zh': '个股与 ETF 期权月末未平仓', 'cols': [
            {'col': 'mx_oi_equity_options_contracts', 'zh': '个股期权月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_etf_options_contracts', 'zh': 'ETF 期权月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},


        # ── 以下全是慢腿（2021-08 起，比 MX 晚一档发布）────────────────
        {'zh': '加拿大现货成交额' + _since('tsx_value_cad', '慢腿'), 'cols': [
            {'col': 'tmx_all_value_cad', 'zh': 'TMX 合计',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'tsx_value_cad', 'zh': 'TSX',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'tsxv_value_cad', 'zh': 'TSX Venture',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'alpha_value_cad', 'zh': 'TSX Alpha',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
         ], 'mix': {
            'total': 'tmx_all_value_cad',
            'parts': ['tsx_value_cad', 'tsxv_value_cad', 'alpha_value_cad'],
            'residual_zh': 'Alpha-X & Alpha DRK（2023-11 起计入合计）',
            # 成交**额**这一张（而不是股数/笔数那两张）要右轴线：按金额算 TSX 常年占
            # 八成半到九成半，其余三档被压在顶上不到 15pp 里，谁在动完全量不出来。
            # 挑 TSX Alpha 而不是别的两段：它是三者里最大、也是唯一有明显结构位移的一档。
            'rhs_share': 'alpha_value_cad',
            'share_note': _NOTE_MIX_SPOT}},

        {'zh': '加拿大现货成交股数' + _since('tsx_volume_shares', '慢腿'), 'cols': [
            {'col': 'tmx_all_volume_shares', 'zh': 'TMX 合计',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'tsx_volume_shares', 'zh': 'TSX',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'tsxv_volume_shares', 'zh': 'TSX Venture',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'alpha_volume_shares', 'zh': 'TSX Alpha',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         ], 'mix': {
            'total': 'tmx_all_volume_shares',
            'parts': ['tsx_volume_shares', 'tsxv_volume_shares', 'alpha_volume_shares'],
            'residual_zh': 'Alpha-X & Alpha DRK（2023-11 起计入合计）',
            'note': _NOTE_TTM_SPOT,
            'share_note': _NOTE_MIX_SPOT}},

        {'zh': '加拿大现货成交笔数' + _since('tsx_transactions', '慢腿'), 'cols': [
            {'col': 'tmx_all_transactions', 'zh': 'TMX 合计',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'tsx_transactions', 'zh': 'TSX',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'tsxv_transactions', 'zh': 'TSX Venture',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'alpha_transactions', 'zh': 'TSX Alpha',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
         ], 'mix': {
            'total': 'tmx_all_transactions',
            'parts': ['tsx_transactions', 'tsxv_transactions', 'alpha_transactions'],
            'residual_zh': 'Alpha-X & Alpha DRK（2023-11 起计入合计）',
            'share_note': _NOTE_MIX_SPOT}},

        {'zh': '月末指数点位' + _since('tsx_composite_close', '慢腿'), 'cols': [
            {'col': 'tsx_composite_close', 'zh': 'S&P/TSX Composite',
             'unit': 'index level', 'fmt': 'f0c', 'stock': True},
            {'col': 'tsxv_composite_close', 'zh': 'S&P/TSX Venture Composite',
             'unit': 'index level', 'fmt': 'f1', 'stock': True},
        ]},

        # 三列三个单位 ⇒ 三个单桶 ⇒ 三张 gs_bar，次轴都是单月同比，而本表里
        # 没有任何同单位的第二条列可以同轴（Alpha-X&DRK 只有这一档）。
        # 所以口径写进组名 —— 这一组的三张图全都适用，不会误标到别处。
        # 实测（tools/check_yoy_caliber.py）：成交额那条有 1 个月与滚动口径符号相反
        # （2025-12 单月 −2.8% 而滚动 +83.2%）。
        {'zh': 'Alpha-X & Alpha DRK'
         + _since('alphax_drk_volume_shares', '慢腿；次轴：单月同比'), 'cols': [
            {'col': 'alphax_drk_value_cad', 'zh': '成交额',
             'unit': 'C$bn/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'alphax_drk_volume_shares', 'zh': '成交股数',
             'unit': 'bn shares/month', 'fmt': 'f3', 'scale': 1e-9},
            {'col': 'alphax_drk_transactions', 'zh': '成交笔数',
             'unit': 'mn trades/month', 'fmt': 'f3', 'scale': 1e-6},
        ]},
    ],

    # 17 条现货列全部是慢腿：它们与 MX 不同源、晚一档发布，最新月留空是正常状态。
    # 不这么标，整页的发布门槛会被现货那半边永久拖住一个月。
    'slow_cols': [
        'tmx_all_volume_shares', 'tmx_all_value_cad', 'tmx_all_transactions',
        'tsx_volume_shares', 'tsx_value_cad', 'tsx_transactions', 'tsx_composite_close',
        'tsxv_volume_shares', 'tsxv_value_cad', 'tsxv_transactions', 'tsxv_composite_close',
        'alpha_volume_shares', 'alpha_value_cad', 'alpha_transactions',
        'alphax_drk_volume_shares', 'alphax_drk_value_cad', 'alphax_drk_transactions',
    ],

    'breaks': _breaks(),

    # ══ 量价分解：三张图，同一个业务（TSX 主板）三个视角 ══════════════════════
    # 为什么是 TSX 而不是 TMX 合计、为什么三因子拆成两张图，见模块 docstring。
    # 三张都 granularity='monthly_total'：series/tmx.csv 的现货三类列都是**原始月度合计**
    # （量级见页尾 notes 里那条现算的举例，11–12 位数），不是日均。
    # ⇒ 一律**不给** weight_col：声明 monthly_total 又给 weight_col 是硬失败，
    #   而真乘上去会把年度合计放大二十几倍，图形却照常画得出来。
    # scale 只做显示换算（金额 ×1e-9 → C$bn、股数 ×1e-9 → bn shares、笔数 ×1e-6 → mn trades），
    # 它在分子分母上同时出现，对分解结果一个数都不影响。
    'decomp': [
        # ── 图 A：量 × 价。派生量是成交量加权平均成交价 ⇒ kind='share_price'。
        {'zh': 'TSX 主板成交额',
         'kind': 'share_price',
         'granularity': 'monthly_total',
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_volume_shares', 'zh': 'TSX 成交股数',
                 'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         # C$bn ÷ bn shares = C$/股，两边的 1e9 自己抵掉 ⇒ price_scale 用缺省 1.0。
         'price_zh': '加权平均成交价',
         'price_unit': 'C$/share',
         'price_fmt': 'f2',
         # TMX 的财年就是日历年（10-K/年报截至 12-31）⇒ year_start_month=1。
         # 日历年下 year_label 只能是 'start'（底座硬失败挡 'end'），
         # 而且日历年的柱标签直接印年份、不带 FY 前缀，不存在偏一年的风险。
         'year_start_month': 1, 'year_label': 'start',
         # 用户指令（2026-08-07）：四家分解图统一「4 根完整日历年柱 + 1 根当年 YTD」。
         # 底座取 run[-(years+1):] 个完整年 ⇒ 至多 years 根柱；最新年不完整时自动补
         # YTD 柱（两侧月份对齐去年同期，见 single._ytd）。
         # ⚠ 现货回补到 2015-01 之后完整日历年有 11 个，**画的仍然只有 4 根** ——
         #   图注里 _index_split() / _three_factor() 也切到同样的 _DECOMP_YEARS，
         #   否则会出现「图注报 10 年、图上 4 根柱」的对不上。
         'years': _DECOMP_YEARS,
         'note': _NOTE_PRICE},

        # ── 图 B：笔数 × 每笔金额。派生量是每笔平均成交额 ⇒ kind='per_trade'。
        #    ⚠ 绝不能写 share_price：底座会据 kind 印出「它不是什么」那段话，
        #      把「订单碎片化程度」说成「价格」是本批最容易犯的错。
        {'zh': 'TSX 主板成交额（按成交笔数拆）',
         'kind': 'per_trade',
         'granularity': 'monthly_total',
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_transactions', 'zh': 'TSX 成交笔数',
                 'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
         # C$bn ÷ mn trades = 1e-3 × (C$/笔) ⇒ price_scale=1e3 换回 C$/笔。
         # 纯单位换算，对增长率没有任何影响，只决定图注里报出来的水平值读数。
         'price_zh': '每笔平均成交额',
         'price_unit': 'C$/trade',
         'price_fmt': 'f0c', 'price_scale': 1e3,
         # 同图 A：_DECOMP_YEARS 根完整日历年柱 + YTD（数据够时）。
         'year_start_month': 1, 'year_label': 'start', 'years': _DECOMP_YEARS,
         'note': _NOTE_TRADE},

        # ── 图 C：三分法。bench = TMX 集团合计，子集关系逐月精确成立（见 _NOTE_SHARE）。
        #    行业块 = 集团整体在动多少；份额块 = TSX 在集团里的股数份额；
        #    结构块 = TSX 均价相对集团（成交在贵票 / 仙股之间的迁移）。
        #    ⚠ bench 两列必须与自家两列**同一套 granularity / 同样不给 weight_col**，
        #      否则份额 s 会带一条逐月漂移的假趋势。
        {'zh': 'TSX 主板成交额（相对 TMX 集团）',
         'kind': 'share_price',
         'granularity': 'monthly_total',
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_volume_shares', 'zh': 'TSX 成交股数',
                 'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         'bench_value': {'col': 'tmx_all_value_cad', 'zh': 'TMX 集团合计成交额',
                         'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'bench_qty': {'col': 'tmx_all_volume_shares', 'zh': 'TMX 集团合计成交股数',
                       'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         'share_zh': 'TSX 在集团内的股数份额',
         'mix_zh': 'TSX 均价相对集团（品种结构）',
         'price_zh': '加权平均成交价',
         'price_unit': 'C$/share',
         'price_fmt': 'f2',
         # 同图 A：_DECOMP_YEARS 根完整日历年柱 + YTD（数据够时）。
         'year_start_month': 1, 'year_label': 'start', 'years': _DECOMP_YEARS,
         'note': _NOTE_SHARE},
    ],

    # ══ 为什么没有 'ttm_yoy' 段 ═════════════════════════════════════════════
    # 曾经有两条：「MX 衍生品成交量」与「TMX 合计现货成交股数」，都是
    # 「水平值柱 + 12 个月滚动同比」。2026-09 改版之后这两张图**原样**由
    # `groups[].mix` 的第一张（合计柱）产出：
    #   · MX 那条 → 最上面那组的 mix（total=mx_adv_contracts、
    #     total_col=mx_volume_contracts，与原来逐字相同，_NOTE_TTM_MX 也搬了过去）；
    #   · 现货那条 → 「加拿大现货成交股数」那组的 mix（total=tmx_all_volume_shares、
    #     granularity='monthly_total'，同样把 _NOTE_TTM_SPOT 搬了过去）。
    # 留在 'ttm_yoy' 里会画出**第二张一模一样的图**（底座把 ttm_yoy 追加在全部
    # exhibit 之后，不会去重），所以在这里删掉，而不是在底座里加一条去重规则。

    'notes': [
        _SEG
        # ⚠️ 下面只列**查过来路**的那几段，所以主语写「下面这几段」而不是「各段」——
        # 上一版把它写成「各段各有各的地板」，而列出来的只有三条（月末指数点位那一段
        # 没查过），一句全称断言被紧挨着的名单当场证伪。加一段就把它的地板补进来。
        + '⚠️ 下面这几段的地板都是**源的地板**、不是本页的取舍：'
        'MX 的 m-x.ca 月度 xlsx 到 2002-01 为止（2001-12 及更早干净 404）；'
        '现货到 2015-01 为止（CIRO 官方页面写明 2007–2014 的报表需人工索取）；'
        'Alpha-X & Alpha DRK 到 2023-11 为止（TMX 与 CIRO 两个互相独立的源'
        '**同一个起点**，说明这两个盘口此前不单独披露，不是我们漏解析）。',

        '现货比 MX 晚一档发布：每月初都会出现「MX 已有上月、现货还没发」的正常状态。'
        '所以 17 条现货列全部标为 slow_cols，最新月留空是正常状态，不参与发布门槛。',

        f'**{_SRC_SWITCH} 现货 12 列换过数据源**：之前是监管方 CIRO 的'
        '『Report of Marketshare by Marketplace (Historical 2015–Present)』，'
        '之后是 TMX 自己的 Consolidated Trading Statistics 新闻稿。'
        'TMX 自家 2021-08 之前的月度明细只挂在 tmx.com/en/resource 的 PDF 上，'
        '该域对本网络整段返回 CloudFront 403（curl / urllib / nscurl / curl_cffi / '
        '本机真实 Chrome 实测全部 403），至今没有合规通道 —— 所以历史只能由监管方补。'
        '两把尺子不完全一样：60 个重叠月（2021-08~2026-07）逐月比过，'
        '笔数三列与 TSXV 三列的比值中位数是 1.00000（多数月逐位相同），'
        '而 tsx_volume_shares 是 0.98683、tsx_value_cad 1.00162、alpha_value_cad 1.00249 ——'
        '**量偏低、额偏高，方向相反**，所以不是「含不含大宗对敲」那种可加减的一块，'
        '是两家各自的统计口径。接缝处的纯口径台阶：tsx_volume_shares −1.62%、'
        'TMX 合计股数 −0.98%，三条成交额 +0.15%~+0.17%，其余 7 列 |台阶| ≤0.11%。'
        f'⇒ 图上只给前两条列画 {_SRC_SWITCH} 的红色竖虚线（标签「{_SRC_ZH}」），'
        '其余列跨这个月是可比的，画了等于说假话。'
        '**回补只往左填空、不覆盖已有值**：2021-08 起印在图上的仍是 TMX 官方新闻稿的原值。'
        '⚠️ 2021 是拼接年（1–7 月 CIRO、8–12 月 TMX 自报），'
        '所以三张分解图里跨 2021→2022 那一格的股数增速被抬高约 0.75pp（TMX 合计 0.35pp），'
        '成交额一侧 ≤0.07pp。照实说明，不做剔除 —— 剔除等于自造一条谁也没发过的序列。',

        '短端利率合约在 2024-07 完成基准换代：CDOR 停用，BAX 的 ADV 自该月起为 0'
        '（最后一个非零月是 2024-06），CORRA 合约 CRA 接棒。'
        f'实测 {_lm("mx_adv_cra_contracts")}：'
        f'CRA ADV {_lv("mx_adv_cra_contracts")} 张/日、'
        f'BAX {_lv("mx_adv_bax_contracts")}、'
        f'短端利率合计 {_lv("mx_adv_stir_futures_contracts")} 张/日。'
        '本页把 BAX 与 CRA 画在一起而不是各画各的 —— 只看其中一条会得到「短端利率业务'
        '归零」或「凭空长出一个新产品」两个都不对的结论。断点月份由 series/tmx.csv '
        '里 BAX 转 0 的那一月读出，没有写死。'
        '图上那条红线的标签只写「BAX→CORRA 迁移」——**标签的职责是标记位置**，'
        '来龙去脉在这一条里；标签写长了会竖排压住图上的读数'
        '（断点线的全长就是绘图区高度，柱图那几张正中间还钉着柱值标签）。'
        '这条线<b>只画在短端利率那 ' + str(len(_BAX_COLS)) + ' 列的图上</b>：'
        '它是产品替换不是集团口径变化，MX 合计跨这个月是连续的（BAX 掉多少 CRA 接多少），'
        '画到指数点位、现货成交这些图上就是错的。',

        _NOTE_BOND_OI,

        'TMX 合计口径在 2023-11 变大：Alpha-X & Alpha DRK 自该月起单独披露并计入合计。'
        '实测恒等式核过 —— 2023-10 及之前 tmx_all_volume_shares 恰等于 TSX + TSXV + Alpha 三家之和'
        '（差为 0）；2023-11 起恰等于三家 + Alpha-X&DRK'
        f'（{_lm("alphax_drk_volume_shares")} 该项 '
        f'{_lv("alphax_drk_volume_shares")} 股）。'
        '所以合计序列跨 2023-11 不可直连。'
        '图上那条红线的标签只写「TMX 合计口径扩容」（理由同上：标签要短），'
        '且**只画在受影响的六列上** —— TMX 合计三列（覆盖范围变大）与 Alpha-X&DRK 三列'
        '（序列自此开始）。TSX / TSXV / Alpha 三档一列都没变，它们的图上不该有这条线。',

        '**现货三类列在 series/tmx.csv 里是原始单位**：实测 '
        f'{_lm("tsx_value_cad")} '
        f'tsx_value_cad = {_lv("tsx_value_cad")}（加元）、'
        f'tsx_volume_shares = {_lv("tsx_volume_shares")}（股）、'
        f'tsx_transactions = {_lv("tsx_transactions")}（笔）。'
        '直接上图轴刻度会是 11–12 位数，'
        '所以本页用 spec 的 scale 字段做**纯显示换算**：金额 ×1e-9 → C$bn、'
        '股数 ×1e-9 → bn shares、笔数 ×1e-6 → mn trades。'
        'scale 只影响本页的显示，series/tmx.csv 与 build/notional.py 读到的仍是原值，'
        '删掉本文件这些除数即随之消失，不碰任何公共代码。'
        f'MX 那半边的张数（{_lm("mx_adv_contracts")} ADV '
        f'{_lv("mx_adv_contracts")} 张/日）量级本来就可读，不做换算。',

        'BOX 期权做不出月度序列：TMX 官方只在季度 MD&A 里按季披露（series/tmx_box_q.csv，'
        '实测 8 行 2024-Q3 → 2026-Q2），BOX 自身站点也不发月度统计。'
        '本页是月频页，不收季频列。',

        '本页全部金额为加元。跨币种比较由 build/notional.py 统一换算：'
        '流量（成交额、成交股数/笔数）配月均汇率，存量（月末未平仓、月末指数点位）配月末汇率。',

        '未上页面的月频列：mx_adv_index_options_contracts（最后一个非零月 '
        f'{_zero_tail("mx_adv_index_options_contracts")[0] or "（未知）"}，此后连续 '
        f'{_zero_tail("mx_adv_index_options_contracts")[1]} 个月全为 0 的死列）、'
        'trading_days_rates 与 trading_days_equity'
        + ('（两套分母，' + (_TDAY_MISMATCH or '两者并非逐月相等')
           + '；ADV 官方直接给，本页不做除法）。'),
    ],
}
