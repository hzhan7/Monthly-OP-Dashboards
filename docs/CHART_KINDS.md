# charts.js 图型数据契约（17 种 kind 全量）

引擎：`assets/charts.js`（零依赖 SVG，不 fetch、不算数）。
<!-- 这里以前写着行数。别再写：每动一次就过期一次，而它不承载任何判断。 -->
调用链：`build/<t>.py` → `data/<t>.js` 的 `window.DASH.exhibits[]` → `assets/page.js`
逐个交给 `window.Exhibits.card(mount, ex, opt)` → `draw()`。

**这份文档是从引擎源码逐行读出来的，不是从设计意图推的。** 凡是写「会抛异常」「会静默画错」
的地方，都能在 `assets/charts.js` 里指到具体那一行。写 build 脚本时以本文为准；
`build/CONTRACT.md` §3 与 `build/engine_kinds.md` 是同一件事的另外两个视角
（前者是 payload 顶层契约，后者只覆盖后加的 7 种），三份不一致时以引擎源码为准。

> 引擎**不许改**。图型不够用就换图型或改 Python 侧的数据组织，不要去动 `assets/charts.js`
> —— 它同时服务已上线的 14 张页，改一行要重新验收 14 页。

---

## 0. 17 种 kind 一览

| kind              | 形态                             | 系列字段                   | 双轴           | 默认画布高 |
|-------------------|----------------------------------|----------------------------|----------------|------------|
| `bar_line`        | 柱 + 线（同一轴）                | `bar{} line{}`             | 否             | 248        |
| `bar_line_dual`   | 柱（左）+ 线（右）               | `bar{} line{}`             | **总是**       | 248        |
| `bars_labeled`    | 柱 + 每柱数值                    | `values[]`                 | 否             | 248        |
| `bridge_bar`      | 正上负下的恒等式桥 + 净额菱形    | `stacks[] net{}`           | 否             | 268        |
| `diverging_bars`  | 正负分色柱（正 NAVY / 负 RED）   | `values[]`                 | 否             | 248        |
| `grouped_bars`    | 同 x 并排 2–4 根柱               | `groups[] line{}`          | 给 `line` 才有 | 268        |
| `gs_bar`          | 浅蓝柱 + 12 月均线（或次轴 y/y）；可按分部分色堆叠 | `values[] avg12 yoy{} stacks[]` | 给 `yoy` 才有  | 268        |
| `gs_line`         | 平滑线 + 每点数值                | `values[]`                 | 否             | 268        |
| `gs_line_avg`     | 平滑线 + 均线 + 右端均值         | `values[] avg12`           | 否             | 268        |
| `heat_matrix`     | 行 × 列热力矩阵，格内写数值      | `rows[] cols[] matrix[][]` | 否             | 自适应     |
| `lines`           | N 条折线（可零基线、可标末点）   | `series[]`                 | 否             | 248        |
| `lines_endlabels` | N 条平滑线，只标两端             | `series[]`                 | 否             | 268        |
| `qtr_bar`         | 季度柱 + 右轴 y/y                | `values[] line{}`          | 给 `line` 才有 | 268        |
| `range_band`      | 区间带 + 实际值菱形              | `lo[] hi[] actual[]`       | 否             | 268        |
| `seasonality`     | 灰=同月均值 / 蓝=实际，配对柱    | `base{} actual{}`          | 否             | 268        |
| `stacked_dual`    | 堆叠柱（+ 可选的右轴百分比线）   | `stacks[]` `line{}`可选    | 给 `line` 才有 | 268        |
| `year_lines`      | 每年一条线叠在 12 格上           | `series[] highlight`       | 否             | 268        |

画布最终高 = `height || 默认高` + x 标签带（`xrot=90` → 48、`45` → 36、`0` → 22）。

---

## 1. 所有 kind 通用的字段

