# 数据契约：build/&lt;t&gt;.py → data/&lt;t&gt;.js → assets/page.js + assets/charts.js

每家公司的生成器只做一件事：把 `series/*.csv` 算成一个 JSON payload，写进 `data/<t>.js`。
页面不做任何计算 —— 同一个数字在 Python 和 JS 里各算一遍，迟早会出现图上与表里对不上
而没人发现。**所有数值、所有格式化、所有口径判断都在 Python 侧完成。**

写法：

```python
with open(f'data/{t}.js', 'w', encoding='utf-8') as f:
    # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
    # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效，
    # 每天都会产出一个内容相同、只有日期变了的 no-op commit。
    f.write(f'// 由 build/{t}.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
    f.write('window.DASH = ')
    json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';\n')
```

---

## 1. payload 顶层

| 字段 | 必需 | 说明 |
|---|---|---|
| `ticker` | ✓ | 小写，与目录名一致（`cme` → `/cme/`） |
| `tracker` | ✓ | 抬头左侧与浏览器标题，如 `CME Monthly Volume Tracker` |
| `title` | ✓ | H1，如 `CME Group (CME): 月度成交量跟踪 — 2026年7月` |
| `data_through` | ✓ | `'YYYY-MM'`。**页面的新鲜度信号绑它，不绑构建日期** |
| `through_label` | ✓ | 人话月份，如 `2026 年 7 月`；零售日历公司可写 `零售月 Jun 2026（5 周）` |
| `subtitle` | ✓ | 副标题：数据源 + 覆盖区间 + 版式出处 |
| `headline` | ✓ | 一行数据条。正负号交给 f-string 的 `+` 标志，别写死字面量（负值会印成 `+-0.6%`） |
| `hub_line` | | 首页卡片上的短摘要（≤60 字）。不给则截取 `headline` 前 110 字 |
| `source` | ✓ | 所有 exhibit 共用的 `Source:` 行 |
| `source_date` | | 官方发布日 `YYYY-MM-DD`，显示在抬头右侧。**必须是源头自己写出来的日期**（文件里的 "Published on"、新闻稿电头、SEC filingDate，或该家 fetch docstring 已认定为发布日的 HTTP `Last-Modified`）。构建日、文件 mtime、下载时刻一律不行 —— 那是一句关于外部世界的事实断言，编不得。台账在 `series/source_dates.csv`，由 `fetch/<t>.py` 摄入该月时按月份钉进去、`build/<t>.py` 查表；**不要在 build 里当场从 `cache/` 解析**（cache 是 gitignore 的，清掉后这半句会静默消失，且缓存里可能躺着比 `data_through` 更新的一期文件，当场解析会把新一期的发布日安到旧月份上）。横截面页用 `latest_of()` 取成员里最晚的那个，缺任何一个成员就整体省略 |
| `source_date_note` | | 源头**根本不标**发布日时，改印这句话（如 MSCI 的「官方未标注发布日」）。只在 `source_date` 缺席时渲染。用于「这是那个源的固有属性」，**不要**用来搪塞「台账这个月还没记上」那种临时缺口 —— 后者应当留白并等它自愈 |
| `stale_source` | | `True` 时抬头打红标「官网下载失败，本次沿用本地缓存」。**目前没有任何生成器会产生它** —— 现有的 fetch 模块下载失败一律抛异常，那家整个跳过、`data_through` 原地不动，由首页红点报警。渲染分支保留着，但在有 fetch 真走「降级到旧缓存」这条路之前，不要在生成器里设它 |
| `xlabels` | ✓ | 短窗口 x 轴标签数组 |
| `xlabels_long` | | 长历史 x 轴标签数组；exhibit 写 `x: 'long'` 时用它 |
| `summary` | ✓ | Exhibit 1 汇总表，见 §2 |
| `exhibits` | ✓ | Exhibit 2..N，见 §3 |
| `table` | | 末尾核对表，见 §4 |
| `notes` | ✓ | 「口径与方法说明」的 `<li>` 数组，允许 HTML |
| `footer` | | 页脚 HTML |

## 2. summary（Exhibit 1 汇总表）

