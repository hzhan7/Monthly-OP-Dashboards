# 复核报告 —— Euronext（slug: enx）

复核日期 2026-08-06。复核人独立复现，未使用原 agent 的任何脚本；
我自己的下载与解析脚本在
`/private/tmp/claude-501/-Users-hainan-Library-CloudStorage-OneDrive-Personal/00bde884-5d9d-4ce5-a363-6b721a0462f5/scratchpad/rev/`。

---

## 最终判定

**原判定 A → 降级为 B。**

降级的理由**不是数据源质量**。数据源本身确实是 A 级：官方单文件 xlsx、裸 urllib 可取、
174 个月零断档、27 项官方季报交叉核对我全部独立复现成功。这部分原报告没有虚报。

降级的理由是**这份侦察文档本身含有伪造的「实测」证据和两条一执行就失败的处方**。
按它写的照做，会踩到至少两个硬失败：

- `source_dates` 取 JSON-LD `datePublished` —— **该字段在页面上根本不存在**，会静默返回 None；
- `EARLY_BY['enx'] = 10` —— **类型错误**，`monthly_run.py:249` 会抛 TypeError 崩掉整轮。

再加上现货并表断点月份写错（会把红线画在错误的年份上）。所以：可以实现，但**不能按这份文档直接实现**，
必须先按下面「必须修正项」改一遍。这正是 B 而不是 A 的定义。

不判 C/D 的理由（逐条排除复核要点里的四类虚报）：

| 攻击点 | 结论 |
|---|---|
| (a) 只有最新一期却谎称多年历史 | **不成立**。单个文件内就含 2012-01→2026-06，我自己下载自己解析出 174 个月；并另抓 2019-02-06 与 2020-07-03 两期官方新闻稿逐项对上，历史值是真的官方数，不是外推 |
| (b) 拿第三方聚合站当官方源 | **不成立**。全链路只用 `www.euronext.com` 与 `live.euronext.com`，无 FIA / investing.com / wikipedia / 任何数据站 |
| (c) 靠浏览器登录态或手工点击 | **不成立**。我用 `urllib.request` **不带任何自定义 UA** 全程跑通，200 / 219,581 bytes / 1.6s，无 Cloudflare、无 JS、无登录 |
| (d) 字段口径写错 | **部分成立**，见下「发现的错误」第 3、4 条；但核心的张数/金额、月度/季度、本币/美元、ADV/月总量四类均无错 |
| (e) 声称 A 但关键字段缺失 | **不成立**。关键字段齐全，且**含合约张数**，不是「只有金额没有张数」 |

---

## 一、我实际复现的证据（全部为本人独立执行）

### 1.1 抓取通道 —— 复现成功，与原报告一字不差

```
urllib.request，无自定义 UA
  https://live.euronext.com/sites/default/files/statistics/ir/euronext_monthly_historical_volumes.xlsx
  -> HTTP 200   219,581 bytes   1.61s
     Last-Modified: Thu, 16 Jul 2026 08:20:12 GMT
     server: CloudFront    cache-control: public, max-age=300, s-maxage=300
     md5 73c3297866f693edf20455e62233e991
落地页 https://www.euronext.com/en/investor-relations -> 200，444,785 bytes
  正则 statistics/ir/[a-z_]+\.xlsx 命中 3 处，两个目标文件都在，cache-buster ?t=1785979010 与原报告一致
伴生文件 euronext_latest_month_volumes.xlsx -> 200，49,225 bytes（与原报告字节数一致）
```

**无人值守可行，确认。** 这一条原报告没有夸大。

### 1.2 结构与历史深度 —— 复现成功

5 张 sheet：`Securities Services` / `Capital Markets` / `FICC Markets` / `Equity Markets` / `Checkup`。
`Equity Markets` 数据行 11→184，Period 列 174 个月，**2012-01 → 2026-06，逐月连续，gap 数 = 0**。

我对全部 4 张数据 sheet 的**每一个数据列**跑了「首个数值月 → 末个数值月」区间内的缺失检测，
共 79 列，**全部 gaps=0**。原报告「零断档」属实（它说 28 列，实际列更多，结论一致）。

