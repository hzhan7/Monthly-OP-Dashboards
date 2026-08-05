# charts.js 图型数据契约（新增 7 种）

引擎：`assets/charts.js`。零依赖、零构建、不 fetch —— exhibit 对象由 `build/<t>.py` 写进
`data/<t>.js` 的 `window.DASH.exhibits`，`assets/page.js` 逐个交给 `window.Exhibits.card()`。

自测页：`cache/enginetest.html`（14 种 kind 全画一遍，含负值 / 缺失点 / 需截轴的离群值 / 断点）。

> **总原则**：数值一律在 Python 侧算好、格式化口径也在 Python 侧定。累计值、历史同月均值、
> 季度合计、误差率都不要指望 JS 去算。唯一例外是 `bridge_bar` 的净额 —— 没给 `net` 时才按
> 恒等式求和，因为那是加法恒等式而不是口径判断。

---

## 0. 所有 kind 通用的字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `n` | int | Exhibit 编号，进标题 |
| `kind` | string | 图型 |
| `title` | string | 标题（不含 "Exhibit n:" 前缀） |
| `xlabels` | string[] | 该图自己的 x 轴标签。**新 kind 基本都要自带**，别指望 `DASH.xlabels`（那是 13 个月窗口） |
| `full` | bool | 通栏（`heat_matrix` 一般要 `true`） |
| `height` | int | 覆盖默认画布高 |
| `ylab` / `ylab2` | string | 左/右轴标题 |
| `fmt` / `yfmt` | string | 数值 / 轴格式器名（见下表） |
| `label_fmt` | string | 数据标签用的格式器，缺省回退 `fmt` |
| `legend` | string | 单系列图的图例名 |
| `note` / `src_extra` | string | 卡片下方说明 |
| `xrot` / `xstep` | int | x 标签角度（0/45/90）、每隔几个标一次 |
| `ycap` / `yfloor` | number | 截轴上/下界。**截轴不删点**：超界的柱画到边界 + 断口符号，超界的点画空心红圈，真值一律竖排标出 |
| `cap_note` | string | 截轴时右上角的斜体小字，如 `axis capped — outlier shown in red` |
| `break_at` | int \| int[] | 结构性断点的 x 索引，红色竖虚线画在**该期左缘**，语义是「从这一期起与左侧不可比」 |
| `break_label` | string \| string[] | 断点竖排标签；给一条时所有断点共用 |
| `bar_marks` / `mark_note` | int[] / string | 斜纹柱（不可比期）与它在 tooltip 里的解释 |
| `bar_labels` | bool | `false` 关掉每柱/每点数值标签（`grouped_bars` 相反，默认关、给 `true` 才开） |

格式器名：`f0 f1 f0c int pct0 pct1 pct0z pp0 pp1 x0 usd0 usd1 usd2`。
颜色名只许用 `C.*` 常量名：`NAVY BLUE MBLUE GRAY GREEN RED WHITE GRID AXIS INK`（也可直接写 `#RRGGBB`，但别这么干 —— 这套色已过色盲安全校验）。

---

## 1. `heat_matrix` ← `gsx.heat_matrix`

行=年、列=月的热力矩阵，格内写数值，发散配色。**不吃 `xlabels`，自己排版**，建议 `full: true`。

```js
{ n: 11, kind: 'heat_matrix', full: true, title: '可比销售 y/y：月 × 年',
  rows: ['2019','2020', …],          // 行标签（年），从旧到新
  cols: ['Jan','Feb', …],            // 列标签，缺省为 Jan..Dec
  matrix: [[5.1, 4.8, …], …],        // rows.length × cols.length，缺失写 null
  fmt: 'pct1',                       // 格内数值格式
  reverse: false,                    // true = 高值红、低值绿（缺省低红高绿，同 gsx RdYlGn）
  legend: '可比销售 y/y',            // tooltip 里的系列名
  cell_h: 19,                        // 单元格高（13–26，缺省 19）
  row_lab_w: 32, row_head: '年' }    // 左侧行标签宽 / 表格视图的首列表头
```

- 色标取全部有限值的 **5/95 分位**（同 gsx），一两个离群月不会把整表压平；超出分位的格子钳到端点色。
- 格内字色按底色亮度自动黑/白（gsx 固定用深色字，在深红/深绿格上读不出来，网页版不跟）。
- 缺失格填 `C.GRID` 浅灰，表格视图里写 `—`。
- 图例是一条色标 + 两端真值（gsx 那边没有色标，读者只能靠格内数字）。
- 字号按格宽自动收缩，保证数字不压出格子。
- **不支持 `break_at` / `ycap`**（矩阵没有连续 x 轴）。