```python
'summary': {
  'title': '2026 年 7 月汇总 —— 本月 vs 上月／去年同月，及近 3 年分位',
  'heads': ['本月', '上月', '去年同月', 'm/m', 'y/y', '3Y %ile'],
  'sep':   3,          # 第几列前画竖分隔线（水平值与变化率之间），0-based
  'rows': [
    {'kind': 'group', 'label': '成交量'},                    # 板块分隔条
    {'label': 'ADV 千张', 'cells': [
        {'v': '30,100'}, {'v': '28,400'}, {'v': '26,900'},
        {'v': '+6.0%', 'cls': 'pos'}, {'v': '+11.9%', 'cls': 'pos'},
        {'v': '88', 'cls': 'hi'}]},
  ],
  'note': '分位为近 36 个月百分位。…',
}
```

`cells[i].v` 是**已经格式化好的字符串**，`cls` 取 `pos` / `neg`（绿/红）、`hi` / `lo`
（分位高/低）或空。格式化规则属于口径，必须在 Python 侧决定：

- **比率类指标的差异一律用 pp / bp**，不用百分比变化（GS LPLA 规矩 2）。
  `abs(v) < 1` 时用 bp，否则用 pp。
- **反向指标**（逾期率、坏账率等，越低越好）算好之后再决定 `cls`，不要让页面猜。
- **分位对单调序列没有意义**：仓库数、累计资产这类几乎只增不减的序列，分位永远是 100，
  是噪音不是信息。判据：`diff >= 0` 的比例 ≥ 90% 就把该行分位留空（`{'v': ''}`）。
- **4-4-5 零售日历**下净销售额的 m/m 不可当趋势读（5 周月 vs 4 周月），要么留空要么在
  `note` 里写明。

## 3. exhibits

公共字段：

| 字段 | 说明 |
|---|---|
| `n` | Exhibit 编号（汇总表占 1，图从 2 起） |
| `kind` | 见下表 |
| `title` | 图标题。GS 的做法是标题即结论，含当期数字 |
| `fmt` | 数值格式键：`f0` `f1` `f2` `f0c`(千分位) `int` `pct0` `pct1` `pct0z` `pp0` `pp1` `x0` `usd0` `usd1` `usd2` |
| `yfmt` | y 轴刻度格式键；不给则按步长自适应 |
| `label_fmt` | 柱顶/点上数值标签的格式键；不给则退回 `fmt` |
| `ylab` / `ylab2` | 左轴 / 右轴标题 |
| `note` | 图下方 `Note:` 行 |
| `src_extra` | 追加在 `Source:` 行后的补充说明 |
| `x` | `'long'` 时用 `xlabels_long`，否则用 `xlabels` |
| `xlabels` | 该图自己的 x 轴标签（覆盖上面两者） |
| `xstep` / `xrot` | x 轴标签的抽稀步长 / 旋转角度 |
| `full` | `True` 走通栏（127 根柱塞进半栏每根不到 3px，必须通栏） |
| `height` | 覆盖默认高度 |
| `legend` | 单序列图的图例文字 |
| `annot` | 图内注解 |
| `zero_line` | 强制画零线 |

**基线规范字段**（这几条是硬约定，见 charts.js 头部注释）：

| 字段 | 语义 |
|---|---|
| `ycap` / `yfloor` | 截轴上/下界。**截轴不删点**：超界的柱画到 cap 并加断口符号，超界的点钳位画红色空心圈，真值一律竖排标出 |
| `cap_note` | 截轴时图顶的斜体小字，如 `axis capped — outliers shown in red` |
| `break_at` | 结构性断点的 x 索引（int 或 int[]），红色虚线画在该期柱的**左缘**，语义是「从这一期起与左侧不可比」 |
| `break_label` | 断点竖排标签；给一个字符串时所有断点共用 |
| `bar_marks` | 需要画成斜纹的柱的索引（口径调整月、53 周月等） |
| `mark_note` | 斜纹柱在 tooltip 里追加的说明 |

### 已有 kind（COST / IBKR 在用，不要改动其行为）

