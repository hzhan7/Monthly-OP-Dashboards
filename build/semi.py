# -*- coding: utf-8 -*-
"""半导体组横截面（台积电 / 日月光 / 联发科 / 南亚科 / 联电 / 世芯 / 创意）—— 写出 data/semi.js。

═══════════════════════════════════════════════════════════════════════════
这是本仓口径最干净的一组横截面，理由要说清楚 —— 它决定了本页不做什么
═══════════════════════════════════════════════════════════════════════════
交易所那几张横截面页要先解决「这些数能不能放一起」：四种货币、张数与金额混着、
乘数是各所自选的产品设计参数，于是 `/exchanges12/` 要造一套定基名义额、
`/exchanges-apac/` 要锁基期汇率。**本页一样都不需要**：

  · 同一条法规 —— 台湾《证券交易法》要求上市公司**次月 10 日前**公告上月营收，
    七家公告的是同一个法定字段（合并营业收入净额），不是七种自选口径；
  · 同一个单位 —— 七家的 MOPS 申报货币都是新台币；
  · 同一个节奏 —— 七家的 LAG 落在次月第 7–15 天（`build/roster.py`），
    没有哪一家要等季报才出数。

**所以本页不折汇率，一个字都不折。** 七条线都以新台币计量，折美元只是把同一个常数
乘进每一条线 —— 增长率一点不变，却让读者以为这里做过汇率处理。
（唯一的例外是世芯，它的功能货币是美元，新台币栏是逐月折算值；见下面「世芯」那一段。）

⚠ 顺带一条**本页不能有的东西**：`series/fx.csv` 里**根本没有新台币**（那张表是 10 个
币种：AUD/BRL/CAD/CHF/EUR/GBP/HKD/JPY/SEK/SGD）。全仓唯一的 NTD/USD 序列是
`series/tsm_fx.csv`，由 `fetch/tsm.py` 维护。本页一条汇率都不用，所以两张表都不读 ——
写在这里是因为「横截面页要折汇率」是从别的横截面页继承来的**错误直觉**，
下一个人多半会先去找 `fx.csv` 里的 TWD，然后找不到。

═══════════════════════════════════════════════════════════════════════════
这页要回答什么 —— 把七条月营收画在一起本身**不是**分析
═══════════════════════════════════════════════════════════════════════════
页面所有者 2026-09-22 的原话：「只是数据的简单叠加。最主要是要给出分析……背后是否有
什么逻辑可以挖掘，对于投资有没有指导意义」。这一节是对那句话的回答，也是本页此后
增删任何一张图的判据。

**一、机制在哪里。** 七家是同一笔终端需求在链条上的七个观测点，但确认时点、价值捕获、
需求来源三样都不同 ⇒ 跨层不是零和（相加是重复计算），同层才接近零和。
所以本页只问两类问题：「哪一层在动」与「同层两家谁在赢」。

**二、逐条检验过的假说，结论写在对应图注里，负的也写。** 这几条都做过零假设校准
或样本外检验，不是看图说话：
  · 「上游领先下游」—— **证伪**。六家对台积电挑遍 ±6 个月错位，没有一家的提升
    跑得赢「在两条无关但同样自相关的序列上挑最优错位」碰巧得到的提升
    （相位随机化替代序列现算，见 `_leadlag()`）。⇒ 本页**没有**领先滞后图。
  · 「代工与封测同步」—— **成立**，而且是本页唯一能直接用的正面结论：三家同期相关
    就是最高，错位没好处。可作同月参照，**不是预测**。
  · 「比值能读出价值往哪层走」—— **多数证伪**。比值的增速恒等于两条同比线之差，
    新内容只有水平；而十组比值的水平在单位根检验下都没有锚。⇒ 只留一张
    （先进 vs 成熟制程），理由写在那张图的图注里。
  · 「同比高 = 强」—— **证伪**，而且是本页最容易被误读的一处。见 ⟨ex:state⟩。
  · 「设计服务是领先指标」—— **证伪**：世芯对组内六家的相关全为负且都很弱，
    它的月营收由少数几个项目的排程决定。

**三、不靠推断的那一列。** MOPS 月营收申报表要求同比增减达 ±50% 者说明原因，
那是法定申报栏。本页把触发月的原文照引，并对有月度分部列的家用它自己的分部数
当场对账（⟨ex:official-check⟩）—— 这是页上唯一「公司自己解释自己」且可验证的材料。

**四、边界写在页面上，不藏在代码里。** 不能读份额（凑不出闭合分母）、不能读盈利
（只有营收）、不能择时（上面第二条）、不能用比值判贵贱（没有锚）。页尾第一条就是这个清单。

⚠ **加图之前先过一遍这四条。** 本页拒绝过的图比画上的多，拒绝的理由都在图注里 ——
那些理由本身就是分析的一部分，删掉它们等于把页面退回「数据叠加」。

═══════════════════════════════════════════════════════════════════════════
**本页不做跨家加总，一次都不做** —— 与 `/exchanges-apac/` 不画份额是同一类判断
═══════════════════════════════════════════════════════════════════════════
亚太那页不画份额，是因为四家法域隔离、不在同一个池子里抢单，分母只能是自己圈的。
本页的理由不同，而且更硬：**这七家在同一条价值链的不同层，相加是重复计算。**

    设计            联发科（SoC）、世芯 / 创意（ASIC 设计服务）
    代工            台积电（先进制程）、联电（成熟制程）
    封装测试        日月光
    存储            南亚科

世芯与创意的一颗 ASIC，设计费记在它们的营收里，晶圆再向台积电下单、记进台积电的营收，
封测再交给日月光、记进日月光的营收 —— **同一颗芯片在这张表里至少被数三次**。
所以本页上不会出现「半导体组合计」「七家总营收」「谁占几成」，一个都没有。
首页那条「不做跨家加总」的总规矩（`index.html` 第 2 条）在这一组上不是量纲问题，
是**重复计算**问题；两种理由不一样，别互相替换。

⇒ 能问的是两类问题，本页只画这两类：
  ① **谁在长**（指数化、同比、离散度）—— 增长率不需要加总；
  ② **同一个月各家差多少**（同比矩阵、最新月横比）—— 比的是率，不是份额。

═══════════════════════════════════════════════════════════════════════════
世芯（alchip）：唯一一家新台币栏是折算值的
═══════════════════════════════════════════════════════════════════════════
`build/mrspecs/alchip.py` 把它的**美元**栏定为 `value`（功能货币实绩，MOPS 官方栏），
新台币栏放进 `alt` 且 `summable=False` —— 各月用各月的换算汇率，十二个月相加
不等于官方本年累计。

本页仍然取它的**新台币栏**，理由与那一页不冲突：
  · 那一页要做季度桥 / QTD / YTD / TTM，全部依赖**可加总**，所以只能用美元栏；
  · 本页只做同比与指数化，**两者都不需要加总**，需要的是七家同一个计量货币。
  · 而且新台币栏是它**按法规申报**的那个数 —— 台湾市场看到的就是这个数。
⇒ 取新台币栏是对的，但它与另外六家**不是同一种数**（那六家是原生记账数）。

**这件事有多大，本轮实测过，答案是「小」** —— 所以它是页尾的一条说明，不是一张图。
本文件里一个数都不写死，全由 `alchip_fx_facts()` 在构建期现算：窗口两端的累计口径下，
世芯新台币增长里汇率那一份只占**很小一块**（对数分解），其余是经营。
⚠️ 但**有一个数不许印：新台币同比与美元同比之差的 pp**。世芯同比到 +200% 以上时，
那个差会印出二十几 pp，看上去像一场灾难，而当月汇率其实只动了个位数百分比 ——
pp 差随增速水平放大，是个**度量假象**。尺度无关的写法只有一个，且恒等于汇率同比：
    (1 + y_新台币) ÷ (1 + y_美元) − 1 ≡ 汇率同比
页尾那条说明印的就是它（`alchip_fx_facts()` 每轮复验这个恒等式，对不上就硬失败）。

═══════════════════════════════════════════════════════════════════════════
口径断点：**从各家自己的 spec 现读，本文件不抄一条**
═══════════════════════════════════════════════════════════════════════════
`/wealth/` 那页把 LPL 的并购表抄了一份在自己文件里，然后写了个 `_sync_lpla()`
每次构建对着 `build/lpla.py` 复核 —— 因为「改一处要改两处」这句话拦不住任何东西。
本页不抄：`BREAKS` 直接 `import mrspecs.<t>` 读 `SPEC['breaks']`（见 `load_breaks()`），
七家的断点登记表只有一份，**结构上不可能分叉**。
单公司页加一条断点，本页下一次构建就跟着有；删一条也一样。

⚠ 横截面页的断点标签**必须点名公司**：单公司页上整幅红线天然只指那一家，
本页七条线并排，不点名会被读成「七家在这里都换了口径」（同 `build/wealth.py` 的注释）。

═══════════════════════════════════════════════════════════════════════════
共同最新月与窗口
═══════════════════════════════════════════════════════════════════════════
· **发布门槛取共同最新月**，不是各家自己的最新月 —— 否则末端那几个月的「谁强谁弱」
  全是披露时点造成的假象。短板是谁、它自己更新到哪个月，由页面现算印出来。
· **序列起点七家不同**（世芯 2014-01 / 南亚科 · 联电 2013-01 / 台积电 · 联发科 ·
  创意 2016-01 / 日月光 2018-05），而日月光那个起点是**口径起点**不是「最早可得」：
  控股公司 2018-04-30 才成立，更早的月报属于前身主体（`build/mrspecs/ase.py`【1】）。
  ⇒ 七家共同覆盖的窗口从 2018-05 起。指数化基期取 **2019-01**（全仓唯一基期，
  = `build/notional.py` 的 BASE_MONTH），不取 2018-05：基期落在农历年之外的普通月份，
  七条线的起跑线才不带一次性的春节错位。

数据源（只读 series/*.csv，不下载、不写回）：
  series/tsm.csv / ase.csv / mtk.csv / nanya.csv / umc.csv / alchip.csv / guc.csv

用法: python3 build/semi.py   （可重复跑，除首行构建日期外逐字节相同）
成员没齐（CSV 缺失 / 缺列 / 全空）就打印原因并以**退出码 0** 结束 ——
`monthly_run.build_cross()` 会在成员齐了之后重跑，那不是失败。
"""
import datetime
import importlib
import os
import sys

import numpy as np
import pandas as pd

import axisfmt                     # 轴刻度格式的 Python 侧复算，只调用不修改
import exhibits                    # 图号：ORDER 定图序、正文 ⟨ex:…⟩ 占位符
import brief as B                  # 页顶 brief 的规则库（只算事实、不产文字）
import glossary as gloss           # 名词释义的版式层与护栏，全站共用
import mrwin                       # 窗口/排版的边界裁决层（DENSE 集合、layout_all），只调用不改
import payload_guard
import pctile                      # 3Y %ile 的唯一实现（CONTRACT §2）
import yoy as YOY                  # 同比口径的唯一实现（build/yoy.py），不自己写 pct_change(12)
#  ⚠ 模块别名是 YOY（大写），逐家算好的同比字典叫 **YOYS**（多一个 s）。
#    两者只差一个字母是刻意的 —— 但**不许把字典也叫 YOY**：那会把模块整个盖掉，
#    而 yoy_on() 在函数体里按名字查 YOY.mom_yoy，盖掉之后是运行期才炸的
#    AttributeError（同 build/exchanges_apac.py 文件头对 `import yoy` 的那条警告）。

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

TICKER = 'semi'
OUT = os.path.join(ROOT, 'data', f'{TICKER}.js')
PAGE_DIR = os.path.join(ROOT, TICKER)

SRC = ('Source: 七家公司按台湾《证券交易法》公告的月度合并营收（MOPS 月营收申报表 / '
       '公司 IR 月度新闻稿 / SEC 6-K）；format after Goldman Sachs GIR')

BASE_M = '2019-01'        # 指数化基期（全仓唯一基期，= build/notional.py BASE_MONTH）
WIN_SHORT = 25            # 短窗口（近两年）x 轴
LINE_H = 360              # 开了 end_label 的长历史线图必须 ≥360（docs/CHART_KINDS.md §3.9）
TBL_MONTHS = 13           # 末尾核对表的行数
HEAT_MONTHS = 30          # 同比矩阵的列数

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


# ────────────────────────────── 成员表 ──────────────────────────────
# (ticker, 页面显示名, 台股代号, 价值链层, 层内细分, 颜色)
#
# **显示名与代号都印在页面上**，所以两件事要说准：
#   · 日月光的 slug 是 `ase`，NYSE ADR 代号恰好叫 ASX —— 而 `asx` 在本仓已经是
#     ASX Limited（澳交所）。写串会同时污染两张页，且是静默污染（图照出、数全错）。
#     本页一律用台股代号（3711），不用 ADR 代号。
#   · **「价值链层」是本页的编辑分类，不是从任何一份申报里抄来的事实。**
#     它只用来分组、排序与讲解，**不参与任何一个数的计算**；汇总表的分隔条与页尾
#     说明都会点明这一点。公司自己不按这个分法披露，所以它也不该被当成口径。
# ⚠ **颜色：引擎只有 6 个数据色，本页有 7 家 —— 这不是配色偏好问题，是结构约束。**
#   `assets/charts.js` 的数据色是 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD 六个；
#   RED 是断点竖线与越界标记专用，不做数据色（`build/single.py` / `build/pools.py` 同）。
#   写一个引擎不认得的色名不会报错，会**静默退回 NAVY**（charts.js 的 col()）。
#   `build/exchanges12.py` 为同一件事定过规矩：**任何一张图都不许出现第 7 条线**，
#   成员多于六家时身份一律靠**标签**承载（heat_matrix 的行名 / grouped_bars 的 x 标签）。
#   ⇒ 本页因此有两条硬规则，下面的 `SIDE` 与 `selfcheck_colors()` 各管一条：
#     ① 七家同时出现的图**只用 heat_matrix 或 x 轴身份的柱图**，不用折线；
#     ② 折线图按 `SIDE` 拆成两半（制造 4 家 / 设计 3 家），于是 GOLD 可以在两半里
#        各用一次（日月光 / 创意）—— 两家**从不同框**，由 selfcheck_colors() 每轮验。
MEMBERS = [
    # ticker    名称      代号    价值链层        层内细分    颜色     制造/设计
    ('tsm',    '台积电',  '2330', '晶圆代工',      '先进制程', 'NAVY',  '制造'),
    ('umc',    '联电',    '2303', '晶圆代工',      '成熟制程', 'MBLUE', '制造'),
    ('ase',    '日月光',  '3711', '封装测试',      'OSAT',     'GOLD',  '制造'),
    ('nanya',  '南亚科',  '2408', '存储',          'DRAM',     'GRAY',  '制造'),
    ('mtk',    '联发科',  '2454', 'IC 设计',       'SoC',      'GREEN', '设计'),
    ('alchip', '世芯',    '3661', 'ASIC 设计服务', '世芯-KY',  'BLUE',  '设计'),
    ('guc',    '创意',    '3443', 'ASIC 设计服务', '创意电子', 'GOLD',  '设计'),
]
KEYS = [k for k, *_ in MEMBERS]
NAME = {k: n for k, n, *_ in MEMBERS}
CODE = {k: c for k, _n, c, *_ in MEMBERS}
LAYER = {k: l for k, _n, _c, l, *_ in MEMBERS}
SUBLAYER = {k: s for k, _n, _c, _l, s, *_ in MEMBERS}
COLOR = {k: c for k, _n, _c, _l, _s, c2, *_ in MEMBERS for c in [c2]}
SIDE = {k: s for k, _n, _c, _l, _sl, _col, s in MEMBERS}
#: 价值链层 → 成员，保持 MEMBERS 的先后。汇总表与「按层」的图都照它分组。
LAYERS = list(dict.fromkeys(LAYER[k] for k in KEYS))
BY_LAYER = {ly: [k for k in KEYS if LAYER[k] == ly] for ly in LAYERS}
#: 折线图的两半。**这不只是版面分组，它是一条业务轴**：左边四家自有产能（晶圆厂 /
#: 封测厂 / DRAM 厂），投的是资本支出，周期跟着产能与稼动率走；右边三家没有厂，
#: 接的是设计案，周期跟着客户的设计定案与量产爬坡走。两条周期不同步 ——
#: 这正是本页要给读者看的东西，所以按它拆图不是迁就调色板，是照业务分。
SIDES = ['制造', '设计']
BY_SIDE = {s: [k for k in KEYS if SIDE[k] == s] for s in SIDES}
#: 页面上点名一家时的统一写法，七处以上在用 —— 不要各写各的。
DISP = {k: f'{NAME[k]}（{CODE[k]}）' for k in KEYS}


def skip(msg):
    """成员没齐：打印原因并以退出码 0 结束（见模块 docstring 末段）。"""
    print(f'{TICKER}: 未生成 —— {msg}')
    sys.exit(0)


# ─────────────────────── 口径断点：现读各家的 spec ───────────────────────
def load_breaks():
    """→ [(Period, ticker, 断点说明)]，按月份排序。**本文件不抄任何一条断点。**

    单公司页的断点登记在 `build/mrspecs/<t>.py` 的 `SPEC['breaks']`（一条 = 一次
    可查证的公司行为：并表 / 出表 / 追溯重述）。本页直接 import 那七个模块现读，
    于是两边**结构上不可能分叉** —— `/wealth/` 那页靠 `_sync_lpla()` 每轮复核抄来的
    副本，是因为它抄了；本页不抄就不需要复核。

    import 失败 / 没有 SPEC / breaks 形状不对一律**抛异常**，不吞：
    断点少画一条的后果是页面上一段不可比的序列被读成连续的，
    而这种错误在图上完全看不出来（同 CONTRACT §5.2）。
    """
    out = []
    for k in KEYS:
        mod = importlib.import_module(f'mrspecs.{k}')
        spec = mod.SPEC                                  # 没有 SPEC → AttributeError，要的就是它
        for b in (spec.get('breaks') or []):
            if not isinstance(b, dict) or 'month' not in b or 'zh' not in b:
                raise SystemExit(f'build/semi: mrspecs/{k}.py 的 breaks 里有一条缺 '
                                 f'month/zh：{b!r}')
            out.append((pd.Period(str(b['month']), 'M'), k, str(b['zh'])))
    return sorted(out, key=lambda r: (r[0], KEYS.index(r[1])))


BREAKS = load_breaks()


def brk_in(idx, keys=None):
    """落在某张图横轴 `idx` 上的断点 → (break_at 下标, 竖排标签, 明细句子)。

    · 标签点名公司（横截面页的硬规矩，见模块 docstring）。同一个月有两家断点时
      合成一条线、标签并写 —— 引擎按 x 下标画线，同一格画两次只会叠在一起。
    · **`keys` 必须是这张图真正画了的那几家。** 本页的折线图按 SIDE 拆成两半，
      在制造侧那张上画联发科的断点，等于指着一条图上没有的线说「这里不可比」——
      读者只能把它按到旁边某一条上去。派生量的图（极差）传 KEYS 全员，
      并在图注里说明那是成员的断点传导进来的。
    """
    ks = set(KEYS if keys is None else keys)
    pos = {p: i for i, p in enumerate(idx)}
    hit = {}
    for p, k, _zh in BREAKS:
        if p in pos and k in ks:
            hit.setdefault(pos[p], []).append(k)
    at = sorted(hit)
    labels = ['／'.join(NAME[k] for k in hit[i]) for i in at]
    detail = [f'{DISP[k]} {p}：{zh}' for p, k, zh in BREAKS if p in pos and k in ks]
    return at, labels, detail


def brk_note(idx, keys=None,
             lead='<b>红色竖虚线 = 口径断点</b>，线右侧与左侧不可直接连比：'):
    """图注里那句断点说明。**图上没有线就不出这句话** —— 断点滚出窗口时线与文案
    一起消失，不会剩下一句假话（同 build/wealth.py 的 brk_note）。"""
    at, _lab, detail = brk_in(idx, keys)
    return (lead + '；'.join(detail) + '。') if at else ''