## 2. `year_lines` ← `gsx.year_lines`

每年一条线叠在 1–12 月轴上，当年高亮加粗。

```js
{ n: 12, kind: 'year_lines', title: '年初至今累计净流入',
  xlabels: ['Jan', …, 'Dec'],        // 必给
  series: [ { name: '2021', values: [12 个数，缺失 null] }, …,
            { name: '2026', values: [4.1, …, null, null] } ],   // 未完年后面填 null
  highlight: 5,                      // 高亮哪一条，缺省最后一条
  fmt: 'f1', label_fmt: 'f1', ylab: '十亿美元' }
```

- `cumulative` 由 Python 决定：**传进来的就是要画的值**，本文件不再 cumsum。
- 配色阶梯由旧到新 = 浅灰 → 浅蓝 → BLUE → MBLUE → NAVY，高亮年 = `C.RED` + 圆点标记 + 末点数值。
  条数超过 6 时阶梯会自动摊开（gsx 那边超过 5 条就全挤成 NAVY）。
  `series[k].color` 可逐条覆盖。
- 默认 `xrot: 0`（月份水平标，同 PDF）。

## 3. `qtr_bar` ← `gsx.qtr_bar`

月度序列汇总成的季度柱 + 右轴 y/y，末季未满时标成「本季至今」。

```js
{ n: 13, kind: 'qtr_bar', title: '季度成交量',
  xlabels: ['2Q23', …, '2Q26'],
  values: [214, …, 205],             // 季度合计，Python 侧算好
  partial_months: 2, qtr_months: 3,  // 末季已含 2 个月 → 末柱浅蓝 + 图例写 "QTD (2 of 3 months)"
  line: { name: 'y/y（RHS）', color: 'GREEN', values: [null,…,-8.2], yfmt: 'pct0' },
  fmt: 'f0c', label_fmt: 'f0c', ylab: '成交量（百万张）',
  break_at: 8, break_label: '并表 XYZ' }
```

- 柱顶数值**竖排**（同 gsx 的 `rotation=90`），所以纵轴上界给到 `max × 1.32`；柱太高时标签会自动压回画布内。
- `line` 可省略 → 退化成单轴柱图，不画空的右刻度。
- gsx 的金色（`GOLD #BF9000`）不在本文件的 `C.*` 里，y/y 线默认退到 `GREEN`。

> **未满季的 y/y 由引擎强制作废。** 给了 `partial_months < qtr_months` 时，末季那根柱会
> 变浅蓝并在图例写「QTD (2 of 3 months)」，**同时右轴 y/y 的最后一点会被丢掉**（绘图、
> 右轴量程、表格视图、tooltip 四处一致）。原因：拿 2 个月的累计去比上年完整 3 个月，
> 必然砸出一个 -8% 之类的假坑，而线是连续的、没有任何视觉提示说这一点不可比 ——
> 读者会当成业务塌了。这是口径错误不是排版偏好，所以在引擎侧兜底，
> 不指望每个 build/<t>.py 都记得传 `null`。

## 4. `seasonality` ← `gsx.seasonality`

灰柱 = 过去 N 年同月均值，蓝柱 = 本期实际，两根在 band 中心相接。

```js
{ n: 14, kind: 'seasonality', title: '季节性对照',
  xlabels: [13 个月标签],
  base:   { name: 'Prior 10yr same-month avg.', values: […], color: 'GRAY' },
  actual: { name: 'Actual', values: […], color: 'MBLUE' },
  fmt: 'f1', label_fmt: 'f1', ylab: '十亿美元' }
```

- 数值标签只标 `actual`（同 gsx），负值时自动落到柱下方。
- 「过去 N 年」的 N 与均值本身都在 Python 算，图上不重算；把 N 写进 `base.name` 或 `note`。

## 5. `bridge_bar` ← `gsx.bridge_bar`

正的往上堆、负的往下堆，菱形标净额 —— 期初 + 净新增 + 市值变动 = 期末 的恒等式桥。

```js
{ n: 15, kind: 'bridge_bar', title: '客户资产滚存桥',
  xlabels: [13 个月标签],
  stacks: [ { name: '净新增资产', color: 'NAVY', values: […] },
            { name: '市值变动',   color: 'BLUE', values: […] },
            { name: '客户提取',   color: 'RED',  values: […] } ],
  net: { name: 'Net change', values: […] },   // 建议显式给；省略则按 stacks 求和
  net_color: 'INK',
  fmt: 'f1', ylab: '十亿美元', yfloor: -40, cap_note: 'axis floored — outlier shown in red' }
```

