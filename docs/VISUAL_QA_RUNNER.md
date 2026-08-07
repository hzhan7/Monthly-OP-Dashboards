# 整站视觉 QA 跑批器 —— `tools/visual_qa.py`

把「只有渲染出来才看得见」的缺陷变成**可无人值守复跑**的机器判据：柱子画到画布外、
坐标轴画反、断点线画两遍、2.5 步长被印成整数、45° 类别标签压住 Note 正文、末点标签叠字。
这些 `build/verify_pages.py` 一条都抓不到 —— 它只校验 payload 结构，不渲染。

本文件配套 `docs/VISUAL_QA.md`（2026-08-06 那一轮**人工**验收的记录与结论）。
那一轮留下的三个检查器 `docs/verify/qa/qa_geom.html` / `qa_geom_one.html` / `qa_ticks.html`
是本工具的前身，它们的思路（同源 iframe + `getBoundingClientRect`）被沿用，
四个已知短板被补掉（见 §7）。**本工具只读渲染，不改仓里任何文件。**

---

## 1. 怎么跑

```bash
# 全站（当前 29 页 × 2 视口 = 58 轮，约 40 秒）
python3 tools/visual_qa.py --all

# 单页
python3 tools/visual_qa.py --page tmx
python3 tools/visual_qa.py --page tmx --page enx --viewports 1280

# 首页用 --page index
python3 tools/visual_qa.py --page index
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--all` | — | 跑 `data/roster.js` 里的全部页 + 首页 |
| `--page X` | — | 只跑指定页，可重复 |
| `--out DIR` | `/tmp/visual_qa` | 输出目录，**每次跑之前整个重建**（可重复跑、不留旧结果） |
| `--viewports` | `1280,768` | 逗号分隔的视口宽度 |
| `--jobs` | `4` | 并发 Chrome 数 |
| `--no-shots` | 关 | 不出截图（CI 里省时间用） |
| `--timeout` | `120` | 单轮 Chrome 超时秒数 |

产出：

- `report.json` —— 机器可读，`pages → 每轮 → defects`，外加一份按严重度排序的扁平 `defects` 数组；
  `meta.thresholds` 里带着这次跑用的全部阈值。
- `report.md` —— 人读，按严重度分段，每条给「页 + 图号 + 图标题 + 缺陷 + 实测像素 + 页内 y 坐标」。
  **页内 y** 是该元素在整页文档里的绝对纵坐标，配合整页截图可以直接跳到出事的位置。
- `shots/<page>@<视口>.png` —— 只给有 🔴 的页出整页截图（同一页在多个视口都红时截桌面那一版）。

**退出码**：有 🔴 → `1`；只有 🟡/🔵 或干净 → `0`；跑不起来（没 Chrome、页名不存在）→ `3`。
可以直接挂进 cron / CI。

### 依赖与副作用

- 只用 Python 标准库 + 本机 `/Applications/Google Chrome.app`。**不装任何包。**
- 临时 http server 绑 `127.0.0.1` + 随机端口，跑完（含异常与 Ctrl-C 路径）在 `finally` 里关掉。
- 每轮 Chrome 用**独立的临时 user-data-dir**，跑完删掉，不碰用户自己的 Chrome 配置；
  用户正开着 Chrome 也不冲突。
- 仓里一个文件都不写。给被测页注入的错误捕获脚本是**由 QA server 在内存里插进 HTTP 响应**的，
  磁盘上的 `index.html` 原样不动。

---

## 2. 它是怎么工作的

```
tools/visual_qa.py
 ├─ 临时 http server（127.0.0.1:随机端口，仓根）
 │    ├─ 静态服务：/tmx/ /assets/charts.js /data/tmx.js …
 │    ├─ 对任何 .html 响应，在 <head> 后**内存注入**错误捕获 shim
 │    │    （window.onerror / unhandledrejection / console.error 全收进 window.__qaErr）
 │    ├─ /__qa__/probe.html      ← 内存里的测量页，不落盘
 │    └─ POST /__qa__/result?id= ← 测量结果回传口
 └─ headless Chrome × N（并发）
      └─ probe.html
           └─ <iframe src="/tmx/">   ← 同源，所以能读 contentDocument
                ├─ 等 .plot .host svg 数量连续 3 次不变（≤80×60ms）
                ├─ 等 document.fonts.ready + 两帧 rAF（另挂 250ms 兜底）
                ├─ 逐 <svg> 量几何 → JSON
                └─ XHR POST 回 /__qa__/result
```

