# 月度经营指标看板（28 家）

28 家公司按月披露的经营数据，做成一套交互看板，版式仿 Goldman Sachs GIR exhibit。
数据全部来自公司官网 IR 或 SEC 申报的原始披露，不含任何券商研报的观点或数据。

**看板地址：** https://hzhan7.github.io/Monthly-OP-Dashboards/

一行一族（与导航分行一致，顺序照 `build/roster.py` 的 `GROUPS`）：

```
/            总览（28 家 + 6 张横截面，含各家新鲜度红点）
/ibkr/ /schw/ /lpla/ /hood/         券商与财富管理
/cme/ /cboe/ /ice/ /ndaq/ /miax/ /tmx/ /enx/ /db1/ /lseg/ /hkex/ /jpx/ /sgx/ /asx/   交易所（北美 6 → 欧洲 3 → 亚太 4）
/msci/ /spgi/                       数据与指数
/cost/ /axp/                        消费与信贷
/tsm/ /ase/ /mtk/ /nanya/ /umc/ /alchip/ /guc/   半导体（台湾月度营收，7 家）
/exchanges12/ /exchanges-na/ /exchanges-eu/ /exchanges-apac/ /exchanges-products/ /wealth/   横截面（同组公司放同一张图比）
```

横截面六张页各管一件事：`/exchanges12/` 12 家交易所总览（定基名义额）、
`/exchanges-na/` 北美真份额、`/exchanges-eu/` 欧洲现货竞争、`/exchanges-apac/` 亚太增长对比、
`/exchanges-products/` 标的轴（利率 / 股指 / 单股ETF期权 / 能源 / 农产品 / FX 即期）、
`/wealth/` 财富管理组。原 `/exchanges/`（CME / Cboe / HKEX 三家旧横截面）已被 12 家版
取代，2026-08-07 删除。

**LSEG（`/lseg/`）本轮只上了单公司页，暂未进任何一张横截面页。** `/exchanges12/` 仍是
那 12 家、`/exchanges-eu/` 仍是 Euronext / Cboe Europe / Deutsche Börse 三家，
`build/exchanges*.py` 与 `data/exchanges-*.js` 这一轮逐字节未动。原因不是漏接：LSEG 的四条腿
（LSE 订单簿 / 一级市场 / Tradeweb / LCH）里没有一条与现有横截面池同口径同量纲，
接进去要先定跨口径规则。四条腿各自的口径边界、能与不能配对的理由见 `docs/verify/lseg.md`。

`/cost/` 与 `/ibkr/` 原先是两个独立仓库（costco-monthly-sales / ibkr-monthly-metrics），
**已整体并入本仓；那两个仓库连同它们的 Pages 站点已于 2026-08-06 从 GitHub 删除。**
两家的数据源没有变，但解析管道的**位置**变了：原先分别借用 `/COST月度销售` 与
`/IBKR月度指标` 两个 skill 的代码，那两个 skill 也已删除，代码逐字搬进本仓
（COST 在 `fetch/cost_release.py`，IBKR 在 `fetch/ibkr_source.py`），真值 CSV 落到 `series/`。
本仓现在自包含 —— 不依赖那两个旧仓、也不依赖 `~/.claude` 下的任何文件，页面上不留指向它们的链接。

搬迁的验收标准是**逐字节**而不是「看起来一样」：把两个 skill 移走后重跑生成器，
`data/cost.js` 与 `data/ibkr.js` 与搬迁前 0 字节不同（连首行构建日期都相同）。
旧仓的 mirror 备份在 `~/Backups/deleted-repos-2026-08-06/`，
两个 skill 的代码在 `~/.claude/skills` 的 git 历史里。

## 目录结构

