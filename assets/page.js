/* ==========================================================================
   通用看板页渲染器 —— **所有**子页共用这一份，权威名单在 build/roster.py 的 GROUPS。
   这里不写死家数：原文写的是「12 家公司共用这一份」，页数一扩它就成了假话，
   而没有任何东西在守这个数字。要知道有几页，读 roster.py 的 GROUPS 或 data/roster.js。

   为什么是「一份渲染器 + 每家一个 data/<t>.js」而不是「每家一个页面脚本」：
   COST 与 IBKR 各自独立成仓时，页面脚本是写死在 index.html 里的，两份长得八成像但
   不完全一样（汇总表的字段名一个用 lab 一个用 label、一个在 JS 里格式化数字一个在
   Python 里格式化）。扩到 12 家后这种做法会变成 12 份要同步维护的近似副本 —— 改一处
   排版要改 12 遍，且必然漏。所以这里把版式固化成一份，把差异全部推进 payload。

   payload 契约（window.DASH，由 build/<t>.py 生成，见 README 的「数据契约」节）：
     ticker/name/tracker/title       标识与抬头
     data_through 'YYYY-MM'          数据月份。页面的新鲜度信号绑它，不绑构建日期
     through_label/subtitle/headline 抬头右侧、副标题、一行数据条
     brief?                          数据总结：**本月这组读数该怎么读**，随月份变
     glossary?                       名词释义：**这些词是什么意思**，不随月份变
     source                          图脚的 Source 行，所有 exhibit 共用
     source_date?  source_date_note? 官方发布日；源头不标发布日时改印 note 说明原因
     stale_source?                   沿用了本地过期缓存时打红标
     xlabels / xlabels_long          短窗口与长历史的 x 轴标签，exhibit 用 x:'long' 选后者
     summary {title,heads,rows,note} Exhibit 1 汇总表。数字**已在 Python 里格式化成字符串**，
                                     连同 *_cls 颜色类一起传过来 —— 格式化规则（pp/bp、
                                     分位反向、正负号）是口径的一部分，属于 Python
     exhibits []                     交给 charts.js 画；full:true 走通栏。
                                     例外是 kind:'table' —— 由本文件自己渲成 HTML 表，
                                     不进引擎（引擎不认得这个 kind，见下面拦截处）
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

  /* ── 顶部导航：所有子页 + 横截面页，名单与分行由 build/roster.py 的 GROUPS 定。
        roster 带各家的数据月份，停更的一眼看得出来（不靠人记）。
        原文写的是「12 家 + 2 张横截面页。roster 由 build_all.py 生成」——
        前半随页数扩张成了假话，后半那个文件在本仓根本不存在（生成器是 build/roster.py）。 ── */
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

  /* ── 数据总结（brief）──
     一行数据条给的是**读数**，这一段给的是**读数该怎么读**：基数效应、口径背离、
     所处区间。两者职责不同，所以没有并进 headline。
     文字整段在 Python 侧拼好（同 CONTRACT：页面不做计算，也不做措辞判断）。
     生成器没给 brief 的页面保持 hidden，不会留下一个空框。 */
  if (D.brief) {
    var bn = el('brief');
    if (bn) { bn.innerHTML = D.brief; bn.hidden = false; }
  }

  /* ── 名词释义（glossary）──
     与 brief 的分工：brief 说的是「**这个月**这组读数该怎么读」（基数效应、口径背离、
     所处区间），每月重写；glossary 说的是「**这些词**是什么意思」（ADV、DARTs、
     零售月、口径断点……），一年到头都是同一段，换个月份不用动一个字。
     两件事合进 brief 会有两个后果：每月重写 brief 时要连释义一起重抄一遍（迟早抄漏
     或抄旧），而且真正当月的判断被淹在一堆常年不变的定义里。
     所以给它自己的槽位，排在**所有 exhibit 之前** —— 不认识词的人是在看第一张图
     之前卡住的。同样整段在 Python 侧拼好（页面不做措辞判断），没给就保持 hidden。 */
  if (D.glossary) {
    var gn = el('glossary');
    if (gn) { gn.innerHTML = D.glossary; gn.hidden = false; }
  }

  /* ── HTML 表格卡片：两处共用 ──
     用它的是 ① 末尾核对表（顶层 D.table）② exhibits 里 kind:'table' 的那种。
     两者的字段完全一样（n/title/idx/cols/rows，值都是已格式化的字符串），
     所以渲染只留一份 —— 复制成两份的话，改一处版式必然漏掉另一处，而两张表
     长得八成像，肉眼比对根本发现不了（这正是 12 家共用一份 page.js 的理由）。

     **不进 charts.js**，理由同下面 Exhibit 1 处那一条（SVG 内核不兼职排 HTML 表）；
     再加一条：引擎服务着全站 34 张页，为一个根本不画图的 kind 动它要重新验收 34 页
     （docs/CHART_KINDS.md 开头那句「引擎不许改」）。

     `T.note` 是给 kind:'table' 用的，位置与用词跟 charts.js 的卡片一致
     （`<p class="src"><b>Note:</b> …`，排在 Source 行之前）。顶层 D.table 没有这个
     字段（CONTRACT §4），所以这一段对既有 34 页是死代码，它们渲染出来的 HTML
     与拆函数之前逐字节相同。 */
  function tableCardHTML(T, src) {
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
    return h + '</tbody></table></div>' +
      (T.note ? '<p class="src"><b>Note:</b> ' + T.note + '</p>' : '') +
      '<p class="src">' + src + '</p></section>';
  }

  /* 宽表（HOOD 16 列、AXP 16 列、wealth 12 列）在 1280px 屏上装不下。
     .tblwrap 本来就有 overflow-x:auto、能滑，但**没有任何可滑动的提示** ——
     截图上看就是被生生切断，读者不会知道右边还有列，只会以为数据丢了。
     所以这里实测一下宽度，真的溢出才挂 class，由 CSS 画右缘渐隐 + 一行提示。
     必须在 host 已经进了文档之后调用：没上屏的元素 clientWidth 是 0，
     scrollWidth > 0 恒成立，会给每一张表都挂上滑动提示。 */
  function markScrollable(host, T) {
    var wrap = host.querySelector('.tblwrap');
    if (wrap && wrap.scrollWidth > wrap.clientWidth + 1) {
      wrap.classList.add('scrollable');
      wrap.setAttribute('data-cols', String(T.cols.length + 1));
    }
  }

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
    /* 章节标题：带 ex.section 的图之前起一个新板块。
       用途是「这一段图读的不是同一份数据」—— TSM 的 Ex10 起读的是营收之外的
       五张法定申报表，跟上面九张没有派生关系，混在一条编号里读者会默认它们同源。
       没有任何既有页面的 payload 带这个字段，所以另外 33 页一行都不会变。 */
    if (ex.section) {
      var sh2 = document.createElement('h2');
      sh2.className = 'section ingrid';
      sh2.textContent = ex.section;
      grid.appendChild(sh2);
    }
    /* kind:'table' 在这里被截住，**不往下走引擎**。
       charts.js 的 kind 分派没有这一支：未知 kind 会掉进 else 分支当 values[] 柱图，
       而这种 exhibit 根本没有 values —— 引擎抛 TypeError，本页此图之后的 exhibit
       一张都渲染不出来（同 verify_pages 里「缺必填字段」那条的后果）。
       所以拦截必须在 card() 之前，而不是在引擎里加一支。 */
    if (ex.kind === 'table') {
      var box = document.createElement('div');
      box.innerHTML = tableCardHTML(ex, D.source);
      var tc = box.firstChild;
      /* 标出「这是夹在图中间的表」，让 CSS 关掉末行高亮 —— 那条高亮是给附录核对表的
         最新月行准备的，这种表的最后一行只是又一个普通项目（见 style.css 的 .tblex）。 */
      tc.classList.add('tblex');
      /* 表格卡片没有 SVG viewBox 要重算，所以 full 只是加 class，不进 needRedraw：
         HTML 表的列宽由浏览器按容器宽自己排，加完 class 就已经是最终版式。 */
      if (ex.full) tc.classList.add('wide');
      grid.appendChild(tc);
      markScrollable(tc, ex);      // 必须在 appendChild 之后：没上屏量不出宽度
      return;
    }
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
    el('tbl').innerHTML = tableCardHTML(T, D.source);
    /* 章节标题只写「附录」两个字。以前这里写的是完整的 "Exhibit N：<title>"，
       而卡片自己的 header 也会渲染一遍同样的文字 —— 14 个页面全都把核对表标题
       原样打印了两次，一大一小上下挨着。 */
    var sec = el('tblhead');
    if (sec) sec.textContent = '附录';
    markScrollable(el('tbl'), T);
  }

  /* ── 口径与方法说明 ── */
  if (D.notes && D.notes.length) {
    el('notes').innerHTML = D.notes.map(function (n) { return '<li>' + n + '</li>'; }).join('');
  }
  if (D.footer) el('foot').innerHTML = D.footer;
})();
