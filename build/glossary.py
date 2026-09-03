# -*- coding: utf-8 -*-
"""名词释义（payload 的 `glossary` 字段）的**版式层 + 护栏**。全站一份。

═══ 这个模块做什么、不做什么 ═══
做：把 `[(词, 释义), …]` 这张表拼成 `.glossary` 的 CSS 唯一认得的那段 HTML，
    并在构建期把四类「页面上看得见、但构建期一声不吭」的写法挡掉（见下）。
不做：**一个字的措辞都不在这里**。释义是口径判断，属于各家自己 ——
    与 `build/brief.py` 同一条分工（那边只算事实，句子由各家 compose_brief 拼）。

═══ 为什么版式要收在一处 ═══
`.glossary` 的 CSS（assets/style.css）只认 `<h4>` + `<dl><dt>…</dt><dd>…</dd></dl>`
这一种结构：`dl` 是 `grid-template-columns: max-content 1fr`，`dt` 在左、`dd` 在右。
34 页各拼各的字符串，迟早有一页把 `<dt>` 写成 `<b>`，页面照渲、grid 只剩一列，
而**没有任何东西会响**。所以拼装只留这一个入口，各家只交那张二元组表。

═══ 四道护栏，各自堵的是哪一种「页面上看得见的静默缺陷」═══
  1. Markdown 星号     page.js 走 innerHTML，`**粗体**` 不加粗，四个星号原样印出来，
                       而 glossary 是**全页第一段**被读到的文字。
                       （build/verify_pages.py 的 _md() 也查，但那是产物侧的事后 WARN；
                        这里是构建期硬失败 —— 早一步，且不给「WARN 攒着不看」留口子。）
  2. 未知标签          `<div>` / `<p>` 进 `<dd>` 会把两列 grid 撑成块级、错行；
                       `<script>` 更不必说。只放行 §_TAGS 里那几个纯行内标签。
  3. `dt` 过长         第一列宽度是 `max-content`（取**最长**的那个 dt）——
                       一个 20 字的词条会把所有释义挤成一根窄柱。窄到装不下时
                       还会顶出横向滚动条（style.css 那条注释点名的 HSCROLL 判据，
                       tools/visual_qa.py 判 🔴）。所以按估算像素宽卡上限。
  4. 词条重复 / 空值   同一个词写两遍是复制粘贴的残留；空 dd 会在页面上留一格空白，
                       两者都不该由读者来发现。

═══ 与 brief 的分工（CONTRACT §1 那张表，抄在这里免得两处不同步）═══
brief 说「**这个月**这组读数该怎么读」，每月重写；
glossary 说「**这些词**是什么意思」，一年到头是同一段。
⇒ 释义里**不写当月判断**。要写数，只写两类：
   (a) 把定义钉住的**结构性**量（会员费占总收入多少、合约乘数是多少）；
   (b) 恒等式本身。
   两类都当场从 CSV / 申报现算，别写死 —— 写死的那一天就是它开始变旧的那一天。
"""

import re

# ── §_TAGS 放行名单 ────────────────────────────────────────────────────────
# 全是**行内**标签：进了两列 grid 也不会撑破行。`<a>` 不在名单里 ——
# 释义是页面最上方的一段定义，正文里挂外链会把读者在读第一段时就带走；
# 出处该写在 notes 或图注里（cost 的 9 条释义一个链接都没有，是同一条判断）。
_TAGS = {'b', 'i', 'u', 's', 'code', 'br', 'sup', 'sub', 'em', 'strong', 'small'}
_TAG_RE = re.compile(r'</?\s*([A-Za-z][A-Za-z0-9]*)')

# ── §_DT 宽度 ─────────────────────────────────────────────────────────────
# 桌面版第一列是 max-content，量的是**最长的那个 dt**。这里按字符类估算宽度：
# 12.5px 字号、700 字重下，CJK/全角约占一个字号宽，西文与数字约 0.58 个字号宽。
# 上限 170px 是照 /cost/ 那 9 条实测定的（最宽的 'Digitally-Enabled' ≈ 119px、
# '净销售额与总收入' ≈ 100px），留了约 40% 余量；再宽下去第二列在 1240px 版心里
# 就开始明显变窄，而窄屏（≤900px）虽然改成上下排、但 dt 仍要单独占一行。
_DT_MAX_PX = 170.0
_WIDE = re.compile(r'[ᄀ-ᅟ⺀-〾ぁ-㏿㐀-䶿'
                   r'一-鿿ꀀ-꓏가-힣豈-﫿'
                   r'︰-﹏＀-｠￠-￦]')