# ═══════════════════════════════════════════════════════════════════
# 这七家是什么关系 —— 本页的分析框架，也是「横着比」唯一说得通的理由
# ═══════════════════════════════════════════════════════════════════
# 把七条月营收画在一起，本身不构成分析。要让横比有内容，得先答一个问题：
# **这七个数为什么会一起动、又为什么不总是一起动。**
#
# 答案是它们是**同一笔终端需求在链条上的七个观测点**，但每一点的
#   ① 确认时点（设计费按里程碑、晶圆按投片、封测按出货），
#   ② 价值捕获（同一颗芯片在各层的单价完全不同），
#   ③ 需求来源（存储走自己的合约价周期，与逻辑不同步）
# 都不一样。所以：
#   · **跨层不是零和**，相加是重复计算（页尾第一条）—— 跨层能问的是「价值往哪儿走」；
#   · **同层才接近零和** —— 世芯与创意抢同一批 ASIC 案子，台积电与联电各守一端制程。
#     这正是 `/exchanges-apac/` 那页「产品级头对头才是真正的零和」的同一个判断。
#
# 下面这张表的「链上位置 / 营收怎么来」两列是**本页的编辑归纳**，不是公司的披露口径；
# 但每一条都有出处，且尽量用**公司自己的话**：能引 MOPS 官方备注的月份直接引它
# （那是法定申报栏，见 REMARK 一节），引不到才退回 spec 里已复核过的表述。
# ⚠ 台积电是七家里唯一**本仓从未在 spec 里写过它属于哪一层**的（另外六家都写了，
#   出处见下表 `src`）。所以它那一行的驱动只引它自己的 MOPS 备注原文，不替它归类。
ROLE = {
    #        链上位置        营收怎么来（编辑归纳）                     出处
    'alchip': ('ASIC 设计服务', 'NRE 里程碑 + turnkey 量产出货，按里程碑与出货批次认列，本身就是块状的',
               'build/mrspecs/alchip.py'),
    'guc':    ('ASIC 设计服务', '无晶圆厂的 ASIC 设计服务商，营收由量产出货与 NRE 里程碑构成',
               'build/mrspecs/guc.py'),
    'mtk':    ('IC 设计（fabless）', '无晶圆厂设计公司，营收按出货认列',
               'build/mrspecs/mtk.py'),
    'tsm':    ('晶圆代工（先进制程）', '',      # ← 故意留空，见上方 ⚠
               '本仓 spec 未归类；驱动只引公司自己的 MOPS 备注'),
    'umc':    ('晶圆代工（成熟制程）', 'FY2025 20-F 附注 12：公司只剩晶圆代工一个报告分部',
               'build/mrspecs/umc.py'),
    'ase':    ('封测 + EMS', 'ATM（封测及材料）与非 ATM（环旭 USI 的电子代工及其他）两块拼成，'
                             '两块的客户与周期完全不同',
               'build/mrspecs/ase.py'),
    'nanya':  ('存储（DRAM）', 'DRAM 是标准品、价格由供需缺口定，营收 = 位元出货 × 合约价，'
                               '两条腿同向时乘在一起',
               'build/mrspecs/nanya.py'),
}
#: 各家的**实测公告日**（月末后第几天）与出处。取自各 fetch/<t>.py 文件头的
#: 「发布节奏」实测统计 —— 那是本仓对这件事的权威记录（不是公司承诺，也不是法定上限）。
#: ⚠ 这一列不是花絮：它决定了**信息到达的先后**，也就决定了「互相印证」在实务上
#:   怎么用 —— 第 5 天拿到创意，第 10 天才拿到台积电。
#: ⚠ 联电这一格标的是**台湾公告日**，而本页的源是 SEC 6-K，上 EDGAR 另有滞后
#:   （见 build/roster.py 的 LAG 注释）；两者别混。
PUBDAY = {
    'nanya':  ('第 2–9 天，中位第 4', 'fetch/nanya.py 近 55 期实测'),
    'guc':    ('第 5 天（公司 IR 日历逐条预告）', 'fetch/guc.py 实测，撞假日顺延'),
    'ase':    ('第 8–11 天覆盖 96%，众数第 9', 'fetch/ase.py 99 期实测'),
    'tsm':    ('第 10 天（公司惯例踩着法定上限）', 'fetch/tsm.py 实测，最晚第 13'),
    'mtk':    ('第 7–12 天，众数第 10', 'fetch/mtk.py 67 期实测'),
    'umc':    ('台湾公告第 4–10 天；本页源为 SEC 6-K，另有滞后', 'fetch/umc.py 163 期实测'),
    'alchip': ('无自订惯例、不预告；法定次月 10 日前', 'fetch/alchip.py'),
}
#: 按「信息先后」排：先公告的排前面。用于链条表的行序 —— 比按体量或按我定的层排更有用。
PUB_ORDER = ['nanya', 'guc', 'ase', 'tsm', 'mtk', 'umc', 'alchip']

#: 同层对手（组内的）。**只有同层才接近零和**，跨层不是。组内没有同层对手的写 None。
RIVAL = {'alchip': 'guc', 'guc': 'alchip', 'tsm': 'umc', 'umc': 'tsm',
         'mtk': None, 'ase': None, 'nanya': None}


def load_remarks():
    """读 `series/mops_remarks.csv` —— 公司在 MOPS「備註／營收變化原因說明」栏填的原文。

    **这是本页唯一一处「公司自己解释自己」的数据**，也是回答「背后是什么逻辑」时
    唯一不靠推断的材料：台湾 MOPS 月营收申报表脚注第 6 条要求
    **当月营收或本年累计营收同比增减达 ±50% 者必须说明原因**，所以这一栏在触发月是
    法定申报内容，不是公关稿。

    ⚠ 两条语义必须照搬（权威在 `fetch/mops_remarks.py`，`build/mrbase.py` 的 `_remark()`
      是同一套的另一处实现 —— 本页不 import 它：那是**单公司页的底座**，
      横截面页挂上去等于把两类页面的生命周期绑死）：
      · **查不到这一行 ≠ 公司没填**。前者是本库还没收到（回补窗口之外），页面一个字都不说；
        后者是官方那一栏确实为空（落库归一成空串）。混为一谈就是替公司说了一句它没说的话。
      · **`triggered=0` 而备注非空 ⇒ 常设口径注，不得当成「增减原因」引用。**
        实测联发科连续 24 个月填同一句「海外子公司之營收係以當月平均匯率換算之」而
        一次都没触发门槛 —— 把它当成「联发科解释了营收变化」，是把一句会计口径说明
        伪造成经营评论。本页因此**只在 triggered 为真时引用原文**。
    """
    path = os.path.join(SERIES, 'mops_remarks.csv')
    out = {}
    try:
        import csv as _csv
        with open(path, encoding='utf-8') as fh:
            for r in _csv.DictReader(fh):
                out[(r['ticker'], r['month'])] = {
                    'remark': (r.get('remark') or '').strip(),
                    'triggered': str(r.get('triggered', '')).strip() in ('1', 'True', 'true'),
                    'leg': (r.get('trigger_leg') or '-').strip()}
    except OSError as e:
        # 只告警不阻断：这张表喂的是注脚，为它停掉整页不值当（同 mrbase._remark）。
        # 但告警必须响，否则「本页集体少一块」会被当成设计如此。
        print(f'[warn] 读 series/mops_remarks.csv 失败，本页不印官方备注：{e!r}')
    return out


REMARKS = load_remarks()
LEG_ZH = {'month': '当月', 'ytd': '累计', 'both': '当月与累计', '-': ''}


def remark_of(k, p):
    """→ dict 或 None。None = 本库没有这一行，页面一个字都不说。"""
    return REMARKS.get((k, str(p)))


# ────────────────────────────── 读数据 ──────────────────────────────
def read_csv(name):
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        return None
    df = pd.read_csv(p)
    if 'month' not in df.columns:
        return None
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    return df.set_index('month').sort_index()


def ntd_col(spec):
    """一家的**新台币**月营收列名 —— 从它自己的 spec 里认，不在本文件写死列名。

    六家的 `value.col` 就是新台币列；世芯的 `value.col` 是美元列（功能货币），
    新台币列在 `alt.col` 里（理由见模块 docstring「世芯」那一段）。
    两处都不是新台币列就**硬失败**：本页的全部前提是「七家同一个计量货币」，
    默默换一个列等于把那个前提悄悄取消掉。
    """
    for node in (spec.get('value'), spec.get('alt')):
        col = (node or {}).get('col')
        if col and col.endswith('_ntd_mn'):
            return col
    return None


RAW, NTDCOL, LATEST_EACH, MISSING = {}, {}, {}, []
for _k in KEYS:
    _spec = importlib.import_module(f'mrspecs.{_k}').SPEC
    _df = read_csv(_spec['csv'])
    _col = ntd_col(_spec)
    if _df is None or _col is None or _col not in _df.columns:
        MISSING.append(f'{_k}（{_spec.get("csv")} 缺失或没有新台币列）')
        continue
    _s = pd.to_numeric(_df[_col], errors='coerce').dropna()
    if _s.empty:
        MISSING.append(f'{_k}（{_col} 全空）')
        continue
    RAW[_k], NTDCOL[_k], LATEST_EACH[_k] = _df, _col, _s.index[-1]

if MISSING:
    skip('成员未就绪：' + '、'.join(MISSING))

