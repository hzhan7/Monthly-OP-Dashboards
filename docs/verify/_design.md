# /exchanges/ 扩容到 12 家：竞争池数据模型与呈现方式设计

设计日期 2026-08-06 · 输入 = `build/exchanges.py`（746 行）、`assets/charts.js`（17 种 kind）、
`assets/page.js`、`build/engine_kinds.md`、`/tmp/exch_recon/*.md`（9 家侦察稿 + 9 份复核稿）
· 现有仓内 `series/{cme,cboe,hkex,msci}.csv` 表头逐列核过

本文只做设计，不改仓内任何文件。所有字段都出自侦察稿**实测证实可取**的列；
凡侦察稿说"拿不到""只有季度""历史不够"的，一律不出现在任何图的数据契约里。

> ⚠️ **2026-08-06 追记 —— 本文是设计存档，有一处已被实现推翻，原文一字未改**：
> 设计里的 `/exchanges-intl/`（欧洲与亚太合页，见 §3.1 表与 §3.4）**建出来之后又被拆成
> `/exchanges-eu/` 与 `/exchanges-apac/` 两张页**，理由是口径不是版面（欧洲三家争同一批
> 订单流、占比有内容；亚太几家法域隔离、占比没有外部指涉）。拆分完成后合页于同日删除。
> 因此本文凡出现 `'page': 'exchanges-intl'` 的池，**现役 `build/pools.py` 里已改指**：
> `eu_cash` / `eu_deriv` → `exchanges-eu`，`apac_cash` / `apac_deriv` / `fn_listing` →
> `exchanges-apac`。删除的实际步骤见 `docs/DELIVERY.md §4.4`。

---

## 0. 三条继承下来的硬约束，以及扩容后各自变成什么

现有 `build/exchanges.py` 的 docstring 立了三条规矩。12 家之后它们不是"仍然适用"，
而是**各自被放大成一个设计决策**：

| 原规矩 | 3 家时的形态 | 12 家之后必须变成什么 |
|---|---|---|
| 单位不可加总 | 全页只用同比 + 指数化 | **池是单位可比性的定义单位**。同比与指数化是"最低可比口径"，但欧洲现货池（三家同为 €bn/日 ADNV）可以直接比水平值，北美两池甚至可以比真份额 —— 一刀切成"只准指数化"会白扔掉扩容带来的最大增量 |
| 发布门槛取成员共同最新月 | 三家取 min ⇒ 次月第 10 天（HKEX 是短板） | **门槛必须按页算，不能按仓算**。12 家取 min ⇒ 次月第 13–14 天（SGX / Euronext 是短板），而北美四家第 6 天就齐了。不拆页 = 让最慢的成员每月拖住最快的池整整一周 |
| 算不出共同最新月就不写半张页 | 缺一家整页不发 | 拆页之后，缺员只黑掉**它自己那一页**。这条对分批上线是决定性的：批 1 只上 ICE，`/exchanges-na/` 就能发，其余三页照旧 skip |

另有两条从复核稿里读出来、现在必须写进设计的新约束：

- **慢腿列不得进 panel。** `exchanges.py:240-243` 对共同窗口内的空洞直接 `raise SystemExit`。
  DB1 的 Clearstream / OTC / 360T 列、NDAQ 的 `marketshare{YY}.xlsx`（次月第 10 个工作日）
  天生会在最新月留空 ⇒ 这些列只能进单公司页，绝不能进池（`verify_db1.md` §四.3、`verify_ndaq.md` §四）。
- **数据色只有 6 个。** `C.*` 里能做数据色的是 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD
  （RED 是断点与截轴离群值专用）。**12 家不可能一家一色。** 这不是配色偏好问题，
  它直接决定了图型选择 —— 见第二节 §B.0。

---

## 一、竞争池数据模型（POOLS）

### 1.1 结构说明

池是一等公民：**一个池 = 一个"这些数放在一起是同一件事"的断言**，
断言的强度由 `share` 字段分三档，这是整个设计里最重要的一个区分：

| `share` 取值 | 含义 | 允许画什么 | 禁止画什么 |
|---|---|---|---|
| `'true'` | 有**官方披露的行业分母**，份额是真的 | 堆叠份额带（含残差）、Δpp 排序柱、增长归因桥 | —— |
| `'pool'` | 无行业分母，只能算"成员合计中的占比" | 池内相对占比（图注必须写明分母 = 本池 N 家之和） | 一律不许写"市场份额"四个字 |
| `'none'` | 币种/量纲/标的都不同 | 指数化、同比、同比离散度 | 任何形式的占比、任何绝对值并排 |

**全仓只有两个池是 `'true'`**，而且都靠 ICE 一家带进来的行业分母
（`adv_tapeA/B/C_consolidated_mnsh` 与 `adv_us_equity_options_industry_kcontracts`）。
这是"ICE 排在实现路线第一批"的全部理由 —— 它的价值不是多一条线，是把分母带进来。

每个池的 `head` 与 `members` 是**两个不同的清单**，这一条是从 TMX 现货（2021-08 起，
比 HKEX 还短 2 年 7 个月）逼出来的：

- `head` = 决定本池共同最新月与共同起点的成员。必须是历史长、发布快、无空洞的。
- `members` = 进图的全部成员。历史短的成员在长历史图上前段留 `None`，
  引擎会在缺口处断线（`L()` 已经这么做），**不会**把共同窗口砍到它的起点。

现有 `exchanges.py:240-243` 只对 `HEAD` 列查空洞，所以这个设计**不需要改引擎**。

### 1.2 POOLS 字面量

可直接放进 `build/pools.py`，被各页 build 脚本 import。

