# -*- coding: utf-8 -*-
"""世芯-KY（Alchip Technologies，3661.TW）月度营收页配置 —— 通用底座 `build/mrbase.py`。

本文件只有**数据与本家专属的事实**，没有图型逻辑。

━━ 本家与另外六家、与 TSM 都不同的一件事：功能货币是美元 ━━━━━━━━━━━━━━
MOPS 月营收申报表（`ajax_t05st10_ifrs`，co_id=3661）对本家一次给出**三个官方格子**：
本月營業收入淨額的**新台幣**欄、**功能性貨幣(美金)**欄，以及**本月換算匯率**。
官方页脚註1 写明恒等式：

    本月新台幣營業收入淨額 ＝ 本月功能性貨幣營業收入淨額 × 本月換算匯率

所以本家的美元栏是**公司申报的功能货币实绩**，新台币栏才是逐月折算值 ——
方向与 TSM 恰好相反（TSM 以新台币入账，美元线是拿 FRED 牌价折出来的推导值）。
`series/alchip.csv` 的 `fx_ntd_per_usd` 也是官方那个「本月換算匯率」，不是外部牌价。
抓取、逐月恒等式校验与重述体检见 `fetch/alchip.py`（该文件的 docstring 里有接口
原始回应与八条「口径坑」，本文件下面每条带数的说明都能在那里或在 CSV 上复算）。

━━ value / alt 的分工由「可不可加总」定，不由「哪个是头条」定 ━━━━━━━━━━━
各月用各月的换算汇率、官方本年累计走**累计**汇率（註2）⇒ 新台币列**十二个月相加
≠ 官方本年累计**（下面 `_ADD` 现算，本轮实测最差年 +0.72%）；同一检验在美元列上是
0.000008%，逐年全中。底座的季度桥 / QTD / YTD / TTM 合计（汇总表的「占 TTM 比重」行）全要过加总，
⇒ `value` 只能是美元列，新台币列进 `alt`（`summable: False`，只进核对表）。

━━ Ex5 / Ex6 / Ex8：本家两条腿与那条汇率线**同出一张官方表** ━━━━━━━━━━━━━
TSM 那张 Ex5 的美元线是拿本币 ÷ 外部牌价折的推导值（`fx.implied` 默认 True）；
本家两条线来自官方同一张表（`implied=False`）。

⚠️ **「两条腿都是官方值」本轮起不再是本家独有的性质**，别再把它写成「七家里唯一」：
日月光（ase）的月度新闻稿自印美元营收实绩，`series/ase.csv` 已落 `revenue_usd_mn` /
`revenue_atm_usd_mn` 两列，底座为这一形态开了 `fx.fgn_col`（见 `mrbase._FX` 的注释
「fgn_col 的家（日月光）」），它的美元腿同样是官方申报值。

本家真正独有的是**更强的两件事**，它们在底座里是**两个独立标志**，不许混着说：
  (a) 两条腿由官方页脚註1 的**恒等式**绑在一起 —— 日月光那两条是公司两次**独立**
      披露，底座在 `_read()` 里明写「任何依赖这条恒等式的算式都不许套到 fgn_col
      的家上」；
  (b) **Ex8 那条汇率线本身也是公司申报的**（`rate_filed`，本轮才从 `implied` 里劈
      出来；本家不显式给，取默认 `not implied` = True，图上印 "as filed"）。
      日月光 `implied=False` 但 `rate_filed=False`（它从不披露所用汇率，Ex8 挂的是
      H.10/FRED 外部牌价），TSM 两者都不是 —— 所以「美元腿是官方值」与「汇率线是
      官方申报的」是两件事，本家恰好同时成立，不等于它们是同一件事。

因果方向也相反，图注里写明：
**新台币那条线是被汇率决定的**，不是汇率去解释一个独立观测到的本币数。

⚠️ 依赖底座的 `fx.local_col` 一组字段（本币腿 ≠ 主序列）。底座不给这组字段时
行为一格不变（TSM 打补丁前后 `data/tsm.js` 逐字节相同，本轮实测），
而拼错字段会硬失败、不会被静默忽略。
"""
from . import _facts

_CSV = 'alchip.csv'
_C_USD = 'revenue_usd_mn'
_C_NTD = 'revenue_ntd_mn'
_C_FX = 'fx_ntd_per_usd'


