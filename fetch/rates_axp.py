# -*- coding: utf-8 -*-
"""American Express (AXP) 季度费率解析器 —— SEC EDGAR，无人值守。

给 series/fee_rates.csv 供数：net interest income / 平均余额 / net interest yield。
月度指标那套（8-K Item 7.01 + 10-D）在 fetch/axp.py 里，跟本模块没有交集。

════════ 数据源 ════════
季度业绩 8-K（Item 2.02）的 **Exhibit 99.2「Statistical Tables」**，发行人
AMERICAN EXPRESS CO，CIK 0000004962。

    索引  https://data.sec.gov/submissions/CIK0000004962.json
    目录  https://www.sec.gov/Archives/edgar/data/4962/<acc-nodash>/index.json
    正文  .../q<Q><YY>exhibit992.htm        例：q226exhibit992.htm = 2026 年 Q2

每份 Ex-99.2 横向给 **最近 5 个季度**，所以每期都自带 4 个季度的重述窗口，
全量跑一遍就能看出官方有没有改口径 / 改数。命名 q<Q><YY>exhibit992.htm 从
2019-Q3 到 2026-Q2 一路没变（28 期实测），但代码仍然从 index.json 里找文件名，
不硬编码 URL。

════════ 抽哪几行 ════════
CSV 里 AXP 现有 5 个 metric，对应 Ex-99.2 里这些**行标签**（标签会变，值不变，
所以必须按标签的历史变体全部匹配，不能只认最新写法）：

  net_interest_income                            USD_mn
      合并利润表首行 "Net interest income"（各分部表里也有同名行，取全文第一处）
  avg_cardmember_loans_incl_hfs                  USD_mn
      "Average Card Member loans"（q224–q324）
      "Average Card Member loans including loans held for sale"（q424–q225）
  net_interest_yield_on_cardmember_loans_oldbasis  pct_annualized
      "Net interest yield on average Card Member loans (X)"（…–q324）
      "Net interest yield on average Card Member loans including loans held for sale (X)"（q424–q225）
  avg_card_balances_and_other_loans              USD_mn
      "Average Card balances and Other loans"（q126 起）
  net_interest_yield_newbasis                    pct_annualized
      "Net interest yield (X)"（q325 起）

════════ 口径坑（会咬人的地方）════════
· **单位在 2024-Q2 那期换过**。q124 及更早的 Ex-99.2 里平均余额写成
  "Average Card Member loans (billions) $116.6"，只有 1 位小数；q224 起改成
  "$ 116,626"（百万）。CSV 的 unit 是 USD_mn，所以 (billions) 那种行**直接丢弃**，
  不做 116.6→116,600 的假精度换算。后果：2023-Q2 之前没有平均余额，
  2023-Q2/Q3/Q4 的百万级数字实际最早出现在 q224（不是它们各自当期的申报）。
· **口径换过两次，是三套东西，不是两套**：
    ① 老口径 Card Member loans（含 HFS），yield ≈ 11–12%，末次披露 q225；
    ② q325/q425：分母改成 "Card Member loans and receivables"，yield ≈ 8%；
    ③ q126 起：分母再改成 "Card balances and Other loans"（把 pay-in-full 并进来），
       yield 仍 ≈ 8%。
  CSV 把 ②③ 合并成一个 net_interest_yield_newbasis —— 官方自己给的 ②③ 重叠季度
  yield 完全一致（Q4'25/Q3'25/Q2'25/Q1'25 = 8.0/8.2/7.9/8.2），合并成立；
  但**分母序列不能合并**：q425 说 Q4'25 平均 210,440，q126 说 221,187，
  所以 avg_card_balances_and_other_loans 只认 ③ 的标签，② 的分母根本不入库。
· yield 不是 4×NII/平均余额，是按**实际天数**年化、且分母含 held for sale：
  Q3'23 = 3442×365/92/116,626 = 11.71% → 官方 11.7%。想自查用 365/天数，
  用 ×4 会差 0.1–0.5pp，别当成解析错了。
· "Net interest income" 在合并表、USCS、CS、ICS、GMNS 五张表里都有，
  合并数是全文第一处、也是五者里最大的一个 —— 两个条件都断言，错一个就抛。
· 表头形如 Q2'26 Q1'26 Q4'25 Q3'25 Q2'25 | YOY | YTD'26 YTD'25 | YOY。
  百分比行没有 YOY 单元格，所以**不能按列位对齐**；季度永远是最左 5 列，
  取「标签之后的前 5 个数字」才稳。YTD/FY 列必须扔掉。

════════ 反爬 ════════
EDGAR 无 Cloudflare、无登录、无验证码。标准库 urllib + 带邮箱的 User-Agent 即可
（UA 里没有联系邮箱会整站 403）。串行 + sleep，远低于 SEC 的 10 req/s 上限。
"""
import gzip
import html as _html
import json
import os
import re
import time
import urllib.error
import urllib.request

