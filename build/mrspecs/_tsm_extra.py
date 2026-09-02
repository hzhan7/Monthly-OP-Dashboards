# -*- coding: utf-8 -*-
"""台积电「非营收月度披露」板块 —— Exhibit 10 起的八张图，外加汇总表的三组附加行。

**为什么这一整块住在 mrspecs/ 而不是 mrbase.py**：底座是 34 个页面共用的，
里面每一行都会印到另外 33 页上。这八张图读的是**只有台积电才申报**的五张表 ——
另外六家台股页没有一家有董事會核准資本支出的英文披露，衍生性商品与背書保證的
表式也各不相同。所以它们是本家事实，按 mrspecs/tsm.py 文件头第 2 条的同一条理由
留在本家 spec 里。底座那边只加两个**纯位置性**的钩子（`summary_extra` /
`extra_exhibits`），不认识「台积电」三个字。

文件名以 `_` 开头是硬要求：`mrbase.all_tickers()` 把 `build/mrspecs/*.py` 里
不以下划线开头的都当成一个 ticker，取名 `tsm_extra.py` 会让 `--all` 去 build
一个不存在的公司。

━━ 五份数据的来源与口径 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. `tsm_capex_approvals.csv` 董事會核准資本支出 —— SEC 董事会当日 6-K（CIK 0001046179）。
   **不是 capex**：核准授权约为当年现金资本支出的 1.5–1.7 倍。
   只收 2016 起：更早有 4 次是新台币口径、3 个月一月两会，混进来会静默算错年度合计。
2. `tsm_derivatives.csv` 遠期外匯未平倉 —— MOPS ajax_t15sf。
   ⚠️ `未沖銷契約-契約總金額` 是**月底存量**；同表相邻的 `已沖銷` 才是年初至今累计、
   每年一月归零。两栏同名、相邻，解析错一行整条序列作废。
3. `tsm_guarantees.csv` 背書保證 —— approved 来自 MOPS ajax_t05st11，
   outstanding 只有 SEC 月度 6-K 有。**两者差约 26%，永远不可拼接成一条序列**。
4. `tsm_bonds_monthly.csv` / `tsm_bonds_tranches.csv` 公司債 —— MOPS ajax_t47sb17 +
   逐檔發行辦法登记簿 + FY2012~FY2019 Form 20-F 的 BONDS PAYABLE 逐檔表。
   月报表只留滚动 3 个月窗口，**整条序列里只有最近 3 个月来自月报表本身**，
   其余由券别登记簿与还本时程重建（月数别写死在这里，图注 `len(bmo)` 现算）。
   窗口起点由 `fetch/tsm.py` 的 `BONDS_FROM` 定，2026-08 从 2020-03 前移到
   2011-09 —— 理由（「能被 20-F 年末余额钉住的最早一个月」、以及为什么不到 2002）
   写在那个常量上方，别在这里复述第二份。
   **对账口径要说清是哪一段、对的是哪个子集**（这一句以前写成「已用六个 20-F 年末
   余额对账」，那是一句自我表扬式的假话，实测只有三年能对上）：
     · 现在：`python3 fetch/tsm.py bonds` 逐年打表。2011–2019 九个年末对
       `Domestic unsecured bonds` **零误差**（那几年这一行是纯新台币）；
       2020–2025 六个年末只能做**带宽核对** —— 那一行含在台发行的美元宝岛债，
       本序列有意剔除，残差 ÷ 宝岛债名目必须落在同月 H.10 月均的 ±3% 内。
       另有 6 个年份的 `Less: Current portion` 作为**独立的第二判据**验到期时程。
     · 曾经：登记簿里只有 109- 起（2020-03 首檔）的新券，漏了 100-/101-/102- 三个
       系列 2020 年后仍未到期的旧券，所以 2020-03…2023-09 这 43 个月的 outstanding
       系统性偏低（2020-03 24,000 vs 实际 59,300 NT$mn），wavg_coupon 更是被拉低
       近 63bp。那次「六个 20-F 零误差」实际只有 FY2023–FY2025 三年成立 ——
       恰好是旧券已全部到期（末檔 102-4F，2023-09）之后的三年。

━━ 刷新 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ **这五张表目前没有接进 `monthly_run.py`，不会自动更新。** 月营收往前走、它们
不走时，页面不会静默装作同月：`_lag_note()` 逐图现算各自的数据截止月，滞后就在
章节标题与图注里印出来。要自动化得给这五个源各写一个 fetcher —— 而且 TSM 的
`not_due()` 在营收到手后整月返回 NOCHANGE，董事会 6-K 是月中发的，
不能挂在现有的 `one('tsm')` 后面搭车。
"""
import os

import numpy as np
import pandas as pd

import mrbase
import mrwin                        # 只调用（MAX_XLABS / DENSE），不改它
from mrbase import L, mlab

_SEC = '非营收月度披露：台积电按月申报的另外五张表'

_S_CAPEX = ('Exhibit source: TSMC 董事会当日 Form 6-K（SEC EDGAR，CIK 0001046179），'
            '与月末 6-K 分项及 MOPS ajax_t05st01 三方对账')
_S_DERIV = ('Exhibit source: MOPS ajax_t15sf 衍生性商品交易情形'
            '（取得或處分資產處理準則 §31 第 4 項）')
_S_BOND = ('Exhibit source: MOPS ajax_t47sb17 公司債月報表 + 逐檔發行辦法登记簿 + '
           'FY2012–FY2019 Form 20-F 的 BONDS PAYABLE 逐檔表（CIK 0001046179）；'
           '年末对账见 build/mrspecs/_tsm_extra.py 文件头第 4 条')
_S_GUAR = ('Exhibit source: 核准数 MOPS ajax_t05st11、在外数 TSMC 月度 Form 6-K；'
           '美元化用本页汇率图同一条 H.10 月均汇率')

# 在外数窗口的起点。见 _load() 里那段注释：这个数**必须写死**。
_GUAR_FROM = pd.Period('2011-07', freq='M')


def _read(name):
    df = pd.read_csv(os.path.join(mrbase.SERIES, name))
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    return df.set_index('month').sort_index()


