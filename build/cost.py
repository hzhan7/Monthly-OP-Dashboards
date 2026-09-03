# -*- coding: utf-8 -*-
"""Costco (COST) 月度销售 —— 生成 data/cost.js（网页看板的数据源）。

本文件是 costco-monthly-sales/build_data.py 的移植：那个站已经上线并由用户逐张验收过，
所以 **exhibit 的顺序、编号、标题文案、图注、窗口、截轴与断点一张都没改**，
改的只有三处工程约定：

  1. 数据源改读本仓库的 series/cost.csv —— 它就是真值，由 fetch/cost.py 每月解析
     官网新闻稿后追加（历史内容承自已删除的 /COST月度销售 skill，逐字节未改）。
  2. payload 顶层字段名改成 build/CONTRACT.md 的统一契约（window.DASH，
     不再是 window.COST_DATA），补上 ticker / tracker / title / notes / footer。
  3. 汇总表的行由 {cur,prev,yag,mm,...} 摊平成 cells 数组，末尾核对表由裸数组
     改成 {n,title,cols,rows} 且单元格全部是**已格式化的字符串**（页面不做计算）。

原 index.html 里写死的「口径与方法说明」10 条搬进 payload.notes；其中 53 周月份
那条改成从数据里自动识别（原来是手写死的四个月份，加一个 53 周财年就会过时）。

CSV 列义：_r = reported（报告口径）, _a = adjusted（核心口径，剔除汽油与汇率）
         tc = total comp, us/ca/oi = 美国/加拿大/其他国际, ec = 电商, wh = 仓库数

依赖：pandas、numpy
用法：python3 build/cost.py
"""
import datetime
import json
import os
import re

import numpy as np
import pandas as pd

import axisfmt
import chartscale                    # Exhibit 15 现算「半栏/通栏各多宽」用的量边距算式
import brief as B                  # 顶部 brief 的共享规则库（R1-R6），只算事实不出文字
import mrwin                            # 通栏 / x 标签抽稀的裁决层，与 single.py 共用
import payload_guard
import pctile                      # 3Y %ile 的唯一实现，本文件不再自己写分位判据
import yoy as Y                    # 同比口径的唯一实现；本页图上的增速全是公司披露值，
#                                    只借它的窗口常量把「§6.1 第 3 条那笔代价账为何在本页
#                                    无处可印」写清楚，一个同比数都不由它算

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES_DIR = os.path.join(ROOT, 'series')
SERIES = os.path.join(SERIES_DIR, 'cost.csv')
OUT = os.path.join(ROOT, 'data', 'cost.js')


