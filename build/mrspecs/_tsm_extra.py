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
   逐檔發行辦法登记簿。月报表只留滚动 3 个月窗口，77 个月里只有最近 3 个来自月报表
   本身，其余由券别登记簿与还本时程重建，已用六个 20-F 年末余额对账。

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
from mrbase import L, mlab

_SEC = '非营收月度披露：台积电按月申报的另外五张表'

_S_CAPEX = ('Exhibit source: TSMC 董事会当日 Form 6-K（SEC EDGAR，CIK 0001046179），'
            '与月末 6-K 分项及 MOPS ajax_t05st01 三方对账')
_S_DERIV = ('Exhibit source: MOPS ajax_t15sf 衍生性商品交易情形'
            '（取得或處分資產處理準則 §31 第 4 項）')
_S_BOND = ('Exhibit source: MOPS ajax_t47sb17 公司債月報表 + 逐檔發行辦法登记簿，'
           '已与 FY2020–FY2025 Form 20-F 的年末余额对账')
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
    """
    col = next(c for c in btr.columns if c.startswith('outstanding_k_'))
    asof = pd.Period(col[len('outstanding_k_'):].replace('_', '-'), freq='M')
    live = btr[(btr[col] > 0) & (btr['currency'] == 'TWD')].copy()
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
              f'<b>本页往前看的只有它和到期墙（Exhibit {n0 + 5}）</b> —— '
              'Exhibit 2–9 讲的是已经发生的营收与汇率，本板块其余各图讲的是月底存量。'
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
    t5 = d['btr'][(d['btr']['currency'] == 'TWD') & (d['btr']['tenor_years'] == 5.0)].copy()
    t5['p'] = pd.PeriodIndex(pd.to_datetime(t5['issue_date']).dt.to_period('M').astype(str),
                             freq='M')
    new5 = t5.groupby('p')['coupon_pct'].last().reindex(bmo.index).ffill()
    stock = bmo['wavg_coupon_pct'].astype(float)
    ex.append(base(
        n=nxt(), kind='lines_endlabels', height=320,
        title='Cost of NT$ debt: new issues vs. the stock（新台币债务资金成本）',
        xlabels=[mlab(p) for p in bmo.index], xstep=3, xrot=90,
        ylab='Coupon, %', fmt='pct2', label_fmt='pct2',
        series=[{'name': '最近一档新发 5 年券票面（边际成本）', 'color': 'NAVY',
                 'values': L(new5.values)},
                {'name': '在外公司债加权平均票面（平均成本）', 'color': 'MBLUE',
                 'values': L(stock.values)}],
        src_extra=_S_BOND,
        note=('深色是<b>边际成本</b>（今天再借要多少钱），浅色是<b>平均成本</b>'
              '（历史存量的实际负担）；两线之间的缺口是还没重定价完的部分。'
              f'新发 5 年券自 {new5.min():.2f}%（{mlab(new5.idxmin())}）升到 '
              f'{new5.iloc[-1]:.2f}%，存量加权平均自 {stock.iloc[0]:.2f}% 升到 '
              f'{stock.iloc[-1]:.2f}%。深色线是<b>阶梯</b>：保持上一档 5 年券的票面'
              '直到下一档发行，不是月度报价。'
              f'⚠️ {len(bmo)} 个月里<b>只有最近 3 个月来自月报表本身</b>'
              '（MOPS 只留滚动 3 个月窗口），其余由券别登记簿与还本时程重建，'
              '已用六个 20-F 年末余额零误差对账，但仍是推导值。'
              '两条线都只含新台币，已剔除两檔各 US$10 亿的宝岛债'
              '（2.70% / 3.10%，30–40 年期），并进来会把两个指标都打歪。')))

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
    ex.append(base(
        n=nxt(), kind='gs_line', height=300,
        title='Guarantees outstanding to subsidiaries（背書保證在外余额）',
        xlabels=[mlab(p) for p in go.index], xstep=12, xrot=90,
        ylab='NT$bn outstanding', fmt='f0c', yfmt='f0c',
        values=L(go.values), src_extra=_S_GUAR,
        note=('海外子公司自己借钱发债、母公司出具背書保證，所以这条线是'
              '<b>海外建厂融资规模的代理变量</b>。'
              '台积电曾<b>连续 77 个月（2006-09 至 2013-01）担保余额为零</b> —— '
              '那不是缺数据，当时的 6-K 上写的就是 "Endorsements and guarantees: None."。'
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
