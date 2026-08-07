# 第二轮验收：`/exchanges-na/`（改造）、`/exchanges-eu/`、`/exchanges-apac/`（新建）

验收日 2026-08-06 · 验收人：本轮验收 agent · 对象是上一阶段三个 agent 交付的
`build/exchanges_na.py` / `build/exchanges_eu.py` / `build/exchanges_apac.py`

**结论：三张页可发。** 0 个 ERROR；本轮查出 5 处缺陷，4 处已改并复验，1 处属别人的范围只报不改。
下面每一节都写了「怎么判的」和「实测值」，判据都可以照着重跑。

---

## 0. 一句话结论

| 页 | 图数 | 数据截至 | HTTP | payload 契约 | 控制台 | 判定 |
|---|---|---|---|---|---|---|
| `/exchanges-na/` | 18（Ex2–19，新增 Ex16–19） | 2026-07 | 全 200 | 0 ERROR | 0 条 | **可发** |
| `/exchanges-eu/` | 12（Ex2–13） | 2026-06 | 全 200 | 0 ERROR | 0 条 | **可发**（改了 2 处后） |
| `/exchanges-apac/` | 13（Ex2–14） | 2026-06 | 全 200 | 0 ERROR | 0 条 | **可发**（改了 1 处措辞后） |

`/exchanges12/` 仍未生成（`data/exchanges12.js` 不存在），本轮不在范围内，verify 里那 2 条 WARN 是它。

---

## 1. 外壳：没有第二份模板

`build/make_shells12.py` 的 `TICKERS` 里**漏了 `exchanges-apac`** —— 目录能打开只是因为
`build/exchanges_apac.py` 自己顺手写了一份（它同样从 `make_shells.py` import `SHELL`，
所以没有模板分叉）。但「外壳的唯一生成入口」这条约定被破了：以后单独重跑 `make_shells12.py`
不会碰这张页，版式改动就会漏掉它一张。

**已改**：`make_shells12.py` 的 TICKERS 补上 `exchanges-apac`，docstring 里写了这一页的定位
（不画份额、四家法域隔离）。改完逐字节比对，5 张页的 `index.html` 与
`make_shells.SHELL.format(t=...)` **完全相同**：

```
exchanges12 IDENTICAL / exchanges-na IDENTICAL / exchanges-intl IDENTICAL
exchanges-eu IDENTICAL / exchanges-apac IDENTICAL
（当时是 5 张页；`exchanges-intl` 已于 2026-08-06 删除，现存 4 张，见 docs/DELIVERY.md §4.4）
```

**目录名 = data 文件名 = payload ticker，三者逐字相同，全用连字符** —— 三张页都合规
（`verify_pages.py` 的 ticker/stem 一致性检查是 ERROR 级，本轮全过）。
`verify_pages.py` 的 `--pages` 默认值也补上了 `exchanges-eu,exchanges-apac`
（原来默认只跑三张，新页跑不到就等于没有兜底）。

---

## 2. 校验：verify_pages + HTTP 段

```
python3 build/verify_pages.py
```

- **A. HTTP 段**：5 张页 `index.html` 全 200，每张页引用的 5 个静态文件
  （`style.css` / `roster.js` / `<t>.js` / `charts.js` / `page.js`）全 200，无孤儿目录。
- **B. payload 段**：`data/` 下全部 payload，**0 ERROR**。
- **无头 Chrome 实跑**：三张页 `console` 与 `exceptionThrown` **各 0 条**；
  DOM 里 `.card` / `<svg>` 数与 exhibit 数一一对上（NA 20/18、EU 14/12、APAC 15/13
  —— 差的 2 个是汇总表卡与核对表卡，它们不画 SVG）。这条最重要：`gs_line` 的
  `null.toFixed()` 一旦触发，卡片之后的 exhibit 会**静默全不渲染**，只有点数对得上才能排除。

**收尾那次实跑：0 ERROR / 45 WARN，退出码 0，而 45 条 WARN 里落在本轮三张页上的是 0 条。**
其余全部是：`exchanges12` 尚未生成（2 条）、并发的另一条产线本轮新写出的
`data/{asx,db1,enx,ice,jpx,miax,ndaq,sgx,tmx}.js` 还没有页面壳（9 条）、
以及第 8 节那条新加的 Markdown 检查在那些页与 `cboe`/`spgi` 上的命中（34 条）。
并发产线还在改动那些文件，所以 WARN 总数会浮动 —— 判据请只看「本轮三张页 0 条」。