| kind | 数据字段 | 用途 |
|---|---|---|
| `gs_bar` | `values[]`, `legend`, `avg12`, `yoy_txt`, `mom_txt`, `yoy?`, `stacks?` | 柱 + 12月均线 + 每柱数值 + YoY/MoM 气泡。对应 `gsx.lvl_bar`。**给了可选的 `yoy{values,color,yfmt,name}` 就改画次轴 y/y 折线、不画均线**（deck 的原样）。**给了可选的 `stacks[{name,color,values}]` 就把柱按业务分色堆叠，总额仍取 `values`**（轴、柱顶数值、均线、次轴 y/y、表格视图全部照总额走；各段之和 ≡ `values` 是硬校验，配色不得与 `yoy.color` 撞）。两者见 `engine_kinds.md` §8 |
| `gs_line` | `values[]`, `ovals_at_bottom?` | 平滑线 + 每点数值。对应 `gsx.chg_line` |
| `gs_line_avg` | `values[]`, `avg12`, `avg_label` | 平滑线 + 均线 + 右端均值标注 |
| `lines` | `series[{name,color,values,dash?}]`, `markers?`, `zero_base?`, `end_label?` | N 条线。对应 `gsx.long_line` / `gsx.indexed_lines`。**长历史图（对应 `long_line` 的）应当给 `zero_base: true`（deck 是零基线，不给等于隐性截轴）与 `end_label: true`（deck 会标最新一点）**，见 `engine_kinds.md` §8 |
| `lines_endlabels` | 同上 | 多条平滑线，仅两端标数值。对应 `gsx.multi_line` |
| `bar_line` | `bar{color,values,yfmt}`, `line{color,values,yfmt}` | 柱 + 线（同一轴） |
| `bar_line_dual` | 同上 + `ylab2` | 柱（左轴）+ 线（右轴）。对应 `gsx.rev_bar_yoy` |
| `stacked_dual` | `stacks[{name,color,values}]`, `line{...}` | 堆叠柱 + 右轴占比线。对应 `gsx.stack_share` |
| `diverging_bars` | `values[]` | 正负分色柱 |
| `bars_labeled` | `values[]`, `annot?` | 柱 + 每柱数值 + 注解 |

颜色用色名字符串（`NAVY` `BLUE` `MBLUE` `GRAY` `GREEN` `GOLD` `RED`），不要写十六进制 ——
这套配色过了色盲安全校验，另起新色会破坏它。

### 新增 kind

见 `engine_kinds.md`（由图表引擎那一侧维护）：
`heat_matrix` `year_lines` `qtr_bar` `seasonality` `bridge_bar` `grouped_bars` `range_band`。

## 4. table（末尾核对表）

```python
'table': {
  'n': 20, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
  'idx': '月份',                       # 首列表头，默认「月份」
  'cols': [['ADV 千张', 'adv'], ['交易日', 'days']],
  'rows': [{'xl': 'Jul-26', 'adv': '30,100', 'days': '22'}, ...],
}
```

`rows` 里的值同样是**已格式化的字符串**（或 `None` → 渲染成 `—`）。这张表的作用是让人
拿它和公司披露逐条核对，所以**保持官方原始单位，不做任何换算**。

## 5. 每个生成器都要遵守的几条

1. **推导值必须标 Implied。** 标题带 *Implied* 的图不是公司披露值，假设写进 `note`。
2. **口径断点必须画出来**，不能靠图注文字提一句就算数（`break_at` + `break_label`）。
3. **不可比的相邻期不能画成连续序列**：缺口不要用直线连，宁可断开。
4. **窗口选择**：近期图固定 13 个月（够算 y/y 首末对比与 prior-12mo 均值）；
   长历史图用全序列并标 `full: True`。
5. **失败要响**：解析结果缺列、月份对不上，抛异常让 `monthly_run.py` 记 FAIL，
   **绝不静默写 NaN 上线**。

   这条不靠自觉：写文件一律走 `build/payload_guard.py` 的 `write_dash(path, payload, ticker)`，
   它在写出**之前**递归扫 payload，发现 NaN / Infinity（含已被 f-string 格式化成
   `$nanbn` `nan%` 的展示串）就报出具体路径（`exhibits[7].values[3]` + 该图编号标题）
   并 exit 1，旧的 `data/*.js` 原地不动。新增生成器**不要**自己写 `json.dump` ——
   `json.dump` 默认 `allow_nan=True`，写出的裸 `NaN` 是非法 JSON 但合法 JS，
   浏览器照渲染，退出码还是 0。
   `null` 不在拦截范围：缺月、未满季作废的 y/y、Cboe 滞后一月的 RPC、HKEX 月中才披露的
   new_listings 都是合法留空，一律走 `L()/LN()` 出 `null`。

