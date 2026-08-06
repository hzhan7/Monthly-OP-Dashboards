# 月度经营指标看板（12 家）

12 家公司按月披露的经营数据，做成一套交互看板，版式仿 Goldman Sachs GIR exhibit。
数据全部来自公司官网 IR 或 SEC 申报的原始披露，不含任何券商研报的观点或数据。

**看板地址：** https://hzhan7.github.io/monthly-op-dashboards/

```
/            总览（12 家 + 2 张横截面，含各家新鲜度红点）
/cme/ /cboe/ /hkex/                 交易所
/ibkr/ /schw/ /lpla/ /hood/         券商与财富管理
/msci/ /spgi/                       数据与指数
/cost/ /axp/                        消费与信贷
/tsm/                               半导体
/exchanges/ /wealth/                横截面（同组公司放同一张图比）
```

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
<ticker>/index.html 14 个页面外壳 —— 里面没有任何公司专属内容，由 build/make_shells.py 生成
assets/charts.js    手写 SVG 图表引擎，零依赖零构建（17 种 kind）
assets/page.js      通用页面渲染器，12 家共用一份
assets/style.css    版式
series/*.csv        历史序列（唯一真值，入库）[注]
fetch/<t>.py        各家的无人值守抓取器：latest_month() / update()
build/<t>.py        各家的 payload 生成器：series/*.csv → data/<t>.js
build/CONTRACT.md   payload 数据契约（写生成器前先读它）
build/roster.py     生成 data/roster.js（总览页与导航的目录）
build/repo.py       仓库定位 + 发布日台账入口（生成器共用）
build/monthlab.py   x 轴月份标签 `Jul-26` 的唯一实现
build/feerates.py   series/fee_rates.csv 的共享读取层（整表读一次）
build/payload_guard.py  写出前拦 NaN（CONTRACT §5 第 5 条的唯一执行点）
build/pctile.py     汇总表 3Y %ile 的唯一实现
data/<t>.js         生成物，页面直接 <script src> 加载
cache/              下载来的原始文件（gitignore）
monthly_run.py      月度入口（cron 跑的就是它）
scripts/verify_build.py  回归护栏：重生成 data/*.js 并与 HEAD 逐字节比对
```

## 改了生成器之后

```bash
python3 scripts/verify_build.py     # 全部 15 个 data/*.js 与 HEAD 逐字节一致？（约 0.5s）
python3 build/test_monthlab.py      # 月份标签的等价性测试
```

build 层是纯函数（`series/*.csv` → `data/<t>.js`，不联网、不看时钟、不用随机数，
窗口一律从数据最新月倒推），所以「同一份 CSV 重复跑，输出逐字节相同」是可断言的 ——
`verify_build.py` 断言的就是这一条，判据与上面两个旧仓搬迁时一样是**逐字节**，
唯一允许的差异是首行那句构建日期注释。它在临时沙箱里跑（`series/` 与 `cache/`
只读软链进去），不动工作树里的 `data/*.js`。

纯重构（抽公共代码、改内部结构）应当 15/15 全绿；**输出真该变的时候**（改了口径、
加了 exhibit），预期看到相应几家「不一致」，此时逐条核对差异是不是你想要的那一处，
确认后再连同新的 `data/*.js` 一起提交。

**[注] 个别 `series/*.csv` 只被 `fetch/` 读回当台账，不进 build —— 「没有 build 读它」
不等于它是断链孤儿。** 目前是 `series/spgi.csv`：它与 `spgi_clean.csv` 在
`fetch/spgi.py` 的**同一次 `update()` 里一起写**（中间没有「清洗步骤」这一环），
画图只读 `spgi_clean.csv`，但 `spgi.csv` 是该模块的去重台账 + **官方重述体检的唯一基线**。
删了 = SPGI 抓取当场报错，且从此再也发现不了官方悄悄重述历史。理由写在
`fetch/spgi.py` 的 `update()` docstring 里。做孤儿盘点时，判据要用「**fetch 或 build
有没有人读它**」，只按 build 的读取面盘点必然误杀这一类文件。

## 每月更新

**入口是 `monthly_run.py`**，一条 cron 管 12 家。

```bash
python3 monthly_run.py                 # 正常：逐家检查，有新数据才 commit + push
python3 monthly_run.py --only cme,cboe # 只跑指定几家
python3 monthly_run.py --dry-run       # 抓取与生成都做，但不 commit/push
python3 monthly_run.py --force         # 数据没变也重建并推送（改了图表代码后用）
```

每家输出一行 `<ticker> <状态> <说明>`，stdout **最后一行**是总状态，调度任务只读这一行：

| 总状态 | 含义 |
|---|---|
| `NOTHING_TO_DO` | 12 家都没有新数据（正常，等下次） |
| `PUBLISHED <sha> <n> <月份串>` | n 家更新并已推送，Pages 约 1 分钟后生效 |
| `PARTIAL <sha> <n> ok / <m> fail` | 有更新也有失败，成功的那部分已发布 |
| `FAILED <原因>` | 一家都没成功，或工作树不干净 / push 失败 |

### 一家失败不拖累其余十一家

单公司仓库的老脚本是「一有问题就整体退出」——那时只有一家，退出=什么都不做，代价为零。
扩到 12 家后同样的写法意味着：TSMC 官网当天抽风，CME / Cboe / HKEX 已经抓到的新数据
也一起不发布，**一家的故障惩罚了另外十一家**。所以这里逐家隔离：失败的那家跳过
（线上仍是它自己的旧数据，不会变成错数据），成功的照常发布，失败清单打在总状态里。

### 三条护栏（刻意让它失败，而不是替你做决定）

1. **工作树不干净就拒跑。** 提交范围只有 `data/`；`data/` 以外（`assets/`、
   `index.html`、`build/`）有任何未提交改动时，脚本在下载之前就退出。这个仓库是
   手写手改的，没有这道护栏时改到一半的图表引擎会被 cron 连同数据一起 commit 成
   「更新数据」推到公开站。（`--dry-run` 不 commit/push，故只警告不拦。）
2. **缺列一律失败**，绝不静默写 NaN 上线。解析结果少任何一个已有列，该家的 fetch
   模块直接抛异常。
3. **未到披露期不下载。** 12 家的披露日从次月 1 号散到 20 号，要覆盖全部窗口就得
   天天跑；但天天把 12 个源全下一遍是浪费（也给对方站点添堵）。所以先用本地
   `data_through` 对照各家的 LAG 节奏表，够新的直接跳过。

   **闸门比 LAG 提前 `EARLY = 5` 天开，不要改成和红点一样的 `+ GRACE`。** 两者共用
   LAG 表但方向相反：红点早响一天是假警报，闸门晚开一天是公开页面挂旧数据一天。
   原先两处都写 `+ GRACE`，实测代价是 12 家 × 常规月/季末月共 24 档**全部**晚于
   实际发布日 5-8 天（Costco 2026-08-05 发的 7 月数据，闸门要等到 8-13 才开）。
   改成 `-EARLY` 后 24 档无一迟到，代价是每家每月多打几个空请求。
   校验用的「实测发布日」现在有台账兜底：`series/source_dates.csv` 每月记下各家
   官方自述的发布日，随时可以回头核对这张 LAG 表准不准（SPGI 就是这样被抓出来的 ——
   它季末月的实测发布日在第 14 到第 41 天之间飘，见 `monthly_run.EARLY_BY`）。

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
- **多年份对比图（`year_lines`）的往年色是同色相的等间距明度阶**，最浅一档也压得住网格线；
  当年红色高亮。逐年对比是这类图唯一的用途，颜色分不开等于图没画

## 免责

仅供个人研究使用，不构成投资建议。数值以公司原始披露为准。
页面版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，不含其研究观点或数据。
