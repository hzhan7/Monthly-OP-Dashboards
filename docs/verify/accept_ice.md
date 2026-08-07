# 验收：ICE（fetch/ice.py + series/ice.csv）

**结论：通过**（4 条 minor，无 blocker / 无 major）

验收员独立执行，不采信交付说明里的任何数字 —— 下面每个数都是我自己重新下载官方文件、
自己写解析、自己重算出来的。

---

## 1. 我实际跑出来的输出

```
$ python3 fetch/ice.py
[ice] 与官方新闻稿「Intercontinental Exchange Reports July 2026 Statistics」逐条对账 12/12 一致（容差 2.0pp）
added : 0 个月 []
EXIT=0      real 3.9s

$ python3 fetch/ice.py            # 第二次
[ice] 与官方新闻稿「…July 2026 Statistics」逐条对账 12/12 一致（容差 2.0pp）
added : 0 个月 []

$ python3 fetch/ice.py latest
latest: 2026-07
```

## 2. 幂等测试：通过

| | series/ice.csv | series/source_dates.csv |
|---|---|---|
| 跑之前 | `7e0c3b30cfffb885fe6481fc04ac6785` | `30ebdabf698b56b7745a789e2c1e1546` |
| 第 1 次跑完 | `7e0c3b30…` | `30ebdabf…` |
| 第 2 次跑完 | `7e0c3b30…` | `30ebdabf…` |

两个文件字节级不变，mtime 也没动（`update()` 在 `added or filled` 为空时根本不写盘）。

**更强的一条：从零全量重建也字节一致。** 我把 `series_dir` / `cache_dir` 指到两个空目录
重跑 `update()`：写出 187 个月、`md5 = 7e0c3b30cfffb885fe6481fc04ac6785`，
与仓库里那份 `diff` 无输出。也就是说这份 CSV 不是手工拼出来再让脚本"认领"的，
脚本自己能重新生产出逐字节相同的结果。

（验收过程中 `series/source_dates.csv` 的 md5 后来变了 —— 我 diff 过，
新增的是 `enx,2026-06,…` 一行，是**同批次另一个 agent** 写的，与 ICE 无关；
`^ice,` 行全表恰好 1 条，内容未被改动。）

## 3. 对账复算：全部自己重算，全部对上

### 3.1 回源取原值

- 自己打 `ir.theice.com/feed/ContentAsset.svc/GetContentAssetList` → 命中两条，
  `Monthly Statistics Tracking` 与 `Monthly Statistics`，**FilePath 完全相同**，
  指向 `s2.q4cdn.com/154085107/files/doc_downloads/2026/07/2011-2026-Monthly-Stats-July-2026_vF.xlsx`。
- 自己重新下载该 xlsx：**377,178 B，sha256 `b091b514d189c979…`，Last-Modified `Wed, 05 Aug 2026 12:30:32 GMT`**
  —— 与 docstring 自述逐位相同，且与 `cache/ice_monthly_stats.xlsx` 的 md5 相同。

### 3.2 逐格复算（不是抽查，是全量）

我另写了一份**独立解析器**（把行号 D7/D8/D11-36/D59-64/D70-75、O9/O10/O11/O16、
C6/C9-12/C15-18/C21-24/C26/C27/C35、X6/X7/X8 全部写死，走的路径与被验代码完全不同），
对我自己下载的那份 xlsx 提取，与 `series/ice.csv` 逐格比对：

```
cells checked 10285   mismatches 0
```

**10,285 格 / 55 列 / 187 月，零差异。** 月份连续性：2011-01..2026-07 与理论序列完全相等，无断档。

### 3.3 份额自洽（任务点名要的那条）

自算 `(tapeA+B+C matched) / (tapeA+B+C consolidated)` vs ICE 自报 `share_nyse_us_cash_matched`：

| 月份 | 自算 | 自报 | 差 |
|---|---|---|---|
| 2026-07 | 0.19092 | 0.191 | −0.0084pp |
| 2026-06 | 0.20020 | 0.200 | +0.0197pp |
| 2025-07 | 0.18666 | 0.187 | −0.0342pp |
| 2025-12 | 0.19704 | 0.197 | +0.0040pp |
| 2019-06 | 0.24802 | 0.248 | +0.0017pp |
| 2011-01 | 0.26855 | 0.269 | −0.0451pp |

全 187 个月**最大偏差 0.0719pp，出现在 2017-12** —— 与交付自述一字不差。>0.15pp 容差的：0 个月。
期权份额同法：187/187 通过，最大 0.0508pp（2016-09）；2026-07 = 13614/64394 = **0.21142** vs 自报 0.211。

### 3.4 外部证据：官方新闻稿 y/y（我自己读 PDF、自己算）

从 `cache/ice_release_2026-07.pdf`（BUSINESS WIRE 原稿，2026-08-05）逐条抠出百分比，
用 CSV 自己算同比：

