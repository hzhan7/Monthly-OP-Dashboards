# -*- coding: utf-8 -*-
"""fetch/tsm_6k.py 的离线测试 —— 只用标准库，不联网，不进 cron。

跑法: python3 fetch/test_tsm_6k.py
      TSM6K_CACHE=<含 tsm_6k/ 的 cache 目录> python3 fetch/test_tsm_6k.py   （worktree 里指向主 checkout）

━━ 守的是哪几件事 ━━
1. 口径：TSMC 的 Forward 块跨 (1)(2) 两节求和；只加 guarantor=TSMC 的行；亚利桑那按脚注认行。
2. 严格语法：第 3/4 项多一句、换一个工具、换一个担保人名、核准<在外、限额<核准和、两行亚利桑那，
   都必须抛，而不是悄悄少算。第 4 项块主体按清单认（口径坑 k）：清单外而名字像 TSMC 的抛，
   其它清单外主体不计入但打 ⚠；(1) 节不是恰好 1 块 'TSMC' 的抛。TestBlockEntityList 把 SUBSIDIARY_ENTITIES
   换成虚构夹具清单、夹具里的子公司块主体也换成虚构名 —— 照口径坑 k 往真清单登记子公司，这里不会变红。
3. 写入：只追加、照抄行尾、幂等、失步自愈、重述抛异常且零字节写；表头调换 / 断月 / 已有行不同 /
   读后被改都抛；last_month 取两表较小值、fingerprint 随字节变；tmp 只落 cache/tsm_6k/。
4. 候选定位：第 13 天前只看 reportDate 等于月末的件；第 14 天起放宽且限量；
   已认到月报时不为无关件多打一个请求，但 6-K/A 照下（2020-04-14 前例），同月取 6-K/A。
5. 护栏：SEC 封禁页 / 短页 / 缺 "filings" 必抛；MOPS 取不到只告警，核准 / 限额对不上、
   版式认不出、页内不自洽才抛。
6. TestReplayCached：真缓存里 ≥2023-03 的月报逐月严格解析，与仓库两张表逐格相等。

━━ 夹具 ━━
2026-08（0001046179-26-000658）、2024-08、2023-03、2021-08 的第 3/4 项是从真件压平后摘下的片段；
重述体检用的 2026-05..07 三份是按同一版式合成的（数值取自 series 里的真行）。
6-K/A 用例照 2020-04-14 前例（0001564590-20-016539，reportDate 沿用原件）按同一版式合成。
MOPS 页是 115/08 实拉页的表格部分。
"""

import ast
import contextlib
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import tsm_6k as T     # noqa: E402

REAL_CACHE = os.environ.get('TSM6K_CACHE') or os.path.join(ROOT, 'cache')
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
          'August', 'September', 'October', 'November', 'December']


def pre(mon, year):
    return (f'TSMC {mon} {year} Revenue Report HSINCHU, Taiwan, R.O.C. - TSMC (TWSE: 2330, NYSE: TSM) '
            'Taiwan Semiconductor Manufacturing Company Limited This is to report the changes or status of '
            '1) revenue, 2) funds lent to other parties, 3) endorsements and guarantees, and 4) financial '
            f'derivative transactions for {mon} {year} (“Current Month”). Note: “Outstanding” herein means '
            'the outstanding balance at the end of Current Month; and “Cumulative” herein represents the '
            'accumulated amounts from the beginning of this year till the end of Current Month. '
            '1. Revenue (in NT$ thousands) Period Items 2026 2025 Net Revenue 514,805,337 335,771,691 '
            '2. Funds lent to other parties (in NT$ thousands) Lending Company Limit of lending Amount '
            'approved by the Board of Directors Outstanding amount TSMC Development* 34,352,432 3,797,160 '
            '2,847,870 * The borrower is TSMC Washington, a wholly-owned subsidiary of TSMC. ')


FOOT = ('* The guarantee was provided to TSMC North America, a wholly-owned subsidiary of TSMC. '
        '** The guarantee was provided to TSMC Global, a wholly-owned subsidiary of TSMC. '
        '*** The guarantee was provided to TSMC Arizona, a wholly-owned subsidiary of TSMC. ')
S3_HEAD = ('3. Endorsements and guarantees (in NT$ thousands) Guarantor Limit of guarantee Amount '
           'approved by the Board of Directors Outstanding amount ')

# ── 2026-08（000658，filed 2026-09-10）真件片段 ─────────────────────────────
S3_2026_08 = (S3_HEAD + 'TSMC* 2,573,007,334 2,633,118 2,633,118 TSMC** 170,872,200 170,872,200 '
              'TSMC*** 483,851,076 346,948,663 ' + FOOT)
S4_2026_08 = (
    '4. Financial derivative transactions (in NT$ thousands) (1) Derivatives not applying hedge accounting. '
    '‧TSMC Forward Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional Amount '
    '192,798,341 Mark to Market of Outstanding Contracts 1,582,051 Cumulative Unrealized Profit/Loss 4,597,248 '
    'Expired Contracts Cumulative Notional Amount 1,251,988,723 Cumulative Realized Profit/Loss (7,563,234) '
    'Equity price linked product (Y/N) N '
    '‧TSMC China Forward Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional '
    'Amount 893,620 Mark to Market of Outstanding Contracts 5 Cumulative Unrealized Profit/Loss (16,567) '
    'Expired Contracts Cumulative Notional Amount 10,874,743 Cumulative Realized Profit/Loss 33,478 '
    'Equity price linked product (Y/N) N '
    '‧TSMC Nanjing Forward Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional '
    'Amount 2,265,965 Mark to Market of Outstanding Contracts (26) Cumulative Unrealized Profit/Loss (23,851) '
    'Expired Contracts Cumulative Notional Amount 27,028,623 Cumulative Realized Profit/Loss 54,191 '
    'Equity price linked product (Y/N) N '
    '‧Japan Advanced Semiconductor Mfg., Inc. Forward Margin Payment - Premium Income (Expense) - Existing '
    'Contracts Outstanding Notional Amount - Mark to Market of Outstanding Contracts - Cumulative Unrealized '
    'Profit/Loss (4,241) Expired Contracts Cumulative Notional Amount 2,767,287 Cumulative Realized '
    'Profit/Loss 20,888 Equity price linked product (Y/N) N '
    '(2) Derivatives applying hedge accounting. '
    '‧TSMC Global Future Margin Payment (16,201) Premium Income (Expense) - Existing Contracts Outstanding '
    'Notional Amount 253,144 Mark to Market of Outstanding Contracts 1,467 Cumulative Unrealized Profit/Loss '
    '2,347 Expired Contracts Cumulative Notional Amount 9,818,823 Cumulative Realized Profit/Loss 22,175 '
    'Equity price linked product (Y/N) N')
DOC_2026_08 = pre('August', 2026) + S3_2026_08 + S4_2026_08

# ── 2024-08（filed 2024-09-10）第 3 项：含子公司担保人 TSMC Japan Ltd. ───────────────
S3_2024_08 = (S3_HEAD + 'TSMC* 1,516,561,150 2,659,497 2,659,497 TSMC** 239,700,000 239,700,000 '
              'TSMC*** 384,556,143 256,716,128 TSMC Japan Ltd.**** 356,414 291,060 291,060 ' + FOOT
              + '**** The guarantee was provided to TSMC Design Technology Japan, a wholly-owned subsidiary of TSMC. ')
