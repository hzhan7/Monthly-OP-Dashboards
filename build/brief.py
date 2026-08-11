# -*- coding: utf-8 -*-
"""看板页顶部 ~300 字数据总结（payload 的 `brief` 字段）的**规则库**。

═══ 这一段的职责 ═══
一行数据条（`headline`）给的是**读数**，brief 给的是**读数该怎么读**。
所以 brief 刻意不复述 headline 与 Exhibit 1 已经印过的数字 —— 仓库既有的
「规矩 13：只留一行数据条，叙述性 bullets 里的数字全部在下面的表和图里」
禁的就是那种复述式摘要。brief 只写图表本身讲不出来的三件事：

    基数效应（这个环比是被上月的极值顶出来的吗）
    口径背离（总量在涨而单位量在跌吗；哪个指标与其余指标反向）
    所处区间（这个读数在全样本里是什么位置）

═══ 为什么是「规则库 + 各家自己拼句子」而不是一个通吃的模板函数 ═══
12 家的列长得完全不一样：IBKR 有交易日与账户数，CME 披露的直接就是 ADV，
COST 是 4-4-5 零售周，AXP 全是**越低越好**的反向比率。一个吃 spec 的通用
composer 要么退化成「本月 X 为 N，同比 Y%」的填空（那就成了被禁的复述式摘要），
要么把 12 家的特例全塞进参数里而没人看得懂。

所以这里只提供**算事实**的函数（返回数字与判定，不返回文字），句子由各家的
`build/<t>.py::compose_brief()` 自己拼 —— 措辞是口径的一部分，属于各家自己。

═══ 六条规则 ═══
  R1 峰值扫描   `peak_scan()`。对**存量**列取 argmax，报本月命中了哪几个、没命中的
                峰值停在哪个月。防「看到一个新高就以为全线新高」。
  R2 基数护栏   `base_effect()`。m/m 与 y/y 反号时必须补一句基数说明；上月若处在
                全样本前三高，必须同句给出上月的排名。本项目最高频的误读源。
  R3 日历护栏   `calendar_split()`。**只对「当月合计量」列成立**。交易日/周数环比
                变动时，同时给出表面 m/m 与日均 m/m。
  R4 单位恒等   `per_unit()`。人均/户均指标的同比 ≡ 分子同比 ÷ 分母同比，只能报两个
                增速之商，不能写成「一半分子一半分母」的比例拆分（那是错的）。
  R5 标注规则   A/B 形式而公司只披露 A 与 B 的，正文必带「（推导值）」；命中公司
                Notes 一次性调整的，必带「（还原口径）」。由各家自己在句子里写。
  R6 有效位     `usd()` / `num()` / `pct()`。$ 取整、bn 一位、% 一位，同页统一。

═══ 三个最容易踩的坑 ═══
  · **R3 会造假修正**：CME / CBOE / HKEX / SPGI 披露的本来就是 ADV（已经日均化），
    再除一次交易日是错的。判据不是「有没有交易日列」，而是「这一列是当月合计还是
    已经日均」。COST 的对应物是 4-4-5 的 `weeks`（5 周月 vs 4 周月），不是交易日。
  · **反向指标**（AXP 的 dq30/nco 逾期率与坏账率、任何「越低越好」的比率）：
    `peak_scan()` 的「创新高」在那里意味着**坏消息**，必须传 `inverse=True`，
    否则会写出「唯一创新高」这种把风险读成利好的句子。
  · **单调序列**：累计资产、仓库数这类几乎只增不减的列，「又创新高」每个月都成立，
    是噪音不是信息。`is_monotonic()` 用来把它们挡在 R1 之外。
"""
import re

import numpy as np

# ── R6：有效位。同页统一，别各写各的 ──────────────────────────────────────
CN = '一二三四五六七八九十'


