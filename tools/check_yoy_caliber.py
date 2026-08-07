#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同比口径的自动判据 —— 扫 `data/*.js`，判每一张含同比的图口径对不对。

    python3 tools/check_yoy_caliber.py                    # 人读报告
    python3 tools/check_yoy_caliber.py --json out.json    # 顺带写机器可读结果
    python3 tools/check_yoy_caliber.py --page cme --verbose
    python3 tools/check_yoy_caliber.py --selftest         # 判据自测（见文件末）

退出码：有 🔴 → 1；只有 🟡 或全过 → 0。
`--json` 不给就**不写文件** —— 判据不往仓库里丢产物，免得 `git status` 长草。

## 为什么是独立脚本，而不是接进 build/payload_guard.py

`payload_guard` 被**每一个** builder import，写文件之前跑。现在（2026-08-07）有 10 个
agent 同时在改 builder，往那个文件里加规则，任何一个 bug 都会让 10 条构建同时炸，
而且炸在别人的改动上、排查成本全落在别人头上。所以先做成独立脚本，跑通、看清它在
真实 payload 上报什么，再接。**接进去的建议改法写在文件末尾 `HOW_TO_WIRE_IN`。**

## 它怎么知道一张图画的是哪种口径 —— 不看文字，回源复算

文字声明是**被检查的对象**，不能同时当证据。所以判据反过来做：

  1. 从 exhibit 的 `xlabels`（`Jul-26` / `7/26` / `2026-07`）解出月份；
  2. 把 `series/*.csv` 每一个数值列都按两种口径算一遍同比（`build/yoy.py` 的
     `mom_yoy` / `ttm_yoy_unchecked`），索引到月份上；
  3. 拿图上那条同比序列的**数值**去比对，命中哪一种口径就是哪一种。

比对的是数字不是名字，所以改标题骗不过它；反过来，凡是**派生量**的同比
（ADV × 交易日、多列相加、FX 换算过的）都匹配不上任何原始列 → 判为「未确定」，
**只计数不报错**。这是有意的：宁可漏报也不要制造噪声（本仓规矩）。

## 四条规则

  🔴 R1 未声明口径的单月同比，与它的滚动对应口径**符号相反**
       —— 读者没有任何线索知道这张图与隔壁那张为什么反向。
  🔴 R2 存量序列（OI / AUM / 市值 / 余额）的同比被**称作**「12 个月滚动合计」
       —— 数值恒等于滚动均值同比（没错），但「合计」对存量不指代任何真实的量。
  🟡 R3 同一张页里混用两种口径，而页尾「口径与方法说明」没有逐处点名。
  🟡 R4 用了单月同比但标题里没写明（CONTRACT.md §6 要求写进标题）。

