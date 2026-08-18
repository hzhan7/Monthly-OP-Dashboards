# -*- coding: utf-8 -*-
"""创意电子（GUC，3443.TW）月度营收看板 —— **指向共用底座的薄壳 + 一处本家专属的裁剪**。

    图列 / 图注 / 口径规矩 / 版式判据 → build/mrbase.py（底座，不认得任何一家）
    窗口左端与排版的裁决             → build/mrwin.py（可单测：python3 build/mrwin.py）
    GUC 自己的数据源、单位与精度、
    分部拆分、可加总凭据、
    为什么没有汇率腿与指引桥         → build/mrspecs/guc.py

━━ 这个壳是「图列归属」的落地，不是一层转发 ━━━━━━━━━━━━━━━━━━━━━━━━
`monthly_run.py:389` 的 `builder(t)` 按**文件在不在**解析生成器：先找 `build/<t>.py`，
再找下划线版，最后才退到 `build/single.py` + `build/specs/<t>.py`。
本文件一落地，`data/guc.js` 就归本底座，每月 cron 也走这条路 —— 底座的
`owned_elsewhere()` 认得本壳里的 `mrbase` 字样，因此不再拦写 `data/`。

⚠️ `build/specs/guc.py` 仍在仓库里，但**已经不再被调用**（本壳优先级高于它）。
   留着它是为了保留旧图列的口径记录（Note 17b 那两个地区占比就转录自它），
   不是为了继续生成页面；要清理请单独一轮做。
   两份文件对同一页并存期间，**改口径请改 `build/mrspecs/guc.py`**。
   （与 tsm / ase / mtk / umc / alchip 五家同一处置。）

━━ 与旧图列（build/single.py + build/specs/guc.py）相比，换来什么、丢了什么 ━━
换来：Ex1 汇总表（月营收 / Turnkey / NRE & Others / 3MMA / QTD / YTD / 占 TTM 比重
      + 3Y 分位列）、月营收柱 + 12 个月滚动合计同比、月→季桥（未满季浅色 +
      y/y 置 null）、环比、全历史（合并线 + 两条分部线）、逐年×逐月
      **单月**同比矩阵、近 13 个月核对表（官方原始单位、多两列分部），
      以及页尾整套现算的口径说明（七期查核／核阅数对账、逐月分部恒等式、
      2026-01 分部并行不是断点、为什么没有美元腿与指引桥、
      「公司其实是报同比的、只是没落库」这条更正）。
丢掉：旧页的 decomp / ttm_yoy / seasonality 三张（本底座不产出）。
      季节性改由热力矩阵承担；分部构成改由全历史图的两条线 + 汇总表两行承担。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本壳唯一一段真正的逻辑：`_trim_stacked_bar()`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
2026-08 起本页序列自 **2016-01**（合并营收从 MOPS 月档回补，见 fetch/guc.py 源 1b），
而官方的 Turnkey / NRE & Others **月度拆分只到 2017-01**（IR 那份 xlsx 的硬边界）。
于是月营收柱（`gs_bar` + `stacks`）的窗口里出现了 12 个「柱高有值、分段全空」的月份。

**这在引擎里不是「素色柱」，是「没有柱」。** `assets/charts.js:1317-1345` 的分段分支
只要 `ex.stacks` 非空、该柱没被截轴/斜纹命中就一定走，段值是 null 就 `continue` ——
12 个月一根 rect 都不画，柱顶那个数值标签却照印，页面上是十二个凭空悬着的数字。
`build/verify_pages.py:384` 那条「stacks 在 N 个位置有分段缺值」正是拦这个的，
本轮实测确实 ERROR。

**为什么只能在这里修**：
  · 补 0 / 按 2017 的比例摊 / 拿合计当单段 —— 都是造数，`fetch/guc.py` 口径坑 8 已禁；
  · 把 `values[i]` 置 null 让护栏放行 —— 那是把真数据从图上删掉，比画错更糟；
  · 正解是底座给 `stacks` 一条「该月分段缺值就整根退回单色」的分支，
    **但 build/mrbase.py 是 tsm / ase / mtk / umc / alchip / nanya 共用的**，
    本轮不动它（并发改共用文件会互相覆盖）。
⇒ 退而求其次，按任务书 D 段给平滑图型开的同一个方子办：**裁左端**
  （`mrwin.resolve()` 对 Ex5 `stacked_dual` 做的就是这件事，本图只是因为
  `stacks` 不是 `mrwin.Leg`、底座看不见它，才没被自动裁到）。
  于是本图左端落在「两条分部列都有值」的第一期，其余各图照常自 2016-01 起 ——
  **同一页各图左端本来就不同**（环比晚 1 期、占比图晚 12 期），这不是新引入的形态。

⚠️ **别用 `python3 build/mrbase.py guc` 重建本页。** 那条路绕过本壳、也就绕过这段裁剪，
   写出来的 `data/guc.js` 会带着 12 根「有数值标签、没有柱」的空柱
   （`build/verify_pages.py` 会当场报 ERROR，那是唯一的安全网 —— 页面自己不会喊）。
   重建本页只有两条合法入口：`python3 build/guc.py`，或 `monthly_run.py`
   （它的 `builder()` 解析到的正是本文件）。
⚠️ 这一段是**临时的**。底座哪天学会 per-month 退回单色，把 `_trim_stacked_bar()`
   连同它的调用一起删掉即可，本壳退回三行的薄壳。
⚠️ 它**只裁不造**：不改任何一个数值，只丢掉左端那几格；丢掉几格、为什么丢，
   由 `mrspecs/guc.py` 的 `note_extra['rev_bar']` 现算着写在图注里。
⚠️ 认不出该改的地方就**抛异常**，绝不静默跳过 —— 静默跳过会让页面退回到
   「十二个悬空数字」那个状态，而且三道闸门里只有 verify_pages 抓得到。
"""
import re
import os
import sys

