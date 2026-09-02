# -*- coding: utf-8 -*-
"""Nasdaq（NDAQ）单公司页配置。

口径以 docs/verify/verify_ndaq.md（复核稿，判定 B）为准。侦察稿 docs/verify/ndaq.md
的两条已被复核证伪，本文件按复核稿写：
  · E1「五个字段 250 个月零空值」是假的 —— 缺失值是字符串 'n/a' 不是 None，
    复合 matched 口径实际从 **2010-10** 起（NTX 2009-01、PSX 2010-10）。
  · E2「欧洲只比份额不比绝对值」方向反了 —— Nasdaq 的欧洲份额是**北欧+波罗的海**分母，
    与 Cboe 的泛欧份额不是同一个宇宙；可比的是绝对值，不可比的是份额。
    所以本文件里两列一律写明「北欧与波罗的海」，且不给份额列（CSV 里也没有）。

列名全部对着 `head -1 series/ndaq.csv` 逐字核过（14 列，251 个月，2005-09..2026-07）。
注意：侦察稿里的 vol_us_matched_shares_mm / us_trading_days / us_*_shares_bn 等名字
**都不是最终列名**，fetcher 落库时改过；docs/verify/_design.md 里引用的也是旧名。以 CSV 为准。

━━ 2026-08-18：原来「只有 19 个月」的四列里，有两列已经回补 ━━━━━━━━━━━━━
本文件此前整篇建立在「A 组四列只有 2025-01 起 19 个月且不可回补」这个前提上
（头条为什么不取 A 组、次轴为什么用单月同比、level_yoy 为什么不取 IR 那条，
理由全指向它）。**那个前提对其中两列已经不成立**：
  · `vol_nordic_derivs_mmcontracts` → **2013-01** 起（163 个月）。来源是 Nasdaq Nordic
    交易所公告的 "Derivative Volumes per Month" 月报，19 个重叠月与 IR 印刷值一位小数全等。
  · `vol_us_cash_matched_mnsh`       → **2010-10** 起（190 个月）。2025-01 起仍是 IR 原值，
    更早是同一张 CSV 里 nasdaqtrader 三盘口（Nasdaq + NTX + PSX）的和 ÷ 1e6。
    19 个重叠月里 18 个 |差| ≤ 0.0101% ⇒ 拼接落差在 0.01% 量级。
另外两列仍然只有 19 个月，而且是**两种不同的「不能」**（别混为一谈）：
  · `vol_us_options_mmcontracts`  Nasdaq 一方确实没有月度档案（source_hard）。
  · `vol_nordic_cash_value_usdbn` 官方月度原件是**欧元**的，换算不回 IR 那条美元
    （13 个重叠月系统性低 0.77%~2.50%）—— 是口径断点，不是抓取难题。
两条的实测证据都在 `fetch/ndaq.py` 的模块 docstring（A 组「历史深度」一节 + 口径坑 19/20）。

━━ 📌 本页做不了量价分解：金额与股数分属两个法域 ━━━━━━━━━━━━━━━━━━━━━━━
量价分解要一对**同口径**的（金额，数量）。本表唯一的金额列是
`vol_nordic_cash_value_usdbn`（**北欧 + 波罗的海**现货成交额），
而全部股数列（`vol_us_cash_*_sh` 四条 + `vol_us_cash_matched_mnsh`）都是**美国**的。
两者相除得到的是「北欧的钱 ÷ 美国的股」—— 不指代任何东西，连量纲都是拼出来的。
📌 **不许相除。**缺的是列不是口径：Nasdaq 既不发美股的成交金额，也不发北欧的成交股数。

（北欧那一侧连「成交额 + 成交股数」都凑不齐：`vol_nordic_derivs_mmcontracts` 是
衍生品张数，配的是衍生品不是现货。美股那一侧的四条股数列则一条金额都没有。）
"""

import csv
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'ndaq.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：在 import 期从 series/ndaq.csv 现算。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, col):
    try:
        v = r[col].strip()
    except (KeyError, AttributeError):
        return None
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _span(col):
    """该列的 (首月, 末月, 有值月数)；算不出返回 (None, None, 0)。"""
    ms = [r['month'] for r in _rows() if _num(r, col) is not None]
    return (ms[0], ms[-1], len(ms)) if ms else (None, None, 0)


def _tradingday_spread():
    v = [d for d in (_num(r, 'trading_days_us_equities') for r in _rows()) if d]
    if not v:
        return None, None, None
    return min(v), max(v), (max(v) / min(v) - 1.0) * 100.0


_MN0, _MN1, _MNN = _span('vol_us_cash_matched_mnsh')       # 拼接列：IR + 三盘口和
_OPT0, _OPT1, _OPTN = _span('vol_us_options_mmcontracts')  # 纯 IR，只有 19 个月
_ND0, _ND1, _NDN = _span('vol_nordic_derivs_mmcontracts')  # 交易所公告档案回补
_NC0, _NC1, _NCN = _span('vol_nordic_cash_value_usdbn')    # 纯 IR，只有 19 个月
_B0, _B1, _BN = _span('vol_us_cash_matched_nasdaq_sh')     # B 组（nasdaqtrader）
_DMIN, _DMAX, _DSPR = _tradingday_spread()


def _span_zh(m0, n, fallback=''):
    """图注里那半句「X 起 N 个月」。算不出就退回不含数字的写法。"""
    return f'{m0} 起 {n} 个月' if m0 else fallback