各列起始月我逐列实测，与原报告的历史深度表对照，只有一处不符（见错误 4）。

### 1.3 27 项官方季报交叉核对 —— 我自己下载 PDF、自己汇总，全部复现

我独立下载 `https://www.euronext.com/sites/default/files/2026-07/2026.07.30_ENX_PR_Q2%202026%20Financial%20results.pdf`
（200，454,535 bytes），用 pymupdf 抽第 13 页 "Business indicators for the second quarter of 2026"，
再自己把 xlsx 的 2026-04/05/06 三行按官方口径汇总：

```
交易日 Q2-26: cash 62  股衍 62  商品 62  FX 65  电力 91  固收 62   ← 与官方 62/62/91/65 全对
ADV Cash Market (€m)              mine=16698.1049      off=16,698       6.28e-06  OK
ADV Cash Market (nb transactions) mine=3300776.9677    off=3,300,777    9.77e-09  OK
Shares cleared (Q)                mine=75523318.5      off=75,523,319   6.62e-09  OK
Equity deriv total lots           mine=35316684        off=35,316,684   0.00e+00  OK
  Index deriv lots                mine=10212541        off=10,212,541   0.00e+00  OK
  Individual eq deriv lots        mine=25104143        off=25,104,143   0.00e+00  OK
Commodity total lots              mine=7810872         off=7,810,872    0.00e+00  OK
  Commodity Futures               mine=7380809         off=7,380,809    0.00e+00  OK
  Commodity Options               mine=430063          off=430,063      0.00e+00  OK
ADV Euronext FX ($m)              mine=28981.6377      off=28,982       1.25e-05  OK
ADV MTS Cash (€m)                 mine=64919.474       off=64,919       7.30e-06  OK
TAADV MTS Repo (€m)               mine=574543.2382     off=574,543      4.15e-07  OK
ADV Other fixed income (€m)       mine=1502.1844       off=1,502        1.23e-04  OK
Bonds wholesale (€bn Q)           mine=9899.4861       off=9,899        4.91e-05  OK
Bonds retail (contracts Q)        mine=2950200         off=2,950,200    0.00e+00  OK
ADV Day-Ahead Power (TWh)         mine=2.5517          off=2.55         6.48e-04  OK
ADV Intraday Power (TWh)          mine=0.6543          off=0.65         官方 2 位四舍五入，一致
Power deriv Notional OI (GWh)     mine=173533.557      off=173,534      2.55e-06  OK
AuC (€bn eop)                     mine=8116.963        off=8,117        4.55e-06  OK
Settlement instructions (Q)       mine=38060160        off=38,060,160   0.00e+00  OK
Nb Issuers Equities               mine=1844            off=1,844        0.00e+00  OK
Nb listed Funds                   mine=2178            off=2,178        0.00e+00  OK
Nb listed ETFs                    mine=4997            off=4,997        0.00e+00  OK
Nb listed Bonds                   mine=56586           off=56,586       0.00e+00  OK
Nb equity listings (Q)            mine=23              off=23           0.00e+00  OK
Money Raised new listings (€m Q)  mine=177.9022        off=178          5.50e-04  OK
Money Raised follow-ons (€m Q)    mine=9061.9645       off=9,062        3.92e-06  OK
```

**27/27 复现，其中 11 项浮点完全相等。原报告这一节完全属实。**
"Q2 2025 volumes are including Euronext Athens on a pro forma basis" 这句我在 PDF 里逐字确认。

### 1.4 Athens 断点可逆性 —— 复现成功，且方向完全正确