```
index.html          总览页
<ticker>/index.html 34 个页面外壳 —— 里面没有任何公司专属内容
                    13 个（11 家老单公司页 + tsm + wealth）由 build/make_shells.py 生成；
                    22 个（5 张横截面 + build/specs/ 与 build/mrspecs/ 下每一家）
                    由 build/make_shells12.py 生成
                    （tsm 两处都在，是接入 mrbase 时留下的历史重叠，去重后 34）
assets/charts.js    手写 SVG 图表引擎，零依赖零构建（17 种 kind）
assets/page.js      通用页面渲染器，全部页面共用一份（导航分行读 roster 的 row）
assets/style.css    版式
series/*.csv        历史序列（唯一真值，入库）[注]
fetch/<t>.py        各家的无人值守抓取器：latest_month() / update()
fetch/fx.py         月度汇率（10 币种对美元，ECB）—— 横截面页的公共底座，不属于任何一家
build/<t>.py        各家的 payload 生成器：series/*.csv → data/<t>.js
build/single.py     单公司页通用底座：build/specs/<t>.py → data/<t>.js（10 家新交易所走这条）
build/specs/<t>.py  一家一份配置（见 docs/SINGLE_SPEC.md）
build/mrbase.py     月度营收页通用底座（台湾半导体 7 家）：build/mrspecs/<t>.py → data/<t>.js
                    配置契约写在 mrbase.py 自己的 §1（不在 docs/ 里另开一份，
                    免得字段清单与 validate() 两处走散）
build/mrspecs/<t>.py 一家一份配置；build/<t>.py 是 7 个薄壳入口
build/mrwin.py      mrbase 的窗口左端与排版裁决层，可单测（python3 build/mrwin.py）
build/CONTRACT.md   payload 数据契约（写生成器前先读它；§6 是全站同比口径）
build/yoy.py        同比口径的唯一实现，所有生成器算同比一律走这里
build/brief.py      页顶数据总结（brief）的规则库，句子由各家生成器自己拼
build/roster.py     生成 data/roster.js（总览页与导航的目录，含各家披露节奏 LAG）
data/<t>.js         生成物，页面直接 <script src> 加载
cache/              下载来的原始文件（gitignore）
monthly_run.py      月度入口（cron 跑的就是它）
tools/check_yoy_caliber.py  同比口径判据（机检 CONTRACT §6，改生成器后跑）
tools/visual_qa.py          整站视觉 QA（截图 + 机器判据，页名自动取自 data/roster.js）
tools/prune_cache.py        cache/ 分级清理（白名单制，dry-run 默认；见「cache 怎么清」）
docs/CRON_WIRING.md 各家的发布节奏与闸门参数、以及「怎么删掉一家」
```

**[注] 个别 `series/*.csv` 只被 `fetch/` 读回当台账，不进 build —— 「没有 build 读它」
不等于它是断链孤儿。** 目前是 `series/spgi.csv`：它与 `spgi_clean.csv` 在
`fetch/spgi.py` 的**同一次 `update()` 里一起写**（中间没有「清洗步骤」这一环），
画图只读 `spgi_clean.csv`，但 `spgi.csv` 是该模块的去重台账 + **官方重述体检的唯一基线**。
删了 = SPGI 抓取当场报错，且从此再也发现不了官方悄悄重述历史。理由写在
`fetch/spgi.py` 的 `update()` docstring 里。做孤儿盘点时，判据要用「**fetch 或 build
有没有人读它**」，只按 build 的读取面盘点必然误杀这一类文件。

## 每月更新

**入口是 `monthly_run.py`**，一条 cron 管 28 家 + 2 张公共表（费率、汇率）+ 6 张横截面页。
**每天跑一次**：28 家的披露日从次月 1 号散到 21 号，覆盖全部窗口只能天天开工；
省下来的是「今天该不该下载」那一层判断（`not_due()`），够新的那几家一个字节都不下。
各家的闸门参数与「怎么删掉一家」见 `docs/CRON_WIRING.md`
（删一家 = 3 个文件 + 5 行注册，见其 §4；删一张横截面页照 `docs/DELIVERY.md` §4.4 的实测清单）。

```bash
python3 monthly_run.py                 # 正常：逐家检查，有新数据才 commit + push
python3 monthly_run.py --only cme,cboe # 只跑指定几家
python3 monthly_run.py --dry-run       # 抓取与生成都做，但不 commit/push
python3 monthly_run.py --force         # 数据没变也重建并推送（改了图表代码后用）
```