def cn(v, ordinal=False):
    """小计数写中文数字：「4个总量指标」在一句中文里读起来像个金额，「四个」才是量词。

    只覆盖 1-10；超出退回阿拉伯数字（两位数的中文反而更难读）。

    **2 作基数词时是「两」不是「二」**（两个品种 / 第二高）。这条不给各家自己贴补丁：
    第一轮铺开时 cme.py 就在本地包了一层 `.replace('二个','两个')`，而 ibkr、cost 等
    页面同样会在计数为 2 时印出「二个」—— 同一条中文规矩在 14 个文件里各修一次，
    必然漏。ordinal=True 时保留「二」，供「第二」这类序数使用。
    """
    if not 1 <= v <= 10:
        return str(v)
    return CN[v - 1] if (ordinal or v != 2) else '两'


def quant(k, n, noun=''):
    """计数 + **跟着数字走的量词**。写「只有一个」这种定性词时一律走这里。

    为什么需要它：审查里逮到的最隐蔽的一类 bug 是「写死的措辞 + 算出来的数字」——
    句子写成 f'六个品种里上行的只有{cn(k)}个'，本月 k=1 读着通顺，但 k 是当场算的，
    下个月 k=6 就会印出「六个里只有六个」，把全线上涨写成稀缺。CME 的历史重放里
    199 个月有 108 个月（54%）会印出这种自相矛盾的句子。

    判据：占比 ≤1/3 才配「只有」，≥2/3 用「多达」，中间用中性的「有」。
    """
    word = '只有' if n and k / n <= 1 / 3 else ('多达' if n and k / n >= 2 / 3 else '有')
    return f'{word}{cn(k)}{noun}'


def need(*vals):
    """全部有限才返回 True。用来在拼句子之前挡住缺值。

    本仓的规矩是「失败要响」，但那针对的是**数据错**；brief 是页面上的一段解读，
    某个月某一列恰好没有读数是常态（Cboe 的 RPC 滞后一月、HKEX 的 new_listings
    月中才发、CME 的 open-outcry 在 2021-04 整列缺）。正确处理是**这一句不写**，
    而不是整页构建失败 —— 后者会让一个可发布的月份因为一句解读发不出去。

    用法：`if not B.need(a[i], a[i-12]): s3 = ''`
    """
    try:
        return all(v is not None and np.isfinite(float(v)) for v in vals)
    except (TypeError, ValueError):
        return False


def top_pct(rank, n):
    """名次 → 「前 N%」。**向上取整**，不能用四舍五入。

    223 个月里排第 23，23/223 = 10.31%，而「前 10%」的边界是第 22.3 名 ——
    第 23 名恰恰在前 10% 之外，四舍五入却会印出「前 10%」。这类朝好看方向的
    舍入在一个公开页面上就是假话。向上取整还能顺带修掉「第 1 名 → 前 0%」。
    """
    import math
    return f'前{math.ceil(rank / n * 100)}%'


def pct(v, d=1, sign=True):
    """比率 → 百分比串。v 传的是**小数**（0.426 → '+42.6%'）。

    四舍五入后为 0 时不带符号 —— '-0.0%' 是格式化产物不是数据，夹在一片两位数里
    会让读者停下来猜它是不是缺失值（同一个毛病在 tsm Ex12 被人眼审查逮到过）。
    """
    s = f'{v * 100:+.{d}f}' if sign else f'{v * 100:.{d}f}'
    if float(s) == 0:
        s = f'{0.0:.{d}f}'
    return s + '%'


def num(v, d=1):
    """千分位数值。负零一律去掉负号。"""
    s = f'{v:,.{d}f}'
    if s.startswith('-') and float(s.replace(',', '')) == 0:
        s = s[1:]
    return s


def usd(v, d=0):
    """美元金额。R6：$ 取整（除非显式给 d）。"""
    return '$' + num(v, d)


def mo(key):
    """'YYYY-MM' → 月份数字（写「停在5、6月」用）。"""
    return int(key[5:7])


# ── 序列判定的公共件 ─────────────────────────────────────────────────────
def _fin(a):
    """有限值掩码。NaN 必须显式排除：np.argmax 遇 NaN 返回 NaN 的位置，
    「峰值停在 X 月」会指到一个缺月上，而且不报错。"""
    return np.isfinite(np.asarray(a, float))