# 四条绝对成交股数列（本页不画、只在页注里交代）的覆盖 —— **逐列**现算。
# 上一版这里写死成「2005-09 起 250 个月」，两处都不对：① 251 不是 250
#    （写死那天数据月是 2026-06，每发一期就差 1）；
# ② 四列根本不同起点，PSX 要到 2010-10 —— 而同一页上一条注就写着
#    「三个盘口凑齐的时间不同：2005-09 / 2009-01 / 2010-10」，自己打自己。
_SHARE_SRC_COLS = (
    ('vol_us_cash_consolidated_sh', '全美 consolidated'),
    ('vol_us_cash_matched_nasdaq_sh', 'The Nasdaq Stock Market'),
    ('vol_us_cash_matched_ntx_sh', 'Nasdaq NTX'),
    ('vol_us_cash_matched_psx_sh', 'Nasdaq PSX'),
)


def _share_src_spans():
    """→ ('四列', '全美 consolidated 2005-09 起 251 个月、…')；条数与覆盖都现算。

    条数也得现算：页注上一版写「官方文件里还有**四列**绝对成交股数」，而这里
    有几列 CSV 里就真有几列 —— 少一列（源不再给）时那句话立刻变成假话，
    而条数与名单印在同一句里，读者一数就对不上。
    """
    bits = []
    for col, zh in _SHARE_SRC_COLS:
        m0, _m1, n = _span(col)
        if m0:
            bits.append(f'{zh} {m0} 起 {n} 个月')
    if not bits:
        return '若干', '这几列本轮在 CSV 里一列都没读到'
    k = len(bits)
    n_zh = ('%s列' % '一两三四五六七八九十'[k - 1]) if k <= 10 else ('%d 列' % k)
    return n_zh, '、'.join(bits)


_SHARE_SRC_N, _SHARE_SRC_SPANS = _share_src_spans()


# 拼接列的接缝：IR 段从哪个月起，用**探针列**现算，不写死 '2025-01'。
# 探针 = `vol_us_options_mmcontracts` 的首月 —— 那一列只来自 IR 那份 PDF、从来没被回补过，
# 所以它在 CSV 里的首月就是「IR 第一次进这张表」的那个月，正是接缝的位置。
# （它不会随 PDF 的滚动窗口移动：已入库的月份永不删除，见 fetch/ndaq.py 的幂等约定。）
_SPLICE_AT = _OPT0


# 拼接列的两段在重叠月上对不对得上 —— **现算**，不写死「19 个重叠月里 18 个月」。
# 那两个数每发一期就变一次（IR 段每月长一个月），而 CSV 里三个盘口的分列还在，
# 「IR 原值 vs 三盘口之和」随时可以重算，没有理由写死。
# 阈值 0.05%：实测一致的那批在 0.01% 量级（官方四舍五入的痕迹），
# 唯一一个真正的离群点在 0.3% 量级，两者之间空着一个数量级，取中间。
_SPLICE_TOL = 0.05


def _splice_overlap():
    """(重叠月数, 一致月数, 一致那批的最大 |差|%, [(离群月, 差%)])；算不出返回 None。

    差的方向：**nasdaqtrader 三盘口之和相对 IR 原值**（负 = nasdaqtrader 少计），
    与页注的措辞一致。
    """
    if not _SPLICE_AT:
        return None
    ok, bad, worst = 0, [], 0.0
    n = 0
    for r in _rows():
        if r['month'] < _SPLICE_AT:
            continue
        ir = _num(r, 'vol_us_cash_matched_mnsh')
        parts = [_num(r, c) for c in ('vol_us_cash_matched_nasdaq_sh',
                                      'vol_us_cash_matched_ntx_sh',
                                      'vol_us_cash_matched_psx_sh')]
        if ir in (None, 0) or any(p is None for p in parts):
            continue
        n += 1
        d = (sum(parts) / 1e6 / ir - 1.0) * 100.0
        if abs(d) <= _SPLICE_TOL:
            ok += 1
            worst = max(worst, abs(d))
        else:
            bad.append((r['month'], d))
    return (n, ok, worst, bad) if n else None


_SPLICE_OV = _splice_overlap()


def _splice_bad_zh():
    """例外那几个月落在哪儿 —— **现判**，不写死「都在 IR 段内部、与接缝无关」。

    「与接缝无关」这句话只有在例外月**不是接缝那一格**时才成立。上一版把它写成
    对一个现算列表的全称断言：列表是活的、断言是死的，哪天离群点正好落在接缝上，
    页面就会一边列出接缝那个月、一边说「与接缝无关」。这里按 `_SPLICE_AT` 现判。
    """
    if not _SPLICE_OV or not _SPLICE_OV[3]:
        return '窗口内没有例外。'
    bad = _SPLICE_OV[3]
    lst = '、'.join('%s 差 %+.4f%%' % (m, d) for m, d in bad)
    on_seam = [m for m, _ in bad if m == _SPLICE_AT]
    if not on_seam:
        where = '都在 IR 段内部（不是接缝那一格），与接缝无关'
    elif len(on_seam) == len(bad):
        where = '<b>正落在接缝那一格</b>（%s）—— 不能再说「与接缝无关」，请重新裁定' % _SPLICE_AT
    else:
        where = ('其中 %s <b>正落在接缝那一格</b>，其余在 IR 段内部 —— 接缝那一格'
                 '请重新裁定' % '、'.join(on_seam))
    return '例外 %d 个月：%s —— %s。' % (len(bad), lst, where)