改过生成器或引擎之后，三条校验各管一层，谁都替代不了谁：

```bash
python3 build/verify_pages.py          # 结构层：payload 契约 + 页面引用，0 ERROR 才算过
python3 tools/check_yoy_caliber.py     # 口径层：同比口径判据（CONTRACT §6 的机检）
python3 tools/visual_qa.py --all       # 像素层：整站截图 + 机器判据（轴刻度/越界柱/压字）
```

每家输出一行 `<ticker> <状态> <说明>`，stdout **最后一行**是总状态，调度任务只读这一行：

| 总状态 | 含义 |
|---|---|
| `NOTHING_TO_DO` | 28 家都没有新数据（正常，等下次） |
| `PUBLISHED <sha> <n> <月份串>` | n 家更新并已推送，Pages 约 1 分钟后生效 |
| `PARTIAL <sha> <n> ok / <m> fail` | 有更新也有失败，成功的那部分已发布 |
| `FAILED <原因>` | 一家都没成功，或工作树不干净 / push 失败 |

### 一家失败不拖累其余二十七家

单公司仓库的老脚本是「一有问题就整体退出」——那时只有一家，退出=什么都不做，代价为零。
扩到 28 家后同样的写法意味着：TSMC 官网当天抽风，CME / Cboe / HKEX 已经抓到的新数据
也一起不发布，**一家的故障惩罚了另外二十七家**。所以这里逐家隔离：失败的那家跳过
（线上仍是它自己的旧数据，不会变成错数据），成功的照常发布，失败清单打在总状态里。

### 三条护栏（刻意让它失败，而不是替你做决定）

1. **工作树不干净就拒跑。** 提交范围只有 `data/` 与 `series/`；这之外（`assets/`、
   `index.html`、`build/`）有任何未提交改动时，脚本在下载之前就退出。这个仓库是
   手写手改的，没有这道护栏时改到一半的图表引擎会被 cron 连同数据一起 commit 成
   「更新数据」推到公开站。（`--dry-run` 不 commit/push，故只警告不拦。）
2. **缺列一律失败**，绝不静默写 NaN 上线。解析结果少任何一个已有列，该家的 fetch
   模块直接抛异常。
3. **未到披露期不下载。** 28 家的披露日从次月 1 号散到 21 号，要覆盖全部窗口就得
   天天跑；但天天把 28 个源全下一遍是浪费（也给对方站点添堵）。所以先用本地
   `data_through` 对照各家的 LAG 节奏表，够新的直接跳过。

   **闸门比 LAG 提前 `EARLY = 5` 天开，不要改成和红点一样的 `+ GRACE`。** 两者共用
   LAG 表但方向相反：红点早响一天是假警报，闸门晚开一天是公开页面挂旧数据一天。
   原先两处都写 `+ GRACE`，实测代价是当时在仓的 12 家 × 常规月/季末月共 24 档**全部**
   晚于实际发布日 5-8 天（Costco 2026-08-05 发的 7 月数据，闸门要等到 8-13 才开）。
   改成 `-EARLY` 后 24 档无一迟到，代价是每家每月多打几个空请求。
   校验用的「实测发布日」现在有台账兜底：`series/source_dates.csv` 每月记下各家
   官方自述的发布日，随时可以回头核对这张 LAG 表准不准（SPGI 就是这样被抓出来的 ——
   它季末月的实测发布日在第 14 到第 41 天之间飘，见 `monthly_run.EARLY_BY`）。

### 第四类：不出声的失败

上面三条护栏管的是「拦住不该发生的事」，它们失败时会喊。真正难查的是另一类
——**失败时安静退出的环节**：日志没有红字，最后一行状态也正常，只是某件事没发生。
判据是一句话：

> **它连续失败十天，和成功十天，在日志里长得一样吗？** 一样，就缺一道护栏。

本仓踩过的四处。机制都写在代码现场，这里只留指路：

