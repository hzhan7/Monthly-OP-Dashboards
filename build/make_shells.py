# -*- coding: utf-8 -*-
"""生成 14 个子页的 index.html 外壳。

外壳里没有任何公司专属内容 —— 抬头、标题、口径说明全部由 data/<t>.js 注入，
渲染逻辑在 assets/page.js。这样改版式只改一处，不用挨个页面同步。
重跑本脚本是幂等的：外壳内容只跟 ticker 有关。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TICKERS = ['cost', 'ibkr', 'schw', 'lpla', 'hood', 'cme', 'cboe', 'hkex',
           'msci', 'spgi', 'axp', 'tsm', 'exchanges', 'wealth']

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

<!-- 通栏区：汇总表 + 标了 full 的长历史图（127 根柱塞进半栏每根不到 3px） -->
<div class="grid full" id="lead"></div>

<div class="grid" id="grid"></div>

<div class="prose">
  <h2>口径与方法说明</h2>
  <ol id="notes"></ol>
</div>

<h2 class="section" id="tblhead">核对表</h2>
<div class="grid full" id="tbl"></div>

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
