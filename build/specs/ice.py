# -*- coding: utf-8 -*-
"""ICE（Intercontinental Exchange，NYSE: ICE）单公司页配置。

一行一条注册、删掉不留残渣：本文件是 ICE 在看板里的**全部**足迹，
除了 series/ice.csv 与导航注册表之外，没有任何一处写着 "ice"。

口径以 docs/verify/verify_ice.md（复核稿，判定 A）为准，与 docs/verify/ice.md
（侦察稿）冲突时一律听复核稿 —— 侦察稿的 §5「Cloudflare 403」「adv_fx_credit 含信用」
两条已被复核实测证伪。

列名全部对着 `head -1 series/ice.csv` 逐字核过（55 列，187 个月，2011-01..2026-07，
CDS 三列 2013-01 起，其余 52 列零空洞）。

━━ 📌 本页做不了量价分解，而且「收入分解」也不是它的替身 ━━━━━━━━━━━━━━━━
量价分解的恒等式是 `成交额 ≡ 成交量 × 成交价`。本表**一条成交金额列都没有** ——
`adv_*_kcontracts` 是张数、`oi_*` 是未平仓张数、`adv_nyse_tape*_mnsh` 是股数，
唯一带货币单位的是 `rpc_*_usd` 与 `cds_*_notional_usdbn`。

⚠ **`rpc_*_usd` 是每张收入（费率），不是成交价。**这是本页最容易犯的一个错：
它长得像「价」（美元 / 张），语义却完全不同 —— 成交价是市场撮合出来的价格，
每张收入是 ICE 向会员收的费。拿它当 `decomp` 的派生量，底座会印出
「成交量加权平均成交价」那一整套措辞，句句是假的。

ICE 确实有另一条恒等式 `交易收入 ≡ 成交量 × 每张费率`，底座也确实为它准备了
`kind='revenue_rate'`（图注会写明「分解的是**收入**不是成交额；与前两类不可并读」）。
**但本页仍然不画**，原因是缺列不是缺口径：`decomp.value` 要的是一条**真实存在的
金额列**，而本表没有收入列。用 `ADV × 交易日 × RPC` 现造一条，等于把算术写进 spec ——
契约第一句就是「配置里只有数据，没有逻辑」，而且那样造出来的「收入」既不是 ICE 的
分部收入口径（不含数据 / 上市 / 固定收益等非交易收入），也没有任何官方数字能对账。
⇒ 📌 **不具备数据条件，不凑。**RPC 本身照常上页面（「单位经济」那一组），
它作为费率序列是有信息的，只是不能进分解图。

`cds_*_notional_usdbn` 是清算名义额，配得上的数量列同样没有（没有 CDS 笔数 / 张数列）。
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'ice.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：在 import 期从 series/ice.csv 的表头现数。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
def _column_census():
    """数「金额列 / 数量列 / 费率列」各几条 —— 「做不了分解」的机器判据。

    返回 (成交金额列数, 数量列数, 费率列数, 清算名义额列数)；读不到返回 (None,)*4。
    """
    try:
        with open(_CSV, encoding='utf-8') as fh:
            cols = next(csv.reader(fh))
    except (OSError, StopIteration):
        return (None,) * 4
    rate = [c for c in cols if c.startswith('rpc_')]
    notional = [c for c in cols if 'notional' in c]
    qty = [c for c in cols if c.endswith('_kcontracts') or c.endswith('_mnsh')]
    # 「成交金额」= 带货币单位、且不是费率、不是清算名义额的列。本表应当是 0 条。
    money = [c for c in cols
             if (c.endswith('_usd') or c.endswith('_usdbn') or 'usd' in c)
             and c not in rate and c not in notional]
    return len(money), len(qty), len(rate), len(notional)


def _split_vs_total():
    """商品合计 + 金融合计 与「衍生品总 ADV」的相对差 —— 「两套交易日」的直接证据。

    官方分项与合计用不同的交易日归一，所以这两个数本来就不该逐格相等。
    量出来才敢在图注里说「没有哪一套交易日能单独代表总 ADV」。

    返回 (可比月数, 最大相对差%, 中位相对差%)；算不出返回 (None, None, None)。
    """
    rel = []
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                try:
                    c = float(r['adv_commodities_kcontracts'])
                    f = float(r['adv_financials_kcontracts'])
                    t = float(r['adv_futures_options_kcontracts'])
                except (KeyError, ValueError, TypeError):
                    continue
                if t:
                    rel.append(abs((c + f) / t - 1.0) * 100.0)
    except OSError:
        return (None,) * 3
    if not rel:
        return (None,) * 3
    rel.sort()
    return len(rel), rel[-1], rel[len(rel) // 2]


_NMONEY, _NQTY, _NRATE, _NNOT = _column_census()
_SPLITN, _SPLITMAX, _SPLITMED = _split_vs_total()

_NO_DECOMP_NOTE = (
    '📌 <b>本页不具备量价分解的数据条件。</b>量价分解的恒等式是「成交额 ≡ 成交量 × '
    '成交价」，而本表<b>一条成交金额列都没有</b>：'
    + ((f'数量类列 <b>{_NQTY}</b> 条（合约张数与股数），费率类 <code>rpc_*</code> '
        f'<b>{_NRATE}</b> 条，清算名义额 <b>{_NNOT}</b> 条，'
        f'真正的成交金额列 <b>{_NMONEY}</b> 条。'
        if _NQTY is not None else
        '数量类列有几十条，货币单位的只有 rpc_* 与 CDS 清算名义额。'))
    + '<b>⚠️ <code>rpc_*_usd</code> 是每张收入（费率），不是成交价</b> —— '
      '这是本页最容易犯的一个错：它长得像「价」（美元/张），语义却完全不同。'
      '成交价是市场撮合出来的价格，每张收入是 ICE 向会员收的费。'
      '拿它当分解的派生量，图注会印出「成交量加权平均成交价」那一整套措辞，句句是假的。'

      '<b>ICE 确实另有一条恒等式：交易收入 ≡ 成交量 × 每张费率。</b>'
      '那是<b>收入分解</b>，与成交额分解不是一回事，两者的读数<b>不可并读</b>。'
      '本页仍然不画它，原因同样是缺列：分解图要的是一条<b>真实存在的金额列</b>，'
      '而本表没有收入列。用「ADV × 交易日 × RPC」现造一条，'
      '既把算术写进了配置（契约只允许配置放数据、不放逻辑），'
      '造出来的「收入」也不是 ICE 任何一个官方口径（不含数据 / 上市 / 固定收益等'
      '非交易收入），没有任何官方数字能对账。<b>不具备数据条件，不凑。</b>'
      'RPC 本身照常上页面（见「单位经济」那一组），它作为费率序列有信息，'
      '只是不能进分解图。'
)

_NOTE_TTM_FO = (
    '<b>⚠️ 本图没有交易日权重列可用，这是有意的选择而不是疏漏。</b>'
    '<code>series/ice.csv</code> 里有两套交易日（<code>trading_days_commod</code> 与 '
    '<code>trading_days_rates</code>），而「衍生品总 ADV」横跨商品与金融两侧，'
    '没有哪一套能单独代表它 —— 官方自己也是分项与合计用不同的交易日归一。'
    + ((f'这件事在本表里量得出来：商品合计 + 金融合计与「衍生品总 ADV」的相对差'
        f'<b>中位 {_SPLITMED:.3f}%、最大 {_SPLITMAX:.3f}%</b>（{_SPLITN} 个月）——'
        f'两套交易日不同，分项与合计本来就不该逐格相等。'
        if _SPLITMAX is not None else
        '分项之和与合计因此有一个系统性差。'))
    + '硬挑一套乘回去，会给一半的量配错权重，而图上完全看不出来。'
    '⇒ 这里让底座按<b>等权</b>相加，并在上面那段话里把这个偏差说出来。'
    '<b>滚动同比对这件事天然更耐受</b>：任意连续 12 个月覆盖同一套日历，'
    '而单月同比里那截「今年这个月比去年多开几天市」的差是消不掉的。'
)

_NOTE_TTM_CASH = (
    '<b>这一张有正确的交易日列可用</b>（<code>trading_days_us_equities</code>，'
    '就是官方拿来算这条 ADV 的那一列除数），所以线的滚动合计是把日均精确还原成'
    '当月合计之后再滚 12 个月，柱与线口径不同是有意的：'
    '柱回答「开市那天有多热」，线回答「一整年的总量在不在长」。'
    '⚠️ handled ≠ matched：handled 含 ICE 为客户路由到别家撮合的量，'
    'matched 才是本所自己撮合的。市场份额只能用 matched 算'
    '（见「NYSE 美股现货：本所量 vs 全市场分母」那一组）。'
)

# ── 为什么 fmt 这么选 ───────────────────────────────────────────────────────
# 1) 月度单元格在官方原表里就已经四舍五入到整千张 / 整百万股（10,026 格里只有
#    2,429 个非整数，且全部落在 RPC 与份额这 13 列上，verify_ice §1.2）。
#    给月度 ADV 标小数位是假精度 ⇒ 计数类一律 f0c（千分位整数，charts.js:91）。
# 2) share_* 五列在 CSV 里是**分数**（0.191 = 19.1%），不是百分数。
#    charts.js 的 pct1 实现是 `v.toFixed(1) + '%'`（charts.js:94），**不做 ×100**，
#    直接配 pct1 会把 19.1% 印成「0.2%」—— 图照画、没人报错。
#    所以这五列一律 `'scale': 100` + pct1。本机用算术验过是分数而不是百分数：
#    share ÷ (matched ÷ consolidated) 的中位比值 = 1.000（若是百分数会是 100）。
#    对照：series/miax.csv 的 share_*_pct 存的是百分数（比值 99.9），那边不加 scale。
# 3) RPC 官方给 2 位小数，现货 RPC 给到 $0.032~$0.055 ⇒ 前者 usd2、后者 usd3。

SPEC = {
    'ticker': 'ice',
    'name':   'Intercontinental Exchange',
    'title':  '洲际交易所（ICE）月度经营指标',
    'csv':    'ice.csv',
    'ccy':    'USD',
    'source': 'Source: ICE Monthly Statistics Tracking spreadsheet (ir.theice.com ContentAsset feed, '
              'file hosted on s2.q4cdn.com); format after Goldman Sachs GIR',

    # 头条：TOTAL F&O ADV 与 NYSE 现货 handled ADV。
    # 两条都在同一个 xlsx 里、同一天发布、187 个月零空洞 —— 满足「历史长 / 发布快 / 无空洞」。
    # 不用 adv_energy 之类分项当头条：分项与合计用不同的交易日归一，
    # 分项之和与合计有 0~0.55% 的系统性差（verify_ice §四.4），当门槛会引入无意义的抖动。
    'headline': [
        {'col': 'adv_futures_options_kcontracts', 'zh': '衍生品总 ADV',
         'unit': 'k contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_nyse_us_cash_handled_mnsh',  'zh': 'NYSE 美股现货 ADV（handled）',
         'unit': 'mn shares/day', 'fmt': 'f0c'},
    ],

    'groups': [
        # ── 能源：ICE 的利润中心。六个子项 + TOTAL，六项之和 = TOTAL 只在 85/187 个月
        #    精确成立（各自四舍五入到整千张），±2 内 187/187 —— 不要当恒等式校验。
        {'zh': '能源衍生品 ADV', 'cols': [
            {'col': 'adv_energy_kcontracts',         'zh': '能源合计',   'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_brent_kcontracts',          'zh': 'Brent 原油', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_gasoil_kcontracts',         'zh': 'Gasoil 柴油', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_otheroil_kcontracts',       'zh': '其他原油与成品油', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_natgas_kcontracts',         'zh': '天然气（含 TTF）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_power_kcontracts',          'zh': '电力',       'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_environmentals_kcontracts', 'zh': '环境权益与其他', 'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '农产品与金属 ADV', 'cols': [
            {'col': 'adv_ag_metals_kcontracts',       'zh': '农产品与金属合计', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_sugar_kcontracts',           'zh': '糖',       'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_otherags_metals_kcontracts', 'zh': '其他农产品与金属', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_commodities_kcontracts',     'zh': '大宗商品合计（能源+农金）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        # ── 金融：ICE 的利率腿是**欧洲曲线**（Euribor / SONIA / Gilts），
        #    与 CME 的美国曲线互补不竞争，横截面上只能画增速不能画绝对量。
        #    单股一列官方明说已从 TOTAL FINANCIALS 剔除，放在这里只作单独观察。
        {'zh': '金融衍生品 ADV', 'cols': [
            {'col': 'adv_financials_kcontracts',   'zh': '金融合计（不含单股）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_stir_kcontracts',         'zh': '短期利率', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_mltir_kcontracts',        'zh': '中长期利率', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_equity_index_kcontracts', 'zh': '股指',     'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_fx_credit_kcontracts',    'zh': 'FX 与 USDX', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_single_stock_kcontracts', 'zh': '单股（已剔出合计）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_futures_options_kcontracts', 'zh': '期货与期权总计', 'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        # ── OI：月末净未平仓，是**存量**（stock=True）。
        #    单位是千张 —— 与 cme.csv 的 oi_*_contracts（裸张）差 1000 倍，
        #    这是横截面上最容易翻车的一处（verify_ice §五.4）。
        #    官方没有 TOTAL OI 行，新闻稿里的 "Total OI" 是 commodities + financials 自己加的。
        {'zh': '未平仓合约（月末净 OI）', 'cols': [
            {'col': 'oi_commodities_kcontracts',       'zh': '大宗商品', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_energy_kcontracts',            'zh': '能源',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_ag_metals_kcontracts',         'zh': '农产品与金属', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_financials_kcontracts',        'zh': '金融',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_rates_kcontracts',             'zh': '利率',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_other_financials_kcontracts',  'zh': '股指与 FX', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # ── RPC：滚动三月均，美元/张。与 Cboe 的 RPC 不同，ICE **不滞后**
        #    （2026-07 期 rpc_energy 已填），所以不进 slow_cols。
        #    但正因如此，任何 ICE vs Cboe 的 RPC 并排图，ICE 那条每月都会多伸出一格。
        {'zh': '单位经济：每张收入（RPC，滚动三月均）', 'cols': [
            {'col': 'rpc_commodities_usd',       'zh': '大宗商品', 'unit': 'USD/contract', 'fmt': 'usd2'},
            {'col': 'rpc_energy_usd',            'zh': '能源',     'unit': 'USD/contract', 'fmt': 'usd2'},
            {'col': 'rpc_ag_metals_usd',         'zh': '农产品与金属', 'unit': 'USD/contract', 'fmt': 'usd2'},
            {'col': 'rpc_financials_usd',        'zh': '金融',     'unit': 'USD/contract', 'fmt': 'usd2'},
            {'col': 'rpc_rates_usd',             'zh': '利率',     'unit': 'USD/contract', 'fmt': 'usd2'},
            {'col': 'rpc_other_financials_usd',  'zh': '股指与 FX', 'unit': 'USD/contract', 'fmt': 'usd2'},
        ]},

        # ── 美股期权：adv_us_equity_options_industry_kcontracts 是**全行业分母**，
        #    全仓最值钱的几列之一 —— 有了它，NYSE 与 Cboe multilist、MIAX 才能同分母算份额。
        {'zh': 'NYSE 美股期权（Arca + American）', 'cols': [
            {'col': 'adv_us_equity_options_industry_kcontracts', 'zh': '全美股票/ETF 期权行业总量',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_equity_options_kcontracts', 'zh': 'NYSE 两所合计',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_equity_options', 'zh': 'NYSE 份额（官方直接给）',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'rpc_nyse_equity_options_usd', 'zh': 'NYSE 期权 RPC',
             'unit': 'USD/contract', 'fmt': 'usd2'},
        ]},

        # ── 美股现货：本页最重要的一组。
        #    adv_tape{A,B,C}_consolidated_mnsh 是**全市场**合并成交量（不是 NYSE 自己的），
        #    是「场外化侵蚀」这条趋势唯一可跟踪的证据。本机实测 2026-06
        #    （四家份额都有值的最新一个月；2026-07 Nasdaq 在慢腿里还没到）：
        #      三 tape 合并 23,382 百万股/日
        #      NYSE matched 4,681 = 20.02%   Cboe 2,185 = 9.35%
        #      Nasdaq 三盘口 14.77%          MIAX Pearl 192 = 0.82%
        #      ⇒ 四家合计 44.96%，其余 55.04% 成交在暗池 / 内化商 / TRF。
        #    这个分母只有 ICE 披露。
        {'zh': 'NYSE 美股现货：本所量 vs 全市场分母', 'cols': [
            {'col': 'adv_nyse_us_cash_handled_mnsh', 'zh': 'NYSE Group handled ADV',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_us_cash_matched', 'zh': 'NYSE 全美 matched 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'rpc_nyse_us_cash_usd_per100sh', 'zh': '现货 RPC（每 100 股）',
             'unit': 'USD/100 shares', 'fmt': 'usd3'},
            {'col': 'adv_tapeA_consolidated_mnsh', 'zh': 'Tape A 全市场',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeA_matched_mnsh', 'zh': 'Tape A · NYSE matched',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeA_handled_mnsh', 'zh': 'Tape A · NYSE handled',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_tapeA_matched', 'zh': 'Tape A 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'adv_tapeB_consolidated_mnsh', 'zh': 'Tape B 全市场',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeB_matched_mnsh', 'zh': 'Tape B · NYSE matched',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeB_handled_mnsh', 'zh': 'Tape B · NYSE handled',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_tapeB_matched', 'zh': 'Tape B 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'adv_tapeC_consolidated_mnsh', 'zh': 'Tape C 全市场',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeC_matched_mnsh', 'zh': 'Tape C · NYSE matched',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeC_handled_mnsh', 'zh': 'Tape C · NYSE handled',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_tapeC_matched', 'zh': 'Tape C 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
        ]},

        # ── CDS：ICE Clear Credit 当月清算名义总额，**当月总量不是日均**（表标题里没有 daily 字样）。
        #    2013-01 起，比其余列晚两年，但它每月与主表同时发布，所以不是慢腿。
        {'zh': 'CDS 清算名义额（ICE Clear Credit，当月总量）', 'cols': [
            {'col': 'cds_total_notional_usdbn',     'zh': '合计',   'unit': 'USD bn/month', 'fmt': 'f0c'},
            {'col': 'cds_client_notional_usdbn',    'zh': '客户盘', 'unit': 'USD bn/month', 'fmt': 'f0c'},
            {'col': 'cds_nonclient_notional_usdbn', 'zh': '非客户盘', 'unit': 'USD bn/month', 'fmt': 'f0c'},
        ]},
    ],

    # ICE 全表 55 列同一个 xlsx、同一天发布，没有任何一列比头条晚 ——
    # RPC 不滞后（这是与 Cboe 的关键差别），CDS 也不滞后。所以慢腿为空。
    'slow_cols': [],

    # 唯一一处会改变序列含义的口径断点。
    # ICE 2013-11 才完成 NYSE Euronext 收购，但原表 row 79 明写
    # "For comparison purposes, we include NYSE ADV, RPC and OI in all periods covered"
    # ⇒ 2011-01 ~ 2013-10 的 NYSE 现货与期权是**追溯并入的形式数**，
    #    那 34 个月讲的是被收购前 NYSE Euronext 的份额，不是 ICE 的。
    'breaks': [
        {'month': '2013-11', 'zh': 'NYSE Euronext 收购完成；此前 NYSE 各列为追溯并入的形式数'},
    ],

    # 📌 'decomp' 刻意留空：本表没有任何一条成交金额列，rpc_* 是费率不是价。
    # 完整理由与机器判据见 _NO_DECOMP_NOTE（它进了下面 notes 的第一条）。

    # ══ 水平值 + 12 个月滚动同比 ═════════════════════════════════════════════
    # 两条头条各一张。两条 level 列在 groups 里都落在多列同轴的图里
    # （能源/金融 ADV 那几组、以及 tape 那一大组），不是单桶 gs_bar ⇒ 不与任何图重复。
    'ttm_yoy': [
        {'zh': 'ICE 衍生品成交量',
         'granularity': 'daily_avg',      # 官方原表发的就是 ADV
         'level': {'col': 'adv_futures_options_kcontracts', 'zh': '衍生品总 ADV',
                   'unit': 'k contracts/day', 'fmt': 'f0c'},
         # ⚠ 刻意**不给** weight_col：本表有 trading_days_commod 与 trading_days_rates
         #   两套交易日，而总 ADV 横跨商品与金融两侧，没有哪一套能单独代表它。
         #   硬挑一套会给一半的量配错权重，而图上完全看不出来。
         #   底座会因此在图注里印一段 ⚠️ 等权相加的说明 —— 那句话是真的，别去掩盖。
         'note': _NOTE_TTM_FO},

        {'zh': 'NYSE 美股现货成交股数',
         'granularity': 'daily_avg',
         'level': {'col': 'adv_nyse_us_cash_handled_mnsh', 'zh': 'NYSE handled ADV',
                   'unit': 'mn shares/day', 'fmt': 'f0c'},
         # 这一条有唯一正确的交易日列：美股现货只有一套日历。
         'weight_col': 'trading_days_us_equities',
         'note': _NOTE_TTM_CASH},
    ],

    'notes': [
        _NO_DECOMP_NOTE,

        '数据源：ICE 官网 IR 的 Monthly Statistics Tracking 单一 xlsx（4 个 sheet，2011-01 起 187 个月），'
        '指针由 ir.theice.com 的 ContentAsset JSON feed 给出。全部 55 列取自同一文件、同一发布日。',

        '<b>衍生品 ADV 单位是千张（官方原表 "contracts in 000s"）；OI 单位同样是千张</b> —— '
        '与 series/cme.csv 的 oi_*_contracts（裸张数）差 1000 倍。跨家对比时必须先统一。',

        '<b>月度值在官方原表里就已四舍五入到整千张 / 整百万股</b>，只有 RPC 与份额这 13 列是非整数。'
        '所以本页所有计数类一律按 0 位小数显示；小基数行（环境权益、FX/USDX）的同比会与官方新闻稿差 1–2pp，'
        '这是官方自己的取整造成的，不是解析错误。',

        '<b>分项之和 ≠ 合计，不要当恒等式。</b>TOTAL ENERGY = 六子项之和只在 85/187 个月精确成立（±2 内 187/187）；'
        'TOTAL FINANCIALS = 四子项之和只在 109/187 个月精确成立。'
        '另外 adv_commodities + adv_financials 与 adv_futures_options 有 0~0.55% 的系统性差 —— '
        '合计用「总量÷总交易日」归一，而商品与利率两条交易日在 187 个月里有 118 个月不相等。',

        '<b>官方没有 TOTAL OI 行。</b>新闻稿里的 "Total OI" 是 oi_commodities + oi_financials 自己加出来的'
        '（已用 2026-06 / 2026-07 两期新闻稿反算验证）。OI 是月末净未平仓（net OI）。',

        '<b>RPC 是滚动三月均，不能与单月量相乘当单月收入。</b>官方定义（表内脚注 1）= 交易收入 ÷ 合约量。'
        '与 Cboe 不同，ICE 的 RPC 不滞后一个月，所以任何 ICE vs Cboe 的 RPC 并排图，'
        'ICE 那条线每个月都会比 Cboe 多伸出一格，需要在绘图层截齐。',

        '<b>share_* 五列在官方原表里是 0–1 的小数比率</b>（0.191 = 19.1%），'
        '本页统一乘 100 按百分数显示。这一点用算术核过而不是照抄文档：'
        'share ÷（matched ÷ consolidated）的中位比值 = 1.000（若源表存的是百分数，该比值会是 100）。'
        '注意 series/miax.csv 的 share_*_pct 存的是百分数，两家形态相反，跨页取数时别弄混。',

        '<b>adv_tapeA/B/C_consolidated_mnsh 是全美合并成交量，不是 NYSE 自己的量</b> —— '
        '这是本仓唯一一个由交易所自己披露、且回溯到 2011-01 的现货行业分母。'
        '本机实测 2026-06（四家份额都有值的最新一个月）：三个 tape 合并 23,382 百万股/日，'
        'NYSE matched 4,681（20.0%）、Cboe 2,185（9.4%）、Nasdaq 三盘口 14.8%、MIAX Pearl 192（0.8%），'
        '<b>四家合计 44.96%，其余 55.04% 成交在暗池 / 内化商 / TRF</b>。'
        '「场外化侵蚀」这条趋势只能靠这几列跟踪。',

        '<b>ICE 的三 tape 合并量与 MIAX 自己披露的行业 ADV 是两家独立申报、数值几乎逐位相同的两条线</b>：'
        '实测 2026-06 = 23,382 vs 23,383、2026-07 = 17,437 vs 17,437。'
        '这既是两边解析正确性的交叉证据，也意味着横截面页上这两列是同一个分母，不要当成两个口径并列。',

        '<b>matched ≠ handled。</b>handled 含路由到别的交易所成交的量，跨家份额一律用 matched。'
        '官方没有 A+B+C matched 的合计行，只给了 share_nyse_us_cash_matched（与自算一致，误差 <0.15pp）。',

        '<b>adv_us_equity_options_industry_kcontracts 是全美股票/ETF 期权行业总量，'
        '经与 Cboe multilist 及 ICE 10-K 交叉验证与「不含指数期权」的口径一致</b> —— '
        '但工作簿里这一行没有任何脚注，ICE 从未书面定义过，不要在页面上写成官方定义。',

        '<b>adv_fx_credit_kcontracts 的行标签写着 "TOTAL FX & CREDIT"，但口径是 FX + 美元指数，不含信用。</b>'
        '依据：表内脚注 (12) 原文只提 U.S. Dollar Index 与 foreign exchange；'
        '2015-2021 官方合约级明细文件里对应行 Total FX & Other 与本列 2019-06 精确相符（38,947 张 = 39 千张）。',

        '<b>adv_single_stock_kcontracts 已被官方从 TOTAL FINANCIALS 剔除</b>'
        '（理由是收入封顶、与量无相关性），只能单独看，不要并入任何合计或竞争池。',

        '2011-01 起的历史里还有三处官方追溯重刷，已体现在当前文件中（本仓一次性全量摄入，不受影响）：'
        'NGX 的量与收入追溯并入 2011 年起的 Other Oil / 天然气 / 电力 / 能源与商品合计；'
        '2013 年起的电力 ADV、能源 RPC、能源 OI 按新的电力量折算法重算；'
        'Russell 合约 2016-12 规格减半后量、OI、RPC 全部追溯调整。'
        '<b>后果是本仓 CSV 与 ICE 历年季报 / 10-K 原文里的数字可能对不上</b> —— 以当前文件为准。',

        'CDS 三列自 2013-01 起（比其余列晚两年），是当月清算名义总额（单边计），不是日均。'
        '历史上出过一次实质重述：2026-06 那期的 2026-01 Non-Client = 291（不平 99），'
        '2026-07 那期改成 391 —— 这是跨 vintage 唯一一处实质改动。',

        '交易日有两列（trading_days_commod / trading_days_rates，187 个月里只有 69 个月相同），'
        '本页所有序列已是官方算好的 ADV，因此不单独出图；两列的差异是上面「分项之和 ≠ 合计」的成因之一。',
    ],
}
