# -*- coding: utf-8 -*-
"""生成 14 个子页的 index.html 外壳。

外壳里没有任何公司专属内容 —— 抬头、标题、口径说明全部由 data/<t>.js 注入，
渲染逻辑在 assets/page.js。这样改版式只改一处，不用挨个页面同步。
重跑本脚本是幂等的：外壳内容只跟 ticker 有关。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ⚠️ ice 在这里，不在 make_shells12.singles() 的枚举里 —— 它 2026-09 从 build/specs/
#    改成了手写的 build/ice.py，spec 已删，那边的枚举源（build/specs/ ∪ build/mrspecs/）
#    再也扫不到它。不写进这份名单，下次改版式重铺壳就会**静默漏掉** /ice/ 那一页。
#    （tsm 也在这儿，同样的历史原因；两处都要在才算齐。）
TICKERS = ['cost', 'ibkr', 'schw', 'lpla', 'hood', 'cme', 'cboe', 'hkex',
           'msci', 'spgi', 'axp', 'tsm', 'wealth', 'ice']

SHELL = '''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t}</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<div class="wrap"><div class="inner">

<div id="head-slot"></div>

<div class="masthead">
  <span class="tracker" id="tracker">—</span>
  <span class="meta" id="meta">—</span>
</div>

<h1 id="h1">—</h1>
<p class="subtitle" id="sub">—</p>
<p class="headline" id="headline">—</p>

<!-- 数据总结：由 data/<t>.js 的 brief 字段注入。带 hidden，生成器没给 brief 的页面
     不会留下一个空的带框方块（尚未接入的那几家就是这种情况）。 -->
<div class="brief" id="brief" hidden></div>

<!-- 名词释义：由 data/<t>.js 的 glossary 字段注入，位置在**所有 exhibit 之前** ——
     不认识词的人是在看第一张图之前卡住的，把释义放页尾等于没放。
     与 brief 分工不同：brief 讲「这个月的读数该怎么读」，随月份变；
     glossary 讲「这些词是什么意思」，一年到头都是同一段。
     同样带 hidden：没给 glossary 的页面不会留下一个空的带框方块。 -->
<div class="glossary" id="glossary" hidden></div>

<!-- 通栏区：汇总表 + 标了 full 的长历史图（127 根柱塞进半栏每根不到 3px） -->
<div class="grid full" id="lead"></div>

<div class="grid" id="grid"></div>

<h2 class="section" id="tblhead">核对表</h2>
<div class="grid full" id="tbl"></div>

<!-- 口径与方法说明排在附录之后：它是查证用的参考资料，不是阅读路径的一环。
     排在图与附录中间时，它把「看图 → 拿附录逐条核对」这条动线截断了。 -->
<div class="prose">
  <h2>口径与方法说明</h2>
  <ol id="notes"></ol>
</div>

<footer id="foot"></footer>

</div></div>

<script src="../data/roster.js"></script>
<script src="../data/{t}.js"></script>
<script src="../assets/charts.js"></script>
<script src="../assets/page.js"></script>
</body>
</html>
'''


def main():
    for t in TICKERS:
        d = os.path.join(ROOT, t)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(SHELL.format(t=t))
    print(f'写出 {len(TICKERS)} 个页面外壳')


if __name__ == '__main__':
    main()