```python
# -*- coding: utf-8 -*-
"""竞争池定义 —— 横截面页的唯一真值。

一个池 = 一个「这些数放在一起是同一件事」的断言。断言的强度写在 share 字段里：
  'true' 有官方行业分母，份额是真的（全仓只有北美两池）
  'pool' 无分母，只能算成员合计中的占比；图注必须写明分母是谁
  'none' 币种/量纲/标的都不同，只能指数化与同比

head 与 members 是两个清单：head 决定共同最新月与共同起点，members 决定进图的线。
历史短的成员进 members 不进 head —— 它在长历史图上前段留 None，不把窗口砍短。

member.cols 是「同一件事」的原始列，多列表示要相加（口径已在侦察稿核过）；
scale 是到池内统一单位的乘数；per_day 给交易日列名表示原始值是月度总量、需要除。
这三样一律在 Python 侧算完再进 payload，页面只画不算。
"""

# 池内统一单位。跨池不可比，同池内可比 —— 这是池存在的意义。
U_KCTR = 'k contracts/day'      # 千张/日
U_BNSH = 'bn shares/day'        # 十亿股/日
U_EURBN = 'EUR bn/day'          # 十亿欧元/日（ADNV，单边计）
U_USDBN = 'USD bn/day'
U_LOCAL = 'local ccy/day'       # 各家本币，只可指数化

POOLS = [

  # ══════════════════════ 轴一：地理池 ══════════════════════

  {
    'id': 'na_cash', 'zh': '北美现货股票', 'axis': 'geo', 'page': 'exchanges-na',
    'unit': U_BNSH, 'share': 'true',
    'basis': ('全部为 matched（本所撮合）ADV，十亿股/日。一律不用 handled —— '
              'handled 含路由到别家成交的量，Cboe / Nasdaq 不披露对应口径。'),
    'denom': {                                   # ⭐ 全行业分母，ICE 独家带进来的
      'key': 'ice', 'csv': 'ice.csv',
      'cols': ['adv_tapeA_consolidated_mnsh',
               'adv_tapeB_consolidated_mnsh',
               'adv_tapeC_consolidated_mnsh'],
      'scale': 1 / 1000.0, 'per_day': None, 'start': '2011-01',
      'label': '全美合并成交量（Tape A+B+C consolidated）',
      'evidence': 'verify_ice.md §5.1：2026-07 = 17.437bn 股/日，'
                  'NYSE 3.329bn = 19.1% 与 ICE 自报 share 0.191 逐位相符',
    },
    'residual': '其余（Nasdaq 之外的 ATS / MEMX / IEX / TRF 场外）',
    'head': ['ice', 'cboe'],                     # 两家都是次月第 3 个交易日
    'members': [
      {'key': 'ice', 'disp': 'NYSE Group', 'color': 'NAVY', 'csv': 'ice.csv',
       'cols': ['adv_nyse_tapeA_matched_mnsh', 'adv_nyse_tapeB_matched_mnsh',
                'adv_nyse_tapeC_matched_mnsh'],
       'scale': 1 / 1000.0, 'per_day': None, 'start': '2011-01',
       'note': '官方无 A+B+C 合计行，需派生；ICE 另给 share_nyse_us_cash_matched 可做自校验'},
      {'key': 'cboe', 'disp': 'Cboe U.S.', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_us_equities_matched_shares_bn'],
       'scale': 1.0, 'per_day': None, 'start': '2017-01'},
      {'key': 'ndaq', 'disp': 'Nasdaq', 'color': 'GOLD', 'csv': 'ndaq.csv',
       'cols': ['vol_us_matched_shares_mm'],
       'scale': 1 / 1000.0, 'per_day': 'us_trading_days_pub', 'start': '2010-10',
       'note': '⚠ 原始是月度总量不是 ADV，不除交易日会比同行大 ~20 倍（verify_ndaq E1）。'
               '交易日**不取 nasdaqtrader 的 us_trading_days**（次月第 10 个工作日才出，'
               '会把整页门槛拖后一周），改用 miax.trading_days_options（次月第 3-5 天）'},
      {'key': 'miax', 'disp': 'MIAX Pearl Equities', 'color': 'GRAY', 'csv': 'miax.csv',
       'cols': ['adv_equities_mnshares'],
       'scale': 1 / 1000.0, 'per_day': None, 'start': '2020-12',
       'note': '尾部对照，份额 0.7-1.3%。capture 与 Cboe 分母不同（total vs touched），'
               '只进 ADV 不进 take rate 图（verify_miax §四）'},
      {'key': 'tmx', 'disp': 'TMX（加拿大，另一分母）', 'color': 'GREEN', 'csv': 'tmx.csv',
       'cols': ['tmx_all_volume_shares_bn'], 'scale': 1.0,
       'per_day': 'trading_days_equity', 'start': '2021-08',
       'in_share': False,                        # ⚠ 不进份额计算：分母是加拿大不是美国
       'note': '只做规模对照，绝不进份额分子 —— TSX 不在美国合并成交量里。'
               '起点 2021-08，只进近端图不进长历史图，也不进 head'},
    ],
  },

  {
    'id': 'na_multilist_opt', 'zh': '北美多重挂牌期权', 'axis': 'geo', 'page': 'exchanges-na',
    'unit': U_KCTR, 'share': 'true',
    'basis': ('equity & ETF 多重挂牌期权 ADV，千张/日，**均不含指数期权**。'
              'Cboe 与 MIAX 的列名、RPC 定义逐字相同。'),
    'denom': {
      'key': 'ice', 'csv': 'ice.csv',
      'cols': ['adv_us_equity_options_industry_kcontracts'],
      'scale': 1.0, 'per_day': None, 'start': '2011-01',
      'label': '全美股票/ETF 期权行业 ADV',
      'evidence': 'verify_ice.md §5.2：2026-07 行业 64,394k，NYSE 21.1% + Cboe 24.4% = 45.5%，'
                  '余下 54.5% 给 Nasdaq/MIAX/BOX，量级自洽；ICE 10-K 自报 2025 年 18.9% 可反算',
      'caveat': '⚠ ICE 从未书面说明该分母是否含指数期权。页面上只能写「经与 Cboe multilist 及 '
                'ICE 10-K 交叉验证，口径与多重上市股票/ETF 期权一致」，'
                '不得写成「ICE 官方定义为不含指数期权」',
      'alt': 'miax.industry_adv_options_kcontracts 是第二个候选分母，'
             '**必须二选一定死**，两条并存会造出两套份额（verify_miax §12）',
    },
    'residual': '其余（Nasdaq 六所 / BOX / MEMX Options）',
    'head': ['ice', 'cboe', 'miax'],
    'members': [
      {'key': 'cboe', 'disp': 'Cboe', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_multilist_options_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2017-01'},
      {'key': 'miax', 'disp': 'MIAX（四所合计）', 'color': 'GOLD', 'csv': 'miax.csv',
       'cols': ['adv_multilist_options_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2015-04',
       'note': '份额 2015 年 7.4% → 2026-07 17.9%。单所线（M/P/D/S）2019-03 Emerald 起量时'
               '有内部导流造成的假跳，画单所必须标注'},
      {'key': 'ice', 'disp': 'NYSE（Arca + American）', 'color': 'NAVY', 'csv': 'ice.csv',
       'cols': ['adv_nyse_equity_options_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2011-01'},
    ],
    'rpc': {                                     # 全仓唯一一对逐字同定义的 take rate
      'unit': 'USD/contract',
      'series': [('cboe', 'rpc_multilist_options_usd', '2017-01'),
                 ('miax', 'rpc_multilist_options_usd', '2025-01'),
                 ('ice', 'rpc_nyse_equity_options_usd', '2011-01')],
      'overlap': '2025-01 – 2026-06（18 个月）',
      'caveat': ('⚠ 三家的滞后不同：Cboe 与 MIAX 的 RPC 滞后一个月（最新月天然为空），'
                 'ICE 的不滞后。任何并排图必须在绘图层截齐到三家都有值的那个月，'
                 '否则每月看板一刷新都像是 Cboe 抓挂了（verify_ice §5.3）。'
                 'MIAX 只有 18 个月 ⇒ 2026-12 之前做不了同比、做不了指数化，只能画绝对值'),
    },
  },

  {
    'id': 'na_total_opt', 'zh': '北美期权总量（含指数）', 'axis': 'geo', 'page': 'exchanges-na',
    'unit': U_KCTR, 'share': 'pool',
    'basis': '含指数期权的美股期权 ADV。Nasdaq 的口径含指数期权，无法拆，只能进这个池。',
    'denom': None,
    'head': ['cboe', 'ndaq'],
    'members': [
      {'key': 'cboe', 'disp': 'Cboe（总）', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_us_options_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2017-01'},
      {'key': 'ndaq', 'disp': 'Nasdaq（六所）', 'color': 'GOLD', 'csv': 'ndaq.csv',
       'cols': ['vol_us_options_mmcontracts'], 'scale': 1000.0,
       'per_day': 'us_trading_days_pub', 'start': '2025-01',
       'note': '⚠ 只有 19 个月（IR PDF 每月原地替换，历史只在 Wayback 而本机硬禁）。'
               '2026-12 之前做不了同比'},
      {'key': 'miax', 'disp': 'MIAX', 'color': 'GRAY', 'csv': 'miax.csv',
       'cols': ['adv_multilist_options_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2015-04', 'note': 'MIAX 完全不做指数期权（INDEX_OPTION 实测恒为 0），'
                                   '这本身就是它与 Cboe 最大的结构差异'},
    ],
  },

  {
    'id': 'eu_cash', 'zh': '欧洲现货股票', 'axis': 'geo', 'page': 'exchanges-intl',
    'unit': U_EURBN, 'share': 'pool',
    'basis': ('全部为 €bn/日 ADNV、单边计、股票口径。这是全仓**唯一可以直接比水平值**的池 —— '
              '同币种、同单位、同口径。但覆盖范围不同（Xetra 只德国上市，Cboe Europe 与 '
              'Euronext 是泛欧），所以水平可比、份额不成立：全欧 lit 成交没有任何一家披露分母。'),
    'denom': None,
    'residual': None,
    'head': ['enx', 'cboe'],
    'members': [
      {'key': 'enx', 'disp': 'Euronext', 'color': 'NAVY', 'csv': 'enx.csv',
       'cols': ['adv_cash_equities_adnv_eurbn'], 'scale': 1.0, 'per_day': None,
       'start': '2012-01',
       'note': '⚠ 不要用 adv_cash_adnv_eurbn（含结构化产品与 ETF），Cboe 那列不含。'
               '断点：2025-11 Athens、2021-05 Borsa Italiana、2017-01 / 2018-01'},
      {'key': 'cboe', 'disp': 'Cboe Europe', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_eu_equities_adnv_eurbn'], 'scale': 1.0, 'per_day': None, 'start': '2017-01'},
      {'key': 'db1', 'disp': 'Xetra', 'color': 'GOLD', 'csv': 'db1.csv',
       'cols': ['adv_xetra_adnv_eurbn'], 'scale': 1.0, 'per_day': None, 'start': '2010-01'},
    ],
    'evidence': '2026-06 实测 Euronext 15.52 / Cboe 14.95 / Xetra 8.59 €bn per day '
                '（verify_enx §四、verify_db1 §四）',
  },

  {
    'id': 'eu_deriv', 'zh': '欧洲衍生品', 'axis': 'geo', 'page': 'exchanges-intl',
    'unit': U_KCTR, 'share': 'none',
    'basis': '千张/日。合约乘数差数十倍（Bund vs CAC40 vs Brent），只能指数化与同比。',
    'denom': None,
    'head': ['db1', 'enx'],
    'members': [
      {'key': 'db1', 'disp': 'Eurex（总）', 'color': 'NAVY', 'csv': 'db1.csv',
       'cols': ['adv_eurex_total_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2009-01'},
      {'key': 'enx', 'disp': 'Euronext 衍生品', 'color': 'MBLUE', 'csv': 'enx.csv',
       'cols': ['adv_index_deriv_kcontracts', 'adv_singlestock_deriv_kcontracts'],
       'scale': 1.0, 'per_day': None, 'start': '2012-01',
       'note': '⚠ 单股那条必须用 legacy 口径（主列 − athex_* 备注列），'
               '否则 2025-11 有 3-6 倍假跳'},
      {'key': 'ice', 'disp': 'ICE Futures Europe（利率）', 'color': 'GOLD', 'csv': 'ice.csv',
       'cols': ['adv_stir_kcontracts', 'adv_mltir_kcontracts'], 'scale': 1.0,
       'per_day': None, 'start': '2011-01'},
      {'key': 'ndaq', 'disp': 'Nasdaq 欧洲', 'color': 'GRAY', 'csv': 'ndaq.csv',
       'cols': ['vol_eu_derivs_mmcontracts'], 'scale': 1000.0, 'per_day': None,
       'start': '2025-01', 'in_share': False,
       'note': '⚠ 无欧洲交易日可用（IR 不给），**只能画月度总量、不能画 ADV**；'
               '19 个月、比 Eurex 小两个数量级 ⇒ 只进指数化图，不进任何同轴绝对值图'},
    ],
  },

  {
    'id': 'apac_cash', 'zh': '亚太现货股票', 'axis': 'geo', 'page': 'exchanges-intl',
    'unit': U_LOCAL, 'share': 'none',
    'basis': ('各家本币日均成交额（HK$bn / ¥tn / S$mn / A$bn）。币种与量纲全不同，'
              '**只能指数化**（统一基期 2019-01 = 100，即 HKEX 起点）。'
              '不做汇率折算 —— FX 换算是派生量，仓库硬约束是 series 只放官方原始披露。'),
    'denom': None,
    'head': ['hkex', 'jpx', 'sgx', 'asx'],
    'members': [
      {'key': 'hkex', 'disp': 'HKEX', 'color': 'GOLD', 'csv': 'hkex.csv',
       'cols': ['adt_hkdbn'], 'scale': 1.0, 'per_day': None, 'start': '2019-01'},
      {'key': 'jpx', 'disp': 'JPX（东证）', 'color': 'NAVY', 'csv': 'jpx.csv',
       'cols': ['adt_cash_total_jpytn'], 'scale': 1.0, 'per_day': None, 'start': '1985-01',
       'note': '与 HKEX 是全仓最干净的一对现货对照：都是日均成交额 + 月末时价总额，'
               '都含 ETF/REIT，都含场内大宗'},
      {'key': 'sgx', 'disp': 'SGX', 'color': 'MBLUE', 'csv': 'sgx.csv',
       'cols': ['sdav_sgdmn'], 'scale': 1.0, 'per_day': None, 'start': '2015-01'},
      {'key': 'asx', 'disp': 'ASX', 'color': 'GREEN', 'csv': 'asx.csv',
       'cols': ['adt_cash_onmarket_audbn'], 'scale': 1.0, 'per_day': None, 'start': '2016-01',
       'note': 'on-market 口径，不含场外报告成交；Cboe Australia 约占澳洲两成且不在此数里'},
    ],
  },

  {
    'id': 'apac_deriv', 'zh': '亚太衍生品', 'axis': 'geo', 'page': 'exchanges-intl',
    'unit': U_KCTR, 'share': 'none',
    'basis': ('统一到千张/日后指数化。⚠ 这个池是全站最容易画错的一个：'
              'HKEX 存的是裸张数、SGX 原始值是裸张数、ASX 是裸张数、'
              'JPX 的原始张数被 mini(1/10) 与 micro(1/100) 严重扭曲。'),
    'denom': None,
    'head': ['hkex', 'sgx', 'asx'],
    'members': [
      {'key': 'hkex', 'disp': 'HKEX', 'color': 'GOLD', 'csv': 'hkex.csv',
       'cols': ['derivatives_adv_contracts'], 'scale': 1 / 1000.0, 'per_day': None,
       'start': '2019-01'},
      {'key': 'sgx', 'disp': 'SGX', 'color': 'MBLUE', 'csv': 'sgx.csv',
       'cols': ['ddav_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2015-01',
       'note': 'SGX 原始 DDAV 是**张**（2026-06 = 1,619,444），入库时已 ÷1000'},
      {'key': 'jpx', 'disp': 'JPX（大合约当量）', 'color': 'NAVY', 'csv': 'jpx.csv',
       'cols': ['adv_deriv_total_lgeq_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2014-12',
       'note': '⚠ **必须用大合约当量列，禁止用 adv_deriv_total_kcontracts**。'
               '原始张数下 JPX ≈ 1.23 × HKEX（亚太第一），当量口径下 JPX ≈ 0.27 × HKEX —— '
               '排序直接翻转（verify_jpx §五）。当量列是派生列，折算表须按 JPX 合约规格页复核后写死'},
      {'key': 'asx', 'disp': 'ASX', 'color': 'GREEN', 'csv': 'asx.csv',
       'cols': ['adv_futures_total_contracts', 'adv_single_stock_options_contracts',
                'adv_index_options_contracts'],
       'scale': 1 / 1000.0, 'per_day': None, 'start': '2016-01',
       'note': '⚠ 混合口径（利率 + 股指 + 商品 + 电力 + NZ），且含 non-traded volume。'
               '图注必须写明是混合量，不能标成任何单一资产类'},
    ],
  },

  # ══════════════════════ 轴二：标的池 ══════════════════════

  {
    'id': 'rates', 'zh': '利率衍生品', 'axis': 'product', 'page': 'exchanges-products',
    'unit': U_KCTR, 'share': 'none',
    'basis': ('千张/日。这个池的看点**不是谁抢谁的单**，而是各条货币曲线的周期错位：'
              'CME = 美元（SOFR / Treasuries）、ICE + Eurex = 欧元与英镑、'
              'TMX = 加元、JPX = 日元。互补而非竞争，所以只比增速，绝对量无意义。'),
    'denom': None,
    'head': ['cme', 'ice', 'db1'],
    'members': [
      {'key': 'cme', 'disp': 'CME（美元）', 'color': 'NAVY', 'csv': 'cme.csv',
       'cols': ['adv_rates_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2008-01'},
      {'key': 'ice', 'disp': 'ICE（欧洲曲线）', 'color': 'MBLUE', 'csv': 'ice.csv',
       'cols': ['adv_stir_kcontracts', 'adv_mltir_kcontracts'], 'scale': 1.0,
       'per_day': None, 'start': '2011-01'},
      {'key': 'db1', 'disp': 'Eurex（欧债）', 'color': 'GOLD', 'csv': 'db1.csv',
       'cols': ['adv_eurex_rates_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2002-01'},
      {'key': 'tmx', 'disp': 'MX（加元）', 'color': 'GREEN', 'csv': 'tmx.csv',
       'cols': ['mx_adv_stir_kcontracts', 'mx_adv_bond_futures_kcontracts'],
       'scale': 1.0, 'per_day': None, 'start': '2002-01'},
      {'key': 'jpx', 'disp': 'JPX（日元）', 'color': 'GRAY', 'csv': 'jpx.csv',
       'cols': ['adv_jgb10y_futures_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '1985-10',
       'note': 'CME 以 SOFR 短端为主、JPX 以 10 年 JGB 长端为主，绝对量差两个数量级'},
    ],
    'excluded': [
      ('enx', 'Euronext 没有利率期货。MTS 现券与回购（adv_mts_cash_eurbn / '
              'taadv_mts_repo_eurbn）是**另一层**，禁止进同一张图'),
      ('asx', '分品种（3y / 10y / 90d bank bill）只有 2026-06 起 2 个月，不可回补。'
              '用 adv_futures_contracts 合计当代理会漂移，只能进 apac_deriv 的混合口径'),
    ],
  },

  {
    'id': 'equity_index', 'zh': '股指衍生品', 'axis': 'product', 'page': 'exchanges-products',
    'unit': U_KCTR, 'share': 'none',
    'basis': ('千张/日。标的与乘数完全不同（ES $50/点 vs SPX 期权 $100/点 vs '
              'CAC40 €10/点 vs 日経225 ¥1000/点），**绝对值同轴就是误导**，只能指数化。'),
    'denom': None,
    'head': ['cme', 'cboe', 'db1'],
    'members': [
      {'key': 'cme', 'disp': 'CME（E-mini 系）', 'color': 'NAVY', 'csv': 'cme.csv',
       'cols': ['adv_equity_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2008-01'},
      {'key': 'cboe', 'disp': 'Cboe（SPX/VIX 期权）', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_index_options_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2017-01'},
      {'key': 'db1', 'disp': 'Eurex（ESTX50/DAX）', 'color': 'GOLD', 'csv': 'db1.csv',
       'cols': ['adv_eurex_index_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2002-01'},
      {'key': 'enx', 'disp': 'Euronext（CAC/AEX）', 'color': 'GREEN', 'csv': 'enx.csv',
       'cols': ['adv_index_deriv_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2012-01'},
      {'key': 'jpx', 'disp': 'JPX（N225 + TOPIX）', 'color': 'GRAY', 'csv': 'jpx.csv',
       'cols': ['adv_n225_lgeq_kcontracts', 'adv_topix_futures_kcontracts'],
       'scale': 1.0, 'per_day': None, 'start': '2014-12'},
      {'key': 'ice', 'disp': 'ICE（FTSE/MSCI 授权）', 'color': 'BLUE', 'csv': 'ice.csv',
       'cols': ['adv_equity_index_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2011-01',
       'note': '与 msci.csv 的 aum_eop_usdbn 形成「上游指数 IP × 下游成交量」的对照'},
    ],
    'excluded': [
      ('sgx', 'vol_equity_index_futures_kcontracts 是**月度总量**，需先除交易日；'
              '且 SGX 只给月总量不给分产品日均，隐含日数要用 deriv_vol / ddav 反推，'
              '不能用 sec_trading_days'),
      ('miax', 'adv_futures_fin_contracts 2026-07 = 4,194 张/日 vs CME 8,168,834 张/日，'
               '差约 1,950 倍。只能做「新产品爬坡曲线」，进池会造出无经济含义的 0.05%'),
      ('ndaq', 'q_index_futures_mmcontracts 是**别家撮合、Nasdaq 只收授权费**的量，'
               '与 CME 的股指量有重合部分（同一批合约被两家分别记账）。'
               '绝不能与 CME 同柱比「谁成交大」。且是季度'),
    ],
  },

  {
    'id': 'single_stock_etf_opt', 'zh': '单股与 ETF 期权', 'axis': 'product',
    'page': 'exchanges-products', 'unit': U_KCTR, 'share': 'none',
    'basis': ('千张/日。**这个池只在北美三家之间是真竞争**（见 na_multilist_opt），'
              '其余各家是不同法域的同业务形态对照 —— 各自本土的唯一或主要场所，'
              '不争同一批订单流。图注必须写明，否则会被误读成市占率此消彼长。'),
    'denom': None,
    'head': ['cboe', 'db1'],
    'members': [
      {'key': 'cboe', 'disp': 'Cboe（美国）', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_multilist_options_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2017-01'},
      {'key': 'miax', 'disp': 'MIAX（美国）', 'color': 'GOLD', 'csv': 'miax.csv',
       'cols': ['adv_multilist_options_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2015-04'},
      {'key': 'db1', 'disp': 'Eurex（欧洲）', 'color': 'NAVY', 'csv': 'db1.csv',
       'cols': ['adv_eurex_equity_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2002-01',
       'note': '⚠ 含 single stock futures，Cboe 那列是纯期权'},
      {'key': 'tmx', 'disp': 'MX（加拿大）', 'color': 'GREEN', 'csv': 'tmx.csv',
       'cols': ['mx_adv_equity_options_kcontracts', 'mx_adv_etf_options_kcontracts'],
       'scale': 1.0, 'per_day': None, 'start': '2002-01'},
      {'key': 'jpx', 'disp': 'JPX（日本）', 'color': 'GRAY', 'csv': 'jpx.csv',
       'cols': ['adv_secoptions_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '1997-07'},
      {'key': 'asx', 'disp': 'ASX ETO（澳洲）', 'color': 'BLUE', 'csv': 'asx.csv',
       'cols': ['adv_single_stock_options_contracts'], 'scale': 1 / 1000.0,
       'per_day': None, 'start': '2016-01'},
    ],
    'excluded': [
      ('enx', 'adv_singlestock_deriv_kcontracts 含期货，且 2025-11 起 Athex 单股期货占 90-98% '
              '且是融券替代品不是方向性交易。要进必须先取 legacy 口径，'
              '第一版**不进**，等 legacy 序列建好再说'),
    ],
  },

  {
    'id': 'energy', 'zh': '能源商品', 'axis': 'product', 'page': 'exchanges-products',
    'unit': U_KCTR, 'share': 'none',
    'basis': ('千张/日。全仓最有故事的一对：**Brent（ICE）vs WTI（CME）的基准之争**。'
              '合约标的不可比（桶 / MMBtu / MWh），只能同比与指数化。'),
    'denom': None,
    'head': ['cme', 'ice'],
    'members': [
      {'key': 'cme', 'disp': 'CME（WTI / Henry Hub）', 'color': 'NAVY', 'csv': 'cme.csv',
       'cols': ['adv_energy_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2008-01'},
      {'key': 'ice', 'disp': 'ICE（Brent / TTF）', 'color': 'MBLUE', 'csv': 'ice.csv',
       'cols': ['adv_energy_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2011-01',
       'note': '⚠ OI 一边千张一边裸张：ice.oi_energy_kcontracts vs cme.oi_energy_contracts 差 1000 倍'},
      {'key': 'jpx', 'disp': 'JPX（旧 TOCOM）', 'color': 'GRAY', 'csv': 'jpx.csv',
       'cols': ['adv_deriv_cmdty_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2020-07',
       'note': '⚠ 2020-07 之前宽表把 TOCOM 回填到 1985，但 JPX 当时并不拥有这块业务 ⇒ '
               '2020-07 之前必须留空，不得 pro-forma'},
    ],
    'excluded': [
      ('db1', 'vol_power_deriv_twh / vol_gas_twh 是 **TWh 不是张数**，量纲无关。'
              '只能单独做同比，不进本池的任何水平或指数图'),
      ('enx', 'Nord Pool 电力是 TWh 且仓内无对手；adv_commodity_deriv_kcontracts 是**农产品**，'
              '要配 cme.adv_ag_kcontracts，绝不能配 adv_energy_kcontracts'),
      ('sgx', '商品盘 98% 是铁矿石与干散货运费，与能源不是同一标的'),
    ],
  },

  {
    'id': 'ags', 'zh': '农产品', 'axis': 'product', 'page': 'exchanges-products',
    'unit': U_KCTR, 'share': 'none',
    'basis': '千张/日。标的几乎不重合，只做量级与增速对照，**不做份额**。',
    'denom': None,
    'head': ['cme', 'enx'],
    'members': [
      {'key': 'cme', 'disp': 'CME（玉米/大豆/小麦复合体）', 'color': 'NAVY', 'csv': 'cme.csv',
       'cols': ['adv_ag_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2008-01'},
      {'key': 'enx', 'disp': 'Euronext MATIF', 'color': 'MBLUE', 'csv': 'enx.csv',
       'cols': ['adv_commodity_deriv_kcontracts'], 'scale': 1.0, 'per_day': None,
       'start': '2012-01'},
      {'key': 'miax', 'disp': 'MIAX Futures（春小麦）', 'color': 'GRAY', 'csv': 'miax.csv',
       'cols': ['adv_futures_ag_contracts'], 'scale': 1 / 1000.0, 'per_day': None,
       'start': '2025-01', 'in_share': False,
       'note': '⚠ 只有 Minneapolis 硬红春小麦一个品种，与 CME 差约 160 倍且标的不重合。'
               '复核明确反对把它当份额用（verify_miax §四）—— 只进量级对照表，不进任何占比图'},
    ],
  },

  {
    'id': 'fx_futures', 'zh': 'FX 期货', 'axis': 'product', 'page': 'exchanges-products',
    'unit': U_KCTR, 'share': 'none',
    'basis': '千张/日，**期货张数**。与下面的 FX 即期 ECN 池是两层不同的东西，严禁混画。',
    'denom': None,
    'head': ['cme', 'sgx'],
    'members': [
      {'key': 'cme', 'disp': 'CME', 'color': 'NAVY', 'csv': 'cme.csv',
       'cols': ['adv_fx_kcontracts'], 'scale': 1.0, 'per_day': None, 'start': '2008-01'},
      {'key': 'sgx', 'disp': 'SGX（全球前三）', 'color': 'MBLUE', 'csv': 'sgx.csv',
       'cols': ['vol_fx_futures_kcontracts'], 'scale': 1.0, 'per_day': 'implied_days',
       'start': '2015-01',
       'note': '⚠ 原始是月度总量，隐含交易日用 deriv_vol / ddav 反推，不要用 sec_trading_days'},
    ],
    'excluded': [
      ('ice', 'adv_fx_credit_kcontracts 是 **FX 与信用合并**披露，口径不纯；'
              '要进必须在图上写明「ICE 含信用」'),
      ('tmx', 'USX 2026-06 ADV = 0.568 千张/日，四舍五入就是噪声'),
      ('jpx', 'USD/JPY 等 2026-04 才上市，只有 3 个月，第一版不入池'),
    ],
  },

  {
    'id': 'fx_spot_ecn', 'zh': 'FX 即期 ECN', 'axis': 'product', 'page': 'exchanges-products',
    'unit': U_USDBN, 'share': 'pool',
    'basis': ('$bn/日 ADNV、单边计。Euronext FX（原 FastMatch）与 Cboe FX（原 Hotspot）'
              '是**同一门生意**，全仓最干净的一对之一。'),
    'denom': None,
    'head': ['cboe', 'enx'],
    'members': [
      {'key': 'cboe', 'disp': 'Cboe FX', 'color': 'MBLUE', 'csv': 'cboe.csv',
       'cols': ['adv_fx_adnv_usdbn'], 'scale': 1.0, 'per_day': None, 'start': '2017-01'},
      {'key': 'enx', 'disp': 'Euronext FX', 'color': 'NAVY', 'csv': 'enx.csv',
       'cols': ['adv_fx_spot_usdbn'], 'scale': 1.0, 'per_day': None, 'start': '2013-01'},
      {'key': 'db1', 'disp': '360T', 'color': 'GOLD', 'csv': 'db1.csv',
       'cols': ['adv_360t_fx_eurbn'], 'scale': None, 'per_day': None, 'start': '2016-01',
       'in_share': False,
       'note': '⚠ 单位是 **EUR** bn，另两家是 USD bn。不做汇率折算（仓库硬约束）⇒ '
               '360T 只进指数化图，不进 $bn 的水平图与池内占比'},
    ],
    'evidence': '2026-06 实测 Euronext 30.53 vs Cboe 64.27 USD bn/day（verify_enx §四）',
  },

  # ══════════════════════ 轴三：职能层 ══════════════════════
  # 交易所不是只有撮合一层。这一轴回答的是「同一家公司在价值链的哪一段赚钱、
  # 哪一段在被侵蚀」——Euronext 与 DB1 的上市/结算是垄断而交易是竞争，
  # 这个「一半垄断、一半竞争」的结构，正是横截面页最值得画出来的那条张力。

  {
    'id': 'fn_listing', 'zh': '上市与募资（一级市场）', 'axis': 'function',
    'page': 'exchanges-intl', 'unit': 'count / local ccy', 'share': 'none',
    'basis': ('新上市家数是纯计数、**可直接跨家比**；募资额是各家本币，只能指数化。'
              '一级市场是交易所里少数几乎没有跨境竞争的环节 —— 它的周期与二级市场成交量'
              '经常反向，把它与撮合量并列，才看得出「量在别人手上、单子在自己手上」。'),
    'denom': None,
    'head': ['hkex', 'sgx', 'asx'],
    'members': [
      {'key': 'hkex', 'disp': 'HKEX', 'color': 'GOLD', 'csv': 'hkex.csv',
       'cols': ['new_listings'], 'scale': 1.0, 'per_day': None, 'start': '2019-01',
       'funds': ('ipo_funds_hkdbn', 'HK$bn'),
       'note': '⚠ IPO 募资是暂定数，官方会上修 ⇒ 只填空不覆盖，且末月要标「暂定」'},
      {'key': 'sgx', 'disp': 'SGX', 'color': 'MBLUE', 'csv': 'sgx.csv',
       'cols': ['ipos_count'], 'scale': 1.0, 'per_day': None, 'start': '2015-01',
       'funds': ('ipo_funds_sgdmn', 'S$mn')},
      {'key': 'asx', 'disp': 'ASX', 'color': 'GREEN', 'csv': 'asx.csv',
       'cols': ['new_listed_entities'], 'scale': 1.0, 'per_day': None, 'start': '2016-01',
       'funds': ('capital_new_quoted_audmn', 'A$mn'),
       'note': '⚠ 上市实体含债券发行人，与 HKEX 的「新上市公司」口径不同，图注必写'},
      {'key': 'enx', 'disp': 'Euronext', 'color': 'NAVY', 'csv': 'enx.csv',
       'cols': ['issuers_equities'], 'scale': 1.0, 'per_day': None, 'start': '2018-01',
       'funds': ('money_raised_new_listings_eurm', '€mn'),
       'note': 'issuers_equities 是**存量家数**不是新增，与另三家的口径不同 ⇒ '
               '只与 funds 一起进募资图，不与 new_listings 同图'},
    ],
    'excluded': [
      ('ndaq', 'q_listed_cos_us / q_listed_total 是**季度**，不能插值成月度'),
      ('jpx', '第一版不做 new_listings（侦察稿已说明成本判断）'),
    ],
  },

  {
    'id': 'fn_index_aum', 'zh': '指数 IP 与挂钩资产（存量）', 'axis': 'function',
    'page': 'exchanges-products', 'unit': 'bn (own ccy)', 'share': 'none',
    'basis': ('挂钩自家指数的 ETF 资产。**全仓唯一一对真正同形的指数授权规模指标** —— '
              '与成交量池并置的意义在于：成交量是流量、AUM 是存量，'
              '同一轮行情里两者的弹性完全不同，只看成交量会把周期性误读成结构性。'),
    'denom': None,
    'head': ['msci', 'db1'],
    'members': [
      {'key': 'msci', 'disp': 'MSCI 挂钩 ETF AUM', 'color': 'NAVY', 'csv': 'msci.csv',
       'cols': ['aum_eop_usdbn'], 'scale': 1.0, 'per_day': None, 'start': '2008-12'},
      {'key': 'db1', 'disp': 'STOXX/DAX 挂钩 ETF AUM', 'color': 'GOLD', 'csv': 'db1.csv',
       'cols': ['aum_stoxx_dax_etf_eurbn'], 'scale': 1.0, 'per_day': None, 'start': '2012-01',
       'note': '⚠ €bn vs $bn，不折汇 ⇒ 只做指数化对照'},
    ],
    'excluded': [
      ('hkex', 'mktcap_hkdtn 是**市值**不是托管/AUM，只能并置不能相除'),
      ('db1_auc', 'auc_group_total_eurtn（Clearstream 托管）是慢腿列，'
                  '次月约 10 日才出 ⇒ 不得进横截面 panel，只放 db1 单公司页'),
    ],
  },

  {
    'id': 'fn_monopoly', 'zh': '结构对照：垄断 vs 竞争', 'axis': 'function',
    'page': 'exchanges-na', 'unit': 'pp', 'share': 'true',
    'basis': ('⚠ 这个池是**复核过程中被砍掉一半**的那个。原侦察稿设想「ICE 份额十五年跌 8pp '
              'vs HKEX 恒为 100%」是最直白的一张图，但 verify_ice.md §5 实锤：'
              'hkex.csv 里**根本没有任何份额字段**，"HKEX 恒为 100%" 是断言不是数据，'
              '要画只能在代码里硬写常数 1.0 —— 那不是数据看板该干的事。'
              '⇒ 本池只保留**有真实份额序列的成员**，垄断侧改用「可测量的替代指标」表达：'
              '不是画一条 100% 的直线，而是画垄断方的**量本身**与竞争方的**份额**并置，'
              '让读者看到「一个在争份额、一个只需要跟随市场」。'),
    'denom': None,
    'head': ['ice', 'cboe'],
    'members': [
      {'key': 'ice', 'disp': 'NYSE 美股现货份额', 'color': 'NAVY', 'csv': 'ice.csv',
       'cols': ['share_nyse_us_cash_matched'], 'scale': 100.0, 'per_day': None,
       'start': '2011-01',
       'note': '官方直接给，187/187 与自算一致（误差 <0.15pp）。2011-01 26.9% → 2026-07 19.1%'},
      {'key': 'ice2', 'disp': 'NYSE 美股期权份额', 'color': 'MBLUE', 'csv': 'ice.csv',
       'cols': ['share_nyse_equity_options'], 'scale': 100.0, 'per_day': None,
       'start': '2011-01', 'note': '24.5% → 21.1%'},
      {'key': 'miax', 'disp': 'MIAX 期权份额', 'color': 'GOLD', 'csv': 'miax.csv',
       'cols': ['share_multilist_options_pct'], 'scale': 1.0, 'per_day': None,
       'start': '2015-04',
       'note': '⚠ 官方自报份额，分母是 MIH 自己的行业 ADV。与 ICE 分母不同 ⇒ '
               '本页统一改用 ICE 行业分母重算，官方值只做校验'},
      {'key': 'ndaq', 'disp': 'Nasdaq 美股现货份额', 'color': 'GRAY', 'csv': 'ndaq.csv',
       'cols': ['us_matched_mktshare_pct'], 'scale': 1.0, 'per_day': None, 'start': '2010-10',
       'in_head': False,
       'note': '⚠ 来自 nasdaqtrader（次月第 10 个工作日）⇒ **慢腿，不进 head**；'
               '最新月用 ICE 分母现算，历史用官方值回补'},
    ],
  },
]
```

