/* ==========================================================================
   GS exhibit 渲染器 —— 零依赖 SVG，目标是与 skill 生成的 PDF 逐张一致。

   图型 ←→ build_report.py 的绘图函数：
     bar_line         柱 + 线（同一轴）                COST Ex1/5/6/7/8
     lines            N 条线（可带点标记 / 注解）        COST Ex2/9/10/11
     bar_line_dual    柱（左轴）+ 线（右轴）             COST Ex3
     diverging_bars   正负分色柱                        COST Ex4
     bars_labeled     柱 + 每柱数值 + 注解               COST Ex12
     gs_bar           柱 + 12月均线 + 每柱数值 + YoY/MoM 气泡  IBKR Ex2/4/6/10/12
     gs_line          平滑线 + 每点数值（可选底部气泡）   IBKR Ex3/5/11/13
     gs_line_avg      平滑线 + 12月均线 + 右端均值标注    IBKR Ex7
     lines_endlabels  多条平滑线 + 仅两端标数值          IBKR Ex9
     stacked_dual     堆叠柱 + 右轴线（段内标数值）       IBKR Ex8

   12 家看板新增的图型 ←→ build/gsx.py 的同名函数（PDF 版与网页版必须同型）：
     heat_matrix      行=年 列=月 的热力矩阵，格内写数值   gsx.heat_matrix
     year_lines       每年一条线叠在 1-12 月轴上，当年红   gsx.year_lines
     qtr_bar          月度汇总成季度柱 + 右轴 y/y          gsx.qtr_bar
     seasonality      灰=历史同月均值 / 蓝=今年 配对柱     gsx.seasonality
     bridge_bar       正上负下的恒等式桥 + 净额菱形        gsx.bridge_bar
     grouped_bars     同一 x 上两根并排柱 + 右轴误差线     gsx.implied_vs_actual
     range_band       指引区间带状填充 + 实际值菱形        gsx.range_vs_actual
   字段清单见 cache/engine_kinds.md（数据契约）。

   所有数值由 build_data.py（复用 skill 同一份算法）预先算好，本文件只负责画。
   —— 新图型同此：累计值、历史同月均值、季度合计、误差率一律在 Python 侧算完再传。
      唯一的例外是「桥」的净额：给了 ex.net 就用给的，没给才在这里求和（那是恒等式，
      不是口径判断）。

   ex 上与「基线规范」直接对应的可选字段（build_data.py 传入）：
     ycap    number    截轴上界（规矩 7）。超界的柱画到 cap 并加断口符号，超界的点钳位
                       画空心圈，真值一律竖排标出——截轴是为了看清主体，不是删点。
                       注意：双轴图上零点对齐可能把上界重新推高到 ycap 之上，此时就不截了
                       （宁可不截也不能让两轴零点错位）；截轴主要给单轴柱图用。
     yfloor  number    截轴下界，同上。
     cap_note string   截轴时图顶左上角的斜体小字（如 'axis capped — outliers shown in red'）。
     break_at  int|int[]   结构性断点的 x 索引（规矩 6），画在该期柱的左缘，
                           语义是「从这一期起与左侧不可比」。
     break_label string|string[]  断点竖排标签；给一条时所有断点共用。
     bar_marks int[]   需要标成斜纹的柱（如 53 周财年多出一周的月份），与 break_at 配合用。
     mark_note string  bar_marks 命中的期在 tooltip 里追加的说明。
     ylab2   string    右轴标题（双轴图），与左侧 ylab 对称。
   ========================================================================== */