def rank_of(a, i):
    """a[i] 在全序列里降序第几名（1 = 最高）。NaN 不参与计数。"""
    a = np.asarray(a, float)
    if not np.isfinite(a[i]):
        return None
    return int(np.sum(a[_fin(a)] > a[i])) + 1


def is_monotonic(a, thresh=0.9):
    """几乎只增不减？累计资产、仓库数这类序列「又创新高」每月都成立，是噪音。

    判据与 CONTRACT §2 给分位留空用的是同一条（diff >= 0 的比例 ≥ 90%）——
    口径只能有一处定义，各写各的正是同一条序列在两页判定相反的原因。
    """
    a = np.asarray(a, float)
    d = np.diff(a[_fin(a)])
    return len(d) > 0 and float(np.mean(d >= 0)) >= thresh


def months_since_lower(a, i, inverse=False):
    """上一次比 a[i] 更低（inverse 时更高）是多少个月以前。没有过则返回 None。

    用来写「为 14 个月最低」。返回 None 表示这就是全样本极值，句子该改写成
    「为 N 个月最低」里的 N = 全长。
    """
    a = np.asarray(a, float)
    hit = [j for j in range(i) if np.isfinite(a[j]) and (a[j] > a[i] if inverse else a[j] < a[i])]
    return (i - hit[-1]) if hit else None


# ── R1：峰值扫描 ─────────────────────────────────────────────────────────
def peak_scan(months, stocks, i, inverse=False, skip_monotonic=True):
    """存量列的峰值扫描。

    stocks: [(名称, 序列), ...]，只放**存量/水平值**，不要放流量。
    inverse: 序列越低越好（逾期率、坏账率）时传 True —— 此时「极值」取 argmin，
             且调用方必须把措辞从「创新高」改成「升至最高」这类中性/负面表述。
    skip_monotonic: 剔掉几乎只增不减的列（它们每月都「创新高」，是噪音）。

    返回 {'at_peak': [名称], 'off_peak': [(名称, 'YYYY-MM')], 'skipped': [名称]}
    """
    at, off, skipped = [], [], []
    for nm, a in stocks:
        a = np.asarray(a, float)
        if skip_monotonic and is_monotonic(a) and not inverse:
            skipped.append(nm)
            continue
        if not np.isfinite(a[i]):
            continue
        # 「峰值停在 X 月」的语义是**最近一次**触及极值 —— nanargmax/nanargmin 返回的是
        # **第一次**。披露值常带舍入（AXP 逾期率 1.3% 在 2024 年三个月里三次触底），
        # 取第一次会让读者以为此后再没到过。所以先取极值、再取命中集合的最后一个。
        ext = np.nanmin(a) if inverse else np.nanmax(a)
        hits = np.flatnonzero(np.isfinite(a) & (a == ext))
        k = int(hits[-1])
        (at if k == i else off).append(nm if k == i else (nm, months[k]))
    return {'at_peak': at, 'off_peak': off, 'skipped': skipped}


def peak_months_txt(off_peak):
    """[(名, 'YYYY-MM')] → '5、6'（去重升序的月份数字串）。"""
    return '、'.join(str(x) for x in sorted({mo(k) for _, k in off_peak}))