import mrbase
import payload_guard


class GucShellError(RuntimeError):
    """本壳的故障出口。底座的措辞一变，宁可整页构建失败，也不静默留下一段假话。"""


def _seg_start(ex):
    """分部堆叠从哪一格起才是完整的（每一段都有值）。全窗口都完整就返回 0。"""
    stk = ex.get('stacks') or []
    vals = ex.get('values') or []
    for i in range(len(vals)):
        if all(s['values'][i] is not None for s in stk):
            return i
    raise GucShellError('Ex2 的 stacks 一格完整的都没有 —— 分部列整条空了？')


def _trim_stacked_bar(payload):
    """把月营收柱裁到分部列的起点。返回 (裁掉几格, 新左端标签)；不用裁就返回 (0, None)。"""
    ex = next((e for e in payload['exhibits']
               if e.get('kind') == 'gs_bar' and e.get('stacks')), None)
    if ex is None:                       # 没有分部堆叠柱 ⇒ 本段无对象，正常退出
        return 0, None
    k = _seg_start(ex)
    if k == 0:
        return 0, None
    n_old, lab_old = len(ex['values']), ex['xlabels'][0]

    # ── ① 数组逐条裁左端。**只切片，不改任何一个数** ──────────────────────────
    ex['xlabels'] = ex['xlabels'][k:]
    ex['values'] = ex['values'][k:]
    if ex.get('yoy'):
        ex['yoy']['values'] = ex['yoy']['values'][k:]
    for s in ex['stacks']:
        s['values'] = s['values'][k:]

    # ── ② 图注里两处随窗口长度变的数 ────────────────────────────────────────
    #    (a) 「右轴那条线比柱短 N 期」—— 底座按未裁前的下标算的，裁掉 k 格就少 k 期。
    note = ex['note']
    m = re.search(r'(比柱短 )(\d+)( 期)', note)
    if not m:
        raise GucShellError(
            '在 Ex2 图注里找不到「比柱短 N 期」那句 —— 底座的 mrwin.resolve() 措辞变了。'
            '裁完不改这个数，页面会印一个比实际多 %d 期的谎。' % k)
    if int(m.group(2)) < k:
        raise GucShellError(
            f'Ex2 图注说右轴线比柱短 {m.group(2)} 期，比要裁掉的 {k} 期还少 —— '
            f'那条线的首点落在分部列起点之前，裁左端会把它整条切没，本壳不处理这种形态。')
    note = note[:m.start()] + f'比柱短 {int(m.group(2)) - k} 期' + note[m.end():]

    #    (b) 排版说明（通栏判定、x 标签抽稀步长、首末标签压刻度）整段重算 ——
    #        那一段全是按 n=127 量出来的像素账，裁完每一个数都不对。
    #        `mrbase.lay()` 就是底座生成这一段用的那个函数，这里**调它**、不抄它。
    heads = ('<b>本图通栏</b>', 'x 轴标签每 ', '首点/末点的数值标签')
    at = min([note.find(h) for h in heads if note.find(h) >= 0] or [-1])
    if at < 0:
        raise GucShellError(
            'Ex2 图注里认不出底座那段排版说明（找不到「本图通栏 / x 轴标签每 / '
            '首点/末点的数值标签」任何一个开头）—— mrbase.lay() 的措辞变了。'
            '不重算的话页面会拿 127 期的像素账去解释一张 %d 期的图。' % (n_old - k))
    ex.pop('full', None)
    ex.pop('xstep', None)
    ex['note'] = note[:at] + mrbase.lay(ex).replace(mrbase._LAY, '')

    # ── ③ 页尾「短窗口图的起点与数据边界」那条逐图清单 ──────────────────────
    #    它是在 build() 里按裁剪**之前**的 xlabels 生成的，不改就会与图对不上。
    old_row = f'Exhibit {ex["n"]}（{ex["kind"]}）自 {lab_old} 起，{n_old} 格'
    hit = False
    for i, s in enumerate(payload['notes']):
        if old_row in s:
            payload['notes'][i] = s.replace(
                old_row,
                f'Exhibit {ex["n"]}（{ex["kind"]}）自 {ex["xlabels"][0]} 起，'
                f'{len(ex["xlabels"])} 格')
            hit = True
    if not hit:
        raise GucShellError(
            f'页尾逐图清单里找不到 {old_row!r} —— 底座那段措辞变了。'
            f'不改的话页尾会说 Ex{ex["n"]} 有 {n_old} 格，而图上只有 {len(ex["xlabels"])} 格。')

    # ── ④ 同一条页尾说明里那句「差出来的那几格全部是 lag」——**在本页不成立**。
    #    底座只认得 lag 这一种左端右移的原因（环比 1 个月、单月同比 12 个月……）；
    #    本页还有第二种：官方分部拆分的**源起点**（2017-01）比合并序列晚 12 个月。
    #    被它定住左端的有两张：本图（人工裁，见本文件抬头）与占比图
    #    （`stacked_dual`，`mrwin.resolve()` 自动裁）。不改这一句，页尾会把
    #    「源里没有」说成「lag 算不出来」—— 两者对读者的含义完全不同。
    seg_ex = [ex['n']] + [e['n'] for e in payload['exhibits']
                          if e.get('kind') == 'stacked_dual'
                          and (e.get('xlabels') or [None])[0] != payload['xlabels_long'][0]]
    old_clause = '差出来的那几格全部是 lag，不是缺数：'
    new_clause = (
        '差出来的那几格<b>除' + '、'.join(f'Exhibit {i}' for i in sorted(seg_ex))
        + f'外</b>全部是 lag，不是缺数（那两张的左端不是 lag 定的：'
        f'官方的 Turnkey／NRE &amp; Others <b>月度拆分自 {ex["xlabels"][0]} 才有</b>，'
        f'比合并营收晚 {k} 个月，两张图都只能从分部列真的有值的那一期起画 —— '
        f'理由与「差几格」写在它们各自的图注里）：')
    hit = False
    for i, s in enumerate(payload['notes']):
        if old_clause in s:
            payload['notes'][i] = s.replace(old_clause, new_clause)
            hit = True
    if not hit:
        raise GucShellError(
            f'页尾找不到 {old_clause!r} —— 底座那段措辞变了。不改的话页尾会把'
            f'「官方分部拆分只到 {ex["xlabels"][0]}」说成「lag 算不出来」。')
    return k, ex['xlabels'][0]