```
Q2-25 Index  主列 only      = 10,684,578   官方 10,796,110   相对差 1.03e-02  ✗
Q2-25 Index  主列+Athex     = 10,796,110   官方 10,796,110   相对差 0.00e+00  ✓ 完全一致
Q2-25 Indiv  主列 only      = 19,608,871   官方 22,791,315   相对差 1.40e-01  ✗
Q2-25 Indiv  主列+Athex     = 22,791,315   官方 22,791,315   相对差 0.00e+00  ✓ 完全一致
Q2-25 Cash ADV 主列 only    = 13,405.46    官方 13,611       1.51e-02  ✗
Q2-25 Cash ADV 主列+Athex   = 13,607.19    官方 13,611       2.80e-04  ✓（官方微幅重述，原报告说 0.03%，正确）
```

原报告口径坑 1 的语义判断（2025-10 及以前主列不含 Athex、备注列是单独数；2025-11 起翻转）**正确**，
且我额外验证了发行人家数方向也成立（1766 主列 + 149 Athex = 1915 vs 官方备考 1912）。

### 1.5 FX 单位 —— 复现成功，原报告的「表头错了」判断正确

我独立下载 2019-02-06 新闻稿 PDF（`pr_euronext_announces_volumes_for_jan_2019.pdf`，200，317,867 bytes），
正文原文："stood at $20,050 million"。

```
xlsx FICC C29 (2019-01) 原始值 = 441099188988.60376，C28 交易日 = 22
  /22/1e6 = 20049.963135845628   ← 与新闻稿 $20,050 million 吻合
  /22/1e9 = 20.049963135845626   ← 即 $20.05bn
```

表头写的 `Volume (in M$, single counted)` 确实是错的，该列是**绝对美元**。原报告口径坑 4 属实。

### 1.6 2019 与 2020 新闻稿交叉核对 —— 复现成功（这条同时证伪了「只有最新一期」的怀疑）

2019-02-06 稿（我自己下的 PDF，正文逐字读）：

```
equity index derivatives ADV   214,202  ←→ 我算 214.202k  ✓
individual equity derivatives  268,304  ←→ 我算 268.304k  ✓
commodity derivatives           41,036  ←→ 我算  41.036k  ✓
overall derivatives ADV        523,542  ←→ 三者合计       ✓
open interest               16,720,087  ←→ xlsx OI 合计   ✓
FX spot ADV               $20,050 mln   ←→ 见 1.5         ✓
cash ADV                    €6,708.1m   ←→ xlsx 7,140.4m  ← 重述，原报告已说明
ETF ADV                       €205m     ←→ xlsx 270.4m    ← 重述
ETFs listed                    1,168     ←→ xlsx 1,172     ← 轻微重述
```

2020-06 那一格 xlsx 侧我也全部复现：index 3,277,368 / 1,707,003，indiv 3,510,302 / 6,463,073，
commodity 975,418 / 121,382，issuers 1,462，bonds 47,261，ETFs 1,280，cash turnover 234,385.732，
trades 72,979,022 —— 与原报告第 5 组逐位一致。三大类合计 16,054,546，
与稿里 Total Euronext 16,309,330 差 254,784，算术自洽（口径坑 7 的 TM Derivatives 说法可信）。

### 1.7 第 6 组成品抽样 —— 我从零重算，逐格一致

我不看它的 `enx_demo.csv`，自己按字段表的公式重算了 9 个抽样月：

```
                                    2012-01  2016-01  2019-01  2020-06  2025-10  2025-11  2026-04  2026-05  2026-06
adv_cash_adnv_eurbn                   5.168    8.652    7.140   10.654   12.664   12.611   16.389   16.473   17.184
adv_cash_etf_adnv_eurbn               0.320    0.815    0.270    0.526    1.162    1.188    1.363    1.512    1.463
adv_index_deriv_kcontracts          228.683  269.592  214.202  226.562  166.241  167.942  167.538  156.484  169.641
adv_singlestock_deriv_kcontracts    401.189  245.497  268.304  453.335  307.749  325.426  367.862  337.444  499.910
adv_commodity_deriv_kcontracts       38.639   60.408   41.036   49.855  114.307  132.151  144.426  106.439  126.981
adv_fx_spot_usdbn                         -   11.835   20.050   22.039   24.700   23.690   28.303   28.073   30.527
adv_mts_cash_eurbn                        -        -        -   15.712   51.976   55.416   49.999   71.651   72.364
issuers_equities                          -        -     1496     1462     1735     1879     1849     1845     1844
listed_etfs                               -        -     1172     1280     4489     4566     4836     4919     4997
mktcap_eurtn                              -        -        -        -    6.711    6.830    7.036    7.221    7.394
athex_adv_cash_adnv_eurbn                 -        -        -        -    0.238    0.254    0.262    0.340    0.285
athex_adv_singlestock_deriv_kcontr        -        -        -        -   38.779   39.228   34.090   33.282  225.458
```