### 1.3 核心洞察在这个模型里怎么表达

用户点名的那句话 —— **同一家在不同池里可以同时是赢家和输家** —— 在模型里落在三个地方：

| 落点 | 机制 | 具体到 Cboe |
|---|---|---|
| 一家出现在多个池且 `share` 档次不同 | 同一个 key 出现在 `na_multilist_opt`（`share='true'`）与 `equity_index`（`share='none'`）里 | 多挂牌期权池：真份额，被 MIAX 从 92.6% 的对手位一路侵蚀；股指池：SPX/VIX 是独占产品，根本没有份额可言，只有增长 |
| `in_share: False` 开关 | 同一家在某池只做规模对照、不进份额分子 | MIAX 在 `ags` 池 `in_share=False`：进量级表，不进占比图 |
| 跨池份额变化矩阵（Exhibit，见 §三） | 行 = 交易所、列 = 池、格 = Δpp | Cboe 那一行会同时出现红格（多挂牌期权 −pp）与绿格（指数期权增长），一眼可见 |

---

## 二、呈现方式设计

### B.0 先解决一个会决定全部图型选择的约束：只有 6 个数据色

`C.*` 里能做数据色的是 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD，RED 是断点与截轴离群值专用。
12 家不可能一家一色 —— 而现有 `exchanges.py` 的注释明确写着「成员固定配色，一家一色，全页所有图一致」，
因为「横截面页读者是在几张图之间来回比谁是谁」。