| 稿方口径 | 稿称 | 我用 CSV 算出 |
|---|---|---|
| Total ADV | +25% | +24.6% |
| Total OI（= oi_comm + oi_fin，官方无此行） | +18% | +18.4% |
| Total Energy ADV / OI | +13% / +6% | +13.4% / +6.3% |
| Total Oil ADV | +16% | +15.6% |
| Brent ADV | +40% | +39.7% |
| Gasoil ADV | +10% | +10.2% |
| Total Natural Gas ADV | +9% | +9.1% |
| Total Ag & Metals ADV / OI | +38% / +42% | +38.0% / +41.9% |
| Sugar ADV | +11% | +11.0% |
| Total Financials ADV / OI | +39% / +38% | +38.6% / +38.1% |
| Total Interest Rates ADV / OI | +40% / +43% | +39.7% / +42.6% |
| Total Equity Indices ADV | +30% | +29.9% |
| NYSE Equity Options ADV | +26% | +26.5% |

16/16 全部在 0.6pp 以内。这一条排除了"读到别的行还看着像正常数字"。

### 3.5 docstring 里的统计断言，我逐条重跑

全部**精确复现**，一个没编：

- 闭合严格相等计数 ENERGY 85/187、AG 140、COMM 138、FIN 109、OI-COMM 134、OI-FIN 139；max|差| 2/1/1/2/1/1 ✔
- `TOTAL F&O ≠ COMM+FIN`：121 个月相等，max|差| 32（2011-08）✔
- 非整数格 **2,429** 个 ✔
- 三行交易日只在 **2012-10 / 2018-12 / 2025-01** 三个月不同；`commod == rates` 恰好 **69/187** ✔
- 新闻稿节奏：逐年扫 2015-2026 得 **124 期**，最早数据月 **2015-09**（2015-10-05 发），
  几号分布 **3 号 44 / 4 号 15 / 5 号 46 / 6 号 19，最晚 6 号** ✔（与 LAG=(6,6) 的推荐一致）
- 工作簿内部：`2Q26` 列 Financials ADV = **4996.292370711726** ✔；
  sharedStrings 里唯一带日期的字符串就是 CHX 那条脚注 ✔；`TTF/Title Transfer/Dutch` **0 命中** ✔；
  CDS 表 r17/r20 各只有 **34 个月**有值（2016-09..2019-06）✔；CDS 2026-01 = **391/1330/1720** ✔
- 路径claim：`/2026/07/…May-2026_vF.xlsx` → **404**，`/2026/06/…` → **200** ✔；
  `ir.theice.com/ir-resources/supplemental-information` → **200，64,725 B，`Monthly-Stats*.xlsx` 命中 0** ✔
  （即 docstring 那条"别去搬 curl_cffi/Chrome"的纠错是对的，不是被拦，是页面里真没有链接）

## 4. 翻假

**(a) 整列全空 / 用 0 或 NaN 冒充缺失？没有。**
全表零值单元格 **0 个**，无 NaN/inf。唯一的空格子是 `cds_*` 三列在 2011-01..2012-12 共 24 个月 ——
我在**官方原表里**核对过，那 24 个月列在 `CDS Clearing` 表里本来就不存在（该表只有 163 个日期列，
比其余三张少 24），不是解析漏读。`_validate` 对 `< 2013-01` 的 CDS 空格开豁免，其余任何列
任何月为空一律抛错。

**(b) 无出处的魔数？没有。**
代码里没有任何写死的行号/列号 —— 表头行是按「一行里 ≥3 个 datetime 单元格」现扫出来的
（我独立确认了 Derivs 5/58/69、Options 5/15、Cash 4/34、CDS 5 与 docstring 完全一致），
sheet 按正则认，标签列按「1 .. 最小月份列−1」现算。
数值常量只有 `FOOT_TOL=3.0` / `CDS_TOL=2.0` / `SHARE_TOL=0.0015` / `PR_TOL_PP=2.0` /
`PR_MIN_CLAIMS=3` / `_PAGE=600`，每个紧邻都有实测出处，且我上面 3.5 节把这些出处全部复算过。

**(c) docstring 声称的口径坑，是不是真在代码里被处理？逐条查了，是。**