def _splice_step_zh():
    """接缝那一格的环比，以及同月三个盘口分列的环比 —— 逐个现算。

    这三个数上一版是写死的（-2.69% / -2.65% / -2.66%），而它们旁边的月份
    (`_SPLICE_AT`) 是现算的：接缝一移，月份跟着走、数字不跟着走，两半立刻打架。
    这一段的论证是「台阶与分列同步 ⇒ 是真实波动不是接缝台阶」，所以三个数必须同源。
    """
    if not _SPLICE_AT:
        return ''
    months = [r['month'] for r in _rows()]
    if _SPLICE_AT not in months:
        return ''
    i = months.index(_SPLICE_AT)
    if i == 0:
        return ''
    prev = months[i - 1]
    idx = {r['month']: r for r in _rows()}

    def mom(cols):
        a = b = 0.0
        for c in cols:
            x, y = _num(idx[prev], c), _num(idx[_SPLICE_AT], c)
            if x is None or y is None:
                return None
            a += x
            b += y
        return None if not a else (b / a - 1.0) * 100.0

    ir = mom(['vol_us_cash_matched_mnsh'])
    nd = mom(['vol_us_cash_matched_nasdaq_sh'])
    # 第三个数取**份额**列而不是三盘口之和：拼接列在接缝左侧就等于那个和，
    # 拿和来印证等于自己证自己。份额列是另一条独立落库的序列，才有证据力。
    sh = mom(['share_us_cash_matched_group'])
    if ir is None or nd is None or sh is None:
        return ''
    # 「同步」是本段的论点，所以它也得是判据而不是形容词：三个环比互差 ≤ 0.2pp 才叫同步。
    same = max(abs(ir - nd), abs(ir - sh), abs(nd - sh)) <= 0.2
    return ('接缝那一格 %s → %s 环比 %+.2f%%，与同月三个盘口分列的环比'
            '（Nasdaq %+.2f%%、三盘口合成份额 %+.2f%%）%s ⇒ %s。'
            % (prev, _SPLICE_AT, ir, nd, sh,
               '完全同步' if same else '<b>并不同步</b>',
               '那是真实的市场波动，不是接缝台阶' if same else
               '<b>这一段的原结论（真实波动、不是接缝台阶）在本期数据下不成立，请重新裁定</b>'))


_SPLICE_BAD = _splice_bad_zh()
_SPLICE_STEP = _splice_step_zh()

_NO_DECOMP_NOTE = (
    '📌 <b>本页不具备量价分解的数据条件 —— 金额与股数分属两个法域。</b>'
    '量价分解要一对<b>同口径</b>的（金额，数量）。本表唯一的成交金额列是 '
    '<code>vol_nordic_cash_value_usdbn</code>（<b>北欧 + 波罗的海</b>现货成交额），'
    '而全部股数列都是<b>美国</b>的。两者相除得到的是「北欧的钱 ÷ 美国的股」，'
    '不指代任何东西，连量纲都是拼出来的。<b>不许相除。</b>'
    '北欧那一侧自己也凑不齐：<code>vol_nordic_derivs_mmcontracts</code> 是衍生品张数，'
    '配的是衍生品不是现货；美股那一侧的四条股数列则一条金额都没有。'
    '缺的是列不是口径 —— Nasdaq 既不发美股的成交金额，也不发北欧的成交股数。'
)

_NOTE_TTM = (
    '<b>这张图用的是本页历史最长、而且<u>单一来源</u>的那条流量序列</b>'
    + (f'（<code>vol_us_cash_matched_nasdaq_sh</code>，{_B0} 起 {_BN} 个月，'
       f'整条都来自 nasdaqtrader 的月度市占 xlsx）' if _B0 else '')
    + '，而不是三盘口合计那条'
    + (f'（<code>vol_us_cash_matched_mnsh</code>，{_MN0} 起 {_MNN} 个月）'
       if _MN0 else '')
    + '。⚠ 这里的理由换过两次，两次的旧理由都已作废，记在这里免得有人再走一遍：'
      '① 最早写的是「IR 那条只有 19 个月，滚动同比要 24 个月，够不到」；'
    + (f'② 2026-08 改成「它已回补到 {_MN0}，够长了，但它是<b>拼接列</b>'
       f'（{_SPLICE_AT} 起 IR 原值、更早是 nasdaqtrader 三盘口和），'
       f'而滚动同比把 24 个月压成一个数、接缝落在窗口里读者挑不出来」。'
       if _MN0 and _SPLICE_AT else '② 2026-08 改成「它够长了，但它是拼接列」。')
    + '<b>③ 2026-09 全站同比改成单月之后，前两条都不再是理由</b> —— '
      '单月同比只跨两个月，接缝落在哪一个月一眼就看得出来。'
      '仍然留在单一来源那条上的<b>新</b>理由只剩一个、也够了：'
      '两条的水平值差在 0.01% 量级，换列不改变图形，只会让来源变得不好交代。'
      '⚠️ 但拼接这件事在单月口径下有一处**具体**的后果要记住：'
    + (f'{_SPLICE_AT} 与它之后的 11 个月，同比的基期落在接缝另一侧；'
       if _SPLICE_AT else '接缝之后的 12 个月，同比的基期落在接缝另一侧；')
    + '本图用的这一列没有接缝，所以不受影响 —— 这正是留在它上面的价值。'

      '<b>为什么这一列不在上面的分组里。</b>它的单位是裸股数/月、量级 10¹¹，'
      '唯一能读的显示方式是 ×1e-9 换成「十亿股/月」；而底座给带 scale 的列生成的'
      '<b>核对表脚注</b>写死成「源表是 0–1 的小数比率，本页统一按百分数显示」——'
      '对这种非比率列会在页面上印出一句假话。'
      '页尾这类「水平值 + 单月同比」的图<b>不走核对表那条路径</b>，'
      '所以在这里用 scale 是安全的；'
      '等底座把那句脚注一般化之后，这一列可以一并加回上面的分组。'
    + (f'<b>⚠️ 柱是<u>当月合计</u>，所以交易日数这一层留在同比里。</b>'
       f'美股每月 {_DMIN:.0f}–{_DMAX:.0f} 个交易日，两端相差 {_DSPR:.0f}%；'
       f'本图的单月同比里有一截只是「今年这个月比去年多开 / 少开了几天市」，'
       f'读的时候要把它减掉再判断量本身的方向。'
       f'（本页 ADV 那几张是日均口径，天然不含这一层 —— 两种图要分开读。）'
       if _DSPR is not None else '')
    + '<b>柱与线取自同一列</b>（当月合计）：拿这根柱除以 12 根柱之前那根就是线上这一点，'
      '中间没有任何「日均还原成合计」的步骤。'
)