| 安静失败的地方 | 为什么看不出来 | 现在靠什么拦 |
|---|---|---|
| push 被拒 | `main()` 末尾的发布段先 commit 后 push。推失败那个提交留在本地，次日在它上面再 commit、再被拒 —— **本地分支永不收敛**，每天安静 FAILED 一次；而 `NOTHING_TO_DO` 的日子压根走不到 push，看不出区别 | `sync_with_origin()`（完整推理见其 docstring） |
| 跑在非 main 分支上 | 裸 `git push` 推的是**当前分支** → 数据进了别处 → 而 Pages 从 main 根目录发 → 站点静默停更 | 同上 |
| 解析器认不出某行/某列 | 该行被静默丢弃，`latest_month` 停在上个月，fetch 干干净净报 `NOCHANGE`，红点与断档检查全都抓不到。**这一条 2026-08-19 一天之内独立复发三次**：MSCI 把脚注写成裸文本、cboe/ice 手里有自报月却没拿来对账、AXP 的 `Certificates` 被申报方手误写成单数（2021-02 那期，少算一家）—— 三次的形状都是**读不到不抛错** | 用**独立于解析器的外部判据**对账：`fetch/cboe.py` 的 `_crosscheck_report_month`、`fetch/ice.py` 的 `_crosscheck_workbook_month`；词形容错见 `fetch/axp.py` 里 `_series_excess_spread` 的 docstring |
| 合并冲突时选「保留我的」 | 机械改写行（import 块、月份标签定义）两边都像对的：改动数不变、测试照样绿，于是重构被静默回退 | 验收方式改成**重跑原判据**（如死 import 扫描），而不是读 diff |

这四条的共同点：**代价不在「出错」，在出错不会被计入**。

**而且自检要跑在自己身上，不只跑在别人的分支上。** 「引用的符号是否真有定义」
这道检查最初是为了审一个旧分支的 README 才写的（那里有 4 行指向不存在的文件），
第一次跑到自己刚写的东西上，就抓出了同款：一处代码注释把发布段称作 `publish()`，
而全仓没有这个函数（commit + push 内联在 `main()` 里），那个名字被复制了六遍、
两个人复核都没发现——因为大家都在核「逻辑对不对」，没在核「这段话提到的东西
存不存在」。同理，**注释里不要写行号**：加一段代码就会让下游行号全错，写死的
行号下一次改动就成假话。

### 多 session 并发改这个仓

主 checkout 是共用的，而 `guard_dirty_tree()` 的粒度是全仓：`data/`、`series/` 之外
任何一处未提交改动，整轮 28 家一起拒跑 —— 一个人的私事会变成全局故障。
三条规矩，都是实战踩出来的：

- **动手前问一句「这要不要跑 `monthly_run.py`」。** 不要，就去 worktree 做；
  主 checkout 留给 cron。
- **边界写进消息，不要留在各自心里默认。** 分歧只有被写下来才变得可见 ——
  写下来的成本是一句话，不写的成本是按错的理解一路放行下去。
- **不确定某处改动是谁的，用 `git stash`，不要 `git checkout`。**
  前者可逆，后者销毁的是没提交过的手写源码。

存档类分支（如 `backup/axp-2016-preRebase`）不要合并，处置结论记在 git notes 里：
`git notes show cb77376`。

### 幂等

`data/*.js` 首行是构建日期注释，不是数据。`monthly_run.py` 按「忽略首行的正文比较」
判断 `data/` 是否真变了——没变时报 `NOTHING_TO_DO`，不会产生只有日期不同的 no-op
commit，也不会把页面的新鲜度信号刷成当天。**构建日期不进 payload**，进了这套判断就
永久失效。

### 新鲜度红点

总览页每家一个圆点，红色=按该家自己的披露节奏**已经超期**。两条设计：

- 判断用**打开页面那一刻**的浏览器日期，不是构建时算死的。若在构建时算死，这套东西
  哪天停跑了，页面会永远显示一片绿——恰恰在最该报警的时候不报警。
- 节奏表 `build/roster.py` 的 `LAG` 是 `(常规月, 季末月)` 两个值。SCHW / LPLA / HOOD /
  SPGI 的**季末月（3/6/9/12）没有独立月报**，数值随当季财报走，晚 2-4 周；用同一个
  日子判断会每季度误报一次红点，而每季度假一次的警报，人很快就学会无视了。