**扩容后这条规矩必须改写成两条：**

1. **颜色在池内唯一，跨池不承诺一致。** 每池 ≤5 家 ⇒ 6 个色够用。页面顶部写明这一条。
2. **凡是要同时呈现 6 家以上的图，一律选「身份靠标签而不是靠颜色」的图型。**
   这不是妥协，恰恰指向了最适合 12 家的三种图型：`heat_matrix`（行标签就是身份）、
   `diverging_bars`（x 轴标签就是身份）、`grouped_bars`（x 轴标签就是身份）。

不建议扩色板。新增 4 个 `C.*` 要重过色盲安全校验，成本远高于收益，
且 12 条线的折线图**即使颜色够也读不出来** —— 颜色不是那张图的瓶颈。

---

### A. 增长的变化

指数化是跨币种唯一可比的口径，但它只回答「自基期以来累计谁跑赢」这一个问题，
而且**12 条线画不下**。下面五种是对它的补充，不是替代。

#### A1 ⭐ 增长动量矩阵 —— `heat_matrix`，行 = 交易所、列 = 月、格 = y/y（pp）

```python
{'n': 2, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct0z',
 'rows': ['CME', 'ICE', 'Cboe', 'Nasdaq', 'MIAX', 'TMX',
          'Euronext', 'DB1', 'HKEX', 'JPX', 'SGX', 'ASX'],
 'cols': [mlab(p) for p in IDX[-24:]],           # 近 24 个月
 'matrix': [[各家该月 y/y，缺失 None], ...],
 'cell_h': 20, 'row_lab_w': 62, 'row_head': '交易所',
 'legend': '头条序列 y/y'}
```