CIK = '0000004962'
CIK_INT = '4962'
COMPANY = 'AXP'

# SEC 要求 UA 带真实联系方式，否则 403。这不是可选项。
USER_AGENT = os.environ.get('SEC_EDGAR_UA', 'monthly-op-dashboards hzhan7@gmail.com')

SUBMISSIONS = 'https://data.sec.gov/submissions/CIK{cik}.json'
INDEX_JSON = 'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json'
DOC_URL = 'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}'

# 只回溯这么多期业绩 8-K。28 期≈7 年，够覆盖所有口径变更；再往前 Ex-99.2 的
# 分部结构和单位都不一样，解析出来的东西对上层没用。
MAX_FILINGS = 40


class FetchError(RuntimeError):
    """抓不到 / 解析不出时统一抛这个，方便调度器分类告警。"""


# ── metric 定义 ────────────────────────────────────────────────────────
# label_ok(label) -> bool。标签已去掉尾部脚注字母，如 "(C)" "(P)(W)"。
def _mk(*exact):
    s = set(exact)
    return lambda lab: lab in s


METRICS = [
    # (metric, unit, kind, label 判定)
    ('net_interest_income', 'USD_mn', 'num',
     _mk('Net interest income')),
    ('avg_cardmember_loans_incl_hfs', 'USD_mn', 'num',
     _mk('Average Card Member loans',
         'Average Card Member loans including loans held for sale')),
    ('net_interest_yield_on_cardmember_loans_oldbasis', 'pct_annualized', 'pct',
     _mk('Net interest yield on average Card Member loans',
         'Net interest yield on average Card Member loans including loans held for sale')),
    ('avg_card_balances_and_other_loans', 'USD_mn', 'num',
     _mk('Average Card balances and Other loans')),
    ('net_interest_yield_newbasis', 'pct_annualized', 'pct',
     _mk('Net interest yield')),
]

# 合理区间。越界一律抛 —— 单位换挡（十亿 vs 百万）和取错行都会在这里露馅。
SANITY = {
    'net_interest_income': (500, 20000),
    'avg_cardmember_loans_incl_hfs': (50000, 400000),
    'avg_card_balances_and_other_loans': (100000, 600000),
    'net_interest_yield_on_cardmember_loans_oldbasis': (5, 20),
    'net_interest_yield_newbasis': (3, 15),
}


# ── 网络层 ──────────────────────────────────────────────────────────────
def _http_get(url, retries=4):
    """EDGAR 偶发 503/超时，退避重试；连不上就抛，绝不返回半截内容。"""
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept-Encoding': 'gzip, deflate',
            'Accept': '*/*',
        })
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                body = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    body = gzip.decompress(body)
                return body
        except Exception as e:                      # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise FetchError(f'GET 失败 {url}: {last}')


def _cache_dir(cache_dir):
    d = os.path.join(cache_dir, 'axp', 'rates')
    os.makedirs(d, exist_ok=True)
    return d


def _get_cached(cache_dir, name, url, ttl=None):
    """EDGAR 的归档文件是不可变的，落盘后就不再回源；ttl 只给 submissions 用。"""
    p = os.path.join(_cache_dir(cache_dir), name)
    if os.path.exists(p) and (ttl is None or time.time() - os.path.getmtime(p) < ttl):
        with open(p, 'rb') as f:
            return f.read()
    body = _http_get(url)
    with open(p, 'wb') as f:
        f.write(body)
    time.sleep(0.25)                                # SEC 限速，别贴上限跑
    return body


# ── 找文件 ──────────────────────────────────────────────────────────────
def list_exhibits(cache_dir):
    """返回 [(filing_date, accession, exhibit 文件名, url)]，新→旧。"""
    sub = json.loads(_get_cached(cache_dir, 'submissions.json',
                                 SUBMISSIONS.format(cik=CIK), ttl=6 * 3600))
    rec = sub['filings']['recent']
    out = []
    for i, form in enumerate(rec['form']):
        if form != '8-K' or '2.02' not in (rec['items'][i] or ''):
            continue                                # 2.02 = Results of Operations
        acc = rec['accessionNumber'][i].replace('-', '')
        idx = json.loads(_get_cached(cache_dir, f'index_{acc}.json',
                                     INDEX_JSON.format(cik=CIK_INT, acc=acc)))
        names = [it['name'] for it in idx['directory']['item']]
        ex = [n for n in names if re.fullmatch(r'q[1-4]\d{2}exhibit992\w*\.htm', n, re.I)]
        if not ex:
            continue                                # 极老的期次没有这份附件
        out.append((rec['filingDate'][i], rec['accessionNumber'][i], ex[0],
                    DOC_URL.format(cik=CIK_INT, acc=acc, name=ex[0])))
        if len(out) >= MAX_FILINGS:
            break
    if not out:
        raise FetchError('submissions.json 里一份带 Ex-99.2 的业绩 8-K 都没找到')
    return out


