# cron 接线：一轮跑什么、各家什么时候开闸、怎么删掉一家

入口是 `monthly_run.py`，**每天跑一次**。天天跑不是浪费：21 家的披露日从次月 1 号散到
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
for t in TICKERS:      21 家，逐家隔离：not_due? → fetch → build
    one(t)             一家失败只让这一家 FAIL，其余照常发布
                       ↓
fee_rates()            季度费率表（六个单公司页共用）→ 有新季度就重跑那六页
fx()                   月度汇率表（横截面页共用）    → 不重跑任何页，见下
                       ↓
build_cross()          6 张横截面页，**无条件全跑**（它们没有闸门）
roster()               重建 data/roster.js（首页与导航目录）
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

**两张公共表都不是 ticker，也都不进 `TICKERS`**：一张表被六页 / 六页共用（费率六个
单公司页、汇率六张横截面页），挂在某一家的 ticker 下面，那一家被删掉时另外几页的
分母就跟着消失了。

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

### 2.1 定这两个数的判据（本轮 9 家统一按这条）

> **`LAG` 照实测最晚那期定**（红点要的是上界）；
> **`EARLY` 照实测最早那期定**，于是 `开闸日 = LAG − EARLY = 实测最早发布日`。
> 默认 `EARLY=5` 已经让开闸日落在最早发布日**当天或更早**的，就不写 `EARLY_BY`（宁可给宽）。

⚠️ 还有一条比上面更优先的：**`LAG` 要跟着「哪条腿决定这一页的 `data_through`」走，
不是跟着官网最快那条腿走。** 多源的四家（NDAQ / TMX / DB1 / MIAX）由
`build/specs/<t>.py` 的 `headline` 列决定 `data_through`；拿快腿的日子当 LAG，
红点会在慢腿到货之前每个月假红几天。NDAQ 就是被这条规则单独处理的（见表下的注）。

### 2.2 12 家交易所

| ticker | 官方节奏（实测，出处见 `fetch/<t>.py` 的「发布节奏」节） | LAG | EARLY_BY | 闸门开在月末后第几天 |
|---|---|---|---|---|
| `cme`  | 次月第 1-2 个工作日 | (2, 2) | — | 0（次月 1 号） |
| `cboe` | 次月第 3 个美股交易日（32 期样本） | (4, 4) | — | 0 |
| `ice`  | 次月第 3 个美股交易日；124 期实测落在 3-6 号，最晚 6 号无例外 | (6, 6) | — | 1 |
| `ndaq` | 份额腿次月第 10 个工作日；IR 腿次月第 2-6 天 | (16, 16) | (14, 14) | 2 |
| `miax` | 次月第 3-5 个工作日；4 期实测日历第 3/5/5/7 天 | (8, 8) | — | 3 |
| `tmx`  | MX 腿次月第 1-4 个工作日（2026 年 7 期实测日历第 1-4 天） | (6, 6) | — | 1 |
| `enx`  | 90 个数据月逐月实测第 3-13 天，中位第 7；最晚 2024-04 → 05-13 | (13, 13) | (11, 11) | 2 |
| `db1`  | Eurex / FWB 快腿次月 1-5 日；IR 台账慢腿次月约 10 日 | (5, 5) | — | 0 |
| `hkex` | 次月上旬 | (10, 10) | — | 5 |
| `jpx`  | 每月第 5 个营业日；1 号撞周六 + 假期时最晚落在 8 号 | (8, 8) | — | 3 |
| `sgx`  | 95 个可信月实测，中位第 9 天，最晚一档第 13 天 | (13, 13) | (7, 7) | 6 |
| `asx`  | 次月第 3-8 个日历日，众数第 5-6；财年 6 月末**没有**季末月例外 | (8, 8) | — | 3 |

三条需要单独说明的：

- **`sgx` 的 `EARLY_BY=(7,7)` 不能省。** 默认闸门 = 13−5 = 第 8 天，而近 35 个月里有
  **8 个月（23%）在第 6-7 天就发了**（2024-04/05/07/10/11、2025-02/03/05）——
  那 8 次公开页面会挂 1-2 天陈旧数据。改成 7 之后闸门落在第 6 天，无一迟到。
- **`enx` 的 `EARLY_BY=(11,11)`**：13−11 = 第 2 天开闸，比实测最早的第 3 天再早一天。
  第 3 天出现过 4 次不是孤例，零余量迟早漏一次；代价只是每月一两个空请求
  （对方是 220KB 的 CDN 静态文件）。
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

### 2.3 其余 9 家（本轮未改动，列此供对照）