(function () {
  'use strict';
  var SVG = 'http://www.w3.org/2000/svg';

  /* PDF 使用的 GS 风格取色，与 build_report.py 完全一致 */
  var C = {
    NAVY: '#1F3864', BLUE: '#9DC3E6', MBLUE: '#2E75B6',
    GRAY: '#A6A6A6', GREEN: '#548235', RED: '#B23A48',
    /* gsx.py 的第 6 个序列色。原先漏在这里，导致六品种堆叠图（CME）没有第 6 个颜色可用，
       只能把 RED 拿去当数据色 —— 而 RED 在这套语言里是断点与离群值的专用色，
       一根红柱到底是「金属品种」还是「这个点被截轴了」就分不清了。 */
    GOLD: '#BF9000',
    WHITE: '#FFFFFF', GRID: '#E3E3E3', AXIS: '#999999', INK: '#333333',
  };
  /* 认得的色名 → 十六进制；本来就是 CSS 颜色（#xxx / rgb() / url(#pat)）的原样放行；
     其余一律退回 NAVY。
     原先是 `C[k] || k`：payload 写了 'GOLD' 这种 C 里没有的名字时，字符串会被原样塞进
     fill 属性，浏览器当作无效值 → 渲染成黑色。黑色不在这套配色里，但它看起来像是
     「故意的深色」，所以这种错会一路上线而没人看出来。退回 NAVY 至少是本套色。 */
  var col = function (k) {
    if (C[k]) return C[k];
    if (typeof k === 'string' && /^(#|rgb|hsl|url\()/i.test(k)) return k;
    return C.NAVY;
  };
  var BREAK = '#C00000';        // 断点/截轴标注专用红，与 gsx.py 的 RED 同一角色
  var uid = 0;                  // 一页多张图共存，pattern 之类的 id 必须全局唯一

  /* 数值格式 —— 逐个对应 build_report.py 里的 lambda */
  function comma(v, d) {
    var s = Math.abs(v).toFixed(d), p = s.split('.');
    p[0] = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (v < 0 ? '-' : '') + p.join('.');
  }
  var FMT = {
    f1:    function (v) { return v.toFixed(1); },
    f0:    function (v) { return v.toFixed(0); },
    f0c:   function (v) { return comma(v, 0); },
    int:   function (v) { return comma(v, 0); },
    pct0:  function (v) { return v.toFixed(0) + '%'; },
    pct1:  function (v) { return v.toFixed(1) + '%'; },
    pct0z: function (v) { return (Math.abs(v) < 0.5 ? 0 : v).toFixed(0) + '%'; },
    pp0:   function (v) { return (v >= 0 ? '+' : '') + v.toFixed(0) + 'pp'; },
    pp1:   function (v) { return (v >= 0 ? '+' : '') + v.toFixed(1) + 'pp'; },
    x0:    function (v) { return v.toFixed(0) + 'X'; },
    usd0:  function (v) { return '$' + v.toFixed(0); },
    usd1:  function (v) { return '$' + v.toFixed(1); },
    usd2:  function (v) { return '$' + v.toFixed(2); },
    /* 高精度档。缺这几个的时候 fmtOf 会**静默**退回 f1，于是 $0.0719 的合约单价被印成
       $0.1、3 位小数的 RPC 掉到 1 位有效数字 —— 图还是画出来了，只是数字没了意义。
       补齐比让每个生成器各自换单位绕过去更稳妥。 */
    f2:    function (v) { return v.toFixed(2); },
    f3:    function (v) { return v.toFixed(3); },
    pct2:  function (v) { return v.toFixed(2) + '%'; },
    usd3:  function (v) { return '$' + v.toFixed(3); },
    usd4:  function (v) { return '$' + v.toFixed(4); },
  };
  var fmtOf = function (k) { return FMT[k] || FMT.f1; };

  /* 纯数字轴刻度：小数位数随步长自适应，可选千分位。
     IBKR 的 exhibit 在 build_report.py 里没有设置 y 轴格式器（Ex8 例外，显式加了
     千分位），所以轴上只有数字，单位靠轴标题与数据标签表达。此处照此还原。 */
  function plainAxis(step, useComma) {
    var d = Math.max(0, Math.min(4, -Math.floor(Math.log10(Math.abs(step) || 1)))) ;
    if (Math.abs(step - Math.round(step)) < 1e-9) d = 0;
    return function (v) {
      return useComma ? comma(v, d) : (v < 0 ? '-' : '') + Math.abs(v).toFixed(d);
    };
  }

  function el(tag, attrs, parent) {
    var n = document.createElementNS(SVG, tag), k;
    for (k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function txt(parent, x, y, s, o) {
    o = o || {};
    var t = el('text', {
      x: x, y: y, fill: o.fill || C.INK, 'font-size': o.size || 9,
      'text-anchor': o.anchor || 'middle', 'font-weight': o.weight || null,
      'font-style': o.style || null, transform: o.transform || null,
    }, parent);
    t.textContent = s;
    return t;
  }

  function ticks(min, max, count) {
    if (!isFinite(min) || !isFinite(max)) { min = 0; max = 1; }
    if (min === max) { min -= 1; max += 1; }
    var raw = (max - min) / count;
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var cand = [1, 2, 2.5, 5, 10], step = null, i;   // 与 matplotlib MaxNLocator 默认 steps 相同
    for (i = 0; i < cand.length; i++) if (cand[i] * mag >= raw) { step = cand[i] * mag; break; }
    if (!step) step = 10 * mag;
    var lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, out = [], v;
    for (v = lo; v <= hi + step / 2; v += step) out.push(Math.abs(v) < step / 1e6 ? 0 : v);
    return out;
  }

  /* ---- 双轴零点对齐（规矩：柱的基线与线的 0 必须是同一条水平线）----------
     zeroFrac：0 在该轴上的相对高度（0 = 贴画布底，1 = 贴顶）。 */
  function zeroFrac(a0, a1) {
    if (!(a1 > a0) || a0 >= 0) return 0;
    if (a1 <= 0) return 1;
    return -a0 / (a1 - a0);
  }
  /* alignZero：把 [a0,a1] 重排成「0 落在相对高度 f」。只放大不缩小 ——
     新范围写成 [-f·R, (1-f)·R]，要同时罩住原来的上下界，
     故 R = max(a1/(1-f), -a0/f)。两条轴各自这样扩一次，零点自然落在同一高度，
     且没有任何数据点被挤出画布。 */
  function alignZero(a0, a1, f) {
    if (!(f > 1e-9) || f >= 1 - 1e-9) return [a0, a1];
    var R = Math.max(Math.max(a1, 0) / (1 - f), Math.max(-a0, 0) / f);
    return [-f * R, (1 - f) * R];
  }

  /* Catmull-Rom 平滑，端点外推方式与 build_report.py 的 smooth() 相同 */
  function smooth(vals, n) {
    n = n || 24;
    var N = vals.length, X = [-1], Y = [vals[0] - (vals[1] - vals[0])], i, j, t, ox = [], oy = [];
    for (i = 0; i < N; i++) { X.push(i); Y.push(vals[i]); }
    X.push(N); Y.push(vals[N - 1] + (vals[N - 1] - vals[N - 2]));
    function cr(v0, v1, v2, v3, tt) {
      return 0.5 * ((2 * v1) + (-v0 + v2) * tt + (2 * v0 - 5 * v1 + 4 * v2 - v3) * tt * tt +
                    (-v0 + 3 * v1 - 3 * v2 + v3) * tt * tt * tt);
    }
    for (i = 1; i < X.length - 2; i++) {
      for (j = 0; j < n; j++) {
        t = j / n;
        ox.push(cr(X[i - 1], X[i], X[i + 1], X[i + 2], t));
        oy.push(cr(Y[i - 1], Y[i], Y[i + 1], Y[i + 2], t));
      }
    }
    ox.push(X[X.length - 2]); oy.push(Y[Y.length - 2]);
    return { x: ox, y: oy };
  }

  /* 顶部圆角、基线端方角的柱（负值自动翻转） */
  function barPath(x, yBase, yVal, w, r) {
    var top = Math.min(yBase, yVal), h = Math.abs(yVal - yBase);
    if (h < 0.6) return 'M' + x + ' ' + top + 'h' + w;
    var rr = Math.min(r, w / 2, h);
    if (yVal <= yBase) {
      return 'M' + x + ' ' + (top + h) + 'V' + (top + rr) +
             'a' + rr + ' ' + rr + ' 0 0 1 ' + rr + ' ' + (-rr) +
             'h' + (w - 2 * rr) + 'a' + rr + ' ' + rr + ' 0 0 1 ' + rr + ' ' + rr +
             'V' + (top + h) + 'Z';
    }
    return 'M' + x + ' ' + top + 'V' + (top + h - rr) +
           'a' + rr + ' ' + rr + ' 0 0 0 ' + rr + ' ' + rr +
           'h' + (w - 2 * rr) + 'a' + rr + ' ' + rr + ' 0 0 0 ' + rr + ' ' + (-rr) +
           'V' + top + 'Z';
  }

  /* 截轴处的断口符号：两道白色斜线画在柱端，告诉读者这根柱被截过而不是到顶了 */
  function capMark(g, xc, y, w) {
    var hw = Math.min(w, 11) / 2, k, yy;
    for (k = 0; k < 2; k++) {
      yy = y + 2.4 + k * 3.2;
      el('line', { x1: xc - hw, y1: yy + 1.8, x2: xc + hw, y2: yy - 1.8,
        stroke: C.WHITE, 'stroke-width': 1.5 }, g);
    }
  }

  /* PDF 里的白底灰框圆角气泡，可带虚线箭头 */
  function oval(g, x, y, s, arrowTo) {
    var w = Math.max(28, s.length * 6.2 + 12);
    el('rect', { x: x - w / 2, y: y - 8, width: w, height: 17, rx: 5,
      fill: '#fff', stroke: '#555555', 'stroke-width': 0.9 }, g);
    txt(g, x, y + 3.6, s, { size: 10, style: 'italic', fill: '#000' });
    if (arrowTo) {
      el('path', { d: 'M' + (x + w / 2 + 2) + ' ' + y + 'L' + arrowTo[0] + ' ' + arrowTo[1],
        stroke: '#444444', 'stroke-width': 0.9, fill: 'none', 'stroke-dasharray': '3 2',
        'marker-end': 'url(#exArrow)' }, g);
    }
  }

  /* ────────────────────── 新图型共用的小零件 ────────────────────── */
  function isNum(v) { return v != null && isFinite(v); }

  /* qtr_bar 的末季未满时，右轴那条 y/y 一律作废。
     拿 2 个月的累计去比上年完整 3 个月，必然砸出一个 -8% 之类的假坑，而线是连续的、
     没有任何视觉提示说这一点不可比 —— 读者会当成业务塌了。柱子有浅蓝 + 图例提示，
     线没有，所以只能丢。
     在引擎侧丢而不是指望每个 build/<t>.py 传 null：这是口径错误不是排版偏好，
     漏一次就是发布一张误导图。
     范围计算、绘图、表格视图、tooltip **四处都要用它** —— 漏掉任何一处就会出现
     「图上没有但表里有」的不一致，或者右轴被一个不画出来的点撑开。 */
  function lineVals(ex) {
    var v = ex.line && ex.line.values;
    if (!v || ex.kind !== 'qtr_bar') return v;
    if (isNum(ex.partial_months) && +ex.partial_months > 0 &&
        +ex.partial_months < (ex.qtr_months || 3)) {
      v = v.slice();
      v[v.length - 1] = null;
    }
    return v;
  }
  function lastFinite(a) {
    var k;
    for (k = (a || []).length - 1; k >= 0; k--) if (isNum(a[k])) return k;
    return -1;
  }

  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  function rgbOf(h) {
    return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  }
  /* 在两个 C.* 之间线性插值。热力图必须有连续色标，但端点只许取 C.* —— 中间色是
     这两个端点的混合，不算新引入的颜色。 */
  function mix(a, b, t) {
    var A = rgbOf(a), B = rgbOf(b), o = '#', k, v;
    t = t < 0 ? 0 : (t > 1 ? 1 : t);
    for (k = 0; k < 3; k++) {
      v = Math.round(A[k] + (B[k] - A[k]) * t);
      o += (v < 16 ? '0' : '') + v.toString(16);
    }
    return o;
  }
  /* 深底上的字必须翻白，否则 RdGn 两端（RED/GREEN 亮度都只有 0.4 上下）压着深色字看不清。
     gsx 里格子字固定 #111111，那是 matplotlib 的老毛病，网页版不跟。 */
  function inkOn(hex) {
    var r = rgbOf(hex);
    return (0.299 * r[0] + 0.587 * r[1] + 0.114 * r[2]) / 255 > 0.58 ? C.INK : C.WHITE;
  }
  /* numpy.percentile 的线性插值版，用来复刻 gsx.heat_matrix 的 5/95 分位色标 */
  function pctile(sorted, p) {
    if (!sorted.length) return 0;
    var idx = (sorted.length - 1) * p, lo = Math.floor(idx), hi = Math.ceil(idx);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }
  function heatScale(ex) {
    var m = ex.matrix || [], fin = [], i, j, row;
    for (i = 0; i < m.length; i++) {
      row = m[i] || [];
      for (j = 0; j < row.length; j++) if (isNum(row[j])) fin.push(+row[j]);
    }
    fin.sort(function (a, b) { return a - b; });
    var lo = fin.length ? pctile(fin, 0.05) : 0;
    var hi = fin.length ? pctile(fin, 0.95) : 1;
    if (!(hi > lo)) { lo = lo - 0.5; hi = hi + 0.5; }     // 全同值：不除零，整片中性色
    var loc = ex.reverse ? C.GREEN : C.RED, hic = ex.reverse ? C.RED : C.GREEN;
    return { lo: lo, hi: hi, loc: loc, hic: hic,
      at: function (v) {
        var t = (v - lo) / (hi - lo);
        return t < 0.5 ? mix(loc, C.WHITE, t * 2) : mix(C.WHITE, hic, t * 2 - 1);
      } };
  }

  /* year_lines 的配色：旧年份由浅到深，当年红色加粗（同 gsx 的 cmap 阶梯）。
     draw / seriesRows / legendHTML 三处必须拿到同一组颜色，所以抽出来。 */
  function yearColors(ex) {
    /* 阶梯对应 gsx 的 [LGRAY, #C9D6E4, BLUE, MBLUE, NAVY]：两个浅端由 C.* 兑白得到。
       最浅一档不能直接用 C.GRID —— 那是网格线的颜色，数据线跟网格同色等于没画。 */
    var ramp = [mix(C.GRAY, C.WHITE, 0.5), mix(C.BLUE, C.WHITE, 0.45),
                C.BLUE, C.MBLUE, C.NAVY], ser = ex.series || [];
    var nS = ser.length, hl = ex.highlight != null ? +ex.highlight : nS - 1, out = [], k, t;
    for (k = 0; k < nS; k++) {
      if (ser[k].color) { out.push(col(ser[k].color)); continue; }
      if (k === hl) { out.push(C.RED); continue; }
      t = nS > 2 ? Math.round(k / (nS - 2) * (ramp.length - 1)) : ramp.length - 1;
      out.push(ramp[Math.max(0, Math.min(ramp.length - 1, t))]);
    }
    return out;
  }

  function stackLen(ex) {
    var L = 0, k, st = ex.stacks || [];
    for (k = 0; k < st.length; k++) L = Math.max(L, (st[k].values || []).length);
    return L;
  }
  /* 桥的净额：口径上应由 Python 给（ex.net），没给才在这里按恒等式求和 */
  function bridgeNet(ex, n) {
    if (ex.net && ex.net.values) return ex.net.values;
    var out = [], i, s, t, any, v;
    for (i = 0; i < n; i++) {
      t = 0; any = false;
      for (s = 0; s < ex.stacks.length; s++) {
        v = ex.stacks[s].values[i];
        if (isNum(v)) { t += v; any = true; }
      }
      out.push(any ? t : null);
    }
    return out;
  }

  function diamond(g, x, y, r, fill, stroke, sw) {
    el('path', { d: 'M' + x.toFixed(2) + ' ' + (y - r).toFixed(2) +
      'L' + (x + r).toFixed(2) + ' ' + y.toFixed(2) +
      'L' + x.toFixed(2) + ' ' + (y + r).toFixed(2) +
      'L' + (x - r).toFixed(2) + ' ' + y.toFixed(2) + 'Z',
      fill: fill, stroke: stroke || null, 'stroke-width': sw || null }, g);
  }

  /* 把 tooltip 定位到某个画布 x（与 draw() 里的逻辑一致，heat_matrix 也要用） */
  function placeTip(tip, host, xInSvg, W) {
    var tw = tip.offsetWidth, px = xInSvg / W * host.clientWidth;
    tip.style.left = Math.max(2, Math.min(host.clientWidth - tw - 2, px - tw / 2)) + 'px';
    tip.style.top = '0px';
  }

  /* ───────────── heat_matrix：行=年、列=月的热力矩阵（gsx.heat_matrix）─────────────
     它不吃 band/y 轴那一整套，所以在 draw() 里提前分流，自己排版。
     色标取 5/95 分位：一两个离群月不该把整张表压成一片白。 */
  function drawHeat(host, ex, W) {
    var rows = ex.rows || [], cols = ex.cols || MONTHS, m = ex.matrix || [];
    if (!rows.length || !cols.length) { host.innerHTML = '<p class="note">无数据</p>'; return; }
    var fmt = fmtOf(ex.fmt || 'f1'), i, j, v;
    var M = { t: 3, r: 6, b: 15, l: ex.row_lab_w || 32 };
    var pw = Math.max(60, W - M.l - M.r), cw = pw / cols.length;
    var chh = Math.max(13, Math.min(26, ex.cell_h || 19));
    var ph = rows.length * chh, H = M.t + ph + M.b;
    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img',
      'aria-label': 'Exhibit ' + ex.n + ': ' + ex.title }, host);
    var g = el('g', {}, svg), sc = heatScale(ex);
    var maxLen = 1;
    for (i = 0; i < rows.length; i++)
      for (j = 0; j < cols.length; j++) {
        v = (m[i] || [])[j];
        if (isNum(v)) maxLen = Math.max(maxLen, fmt(+v).length);
      }
    /* 字号按格宽收缩：半栏 12 列时一格只有 ~38px，宁可字小也不能让数字压出格子 */
    var fs = Math.max(4.6, Math.min(9, (cw - 5) / (maxLen * 0.58), chh * 0.52));
    var tip = host.parentElement ? host.parentElement.querySelector('.tip') : null;
    var name = ex.legend || ex.ylab || '数值', pf = precise(fmt);

    for (i = 0; i < rows.length; i++) {
      for (j = 0; j < cols.length; j++) {
        v = (m[i] || [])[j];
        var ok = isNum(v), x = M.l + j * cw, y = M.t + i * chh;
        var fc = ok ? sc.at(+v) : C.GRID;
        var rc = el('rect', { x: x.toFixed(2), y: y.toFixed(2), width: cw.toFixed(2),
          height: chh, fill: fc, stroke: C.WHITE, 'stroke-width': 1.1 }, g);
        if (ok) txt(g, x + cw / 2, y + chh / 2 + fs * 0.35, fmt(+v),
          { size: +fs.toFixed(2), fill: inkOn(fc) });
        if (tip) (function (node, head, val, sw, cx) {
          node.setAttribute('style', 'cursor:crosshair');
          node.addEventListener('mouseenter', function () {
            tip.innerHTML = '<div class="th">' + head + '</div><div class="row"><i style="background:' +
              sw + '"></i><span>' + name + '</span><b>' +
              (val == null ? '—' : pf(val)) + '</b></div>';
            tip.style.opacity = 1;
            placeTip(tip, host, cx, W);
          });
        }(rc, rows[i] + ' · ' + cols[j], ok ? +v : null, fc, x + cw / 2));
      }
      txt(g, M.l - 5, M.t + i * chh + chh / 2 + 3, rows[i], { size: 8, anchor: 'end' });
    }
    var cfs = Math.max(5, Math.min(8, cw / 3.4));
    for (j = 0; j < cols.length; j++)
      txt(g, M.l + (j + 0.5) * cw, M.t + ph + 11, cols[j], { size: +cfs.toFixed(2) });
    if (tip) g.addEventListener('mouseleave', function () { tip.style.opacity = 0; });
  }

  function draw(host, ex, opt) {
    host.innerHTML = '';
    opt = opt || {};
    var W = host.clientWidth || 520, i, s;
    if (ex.kind === 'heat_matrix') { drawHeat(host, ex, W); return; }
    var labels = ex.xlabels || opt.xlabels || [], n = labels.length;
    if (!n) { host.innerHTML = '<p class="note">无数据</p>'; return; }
    var kind = ex.kind;
    /* x 标签角度：COST 月份标签 90°、IBKR 月份标签 45°、COST Ex12 年份水平（同 PDF）。
       year_lines 的 x 是 Jan..Dec 十二格，PDF 里是水平标的，默认跟着走。 */
    var rot = ex.xrot != null ? ex.xrot : (kind === 'year_lines' ? 0 : (n > 20 ? 90 : 45));
    var XB = rot === 90 ? 48 : (rot === 0 ? 22 : 36);
    /* 新图型里 qtr_bar / grouped_bars 的右轴（y/y、误差）是可选的：payload 没给 ex.line
       就退化成单轴柱图，不画空的右刻度。 */
    var dual = kind === 'bar_line_dual' || kind === 'stacked_dual' ||
               ((kind === 'qtr_bar' || kind === 'grouped_bars') && !!(ex.line && ex.line.values));
    var perPointLabels = kind === 'gs_bar' || kind === 'gs_line' || kind === 'gs_line_avg' ||
                         kind === 'stacked_dual' || kind === 'lines_endlabels' ||
                         kind === 'qtr_bar' || kind === 'seasonality' || kind === 'bridge_bar' ||
                         kind === 'grouped_bars' || kind === 'range_band' || kind === 'year_lines';
    var H = (opt.height || (perPointLabels ? 268 : 248)) + XB;
    /* 截轴时真值标注竖排在图顶之上，顶边距要留够一行竖排文字（约 22px）；
       右轴有标题时右边距要在刻度数字之外再让出一列。 */
    var capOn = ex.ycap != null || ex.yfloor != null;
    var M = { t: capOn ? 30 : 14,
              r: dual ? (ex.ylab2 ? 56 : 42)
                      : (kind === 'lines_endlabels' || kind === 'gs_line_avg' ||
                         kind === 'year_lines' ? 42 : 14),
              b: XB, l: ex.ylab ? 56 : 46 };
    var pw = Math.max(60, W - M.l - M.r), ph = Math.max(80, H - M.t - M.b);

    var svg = el('svg', { viewBox: '0 0 ' + W + ' ' + H, role: 'img',
      'aria-label': 'Exhibit ' + ex.n + ': ' + ex.title }, host);
    var defs = el('defs', {}, svg);
    var mk = el('marker', { id: 'exArrow', viewBox: '0 0 10 10', refX: 8, refY: 5,
      markerWidth: 5, markerHeight: 5, orient: 'auto-start-reverse' }, defs);
    el('path', { d: 'M0 1L9 5L0 9z', fill: '#444444' }, mk);

    /* 斜纹填充：给「与相邻柱不可比」的柱用（如 53 周财年多出一周的月份）。
       pattern 里塞的是该图自己的柱色，所以 id 必须一图一个，不能共用。 */
    var markSet = null, hatchId = null;
    if (ex.bar_marks && ex.bar_marks.length) {
      markSet = {};
      for (i = 0; i < ex.bar_marks.length; i++) markSet[ex.bar_marks[i]] = 1;
      hatchId = 'exHatch' + (++uid);
      var pat = el('pattern', { id: hatchId, width: 5, height: 5,
        patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)' }, defs);
      // 底色必须跟本图柱色一致，否则斜纹柱会整根变色、看着像另一个系列。
      // gs_bar 没有 ex.bar 且柱子固定是 BLUE，不能退成 NAVY。
      el('rect', { width: 5, height: 5,
        fill: (ex.bar && ex.bar.color) ? col(ex.bar.color)
                                       : (kind === 'gs_bar' ? C.BLUE : C.NAVY) }, pat);
      el('line', { x1: 0, y1: 0, x2: 0, y2: 5, stroke: C.WHITE, 'stroke-width': 1.8 }, pat);
    }

    var band = pw / n;
    var Xc = function (k) { return M.l + band * (k + 0.5); };

    /* 左轴参与计算的值 */
    var lv = [];
    if (kind === 'bar_line') lv = ex.bar.values.concat(ex.line.values);
    else if (kind === 'bar_line_dual') lv = ex.bar.values.slice();
    else if (kind === 'lines' || kind === 'lines_endlabels' || kind === 'year_lines') {
      for (s = 0; s < ex.series.length; s++) lv = lv.concat(ex.series[s].values);
    } else if (kind === 'seasonality') {
      lv = (ex.base.values || []).concat(ex.actual.values || []);
    } else if (kind === 'grouped_bars') {
      for (s = 0; s < ex.groups.length; s++) lv = lv.concat(ex.groups[s].values);
    } else if (kind === 'range_band') {
      lv = (ex.lo || []).concat(ex.hi || [], ex.actual || []);
      if (isNum(ex.qtd)) lv.push(ex.qtd);
    } else if (kind === 'bridge_bar') {
      /* 桥的纵轴要罩住「正向堆到哪」「负向堆到哪」两条包络，不是单项的最值 */
      var bp_, bn_, bv_;
      for (i = 0; i < n; i++) {
        bp_ = 0; bn_ = 0;
        for (s = 0; s < ex.stacks.length; s++) {
          bv_ = ex.stacks[s].values[i];
          if (!isNum(bv_)) continue;
          if (bv_ >= 0) bp_ += bv_; else bn_ += bv_;
        }
        lv.push(bp_); lv.push(bn_);
      }
      lv = lv.concat(bridgeNet(ex, n));
    } else if (kind === 'stacked_dual') {
      for (i = 0; i < n; i++) {
        var tot = 0;
        for (s = 0; s < ex.stacks.length; s++) tot += ex.stacks[s].values[i] || 0;
        lv.push(tot);
      }
    } else lv = ex.values.slice();

    var clean = lv.filter(function (v) { return v != null && isFinite(v); });
    if (!clean.length) { host.innerHTML = '<p class="note">无数据</p>'; return; }
    var mn = Math.min.apply(null, clean), mx = Math.max.apply(null, clean);
    var avg = ex.avg12, y0, y1, tk;
    var hasBar = kind === 'bar_line' || kind === 'bar_line_dual' || kind === 'diverging_bars' ||
                 kind === 'bars_labeled';

    /* 柱状图的 ylim 与 PDF 一致（0 .. max×倍数），刻度算在 ylim 上而非数据最大值上
       —— matplotlib 的 locator 作用于最终 ylim，算在 max 上会得到两倍密度的刻度。
       各分支只定 y0/y1，刻度统一放到截轴、对零点之后再算。 */
    if (kind === 'gs_bar') { y0 = 0; y1 = mx * 1.22; }
    else if (kind === 'stacked_dual') { y0 = 0; y1 = mx * 1.28; }
    else if (kind === 'bars_labeled') { y0 = 0; y1 = mx * 1.13; }
    /* 以下四个与 gsx.py 同名函数的 set_ylim 一一对应（qtr_bar 的 1.32 是给竖排标签留的） */
    else if (kind === 'qtr_bar') { y0 = Math.min(0, mn * 1.15); y1 = mx * 1.32; }
    else if (kind === 'seasonality') { y0 = Math.min(0, mn * 1.15); y1 = mx * 1.26; }
    else if (kind === 'grouped_bars') { y0 = Math.min(0, mn * 1.15); y1 = mx * 1.22; }
    else if (kind === 'bridge_bar') {
      var bpad = (mx - mn) * 0.16 || 1; y0 = mn - bpad; y1 = mx + bpad;
    } else if (kind === 'range_band') {
      /* gsx 用 min*0.88 / max*1.10 的乘法留白；那在负值上会往零点缩（越界画到画布外），
         所以只在整段非负时照抄，含负值时改成按极差加白。 */
      if (mn >= 0) { y0 = mn * 0.88; y1 = mx * 1.10; }
      else { var rr0 = (mx - mn) || 1; y0 = mn - rr0 * 0.12; y1 = mx + rr0 * 0.10; }
    }
    else if (kind === 'gs_line' || kind === 'gs_line_avg') {
      if (avg != null) { mn = Math.min(mn, avg); mx = Math.max(mx, avg); }
      var rr = (mx - mn) || 1, pd = kind === 'gs_line_avg' ? 0.35 : 0.30;
      y0 = mn - rr * pd; y1 = mx + rr * pd;
    } else if (kind === 'lines_endlabels') {
      var r2 = (mx - mn) || 1; y0 = mn - r2 * 0.20; y1 = mx + r2 * 0.18;
    } else {
      /* COST 的 exhibit 在 PDF 里走 matplotlib 默认 autoscale：数据范围 ±5% 留白，
         再画落在范围内的刻度（不把轴对齐到刻度边界，否则会多出上下各一档）。
         柱状图从 0 起，含 axhline(0) 的线图（Ex9）也要把 0 纳入数据域。 */
      var incZero = hasBar || !!ex.zero_line;
      var dmn = incZero ? Math.min(mn, 0) : mn;
      var dmx = incZero ? Math.max(mx, 0) : mx;
      var rg = (dmx - dmn) || 1;
      /* 有柱的图 y0 不能因为 5% 留白掉到 0 以下：那样柱的基线 Y(0) 会浮在画布底
         上方几像素，而右轴的 0 在底边，图上唯一那条零线就骗人了（实测 Ex3 里
         y/y < 1.59% 的三个正增长月被画到零线下方）。数据本身有负值时照常留白。 */
      y0 = (hasBar && dmn >= 0) ? 0 : dmn - rg * 0.05;
      y1 = dmx + rg * 0.05;
    }

    /* 截轴（规矩 7）：离群值只截轴、不删点，超界的柱/点后面单独标真值。 */
    if (ex.ycap != null) y1 = ex.ycap;
    if (ex.yfloor != null) y0 = ex.yfloor;

    var Y = function (v) { return M.t + ph - ((v - y0) / (y1 - y0)) * ph; };

    /* 右轴范围先算出来，好在画任何东西之前跟左轴对齐零点 */
    var r0 = null, r1 = null, rtk = null, rc = null;
    if (dual) {
      rc = ex.line;
      /* 用 lineVals()：被作废的未满季 y/y 不能参与右轴量程，否则轴被一个根本不画出来的
         点撑开（实测会把 0~15% 的轴拉成 -10%~15%，整条线压扁在上半幅）。 */
      var rv = lineVals(ex).filter(function (v) { return v != null && isFinite(v); });
      if (kind === 'stacked_dual') { rtk = ticks(0, rc.ymax || 60, 6); r0 = 0; r1 = rtk[rtk.length - 1]; }
      else {
        rtk = ticks(Math.min.apply(null, rv.concat([0])), Math.max.apply(null, rv), 9);
        r0 = rtk[0]; r1 = rtk[rtk.length - 1];
      }
      /* 两轴的 0 必须落在同一画布高度：取两者中较高的那个零点比例 f，
         再让两条轴各自向下扩量程去凑（只扩不缩，数据点一个都不会被挤出去）。
         左右都不含负值时 f = 0，走的还是老路径，不影响既有图。 */
      var f = Math.max(zeroFrac(y0, y1), zeroFrac(r0, r1));
      if (f > 1e-9) {
        var la = alignZero(y0, y1, f); y0 = la[0]; y1 = la[1];
        var ra = alignZero(r0, r1, f); r0 = ra[0]; r1 = ra[1];
        rtk = ticks(r0, r1, 9);       // 量程动过，右轴刻度要重算
      }
    }

    tk = ticks(y0, y1, 9);   // 截轴 / 对零点之后才算刻度，否则刻度会跑到 cap 之外
    /* COST 的 exhibit 在 PDF 里显式设了轴格式器（%、$、pp），故用 yfmt；
       IBKR 的没设，轴为纯数字（Ex8 带千分位）。 */
    var tstep = tk.length > 1 ? tk[1] - tk[0] : 1;
    var yfKey = ex.yfmt || (ex.bar && ex.bar.yfmt);          // 双轴图的左轴格式在 bar 上
    var yf = yfKey ? fmtOf(yfKey) : plainAxis(tstep, kind === 'stacked_dual');

    for (i = 0; i < tk.length; i++) {
      if (tk[i] < y0 - 1e-9 || tk[i] > y1 + 1e-9) continue;
      el('line', { x1: M.l, x2: M.l + pw, y1: Y(tk[i]), y2: Y(tk[i]), stroke: C.GRID, 'stroke-width': 1 }, svg);
      txt(svg, M.l - 6, Y(tk[i]) + 3.2, yf(tk[i]), { size: 9, anchor: 'end' });
    }
    if (y0 < -1e-9 && y1 > 1e-9)
      el('line', { x1: M.l, x2: M.l + pw, y1: Y(0), y2: Y(0), stroke: C.AXIS, 'stroke-width': 0.9 }, svg);

    var step = ex.xstep || 1;
    for (i = 0; i < n; i++) {
      if (i % step) continue;
      var xx = Xc(i), yy = M.t + ph + (rot === 0 ? 13 : 9);
      txt(svg, xx, yy, labels[i], { size: 8.2, anchor: rot === 0 ? 'middle' : 'end',
        transform: rot === 0 ? null : 'rotate(' + (-rot) + ' ' + xx + ' ' + yy + ')' });
    }

    /* 右轴刻度（范围与零点对齐在上面已经定好） */
    var Y2 = null;
    if (dual) {
      Y2 = function (v) { return M.t + ph - ((v - r0) / (r1 - r0)) * ph; };
      var rf = fmtOf(rc.yfmt || 'pct0');
      for (i = 0; i < rtk.length; i++) {
        if (rtk[i] < r0 - 1e-9 || rtk[i] > r1 + 1e-9) continue;   // 对齐后量程会窄于刻度序列
        txt(svg, M.l + pw + 6, Y2(rtk[i]) + 3.2, rf(rtk[i]), { size: 9, anchor: 'start' });
      }
      /* 右轴标题：否则「哪条系列读右轴」全靠 legend 里「(RHS)」三个字 */
      if (ex.ylab2) {
        var cy2 = M.t + ph / 2, xr = W - 11;
        txt(svg, xr, cy2, ex.ylab2, { size: 8.4, transform: 'rotate(90 ' + xr + ' ' + cy2 + ')' });
      }
    }

    var g = el('g', {}, svg);
    var BW = function (frac) { return Math.max(1.5, Math.min(band * frac, band - 1.5)); };

    /* 截轴后的真值标注一律竖排：被截的往往是连着几个月（COVID 低基数），
       横排标签在 band 只有几像素宽的图上必然叠成一团。 */
    var capFmt = fmtOf(ex.label_fmt || yfKey || ex.fmt || 'f1');
    /* 被截的点常常挨在一起（同一个月的柱和线都超界、或连着几个月的低基数尖峰），
       竖排字宽约 8px，比 band 还宽，所以要占位排开；只向右挪，仍紧贴各自的柱。 */
    var capSlots = [];
    function capSlot(x) {
      var moved = true, k;
      while (moved) {
        moved = false;
        for (k = 0; k < capSlots.length; k++)
          if (Math.abs(capSlots[k] - x) < 8) { x = capSlots[k] + 8; moved = true; break; }
      }
      capSlots.push(x);
      return x;
    }
    function capLabel(x, over, s) {
      /* over=true 标在图顶之上（M.t 已为此留位），false 标在图内贴底 */
      var yy = over ? M.t - 3 : M.t + ph - 3;
      x = capSlot(x);
      txt(g, x, yy, s, { size: 7.2, fill: BREAK, anchor: 'start',
        transform: 'rotate(-90 ' + x + ' ' + yy + ')' });
    }

    function polyline(vals, color, lw, doSmooth, markers, yfn) {
      yfn = yfn || Y;
      var d = '', pen = false, pts = [], out = [], vs = vals;
      /* 只有左轴参与截轴；超界的点钳到边界画空心圈 + 真值，绝不丢点（规矩 7） */
      if (yfn === Y && capOn) {
        vs = vals.map(function (v, k) {
          if (v == null || !isFinite(v)) return v;
          if (ex.ycap != null && v > y1) { out.push([k, v, y1, true]); return y1; }
          if (ex.yfloor != null && v < y0) { out.push([k, v, y0, false]); return y0; }
          return v;
        });
      }
      if (doSmooth) {
        var sm = smooth(vs);
        for (i = 0; i < sm.x.length; i++)
          d += (i ? 'L' : 'M') + (M.l + band * (sm.x[i] + 0.5)).toFixed(2) + ' ' + yfn(sm.y[i]).toFixed(2);
      } else {
        for (i = 0; i < vs.length; i++) {
          if (vs[i] == null || !isFinite(vs[i])) { pen = false; continue; }
          d += (pen ? 'L' : 'M') + Xc(i).toFixed(2) + ' ' + yfn(vs[i]).toFixed(2);
          pen = true; pts.push([Xc(i), yfn(vs[i])]);
        }
      }
      el('path', { d: d, fill: 'none', stroke: color, 'stroke-width': lw,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round' }, g);
      if (markers) for (i = 0; i < pts.length; i++)
        el('circle', { cx: pts[i][0], cy: pts[i][1], r: 2.1, fill: color }, g);
      for (i = 0; i < out.length; i++) {
        el('circle', { cx: Xc(out[i][0]), cy: yfn(out[i][2]), r: 2.6, fill: C.WHITE,
          stroke: BREAK, 'stroke-width': 1.1 }, g);
        capLabel(Xc(out[i][0]) + 3.4, out[i][3], capFmt(out[i][1]));
      }
    }

    /* ── 新图型共用：截轴不删点的柱与点 ──
       与上面 bar_line 分支里那段内联逻辑同规矩（超界画到边界 + 断口符号 + 真值竖排），
       抽成函数是因为新图型里同一张图要画好几组柱（配对柱、并排柱、区间带）。 */
    function clampY(v) {
      if (ex.ycap != null && v > y1) return y1;
      if (ex.yfloor != null && v < y0) return y0;
      return v;
    }
    function capBar(xl, w, v, color, r) {
      var vp = clampY(v), cut = vp !== v;
      el('path', { d: barPath(xl, Y(0), Y(vp), w, cut ? 0 : (r == null ? 3 : r)), fill: color }, g);
      if (cut) { capMark(g, xl + w / 2, Y(vp), w); capLabel(xl + w / 2 + 3.4, v > vp, capFmt(v)); }
      return cut;
    }
    /* 被截的「点」（菱形/圆点）一律换成空心红圈 + 真值，同 polyline 里的规矩 */
    function capPoint(x, v) {
      var vp = clampY(v), cut = vp !== v;
      if (cut) {
        el('circle', { cx: x.toFixed(2), cy: Y(vp).toFixed(2), r: 2.9, fill: C.WHITE,
          stroke: BREAK, 'stroke-width': 1.1 }, g);
        capLabel(x + 3.4, v > vp, capFmt(v));
      }
      return cut;
    }
    /* 竖排数值标签（qtr_bar 用）：柱很高时把标签压回画布内，不许越过 viewBox 顶 */
    function vLabel(x, yTop, s, o) {
      var need = s.length * (o.size || 8) * 0.62;
      var yy = Math.max(yTop, need + 2);
      txt(g, x, yy, s, { size: o.size || 8, anchor: 'start', fill: o.fill || C.INK,
        transform: 'rotate(-90 ' + x.toFixed(2) + ' ' + yy.toFixed(2) + ')' });
    }

    if (kind === 'bar_line' || kind === 'diverging_bars' || kind === 'bars_labeled' || kind === 'bar_line_dual') {
      var vals = (kind === 'bar_line' || kind === 'bar_line_dual') ? ex.bar.values : ex.values;
      var w = BW(0.75);
      for (i = 0; i < n; i++) {
        var v = vals[i];
        if (v == null || !isFinite(v)) continue;
        var cc = kind === 'diverging_bars' ? (v >= 0 ? C.NAVY : C.RED)
               : col((kind === 'bar_line' || kind === 'bar_line_dual') ? ex.bar.color : 'NAVY');
        if (markSet && markSet[i]) cc = 'url(#' + hatchId + ')';
        /* 超出截轴范围的柱画到边界，柱端加断口符号，真值竖排标在图外 */
        var vp = v, ov = false;
        if (ex.ycap != null && v > y1) { vp = y1; ov = true; }
        else if (ex.yfloor != null && v < y0) { vp = y0; ov = false; }
        var cut = vp !== v;
        el('path', { d: barPath(Xc(i) - w / 2, Y(0), Y(vp), w, cut ? 0 : 3), fill: cc }, g);
        if (cut) { capMark(g, Xc(i), Y(vp), w); capLabel(Xc(i) + 3.4, ov, capFmt(v)); }
      }
      if (kind === 'bar_line') polyline(ex.line.values, col(ex.line.color), 1.6, false, false);
      if (kind === 'bar_line_dual') polyline(ex.line.values, col(ex.line.color), 1.6, false, false, Y2);
      if (kind === 'bars_labeled') {
        var lf = fmtOf(ex.label_fmt || 'f1');
        for (i = 0; i < n; i++) {
          if (vals[i] == null) continue;
          /* 柱被截过时数值标签跟着柱端走，否则会跑到画布外 */
          var yl = ex.ycap != null ? Math.min(vals[i], y1) : vals[i];
          if (yl !== vals[i]) continue;             // 真值已由 capLabel 竖排标出，别重复
          txt(g, Xc(i), Y(yl) - 5, lf(vals[i]), { size: 8.5 });
        }
      }
    } else if (kind === 'lines') {
      for (s = 0; s < ex.series.length; s++)
        polyline(ex.series[s].values, col(ex.series[s].color), 1.6, false, !!ex.markers);
    } else if (kind === 'gs_bar') {
      var wg = BW(0.62), fb = fmtOf(ex.fmt);
      for (i = 0; i < n; i++) {
        /* 原来这里是直接 barPath(Y(values[i]))，没走截轴：设了 ycap 的话柱和数值标签
           会一起画到画布外几百像素（IBKR 现有 payload 没设过 ycap，所以一直没暴露）。
           改走 capBar 后，没设 ycap 时输出与从前逐字节相同。 */
        if (!isNum(ex.values[i])) continue;
        var cutg2 = capBar(Xc(i) - wg / 2, wg, ex.values[i],
          (markSet && markSet[i]) ? 'url(#' + hatchId + ')' : C.BLUE);
        if (!cutg2) txt(g, Xc(i), Y(ex.values[i]) - 4.5, fb(ex.values[i]), { size: 8 });
      }
      el('line', { x1: M.l, x2: M.l + pw, y1: Y(avg), y2: Y(avg), stroke: C.NAVY,
        'stroke-width': 1.4, 'stroke-dasharray': '6 4' }, g);
      if (ex.yoy_txt) oval(g, Xc(0) + band * 0.25, Y(y1 * 0.93), ex.yoy_txt);
      if (ex.mom_txt) {
        var last = ex.values[n - 1];
        /* 气泡与箭头按**窗口末端**定位，不能写死 Xc(9)/Xc(11)。
           原先是照 PDF 的 13 个月窗口硬编的坐标，窗口一改成 25 根柱，箭头就指到第 12 根，
           而那根柱看着完全正常 —— 读者会把它当成最新月。n=13 时 n-4/n-2 正好还原原值。 */
        oval(g, Xc(n - 4) + band * 0.2, Y(Math.min(last * 1.13, y1 * 0.94)), ex.mom_txt,
          [Xc(n - 2) + band * 0.3, Y(last * 1.06)]);   // PDF: arrow_to=(11.8, vals[-1]*1.06)
      }
    } else if (kind === 'gs_line' || kind === 'gs_line_avg') {
      var fv = fmtOf(ex.fmt);
      var dmn = Math.min.apply(null, ex.values), dmx = Math.max.apply(null, ex.values);
      var rngv = (dmx - dmn) || 1;
      if (kind === 'gs_line_avg') {
        el('line', { x1: M.l, x2: M.l + pw, y1: Y(avg), y2: Y(avg), stroke: C.BLUE,
          'stroke-width': 1.4, 'stroke-dasharray': '6 4' }, g);
        txt(g, M.l + pw + 4, Y(avg) + 3.2, fv(avg), { size: 8.5, anchor: 'start', fill: C.MBLUE });
      }
      polyline(ex.values, C.NAVY, 1.8, true, false);
      var off = (kind === 'gs_line_avg' ? 0.05 * 1.7 : 0.06 * 1.6) * rngv;
      for (i = 0; i < n; i++) {
        var vv = ex.values[i];
        var up = !(i > 0 && i < n - 1 && vv < (ex.values[i - 1] + ex.values[i + 1]) / 2);
        txt(g, Xc(i), Y(vv + (up ? off : -off)) + (up ? 0 : 7), fv(vv), { size: 8, fill: C.NAVY });
      }
      if (ex.ovals_at_bottom) {
        var by = Y(dmn - rngv * 0.12);
        if (ex.yoy_txt) oval(g, Xc(1), by, ex.yoy_txt, [Xc(2) + band * 0.6, by]);
        // 同上：按窗口末端定位，不写死 13 个月窗口的下标
        if (ex.mom_txt) oval(g, Xc(n - 4) + band * 0.1, by, ex.mom_txt, [Xc(n - 2) + band * 0.5, by]);
      }
    } else if (kind === 'lines_endlabels') {
      var fe = fmtOf(ex.fmt);
      for (s = 0; s < ex.series.length; s++) {
        var sr = ex.series[s], sc = col(sr.color);
        polyline(sr.values, sc, 1.8, true, false);
        txt(g, Xc(0) - 7, Y(sr.values[0]) + 3.2, fe(sr.values[0]), { size: 8, anchor: 'end', fill: sc });
        txt(g, Xc(n - 1) + 7, Y(sr.values[n - 1]) + 3.2, fe(sr.values[n - 1]),
          { size: 8, anchor: 'start', fill: sc });
      }
    } else if (kind === 'stacked_dual') {
      var ws = BW(0.62), base = [];
      for (i = 0; i < n; i++) base.push(0);
      for (s = 0; s < ex.stacks.length; s++) {
        var st = ex.stacks[s];
        for (i = 0; i < n; i++) {
          var lo = base[i], hi = base[i] + st.values[i];
          var hgt = Math.max(0, Y(lo) - Y(hi) - (s ? 1.5 : 0));
          el('rect', { x: Xc(i) - ws / 2, y: Y(hi), width: ws, height: hgt, fill: col(st.color) }, g);
          if (st.label && hgt > 8)
            txt(g, Xc(i), (Y(lo) + Y(hi)) / 2 + 2.4, comma(st.values[i], 0),
              { size: 6.6, fill: col(st.label_color) });
          base[i] = hi;
        }
      }
      polyline(ex.line.values, col(ex.line.color), 1.8, true, false, Y2);
      for (i = 0; i < n; i++)
        txt(g, Xc(i), Y2(ex.line.values[i]) - 5, ex.line.values[i].toFixed(1) + '%',
          { size: 6.6, fill: col(ex.line.color) });

    /* ══════════════ 以下七个图型对应 build/gsx.py 的同名函数 ══════════════ */

    /* qtr_bar ← gsx.qtr_bar：季度柱 + 右轴 y/y；未满季用浅蓝并在图例里写明「几 of 3」。
       数值标签竖排在柱顶（gsx 是 rotation=90），所以纵轴上界给 1.32 倍。
       右轴的金色（gsx GOLD）不在本文件的 C.* 里，默认退到 GREEN，payload 可指定。 */
    } else if (kind === 'qtr_bar') {
      var wq = BW(0.70), fq = fmtOf(ex.label_fmt || ex.fmt || 'f0c');
      var partialQ = isNum(ex.partial_months) && +ex.partial_months > 0 &&
                     +ex.partial_months < (ex.qtr_months || 3);
      for (i = 0; i < n; i++) {
        var vq = ex.values[i];
        if (!isNum(vq)) continue;
        var cq = (partialQ && i === n - 1) ? C.BLUE : C.NAVY;
        if (markSet && markSet[i]) cq = 'url(#' + hatchId + ')';
        var cutq = capBar(Xc(i) - wq / 2, wq, vq, cq);
        if (cutq || ex.bar_labels === false) continue;
        if (vq >= 0) vLabel(Xc(i), Y(vq) - 4, fq(vq), { size: 7.4 });
        else txt(g, Xc(i), Y(vq) + 9, fq(vq), { size: 7.4 });   // 负柱不竖排，会插进柱体里
      }
      if (Y2) {
        var lcq = col((ex.line.color) || 'GREEN');
        /* 未满季的那根柱有浅蓝 + 图例提示，但**右轴的 y/y 必须一起丢掉**：
           拿 2 个月的累计去比上年完整 3 个月，必然砸出一个 -8% 之类的假坑，
           而线是连续的、没有任何视觉提示说这一点不可比 —— 读者会当成业务塌了。
           这里在引擎侧直接丢，不指望每个 build/<t>.py 都记得传 null：
           这是口径错误，不是排版偏好，漏一次就是发布一张误导图。 */
        var lvq = lineVals(ex);
        if (r0 < -1e-9 && r1 > 1e-9)
          el('line', { x1: M.l, x2: M.l + pw, y1: Y2(0), y2: Y2(0), stroke: lcq,
            'stroke-width': 0.7, 'stroke-dasharray': '2 2' }, g);
        polyline(lvq, lcq, 1.6, false, true, Y2);
        var jq = lastFinite(lvq);
        if (jq >= 0)
          txt(g, Xc(jq) + 5, Y2(lvq[jq]) + 3.2,
            fmtOf(ex.line.yfmt || 'pct0')(lvq[jq]),
            { size: 8, anchor: 'start', weight: 700, fill: lcq });
      }

    /* seasonality ← gsx.seasonality：灰柱 = 过去 N 年同月均值、蓝柱 = 本期实际。
       两根柱各占 band 的 0.40，在 band 中心相接（同 matplotlib 的 ±0.20 偏移）。 */
    } else if (kind === 'seasonality') {
      var wb = BW(0.40), fsz = fmtOf(ex.label_fmt || ex.fmt || 'f1');
      var cb = col((ex.base && ex.base.color) || 'GRAY');
      var ca = col((ex.actual && ex.actual.color) || 'MBLUE');
      var bvals = (ex.base && ex.base.values) || [], avals = (ex.actual && ex.actual.values) || [];
      for (i = 0; i < n; i++) {
        if (isNum(bvals[i])) capBar(Xc(i) - wb, wb, bvals[i], cb);
        if (!isNum(avals[i])) continue;
        var cuta = capBar(Xc(i), wb, avals[i], ca);
        if (!cuta && ex.bar_labels !== false)
          txt(g, Xc(i) + wb / 2, Y(avals[i]) + (avals[i] < 0 ? 9 : -4), fsz(avals[i]),
            { size: 7.6, fill: ca });
      }

    /* bridge_bar ← gsx.bridge_bar：正的往上堆、负的往下堆，菱形标净额。
       堆叠段不参与截轴（截一段堆叠柱等于把恒等式画错），只有净额点会被截。 */
    } else if (kind === 'bridge_bar') {
      var wbr = BW(0.70), posB = [], negB = [];
      for (i = 0; i < n; i++) { posB.push(0); negB.push(0); }
      for (s = 0; s < ex.stacks.length; s++) {
        var stb = ex.stacks[s], cbb = col(stb.color);
        for (i = 0; i < n; i++) {
          var vb = stb.values[i];
          if (!isNum(vb) || vb === 0) continue;
          var bb0 = vb >= 0 ? posB[i] : negB[i], bb1 = bb0 + vb;
          if (vb >= 0) posB[i] = bb1; else negB[i] = bb1;
          /* 段也要吃截轴：不然一根 −46 的市值变动段会径直画到 x 轴标签底下去。
             这里只把「画到哪」钳住，真值下面按列标出，堆叠关系一个不删。 */
          var yA = Y(clampY(bb0)), yB = Y(clampY(bb1));
          if (Math.abs(yA - yB) < 0.05) continue;      // 整段在界外，不画 0 高的柱
          el('rect', { x: (Xc(i) - wbr / 2).toFixed(2), y: Math.min(yA, yB).toFixed(2),
            width: wbr.toFixed(2), height: Math.abs(yA - yB).toFixed(2), fill: cbb }, g);
        }
      }
      var netv = bridgeNet(ex, n);
      for (i = 0; i < n; i++) {
        /* 包络被截：柱端画断口 + 真值。净额与包络重合时（全负/全正列）不重复标 */
        if (ex.ycap != null && posB[i] > y1) {
          capMark(g, Xc(i), Y(y1), wbr);
          if (!(isNum(netv[i]) && Math.abs(netv[i] - posB[i]) < 1e-9))
            capLabel(Xc(i) + 3.4, true, capFmt(posB[i]));
        }
        if (ex.yfloor != null && negB[i] < y0) {
          capMark(g, Xc(i), Y(y0) - 8, wbr);
          if (!(isNum(netv[i]) && Math.abs(netv[i] - negB[i]) < 1e-9))
            capLabel(Xc(i) + 3.4, false, capFmt(negB[i]));
        }
        if (!isNum(netv[i]) || capPoint(Xc(i), netv[i])) continue;
        diamond(g, Xc(i), Y(netv[i]), 3.2, col(ex.net_color || 'INK'));
      }

    /* grouped_bars ← gsx.implied_vs_actual：同一 x 上两根并排柱 + 右轴误差线。
       误差是这张图存在的理由（桥的假设可不可信），所以末点误差要标出来。 */
    } else if (kind === 'grouped_bars') {
      var gps = ex.groups || [], ng = Math.max(1, gps.length);
      var wgb = BW(0.74 / ng), xg0 = -(ng * wgb) / 2;
      var gdef = ['BLUE', 'NAVY', 'MBLUE', 'GRAY'];
      var fgb = fmtOf(ex.label_fmt || ex.fmt || 'f0c');
      for (s = 0; s < gps.length; s++) {
        var cg = col(gps[s].color || gdef[s % gdef.length]);
        for (i = 0; i < n; i++) {
          var vg = gps[s].values[i];
          if (!isNum(vg)) continue;
          var cutg = capBar(Xc(i) + xg0 + s * wgb, wgb, vg, cg);
          if (!cutg && ex.bar_labels)
            txt(g, Xc(i) + xg0 + (s + 0.5) * wgb, Y(vg) + (vg < 0 ? 8.5 : -4), fgb(vg),
              { size: 6.6, fill: cg });
        }
      }
      if (Y2) {
        var lce = col((ex.line.color) || 'RED');
        if (r0 < -1e-9 && r1 > 1e-9)
          el('line', { x1: M.l, x2: M.l + pw, y1: Y2(0), y2: Y2(0), stroke: lce,
            'stroke-width': 0.7, 'stroke-dasharray': '2 2' }, g);
        polyline(ex.line.values, lce, 1.4, false, true, Y2);
        var je = lastFinite(ex.line.values);
        if (je >= 0)
          txt(g, Xc(je) + 5, Y2(ex.line.values[je]) + 3.2,
            fmtOf(ex.line.yfmt || 'pct1')(ex.line.values[je]),
            { size: 8, anchor: 'start', weight: 700, fill: lce });
      }

    /* range_band ← gsx.range_vs_actual：指引区间画成带、实际值打菱形。
       未完成期的累计值（qtd）用空心红菱形，标签压在点下方，跟实际值分得开。 */
    } else if (kind === 'range_band') {
      var wrb = BW(0.74), frb = fmtOf(ex.label_fmt || ex.fmt || 'f1');
      var loA = ex.lo || [], hiA = ex.hi || [], acA = ex.actual || [];
      for (i = 0; i < n; i++) {
        if (isNum(loA[i]) && isNum(hiA[i])) {
          var t0 = Math.min(loA[i], hiA[i]), t1 = Math.max(loA[i], hiA[i]);
          var c0 = clampY(t0), c1 = clampY(t1), yT = Y(c1), yB = Y(c0);
          el('rect', { x: (Xc(i) - wrb / 2).toFixed(2), y: yT.toFixed(2),
            width: wrb.toFixed(2), height: Math.max(0.9, yB - yT).toFixed(2), fill: C.BLUE }, g);
          var hwr = wrb * 0.46;
          el('line', { x1: (Xc(i) - hwr).toFixed(2), x2: (Xc(i) + hwr).toFixed(2),
            y1: yT.toFixed(2), y2: yT.toFixed(2), stroke: C.MBLUE, 'stroke-width': 0.9 }, g);
          el('line', { x1: (Xc(i) - hwr).toFixed(2), x2: (Xc(i) + hwr).toFixed(2),
            y1: yB.toFixed(2), y2: yB.toFixed(2), stroke: C.MBLUE, 'stroke-width': 0.9 }, g);
          if (c1 !== t1) { capMark(g, Xc(i), yT, wrb); capLabel(Xc(i) + 3.4, true, frb(t1)); }
          if (c0 !== t0) capLabel(Xc(i) + 3.4, false, frb(t0));
        }
        if (!isNum(acA[i]) || capPoint(Xc(i), acA[i])) continue;
        diamond(g, Xc(i), Y(acA[i]), 3.4, col(ex.actual_color || 'NAVY'));
        if (ex.bar_labels !== false)
          txt(g, Xc(i), Y(acA[i]) - 7, frb(acA[i]), { size: 7.6, fill: col(ex.actual_color || 'NAVY') });
      }
      if (isNum(ex.qtd)) {
        var jd = ex.qtd_at != null ? +ex.qtd_at : n - 1;
        if (jd >= 0 && jd < n && !capPoint(Xc(jd), ex.qtd)) {
          diamond(g, Xc(jd), Y(ex.qtd), 4.2, C.WHITE, C.RED, 1.4);
          txt(g, Xc(jd), Y(ex.qtd) + 12, frb(ex.qtd), { size: 7.8, fill: C.RED, weight: 700 });
        }
      }

    /* year_lines ← gsx.year_lines：每年一条线叠在 Jan..Dec 上，当年红色加粗带点。
       累计与否由 Python 决定（传进来的就是要画的值），本文件不再 cumsum。 */
    } else if (kind === 'year_lines') {
      var ycs = yearColors(ex), hly = ex.highlight != null ? +ex.highlight : ex.series.length - 1;
      var fyl = fmtOf(ex.label_fmt || ex.fmt || 'f0c');
      for (s = 0; s < ex.series.length; s++) {
        var isCur = (s === hly);
        polyline(ex.series[s].values, ycs[s], isCur ? 2 : 1.1, false, isCur);
        if (!isCur) continue;
        var jl = lastFinite(ex.series[s].values), vl = jl >= 0 ? ex.series[s].values[jl] : null;
        /* 末点被截时真值已由 capLabel 竖排标出，别再横着标一遍 */
        if (jl >= 0 && clampY(vl) === vl)
          txt(g, Xc(jl) + 5, Y(vl) + 3.2, fyl(vl),
            { size: 8.2, anchor: 'start', weight: 700, fill: ycs[s] });
      }
    }

    /* 结构性断点（规矩 6）：口径变更、并表、周数不可比等「左右两侧不能连着读」的位置。
       画在该期柱的左缘（band*i，等价于 gsx._draw_break 的 x-0.5），语义是
       「从这一期起与左侧不可比」。放在系列之后画，保证虚线压在柱和线上面。 */
    if (ex.break_at != null) {
      var bAt = Array.isArray(ex.break_at) ? ex.break_at : [ex.break_at];
      var bLb = Array.isArray(ex.break_label) ? ex.break_label : [ex.break_label];
      for (i = 0; i < bAt.length; i++) {
        var bi = +bAt[i];
        if (!isFinite(bi) || bi < 0 || bi > n) continue;
        var bx = M.l + band * bi;
        el('line', { x1: bx, x2: bx, y1: M.t, y2: M.t + ph, stroke: BREAK,
          'stroke-width': 1, 'stroke-dasharray': '4 3' }, g);
        var bs = bLb.length === 1 ? bLb[0] : bLb[i];
        if (bs) txt(g, bx - 3, M.t + 3, bs, { size: 7, fill: BREAK, anchor: 'end',
          transform: 'rotate(-90 ' + (bx - 3) + ' ' + (M.t + 3) + ')' });
      }
    }
    /* 截轴说明贴右上角：被截的通常是早期的低基数尖峰（图左侧），
       左上角要留给那几个竖排真值标签。 */
    if (capOn && ex.cap_note)
      txt(svg, M.l + pw, 8, ex.cap_note, { size: 7.4, anchor: 'end', style: 'italic', fill: BREAK });

    if (ex.ylab) {
      var cy = M.t + ph / 2;
      txt(svg, 13, cy, ex.ylab, { size: 8.4, transform: 'rotate(-90 13 ' + cy + ')' });
    }
    if (ex.annot) {
      if (kind === 'bars_labeled')
        txt(svg, M.l + 3, M.t + 13, ex.annot, { size: 9.5, anchor: 'start', weight: 600, fill: C.NAVY });
      else
        txt(svg, M.l + pw - 3, M.t + ph - 7, ex.annot, { size: 8.5, anchor: 'end' });
    }

    /* hover：整段 band 命中，tooltip 列出该期全部系列 */
    var tip = host.parentElement.querySelector('.tip');
    if (tip) {
      var cross = el('line', { y1: M.t, y2: M.t + ph, stroke: C.AXIS, 'stroke-width': 1,
        opacity: 0, 'stroke-dasharray': '2 2' }, svg);
      var hit = el('g', {}, svg), rows = seriesRows(ex);
      for (i = 0; i < n; i++) {
        (function (idx) {
          var r = el('rect', { x: M.l + band * idx, y: M.t, width: band, height: ph,
            fill: 'transparent', style: 'cursor:crosshair' }, hit);
          r.addEventListener('mouseenter', function () {
            cross.setAttribute('x1', Xc(idx)); cross.setAttribute('x2', Xc(idx));
            cross.setAttribute('opacity', 1);
            var html = '<div class="th">' + labels[idx] + '</div>', j;
            for (j = 0; j < rows.length; j++) {
              var vr = rows[j].values[idx];
              html += '<div class="row"><i style="background:' + rows[j].color + '"></i><span>' +
                rows[j].name + '</span><b>' +
                (vr == null || !isFinite(vr) ? '—' : rows[j].fmt(vr)) + '</b></div>';
            }
            /* 斜纹柱（如 53 周月份）在 tooltip 里补一句为什么它与相邻柱不可比 */
            if (markSet && markSet[idx] && ex.mark_note)
              html += '<div class="row" style="font-style:italic;opacity:.85"><span>' +
                ex.mark_note + '</span></div>';
            tip.innerHTML = html; tip.style.opacity = 1;
            var tw = tip.offsetWidth, px = Xc(idx) / W * host.clientWidth;
            tip.style.left = Math.max(2, Math.min(host.clientWidth - tw - 2, px - tw / 2)) + 'px';
            tip.style.top = '0px';
          });
        }(i));
      }
      hit.addEventListener('mouseleave', function () {
        tip.style.opacity = 0; cross.setAttribute('opacity', 0);
      });
    }
  }

  function seriesRows(ex) {
    var f = fmtOf(ex.fmt || ex.yfmt), out = [], i;
    if (ex.kind === 'bar_line' || ex.kind === 'bar_line_dual') {
      out.push({ name: ex.bar.name, color: col(ex.bar.color), values: ex.bar.values,
        fmt: fmtOf(ex.bar.yfmt || ex.yfmt) });
      out.push({ name: ex.line.name, color: col(ex.line.color), values: ex.line.values,
        fmt: fmtOf(ex.line.yfmt || ex.yfmt) });
    } else if (ex.kind === 'lines' || ex.kind === 'lines_endlabels') {
      for (i = 0; i < ex.series.length; i++)
        out.push({ name: ex.series[i].name, color: col(ex.series[i].color),
          values: ex.series[i].values, fmt: f });
    } else if (ex.kind === 'stacked_dual') {
      for (i = 0; i < ex.stacks.length; i++)
        out.push({ name: ex.stacks[i].name, color: col(ex.stacks[i].color),
          values: ex.stacks[i].values, fmt: FMT.f0c });
      out.push({ name: ex.line.name, color: col(ex.line.color), values: ex.line.values, fmt: FMT.pct1 });
    } else if (ex.kind === 'diverging_bars') {
      out.push({ name: 'Reported − Core', color: C.NAVY, values: ex.values, fmt: f });

    /* ── 新图型：表格视图与 tooltip 都吃这里的行，缺一个就是「切过去一片空白」 ── */
    } else if (ex.kind === 'year_lines') {
      var yc = yearColors(ex);
      for (i = 0; i < ex.series.length; i++)
        out.push({ name: ex.series[i].name, color: yc[i], values: ex.series[i].values, fmt: f });
    } else if (ex.kind === 'qtr_bar') {
      out.push({ name: ex.legend || ex.ylab || '季度合计', color: C.NAVY, values: ex.values,
        fmt: fmtOf(ex.fmt || ex.label_fmt) });
      if (ex.line && ex.line.values)
        /* 同样走 lineVals()：图上抹掉的未满季 y/y，表格与 tooltip 也必须是「—」。
           两边不一致时，人会以为图画漏了，反而去信那个本来就不可比的数。 */
        out.push({ name: ex.line.name || 'y/y', color: col(ex.line.color || 'GREEN'),
          values: lineVals(ex), fmt: fmtOf(ex.line.yfmt || 'pct0') });
    } else if (ex.kind === 'seasonality') {
      var bs = ex.base || {}, as = ex.actual || {};
      out.push({ name: bs.name || '同月均值', color: col(bs.color || 'GRAY'),
        values: bs.values || [], fmt: f });
      out.push({ name: as.name || '实际', color: col(as.color || 'MBLUE'),
        values: as.values || [], fmt: f });
    } else if (ex.kind === 'bridge_bar') {
      for (i = 0; i < ex.stacks.length; i++)
        out.push({ name: ex.stacks[i].name, color: col(ex.stacks[i].color),
          values: ex.stacks[i].values, fmt: f });
      out.push({ name: (ex.net && ex.net.name) || 'Net change', color: col(ex.net_color || 'INK'),
        values: bridgeNet(ex, stackLen(ex)), fmt: f });
    } else if (ex.kind === 'grouped_bars') {
      var gd = ['BLUE', 'NAVY', 'MBLUE', 'GRAY'];
      for (i = 0; i < ex.groups.length; i++)
        out.push({ name: ex.groups[i].name, color: col(ex.groups[i].color || gd[i % gd.length]),
          values: ex.groups[i].values, fmt: f });
      if (ex.line && ex.line.values)
        out.push({ name: ex.line.name || 'Error', color: col(ex.line.color || 'RED'),
          values: ex.line.values, fmt: fmtOf(ex.line.yfmt || 'pct1') });
    } else if (ex.kind === 'range_band') {
      var nm = ex.names || {};
      out.push({ name: nm.lo || 'Guidance low', color: C.BLUE, values: ex.lo || [], fmt: f });
      out.push({ name: nm.hi || 'Guidance high', color: C.MBLUE, values: ex.hi || [], fmt: f });
      out.push({ name: nm.actual || 'Actual', color: col(ex.actual_color || 'NAVY'),
        values: ex.actual || [], fmt: f });
      if (isNum(ex.qtd)) {
        var qv = [], qj = ex.qtd_at != null ? +ex.qtd_at : (ex.actual || []).length - 1;
        for (i = 0; i < (ex.actual || []).length; i++) qv.push(i === qj ? ex.qtd : null);
        out.push({ name: nm.qtd || 'Quarter-to-date', color: C.RED, values: qv, fmt: f });
      }
    } else {
      out.push({ name: ex.legend || ex.ylab || '数值',
        color: ex.kind === 'gs_bar' ? C.BLUE : C.NAVY, values: ex.values, fmt: f });
    }
    return out;
  }

  function legendHTML(ex) {
    var items = [], i;
    if (ex.kind === 'bar_line_dual') {
      /* PDF 里双轴图的图例是显式 h1+h2（柱在前、线在后） */
      items.push(['sq', col(ex.bar.color), ex.bar.name]);
      items.push(['line', col(ex.line.color), ex.line.name]);
    } else if (ex.kind === 'bar_line') {
      /* 单轴图走 matplotlib get_legend_handles_labels：线在前、柱在后 */
      items.push(['line', col(ex.line.color), ex.line.name]);
      items.push(['sq', col(ex.bar.color), ex.bar.name]);
    } else if (ex.kind === 'lines' || ex.kind === 'lines_endlabels') {
      for (i = 0; i < ex.series.length; i++)
        items.push(['line', col(ex.series[i].color), ex.series[i].name]);
    } else if (ex.kind === 'gs_bar') {
      items.push(['sq', C.BLUE, ex.legend]);
      items.push(['dash', C.NAVY, 'Prior 12mo Avg.']);
    } else if (ex.kind === 'gs_line_avg') {
      items.push(['line', C.NAVY, ex.legend]);
      items.push(['dash', C.BLUE, ex.avg_label || 'Prior 12mo Avg.']);
    } else if (ex.kind === 'stacked_dual') {
      for (i = 0; i < ex.stacks.length; i++)
        items.push(['sq', col(ex.stacks[i].color), ex.stacks[i].name]);
      items.push(['line', col(ex.line.color), ex.line.name]);
    } else if (ex.kind === 'diverging_bars') {
      items.push(['sq', C.NAVY, 'Reported > Core（油汇顺风）']);
      items.push(['sq', C.RED, 'Reported < Core（油汇拖累）']);

    /* ── 新图型 ── */
    } else if (ex.kind === 'heat_matrix') {
      /* 矩阵没有系列可列，图例改成一条色标 + 两端真值 —— 否则读者只能靠格内数字，
         看不出「这一格算高还是低」是相对什么定的。 */
      var hs = heatScale(ex), hf = fmtOf(ex.fmt || 'f1');
      items.push(['grad', hs.loc + ',' + C.WHITE + ',' + hs.hic,
        hf(hs.lo) + ' → ' + hf(hs.hi) + '（5–95 分位色标）']);
    } else if (ex.kind === 'year_lines') {
      var ycl = yearColors(ex);
      for (i = 0; i < ex.series.length; i++) items.push(['line', ycl[i], ex.series[i].name]);
    } else if (ex.kind === 'qtr_bar') {
      items.push(['sq', C.NAVY, ex.legend || 'Complete quarter']);
      if (isNum(ex.partial_months) && +ex.partial_months > 0 &&
          +ex.partial_months < (ex.qtr_months || 3))
        items.push(['sq', C.BLUE, 'QTD (' + ex.partial_months + ' of ' +
          (ex.qtr_months || 3) + ' months)']);
      if (ex.line && ex.line.values)
        items.push(['line', col(ex.line.color || 'GREEN'), ex.line.name || 'y/y (RHS)']);
    } else if (ex.kind === 'seasonality') {
      items.push(['sq', col(((ex.base || {}).color) || 'GRAY'),
        (ex.base || {}).name || 'Prior-year same-month avg.']);
      items.push(['sq', col(((ex.actual || {}).color) || 'MBLUE'),
        (ex.actual || {}).name || 'Actual']);
    } else if (ex.kind === 'bridge_bar') {
      for (i = 0; i < ex.stacks.length; i++)
        items.push(['sq', col(ex.stacks[i].color), ex.stacks[i].name]);
      items.push(['dia', col(ex.net_color || 'INK'), (ex.net && ex.net.name) || 'Net change']);
    } else if (ex.kind === 'grouped_bars') {
      var gdf = ['BLUE', 'NAVY', 'MBLUE', 'GRAY'];
      for (i = 0; i < ex.groups.length; i++)
        items.push(['sq', col(ex.groups[i].color || gdf[i % gdf.length]), ex.groups[i].name]);
      if (ex.line && ex.line.values)
        items.push(['line', col(ex.line.color || 'RED'), ex.line.name || 'Error (RHS)']);
    } else if (ex.kind === 'range_band') {
      var rn = ex.names || {};
      items.push(['sq', C.BLUE, rn.range || 'Guidance range']);
      items.push(['dia', col(ex.actual_color || 'NAVY'), rn.actual || 'Actual']);
      if (isNum(ex.qtd)) items.push(['odia', C.RED, rn.qtd || 'Quarter-to-date']);
    }
    if (!items.length) return '';
    /* 新增的三种图示（菱形/空心菱形/色标）只用行内样式，不动 style.css ——
       那份文件是三个站共用的，为了图例改它等于同时改已上线的两个站。 */
    return '<div class="legend">' + items.map(function (it) {
      var dia = 'width:8px;height:8px;transform:rotate(45deg)';
      var sw = it[0] === 'sq' ? '<i class="sq" style="background:' + it[1] + '"></i>'
        : it[0] === 'dash' ? '<i class="dash" style="border-top-color:' + it[1] + '"></i>'
        : it[0] === 'dia' ? '<i style="background:' + it[1] + ';' + dia + '"></i>'
        : it[0] === 'odia' ? '<i style="background:' + C.WHITE + ';border:1.4px solid ' +
            it[1] + ';' + dia + '"></i>'
        : it[0] === 'grad' ? '<i style="width:54px;height:9px;background:linear-gradient(90deg,' +
            it[1] + ')"></i>'
        : '<i style="background:' + it[1] + '"></i>';
      return '<span>' + sw + it[2] + '</span>';
    }).join('') + '</div>';
  }

  /* 表格视图的存在意义就是逐条核对，所以比轴刻度多给一位小数
     （轴上写 $29 是对的，表格里应看到 29.24）。 */
  var PRECISE = { usd0: 'usd2', usd1: 'usd2', pct0: 'pct1', pct0z: 'pct1',
                  pp0: 'pp1', f0: 'f1', x0: 'f0' };
  function precise(fn) {
    var k;
    for (k in FMT) if (FMT[k] === fn && PRECISE[k]) return FMT[PRECISE[k]];
    return fn;
  }

  /* 热力矩阵的表格视图不是「期间 × 系列」，而是把矩阵原样铺开（行=年、列=月），
     不给它单独一支就是切到表格一片空白。 */
  function heatTable(ex) {
    var cols = ex.cols || MONTHS, rows = ex.rows || [], m = ex.matrix || [];
    var fmt = precise(fmtOf(ex.fmt || 'f1')), i, j, v;
    var h = '<div class="tblwrap"><table><caption>Exhibit ' + ex.n +
      ' — 表格视图（与图同源数值）</caption><thead><tr><th>' + (ex.row_head || '年') + '</th>';
    for (j = 0; j < cols.length; j++) h += '<th>' + cols[j] + '</th>';
    h += '</tr></thead><tbody>';
    for (i = 0; i < rows.length; i++) {
      h += '<tr><td>' + rows[i] + '</td>';
      for (j = 0; j < cols.length; j++) {
        v = (m[i] || [])[j];
        h += '<td>' + (isNum(v) ? fmt(+v) : '—') + '</td>';
      }
      h += '</tr>';
    }
    return h + '</tbody></table></div>';
  }

  function tableHTML(ex, labels) {
    if (ex.kind === 'heat_matrix') return heatTable(ex);
    var rows = seriesRows(ex), i, j;
    var h = '<div class="tblwrap"><table><caption>Exhibit ' + ex.n +
      ' — 表格视图（与图同源数值）</caption><thead><tr><th>期间</th>';
    for (j = 0; j < rows.length; j++) h += '<th>' + rows[j].name + '</th>';
    h += '</tr></thead><tbody>';
    for (i = 0; i < labels.length; i++) {
      h += '<tr><td>' + labels[i] + '</td>';
      for (j = 0; j < rows.length; j++) {
        var v = rows[j].values[i];
        h += '<td>' + (v == null || !isFinite(v) ? '—' : precise(rows[j].fmt)(v)) + '</td>';
      }
      h += '</tr>';
    }
    return h + '</tbody></table></div>';
  }

  var registry = [];
  window.Exhibits = {
    card: function (mount, ex, opt) {
      opt = opt || {};
      var labels = ex.xlabels || opt.xlabels || [];
      var card = document.createElement('section');
      card.className = 'card';
      card.innerHTML =
        '<header><h3>Exhibit ' + ex.n + ': ' + ex.title + '</h3>' +
        '<button class="toggle" type="button">表格</button></header>' +
        legendHTML(ex) +
        '<div class="plot"><div class="tip"></div><div class="host"></div></div>' +
        '<div class="tv" hidden></div>' +
        (ex.note ? '<p class="src"><b>Note:</b> ' + ex.note + '</p>' : '') +
        '<p class="src">' + (opt.source || '') +
        (ex.src_extra ? '<br>' + ex.src_extra : '') + '</p>';
      mount.appendChild(card);
      var host = card.querySelector('.host'), tv = card.querySelector('.tv'),
          btn = card.querySelector('.toggle'), mode = 'chart';
      function render() {
        if (mode === 'chart') draw(host, ex, opt);
        else tv.innerHTML = tableHTML(ex, labels);
      }
      btn.addEventListener('click', function () {
        mode = mode === 'chart' ? 'table' : 'chart';
        btn.textContent = mode === 'chart' ? '表格' : '图表';
        card.querySelector('.plot').hidden = mode === 'table';
        tv.hidden = mode === 'chart';
        render();
      });
      registry.push(render);
      render();
    },
    redrawAll: function () { registry.forEach(function (f) { f(); }); },
  };

  var t;
  window.addEventListener('resize', function () {
    clearTimeout(t); t = setTimeout(window.Exhibits.redrawAll, 150);
  });
})();