def _load(ds):
    d = {}
    d['cap'] = _read('tsm_capex_approvals.csv')['approved_usd_mn'].astype(float) / 1000.0
    d['gua'] = _read('tsm_guarantees.csv')
    d['bmo'] = _read('tsm_bonds_monthly.csv')
    d['btr'] = pd.read_csv(os.path.join(mrbase.SERIES, 'tsm_bonds_tranches.csv'))
    d['notional'] = (_read('tsm_derivatives.csv')['open_notional_ntd_k']
                     .astype(float) / 1e6)                              # NT$bn

    # 避险强度 = 名目 ÷ 月均营收（TTM ÷ 12）。分母不用当月营收：当月带农历年与季末
    # 拉货的锯齿，拿一个月底存量去除一个锯齿状流量，等于把分母的噪声灌进比值。
    ttm12 = ds.disp.rolling(12).sum() / 12.0
    ix = d['notional'].index.intersection(ttm12.dropna().index)
    d['cover'] = (d['notional'].reindex(ix) / ttm12.reindex(ix)).dropna()

    # 亚利桑那两条腿折成美元：美元计价、以新台币申报，不折就被汇率主导。
    # 例：2025-05 亚利桑那腿 NT$ 口径 −318 亿，两条腿同月同比例变动、美元金额没动，
    # 纯粹是申报汇率重估。
    # ⚠️ 别拿全公司核准数的 −479 亿／−437 亿当例子：2026-04 那一笔里有真实的
    #    非亚利桑那担保解除，不是汇率。
    az = d['gua'][['arizona_approved_k', 'arizona_outstanding_k']]
    fx = ds.fx_raw.reindex(az.index)
    d['az'] = pd.DataFrame({'approved': az['arizona_approved_k'] / 1e3 / fx / 1000.0,
                            'outstanding': az['arizona_outstanding_k'] / 1e3 / fx / 1000.0})

    # 背書保證在外余额。2004-01..2011-06 之间共 55 个空月，分 4 段（2004-01..2006-12、
    # 2007-03..2008-07、2008-09、2011-06），其间另有 35 个月是有申报值的；那几代 6-K
    # 没有「在外余额」这一栏。
    # ⚠️ 窗口起点**写死**，不靠「最后一个空月之后」现算。现算的话任何一个新空月都会把
    #    窗口静默往后推 —— 包括「核准已键入、在外数还没到」这种正常的月中中间态，
    #    那会让 Ex16 某天早上突然只剩几十个点，而且一个字的提示都没有；
    #    空月落在**最后一行**时 `nul[-1] + 1` 更会直接越界，整页 build 挂掉。
    s = (d['gua']['outstanding_total_k'].astype(float) / 1e6).loc[_GUAR_FROM:]
    s = s.loc[:s.last_valid_index()]      # 尾部「还没申报」的月份不画
    if s.isna().any():
        raise ValueError(
            f'背書保證在外余额在 {_GUAR_FROM} 之后出现空月：'
            f'{[str(p) for p in s.index[s.isna()]]} —— gs_line 会把缺口静默接成一条直线，'
            f'请先补数或把 _GUAR_FROM 往后挪，不要让它自己猜')
    d['guar_out'] = s
    return d


def _ladder(btr):
    """到期墙：按**实际还本时程**排，不是按到期日。

    109-4/5/6/7 那 12 檔是 50/50 分次还本 —— 到期日前一年先还一半。
    只按 maturity_date 排会把那一半记到错误的年份上。
    返回 (as-of 月, 年份, 实际时程, 只看到期日的错误版本)，最后一个只用来量化差多少。

    ⚠️ **as-of 取的是在外余额那一列自己的月份，不是月营收的月份。**
    「哪些提前腿还没还」这个判断必须与它切分的那份余额快照同月：拿营收月去判，
    营收往前走而债券表没更新时，同一份 outstanding 会被重新切一次 ——
    2026-10 那次 build 会把 NT$119 亿从 2026 柱静默挪到 2027 柱，
    债券数据一个字节没动，图却变了。列名里的日期也从这里读，不写死。

    ⚠️ 登记簿里**有两种日期精度**：109- 起的新券来自逐檔發行辦法，精确到日；
    2002 年那檔与 100-/101-/102- 三个系列共 26 檔旧券来自 20-F，官方只印到月
    （"September 2011 to September 2016"），所以那些行的日期就是 'YYYY-MM'，没有补日。
    本函数按**日**算提前腿（`mat - 1 年` 要跟 as-of 月末比大小），月精度的行
    会被 pandas 当成当月 1 号，误差最多半个月、足以把一条腿挪错年份 —— 现在
    所有月精度的行都已到期（在外为 0）因而被上面那个过滤器排除，但这是**当前
    事实、不是不变量**，所以下面显式断言，将来真有月精度的活券要先想清楚再放行。
    """
    col = next(c for c in btr.columns if c.startswith('outstanding_k_'))
    asof = pd.Period(col[len('outstanding_k_'):].replace('_', '-'), freq='M')
    live = btr[(btr[col] > 0) & (btr['currency'] == 'TWD')].copy()
    coarse = live.loc[live['maturity_date'].astype(str).str.len() < 10, 'tranche_id']
    if len(coarse):
        raise ValueError(
            f'到期墙拿到只精确到月的在外券：{list(coarse)} —— 提前还本腿按日切分，'
            f'月精度会被当成当月 1 号，可能把半年的量记到错误的年份上。'
            f'请先把这些檔的發行辦法日期补全，或为它们单独定义切分规则')
    live['mat'] = pd.to_datetime(live['maturity_date'])
    end = pd.Timestamp(asof.to_timestamp(how='end').date())
    act, naive = {}, {}
    for _, r in live.iterrows():
        out, my = float(r[col]), r['mat'].year
        naive[my] = naive.get(my, 0.0) + out
        if r['repayment_type'] == 'amort_50_50':
            first = r['mat'] - pd.DateOffset(years=1)
            if first > end:
                act[first.year] = act.get(first.year, 0.0) + out / 2
                act[my] = act.get(my, 0.0) + out / 2
                continue
        act[my] = act.get(my, 0.0) + out
    # 不按年份写死上界：`y <= 2036` 会把 2051／2060 那两檔美元宝岛债之外的任何
    # 长券也一起吞掉。改成只排除非新台币券（上面已按 currency 过滤），
    # 再把超过 15 年的尾巴折进最后一根柱之外由图注交代。
    yrs = sorted(set(naive) | set(act))
    keep = [y for y in yrs if y <= asof.year + 10]
    return (asof, keep,
            [act.get(y, 0.0) / 1e6 for y in keep],
            [naive.get(y, 0.0) / 1e6 for y in keep],
            {y: act.get(y, 0.0) / 1e6 for y in yrs if y > asof.year + 10})