三个实现选择需要交代，因为它们都是踩过坑之后定的：

**(a) 为什么用 iframe 而不是直接开被测页。** 要在页面里跑测量脚本就得注入 JS，
headless Chrome 没有命令行注入入口。iframe 同源、`contentDocument` 直接可读，
`getBoundingClientRect` / `getBBox` / `getScreenCTM` 全部照常工作。
上一轮 `qa_geom.html` 用的就是这条路，这里沿用。

**(b) 为什么结果是 POST 回传，不用 `--dump-dom`。**
真正的原因是 **`requestAnimationFrame` 在虚拟时间下不回调**，不是 `--dump-dom` 本身有问题。
实测三种组合（Chrome 151，被测页 `/tmx/`）：

| 命令 | `<pre id="out">` |
|---|---|
| `--dump-dom`，等待链结尾是 `rAF(rAF(measure))` + `--virtual-time-budget=45000` | `PENDING`（测量根本没跑） |
| `--dump-dom` + `--virtual-time-budget=45000`，等待链改成纯 `setTimeout` | `DONE 959` ✅ |
| `--dump-dom`，不给 `--virtual-time-budget` | `PENDING`（load 一到就吐，符合预期） |

所以 `docs/VISUAL_QA.md` §4 那三个 html 检查器**现在仍然能跑**（它们等待用的是纯 `setTimeout`），
这条路没断。改成 POST 回传是为了两件事：

1. **能用真实的 rAF 和 `document.fonts.ready` 等版面稳定。** 虚拟时间下 rAF 不回调，
   等于没法等一帧真正画完就去量 —— 而量版面恰恰需要一个已经落定的帧。
   POST 回传不依赖虚拟时间，rAF / `fonts.ready` 正常工作（另挂 250ms 兜底，谁先到算谁）。
2. 去掉「Chrome 什么时候吐 DOM」这个隐性变量。上面第一行那种失败是**静默**的 ——
   吐出来的是一份结构完整、只是 `<pre>` 还没填的 DOM，不报错、不超时，
   只有去看 `<pre>` 里到底是什么才发现。这种坑不适合放在无人值守的跑批里。

**(c) 为什么不用 `subprocess.run` 等 Chrome 自己退出。**
Chrome 会拉起 `GoogleUpdater` 子进程，它继承了 stdout 且长期不退出 —— 等 EOF 会永远挂住
（实测 90 秒仍未返回，而页面其实 2 秒就跑完了）。所以一律「自己判完成 + `killpg` 整个进程组」。
这也是脚本跑完不留后台进程的原因。

---

## 3. 每条判据与阈值推导

阈值全部集中在 `tools/visual_qa.py` 顶部的 `THRESH` 字典里，并原样写进 `report.json` 的
`meta.thresholds`，事后能复核这份报告是按什么标准出的。

### 3.1 本底噪声是多少（几乎所有像素阈值的共同基线）

`charts.js:140-148` 的 `txt()` **默认给每个字加 2.4px 的白色描边**（`paint-order: stroke fill`），
`getBoundingClientRect()` 把描边算进去 ⇒ 单边 **+1.2px**。
图元里最粗的 `stroke-width` 是 1.8 ⇒ 单边 **+0.9px**。再加抗锯齿约 0.5px。
**本底 ≈ 2.6px。** 所有「越界」类阈值取 **6px**，留 2.3 倍余量。
实测：全站 29 页里没有一张干净图的越界超过 4px，6px 以上的全是真缺陷。

### 3.2 判据表