| 字段              | 类型               | 必填 | 说明                                                                                                                                          |
|-------------------|--------------------|------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `n`               | int                | ✓    | Exhibit 编号，渲染成卡片标题 `Exhibit n: title`，也进 SVG 的 aria-label                                                                       |
| `kind`            | string             | ✓    | 必须是上表 17 个之一。**引擎对未知 kind 不报错**：走 `else` 分支当 `values[]` 柱图，多半是一片空白                                            |
| `title`           | string             | ✓    | 标题（不含 `Exhibit n:` 前缀，前缀由引擎加）                                                                                                  |
| `xlabels`         | string[]           | 见下 | 该图自己的 x 轴标签。缺省则用 `opt.xlabels`（= `DASH.xlabels`，或 `ex.x==='long'` 时的 `DASH.xlabels_long`）。**长度为 0 就渲染成「无数据」** |
| `x`               | `'long'`           |      | 由 page.js 解释：改用 `DASH.xlabels_long`                                                                                                     |
| `full`            | bool               |      | 通栏。page.js 在 card 上加 `.wide` 后**重画一遍**（viewBox 要按新宽度重算）                                                                   |
| `height`          | int                |      | 覆盖默认画布高                                                                                                                                |
| `ylab` / `ylab2`  | string             |      | 左 / 右轴标题。**双轴图必须给 `ylab2`**，否则右边距只有 42px 且没人知道右轴是什么                                                             |
| `fmt`             | string             |      | 数值格式器名（下表），缺省 `f1`                                                                                                               |
| `yfmt`            | string             |      | 左轴刻度格式器；不给则按刻度步长自适应（纯数字，`stacked_dual` 带千分位）                                                                     |
| `label_fmt`       | string             |      | 数据标签格式器，缺省回退 `fmt`                                                                                                                |
| `legend`          | string             |      | 单系列图的图例名（`gs_bar` / `qtr_bar` / `heat_matrix` tooltip / 表格视图行名）                                                               |
| `note`            | string             |      | 卡片下方 `Note:` 行，允许 HTML                                                                                                                |
| `src_extra`       | string             |      | 追加在 `Source:` 行之后                                                                                                                       |
| `xrot`            | 0/45/90            |      | x 标签角度。缺省：`year_lines` 为 0，其余 `n>20` 时 90、否则 45                                                                               |
| `xstep`           | int                |      | 每隔几个标一次 x 标签                                                                                                                         |
| `ycap` / `yfloor` | number             |      | 截轴上 / 下界。**截轴不删点**：柱画到界 + 白色断口符号，点画空心红圈，真值一律竖排标出                                                        |
| `cap_note`        | string             |      | 截轴时右上角斜体小字，如 `axis capped — outlier shown in red`                                                                                 |
| `break_at`        | int \| int[]       |      | 结构性断点的 x 索引；红虚线画在**该期左缘**，语义是「从这一期起与左侧不可比」                                                                 |
| `break_label`     | string \| string[] |      | 断点竖排标签；给一个字符串时所有断点共用                                                                                                      |
| `bar_marks`       | int[]              |      | 斜纹柱（不可比期）。**只对 `bar_line` / `bar_line_dual` / `diverging_bars` / `bars_labeled` / `gs_bar` / `qtr_bar` 生效**                     |
| `mark_note`       | string             |      | 斜纹柱在 tooltip 里追加的解释                                                                                                                 |
| `bar_labels`      | bool               |      | 柱值标签开关，**默认值随 kind 不同**，见 §5                                                                                                   |
| `annot`           | string             |      | 图内注解（`bars_labeled` 画左上、其余画右下）                                                                                                 |
| `zero_line`       | bool               |      | 只影响通用留白分支（`lines` 等）：把 0 纳入数据域                                                                                             |

### 1.1 长度规则（最容易踩的一条）

设 `n = xlabels.length`（heat_matrix 除外，它完全不看 xlabels）。

- 所有绘图循环都是 `for i < n`，**数据数组必须恰好长 n**。
- **短了**：尾部按缺失处理 —— 对有 `isNum()` 守卫的 kind 是安全的（少画几根柱），
  对 `stacked_dual` 会算出 `NaN` 坐标（`base[i] + undefined`），rect 直接画不出来。
- **长了**：多出来的点画不出来，但**仍然参与 y 轴量程计算**
  （`lv` 取的是整个数组，`lines` / `grouped_bars` / `seasonality` / `range_band` /
  `bar_line` / `diverging_bars` / `bars_labeled` / `gs_*` 都如此）——
  结果是纵轴被一个看不见的点撑开，图被压扁而没有任何提示。
  只有 `bridge_bar` 与 `stacked_dual` 的量程按 `i < n` 算，不受影响。
- 同一 exhibit 内所有系列（`series[*].values`、`stacks[*].values`、`groups[*].values`、
  `lo/hi/actual`、`line.values`、`yoy.values`）长度必须一致，都等于 n。
- `heat_matrix`：`matrix.length === rows.length`，且每行 `matrix[i].length === cols.length`。
  对不上不报错 —— 缺的格子按缺失画成浅灰，**看起来就像那个月没数据**。

`build/verify_pages.py` 会把以上全部机器校验一遍。

### 1.2 空值（null）容忍度

`null` 是合法值（缺月、未满季作废的同比、滞后一月的 RPC），但**只有一半 kind 真的容忍它**。
分水岭是「这条线要不要过 Catmull-Rom 平滑」：平滑函数直接做算术，`null` 被 JS 当成 `0`，
于是画出一条**塌到零的假线**，而且不报错。

| 容忍 null（线断开 / 柱跳过）                                                                                                                                                             | 不容忍 null（必须逐点稠密）                                                             |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| `lines` `year_lines` `bar_line` `bar_line_dual` `diverging_bars` `bars_labeled` `qtr_bar` `seasonality` `bridge_bar` `grouped_bars` `range_band` `heat_matrix` `gs_bar`(含 `yoy.values`) | `gs_line` `gs_line_avg` `lines_endlabels` `stacked_dual`（`stacks` 与右轴 `line` 都是，`line` 不给时只查 `stacks`） |

不容忍那一侧的具体后果：

- `gs_line` / `gs_line_avg`：平滑曲线先塌到 0，随后逐点标数值时 `null.toFixed()`
  **抛 TypeError** —— 该卡片以下的渲染全部中断（同一页后面的 exhibit 都不会出现）。
- `lines_endlabels`：首尾任一为 `null` 同样抛 TypeError；中间的 `null` **不抛**，
  只是把线画塌到 0，最难发现。
- `stacked_dual`：段高算出 `NaN`，该柱不画；右轴线塌到 0。

对策：这四种图型在 Python 侧就要把窗口截到「所有序列都有值」的区间，别指望引擎兜底。