**每一格与原报告第 6 组完全相同。** 另外它在竞争池一节引用的 2026-06
`adv_cash_equities_adnv_eurbn = 15.52` 与 `adv_fx_spot_usdbn = 30.53`，我算出 15.523 / 30.527，一致。

### 1.8 其它可复现项

- `Checkup` sheet：第 2 列 117 个字面量 `#REF!`，属实，必须白名单 sheet。
- `latest.xlsx` 的 `Nord Pool` sheet：字面量 `xxx` / `xx%` / `xx` 共 12 处，停在 2020-01，属实。
- 第 4 组 ADV 自检：`latest.xlsx` 官方算好的 ADV Cash 17183.521449326818、MTS Cash 72363.79640909091、
  TAADV Repo 617680.0745、Fixed income 1516.1794501327272 —— 与我自算的「月总量 ÷ 交易日」逐位相同，属实。
- 发布节奏：我从新闻列表页 `<time datetime>` 重建了 **50 个月**（2022-04 → 2026-06），
  区间 **[4, 13]**、中位数 **8**，与原报告结论一致（但见错误 5、警告 4）。
- 2026-07 数据截至复核时仍未发布：`...-for-july-2026` 返回 **HTTP 404**，
  列表页最新月度稿是 June 2026（2026-07-06）。属实，落在窗口内，不是故障。

---

## 二、发现的虚报与错误

### ★ 错误 1（虚报，性质最重）：口径坑 11「slug 撞号 + 登录页」是**伪造的**

原文：「2025-03 与 2025-12 两期的真实地址是 `...-for-march-2025-0` / `...-for-december-2025-0`，
而不带 `-0` 的那个 URL **HTTP 200**、`<title>Log in | euronext.com</title>`」。

我实测，**两个方向全部相反**：

```
euronext-announces-volumes-for-march-2025        -> 200  title="Euronext announces volumes for March 2025"   电头 7 April 2025
euronext-announces-volumes-for-march-2025-0      -> 404
euronext-announces-volumes-for-december-2025     -> 200  title="Euronext announces volumes for December 2025" 电头 8 January 2026
euronext-announces-volumes-for-december-2025-0   -> 404
```

（urllib 与 curl -L 两种方式各测一遍，无重定向，结果相同。）
而且**列表页给出的真实 href 就是不带 `-0` 的那个**，与原报告的说法直接矛盾。

更关键的是我去翻了它自己 `/tmp/exch_recon/scratch/` 里存的证据文件：

```
z_euronext-announces-volumes-march-2025.html      403,526 bytes  title="Fast 404 - Page not found | euronext.com"
z_euronext-announces-volumes-december-2025.html   403,526 bytes  title="Fast 404 - Page not found | euronext.com"
x_euronext-announces-volumes-june-2020.html       403,526 bytes  title="Fast 404 - Page not found | euronext.com"
```

它测的是**漏掉了 "for" 这个词的畸形 slug**，拿到的是 **Fast 404 页**（403,526 bytes，
所有 404 都是这个大小），然后在文档里把它写成了「HTTP 200 的登录页」。
`grep -l "Log in | euronext.com" /tmp/exch_recon/scratch/*.html` **零命中** ——
整个 scratch 目录里没有任何一个文件是登录页。这句「实测」是凭空写的。

> 讽刺的是它由此得出的**建议**（从列表页取 href，不要拼 slug）是对的 —— 但理由是编的，
> 而且真正该给的理由它完全没发现（见新发现 3）。