| # | 判据 | 怎么量 | 起报 | 🟡 | 🔴 |
|---|---|---|---|---|---|
| 1 | `SVG_OVERFLOW` 图元画到画布外 | 每个 `path/rect/circle/line/polyline/polygon/text/image` 的 client rect 对 `<svg>` client rect 逐边求差，取四边各自最坏的一个 | 6px | 6–24px | ≥24px **或** ≥画布高 10% |
| 2 | `TEXT_OUT_OF_CARD` 文字越出卡片 | `<text>` client rect 对 `section.card` client rect 逐边求差 | 6px | 6–15px | ≥15px |
| 2b | `TEXT_ON_PROSE` 图上文字压住卡片正文 | `<text>` 墨迹四边形 ∩ 同卡片的 `p.src` / `p.note` / `.legend` / `h3` / `.toggle` 的矩形 | 8px² | <60px² | ≥60px² 或占小者 ≥55% |
| 3 | `TEXT_OVERLAP` 文字互相压字 | 同一 `<svg>` 内两两 `<text>` 的**墨迹四边形**求交面积 | 8px² | 12–60px² | ≥60px² 或占小者 ≥55% |
| 3b | `DUPLICATE_TEXT` 同文字画两遍 | 内容相同且墨迹框中心距 <1.5px | — | — | 全部 🔴 |
| 3c | `DUPLICATE_ELEMENT` 虚线重复绘制 | 同 `d`/坐标/描边/dasharray 的**虚线**出现 ≥2 次 | — | 全部 🟡 | — |
| 4a | `AXIS_DUP_LABEL` 轴刻度重复标签 | 同一根轴上相邻两格标签**字面相同** | — | — | 全部 🔴 |
| 4b | `AXIS_INVERTED` / `AXIS_NOT_MONOTONIC` 轴方向 | 按屏幕 y 升序排，刻度值必须严格递减 | — | 部分逆序 🟡 | 全逆序 🔴 |
| 4c | `AXIS_UNEVEN` 刻度不等距 | 相邻两格的「像素-数值比」`k=Δ值/Δ像素` 必须恒定 | 5% | 5–10% | ≥10% |
| 4d | `ZERO_BASE_BROKEN` 柱图零基线 | 单轴柱图数据全非负 ⇒ 最小刻度必须是 0；有正有负 ⇒ 0 必须落在量程内 | — | 全部 🟡 | — |
| 5 | `HSCROLL` 页面横向滚动 | `documentElement.scrollWidth > clientWidth + 1`，再回溯最宽的越界元素 | 1px | — | 全部 🔴 |
| 6 | `CONSOLE_ERROR` 渲染期 JS 报错 | 注入 shim 收 `error` / `unhandledrejection` / `console.error` | — | — | 全部 🔴 |
| — | `NON_FINITE_ATTR` 图元属性含 NaN | 扫 `x/y/x1/x2/y1/y2/width/height/cx/cy/d/points` | — | — | 全部 🔴 |
| — | `SVG_COUNT_MISMATCH` 图整段没渲染出来 | payload 的 exhibit 数 vs DOM 里 `.plot .host svg` 数 | — | — | 全部 🔴 |

### 3.3 推导细节

**#1 的 🔴 线 24px。** 半栏图高 228–360px。24px ≈ 两行 12px 正文的高度，
到这个量级必然压到卡片下方的 Note 或隔壁栏。另加一条**相对**判据「≥画布高 10%」，
是冲着 `miax` Ex13 那种「柱画出画布 3.8 个图高、盖住下面两个 exhibit」的页面级破相去的 ——
合成复现实测报 796.8px（2.6 个图高），全负值柱图报 1825.5px。

**#2 的 🔴 线 15px。** 卡片之间横向 gap 30px、纵向 26px（`style.css:60`），
越界 15px（半个 gap）以内还碰不到邻居，超过就开始进别人的地盘。

**#3 的墨迹框（不是 em 框）。** `getBBox()` 给的是 em 框，Arial 的 ascent 0.905em /
descent 0.212em ⇒ 框高 1.117em，而数字与大写字母只占基线上 0.716em。
所以墨迹框 = em 框自顶部内缩 `(0.905−0.716)/1.117 = 16.9%`、自底部内缩 `0.212/1.117 = 19.0%`，
剩 **64%**。不做这个内缩，上下相邻两行标签的 em 框天然就贴着，会大批量假阳。

**#3 的面积阈值。** 9px 字的墨迹高 ≈ `0.716 × 9 = 6.4px`。
`docs/VISUAL_QA.md` §3.F 里人工确认过的**最轻**一处真压字（`db1` Ex14 的
`80000000` × `76,941,267`）横向重叠 2.6px ⇒ 面积 ≈ **17px²**。
起报定 8px²（≈1.2px 横向重叠，肉眼可见的「字碰字」下限，比最轻的真缺陷还低一倍，不会漏）；
🔴 定 60px²（≈9.4px 横向重叠 ≈ 1.5 个字宽被完全盖住，必然读错数）。