# ── 本页最要命的一件事：两组数据的发布节奏差一周多 ─────────────────────────
# A 组（IR Monthly Reporting Sheet PDF，4 列）：次月第 6~8 个日历日发布；那份 PDF 每月
#     **原地替换**同一个 uuid，所以 **IR 自己**只有 2025-01 起 19 个月的窗口。
# B 组（nasdaqtrader.com marketshare{YY}.xlsx，9 列）：可回溯到 2005-09，
#     但发布晚得多 —— 2026-06 那份的 Last-Modified 是 07-13，而 IR 的 07 月数据 08-05 就发了。
# ⇒ 直觉是「头条取 A 组、B 组进 slow_cols」，但实测行不通：底座要求头条有 ≥24 个月
#   共同历史，A 组四列里最新那期只有 19 个月的 IR 窗口，这一页要等到 2026-12 才发得出来。
#   所以本页反过来 —— **以慢而长的 B 组为脊梁**，A 组当「发布更快的腿」。
#   代价是本页数据月比 Nasdaq IR 官方晚一期（见 headline 处的完整推理）。
#
# ⚠ 2026-08-18 起「A 组 = 短、B 组 = 长」这个二分法**只对四列里的两列成立**了。
#   回补之后各列真实长度（本文件在 import 期从 CSV 现算，不写死）：
#       vol_us_options_mmcontracts     19 个月   纯 IR，source_hard
#       vol_nordic_cash_value_usdbn    19 个月   纯 IR，欧元原件换不回美元
#       vol_us_cash_matched_mnsh      190 个月   拼接（IR + nasdaqtrader 三盘口和）
#       vol_nordic_derivs_mmcontracts 163 个月   Nasdaq Nordic 交易所公告档案
#   头条与 slow_cols 的结论**不变**：头条要的是「四列共同历史」，那仍然被 19 个月的
#   两条卡着；发布节奏也没变（IR 仍比 nasdaqtrader 早一个多星期）。变的只是
#   分组的组织方式 —— 长短两类不再共用一个组标题，见下面 groups 的注释。

