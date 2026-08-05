/* ==========================================================================
   通用看板页渲染器 —— 12 家公司共用这一份。

   为什么是「一份渲染器 + 每家一个 data/<t>.js」而不是「每家一个页面脚本」：
   COST 与 IBKR 各自独立成仓时，页面脚本是写死在 index.html 里的，两份长得八成像但
   不完全一样（汇总表的字段名一个用 lab 一个用 label、一个在 JS 里格式化数字一个在
   Python 里格式化）。扩到 12 家后这种做法会变成 12 份要同步维护的近似副本 —— 改一处
   排版要改 12 遍，且必然漏。所以这里把版式固化成一份，把差异全部推进 payload。

   payload 契约（window.DASH，由 build/<t>.py 生成，见 README 的「数据契约」节）：
     ticker/name/tracker/title       标识与抬头
     data_through 'YYYY-MM'          数据月份。页面的新鲜度信号绑它，不绑构建日期
     through_label/subtitle/headline 抬头右侧、副标题、一行数据条
     source                          图脚的 Source 行，所有 exhibit 共用
     source_date?  stale_source?     官方发布日；沿用了本地过期缓存时打红标
     xlabels / xlabels_long          短窗口与长历史的 x 轴标签，exhibit 用 x:'long' 选后者
     summary {title,heads,rows,note} Exhibit 1 汇总表。数字**已在 Python 里格式化成字符串**，
                                     连同 *_cls 颜色类一起传过来 —— 格式化规则（pp/bp、
                                     分位反向、正负号）是口径的一部分，属于 Python
     exhibits []                     交给 charts.js 画；full:true 走通栏
     table {n,title,cols,rows}       末尾的原始值核对表
     notes []                        「口径与方法说明」的 li，允许 HTML
     footer                          页脚 HTML

   数值一律在 Python 侧算好、格式化好。本文件只排版，不做任何计算 ——
   同一个数字在两个语言里各算一遍，迟早会出现图上与表里不一致而没人发现。
   ========================================================================== */
(function () {
  'use strict';
  var D = window.DASH;
  if (!D) { document.body.innerHTML = '<p style="padding:40px">缺少 data/*.js</p>'; return; }

  function el(id) { return document.getElementById(id); }
  function set(id, text) { var n = el(id); if (n) n.textContent = text; }

  /* ── 顶部导航：12 家 + 2 张横截面页。roster 由 build_all.py 生成，
        带各家的数据月份，停更的一眼看得出来（不靠人记）。 ── */
  function nav() {
    var R = window.ROSTER;
    if (!R) return '';
    var here = D.ticker, h = '<nav class="nav">';
    R.groups.forEach(function (g) {
      h += '<span class="ng">' + g.label + '</span>';
      g.items.forEach(function (it) {
        var cur = it.ticker === here;
        h += '<a class="' + (cur ? 'on' : '') + '" href="' + (cur ? '#' : '../' + it.ticker + '/') +
             '" title="' + it.name + ' · 数据截至 ' + (it.through || '—') + '">' + it.label + '</a>';
      });
    });
    return h + '<a class="home" href="../">总览</a></nav>';
  }

  var head = el('head-slot');
  if (head) head.innerHTML = nav();

  document.title = D.tracker;
  set('tracker', D.tracker);
  el('meta').innerHTML = '个人研究用 · 数据截至 ' + D.through_label +
    (D.source_date ? ' · 官方发布于 ' + D.source_date : '') +
    (D.stale_source ? '<span class="chip">官网下载失败，本次沿用本地缓存</span>' : '');
  set('h1', D.title);
  set('sub', D.subtitle);
  set('headline', D.headline);

  /* ── Exhibit 1：汇总表 ──
     不进 charts.js：那份文件是 SVG 绘图内核，塞 HTML 表格进去会让它同时承担两种职责。 */
  var S = D.summary;
  if (S) {
    var sh = '<section class="card"><header><h3>Exhibit 1: ' + S.title + '</h3></header>' +
      '<div class="tblwrap"><table class="sum"><thead><tr><th>指标</th>';
    S.heads.forEach(function (x, i) {
      sh += '<th' + (i === S.sep ? ' class="sep"' : '') + '>' + x + '</th>';
    });
    sh += '</tr></thead><tbody>';
    S.rows.forEach(function (r) {
      if (r.kind === 'group') {
        sh += '<tr class="grp"><td colspan="' + (S.heads.length + 1) + '">' + r.label + '</td></tr>';
        return;
      }
      sh += '<tr><td>' + r.label + '</td>';
      r.cells.forEach(function (c, i) {
        sh += '<td class="' + (c.cls || '') + (i === S.sep ? ' sep' : '') + '">' + c.v + '</td>';
      });
      sh += '</tr>';
    });
    sh += '</tbody></table></div><p class="src">' + D.source +
      (S.note ? '<br><b>Note:</b> ' + S.note : '') + '</p></section>';
    el('lead').innerHTML = sh;
  }

  /* ── Exhibit 2..N ── */
  var lead = el('lead'), grid = el('grid'), needRedraw = false;
  D.exhibits.forEach(function (ex) {
    var mount = ex.full ? lead : grid;
    window.Exhibits.card(mount, ex, {
      source: D.source,
      xlabels: ex.x === 'long' ? D.xlabels_long : D.xlabels,
      height: ex.height,
    });
    /* 通栏卡片是在 card() 渲染之后才加的 class，SVG 的 viewBox 还是按半栏宽算的，
       被 CSS 拉伸后字号会整体偏大 —— 所以加完 class 必须重画一遍。 */
    if (ex.full) { mount.lastElementChild.classList.add('wide'); needRedraw = true; }
  });
  if (needRedraw) window.Exhibits.redrawAll();

  /* ── 末尾核对表：官方原始单位，供逐条核对 ── */
  var T = D.table;
  if (T) {
    var h = '<section class="card"><header><h3>Exhibit ' + T.n + ': ' + T.title +
      '</h3></header><div class="tblwrap"><table><thead><tr><th>' + (T.idx || '月份') + '</th>';
    T.cols.forEach(function (c) { h += '<th>' + c[0] + '</th>'; });
    h += '</tr></thead><tbody>';
    T.rows.forEach(function (r) {
      h += '<tr><td>' + r.xl + '</td>';
      T.cols.forEach(function (c) {
        var v = r[c[1]];
        h += '<td>' + (v == null ? '—' : v) + '</td>';
      });
      h += '</tr>';
    });
    el('tbl').innerHTML = h + '</tbody></table></div><p class="src">' + D.source + '</p></section>';
    var sec = el('tblhead');
    if (sec) sec.textContent = 'Exhibit ' + T.n + '：' + T.title;
  }

  /* ── 口径与方法说明 ── */
  if (D.notes && D.notes.length) {
    el('notes').innerHTML = D.notes.map(function (n) { return '<li>' + n + '</li>'; }).join('');
  }
  if (D.footer) el('foot').innerHTML = D.footer;
})();