**为什么它比显而易见的做法更好。**
显而易见的做法是画 12 条 y/y 折线，或者按现在的样子画 12 张各自的年 × 月矩阵。
两条都不行：12 条线在一张图上互相穿插，而 12 张矩阵**颜色不可横向比** ——
现有页面的图注就明写着「Exhibit 9/10/11 三张图的颜色不能横向比，同一个绿在三张图里代表的增速不同」。
把「年」换成「交易所」之后，**整个矩阵只有一个 5/95 色标，颜色第一次跨家可比**：
同一个绿在 CME 行和在 SGX 行代表同一个增速。这是一次实打实的信息增量，而不是换个画法。
一屏之内可读出三件事：谁在加速（一行由浅转深）、哪个月是全行业事件（一整列同色）、
谁与行业脱钩（一行的颜色与其余各行反向）。

**失效条件。** (a) 单月极值会把色标压平 —— 引擎用 5/95 分位已缓解，但若某家单月 y/y 达 +400%
（港股 2024-09 那种整段行情不是单月离群，不受保护），整列会被拉偏，此时须给该家单独一行注释；
(b) 列超过 30 时格宽 < 20px，格内数字字号会被压到 5px 以下（引擎有自适应收缩，但会难读）⇒ **列上限 24**；
(c) 只对 y/y 有意义，不要拿它画水平值 —— 单位不可加总这条在矩阵里同样成立。

#### A2 累计增长排序 —— `diverging_bars`，x = 交易所、值 = 指数 − 100

```python
{'n': 3, 'kind': 'diverging_bars', 'full': True,
 'xlabels': ['ICE', 'CME', 'Cboe', ...],          # 已按值降序排好，Python 侧排
 'values': [+261, +172, +148, ..., -12],
 'fmt': 'pct0', 'ylab': f'自 {mlab(START)} 以来累计增长（%）'}
```

**为什么更好。** 12 条指数化折线要读「谁最高」，眼睛得跟着线走到最右端再比高低，
而末点标签在 12 条时必然互相遮挡（引擎的 `spreadY` 避让在 3 条时就已经有顶缘兜底的坑，
`LINE_H_ENDLABEL = 360` 那段注释就是为此写的）。排序柱把同一个信息压成一维，
且**顺序本身就是结论**。折线保留下来（A3）回答"路径"，柱回答"结果"。

**失效条件。** 丢掉全部路径信息 —— 一家先跌 60% 再涨 200% 与一路平稳上行，在这张图上完全相同。
所以它必须与 A3 成对出现，绝不能单独放。

#### A3 指数化折线，但**按池拆图、每图 ≤5 条** —— `lines`（`x:'long'`, `end_label`, `height:360`）

沿用现有 Exhibit 2 的全部参数。唯一的改动是：不再是「一张图放全部成员」，
而是**一池一张**。`end_label` 只在 ≤5 条时开 —— 引擎的末点标签避让在条数多时会把标签
收成一摞贴在右上角，那比不标更糟（现有代码注释已记录这个几何触发条件）。

#### A4 同比的分布与离散度 —— `range_band`

```python
{'n': 6, 'kind': 'range_band', 'full': True,
 'xlabels': XL25,
 'lo': [每月 12 家 y/y 的最小值], 'hi': [每月的最大值],
 'actual': [每月的中位数],
 'names': {'range': '12 家 y/y 的极差', 'actual': '中位数',
           'lo': '最慢的一家', 'hi': '最快的一家'},
 'fmt': 'pct0', 'ylab': '% y/y'}
```

**为什么更好。** 这是全套设计里信息密度最高的一张，也是**只有横截面页才画得出来的一张**：
它回答的不是「谁在涨」，而是「这一轮涨是不是大家一起涨」。带子收窄 = 行业贝塔（宏观波动率驱动，
个股选择不重要）；带子张开 = 个体阿尔法（份额、产品、法域的差异开始起作用）。
用 12 条折线去看这件事等于用眼睛做统计，看不出来。
`range_band` 本来是给"指引区间 vs 实际"设计的，但它的数据契约（`lo`/`hi`/`actual` 三个等长数组）
与"分布带 + 中位数"完全同构，**不需要改引擎**。

**失效条件。** (a) 成员少于 4 家时极差就是两个点的差，没有分布可言 ⇒ 只在 12 家总览页画，
不在单池页画；(b) 一家极端离群会把带子撑满整个画布，此时中位数线被压扁 ⇒
须同时给 `ycap` 与 `cap_note`，或改用 P10/P90 代替 min/max（Python 侧算，图型不变）。
建议第一版就用 **P10/P90 + 中位数**，把 min/max 留给表格视图。

#### A5 加速/减速（二阶）—— `diverging_bars`，值 = 本月 y/y − 3 个月前 y/y

```python
{'n': 7, 'kind': 'diverging_bars', 'full': True,
 'xlabels': [按值排序的 12 家], 'values': [Δpp],
 'fmt': 'pp1', 'ylab': 'y/y 的 3 个月变化（pp）'}
```

**为什么更好。** y/y 本身是一阶量，它的水平高低主要由**去年同月的基数**决定 ——
一家去年崩过的公司今年 y/y 必然好看，那不是经营改善。二阶量把基数效应差掉了：
`Δ(y/y)` 只有在**本期动量真的变了**的时候才动。这是从"谁在涨"跨到"谁在拐"的唯一一步。

**失效条件。** (a) 噪声放大 —— 二阶量的方差是一阶的两倍以上，单月读数不可信 ⇒
窗口必须取 3 个月而不是 1 个月，且图注要写明"3 个月是为了压噪声，不是任意选的"；
(b) 基数本身异常的月份（去年同月有一次性事件）会在今年制造一个假拐点 ⇒ 与 A1 的矩阵对照看。

#### A6 季节性剔除 —— `seasonality`，但只用在**唯一可加总的那条序列**上

```python
{'n': 9, 'kind': 'seasonality', 'full': True,
 'xlabels': XL13,
 'base': {'name': '过去 5 年同月均值', 'values': [...], 'color': 'GRAY'},
 'actual': {'name': '本期实际', 'values': [...], 'color': 'MBLUE'},
 'fmt': 'f1', 'ylab': '全美合并成交量（bn 股/日）'}
```

**为什么更好，以及为什么只有一条序列能用它。**
`seasonality` 要求灰蓝两根柱在同一量纲上并排 —— 那意味着**必须是一条水平值序列**，
不能是同比、不能是指数。12 家里没有任何两家的水平值可加总，
**唯一合法的对象是 ICE 带进来的行业分母**：`adv_tapeA/B/C_consolidated_mnsh` 之和
是真正的全美合并成交量，可加总、有 15 年历史、单位明确。
这张图回答的是"这个月的行业活跃度是季节性的还是真的"，
它是全页唯一一个不涉及"谁跑赢"、而涉及"池本身在不在长"的图。

**失效条件。** (a) 过去 5 年里含 2020 与 2021 两个极端年 ⇒ 均值被抬高，
须在 `base.name` 里写明 N 与窗口，且考虑改用中位数（Python 侧决定，图型不变）；
(b) 除这一条之外的任何序列都不要用它 —— 用在 y/y 上是拿季节性去比季节性，双重计数。

#### A7 长周期与近期双时窗 —— `qtr_bar`（长）+ `lines_endlabels`（近）

近期沿用现有的 25 个月 `lines_endlabels`。长周期改用 `qtr_bar`：

> **2026-08-19 注：本文里的 25 个月（`XL25` / `WIN_LINE = 25`）不是遗留物，别顺手改掉。**
> 2026-08-18 那一轮把「近 25 个月」统一改成「2016-01 起」，改的是**单公司页**
> （`build/single.py` 的 `WIN_FROM`、cboe / cme / hkex / cost / hood 的同名常量、
> mrbase 那 7 家的 `window.x_from`）。**横截面页不在那一轮的范围里** ——
> `build/exchanges_apac.py` 今天仍然是 `WIN_LINE = 25`，实测 `exchanges-apac.js`
> 的短窗口 x 轴就是 25 格（长历史图另有 `XL_LONG`，127 格）。
> 两类页的窗口本来就该分开定：单公司页比的是**一条序列自己的历史**，
> 横截面页比的是**几家在同一窗口内的相对位置**，后者窗口越长成员起点差异越碍事。


把 15 年 180 个月压成 60 根季度柱，比 180 个点的折线可读得多，且右轴可挂 y/y。

**必须在 Python 侧处理的一个坑：** `qtr_bar` 的语义是"月度汇总成季度"，
但我们的序列是 **ADV（日均）**，直接求和是错的 —— 必须按**交易日加权平均**。
各家的交易日列不同（`cme.trading_days` / `ice.trading_days_commod` 与 `trading_days_rates`
两行 187 个月里只有 69 个月相同 / `enx.trading_days_cash` 与 `trading_days_eqderiv` 分列），
所以加权用哪一列必须写进 POOLS 的 `per_day` 并在图注注明。
末季未满时 `partial_months` 必须给，引擎会自动作废那一点的 y/y。

---

### B. 市场份额变化

前提复述一遍：**只有 `na_cash` 与 `na_multilist_opt` 两个池能算真份额**，
其余只能算池内相对占比或干脆不算。下面五种按信息量排序。

#### B1 ⭐ 池内份额堆叠带 + 右轴池总量 —— `stacked_dual`

```python
{'n': 2, 'kind': 'stacked_dual', 'full': True, 'height': 320,
 'xlabels': XL25,                                 # 近 25 个月
 'stacks': [{'name': 'Cboe',   'color': 'MBLUE', 'values': [...]},
            {'name': 'MIAX',   'color': 'GOLD',  'values': [...]},
            {'name': 'NYSE',   'color': 'NAVY',  'values': [...]},
            {'name': '其余（Nasdaq / BOX / MEMX）', 'color': 'GRAY', 'values': [...]}],
 'line': {'name': '行业 ADV（RHS）', 'color': 'GREEN',
          'values': [ICE 行业分母], 'yfmt': 'f0c'},
 'bar_labels': False,                             # 25 根 × 4 段，段内标数值必然糊成一片
 'fmt': 'pct1', 'ylab': '池内份额（%）', 'ylab2': '行业 ADV（千张/日）'}
```

**为什么它比显而易见的做法更好。**
显而易见的做法是画 4 条份额折线。折线的问题不是不可读（4 条还行），
而是它**回答不了最关键的那个问题**：份额跌了，到底是自己丢了单，还是池子本身缩了？
堆叠带把 100% 填满，右轴那条线给出池的绝对大小 ——
"份额稳但线在跌"与"份额跌但线在涨"是两种完全相反的处境，折线图上长得一样。
**残差段（其余）是这张图的关键设计**：它不是编造出来的，它是恒等式
`1 − Σ已知成员份额` 的结果，而且它的宽度直接告诉读者"我们只覆盖了这个池的多少"。
没有残差段的堆叠份额图是在偷偷把分母改成"成员之和"，那正是 `share='pool'` 与 `share='true'` 的区别。

