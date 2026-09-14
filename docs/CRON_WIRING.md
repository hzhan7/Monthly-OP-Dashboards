# cron 接线：一轮跑什么、各家什么时候开闸、怎么删掉一家

入口是 `monthly_run.py`，**每天跑一次**。天天跑不是浪费：28 家的披露日从次月 1 号散到
21 号，要覆盖全部窗口就只能天天开工；真正省下来的是「今天该不该下载」这一层判断
（`not_due()`），够新的那几家一个字节都不下。

本文档答三个问题：**一轮跑了什么** / **各家的闸门参数是怎么来的** / **删掉一家要动哪几处**。

---

## 1. 一轮的执行顺序

```
report_deps()          依赖钉版体检          只告警，不退出
report_registry()      注册名单体检          只告警，不退出（本轮新增，见 §5）
guard_dirty_tree()     data|series 之外的脏树 → FAILED 退出
check_specs.main()     contract_specs 结构体检 → 不过就 FAILED 退出
                       ↓
taiwan_fx()            台湾六页共用的 NTD/USD 底座（series/tsm_fx.csv）→ **必须在循环之前**
                       它是唯一跑在循环**前面**的公共表，理由见下（2026-09 新增）
                       ↓
for t in TICKERS:      28 家，逐家隔离：not_due? → fetch → build
    one(t)             一家失败只让这一家 FAIL，其余照常发布
                       多腿源的 DEGRADED → LEG_ALERTS：该家照常发布，但计入末行失败清单（接口见 §5）
                       ↓
taiwan_fx_rebuild()    汇率有新月份时补重建那六页里**循环没碰过**的几张
                       ↓
cost_sec()             /cost/ 的第二个数据源（SEC 申报层，季度/年度）→ 有新申报就重跑 /cost/
                       只在 cost 落在本轮名单里时才跑（**它看 --only，四张公共表都不看**）
tsm_6k()               /tsm/ 的月报 6-K 腿（背書保證 / 衍生性商品）→ 有新月份就重跑 /tsm/
                       只在 tsm 落在本轮名单里时才跑（同样看 --only）；日历预闸复用 tsm 的 LAG−EARLY，
                       追平后零请求；月末后第 16 天起逾期黏警报 → 计入失败清单（见 §2.6）
                       ↓
mops_remarks()         MOPS 月报備註栏（七家半导体页共用）→ 有新月份就重跑那七页
fee_rates()            季度费率表（六个单公司页共用）→ 有新季度就重跑那六页
fx()                   月度汇率表（横截面页共用）    → 不重跑任何页，见下
                       ↓
build_cross()          6 张横截面页，**无条件全跑**（它们没有闸门）
roster()               重建 data/roster.js（首页与导航目录）
audit_stale_cols()     陈旧列审计 → 只打印
audit_overdue_headline()  头条逾期（= 首页红点线）→ 计入失败清单（去重）
fails += LEG_ALERTS    腿级报警并入失败清单（去重）；必须排在 taiwan_fx_rebuild() 之后
                       ↓
verify_pages / check_yoy_caliber   收尾产物闸门 → 不过就 FAILED、不提交（两道都跑完、下面几块印完才判）
report_restatement_logs()
                       cache/ 里各 fetcher 的重述台账（行数 + mtime）→ 只告警，不改末行、不看 --only；
                       印在收尾闸门之后、末行之前，读日志尾部的人才看得见（理由见它定义上方与调用处的注释）
audit_manual_series()  人工维护表（公司債月表 / 董事会核准资本支出）陈旧提示 → 只打印，无陈旧项时一个字不印（见 §2.6）
report_leg_alerts()    腿级降级/报警明细 → 只打印，LEG_ALERTS 为空时一个字不印；贴近末行，理由同上
                       ↓
data_changed()?        忽略首行构建日期的正文比较 → 有变化才 commit + push
```

`fx()` 必须夹在 `fee_rates()` 与 `build_cross()` **之间**，两条理由缺一不可：

- **在 build_cross 之前**：读 `series/fx.csv` 的是横截面页的生成器。fx 在后、生成器在前的话，
  本轮的汇率更新要等下一轮才上页面；而下一轮 fx 已经没有新月份了（NOCHANGE），
  也就不会有任何东西再去催那些生成器 —— 更新会**永久停在「差一轮」**的状态。
- **fx 自己不重跑任何生成器**（`fee_rates()` 要重跑六家，它不用）：读 fx 的只有横截面页，
  而 `build_cross()` 紧接其后、每轮无条件全跑一遍。再喊一次是重复劳动。
  `fee_rates` 不一样 —— 读它的是**单公司页**，那六家这一轮可能整轮都没被碰过。

`taiwan_fx()` 是**唯一一张跑在按家循环之前**的公共表，因为它被读的时机不一样：
上面三张（備註 / 费率 / 汇率）都是「页面正文要用」，晚一步只是内容旧一轮；
`series/tsm_fx.csv` 却是 **build 的硬前置** —— 营收有 M 月而汇率没有 M 月，
`build/mrbase.py:898` 直接抛 `SpecError: series/tsm_fx.csv 缺月份 [M]`，那一家当轮 FAIL。

而这张表由 `fetch/tsm.py` 维护，被 **六页** 读（tsm / umc / ase / mtk / nanya / guc），
其中 **umc / ase / mtk / nanya / guc 五家在 `TICKERS` 里全排在 tsm 前面**。
也就是说「谁先披露完营收，谁就先撞上这堵墙」，一年里迟早轮得到：

> **2026-09-05 实测**：UMC 的 6-K 先到（2026-08），TSMC 的 xlsx 还停在 7 月、
> `tsm_fx.csv` 也还停在 2026-07。`--only umc,tsm` 复现 `umc FAIL`，
> `--only tsm,umc` 两家都 `NEW` —— 同一天、同一份数据，差别只有顺序。

更糟的是它**自我掩盖**：`fetch/umc.py` 已经把 2026-08 写进 `series/umc.csv` 了，
所以下一轮 `series_fingerprint` 不再变化 → `one()` 走 NOCHANGE 分支、连 build 都不再试。
`FAIL` 只在第一轮出现一次，之后每天都是干干净净的 `NOCHANGE`，而 `data/umc.js`
永远停在 2026-07 —— 又是 `one()` docstring 里「长得和健康的安静日一模一样」那个坑。

`taiwan_fx()` **不套下载闸门**（与 `fx()` 同理）：H.10 是美联储周更，月均在次月第 1 个
营业日就算得全，与台湾任何一家的披露节奏无关；套上按家闸门等于让底座陪最晚的那家一起等。
它**要**补重建消费页（与 `fee_rates()` 同理、与 `fx()` 相反）：读它的是单公司页，
那几家这一轮可能整轮没被碰过。补重建放在循环**之后**并跳过循环已建过的那几家 ——
在循环前建等于拿旧 CSV 白建一遍。实测汇率多一个月会改动页面正文：`data/tsm.js` 里
那句季度对表从「当季 7 月已实现 32.22」变成「当季 7、8 月已实现 32.13」。

