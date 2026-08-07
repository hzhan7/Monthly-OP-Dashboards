# 验收：contract_specs 规格常数表（2026-08-06）

**结论：通过（有 2 个 major + 7 个 minor 待修，无 blocker）**

交付的两张 CSV 我逐条重跑、重算、并回官方源重取原值比对，**没有发现任何一个编造的数字**。
这是本次验收里最重要的一句：18 条合约级规格的乘数引文、6 个实测基期价格、
以及 todo 表里 5 条「抓不到」的技术性描述（字节数、末行日期、"contract" 一词出现 0 次），
我全部独立复现了。下面列的问题都是工程闸门与口径留痕问题，不是数据错误。

---

## 1. 我自己跑的结果

### 1.1 两个生成器

```
$ python3 scratchpad/spec/gen_specs.py
wrote /Users/hainan/Projects/monthly-op-dashboards/series/contract_specs.csv: 73 rows      exit=0

$ python3 scratchpad/spec/gen_todo.py
wrote /Users/hainan/Projects/monthly-op-dashboards/series/contract_specs_todo.csv: 21 rows exit=0
```

### 1.2 check_specs.py（三种入口全跑）

```
$ python3 build/check_specs.py
contract_specs.csv：73 行（contract 18，index_ref 7，pool_product 48），基期价格已实测 23 行、待测 50 行
contract_specs_todo.csv：21 行缺口待补
pools.py 引用的 48 个产品：已入表 48，缺 0，其中基期价格待测 35

OK 全部检查通过                                                                            exit=0

$ python3 build/check_specs.py --selftest
== check_specs 自检（合成行，不读 series/）==
  区间重叠 / 区间断档 / 两行都开口 / 多代缺 from / product_id 重复 / 乘数为 0 /
  基期价为负 / 冗余列对不上 / 留空却无 📌 / 基准非法 / notional 乘数≠1 /
  index_ref 乘数≠1 / 基期月写错 / 干净的两代表        —— 14/14 PASS
自检通过                                                                                   exit=0

$ python3 build/check_specs.py --coverage      同上 + 覆盖率行                              exit=0
```

## 2. 幂等测试：通过

连跑两次 `gen_specs.py`，再连跑两次 `gen_todo.py`，md5 四次全同，
且**与交付时的文件逐字节相同**（`diff` 无输出）：

| 文件 | 交付时 | 第 1 次重跑 | 第 2 次重跑 |
|---|---|---|---|
| `series/contract_specs.csv` | `53fe30db4cb122454386dc7737a86283` | 同 | 同 |
| `series/contract_specs_todo.csv` | `cb3b19b2374a6f8118fea495766c5d86` | 同 | 同 |

两个脚本都是纯字面量 + 排序输出（`body.sort` / `sorted(ROWS)`），没有时间戳、没有
`dict` 迭代序依赖、没有网络。这一点符合仓库「构建日期不进 payload」的幂等约定。

## 3. 对账复算：三条 Cboe 序列全部逐位复现

我自己从 Cboe 官方 CDN 重下三份日频文件（不是复用它的缓存），自己解析、自己求均值：

```
SPX_History.csv  292,067 bytes  header ['DATE','SPX']            13,006 行
XSP_History.csv  233,335 bytes  header ['DATE',...,'CLOSE']       4,242 行
VIX_History.csv  471,187 bytes  header ['DATE',...,'CLOSE']       9,244 行
```

| 序列 | 交易日 | 首日 | 末日 | 我算的 2019-01 月均 | 表里的值 |
|---|---|---|---|---|---|
| SPX | 21 | 01/02 = 2510.03 | 01/31 = **2704.1001** | `2607.3899952380953` | 一致 |
| XSP | 21 | 01/02 = 251.00 | 01/31 = 270.41 | `260.7395238095238` | 一致 |
| VIX | 21 | 01/02 = 23.22 | 01/31 = 16.57 | `19.57238095238095` | 一致 |

- 它自称的「月末收盘 2704.1001，与月均差 3.7%」——我复算 2704.1001/2607.39 − 1 = **3.71%**，成立。
- VIX 区间自称 16.57 – 25.45 —— 我算 min=16.57 max=25.45，**逐位一致**。
- 它自称的两条独立恒等式，我用表里的 `base_notional_per_unit_local` 重除了一遍：
  - `CBOE_SPX_OPT / CBOE_XSP_OPT = 9.999979892357452`（偏离 10 为 2.0e-6，纯舍入）
  - `CBOE_VIX_FUT / CBOE_VIX_OPT = 10.0` 精确
  - `CME_MES_SP500 = 5 × 2607.3899952380953 = 13036.949976190477` ✓

