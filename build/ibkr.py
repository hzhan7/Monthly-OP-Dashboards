# -*- coding: utf-8 -*-
"""Interactive Brokers (IBKR) 月度经营指标 —— 网页看板 payload 生成器。

由独立仓 `ibkr-monthly-metrics/build_data.py` 移植而来：**图一张都没改**（Exhibit 2-18
的序列、标题文案、图注、断点、截轴逐字照搬），只做两件事——

  1. payload 顶层换成 monthly-op-dashboards 的统一契约（`window.DASH`，见 build/CONTRACT.md）：
     加 ticker/tracker/title/through_label/subtitle/notes/footer，去掉 month_name/footnote/window。
  2. 汇总表的行从 `{lab,cur,prev,yag,mm,yy,mode,inv,pctile}` 改成 `cells[]` 形式。
     **原来写在 index.html 那段 JS 里的格式化口径一并搬到 Python 侧**：
     比率类差异用 pp/bp（|v|<1 用 bp）、反向指标（inv）决定绿红、分位对反向指标要反转后
     再判高低、单调序列不给分位。页面只排版，不做任何计算。

═══ 数据源 ═══
  · `series/ibkr.csv` —— 历史指标表（2016-01 起逐月，官方原始单位），由 fetch/ibkr.py 落库。
    **所有存量/流量指标都从这里读**，本模块不下载、不自己解析历史 PDF 的数字。
  · `~/.claude/skills/IBKR月度指标/cache/pr_YYYYMM.pdf` —— 月度新闻稿，佣金与平均订单规模
    （历史指标表里没有这两列，CSV 也就没有）。解析函数复用 skill 的 `build_report.py::parse_pr`，
    不重写：那份代码是 skill 出 PDF 与本站共用的，各写一份迟早分叉，而分叉的表现是
    「skill 的 PDF 与网页对同一个月给出不同的 CPT」——最难发现的那种错。
  · `~/.claude/skills/IBKR月度指标/cache/hist_latest.pdf` —— 只取 Notes 段的**文字**
    （账户口径调整的原文），用作护栏与图注；一个数字都不从这里取。

═══ 口径 ═══
  历史指标表首个区块 "(in Thousands, except Trading Days)" —— 账户/DARTs/合约/股数以千计；
  第二区块 "(in Billions)" —— 客户权益/现金/融资余额。
  新闻稿 Key products 两列 = Average Order Size（股/张）与 Average Commission per Cleared
  Commissionable Order（$/笔），**不是每股/每张单价**。

═══ 窗口 ═══
  Exhibit 2-13   最近 13 个月（从 CSV 最新月倒推，不依赖构建当天日期）
  Exhibit 14-18  2016-01 起全历史
  Exhibit 1 的 3Y %ile 取近 36 个月

构建日期只写文件首行注释，不进 payload —— 进了 payload，monthly_run 的
「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效，每天都会产出一个
内容相同、只有日期变了的 no-op commit。
"""
import csv
import datetime
import importlib.util
import json
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
SKILL = os.path.expanduser('~/.claude/skills/IBKR月度指标')
CACHE = os.path.join(SKILL, 'cache')

SRC = ('Source: Company data (IBKR monthly brokerage metrics); '
       'chart format after Goldman Sachs GIR')

# ── 账户口径的一次性调整（历史指标 PDF 的 Notes 段，解析器的数字正则抓不到）──
# 键 = 'YYYY-MM'；field 指明这条脚注调的是哪条序列：
#   'net_new'  —— 表内 Net New Accounts 就是账户差分，真实增长另有其数，画 y/y 必须用 real
#   'accounts' —— 调的是 Total Accounts 的**存量口径**，net_new 那一行已经是真实值
# reported/real 单位与表内一致（千户）。三条都逐字核对过 hist_latest.pdf 的 Notes 原文。
ADJ = {
    # 第 2 页 Notes(1)：real growth 87.7 vs calculated 74.4，差额 13.3 上交政府
    '2025-03': {'field': 'net_new', 'reported': 74.4, 'real': 87.7,
                'reason': '13.3k 账户按法律要求上交政府（escheat），被计进了账户差分'},
    # 第 2 页 Notes(1)：real growth 111.9 vs calculated 73.1，差额 38.8 来自一家 IB 撤出
    '2025-09': {'field': 'net_new', 'reported': 73.1, 'real': 111.9,
                'reason': '一家 introducing broker（Futu 子公司）撤出，带走 38.8k 账户'},
    # 第 3 页 Notes(1)：Total Accounts at Nov 30, 2024 下调 9.1k（为受制裁证券开的非交易账户）。
    # 核对算术：accounts 3,249.1 − 3,185.4 = 63.7，而表内 net_new = 72.8，差 9.1 正是这笔下调，
    # 即**净新增那一行已经是还原后的真实值**，只有账户存量序列在 2024-11 有一个向下的台阶。
    # 所以这条不改 net_new，只作为脚注渲染出来（也用于「有脚注必须有登记」的护栏）。
    '2024-11': {'field': 'accounts', 'level_adj': -9.1,
                'reason': '2024-11-30 的 Total Accounts 下调 9.1k（两年间为受制裁证券开立、不可交易）'},
}

# IBKR 写这类脚注的四种固定措辞。命中即视为「该月有口径调整」，必须在 ADJ 里有登记。
NOTE_RE = re.compile(r'real account growth|adjusted downward|escheat|withdraw', re.I)
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December']
MONTH_RE = re.compile(r'\b(' + '|'.join(MONTHS) + r')\b\s+(?:\d{1,2}\s*,\s*)?(20\d{2})')

COLS = ['trading_days', 'accounts', 'net_new', 'darts', 'ann_dart_acct',
        'opt_contracts', 'fut_contracts', 'stk_shares', 'equity', 'credits', 'margin']