## cache 怎么清

`cache/` 是 gitignore 的，但它只增不减：2026-08 首次盘点时 711 MB。
清理走 `python3 tools/prune_cache.py`（**默认 dry-run，加 `--apply` 才真删**）。

**判据是「谁会再读它」，不是「它有多老」。** 按 mtime 一刀切会同时犯两个方向的错：
删掉再也拿不回来的东西，同时留着明天就会自己长回来的东西。四种性质分开处理：

| 性质 | 是谁 | 体积 | 处理 |
|---|---|---|---|
| 不可重下 | `basefill/` | 245 MB | **永不清理**，且是唯一需要异地备份的部分 |
| 热工作集 | `axp/`、`*_rates/` | 172 MB | 永不清理：`fetch/rates_*.py` 的 `rows()` 每次全量重放做重述对账，删了每月重打几百个 SEC 请求 |
| 删了会回来 | `lseg_primary_*.xlsx` | 38 MB | 不清理：`fetch/lseg_primary.py:843` 每次跑全月份区间，本地没有就重下 |
| 冷档 | `POLICY` 表登记的族 | 139 MB | 按期次保留最近 N 期 |

`basefill/` 里有三类无人值守拿不回来的东西：只存在于 archive.org 的 CME 规则手册、
CME 2019 每日 SPAN 存档（同期 Settlements API 已返回 empty、HTTPS 镜像恒 400，
那条 FTP 是唯一还活着的通道，见 `build/basefill/cme2.py` 模块头）、
以及 ICE reCAPTCHA 墙后只能人工导出的报表（`build/basefill/ice_enx2.py`）。
它的备份在 private 仓 `hzhan7/dashboards-data-archive`，用那边的 `backup.sh` 刷新。

**`POLICY` 是白名单，不是黑名单。** 新加数据源之后它的 cache 文件族默认不在表里、
不会被动；报告末尾单列「未登记的散文件」体积，超过 50 MB 会警告 —— 看见它涨了，
就去核一遍那个 fetcher 的读取语义（`update()` 是只处理 CSV 里没有的期次，
还是每次全区间重放），再决定要不要登记进来。登记时**必须**在表里写下依据那一句。

⚠ 跑完 `--apply` 之后 `cache/` 是 gitignore 的所以工作树不脏，但**改这个工具本身要提交** ——
`monthly_run.py` 的第一道闸是「工作树不干净就拒跑」，留着未提交的改动会让第二天的 cron 直接停摆。

## 数据源

各家的源、发布节奏、口径坑写在 `fetch/<t>.py` 的模块 docstring 里，那是第一手记录。
几条踩过的坑：

- **HOOD**：Akamai 按 **TLS 指纹（JA3）** 拦客户端，不是按 UA。`curl` / `urllib` /
  `requests` 会「连上但永远不返回」（不是 403，看日志会误判成网络问题）。可用通道：
  `curl_cffi(impersonate='chrome')`、macOS 自带 `/usr/bin/nscurl`、node 原生 `fetch`。
  月度数据走 Reg FD 挂 IR 站，**不进 8-K，盯 EDGAR 抓不到**。
- **SPGI**：`investor.spglobal.com` 对 curl 一律 Cloudflare 403，但 `s29.q4cdn.com`
  的 CDN 直链可直接下。Billed Issuance 官方**只披露同比百分比，从不给绝对面值**。
- **CME**：`cmegroupinc.gcs-web.com/monthly-volume` 这个无扩展名地址**本身就是 xlsx**，
  且是稳定别名，每月指向新文件。别去猜带月份的文件名直链，那种链接每月都变。
- **AXP**：SEC EDGAR CIK 0000004962 的 8-K Item 7.01。2026-05 起口径从 loans-only
  改成合并的 Card balances，两套口径不可连比，分别存不同 CSV。
- **SCHW / LPLA**：季末月（3/6/9/12）没有独立月报，数值取自当季季报。
- **HKEX**：官方有时先把下个月的列开出来再填数，所以「最新月」以**表里最后一个
  ADT 非空的月**为准，不能信文件名。