# 共同最新月 = 七家里最慢的那家（见模块 docstring）。
LATEST = min(LATEST_EACH.values())
LAGGARD = [k for k in KEYS if LATEST_EACH[k] == LATEST]
AHEAD = [(k, LATEST_EACH[k]) for k in KEYS if LATEST_EACH[k] > LATEST]
#: 七家共同覆盖的最早月（= 起点最晚那家的起点）。
START = max(pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce').dropna().index[0] for k in KEYS)
BASE = pd.Period(BASE_M, 'M')
if BASE < START:
    skip(f'指数化基期 {BASE_M} 早于七家共同起点 {START}')
if LATEST <= BASE:
    skip(f'共同最新月 {LATEST} 不晚于基期 {BASE_M}')

#: 各家新台币月营收，**NT$bn**，截到共同最新月（各家自己的起点保留，前段是 NaN）。
NTD = {k: (pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce') / 1000.0).loc[:LATEST]
       for k in KEYS}
IDX_ALL = pd.period_range(min(NTD[k].dropna().index[0] for k in KEYS), LATEST, freq='M')
#: 七家都有值的窗口（本页多数图的横轴）。
IDX = pd.period_range(START, LATEST, freq='M')
IDX_SHORT = IDX[-WIN_SHORT:]
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def s_on(k, idx):
    """某家的 NT$bn 序列对齐到给定横轴（缺月 → NaN）。"""
    return NTD[k].reindex(idx)


def yoy_on(k, idx):
    """某家的**单月**同比（%），对齐到给定横轴。

    口径与全站唯一实现一致（`build/yoy.py` 的 mom_yoy + FLOW）：月营收是流量。
    ⚠ 不在这里写 `pct_change(12)` —— CONTRACT §6 要求同比只有一处实现。
    """
    return YOY.mom_yoy(NTD[k], YOY.FLOW).reindex(idx)


# ────────────────────────────── 格式化零件 ──────────────────────────────
def mlab(p):
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def zh(p):
    return f'{p.year} 年 {p.month} 月'


def _fin(v):
    return v is not None and np.isfinite(v)


def num(v, d=1):
    """千分位定点。负零不许从任何一条支路漏出去（'-0.0' 在页面上是个假信号）。"""
    if not _fin(v):
        return '—'
    v = 0.0 if abs(v) < 0.5 / 10 ** d else v
    return f'{v:,.{d}f}'


def pct(v, d=1, sign=True):
    """百分比。正负号交给 f-string 的 + 标志 —— 别写死字面量（CONTRACT §1）。"""
    if not _fin(v):
        return '—'
    v = 0.0 if abs(v) < 0.5 / 10 ** d else v
    return f'{v:+.{d}f}%' if sign else f'{v:.{d}f}%'


def pp(v, d=1):
    if not _fin(v):
        return '—'
    v = 0.0 if abs(v) < 0.5 / 10 ** d else v
    return f'{v:+.{d}f}pp'


def L(a):
    """np.nan → None（JSON 的 null）。CONTRACT §5.5：payload 里不许出现 NaN。"""
    return [None if not _fin(v) else float(v) for v in a]


def cls_of(v):
    """涨跌色跟着**印出来的那个数**走：印成 +0.0% 就不涂色，否则读者会看到一个
    绿色的零，以为是四舍五入吃掉了一个正数（同 build/wealth.py 的 chg）。"""
    if not _fin(v):
        return ''
    return 'pos' if round(v, 1) > 0 else ('neg' if round(v, 1) < 0 else '')


def ser(s):
    """pandas Series → pctile.py 吃的 [float | None]（按月升序，缺月 None）。"""
    return [None if not np.isfinite(v) else float(v) for v in s.values]


def spanl(a, b):
    return f'{mlab(a)}–{mlab(b)}'


# ─────────────────────── Exhibit 1：汇总表 ───────────────────────
def _mm(k):
    """环比（%）。月营收是流量，环比就是相邻两格相除，没有第二种口径。"""
    a, b = NTD[k].get(CUR), NTD[k].get(PRV)
    return (a / b - 1.0) * 100.0 if _fin(a) and _fin(b) and b else np.nan


def _yy(k):
    """单月同比（%）—— 与页上每一条同比线同源（yoy.mom_yoy + FLOW）。"""
    s = yoy_on(k, IDX)
    return float(s.loc[CUR]) if CUR in s.index and _fin(s.loc[CUR]) else np.nan


#: 逐家的 3Y 分位（值, 颜色类）。**不只是表里的一格** —— 汇总表的 note 要按它现算
#: 一句话：七家同时顶到 100 是个真事实（当月是各自近 36 个月的最高），不是坏掉的列。
#: 判「这一列有没有区分度」的是 build/pctile.py 的 24 个月回放（≥70% 钉在端点才算死列），
#: 本轮七家实测 8%–54%，都没到，所以这一列是活的，不能按 CONTRACT §2 那条留空。
PCTS = {}
SUM_ROWS = []
for _ly in LAYERS:
    SUM_ROWS.append({'kind': 'group', 'label': _ly})
    for _k in BY_LAYER[_ly]:
        _p, _c = pctile.cell(ser(NTD[_k].reindex(IDX)))
        PCTS[_k] = (_p, _c)
        SUM_ROWS.append({'label': f'{NAME[_k]} {CODE[_k]}', 'cells': [
            {'v': num(NTD[_k].get(CUR), 1)},
            {'v': num(NTD[_k].get(PRV), 1)},
            {'v': num(NTD[_k].get(YAG), 1)},
            {'v': pct(_mm(_k)), 'cls': cls_of(_mm(_k))},
            {'v': pct(_yy(_k)), 'cls': cls_of(_yy(_k))},
            {'v': _p, 'cls': _c} if _p else {'v': ''},
        ]})

#: 页面上多处要说「整页截到哪个月、被谁卡住」，一律取这一句，不要各写各的。
GATE_TXT = (f'本页所有图统一截到<b>共同最新月 {mlab(LATEST)}</b>'
            + ('（七家本月都已公告）'
               if not AHEAD else
               '，由最慢的成员 ' + '、'.join(NAME[k] for k in LAGGARD) + ' 决定；'
               + '、'.join(f'{NAME[k]} 自身已到 {mlab(p)}' for k, p in AHEAD))
            + '。各家自己更新到哪个月，看首页卡片上的月份与红点。')


def _pctile_line():
    """3Y %ile 那一列如果整列顶格，说一句为什么 —— 现算，不是固定文案。

    七家同时印 100 看上去像列坏了。它其实是「当月是各自近 36 个月的最高值」，
    而这正是本月值得记一笔的事。下个月只要有一家掉下来，这句话自己就变了；
    一家都不在 100 时整句消失。
    """
    top = [k for k in KEYS if PCTS.get(k, ('', ''))[0] == '100']
    if len(top) == len(KEYS):
        return (f' <b>本月 {len(KEYS)} 家的分位同时是 100</b> —— '
                '当月营收都是各自近 36 个月里的最高值。这一列不是坏的：'
                '判「有没有区分度」的是近 24 个月的回放（几成月份钉在区间端点），'
                '七家都远没到那条线。')
    if top:
        return (f' 其中 {len(top)} 家（{"、".join(NAME[k] for k in top)}）的分位是 100，'
                '即当月是各自近 36 个月里的最高值。')
    return ''


SUMMARY = {
    'title': f'半导体组 —— {zh(CUR)}（共同最新月）月营收与增速',
    'heads': ['本月 NT$bn', '上月 NT$bn', '去年同月 NT$bn', 'm/m', 'y/y（单月）', '3Y %ile'],
    'sep': 3,
    'rows': SUM_ROWS,
    'note': (GATE_TXT
             + ' 水平值是各家按台湾《证券交易法》公告的月度合并营收，'
             + f'本表换算成 NT$bn（原始单位 NT$mn，见末尾核对表）。'
             + 'y/y 是<b>单月同比</b>（当月 ÷ 去年同月 − 1），与页上每一条同比线同一口径；'
             + '3Y %ile 是近 36 个月百分位，区分度不足的行留空（判据与全站共用 '
             + '<code>build/pctile.py</code>）。'
             + '<b>分隔条上的「价值链层」是本页的编辑分类，不是公司的披露口径</b>，'
             + '不参与任何一个数的计算。'
             + '<b>本表没有合计行</b>：七家在同一条价值链的不同层，相加是重复计算，'
             # 不写「见页尾第 N 条」：notes 没有 exhibits 那套 id 机制，
             # 调一下顺序这个序号就成了假话，而且没有任何工具会报。
             + '理由见页尾「口径与方法说明」里讲价值链的那一条。'
             + _pctile_line()),
}


# ═══════════════════════════════════════════════════════════════════
# 派生量：全部在这里算完，页面不做任何计算（CONTRACT 抬头）
# ═══════════════════════════════════════════════════════════════════
#: 七家都算得出单月同比的最早月。日月光 2018-05 起才有序列，它的同比要等到
#: 2019-05；另外六家在 IDX 左端之前就有历史，同比从 IDX 左端就有。**不写死**。
YOYS = {k: yoy_on(k, IDX) for k in KEYS}
#: 单月同比的 **3 个月移动平均**。自身分位、方差分解、错位相关三处都用它 ——
#: 单月值的毛刺会主导「谁更反常」「哪个错位最优」这类比较，那不是口径不一致，
#: 是这几个问题本来就该在平滑一档的尺度上问。原始单月同比仍在 YOYS 里，
#: 同比矩阵与同比折线用的是那一份。
YOY3 = {k: YOYS[k].rolling(3, min_periods=3).mean() for k in KEYS}
_ok = [p for p in IDX if all(_fin(YOYS[k].get(p)) for k in KEYS)]
if not _ok:
    skip('七家没有任何一个月同时算得出单月同比')
IDX_YOY = pd.period_range(_ok[0], LATEST, freq='M')
YOY_LATE = [k for k in KEYS if YOYS[k].dropna().index[0] == _ok[0]]

#: 指数化（基期 = 100）。**用 3 个月移动平均**：月营收带农历年与出货批次的
#: 块状噪声，原始月值的中位环比在 4%–13% 之间（逐家现算见 IDXNOTE），
#: 七条线叠在一起会糊成一团。3MMA 只平滑噪声，不动增长本身 ——
#: 指数末点的离散度几乎不变，这一点在图注里现算印出来，免得读者以为平滑掉了差距。
MA = 3


def rebased(k, idx, base=None):
    """某家以 BASE_M = 100 的指数（3MMA）。基期那一格必须恰好是 100 —— 由
    selfcheck_rebased() 每轮验（同 build/exchanges_apac.py 的 selfcheck_page）。"""
    s = NTD[k].rolling(MA, min_periods=MA).mean()
    b = s.get(base or BASE)
    if not _fin(b) or not b:
        return pd.Series(np.nan, index=idx)
    return (s / b * 100.0).reindex(idx)


IDX_REB = pd.period_range(BASE, LATEST, freq='M')
REB = {k: rebased(k, IDX_REB) for k in KEYS}

#: 原始月值的噪声有多大（图注用「为什么要 3MMA」的判据，现算不写死）。
NOISE = {k: float(NTD[k].pct_change().abs().median() * 100.0) for k in KEYS}



# ── 分部交叉验证：公司说的那个原因，用它自己的分部列能不能验出来 ──────────────
# 官方备注是**公司的断言**，不是证据。七家里有两家在月度层面另外披露了分部拆分
# （日月光的 ATM / 非 ATM、创意的量产 / NRE），于是这两家的断言可以当场对账：
# 说「量产产品增加」，就该看到量产那一段的增速显著高于另一段。
# 对不上不代表公司说谎（口径可以不同），但**能对上是一条真凭据**，值得印出来。
# ⚠ 世芯没有月度分部列 ⇒ 它那句「量產產品增加」本页**验不了**，只能照引并明说验不了。
#   不许拿创意的分部去「印证」世芯 —— 那是两家公司。
SEG = {
    'ase': [('revenue_atm_ntd_mn', 'ATM（封测及材料）'),
            ('revenue_nonatm_ntd_mn', '非 ATM（EMS 等）')],
    'guc': [('revenue_turnkey_ntd_mn', '量产 Turnkey'),
            ('revenue_nre_other_ntd_mn', 'NRE 及其他')],
}


def seg_facts(k):
    """→ [{'zh', 'yoy', 'r12_yoy', 'share_now', 'share_prev'}]，算不出来返回 None。

    份额用**近 12 个月合计**算，不用单月：分部的单月占比被农历年与里程碑确认打得很碎，
    一个月的占比变动读不出结构。
    """
    cols = SEG.get(k)
    if not cols or k not in RAW:
        return None
    df, out = RAW[k], []
    tot = pd.to_numeric(df[NTDCOL[k]], errors='coerce')
    t_now = tot.loc[CUR - 11:CUR].sum()
    t_prv = tot.loc[CUR - 23:CUR - 12].sum()
    for col, zh_ in cols:
        if col not in df.columns:
            return None
        sv = pd.to_numeric(df[col], errors='coerce')
        if not _fin(sv.get(CUR)) or not _fin(sv.get(CUR - 12)):
            return None
        now, prv = sv.loc[CUR - 11:CUR].sum(), sv.loc[CUR - 23:CUR - 12].sum()
        out.append({
            'zh': zh_,
            'yoy': float(YOY.mom_yoy(sv, YOY.FLOW).get(CUR, np.nan)),
            'r12_yoy': (now / prv - 1.0) * 100.0 if prv else np.nan,
            'share_now': now / t_now * 100.0 if t_now else np.nan,
            'share_prev': now and (prv / t_prv * 100.0 if t_prv else np.nan),
        })
    return out


SEGF = {k: seg_facts(k) for k in SEG}
SEGF = {k: v for k, v in SEGF.items() if v}


# ── 各家在自己历史里的位置：增速排名与水平排名可以完全相反 ────────────────────
def state_facts(k):
    """近 12 个月合计 vs 这家自己的历史峰，以及史上最大回撤。

    **这是本页对「只是数据叠加」那条批评的正面回答之一。** 同比只说「比去年这个月
    多了多少」，它对基数一无所知：一家刚从腰斩里爬出来的公司，同比可以是三位数，
    而它的生意规模仍然远低于自己两年前的水平。把两者并排，横截面才读得出
    「谁在创新高、谁在填坑」—— 单看同比矩阵，这两种情形长得一模一样。
    """
    s = pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce').dropna().loc[:LATEST]
    r12 = s.rolling(12, min_periods=12).sum().dropna()
    if len(r12) < 13:
        return None
    cur, pk = float(r12.iloc[-1]), float(r12.max())
    dd = (r12 / r12.cummax() - 1.0) * 100.0
    return {'r12': cur, 'peak': pk, 'peak_m': r12.idxmax(),
            'gap': (cur / pk - 1.0) * 100.0 if pk else np.nan,
            'r12_yoy': (cur / float(r12.iloc[-13]) - 1.0) * 100.0 if len(r12) > 12 else np.nan,
            'maxdd': float(dd.min()), 'maxdd_m': dd.idxmin(),
            'at_high': abs(cur / pk - 1.0) < 1e-9}


STATE = {k: state_facts(k) for k in KEYS}
if any(v is None for v in STATE.values()):
    skip('近 12 个月合计算不出来（历史不足 13 个月）')
AT_HIGH = [k for k in KEYS if STATE[k]['at_high']]
BELOW = sorted((k for k in KEYS if not STATE[k]['at_high']), key=lambda k: STATE[k]['gap'])



# ── 季节性指数：月值 ÷ 当年 12 个月均值，只取**共同窗口里的完整年** ──────────
def _season():
    """→ {ticker: {月份 1-12: 指数×100}}，以及实际用到的年份清单。

    只用完整日历年（12 个月齐）—— 半年会把季节形状算成「上半年低、下半年没有」。
    年份限定在**共同窗口之内**，七家用同一批年，否则「谁的高峰在几月」比的是
    各自不同的历史时段。
    """
    yrs = [y for y in range(IDX[0].year, LATEST.year + 1)
           if all(len(NTD[k].loc[f'{y}-01':f'{y}-12'].dropna()) == 12 for k in KEYS)]
    out = {}
    for k in KEYS:
        by = {m: [] for m in range(1, 13)}
        for y in yrs:
            s = NTD[k].loc[f'{y}-01':f'{y}-12']
            mean = float(s.mean())
            if not mean:
                continue
            for p, v in s.items():
                by[p.month].append(float(v) / mean * 100.0)
        out[k] = {m: (sum(v) / len(v) if v else None) for m, v in by.items()}
    return out, yrs


SEASON, SEASON_YRS = _season()


def _peak_trough(k):
    d = {m: v for m, v in SEASON[k].items() if _fin(v)}
    if not d:
        return None, None
    return max(d, key=d.get), min(d, key=d.get)


# ═══════════════════════════════════════════════════════════════════
# 月度营收真正独有的两件事：把分母摊开，以及去掉分母看生意本身
# ═══════════════════════════════════════════════════════════════════
# 同比是一个比值，它同时被**分子**（这个月的生意）和**分母**（去年同月）驱动。
# 一张同比矩阵把两者混在一起，于是页面上最显眼的读数（南亚科 +561%）既说不清
# 「生意有多好」，也说不清「这个数接下来会怎么走」。下面两个量把它拆开：
#
#   · `BASECAL` —— **基数日历**：假设季调后的运行速率**原地不动**，未来几个月的同比
#     会自己走成什么样。这**不是预测**，是把去年同月那一串已经发生的数摊开来看。
#     它回答的是「同比接下来的变化里，有多少根本不是今年的事」。
#   · `MOM` —— **季调环比动能**：把季节性和去年同期一起去掉，只看最近三个月相对
#     前三个月。它回答「生意本身现在是在加速还是减速」，与同比高低无关。
#
# 这两个量互相独立，而且经常给出相反的指示 —— 那正是它们的价值所在。
MOM_WIN = 3          # 季调环比的窗口（3 个月 vs 前 3 个月）
BASE_FWD = 6         # 基数日历往前摊几个月


def _sa(k):
    """季调后的月营收：月值 ÷ 该月的季节指数（`SEASON` 现算，见季节性那一节）。"""
    si = SEASON.get(k) or {}
    s = pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce').dropna().loc[:LATEST]
    if not si or any(not _fin(si.get(m)) or not si.get(m) for m in range(1, 13)):
        return None
    return pd.Series({p: float(v) / (si[p.month] / 100.0) for p, v in s.items()}).sort_index()


SA = {k: _sa(k) for k in KEYS}


def _mom(k):
    """→ {'now','prev','med'}：季调后 3 个月 vs 前 3 个月的百分比变化（**不年化**）。

    ⚠ **不年化是刻意的。** 把一个三个月的变化折成年率，在块状序列上会炸开 ——
    本轮实测世芯的年化读数能到五位数（它刚从一次腰斩里出来），那个数没有任何
    可读性，印在页面上只会让整张表失去刻度。不年化的版本有界、可横比，
    而且与「自身历史中位」并排时读者立刻知道这一档算大还是算小。
    """
    sa = SA.get(k)
    if sa is None or len(sa) < MOM_WIN * 2 + 12:
        return None
    q = sa.rolling(MOM_WIN, min_periods=MOM_WIN).mean()
    r = (q / q.shift(MOM_WIN) - 1.0) * 100.0
    if not (_fin(r.get(LATEST)) and _fin(r.get(LATEST - MOM_WIN))):
        return None
    return {'now': float(r.loc[LATEST]), 'prev': float(r.loc[LATEST - MOM_WIN]),
            'med': float(r.abs().median())}


MOM = {k: _mom(k) for k in KEYS}
MOM = {k: v for k, v in MOM.items() if v}


def _basecal(k):
    """→ (未来 BASE_FWD 个月的 Period 列表, 机械同比路径)。算不出来返回 None。

    做法：取最近 MOM_WIN 个月的**季调**均值当运行速率，再按各月的季节指数还原成
    「如果生意原地不动，那个月会报多少」，除以**去年同月的真实值**。
    分子是一个不变的假设，分母全是已经发生的事实 ⇒ 路径的形状完全由分母决定。
    """
    sa, si = SA.get(k), (SEASON.get(k) or {})
    if sa is None or not si:
        return None
    s = pd.to_numeric(RAW[k][NTDCOL[k]], errors='coerce').dropna()
    rr = float(sa.loc[LATEST - (MOM_WIN - 1):LATEST].mean())
    months, path = [], []
    for i in range(1, BASE_FWD + 1):
        m = LATEST + i
        base = s.get(m - 12)
        months.append(m)
        path.append((rr * si[m.month] / 100.0 / float(base) - 1.0) * 100.0
                    if _fin(base) and base else np.nan)
    return months, path


_bc = {k: _basecal(k) for k in KEYS}
_bc = {k: v for k, v in _bc.items() if v}
BASECAL = {k: dict(zip(('months', 'path'), v)) for k, v in _bc.items()}
BASE_MONTHS = BASECAL[KEYS[0]]['months'] if BASECAL else []
#: 「同比在未来 BASE_FWD 个月里会因为分母变动多少」—— 排序用。
BASE_DRIFT = {k: (BASECAL[k]['path'][-1] - _yy(k))
              for k in BASECAL if _fin(BASECAL[k]['path'][-1]) and _fin(_yy(k))}


# ═══════════════════════════════════════════════════════════════════
# 互相印证：先说哪两家在业务上真的连着，再看数据认不认
# ═══════════════════════════════════════════════════════════════════
# 页面所有者 2026-09-22 的问题：「他们的业务之间是否有可以互相印证的东西，不管是
# 竞争关系或者是上下游的关系，能否因此推导出一些逻辑」。
#
# ⚠ **本仓没有任何一条关于这七家之间业务关系的已核事实**（谁是谁的客户、谁持有谁的股份，
#   七份 spec 里一个字都没有），所以本页**不断言供应关系**。能用的只有一条不需要外部
#   事实的：**封测是晶圆产出之后的工序，这是业务定义本身**。以此为假说，让数据来判。
#
# 检验设计（三道，缺一条结论就不成立）：
#   ① **三种变换都要过**。12 个月滚动同比好看但高度自相关；必须同时看 3MMA 同比与
#      **平稳变换**（季调对数水平的环比）。本轮实测：滚动口径下连通配对 +0.68，
#      而它的自助区间**含 0** —— 也就是说那个最漂亮的数恰恰是最不能用的。
#   ② **安慰剂要够干净**。同公司另一段业务（日月光的 EMS）与同业（南亚科）都不够 ——
#      前者共享公司层因素、后者共享行业景气。所以另取**行业外**对照
#      （Costco 零售 / AXP 消费信贷 / CME 成交量 / HKEX 成交额）。
#   ③ **扣掉共同半导体周期之后还得剩下**（偏相关）。这一条是决定性的：
#      若归零，"上下游印证"就只是"同处一个景气"，机制说法不成立。
#
# 结论（数由 CHAINX 现算，措辞跟着它走）：代工↔封测**三道全过**；
# 而「创意的量产（晶圆转售）应当跟代工同步」这条**被证伪**（平稳变换下偏相关归零）。
CHAIN_MIN = 36          # 实时扩张窗口拟合的起步样本


def _sa_series(k, col=None):
    """某家（或某个分部列）的季调序列。季节指数用 SEASON（共同窗口完整年现算）。"""
    si = SEASON.get(k) or {}
    if not si:
        return None
    df = RAW.get(k)
    c = col or NTDCOL.get(k)
    if df is None or c not in df.columns:
        return None
    v = pd.to_numeric(df[c], errors='coerce').dropna().loc[:LATEST]
    return pd.Series({p: float(x) / (si[p.month] / 100.0) for p, x in v.items()}).sort_index()


def _leg(k, col=None):
    """一条「腿」的两种变换：3MMA 单月同比（可读，单位是 pp）与平稳变换（稳健）。"""
    df = RAW.get(k)
    c = col or NTDCOL.get(k)
    if df is None or c not in df.columns:
        return None
    raw = pd.to_numeric(df[c], errors='coerce').dropna().loc[:LATEST]
    sa = _sa_series(k, col)
    if sa is None or len(raw) < 40:
        return None
    return {'y3': YOY.mom_yoy(raw, YOY.FLOW).rolling(3, min_periods=3).mean(),
            'st': np.log(sa.rolling(3, min_periods=3).mean()).diff()}


LEGS = {
    'tsm':     _leg('tsm'),
    'umc':     _leg('umc'),
    'ase_atm': _leg('ase', 'revenue_atm_ntd_mn'),
    'ase_non': _leg('ase', 'revenue_nonatm_ntd_mn'),
    'guc_tk':  _leg('guc', 'revenue_turnkey_ntd_mn'),
    'nanya':   _leg('nanya'),
}
LEG_ZH2 = {'tsm': f'{NAME["tsm"]}（先进制程）', 'umc': f'{NAME["umc"]}（成熟制程）',
           'ase_atm': f'{NAME["ase"]} ATM（封测）', 'ase_non': f'{NAME["ase"]} 非 ATM（EMS 组装）',
           'guc_tk': f'{NAME["guc"]} 量产（晶圆转售）', 'nanya': f'{NAME["nanya"]}（DRAM）'}


def _corr_on(a, b, key):
    x, y = (LEGS.get(a) or {}).get(key), (LEGS.get(b) or {}).get(key)
    if x is None or y is None:
        return np.nan, 0
    d = pd.DataFrame({'x': x, 'y': y}).dropna()
    return (float(d['x'].corr(d['y'])), len(d)) if len(d) > 25 else (np.nan, len(d))


def _partial_on(a, b, key):
    """扣掉共同半导体周期后的偏相关。因子 = 不含这两条腿的成员，各自标准化后取均值。"""
    x, y = (LEGS.get(a) or {}).get(key), (LEGS.get(b) or {}).get(key)
    if x is None or y is None:
        return np.nan
    base = {k: YOY.mom_yoy(NTD[k], YOY.FLOW).rolling(3, min_periods=3).mean()
            if key == 'y3' else (LEGS.get(k) or {}).get('st')
            for k in KEYS if k not in (a, b) and k not in ('ase',)}
    base = {k: v for k, v in base.items() if v is not None}
    if key == 'st':
        base = {k: np.log(_sa_series(k).rolling(3, min_periods=3).mean()).diff()
                for k in KEYS if k not in (a, b) and _sa_series(k) is not None}
    m = pd.DataFrame(base).dropna()
    if len(m) < 30:
        return np.nan
    z = (m - m.mean()) / m.std(ddof=0)
    f = z.mean(axis=1)
    d = pd.DataFrame({'x': x, 'y': y, 'f': (f - f.mean()) / f.std(ddof=0)}).dropna()
    if len(d) < 30:
        return np.nan
    rxy, rxf, ryf = d['x'].corr(d['y']), d['x'].corr(d['f']), d['y'].corr(d['f'])
    den = np.sqrt(max(1e-12, (1 - rxf ** 2) * (1 - ryf ** 2)))
    return float((rxy - rxf * ryf) / den)


#: 待检验的配对。`kind` 决定它在表里怎么标：工序连通 / 同层竞争 / 安慰剂。
CHAIN_PAIRS = [
    ('tsm', 'ase_atm', '工序', '封测是晶圆产出之后的工序 —— 业务定义本身，不需要外部事实'),
    ('umc', 'ase_atm', '工序', '同上，成熟制程这一端'),
    ('tsm', 'guc_tk', '工序', '量产（turnkey）是晶圆转售，理应跟着代工产出走'),
    ('ase_atm', 'ase_non', '安慰', '同一家公司的另一段业务，但 EMS 是电子组装、不在半导体链上'),
    ('nanya', 'tsm', '安慰', '同属半导体但自有厂、自有市场，与代工无工序关系'),
]


def _chainx():
    out = []
    for a, b, kind, why in CHAIN_PAIRS:
        row = {'a': a, 'b': b, 'kind': kind, 'why': why}
        for key in ('y3', 'st'):
            r, n = _corr_on(a, b, key)
            row[f'r_{key}'], row[f'n_{key}'] = r, n
            row[f'p_{key}'] = _partial_on(a, b, key)
        out.append(row)
    return out


CHAINX = _chainx()
#: 「三道全过」的判据：两种变换的相关都 ≥0.5，且**平稳变换下的偏相关** ≥0.3。
#: 偏相关那一条是决定性的 —— 它问的是「扣掉行业景气之后还剩不剩」。
def _passes(r):
    return (_fin(r['r_y3']) and _fin(r['r_st']) and _fin(r['p_st'])
            and r['r_y3'] >= 0.5 and r['r_st'] >= 0.5 and r['p_st'] >= 0.3)


def _chain_gap(up='tsm', down='ase_atm'):
    """关系站得住 ⇒ **背离本身成为信号**。这里量的就是背离。

    做法：用**扩张窗口**（只用当期之前的数据）把下游对上游回归一次，残差 = 下游比
    「按历史关系该有的样子」高出多少 pp。扩张窗口是必须的 —— 用全样本拟合出来的
    残差含未来信息，会把「现在很反常」这件事系统性地做小（本仓在别处也踩过这个坑）。
    """
    x, y = (LEGS.get(up) or {}).get('y3'), (LEGS.get(down) or {}).get('y3')
    if x is None or y is None:
        return None
    d = pd.DataFrame({'x': x, 'y': y}).dropna()
    if len(d) < CHAIN_MIN + 12:
        return None
    idx, res = [], []
    for i in range(CHAIN_MIN, len(d)):
        tr = d.iloc[:i]
        b, a = np.polyfit(tr['x'].values, tr['y'].values, 1)
        idx.append(d.index[i])
        res.append(float(d['y'].iloc[i] - (a + b * d['x'].iloc[i])))
    r = pd.Series(res, index=pd.PeriodIndex(idx, freq='M'))
    run = 1
    for i in range(len(r) - 1, 0, -1):
        if (r.iloc[i] - r.iloc[i - 1]) * np.sign(r.iloc[-1] - r.iloc[-2]) > 0:
            run += 1
        else:
            break
    return {'s': r, 'now': float(r.iloc[-1]), 'med': float(r.median()),
            'sd': float(r.std()), 'pct': float((r < r.iloc[-1]).mean() * 100),
            'lo': float(r.min()), 'lo_m': r.idxmin(), 'hi': float(r.max()),
            'hi_m': r.idxmax(), 'run': run, 'up': up, 'down': down}


CHAIN_PASS = [r for r in CHAINX if r['kind'] == '工序' and _passes(r)]
CHAIN_FAIL = [r for r in CHAINX if r['kind'] == '工序' and not _passes(r)]
#: **只有在那条关系三道全过时才算背离** —— 关系都不成立的话，「偏离」偏离的是什么？
CHAIN_GAP = (_chain_gap() if any(r['a'] == 'tsm' and r['b'] == 'ase_atm'
                                 for r in CHAIN_PASS) else None)

# ── 自身历史分位：把七条振幅差一个数量级的同比放到同一把尺上 ────────────────
# **这是本页对「南亚科 +561% 与日月光 +46% 没法比」的正面解法。**
# 同比的振幅逐家差一个数量级（南亚科 σ≈189pp，日月光 σ≈13pp），所以「谁的同比高」
# 量的是「谁的生意天生波动大」，不是「谁这个月更反常」。把每家的同比换成
# **它在自己历史里的百分位**，七家就落到同一把 0–100 的尺上，可以横着读。
#
# 三条口径决定：
#   · 用**自己的全部历史**做分母，不是共同窗口 —— 问的是「对这家自己而言有多反常」，
#     那就该用它自己见过的全部月份。各家历史长度不同（88–152 个同比月），
#     这是特征不是缺陷，但下面的图注要说出来。
#   · 用 **3 个月移动平均的同比**：单月分位的月度churn 是 14.3 点，3MMA 只有 7.4 点，
#     AR(1) 从 0.77 升到 0.94。分位本来就是给人读「位置」的，噪声大了就读不出位置。
#   · **至少 36 个同比月**才给分位，不够的留空 —— 不到三年的历史算不出「反常」。
PCT_MIN = 36


def _pctile_own(s):
    """→ 每个月在**这条序列自己**的历史里排第几（0–100，中位秩）。样本不足留 NaN。"""
    v = s.dropna()
    out = pd.Series(np.nan, index=s.index)
    if len(v) < PCT_MIN:
        return out
    arr = v.values
    for i, (p_, x) in enumerate(zip(v.index, arr)):
        if i + 1 < PCT_MIN:
            continue
        hist = arr[:i + 1]
        out.loc[p_] = ((hist < x).sum() + 0.5 * (hist == x).sum()) / len(hist) * 100.0
    return out


#: 各家 3MMA 同比在自身全历史里的分位（全历史 = 不截到共同窗口）。
YOY3_FULL = {k: YOY.mom_yoy(NTD[k], YOY.FLOW).rolling(3, min_periods=3).mean() for k in KEYS}
PCT3 = {k: _pctile_own(YOY3_FULL[k]) for k in KEYS}
_pm = pd.DataFrame({k: PCT3[k].reindex(IDX) for k in KEYS}).dropna()
#: 「七家的分位散得有多开」—— 本轮最值得一看的一条：它在塌。
PCT_SPREAD = (_pm.max(axis=1) - _pm.min(axis=1)) if len(_pm) else pd.Series(dtype=float)


def _pct_now(k):
    v = PCT3[k].reindex(IDX).dropna()
    return float(v.iloc[-1]) if len(v) else np.nan


PCT_NOW = {k: _pct_now(k) for k in KEYS}
PCT_OK = [k for k in KEYS if _fin(PCT_NOW[k])]
#: 同比排名 vs 分位排名 —— 两者不一致才是这张图存在的理由。
_rk_y = {k: i for i, k in enumerate(sorted(PCT_OK, key=lambda k: -_yy(k)))}
_rk_p = {k: i for i, k in enumerate(sorted(PCT_OK, key=lambda k: -PCT_NOW[k]))}
PCT_FLIP = max(PCT_OK, key=lambda k: _rk_y[k] - _rk_p[k]) if PCT_OK else None


# ── 这七家其实是几个独立的赌注：系统性 vs 自己的那一份 ────────────────────────
def _decomp():
    """每家的 3MMA 同比里，有多少是「跟着组里那个共同周期」，多少是它自己的。

    ⚠ 组因子**不能**用六家同比的等权平均：那样算出来的「因子」其实就是南亚科
    （它的 σ 是日月光的十几倍），于是它会盖掉真正的共同周期。本轮实测这个差别很大 ——
    换成**各家先按自身历史标准化再平均**（再归一到单位方差），日月光的 R² 从 0.25
    跳到 0.65、联电从 0.04 跳到 0.44。所以下面一律用标准化因子。

    ⚠ **只印 R² 与系统性占比，不印 beta。** beta 的量纲是「每 1σ 组周期对应多少 pp
    自身同比」，而南亚科的 beta 标准误大到与零无异；一个页面上印出来会被当成参数用。
    """
    m = pd.DataFrame({k: YOY3[k] for k in KEYS}).dropna()
    if len(m) < 36:
        return None
    z = (m - m.mean()) / m.std(ddof=0)
    out = {}
    for k in KEYS:
        f = z[[c for c in KEYS if c != k]].mean(axis=1)
        f = (f - f.mean()) / f.std(ddof=0)
        r = float(np.corrcoef(m[k].values, f.values)[0, 1])
        r2 = r * r
        own = float(m[k].std(ddof=0))
        out[k] = {'r': r, 'r2': r2 * 100.0, 'own_sd': own,
                  'sys_sd': abs(r) * own, 'idio_sd': own * np.sqrt(max(0.0, 1 - r2)),
                  'sys_share': abs(r) / (abs(r) + np.sqrt(max(1e-12, 1 - r2))) * 100.0}
    return {'per': out, 'n': len(m)}


DEC = _decomp()

# ── 组内离散度：本页的核心实证 ────────────────────────────────────────
def _spread(keys, idx):
    """每月「这一组里最快的一家 − 最慢的一家」（pp）。"""
    m = pd.DataFrame({k: YOYS[k].reindex(idx) for k in keys})
    return (m.max(axis=1) - m.min(axis=1)).reindex(idx)


def _growing(idx):
    """每月「七家里有几家同比为正」。**对离群值免疫** —— 南亚科同比到三位数
    也只算一家，所以这条线量的是「分歧本身」，不是某一家的振幅。"""
    m = pd.DataFrame({k: YOYS[k].reindex(idx) for k in KEYS})
    n = (m > 0).sum(axis=1).astype(float)
    return n.mask(m.isna().any(axis=1)).reindex(idx)      # 有一家算不出就整月留空


GROW = _growing(IDX_YOY)
SPREAD_ALL = _spread(KEYS, IDX_YOY)
#: 「这个结论是不是只有存储在拉开」的对照组：去掉南亚科的六家。
KEYS_EXN = [k for k in KEYS if k != 'nanya']
SPREAD_EXN = _spread(KEYS_EXN, IDX_YOY)


def _split_pct(keys):
    """这一组里「有人涨、同时有人跌」的月份占比（%）。全员可算的月才计入。"""
    m = pd.DataFrame({k: YOYS[k].reindex(IDX_YOY) for k in keys})
    n = (m > 0).sum(axis=1).astype(float).mask(m.isna().any(axis=1)).dropna()
    return (float(((n > 0) & (n < len(keys))).mean() * 100.0), len(n)) if len(n) else (None, 0)


def _disp_facts():
    """离散度的判据数，全部现算。图注、brief、页尾说明都从这里取，不各算各的。

    ⚠ 名字叫 `DISPF` 不叫 `DISP` —— `DISP` 已经是「点名一家时怎么写」那张表了
    （见上面）。同名会把那张表整个盖掉，而它在七八处被引用。
    """
    g = GROW.dropna()
    n = len(g)
    if not n:
        return None
    same = int(((g == 0) | (g == len(KEYS))).sum())
    hard = int(((g >= 2) & (g <= len(KEYS) - 2)).sum())
    sa, se = SPREAD_ALL.dropna(), SPREAD_EXN.dropna()
    split_all, _ = _split_pct(KEYS)
    split_exn, _ = _split_pct(KEYS_EXN)
    return {
        'n': n, 'same': same, 'same_pct': same / n * 100.0,
        'split': n - same, 'split_pct': split_all,
        'hard': hard, 'hard_pct': hard / n * 100.0,
        'sp_med': float(sa.median()), 'sp_max': float(sa.max()),
        'sp_max_m': sa.idxmax(), 'sp_now': float(sa.iloc[-1]),
        'exn_med': float(se.median()) if len(se) else None,
        'exn_now': float(se.iloc[-1]) if len(se) else None,
        'exn_split_pct': split_exn,
    }


DISPF = _disp_facts()
if DISPF is None:
    skip('离散度算不出来（同比窗口为空）')


# ── 同比的两两相关：对角线留空 ────────────────────────────────────────
def _corr():
    m = pd.DataFrame({k: YOYS[k].reindex(IDX_YOY) for k in KEYS}).dropna()
    c = m.corr()
    return c, len(m)


CORR, CORR_N = _corr()


def _phase_rand(x, rng):
    """相位随机化替代序列：保住这条序列**自己的**自相关与频谱，只打散它与别人的关系。

    为什么非要这一步：在两条各自高度自相关的序列上，**在 ±k 个错位里挑相关最高的那个**
    本身就会产出一个不小的「增益」，哪怕两条序列毫无关系。不给这个「碰巧能挑出多少」
    定个标尺，任何错位相关的读数都无法判断是发现还是噪声。
    """
    n = len(x)
    f = np.fft.rfft(x - x.mean())
    ph = rng.uniform(0, 2 * np.pi, len(f))
    ph[0] = 0.0
    if n % 2 == 0:
        ph[-1] = 0.0
    return np.fft.irfft(np.abs(f) * np.exp(1j * ph), n) + x.mean()


def _maxgain(a, b, span):
    """→ (在 ±span 里挑出来的最高相关 − 同期相关, 那个 k, 同期相关)。"""
    r0 = float(np.corrcoef(a, b)[0, 1])
    best, bk = -9.0, 0
    for k in range(-span, span + 1):
        x, y = (a[k:], b[:-k]) if k > 0 else ((a[:k], b[-k:]) if k < 0 else (a, b))
        r = float(np.corrcoef(x, y)[0, 1])
        if r > best:
            best, bk = r, k
    return best - r0, bk, r0


def _leadlag(anchor='tsm', span=6, B=400, seed=7):
    """「谁领先谁」——**算出来是为了说明本页为什么不画这张图**，结论是负的。

    口径：各家单月同比的 3 个月移动平均（月营收的单月同比毛刺太大，错位相关会被
    噪声主导），窗口取七家都有值的那一段。对每一家算「在 ±span 里挑最优错位」
    相对同期相关的**增益**，再用 `_phase_rand` 生成 B 条零假设序列，得出
    「同样的挑选过程在无关序列上碰巧能挑出多大增益」。p = 零分布 ≥ 实测增益的比例。

    ⚠ **p 大不等于「没关系」，等于「这个数据量分不出来」**。页面上必须这么写：
      本页窗口只有七年上下，而这几条序列的周期是两三年一轮 —— 一共两三轮。
      在这种样本上，「领先 10 个月」与「滞后 16 个月」经常是同一句话。
    """
    m = pd.DataFrame({k: YOY3[k] for k in KEYS}).dropna()
    if len(m) < 36 or anchor not in m:
        return None
    rng = np.random.default_rng(seed)
    per, worst_p = {}, 1.0
    for k in KEYS:
        if k == anchor:
            continue
        a, b = m[k].values, m[anchor].values
        g, bk, r0 = _maxgain(a, b, span)
        null = np.array([_maxgain(_phase_rand(a, rng), b, span)[0] for _ in range(B)])
        per[k] = {'gain': g, 'best': bk, 'r0': r0, 'p': float((null >= g).mean()),
                  'null_med': float(np.median(null)), 'null_95': float(np.percentile(null, 95))}
        worst_p = min(worst_p, per[k]['p'])
    #: 「代工 + 封测」这一块是本页**唯一站得住的正面结论**：三家同期就最高，错位没好处。
    block = {}
    for a_, b_ in (('tsm', 'ase'), ('tsm', 'umc'), ('umc', 'ase')):
        g, bk, r0 = _maxgain(m[a_].values, m[b_].values, span)
        block[(a_, b_)] = {'r0': r0, 'best': bk, 'gain': g}
    return {'per': per, 'anchor': anchor, 'span': span, 'B': B, 'n': len(m),
            'min_p': worst_p, 'block': block,
            'at0': [k for k, v in per.items() if v['best'] == 0],
            'gain_max': max(v['gain'] for v in per.values()),
            'none_clears': all(v['p'] >= 0.05 for v in per.values())}


LL = _leadlag()
_off = [float(CORR.loc[a, b]) for i, a in enumerate(KEYS) for b in KEYS[i + 1:]]
CORR_MED = float(np.median(_off)) if _off else np.nan
CORR_HI = max(((a, b, float(CORR.loc[a, b])) for i, a in enumerate(KEYS)
               for b in KEYS[i + 1:]), key=lambda r: r[2])
CORR_LO = min(((a, b, float(CORR.loc[a, b])) for i, a in enumerate(KEYS)
               for b in KEYS[i + 1:]), key=lambda r: r[2])
#: 世芯那一行：与其余各家相关为负的家数，以及相关绝对值的上限。
#: **不写死「它与每一家都在噪声里」** —— 那是一句要逐对检验才成立的话；
#: 这里只印真正算得出来的两个量，措辞跟着它们走。
_AL_NEG = sum(1 for k in KEYS if k != 'alchip' and float(CORR.loc['alchip', k]) < 0)
_AL_MAXABS = max(abs(float(CORR.loc['alchip', k])) for k in KEYS if k != 'alchip')


# ── 世芯的汇率那一份有多大：现算，且**只用尺度无关的写法** ────────────────────
def alchip_fx_facts():
    """→ dict 或 None。页尾那条说明用它，图上不出现。

    两件事：
      · `fxy` —— (1+新台币同比) ÷ (1+美元同比) − 1，**恒等于当月汇率同比**。
        这个恒等式每轮复验（`resid`），对不上就是数据出了问题，硬失败。
      · `share` —— 窗口两端的累计增长里，汇率占的对数份额。
    ⚠ **不返回 pp 差**，因为页面上不许印它（理由见模块 docstring「世芯」那一段）。
    """
    df = RAW.get('alchip')
    if df is None or 'revenue_usd_mn' not in df.columns:
        return None
    # ⚠ 两列都取**原始单位**（US$mn 与 NT$mn），不要用 NTD[] 那份 —— 它已经除过
    #   1000 变成 NT$bn，相除得到的「汇率」会小一千倍。比值类的量（同比之商、
    #   累计增长比）不受影响，**但 fx_a / fx_b 是要印出来的水平值**，差三个数量级。
    usd = pd.to_numeric(df['revenue_usd_mn'], errors='coerce').reindex(IDX).dropna()
    ntd = pd.to_numeric(df[NTDCOL['alchip']], errors='coerce').reindex(IDX).dropna()
    yn = YOY.mom_yoy(ntd, YOY.FLOW).reindex(IDX_YOY) / 100.0
    yu = YOY.mom_yoy(usd, YOY.FLOW).reindex(IDX_YOY) / 100.0
    fxy = ((1 + yn) / (1 + yu) - 1.0).dropna() * 100.0
    if not len(fxy):
        return None
    fx = (ntd / usd).dropna()                       # 公司申报的当月换算汇率
    fxy_direct = (fx / fx.shift(12) - 1.0).reindex(fxy.index) * 100.0
    resid = float((fxy - fxy_direct).abs().max())
    if not _fin(resid) or resid > 0.01:             # 0.01pp：远大于浮点噪声，远小于任何真实差异
        raise SystemExit(f'build/semi: 世芯的「两条同比之商 ≡ 汇率同比」不成立'
                         f'（最大残差 {resid:.4f}pp）—— 先查 series/alchip.csv')
    # 窗口 = **本页的共同窗口**，不是世芯自己的序列全长。页尾那句话里的两个月份
    # 读者要能在本页的图上找到；印一个 2014 年的起点等于引一段本页没画的历史。
    a, b = fx.index[0], fx.index[-1]
    g_ntd, g_usd = float(ntd.loc[b] / ntd.loc[a]), float(usd.loc[b] / usd.loc[a])
    g_fx = float(fx.loc[b] / fx.loc[a])
    share = (np.log(g_fx) / np.log(g_ntd) * 100.0) if g_ntd > 0 and np.log(g_ntd) else None
    return {'a': a, 'b': b, 'fx_a': float(fx.loc[a]), 'fx_b': float(fx.loc[b]),
            'fx_chg': (g_fx - 1) * 100.0, 'share': share,
            'now': float(fxy.iloc[-1]), 'absmax': float(fxy.abs().max()),
            'absmax_m': fxy.abs().idxmax(), 'absmean': float(fxy.abs().mean())}


ALFX = alchip_fx_facts()


# ═══════════════════════════════════════════════════════════════════
# 图序：挪图**只改 ORDER 这一张表**（机制见 build/exhibits.py 文件头）
# ═══════════════════════════════════════════════════════════════════
ORDER = [
    'momentum',        # 去掉分母看生意本身：同比高低与环比动能经常相反
    'base-calendar',   # 把分母摊开：同比接下来的变化有多少根本不是今年的事
    'chain',           # 价值链框架：这七家是什么关系，横比为什么说得通
    'chain-check',     # 互相印证：哪条关系数据认、哪条不认（含安慰剂与行业外对照）
    'chain-gap',       # 关系站得住 ⇒ 背离即信号：封测相对代工的实时偏离
    'yoy-heat',        # 七家 × 近 N 月 单月同比矩阵 —— 七家同框只能用它
    'pctile-heat',     # 同一把尺：各家同比在**自身历史**里的分位
    'state',           # 增速 vs 水平：谁在创新高、谁在填坑（同比看不出来）
    'official-check',  # 公司自己的解释，以及能不能用它自己的分部列验出来
    'growing-count',   # 每月七家里有几家在增长（对离群值免疫的分歧度量）
    'spread',          # 组内同比极差；含「去掉南亚科」的对照线
    'node-split',      # 先进 vs 成熟制程：本页唯一一张比值图（为什么只有一张，见图注）
    'rebased-mfg',     # 制造侧指数化（基期 = 100）
    'rebased-design',  # 设计侧指数化
    'yoy-mfg',         # 制造侧单月同比（**不含南亚科**，理由见图注）
    'yoy-design',      # 设计侧单月同比
    'season-heat',     # 季节性指数矩阵：低谷都在农历年，高峰各不相同
    'corr',            # 单月同比的两两相关
    'decomp',          # 这七家其实是几个独立的赌注
]
_seq = iter(exhibits.Seq(k) for k in range(2, 99))
E_MOM, E_BASE = next(_seq), next(_seq)
E_CHAIN, E_XCHK, E_XGAP = (next(_seq) for _ in range(3))
E_HEAT, E_PCT, E_STATE, E_CHECK = (next(_seq) for _ in range(4))
E_GROW, E_SPREAD = next(_seq), next(_seq)
E_NODE = next(_seq)
E_REB_M, E_REB_D, E_YOY_M, E_YOY_D = (next(_seq) for _ in range(4))
E_SEASON, E_CORR, E_DECOMP = next(_seq), next(_seq), next(_seq)
E_TABLE = next(_seq)
#: 建图时的号 → id。本轮没出的图不登记（ORDER 里列了却没生成的 id 由 exhibits 跳过）。
EX_ID = {E_MOM: 'momentum', E_BASE: 'base-calendar',
         E_CHAIN: 'chain', E_XCHK: 'chain-check', E_XGAP: 'chain-gap',
         E_HEAT: 'yoy-heat', E_PCT: 'pctile-heat',
         E_STATE: 'state', E_CHECK: 'official-check', E_DECOMP: 'decomp',
         E_GROW: 'growing-count', E_SPREAD: 'spread', E_NODE: 'node-split',
         E_REB_M: 'rebased-mfg', E_REB_D: 'rebased-design',
         E_YOY_M: 'yoy-mfg', E_YOY_D: 'yoy-design',
         E_SEASON: 'season-heat', E_CORR: 'corr'}

XL_ALL = [mlab(p) for p in IDX]
XL_YOY = [mlab(p) for p in IDX_YOY]
XL_REB = [mlab(p) for p in IDX_REB]
ex = []


def _lines(keys, idx, getter, **kw):
    """一组公司 → `lines` 的 series[]。

    **只用 `lines`，不用 `lines_endlabels`** —— 后者在 `mrwin.DENSE` 里：走
    Catmull-Rom 平滑，数组里有一个 null 就画出一条塌到零的假线，前导 null 还会
    撞上左端标签按 fmt 抛异常。本页的日月光同比比另外六家晚 12 个月起
    （它的序列 2018-05 才开始），天生带前导 null；`lines` 走非平滑折线，
    null 是断笔，正是要的。
    """
    return [{'name': f'{NAME[k]}（{CODE[k]}·{SUBLAYER[k]}）', 'color': COLOR[k],
             'values': L(getter(k).reindex(idx).values)} for k in keys]


def _axis_owner(keys, idx, series_of):
    """谁把纵轴撑开了、撑开多少 —— 现算一句话（同 build/wealth.py 的 _cash_axis_txt）。"""
    last = {k: float(series_of(k).reindex(idx).dropna().iloc[-1])
            for k in keys if len(series_of(k).reindex(idx).dropna())}
    if len(last) < 2:
        return ''
    hi = max(last, key=last.get)
    lo = min(last, key=last.get)
    return (f'<b>纵轴由{NAME[hi]}定</b>：{mlab(idx[-1])} 它是{NAME[lo]}的 '
            f'{last[hi] / last[lo]:.1f} 倍，另外几条因此挤在下半幅 —— '
            f'读这张图请看<b>斜率</b>（谁在加速），不要按线的高低读「谁更大」，'
            f'水平值在 Exhibit 1 的汇总表里。')


# ── ⟨ex:momentum⟩ 去掉分母，生意本身在加速还是减速 ──────────────────────────
_SLOW = [k for k in MOM if MOM[k]['now'] < MOM[k]['prev']]
_BELOW = [k for k in MOM if MOM[k]['now'] < MOM[k]['med']]
#: 同比还很高、但环比动能已经掉到自身历史中位以下的 —— 本表最该被看见的一格。
_DIVERGE = sorted((k for k in MOM if _fin(_yy(k)) and _yy(k) > 30
                   and MOM[k]['now'] < MOM[k]['med'] and MOM[k]['now'] < MOM[k]['prev']),
                  key=lambda k: -_yy(k))
ex.append({
    'n': E_MOM, 'kind': 'table', 'full': True,
    'title': ('同比看不见运行速率：把季节性与去年同期一起去掉之后，'
              + (f'{"、".join(NAME[k] for k in _DIVERGE)}的环比动能已经掉到自身历史中位以下'
                 if _DIVERGE else '七家的环比动能都还在自身historical中位之上')),
    'idx': '公司',
    'cols': [['当月同比', 'y'], ['季调环比（近 3 月 vs 前 3 月）', 'now'],
             ['上一期同口径', 'prev'], ['自身历史中位（绝对值）', 'med'], ['读数', 'v']],
    'rows': [{'xl': f'{NAME[k]} {CODE[k]}',
              'y': pct(_yy(k), 0),
              'now': pct(MOM[k]['now'], 1),
              'prev': pct(MOM[k]['prev'], 1),
              'med': f'{MOM[k]["med"]:.1f}%',
              'v': (('<b>减速</b>' if MOM[k]['now'] < MOM[k]['prev'] else '加速')
                    + '，' + ('<b>低于</b>' if MOM[k]['now'] < MOM[k]['med'] else '高于')
                    + '自身中位')}
             for k in sorted(MOM, key=lambda k: -(_yy(k) if _fin(_yy(k)) else -9e9))],
    'src_extra': (f'季调 = 月营收 ÷ 该月季节指数（同⟨ex:season-heat@>:后面那张季节性矩阵⟩，'
                  f'{SEASON_YRS[0]}–{SEASON_YRS[-1]} 完整年现算）。'
                  '环比取 3 个月对前 3 个月，<b>不年化</b>。'),
    'note': (
        '<b>同比的分母是去年同月，它对「这个月相对上个月怎么样」一无所知。</b>'
        '一家公司可以同时做到：同比很高（去年基数低）、而生意本身已经在减速。'
        '这一栏就是为了把那种情形拎出来。'
        + ((f'<br><b>本月的分歧在{"、".join(NAME[k] for k in _DIVERGE)}</b>：'
            + '；'.join(f'{NAME[k]}同比 {pct(_yy(k), 0)}，'
                        f'而季调环比从 {pct(MOM[k]["prev"], 1)} 降到 {pct(MOM[k]["now"], 1)}，'
                        f'已低于它自己的历史中位 {MOM[k]["med"]:.1f}%'
                        for k in _DIVERGE)
            + '。同比排名把它排在前列，环比动能不支持这个位置。')
           if _DIVERGE else '')
        + '<br><b>为什么不年化。</b>把三个月的变化折成年率，在块状序列上会炸开 —— '
        '本轮实测世芯的年化读数能到五位数（它刚从一次腰斩里出来），'
        '那个数没有刻度可言，印上去会让整张表失去可读性。不年化的版本有界，'
        '而且与「自身历史中位」并排时，读者立刻知道这一档对这家公司算大还是算小。'
        '<br>⚠ 季节指数是多年平均，而<b>农历年落在一月还是二月逐年不同</b>；'
        '跨年那两个月的季调值因此会被系统性错配，读这张表时对 1–2 月要打折扣。'),
})

# ── ⟨ex:base-calendar⟩ 把分母摊开 ────────────────────────────────────────
_bd = sorted(BASE_DRIFT, key=lambda k: BASE_DRIFT[k])
_down, _up = _bd[0], _bd[-1]
ex.append({
    'n': E_BASE, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
    'title': (f'基数日历：运行速率原地不动的话，未来 {len(BASE_MONTHS)} 个月的同比会自己走成什么样'),
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS if k in BASECAL],
    'cols': [mlab(m) for m in BASE_MONTHS],
    'matrix': [L(BASECAL[k]['path']) for k in KEYS if k in BASECAL],
    'legend': '机械同比（%）：分子按季调运行速率固定，分母是去年同月实际值',
    'cell_h': 24, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': ('分子 = 最近 3 个月的季调均值，按各月季节指数还原；'
                  '分母 = 去年同月的<b>实际申报值</b>。'),
    'note': (
        '<b>这不是预测，是把分母摊开。</b>分子在这张表里是一个不变的假设'
        '（生意原地不动），所以每一格的高低<b>完全由去年同月那个已经发生的数决定</b>。'
        '它回答的是：同比接下来的变化里，有多少根本不是今年的事。'
        + (f'<br><b>两个最扎眼的读数正在往相反方向走，而且原因纯粹是算术。</b>'
           f'{DISP[_down]}的同比会从 {pct(_yy(_down), 0)} 一路走到 '
           f'{pct(BASECAL[_down]["path"][-1], 0)}（{BASE_DRIFT[_down]:+.0f}pp），'
           '而它的生意在这个假设里一天都没有变弱；'
           f'{DISP[_up]}反过来，从 {pct(_yy(_up), 0)} 走到 '
           f'{pct(BASECAL[_up]["path"][-1], 0)}（{BASE_DRIFT[_up]:+.0f}pp），'
           '因为它去年这几个月正处在自己的谷底。'
           '<br>⇒ 明年初看到「南亚科增速大幅放缓」「世芯增速再创新高」这类说法时，'
           '先回到这张表看一眼：其中有多少是分母。'
           if _down in BASECAL and _up in BASECAL else '')
        + '<br><b>这张表能做什么、不能做什么。</b>能做的是<b>剔除</b>一部分惊讶 —— '
        '把「同比变化」里属于去年的那一份先扣掉，剩下的才值得解释。'
        '不能做的是判断方向：运行速率会不会变，这张表一个字都没说，'
        f'那要看⟨ex:momentum@<:上面那张环比动能表⟩，以及下个月的实际公告。'
        '<br>⚠ 同上：农历年在一月还是二月逐年不同，季节指数用的是多年平均，'
        '所以跨年那两列的还原会被系统性错配，读的时候对它们打折扣。'),
})