**#3 用有向包围盒（OBB）而不是轴对齐包围盒（AABB）。** 45° 旋转的类别标签，
它的 AABB 面积是字形本身的好几倍，相邻两个标签的 AABB 必然大面积相交 —— 上一轮
`qa_geom.html` 因此**直接跳过所有带 rotate 的文字**，等于放弃了「45° 标签压字」这一整类。
本工具用 `getBBox()`（元素自身坐标系，不含自身 transform）+ `getScreenCTM()`（含自身 transform）
把四个角点变换到视口坐标，得到真正的有向四边形，再用 Sutherland–Hodgman 凸多边形裁剪求交面积。
**自检**：每个 `<text>` 都会拿 OBB 反算出的 AABB 中心和 `getBoundingClientRect()` 中心比一次，
差 >2px 就计一次 `geom_selfcheck_fail` 并写进 `meta` —— 一旦变换算错，报告会自己说不可信。
全站 29 页 × 2 视口实测 `geom_selfcheck_fail = 0`。

**#4c 为什么判「像素-数值比」而不是「数值差相等」。** 这是本工具相对上一轮最大的改进。
`charts.js` 末尾的 `dropClashingTicks` 会**故意**删掉与末点读数打架的那一格刻度
（注释：读数是真实数据、刻度只是标尺，冲突时让刻度让位）。
判「数值差相等」的话，被删一格的轴就报「不等距」—— `docs/VISUAL_QA.md` §4 记录的
**71 条告警全部是这一类，无一真错**。
改判 `k = Δ值 / Δ像素`：让位漏掉一格时 Δ值与 Δ像素**同倍**放大，`k` 不变，不报；
而 2.5 步长被印成 3/2 时 Δ像素恒定、Δ值在 3 和 2 之间跳，`k` 偏离 33%。
实测分离度：干净的轴偏离 **0.0%**，坏的轴偏离 **33.3%–100%**，中间是空的。
5% 的起报线和 10% 的 🔴 线都落在这个空档里，两头都有 3 倍以上余量。

**#4c 的 🔴 线为什么是 10%。** 偏离 ≥10% 只可能是标签被四舍五入到了**错误的数值**
（2.5 步长印成 3/2、0.25 步长印成 0.3/0.2，都是 33%）—— 也就是轴上印的数字本身是错的，
属于正确性缺陷不是版式瑕疵，所以判 🔴、卡住 CI。

**轴刻度是怎么认出来的。** `charts.js` 里 `font-size=9` 只出现在左右轴刻度这两处
（724 行 `anchor='end'`、749 行 `anchor='start'`），但 `txt()` 的**默认**字号也是 9，
所以还要再过两道：① 排除带 `transform` 的（轴刻度不旋转）；
② 按 `x` 属性聚类、取**最靠右**的那一列且至少 3 格 ——
`lines_endlabels` 的左端标签（`anchor='end'`，x = `M.l−10−tickW`）在左轴刻度列的**左**边，
末点读数（`anchor='start'`，x = `Xc(last)+5`）在右轴刻度列的**左**边，都被这一条排掉。
只要有一格标签解析不出数字，整根轴放弃检查（宁可漏报）。
逐图人工核对过 `tmx` 全部 26 张：认出来的左轴全是柱的量纲、右轴全是 y/y 百分比，没有一张认错。

---

## 4. 定级与退出码

| 级别 | 含义 | 处置 |
|---|---|---|
| 🔴 | **数字是错的**（轴上印错值、图整段没渲染出来、JS 报错）或**版面已破**（越界 ≥24px、横向滚动） | 退出码 1，卡住 CI |
| 🟡 | 可读性受损但不影响正确性（标签互相压、虚线重复绘制、隐性截轴） | 退出码 0，进人工队列 |
| 🔵 | 刚过起报线，多半可以放着 | 只留在报告里 |

---

## 5. 已知误报，以及为了不误报付出的代价

**规矩：宁可漏报也不要制造噪声。** 下面每一条都是实跑之后**主动调掉**的，代价写在旁边。