---

## 3. 逐张新图的数据契约

判据：kind 在 17 种白名单内 / 每个逐点数组长度 == 该图 xlabels 长度 /
无 `NaN`·`Infinity`·`undefined` 裸字面量 / 平滑类图型（`gs_line`·`gs_line_avg`·
`lines_endlabels`·`stacked_dual`）里**一个 null 都没有**。

三张页用到的 kind 只有 6 种：`lines` / `grouped_bars` / `stacked_dual` / `heat_matrix` /
`bridge_bar` / `bar_line`，全部在白名单内。

### `/exchanges-na/`

| Ex | kind | 数组 × 长度 vs xlabels | null | 长度 |
|---|---|---|---|---|
| 2 | stacked_dual | 5 × 19 vs 19 | 0 | OK |
| 3 | grouped_bars | 2 × 5 vs 5 | 0 | OK |
| 4 | grouped_bars | 1 × 5 vs 5 | 0 | OK |
| 5 | bridge_bar | 3 × 6 vs 6 | 0 | OK |
| 6 | stacked_dual | 5 × 68 vs 68 | 0 | OK |
| 7 | grouped_bars | 2 × 5 vs 5 | 0 | OK |
| 8 | grouped_bars | 1 × 5 vs 5 | 0 | OK |
| 9 | bridge_bar | 3 × 6 vs 6 | 0 | OK |
| 10 | bar_line | 2 × 19 vs 19 | 0 | OK |
| 11 | lines | 2 × 187 vs 187 | 72 | OK |
| 12 | lines | 5 × 187 vs 187 | 310 | OK |
| 13 | grouped_bars | 1 × 187 vs 187 | 0 | OK |
| 14 | heat_matrix | 8 行 × 12 列 | 5 | full ✓ |
| 15 | grouped_bars | 2 × 8 vs 8 | 0 | OK |
| **16** | **lines**（季度份额，新） | 4 × 62 vs 62 | 97 | OK |
| **17** | **lines**（季度份额，新） | 4 × 62 vs 62 | 64 | OK |
| **18** | **grouped_bars**（同月份额，新） | 4 × 5 vs 5 | 4 | OK |
| **19** | **grouped_bars**（同月份额，新） | 4 × 5 vs 5 | 0 | OK |

### `/exchanges-eu/`

| Ex | kind | 数组 × 长度 vs xlabels | null | 长度 |
|---|---|---|---|---|
| 2 | stacked_dual | 4 × 114 vs 114 | **0** | OK |
| **3** | **lines**（季度份额） | 3 × 38 vs 38 | 0 | OK |
| **4** | **grouped_bars**（同月份额） | 4 × 3 vs 3 | 0 | OK |
| 5 | grouped_bars | 1 × 3 vs 3 | 0 | OK |
| 6 | lines | 4 × 114 vs 114 | 0 | OK |
| 7 | lines | 2 × 114 vs 114 | 0 | OK |
| 8 | lines | 2 × 114 vs 114 | 0 | OK |
| 9 | lines | 4 × 18 vs 18 | 0 | OK |
| 10 | grouped_bars | 3 × 14 vs 14 | 0 | OK |
| 11 | lines | 2 × 66 vs 66 | 0 | OK |
| 12 | lines | 2 × 19 vs 19 | 0 | OK |
| 13 | heat_matrix | 3 行 × 24 列 | 0 | full ✓ |

Ex2 是 `stacked_dual`（不容忍 null 的四种之一），**实测 0 个 null** —— 这一点最要紧：
`stacked_dual` 的段高遇到 null 会算成 NaN、右轴线会被平滑塌到 0，而且两种都不报错。

### `/exchanges-apac/`

| Ex | kind | 数组 × 长度 vs xlabels | null | 长度 |
|---|---|---|---|---|
| 2 | lines | 4 × 90 vs 90 | 0 | OK |
| 3 | lines（季度长历史） | 4 × 46 vs 46 | 27 | OK |
| 4 | grouped_bars | 2 × 4 vs 4 | 0 | OK |
| **5** | **grouped_bars**（同月 y/y） | 3 × 4 vs 4 | 0 | OK |
| 6 | lines | 4 × 90 vs 90 | 0 | OK |
| 7 | heat_matrix | 4 行 × 24 列 | 0 | full ✓ |
| 8 | lines | 4 × 90 vs 90 | 0 | OK |
| 9 | lines | 2 × 138 vs 138 | 0 | OK |
| 10 | lines | 2 × 138 vs 138 | 0 | OK |
| 11 | lines | 2 × 138 vs 138 | 11 | OK |
| 12 | lines | 1 × 138 vs 138 | 0 | OK |
| 13 | lines | 2 × 48 vs 48 | 32 | OK |
| 14 | lines | 1 × 90 vs 90 | 42 | OK |