**另外三张公共表都不是 ticker，也都不进 `TICKERS`**：一张表被六页 / 六页 / 七页共用（费率六个
单公司页、汇率六张横截面页、備註七张半导体页），挂在某一家的 ticker 下面，那一家被删掉时
另外几页的分母就跟着消失了。同理**都不进 `build/roster.py` 的 `LAG` / `GROUPS`** ——
那两处一个喂首页红点、一个被 `not_due()` 读，而公共表没有页、没有 `data/<t>.js`、
没有 `data_through`，两处都取不到它；只加 `LAG` 是一行谁都不读的死配置，
连 `GROUPS` 一起加则会在首页多出一张永远空白的卡片。

`mops_remarks()` 放在**按家循环之后**，而且它自己要**主动重跑那七页** —— 这一步不能省：
各家的月营收在次月第 2–15 天陆续到，而 MOPS 全市场汇总要等最后一家申报完（实测第 13 天）。
等備註到的那天，七家的 `not_due()` 早已判定「已追平 M 月」→ 全部 NOCHANGE、连 fetch 都不下。
不主动催重建的话，`series/mops_remarks.csv` 更新了而七页永远读不到，症状是
**当月引文与核对表末行永久缺席**（上个月的却在，因为下个月重建时补上了）——
和 `one()` docstring 里那条「长得和健康的安静日一模一样」是同一个坑。
也因此**不能**用「本轮已建过就跳过」优化：循环里那次 build 读的还是旧 CSV。

---

## 2. 各家的发布节奏与闸门参数

两个阈值共用一张 `LAG` 表（`build/roster.py`），但**偏置方向相反**，别再合并回去：

| | 谁用 | 公式 | 偏置方向的理由 |
|---|---|---|---|
| 首页红点 | 浏览器，按打开页面那一刻的日期算 | `LAG + GRACE`（宽限 5 天） | 早一天变红就是假警报；每季度假一次的警报，人很快学会无视 |
| 下载闸门 | `monthly_run.not_due()` | `max(0, LAG − EARLY)` | 早开闸一天 = 一个「还没发」的 HTTP 请求；晚开闸一天 = 公开页面挂旧数据一天 |

`EARLY` 默认 5；`EARLY_BY[t]` 是逐家例外，格式同 LAG = `(常规月, 季末月)`，
**必须写成元组** —— 取值处是 `EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]`，
写成裸整数会在下标那步 TypeError，崩掉的是**整轮** monthly_run，不只是那一家。

⚠️ **下面 §2.2 / §2.3 两张表是手抄的代码常量，改了 `LAG` / `EARLY_BY` / `FACT_GATE`
必须同步改表。** 有机检：`python3 tools/check_doc_gates.py` 逐行核 28 家的 `LAG` /
`EARLY_BY` / 闸门，连 §2.3 那句「13 + 15 = 28 家」一起核；闸门那一格双向认两种写法
——数字，或 `FACT_GATE` 里那几家的「事实闸门」，写反了哪个方向都报。它不在 cron 路径上
（理由见脚本头），跟着 README「改过生成器或引擎之后」那一组一起手工跑。

### 2.1 定这两个数的判据（本轮 9 家统一按这条）

> **`LAG` 照实测最晚那期定**（红点要的是上界）；
> **`EARLY` 照实测最早那期定**，于是 `开闸日 = LAG − EARLY = 实测最早发布日`。
> 默认 `EARLY=5` 已经让开闸日落在最早发布日**当天或更早**的，就不写 `EARLY_BY`（宁可给宽）。

⚠️ 还有一条比上面更优先的：**`LAG` 要跟着「哪条腿决定这一页的 `data_through`」走，
不是跟着官网最快那条腿走。** 多源的五家（NDAQ / TMX / DB1 / MIAX / LSEG）由
`build/specs/<t>.py` 的 `headline` 列决定 `data_through`；拿快腿的日子当 LAG，
红点会在慢腿到货之前每个月假红几天。NDAQ 就是被这条规则单独处理的（见表下的注）。
LSEG 是反方向的同一条规则：它的头条在**快腿**（Tradeweb）上，LAG 就只能照快腿定，
另外三条慢腿进 `slow_cols`、靠下一轮回补（见表下的注）。

### 2.2 13 家交易所

| ticker | 官方节奏（实测，出处见 `fetch/<t>.py` 的「发布节奏」节） | LAG | EARLY_BY | 闸门开在月末后第几天 |
|---|---|---|---|---|
| `cme`  | 次月第 1-2 个工作日 | (2, 2) | — | 0（次月 1 号） |
| `cboe` | 次月第 3 个美股交易日（32 期样本） | (4, 4) | — | 0 |
| `ice`  | 次月第 3 个美股交易日；124 期实测落在 3-6 号，最晚 6 号无例外 | (6, 6) | — | 1 |
| `ndaq` | 份额腿次月第 10 个工作日；IR 腿次月第 2-6 天 | (16, 16) | (14, 14) | 2 |
| `miax` | 次月第 3-5 个工作日；5 期实测日历第 3/4/5/5/7 天 | (8, 8) | — | 3 |
| `tmx`  | MX 腿次月第 1-4 个工作日（2026 年 7 期实测日历第 1-4 天） | (6, 6) | — | 1 |
| `enx`  | 90 个数据月逐月实测第 3-13 天，中位第 7；最晚 2024-04 → 05-13 | (13, 13) | (11, 11) | 2 |
| `db1`  | Eurex / FWB 快腿次月 1-5 日；IR 台账慢腿次月约 10 日 | (5, 5) | — | 0 |
| `lseg` | 头条腿（Tradeweb）88 期实测第 2-11 天，2021 起 n=65 收敛到第 2-8 天、中位第 5 | (8, 8) | (7, 7) | 1 |
| `hkex` | 次月上旬 | (10, 10) | — | 5 |
| `jpx`  | 每月第 5 个营业日；1 号撞周六 + 假期时最晚落在 8 号 | (8, 8) | — | 3 |
| `sgx`  | 95 个可信月实测，中位第 9 天，最晚一档第 13 天 | (13, 13) | (7, 7) | 6 |
| `asx`  | 次月第 3-8 个日历日，众数第 5-6；财年 6 月末**没有**季末月例外 | (8, 8) | — | 3 |

五条需要单独说明的：

- **`sgx` 的 `EARLY_BY=(7,7)` 不能省。** 默认闸门 = 13−5 = 第 8 天，而近 35 个月里有
  **8 个月（23%）在第 6-7 天就发了**（2024-04/05/07/10/11、2025-02/03/05）——
  那 8 次公开页面会挂 1-2 天陈旧数据。改成 7 之后闸门落在第 6 天，无一迟到。
- **`enx` 的 `EARLY_BY=(11,11)`**：13−11 = 第 2 天开闸，比实测最早的第 3 天再早一天。
  第 3 天出现过 4 次不是孤例，零余量迟早漏一次；代价只是每月一两个空请求
  （对方是 220KB 的 CDN 静态文件）。