# ══════════════════════════════════════════════════════════════════════════════
# 图注里的数**一个都不写死**：下面全部在 import 期从 series/alchip.csv 现算，
# 读不到源（文件缺、列缺、数不够）就退回不带数字的定性版本，不抛异常
# —— import 期抛异常会让 monthly_run 因为「少一句话」炸掉整批构建。
# ══════════════════════════════════════════════════════════════════════════════
_ADD = _facts.additivity_gap(_CSV, _C_NTD, 'ytd_revenue_ntd_mn')
_ADD_U = _facts.additivity_gap(_CSV, _C_USD, 'ytd_revenue_usd_mn')
_D = _facts.days_effect(_CSV, _C_USD)
_YX = _facts.yoy_extremes(_CSV, _C_USD)


def _ident_bp():
    """官方註1 那条恒等式的实测最大残差（基点）+ 月份 + 样本数。拿不到返回 None。

    这不是装饰性的核对：它是「新台币列确实是折算值、美元列确实是功能货币原值」
    这个**判断**的证据。残差应当只剩 4 位小数汇率的舍入（0.5e-4 ÷ 30 ≈ 0.17bp）；
    真要是两栏各自独立计量，残差不会这么规律地贴着舍入界。
    """
    rs = _facts._rows(_CSV)
    if not rs:
        return None
    worst, at, n = 0.0, None, 0
    for r in rs:
        ntd, usd, fx = (_facts._f(r.get(_C_NTD)), _facts._f(r.get(_C_USD)),
                        _facts._f(r.get(_C_FX)))
        if not (ntd and usd and fx):
            continue
        n += 1
        bp = abs(ntd - usd * fx) / ntd * 1e4
        if bp > worst:
            worst, at = bp, r['month']
    return {'bp': worst, 'at': at, 'n': n} if n else None


def _fx_swing():
    """換算匯率在本序列上的区间与最新值。拿不到返回 None。"""
    rs = _facts._rows(_CSV)
    if not rs:
        return None
    xs = [(r['month'], _facts._f(r.get(_C_FX))) for r in rs]
    xs = [(m, v) for m, v in xs if v]
    if len(xs) < 12:
        return None
    return {'lo': min(xs, key=lambda t: t[1]), 'hi': max(xs, key=lambda t: t[1]),
            'cur': xs[-1], 'n': len(xs)}


_ID = _ident_bp()
_FXS = _fx_swing()
_ROWS = _facts._rows(_CSV) or []


# ── 说明：本页的美元是申报值，不是折算值 ──────────────────────────────
_ORIG_NOTE = (
    '<b>本页的 US$ 是公司申报值，不是我们折出来的</b>：本家功能货币为美元，'
    'MOPS 月营收表同时给出新台币栏、功能性貨幣（美金）栏与本月換算匯率三个官方格子，'
    '页脚註1 写明三者的恒等式。'
    + (f'恒等式在本序列 {_ID["n"]} 个月上实测最大残差 <b>{_ID["bp"]:.4f} 个基点</b>'
       f'（{_ID["at"]}），量级与 4 位小数汇率的舍入（0.5e-4 ÷ 30 ≈ 0.17bp）一致 —— '
       '这正说明新台币栏是折算出来的、美元栏是原值。' if _ID else
       '（本次未能从 CSV 现算出恒等式残差，故只作定性表述。）')
    + '这与 TSM 那一页方向相反：那边以新台币入账、美元线是拿外部牌价折的推导值；'
      '本页反过来，<b>新台币才是被汇率逐月决定的那一栏</b>。')

_CAUSAL_NOTE = (
    '<b>汇率在本家是恒等式的一条腿，不是外生驱动因子</b>：因为 '
    '新台币 ≡ 美元 × 換算匯率，「汇率对新台币增速贡献了几个百分点」在本家是'
    '恒等式的代数重排，不是一个可归因的经营发现 —— 读它只能读出'
    '「以新台币计的那个头条数被汇率抬高/压低了多少」，读不出公司受了多大汇率冲击'
    '（真正的汇率暴露在成本端与对冲上，月营收公告看不到）。'
    + (f'本序列 {_FXS["n"]} 个月里换算汇率区间 {_FXS["lo"][1]:.4f}'
       f'（{_FXS["lo"][0]}）– {_FXS["hi"][1]:.4f}（{_FXS["hi"][0]}），'
       f'最新 {_FXS["cur"][1]:.4f}（{_FXS["cur"][0]}）。' if _FXS else ''))


# ── 说明：新台币列为什么只能进核对表 ────────────────────────────────────
if _ADD:
    _w = max(_ADD.items(), key=lambda kv: abs(kv[1]))
    _y = sorted(_ADD)[-1]
    _u_txt = ('；同一检验在美元列上逐年都不超过 '
              f'{max(abs(v) for v in _ADD_U.values()):.6f}%' if _ADD_U else '')
    _ADD_TXT = (f'实测 {len(_ADD)} 个完整年度，缺口最大的 {_w[0]} 年是 {_w[1]:+.3f}%、'
                f'最近的完整年 {_y} 年是 {_ADD[_y]:+.3f}%{_u_txt}。')