def _lags(ds, d):
    """各表的数据截止月，以及相对月营收滞后几个月。"""
    cur = ds.all[-1]
    out = {}
    for k, s in (('衍生性商品', d['notional']), ('背書保證', d['guar_out']),
                 ('公司債', d['bmo'].index.to_series()),
                 ('董事會核准資本支出', d['cap'])):
        last = s.index[-1]
        out[k] = (last, (cur.year - last.year) * 12 + (cur.month - last.month))
    return out


def _lag_note(ds, d):
    """滞后就说滞后。这五张表没接进 monthly_run，月营收先走时必须在页面上看得见。"""
    lag = {k: v for k, v in _lags(ds, d).items() if v[1] > 0}
    if not lag:
        return ''
    return ('⚠️ <b>本板块的数据未与月营收同步</b>：'
            + '；'.join(f'{k}截至 {mlab(m)}（滞后 {n} 个月）' for k, (m, n) in lag.items())
            + '。这五张表尚未接入月度自动刷新，读数请按各自的截止月理解。')


# ══════════════════════════════════════════════════════════════════════════════
# Exhibit 1 的附加行
# ══════════════════════════════════════════════════════════════════════════════
def summary_rows(ds, spec):
    """返回底座 build_summary 内部的 8 元组：(kind, label, series, dec, pct, mode, inv, cum)。

    ⚠️ 每条序列都 `reindex(ds.all)`。底座取值的两列用的是**两个不同的判据** ——
    前三列走 `s.get(cur)`（按月份查），3Y %ile 走 `pctile.cell(vals, i=-1)`
    （按数组**最后一行**取）。序列比主序列短一个月时，水平列会印 '—' 而分位列
    照常印一个数，那个数是上个月的，表面上完全看不出来。对齐到主序列的索引之后
    两者恒指向同一个月。
    """
    d = _load(ds)
    ix = ds.all

    def A(s):
        return s.reindex(ix)

    return [
        ('group', 'FX hedging book（衍生性商品：遠期外匯未平倉）',
         None, None, None, None, None, False),
        ('row', 'Outstanding FX forwards (NT$bn notional)', A(d['notional']),
         0, False, 'ratio', False, False),
        ('row', 'Hedge book / avg. monthly revenue (months)', A(d['cover']),
         2, False, 'ratio', False, False),
        ('group', 'Guarantees to subsidiaries（背書保證，在外余额）',
         None, None, None, None, None, False),
        ('row', 'Total outstanding (NT$bn)', A(d['guar_out']),
         0, False, 'ratio', False, False),
        ('row', 'of which TSMC Arizona (US$bn)', A(d['az']['outstanding']),
         1, False, 'ratio', False, False),
        ('group', 'NT$ bond funding（公司債）', None, None, None, None, None, False),
        ('row', 'Bonds outstanding (NT$bn)',
         A(d['bmo']['outstanding_twd_k'].astype(float) / 1e6), 0, False, 'ratio', False, False),
        # 票面利率是**比率**行 ⇒ m/m、y/y 走百分点差；升高不是好事 ⇒ inv=True
        ('row', 'Weighted-avg. coupon on bonds (%)',
         A(d['bmo']['wavg_coupon_pct'].astype(float)), 2, True, 'pp', True, False),
    ]


def summary_note(ds, spec):
    d = _load(ds)
    cur = ds.all[-1]
    ap = float(d['gua']['approved_total_k'].iloc[-1]) / 1e6
    ou = float(d['guar_out'].iloc[-1])
    # 行数与表数都现算／点名，不写死 —— 上一版写着「五行来自另外五张申报表」，
    # 实际是六行、来自三张表，而且顺手引了一个对本表没有任何贡献的申报期限。
    nrow = sum(1 for r in summary_rows(ds, spec) if r[0] == 'row')
    return (f'下半张表的 {nrow} 行来自台积电<b>另外三张月度申报表</b>'
            '（衍生性商品、背書保證、公司債月報表），与月营收没有派生关系 —— '
            '唯一的例外是 Hedge book / avg. monthly revenue 一行，'
            '它的分母取的正是本页月营收的 12 个月均值。'
            '两处口径必须记住：'
            '（1）背書保證这里取的是<b>在外余额</b>，不是 MOPS 的「至本月份累計餘額」——'
            f'后者是<b>董事會核准數</b>，{mlab(d["gua"].index[-1])} 为 NT${ap:,.0f}bn，'
            f'比在外的 NT${ou:,.0f}bn 高约 {ap / ou - 1:.0%}，两者不可互换也不可拼接；'
            '（2）遠期外匯是<b>月底未平倉存量</b>，既不是当月成交量，也不是年初至今累计。'
            + _lag_note(ds, d))


