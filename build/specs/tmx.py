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
  2. 现货那半边的列、连同两条月末指数点位，全部进 `slow_cols`（名单只有一份：
     `_SLOW_COLS`，页尾那条 note 的条数由它 len() 现算 —— 别在散文里另写一个数，
     上一版写死的「17 条现货列」就把两条指数点位错算成了现货列）。
     它们比 MX 晚一档发布，最新月留空是**正常状态**，不是解析失败，
     绝不能参与发布门槛判定。

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

⚠ **两张分解图里跨换源的那 12 格带着口径失真。**它们的本期在 2021-08 之后、
基期在 2021-08 之前，各自站在两把尺子的两侧（月份由 `_splice_note()` 按换源月现算，
这里不写死）。⚠️ 2026-09 之前这里写的是「三张分解图里跨 2021→2022 **那一格**，
股数增速被抬高 0.75pp / 0.35pp / ≤0.07pp」—— 那三个数量的是**年度柱**
（2021 那一整年半年一把尺子），而分解图改月度桶之后一根年度柱都没有了，
搬到月度格上就是假话，所以随年度桶一起删掉。台阶逐列量过多大写在页尾
「口径与方法说明」那一条里。图注里照实说，不做剔除。

━━ BOX 期权：本页做不出来 ━━
TMX 官方**只按季度**披露 BOX（季度 MD&A 里的「最近八个季度」表），没有任何月度口径，
BOX 自己的站点也不发月度统计。它落在 series/tmx_box_q.csv（quarter 列，
实测 8 行：2024-Q3 → 2026-Q2），与本页契约的月频 groups 不兼容。
硬塞进来要么改契约、要么在底座里为 TMX 开一条季频分支 —— 两者都违背
「删掉不留残渣、不许 if ticker == 'tmx'」。要做就另起一页，不缠这一页。

━━ 量价分解：为什么两张图都画 TSX 主板，而不是 TMX 合计 ━━
本页现货侧有 TMX 合计 / TSX / TSXV / Alpha / Alpha-X&DRK 五档，每一档都有
**金额 + 股数 + 笔数**三列成对（全仓唯一一家）。分解图一律取 **TSX 主板**，两个理由：

  1. **只有 TSX 配得上指数。**series/tmx.csv 里的 `tsx_composite_close` 是
     S&P/TSX Composite —— 它的成分就是 TSX 主板的票。拿它去除 TMX 合计的均价，
     分母里混着 TSXV 的仙股（本文件 `_venue_price()` 现算：TSXV 均价中位数不到
     1 C$/股，TSX 是它的几十倍），得到的「结构效应」里有一大截只是 venue 混合比例。
     ⚠️ 这条现算证据 2026-09 之前印在三分法那张图的图注里，那张图删掉之后
     **搬进了 `_NOTE_PRICE`**（量 × 价那张）—— 它本来就是「为什么画 TSX」的论据，
     跟着被删的图一起消失等于把自己的论据删了。
  2. **TSX 自己没有口径断点。**TMX 合计在 2023-11 纳入 Alpha-X & Alpha DRK
     （见 `_breaks()`），TSX 那一列从头到尾同口径。

⚠️ 2026-09 之前这里还有一句「TMX 合计并没有因此消失：它是第三张图（三分法）的
**bench**」—— 三分法那张图本轮删掉了（理由见页尾那条历史账），这句话随之作废。
TMX 合计在本页仍然到处都是（现货三组的合计柱与三张 100% 占比堆叠的分母都是它），
只是不再以「分解图的 bench」这个身份出现。

━━ 分解图为什么需要一个「锚点组」━━
两张分解图走 `bucket='monthly'`，而底座对月度桶有一道硬现验：本页必须有**唯一一张**
「该金额列（`tsx_value_cad`）的水平值 + 次轴单月同比、且横轴与分解图逐格相同」的图，
否则 SpecError。有它，分解图的图注才敢说「菱形与那张图的金线是同一条数」「可以逐格
上下对读同一个月」。所以 groups 里专门有一组「TSX 主板成交额」只放这一条列 ——
它不是装饰，删掉它两张分解图当场硬失败。
⚠️ `tsx_value_cad` 的列配置因此**只在那一组里声明一次**，「加拿大现货成交额」那组的
mix 用跨组引用取它（同下面那条「有两条 mix 跨组引用」的写法）。两处各写一份会让
`by_name`（后者覆盖）与末尾核对表（前者优先）取舍相反，同一条列在图例与表头上印两个
名字，而没有任何护栏会响。

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

━━ 图列：一组「合计柱 + 分项 100% 占比堆叠」，合计已被开篇图画过的那组只出后一张 ━━
2026-09 改版。用户给的两条原则：
  1. 月度数据尽量画**柱状图**，并在同一张图上叠一条同比折线；
  2. 像旧 Ex4 那样「合计 + 期货/期权」的组，先给合计一张柱 + 同比，再给分项一张占比图。

落地方式是底座新增的 `groups[].mix`（`build/single.py`，spec 驱动、不含任何
`if ticker == 'tmx'`）：声明 `total` 与 `parts` 两个**列名**，底座就出图 ——
合计那张是 `gs_bar` + 次轴同比，分项那张是 `stacked_dual` 的 100% 堆叠。

⚠️ **合计柱不是无条件出的，本页正好撞上那个例外。**本页头条列
（`mx_adv_contracts`，`headline_style='bar_yoy'`）与最上面那组 `mix` 的 `total` 是
**同一列**，于是开篇那张全历史柱已经把它画过了；组内那张合计柱只是同一条序列
换一个更窄的窗口再画一遍，重叠的那一段逐点相等。2026-09 页面所有者拍板并成一张
（底座原本在页尾自己印过一段「要不要并成一张由页面所有者定」），所以底座现在会先查
`log_yoy_bar` 那本账：合计列的窗口被别处那张 `bar_yoy` **真包含**时不出合计柱，
占比图顶上来，图注里那句「合计的绝对量看 Exhibit k」改指开篇那张
（见 `build/single.py` 的 `Page.total_drawn_wider`）。
「真包含」不是「覆盖」：两张的横轴**逐格相同**那一档照旧是底座的硬失败
（`log_yoy_bar`：两张一字不差，请从 spec 里删掉其中一条），底座不替 spec 删图。
这是**现算的事实判定**，不是本文件里的一个开关 —— spec 里一个新键都没加，
头条哪天换成别的列，这一组的合计柱自己就回来了。
⇒ **本文件里不许写「每组两张」「本页共几张图」这类数**，见下一段的同一条教训。
同比口径不是排版偏好，由列的性质定（CONTRACT §6.1）：
流量走**单月同比**（第 1 条，2026-09 起全站统一，页面所有者指定 —— 本页一条
12 个月滚动同比都不画），存量走**点对点同比**（第 2 条，12 个月末快照相加不指代任何量）。

于是本页除了量价分解（`decomp`）与季节性之外，**再没有多列折线对比图**：
（**这里同样不写张数、不写桶** —— 分解图 2026-09 已从年度桶改月度桶，
写死「三张年度量价分解」的上一版当场变成两处假话。）
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


def _dense_zh(col):
    """「YYYY-MM 起逐月无洞（实测 N/N）」—— 有洞就照实说有几个洞。

    ⚠️ 这句话上一版把「295/295」**写死**在图注与两处注释里。那个数每回补一个月就加一，
    2026-08 的数据到货之后它原地变成假话，而没有任何护栏会响（图注只是字符串）。
    分子分母都从 CSV 现算，顺带把「无洞」这个断言也变成可证伪的：真有洞就换一句话说。
    """
    ms = [r['month'] for r in _rows() if col in r and r[col].strip()]
    if not ms:
        return '（本次未能从 CSV 读出这一列）'
    y0, m0 = int(ms[0][:4]), int(ms[0][5:7])
    y1, m1 = int(ms[-1][:4]), int(ms[-1][5:7])
    span = (y1 - y0) * 12 + (m1 - m0) + 1
    if len(ms) == span:
        return f'{ms[0]} 起逐月无洞（实测 {len(ms)}/{span}）'
    return (f'{ms[0]} → {ms[-1]} 这 {span} 个月里有 {len(ms)} 个月有值'
            f'（缺 {span - len(ms)} 个月，源里就没有）')


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

#: ⚠️ 2026-09 删掉的 `_DECOMP_YEARS = 4`（连同 `_cal_years()`）：两张分解图改走
#: 底座的 `bucket='monthly'` 之后，图上一根**年度柱**都没有了 —— 「画几根完整日历年柱」
#: 这个量在月度桶里不存在，留着一个谁也不读的常量只会让下一个人以为还有年度分支。
#: 现在图注里那几组读数由下面的 `_mon_cells()` 按**月度同比格**现算，见 `_index_split()`。


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


def _prev_m(m):
    """'2026-01' → '2025-12'。只服务下面那条时点敏感度，不做任何合法性检查。"""
    y, mm = int(m[:4]), int(m[5:])
    return f'{y - 1}-12' if mm == 1 else f'{y}-{mm - 1:02d}'


def _mon_cells(cols):
    """→ [(月份, {列: 本月值}, {列: 去年同月值}), …]：**算得出单月同比**的那些月。

    月度桶的一格 = 一个月，基期是**去年同月**（CONTRACT §6：全站只有这一种同比），
    所以这里不再按日历年分桶 —— 2026-09 两张分解图从年度桶改月度桶之后，
    `_cal_years()` 连同 `_DECOMP_YEARS` 一起删掉了，图注要报的读数改从这里出。

    ⚠️ **这不是图上那个窗口。**图上画哪几格由底座的 `win_long()`（左界是
    `build/single.py` 的 `WIN_FROM`）定，本文件看不见那个常量，也不该去猜。
    这里收的是「两侧都有值」的全部月份，所以下面每一处报数都必须把**格数与首末月**
    一起印出来，让读者自己对；一句「与图上那 N 格逐格相同」都不许写 ——
    要写就得有护栏，而这里没有护栏。（今天两者恰好都是 2016-01 起、128 格，
    因为现货列自 2015-01 起、恰好比 WIN_FROM 早整整一年 —— 恰好不是保证。）

    算不出返回 []。
    """
    by_m = {}
    for r in _rows():
        m = (r.get('month') or '').strip()
        if len(m) == 7 and m[4] == '-':
            by_m[m] = r
    out = []
    for m in sorted(by_m):
        b = f'{int(m[:4]) - 1}-{m[5:]}'
        r1, r0 = by_m[m], by_m.get(b)
        if r0 is None:
            continue
        a1 = {c: _num(r1, c) for c in cols}
        a0 = {c: _num(r0, c) for c in cols}
        if any(v is None for v in a1.values()) or any(v is None for v in a0.values()):
            continue
        out.append((m, a1, a0))
    return out