SPEC = {
    'ticker': 'ndaq',
    'name':   'Nasdaq',
    'title':  '纳斯达克（NDAQ）月度经营指标',
    'csv':    'ndaq.csv',
    'ccy':    'USD',
    'source': 'Source: Nasdaq IR Monthly Reporting Sheet (ir.nasdaq.com), nasdaqtrader.com '
              'monthly market share files and Nasdaq Nordic exchange notices '
              '("Derivative Volumes per Month"); format after Goldman Sachs GIR',

    # ── 头条为什么不是 A 组：这家的两条腿是「快而短」对「慢而长」，只能二选一。
    # 底座的门槛要求头条列有 ≥24 个月的共同历史（同比与 3Y 分位算不出来就不该发页）。
    # A 组四列里，美股期权与北欧现货至今只有 19 个月（另两列 2026-08-18 已回补，
    # 见文件头那一段）—— 拿 A 组整组当头条，共同历史仍然是那 19 个月，过不了门槛。
    # 所以头条取 B 组的份额列：share_us_cash_matched_group 有 190 个月（2010-10 起）、
    # share_us_cash_matched_nasdaq 有 251 个月（2005-09 起），共同历史 190 个月，够。
    # 代价是本页数据月跟着 B 组走（比 IR 晚一期）；A 组因此变成「发布更快的腿」，
    # 在核对表尾部会多出一行、其余列显示「—」，这是底座内建的正常形态。
    # ⇒ slow_cols 因此为空：没有任何一列比头条更晚。
    # ⚠ 回补**没有**给「换头条」开门：`vol_us_cash_matched_mnsh` 现在够长了，但它是
    #   月度流量、量级 5 万，而头条那两格是份额（%）—— 换过去等于把这一页的主线从
    #   「Nasdaq 在美股里占多少」改成「美股这个月成交了多少」，是换页不是换列。
    'headline': [
        {'col': 'share_us_cash_matched_group', 'zh': '美股 matched 市占率（三盘口合计）',
         'unit': '%', 'fmt': 'pct1', 'scale': 100},
        {'col': 'share_us_cash_matched_nasdaq', 'zh': 'The Nasdaq Stock Market 市占率',
         'unit': '%', 'fmt': 'pct1', 'scale': 100},
    ],

    'groups': [
        # ══ 为什么这里是四个单列组，而不是原来的两个双列组 ═══════════════════
        # 底座对每个组**按单位分桶、一桶一图**（build/single.py 的 `buckets`）。
        # 原来的「美国市场」组里两列两个单位，本来就出两张 gs_bar；组标题只是被
        # 原样贴到两张图前面。回补之后这两列一条 19 个月、一条 190 个月，
        # 再共用一句「IR 月报口径」的标题就是**在其中一张图上印假话**。
        # 拆成四个单列组，出图数量、顺序、图型全不变，变的只是每张图的标题说的是它自己。
        #
        # 四张图的次轴一律是**单月同比**（底座 `ex_single` 给的就是它，本页无法改）。
        # 单月是全站唯一口径（CONTRACT §6.1 第 1 条），§6.6 的自动判据要求它写进标题
        # （R4，不写就报 🟡）⇒ 四个组名里都带那半句。
        # ⚠ 别再写「等攒够 24 个月就改用滚动同比」—— 2026-09 全站同比统一成单月
        #   （CONTRACT §6，页面所有者指定），滚动口径页上一条线都不画了。

        # ── ① 美股期权：本页唯一一条**源头上就没有月度档案**的列（source_hard）。
        #    与下面第 ③ 条不同：③ 的官方原件存在、只是币种口径接不上；这一条是根本没有。
        #    Nasdaq 一方没有月度档案：IR 落地页只有一条 static-file、没有年份归档；
        #    2016 的新闻稿 slug 404、2024 的新闻稿正文一个千分位数字都没有；
        #    同目录的 msoption{YY}.xlsx 只有三家所（不含 ISE/GEMX/MRX）、只有三个月的快照。
        #    三条 2026-08-18 都重新实测过，证据在 fetch/ndaq.py 的 A 组「历史深度」一节。
        {'zh': '美股期权（IR 月报口径，%s；当月总量，次轴：单月同比）'
               % _span_zh(_OPT0, _OPTN, '仅最近一段'), 'cols': [
            {'col': 'vol_us_options_mmcontracts', 'zh': '美股期权成交量（六所合计，含指数期权）',
             'unit': 'mn contracts/month', 'fmt': 'f0c'},
        ]},

        # ── ② 美股 matched 成交股数：拼接列。接缝在 _SPLICE_AT，落差 0.01% 量级。
        #    组名里必须写出两段来源 —— 这是全页唯一一条「同一根线上有两个数据源」的序列，
        #    不写出来读者会以为整条都是 IR 发的。
        #    为什么不给它挂一条红色断点竖线：`breaks` 的语义是「从这一期起与左侧不可比」，
        #    而这两段实测就是同一个东西（19 个重叠月里 18 个 |差| ≤ 0.0101%）。
        #    画红线会把一个 0.01% 的来源切换说成口径换代，比不画更误导。理由同下面 breaks 处。
        {'zh': ('美股 matched 成交股数（%s 起 IR 原值、更早为 nasdaqtrader 三盘口和；'
                '当月总量，次轴：单月同比）' % _SPLICE_AT) if _SPLICE_AT else
               '美股 matched 成交股数（当月总量，次轴：单月同比）', 'cols': [
            {'col': 'vol_us_cash_matched_mnsh', 'zh': '美股 matched 成交股数（Nasdaq+NTX+PSX）',
             'unit': 'mn shares/month', 'fmt': 'f0c'},
        ]},

        # ── ③ 北欧与波罗的海现货成交额：**不是泛欧**。本机用仓内数据实算 2026-06：
        #    本列 Nasdaq = $93.2bn/月，而 Cboe Europe = 14.95 EURbn/日 × 22 个观察日
        #    × EURUSD 1.1518 ≈ $379bn/月 —— Cboe 是 Nasdaq 的 4.1 倍。
        #    Nasdaq 自报的「欧洲份额 74.5%」是北欧/波罗的海本地分母，与 Cboe 的泛欧份额
        #    不是同一个市场。所以只放绝对值，不放份额（CSV 里也没有份额列）。
        #    这一列同样只有 19 个月，但**原因与美股期权不同**：官方月度原件是欧元的
        #    （交易所公告 'Main Market Total Equity Trading'，2022-03 起逐月连续），
        #    折美元后与 IR 系统性低 0.77%~2.50%，scope 复原不了 ⇒ 是口径断点不是抓不到。
        {'zh': '北欧与波罗的海现货成交额（Nordic + Baltic 口径，%s；当月总量，次轴：单月同比）'
               % _span_zh(_NC0, _NCN, '仅最近一段'), 'cols': [
            {'col': 'vol_nordic_cash_value_usdbn', 'zh': '北欧+波罗的海现货成交额',
             'unit': 'USD bn/month', 'fmt': 'f1'},
        ]},

        # ── ④ 北欧与波罗的海衍生品：2026-08-18 从交易所公告档案回补到 2013-01。
        #    重建口径 = 各权益类产品族 sheet 的 Cleared volumes / No. of Contracts 求和，
        #    与 IR 印刷值在 19 个重叠月上一位小数全等（fetch/ndaq.py 口径坑 19）。
        #    ⚠ 产品族是逐年长出来的（Mini Index 2020、OMXESG 2023、Custom Basket 2024），
        #      2013-2019 只有股票与指数两族 —— 这不是口径变更（那些产品当时不存在），
        #      但读者若拿 2013 与 2026 直接比"覆盖面"会想错，所以写进 notes。
        {'zh': '北欧与波罗的海期权与期货（Nordic + Baltic 口径，%s；当月总量，次轴：单月同比）'
               % _span_zh(_ND0, _NDN, '仅最近一段'), 'cols': [
            {'col': 'vol_nordic_derivs_mmcontracts', 'zh': '北欧+波罗的海期权与期货成交量',
             'unit': 'mn contracts/month', 'fmt': 'f1'},
        ]},

        # ── B 组份额：本页历史最长的一组，也是这家真正的看点。
        #    合成口径 2010-10 起（PSX 是最后一个凑齐的盘口）；
        #    单盘口 Nasdaq 一列可回到 2005-09，NTX 回到 2009-01。
        #    这四列在 CSV 里是**分数**（0.1477 = 14.77%），所以一律 scale=100 + pct1。
        #    本机用算术验过：share ÷（matched ÷ consolidated）中位比值 = 1.000。
        {'zh': '美股 matched 市占率（nasdaqtrader 口径，本页脊梁）', 'cols': [
            {'col': 'share_us_cash_matched_group', 'zh': '三盘口合计（2010-10 起）',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'share_us_cash_matched_nasdaq', 'zh': 'The Nasdaq Stock Market（2005-09 起）',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            # NTX / PSX 是尾部盘口（历史最大 4.52% / 1.43%）。这两条用 f2 而不是 pct2：
            # 底座的比率量纲体检对 pct* 列要求「缩放后最大值 > 1.5」，PSX 缩放后最大只有
            # 1.428（那是它真实的份额上限，不是没缩放），配 pct2 会被硬失败挡下。
            # 换 f2 后数值仍是百分数刻度（scale=100），单位由 unit 写明，读数不变。
            {'col': 'share_us_cash_matched_ntx', 'zh': 'Nasdaq NTX（原 BX，2009-01 起）',
             'unit': '%', 'fmt': 'f2', 'scale': 100},
            {'col': 'share_us_cash_matched_psx', 'zh': 'Nasdaq PSX（2010-10 起）',
             'unit': '%', 'fmt': 'f2', 'scale': 100},
        ]},

        # ── B 组的四列绝对量（vol_us_cash_*_sh）**故意不上页**。
        #    它们的单位是裸股数/月，量级 1e11（2026-06 全美 consolidated = 491,030,721,182），
        #    唯一能读的显示方式是 ×1e-9 换成「十亿股/月」；
        #    但底座给 scale 列生成的表注文案写死成「源表是 0–1 的小数比率，本页统一按百分数显示」
        #    （底座 `Page.notes()` 里拼「末尾核对表」那一条时写死的那半句），
        #    对非比率列会在页面上印出一句假话。
        #    ⇒ 信息没有丢：上面四条份额列就是这四列除出来的，且历史一样长。
        #      等底座把那句表注一般化之后，这四列可以一行一条加回来（scale: 1e-9）。

        # ── 交易日：把 A 组的「当月总量」换成 ADV 的唯一钥匙，但它在 B 组里，
        #    比 A 组晚一期 —— 所以 A 组最新那一期**换不出 ADV**，要等交易日跟上。
        {'zh': '美股交易日（换算 ADV 用）', 'cols': [
            {'col': 'trading_days_us_equities', 'zh': '当月交易日数',
             'unit': 'days/month', 'fmt': 'f0'},
        ]},
    ],

    # 空：头条已经是发布最慢的那条腿（B 组 nasdaqtrader），没有任何一列比它更晚。
    # A 组四列反过来比头条**早**一期 —— 那不是慢腿，是快腿，底座会让它们在核对表
    # 尾部多出一行、其余列显示「—」。若将来 IR 那份 PDF 攒够 24 个月历史，
    # 应把头条换回 A 组，届时这里要填上 B 组的五列。
    'slow_cols': [],

    # 无口径断点。复核实测：2025-12 定格的 marketshare25.xlsx 与 2026-06 版的
    # marketshare26.xlsx 在 244 个重叠月 × 5 字段上逐格比对，不一致数 = 0 ——
    # Nasdaq 不重述美股月度成交量。NTX 只是 BX 的改名，不是换盘口。
    # 各列不同的起点（2005-09 / 2009-01 / 2010-10 / 2013-01 / 2025-01）是序列起点不是断点，
    # 写成断点会在 127 个月的图上画出好几条与口径无关的红线。
    #
    # ⚠ 2026-08-18 回补之后专门重新想过两处「要不要登记断点」，结论都是**不登记**：
    #  (a) `vol_us_cash_matched_mnsh` 在 2025-01 换来源（nasdaqtrader 三盘口和 → IR 原值）。
    #      `breaks` 的语义是「从这一期起与左侧不可比」。这两段实测就是同一个东西：
    #      19 个重叠月里 18 个 |差| ≤ 0.0101%（唯一的例外 2026-07 差 -0.2896%，
    #      在 IR 段内部，与接缝无关，且第三方 Cboe tape 裁定 IR 对）。
    #      接缝那一格 2024-12 → 2025-01 的环比 -2.69%，与同月三个盘口分列的环比
    #      （Nasdaq -2.65%、合成份额 -2.66%）完全同步 ⇒ 那是真实的市场波动，不是接缝台阶。
    #      画红线会把一个 0.01% 的来源切换说成口径换代。改写进组名与 notes，不画线。
    #  (b) `vol_nordic_derivs_mmcontracts` 的产品族逐年增加（Mini Index 2020、OMXESG 2023、
    #      Custom Basket 2024）。新产品上线不是口径变更 —— 上线前它们的成交量是 0 而不是
    #      「没被统计」，与 PSX 2010-10 上线同型，本页对 PSX 也没有登记断点。
    'breaks': [],

    # 📌 'decomp' 刻意留空：金额列在北欧、股数列在美国，跨法域相除没有经济含义。
    # 完整理由见 _NO_DECOMP_NOTE（它进了下面 notes 的第一条）。

    # ══ 水平值 + 次轴单月同比 ════════════════════════════════════════════════
    # ⚠ level 用的是 vol_us_cash_matched_nasdaq_sh 而**不是**三盘口合计那条。
    #   理由换过三次，最后一次见 _NOTE_TTM 的 ③：2026-09 全站改单月之后，
    #   「滚动同比把接缝压进 24 个月里」那条理由整个失效（单月同比只跨两个月）。
    #   现在留在这一列上的理由只剩「整段单一来源、更长（2005-09 起）」，
    #   而两条的水平值差在 0.01% 量级，换过去不会改变图形。
    # ⚠ 这一列**不在** groups 里（理由见上面的注释：底座给带 scale 的列生成的
    #   核对表脚注对非比率列是假话）。level_yoy 不走核对表那条路径，所以这里用 scale 安全。
    #   底座只校验它真实存在于 CSV，不会把它塞进核对表 ⇒ 那句假话不会被印出来。
    'level_yoy': [{
        'zh': 'The Nasdaq Stock Market 美股 matched 成交股数',
        # 官方 xlsx 发的就是当月合计裸股数；次轴是本列自己的单月同比（本列除本列）。
        'level': {'col': 'vol_us_cash_matched_nasdaq_sh', 'zh': '当月 matched 成交股数',
                  'unit': 'bn shares/month', 'fmt': 'f1', 'scale': 1e-9},
        'note': _NOTE_TTM,
    }],

    'notes': [
        _NO_DECOMP_NOTE,

        '本页有三个数据源、两种发布节奏。<b>A 组</b>（美国期权、美股 matched、北欧两列）来自 Nasdaq IR 的 '
        'Monthly Reporting Sheet PDF，次月第 6~8 个日历日发布，是官方权威值；'
        '<b>B 组</b>（成交股数、份额、交易日）来自 nasdaqtrader.com 的月度市占率 xlsx，'
        '历史深但发布晚一周多（2026-06 那份的 Last-Modified 是 2026-07-13，而 IR 的 07 月数据 08-05 就发了）；'
        '<b>D 组</b>（只用于历史，不用于当期）是 Nasdaq Nordic 交易所公告的衍生品月报。'
        '<b>本页以 B 组为脊梁</b> —— 只有它够 24 个月历史、过得了发布门槛，'
        '因此页面数据月比 Nasdaq IR 官方晚一期；A 组反而是「发布更快的腿」，'
        '在末尾核对表里会多出一行、其余列显示「—」。这是刻意的取舍，不是抓取失败。',

        '<b>IR 那份 PDF 只有 %s 起的滚动窗口，但四条 IR 序列里有两条已经从别的官方档案回补。</b>'
        'PDF 每月原地替换同一个 static-file uuid，IR 站不保留历史版本（2026-08-18 复测：落地页全页只有 1 条 '
        'static-file、无年份归档；2016 的新闻稿 slug 404；2024-10 那篇 200 但正文里一个千分位数字都没有）。'
        '不过「PDF 回不去」不等于「这四列回不去」——'
        '<b>北欧期权与期货</b>已按 Nasdaq Nordic 交易所公告的 "Derivative Volumes per Month" 月报重建到 %s'
        '（19 个重叠月与 IR 印刷值一位小数全等）；'
        '<b>美股 matched 成交股数</b>已按同一张表里 nasdaqtrader 的三个盘口分列相加补到 %s。'
        '仍然只有 %s 起的是<b>美股期权</b>（Nasdaq 一方确实没有月度档案）与'
        '<b>北欧现货成交额</b>（官方月度原件是欧元的，折美元后与 IR 系统性低 0.77%%~2.50%%，'
        'scope 复原不了 —— 那是口径断点，不是抓取难题）。'
        % (_SPLICE_AT or '最近一段', _ND0 or '更早', _MN0 or '更早', _SPLICE_AT or '最近一段'),

        ('<b>美股 matched 成交股数那条线上有一处来源切换，落差在 0.01%% 量级。</b>'
         '%s 起是 IR 月报的原值，更早是同一张 CSV 里 nasdaqtrader 三个盘口'
         '（Nasdaq + NTX + PSX）撮合量之和 ÷ 1e6。'
         % (_SPLICE_AT or '最近一段'))
        + (('两段在重叠月上逐月比过（现算）：%d 个重叠月里 %d 个月 |差| ≤ %.4f%%。'
            % (_SPLICE_OV[0], _SPLICE_OV[1], _SPLICE_OV[2]))
           + _SPLICE_BAD
           + ('2026-07 那一格已经逐日裁定过：是 nasdaqtrader 自己当月少计，'
              '用第三方 Cboe 日频 tape 逐日求和判 IR 对。'
              if any(m == '2026-07' for m, _ in _SPLICE_OV[3]) else '')
           if _SPLICE_OV else
           '（本次算不出重叠月的对账结果，请查 CSV。）')
        + _SPLICE_STEP,

        '<b>北欧期权与期货那条线的产品覆盖面是逐年扩的，但那不是口径变更。</b>'
        '重建口径 = 交易所月报里各<b>权益类</b>产品族的 "Cleared volumes / No. of Contracts" 求和。'
        '产品族随年份增加：2013–2019 只有股票与指数两族，Mini Index Futures 2020 才出现、'
        'OMXESG Index Futures 2023、Custom Basket Forwards and Futures 2024。'
        '新产品上线前它们的成交量是 0 而不是「没被统计」，所以序列前后可比（与 PSX 2010-10 上线同型）。'
        '⚠ 但 Custom Basket 这一族偶尔会一个月放出很大的量 —— 2026-03 那 7.6mm 里有 1.831mm 来自它，'
        '所以那一格的跳升是真实的大宗，不是解析错。',

        '<b>A 组给的是「当月总量」不是日均。</b>官方 PDF 段落标题原文是 '
        '"U.S. equity options volume (millions of contracts)" / "U.S. matched equity volume (millions of shares)"，'
        '没有 average daily 字样。要与 CME / Cboe 的 ADV 比必须先除交易日 —— '
        '而交易日在 B 组、比 A 组晚一期，所以 A 组最新那一期换不出 ADV。'
        '换算后量级已验证合理：2026-06 美股 3.455bn 股/日（Cboe 2.185）、期权 20,381k 张/日（Cboe 22,977）。',

        '<b>vol_us_options_mmcontracts 含指数期权</b>（PDF 脚注 1 的 capture 口径明说含）。'
        '跨家对比时对应的是 Cboe 的 adv_us_options_kcontracts（总数），'
        '<b>不是</b> adv_multilist_options_kcontracts（不含指数）—— 拿 multilist 去比是苹果比橘子。',

        '<b>北欧两列是「北欧 + 波罗的海」口径，不是泛欧 —— 这是本页最容易画出误导图的一处。</b>'
        'Nasdaq 季报自报的欧洲现货市占率约 74.5%，那是北欧/波罗的海本地市场的份额；'
        'Cboe Europe 报的是泛欧份额（约 20–25%）。两者分母不是同一个市场，叠在一张图上会让读者以为 '
        'Nasdaq 是 Cboe 的三倍强。本机用仓内数据实算（Cboe adv_eu_equities_adnv_eurbn × series/fx.csv 的 '
        'obs_days 与 fx_avg_eurusd）：2026-06 Cboe Europe 约 $379bn/月，本列 Nasdaq 为 $93.2bn/月，'
        '<b>Cboe 是 Nasdaq 的 4.1 倍</b>（2026-05 为 3.6 倍、2026-07 为 4.2 倍）。'
        '⇒ <b>欧洲份额禁止跨家对比；可比的只有绝对值</b>，且量级关系与份额给人的印象正好相反。'
        '本页因此只放绝对额，不放欧洲份额（CSV 里也没有这一列）。',

        '<b>美股 matched 的合成口径从 2010-10 起，不是 2005-09。</b>三个盘口凑齐的时间不同：'
        'The Nasdaq Stock Market 2005-09、Nasdaq NTX（2026 年起的名字，之前叫 BX）2009-01、PSX 2010-10。'
        '更早的行在官方 xlsx 里是字符串 "n/a" 而不是空格，只判 None 会在求和时抛 TypeError。',

        '<b>share_us_cash_matched_* 四列在官方原表里是 0–1 的小数比率</b>（0.1477 = 14.77%），'
        '本页统一乘 100 按百分数显示。这一点用算术核过而不是照抄文档：'
        'share ÷（matched 股数 ÷ consolidated 股数）的中位比值 = 1.000。'
        '注意 series/miax.csv 的 share_*_pct 存的是百分数，两家形态相反。',

        '官方文件里还有%s绝对成交股数（全美 consolidated 与三个盘口的 matched，%s），'
        '<b>本页故意不放</b>：它们的单位是裸股数/月、量级 1e11（2026-06 全美 consolidated = '
        '491,030,721,182 股），按裸数显示读不动。信息没有丢 —— 上面四条份额线正是这四列除出来的，'
        '逐条历史一样长。另外同一个行业分母在 ICE 页上有可读形态（三个 tape 的 consolidated ADV，'
        '百万股/日，2011-01 起）。' % (_SHARE_SRC_N, _SHARE_SRC_SPANS),

        '<b>Nasdaq 不重述美股月度成交量。</b>2025-12 定格版与 2026-06 版在 244 个重叠月 × 5 字段上'
        '逐格比对，不一致数 = 0。（例外在季度面板的 revenue capture 四列，那四列当期是估计值会被改，'
        '但不在本 CSV 里。）',

        '本 CSV 不含 IR PDF 第 2 页的季度面板（期权/现货 capture、ETP AUM、上市家数、'
        '跟踪 Nasdaq 指数的股指期货量等 21 行）。其中 q_index_futures 是**别家撮合、Nasdaq 只收授权费**的量，'
        '与 CME 的股指合约有重合，两家分别记账，任何情况下都不能同柱比「谁成交大」。',
    ],
}