## 全站口径纪律（2026-08 定）

- **时序图的窗口左端统一为 2016-01**（2026-08-18 定）。在此之前各页各定各的：
  `build/single.py` 的 10 家是「近 25 个月」、cboe / cme 各有一个 `WIN_LONG = 25`、
  hkex 是 12 处写死的 `.iloc[-25:]`、cost 是 2021-01、hood 是近 25 个月，
  而 msci 早就写着 `WIN0 = '2016-01'`。后果是**回补了历史也看不见** ——
  db1 有 295 个月、tmx 295、ndaq 251，页面上除了每页那 1-2 张「全历史」图之外一律只画近两年。
  现在各生成器统一用 `WIN_FROM = '2016-01'`（mrbase 那 7 家走 `window.x_from`），
  取 `max(序列首月, 2016-01)`：**只往右让、不往左借**，序列比它短的家用序列自己的起点
  （2026-08-19 实测：asx / hkex / guc / lseg 等 127 期，hood 67 期 —— 各按各的）。
  · **排版不要各写各的**：通栏与 x 标签抽稀一律调 `build/mrwin.py` 的 `layout_all()`
    （台湾半导体 7 家的 127 点图已经用它跑了一年）。全站已经有过三份互相抄来的量边距
    算式，再抄第四份的下场是改一处漏三处。
  · **窗口一变长，三类错会同时冒出来**，都被现有护栏抓到过，改窗口前先知道它们长什么样：
    ① 平滑图型（`mrwin.DENSE`：gs_line / lines_endlabels / stacked_dual）窗口里出现
       前导 null → 引擎把 null 交给 Catmull-Rom 插值画出一条塌到零的假线，
       逐点标数值时抛 TypeError（cboe Ex7 栽过）。解法是 `mrwin.resolve()` 裁左端，**不是补 0**。
    ② 派生列（环比 / 同比）在序列首月定义上不存在 → 首格 NaN，被 `payload_guard` 拦
       （hkex Ex3 栽过）。解法是丢掉那一格。
    ③ 辅助函数的默认参数写死旧窗口（`def yoy_rhs(..., win=25)`）→ 「values 长 25、
       x 轴 127 格」，被 `verify_pages` 拦（hkex、hood 各栽一次）。默认值要跟着窗口走。
  · **列里有中间空洞时，横轴绝不能用「有值的月」拼起来** —— 那会把相隔数年的两点画成
    相邻格，是 `build/CONTRACT.md` 规矩 3 说的假时间轴（exchanges-eu Ex12 栽过）。
    逐月铺开、缺月留 null，用 `lines`（`doSmooth=false`，null 是断笔）。
    ⚠ 同时注意统计量（min/median/max）要走**真有值的月**，走全轴会算出 nan。
  · **口径断点的竖排标签在长窗口下挂不住**：`rotate(-90)` 的文案长 150-200px，
    charts.js 那套沿竖直带找空档的避让在 25 期时够用、127 期时那条带上挤满柱值标签，
    一个空档都没有。所以 `single.py` 的 `BREAK_LABEL_MAX = 60`：超过就只画红虚线、
    文案移进图注（图注本来就按从左到右的顺序逐条点名）。实测这一条把全站 🔴 从 94 降到 1。

- **流量序列的同比默认用 12 个月滚动合计**。2026-08 全站审计发现单月同比的噪声是
  滚动口径的 2 倍以上，65% 的序列两种口径出现过符号相反 —— 最刺眼的一处是同一张页
  两张图对同一批合约给出相反的增长方向，而读者没有任何线索知道该信哪张。所以同比
  收敛成一份实现（`build/yoy.py`）+ 一条契约（`build/CONTRACT.md` §6）：要用单月同比
  必须在标题里声明并在图注给理由；存量序列（OI / AUM / 账户数）禁止滚动合计。
  判据可机检：`python3 tools/check_yoy_caliber.py`。