**全部 null 都落在 `lines`（17 种里唯一能安全吃缺口的多线图型），一个都没落进四种平滑图型。**
`lines` 的 `end_label` 走 `lastFinite()`，首尾 null 不抛异常（逐行读过 `charts.js` 确认），
所以 NA Ex11/12/16/17、APAC Ex3/11 的前导 null 是安全的。
`grouped_bars` 的 `if (!isNum(vg)) continue` 会把缺值那根柱整根跳过 —— 缺位是**空白**，不是 0。

裸字面量扫描（`NaN` / `Infinity` / `undefined`，正则排除字符串里的英文单词）：三张页各 0 处。

---

## 4. 专项一：季度份额是不是量加权

**这是本轮最该被独立复算的一条。** 我没有调用 build 里的任何函数，直接从 `series/*.csv`
重算一遍，再和 payload 逐位比。

### NA Ex16（期权池）——**量加权，通过**

口径：`Σ(当季各月 ADV × 当月美股交易日) ÷ Σ(当季各月行业 ADV × 同一批交易日)`，
交易日全页统一取 `ice.trading_days_us_equities`。抽三个季度手算：

| 季 | 交易日 | 成员 | payload | 独立量加权 | 简单平均月份额 |
|---|---|---|---|---|---|
| 2026Q2 | 21/20/21 | NYSE (ICE) | 21.217560 | **21.217560** | 21.218249 |
| 2026Q2 | | Cboe | 23.534241 | **23.534241** | 23.522138 |
| 2026Q2 | | Nasdaq | 29.074053 | **29.074053** | 29.071692 |
| 2026Q2 | | MIAX | 16.521313 | **16.521313** | 16.534759 |
| 2019Q4 | 23/20/21 | NYSE (ICE) | 17.666749 | **17.666749** | 17.668055 |
| 2019Q4 | | Cboe | 31.317266 | **31.317266** | 31.297040 |
| 2019Q4 | | MIAX | 9.988587 | **9.988587** | 9.980015 |
| 2015Q3 | 22/21/21 | NYSE (ICE) | 20.278773 | **20.278773** | 20.288146 |
| 2015Q3 | | MIAX | 6.736439 | **6.736439** | 6.728837 |

payload 与量加权**逐位相等**，与简单平均**处处不等**（最大 2.0bp）。判定成立。
缺月的季度留 `None`（2019Q4 的 Nasdaq、2015Q3 的 Cboe/Nasdaq），线断开而不是补假值 —— 正确。

### EU Ex3 ——**量加权，通过**

口径：`Σ该季三个月成交额 ÷ Σ该季池合计`；Euronext/Cboe 用 `ADV × Euronext trading_days_cash`，
Deutsche Börse 直接用官方原生月度总额列。抽三个季度：

| 季 | 交易日 | payload（ENX / Cboe / DB1） | 独立量加权 | 简单平均月份额 |
|---|---|---|---|---|
| 2Q26 | 20/20/22 | 38.714847 / 39.771905 / 21.513247 | **逐位相同** | 38.6826 / 39.8096 / 21.5078 |
| 4Q19 | 23/21/20 | 38.888660 / 33.480175 / 27.631166 | **逐位相同** | 39.0322 / 33.2846 / 27.6832 |
| 1Q17 | 22/20/23 | 30.413915 / 45.423122 / 24.162963 | **逐位相同** | 30.3962 / 45.4647 / 24.1391 |

4Q19 上简单平均会把 Euronext 抬高 0.14pp —— 这个季度差不是可以忽略的，量加权是对的。

### APAC ——**没有季度份额图**（本页一个份额都不画，见第 6 节）