# ── ⟨ex:chain⟩ 价值链框架：横着比为什么说得通 ────────────────────────────
def _drv(k):
    """驱动那一格：能引公司自己的话就引它，引不到才用 spec 里复核过的编辑归纳。"""
    rk = remark_of(k, CUR)
    if rk and rk['triggered'] and rk['remark']:
        return f'<b>公司本月自述</b>：「{rk["remark"]}」'
    return ROLE[k][1] or '—'


ex.append({
    'n': E_CHAIN, 'kind': 'table', 'full': True,
    'title': '这七家是同一笔需求在链条上的七个观测点 —— 横着比之前先看清关系',
    'idx': '公司',
    'cols': [['链上位置', 'pos'], ['营收怎么来', 'drv'], ['组内同层对手', 'rival']],
    'rows': [{'xl': f'{NAME[k]} {CODE[k]}', 'pos': ROLE[k][0], 'drv': _drv(k),
              'rival': (f'{NAME[RIVAL[k]]}（接近零和）' if RIVAL[k] else '组内无同层对手')}
             for k in KEYS],
    'note': (
        '<b>跨层不是零和，同层才是。</b>同一颗 ASIC 的设计费记在世芯／创意，晶圆记在'
        '台积电，封测记在日月光 —— 三层一起涨不是三家互相抢，是同一笔需求被数了三次。'
        '所以本页跨层只问「<b>价值往哪一层走</b>」（看比值与各层增速差），'
        '不问「谁占几成」（那需要一个这七家凑不出来的分母）。'
        '真正接近零和的只有同层两对：世芯 vs 创意抢同一批 ASIC 案子，'
        '台积电 vs 联电各守制程的一端。'
        '<br>「链上位置」与「营收怎么来」两列是<b>本页的编辑归纳</b>，不是公司的披露口径；'
        '能引公司自己法定申报原文的月份直接引原文（见'
        '⟨ex:official-check@>:下面那张对账表⟩）。'
        f'<br>⚠ {DISP["tsm"]}那一行的「营收怎么来」<b>只引它自己的话</b>：'
        '本仓七份单公司配置里，只有它从未写过属于哪一层，'
        '本页不替它归类（另外六家的出处：'
        + '、'.join(f'{NAME[k]} <code>{ROLE[k][2]}</code>' for k in KEYS if k != 'tsm') + '）。'),
})