else:
    _ADD_TXT = ('各月用各月的换算汇率，因此逐月相加与官方本年累计（累计美元 × 累计换算'
                '汇率）不是同一个算式（本次未能从 CSV 现算出逐年缺口，故只作定性表述）。')

_ALT_NOTE = (
    '它是官方同表的「新台幣」栏，= 当月美元 × 当月换算汇率（官方註1），不是原生记账数。'
    '<b>各月汇率不同，十二个月相加不等于官方本年累计</b>'
    f'（官方累计 ≡ 累计美元 × <b>累计</b>换算汇率，是另一个算式）。{_ADD_TXT}'
    '所以它不进季度桥、不进 QTD/YTD、不进 12 个月滚动合计。'
    '留它在页上只为一件事：TWSE OpenAPI、MOPS 全市场彙總表与台湾媒体'
    '<b>只报新台币</b>，读者要能拿本页去跟那个数逐格对上。')


# ── 说明：短窗口图自 2016 起是主动选的窗口，不是数据边界 ──────────────────
#    底座的「短窗口图的起点与数据边界」那条总账只解释**窗口之内**各图差几格 lag，
#    不解释窗口本身为什么从 2016 起。本家数据自 2014-01 就有，副标题也照实写着
#    「覆盖 Jan-14 – … 共 N 个月」——不把这件事说破，页面读起来就是自相矛盾的。
def _win_note():
    if not _ROWS:
        return ('<b>短窗口图自 2016-01 起是主动选的窗口，不是数据边界</b>：'
                '本家序列起点早于 2016-01，早期月份仍完整保留在全历史图与热力矩阵上。')
    n_drop = sum(1 for r in _ROWS if r['month'] < '2016-01')
    return ('<b>短窗口图自 2016-01 起是<u>主动选的窗口</u>，不是数据边界</b>：'
            f'本家 MOPS 月营收自 <b>{_ROWS[0]["month"]}</b> 就有且逐月连续，'
            f'2016-01 之前那 <b>{n_drop} 个月</b>是被窗口<b>主动挡在外面</b>的，'
            '不是没有数 —— 本轮统一取 2016-01 起，为的是跨家看同一段时间轴'
            '（序列本身晚于 2016-01 的页面则自其序列起点起）。'
            '被挡掉的那两年<b>并没有从页面上消失</b>：全历史图与逐年×逐月同比矩阵'
            '都按全量口径画（矩阵的年份数已按本家的可用年数给足，没有第二次收窄），'
            '副标题「覆盖 …」写的也是全序列范围。'
            '只看短窗口图会低估本家的历史长度，请以全历史图为准。')


_WIN_NOTE = _win_note()


# ── 说明：序列为什么自 2014-01 起（这是口径边界，不是抓取偷懒）────────────
#    断点落在序列第 0 格，底座对第 0 格断点不画红线，所以只能写在这里。
#    三条依据都在 fetch/alchip.py 的「口径坑 2」里逐条实测过。
_START_NOTE = (
    '<b>序列自 2014-01 起，这是口径边界不是抓取上限</b>：MOPS 接口本身能查到 2013 年'
    '（旧的非 IFRS 接口更早到 2011-07），本页不取，三条理由都实测过（'
    '<code>fetch/alchip.py</code> 口径坑 2）——'
    '(1) <b>2013 及以前美元栏被舍入到整数仟元</b>，于是本页最核心的那句「美元列可加总」'
    '在那一段上不成立：2013 年 12 个月相加与官方本年累计差 +330ppm，'
    '而 2014 年同一检验是 −0.065ppm，相差约 5,000 倍；'
    '(2) 换算汇率栏 2013 及以前只有 2–3 位小数（29.07 / 29.5），2014 起是 4 位，'
    '恒等式核验的分辨率差一个量级；'
    '(3) 2013-01 是 ROC GAAP → Taiwan-IFRSs 的准则断点，而 IFRS 之前那一段<b>有真重述</b>'
    '（2011-12 当期申报 NT$336,689 仟元，一年后在 2012-12 那期的比较列里变成 '
    'NT$328,443 仟元，−2.4%）。2012-01 之后「去年同期」与上一年「本月」逐月相等。'
    '⇒ 拿 2013 及更早的数接上来，会让页面上「可加总」「恒等式成立」两句话同时失真。')