# ══════════════════════════════════════════════════════════════════════════════
# Exhibit 10..17
# ══════════════════════════════════════════════════════════════════════════════
def exhibits(ds, spec, n0, R):
    d = _load(ds)
    cur = ds.all[-1]
    lagn = _lag_note(ds, d)
    n = [n0 - 1]

    def nxt():
        n[0] += 1
        return n[0]

    def base(**kw):
        # off_window：本板块的图不进「短窗口图总账」那条页尾说明。那条讲的是
        # 「同一个页面窗口起点下各图首点差在哪个 lag 上」，而这些图各读各的申报表、
        # 各有各的起点，其中到期墙的 x 轴根本不是时间轴。
        kw['off_window'] = True
        kw['full'] = True
        return kw

    ex = []

    # ── ① 董事會核准資本支出：逐次董事会 ────────────────────────────────
    cap = d['cap']
    yr = cap.groupby(cap.index.year).sum()
    ex.append(base(
        n=nxt(), kind='bars_labeled', height=300, section=_SEC,
        title='Board-approved capital appropriations, per meeting'
              '（董事會核准資本支出，逐次会议）',
        xlabels=[mlab(p) for p in cap.index], xstep=2, xrot=90,
        ylab='US$bn approved', fmt='usd1', label_fmt='usd1', yfmt='usd0',
        values=L(cap.values), src_extra=_S_CAPEX,
        note=('<b>这不是 capex</b>：核准的是未来资本项目的<b>授权额度</b>，'
              '钱在其后若干年才花出去。'
              '⚠️ <b>不要拿它跟同年的现金资本支出对比、更不要按年换算</b> —— '
              '一次董事会批的额度横跨多年，落在哪一年由会议日期决定，'
              f'所以年度合计本身是跳的（{yr.idxmin()} 只有 US${yr.min():.1f}bn，'
              f'{yr.idxmax()} 有 US${yr.max():.1f}bn）。把图题写成 "capex" 就是一句错话。'
              f'年度合计（US$bn）：{"、".join(f"{y} {vv:.1f}" for y, vv in yr.items())}'
              f'（{cur.year} 年只到 {mlab(cap.index[-1])}，尚未走完）。'
              # ⚠️ 这里不许写「本页往前看的只有 X 和 Y」「本板块其余各图讲的是月底存量」
              #    这类把外延放到整页／整板块的句子：本板块的图各是各的口径（存量、
              #    比率、利率、授权都有），逐张点名就得有人每次加图回来改，而漏改
              #    不会报错。只说本图与紧挨着它、由同一份 `cap` 画出来的下一张图 ——
              #    那张就在下面十几行处生成，`nxt()` 保证编号相邻，说错不了。
              f'<b>本图与紧随其后的年内累计视图（Exhibit {n0 + 1}）画的是同一批核准额度</b>，'
              '两张都是**往前看的授权**，既不是已经花掉的钱，也不是月底存量 —— '
              '本板块另有几张画的是月底余额、比率或利率，读之前先看各自的图题与图注。'
              '而且董事会 6-K 当日就发，比复述同一件事的月末 6-K 早 40–45 天，'
              '所以它的最新点可以比月营收更靠前'
              + (f'（{mlab(cap.index[-1])} vs {mlab(cur)}）。' if cap.index[-1] > cur
                 else '（本次并未领先）。')
              + '窗口自 2016 起：更早的四次董事会是新台币口径、另有三个月一月两会，'
                '混进来会静默算错年度合计。' + lagn)))

    # ── ② 同一份数据的年内累计视图 ──────────────────────────────────────
    years = sorted({p.year for p in cap.index})[-6:]
    lastp = cap.index[-1]
    yser = []
    for y in years:
        vals, run, got = [None] * 12, 0.0, False
        for m in range(1, 13):
            # 当年只画到最新一次董事会为止，其后留 null。补到 12 月的话，
            # 一个只开了三次会的年份会和已经走完的年份一样在 12 月收尾并带末点标签，
            # 读者拿一个残年跟整年比高低。全站的 year_lines 当年行都是这么留空的
            # （payload_guard 也把「尾部一串 null」写成常态）。
            if y == lastp.year and m > lastp.month:
                break
            hit = [float(vv) for p, vv in cap.items() if p.year == y and p.month == m]
            if hit:
                run += sum(hit)
                got = True
            vals[m - 1] = round(run, 4) if got else None
        yser.append({'name': str(y), 'values': vals})
    ex.append(base(
        n=nxt(), kind='year_lines', height=300,
        title='Capital appropriations approved year-to-date（年内累计，按年分线）',
        xlabels=['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
        ylab='US$bn cumulative', fmt='usd1', label_fmt='usd0',
        series=yser, highlight=len(yser) - 1, src_extra=_S_CAPEX,
        note=(f'与 Exhibit {n0} 同源，换成年内累计 —— 逐次柱图看不出年度总量，'
              '因为董事会月份逐年漂移（2021 开五次、2024 用 6 月不用 5 月）。'
              '线在没有开会的月份保持水平，不是缺数据；开年到首次董事会之前留空。'
              '⚠️ 正因为会议月份逐年漂移，<b>台阶的横向位置不能读成「进度快慢」</b>。')))

    # ── ③ 避险帐簿：名目 vs 汇率 ────────────────────────────────────────
    nt = d['notional'].iloc[-48:]
    fx48 = ds.fx_raw.reindex(nt.index)
    ex.append(base(
        n=nxt(), kind='bar_line_dual', height=320,
        title='FX forward book vs. the NT dollar（遠期外匯未平倉名目 vs 汇率）',
        xlabels=[mlab(p) for p in nt.index], xstep=3, xrot=90,
        ylab='NT$bn notional outstanding', ylab2='NTD per USD',
        fmt='f0c', yfmt='f0c',
        bar={'name': '月底未平倉遠期外匯名目（NT$bn）', 'color': 'BLUE',
             'values': L(nt.values)},
        # zero_base=False：右轴是**水平量**（汇率在 29–33 之间走），不是跨零的 y/y。
        # 缺省会把 0 纳入右轴量程，把整条线压成轴顶端的一条直线，结构全部消失。
        line={'name': 'NTD/USD 月均（RHS）', 'color': 'NAVY',
              'values': L(fx48.values), 'yfmt': 'f1', 'zero_base': False},
        src_extra=_S_DERIV,
        note=('台积电以美元卖货、以新台币入账，把未来会收到的美元提前卖成新台币；'
              '柱高就是这个「已提前卖掉」的规模。'
              '⚠️ <b>这是月底未平倉存量，不是当月成交量，也不是年初至今累计</b> —— '
              '同一张 MOPS 表里紧挨着的「已沖銷契約」才是 YTD、每年一月归零，'
              '而两栏都叫「契約總金額」，解析器错一行整条序列作废。'
              f'峰值 NT${d["notional"].max():,.0f}bn（{mlab(d["notional"].idxmax())}），'
              f'当前 NT${nt.iloc[-1]:,.0f}bn。'
              f'<b>绝对水平要配 Exhibit {n0 + 3} 一起读</b>：名目跟着营收长，'
              '光看水平量不出避险做得多不多。')))

    # ── ④ 归一化：避险强度 ──────────────────────────────────────────────
    cov = d['cover']
    _n = d['notional'].reindex(cov.index)
    ex.append(base(
        n=nxt(), kind='gs_line', height=300,
        title='Hedge book scaled to revenue（避险强度：名目 ÷ 月均营收）',
        xlabels=[mlab(p) for p in cov.index], xstep=6, xrot=90,
        ylab='覆盖月数（名目 ÷ 月均营收）', fmt='f2', yfmt='f1',
        values=L(cov.values), src_extra=_S_DERIV,
        note=('分母用 <b>TTM ÷ 12</b> 而不是当月营收：当月营收带农历年与季末拉货的锯齿，'
              '拿一个月底存量去除一个锯齿状流量，等于把分母的噪声灌进比值。'
              f'当前 {cov.iloc[-1]:.2f} 个月（占 TTM 营收 {cov.iloc[-1] / 12 * 100:.1f}%），'
              f'2016 年以来均值 {cov.mean():.2f}，'
              f'峰值 {cov.max():.2f}（{mlab(cov.idxmax())}）、'
              f'谷底 {cov.min():.2f}（{mlab(cov.idxmin())}）。'
              f'<b>归一化几乎没有减小波动</b>（变异系数 {_n.std() / _n.mean():.2f} → '
              f'{cov.std() / cov.mean():.2f}）—— 这些起伏本来就不是营收增长造成的，'
              '是避险决策自己在动。'
              '⚠️ <b>这是标尺，不是覆盖率</b>：远期避的是已存在的美元货币性资产'
              '（应收、美元现金），不是未来销售，不能读成「未来 N 个月的销售已锁定」。')))

    # ── ⑤ 新台币债：价 ──────────────────────────────────────────────────
    bmo = d['bmo']
    tw = d['btr'][d['btr']['currency'] == 'TWD'].copy()
    # 登记簿里日期有两种精度：109- 起的新券到日，100-/101-/102- 旧券来自 20-F、
    # 官方只印到月。这里一律 `str[:7]` 按月比 —— 对两种精度都对，
    # 而 pd.to_datetime 遇到混合格式会给月精度的行补一个当月 1 号，
    # 补出来的那个「日」在按月分桶的场景里不多一分信息，只会让人以为它是真的。
    tw['ip'] = pd.PeriodIndex(tw['issue_date'].astype(str).str[:7], freq='M')
    tw['mp'] = pd.PeriodIndex(tw['maturity_date'].astype(str).str[:7], freq='M')
    t5 = tw[tw['tenor_years'] == 5.0]
    new5 = t5.groupby('ip')['coupon_pct'].last().reindex(bmo.index).ffill()
    stock = bmo['wavg_coupon_pct'].astype(float)
    # `lines_endlabels` 属于 mrwin.DENSE，吃不了前导 null（首点为 null 直接 TypeError）。
    # 深色线是 ffill 出来的阶梯，只要窗口起点早于第一檔 5 年券就会留下一段 NaN。
    # 现在起点恰好就是第一檔 5 年券的发行月，所以不留 —— 但那是**当前事实**，
    # 谁把 BONDS_FROM 再往前挪一格就不成立了，所以在这里显式挡住。
    if new5.isna().any():
        raise ValueError(
            f'新发 5 年券阶梯在窗口左端有 {int(new5.isna().sum())} 个 null'
            f'（{mlab(bmo.index[0])} 早于第一檔 5 年券 {mlab(t5["ip"].min())}）—— '
            f'lines_endlabels 是 DENSE 图型，前导 null 会被平滑成一条塌到零的假线。'
            f'要么把 fetch/tsm.py 的 BONDS_FROM 挪回不早于第一檔 5 年券，'
            f'要么给这张图换一个吃得了 null 的图型（见 mrwin.DENSE）')

    # 首月的在外余额里有一块是**窗口之前发的**：序列讲的是在外存量，不是「窗口内
    # 发了多少」，所以首行 outstanding ≠ issued。这个差额必须在图注里交代 ——
    # 不交代的话读者拿首行的 issued 去对 outstanding，只会得出「数据错了」。
    # 期初存量从**月度表自己**倒推（outstanding − issued + repaid），
    # 再拿登记簿独立算一遍对上；两份文件互为对方的校验，谁被单独改动都会在这里炸。
    p0 = bmo.index[0]
    r0 = bmo.iloc[0]
    pre_k = (float(r0['outstanding_twd_k']) - float(r0['issued_twd_k'])
             + float(r0['repaid_twd_k']))
    pre = tw[(tw['ip'] < p0) & (tw['mp'] > p0)]
    n_pre = int(r0['n_tranches_outstanding']) - int((tw['ip'] == p0).sum())
    # 简单求和只在期初那批券都是一次还本时成立。以前这句话只是括号里的一句提醒，
    # 提醒挡不住任何东西 —— 期初真混进一檔 amort_50_50，上面的 `pre_k` 会静默偏大，
    # 而两边**同时**偏大（月度表倒推的也不知道有半腿已还），互校照样通过。
    if len(pre) and (pre['repayment_type'] != 'bullet').any():
        raise ValueError(
            f'{mlab(p0)} 的期初存量里有非 bullet 券：'
            f'{list(pre.loc[pre["repayment_type"] != "bullet", "tranche_id"])} —— '
            f'本处按发行额直接求和，分次还本的券在起点前可能已还掉一半，'
            f'这个和会偏大而互校两边一起偏大、发现不了。'
            f'请改用 fetch/tsm.py 的 `_bond_state` 口径重算期初存量')
    if abs(float(pre['issue_amount_k'].sum()) - pre_k) > 1.0 or len(pre) != n_pre:
        raise ValueError(
            f'{mlab(p0)} 期初存量对不上：月度表倒推 {pre_k:,.0f}k / {n_pre} 檔，'
            f'登记簿算出 {pre["issue_amount_k"].sum():,.0f}k / {len(pre)} 檔。'
            f'两份 CSV 已经不同步 —— 跑 `python3 fetch/tsm.py bonds --write` 重建，'
            f'不要在这里改判据把它凑过去')
    # 图注里点名的券号都从数据里取，不手打 —— 手打的那一刻它就跟数据脱钩了，
    # 下次谁补一檔进来它照样理直气壮地印着旧答案。
    # 期初只剩一檔时直接点券号；多檔时才归并成「1xx- 系列」。
    # ⚠️ 别无脑 `qibie.split('-')[0]`：2011 年之前那檔的期别是 "Domestic 5th"，
    #    没有连字号，切完再补一个 '-' 就印成「Domestic 5th- 系列」。
    if not len(pre):
        pre_txt = ''
    elif len(pre) == 1:
        pre_txt = f'1 檔 {pre["tranche_id"].iloc[0]}（{mlab(pre["ip"].iloc[0])} 发、' \
                  f'票面 {pre["coupon_pct"].iloc[0]:.2f}%）'
    else:
        _ser = sorted({str(q).rsplit('-', 1)[0] for q in pre['qibie']})
        pre_txt = (f'{n_pre} 檔 {"/".join(_ser)} 系列的旧券'
                   f'（{pre["coupon_pct"].min():.2f}%–{pre["coupon_pct"].max():.2f}%，'
                   f'{mlab(pre["ip"].min())}–{mlab(pre["ip"].max())} 发）')
    # 「期初存量」与「首行 outstanding ≠ issued」这两句在起点前移到第一檔发行月时
    # 会变成假话（那时期初为 0、两者相等），所以整句按 pre 是否为空现算，不写死。
    # ⚠️ 别用 `stock.iloc[<某个下标>]` 取「期初券到期那个月」—— 下标是当前窗口的
    #    巧合，窗口一变它就静默指向另一个月份，而且指错了也照样印得出一个数。
    if len(pre):
        _pm = pre['mp'].max()
        pre_sent = (f'起点之所以高，是因为窗口开始时账上还压着期初存量 '
                    f'NT${pre_k / 1e6:,.1f}bn —— {pre_txt}；'
                    f'这批券的最后一檔于 {mlab(_pm)} 到期，当月平均票面 '
                    f'{float(stock.loc[_pm]):.2f}%。')
        pre_warn = (f'⚠️ <b>首行 outstanding ≠ 首行 issued</b>：{mlab(p0)} 发了 '
                    f'NT${float(r0["issued_twd_k"]) / 1e6:,.1f}bn，在外却是 '
                    f'NT${float(r0["outstanding_twd_k"]) / 1e6:,.1f}bn，'
                    f'差的就是上面那笔期初存量。'
                    f'这条序列画的是<b>在外余额</b>，不是窗口内的发行累计。')
    else:
        pre_sent = (f'{mlab(p0)} 就是第一檔的发行月，<b>期初存量为 0</b>，'
                    f'首行 outstanding 等于首行 issued。')
        pre_warn = ('这条序列画的是<b>在外余额</b>，不是窗口内的发行累计 —— '
                    '两者眼下恰好相等，只因为窗口起点上账面还没有旧券。')

    # ── 发行断层：窗口里最长的一段「一檔没发」──────────────────────────────
    # 这一段是扩窗之后才看得见的，也是深色阶梯线为什么会平躺好几年的唯一原因。
    _im = sorted(tw.loc[tw['ip'] >= p0, 'ip'].unique())
    _g0, _g1 = max(zip(_im, _im[1:]), key=lambda ab: ab[1].ordinal - ab[0].ordinal)
    dry = _g1.ordinal - _g0.ordinal - 1                       # 中间几个月一檔没发
    _pk = _g1 - 1                                             # 断层末月
    # 深色阶梯的最长平台**不等于**发行断层：断层里最后那几次发行（102-2/3/4）压根
    # 没有 5 年期的一檔，所以阶梯早在断层开始前 7 个月就已经不动了。
    # 两个数各算各的，别拿一个去说另一个。
    _run = new5.groupby((new5 != new5.shift()).cumsum())
    _flat = max(_run, key=lambda kv: len(kv[1]))[1]
    # 平均成本那条线的形状：**五个转折点全部现算**。
    # 只报「首点 → 全局最低 → 末点」会印出「一路降到谷底」这种话，而中间那段
    # 明明是在往上走 —— 图注自己打自己脸。断层两端就是那两个转折，顺手拿来用。
    _pts, _seen = [], set()
    for _p in (p0, stock.loc[:_g0].idxmin(), _pk, stock.idxmin(), bmo.index[-1]):
        if _p not in _seen:
            _seen.add(_p)
            _pts.append(_p)
    path_txt = ' → '.join(f'{float(stock.loc[_p]):.2f}%（{mlab(_p)}）' for _p in _pts)
    # 断层两端的在外券，从登记簿独立切一遍；再拿它跟月度表的 wavg_coupon 对。
    # 这是期初存量互校之外的**第二处双算**，而且落在新扩出来的那段窗口里 ——
    # 不然扩出来的 102 个月就只有递推自洽这一条 guard 罩着。
    _live = tw[(tw['ip'] <= _g0) & (tw['mp'] > _g0)]
    gone, stay = _live[_live['mp'] <= _pk], _live[_live['mp'] > _pk]
    if (_live['repayment_type'] != 'bullet').any():
        raise ValueError(
            f'{mlab(_g0)} 在外券里有分次还本的：'
            f'{list(_live.loc[_live["repayment_type"] != "bullet", "tranche_id"])} —— '
            f'下面按发行额加权算票面，半腿已还的券权重会偏大')

    def _wa(x):
        return float((x['issue_amount_k'] * x['coupon_pct']).sum() / x['issue_amount_k'].sum())

    for _p, _sub in ((_g0, _live), (_pk, stay)):
        if abs(_wa(_sub) - float(stock.loc[_p])) > 5e-4:
            raise ValueError(
                f'{mlab(_p)} 加权票面双算对不上：登记簿切出 {len(_sub)} 檔算得 '
                f'{_wa(_sub):.4f}%，月度表印的是 {float(stock.loc[_p]):.4f}%。'
                f'两份 CSV 已经不同步 —— 跑 `python3 fetch/tsm.py bonds --write` 重建，'
                f'不要在这里放宽容差把它凑过去')
    # 被剔除的宝岛债也现算：檔数、名目、票面、年期全从登记簿取。
    # 「两檔各 US$10 亿、2.70%/3.10%、30–40 年期」以前是手打的，
    # 再发一檔宝岛债它就变成一句错话，而且是**图注自己说自己剔干净了**那种错话。
    usd = d['btr'][d['btr']['currency'] == 'USD']
    usd_txt = ('%d 檔%s宝岛债（%s，%.0f–%.0f 年期）'
               % (len(usd),
                  ('各 US$%.0f 亿的' % (usd['issue_amount_k'].iloc[0] / 1e5))
                  if usd['issue_amount_k'].nunique() == 1 else
                  ('合计 US$%.0f 亿的' % (usd['issue_amount_k'].sum() / 1e5)),
                  ' / '.join('%.2f%%' % c for c in sorted(usd['coupon_pct'])),
                  usd['tenor_years'].min(), usd['tenor_years'].max()))
    win = tw[tw['ip'] >= p0]
    cheap = win.loc[win['coupon_pct'].idxmin()]
    # 「把平均从谷底拖回来的」必须是**谷底之后**发的券。取全窗口最贵的一檔会拿到
    # 102-4F（2.10%，Sep-13）—— 一檔在谷底之前七年就已到期的旧券，
    # 印在「近年新券」四个字后面就是一句直接说反了的话。
    aft = win[win['ip'] > stock.idxmin()]
    dear = aft.loc[aft['coupon_pct'].idxmax()]
    n_dec = sum(1 for p in bmo.index if p.month == 12)         # 窗口内跨过的年末数
    ex.append(base(
        n=nxt(), kind='lines_endlabels', height=320,
        title='Cost of NT$ debt: new issues vs. the stock（新台币债务资金成本）',
        # x 标签密度不写死：窗口长度是会变的，`xstep=3` 在 77 个月时是 26 个标签、
        # 在 179 个月时就是 60 个 —— 一堵字墙。沿用 mrwin 给长月份轴定的同一条
        # 上限（约 MAX_XLABS 个标签），只调用不改它。
        xlabels=[mlab(p) for p in bmo.index], xrot=90,
        xstep=max(3, -(-len(bmo) // mrwin.MAX_XLABS)),
        ylab='Coupon, %', fmt='pct2', label_fmt='pct2',
        series=[{'name': '最近一档新发 5 年券票面（边际成本）', 'color': 'NAVY',
                 'values': L(new5.values)},
                {'name': '在外公司债加权平均票面（平均成本）', 'color': 'MBLUE',
                 'values': L(stock.values)}],
        src_extra=_S_BOND,
        note=('深色是<b>边际成本</b>（今天再借要多少钱），浅色是<b>平均成本</b>'
              '（历史存量的实际负担）；两线之间的缺口是还没重定价完的部分。'
              f'<b>浅色那条既不是单调上行也不是一个 V，是四段来回</b>：'
              f'{path_txt}。'
              + pre_sent +
              # ── 扩窗之后才看得见的那一段，也是本图最容易被读反的一段 ──
              f'<b>中间那段上坡不是利率在涨，是幸存者在换</b>：'
              f'{mlab(_g0)} 发完最后一檔之后整整 {dry} 个月一檔没发，'
              f'直到 {mlab(_g1)} 才重新开闸。这段断层里平均票面从 '
              f'{float(stock.loc[_g0]):.2f}% 爬到 {float(stock.loc[_pk]):.2f}%，'
              f'而这期间<b>没有任何一檔债被重定价</b> —— 只是先到期的 {len(gone)} 檔'
              f'（NT${float(gone["issue_amount_k"].sum()) / 1e6:,.1f}bn、'
              f'加权 {_wa(gone):.2f}%）比留下来的 {len(stay)} 檔'
              f'（NT${float(stay["issue_amount_k"].sum()) / 1e6:,.1f}bn、'
              f'加权 {_wa(stay):.2f}%）便宜，短券先走、长券留下，把平均抬了上去。'
              f'其后 {mlab(_g1)} 起那批超低息新券（最低 {cheap["coupon_pct"]:.2f}%，'
              f'{cheap["tranche_id"]}，{mlab(cheap["ip"])}）把平均砸到谷底，'
              f'再由谷底之后新发的那批（最贵 {dear["coupon_pct"]:.2f}%，'
              f'{dear["tranche_id"]}，{mlab(dear["ip"])}）拖回来。'
              # ── 深色线 ──
              f'深色线是<b>阶梯</b>：保持上一档 5 年券的票面直到下一档发行，'
              f'不是月度报价。它自 {new5.iloc[0]:.2f}%（{mlab(p0)}）跌到 '
              f'{new5.min():.2f}%（{mlab(new5.idxmin())}）、再升到 '
              f'{new5.iloc[-1]:.2f}%（{mlab(bmo.index[-1])}）。'
              f'⚠️ 它最长的一段平台有 <b>{len(_flat)} 个月</b>'
              f'（{mlab(_flat.index[0])}–{mlab(_flat.index[-1])}），'
              f'全程是 {float(_flat.iloc[0]):.2f}% 这一个 {mlab(_flat.index[0])} 的旧报价被拖着走，'
              f'<b>不是「那些年都能按这个价借到钱」</b> —— 其中 {mlab(_g0)} 之后、'
              f'{mlab(_g1)} 之前的 {dry} 个月台积电一檔新台币债都没发；'
              f'平台比断层还长 {len(_flat) - dry} 个月，'
              f'是因为断层前最后几次发行里根本没有 5 年期的一檔。'
              + pre_warn +
              f'⚠️ {len(bmo)} 个月里<b>只有最近 3 个月来自月报表本身</b>'
              '（MOPS 只留滚动 3 个月窗口），其余由券别登记簿与还本时程重建，仍是推导值。'
              f'窗口起点定在 {mlab(p0)} 而不是更早，是因为它是<b>能被官方年末余额'
              f'钉住的最早一个月</b>（本图跨过 {n_dec} 个年末，逐年对账见下）；'
              '再往前登记簿自己知道自己不全（唯一那檔 2002 年的旧券叫「丙類」，'
              '同期的甲類/乙類根本不在表里），而本仓最早的 20-F 是 FY2012，'
              '核都没得核 —— 详见 <code>fetch/tsm.py</code> 的 <code>BONDS_FROM</code>。'
              '对账口径分两段，别混着说：2011–2019 九个年末对 20-F 的 '
              '<b>Domestic unsecured bonds</b> 零误差；2020 起那一行含宝岛债，'
              '只能核到「残差 = 宝岛债名目 × 年末即期」。逐年结果跑 '
              '<code>python3 fetch/tsm.py bonds</code>。'
              f'两条线都只含新台币，<b>已剔除 {usd_txt}</b>'
              ' —— 它们在 20-F 里混在 domestic 那一行，并进来会把两个指标都打歪。')))

    # ── ⑥ 新台币债：时程 ────────────────────────────────────────────────
    b_asof, yrs, act, naive, tail = _ladder(d['btr'])
    # 差额逐年枚举，不假定「一定是 cur.year 与 cur.year+3 这两年」——
    # 那两个下标是 2026 年的巧合，年份一过 `yrs.index()` 直接抛 ValueError 把整页 build 打死，
    # 而在此之前它会先印出「把 NT$0.0bn 从 X 挪到 Y」这种自我否定的句子。
    shift = [(y, a - nv) for y, a, nv in zip(yrs, act, naive) if a - nv > 0.05]
    ex.append(base(
        n=nxt(), kind='bars_labeled', height=300,
        title='NT$ bond refinancing wall（到期墙，按实际还本时程）',
        xlabels=[str(y) for y in yrs], xstep=1, xrot=0,
        ylab='NT$bn due', fmt='f0c', label_fmt='f0c', yfmt='f0c',
        values=L(act), src_extra=_S_BOND,
        note=(f'截至 <b>{mlab(b_asof)}</b> 在外 '
              f'NT${float(bmo["outstanding_twd_k"].iloc[-1]) / 1e6:,.0f}bn 本金的偿还时程，'
              '按日历年排。'
              '⚠️ <b>按实际还本时程建，不是按到期日</b>：109-4/5/6/7 那 12 檔是 50/50 '
              '分次还本、到期日前一年先还一半，'
              + ('只看到期日会' + '、'.join(f'把 NT${vv:,.1f}bn 从 {y} 挪到 {y + 1}'
                                           for y, vv in shift) + '。'
                 if shift else '本期在外券里已经没有尚未偿付的提前半段。')
              + f'<b>本图不是月度序列</b>，是 {mlab(b_asof)} 那份存量快照的前瞻切片 —— '
                f'切分口径锚在快照月本身，不随月营收往前走而变；'
                f'{yrs[0]} 那根只含该年剩余月份。'
              + (f'另有 NT${sum(tail.values()):,.1f}bn 到期在 {min(tail)} 年之后'
                 f'（{"、".join(str(y) for y in sorted(tail))}），未画进本图。'
                 if tail else '')
              + '已剔除美元计价的宝岛债，本图只含新台币券。')))

    # ── ⑦ 背書保證全史 ──────────────────────────────────────────────────
    go = d['guar_out']
    ap = float(d['gua']['approved_total_k'].iloc[-1]) / 1e6
    # 「连续 N 个月在外余额为零」那一句**现算**，不写死：原文写的是「连续 77 个月
    # （2006-09 至 2013-01）」，实测在今天的 series/tsm_guarantees.csv 上确实是这一段，
    # 但它是一句关于数据的断言 —— 档案一回补或一重述就过期，而没有任何东西会报错。
    # 这一段在本图窗口（自 go.index[0] 起）**之外**，所以要读整列而不是读 go。
    # ⚠️ 原文写的是「连续 77 个月（2006-09 至 2013-01）」—— 那两个数是**核准數**
    #    （approved_total_k）那一列的零段，而本图画的是**在外余额**
    #    （outstanding_total_k）。同一张 CSV 的两列，句子挂错了列：在外余额上最长的
    #    连续零段是另一段（现算，见下）。两列的零段本来就该不一样 ——
    #    核准了额度不等于用掉，这正是本图注下面那句「别拿核准數代替本图」说的事。
    _oz = d['gua']['outstanding_total_k']
    _zrun = _zmax = 0
    _z0 = _z1 = None
    for _i, (_p, _v) in enumerate(_oz.items()):
        _zrun = _zrun + 1 if _v == 0 else 0
        if _zrun > _zmax:
            _zmax, _z0, _z1 = _zrun, _oz.index[_i - _zrun + 1], _p
    ex.append(base(
        n=nxt(), kind='gs_line', height=300,
        title='Guarantees outstanding to subsidiaries（背書保證在外余额）',
        xlabels=[mlab(p) for p in go.index], xstep=12, xrot=90,
        ylab='NT$bn outstanding', fmt='f0c', yfmt='f0c',
        values=L(go.values), src_extra=_S_GUAR,
        note=('海外子公司自己借钱发债、母公司出具背書保證，所以这条线是'
              '<b>海外建厂融资规模的代理变量</b>。'
              + (f'台积电曾<b>连续 {_zmax} 个月（{mlab(_z0)} 至 {mlab(_z1)}）'
                 f'担保余额为零</b> —— '
                 '那不是缺数据，当时的 6-K 上写的就是 "Endorsements and guarantees: None."。'
                 if _zmax >= 12 else
                 '这条序列早年有过整段为零的月份 —— 那不是缺数据，'
                 '当时的 6-K 上写的就是 "Endorsements and guarantees: None."。')
              + 
              '这条序列的存在本身就是海外扩产这件事的证据。'
              f'窗口自 {mlab(go.index[0])} 起：那是在外数第一个不间断的月份，'
              '更早的申报版式没有「在外余额」这一栏，接上去等于把缺口静默补平。'
              '⚠️ 别拿 MOPS 的「至本月份累計餘額」代替本图 —— 那是<b>董事會核准數</b>，'
              f'{mlab(d["gua"].index[-1])} 为 NT${ap:,.0f}bn，'
              f'比在外数高约 {ap / float(go.iloc[-1]) - 1:.0%}。')))

    # ── ⑧ 亚利桑那腿 ────────────────────────────────────────────────────
    # 只画核准腿存在的区间：lines_endlabels 属于 DENSE，序列里带 null 会被平滑
    # 当成 0，画出一条塌到零的假线（首尾为 null 时直接抛 TypeError）。
    az = d['az'].dropna()
    azo = d['az']['outstanding'].dropna()
    ex.append(base(
        n=nxt(), kind='lines_endlabels', height=320,
        title='Parent guarantees for TSMC Arizona（亚利桑那厂：核准 vs 实际动支）',
        xlabels=[mlab(p) for p in az.index], xstep=3, xrot=90,
        ylab='US$bn', fmt='usd1', label_fmt='usd1',
        series=[{'name': '董事会核准额', 'color': 'NAVY', 'values': L(az['approved'].values)},
                {'name': '实际动支（在外）', 'color': 'MBLUE',
                 'values': L(az['outstanding'].values)}],
        src_extra=_S_GUAR,
        note=('两线之间的缺口是<b>已批准但还没动用的融资额度</b>，是产能投放的领先量。'
              f'当前核准 US${az["approved"].iloc[-1]:.1f}bn、'
              f'实际动支 US${az["outstanding"].iloc[-1]:.1f}bn。'
              '⚠️ <b>刻意折成美元</b>：这是美元计价的担保、以新台币申报，不折的话'
              '新台币升值会被读成「台积电撤回担保」——'
              '2025-05 新台币单月大幅升值，亚利桑那腿的 NT$ 口径掉了 318 亿，'
              '而美元口径两条腿都几乎没动。'
              f'⚠️ 窗口自 {mlab(az.index[0])} 起，因为<b>核准腿只从那时才有</b> —— '
              'MOPS 只发核准数、6-K 只发在外数，在那之前的 6-K 不分栏，'
              f'两个来源不可拼接。在外腿本身可回溯到 {mlab(azo.index[0])}，'
              '本图为了让两条线共用一个窗口没有画那一段。')))
    return ex
