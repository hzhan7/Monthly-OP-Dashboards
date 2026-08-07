# 验收报告：build/pools.py · build/notional.py · build/test_pools.py

验收人：独立验收 agent　｜　日期：2026-08-06　｜　仓库：`/Users/hainan/Projects/monthly-op-dashboards`
被验对象 md5：`pools.py = 8dded2c606e5961929f53af200c047ce`（验收全程未变）

## 结论：**不通过**

理由只有一条，但是硬的：**交付的测试套件在当前仓库里跑不过**（`FAILED (failures=1)`）。
交付时它是绿的，因为它依赖的 `series/enx.csv` 当时还不存在，而
`check_columns()` 把「CSV 还没建」记成 pending 而不是错。文件在 15:41 落地，
pools.py 声明的 3 个 enx 列当场对不上。

需要强调的是：**这个 agent 自己声称的每一个对账数字，我全部独立复现，并且逐位相符。**
我另外从官方源重新下载/重新解析了一遍，也全部相符，还额外找到两条它没声称、
但同样成立的独立交叉验证。数据侧没有造假。不通过是卡在与兄弟交付物的 schema 契约上。

---

## 一、我实际跑出来的输出

Python 3.12.12，`cd /Users/hainan/Projects/monthly-op-dashboards`。

### 1. `python3 build/pools.py` — exit 0

```
POOLS: 17 个池 / 61 个成员位 / 48 个 product_id
PRODUCTS 清单: 48 个（contract_specs.csv 必须逐个填齐）
validate(): 全过

池                      页                  share  levels dual  deflator    flow       fx   成员   产品
na_cash                exchanges-na       true   True   True  base_price  per_day    avg  5    2
na_multilist_opt       exchanges-na       true   True   True  base_price  per_day    avg  3    1
na_total_opt           exchanges-na       pool   True   False base_price  per_day    avg  3    3
...（17 行全部打出）

列名核对：已建 CSV 里核了 42 个 (表,列)，3 处对不上；6 个 CSV 还没建
  ✗ series/enx.csv 没有列 'adv_commodity_deriv_kcontracts'（POOLS 里引用了它）
  ✗ series/enx.csv 没有列 'adv_index_deriv_kcontracts'（POOLS 里引用了它）
  ✗ series/enx.csv 没有列 'adv_singlestock_deriv_legacy_kcontracts'（POOLS 里引用了它）
  待建：asx.csv, db1.csv, jpx.csv, ndaq.csv, sgx.csv, tmx.csv

规格表：73 个产品已入库，35 个待实测
```

### 2. `python3 build/notional.py` — exit 0

```
规格表: 73 条
汇率表: 5180 条
价格表: 缺 series/prices.csv —— 只有「当期名义额」需要它；定基名义额不需要…
  币种 10 个：AUD, BRL, CAD, CHF, EUR, GBP, HKD, JPY, SEK, SGD
  月份 259 个：2005-01 – 2026-07
  基期 2019-01 的汇率（1 单位外币 = 多少美元）：
    EUR  avg=1.141640909090909      eom=1.1488
    JPY  avg=0.009181686095406594   eom=0.009204390673824213
    HKD  avg=0.1275184987405082     eom=0.12745043655768443
    …
```

### 3. `python3 build/test_pools.py`

- **交付当时（15:35，enx.csv/miax.csv/contract_specs.csv 都还没落地）**：`Ran 48 tests … OK`
- **当前（15:46）**：`Ran 48 tests … FAILED (failures=1)`

```
FAIL: test_all_declared_columns_exist_in_built_csvs
AssertionError: Lists differ: ["series/enx.csv 没有列 'adv_commodity_deriv_…"] != []
```

对账那两条仍然是绿的，且数字与它自称的完全一致：

```
  自报份额对账：
    ✓ na_cash.ice          187 月 中位0.027 最大0.072pp(2017-12) 容差0.10
    ✓ na_multilist_opt.ice 187 月 中位0.022 最大0.051pp(2016-09) 容差0.10
```

---

## 二、幂等测试：**通过**

三个脚本连跑两轮，对 `series/ + data/ + build/` 全部 77 个 csv/js/py 文件取 md5：