APAC Ex3 是季度**指数**（成交额指数化），不是份额，季度值用的是三个月日均的**等权平均**。
这一步是有意为之且已写进图注：四家里只有 JPX/SGX/ASX 有交易日列，HKEX 没有，
混着加权等于同一张图两套口径。**代价由代码自己实测并印在页面上**：对有交易日列的三家逐季比过，
日加权与等权最大差 **1.18%**。因为这张图不算任何比值、分母不是别家，这个近似不会污染结论 —— **接受**。

---

## 5. 专项二：同比同月图取的是不是同一个月

### NA Ex18 / Ex19 ——**通过**

四根柱是 Jul-23 / Jul-24 / Jul-25 / Jul-26，`LONG_NUM[...].get(pd.Period('YYYY-07'))`
直接按月份取值，分母也取**各自那个月**的官方行业总量。独立复算 Ex18：

| 月 | NYSE | Cboe | Nasdaq | MIAX | 其他所 |
|---|---|---|---|---|---|
| 2023-07 | 18.5889 | 27.4588 | **None** | 15.5276 | **None** |
| 2024-07 | 22.2247 | 24.4363 | **None** | 13.6875 | **None** |
| 2025-07 | 20.8984 | 23.7110 | 27.9701 | 16.7074 | 10.7131 |
| 2026-07 | 21.1417 | 24.3609 | 28.3764 | 17.1118 | 9.0091 |

与 payload 逐位相同。**成员起点晚于某年时那根柱是留空，不是画假值** —— Nasdaq 的月度披露
自 2025-01 起，Jul-23/Jul-24 两格是 `None`；残差桶「其他所」要 100 减四家之和，
四家缺一就算不出来，所以对应两格也一并留空。图注里点了名（「缺柱点名：Nasdaq（Jul-23、Jul-24
无月度披露）」）。引擎侧 `grouped_bars` 跳过非数值，那两格是**空白**而不是零柱 —— 截图确认。

### EU Ex4 ——**通过**

Jun-23 / Jun-24 / Jun-25 / Jun-26 四年同一个日历月，逐位复算：

| 月 | Euronext | Cboe Europe | Deutsche Börse |
|---|---|---|---|
| 2023-06 | 40.1346 | 38.5735 | 21.2919 |
| 2024-06 | 41.7562 | 37.5403 | 20.7036 |
| 2025-06 | 36.9643 | 40.5011 | 22.5346 |
| 2026-06 | 39.7393 | 38.2737 | 21.9870 |

payload 逐位相同。EU 三家全窗口都有披露，本轮无缺柱；代码里的 `all(ok(SHARE[k][p]) for k in KEYS)`
守着这条，某年缺任一家就整年不画（不会只画半组）。

### APAC Ex5 ——**通过（但柱高是增长率，不是份额）**

Jun-24 / Jun-25 / Jun-26 三年同月，柱高是**各家与自己去年同月比的 y/y**，
四根柱之间不构成加总关系 —— 图注已写明。四家全有值，无缺柱。

---

## 6. 专项三：亚太页有没有偷偷画份额

**通过，而且做得比要求更严。** 对 `data/exchanges-apac.js` 全文做字符串扫描：

| 词 | 命中 |
|---|---|
| `市场份额` | **0** |
| `市占` | **0** |
| `share` / `Share` / `market share` / `pool share` | **0** |
| `份额` | 5（全部是**否定句**：「本表没有任何一行是份额」「柱高是增长率不是份额」「只是张数口径，不是名义额份额」…） |
| `占比` | 9（全部是「本页不画跨市场占比」这类否定句，或明确限定在**同标的双挂牌两所之间**与**同一家内部构成**） |

页面第一条注就是「这一页不画跨市场占比，一个都不画」，并给出理由（法域隔离、几乎零替代性、
分母没有外部指涉），还与 `/exchanges-na/` 做了对照（那页能说份额是因为 ICE 逐月披露官方行业总量）。

### 产品级头对头的合约规格可比性 —— **原稿说得不够准，已改**

原文写「📌 两所的合约规格没能核实」。这句话把两侧说成对称的，**实际不是**：

- **JPX 侧的乘数已核实入库**（`series/contract_specs.csv`：`JPX_N225_FUT_LARGE` ¥1,000/点、
  `JPX_N225_MINI` ¥100、micro ¥10），而且那一侧**已经按大合约当量归一过**
  （`adv_n225_lgeq_kcontracts`）。