def _source_dates():
    """按路径加载仓库根的 source_dates.py：`python3 build/cost.py` 跑起来时
    sys.path 上只有 build/，裸 import 会 ModuleNotFoundError。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 时序图的窗口起点。2026-08-18 从原 PDF 的 2021-01 改成 2016-01，全站统一
# （build/single.py 的 WIN_FROM、cboe / cme / hkex 的同名常量、msci 的 WIN0 都是这一个）。
# 原来只有头条图（Ex2）用 2016 起的长窗口，理由写在下面那条 HIST_START 上 ——
# 那条理由（「2021 起的窗口里基数本身被 COVID 扭曲，『当前 7-8% 相对 Costco 常态算什么
# 水平』在短窗口下根本回答不了」）对**其余每一张 comp 图**同样成立，所以现在两者相等。
# 两个名字都保留：HIST_START 是「头条图刻意用长窗口」这个决定的锚点，
# 哪天想让头条图再长一些（本页 series 自 2015-12 起），改它一个就够。
WIN_START = '2016-01'
HIST_START = '2016-01'
# ECOMM_START = '2022-01' 已删（2026-08-19）：那是画图时截的窗口，不是数据的边界 ——
# 与 Exhibit 12 上一轮用的是同一条判据，当时漏了这张。series/cost.csv 里 ec_r 自 2017-09、
# ec_a 自 2017-12 起逐月无缺，2022 之前另有 52 / 49 个公司披露值被这个常数挡在图外。
# 左端改成现算：max(WIN_START, 两条腿里最早的那个首值)（见 main() 里的 ECOMM_FROM）。
# 不写死也不回退到 2022：写死一个新常数只是把过期时间往后推。
# OVERLAY_MONTHS = 25 已删（2026-08-19）：唯一用它的 Exhibit 12 改成 win() = WIN_START 起。
# 留着一个没人用的旧窗口常量，下一次有人「顺手复用一下」就把 25 个月又带回来了。
# FY26 起 e-commerce comp 更名为 Digitally-Enabled comparable sales，公司不重述历史。
# 断点在哪张图上画得出来、汇总表哪几格要加注，全部由它现算，不写死索引也不写死月份文案。
ECOMM_BREAK = pd.Period('2025-09', 'M')

# SRC 见下面正文块 §3：两条腿并列（月度新闻稿 + SEC 申报），旧的单源那一行已删。


# ─────────────────────────── ① 模块级：常量 + loader ───────────────────────────
# 本页其余每一张图的出处都是官网月度新闻稿（`SRC` 那一行），而**分部口径的收入新闻稿
# 从来不报** —— 只有 10-K / 10-Q 的分部附注（Segment Reporting）里有。也就是说这两张
# 新图的出处与全页 `source` 那一行不是同一个，而 CONTRACT §3 的公共字段表里**没有**
# 逐图覆盖 source 的字段。做法照 build/axp.py：出处写进**标题前缀常量**再加一份
# src_extra，两处都点名表单与 CIK（axp 用 SEC_A / SEC_T / SEC_O 三个前缀分别标
# 「新口径」「Form 10-D 信托」「旧口径」，同一套写法）。
#
# ⚠️ 两个前缀而不是一个，是因为两张图的**表单不同**：分部收入在 10-K/10-Q 的附注里，
# 客单/客流在 8-K 的 Exhibit 99.2 里。共用一个「【SEC 10-K/10-Q】」前缀会把 8-K 的数
# 挂到 10-K 名下 —— 那是页面上一句可证伪的假话，而本仓对这类话是零容忍的。
# 共同的部分（同一家申报人、同一个 CIK）由 `SEC_CIK` 一个常量供两处引用，
# 前缀本身也共用「【SEC · 」这个头，读者一眼看得出是同一族。
SEC_CIK = '0000909832'
SEC_SEG = '【SEC · 10-K/10-Q 分部附注】'
SEG_Q = os.path.join(SERIES_DIR, 'cost_seg_q.csv')
FY_SERIES = os.path.join(SERIES_DIR, 'cost_fy.csv')

# 分部序列的**数据下限**（不是画图时截的窗口 —— 本页的窗口纪律见 Exhibit 10/11 的图注：
# 「那是画图时截的窗口，不是数据的边界」，够得到就画满）。Costco 自 2010-08-30 起把
# 原本 50% 权益的墨西哥合资公司并表，**并且不重述历史**：并表日之前的 Other International
# 与之后不是同一个口径，跨过去读会看到一个纯属并表造成的跳升。cost_seg_q.csv 的第一行
# period_start 正是这一天，下面有一条断言钉住它 —— 哪天 CSV 往前补了行，构建期当场停机，
# 而不是让这张图悄悄跨过一个没有画出来的口径断点（CONTRACT §5 第 2 条）。
SEG_FLOOR = '2010-08-30'


def load_seg_q():
    """series/cost_seg_q.csv —— 分部收入，USD **百万**，**总收入**口径。

    ⚠️ 口径一句话说清：`us_mn / ca_mn / oi_mn / total_mn` 是**总收入**
    （净销售额 + 会员费），**不是净销售额**。本页 Exhibit 2–6 画的全是净销售额口径的
    comp 与净销售额本身，两者不是同一个量 —— 图的标题、纵轴标题、图注三处都必须点明，
    否则这张图会安安静静地和同一页其余的图互相矛盾。

    列义：
      fq            'FY11Q1'…'FY26Q3'（scope='Q'）/ 'FY11'…'FY25'（scope='FY'）
      weeks         Q1–Q3 各 12 周，Q4 16 或 17 周（53 周财年），全年 52 / 53 周
      derived       1 = 该行是**推导值**（每个 Q4 都是）：Costco 从不单独披露第四财季，
                    Q4 = 全年 − 同一起点的 36 周 YTD。CONTRACT §5 第 1 条要求标出来。
      accession     该行读自哪一份申报（EDGAR accession no.）
    """
    d = pd.read_csv(SEG_Q, dtype={'fq': str, 'scope': str, 'accession': str})
    need = ['fq', 'period_start', 'period_end', 'weeks', 'scope',
            'us_mn', 'ca_mn', 'oi_mn', 'total_mn', 'derived', 'accession']
    miss = [c for c in need if c not in d.columns]
    if miss:
        raise SystemExit(f'series/cost_seg_q.csv 缺列 {miss}')
    return d


def load_fy():
    """series/cost_fy.csv —— 年度损益/门店表。本块只用三列：

      memb_fee_mn / net_sales_mn / total_rev_mn

    用途只有一个：给「会员费按地区拆不开」这层不确定**定界**（见 Exhibit 7 的图注）。
    不把它画成图 —— 年度频率的东西挤进季度轴，只会多出一条读者对不上的线。
    """
    d = pd.read_csv(FY_SERIES, dtype={'fy': str})
    need = ['fy', 'net_sales_mn', 'memb_fee_mn', 'total_rev_mn']
    miss = [c for c in need if c not in d.columns]
    if miss:
        raise SystemExit(f'series/cost_fy.csv 缺列 {miss}')
    return d


def fq_xlabels(fqs, who):
    """财季 x 标签的构建期闸门：既保证格式，也保证它**长得不像月份**。

    main() 末尾那段 WINDOW_NOTE 要给每张图判横轴步长（`_cadence_of()`），判据第一步是
    `_MLAB_RE.match(标签)` —— 'Jan-21' 这种月份格式。而 Costco 的财年结束在 8 月末或
    9 月初（近十年有 5 年落在 9 月），季末**月份**之间的间隔是 2 / 3 / 4 个月、**不唯一**：
    一旦这两张图的标签长得像月份，`_cadence_of()` 会当场
    `raise SystemExit('…相邻两格的间隔不是同一个数…')`，整页停更。

    'FY11Q1' / 'FY24Q3' 这种标签匹配不上那条正则，于是它们落进 `_nonmonth` 那一档，
    被页尾那段注文按「横轴不是逐月月份轴」逐张点名 —— 那正是我们要的结果。

    这里用**独立实现**（strptime 解析成功即判定「像月份」）复核同一件事，
    而不是把 `_MLAB_RE` 那条正则再抄一份：抄一份只会在有人改动其中一处时一起错，
    两处各自成立才算数。
    """
    labs = [str(s) for s in fqs]
    bad = [s for s in labs if not re.fullmatch(r'FY\d{2}(?:Q[1-4])?', s)]
    if bad:
        raise SystemExit(f'{who}: 财季标签格式不对（前 3 个：{bad[:3]}）—— '
                         f'x 轴标签是页尾横轴分组那段注文的唯一判据，不能是自由文本')
    for s in labs:
        try:
            datetime.datetime.strptime(s, '%b-%y')
        except ValueError:
            continue
        raise SystemExit(f'{who}: 标签 {s!r} 能被当成月份解析 —— '
                         f'main() 末尾的 _cadence_of() 会拿它算横轴步长，'
                         f'而 Costco 的季末月份间隔是 2/3/4 个月、不唯一，那里会直接 SystemExit')
    return labs



# ─────────────────────────── ① 模块级：常量 + loader ───────────────────────────
# ⇄ 与 Exhibit 7 那一块共用（两块都贴时只留一份）：
#     SEC_CIK = '0000909832'
#     def fq_xlabels(fqs, who): ...
#     def load_seg_q(): ...
#
# 标题前缀单独一个，不复用 Exhibit 7 的那个：两张图同为 SEC 申报、同一个 CIK，但**表单
# 不同** —— 分部收入在 10-K / 10-Q 的分部附注里，客单/客流在 8-K 的 Exhibit 99.2 里。
# 拿「10-K/10-Q」的前缀去挂 8-K 的数，是页面上一句可证伪的假话。两个前缀共用「【SEC · 」
# 这个头，读者一眼看得出是同一族，具体表单各自点名（build/axp.py 同页并存三个前缀，
# SEC_A / SEC_T / SEC_O，就是这个用法）。
SEC_TKT = '【SEC · 8-K Ex.99.2 补充资料】'
TKT_Q = os.path.join(SERIES_DIR, 'cost_tkt_q.csv')


def load_tkt_q():
    """series/cost_tkt_q.csv —— 可比销售的客单 × 客流分解，**季度**，单位是百分比。

    这张表回答的是页面所有者问的那句「有没有把收入拆成客单和客流的口径」。
    诚实的答案是：**有，但只有季度的，没有月度的** —— 月度新闻稿一个字都不报
    （本页「口径与方法说明」里「客流与品类」那一条说的就是这件事），
    只有季末随 8-K 一起报送的 Exhibit 99.2「Supplemental Information」里有。

    列义：
      fq          'FY24Q3'…（与 cost_seg_q.csv 的财季标签同一套写法）
      basis       'reported' = 报告口径；'adjusted' = 剔除汽油与汇率的核心口径
                  ⚠️ adjusted 那张表是**后来才加的**：最早的几个季度整行**不存在**，
                     不是 0。缺的季度必须以「没有这一行」的方式缺席，不能补零。
      *_sales     该口径下的可比销售同比（%）
      *_tkt       平均客单价（average transaction / ticket）同比（%）
      *_trf       客流 / 购物频次（shopping frequency / traffic）同比（%）
                  前缀 us / ca / oi / tc = 美国 / 加拿大 / 其他国际 / 全公司
      mdna_tc_*   10-Q / 10-K 的 MD&A 正文里那两个**整数百分比**的全公司读数，
                  只在部分季度出现 —— 它是一条**独立的对账腿**（另一份申报、另一处披露），
                  不进图，只用来在图注里核对 8-K 那份 deck 有没有自相矛盾。

    恒等式：客单与客流是**相乘**的关系，不是相加 ——
        (1 + tkt/100) × (1 + trf/100) − 1 == sales/100
    下面 Exhibit 15 的块里逐格实测，并把实测到的最大偏差印在图注里。
    """
    d = pd.read_csv(TKT_Q, dtype={'fq': str, 'basis': str, 'accession': str})
    need = ['fq', 'filed', 'accession', 'basis',
            'us_sales', 'ca_sales', 'oi_sales', 'tc_sales',
            'us_tkt', 'ca_tkt', 'oi_tkt', 'tc_tkt',
            'us_trf', 'ca_trf', 'oi_trf', 'tc_trf', 'mdna_tc_tkt', 'mdna_tc_frq']
    miss = [c for c in need if c not in d.columns]
    if miss:
        raise SystemExit(f'series/cost_tkt_q.csv 缺列 {miss}')
    bad = sorted(set(d['basis']) - {'reported', 'adjusted'})
    if bad:
        raise SystemExit(f'series/cost_tkt_q.csv 出现未知 basis {bad} —— '
                         f'图注按两种口径分别措辞，多一种就有话没说到')
    return d


# ══════════════════════════════════════════════════════════════════════════
# §1  取证常量
# 落点：build/cost.py 顶部，紧跟现有 SRC / ECOMM_BREAK 那一组常量之后
# ══════════════════════════════════════════════════════════════════════════

#: SEC 申报人编号。四张 SEC 派生的 CSV（cost_seg_q / cost_tkt_q / cost_fy /
#: cost_cohort）都出自这一个 CIK，fetch/cost_sec.py 的申报清单也是按它拉的。
# SEC_CIK 已在上面 Exhibit 7 那一段定义（同一个申报人，全页只此一份）。

#: 引文出处：FY2025 10-K。**这不是「最新一篇」的别名** —— 下面那几句引文是从这一篇里
#: 逐字核出来的，换一篇就得重新核一遍，所以把 accession 钉死在引文旁边，而不是去现算
#: 「最新 10-K」。（同 build/axp.py 的 SAME_DAY_NOTE：把不能现算的事实写成一句**带
#: 出处与日期的历史陈述**，它不会随数据滚动而变假。）
FY25_10K_ACC = '0000909832-25-000101'
FY25_10K_LABEL = 'FY2025 10-K'

#: 10-K 把净销售额拆成的四个商品口径（Item 7 的 net sales by merchandise category）。
#: 只留**名字**不留金额：金额每年一变而 CSV 里没有这一列，写进正文就是一处必然过期的
#: 硬编码；条数由 len() 现取，将来公司改成三类或五类时这句会自己跟着变。
#: 前三类是公司自己说的 'Core Merchandise Categories'。
MERCH_CATS = ('Foods and Sundries', 'Non-Foods', 'Fresh Foods',
              'Warehouse Ancillary and Other Businesses')
MERCH_CORE_N = 3          # 前 3 类属于公司口径的 'Core Merchandise Categories'

#: FY2025 10-K 自己给的两个口径的体量（Item 1）：
#:   'Net sales for e-commerce represented approximately 7% of total net sales in 2025.'
#:   'Digitally-enabled sales, which represents sales delivered to members that are
#:    initiated through a digital device, whether fulfilled through a warehouse or
#:    distribution center, as well as Costco Travel, represented approximately 10%...'
#: 这两个数**不在任何 CSV 里**，所以按 axp 的办法写成带出处的历史陈述（见上）。
#: 它们是本页唯一能证明 FY26 改名**同时换了外延**（不只是换个词）的公司自证数据。
EC_SHARE_PCT, DE_SHARE_PCT = 7, 10


# ══════════════════════════════════════════════════════════════════════════
# §2  compose_glossary()
# 落点：build/cost.py 里与 compose_brief() 并列；payload 加一行
#         'glossary': compose_glossary(df, fy, tkt, seg_q, EXN),
#       位置在 'brief' 之后（CONTRACT §表：glossary 排在 brief 之下、Exhibit 1 之上）
# ══════════════════════════════════════════════════════════════════════════

#: 本页 glossary 要点名的 exhibit。**编号一个都不写死** —— 本轮四张 SEC 图插进来
#: 之后整页要重新编号，写死的图号会指到别的图上，而页面照渲、没有任何检查会响。
#: 调用方在装配完 ex 之后建这张表：slug → 该图实际的 e['n']，然后过 bind_exhibits()。
#:
#:   EXN = bind_exhibits(ex, {
#:       'noncomp': <Ex «Net Sales Growth: Comp vs Non-Comp Contribution»>,
#:       'wedge'  : <Ex «Gas & FX Wedge by Region»>,
#:       'ecomm'  : <Ex «E-commerce / Digitally-Enabled Comp»>,
#:       'tkt'    : <新增：季度 ticket / traffic 图>,
#:       'seg'    : <新增：分部总收入图（total revenue 口径）>,
#:   })
#:
#: 缺哪一个就传 None（或整个 key 不给）：引用那张图的**半句话**会自动不写，
#: 而不是印出「见 Exhibit None」。
GLOSSARY_SLUGS = ('noncomp', 'wedge', 'ecomm', 'tkt', 'seg')


def bind_exhibits(ex, want):
    """把 slug→图号 的绑定核一遍：号必须真的落在本页 payload 里。

    写死图号的毛病是「指错了也不报错」；而现算图号的毛病是「slug 拼错了静默变 None、
    整句话凭空消失」。这道护栏堵的是后者：给了号就必须对得上一张真图，对不上硬失败。
    没给（None / 缺 key）是**合法**的 —— 那张图这一轮可能压根没建。
    """
    have = {e['n'] for e in ex}
    out = {}
    for k in GLOSSARY_SLUGS:
        n = want.get(k)
        if n is None:
            out[k] = None
            continue
        if n not in have:
            raise SystemExit(
                f'glossary: slug {k!r} 绑到 Exhibit {n}，但本页 payload 里没有这张图'
                f'（现有 {sorted(have)}）—— 图号改了却没改绑定，正文会指向一张不存在的图。')
        out[k] = n
    return out


def compose_glossary(df, fy, tkt, seg_q, exn=None):
    """/cost/ 页最上方的「名词释义」（payload 的 `glossary` 字段）。

    与 brief 的分工（CONTRACT §表 / assets/page.js 的注释）：brief 说「**这个月**这组
    读数该怎么读」、每月重写；glossary 说「**这些词**是什么意思」、一年到头不动。
    所以这里**不写当月判断**，只写口径本身；出现的数只有两类：
      (a) 用来把定义钉住的**结构性**量（会员费占总收入多少、最新披露的 DE comp 是多少），
      (b) 恒等式的当期实例（非 comp = 净销售额 y/y − 报告 comp）。
    两类都当场从 CSV 算，一处硬编码都没有。

    参数
      df     series/cost.csv，PeriodIndex(M)，已含 nc_gap 列（= ns_yoy − tc_r）
      fy     series/cost_fy.csv（财年利润表；取最后一行做「最新财年」）
      tkt    series/cost_tkt_q.csv（季度 ticket/traffic）
      seg_q  series/cost_seg_q.csv（季度/财年分部收入；本函数只用它取季度周数）
      exn    bind_exhibits() 的返回值；None 表示一张都不点名

    版式（.glossary 的 CSS 只认这一种结构，见 assets/style.css：dl 是两列 grid，
    dt 在左、dd 在右）：<h4>名词释义</h4><dl><dt>词</dt><dd>释义</dd>…</dl>
    允许 <b>/<code>/<br>；**绝不能用 Markdown 的星号** —— page.js 走 innerHTML，
    星号会原样印出来，且 build/verify_pages.py 的 _md() 会对 glossary 单独报 WARN。

    dt 一律短：第一列宽度是 `max-content`（取最长的那个 dt），dt 一长就把释义挤成
    窄柱，窄到装不下时还会顶出横向滚动条（style.css 那条注释点名的 HSCROLL）。
    """
    exn = exn or {k: None for k in GLOSSARY_SLUGS}

    def ref(key, prefix='见 '):
        """点名一张图；没绑到就返回空串，让那半句话整个不写。"""
        n = exn.get(key)
        return '' if n is None else f'{prefix}Exhibit {n}'

    # ── 最新财年的三个口径（净销售额 / 会员费 / 总收入）──────────────────────
    # 三个数一个都不写死：cost_fy.csv 每年多一行，写死的 FY2025 明年就是旧闻。
    f = fy.iloc[-1]
    ns_bn, mf_bn, tr_bn = (float(f['net_sales_mn']) / 1000,
                           float(f['memb_fee_mn']) / 1000,
                           float(f['total_rev_mn']) / 1000)
    fy_lab = str(f['fy'])
    # 会员费占总收入的比重：这是「两个口径差多远」的唯一诚实答案（差的**就是**会员费）。
    mf_share = 100 * mf_bn / tr_bn if tr_bn else float('nan')
    # 恒等式当场自证，不只是宣称：三个数印在一起，读者可以直接相加核对。
    ident = f'{ns_bn:,.3f} + {mf_bn:,.3f} = {tr_bn:,.3f}'

    # ── 当月的非 comp 残差（恒等式的当期实例）────────────────────────────────
    last = df.index[-1]
    v_ns, v_tc = df['ns_yoy'].iloc[-1], df['tc_r'].iloc[-1]
    mlab = last.strftime('%b-%y')
    if np.isfinite(v_ns) and np.isfinite(v_tc):
        nc_now = (f'{mlab} 的实例：{v_ns:+.1f}% − {v_tc:+.1f}% = '
                  f'<b>{v_ns - v_tc:+.1f}pp</b>。')
    else:
        # 缺值月让这半句不写，而不是让整页构建失败（同 compose_brief 的 B.need 规矩）。
        nc_now = ''

    # ── 最新披露的 Digitally-Enabled comp ───────────────────────────────────
    _de = df['ec_r'].dropna()
    de_now = (f'最新一期（{_de.index[-1].strftime("%b-%y")}）报告口径 '
              f'<b>{float(_de.iloc[-1]):+.1f}%</b>。' if len(_de) else '')

    # ── 最新一季的 ticket / traffic ─────────────────────────────────────────
    # 公司按 reported / adjusted 两套基准各报一套，取最新一季的 reported 那行；
    # 没有 reported 就退到该季任意一行，两者都没有就整句不写。
    tk_now = ''
    if tkt is not None and len(tkt):
        _q = str(tkt['fq'].iloc[-1])
        _rows = tkt[tkt['fq'] == _q]
        _r = _rows[_rows['basis'] == 'reported']
        _r = _r.iloc[-1] if len(_r) else _rows.iloc[-1]
        if pd.notna(_r.get('tc_tkt')) and pd.notna(_r.get('tc_trf')):
            tk_now = (f'最新一季（{_q}，{_r["basis"]} 基准）全公司客单 '
                      f'<b>{float(_r["tc_tkt"]):+.1f}%</b>、客流 '
                      f'<b>{float(_r["tc_trf"]):+.1f}%</b>。')

    # ── 季度轴的周数：**现算**，不写「12/12/12/16」──────────────────────────
    # 那个写法只对 52 周财年成立；53 周财年的 Q4 是 17 周（实测 FY12Q4/FY17Q4/FY23Q4）。
    q_wk = _quarter_weeks(seg_q)

    G = []                      # (dt, dd) —— 顺序即页面上的顺序

    # 1) comp 本体：定义 + 可比周 + 出处。这三件缺一件都会让下面几条失去锚点。
    G.append(('comp（可比销售）',
              f'公司自己的定义（{FY25_10K_LABEL}）：<b>开业满一年以上</b>的仓库的净销售额，'
              f'含改建（remodel）、迁址（relocation）与扩建（expansion），'
              f'再加上运营满一年以上的电商站点的销售额。'
              f'注意是「满一年以上」——<b>不是</b>本页末尾那张核对表的 13 个月，'
              f'那个 13 只是核对表的行数，与 comp 的门槛无关。'))

    # 2) 可比零售周：单独立条，因为它是「comp ≠ 本月÷去年同月」的唯一原因，
    #    而本页另有一整条 note 在数据上实测这件事 —— 释义里只说「同比」会当场与它打架。
    G.append(('可比零售周',
              f'comp 报的是<b>可比零售周</b>口径（{FY25_10K_LABEL} 的表注原文：'
              f'comparable sales were calculated using comparable retail weeks），'
              f'基期是<b>周数相同</b>的上年错位窗口，不是日历上的「去年同月」。'
              f'所以 comp <b>不等于</b>拿两个月的绝对额相除 —— 差多少、哪几个月甚至反号，'
              f'页尾「53 周财年」与「同比口径」两条里有本页数据上的实测。'))

    # 3) 报告口径
    G.append(('报告口径 comp',
              '公司公布的<b>未作任何调整</b>的 comp（reported），汽油价格变动与汇率折算'
              '都还在里面。本页凡是标「报告口径」的线与行都是它。'))

    # 4) 核心 comp —— 三件事：是本页的简称、调掉的是什么、以及与公司自己的 "core" 撞名
    G.append(('核心 comp',
              f'<b>本页的简称</b>（承自原始 PDF），公司<b>不用</b> "core comp" 这个说法；'
              f'公司的原话是「剔除汇率与汽油<b>价格</b>变动影响的可比销售」。'
              f'它调掉的只有汽油<b>价格</b>的变动与汇率折算 ——'
              f'<b>不</b>调汽油销量，也<b>不</b>剔除任何商品品类。'
              f'⚠️ 别与公司口径里的 "Core Merchandise Categories" 混为一谈：'
              f'那是 10-K 把净销售额拆成的 {len(MERCH_CATS)} 类商品中的前 {MERCH_CORE_N} 类'
              f'（{"、".join(MERCH_CATS[:MERCH_CORE_N])}），是<b>品类</b>划分，'
              f'与这里的「核心」是两回事。'
              + (f'两个口径之差按地区拆开即 {ref("wedge", "")}。' if ref('wedge') else '')))

    # 5) 非 comp —— 必须说清它不是公司数
    G.append(('非 comp',
              f'<b>不是公司披露的数</b>，是本页轧出来的残差：'
              f'<code>非 comp 贡献 = 净销售额 y/y − 报告口径 comp</code>。'
              f'里面装着新开与关闭的仓库，以及两个口径分母不同所留下的残差。'
              f'公司表达同一件事时用的是文字而非数字（{FY25_10K_LABEL}：'
              f'净销售额余下的增长来自本财年净新开的那些仓库）。'
              + nc_now
              + (f'{ref("noncomp")}（柱线之间的间距就是它）。' if ref('noncomp') else '')))

    # 6) 三个收入口径 —— 这条是本轮新增 SEC 图的前提，两个口径混轴就是这里没说清
    G.append(('净销售额与总收入',
              f'<b>净销售额</b>（net sales）<b>不含</b>会员费；'
              f'<b>总收入</b>（total revenue）= 净销售额 + 会员费。'
              f'{fy_lab}（$bn）：{ident}，会员费占总收入 {mf_share:.2f}%。'
              f'这条不是背景知识而是<b>读图前提</b>：本页月度各图用的是净销售额口径，'
              f'而 SEC 分部图用的是<b>总收入</b>口径'
              + (f'（{ref("seg", "")}）' if ref('seg') else '')
              + '，两者<b>不能放在同一根轴上</b>比较（详见页尾口径警告那一条）。'))

    # 7) Digitally-Enabled —— 改名同时换了外延，这才是断点的实质
    G.append(('Digitally-Enabled',
              f'FY26 起公司把原来的 e-commerce comp 一行改名为 Digitally-Enabled '
              f'comparable sales，<b>且不重述历史</b>，所以断点两侧不保证可比。'
              f'改的不只是名字：{FY25_10K_LABEL} 里 e-commerce 约占净销售额 '
              f'{EC_SHARE_PCT}%，而 digitally-enabled（凡由数字设备发起的销售，'
              f'不论最终由仓库还是配送中心履约，另含 Costco Travel）约占 '
              f'{DE_SHARE_PCT}% —— 外延更宽。'
              + de_now
              + (f'{ref("ecomm")}（断点画在图上）。' if ref('ecomm') else '')))

    # 8) ticket / traffic —— 公司自己的措辞是 shopping frequency
    G.append(('客单 / 客流',
              f'comp 的两个<b>相乘</b>的驱动项：<b>客单</b>（average ticket，每次消费金额）'
              f'与<b>客流</b>（公司用词是 shopping frequency 购物频次）。'
              f'公司原话（{FY25_10K_LABEL}）：comp 的增长来自会员购物频次的提高'
              f'与每次到店消费金额的增加。'
              f'两者<b>不在月度新闻稿里</b>，只按<b>季</b>披露'
              + (f'，{ref("tkt", "")} 画的就是这条季度序列' if ref('tkt') else '')
              + '。' + tk_now))

    # 9) 两条时间轴 —— 放在最后，因为它要用到上面所有词
    G.append(('零售月 / 财季',
              f'本页有<b>两条互不相同</b>的时间轴。月度腿是 4-4-5 零售日历的<b>零售月</b>'
              f'（每月 4 或 5 周，周日截止）；SEC 腿是<b>财季</b>（{q_wk}）。'
              f'两者<b>不是嵌套关系</b>：财季的边界切在零售月<b>中间</b>，'
              f'所以任何一张图都只能用其中一条轴，两条轴上的数不能逐格对照。'))

    dl = ''.join(f'<dt>{d}</dt><dd>{t}</dd>' for d, t in G)
    return '<h4>名词释义</h4><dl>' + dl + '</dl>'


def _quarter_weeks(seg_q):
    """财季的周数说明 —— **现算**，因为它不是一个常数。

    任务书与直觉都说「12/12/12/16」，实测不成立：53 周财年的第四季是 <b>17</b> 周
    （series/cost_seg_q.csv 里 FY12Q4 / FY17Q4 / FY23Q4 都是 17）。把 16 写死之后，
    每逢 53 周财年这句就是假的 —— 而本页恰好另有一整条 note 专讲 53 周财年，
    同一页两句话会当场打架。所以周数按季位现读 CSV，异常季逐个点名。
    """
    if seg_q is None or not len(seg_q):
        return '每季周数见申报'
    q = seg_q[seg_q['scope'] == 'Q'].copy()
    if not len(q):
        return '每季周数见申报'
    q['pos'] = q['fq'].astype(str).str[-1]
    parts, odd = [], []
    for pos in sorted(set(q['pos'])):
        w = sorted({int(x) for x in q.loc[q['pos'] == pos, 'weeks'].dropna()})
        if len(w) == 1:
            parts.append(f'Q{pos} {w[0]} 周')
        else:
            # 多于一种周数的季位：报众数，把少数派逐个点名（那才是 53 周财年）。
            base = max(w, key=lambda v: int((q.loc[q['pos'] == pos, 'weeks'] == v).sum()))
            parts.append(f'Q{pos} {base} 周')
            for v in w:
                if v == base:
                    continue
                yrs = [str(x) for x in q.loc[(q['pos'] == pos) & (q['weeks'] == v), 'fq']]
                odd.append(f'{"／".join(yrs)} 为 {v} 周')
    s = '、'.join(parts)
    return s + (f'；例外：{"；".join(odd)}（53 周财年）' if odd else '')


# ══════════════════════════════════════════════════════════════════════════
# §3  SRC —— 落点：build/cost.py 第 79 行，整行替换
#     现文（单源，已成假话）：
#       SRC = 'Source: Company data (Costco monthly sales press releases)'
#     样板：build/axp.py 的 payload['source']（两源并列 + 各自的 CIK/表单）
# ══════════════════════════════════════════════════════════════════════════
SRC = ('Source: Costco monthly sales press releases (investor.costco.com) and '
       f'SEC filings (CIK {SEC_CIK}: Form 10-K / 10-Q / 8-K EX-99.2)')


# ══════════════════════════════════════════════════════════════════════════
# §4  NOTES[0] —— 数据源
# 落点：build/cost.py 第 1152-1155 行那条（以 '<b>数据源（唯一）</b>' 开头）整条替换
#
# 改法照 build/mrbase.py 第 2865-2868 行写死的规矩：
#   「收窄主语，别在别处补一句『不过某几张除外』。」
# 所以这里不是把「唯一」删掉了事，而是把主语从「本页」收窄成「月度腿喂的那几张」，
# 并把两组图号**现读 payload 列出来**（本轮编号在动，写死必错）。
# ══════════════════════════════════════════════════════════════════════════

def note_datasource(df, ex, sec_ex, table_n=None):
    """NOTES[0]：两条腿各自喂哪几张图，逐张点名。

    参数
      df      series/cost.csv
      ex      已装配好的 exhibits 列表（现读，不写死图号）
      sec_ex  由 SEC 腿喂的 exhibit 编号集合（调用方在建那几张图时登记）
      table_n 末尾核对表的编号（payload['table']['n']）；它不在 ex 里，单独给
    """
    sec = sorted(set(sec_ex))
    have = {e['n'] for e in ex}
    bad = [n for n in sec if n not in have]
    if bad:
        # 登记了却没建（或建完改了号）：那几张图会在正文里被算进 SEC 腿，
        # 而月度腿的名单同时少了它们 —— 两句话一起错，页面照渲。硬失败。
        raise SystemExit(f'note_datasource: sec_ex 里的 Exhibit {bad} 不在本页 payload 里'
                         f'（现有 {sorted(have)}）')
    mon = [n for n in sorted(have) if n not in set(sec)]
    # 「Exhibit」只写一次：13 张图各带一个前缀会把这条 note 撑成一堵字墙。
    j = lambda ns: 'Exhibit ' + ' / '.join(str(n) for n in ns)
    return (
        '<b>数据源（两条腿）</b>：'
        # ── 腿 1：月度新闻稿。主语收窄到它真正喂的那几张 ──
        f'<b>月度腿</b> = Costco 每零售月结束后首个周三盘后在官网 IR'
        f'（investor.costco.com）发布的月度销售新闻稿，本页解析 '
        f'{df.index[0].strftime("%b-%y")} 以来全部新闻稿（{len(df)} 个零售月，至 '
        f'{df.index[-1].strftime("%b-%y")}）；它喂的是 Exhibit 1 汇总表、'
        + (j(mon) if mon else '（本轮没有一张图走月度腿）')
        + (f' 与末尾的 {table_n} 号核对表' if table_n is not None else '')
        + '。'
        # ── 腿 2：SEC。表单 + CIK + 节奏，节奏是「为什么它只能按季」的理由 ──
        + (f'<b>SEC 腿</b> = 公司向 SEC 报送的申报（CIK {SEC_CIK}）：'
           f'年报 10-K、季报 10-Q，以及业绩稿 8-K 所附的 EX-99.2'
           f'「Supplemental Information」补充资料。'
           f'节奏是<b>按季</b>而非按月 —— 10-Q 在季末约 3-4 周后、10-K 在财年结束后约 '
           f'5-6 周，8-K 补充资料比同季 10-Q 还早约一周。它喂的是 {j(sec)}。'
           if sec else
           # 一张 SEC 图都没建的那一轮：不能留着「本页有 SEC 腿」这半句空转。
           f'<b>SEC 腿</b>本轮没有喂出任何一张图 —— 页面暂时只有月度腿。')
        # 只剩一条腿时，「两条腿…」「见下一条」都是假话：那条口径警告也不会印出来。
        + ('两条腿都是公司自己的一手披露，'
           '<b>不使用任何第三方（券商）研报数据或观点</b>。'
           '两者口径与时间轴都不同，不能混读 —— 见下一条。' if sec else
           '本页只采用公司自己的一手披露，'
           '<b>不使用任何第三方（券商）研报数据或观点</b>。'))


# ══════════════════════════════════════════════════════════════════════════
# §5  新增 NOTES 条目 —— 两条腿的口径警告
# 落点：NOTES 里紧跟 note_datasource() 那条之后
# 形制照 build/axp.py 的「Lending Trust 是另一个池子」那条：
#   先一句加粗的断言，再说差在哪、差多少（现算），最后说因此不能怎么做。
# ══════════════════════════════════════════════════════════════════════════

def note_two_source(df, fy, seg_q, rev_ex=()):
    """两条腿为什么不能放在一根轴上 —— 口径差与轴差分开说，各自给现算的证据。

    ⚠️ 这条**不写**「两条腿对不上」。口径差是可精确解释的：差的**恰好**是会员费，
    金额由 CSV 现算得出。裸写「对不上」既不准确，也放弃了本页唯一能自证的那个数。
    真正不能调和的是**时间轴**，所以下面第二段用实测的周数说话。

    ⚠️ `rev_ex` 是**真的画总收入**的那几张，不是「所有 SEC 图」。两者不是一回事：
    SEC 腿里还有画客单/客流百分比的图，那上面一个金额都没有。把 sec_ex 整份传进来
    会印出「SEC 腿画的是总收入（… 客单客流那张 …）」这种当场可证伪的话。
    """
    f = fy.iloc[-1]
    ns_bn, mf_bn, tr_bn = (float(f['net_sales_mn']) / 1000,
                           float(f['memb_fee_mn']) / 1000,
                           float(f['total_rev_mn']) / 1000)
    fy_lab, fy_wk = str(f['fy']), int(f['weeks'])
    mf_share = 100 * mf_bn / tr_bn if tr_bn else float('nan')

    # ── 轴差的硬证据：拿最新一季与「带同样标签的那几个零售月」比周数 ──────────
    # 这不是修辞。实测（本轮数据）最新季 12 周，而同标签的零售月合计 17 周 ——
    # 财季边界切在零售月中间，两条轴根本不是同一套切法。数字全部现算。
    axis_evid = ''
    q = seg_q[seg_q['scope'] == 'Q'] if seg_q is not None and len(seg_q) else None
    if q is not None and len(q):
        r = q.iloc[-1]
        ps, pe = pd.Period(r['period_start'], 'M'), pd.Period(r['period_end'], 'M')
        seg = df.loc[ps:pe, 'weeks'].dropna()
        if len(seg):
            axis_evid = (
                f'实证（{r["fq"]}）：该财季自身是 <b>{int(r["weeks"])} 周</b>，'
                f'而本页月度腿里落在同一段日历上的 {len(seg)} 个零售月'
                f'（{ps.strftime("%b-%y")}–{pe.strftime("%b-%y")}）合计 '
                f'<b>{seg.sum():.0f} 周</b> —— 两个数不相等，正说明<b>财季的边界切在'
                f'零售月中间</b>，零售月并不嵌套进财季。')

    # ── 为什么连「把月度腿加总成季」这条退路也没有 ────────────────────────────
    # series/cost.csv 只有月份标签与周数，没有起止日期，所以无法把它重切到财季轴上。
    # ⚠️ 不报列数：调用方传进来的 df 这时已经挂了 nc_gap 等派生列，列数不等于「源列数」。
    # 改成**现查有没有日期列**——这才是这句话真正依赖的那个条件。
    _dcols = [c for c in df.columns
              if any(k in str(c).lower() for k in ('date', 'start', 'end'))]
    no_dates = ('<code>series/cost.csv</code> 逐行只有一个<b>月份标签</b>与一个<b>周数</b>，'
                '<b>没有起止日期列</b>，所以月度腿也无法在本仓内被重新切到财季轴上 —— '
                '这不是懒得做，是做不到。'
                if not _dcols else
                # 哪天真加了日期列，这句话就该重写，而不是继续印一句已经不成立的话。
                f'（<code>series/cost.csv</code> 现已有日期列 {"、".join(_dcols)}，'
                f'「无法重切到财季轴」这句已不再成立，请重写本条。）')

    j = 'Exhibit ' + ' / '.join(str(n) for n in sorted(set(rev_ex)))
    return (
        '<b>⚠️ 两条腿的口径与时间轴都不同，不能放在同一根轴上，也不能逐格对照。</b>'
        # 口径差：差的就是会员费，给金额与占比
        f'<b>口径</b>：月度腿画的是<b>净销售额</b>（不含会员费）；SEC 腿画的是'
        f'<b>总收入</b>（含会员费）'
        # 判据用 rev_ex 本身，不用拼好的字符串：j 恒以 'Exhibit ' 开头，永远为真。
        + (f'（{j}）。' if rev_ex else '。')
        + f'{fy_lab}（$bn）：净销售额 {ns_bn:,.3f} + 会员费 {mf_bn:,.3f} = 总收入 '
          f'{tr_bn:,.3f}，会员费占总收入 <b>{mf_share:.2f}%</b>。'
          f'两者之差<b>不是误差</b>，就是这笔会员费 —— 所以把两条腿画进一张图，'
          f'读者看到的那个缺口会被当成经营变化。'
        # 轴差：现算的周数证据
        + f'<b>时间轴</b>：月度腿是 4-4-5 零售日历的零售月（每月 4 或 5 周）；'
          f'SEC 腿是财季（{_quarter_weeks(seg_q)}），最新财年 {fy_lab} 共 {fy_wk} 周。'
        + axis_evid
        + no_dates
        + '因此本页的做法是：两条腿各画各的图，<b>不合并、不换算、不互相校验</b>，'
          '每张图的口径写在它自己的图注里。')


# ══════════════════════════════════════════════════════════════════════════
# §6  NOTES 里「客流与品类」那条 —— 落点：build/cost.py 第 1167-1168 行整条替换
#
# 现文（两处事实都错，且「仅」是错的）：
#   '<b>客流与品类</b>：traffic（客流）/ ticket（客单）与品类细分不在月度新闻稿内'
#   '（仅公司预录电话留言口头披露），本页只采用官网新闻稿数据，故不含该细分。'
#
# 错在哪（逐条核过）：
#  (1) 「电话留言」——月度新闻稿原文说的是 a pre-recorded message，访问方式是
#      investor.costco.com 的 "Events & Presentations"，是 IR 网站上的**预录音频**，
#      挂网约一周后下线；全文 "telephone" 出现 **0** 次。拨入电话的形式 2024 年就取消了。
#  (2) 「仅…口头披露」——ticket/traffic 是**有书面披露**的，只是按季不按月：
#      (a) 10-Q/10-K 的 MD&A 用文字量化全公司口径；
#      (b) 自 FY24Q3 起，每季 8-K 的 EX-99.2「Supplemental Information」给出
#          **分部**的 comp/ticket/traffic，且 reported 与 adjusted 两套都有。
#  (3) 「品类细分」没有 —— 10-K 按商品品类把净销售额拆成四类（金额到 $mn）。
#
# ⚠️ 取证留在注释里，**不上页面**（页面要的是结论，不是我的检索日志）：
#     EDGAR 全文检索（Costco 全部申报）："average ticket" 共 46 命中，
#     全部落在 10-Q(33) / 10-K(12) / ARS(1)，8-K 命中 **0**；
#     "shopping frequency" 共 91 命中，同样 8-K 命中 0。
#     —— 即：这两个词的**正文**只出现在定期报告里；8-K 那一路是靠 EX-99.2
#     附件的**表格**给数，表头不含这两个词组，所以全文检索抓不到它。
#     两件事都成立，写页面时不要把其中一件说成另一件的反证。
# ══════════════════════════════════════════════════════════════════════════

def note_ticket_traffic(tkt, ex_tkt=None):
    """重写后的第 8 条。核心改动：把原因从「拿不到」改成「频率不同」。

    参数
      tkt     series/cost_tkt_q.csv
      ex_tkt  季度 ticket/traffic 那张图的编号；None 则不点名
    """
    # 覆盖范围全部现算：季数、首末季、首末申报日、两套基准各有几季。
    span = ''
    if tkt is not None and len(tkt):
        qs = list(dict.fromkeys(str(x) for x in tkt['fq']))
        nb = {b: int((tkt['basis'] == b).sum()) for b in sorted(set(tkt['basis']))}
        basis_txt = '、'.join(f'{b} {n} 季' for b, n in nb.items())
        span = (f'本页已收 {len(qs)} 个季度（{qs[0]} → {qs[-1]}，申报日 '
                f'{tkt["filed"].iloc[0]} → {tkt["filed"].iloc[-1]}；{basis_txt}）。')
    where = ('，' + (f'Exhibit {ex_tkt} ' if ex_tkt is not None else '本页新增的季度图')
             + '画的就是它')
    return (
        '<b>客单、客流与品类</b>：这三项<b>不是拿不到，是频率对不上</b> —— '
        '公司按<b>季</b>书面披露，而本页月度各图的横轴是<b>零售月</b>，'
        '所以月度图里没有它们，不是因为公司没说。'
        # 书面披露的两个出处，分别说清各自的粒度
        '客单（average ticket）与客流（公司用词 shopping frequency）的书面出处有两处：'
        '一是 10-Q / 10-K 的 MD&A，用文字量化<b>全公司</b>口径；'
        '二是自 FY24Q3 起每季 8-K 所附的 EX-99.2「Supplemental Information」，'
        '给出<b>分部</b>的 comp / 客单 / 客流，且 reported 与 adjusted 两套基准都有。'
        + span + f'本页因此把季度读数单列一张图{where}，与月度各图<b>不共轴</b>。'
        # 品类：说清有什么，别再说「没有」
        f'<b>品类</b>同理：10-K 按商品品类把净销售额拆成 {len(MERCH_CATS)} 类'
        f'（{"、".join(MERCH_CATS)}，金额到 $mn），前 {MERCH_CORE_N} 类是公司口径的 '
        f'"Core Merchandise Categories"；它同样是<b>年度</b>披露，进不了月度轴。'
        # 预录消息：把原文说对，并说明它为什么不能当数据源
        '至于月度新闻稿末尾提到的那条<b>预录消息</b>（pre-recorded message）：'
        '它挂在 investor.costco.com 的 "Events & Presentations" 下，是 IR 网站上的'
        '<b>预录音频</b>、约一周后下线，<b>不是电话留言</b>（新闻稿全文没有 telephone 一词，'
        '拨入电话的形式已于 2024 年取消）。'
        '本页不采用它 —— 音频既会下线、也无法逐条核对，'
        '与本页「每个数都能回到一份可长期引用的申报」的要求不符。')


# ══════════════════════════════════════════════════════════════════════════
# §7  subtitle / footer
# 落点：build/cost.py 第 1202-1204 行（subtitle）与第 1220-1223 行（footer）
# ══════════════════════════════════════════════════════════════════════════

def subtitle_for(df, fy, seg_q, LATEST, iv):
    """payload['subtitle']：两条腿各报各的覆盖区间。

    现文（一源一段，已成假话）：
      f'零售月 {…} ({…}周) | 数据: Costco 官网月度销售新闻稿 ({df.index[0]} 至今 {len(df)} 个月) | 版式仿 Goldman Sachs GIR'
    照 build/axp.py 的 subtitle：两个来源并列，**各自的起止各算各的**。
    """
    q = seg_q[seg_q['scope'] == 'Q'] if seg_q is not None and len(seg_q) else None
    sec_span = ''
    if q is not None and len(q):
        sec_span = f'季度 {q["fq"].iloc[0]}–{q["fq"].iloc[-1]}'
    if fy is not None and len(fy):
        sec_span += ('；' if sec_span else '') + f'财年 {fy["fy"].iloc[0]}–{fy["fy"].iloc[-1]}'
    return (f'零售月 {LATEST.strftime("%b %Y")} ({iv(df["weeks"].iloc[-1])}周) | '
            f'数据源两条：月度销售新闻稿（{df.index[0]} 至今 {len(df)} 个月）'
            f' + SEC 申报 CIK {SEC_CIK}（{sec_span}） | '
            f'版式仿 Goldman Sachs GIR')


def footer_for(ex):
    """payload['footer']：两处都得改。

    现文：
      '数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
      '数值以 Costco 官网原始披露为准 · '
      '每张图右上角可切换「表格」视图逐条核对 · '
      '仅供个人研究，不构成投资建议'

    (1)「以 Costco 官网原始披露为准」——只盖住了月度腿。SEC 申报不在官网新闻稿里，
        这半句把新增那几张图排除在「以原始披露为准」之外了。改成同时点名两处。
    (2)「每张图右上角可切换『表格』视图」——对 kind:'table' 的 exhibit 是**假话**：
        那种 exhibit 在 assets/page.js 里被 `if (ex.kind === 'table')` 就地截住、
        自己渲成 HTML 表，**根本不进引擎**，而「表格」按钮是引擎 card() 里
        `<button class="toggle">表格</button>` 渲的 —— 它压根没有那个按钮。
        它本身就已经是一张表，也不需要。所以把「每张图」收窄成「每张**图**」，
        并把本页真正是表的那几张现读点名。
    """
    tbl = sorted(e['n'] for e in ex if e.get('kind') == 'table')
    toggle = (
        '每张图右上角可切换「表格」视图逐条核对'
        + (f'（Exhibit {" / ".join(str(n) for n in tbl)} 本身就是 HTML 表，'
           f'已是逐条明细，没有也不需要这个切换按钮）' if tbl else ''))
    return ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
            f'数值以 Costco 官网月度新闻稿与 SEC 申报（CIK {SEC_CIK}）的原始披露为准 · '
            + toggle + ' · 仅供个人研究，不构成投资建议')


# ══════════════════════════════════════════════════════════════════════════
# §8  两处分桶助手的修正
# 落点：build/cost.py 第 1023-1028 行（_is_pct_axis / _LVL_ONLY_EX）
#       与第 1104-1109 行（_STEP / _month_ex / _nonmonth）
# ══════════════════════════════════════════════════════════════════════════

#: 本仓「纵轴百分比 = 占比而非同比」的图型。目前只有 stacked_dual（docs/CHART_KINDS.md
#: §3.14：堆叠柱，右轴写死成百分号）。加新图型时必须同时加进来 —— 下面 partition_axes()
#: 的双向核对会在漏加时硬失败，不会静默把一张占比图算进同比桶。
SHARE_KINDS = frozenset({'stacked_dual'})


def _is_pct_axis(e):
    """这张图的纵轴画的是不是百分比/百分点。

    ⚠️ 修正（原实现只看 yfmt / bar.yfmt / line.yfmt）：
    `stacked_dual` 的占比图可以只声明 <b>fmt</b> 而**不给 yfmt**
    （data/ase.js 的 Revenue mix 就是 `{"kind":"stacked_dual","fmt":"pct1"}`，
    全图没有一个 yfmt）。原判据会把它判成「水平值图」，于是 WEEK_CAL_NOTE 里
    「本页画水平值、纵轴不是百分比的是 Exhibit …」当场点了一张百分比图的名。
    docs/CHART_KINDS.md 的格式器表里 fmt / yfmt / label_fmt / line.yfmt / yoy.yfmt
    共用同一张名表，所以 fmt 本来就与 yfmt 同源，判据必须一并看。
    `label_fmt` 故意不看：它管的是数据标签，不是轴。
    """
    fs = [e.get('yfmt'), e.get('fmt'),
          (e.get('bar') or {}).get('yfmt'), (e.get('line') or {}).get('yfmt'),
          (e.get('yoy') or {}).get('yfmt')]
    return any(str(f).startswith(('pct', 'pp')) for f in fs if f)


def partition_axes(ex, share_ex=()):
    """把 exhibits 分成**三**桶（原来只有两桶，占比图无处可放）。

    ⚠️ 为什么必须有第三桶：WEEK_CAL_NOTE 原来的二分是「同比图 / 水平值图」，
    而一张 100% 结构图上的百分比<b>两者都不是</b> —— 它既不是公司披露的同比，
    也不是披露同比之间的加减，而是同期各分部占合计的比重。把它归进同比桶，
    那条 note 里「图上的同比只有两种来源」就是假的；归进水平值桶，
    「纵轴不是百分比」也是假的。所以给它一个自己的名分。

    返回 (yoy_ex, share_ex, lvl_ex, table_ex)，四个都是排好序的编号列表。

    `share_ex` 由调用方在建那几张图时登记（占比 vs 同比是**语义**，payload 里
    没有字段能直接判）。但登记不是无凭无据的宣称 —— 下面做**双向**核对：
      · 登记了的必须真有百分比轴（否则是登记错了）；
      · 凡 kind 属 SHARE_KINDS 且是百分比轴的，必须已登记（否则是漏登记）。
    漏一个方向都会让那条 note 悄悄说假话，所以两个方向都硬失败。
    """
    share = set(share_ex)
    # kind:'table' 先摘出去：它没有纵轴，谈不上「画的是不是百分比」。
    tbl = [e for e in ex if e.get('kind') == 'table']
    rest = [e for e in ex if e.get('kind') != 'table']

    have = {e['n'] for e in rest}
    bad = sorted(share - have)
    if bad:
        raise SystemExit(f'partition_axes: share_ex 登记的 Exhibit {bad} 不是本页的作图 '
                         f'exhibit（现有 {sorted(have)}；kind:"table" 不参与分桶）')
    for e in rest:
        if e['n'] in share and not _is_pct_axis(e):
            raise SystemExit(
                f'partition_axes: Exhibit {e["n"]} 登记成占比图，纵轴却不是百分比 —— '
                f'要么登记错了，要么这张图的格式器该给 pct。')
        if e['n'] not in share and e.get('kind') in SHARE_KINDS and _is_pct_axis(e):
            raise SystemExit(
                f'partition_axes: Exhibit {e["n"]} 是 {e.get("kind")} 的百分比图却没登记进 '
                f'share_ex —— 它会被算进「同比」桶，而页尾那条口径说明会因此说假话。')

    yoy = sorted(e['n'] for e in rest if _is_pct_axis(e) and e['n'] not in share)
    shr = sorted(e['n'] for e in rest if _is_pct_axis(e) and e['n'] in share)
    lvl = sorted(e['n'] for e in rest if not _is_pct_axis(e))
    tb = sorted(e['n'] for e in tbl)
    if len(yoy) + len(shr) + len(lvl) + len(tb) != len(ex):
        raise SystemExit('partition_axes: 分桶没有覆盖本页每一张 exhibit。')
    return yoy, shr, lvl, tb


def week_cal_tail(lvl_ex, share_ex, table_ex):
    """WEEK_CAL_NOTE 里那半句的替换文本。

    落点：build/cost.py 第 1044-1045 行，即
        f'本页画水平值、纵轴不是百分比的是 Exhibit {"／".join(_LVL_ONLY_EX)}'
        '（现读 payload 的纵轴格式器，不写死图号）。'
    整段替换成 week_cal_tail(*partition_axes(ex, share_ex)[2:] …) 的返回值。
    调用示例：
        _yoy, _shr, _lvl, _tbl = partition_axes(ex, SHARE_EX)
        …  + week_cal_tail(_lvl, _shr, _tbl) + …
    """
    j = lambda ns: '／'.join(str(n) for n in ns)
    out = (f'本页画水平值、纵轴不是百分比的是 Exhibit {j(lvl_ex)}'
           if lvl_ex else '本页没有一张画水平值的图')
    out += '（现读 payload 的纵轴格式器，不写死图号）。'
    if share_ex:
        # 第三类：明确划出去，并说清它为什么不归本条管。
        out += (f'另有 Exhibit {j(share_ex)} 画的是<b>占比</b>（各分部占合计的比重，'
                f'纵轴虽然也是百分比）：那上面的百分比<b>既不是</b>披露的同比、'
                f'<b>也不是</b>披露同比之间的加减，而是同一期内部的结构，'
                f'不在本条「同比口径」的管辖范围内。')
    if table_ex:
        # kind:'table' 根本没有纵轴，前面那两句话对它都不成立。
        out += (f'Exhibit {j(table_ex)} 是 HTML 表（<code>kind:"table"</code>）、'
                f'没有纵轴，上面三句都不针对它。')
    return out


def partition_cadence(ex, cadence_of):
    """横轴步长分桶 —— **排除 kind:'table'**。

    ⚠️ 修正：原实现 `_STEP = {e['n']: _cadence_of(e) for e in ex}` 把表也算了进去。
    表没有 xlabels，_cadence_of 返回 None，于是它落进 `_nonmonth`，
    WINDOW_NOTE 末尾就会印出「本页另有 N 张的横轴不是逐月月份轴：Exhibit 17」——
    而 Exhibit 17 是一张 HTML 表，它根本没有横轴。读者会去找一根不存在的轴。

    返回 (month_ex, nonmonth, table_ex)：
      month_ex  [(n, xlabels[0], 格数)]，横轴逐月推进的
      nonmonth  非逐月（季/年桶等）**作图** exhibit 的编号
      table_ex  kind:'table' 的编号（不参与横轴叙述，单独交代）
    覆盖断言同样只对**作图** exhibit 成立。
    """
    tbl = sorted(e['n'] for e in ex if e.get('kind') == 'table')
    rest = [e for e in ex if e.get('kind') != 'table']
    step = {e['n']: cadence_of(e) for e in rest}
    month = [(e['n'], e['xlabels'][0], len(e['xlabels'])) for e in rest
             if step.get(e['n']) == 1]
    non = [e['n'] for e in rest if step.get(e['n']) != 1]
    if len(month) + len(non) != len(rest):
        raise SystemExit('横轴分组没有覆盖本页每一张图 —— 页尾那段会漏掉几张不说。')
    return month, non, tbl


def window_note_tail(nonmonth, table_ex):
    """WINDOW_NOTE 末尾那个括注的替换文本。

    落点：build/cost.py 第 1144-1147 行，即
        (f'（这条判据只管横轴<b>逐月推进</b>的图；本页另有 {len(_nonmonth)} 张的横轴'
         f'不是逐月月份轴：Exhibit ' + ' / '.join(...) + '。）' if _nonmonth else '')
    """
    out = ''
    if nonmonth:
        out += (f'（这条判据只管横轴<b>逐月推进</b>的图；本页另有 {len(nonmonth)} 张作图的'
                f'横轴不是逐月月份轴：Exhibit '
                + ' / '.join(str(n) for n in nonmonth) + '。）')
    if table_ex:
        # 「左端从哪个月起画」对一张表没有意义，所以它不在上面任何一组里 ——
        # 但也必须说一句，否则读者滚到那张表就发现自己不在名单上（本页第三次栽在这里）。
        out += (f'（另有 {len(table_ex)} 张是 HTML 表：Exhibit '
                + ' / '.join(str(n) for n in table_ex)
                + '，没有横轴，不适用「左端」这个说法。）')
    return out


def compose_brief(df):
    """COST 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实、不出文字，句子在这里拼 —— 措辞是口径的一部分，
    属于各家自己。每个数字都当场从 `series/cost.csv` 算，**一处硬编码都没有**：排名、
    「N 个月最低」、哪个地区相对自身历史最弱、净增 0 出现过几次，下月重跑全都会自己变。

    ═══ COST 独有，别家不能照抄 ═══
      · **R3 的日历变量是 4-4-5 零售日历的 `weeks`（5 周月 vs 4 周月），不是交易日。**
        全站只有这一家是零售周口径。判据仍是「这一列是当月合计还是已经日均化」：
        `net_sales_bn` 是当月合计，除周数才可比；而 comp（同店）是公司**已经按可比周
        调整过**的口径，再除一次周数就是重复修正，所以下面凡是 comp 的句子一律不碰 weeks。
      · 净销售额的 m/m 在 Exhibit 1 里是**整格留空**的（`srow(..., mm_ok=False)`），
        表面 m/m 是多少、其中多少百分点纯粹是周数，全页只有这一段有 —— 它补的正是被
        留空的那一格背后的算术，不是复述汇总表。
      · 报告口径与核心 comp 之差是**推导值**（公司只披露两个口径各自的 comp，不披露差额），
        且按地区拆开后常常正负相消（美国项主要是汽油、国际项主要是汇率，见 Exhibit 6），
        所以只报合计楔子的水平与各地区的符号，不报「合计楔子里汽油占几成」这种拆不出来的比例。
        合计楔子的**名次按符号分两头取**：正楔子问「油汇撑得多不多」（降序第 1 = 撑得最多），
        负楔子问「拖得多深」（升序第 1 = 拖得最深）。一律用降序会印出「被油汇拖低 3.3pp、
        排 53 个月第 53 高」这种要读者自己反过来读的话（2020-04 就是）。
        楔子**是宽是窄只能由 |楔子ᵢ| − |楔子ᵢ₋₁| 现算**：两个口径同向还是反向变动与楔子走阔
        走窄毫无关系（原来那句写死的「继续走阔」在 96 次触发里有 54 次是假的）；
        取绝对值是因为「宽窄」问的是两个口径离得多远，−2.7 → −4.2 是拉开了不是收窄了。
        核心口径已剔除汽油与汇率，所以楔子越宽 = 报告 comp 被油价/汇率撑得越多、
        读数质量越低 —— 排位高不是好消息，措辞必须把这层含义带出来。
      · 仓库数 `wh_total` 是只增不减的计数（`B.is_monotonic` 为真，全序列的月度变动
        一次都没降过）：按 T3，「又创新高」每月都成立、是噪音，汇总表的分位那一列也因此
        留空；有信息的是「净增 0」这件事在历史上有多常见，所以改成频次这种**相对**表述。
      · 本页没有「越低越好」的反向序列（comp、销售额、仓库数都是越高越好），故
        `peak_scan(inverse=True)` 与 T2 的措辞规则在这一家不适用。

    ═══ 与本页 2026-08 同比口径改造的关系（移植时的口径适配）═══
      本页所有增速都是**公司披露的可比周口径**，这是页尾「同比口径」条 + WK_EVID
      在本页数据上实测过的：53 周错位月里披露值与「本月 ÷ 去年同月」的表内算术差出
      整整一周的量、甚至反号（Jan-25 披露 +9.2% vs 算术 −11.6%）。所以本段**一个
      自算的跨年增速都不引**。远端原版 s2 引的是周均序列的自算 y/y（pw[i]/pw[i-12]−1），
      还在错位月配一句「y/y 也非同长区间之比」—— 对披露值这句是**反的**（披露同比的
      基期本来就是同周数的上年错位窗口，错位月里恰恰只有它可直读，不可直读的是表内
      算术），对自算值则当场推翻页尾「唯一一处表内算术在汇总表」的声明。适配后 s2 引
      **披露的 ns_yoy**，按 CONTRACT §6 标「单月」（与汇总表 y/y 列同口径、可逐格
      对上），只作位置与基数陈述、不作趋势断言；反号判据改为周均环比（现算，环比不涉
      同比口径之争）对披露同比；错位月的警告句方向反转 —— 提醒「会反号的是表内算术」。
      环比侧（s1 的表面/周均拆分）保持现算：它是环比不是同比，补的是汇总表 m/m
      留空那一格背后的算术，页尾口径条已把这两处现算读数点名。

    ═══ 定性词一律由当场算出的量决定分支（写死的措辞 + 算出来的数字 = bug）═══
      「只」「走阔」「撑出」「最低」「常态」这类词下面**没有一个是写死的**：周均折算的
      「只」由 |周均变化| < |表面变化| 定（周数 4→5 的月份周均跌得更深，写「只」是反的）；
      楔子的走阔/收窄由 |楔子| 的环比变化定（还有第四个分支：跨零时说「翻了号」）；
      「靠油汇撑出」在楔子为负时改写成「被油汇拖低」、为零时改写成「净影响约为 0」；
      「N 个月最低」在与上月并列时改写成「已连续 N 个月停在下沿」（并列不是本月才发生的
      新低，读者会当成新闻）；净增 0 的稀常由 `B.quant` 按占比给词，不写死「是常态」。
      缺值月一律用 `B.need` 让**该句不写**，而不是让整页构建失败。

    ═══ 分寸：并排读 build/ibkr.py 的 compose_brief()（那是样板，也是上限）═══
    一句话一个意思，五句五层：日历（周数）/ 基数（周均的位置与反号）/ 口径（楔子）/
    区间（三地各自的名次）/ 存量（仓库数）。本月 302 字对样板 347 字，同一个量级。

    改的是**从句数，不是字数**：第一版把楔子那句写成「值 + 走向 + 地区 + 金额 + 排位 +
    破折号转折」六件事挤一句，又把仓库数拿分号挂在「哪个地区最弱」的尾巴上凑成两件事
    一句话 —— 那读起来像脚注不像导读。现在楔子的水平与地区归属用分号分成两段、仓库
    单独成句（顺带不再受地区名次那个 if 的连累）。

    真正删掉的只有一句：周数两端相同时的「y/y 无日历成分」（那是常态，全样本九成以上
    的月份，印出来等于没说）。补上的两处都是**相对表述**：合计楔子的历史名次，以及三地
    里最强的那个排第几 —— 只报最弱的等于只给半张图，读者分不清是全线走弱还是地区分化。
    """
    i = len(df) - 1
    ALL = [str(p) for p in df.index]
    ns, wk = df['net_sales_bn'].values, df['weeks'].values
    nfin = lambda a: int(np.isfinite(np.asarray(a, float)).sum())
    # 序列只剩一个月时，四句话（环比 / 基数 / 楔子变化 / 区间）没有一句算得出来，而 numpy
    # 的 a[i-1] 在 i=0 时会静默取到序列末尾那个月 —— 宁可显式失败，也别印一段拿末月冒充上月的话。
    if i < 1:
        raise SystemExit('brief: 序列只有一个月，无法做任何环比/区间判断')

    # ── R3：净销售额是「当月合计」，周数就是这一家的日历变量 ──────────────
    cs = B.calendar_split(ns, wk, i)
    if cs is None:                       # 缺周数就没法拆日历，宁可整页失败也别少说一半
        raise SystemExit('brief: 最近两个月的 net_sales_bn / weeks 有缺失，无法做 4-4-5 日历拆分')
    pw = cs['series']                                   # 周均销售额（推导值）
    # 相邻月周数相同的月份（4-4-5 里的 4+4 那一对）占三分之一强，那种月份没有日历成分，
    # 硬套「其中 0.0pp 是周数差、周均也是同一个数」等于把同一个环比印两遍。两种写法都得有。
    ndiff = int((np.diff(wk) != 0).sum())
    # 「只」是定性词，得由两个幅度的大小决定：周数由 4 增到 5 的月份，周均变化比表面变化
    # 更深（per_week = (1+raw)·wᵢ₋₁/wᵢ − 1），那种月份印「只」正好说反。
    softer = '只' if abs(cs['per_day']) < abs(cs['raw']) else ''
    s1 = (f'{B.mo(ALL[i])}月{wk[i]:.0f}周、{B.mo(ALL[i - 1])}月{wk[i - 1]:.0f}周：'
          f'净销售额表面环比<b>{B.pct(cs["raw"])}</b>，其中{abs(cs["gap_pp"]):.1f}pp'
          f'纯是周数差，按周均（推导值）{softer}{B.pct(cs["per_day"])}；日历拆得掉、季节性拆不掉。'
          if wk[i] != wk[i - 1] else
          f'{B.mo(ALL[i])}月与{B.mo(ALL[i - 1])}月同为{wk[i]:.0f}周，'
          f'净销售额表面环比<b>{B.pct(cs["raw"])}</b>不含日历成分'
          f'（全样本{len(wk) - 1}次相邻月里{ndiff}次周数不同，这次不是）；季节性仍在。')

    # ── R2：环比与同比反号时必须给基数。周均序列排名接近历史高位，退一格不是掉头 ──
    # 名次的移动方向也是算出来的：写死「退到」的话，周均创出新高的月份会印成往下退。
    # ⚠ 口径适配（2026-08 移植时改，理由见 docstring）：这句的同比引**公司披露的
    # ns_yoy**（单月可比周口径，与汇总表 y/y 列同口径、可逐格对上），不引 base_effect
    # 在周均序列上的自算 y/y —— 本页所有增速都是披露值，53 周错位月里自算的跨年增速
    # 与披露值会反号（见表注与页尾口径条），引它等于把「唯一一处表内算术在汇总表」
    # 的页尾声明当场推翻。be 只取排名（位置陈述），它的 yy / mm / conflict 一概不用。
    be = B.base_effect(pw, i)
    yy_disc = df['ns_yoy'].values
    s2 = ''
    if B.need(pw[i], be['rank'], be['prev_rank']):
        r, pr = be['rank'], be['prev_rank']
        move = (f'从上月的历史第{pr}高退到第{r}' if r > pr else
                (f'从上月的第{pr}升到历史第{r}高' if r < pr else f'与上月并列历史第{r}高'))
        if not B.need(yy_disc[i]):
            # 披露同比缺失的月份（历史上没有，但护栏不能只对今天的数据成立）：
            # 说清楚为什么没有这句，别让读者以为漏印。
            cf, cal = '；本月新闻稿未披露净销售额同比，这句从缺', ''
        else:
            # 反号判据：周均环比（现算，s1 刚印过的那个数）对披露同比 —— 两个都是
            # 读者在本页看得到的读数，不另引第三个口径。
            cf = (f'，却与披露同比（单月可比周口径）{B.pct(yy_disc[i] / 100)}反号，'
                  f'<b>只看环比会读错方向</b>'
                  if (cs['per_day'] < 0) != (yy_disc[i] < 0) else
                  f'，与披露同比（单月可比周口径）{B.pct(yy_disc[i] / 100)}同向')
            # 周数错位月（53 周财年）的警告方向与远端原版**相反**：披露同比的基期本来
            # 就是同周数的上年错位窗口，错位月里恰恰只有它可直读；会反号的是「本月 ÷
            # 去年同月」的表内算术（本页实测差出整整一周的量，见页尾 WK_EVID 与表注）。
            # 同周数月份什么都不加 —— 那是常态，印出来等于没说。i < 12 时 wk[i-12]
            # 是负索引回卷（会静默取到序列末尾），必须先挡。
            cal = ('' if i < 12 or not B.need(wk[i], wk[i - 12]) or wk[i] == wk[i - 12] else
                   f'；本月{wk[i]:.0f}周、去年同月{wk[i - 12]:.0f}周（53 周财年错位），'
                   f'该披露值仍可直读，会反号的是表内算术（见表注）')
        s2 = f'周均{B.usd(pw[i], 2)}bn{move}{cf}{cal}。'

    # ── 口径背离：楔子（= 汽油 + 汇率的贡献）本月是宽了还是窄了，只能靠差分现算 ──
    tr, ta = df['tc_r'].values, df['tc_a'].values
    # R6 的负零规矩：-0.04pp 印成 '-0.0pp' 是格式化产物不是数据（同一个毛病在 pctf/dsp/num
    # 里都单独堵过一次），夹在一串带符号的 pp 中间会让人以为那是个缺失值。
    pp = lambda v: f'{v:+.1f}pp' if round(float(v), 1) else '0.0pp'
    REG = [('美国', 'us_r', 'us_a'), ('加拿大', 'ca_r', 'ca_a'), ('其他国际', 'oi_r', 'oi_a')]
    wg = {nm: df[r].values - df[a].values for nm, r, a in REG}
    s3 = ''
    if B.need(tr[i], ta[i], tr[i - 1], ta[i - 1], *(wg[nm][i] for nm in wg)):
        # 走阔/收窄只能由楔子自己的**环比变化**定：触发原措辞的条件（两个口径同向还是
        # 反向变动）与楔子是宽是窄毫无关系。而「宽窄」问的是两个口径**离得多远**，所以
        # 判据是 |楔子| 的变化，不是带符号差 —— 楔子由 -2.7 走到 -4.2，带符号差为负，
        # 两个口径却是拉开了 1.5pp（油汇的拖累在加重）；由 -2.0 走到 0.0 更露馅：带符号差
        # +2.0 会印出「楔子 0.0pp、环比走阔 2.0pp」这种自己打自己的话。
        # 取整后再比，措辞才和印出来的那两个数一致（0.04 的抖动不该说成走阔）。
        w_now, w_prev = round(tr[i] - ta[i], 1), round(tr[i - 1] - ta[i - 1], 1)
        dgap = round(abs(w_now) - abs(w_prev), 1)
        moveW = (f'较上月的{pp(w_prev)}翻了号' if w_now * w_prev < 0 else
                 f'环比走阔{dgap:.1f}pp' if dgap > 0 else
                 f'环比收窄{abs(dgap):.1f}pp' if dgap < 0 else '环比与上月持平')
        # 名次按符号分两头取（见 docstring）：正楔子降序数「第几宽」，负楔子升序数「第几深」。
        # 印出来的符号是四舍五入后的 w_now，分支就跟着它走，否则措辞和数字会对不上。
        wser = tr - ta                                  # 合计楔子（推导值）
        rkw = ('' if not w_now else
               f'，排{nfin(wser)}个月第{B.rank_of(wser if w_now > 0 else -wser, i)}'
               f'{"宽" if w_now > 0 else "深"}')
        top = max(wg, key=lambda k: wg[k][i])           # 楔子最高的地区
        # 措辞跟**印出来的那个数**走（四舍五入后的），否则 +0.04pp 会印成「撑出0.0pp」。
        tv = round(float(wg[top][i]), 1)
        # 核心口径已剔除油汇，所以正楔子 = 报告 comp 被油价/汇率撑高的幅度（负则是被拖低）。
        how = (f'靠油汇撑出{tv:.1f}pp' if tv > 0 else
               (f'被油汇拖低{abs(tv):.1f}pp' if tv < 0 else '油汇净影响约为 0'))
        pos = [nm for nm in wg if wg[nm][i] > 0]        # 报告口径**严格**高于核心的地区
        neg = [nm for nm in wg if wg[nm][i] < 0]
        # 楔子按地区拆开常正负相消，所以只报符号与是谁，不报「汽油占几成」那种拆不出的比例。
        # 四种组合都得说得通，且**楔子恰好为 0 的地区既不算正也不算负**（历史上出现过 3 次，
        # comp 只有一位小数，0 楔子不罕见）—— 兜底措辞因此不含正负断言。
        # 「只有」只出现在 len(pos)==1 这一支：那时正楔子的地区必然就是 top（最高的那个），
        # 名字不用报两遍；pos 有两个的月份改说「是 A、B，其中 C…」，不能沿用「只有」。
        if pos and neg:
            split = (f'报告口径高于核心的只有{pos[0]}，{how}' if len(pos) == 1 else
                     f'报告口径高于核心的是{"、".join(pos)}，其中{top}{how}')
        elif pos:
            split = f'各地区楔子无一为负，最高的{top}{how}'
        elif neg:
            split = f'各地区楔子无一为正，最高的{top}{how}'
        else:
            split = '各地区楔子全为 0'
        s3 = f'报告−核心楔子（推导值）<b>{pp(w_now)}</b>、{moveW}{rkw}；{split}。'

    # ── 所处区间：地区里相对自身历史最弱的那个 + T3 的单调序列改成频次表述 ──
    REGA = {nm: a for nm, _, a in REG}
    rk = {nm: B.rank_of(df[a].values, i) for nm, a in REGA.items()}
    s4 = ''
    if all(v is not None for v in rk.values()):
        worst = max(rk, key=lambda k: rk[k])
        wa = df[REGA[worst]].values
        lo = B.months_since_lower(wa, i)                # 上一次严格更低是多少个月以前
        # 判据是**严格**小于，所以与上月并列时「为 N 个月最低」上个月同样成立 —— 语义不假，
        # 但读起来像本月才发生的恶化。并列几个月就说几个月，由这里数出来。
        tie = 0
        while i - tie - 1 >= 0 and np.isfinite(wa[i - tie - 1]) and wa[i - tie - 1] == wa[i]:
            tie += 1
        # 「二个月」不是中文量词，B.cn 只管数字不管量词，两个月这一档在这里单独给。
        cnt = '两' if tie == 1 else B.cn(tie + 1)
        if lo is None:                                  # 全样本里没有更低的月份
            zone = f'已连续{cnt}个月停在全样本最低位' if tie else '为全样本最低'
        elif tie:
            zone = f'已连续{cnt}个月停在{lo}个月区间的下沿（上次更低在 {ALL[i - lo]}）'
        else:
            zone = f'为{lo}个月最低（上次更低在 {ALL[i - lo]}）'
        # 只报最弱的那个等于只给了半张图：三地各自的名次同为「相对自身历史」的位置，
        # 另一头在哪里，读者才知道这是全线走弱还是分化。名次并列时（序列头几个月三地
        # 都排第 1）不写这半句 —— 否则会印出「A 最弱…最强的 A 排第 1」。
        best = min(rk, key=lambda k: rk[k])
        far = (f'，最强的{best}排第{rk[best]}'
               if best != worst and rk[best] < rk[worst] else '')
        s4 = (f'{B.cn(len(REG))}个地区里{worst}核心 comp 相对自身历史最弱，'
              f'排第{rk[worst]}/{nfin(wa)}、{zone}{far}。')

    # ── T3：wh_total 只增不减，「又创新高」每月都成立、是噪音（汇总表的分位那一列也因此留空），
    #    所以这里不报水平值，只报「净增 0」在历史上出现的频次这种相对表述 —— 而「常见不常见」
    #    这个词也得跟着频次走（B.quant），不能写死「是常态」：36/122 与 3/122 是两回事。
    #    仓库是自成一层的存量，原来挂在上一句的分号后面，跟「哪个地区最弱」凑成了两件事一句话；
    #    拆出来单独成句，顺带不再受地区名次那个 if 的连累（缺了地区名次不等于缺仓库数）。
    wh = df['wh_total'].values
    dwh = np.diff(wh)
    fin = np.isfinite(dwh)               # 2016-08 / 2017-08 / 2017-09 三个月未披露仓库数
    nz, nf = int(((dwh == 0) & fin).sum()), int(fin.sum())
    if nf and B.need(wh[i], wh[i - 1]) and B.is_monotonic(wh):
        op = wh[i] - wh[i - 1]
        # is_monotonic 允许一成的下降，真出现关店月时「净增 -1 家」既难读又像格式化事故。
        s5 = ('仓库数本月' + ('净增 0' if not op else
                           f'净{"增" if op > 0 else "减"} {abs(op):.0f} 家')
              + f'，{nf}次可比变动里{B.quant(nz, nf, "次")}为 0。')
    else:
        # 2016-08 / 2017-08 / 2017-09 的新闻稿没给仓库数，那两三个月的净增算不出来。
        # 同上：说清楚缺的是哪一头，比整句消失强 —— 缺口本身在 Exhibit 14 的图注里也点了名。
        miss = '本月' if not B.need(wh[i]) else ('上月' if not B.need(wh[i - 1]) else '')
        s5 = (f'仓库数{miss}新闻稿未披露（全序列 {int((~np.isfinite(wh)).sum())} 个月缺），'
              '本月净增算不出。' if miss else '')

    return B.render([s1, s2, s3, s4, s5])


def main():
    if not os.path.exists(SERIES):
        raise SystemExit(f'找不到源数据: {SERIES}')

    df = pd.read_csv(SERIES, index_col=0)
    df.index = pd.PeriodIndex(df.index, freq='M')
    need = ['net_sales_bn', 'weeks', 'ns_yoy', 'us_r', 'ca_r', 'oi_r', 'tc_r',
            'us_a', 'ca_a', 'oi_a', 'tc_a', 'wh_total', 'wh_us', 'ec_r', 'ec_a']
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise SystemExit(f'series/cost.csv 缺列 {miss}')
    # 月份必须逐月连续：断档的序列画成相邻柱就是假的时间轴
    for a, b in zip(df.index[:-1], df.index[1:]):
        if (b - a).n != 1:
            raise SystemExit(f'月份不连续：{a} → {b}')
    LATEST = df.index[-1]

    # 净销售额增速里不进 comp 基数的那部分（新开/关闭仓库 + 口径残差），Ex5 与汇总表共用一列
    df['nc_gap'] = df['ns_yoy'] - df['tc_r']

    mlab = lambda p: p.strftime('%b-%y')                      # 'Jan-21'
    win = lambda start=WIN_START: df.loc[pd.Period(start, 'M'):]
    L = lambda a: [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 6) for v in a]
    iv = lambda v: '—' if pd.isna(v) else f'{int(v)}'         # 缺列时别把 NaN 塞进 int()

    # 53 周财年多出的那一周落在某个 1 月，使该月与「上年同月」不是同一长度的区间。
    # 自动识别而不是硬编码月份；shift(12) 落在序列头部时是 NaN，而 NaN != 4.0 恒为 True，
    # 不加 notna() 守卫会把最早 12 个月整段误报成断点。
    _w = df['weeks']
    WEEK_BREAKS = set(df.index[_w.notna() & _w.shift(12).notna() & (_w != _w.shift(12))])

    def brk(d):
        """把断点月换算成给定窗口内的 x 索引（引擎把线画在该期柱的左缘）。

        窗口盖不到的断点自然不在返回值里，返回空表示这张图上一条线都没有 ——
        调用处必须据此把图注里「此处画了红色竖虚线」那句话一并去掉，否则就是
        图注声称画了、图上没有（复查全站报了 7 条这类）。"""
        return [i for i, p in enumerate(d.index) if p in WEEK_BREAKS]

    def brk1(d, period):
        """单个断点在窗口内的 x 索引；滚出窗口返回 None，绝不抛异常。

        原来这里写的是 list(d8.index).index(...)，2025-09 一旦滚出 e-comm 图窗
        就是 ValueError、整个生成器退出、页面永久停更（build/lpla.py 现在就是
        这个毛病）。窗口起点固定时今天不会触发，但硬失败的写法本身不能留。"""
        lst = list(d.index)
        return lst.index(period) if period in lst else None

    # ── 数值格式化的两条硬约定 ────────────────────────────────────────────
    def dsp(v, d, unit):
        """格式化一个差值/水平值，返回 (显示串, 配色类)。

        两件事在这里一并管住：
          1. **负零不是信息**：四舍五入后等于 0 就印 '0.0'，不印 '-0.0'。
          2. **配色按四舍五入后的值定**：+0.04 印成 '0.0' 却涂成绿色是自相矛盾。
        """
        r = round(float(v), d) + 0.0                 # +0.0 把 -0.0 归一成 0.0
        s = f'{r:+.{d}f}{unit}' if r else f'{0:.{d}f}{unit}'
        return s, ('pos' if r > 0 else ('neg' if r < 0 else ''))

    def ppdiff(v):
        """比率类差异的单位规矩（CONTRACT §2 / GS LPLA 规矩 2）：|差| < 1 写 bp，否则写 pp。

        本页原来一律写 pp，与其余 8 页（schw/lpla/axp/hood/hkex/msci/tsm/wealth）不一致，
        同一站内同类量出现两套写法（复查 recheck#2）。数值本身没错，改的是单位约定。"""
        return dsp(v * 100, 0, 'bp') if abs(v) < 1 else dsp(v, 1, 'pp')

    # ── 截轴上界：从数据里定，而不是从 deck 抄一个固定值 ──────────────────
    def cap_for(d, cols, step=5):
        """上界 = 「除最极端那一个月之外的最大值」向上取整到 step 的倍数；算不出返回 None。

        原来四张图的上界是 deck 里的固定值 18/20/20/25，结果 Apr-21 与 May-21 两个
        COVID 低基数月（有时还带上 Jun-22 那种只超界 0.1pp 的）一起越界，图顶挤出
        三四个红色竖排真值，而空心圈只有一两个 —— 标签与锚点对不上号，人眼复查
        逐张点名（当时是 Ex2 / Ex5 与两张分地区图；本页图号后来改过，别照这串去对今天的页面）。

        改成「只截最极端的那一个月」之后，越界读数集中在同一个 x 上，每个标签都有
        唯一锚点；其余尖峰照常画在轴内。**一个点都没删**，变的只是画到哪里为止。
        """
        v = pd.concat([d[c] for c in cols], axis=1)
        peak = v.max(axis=1)                          # 每月的上包络
        if peak.notna().sum() < 3:
            return None
        rest = peak.drop(peak.idxmax()).max()
        return None if not np.isfinite(rest) else float(np.ceil(rest / step) * step)

    def cap_outliers(d, named, cap):
        """被截读数的清单：月份 + 是哪条序列 + 真值。

        图上那几个红色竖排数字必须能对上号 —— 复查原话是「第三个数没有任何锚点，
        读者没法知道它属于哪个月、哪条序列」。图上画不下的那部分身份信息写进图注。"""
        out = []
        for p in d.index:
            for c, name in named:
                v = d.at[p, c]
                if pd.notna(v) and float(v) > cap:
                    out.append(f'{mlab(p)} {name} {float(v):+.1f}%')
        return out

    def stack(col, k):
        """同一零售月过去 N 年核心 comp 之和（照抄 build_report.py 的 stack）。"""
        v = df[col].values
        out = []
        for i in range(len(v)):
            idxs = [i - 12 * j for j in range(k)]
            out.append(np.nan if min(idxs) < 0 else sum(v[j] for j in idxs))
        return np.array(out)

    def stack_ex(n, col, title):
        d = win()
        pos = [df.index.get_loc(p) for p in d.index]
        ser = []
        for k, c, lab in [(2, 'BLUE', '2-year stack'), (3, 'NAVY', '3-year stack'), (4, 'MBLUE', '4-year stack')]:
            s = stack(col, k)
            ser.append({'name': lab, 'color': c, 'values': L([s[p] for p in pos])})
        return {'n': n, 'kind': 'lines', 'title': title, 'yfmt': 'pct0',
                'xlabels': [mlab(p) for p in d.index], 'xstep': 3,
                'src_extra': 'Stacks = sum of same-retail-month core comp over trailing N years',
                'series': ser}

    def bar_line_ex(n, bar_col, line_col, title, bar_name, line_name, start=WIN_START, xstep=4,
                    src_extra=None, cap=False, **kw):
        d = win(start)
        out = {'n': n, 'kind': 'bar_line', 'title': title, 'yfmt': 'pct0',
               'xlabels': [mlab(p) for p in d.index], 'xstep': xstep,
               'bar': {'name': bar_name, 'color': 'NAVY', 'values': L(d[bar_col])},
               'line': {'name': line_name, 'color': 'BLUE', 'values': L(d[line_col])}}
        if cap:
            c = cap_for(d, [bar_col, line_col])
            outl = ([] if c is None else                       # 上界可能算出 0，别用真值判断
                    cap_outliers(d, [(bar_col, bar_name), (line_col, line_name)], c))
            # 一个点都没越界就根本不截轴，也不留下「本图已截轴」的说明 ——
            # 图注说了截轴、图上却没有红色标注，读者会去找一个不存在的东西。
            if outl:
                out.update({'ycap': c, 'cap_note': CAP_NOTE, 'label_fmt': 'pct1'})
                capped.append(n)
                cs = (f'纵轴上界截在 {c:.0f}%，其余月份全部画在轴内；'
                      f'超界读数（{len(outl)} 个，一个点都没删）：{"；".join(outl)}，'
                      f'图上以红色空心圈/柱端断口符号 + 竖排真值标出。')
                src_extra = (src_extra + cs) if src_extra else cs
        if src_extra:
            out['src_extra'] = src_extra
        out.update(kw)
        return out

    # 截轴文案统一一份：2021 年那几个 COVID 低基数尖峰把近 12 个月压成一条窄带，
    # 规矩 7 的做法是截轴 + 标真值，不是删点也不是砍窗口。
    CAP_NOTE = 'axis capped — outliers shown in red'

    ex = []
    capped = []          # 真正截了轴的 exhibit 编号，「口径与方法说明」那一条据此生成
    # ── 三本登记簿：都在建图那一刻**现读 `ex[-1]['n']`** 记下来，不写死图号 ──
    # 页尾三条注（数据源、两腿口径、同比口径）各自要点名一组图，而图号本轮就动过一次。
    # 写死的名单指错了图不会报错，所以名单只准在建图现场登记；
    # note_datasource() / partition_axes() 那边还会拿它跟 payload 双向对一遍。
    SEC_EX = []          # 由 SEC 申报腿喂的图（其余全是月度新闻稿腿）
    SHARE_EX = []        # 纵轴是百分比、但画的是**占比**而非同比的图（第三桶，见正文块 §8）
    REV_EX = []          # 真的画「总收入」口径的图（口径警告那条只该点它们的名）

    # ── Ex2 图注要回答「本页 comp 图是不是同一个左端」——这句话上一轮写成了
    # 「（全页 comp 图同一起点）」，判据却只是 `HIST_START == WIN_START` 这两个常量相等。
    # 常量相等 ≠ 图相等：Exhibit 11 的电商 comp 这一轮放宽到 Sep-17（两条腿的数据下限），
    # 那句括注当场变成假话。改成现算 —— 把本页每一条 comp 序列的首值都扫一遍，
    # 谁够不到这个左端就点谁的名（点**列名**不点图号：列名在 CSV 里，改图序也不会失效）。
    #
    # ⚠️ 第二次改：上一版写的是「8 条在 2016-01 就有值；另 2 条要更晚才开始」。
    # 「在 2016-01 就有值」是真的，但读起来像「2016-01 是它们的第一个月」—— 实际那 8 条
    # 自 Dec-15 就有值，Exhibit 2 画 127 格是把 Dec-15 那一格真实数据切掉了，页面上
    # 一句话都没有。改成按**首值月份**分组逐条列，是切是缺一眼看得出来。
    COMP_COLS = ['tc_a', 'tc_r', 'us_a', 'us_r', 'ca_a', 'ca_r', 'oi_a', 'oi_r', 'ec_a', 'ec_r']
    _w0 = pd.Period(WIN_START, 'M')
    # COMP_REACH 只挂在 Exhibit 2 上，而 Exhibit 2 的左端是 HIST_START（不是 win() 的
    # WIN_START）。两个常量今天同值，但拿 WIN_START 去描述 Exhibit 2 的左端就是又一处
    # 「常量相等 ≠ 图相等」——按这张图自己真正用的那个常量说。
    _h0 = pd.Period(HIST_START, 'M')
    _comp_first = {c: df[c].dropna().index[0] for c in COMP_COLS if len(df[c].dropna())}
    _comp_by = {}
    for _c, _p in sorted(_comp_first.items(), key=lambda t: (t[1], t[0])):
        _comp_by.setdefault(_p, []).append(_c)
    COMP_REACH = (
        (f'本页 {len(COMP_COLS)} 条 comp 序列的第一个值<b>不在同一个月</b>：'
         if len(_comp_by) > 1 else
         f'本页 {len(COMP_COLS)} 条 comp 序列的第一个值本期落在同一个月：')
        + '；'.join(f'{mlab(p)} 起的有 ' + '、'.join(f'<code>{c}</code>' for c in cs)
                    for p, cs in _comp_by.items())
        + f'。本图窗口左端锁在 {HIST_START}：'
        + (f'比它早的那几个月（'
           + '、'.join(f'{mlab(p)}' for p in _comp_by if p < _h0)
           + '）有值也不画'
           if any(p < _h0 for p in _comp_by) else '没有哪条序列比它更早')
        + (f'，比它晚才开始的那几条（'
           + '、'.join(f'<code>{c}</code> 自 {mlab(p)}'
                       for p, cs in _comp_by.items() if p > _h0 for c in cs)
           + '）画出来的图相应更短。'
           if any(p > _h0 for p in _comp_by) else '，也没有哪条比它更晚。'))

    # Ex 2 —— 头条图：核心 comp 柱 + 报告口径线（同一 % 轴），全历史窗口
    # full: True → 渲染器把它排到汇总表下方的通栏区（127 根柱塞进半栏每根不到 3px）
    ex.append(bar_line_ex(2, 'tc_a', 'tc_r', 'COST Core Comp vs Reported Comp, y/y',
                          'Core Comp (ex. gas & FX)', 'Reported Comp',
                          start=HIST_START, xstep=6, full=True, cap=True,
                          src_extra='Core Comp = global SSS, ex. gas & FX；本图窗口自 '
                                    f'{HIST_START} 起'
                                    + ('（与 win() 的默认左端 WIN_START 同值）。'
                                       if HIST_START == WIN_START
                                       else f'（win() 的默认左端 WIN_START 是 {WIN_START}）。')
                                    + COMP_REACH))

    # Ex 3 —— 全公司 stacks
    ex.append(stack_ex(3, 'tc_a', 'COST Core Comp Growth Trends'))

    # Ex 4 —— 净销售额（左轴 $bn 柱）+ 同比（右轴 % 线）：PDF 为双轴，此处照搬
    d = win()
    b4 = brk(d)
    ex4 = {
        'n': 4, 'kind': 'bar_line_dual', 'title': 'Monthly Net Sales ($bn) & y/y Growth',
        'xlabels': [mlab(p) for p in d.index], 'xstep': 3, 'ylab2': 'y/y (%)',
        'src_extra': '注: 柱 = 净销售额绝对值，未按周数调整（零售月为 4 或 5 周，4-4-5 日历）；'
                     '线 = 公司报告 y/y，其基期是同样周数的上年错位窗口，与相邻柱不是同一区间。',
        'bar': {'name': 'Net sales ($bn, LHS)', 'color': 'BLUE', 'values': L(d['net_sales_bn']), 'yfmt': 'usd0'},
        'line': {'name': 'y/y % (RHS)', 'color': 'NAVY', 'values': L(d['ns_yoy']), 'yfmt': 'pct0'},
    }
    if b4:
        # 断点竖排标签压在柱体上（人眼复查：红字盖住浅蓝柱、占掉图中相当高一段），
        # 所以标签只留能一眼认出的最短说法，完整解释在下面的 src_extra、tooltip
        # 与页尾说明第 5 条里各有一份 —— 信息一点没少，图上少压掉三分之二的柱。
        ex4.update({
            'break_at': b4, 'break_label': '53-week month',
            'bar_marks': b4,
            'mark_note': '本零售月与上年同月周数不同（53 周财年），柱的同比不可直接读',
        })
        ex4['src_extra'] += (f'图上 {"、".join(mlab(d.index[i]) for i in b4)} 处画有红色竖虚线、'
                             '柱用斜纹标出：53 周财年造成该月与上年同月周数不同，'
                             '该处柱的同比不可直接读。')
    ex.append(ex4)

    # Ex 5 —— 净销售额增长的 comp / 非 comp 拆分（柱线间距即非 comp 贡献）
    ex.append(bar_line_ex(5, 'tc_r', 'ns_yoy', 'Net Sales Growth: Comp vs Non-Comp Contribution',
                          'Reported comp (y/y)', 'Net sales (y/y)', xstep=3, cap=True,
                          src_extra='恒等式轧差：非 comp 贡献 = 净销售额 y/y − 报告口径 comp，'
                                    '含新开/关闭仓库与口径残差，不是公司披露值。'))

    # Ex 6 —— 汽油与汇率影响（报告 − 核心）分地区，避免正负相消
    # 「两股力常互相抵消」这句话原来配了一个写死的例子（2022-05：US +6.8 / Other Intl −7.5）。
    # 数字今天仍对得上，但那是把一次实测钉进文案：CSV 一重述它就悄悄变成假话，
    # 而没有任何检查会响。所以例子改成现算。
    #
    # ⚠️ 第二次改：上一版现算的判据是「两侧符号相反、|US|+|OI| 合计张口最大」，选出
    # Oct-22（US +3.1 对 OI −13.3）—— 13.3 里只被抵掉 3.1，读者看到的是「两股力量级
    # 悬殊」，正好不是这句话要论证的「互相抵消」。数字没错，是**论据与论点脱节**。
    # 判据换成直接量「这个月被对冲掉了多少个百分点」= min(|US|, |OI|)，取它最大的月份，
    # 句子里报的也正是这个量 —— 判据、数字、论点是同一件事。
    _us_w, _oi_w = d['us_r'] - d['us_a'], d['oi_r'] - d['oi_a']
    _opp = (_us_w * _oi_w < 0) & _us_w.notna() & _oi_w.notna()
    _wedge_eg = ''
    if _opp.any():
        _cancel = pd.concat([_us_w[_opp].abs(), _oi_w[_opp].abs()], axis=1).min(axis=1)
        _pk = _cancel.idxmax()
        _wedge_eg = (f'合并成一根柱时两股力常互相抵消 —— 图窗内 US 与 Other Int\'l '
                     f'抵消得最多的一个月是 '
                     f'{mlab(_pk)}：US {_us_w[_pk]:+.1f} 对 Other Int\'l {_oi_w[_pk]:+.1f}，'
                     f'<b>这两条</b>相加只剩 {_us_w[_pk] + _oi_w[_pk]:+.1f}pp，'
                     f'{_cancel[_pk]:.1f}pp 在它们之间对冲掉了'
                     f'（{int(_opp.sum())} 个月两侧符号相反）。'
                     # ⚠️ 别写「合成一根柱只剩 X」：那会被读成把**本图三条腿**合起来的
                     # 那根柱，而 Canada 也在里面（本期 Jun-22 全公司 wedge 是 +5.1，
                     # 不是 US+OI 的 +1.1）。只说被点名的这两条。
                     )
    ex.append({
        'n': 6, 'kind': 'lines', 'title': 'Gas & FX Wedge by Region (reported - core), pp',
        'yfmt': 'pp0', 'xlabels': [mlab(p) for p in d.index], 'xstep': 3, 'zero_line': True,
        'src_extra': '用公司自己披露的分地区 reported 与 core 之差做的近似归因：'
                     '美国项主要是汽油价格，国际项主要是汇率折算——不是公司拆分。'
                     + _wedge_eg,
        'series': [{'name': 'US', 'color': 'NAVY', 'values': L(d['us_r'] - d['us_a'])},
                   {'name': 'Canada', 'color': 'MBLUE', 'values': L(d['ca_r'] - d['ca_a'])},
                   {'name': "Other Int'l", 'color': 'BLUE', 'values': L(d['oi_r'] - d['oi_a'])},
                   {'name': 'Total (对照)', 'color': 'GRAY', 'values': L(d['tc_r'] - d['tc_a'])}],
    })

    # Ex 7 —— 分部收入结构（季度，100% 堆叠柱）
    #
    # 这张图回答的是「三个地区各占多少、结构怎么挪的」，与本页其余 comp 图不同频、
    # 也不同口径，所以每一层都得当场说清楚：
    #
    #   · **口径**：总收入（净销售额 + 会员费），不是净销售额。同页 Exhibit 2–6 全是
    #     净销售额口径 —— 不点明就是让两张图在同一页里互相打架。会员费拆不开地区，
    #     这也正是只能用总收入口径的原因；那层不确定下面**定了界**，不是含糊过去。
    #   · **推导值**：每个 Q4 都是 FY 减 36 周 YTD 推出来的（CONTRACT §5 第 1 条）。
    #     推导有多少根、恒等式在不在，全部现算 + 断言，不写死。
    #   · **窗口**：左端是数据边界（墨西哥 JV 并表日），不是画图时截的。
    #
    # 图型选 `stacked_dual` 且**不给 `line`**：CONTRACT §3 那张表写着「不给 line 就退化成
    # 纯堆叠柱」，而占比型堆叠里三段之和恒为 100，段高本身就是占比，再拿其中一段换个刻度
    # 画一遍是同一个数说两遍。给 line 的例外是「最矮那段量不出来」—— 本图最矮的一段在
    # 11% 上下（下面现算并印在图注里），量得出来，例外不成立。
    #
    # 段内不开 `label`：引擎的 stacked_dual 分支画段内数值走的是 `comma(值, 0)`
    # （assets/charts.js 里写死 0 位小数、不带单位），占比在那里会被印成裸整数「73」，
    # 与本图声明的 `fmt: 'pct1'` 当场对不上。逐格读数走右上角「表格」视图 —— 那一路
    # 认 `ex.fmt`（charts.js 的 `var sdf = fmtOf(ex.fmt || 'f0c')`），所以 `fmt` 与
    # `yfmt` **两个都要给**：只给 yfmt 的话表格视图会退回 f0c，把占比印成没有百分号的整数。
    _seg = load_seg_q()
    # ⚠️ 页尾那几条注与页顶释义要用**同一份**装载结果（note_two_source /
    # note_ticket_traffic / compose_glossary / subtitle_for），别重新读一遍磁盘 ——
    # 读两遍就有两份可能不一致的真值。就地留个别名，装载现场只此一处。
    # 目标文件里没有那一层页尾注时，这一行删掉即可（它只是个别名）。
    _SEG_ALL = _seg
    _sq = _seg[_seg['scope'] == 'Q'].reset_index(drop=True)
    _sfy = _seg[_seg['scope'] == 'FY'].set_index('fq')
    if _sq.empty:
        raise SystemExit('cost_seg_q.csv 里一行 scope=Q 都没有，Exhibit 7 画不出来')

    # ── 断言 1：窗口左端就是数据边界本身 ───────────────────────────────────────
    # SEG_FLOOR 是**事件日**（墨西哥 JV 并表日），不是随数据滚动的读数，所以它可以是常量；
    # 但「CSV 的第一格正好落在这一天」是一句会过期的话，必须每次构建当场验。
    if str(_sq['period_start'].iloc[0]) != SEG_FLOOR:
        raise SystemExit(
            f'Exhibit 7 的左端说明写着「窗口左端 = 墨西哥 JV 并表日 {SEG_FLOOR}」，'
            f'而 cost_seg_q.csv 的第一格自 {_sq["period_start"].iloc[0]} 起 —— '
            f'先决定这张图跨不跨那个口径断点（跨就得画 break_at），再改这条断言')

    # ── 断言 2：季度轴逐格相接，中间不许有洞 ───────────────────────────────────
    # 堆叠柱把相邻两格画成挨着的柱，等于声称时间轴是连续的。少一个季度而照画，
    # 就是 CONTRACT §5 第 3 条点名的「不可比的相邻期画成连续序列」。
    _ps = pd.to_datetime(_sq['period_start'])
    _pe = pd.to_datetime(_sq['period_end'])
    _hole = [f'{_sq["fq"][i]}→{_sq["fq"][i + 1]}' for i in range(len(_sq) - 1)
             if _pe.iloc[i] + pd.Timedelta(days=1) != _ps.iloc[i + 1]]
    if _hole:
        raise SystemExit(f'分部季度序列不首尾相接：{_hole} —— 堆叠柱会把断档画成相邻两格')

    # ── 断言 3：Q4 的推导恒等式（这就是 derived 那一列的全部含义）───────────────
    # Q4 = 全年 − (Q1+Q2+Q3)。逐年逐列核，周数也核（Q4 周数 = 全年周数 − 36）。
    # 只核**四个季度齐全且有对应 FY 行**的年份：最新财年在途（本期 FY26 只有 3 个季度），
    # 那不是错，是还没到 Q4。
    _SEG_COLS = ['us_mn', 'ca_mn', 'oi_mn', 'total_mn', 'weeks']
    _der_ck, _off = 0, []
    for _y, _g in _sq.groupby(_sq['fq'].str[:4]):
        if _y not in _sfy.index or len(_g) != 4:
            continue
        _der_ck += 1
        for _c in _SEG_COLS:
            if int(_g[_c].sum()) != int(_sfy.loc[_y, _c]):
                _off.append(f'{_y}.{_c}（四季合计 {int(_g[_c].sum())} vs 全年 {int(_sfy.loc[_y, _c])}）')
    if _off:
        raise SystemExit('Q4 = 全年 − 前三季 这条恒等式对不上：' + '；'.join(_off)
                         + ' —— Exhibit 7 的图注正是拿它给 derived 那一列背书，不能带伤上线')
    if set(_sq['fq'][_sq['derived'] == 1]) != set(_sq['fq'][_sq['fq'].str.endswith('Q4')]):
        raise SystemExit('derived 标记与「Q4 才是推导值」对不上 —— 图注会把推导根数说错')

    # ── 占比：分部 ÷ 该季总收入（构造上三段和恒为 100）─────────────────────────
    _SEG_REG = [('US', 'us_mn', 'NAVY'),            # 配色与 Exhibit 6 / 12 的地区线一一对应：
                ('Canada', 'ca_mn', 'MBLUE'),       # 同一个地区在本页每张图上永远是同一个颜色，
                ("Other Int'l", 'oi_mn', 'BLUE')]   # 换图不用重新认色。
    if (_sq['total_mn'] <= 0).any():
        raise SystemExit('分部季度表里有非正的 total_mn —— 占比的分母不能是它')
    _sh = {nm: _sq[c] / _sq['total_mn'] * 100 for nm, c, _ in _SEG_REG}
    _sum_err = float((sum(_sh.values()) - 100).abs().max())
    if _sum_err > 1e-9:
        raise SystemExit(f'三段占比之和偏离 100 达 {_sum_err:.3g}pp —— '
                         f'us+ca+oi 与 total 对不上，堆叠柱会缺一块或溢出柱顶')

    _SEG_X = fq_xlabels(_sq['fq'], 'Exhibit 7')
    _seg_vals = {nm: L(_sh[nm]) for nm, _, _ in _SEG_REG}
    # ── 断言 4：稠密（stacked_dual ∈ verify_pages.DENSE / mrwin.DENSE）──────────
    # 平滑图型里一个 null 就是 ERROR：引擎把 null 交给 Catmull-Rom 会画出一条塌到零的
    # 假线，逐点标数值时还会抛异常。这里显式验，而不是指望 CSV 永远是满的。
    _nul = {nm: [i for i, v in enumerate(a) if v is None] for nm, a in _seg_vals.items()}
    if any(_nul.values()) or any(len(a) != len(_SEG_X) for a in _seg_vals.values()):
        raise SystemExit(
            f'Exhibit 7 是 stacked_dual（DENSE 图型），窗口内不许有 null、长度必须等于'
            f' x 标签数（{len(_SEG_X)}）：'
            + '；'.join(f'{nm} {len(a)} 格、null {len(_nul[nm])} 个' for nm, a in _seg_vals.items()))

    # ── 图注要用的读数，全部现算 ───────────────────────────────────────────────
    _seg_lo_nm, _seg_lo_i = min(((nm, _sh[nm].idxmin()) for nm, _, _ in _SEG_REG),
                                key=lambda t: _sh[t[0]][t[1]])
    _seg_rng = '；'.join(
        f'{nm} 本期 {_sh[nm].iloc[-1]:.1f}%（{_sh[nm].min():.1f}% @{_sq["fq"][_sh[nm].idxmin()]} ~ '
        f'{_sh[nm].max():.1f}% @{_sq["fq"][_sh[nm].idxmax()]}）'
        for nm, _, _ in _SEG_REG)
    _seg_der = int(_sq['derived'].sum())
    _is_q4 = _sq['fq'].str.endswith('Q4')
    _seg_wk4 = sorted({int(w) for w in _sq['weeks'][_is_q4]})
    _seg_wk13 = sorted({int(w) for w in _sq['weeks'][~_is_q4]})
    # 53 周财年多出来的那一周落在 Q4：哪几个季度是长的，点名而不是写死
    # （同 main() 里 WEEK_BREAKS 的做法 —— 再加一个 53 周财年，这句话自己会变）。
    _seg_q4_long = list(_sq['fq'][_is_q4 & (_sq['weeks'] == max(_seg_wk4))])

    # 口径对照 + 会员费的**定界**：拿分部表的 FY 行去接 cost_fy.csv 的同一财年。
    # 'FY2025' → 'FY25' 只是两张表的写法差异，不是口径差异。
    _fyd = load_fy()
    _FY_ALL = _fyd           # 同上（Exhibit 16 会把 _fyd 换成按财年建索引的另一份）
    _fyd['fq'] = 'FY' + _fyd['fy'].str[-2:]
    _cal = _fyd.set_index('fq').join(_sfy[['us_mn', 'ca_mn', 'oi_mn', 'total_mn']], how='inner')
    if _cal.empty:
        raise SystemExit('cost_fy.csv 与分部表没有一个共同财年 —— '
                         'Exhibit 7 图注里「总收入 vs 净销售额」那句话没有数可引，'
                         '而那句话是本图口径声明的全部依据，不能空着上线')
    # 这一条顺带把「分部合计 = 利润表的总收入」验了：两张表出自同一份 10-K 的不同段落，
    # 对不上就说明其中一张读错了，而图注正要拿它们的差额去解释「总收入 ≠ 净销售额」。
    _cal_err = float((_cal['total_mn'] - _cal['total_rev_mn']).abs().max())
    if _cal_err > 0:
        raise SystemExit(f'分部三段合计与 cost_fy.csv 的 total_rev_mn 最大差 {_cal_err:.0f}mn —— '
                         f'两张表本该是同一份 10-K 的同一个数')
    _cal['us_share'] = _cal['us_mn'] / _cal['total_mn'] * 100
    # 最极端的一侧：把**全部**会员费算给美国，再看美国的占比掉到哪里。
    # 这不是估计值，是上界 —— 会员费怎么分，美国的占比都不会比这更低。
    _cal['us_share_ns'] = ((_cal['us_mn'] - _cal['memb_fee_mn'])
                           / (_cal['total_mn'] - _cal['memb_fee_mn']) * 100)
    _cal['bound'] = _cal['us_share_ns'] - _cal['us_share']
    _cc = _cal.iloc[-1]
    _cy = str(_cal.index[-1])
    _bw_y = _cal['bound'].abs().idxmax()

    # 图注里要指认「同一页别的图」时，图号一律**现读已装配的 payload**，不写字面量。
    # 本页因为重排图序翻过车（见页尾 WINDOW_NOTE 那段的三次返工），而这张图之前的
    # 每一张都已经在 `ex` 里了，数一遍就有。指不到的就把那半句话去掉，不留一个空号。
    _pn = [e['n'] for e in ex]
    _pre_txt = ('' if not _pn else
                (f'本页 Exhibit {_pn[0]}–{_pn[-1]}' if len(_pn) > 1 else f'本页 Exhibit {_pn[0]}'))
    _ns_n = next((e['n'] for e in ex if 'Monthly Net Sales' in str(e.get('title'))), None)

    ex.append({
        'n': 7, 'kind': 'stacked_dual', 'full': True,
        # `fmt` 与 `yfmt` 两个都给（见上面那段注释）：前者管表格视图与 tooltip，
        # 后者管纵轴刻度。只给一个就会有一路把百分比印成裸数字。
        'fmt': 'pct1', 'yfmt': 'pct0',
        # 标题里「total revenue (net sales + membership fees)」不是修辞，是口径声明：
        # 同一页别的图画的是净销售额，标题不写全的话这张图会安静地和它们打架。
        'title': SEC_SEG + 'Revenue mix by segment — total revenue '
                           '(net sales + membership fees), quarterly',
        'ylab': '% of total revenue（净销售额 + 会员费；堆叠 = 100%）',
        'xlabels': _SEG_X,
        'stacks': [{'name': nm, 'color': cl, 'values': _seg_vals[nm]}
                   for nm, _, cl in _SEG_REG],
        'src_extra':
            # ── 出处（全页 source 那一行说的是新闻稿，本图不是）──
            f'<b>本图的数据源与本页其余各图不同</b>：分部口径的收入月度新闻稿从来不报，'
            f'本图取自 Costco 报送 SEC 的 <b>Form 10-K / 10-Q 分部附注（Segment '
            f'Reporting）</b>，申报人 CIK <code>{SEC_CIK}</code>，'
            f'{len(_sq)} 个季度共读自 {int(_sq["accession"].nunique())} 份申报'
            f'（每一行的 accession 号都在 <code>series/cost_seg_q.csv</code> 里）。'
            f'页面顶部那条 <code>Source:</code> 说的是月度新闻稿，对本图不适用 —— '
            f'payload 没有逐图覆盖 source 的字段，所以出处写在标题前缀与这里。'
            # ── 口径：总收入，不是净销售额 ──
            f'<b>⚠️ 口径是「总收入」＝ 净销售额 + 会员费，不是净销售额。</b>'
            + (f'{_pre_txt}（本图之前的每一张）画的全是净销售额与净销售额口径的 comp，'
               f'与本图不是同一个量。' if _pre_txt else '')
            +
            f'{_cy} 实测：分部三段 {_cc["us_mn"]:,.0f} / {_cc["ca_mn"]:,.0f} / '
            f'{_cc["oi_mn"]:,.0f} = 合计 {_cc["total_mn"]:,.0f}mn，'
            f'而合并利润表的净销售额是 {_cc["net_sales_mn"]:,.0f}mn，'
            f'差的 {_cc["memb_fee_mn"]:,.0f}mn 就是会员费（占总收入 '
            f'{_cc["memb_fee_mn"] / _cc["total_mn"] * 100:.1f}%）。'
            # ── 会员费拆不开：给出界，而不是挥挥手 ──
            f'<b>会员费按地区拆不开</b>（分部附注只给各分部的<b>总收入</b>，不单列各地区会员费），'
            f'所以本图只能是总收入口径。这层不确定有多大是<b>可以定界</b>的：'
            f'把会员费<b>全部</b>算到美国头上是最极端的一侧，那样 {_cy} 美国的占比会从 '
            f'{_cc["us_share"]:.1f}% 掉到 {_cc["us_share_ns"]:.1f}%（{_cc["bound"]:+.2f}pp）；'
            f'{len(_cal)} 个可对照财年（{_cal.index[0]}–{_cal.index[-1]}）里这个界最宽的是 '
            f'{_bw_y} 的 {_cal.loc[_bw_y, "bound"]:+.2f}pp。'
            f'<b>也就是说，会员费怎么分都动不了本图一个百分点</b> —— '
            f'口径要标清楚，但结构结论不因它改写。'
            # ── 推导值（CONTRACT §5 第 1 条）──
            f'<b>{len(_sq)} 根柱里有 {_seg_der} 根是推导值</b>：Costco 从不单独披露第四财季，'
            f'Q4 ＝ 全年 − 同一起点的 36 周 YTD（Q1+Q2+Q3，各 '
            f'{"／".join(str(w) for w in _seg_wk13)} 周）。这条恒等式在构建期逐年核过 —— '
            f'{_der_ck} 个四季齐全的财年、{len(_SEG_COLS)} 列（含周数）全部对得上，差额恒为 0；'
            f'对不上就停机，不出图。'
            f'Q4 是 {"／".join(str(w) for w in _seg_wk4)} 周而 Q1–Q3 各 '
            f'{"／".join(str(w) for w in _seg_wk13)} 周'
            + (f'（多出来的那一周落在 53 周财年：{"、".join(_seg_q4_long)} 是 '
               f'{max(_seg_wk4)} 周）' if len(_seg_wk4) > 1 else '')
            + f'：本图画的是<b>占比</b>不是水平值，柱高恒为 100%，'
            f'周数长短不会把柱高读错；但 Q4 那一格里的季节性是十六七周的平均，'
            f'与相邻三格不是同一段长度。'
            # ── 窗口 = 数据边界 ──
            f'<b>窗口自 {_SEG_X[0]}（{SEG_FLOOR} 起）画满 {len(_sq)} 个季度，'
            f'左端是数据边界不是画图时截的</b>：Costco 自 {SEG_FLOOR} 起把原本 50% 权益的'
            f'墨西哥合资公司并表且<b>不重述</b>历史，并表日之前的 Other International 与之后'
            f'不是同一个口径，跨过去读会看到一个纯属并表造成的跳升。CSV 的第一格 period_start '
            f'正是这一天（构建期有断言钉着）。本页的窗口纪律是「数据在就画」'
            f'（与电商 comp 那张、地区叠图那张的图注同一条判据），所以这里一格都没截。'
            # ── 怎么读 ──
            f'<b>每根柱恒高 100%，所以本图只讲结构、一个字都没讲规模</b> —— '
            f'柱高一样不代表那个季度收入一样，'
            + (f'规模看 Exhibit {_ns_n}。' if _ns_n else '规模请看本页那张月度净销售额图。')
            +
            f'区间（现算）：{_seg_rng}。'
            f'<b>本图不画右轴占比线</b>：三段之和恒为 100，段高本身就是占比，'
            f'再拿其中一段换个刻度画一遍是同一个数说两遍（CONTRACT §3）；'
            f'给线的例外条件是「最矮那段量不出来」—— 本图最矮的一格是 '
            f'{_seg_lo_nm} 在 {_sq["fq"][_seg_lo_i]} 的 {_sh[_seg_lo_nm][_seg_lo_i]:.1f}%，'
            f'量得出来，例外不成立。'
            f'段内不标数值：引擎画段内数字走的是写死 0 位小数、不带单位的格式器，'
            f'占比会被印成裸整数，与本图声明的百分比格式对不上 —— '
            f'逐格读数请走右上角「表格」视图。',
    })

    # 页尾三条注各自要点名一组图，而图号本轮动过 —— 名单只准在建图现场登记
    # （main() 开头的 `SEC_EX / SHARE_EX / REV_EX = []`）。**这张图三样都占**：
    #   SEC_EX   出自 SEC 申报，不是月度新闻稿（数据源那条注要分开说）
    #   SHARE_EX 纵轴是百分比但画的是**占比**不是同比（同比口径那条注的第三桶；
    #            不登记的话 partition_axes() 会把它算进「同比」桶并当场硬失败）
    #   REV_EX   画的是「总收入」口径（含会员费），口径警告那条只该点它的名
    # ⚠️ 若目标文件里还没有这三张登记表（它们是页尾注那一层引入的），把这三行删掉；
    #    留着会 NameError。三行放在 append 之后、用 ex[-1]['n'] 取号，不写死数字。
    SEC_EX.append(ex[-1]['n'])      # 出自 10-K/10-Q 分部附注
    SHARE_EX.append(ex[-1]['n'])    # 画的是占比，不是同比
    REV_EX.append(ex[-1]['n'])      # 且是「总收入」口径（含会员费）

    # Ex 8-10 —— 分地区
    ex.append(bar_line_ex(8, 'us_a', 'us_r', 'US Comp, y/y', 'Core (ex. gas & FX)', 'Reported',
                          cap=True))
    ex.append(bar_line_ex(9, 'ca_a', 'ca_r', 'Canada Comp, y/y', 'Core (ex. gas & FX)', 'Reported',
                          cap=True))
    # Ex10 不截轴：其余三张图的最大值与「次极端月」差着一大截（Canada 44.0 vs 28.8），
    # 截掉一个月能换回 1/3 的纵向空间；Other Int'l 是 33.5 vs 25.7，同样规则只把上界
    # 从 ~34 挪到 30，为一成的空间多添一处红色标注不划算。轴范围本来就不是被单点定死的。
    ex.append(bar_line_ex(10, 'oi_a', 'oi_r', 'Other International Comp, y/y',
                          'Core (ex. gas & FX)', 'Reported'))
    # 三张分地区图的图号现读，不写死：下面 Ex12（叠图）的图注要点它们的名，
    # 而图序改过一次之后那句话就成了假话（原文写死「与 Exhibit 7/8/9 是同样的三条序列」）。
    _REGION_NS = [e['n'] for e in ex[-3:]]

    # Ex 11 —— 电商（左端现算：公司开始披露 e-comm comp 的第一个月，不早于 WIN_START）
    #
    # 2026-08-19：原来这里是写死的 ECOMM_START='2022-01'，把图截在 55 格。判据与 Ex12 同一条 ——
    # 「那是画图时截的窗口，不是数据的边界」—— 上一轮把 Ex12 放宽了却漏了这张。
    # 两条腿在 series/cost.csv 里都是**逐月无缺**的连续段（下面的 assert 钉死），
    # 2022 之前的那 50 来个月是公司真披露过的读数，不是插值，就该画上去。
    #
    # 左端取**两条腿里最早的那个首值**（ec_r 的 2017-09），不取主腿 ec_a 的首值：
    # 后者会把 ec_r 那 3 个月真值扔掉，与本轮「数据在就画」的判据相反。bar_line 不属
    # mrwin.DENSE，前 3 格只有线没有柱，引擎按 null 断笔处理，不会插出假柱。
    _ec = df[['ec_r', 'ec_a']].dropna(how='all')
    for _c in ('ec_r', 'ec_a'):
        _s = df[_c].dropna()
        if len(_s) != (_s.index[-1] - _s.index[0]).n + 1:
            raise SystemExit(f'{_c} 首末之间有缺月，电商 comp 那张图的左端判据要重看')
    ECOMM_FROM = max(pd.Period(WIN_START, 'M'), _ec.index[0])
    d8 = win(str(ECOMM_FROM))
    b10 = brk1(d8, ECOMM_BREAK)
    _ec_w = d8[['ec_a', 'ec_r']]
    _lo, _hi = _ec_w.min().min(), _ec_w.max().max()
    _lo_p = _ec_w.min(axis=1).idxmin()
    _hi_p = _ec_w.max(axis=1).idxmax()
    _r0, _a0 = df['ec_r'].dropna().index[0], df['ec_a'].dropna().index[0]
    ec_src = (f'序列本身月度波动很大（图窗内 {_lo:+.1f}% ~ {_hi:+.1f}%，'
              f'低点 {mlab(_lo_p)}、高点 {mlab(_hi_p)}），无法从图上分离口径影响。'
              f'<b>图窗自 {mlab(ECOMM_FROM)} 起，那是公司开始披露电商 comp 的第一个月，'
              f'不是画图时截的</b>：报告口径自 {mlab(_r0)} 起 '
              f'{int(df["ec_r"].notna().sum())} 个月、核心口径自 {mlab(_a0)} 起 '
              f'{int(df["ec_a"].notna().sum())} 个月，逐月无缺，全部画上'
              f'（最左 {(_a0 - _r0).n} 格只有 Reported 那条线：核心口径晚 {(_a0 - _r0).n} '
              f'个月才开始披露，柱在那里留空、不补 0）。'
              # ⚠️ 2026-08-19（第二次改）：原文「本页其余 comp 图一律自 2016-01 起」是全称，
              # 上一轮改成「本页时序图的窗口左端**统一取** 2016-01」—— 换了个说法，还是假的：
              # 同一页的 Exhibit 14（Warehouse Count）起于 Dec-15，比 2016-01 还早一个月
              # （它走 first_valid_index()，不过 win()），读者往下滚三张图就看得到。
              # 现在只说一件本文件当场能验的事：win() 的默认左端是哪个常量、本图取的是哪个值。
              # 「本页所有图」这种外延不归这句话管，页尾说明第 3 条那边现读 payload 逐张列。
              f'本图的左端是 max(win() 的默认左端 {WIN_START}，两条腿里最早的那个首值)'
              f' = {mlab(ECOMM_FROM)}；够不到 {WIN_START} 是<b>数据下限</b>，不是截断。'
              f'代价说在明处：窗口里含 COVID 低基数那一段（{mlab(_hi_p)} 峰值 {_hi:+.1f}%），'
              f'纵轴被它撑开，近两年那段个位数波动在图上是一条窄带 —— '
              f'要逐月读近端请看 Exhibit 1 汇总表与页尾核对表。'
              f'本图<b>不截轴</b>：截轴的判据（cap_for）是「除最极端那一个月之外的最大值」，'
              f'为的是把越界读数收敛到同一个 x 上；而这里高台是连续十几个月、不是一个离群点，'
              f'截了会在图顶排出一串没法逐个对锚的红字。')
    ec_kw = {}
    if b10 is not None:
        # 同 Ex4：竖排标签原文 44 个字符，从图顶一路压到零线，中段压在深蓝柱上读不出来。
        # 图上只留「definition change」，改成什么、为什么不可比写在图注与说明第 4 条。
        ec_kw = {'break_at': [b10], 'break_label': 'definition change'}
        ec_src = (f'FY26 起口径由 e-commerce 改为 Digitally-Enabled comparable sales，前后不保证可比；'
                  f'图上 {mlab(ECOMM_BREAK)} 处的红色竖虚线即该口径变更。' + ec_src)
    else:
        ec_src = ('FY26 起口径由 e-commerce 改为 Digitally-Enabled comparable sales，前后不保证可比；'
                  '该断点已滚出本图窗口，图上不再画竖虚线。' + ec_src)
    ex.append(bar_line_ex(11, 'ec_a', 'ec_r', 'E-commerce / Digitally-Enabled Comp, y/y',
                          'E-comm Core (ex. FX)', 'Reported', start=str(ECOMM_FROM),
                          src_extra=ec_src, **ec_kw))
    _EC_N = ex[-1]['n']          # 电商 comp 那张图的图号；下面三处图注/表注现读它

    # Ex 12 —— 分地区核心 comp 叠图
    # 2026-08-19：窗口从写死的 `df.iloc[-OVERLAY_MONTHS:]`（25 个月）改成 win() = 2016-01 起，
    # 与本页 Ex2/3/4/5/6/8/9/10/13 同一个左端。理由不是「统一好看」，是这三列本来就有：
    # series/cost.csv 的 us_a / ca_a / oi_a 从 2015-12 起 128 个月**一格不缺**（0 个 null），
    # 25 个月是画的时候截的，不是数据的边界。同一页 Ex8/9/10 早就把这三条各自画满 127 个月，
    # 而本图是它们的叠合对照 —— 单看一个地区能看十年、三个地区放一起只能看两年，
    # 「哪个地区先转向」这个本图唯一要回答的问题在 25 个月里根本问不出来 ——
    # 实测（2026-08-19 的数据）：三条序列的**每一个**极值都落在旧窗口（Jul-24 起）之外，
    # 加拿大谷底 −5.0%（2020-04）、美国峰值 +24.9% 与加拿大峰值 +23.8%（同为 2021-04）、
    # Other Int'l 谷底 −1.2%（2019-02）；旧窗口内三条线的实际区间只有 +2.7% ~ +12.3%。
    # 标题里原本写死的 "last 25m" 一并作废 —— 那是对窗口的一句声称，窗口变了它就是假话。
    #
    # `markers` 同时撤掉：markers 在 charts.js 里是每点一个 r=2.1 的实心圆（直径 4.2px）。
    # 25 个月半栏时一格 20.4px，圆点之间还有 16px 空当，是「逐月观测」的标记；
    # 127 个月通栏后一格只剩 8.76px（mrwin.band_px 实测），三条线各铺 127 个 4.2px 的点，
    # 线本身（lw=1.6）会被自己的标记吃掉，变成三条虚线带。点标记的信息在这个密度下已经没有了。
    d9 = win()
    ex.append({
        'n': 12, 'kind': 'lines', 'yfmt': 'pct0',
        'title': f"Core Comp by Region (ex. gas & FX), since {mlab(d9.index[0])}",
        'xlabels': [mlab(p) for p in d9.index], 'xstep': 3,
        'zero_line': True,          # PDF 里 ex_region_overlay 调了 axhline(0)，轴需含 0
        'src_extra': f'三条线都是公司披露的核心（除油汇）可比销售同比，'
                     f'{mlab(d9.index[0])}–{mlab(d9.index[-1])} 共 {len(d9)} 个月逐月无缺。'
                     f'与 Exhibit {"/".join(str(n) for n in _REGION_NS)} 是同样的三条序列，这里叠在一张图上是为了看'
                     f'<b>地区之间的相对次序与转向先后</b>，不是重复。'
                     f'（旧版本只画最近 25 个月并在标题里写 "last 25m"；'
                     f'那是画图时截的窗口，不是数据的边界。）',
        'series': [{'name': 'US', 'color': 'NAVY', 'values': L(d9['us_a'])},
                   {'name': 'Canada', 'color': 'MBLUE', 'values': L(d9['ca_a'])},
                   {'name': "Other Int'l", 'color': 'BLUE', 'values': L(d9['oi_a'])}],
    })

    # Ex 13 —— 美国 stacks
    ex.append(stack_ex(13, 'us_a', 'US Core Comp Growth Trends'))

    # Ex 14 —— 仓库数（全历史）
    # 2016-08 / 2017-08 / 2017-09 三个月的新闻稿未披露仓库数。这里不能 dropna：
    # dropna 会把这 3 个月从 x 轴上一并抹掉，剩下的点等距连成一条线 ——
    # Jun-16→Jan-17 的 7 个月与 Jan-17→Jul-17 的 6 个月在图上一样宽，
    # 「一年新开多少家」直接从图上读会偏，且页面无任何提示（违反 CONTRACT §5.3）。
    # 保留完整月度轴，缺失月由 L() 传 None，charts.js 的 lines 分支遇 null 抬笔断线。
    # 用 first/last_valid_index 而不是整段 df，是保留 dropna 原本「序列两端不留空」的效果
    # （本例首尾都有值，结果就是全部 127 行；将来该列若晚于 Dec-15 才开始也仍然正确）。
    wh = df.loc[df['wh_total'].first_valid_index():df['wh_total'].last_valid_index()]
    whv = wh['wh_total'].dropna()          # annot 的首末端点必须落在真实观测上
    v0, v1 = whv.iloc[0], whv.iloc[-1]
    # 缺失月份也从数据里读，不写死：图注声称「线在这三处断开」，那就必须真的是这三处。
    wh_gaps = [str(p) for p in wh.index[wh['wh_total'].isna()]]
    wh_src = ('未披露月份：' + ' / '.join(wh_gaps) +
              f'（共 {len(wh_gaps)} 处），线在这些位置断开，不做插值补点。'
              ) if wh_gaps else '全窗口逐月均有披露，线上没有断点。'
    # 本图画的是**全历史**，左端由 first_valid_index() 定，不过 win() —— 所以它可能
    # （今天就是）比本页那个窗口常量还早。这件事必须写在图上，否则页尾任何一句
    # 「本页图自 WIN_START 起」都会被这张图当场证伪，而读者只看得到矛盾、看不到原因。
    wh_src += (f'本图画全历史（{mlab(wh.index[0])} → {mlab(wh.index[-1])}，{len(wh)} 格），'
               f'左端取该列第一个有值的月份、不走 <code>win()</code> 的 {WIN_START} 左端'
               + (f'，因此比它早 {(pd.Period(WIN_START, "M") - wh.index[0]).n} 个月。'
                  if wh.index[0] < pd.Period(WIN_START, 'M') else '。'))
    ex.append({
        'n': 14, 'kind': 'lines', 'title': 'Warehouse Count', 'yfmt': 'int',
        'xlabels': [mlab(p) for p in wh.index], 'xstep': 6,
        'annot': f'{mlab(whv.index[0])}: {v0:.0f} → {mlab(whv.index[-1])}: {v1:.0f}',
        'src_extra': wh_src,
        'series': [{'name': 'Total warehouses', 'color': 'NAVY', 'values': L(wh['wh_total'])},
                   {'name': 'US & PR', 'color': 'BLUE', 'values': L(wh['wh_us'])}],
    })

    # Ex 15 —— 全公司 comp 的客单 / 客流分解（季度）
    #
    # ── 为什么是 grouped_bars ──────────────────────────────────────────────────
    # 9 个点。判据有三条，三条都指向并排柱：
    #   1. **不能用平滑/稠密图型**。9 个点上跑 Catmull-Rom 会在点与点之间造出根本没被
    #      观测过的形状，而这条序列一格是一个季度、相邻两格之间什么都没有。
    #      （引擎的 DENSE 那一族 —— gs_line / gs_line_avg / lines_endlabels /
    #      stacked_dual —— 因此一个都不考虑。）
    #   2. **不能用堆叠**。客单与客流是**相乘**的，堆起来就是在图上宣称它们相加等于 comp。
    #      量级上 a+b 确实很接近 (1+a)(1+b)−1（交叉项下面现算，只有零点几个 pp），
    #      但「很接近」不是恒等式，把一个近似画成一根柱子是最难被发现的那种错。
    #   3. `bar_line` 也不行：柱与线在同一根轴上，读者会去读「柱线间距」——
    #      本页 Exhibit 5 的图注刚教过读者那个间距是**差值**（净销售额 y/y − comp）。
    #      同一页上同一种视觉语言不能一处是减法一处是乘法。
    # 并排柱把三个量放在同一根轴上、各占各的位置，不暗示任何算术关系；
    # 关系由图注里的恒等式说，且当场实测。
    #
    # ── 为什么画报告口径这一路 ────────────────────────────────────────────────
    # 核心口径（剔除油汇）那张表是后来才加进 deck 的，最早的几个季度**整行不存在**。
    # 拿它当主腿会让一半的柱在图左边留洞，而读者第一反应是「那几个季度没数据」——
    # 实际是「那几个季度公司没报这个口径」。所以图上画报告口径（9 格满格），
    # 核心口径的信息一个字都没丢：客流在两个口径下**完全相同**（下面断言），
    # 所以两口径之差整个落在客单那一条腿上，逐季差多少印在图注里。
    #
    # ── 为什么通栏 ────────────────────────────────────────────────────────────
    # 因为要标数值，而 grouped_bars 的柱值标签是引擎里**唯一不过 thinLabels 的一路**
    # （gs_bar / stacked_dual / gs_line 那几支都抽稀，这一支直接 txt() 落笔、画上就不管）。
    # 半栏时一格 55.7px、三组各占 13.7px，而「+9.8%」这种标签实测 15.0px（按
    # build/chartscale.py 的 `_label_px`，与引擎同一把尺子）—— 相邻两个标签压 1.3px，
    # 谁也读不出来。通栏后一组 30.2px，富余一倍。所以这里的 `full` 不是版式偏好，
    # 是「要么通栏、要么别标数值」二选一的结果，两个数都写进图注。
    # Ex 15 —— 全公司 comp 的客单 / 客流分解（季度）
    #
    # ── 为什么是 grouped_bars ──────────────────────────────────────────────────
    # 9 个点。判据有三条，三条都指向并排柱：
    #   1. **不能用平滑/稠密图型**。9 个点上跑 Catmull-Rom 会在点与点之间造出根本没被
    #      观测过的形状，而这条序列一格是一个季度、相邻两格之间什么都没有。
    #      （引擎的 DENSE 那一族 —— gs_line / gs_line_avg / lines_endlabels /
    #      stacked_dual —— 因此一个都不考虑。）
    #   2. **不能用堆叠**。客单与客流是**相乘**的，堆起来就是在图上宣称它们相加等于 comp。
    #      量级上 a+b 确实很接近 (1+a)(1+b)−1（交叉项下面现算，只有零点几个 pp），
    #      但「很接近」不是恒等式，把一个近似画成一根柱子是最难被发现的那种错。
    #   3. `bar_line` 也不行：柱与线在同一根轴上，读者会去读「柱线间距」——
    #      本页 Exhibit 5 的图注刚教过读者那个间距是**差值**（净销售额 y/y − comp）。
    #      同一页上同一种视觉语言不能一处是减法一处是乘法。
    # 并排柱把三个量放在同一根轴上、各占各的位置，不暗示任何算术关系；
    # 关系由图注里的恒等式说，且当场实测。
    #
    # ── 为什么画报告口径这一路 ────────────────────────────────────────────────
    # 核心口径（剔除油汇）那张表是后来才加进 deck 的，最早的几个季度**整行不存在**。
    # 拿它当主腿会让一半的柱在图左边留洞，而读者第一反应是「那几个季度没数据」——
    # 实际是「那几个季度公司没报这个口径」。所以图上画报告口径（9 格满格），
    # 核心口径的信息一个字都没丢：客流在两个口径下**完全相同**（下面断言），
    # 所以两口径之差整个落在客单那一条腿上，逐季差多少印在图注里。
    #
    # ── 为什么通栏 ────────────────────────────────────────────────────────────
    # 因为要标数值，而 grouped_bars 的柱值标签是引擎里**唯一不过 thinLabels 的一路**
    # （gs_bar / stacked_dual / gs_line 那几支都抽稀，这一支直接 txt() 落笔、画上就不管）。
    # 9 格的图 `mrwin.layout_all` 根本不看（它的 min_n=21），所以这一步没有人替它算 ——
    # 下面自己按同一把尺子量：半栏 vs 通栏各自的一组柱有多宽、要印的标签有多宽。
    # 结论写进图注，**每个像素数都是现算的**（改组数、改格式器、改卡片宽度都会自己变）。
    _tk = load_tkt_q()
    # ⚠️ 页尾那几条注与页顶释义要用**同一份**装载结果（note_two_source /
    # note_ticket_traffic / compose_glossary / subtitle_for），别重新读一遍磁盘 ——
    # 读两遍就有两份可能不一致的真值。就地留个别名，装载现场只此一处。
    # 目标文件里没有那一层页尾注时，这一行删掉即可（它只是个别名）。
    _TKT_ALL = _tk
    _rep = _tk[_tk['basis'] == 'reported'].set_index('fq')
    _adj = _tk[_tk['basis'] == 'adjusted'].set_index('fq')
    if _rep.empty:
        raise SystemExit('cost_tkt_q.csv 里一行 basis=reported 都没有，Exhibit 15 画不出来')
    if not _rep.index.is_unique or not _adj.index.is_unique:
        raise SystemExit('cost_tkt_q.csv 同一 (fq, basis) 出现多行 —— 取哪一行是未定义的')

    # ── 断言 1：恒等式 (1+tkt)(1+trf)−1 == sales，逐格实测 ─────────────────────
    # 这是本图图注里最要紧的一句话的依据。**偏差多大是量出来的，不是抄公司口径**：
    # 只报「公司说它们相乘」而不核，等于把恒等式当信仰。
    # 阈值 0.15pp：三列都只有一位小数，四舍五入本身就能带来 ±0.05pp × 3 的量级。
    _ID_TOL = 0.15
    _TKT_REG = [('us', '美国'), ('ca', '加拿大'), ('oi', '其他国际'), ('tc', '全公司')]
    _id_dev, _cross = [], []
    for _bn, _bd in (('reported', _rep), ('adjusted', _adj)):
        for _p, _zh in _TKT_REG:
            _im = ((1 + _bd[f'{_p}_tkt'] / 100) * (1 + _bd[f'{_p}_trf'] / 100) - 1) * 100
            for _fq, _v in (_im - _bd[f'{_p}_sales']).dropna().items():
                _id_dev.append((abs(float(_v)), _fq, _bn, _zh))
            for _fq in _bd.index:
                _cross.append((abs(float(_bd.at[_fq, f'{_p}_tkt'] * _bd.at[_fq, f'{_p}_trf']) / 100),
                               _fq, _bn, _zh))
    if not _id_dev:
        raise SystemExit('客单×客流恒等式一格都没验上 —— 图注里那句话没有依据，不出图')
    _worst = max(_id_dev)
    if _worst[0] > _ID_TOL:
        raise SystemExit(
            f'客单 × 客流的恒等式在 {_worst[1]}（{_worst[2]}，{_worst[3]}）偏离 '
            f'{_worst[0]:.2f}pp，超过 {_ID_TOL}pp —— 图注声称这三个数互相咬得住，'
            f'咬不住就别出图')
    _xmax = max(_cross)       # 交叉项 tkt×trf：把「相加」当近似用时最多差这么多

    # ── 断言 2：客流在两个口径下完全相同（公司只调价、不调客流）────────────────
    # 图注拿这条推出「两口径之差整个落在客单上」。它是从数据里读出来的，不是从公司
    # 文案里读出来的 —— 哪天公司改了做法，这里当场停机，而不是让那句话变成假话。
    _both = _adj.index.intersection(_rep.index)
    _trf_gap = max((abs(float(_adj.at[f, f'{p}_trf'] - _rep.at[f, f'{p}_trf']))
                    for f in _both for p, _ in _TKT_REG), default=0.0)
    if _trf_gap > 1e-9:
        raise SystemExit(f'核心口径与报告口径的客流出现 {_trf_gap:.2f}pp 的差 —— '
                         f'Exhibit 15 图注里「油汇只调价、不调客流」那句话不再成立')

    # ── 一格一根柱：客单与客流叠在同一根柱上，菱形标 comp ─────────────────────
    # （所有者 2026-09-03 指令：「把 ticket 和 traffic 两个因素都放在一根柱子上」。
    #  原来是三根并排柱。）
    #
    # 图型选 `bridge_bar` 而不是 `stacked_dual`，两条硬理由：
    #   1. **客单会是负的**（FY24Q4 全公司 −0.9%，同期客流 +6.4%）。`stacked_dual` 的
    #      柱顶画的是**正向包络**，那一格会停在 +6.4，而 comp 是 +5.4 —— 柱顶不是
    #      合计，读者按柱顶读就错了。`bridge_bar` 正的往上堆、负的往下堆，另用菱形
    #      标净额，这一格 comp 才有地方落。
    #   2. `stacked_dual` 的段内数值标签走的是引擎里写死 0 位小数、不带单位的格式器，
    #      +7.3% 会印成「7」；`bridge_bar` 干脆一个数值标签都不画，反而不会印错值
    #      （逐格读数走右上角「表格」视图，当期读数写进标题）。
    #
    # ⚠️ 三段之和必须**恰好**等于 comp，而客单与客流是**相乘**的：
    #     (1 + 客单)(1 + 客流) − 1 = comp
    # 所以两条腿相加不等于 comp，差的是交叉项。做法不是把它藏起来（那才是最难被
    # 发现的错），而是把差额单列成第三段「残差」，定义就是 comp −（客单 + 客流）——
    # 它同时装着交叉项与两处一位小数的四舍五入。这样图上三段之和与公司披露的 comp
    # 在显示精度上逐格相等，两条腿也仍然逐字是申报里那个数（没有被摊过、没有被换算过）。
    _TKT_X = fq_xlabels(_rep.index, 'Exhibit 15')
    _tkt_res = [round(float(_rep.at[f, 'tc_sales'] - _rep.at[f, 'tc_tkt']
                            - _rep.at[f, 'tc_trf']), 1) or 0.0 for f in _rep.index]
    _TKT_G = [('Average transaction (ticket)', 'tc_tkt', 'BLUE'),
              ('Shopping frequency (traffic)', 'tc_trf', 'MBLUE')]
    _tkt_vals = {c: L(_rep[c]) for _, c, _ in _TKT_G}
    _tkt_vals['tc_sales'] = L(_rep['tc_sales'])
    _tkt_nul = {c: sum(v is None for v in a) for c, a in _tkt_vals.items()}
    if any(_tkt_nul.values()):
        raise SystemExit(f'Exhibit 15 的报告口径各腿有缺格（{_tkt_nul}）—— '
                         f'`bridge_bar` 遇 null 只是不画那一段，**菱形照画**，'
                         f'于是可见的几段够不到菱形，而没有任何东西会报错')
    # 恒等式硬校验（docs/CHART_KINDS.md §3.15：引擎不会替你求和，Python 侧要断言）
    _res_bad = [(f, round(float(_rep.at[f, 'tc_tkt'] + _rep.at[f, 'tc_trf']) + r
                          - float(_rep.at[f, 'tc_sales']), 6))
                for f, r in zip(_rep.index, _tkt_res)]
    _res_bad = [t for t in _res_bad if abs(t[1]) > 1e-9]
    if _res_bad:
        raise SystemExit(f'Exhibit 15 三段之和 ≠ 菱形（comp）：{_res_bad} —— '
                         f'柱高与菱形对不上，而引擎不会告诉你')
    # 残差在图注里被称作「一根发丝」。它要是真的长起来，那句话就成了假话。
    _res_max = max(abs(r) for r in _tkt_res)
    if _res_max > 0.5:
        raise SystemExit(f'Exhibit 15 的残差段最大已到 {_res_max:.2f}pp —— '
                         f'图注里「细到几乎看不见」那句话不再成立，先改措辞再上线')
    # 季度轴必须逐格相接：并排柱把相邻两格画成挨着的，跳掉一个季度就是
    # CONTRACT §5 第 3 条点名的「不可比的相邻期画成连续序列」。
    _qn = [int(f[2:4]) * 4 + int(f[-1]) for f in _TKT_X]
    if any(b - a != 1 for a, b in zip(_qn, _qn[1:])):
        raise SystemExit(f'客单/客流的季度序列不连续或没排序：{_TKT_X}')

    # ── 图注要用的读数，全部现算 ───────────────────────────────────────────────
    # (a) 这张图的横轴与全页月度轴不是同一张网格：一格几周，从分部季度表现读
    _sgw = load_seg_q()
    _sgw = _sgw[_sgw['scope'] == 'Q'].set_index('fq')['weeks']
    _miss_w = [f for f in _rep.index if f not in _sgw.index]
    if _miss_w:
        raise SystemExit(f'分部季度表里查不到 {_miss_w} 的周数 —— '
                         f'Exhibit 15 图注要拿它说明「一格是几周」，缺了这句话就得改写')
    _wq = [int(_sgw[f]) for f in _rep.index]
    _wm = sorted({int(w) for w in df['weeks'].dropna()})       # 月度轴一格是 4 或 5 周
    # (b) 序列为什么只有 9 格：两张表各自的第一个季度 + 核心口径缺的那几季
    _adj_gap = [f for f in _rep.index if f not in _adj.index]
    # (c) 报告 − 核心：客流相同，所以整个差落在客单上（逐季印出来）
    _wedge = '；'.join(
        f'{f} 客单 {float(_rep.at[f, "tc_tkt"]):+.1f}% vs 核心 {float(_adj.at[f, "tc_tkt"]):+.1f}%'
        f'（{float(_rep.at[f, "tc_tkt"] - _adj.at[f, "tc_tkt"]):+.1f}pp）'
        for f in _rep.index if f in _adj.index)
    # (d) MD&A 那条独立对账腿：两份申报对不对得上
    # 指认同一页别的图时图号**现读已装配的 payload**，不写字面量（本页因为重排图序
    # 翻过车，见页尾 WINDOW_NOTE 那段的三次返工）。指不到就把那半句去掉，不留空号。
    _wedge_n = next((e['n'] for e in ex if 'Gas & FX Wedge' in str(e.get('title'))), None)
    _MDNA = [('mdna_tc_tkt', 'tc_tkt', '客单'), ('mdna_tc_frq', 'tc_trf', '客流')]
    _md_rows = sorted({f for c, _, _ in _MDNA for f in _rep[c].dropna().index})
    _md_dev = [(abs(float(_rep.at[f, c] - _rep.at[f, k])), f, zh, float(_rep.at[f, c]),
                float(_rep.at[f, k])) for c, k, zh in _MDNA for f in _rep[c].dropna().index]
    _md_txt = ('本图这 9 个季度里 MD&A 一个读数都没有，这条对账腿本期是空的。'
               if not _md_dev else
               f'{len(_md_rows)}/{len(_rep)} 个季度另有一条<b>独立对账腿</b>：'
               f'同一季度的 10-Q / 10-K 正文（MD&A）也用<b>整数百分比</b>报了全公司的客单与客流，'
               f'与 8-K 那份 deck 是两份不同的申报。{len(_md_dev)} 个可比读数逐个对下来，'
               f'差最大的是 {max(_md_dev)[1]} 的{max(_md_dev)[2]}'
               f'（deck {max(_md_dev)[4]:+.1f}% vs MD&A {max(_md_dev)[3]:+.0f}%，'
               f'差 {max(_md_dev)[0]:.1f}pp），全部落在整数四舍五入的半宽 0.5pp 之内 —— '
               f'两份申报没有互相矛盾。')

    # ── (e) 段那几个读数，全部现算 ─────────────────────────────────────────────
    # 交叉项：本图画的那条（全公司、报告口径），以及「三地区 × 两口径」全体的最大值。
    # 两个都报，是因为读者会拿本图去理解**整套**披露，而全体的那个更大。
    _xt = lambda a, b: abs(float(a) * float(b) / 100.0)
    _x_tc, _x_tc_f = max(((_xt(_rep.at[f, 'tc_tkt'], _rep.at[f, 'tc_trf']), f)
                          for f in _rep.index))
    _ZH_G = {'us': '美国', 'ca': '加拿大', 'oi': '其他国际', 'tc': '全公司'}
    _x_all, _x_all_f = max(
        (_xt(row[f'{g}_tkt'], row[f'{g}_trf']),
         f'{row["fq"]}·{_ZH_G[g]}·{"报告" if row["basis"] == "reported" else "核心"}口径')
        for _, row in _tk.iterrows() for g in _ZH_G
        if pd.notna(row[f'{g}_tkt']) and pd.notna(row[f'{g}_trf']))
    # 四舍五入那一半 = 残差 − 交叉项（同一格里两者之差就是进位造成的部分）
    _x_rnd = max(abs(r - _xt(_rep.at[f, 'tc_tkt'], _rep.at[f, 'tc_trf']) *
                     (1 if float(_rep.at[f, 'tc_tkt']) * float(_rep.at[f, 'tc_trf']) >= 0 else -1))
                 for f, r in zip(_rep.index, _tkt_res))
    _res_zero = [f for f, r in zip(_TKT_X, _tkt_res) if abs(r) < 0.05]
    # 残差在图上有多细：报「占纵轴量程的百分之几」，不报像素。
    # 报像素就要复算引擎的**纵向**几何，而 chartscale 只复算了横向（_margins）——
    # 再抄一份高度算式就是仓里的第 N 份副本，engine_kinds.md 那条「量程逻辑有三份
    # 副本、改一处要同改另两处」的警告说的就是这种事。比值与画布高无关，够用。
    # 量程本身与引擎同一条算式：bridge_bar 的 y0/y1 = 正负包络各外扩 0.16×range。
    _env = [sum(v for v in (float(_rep.at[f, 'tc_tkt']), float(_rep.at[f, 'tc_trf']), r) if v > 0)
            for f, r in zip(_rep.index, _tkt_res)]
    _envn = [sum(v for v in (float(_rep.at[f, 'tc_tkt']), float(_rep.at[f, 'tc_trf']), r) if v < 0)
             for f, r in zip(_rep.index, _tkt_res)]
    _y1, _y0 = max(_env + _tkt_vals['tc_sales']), min(_envn + _tkt_vals['tc_sales'])
    _rng = (_y1 - _y0) * 1.32 or 1.0          # 上下各 0.16 的留白
    _res_share = _res_max / _rng
    _neg_txt = ('本期这 %d 格里 %s 的客单为负' % (
        len(_tkt_res), '、'.join(f for f, v in zip(_TKT_X, _tkt_vals['tc_tkt']) if v < 0))
        if any(v < 0 for v in _tkt_vals['tc_tkt']) else '本期九格的两条腿都为正')

    _bs = _rep.iloc[-1]                       # 当期那一格，标题与 annot 都引它
    ex.append({
        'n': 15, 'kind': 'bridge_bar',
        # 不给 full：旧版那条「必须通栏」的理由是 grouped_bars 的柱值标签不过抽稀、
        # 半栏装不下 —— 而 bridge_bar **一个数值标签都不画**，那笔账连被算的对象都没有了。
        # 一格一根柱，半栏放得下。
        #
        # `fmt` 是**载荷字段**：bridge_bar 的表格视图与 tooltip 走 `ex.fmt || ex.yfmt`，
        # 而且各段与净额都走它 —— 只给 yfmt 的话表格里会退成 pct0，残差那一段
        # （0.1pp 量级）会被四舍五入成 0.0%，正好把本图要交代的那件事抹掉。
        # 不给 `label_fmt` / `bar_labels`：bridge_bar 只在截轴时用 label_fmt，本图没截轴，
        # 给了就是一个谁都不读的死键。
        'fmt': 'pct1', 'yfmt': 'pct0',
        # xrot 交回引擎自适应（n=9 → 45°）：写死 0° 时 375px 视口下九个「FY24Q3」
        # 首尾相压，visual_qa 记了 8 条 🟡。判据不能只在开发用的那个视口上成立。
        'xstep': 1,
        'title': SEC_TKT + 'Comp = ticket × traffic, decomposed additively '
                           '(total company, reported basis, quarterly); '
                 f'{_TKT_X[-1]}: comp {float(_bs["tc_sales"]):+.1f}% = ticket '
                 f'{float(_bs["tc_tkt"]):+.1f}% + traffic {float(_bs["tc_trf"]):+.1f}% '
                 f'+ residual {_tkt_res[-1]:+.1f}%',
        'ylab': 'y/y (%)',
        'xlabels': _TKT_X,
        # 图上不印任何数值（bridge_bar 不画数据标签），所以当期的乘法恒等式写进 annot：
        # 读者至少能在图上把「相乘不是相加」这件事对一遍。
        'annot': (f'{_TKT_X[-1]}: (1{float(_bs["tc_tkt"]) / 100:+.4f}) × '
                  f'(1{float(_bs["tc_trf"]) / 100:+.4f}) − 1 = '
                  f'{((1 + float(_bs["tc_tkt"]) / 100) * (1 + float(_bs["tc_trf"]) / 100) - 1) * 100:.2f}%'),
        'stacks': [{'name': nm, 'color': cl, 'values': _tkt_vals[c]} for nm, c, cl in _TKT_G]
                  + [{'name': 'Residual: comp − (ticket + traffic) — cross term + rounding',
                      'color': 'GRAY', 'values': _tkt_res}],
        # 菱形 = 公司申报的 comp 本身，不是三段求和的结果。显式给：省略时引擎会替我们
        # 求和，那样「三段之和 ≡ 披露值」就成了自证，上面那道断言也就白写了。
        'net': {'name': 'Reported comp (y/y, as filed)', 'values': _tkt_vals['tc_sales']},
        'net_color': 'INK',
        'src_extra':
            # ── 出处 ──
            f'<b>本图的数据源与本页其余各图不同</b>：客单与客流月度新闻稿一个字都不报'
            f'（见页尾「客流与品类」那一条），本图取自 Costco 季度业绩 8-K 所附的 '
            f'<b>Exhibit 99.2「Supplemental Information」</b>，申报人 CIK '
            f'<code>{SEC_CIK}</code>，{len(_rep)} 个季度共 '
            f'{int(_rep["accession"].nunique())} 份申报（accession 号在 '
            f'<code>series/cost_tkt_q.csv</code> 里逐行可查）。'
            # ── (a) 横轴：与全页不是同一张网格 ──
            f'<b>⚠️ 这张图的横轴是财季，不是本页其余各图的零售月 —— 两张网格不一样。</b>'
            f'本图一格是 {"／".join(str(w) for w in sorted(set(_wq)))} 周'
            f'（{_TKT_X[0]}–{_TKT_X[-1]} 逐格 {"、".join(str(w) for w in _wq)} 周，'
            f'合计 {sum(_wq)} 周），而本页月度图一格是 '
            f'{"／".join(str(w) for w in _wm)} 周（4-4-5 零售日历）。'
            f'一格不是同一个东西，<b>本图的柱不能跟任何一张月度图的柱并排读</b>；'
            f'两张网格之间也没有一条现成的换算 —— 要对，只能拿整季对整季。'
            # ── (b) 只有 9 格，为什么 ──
            f'<b>序列只有 {len(_rep)} 个季度，这是数据下限不是画图时截的窗口</b>：'
            f'公司是从 {_rep["filed"].iloc[0]} 报送的那份 8-K（{_TKT_X[0]}）起才在 '
            f'Exhibit 99.2 里放这张分解表的，更早的季度<b>没有这个披露</b>'
            f'（是公司没报，不是本页没抓）。'
            + (f'剔除汽油与汇率的<b>核心口径</b>那张子表加得更晚：{len(_adj)} 个季度有，'
               f'{"、".join(_adj_gap)} 这 {len(_adj_gap)} 个季度<b>整行不存在</b>'
               f'（是没披露，不是 0；本页从不补零）。' if _adj_gap else
               f'核心口径那张子表这 {len(_adj)} 个季度都有。')
            # ── (c) 相乘不是相加 ──
            + f'<b>⚠️ 客单与客流是<u>相乘</u>的，不是相加</b>：'
              f'(1 + 客单/100) × (1 + 客流/100) − 1 ＝ 可比销售/100。'
              f'这条恒等式在构建期<b>逐格实测</b>过 —— {len(_id_dev)} 个'
              f'「季度 × 地区 × 口径」读数里最大偏差 {_worst[0]:.2f}pp'
              f'（{_worst[1]}，{_worst[3]}，{_worst[2]} 口径），与三列都只有一位小数的'
              f'四舍五入同量级。本期 {_TKT_X[-1]} 的算式：'
              f'(1{float(_rep["tc_tkt"].iloc[-1]) / 100:+.4f}) × '
              f'(1{float(_rep["tc_trf"].iloc[-1]) / 100:+.4f}) − 1 = '
              f'{((1 + float(_rep["tc_tkt"].iloc[-1]) / 100) * (1 + float(_rep["tc_trf"].iloc[-1]) / 100) - 1) * 100:.2f}%'
              f'，公司披露 {float(_rep["tc_sales"].iloc[-1]):.1f}%。'
              f'（本图怎么把这条<b>乘法</b>恒等式画成一根<b>加法</b>的柱、'
              f'差额去了哪里，见下面「怎么读这根柱」那一段。）'
            # ── 报告 vs 核心：差全在客单上 ──
            + (f'<b>图上画的是报告口径</b>（9 格满格）。核心口径的信息一个字都没丢：'
               f'公司调的只是价，<b>客流在两个口径下逐格完全相同</b>（构建期实测差 '
               f'{_trf_gap:.2f}pp），所以两个口径之差整条落在客单上 —— {_wedge}。'
               + (f'这与 Exhibit {_wedge_n} 那张油汇楔子图问的是同一件事，只是频率不同。'
                  if _wedge_n else '')
               if _wedge else '')
            # ── (d) 独立对账腿 ──
            + _md_txt
            # ── (e) 三段怎么读、那根发丝是什么 ──
            + f'<b>怎么读这根柱</b>：一格一根柱，客单与客流叠在同一根上（负的往下堆 —— '
              f'{_neg_txt}），<b>黑色菱形是公司申报的 comp 本身</b>，不是三段求和的结果；'
              f'三段之和与菱形在构建期逐格核过，差恒为 0（对不上就整页失败）。'
              f'柱顶<b>不等于</b> comp：有负段的那一格柱顶停在正向包络上，'
              f'comp 要看菱形。'
            + f'<b>⚠️ 客单与客流是<u>相乘</u>的，两条腿相加不等于 comp</b>：'
              f'(1 + 客单)(1 + 客流) − 1 = comp。差额就是图上那条灰色的<b>残差</b>段，'
              f'它按定义 = comp −（客单 + 客流），里面装着两样东西：交叉项'
              f'（本图这条序列上最大 {_x_tc:.2f}pp @{_x_tc_f}；把三个地区、两个口径一起算，'
              f'最大 {_x_all:.2f}pp @{_x_all_f}）与两处一位小数的四舍五入'
              f'（最大 {_x_rnd:.2f}pp）。本期残差 {_tkt_res[-1]:+.1f}pp。'
            + f'<b>残差细到几乎看不见，而这正是本图的一个结论</b>：'
              f'{len(_tkt_res)} 格里最大的一格也只有 {_res_max:.1f}pp，'
              f'不到本图纵轴量程的 {_res_share:.1%}；'
            + (f'{"、".join(_res_zero)} 这 {len(_res_zero)} 格四舍五入后是 0.0pp，'
               f'引擎索性不画那一段。' if _res_zero else '没有一格恰好归零。')
            + f'也就是说「把客单与客流加起来当 comp」在这条序列上误差不到 '
              f'{_res_max:.1f}pp —— 但它是<b>近似</b>不是恒等式，所以图上把差额画出来，'
              f'而不是让两条腿假装加得起来。'
            + f'<b>图上不印任何数值</b>：本图型不画数据标签。当期读数写在标题里、'
              f'乘法恒等式写在图内注解里，逐格读数请走右上角「表格」视图'
              f'（那一路按本图的 <code>pct1</code> 格式印，残差那 0.1pp 不会被抹掉）。',
    })

    # 数据源那条页尾注要把「SEC 申报腿」与「月度新闻稿腿」分开点名，名单只准在建图
    # 现场登记（main() 开头的 `SEC_EX = []`），不写死图号。
    # 本图**只**进 SEC_EX：它画的是同比（不是占比，所以不进 SHARE_EX），
    # 口径是可比销售同比（不是总收入，所以不进 REV_EX）。
    # ⚠️ 若目标文件里还没有 SEC_EX 这张登记表，把这一行删掉；留着会 NameError。
    SEC_EX.append(ex[-1]['n'])            # 出自 8-K 的 EX-99.2 补充资料

    # ══════════════════════════════════════════════════════════════════════════════
    # Ex 16 —— 开业年份 × 财年：均店销售矩阵（公司自己披露的新店爬坡曲线）
    #
    # 贴在 build/cost.py 的 main() 里、Exhibit 15（另一位 agent 的 ticket/traffic）之后、
    # 「── 图号连号硬护栏（照 build/ibkr.py 的 `_ens`）──」那一段**之前**。
    # 缩进 4 格（main() 的函数体），与上面的 ex.append(...) 平级。
    # 位置不能再往后：`_ens` 那道护栏与末尾核对表的 `'n': _ens[-1] + 1` 都要数到本图，
    # 贴到护栏之后，护栏会判 2..15 连号通过、而核对表拿到 16 号，与本图当场同号。
    #
    # 这是全页**唯一一张 100% 公司披露值的开店经济图**：数字一个都不是我们算的，
    # 全部来自 10-K 里 "Item 6—Reserved" 前那张 "Average Sales Per Warehouse*
    # (Sales In Millions)" 图（fetch/cost_sec.py 的 build_cohort 解析）。所以标题里
    # **不许出现 Implied**（CONTRACT §5 第 1 条管的是推导值；把披露值也标上 Implied，
    # 这个标记就不再有区分力了）。真正的推导值在下一张 Exhibit 17。
    #
    # 数据源与本页其余每一张图都不同（那些是月度销售新闻稿），所以 src_extra 里
    # **必须**把这件事说出来：卡片下方的 Source 行是全页共用的 SRC 常量
    # （"Company data (Costco monthly sales press releases)"），不改口就是假的。
    # ⚠️ 页尾 notes[0]「数据源（唯一）」那条也会因此变成假话，见本文件末尾的可选补丁。
    #
    # 只用**一个 vintage**（最新的那一份 10-K）。理由不是省事：聚合行的含义逐年在变
    # （FY2025 那份是 "2016 & Before"、FY2024 那份是 "2015 & Before"），把两份的行
    # 并排读等于把两个不同的仓店池画成同一行。判据写成现算 —— 明年多一份 10-K，
    # 本图自己会换到新的 vintage，图注里那些「上一份印的是什么」也跟着变。
    # ══════════════════════════════════════════════════════════════════════════════
    _COH_CSV = os.path.join(SERIES_DIR, 'cost_cohort.csv')
    _FY_CSV = os.path.join(SERIES_DIR, 'cost_fy.csv')
    for _p in (_COH_CSV, _FY_CSV):
        if not os.path.exists(_p):
            raise SystemExit(f'找不到源数据: {_p}（Exhibit 16/17 用的是 10-K 年度表，'
                             f'不是月度新闻稿）')
    _coh = pd.read_csv(_COH_CSV)
    _fyd = pd.read_csv(_FY_CSV)
    for _c, _cols, _f in ((_coh, ['vintage', 'cohort', 'n_whses', 'fiscal_year',
                                  'avg_sales_musd'], 'cost_cohort.csv'),
                          (_fyd, ['fy', 'weeks', 'net_sales_mn', 'wh_total'], 'cost_fy.csv')):
        _m = [c for c in _cols if c not in _c.columns]
        if _m:
            raise SystemExit(f'series/{_f} 缺列 {_m}')
    # 年度表按财年建索引，两块（Ex16 / Ex17）共用；'FY2025' → 2025
    _fyd = _fyd.assign(y=_fyd['fy'].str.slice(2).astype(int)).set_index('y').sort_index()

    def _cohort_footnote():
        """按路径加载 fetch/cost_sec.py，取那张图的脚注原文 COHORT_FOOTNOTE。

        不把这句话抄进本文件：它是 10-K 图下的**原文**，抄一份就有了两个真源 ——
        公司改了措辞时 fetch 那边会打 WARN（build_cohort 末尾比对过），
        这边的副本却会一声不响地继续印旧话。同 build/ibkr.py 的 load_pipeline()：
        管道文件在 fetch/ 下，本脚本跑起来时 sys.path[0] 是 build/，裸 import 找不到。
        """
        import importlib.util
        p = os.path.join(ROOT, 'fetch', 'cost_sec.py')
        if not os.path.exists(p):
            raise SystemExit(f'找不到 {p} —— Exhibit 16 图注要引的脚注原文只有那里有')
        spec = importlib.util.spec_from_file_location('cost_sec', p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.COHORT_FOOTNOTE

    # ── vintage：取最新的一份 10-K，并记住上一份，图注要拿它说「聚合行会变」──
    _COH_VS = sorted(_coh['vintage'].unique(), key=lambda v: int(v[2:]))
    if len(_COH_VS) < 1:
        raise SystemExit('cost_cohort.csv 里一个 vintage 都没有')
    _COH_V, _COH_PREV = _COH_VS[-1], (_COH_VS[-2] if len(_COH_VS) > 1 else None)
    _cm = _coh[_coh['vintage'] == _COH_V]
    _COH_YRS = sorted(int(y) for y in _cm['fiscal_year'].unique())

    def _agg_of(v):
        """某个 vintage 的聚合行（"YYYY & Before"）→ (行名, 家数)；没有就 (None, None)。"""
        s = _coh[(_coh['vintage'] == v) & (_coh['cohort'].str.contains('&'))]
        return (None, None) if s.empty else (s['cohort'].iloc[0], int(s['n_whses'].iloc[0]))

    # 聚合行的标签里带 &（「2016 & Before」），而下面 src_extra / note 走的是 innerHTML：
    # HTML5 对孤立的 & 是宽容的（照literal 渲），但那是「碰巧没坏」，标签一旦变成
    # 「2016 &amp; Prior」之类就会被吃掉。转义一次，成本为零。
    _hesc = lambda s: str(s).replace('&', '&amp;')
    _AGG_LAB, _AGG_N = _agg_of(_COH_V)
    _PREV_LAB, _PREV_N = _agg_of(_COH_PREV) if _COH_PREV else (None, None)

    def _ckey(c):
        """行序：聚合行最老 → 逐个开业年份 → Totals 收尾（engine_kinds §1 要求从旧到新）。"""
        if c == 'Totals':
            return (2, 0)
        return (0, int(c.split()[0])) if '&' in c else (1, int(c))

    _COH_LABS = sorted(_cm['cohort'].unique(), key=_ckey)
    _cval = {(r.cohort, int(r.fiscal_year)): int(r.avg_sales_musd) for r in _cm.itertuples()}
    _cnt = {c: int(_cm[_cm['cohort'] == c]['n_whses'].iloc[0]) for c in _COH_LABS}
    _coh_matrix = [[_cval.get((c, y)) for y in _COH_YRS] for c in _COH_LABS]

    # ── 三条硬校验（CONTRACT §5 第 5 条：算不对就整页失败，绝不静默上线）──────────
    # 这张图是**右对齐**读出来的：财年表头印在数据行**下面**，每行的值向右对齐、末位
    # 属于当年（见 fetch/cost_sec.py 的 _cohort_parse）。串一格照样像模像样，所以
    # 这三条不是形式主义 —— 它们是唯一能发现「整表左移一格」的东西。
    _COH_TOT = 'Totals'
    if _COH_TOT not in _cnt:
        raise SystemExit(f'{_COH_V} 矩阵没有 Totals 行')
    _data_labs = [c for c in _COH_LABS if c != _COH_TOT]
    _nsum = sum(_cnt[c] for c in _data_labs)
    if _nsum != _cnt[_COH_TOT]:
        raise SystemExit(f'{_COH_V} 各队列家数合计 {_nsum} ≠ Totals 的 {_cnt[_COH_TOT]}')
    _wa_dev, _den_ok = {}, 0
    for _y in _COH_YRS:
        _num = sum(_cnt[c] * _cval[(c, _y)] for c in _data_labs if (c, _y) in _cval)
        _den = sum(_cnt[c] for c in _data_labs if (c, _y) in _cval)
        if (_COH_TOT, _y) not in _cval or not _den:
            raise SystemExit(f'{_COH_V} 矩阵 FY{_y} 列缺 Totals 或分母为 0')
        # ① Totals 行 = 按家数加权的均值。容差 1.0 与 fetch/cost_sec.py 同源：格值本身
        #    已经被公司四舍五入到整百万，复算的加权均值因此必然带零点几的残差
        #    （本期最大一处 FY2023 差 0.74）。收紧到 0.5 会把公司自己的取整判成串位。
        _dev = abs(_num / _den - _cval[(_COH_TOT, _y)])
        _wa_dev[_y] = _dev
        if _dev > 1.0:
            raise SystemExit(f'{_COH_V} 矩阵 FY{_y} 列：按家数加权均值 {_num / _den:.2f} 与'
                             f'印出来的 Totals {_cval[(_COH_TOT, _y)]} 差 {_dev:.2f} > 1 —— '
                             f'多半是右对齐串了一列')
        # ② 每一列的分母（当年已开业队列的家数之和）必须等于当年披露的**期末**仓店数。
        #    这条同时钉死了两件事：矩阵没有串行，以及「均店销售的分母是期末家数」这个
        #    口径判断有据可依（Ex16/17 的图注都要引它）。
        if _y not in _fyd.index:
            raise SystemExit(f'series/cost_fy.csv 没有 FY{_y} —— 无法核对矩阵 FY{_y} 列的分母')
        _wh = int(_fyd.at[_y, 'wh_total'])
        if _den != _wh:
            raise SystemExit(f'{_COH_V} 矩阵 FY{_y} 列的分母 {_den} ≠ 当年披露期末仓店数 {_wh}')
        _den_ok += 1
    # ③ 空格子只许出现在队列开业年之前。中间漏一格会被热力图画成浅灰，读者只会
    #    理解成「那年没数据」，而真相是我们解析漏了一格。
    for _c in _COH_LABS:
        _start = min(_COH_YRS) if (_c == _COH_TOT or '&' in _c) else int(_c)
        _want = {y for y in _COH_YRS if y >= _start}
        _have = {y for y in _COH_YRS if (_c, y) in _cval}
        if _want != _have:
            raise SystemExit(f'{_COH_V} 矩阵「{_c}」行的有值年份 {sorted(_have)} '
                             f'与开业年推出来的 {sorted(_want)} 对不上')

    # ── 图注里要印的量，一个都不写死 ────────────────────────────────────────────
    _COH_LAST = _COH_YRS[-1]
    _coh_newest = max((c for c in _data_labs if '&' not in c), key=lambda c: int(c))
    _first_new = _cval[(_coh_newest, int(_coh_newest))]          # 最新队列的首年（年化）值
    _sys_avg = _cval[(_COH_TOT, _COH_LAST)]                      # Totals 行最新一格
    _n_null = sum(1 for r in _coh_matrix for v in r if v is None)
    # 口径缺口：把整张图按家数还原成系统销售额，与当年合并净销售额比
    _coh_impl = {y: sum(_cnt[c] * _cval[(c, y)] for c in _data_labs if (c, y) in _cval)
                 for y in _COH_YRS}
    _coh_gap = {y: 1 - _coh_impl[y] / float(_fyd.at[y, 'net_sales_mn']) for y in _COH_YRS}
    # ── 单位经济性（Exhibit 17 的全部算术）提前到这里算 ──────────────────────
    # 它本来长在 Exhibit 17 那一块里。搬上来是因为所有者要把「盈亏平衡销售额」
    # 写进本图 Totals 那一行（2026-09-03 指令），于是 16 与 17 必须**共用同一份**
    # 计算结果 —— 各算一遍的分叉长这样：两张图上的 $272mn 不是同一个数，而页面
    # 不会报错。它读的是 _fyd（年度表）与 _cval（本块刚解出来的队列矩阵），
    # 两样在这里都已经就位。
    # ── 每年一份口径无关的比率 + 两个均店销售口径 ────────────────────────────────
    def _e17_calc(y):
        r = _fyd.loc[y]
        ns = float(r.net_sales_mn)
        g = (ns - float(r.merch_cost_mn)) / ns          # 商品毛利率（对净销售额）
        s = float(r.sga_mn) / ns                        # SG&A 率（已含开办费）
        m = float(r.memb_fee_mn) / ns                   # 会员费率
        wh = float(r.wh_total)
        coh = _cval.get((_COH_TOT, y))                  # 队列表 Totals 行（披露的均店销售）
        # 盈亏平衡 = 覆盖 SG&A 需要的销售额 ÷ 单位销售额的贡献率。
        # 上沿：贡献只算商品毛利 g（一分会员费都不给这家店）。
        # 下沿：把会员费按公司平均费率 m 记进贡献（g + m）。两者都是**比率**，与均店
        # 销售的口径无关 —— 折成金额时才需要挑一个口径，见 note。
        return {
            'ns': ns, 'g': g, 's': s, 'm': m, 'wh': wh, 'coh': coh,
            'memb': float(r.memb_fee_mn), 'gp': ns - float(r.merch_cost_mn),
            'sga': float(r.sga_mn), 'oi': float(r.op_income_mn),
            'hi': s / g, 'lo': s / (g + m),
            'ns_wh': ns / wh,
            'first': _cval.get((str(y), y)),            # 当年新开队列的首年（年化）销售
        }

    # 窗口 = series/cost_fy.csv 里的**全部**财年（本期 FY2016 起，所有者 2026-09-03 指令：
    # 「ex17 时间维度从 2016 年开始算」）。不写死起点年：那张 CSV 的左端由
    # fetch/cost_sec.py 的 FY_FIRST 定（再往前 XBRL 就没有分国家仓店数与
    # 净销售额/会员费拆分了），在这里再写一个 2016 只会有两处可以互相说谎。
    _E17_YS = [int(y) for y in _fyd.index]
    # ── C 段（分部经营利润）有一条口径断点，必须硬拦，不能只写在注里 ──────────────
    # Costco 在 FY2022 10-K 里说「Effective for fiscal 2022, stock-based compensation
    # was allocated to the segments … Operating income was restated in each of the
    # segments for all prior periods」，但它**只呈现了 FY2022/2021/2020 三年** ——
    # FY2019 及更早从来没有被重述过。series/cost_fy.csv 的 `seg_oi_basis` 记着每一年落在
    # 哪一侧（pre-sbc-alloc / sbc-alloc）。两侧混在一张表里画趋势，会读出一段纯属
    # 股权激励改分摊造成的假拐点（实测：其他国际 FY19 3.83% → FY20 3.76%，看着像下滑）。
    # 合并口径的 `op_income_mn` 不受影响 —— 断的只是分部的拆法。
    _E17_BAS = {y: str(_fyd.at[y, 'seg_oi_basis']) for y in _E17_YS}
    _E17_BASIS = sorted(set(_E17_BAS.values()))
    # 窗口跨了断点是**允许**的（不跨就看不到 FY2016-2019），但跨了就必须在**表里**
    # 逐列标出来 —— CONTRACT §5 第 2 条：「口径断点必须画出来，不能靠图注文字提一句
    # 就算数」。下面 C 段会因此多一行「分部口径」，值逐列现读 _E17_BAS。
    # 这里只拦「出现了本文件不认识的取值」：那说明上游又加了一档，而 C 段那一行
    # 会把它印成原始英文串，读者读不懂，且我们也不知道新那一档跟旧的能不能比。
    # 值要短：这一行有 10 列，写成「旧（股权激励未摊入分部）」会把整张表撑到必须横滑。
    # 两档各是什么意思写在行名与 note 里，格子里只留可区分的最短记号。
    _E17_BAS_ZH = {'pre-sbc-alloc': '旧', 'sbc-alloc': '新'}
    _bad_bas = [b for b in _E17_BASIS if b not in _E17_BAS_ZH]
    if _bad_bas:
        raise SystemExit(f'series/cost_fy.csv 的 seg_oi_basis 出现本文件不认识的取值 '
                         f'{_bad_bas} —— 先决定它与已有两档能不能并排读，再改这里')
    if len(_E17_YS) < 5:
        raise SystemExit(f'series/cost_fy.csv 只有 {len(_E17_YS)} 个财年，'
                         f'Exhibit 17 至少要 5 列才看得出趋势')
    # Exhibit 16 的横轴也是财年，两张表并排读；列对不上时读者会以为其中一张漏了年份。
    # 不强行取交集：对不上就说明两张 CSV 的覆盖区间分叉了，那是要人去看的事。
    if [y for y in _E17_YS if y in _COH_YRS] != _COH_YRS:
        raise SystemExit(f'Exhibit 17 的财年 {_E17_YS} 没有覆盖 Exhibit 16 的 {_COH_YRS} —— '
                         f'两张表的列对不上，而 16 的 Totals 行要印 17 算出来的平衡线')
    _E = {y: _e17_calc(y) for y in _E17_YS}
    _EL = _E[_E17_YS[-1]]                               # 最新财年，note 与标题的水平值都引它
    # 标题与 note 里直接引这两个值，缺了会印出 'None'。宁可整页失败也别印那种字。
    for _k, _why in (('coh', f'{_COH_V} 矩阵的 Totals 行没有 FY{_E17_YS[-1]} 那一格'),
                     ('first', f'{_COH_V} 矩阵里没有 {_E17_YS[-1]} 年开业那一队的首年值')):
        if _EL[_k] is None:
            raise SystemExit(f'Exhibit 17 的标题/图注要引 {_k}，但{_why}')
    # 盈亏平衡的两条边，按 Exhibit 16 那张矩阵的年份逐年折成金额。
    # 在这里算而不是在下面追加行的地方算：Ex16 的 note 要引这两行的首末读数，
    # 而 note 拼好的时候行还没接上去。一处算、两处用，不许各算一遍。
    _be_vals = {k: [None if not _E[y]['coh'] else round(_E[y][k] * _E[y]['coh'])
                    for y in _COH_YRS] for k in ('lo', 'hi')}
    _be_lo0, _be_hi0 = _be_vals['lo'][0], _be_vals['hi'][0]
    _be_lo1, _be_hi1 = _be_vals['lo'][-1], _be_vals['hi'][-1]

    _ns_last = float(_fyd.at[_COH_LAST, 'net_sales_mn'])
    _wh_last = int(_fyd.at[_COH_LAST, 'wh_total'])
    # 期间平均家数：只为**证伪**「缺口是期末/期间平均之差造成的」这一说 —— 换了平均数，
    # 合并口径的均店销售只会离披露值更远。这不是我们采用的口径。
    _wh_prev = (int(_fyd.at[_COH_LAST - 1, 'wh_total'])
                if (_COH_LAST - 1) in _fyd.index else None)
    _wh_avg = None if _wh_prev is None else (_wh_prev + _wh_last) / 2.0
    # 脚注说 53 周财年已归一 —— 用本仓自己的 weeks 列核一遍它点的是哪两年
    _w53 = [str(_fyd.at[y, 'fy']) for y in _fyd.index if int(_fyd.at[y, 'weeks']) == 53]
    # 爬坡的实测：单独列出的队列里年份跨得最长的那个（"& Before" 是聚合行，不算队列）
    _ramp_c = max((c for c in _data_labs if '&' not in c),
                  key=lambda c: len([y for y in _COH_YRS if (c, y) in _cval]))
    _ramp_y = [y for y in _COH_YRS if (_ramp_c, y) in _cval]
    _ramp_v0, _ramp_v1 = _cval[(_ramp_c, _ramp_y[0])], _cval[(_ramp_c, _ramp_y[-1])]
    _ramp_n = len(_ramp_y) - 1
    _ramp_cagr = (_ramp_v1 / _ramp_v0) ** (1.0 / _ramp_n) - 1 if _ramp_n else float('nan')

    _COH_SRC = (f'Costco {_COH_V} 10-K 内 "Average Sales Per Warehouse* (Sales In Millions)" '
                f'一图（排在 "Item 6—Reserved" 之前），经 <code>fetch/cost_sec.py</code> 解析'
                f'入 <code>series/cost_cohort.csv</code>。'
                f'<b>本图与 Exhibit 17 的数据源不是月度销售新闻稿</b>（卡片下方 Source 行印的是'
                f'全页共用的那一个），本页其余各图才是。')
    _COH_NOTE = (
        f'<b>整张图都是公司披露值，没有一个数是我们算的</b>：{len(_data_labs)} 个开业队列'
        f'（含聚合行「{_hesc(_AGG_LAB)}」{_AGG_N} 家）+ Totals 行，'
        f'横向 {len(_COH_YRS)} 个财年 FY{_COH_YRS[0]}–FY{_COH_LAST}，'
        f'合计 {_cnt[_COH_TOT]:,} 家。'
        f'<b>只取一个 vintage（{_COH_V} 10-K）</b>：这张图公司每年都印，但聚合行的含义'
        + (f'逐年在变 —— 本图这一行是「{_hesc(_AGG_LAB)}」（{_AGG_N} 家），'
           f'上一份（{_COH_PREV} 10-K）印的是「{_hesc(_PREV_LAB)}」（{_PREV_N} 家）；'
           f'两份混着读等于把两个不同的仓店池画成同一行。'
           if _PREV_LAB else '会逐年变（本仓目前只存了一个 vintage，无从对照）。')
        + f'<b>脚注照抄公司原文</b>：「{_cohort_footnote()}」——「首年年化」这四个字很要紧：'
        f'最新队列（{_coh_newest} 年开业的 {_cnt[_coh_newest]} 家）那一格 ${_first_new}mn '
        f'不是它当年真收到的钱，是把不足一年的经营期折算成整年的数；'
        f'脚注点名的两个 53 周财年，在本仓 <code>series/cost_fy.csv</code> 的 weeks 列里'
        f'查出来正是 {" / ".join(_w53)}，对得上。'
        f'<b>格子是名义美元，没有做任何通胀调整</b>：横着读一行'
        f'（最长的一行是 {_ramp_c} 年开业的 {_cnt[_ramp_c]} 家：首年 ${_ramp_v0}mn → '
        f'FY{_ramp_y[-1]} ${_ramp_v1}mn，{_ramp_n} 个财年区间累计 '
        f'{_ramp_v1 / _ramp_v0 - 1:+.0%}、折年均 {_ramp_cagr:+.1%}），'
        f'这里面含物价涨幅，不能整段读成客流或客单的改善。'
        f'<b>口径缺口 —— 印出来，但不给它编理由</b>：把整张图按家数还原成系统销售额，'
        f'Σ(家数 × 格值) = ${_coh_impl[_COH_LAST]:,}mn（${_coh_impl[_COH_LAST] / 1000:.1f}bn），'
        f'而 FY{_COH_LAST} 合并净销售额是 ${_ns_last:,.0f}mn（${_ns_last / 1000:.1f}bn），'
        f'差 {_coh_gap[_COH_LAST]:.1%}；这个缺口在 FY{_COH_YRS[0]} 是 {_coh_gap[_COH_YRS[0]]:.1%}，'
        f'{len(_COH_YRS)} 个财年一路走阔到今天。'
        f'<b>10-K 没有一个字说这张图的分子含什么、不含什么</b>，所以本页只印缺口本身。'
        f'两条听起来顺理成章的解释，一条在本页数据上当场被证伪、另一条无据：'
        f'（1）「期末家数 vs 期间平均家数」——矩阵每一列的分母（当年已开业队列的家数之和）'
        f'与当年披露的<b>期末</b>仓店数逐年相等（{_den_ok}/{len(_COH_YRS)} 个财年全对上，'
        f'FY{_COH_LAST} 是 {_wh_last} 对 {_wh_last}）'
        + ('' if _wh_avg is None else
           f'，而改用期间平均家数（{_wh_avg:.0f}）只会把合并口径的均店销售推到 '
           f'${_ns_last / _wh_avg:.0f}mn、离图上的 ${_sys_avg}mn <b>更远</b>')
        + f'；（2）「电商销售不进这张图」—— 10-K 既没这么说也没否认，那是猜，不是口径。'
        f'<b>怎么读</b>：一行一个开业队列，往右是它开业后的每一个财年；开业年之前的 '
        f'{_n_null} 格留空（那时这些仓店还不存在，不是缺数据）。'
        f'最新队列首年 ${_first_new}mn 与系统均店 ${_sys_avg}mn 之间的那一段就是新店爬坡。'
        # ── 末两行（盈亏平衡）不是公司披露值，必须在这里说清 ──
        f'<b>⚠️ 末两行不是公司披露值，是推导的盈亏平衡区间</b>（算法、两条假设与'
        f'「为什么只能是区间」全部写在 Exhibit 17 的 Note 里，这里不重复一遍）：'
        f'上面每一行都是 {_COH_V} 10-K 印出来的数，末两行是本页拿合并损益的三个比率'
        f'（商品毛利率 g、SG&amp;A 率 s、会员费率 m）折到同一张矩阵的口径上算出来的 —— '
        f'下沿把会员费按公司平均费率记进贡献，上沿一分都不记。'
        f'本期 FY{_COH_YRS[0]} 是 ${_be_lo0}–{_be_hi0}mn、FY{_COH_LAST} 是 '
        f'${_be_lo1}–{_be_hi1}mn。接进这张矩阵是为了让「某一队爬到第几年才过线」'
        f'能在同一张图上竖着读，不用跳到下一张表。'
        f'<b>⚠️ 但别按颜色读这两行</b>：色阶是全矩阵共用的（引擎按所有有限值的 5/95 '
        f'分位定色），而它们的语义与队列各行相反 —— 队列是越高越好，平衡线是越高越难达标，'
        f'于是同一种绿色在这两行上的含义正好反过来。引擎没有逐行色阶这个开关，'
        f'所以只能在这里点名，读数请看格子里的数字。')

    # ── 把盈亏平衡线并进矩阵（所有者 2026-09-03 指令：「把『盈亏平衡销售额』这个数字
    #    写到 ex16 里面 totals 这一行」）──────────────────────────────────────────
    # 放在这里、而不是在上面那些校验之前：以上每一条校验（家数合计、加权均值复现、
    # 每队列格数、缺口、_n_null）问的都是「公司披露的那张矩阵自洽不自洽」，
    # 推导行掺进去会把它们全部变成另一个问题。所以先验完披露值，再往下面接两行。
    #
    # 为什么是**两行**而不是一行：平衡线本来就是个区间（上沿不给这家店记一分会员费、
    # 下沿按公司平均费率记进去），Exhibit 17 的 E 段也是这么印的。在这里塌成一个数，
    # 等于把一个明确标了「区间」的推导值在另一张图上改口说成点估计。
    #
    # ⚠️ 色阶是**全矩阵共用**的（引擎按所有有限值的 5/95 分位定色），而这两行的
    # 语义与其余各行相反 —— 队列行是「越高越好」，平衡线是「越高越难达标」。
    # 引擎没有逐行色阶这个开关，所以只能在 note 里点名，别让读者按颜色读这两行。
    _BE_LO = f'盈亏平衡（计会员费）'
    _BE_HI = f'盈亏平衡（不计会员费）'
    for _lab, _k in ((_BE_LO, 'lo'), (_BE_HI, 'hi')):
        _COH_LABS.append(_lab)
        _coh_matrix.append(_be_vals[_k])              # 上面算好的那一份，不重算

    ex.append({
        'n': 16, 'kind': 'heat_matrix', 'full': True,
        # 队列各行与 Totals 是**公司披露值**，末两行是推导的盈亏平衡区间 ——
        # 标题里必须让这件事一眼看得见（CONTRACT §5 第 1 条），不能只写在 note 里。
        'title': (f'Average Sales Per Warehouse by Year Opened, $mn ({_COH_V} 10-K), '
                  f'+ Implied Break-Even: New Warehouse ${_first_new}mn vs '
                  f'System Average ${_sys_avg}mn vs Break-Even ${_be_lo1}–{_be_hi1}mn'),
        'rows': _COH_LABS,
        'cols': [f'FY{y}' for y in _COH_YRS],
        'matrix': _coh_matrix,
        'fmt': 'usd0',
        'legend': '均店销售（$mn/店·年）',
        # 行标签里最长的是聚合行「2016 & Before」（13 个字符，size 8 下约 58px），
        # 默认的 row_lab_w=32 会让它压到格子里去；这里按最长行标签定宽，不猜常数。
        # 4.8 是 size-8 行标签的每 **ASCII** 字符宽（引擎给 heat_matrix 的行标签写死
        # size 8）。中日韩字符在同一字号下约是它的两倍宽，而新加的两行盈亏平衡标签
        # 全是中文 —— 按 len() 直接乘 4.8 会把标签栏算窄一半、标签压进格子里。
        # 所以按「CJK 记 2、其余记 1」现算宽度，仍不写死常数。
        'row_lab_w': max(32, round(max(
            sum(2 if ord(ch) > 0x2E7F else 1 for ch in lab) for lab in _COH_LABS) * 4.8) + 10),
        'row_head': '开业年份（队列）', 'cell_h': 20,
        'src_extra': _COH_SRC,
        'note': _COH_NOTE,
    })
    SEC_EX.append(ex[-1]['n'])            # 出自 10-K Item 5 的均店销售矩阵

    # ══════════════════════════════════════════════════════════════════════════════
    # Ex 17 —— 每仓店单位经济性与推导的盈亏平衡线（kind: 'table'）
    #
    # 贴在 Exhibit 16 那一块**之后**、「── 图号连号硬护栏 ──」那一段之前，缩进 4 格。
    # ⚠️ 本块复用 Exhibit 16 那一块算出来的 `_fyd` / `_cval` / `_cnt` / `_COH_V` /
    #    `_COH_TOT` / `_sys_avg`（同一份 vintage、同一张 Totals 行）。两块各读一遍
    #    CSV、各选一次 vintage 迟早会分叉 —— 那种分叉的表现是「两张图上的 $272mn
    #    不是同一个数」，页面不会报错。所以只准一起贴，且 16 在前；漏贴 16 会当场
    #    NameError（响，比静默分叉好）。
    #
    # 为什么是 kind:'table' 而不是图：这张表的每一行单位都不同（$mn/店、%、家数、
    # 区间），画成柱线只能挑一行画，其余全丢；而它要参与阅读顺序（读者刚看完
    # Exhibit 16 的爬坡曲线，紧接着就要问「爬到多少才不亏」），推到页尾附录等于让他
    # 翻回去找（CONTRACT §3 的 kind:'table' 那一节）。
    #
    # 为什么标题必须带 Implied：Costco **不披露**任何单店损益，也不披露任何盈亏
    # 平衡数 —— 'break-even' / 'breakeven' / 'payback' 在 FY2025 10-K 与 FY26 Q3
    # 10-Q 里出现 0 次。所以这是推导构造，按 CONTRACT §5 第 1 条标 Implied，
    # 假设写进 note，并且**只给区间、不给单一数字**。
    # ══════════════════════════════════════════════════════════════════════════════
    # ── 恒等式：净销售额 + 会员费 − 商品成本 − SG&A = 经营利润（逐年验，不过就整页失败）──
    # 这条不是抄来的信念：开办费（preopening）这一行在 FY2021 及以前的申报里是**单列**的，
    # 后来才并进 SG&A。series/cost_fy.csv 的 `sga_mn` 对**全部年份**都已含开办费
    # （那是该表对下游的硬承诺），`preopen_src` 只记这一笔是谁折进去的
    # （loader-folded / issuer-folded / not-disclosed）—— 是**来路**，不是「含没含」。
    # 折错一年，这条恒等式立刻差出一个开办费的量级，所以逐年验。
    for _y in _fyd.index:
        _r = _fyd.loc[_y]
        _lhs = (_r.net_sales_mn + _r.memb_fee_mn - _r.merch_cost_mn - _r.sga_mn)
        if abs(_lhs - _r.op_income_mn) > 0.5:
            raise SystemExit(f'FY{_y} 恒等式不成立：净销售 {_r.net_sales_mn} + 会员费 '
                             f'{_r.memb_fee_mn} − 商品成本 {_r.merch_cost_mn} − SG&A '
                             f'{_r.sga_mn} = {_lhs} ≠ 经营利润 {_r.op_income_mn}')
        _seg = _r.op_income_us_mn + _r.op_income_ca_mn + _r.op_income_oi_mn
        if abs(_seg - _r.op_income_mn) > 0.5:
            raise SystemExit(f'FY{_y} 分部经营利润合计 {_seg} ≠ 合并 {_r.op_income_mn}')

    _m1 = lambda v: None if v is None else f'{float(v):,.1f}'      # $mn 一位小数
    _p2 = lambda v: None if v is None else f'{float(v) * 100:.2f}%'
    _i0 = lambda v: None if v is None else f'{float(v):,.0f}'
    _KEY = {y: f'fy{y}' for y in _E17_YS}

    def _row(label, fn):
        """一行：首列文字 + 逐年已格式化好的字符串（CONTRACT §3/§4：页面不做计算）。"""
        return {'xl': label, **{_KEY[y]: fn(_E[y]) for y in _E17_YS}}

    def _hdr(label):
        """分块表头行。值给空串而不是 None —— None 会渲染成一排「—」，看着像缺数据。"""
        return {'xl': label, **{_KEY[y]: '' for y in _E17_YS}}

    _E17_ROWS = [
        _hdr('<b>A. 合并口径的每仓店 P&amp;L</b>（分母 = 期末全球仓店数）'),
        _row('　期末全球仓店数（家）(D)', lambda e: _i0(e['wh'])),
        _row('　净销售额 / 店 (A)', lambda e: _m1(e['ns'] / e['wh'])),
        _row('　会员费 / 店 (A)', lambda e: _m1(e['memb'] / e['wh'])),
        _row('　商品毛利 / 店（净销售 − 商品成本）(A)', lambda e: _m1(e['gp'] / e['wh'])),
        _row('　SG&amp;A / 店（已含开办费）(A)', lambda e: _m1(e['sga'] / e['wh'])),
        _row('　经营利润 / 店 (A)', lambda e: _m1(e['oi'] / e['wh'])),

        _hdr('<b>B. 口径无关的比率</b>（分母一律是合并净销售额）'),
        _row('　商品毛利率 g (A)', lambda e: _p2(e['g'])),
        _row('　会员费率 m (A)', lambda e: _p2(e['m'])),
        _row('　SG&amp;A 率 s (A)', lambda e: _p2(e['s'])),
        _row('　经营利润率 = g + m − s (A)', lambda e: _p2(e['g'] + e['m'] - e['s'])),

        _hdr('<b>C. 分部经营利润 / 店</b>（收入侧含会员费，与 A 段不可加减）'),
    ]
    # ── C 段的口径断点：逐列标出来，而不是在 note 里提一句 ─────────────────────
    # Costco 在 FY2022 10-K 里说「Effective for fiscal 2022, stock-based compensation was
    # allocated to the segments … Operating income was restated in each of the segments for
    # all prior periods」，但它**只呈现了 FY2022/2021/2020 三年** —— FY2019 及更早从来
    # 没有被重述过。所以本段横着读会在 FY2019/FY2020 之间跨一次口径：实测其他国际
    # 3.83% → 3.76% 看着像下滑，同口径下其实是上升。合并口径的 op_income_mn 不受影响，
    # 断的只是分部的拆法，所以 A/B/D/E 四段照旧可以整条横读。
    # 这一行只在窗口真的跨了断点时才加：没跨的时候它每列一个样，是纯噪音。
    if len(_E17_BASIS) > 1:
        _E17_ROWS.append({'xl': '　<b>分部口径</b>：旧 = 股权激励未摊入分部 · '
                                '新 = 已摊入（<b>跨档不可比</b>）(D)', **{
            _KEY[y]: _E17_BAS_ZH[_E17_BAS[y]] for y in _E17_YS}})
    # 分部三行读的是 op_income_{us,ca,oi} / wh_{us,ca,oi}，与 _row 走的「先算比率再乘」
    # 那条路结构不同，单独拼一遍比给 _row 加一堆参数清楚。
    for _lab, _oc, _wc in (('美国', 'op_income_us_mn', 'wh_us'),
                           ('加拿大', 'op_income_ca_mn', 'wh_ca'),
                           ("其他国际", 'op_income_oi_mn', 'wh_oi')):
        _E17_ROWS.append({'xl': f'　{_lab} (A)', **{
            _KEY[y]: _m1(float(_fyd.at[y, _oc]) / float(_fyd.at[y, _wc])) for y in _E17_YS}})
    _E17_ROWS.append({'xl': '　分部期末仓店数（家；美国 / 加拿大 / 其他国际）(D)', **{
        _KEY[y]: ' / '.join(f'{int(_fyd.at[y, c])}' for c in ('wh_us', 'wh_ca', 'wh_oi'))
        for y in _E17_YS}})

    _E17_ROWS += [
        _hdr('<b>D. 「均店销售」的两个口径</b>（$mn/店·年，两者不可混用）'),
        _row(f'　① 队列表 Totals 行（{_COH_V} 10-K 披露，= Exhibit 16 末行）(D)',
             lambda e: _i0(e['coh'])),
        _row('　② 合并净销售额 ÷ 期末仓店数 (A)', lambda e: _m1(e['ns_wh'])),
        _row('　②÷① − 1（口径差）(A)',
             lambda e: None if not e['coh'] else f'{e["ns_wh"] / e["coh"] - 1:+.1%}'),

        _hdr('<b>E. 盈亏平衡（推导值 Implied，两条假设见下方 Note）</b>'),
        _row('　对照：当年新开队列的首年（年化）销售（Exhibit 16 对角线）(D)',
             lambda e: _i0(e['first'])),
        _row('　盈亏平衡 ÷ 均店销售：s/(g+m) – s/g (E)',
             lambda e: f'{e["lo"] * 100:.1f}–{e["hi"] * 100:.1f}%'),
        _row('　<b>盈亏平衡销售额（$mn/店·年，按口径 ①）(E)</b>',
             lambda e: None if not e['coh']
             else f'<b>{e["lo"] * e["coh"]:.0f}–{e["hi"] * e["coh"]:.0f}</b>'),
    ]

    # ── 图注：每一个数都现算 ────────────────────────────────────────────────────
    _e17_capex = float(_fyd.at[_E17_YS[-1], 'capex_mn'])
    _e17_open = _fyd.at[_E17_YS[-1], 'wh_open_total']
    # 本表窗口里哪几年的开办费是**本仓的加载器**折进 SG&A 的（其余要么是公司自己
    # 重述时折的，要么源里已经没有这条线）。读 `preopen_src` 的取值，不读旧的
    # `sga_folded_preopen`（那一列已改名，且它的语义读起来正好是反的 ——
    # 见 fetch/cost_sec.py 里那段改名说明）。
    _e17_folded = [f'FY{y}' for y in _E17_YS
                   if str(_fyd.at[y, 'preopen_src']) == 'loader-folded']
    _e17_dgap = _EL['ns_wh'] / _EL['coh'] - 1
    _e17_lo_usd, _e17_hi_usd = _EL['lo'] * _EL['coh'], _EL['hi'] * _EL['coh']
    _e17_y0 = _E[_E17_YS[0]]
    _E17_NOTE = (
        f'<b>来源不是月度新闻稿</b>：本表读 <code>series/cost_fy.csv</code>'
        f'（Costco 10-K 的合并损益、资本开支与仓店数，FY{int(list(_fyd.index)[0])}–'
        f'FY{_E17_YS[-1]}），口径 ① 那一行读 Exhibit 16 的同一张 {_COH_V} 10-K 矩阵；'
        f'卡片下方的 Source 行是全页共用的那一个（月度销售新闻稿），对本表不适用。'
        f'<b>行末标记</b>：(D) 公司披露值 · (A) 披露值之间的算术 · (E) 推导估计 —— '
        f'全表只有 E 段最后两行是 (E)，且只以<b>区间</b>出现。'
        f'<b>恒等式已逐年验过</b>：净销售额 + 会员费 − 商品成本 − SG&amp;A = 经营利润，'
        f'{len(_fyd)} 个财年逐年成立（对不上就整页构建失败，不静默上线）；'
        f'SG&amp;A 每一年都<b>含开办费</b>'
        + (f'（本表所列 {len(_E17_YS)} 年里 {"、".join(_e17_folded)} 是构建时折进去的，'
           f'其余年份公司报出来就已经含）。' if _e17_folded else
           '（本表所列各年公司报出来就已经含，无需折算）。')
        + f'<b>盈亏平衡怎么算的</b>：平衡点 = SG&amp;A 率 ÷ 贡献率 —— '
        f'FY{_E17_YS[-1]} 的 s = {_EL["s"]:.3%}，上沿的贡献率只算商品毛利 '
        f'g = {_EL["g"]:.3%}（一分会员费都不给这家店，{_EL["s"]:.3%}/{_EL["g"]:.3%} = '
        f'{_EL["hi"]:.1%}），下沿把会员费按公司平均费率 m = {_EL["m"]:.3%} 记进贡献'
        f'（{_EL["s"]:.3%}/{_EL["g"] + _EL["m"]:.3%} = {_EL["lo"]:.1%}）。'
        f'区间口径从 FY{_E17_YS[0]} 的 {_e17_y0["lo"]:.1%}–{_e17_y0["hi"]:.1%} '
        f'收窄到今天的 {_EL["lo"]:.1%}–{_EL["hi"]:.1%}。'
        f'<b>假设 1（也是这条带只能当上界的原因）</b>：它按公司<b>全口径</b>的 SG&amp;A 率'
        f'给一家店记账，而那一行里含总部与电商的成本 —— Costco 把仓店薪酬、<b>全部</b>'
        f'总部薪酬、几乎全部折旧摊销、信用卡手续费、水电与开办费统统计入这一行，'
        f'从不拆固定与变动。所以真实的<b>店层面</b>平衡点比这条带更低，低多少公开数据里'
        f'算不出来 —— 不是没算，是分不出来。'
        f'<b>假设 2</b>：新店按公司平均的毛利率与费用率经营。新店的实际毛利结构、'
        f'当地薪酬与租金公司都不披露。'
        f'<b>口径纪律（这是本表最容易出错的一处）</b>：比率与口径无关，但折成金额时'
        f'必须挑一个均店销售。本表用的是<b>队列表口径</b>（口径 ①，FY{_E17_YS[-1]} '
        f'${_EL["coh"]}mn），不是合并净销售额 ÷ 期末仓店数（口径 ②，'
        f'${_EL["ns_wh"]:.1f}mn，比 ① 高 {_e17_dgap:.1%}）—— 因为 E 段要比的那个'
        f'「首年 ${_EL["first"]}mn」本来就活在队列口径里，拿 ② 去乘就是把两个口径的数'
        f'放在同一行比。两个口径都印在 D 段，差多少读者自己看得见；那个 {_e17_dgap:.1%} '
        f'的缺口本身没有披露上的解释，见 Exhibit 16 的图注。'
        f'<b>读出来是什么</b>：FY{_E17_YS[-1]} 的平衡带是 ${_e17_lo_usd:.0f}–'
        f'${_e17_hi_usd:.0f}mn/店·年，而公司披露的新店首年（年化）销售是 '
        f'${_EL["first"]}mn、系统均店是 ${_EL["coh"]}mn。'
        f'下沿与首年只差 ${abs(_e17_lo_usd - _EL["first"]):.1f}mn —— <b>这是算术上的巧合，'
        f'不是因果</b>：下沿本身已经是上界性质的估计（假设 1），首年那个数又是年化过的'
        f'（Exhibit 16 的脚注原文）。能说的只有一句：新店首年落在这条带的下沿附近，'
        f'离系统均店 ${_EL["coh"]}mn 还差整整一段爬坡。'
        f'<b>最大的读数陷阱</b>：均店销售把成熟店与刚开的店混在一口锅里，而新店是要爬坡的'
        f'—— 那正是 <b>Exhibit 16</b> 那张矩阵画的东西（{_coh_newest} 年那一队 '
        f'${_first_new}mn 对系统 ${_sys_avg}mn）。拿本表任何一行去回答'
        f'「新开一家店赚不赚钱」之前，先看那张图。'
        f'<b>算不出来的两件事，说在明处</b>：（1）<b>开业当年的现金平衡点</b>算不出来 —— '
        f'公司不披露店层面的开办成本与薪酬，SG&amp;A 里的开办费是全公司一个合计数；'
        f'（2）<b>任何资本回报口径的平衡点</b>算不出来 —— 资本开支只有合计数'
        f'（FY{_E17_YS[-1]} ${_e17_capex:,.0f}mn），它同时覆盖新开与改建仓店的土地、'
        f'建筑与设备，还含 IT 与配送设施，把它除以当年开业的 {_e17_open:.0f} 家得到的'
        f'那个数<b>不是一家仓店的造价</b>，所以本表不印这个比值，也请不要在别处这么用。'
        + (f'<b>⚠️ C 段横着读要在 FY{[y for y in _E17_YS if _E17_BAS[y] == _E17_BASIS[0]][-1]}'
           f'/FY{[y for y in _E17_YS if _E17_BAS[y] != _E17_BASIS[0]][0]} 之间断一次</b>：'
           f'Costco 在 FY2022 10-K 里写「Effective for fiscal 2022, stock-based compensation '
           f'was allocated to the segments … Operating income was restated in each of the '
           f'segments for all prior periods」，但那份年报<b>只呈现了三个财年</b>，'
           f'FY2019 及更早从来没有被重述过。所以本段前 '
           f'{sum(1 for y in _E17_YS if _E17_BAS[y] == "pre-sbc-alloc")} 列是旧口径、'
           f'后 {sum(1 for y in _E17_YS if _E17_BAS[y] == "sbc-alloc")} 列是新口径，'
           f'C 段头一行逐列标着「旧 / 新」。跨着那一档读会读出一段纯属改分摊的假拐点'
           f'（实测其他国际由 3.83% 变成 3.76%，看着像下滑，同口径下其实是上升）。'
           f'<b>只有 C 段受影响</b> —— 合并口径的经营利润在两侧完全相同'
           f'（FY2020 两侧都是 5,435mn），所以 A / B / D / E 四段照旧可以整条横读。'
           if len(_E17_BASIS) > 1 else '')
        + f'<b>分部段的口径提醒</b>：分部经营利润是在把会员费算进分部收入之后结出来的，'
        f'而 A 段的「净销售额 / 店」<b>不含</b>会员费（会员费在 A 段单列一行），'
        f'两段不能相加减；本表的源里没有分部收入，所以分部只给到经营利润 / 店，'
        f'<b>也因此没有分部的盈亏平衡列</b> —— 那需要分地区的会员费，公司不披露。')

    ex.append({
        'n': 17, 'kind': 'table',
        # Implied 是硬要求（CONTRACT §5 第 1 条）：公司不披露单店损益，也从不给平衡点。
        'title': (f'Implied Break-Even Sales per Warehouse: '
                  f'{_EL["lo"]:.0%}–{_EL["hi"]:.0%} of the ${_EL["coh"]}mn System Average '
                  f'(${_e17_lo_usd:.0f}–${_e17_hi_usd:.0f}mn per Warehouse)'),
        'idx': '每仓店 / 年（$mn，除非另注）',
        'cols': [[f'FY{y}', _KEY[y]] for y in _E17_YS],
        'rows': _E17_ROWS,
        'full': True,
        'note': _E17_NOTE,
    })
    SEC_EX.append(ex[-1]['n'])            # 出自 10-K 的年度合并损益与仓店数

    # ── 图号连号硬护栏（照 build/ibkr.py 的 `_ens`）──────────────────────────
    # 本页原来一个都没有，代价 2026-09-03 实测过：把 Ex14 整块删掉之后，剩下的 2..13
    # 仍然连号，而末尾核对表还写死在 `'n': 15` —— 构建退出码 0、verify_pages
    # 0 ERROR / 0 WARN、生成器自己还理直气壮地印「Exhibit 2-13 共 12 张图 +
    # Exhibit 15 核对表」，页面上凭空少了一个 14。所以两件事要一起做：
    # 这条护栏管「图与图之间不许有洞」，下面核对表的 `'n': _ens[-1] + 1` 管
    # 「表紧跟在最后一张图后面」—— 只做前者拦不住上面那个洞。
    _ens = [e['n'] for e in ex]
    if _ens != list(range(2, 2 + len(_ens))):
        raise SystemExit(f'Exhibit 编号不是从 2 起的连号: {_ens}')
    # 多年叠加图的图号，现读 payload：stack_ex() 写的那句 src_extra 是它唯一的身份标记。
    # 页尾 Stacks 那条注要点名，原文写死「Exhibit 3 / 12」，插一张图就成假话。
    _STACK_NS = [e['n'] for e in ex
                 if str(e.get('src_extra', '')).startswith('Stacks = sum of same-retail-month')]
    if len(_STACK_NS) != 2:
        raise SystemExit(f'本页应当有 2 张多年叠加图，实测 {len(_STACK_NS)} 张: {_STACK_NS}')
    # 页尾三条注（数据源 / 两腿口径 / 客单客流）与页顶的名词释义读的都是上面各块
    # **装载现场**留下的那一份别名（_SEG_ALL / _FY_ALL / _TKT_ALL），不重新读磁盘：
    # 同一次构建里读两遍，理论上就可能读到两个不同的东西，而页面上不会有任何迹象。
    # 名词释义里那几处「见 Exhibit N」的绑定：slug → 图号，全部现读，且过 bind_exhibits()
    # 双向核一遍（绑到一张不存在的图会硬失败，而不是印出「见 Exhibit None」）。
    # 客单/客流那张图的号：**按标题现读**，不能拿 SEC_EX[0] —— 那本登记簿是按建图
    # 先后排的，第 0 个是分部收入结构（Exhibit 7），不是客单/客流。写成 SEC_EX[0]
    # 时页顶释义里印的是「Exhibit 7 画的就是这条季度序列」，指向了一张画收入结构的图，
    # 而 bind_exhibits() 只核「这个号存不存在」、核不出「指的是不是那张」。
    _EX_TKT = next((e['n'] for e in ex if 'ticket' in str(e.get('title')).lower()
                    and 'traffic' in str(e.get('title')).lower()), None)
    _GLOSS_EXN = bind_exhibits(ex, {
        'noncomp': 5,                            # 净销售额增长的 comp / 非 comp 拆分
        'wedge': 6,                              # 油汇楔子
        'ecomm': _EC_N,                          # 电商 / Digitally-Enabled comp
        'tkt': _EX_TKT,                          # 季度客单 × 客流
        'seg': REV_EX[0] if REV_EX else None,    # 分部收入结构（总收入口径）
    })

    # ── 轴刻度收口（必须排在 notes 之前）────────────────────────────────────
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.25 步长整列印成重复/错值，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    # **位置很要紧**：axisfmt 除了改格式器，还会给「柱图型出现负值」的图补 ycap/yfloor。
    # 下面 cap_note_txt 那句「本页哪几张截了轴」若在它之前算，某个月一旦真触发那条兜底，
    # 就会出现「图上截了轴、图注说没有」。所以先收口，再让 capped 现读最终 payload。
    axisfmt.fix_all(ex)
    capped = [e['n'] for e in ex if e.get('ycap') is not None or e.get('yfloor') is not None]

    # ── Exhibit 1：规矩 10 的汇总表（本月 | 上月 | 去年同月 ‖ m/m | y/y | 3Y %ile）──
    cur, prv, yag = LATEST, LATEST - 1, LATEST - 12

    def sget(col, p):
        v = df[col].get(p, np.nan) if p in df.index else np.nan
        return float(v) if pd.notna(v) else np.nan

    # ── 3Y %ile ──────────────────────────────────────────────────────────
    # 分位**判据**统一走 build/pctile.py，本文件不再自己写一份：同一条序列在两页被判
    # 成相反结果，正是各写各的造成的。下面这张表是**本页自己的口径理由**导致的留空，
    # 与「这一列有没有区分度」是两回事，各自独立生效。
    BLANK_WHY = {
        'net_sales_bn':
            '4-4-5 零售日历下 4 周月与 5 周月混在同一段历史里，拿 5 周月去比一堆 4 周月'
            '不是同一个量（与 Exhibit 4 红线标的是同一件事）',
        'wh_total':
            '期末仓库数是只增不减的开店计数，几乎每月都是历史新高，分位恒在区间上端'
            '并被涂成绿色，读起来像「异常之高」，其实只是在开店',
    }
    BLANK_WHY['wh_us'] = BLANK_WHY['wh_total']
    # e-comm 两行的 36 个月分位窗口跨了 FY26 口径变更：窗口里一部分是旧 e-commerce、
    # 一部分是新 Digitally-Enabled，混在一起排序算不出有意义的分位。断点滚出 36 个月
    # 窗口后这两条自动消失，不写死。
    EC_IN_WIN = ECOMM_BREAK > cur - 36
    if EC_IN_WIN:
        for _c in ('ec_a', 'ec_r'):
            BLANK_WHY[_c] = (f'近 36 个月窗口跨了 {ECOMM_BREAK} 的口径变更'
                             '（e-commerce → Digitally-Enabled），窗口内两种口径混排')
    # y/y 是否也跨断点（本月与去年同月分属两种口径）—— 同样现算
    EC_CROSS_YOY = yag < ECOMM_BREAK <= cur

    def pcell(col):
        """3Y %ile 单元格。判据交给 pctile.cell()，本页只负责口径性留空。"""
        if col in BLANK_WHY:
            return {'v': ''}
        s = [None if pd.isna(x) else float(x) for x in df[col]]
        v, cls = pctile.cell(s)
        return {'v': v, 'cls': cls} if cls else {'v': v}

    PCTF = lambda v: '—' if not np.isfinite(v) else dsp(v, 1, '%')[0]
    # 非 comp 贡献是两个增速相减，量纲是百分点不是百分比，水平值也得写 pp
    PPF = lambda v: '—' if not np.isfinite(v) else dsp(v, 1, 'pp')[0]
    USDF = lambda v: '—' if not np.isfinite(v) else f'${v:.2f}bn'
    INTF = lambda v: '—' if not np.isfinite(v) else f'{v:,.0f}'

    def srow(label, col, mode, vfmt, mm_ok=True, cross=False):
        """mode: pp = 比率指标（变化只能是百分点差）/ abs = 绝对个数 / ratio = 百分比变化。

        mm_ok=False 用于「相邻月本身就不可比」的行（4-4-5 零售日历下的绝对额）：
        m/m 整格留空。算得出来不等于该显示 —— 净销售额 4 周月与 5 周月相邻，
        m/m 的绝对多数是周数比而不是经营变化，一旦算出来还会按符号被涂成绿色，
        与表注里「不可当趋势读」的说明正好相反。

        cross=True 用于 y/y 两端分属两种口径的行（e-comm 跨 FY26 定义变更）：
        数值照印 —— 公司自己就是这么报的 —— 但**不涂涨跌色**，并在行名后加 †。
        把一个跨口径的差涂成绿色，等于替读者下了「确实好转了」这个结论，而本页
        Exhibit 11 的图注刚说过「前后不保证可比、无法从图上分离口径影响」。
        """
        c, p1, p12 = sget(col, cur), sget(col, prv), sget(col, yag)

        def delta(a, b):
            if not (np.isfinite(a) and np.isfinite(b)):
                return ('', '')
            if mode == 'pp':
                return ppdiff(a - b)
            if mode == 'abs':
                r = round(a - b) + 0.0
                return (f'{r:+,.0f}' if r else '0'), ('pos' if r > 0 else ('neg' if r < 0 else ''))
            if b == 0 or a * b < 0:          # 分母近 0 或两期异号，百分比变化没有意义
                return ('', '')
            return dsp((a / b - 1) * 100, 1, '%')

        mm, yy = (delta(c, p1) if mm_ok else ('', '')), delta(c, p12)
        if cross:
            yy = (yy[0], '')
        return {'kind': 'row', 'label': label + (' †' if cross else ''), 'cells': [
            {'v': vfmt(c), 'cls': 'cur'}, {'v': vfmt(p1)}, {'v': vfmt(p12)},
            {'v': mm[0], 'cls': mm[1]}, {'v': yy[0], 'cls': yy[1]},
            pcell(col),
        ]}

    # 「净销售额」那一组的两个 y/y 读数：表内算术 vs 公司披露的可比口径。
    # 两个数都现算，一个都不写死 —— 差值在 53 周财年前后会从 0.0pp 跳到 20pp 以上。
    _ns_c, _ns_y = sget('net_sales_bn', cur), sget('net_sales_bn', yag)
    NS_ARITH = ((_ns_c / _ns_y - 1) * 100 if np.isfinite(_ns_c) and np.isfinite(_ns_y) and _ns_y
                else float('nan'))
    NS_DISC = sget('ns_yoy', cur)
    NS_ARITH_TXT = PCTF(NS_ARITH)
    NS_DISC_TXT = PCTF(NS_DISC)
    NS_GAP_TXT = (ppdiff(NS_ARITH - NS_DISC)[0]
                  if np.isfinite(NS_ARITH) and np.isfinite(NS_DISC) else '—')
    _wk_c, _wk_y = df['weeks'].get(cur), df['weeks'].get(yag)
    WK_MATCH = bool(pd.notna(_wk_c) and pd.notna(_wk_y) and _wk_c == _wk_y)

    # 表注：每一个留空、每一个 † 都必须在这里有一句对应的解释，且解释由留空本身
    # 现算出来 —— 手写的表注会在数据滚动后变成假话。
    _blank_lines = []
    for _c, _lab in [('net_sales_bn', '净销售额 ($bn)'), ('wh_total', '仓库数（全球 / 美国及波多黎各）'),
                     ('ec_a', 'E-comm / Digitally-Enabled（核心与报告两行）')]:
        if _c in BLANK_WHY:
            _blank_lines.append(f'<b>{_lab}</b> 的 3Y %ile 留空：{BLANK_WHY[_c]}。')
    # pctile.py 自己判成「没有区分度」的行，理由用它给的原话，不另写一套说法
    for _c, _lab in [('tc_a', '核心 comp Total'), ('us_a', '核心 comp US'), ('ca_a', '核心 comp Canada'),
                     ("oi_a", "核心 comp Other Int'l"), ('tc_r', '报告 comp Total'),
                     ('us_r', '报告 comp US'), ('ca_r', '报告 comp Canada'),
                     ('oi_r', "报告 comp Other Int'l"), ('ns_yoy', '净销售额 y/y'),
                     ('nc_gap', '非 comp 贡献')]:
        if _c not in BLANK_WHY:
            _w = pctile.why_blank([None if pd.isna(x) else float(x) for x in df[_c]])
            if _w:
                _blank_lines.append(f'<b>{_lab}</b> 的 3Y %ile 留空：{_w}。')
    _summary_note = (
        'm/m、y/y 对比率指标一律取百分点差，|差| ≥ 1 写 pp、< 1 写 bp（全站同一约定）；'
        '对绝对量取百分比或个数差。3Y %ile = 该读数在最近 36 个月中的分位（100 = 三年最高），'
        '判据与全站共用 build/pctile.py：某一行的分位若在近两年里几乎恒定在区间端点，'
        '说明它对这一行没有区分度，整列留空。'
        f'净销售额是 4-4-5 零售日历下的月度绝对额，相邻月在周数与季节性上都不可比'
        f'（本月 {iv(df["weeks"].iloc[-1])} 周 vs 上月 {iv(df["weeks"].iloc[-2])} 周），'
        f'其 m/m 一律留空，不做周均折算。'
        # ⚠️ 这里原来无条件写着「y/y 对齐同一零售月，可比」。那句话在 53 周财年前后
        # 是**假的**：Jan-25 是 4 周、Jan-24 是 5 周，表内算术给 −11.6%，而公司披露 +9.2%，
        # 差 20.8pp —— 表里两行相隔两行、符号相反，却没有一个字解释。
        # WEEK_BREAKS 本来就是现算的，这句话现在跟着它走。
        + f'<b>「净销售额 ($bn)」行的 y/y 列是<u>表内算术</u></b>'
          f'（{mlab(cur)} ÷ {mlab(yag)} 的绝对额之比 = {NS_ARITH_TXT}），'
          f'读者拿第一列除第三列必须能得到同一个数，所以这一格<b>不换口径</b>；'
          f'而下一行「净销售额 y/y」印的是<b>公司披露的可比口径</b>'
          f'（{NS_DISC_TXT}，基期是同样周数的上年错位窗口）。'
        + (f'本月与去年同月周数相同（各 {iv(df["weeks"].get(cur))} 周），'
           f'两者差 {NS_GAP_TXT}，只是公司口径的错位与四舍五入。'
           if WK_MATCH else
           f'<b>⚠️ 本月 {iv(df["weeks"].get(cur))} 周而去年同月 {iv(df["weeks"].get(yag))} 周'
           f'（53 周财年），两者差 {NS_GAP_TXT} —— 这一格的表内算术里有整整一周的量，'
           f'该读的是下一行的披露值。</b>')
        + ('' if not _blank_lines else ' ' + ' '.join(_blank_lines))
        + ('' if not EC_CROSS_YOY else
           f' <b>†</b>：本月（{mlab(cur)}）与去年同月（{mlab(yag)}）分处 {ECOMM_BREAK} '
           'e-commerce → Digitally-Enabled 口径变更的两侧，该 y/y 是两种口径相减，'
           f'数值照公司披露印出但不涂涨跌色（见 Exhibit {_EC_N} 的断点线与图注）。'))

    G = lambda t: {'kind': 'group', 'label': t}
    summary = {
        'title': '关键指标汇总（本月 vs 上月 / 去年同月，含近 3 年分位）',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,                     # 竖线画在「水平值」与「变化率」之间
        'rows': [
            G('核心 comp（剔除汽油与汇率，y/y）'),
            srow('Total', 'tc_a', 'pp', PCTF),
            srow('US', 'us_a', 'pp', PCTF),
            srow('Canada', 'ca_a', 'pp', PCTF),
            srow("Other Int'l", 'oi_a', 'pp', PCTF),
            srow('E-comm / Digitally-Enabled', 'ec_a', 'pp', PCTF, cross=EC_CROSS_YOY),
            G('报告口径 comp（含汽油与汇率，y/y）'),
            srow('Total', 'tc_r', 'pp', PCTF),
            srow('US', 'us_r', 'pp', PCTF),
            srow('Canada', 'ca_r', 'pp', PCTF),
            srow("Other Int'l", 'oi_r', 'pp', PCTF),
            srow('E-comm / Digitally-Enabled', 'ec_r', 'pp', PCTF, cross=EC_CROSS_YOY),
            # 组标题写明这一组的 y/y 是什么口径：这一组里「$bn」行的 y/y 是表内算术
            # （本月 ÷ 去年同月），而下一行是公司披露的可比口径，两者在 53 周财年前后
            # 差 20pp 以上。不在组标题上说清楚，读者只会以为表里有个数算错了。
            G('净销售额（「$bn」行的 y/y 是<b>单月口径</b>表内算术 = 本月 ÷ 去年同月；'
              '下一行是公司披露的可比口径 —— 两者当期读数见表注）'),
            srow('净销售额 ($bn)', 'net_sales_bn', 'ratio', USDF, mm_ok=False),
            srow('净销售额 y/y', 'ns_yoy', 'pp', PCTF),
            srow('非 comp 贡献 (y/y − 报告 comp)', 'nc_gap', 'pp', PPF),
            G('仓库数（期末）'),
            srow('全球', 'wh_total', 'abs', INTF),
            srow('美国及波多黎各', 'wh_us', 'abs', INTF),
        ],
        'note': _summary_note,
    }

    # ── 近 13 个月核对表（与 PDF 第 4 页一致；逐条核对用，放在页面最后）──
    # 单元格一律是已格式化的字符串（CONTRACT §4）：官方原始单位，不做任何换算。
    F1 = lambda v: None if pd.isna(v) else f'{float(v):.1f}'
    F2 = lambda v: None if pd.isna(v) else f'{float(v):.2f}'
    I0 = lambda v: None if pd.isna(v) else f'{int(v):,d}'
    d13 = df.iloc[-13:]
    table = {
        # 紧跟最后一张图，不写死（写死过 15，删一张图就在页面上留了个洞，见上面 _ens）。
        'n': _ens[-1] + 1,
        'title': '近 13 个月月度数据核对表（comp 均为 y/y %, 核心 = 除油汇）',
        'idx': '零售月',
        'cols': [['净销售额 $bn', 'net_sales_bn'], ['y/y %', 'ns_yoy'], ['核心 Total', 'tc_a'],
                 ['核心 US', 'us_a'], ['核心 Canada', 'ca_a'], ['核心 Other Intl', 'oi_a'],
                 ['核心 E-comm', 'ec_a'], ['报告 Total', 'tc_r'], ['周数', 'weeks'],
                 ['仓库数(全球)', 'wh_total']],
        'rows': [{'xl': mlab(p), 'net_sales_bn': F2(r.net_sales_bn),
                  **{k: F1(getattr(r, k)) for k in
                     ['ns_yoy', 'tc_a', 'us_a', 'ca_a', 'oi_a', 'ec_a', 'tc_r']},
                  'weeks': I0(r.weeks), 'wh_total': I0(r.wh_total)}
                 for p, r in zip(d13.index, d13.itertuples())],
    }

    # ── 口径与方法说明（原 index.html 的 10 条；凡是「图上画了什么」的话一律现算）──
    #
    # 这一节里的每一句「Exhibit N 画了红色竖虚线 / 截了轴」都是对渲染结果的**声称**。
    # 声称必须由生成断点、生成截轴的那段代码本身产出，不能手写。原案（Ex4 的窗口还写死
    # 自 2021-01 起那阵）：WEEK_BREAKS 里的 2018-01 / 2019-01 落在窗口之外，原文却写
    # 「故 Exhibit 4 在这些位置画红色竖虚线」—— 读者会去图上找四条线，实际只有两条。
    # 窗口后来放宽到 WIN_START，四条线今天都在图上了 —— 但下面这段仍然现算，
    # 因为「今天恰好都在」不是把话写死的理由，窗口或 CSV 一动它就又是假话。
    wk_all = sorted(WEEK_BREAKS)
    wk_drawn = [d.index[i] for i in b4]                       # Ex4 上真正画出来的
    wk_out = [p for p in wk_all if p not in wk_drawn]
    wk_txt = f'本页自动识别：{" / ".join(str(p) for p in wk_all)}'
    if wk_drawn:
        wk_txt += ('；其中 ' + ' / '.join(str(p) for p in wk_drawn) +
                   ' 落在 Exhibit 4 的窗口内，图上画有红色竖虚线、柱用斜纹标出')
        if wk_out:
            wk_txt += ('，' + ' / '.join(str(p) for p in wk_out) +
                       ' 早于图窗起点，图上没有对应的线')
    else:
        wk_txt += '；全部早于 Exhibit 4 的图窗起点，图上没有对应的线'
    ec_note = ('<b>E-commerce 口径</b>：FY26 起更名为 Digitally-Enabled comparable sales，历史序列直接拼接'
               + (f'，Exhibit {_EC_N} 在 {ECOMM_BREAK} 处画红色竖虚线标注该断点。'
                  if b10 is not None else
                  f'；该断点已早于 Exhibit {_EC_N} 的图窗起点，图上没有对应的线。')
               # 原文「Exhibit 10 图窗自 2022 起（2021-01 曾达 ~+106% 的 COVID 低基数）」
               # 与图注是同源拷贝，窗口一放宽它就是假话，所以两处都由 ECOMM_FROM 现算。
               + f'Exhibit {_EC_N} 图窗自 {mlab(ECOMM_FROM)} 起 —— 那是公司披露电商 comp 的'
                 f'第一个月（报告口径 {mlab(_r0)}、核心口径 {mlab(_a0)}，逐月无缺），'
                 f'不是画图时截的窗口；纵轴因此含 COVID 低基数那一段，近端读数请看汇总表。'
               + ('' if not EC_CROSS_YOY else
                  f'Exhibit 1 汇总表里 e-comm 两行的 y/y 跨该断点，已加 † 标出。'))
    # ── 「公司披露的 y/y 已按可比周调整」这句话，用本页数据当场验一遍 ──────────
    # 判据：把周数错位的那几个月，公司披露的 ns_yoy 与「本月绝对额 ÷ 去年同月绝对额」
    # 并排放。若公司真按可比周报，两者应当在这些月份上差出接近整整一周的量
    # （4 周 vs 5 周 ⇒ 约 ±20%），而在周数相同的月份上几乎重合。差多少全部现算。
    _arith_all = (df['net_sales_bn'] / df['net_sales_bn'].shift(12) - 1) * 100
    _gap_all = (df['ns_yoy'] - _arith_all).dropna()
    _gap_mis = _gap_all[[p for p in _gap_all.index if p in WEEK_BREAKS]]
    _gap_ok = _gap_all[[p for p in _gap_all.index if p not in WEEK_BREAKS]]
    WK_EVID = (
        f'周数与上年同月<b>相同</b>的 {len(_gap_ok)} 个月里，公司披露值与表内算术的差'
        f'中位只有 {_gap_ok.abs().median():.2f}pp；'
        f'而周数<b>错位</b>的 {len(_gap_mis)} 个月里，这个差是 '
        + '、'.join(f'{mlab(p)} {v:+.1f}pp' for p, v in _gap_mis.items())
        + f'，量级正好是一周营收（{100 / 5:.0f}% 上下）。'
        '两条口径在错位月给出的甚至是相反的符号 —— '
        + '；'.join(f'{mlab(p)} 披露 {df["ns_yoy"][p]:+.1f}% vs 算术 {_arith_all[p]:+.1f}%'
                    for p in list(_gap_mis.index)[-2:])
        + '。')
    # ── 同比口径盘点（CONTRACT.md §6）──────────────────────────────────────
    # 全站口径是单月同比（§6.1 第 1 条），本页无处偏离 —— 但也无处落地：本页**没有一处**
    # 是「本脚本自算的同比」，图上画的增速全是公司披露值，公司的分母是它自己的可比周窗口，
    # 我们手里根本没有那个基期的水平值。§6.1 第 3 条要求每张同比图印出单月口径的代价
    # （`yoy.caliber_diff` 拿这条序列的水平值自算两遍再对齐），因此在本页算不出来，
    # 下面那条 note 要把「为什么算不出来」说清楚 —— 不是省了这笔账。
    _disc_cols = ['tc_a', 'tc_r', 'us_a', 'us_r', 'ca_a', 'ca_r', 'oi_a', 'oi_r',
                  'ec_a', 'ec_r', 'ns_yoy']

    # 分桶交给模块级的 partition_axes()（正文块 §8）：它比原来的二分多一个「占比」桶，
    # 且判据同时看 fmt —— stacked_dual 的占比图可以只给 fmt 不给 yfmt，原判据会把它
    # 判成「水平值图」，于是下面那句话当场点了一张百分比图的名。
    _yoy_ex, _share_ex, _lvl_ex, _tbl_ex = partition_axes(ex, SHARE_EX)
    # ⚠️ 原文是「除 Exhibit {水平值那几张} 之外，本页**每一张图上的每一条线**、以及
    # 汇总表与核对表里的每一条 comp 与净销售额同比，**都是** Costco 新闻稿里的披露值」。
    # 排除项是现算的，可被断言的那一类却比判据宽：判据只问「纵轴是不是百分比」，
    # 而百分比轴上还有一批**由披露值加减出来的**线 —— 多年叠加（相邻年份的披露 comp
    # 相加）、油汇楔子（reported − core，Exhibit 6 自己的图注就写着「不是公司拆分」）、
    # 非 comp 贡献（净销售额 y/y − 报告 comp）。它们都不是「新闻稿里的披露值」。
    # 这句话真正要说的是「我们从不拿水平值自己算同比」，所以把外延收到那句上，
    # 并把来源分成「披露值本身」与「披露值之间的加减」两类 —— 一个数只能是这两者之一。
    WEEK_CAL_NOTE = (
        '<b>同比口径：全站一律<u>单月</u>同比（当月 ÷ 去年同月 − 1，CONTRACT.md §6.1 第 1 条）；'
        '而本页<u>图上</u>的同比没有一个是我们拿水平值自己算出来的</b>。'
        '图上的同比只有两种来源：一是 Costco 新闻稿里的<b>披露值</b>本身'
        f'（CSV 里的 {len(_disc_cols)} 列：<code>' + '</code> <code>'.join(_disc_cols)
        + '</code>），二是这些披露值之间的<b>加减</b>（例如多年叠加与油汇楔子；'
        '算式写在用到它的那张图的图注里）。两类都不含我们拿绝对额自算的跨年增速。'
        + week_cal_tail(_lvl_ex, _share_ex, _tbl_ex)
        +
        '披露值由公司按<b>可比周</b>口径报出，基期是同样周数的上年错位窗口 —— '
        '它问的正是「本月对去年同月」这一层，与全站的单月口径同层，'
        '只是那个窗口按<b>周</b>对齐而不是按日历月，所以它<b>不等于</b>逐日历月相除的那个数'
        '（差多少、哪几个月甚至反号，见上一条）。'
        f'§6.1 第 3 条要求每张画<b>流量</b>同比的图印出单月口径的代价 —— 拿这条序列自己的单月同比与 '
        f'{Y.TTM_WIN} 个月滚动同比对齐后实测（对照的那一侧只以数字出现，页上一条线都不画）。'
        '<b>这笔账在本页无处可印</b>：它要求同一条序列的水平值能被我们自己算两遍，'
        '而本页图上的同比既不是我们算的，我们手里也没有公司那个可比周基期的水平值。'
        f'全页唯一能加总的水平值序列只有 <code>net_sales_bn</code>（净销售额那张图的柱就是它），'
        f'而<b>图上没有一条同比线是拿它算出来的</b> —— 连那张图上的金线也是公司披露的 '
        f'<code>ns_yoy</code>，不是柱与柱相除的结果（53 周错位月两者甚至反号）。'
        '<b>唯一一处「本月 ÷ 去年同月」的表内算术</b>在汇总表「净销售额 ($bn)」那一行的 '
        'y/y 列，已在组标题与表注里点名，并把两种口径的当期读数并排印出。'
        '页顶「本月读数怎么读」一段（brief）遵守同一条：段内的<b>同比</b>全部引披露值，'
        '句内标「单月可比周口径」，与汇总表 y/y 列同口径、可逐格对上，没有一个自算的'
        '跨年增速；段内现算的只有环比与位置类推导量（净销售额的表面环比与周均折算、'
        '楔子的宽窄、历史排名）—— 环比不是同比，不在本条口径之列，周均拆分补的正是'
        '汇总表 m/m 留空那一格背后的算术。')
    cap_note_txt = (
        '<b>截轴</b>（' + ' / '.join(f'Exhibit {n}' for n in capped) + '）：'
        '2021 年 COVID 低基数尖峰把近 12 个月压成窄带，故对 y 轴设上界。'
        '上界不是拍的：设在「除最极端那一个月之外的最大值」之上，'
        '使越界读数集中在同一个月份上、图上每个红色数字都有唯一锚点；'
        '<strong>超界的点一个都不删</strong>，柱端加断口符号、点画成红色空心圈，'
        '真实值以红色竖排数字标在图上，并在各图图注里逐条列出「哪个月、哪条序列、多少」。'
    ) if capped else '<b>截轴</b>：本期数据没有需要截轴的离群月，各图 y 轴均按数据自适应。'

    # ── 「本页各图从哪个月起画」：现读已装配的 exhibits，一个全称断言都不写 ──
    # 这句话在本页写坏过两回：「全页 comp 图同一起点」（Ex11 放宽到 Sep-17 后成假）、
    # 「本页时序图的窗口左端统一取 2016-01」（Ex14 起于 Dec-15，比它还早）。
    # 判据本来就在 payload 里：左端就写在每张图的 xlabels[0] 上，数一遍即可。
    # ⚠️ 2026-08-19（第三次改）：上一版首句写的是「<b>各图的左端并不齐</b>」，随后逐张
    # 点名 —— 可是判据 `xlabels[0][3:4] == '-'` 把**横轴不是月份**的图过滤掉了，那几张
    # 既不在任何一组里，整条注也没有一句限定语说「这条判据只管横轴是月的图」，
    # 读者滚到那里就发现自己不在名单上。当时的例子是年桶图 Exhibit 14（横轴 2016 → 2026），
    # 它已于 2026-09-03 按页面所有者的指令删除；今天落在同一类里的是财季轴的那几张
    # SEC 图与表格型 exhibit —— **例子会变，判据不变**，所以下面这段一个图号都不写死。
    # 这一版：判据看**相邻两格差几个月**（差 1 才是月度轴），不是月度轴的当场现算列出来；
    # 首句的「并不齐」也按现算的左端种类数分支，不写死。
    _win_lab = mlab(pd.Period(WIN_START, 'M'))
    _MLAB_RE = re.compile(r'[A-Z][a-z]{2}-\d{2}$')
    _p_of = lambda a: pd.Period(pd.to_datetime(a, format='%b-%y'), 'M')
    _CADENCE = {1: '月', 3: '季', 12: '年'}

    def _cadence_of(e):
        """横轴的推进步长（月数）；标签不是整条月份格式就返回 None（例如年桶图）。"""
        xl = [str(x) for x in (e.get('xlabels') or [])]
        if not xl or not all(_MLAB_RE.match(x) for x in xl):
            return None
        if len(xl) == 1:
            return 1
        ps = [_p_of(x) for x in xl]
        steps = {(b - a).n for a, b in zip(ps, ps[1:])}
        if len(steps) != 1 or steps.copy().pop() not in _CADENCE:
            raise SystemExit(
                f'Exhibit {e["n"]}：横轴标签是月份格式，但相邻两格的间隔不是同一个数、'
                f'或不是月／季／年（实测间隔 {sorted(steps)}）—— 页尾「本页月度图…」'
                f'那一段没法如实描述这张图。先决定它的横轴怎么说，再改这里的判据。')
        return steps.pop()

    # 分桶走模块级的 partition_cadence()（正文块 §8）：kind:'table' 没有横轴，
    # 留在这条判据里会让页尾印出「本页另有 N 张的横轴不是逐月月份轴：Exhibit 18」，
    # 而那是一张 HTML 表 —— 读者会去找一根不存在的轴。
    _month_ex, _nonmonth, _tbl_axis = partition_cadence(ex, _cadence_of)
    _starts = {}
    for _n, _a, _k in _month_ex:
        _starts.setdefault(_a, []).append(_n)
    _late_lab = sorted((a for a in _starts if _p_of(a) > _w0), key=_p_of)
    _early_lab = sorted((a for a in _starts if _p_of(a) < _w0), key=_p_of)
    # CSV 比窗口左端更早的那几个月：走 win() 的图把它们切在窗外。这不是「数据下限」，
    # 是**截断** —— 上一版只解释了左端为什么不同，没有一句说「有真实数据没画」。
    _cut_m = [p for p in df.index if p < _w0]
    WINDOW_NOTE = (
        (f'<b>本页月度图的左端并不齐</b>（本期共 {len(_starts)} 种，现读 payload，'
         f'不写死图号）：' if len(_starts) > 1 else
         f'<b>本页月度图的左端本期恰好只有一种</b>（现读 payload，不写死图号）：')
        + '；'.join(f'自 {a} 起的是 Exhibit ' + ' / '.join(str(n) for n in ns)
                    for a, ns in _starts.items())
        + f'。走 <code>win()</code> 的图左端取常量 WIN_START = {_win_lab}'
        + (f'，本期共 {len(_starts.get(_win_lab, []))} 张落在这里'
           if _win_lab in _starts else '，但本期没有一张图的左端正好落在这里')
        + (f'；起点更<b>晚</b>的（{"、".join(_late_lab)}）是那条序列本身晚于这个常量'
           if _late_lab else '')
        + (f'；起点更<b>早</b>的（{"、".join(_early_lab)}）是画全历史、用 '
           f'<code>first_valid_index()</code> 取左端的图，压根不过 <code>win()</code> —— '
           f'所以本页确实有图画在 {_win_lab} 之前，别把这个常量当成全页的左端'
           if _early_lab else '')
        + '。'
        + (f'<b>{_win_lab} 之前的月份不是没有数，是没画</b>：'
           f'<code>series/cost.csv</code> 自 {mlab(df.index[0])} 起，'
           f'早于 WIN_START 的有 {len(_cut_m)} 个月'
           f'（{"、".join(mlab(p) for p in _cut_m)}），'
           f'那 {len(_cut_m)} 个月里 CSV 的 {len(need)} 个源列中有 '
           f'{sum(int(df.loc[_cut_m, c].notna().any()) for c in need)} 列是有值的；'
           f'走 <code>win()</code> 的图把它们切在窗口外（左端更早的那几张见上）。'
           if _cut_m else
           f'<code>series/cost.csv</code> 的第一个月就是 {mlab(df.index[0])}，'
           f'不早于 WIN_START，本期没有哪一格是被窗口切掉的。')
        + window_note_tail(_nonmonth, _tbl_axis))
    NOTES = [
        # ⚠️ 2026-08-19：原文写死「本页解析 2016-01 以来全部新闻稿」（引的是 HIST_START）。
        # 那是图窗常量，不是抓取范围：series/cost.csv 第一行是 2015-12，Exhibit 14 就画着
        # 那一格。两句在同一个页面里对不上。范围改成现读 CSV 的第一个月。
        # 两条腿各自喂哪几张图，逐张现读 payload 点名（正文块 §4）——
        # 原文写的是「数据源（唯一）」，本轮接进 SEC 腿之后那个「唯一」当场成假话，
        # 而它排在页尾第一条。改法照 build/mrbase.py 的规矩：**收窄主语**，
        # 不是在别处补一句「不过某几张除外」。
        note_datasource(df, ex, SEC_EX, table_n=table['n']),
        # 紧跟着一条口径警告：两条腿差在哪、差多少、为什么不能放一根轴（正文块 §5）。
        note_two_source(df, _FY_ALL, _SEG_ALL, rev_ex=REV_EX),
        ('<b>4-4-5 零售日历</b>：零售月为 4 周或 5 周（周日截止），4 周与 5 周月份的'
         '净销售额绝对值<strong>不可直接环比</strong>。'),
        ('<b>核心 comp</b> = 公司披露的「剔除汽油价格变动与汇率影响」的可比销售；'
         '报告口径为未调整值。两者之差按地区拆开即 Exhibit 6。'),
        ec_note,
        WINDOW_NOTE,
        (f'<b>53 周财年</b>造成个别 1 月的周数与上年同月不同（{wk_txt}）。'
         '公司披露的 comp 已按可比周调整；<strong>净销售额同比是公司报告值，'
         '其基期是同样周数的上年错位窗口</strong>，与图上相邻的柱不是同一区间。'
         '这句话不是引述公司的说法，是<b>在本页数据上实测过的</b>：' + WK_EVID),
        WEEK_CAL_NOTE,
        # 原文两处都是假话：那段预录音频**不是电话留言**（2024 年起改成挂在 IR 网站的
        # 音频，只挂一周），而且「仅…口头披露」也不成立 —— 客单与客流每季都写在
        # 10-Q / 10-K 的 MD&A 里，8-K 的 EX-99.2 还按地区给。真正的理由是**频率**，
        # 不是拿不到（正文块 §6）。
        note_ticket_traffic(_TKT_ALL, ex_tkt=_EX_TKT),
        (f'<b>Stacks</b>（Exhibit {" / ".join(str(n) for n in _STACK_NS)}）'
         '= 同一零售月过去 N 年核心 comp 之和，用于剔除单年基数扰动看趋势。'),
        cap_note_txt,
        ('<b>核对表保持官方原始单位</b>：净销售额为 $bn、comp 与 y/y 为百分比、'
         '周数与仓库数为个数，均未换算，可直接拿去和官网新闻稿逐条对。'),
        ('本页图表版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，'
         '不含其研究观点或数据。仅供个人研究，不构成投资建议。'),
    ]

    Lr = df.iloc[-1]
    tail13 = [mlab(p) for p in d13.index]
    # 抬头带上核心 comp 与净销售额 y/y 的**环比方向**：只写水平值时，一个从 +8.0%
    # 掉到 +7.0% 的月份在抬头上看仍然是「+7.0%」，读者要翻到汇总表才知道在减速。
    # 抬头不该只报一个方向的事实（复查对 cme 抬头报的就是这一条）。
    mm_tc = ppdiff(sget('tc_a', cur) - sget('tc_a', prv))[0]
    mm_ns = ppdiff(sget('ns_yoy', cur) - sget('ns_yoy', prv))[0]
    headline = (f'核心 comp（除油汇）{dsp(Lr["tc_a"], 1, "%")[0]}（{mm_tc} m/m）· '
                f'报告口径 comp {dsp(Lr["tc_r"], 1, "%")[0]} · '
                f'净销售额 ${Lr["net_sales_bn"]:.2f}bn（{dsp(Lr["ns_yoy"], 1, "%")[0]} y/y，'
                f'{mm_ns} m/m）· 仓库数 {iv(Lr["wh_total"])}（US & PR {iv(Lr["wh_us"])}）')

    mrwin.layout_all(ex)

    payload = {
        # 构建日期不进 JSON：进了以后每天跑都会 diff，monthly_run 的幂等检查永久失效。
        # 页面上的新鲜度信号绑数据月份（data_through），不绑构建日期。
        'ticker': 'cost',
        'tracker': 'COST Monthly Sales Tracker',
        'title': f'Costco Wholesale (COST): 月度销售跟踪 — {LATEST.year}年{LATEST.month}月',
        'data_through': str(LATEST),
        'through_label': f'零售月 {LATEST.strftime("%b %Y")}（{iv(Lr["weeks"])} 周）',
        # 月数按 CSV 实际首末月算，不能用 len(df)：CSV 从 2015-12 起，
        # 而 Ex2 的时间轴自 HIST_START(2016-01) 起，两者差一个月，写死会和图对不上。
        'subtitle': subtitle_for(df, _FY_ALL, _SEG_ALL, LATEST, iv),
        # 规矩 13：只留一行数据条，叙述性 bullets 里的数字全部在下面的表和图里。
        # 正负号一律交给 f-string 的 '+' 标志，不能写死字面量（负值会印成 '+-0.6%'）。
        'headline': headline,
        # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
        # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
        'brief': compose_brief(df),
        # 名词释义。与 brief 的分工写在 assets/page.js 那一段注释里：
        # brief 说「**这个月**这组读数该怎么读」，每月重写；
        # glossary 说「**这些词**是什么意思」，一年到头不动。页面上它排在所有图之前 ——
        # 不认识词的人是在看第一张图之前卡住的。
        'glossary': compose_glossary(df, _FY_ALL, _TKT_ALL, _SEG_ALL, exn=_GLOSS_EXN),
        'hub_line': (f'核心 comp {dsp(Lr["tc_a"], 1, "%")[0]}（{mm_tc} m/m）· '
                     f'净销售额 ${Lr["net_sales_bn"]:.2f}bn（{dsp(Lr["ns_yoy"], 1, "%")[0]} y/y）'),
        'source': SRC,
        'xlabels': tail13,
        'xlabels_long': [mlab(p) for p in df.index],
        'summary': summary,
        'exhibits': ex,          # 已在上面过完 axisfmt.fix_all（幂等，这里不重复调）
        'table': table,
        'notes': NOTES,
        'footer': footer_for(ex),
    }

    # 抬头那半句「官方发布于 X」：查的是**台账里 LATEST 这个月**的发布日，不是「最近一条」——
    # 拿别的月份的发布日安到本月数据上，页面照样理直气壮地印出来。
    # 查不到就把整个字段省掉（不能写 None、不能写空串：assets/page.js 判的是字段在不在）。
    src_date = _source_dates().lookup(SERIES_DIR, 'cost', str(LATEST))
    if src_date:
        payload['source_date'] = src_date

    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cost')

    print(f'cost: 数据截至 {LATEST} | CSV 共 {len(df)} 个月 {df.index[0]} → {df.index[-1]}')
    print(f'53 周周数错位月份（自动识别）: {sorted(str(p) for p in WEEK_BREAKS)}'
          f' | Ex4 窗口内画线: {[str(d.index[i]) for i in b4]}')
    print('截轴（自动定界）: ' + ('无' if not capped else ', '.join(
        f'Ex{e["n"]}→{e["ycap"]:.0f}%' for e in ex if e.get('ycap') is not None)))
    print(f'Exhibit 1 汇总表 + Exhibit 2-{ex[-1]["n"]} 共 {len(ex)} 张图 + '
          f'Exhibit {table["n"]} 核对表 → {os.path.relpath(OUT, ROOT)} '
          f'({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