`gs_bar.stacks`（§3.6）是这张表的一个附带条件：**段值本身容忍 `null`**（该段不画，柱不塌），
但**只要 `values[i]` 是数，各段在 i 处就必须全部有值** —— 少一段，那根柱就只画到「已有段之和」
的高度，看着像「这个月分部数据不全」，实际是漏了一整块业务。
这条不在引擎里兜底（兜底 = 把漏掉的一块画成一根矮柱，而矮柱看着完全正常），
`build/verify_pages.py` 硬 ERROR。

### 1.3 会抛异常（整页后续 exhibit 全丢）的必填对象

引擎在算 y 量程时直接解引用，缺了就是 TypeError，不是「画个空白」：

| kind                                                                 | 缺了就抛的字段                                          |
|----------------------------------------------------------------------|---------------------------------------------------------|
| `bar_line` / `bar_line_dual`                                         | `bar.values`、`line.values`                             |
| `lines` / `lines_endlabels` / `year_lines`                           | `series`（数组本身）                                    |
| `seasonality`                                                        | `base`、`actual`（两个对象都要在，`values` 可为空数组） |
| `grouped_bars`                                                       | `groups`                                                |
| `bridge_bar` / `stacked_dual`                                        | `stacks`（`stacked_dual` 的 `line` 是**可选**的，见下）  |
| `gs_line_avg`                                                        | `avg12`（要画右端均值文字）                             |
| 其余（`gs_bar` `gs_line` `qtr_bar` `diverging_bars` `bars_labeled`） | `values`                                                |

`gs_bar` 少了 `avg12` 不抛，但均线的坐标是 `NaN`，**那条虚线会静默消失**，
而图例里仍写着 `Prior 12mo Avg.`。

`gs_bar.stacks` 是可选的，缺了不抛也不影响任何别的东西（不给就是从前的单色柱）；
但**给了就等于多了一条恒等式**，而引擎**不替 payload 求和**：柱高照 `values` 画、
填色照 `stacks` 画，两者对不上时画面不报错。见 §3.6。

---

## 2. 格式器与颜色

**格式器名**（`fmt` / `yfmt` / `label_fmt` / `line.yfmt` / `yoy.yfmt` 共用一张表）：

| 名                                 | 输出                         | 名                   | 输出                                             |
|------------------------------------|------------------------------|----------------------|--------------------------------------------------|
| `f0` `f1` `f2` `f3`                | `29` `29.2` `29.24` `29.241` | `pct0` `pct1` `pct2` | `29%` `29.2%` `29.24%`                           |
| `f0c` `int`                        | `1,234`（千分位）            | `pct0z`              | 同 `pct0`，但绝对值 < 0.5 印 `0%`（消灭「-0%」） |
| `usd0` `usd1` `usd2` `usd3` `usd4` | `$29` … `$29.2412`           | `pp0` `pp1`          | `+5pp` `+5.1pp`（自带符号）                      |
| `x0`                               | `29X`                        | 缺省 / 不认识的名字  | **静默退回 `f1`**                                |

最后一条是坑：`fmt: 'pct'`（少写一个 0）不会报错，只会把 3 位小数的 RPC 印成 1 位。