- 截轴对堆叠段**也生效**：段画到边界为止 + 柱端断口符号，该列的真实包络值竖排标出
  （不然一根 −46 的段会直接画到 x 轴标签底下）。整段落在界外的就不画，真值靠标签交代。
- 净额点被截时按通例画空心红圈；净额与包络重合的列（全正/全负）不重复标真值。
- gsx 的净额是纯黑 `#111111`，这里用 `C.INK`。

## 6. `grouped_bars` ← `gsx.implied_vs_actual`

同一 x 上两根并排柱（预测 vs 实际）+ 右轴误差线。

```js
{ n: 16, kind: 'grouped_bars', title: '桥算出的隐含季度 vs 实际披露',
  xlabels: ['3Q24', …],
  groups: [ { name: 'Implied by the bridge', color: 'BLUE', values: […] },
            { name: 'Actually reported',     color: 'NAVY', values: […] } ],   // 2–4 组
  line: { name: 'Error（RHS）', color: 'RED', values: […], yfmt: 'pct1' },
  bar_labels: false,                 // 默认不标柱值（同 gsx），给 true 才标
  fmt: 'f0c', ylab: '百万美元',
  note: '窗口内平均绝对误差 1.1%。' }  // MAE 在 Python 算好写进 note
```

- 未披露的期把 `values` 与 `line.values` 都写 `null`，柱与线自动断开。
- **注意双轴代价**：本引擎的硬规矩是「两轴零点必须落在同一条水平线上」。误差线跨零时，
  左轴会被迫向下扩到负区，柱子被压进画布上半张 —— 与 PDF（matplotlib 不对齐零点、
  误差线直接压在柱子上）观感不同。不能接受就**省掉 `line`**，把误差写进 `note` 或表格。

## 7. `range_band` ← `gsx.range_vs_actual`

指引区间画成带、实际值打菱形。

```js
{ n: 17, kind: 'range_band', title: '季度指引区间 vs 实际',
  xlabels: ['3Q24', …],
  lo: […], hi: […],                  // 指引下/上限，缺失 null（该期不画带）
  actual: […],                       // 实际值，未披露写 null
  qtd: 4.86, qtd_at: 7,              // 可选：进行中期的累计值 + 落在哪一格（缺省最后一格）
  actual_color: 'NAVY',
  names: { range: '指引区间', actual: '实际', qtd: '本季至今',
           lo: '指引下限', hi: '指引上限' },   // range/actual/qtd 进图例；lo/hi/actual/qtd 进表格
  fmt: 'f1', label_fmt: 'f1', ylab: '十亿美元' }
```

- 带子用 `C.BLUE` 填充，上下缘各画一条 `C.MBLUE` 细横杠（同 gsx 的 lo/hi 横线）。
- `qtd` 用空心红菱形，标签压在点下方，与实际值的标签分得开。
- 纵轴留白：整段非负时照 gsx 用 `min×0.88 / max×1.10`；**含负值时改成按极差加白**
  （乘法留白在负值上会往零点缩，把数据挤出画布）。
- 截轴对带子的上下端各自生效，被截的一端画断口 + 真值。

---

## 表格视图

每张卡右上角的「表格」都由 `seriesRows()` + `tableHTML()` 出，新 kind 全部实现了：

| kind | 表格列 |
|---|---|
| `heat_matrix` | 走单独的 `heatTable()`：行=年、列=月，原样铺开 |
| `year_lines` | 期间（Jan..Dec） + 每年一列 |
| `qtr_bar` | 期间 + 季度值 + y/y |
| `seasonality` | 期间 + 同月均值 + 实际 |
| `bridge_bar` | 期间 + 各分项 + Net change |
| `grouped_bars` | 期间 + 各组 + Error |
| `range_band` | 期间 + 下限 + 上限 + 实际 +（有 qtd 时）本季至今 |

表格比轴刻度多给一位小数（轴上写 `$29`，表格里应看到 `29.24`）。

## 已知边界

- 深浅色：`assets/style.css` 明确写死 `color-scheme: light`（PDF 是白底文档，反转会破坏 exhibit 的取色关系）。
  新图型全部用显式 fill，`prefers-color-scheme: dark` 下与浅色**逐像素相同**。
  Chrome 实验性的 `--force-dark-mode` 会强制反转页面，此时 `heat_matrix` 里接近白色的格子会被反成
  深色而格内字仍是深色 → 读不出来（`gs_bar`/`gs_line` 的白底气泡本来就有同样毛病）。
- `heat_matrix` 不支持 `break_at` / `ycap`；`stacked_dual` 不支持截轴（截一段堆叠柱等于把总量画错）。