| 坑 | 代码里的落点 | 我的验证 |
|---|---|---|
| 1 四舍五入 → 用容差 | `_validate` 全部走 `near()` + FOOT_TOL | 若改成 `==` 会失败 102 次，实测 |
| 2 同名标签三段 | `_blocks()` 按日期表头分块 + `group` 小节头 | 人为造重复标签 → 抛错（见 4e） |
| 3 只认 datetime 表头 | `_month_columns` `isinstance(_dt.datetime)` | 季度列 `1Q11` 确实被丢掉，187 列全月份 |
| 5 无 TOTAL OI，自己加 | `_PR_METRICS['total'][1]` = comm+fin，每月自动撞新闻稿 | 我复算 +18.4% / +19.7% ✔ |
| 6 F&O 不当校验 | `_validate` 里确实**没有**这条 near() | ✔ |
| 7 单股不进合计 | `adv_financials` 只校验 4 子项，单股不在内 | 187 个月全过 ✔ |
| 11 已有值永不覆盖 | `update()` 只填空，冲突写 `cache/ice_restatements.csv` | 重跑 0 变更 ✔ |
| 13 latest 以 ANCHOR 非空为准 | `data = {m:r for … if r[ANCHOR_COL] is not None}` | 人造空占位月 → 被丢弃，仍 187 月 ✔ |
| 15 三列交易日 | 三列都入库 | 三月不同已复现 ✔ |
| 16 CDS 收入两行故意不入库 | 不在 COLUMN_SPEC | 我确认那两行确实只有 34 个月有值 ✔ |

**(d) 第三方聚合站？没有。**
全链只有 `ir.theice.com`（ICE 自己的 IR 站）与 `s2.q4cdn.com/154085107/`（ICE 自己的 Q4 CDN，
路径由 ICE 的 feed 给出、不是猜的）。没有 barchart / investing / wsj / 任何行情站。

**(e) 异常路径：抛异常，不静默写空。8+6 个故障全部炸。**

解析层（我拿官方 xlsx 复制件人为改坏后跑）：

```
baseline（无损往返）                  ==> 正常，187 月
最新月 Brent 置空                     ==> IceFetchError: 2026-07 缺列 ['adv_brent_kcontracts']
tapeA matched ← tapeB matched（错行）  ==> IceFetchError: Tape A 份额对不上 …（差 -15.088pp）
CDS 非客户少 99（复刻 2026-06 官方错值）==> IceFetchError: CDS 恒等式不成立（差 99）
NYSE 期权 ADV 虚增 20%                ==> IceFetchError: NYSE 期权份额对不上
tapeA handled < matched               ==> IceFetchError: 两行读反了
Nat Gas +50（破坏 TOTAL ENERGY 闭合）  ==> IceFetchError: 恒等式不成立
sheet 改名 Cash Products→Cash Prodz   ==> IceFetchError: 匹配 sheet 得到 []
行名 TOTAL ENERGY→TOT EN              ==> IceFetchError: 匹配到 0 行（应当恰好 1 行）
删掉行业分母行                        ==> IceFetchError: 匹配到 0 行
造一个重复的 TOTAL COMMODITIES 标签    ==> IceFetchError: 匹配到 2 行
数字格换成文本 'n.m.'                 ==> IceFetchError: 单元格 R11C251 不是数字
官方开出一个空的 2026-08 占位列        ==> 正常丢弃，仍 187 月（不写半行空数据）
```

网络层（monkeypatch `_http_get`）：

```
feed 404 / 断网         ==> IceFetchError 下载失败
feed 返回 HTML          ==> IceFetchError 返回的不是 JSON
feed JSON 但少了结果键   ==> IceFetchError 接口可能改版
feed 里没有月度统计条目  ==> IceFetchError 找不到 'Monthly Statistics Tracking'
feed 里两个不同的 xlsx   ==> IceFetchError 无法判断用哪一份
xlsx 直链返回 Cloudflare HTML ==> IceFetchError 返回的不是 xlsx（前 8 字节 b'<!DOCTYP'）
```

一条静默写空的路径都没有找到。新闻稿回校是唯一"取不到就只警告"的地方，
但**取到了却对不上**是硬失败 —— 这个软硬分界是合理的（它依赖 ICE 的文案措辞，不依赖数据）。

**(f) 数字凭记忆编造？抽查全部命中，只逮到 1 处错引（见问题 1）。**
上面 3.5 节列的十几条断言全部一手复核通过。唯一对不上的是引用**别家 CSV** 的那个数。

## 5. 口径审查（定基名义额链）

本批次交付物**不包含**换算链，所以这一节能查的只有"源数据有没有被提前污染"：

- `series/ice.csv` **只存官方原样给出的行**：张数（`adv_*_kcontracts`）、股数（`_mnsh`）、
  RPC、份额、OI、CDS 名义额。逐格与官方 xlsx 比对为 0 差异 ⇒ **没有任何乘数 / 价格被提前乘进去**，
  也没有派生列（`adv_nyse_us_cash_matched_mnsh` 确实没入库，符合"官方没有的行不造"）。