- **`lseg` 有四条腿，LAG 与 `EARLY_BY` 都只跟头条那一条（Tradeweb）。**
  `build/specs/lseg.py` 的 `headline` 是 `tradeweb_volume_total_usd_tn` /
  `tradeweb_adv_total_usd_bn`，所以 `data_through` 由 Tradeweb 决定，LAG 也只能照它定：
  Tradeweb 月报 88 期实测落在次月第 2-11 天，2021 起 n=65 收敛到第 2-8 天、中位第 5，
  `LAG=(8,8)` 取的是那 65 期的最晚值。
  `EARLY_BY=(7,7)` 不能省：默认闸门 = 8−5 = 第 3 天，而**第 3 天正是分布最密的一档
  （88 期里出现 17 次）**，零余量；而且实测最早的一次是第 2 天（2023-01 数据 →
  2023-02-02），默认闸门必然漏掉它。8−7 = 第 1 天开闸，比实测最早再早一天。
  ⚠ **另外三条腿的滞后既不进 LAG 也不进 `EARLY_BY`。** LSE 订单簿的节奏见 `fetch/lseg_orderbook.py`
  的「实测发布节奏」节（2024 年起明显变慢）；一级市场 factsheet 中位 +2、约 90% 落在 +9 内、最晚 +27；
  LCH 两条快腿第 3-4 天（RepoClear 自己还要再滞后约两个月）。它们填的不是头条列，全在 `slow_cols` 里，
  靠「只填空不覆盖」在后续轮次回补。拿订单簿的节奏当 LAG，整页就得陪最慢那条腿一起晚上线 ——
  那是拿头条的新鲜度换慢腿的完整度。
  订单簿与一级市场两条腿登记在 `monthly_run.SLOW_LEGS['lseg']`（共用开闸日，数值见代码）：
  头条追平后，只要任一登记列欠货，闸门就保持开着。一级市场腿另有模块内逾期护栏
  （`fetch/lseg_primary.py` 的 `_MAX_PUBLISH_LAG_DAYS`），经 `fetch/lseg.py` 的 `DEGRADED`
  → `monthly_run.LEG_ALERTS` 计入末行失败清单；其余三条腿的普通抓取失败也走同一条路。
  LCH 那一路不登记（含 RepoClear 那条慢腿）。
- **`ndaq` 的两条腿差一个多星期，闸门与红点各跟各的腿。**
  `build/specs/ndaq.py` 的 headline 是 `share_us_cash_matched_*`，来自
  **Monthly Market Activity（慢腿）**，官方自述次月第 10 个工作日、实测 2026-06 数据 →
  2026-07-13。所以红点跟慢腿（LAG=16 是第 10 个工作日在最坏排列下的日历日上界）。
  闸门跟**快腿**（IR Monthly Reporting Sheet，实测次月第 2-6 天）：16−14 = 第 2 天开闸 ——
  快腿那一行会先落库（`update()` 建行、慢腿的 9 列留空，下一轮回补），闸门等到第 11 天
  才开的话，快腿的数要在源站上白挂九天。
  📌 **待复核**：`fetch/ndaq.py` 的 docstring 建议 `LAG=(6, 9)`，那是**按 IR 快腿写的**，
  与本仓 spec 把头条放在慢腿上的事实冲突。要么保持现状（本表这一行），要么让
  `build/specs/ndaq.py` 把 `share_*` 移进 `slow_cols`、改用 IR 列做头条 —— 后者是页面
  口径的改动，不该由接线这一步顺手做掉。
- **`miax` 头条走 API 腿，IR 报表腿与历史档案列登记在 `monthly_run.SLOW_LEGS`，开闸日 (3, 3) = 头条闸门。**
  `build/specs/miax.py` 的 headline 是两条 `_api_` 列（整月过完即可取），所以 `data_through` 由 API 腿推。
  IR 报表（实测第 3-7 天）和历史档案 PDF（比报表晚 1-4 天）晚几天。
  没登记时，2026-09 头条 09-03 落地后闸门关死，09-04 已发的报表零请求到 09-14，
  `/exchanges-na/`（期权池 MIAX 取 IR 口径）被钉在 Jul-26。
  LAG 与闸门两格照旧跟头条腿走。四条 RPC/capture 按设计晚一整期，**不**进 `SLOW_LEGS`，
  只进 `slow_cols` —— 两张表刻意不相交。

### 2.3 其余 15 家（非交易所，列此供对照）

13（§2.2）+ 15（本节）= **28 家**，与开头的家数一致。

| ticker | LAG | EARLY_BY | 闸门 |
|---|---|---|---|
| `ibkr` | (2, 2) | — | 0 |
| `cost` | (7, 7) | — | 2 |
| `guc`  | (7, 7) | — | 2 |
| `tsm`  | (10, 10) | — | 5 |
| `alchip` | (10, 10) | — | 5 |
| `mtk`  | (12, 12) | — | 7 |
| `hood` | (13, 30) | — | 8 / 25 |
| `nanya` | (13, 13) | — | 8 |
| `schw` | (17, 21) | — | 12 / 16 |
| `umc`  | (14, 14) | (10, 10) | 4 |
| `ase`  | (15, 15) | (7, 7) | 8 |
| `axp`  | (16, 16) | — | 11 |
| `msci` | (17, 17) | — | **事实闸门**（见下） |
| `spgi` | (18, 18) | (7, 7) | 11 |
| `lpla` | (21, 52) | — | 16 / 47 |

`umc` / `ase` 的 `EARLY_BY` 是 **2026-08-30 补的**（此前两家吃默认 `EARLY=5`，
本表相应写着「—」与旧闸门第 9 / 10 天，2026-09-07 订正）。判据与 §2.1 同一条
——「`EARLY` 照实测最早那期定」，这两家减默认 5 天之后仍**晚于**实测最早发布日：
`umc` 近 12 期实测第 4-8 天、最早第 4 天，默认闸门第 9 天 ⇒ **12/12 期全部迟到**；
`ase` 99 期实测最早第 8 天（出现 9 次），默认闸门第 10 天 ⇒ **51/99 期迟 1-2 天**。
⚠ **只动闸门、不动 LAG。** 闸门只经由差值 `LAG − EARLY` 进 `_due_month()`，改哪一边
对闸门等价；但 LAG 还独自喂着首页红点与 `audit_stale_cols()` 的 due 基线（传的是**裸
LAG**），改小它会连带压薄红点余量 —— `umc` 会只剩 1 天。逐条推导与「`nanya` 为什么
刻意不在这张表里」都在 `monthly_run.py` 的 `EARLY_BY` 注释里。

`schw` 的 `LAG` 是 **2026-09-14 从 `(14, 21)` 抬到 `(17, 21)`** 的（闸门随之从 9 / 16 变成 12 / 16）。
月报实测是次月**第 10 个美股交易日**（13/13 期电头，逐期见 `fetch/schw.py`「发布节奏」节）；
原先的 14 只是 9 月以外的日历日上界，9 月撞劳动节落在第 15-17 天，13 期里已有 6 期越过 14。
17 = 9/1 周六那一档的规则上界，照 §2.1「`LAG` 照实测最晚那期定」与 `spgi` 取规则上界的先例。
闸门第 12 天 = 规则最早发布日，默认 `EARLY=5` 已满足 §2.1，**不写 `EARLY_BY`**：开闸当天 07:56 那轮
就在，官方即使前一天（美东）先把文件挂上 CDN 也抓得到。代价是常规月红点从第 20 天推到第 23 天、
`fetch/schw.py` 的逾期对账红线从第 28 天推到第 31 天。

