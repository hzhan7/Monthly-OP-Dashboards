# -*- coding: utf-8 -*-
"""TMX Group 单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/tmx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页最容易犯的错：把两段完全不同的历史当成一段 ━━
series/tmx.csv 里躺着**两条互相独立的官方序列**，起点差 19 年、每月到货时间也差几天：

    Montréal Exchange 衍生品（mx_*）   2002-01 → 2026-07   实测 295 个月，零断档
    加拿大现货（tmx_/tsx_/tsxv_/alpha_）2021-08 → 2026-06   实测  59 个月，零断档

写这份配置的当天（2026-08-06）就正是「MX 已有 2026-07、现货还停在 2026-06」的状态。
两条结论直接来自这个事实：

  1. `headline` **只能放 MX 那条**。把现货放进头条，本页的共同最新月会被拖回 6 月，
     而且 2021-08 之前的 19 年历史会因为「共同历史」被整段砍掉。
  2. 全部 17 条现货列进 `slow_cols`。它们比 MX 晚一档发布，最新月留空是**正常状态**，
     不是解析失败，绝不能参与发布门槛判定。

现货那半边为什么只到 2021-08：更早的数据只存在于 tmx.com/en/resource/<id> 的 PDF 里，
而整个 tmx.com 对本网络返回 CloudFront 403（实测 curl / urllib / nscurl / curl_cffi /
本机真实 Chrome 全部 403），没有合规通道。这是数据可得性问题，不是本页的选择。

━━ BOX 期权：本页做不出来 ━━
TMX 官方**只按季度**披露 BOX（季度 MD&A 里的「最近八个季度」表），没有任何月度口径，
BOX 自己的站点也不发月度统计。它落在 series/tmx_box_q.csv（quarter 列，
实测 8 行：2024-Q3 → 2026-Q2），与本页契约的月频 groups 不兼容。
硬塞进来要么改契约、要么在底座里为 TMX 开一条季频分支 —— 两者都违背
「删掉不留残渣、不许 if ticker == 'tmx'」。要做就另起一页，不缠这一页。

━━ 量价分解：为什么三张图都画 TSX 主板，而不是 TMX 合计 ━━
本页现货侧有 TMX 合计 / TSX / TSXV / Alpha / Alpha-X&DRK 五档，每一档都有
**金额 + 股数 + 笔数**三列成对（全仓唯一一家）。三张分解图一律取 **TSX 主板**，两个理由：

  1. **只有 TSX 配得上指数。**series/tmx.csv 里的 `tsx_composite_close` 是
     S&P/TSX Composite —— 它的成分就是 TSX 主板的票。拿它去除 TMX 合计的均价，
     分母里混着 TSXV 的仙股（本文件 `_venue_price()` 现算：TSXV 均价中位数不到
     1 C$/股，TSX 是它的几十倍），得到的「结构效应」里有一大截只是 venue 混合比例。
  2. **TSX 自己没有口径断点。**TMX 合计在 2023-11 纳入 Alpha-X & Alpha DRK
     （见 `_breaks()`），TSX 那一列从头到尾同口径。

TMX 合计并没有因此消失：它是第三张图（三分法）的 **bench**，
「集团整体在动多少 / TSX 在集团里丢了多少份额 / TSX 的品种结构补回多少」正是那张图的读数。

━━ 三因子（笔数 × 每笔股数 × 均价）为什么是两张图不是一张 ━━
恒等式 `成交额 ≡ 笔数 × 每笔股数 × 均价` 成立且三项都有列，但底座的 `decomp`
只提供两种形状：两分法（量 × 派生量）与**三分法（bench 行业 / 份额 / 结构）**。
把「笔数」硬塞进 `bench_value`/`bench_qty` 在算术上确实能凑出这三块
（令 bench 两列同为笔数 ⇒ 行业块 = ln 笔数、份额块 = ln 每笔股数、结构块 = ln 均价），
但底座会据此在图注里印出三句**不成立**的话：「份额 ≡ 股数 ÷ 笔数」、
「结构 ≡ 自家均价 ÷ 行业均价」、以及「⚠️ 分子必须是分母的子集」——
股数不是笔数的子集，那句警告在这里是胡话。**图注说假话的代价高于少画一块柱**，
所以本页改成两张两分法：

    图 A  成交额 ≡ 成交股数 × 均价          （量的贡献 = ln 股数）
    图 B  成交额 ≡ 成交笔数 × 每笔平均金额  （量的贡献 = ln 笔数）

两张一并读就是三因子：ln(股数) − ln(笔数) = ln(每笔股数)，
而图 B 的「每笔金额」块 = 图 A 的「均价」块 + 每笔股数块。
逐年的三项实测数字由 `_three_factor()` 在 import 期从 CSV 现算，写进图 B 的图注，
一个都不写死。

━━ 有意不上页面的其他列 ━━
· mx_adv_index_options_contracts —— 实测最后一个非零月是 2020-10，此后 68 个月全是 0。
  一条归零五年多的死线不提供信息。

━━ BAX 未平仓在窗口内恒为 0：这一列照常声明，不在本文件里做特殊处理 ━━
mx_oi_bax_contracts 最后一个非零月是 2024-05（86,729 张），此后逐月为 0，
2026-06 起整个图窗口恒为 0。恒为 0 的柱图会让引擎的纵轴量程（`0 .. 最大值×1.22`）
上下界重合、坐标算成 0÷0，把图画出卡片外 —— 但**这件事已由底座统一处理**
（`build/single.py` 的 `flat_zero()` / `flat0_skip()`：窗口内全零的图不出，
并在「口径与方法说明」里点名，而**该列仍留在末尾核对表里**）。
所以本文件按常规声明这一列即可，不要在这里摘列：摘了核对表也会跟着少一列，
而「官方报的就是 0」与「本页没有这个指标」是两回事。
· trading_days_rates / trading_days_equity —— 两套分母（每年 9 月、11 月两者不等），
  ADV 官方直接给，本页不做除法。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'tmx.csv')


# ── 断点从 CSV 读，不写死 ──────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。两个函数都只做逐行扫描，
# 不含任何统计口径。读不到就返回 None —— 缺文件不许在 import 期抛异常。
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _first_present(col):
    for r in _rows():
        if col in r and r[col].strip():
            return r['month']
    return None


def _first_zero_after_nonzero(col):
    """该列**由正数转为 0** 的第一个月（产品停发/迁移用这条）。"""
    seen = False
    for r in _rows():
        if col not in r or not r[col].strip():
            continue
        try:
            v = float(r[col])
        except ValueError:
            continue
        if v > 0:
            seen = True
        elif seen:
            return r['month']
    return None


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：全部在 import 期从 series/tmx.csv 现算，
# 再用 f-string 拼进下面三段 _*_NOTE（照 build/specs/jpx.py 的 _wedges()）。
# 任何一步算不出来就返回 None，对应的 note 退回**不含数字的定性版本** ——
# 缺文件 / 缺列不许在 import 期抛异常，否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
import math


def _num(r, col):
    """CSV 里一格 → float；空格子 / 非数返回 None（不拿 0 冒充缺失）。"""
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


def _cal_years(cols):
    """→ [(年份, {列: 该年 12 个月的合计}), …]，只保留 12 个月齐全且各列都有值的日历年。

    与底座 `Page._years(start_month=1, …)` 同一条规矩：缺月的年份整年丢掉，
    **不按 11 个月折算成 12 个月**（折算要假设缺的那个月与其余月同分布，
    而缺月最常见的原因恰恰是「那个月不正常」）。这里再算一遍是因为图注要报的
    「指数涨了多少」「三因子各占多少」底座并不算 —— 底座只认恒等式里那两列。
    """
    buckets = {}
    for r in _rows():
        m = (r.get('month') or '').strip()
        if len(m) != 7 or m[4] != '-':
            continue
        buckets.setdefault(m[:4], []).append(r)
    out = []
    for y in sorted(buckets):
        rows = buckets[y]
        if len(rows) != 12:
            continue
        agg = {}
        for c in cols:
            vals = [_num(r, c) for r in rows]
            if any(v is None for v in vals):
                agg = None
                break
            agg[c] = sum(vals)
        if agg is not None:
            agg['_n'] = 12
            out.append((y, agg))
    # 只保留末尾逐年连续的一段（同底座：中间断一年会把两个不相邻的年度画成相邻柱）
    run = out[-1:]
    for k in range(len(out) - 2, -1, -1):
        if int(out[k][0]) != int(run[0][0]) - 1:
            break
        run.insert(0, out[k])
    return run


def _index_split():
    """把 TSX 均价的增长拆成「市场涨跌」与「品种结构」两截 —— 全仓只有这一家做得到。

    均价 P ≡ 成交额 ÷ 成交股数，它同时含（a）市场涨跌与（b）成交结构变化
    （贵票 vs 便宜票的成交占比此消彼长）。JPX / SGX 两页的图注都只能说
    「均价里含结构效应，但本页拆不出它有多大」—— 因为那两家的 series 里没有指数列。
    TMX 有 `tsx_composite_close`，而且它的成分正是 TSX 主板的票，所以这里能写成

        ln(P₁/P₀) = ln(I₁/I₀) + ln[(P/I)₁ ÷ (P/I)₀]
                     └ 市场涨跌 ┘   └── 品种结构（成交在贵票/便宜票之间的迁移）──┘

    I 取**该年 12 个月末点位的平均**，不取 12 月那一个点：分子 P 是整整 12 个月的
    Σ金额÷Σ股数，拿单月末点位当年度指数水平，端点挑到一个异常月就能把归因说反。

    两块再乘上与图上同一个重标定权重 w = g_额 ÷ ln(V₁/V₀)，于是它们**逐年相加
    恰好等于图 A 里「均价的贡献」那一块**（单位同为百分点），读者可以直接对上。

    返回 [(年标签, 价的贡献pp, 市场涨跌pp, 品种结构pp), …]；算不出返回 []。
    """
    ys = _cal_years(['tsx_value_cad', 'tsx_volume_shares', 'tsx_composite_close'])
    out = []
    for (y1, a1), (y0, a0) in zip(ys[1:], ys[:-1]):
        try:
            V1, V0 = a1['tsx_value_cad'], a0['tsx_value_cad']
            Q1, Q0 = a1['tsx_volume_shares'], a0['tsx_volume_shares']
            I1, I0 = a1['tsx_composite_close'] / 12.0, a0['tsx_composite_close'] / 12.0
            if min(V1, V0, Q1, Q0, I1, I0) <= 0:
                continue
            lV = math.log(V1 / V0)
            if abs(lV) < 1e-6:          # 与底座 DECOMP_LN_MIN 同一条：w 此时是 0/0
                continue
            w = (V1 / V0 - 1.0) / lV
            lP = math.log((V1 / Q1) / (V0 / Q0))
            lI = math.log(I1 / I0)
            out.append((y1, w * lP * 100, w * lI * 100, w * (lP - lI) * 100))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    return out


def _three_factor():
    """三因子实测：ln(成交额) = ln(笔数) + ln(每笔股数) + ln(均价)，重标定成百分点。

    底座画不了三块（理由见模块 docstring），但**数字可以在图注里报全**。
    与图 A / 图 B 用同一个权重 w，所以三项相加逐年等于那两张图菱形上的总增长。

    返回 [(年标签, 总增长%, 笔数pp, 每笔股数pp, 均价pp), …]；算不出返回 []。
    """
    ys = _cal_years(['tsx_value_cad', 'tsx_volume_shares', 'tsx_transactions'])
    out = []
    for (y1, a1), (y0, a0) in zip(ys[1:], ys[:-1]):
        try:
            V1, V0 = a1['tsx_value_cad'], a0['tsx_value_cad']
            Q1, Q0 = a1['tsx_volume_shares'], a0['tsx_volume_shares']
            T1, T0 = a1['tsx_transactions'], a0['tsx_transactions']
            if min(V1, V0, Q1, Q0, T1, T0) <= 0:
                continue
            lV = math.log(V1 / V0)
            if abs(lV) < 1e-6:
                continue
            w = (V1 / V0 - 1.0) / lV
            lT = math.log(T1 / T0)
            lS = math.log((Q1 / T1) / (Q0 / T0))
            lP = math.log((V1 / Q1) / (V0 / Q0))
            out.append((y1, (V1 / V0 - 1.0) * 100,
                        w * lT * 100, w * lS * 100, w * lP * 100))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
    return out


def _bench_wedge():
    """三分法的 bench（TMX 合计）在 2023-11 变大了多少 —— 份额那一块的口径楔子。

    合计口径自 Alpha-X & Alpha DRK 单列起纳入这两个盘口（见 `_breaks()`），
    于是「TSX 的股数份额」的**分母**在那个月一次性变大，份额被机械地压低一点点。
    这一点点有多大不靠形容词：这里量出 Alpha-X&DRK 占合计股数的最大值与最新值。

    返回 (最新月, 最新占比%, 全期最大占比%, 恒等式最大残差)；算不出全部返回 None。
    """
    cur, mx, res = None, 0.0, 0.0
    for r in _rows():
        tot = _num(r, 'tmx_all_volume_shares')
        ax = _num(r, 'alphax_drk_volume_shares')
        if not tot:
            continue
        parts = [_num(r, c) for c in ('tsx_volume_shares', 'tsxv_volume_shares',
                                      'alpha_volume_shares')]
        if all(p is not None for p in parts):
            res = max(res, abs(tot - (sum(parts) + (ax or 0.0))))
        if ax is None:
            continue
        s = ax / tot * 100.0
        mx = max(mx, s)
        cur = (r['month'], s)
    if cur is None:
        return (None,) * 4
    return cur[0], cur[1], mx, res


def _venue_price():
    """各 venue 的均价中位数（C$/股）—— 「品种结构」这件事的直接证据。

    返回 {venue: 中位均价}；算不出返回 {}。
    """
    out = {}
    for pref, zh in (('tsx', 'TSX'), ('tsxv', 'TSX Venture'),
                     ('alpha', 'TSX Alpha'), ('tmx_all', 'TMX 合计')):
        vs = []
        for r in _rows():
            v, q = _num(r, pref + '_value_cad'), _num(r, pref + '_volume_shares')
            if v and q:
                vs.append(v / q)
        if vs:
            vs.sort()
            out[zh] = vs[len(vs) // 2]
    return out


_IDX = _index_split()
_3F = _three_factor()
_BWM, _BWC, _BWX, _BWR = _bench_wedge()
_VP = _venue_price()


def _pp(x):
    return f'{x:+.1f}pp'


# ── 图 A（量 × 价）的图注：把「价」再拆成市场涨跌与品种结构 ────────────────
_NOTE_PRICE = (
    '<b>本页是全仓唯一能把「市场涨跌」与「品种结构」拆开的一家。</b>'
    '均价 ≡ 成交额 ÷ 成交股数，它同时含（a）市场整体涨跌与（b）成交在贵票与便宜票之间的'
    '迁移。JPX 与 SGX 两页的同类图注只能写「均价里含结构效应，但本页拆不出它有多大」——'
    '因为那两家的 series 里没有指数列。'
    '<code>series/tmx.csv</code> 有 <code>tsx_composite_close</code>（S&P/TSX Composite '
    '月末点位），而它的成分正是 TSX 主板的票，所以这里能再写一层**定义式**：'
    'ln(P₁/P₀) = ln(I₁/I₀) + ln[(P/I)₁ ÷ (P/I)₀]，前者是市场涨跌、后者是品种结构。'
    'I 取该年 <b>12 个月末点位的平均</b>而不是 12 月那一个点 —— 分子是整整 12 个月的'
    'Σ金额÷Σ股数，拿单月点位当年度指数水平，挑到一个异常月就能把归因说反。'
    + (('两块乘上与本图同一个重标定权重 w，因此<b>逐年相加恰好等于上面「均价的贡献」'
        '那一块</b>，可以直接对上（单位同为百分点）：'
        + '；'.join(f'{y} 价 {_pp(p)} = 市场 {_pp(i)} + 结构 {_pp(m)}'
                    for y, p, i, m in _IDX)
        + '。以上逐年对账只覆盖<b>完整日历年</b>；末尾的 YTD 格窗口与此不同，'
          '其「均价的贡献」以图上读数为准，这里不另拆市场/结构。')
       if _IDX else
       '（本次未能从 CSV 算出逐年读数，此处只给方法不给数字。）')
    + '<b>⚠️ 这一层只对 TSX 成立。</b>S&P/TSX Composite 不含 TSX Venture，'
      '拿它去除 TMX 合计的均价，分母里混着仙股，算出来的「结构」有一大截只是 venue 混合比例。'
      '本页三张分解图因此一律画 TSX 主板，TMX 合计只作为第三张图的 bench 出现。'
)

# ── 图 B（笔数 × 每笔金额）的图注：三因子在这里报全 ────────────────────────
_NOTE_TRADE = (
    '<b>这张与上一张合起来就是三因子。</b>'
    '恒等式 成交额 ≡ 笔数 × 每笔股数 × 均价 三项都有列'
    '（<code>tsx_transactions</code> / <code>tsx_volume_shares</code> / '
    '<code>tsx_value_cad</code>），但底座的三分法是「行业 / 份额 / 结构」形状 ——'
    '把笔数塞进 bench 虽然凑得出三块，图注却会跟着印出「份额 ≡ 股数 ÷ 笔数」'
    '「结构 ≡ 自家均价 ÷ 行业均价」「⚠️ 分子必须是分母的子集」三句不成立的话。'
    '<b>图注说假话的代价高于少画一块柱</b>，所以拆成两张两分法，三项读数在这里报全'
    '（同一个重标定权重 w，三项相加逐年等于菱形上的总增长）：'
    + ('；'.join(f'{y} 总 {g:+.1f}% = 笔数 {_pp(t)} + 每笔股数 {_pp(s)} + 均价 {_pp(p)}'
                 for y, g, t, s, p in _3F)
       + '。以上三因子读数只覆盖<b>完整日历年</b>；末尾的 YTD 格不在此列，'
         '两张图各自 YTD 格的读数以图上为准。' if _3F else
       '（本次未能从 CSV 算出逐年读数。）')
    + '<b>⚠️「每笔平均成交额」不是价。</b>它衡量的是订单碎片化程度 —— '
      '同一笔母单被切成更多子单，笔数上升、每笔金额下降，而成交额与股价一点没变。'
      '要读价请看上一张图。'
)

# ── 图 C（三分法）的图注：子集关系与 2023-11 的口径楔子 ────────────────────
_NOTE_SHARE = (
    '<b>子集关系是精确成立的，不是近似。</b>SINGLE_SPEC §1.3.1 把「分子必须是分母的子集」'
    '列为 spec 作者的责任（底座验证不了）。本页的核实办法是撞恒等式：'
    'TMX 合计股数 ≡ TSX + TSXV + Alpha（+ 2023-11 起的 Alpha-X&DRK）'
    + (f'，全期最大残差 <b>{_BWR:.0f} 股</b>（即逐月分毫不差）。' if _BWR is not None
       else '，本次未能复算残差。')
    + '<b>⚠️ bench 在 2023-11 变大过一次。</b>合计口径自该月起纳入 Alpha-X & Alpha DRK，'
      '于是「TSX 股数份额」的**分母**一次性变大、份额被机械压低一点点。'
    + (f'这一点点有多大：Alpha-X&DRK 占合计股数最高只有 <b>{_BWX:.2f}%</b>'
       f'（{_BWM} 为 {_BWC:.2f}%），所以跨 2023 那一格的「份额」块里最多有 '
       f'{_BWX:.2f}pp 量级不是份额变化而是口径变化。' if _BWX else
       '本次未能量出它的幅度。')
    + '本页照实说明而不做剔除：把 Alpha-X&DRK 从合计里减掉等于自造一条官方没发过的序列。'
    + ('<b>「品种结构」这一块在读什么。</b>各 venue 的均价中位数实测：'
       + '、'.join(f'{k} {v:,.2f} C$/股' for k, v in _VP.items())
       + '。TSX 与 TSX Venture 差着一两个数量级（仙股主导），'
         '所以「TSX 均价相对集团」这一块量的就是成交在这两类票之间的迁移。'
       if _VP else '')
)

# ── ttm_yoy 两张图的图注 ──────────────────────────────────────────────────
_NOTE_TTM_MX = (
    '<b>柱与线的口径不同是有意的。</b>柱是 <code>mx_adv_contracts</code>（当月日均，'
    '官方直接发布），线的滚动合计取自 <code>mx_volume_contracts</code>（当月合计，'
    '同样官方直接发布）—— 两者谁也不从谁推。'
    '<b>本页不给 weight_col：</b>series/tmx.csv 里有 <code>trading_days_rates</code> 与 '
    '<code>trading_days_equity</code> **两套**交易日（每年 9 月与 11 月两者不等），'
    '而 MX 合计横跨利率与股票两侧，没有哪一套是对的。既然官方直接发布了当月合计，'
    '就用它，不做还原。'
)

_NOTE_TTM_SPOT = (
    '<b>柱与线取自同一列</b>（<code>tmx_all_volume_shares</code>，当月合计），'
    '所以这里没有任何「日均还原成合计」的步骤。'
    '<b>为什么现货这条要看滚动。</b>加拿大现货只有 2021-08 起的历史，'
    '而这段里既有 2023-11 的合计口径扩容、又有月度交易日数与到期周期的形状；'
    '任意连续 12 个月覆盖同一套日历，把这两层里的日历部分整个消掉。'
    '⚠️ 口径扩容那一层消不掉 —— 它是真实的覆盖范围变化，红色竖虚线标的就是它。'
)


# 断点标签**必须短**：它竖排画在断点线上，而断点线全长只有 ~254px，正中间还钉着
# 柱值标签（上段 ~112px、下段 ~133px）。原来那句「CDOR 停用，短端利率合约由 BAX 迁至
# CORRA（CRA）」竖排 180.5px，哪一段都塞不下，引擎只能靠 z 序兜底保住数字可读，
# 几何重叠仍在（tools/visual_qa.py 实测 8 条 🟡 全出自这一句）。
# ⇒ 标签的职责是**标记位置**，不是讲故事：缩到 10 个汉字以内，来龙去脉留给页尾 notes。
_BAX_ZH = 'BAX→CORRA 迁移'
_ALPHAX_ZH = 'TMX 合计口径扩容'

# 断点**逐列绑定**，不画成贯穿全页的红线。
# 不绑列的断点底座会画到本页每一张图上（`Page.breaks_for()` 里 b['col'] 为空就放行），
# 实测后果：「CDOR 停用…」这条利率合约迁移的红线出现在 S&P/TSX Composite 月末点位、
# Alpha-X 成交额、现货成交股数这些与它毫无关系的图上 —— 断点线的语义是
# 「这张图上这条序列从这一期起与左侧不可比」，标错比不标更糟（asx.py 记过同一条教训）。
_BAX_COLS = ('mx_adv_stir_futures_contracts', 'mx_adv_bax_contracts',
             'mx_adv_cra_contracts', 'mx_oi_stir_futures_contracts',
             'mx_oi_bax_contracts', 'mx_oi_cra_contracts')
# 口径扩容只改「TMX 合计」这三列的覆盖范围，外加 Alpha-X&DRK 自己那三列的起点。
# TSX / TSXV / Alpha 三档一列都没变，它们的图上不该出现这条线。
_ALPHAX_COLS = ('tmx_all_volume_shares', 'tmx_all_value_cad', 'tmx_all_transactions',
                'alphax_drk_volume_shares', 'alphax_drk_value_cad',
                'alphax_drk_transactions')


def _breaks():
    out = []
    # CDOR 停用 → 短端利率基准迁到 CORRA。BAX 的 ADV 转 0 的那个月就是迁移完成月。
    # 实测 = 2024-07（BAX 最后一个非零月是 2024-06，CRA 同月接棒）。
    # 只绑短端利率那六列：这是**产品替换**不是集团口径变化，
    # MX 合计跨这个月是连续的（BAX 掉多少 CRA 接多少），所以合计那几列不标。
    m = _first_zero_after_nonzero('mx_adv_bax_contracts')
    if m:
        out += [{'month': m, 'col': c, 'zh': _BAX_ZH} for c in _BAX_COLS]
    # tmx_all_* 的覆盖范围在 Alpha-X & Alpha DRK 单列之后变大。
    # 实测恒等式：2023-10 及之前 tmx_all = TSX + TSXV + Alpha（差恰为 0）；
    # 2023-11 起 tmx_all = 三家 + Alpha-X&DRK（差同样恰为 0，见 _bench_wedge()）。
    m = _first_present('alphax_drk_volume_shares')
    if m:
        out += [{'month': m, 'col': c, 'zh': _ALPHAX_ZH} for c in _ALPHAX_COLS]
    # 两条断点的推导顺序与时间顺序不同（BAX 那条在前推出、月份却在后），
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 这里统一按月份排。
    return sorted(out, key=lambda b: (b['month'], b['col']))


SPEC = {
    'ticker': 'tmx',
    'name': 'TMX Group',
    'title': '多伦多交易所集团（TMX）月度经营指标',
    'csv': 'tmx.csv',
    'ccy': 'CAD',
    'source': ('Source: Montréal Exchange monthly statistics (m-x.ca) and '
               'TMX Group Consolidated Trading Statistics press releases; '
               'format after Goldman Sachs GIR'),

    # 头条只有 MX 一条 —— 见文件抬头第 1 条。
    # 2002-01 起逐月无洞（实测 295/295），次月第 1–4 个工作日发布，是本页最快、最长的序列。
    'headline': [
        {'col': 'mx_adv_contracts', 'zh': 'MX 衍生品 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        # 合计与期货 / 期权三条同为 contracts/day，**必须放在同一组**。
        # 分成两组的代价不是排版：底座对「一个单位桶里只有一列」的组画 gs_bar，
        # 而 gs_bar 的次轴是**单月同比**。tools/check_yoy_caliber.py 实测本页
        # 「MX 日均成交」曾有 2 个月与 12 个月滚动口径**符号相反**
        # （单月 −1.2% 而滚动 +17.0%）—— 读者从图上看不出该信哪一个。
        # 三条同轴之后这张变成 lines，不再有次轴同比；MX 的滚动同比改由末尾
        # 'ttm_yoy' 那张专图给（口径写在标题里）。
        {'zh': 'MX 衍生品 ADV（2002-01 起）', 'cols': [
            {'col': 'mx_adv_contracts', 'zh': '日均成交',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_futures_contracts', 'zh': '期货 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_options_contracts', 'zh': '期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        # 当月合计单独一列、单位 contracts/month，本表里没有第二条同单位的列可以同轴，
        # 所以它注定是 gs_bar + 单月同比。**口径写进组名**（组名会进图题）：
        # 契约允许用单月同比，条件是标题里声明（CONTRACT.md §6）。
        # 这一组只有这一列，所以声明不会误标到别的图上。
        {'zh': 'MX 当月成交总量（次轴：单月同比）', 'cols': [
            {'col': 'mx_volume_contracts', 'zh': '当月成交',
             'unit': 'contracts/month', 'fmt': 'f0c'},
        ]},

        # 存量单列一组：点对点同比对期末口径是合法读法，这里保留它。
        # ⚠ 给下一个改这里的人：**「存量不能做滚动」是一句错话**。12 个月合计比恒等于
        #   12 个月均值比（除数 12 约掉，build/yoy.py 实测差 2.3e-14），所以存量序列
        #   画滚动窗口同比在数值上完全正确 —— 错的只是**把它叫「合计」**
        #   （12 个月末未平仓相加不指代任何真实的量）。要平滑就走
        #   `yoy.ttm_mean_yoy(s, kind)` 并写成「12 个月滚动**均值**同比」。
        {'zh': 'MX 月末未平仓（存量，期末口径）', 'cols': [
            {'col': 'mx_oi_contracts', 'zh': '月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # 本页第二重要的一张：基准利率换代时旗舰合约的整体搬迁。
        {'zh': '短端利率 ADV：BAX → CORRA 迁移', 'cols': [
            {'col': 'mx_adv_stir_futures_contracts', 'zh': '短端利率合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_bax_contracts', 'zh': 'BAX（CDOR，已停）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cra_contracts', 'zh': 'CRA（CORRA）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '短端利率月末未平仓', 'cols': [
            {'col': 'mx_oi_stir_futures_contracts', 'zh': '短端利率合计',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_bax_contracts', 'zh': 'BAX（CDOR，已停）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cra_contracts', 'zh': 'CRA（CORRA）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '国债期货 ADV', 'cols': [
            {'col': 'mx_adv_bond_futures_contracts', 'zh': '国债期货合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgb_contracts', 'zh': 'CGB（10 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgf_contracts', 'zh': 'CGF（5 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgz_contracts', 'zh': 'CGZ（2 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '国债期货月末未平仓', 'cols': [
            {'col': 'mx_oi_bond_futures_contracts', 'zh': '国债期货合计',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cgb_contracts', 'zh': 'CGB（10 年）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '股指期货', 'cols': [
            {'col': 'mx_adv_index_futures_contracts', 'zh': '股指期货合计 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_sxf_contracts', 'zh': 'SXF（S&P/TSX 60）ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_oi_sxf_contracts', 'zh': 'SXF 月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '个股与 ETF 期权', 'cols': [
            {'col': 'mx_adv_equity_options_contracts', 'zh': '个股期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_etf_options_contracts', 'zh': 'ETF 期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_share_futures_contracts', 'zh': '个股期货 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_oi_equity_options_contracts', 'zh': '个股期权月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_etf_options_contracts', 'zh': 'ETF 期权月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # ── 以下全是慢腿（2021-08 起，比 MX 晚一档发布）────────────────
        {'zh': '加拿大现货成交额（2021-08 起，慢腿）', 'cols': [
            {'col': 'tmx_all_value_cad', 'zh': 'TMX 合计',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'tsx_value_cad', 'zh': 'TSX',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'tsxv_value_cad', 'zh': 'TSX Venture',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'alpha_value_cad', 'zh': 'TSX Alpha',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
        ]},

        {'zh': '加拿大现货成交股数（2021-08 起，慢腿）', 'cols': [
            {'col': 'tmx_all_volume_shares', 'zh': 'TMX 合计',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'tsx_volume_shares', 'zh': 'TSX',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'tsxv_volume_shares', 'zh': 'TSX Venture',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'alpha_volume_shares', 'zh': 'TSX Alpha',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
        ]},

        {'zh': '加拿大现货成交笔数（2021-08 起，慢腿）', 'cols': [
            {'col': 'tmx_all_transactions', 'zh': 'TMX 合计',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'tsx_transactions', 'zh': 'TSX',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'tsxv_transactions', 'zh': 'TSX Venture',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'alpha_transactions', 'zh': 'TSX Alpha',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
        ]},

        {'zh': '月末指数点位（2021-08 起，慢腿）', 'cols': [
            {'col': 'tsx_composite_close', 'zh': 'S&P/TSX Composite',
             'unit': 'index level', 'fmt': 'f0c', 'stock': True},
            {'col': 'tsxv_composite_close', 'zh': 'S&P/TSX Venture Composite',
             'unit': 'index level', 'fmt': 'f1', 'stock': True},
        ]},

        # 三列三个单位 ⇒ 三个单桶 ⇒ 三张 gs_bar，次轴都是单月同比，而本表里
        # 没有任何同单位的第二条列可以同轴（Alpha-X&DRK 只有这一档）。
        # 所以口径写进组名 —— 这一组的三张图全都适用，不会误标到别处。
        # 实测（tools/check_yoy_caliber.py）：成交额那条有 1 个月与滚动口径符号相反
        # （2025-12 单月 −2.8% 而滚动 +83.2%）。
        {'zh': 'Alpha-X & Alpha DRK（2023-11 起，慢腿；次轴：单月同比）', 'cols': [
            {'col': 'alphax_drk_value_cad', 'zh': '成交额',
             'unit': 'C$bn/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'alphax_drk_volume_shares', 'zh': '成交股数',
             'unit': 'bn shares/month', 'fmt': 'f3', 'scale': 1e-9},
            {'col': 'alphax_drk_transactions', 'zh': '成交笔数',
             'unit': 'mn trades/month', 'fmt': 'f3', 'scale': 1e-6},
        ]},
    ],

    # 17 条现货列全部是慢腿：它们与 MX 不同源、晚一档发布，最新月留空是正常状态。
    # 不这么标，整页的发布门槛会被现货那半边永久拖住一个月。
    'slow_cols': [
        'tmx_all_volume_shares', 'tmx_all_value_cad', 'tmx_all_transactions',
        'tsx_volume_shares', 'tsx_value_cad', 'tsx_transactions', 'tsx_composite_close',
        'tsxv_volume_shares', 'tsxv_value_cad', 'tsxv_transactions', 'tsxv_composite_close',
        'alpha_volume_shares', 'alpha_value_cad', 'alpha_transactions',
        'alphax_drk_volume_shares', 'alphax_drk_value_cad', 'alphax_drk_transactions',
    ],

    'breaks': _breaks(),

    # ══ 量价分解：三张图，同一个业务（TSX 主板）三个视角 ══════════════════════
    # 为什么是 TSX 而不是 TMX 合计、为什么三因子拆成两张图，见模块 docstring。
    # 三张都 granularity='monthly_total'：series/tmx.csv 的现货三类列都是**原始月度合计**
    # （2026-06 tsx_value_cad = 456,631,843,665 加元 / tsx_volume_shares = 10,796,096,148 股 /
    #  tsx_transactions = 29,942,529 笔），不是日均。
    # ⇒ 一律**不给** weight_col：声明 monthly_total 又给 weight_col 是硬失败，
    #   而真乘上去会把年度合计放大二十几倍，图形却照常画得出来。
    # scale 只做显示换算（金额 ×1e-9 → C$bn、股数 ×1e-9 → bn shares、笔数 ×1e-6 → mn trades），
    # 它在分子分母上同时出现，对分解结果一个数都不影响。
    'decomp': [
        # ── 图 A：量 × 价。派生量是成交量加权平均成交价 ⇒ kind='share_price'。
        {'zh': 'TSX 主板成交额',
         'kind': 'share_price',
         'granularity': 'monthly_total',
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_volume_shares', 'zh': 'TSX 成交股数',
                 'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         # C$bn ÷ bn shares = C$/股，两边的 1e9 自己抵掉 ⇒ price_scale 用缺省 1.0。
         'price_zh': '加权平均成交价',
         'price_unit': 'C$/share',
         'price_fmt': 'f2',
         # TMX 的财年就是日历年（10-K/年报截至 12-31）⇒ year_start_month=1。
         # 日历年下 year_label 只能是 'start'（底座硬失败挡 'end'），
         # 而且日历年的柱标签直接印年份、不带 FY 前缀，不存在偏一年的风险。
         'year_start_month': 1, 'year_label': 'start',
         # 用户指令（2026-08-07）：四家分解图统一「4 根完整日历年柱 + 1 根当年 YTD」。
         # 现货只有 2021-08 起的历史 ⇒ 完整日历年 2022…2025 共 4 个 ⇒ 目前画得出
         # 3 根完整年柱（底座取 run[-(years+1):]，够几根画几根，明年自动多一根）；
         # 最新年不完整时底座自动补 YTD 柱（两侧月份对齐去年同期，见 single._ytd）。
         'years': 4,
         'note': _NOTE_PRICE},

        # ── 图 B：笔数 × 每笔金额。派生量是每笔平均成交额 ⇒ kind='per_trade'。
        #    ⚠ 绝不能写 share_price：底座会据 kind 印出「它不是什么」那段话，
        #      把「订单碎片化程度」说成「价格」是本批最容易犯的错。
        {'zh': 'TSX 主板成交额（按成交笔数拆）',
         'kind': 'per_trade',
         'granularity': 'monthly_total',
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_transactions', 'zh': 'TSX 成交笔数',
                 'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
         # C$bn ÷ mn trades = 1e-3 × (C$/笔) ⇒ price_scale=1e3 换回 C$/笔。
         # 纯单位换算，对增长率没有任何影响，只决定图注里报出来的水平值读数。
         'price_zh': '每笔平均成交额',
         'price_unit': 'C$/trade',
         'price_fmt': 'f0c', 'price_scale': 1e3,
         # years=4：同图 A（4 根完整日历年柱 + YTD，数据够时）。
         'year_start_month': 1, 'year_label': 'start', 'years': 4,
         'note': _NOTE_TRADE},

        # ── 图 C：三分法。bench = TMX 集团合计，子集关系逐月精确成立（见 _NOTE_SHARE）。
        #    行业块 = 集团整体在动多少；份额块 = TSX 在集团里的股数份额；
        #    结构块 = TSX 均价相对集团（成交在贵票 / 仙股之间的迁移）。
        #    ⚠ bench 两列必须与自家两列**同一套 granularity / 同样不给 weight_col**，
        #      否则份额 s 会带一条逐月漂移的假趋势。
        {'zh': 'TSX 主板成交额（相对 TMX 集团）',
         'kind': 'share_price',
         'granularity': 'monthly_total',
         'value': {'col': 'tsx_value_cad', 'zh': 'TSX 成交额',
                   'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'qty': {'col': 'tsx_volume_shares', 'zh': 'TSX 成交股数',
                 'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         'bench_value': {'col': 'tmx_all_value_cad', 'zh': 'TMX 集团合计成交额',
                         'unit': 'C$bn/month', 'fmt': 'f0c', 'scale': 1e-9},
         'bench_qty': {'col': 'tmx_all_volume_shares', 'zh': 'TMX 集团合计成交股数',
                       'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         'share_zh': 'TSX 在集团内的股数份额',
         'mix_zh': 'TSX 均价相对集团（品种结构）',
         'price_zh': '加权平均成交价',
         'price_unit': 'C$/share',
         'price_fmt': 'f2',
         # years=4：同图 A（4 根完整日历年柱 + YTD，数据够时）。
         'year_start_month': 1, 'year_label': 'start', 'years': 4,
         'note': _NOTE_SHARE},
    ],

    # ══ 水平值 + 12 个月滚动同比 ═════════════════════════════════════════════
    # 两条腿各给一张：MX 衍生品（2002-01 起，本页最长）与加拿大现货（2021-08 起）。
    'ttm_yoy': [
        {'zh': 'MX 衍生品成交量',
         # mx_adv_contracts 是当月**日均**（官方直接发布，不是本仓算的）。
         'granularity': 'daily_avg',
         'level': {'col': 'mx_adv_contracts', 'zh': '日均成交',
                   'unit': 'contracts/day', 'fmt': 'f0c'},
         # 官方同时发布当月合计，直接拿它滚 12 个月 —— 比「日均 × 交易日」可信，
         # 而且本表的两套交易日列（rates / equity）谁也不能单独代表 MX 合计。
         'total_col': 'mx_volume_contracts',
         'note': _NOTE_TTM_MX},

        {'zh': 'TMX 合计现货成交股数',
         'granularity': 'monthly_total',
         'level': {'col': 'tmx_all_volume_shares', 'zh': '当月成交股数',
                   'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
         # 不给 total_col / weight_col：level 那一列本身就是当月合计，
         # 底座直接拿它滚 12 个月，柱与线同口径。
         'note': _NOTE_TTM_SPOT},
    ],

    'notes': [
        '本页有**两段起点差 19 年的历史**：MX 衍生品自 2002-01（实测 295 个月零断档），'
        '加拿大现货自 2021-08（实测 59 个月零断档）。两者不是同一段历史，'
        '任何「TMX 从 2002 年以来如何」的说法只对 MX 成立。'
        '现货更早的数据只存在于 tmx.com/en/resource 的 PDF 里，'
        '而该域对本网络返回 CloudFront 403（curl / urllib / nscurl / curl_cffi / '
        '本机真实 Chrome 实测全部 403），没有合规通道，属数据不可得而非本页取舍。',

        '现货比 MX 晚一档发布：写这份配置的 2026-08-06，MX 已有 2026-07、现货仍停在 2026-06。'
        '所以 17 条现货列全部标为 slow_cols，最新月留空是正常状态，不参与发布门槛。',

        '短端利率合约在 2024-07 完成基准换代：CDOR 停用，BAX 的 ADV 自该月起为 0'
        '（最后一个非零月是 2024-06），CORRA 合约 CRA 接棒。'
        '实测 2026-07：CRA ADV 191,902 张/日、BAX 0、短端利率合计 192,122 张/日。'
        '本页把 BAX 与 CRA 画在一起而不是各画各的 —— 只看其中一条会得到「短端利率业务'
        '归零」或「凭空长出一个新产品」两个都不对的结论。断点月份由 series/tmx.csv '
        '里 BAX 转 0 的那一月读出，没有写死。'
        '图上那条红线的标签只写「BAX→CORRA 迁移」——**标签的职责是标记位置**，'
        '来龙去脉在这一条里；标签写长了会竖排压住柱值数字（断点线全长只有 254px，'
        '中间还钉着柱值标签）。这条线**只画在短端利率那六列的图上**：'
        '它是产品替换不是集团口径变化，MX 合计跨这个月是连续的（BAX 掉多少 CRA 接多少），'
        '画到指数点位、现货成交这些图上就是错的。',

        'TMX 合计口径在 2023-11 变大：Alpha-X & Alpha DRK 自该月起单独披露并计入合计。'
        '实测恒等式核过 —— 2023-10 及之前 tmx_all_volume_shares 恰等于 TSX + TSXV + Alpha 三家之和'
        '（差为 0）；2023-11 起恰等于三家 + Alpha-X&DRK（2026-06 该项 33,865,231 股）。'
        '所以合计序列跨 2023-11 不可直连。'
        '图上那条红线的标签只写「TMX 合计口径扩容」（理由同上：标签要短），'
        '且**只画在受影响的六列上** —— TMX 合计三列（覆盖范围变大）与 Alpha-X&DRK 三列'
        '（序列自此开始）。TSX / TSXV / Alpha 三档一列都没变，它们的图上不该有这条线。',

        '**现货三类列在 series/tmx.csv 里是原始单位**：实测 2026-06 '
        'tsx_value_cad = 456,631,843,665（加元）、tsx_volume_shares = 10,796,096,148（股）、'
        'tsx_transactions = 29,942,529（笔）。直接上图轴刻度会是 11–12 位数，'
        '所以本页用 spec 的 scale 字段做**纯显示换算**：金额 ×1e-9 → C$bn、'
        '股数 ×1e-9 → bn shares、笔数 ×1e-6 → mn trades。'
        'scale 只影响本页的显示，series/tmx.csv 与 build/notional.py 读到的仍是原值，'
        '删掉本文件这些除数即随之消失，不碰任何公共代码。'
        'MX 那半边的张数（2026-07 ADV 918,716 张/日）量级本来就可读，不做换算。',

        'BOX 期权做不出月度序列：TMX 官方只在季度 MD&A 里按季披露（series/tmx_box_q.csv，'
        '实测 8 行 2024-Q3 → 2026-Q2），BOX 自身站点也不发月度统计。'
        '本页是月频页，不收季频列。',

        '本页全部金额为加元。跨币种比较由 build/notional.py 统一换算：'
        '流量（成交额、成交股数/笔数）配月均汇率，存量（月末未平仓、月末指数点位）配月末汇率。',

        '未上页面的月频列：mx_adv_index_options_contracts（最后一个非零月 2020-10，'
        '此后 68 个月全为 0 的死列）、trading_days_rates 与 trading_days_equity'
        '（两套分母，每年 9 月与 11 月两者不等；ADV 官方直接给，本页不做除法）。',
    ],
}