def _med_max(xs):
    """→ (中位, 最大, 最大值所在的那一格)；空表返回 (None, None, None)。"""
    if not xs:
        return None, None, None
    vs = sorted(v for _m, v in xs)
    hi = max(xs, key=lambda t: t[1])
    return vs[len(vs) // 2], hi[1], hi[0]


def _index_split():
    """把 TSX 均价的增长拆成「市场涨跌」与「品种结构」两截 —— 全仓只有这一家做得到。

    均价 P ≡ 成交额 ÷ 成交股数，它同时含（a）市场涨跌与（b）成交结构变化
    （贵票 vs 便宜票的成交占比此消彼长）。本仓其余做量价分解的页都没有这一层 ——
    它们的 series 里没有指数点位列（全仓只有 series/tmx.csv 有）。
    ⚠️ 2026-09 收口复核订正（`_NOTE_PRICE` 里有同一句的副本，两处同步改）：
    上一版这里写的是「JPX / SGX 两页的图注都只能说『均价里含结构效应，但本页拆不出
    它有多大』」。实测那句话**逐字只印在 data/jpx.js 上**（源头 build/specs/jpx.py），
    data/sgx.js 里「拆不出」「结构效应」「指数点位」各 0 次 —— SGX 那页的分解图注
    从头到尾没有这一层。把一句只有一页印过的话安到两页头上是引文不实，
    ⇒ 引文只归给真印过它的那一页。
    ⚠️ **别在这两处写「几家有 decomp」之类的家数**：build/specs/sgx.py 的 'decomp'
    上方记着同一条教训（那个数已经错过两轮），要当期实况就现跑那段循环。
    TMX 有 `tsx_composite_close`，而且它的成分正是 TSX 主板的票，所以这里能写成

        ln(P₁/P₀) = ln(I₁/I₀) + ln[(P/I)₁ ÷ (P/I)₀]
                     └ 市场涨跌 ┘   └── 品种结构（成交在贵票/便宜票之间的迁移）──┘

    两块再乘上与图上同一个重标定权重 w = g_额 ÷ ln(V₁/V₀)，于是它们**逐格相加
    恰好等于图上「均价的贡献」那一块**（单位同为百分点）。

    ⚠️ **月度版有一处年度版没有的时点错配，必须报出来、不许无声带过。**
    年度版的 I 取「该年 12 个月末点位的平均」，两侧都是一整年，勉强对得上分子那个
    「Σ金额 ÷ Σ股数」。月度版的 I 只能取**月末点位**（本页没有日频指数），而 P 是
    **当月成交量加权均价**（整个月的成交摊出来的），两者的时点根本不是同一个。
    差出来的那一截会被「品种结构」那一块**整段吸收** —— 结构块 = w(lP − lI)，
    lI 偏了多少，结构块就反向偏多少。
    这一层**仍然做**（它是本页相对 JPX/SGX 的唯一增量，也是「为什么画 TSX 而不是
    TMX 合计」那节论证的落点），代价改成**量出来写进图注**：这里同时按
    I' =（本月末 + 上月末）÷ 2 这个「当月平均水平」的粗代理再算一遍，
    把两版结构块的差报成敏感度。它不是修正、更不是更准的口径 ——
    它回答的是「换一个同样说得通的时点，这块会挪多少」。

    返回一个 dict（键见下面 `_NOTE_PRICE` 的用法）；算不出返回 None。
    """
    cells = _mon_cells(['tsx_value_cad', 'tsx_volume_shares', 'tsx_composite_close'])
    # 敏感度那一版还要上个月的点位 ⇒ 单独按月取一份收盘价。
    close = {}
    for r in _rows():
        m = (r.get('month') or '').strip()
        v = _num(r, 'tsx_composite_close')
        if len(m) == 7 and v:
            close[m] = v
    rows, mkt, mix, sens = [], [], [], []
    for m, a1, a0 in cells:
        try:
            V1, V0 = a1['tsx_value_cad'], a0['tsx_value_cad']
            Q1, Q0 = a1['tsx_volume_shares'], a0['tsx_volume_shares']
            I1, I0 = a1['tsx_composite_close'], a0['tsx_composite_close']
            if min(V1, V0, Q1, Q0, I1, I0) <= 0:
                continue
            lV = math.log(V1 / V0)
            if abs(lV) < 1e-6:          # 与底座 DECOMP_LN_MIN 同一条：w 此时是 0/0
                continue
            w = (V1 / V0 - 1.0) / lV
            lP = math.log((V1 / Q1) / (V0 / Q0))
            lI = math.log(I1 / I0)
            rows.append((m, w * lP * 100, w * lI * 100, w * (lP - lI) * 100))
            mkt.append((m, abs(w * lI * 100)))
            mix.append((m, abs(w * (lP - lI) * 100)))
            p1, p0 = _prev_m(m), _prev_m(f'{int(m[:4]) - 1}-{m[5:]}')
            c1, c0 = close.get(p1), close.get(p0)
            if c1 and c0:
                lI2 = math.log(((I1 + c1) / 2.0) / ((I0 + c0) / 2.0))
                sens.append((m, abs(w * (lI2 - lI) * 100)))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    if not rows:
        return None
    mk_med, mk_max, mk_at = _med_max(mkt)
    mx_med, mx_max, mx_at = _med_max(mix)
    se_med, se_max, se_at = _med_max(sens)
    return {'n': len(rows), 'm0': rows[0][0], 'm1': rows[-1][0],
            'last': rows[-1],
            'mk_med': mk_med, 'mk_max': mk_max, 'mk_at': mk_at,
            'mx_med': mx_med, 'mx_max': mx_max, 'mx_at': mx_at,
            'opp': sum(1 for _m, _p, i, x in rows if i * x < 0),
            'se_n': len(sens), 'se_med': se_med, 'se_max': se_max, 'se_at': se_at}


def _three_factor():
    """三因子实测：ln(成交额) = ln(笔数) + ln(每笔股数) + ln(均价)，重标定成百分点。

    底座画不了三块（理由见模块 docstring），但**数字可以在图注里报全**。
    与两张分解图用同一个权重 w，所以三项相加逐格等于那两张图菱形上的总增长。

    2026-09 随分解图一起改基：从「逐日历年」改成**月度同比格**（见 `_mon_cells()`）。
    128 行读数印不进图注，所以这里返回**聚合读数**：末格逐项 + 那一项自己的
    |中位| / |最大| 与最大值落在哪一格。图注里报的每一个数都出自这里，一个都不写死。

    返回一个 dict（键见 `_NOTE_TRADE` 的用法）；算不出返回 None。
    """
    cells = _mon_cells(['tsx_value_cad', 'tsx_volume_shares', 'tsx_transactions'])
    rows, sh = [], []
    for m, a1, a0 in cells:
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
            rows.append((m, (V1 / V0 - 1.0) * 100,
                         w * lT * 100, w * lS * 100, w * lP * 100))
            sh.append((m, abs(w * lS * 100)))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    if not rows:
        return None
    s_med, s_max, s_at = _med_max(sh)
    return {'n': len(rows), 'm0': rows[0][0], 'm1': rows[-1][0], 'last': rows[-1],
            's_med': s_med, 's_max': s_max, 's_at': s_at}


def _venue_price():
    """各盘口**逐月**成交量加权均价的中位数（C$/股）—— 「品种结构」这件事的直接证据。

    先按月算 成交额 ÷ 成交股数（那就是当月的成交量加权均价），再对这些月取中位数；
    **不是**把全期成交额除以全期成交股数（那样大月会把小月压掉）。

    ⚠️ 2026-09 换了消费者：它原来喂三分法那张图的图注，那张图删掉之后搬给了
    `_NOTE_PRICE`（量 × 价那张）。搬而不是删的理由写在模块 docstring
    「为什么两张图都画 TSX 主板」那一节 —— 这几个数正是那一节的论据，
    跟着被删的图一起消失等于把自己的论据删了。

    返回 {盘口: 中位均价}；算不出返回 {}。
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


def _bond_resid(pre):
    """一侧（`pre` = `mx_adv` 或 `mx_oi`）的「合计 − 三档之和」逐月残差统计。

    只做取数与统计，措辞留给 `_bond_resid_zh()`。算不出（缺列 / 缺文件）返回 None，
    调用方据此退回不报数的说法 —— 缺文件不许在 import 期抛异常。
    """
    got = []
    for r in _rows():
        tot = _num(r, f'{pre}_bond_futures_contracts')
        parts = [_num(r, f'{pre}_{k}_contracts') for k in ('cgb', 'cgf', 'cgz')]
        if not tot or any(p is None for p in parts):
            continue
        d = tot - sum(parts)
        got.append((r['month'], d, d / tot * 100.0))
    if not got:
        return None
    pct = sorted(g[2] for g in got)
    return {'n': len(got), 'med': pct[len(pct) // 2], 'max': max(pct),
            'worst': max(got, key=lambda g: g[2]), 'last': got[-1],
            # 张数是整数，|残差| < 0.5 就是「恰为 0」；别写 == 0，那是拿浮点赌运气。
            'n0': sum(1 for g in got if abs(g[1]) < 0.5)}


def _bond_resid_zh(zh, d, unit):
    """一侧的读数写成一句话。**单位跟着这一侧走** —— ADV 是张/日，未平仓是张。"""
    return (f'<b>{zh}</b>（{d["n"]} 个月）中位 {d["med"]:.4f}%、'
            f'最大 {d["max"]:.4f}%（{d["worst"][0]}，{d["worst"][1]:,.0f} {unit}），'
            f'最新月 {d["last"][0]} 是 {d["last"][1]:,.0f} {unit} = {d["last"][2]:.4f}%，'
            f'其中 {d["n0"]} 个月残差恰为 0')


def _bond_note():
    """国债期货那两组（ADV 与月末未平仓）的口径交代 —— 恒等式闭不闭合，两侧各自现算。

    ⚠️ 给下一个改这里的人：未平仓这一组在 2026-09 之前只有「合计 + CGB」两条列，
    于是合计与 CGB 之间那条越拉越宽的口子读起来像「其余合约」（2024 年起中位 41%）。
    **它从来不是官方的披露边界，是本仓的管道边界** —— `MONTH END OPEN INTEREST`
    在 m-x.ca 的 xlsx 里是横跨所有产品行的列块，CGF / CGZ 的格子一直都在，
    只是 `fetch/tmx.py` 的 `MX_SPEC` 当时没登记这两条（ADV 一侧四条一直是齐的）。
    补齐之后残差落到千分之几，剩下的只有 LGB 一个合约。

    所以这段话报的数只有一个用处：**证明恒等式现在真的闭合**。它必须现算 ——
    哪天官方在 Bond Futures 小节里新上一个合约，残差会自己变大，这段话跟着变，
    而写死的「只剩 LGB」会原地变成假话且没有护栏会喊。

    ⚠️ 2026-09 收口复核抓到的假话：上一版开头写「ADV 与月末未平仓现在都是『合计 + 三档』」，
    紧跟着**只报了未平仓那一侧**的一组读数（中位 / 最大 / 最新 / 零残差月数），
    读者会把它当成两侧共同的实测 —— 而两侧的数并不一样（最大残差落在不同的月份上，
    零残差的月数也不同）。现在两侧各算各的、各自点名、各带各的单位
    （ADV 是张/日的流量，未平仓是张的存量快照 —— 上一版只写「张」，
    勉强钉住了是未平仓那一侧，但紧挨着「两侧都是」那句话读起来仍然像两侧共用）。
    句尾说 LGB 多数月份未平仓为 0，佐证就是未平仓那一侧现算的零残差月数。
    """
    head = ('<b>国债期货的 ADV 与月末未平仓现在都是「合计 + 三档」</b>：'
            'CGB（10 年）、CGF（5 年）、CGZ（2 年）。'
            # ⚠️ 上一版这里写「ADV 四条同轴画一张，未平仓是存量、每列各一张柱图」——
            # 那是 `groups[].mix` 进底座之前的画法，现在两侧同构，都是「合计柱 + 占比堆叠」
            # 两张一对。图注不许留着描述一套已经不存在的版式。
            '<b>两侧现在同构</b>：ADV 与未平仓各出「合计柱 + 三档占比堆叠」两张，'
            '差别只在口径（ADV 是当月日均的流量，未平仓是月末快照的存量）。'
            '要逐格对总量请看页尾核对表 —— 两侧的合计与三档都在那里并排。'
            '官方 xlsx 的 Bond Futures 小节里只有这三档加一个 LGB（30 年），'
            '四条之和恰是小节的 Total，所以「合计」与三档之间那点差就是 LGB，'
            '不是一篮子说不清的东西。'
            '（小节的 Total 之<b>后</b>还印着一行 Bond Options - OGB，那是期权、'
            '不在 Total 里，别把它算进来。）')
    sides = [_bond_resid_zh(zh, d, unit) for zh, d, unit in
             (('ADV', _bond_resid('mx_adv'), '张/日'),
              ('月末未平仓', _bond_resid('mx_oi'), '张')) if d]
    if not sides:
        return head + '（本次未能从 series/tmx.csv 算出恒等式残差，此处不报数。）'
    return head + (
        '<b>两侧各自逐月核过</b>（合计 − 三档之和占合计的比例，'
        '两侧的读数不一样，别把一侧的当成两侧的）：' + '；'.join(sides) + '。'
        '<b>LGB 不单列</b>就是这个原因 —— 它多数月份未平仓为 0，'
        '单画一条会是贴着零轴的死线。')


_IDX = _index_split()
_3F = _three_factor()
# ⚠️ 2026-09 删掉的 `_BWM/_BWC/_BWX/_BWR = _bench_wedge()`：那四个数只服务三分法那张
# 图的图注（「bench 在 2023-11 变大了多少」），三分法那张图删掉之后它们一个消费者都没有。
# 恒等式残差另有出处、且口径更准：`_all_identity_split()` 把「本仓自己加总的那一段」
# 与「拿官方合计核过的那一段」分开报，释义里用的是后者。
_VP = _venue_price()
_NOTE_BOND = _bond_note()
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
# 只绑**纯口径台阶 ≥0.5%** 的两条列（台阶值见下面的 `_SRC_STEP`）。
# 另外 10 条列的台阶在 0.00%~0.17% 之间，跨这个月是可比的，画线等于说假话。
# 台阶怎么量的、为什么不整段改用 CIRO：见 fetch/tmx.py 口径坑 16。
_SRC_COLS = ('tsx_volume_shares', 'tmx_all_volume_shares')
# 接缝处的纯口径台阶（CIRO 2021-07 → TMX 2021-08，把口径差从真实环比里剥出来）。
# ⚠️ **这两个数现算不出来**：series/tmx.csv 每格只存一个值（回补只往左填空、已有值
# 永不覆盖），两把尺子的重叠段根本不在本仓的 CSV 里 —— 它们由
# `build/basefill/tmx_ciro_2015.py` 抓 CIRO 原表时实测（那份脚本每次运行都重算并打印）。
# 所以这里是页面侧**唯一**一份副本，图注与页尾两处都从这里取。
# ⚠️ **不许再各写一份**：2026-09 就栽在这上面 —— `_splice_note()` 手抄成「约 1%」，
# 那是 tmx_all_volume_shares 的数（−0.98%），而那一句点名的是 tsx_volume_shares，
# 同一页上「最大的那条 = 约 1%」与页尾台阶表里的「−1.62%」并排印着，读者一眼可拆。
_SRC_STEP = {'tsx_volume_shares': -1.62, 'tmx_all_volume_shares': -0.98}


def _step_pct(col):
    """接缝台阶 → 「−1.62%」。负号用 U+2212，与页面上其余负号同一个字形。"""
    return f'{_SRC_STEP[col]:.2f}%'.replace('-', '−')
# 断点标签，长度与另外两条对齐（理由见下面「断点标签必须短」那段）。
_SRC_ZH = 'CIRO→TMX 换源'


def _splice_note():
    """两张分解图共用的一句：跨换源那一段的格子带着口径失真。

    2026-09 随分解图从年度桶改月度桶一起重写。变了两件事：

    · **「那一格」变成 12 格。**年度桶下换源只污染一根柱（跨拼接年 2021→2022 那根），
      月度桶下每一格是「本月 ÷ 去年同月」，本期在换源之后、基期在换源之前的格子共有
      **12 个**（_SRC_SWITCH 起连续 12 个月）—— 下面按 _SRC_SWITCH 现算出首末月，
      不写死月份。
    · **年度版那三个数（0.75pp / 0.35pp / ≤0.07pp）整段删掉。**它们量的是
      「2021 那一整年里 8–12 月换成 CIRO 重算」对**年度**柱的影响，而年度柱已经没有了；
      月度格的本期与基期各自只有一个月、分别落在两把尺子的两侧，失真的结构完全不同，
      那三个数搬过来就是假话。月度侧的台阶多大、怎么量的，页尾「口径与方法说明」
      那一条里逐列报着（成交股数是全页台阶最大的一条），这里只交代方向与去处。

    ⚠️ **不要把「滑出窗口就自己消失」当活逻辑写。**上一版的判据（拼接年还在不在
    末尾几根柱里）在月度桶下**恒真**：图的左界是 `build/single.py` 的 `WIN_FROM`
    （钉死在 2016-01，不随时间滚动），这 12 格永远滑不出去。写一个永远为真的分支
    等于在注释里承诺一件底座不会做的事。
    这里保留的判据是另一件**真会变**的事：CSV 里到底有没有换源之前的月份 ——
    `build/basefill/tmx_ciro_2015.py` 哪天被撤掉，序列就从 _SRC_SWITCH 起，
    整段没有「两把尺子」可言，这句话必须自己消失。与 `_breaks()` 里那条同源同判据。
    """
    first_spot = _first_present('tsx_volume_shares')
    if not (first_spot and first_spot < _SRC_SWITCH):
        return ''
    y, mm = int(_SRC_SWITCH[:4]), int(_SRC_SWITCH[5:])
    last = f'{y + (mm - 2) // 12 + 1}-{(mm + 10) % 12 + 1:02d}'
    return (f'<b>⚠️ 跨换源的那 12 格。</b>现货 12 列在 {_SRC_SWITCH} 换过源'
            f'（此前是监管方 CIRO、此后是 TMX 自报，见页尾「口径与方法说明」）。'
            f'月度格的本期是该月、基期是去年同月，所以<b>本期在换源之后、'
            f'基期在换源之前</b>的格子恰好是 {_SRC_SWITCH} 至 {last} '
            f'这连续 12 格 —— 它们跨着那道纯口径台阶，读到的有一部分是口径不是业务。'
            f'台阶逐列量过多大、方向如何，逐列印在页尾「口径与方法说明」里 —— '
            f'⚠️ <b>三条列各不相同，本图用到哪两条就看哪两条</b>：'
            f'<b>成交股数</b>的台阶是全页最大的一条'
            f'（{_step_pct("tsx_volume_shares")}，TMX 自报的口径低于 CIRO），'
            f'<b>成交额</b>一侧方向相反、量级小一档，'
            f'<b>成交笔数</b>实测两把尺子几乎重合（60 个重叠月的比值中位数 1.00000，'
            f'多数月逐位相同）。'
            f'本页照实说明、不做剔除 —— 剔除等于自造一条谁也没发过的序列。'
            f'⚠️ 这 12 格<b>不会随时间滑出图</b>：本图左界是全站统一的固定左界，'
            f'不是滚动窗口。')


_NOTE_SPLICE = _splice_note()


# ── 图 A（量 × 价）的图注：把「价」再拆成市场涨跌与品种结构 ────────────────
# ⚠️ 2026-09 随分解图改月度桶整段重写。删掉的年度专有措辞：「I 取该年 12 个月末点位的
# 平均」「逐年相加」「以上逐年对账只覆盖完整日历年」「末尾的 YTD 格」——
# 月度桶下一根年度柱都没有，这些话指的是页面上不存在的东西。
# 底座那半边（格数、留空格、w 区间、交叉项、闭合残差、与输入图逐格对读）由
# `_decomp_monthly` 逐图现算并印在同一段图注里，这里**只补它算不出来的那一半**。
_NOTE_PRICE = (
    '<b>本页是全仓唯一能把「市场涨跌」与「品种结构」拆开的一家。</b>'
    '均价 ≡ 成交额 ÷ 成交股数，它同时含（a）市场整体涨跌与（b）成交在贵票与便宜票之间的'
    # ⚠️ 引文只归给真印过它的那一页 —— 订正的来龙去脉写在 `_index_split` 的
    #    docstring 里（那里有同一句的副本，两处同步改）。
    '迁移。<b>本仓其余做量价分解的页都没有这一层</b> —— 它们的 series 里没有指数点位列，'
    '全仓只有本页有。JPX 那页的同类图注把这件事写在明处：'
    '「均价里含结构效应，但本页拆不出它有多大」。'
    '<code>series/tmx.csv</code> 有 <code>tsx_composite_close</code>（S&P/TSX Composite '
    '月末点位），而它的成分正是 TSX 主板的票，所以这里能再写一层<b>定义式</b>：'
    'ln(P₁/P₀) = ln(I₁/I₀) + ln[(P/I)₁ ÷ (P/I)₀]，前者是市场涨跌、后者是品种结构。'
    '两块乘上与本图同一个重标定权重 w，因此<b>逐格相加恰好等于图上「均价的贡献」'
    '那一块</b>（单位同为百分点）。'
    + ((f'实测（凡算得出单月同比的月份全在内，{_IDX["n"]} 格，'
        f'{_IDX["m0"]} – {_IDX["m1"]}）：最新一格 {_IDX["last"][0]} '
        f'价 {_pp(_IDX["last"][1])} = 市场 {_pp(_IDX["last"][2])} + '
        f'结构 {_pp(_IDX["last"][3])}；'
        f'|结构| 中位 {_IDX["mx_med"]:.1f}pp、最大 {_IDX["mx_max"]:.1f}pp'
        f'（{_IDX["mx_at"]}），|市场| 中位 {_IDX["mk_med"]:.1f}pp、'
        f'最大 {_IDX["mk_max"]:.1f}pp（{_IDX["mk_at"]}）；'
        f'两块<b>反号</b>的有 {_IDX["opp"]} 格 —— 那些月份里结构在抵消市场，'
        f'光看均价读不出来。'
        f'<b>逐格清单印不进图注</b>（{_IDX["n"]} 行），要逐格对账请走页尾核对表的'
        f'原始列自己算。')
       if _IDX else
       '（本次未能从 CSV 算出读数，此处只给方法不给数字。）')
    # ⚠️ 时点错配：所有者点名不许无声带过。这一层仍然做，代价量出来写在这里。
    + ('<b>⚠️ 这一层在月度桶下有一处时点错配，说清楚再读。</b>'
       '分子 P 是<b>当月成交量加权均价</b>（整个月的成交摊出来的），'
       '而 I 只能取<b>月末点位</b> —— 本页没有日频指数，'
       '年度版靠「该年 12 个月末点位的平均」把这件事绕开了，月度版绕不开。'
       '两者时点不同，差出来的那一截会被<b>「品种结构」那一块整段吸收</b>'
       '（结构块 ≡ w(lnP − lnI)，lnI 偏多少结构块就反向偏多少）。'
       + ((f'这一截有多大，这里量给你看：把 I 换成「本月末与上月末的平均」这个同样'
           f'说得通的当月水平代理再算一遍，结构块挪动 |Δ| 中位 '
           f'{_IDX["se_med"]:.1f}pp、最大 {_IDX["se_max"]:.1f}pp'
           f'（{_IDX["se_at"]}，{_IDX["se_n"]} 格可比）。'
           f'⚠️ 那不是更准的口径、更不是修正，它回答的只是'
           f'「换一个同样说得通的时点，这块会挪多少」。')
          if _IDX and _IDX['se_med'] is not None else
          '（本次未能量出这一截的幅度。）')
       + '所以<b>「结构」这一块要连着相邻几格一起读</b>，别拿单独一格当结论；'
         '真正干净的那一半是「市场涨跌」，它两侧都是月末点位、时点一致。')
    + '<b>⚠️ 这一层只对 TSX 成立。</b>S&P/TSX Composite 不含 TSX Venture，'
      '拿它去除 TMX 合计的均价，分母里混着仙股，算出来的「结构」有一大截只是盘口混合比例。'
      '<b>这不是形容词，是量得出来的</b>：'
    + (('各盘口<b>逐月</b>成交量加权均价的中位数实测 —— '
        + '、'.join(f'{k} {v:,.2f} C$/股' for k, v in _VP.items())
        + '，TSX 与 TSX Venture 差着一两个数量级（仙股主导）。')
       if _VP else '（本次未能从 CSV 算出各盘口的均价中位数。）')
    + '本页两张分解图因此一律画 <b>TSX 主板</b>，不画 TMX 合计。'
    + _NOTE_SPLICE
)

# ── 图 B（笔数 × 每笔金额）的图注：三因子在这里报全 ────────────────────────
# ⚠️ 这段图注里**不许出现「上一张」「下一张」这类位置话术**：两张分解图现在各自
# 用 `after_group` 就地排在自己的输入之后（见 SPEC['decomp']），中间隔着别的组，
# 它们**不再相邻**；「要读价请看上一张图」那种写法当场变成假话，而没有护栏会响。
# 一律按**图题**点名（sgx.py / enx.py 的 spec 里是同一条写法）。
_NOTE_TRADE = (
    '<b>这张与「TSX 主板成交额」那张<u>量价分解</u>合起来就是三因子。</b>'
    '恒等式 成交额 ≡ 笔数 × 每笔股数 × 均价 三项都有列'
    '（<code>tsx_transactions</code> / <code>tsx_volume_shares</code> / '
    '<code>tsx_value_cad</code>），但底座的三分法是「行业 / 份额 / 结构」形状 ——'
    '把笔数塞进 bench 虽然凑得出三块，图注却会跟着印出「份额 ≡ 股数 ÷ 笔数」'
    '「结构 ≡ 自家均价 ÷ 行业均价」「⚠️ 分子必须是分母的子集」三句不成立的话。'
    '<b>图注说假话的代价高于少画一块柱</b>，所以拆成两张两分法，三项读数在这里报全'
    '（同一个重标定权重 w，三项相加逐格等于菱形上的总增长）：'
    + ((f'实测（凡算得出单月同比的月份全在内，{_3F["n"]} 格，'
        f'{_3F["m0"]} – {_3F["m1"]}）：最新一格 {_3F["last"][0]} '
        f'总 {_3F["last"][1]:+.1f}% = 笔数 {_pp(_3F["last"][2])} + '
        f'每笔股数 {_pp(_3F["last"][3])} + 均价 {_pp(_3F["last"][4])}；'
        f'中间那一项（<b>每笔股数</b>，两张图都没单画）|中位| {_3F["s_med"]:.1f}pp、'
        f'|最大| {_3F["s_max"]:.1f}pp（{_3F["s_at"]}）。'
        f'两张图的量腿之差就是它：ln(股数) − ln(笔数) = ln(每笔股数)。')
       if _3F else '（本次未能从 CSV 算出读数。）')
    + '<b>⚠️「每笔平均成交额」不是价。</b>它衡量的是订单碎片化程度 —— '
      '同一笔母单被切成更多子单，笔数上升、每笔金额下降，而成交额与股价一点没变。'
      '要读价请看<b>「TSX 主板成交额」那张<u>量价分解</u></b>'
      '（同一条成交额拆成股数 × 均价；别与同名那一组的<b>水平值柱</b>混了，'
      '那张画的是成交额本身，不是它的分解）。'
      '本页两张分解图不相邻，按图题找、别按图号数。'
    + _NOTE_SPLICE
)

# ⚠️ 2026-09 删掉的 `_NOTE_SHARE`：它是三分法那张图（TSX 相对 TMX 集团）的图注，
# 那张图本轮删掉了（理由见页尾那条历史账），图注跟着一起删 —— 留着就是死配置。
# 它讲的两件事都没有丢：①「子集关系精确成立」的恒等式核对留在释义「TMX 合计」里
# （`_all_identity_split()`，而且口径更准，把本仓自己加总的那一段单独说明）；
# ②「各盘口均价差着一两个数量级」这条现算证据搬进了上面的 `_NOTE_PRICE`
# —— 它本来就是「为什么画 TSX 而不是 TMX 合计」的论据，放在那里比放在被删的图上更对。


def _cover_rank_zh(col):
    """这一列在**本页声明过的全部列**里的覆盖名次 —— 谁最长、长多少、几条并列，全现算。

    ⚠️ 上一版这里写死的是一句三重超级式：「本页最长、最快、最干净的一条序列」。
    2026-09 收口复核实测：三个断言没有一个站得住。`mx_adv_contracts` 是 296 个月，
    而两条月末指数点位各 297 个月（2001-12 起）**比它长一个月** —— 同一页
    `_seg_zh()` 生成的那条 notes 自己就写着「回得最早的是月末指数点位」，
    两句话在页面上当场打架；「最快」「最干净」严格说也只是并列第一（同一份 m-x.ca
    月度 xlsx 出来的那几条列同发布节奏、同样逐月无洞）。
    所以这里一个超级式都不写死，只报现算的名次：本页最长的是谁、多长、从哪个月起，
    以及有几条列与这一列同长。哪天回补把谁拉长、或者哪条列上页下页，这句自己跟着变。

    ⚠️ **只能在构建期调用**（本页是从 `callable(page)` 的那条 notes 里调的）：
    它读模块级的 `SPEC`，而 `SPEC` 在本文件末尾才定义 —— 写进模块级字面量会 NameError。
    列的名单 = `groups` 里声明的列 + `decomp` 的两条输入列（`mix` 的 total/parts
    都是跨组引用，本来就在 `groups` 里）；名字取 spec 自己写的 `zh`，不另写一份。
    """
    cols = {}
    for g in SPEC['groups']:
        for c in g['cols']:
            cols.setdefault(c['col'], c.get('zh') or c['col'])
    for d in (SPEC.get('decomp') or []):
        for k in ('value', 'qty'):
            if d.get(k):
                cols.setdefault(d[k]['col'], d[k].get('zh') or d[k]['col'])
    cov = {}
    for c in cols:
        ms = [r['month'] for r in _rows() if c in r and r[c].strip()]
        if ms:
            cov[c] = (len(ms), ms[0])
    if col not in cov:
        return ''
    n = cov[col][0]
    top = max(v[0] for v in cov.values())
    same = [c for c in cov if cov[c][0] == n and c != col]
    same_zh = (f'与它同为 {n} 个月的还有本页另外 {len(same)} 条列'
               if same else f'本页没有第二条同为 {n} 个月的列')
    if n >= top:
        return ('<b>它是本页覆盖最长的一档</b>：'
                + (f'{n} 个月，{len(same) + 1} 条列并列。' if same
                   else f'{n} 个月，独一份。'))
    tops = sorted((c for c in cov if cov[c][0] == top), key=lambda c: cov[c][1])
    who = '、'.join(cols[c] for c in tops) if len(tops) <= 4 else f'本页另外 {len(tops)} 条列'
    starts = {cov[c][1] for c in tops}
    since = f'、{next(iter(starts))} 起' if len(starts) == 1 else ''
    return (f'<b>但它不是本页覆盖最长的那一条</b>：{who} 各 {top} 个月{since}，'
            f'比它还长；{same_zh}。')


# ── 现货那张「合计柱 + 单月同比」的图注（原 ttm_yoy 专图搬过来的）─────────────
# ⚠️ 这条图注的**上一版讲的是 12 个月滚动同比**（柱与线怎么还原、为什么现货要看滚动）。
# 2026-09 全页次轴统一改成**单月同比**（页面所有者指定）之后那些话一句都不成立了，
# 所以整段重写，没有留半句。口径本身的实测代价由底座的 `mom_cost_zh()` 逐图现算，
# 这里只补它算不出来的那一半：这条序列自己的脾气。
#
# ⚠️ MX 那一条**从图注挪到了页尾 notes**（`_note_mx_adv`）。原因：它挂在最上面那组
# `mix` 的 `note` 上，而那一组的合计柱在 2026-09 已经不出了（与开篇图逐点相同，
# 见本文件抬头「图列」那一段），`note` 会变成一条**永远印不出来的死配置**，
# 它讲的三件事也会跟着从页面上消失 —— 而那三件事底座一件都算不出来。
def _note_mx_adv(page):
    """页尾那条讲 `mx_adv_contracts` 脾气的说明。**写成 callable(page)。**

    ⚠️ **为什么不能是无条件的字面量。**这段话里有两句在指路（「那条单月同比的毛刺」
    「想看开市那天有多热看哪张」），而那条同比画在哪张图上、甚至在不在，是底座每次构建
    现判的：`headline_style='bar_yoy'` 时开篇那张就是这一列的「水平值柱 + 次轴单月同比」，
    本组的合计柱因此被折叠进去（`page.mix_folded`）；去掉那个键重跑，开篇改成
    「分位带折线 + 同比柱」两张、一条次轴都没有，而本组的合计柱站回页面上。
    它原来挂在 `mix` 的 `note` 上时有结构护栏（合计柱出图才印），搬进 `SPEC['notes']`
    成字面量之后护栏没了 —— 实跑复现过：去掉 `headline_style` 重跑，这一段照旧印
    「开篇那张图次轴上那条单月同比」，而那次构建的开篇是分位带折线。
    这与 `_note_2609` 的 docstring 里那句「声明与事实各走各的，就迟早分叉，
    而且没有任何东西会响」是同一个病，机制建好了不能只用一半。

    所以指路那两句改成随事实收放：折叠了就指底座**现算**出来的那个图号（那张按判据
    必然是同一列、同族 `bar_yoy` 的水平值柱 + 次轴同比）；没折叠就不指号、按组名点
    本组那张合计柱。**这一列自己的脾气**（日均口径、出自发布最快的那一批列、
    本页数据月由它定、覆盖名次由 `_cover_rank_zh()` 现算）与画法无关，两档逐字相同。
    ⚠️ 没折叠那一档假定本组的合计柱真画出来了。它另有几条画不出来的路（合计整列为空、
    窗口不足 24 个月……），撞上时这半句会指一张不在页上的图 —— 那一档由底座的
    `skipped` 那本账在页尾「本轮未出的派生图」里另行交代，而那时本页早已不是这个形状。
    """
    fold = next((d for d in page.mix_folded if d['col'] == _FOLD_COL), None)
    where = (f'Exhibit {fold["n"]} 那张水平值柱' if fold
             else '「MX 衍生品 ADV」那一组的合计柱')
    # `where` 以 ASCII 开头（「Exhibit …」）时前面要空一格、以全角引号开头（「MX…」）时
    # 不要 —— 中文与 ASCII 之间空一格是全站写法，两个全角括号之间空一格则是排版噪声。
    # ⚠️ 这里**不举带图号的例子**：本文件里凡是出现「Exhibit N」都要能归进白名单
    # （汇总表 / 冻结的「原 Exhibit N」/ 明文冻结的改版前证据），一个排版示例归不进去，
    # 而且折叠目标一挪，示例里那个号就读着别扭。
    sp = ' ' if fold else ''
    return (
        '<b>本页发布最快的那一批列（MX 那半边，一条都不进 slow_cols）里的一条。</b>'
        '<code>mx_adv_contracts</code> '
        + _dense_zh('mx_adv_contracts')
        + '，次月第 1–4 个工作日就发 —— <b>本页的数据月由它一条定</b>（页顶抬头行与'
          '汇总表的「头条指标」说的就是它）。'
        + _cover_rank_zh('mx_adv_contracts')
        + '<b>⚠️ 它是当月<u>日均</u></b>（官方直接发布，不是本仓拿月合计除交易日算的）：'
          '交易日多的月份不会因此显得更热，但**月度形状仍在**（到期周、假期分布），'
        + f'{where}次轴上那条单月同比的毛刺，一部分就来自这里。'
        + '官方同时发布当月合计 <code>mx_volume_contracts</code>，本页把它单独画成一张柱图'
          '（组名「MX 当月成交总量」那张）—— 两条谁也不从谁推，'
        + f'想看「一个月一共做了多少」看那张，想看「开市那天有多热」看{sp}{where}。'
    )


# ── 2026-09 改版的历史账（一条 note 覆盖本轮全部四件事）──────────────────────
#: 被删那两张图的标题，**逐字**从改版前那一版的 payload 取
#: （`git show HEAD:data/tmx.js`，即 2026-09 这一轮动手之前最后一次提交的产物）。
#: 这两条引文的全部用处就是让手里还留着上一版的读者对上号，用「」括起来的引文漏掉
#: 半句组名（上一版就漏掉了「（2002-01 起）」），正好漏在那半句最容易被搜的地方。
_FOLD_OLD_TITLE = 'MX 衍生品 ADV（2002-01 起）：日均成交 —— 水平值与单月同比'
_DROP_OLD_TITLE = ('TSX 主板成交额（相对 TMX 集团）：增长的量价分解'
                   '（一格 = 一个完整年度，末格 = 当年 YTD）')
#: 年度桶那三张分解图的图注里、本轮作废的那一句，**逐字**从改版前那一版的 payload 取。
#: ⚠️ **一个字都不许改**（尤其不许把开头那五个字缩成「每个端点都是」）：底座把这句话
#: 拆成两支（`build/single.py` 的 `_decomp_annual`），有 YTD 格的走这一支、没有 YTD 格的
#: 才走「每个端点都是整整 12 个月的合计」那一支，而底座自己的注释就写着后者
#: 「对 YTD 那一格是假话」。/tmx/ 原来那三张分解的图题里逐字写着「末格 = 当年 YTD」
#: ⇒ 走的必然是这一支。抄成另一支的措辞，等于替旧版页面认领一句它从没印过、
#: 印出来还是假话的断言。
_OLD_ANNUAL_QUOTE = ('完整年各格的端点都是整整 12 个月的合计，不是某一个月的点值 —— '
                     '拿单月当端点，挑到一个异常月就能把归因整个说反')
#: 底座那段「同一条同比出现在不止一张图上」的结尾半句，同样**逐字**取自改版前的 payload
#: （生成处是 `build/single.py` 的 `dup_yoy_zh()`，今天仍逐字如此）。
#: 引号里只放逐字的这半句 —— 上一版把整段转述塞进「」里，那是引文不实。
_OLD_DUP_TAIL = '要不要并成一张由页面所有者定'
#: 被折叠掉的是哪一列 —— 与 `headline` / 最上面那组 mix 的 total 同一个列名。
_FOLD_COL = 'mx_adv_contracts'


def _shift_zh(k, many=True):
    """相对位移 → 「各前移 N 号」/「号不动」/「各后移 N 号」（`many=False` 去掉「各」）。

    只做一件事：**让措辞跟着符号走**。下面那张旧→新图号对照表里的位移是本轮四个编辑
    动作的累加（并图 −1、新增锚点 +1、两张分解各就地插一次 +1 +1），一路上有前移、
    有不动、也有后移 —— 手写「各前移/各后移」四个字最容易在某一行写反，而写反了
    页面上不会有任何东西响。把符号交给这里，正文里只写那个累加值。
    """
    if k == 0:
        return '号不动'
    ge = '各' if many else ''
    return f'{ge}前移 {-k} 号' if k < 0 else f'{ge}后移 {k} 号'


def _note_2609(page):
    """页尾那条「2026-09 这一轮改了什么」的历史账。**写成 callable。**

    ⚠️ **为什么不能整条写死成散文。**本轮四件事里有三件是不可逆的 spec 编辑
    （删三分法分解、删那条右轴线、加锚点组并把两张分解改月度桶前移），写死就对；
    但第一件 —— 开篇柱与 MX ADV 合计柱并成一张 —— 描述的是**底座每次构建重新判定
    的结果**：折叠的判据在 `build/single.py` 的 `Page.total_drawn_wider` 里现算，
    本文件抬头「图列」那一段还专门把「头条哪天换成别的列，这一组的合计柱自己就回来了」
    当成优点。那正是这条 note 变成假话的开关 —— 去掉 `headline_style` 重跑，
    合计柱就站回页面上，而写死的这条照旧加粗宣布「删掉的是原 Exhibit 3……」，
    页面指着一张明明在场的图说它被删了，四道闸门一道都不响。
    （这与底座在 `total_drawn_wider` 的 docstring 里否掉「做成 spec 开关」是同一条理由：
     声明与事实各走各的，就迟早分叉，而且没有任何东西会响。）

    所以这里回读 `page.mix_folded`（底座那本「合计柱有意不出」的账）：并图那一段
    这一列真被折叠了才印，没折叠就整段换成「这一轮没有并掉」，而且**旧→新图号对照
    里那一号的位移跟着收放**（`_shift_zh`）—— 一处成立、另一处不成立的对照表比不写更糟。

    ⚠️ 本条里**一个当前图号、一个当月读数都不许出现**：图号由底座按渲染顺序现算，
    读数每月都变。只用「原 Exhibit N」（冻结的改版前编号）与算出来的相对位移。
    """
    folded = any(d['col'] == _FOLD_COL for d in page.mix_folded)
    return (
        '<b>2026-09：本页改了四件事 —— 并掉一张重复的合计柱、删掉一张重复的量价分解、'
        '删掉一条重复的右轴线、把剩下两张量价分解改成月度桶并前移到各自的输入之后'
        '（为此新增一张锚点图）。</b>'
        '本条逐项交代改了什么、为什么，以及旧图号对应到哪里。'
        '<b>它是历史账，不随每月新数据变</b>；各图自己的判据与实测数在各图图注里，'
        '这里只点名、不复述。'

        # ── 一、并图 ──────────────────────────────────────────────────────
        + (('（一）<b>开篇柱与紧随其后的 MX ADV 合计柱并成一张。</b>'
            f'<b>删掉的是原 Exhibit 3</b>（「{_FOLD_OLD_TITLE}」）。'
            '它与开篇那张画的是<b>同一列</b>（<code>mx_adv_contracts</code>）、'
            '<b>同一种单月同比</b>（本列除本列），只是横轴短一截：'
            '开篇那张从这条序列的第一个月起画全部已披露历史，被删的那张从全站统一的'
            '左界起画。两张重叠的那一段<b>逐点相等</b>（2026-09 并图当天<b>人工</b>'
            '逐月比对过，水平值与同比的最大绝对差都是 0；底座本身不复算数据点，它判的是'
            '「同一列、同一口径、同一图族、横轴真包含」这四项元数据 —— 四项齐了，'
            '窄的那张按构造就是宽的那张里的一段连续复制）。'
            '被删的那张没有一个月落在开篇那张之外 —— 它不是第二个读数，是同一条序列'
            '换个窗口再画一遍。<b>这一组的结构那一半没有丢</b>：紧跟开篇图的 100% '
            '占比堆叠照旧，它的图注里点名了「合计的绝对量看哪一张」，指的就是开篇那张。'
            '<b>页面上原来替这件事说话的那段也随之消失了</b>：底座本来会在页尾逐图比对、'
            '现算出一段说明这两张同源，末尾写着'
            f'「{_OLD_DUP_TAIL}」—— 并成一张之后它自动没了，所以改由本条交代。')
           if folded else
           ('（一）<b>开篇柱与 MX ADV 合计柱这一轮没有并掉。</b>'
            '并图是底座每次构建现算的判定（头条那一列的窗口真包含组内那张合计柱时才并），'
            '本次构建没有命中 —— 那张合计柱仍在页上，'
            '下面第（五）条的旧→新图号对照也因此不成立、整张不印。'))

        # ── 二、删三分法分解 ──────────────────────────────────────────────
        + '（二）<b>删掉三分法那张量价分解</b>'
          f'（原 Exhibit 39，「{_DROP_OLD_TITLE}」）。'
          '它与「TSX 主板成交额」那张分解用的是<b>同一对列</b>'
          '（<code>tsx_value_cad</code> ÷ <code>tsx_volume_shares</code>），'
          '只是把同一个增长换成「行业 / 份额 / 结构」三块再切一遍 —— '
          '<b>同一条序列换个切法再画一遍</b>，这是本轮统一要删的形状。'
          '它真正多问的那件事 ——「TSX 在集团里占多少、份额怎么动」—— '
          '本页三张 100% 占比堆叠（成交额 / 股数 / 笔数各一张）已经各答过一次，'
          '而且答得更直接：那三张画的就是份额本身，不是份额的对数贡献。'
          '<b>它图注里两件真东西都留下了</b>：'
          '「TSX + TSXV + Alpha（+Alpha-X&DRK）≡ TMX 合计」这条恒等式的核对结果'
          '<b>一直写在释义「TMX 合计」里</b>（本轮一个字都没搬 —— 那一版口径还更准：'
          '它把 2021-08 之前本仓自己加总的那一段单独说明，那一段的零残差是定义使然、'
          '不是核对结果），所以那张图删掉，这件事一个字都没丢；'
          '「各盘口成交量加权均价差着一两个数量级」那条现算证据搬进了'
          '「TSX 主板成交额」那张分解图的图注 —— 它本来就是「为什么画 TSX 而不画 '
          'TMX 合计」的论据，跟着被删的图一起消失等于把自己的论据删了。'

        # ── 三、右轴线 ────────────────────────────────────────────────────
        + '（三）<b>「加拿大现货成交额」那张 100% 占比堆叠上的右轴线删掉了。</b>'
          '那条线画的是 TSX Alpha 的占比，而 TSX Alpha <b>就是这张堆叠的第三段</b> —— '
          '同一条序列换个刻度再画一遍（那条线自己的纵轴标题当时写的就是'
          '「同一条序列换个刻度」）。'
          '<b>信息一点没少</b>：那一段照旧在堆叠里，最新值与窗口内极值印在这张图'
          '自己的图注里。'
          # ⚠️ 2026-09 收口复核订正（与下面「加拿大现货成交额」那组 mix 上方的同一句
          #    副本一起改的，两处措辞必须同步）。上一版这里写的是「那一段…扣掉段间
          #    白缝之后高度就是 0、根本画不出来，那条线是那张图的全部内容」——
          #    实测是假话：那一段窗口内的最大占比是**几个百分点**（底座在那张图的图注里
          #    现算并印出来，右轴的上界就是按这个量程取的），一半上下的月份高过底座
          #    那条「扣完白缝高度就是 0」的门槛，画得出来；写成「根本画不出来」既与
          #    那张图自己的图注当场打架，也把保留这条线的真理由说错了。
          #    真理由是**读不出**、不是**画不出** —— 见 build/single.py 立 `rhs_share`
          #    这条例外时写下的判据：「某一段常年只占几个百分点，在 0–100 的堆叠里
          #    它几个 pp 的变化根本量不出来」。
          #    ⚠️ 改完不许在本条里补一个实测数：这条 note 的抬头写着「它是历史账，
          #    不随每月新数据变」，而那一段的区间每个月都动 —— 数一律留给底座在
          #    那张图自己的图注里现算。
          '⚠️ <b>本页另一张堆叠上的右轴线保留</b>（股指期货那张，画的是「其他股指期货」'
          '那一段）：两条线不是一回事，差在<b>读不读得出</b>。'
          '被删的那条画的 TSX Alpha 取自一条真实存在的列，在那张堆叠里常年厚到'
          '<b>段高本身就把它读出来了</b>，右轴等于同一件事说两遍；'
          '保留的那条画的是<b>算出来的残差</b>（股指期货合计 − SXF，本仓没有对应的列），'
          '它薄得多，整个量程都压在 0–100 柱高最下面那一截里 —— '
          '几个百分点的进退在那个刻度上量不出来，换成右轴按它自己量程取的刻度才读得出。'
          '<b>这正是底座给这类右轴线立例外时写下的判据</b>，'
          '而当期的实测区间与右轴取到的量程由底座现算、印在那张图自己的图注里，'
          '本条一个会随数据变的数都不抄。'

        # ── 四、分解改月度桶 + 前移 + 新增锚点图 ──────────────────────────
        + '（四）<b>剩下两张量价分解由「4 根完整日历年柱 + 当年 YTD」改成月度桶，'
          '并由页面末位前移到各自的输入之后。</b>'
          '两件事是同一件事的两半：改月度桶让它与本页其余时序图同一个刻度、同一个基期'
          '（去年同月），前移让「输入 → 分解」在阅读顺序上连成一段。'
          # ⚠️ 上一版这里写的是「因此它与**全站其余仍按年度桶**的分解图不再同口径，
          #    跨页不要比」。2026-09 收口复核实测：那个前提是假的 —— 别的页也有同一轮
          #    改成月度桶的分解图（同基期、同刻度、xlabels 逐格相同），那句话恰好把
          #    唯一**可以**逐格对读的兄弟页图排除掉了。
          #    ⚠️ **别改成写死家数**（「另外三家还是年度桶」之类）：本文件管不到别家，
          #    build/specs/ 里加一个 spec 或改一个 bucket 键，那个数就过期，而页面上
          #    不会有任何东西响。同一条教训 sgx.py 的 'decomp' 那段注释记过两轮。
          #    ⇒ 改成不依赖家数的说法：桶是每张分解图**自己图题里的一句话**
          #    （底座无条件印：bucket='year' 印「一格 = 一个完整年度」、'monthly' 印
          #    「一格 = 一个月，本期该月、基期去年同月」），叫读者当场对图题即可。
          '⚠️ <b>跨页比之前先对桶</b>：桶写在每张量价分解图<b>自己的图题</b>里，'
          '本页这两张写的是「一格 = 一个月，本期该月、基期去年同月」。'
          '别页那张若写的是完整日历年，两边的一格根本不是同一段时间，逐格对读会把'
          '桶的差读成业务的差；写的同样是月度桶、窗口又对得上，才能逐格比。'
          f'年度版图注里「{_OLD_ANNUAL_QUOTE}」那段话<b>随之作废</b>：'
          '月度桶的端点<b>就是</b>一个月。换来的是每一格都能与本页其余月度图逐格对读；'
          '换掉的正是那层保护，所以要连着相邻几格一起读，别拿单独一格下结论。'
          '同时作废的还有年度版里「逐年对账」那几组读数（页面上已经没有年度柱），'
          '以及「跨 2021→2022 那一根柱带着多少口径失真」那句 —— 月度桶下受换源影响的'
          '不是一根柱而是连续 12 格，改由那两张图各自的图注按换源月现算点名。'
          '<b>为此新增一张图：「TSX 主板成交额」的水平值柱 + 次轴单月同比。</b>'
          '它不是凑数，是底座对月度桶的<b>硬前提</b>：本页必须有唯一一张'
          '「该金额列的水平值 + 单月同比、横轴与分解图逐格相同」的图，'
          '分解图的图注才敢说「菱形就是那条金线」「可以逐格上下对读同一个月」——'
          '找不到就直接不出图。它同时补上了页面此前<b>没有一张图</b>回答的问题：'
          'TSX 主板成交额的<b>绝对水平</b>走了什么形状 —— 改版前画到它的只有'
          '「加拿大现货成交额」那张 100% 堆叠里的一段<b>占比</b>；'
          '它的绝对量一直印在汇总表（本月 / 上月 / 去年同月）与末尾核对表（近 13 个月）里，'
          '但那两处都读不出这条序列自己的走势。'
          '⚠️ 这一列的配置因此<b>搬进了那一组、只声明一次</b>，'
          '「加拿大现货成交额」那组的堆叠改用跨组引用取它 —— 同一条列声明两份，'
          '图例与核对表会各取一份、印出两个名字。'

        # ── 五、编号 ──────────────────────────────────────────────────────
        # ⚠️ 这张对照表**只在并图那一件也发生了的前提下才对得上**。折叠的开关是
        # 「头条那一列与那一组的合计柱是不是同一列」，而把那个开关关掉（换头条列 /
        # 去掉 headline_style）本身就会改掉开篇那一段的结构（实测：去掉 headline_style
        # 之后开篇由一张柱变回「分位带折线 + 同比柱」两张），页面的编号从此不再是这张
        # 表能对上的那一版。所以没折叠时**整张表不印** —— 印一张指错的对照表比不印更糟。
        + ('（五）<b>编号怎么动。</b>'
           '原 Exhibit 1（汇总表）与原 Exhibit 2（开篇柱）不动。'
           f'原 Exhibit 3 已删；原 Exhibit 4 至原 Exhibit 17 {_shift_zh(-1)}；'
           f'新增的那张锚点图插在原 Exhibit 17 之后，'
           f'于是原 Exhibit 18 与原 Exhibit 19 {_shift_zh(0)}；'
           f'「TSX 主板成交额」那张分解插在原 Exhibit 19 之后，'
           f'于是原 Exhibit 20 与原 Exhibit 21 {_shift_zh(1)}；'
           f'「按成交笔数拆」那张分解插在原 Exhibit 21 之后，'
           f'于是原 Exhibit 22 至原 Exhibit 36 {_shift_zh(2)}。'
           f'原 Exhibit 37 / 38 就是这两张分解本身（它们从页尾搬到了上面那两个位置），'
           f'原 Exhibit 39 已删；末尾核对表（原 Exhibit 40）{_shift_zh(-1, many=False)}。'
           '<b>本页每一个图号都是底座按渲染顺序现算的</b>，正文、图注与本条里没有写死'
           '任何一个新号，所以下一次增删同样只会移动号，不会造出一句指错图的话。'
           if folded else
           '（五）<b>编号怎么动 —— 本条这一版给不出对照表。</b>'
           '旧→新图号对照只有在「并图那一件也发生了」的前提下才对得上（本条写下来的'
           '时候正是那一版）。这次构建里合计柱没有被折叠，说明开篇那一段的结构已经与'
           '写这条时不同，页面的编号也就不再是那张对照表能对上的那一版 —— '
           '所以这里不印一张会指错的表。上面（二）（三）（四）三件事是不可逆的编辑，'
           '照旧成立；要对旧号请直接比对上一版的页面。')
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

#: 未平仓那一组的组名 —— 组名会进图题，而下面这条图注要按名字点它的合计柱，
#: 所以两处**共用这一份**：分成两份写，改了组名就会留下一处指不着的交叉引用，
#: 而引文漏半句组名恰好漏在最容易被搜的那半句上（同一条教训见 `_FOLD_OLD_TITLE`）。
_G_OI_ZH = 'MX 月末未平仓（存量，期末口径）'

_NOTE_MIX_OI_ALL = (
    # ⚠️ 上一版这里写的是「而 <b>Exhibit 里的合计柱</b>只回答『一共多少』」——
    #    「Exhibit」后面没有图号，这处交叉引用指不到页面上任何一张图。
    #    **本页正确的写法是按内容点名、不写图号**（图号由底座按渲染顺序现算，
    #    spec 里写死一个就等着下一次增删把它指歪）；同页先例：`_NOTE_TRADE` 的
    #    「「TSX 主板成交额」那张量价分解」、`_note_mx_adv` 没折叠那一档的
    #    「「MX 衍生品 ADV」那一组的合计柱」。这里点的就是同一组那张合计柱。
    '<b>这张图回答「MX 的持仓压在哪个产品上」，而同一组那张合计柱'
    f'（组名「{_G_OI_ZH}」，画的是月末未平仓的绝对张数）只回答「一共多少」。</b>'
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
    # 2023-11 起 tmx_all = 三家 + Alpha-X&DRK（差同样恰为 0，见 _all_identity_split()）。
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



# ══════════════════════════════════════════════════════════════════════════════
# 名词释义（SPEC 的 `glossary`，排在所有 exhibit 之前）
#
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图这个月该怎么读」（含当月读数、当月实测的毛刺量）；
# 这一块说的是「这些词是什么意思」，一年到头是同一段 ⇒ 这里**不写当月读数**。
# 出现的数只有两类：把定义钉住的**结构性**量（隐含交易日数有多少个月不是整数、
# 两类利率合约的单张面值差几倍、四档相加与合计的残差）与恒等式本身；
# 能现算的一个都不写死（同本文件其余图注的做法，全部在 import 期从
# series/tmx.csv 与 series/contract_specs.csv 读）。唯一的两个字面常数是
# **官方合约规格里的乘数**（个股 / ETF 期权 100 股·份/张），出处写在 `_FACE_OPT`
# 的注释里 —— 它在 contract_specs.csv 里那一格是空的（📌 未填），现算不出来。
#
# ━━ 为什么是这 15 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 核对表列头里，
# 而且**不看定义就会读错**。按「读错会出什么事」分四类：
#   ① 单位与分母   ADV / 张（contract）/ 月末未平仓（OI）—— 本页四十来张图在
#      contracts/day、contracts/month、contracts 三种量纲之间反复切换，而 MX 的 ADV
#      是官方直接发的、**还原不出来**（一个月跑两套交易日历）。不点破，读者会拿
#      「当月合计 ÷ 交易日数」去核对 ADV，或把存量的未平仓与流量的成交加在一起。
#   ② 合约代码     BAX / CRA、CGB / CGF / CGZ、SXF、个股期货 / 个股期权 ——
#      它们以**裸代码**出现在图题、图例、汇总表行头里，不查表根本不知道是什么；
#      而且各自带一个坑（换代不是归零、张数不是久期、占比高不是抢份额、
#      名字只差一个字却分属两个分母）。
#   ③ 本页轧出来、不是官方披露的数   「其他」段（占比图的残差）、加权平均成交价、
#      每笔平均成交额 —— 这三个在页面上长得和官方列一模一样，必须点明来路，
#      而且「其他」段在本页有**三种**含义。
#      ⚠ 2026-09 复核：上一版这里只写了两种（官方未单列 vs 本仓的管道边界），
#      漏掉了本页 mix 图里占三张的那一种 —— 现货成交额 / 股数 / 笔数的残差段
#      `residual_zh` 明写着「Alpha-X & Alpha DRK」，那是官方 2023-11 起单列、
#      本仓已入库、并且各自另有专图的一条列（`_NOTE_MIX_SPOT` 第一句说的正是这件事），
#      既不是「官方未单列」也不是「本仓的管道边界」。按两分法读那三张图两种都是错的。
#      同一次复核还改掉两处与本页既有图注打架的说法：
#        · 「官方未单列 = 官方表里本来就没有这一栏」对 **LGB 不成立** ——
#          `_NOTE_BOND` 与 CGB 那条词条都写着它在官方 Bond Futures 小节里是一行
#          （四条之和恰是小节 Total），进残差是因为本仓没为它登记列；
#        · 「期权那张的残差 = fetch/tmx.py 没登记那一格」也不全对 ——
#          股指期权那一块**入库了**（`mx_adv_index_options_contracts`，`_NOTE_MIX_OPT`
#          还拿它量过占比），只是归零多年没单开线。
#   ④ 谁是谁的分母 / 外延   MX、TMX 合计、TSX / TSXV / Alpha、Alpha-X & Alpha DRK、
#      S&P/TSX Composite —— 本页最贵的一类误读全在这里：把「TMX 合计」读成加拿大
#      全市场（于是把池内份额读成全国市占率）、把 Alpha-X 2023-11 之前的空白读成
#      「那时没有成交」、拿含仙股的合计去配只含主板成分的指数。
# **有意不收**：
#   · m/m、y/y、单月同比 / 点对点同比、3Y %ile、pp/bp —— 全站通用的读图约定，
#     summary.note 与页尾 notes 第 6、7 条已经逐条讲过，释义板再讲一遍就是两处各写一份；
#   · 「慢腿」「口径断点」—— 页尾 notes 第 2、3 条讲的正是这两件事在本页的**具体落点**
#     （哪几列、哪几张图），那是每月都会变的名单，不该塞进一年不动的释义里；
#   · 「存量 / 流量」—— notes 第 4 条逐列点名了哪些是存量，这里只在「月末未平仓」
#     那一条里带一句它属于哪边就够；
#   · 成交额 / 成交股数 / 成交笔数 —— 本页对它们没有特殊口径（原始单位、当月合计），
#     真正的坑在「谁是分母」上，已由 TMX 合计与那三条盘口词条覆盖；
#   · BOX —— 页尾说明了它只有季度口径、本页一张图都没有，页面上不出现的词不收。
# ══════════════════════════════════════════════════════════════════════════════

#: 个股 / ETF 期权的合约乘数：**官方规格里的常数**，只能写死。
#: series/contract_specs.csv 的 MX_EQUITY_OPT / MX_ETF_OPT 两行 base_notional 那一格
#: 至今是空的（📌 未填 —— 要逐个期权类拉 2019-01 成交量与标的均价才补得上），
#: 所以这个数现算不出来。出处写在同两行的 evidence 列里：
#: 「乘数已核实：100 股/张（m-x.ca 单股期权规格页）」/「100 份/张（Options on ETF 规格页）」。
#: 页尾 notes 与两条图注里那句「一张个股期权的名义值是 100 股 × 股价」用的是同一个数。
_FACE_OPT = 100


def _face(pid):
    """series/contract_specs.csv 里某个 MX 产品的**基期单张面值**（本币，float）。

    利率合约按**面值**计名义额、不乘结算价（报价是 100 − 收益率，乘上去无经济含义），
    所以这一格就是「一张合约代表多大敞口」的官方口径答案。读不到返回 None ——
    缺文件 / 缺行不许在 import 期抛异常（同本文件其余现算函数）。
    """
    path = os.path.join(_ROOT, 'series', 'contract_specs.csv')
    try:
        with open(path, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if r.get('product_id') == pid:
                    v = (r.get('base_notional_per_unit_local') or '').strip()
                    return float(v) if v else None
    except (OSError, ValueError):
        return None
    return None


def _adv_divisor_zh():
    """「当月合计 ÷ ADV」得到的隐含交易日数有多少个月不是整数 —— 现算。

    这是「MX 全所 ADV 还原不出来」这句话的**证据**，不是形容词：MX 一个月里跑两套
    交易日历（利率/债券类跟债市、股票类跟股市），GRAND TOTAL 的 ADV 因此是两套日历
    混出来的，拿当月合计除以任何一个整数天都得不到它。
    容差 0.05 与 fetch/tmx.py 口径坑 2 的反推容差对齐（那边超过 0.05 就判「基准合约
    自己跨了日历」并报错）—— 两处用同一把尺子，免得同一件事在两处各有一个门槛。
    算不出返回空串，调用方退回不带数字的说法。

    ⚠ **这个计数不能整个归因给「两套日历」，所以它自己要把归因拆开报。**
    2026-09 复核：上一版只报「N 个月得不到整数天」并把它直接摆在「两套日历」后面当
    证据，而页尾说明里 `_tday_mismatch_zh()` 现算的是另一个数（两条交易日列真的不等的
    月份数），同一页上两个数并排、读者无从判断该信哪个。实测这不是口径差而是归因错：
    两列不等的那些月份**恰好是**得不到整数天的月份的一个子集，剩下的那些月两列完全
    相同、集中在早年，是官方的量表与 ADV 表本身对不上，与日历无关。
    ⇒ 这里按「两列等不等」把 bad 拆成两堆分别报，两条腿都现算：
      · 不等的那一堆与页尾那条 notes **同源同数**（同样比 trading_days_rates /
        trading_days_equity 两列），页面上不会再出现两个互相打架的计数；
      · 相等的那一堆报个数、最晚月份与最离谱的一个月（隐含天数 vs CSV 记的天数）。
    **上一版那句「最大偏离 X 天」已删**：dev 是「离最近整数的距离」，按定义就 ≤0.50，
    印出来的 0.50 是这把尺子的天花板而不是一个观测，而且会被读成「隐含天数最多差半天」
    ——实际最远的一个月离 CSV 记的天数差了 4 天以上。要报差距就报离**记录值**的差。
    """
    a_col, e_col = 'trading_days_rates', 'trading_days_equity'
    n = bad = same = 0
    last_same = None
    gap, gap_m, gap_d, gap_rec = 0.0, None, None, None
    for r in _rows():
        v, a = _num(r, 'mx_volume_contracts'), _num(r, 'mx_adv_contracts')
        if not v or not a:
            continue
        n += 1
        d = v / a
        if abs(d - round(d)) <= 0.05:
            continue
        bad += 1
        x = (r.get(a_col) or '').strip()
        y = (r.get(e_col) or '').strip()
        if not x or not y or x != y:
            continue                    # 两套日历真的不同 —— 只有这一堆能归因给日历
        same += 1
        last_same = r['month']
        try:
            rec = float(x)
        except ValueError:
            continue
        if abs(d - rec) > gap:
            gap, gap_m, gap_d, gap_rec = abs(d - rec), r['month'], d, rec
    if not n or not bad:
        return ''
    out = f'实测拿当月合计去除 ADV，{n} 个月里有 <b>{bad} 个月得不到整数天</b>'
    if not same:
        return out + '，逐月都对得上「两列不等」那几个月'
    out += (f'；其中 {bad - same} 个月正是两条交易日列<b>本身不等</b>的那几个月'
            f'（与页尾说明里那条现算的是同一批），另外 {same} 个月两列<b>相等</b>'
            f'（最晚一个 {last_same}）')
    if gap_m:
        out += (f'——那是早年官方的量表与 ADV 表<b>本身对不上</b>，与日历无关'
                f'（差得最远的 {gap_m} 隐含 {gap_d:.1f} 天，而两列都记 {gap_rec:.0f} 天）')
    return out


_ADV_DIV = _adv_divisor_zh()
_FACE_STIR, _FACE_BOND = _face('MX_STIR'), _face('MX_BOND')
# 「两类利率合约一张差几倍」——两个面值都读得到才说，读不到就整句不写。
_FACE_ZH = (
    f'本仓 <code>series/contract_specs.csv</code> 记的基期单张面值：'
    f'短端利率（BAX / CRA）C${_FACE_STIR:,.0f}、国债期货（CGB / CGF）'
    f'C${_FACE_BOND:,.0f}，相差 {_FACE_STIR / _FACE_BOND:,.0f} 倍；'
    f'个股与 ETF 期权一张对应 {_FACE_OPT} 股（份）× 标的价。'
    if _FACE_STIR and _FACE_BOND else
    f'不同合约一张代表的敞口差着数量级（个股与 ETF 期权一张对应 {_FACE_OPT} 股'
    f'（份）× 标的价，利率合约按面值计）。')

# BAX → CRA 换代的两个月份：迁移完成月（BAX 转 0 的那一月）与最后一个非零月，
# 与 `_breaks()` 用的是同一个 `_first_zero_after_nonzero()`，不另写一份。
_BAX_LAST, _BAX_GONE = _zero_tail('mx_adv_bax_contracts')[0], \
    _first_zero_after_nonzero('mx_adv_bax_contracts')
_BAX_ZH_G = (f'BAX 的 ADV 自 <b>{_BAX_GONE}</b> 起恒为 0（最后一个非零月 {_BAX_LAST}）'
             if _BAX_GONE and _BAX_LAST else 'BAX 的 ADV 在换代完成那一月起恒为 0')
# Alpha-X & Alpha DRK 单列（并计入 TMX 合计）的首月，以及四档相加与合计的残差。
_AX_FROM = _first_present('alphax_drk_volume_shares')
# 四档相加与合计的残差**不能整段当核对结果用**：一个覆盖 tmx_all_* **全部**月份的
# 「全期最大残差」里，换源前那一段是本仓自己按三档加总出来的，残差恒 0 是定义使然，
# 不是核对结果 —— 释义里报的是下面 `_all_identity_split()` 拆出来的右半段。
# （2026-09 之前这里指的是 `_bench_wedge()` 的 `_BWR`，那个函数随三分法那张图一起删了。）
# **这段注释里一个计数都不写**：写死一次就要过期一次，要看当期数就 import 本模块
# 打印 `_all_identity_split()`（同 `_tday_mismatch_zh()` 的做法）。


def _all_identity_split():
    """「TSX + TSXV + Alpha(+Alpha-X&DRK) ≡ TMX 合计」这条式子里，**哪一段真的核过**。

    2026-09 复核加的：上一版释义把它写成「官方恒等式 … 全期最大残差 0 股（分毫不差）」，
    而 fetch/tmx.py 口径坑 17 写得很直白 —— **CIRO 的历史报里没有「TMX 合计」这一列**
    （它的 `All Traded Marketplaces` 是全加拿大，含 CSE / Nasdaq CXC / MATCHNow / NEO…），
    所以 `_SRC_SWITCH` 之前那一段的 `tmx_all_*` 是**本仓按三档加总**出来的。
    那一段的零残差是**定义使然**，不是核对结果；「官方」与「全期」两个词一起用，
    正好把这件事盖住。这里把月份数按 `_SRC_SWITCH` 拆成两堆，让释义只把
    「核对结果」这四个字给到右边那一堆。

    返回 (换源前月数, 换源后月数, 换源后的最大残差)；算不出返回 (None, None, None)。
    """
    before = after = 0
    resid = 0.0
    for r in _rows():
        tot = _num(r, 'tmx_all_volume_shares')
        if not tot:
            continue
        parts = [_num(r, c) for c in ('tsx_volume_shares', 'tsxv_volume_shares',
                                      'alpha_volume_shares')]
        if any(p is None for p in parts):
            continue
        ax = _num(r, 'alphax_drk_volume_shares') or 0.0
        if r['month'] < _SRC_SWITCH:
            before += 1
        else:
            after += 1
            resid = max(resid, abs(tot - (sum(parts) + ax)))
    if not before and not after:
        return None, None, None
    return before, after, resid


_ALL_N_CIRO, _ALL_N_TMX, _ALL_RESID_TMX = _all_identity_split()

_GLOSSARY = [
    # ── ① 单位与分母 ────────────────────────────────────────────────────
    ('ADV（日均成交）',
     '<b>日均成交张数</b>（average daily volume，contracts/day）。'
     '⚠️ MX 这一侧的 ADV 是<b>官方直接发布</b>的（m-x.ca 月度 xlsx 的 <code>EN ADV</code> 表），'
     '本页<b>不做除法</b>，也<b>还原不出来</b>：MX 一个月里跑<b>两套交易日历</b>'
     '（利率 / 债券类跟债市、股票类跟股市），全所合计的 ADV 是两套混出来的，'
     '拿当月合计除以任何一个整数天都还原不回去。'
     + (_ADV_DIV + '。' if _ADV_DIV else '')
     + '想看「一个月一共做了多少」要看 <code>contracts/month</code> 那张'
       '（「MX 当月成交总量」），它是官方<b>另发的一列</b>，两条谁也不从谁推。'
       '⚠️ 现货那半边<b>一条 ADV 都没有</b>：本页现货三类列一律是<b>当月合计</b>'
       '（官方新闻稿里印的 Daily Average 只保留到 0.1 million，本仓不入库，'
       '见 <code>fetch/tmx.py</code>）。'),

    ('月末未平仓（OI）',
     'open interest：<b>月末仍未了结</b>的合约张数，取自官方 xlsx 的 '
     '<code>MONTH END OPEN INTEREST</code> 列块。'
     '它是<b>某一天的截面（存量）</b>，不是当月累计（流量）⇒ 与 ADV、当月成交'
     '<b>既不能相加也不能比大小</b>，本页也一律不与流量共轴。'
     '本页凡带「月末未平仓」的行、图与核对表列头都是它。'),

    ('张（contract）',
     'MX 那半边的唯一计量单位：<b>合约张数</b>，一张合约成交计 1 张、<b>单边计</b>'
     '（不把买卖两边各计一次）。'
     '⚠️ <b>张数既不是名义额也不是风险敞口</b>：不同合约一张代表的敞口差着数量级 —— '
     + _FACE_ZH
     + '⇒ 本页所有占比图读作「成交（或持仓）<b>张数</b>落在哪个产品上」，'
       '不是收入构成，也不是风险构成。'),

    # ── ② MX 那条腿与它的合约代码 ───────────────────────────────────────
    # 顺序上把 ④ 类里的「MX」提到这里：下面五条讲的都是 MX 的产品，
    # 先说清「MX 是哪半边」再逐个讲代码，比按分类硬排更好读。
    ('MX（蒙特利尔交易所）',
     'Montréal Exchange，TMX 集团的<b>衍生品交易所</b>。本页凡以 contracts 计量的行与图'
     '（ADV、当月成交、月末未平仓、各产品分档）全部只讲它；'
     '加拿大<b>现货</b>那半边（TSX / TSX Venture / TSX Alpha / Alpha-X & Alpha DRK）'
     '是<b>另一条腿</b> —— 另一个官方源、另一套单位、另一个发布节奏。'
     '⇒ 两条腿的读数不能相加；本页的数据月也只由 MX 那条定。'),

    ('BAX / CRA',
     'MX 的两代<b>三个月期短端利率期货</b>：<b>BAX</b> 是加拿大银行承兑汇票期货'
     '（基准 CDOR），<b>CRA</b> 是 CORRA 期货。CDOR 停用后二者完成换代，'
     + _BAX_ZH_G + '，CRA 接棒（月份由 CSV 里 BAX 转 0 的那一月读出，没有写死）。'
     '⚠️ 这是<b>产品替换</b>，不是短端利率业务归零：「短端利率合计」那条跨这个月是'
     '连续的（BAX 掉多少 CRA 接多少），所以本页把两条画在一起，'
     '红色竖虚线也只画在短端利率这几列上。'),

    ('CGB / CGF / CGZ',
     'MX 的<b>加拿大国债期货</b>三档久期：CGB = 10 年（MX 旗舰合约）、CGF = 5 年、'
     'CGZ = 2 年。官方 Bond Futures 小节里还有一个 <b>LGB</b>（30 年），'
     '四条之和恰是小节的 Total ⇒ 本页「国债期货合计」与三档之间的那点残差<b>就是 LGB</b>，'
     '不是一篮子说不清的东西。'
     '⚠️ 三档是按<b>张数</b>并排，不是按利率风险：同样面值下 2 年期与 10 年期的 DV01 '
     '差 5 倍以上（久期约 1.9 年 vs 约 8 年，出处见 '
     '<code>series/contract_specs.csv</code> 的 MX_BOND 行），'
     '而月度成交报表里没有久期字段，本页拆不出风险口径。'),

    ('SXF',
     '<b>S&P/TSX 60 标准股指期货</b>，MX 股指期货的主力合约；'
     '「股指期货合计」减去 SXF 之后那一小段是官方未单列的其余股指合约（SXM 迷你等）。'
     '⚠️ 它的占比常年在九成以上，读作「加拿大的股指期货成交几乎全部集中在<b>一张合约</b>上」，'
     '<b>不是</b>「它打赢了谁」—— 这些合约的唯一挂牌地就是 MX。'),

    ('个股期货 / 个股期权',
     '<b>两条不同的序列，名字只差一个字。</b><b>个股期货</b>（share futures）是期货，'
     '在本页算进「期货 ADV」那张占比图的分母；<b>个股期权</b>（equity options）是期权，'
     '在「MX 期权」那张占比图里，分母是期权 ADV 合计。'
     '⇒ 两者<b>分属两个分母</b>，把它们相加不指代任何东西；'
     '与个股期权同图可比的是 <b>ETF 期权</b>那一段。'),

    # ── ③ 本页轧出来、不是官方披露的数 ──────────────────────────────────
    ('「其他」段',
     '<b>几乎每一张</b> 100% 占比图最上面那一段是<b>算出来的残差</b> —— '
     '合计减去本页画出来的各分项，<b>不是</b>直接取自某一条官方列'
     '（唯一没有这一段的是 MX「期货 vs 期权」那张：两栏之和逐月恰等于合计）。'
     '本页有<b>三种</b>残差，读法完全不同：'
     '① <b>官方单列、本页另有专图</b>，只是这张图没把它画成一段 —— '
     '现货成交额 / 股数 / 笔数那三张，那一段<b>就是 Alpha-X & Alpha DRK</b>'
     '（官方自己一行、本页另有三张图，构成完全已知，见它自己那条词条）；'
     '② <b>本页没为它单画一条线的其余合约</b> —— 国债期货那两张的 <b>LGB（30 年）</b>'
     '（它在官方 Bond Futures 小节里<b>是一行</b>，三档加它之和恰是小节的 Total，'
     '所以那一段就是它）、股指期货那张的 SXM 迷你等（官方在本页取数的那一栏里没有单开）；'
     '③ <b>本仓的管道边界</b> —— 期权那张、MX 月末未平仓那张：官方那几行都在，'
     '本页却没把它们画成一段（有的没入库，有的入库了但归零多年、单开是条死线）。'
     '⇒ ①② 查得到是什么，只有 ③ <b>本页给不出构成，别去估</b>。'),

    # ⚠️ 这条释义 2026-09 改过两处：①「页尾」—— 分解图已用 after_group 前移到它的
    # 输入之后，不在页尾了；②「逐年读数」—— 分解图改月度桶，页面上一个逐年读数都没有。
    # 两处都换成**不带位置、不带桶**的写法，按图题点名（本文件抬头那条教训：
    # 位置与张数写死一次就要错一次）。
    ('加权平均成交价',
     '<b>不是官方披露的数</b>，是「TSX 主板成交额」那张<b>量价分解</b>图现算的派生量：'
     '<code>当期成交额 ÷ 当期成交股数</code>（C$/股）。'
     '它同时含两件事 —— 市场整体涨跌，与成交在贵票和便宜票之间的迁移'
     '（本页把后者叫<b>品种结构</b>）。两者靠 S&P/TSX Composite 拆得开，'
     '拆法与实测读数在那张图的图注里。'),

    ('每笔平均成交额',
     '同样<b>不是官方披露的数</b>：<code>当期成交额 ÷ 当期成交笔数</code>（C$/笔）。'
     '⚠️ <b>它不是价。</b>它衡量的是<b>订单碎片化</b> —— 同一笔母单被切成更多子单时，'
     '笔数上升、每笔金额下降，而成交额与股价一个都没动。要读价请看「加权平均成交价」。'),

    # ── ④ 谁是谁的分母 / 外延（现货那条腿；MX 那一条见上）────────────────
    ('TMX 合计',
     '现货那半边的分母：<code>TSX + TSX Venture + TSX Alpha</code>'
     + (f'（{_AX_FROM} 起再加 Alpha-X & Alpha DRK）' if _AX_FROM else '（后来再加 Alpha-X & Alpha DRK）')
     + '。⚠️ <b>这条恒等式只有右半段是核对结果</b>：'
     + (f'{_SRC_SWITCH} 起 TMX 自报合计的那 {_ALL_N_TMX} 个月是逐月核过的'
        f'（最大残差 {_ALL_RESID_TMX:,.0f} 股）；'
        if _ALL_N_TMX and _ALL_RESID_TMX is not None else
        f'{_SRC_SWITCH} 起那一段是拿 TMX 自报的合计逐月核过的；')
     + f'{_SRC_SWITCH} 之前'
     + (f'那 {_ALL_N_CIRO} 个月' if _ALL_N_CIRO else '那一段')
     + '的合计是<b>本仓按三档加总</b>出来的 —— <b>CIRO 没有「TMX 合计」这一列</b>'
       '（它的 All Traded Marketplaces 是全加拿大，不是 TMX 集团），'
       '所以那一段的零残差是<b>定义使然</b>，不是核对结果。'
     + '⚠️ 它是 <b>TMX 自家盘口之和，不是加拿大全市场</b> —— 加拿大还有 TMX 之外的'
       '交易场所（本页现货历史那一段的源，标题就叫 Report of Marketshare by '
       '<b>Marketplace</b>）。⇒ 本页一切「份额」都是<b>池内份额</b>（分母 = TMX 合计），'
       '<b>不能</b>读成全国市占率。'),

    ('TSX / TSXV / Alpha',
     'TMX 的三个现货盘口：<b>TSX</b> 是主板（Toronto Stock Exchange）、'
     '<b>TSX Venture</b> 是创业板（官方表下脚注写明<b>含 NEX</b>）、'
     '<b>TSX Alpha</b> 是另一个撮合盘口。'
     '⚠️ Alpha 那三列<b>不含</b> Alpha-X 与 Alpha DRK（那两个盘口另有自己的三列）。'
     '三档的标的与上市层级都不同 ⇒ 占比图读作「成交落在<b>哪个场所</b>」，'
     '不是三家在抢同一批订单流。'),

    ('Alpha-X & Alpha DRK',
     'TMX 的另外两个盘口，官方在<b>同一行里合并披露</b>（所以本页也只有合计一条列，'
     '拆不开），并且'
     + (f'<b>{_AX_FROM} 才开始单列</b>并计入 TMX 合计。' if _AX_FROM else
        '在某一月才开始单列并计入 TMX 合计。')
     + '⇒ 图上它在那之前是空的，含义是<b>当时的「合计」口径不含它们</b>，'
       '不是那时没有成交；跨那个月读 TMX 合计与各段占比，<b>分母变大过一次</b>'
       '（红色竖虚线标的就是这件事）。'),

    ('S&P/TSX Composite',
     '加拿大股票市场的宽基指数，本页画的是<b>月末收盘点位</b>（<b>存量</b>、时点数）。'
     '日常增量与现货成交印在<b>同一张官方表</b>里；更早的历史由 TMX Money 的官方指数'
     '历史回补（<code>fetch/tmx.py</code> 每次回补都拿重叠月逐格断言，对不上就拒绝入库），'
     '所以左边那一段不是另一套数。'
     '⚠️ 它的成分是 <b>TSX 主板</b>的票，<b>不含</b> TSX Venture'
     '（后者另有 S&P/TSX Venture Composite 一条）—— 这正是本页量价分解图'
     '一律画 TSX 主板、而不画 TMX 合计的原因：拿它去除含仙股的合计均价，'
     '算出来的「品种结构」有一大截只是盘口混合比例。'),
]


# ── 慢腿名单：SPEC['slow_cols'] 与页尾那条 note 共用这一份 ────────────────────
# 它们与 MX 不同源、晚一档发布，最新月留空是**正常状态**，不参与发布门槛判定；
# 不这么标，整页的发布门槛会被现货那半边永久拖住一个月。
# ⚠️ 名单只写这一份、条数一律现算。上一版页尾那条 note 写死「所以 17 条现货列全部
# 标为 slow_cols」—— 数对、名不对：17 条里有 2 条是**月末指数点位**，按本页自己的
# 释义（「MX」条把现货那半边点成 TSX / TSX Venture / TSX Alpha / Alpha-X & Alpha DRK）
# 与另外两条 note 的分档（`_seg_zh()` 把「月末指数点位」与「加拿大现货成交」列成两段
# 不同的历史；「存量与流量」那条把两条指数列归进存量）都不算现货列，现货实为 15 条。
# ⇒ 下面按列名后缀把两档分开，note 里的三个数全部由 len() 现算：加一条列、
#   或把某条列从慢腿里拿掉，那句话自己跟着变。
_SLOW_COLS = [
    'tmx_all_volume_shares', 'tmx_all_value_cad', 'tmx_all_transactions',
    'tsx_volume_shares', 'tsx_value_cad', 'tsx_transactions', 'tsx_composite_close',
    'tsxv_volume_shares', 'tsxv_value_cad', 'tsxv_transactions', 'tsxv_composite_close',
    'alpha_volume_shares', 'alpha_value_cad', 'alpha_transactions',
    'alphax_drk_volume_shares', 'alphax_drk_value_cad', 'alphax_drk_transactions',
]
#: 月末指数点位那一档（`*_composite_close`）与现货成交那一档，分开数。
_SLOW_IDX = [c for c in _SLOW_COLS if c.endswith('_composite_close')]
_SLOW_SPOT = [c for c in _SLOW_COLS if c not in _SLOW_IDX]

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
    # 逐月无洞、次月第 1–4 个工作日发布，是本页发布最快的那一批列（= 非 slow_cols
    # 那半边，全部出自同一份 m-x.ca 月度 xlsx）里的一条（覆盖多少个月由 `_dense_zh()`
    # 现算、在本页所有列里排第几由 `_cover_rank_zh()` 现算，两处都写进页尾 notes 的
    # `_note_mx_adv`；这里**不写数**：上一版在这里与那条说明里各写死一份「295/295」，
    # 回补一个月之后两处一起变成假话）。
    # ⚠️ **「最快」不等于「最长」**：上一版这里与页尾那条说明都写着它是本页「最长」的
    # 序列，而月末指数点位那一档起步更早（2026-09 收口复核实测），两处一起是假话。
    # 名次改由 `_cover_rank_zh()` 现算，这里不再复述一份。
    # ⚠️ 它同时是最上面那组 `mix` 的 `total`，所以那一组的合计柱不出 —— 开篇这张
    # 已经把同一列画过了，而且窗口更宽。见本文件抬头「图列」那一段。
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
        # 那条理由**在 2026-09 之后不成立了**，但不是因为口径变干净了：全站改单月之后
        # `mix` 的合计柱走的也是单月同比，拆不拆组都是同一条金线，所以它已经不能当
        # 「必须放在同一组」的理由用。（`granularity` / `total_col` / `weight_col`
        # 三个还原用的键同轮从底座与 spec 里一并删除，见 CONTRACT §6.4。）
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
            # ⚠️ **这一组没有 `note`**，而且加不回来：`note` 只挂在合计柱的图注上，
            # 而这一组的合计柱不出（`total` 就是头条那一列，开篇图已经画过、窗口更宽，
            # 见本文件抬头「图列」那一段）。写了就是一条永远印不出来的死配置，
            # 所以底座在 `mix_pair` 里对「折叠 + 声明了 note」**硬失败**（退出码 1）——
            # 不是靠这行注释拦着。原来挂在这里的那段（这条序列的脾气：日均而非月合计、
            # 发布最快、本页的数据月由它定）已搬到页尾 notes 的 `_note_mx_adv`。
            'share_note': _NOTE_MIX_MX}},

        # 个股期货从「个股与 ETF 期权」里拆出来，落在这一组里 —— 它是**期货**不是期权，
        # 进不了那张期权占比图的分母，而在这里它正好是「期货 ADV」的四个分项之一。
        # 本组的合计 `mx_adv_futures_contracts` 声明在最上面那组（在那里它是
        # 「期货 vs 期权」的一个分项），跨组引用即可。
        #
        # 这一对是「MX 衍生品 ADV」那组的**下一层**：上一层（开篇那张全历史柱讲规模、
        # 紧跟的 100% 占比堆叠讲结构）说 MX 的量里期货占多少，这一对说期货那一块里
        # 利率、股指、个股各占多少 —— 也就是「MX 到底是一家做什么的交易所」。
        # ⚠️ **按内容点名，不写 Exhibit 号。** 这句话上一版把上一层那两张的图号写死了，
        # 而开篇两张并成一张之后全页编号左移过一位，它**当时就已经指错一号**、
        # 没有任何护栏会响；本轮删掉那张合计柱，还会再错一次。改成点名内容就永不过期。
        # 四个分项之和与合计的残差实测在千分之二以内（官方未单列的其余期货）。
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
        # 单月是全站唯一口径（CONTRACT §6.1 第 1 条），§6.6 的自动判据
        # 要求它写进标题（R4，不写就报 🟡）。
        # 这一组只有这一列，所以声明不会误标到别的图上。
        {'zh': 'MX 当月成交总量（次轴：单月同比）', 'cols': [
            {'col': 'mx_volume_contracts', 'zh': '当月成交',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 存量单列一组：点对点同比对期末口径是合法读法，这里保留它。
        # ⚠ 给下一个改这里的人：**「存量不能做滚动」是一句错话**。12 个月合计比恒等于
        #   12 个月均值比（除数 12 约掉，build/yoy.py 实测差 2.3e-14），所以存量序列
        #   画滚动窗口同比在数值上完全正确 —— 错的只是**把它叫「合计」**
        #   （12 个月末未平仓相加不指代任何真实的量）。
        #   ⚠️ 但 2026-09 起这条算术**不再是一条可选的画法**：页上一条滚动线都不画
        #   （CONTRACT §6.1 第 2 条，页面所有者指定），噪声大改用轴范围
        #   （`ycap` / `yfloor`）压，不换口径。`yoy.ttm_mean_yoy(s, kind)` 仍在模块里，
        #   但只能在图注里当对照数字出现，写的时候必须叫「12 个月滚动**均值**同比」。
        # 本组只声明合计那一条列，五个分项都引用自后面各自的组 —— mix 的 total/parts
        # 写的是**列名**，跨组引用即可。五段 + 一段残差正好用满本仓全部 6 个数据色，
        # 是 `MIX_SEG_COLORS` 的硬上限；再多一档就得先在这里把小块并进残差。
        # 组名从 `_G_OI_ZH` 取：本组的 share_note 要按名字点这一组的合计柱，
        # 两处共用一份，改名不会留下一处指不着的交叉引用。
        {'zh': _G_OI_ZH, 'cols': [
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
            # 第 2 条）。（那三个键 2026-09 已从底座与 spec 里一并删除，这里留一句
            # 是为了让下一个人知道它们为什么不该回来。）存量柱的次轴走点对点同比，
            # 底座自己认得。
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
        #   两列补齐后三档与合计逐月闭合，剩下的只有 LGB（见 _NOTE_BOND）。
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
            # ⚠️ tsx_value_cad 的**列配置不在这里** —— 2026-09 搬进了下面那个
            # 「TSX 主板成交额」锚点组。下面 mix 的 parts 写的是**列名**，跨组引用即可
            # （本页 MX 期权、MX 月末未平仓两条 mix 已经是这个写法）。
            # 为什么必须搬而不是在两处各写一份：`by_name`（build/single.py 的 `_norm_mix`）
            # 后者覆盖，而末尾核对表按 `seen` 去重、前者优先 —— 两条路径的取舍方向
            # **相反**，同一条列会在堆叠段名与核对表表头上印出两个名字，
            # 而 `_norm_mix` 的 docstring 明写这种分叉「没有任何护栏会响」。
            {'col': 'tsxv_value_cad', 'zh': 'TSX Venture',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'alpha_value_cad', 'zh': 'TSX Alpha',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
         ], 'mix': {
            'total': 'tmx_all_value_cad',
            'parts': ['tsx_value_cad', 'tsxv_value_cad', 'alpha_value_cad'],
            'residual_zh': 'Alpha-X & Alpha DRK（2023-11 起计入合计）',
            # ⚠️ 2026-09 删掉的 `'rhs_share': 'alpha_value_cad'`（页面所有者拍板）：
            # 那条右轴线画的是 TSX Alpha 的占比，而它**就是这张堆叠的第 3 段** ——
            # 同一条序列换个刻度再画一遍，`ylab2` 自己就是这么写的。
            # 所有者的既有指令：同一条序列不许换个切法再画一遍。
            # ⚠️ **别顺手把股指期货那组的 `rhs_share: 'residual'` 也删了**：
            # 那一段是**算出来的残差**（股指期货合计 − SXF，本仓没有对应的列），
            # 薄得多 —— 整个量程都压在 0–100 柱高最下面那一截里，几个百分点的进退
            # 在那个刻度上量不出来（这正是 build/single.py 给 `rhs_share` 立例外时
            # 写下的判据：「某一段常年只占几个百分点，在 0–100 的堆叠里它几个 pp 的
            # 变化根本量不出来」）。与本条删掉的那条正相反：那条画的 TSX Alpha
            # 取自一条真实存在的列，在堆叠里常年厚到段高本身就把它读出来了。
            # ⚠️ 2026-09 收口复核订正（页尾历史账（三）里有同一句的副本，两处同步改）：
            # 上一版这里写的是「那一段窗口内最低只有零点零几个百分点…扣掉段间白缝之后
            # 高度就是 0 —— 那条线是那张图的全部内容」。实测是假话：2026-09 当期
            # 128 格里最低 0.04%（2022-04）、最高 5.87%（2025-10）、68 格 ≥ 0.6%
            # （= 底座 `MIX_TINY_SEG_PCT`，那条「扣完白缝高度就是 0」的门槛），
            # 一半以上的月份画得出来，而且与那张图自己的图注（底座现算的
            # 「窗口内它最大占到 X%」）当场打架。保留这条线的理由是**读不出**、
            # 不是**画不出**。（这四个数是那一次的实测记录，不是页面上的话 ——
            # 页面上一个都不许抄，区间与右轴量程一律由底座现算印在图注里。）
            'share_note': _NOTE_MIX_SPOT}},

        # ── 分解图的锚点：本页唯一一张画 tsx_value_cad 水平值的图 ────────────────
        # ⚠️ **这一组不是装饰，是 `decomp` 的 `bucket='monthly'` 的硬前提。**
        # 底座（build/single.py 的 `_decomp_monthly`）在出月度分解图之前现验：本页必须有
        # **唯一一张**「该金额列的水平值 + 次轴单月同比、且横轴与分解图逐格相同」的图；
        # 找不到就 SpecError。有了它，分解图的图注才敢说「菱形与那张图的金线是同一条数」
        # 「可以逐格上下对读同一个月」—— 而这两句话正是把分解图前移到输入之后的全部理由。
        # ⇒ 删掉这一组 = 两张分解图当场硬失败，不是「少一张图」。
        #
        # ⚠️ 组名带口径、**列的 zh 保持「TSX」不动**：它同时被上一组 mix 的堆叠引用，
        # 改名会把那张 100% 堆叠的段名与图注读数一起静默改掉（图例印「TSX 成交额」、
        # 核对表表头仍印「TSX」）。口径一律写进组名，组名只进本组的图题。
        #
        # ⚠️ 跨组引用**不吃掉**被引用那一列在它自己这一组里的图（`eaten` 按组算，
        # 见 `Page.mix_pair`）—— 与 SXF / 个股期权 / ETF 期权三张存量柱同一条规则，
        # 所以这一组照常出一张 gs_bar。
        {'zh': 'TSX 主板成交额'
         + _since('tsx_value_cad', '慢腿；次轴：单月同比'), 'cols': [
            {'col': 'tsx_value_cad', 'zh': 'TSX',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
        ]},

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

    # 慢腿名单在上面的 `_SLOW_COLS`（页尾那条 note 与这里共用一份，条数现算）。
    'slow_cols': _SLOW_COLS,

    'breaks': _breaks(),

    # ══ 量价分解：两张两分法，同一条成交额换两个量腿 ═══════════════════════════
    # 为什么是 TSX 而不是 TMX 合计、为什么三因子拆成两张图，见模块 docstring。
    # 两张都 granularity='monthly_total'：series/tmx.csv 的现货三类列都是**原始月度合计**
    # （量级见页尾 notes 里那条现算的举例，11–12 位数），不是日均。
    # ⇒ 一律**不给** weight_col：声明 monthly_total 又给 weight_col 是硬失败，
    #   而真乘上去会把桶内合计放大二十几倍，图形却照常画得出来。
    # scale 只做显示换算（金额 ×1e-9 → C$bn、股数 ×1e-9 → bn shares、笔数 ×1e-6 → mn trades），
    # 它在分子分母上同时出现，对分解结果一个数都不影响。
    #
    # ── 2026-09：桶从日历年改成**月度**，位置从页尾改成**紧跟输入之后** ──────────
    # 两件事是同一件事的两半（asx 那一轮的判例）：改月度桶让它与本页其余时序图同一个
    # 刻度、同一个基期（去年同月），前移让「输入 → 分解」在阅读顺序上连成一段。
    # ⚠️ **月度桶下 year_start_month / year_label / years 三个键一写就硬失败**
    #   （build/single.py 的 `_norm_decomp`，判据是 `k in d`，写 None 也算写）：
    #   它们只管年度分桶，留一个都会让下一个人以为月度图的横轴还受它们管。
    #   日历年 / FY / YTD 那一整套在本页已经作废。
    # ⚠️ **spec 侧一个字都不许写 xrot / full / height / xstep**：128 格的排版由
    #   `build/mrwin.py` 统一算（见 `_decomp_monthly` 的 docstring 里那段警告）。
    #
    # ── `after_group` 挂哪一组：判据是「紧跟它的**两条**输入里较后的那一个」──────
    # 值必须逐字等于某个 group 的 zh 且在本页唯一，打错字底座当场 SpecError；
    # 而组名带着 `_since()` 现算的那半句「（YYYY-MM 起，慢腿）」，所以这里**必须写成
    # 同一个表达式**。抄成字面量「加拿大现货成交股数（2015-01 起，慢腿）」会在下一次
    # 回补把起点改掉的那一刻静默过期 → 硬失败（asx.py 记的是同一条）。
    # 逐条判：
    #   · 两张的金额腿都是 tsx_value_cad ⇒ 输入之一是新增的「TSX 主板成交额」那一组
    #     （本页唯一一张画它水平值的图，也是月度桶的硬前提，见那一组的注释）。
    #   · 图 A 的量腿是 tsx_volume_shares ⇒ 另一个输入落在「加拿大现货成交股数」那组：
    #     它被那组的 mix 吃掉，**页面上没有任何一张图画它的水平值**，只有那张 100% 堆叠
    #     里的一段占比（tsx_volume_shares ÷ tmx_all_volume_shares）。⚠️ 那一段**不等于**
    #     量腿本身（一个是占比、一个是水平值）—— 挂在这一组，是因为那一段是页面上离这条
    #     序列最近的落点，不是因为那一段就是它。
    #   · 图 B 的量腿是 tsx_transactions ⇒ 同理落在「加拿大现货成交笔数」那组。
    # 两条输入里较后的那个分别是股数组与笔数组 ⇒ 就挂在它们后面。读者往上一格是那一组的
    # 占比堆叠（量腿在集团里占多少就是里面的一段），再往上一格是那一组的合计柱（TMX 合计
    # 口径，**不是** TSX）；金额腿另有自己那一组的水平值柱，在更上面几格。
    # 与 asx 那一轮的挂法同一条判据：分解图紧跟它两条输入里较后的那一条的落点。
    'decomp': [
        # ── 图 A：量 × 价。派生量是成交量加权平均成交价 ⇒ kind='share_price'。
        {'zh': 'TSX 主板成交额',
         'kind': 'share_price',
         'granularity': 'monthly_total',
         'bucket': 'monthly',
         'after_group': '加拿大现货成交股数' + _since('tsx_volume_shares', '慢腿'),
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_volume_shares', 'zh': 'TSX 成交股数',
                 'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         # C$bn ÷ bn shares = C$/股，两边的 1e9 自己抵掉 ⇒ price_scale 用缺省 1.0。
         'price_zh': '加权平均成交价',
         'price_unit': 'C$/share',
         'price_fmt': 'f2',
         'note': _NOTE_PRICE},

        # ── 图 B：笔数 × 每笔金额。派生量是每笔平均成交额 ⇒ kind='per_trade'。
        #    ⚠ 绝不能写 share_price：底座会据 kind 印出「它不是什么」那段话，
        #      把「订单碎片化程度」说成「价格」是本批最容易犯的错。
        {'zh': 'TSX 主板成交额（按成交笔数拆）',
         'kind': 'per_trade',
         'granularity': 'monthly_total',
         'bucket': 'monthly',
         'after_group': '加拿大现货成交笔数' + _since('tsx_transactions', '慢腿'),
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_transactions', 'zh': 'TSX 成交笔数',
                 'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
         # C$bn ÷ mn trades = 1e-3 × (C$/笔) ⇒ price_scale=1e3 换回 C$/笔。
         # 纯单位换算，对增长率没有任何影响，只决定图注里报出来的水平值读数。
         'price_zh': '每笔平均成交额',
         'price_unit': 'C$/trade',
         'price_fmt': 'f0c', 'price_scale': 1e3,
         'note': _NOTE_TRADE},

        # ⚠️ 2026-09 删掉的第三条（三分法，'TSX 主板成交额（相对 TMX 集团）'，
        # bench = TMX 集团合计）：它与图 A 是**同一对列**（tsx_value_cad ÷
        # tsx_volume_shares）换个切法再画一遍，而它真正多问的那件事 ——
        # 「TSX 在集团里占多少、份额怎么动」—— 本页三张 100% 占比堆叠
        # （成交额 / 股数 / 笔数各一张）已经各答过一次，而且答得更直接。
        # 页面所有者 2026-09 拍板删。理由与去处写进了页尾那条历史账，
        # `_NOTE_SHARE` / `_bench_wedge()` / `_BWM/_BWC/_BWX/_BWR` 一并删掉，不留死代码；
        # 它图注里那条「各盘口均价差着一两个数量级」的现算证据搬进了 `_NOTE_PRICE`。
    ],

    # ══ 为什么没有 'level_yoy' 段（旧名 'ttm_yoy'）══════════════════════════
    # 曾经有两条：「MX 衍生品成交量」与「TMX 合计现货成交股数」，都是
    # 「水平值柱 + 12 个月滚动同比」。2026-09 改版之后这两条列的水平值柱改由别处产出
    # —— **图型与列相同，口径不同**：次轴由 12 个月滚动同比改成单月同比
    # （全站统一，页面所有者指定），两条图注也因此整段重写过。
    #   · MX 那条 → **开篇那张全历史柱**（headline_style='bar_yoy'）。它同时是最上面
    #     那组 mix 的 total，所以那一组的合计柱不出，只留占比堆叠（见抬头「图列」）；
    #     原来挂在合计柱上的那段说明搬到了页尾 `_note_mx_adv`。
    #   · 现货那条 → 「加拿大现货成交股数」那组的 mix 的合计柱（`_NOTE_TTM_SPOT`，
    #     total=tmx_all_volume_shares；它不是头条列，那张合计柱照常出）。
    # 留在 'level_yoy' 里会画出**第二张一模一样的图**（底座把它追加在全部
    # exhibit 之后，不会去重），所以在这里删掉，而不是在底座里加一条去重规则。

    # 名词释义：排在所有 exhibit 之前。选词判断与「有意不收」的理由写在 `_GLOSSARY`
    # 上面那块注释里（为什么是这 15 个词、按「读错会出什么事」分哪四类）。
    'glossary': _GLOSSARY,

    'notes': [
        # ── 本轮的历史账（页面所有者 2026-09 的四条指令，一条 note 覆盖全部四件事：
        #    并掉逐点相同的那一对 / 删掉同一对列换个切法的那张分解 /
        #    删掉与堆叠某一段同源的那条右轴线 / 分解改月度桶并前移到输入之后）──
        # 判例第 4 条（asx / cme / cboe 三轮都照这条办）：删图与重排必须在页面上向读者
        # 交代。读者手里可能还留着上一版的图号（站外引用、自己的笔记都按号说话），
        # 不写明白就只剩「怎么少了一张、后面的号还全变了」。
        # ⚠️ 本页是声明式 spec 页，**图号由底座按渲染顺序现算** —— 这一条里
        #    一个新号都不许写死，只用「原 Exhibit N」（冻结的上一版编号）与相对位移。
        #    同理它是历史账、不随数据变 ⇒ 一个当月读数、一个会随窗口滚动的期数都不含，
        #    全是静态字面量（重叠了多少个月每月加一，写下来就等着过期）。
        # ⚠️ 但它**不是无条件印的**：本轮四件事里「并图」那一件由底座每次构建重新判定，
        #    所以整条写成 `callable(page)`、回读那本账现算收放（连带旧→新图号对照里
        #    那一号的位移）—— 理由见 `_note_2609` 的 docstring。
        _note_2609,

        # ⚠️ 同样是 `callable(page)`：它里面两句指路（「哪张图次轴上那条单月同比」
        #    「想看开市那天有多热看哪张」）指的图是底座每次构建现判的，写成字面量
        #    就会在去掉 `headline_style` 的构建里指着一条不存在的次轴 ——
        #    理由见 `_note_mx_adv` 的 docstring。
        _note_mx_adv,

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
        f'所以现货那 {len(_SLOW_SPOT)} 条成交列'
        + (f'、连同 {len(_SLOW_IDX)} 条月末指数点位（同样晚一档发布，不是现货成交列）'
           if _SLOW_IDX else '')
        + f'，共 {len(_SLOW_COLS)} 条全部标为 slow_cols，'
          '最新月留空是正常状态，不参与发布门槛。',

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
        f'是两家各自的统计口径。接缝处的纯口径台阶：'
        f'tsx_volume_shares {_step_pct("tsx_volume_shares")}、'
        f'TMX 合计股数 {_step_pct("tmx_all_volume_shares")}，'
        f'三条成交额 +0.15%~+0.17%，其余 7 列 |台阶| ≤0.11%。'
        f'⇒ 图上只给前两条列画 {_SRC_SWITCH} 的红色竖虚线（标签「{_SRC_ZH}」），'
        '其余列跨这个月是可比的，画了等于说假话。'
        '**回补只往左填空、不覆盖已有值**：2021-08 起印在图上的仍是 TMX 官方新闻稿的原值。'
        '⚠️ 两张量价分解图是**月度桶**（一格 = 一个月、基期去年同月），'
        f'所以受这次换源影响的是<b>本期在 {_SRC_SWITCH} 之后、基期在它之前</b>的'
        '那连续 12 格（具体月份印在那两张图各自的图注里，由换源月现算）：'
        '它们的本期与基期分别站在两把尺子的两侧，读到的有一部分是口径不是业务。'
        f'受影响多大逐列不同，就是上面那张台阶表：成交股数的台阶最大'
        f'（就是表里那条 {_step_pct("tsx_volume_shares")}，全页之最），'
        '成交额一侧方向相反且小一档，成交笔数两把尺子几乎重合 —— '
        '所以这 12 格在用到成交股数的那张分解上最明显，在按成交笔数拆的那张上几乎看不出来。'
        '照实说明，不做剔除 —— 剔除等于自造一条谁也没发过的序列。',

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

        _NOTE_BOND,

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