**失效条件。** (a) 残差 > 50% 时这张图就退化成"我们看不见大半个市场" ⇒
北美期权池残差约 54.5%（Nasdaq + BOX + MEMX），**必须把 Nasdaq 单拆出来**才有意义，
而 Nasdaq 的期权数含指数期权、口径不合 ⇒ 第一版残差就叫"其余"，
批 2 加入 Nasdaq 后要么找到它的 multilist 拆分、要么永远保留大残差并在图注写明；
(b) 引擎不支持 `stacked_dual` 截轴（"截一段堆叠柱等于把总量画错"），
所以右轴那条线若有极端月，只能靠 `ycap` 之外的办法处理，或者接受被压平；
(c) 25 根柱 × 4 段时段边界只有 1px，`bar_labels` 必须关。

#### B2 起止对照 —— `grouped_bars`，x = 交易所、两组 = 基期份额 / 当期份额

```python
{'n': 4, 'kind': 'grouped_bars', 'full': True,
 'xlabels': ['NYSE', 'Cboe', 'MIAX', 'Nasdaq', '其余'],
 'groups': [{'name': f'{mlab(BASE)} 份额', 'color': 'BLUE',  'values': [...]},
            {'name': f'{mlab(CUR)} 份额',  'color': 'NAVY',  'values': [...]}],
 'bar_labels': True,
 'fmt': 'pct1', 'ylab': '池内份额（%）',
 # ⚠ 刻意不给 line：Δpp 跨零会把左轴拉进负区（引擎的零点对齐规矩），
 #   柱子被压进上半张画布。Δpp 单独用 B3 画。
 'note': 'Δpp 见下一张 Exhibit'}
```

**为什么更好。** 折线要读"五年前 vs 现在"得在图上量两个高度差；
并排柱把这个差直接摆成两根柱的落差，且**保留了绝对水平** ——
一个从 24% 掉到 21% 与一个从 3% 掉到 0.5%，Δpp 分别是 −3 与 −2.5（差不多），
但业务含义天差地别（后者是被打没了）。B3 的 Δpp 柱丢掉这个信息，所以两张必须成对。

**失效条件。** 只有两个时点，中间的路径全丢；基期选择直接决定结论 ⇒
基期必须写进标题而不是图注，且与 A3 的指数化基期取同一个月。

#### B3 份额变化量排序 —— `diverging_bars`

```python
{'n': 5, 'kind': 'diverging_bars', 'full': True,
 'xlabels': [按 Δpp 降序的成员],
 'values': [Δpp, ...], 'fmt': 'pp1',
 'ylab': f'份额变化（pp，{mlab(BASE)} → {mlab(CUR)}）'}
```

**为什么更好。** 这是"谁赢了谁输了"唯一一眼可得的形式：正负分色（引擎自动 NAVY / RED），
排序即结论。份额是零和的，所以**这张图的正负两侧之和必须为 0** ——
这条恒等式可以写成 Python 侧的断言，是一个免费的护栏。

**失效条件。** (a) 只在**单一池、固定分母**内成立 —— 跨池比 Δpp 是错的（不同池的份额波动量级差一个数量级）；
(b) 窗口长度决定符号：12 个月和 60 个月的 Δpp 经常反号 ⇒ 窗口必须进标题。

#### B4 ⭐ 跨池份额矩阵 —— `heat_matrix`，行 = 交易所、列 = 池、格 = Δpp

```python
{'n': 10, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pp1',
 'rows': ['CME', 'ICE/NYSE', 'Cboe', 'Nasdaq', 'MIAX', 'TMX',
          'Euronext', 'DB1', 'HKEX', 'JPX', 'SGX', 'ASX'],
 'cols': ['北美现货*', '北美期权*', '欧洲现货', '欧洲衍生品',
          '亚太现货', '亚太衍生品', '利率', '股指', '单股期权'],
 'matrix': [[Δpp 或 None], ...],
 'cell_h': 22, 'row_lab_w': 70, 'row_head': '交易所',
 'legend': '池内占比变化（pp，近 12 个月）',
 'scale': 'per_col',                              # ← 需要引擎小改，见 §2.C
 'src_extra': '带 * 的两列是真份额（分母 = ICE 披露的行业总量）；'
              '其余列是**池内相对占比**（分母 = 该池成员之和），不是市场份额'}
```

**为什么它是整套设计的题眼。** 用户要的"同一家在不同池里同时是赢家和输家"，
在任何一种折线或柱状形式里都表达不出来 —— 因为那需要**同时呈现一家在 N 个池里的位置**。
矩阵是唯一能做到的：Cboe 那一行会同时有红格（北美期权被 MIAX 侵蚀）与绿格（其余池），
MIAX 那一行几乎全红（它只在一个池里存在，其余是空格），
而 ICE 那一行的北美现货格是长期深红 —— 十五年从 26.9% 跌到 19.1%。
**空格本身也是信息**：一行里有几个格 = 这家公司铺了多少条战线。

**失效条件与必须写明的限制。**
(a) **真份额与相对占比混在一张矩阵里**，不写清楚必被误读 ⇒ 列名加 `*` 标记 + `src_extra` 说明，
这是本设计里最需要人工审的一处；
(b) 各池的份额波动量级差一个数量级（北美现货年动 0.5pp、北美期权年动 3pp），
单一 5/95 色标会把现货那一列压成一片白 ⇒ 需要 `scale: 'per_col'`（见 §2.C）；
(c) 窗口固定 12 个月，不同池的成员起点不同（MIAX 现货 2020-12；TMX 现货 `pools.py` 里仍写 2021-08，序列本身 2026-08-18 起已到 2015-01）⇒
不满 12 个月的格子必须留 `None` 而不是用短窗口凑，宁可空一格。

#### B5 ⭐ 增长归因桥：池扩大 vs 份额转移 —— `bridge_bar`

恒等式：设 V = s × I（本家量 = 份额 × 行业量），则

```
ΔV  =  s₀·ΔI      +  I₀·Δs        +  Δs·ΔI
       ↑池扩大贡献    ↑份额转移贡献    ↑交叉项
```

```python
{'n': 6, 'kind': 'bridge_bar', 'full': True,
 'xlabels': ['NYSE', 'Cboe', 'MIAX', '其余'],     # x = 成员，不是月份
 'stacks': [{'name': '池扩大（行业量增长）', 'color': 'BLUE', 'values': [...]},
            {'name': '份额转移',            'color': 'NAVY', 'values': [...]},
            {'name': '交叉项',              'color': 'GRAY', 'values': [...]}],
 'net': {'name': 'ADV 净变化', 'values': [...]},   # 显式给，不让引擎求和
 'net_color': 'INK',
 'fmt': 'f0c', 'ylab': 'ADV 变化（千张/日，近 12 个月）'}
```

**为什么它比显而易见的做法更好，而且为什么它是全套里最值钱的一张。**
显而易见的做法是分别看"我的量涨了多少"和"我的份额动了多少"两张图，
读者得在脑子里做乘法才知道哪一个是主因。这张图把乘法做完了：
**一家 ADV 涨 20% 但份额跌 2pp，桥上会看到一根很高的蓝柱（水涨船高）和一根往下的深蓝柱（自己在丢单）** ——
"业绩好但生意在变差"这件事，只有这张图说得清。反过来，MIAX 那一列会是
蓝柱中等、深蓝柱很高 —— 它的增长主要来自抢单而不是行业。
这正是买方最想知道的那个区分：**周期性 vs 结构性**。

**失效条件。**
(a) **只在有真分母的两个池里成立** —— 用池内相对占比做这个分解，
"池扩大"那一项会变成"其余成员的合计变化"，含义完全不同 ⇒ 严禁在 `share='pool'` 的池里画；
(b) 交叉项 `Δs·ΔI` 在变化量大时会显著（两位数增长 × 两位数份额变动），
不能省略也不能并进另两项，否则恒等式不闭合 ⇒ 单独一段，且颜色用 GRAY 弱化；
(c) 窗口越长交叉项越大，12 个月是可接受上限；
(d) `net` 必须显式给（引擎的 `bridgeNet` 只在没给时求和），因为这里的 net 是
`V₁ − V₀` 的真值，与三段之和在浮点上可能差最后一位。

#### B6 份额 × take rate 的二维定位 —— 【需要新增 kind `scatter_xy`】

这是唯一一个**现有 17 种 kind 做不到**的效果。

要回答的问题是"MIAX 的份额上行是靠降价买来的，还是量价齐升"。
数据是现成的：`na_multilist_opt.rpc` 三家的 RPC 与三家的份额，
`rpc_multilist_options_usd` 在 Cboe 与 MIAX 是**逐字同定义**的（复核已实锤）。
但这是两个测量量互相对照，不是一个量随时间变化 —— 所有 17 种 kind 的 x 轴都是"期间"，
没有一种能把 x 轴换成另一个测量量。用双轴折线勉强凑，读者仍然要在脑子里做配对。

**数据契约（建议实现）：**

```js
{ n: 10, kind: 'scatter_xy', full: true, height: 340,
  title: '份额 vs take rate：谁在用价格买份额',
  points: [ { name: 'Cboe', color: 'MBLUE', x: -1.8, y: -0.004 },
            { name: 'MIAX', color: 'GOLD',  x: +3.1, y: +0.017 },
            { name: 'NYSE', color: 'NAVY',  x: -0.6, y: +0.002 } ],
  xlab: '多挂牌期权份额变化（pp，近 12 个月）',
  ylab: 'RPC 变化（$/张，近 12 个月）',
  xfmt: 'pp1', yfmt: 'usd3',
  quadrant: { x: 0, y: 0 },                    // 十字参考线，可省
  quad_labels: ['量价齐升', '以价换量', '份额与价同跌', '守价失量'],
  trail: [ { name: 'MIAX', color: 'GOLD',
             values: [[0.4,0.002],[1.2,0.008],[3.1,0.017]] } ]   // 可选拖尾，最近 N 期
}
```

**实现要点（约 120 行，风险低）：**

- x 与 y 各自走一遍现有的 `ticks()`，不共用量程；两轴都要能跨零。
- 点半径固定 4.5px，`fill` 用 `col(p.color)`，`stroke: C.WHITE, stroke-width: 1`（重叠时仍分得开）。
- 点标签用现有的 `txt()` 并保留 `halo`（白描边打底）—— 这正是引擎里那段注释说的
  "描边比把线画在标签下面更彻底"，散点图上标签互压比折线更严重。
  避让只做一维：**同一象限内按 y 排序后上下推开 11px**，不做二维力导（不值得）。
- 十字参考线用 `C.GRID`、`stroke-dasharray: '4 3'`；象限文字用 `size: 8, style: 'italic', fill: C.AXIS`，
  画在四角内缩 6px 处。
- `trail` 用同色 1.2px 折线 + 末点实心、前点空心，画在点之下。
- 表格视图：`name / x / y` 三列，走 `PRECISE` 映射升一位小数（与其余 kind 一致）。
- **不支持** `break_at`（没有连续 x 轴）；`ycap`/`xcap` 第一版不做，越界点直接改用
  `cap_note` 文字说明（散点的离群点数量少，值得单独标）。
- `xlabels` 不用，与 `heat_matrix` 一样在 `draw()` 里提前分流自己排版。

**失效条件。** (a) 点数 > 8 时标签必然互压 ⇒ 只用在单池（≤5 家）；
(b) 两轴都是"变化量"时，基期选择同时影响 x 与 y，结论对基期极敏感 ⇒
必须给 `trail` 展示路径，或至少在图注写明换基期会怎样；
(c) MIAX 的 RPC 只有 18 个月 ⇒ 2026-12 之前这张图的窗口只能是 12 个月且刚好卡满，
在那之前图注要写明"窗口受 MIAX RPC 序列长度所限"。