def dt_px(s):
    """`dt` 的估算像素宽（12.5px / 700）。护栏与单测共用，别各算一份。"""
    return sum(12.5 if _WIDE.match(ch) else 7.25 for ch in s)


def render(pairs, where='glossary'):
    """`[(词, 释义), …]` → `.glossary` 认得的那段 HTML；一条都没有就返回 None。

    返回 None 而不是空串：payload 里 `'glossary': None` 与不给这个字段，
    在 page.js 那边是同一条分支（`if (D.glossary)`），块保持 hidden、页面上
    不会留下一个空的带框方块。所以调用方可以无脑写
    `payload['glossary'] = glossary.render(G)`，不必自己判空。

    参数
      pairs  可迭代的二元组 (dt, dd)。**顺序即页面上的顺序** ——
             页面不排序，各家自己决定先讲哪个词（一般是「本页最独有的口径」在前、
             「要用到前面几个词才讲得清的」在后）。
      where  出错信息里的定位串，一般传 ticker。

    出错一律 `SystemExit`（与 build/single.py 的 SpecError、mrbase 的 SpecError 同档）：
    这四类毛病在页面上都**看得见**，放过去等于把它交给读者去发现。
    """
    items = [tuple(p) for p in (pairs or [])]
    if not items:
        return None
    seen = {}
    out = []
    for i, p in enumerate(items):
        if len(p) != 2:
            raise SystemExit(f'{where}: 第 {i + 1} 条不是 (词, 释义) 二元组：{p!r}')
        dt, dd = (str(x) if x is not None else '' for x in p)
        dt, dd = dt.strip(), dd.strip()
        if not dt:
            raise SystemExit(f'{where}: 第 {i + 1} 条的词是空的')
        if not dd:
            raise SystemExit(f'{where}: 词条 {dt!r} 的释义是空的 —— '
                             f'页面上会留下一格空白，没有任何提示')
        if dt in seen:
            raise SystemExit(f'{where}: 词条 {dt!r} 出现两次（第 {seen[dt]} 条与'
                             f'第 {i + 1} 条）—— 两条释义只会前后脚印在同一列里')
        seen[dt] = i + 1
        if '<' in dt or '>' in dt:
            raise SystemExit(f'{where}: 词条 {dt!r} 里有 HTML 标签 —— '
                             f'`dt` 由 CSS 统一加粗，标签只会让第一列宽度算不准')
        w = dt_px(dt)
        if w > _DT_MAX_PX:
            raise SystemExit(
                f'{where}: 词条 {dt!r} 估算宽 {w:.0f}px，超过 {_DT_MAX_PX:.0f}px。'
                f'第一列是 max-content（取最长的那个词），一个长词会把**所有**释义'
                f'挤成一根窄柱，窄屏下还会顶出横向滚动条。把限定语挪进释义里。')
        for s, what in ((dt, '词'), (dd, '释义')):
            if '**' in s:
                raise SystemExit(
                    f'{where}: {what} {dt!r} 里有 Markdown 的 `**` —— '
                    f'page.js 走 innerHTML，星号会原样印在整页第一段上。用 <b>…</b>。')
        bad = sorted({t.lower() for t in _TAG_RE.findall(dd)} - _TAGS)
        if bad:
            raise SystemExit(
                f'{where}: 词条 {dt!r} 的释义里有非行内标签 {bad} —— '
                f'`dd` 在两列 grid 里，块级标签会把那一行整个错开。'
                f'放行的只有 {sorted(_TAGS)}。')
        out.append(f'<dt>{dt}</dt><dd>{dd}</dd>')
    return '<h4>名词释义</h4><dl>' + ''.join(out) + '</dl>'


def terms(html):
    """从渲染好的一段 glossary 里把词条抽回来（verify_pages / 单测用）。"""
    return re.findall(r'<dt>(.*?)</dt>', html or '', re.S)


if __name__ == '__main__':                                   # python3 build/glossary.py
    assert render([]) is None
    h = render([('ADV', '日均成交量（average daily volume）：当月成交合计 ÷ 当月交易日数。')])
    assert h.startswith('<h4>名词释义</h4><dl><dt>ADV</dt><dd>')
    assert terms(h) == ['ADV']
    for bad, why in (
            ([('x', 'a **b**')], 'Markdown'),
            ([('x', '<div>a</div>')], '块级标签'),
            ([('x', ''), ], '空释义'),
            ([('x', 'a'), ('x', 'b')], '重复词条'),
            ([('这是一个非常非常长的词条名字够长了吧', 'a')], '过长 dt'),
    ):
        try:
            render(bad)
        except SystemExit:
            pass
        else:
            raise AssertionError(f'没挡住：{why}')
    print('build/glossary.py 自测通过')