# ── HTML 表格 ───────────────────────────────────────────────────────────
def _cells(tbl):
    """把一张 <table> 拆成 [[非空单元格文本, ...], ...]。"""
    rows_ = []
    for tr in re.findall(r'<tr\b.*?</tr>', tbl, re.S | re.I):
        cs = []
        for cell in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', tr, re.S | re.I):
            t = re.sub(r'<[^>]+>', ' ', cell)
            t = _html.unescape(t).replace('\xa0', ' ').replace('’', "'")
            t = re.sub(r'\s+', ' ', t).strip()
            if t:
                cs.append(t)
        rows_.append(cs)
    return rows_


_QTOK = re.compile(r"^Q([1-4])'(\d{2})$")
_FOOT = re.compile(r'(\s*\([A-Z]{1,2}\))+$')        # 尾部脚注 "(C)" / "(P)(W)"
_NUM = re.compile(r'^\(?\$?\s*-?[\d,]+(?:\.\d+)?\s*%?\)?$')


def _header_periods(rows_):
    """表头里的季度列，按出现顺序（官方一律新→旧）。没有就返回 None。"""
    for r in rows_:
        qs = [c for c in r if _QTOK.match(c)]
        if len(qs) >= 2:
            per = []
            for c in qs:
                m = _QTOK.match(c)
                per.append(f'20{m.group(2)}-Q{m.group(1)}')
            return per
    return None


def _numbers(cells):
    """标签之后的数字，按出现顺序；'$' '%' 单独成格或粘在数字上都吃得下。"""
    out = []
    for c in cells:
        c = c.strip()
        if c in ('$', '%', '', '#', '-'):
            continue
        if not _NUM.match(c):
            break                                   # 碰到非数字就停，别越界抓别的行
        v = c.replace('$', '').replace('%', '').replace(',', '').strip()
        neg = v.startswith('(') or c.startswith('(')
        v = v.strip('()')
        try:
            x = float(v)
        except ValueError:
            break
        out.append(-x if neg else x)
    return out


def parse_exhibit(doc):
    """一份 Ex-99.2 → {metric: {period: value}}；只取全文第一处命中的行（= 合并数）。"""
    got = {}
    nii_all = []                                    # 合并数必须是全文最大的那个 NII
    for tbl in re.findall(r'<table\b.*?</table>', doc, re.S | re.I):
        rows_ = _cells(tbl)
        periods = _header_periods(rows_)
        if not periods:
            continue
        for r in rows_:
            if not r:
                continue
            lab = _FOOT.sub('', r[0]).strip()
            if lab.endswith('(billions)') or 'billions' in lab:
                continue                            # 1 位小数的十亿口径，见模块 docstring
            for metric, _unit, kind, ok in METRICS:
                if not ok(lab):
                    continue
                vals = _numbers(r[1:])
                if len(vals) < len(periods[:5]):
                    continue
                pairs = dict(zip(periods[:5], vals[:5]))
                if metric == 'net_interest_income':
                    nii_all.append(vals[0])
                if metric not in got:
                    got[metric] = pairs
    if 'net_interest_income' in got and nii_all:
        first = got['net_interest_income'][max(got['net_interest_income'])]
        if first < max(nii_all) - 1e-9:
            raise FetchError(f'合并 NII 取错行：first={first} max={max(nii_all)}')
    for metric, pairs in got.items():
        lo, hi = SANITY[metric]
        for p, v in pairs.items():
            if not lo <= v <= hi:
                raise FetchError(f'{metric}/{p}={v} 越出合理区间 [{lo},{hi}]')
    if not got:
        raise FetchError('这份 Ex-99.2 一个目标行都没解析出来')
    return got