# ── 说明：日历与波动，以及热力矩阵该怎么读 ────────────────────────────
_LUMP_NOTE = (
    '<b>本页不做日均化，也不要把单月当趋势读</b>：本家是 ASIC 设计服务'
    '（NRE 里程碑 + turnkey 量产出货），营收按里程碑与出货批次认列，本身就是<b>块状</b>的，'
    '与晶圆厂那种连续产出不是一回事。'
    + (f'「按天数归一化」在本序列同样不成立：<code>(m/m) ~ (天数变化%)</code> 在 '
       f'{_D["n"]} 个月上的回归斜率是 {_D["slope"]:.2f} 而不是 1，'
       f'2 月对 1、3 月均值的实际比值 {_D["feb"]:.2f}（{_D["feb_n"]} 个年度平均）、'
       f'天数比值却是 {_D["feb_days"]:.2f}。' if _D else
       '（本次未能从 CSV 现算出天数回归，故只作定性表述。）')
    + (f'单月同比的实测跨度是 {_YX["min"]:+.0f}% – {_YX["max"]:+.0f}%'
       f'（{_YX["n"]} 个月，5–95 分位 {_YX["p5"]:+.0f}% – {_YX["p95"]:+.0f}%）；'
       '这个量级的摆动主要来自项目节奏，不来自日历。'
       '<b>热力矩阵因此只当极值图读</b>：色标在 5/95 分位之间线性插值，'
       '而本家绝大多数月份挤在色带中段，比较中等月份请直接读格子里的数字。'
       if _YX else ''))