```
snap1 vs snap2  → SAME
snap2 vs snap3  → SAME
stdout run1 vs run2 → POOLS_SAME / NOTIONAL_SAME / TEST_SAME
```

三个文件里唯一的 `open(..., 'w')` 在 `test_pools.py:69`，写的是
`tempfile.mkdtemp(prefix='pools_fixture_')` 下的合成夹具，不碰仓库。
三个模块都是纯声明 + 纯函数，不写任何产出物。

---

## 三、对账复算：**全部逐位相符，并且我从官方源重取了原值**

### 3.1 重新下载 ICE 官方工作簿（一手源，非缓存）

从 ICE 自己的 IR CDN 直取（`s2.q4cdn.com/154085107/`，站点号是 ICE 的 Q4 站点，
不是第三方聚合站）：

```
GET https://s2.q4cdn.com/154085107/files/doc_downloads/2026/07/2011-2026-Monthly-Stats-July-2026_vF.xlsx
200 / 377,178 B / Last-Modified: Wed, 05 Aug 2026 12:30:32 GMT
sha256 b091b514d189c979bf0808c0e62f625f93f8618b75f1d8e7ccb7645c73669a41
   ==  cache/ice_monthly_stats.xlsx 逐字节相同
```

然后用**我自己写的 openpyxl 解析**（没有调用它的 `fetch/ice.py`），
定位 `Cash Products` 表头行第 4 行里 `2026-07-01` 那一列（第 251 列）：

| 行 | 标签 | 值 |
|---|---|---|
| 11 | Total NYSE Listed Consolidated Volume | 5267 |
| 17 | Total NYSE Arca and American Listed Consolidated Volume | 3760 |
| 23 | Total Nasdaq Listed Consolidated Volume | 8410 |
| 10/16/22 | Matched Volume（Tape A/B/C） | 1534 / 738 / 1057 |
| 26 | TOTAL U.S. Cash Market Share Matched | 0.191 |

- 分母 5267+3760+8410 = **17,437 mn = 17.437 bn 股/日** — 它写 17.437 ✅
- 分子 1534+738+1057 = **3,329 mn = 3.329 bn 股/日** — 它写 3.329 ✅
- 自算份额 = 0.19091586855537077 = 19.0916%，自报 0.191 → 差 **0.008413 pp**
  — 它写 0.0084pp ✅

`US Equity Options` 表同列：NYSE 13,614k / Total Equity Options 64,394k /
NYSE Share of Group Total 0.211。13614/64394 = 21.1417% ✅

（顺带证伪一个可能的误读：`Total Equity Options` 确实是**行业**总量不是 ICE 集团总量 ——
2011-01 那列 4350/17740 = 24.5%，正是当年 NYSE Amex+Arca 的行业份额。）

### 3.2 重新解析 Cboe 官方工作簿

`cache/July-2026-Monthly-Volume-Statistics-Xlsx-.xlsx`（A2 = "Updated on August 5, 2026"），
Jul-26 列（第 8 列）：

- 行 13 Multiply-listed options ADV = **15,686.9725 k张/日** — 它写 15,687k ✅
  与 `series/cboe.csv` 的 `adv_multilist_options_kcontracts` 完全相同
- 15686.9725 / 64394 = **24.362%** — 它写 24.4% ✅
- NYSE 21.14% + Cboe 24.36% = **45.5%**，残差 **54.5%** ✅

### 3.3 两条它**没有**声称、我额外做的独立交叉验证（都成立）

Cboe 在同一份工作簿里自报市占率，可以拿来反过来验 ICE 的分母口径：

| 检查 | Cboe 自报 | 用 ICE 分母自算 | 差 |
|---|---|---|---|
| Cboe 多重挂牌期权份额（行 28） | 0.24360931 | 0.24362437 | **0.0015 pp** |
| Cboe 美股现货交易所份额（行 31） | 0.09008162 | 0.08998289 | **0.0099 pp** |

这两条比它自己给的证据更有力：它证明 **ICE 的 consolidated / industry 分母，
就是 Cboe 自己算份额时用的同一个分母**。na_multilist_opt 那条
「ICE 从未书面说明该分母是否含指数期权」的 caveat，实际上已经被这条 0.0015pp 的
一致性堵死了（若含指数期权，Cboe 那边会差 5pp 以上）。