DOC_2024_08 = pre('August', 2024) + S3_2024_08 + S4_2026_08

# ── 2023-03（filed 2023-04-10）第 4 项：TSMC 的 Forward 块 (1)(2) 各一块 ─────────────────
S3_2023_03 = (S3_HEAD + 'TSMC* 736,413,299 2,531,515 2,531,515 TSMC** 228,165,000 228,165,000 '
              'TSMC*** 366,050,281 244,362,267 TSMC Japan Ltd.**** 331,204 302,940 302,940 ' + FOOT
              + '**** The guarantee was provided to TSMC Design Technology Japan, a wholly-owned subsidiary of TSMC. ')
S4_2023_03 = (
    '4. Financial derivative transactions (in NT$ thousands) (1) Derivatives not applying hedge accounting. '
    '‧TSMC Forward Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional Amount '
    '114,372,932 Mark to Market of Outstanding Contracts 110,516 Cumulative Unrealized Profit/Loss (424,271) '
    'Expired Contracts Cumulative Notional Amount 185,175,211 Cumulative Realized Profit/Loss 1,486,570 '
    'Equity price linked product (Y/N) N '
    '‧TSMC China Forward Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional '
    'Amount 20,811,446 Mark to Market of Outstanding Contracts 147,634 Cumulative Unrealized Profit/Loss '
    '(235,066) Expired Contracts Cumulative Notional Amount 50,185,972 Cumulative Realized Profit/Loss 342,528 '
    'Equity price linked product (Y/N) N '
    '(2) Derivatives applying hedge accounting. '
    '‧TSMC Forward Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional Amount '
    '230,810 Mark to Market of Outstanding Contracts (1,179) Cumulative Unrealized Profit/Loss (1,179) '
    'Expired Contracts Cumulative Notional Amount - Cumulative Realized Profit/Loss 39,989 '
    'Equity price linked product (Y/N) N '
    '‧TSMC Global Future Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional '
    'Amount 1,560,649 Mark to Market of Outstanding Contracts (37,929) Cumulative Unrealized Profit/Loss '
    '(39,432) Expired Contracts Cumulative Notional Amount 2,631,503 Cumulative Realized Profit/Loss 20,623 '
    'Equity price linked product (Y/N) N')
DOC_2023_03 = pre('March', 2023) + S3_2023_03 + S4_2023_03

# ── 2021-08（filed 2021-09-10）旧版式：没有核准栏 ─────────────────────────────
DOC_2021_08 = (
    'This is to report the changes or status of 1) revenue, 2) funds lent to other parties, 3) endorsements '
    'and guarantees, and 4) financial derivative transactions for the period of August 2021. '
    '3. Endorsements and guarantees (in NT$ thousands)： Guarantor Limit of guarantee Amount Bal. as of '
    'period end TSMC* 497,946,450 2,310,417 TSMC** 180,472,500 TSMC*** 900,141 ' + FOOT
    + '4. Financial derivative transactions (in NT$ thousands) (1) Derivatives not under hedge accounting. '
    '‧TSMC Forward Margin Payment - Premium Income (Expense) - Outstanding Contracts Notional Amount '
    '165,892,312 Mark to Market Profit/Loss (1,285,939) Unrealized Profit/Loss (3,317,467) Expired Contracts '
    'Notional Amount 521,462,896 Realized Profit/Loss (1,551,481) Equity price linked product (Y/N) N')

# ── MOPS ajax_t05st11 115/08 实拉页的表格部分（补足长度，flat 会吃掉 script）──────────────
MOPS_115_08 = (
    "<html><head><title>公開資訊觀測站</title></head><body><div id='div01'>"
    "<table class='noBorder'><tr><TD align='center'>民國115年08月</TD></tr>"
    "<tr><TD align='right'>單位：新台幣仟元</TD></tr></table>"
    "<TABLE class='hasBorder'><TR><TH>是否有資金貸放餘額</Th><TH>本月</Th><TH>上月</Th><TH>最高限額</Th></TR>"
    "<tr><TD>本公司\n<font color='red'>無</font>\n資金貸放餘額</TD><TD>&nbsp;     0</TD><TD>&nbsp;     0</TD>"
    "<TD>&nbsp;     0</TD></TR><tr><TD>各子公司\n<font color='red'>有</font>\n資金貸放餘額</TD>"
    "<TD>&nbsp; 3,797,160</TD><TD>&nbsp; 3,896,160</TD><TD>&nbsp; 168,729,108</TD></TR></TABLE>"
    "<TABLE class='hasBorder'><TR><TH nowrap>是否有背書保證資訊</Th><TH nowrap>本月增減金額</Th>\n"
    "<TH nowrap>至本月份累計餘額</Th>\n<TH nowrap>最高額度</Th>\n</TR><tr>"
    "<TD nowrap>本公司\n<font color='red'>有</font>\n背書保證資訊</TD>\n<TD>&nbsp;    -17,138,673</TD>"
    "<TD>&nbsp;    657,356,394</TD><TD>&nbsp;  2,573,007,334</TD></tr><TR>"
    "<TD nowrap>各子公司\n<font color='red'>無</font>\n背書保證資訊</TD>\n<TD>&nbsp; 0</TD><TD>&nbsp; 0</TD>"
    "<TD>&nbsp; 0</TD></tr></TABLE><TABLE class='hasBorder'><TR><TH colspan=2>本公司與子公司間\n"
    "<font color='red'>有</font>\n背書保證資訊</Th></tr><tr><TD>本公司對子公司背書保證累計餘額</TD>\n"
    "<TD>&nbsp;    657,356,394</TD></tr><TR><TD>子公司對本公司背書保證累計餘額</TD>\n<TD>&nbsp; 0</TD></TR>"
    "</TABLE></div></body><script>" + '/* padding */ ' * 400 + '</script></html>').encode('utf-8')
MOPS_NONE = ("<html><body><div id='div01'><center><H3>資料庫中查無需求資料 </div></body>"
             + ' ' * 2300 + '</html>').encode('utf-8')
MOPS_OVERRUN = '<html><body>Overrun - 查詢過於頻繁,請稍後再試!!</body></html>'.encode('utf-8')

# ── 写入测试用的 series 行（真值）与候选行 ─────────────────────────────────────
DER_ROWS = ['2026-05,211234354,722513.0', '2026-06,201319113,-2393995.0', '2026-07,230720646,-2645507.0']
GUA_ROWS = ['2026-05,641966939,514588269.0,470040786.0,342662116.0',
            '2026-06,653493885,524230212.0,478480683.0,349217010.0',
            '2026-07,674495067,534023318.0,496466098.0,355994349.0']
LINE_DER_08 = '2026-08,192798341,1582051.0'
LINE_GUA_08 = '2026-08,657356394,520453981.0,483851076.0,346948663.0'


def row(fd, acc, doc, size, rd, form='6-K'):
    return dict(fd=fd, form=form, acc=acc, doc=doc, size=size, rd=rd)