SPEC = {
    'ticker': 'alchip',
    'name': 'Alchip',
    'tracker': 'Alchip Monthly Revenue Tracker',
    'title': '世芯-KY Alchip (3661.TW)：月度营收跟踪',
    'source': 'Source: Taiwan MOPS monthly revenue filing (t05st10_ifrs) for Alchip '
              'Technologies (3661.TW), functional-currency (US$) column as filed; '
              'format after Goldman Sachs GIR',
    'source_zh': 'MOPS 公开资讯观测站「采用 IFRSs 后之月营业收入资讯」（t05st10_ifrs）'
                 '世芯-KY 合并营业收入净额的「功能性貨幣（美金）」栏，原表单位 US$仟元，'
                 '未经会计师查核，台湾法定次月 10 日前公告'
                 '（https://mopsov.twse.com.tw/mops/web/t05st10_ifrs）；'
                 '新台币栏为官方按当月換算匯率逐月折算的那一栏',
    'csv': _CSV,

    # ── 主序列 = 官方申报的**功能货币（美元）**栏。
    #    本身已是 US$mn，不再除 ⇒ div=1.0 且 unit='mn'；沿用底座默认的 'bn'
    #    会把「US$230.7mn」印成「US$230.7bn」，差三个数量级。
    #    `summable=True` 在本家是**实测结论**不是声明：逐年 12 个月相加与官方本年累计
    #    的残差在 1e-5 % 以下（`_ADD_U` 现算）。新台币栏做不到，见 `alt`。
    'value': {'col': _C_USD, 'div': 1.0,
              'label': 'US$mn', 'sym': 'US$', 'unit': 'mn', 'dec': 1,
              # 官方原始格子是 US$仟元两位小数；本仓存 US$mn，
              # **5 位小数正好是原值右移三位** ⇒ 核对表逐格可与 MOPS 对字，
              # 不需要「约等于」。少一位就得四舍五入，那个属性就丢了。
              'raw_label': 'US$mn', 'raw_dec': 5,
              'zh': 'US$ revenue', 'ccy_zh': '美元',
              'summable': True},

    # 折算腿：只进核对表，结构上进不了任何加总。
    # dec=3：官方新台币栏是仟元整数，NT$mn 三位小数是无损搬运（7,433,152 仟元 →
    # 7433.152），核对表同样逐格可对字。
    'alt': {'col': _C_NTD, 'label': 'Consolidated revenue (NT$mn, translated)',
            'dec': 3, 'zh': '新台币折算列', 'summable': False, 'note_zh': _ALT_NOTE},

    # `official_yoy` 不给：series/alchip.csv 没有公告同比列，同比一律走 build/yoy.py 自算。
    # 底座会照实说「本页 spec 未登记 official_yoy」，并明说那不等于「公司没披露」——
    # 后者是关于公司公告内容的事实断言，本轮没核到可点开复核的出处，所以不说。

    # ── 汇率腿。本家三个格子全是官方申报值，所以 Ex5 / Ex6 / Ex8 全部成立。──────
    'fx': {
        # 换算汇率与两栏营收来自 MOPS **同一张表**，所以就指回主 CSV，
        # 不像 TSM 那样另开一张外部牌价表。
        'csv': _CSV, 'col': _C_FX, 'quote': 'NTD per USD',
        'src': '台湾 MOPS 月营收申报表「本月換算匯率」栏（co_id=3661，'
               '<code>ajax_t05st10_ifrs</code>）—— 公司自己申报的换算汇率，'
               '不是 H.10 / FRED / 台银牌价；'
               'https://mopsov.twse.com.tw/mops/web/t05st10_ifrs',
        # TSM 那句「按当月平均汇率一次性折算，是个近似」在本家**不成立**：
        # 这里没有近似，官方恒等式就是这么定义的。
        'assumption': 'No approximation: the NT$ column is the company-filed '
                      'translation at its own filed monthly rate.',

        # ↓ 「本币腿 ≠ 主序列」的一组字段。本币腿在另一列，且两条腿都是官方值。
        'local_col': _C_NTD,
        'local_label': 'NT$ revenue', 'local_zh': '新台币', 'local_sym': 'NT$',
        'implied': False,

        'usd_share_note': {
            'en': 'Alchip is a Cayman (KY) issuer whose functional currency is the '
                  'US dollar: the US$ column is the filed measurement and the NT$ '
                  'column is the filed translation of it, not a separate measurement.',
            'zh': '世芯-KY 的功能货币是美元，美元栏是申报的计量本身，'
                  '新台币那一栏是官方按自报汇率折算出来的，不是另一次独立计量 —— '
                  '所以这条汇率线不是「影响因素」，它是恒等式本身',
            'src': 'MOPS 月营收申报表页脚註1「本月新台幣營業收入淨額＝'
                   '本月功能性貨幣營業收入淨額×本月換算匯率」，'
                   'https://mopsov.twse.com.tw/mops/web/t05st10_ifrs'
                   '（本仓的逐月抓取与恒等式校验见 <code>fetch/alchip.py</code>；'
                   '功能货币政策本身随年报「重要會計政策」之功能性貨幣一节复核）',
        },
    },

    'window': {
        # 本轮统一自 2016-01 起，为的是跨家看同一段时间轴。
        # ⚠️ 不要把这句写成「七家统一取 2016-01」：联发科（2018-01 起）、日月光
        #    （2018-05 起）、创意（2017-01 起）三家的序列本身就晚于 2016-01，
        #    它们的 spec 给的是 `x_from=None`（自序列起点起）。真正的规则是
        #    「2016-01 与本家序列起点取其晚者」，不是七家同一个日期。
        # 本家 series 自 2014-01 起 ⇒ 这是**主动选的短窗口**，不是数据边界，
        # 由 _WIN_NOTE 在页面上说破（副标题写的是全序列范围，不说破就自相矛盾）。
        'x_from': '2016-01',
        # 单月同比自 2015-01 起有值，正好 12 个年度 ⇒ 矩阵给足，不在第二个地方
        # 再悄悄收窄一次（那会让 _WIN_NOTE 里「矩阵按全量口径画」这句变成假话）。
        'heat_years': 12,
        'check_rows': 13,
    },

    # `breaks` 为空：唯一的口径断点（2013-01 准则切换 + 美元栏精度跳变）落在序列
    # 第 0 格之前，底座对第 0 格不画线，改由 _START_NOTE 说清楚。
    #
    # **不给 `continuity`**：那是「口径连续、未发生并表或重述」的事实断言，需要年报
    # 合并范围附注这一级的出处。本轮拿得到的最强证据只是「官方每期自带的『去年同期』
    # 与本仓存的 M−12 逐字相等」（fetch/alchip.py 的重述体检每轮在跑），那只证明
    # 披露值没被改写，证不了合并范围没变过。给不出出处就整个不给。

    # ⚠️ 「右轴滚动同比」是**这一页**的排版描述，2026-09 起右轴改成单月同比，
    #    再写「滚动」就是在描述一张页面上不存在的图（版式仿的是 GS 的排版，
    #    不是它的口径 —— 口径由 CONTRACT §6 与页面所有者定）。
    'format_source': '版式仿 Goldman Sachs GIR 台股月营收报告（Exhibit 1-2 的柱 + '
                     '右轴同比、长历史层与逐年×逐月同比矩阵）',

    'notes': [_ORIG_NOTE, _CAUSAL_NOTE, _WIN_NOTE, _START_NOTE, _LUMP_NOTE],

    'footer': '图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
              '仅供个人研究，不构成投资建议',
}