R1/R2 只在口径**已确定**（回源复算命中）时才报 —— 判据自己拿不准就不喊。
"""
import argparse
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'build'))
import yoy as Y  # noqa: E402  —— 共享实现，口径只有这一份

# ── 判据参数（每一个都有理由，见下）──────────────────────────────────────────

# 回源比对的容差（百分点）。payload 里的同比是 Python 侧算完直接 json.dump 的
# 原始浮点，理论上应当逐位相等；给 0.02pp 是留给「先 round 再写」的少数生成器
# （0.02pp = 万分之二，比任何一家的展示精度都细）。给大了会开始误配到别的列上 ——
# 同比是尺度无关的，两条形状相近的序列很容易在 1pp 内互相冒充。
MATCH_TOL_PP = 0.02

# 至少要有这么多个月同时有值才认一次匹配。
# 6 的理由：一条 13 个月的窗口里，随便两条无关序列在 ≤6 个点上偶然对齐到 0.02pp
# 的概率可以忽略；再少（比如 3）就开始出现巧合匹配。实测把门槛从 6 降到 3，
# 匹配数只多 4 条，但其中 3 条的最佳匹配列明显与图题无关 —— 那是噪声不是覆盖。
MIN_MATCH_PTS = 6

# 判「符号相反」时忽略贴着零的读数：±0.5pp 以内的正负不是方向分歧，是舍入。
# 0.5pp 的来处：本仓同比的展示精度是 `pct0`（整数百分点）与 `pct1`（一位小数），
# 前者的舍入半径就是 0.5pp —— 图上印出来根本区分不了的差别，不该报成方向相反。
SIGN_DEADBAND_PP = 0.5

# 图型豁免（CONTRACT.md §6）：逐格波动就是题眼的图，不适用「默认滚动」。
EXEMPT_KINDS = {'heat_matrix', 'seasonality', 'qtr_bar', 'bridge_bar', 'range_band'}

# ── 结构性守卫：判据读得到哪些字段 ──────────────────────────────────────────
# 2026-08-07 修的那个盲区就死在这里：`yoy_series()` 只认六个字段，`grouped_bars`
# 的 `groups[]` 一个都没读过。整张图**静悄悄地**不进任何一条规则 —— 输出里既不报
# 违规，也不报「我没看」，看上去和「这页很干净」一模一样。
#
# 所以现在反过来做：不再维护「我会读哪些字段」，而是每张图逐字段问一句「你长得像
# 不像一条数据序列」，凡是像、而 `yoy_series()` 又没碰过的，**当成判据的缺陷报出来**。
# 下一次有人加一种 kind、带一个新字段名，判据会当场喊，而不是再瞎三个月。
_META_KEYS = {
    'n', 'kind', 'title', 'fmt', 'yfmt', 'label_fmt', 'ylab', 'ylab2', 'note',
    'src_extra', 'x', 'xlabels', 'xlabels_long', 'xstep', 'xrot', 'full', 'height',
    'legend', 'annot', 'zero_line', 'ycap', 'yfloor', 'cap_note', 'break_at',
    'break_label', 'bar_marks', 'mark_note', 'bar_labels', 'rows', 'cols', 'names',
    'row_head', 'row_lab_w', 'cell_h', 'reverse', 'highlight', 'avg12', 'avg_label',
    'yoy_txt', 'mom_txt', 'markers', 'zero_base', 'end_label', 'ovals_at_bottom',
    'net_color', 'actual_color', 'partial_months', 'qtr_months', 'qtd', 'qtd_at',
    'caliber', 'caliber_src', 'color',
}

# `yoy_series()` 声称自己读过的字段。两者对不上就是判据的盲区。
SCANNED_FIELDS = {'yoy', 'line', 'bar', 'series', 'stacks', 'values',
                  'groups', 'net', 'base', 'actual', 'lo', 'hi', 'matrix'}


def data_like_keys(ex):
    """这个 exhibit 上「长得像一条数据序列」的字段名（不看白名单，看形状）。

    三种形状算数：裸数值列表、`{'values': [...]}`、`[{'values': [...]}, ...]`；
    外加 `matrix` 的二维表。`xlabels` / `break_at` / `rows` 这些排版字段先按名字排除
    —— 它们也是列表，但不承载被判的量。
    """
    def numeric_list(v):
        return (isinstance(v, list) and len(v) >= MIN_MATCH_PTS
                and any(isinstance(x, (int, float)) and not isinstance(x, bool)
                        for x in v))

    out = set()
    for k, v in (ex or {}).items():
        if k in _META_KEYS:
            continue
        if numeric_list(v):
            out.add(k)
        elif isinstance(v, dict) and isinstance(v.get('values'), list):
            out.add(k)
        elif (isinstance(v, list) and v
              and all(isinstance(x, dict) and isinstance(x.get('values'), list)
                      for x in v)):
            out.add(k)
        elif isinstance(v, list) and v and all(isinstance(x, list) for x in v):
            out.add(k)                      # heat_matrix 的 matrix[][]
    return out

# ── 文字识别 ────────────────────────────────────────────────────────────────
# 「这条序列是不是同比」只看**结构位**（名字 / 轴标题 / 图题 / 图例 / 数值格式），
# 不看 note —— note 里提一句「同比」不代表这条线是同比，那样会把一堆水平值图
# 误判进来。note 只用来判「有没有声明口径」。
_IS_YOY = re.compile(r'y\s*/\s*y|yoy|同比|变化率|growth\s*%|% *chg', re.I)
_ROLL_DECL = re.compile(
    r'12\s*个月滚动|滚动合计|滚动同比|12M\s*滚动|\bTTM\b|12M\s*roll|'
    r'12[-\s]?month\s+rolling|rolling\s+12', re.I)
_MOM_DECL = re.compile(
    r'单月同比|单月口径|单月[的]?[y／/]|single[-\s]?month|单月|'
    # 描述式声明也算「声明过」—— 页面用大白话把口径说清楚了，只是没用契约的
    # 关键词。这类降级到 R4（标题里没写明），不进 R1（完全没线索）。
    r'同月对去年同月|当月对去年同月|与去年同月相比|水平值同比|点对点同比', re.I)

# 「滚动**合计**」与「滚动**均值**」在算术上给出同一个数（Σ12/Σ12′ ≡ 均值比，
# 除数约掉），但对存量只有后者是真话：12 个月末市值相加不指代任何真实的量。
# 所以 R2 判的是**措辞**，两个正则必须分开。
_ROLL_SUM_DECL = re.compile(r'滚动合计|合计的同比|rolling\s+sum|12\s*个月合计|TTM\s*sum', re.I)
_ROLL_MEAN_DECL = re.compile(r'滚动均值|滚动平均|rolling\s+(average|mean)|均值的同比', re.I)

# 「这张图画的是存量」的文字标记。本仓的图题已经在自报了（`（存量，期末口径）`、
# `Month-end total open interest`），所以这是**页面自己的声明**，不是我猜的。
# 用途有两个，方向相反：
#   · 存量 → R1（单月同比该不该报）整条豁免，因为点对点同比正是存量的合法口径；
#   · 存量 → R2（被做成滚动合计）加一道确认，避免只凭列名正则就下硬结论。
_STOCK_TXT = re.compile(
    r'存量|期末口径|月末|期末|未平仓|市值|托管资产|在外量|余额|'
    r'month-?end|end[-\s]?of[-\s]?period|open interest|outstanding|'
    r'market cap|assets under', re.I)

# 列名本身就无歧义的存量前缀 —— 这几个不需要文字确认也能下 R2 的硬结论。
# 与「需要文字确认」的那些（accounts / listed_ / advisors / holdings）区别在于：
# 这些词在本仓 500+ 列里**没有一个**是流量，而 accounts 就有反例
# （`new_brokerage_accounts_k` 是当月新开户数，是流量）。
_STOCK_UNAMBIGUOUS = re.compile(
    r'(^|_)(oi|aum|auc|mktcap)(_|$)|open_interest|open_notional|'
    r'_balances?(_|$)|outstanding', re.I)


def _txt(*xs):
    return ' '.join(str(x) for x in xs if x)


# ── 月份标签 ────────────────────────────────────────────────────────────────
_MON = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}


def lab2month(s):
    """`Jul-26` / `7/26` / `2026-07` → `'2026-07'`；其它（季度标签 `2023Q1`、
    seasonality 的 `Jan`、横截面的公司名）→ None，那些图本来就不进这个判据。"""
    s = str(s).strip()
    m = re.fullmatch(r'([A-Z][a-z]{2})-(\d{2})', s)
    if m:
        return f'20{m.group(2)}-{_MON[m.group(1)]:02d}'
    m = re.fullmatch(r'(\d{1,2})/(\d{2})', s)
    if m:
        return f'20{m.group(2)}-{int(m.group(1)):02d}'
    if re.fullmatch(r'\d{4}-\d{2}', s):
        return s
    return None


# ── 回源：把 series/*.csv 每一列的两种口径预算一遍 ────────────────────────────
def build_index(root):
    """{(csv, col): {'kind', 'mom', 'ttm', 'mompp'}}。约 580 列、耗时 <1s。

    `ttm` 走 `yoy.ttm_yoy_unchecked` —— 对**存量列也算**。这不是违反口径规矩，
    恰恰相反：只有把存量列的滚动同比也算出来，才能判断「有没有人把存量做成了
    滚动合计」（R2 要报的就是这个）。
    """
    keys, meta, frames = [], {}, {'mom': [], 'ttm': [], 'mompp': []}
    for f in sorted(glob.glob(os.path.join(root, 'series', '*.csv'))):
        try:
            head = open(f, encoding='utf-8').readline().strip().split(',')
            if 'month' not in head:
                continue
            df = pd.read_csv(f)
        except Exception:
            continue
        df = df.set_index('month').sort_index()
        df = df[~df.index.duplicated(keep='last')]
        for c in df.columns:
            s = pd.to_numeric(df[c], errors='coerce')
            if np.isfinite(s.values.astype(float)).sum() < 15:
                continue
            k = (os.path.basename(f), c)
            keys.append(k)
            # `classify()` 的最后一行是 `return STOCK  # 拿不准判存量`。对生成器那是
            # 安全的默认（少画一条线），但在**判据**里方向正好相反：kind==STOCK 会让
            # legal_mom 成立，把 R1/R4 整条关掉 —— 一个「我不知道」被当成了「它合法」。
            # 所以这里记下这次分类到底是**正则命中**还是**兜底猜的**，好把后者单列出来。
            classified = bool(Y._RATIO_PAT.search(c) or Y._NEW_FLOW_PAT.search(c)
                              or Y._STOCK_PAT.search(c) or Y._FLOW_PAT.search(c))
            meta[k] = {'kind': Y.classify(c),
                       'kind_fallback': not classified,
                       'strong_stock': bool(Y._STOCK_PAT.search(c))
                                       and not Y._NEW_FLOW_PAT.search(c),
                       'unambiguous_stock': bool(_STOCK_UNAMBIGUOUS.search(c))}
            frames['mom'].append(Y.mom_yoy(s, Y.FLOW).rename(k))
            frames['ttm'].append(Y.ttm_yoy_unchecked(s).rename(k))
            frames['mompp'].append(Y.mom_yoy(s, Y.RATIO).rename(k))
    # 一次性拼成三张宽表（月 × 列）。identify() 因此只需一次 reindex + 一次
    # 向量化比对，而不是「239 条 × 580 列 × 3 口径」次 pandas 调用 —— 15s → <1s。
    return {'keys': keys, 'meta': meta,
            'mat': {k: pd.concat(v, axis=1).sort_index() for k, v in frames.items()}}


def identify(values, months, idx):
    """拿图上的同比数值回源复算，判它是哪种口径。

    返回 {'caliber': 'mom'|'ttm'|None, 'col', 'csv', 'kind', 'err', 'n',
          'ambiguous': bool, 'alts': [...]}。
    caliber=None 表示**没判出来**（派生量、跨源合成、或历史太短）—— 不报错。
    """
    pairs = [(m, float(v)) for m, v in zip(months, values)
             if m and v is not None and isinstance(v, (int, float))
             and np.isfinite(float(v))]
    out = {'caliber': None, 'col': None, 'csv': None, 'kind': None, 'err': None,
           'n': len(pairs), 'ambiguous': False, 'strong_stock': False,
           'unambiguous_stock': False, 'kind_fallback': False, 'alts': []}
    if len(pairs) < MIN_MATCH_PTS:
        return out
    ms = [m for m, _ in pairs]
    want = np.array([v for _, v in pairs])[:, None]

    hits = []
    for cal, key in (('mom', 'mom'), ('ttm', 'ttm'), ('mom', 'mompp')):
        got = idx['mat'][key].reindex(ms).values.astype(float)
        # 只在「窗口内每个月都有值」的列上比 —— 缺一个月就没法确认口径，
        # 拿 nanmax 去凑会把一条只重叠 2 个月的列当成命中。
        ok = np.isfinite(got).all(axis=0)
        err = np.full(got.shape[1], np.inf)
        if ok.any():
            err[ok] = np.abs(got[:, ok] - want).max(axis=0)
        for j in np.flatnonzero(err <= MATCH_TOL_PP):
            hits.append((float(err[j]), cal, idx['keys'][j], key == 'mompp'))
    if not hits:
        return out
    hits.sort(key=lambda t: t[0])
    err, cal, k, is_pp = hits[0]
    cals = {h[1] for h in hits}
    out.update(caliber=cal, csv=k[0], col=k[1], err=err, pp=is_pp, **idx['meta'][k],
               # 同一条同比可能同时命中多列（同比是尺度无关的，一列和它的换算列
               # 读数完全一样）。只要命中的**口径**唯一，就不算歧义 —— 我们要判的
               # 是口径不是列名。口径都不唯一才是真拿不准，那就不下结论。
               ambiguous=len(cals) > 1)
    out['alts'] = sorted({(h[2][0], h[2][1], h[1]) for h in hits[:8]})
    if len(cals) > 1:
        out['caliber'] = None
    return out


# ── payload 遍历 ────────────────────────────────────────────────────────────
def load_page(path):
    s = open(path, encoding='utf-8').read()
    i = s.index('window.DASH =')
    j = s.rindex(';')
    return json.loads(s[i + len('window.DASH ='):j])


def page_months(payload, ex):
    """这张图的 x 轴月份。优先图自己的 xlabels，其次按 `x` 字段取页级标签。"""
    xl = ex.get('xlabels') or (payload.get('xlabels_long') if ex.get('x') == 'long'
                               else payload.get('xlabels')) or []
    return [lab2month(x) for x in xl]


def heat_series(ex):
    """`heat_matrix` 的 `matrix[][]` 摊平成「序列 + 它自己的月份轴」。

    两种排版都在用，必须分开处理 —— 认错一种就会把值和月份错位对齐：

      A. **列是月标签**（`cols=['Jul-24', …]`，行是不同标的，如 exchanges-eu Ex13）
         → 一行一条序列，月份取自 `cols`。
      B. **行是年、列是月名**（`rows=['2017', …]`, `cols=['Jan', …]`，如 cme Ex18）
         → 整张矩阵在日历上本来就是一条连续序列，摊平成一条（最多 120 个点，
            比逐行 12 个点更容易在回源里认出口径）。

    两种都不是（季度矩阵 exchanges-apac Ex7 的 `cols=['3Q20', …]`）→ 返回空。
    这是**真的读不出月份**，与「没写代码去读」是两件事，census 里分开记。
    """
    mat = ex.get('matrix')
    if not isinstance(mat, list) or not mat:
        return []
    rows = ex.get('rows') or []
    cols = ex.get('cols') or list(_MON)          # 缺省 Jan..Dec（hkex Ex17 就没给）

    col_m = [lab2month(c) for c in cols]
    if any(col_m):                                # 排版 A
        out = []
        for i, r in enumerate(mat):
            if isinstance(r, list) and len(r) >= MIN_MATCH_PTS:
                nm = str(rows[i]) if i < len(rows) else f'row{i}'
                out.append((nm, list(r), col_m))
        return out

    idx = [_MON.get(str(c).strip()[:3].title()) for c in cols]   # 排版 B
    if not cols or not all(idx):
        return []
    flat_m, flat_v = [], []
    for i, r in enumerate(mat):
        y = str(rows[i]).strip() if i < len(rows) else ''
        if not re.fullmatch(r'\d{4}', y) or not isinstance(r, list):
            return []
        for j, v in enumerate(r[:len(idx)]):
            flat_m.append(f'{y}-{idx[j]:02d}')
            flat_v.append(v)
    return [(str(ex.get('legend') or ''), flat_v, flat_m)] if len(flat_v) >= MIN_MATCH_PTS else []


def yoy_series(ex):
    """从一个 exhibit 里挑出「画的是同比」的那些序列。

    只认结构位上的证据（序列名 / 该序列所在轴的轴标题 / 图题 / 图例 / yfmt），
    因为「有没有在文字里声明口径」是被检查项，不能拿来当识别依据。

    返回的每条可带 `months` —— 该序列**自己的**月份轴（目前只有 `heat_matrix` 需要，
    它不吃 `xlabels`，月份藏在 `rows`×`cols` 里）。不给就用页/图的 `xlabels`。
    """
    title, ylab, ylab2 = ex.get('title', ''), ex.get('ylab', ''), ex.get('ylab2', '')
    found = []

    def take(obj, where, axis_lab, name_hint=None, months=None, force=False):
        # 裸列表形态（range_band 的 lo/hi/actual 是 `[…]` 而不是 `{values: […]}`）
        if isinstance(obj, list):
            obj = {'values': obj}
        if not isinstance(obj, dict):
            return
        vals = obj.get('values')
        if not isinstance(vals, list) or len(vals) < MIN_MATCH_PTS:
            return
        nm = obj.get('name') or name_hint or ''
        sig = _txt(nm, obj.get('legend'), axis_lab, obj.get('yfmt'))
        # 次轴序列（yoy / line）默认继承 ylab2；只有主轴序列才需要图题来判定。
        # force=True 只给 heat_matrix 用：那种图的口径写在图级签名上，行标签是标的名
        # （'Euronext'）或年份（'2017'），拿行标签去搜「同比」永远搜不到。
        if force or _IS_YOY.search(sig) or (not nm and _IS_YOY.search(_txt(title, axis_lab))):
            found.append({'where': where, 'name': nm or ex.get('legend') or '',
                          'values': vals, 'yfmt': obj.get('yfmt'), 'months': months})

    take(ex.get('yoy'), 'yoy', ylab2)                    # gs_bar 的次轴金线
    take(ex.get('line'), 'line', ylab2 or ylab)          # bar_line_dual / stacked_dual / grouped_bars 的误差线
    take(ex.get('bar'), 'bar', ylab)
    for i, s in enumerate(ex.get('series') or []):
        take(s, f'series[{i}]', ylab)
    for i, s in enumerate(ex.get('stacks') or []):
        take(s, f'stacks[{i}]', ylab)

    # ── 以下五类曾经一条都没读过（2026-08-07 补）────────────────────────────
    # grouped_bars 的并排柱。**这一类不在豁免名单里**，所以补上之后是真的会进
    # R1/R3/R4 —— 全站 38 张 grouped_bars 里有一批标题就写着「：同比」。
    for i, g in enumerate(ex.get('groups') or []):
        take(g, f'groups[{i}]', ylab)

    take(ex.get('net'), 'net', ylab)                     # bridge_bar 的净额菱形
    take(ex.get('base'), 'base', ylab)                   # seasonality 的同月常态灰柱
    take(ex.get('actual'), 'actual', ylab,               # seasonality 蓝柱 / range_band 菱形
         name_hint=(ex.get('names') or {}).get('actual'))
    for f in ('lo', 'hi'):                               # range_band 的区间上下缘
        take(ex.get(f), f, ylab, name_hint=(ex.get('names') or {}).get(f))

    # heat_matrix：一整张图只有一个口径，语义写在图题/图例上而不是行标签上
    # （行标签是标的名 'Euronext'、或年份 '2017'），所以这里查的是**图级**签名。
    if _IS_YOY.search(_txt(ex.get('legend'), title, ylab)):
        for nm, vals, mm in heat_series(ex):
            take({'name': nm, 'values': vals}, 'matrix', ylab,
                 name_hint=nm or ex.get('legend'), months=mm, force=True)

    if isinstance(ex.get('values'), list) and _IS_YOY.search(_txt(title, ylab, ex.get('legend'))):
        found.append({'where': 'values', 'name': ex.get('legend') or '',
                      'values': ex['values'], 'yfmt': ex.get('yfmt'), 'months': None})
    return found


def declarations(ex, s):
    """这条同比在文字里声明了什么口径。分「标题里」与「任意位置」两级 ——
    CONTRACT.md §6 要求单月口径写进**标题**，图注补理由。"""
    title = _txt(ex.get('title'), s['name'], ex.get('ylab2'), ex.get('legend'))
    body = _txt(title, ex.get('note'), ex.get('src_extra'), ex.get('ylab'), ex.get('annot'))
    return {
        'roll_in_title': bool(_ROLL_DECL.search(title)),
        'mom_in_title': bool(_MOM_DECL.search(title)),
        'roll_anywhere': bool(_ROLL_DECL.search(body)),
        'mom_anywhere': bool(_MOM_DECL.search(body)),
        'sum_wording': bool(_ROLL_SUM_DECL.search(body)),
        'mean_wording': bool(_ROLL_MEAN_DECL.search(body)),
    }


# ── 规则 ────────────────────────────────────────────────────────────────────
def check_page(path, idx):
    return check_payload(load_page(path), os.path.basename(path)[:-3], idx)


def check_payload(payload, page, idx):
    findings, items, census = [], [], []

    for ex in payload.get('exhibits') or []:
        n, kind_, title = ex.get('n'), ex.get('kind'), ex.get('title', '')
        months = page_months(payload, ex)
        exempt = kind_ in EXEMPT_KINDS
        # 这张图是不是存量图 —— 用**页面自己写的**标记判，不是靠列名正则猜
        says_stock = bool(_STOCK_TXT.search(_txt(title, ex.get('ylab'), ex.get('legend'))))

        found = yoy_series(ex)
        # 逐张图记账，**与「找到几条同比序列」无关**。老版本只在找到序列时才记，
        # 于是「豁免图型 N 条」统计的是「豁免图里被读到的序列数」而不是豁免图数量；
        # 一张图一条都没读到时，它在输出里彻底不存在 —— 失明长得和干净一模一样。
        census.append({'page': page, 'n': n, 'kind': kind_, 'title': title,
                       'exempt': exempt, 'n_series': len(found),
                       'blind': sorted(data_like_keys(ex) - SCANNED_FIELDS)})

        for s in found:
            d = declarations(ex, s)
            # heat_matrix 的月份藏在 rows×cols 里，不在 xlabels 上，所以序列可自带月份轴
            ms = s.get('months') or months
            m = identify(s['values'], ms, idx)
            is_stock = says_stock or m['kind'] == Y.STOCK or m['unambiguous_stock']
            is_ratio = m['kind'] == Y.RATIO or m.get('pp')
            # 「单月是这条序列唯一合法的口径」—— 存量（点对点）与比率（百分点差）。
            # 对这两类报「你怎么不用滚动」是把规矩用反了，全部规则一律豁免。
            # 实测这一条挡掉 4 个误报：ice Ex12/15 的 RPC、sgx Ex9 换手率、
            # axp Ex8 excess spread —— 它们的滚动同比在数学上根本不存在。
            legal_mom = is_stock or is_ratio
            # 这条豁免是**猜**出来的吗 —— 存量身份既没有列名正则支持、页面也没自称
            # 存量，只是 classify() 的兜底返回了 STOCK。这种豁免会静默关掉 R1/R4，
            # 与「判据读不到这个字段」是同一类失明，所以也要在输出里露头。
            weak_exempt = bool(legal_mom and m['caliber'] == 'mom' and not is_ratio
                               and m.get('kind_fallback') and not says_stock
                               and not m['unambiguous_stock'] and not m['strong_stock'])
            # 只有「拿掉这条豁免就真会响一条规则」的才值得人工看 —— 其余那些图早就
            # 在标题里写了单月，豁免与否结果一样，列出来只是噪声。
            hidden = ''
            if weak_exempt:
                if not (d['roll_anywhere'] or d['mom_anywhere']) and sign_flips(m, ms):
                    hidden = 'R1'
                elif not d['mom_in_title']:
                    hidden = 'R4'
            it_hidden = hidden
            it = {'page': page, 'n': n, 'chart_kind': kind_, 'title': title,
                  'where': s['where'], 'name': s['name'], 'exempt': exempt,
                  'says_stock': says_stock, 'is_stock': is_stock,
                  'is_ratio': is_ratio, 'legal_mom': legal_mom,
                  'weak_exempt': weak_exempt, 'hidden_rule': it_hidden,
                  'declared': d, 'match': {k: v for k, v in m.items() if k != 'alts'},
                  'alts': m.get('alts', [])}
            items.append(it)
            if exempt:
                continue

            declared_any = d['roll_anywhere'] or d['mom_anywhere']

            # R2 存量被称作「滚动合计」。先判这条，它比 R1 更硬（图在说一句关于
            # 自己算术的假话）。三个条件同时成立才报，逐条都是为了压噪声：
            #   ① 列名正则命中存量，**且**（列名无歧义 或 图题自己说是存量）——
            #      只凭列名会误伤 `new_brokerage_accounts_k`（当月新开户数是流量，
            #      名字里却有 accounts）；
            #   ② 文字里确实写了「滚动**合计**」。写「滚动均值」的不报 ——
            #      对存量那是正确说法，而且**数值完全一样**（Σ12/Σ12′ ≡ 均值比，
            #      实测 hkex 市值两者差 2.3e-14）。这条判据判的是措辞，不是数字。
            if m['caliber'] == 'ttm' and m['strong_stock'] \
                    and (m['unambiguous_stock'] or says_stock) \
                    and d['sum_wording'] and not d['mean_wording']:
                findings.append(dict(
                    lvl='🔴', rule='R2_stock_called_rolling_sum', page=page, n=n, title=title,
                    msg=(f'{s["where"]}「{s["name"]}」回源命中**存量列** '
                         f'{m["csv"]}:{m["col"]}，而图上/图注把这条线称作'
                         f'「12 个月滚动**合计**的同比」。数值本身没错 —— 12 个月合计比'
                         f'恒等于 12 个月均值比 —— 但对存量，「合计」（12 个月末快照相加）'
                         f'不指代任何真实的量，那是一句关于自己算术的假话。'
                         f'改称「12 个月滚动**均值**同比」（= 去年一整年的平均水平 vs '
                         f'前一年），或改用点对点同比。函数走 yoy.ttm_mean_yoy()。')))
                continue

            # R1 未声明口径的单月同比，且与滚动口径符号相反。
            # **存量与比率整条豁免**（legal_mom）：点对点／百分点差正是它们唯一
            # 合法的口径，对它们报「你怎么不用滚动」是把规矩用反了
            # （asx Ex26 月末未平仓名义额、enx Ex34 挂牌基金只数 —— 标题自己就写着
            # 「存量，期末口径」）。
            if m['caliber'] == 'mom' and not legal_mom and not declared_any:
                flips = sign_flips(m, ms)
                if flips:
                    ex_txt = '；'.join(f'{mm} 单月 {a:+.1f}% vs 滚动 {b:+.1f}%'
                                      for mm, a, b in flips[:3])
                    findings.append(dict(
                        lvl='🔴', rule='R1_undeclared_mom_sign_flip', page=page, n=n,
                        title=title,
                        msg=(f'{s["where"]}「{s["name"]}」画的是**单月同比**（回源命中 '
                             f'{m["csv"]}:{m["col"]}），标题与图注都没声明口径，'
                             f'而窗口内有 {len(flips)} 个月与 12 个月滚动口径**符号相反**：'
                             f'{ex_txt}。'),
                        flips=[[mm, a, b] for mm, a, b in flips]))
                    continue

            # R4 用了单月但标题没写明（存量 / 比率同样豁免，理由同 R1）
            if (m['caliber'] == 'mom' or (d['mom_anywhere'] and not d['roll_anywhere'])) \
                    and not legal_mom and not d['mom_in_title']:
                findings.append(dict(
                    lvl='🟡', rule='R4_mom_not_in_title', page=page, n=n, title=title,
                    msg=(f'{s["where"]}「{s["name"]}」是单月同比'
                         + (f'（回源命中 {m["csv"]}:{m["col"]}）' if m['caliber'] else '（据图注）')
                         + '，但标题里没有「单月 / single-month」。'
                           'CONTRACT.md §6：要用单月同比必须在标题里写明。')))

    findings += check_page_mix(payload, page, items)
    return findings, items, census


def sign_flips(m, months):
    """这条单月同比与它的滚动对应口径，在窗口内哪些月符号相反。

    死区 ±SIGN_DEADBAND_PP：贴着零的正负是舍入不是方向分歧，报出来是噪声。
    """
    k = (m['csv'], m['col'])
    if k not in _IDX['meta']:
        return []
    ms = [x for x in months if x]
    a = _IDX['mat']['mom'][k].reindex(ms).values.astype(float)
    b = _IDX['mat']['ttm'][k].reindex(ms).values.astype(float)
    out = []
    for i, mm in enumerate(ms):
        if not (np.isfinite(a[i]) and np.isfinite(b[i])):
            continue
        if abs(a[i]) < SIGN_DEADBAND_PP or abs(b[i]) < SIGN_DEADBAND_PP:
            continue
        if a[i] * b[i] < 0:
            out.append((mm, float(a[i]), float(b[i])))
    return out


def check_page_mix(payload, page, items):
    """R3：同页混用口径而页尾「口径与方法说明」没有逐处点名。

    「点名」= notes 里某一条**同时**提到口径关键词和 `Exhibit N`（或 `Ex N`）。
    只要求点名少数派那一侧（单月），因为契约的默认是滚动 —— 默认口径不需要逐张点名，
    偏离默认的才需要。这样判据不会因为一页有 20 张滚动图就喊 20 次。
    """
    mom_ns, ttm_ns = set(), set()
    for it in items:
        # 存量 / 比率不进「混用口径」的分子：它们的口径是被数学定死的，不是一个选择。
        # 一页上有几张 OI 图就喊一次「你混用口径」，那是噪声不是信号。
        if it['exempt'] or it['legal_mom']:
            continue
        c = it['match']['caliber'] or (
            'mom' if it['declared']['mom_anywhere'] and not it['declared']['roll_anywhere']
            else 'ttm' if it['declared']['roll_anywhere'] else None)
        if c == 'mom':
            mom_ns.add(it['n'])
        elif c == 'ttm':
            ttm_ns.add(it['n'])
    if not (mom_ns and ttm_ns):
        return []
    notes = [x for x in (payload.get('notes') or [])
             if _MOM_DECL.search(str(x)) or _ROLL_DECL.search(str(x))]
    named = set()
    for x in notes:
        for k in re.findall(r'(?:Exhibit|Ex\.?)\s*(\d+)', str(x)):
            named.add(int(k))
    missing = sorted(n for n in mom_ns if n not in named)
    if not missing:
        return []
    return [dict(lvl='🟡', rule='R3_mixed_caliber_unnamed', page=page, n=None,
                 title='（页尾口径与方法说明）',
                 msg=(f'本页混用两种同比口径：单月 Exhibit {sorted(mom_ns)}、'
                      f'滚动 Exhibit {sorted(ttm_ns)}；'
                      f'但口径说明里没有点名 Exhibit {missing}。'
                      f'CONTRACT.md §6：同页并存两种口径必须在口径说明里逐处点名。'),
                 missing=missing, mom=sorted(mom_ns), ttm=sorted(ttm_ns))]


# ── 判据自测：证明四条规则都还活着 ───────────────────────────────────────────
def selftest(idx):
    """用真实序列拼出四张**故意写错**的假图，逐条确认规则会响。

    为什么需要这个：判据在真实快照上的命中数会随页面被修好而归零
    （实测 hkex Ex8 就在本次开发过程中被另一个 agent 改对了，R2 当场从 1 变 0）。
    「今天没报错」和「规则坏了」在输出上长得一模一样 —— 只有对着已知的错例跑一遍
    才能分开这两件事。这是判据的判据。
    """
    def yoy_ex(n, csv, col, cal, months, **kw):
        k = (csv, col)
        v = idx['mat'][cal][k].reindex(months)
        ex = {'n': n, 'kind': 'gs_bar', 'fmt': 'f1',
              'xlabels': [f'{["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m[5:7]) - 1]}-{m[2:4]}' for m in months],
              'values': [1.0] * len(months),
              'yoy': {'name': kw.pop('yname', 'y/y (RHS)'), 'color': 'GOLD',
                      'yfmt': 'pct0',
                      'values': [None if not np.isfinite(x) else float(x) for x in v]}}
        ex.update(kw)
        return ex

    ms = sorted(set(idx['mat']['mom'].index))[-40:]
    cases = []

    # R1：流量 + 单月 + 一句口径都没写 + 与滚动符号相反
    w = [m for m in ms if np.isfinite(idx['mat']['mom'][('sgx.csv', 'sec_turnover_sgdmn')].get(m, np.nan))][-25:]
    cases.append(('R1_undeclared_mom_sign_flip', {
        'exhibits': [yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                            title='证券市场成交：当月成交额', note='柱是当月成交额。')],
        'notes': []}))

    # R2：存量 + 滚动窗口同比 + 文字自称「滚动合计」
    w2 = [m for m in ms if np.isfinite(idx['mat']['ttm'][('hkex.csv', 'mktcap_hkdtn')].get(m, np.nan))][-13:]
    cases.append(('R2_stock_called_rolling_sum', {
        'exhibits': [yoy_ex(8, 'hkex.csv', 'mktcap_hkdtn', 'ttm', w2,
                            title='Securities market capitalisation',
                            yname='12M rolling y/y (RHS)',
                            note='次轴 = 12 个月滚动合计的同比（最近 12 个月合计 ÷ 上一个 12 个月合计 − 1）。')],
        'notes': []}))

    # R3：同页两种口径，页尾口径说明没点名单月那张
    cases.append(('R3_mixed_caliber_unnamed', {
        'exhibits': [
            yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                   title='当月成交额（单月同比）', note='本图用单月同比。'),
            yoy_ex(3, 'hkex.csv', 'adt_hkdbn', 'ttm',
                   [m for m in ms if np.isfinite(idx['mat']['ttm'][('hkex.csv', 'adt_hkdbn')].get(m, np.nan))][-13:],
                   title='现货 ADT（12 个月滚动合计同比）', note='12 个月滚动合计同比。')],
        'notes': ['<b>同比口径。</b>本页混用单月与 12 个月滚动合计两种口径。']}))

    # R4：单月，图注声明了但标题里没写
    cases.append(('R4_mom_not_in_title', {
        'exhibits': [yoy_ex(2, 'sgx.csv', 'sec_turnover_sgdmn', 'mom', w,
                            title='证券市场成交：当月成交额',
                            note='次轴是单月同比，因为本图讲的就是单月的事。')],
        'notes': []}))

    print('判据自测 —— 对着已知错例跑，确认规则没死')
    ok = True
    for want, payload in cases:
        payload = dict(payload, xlabels=payload['exhibits'][0]['xlabels'])
        f, _, _ = check_payload(payload, '_selftest', idx)
        rules = [x['rule'] for x in f]
        hit = want in rules
        ok &= hit
        print(f'  {"✅" if hit else "❌"} {want:34s} 实报 {rules or "（无）"}')
    print('  判据自测' + ('通过' if ok else '**失败** —— 有规则不再触发，先修判据再看报告'))
    return 0 if ok else 1


# ── 报告 ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='同比口径判据（CONTRACT.md §6）')
    ap.add_argument('--root', default=_ROOT)
    ap.add_argument('--page', action='append', help='只查某几页（不带 .js）')
    ap.add_argument('--json', help='机器可读结果写到这个路径；不给就不写文件'
                                   '（默认不往仓库里丢产物）。`-` = 打到 stdout')
    ap.add_argument('--verbose', action='store_true', help='逐条列出口径未确定的图')
    ap.add_argument('--selftest', action='store_true',
                    help='只跑判据自测（对着已知错例确认四条规则都还会响），不扫 data/')
    a = ap.parse_args()

    global _IDX
    _IDX = build_index(a.root)
    if a.selftest:
        return selftest(_IDX)

    paths = sorted(glob.glob(os.path.join(a.root, 'data', '*.js')))
    paths = [p for p in paths if not p.endswith('roster.js')]  # 首页索引，无 exhibits
    if a.page:
        want = set(a.page)
        paths = [p for p in paths if os.path.basename(p)[:-3] in want]

    allf, alli, allc = [], [], []
    for p in paths:
        try:
            f, i, c = check_page(p, _IDX)
        except Exception as e:                    # 一页坏掉不该拖垮整次扫描
            allf.append(dict(lvl='🟡', rule='R0_page_unreadable', page=os.path.basename(p),
                             n=None, title='', msg=f'读不出来：{type(e).__name__}: {e}'))
            continue
        allf += f
        alli += i
        allc += c

    red = [x for x in allf if x['lvl'] == '🔴']
    yel = [x for x in allf if x['lvl'] == '🟡']
    live = [x for x in alli if not x['exempt']]
    det = [x for x in live if x['match']['caliber']]
    print('=' * 86)
    print('同比口径判据 —— data/*.js 快照')
    print('=' * 86)

    # ── 图数量的账，按 exhibit 记（不是按「读到了几条序列」记）─────────────────
    # 这三行是 2026-08-07 补的。老版本只有「同比序列 N 条（豁免 M 条）」一行，
    # 而 M 是**豁免图里被读到的序列数** —— 一张图一条都没读到时它就凭空消失了，
    # 于是「判据没读」被印成了「豁免 0 条」。现在豁免 / 读到 / 没读到分三栏印。
    ex_all, ex_ex = len(allc), [c for c in allc if c['exempt']]
    ex_ex_read = [c for c in ex_ex if c['n_series']]
    ex_kinds = {}
    for c in ex_ex:
        ex_kinds.setdefault(c['kind'], [0, 0])
        ex_kinds[c['kind']][0] += 1
        ex_kinds[c['kind']][1] += bool(c['n_series'])
    blind = [c for c in allc if c['blind']]
    print(f'页 {len(paths)} 张；exhibit {ex_all} 张，其中豁免图型 {len(ex_ex)} 张'
          f'（{" / ".join(f"{k} {v[0]}" for k, v in sorted(ex_kinds.items()))}）')
    print(f'  └ 豁免图里读出同比序列的 {len(ex_ex_read)} 张、'
          f'一条也读不出的 {len(ex_ex) - len(ex_ex_read)} 张'
          f'（横轴不是月，回源无从对齐 —— 与「判据不认识这个字段」不是一回事）')
    print(f'同比序列 {len(alli)} 条（豁免图型 {len(alli) - len(live)} 条，只计数不判规则）')
    print(f'口径回源确定 {len(det)} 条'
          f'（滚动 {sum(1 for x in det if x["match"]["caliber"] == "ttm")} / '
          f'单月 {sum(1 for x in det if x["match"]["caliber"] == "mom")}）；'
          f'未确定 {len(live) - len(det)} 条 —— 派生量 / 跨源合成，判据不下结论')
    if blind:
        print(f'\n⚠ 判据读不到的数据字段 {len(blind)} 张图 —— **这是判据自己的缺陷，'
              f'不是页面的问题**，先补 yoy_series() 再看下面的结论：')
        for c in blind[:20]:
            print(f'    {c["page"]} Ex{c["n"]}（{c["kind"]}）未扫描字段 {c["blind"]} '
                  f'— {c["title"][:48]}')
    else:
        print('判据未扫描到的数据字段：0 —— 每张图上长得像数据序列的字段都进过 yoy_series()')

    # 「因为判据猜它是存量而被关掉 R1/R4」的单月同比。不计入 🔴/🟡（判据自己拿不准
    # 就不该硬判），但必须印出来 —— 否则它和「这张图合规」在输出上又长得一样了。
    weak = [x for x in live if x.get('weak_exempt')]
    hid = [x for x in weak if x.get('hidden_rule')]
    if weak:
        print(f'\n⚠ 单月同比被「判据猜它是存量」挡掉 R1/R4 的 {len(weak)} 条 —— '
              f'yoy.classify() 对这些列名四条正则一条都没命中，走的是最后一行的兜底 '
              f'`return STOCK`。对生成器那是安全默认，在判据里方向相反：'
              f'一个「我不知道」被当成了「它合法」。')
        print(f'  其中 {len(hid)} 条一旦确认是流量就会当场变成违规'
              f'（其余 {len(weak) - len(hid)} 条标题里已写明单月，豁免与否结果一样）：')
        for x in hid:
            print(f'    [{x["hidden_rule"]}?] {x["page"]} Ex{x["n"]} {x["where"]}'
                  f'「{x["name"]}」回源 {x["match"]["csv"]}:{x["match"]["col"]}'
                  f' — {x["title"][:44]}')
    print(f'🔴 {len(red)}   🟡 {len(yel)}')
    if not red:
        # 「今天没报错」与「规则坏了」在输出上长得一样，必须能分开。
        print('（无 🔴。规则是否还活着请跑 --selftest —— 它对着已知错例验四条规则）')

    for lvl, rows in (('🔴', red), ('🟡', yel)):
        if not rows:
            continue
        print('\n' + '-' * 86)
        print(f'{lvl} {len(rows)} 条')
        print('-' * 86)
        for r in rows:
            head = f'{r["page"]}' + (f' Ex{r["n"]}' if r['n'] else '')
            print(f'{lvl} [{r["rule"]}] {head} — {r["title"][:70]}')
            print(f'     {r["msg"]}')

    if a.verbose:
        und = [x for x in live if not x['match']['caliber']]
        print('\n' + '-' * 86)
        print(f'口径未确定的 {len(und)} 条（只列不报 —— 宁可漏报不制造噪声）')
        print('-' * 86)
        for x in und:
            print(f'   {x["page"]} Ex{x["n"]} {x["where"]}「{x["name"]}」'
                  f'（{x["match"]["n"]} 个可比点）— {x["title"][:56]}')

    payload = {'summary': {'pages': len(paths), 'series': len(alli),
                           'exempt': len(alli) - len(live), 'determined': len(det),
                           'exhibits': ex_all, 'exhibits_exempt': len(ex_ex),
                           'exhibits_exempt_read': len(ex_ex_read),
                           'exhibits_unscanned_fields': len(blind),
                           'red': len(red), 'yellow': len(yel)},
               'census': allc,
               'params': {'MATCH_TOL_PP': MATCH_TOL_PP, 'MIN_MATCH_PTS': MIN_MATCH_PTS,
                          'SIGN_DEADBAND_PP': SIGN_DEADBAND_PP,
                          'EXEMPT_KINDS': sorted(EXEMPT_KINDS)},
               'findings': allf, 'items': alli}
    if a.json == '-':
        print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    elif a.json:
        with open(a.json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=1, default=str)
        print(f'\n机器可读结果 → {a.json}')

    print('\n' + ('🔴 有硬错，退出码 1' if red else '无硬错，退出码 0'))
    return 1 if red else 0


HOW_TO_WIRE_IN = """
接进 build/payload_guard.py 的建议改法（等 10 个 agent 的改动落定后再做）
─────────────────────────────────────────────────────────────────────────
1. 不要在 payload_guard 里 import 本文件。payload_guard 现在只依赖 json/re/os，
   本文件依赖 pandas + numpy + 全量读 series/*.csv（约 1s）。让**每一个** builder
   在写文件时都付这 1s、并且多背两个第三方依赖，不划算。
   改法：把 `identify()` 需要的东西前移 —— 让 builder 在算同比时就走
   `build/yoy.py`，并把口径以**结构化字段**写进 payload：

       ex['caliber'] = 'ttm' | 'mom'        # 必填，来自 yoy.py 的哪个函数
       ex['caliber_src'] = 'db1.csv:oi_bund_contracts'   # 可选，回源用

   有了这个字段，payload_guard 侧的检查退化成纯字符串/结构判断，零依赖、零耗时：
     · 有 yoy 序列却没有 caliber 字段 → 报错（堵住「又抄了一份」）
     · caliber == 'mom' 而 title 里没有「单月 / single-month」→ 报错
     · caliber == 'ttm' 而 caliber_src 命中 yoy._STOCK_PAT → 报错
     · 同页出现两种 caliber，而 notes 里没有逐个 Exhibit 点名 → 报错
   本文件（回源复算那一半）保留为**离线校验**：CI / monthly_run 收尾各跑一次，
   负责验证 `ex['caliber']` 这个自述字段没有说谎。自述字段能被改坏，回源复算不能。

2. 挂在哪：`payload_guard.write_dash()` 里 `check(payload)` 之后、`json.dumps` 之前，
   加一句 `check_caliber(payload, gen)`，沿用 `PayloadGuardError`（它已经是
   SystemExit 子类，monthly_run 那边看到的仍是「returncode != 0 → FAIL」）。

3. 灰度：先只对 `ex['caliber']` 缺失**且**页面已经出现过两种口径的页报错，
   其余只 warn（stderr）。等 28 页全部补上 caliber 字段，再把 warn 提成 error。
   一次性全量报错会把 28 页同时打成 FAIL，那天谁也别想 build。

4. 本文件的四条规则里，R1（回源复算符号相反）**不要**搬进 payload_guard ——
   它要读全量 series/*.csv 才能判，属于离线校验的活。R2/R3/R4 可以搬。
"""

if __name__ == '__main__':
    sys.exit(main())