### 3.4 187 个月全量重算（我自己写的循环，没调它的代码）

```
na_multilist_opt : n=187  median 0.0221 pp  max 0.05076 pp @ 2016-09
na_cash          : n=187  median 0.0273 pp  max 0.07192 pp @ 2017-12
```
与它写的「中位 0.022 / 最大 0.051 @2016-09」「中位 0.027 / 最大 0.072 @2017-12」
逐位一致。容差 0.10pp 确实是实测上界留一档，不是拍的。

### 3.5 定基汇率常数：从 ECB 官方 SDMX API 现取

`https://data-api.ecb.europa.eu/service/data/EXR/D.<CCY>.EUR.SP00.A?startPeriod=2019-01-01&endPeriod=2019-01-31`

| 币 | ECB 现取 avg | notional.py 打印 | ECB 现取 eom | notional.py |
|---|---|---|---|---|
| EUR | 1.141640909090909 | 1.141640909090909 ✅ | 1.1488 | 1.1488 ✅ |
| JPY | 0.009181686095406594 | 同 ✅ | 0.009204390673824213 | 同 ✅ |
| HKD | 0.127518498740508190 | 0.1275184987405082 ✅ | 0.127450436557684427 | 0.12745043655768443 ✅ |

22 个观测日，与 `obs_days` 一致。**定基那一行是真的，不是编的。**

### 3.6 其余抽查（要求抽 3 个，实抽 7 个，全中）

| 它写的 | 我的核验 | 结论 |
|---|---|---|
| ICE 10-K 自报 2025 年 NYSE 期权份额 18.9%「可反算」 | 从 ice.csv 反算 2025 = 18.9185% | ✅ |
| fn_monopoly「2011-01 26.9% → 2026-07 19.1%」 | 官方 xlsx 第 26 行：0.269 / 0.191 | ✅ |
| fn_monopoly「24.5% → 21.1%」 | 官方 xlsx：0.245 / 0.211 | ✅ |
| fx_spot_ecn「2026-06 Euronext 30.53 vs Cboe 64.27」 | enx.csv 30.52737839722727 / cboe.csv 64.266868 | ✅ |
| `verify_ice.md §5.1 / §5.2` 的原文 | /tmp/exch_recon/verify_ice.md 第 343、358 行逐字相符 | ✅ |

**没有找到任何凭记忆编造的数字。**

---

## 四、翻假：逐条结果

### (a) 整列全空 / 用 0 或 NaN 冒充缺失 —— 未发现
`ice.csv` / `fx.csv` / `cboe.csv` 逐列扫描：**0 个整列全空、0 个用 0 冒充缺失**。
唯一的空是 ice 的 CDS 三列前 24 个月（CDS Clearing 自 2013-01 才有，与 docstring 一致）
和 cboe 的 RPC 滞后一月 / XSP·MiniVIX 上市前。缺月一律留空，
`to_base_notional` 与 `apply_unit` 都是缺→`None`、交易日为 0 →`None`（不是 0、不是 inf），
有专门的测试 `test_holes_stay_holes` / `test_zero_trading_days_is_none_not_inf` 守着。

### (b) 无出处的魔数 —— 未发现
`PRODUCTS` 清单里**一个数字都没有**（`test_manifest_carries_no_numbers` 强制）。
全文件的数值字面量只有两类：
- 单位倍数 `K/MN/BN/TN = 1e3/1e6/1e9/1e12`（换算，不是实测值）
- 容差 `0.10 pp` ×4、`scale 1.0/100.0` ×4。0.10pp 的推导我在 §3.4 复算并复现；
  `scale=1.0` vs `100.0` 我对着 CSV 实际取值核过（ice 存小数 0.191 → ×100；
  miax/ndaq 列名带 `_pct` → ×1）。
`BASE_MONTH` 全仓只有一份（`notional.BASE_MONTH`，pools 直接引用），
`FLOW_TO_FX_BASIS`、`SRC_TO_KIND` 也都只有一份、pools 直接引用 —— 没有第二处副本。

### (c) docstring 声称的口径坑是否真的在代码里落地 —— 是
逐条对过，全部有代码或测试对应：