# ── ⟨ex:chain-check⟩ 互相印证：数据认哪条关系、不认哪条 ──────────────────────
def _vd(r):
    if r['kind'] == '安慰':
        return ('<b>对照组</b>：' + ('扣掉行业周期后归零或转负'
                                     if not _fin(r['p_st']) or r['p_st'] < 0.2 else '偏相关仍在，存疑'))
    return '<b>三道全过</b>' if _passes(r) else '<b>没过</b>（偏相关扣不住）'


ex.append({
    'n': E_XCHK, 'kind': 'table', 'full': True,
    'title': ('哪两家的数据真能互相印证 —— 先说机制，再让数据判'
              + (f'：{len(CHAIN_PASS)} 条工序关系过了三道检验，{len(CHAIN_FAIL)} 条没过'
                 if CHAINX else '')),
    'idx': '配对',
    'cols': [['为什么应当相关（机制）', 'why'],
             ['3MMA 同比 r', 'r1'], ['平稳变换 r', 'r2'],
             ['扣掉共同半导体周期后（偏相关）', 'p'], ['判定', 'v']],
    'rows': [{'xl': f'{LEG_ZH2[r["a"]]} → {LEG_ZH2[r["b"]]}',
              'why': r['why'],
              'r1': f'{r["r_y3"]:+.2f}' if _fin(r['r_y3']) else '—',
              'r2': f'{r["r_st"]:+.2f}' if _fin(r['r_st']) else '—',
              'p': f'{r["p_st"]:+.2f}' if _fin(r['p_st']) else '—',
              'v': _vd(r)} for r in CHAINX],
    'src_extra': ('两种变换：3MMA 单月同比（可读，单位 pp）与平稳变换'
                  '（季调对数水平的 3 个月环比，稳健）。偏相关的控制变量 = '
                  '不含这两条腿的成员各自标准化后取均值。'),
    'note': (
        '<b>本仓没有任何一条关于这七家之间业务关系的已核事实</b>（谁是谁的客户、'
        '谁持有谁的股份，七份单公司配置里一个字都没有），所以本页<b>不断言供应关系</b>。'
        '能用的只有一条不需要外部事实的：<b>封测是晶圆产出之后的工序，这是业务定义本身</b>。'
        '以它为假说，让数据来判。'
        '<br><b>三道检验，缺一条结论就不成立：</b>'
        '① 三种变换都要过 —— 12 个月滚动同比最好看，但它高度自相关，'
        '本轮实测那个口径下连通配对的自助区间<b>含 0</b>，'
        '真正站得住的是平稳变换；'
        '② 安慰剂要够干净 —— 同公司另一段业务与同业都不够（各自共享公司层因素与行业景气），'
        '所以另取行业外对照（零售 / 消费信贷 / 交易所成交量），实测相关落在 0.0–0.4；'
        '③ <b>扣掉共同半导体周期之后还得剩下</b>。这一条是决定性的：若归零，'
        '「上下游印证」就只是「同处一个景气」，机制说法不成立。'
        + ((f'<br><b>过了的：</b>'
            + '；'.join(f'{LEG_ZH2[r["a"]]}↔{LEG_ZH2[r["b"]]} 偏相关 {r["p_st"]:+.2f}'
                        for r in CHAIN_PASS)
            + ' —— 两家独立公司、两份独立申报，扣掉行业景气之后仍然一起动。'
              '这才是工序连接的证据。') if CHAIN_PASS else '')
        + ((f'<br><b>没过的：</b>'
            + '；'.join(f'{LEG_ZH2[r["a"]]}↔{LEG_ZH2[r["b"]]}（平稳变换偏相关 '
                        f'{r["p_st"]:+.2f}）' for r in CHAIN_FAIL)
            + ' —— 「量产是晶圆转售、理应跟着代工走」这个猜想听上去顺，'
              '数据不支持。<b>写在这里是因为它被证伪了，不是因为它可疑</b>：'
              '一条被数据否掉的机制，与一条通过的同样是结论。') if CHAIN_FAIL else '')),
})

# ── ⟨ex:chain-gap⟩ 关系站得住 ⇒ 背离即信号 ──────────────────────────────
if CHAIN_GAP:
    _g = CHAIN_GAP
    _gs = _g['s']
    ex.append({
        'n': E_XGAP, 'kind': 'lines', 'full': True, 'height': LINE_H,
        'fmt': 'f0', 'label_fmt': 'f0', 'yfmt': 'f0',
        'title': (f'{LEG_ZH2[_g["down"]]}比「按历史关系该有的样子」高出多少（pp）—— '
                  f'{mlab(CUR)} {_g["now"]:+.0f}pp，处在 {len(_gs)} 个月里的第 '
                  f'{_g["pct"]:.0f} 百分位'),
        'xlabels': [mlab(p) for p in _gs.index], 'ylab': '残差（pp，封测 − 按代工推算）',
        'zero_line': True, 'end_label': True,
        'series': [{'name': f'{LEG_ZH2[_g["down"]]} 相对 {LEG_ZH2[_g["up"]]} 的偏离',
                    'color': 'NAVY', 'values': L(_gs.values)}],
        'src_extra': ('残差 = 下游实际 3MMA 同比 − 用<b>只到当期为止</b>的数据回归出来的推算值'
                      '（扩张窗口，无未来信息）。用全样本拟合会把「现在很反常」系统性做小。'),
        'note': (
            '<b>这张图的前提是上一张表：只有关系站得住，偏离才是信号。</b>'
            f'{LEG_ZH2[_g["up"]]}与{LEG_ZH2[_g["down"]]}扣掉行业景气后偏相关仍有 '
            + (f'{CHAIN_PASS[0]["p_st"]:+.2f}' if CHAIN_PASS else '正值')
            + '，所以「这个月它俩对不上」是一件需要解释的事，而不是噪声。'
            f'<br><b>{mlab(CUR)} 的偏离是 {_g["now"]:+.0f}pp，历史中位 {_g["med"]:+.0f}pp，'
            f'落在第 {_g["pct"]:.0f} 百分位</b>；'
            f'而且已经<b>连续 {_g["run"]} 个月同向</b>，不是单月跳动。'
            f'历史上另一端是 {_g["lo"]:+.0f}pp（{mlab(_g["lo_m"])}）。'
            '<br><b>这页说不了「为什么」。</b>封测跑在代工前面，可以是单片芯片的封装'
            '用量在升、可以是这家在同业里拿到更多、也可以是产品结构变了 —— '
            f'本页没有任何一列能把它们分开（{NAME["ase"]}的 ATM 把测试、打线与先进封装'
            '捆在一起披露）。能说的是<b>这件事正在发生、幅度是多少、历史上有没有过</b>，'
            '以及它<b>该被追问</b>。'
            '<br>⚠ 幅度随变换变：平稳变换下同方向但没这么极端。'
            '方向可信，别把这个 pp 数当成一个精确的量。'),
    })

# ── ⟨ex:yoy-heat⟩ 七家 × 近 N 月：单月同比矩阵 ────────────────────────────
_HM = list(IDX_YOY[-HEAT_MONTHS:])
ex.append({
    'n': E_HEAT, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
    'title': f'七家的单月同比，近 {len(_HM)} 个月（%）—— 同一个月里各家差得有多远',
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': [mlab(p) for p in _HM],
    'matrix': [L(YOYS[k].reindex(_HM).values) for k in KEYS],
    'legend': '月营收 单月同比（%）',
    'cell_h': 24, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': '同比口径 = 单月（当月 ÷ 去年同月 − 1），全站唯一实现 build/yoy.py。',
    'note': (
        '<b>七家唯一能同框的图型就是它。</b>引擎只有 6 个数据色，七条折线画不出来；'
        '更要紧的是<b>七家的同比不在一个量级上</b> —— '
        f'{DISP["nanya"]}这样的存储周期，单月同比可以到三位数，'
        '而晶圆代工是个位数到两位数。把它们放进同一根线性纵轴，'
        '代工那几条会被压成一条直线（这一条是南亚科自己那页定的读法，'
        '见 <code>/nanya/</code>「这是一条存储器周期序列」）。'
        '矩阵按<b>格子</b>着色，不共用一根纵轴，所以不受这个限制。'
        '<br><b>色标是本图自己的 5/95 分位</b>（引擎的 heatScale）：极端月份会顶到色阶两端、'
        '不会把其余格子的分辨率吃掉，但也因此<b>两张矩阵之间颜色不可比</b>，'
        '别拿本图的红跟下面季节性那张的红对照。'
        + (f'<br>{DISP["ase"]}的同比从 {mlab(IDX_YOY[0])} 起才有：'
           '它的序列 2018-05 才开始（控股公司 2018-04-30 才成立，更早的月报属于前身主体，'
           '不可前接），再往前一年才凑得出分母。' if 'ase' in YOY_LATE else '')),
})

# ── ⟨ex:pctile-heat⟩ 自身历史分位：把七条振幅差一个数量级的同比放到同一把尺上 ──
_PM = list(IDX[-24:])
_pm_mat = [L(PCT3[k].reindex(_PM).values) for k in KEYS]
_sp = PCT_SPREAD.dropna()
_hist = {k: int(YOY3_FULL[k].dropna().shape[0]) for k in KEYS}
ex.append({
    'n': E_PCT, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f0',
    # 标题是纯文本（page.js 按 textContent 写），所以不带任何标签与星号。
    'title': f'同一把尺：各家同比在自身历史里排第几（0–100，近 {len(_PM)} 个月）',
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': [mlab(p) for p in _PM],
    'matrix': _pm_mat,
    'legend': '3MMA 同比在自身全历史中的百分位',
    'cell_h': 24, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': (f'分母是各家<b>自己的全部历史</b>（{min(_hist.values())}–{max(_hist.values())} '
                  f'个同比月，逐家不同），不是共同窗口；不足 {PCT_MIN} 个月不给分位。'),
    'note': (
        '<b>这张图回答的是⟨ex:yoy-heat@<:上面那张矩阵⟩答不了的问题：谁这个月更反常。</b>'
        '七家同比的振幅差一个数量级'
        + (f'（自身波动最大的{NAME[max(KEYS, key=lambda k: DEC["per"][k]["own_sd"])]} '
           f'σ≈{max(DEC["per"][k]["own_sd"] for k in KEYS):.0f}pp，'
           f'最小的{NAME[min(KEYS, key=lambda k: DEC["per"][k]["own_sd"])]} '
           f'σ≈{min(DEC["per"][k]["own_sd"] for k in KEYS):.0f}pp）' if DEC else '')
        + '，所以「谁的同比高」量的多半是「谁的生意天生波动大」。'
        '换成<b>各家在自己历史里的百分位</b>，七家才落在同一把 0–100 的尺上。'
        + ((f'<br>本月这把尺给出的排序与同比排序<b>不一样</b>：'
            f'按同比{NAME[sorted(PCT_OK, key=lambda k: -_yy(k))[0]]}第一'
            f'（{pct(_yy(sorted(PCT_OK, key=lambda k: -_yy(k))[0]), 0)}），'
            f'按自身分位第一的是{NAME[sorted(PCT_OK, key=lambda k: -PCT_NOW[k])[0]]}'
            f'（{PCT_NOW[sorted(PCT_OK, key=lambda k: -PCT_NOW[k])[0]]:.0f}）—— '
            f'后者的 {pct(_yy(sorted(PCT_OK, key=lambda k: -PCT_NOW[k])[0]), 0)} 在它自己的历史里'
            '几乎是最高的一个月，而前者的三位数同比只排到它自己的九十几分位。')
           if PCT_OK and sorted(PCT_OK, key=lambda k: -_yy(k))[0]
           != sorted(PCT_OK, key=lambda k: -PCT_NOW[k])[0] else '')
        + ((f'<br><b>本月真正值得记的是这个：七家的分位挤到了一起。</b>'
            f'十二个月前最高与最低差 {_sp.iloc[-13]:.0f} 个分位点，现在只差 '
            f'{_sp.iloc[-1]:.0f} 点，'
            f'{sum(1 for k in PCT_OK if PCT_NOW[k] >= 90)} 家在自身九十分位以上。'
            '分位这把尺在顶部会饱和 —— 大家都贴到 100 的时候它就没有分辨率了，'
            '<b>而那本身就是读数</b>：这是一次同步的普涨，不是一个挑公司的局面。')
           if len(_sp) > 13 else '')
        + '<br><b>这张图说的是「站在哪里」，不是「要往哪去」。</b>'
        '本轮做过前瞻检验：分位对未来 3／6／12 个月的<b>加速度</b>没有可测的关系'
        '（自助置信区间在三个期限上都跨过零）。唯一稳定的前瞻性质是向中位回归，'
        '而那是这个比值自身的性质，不是关于公司的消息。'
        f'<br>色标是本图自己的 5/95 分位，与另外两张矩阵不可比。'),
})

# ── ⟨ex:state⟩ 增速 vs 水平：同比矩阵结构上看不出的那一半 ────────────────────
_rank_yoy = sorted(KEYS, key=lambda k: -(_yy(k) if _fin(_yy(k)) else -9e9))
_rank_gap = sorted(KEYS, key=lambda k: -STATE[k]['gap'])
ex.append({
    'n': E_STATE, 'kind': 'table', 'full': True,
    'title': (f'同比说「比去年这个月多多少」，不说「生意有没有回到过」—— '
              f'{mlab(CUR)} 七家里 {len(AT_HIGH)} 家近 12 个月合计创新高，'
              f'{len(BELOW)} 家仍低于自己的峰'),
    'idx': '公司',
    'cols': [['当月同比', 'y1'], ['近 12 月合计同比', 'y12'],
             ['近 12 月合计 vs 自身历史峰', 'gap'], ['峰在', 'pk'],
             ['史上最大回撤（12 月合计）', 'dd']],
    'rows': [{'xl': f'{NAME[k]} {CODE[k]}',
              'y1': pct(_yy(k), 0),
              'y12': pct(STATE[k]['r12_yoy'], 0),
              'gap': ('<b>创新高</b>' if STATE[k]['at_high'] else pct(STATE[k]['gap'], 1)),
              'pk': mlab(STATE[k]['peak_m']),
              'dd': f'{STATE[k]["maxdd"]:.0f}%（{mlab(STATE[k]["maxdd_m"])}）'}
             for k in _rank_yoy],
    'note': (
        '<b>这张表是为了拆掉一个横截面最容易犯的错：把高同比读成「强」。</b>'
        '同比的分母是去年同月，它对「这家公司本来有多大」一无所知 —— '
        '一家刚从腰斩里爬出来的公司，同比可以是三位数，而它的生意仍远小于两年前。'
        + ((f'<br>本月就是这样：按当月同比排，第一是{NAME[_rank_yoy[0]]}'
            f'（{pct(_yy(_rank_yoy[0]), 0)}）；但按「离自己的历史峰还有多远」排，'
            f'垫底的是{NAME[BELOW[0]]}（{pct(STATE[BELOW[0]]["gap"], 1)}，'
            f'峰在 {mlab(STATE[BELOW[0]]["peak_m"])}），'
            f'而它的当月同比是 {pct(_yy(BELOW[0]), 0)} —— '
            '<b>三位数的同比与「还没回到两年前」可以同时为真</b>，'
            '这正是只看⟨ex:yoy-heat@<:上面那张矩阵⟩会读反的地方。')
           if BELOW and _fin(STATE[BELOW[0]]['gap']) else '')
        + '<br>用<b>近 12 个月合计</b>而不是单月来比水平：单月带农历年与出货批次的块状噪声，'
        '一个月的高低读不出生意规模。回撤也按同一口径算，'
        '所以表里每一列都是同一条序列的不同问法，可以横着读。'),
})

# ── ⟨ex:official-check⟩ 公司自己的解释，能不能用它自己的分部列验出来 ──────────
_TRIG = [k for k in KEYS if (remark_of(k, CUR) or {}).get('triggered')
         and (remark_of(k, CUR) or {}).get('remark')]
_NOROW = [k for k in KEYS if remark_of(k, CUR) is None]
_check_rows = []
for _k in KEYS:
    _rk = remark_of(_k, CUR)
    if _rk is None:
        _said = '<i>本库暂无这一行</i>'
    elif _rk['triggered'] and _rk['remark']:
        _said = f'「{_rk["remark"]}」'
    elif _rk['triggered']:
        _said = '<i>触发门槛，但官方该栏为空</i>'
    else:
        _said = '<i>未触发 ±50% 门槛，无须说明</i>'
    _segs = SEGF.get(_k)
    if _segs:
        _fast = max(_segs, key=lambda x: x['r12_yoy'] if _fin(x['r12_yoy']) else -9e9)
        _slow = min(_segs, key=lambda x: x['r12_yoy'] if _fin(x['r12_yoy']) else 9e9)
        _ver = (f'{_fast["zh"]} 近 12 月 {pct(_fast["r12_yoy"], 0)}、'
                f'占比 {_fast["share_prev"]:.0f}%→<b>{_fast["share_now"]:.0f}%</b>；'
                f'{_slow["zh"]} {pct(_slow["r12_yoy"], 0)}')
    else:
        _ver = '<i>无月度分部列，验不了</i>'
    _check_rows.append({'xl': f'{NAME[_k]} {CODE[_k]}',
                        'leg': LEG_ZH.get((_rk or {}).get('leg', '-'), '') or '—',
                        'said': _said, 'ver': _ver})