| ticker | LAG | EARLY_BY | 闸门 |
|---|---|---|---|
| `ibkr` | (2, 2) | — | 0 |
| `cost` | (7, 7) | — | 2 |
| `tsm`  | (10, 10) | — | 5 |
| `hood` | (13, 30) | — | 8 / 25 |
| `schw` | (14, 21) | — | 9 / 16 |
| `spgi` | (16, 46) | (5, 33) | 11 / 13 |
| `axp`  | (16, 16) | — | 11 |
| `msci` | (17, 17) | — | 12 |
| `lpla` | (21, 52) | — | 16 / 47 |

### 2.4 两张公共表

| | 闸门 | 失败怎么处理 |
|---|---|---|
| `fee_rates` | 无（每天查一次，有新季度才写） | 计入失败清单 → PARTIAL |
| `fx` | **无，且刻意不给它套** | 计入失败清单 → PARTIAL |

**为什么 fx 不套 `not_due` 的闸门**：那道闸门的前提是「M 月的数据要等 M+1 月才发」。
ECB 恰恰不是 —— 每个 TARGET2 营业日 14:15 CET 定盘、约 16:00 CET 发布，
**M 月这一行在 M 月最后一个营业日当天就齐了**（全仓唯一一条在数据月之内就能定稿的序列）。
套上闸门等于让它白等到次月，横截面页跟着晚一整轮。每天跑的代价是 10 条 SDMX 请求
（实测 17-32 秒），没有新月份时返回 `[]` 且 `series/fx.csv` 逐字节不变。

**为什么 fx 失败不吞**：汇率是所有跨市场图的换算层。它悄悄冻在上个月，页面上不会有
任何异常表现 —— 没有断笔、没有空值、没有红点（fx.csv 不上任何页面抬头），
只是份额与增长整体偏一点点。末行的 `PARTIAL` 是它唯一的故障信号。

---

## 3. 生成器怎么找：`builder(t)`

仓库里同时存在三种生成器，`monthly_run.builder()` 按顺序试，**判据一律是「文件在不在」，
不是「这个 ticker 叫什么名字」**：

| 顺序 | 找什么 | 谁在用 |
|---|---|---|
| 1 | `build/<t>.py` | 12 家老单公司页，一家一份手写生成器；名字里没有连字符的两张横截面（`wealth` / `exchanges12`）也命中这条 |
| 2 | `build/<t 下划线版>.py` | 带连字符的 4 张横截面：目录 `exchanges-na` ↔ 生成器 `build/exchanges_na.py`（连字符不能做模块名），`-eu` / `-apac` / `-products` 同理 |
| 3 | `build/single.py <t>`（需 `build/specs/<t>.py`） | 9 家新交易所，通用底座 + 一家一份配置 |

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
#   monthly_run.py   EARLY_BY 里的   'sgx':  那一段（EARLY_BY 现有 spgi / enx / sgx / ndaq 四家，交易所是后三家）

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
2. `build/specs/<t>.py` —— 见 `docs/SINGLE_SPEC.md`。**注意 headline 选哪条腿**：
   它决定 `data_through`，也就决定 §2 的 LAG 该跟哪条腿。
3. `python3 build/make_shells12.py` —— 壳自动生成（它扫 `build/specs/`，不需要登记）。
4. `monthly_run.py` 的 `EXCHANGES` 加一行；`build/roster.py` 的 `EXCH` / `LAG` / `META`
   各加一行；闸门迟到了才加 `EARLY_BY`。
5. `python3 build/single.py <t>` → `python3 build/roster.py` → 打开页面看导航。

---

## 6. 导航为什么排成三行

`build/roster.py` 的 `GROUPS` 每组带一个 `nav_row`，`assets/page.js` 照它把导航铺成几条
独立的 `.navrow`：

```
第 1 行   券商与财富管理 · 数据与指数 · 消费与信贷 · 半导体            [总览]
第 2 行   交易所（12 家，北美 6 → 欧洲 2 → 亚太 4）
第 3 行   横截面（6 张页）
```

原来整条导航是一个 flex 容器靠 `flex-wrap` 自动折行。交易所从 3 家扩到 12 家之后，
折行断点随窗口宽度乱跳 ——「交易所」这个标签可能落在上一行末尾，它的 12 个 ticker 散在
两行里，中间还夹着「数据与指数」。**分组标签全在，分组信息没了。**
所以行的划分改由数据说了算；`.navrow` 自己仍然 wrap，窄屏上 12 个 ticker 折成两行，
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
| `--only` 不跳过 `fee_rates` / `fx` / `build_cross` | 调试单家时仍会打 ECB 与费率源（各一个站） | 沿用既有行为，未改 |