**颜色名**：`NAVY`(#1F3864) `BLUE`(#9DC3E6) `MBLUE`(#2E75B6) `GRAY`(#A6A6A6)
`GREEN`(#548235) `GOLD`(#BF9000) —— 数据色只有这 6 个；
`RED`(#B23A48) 是断点与截轴离群值的专用色，**不做数据色**；
`WHITE` `GRID` `AXIS` `INK` 是版式色。
不认识的名字**静默退回 NAVY**（写 `'ORANGE'` 不会报错，只会多出一条与别人同色的线）。

推论（本仓的硬规矩）：**一张图最多 5 条靠颜色区分的序列**。成员超过 6 家的横截面，
必须改用身份靠标签的图型 —— `heat_matrix`（行标签）、`diverging_bars`（x 标签）、
`grouped_bars`（组图例 ≤4 组）。不要画 12 条折线。

---

## 3. 逐个 kind 的数据契约

### 3.1 `bar_line` —— 柱 + 线，同一根轴

```js
{ n: 2, kind: 'bar_line', title: '…',
  bar:  { name: '净销售额', color: 'NAVY',  values: [...], yfmt: 'usd0' },
  line: { name: 'y/y',      color: 'GREEN', values: [...], yfmt: 'pct0' },
  fmt: 'f1', ylab: '十亿美元' }
```
两条序列共用左轴 —— 只有量纲相同时才该用它，否则用 `bar_line_dual`。
图例顺序是「线在前、柱在后」（照 matplotlib 的 legend handles）。
`yfmt` 的取值优先级：`ex.yfmt` > `ex.bar.yfmt`。

### 3.2 `bar_line_dual` —— 柱（左轴）+ 线（右轴）

字段同上，另加 `ylab2`。**总是双轴**，两轴零点默认对齐（见 §4）。
图例顺序是「柱在前、线在后」。

### 3.3 `bars_labeled` —— 柱 + 每柱数值

```js
{ n: 12, kind: 'bars_labeled', values: [...], label_fmt: 'f1', annot: '…' }
```
纵轴**强制 `y0 = 0`、`y1 = max×1.13`** ⇒ **含负值的序列不能用它**（负柱画到画布外）。
没有图例（`legendHTML` 对它返回空串）。每柱都标数值，无开关。

### 3.4 `diverging_bars` —— 正负分色柱 ⚠️ 有写死的中文文案

```js
{ n: 3, kind: 'diverging_bars', values: [...], fmt: 'pp1', xlabels: [...] }
```
正值 NAVY、负值 RED，颜色由引擎按符号定，payload 改不了。

> ⚠️ **引擎把 COST 的业务文案写死在这个 kind 里**：图例固定是
> 「Reported > Core（油汇顺风）」/「Reported < Core（油汇拖累）」，
> 表格视图与 tooltip 的行名固定是「Reported − Core」。`ex.legend` 被忽略。
> 用在交易所页（份额变化排序、累计增长排序）会印出「油汇顺风」四个字。
>
> 三条出路，按推荐度排：
> 1. 用 `grouped_bars` 只放一个 group —— 图例名、表格列名都能自定义，纵轴
>    `y0 = min(0, mn×1.15)` 正常容纳负值；代价是正负同色（组色一个，不再分色）。
> 2. 保留 `diverging_bars`，在 `note` 里说明图例文案是引擎缺省值 —— 但页面上仍会
>    出现与本页无关的「油汇」字样，不建议。
> 3. 不要用 `bars_labeled` 代替：它强制零基线，负柱会被画出画布。

### 3.5 `grouped_bars` —— 同一 x 上 2–4 根并排柱（+ 可选右轴线）

```js
{ n: 4, kind: 'grouped_bars', xlabels: ['2019-01','2026-06'],
  groups: [ { name: '基期份额', color: 'BLUE', values: [...] },
            { name: '当期份额', color: 'NAVY', values: [...] } ],   // 2–4 组
  line: { name: '误差（RHS）', color: 'RED', values: [...], yfmt: 'pct1' },  // 可选
  bar_labels: true,          // ← 默认 false，要标柱值必须显式打开
  fmt: 'f1', ylab: '%' }
```
- 组色缺省循环 `BLUE → NAVY → MBLUE → GRAY`，**第 5 组开始颜色重复**，所以上限 4 组。
- 给了 `line` 才变双轴；不给就是干净的单轴并排柱（横截面页多数情况都该省掉它，
  见 §4 的双轴代价）。
- 表格视图 / tooltip 列名 = 各组 `name` + `line.name`（缺省 `'Error'`）。

### 3.6 `gs_bar` —— 浅蓝柱 + 12 月均线 / 次轴 y/y

```js
{ n: 2, kind: 'gs_bar', values: [...], legend: '净新增账户', avg12: 123.4,
  fmt: 'f0', yoy_txt: '+24.6% y/y', mom_txt: '+3.1% m/m' }

{ n: 2, kind: 'gs_bar', values: [...], legend: '…', ylab2: '% y/y',
  yoy: { name: 'y/y（RHS）', values: [...], color: 'GOLD', yfmt: 'pct0' } }
```
- 给了 `yoy` ⇒ 画次轴同比折线、**不画均线**（`avg12` 可省），气泡 `yoy_txt` 自动不画。
- 没给 `yoy` ⇒ 画 `avg12` 虚线，图例写 `Prior 12mo Avg.`；`avg12` 缺失时虚线静默消失。
- `mom_txt` 气泡按窗口末端定位（`n-4` / `n-2`），要求 `values[n-1]` 是数。
- 柱顶数值标签会按实测 bbox 自动抽稀（最新一期永远保留），被抽掉的值在表格视图里都在。

#### 3.6.1 可选的分部堆叠 `stacks[]` —— 一根柱按业务分色，总额仍是 `values`

```js
{ n: 2, kind: 'gs_bar', values: [...], legend: '合并月营收', ylab2: '% y/y',
  yoy: { name: 'y/y（12M 滚动，RHS）', values: [...], color: 'GOLD', yfmt: 'pct0' },
  stacks: [ { name: 'ATM',   color: 'MBLUE', values: [...] },
            { name: '非 ATM', color: 'GRAY',  values: [...] } ] }   // Σ 逐格 == values
// ⚠️ 第 2 段是 GRAY 不是 GOLD：GOLD 已经被上面 yoy.color 占了，同色会触发
//    build/verify_pages.py 的硬 ERROR（次轴那条线无描边、画在柱之后，穿过同色段时整段看不见）
```

**语义**：这只是把「同一根柱」的填色从一块变成几块，**不是换了一个量**。
纵轴量程、柱顶数值标签、12 个月均线、次轴 y/y 折线一律照 `ex.values`（总额）走，一格都不改。
不给 `stacks` 时整段绘制逻辑跳过，输出与从前**逐字节相同**（与 `yoy` / `zero_base` 同一条
「默认关闭」的规矩，IBKR 那 5 张已上线的 `gs_bar` 正走原路径）。

- **段间留 1.2px 白缝**（首段不留，否则柱底浮空）：两段亮度接近时没有缝就看不出分界。
- **图例改列各分部**：给了 `stacks` 之后，原来那个「浅蓝方块 + `ex.legend`」不再画 ——
  画面上根本没有一块浅蓝，再印它就是给一个不存在的颜色配文字。`ex.legend` 仍然是
  **表格视图 / tooltip 里总额那一行的行名**，只是不出现在图例上。
- **表格视图与 tooltip 逐段列出**：总额一行 + 每个分部一行（+ 有 `yoy` 时同比一行）。
  图上分了色、表里只有一个总额，等于把刚画出来的拆分又藏起来。
  同时总额那一行的色块由浅蓝 `BLUE` 换成 `NAVY`（本站「合计 / 合并」的既定用色）——
  画面上没有一块浅蓝，色块对不上任何东西。

**三条硬约束**（都写进了 `build/verify_pages.py`，是 **ERROR 不是 WARN**）：

| 约束 | 不满足会怎样（画面**不报错**） |
|---|---|
| 各段之和逐格 `== ex.values`（相对容差 `1e-6`） | 引擎不替 payload 求和。少了 → 柱顶留一截空白，看着像「这个月分部数据只有一部分」；多了 → 最上面那段溢出柱顶、盖住数值标签 |
| 各段**必须显式给 `color` 且互不重复** | 缺省色与同色段在一根柱里连不出分界，图例也指不到具体哪一段（不认识的颜色名还会静默退回 `NAVY`，见 §2） |
| 与 `ycap` / `bar_marks` **不兼容** | 引擎对这两种柱**退回单色**：截轴的断口语义是「这根柱到不了顶」，分段后断口落在最上面那一段上、读者无从判断是哪一段被切；斜纹是整根柱的标记，分段会把它切碎。退回单色本身是对的，问题是**图例仍列着各分部** —— 读者看到的柱与图例对不上 |

配色由 Python 侧的调用方决定，而且**同一块业务在几张图上必须同色**：
`build/mrbase.py` 为此设了共用常量 `_SEG_COLORS = ('MBLUE', 'GRAY', 'GREEN', 'GOLD')`，
Ex2 的堆叠段 / `mix` 的 100% 堆叠段 / `hist` 的分部线三张图共用同一份、按 `spec['segments']`
的顺序取色。三张图各配各的色，等于让读者在同一页里把同一块业务认成三块。

⚠️ **GOLD 排在第 4 位是为了躲 Ex2 的次轴同比线**（那条固定 GOLD）。所以先出事的
不是第 5 段而是**第 4 段** —— 它会拿到 GOLD、与右轴那条线撞色，触发硬 ERROR。
第 5 段起才轮到 `_SEG_COLORS[k % 4]` 绕回第 1 段、撞「各段配色互不重复」。
⇒ **分部超过 3 块**就要先在 Python 侧把小块并成「其他」，或显式改掉 `yoy.color`。
（第 3 段本身也是雷：MBLUE vs GREEN 对比度只有 1.07:1、灰度差 1.7%。）
这与 §2 那条「一张图最多 5 条靠颜色区分的序列」是同一件事的两个面。

#### 3.6.2 为什么不用现成的 `stacked_dual`

这是本字段最重要的一条设计理由，**新加分部堆叠之前先读这一条**。

`stacked_dual`（§3.14）看上去正好是「堆叠柱 + 右轴线」，但它的**右轴被写死**成
`ticks(0, rc.ymax || 60, 6)`、`r0 = 0` —— 下界恒为 0，画不出负值。

而 `gs_bar` 这里的次轴是**12 个月滚动同比，会转负**：日月光实测最低 **−13.6%**、
创意实测最低 **−23.0%**（创意 92 个有值月里 **26 个为负**）。
把这条线放进 `stacked_dual`，所有负值点会被顶到轴外 —— 页面等于在宣称
**「增速从没转负过」**，而且不报任何错。这是口径谎话，不是排版偏好。

其余几条也对不上，但都排在上面这条之后：`stacked_dual` 的右轴点标签硬编码成
`toFixed(1) + '%'`、堆叠段的表格格式硬编码 `f0c`（§6），也**不容忍 `null`**（§1.2），
而 `gs_bar` 的分部段允许缺段不画。

### 3.7 `gs_line` / `gs_line_avg` —— 平滑线 + 每点数值

```js
{ n: 3, kind: 'gs_line', values: [...], fmt: 'pct1', ovals_at_bottom: true,
  yoy_txt: '…', mom_txt: '…' }
{ n: 7, kind: 'gs_line_avg', values: [...], avg12: 41.2, avg_label: 'Prior 12mo Avg.',
  legend: 'DARTs', fmt: 'f0c' }
```
**`values` 必须逐点稠密**（见 §1.2）。`gs_line_avg` 的 `avg12` 必填。
`gs_line` 没有图例（`legendHTML` 返回空串），系列名只出现在表格视图 / tooltip，
取 `legend || ylab || '数值'`。

### 3.8 `heat_matrix` —— 行 × 列热力矩阵 ⚠️ 完全不看 xlabels

```js
{ n: 2, kind: 'heat_matrix', full: true, title: '增长动量矩阵：12 家 × 近 24 个月',
  rows: ['ICE','Cboe','NDAQ', …],          // 行标签，自上而下
  cols: ['Jul-24','Aug-24', …],            // 列标签；缺省是 Jan..Dec 十二个月
  matrix: [[5.1, 4.8, null, …], …],        // rows.length × cols.length，缺失写 null
  fmt: 'pct0',                             // 格内数值格式
  reverse: false,                          // 缺省低红高绿；true = 高红低绿（逾期率这类反向指标）
  legend: '成交量 y/y',                     // 只进 tooltip，不是图例（图例是色标）
  cell_h: 19,                              // 单元格高，钳在 13–26
  row_lab_w: 44,                           // 左侧行标签列宽（缺省 32，交易所名要加宽）
  row_head: '交易所' }                      // 表格视图首列表头，缺省「年」
```
- 色标 = 全部有限值的 **5/95 分位**，超出的钳到端点色。
  ⇒ **每张矩阵各算各的色标，两张矩阵之间颜色不可比**，必须在 `note` 里写明。
- 缺失格填浅灰 `GRID`，表格视图写 `—`。
- 格内字色按底色亮度自动黑 / 白；字号按格宽自动收缩到 4.6px 下限
  ⇒ 列数多时**务必 `full: true`**，半栏 24 列基本读不出数字。
- **不支持 `xlabels` / `break_at` / `ycap` / `yfloor` / `xstep` / `xrot` / `height`**
  （高度 = 行数 × `cell_h` + 18）。
- 图例是一条色标 + 两端真值（`5–95 分位色标`）。

### 3.9 `lines` —— N 条折线（横截面页的主力）

```js
{ n: 4, kind: 'lines', x: 'long', height: 360, full: true,
  series: [ { name: 'ICE', color: 'NAVY', values: [...] },
            { name: 'Cboe', color: 'MBLUE', values: [...] } ],   // ≤5 条
  zero_base: true,      // 纵轴从 0 起（长历史图必给，不给等于一次没标注的隐性截轴）
  end_label: true,      // 每条线末点标数值（长历史图上唯一的绝对水平锚点）
  markers: false,       // true = 每个数据点画圆点
  fmt: 'f0', label_fmt: 'f0', ylab: '2019-01 = 100' }
```
- 不平滑（折线直连），`null` 处断开 —— 这是**唯一能安全吃缺口的多线图型**。
- 开了 `end_label` 的长历史图 **`height` 要给到 ≥ 360**：末点标签的避让逻辑在
  绘图区高度 < 308px 时会把整列标签收成一摞贴右上角，读数会安到别的线上
  （`build/exchanges.py` 的 `LINE_H_ENDLABEL = 360` 就是为此定的，别改小）。
- `zero_base` 遇到含负值的序列时下界仍留在数据之下，不会把负值压没。

### 3.10 `lines_endlabels` —— N 条平滑线，只标两端

字段同 `lines`（`series[]`），但**平滑 + 首尾必须有值**（见 §1.2），
且没有 `zero_base` / `end_label` 开关。左端标签有自己的 30px 专列，两端标签会竖向避让。
适合「take rate 三家对比」这类首尾都齐、要读绝对水平的图。

### 3.11 `qtr_bar` —— 季度柱 + 右轴 y/y

```js
{ n: 8, kind: 'qtr_bar', xlabels: ['2Q23', …, '2Q26'],
  values: [214, …, 205],                 // 季度合计，Python 侧算好
  partial_months: 2, qtr_months: 3,      // 末季只含 2 个月 → 末柱浅蓝 + 图例写 QTD
  line: { name: 'y/y（RHS）', color: 'GREEN', values: [...], yfmt: 'pct0' },
  legend: '季度合并成交量',                // 完整季那根柱的图例名，缺省 'Complete quarter'
  bar_labels: true,                      // 默认开；给 false 关掉柱顶竖排数值
  fmt: 'f0c', ylab: '百万股/日' }
```
**未满季的 y/y 由引擎强制作废**：给了 `partial_months < qtr_months` 时，右轴那条线的
最后一点会被丢掉（绘图 / 量程 / 表格 / tooltip 四处一致）。别再自己传 `null`，也别指望它保留。

### 3.12 `range_band` —— 区间带 + 实际值菱形

```js
{ n: 6, kind: 'range_band', xlabels: [...],
  lo: [...], hi: [...],                  // 缺失 null → 该期不画带
  actual: [...],                         // 未披露写 null
  qtd: 4.86, qtd_at: 7,                  // 可选：进行中期的累计值 + 落在第几格（缺省最后一格）
  actual_color: 'NAVY',
  names: { range: '分布带 P10–P90', actual: '中位数', qtd: '本季至今',
           lo: 'P10', hi: 'P90' },       // range/actual/qtd 进图例；lo/hi/actual/qtd 进表格
  bar_labels: true,                      // 默认开；false 关掉实际值旁的数值
  fmt: 'f1', ylab: '% y/y' }
```
横截面页拿它画 y/y 分位带时：`lo`=P10、`hi`=P90、`actual`=中位数，
**必须用 `names` 把「指引区间 / 实际」的缺省文案改掉**，否则图例写着「Guidance range」。

### 3.13 `seasonality` —— 灰=同月均值 / 蓝=本期实际

```js
{ n: 9, kind: 'seasonality', xlabels: [13 个月标签],
  base:   { name: '过去 5 年同月均值', values: [...], color: 'GRAY' },
  actual: { name: '今年实际',          values: [...], color: 'MBLUE' },
  bar_labels: true, fmt: 'f0c', ylab: '百万股/日' }
```
`base` 与 `actual` 两个对象都必须存在（缺一个抛异常）。数值标签只标 `actual`。
「过去 N 年」的 N 与均值本身都在 Python 算，把 N 写进 `base.name` 或 `note`。

### 3.14 `stacked_dual` —— 堆叠柱 + 右轴百分比线 ⚠️ 右轴写死成百分号

```js
{ n: 2, kind: 'stacked_dual', xlabels: [...],
  stacks: [ { name: 'Cboe', color: 'NAVY',  values: [...], label: true, label_color: 'WHITE' },
            { name: 'MIAX', color: 'MBLUE', values: [...], label: true },
            { name: '其余', color: 'GRAY',  values: [...] } ],
  line: { name: '行业 ADV（RHS）', color: 'GREEN', values: [...], ymax: 60 },
  ylab: '千张/日', ylab2: '%' }
```
- **`line` 是可选的**：不给就退化成**纯堆叠柱** —— 右轴刻度、图例里那一项、
  表格视图里那一行、以及柱顶那 28% 的留白（它本来是给右轴线的逐点标签用的）一并消失，
  左轴改成 `0 .. 堆叠总高 ×1.06`。
  什么时候不该给：**占比型堆叠**（各段之和恒为 100）里段高本身就把每一块读出来了，
  再拿其中一段换个刻度画一遍是同一个数说两遍。
  ⚠️ **判据是「最矮那一段在 0–100 的堆叠里量不量得出来」，不是段数。**
  段数只是它的代理，而且会失准两次：两段业务各占四五成时（ase / guc 的 Ex5）
  线是纯冗余，该去掉；两段里有一段常年 99%+ 时（`/tmx/` Ex12 的
  SXF vs 其余股指期货，最矮那段 0.04%~5.9%）线反而是这张图的**全部内容**。
  给了线就在 `ylab2` 里照实写「同一条序列换个刻度」（`/exchanges-eu/` Ex2 的措辞），
  别让读者当成第四个量。
- 左轴强制 `0 .. 堆叠总高 ×1.28`（无 `line` 时 ×1.06）；右轴强制 `0 .. line.ymax`
  （**缺省 60**，给了 `line` 就几乎一定要显式给 `ymax`）。
  ⚠️ **右轴下界写死成 0（`r0 = 0`），右轴线含负值的图不能用这个 kind** ——
  负值点会被顶到轴外，画面不报错，读者只会读到「这条线从没转过负」。
  要「堆叠柱 + 会转负的次轴线」，走 `gs_bar` 的 `stacks` + `yoy`（§3.6.1 / §3.6.2）。
- `line.values` 的**数值标签硬编码成 `toFixed(1) + '%'`**，表格视图里也硬编码 `pct1`
  ⇒ 右轴那条线必须是「百分数的数值」（41.5 表示 41.5%）。
  **堆叠段的表格格式跟着 `ex.fmt` 走**（2026-08-14 起；不声明才退回 `f0c`）——
  占比型堆叠请显式写 `fmt: 'pct1'`，不写会被截成整数。
  ⚠️ 段**内**那个标签（`label: true`）仍然硬编码 `comma(v, 0)`，只印整数、不跟 `fmt`。
- `label: true` 才在段内写数值（字号 6.6px，段高 < 8px 时自动不写）。
- **不支持截轴**（截一段堆叠柱等于把总量画错）；`values` 必须逐点稠密。
- 份额堆叠带的用法：把「1 − Σ 已知家」的残差做成最后一个 GRAY 段，并在 `note` 里
  点名残差是什么。

### 3.15 `bridge_bar` —— 正上负下的归因桥 + 净额菱形

```js
{ n: 8, kind: 'bridge_bar', xlabels: ['池扩大', '份额转移', '交叉项'],
  stacks: [ { name: '池扩大 s₀·ΔI', color: 'NAVY', values: [...] },
            { name: '份额转移 I₀·Δs', color: 'MBLUE', values: [...] },
            { name: '交叉项 Δs·ΔI',   color: 'GRAY', values: [...] } ],
  net: { name: 'ΔADV 合计', values: [...] },     // 建议显式给；省略则按 stacks 求和
  net_color: 'INK', fmt: 'f0c', ylab: '千张/日' }
```
- 每一列各自把正的往上堆、负的往下堆，菱形标净额 —— 一列 = 一个时点或一个分解项。
- 截轴对堆叠段也生效（段画到边界 + 断口 + 竖排真值），整段在界外的不画。
- 恒等式是这张图的全部意义：`net` 与 `Σstacks` 对不上时引擎不会告诉你，Python 侧要断言。

### 3.16 `year_lines` —— 每年一条线叠在 12 格上

```js
{ n: 10, kind: 'year_lines', xlabels: ['Jan', …, 'Dec'],
  series: [ { name: '2021', values: [12 个数] }, …,
            { name: '2026', values: [4.1, …, null, null] } ],   // 未完年后面填 null
  highlight: 5,          // 高亮第几条（0-based），缺省最后一条
  fmt: 'f1', ylab: '…' }
```
往年线走 `BLUE → NAVY` 的等间距明度阶（越早越淡），高亮年为 `RED` + 圆点 + 末点数值。
`series[k].color` 可逐条覆盖，覆盖的那条不占阶梯位置。累计与否由 Python 决定。

---

## 4. 双轴的规则与代价

- 触发条件：`bar_line_dual` / `stacked_dual` 恒为双轴；`qtr_bar` / `grouped_bars` 给了
  `line`、`gs_bar` 给了 `yoy` 才是双轴。
- **两轴零点默认画在同一高度**（只扩不缩，数据点一个都不会被挤出去）。
- 对齐代价 = 扩出来的量程 ÷ 对齐后的量程；超过 **0.38** 就放弃对齐，两轴各自缩放，
  并在绘图区左上角画一行红字「左右轴零点不同高（两轴独立缩放）」。
- 代价大多来自「柱全为正、线跨零」的组合 —— 左轴会被拉到负区，下方四成画布全空。
  **不能接受就省掉 `line`**，把那条信息写进 `note` 或另起一张图。
- 右轴末点读数与右轴刻度冲突时，**刻度让位**（读数是数据，刻度只是标尺）。

---

## 5. `bar_labels` 的默认值随 kind 不同

| kind                                                                        | 默认                           | 关 / 开的写法          |
|-----------------------------------------------------------------------------|--------------------------------|------------------------|
| `qtr_bar`                                                                   | **开**                         | `bar_labels: false` 关 |
| `seasonality`                                                               | **开**（只标 actual）          | `bar_labels: false` 关 |
| `range_band`                                                                | **开**（只标 actual）          | `bar_labels: false` 关 |
| `grouped_bars`                                                              | **关**                         | `bar_labels: true` 开  |
| `bars_labeled` `gs_bar` `gs_line` `gs_line_avg` `year_lines`                | 恒开，无开关                   | —                      |
| `stacked_dual`                                                              | **逐段**，缺省关               | 段上写 `label: true` 开 |
| `bar_line` `bar_line_dual` `lines` `diverging_bars` `heat_matrix`           | 恒关（`lines` 用 `end_label`） | —                      |

`gs_bar` 给了 `stacks` 时柱顶那个数**仍然是总额**（`values[i]`），不是任何一段 ——
段内不写数值（柱太窄，写了必压字），分部的逐月数值在表格视图里逐段列着（§3.6.1）。

---

## 6. 引擎里写死、payload 改不了的文案

写新页之前先看这张表 —— 这些字符串会原样出现在页面上。

| 位置                      | 写死的内容                                                    | 能不能绕                         |
|---------------------------|---------------------------------------------------------------|----------------------------------|
| `diverging_bars` 图例     | `Reported > Core（油汇顺风）` / `Reported < Core（油汇拖累）` | ✗ 只能换 kind                    |
| `diverging_bars` 表格列名 | `Reported − Core`                                             | ✗                                |
| `stacked_dual` 右轴点标签 | `值.toFixed(1) + '%'`                                         | ✗（数值必须是百分数）            |
| `stacked_dual` 表格格式   | 线 = `pct1`；**段跟着 `ex.fmt` 走**（不声明才退回 `f0c`）     | 段可绕（给 `fmt`），线 ✗         |
| `qtr_bar` 未满季图例      | `QTD (2 of 3 months)`                                         | ✗（`legend` 只改完整季那条）     |
| `gs_bar` 均线图例         | `Prior 12mo Avg.`                                             | 给 `yoy` 就没有这条              |
| `gs_bar` 单系列图例方块   | 浅蓝 `BLUE` + `ex.legend`                                     | 给 `stacks` 就换成逐段方块，`ex.legend` 不再进图例（仍是表格总额行名） |
| `gs_bar` 表格总额行色块   | 浅蓝 `BLUE`                                                   | 给 `stacks` 时自动换 `NAVY`      |
| `grouped_bars` 线名缺省   | `Error (RHS)`                                                 | ✓ 给 `line.name`                 |
| `range_band` 图例缺省     | `Guidance range` / `Actual` / `Quarter-to-date`               | ✓ 给 `names{}`                   |
| `seasonality` 图例缺省    | `Prior-year same-month avg.` / `Actual`                       | ✓ 给 `base.name` / `actual.name` |
| `bridge_bar` 净额名缺省   | `Net change`                                                  | ✓ 给 `net.name`                  |
| `qtr_bar` 完整季图例缺省  | `Complete quarter`                                            | ✓ 给 `legend`                    |
| 表格视图首列表头          | `期间`（`heat_matrix` 走 `row_head`，缺省 `年`）              | ✗ / ✓                            |

---

## 7. 自检

写完 build 脚本先跑：

```
python3 build/verify_pages.py            # 起 http.server，抓页面 + 校验全部 data/*.js
python3 build/verify_pages.py --pages exchanges12,exchanges-na,exchanges-eu
```

它检查：HTTP 200、页面引用的 `data/*.js` 与 `assets/*` 可取、payload 是合法 JS
（`node --check`）与合法 JSON、`window.DASH` 顶层字段齐全、每个 exhibit 的 `kind`
在 17 种白名单内、所有数据数组长度与该图的 `xlabels` 一致、`heat_matrix` 的
`matrix` 维度与 `rows`/`cols` 相符、无 `NaN` / `undefined` / `Infinity` 字面量、
格式器名与颜色名都认得、以及 §1.2 / §1.3 的空值与必填对象规则。

`gs_bar` 的分部堆叠另有三条硬 ERROR（§3.6.1，都是「画面不报错」那一类）：

| 判据 | 为什么必须在这里查 |
|---|---|
| 各段之和逐格 `== ex.values`（相对容差 `1e-6`） | 引擎不替 payload 求和；差额变成柱顶一截空白或最上一段溢出 |
| 各段显式给 `color` 且互不重复 | 同色两段连不出分界，图例指不到具体哪一段 |
| 不与 `ycap` / `bar_marks` 同时出现 | 引擎对这些柱退回单色，而图例仍列着各分部 |

外加一条：`values[i]` 非 null 时各段在 i 处必须全部有值，缺一段就是一根短柱（§1.2）。