| 声称 | 落地位置 | 我的验证 |
|---|---|---|
| 混 deflator 的池不许算份额 | `validate()` 的 mixed 检查 | 有代码，测试 `test_no_mixed_price_basis_inside_a_pool` |
| avg/eom 不许手写字面量 | `fx_basis()` 唯一入口 + `FLOW_TO_FX_BASIS` | `test_pools_does_not_keep_its_own_copy_of_the_mapping` |
| 汇率缺月不许拿相邻月/1.0 顶 | `fx_rate()` 抛 `MissingFxMonth` | 有代码 |
| 汇率表取了倒数要当场炸 | `load_fx` 的 USD≠1.0 检查 | 有代码（但见 minor，真表里无 USD 列，此守卫在真数据上不触发） |
| 半个币种（有 avg 无 eom）要炸 | `load_fx` 的 `half` 检查 | 有代码 |
| 整表错位一行要炸 | `eom_date[:7] != month` | 有代码 |
| 基期不许一个产品一个样 | `load_specs` 逐行 `base_month != BASE_MONTH` → raise | 有代码 |
| 冗余列 `base_notional_per_unit_local` 必须校验 | `load_specs` 1e-9 相对误差 | 有代码 |
| 基期价格留空不许静默变 NaN | `MissingBasePrice` | 有代码 |
| 每池 ≤5 家 / 同池颜色唯一 / head ⊂ members | `validate()` | 有代码 |

### (d) 第三方聚合站冒充官方源 —— 未发现
三个交付文件里**一个 URL 都没有**。上游链路我实测过：
ICE = `ir.theice.com` + `s2.q4cdn.com/154085107/`（ICE 自己的 IR CDN）；
Cboe = `cdn.cboe.com`；FX = ECB SDMX。**没有 Yahoo / investing.com / Wind 一类聚合站。**
（`fetch/fx.py` 的交叉核对用了 FRED 分发的美联储 H.10 —— FRED 是圣路易斯联储，
仍属官方，且只做旁证不做数据源。）

### (e) 异常路径：抛异常还是静默写空 —— 抛
`SpecMissing` / `SpecInconsistent` / `UnknownProduct` / `MissingBasePrice` /
`MissingFxMonth` / `MissingPrice` / `ChainError` 全部 raise，且每一跳有独立异常类。
**唯一一处"静默"是有意的**：`check_columns()` 把「CSV 还没建」记成 pending 而不是错，
docstring 明写这是分批上线状态。这条设计恰恰是本次不通过的成因（见问题 1）。

### (f) 数字凭记忆编造 —— 未发现（见 §3.6，抽 7 中 7）

### (g) 我做的变异测试（它没做，我加的）
把 `series/ice.csv` 的 `adv_nyse_tapeA_matched_mnsh` 整列 **+2%**，
复制一份仓库重跑 `test_pools.py`：

```
FAIL: test_selfreported_share_reconciles_on_real_data
AssertionError: 0.4486 not less than or equal to 0.1 :
  na_cash.ice 自算份额与官方自报在 2011-02 差 0.4486 pp，超过容差 0.10 pp
```

**对账测试是有牙齿的，不是摆设。**

---

## 五、口径审查（本批次特有）

**换算链正确。** 逐条验：

1. **基期是否统一锁 2019-01** —— 是。`notional.BASE_MONTH = '2019-01'` 是全仓唯一定义
   （`pools.BASE_MONTH` 直接引用，没有第二份），并且在 `load_specs()` 里
   **逐行**强制 `base_month == BASE_MONTH`，不符即 `SpecInconsistent`。
   `test_base_month_must_be_locked` 覆盖。

2. **价格项是不是真的是常数** —— 是，而且是结构性保证不是约定：
   ```python
   def base_notional_per_unit_usd(product_id, specs, fx, basis='avg'):
       return (sp['base_notional_per_unit_local']
               * fx_rate(fx, sp['ccy'], BASE_MONTH, basis))   # ← 月份参数是 BASE_MONTH，不是 month
   def to_base_notional(series, ...):
       k = base_notional_per_unit_usd(...)                     # ← 循环外算一次
       return {m: (float(v) * k if _finite(v) else None) ...}  # ← 每月同乘一个 k
   ```
   函数签名里**根本没有 month 参数**，当期价格在类型上就进不来。
   当期口径是完全分开的 `current_notional_per_unit_usd(..., month, ...)`，
   走 `prices.csv`（该表尚未建），且 pools.py 与 notional.py 都写明它不进增长图/份额图。
   `test_base_notional_growth_equals_contract_growth` 与
   `test_growth_is_basis_independent` 两条测试从性质侧再守一遍。
   我另外确认了 `basis`（avg/eom）只改变取哪一档**基期**汇率，仍与月份无关。