⚠️ **`msci` 不吃这张表**（2026-09-07 起）：它改走 `monthly_run.FACT_GATE` —— 不判日历，
每轮都真去问一次 `fetch/msci.py` 的 `latest_month()`。原因是它在 28 家里**唯一**闸门余量
算不出来、且结构上永远算不出来（源不自述发布日 ⇒ 进不了 `series/source_dates.csv`
⇒ 被排除在 §2.1 那条判据之外）；而日历闸门会让这个盲区**自我强化** —— 闸门不开就
一个请求都不发，源到底哪天发的因此永远观测不到。实测代价：2026-08 那期 09-04 就已上线
（月末后第 4 天），闸门第 12 天，晚了至少 8 天。**`LAG` 那一列仍然保留**，它另外喂着
首页红点、`audit_stale_cols()` 与 `audit_overdue_headline()` 三处，删了这三道对 msci 全失效。
准入条件见 `FACT_GATE` 的注释：探针必须真拿得到当下的源（msci 这一侧靠
`fetch/msci.py` 的 `_cache_key_url()` 每天轮换缓存键，固定 URL 会被边缘钉住 30 天）。

台湾半导体那 6 家（`ase` / `mtk` / `nanya` / `umc` / `alchip` / `guc`）是 2026-08 接入的，
与 `tsm` 同属一条披露节奏族，但 **LAG 逐家给、不共用一个数**：
台湾《证交法》只规定「次月 10 日前」这个**上界**，差异全在各家自订的惯例
（guc 官方财务日历预告次月 5 日、mtk 踩着第 10 天、nanya 中位第 5 天、ase 众数第 9-10 天）
与**本页数据源的额外滞后**上（`umc` 的 14 天是 SEC 6-K 上 EDGAR 的最坏滞后，
不是台湾公告日；`alchip` 不发月营收新闻稿、无预告，只能照法定上限取 10）。
逐家实测统计在各自的 `fetch/<t>.py` docstring 里。

这 7 家的季末月与常规月**不分档**（LAG 两个值相同）—— 月营收是法定月报，不随季报走，
所以没有 SCHW / LPLA / HOOD 那种「季末月没有独立月报」的问题。
（`spgi` 原本也在这份名单里，2026-08 复核后移出：官方 8-K 承诺 2026-01 数据起
固定「每月 15 日或顺延」、季末月不再例外，LAG 已从 `(16, 46)` 收成 `(18, 18)`、
EARLY_BY 从 `(5, 33)` 收成 `(7, 7)`，闸门两档并成第 11 天。
实测发布日全表见 `fetch/spgi.py` docstring 的「发布节奏」一节。）

### 2.4 四张公共表

| | 闸门 | 失败怎么处理 |
|---|---|---|
| `taiwan_fx` | **无，且刻意不给它套**（H.10 周更，与台湾各家披露节奏无关） | 计入失败清单 → PARTIAL；抓不到时六页里**没有新营收月的那几家一点信号都不会有**，所以它必须自己记一条 |
| `fee_rates` | 无（每天查一次，有新季度才写） | 计入失败清单 → PARTIAL |
| `fx` | **无，且刻意不给它套** | 计入失败清单 → PARTIAL |
| `mops_remarks` | 无日历闸门，用**事实闸门**：TWSE OpenAPI 的 `資料年月` | 计入失败清单 → PARTIAL，**七页照发** |

（`taiwan_fx` 与另外三张的分别：它跑在按家循环**之前**，因为它是 build 的硬前置而不是页面正文的一部分 —— 完整理由见 §1。）

**为什么 `mops_remarks` 不套 LAG**：它的闸门是证交所**汇总完全市场**才翻的那个
`資料年月`，模块 `latest_month()` 每轮问一次（一条 ~600KB JSON，比 fx 的 10 条 SDMX 还便宜）。
用事实闸门就不该再叠一层日历闸门 —— 叠上去只会在证交所翻早的月份把页面卡住。
（真要一个数是 16 = 实测第 13 天 + 撞假日的余量，但 **n=1**，按本文 `EARLY` 那条规矩
「在 n=1 的样本上做逐家微调＝把噪音当规律」，这个数不该被当成实测值用。）

**为什么它失败不阻断**：这条序列只喂**注脚** —— brief 一句引文 + 核对表一列，
没有任何数值、图、`data_through` 依赖它。抓失败时 `mrbase._remark()` 返回 `None`，
页面一个字都不说，且刻意**不**退化成「公司没填」（那是一句页面读不到的事实断言）。
降级后的页面是**残缺但诚实**，不属于「宁可不发也不发错」要拦的那个「错」。
而且「只扣七页」这个选项根本不存在：提交是整个 `data/` 一起走的，抛异常 ＝ 34 张页今天全不发。
但失败必须响：缺一句话没有任何视觉异常，roster 也不给它红点（它没有页）——
末行的 `PARTIAL` 是唯一信号，与上面 fx 那条是同一论证。

**为什么 fx 不套 `not_due` 的闸门**：那道闸门的前提是「M 月的数据要等 M+1 月才发」。
ECB 恰恰不是 —— 每个 TARGET2 营业日 14:15 CET 定盘、约 16:00 CET 发布，
**M 月这一行在 M 月最后一个营业日当天就齐了**（全仓唯一一条在数据月之内就能定稿的序列）。
套上闸门等于让它白等到次月，横截面页跟着晚一整轮。每天跑的代价是 10 条 SDMX 请求
（实测 17-32 秒），没有新月份时返回 `[]` 且 `series/fx.csv` 逐字节不变。

**为什么 fx 失败不吞**：汇率是所有跨市场图的换算层。它悄悄冻在上个月，页面上不会有
任何异常表现 —— 没有断笔、没有空值、没有红点（fx.csv 不上任何页面抬头），
只是份额与增长整体偏一点点。末行的 `PARTIAL` 是它唯一的故障信号。

### 2.5 `/cost/` 的第二个数据源：`cost_sec`（2026-09 接入）

`/cost/` 与 `/tsm/` 是全仓仅有的两页多源页 —— 按「在 `monthly_run.py` 里各自成一步」数
（lseg 那种一个 fetch 模块下挂几条腿的不算）；`/tsm/` 见 §2.6。`/cost/` 的两条腿：

| 腿 | 源 | 写什么 | 节奏 | 闸门 |
|---|---|---|---|---|
| 月度腿 | GlobeNewswire 月度销售稿（`fetch/cost.py`） | `series/cost.csv` | 零售月结束后首个周三 | 日历闸门，`LAG=(7,7)`、`EARLY` 默认 → 月末后第 2 天（见 §2.3） |
| SEC 腿 | EDGAR CIK **0000909832** 的 10-K / 10-Q / 8-K(EX-99.2)（`fetch/cost_sec.py`） | `series/cost_seg_q.csv` / `cost_tkt_q.csv` / `cost_fy.csv` / `cost_cohort.csv` / `cost_fy_be.csv` | 8-K 季末后约 4 周、10-Q 后 3-4 周、10-K 后 5-6 周 | **无闸门，每轮都跑**（理由见下） |