## 4. 翻假：逐项结果

### (a) 整列全空 / 用 0 或 NaN 冒充缺失

- **有两列 100% 空**：`effective_from`、`effective_to`（73/73 空）。但这是**合法状态**而非
  造假：check_specs 的 C12 允许「单行规格组两头都空 = 本表未见规格变更」，
  且 `--selftest` 专门为这条从没被真实数据走过的分支写了 5 个合成用例。→ 记 minor。
- 其余空值：`contract_name`/`underlying_symbol` 空 48（全部是 pool_product 行，设计如此）、
  `base_price_local` 空 50、`price_id` 空 52。
- **没有一个 0 / NaN / -1 冒充缺失**：我扫了三列数值列的字面量，零命中。
- C4 强制「留空必须在 notes 里带 📌」，50 个空行全部带，我用变异测试确认这条抓得住。

### (b) 硬编码魔数无出处

**没有无出处的魔数。** 18 条合约行每条都带 `source`（官方 URL）+ `evidence`（原文引文）。
最值得怀疑的一个是 SOFR 的 `$1,000,000` —— 它不是页面上的字，是推导值。
推导写在 evidence 里，我重算：官方页给 `$2,500 x contract-grade IMM Index`，
`N × 0.01 × 0.25 = 2500 ⇒ N = 1,000,000`，成立。

### (c) docstring 声称的口径坑是否真在代码里被处理

逐条对照 C1–C13，**都在代码里，不是只写在注释里**。我做了 8 个变异测试直接打真表：

| 变异 | 结果 |
|---|---|
| 基期价改成月末收盘 2704.1001（冗余列不动） | 抓住（C5 冗余列对不上） |
| `base_price_basis` 改 `eom_close` | 抓住（C7） |
| MES 乘数偷改 5→50 | 抓住（C5） |
| `base_month` 偷改 2020-01 | 抓住（C6） |
| `product_id` 重复 | 抓住（C2） |
| 实测价被清空 | 抓住（C4，2 条） |
| 乘数改 0 | 抓住（C3） |
| **基期价改月末收盘 + 冗余列同步改成一致** | **抓不住** → 见 major-2 |

todo 表的三个变异（登记已入库产品 / next_step 留空 / 非 https）也全部抓住。

### (d) 第三方聚合站冒充官方源

**没有。** 我把 73 行的 `source` 列 + 三列里出现的全部 URL 抽出来做域名统计：

```
www.cmegroup.com 7   www.cboe.com 4   www.jpx.co.jp 4   cdn.cboe.com 3
www.stoxx.com 2      www.ice.com 2    www.hkex.com.hk 2  www.dax-indices.com 1
www.sgx.com 1        www.hsi.com.hk 1 www.asx.com.au 1
（另 48 行 source = "build/pools.py PRODUCTS[...]" 内部指针）
```
全部是交易所本体或指数编制方官网，零 Yahoo / Investing / TradingView / Barchart。
todo 表 21 行的 `official_url` 也全是 https 官方直链（check_todo 有硬闸门）。

### (e) 异常路径

- `pools.PRODUCTS` 新增产品而 `POOL_EXTRA` 没跟上 → `KeyError` **硬失败**（我实测触发）。方向正确。
- 反向（`POOL_EXTRA` 有残留 key）→ **静默忽略**，仍写出 73 行。→ 记 minor。
- 表缺失 / 空表 / 缺列 → `SpecCheckError`，`main` 打 FAIL 并 `return 1`。
- 基期价留空的产品一旦被换算链用到 → `notional.MissingBasePrice` 抛异常，不静默变 NaN。
- 两个生成器不联网，所以「源站改版」对它们不适用；风险转移到了 major-3。

### (f) 抽查 3 个数值回一手源

我用 nscurl 绕开 Akamai（curl 全部 403），逐页取原文比对：