### 2.C 需要的引擎改动清单（只有两处，都很小）

| 改动 | 类型 | 用在哪 | 规模 | 不做的代价 |
|---|---|---|---|---|
| 新增 kind `scatter_xy` | 新 kind | B6 | 约 120 行 + 表格视图 20 行 | 「份额上行是不是靠降价买的」这个问题画不出来，只能写进图注文字 |
| `heat_matrix` 增加 `scale: 'per_col'` | 现有 kind 加一个可选字段 | B4 | 约 15 行（`heatScale` 改成按列各算一次 5/95，`at(v, colIdx)`）+ 图例文案 | 跨池矩阵里北美现货那一列（年动 0.5pp）会被期权池（年动 3pp）压成一片白，整列变成噪声 |

除这两处外，**A1–A7、B1–B5 全部用现有 17 种 kind 原样实现**，不需要改引擎。

有三处是"看起来要改、其实不用改"的，记在这里免得下一个人重复判断：

- **12 家份额折线**：不改引擎，改图型（B1/B3/B4）。加 12 个颜色是错误的解法。
- **`range_band` 用来画分布带**：字段完全同构（`lo`/`hi`/`actual`），只是语义换了，不需要改。
- **短历史成员不拖垮共同窗口**：`exchanges.py:240-243` 本来就只查 `HEAD` 三条列的空洞，
  把 `head` 与 `members` 分开之后天然兼容，一行都不用改。

---

## 三、页面结构

### 3.1 拆几张页，以及为什么

**建议拆成 4 张。理由按重要性排序：**

1. **发布节奏分层，这是最硬的一条。** 各家实测发布日（月末后第几天）：

   | 次月第 1–6 天 | 次月第 8–10 天 | 次月第 13–14 天 |
   |---|---|---|
   | CME 2 · ICE 3 · Cboe 3 · MIAX 3–5 · TMX(MX) 1–4 · DB1(Eurex/Xetra) 1–4 · NDAQ(IR) 2–6 · JPX 第 5 个营业日 · ASX 3–8 | HKEX 10 · NDAQ(trader xlsx) 第 10 个工作日 | SGX 6–13 · Euronext 4–13 |

   12 家取 min ⇒ **整站每月要等到第 13–14 天**才发。而北美四家（ICE / Cboe / MIAX / NDAQ-IR）
   第 6 天就齐了。不拆页 = 每个月让最慢的两家把最快的池拖住整整一周，
   而那一周恰恰是月度数据最有价值的时候。

2. **分母性质不同，混在一页必被误读。** 只有北美两池有真分母。
   把"NYSE 份额 19.1%"和"Euronext 在三家里占 40%"放在同一页的相邻两张图上，
   读者没有任何视觉线索区分它们 —— 前者是市场份额，后者是我们自己框出来的三家之和。
   **拆页是最便宜的隔离手段**，比在每张图上加免责说明可靠得多。

3. **"一张图 ≤5 条线"落到版面上就是拆页。** 见 §B.0，这是颜色约束的必然结果。

4. **分批上线要求单页可独立 skip。** "算不出共同最新月就不写半张页"这条规矩，
   在单页 12 成员时意味着"少一家整站没有横截面"。拆页之后，
   批 1 只上 ICE，`/exchanges-na/` 就能发，其余三页照常 skip 并打印原因。

**不建议按题面提示的 `/exchanges-options/` + `/exchanges-derivatives/` 那样拆**，
理由是那种切法把"北美期权"（有真分母、发布快）与"欧洲/亚太期权"（无分母、发布慢）
切进了同一页，上面 1、2 两条约束一条都解决不了。**按「分母性质 × 发布节奏」拆，
恰好与「地理 → 标的」的池轴大体重合，这不是巧合** —— 交易所的竞争本来就是按法域分割的。

| 页 | 成员 | 池 | 门槛（月末后） | 这一页只回答 |
|---|---|---|---|---|
| `/exchanges/` 总览 | 12 家 | 无（只用各家头条序列） | 第 13–14 天 | 12 家里谁在跑赢、谁在拐点 |
| `/exchanges-na/` 北美竞争 | ICE / Cboe / MIAX / NDAQ /（TMX 对照） | `na_cash` `na_multilist_opt` `na_total_opt` `fn_monopoly` | **第 6 天** | 真份额在怎么转移，增长里哪部分是抢来的 |
| `/exchanges-intl/` 欧洲与亚太 | ENX / DB1 / Cboe(EU) / HKEX / JPX / SGX / ASX | `eu_cash` `eu_deriv` `apac_cash` `apac_deriv` `fn_listing` | 第 13–14 天 | 各法域主场的量在怎么长，上市与成交是不是同向 |
| `/exchanges-products/` 标的池 | 全部 12 家（按池选） | `rates` `equity_index` `single_stock_etf_opt` `energy` `ags` `fx_futures` `fx_spot_ecn` `fn_index_aum` | 第 13–14 天 | 同一类标的在不同法域的周期错位 |

### 3.2 `/exchanges/` 总览页 exhibit 序列

| # | 标题 | kind | 数据来源列 | 回答什么问题 |
|---|---|---|---|---|
| 1 | 交易所组横截面 —— 共同最新月汇总表 | （HTML 表，非 kind） | 12 家头条序列各自的水平值 + y/y + 3Y %ile，按北美/欧洲/亚太分组 | 本月各家的读数与它在自己 3 年历史里的位置 |
| 2 | 增长动量矩阵：12 家 × 近 24 个月 y/y | `heat_matrix` | 各家头条序列的 y/y（`cme.adv_total_kcontracts` / `ice.adv_futures_options_kcontracts` / `cboe.adv_us_options_kcontracts` / `hkex.adt_hkdbn` / …） | 谁在加速、哪个月是全行业事件、谁与行业脱钩 |
| 3 | 自共同基期以来累计增长排序 | `diverging_bars` | 各家头条序列指数化后 −100，Python 侧排序 | 长周期谁跑赢（结果） |
| 4 | 指数化曲线 —— 北美 + 欧洲 | `lines`（`x:'long'`, `end_label`, h=360） | 同上，取 ICE / Cboe / NDAQ / MIAX / ENX（5 条） | 长周期谁跑赢（路径） |
| 5 | 指数化曲线 —— 亚太 + CME | `lines`（同上） | CME / HKEX / JPX / SGX / ASX（5 条） | 同上，另一半成员 |
| 6 | 12 家 y/y 的分布带（P10–P90 + 中位数） | `range_band` | 每月对 12 条 y/y 取分位，Python 侧算 | 这一轮是行业贝塔还是个体阿尔法 |
| 7 | 增长的二阶：y/y 的 3 个月变化 | `diverging_bars` | 各家 y/y 序列的 3 个月差分（pp） | 谁在拐点上（把基数效应差掉） |
| 8 | 行业池总量：全美合并成交量，季度 + y/y | `qtr_bar` | `ice.adv_tapeA/B/C_consolidated_mnsh`（交易日加权），右轴 y/y | 池本身在不在长（唯一可加总的真实总量） |
| 9 | 行业池总量的季节性：过去 5 年同月均值 vs 今年 | `seasonality` | 同上 | 这个月的活跃度是季节性的还是真的 |
| 10 | ⭐ 跨池占比变化矩阵：行=交易所、列=池 | `heat_matrix`（`scale:'per_col'`） | 各池的份额/池内占比 Δpp（近 12 个月） | **同一家在不同池里同时是赢家和输家** |
| 11 | 近 13 个月各家原始指标核对表 | （HTML 表） | 各家官方原始单位，不换算 | 逐条与官方披露核对 |

### 3.3 `/exchanges-na/` 北美竞争页 exhibit 序列（信息量最高的一页）

| # | 标题 | kind | 数据来源列 | 回答什么问题 |
|---|---|---|---|---|
| 1 | 北美两池汇总表 | （HTML 表） | 各家 ADV + 真份额 + Δpp + RPC | 本月的分池读数 |
| 2 | ⭐ 多重挂牌期权池：份额堆叠带 + 右轴行业 ADV | `stacked_dual` | 分子 `cboe/miax.adv_multilist_options_kcontracts`、`ice.adv_nyse_equity_options_kcontracts`；分母 `ice.adv_us_equity_options_industry_kcontracts`；残差 = 1−Σ | 份额在怎么转移，同时池子本身在不在长 |
| 3 | 美股现货池：份额堆叠带 + 右轴全美合并 ADV | `stacked_dual` | 分子 ICE tape A+B+C matched / `cboe.adv_us_equities_matched_shares_bn` / `ndaq.vol_us_matched_shares_mm÷交易日` / `miax.adv_equities_mnshares`；分母 ICE consolidated | 同上，现货侧 |
| 4 | 期权池份额：基期 vs 当期 | `grouped_bars`（不给 `line`） | 同 Ex2 的份额序列取两个时点 | 五年前 vs 现在的绝对水平落差 |
| 5 | 现货池份额：基期 vs 当期 | `grouped_bars` | 同 Ex3 | 同上（与 Ex4 成对半栏） |
| 6 | 期权池份额变化排序（近 12 个月） | `diverging_bars` | Δpp，Python 侧排序；正负两侧之和须为 0（断言） | 谁赢了谁输了 |
| 7 | 现货池份额变化排序 | `diverging_bars` | 同上 | 同上（与 Ex6 成对） |
| 8 | ⭐ 期权池增长归因桥：池扩大 vs 份额转移 | `bridge_bar` | `s₀·ΔI` / `I₀·Δs` / `Δs·ΔI`，net = ΔADV | 增长是水涨船高还是抢来的 |
| 9 | 现货池增长归因桥 | `bridge_bar` | 同上 | 同上 |
| 10 | ⭐ Cboe 的双重身份：被侵蚀的一半 vs 独占的一半 | `bar_line_dual` | 柱 = `cboe` 多挂牌期权真份额（%，左轴）；线 = `cboe.adv_index_options_kcontracts` 指数化（右轴） | 同一家公司在两个池里同时输和赢 |
| 11 | take rate：Cboe vs MIAX vs NYSE | `lines_endlabels` | `cboe/miax.rpc_multilist_options_usd`、`ice.rpc_nyse_equity_options_usd`，截齐到三家都有值的月 | 抢份额有没有付出价格代价 |
| 12 | ⭐ 份额 vs take rate 二维定位 | **`scatter_xy`（新增）** | x = Δ份额（pp），y = ΔRPC（$/张），点 = 各家 | 是量价齐升还是以价换量 |
| 13 | 份额变化矩阵：行=各家、列=近 24 个月 | `heat_matrix` | 期权池月度 Δpp | 份额转移是持续的还是一次性的 |
| 14 | 结构对照：NYSE 十五年份额下滑 | `lines`（`x:'long'`, h=360） | `ice.share_nyse_us_cash_matched`、`ice.share_nyse_equity_options`、`miax` 用 ICE 分母重算 | 竞争性市场里"国家级交易所"的份额长期走向 |
| 15 | 近 13 个月原始指标核对表 | （HTML 表） | 官方原始单位 | 逐条核对 |

Ex10 与 Ex12 是这一页的题眼，Ex8/Ex9 是信息量最高的两张。

### 3.4 `/exchanges-intl/` 与 `/exchanges-products/` 序列（结构相同，只列骨架）

> `/exchanges-intl/` 这一页**没有按本节的形态留存**：它先建出来，随后被拆成
> `/exchanges-eu/` 与 `/exchanges-apac/`，合页已于 2026-08-06 删除（见文首追记）。
> 下面的骨架读作设计原稿。

