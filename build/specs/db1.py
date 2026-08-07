# -*- coding: utf-8 -*-
"""Deutsche Börse Group（db1）单公司页配置。

本文件只声明「画哪些列、叫什么、什么单位、什么格式」，**不含任何算术、不含任何取数**。
数值在通用底座里算完再进 payload，页面只画不算。

━━ 为什么这家的 slow_cols 特别长 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB1 一家缝了**三个官方源、两种发布节奏**（fetch/db1.py 模块 docstring「发布节奏」节，
全量实测 223 期 Eurex + 20 期 FWB）：

  快腿 Eurex 工作簿   月末后第 2–6 天（2016-01 以来 127 期全部落在这个带宽内）
  快腿 FWB 现货工作簿 月末后第 1–4 天（20 期里 18 期）
  慢腿 集团 IR 台账   月末后约第 10 天（落地页原文 "available as of the second week
                      after the reporting month"）

所以每个月都有一段时间：Eurex / Xetra 列已经有最新月，而 Clearstream / EurexOTC /
360T / EEX / 台账口径成交量这些列**天生是空的**。这不是解析失败，也不是数据缺失。
本机实测（series/db1.csv，2026-08-06）：快腿列最新月 2026-07，慢腿列最新月 2026-06，
正好差一个月 —— 如果把慢腿列放进门槛判定，整页会被拖住一整个月。

⇒ `slow_cols` 不手抄。fetch/db1.py 的 docstring 口径坑 12 明写「模块常量
   `FAST_LEG_COLUMNS` / `SLOW_LEG_COLUMNS` 就是给下游做这个排除用的，别再手抄一份清单」。
   本文件照办：能 import 到就从那个常量派生，import 不到才退回本文件里的字面量兜底
   （兜底是为了「删掉本文件不留残渣」这条约束 —— spec 不该硬依赖 fetch/ 才能被读）。

━━ 口径断点 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`series/db1_breaks.csv` **不存在**（enx 有、db1 没有 —— 官方 xlsx 没有可机器抽取的
脚注台账）。已知的列级口径变化（360T 自 2018-07 含 GTX 等）只影响单列，
画在全页的红色竖线会误伤其余四十多列，所以 `breaks` 留空，逐条写进 `notes`。

━━ 单位与「存量 / 流量」━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`stock: True` 的列在跨币种换算时配月末汇率，缺省配月均汇率。本页是 EUR 本币页，
换算不在这里发生（notional.py 的事），但标注必须先对 —— 见 notes 里 AuC 那条**冲突声明**。
"""

import os

# ── 慢腿列：优先从 fetch/db1.py 的权威常量派生 ─────────────────────────────
# 兜底清单只在 fetch/db1.py 读不到时使用。两者本机实测完全一致（20 列），
# 不一致时以 fetch 侧为准 —— 那边是跟着抓取代码一起改的，这边是配置。
_SLOW_FALLBACK = frozenset([
    'adv_360t_fx_eurbn', 'auc_fund_services_eurbn', 'auc_securities_services_eurbn',
    'aum_stoxx_dax_etf_eurbn', 'cash_balances_eurmn', 'gsf_collateral_eurbn',
    'otc_notional_cleared_eurbn', 'otc_notional_outstanding_eurbn',
    'settle_icsd_txn_mn', 'settle_ifs_txn_mn', 'trading_days_cash',
    'turnover_cash_total_eurbn', 'vol_fd_equity_contracts', 'vol_fd_index_contracts',
    'vol_fd_rates_contracts', 'vol_fd_total_contracts', 'vol_gas_mwh',
    'vol_licensed_index_contracts', 'vol_power_deriv_mwh', 'vol_power_spot_mwh',
])