| 行 | 表里的引文 | 官方页实际文字 | 判定 |
|---|---|---|---|
| `CME_SR3_SOFR` | `Contract Unit $2,500 x contract-grade IMM Index` | `...Contract Unit $2,500 x contract-grade IMM Index Price Quotation contract-grade IMM Index = 100 minus R...` | **逐字一致** |
| `CME_ZN/ZF/ZB` | `Contract Unit Face value at maturity of $100,000` | 三页均命中同一句 | **逐字一致** |
| `CME_MES_SP500` | `The Micro E-mini S&P 500 futures contract is $5 x the S&P 500 Index and has a minimum tick of 0.25 index point` | 官方页原句（末尾是 `index points`，表里写 `index point` 少一个 s） | 一致（差 1 个 s） |
| `CME_NQ_NDX` / `CME_MNQ_NDX` | `$20 x the Nasdaq-100 index` / `$2 x the Nasdaq-100 Index` | 逐字命中 | **一致** |
| `CBOE_SPX_OPT` | `Product Snapshot (as of March 19, 2024)` + `100 Multiplier` | 逐字命中，含快照日期 | **一致** |
| `CBOE_XSP_OPT` | `(as of June 13, 2025)` + `100 Multiplier` | 逐字命中 | **一致** |
| `CBOE_VIX_OPT` | `VIX Snapshot (as of March 19, 2024)` + `100 Multiplier` | 逐字命中 | **一致** |
| `CBOE_VIX_FUT` | `Contract Snapshot (as of June 13, 2025)` + `1000 Multiplier` | 逐字命中 | **一致** |
| `HKEX_HSI_FUT` | `Contract Multiplier HK$50 per index point` | 逐字命中 | **一致** |
| `HKEX_MHI_FUT` | `HK$10 per index point` + `one-fifth the size of the HSI...` | 命中（页面在词间插了断词空格） | 一致 |
| `JPX_N225_FUT_LARGE` | `The minimum trading unit is 1,000 times the Nikkei Stock Average (Nikkei 225)` | 逐字命中 | **一致** |
| `JPX_N225_MINI` | `The minimum trading unit (1 contract) is 100 times...` + `one-tenth` | 逐字命中 | **一致** |
| `JPX_TOPIX_FUT_LARGE` | `The minimum trading unit (1 contract) is 10,000 times TOPIX` | 逐字命中 | **一致** |
| `ICE_BRENT_FUT` | `Contract Size 1,000 barrels` / `Any multiple of 1,000 barrels` / `US Dollars and cents` | 三句全命中 | **一致** |
| `ICE_GASOIL_FUT` | `Contract Size 100 metric tonnes` / `One or more lots of 100 metric tonnes of low sulphur gasoil (10ppm diesel)` | 逐字命中 | **一致** |

todo 表里的「卡在哪一步」也可证伪，我也重取了：

| 声称 | 我实测 |
|---|---|
| CME 2 年期页没有 `Review contract highlights` 区块 | 页面 212KB 可下，正文里 `Contract Unit` **零命中** ✓ |
| eurex.com 规格页 133KB，`contract` 一次都不出现 | 133,041 bytes，`grep -oic contract` = **0** ✓ |
| sgx.com 只返回 14KB 外壳 | 14,850 bytes ✓ |
| miaxglobal.com 页能下 64KB 但没规格表 | 64,335 bytes ✓ |
| stoxx `hbrbcpe.txt` 688KB、**末行只到 2016-10-04** | 688,500 bytes，末行 `04.10.2016; 2871.06; ...` ✓ |
| asx.com.au 返回 136,883 字节通用外壳 | 我取到 136,750 bytes（差 133 字节，页面自身变动）→ minor-7 |

## 5. 口径审查

- **换算链正确。** `notional.to_base_notional` = `qty × base_notional_per_unit_local × fx(2019-01)`，
  价格项与汇率项都是常数 ⇒ 定基序列的增长率 = 张数增长率。**没有任何一处混进当期价格**：
  当期价格只出现在 `current_notional_per_unit_usd` / `to_current_notional`，
  且 docstring 明写「不进任何增长图或份额图」。
- **基期统一锁 2019-01。** `check_specs.BASE_MONTH` 与 `notional.BASE_MONTH` 都是 `'2019-01'`，
  C6 逐行核；73 行 `base_month` 全部等于 `2019-01`，我复核过。
- **张数列原样保留。** 规格表只提供常数，不改写 `series/*.csv` 的任何张数列；
  `unit_scale`（千张→张）刻意留在 pools.py，与规格分离，理由写在 `to_base_notional` 的 docstring 里。