`/exchanges-intl/`：Ex1 汇总表 → Ex2 欧洲现货**水平值**折线（全仓唯一可比水平的池，€bn/日，
`lines` + `end_label`）→ Ex3 欧洲现货池内相对占比堆叠带（`stacked_dual`，图注写明分母是三家之和）
→ Ex4 欧洲衍生品指数化 → Ex5 亚太现货指数化（2019-01=100）→ Ex6 亚太衍生品指数化（统一千张）
→ Ex7 亚太 y/y 分布带（`range_band`）→ Ex8 上市家数跨家直比（`grouped_bars`，纯计数可比）
→ Ex9 募资额指数化（各家本币）→ Ex10 y/y 矩阵（7 家 × 24 月）→ Ex11 核对表。

`/exchanges-products/`：Ex1 汇总表（按池分组）→ Ex2 利率池指数化（5 条：美/欧/欧/加/日）
→ Ex3 利率池 y/y 矩阵 → Ex4 股指池指数化（6 条，须拆两张半栏）→ Ex6 能源池：Brent vs WTI
指数化 + OI 对照（`lines`，OI 须先把 ICE 的千张 ×1000）→ Ex7 单股期权池指数化
→ Ex8 FX 期货 vs FX 即期两张（严格分图，`lines`）→ Ex9 指数 IP 与挂钩 AUM 指数化
（MSCI vs STOXX/DAX）→ Ex10 跨池 y/y 矩阵（行=交易所、列=标的池）→ Ex11 核对表。

---

## 四、实现路线图

排序依据 = 信息增量 ÷ 实现成本。成本档取侦察复核的判定（A = 直接实现，B = 有坑但可无人值守）。

| 批 | 新增成员 | 判定 | 解锁的池 | 信息增量 | 主要成本 |
|---|---|---|---|---|---|
| **1** | **ICE** | A | `na_cash`(真) `na_multilist_opt`(真) `energy` `rates` `equity_index` `fn_monopoly` | **最高**。一家解锁 6 个池，且是全仓**唯一的行业分母来源** —— 没有它，B1/B4/B5 三种图型一张都画不出来 | 单个 xlsx、纯 urllib 3 个请求 5 秒、187 个月无断档。坑：OI 是千张（与 CME 差 1000 倍）、要避开 Cloudflare 拦的 HTML 页只走 feed |
| **2** | **MIAX** | B | `na_multilist_opt` 补齐对手方 + `fn_monopoly` 竞争侧 | **兑现题眼**：Cboe 在多挂牌期权池被侵蚀（份额 7.4%→17.9%），全仓唯一一对逐字同定义的 RPC | PDF 按 x 坐标分桶（按 token 顺序会静默把 53,135 读成 3,135，错 17 倍）；RPC 只有 18 个月，2026-12 前做不了同比 |
| **3** | **Euronext** | A | `eu_cash`(与仓内 Cboe 立即成池) `eu_deriv` `fx_spot_ecn` `ags` `fn_listing` | 与 Cboe 在**欧洲现货**（同币同单位同口径，2026-06 实测 15.52 vs 14.95）与 **FX 即期**（同为 ECN）各成一对，是全仓两处最干净的头对头 | 单个 xlsx 裸奔可取、174 个月零断档。坑：Athex 并表（单股衍生品 2025-11 有 3-6 倍假跳，必须用 legacy 口径）、四条断点竖线 |
| **4** | **JPX + SGX** | A / B | `apac_cash`(4 家齐) `apac_deriv` `rates` `equity_index` `fx_futures` | 亚太现货池从"只有 HKEX 一家"变成 4 家；JPX 与 HKEX 是全仓最干净的一对现货对照 | JPX 须**新建派生列** `adv_deriv_total_lgeq_kcontracts`（不建则排序翻转：原始张数下 JPX 是 HKEX 的 1.23 倍，当量口径下只有 0.27 倍）；SGX 是 PDF + 会轮换的 GraphQL id（失效时返回 200 + errors，静默失败） |
| **5** | **DB1 + NDAQ** | B / B | `eu_cash` 补第三家 · `eu_deriv` 加 Eurex（与 ICE 欧洲利率正面对上）· `na_cash`/`na_total_opt` 补 Nasdaq | Eurex 的 `oi_eurex_total_contracts` 2026-06 = 1.37 亿张，**反超 CME 的 1.28 亿** —— 这是真头对头。Nasdaq 把北美现货池的残差从 ~30% 压到 ~15% | DB1 要缝三个源两种节奏、需引入 `xlrd`，且**慢腿列绝不能进 panel**（`exchanges.py:242` 对空洞直接 raise）；~~NDAQ 三条腿只有 19 个月~~（**2026-08-19 已部分证伪**：只有 `vol_us_options_mmcontracts` 与 `vol_nordic_cash_value_usdbn` 还是 19 个月，`vol_nordic_derivs_mmcontracts` 已回到 2013-01 共 163 个月、`vol_us_cash_matched_mnsh` 回到 2010-10 共 190 个月；⚠ `build/pools.py` 里这两条腿的 `start` 仍写着 `'2025-01'`，池子还没吃上这段新历史 —— 这是**待办**，不是本次文档清账能改的），且交易日必须改用 MIAX 的（否则整页门槛被拖后一周） |
| **6** | **ASX + TMX** | B / B | `apac_cash`/`apac_deriv` 补第 4 家 · `rates` 加加元腿 · `single_stock_etf_opt` 加两家 | 最低。两家都只能贡献混合口径或短序列 | ASX 分品种只有 2 个月且不可回补，历史区间只能给混合期货 ADV（含电力/NZ，比例会漂移）；~~TMX 现货起点 2021-08，比 HKEX 还短 2 年 7 个月~~（**2026-08-18 已证伪**：TMX 现货经 CIRO 回填后是 2015-01 起 139 个月，比 HKEX 的 127 还长；⚠ `build/pools.py` 里 tmx 的 `start` 仍是 `'2021-08'`，待办同上），且 BOX 只有季度 —— **北美期权池永远缺 TMX** 这一条没变 |

### 4.1 各池"什么时候才凑得齐成员"

| 池 | 现在（3 家） | 批 1 后 | 批 2 后 | 批 3 后 | 批 4 后 | 批 5 后 | 批 6 后 |
|---|---|---|---|---|---|---|---|
| `na_cash` | ✗ | ✅ 2 家 + 真分母 | ✅ 3 家 | — | — | ✅ 4 家 | ✅ 5 家 |
| `na_multilist_opt` | ✗ | ✅ 2 家 + 真分母 | ✅ **3 家齐，题眼成立** | — | — | — | — |
| `eu_cash` | ✗ | ✗ | ✗ | ✅ 2 家 | — | ✅ 3 家齐 | — |
| `eu_deriv` | ✗ | 半（ICE 单腿） | — | ✅ 2 家 | — | ✅ 3 家齐 | — |
| `apac_cash` | 半（HKEX 单家） | — | — | — | ✅ 3 家 | — | ✅ 4 家齐 |
| `apac_deriv` | 半 | — | — | — | ✅ 3 家 | — | ✅ 4 家齐 |
| `rates` | 半（CME 单腿） | ✅ 2 家 | — | — | ✅ 3 家 | ✅ 4 家 | ✅ 5 家齐 |
| `equity_index` | ✅ 2 家 | ✅ 3 家 | — | ✅ 4 家 | ✅ 5 家 | ✅ 6 家齐 | — |
| `energy` | 半 | ✅ **2 家齐（Brent vs WTI）** | — | — | ✅ 3 家 | — | — |
| `fx_spot_ecn` | 半 | — | — | ✅ **2 家齐** | — | ✅ 3 家 | — |
| `fn_monopoly` | ✗ | ✅ 成立（ICE 两条份额线） | ✅ 加竞争侧 | — | — | ✅ 加 Nasdaq | — |
| `fn_index_aum` | 半（MSCI 单家） | — | — | — | — | ✅ 2 家齐 | — |

### 4.2 页面上线时点

| 页 | 最早可发 | 条件 |
|---|---|---|
| `/exchanges-na/` | **批 1 之后**（只有 ICE + Cboe 两家时就能发） | ICE 带来的两个真分母使 B1/B3/B5 立即可画；残差段先叫"其余"，批 2 加 MIAX 后拆细 |
| `/exchanges-products/` | 批 1 之后（先只上 `energy` + `rates` 两池） | 池是可增量添加的，一池一节，不必等全部标的池齐 |
| `/exchanges-intl/` | 批 3 之后（欧洲两家先成页），批 4 补亚太 | 在此之前 `apac_cash` 只有 HKEX 一家，画不成横截面 |
| `/exchanges/` 总览 | **最后**（批 6 之后才是真正的 12 家） | 但可以从批 1 起就发"当前成员数"的版本 —— A1/A2/A4/A5 的图型对成员数不敏感，行数少一行而已；抬头要写清"本页当前 N 家" |

### 4.3 与现有 `/exchanges/` 的迁移关系

现在这张 CME / Cboe / HKEX 页的 11 张图，扩容后的去向：

| 现有 | 去向 |
|---|---|
| Ex1 汇总表 | 拆到四页各自的 Ex1，行按池分组 |
| Ex2 指数化 | → 总览 Ex4/Ex5（按池拆成两张，各 ≤5 条） |
| Ex3–6 同比四张（按量级拆图） | → 总览 Ex2 的动量矩阵**取代**。四张拆图是"三条线量程差 2.7 倍"逼出来的权宜之计；12 家时量程差只会更大，继续拆下去要拆成 6 张 —— 矩阵一张就够，且颜色跨家可比 |
| Ex7 Mix quality（高费率品种占比） | → `/exchanges-na/` 的 take rate 节（Ex11/Ex12），并升级成真 RPC 而不是品种占比 |
| Ex8 衍生品指数化 | → `/exchanges-products/` 各标的池 |
| Ex9–11 三张 y/y 热力矩阵（各家一张） | **合并成一张**（总览 Ex2）。原图注承认"三张图颜色不能横向比"，那正是这次要消掉的缺陷 |
| Ex12 核对表 | 每页各留一张，只列本页成员 |

---

## 五、三条给实现阶段的硬提醒

1. **分母二选一必须先定死。** 北美期权池有两个候选分母
   （`ice.adv_us_equity_options_industry_kcontracts` 与 `miax.industry_adv_options_kcontracts`），
   两条并存会造出两套份额、两套 Δpp、两套归因桥。建议用 ICE 那个（历史 187 个月 vs MIAX 的 18 个月，
   且 ICE 官方直接给 `share_nyse_equity_options` 可自校验），MIAX 的自报份额只做交叉核对。

2. **交易日列必须写进 POOLS 而不是散在各处。** 至少四家的原始值是**月度总量**不是 ADV
   （NDAQ 全部、SGX 分产品、TMX 现货、ASX 部分），不除交易日会比同行大约 20 倍；
   而各家的交易日列口径还不同（ICE 的商品与利率两行 187 个月里只有 69 个月相同）。
   `per_day` 这个字段就是为此存在的，不要在 build 脚本里临时决定。

3. **不要为了"图好看"去补一条数据里没有的线。** 复核已经砍掉了一个这样的设计
   （"HKEX 份额恒为 100%"—— `hkex.csv` 里根本没有份额字段，画它只能硬写常数 1.0）。
   本设计里所有 `share='true'` 的池都有官方披露的分母，`share='pool'` 的池在图注里
   点名分母是谁，`share='none'` 的池一个占比数字都不出现。这条是这套设计的底线。