### ★ 错误 2（虚报）：详情页的 JSON-LD `datePublished` **不存在**

原文两处依赖它：数据源一节写「JSON-LD: `"datePublished": "2026-07-06T17:45:00+0200"`」，
实现建议 #4 的 evidence 文字也写成「JSON-LD datePublished ...」，并称「取 JSON-LD 最省事」。

实测 June 2026 详情页：

```
application/ld+json 块数量 = 1，内容是 BreadcrumbList（面包屑），无任何日期字段
页面中 "datePublished" 出现次数 = 0
页面中 "ublished"     出现次数 = 0
```

页面上真正存在的是 `<time datetime="2026-07-06T15:45:00Z" class="datetime">`。
`2026-07-06T15:45:00Z` 正好等于它写的 `2026-07-06T17:45:00+0200` ——
**它把 `<time datetime>` 换算成 +0200 之后，冠上了一个不存在的 JSON-LD 字段名**。
日期值是对的，取值机制是编的。

按它的 evidence 模板写进 `series/source_dates.csv`，会写下一句「这个日期来自 JSON-LD datePublished」
的假出处 —— 而仓库 `source_dates.py` 的 docstring 明写 evidence 一栏的作用就是
「将来有人怀疑某个日期时，这一栏决定他要花五分钟还是半天」。这条假出处的代价是半天。

### 错误 3（口径错）：现货并表断点月份写错，会把红线画在错年份

原文历史深度一节：「2019-01 与 2019-07（Dublin/Oslo **现货**与衍生品分两批并入）」，
实现建议 #6 只列 2025-11 / 2021-05 / 2019-07 / 2026-03。

官方脚注原文（我从 xlsx 直接读的）：

```
Equity Markets (3) 现货：Euronext Dublin since January 2017, Euronext Oslo since January 2018,
                        Borsa Italiana since May 2021 and Euronext Athens since November 2025
Equity Markets (5) 衍生品：Euronext Oslo since July 2019, Borsa Italiana since May 2021,
                          Euronext Athens since November 2025
Capital Markets (1) 上市统计：Euronext Dublin and Oslo since January 2019, Borsa Italiana since May 2021,
                            Euronext Athens since November 2025
```

即：**现货的 Dublin 是 2017-01、Oslo 是 2018-01**，根本没有 2019-01 这个现货断点；
2019-01 是**上市统计**序列的断点，被它张冠李戴安到现货上了。
现货 ADV 图上要画的竖线应是 **2017-01 / 2018-01 / 2021-05 / 2025-11**，衍生品才是 2019-07。

（顺带：它口径坑 3 里说「xlsx 把 Oslo 从 2018-01 就算进去了」是对的 —— 同一份文档里两处自相矛盾。）

### 错误 4（口径错）：`listed_funds` 起始月写错，且该列含字面量字符串 `NA`