REV = {'2026-05': row('2026-06-10', '0001046179-26-000367', 'tsm-revenue20260610.htm', 99533, '2026-05-31'),
       '2026-06': row('2026-07-13', '0001046179-26-000447', 'tsm-revenue20260713.htm', 99496, '2026-06-30'),
       '2026-07': row('2026-08-10', '0001046179-26-000471', 'tsm-revenue20260810.htm', 100125, '2026-07-31'),
       '2026-08': row('2026-09-10', '0001046179-26-000658', 'tsm-revenue20260910.htm', 100154, '2026-08-31')}
MONTHEND_07 = row('2026-08-25', '0001046179-26-000545', 'tsm-monthend6kx20260825.htm', 33289, '2026-07-31')
DIVIDEND = row('2026-09-01', '0001046179-26-000552', 'tsm-dividendadjustmentx202.htm', 17441, '2026-09-01')


def url_of(r):
    return T.DOC_URL % (r['acc'].replace('-', ''), r['doc'])


def html(fl):
    return ('<html><body><p>' + fl + '</p>' + ' ' * 3000 + '</body></html>').encode('utf-8')


def filler(n):
    return ('<html><body>' + 'lorem ' * (n // 6) + '</body></html>').encode('utf-8')


def fmt(v):
    return f'({abs(v):,})' if v < 0 else f'{v:,}'


def blk(head, notional, mtm):
    return (f'‧{head} Margin Payment - Premium Income (Expense) - Existing Contracts Outstanding Notional '
            f'Amount {notional} Mark to Market of Outstanding Contracts {mtm} Cumulative Unrealized Profit/Loss - '
            'Expired Contracts Cumulative Notional Amount - Cumulative Realized Profit/Loss - '
            'Equity price linked product (Y/N) N ')


def synth(der_line, gua_line):
    """按真版式合成一份月报：两行 CSV 的 6 格 → 第 3/4 项。"""
    m, notional, mtm = der_line.split(',')
    _, appr, out, az_a, az_o = [x.split('.')[0] for x in gua_line.split(',')]
    appr, out, az_a, az_o, notional, mtm = map(int, (appr, out, az_a, az_o, notional, float(mtm)))
    x = 2_700_000
    s3 = (S3_HEAD + f'TSMC* {fmt(3_000_000_000)} {fmt(x)} {fmt(x)} TSMC** {fmt(appr - az_a - x)} '
          f'{fmt(out - az_o - x)} TSMC*** {fmt(az_a)} {fmt(az_o)} ' + FOOT)
    s4 = ('4. Financial derivative transactions (in NT$ thousands) (1) Derivatives not applying hedge accounting. '
          + blk('TSMC Forward', fmt(notional), fmt(mtm)) + '(2) Derivatives applying hedge accounting. '
          + blk('TSMC Global Future', '253,144', '1,467'))
    return pre(MONTHS[int(m[5:]) - 1], m[:4]) + s3 + s4


def subs_json(rows, with_filings=True):
    r = {k: [] for k in ('accessionNumber', 'filingDate', 'reportDate', 'form', 'primaryDocument', 'size')}
    for x in rows:
        r['accessionNumber'].append(x['acc'])
        r['filingDate'].append(x['fd'])
        r['reportDate'].append(x['rd'])
        r['form'].append(x['form'])
        r['primaryDocument'].append(x['doc'])
        r['size'].append(x['size'])
    d = {'cik': '0001046179', 'name': 'TAIWAN SEMICONDUCTOR MANUFACTURING CO LTD', 'description': 'x' * 60000}
    d['filings' if with_filings else 'other'] = {'recent': r, 'files': []}
    return json.dumps(d).encode()


class Stub:
    """opener 测试缝：opener(url, data, headers) → bytes；没登记的 URL 抛 OSError。"""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.asked = []

    def __call__(self, url, data, headers):
        self.asked.append(url)
        v = self.routes.get(url)
        if v is None:
            raise OSError(f'404 {url}')
        if isinstance(v, Exception):
            raise v
        return v


def quiet(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = fn(*a, **kw)
    return out, buf.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._sleep = T._sleep
        T._sleep = lambda s: None
        T._SUBS_MEMO.clear()

    def tearDown(self):
        T._sleep = self._sleep


class Env:
    """临时 series/ + cache/tsm_6k/，重述体检的 2026-05..07 三份合成月报先放进缓存。"""

    def __init__(self, der=DER_ROWS, gua=GUA_ROWS, crlf=False):
        self.root = tempfile.mkdtemp(prefix='tsm6k_')
        self.series = os.path.join(self.root, 'series')
        self.cache = os.path.join(self.root, 'cache')
        os.makedirs(self.series)
        os.makedirs(os.path.join(self.cache, T.CACHE_SUB))
        nl = '\r\n' if crlf else '\n'
        for name, cols, lines in ((T.DER_CSV, T.DER_COLS, der), (T.GUA_CSV, T.GUA_COLS, gua)):
            with open(os.path.join(self.series, name), 'w', newline='', encoding='utf-8') as f:
                f.write(nl.join([','.join(cols)] + list(lines)) + nl)
        for m, d, g in zip(('2026-05', '2026-06', '2026-07'), DER_ROWS, GUA_ROWS):
            with open(T._cache_path(self.cache, REV[m]), 'wb') as f:
                f.write(html(synth(d, g)))

    def stub(self, rows=None, doc_08=True):
        rows = rows if rows is not None else [REV['2026-05'], REV['2026-06'], MONTHEND_07, REV['2026-07'],
                                              DIVIDEND, REV['2026-08']]
        # 第 14 天起候选放宽，缺月报时会去看 9 月初那份股利调整件：照真件大小给一份无关正文
        routes = {T.SUB_URL: subs_json(rows), T.MOPS_T05ST11: MOPS_115_08,
                  url_of(DIVIDEND): filler(17441)}
        if doc_08:
            routes[url_of(REV['2026-08'])] = html(DOC_2026_08)
        return Stub(routes)

    def raw(self):
        return tuple(open(os.path.join(self.series, n), 'rb').read() for n in (T.DER_CSV, T.GUA_CSV))

    def tmp_files(self):
        return [os.path.join(dp, f) for dp, _, fs in os.walk(self.root) for f in fs if f.endswith('.tmp')]

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


TODAY = datetime.date(2026, 9, 14)


# ══════════════════════════════════════════════════════════════════════════
# 1–7：解析
# ══════════════════════════════════════════════════════════════════════════
class TestParse2026_08(Base):
    def test_six_cells_and_lines(self):
        p = quiet(T.parse, DOC_2026_08)[0]
        g, d = p['guar'], p['deriv']
        self.assertEqual(p['month'], '2026-08')
        self.assertEqual((g['approved_total_k'], g['outstanding_total_k']), (657356394, 520453981))
        self.assertEqual((g['arizona_approved_k'], g['arizona_outstanding_k']), (483851076, 346948663))
        self.assertEqual(g['limit_k'], 2573007334)
        self.assertEqual((d['open_notional_ntd_k'], d['open_fair_value_ntd_k']), (192798341, 1582051))
        self.assertEqual(T.rows_for(p), (LINE_DER_08, LINE_GUA_08))

    def test_subsidiary_and_future_blocks_not_counted(self):
        blocks = quiet(T.parse, DOC_2026_08)[0]['deriv']['blocks']
        self.assertEqual([(b['entity'], b['instrument']) for b in blocks if b['counted']], [('TSMC', 'Forward')])
        self.assertEqual({b['kind'] for b in blocks if not b['counted']}, {'known'})
        self.assertEqual({(b['entity'], b['instrument']) for b in blocks if not b['counted']},
                         {('TSMC China', 'Forward'), ('TSMC Nanjing', 'Forward'),
                          ('Japan Advanced Semiconductor Mfg., Inc.', 'Forward'), ('TSMC Global', 'Future')})


class TestTwoParentForwardBlocks(Base):
    def test_both_sections_summed(self):
        d = quiet(T.parse, DOC_2023_03)[0]['deriv']
        self.assertEqual((d['open_notional_ntd_k'], d['open_fair_value_ntd_k']), (114603742, 109337))
        first = [b for b in d['blocks'] if b['counted']][0]
        self.assertNotEqual(first['notional'], d['open_notional_ntd_k'], '「只取第一块」会得到 114372932')


class TestSubsidiaryGuarantorExcluded(Base):
    def test_japan_row_not_in_totals(self):
        p, out = quiet(T.parse, DOC_2024_08)
        g = p['guar']
        self.assertEqual(g['approved_total_k'], 626915640)          # = CSV 2024-08 = MOPS 113/08
        self.assertEqual(sum(r['approved'] for r in g['parties']), 627206700)
        self.assertIn('TSMC Japan Ltd.', out)


class TestArizonaByFootnote(Base):
    def test_stars_swapped(self):
        s3 = (S3_HEAD + 'TSMC* 2,573,007,334 2,633,118 2,633,118 TSMC*** 170,872,200 170,872,200 '
              'TSMC** 483,851,076 346,948,663 '
              '* The guarantee was provided to TSMC North America, a wholly-owned subsidiary of TSMC. '
              '** The guarantee was provided to TSMC Arizona, a wholly-owned subsidiary of TSMC. '
              '*** The guarantee was provided to TSMC Global, a wholly-owned subsidiary of TSMC. ')
        g = quiet(T.parse, pre('August', 2026) + s3 + S4_2026_08)[0]['guar']
        self.assertEqual((g['arizona_approved_k'], g['arizona_outstanding_k']), (483851076, 346948663))
        self.assertEqual(g['approved_total_k'], 657356394)


class TestStrictGrammar(Base):
    def bad(self, doc, needle=None):
        with self.assertRaises(T.Tsm6kError) as cm:
            quiet(T.parse, doc)
        if needle:
            self.assertIn(needle, str(cm.exception))

    def test_unknown_sentence_in_item_3(self):
        s3 = S3_2026_08.replace('* The guarantee was provided to TSMC North',
                                'Amounts above are unaudited. * The guarantee was provided to TSMC North')
        self.bad(pre('August', 2026) + s3 + S4_2026_08, '认不出的文字')

    def test_tsmc_swap_block(self):
        s4 = S4_2026_08 + ' ' + blk('TSMC Swap', '1,000', '10').strip()
        self.bad(pre('August', 2026) + S3_2026_08 + s4, 'Swap')

    def test_multiword_instrument(self):
        s4 = S4_2026_08 + ' ' + blk('TSMC Cross Currency Swap', '1,000', '10').strip()
        self.bad(pre('August', 2026) + S3_2026_08 + s4, '工具类词汇')

    def test_unknown_guarantor(self):
        self.bad(pre('August', 2024) + S3_2024_08.replace('TSMC Japan Ltd.****', 'Sony Corp.****') + S4_2026_08,
                 'Sony Corp.')

    def test_none(self):
        self.bad(pre('August', 2026) + '3. Endorsements and guarantees (in NT$ thousands) None. ' + S4_2026_08,
                 '口径坑 g')

    def test_forward_notional_all_dash(self):
        s4 = S4_2026_08.replace('Outstanding Notional Amount 192,798,341', 'Outstanding Notional Amount -')
        self.bad(pre('August', 2026) + S3_2026_08 + s4, '合计为 0')

    def test_star_without_footnote(self):
        s3 = S3_2026_08.replace('*** The guarantee was provided to TSMC Arizona, a wholly-owned subsidiary of TSMC. ',
                                '')
        self.bad(pre('August', 2026) + s3 + S4_2026_08, '对不上')

    def test_approved_below_outstanding(self):
        s3 = S3_2026_08.replace('TSMC** 170,872,200 170,872,200', 'TSMC** 170,872,200 170,872,201')
        self.assertNotEqual(s3, S3_2026_08)
        self.bad(pre('August', 2026) + s3 + S4_2026_08, '核准 ≥ 在外')

    def test_limit_below_approved_sum(self):
        s3 = S3_2026_08.replace('TSMC* 2,573,007,334 ', 'TSMC* 657,356,393 ')        # 核准和 657,356,394
        self.assertNotEqual(s3, S3_2026_08)
        self.bad(pre('August', 2026) + s3 + S4_2026_08, '首行限额')

    def test_two_arizona_rows(self):
        s3 = S3_2026_08.replace('** The guarantee was provided to TSMC Global,',
                                '** The guarantee was provided to TSMC Arizona,')
        self.assertNotEqual(s3, S3_2026_08)
        self.bad(pre('August', 2026) + s3 + S4_2026_08, '有 2 行')


class TestBlockEntityList(Base):
    """口径坑 k：第 4 项块主体按清单认 —— 'TSMC' 计入；清单内不计入；清单外像 TSMC 的抛；其它打 ⚠；
    (1) 节恰好 1 块 'TSMC'，否则抛。

    清单换成虚构夹具 FIX_SUBS（setUp 里 mock，addCleanup 还原），真件片段里的子公司块主体也换成虚构名（fx）：
    照口径坑 k 往真 SUBSIDIARY_ENTITIES 登记 'TSMC Arizona' / 'WaferTech' 之类确认过的子公司，这里照样绿。
    真清单里那 4 个名字由 TestParse2026_08 与 TestReplayCached 按真件钉住。"""
    H1 = '(1) Derivatives not applying hedge accounting. '
    H2 = '(2) Derivatives applying hedge accounting. '
    FIX = {'TSMC China': 'TSMC Fixture Alpha', 'TSMC Nanjing': 'TSMC Fixture Beta',
           'Japan Advanced Semiconductor Mfg., Inc.': 'Fixture Gamma Mfg., Inc.',
           'TSMC Global': 'TSMC Fixture Delta'}
    FIX_SUBS = frozenset(FIX.values())
    UNLISTED_TSMC_LIKE = 'TSMC Fixture Omega'          # 清单外、名字像 TSMC → 抛
    UNLISTED_OTHER = 'Fixture Wafer Co.'               # 清单外、名字不像 TSMC → 不计入、打 ⚠

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(T, 'SUBSIDIARY_ENTITIES', self.FIX_SUBS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fx(self, doc):
        """第 4 项块标题里的真子公司主体换成虚构名（第 3 项脚注里的公司名不动）。"""
        for real, fake in self.FIX.items():
            self.assertLessEqual(doc.count('‧' + real + ' '), 1)
            doc = doc.replace('‧' + real + ' ', '‧' + fake + ' ')
        return doc

    def ren(self, head, new):
        """2023-03（两块母公司的月份）某一节那块 TSMC Forward 改印主体名。"""
        doc, old = self.fx(DOC_2023_03), head + '‧TSMC Forward '
        self.assertEqual(doc.count(old), 1)
        return doc.replace(old, head + f'‧{new} Forward ')

    def ren2(self, new):
        """(2) 节改名（旧写法会按子公司静默不计入）。"""
        return self.ren(self.H2, new)

    def raises(self, doc, needle):
        with self.assertRaises(T.Tsm6kError) as cm:
            quiet(T.parse, doc)
        self.assertIn(needle, str(cm.exception))
        self.assertIn('口径坑 k', str(cm.exception))

    def test_parent_block_renamed_in_section_2(self):
        # 旧写法：名目 114,372,932（少 230,810）照样入库
        self.raises(self.ren2('TSMC Ltd.'), "'TSMC Ltd.'")

    def test_unlisted_tsmc_like_forward(self):
        s4 = S4_2026_08 + ' ' + blk(self.UNLISTED_TSMC_LIKE + ' Forward', '1,000', '10').strip()
        self.raises(self.fx(pre('August', 2026) + S3_2026_08 + s4), repr(self.UNLISTED_TSMC_LIKE))

    def test_tsmc_like_names_case_insensitive(self):
        for name in ('tsmc', 'Taiwan Semiconductor Manufacturing Co., Ltd.', 'TAIWAN SEMICONDUCTOR MFG. CO.'):
            with self.subTest(name=name):
                self.raises(self.ren2(name), repr(name))

    def test_unlisted_other_name_warns_not_counted(self):
        name = self.UNLISTED_OTHER
        s4 = S4_2026_08 + ' ' + blk(name + ' Forward', '1,000', '10').strip()
        p, out = quiet(T.parse, self.fx(pre('August', 2026) + S3_2026_08 + s4), verbose=False)
        d = p['deriv']
        self.assertEqual(d['open_notional_ntd_k'], 192798341)
        self.assertEqual([(b['kind'], b['counted']) for b in d['blocks'] if b['entity'] == name],
                         [('unlisted', False)])
        warns = [ln for ln in out.splitlines() if '⚠' in ln]
        self.assertEqual(len(warns), 1, 'verbose=False（重述体检 / audit）也必须看得见')
        self.assertIn(repr(name), warns[0])

    def test_known_subsidiaries_one_info_line(self):
        doc = self.fx(DOC_2026_08)
        out = quiet(T.parse, doc)[1]
        lines = [ln for ln in out.splitlines() if '按清单不计入' in ln]
        self.assertEqual(len(lines), 1)
        for e in sorted(self.FIX_SUBS):
            self.assertIn(e, lines[0])
        self.assertNotIn('⚠', out)
        self.assertEqual(quiet(T.parse, doc, verbose=False)[1], '')

    def test_section_1_parent_renamed_non_tsmc_name(self):
        # 两块母公司的月份：没有 (1) 节不变式时 'The Company' 只打 ⚠、按子公司不计入，名目写成 230,810（真值 114,603,742）
        self.raises(self.ren(self.H1, 'The Company'), '(1) 节主体恰好是 TSMC 的块有 0 个')

    def test_section_1_two_parent_blocks(self):
        doc, old = self.fx(DOC_2026_08), self.H1 + '‧TSMC Forward '
        self.assertEqual(doc.count(old), 1)
        doc = doc.replace(old, self.H1 + blk('TSMC Forward', '1,000', '10') + '‧TSMC Forward ')
        self.raises(doc, '(1) 节主体恰好是 TSMC 的块有 2 个')


class TestOldFormatRejected(Base):
    def test_2021_08(self):
        with self.assertRaises(T.Tsm6kError) as cm:
            T.parse(DOC_2021_08)
        self.assertIn('2023-03', str(cm.exception))


class TestNumbers(Base):
    def test_values(self):
        self.assertEqual(T.num('(7,563,234)'), -7563234)
        self.assertEqual(T.num('-'), 0)
        self.assertEqual(T.num('1,582,051'), 1582051)
        with self.assertRaises(T.Tsm6kError):
            T.num('1,58')

    def test_split_thousands_repaired(self):
        s4 = S4_2026_08.replace('Amount 2,265,965 ', 'Amount 2 ,265,965 ')       # 2025-09 真件的形状
        d = quiet(T.parse, pre('August', 2026) + S3_2026_08 + s4)[0]['deriv']
        self.assertIn(2265965, [b['notional'] for b in d['blocks']])


# ══════════════════════════════════════════════════════════════════════════
# 8–10：候选、HTTP 护栏、MOPS 对账
# ══════════════════════════════════════════════════════════════════════════
class TestCandidates(Base):
    def setUp(self):
        super().setUp()
        self.env = Env()

    def tearDown(self):
        self.env.close()
        super().tearDown()

    def test_before_day_14_only_report_date_rows(self):
        subs = [REV['2026-07'], MONTHEND_07, REV['2026-08'], DIVIDEND]
        accs = [r['acc'] for r in T.candidates('2026-08', subs, datetime.date(2026, 9, 13))]
        self.assertEqual(accs, [REV['2026-08']['acc']])

    def test_day_13_never_downloads_dividend(self):
        st = self.env.stub(rows=[REV['2026-07'], MONTHEND_07, DIVIDEND], doc_08=False)
        subs = T.submissions(st)
        got = T.find('2026-08', self.env.cache, datetime.date(2026, 9, 13), st, subs=subs)
        self.assertIsNone(got)
        self.assertNotIn(url_of(DIVIDEND), st.asked)

    def test_day_14_widens_capped_and_skips_big(self):
        others = [DIVIDEND] + [row(f'2026-09-{d:02d}', f'0001046179-26-0006{d:02d}', f'misc{d}.htm', 30000,
                                   f'2026-09-{d:02d}') for d in (2, 3, 4, 5, 6)]
        big = row('2026-09-07', '0001046179-26-000700', 'tsm-fsx.htm', 2_000_000, '2026-06-30')
        st = Stub({url_of(r): filler(17441 if r is DIVIDEND else 30000) for r in others})
        got, checked, skipped = T._scan('2026-08', self.env.cache, TODAY, st, subs=others + [big])
        self.assertIsNone(got)
        self.assertEqual(checked, T.WIDEN_MAX_DOCS)
        self.assertEqual(skipped, len(others) - T.WIDEN_MAX_DOCS)
        self.assertNotIn(url_of(big), st.asked)
        self.assertIn(url_of(DIVIDEND), st.asked)          # 17,441 B 的合法小件照常下、不抛

    def test_widened_segment_finds_misstamped_report(self):
        bad_rd = dict(REV['2026-08'], rd='2026-09-10')
        st = Stub({url_of(bad_rd): html(DOC_2026_08)})
        self.assertIsNone(T.find('2026-08', self.env.cache, datetime.date(2026, 9, 13), st, subs=[bad_rd]))
        r, p = quiet(T.find, '2026-08', self.env.cache, TODAY, st, subs=[bad_rd])[0]
        self.assertEqual((r['acc'], p['month']), (bad_rd['acc'], '2026-08'))

    def test_cached_month_is_zero_request(self):
        st = Stub()
        r, p = quiet(T.find, '2026-07', self.env.cache, TODAY, st, subs=[REV['2026-07'], MONTHEND_07])[0]
        self.assertEqual(r['acc'], REV['2026-07']['acc'])
        self.assertEqual(st.asked, [], '已认到月报时不该为同 reportDate 的无关件多打请求')

    def test_same_month_6ka_preferred(self):
        amended = synth('2026-08,192798000,1582051.0', LINE_GUA_08)
        # 同一天且 accession 更小（只按 filingDate / accession 取就会选错）；以及晚两天的 6-K/A
        for ka in (dict(REV['2026-08'], acc='0001046179-26-000657', doc='tsm-20260910x6ka.htm', form='6-K/A'),
                   dict(REV['2026-08'], acc='0001046179-26-000660', doc='tsm-20260912x6ka.htm', fd='2026-09-12',
                        form='6-K/A')):
            with self.subTest(acc=ka['acc']):
                st = Stub({url_of(REV['2026-08']): html(DOC_2026_08), url_of(ka): html(amended)})
                (r, p), out = quiet(T.find, '2026-08', self.env.cache, TODAY, st, subs=[REV['2026-08'], ka])
                self.assertEqual((r['form'], r['acc']), ('6-K/A', ka['acc']))
                self.assertEqual(p['deriv']['open_notional_ntd_k'], 192798000)
                self.assertIn('6-K/A 优先', out)

    def test_widened_6ka_still_read_after_hit(self):
        # reportDate 没沿用原件的更正件落在第二段：已认到原件也要读它；普通件（两段都有）照旧不下。
        # early 是申报日早于 6-K/A 的第二段普通件（真实顺序：普通件在前、更正件在后）——
        # 把 _scan 里第二段普通件的 continue 改成 break，就读不到后面的 6-K/A、静默选中未更正的原件，这条必须红。
        ka = row('2026-08-20', '0001046179-26-000540', 'tsm-20260820x6ka.htm', 101000, '2026-08-20', form='6-K/A')
        early = row('2026-08-19', '0001046179-26-000538', 'tsm-misc20260819.htm', 30000, '2026-08-19')
        plain = row('2026-08-21', '0001046179-26-000542', 'tsm-misc20260821.htm', 30000, '2026-08-21')
        st = Stub({url_of(ka): html(synth('2026-07,230720000,-2645507.0', GUA_ROWS[2])),
                   url_of(early): filler(30000), url_of(plain): filler(30000)})
        subs = [REV['2026-07'], MONTHEND_07, early, ka, plain]
        self.assertEqual([(r['seg'], r['acc']) for r in T.candidates('2026-07', subs, TODAY)][2:],
                         [(2, early['acc']), (2, ka['acc']), (2, plain['acc'])])
        (r, p), _ = quiet(T.find, '2026-07', self.env.cache, TODAY, st, subs=subs)
        self.assertEqual((r['form'], r['acc']), ('6-K/A', ka['acc']))
        self.assertEqual(p['deriv']['open_notional_ntd_k'], 230720000)
        self.assertEqual(st.asked, [url_of(ka)])


class TestHttpGuards(Base):
    def test_block_page(self):
        body = b'<html>Your Request Originated from an Undeclared Automated Tool</html>' + b' ' * 60000
        with self.assertRaises(T.Tsm6kError) as cm:
            T.submissions(Stub({T.SUB_URL: body}))
        self.assertIn('封禁', str(cm.exception))

    def test_short_body(self):
        with self.assertRaises(T.Tsm6kError) as cm:
            T.submissions(Stub({T.SUB_URL: b'{"filings": {}}'}))
        self.assertIn('字节', str(cm.exception))

    def test_missing_filings(self):
        with self.assertRaises(T.Tsm6kError) as cm:
            T.submissions(Stub({T.SUB_URL: subs_json([REV['2026-08']], with_filings=False)}))
        self.assertIn('"filings"', str(cm.exception))


class TestMopsCrosscheck(Base):
    def setUp(self):
        super().setUp()
        self.p = quiet(T.parse, DOC_2026_08)[0]

    def test_pass(self):
        ok, out = quiet(T.mops_crosscheck, '2026-08', self.p, Stub({T.MOPS_T05ST11: MOPS_115_08}))
        self.assertTrue(ok)
        self.assertIn('对账通过', out)

    def test_approved_off_by_one_raises(self):
        self.p['guar']['approved_total_k'] += 1
        with self.assertRaises(T.Tsm6kError) as cm:
            T.mops_crosscheck('2026-08', self.p, Stub({T.MOPS_T05ST11: MOPS_115_08}))
        self.assertIn('657,356,394', str(cm.exception))

    def test_limit_mismatch_raises(self):
        self.p['guar']['limit_k'] += 1
        with self.assertRaises(T.Tsm6kError) as cm:
            T.mops_crosscheck('2026-08', self.p, Stub({T.MOPS_T05ST11: MOPS_115_08}))
        self.assertIn('最高額度 2,573,007,334', str(cm.exception))

    def test_layout_unrecognised_raises(self):
        pages = {'页上是别的月份': MOPS_115_08.replace('民國115年08月'.encode(), '民國115年07月'.encode()),
                 '认不出本公司那一行': MOPS_115_08.replace('至本月份累計餘額'.encode(), '累計餘額'.encode())}
        for why, page in pages.items():
            with self.subTest(why=why):
                self.assertNotEqual(page, MOPS_115_08)
                with self.assertRaises(T.Tsm6kError) as cm:
                    quiet(T.mops_crosscheck, '2026-08', self.p, Stub({T.MOPS_T05ST11: page}))
                self.assertIn('版式变了', str(cm.exception))

    def test_internally_inconsistent_raises(self):
        page = MOPS_115_08.replace('本公司對子公司背書保證累計餘額</TD>\n<TD>&nbsp;    657,356,394'.encode(),
                                   '本公司對子公司背書保證累計餘額</TD>\n<TD>&nbsp;    657,356,395'.encode())
        self.assertNotEqual(page, MOPS_115_08)
        with self.assertRaises(T.Tsm6kError) as cm:
            T.mops_crosscheck('2026-08', self.p, Stub({T.MOPS_T05ST11: page}))
        self.assertIn('内部不自洽', str(cm.exception))

    def test_none_page_only_warns(self):
        ok, out = quiet(T.mops_crosscheck, '2026-08', self.p, Stub({T.MOPS_T05ST11: MOPS_NONE}))
        self.assertFalse(ok)
        self.assertIn('护栏失效', out)

    def test_overrun_only_warns(self):
        ok, out = quiet(T.mops_crosscheck, '2026-08', self.p, Stub({T.MOPS_T05ST11: MOPS_OVERRUN}))
        self.assertFalse(ok)
        self.assertIn('Overrun', out)

    def test_network_error_only_warns(self):
        ok, out = quiet(T.mops_crosscheck, '2026-08', self.p, Stub())
        self.assertFalse(ok)
        self.assertIn('网络错', out)


# ══════════════════════════════════════════════════════════════════════════
# 11–13：写入
# ══════════════════════════════════════════════════════════════════════════
class TestAppendIdempotent(Base):
    def setUp(self):
        super().setUp()
        self.env = None

    def tearDown(self):
        if self.env:
            self.env.close()
        super().tearDown()

    def test_exact_lines_then_idempotent(self):
        self.env = e = Env()
        st = e.stub()
        added, out = quiet(T.update, e.series, e.cache, '2026-08', TODAY, st)
        self.assertEqual(added, ['2026-08'])
        der, gua = e.raw()
        self.assertTrue(der.endswith(('2026-07,230720646,-2645507.0\n' + LINE_DER_08 + '\n').encode()))
        self.assertTrue(gua.endswith((GUA_ROWS[-1] + '\n' + LINE_GUA_08 + '\n').encode()))
        self.assertIn('对账通过', out)
        self.assertNotIn(url_of(MONTHEND_07), st.asked, '重述体检命中缓存时不该下载同 reportDate 的无关件')
        self.assertEqual(e.tmp_files(), [])
        fp = T.fingerprint(e.series)
        st2 = e.stub()
        self.assertEqual(quiet(T.update, e.series, e.cache, '2026-08', TODAY, st2)[0], [])
        self.assertEqual(T.fingerprint(e.series), fp)
        self.assertEqual(st2.asked, [], '追平之后零请求')
        self.assertEqual(T.last_month(e.series), '2026-08')

    def test_crlf_copied(self):
        self.env = e = Env(crlf=True)
        quiet(T.update, e.series, e.cache, '2026-08', TODAY, e.stub())
        der, gua = e.raw()
        self.assertTrue(der.endswith((LINE_DER_08 + '\r\n').encode()))
        self.assertTrue(gua.endswith((LINE_GUA_08 + '\r\n').encode()))
        self.assertNotIn(b'\n2026-08', der.replace(b'\r\n', b'\r'))

    def test_only_lagging_table_appended(self):
        self.env = e = Env(der=DER_ROWS + [LINE_DER_08])
        der0, _ = e.raw()
        added = quiet(T.update, e.series, e.cache, '2026-08', TODAY, e.stub())[0]
        der, gua = e.raw()
        self.assertEqual(added, ['2026-08'])
        self.assertEqual(der, der0)
        self.assertTrue(gua.endswith((LINE_GUA_08 + '\n').encode()))

    def test_missing_6k_zero_write(self):
        self.env = e = Env()
        before = e.raw()
        rows = [REV['2026-05'], REV['2026-06'], MONTHEND_07, REV['2026-07'], DIVIDEND]
        added, out = quiet(T.update, e.series, e.cache, '2026-08', TODAY, e.stub(rows=rows, doc_08=False))
        self.assertEqual(added, [])
        self.assertEqual(e.raw(), before)
        self.assertIn('尚未出现', out)


class TestWriteGuards(Base):
    """读表 / 写盘护栏的最小反例：该抛的抛，且 series 一个字节不动。"""

    def setUp(self):
        super().setUp()
        self.env = None

    def tearDown(self):
        if self.env:
            self.env.close()
        super().tearDown()

    def rewrite(self, name, old, new):
        p = os.path.join(self.env.series, name)
        with open(p, 'rb') as f:
            raw = f.read()
        self.assertEqual(raw.count(old), 1)
        with open(p, 'wb') as f:
            f.write(raw.replace(old, new))

    def refused(self, needle):
        e = self.env
        before, st = e.raw(), e.stub()
        with self.assertRaises(T.Tsm6kError) as cm:
            quiet(T.update, e.series, e.cache, '2026-08', TODAY, st)
        self.assertIn(needle, str(cm.exception))
        self.assertEqual(e.raw(), before)
        self.assertEqual(e.tmp_files(), [])
        return st

    def test_last_month_is_min_of_two_tables(self):
        for der, gua in ((DER_ROWS + [LINE_DER_08], GUA_ROWS), (DER_ROWS, GUA_ROWS + [LINE_GUA_08])):
            e = Env(der=der, gua=gua)
            try:
                self.assertEqual(T.last_month(e.series), '2026-07')
            finally:
                e.close()

    def test_fingerprint_follows_content(self):
        self.env = Env()
        fp0 = T.fingerprint(self.env.series)
        self.rewrite(T.GUA_CSV, b'355994349.0', b'355994348.0')          # 同长度改一位
        fp1 = T.fingerprint(self.env.series)
        self.rewrite(T.DER_CSV, b'230720646', b'230720647')
        self.assertEqual(len({fp0, fp1, T.fingerprint(self.env.series)}), 3)

    def test_header_columns_swapped(self):
        self.env = Env()
        self.rewrite(T.DER_CSV, b'open_notional_ntd_k,open_fair_value_ntd_k',
                     b'open_fair_value_ntd_k,open_notional_ntd_k')
        self.assertEqual(self.refused('表头不对').asked, [])

    def test_gap_month(self):
        self.env = Env(gua=[GUA_ROWS[0], GUA_ROWS[2]])
        self.assertEqual(self.refused('断月').asked, [])

    def test_existing_row_differs_from_6k(self):
        self.env = Env(der=DER_ROWS + ['2026-08,192798341,1582050.0'])   # der 已有 2026-08 但 MtM 差 1，gua 落后
        self.refused('已有 2026-08 行')

    def test_table_changed_after_read_not_overwritten(self):
        e = self.env = Env()
        der_path = os.path.join(e.series, T.DER_CSV)
        base = e.stub()

        def opener(url, data, headers):                  # MOPS 对账那一刻，别人往 der 表里写了一行
            if url == T.MOPS_T05ST11:
                with open(der_path, 'ab') as f:
                    f.write(b'2026-08,1,1.0\n')
            return base(url, data, headers)

        before = e.raw()
        with self.assertRaises(T.Tsm6kError) as cm:
            quiet(T.update, e.series, e.cache, '2026-08', TODAY, opener)
        self.assertIn('被改动过', str(cm.exception))
        self.assertEqual(e.raw(), (before[0] + b'2026-08,1,1.0\n', before[1]))   # 别人那行原样在，两表都没追加
        self.assertEqual(e.tmp_files(), [])

    def test_tmp_files_live_under_cache_tsm_6k(self):
        e = self.env = Env()
        moves, real = [], os.replace

        def spy(src, dst):
            moves.append((src, dst))
            return real(src, dst)

        with mock.patch.object(T.os, 'replace', spy):
            added = quiet(T.update, e.series, e.cache, '2026-08', TODAY, e.stub())[0]
        self.assertEqual(added, ['2026-08'])
        tmp_dir = os.path.join(e.cache, T.CACHE_SUB)
        into_series = sorted((os.path.basename(d), os.path.dirname(s), s.endswith('.tmp'))
                             for s, d in moves if os.path.dirname(d) == e.series)
        self.assertEqual(into_series, [(T.DER_CSV, tmp_dir, True), (T.GUA_CSV, tmp_dir, True)])


class TestDriftRaises(Base):
    def test_fair_value_off_by_one(self):
        rows = DER_ROWS[:2] + ['2026-07,230720646,-2645506.0']
        e = Env(der=rows)
        try:
            before = e.raw()
            with self.assertRaises(T.Tsm6kError) as cm:
                quiet(T.update, e.series, e.cache, '2026-08', TODAY, e.stub())
            self.assertIn('2026-07 open_fair_value_ntd_k', str(cm.exception))
            self.assertEqual(e.raw(), before)
            self.assertEqual(e.tmp_files(), [])
        finally:
            e.close()


class TestAmendment2020Precedent(Base):
    """口径坑 i：2020-04-14 的 0001564590-20-016539 是月报 6-K/A，reportDate 沿用原件。照此前例，
    今天的更正件 reportDate = 月末、未缓存：原件已缓存且先认到，也必须下载它、让它胜出。"""

    A07 = row('2026-08-20', '0001046179-26-000540', 'tsm-20260820x6ka.htm', 101000, '2026-07-31', form='6-K/A')
    ROWS = [REV['2026-05'], REV['2026-06'], MONTHEND_07, REV['2026-07'], A07, DIVIDEND, REV['2026-08']]

    def setUp(self):
        super().setUp()
        self.env = Env()

    def tearDown(self):
        self.env.close()
        super().tearDown()

    def test_amended_cell_downloaded_wins_drift_raises_zero_write(self):
        e = self.env
        st = e.stub(rows=self.ROWS)
        st.routes[url_of(self.A07)] = html(synth('2026-07,230720000,-2645507.0', GUA_ROWS[2]))
        before = e.raw()
        with self.assertRaises(T.Tsm6kError) as cm:
            quiet(T.update, e.series, e.cache, '2026-08', TODAY, st)
        msg = str(cm.exception)
        self.assertIn(url_of(self.A07), st.asked)                                        # 被下载
        self.assertIn("2026-07 open_notional_ntd_k: 库内 '230720646' vs 官方 230720000", msg)  # 胜出
        self.assertIn(self.A07['acc'], msg)
        self.assertEqual(e.raw(), before)                                                # 零写入
        self.assertEqual(e.tmp_files(), [])
        self.assertNotIn(url_of(REV['2026-08']), st.asked)

    def test_amendment_outside_six_cells_passes(self):
        # 2020 那次更正的是 TSMC Global 已沖銷名目 —— 6 格之外：6-K/A 照样胜出，体检通过，新月份照常追加
        e = self.env
        doc = synth(DER_ROWS[2], GUA_ROWS[2])
        g_old = blk('TSMC Global Future', '253,144', '1,467')
        self.assertEqual(doc.count(g_old), 1)
        doc = doc.replace(g_old, g_old.replace('Expired Contracts Cumulative Notional Amount -',
                                               'Expired Contracts Cumulative Notional Amount 9,755,101'))
        st = e.stub(rows=self.ROWS)
        st.routes[url_of(self.A07)] = html('Amendment: correction of the Notional Amount of TSMC Global Expired '
                                           'Contracts; all other numbers remain unchanged. ' + doc)
        added, out = quiet(T.update, e.series, e.cache, '2026-08', TODAY, st)
        self.assertEqual(added, ['2026-08'])
        self.assertIn(url_of(self.A07), st.asked)
        self.assertIn(f'取 {self.A07["acc"]}', out)
        der, gua = e.raw()
        self.assertTrue(der.endswith((LINE_DER_08 + '\n').encode()))
        self.assertTrue(gua.endswith((LINE_GUA_08 + '\n').encode()))


class TestBackfillCap(Base):
    def test_too_many_months(self):
        e = Env(der=['2026-01,1,1.0', '2026-02,1,1.0', '2026-03,1,1.0'],
                gua=['2026-01,1,1.0,1.0,1.0', '2026-02,1,1.0,1.0,1.0', '2026-03,1,1.0,1.0,1.0'])
        try:
            st = Stub()
            with self.assertRaises(T.Tsm6kError) as cm:
                T.update(e.series, e.cache, '2026-08', TODAY, st)
            self.assertIn('MAX_BACKFILL', str(cm.exception))
            self.assertEqual(st.asked, [])
        finally:
            e.close()


# ══════════════════════════════════════════════════════════════════════════
# 14：真缓存重放
# ══════════════════════════════════════════════════════════════════════════
@unittest.skipUnless(os.path.isdir(os.path.join(REAL_CACHE, T.CACHE_SUB)),
                     f'没有 {os.path.join(REAL_CACHE, T.CACHE_SUB)}（设 TSM6K_CACHE 指向含 tsm_6k/ 的 cache 目录）')
class TestReplayCached(Base):
    def test_all_cached_reports_equal_series(self):
        series = os.path.join(ROOT, 'series')
        res, out = quiet(T._replay, series, REAL_CACHE)
        errors = [(r['month'], r['file'], r['error']) for r in res if r['error']]
        self.assertEqual(errors, [])
        cmp_ = [r for r in res if not r['pending']]
        diffs = [(r['month'], r['diffs']) for r in cmp_ if r['diffs']]
        self.assertEqual(diffs, [])
        self.assertNotIn('⚠', out, '真件里出现了清单外的块主体（口径坑 k）')
        self.assertGreaterEqual(len(cmp_), 41)
        self.assertEqual(min(r['month'] for r in cmp_), T.FORMAT_FROM)
        last = T.last_month(series)
        self.assertTrue(all(r['month'] > last for r in res if r['pending']))
        print(f'\n    TestReplayCached：{len(cmp_)} 个月 × 6 列逐格相等'
              f'（{cmp_[0]["month"]}..{cmp_[-1]["month"]}，cache = {REAL_CACHE}）', end=' ')


# ══════════════════════════════════════════════════════════════════════════
# 模块卫生：重述台账字面量、依赖、SEC UA 与 fetch/umc.py 同值
# ══════════════════════════════════════════════════════════════════════════
class TestModuleHygiene(Base):
    def test_no_quoted_restatement_log_literal(self):
        pat = re.compile('[\'"][A-Za-z0-9_]*' + 'restatements' + r'\.csv' + '[\'"]')
        for name in ('tsm_6k.py', 'test_tsm_6k.py'):
            with open(os.path.join(HERE, name), encoding='utf-8') as f:
                self.assertEqual(pat.findall(f.read()), [], f'{name} 里有重述台账字面量（口径坑 j）')

    def test_stdlib_only(self):
        with open(os.path.join(HERE, 'tsm_6k.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names |= {a.name.split('.')[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split('.')[0])
        self.assertEqual(names - set(sys.stdlib_module_names), set())
        self.assertFalse({'umc', 'tsm'} & names)

    @unittest.skipIf('SEC_EDGAR_UA' in os.environ, '设了 SEC_EDGAR_UA，默认值不生效')
    def test_user_agent_same_as_umc(self):
        with open(os.path.join(HERE, 'umc.py'), encoding='utf-8') as f:
            tree = ast.parse(f.read())
        ua = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
              and any(getattr(t, 'id', None) == '_UA' for t in n.targets)]
        self.assertEqual(ua, [T.USER_AGENT])


def main():
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    print('\n' + '=' * 72)
    skipped = [str(t) for t, _ in result.skipped]
    if not result.wasSuccessful():
        print('FAILED —— %d 处失败 / %d 处错误' % (len(result.failures), len(result.errors)))
        return 1
    print('PASS —— %d 条；跳过 %d 条%s' % (result.testsRun, len(skipped),
                                        ('：' + '；'.join(skipped)) if skipped else ''))
    if any('TestReplayCached' in s for s in skipped):
        print('⚠ TestReplayCached 被跳过：真缓存重放没跑（设 TSM6K_CACHE 指向含 tsm_6k/ 的 cache 目录）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