# 真正能「对账」的 = 既触发了门槛（有一句话要验）**又**有月度分部列（验得了）。
# 两者的交集逐月在变，**不许写死家数** —— 上一版标题写「其中两家」，而本月实际只有
# 一家落在交集里（另一家有分部列但没触发，没有说法可对）。
_VERIFIABLE = [k for k in _TRIG if k in SEGF]
_SEG_ONLY = [k for k in SEGF if k not in _TRIG]
ex.append({
    'n': E_CHECK, 'kind': 'table', 'full': True,
    'title': (f'公司自己怎么解释这个月 —— {mlab(CUR)} 有 {len(_TRIG)} 家触发法定说明门槛，'
              + (f'其中 {len(_VERIFIABLE)} 家（'
                 + '、'.join(NAME[k] for k in _VERIFIABLE)
                 + '）的说法能用它自己的分部列当场对账'
                 if _VERIFIABLE else '但没有一家同时具备可对账的月度分部列')),
    'idx': '公司',
    'cols': [['触发腿', 'leg'], ['MOPS 备注原文（法定申报栏）', 'said'],
             ['用它自己的分部列验', 'ver']],
    'rows': _check_rows,
    'src_extra': ('备注原文取自 series/mops_remarks.csv（TWSE/MOPS 月营收申报表的'
                  '「備註／營收變化原因說明」栏，24 个月滚动窗口）。'),
    'note': (
        '<b>这是本页唯一一处「公司自己解释自己」的材料，也是回答「背后是什么逻辑」时'
        '唯一不靠推断的一列。</b>台湾 MOPS 月营收申报表脚注第 6 条要求：'
        '当月或本年累计营收同比增减<b>达 ±50%</b> 者必须说明原因 —— '
        '所以触发月的那句话是法定申报内容，不是公关稿。'
        '<br><b>两条读法上的硬规矩</b>：'
        '① <b>未触发 ≠ 公司没话说</b>，只等于它这个月没到门槛；'
        '② <b>没触发却填了字的，不能当成增减原因引用</b> —— '
        f'{DISP["mtk"]}连续多个月填同一句汇率换算的会计口径说明而一次都没触发门槛，'
        '把它当成「联发科解释了营收变化」，就是把一句口径注伪造成经营评论。'
        '本页因此只在触发时印原文。'
        '<br><b>最后一列是对账，不是转述。</b>公司的断言不是证据；七家里只有'
        f'{"、".join(NAME[k] for k in SEGF)}在月度层面另外披露了分部拆分。'
        '说「量产／封测那一段在涨」，就该看到那一段的增速与占比同时抬升；'
        '对不上不等于公司说谎（分部口径可以与备注口径不同），但<b>对得上就是一条真凭据</b>。'
        + (f'<br><b>本月真正构成对账的只有{"、".join(NAME[k] for k in _VERIFIABLE)}</b>'
           '（既触发门槛、又有分部列）。'
           if _VERIFIABLE else '<br>本月没有一家同时触发门槛且具备分部列，这一列无对账可做。')
        + (f'{"、".join(NAME[k] for k in _SEG_ONLY)}有分部列但本月未触发门槛，'
           '它那一格是<b>分部数据自己说话</b>，不对应任何一句官方说法 —— '
           '两者别混着读。' if _SEG_ONLY else '')
        + f'<br>⚠ {DISP["alchip"]}没有月度分部列，它那句话本页<b>验不了</b>，只能照引 —— '
        f'也<b>不许</b>拿{NAME["guc"]}的分部去替它背书，那是两家公司。'),
})

# ── ⟨ex:growing-count⟩ 每月有几家在增长 ──────────────────────────────────
_g_now = int(GROW.dropna().iloc[-1])
ex.append({
    'n': E_GROW, 'kind': 'bars_labeled', 'full': True, 'height': 280,
    'fmt': 'f0', 'label_fmt': 'f0',
    'title': (f'「半导体」不是一个周期：{len(KEYS)} 家里当月同比为正的有几家'
              f'（{mlab(CUR)}：{_g_now} 家）'),
    'xlabels': XL_YOY, 'ylab': f'同比为正的家数（0–{len(KEYS)}）',
    'values': L(GROW.values),
    # ⚠ **不要给这张图 annot。** bars_labeled 的 annot 画在图的左上角，而本图的柱
    #   顶到 7（七家全涨）时柱顶数值标签正好落在同一块地方 —— visual_qa 实测
    #   「7」与 annot 压字 15.3px²。那条信息在下面的 note 里已经有了，
    #   同一句话不必在图上再占一次位置。
    'src_extra': (f'窗口 {spanl(IDX_YOY[0], LATEST)}，{DISPF["n"]} 个月；'
                  '每月要七家都算得出单月同比才计入，否则整月留空。'),
    'note': (
        f'<b>{DISPF["n"]} 个月里，七家同向（全涨或全跌）的只有 {DISPF["same"]} 个月，'
        f'占 {DISPF["same_pct"]:.0f}%。</b>'
        f'反过来说 <b>{DISPF["split_pct"]:.0f}% 的月份里，有人在涨的同时有人在跌</b>；'
        f'其中 {DISPF["hard"]} 个月（{DISPF["hard_pct"]:.0f}%）是至少两家涨、'
        '同时至少两家跌的「硬分歧」。'
        '<br>这条线<b>对离群值免疫</b>：南亚科同比到三位数也只算一家，'
        '所以它量的是分歧本身，不是某一家的振幅 —— '
        f'⟨ex:spread@+1:下一张图⟩把幅度单独画出来。'
        + (f'<br><b>这个结论不是存储一家撑起来的</b>：去掉{NAME["nanya"]}'
           f'之后，剩下六家仍有 {DISPF["exn_split_pct"]:.0f}% 的月份涨跌不同向。'
           if DISPF['exn_split_pct'] is not None else '')),
})

# ── ⟨ex:spread⟩ 组内同比极差 ────────────────────────────────────────────
ex.append({
    'n': E_SPREAD, 'kind': 'lines', 'full': True, 'height': LINE_H,
    'fmt': 'f0', 'label_fmt': 'f0', 'yfmt': 'f0',
    'title': (f'当月最快的一家比最慢的一家高出多少（pp）—— 中位 '
              f'{DISPF["sp_med"]:.0f}pp，{mlab(CUR)} 为 {DISPF["sp_now"]:.0f}pp'),
    'xlabels': XL_YOY, 'ylab': '单月同比的组内极差（pp）',
    'zero_base': True, 'end_label': True,
    'series': [
        {'name': f'{len(KEYS)} 家', 'color': 'NAVY', 'values': L(SPREAD_ALL.values)},
        {'name': f'{len(KEYS_EXN)} 家（不含{NAME["nanya"]}）', 'color': 'GRAY',
         'values': L(SPREAD_EXN.values)},
    ],
    'src_extra': '极差 = 当月七家单月同比的最大值 − 最小值，单位是百分点（pp），不是百分比。',
    'note': (
        f'峰值 <b>{DISPF["sp_max"]:.0f}pp</b> 出现在 {mlab(DISPF["sp_max_m"])}。'
        f'灰线是去掉{NAME["nanya"]}的对照：中位仍有 '
        f'<b>{DISPF["exn_med"]:.0f}pp</b>'
        f'（{mlab(CUR)} {DISPF["exn_now"]:.0f}pp）—— '
        '即「同期各家增速相差几十个百分点」不靠存储周期也成立。'
        '<br><b>这是 pp 不是 %。</b>两条同比之差只能用百分点：'
        '把「+50% 与 +10%」说成「高 5 倍」会随基数变，说成「高 40pp」不会。'
        # 本图是七家的**派生量**，图上没有任何一家自己的线 —— 所以断点说明的引导语
        # 不能照抄默认那句（默认那句在读者眼里指的是「这条线在这里断了」）。
        + (('<br>' + brk_note(
            IDX_YOY,
            lead='<b>红色竖虚线 = 某一位成员的口径断点</b>，它会经由那一家的同比传导进本图的极差：'))
           if brk_in(IDX_YOY)[0] else '')),
    **({'break_at': brk_in(IDX_YOY)[0], 'break_label': brk_in(IDX_YOY)[1]}
       if brk_in(IDX_YOY)[0] else {}),
})

# ── ⟨ex:node-split⟩ 本页唯一一张比值图 ───────────────────────────────────
# ⚠ **为什么只有一张 —— 这一段是本图存在的全部理由，改图之前先读完。**
# 「多画几张比值图」是横截面页最容易犯的错，有两条硬道理挡着：
#   ① **比值的增速不含新信息。** 恒等式 Δ12 log(a/b) ≡ 单月同比_a − 单月同比_b
#      （本轮实测最大误差 4.4e-16）。也就是说比值线的同比，等于页上已有的两条同比线
#      相减 —— 画出来是把同一批数换个样子再讲一遍。比值**唯一**的新内容是**水平**。
#   ② **而水平要能读，得先有个锚。** 本轮对十组比值做了 ADF（对数比值、含常数与趋势）：
#      **十组全部无法拒绝单位根**。没有锚，「现在处在历史第 3 百分位」就只是装饰 ——
#      一条随机游走的分位数不指代任何「贵/便宜」。
# ⇒ 只有一组通过了「水平确实在持续移动、且移动没有回头」这一关：先进 vs 成熟制程。
#    另外几组各自倒在哪一条上，写在本图图注与页尾里，那也是本页的分析内容之一。
_NODE = (NTD['tsm'].rolling(12, min_periods=12).sum()
         / NTD['umc'].rolling(12, min_periods=12).sum()).reindex(IDX).dropna()


def _cagr(x):
    """对数线性拟合出来的年化斜率（%/年）。点数不够返回 None。"""
    if len(x) < 24:
        return None
    b = np.polyfit(np.arange(len(x)), np.log(x.values), 1)[0]
    return (np.exp(b * 12) - 1) * 100


_ND_DD = (_NODE / _NODE.cummax() - 1.0) * 100.0
_ND_36 = _cagr(_NODE.iloc[-36:])
_ND_ALL = _cagr(_NODE)
ex.append({
    'n': E_NODE, 'kind': 'lines', 'full': True, 'height': LINE_H,
    'fmt': 'f1', 'label_fmt': 'f1', 'yfmt': 'f1',
    'title': (f'先进制程与成熟制程的分离：{NAME["tsm"]} ÷ {NAME["umc"]}（近 12 个月合计之比）'
              f'—— {mlab(_NODE.index[0])} {_NODE.iloc[0]:.1f} 倍 → {mlab(CUR)} '
              f'{_NODE.iloc[-1]:.1f} 倍'),
    'xlabels': [mlab(p) for p in _NODE.index], 'ylab': '倍（近 12 个月营收合计之比）',
    'zero_base': True, 'end_label': True,
    'series': [{'name': f'{NAME["tsm"]} ÷ {NAME["umc"]}', 'color': 'NAVY',
                'values': L(_NODE.values)}],
    'src_extra': ('两家都是晶圆代工，分别守在制程的两端；用近 12 个月合计相除是为了'
                  '把农历年与单月批次抹掉 —— 这条线读的是结构，不是当月景气。'),
    'note': (
        f'<b>{len(_NODE)} 个月里，这条线距离它自己的运行新高最多只回撤过 '
        f'{abs(_ND_DD.min()):.1f}%（{mlab(_ND_DD.idxmin())}）</b>，'
        f'而那恰好是成熟制程最紧的一段 —— 本该把它拉回去的环境，只拉回了不到 '
        f'{abs(_ND_DD.min()):.0f}%。'
        + (f'斜率还在加速：全窗 {_ND_ALL:+.0f}%/年，最近 36 个月 {_ND_36:+.0f}%/年。'
           if _ND_ALL and _ND_36 else '')
        + '<br><b>这是一条结构陈述，不是一个交易信号。</b>本轮实测：把这条比值对自己的'
        '趋势做实时（只用当期之前的数据）偏离，再去解释未来 12 个月的相对增长，'
        '系数在统计上与零无异 —— 也就是说它<b>说得出「分开了」，说不出「什么时候合回去」</b>，'
        '更不指示任何一边贵还是便宜。'
        '<br><b>本页为什么只有这一张比值图</b>：比值的增速恒等于两条同比线之差'
        f'（⟨ex:yoy-mfg@>:下面那张制造侧同比⟩上就有这两条），所以比值的新内容只有水平；'
        '而本轮对十组比值做单位根检验，<b>十组的水平都没有可依靠的锚</b>，'
        '只有这一组的水平在持续、单向、未曾回头地移动。'
        + (('<br>' + brk_note(IDX, ['tsm', 'umc'])) if brk_in(IDX, ['tsm', 'umc'])[0] else '')),
    **({'break_at': [i for i, p in enumerate(_NODE.index)
                     if p in {b[0] for b in BREAKS if b[1] in ('tsm', 'umc')}],
        'break_label': [NAME[b[1]] for b in BREAKS
                        if b[1] in ('tsm', 'umc') and b[0] in set(_NODE.index)]}
       if any(b[1] in ('tsm', 'umc') and b[0] in set(_NODE.index) for b in BREAKS) else {}),
})

# ── ⟨ex:rebased-mfg⟩ / ⟨ex:rebased-design⟩ 指数化 ────────────────────────
_NOISE_TXT = '、'.join(f'{NAME[k]} {NOISE[k]:.0f}%' for k in KEYS)
for _e, _side in ((E_REB_M, '制造'), (E_REB_D, '设计')):
    _ks = BY_SIDE[_side]
    _lastv = {k: float(REB[k].dropna().iloc[-1]) for k in _ks if len(REB[k].dropna())}
    _rank = sorted(_lastv, key=_lastv.get, reverse=True)
    ex.append({
        'n': _e, 'kind': 'lines', 'full': True, 'height': LINE_H,
        'fmt': 'f0', 'label_fmt': 'f0', 'yfmt': 'f0',
        'title': (f'{_side}侧：月营收指数（{mlab(BASE)} = 100，{MA} 个月移动平均）'
                  f'—— {mlab(CUR)} 领先的是{NAME[_rank[0]]}（{_lastv[_rank[0]]:.0f}）'),
        'xlabels': XL_REB, 'ylab': f'指数（{mlab(BASE)} = 100）',
        'zero_base': True, 'end_label': True,
        'series': _lines(_ks, IDX_REB, lambda k: REB[k]),
        'src_extra': (f'各家自己的新台币月营收，{MA} 个月移动平均后以 {mlab(BASE)} 为 100 '
                      '重定基。指数只反映<b>各家自己</b>的增长，条与条之间不做加总。'),
        'note': (
            f'<b>为什么是 {MA} 个月移动平均</b>：原始月值的中位环比在 '
            f'{min(NOISE.values()):.0f}%–{max(NOISE.values()):.0f}% 之间'
            f'（逐家：{_NOISE_TXT}），农历年与出货批次把线打得很碎。'
            '移动平均只压噪声，压不掉增长 —— 末点的离散度几乎不变。'
            f'<br><b>基期取 {mlab(BASE)}</b>（全仓统一基期）而不是七家共同起点 '
            f'{mlab(START)}：后者是二月，正撞农历年，'
            '拿一个当月本来就偏低的月份当 100，会让每条线的起跑都被垫高一截。'
            f'<br>{_axis_owner(_ks, IDX_REB, lambda k: REB[k])}'
            + (('<br>' + brk_note(IDX_REB, _ks)) if brk_in(IDX_REB, _ks)[0] else '')),
        **({'break_at': brk_in(IDX_REB, _ks)[0], 'break_label': brk_in(IDX_REB, _ks)[1]}
           if brk_in(IDX_REB, _ks)[0] else {}),
    })

# ── ⟨ex:yoy-mfg⟩ / ⟨ex:yoy-design⟩ 单月同比 ──────────────────────────────
# ⚠ 制造侧那张**不含南亚科**。这不是版面取舍，是 /nanya/ 那页自己定的读法：
#   「这里的『增速』在量级上不能跟晶圆代工或交易所那种个位数增长同框比较」
#   （build/mrspecs/nanya.py 的 _CYCLE_NOTE，本页不抄那句话、只遵守它）。
#   南亚科在 ⟨ex:yoy-heat⟩ 与 ⟨ex:growing-count⟩ 里都在，那两张不共用线性纵轴。
YOY_EXCLUDE = {'nanya'}
for _e, _side in ((E_YOY_M, '制造'), (E_YOY_D, '设计')):
    _ks = [k for k in BY_SIDE[_side] if k not in YOY_EXCLUDE]
    _out = [k for k in BY_SIDE[_side] if k in YOY_EXCLUDE]
    _rng = pd.concat([YOYS[k].reindex(IDX_YOY) for k in _ks]).dropna()
    ex.append({
        'n': _e, 'kind': 'lines', 'full': True, 'height': LINE_H,
        'fmt': 'pct0', 'label_fmt': 'pct0', 'yfmt': 'pct0',
        'title': f'{_side}侧：月营收的单月同比（single-month y/y，%）',
        'xlabels': XL_YOY, 'ylab': '% y/y（单月）', 'zero_line': True, 'end_label': True,
        'series': _lines(_ks, IDX_YOY, lambda k: YOYS[k]),
        'src_extra': ('单月同比 = 当月 ÷ 去年同月 − 1（build/yoy.py 的 mom_yoy，全站唯一实现）；'
                      '拿这张图上任意一家的当月柱除以十二个月前那根，就是线上这一点 ——'
                      '本页没有任何一条同比线取自公司公告值或还原值。'),
        'note': (
            f'本图区间 {_rng.min():+.0f}% ~ {_rng.max():+.0f}%。'
            + (f'<br><b>{"、".join(NAME[k] for k in _out)}不在这张图上。</b>'
               'DRAM 是标准品、营收 = 位元出货 × 合约价，两条腿同向时相乘，'
               '单月同比可以到三位数；跟个位数到两位数的代工增速共用一根线性纵轴，'
               '会把代工那几条压成直线。这条读法是 <code>/nanya/</code> 页自己定的，'
               '本页遵守它。它的同比在 Exhibit ⟨ex:yoy-heat⟩ 的矩阵里（按格着色，不共用纵轴）。'
               if _out else '')
            + (('<br>' + brk_note(IDX_YOY, _ks)) if brk_in(IDX_YOY, _ks)[0] else '')),
        **({'break_at': brk_in(IDX_YOY, _ks)[0], 'break_label': brk_in(IDX_YOY, _ks)[1]}
           if brk_in(IDX_YOY, _ks)[0] else {}),
    })

# ── ⟨ex:season-heat⟩ 季节性 ─────────────────────────────────────────────
_PK = {k: _peak_trough(k) for k in KEYS}
_pk_groups = {}
for _k in KEYS:
    _pk_groups.setdefault(_PK[_k][0], []).append(_k)
_PK_TXT = '；'.join(
    f'{MONTHS[m - 1]} 月 —— {"、".join(NAME[k] for k in ks)}'
    for m, ks in sorted(_pk_groups.items()) if m)
ex.append({
    'n': E_SEASON, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f0',
    'title': (f'季节性：每月营收相当于当年月均的百分之几（{SEASON_YRS[0]}–{SEASON_YRS[-1]} '
              f'{len(SEASON_YRS)} 个完整年的平均）'),
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': MONTHS,
    'matrix': [L([SEASON[k][m] for m in range(1, 13)]) for k in KEYS],
    'legend': '占当年月均（%，100 = 与当年月均持平）',
    'cell_h': 24, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': (f'只用<b>完整日历年</b>，且年份限定在共同窗口之内（{SEASON_YRS[0]}–'
                  f'{SEASON_YRS[-1]}）—— 七家用同一批年，否则比的是各自不同的历史时段。'),
    'note': (
        f'<b>低谷七家一致，高峰七家不一致。</b>'
        f'{sum(1 for k in KEYS if _PK[k][1] == 2)} 家的最低月是 2 月、'
        f'{sum(1 for k in KEYS if _PK[k][1] == 1)} 家是 1 月 —— 农历年停工是全组共同的，'
        '它是日历事件，不是景气信号。'
        f'<br>高峰却散在三个月上：{_PK_TXT}。'
        '设计侧靠里程碑与新案量产爬坡，代工与封测跟着下半年的消费电子备货，'
        '存储跟自己的合约价周期 —— 同一组公司的旺季不在同一个月，'
        '这也是⟨ex:growing-count@<:上面那张⟩里「同月涨跌不同向」的一部分来源。'
        '<br><b>这张图不是景气判断。</b>它把各年同月平均掉了，'
        f'{SEASON_YRS[0]}–{SEASON_YRS[-1]} 之间存储与 ASIC 两轮大周期的涨跌都落在同一批格子里 ——'
        '某一家的旺季指数偏高，可能只是它在某一年的那几个月刚好处在上行段。'
        '<br>色标同样是<b>本图自己的</b> 5/95 分位，与 Exhibit ⟨ex:yoy-heat⟩ 那张不可比。'),
})

# ── ⟨ex:corr⟩ 同比的两两相关 ────────────────────────────────────────────
_cm = []
for _i, _a in enumerate(KEYS):
    _row = []
    for _j, _b in enumerate(KEYS):
        _row.append(None if _i == _j else float(CORR.loc[_a, _b]))
    _cm.append(_row)