失败处理与四张公共表同档：**计入失败清单 → `PARTIAL`，不阻断本轮**。

**它为什么不是 `fetch/cost.py` 里的一条慢腿**（三条，任一条单独都够）：

- `one()` 在 import fetch 模块**之前**先问 `not_due('cost')`，而那个判断读的 `data_through`
  由**月度腿独家**推动（`build/cost.py` 的 `LATEST = df.index[-1]`，df 就是 `series/cost.csv`）。
  月度稿一落地闸门就关死，而 SEC 腿的到货日**全部**落在关死之后（10-Q 在季末后 3-4 周，
  那时当月的销售稿早发完了）。2026-09-03 实测 `not_due('cost')` 为真、日志里那行就是
  `cost NOCHANGE 线上已追平候选月 2026-08` —— 慢腿写法的实际效果是「永远不跑」。
- `SLOW_LEGS` 也顶不上来：`slow_pending()` 逐列扫的是 `series/<t>.csv`，而这条腿写的是
  另外四个文件。硬登记几列的话，`_due_month()` 算的是**月度**应到月份，而这是季度源 ——
  一年里八个月都会被判「欠货」，闸门被顶成天天下载，正是 `SLOW_LEGS` 那条
  ⚠「不要为永久停发的列建登记」的形状。
- 炸的范围反了：慢腿写法下 SEC 侧的解析错误会让 `one('cost')` 记 FAIL，
  连那天**月度**的新销售数据也一起不发。

**为什么不给它套闸门 —— 包括不拿 `latest_quarter()` 当跳过闸门**（这条是量过的，别回退）：

- `fetch/cost_sec.py::latest_quarter()` 走的是 `_submissions()`，而那个函数每次都把
  `subs.json` / `subs-001.json` 从缓存里删掉重下（件会从 recent 滚进 -001，缓存住会让那批件
  两边都读不到）。所以**探针与整轮 `update()` 打的是同样那两个请求**。
  2026-09-03 本机实测（缓存热）：探针 0.65 / 1.24 / 1.97s，整轮 update 1.34 / 1.56 / 1.76s ——
  跳过一次省的是半秒 CPU，不是一次网络往返。真能省的只有**冷缓存**那 88 MB / 2 分钟，
  而 `cache/` 在 cron 机器上是持久的（`tools/prune_cache.py` 的 `POLICY` 是白名单，
  `cost_sec` 这一族没登记、不会被清），那两分钟一辈子只付一次。
- 而且它会把 8-K 那条腿**瞎掉一个星期**：`latest_quarter()` 只看 10-K/10-Q，而
  `cost_tkt_q.csv` 的源是 8-K 的 EX-99.2，实测比同季 10-Q 早约一周
  （FY26Q3：8-K 2026-05-28、10-Q 2026-06-03）。拿 10-Q 的报告期当闸门，那六天里新一季的
  客单/客流在源上挂着而这边不取 —— 拿六天陈旧换半秒 CPU，方向反了。

⇒ 结论与 `fx` 同款：**每轮都跑**，代价是两个 JSON 请求（约 420 KB）+ 一秒多本地解析；
没有新申报时五张 CSV 逐字节不变、`update()` 返回 `[]`。

**`latest_quarter()` 改用在对账上，不是闸门**：`update()` 返回 `[]` 有两种含义 ——
「源上真没有新申报」与「有新申报但解析器没认出来」，两者在日志里长得一模一样
（README「不出声的失败」的判据）。所以每轮拿探针的报告期与 `series/cost_seg_q.csv` 的最新
`period_end` 对一次账（两边天生同尺：10-Q 的 `reportDate` = 该季末 = Q 行的 `period_end`），
源比库新就说明掉了一期 → 计入失败清单。这是 `fetch/cboe.py::_crosscheck_report_month`
那条「用独立于解析器的外部判据对账」的同款，只是解析器不归 `monthly_run.py` 管，
就把对账放在调用侧。**这个警报是黏的**（会一直响到有人去修），刻意如此 ——
另一头是「一期数据永久缺席而末行天天 `NOTHING_TO_DO`」。
对账**不覆盖 8-K 那条腿**，也不该覆盖：它比同季 10-Q 早约一周，拿它对账会天天误报。

**有新东西时它自己重跑 `build/cost.py`**（同 `mops_remarks` 要自己重跑那七页）：
触发器是 `series_fingerprint('cost')` 的前后差（`glob` 的 `series/cost*.csv` 本来就包含这五张表），
不是 `if added` —— `update()` 首次建表返回 `[]`，`cost_fy.csv` 的官方重述取最新值也不产生新主键。

**它写盘只落在 `series/` 与 `cache/cost_sec/`**（后者已 gitignore），
`PUBLISH = ['data', 'series']` 覆盖得住，`guard_dirty_tree()` 看不到它。
唯一的边角：`_write()` 先写 `series/cost_*.csv.tmp` 再 `os.replace`，
真在这两句之间被杀掉才会留下 `.tmp` —— 那个残留在 `series/` 里，会被 `git add series` 收走。

### 2.6 `/tsm/` 的第二个数据源：`tsm_6k`（2026-09 接入）

`/tsm/`「非营收月度披露」板块里的背書保證与衍生性商品两张表（Ex12/13/16/17 与汇总表下半张），
从 2026-08 这个数据月起由 SEC 月报 6-K 自动追加；2026-07 及以前的行是人工录的（同口径，
2023-03 起 41 个月离线重放 6 列逐格相等）。另外两张人工表（公司債、董事会核准资本支出）本轮不接自动写入，见本节末段。

| 腿 | 源 | 写什么 | 节奏 | 闸门 |
|---|---|---|---|---|
| 营收腿 | TSMC 官网 IR 月营收 xlsx（`fetch/tsm.py`） | `series/tsm.csv`（另维护六页共用的 `tsm_fx.csv`，见 §1） | 台湾法定次月 10 日前 | 日历闸门，`LAG=(10,10)`、`EARLY` 默认 → 月末后第 5 天（见 §2.3） |
| 月报 6-K 腿 | EDGAR CIK **0001046179** 月报 6-K 第 3/4 项（`fetch/tsm_6k.py`）+ MOPS `ajax_t05st11` 单格对账 | `series/tsm_guarantees.csv` / `tsm_derivatives.csv` | 与营收新闻稿同一份 6-K；42 期 filingDate 落在月末后第 6–13 天 | 与营收腿同一个开闸日，两表追平后零请求；月末后第 16 天起逾期黏警报 |

失败处理与 `cost_sec` 同档：**计入失败清单（失败名 `tsm_6k`，不是 ticker），不阻断本轮** ——
同一轮有发布，末行是 `PARTIAL`；没有发布，末行是 `FAILED 无更新且 N 家失败`。

**它为什么不是 `fetch/tsm.py` 里的一条慢腿**（同 §2.5 的三条）：