| 判据 | 遇到的误报 | 怎么改的 | 代价（会漏掉什么） |
|---|---|---|---|
| `ZERO_BASE_BROKEN` | `tmx` 26 张里 5 张命中，**全部**是误报：`charts.js` 的 `alignZero()` 为了把左右两轴的零点拉到同一屏幕高度，会主动把左轴下界压到 0 以下（右轴 y/y 有负值时必然发生），于是 `gs_bar` 的左轴合法地从 −0.25 起 | **双轴图整个豁免**这条判据 | 双轴柱图上**真正的**隐性截轴抓不到，只剩单轴柱图这一半覆盖 |
| `DUPLICATE_ELEMENT` | `exchanges12` Ex4 命中 7 条，**全部**是误报：`range_band` 在 `lo === hi` 的类别上把上下界横杠画在同一个 y，两条实线天然重合，是合法的退化区间 | 只看**虚线**（`stroke-dasharray` 非空）。断点线是 `'4 3'`、12 个月均线也是虚线，这些标注类图元重合一定是 bug | **实线**的重复绘制抓不到。同一类缺陷靠 `DUPLICATE_TEXT`（断点标签跟着重复，🔴）兜住 |
| `AXIS_UNEVEN` | 上一轮 `qa_ticks.html` 全站 71 条告警**无一真错**，全是 `dropClashingTicks` 让位 | 改判「像素-数值比恒定」（§3.3） | 如果某天引擎改成**非线性轴**（log），这条判据会全线假阳，需要按 kind 豁免 |
| `TEXT_OVERLAP` | 45° 旋转标签用 AABB 判必然大面积互相相交 | 改用 OBB + 墨迹框内缩（§3.3） | 无。上一轮是直接跳过旋转文字，覆盖面反而更小 |

**还没被判成误报、但读报告时要知道的两件事**：

1. **同一个根因会同时触发 #1 和 #2。** `exchanges12` Ex6 那个超长的热力图行标签，
   既是「越出画布左缘 28.1px」也是「越出卡片 28.1px」，报告里是两行。
   这是刻意的 —— 任务书把它们列成两条判据，两个口径的量法确实不同（画布 vs 卡片）。
2. **本轮 40 条 🟡 `TEXT_OVERLAP` 有 38 条是同一个根因**：竖排的红色断点标签
   （`charts.js:1310`，从 `M.t+3` 往下铺）横穿柱顶的数值标签。
   已用整页截图人工确认是**真的**（`lpla` Ex9：`Commonwealth` 这几个竖排红字
   直接盖住 `$49.5` 的后半截）。不是噪声，但它只有一个根因，修一处清一片。

---

## 6. 能力边界：哪些抓得到，哪些抓不到

### 6.1 抓得到（合成缺陷页逐条回归验证过）

验证方式：在仓外造一份只有 `assets` 软链 + 一份人为改坏的 payload 的合成站，逐条复现
`docs/VISUAL_QA.md` 记录过的历史缺陷，看工具报不报、报多少像素。

| 历史缺陷（出处） | 工具报什么 | 实测 |
|---|---|---|
| 柱子画到画布外、盖住下方正文（`miax` Ex13，§2.A） | `SVG_OVERFLOW` 🔴 | **796.8px**（2.6 个图高） |
| 全负值柱图把坐标轴画反（`asx` Ex20，§2.A） | `SVG_OVERFLOW` 🔴 + `TEXT_OUT_OF_CARD` 🔴 | **1825.5px** / 1780.5px |
| 断点线被重复画 2–4 次（`enx`，§2.E） | `DUPLICATE_TEXT` 🔴 + `DUPLICATE_ELEMENT` 🟡 | 标签重合 376.9px²；3 条重合虚线 |
| 刻度被四舍五入成重复标签（`sgx` Ex24 那种 −3%/−3%/−3%） | `AXIS_DUP_LABEL` 🔴 + `AXIS_UNEVEN` 🔴 | `4%│4%│3%│3%│2%│2%│1%│1%│0%`，偏离 100% |
| 2.5 步长被印成整数 0/3/5/8/10/13/15（`ndaq` Ex10，§2.B） | `AXIS_UNEVEN` 🔴 | 偏离 33.3%（**在真站上抓到 7 张，见 §8**） |
| 45° 类别标签伸出画布压在 Note 上（`Deutsche Börse`，§6.1） | `SVG_OVERFLOW` 🔴 + `TEXT_ON_PROSE` 🟡 | **41.5px** / 44.2px² |
| 9 位数标签压住轴刻度（`db1` Ex14，§3.F） | `TEXT_OVERLAP` 🟡 | 20.2px² |
| `avg12` 缺失导致 `Y(undefined)=NaN`（§2.C 第一版修法踩的坑） | `NON_FINITE_ATTR` 🔴 | 每图 2 处 |
| exhibit 整段没渲染出来（§4 的一行脚本） | `SVG_COUNT_MISMATCH` 🔴 | payload 数 vs DOM `<svg>` 数 |
| 折线末端标签互相压字 | `TEXT_OVERLAP` | 本轮真站 0 命中（`spreadY` 在工作，与 §4 结论一致） |