def _slow_universe():
    """返回「哪些列属于慢腿」的全集。读得到 fetch/db1.py 就用它的常量。

    用 spec_from_file_location 而不是 import fetch.db1 —— 本仓没有 __init__.py，
    monthly_run.py 自己也是这么加载模块的（monthly_run.py:151）。
    任何失败都静默退回兜底清单：spec 被读的时候不该因为 fetch/ 缺席而炸。
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'fetch', 'db1.py')
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('_db1_fetch_for_spec', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cols = frozenset(mod.SLOW_LEG_COLUMNS)
        return cols if cols else _SLOW_FALLBACK
    except Exception:
        return _SLOW_FALLBACK


# ── 头条 ───────────────────────────────────────────────────────────────────
# Eurex 全所日均成交合约数：2008-01 起 223 个月零空洞、快腿（月末后第 2–6 天）、
# 官方工作簿自己就发 Daily average（不是本仓算的）。三条都满足「历史长 / 发布快 / 无空洞」。
# 不用 Xetra 现货做头条：turnover_xetra_eurbn 只有 2024-01 起 31 个月，历史太短。
HEADLINE = [
    {'col': 'adv_eurex_total_contracts', 'zh': 'Eurex 衍生品 ADV',
     'unit': 'contracts/day', 'fmt': 'f0c'},
]

# ── 分组 ───────────────────────────────────────────────────────────────────
# 每组一个 exhibit 群。列名全部 head -1 series/db1.csv 核过。
# 刻意排除 turnover_xetra_structured_eurbn：它 2025-10→2026-07 之间只有 5 个值、
# 中间 5 个月是空的（本机实测 gaps=5）。平滑类图型遇到 null 会把它当 0 画出塌到零的假线，
# gs_line 还会 null.toFixed() 抛 TypeError 让该卡片之后的 exhibit 全不渲染。
GROUPS = [
    # 头条那一列在这里再出现一次是**故意的**：头条的契约职责是「定共同最新月与门槛」，
    # 它会不会同时被画成图由底座决定。列在组里 ⇒ 底座只画组时不会丢掉旗舰序列；
    # 若底座也画头条，去重是底座一行的事。反过来（漏掉旗舰图）修起来贵得多。
    # enx.py 同理，两份 spec 保持同一个约定。
    {'zh': 'Eurex 衍生品 ADV（按官方大组）', 'cols': [
        {'col': 'adv_eurex_total_contracts', 'zh': '全所合计',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_rates_contracts', 'zh': '利率衍生品',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_index_contracts', 'zh': '股指衍生品（不含股息）',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_equity_contracts', 'zh': '单股衍生品（不含股息）',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_dividend_contracts', 'zh': '股息衍生品',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ]},

    # OI 全部是月末时点值 ⇒ stock。Eurex 的 OI 会被官方事后重述
    # （fetch/db1.py 口径坑 3：222 对里 17 对不等，最大 2.48%），所以这条线的历史段
    # 与当年印出来的数字可能对不上，不是本页算错。
    {'zh': 'Eurex 未平仓合约（月末）', 'cols': [
        {'col': 'oi_eurex_total_contracts', 'zh': '全所合计',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_rates_contracts', 'zh': '利率',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_index_contracts', 'zh': '股指',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_equity_contracts', 'zh': '单股',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_dividend_contracts', 'zh': '股息',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # 德债三剑客 = Eurex 的利率支柱。产品代码 FGBL / FGBM / FGBS。
    {'zh': '德债期货三剑客（Bund / Bobl / Schatz）', 'cols': [
        {'col': 'adv_bund_contracts', 'zh': 'Bund（FGBL，10 年）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_bund_contracts', 'zh': 'Bund 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_bobl_contracts', 'zh': 'Bobl（FGBM，5 年）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_bobl_contracts', 'zh': 'Bobl 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_schatz_contracts', 'zh': 'Schatz（FGBS，2 年）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_schatz_contracts', 'zh': 'Schatz 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # BTP（意大利）2009-09 起、OAT（法国）2012-04 起 —— 比德债三剑客晚，
    # 前段天然留空，是官方就没有，不是解析失败。
    {'zh': '外围主权债与短端利率（BTP / OAT / EURIBOR）', 'cols': [
        {'col': 'adv_btp_contracts', 'zh': 'BTP（FBTP，意大利）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_btp_contracts', 'zh': 'BTP 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_oat_contracts', 'zh': 'OAT（FOAT，法国）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_oat_contracts', 'zh': 'OAT 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_euribor3m_contracts', 'zh': '3 个月 EURIBOR（FEU3）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_euribor3m_contracts', 'zh': '3 个月 EURIBOR 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'EURO STOXX 50 期货与期权（FESX / OESX）', 'cols': [
        {'col': 'adv_estoxx50_fut_contracts', 'zh': 'EURO STOXX 50 期货 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_estoxx50_fut_contracts', 'zh': 'EURO STOXX 50 期货未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_estoxx50_opt_contracts', 'zh': 'EURO STOXX 50 期权 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_estoxx50_opt_contracts', 'zh': 'EURO STOXX 50 期权未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # FVS 这一行的产品名换过（前 93 期「Mini-Futures auf VSTOXX®」，后 114 期
    # 「Futures on VSTOXX®」），代码始终 FVS；合约乘数是否也换过 fetch 侧没核实过 ——
    # 本页只画张数不做名义额换算，所以不受影响；要换算先去查 Eurex 产品规格。
    {'zh': 'DAX 与 VSTOXX（FDAX / ODAX / FVS）', 'cols': [
        {'col': 'adv_dax_fut_contracts', 'zh': 'DAX 期货 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_dax_fut_contracts', 'zh': 'DAX 期货未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_dax_opt_contracts', 'zh': 'DAX 期权 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_dax_opt_contracts', 'zh': 'DAX 期权未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_vstoxx_fut_contracts', 'zh': 'VSTOXX 期货 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_vstoxx_fut_contracts', 'zh': 'VSTOXX 期货未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # ⚠ 这一组全是**月度总额**，不是 ADV。官方现货工作簿只发月总额；
    #   ADV = 月总额 ÷ trading_days_cash（fetch/db1.py 口径坑 7），而 trading_days_cash
    #   是慢腿列，本页不做算术，所以这里如实标成「月度总额」，别在标题里写 ADV。
    {'zh': '现货成交额（Xetra / 法兰克福场内，月度总额，单边计）', 'cols': [
        {'col': 'turnover_xetra_eurbn', 'zh': 'Xetra 电子盘合计',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
        {'col': 'turnover_fwb_eurbn', 'zh': '法兰克福场内合计',
         'unit': 'EUR bn/month', 'fmt': 'f2'},
        {'col': 'turnover_xetra_equities_eurbn', 'zh': 'Xetra 股票',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
        {'col': 'turnover_xetra_etp_eurbn', 'zh': 'Xetra ETF/ETC/ETN',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
        {'col': 'turnover_fwb_equities_eurbn', 'zh': '法兰克福场内股票',
         'unit': 'EUR bn/month', 'fmt': 'f2'},
        {'col': 'turnover_fwb_structured_eurbn', 'zh': '法兰克福场内结构化产品',
         'unit': 'EUR bn/month', 'fmt': 'f2'},
        {'col': 'turnover_cash_total_eurbn', 'zh': '集团台账口径合计（深史，2010-01 起）',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
    ]},

    # 与上面 adv_eurex_* / oi_eurex_* 是**两套并行口径**，永不互校。
    # fetch/db1.py 口径坑 4 全量实测：vol_fd_rates vs Eurex 利率组小计，
    # 222 个月里 48 个不等；按官方脚注把股息摊回去之后，222 个月里 217 个仍然不等。
    {'zh': '集团台账口径衍生品月成交量（IR 口径，与 Eurex 工作簿不可互校）', 'cols': [
        {'col': 'vol_fd_total_contracts', 'zh': '全所合计（含 ETC/农产品/贵金属）',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'vol_fd_index_contracts', 'zh': '股指（已摊入股息衍生品）',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'vol_fd_equity_contracts', 'zh': '单股（已摊入股息衍生品）',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'vol_fd_rates_contracts', 'zh': '利率',
         'unit': 'contracts/month', 'fmt': 'f0c'},
    ]},

    {'zh': 'EurexOTC Clear 场外清算', 'cols': [
        {'col': 'otc_notional_outstanding_eurbn', 'zh': '名义未平仓（月内平均值）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
        {'col': 'otc_notional_cleared_eurbn', 'zh': '当月清算名义量（含压缩）',
         'unit': 'EUR bn/month', 'fmt': 'f0c'},
    ]},

    # ★ 单独成组、单独一图。全仓**唯一的非交易量月度指标** ——
    #   「利润跑向托管结算层」这条结构性趋势的唯一可跟踪证据。
    #   17,459 €bn = €17.46 tn（本页按 €bn 原样画，不做单位换算）。
    {'zh': 'Clearstream 托管资产 AuC（ICSD + CSD 合并）', 'cols': [
        {'col': 'auc_securities_services_eurbn', 'zh': '托管资产（Assets under custody）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'Clearstream 结算笔数、担保品与现金余额', 'cols': [
        {'col': 'settle_icsd_txn_mn', 'zh': '结算笔数（⚠ 只含 ICSD，不含德国本土 CSD）',
         'unit': 'mn transactions/month', 'fmt': 'f2'},
        {'col': 'gsf_collateral_eurbn', 'zh': 'GSF 担保品在外量（月内平均）',
         'unit': 'EUR bn', 'fmt': 'f0', 'stock': True},
        {'col': 'cash_balances_eurmn', 'zh': '日均现金余额（含受制裁冻结账户）',
         'unit': 'EUR mn', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'Clearstream 基金服务（IFS）', 'cols': [
        {'col': 'auc_fund_services_eurbn', 'zh': 'IFS 托管资产（月内平均）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
        {'col': 'settle_ifs_txn_mn', 'zh': 'IFS 结算笔数',
         'unit': 'mn transactions/month', 'fmt': 'f2'},
    ]},

    {'zh': '指数授权、ETF 资产与 360T 外汇', 'cols': [
        {'col': 'aum_stoxx_dax_etf_eurbn', 'zh': '挂钩 STOXX/DAX 的 ETF 资产',
         'unit': 'EUR bn', 'fmt': 'f1', 'stock': True},
        {'col': 'vol_licensed_index_contracts', 'zh': '授权指数衍生品月成交量',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'adv_360t_fx_eurbn', 'zh': '360T 外汇 ADV',
         'unit': 'EUR bn/day', 'fmt': 'f1'},
    ]},

    # ⚠ 单位是 MWh 不是 TWh。官方工作簿表头写「(in TWh)」是笔误，
    #   单元格里是 MWh，差 10⁶。列名带 _mwh 就是为了每次看到都提醒一次。
    {'zh': 'EEX 电力与天然气（MWh，注意不是 TWh）', 'cols': [
        {'col': 'vol_power_spot_mwh', 'zh': '电力现货',
         'unit': 'MWh/month', 'fmt': 'f0c'},
        {'col': 'vol_power_deriv_mwh', 'zh': '电力衍生品',
         'unit': 'MWh/month', 'fmt': 'f0c'},
        {'col': 'vol_gas_mwh', 'zh': '天然气',
         'unit': 'MWh/month', 'fmt': 'f0c'},
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


# 慢腿列 = 本页画的列 ∩ 慢腿全集。只列真正画了的，避免 slow_cols 里出现幽灵列。
_SLOW_ALL = _slow_universe()
SLOW_COLS = sorted(c for c in _charted() if c in _SLOW_ALL)


SPEC = {
    'ticker': 'db1',
    'name':   'Deutsche Börse',
    'title':  '德意志交易所（DB1）月度经营指标',
    'csv':    'db1.csv',
    'ccy':    'EUR',
    'source': ('Source: Deutsche Börse Group IR "Major business figures"、'
               'Eurex Monthly Statistics、FWB Monthly Cash Market Statistics; '
               'format after Goldman Sachs GIR'),

    'headline': HEADLINE,
    'groups':   GROUPS,
    'slow_cols': SLOW_COLS,

    # series/db1_breaks.csv 不存在 —— 官方 xlsx 没有可机器抽取的脚注台账。
    # 已知的列级口径变化只影响单列，画成全页红线会误伤其余四十多列，故留空。
    'breaks': [],

    'notes': [
        '发布节奏：三个源两种节奏。Eurex 工作簿月末后第 2–6 天（2016-01 以来 127 期'
        '全部在此带宽内）、FWB 现货工作簿第 1–4 天（20 期里 18 期）、集团 IR 台账'
        '约第 10 天（落地页原文 "available as of the second week after the reporting '
        'month"）。本机实测 series/db1.csv：快腿列最新月 2026-07，慢腿列最新月 2026-06。',

        'slow_cols（共 %d 列）不参与门槛判定，最新月留空是正常的。清单不手抄，'
        '由 fetch/db1.py 的模块常量 SLOW_LEG_COLUMNS 派生（本文件保留同名字面量兜底，'
        '两者本机实测一致）。把慢腿列放进门槛会让整页被拖住整整一个月。' % len(SLOW_COLS),

        '⚠ settle_icsd_txn_mn 只含 ICSD，**不含**德国本土 CSD 的约 2 倍笔数；'
        '而同一张表的 auc_securities_services_eurbn 却是 ICSD+CSD 合并 —— 同一份文件'
        '两行两个口径。两期独立实证：2025-12 台账结算 9.823717m ≡ Clearstream 稿 ICSD 9.8'
        '（CSD 17.6 不在内）；同期 AuC 16,788.0104 ≡ ICSD 9,756 + CSD 7,032。'
        '2026-03 再次复现（结算 11.867241m ≡ ICSD 12，CSD 25 不在内）。',

        '⚠⚠ AuC 的「存量」标注与官方口径有冲突，已按主线程指令标 stock: True，但换算时必须特判：'
        '官方 monthly-volume-development PDF 把这一行写成 '
        '"Value of securities deposited (average value)"，即**月内平均值而非期末时点**'
        '（otc_notional_outstanding / gsf_collateral / cash_balances / auc_fund_services 同理）。'
        'stock: True 的缺省语义是配月末汇率，而这几列跨币种换算应配**月均汇率**。'
        '本页是 EUR 本币页、不做换算，所以不影响当前呈现；notional.py 接手之前必须先解决这个冲突。',

        '⚠ 现货那一组是**月度总额**不是 ADV。官方现货工作簿只发月总额；'
        'ADV = 月总额 ÷ trading_days_cash。2026-07 官方新闻稿自己给的是 '
        '"average daily Xetra trading volume to €6.85 billion"，而本机 CSV 里 '
        'turnover_xetra_eurbn = 157.511，157.511 ÷ 23 = 6.848 —— 对得上；'
        '但 **trading_days_cash 的 2026-07 那一格此刻还是空的**（慢腿，要等台账），'
        '这正是本页画不出 Xetra ADV、只能画月度总额的原因。'
        '除数 trading_days_cash 是慢腿列，且与 trading_days_eurex 在 222 个可比月里有 27 个'
        '不等（德国统一日与圣灵降临节周一 Eurex 开、Xetra 关），两个日历不能互相顶替。',

        '⚠ vol_fd_*（台账口径）与 adv_eurex_* / oi_eurex_*（Eurex 工作簿口径）是两套并行口径，'
        '**永不互校、也不要放进同一条线**。全量实测：vol_fd_rates 与 Eurex 利率组小计'
        '222 个月里 48 个不等；按官方脚注把股息衍生品摊回股指+单股之后，222 个月里 217 个'
        '仍然不等。官方脚注自己也写明「总数不等于分项之和」（含 ETC / 农产品 / 贵金属）。',

        '⚠ EEX 三列的单位是 **MWh 不是 TWh**。官方工作簿表头写「(in TWh)」是笔误，'
        '差 10⁶：2026-06 单元格 power spot 88,034,094.5 / power deriv 960,720,291 / '
        'gas 679,742,442.47，同期官方 PDF 是 88.0 / 960.7 / 679.7 TWh。'
        '列名带 _mwh 就是这个原因，本页照原值画，不做换算。',

        'aum_stoxx_dax_etf_eurbn 的时点口径**官方未言明**：同一页别的行都标了 (average value)，'
        '唯独这一行没标，暗示是期末数，但这是推断不是证据。本页按 stock: True 标注，'
        '在拿到官方定义前不要拿它跟 msci.aum_eop_usdbn 比水平值。',

        'adv_360t_fx_eurbn 自 2018-07 起含 GTX，跨那个月的同比不是纯内生增长。'
        '这是列级口径变化、不是全页断点，所以不画红线。',

        'turnover_xetra_structured_eurbn 刻意不入图：本机实测 2025-10→2026-07 之间只有 5 个值、'
        '中间 5 个月为空。平滑类图型遇到 null 会把它当 0 画出塌到零的假线。',

        '成交额一律**单边计**（single-counted）：FWB 工作簿「Explanation Report」表与 IR 台账 PDF '
        '现货行的脚注都写明了。跨家比要注意 HKEX 的南向 ADT 是双边。'
        '另：Xetra ≠ Deutsche Börse 现货全部 —— 2026-07 官方新闻稿的 €163.37bn 是 '
        'Xetra(XETR) €157.51bn + Frankfurt(XFRA) €5.86bn。',

        '三条腿都会被官方事后重述，fetcher 一律「只填空不覆盖」、冲突写 '
        'cache/db1_restatements.csv。实测：Eurex 月成交总数 vs 台账 vol_fd_total，'
        '210 个可比月里 50 个不等；Eurex 未平仓 222 对里 17 对不等（最大 2.48%，2008-07）。'
        '所以历史段与当年印出来的数字对不上是官方重述，不是本页算错。',

        '各列首个非空月（实测）：vol_fd_index/equity/rates 自 2002-01；gsf_collateral 自 2007-01；'
        'Eurex 各列自 2008-01（股息组 2008-06、FVS 2009-05、FBTP 2009-09、FOAT 2012-04）；'
        'vol_fd_total / turnover_cash_total / settle_* 自 2010-01；auc_* 与 aum_stoxx_dax_etf '
        '自 2012-01；360T 与 EEX 与 cash_balances 自 2015-01；otc_* 与 vol_licensed 自 2016-01；'
        'turnover_xetra/fwb 自 2024-01；现货分资产类别列自 2024-12。早于首月为空是官方就没有。',
    ],
}