- `one()` 在 import fetch 模块之前先问 `not_due('tsm')`，读的 `data_through` 由**营收腿独家**推动。
  营收一入库闸门就关死整月：2026-09-11 07:23 那轮 tsm 2026-08 入库（`4d5c1f4`），此后 `not_due('tsm')`
  一直为真、`one('tsm')` 连 `fetch/tsm.py` 都不 import。6-K 只要比营收 xlsx 晚到一轮，慢腿写法就要等下个月。
- `SLOW_LEGS` 顶不上来：`slow_pending()` 只扫 `series/tsm.csv`，这两张表一列都不在里面。
- 炸的范围反了：严格语法任何一次拒绝都会让 `one('tsm')` 记 FAIL，连当天的营收新月份也一起不发。

**预闸与逾期黏警报**：开闸日 = `_due_month((LAG − EARLY))`，直接复用 tsm 那一格（月末后第 5 天，
比实测最早的第 6 天早一天），不另立节奏表。两表末月的较小值追平候选月就 `NOCHANGE`、**零请求**；
没追平时每轮 1 个 submissions JSON（最近 3 个月的重述体检读缓存件），到货那轮多 1 份正文 + 1 个 MOPS POST。
逾期线 = `_due_month((LAG + GRACE + 1))` = 月末后第 16 天，与首页红点、`audit_overdue_headline()` 同一条算术，
比实测最晚的第 13 天多留 3 天；过线仍没入库就每轮 `tsm_6k FAIL 逾期…`，**黏到真入库或有人修**。
它必须自己响：`/tsm/` 的红点跟的是营收腿，6-K 腿冻住时首页照样绿点，页面上只剩 `_lag_note()` 那句滞后说明。

**MOPS `ajax_t05st11` 对账只盖两格**：那一页只有汇总 —— 本公司「至本月份累計餘額」（= `approved_total_k`）
与「最高額度」（= 6-K 第 3 项 TSMC 首行限额），外加「本公司對子公司背書保證累計餘額」必须等于累計餘額。
页取到了而对不上、内部不自洽、或页够长却认不出版式 → 抛异常、两表都不写；网络错 / 查無 / Overrun 限流页 /
落错页 / 短页 → 只打一行 `[tsm_6k][warn] 护栏失效：…`、照常写，事后不补做。
两张表 6 列里只有核准合计这一列有外部证人；其余五列（衍生品名目与市价、在外合计、亚利桑那核准与在外）
只靠严格语法、最近 3 个月重放和行级不变量（核准 ≥ 在外 ≥ 0、亚利桑那恰好一行、首行限额 ≥ TSMC 各行核准之和）把关。

**写入、补建戳与重述**：两张表都校验完才写，每张各自写 tmp（落 `cache/tsm_6k/`，不在 `series/` 留 `.tmp`）
再 `os.replace` —— 不是跨文件原子，进程死在两次替换之间时下一轮只补落后的那张。
有新月份（或两表指纹变了）它自己重跑 `build/tsm.py`（循环里那次读的还是旧 CSV），建成后把两表指纹写进
`cache/tsm_6k/_last_built.sha256`（补建戳）；戳与当前指纹不符就再建一次。CSV 写成了而页面没建成时
（重建失败、进程被杀、本轮 `one('tsm')` 已 FAIL 而推迟），下一轮闸门已关、`update()` 不再被调用 ——
没有这张戳，页面会一声不响地停在旧图。首轮上线戳不存在，会无条件重建一次 `/tsm/`；`--dry-run` 不写戳。
没有新月份、只因指纹 / 戳不符而补建成功时，状态行之后另印 `tsm_6k REBUILT 补建 /tsm/（原因）`（只打印，不改末行）；
补建失败的 `tsm FAIL` 行印的是 `build/tsm.py` stderr 的尾部（折成一行），不是命令路径。
最近 3 个月的月报每轮与库内逐格比，不一致（6-K/A 重述或解析变形）就抛异常、列出 月/列/库内/官方/accession，
不改写，也挡住新月份写入（同 `fetch/umc.py` 口径坑 7）。

**公司債与董事会核准资本支出仍人工维护**：`monthly_run.audit_manual_series()` 只打印陈旧提示 ——
公司債月表按 `month` 列、月末后第 32 天（月末 6-K 实测次月第 21–26 天 + GRACE 5 + 1），
资本支出按 `filed` 列、距上次申报超过 135 天（44 次申报相邻最长 120 天 + 15）。不计入失败清单、不看 `--only`，
没有陈旧项时一个字不印。自动化待所有者定（§7）。

---

## 3. 生成器怎么找：`builder(t)`

仓库里同时存在三种生成器，`monthly_run.builder()` 按顺序试，**判据一律是「文件在不在」，
不是「这个 ticker 叫什么名字」**：

| 顺序 | 找什么 | 谁在用 |
|---|---|---|
| 1 | `build/<t>.py` | 12 家手写单公司页（11 家老页 + `ice`，后者 2026-09 从 `build/specs/ice.py` 改成手写），一家一份手写生成器；名字里没有连字符的两张横截面（`wealth` / `exchanges12`）也命中这条。**台湾半导体 7 家也命中这条**，但它们的 `build/<t>.py` 只是薄壳，正文在 `build/mrbase.py` + `build/mrspecs/<t>.py` |
| 2 | `build/<t 下划线版>.py` | 带连字符的 4 张横截面：目录 `exchanges-na` ↔ 生成器 `build/exchanges_na.py`（连字符不能做模块名），`-eu` / `-apac` / `-products` 同理 |
| 3 | `build/single.py <t>`（需 `build/specs/<t>.py`） | 10 家新交易所里的 9 家（`ice` 除外，见第 1 条），通用底座 + 一家一份配置 |

**半导体那 7 家为什么不走第 3 条**：它们有自己的底座 `build/mrbase.py`（月度营收图列，
与 `single.py` 的图列完全不同），走薄壳是为了不给 `builder()` 加第四条分支。
代价是 `build/single.py` 必须挡住它们 —— 已加单向守卫：**`build/<t>.py` 在不在**，
在就跳过（`build/single.py:6690`，与 `builder()` 同源，两边都只看文件、不认名字）。
判据 2026-09 从「`build/<t>.py` 里有没有 `mrbase` 字样」放宽成现在这条，起因正是 `ice`：
手写页里没有 `mrbase` 这个词，旧判据认不出来。没有这道守卫时，人手跑一次
`python3 build/single.py --all` 会把这些页**静默打回 `single.py` 的旧图列**
（不报错、页面照出，只是图全换了）。

这是「删得干净」的关键：`builder()` 不认得任何一家的名字，删掉 `build/specs/sgx.py`
之后 `monthly_run` 立刻不再知道有 sgx 这回事。如果写成
`if t in EXCHANGES: 用 single.py`，`EXCHANGES` 就成了第二处必须同步的名单，
而删除时漏掉第二处的后果是**每天一条 FAIL**。

`build_cross()` 里找不到生成器的那一条**跳过而不是记失败** —— CROSS 名单可以先于生成器
登记，删页时也可以先删生成器；两种半成品状态都不该让整轮变 PARTIAL。

---

## 4. 怎么删掉一家（用户明说可能删掉部分非美国交易所）