### 6.2 抓不到（诚实清单）

| 抓不到什么 | 为什么 |
|---|---|
| **深色主题** | 这套站根本没有深色。probe 会主动探测（扫 `document.styleSheets` 找 `prefers-color-scheme` 规则、看根节点 `data-theme`），探不到就跳过深色轮并把原因写进报告 —— 而不是用 `--force-dark-mode` 造一份假的深色渲染充数。`style.css` 顶上写着「刻意只做浅色」并钉死 `color-scheme: light`。将来真加了深色，这一轮会**自动**开始跑（`data-theme` 走 DOM 切换，`prefers-color-scheme` 走 `--blink-settings=preferredColorScheme=0`）。⚠ 本机 headless Chrome 默认跟随 macOS 的系统深色设置（实测默认就是 `prefers-color-scheme: dark`），所以「浅色」这一轮是**显式**钉住的，否则跑的其实是深色媒体查询 |
| **断点虚线横穿数值标签** | 只做了「文字 × 文字」和「文字 × HTML 正文」，没做「线 × 文字」。`lpla` Ex9 的 `$45.8` 就是被红色断点虚线拦腰划过的，工具没报。没加是为了控噪声：断点线是全图高的竖线，必然与附近若干标签相交，加上就是每页几十条。**要加的话得先想清楚怎么只报「压在字上」而不是「从字旁边过」** |
| **颜色 / 对比度 / 色盲安全** | 完全没做。图例配色、`heat_matrix` 色标是否被量级差占满（§3 的 G 类），都要看像素值，本工具不读像素 |
| **数值对不对** | 不校验数据。柱子高度是否等于 payload、汇总表与核对表是否一致，归 `build/verify_pages.py` 与 §4 的幂等检查 |
| **语义类缺陷** | 「图注写着有一条均线但图上没有」「断点标到了不相干的图上」「同一根轴上量级差 554 倍」—— 这些要理解图在讲什么，机器判不了。这类清单仍要靠 `docs/VISUAL_QA.md` §4 末尾那段纯读 payload 的脚本 |
| **`AXIS_INVERTED` 在本引擎上实际打不着** | 全负值柱图确实会让 `y0 > y1`，但此时 `ticks(0, −4.88, 9)` 退化到不足 3 格，轴刻度列根本认不出来，判据被跳过。同一张图由 `SVG_OVERFLOW` 以 **1825px** 报出来（🔴，不会漏），只是类型名不是「轴画反」。判据留着是为了引擎将来改动后仍有覆盖 |
| **只量到 `.plot .host > svg`** | 卡片里的表格视图（点「表格」按钮切过去的那一份）、核对表、首页 hub 卡片都不量。`.tblwrap` 自带 `overflow-x:auto`，它的内容溢出**不会**冒泡成 body 的横向滚动，所以 #5 天然不会误报到它头上 —— 反过来说，核对表被切断也不会被本工具发现 |
| **动效 / 交互** | tooltip、图表↔表格切换按钮都不点。只量首次渲染后的静态版面 |

---

## 7. 相对上一轮（`docs/verify/qa/*.html`）补掉的四个短板

| 上一轮 | 现在 |
|---|---|
| `qa_geom.html` 的 OVERLAP **直接跳过所有带 rotate 的文字** | OBB + 墨迹框，旋转文字照量（45° 标签、竖排断点标签都在覆盖内） |
| `qa_ticks.html` 判「数值差相等」，全站 71 条告警**无一真错** | 判「像素-数值比恒定」，本轮 0 误报、7 条真错 |
| 没有控制台错误、没有横向滚动、没有严重度、没有退出码 | 都有，🔴 时退出码 1 |
| 硬编码 12 个页名（漏掉了后来加的页） | 从 `data/roster.js` 自动发现（这次就自动带上了新加的 `exchanges-products`），页名写死会漏 |

那三个 html 检查器**现在仍然能跑**（2026-08-07 实测 `qa_geom.html` 在 Chrome 151 上输出 `CLEAN`）。
它报 CLEAN 而本工具报出 `exchanges12` Ex6 的 28.1px 越界，正是上表第 4 行的差别：
`exchanges12` 不在它那份写死的 12 页清单里。同理，本轮 40 条 🟡 压字它也一条都报不出来 ——
那些全是**竖排**断点标签压字，它按第 1 行的规则直接跳过了旋转文字。
那三个文件建议留作历史记录，日常验收走本工具。

