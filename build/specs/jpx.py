# -*- coding: utf-8 -*-
"""JPX（日本取引所グループ）单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/jpx.csv 的哪些列、按什么中文名、什么单位、什么格式器上页面」。
不算数、不画图、不碰公共代码 —— 那三件事全在底座里。
整份文件可以直接删掉：删了 JPX 页就没了，别的页一行都不受影响。

━━ 本页的核心命题：同一个业务，两个口径的十年趋势符号相反 ━━
JPX 衍生品有两条并行的总量序列，Exhibit 群 G1 把它们画在一起：

    adv_deriv_total_raw_kcontracts   原始张数    2016-06 1572.1 → 2026-06 2365.7   +50.5%
    adv_deriv_total_lgeq_kcontracts  大合约当量  2016-06  706.3 → 2026-06  522.6   −26.0%
    raw / lgeq 倍率                              2016-06  2.23x → 2026-06   4.53x

（以上四组数字是本次从 series/jpx.csv 直接算出来的，不是抄侦察稿。）

倍率单调走高的原因是**迷你化**：日経225mini 是大型合约的 1/10、マイクロ 是 1/100，
ミニTOPIX、長期国債先物（現金決済型ミニ）、日経225ミニオプション 同样是 1/10。
所以「张数」这个计量单位本身在缩小 —— 原始张数上涨一半，实际风险敞口反而少了四分之一。

**表述纪律（页面上不许写错的一句）**：折算系数（1/10、1/100）来自官方合约规格，
JPX 自己的 IR 脚注也写明 "figures ... are calculated using factors of 1/10 and 1/100"；
但**逐月的当量序列是 fetch/jpx.py 折算出来的，JPX 并不逐月发布这一列**。
它的可信度靠对账：fetch/jpx.py 用 IR 的季度合计校准 ——
Financial Derivatives IR 印 23 / 24 百万张，本表折算得 23.63 / 24.58；
Commodity Derivatives IR 印 141 / 349 万张，本表折算得 141.48 / 349.41。
⇒ 页面文案一律写「大合约当量（本仓按官方合约规格折算，已对账 JPX IR 季度值）」，
   **不许写「官方发布」**。

━━ 为什么按「共同起点」分组 ━━
本页三档起点：2014-12（绝大多数列）、2023-05（マイクロ与ミニオプション上线）。
同一个 group 里混起点，底座若取共同窗口就会把长历史砍成 38 个月，
若不取就会给平滑类图型喂 null（gs_line 会 null.toFixed() 抛 TypeError，
整张卡片之后的 exhibit 全不渲染，见 docs/CHART_KINDS.md §1.2）。
所以起点不同的列一律各成一组。

━━ 有意不上页面的列，以及理由 ━━
· trading_days / deriv_trading_days —— 分母，不是经营指标；ADV 已经除过了。
· val_cash_total_jpytn / vol_cash_dom_shares_mn —— 月总量，= 日均 × 交易日，
  与 adt_* 同一条信息的两种写法，上页面只会让人以为多了一个指标。
· cmdty_proforma —— 0/1 标记列，它的用途是**推导断点**（见下面 _first_absent），
  不是画图。
· series/jpx_investors.csv（周频投资主体别买卖动向）—— **本版不做**：
  它是周频（week_end），本契约的 groups 只吃 series/jpx.csv 的月频列，
  硬塞进来要么改契约、要么在底座里为 JPX 开一条周频分支 —— 两者都违背
  「删掉不留残渣、不许 if ticker == 'jpx'」。要做就另起一页，不缠这一页。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'jpx.csv')


# ── 断点从 CSV 读，不写死 ──────────────────────────────────────────────
# 为什么内联而不抽公共函数：本页要能整份删掉不留残渣。这两个函数只做
# 「列 → 有值/无值的第一个月」的字典查询，不含任何统计口径，
# 与 build/pctile.py 记的那条教训（各写各的分位数导致两页判定相反）不是一回事。
# 任何一步失败都返回 None —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批。
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _first_present(col):
    """该列第一个有值的月份。"""
    for r in _rows():
        if col in r and r[col].strip():
            return r['month']
    return None


def _first_absent(col):
    """该列**由有值转为空**的第一个月（标记列 cmdty_proforma 用这条）。"""
    seen = False
    for r in _rows():
        if col not in r:
            return None
        if r[col].strip():
            seen = True
        elif seen:
            return r['month']
    return None


def _num(r, col):
    """CSV 里一格 → float，空格子/非数返回 None（不拿 0 冒充缺失）。"""
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


def _wedges():
    """两个「如果口径没对齐会怎样」的实测幅度，全部从 CSV 现算、一个都不写死。

    量价分解的分母是内国株成交股数，所以分子必须也只含内国株。本表里另外两个候选分子
    各带一层杂质，这里把杂质**量出来**：口径对不齐的代价不该靠形容词交代。

      w_total  = adt_cash_total ÷ adt_cash_dom_stocks − 1
                 = 含 ETF/REIT + 外国株时，均价被抬高多少（%）
      w_stocks = adt_cash_stocks ÷ adt_cash_dom_stocks − 1
                 = 只含外国株那一层杂质时，均价被抬高多少（ppm）

    返回 (最新月, w_total 最新 %, w_total 全期 max %, w_stocks 最新 ppm, w_stocks 全期 max ppm)；
    算不出全部返回 None。
    """
    rows = _rows()
    cur = None
    mx_t, mx_s = 0.0, 0.0
    for r in rows:
        dom = _num(r, 'adt_cash_dom_stocks_jpytn')
        tot = _num(r, 'adt_cash_total_jpytn')
        stk = _num(r, 'adt_cash_stocks_jpytn')
        if not dom or tot is None or stk is None:
            continue
        wt, ws = (tot / dom - 1.0) * 100.0, (stk / dom - 1.0) * 1e6
        mx_t, mx_s = max(mx_t, wt), max(mx_s, ws)
        cur = (r['month'], wt, ws)
    if cur is None:
        return (None,) * 5
    return cur[0], cur[1], mx_t, cur[2], mx_s


def _tradingday_spread():
    """立会日数的最小/最大值与相对差（%）—— 单月同比毛刺的三个来源之一，现算不写死。"""
    v = [d for d in (_num(r, 'trading_days') for r in _rows()) if d]
    if not v:
        return None, None, None
    return min(v), max(v), (max(v) / min(v) - 1.0) * 100.0


_WM, _WT, _WTX, _WS, _WSX = _wedges()
_DMIN, _DMAX, _DSPR = _tradingday_spread()

# ── 图 A（量价分解）的口径交代 ────────────────────────────────────────────
# 本页最关键的一条判断写在这里：分子分母到底是不是同一批标的。
_DECOMP_NOTE = (
    '<b>分子是为这张图新建的一列。</b>'
    '<code>adt_cash_dom_stocks_jpytn</code> / <code>val_cash_dom_stocks_jpytn</code>'
    '（内国株成交额）与 <code>adv_cash_dom_shares_mn</code> / '
    '<code>vol_cash_dom_shares_mn</code>（内国株成交股数）在 <code>fetch/jpx.py</code> 里'
    '<b>出自同一次分段累加</b>（同一个 <code>dom_*</code> 累加器）：同为プライム/スタンダード/'
    'グロース/TOKYO PRO 四段，同为立会市場 + ToSTNeT，同为单边计，同一份 '
    '<code>historical-genbutsu.xlsx</code>。所以这一对是<b>逐段同口径</b>，'
    '相除得到的均价没有口径楔子。'

    '<b>本表原有的两个候选分子各带一层杂质，代价实测如下。</b>'
    + (f'（一）合计 ADT <code>adt_cash_total_jpytn</code> 还含 ETF/ETN/REIT + 外国株，'
       f'而股数列数的是<b>股</b>、根本不含 ETF/REIT 的「口数」——'
       f'拿它当分子，均价被抬高 {_WT:.2f}%（{_WM}），全期最大 {_WTX:.2f}%，'
       f'且这个楔子逐年在变，变化量会被整个读成「价的贡献」。'
       f'（二）股票 ADT <code>adt_cash_stocks_jpytn</code> = 内国株 + 外国株，'
       f'杂质只剩外国株一层，均价被抬高 {_WS:.1f} ppm（{_WM}），全期最大 {_WSX:.0f} ppm。'
       if _WT is not None else
       '（一）合计 ADT 含 ETF/ETN/REIT + 外国株，而股数列不含 ETF/REIT 的「口数」；'
       '（二）股票 ADT 含外国株而股数列不含。两者都会造出口径楔子。')
    + '第二种小到可以忽略，但<b>本页仍然不用它</b> —— 「小到可以忽略」是量出来之后才知道的，'
    '而分解图的读者没法从图上看出分子里混了什么。既然源表分得开，就分干净再相除。'

    '<b>没有指数序列可以并列。</b>把「均价增长」与 TOPIX / 日経225 的涨幅并排，'
    '两者之差就是成交结构效应（贵的票成交占比变化）。但 <code>series/jpx.csv</code> 里'
    '没有任何指数点位列，本仓其余 series 也没有，'
    '而这张图的规矩是<b>只用本仓已有的数据</b>，不为一张图去外部抓一条没有入库口径的序列。'
    '所以这里只能说：均价里含结构效应，但本页拆不出它有多大。'
)

# ── 图 B（量的水平值 + 滚动同比）的口径交代 ──────────────────────────────
_TTM_NOTE = (
    '<b>JPX 的立会日数本身就是一个大扰动</b>'
    + (f'：本序列覆盖期内每月 {_DMIN:.0f}–{_DMAX:.0f} 个立会日，'
       f'两端相差 {_DSPR:.0f}%。' if _DSPR is not None else '。')
    + '日本的假期集中在 1 月、5 月（黄金周）、8 月与 9 月，'
    '所以「当月合计股数」的单月同比里，有一大截只是「今年这个月比去年多开/少开了几天市」。'
    '滚动 12 个月合计把这一层整个抹掉：任意连续 12 个月都覆盖同一套日历。'

    '<b>柱用日均、线用滚动合计，是两个不同的问题。</b>'
    '日均（<code>adv_cash_dom_shares_mn</code>）回答「开市那天有多热」，'
    '已经把立会日数除掉了；滚动同比（<code>vol_cash_dom_shares_mn</code> 的 12 个月合计）'
    '回答「一整年的总量在不在长」。要看单月的量价对照请回上面的现货成交组图。'
)


def _breaks():
    out = []
    # 商品関連在宽表里被 pro-forma 回填到 1985 年，而 JPX 2019-10 才收购 TOCOM、
    # 旧 TOCOM 品种 2020-07-27 才迁入 OSE。cmdty_proforma=1 的月份都是回填期，
    # 它转空的那个月就是「从这里起商品是 JPX 自己的业务」。实测 = 2020-08。
    m = _first_absent('cmdty_proforma')
    if m:
        out.append({'month': m, 'zh': '商品関連自此为实际业务；此前为 TOCOM 回填的 pro-forma'})
    # マイクロ（1/100）上线 —— 原始张数序列从这里起再次被稀释，
    # raw/当量倍率 2023-04 还是 2.9x，2026-06 已经 4.5x。实测 = 2023-05。
    m = _first_present('adv_n225_micro_kcontracts')
    if m:
        out.append({'month': m, 'zh': '日経225マイクロ（1/100）上线，原始张数口径再次稀释'})
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 统一按月份排。
    return sorted(out, key=lambda b: b['month'])


SPEC = {
    'ticker': 'jpx',
    'name': 'Japan Exchange Group',
    'title': '日本交易所集团（JPX）月度经营指标',
    'csv': 'jpx.csv',
    'ccy': 'JPY',
    'source': ('Source: JPX 統計月報（historical-genbutsu / historical-jika / '
               'soukatsu_M / tv_ts 月次）; 大合约当量按官方合约规格折算并对账 JPX IR 季度值; '
               'format after Goldman Sachs GIR'),

    # 头条：现货与衍生品各一条。两者同源于 JPX 每月的统计文件、同一节奏发布，
    # 2014-12 起逐月无洞（实测 139/139），符合「历史长、发布快、无空洞」。
    # 衍生品那条**只能用当量**：用原始张数当头条，页面第一眼就会讲反话。
    'headline': [
        {'col': 'adt_cash_total_jpytn', 'zh': '东证现货 ADT',
         'unit': '¥tn/day', 'fmt': 'f1'},
        {'col': 'adv_deriv_total_lgeq_kcontracts', 'zh': '大阪衍生品 ADV（大合约当量）',
         'unit': 'k contracts/day', 'fmt': 'f0'},
    ],

    'groups': [
        # ── G1 本页最重要的一张：两个口径必须画在一起 ────────────────
        {'zh': '衍生品总量：大合约当量 vs 原始张数', 'cols': [
            {'col': 'adv_deriv_total_lgeq_kcontracts', 'zh': '大合约当量 ADV',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_deriv_total_raw_kcontracts', 'zh': '原始张数 ADV',
             'unit': 'k contracts/day', 'fmt': 'f0'},
        ]},

        {'zh': '衍生品分类 ADV（大合约当量）', 'cols': [
            {'col': 'adv_deriv_fin_lgeq_kcontracts', 'zh': '金融衍生品合计',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_deriv_index_lgeq_kcontracts', 'zh': '株価指数関連等',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_deriv_rates_lgeq_kcontracts', 'zh': '国債・金利関連',
             'unit': 'k contracts/day', 'fmt': 'f1'},
            {'col': 'adv_deriv_cmdty_lgeq_kcontracts', 'zh': '商品関連',
             'unit': 'k contracts/day', 'fmt': 'f1'},
        ]},

        # 分类的原始张数单列一组：与上一组同名不同口径，混在一起读者会当成八个产品。
        {'zh': '衍生品分类 ADV（原始张数，仅供口径对照）', 'cols': [
            {'col': 'adv_deriv_index_raw_kcontracts', 'zh': '株価指数関連等（原始）',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_deriv_rates_raw_kcontracts', 'zh': '国債・金利関連（原始）',
             'unit': 'k contracts/day', 'fmt': 'f1'},
            {'col': 'adv_deriv_cmdty_raw_kcontracts', 'zh': '商品関連（原始）',
             'unit': 'k contracts/day', 'fmt': 'f1'},
        ]},

        # 名义金额：唯一完全不受合约乘数影响的量。但全仓只有 JPX 一家发布，
        # 做不了横截面（cme.csv / hkex.csv 都没有名义金额列），所以只放单页。
        {'zh': '衍生品名义金额（不受合约乘数影响）', 'cols': [
            {'col': 'adnv_deriv_total_jpytn', 'zh': '全品种日均名义额',
             'unit': '¥tn/day', 'fmt': 'f1'},
            {'col': 'adnv_n225_options_jpybn', 'zh': '日経225オプション日均权利金额',
             'unit': '¥bn/day', 'fmt': 'f0'},
        ]},

        {'zh': '东证现货成交', 'cols': [
            {'col': 'adt_cash_total_jpytn', 'zh': '合计 ADT',
             'unit': '¥tn/day', 'fmt': 'f1'},
            {'col': 'adt_cash_stocks_jpytn', 'zh': '股票（内国+外国）',
             'unit': '¥tn/day', 'fmt': 'f1'},
            {'col': 'adt_cash_etfreit_jpytn', 'zh': 'ETF / REIT',
             'unit': '¥tn/day', 'fmt': 'f2'},
            {'col': 'adv_cash_dom_shares_mn', 'zh': '内国株日均成交股数',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
        ]},

        {'zh': '东证市值与上市融资', 'cols': [
            {'col': 'mktcap_eom_jpytn', 'zh': '月末时价总额',
             'unit': '¥tn', 'fmt': 'f0c', 'stock': True},
            {'col': 'ipo_public_offerings', 'zh': '当月公开募集件数',
             'unit': 'offerings', 'fmt': 'f0'},
            {'col': 'ipo_funds_jpybn', 'zh': '当月募资额',
             'unit': '¥bn', 'fmt': 'f1'},
        ]},

        {'zh': '大阪主力合约 ADV（大合约当量 / 当量口径）', 'cols': [
            {'col': 'adv_n225_lgeq_kcontracts', 'zh': '日経225 复合体（当量）',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_topix_lgeq_kcontracts', 'zh': 'TOPIX 复合体（当量）',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_jgb10y_futures_kcontracts', 'zh': '10 年国債先物',
             'unit': 'k contracts/day', 'fmt': 'f1'},
            {'col': 'adv_n225_options_kcontracts', 'zh': '日経225オプション',
             'unit': 'k contracts/day', 'fmt': 'f1'},
            {'col': 'adv_secoptions_kcontracts', 'zh': '个股期权',
             'unit': 'k contracts/day', 'fmt': 'f1'},
        ]},

        # 迷你化的直接证据：大型合约的量在缩，mini 的量在涨，两条线自己会说话。
        {'zh': '迷你化：大型合约 vs mini（原始张数）', 'cols': [
            {'col': 'adv_n225_futures_kcontracts', 'zh': '日経225先物（大型）',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_n225_mini_kcontracts', 'zh': '日経225mini（1/10）',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_topix_futures_kcontracts', 'zh': 'TOPIX先物（大型）',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_minitopix_futures_kcontracts', 'zh': 'ミニTOPIX（1/10）',
             'unit': 'k contracts/day', 'fmt': 'f1'},
        ]},

        # 2023-05 才上线的两个产品自成一组 —— 与上面 139 个月的列不同起点。
        {'zh': '2023-05 上线的微型合约', 'cols': [
            {'col': 'adv_n225_micro_kcontracts', 'zh': '日経225マイクロ（1/100）ADV',
             'unit': 'k contracts/day', 'fmt': 'f0'},
            {'col': 'adv_n225_mini_options_kcontracts', 'zh': '日経225ミニオプション（1/10）ADV',
             'unit': 'k contracts/day', 'fmt': 'f1'},
            {'col': 'oi_n225_micro_contracts', 'zh': 'マイクロ月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '月末未平仓（OI）', 'cols': [
            {'col': 'oi_n225_futures_contracts', 'zh': '日経225先物',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_n225_mini_contracts', 'zh': '日経225mini',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_topix_futures_contracts', 'zh': 'TOPIX先物',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_n225_options_contracts', 'zh': '日経225オプション',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_jgb10y_futures_contracts', 'zh': '10 年国債先物',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},
    ],

    # 本页所有列同源于 JPX 每月那一批统计文件，没有慢腿。
    # 注意：慢的是 JPX **整家** —— 次月第 5 个营业日才出，横截面页里它恒定最慢
    # （2026-08-06 实测：cme / asx / tmx 已有 2026-07，JPX 仍是 2026-06）。
    # 那是横截面页要处理的事，不属于本页的 slow_cols。
    'slow_cols': [],

    # ── 图 A：成交额增长的量价分解 ────────────────────────────────────────
    # 恒等式 成交额 ≡ 成交股数 × 均价（均价 ≡ 成交额 ÷ 成交股数）是定义式。
    # 唯一能出错的地方是分子分母口径不一致，核查过程与结论全写在 _DECOMP_NOTE 里。
    # 横轴用 JPX 自己的**财年**（4 月—次年 3 月）而不是日历年：IR 的季度对账、
    # 公司的经营节奏都按这个口径，用日历年切会把同一份年报的数字劈成两根柱。
    'decomp': [
        {'zh': '东证内国株现货成交额',
         'kind': 'share_price',        # 派生量是「成交价」，不是每笔均值、也不是费率
         # adt_/adv_ 前缀的两列都是**当月日均**（月总额 ÷ 立会日数），不是当月合计。
         # 底座据此生成图注措辞，并要求必须给得出 weight_col 或 *_total_col ——
         # 日均跨月直接相加会给立会日数多的月份配错权重。
         'granularity': 'daily_avg',
         # 分子分母**逐段同口径**：两列同出 fetch/jpx.py 的 g['dom_*']，
         # 都只含内国株四段（プライム/スタンダード/グロース/TOKYO PRO），
         # 都是立会市場 + ToSTNeT、都是单边计。adt_cash_dom_stocks_jpytn 这一列
         # 就是为了这张图才加进 series/jpx.csv 的 —— 在它之前，本表里最接近的
         # adt_cash_stocks_jpytn 含外国株而股数列不含，那是「不可知偏差」，不是近似。
         'value': {'col': 'adt_cash_dom_stocks_jpytn', 'zh': '内国株成交额',
                   'unit': '¥tn/day', 'fmt': 'f1'},
         'qty': {'col': 'adv_cash_dom_shares_mn', 'zh': '内国株成交股数',
                 'unit': 'mn shares/day', 'fmt': 'f0c'},
         # 两侧都有官方自带的当月合计列，年度聚合直接用它们；同时给 weight_col，
         # 底座会拿「日均 × 立会日数」与合计列逐月对账（对不上硬失败）——
         # 这一步同时验证了两列共用同一套立会日数，也就验证了它们同口径。
         'value_total_col': 'val_cash_dom_stocks_jpytn',
         'qty_total_col': 'vol_cash_dom_shares_mn',
         'weight_col': 'trading_days',
         # 兆円 ÷ 百万株 = 1e6 円/株。纯单位换算，对增长率没有任何影响。
         'price_zh': '加权平均成交价', 'price_unit': '円/株',
         'price_fmt': 'f0c', 'price_scale': 1e6,
         'year_start_month': 4, 'years': 5,
         'note': _DECOMP_NOTE},
    ],

    # ── 图 B：量本身（水平值 + 12 个月滚动同比）────────────────────────────
    'ttm_yoy': [
        {'zh': '内国株成交股数',
         'granularity': 'daily_avg',   # adv_ 前缀 = 当月日均，不是当月合计
         'level': {'col': 'adv_cash_dom_shares_mn', 'zh': '日均成交股数',
                   'unit': 'mn shares/day', 'fmt': 'f0c'},
         'total_col': 'vol_cash_dom_shares_mn',
         'weight_col': 'trading_days',
         'note': _TTM_NOTE},
    ],

    'breaks': _breaks(),

    'notes': [
        '衍生品总量有两条并行序列。**大合约当量**（adv_deriv_*_lgeq_*）把 mini 按 1/10、'
        'マイクロ按 1/100 折算回大型合约；**原始张数**（adv_deriv_*_raw_*）是逐张相加。'
        '实测 2016-06 → 2026-06：原始张数 1572.1 → 2365.7 千张/日（+50.5%），'
        '大合约当量 706.3 → 522.6 千张/日（−26.0%）—— 同一个业务，两个口径符号相反。'
        '倍率同期由 2.23x 升到 4.53x。跨所比较、以及本页任何「JPX 衍生品在增长吗」的判断，'
        '一律以当量为准。',

        '**当量序列不是 JPX 发布的**。折算系数来自官方合约规格（JPX IR 脚注亦写明 '
        '"calculated using factors of 1/10 and 1/100"），逐月折算由 fetch/jpx.py 完成，'
        '并用 IR 的季度合计对账：Financial Derivatives IR 印 23 / 24 百万张、本表得 '
        '23.63 / 24.58；Commodity Derivatives IR 印 141 / 349 万张、本表得 141.48 / 349.41。'
        '白金那一档折算系数是 ÷5（标准合约 500g）而不是 ÷10，改折算表等于推翻这组对账。',

        '商品関連（adv_deriv_cmdty_*）在 2020-08 之前是 pro-forma：官方宽表把旧 TOCOM 的历史'
        '一路回填到 1985 年，而 JPX 2019-10 才完成对 TOCOM 的收购、品种 2020-07-27 才迁入 OSE。'
        '断点由 series/jpx.csv 的 cmdty_proforma 标记列推出，不是写死的月份。'
        '含商品的合计口径在该断点之前同样受影响。',

        '现货 ADT 与月末时价总额的统计范围不同：ADT 含内国株 + 外国株 + ETF + REIT'
        '（2026-06 实测 ETF/REIT 占 0.719 / 14.084 = 5.1%），时价总额只含上市股票'
        '（プライム / スタンダード / グロース / TOKYO PRO）。'
        '两者相除得到的换手率会系统性高估，本页不提供该派生指标。',

        '本页全部金额为日元。跨币种比较由 build/notional.py 统一换算：'
        '流量（ADT、日均名义额、募资额）配月均汇率，存量（月末时价总额、月末 OI）配月末汇率。',

        '不单独画成曲线的月频列：deriv_trading_days、val_cash_total_jpytn、'
        'adt_cash_stocks_jpytn 的内国株分项在图上与合计几乎重合，cmdty_proforma 是 0/1 '
        '标记列（只用来推断点）。其中 <b>trading_days / vol_cash_dom_shares_mn / '
        'val_cash_dom_stocks_jpytn 三列虽然不画线，但在末尾两张派生图里承担计算</b>：'
        '年度量价分解与 12 个月滚动同比都要先把「日均」还原成「当月合计」，'
        '否则各月立会日数不同会给年度均价配错权重。',

        'series/jpx_investors.csv（投資部門別売買動向，2023-12 起周频、'
        '实测 136 周至 2026-07-31）本版不上页面：它是周频序列，'
        '而本页契约的 groups 只吃 series/jpx.csv 的月频列。要做应另起一页，'
        '不在这一页里为 JPX 单开分支。',
    ],
}