一家 = **5 处注册 + 3 个文件**。全部是「删掉一整行」或「删掉一个文件」，没有需要改写的逻辑。

以删掉 `sgx` 为例：

```bash
cd /Users/hainan/Projects/monthly-op-dashboards

# ① 文件（3 个）
rm build/specs/sgx.py          # 页面配置（删掉它，builder() 就不再认识 sgx）
rm data/sgx.js                 # 产物
rm -rf sgx/                    # 页面壳

# ② 注册（5 行，逐行删）
#   monthly_run.py   EXCHANGES 里的  'sgx',  这一行
#   build/roster.py  EXCH 里的       'sgx',  这一行
#   build/roster.py  LAG 里的        'sgx':  这一行
#   build/roster.py  META 里的       'sgx':  这一行
#   monthly_run.py   EARLY_BY 里的   'sgx':  那一段（EARLY_BY 现有 spgi / enx / sgx / lseg / ndaq / umc / ase 七家，交易所是中间四家）
#   （另：若该家在 monthly_run.py 的 SLOW_LEGS 里有登记，那一段一并删 —— 留着不影响 cron，one() 不再调它，
#    但手工跑的 test_slow_legs.py 不变式会红；build/test_guards.py 里按 fetch 文件是否存在 skip 的组不用改）

# ③ 抓取侧（可留可删；留着不会被任何东西调用）
rm fetch/sgx.py series/sgx.csv  # 想彻底清掉历史数据时才删

# ④ 验证
python3 -c "import importlib.util as u; s=u.spec_from_file_location('m','monthly_run.py'); \
m=u.module_from_spec(s); s.loader.exec_module(m); print(m.check_registry() or '名单一致')"
python3 build/roster.py         # 应打印少一页，且不报 KeyError
python3 build/make_shells12.py  # 应少写一个壳
```

**横截面页里若还引用被删的那家**（删 `sgx` 时 `exchanges-apac` 与 `exchanges-products`
的成员里都有它 —— 一家交易所通常同时出现在地理轴和标的轴两张页上，两张都要查），
那张页的生成器会自己打印「成员没齐」并以退出码 0 结束 —— 不会让整轮变 PARTIAL，
但那张页会停更。要么同时删掉那张横截面页（同样是删 `build/exchanges_apac.py` +
`data/` + 目录 + `roster.GROUPS['cross']` 那一行 + `monthly_run.CROSS` 那一行），
要么去它的成员名单里把这家去掉。

**删掉一整张横截面页**的完整步骤已经实测跑通一次（2026-08-06 删 `/exchanges-intl/`，
它是 `-eu` / `-apac` 拆分前的旧合页）—— 逐步清单与实测输出见 `docs/DELIVERY.md §4.4`，
比这里的推演可靠，删页时照那一节做。

### 删掉 `/cost/` 的 SEC 腿意味着什么（它不是「一家」，删法也不一样）

`cost_sec` **不在上面那张「5 处注册 + 3 个文件」的清单里** —— 它没有页、没有 `data/<t>.js`、
不在 `TICKERS` / `CROSS` / `roster.GROUPS` / `roster.LAG` 里任何一处，所以 `check_registry()`
既不认识它、也不会因为它告警。删它 = 删两处：

```bash
#   monthly_run.py   main() 里 `if 'cost' in todo: fails += cost_sec()` 那两行
#                    （函数 cost_sec() 与 _cost_sec_behind() 留着不会被调用，想清干净就一起删）
rm fetch/cost_sec.py
rm series/cost_seg_q.csv series/cost_tkt_q.csv series/cost_fy.csv series/cost_cohort.csv series/cost_fy_be.csv
rm -rf cache/cost_sec        # 88 MB，可重下
```

⚠ **两处的顺序与后果**：`monthly_run.py` 那两行删掉、`fetch/cost_sec.py` 还留着，是**静默停更**
（没人调用它，五张 CSV 就此冻住，而 `/cost/` 的红点跟的是月度腿、照样是绿的）；
反过来只删 `fetch/cost_sec.py` 不删那两行是**安全**的 —— `cost_sec()` 第一句就是
「文件不在就返回空清单」，与 `mops_remarks` / `fee_rates` / `fx` 同款。所以真要删，
**先删 `monthly_run.py` 那两行**，别只删文件。

⚠ **删五张 CSV 之前先看 `build/cost.py` 还读不读它们**：`/cost/` 页上凡是分部收入 /
客单客流 / 财年单店经济 / 开业年份矩阵 / Exhibit 16 那两条盈亏平衡线的图都由它们喂，
CSV 没了那些图会缺数据 —— 其中 `cost_fy_be.csv` 是 `build/cost.py` **硬要求**的
（文件不在就 `SystemExit`），不像别的表那样只是少几张图。
月度腿（`series/cost.csv`）与它们**互不读写**，所以只删 SEC 腿不会影响月度那部分。

### 删掉 `/tsm/` 的 6-K 腿

`tsm_6k` 与 `cost_sec` 同一个形状：没有自己的页，不在 `TICKERS` / `CROSS` / `roster.GROUPS` / `roster.LAG`
里任何一处，所以不在上面「5 处注册 + 3 个文件」的清单里，`check_registry()` 也不认识它。删法（先删调用，再删模块）：

```bash
#   monthly_run.py             main() 里 `if 'tsm' in todo: fails += tsm_6k(...)` 那两行
#                              （函数 tsm_6k() 留着不会被调用；想清干净就连它一起删）
#   test_monthly_run_tsm6k.py  **必须同时改**，不是可选的清理 —— 见下面第一条 ⚠
rm fetch/tsm_6k.py fetch/test_tsm_6k.py
rm -rf cache/tsm_6k          # 月报正文缓存 + 补建戳，可重下
```

⚠ **删了 `main()` 那两行，就必须同时处理 `test_monthly_run_tsm6k.py`**：它的 `TestMainWiring.test_call_order`
按「独占一行的语句」钉 `main()` 里 `tsm_6k` 的调用位置，那两行一删它当场变红（这份测试不在 preflight 里，
不会拦 cron，但仓库的回归网从此是红的）。最少删掉 `TestMainWiring`，或只删 `test_call_order` 里涉及
`if 'tsm' in todo:` 与 `tsm_6k(...)` 调用的三条断言；连函数 `tsm_6k()` 一起删时，还要删直接调用它的
`TestGate` / `TestOverdueBoundary` / `TestRebuildStamp`。同一份文件里的 `TestAuditManualSeries` 与删腿无关
（`audit_manual_series()` 仍在跑）—— 整份删文件会连它一起丢。

⚠ **两张 CSV 不删**：`series/tsm_guarantees.csv` 与 `series/tsm_derivatives.csv` 由
`build/mrspecs/_tsm_extra.py` 的 `_load()` 直接 `pd.read_csv`（Ex12/13/16/17 与汇总表下半张），
删了 `/tsm/` 当场建不出来。删腿之后它们回到人工维护，页面的 `_lag_note()` 照实印滞后；
顺手把 `_tsm_extra.py` 文件头「刷新」一节与 `_LAG_WHY` 里「随月报 6-K 自动入库」那两句改回人工的说法。