# ── 汇总 ────────────────────────────────────────────────────────────────
def observations(cache_dir):
    """所有申报 × 所有季度的原始观测：[(filing_date, url, metric, period, value)]。"""
    obs = []
    for i, (fdate, _acc, name, url) in enumerate(list_exhibits(cache_dir)):
        doc = _get_cached(cache_dir, name, url).decode('utf-8', 'replace')
        try:
            got = parse_exhibit(doc)
        except FetchError as e:
            raise FetchError(f'{name}: {e}') from e
        if i == 0:
            # 最新一期的绊线：AXP 改过三次行标签，再改一次时这里必须炸，
            # 不能安静地少给一个 metric（少给的后果是页面停在旧季度还没人知道）。
            yields = {'net_interest_yield_newbasis',
                      'net_interest_yield_on_cardmember_loans_oldbasis'}
            if 'net_interest_income' not in got or not (yields & set(got)):
                raise FetchError(
                    f'{name} 只解析出 {sorted(got)} —— AXP 大概率又改了行标签，'
                    f'去 Ex-99.2 里核对 METRICS 的标签表')
        for metric, pairs in got.items():
            for period, value in pairs.items():
                obs.append((fdate, url, metric, period, value))
    return obs


def rows(cache_dir):
    """AXP 当前官方可得的全部季度费率行。

    同一个 (period, metric) 会被多份申报重复披露。取值规则：
      · 各期一致  → 用**最早**披露它的那份申报作 source_url（原始披露）；
      · 出现分歧  → 官方重述，取**最新**那份的值与 URL（并在 restatements() 里可查）。
    """
    obs = observations(cache_dir)
    by_key = {}
    for fdate, url, metric, period, value in obs:
        by_key.setdefault((period, metric), []).append((fdate, url, value))
    unit = {m: u for m, u, _k, _o in METRICS}

    out = []
    for (period, metric), lst in sorted(by_key.items()):
        lst.sort()                                  # 按 filing_date 升序
        vals = {v for _d, _u, v in lst}
        pick = lst[-1] if len(vals) > 1 else lst[0]
        v = pick[2]
        out.append({
            'company': COMPANY,
            'period': period,
            'metric': metric,
            # 金额取整（CSV 写的是 4649 不是 4649.0），百分比保持 float
            # （CSV 写的是 8.0 不是 8）—— 两边都是为了不给上层制造假 diff
            'value': int(v) if unit[metric] == 'USD_mn' and float(v).is_integer() else v,
            'unit': unit[metric],
            'source_url': pick[1],
        })
    return out


def restatements(cache_dir):
    """(period, metric) 在不同申报里给出过不同数值的清单。"""
    obs = observations(cache_dir)
    by_key = {}
    for fdate, url, metric, period, value in obs:
        by_key.setdefault((period, metric), []).append((fdate, url, value))
    out = []
    for k, lst in sorted(by_key.items()):
        lst.sort()
        if len({v for _d, _u, v in lst}) > 1:
            out.append((k, lst))
    return out


def _fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)


if __name__ == '__main__':
    import argparse
    import csv as _csv

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default=os.path.join(here, 'cache'))
    ap.add_argument('--csv', default=os.path.join(here, 'series', 'fee_rates.csv'))
    a = ap.parse_args()

    got = rows(a.cache)
    idx = {(r['period'], r['metric']): r for r in got}
    print(f'解析出 {len(got)} 行，覆盖 '
          f'{min(r["period"] for r in got)} … {max(r["period"] for r in got)}')

    print('\n── 与 series/fee_rates.csv 现有 AXP 行对账 ──')
    n_ok = n_val = n_url = n_miss = 0
    with open(a.csv, newline='', encoding='utf-8') as f:
        for row in _csv.DictReader(f):
            if row['company'] != COMPANY:
                continue
            k = (row['period'], row['metric'])
            mine = idx.get(k)
            if mine is None:
                n_miss += 1
                print(f'MISSING  {k[0]} {k[1]}  CSV={row["value"]} 解析器没给出')
                continue
            vd = abs(float(row['value']) - mine['value'])
            ud = row['unit'] != mine['unit']
            sd = row['source_url'] != mine['source_url']
            if vd < 1e-9 and not ud and not sd:
                n_ok += 1
            elif vd >= 1e-9 or ud:
                n_val += 1
                print(f'VALUE    {k[0]} {k[1]}  CSV={row["value"]}{row["unit"]} '
                      f'解析={_fmt(mine["value"])}{mine["unit"]} 差={vd}')
            else:
                n_url += 1
                print(f'URL      {k[0]} {k[1]}  值一致={_fmt(mine["value"])}  '
                      f'CSV={row["source_url"].rsplit("/", 1)[-1]} '
                      f'解析={mine["source_url"].rsplit("/", 1)[-1]}')
    print(f'\n完全一致 {n_ok} / 值或单位不符 {n_val} / 仅 source_url 不符 {n_url} / 缺 {n_miss}')

    rs = restatements(a.cache)
    print(f'\n── 官方重述（同一格在不同申报里数值不同）：{len(rs)} 处 ──')
    for (period, metric), lst in rs:
        seq = ' → '.join(f'{d}:{_fmt(v)}' for d, _u, v in lst)
        print(f'  {period} {metric}: {seq}')