# ── R2：基数护栏 ─────────────────────────────────────────────────────────
def base_effect(a, i, lag=12):
    """本月 m/m、y/y、上月排名，以及「环比与同比反号」这个触发条件。

    `conflict` 为 True 时**必须**在句子里补基数说明，否则读者会把一个由上月极值
    造成的环比读成趋势反转。`prev_rank` 用来写「但上月是全样本最高月」。
    """
    a = np.asarray(a, float)
    out = {'mm': None, 'yy': None, 'prev_rank': None, 'prev_is_max': False,
           'conflict': False, 'rank': rank_of(a, i)}
    if i >= 1 and np.isfinite(a[i]) and np.isfinite(a[i - 1]) and a[i - 1] != 0:
        out['mm'] = float(a[i] / a[i - 1] - 1)
        out['prev_rank'] = rank_of(a, i - 1)
        out['prev_is_max'] = out['prev_rank'] == 1
    if i >= lag and np.isfinite(a[i]) and np.isfinite(a[i - lag]) and a[i - lag] != 0:
        out['yy'] = float(a[i] / a[i - lag] - 1)
    if out['mm'] is not None and out['yy'] is not None:
        out['conflict'] = (out['mm'] < 0) != (out['yy'] < 0)
    return out


# ── R3：日历护栏 ─────────────────────────────────────────────────────────
def calendar_split(total, days, i):
    """把「当月合计量」的环比拆成表面变化与日均变化。

    ⚠ 只对**当月合计**的列用（成交量、合约数、股数、营收）。公司披露的若本来就是
    ADV / 日均（CME、CBOE、HKEX、SPGI 都是），再除一次交易日会造出一个假修正。

    返回 {'raw', 'per_day', 'gap_pp', 'dday'}；`gap_pp` 是两者的百分点差 ——
    注意它**不等于**交易日的比例变化，它随跌幅深浅而变，不能写成固定值。
    """
    total, days = np.asarray(total, float), np.asarray(days, float)
    if not (np.isfinite(total[i]) and np.isfinite(total[i - 1])
            and np.isfinite(days[i]) and np.isfinite(days[i - 1])):
        return None
    raw = float(total[i] / total[i - 1] - 1)
    pd_ = total / days
    per_day = float(pd_[i] / pd_[i - 1] - 1)
    return {'raw': raw, 'per_day': per_day, 'gap_pp': (raw - per_day) * 100,
            'dday': float(days[i] - days[i - 1]), 'series': pd_}


# ── R4：单位恒等 ─────────────────────────────────────────────────────────
def per_unit(numer, denom, i, lag=12, scale=1.0):
    """户均/人均指标（推导值：公司披露分子与分母，不披露商）。

    恒等式：per_unit 的同比 ≡ (1+分子同比)/(1+分母同比) − 1。
    所以句子里只能报**两个增速之商**，绝不能写成「一半来自分子、一半来自分母」的
    比例拆分 —— 那个拆法在数学上就是错的。

    scale: 分子分母单位不一致时的换算系数（如 $bn ÷ 千户 → 元：1e9/1e3）。
    """
    numer, denom = np.asarray(numer, float), np.asarray(denom, float)
    pu = numer * scale / denom
    out = {'series': pu, 'value': float(pu[i]),
           'rank_low': rank_of(-pu, i), 'is_min': False, 'is_max': False}
    fin = _fin(pu)
    if np.isfinite(pu[i]):
        out['is_min'] = bool(pu[i] == np.nanmin(pu[fin]))
        out['is_max'] = bool(pu[i] == np.nanmax(pu[fin]))
    if i >= lag and np.isfinite(pu[i - lag]) and pu[i - lag] != 0:
        out['yoy'] = float(pu[i] / pu[i - lag] - 1)
        out['num_yoy'] = float(numer[i] / numer[i - lag] - 1) if numer[i - lag] else None
        out['den_yoy'] = float(denom[i] / denom[i - lag] - 1) if denom[i - lag] else None
    return out


# ── 期间均值对比（「相对起点下行」类判断）─────────────────────────────────
def regime_ratio(months, metrics, i, win=13):
    """首年年均 → 近 win 个月均值 的倍数，逐列算。

    主语必须是**期间均值对期间均值**。拿单月读数去除首年年均是另一个数，两者混编
    是审查里逮到过的硬伤。成交量类的列传进来之前要先日均化（除交易日），否则比值里
    混的是日历噪音。

    返回 [(名称, 倍数)]，以及 `down` = 倍数 < 1 的名称列表。
    """
    y0 = months[0][:4]
    base = [j for j, k in enumerate(months) if k[:4] == y0]
    w = list(range(max(0, i - win + 1), i + 1))
    out = []
    for nm, a in metrics:
        a = np.asarray(a, float)
        b, c = np.nanmean(a[base]), np.nanmean(a[w])
        if np.isfinite(b) and np.isfinite(c) and b != 0:
            out.append((nm, float(c / b)))
    return {'y0': y0, 'ratios': out, 'down': [nm for nm, r in out if r < 1],
            'base_idx': base, 'win_idx': w}