- **张数原样保留 ✔** —— 乘数表将来怎么改都能复原历史。
- 基期：`build/notional.py` 里 `BASE_MONTH = '2019-01'`，并且 `load_specs()` 强制
  **逐行校验 `base_month == BASE_MONTH`，不一致就抛 ChainError**（我读了第 214-218 行），
  `kind='notional'` 的行还强制 `base_price_local == 1`，`base_notional_per_unit_local`
  与 `multiplier × base_price_local` 交叉校验 —— 基期锁死这件事在代码层是硬约束，不是约定。
  价格项走 `base_price_local`（基期常数），当期价格另走 `load_prices()`/`prices.csv` 且
  被注释明确标为「主口径缺它照跑」—— **当期价格没有混进定基口径**。
- ⚠ 但 **ICE 尚未接进这条链**：`build/notional.py` 全文只有注释提到 ICE，
  `series/contract_specs.csv` 与 `series/prices.csv` **两个文件都还不存在**，
  所以"ICE 的定基名义额"目前无法端到端跑通、也无法验收。见问题 4。

---

## 发现的问题

### 1【minor】口径坑 4 引用了错的 CME 列，数字对不上一手源

`fetch/ice.py` 模块 docstring（口径坑 4）写：

> CME：`oi_energy_contracts` 2026-07 = 11,042,384（裸张）

实际查 `series/cme.csv` 的 2026-07 行：`oi_energy_contracts = 15903732`，
而 **11,042,384 是同一行的 `oi_ag_contracts`**（我 grep 定位到的就是这一格）。
这一条正是用来教下一个人"跨家比要注意 ×1000"的锚点，锚点本身错了会把人带偏。

**修复指令**：把该句改为
`CME：oi_energy_contracts 2026-07 = 15,903,732（裸张）`；
若原意是想对比商品口径，请显式写清列名，不要混用 energy/ag。

### 2【minor】docstring 声称 roster 的 LAG 已填 (6,6)，实际 ICE 根本没接进调度

docstring 写「所以 `build/roster.py` 的 LAG 填 **(6, 6)**」，是完成时。实测：

```
$ grep -n ice build/roster.py     → 无
$ python3 monthly_run.py --only ice --dry-run
FAILED 未知 ticker: ['ice']
```

`monthly_run.TICKERS` 里也没有 `ice`。即：这个抓取器现在**不会被 cron 跑到**，
`update()` 里那段关于「上一次被 kill 后重跑要补记发布日」的设计目前无人触发。
如果本批次的验收口径就是"只交 fetcher + CSV"，这不算缺陷，但**文字必须与现实一致**。

**修复指令**（二选一）：
(a) 把 `ice` 加进 `monthly_run.TICKERS`、`build/roster.py` 的 `LAG`（填 `(6, 6)`）、
    `META` 与分组表，并补 `build/ice.py` payload 生成器；或
(b) 把 docstring 那句改成「⇒ `build/roster.py` 的 LAG **应填 (6,6)**（本模块交付时尚未接入调度）」。

### 3【minor】"10,026 个月度单元格"这个统计口径少了一整列

docstring 口径坑 1 说「10,026 个月度单元格里只有 2,429 个非整数」。
非整数计数 **2,429 完全正确**；但分母算错了：55 列 × 187 月 = 10,285 格，
减去 CDS 前 24 个月的 72 个空格 = **10,213 个非空格**。10,026 = 10,213 − 187，
恰好少算了一整列（54 列而非 55 列）。

**修复指令**：把 `10,026` 改成 `10,213`（非空格数），或写成
「10,285 格中 10,213 格有值，其中 2,429 个非整数」。

### 4【minor / 阻塞下一批次，不阻塞本批次】定基名义额链对 ICE 还是空的

`build/notional.py` 的基期锁定与常数价格约束都写得很硬（`BASE_MONTH='2019-01'` 逐行强校验、
`kind='notional'` 强制 `base_price_local==1`、`multiplier × base_price` 与冗余列交叉校验、
缺基期价 `MissingBasePrice` 而不是 NaN），设计上没问题；但
`series/contract_specs.csv` 与 `series/prices.csv` 尚不存在，ICE 也没有任何规格行，
所以「ICE 张数 → 定基名义额」这条链**目前一步都跑不了**，验收无从检查换算结果。

**修复指令**：下一批次交付 ICE 的 `contract_specs.csv` 行时，必须同时给出
(a) 每个 `price_id` 的基期价格来源（2019-01 的哪个官方结算价，链接落在 `source` 列）；
(b) 一条"张数 × 乘数 × 基期价 = 定基名义额"的手算复核（至少 2 个产品 × 2 个月），
让验收员能不读代码就重算。

---

## 没有发现的问题（明确说明，避免下一个人重查）

- 没有整列全空、没有 0/NaN 冒充缺失、没有硬编码行号列号、没有第三方聚合站、
  没有静默吞异常、没有把当期价格混进定基、没有把张数换算掉。
- 交付自述的每一个对账数字我都独立重算过，**除问题 1 那一处引用别家 CSV 的错，全部为真**。