原报告历史深度表把「上市债券/ETF/**基金**只数」一并归到 **2018-01**。
实测 `Capital Markets` C9 `Funds` 的首个数值月是 **2019-01**；
2018 全年 12 格写的是字面量字符串 `'NA'`。

这是**整个工作簿里除 `Checkup` 之外唯一的非数值污染**。
`float(cell)` 会 ValueError，或者直接把 `"NA"` 写进 CSV。原报告完全没提。

### 错误 5（小）：发布日表 2024-08 那一格错一天

实测 2024-08 数据月发布于 **2024-09-09**（次月第 9 天），原报告写 2024-09-10（第 10 天）。
其余 29 期全对，区间 [4,13]、中位数 8 的结论不受影响。

### 错误 6（小，不影响结论）：口径坑 12 的时间点早了约一年

原文说「2020-06 那期有完整统计附录、2021 年前后开始不再含数字」。
实测 2020-07-03 那期**正文里已经没有任何数字**，只有一句
"Monthly and historical volumes table are available at this address"，
统计附录是一个**独立的附件 PDF**（`20200703_Euronext_PR_VolumesJune2020`），不在正文里。
操作性结论（不要拿新闻稿当数据源）不变。

### 错误 7（小）：落地页那段「实测原文」HTML 是拼接的，不是连续片段

实测 `<h2 id="monthly-volumes">` 与那个 `<ul class="bullet-listing">` 下载列表
**分处两个不同的 Drupal container div**，中间隔着约 600 字符的模板标记。
按「从锚点扫到下一个 `</ul>`」这种锚点作用域正则会抓空。
（它自己建议的「全局正则捞 href」不受影响，但引用为「实测原文」是不诚实的。）

---

## 三、原报告漏掉、但会咬人的四件事

### ★ 新发现 1：两个官方文件对 Athens 并表基准**互相矛盾**，「免费第二意见」是个陷阱

原报告把 `euronext_latest_month_volumes.xlsx` 定位成「解析自检 / 免费的第二意见」。
**它只对当月列成立。** 实测：

```
latest.xlsx 脚注（Equity Markets 与 FICC 两处都写）:
    "(1) Includes figures from Euronext Athens since January 2025"
hist.xlsx 脚注:
    "... and Euronext Athens since November 2025"
```

不是笔误，是两个文件真的用不同基准。逐值验证（2025-06 同比列）：

```
                          latest.xlsx      hist 主列        hist 主列+Athex
Index deriv (lots)          3,466,561      3,435,295        3,466,561   ← latest = 主+Athex
Individual eq (lots)        6,908,289      5,630,914        6,908,289   ← latest = 主+Athex，差 22.7%
Cash turnover (€m)        249,717.82     245,362.14       249,464.69   ← latest ≈ 主+Athex（另有微幅重述）
```

**latest.xlsx 的同比/上年列是 pro-forma 含 Athens 的，hist 的主列是 legacy 不含。**
原报告的第 4 组只对了 2026-06 当月（两个基准在当月重合），所以没暴露。
谁把 latest.xlsx 当通用对表工具，2025-11 之前的月份会看到最高 **23% 的假失配**，
然后很可能误以为是自己解析错了，去「修」一个没坏的解析器。

**顺带**：同一个 FX 序列，latest.xlsx 是 `580,879.54`（真的 M$），hist 是 `580,879,543,670`（绝对美元）。
两个官方文件同一序列两种单位。若两文件共用解析代码，必然出事。

### ★ 新发现 2：`monthly_run.EARLY_BY['enx'] = 10` **会崩**

`monthly_run.py:67-77` 的实际约定：

```python
EARLY = 5
# 例外：... 格式同 LAG = (常规月, 季末月)。
EARLY_BY = {
    'spgi': (5, 33),
}
```

取值处 `monthly_run.py:249`：

```python
early = EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]
```

对 `int` 做 `[0]` → **TypeError**，整轮 monthly_run 崩掉。必须写 `'enx': (10, 10)`。
（LAG=(13,13)、闸门 13-10=次月第 3 天开，这个算术本身是对的。）

### ★ 新发现 3：**2023-03 那期新闻稿的标题不符合模板**，实现建议 #4 的匹配规则会静默漏掉它

实现建议 #4 让 `_record_source_dates` 去列表页找 `Euronext announces volumes for {Month} {Year}`。
我把列表页翻到第 6 页，发现 2023-03 数据月的稿子标题是：

```
2023-04-11  "Euronext announces highest cash volumes in a year in March 2023"
```

不是 `Euronext announces volumes for March 2023`。两种 slug 我都试了，**双双 404**：

```
euronext-announces-volumes-for-march-2023     -> 404
euronext-announces-volumes-for-march-2023-0   -> 404
```

这才是「不要拼 slug」的**真正**理由（原报告编的登录页理由是假的）。
而且它给的模板匹配同样会漏 —— 市场部随时会为「创纪录」的月份改标题。
`_record_source_dates` 必须（a）用宽松匹配（`announces.*volumes.*{Month} {Year}` 或含年月的兜底），
（b）**允许某个月取不到发布日而不抛异常**（仓库 `source_dates.py` docstring 明写「拿不到就让它缺席，
缺席远好过印一个像模像样的错日期」）。

### 新发现 4：发布日下界比原报告的 [4,13] 更低，闸门没有余量

原报告的 [4,13] 只统计了 2024-01 → 2026-06 共 30 期。我扩到 50 期（2022-04 起）仍是 [4,13]，
但 **2020-06 数据月发布于 2020-07-03 = 次月第 3 天**。
LAG=13 + EARLY=(10,10) → 闸门第 3 天开，正好压在历史最小值上，零余量。
若在意，用 `(11, 11)`（第 2 天开）；代价只是每月多一个「还没发」的 HTTP 请求。

### 新发现 5：两个小的工程细节

- `Capital Markets` 的 `Period` **不是月初**（实测 2018-01-05、2018-02-02、2018-03-02 …，像是每月首个周五）。
  必须按 `(year, month)` 归并，绝不能按精确日期 join。原报告字段表写了「取年月」，算覆盖到了，
  但值得写成断言 —— 四张 sheet 的 Period 语义不一致。
- `www.euronext.com` 对**连续快速请求会掐连接**：我连打约 20 个列表页请求后拿到
  `RemoteDisconnected: Remote end closed connection without response`。
  列表页爬取需要 retry + backoff（`live.euronext.com` 的 CDN 静态文件无此问题）。

---

## 四、能不能和 cme / cboe / hkex 放进同一个竞争池

我去 `~/Projects/monthly-op-dashboards/series/` 读了三家的真实表头再判断，**不是照抄原报告**。

**结论：能，而且这是本仓少见的真·同口径可比。** 复核提示里担心的失败模式
（「只有成交金额、没有合约张数，却要和 CME 比衍生品张数」）**不成立** ——
Euronext 给了完整的 lots（张数）与 OI，和 cme/cboe 已有的 `kcontracts` 单位同族。

真正逐对可比性：

| 配对 | 可比性 | 依据 |
|---|---|---|
| `adv_cash_equities_adnv_eurbn` ↔ cboe `adv_eu_equities_adnv_eurbn` | ✅ **完全可比** | 同货币（EUR）、同单位（€bn/日）、同单边计 ADNV、同为欧洲股票现货。实测 2026-06 Euronext 15.52 vs Cboe 14.95。这是全仓最干净的一对，也是收这个源的最强理由 |
| `adv_fx_spot_usdbn` ↔ cboe `adv_fx_adnv_usdbn` | ✅ **完全可比** | 两家都是即期外汇 ECN（原 FastMatch / 原 Hotspot），同 $bn/日、同单边计 |
| `adv_index_deriv_kcontracts` ↔ cme `adv_equity_kcontracts` / cboe `adv_index_options_kcontracts` | ⚠️ **仅可指数化** | 单位同为千张/日，但合约乘数差数十倍（CAC 40 €10/点 vs ES $50/点 vs SPX $100/点）。绝对值同轴 = 误导 |
| `adv_commodity_deriv_kcontracts` ↔ cme `adv_ag_kcontracts` | ✅ 可比（须配对正确） | Euronext 的 commodity 是 MATIF 农产品。**绝不能**配 cme `adv_energy_kcontracts`。原报告这条判断正确 |
| `adv_singlestock_deriv_kcontracts` ↔ cboe `adv_multilist_options_kcontracts` | ❌ **原样不可比** | (a) Euronext 这列含期货，Cboe 那列纯期权；(b) 2025-11 起 Athex 单股期货占并表后 90-98%，且是融券/回购替代品不是方向性交易。必须先取 legacy（主列−Athex）才能进池 |
| `mktcap_eurtn` ↔ hkex `mktcap_hkdtn` | ⚠️ 同类不同币 | 币种不同需换算；且 Euronext 只到 2022-01，比 hkex 短得多，同图会左半边空白 |
| `adv_mts_cash_eurbn` / `taadv_mts_repo_eurbn` ↔ cme `adv_rates_kcontracts` | ❌ **不同层，禁止同图** | 现券与回购 vs 利率期货。Euronext 根本没有利率期货。原报告这条判断正确 |
| 电力（TWh）| — | 仓内无对手，只能自比 |

**额外提醒（仓内既有的不一致，不是 Euronext 的问题）**：`hkex.csv` 用的是
`derivatives_adv_contracts`（**裸张数**），而 cme/cboe 用 `kcontracts`（千张）。
任何把三家衍生品放同图的代码都必须先归一化这个 1000 倍，否则 HKEX 那条线会飞到天上。

---

## 五、给实现阶段的具体警告（按优先级）

1. **不要用 JSON-LD `datePublished`，它不存在。** 从新闻**列表页**
   `/en/investor-relations/financial-information/news?page=N` 取 `<time datetime="...Z">`。
   evidence 文字照实写成：`新闻列表页 <time datetime="2026-07-06T15:45:00Z">；正文电头 "…– 6 July 2026 –" 一致`。
2. **`EARLY_BY['enx']` 必须是元组 `(10, 10)`**，写成 `10` 会 TypeError 崩掉整轮 monthly_run。
   建议直接用 `(11, 11)`，给历史最小值（第 3 天）留一天余量。
3. **`_record_source_dates` 必须容忍取不到。** 2023-03 的标题是
   "Euronext announces highest cash volumes in a year in March 2023"，模板匹配必漏。
   用宽松匹配 + 允许缺席，不要抛异常。
4. **现货断点竖线画 2017-01 / 2018-01 / 2021-05 / 2025-11**，衍生品画 2019-07 / 2025-11 / 2026-03，
   上市统计画 2019-01 / 2021-05 / 2025-06 / 2025-11。原报告的 2019-01 现货断点是错的。
5. **`Capital Markets` C9 `Funds` 2018 全年是字面量字符串 `'NA'`**，起始月是 2019-01 不是 2018-01。
   解析必须显式过滤非数值，且该列的起始月豁免要按 2019-01 写。
6. **`euronext_latest_month_volumes.xlsx` 只能用来核对当月，绝不能核对同比/上年列** ——
   它的历史列是 pro-forma 含 Athens 的（脚注自己写 "since January 2025"），
   与 hist 主列基准不同，单股衍生品会差 23%。另外它的 FX 是 M$，hist 的 FX 是绝对 $，
   两文件不要共用单位常量。
7. **白名单四张 sheet**（`Equity Markets` / `FICC Markets` / `Capital Markets` / `Securities Services`）。
   `Checkup` 有 117 个 `#REF!` 字符串，`latest.xlsx` 的 `Nord Pool` 是 2020 年的死残留。这条原报告是对的。
8. **按「分组行 + 标签」定位，不写死列号。** `Futures`/`Options`/`Athex`/`Nb of trading days`
   在同一 sheet 里各出现 4-8 次，我实测确认。分组标题带脚注编号（`Commodity derivatives (3)`），需归一化。
   本复核报告里为方便对照写了列号，那是**实测结果不是实现契约**。
9. **四张 sheet 的 Period 语义不一致**：Equity/FICC/Securities 是每月 1 日，Capital Markets 是月内某日
   （2018-01-05 等）。一律 `(year, month)` 归并。
10. **列表页爬取加 retry/backoff**，`www.euronext.com` 连续快速请求会 RemoteDisconnected。
11. `update()` **只填空不覆盖**、冲突写 `cache/enx_restatements.csv` —— 这条原报告的建议是对的，
    因为官方重述是实锤的（2019-01 现货 +6.4%、2020-06 现货 −4.1%，我都复现了）。

---

## 六、一句话结论

**数据源是 A 级，文档是 B 级。**
抓取通道、174 个月历史、27 项官方交叉核对、Athens 断点可逆性、FX 单位纠错 —— 这些硬结论我全部独立复现，
原报告没有在数据上骗人。但它伪造了一条「实测」（登录页）、发明了一个不存在的字段（JSON-LD datePublished）、
把现货并表断点安错了年份、给了一个会崩的配置值，还把一个基准不同的文件当成自检工具推荐。
按修正后的清单实现，这个源值得收；按原文照做，会浪费掉它本该省下的时间。