# ── 渲染 + 字数护栏 ──────────────────────────────────────────────────────
TITLE = '本月读数怎么读'


def render(sentences, title=TITLE, lo=230, hi=380):
    """句子列表 → brief 的 HTML。

    ═══ 篇幅 ═══
    目标 **~300 字**，250-350 都可接受（去掉 HTML 标签后的字符数）。
    这不是一个要卡死的数字 —— 护栏放到 230-380，只拦「模板拼坏了」那种量级的事故。
    卡死 280-330 会让某个月因为名次多了一位数就整页发不出去，那是拿公开页面的
    新鲜度换一个纯排版指标，不划算。

    ═══ 分寸：以 build/ibkr.py 为准（2026-08 定）═══
    这是**一段月度数字总结**，不是专题研究报告。分寸不靠形容词描述，靠一份样板钉死：

        **build/ibkr.py 的 compose_brief() 就是标准，既是上限也是下限。**

    它是用户逐句验收过的那一版。写别家时把成品和它并排读，比它花哨就是超了，
    比它单薄就是不够。四句话四个层次（规模 / 基数 / 日历 / 分母），每句一个意思。

    照它的样子，这些**可以写**：
      · 当月读数 + 它在历史里的位置（排第几 / N 个月最高或最低）
      · 相对表述（「四个总量指标里唯一创新高的」比「又创新高」有信息量）
      · 一句话基数提示（「6 月是全样本最高月，只看环比会误读成塌方」）
      · 口径调整（「7 月比 6 月多一个交易日，期权表面跌 6.7%、日均实跌 11.0%」）
      · 单位恒等式**加一句落点**（「户均现金…是客户现金 +25.1% 除以账户 +34.3% 的商，
        属摊薄而非撤资」）—— 恒等式后面接一个短结论是允许的，样板就这么写

    **不要写**（第一版 12 家普遍越的线）：
      · 三项以上的分解并逐项给金额贡献、带余项的加总、增长指数之商
      · OLS 区间检验、回撤恢复统计、贡献度拆解
      · 「流量 vs 存量口径分层」「互不印证」这类方法论议论
      · 写给构建者看的规则备忘（「表内已日均化，不能再除一次」之类）

    ── 分解到什么程度算 IBKR 深度 ──
    样板的 `户均现金同比 ≡ 现金同比 ÷ 账户同比`，是**二元恒等式 + 一句落点**。
    这个可以。再往上就超了：Cboe 第一版把 ΔRPC 拆成「结构 -1.46¢ / 费率 -0.22¢ /
    复原余项 -0.06¢」三项带余项，读者要做一次三项加法才能跟上 —— 同一个洞察压到
    样板深度是「RPC 环比跌 1.74¢，但指数期权 RPC 是 102 个月最高，跌的是结构不是单价」。
    **洞察保留，分解的层数收掉。**

    形式上：**一句话一个意思**。第一版铺开时 12 家普遍写成了 380 字的连续从句堆，
    括号套括号、破折号接破折号，读起来像脚注不像导读 —— 那是分寸失控的症状，
    不是字数问题，砍字数不会自动修好它。
    """
    body = ''.join(s for s in sentences if s)
    plain = re.sub(r'<[^>]+>', '', body)
    if not lo <= len(plain) <= hi:
        raise SystemExit(
            f'brief 长度 {len(plain)} 字超出 {lo}-{hi}，模板可能拼坏了：{plain[:140]}…')
    return f'<h4>{title}</h4><p>{body}</p>'