## 6. 同比口径（2026-08 全站审计后定；实现在 `build/yoy.py`）

同比原先在 15+ 个生成器里各实现了一遍（本文件开头那句「`yoy_line` 在 cme.py、
cboe.py、hkex.py 里各实现了一遍」说的就是它）。副本的代价不是重复代码，是**同一个
判断要做 15 次，而漏掉一次不报错**。所以口径从今天起只有一份实现和一条契约。

审计实测（28 页 511 图，其中 223 图画的是单月同比，逐序列复算、样本对齐后）：
单月同比的逐月标准差是 12 个月滚动同比的 **2.08 倍**（中位）；225 条可比序列里
**147 条（65%）**至少有一个月两种口径**符号相反**；相邻月跳变中位 **30pp vs 4.8pp**。
最刺眼的一处是 `cme` Ex2 说 Jun-26 是 **+19.1%**、同一页 Ex8 说 2026Q2 是 **−1.2%** ——
同一批合约、同一张页、符号相反，而读者没有任何线索知道该信哪张。

### 6.1 六条硬约定

1. **流量序列默认用 12 个月滚动合计的同比。** 成交量、成交额、募资额、净新增资产 ——
   走 `yoy.ttm_yoy(s, yoy.FLOW)`。默认就是默认：不需要在图上为它辩护。
   代价（转折点晚半年才显形、窗口左端 24 个月没有线）写进图注即可。

2. **要用单月同比，必须在标题里写明**（`单月` 或 `single-month`），
   **并在图注说明为什么这里该用单月**。理由不能是「看着更灵敏」——
   要么命题本身就是「一个月之内会怎样」（`cme` Ex3 讲交易日数如何在一个月内把
   成交量的方向读反，改成滚动口径这张图会自己消失），要么这条序列的滚动口径
   根本不存在（见第 4、5 条）。理由请用 `yoy.describe(yoy.caliber_diff(s, kind, win))`
   生成 —— 它拿**这条序列自己**实测，不引别家的例子。

3. **同一张页里若同时存在两种口径，必须在页尾「口径与方法说明」里逐处点名**，
   写成「Exhibit 3、Exhibit 18 与汇总表的 y/y 列：单月同比」这种可核对的形式
   （`cme` / `hkex` 已经是这个写法，照抄）。点名的是**偏离默认的那一侧**——
   默认口径不必逐张点名，否则一页 20 张滚动图就要念 20 遍。

4. **存量序列不许做滚动合计。** OI、AUM、市值、账户数、余额、在外名义量：
   把 12 个月末的快照加起来不是任何东西 —— 既不是「一年的量」（存量不累积），
   也不是「平均水平」（没除以 12）。`yoy.ttm()` 对 `kind=STOCK` 直接抛 `CaliberError`，
   不会静默给一个错数。存量的合法口径有两个：
   - **点对点同比** `yoy.mom_yoy(s, yoy.STOCK)` —— 默认。它比流量的单月同比稳得多
     （比的是两个时点的存量，不含日历效应）。**噪声大用轴范围解决**
     （`ycap` / `yfloor`），不要换口径。
   - 要平滑就用 **12 个月滚动均值的同比** `yoy.ttm_mean_yoy(s, yoy.STOCK)`。
     注意：它与滚动合计的同比**算术上是同一个数**（Σ12/Σ12′ ≡ 均值比，除数约掉；
     实测 `hkex` 市值两者差 2.3e-14）。分成两个函数不是为了数，是为了**说法**：
     对存量说「12 个月合计」是一句关于自己算术的假话，说「去年一整年的平均市值 vs
     前年一整年的平均市值」才指代一个真实存在、可以核对的量。图上印哪个词，
     决定读者按什么去理解，所以词必须对。

5. **比率序列的同比一律走百分点差**（`yoy.mom_yoy(s, yoy.RATIO)`），
   与 §2「比率类指标的差异一律用 pp / bp」同一条规矩。RPC 从 0.24 到 0.25 是 **+1bp**，
   不是「+4.2%」。比率不许做滚动合计也不许做滚动均值 —— 要「一年的平均费率」
   得用**量加权**（Σ收入 ÷ Σ量），那要两条序列，不是换个函数能解决的。