- **price basis 单一。** 全表 `base_price_basis` 只有 `avg_close`(6) / `definitional`(17) / 空(50)，
  没有 `eom_close` 混入。C7 是硬闸门。
- **`kind` 与乘数自洽**：`share`/`notional` 的 multiplier 恒为 1，`notional` 的 base_price 恒为 1。C8 核过。
- **`index_ref` 未被换算链引用**：coverage 的 `misuse` 为空，48 个被引用产品全是 `pool_product`。

---

## 6. 问题清单

### major-1 —— `build/check_specs.py` 没有任何调用方

```
$ grep -rn "check_specs" . --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=cache
build/test_pools.py:506:  这里查不了 —— 那一条由 check_specs / build 侧在规格表填好后再守。
```
`monthly_run.py` 不跑它，`build/test_pools.py` 只在注释里提到它，仓里也没有 CI / Makefile / pytest 配置。
一道**没人跑的闸门等于没有闸门** —— 表被改坏时不会有任何东西报警，而这张表的
全部价值就是「错了图上看不出来」。这与 README 三条护栏的设计意图直接冲突。

**修复指令**：在 `build/test_pools.py` 末尾加一个 `test_contract_specs_clean()`，
内容为 `assert check_specs.main([]) == 0`；并在 `monthly_run.py` 的 preflight
（工作树检查那一段之后、下载之前）加一次 `check_specs.main([])`，非 0 就 `FAILED specs`。

### major-2 —— 6 个实测常数在仓里不可复算

`SPX_AVG` / `XSP_AVG` / `VIX_AVG` 三个数字在 `gen_specs.py` 里是**手抄字面量**，
取数用的下载与求均值代码没有留在任何地方，`cache/` 又被 gitignore。
后果：`check_specs` 的 C5 只校验「冗余列 = 乘数 × 基期价」这个**内部一致性**，
所以「把基期价换成月末收盘 2704.1001 并同步改冗余列」这个变异**抓不住**（见 §4c 表格末行）——
而这正是模块 docstring 里点名的、代价 3.7% 的那种错。
我这次是自己重下 Cboe CDN 才把它证伪的，仓库自己做不到。

**修复指令**：把我用的这段落到 `build/verify_base_prices.py`（联网、手动跑、不进 cron），
让它重下三份 CDN 文件、重算 2019-01 均值、与 `contract_specs.csv` 比对到 1e-12，
不一致就 exit 1：

```python
import csv, io, urllib.request
CDN = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/%s_History.csv'
WANT = {'CBOE_SPX_OPT': ('SPX', 'SPX'), 'CBOE_XSP_OPT': ('XSP', 'CLOSE'),
        'CBOE_VIX_OPT': ('VIX', 'CLOSE'), 'CBOE_VIX_FUT': ('VIX', 'CLOSE'),
        'CME_MES_SP500': ('SPX', 'SPX'), 'IDXREF_US_SPX': ('SPX', 'SPX')}
def avg(sym, col):
    raw = urllib.request.urlopen(CDN % sym, timeout=60).read().decode()
    v = [float(r[col]) for r in csv.DictReader(io.StringIO(raw))
         if r['DATE'].startswith('01/') and r['DATE'].endswith('/2019')]
    assert len(v) == 21, '%s 2019-01 交易日数 %d ≠ 21（官方文件改版？）' % (sym, len(v))
    return sum(v) / len(v)
```
（我实测这三条的返回：SPX 21 日 → 2607.3899952380953，XSP 21 日 → 260.7395238095238，
VIX 21 日 → 19.57238095238095，与表里逐位相同。）

### major-3 —— `CBOE_VIX_FUT` 用 VIX **现货**当基期价，但 VX 的名义额应按**期货价**计

`CBOE_VIX_FUT` 的 evidence 写的是 `VIX_History.csv`（现货指数日收盘），
而 VX 期货一张的规模是 `1000 × 期货结算价`，不是 `1000 × 现货 VIX`。
2019-01 恰好是 2018-12 波动率尖峰之后，VIX 期限结构在月内从贴水翻成升水，
现货与近月期货的差可以到 5–10%。这不影响增长率（价格项仍是常数），
但**直接影响 VX 在 equity_index 池里的权重**，而按设计权重就是这张表存在的理由。
表里 `notes` 只提醒了「VIX 点不是资产价格」和「乘数差 10 倍」，没提现货≠期货这一层。