3. **张数列是否原样保留** —— 是。每个成员必须显式声明 `contracts_col`（没有就写 `[]`，
   `test_contracts_col_declared_everywhere` 强制），`series/*.csv` 存的仍是官方原始
   张数/股数/本币金额，换算全部发生在 build 侧。ice.csv 里 `adv_nyse_tapeA_matched_mnsh`
   等原列与官方 xlsx 逐位相同（§3.1 已验）。

4. 一个**没有被机器守住**的口径前提，见问题 2。

---

## 六、发现的问题

### 【blocker 1】交付的测试套件在当前仓库里已经失败：pools.py 声明了 enx.csv 里不存在的 3 个列

```
series/enx.csv 没有列 'adv_commodity_deriv_kcontracts'
series/enx.csv 没有列 'adv_index_deriv_kcontracts'
series/enx.csv 没有列 'adv_singlestock_deriv_legacy_kcontracts'
```

实际落地的 `series/enx.csv`（15:41，174 行）把期货与期权**分开**存：
`adv_index_futures_kcontracts` + `adv_index_options_kcontracts`、
`adv_singlestock_futures_kcontracts` + `adv_singlestock_options_kcontracts`
（外加 `athex_*` 一整套备注列）、
`adv_commodity_futures_kcontracts` + `adv_commodity_options_kcontracts`。

pools.py 的 note 写的是「legacy 列由 fetch/enx.py 派生入库，**不要在 build 里现算**」——
方向是对的，但这个契约没有任何机器化的落点，两边就各写各的了。

**并且这不是能靠改 chain 绕过去的**：`_check_chain` 与 `apply_unit` 都强制
`unit_scale > 0`，多条腿只走 `add_series` 相加，**换算链在设计上表达不了减法**。
所以「主列 − athex_*」这个 legacy 口径**只能**是 CSV 里的派生列。

更根本的问题：**pools.py 为 8 个尚不存在的 CSV 凭空发明了 30 多个列名，
而 `check_columns()` 把「文件不存在」记成 pending 不算错，所以这些列名一个都没被验证过。**
第一个落地的 enx.csv 立刻打出 3 处不符 —— 命中率 0/3。
交付自称的「已建 CSV 里核了 31 个 (表,列)，0 处对不上」因此是一句**弱证据**：
它只覆盖了当时已存在的 4 张表。

**修复指令**（二选一，选 A）：
- **A（推荐，与 pools.py 的 note 一致）**：让 `fetch/enx.py` 派生并入库三列
  `adv_index_deriv_kcontracts = adv_index_futures + adv_index_options`、
  `adv_commodity_deriv_kcontracts = adv_commodity_futures + adv_commodity_options`、
  `adv_singlestock_deriv_legacy_kcontracts = (singlestock_futures + singlestock_options)
  − (athex_adv_singlestock_futures + athex_adv_singlestock_options)`。
  派生口径写进 `fetch/enx.py` 的 `update()` docstring，并在那里加一条断言：
  2025-11 及之后 legacy 列相对上月的跳幅不得超过 X 倍（就是 pools.py 说的 3-6 倍假跳）。
- **B**：改 pools.py，把 index / commodity 改成两条腿相加，singlestock 保持派生列不变
  （减法仍然表达不了）。B 只解决 2/3。
- **无论选哪个，另加一条防复发**：在 `build/CONTRACT.md` 里开一节
  「pools.py 对尚未建表的 CSV 提出的列名需求清单」，由 `pools.check_columns()`
  在 pending 分支里把这些列名**打印出来**（现在只打印文件名），
  让写 fetch 的人有一张可对照的清单。

### 【major 2】`dual_unit` 断言的恒等式没有被机器守住

`dual_note` 对读者承诺：「名义额份额 ≡ 张数份额，若不相等一定是换算链坏了」。
这个恒等只在**分母与全部 `in_share` 成员解析到同一个 product_id**（同一个基期常数）
时成立。我实测当前是成立的：