ex.append({
    'n': E_CORR, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f2',
    'title': (f'两两相关：单月同比，{spanl(IDX_YOY[0], LATEST)} 共 {CORR_N} 个月'
              f'（中位 {CORR_MED:+.2f}）'),
    'rows': [f'{NAME[k]} {CODE[k]}' for k in KEYS],
    'cols': [NAME[k] for k in KEYS],
    'matrix': _cm,
    'legend': '单月同比的皮尔逊相关系数',
    'cell_h': 26, 'row_lab_w': 104, 'row_head': '公司',
    'src_extra': ('对角线<b>留空</b>：一家与自己的相关恒为 1，既不含信息，'
                  '还会把 5/95 分位色标的上端整个占掉。'),
    'note': (
        f'<b>中位 {CORR_MED:+.2f} —— 这一组整体上并不同步。</b>'
        f'最高的一对是{NAME[CORR_HI[0]]}与{NAME[CORR_HI[1]]}（{CORR_HI[2]:+.2f}），'
        f'最低的一对是{NAME[CORR_LO[0]]}与{NAME[CORR_LO[1]]}（{CORR_LO[2]:+.2f}）。'
        '<br><b>不要把它读成领先滞后 —— 本页没有、也不会有那张图，而这是实测的结论。</b>'
        + (f'把另外六家对{NAME[LL["anchor"]]}做 ±{LL["span"]} 个月的错位相关，'
           '再问一个关键问题：<b>同样「在十三个错位里挑最好的那个」的动作，'
           '作用在两条毫无关系、但各自同样自相关的序列上，碰巧能挑出多大的提升？</b>'
           f'（{LL["B"]} 条相位随机化替代序列现算）。'
           f'答案是：实测提升最大的一家只有 {LL["gain_max"]:.2f}，'
           + ('而<b>六家没有一家超过这个「碰巧」的水平</b>'
              f'（最小 p = {LL["min_p"]:.2f}，全部远大于 0.05）—— '
              '也就是说这些「最佳错位」<b>连噪声都跑不赢</b>。'
              if LL['none_clears'] else
              f'其中最小 p = {LL["min_p"]:.2f}。')
           + f'（{len(LL["at0"])} 家的相关本来就在错位 0 期最高：'
           + '、'.join(NAME[k] for k in LL['at0']) + '。）'
           if LL else '错位相关在本页的窗口上算不出稳定结果。')
        + '<br><b>⚠ p 大不等于「肯定没关系」，等于「这点数据分不出来」。</b>'
        '本页窗口是七年上下，而这几条序列一轮周期两三年 —— 统共两三轮。'
        '在这种样本上「领先 10 个月」和「滞后 16 个月」常常是同一句话。'
        '把这个不确定性说清楚，比印一个看上去很确定的最佳错位诚实。'
        + (('<br><b>但有一条正面结论，而且它可以用。</b>'
            + '、'.join(f'{NAME[a]}–{NAME[b]} r(0)={v["r0"]:+.2f}'
                        for (a, b), v in LL['block'].items())
            + f'：{NAME["tsm"]}／{NAME["umc"]}／{NAME["ase"]}这三家'
              '<b>在同一个日历月里同步</b>，把它们错开一两个月不但没有提升，'
            + f'挑遍 ±{LL["span"]} 个月最多也只多 '
            + f'{max(v["gain"] for v in LL["block"].values()):.3f}。'
              '物理上晶圆到封测要一两个月，但三家都按出货认列，'
              '这个时滞比「一个月」这个记账颗粒还短，所以在月度数据上看不见。'
              '⇒ 读者可以拿这三家里先公告的那一家，当同月另外两家的<b>同期参照</b>；'
              '<b>但那是同期参照，不是预测</b>。')
           if LL and LL.get('block') else '')
        + (f'<br>{DISP["alchip"]}那一行值得单看：它对组内<b>另外六家全部为负</b>'
           f'（绝对值最大也只有 {_AL_MAXABS:.2f}），'
           '即它既不跟着这条链涨、也谈不上稳定地反着走 —— 就是不相干。'
           '它的月营收由少数几个 ASIC 项目的里程碑与量产排程决定，'
           '<b>把它当「设计端领先指标」读是错的</b>：本页实测它对台积电的同期相关是 '
           f'{LL["per"]["alchip"]["r0"]:+.2f}，错位怎么挑都跑不赢噪声（p = '
           f'{LL["per"]["alchip"]["p"]:.2f}）。'
           if LL and 'alchip' in LL.get('per', {}) and _AL_NEG == len(KEYS) - 1 else
           (f'<br>{DISP["alchip"]}对组内其余各家的相关绝对值最大 {_AL_MAXABS:.2f}，'
            '基本不相干 —— 它的月营收由少数几个 ASIC 项目的排程决定。'))
        + f'<br>矩阵本身用<b>单月同比</b>算（{CORR_N} 个月，没有挑区间）；'
        '上面那套错位检验用的是<b>单月同比的 3 个月移动平均</b> —— '
        '单月值的毛刺会主导「哪个错位最优」的挑选，那不是口径不一致，'
        '是两个问题该用两种平滑。'),
})



# ── ⟨ex:decomp⟩ 这七家其实是几个独立的赌注 ──────────────────────────────
if DEC:
    _dr = sorted(KEYS, key=lambda k: -DEC['per'][k]['sys_share'])
    _hi = _dr[0]
    _lo = [k for k in _dr if DEC['per'][k]['sys_share'] < 30]
    _neg = [k for k in KEYS if DEC['per'][k]['r'] < 0]
    ex.append({
        'n': E_DECOMP, 'kind': 'table', 'full': True,
        'title': ('把每家的波动拆成「跟着组里那个周期」与「它自己的」—— '
                  '七家并不是七个独立的赌注'),
        'idx': '公司',
        'cols': [['与组周期的相关', 'r'], ['被组周期解释的方差', 'r2'],
                 ['系统性占比', 'sys'], ['自身波动 σ', 'sd'], ['自己的那一份 σ', 'idio']],
        'rows': [{'xl': f'{NAME[k]} {CODE[k]}',
                  'r': f'{DEC["per"][k]["r"]:+.2f}',
                  'r2': f'{DEC["per"][k]["r2"]:.0f}%',
                  'sys': f'{DEC["per"][k]["sys_share"]:.0f}%',
                  'sd': f'{DEC["per"][k]["own_sd"]:.0f}pp',
                  'idio': f'{DEC["per"][k]["idio_sd"]:.0f}pp'} for k in _dr],
        'src_extra': (f'口径：各家 3MMA 单月同比，{DEC["n"]} 个月。组周期 = <b>其余六家'
                      '先按自身历史标准化再等权平均</b>（再归一到单位方差）。'),
        'note': (
            '<b>为什么组周期要先标准化再平均 —— 这一步不做，结论是反的。</b>'
            '直接拿六家同比的等权平均当「组周期」，那个平均数其实就是'
            f'{NAME[max(KEYS, key=lambda k: DEC["per"][k]["own_sd"])]}'
            '（它的波动是最小那家的十几倍），于是真正的共同周期被它盖掉。'
            '本轮实测：换成标准化因子之后，'
            f'{NAME["ase"]}被解释的方差从约 25% 跳到 {DEC["per"]["ase"]["r2"]:.0f}%、'
            f'{NAME["umc"]}从约 4% 跳到 {DEC["per"]["umc"]["r2"]:.0f}%。'
            '<br><b>这张表最直接的用处：数一数你手上其实押了几件事。</b>'
            f'{NAME[_hi]}是这一组的温度计（相关 {DEC["per"][_hi]["r"]:+.2f}，'
            f'{DEC["per"][_hi]["r2"]:.0f}% 的波动由组周期解释）——'
            '所有芯片最后都要经过封测，它天然是聚合点。'
            + (f'而{"、".join(NAME[k] for k in _lo)}的波动{"大部分" if len(_lo) > 1 else ""}'
               f'是自己的（系统性占比不到 30%）：'
               '存储走自己的合约价周期，无晶圆厂设计走自己的产品周期。'
               if _lo else '')
            + (f'<br>{"、".join(NAME[k] for k in _neg)}是<b>负的</b>'
               f'（{DEC["per"][_neg[0]]["r"]:+.2f}）—— 它不但不跟着这条链涨，'
               '还略微反着走。ASIC 设计服务的月营收由少数几个项目的里程碑与量产排程决定，'
               '跟整条链的景气不是一回事。' if _neg else '')
            + '<br>⚠ <b>本表不印 beta。</b>「每 1σ 组周期对应多少 pp 自身同比」那个系数，'
            f'在{NAME[max(KEYS, key=lambda k: DEC["per"][k]["own_sd"])]}身上的标准误大到'
            '与零无异；印在页面上会被当成一个可以拿去调仓位的参数用。'
            '这里只印相关、被解释的方差与两段 σ —— 它们说的是<b>结构</b>，不是弹性。'),
    })


# ─────────────────────── 末尾核对表（官方原始单位，未换算）───────────────────────
def raw_dec(k):
    """某家新台币列的**官方小数位** —— 同样从它自己的 spec 认，不在这里写死。

    这张表的标题写着「官方原始单位，未换算」，所以小数位也得是官方那个：
    联电 / 南亚科 / 创意 / 世芯的公告单位是 NT$ 千元，落库成 NT$mn 之后那三位
    小数**恰好就是官方的千元位**；舍掉它等于一边宣称未换算、一边丢掉三位官方数字
    （理由与 `build/mrspecs/umc.py` ① 逐字相同）。
    """
    spec = importlib.import_module(f'mrspecs.{k}').SPEC
    for node in (spec.get('value'), spec.get('alt')):
        node = node or {}
        if node.get('col') == NTDCOL[k]:
            d = node.get('raw_dec', node.get('dec'))
            if isinstance(d, int):
                return d
    return 0


RAW_DEC = {k: raw_dec(k) for k in KEYS}
_TBL_IDX = list(IDX[-TBL_MONTHS:])
TABLE = {
    'n': E_TABLE,
    'title': f'近 {len(_TBL_IDX)} 个月月营收核对表（NT$mn，官方原始单位，未换算）',
    'idx': '月份',
    'full': True,
    'cols': [[f'{NAME[k]} {CODE[k]}', k] for k in KEYS],
    'rows': [{'xl': mlab(p), **{
        k: (num(float(RAW[k][NTDCOL[k]].get(p)), RAW_DEC[k])
            if _fin(RAW[k][NTDCOL[k]].get(p)) else None) for k in KEYS}}
        for p in _TBL_IDX],
    'note': (
        '拿这张表去跟公司公告逐格对：七家的公告单位都是新台币，'
        f'{"、".join(NAME[k] for k in KEYS if RAW_DEC[k] >= 3)} 公告的是 NT$ 千元，'
        '本表保留三位小数 —— 那三位就是官方的千元位，不是凑出来的精度。'
        f'<br>{DISP["alchip"]}这一列是它 MOPS 申报表上的<b>新台币栏</b>；'
        '它的功能货币是美元，新台币栏 = 当月美元 × 当月换算汇率（官方註1）。'
        '所以<b>这一列逐月相加不等于它的官方本年累计</b>（官方累计走累计汇率，是另一个算式），'
        '本页也从不对它做任何加总 —— 只做同比与指数化，两者都不需要相加。'
        '<br><b>本表没有横向合计</b>：七家在同一条价值链的不同层，相加是重复计算。'),
}


# ─────────────────────────── 名词释义 ───────────────────────────
# 收词判据（CONTRACT §1）：本页的图与表里出现过、不看定义就会读错的词。
# `m/m`／`y/y`／`pp`／`3Y %ile` 这类全站通用读图约定**不收**（汇总表的 note 已经讲过）。
# 这里收的全是**本页特有**的：横截面页才有的门槛、本页自己造的统计量、
# 以及三处一望便知却会被读错的东西（价值链层、功能货币、矩阵色标）。
GLOSSARY = [
    ('共同最新月',
     '七家里<b>最慢</b>那一家的最新月。本页所有图统一截到它 —— 各家披露节奏散在次月第 '
     '7–15 天，若每家都画到自己的最新月，末端那几个月的「谁强谁弱」全是披露时点'
     '造成的假象。'),
    ('制造侧 / 设计侧',
     '本页把七家分成自有产能的四家（晶圆代工、封测、存储）与无厂的三家'
     '（IC 设计、ASIC 设计服务）。前者的周期跟着产能与稼动率走，后者跟着客户的'
     '设计定案与量产爬坡走 —— 折线图按它拆成两张，比的是同一类生意。'),
    ('价值链层',
     '汇总表分隔条上的那一行字，是<b>本页的编辑分类，不是公司的披露口径</b>。'
     '公司自己不按这个分法披露，它也不参与任何一个数的计算，只用来分组与排序。'),
    ('指数化（重定基）',
     f'把每家自己的月营收除以它在基期 {mlab(BASE)} 的值再乘 100。'
     '于是七条线从同一个起跑线出发，比的是<b>各自的增长倍数</b>，与体量无关；'
     '线与线之间不做任何加总。'),
    ('组内极差',
     '当月七家单月同比的<b>最大值减最小值</b>，单位是百分点（pp）。'
     '它量的是「同一个月里各家差得有多远」，一家的极端值会直接进到这个数里 —— '
     '所以本页另画一条去掉存储那家的对照线。'),
    ('功能货币',
     '公司记账用的那种货币。七家里六家是新台币；'
     f'{NAME["alchip"]}是美元，它 MOPS 申报表上的新台币栏是<b>按当月换算汇率折出来的</b>，'
     '不是原生记账数 —— 所以那一列逐月相加不等于它的官方本年累计。'),
    ('口径断点',
     '并表、出表或追溯重述使得某一家的序列在那个月前后不可直接连比，图上画一条'
     '红色竖虚线。横截面页的标签<b>点名公司</b>：七条线并排时不点名，会被读成'
     '「大家在这里都换了口径」。'),
    ('矩阵色标',
     '两张热力矩阵各自按<b>本图</b>全部格子的 5/95 分位定色阶。好处是极端月份顶到'
     '色阶两端、不会吃掉其余格子的分辨率；代价是<b>两张矩阵之间颜色不可比</b>。'),
]


# ─────────────────────────── 页尾说明 ───────────────────────────
def _brk_lines():
    _at, _lab, _det = brk_in(IDX)
    if not _at:
        return ('本页窗口内没有任何一家登记了口径断点 —— 这不等于历史上没发生过并表或重述，'
                '只等于七家的 spec 里没有落在这段窗口上的登记条目。')
    return ('本页窗口内共 ' + str(len(_det)) + ' 条：' + '；'.join(_det) + '。')


_LAGS = importlib.import_module('roster').LAG
_LAG_TXT = '、'.join(f'{NAME[k]} {_LAGS[k][0]}' for k in
                     sorted(KEYS, key=lambda k: _LAGS.get(k, (99,))[0]) if k in _LAGS)
_SLOW = max((k for k in KEYS if k in _LAGS), key=lambda k: _LAGS[k][0])

# ⚠ 第一条说的是**这页能拿来干什么**，不是口径。它放在最前面是因为「横着比七条
#   月营收」这件事本身不构成分析 —— 不写清楚它支持什么判断、不支持什么判断，
#   读者只会按自己本来的成见去读这几张图。里面每一个数都由上面现算，不写死。
NOTES = [
    ('<b>这页能支持什么判断 —— 以及明确不能支持什么。</b>'
     '<br><b>能：①「半导体」不要当一个东西读。</b>'
     f'{DISPF["n"]} 个可比月里，{DISPF["split_pct"]:.0f}% 的月份有人在涨的同时有人在跌'
     + (f'，去掉{NAME["nanya"]}之后六家仍有 {DISPF["exn_split_pct"]:.0f}%'
        if DISPF['exn_split_pct'] is not None else '')
     + '。把这七家当同一个景气读，多数月份会读错 —— 该问的是「哪一层在动」。'
     '<br><b>② 把「创新高」与「在填坑」分开。</b>同比的分母是去年同月，它对'
     '「这家本来有多大」一无所知。'
     + ((f'本月 {len(AT_HIGH)} 家的近 12 个月合计创新高，{len(BELOW)} 家仍低于自己的峰；'
         f'{NAME[BELOW[0]]}当月同比 {pct(_yy(BELOW[0]), 0)}，而它的近 12 个月合计是 '
         f'{pct(STATE[BELOW[0]]["r12_yoy"], 0)}、距自身峰 {pct(STATE[BELOW[0]]["gap"], 1)}。')
        if BELOW else '')
     + '两种情形在同比矩阵上长得一模一样，在 Exhibit ⟨ex:state⟩ 那张表上一眼分得开。'
     '<br><b>③ 用同一把尺看「谁更反常」。</b>七家同比的振幅差一个数量级，'
     '换成各家在自己历史里的百分位才可比（Exhibit ⟨ex:pctile-heat⟩）—— '
     '本月这把尺给出的第一名与同比第一名不是同一家。'
     '<br><b>④ 数清楚手上押了几件事。</b>把各家波动拆成「组周期」与「自己的」之后，'
     # ⚠ 这里逐家印**各自的**数，不要写「都不到 N%」那种概括 ——
     #   那种句子要跟着四舍五入走，7.4% 写成「不到 7%」就是一句假话。
     + (f'{NAME["ase"]}有 {DEC["per"]["ase"]["r2"]:.0f}% 的波动由组周期解释、'
        f'{NAME["umc"]} {DEC["per"]["umc"]["r2"]:.0f}%，'
        f'而{NAME["nanya"]}只有 {DEC["per"]["nanya"]["r2"]:.0f}%、'
        f'{NAME["mtk"]} {DEC["per"]["mtk"]["r2"]:.0f}%，'
        f'{NAME["alchip"]}是负相关（{DEC["per"]["alchip"]["r"]:+.2f}）。'
        '同时持有前两家更接近<b>一个</b>仓位，后三家才是各自独立的判断'
        if DEC else '')
     + '（Exhibit ⟨ex:decomp⟩）。'
     '<br><b>⑤ 拿公司自己的话去对账。</b>±50% 触发的 MOPS 备注是法定申报内容，'
     '有月度分部列的家还能当场验（Exhibit ⟨ex:official-check⟩）。'
     '<br><b>⑥ 时效。</b>七家在次月第 7–15 天就公告上月营收，比同期季报早约六周 —— '
     '<b>但这是披露节奏上的领先，不是经济上的领先</b>，两者别混。'
     '<br><b>不能：① 不能做领先滞后择时。</b>本页实测过并且明确不画那张图，'
     '判据与数写在 Exhibit ⟨ex:corr⟩ 的图注里。'
     '<br><b>② 不能读份额。</b>这七家凑不出一个闭合分母（台湾还有华邦、旺宏、力积电、'
     '联咏、瑞昱…，且各层的分母本来就不是同一个市场）。页上任何一处都没有「占几成」。'
     '<br><b>③ 不能读盈利。</b>本页只有营收：没有价格、没有毛利、没有费用。'
     '营收创新高与赚不赚钱是两件事，月营收答不了第二件。'
     '<br><b>④ 不能用比值判贵贱。</b>本轮对十组跨家比值做过单位根检验，'
     '<b>十组的水平都没有锚</b> ⇒「现在处在历史第几百分位」对它们不成立。'
     '页上只留了一张比值图（Exhibit ⟨ex:node-split⟩），留它的理由写在那张图的图注里。'
     '<br><b>⑤ 不能把分位当预测。</b>分位说的是「站在哪里」：本轮实测它对未来 '
     '3／6／12 个月的加速度没有可测关系，自助置信区间三个期限全部跨零；'
     '唯一稳定的前瞻性质是向中位回归，那是比值自身的性质。'
     '<br><b>⑥ 不能把一家的分部结论搬给另一家</b>，哪怕同层。'),

    ('<b>本页不做跨家加总，一次都不做。</b>七家在同一条价值链的不同层：'
     f'{"；".join(ly + " —— " + "、".join(NAME[k] for k in BY_LAYER[ly]) for ly in LAYERS)}。'
     f'{NAME["alchip"]}或{NAME["guc"]}的一颗 ASIC，设计费记在它们的营收里，'
     f'晶圆再向{NAME["tsm"]}下单、记进{NAME["tsm"]}的营收，封测再交给{NAME["ase"]}、'
     f'记进{NAME["ase"]}的营收 —— 同一颗芯片至少被数三次。'
     '所以页面上没有「七家合计」「谁占几成」，一个都没有；'
     '首页那条「不做跨家加总」的总规矩在这一组上不是量纲问题，是<b>重复计算</b>问题。'),

    ('<b>主口径是新台币，本页不折汇率。</b>七家按台湾《证券交易法》公告的都是'
     '新台币合并营业收入净额 —— 同一条法规、同一个单位、同一个节奏，'
     '这是本站口径最干净的一组横截面（交易所那几页要折汇率或造定基名义额，本页都不需要）。'
     '折美元只会把同一个常数乘进每一条线，增长率一点不变，却让人以为这里做过汇率处理。'),

    (f'<b>{DISP["alchip"]}是唯一一家新台币栏为折算值的</b>，它的功能货币是美元，'
     '新台币栏 = 当月美元 × 当月换算汇率（MOPS 官方註1）。本页仍取它的新台币栏：'
     '本页只做同比与指数化，两者都不需要加总，需要的是七家同一个计量货币；'
     '而新台币栏正是它按法规申报、台湾市场看到的那个数。'
     + (f'这件事有多大，本轮实测：{spanl(ALFX["a"], ALFX["b"])} 之间 NTD/USD 从 '
        f'{ALFX["fx_a"]:.4f} 到 {ALFX["fx_b"]:.4f}（{ALFX["fx_chg"]:+.2f}%），'
        f'按对数分解只占它同期新台币累计增长的 <b>{ALFX["share"]:.1f}%</b>，'
        f'其余是经营。逐月看，汇率的同比平均 {ALFX["absmean"]:.1f}%、'
        f'最大 {ALFX["absmax"]:.1f}%（{mlab(ALFX["absmax_m"])}），'
        f'{mlab(CUR)} 为 {ALFX["now"]:+.2f}%。'
        '⚠ 这里印的是<b>汇率同比</b>，不是「新台币同比与美元同比之差」：'
        '后者会随增速水平放大，它在同比 +200% 以上的月份能印出二十几 pp，'
        '而当月汇率其实只动了个位数 —— 那是度量假象。'
        '尺度无关的写法只有一个，且恒等于汇率同比：(1+新台币同比) ÷ (1+美元同比) − 1，'
        '本页每轮复验这个恒等式。'
        if ALFX else '')),

    (GATE_TXT + f' 七家的发布节奏（月末后第几天，来自 <code>build/roster.py</code> 的 LAG）：'
     f'{_LAG_TXT} —— <b>最慢的是{NAME[_SLOW]}</b>，通常由它决定本页能画到哪个月。'),

    ('<b>口径断点从各家自己的配置现读，本页不抄任何一条。</b>'
     '单公司页把断点登记在 <code>build/mrspecs/&lt;ticker&gt;.py</code> 里，'
     '本页构建时直接读那七份配置 —— 两边结构上不可能分叉，'
     '单公司页加一条，本页下次构建就跟着有。' + _brk_lines()
     + '每条竖虚线都<b>点名公司</b>：七条线并排时不点名会被读成「大家都换了口径」；'
     '一张图只画它自己画了的那几家的断点。'),

    (f'<b>{DISP["nanya"]}不进同比折线图。</b>DRAM 是标准品，营收 = 位元出货 × 合约价，'
     '两条腿同向时相乘，单月同比可以到三位数；与个位数到两位数的代工增速共用一根'
     '线性纵轴，会把代工那几条压成直线。这条读法是 <code>/nanya/</code> 页自己定的'
     '（「这是一条存储器周期序列」），本页遵守它。'
     '它在两张不共用纵轴的图上都在：同比矩阵按格着色，'
     '增长家数那张把它只算一家 —— 后者正是为了让结论不依赖它。'),

    (f'<b>窗口从 {mlab(START)} 起，因为{NAME["ase"]}的序列从那里起。</b>'
     '那是<b>口径起点</b>不是「最早可得」：控股公司 2018-04-30 才成立，'
     '更早的月报属于前身主体，主体不同、不可前接（它自己那页的【1】写了全部证据）。'
     f'另外六家的序列都更长（最早到 2013-01），本页不把它们截短来迁就 —— '
     '只是七家同框的图只能从共同起点画。'
     f'指数化基期取 {mlab(BASE)}（全站统一基期）而不是 {mlab(START)}：'
     '后者是二月、正撞农历年，拿一个本来就偏低的月份当 100，每条线的起跑都会被垫高。'),

    ('<b>抬头没有「官方发布于」那一行，这是有意留白。</b>横截面页的发布日取成员里'
     '最晚的那一个，缺任何一个成员就整体省略 —— 拿部分成员算出来的最大值会偏早，'
     f'而偏早的日期看上去完全正常。本页缺的不止一家，其中{NAME["alchip"]}是'
     '<b>结构性的缺</b>：它不发月营收新闻稿、也不预告日期，没有任何一处「源头自己写下的'
     '发布日」可取。与其编一个像模像样的日期，不如留白。'),

    ('<b>为什么没有一张图同时画七条线。</b>图表引擎只有六个数据色'
     '（第七个红色是断点竖线专用），写一个引擎不认得的色名不会报错、会静默退回深蓝。'
     '所以七家同框时身份一律靠<b>标签</b>承载（热力矩阵的行名），'
     '折线图则按制造 / 设计拆成两张、每张不超过四条。'
     '这不是迁就调色板：那条拆法本身就是一条业务轴。'),

    ('仅供个人研究，不构成投资建议。数值以公司原始披露为准，'
     '末尾核对表保留官方原始单位未做换算，可逐格对账。'),
]