6. **近零基数的序列不画同比，画水平值。** 判据：基期 |b| < 本序列 |值| 中位数 × 0.15
   的月份记为近零基数月；这种月份在窗口内占比 ≥ 1/12（平均每年一个月）→ 别画同比。
   `yoy.near_zero_base(s, win=...)` 返回 `flag`，`yoy.recommend()` 会直接给出
   `verdict='level'`。这类序列换口径救不了 —— 滚动合计确实能把 `db1` Ex28 的
   EURIBOR OI 从跳 40,609pp 压下来，但压完剩下的仍然是分母的故事。
   两个阈值的推导（65,544 个真实点、507 条序列的分桶实测）写在
   `yoy.near_zero_base` 的 docstring 里，`python3 build/yoy.py` 会当场重跑。

### 6.2 豁免

以下图型**不适用**「流量默认滚动」，因为逐格波动就是题眼，抹平了就没图了：

| 图型 | 为什么豁免 |
|---|---|
| `heat_matrix` | 每一格就是一个月的读数，平滑掉整张图的信息就没了 |
| `seasonality` | 全部命题是「几月高几月低」，滚动窗口正好把季节性抹平 |
| `qtr_bar` / `bridge_bar` / `range_band` | 横轴不是月，滚动 12 个月无从对齐 |
| 汇总表的 `m/m` / `y/y` 两列 | 那是运营核对表不是趋势判断，读者拿它逐条对公司披露 |

豁免的是「必须用滚动」，**不豁免第 3 条**：一页里既有豁免图又有默认图，
口径说明照样要点名。

### 6.3 几条实现细则（踩过的坑，别再踩一遍）

- **同比在切窗口之前算完，再切窗。** 切完再算，窗口最前 12 期永远没有同比。
- **比较两种口径时样本必须先对齐。** 滚动同比比单月同比少 12 个月历史，不对齐就把
  样本效应混进标准差里读成口径效应（实测 `schw` Core NNA 不对齐是 4.48x、
  对齐后 4.77x）。`yoy.caliber_diff()` 已经先取交集再比，别自己写。
- **日均序列不要乘回交易日。** 本仓的规范单位是日均，滚动合计 = 12 个日均值相加；
  同比是比值，分子分母同权，交易日在比值里直接约掉。乘回去只多引进一条序列的误差，
  而那正是你想抹掉的噪声（实测 `cme`：滚动口径下两种做法最大差 1.65pp，
  单月口径下差 21.1pp）。何况跨家加权物理上做不到 —— 49 个 `series/*.csv` 里只有
  13 个带交易日列，`cboe.csv` 一个都没有，横截面页只要有一家缺就断了。
- **整条同比都算不出来时不要给次轴。** 引擎只看 `ex.yoy` 在不在就判 dual，
  值全是 null 时量程退化成 [0, 1]，右边印出一列假刻度而金线一个点都没画。
  走 `single.yoy_rhs()`，它在这种情况下返回 `None`。

### 6.4 自动判据

`python3 tools/check_yoy_caliber.py` 扫 `data/*.js`，对每一张含同比的图判上面四条：
🔴 未声明口径的单月同比且与滚动口径符号相反；🔴 存量序列的同比被称作「滚动合计」；
🟡 同页混用口径而口径说明没点名；🟡 单月同比没写进标题。有 🔴 退出码非 0。

它**不看文字判口径** —— 文字声明是被检查的对象，不能同时当证据。判法是把
`series/*.csv` 每一列按两种口径各算一遍，拿数值去比对图上那条线，命中哪种就是哪种；
派生量（ADV × 交易日、多列相加、FX 换算过的）匹配不上任何原始列，一律判「未确定」
**只计数不报错**。宁可漏报，不制造噪声。

`--selftest` 对着四个已知错例跑一遍，确认规则还会响 —— 「今天没报错」与「规则坏了」
在输出上长得一模一样，只有这样才能分开。

**目前是独立脚本，还没接进 `build/payload_guard.py`**（接进去的建议改法写在该文件
末尾的 `HOW_TO_WIRE_IN`）。接的方向是让生成器把口径写成结构化字段
（`ex['caliber'] = 'ttm' | 'mom'`），payload_guard 侧只做零依赖的结构检查，
回源复算那一半留在本脚本里当离线校验 —— 自述字段能被改坏，回源复算不能。