**修复指令**：二选一并写进 `notes`——
(a) 改用 Cboe 官方 VX 历史结算价（`cdn.cboe.com/data/us/futures/market_statistics/historical_data/`
     下按合约月的 CSV），按 2019-01 各交易日近月结算价求均值；或
(b) 保留现货值，但在 `notes` 里加一句「基期价用的是 VIX 现货指数月均，
     不是 VX 结算价；两者在 2019-01 相差约 X%，故 VX 在池内的权重是近似值」，
     并把 X 实测出来填进去。**不接受沉默保留现状。**

### minor-4 —— `check_specs` 的汇总行把 `definitional` 算进「已实测」

打印的是「基期价格已实测 23 行、待测 50 行」，但 23 行里只有 **6 行**是 `avg_close`
（真实测：SPX×2、XSP、VIX×2、IDXREF_US_SPX），另 **17 行是 `definitional`**（价格恒为 1）。
自己的模块 docstring 明写「`definitional` … 它不是一种实测基准」，汇总行却把两者混在一起数，
会让人以为规格表的实测覆盖率是 32% 而不是真实的 8%。

**修复**：`main()` 里把 `priced` 拆成 `measured`（`basis == 'avg_close'`）与
`definitional` 两个计数，打印成「实测 6 / 定义值 17 / 待测 50」。

### minor-5 —— `effective_from` / `effective_to` 两列 73 行全空

设计上合法（无多代规格），但一列 100% 空的字段没有任何东西证明它「本该空」。
**修复**：在 `check_specs` 的汇总行加一句「多代规格组 0 个（effective 区间全空是预期状态）」，
把「空」从沉默状态变成一次显式陈述。

### minor-6 —— `POOL_EXTRA` 残留 key 被静默忽略

`pools.PRODUCTS` 新增产品会 `KeyError` 硬失败（正确），但反向 —— pools 删掉产品、
`POOL_EXTRA` 里的条目变成死代码 —— 不报错，我实测仍输出 73 行。
**修复**：`rows()` 里加 `stale = set(POOL_EXTRA) - set(pools.PRODUCTS)`，非空就 `raise`。

### minor-7 —— todo 表 ASX 的字节数已过期

`ASX_SPI200_FUT` 的 blocker 写 `136,883 字节`，我今天实测 `136,750`。
**修复**：把精确字节数改成「约 137KB」，或在 `blocker` 里注明字节数会随页面变动。

### minor-8 —— TTF 引文漏了半句，且 672–744 的区间对不上原文

todo 里 `ICE_TTF_GAS` 引的是 `Contract Size 1 MW per day in contract period`，
官方原文后面还有 `(i.e. month, quarter, season or year) x 23, 24 or 25 hours (summer or winter time)`。
漏掉的正好是夏令时那半句 —— 而 `1 MW × 24h × 天数` 的算法在有 DST 切换的月份会差 1 小时。
（2019-01 无 DST 切换，744 MWh 这个基期值本身是对的。）
**修复**：把引文补全，并把 next_step 的 (a) 方案改成「基期月 2019-01 无 DST 切换 ⇒ 744 MWh/张」。

### minor-9 —— `check_specs` 不校验 `pool` 列取值

18 行 contract + 21 行 todo 的 `pool` 是手打的，我核过全部落在 `pools.POOLS` 的 id 集合里
（`(deflator)` 是 IDXREF_US_SPX 的例外写法），但**没有闸门**保证下一个人手打时不写错。
**修复**：在 `coverage()` 里加一条：contract / todo 行的 `pool` 必须 ∈ `{p['id'] for p in pools.POOLS}`，
`(deflator)` 显式白名单。

### minor-10 —— 生成器写死绝对路径

`gen_specs.py` / `gen_todo.py` 的 `SERIES` 是 `/Users/hainan/Projects/...` 绝对路径，
换机器或换 checkout 位置即失效。既然脚本被刻意留在 scratchpad 之外无人跑，风险不大，
但换机重跑时会静默写到不存在的目录（实际会 `FileNotFoundError`，不算静默）。
**修复**：改成从环境变量或 `sys.argv[1]` 取，默认值保留现路径。

---

## 7. 验收侧留下的复算材料

- 下载的官方原始文件：`/tmp/exch_recon/dl/`（SPX/XSP/VIX CSV + 20 个官方页快照）
- 交付时的 CSV 快照（用于 diff）：`/tmp/exch_recon/backup/`