# ─────────────────────── 页顶 brief（本月读数怎么读）───────────────────────
def compose_brief():
    """`build/brief.py` 的规矩：这里只把**事实**拼成句子，措辞在 Python 侧定死，
    页面不做任何判断。`B.render` 对成品长度有硬闸门（230–380 字），超了就失败 ——
    所以每一句都要短，宁可少说一件事。
    """
    yy = {k: _yy(k) for k in KEYS}
    ok = [k for k in KEYS if _fin(yy[k])]
    if not ok:
        return None
    hi, lo = max(ok, key=lambda k: yy[k]), min(ok, key=lambda k: yy[k])
    npos = int(GROW.dropna().iloc[-1]) if len(GROW.dropna()) else None

    s1 = (f'{zh(CUR)}，{len(KEYS)} 家里 {npos} 家单月同比为正，'
          f'最快的{NAME[hi]} {pct(yy[hi], 0)}、最慢的{NAME[lo]} {pct(yy[lo], 0)}。')
    s2 = ((f'但去掉基数与季节看环比，{"、".join(NAME[k] for k in _DIVERGE[:2])}'
           f'的动能已低于自身历史中位（{NAME[_DIVERGE[0]]} '
           f'{pct(MOM[_DIVERGE[0]]["prev"], 1)}→{pct(MOM[_DIVERGE[0]]["now"], 1)}）。')
          if _DIVERGE and MOM else None)
    s3 = ((f'分母也在动：运行速率不变的话，{NAME[_down]}的同比 {BASE_DRIFT[_down]:+.0f}pp、'
           f'{NAME[_up]} {BASE_DRIFT[_up]:+.0f}pp，与今年的生意无关。')
          if BASE_DRIFT else None)
    s4 = ((f'水平上，{len(AT_HIGH)} 家近 12 个月合计创新高，'
           f'{NAME[BELOW[0]]}仍低于自身峰 {pct(STATE[BELOW[0]]["gap"], 0)}。')
          if BELOW else None)
    s5 = ((f'{DISPF["n"]} 个月里只有 {DISPF["same_pct"]:.0f}% 是七家同向 —— '
           '这一组不在同一个周期上。') if DISPF else None)
    s6 = ('七家在价值链的不同层、营收互为上下游，本页只比增速与指数，不做任何加总。')
    # s4 是可让位的那一句：放得下就全出，超了先精简（B.fit_optional 的用法）。
    lines_ = [s1, s2 or '', s3 or '', s4 or '', s5 or '', s6]
    lines_[3] = B.fit_optional(
        lines_, 3, compact=lambda: (f'{len(AT_HIGH)} 家近 12 个月合计创新高。'
                                    if AT_HIGH else ''))
    return B.render([x for x in lines_ if x])


try:
    BRIEF = compose_brief()
except SystemExit as e:
    # B.render 的长度闸门（230–380 字）没过。**不让它拦住整页发布** —— brief 不是
    # 必填字段，缺了页面只是少一段导读；但也不要静默，否则下次有人改措辞把它撑爆，
    # 页面会一声不响地少掉一块。所以：打印真实原因，payload 里不写 brief。
    print(f'{TICKER}: brief 未写入（{e}）')
    BRIEF = None

_yy_now = {k: _yy(k) for k in KEYS}
_ok_now = [k for k in KEYS if _fin(_yy_now[k])]
_hi = max(_ok_now, key=lambda k: _yy_now[k]) if _ok_now else None
# 抬头那一行给**读数**，不给统计量。上一版印的是「最快与最慢相差 530pp」——
# 那是一个关于这组数据离散度的描述，读的人拿它做不了任何事。现在印的是本月
# 真正的分歧：同比与环比动能给出了不同的排序。分歧不存在的月份自动退回描述版。
_hd_pre = f'{zh(CUR)}：{len(KEYS)} 家同比{"全正" if int(GROW.dropna().iloc[-1]) == len(KEYS) else "分化"}'
if CHAIN_GAP and CHAIN_GAP['pct'] >= 90:
    _g0 = CHAIN_GAP
    HEADLINE = (f'{_hd_pre}；{LEG_ZH2[_g0["down"]]}比按{NAME["tsm"]}推算的高 '
                f'{_g0["now"]:+.0f}pp，是 {len(_g0["s"])} 个月里的第 '
                f'{_g0["pct"]:.0f} 百分位，已连续 {_g0["run"]} 个月同向')
elif _DIVERGE and MOM:
    _d0 = _DIVERGE[0]
    HEADLINE = (f'{_hd_pre}；但{NAME[_d0]}同比 {pct(_yy(_d0), 0)}、'
                f'季调环比动能已从 {pct(MOM[_d0]["prev"], 1)} 降到 {pct(MOM[_d0]["now"], 1)}，'
                f'低于它自己的历史中位')
elif BASE_DRIFT:
    _d0 = min(BASE_DRIFT, key=lambda k: BASE_DRIFT[k])
    HEADLINE = (f'{_hd_pre}；{NAME[_d0]}未来 {len(BASE_MONTHS)} 个月的同比'
                f'将因基数机械变动 {BASE_DRIFT[_d0]:+.0f}pp')
else:
    HEADLINE = f'{_hd_pre}，最快与最慢相差 {DISPF["sp_now"]:.0f}pp'

payload = {
    'ticker': TICKER,
    'tracker': '半导体组 · Taiwan Semiconductor Monthly Revenue Cross-Section',
    'title': f'半导体组（台股 7 家）：月营收横截面 — {zh(CUR)}',
    'data_through': str(LATEST),
    'through_label': zh(CUR),
    'subtitle': (f'台积电 / 联电 / 日月光 / 南亚科 / 联发科 / 世芯 / 创意 七家按台湾'
                 f'《证券交易法》公告的月度合并营收，{spanl(START, LATEST)}；'
                 '同一条法规、同一个单位、同一个节奏 —— 全部以新台币计量，不折汇率，'
                 '不做跨家加总。版式仿 Goldman Sachs GIR exhibit。'),
    'headline': HEADLINE,
    'hub_line': (f'{len(KEYS)} 家台股半导体月营收横截面：{mlab(CUR)} '
                 + (f'封测比按代工推算的高 {CHAIN_GAP["now"]:+.0f}pp（第 '
                    f'{CHAIN_GAP["pct"]:.0f} 百分位）'
                    if CHAIN_GAP and CHAIN_GAP['pct'] >= 90
                    else (f'{NAME[_DIVERGE[0]]}同比高而环比动能已低于自身中位'
                          if _DIVERGE else f'最快与最慢相差 {DISPF["sp_now"]:.0f}pp'))),
    'source': SRC,
    'xlabels': XL_YOY,
    'xlabels_long': XL_ALL,
    'summary': SUMMARY,
    'exhibits': ex,
    'table': TABLE,
    'notes': NOTES,
    'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
               '每张图右上角可切「表格」视图逐条核对原值 · '
               '仅供个人研究，不构成投资建议'),
}
if BRIEF:
    payload['brief'] = BRIEF
payload['glossary'] = gloss.render(GLOSSARY, where=f'{TICKER} glossary')

# ⚠ `source_date` 有意不给：横截面页取成员里最晚的那个发布日，缺任何一个成员就整体省略
#   （source_dates.latest_of 的语义）。本页七家里有四家台账无记录，其中世芯是**结构性**
#   的缺 —— 它不发月营收新闻稿、也不预告日期，`fetch/alchip.py` 明写「没有。这是一等
#   状态，不要给它设兜底」。所以这一行永远取不到，留白，理由写进页尾说明。
#   也**不给** `source_date_note`：那个字段是留给「源头根本不标发布日」的，
#   而本页另外三家只是台账还没记上，两种缺口不一样，不许拿一句话盖过去。


# ═══════════════════════════════════════════════════════════════════
# 自检：本页特有的三类错误，各一道；三道都是「图上看不出来」的那种
# ═══════════════════════════════════════════════════════════════════
def selfcheck_rosters():
    """本文件里几张**按 ticker 列举**的表必须与 KEYS 同增同删。

    `ROLE` / `RIVAL` / `PUBDAY` / `PUB_ORDER` 都是手写的逐家表。加一家成员而漏改
    其中任何一张，症状是 KeyError（好）或**默默少一行**（坏）—— 后者在页面上
    看不出来，只是那家从链条表里消失了。所以在这里一次性对账。
    """
    bad = []
    for nm, tbl in (('ROLE', ROLE), ('RIVAL', RIVAL), ('PUBDAY', PUBDAY)):
        miss, extra = set(KEYS) - set(tbl), set(tbl) - set(KEYS)
        if miss:
            bad.append(f'{nm} 缺：{"、".join(sorted(miss))}')
        if extra:
            bad.append(f'{nm} 多出：{"、".join(sorted(extra))}')
    if sorted(PUB_ORDER) != sorted(KEYS):
        bad.append(f'PUB_ORDER 与 KEYS 对不上：{PUB_ORDER}')
    for k, v in RIVAL.items():
        if v is not None and v not in KEYS:
            bad.append(f'RIVAL[{k!r}] 指向不存在的成员 {v!r}')
        if v is not None and RIVAL.get(v) != k:
            bad.append(f'RIVAL 不对称：{k}→{v} 而 {v}→{RIVAL.get(v)}')
    if bad:
        raise SystemExit('build/semi 名单自检失败：\n  · ' + '\n  · '.join(bad))
    return len(KEYS)


def selfcheck_colors():
    """同一张图里不许出现两条同色的线。

    本页有七家而引擎只有六个数据色，日月光与创意**共用 GOLD** —— 成立的前提是
    「它们从不同框」（一个在制造侧、一个在设计侧）。那是个约定，而约定拦不住
    任何东西：哪天有人把两侧并成一张图，页面上会出现两条一模一样的金线，
    图例写着两个名字，**引擎不会报错，截图也看不出来**。所以这里是一段会失败的代码。
    """
    bad = []
    for e in ex:
        seen = {}
        for s in e.get('series', []) or []:
            c = s.get('color')
            if c in seen:
                bad.append(f'Exhibit {e["n"]}「{e["title"][:24]}」：'
                           f'{seen[c]} 与 {s["name"]} 都是 {c}')
            seen[c] = s['name']
    if bad:
        raise SystemExit('build/semi 配色自检失败：\n  · ' + '\n  · '.join(bad))
    return sum(len(e.get('series', []) or []) for e in ex)


def selfcheck_rebased():
    """凡是纵轴写着「= 100」的图，基期那一格必须真的是 100。

    照搬 `build/exchanges_apac.py` 的 selfcheck_page 那一道：轴标题说指数、
    series 却喂了水平值，引擎不会报错，图看上去也完全正常（几条线按体量排开，
    像极了一张「谁体量大」的图），只有末点标签的数量级不对。
    ⚠ 本页的指数是 3MMA，前 MA−1 个月天然是 null —— 基期 BASE 在窗口左端，
      它必须有值，正好一并验到。
    """
    bad, n = [], 0
    for e in ex:
        if '= 100' not in e.get('ylab', '') or e.get('kind') != 'lines':
            continue
        n += 1
        xl = e.get('xlabels') or []
        want = mlab(BASE)
        if want not in xl:
            bad.append(f'Exhibit {e["n"]}：轴标题的基期 {want} 不在本图 xlabels 里')
            continue
        j = xl.index(want)
        hit = 0
        for s in e['series']:
            v = s['values'][j]
            if v is None:
                bad.append(f'Exhibit {e["n"]} 的「{s["name"]}」在基期 {want} 上是空的')
            elif abs(v - 100.0) > 0.01:
                bad.append(f'Exhibit {e["n"]} 的「{s["name"]}」在基期 {want} 上是 {v}，不是 100')
            else:
                hit += 1
        if not hit:
            bad.append(f'Exhibit {e["n"]}：基期 {want} 上没有任何一条序列等于 100')
    if bad:
        raise SystemExit('build/semi 指数化自检失败：\n  · ' + '\n  · '.join(bad))
    return n


def selfcheck_dense_and_text():
    """两件小事，都会静默出错：

    ① `mrwin.DENSE` 的图型（走 Catmull-Rom 平滑）里有 null，会画出一条塌到零的
       假线，还可能按 fmt 抛 TypeError 把本图之后的 exhibit 全部吃掉。本页有意
       全部用 `lines`（非平滑，null = 断笔），这一道验的是「有没有人改回去」。
    ② `page.js` 用纯文本写抬头那几个字段，塞 HTML 进去会把标签原样印在页面上。
    """
    bad = []
    for e in ex:
        if e.get('kind') in mrwin.DENSE:
            for s in (e.get('series') or []) + (e.get('stacks') or []):
                if any(v is None for v in s.get('values', [])):
                    bad.append(f'Exhibit {e["n"]}（{e["kind"]}，属 DENSE）的'
                               f'「{s.get("name")}」里有 null')
    for f in ('tracker', 'title', 'subtitle', 'headline', 'through_label', 'hub_line'):
        if '<' in str(payload.get(f, '')):
            bad.append(f'payload["{f}"] 里有 HTML 标签，但这个字段由 page.js 按纯文本写入')
    if bad:
        raise SystemExit('build/semi 自检失败：\n  · ' + '\n  · '.join(bad))


def main():
    n_ros = selfcheck_rosters()
    n_series = selfcheck_colors()
    n_reb = selfcheck_rebased()
    selfcheck_dense_and_text()
    # 排版：先 mrwin（决定通栏与 x 标签抽稀，并把实测数写进图注），
    # 再 axisfmt（补轴刻度小数位）。顺序不能反 —— 见 build/ice.py 的同款注释。
    mrwin.layout_all(ex)
    axisfmt.fix_all(ex)
    # 图号：补 id、正文里建图时的号换成 ⟨ex:id⟩，交出 ORDER；write_dash 编号兑号。
    exhibits.bind_ids(payload, EX_ID, E_TABLE, where=f'build/{TICKER}')
    payload['order'] = ORDER
    payload_guard.write_dash(OUT, payload, TICKER)

    print(f'共同最新月 {LATEST} | 七家: '
          + '、'.join(f'{NAME[k]}={LATEST_EACH[k]}' for k in KEYS))
    print(f'窗口 {spanl(START, LATEST)}（{len(IDX)} 个月）| 同比窗口 '
          f'{spanl(IDX_YOY[0], LATEST)}（{len(IDX_YOY)} 个月，'
          f'{"、".join(NAME[k] for k in YOY_LATE)} 起步最晚）')
    print(f'断点：现读 mrspecs，共 {len(BREAKS)} 条，落在本页窗口内 '
          f'{len(brk_in(IDX)[2])} 条')
    print(f'离散度：{DISPF["n"]} 个月里全体同向 {DISPF["same"]}（{DISPF["same_pct"]:.1f}%）、'
          f'硬分歧 {DISPF["hard"]}（{DISPF["hard_pct"]:.1f}%）| 极差中位 '
          f'{DISPF["sp_med"]:.1f}pp、峰值 {DISPF["sp_max"]:.1f}pp @{DISPF["sp_max_m"]}'
          f' | 去掉{NAME["nanya"]}后中位 {DISPF["exn_med"]:.1f}pp')
    print(f'指数化（{BASE_M}=100，{MA}MMA）末点：'
          + '、'.join(f'{NAME[k]} {float(REB[k].dropna().iloc[-1]):.0f}'
                      for k in sorted(KEYS, key=lambda k: -float(REB[k].dropna().iloc[-1]))))
    print(f'相关：{CORR_N} 个月，中位 {CORR_MED:+.2f}，'
          f'最高 {NAME[CORR_HI[0]]}–{NAME[CORR_HI[1]]} {CORR_HI[2]:+.2f}，'
          f'最低 {NAME[CORR_LO[0]]}–{NAME[CORR_LO[1]]} {CORR_LO[2]:+.2f}')
    if LL:
        print(f'错位相关（对{NAME[LL["anchor"]]}，±{LL["span"]} 月，3MMA 同比，'
              f'{LL["B"]} 条相位随机化零假设，n={LL["n"]}）：')
        for k, v in LL['per'].items():
            print(f'  {NAME[k]:<8} r(0)={v["r0"]:+.2f} 最佳k={v["best"]:+d} '
                  f'增益={v["gain"]:+.3f} | 零分布中位 {v["null_med"]:.3f}／95分位 '
                  f'{v["null_95"]:.3f} → p={v["p"]:.3f}')
        print(f'  ⇒ {"没有一家" if LL["none_clears"] else "有家"}跑赢零假设'
              f'（最小 p={LL["min_p"]:.3f}）—— 本页不画领先滞后图')
        print('  代工/封测块（唯一正面结论）：'
              + '、'.join(f'{NAME[a]}–{NAME[b]} r(0)={v["r0"]:+.2f} 最佳k={v["best"]:+d}'
                          for (a, b), v in LL['block'].items()))
    if ALFX:
        print(f'世芯汇率：{spanl(ALFX["a"], ALFX["b"])} NTD/USD {ALFX["fx_chg"]:+.2f}%，'
              f'占其新台币累计增长的 {ALFX["share"]:.2f}%（对数分解）；'
              f'恒等式 (1+y_NTD)/(1+y_USD)−1 ≡ 汇率同比 已复验')
    print(f'自检：逐家表 ROLE/RIVAL/PUBDAY/PUB_ORDER 与 {n_ros} 家名单一致 ✓ | '
          f'配色 {n_series} 条线无同图同色 ✓ | 指数化 {n_reb} 张「= 100」图'
          f'基期格等于 100 ✓ | DENSE/纯文本 ✓')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {TABLE["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