def main():
    who = mrbase.owned_elsewhere('guc')
    if who:
        print(f'[guc] 拒绝写入 data/：这一页目前由 {who} 负责。')
        return 2
    spec = mrbase.load_spec('guc')
    # 先让底座照常跑完（所有护栏、所有现算图注都在里面），产物落到 /dev/null 级的临时
    # 目录；本壳裁完之后再走同一个 `payload_guard.write_dash()` 写正式产物。
    # 这样 data/guc.js **只被写一次**，中途抛异常不会留下半成品。
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        payload = mrbase.build(spec, out_dir=tmp, quiet=True)
    k, at = _trim_stacked_bar(payload)
    if k:
        print(f'[guc] 月营收柱左端裁掉 {k} 格 → 自 {at} 起（分部列的起点；'
              f'其余各图自 {payload["xlabels_long"][0]} 起）')
    path = payload_guard.write_dash(os.path.join(mrbase.DATA, 'guc.js'), payload, 'guc')
    print(f'[guc] 窗口 {payload["xlabels_long"][0]} → {payload["xlabels_long"][-1]}'
          f'（{len(payload["xlabels_long"])} 个月）')
    print(f'[guc] {payload["headline"]}')
    print(f'[guc] 写出 {path} ({os.path.getsize(path) / 1024:.1f} KB)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