- **SGX 侧的规格确实没取到**（`sgx.com` 是 Angular 单页应用，rulebook 直链本轮实测 404），
  已登记在 `series/contract_specs_todo.csv` 的 `SGX_NK_NIKKEI225`，那一侧仍是**原始张数**。

一边归一、一边没归一 ⇒ 汇总表里「SGX 占两所之和 17.5%」**连纯张数口径都算不上**，
原来的行标「张数口径，未做规格归一」会让人以为两侧至少是同一种张。

**已改三处**（`build/exchanges_apac.py`）：
1. 汇总表行标 → 「SGX 占两所之和（%，**SGX 原始张数 ÷ JPX 大合约当量，两侧未同口径**）」；
2. Ex10 图注加第 (c) 条：两条线的「张」不是同一种张，**只能读各自斜率、不能读线间高低**
   —— 这也正是两条线各自指数化到 100 而不是画在同一绝对刻度上的原因；
3. 注 7 ① 改写：把「已核实 / 未核实」两侧分开讲，并指名两个文件的具体行。

Ex11（比值指数）本来就说得准：比值一旦指数化，未知的乘数常数被完全约掉，趋势精确。

---

## 7. 视觉审查（无头 Chrome 1400px 整页截图，逐段看）

三张页整页高 11,118 / 8,708 / 8,078 px，按 1,600px 分段逐段看过，另对可疑卡片按
`.card` 的 `boundingClientRect` 出 2× 高清单卡图。

### 7.1 已改：热力矩阵深色格的数字糊成白斑（**engine 级，影响全站每一张热力矩阵**）

`assets/charts.js` 的 `txt()` **默认给每个字加 2.4px 的白色描边**（`paint-order: stroke fill`），
而热力矩阵深色格上 `inkOn()` 返回的字色**也是白的** —— 白字 + 白描边，在 4.6–9px 的字号上
把笔画整个糊平。颜色越深的格子（也就是极值，最该被读到的那些）越读不出来。

实测（`/exchanges-apac/` Ex7）：修前 HKEX 行的 `83% / 81% / 88% / -36% / 105% / 142% / 97% / 136%`
全是白色团块；修后逐格清晰。`/exchanges-na/` Ex14（2019/2020 深绿行、2025 深红行）、
`/exchanges-eu/` Ex13 同样修复。

**改法**：热力格的数值标签传 `halo: false`。格子本身是实心色块，底下没有网格线要挡，
描边在这里没有任何作用。截图：
`docs/verify/shots_v2/BEFORE_apac_ex7_heat_halo_bug.png` → `AFTER_apac_ex7_heat_halo_fix.png`

### 7.2 已改：EU 抬头把 `<b>` 三个字符原样印出来

`page.js` 的 `set()` 用的是 `textContent`，`subtitle` / `title` / `headline` / `tracker` /
`through_label` 五个字段**不解析 HTML**。`build/exchanges_eu.py` 在 subtitle 里写了
`<b>但分母 = 本池三家之和…</b>`，页面上真的印出了尖括号。

**改法**：subtitle 去掉标签（强调只能靠措辞）。并在 `verify_pages.py` 里加了 **ERROR 级**
检查 `TEXT_ONLY`，以后自动拦 —— 这是肉眼可见的交付缺陷，不该只给 WARN。

### 7.3 其余逐段所见：无 blocker

- **纵轴被离群值拉爆**：NA Ex5 的「池合计」柱 11,259 vs 各家 2,200–3,200，纵轴顶到 12000，
  单家的柱被压到 1/4 高度。但那一列是四家之和、图注写明「只剩池扩大一块，是这张图自带的算术校验」，
  拆掉反而失去校验意义 —— **保留**。
- **色标被量级差占满**：三张热力矩阵的色标都取**本矩阵自己的 5/95 分位**（不是全站共享），
  图注三处都写了「只在本图内部可比」。修完 7.1 后读数清晰。
- **末点标签叠字**：`verify_pages.py` 的 `endlabel_collision()`（复算引擎 `spreadY` 几何）
  本轮 0 命中。人眼复核：NA Ex16 末点 29.1/23.5/21.2/16.5 分得开；NA Ex12 的 19.1/14.6/9.0/0.7/43.4
  分得开；EU Ex3 的 39.8/38.7 相距 1.1pp 被 `spreadY` 顶开 10px、靠颜色区分，可读；
  EU Ex7 的 45.0/44.6 与 EU Ex8 的 0.9/0.9 贴得较近 —— 后者是**恒等式自检图，两条线本来就必须重合**，
  重叠是结论本身，不是缺陷。APAC Ex11 的 42/42 同理（月度比值与 12 月滚动值在末点几乎相等）。
