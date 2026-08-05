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

   所有数值由 build_data.py（复用 skill 同一份算法）预先算好，本文件只负责画。

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
    WHITE: '#FFFFFF', GRID: '#E3E3E3', AXIS: '#999999', INK: '#333333',
  };
  var col = function (k) { return C[k] || k; };
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

  function draw(host, ex, opt) {
    host.innerHTML = '';
    opt = opt || {};
    var W = host.clientWidth || 520, i, s;
    var labels = ex.xlabels || opt.xlabels || [], n = labels.length;
    if (!n) { host.innerHTML = '<p class="note">无数据</p>'; return; }
    /* x 标签角度：COST 月份标签 90°、IBKR 月份标签 45°、COST Ex12 年份水平（同 PDF） */
    var rot = ex.xrot != null ? ex.xrot : (n > 20 ? 90 : 45);
    var XB = rot === 90 ? 48 : (rot === 0 ? 22 : 36);
    var kind = ex.kind;
    var dual = kind === 'bar_line_dual' || kind === 'stacked_dual';
    var perPointLabels = kind === 'gs_bar' || kind === 'gs_line' || kind === 'gs_line_avg' ||
                         kind === 'stacked_dual' || kind === 'lines_endlabels';
    var H = (opt.height || (perPointLabels ? 268 : 248)) + XB;
    /* 截轴时真值标注竖排在图顶之上，顶边距要留够一行竖排文字（约 22px）；
       右轴有标题时右边距要在刻度数字之外再让出一列。 */
    var capOn = ex.ycap != null || ex.yfloor != null;
    var M = { t: capOn ? 30 : 14,
              r: dual ? (ex.ylab2 ? 56 : 42)
                      : (kind === 'lines_endlabels' || kind === 'gs_line_avg' ? 42 : 14),
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
    else if (kind === 'lines' || kind === 'lines_endlabels') {
      for (s = 0; s < ex.series.length; s++) lv = lv.concat(ex.series[s].values);
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
      var rv = rc.values.filter(function (v) { return v != null && isFinite(v); });
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
        el('path', { d: barPath(Xc(i) - wg / 2, Y(0), Y(ex.values[i]), wg, 3),
          fill: (markSet && markSet[i]) ? 'url(#' + hatchId + ')' : C.BLUE }, g);
        txt(g, Xc(i), Y(ex.values[i]) - 4.5, fb(ex.values[i]), { size: 8 });
      }
      el('line', { x1: M.l, x2: M.l + pw, y1: Y(avg), y2: Y(avg), stroke: C.NAVY,
        'stroke-width': 1.4, 'stroke-dasharray': '6 4' }, g);
      if (ex.yoy_txt) oval(g, Xc(0) + band * 0.25, Y(y1 * 0.93), ex.yoy_txt);
      if (ex.mom_txt) {
        var last = ex.values[n - 1];
        oval(g, Xc(9) + band * 0.2, Y(Math.min(last * 1.13, y1 * 0.94)), ex.mom_txt,
          [Xc(11) + band * 0.3, Y(last * 1.06)]);   // PDF: arrow_to=(11.8, vals[-1]*1.06)
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
        if (ex.mom_txt) oval(g, Xc(9) + band * 0.1, by, ex.mom_txt, [Xc(11) + band * 0.5, by]);
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
    }
    if (!items.length) return '';
    return '<div class="legend">' + items.map(function (it) {
      var sw = it[0] === 'sq' ? '<i class="sq" style="background:' + it[1] + '"></i>'
        : it[0] === 'dash' ? '<i class="dash" style="border-top-color:' + it[1] + '"></i>'
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

  function tableHTML(ex, labels) {
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
