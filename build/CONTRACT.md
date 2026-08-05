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
| `source_date` | | 官方发布日，显示在抬头右侧 |
| `stale_source` | | `True` 时抬头打红标「官网下载失败，本次沿用本地缓存」 |
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
| `gs_bar` | `values[]`, `legend`, `avg12`, `yoy_txt`, `mom_txt` | 柱 + 12月均线 + 每柱数值 + YoY/MoM 气泡。对应 `gsx.lvl_bar` |
| `gs_line` | `values[]`, `ovals_at_bottom?` | 平滑线 + 每点数值。对应 `gsx.chg_line` |
| `gs_line_avg` | `values[]`, `avg12`, `avg_label` | 平滑线 + 均线 + 右端均值标注 |
| `lines` | `series[{name,color,values,dash?}]`, `markers?` | N 条线。对应 `gsx.long_line` / `gsx.indexed_lines` |
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