```
na_cash          denom {US_CASH_EQUITY_SHARE}  in_share {US_CASH_EQUITY_SHARE}  OK
na_multilist_opt denom {US_MULTILIST_EQ_OPT}   in_share {US_MULTILIST_EQ_OPT}   OK
（tmx 用 CA_CASH_EQUITY_SHARE，但 in_share=False，不进分子，不破坏恒等）
```

但 `validate()` **没有任何一条规则检查它**。将来谁给 na_cash 加一个
in_share=True、product 不同的成员（比如把 TMX 的 in_share 翻成 True，
或加一个用别的 product 的美国场所），名义额份额与张数份额会悄悄分叉，
而页面仍在宣称两者恒等、且 selfreport 对账只核张数口径 —— **对账会照样绿**。
这正是 `validate()` docstring 自己定义的「写错了在图上看不出来」那一类。

**修复指令**：在 `validate()` 的 `dual_unit` 分支加：

```python
if p.get('dual_unit'):
    dp = {leg['product'] for leg in p['denom']['chain']}
    mp = {leg['product'] for m in p['members'] if m.get('in_share')
                          for leg in (m.get('chain') or [])}
    if len(dp | mp) != 1:
        errs.append('池 %s dual_unit=True，但分母用 %s、in_share 成员用 %s —— '
                    '基期常数不同一，dual_note 宣称的「名义额份额 ≡ 张数份额」'
                    '不再成立，selfreport 对账也不再能代表主口径' % (pid, sorted(dp), sorted(mp)))
```
并在 `test_pools.py` 加一条对应的测试。

### 【major 3】evidence 指向的 verify 文档不在仓库里，只在 /tmp

pools.py 引用：`verify_ice.md` ×4、`verify_miax` ×3、`verify_db1` ×2、
`verify_enx` ×2、`verify_ndaq` ×2、「设计稿」×3。
仓库里 `find . -name "verify_*"` **一个都没有**；它们全在 `/tmp/exch_recon/`。

我确认了内容是真的（`/tmp/exch_recon/verify_ice.md` 第 343 / 358 行与 pools.py 的
evidence 逐字相符），所以这不是假引用 —— 但 `/tmp` 随时会被清掉，
到时候「分母是关于外部世界的断言，必须留下核对痕迹」这句话就落空了。
README 明确要求 `fetch/<t>.py` 的 docstring 是「第一手记录」，池定义的 evidence
应当同等对待。

**修复指令**：把 `/tmp/exch_recon/verify_*.md` 移进仓库
（建议 `build/verify/` 或 `docs/verify/`，随代码一起 commit），
并把 pools.py 里的引用改成仓内相对路径。若嫌体积大，至少把每条 evidence
真正用到的那 3-5 行摘进 pools.py 的字符串里，做到「不打开外部文件也能复算」。

### 【minor 4】列检查只看表头，空表能过关

`series/miax.csv` 在 15:42 落地时**只有表头、0 行数据**，
而 `pools.check_columns()` 与 `test_all_declared_columns_exist_in_built_csvs`
都判它「全对」，把它计入了「已核 42 个 (表,列)」。
一个 0 行的 CSV 通过了就绪门槛。

**修复指令**：`check_columns()` 除表头外再断言（a）至少 1 行数据；
（b）该 CSV 服务的每个成员声明的 `start` 月份在 `month` 列里存在。
后者顺带把「成员 start 写错」这类错也接住（现在 `start` 字段完全没被校验过）。

### 【minor 5】对账测试的逐月跳过是静默的

`test_pools.py:634`：
```python
if num is None or not den or not off:
    continue
```
若某次改版让 186/187 个月变得不可比，测试仍会在剩下 1 个月上通过 ——
只有 `assertTrue(devs)`（≥1 个月）这一道。而 evidence 字段里明明已经写着
「187/187 个月可比」，这个数完全可以拿来当断言。

另外同一行 `off = (drow.get(sr['col']) or mrow.get(sr['col']) or '')` 优先读**分母表**。
今天 na_cash 的分母表与成员表是同一张 ice.csv，无碍；将来某成员的 csv 与分母 csv
各自都有同名份额列时，会静默读到错的那一张。