- **量价分解**：把成交额（或收入）的增长按恒等式拆成量与价两部分，全仓三类派生量 ——
  股数 × 均价、笔数 × 每笔金额、张数 × 每张费率 —— 含义互不相通，图注强制写明
  「它不是什么」。横轴口径统一为**日历年 + 当年 YTD**：一格 = 一个完整日历年
  （对上一年同 12 个月），末格 = 当年 YTD（对去年同月窗口）。缺同口径（金额，数量）
  配对的页面明说「不具备数据条件」，不硬拆（db1 / enx / ice / ndaq 页各有一条说明）。
- **brief**：11 家老单公司页 + 台湾半导体 7 家 + `/wealth/` 的页顶 ~300 字数据总结。
  规则库在 `build/brief.py`（只算事实），句子由各家生成器自己拼（`build/mrbase.py`
  也 `import brief`，7 家共用底座拼出来的那几句 + spec 的 `brief_extra` 钩子）；
  刻意不复述图表里已有的数字，只写图表讲不出来的三件事 —— 基数效应、口径背离、所处区间。

## 图表引擎

纯 SVG + 原生 JavaScript，零依赖、零构建步骤，不加载任何外部脚本或字体。

- 数据用 `<script src>` 而非 `fetch` 加载 → 直接双击 `index.html` 以 `file://` 打开也能跑
- 配色经色盲安全性校验
- **离群值截轴不删点**：被截的柱端画断口符号、被截的点画空心红圈，真值一律竖排标出，
  图顶注明 axis capped
- **结构性断点**用红色虚线 + 竖排标签标在该期左缘，语义是「从这一期起与左侧不可比」
- 每张图右上角可切「表格」视图，所有数值可直接与原始披露核对
- 不同量纲一律拆成独立图表；确需双轴的，两轴零点画在同一高度 ——
  除非对齐会把某一轴 38% 以上的量程推进无数据区（柱全为正却被迫拉出一大片负区那种），
  这时改为两轴各自缩放，并在图上写明「左右轴零点不同高」
- **月度柱可按业务分部分色堆叠**（`gs_bar` 的可选 `stacks[]`），但**总额仍是那一根柱**：
  纵轴、柱顶数值、12 个月均线、次轴同比全部照总额走，分色只是把同一根柱的填色拆开。
  各段之和必须逐格等于总额 —— 引擎不替数据求和，差额会静默变成柱顶一截空白，
  所以这条恒等式在 `build/verify_pages.py` 里硬校验（见 `docs/CHART_KINDS.md` §3.6.1）。
  **没有改用堆叠柱专用图型（`stacked_dual`）是刻意的**：那个图型的右轴下界写死为 0，
  而这里的次轴是 12 个月滚动同比、会转负，负值会被顶到轴外 ——
  页面等于宣称「增速从没转负过」，而且不报任何错
- **多年份对比图（`year_lines`）的往年色是同色相的等间距明度阶**，最浅一档也压得住网格线；
  当年红色高亮。逐年对比是这类图唯一的用途，颜色分不开等于图没画
- **「合计 + 分项」的组画成两张图，不画成一张多列折线**（`build/single.py` 的
  `groups[].mix`，2026-09 起；目前 `/tmx/` 在用）：第一张是**合计的水平值柱 + 次轴同比**
  （流量走 12 个月滚动合计同比、存量走点对点同比，口径由列的性质定，不由排版偏好定），
  第二张是**分项的 100% 堆叠占比图**（`stacked_dual`，每根柱恒高 100%，只讲结构不讲规模）。
  两张回答的是两个问题：柱图答「这门生意有多大、在不在长」，占比图答「结构往哪边走」——
  而占比最有价值的场合恰恰是「总量在涨、某一块的占比反而在掉」。
  **加总关系由底座逐月复算**：分项之和超过合计、或少于合计而没给残差段名字、
  或声明了残差段而残差恒为 0，一律硬失败（见 `docs/SINGLE_SPEC.md` §1.5）——
  一张写着「堆叠 = 100%」而实际不是的图，页面上看不出来

## 免责

仅供个人研究使用，不构成投资建议。数值以公司原始披露为准。
页面版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，不含其研究观点或数据。