def load_skill():
    """只为拿 parse_pr（新闻稿解析）——历史指标的数字一律走 series/ibkr.csv。"""
    p = os.path.join(SKILL, 'build_report.py')
    if not os.path.exists(p):
        raise SystemExit(f'找不到 skill 解析管道: {p}')
    spec = importlib.util.spec_from_file_location('ibkr_br', p)
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)
    return br


def month_add(y, m, delta):
    t = y * 12 + (m - 1) + delta
    return t // 12, t % 12 + 1


def read_series():
    """series/ibkr.csv → {'YYYY-MM': {列: float}}。缺列直接失败，不静默补 None。"""
    path = os.path.join(SERIES, 'ibkr.csv')
    if not os.path.exists(path):
        raise SystemExit(f'找不到 {path}')
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit('series/ibkr.csv 是空的')
    missing = [c for c in COLS if c not in rows[0]]
    if missing:
        raise SystemExit(f'series/ibkr.csv 缺列: {missing}')
    out = {}
    for r in rows:
        key = r['month'].strip()
        if not re.fullmatch(r'20\d{2}-\d{2}', key):
            raise SystemExit(f'series/ibkr.csv 月份格式异常: {r["month"]!r}')
        out[key] = {c: (float(r[c]) if r[c] not in ('', None) else None) for c in COLS}
    return out


def parse_hist_notes(page):
    """抓历史指标 PDF 每页 'Notes:' 到页脚之间、与口径调整有关的条目原文。

    skill 的 parse_hist_page 用的是整串锚定的数字正则，Notes 段的长句一句都命中不了，
    于是「表内差分 ≠ 真实账户增长」这类说明被整段丢弃，Ex3 就挂着 +22pp 的错值而
    页面上没有任何痕迹。这里单独再抓一遍：既渲染到页面上，也用来做护栏——
    命中脚注却没在 ADJ 里登记的月份直接 raise，宁可月度 routine 失败也不静默发错图。
    """
    t = page.get_text()
    i = t.find('Notes:')
    if i < 0:
        return []
    seg = re.split(r'Page \d+ of \d+', t[i + len('Notes:'):])[0]
    out = []
    # Notes 段是 (1)(2)(3) 编号条目；按编号切而不是按句号切——正文里有 "vs." 这种缩写，
    # 按句号切会把「real account growth in September 2025 was 111.9 ... vs.」拦腰截断。
    for part in re.split(r'\(\d\)\s*', seg):
        s = ' '.join(part.split())
        if not s or not NOTE_RE.search(s):
            continue
        ms = sorted({f'{y}-{MONTHS.index(mo) + 1:02d}' for mo, y in MONTH_RE.findall(s)})
        out.append({'text': s, 'months': ms})
    return out


def pctf(x, d=0):
    """与 build_report.py 的 pctf 完全一致。"""
    return f"{'+' if x > 0 else ''}{x * 100:.{d}f}%"


def comma(v, d=0):
    return f'{v:,.{d}f}'