- **断点标注**：NA Ex16/17 两条红色竖虚线（2014Q1 NYSE 形式数、2018Q1 Cboe/Bats 形式数）画出且带旋转标签；
  EU Ex2/3/6 的 Euronext 并表断点（Oslo / Borsa Italiana / Athens）由 `series/enx_breaks.csv` 驱动、
  不是代码写死，落在断点所在季/月；APAC Ex12/13 的竞品上线与授权迁移断点也在。
  MIAX 期权深历史那道拼接（API → IR 报表）**故意不画断点**，理由是代码自己量出来的：
  19 个重叠月相对差 ≤0.28%，换算成份额 ≤2.3bp，在 0–35% 的纵轴上不到一个像素。

---

## 8. 顺手发现、但**不在本轮范围**的一处全站缺陷（未改）

**note / notes 里写 Markdown 的 `**粗体**`，页面会把四个星号原样印出来。**
`note` 系列字段走 `innerHTML`，引擎与 `page.js` 都不做 Markdown 转换（逐行确认）。

实拍证据：`docs/verify/shots_v2/spgi_ex5_markdown_asterisks.png`
—— `/spgi/` Ex5 的图注真的印着「季度值是该季各月 ADV 的\*\*简单平均\*\*（日均口径不能相加）」。

本轮新加的检查（WARN 级）在收尾那次实跑上扫出 **34 处**（并发产线还在改那些页，数字会浮动）：

| 页 | 命中 | 备注 |
|---|---|---|
| `enx` 8 · `db1` 7 · `asx` 6 · `sgx` 3 · `tmx` 2 · `jpx` 2 · `ndaq` 1 | 29 | **并发的另一条产线本轮新写出的单所页**，不是我的范围 |
| `spgi` 4 · `cboe` 1 | 5 | 已上线的旧页（实拍见下） |
| `exchanges-na / -eu / -apac` | **0** | 本轮三张页干净（APAC 上我自己写坏过 3 处，已改回 `<b>`） |

建议交给单所页那条产线统一改（在它们的 note 生成处把 `**x**` 换成 `<b>x</b>`），
本文只报不改 —— 一次性改 8 个未验收页的正文，会把那条产线的验收基线搅乱。

同一根因还有第二个受害者，也未改：`stacked_dual` 的段内数值标签
（`charts.js` 第 1084 行）同样走默认白描边，而 `hood` Ex9/Ex17、`lpla` Ex5、`ibkr` Ex8
都用了 `label_color: WHITE` —— 白字压在深色段上会糊成白斑。
`/exchanges-eu/` Ex2 的图注里其实已经写出了这个现象并因此关掉了段内标签
（`'label': False`），可见交付方也撞见过。修法与 7.1 同：给 `txt()` 传 `halo: false`，
或让 `txt()` 支持「描边用背景色」。**没改是因为它只影响三张已验收的旧页，改了要重跑那三页的视觉验收。**

---

## 9. 本轮改了什么（可 diff 复核）

| 文件 | 改动 | 为什么 |
|---|---|---|
| `assets/charts.js` | 热力格数值标签加 `halo: false` | 白字+白描边糊成白斑（7.1） |
| `build/exchanges_eu.py` | 月度占比从 ADV 基底换成**当月实际成交额**基底；Ex2 图注写出实测虚高幅度 | 见下方「9.1」 |
| `build/exchanges_eu.py` | subtitle 去掉 `<b>` 标签 | `textContent` 不解析 HTML（7.2） |
| `build/exchanges_apac.py` | 汇总表行标 / Ex10 图注 / 注 7 三处改写 | 两侧规格核实程度不对称（6） |
| `build/make_shells12.py` | TICKERS 补 `exchanges-apac` + docstring | 外壳唯一入口（1） |
| `build/verify_pages.py` | `--pages` 默认值补两张新页；新增 `TEXT_ONLY` HTML 标签检查（ERROR）；新增 Markdown `**` 检查（WARN） | 让 7.2 与 8 以后自动被拦 |
| `.gitignore` | 加 `docs/verify/shots_v2/` | 截图 7MB，不进 git |

### 9.1 EU 月度占比的基底（本轮唯一一处口径改动，请重点复核）