**修复指令**：在 `selfreport` 里加一个 `n_months` 字段（写实测的 187），
测试断言 `len(devs) >= sr['n_months']`；并把 `off` 的取值改为
显式声明来源表（`sr['csv']`，默认成员自己的 csv），不要用 `or` 兜底。

### 【minor 6】同一份文件里对同一个测量给了两个精度

`fn_monopoly` 的 ice 成员 note 写「187/187 与自算一致（**误差 <0.15pp**）」，
而 `na_cash` 的 `recon_note` 与我的复算都是**最大 0.072pp**。
两句话说的是同一件事。文件自己的规矩是「容差一律写实测值，不许拍脑袋」。

**修复指令**：把 `fn_monopoly` 那句改成「最大 0.072pp（2017-12），见 na_cash.recon_note」，
不要在第二处另起一个宽松的数。

### 【minor 7】一条免费的对账通道没有接进来（顺带削弱了一条 caveat）

`series/cboe.csv` **没有任何份额列**，但 Cboe 官方工作簿（已经躺在 `cache/` 里）
第 28 行与第 31 行就是 Cboe 自报的多重挂牌期权份额与美股现货交易所份额。
我用它们做了 §3.3 的两条交叉验证，结果是 0.0015pp 与 0.0099pp。

接进来的收益有三层：
1. `na_cash` / `na_multilist_opt` 各多一个可 `selfreport` 的成员，
   不再是整套「唯一能与外部数字核的通道」都押在 ICE 一家；
2. `na_multilist_opt.denom.caveat` 那句「ICE 从未书面说明该分母是否含指数期权，
   页面上只能写『经交叉验证』」可以升级为一条**机器每月自动执行**的交叉验证，
   而不是一句写死在字符串里的历史结论；
3. Cboe 改版导致解析漂移时，这条能当场抓住。

**修复指令**：让 `fetch/cboe.py` 增补
`share_multilist_options`（工作簿 Market Share 段 "Multiply-listed options" 行）
与 `share_us_equities_exchange`（同段 "U.S. Equities - Exchange" 行）两列，
然后在 pools.py 的两个池里给 cboe 成员加 `selfreport`，容差按实测定
（我实测 2026-07 分别是 0.0015pp / 0.0099pp，建议全量跑完 115 个月再定）。

---

## 七、复现命令

```bash
cd /Users/hainan/Projects/monthly-op-dashboards
python3 build/pools.py          # 3 处列名不符
python3 build/notional.py
python3 build/test_pools.py     # FAILED (failures=1)

# 幂等
find series data build -type f \( -name '*.csv' -o -name '*.js' -o -name '*.py' \) \
  -exec md5 {} \; | sort > /tmp/s1.txt
python3 build/pools.py >/dev/null; python3 build/notional.py >/dev/null; python3 build/test_pools.py >/dev/null 2>&1
find series data build -type f \( -name '*.csv' -o -name '*.js' -o -name '*.py' \) \
  -exec md5 {} \; | sort > /tmp/s2.txt
diff /tmp/s1.txt /tmp/s2.txt    # 无差异
```

官方源重取（两条都是一手，无第三方）：
```bash
curl -A 'Mozilla/5.0' -o ice.xlsx \
  https://s2.q4cdn.com/154085107/files/doc_downloads/2026/07/2011-2026-Monthly-Stats-July-2026_vF.xlsx
shasum -a 256 ice.xlsx   # b091b514d189c979bf0808c0e62f625f93f8618b75f1d8e7ccb7645c73669a41

curl 'https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2019-01-01&endPeriod=2019-01-31&format=csvdata'
```

---

## 八、给上游的一句话

**数据与口径这两块，这份交付是我见过质量偏高的一档** —— 187 个月全量对账、
容差从实测反推、基期常数在类型层面就排除了当期价格、变异测试打得穿。
不通过纯粹卡在**跨交付物的 schema 契约没有落到机器上**：
pools.py 为 8 张还不存在的表凭空写了 30 多个列名，而现有的门槛检查设计成
「表不存在 = 不算错」，于是这批列名在落地前一个都没被验证过，
第一张落地的表就打出 3 处不符。修好 blocker 1 + major 2 即可放行。