def main():
    br = load_skill()
    import fitz

    series = read_series()

    # ── 历史指标 PDF 的 Notes 段：只取文字（护栏 + 图注），数字全部来自 CSV ──
    hist_pdf = os.path.join(CACHE, 'hist_latest.pdf')
    if not os.path.exists(hist_pdf):
        raise SystemExit(f'找不到 {hist_pdf}（先跑 fetch/ibkr.py 落缓存）')
    doc = fitz.open(hist_pdf)
    notes = []
    for i in range(doc.page_count):
        notes.extend(parse_hist_notes(doc[i]))

    # 护栏：脚注点名的月份必须在 ADJ 里有登记，否则整个 routine 失败
    flagged = sorted({m for nt in notes for m in nt['months']})
    unknown = [m for m in flagged if m not in ADJ]
    if unknown:
        raise SystemExit(
            f'历史指标 PDF 的 Notes 提到 {unknown} 有账户口径调整，但 build/ibkr.py 的 ADJ 表里没有登记。\n'
            f'请照 PDF 原文补 ADJ 条目后再跑（宁可失败也不要把未还原的 y/y 发上线）。\n'
            + '\n'.join('  · ' + nt['text'] for nt in notes))

    # ── 目标月 = 最新有 trading_days 的月份 ──
    avail = sorted(k for k, v in series.items() if v.get('trading_days'))
    if not avail:
        raise SystemExit('series/ibkr.csv 里没有可用月份')
    target = avail[-1]
    ty, tm = int(target[:4]), int(target[5:7])

    # ── 全历史轴（Exhibit 14-18）：必须逐月连续，否则 12 个月滚动和与 y/y 会错位 ──
    ALL = avail
    for i in range(1, len(ALL)):
        py, pmo = month_add(int(ALL[i - 1][:4]), int(ALL[i - 1][5:7]), 1)
        if f'{py}-{pmo:02d}' != ALL[i]:
            raise SystemExit(f'历史序列不连续: {ALL[i-1]} → {ALL[i]}')
    XL_LONG = [f'{int(k[5:7])}/{k[2:4]}' for k in ALL]

    # 还原后的净新增账户：y/y 的分子分母一律用 real
    real_nn = {k: series[k]['net_new'] for k in ALL}
    for k, a in ADJ.items():
        if a['field'] == 'net_new' and k in real_nn:
            real_nn[k] = a['real']

    # ── 13 个月窗口 ──
    WIN, XL = [], []
    for d in range(-12, 1):
        y, m = month_add(ty, tm, d)
        WIN.append(f'{y}-{m:02d}')
        XL.append(f'{m}/{y % 100:02d}')
    prevm, yagm = {}, {}
    for i, w in enumerate(WIN):
        y, m = month_add(ty, tm, -13 + i)
        prevm[w] = f'{y}-{m:02d}'
        yagm[w] = f'{int(w[:4])-1}-{w[5:]}'

    need = set(WIN) | set(prevm.values()) | set(yagm.values())
    missing = sorted(w for w in need if w not in series)
    if missing:
        raise SystemExit(f'series/ibkr.csv 缺月份: {missing}')

    # ── 月度新闻稿（佣金与订单规模）：只读缓存，不下载（下载是 fetch/ibkr.py 的职责）──
    COMM = {}
    for w in WIN:
        p = os.path.join(CACHE, f'pr_{w.replace("-", "")}.pdf')
        if not os.path.exists(p):
            raise SystemExit(f'缺少新闻稿缓存 {p}（先跑 fetch/ibkr.py）')
        COMM[w] = br.parse_pr(p)

    # 数据源发布日：优先取目标月新闻稿的电头日期（"GREENWICH, CT, August 3, 2026 —"），
    # 取不到再退回历史指标 PDF 的 creationDate；两者都拿不到就整个字段省略。
    source_date = None
    try:
        prt = fitz.open(os.path.join(CACHE, f'pr_{target.replace("-", "")}.pdf'))[0].get_text()
        mdl = re.search(r'\b(' + '|'.join(MONTHS) + r')\s+(\d{1,2}),\s*(20\d{2})\s*[—–-]', prt)
        if mdl:
            source_date = f'{mdl.group(3)}-{MONTHS.index(mdl.group(1)) + 1:02d}-{int(mdl.group(2)):02d}'
    except Exception:
        pass
    if not source_date:
        cd = (doc.metadata or {}).get('creationDate') or ''
        m = re.match(r'D:(\d{4})(\d{2})(\d{2})', cd)
        if m:
            source_date = f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    # ── 派生序列（逐行照抄 build_report.py 的算法）──
    S = lambda f: np.array([series[m][f] for m in WIN], float)
    cpt = np.array([COMM[m][0] for m in WIN])
    stk_os = np.array([COMM[m][1] for m in WIN]); stk_cpt = np.array([COMM[m][2] for m in WIN])
    opt_os = np.array([COMM[m][3] for m in WIN]); opt_cpt = np.array([COMM[m][4] for m in WIN])
    fut_os = np.array([COMM[m][5] for m in WIN]); fut_cpt = np.array([COMM[m][6] for m in WIN])

    net_new = S('net_new')                                   # Ex2 画的是表内披露值
    nn_real = np.array([real_nn[m] for m in WIN])            # Ex3 的 y/y 用还原值
    nn_yoy = np.array([real_nn[m] / real_nn[yagm[m]] - 1 for m in WIN])
    ann_dart = S('ann_dart_acct'); accounts = S('accounts')
    acct_prev = np.array([series[prevm[m]]['accounts'] for m in WIN])
    cleared = ann_dart / 252 * (accounts + acct_prev) / 2
    # 量纲：cleared（千笔/日）× cpt（$/笔）= 千美元/日；÷1000 → 百万美元/日（$mn/day）
    comm_day = cleared * cpt / 1000
    margin = S('margin'); credits = S('credits')
    # GS 规矩 2：融资余额与客户现金都不是高增速指标，m/m 只是 ±2% 噪音，改画 y/y
    marg_yoy = margin / np.array([series[yagm[m]]['margin'] for m in WIN]) - 1
    cred_yoy = credits / np.array([series[yagm[m]]['credits'] for m in WIN]) - 1
    td = S('trading_days')
    stk_d = S('stk_shares') / stk_os / td
    opt_d = S('opt_contracts') / opt_os / td
    fut_d = S('fut_contracts') / fut_os / td
    pct_fo = (opt_d + fut_d) / (stk_d + opt_d + fut_d)
    darts_win = S('darts')
    cov_prod = (stk_d + opt_d + fut_d) / darts_win * 100      # 推导产品 DARTs 对披露总量的覆盖率
    cov_cleared = cleared / darts_win * 100

    avg12 = lambda a: float(np.mean(a[:12]))
    yoy = lambda a: float(a[-1] / a[0] - 1)
    mom = lambda a: float(a[-1] / a[-2] - 1)
    L = lambda a: [round(float(v), 6) for v in a]
    LN = lambda a: [None if v is None or not np.isfinite(v) else round(float(v), 6) for v in a]

    # ── 全历史派生序列（Exhibit 14-18）──
    A = lambda f: np.array([series[m][f] if series[m][f] is not None else np.nan for m in ALL], float)
    ann_all, acc_all, eq_all = A('ann_dart_acct'), A('accounts'), A('equity')
    cr_all, mg_all, dart_all = A('credits'), A('margin'), A('darts')
    nn_all = np.array([real_nn[m] for m in ALL], float)

    roll12 = np.full(len(ALL), np.nan)
    for i in range(11, len(ALL)):
        roll12[i] = nn_all[i - 11:i + 1].sum()
    cleared_all = np.full(len(ALL), np.nan)
    cleared_all[1:] = ann_all[1:] / 252 * (acc_all[1:] + acc_all[:-1]) / 2
    # 右轴画「未清算占比」而不是 cleared/total 本身：bar_line_dual 的右轴强制含 0，
    # 84%~92% 的序列会被压在轴顶 8% 的高度里，2025 那个台阶只剩 3px。取补数后量程
    # 0-16%，台阶清清楚楚，信息一模一样（两者相加恒为 100%）。
    noncl_all = 100 - cleared_all / dart_all * 100
    cr_share = cr_all / eq_all * 100
    mg_share = mg_all / eq_all * 100

    def yr_mean(arr, yr):
        idx = [i for i, k in enumerate(ALL) if k[:4] == yr]
        return float(np.nanmean(arr[idx])) if idx else float('nan')

    pre25 = [i for i, k in enumerate(ALL) if k < '2025-01']
    post25 = [i for i, k in enumerate(ALL) if k >= '2025-01']

    # ── Exhibit 定义（标题文案逐字照抄 build_report.py 的 title_src 调用）──
    ex = []

    # Ex2 的 x 标签给有口径调整的月份挂 †：柱画的是表内披露值，读者要能一眼看到哪根柱不可直读
    adj_nn = [k for k, a in ADJ.items() if a['field'] == 'net_new']
    XL2 = [x + ('†' if WIN[i] in adj_nn else '') for i, x in enumerate(XL)]
    XL3 = [x + ('†' if (WIN[i] in adj_nn or yagm[WIN[i]] in adj_nn) else '') for i, x in enumerate(XL)]
    adj_txt = '；'.join(f'{k} 表内 {ADJ[k]["reported"]:.1f}k → 公司披露真实增长 {ADJ[k]["real"]:.1f}k'
                       f'（{ADJ[k]["reason"]}）' for k in sorted(adj_nn))

    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL2,
        'title': f'IBKR added ~{net_new[-1]:.0f}k net new accounts, with monthly account growth {pctf(mom(net_new))} MoM…',
        'ylab': 'Net New Accounts (thousands)',
        'note': ('柱与 12 个月均线画的是历史指标表披露的 Net New Accounts（= 账户存量差分）。'
                 f'† 的月份含一次性口径调整，不可与相邻柱直读：{adj_txt}。Exhibit 3 的 y/y 已用还原值。'
                 + ('<br>PDF Notes 原文：' + ' / '.join(nt['text'] for nt in notes) if notes else '')),
        'legend': 'Net New Accounts', 'values': L(net_new), 'avg12': avg12(net_new),
        'yoy_txt': pctf(yoy(nn_real)), 'mom_txt': pctf(mom(net_new)),
        'bar_marks': [i for i, w in enumerate(WIN) if w in adj_nn],
        'mark_note': '该月含一次性账户口径调整，见图注 †',
    })
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct0z', 'xlabels': XL3,
        'title': f'…and net new accounts {"growing" if nn_yoy[-1] > 0 else "declining"} {abs(nn_yoy[-1])*100:.0f}% YoY',
        'ylab': 'Change in Net New Accounts YoY (%)', 'values': L(nn_yoy * 100),
        'note': ('分子分母一律用公司 Notes 还原后的真实账户增长：2025-03 87.7k（还原前 74.4k）、'
                 '2025-09 111.9k（还原前 73.1k）。† 标出受影响的月份（自身或去年同月被还原）。'
                 '直接用表内差分会让 2026-03 的 y/y 从 +23% 虚高到 +45%。'),
    })
    ex.append({
        'n': 4, 'kind': 'gs_bar', 'fmt': 'f0c',
        'title': f'Implied cleared DARTs came in {abs(yoy(cleared))*100:.0f}% {"higher" if yoy(cleared) > 0 else "lower"} YoY, and '
                 f'{abs(cleared[-1]/avg12(cleared)-1)*100:.0f}% {"above" if cleared[-1]/avg12(cleared)-1 > 0 else "below"} the prior 12-month average…',
        'ylab': 'Cleared DARTs (thousands of trades/day)',
        'note': 'We calculate cleared DARTs = Cleared avg. DART per account (annualized) / 252 trading days * '
                'average of beginning- and end-of-month total accounts. '
                '假设：账户数在月内线性变化（故取期初期末简单平均）；官方的年化口径就是按 252 天折算，'
                '不要换成当月实际交易日。'
                f'结果约为 IBKR 单独披露的 Total Client DARTs 的 {cov_cleared.min():.0f}%–{cov_cleared.max():.0f}%'
                '（窗口内），差额是口径差（cleared ≠ total client，见 Exhibit 18），不是估算误差。',
        'legend': 'Implied Cleared DARTs', 'values': L(cleared), 'avg12': avg12(cleared),
        'yoy_txt': pctf(yoy(cleared)), 'mom_txt': pctf(mom(cleared)),
    })
    ex.append({
        'n': 5, 'kind': 'gs_line', 'fmt': 'x0',
        'title': f'…leading to {pctf(yoy(ann_dart))} annualized cleared DARTs per account vs. last year',
        'ylab': 'Annualized DARTs / Account (x)', 'values': L(ann_dart),
        'yoy_txt': pctf(yoy(ann_dart)), 'mom_txt': pctf(mom(ann_dart)), 'ovals_at_bottom': True,
        'note': '公司直接披露的 Cleared Avg. DART per Account (Annualized)，非推导值。'
                '长历史见 Exhibit 14——窗口内的波动是一个已经腰斩后的低位平台。',
    })
    ex.append({
        'n': 6, 'kind': 'gs_bar', 'fmt': 'f1',
        'title': f'Implied commission revenue/day came in {abs(yoy(comm_day))*100:.0f}% {"higher" if yoy(comm_day) > 0 else "lower"} YoY '
                 f'and {pctf(mom(comm_day))} MoM',
        'ylab': 'Implied Commission Revenue / Day ($mn)',
        'note': 'Commission revenue/day estimated as cleared DARTs (千笔/日) x average commission per cleared '
                'commissionable order ($/笔) ÷ 1,000 → $mn/day。'
                '假设：新闻稿披露的是 average commission per cleared <b>commissionable</b> order，而乘数是全部 '
                'cleared DART，两个总体是否一致未经证实——若 DART 计入免佣订单，本图偏高；'
                'cleared DARTs 本身也是推导值，两层近似复合。要得到月度总额还需再乘当月官方交易日数。'
                '月度无对应披露可比，季度有（10-Q 的 Commissions 行），但尚未接入。',
        'legend': 'Implied Commission Revenue/Day', 'values': L(comm_day), 'avg12': avg12(comm_day),
        'yoy_txt': pctf(yoy(comm_day)), 'mom_txt': pctf(mom(comm_day)),
    })
    dc = (cpt[-1] - cpt[-2]) * 100
    vs7 = cpt[-1] / avg12(cpt) - 1
    ex.append({
        'n': 7, 'kind': 'gs_line_avg', 'fmt': 'usd2',
        # 用户提供的参考 PDF（2026-07-03 生成）此处是分币符号 ¢；skill 当前版本
        # （2026-07-14 改过）写的是 ASCII 'c'。以参考 PDF 为准，并且 ¢ 是正确排版。
        'title': f'Average CPT {"decreased" if dc < 0 else "increased"} by {abs(dc):.0f}¢ MoM, and was '
                 f'{abs(vs7)*100:.0f}% {"below" if vs7 < 0 else "above"} the 12-month average',
        'ylab': 'Average commission / DART ($)', 'values': L(cpt), 'avg12': avg12(cpt),
        'legend': 'Avg. Commission/DART', 'avg_label': 'Prior 12mo Avg.',
    })

    dpp = (pct_fo[-1] - pct_fo[-2]) * 100
    fo_mom = (opt_d[-1] + fut_d[-1]) / (opt_d[-2] + fut_d[-2]) - 1
    st_mom = stk_d[-1] / stk_d[-2] - 1
    clause = ('as stock DARTs increased more than options and futures' if (dpp < 0 and st_mom > fo_mom)
              else ('as options and futures DARTs outgrew stocks' if dpp > 0 else 'on shifting product mix'))
    ex.append({
        'n': 8, 'kind': 'stacked_dual',
        'title': f'Implied product DARTs: the % in the form of F&O {"decreased" if dpp < 0 else "increased"} '
                 f'{abs(dpp):.1f}pp MoM, {clause}',
        'note': 'Product DARTs estimated as monthly volume / average order size / US trading days. '
                '假设：average order size 取的是全部订单的均值；对期货与国际股票同样套用<b>美股</b>交易日数。'
                f'本图各产品推导值合计约为披露 Total Client DARTs 的 {cov_prod.min():.1f}%~{cov_prod.max():.1f}%'
                '（近 13 个月），故本图口径接近 cleared 而非 total（下方总表那一列是 Total Client DARTs）。',
        'stacks': [
            {'name': 'Implied Stock DARTs', 'color': 'BLUE', 'values': L(stk_d), 'label': True, 'label_color': 'NAVY'},
            {'name': 'Implied Options DARTs', 'color': 'GRAY', 'values': L(opt_d), 'label': True, 'label_color': 'WHITE'},
            {'name': 'Implied Futures DARTs', 'color': 'NAVY', 'values': L(fut_d), 'label': False},
        ],
        'line': {'name': '% Futures/Options', 'color': 'GREEN', 'values': L(pct_fo * 100), 'ymax': 60},
    })
    chg_cpt = [('stocks', stk_cpt[-1] / stk_cpt[-2] - 1), ('options', opt_cpt[-1] / opt_cpt[-2] - 1),
               ('futures', fut_cpt[-1] / fut_cpt[-2] - 1)]
    dec = [f'{abs(c)*100:.0f}% for {n}' for n, c in chg_cpt if c <= -0.01]
    inc = [f'{abs(c)*100:.0f}% for {n}' for n, c in chg_cpt if c >= 0.01]
    flat = [n for n, c in chg_cpt if abs(c) < 0.01]
    parts = []
    if dec: parts.append('decreased ' + ', '.join(dec))
    if inc: parts.append('increased ' + ', '.join(inc))
    ex.append({
        'n': 9, 'kind': 'lines_endlabels', 'fmt': 'usd2',
        'title': 'Average commissions/trade ' + ' and '.join(parts or ['were stable']) + ' MoM' +
                 (f', and were largely flat for {", ".join(flat)}' if flat else ''),
        'ylab': 'Average commission per trade ($)',
        'series': [
            {'name': 'Stocks Avg CPT', 'color': 'NAVY', 'values': L(stk_cpt)},
            {'name': 'Options Avg CPT', 'color': 'BLUE', 'values': L(opt_cpt)},
            {'name': 'Futures Avg CPT', 'color': 'MBLUE', 'values': L(fut_cpt)},
        ],
    })
    va10 = margin[-1] / avg12(margin) - 1
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f1',
        'title': f'Customer margin balances {"rose" if yoy(margin) > 0 else "fell"} by {abs(yoy(margin))*100:.0f}% YoY, '
                 f'{abs(va10)*100:.0f}% {"above" if va10 > 0 else "below"} the prior 12 month average',
        'ylab': 'Customer Margin Balances ($bn)',
        'legend': 'Customer Margin Balances', 'values': L(margin), 'avg12': avg12(margin),
        'yoy_txt': pctf(yoy(margin)), 'mom_txt': pctf(mom(margin)),
    })
    ex.append({
        'n': 11, 'kind': 'gs_line', 'fmt': 'pct0',
        'title': f'Customer margin balances {"increased" if marg_yoy[-1] > 0 else "decreased"} by {abs(marg_yoy[-1])*100:.0f}% YoY',
        'ylab': 'YoY customer margin balances change (%)', 'values': L(marg_yoy * 100),
        'note': '融资余额不是高增速指标，m/m 基本是噪音，故本图画 y/y（相对 Exhibit 10 同一序列的去年同月）。'
                '余额的绝对水平在创新高，但相对客户权益的占比仍在低位，见 Exhibit 17。',
    })
    va12 = credits[-1] / avg12(credits) - 1
    ex.append({
        'n': 12, 'kind': 'gs_bar', 'fmt': 'f1',
        'title': f'Client cash {"increased" if yoy(credits) > 0 else "decreased"} {abs(yoy(credits))*100:.0f}% YoY, to '
                 f'{abs(va12)*100:.0f}% {"above" if va12 > 0 else "below"} the prior 12 months average…',
        'ylab': 'Total Client Cash ($bn)',
        'note': 'Client cash = total client credit balances, including insured bank deposit sweeps.',
        'legend': 'Total Client Cash', 'values': L(credits), 'avg12': avg12(credits),
        'yoy_txt': pctf(yoy(credits)), 'mom_txt': pctf(mom(credits)),
    })
    ex.append({
        'n': 13, 'kind': 'gs_line', 'fmt': 'pct0',
        'title': f'…and was {"up" if cred_yoy[-1] > 0 else "down"} ~{abs(cred_yoy[-1])*100:.0f}% YoY',
        'ylab': 'YoY client cash change (%)', 'values': L(cred_yoy * 100),
        'note': '同 Exhibit 11：客户现金的 m/m 中位数只有约 1.4%，画 y/y 才有信息量。',
    })

    # ── 长历史（Exhibit 14-18）：2016-01 起，x 轴每 12 个月一个标签 ──
    y16, ylast = ALL[0][:4], target[:4]
    ex.append({
        'n': 14, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'f0',
        'title': f'Annualized cleared DARTs per account: {yr_mean(ann_all, y16):.0f}x avg. in {y16} → '
                 f'{yr_mean(ann_all, ylast):.0f}x YTD in {ylast}, '
                 f'{(1 - yr_mean(ann_all, ylast) / yr_mean(ann_all, y16)) * 100:.0f}% below the {y16} level',
        'ylab': 'Annualized cleared DARTs / account (x)',
        'note': '<b>公司直接披露值，非本站推导。</b>年均：'
                + '、'.join(f'{y} {yr_mean(ann_all, y):.0f}x' for y in
                           [y16, '2019', '2020', '2022', '2023', ylast])
                + '。2020-21 的凸起是疫情期间的交易热潮，其后回落到的平台明显低于 2016-18——'
                  'Exhibit 5 的窗口只覆盖最后 13 个月，看不出这是结构性下台阶还是周期性回落。',
        'series': [{'name': 'Cleared avg. DART per account (annualized)', 'color': 'NAVY',
                    'values': LN(ann_all)}],
    })
    ex.append({
        'n': 15, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'f0c',
        'title': f'Trailing-12-month net new accounts at {roll12[-1]:,.0f}k, vs. '
                 f'{roll12[ALL.index("2021-12")]:,.0f}k in Dec-21 and {roll12[ALL.index("2018-12")]:,.0f}k in Dec-18',
        'ylab': 'Net new accounts, trailing 12 months (thousands)',
        'note': '12 个月滚动和，回答「这轮开户潮相对历史有多大」。已按公司 Notes 还原 2025-03 / 2025-09 '
                '的真实账户增长（87.7k / 111.9k），前 11 个月不足一年故留空。',
        'series': [{'name': 'Net new accounts, T12M', 'color': 'NAVY', 'values': LN(roll12)}],
    })
    ex.append({
        'n': 16, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'f0c',
        'title': f'Client equity at ${eq_all[-1]:,.0f}bn, {eq_all[-1] / eq_all[0]:.1f}x the '
                 f'${eq_all[0]:,.0f}bn of {XL_LONG[0]}',
        'ylab': 'Client Equity ($bn)',
        'note': '公司披露值（期末口径，不含非客户余额）。它是 Exhibit 10 / 12 两条余额的分母，也是 NII 的规模基数，'
                '此前站上一张图都没有。',
        'series': [{'name': 'Client Equity', 'color': 'NAVY', 'values': LN(eq_all)}],
    })
    ex.append({
        'n': 17, 'kind': 'lines', 'x': 'long', 'xstep': 12, 'fmt': 'pct1',
        'title': f'Both interest-earning bases keep shrinking vs. client equity: client cash '
                 f'{cr_share[-1]:.1f}% and margin loans {mg_share[-1]:.1f}%, vs. '
                 f'{cr_share[0]:.1f}% / {mg_share[0]:.1f}% in {XL_LONG[0]}',
        'ylab': 'as % of client equity (%)',
        'note': '<b>这是比值，不是公司披露值</b>：分子分母都取自官方历史指标表同一张表内的 Client Credits / '
                'Client Margin Loans / Client Equity。历史最低：客户现金/权益 '
                f'{np.nanmin(cr_share):.2f}%（{ALL[int(np.nanargmin(cr_share))]}）、融资余额/权益 '
                f'{np.nanmin(mg_share):.2f}%（{ALL[int(np.nanargmin(mg_share))]}）。'
                'Exhibit 10 / 12 的绝对额在创新高，但这两条生息基数相对资产规模仍不到 2016-18 年的一半。',
        'series': [
            {'name': 'Client cash / client equity', 'color': 'NAVY', 'values': LN(cr_share)},
            {'name': 'Margin loans / client equity', 'color': 'MBLUE', 'values': LN(mg_share)},
        ],
    })
    brk = ALL.index('2025-01')
    ex.append({
        'n': 18, 'kind': 'bar_line_dual', 'x': 'long', 'xstep': 12, 'full': True, 'height': 300,
        'title': f'Total client DARTs (disclosed) at {dart_all[-1]:,.0f}k/day; the share NOT captured by implied '
                 f'cleared DARTs stepped up from ~{np.nanmean(noncl_all[pre25]):.0f}% to '
                 f'~{np.nanmean(noncl_all[post25]):.0f}% during 2025',
        'ylab': 'Total Client DARTs (thousands of trades/day)',
        'ylab2': 'Implied non-cleared share (%)',
        'bar': {'name': 'Total Client DARTs (disclosed)', 'color': 'BLUE', 'values': LN(dart_all),
                'yfmt': 'f0c'},
        'line': {'name': '1 − implied cleared ÷ total client DARTs (RHS)', 'color': 'GREEN',
                 'values': LN(noncl_all), 'yfmt': 'pct0'},
        'break_at': brk, 'break_label': '2025：疑似口径变更',
        'note': '柱是公司直接披露的 Total Client DARTs；右轴线 = 1 − 推导 cleared DARTs ÷ 披露 Total Client DARTs'
                '（等价于 cleared/total 的补数——bar_line_dual 的右轴强制含 0，直接画 85%~92% 的比值会被压成一条'
                '看不出变化的平线）。cleared/total 的逐年均值：'
                + '、'.join(f'{y} {np.nanmean(1 - noncl_all[[i for i, k in enumerate(ALL) if k[:4] == y]] / 100):.3f}'
                           for y in ['2016', '2019', '2022', '2024', '2025', ylast])
                + '——2019 前后降过一档，2019-2024 六年横盘，2025 起再降一档并保持，'
                  '<b>疑似口径/分类变更，未经公司确认</b>（红色虚线右侧与左侧不可直读）。'
                  '另需提示：推导 cleared DARTs 是用<b>总账户数</b>反推的，而官方指标是 per <b>cleared</b> account，'
                  '若 cleared 账户占总账户的比例本身在变，这条线里就混了推导误差，不能整条归因给 omnibus 渠道。',
    })

    # ── Exhibit 1：汇总表（本月|上月|去年同月 ‖ m/m|y/y|3Y %ile）──
    # 单元格全部是**已格式化的字符串** + 颜色类：pp/bp、反向指标、分位反转这些格式化口径
    # 原先写在 index.html 的 chgCell() 里，现在一并搬到 Python 侧（CONTRACT §2）。
    ti = len(ALL) - 1

    def pctile36(arr, i):
        """单调趋势序列（账户总数、客户权益）留空：它们几乎每月创新高，
        分位恒为 ~100 并被着成绿色，是零信息量却带「异常之高」的暗示。
        用「上升月份占比 ≥ 90%」判定单调，比按字段名写死更稳。"""
        h = arr[max(0, i - 35):i + 1]
        h = h[np.isfinite(h)]
        if len(h) < 8 or not np.isfinite(arr[i]):
            return None
        d = np.diff(h)
        if len(d) and float((d > 0).sum()) / len(d) >= 0.90:
            return None
        return round(float((h < arr[i]).sum()) / max(1, len(h) - 1) * 100, 1)

    def chg(a, b, mode):
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if mode == 'pp':
            return round(float(a - b), 4)
        if b == 0 or a * b < 0:          # 分母为 0 或两期异号时百分比变化无意义
            return None
        return round(float(a / b - 1) * 100, 4)

    # (板块, 标签, 序列, 小数位, 前缀, mode, invert)；invert=True 表示下降为好
    SUM_ROWS = [
        ('账户', None, None, 0, '', '', False),
        (None, '账户总数（千户）', acc_all, 1, '', 'ratio', False),
        (None, '净新增账户（千户，已还原口径）', nn_all, 1, '', 'ratio', False),
        ('交易活动', None, None, 0, '', '', False),
        (None, '人均年化 cleared DART（x）', ann_all, 0, '', 'ratio', False),
        (None, 'Implied cleared DARTs（千笔/日）', cleared_all, 0, '', 'ratio', False),
        ('客户资产与余额', None, None, 0, '', '', False),
        (None, '客户权益（$bn）', eq_all, 1, '$', 'ratio', False),
        (None, '客户现金（$bn）', cr_all, 1, '$', 'ratio', False),
        (None, '融资余额（$bn）', mg_all, 1, '$', 'ratio', False),
    ]
    srows = []
    for grp, lab, arr, d, pre, mode, inv in SUM_ROWS:
        if lab is None:
            srows.append({'kind': 'group', 'label': grp})
            continue
        c, p1, p12 = arr[ti], arr[ti - 1], arr[ti - 12]
        f = lambda v: ('—' if not np.isfinite(v) else pre + comma(v, d))
        cells = [{'v': f(c), 'cls': 'cur'}, {'v': f(p1)}, {'v': f(p12)}]
        for b in (p1, p12):
            v = chg(c, b, mode)
            if v is None:
                cells.append({'v': ''})
                continue
            # 比率类指标的差异用 pp / bp（|v| < 1 用 bp）；其余用百分比变化
            if mode == 'pp':
                txt = f'{v*100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
            else:
                txt = f'{v:+.1f}%'
            good = (v < 0) if inv else (v > 0)      # 反向指标（越低越好）在这里定色
            cells.append({'v': txt, 'cls': 'pos' if good else 'neg'})
        p = pctile36(arr, ti)
        if p is None:
            cells.append({'v': ''})
        else:
            pv = (100 - p) if inv else p            # 反向指标的分位要先反转再判高低
            cells.append({'v': f'{p:.0f}',
                          'cls': 'hi' if pv >= 66 else ('lo' if pv <= 33 else '')})
        srows.append({'label': lab, 'cells': cells})

    month_name = datetime.date(ty, tm, 1).strftime('%B %Y')
    summary = {
        'title': f'{month_name} 汇总 —— 本月 vs 上月／去年同月，及近 3 年分位',
        'heads': ['本月 ' + XL[-1], '上月 ' + XL[-2], '去年同月 ' + XL[0], 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': '3Y %ile = 当月读数在最近 36 个月里高于多少个百分比的观测（分位越高越极端）。'
                '净新增账户按公司 Notes 还原（2025-03 87.7k、2025-09 111.9k）。'
                'CPT 与 F&O 占比来自月度新闻稿，本地只缓存 13 个月，做不出 3Y 分位，故不列。',
    }

    # ── 13 个月核对附表（官方原始单位，便于与披露逐条核对）──
    TCOLS = [('交易日', 'trading_days', 0), ('账户总数 千户', 'accounts', 1),
             ('净新增 千户', 'net_new', 1), ('Total Client DARTs 千笔/日（含未清算）', 'darts', 0),
             ('人均年化 DART', 'ann_dart_acct', 0), ('期权 千张', 'opt_contracts', 0),
             ('期货 千张', 'fut_contracts', 0), ('股数 千股', 'stk_shares', 0),
             ('客户权益 $bn', 'equity', 1), ('客户现金 $bn', 'credits', 1),
             ('融资余额 $bn', 'margin', 1)]
    trows = []
    for i, w in enumerate(WIN):
        r = {'xl': XL[i]}
        for _, key, dec in TCOLS:
            v = series[w][key]
            r[key] = None if v is None else comma(v, dec)
        trows.append(r)
    table = {
        'n': 19, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份', 'cols': [[lab, key] for lab, key, _ in TCOLS], 'rows': trows,
    }

    headline = (f'净新增账户 {net_new[-1]:.1f}k ({pctf(yoy(nn_real))} YoY) · cleared DARTs {cleared[-1]:,.0f}k '
                f'({pctf(yoy(cleared))} YoY) · CPT ${cpt[-1]:.2f} · 融资余额 ${margin[-1]:.1f}B '
                f'({pctf(yoy(margin))} YoY) · 客户现金 ${credits[-1]:.1f}B ({pctf(yoy(credits))} YoY)')
    hub = (f'净新增 {net_new[-1]:.0f}k（{pctf(yoy(nn_real))} y/y）、'
           f'cleared DARTs {cleared[-1]:,.0f}k（{pctf(yoy(cleared))} y/y）')

    payload = {
        'ticker': 'ibkr',
        'tracker': 'Interactive Brokers Group (IBKR): Monthly Brokerage Metrics',
        'title': f'Monthly Brokerage Metrics — {month_name}',
        'data_through': target,
        'through_label': month_name,
        'subtitle': (f'{month_name} update — Exhibits 2–13, recreated in Goldman Sachs GIR exhibit '
                     f'format from IBKR company data · 窗口 {XL[0]} – {XL[-1]} · '
                     f'Exhibits 14–18 为 {XL_LONG[0]} 起全历史'),
        'headline': headline,
        'hub_line': hub,
        'source': SRC,
        'xlabels': XL,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': [
            '<strong>数据源</strong>：IBKR 官网 IR 的 Historical Brokerage Metrics PDF（每月更新，'
            f'共 11 个年度逐月数据，本站落库为 <code>series/ibkr.csv</code>，{ALL[0]} 起 {len(ALL)} 个月连续）'
            '+ 各月度 Metrics 新闻稿（佣金与产品明细，历史表里没有这两列）。',
            '<strong>单位</strong>：历史指标表首个区块标注 “(in Thousands, except Trading Days)”，'
            '故账户数、净新增、DARTs、期权／期货合约数、股票成交股数均以<strong>千</strong>为单位；'
            '客户权益、客户现金、融资余额区块标注 “(in Billions)”。文末核对表保持官方原始单位，'
            '便于与披露逐条核对。',
            '<strong>Cleared DARTs</strong>（Exhibit 4）= Cleared avg. DART per account（年化）÷ 252 '
            '个交易日 × 期初与期末账户总数的平均值。这是券商研究里的标准还原口径，'
            '<strong>非公司直接披露值</strong>，故图标题一律以 Implied 打头。',
            '<strong>Commission revenue/day</strong>（Exhibit 6）= cleared DARTs（千笔/日）× '
            '单笔清算订单平均佣金（$/笔）<strong>÷ 1,000</strong> → 百万美元/日（$mn/day）。'
            '要得到月度总额还需再乘当月官方交易日数。',
            '<strong>Product DARTs</strong>（Exhibit 8）= 当月成交量 ÷ 平均订单规模 ÷ 美股交易日数。'
            f'三段合计约为披露 Total Client DARTs 的 {cov_prod.mean():.0f}%，'
            '即本图口径接近 cleared 而非 total。',
            '<strong>佣金口径</strong>：新闻稿「Key products」表两列分别是 <em>Average Order Size</em>'
            '（平均订单规模，股／张）与 <em>Average Commission per Cleared Commissionable Order</em>'
            '（单笔清算订单平均佣金，$，含交易所、清算与监管费用）。<strong>不是每股／每张单价。</strong>',
            '<strong>期货</strong>含期货期权；公司估计交易所／清算／监管费用约占期货佣金的 56%。',
            '<strong>账户口径调整</strong>：历史指标 PDF 的 Notes 段披露过三次一次性调整'
            '（2025-03 escheat 13.3k、2025-09 一家 introducing broker 撤出 38.8k、'
            '2024-11 Total Accounts 下调 9.1k）。Exhibit 2 画表内披露值并以 † 标出，'
            'Exhibit 3 与 Exhibit 15 的分子分母一律用公司给的真实增长。解析器每月重新抓这段 Notes，'
            '出现未登记的调整会直接让构建失败。',
            '<strong>窗口</strong>：Exhibit 2-13 固定为最近 13 个月（便于 YoY 首末对比与 prior-12mo '
            f'均值计算，本次为 {XL[0]} – {XL[-1]}）；Exhibit 14-18 为 {ALL[0]} 起的全历史；'
            'Exhibit 1 的 3Y %ile 取近 36 个月。窗口一律从数据最新月倒推，不依赖构建当天的日期。',
            'Exhibits 14-17 of the original Goldman Sachs note (IBKR app downloads and MAU) rely on '
            'proprietary Sensor Tower data and cannot be updated from public company disclosures; '
            '本站的 Exhibit 14-18 是另加的长历史图，与原 note 的编号无对应关系。',
            '本页图表版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，不含其研究观点或数据。'
            '仅供个人研究，不构成投资建议。',
        ],
        'footer': ('数据与算法源自 <code>/IBKR月度指标</code> skill 的解析管道 · '
                   '数值以 IBKR 官网原始披露为准。每张图右上角可切换「表格」视图逐条核对。'),
    }
    if source_date:
        payload['source_date'] = source_date

    os.makedirs(os.path.join(ROOT, 'data'), exist_ok=True)
    path = os.path.join(ROOT, 'data', 'ibkr.js')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(f'// 由 build/ibkr.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write('window.DASH = ')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')

    print(f'目标月 {target} | 窗口 {WIN[0]} → {WIN[-1]}（{len(WIN)} 个月）| '
          f'长历史 {ALL[0]} → {ALL[-1]}（{len(ALL)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'口径脚注 {len(notes)} 条，命中月份 {flagged}')
    print(f'写出 data/ibkr.js ({os.path.getsize(path)/1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