⚠ **两处的后果**：只删 `monthly_run.py` 那两行、模块留着 = **静默停更**（没人调用它，两表就此冻住；
`/tsm/` 的红点跟营收腿、照样是绿的，逾期黏警报也随调用一起没了，只剩页面上那句滞后说明）；
只删 `fetch/tsm_6k.py`、那两行留着则不会崩 —— `tsm_6k()` 第一句就是「文件不在就返回空清单」，
与 `cost_sec` / `mops_remarks` 同款。

`audit_manual_series()` 管的是公司債 / 董事会核准资本支出两张人工表，与 6-K 腿无关，删腿不用动它；
整页 `/tsm/` 都删时再把 `MANUAL_SERIES` 那两条一起删（表不在时它只是静默跳过，不报错）。

### 忘了其中一处会怎样

`monthly_run.check_registry()` 每轮开跑前对一次名单，**只告警不退出**
（一个忘掉的名字不该让另外二十页今天不发布）。两个方向的症状都很难由现象反推回原因，
所以它把话说全：

- **monthly_run 留着、roster 删了** → 每天照常抓、照常写 `series/`，但页面不在导航里，
  首页也不给它判红点。数据在更新，没有人看得见。
- **roster 留着、monthly_run 删了** → 导航挂着一个再也不更新的入口，首页给它判红点，
  而日志里一个字都没有 —— 看上去像「抓取悄悄坏了」，实际是根本没人去抓。

`build/roster.py` 里还有一道：`GROUPS` 有而 `META` 没有的 ticker 会抛一条写明该去哪儿补的
`KeyError`（裸 `KeyError: 'sgx'` 看不出要补哪张表）。

---

## 5. 怎么加一家

反着来。加一家新交易所（走通用底座那条路）：

1. `fetch/<t>.py` —— `update(series_dir, cache_dir)` 返回新增月份列表，幂等、只填空不覆盖。
   docstring 里必须写「发布节奏」的**实测统计**（几期样本、日分布、最早/最晚），
   §2 的两个数就是从那里抄的。
   多腿源（一家的数据来自几份互相独立的上游文件）可选再暴露模块级 `DEGRADED: dict`
   （{腿名: '异常类型: 消息'}，每轮 `update()` 开头清空，填入本轮降级或报警的腿）：
   `monthly_run.one()` 读到非空就记进 `LEG_ALERTS`，该家照常发布、但计入末行失败清单，
   明细由 `report_leg_alerts()` 在末行前印。现成的写法见 `fetch/lseg.py`。
2. `build/specs/<t>.py` —— 见 `docs/SINGLE_SPEC.md`。**注意 headline 选哪条腿**：
   它决定 `data_through`，也就决定 §2 的 LAG 该跟哪条腿。
3. `python3 build/make_shells12.py` —— 壳自动生成（它扫 `build/specs/`，不需要登记）。
4. `monthly_run.py` 的 `EXCHANGES` 加一行；`build/roster.py` 的 `EXCH` / `LAG` / `META`
   各加一行；闸门迟到了才加 `EARLY_BY`。
5. `python3 build/single.py <t>` → `python3 build/roster.py` → 打开页面看导航。

**加一家台湾半导体月度营收页**走的是另一条底座，第 2、5 步不同：配置写
`build/mrspecs/<t>.py`（字段契约在 `build/mrbase.py` 自己的 §1，不在 `docs/SINGLE_SPEC.md`），
再加一个引用 `mrbase` 的薄壳 `build/<t>.py`，跑 `python3 build/<t>.py`。
第 3 步不变 —— `make_shells12.singles()` 的枚举源已经是 `build/specs/ ∪ build/mrspecs/`
两个目录的并集，只扫 `specs/` 会**静默漏掉壳**（页面 404，但 cron 一切正常）。
第 4 步的 `EXCHANGES` 换成 `TICKERS`，`roster.EXCH` 换成 `GROUPS` 的 `semi` 组。

---

## 6. 导航为什么排成三行

`build/roster.py` 的 `GROUPS` 每组带一个 `nav_row`，`assets/page.js` 照它把导航铺成几条
独立的 `.navrow`：

```
第 1 行   券商与财富管理 · 数据与指数 · 消费与信贷 · 半导体            [总览]
第 2 行   交易所（13 家，北美 6 → 欧洲 3 → 亚太 4）
第 3 行   横截面（6 张页）
```

原来整条导航是一个 flex 容器靠 `flex-wrap` 自动折行。交易所从 3 家扩到 12 家之后，
折行断点随窗口宽度乱跳 ——「交易所」这个标签可能落在上一行末尾，它的 12 个 ticker 散在
两行里，中间还夹着「数据与指数」。**分组标签全在，分组信息没了。**
所以行的划分改由数据说了算；`.navrow` 自己仍然 wrap，窄屏上现在这 13 个 ticker 折成两行，
但只会与**同组**的折在一起。

`row` 缺失时落到第 1 行 —— 老 `data/roster.js` 撞上新 `assets/page.js` 时退化成原来的
一整条，不白屏（`data/` 与 `assets/` 是两次 commit，上线顺序不可控）。

---

## 7. 已知待办

| 事项 | 影响 | 归属 |
|---|---|---|
| `series/contract_specs.csv` 74 行里 33 行没填基期价，其中 **7 个 product_id 的缺口落在 `/exchanges12/` 的成员腿上**（清单见 `docs/DELIVERY.md` §3.1） | 页已上线（按降级规则生成 `data/exchanges12.js`）：水平值与占比图只画常数齐备的家，增长类图 12 家全上 —— 缺常数的多块家给紧上下界而不是点值；缺口清单由运行时算出并打进页面正文（`build/exchanges12.py` 的 GAP_REASONS） | 补常数那一步 |
| ⛔ **不是待办**：`ICE_STIR` / `ICE_MLTIR` 的基期价**永远留空** | 两者已在 `build/pools.py` 用 `contracts_only=True` 显式声明为永久张数口径；理由见 `docs/DELIVERY.md` §3.2。**不要再去撞 ICE 的 reCAPTCHA** | 已定案 |
| `ndaq` 的 headline 在慢腿上（见 §2.2 注） | 红点与闸门被迫拆成两条腿；改法是动 spec，不是动接线 | 页面口径 |
| `--only` 不跳过 `fee_rates` / `fx` / `mops_remarks` / `build_cross` | 调试单家时仍会打 ECB、费率源与 TWSE（各一个站） | 沿用既有行为，未改 |
| `cost_sec` 与 `tsm_6k` **两步看 `--only`** | 各自只有一个消费者（`/cost/`、`/tsm/`），`--only cme` 没理由去打 EDGAR / MOPS、更没理由改写 `data/cost.js` / `data/tsm.js`；生产环境 `todo` 恒等于 `TICKERS`，cron 行为与不看 `--only` 完全一样 | 有意为之，见 §2.5 / §2.6 |
| `tsm_capex_approvals` / `tsm_bonds_*` 仍人工维护 | `audit_manual_series()` 只打印陈旧提示（公司債月末后第 32 天、资本支出距上次申报超过 135 天），不计入失败清单、不推送 —— 漏录只在日志尾部看得见 | 自动化待所有者定 |