**问题**：Ex2 标题写的是 *Pool share of European cash-equity **turnover***，但它算的是
**ADV 的占比**。而三家的 ADV 不是同一把尺子量出来的 —— Euronext / Cboe Europe 的源列本来就是 ADV，
Deutsche Börse 的源列是月度总额、要除**它自己的** `trading_days_cash`。德国交易所在 12/24、12/31
与圣灵降临节休市，窗口内 **11/114 个月**它的交易日比 Euronext 少 1–2 天：

```
2018-10 23/22   2018-12 19/17   2019-06 20/19   2019-10 23/22   2019-12 20/18
2020-06 22/21   2020-12 22/20   2021-05 21/20   2021-12 23/21   2024-12 20/18   2025-12 21/19
```

天数少 ⇒ ADV 被除大 ⇒ 按 ADV 算占比等于给休市多的那家加权。实测偏差最大 **2.15pp**
（2019-12 的 Deutsche Börse），而且**每年 12 月复发一次**，在堆叠带上看起来像一条季节性规律。
2.15pp 比这张图想讲的结构性移动还大，而且它与 Ex3（季度图，量加权、建在成交额上）**基底不一致**。

**改法**：`SHARE` 改建在 `MONTHLY_EUR`（Euronext/Cboe = ADV × Euronext 交易日；DB1 = 官方原生月度总额）
之上，与 Ex3 同一条链，两张图在重叠处严格自洽。同时留了一个 `SHARE_ADV_MAXGAP` 实测量写进 Ex2 图注，
哪天有人改回 ADV 基底，那句话会自己变大。

**影响面**：Ex1 汇总表的「池内相对占比」三行、Ex2、Ex4、以及 headline 里的占比读数。
Jun-26 三家 39.74% / 38.27% / 21.99%（6 月三家交易日相同，读数不受这次改动影响）；
受影响的是历史上那 11 个月，最大 2.15pp。季度图（Ex3）与同月图（Ex4）的数值本轮复算过，
与独立手算逐位相同。

---

## 10. 截图

全部在 `/Users/hainan/Projects/monthly-op-dashboards/docs/verify/shots_v2/`（已 gitignore）：

| 文件 | 内容 |
|---|---|
| `exchanges-na.png` | `/exchanges-na/` 整页（1400 × 11,118） |
| `exchanges-eu.png` | `/exchanges-eu/` 整页（1400 × 8,708） |
| `exchanges-apac.png` | `/exchanges-apac/` 整页（1400 × 8,078） |
| `BEFORE_apac_ex7_heat_halo_bug.png` | 热力矩阵白斑缺陷（修前，2× 单卡） |
| `AFTER_apac_ex7_heat_halo_fix.png` | 同一张图修后 |
| `spgi_ex5_markdown_asterisks.png` | 第 8 节 Markdown `**` 缺陷的实拍证据（旧页） |

复现方式：

```bash
cd /Users/hainan/Projects/monthly-op-dashboards
python3 build/verify_pages.py                 # A 段 HTTP + B 段 payload
python3 -m http.server 8731 --bind 127.0.0.1  # 再用无头 Chrome 打开 /exchanges-{na,eu,apac}/
```

---

## 11. 没验到的

- **数值口径本身只抽验了本轮点名的两类图**（季度份额、同月份额）与 EU 的月度占比基底。
  各家分子分母是否对得上官方披露，靠的是页面自带的四条自检锚点（NA Ex10/13/15、EU Ex8）
  与 build 里的硬断言（成员之和超过官方分母就 `SystemExit`），本轮没有另起一路核。
- **窄屏 / 打印版式没验**：只在 1400px 下看过。半栏卡片（EU Ex4/5、APAC Ex4/5/13/14）
  在 375px 上 band 会掉到 10px 出头，`bar_labels` 可能横向连片。
- **`/exchanges12/` 与并发产线的 8 张单所页**不在本轮范围，只在 verify 输出里以 WARN 出现。
- **并发风险**：本轮期间 `data/` 下有另一条产线在同时写文件（19:20–19:22 出现了
  `asx/db1/enx/ice/jpx/sgx/tmx.js` 与 `build/single.py`）。本文所有数字取自
  2026-08-06 19:15–19:26 之间那次实跑；若之后有人再动过这三个 build 脚本，
  请先重跑 `python3 build/verify_pages.py` 再信本文。
