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
     source_date?  source_date_note? 官方发布日；源头不标发布日时改印 note 说明原因
     stale_source?                   沿用了本地过期缓存时打红标
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

  /* ── 顶部导航：21 张页（12 家交易所 + 9 家其它公司 + 7 张横截面）。
        roster 由 build/roster.py 生成，带各家的数据月份，停更的一眼看得出来（不靠人记）。

     **导航排成几行由 roster 的 g.row 决定，不靠 flex-wrap 自动折行。**
     原来整条导航是一个 flex 容器、靠 wrap 换行；交易所从 3 家扩到 12 家之后，
     折行断点随窗口宽度乱跳 —— 「交易所」这个标签可能落在上一行末尾，它的 12 个
     ticker 散在两行里，中间还夹着「数据与指数」。分组标签全在，分组信息没了。
     所以改成 roster 说第几行就第几行：交易所独占一行，横截面独占一行。
     row 缺失时落到第 1 行 —— 老 roster.js 与新 page.js 撞上时退化成原来的一整条，
     不至于白屏（发布顺序不可控，data/ 与 assets/ 是两次 commit）。 ── */
  function nav() {
    var R = window.ROSTER;
    if (!R) return '';
    var here = D.ticker, order = [], byRow = {};
    R.groups.forEach(function (g) {
      var k = g.row || 1;
      if (!byRow[k]) { byRow[k] = []; order.push(k); }
      byRow[k].push(g);
    });
    order.sort(function (a, b) { return a - b; });
    var h = '<nav class="nav">';
    order.forEach(function (k, i) {
      h += '<div class="navrow">';
      byRow[k].forEach(function (g) {
        h += '<span class="ng">' + g.label + '</span>';
        g.items.forEach(function (it) {
          var cur = it.ticker === here;
          h += '<a class="' + (cur ? 'on' : '') + '" href="' + (cur ? '#' : '../' + it.ticker + '/') +
               '" title="' + it.name + ' · 数据截至 ' + (it.through || '—') + '">' + it.label + '</a>';
        });
      });
      /* 「总览」只出现一次，挂在第一行右端（CSS 的 margin-left:auto）。
         挂在最后一行的话，行数一变它就换位置；第一行是唯一稳定的锚点。 */
      if (i === 0) h += '<a class="home" href="../">总览</a>';
      h += '</div>';
    });
    return h + '</nav>';
  }

  var head = el('head-slot');
  if (head) head.innerHTML = nav();

  document.title = D.tracker;
  set('tracker', D.tracker);
  /* 官方发布日。有就印日期；没有但生成器给了 source_date_note，就印那句话 ——
     「这一页为什么没有发布日」本身是信息，静默省掉只会让人以为是坏了
     （首页节奏标签踩过同一个坑：标着「次月中下旬」却停在两个月前，看的人只能判断成故障）。
     两者都没有才真的什么都不印。 */
  el('meta').innerHTML = '个人研究用 · 数据截至 ' + D.through_label +
    (D.source_date ? ' · 官方发布于 ' + D.source_date
                   : (D.source_date_note ? ' · ' + D.source_date_note : '')) +
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

  /* ── Exhibit 2..N ──
     全部挂进同一个 grid，通栏图靠 CSS 的 grid-column: 1/-1 就地横跨两列。
     早先的写法是把 ex.full 的图挂进汇总表那个容器，结果散落在各处的通栏图
     （CME 的 Ex6/17/18）会被一起提到 Exhibit 2 前面，编号读起来是 1→6→17→18→2→3。
     GS deck 的图号就是阅读顺序，打乱它比少一张图更糟。 */
  var grid = el('grid'), needRedraw = false;
  D.exhibits.forEach(function (ex) {
    window.Exhibits.card(grid, ex, {
      source: D.source,
      xlabels: ex.x === 'long' ? D.xlabels_long : D.xlabels,
      height: ex.height,
    });
    /* 通栏 class 是在 card() 渲染之后才加的，SVG 的 viewBox 还是按半栏宽算的，
       被 CSS 拉伸后字号会整体偏大 —— 所以加完 class 必须重画一遍。 */
    if (ex.full) { grid.lastElementChild.classList.add('wide'); needRedraw = true; }
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
    /* 章节标题只写「附录」两个字。以前这里写的是完整的 "Exhibit N：<title>"，
       而卡片自己的 header 也会渲染一遍同样的文字 —— 14 个页面全都把核对表标题
       原样打印了两次，一大一小上下挨着。 */
    var sec = el('tblhead');
    if (sec) sec.textContent = '附录';

    /* 宽表（HOOD 16 列、AXP 16 列、wealth 12 列）在 1280px 屏上装不下。
       .tblwrap 本来就有 overflow-x:auto、能滑，但**没有任何可滑动的提示** ——
       截图上看就是被生生切断，读者不会知道右边还有列，只会以为数据丢了。
       所以这里实测一下宽度，真的溢出才挂 class，由 CSS 画右缘渐隐 + 一行提示。 */
    var wrap = el('tbl').querySelector('.tblwrap');
    if (wrap && wrap.scrollWidth > wrap.clientWidth + 1) {
      wrap.classList.add('scrollable');
      wrap.setAttribute('data-cols', String(T.cols.length + 1));
    }
  }

  /* ── 口径与方法说明 ── */
  if (D.notes && D.notes.length) {
    el('notes').innerHTML = D.notes.map(function (n) { return '<li>' + n + '</li>'; }).join('');
  }
  if (D.footer) el('foot').innerHTML = D.footer;
})();