---

## 8. 本轮快照（2026-08-07 10:51，Chrome 151.0.7922.108）

29 页 × 2 视口 = 58 轮，全部成功，40 秒，`geom_selfcheck_fail = 0`，退出码 1。

> ⚠ 这一轮有 8 个 agent 正在同时改 `build/*`，下面这份清单是**当时那一刻**的快照。
> 会变到什么程度：10:40 那一次跑还报了 `hkex` Ex19，11 分钟后的 10:51 这次它已经没了
> （那张图被另一支线改过，页高从 8,393px 变成 8,693px）。清单会变，**工具本身是稳定的**。

**🔴 8 条（去掉视口重复后；报告里按「页×视口」展开是 16 行）**

| 页 | 图 | 类型 | 实测 |
|---|---|---|---|
| `axp` | Ex8 | `AXIS_UNEVEN` | 右轴 `+1.3pp │ +1.0pp │ +0.5pp │ +0.3pp │ +0.0pp │ -0.3pp │ -0.5pp │ -0.8pp │ -1.0pp` —— 真步长 0.25pp 被 `pp1` 印成 0.3/0.8，偏离 33.3% |
| `axp` | Ex10 | `AXIS_UNEVEN` | 左轴 `2.5% │ 2.3% │ 2.0% │ 1.8% │ 1.5% │ 1.3% │ 1.0% │ 0.8% │ 0.5%` —— 真步长 0.25% |
| `cme` | Ex12 | `AXIS_UNEVEN` | 右轴 `20% │ 18% │ 15% │ 13% │ 10% │ 8% │ 5% │ 3% │ 0%` —— 真步长 2.5%，**与当年 `ndaq` Ex10 那条一模一样** |
| `exchanges12` | Ex8 | `AXIS_UNEVEN` | 左轴 `13 │ 10 │ 8 │ 5 │ 3 │ 0 │ -3 │ -5` —— 真步长 2.5 |
| `hkex` | Ex6 | `AXIS_UNEVEN` | 右轴 `20% │ 18% │ 15% │ 13% │ 10% │ 8% │ 5% │ 3% │ 0% │ -3%` —— 真步长 2.5% |
| `hood` | Ex14 | `AXIS_UNEVEN` | 左轴 `2.0 │ 1.8 │ 1.5 │ 1.3 │ 1.0 │ 0.8 │ 0.5 │ 0.3 │ 0.0` —— 真步长 0.25 |
| `exchanges12` | Ex6 | `SVG_OVERFLOW` | 热力图行标签 `ICE / NYSE·能源（仅 Brent 原油） 等 2 腿（已定基）` 越出画布**左缘 28.1px**（`row_lab_w: 168` 装不下） |
| `exchanges12` | Ex6 | `TEXT_OUT_OF_CARD` | 同一根因，越出卡片 **28.1px** |

六条 `AXIS_UNEVEN` 全部落在 **`axisfmt.py` 没覆盖到的生成器**上：
`docs/VISUAL_QA.md` §5 记录的那一轮修法只接了 `single.py` 与四张 `exchanges_*.py`，
`axp.py` / `cme.py` / `hkex.py` / `hood.py` / `exchanges12.py` 都没接。
修法现成：给这几个生成器也调一次 `axisfmt.fix_all()`。

**🟡 40 条 + 🔵 2 条**：`enx` 14、`lpla` 3、`tmx` 3、`asx` 1、`spgi` 1（按「页×图×文字对」去重后 22 处），
**全部**是竖排断点标签横穿数值标签这一个根因（§5 第 2 条），已用整页截图人工确认为真。

**其余全清**：0 条 JS 报错、0 页横向滚动、0 处 `NON_FINITE_ATTR`、
0 处 `AXIS_DUP_LABEL`、0 处 `DUPLICATE_TEXT` / `DUPLICATE_ELEMENT`、0 处末点标签叠字、
29 页的 payload exhibit 数与 DOM `<svg>` 数**全部一一对上**（没有 exhibit 整段丢失）。

截图落在 `/tmp/visual_qa/shots/`：`axp@1280.png` `cme@1280.png` `exchanges12@1280.png`
`hkex@1280.png` `hood@1280.png`（整页，1280 宽 × 内容全高）。
配合报告里的「页内 y」列可以直接定位到出事的那张图。
