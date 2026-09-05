# -*- coding: utf-8 -*-
"""fetch/lseg_tradeweb.py 的发布日护栏测试 —— 全部离线，只用标准库。

跑法: python3 fetch/test_lseg_tradeweb.py

━━ 这套测试守的是哪一件事 ━━
2026-09 Tradeweb 官网改版，工作簿的 href 从

    /globalassets/newsroom/08.06.26-july-mar/tw-historical-adv-…-july-2026.xlsx
                            ↑ MM.DD.YY 就是发布日

变成

    /4a4dd2/globalassets/newsroom/monthly-activity-reports/2026/august/
        tw-historical-adv-and-day-count-through-august-2026.xlsx
     ↑ 每份文件各不相同的缓存串，**URL 里再没有任何日期**

`_FOLDER_DATE` 那条正则当场失配，整条腿硬失败：
    TradewebFetchError: 工作簿 href 里没有 MM.DD.YY 目录名，取不到发布日：…

那次失败真正的教训**不是**「正则该写宽一点」，而是「一个印不出来的字段不该有
打死数据腿的权力」：那一期的数据完完整整躺在工作簿里，116 个月一格没少，
而发布日在本仓的去向只有 fetch/lseg.py 的 `release_dates()`（它本来就接受 None），
`series/source_dates.csv` 至今没有 lseg 行。所以本文件钉的是两件事：

  1. 换源之后那个替代发布日**立不立得住**（三道判据的边界）；
  2. 三道判据全部失灵时**数据还在不在**（每条降级用例都断言字节照常返回）——
     这一条才是 2026-09 那次停摆的回归签名。

分界线不在「严不严」而在「护的是发布日还是护的是数据」：体积不够照旧硬抛
（TestDataGuardsStayHard），「文件名说的月 vs 抬头说的月」不一致也照旧硬抛。

发布日现在来自两处**源头自述**，谁都不许退回构建日 / 文件 mtime（CONTRACT.md §1）：
    1. 工作簿的 HTTP Last-Modified   —— 主源，服务器写的
    2. 工作簿内部 docProps/core.xml 的 dcterms:modified —— 出报表那条工具链写的
外加一道不依赖任何时间戳的结构性判据：发布日必须落在**数据月月末之后**的窗口里。

━━ 夹具是编的，测的是逻辑不是世界 ━━
下面的 xlsx 是当场压出来的 zip，只保证「大于 MIN_XLSX_BYTES、能被 zipfile 打开、
docProps/core.xml 在里面」。它测的是三道判据的边界，不是「2026 年 8 月 Tradeweb
到底发了多少」—— 后者是 fetch/lseg_tradeweb.py 与官网之间的事。

实测锚点（2026-09-05，2026-08 那期）：
    Last-Modified        Fri, 04 Sep 2026 11:29:03 GMT   → 2026-09-04
    dcterms:modified     2026-09-02T18:11:28Z            → 2026-09-02
    数据月               2026-08（月末 08-31）→ 发布日落在月末后第 4 天
"""

import datetime
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import lseg_tradeweb as tw        # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 合成夹具
# ═══════════════════════════════════════════════════════════════════════════
REAL_LM = 'Fri, 04 Sep 2026 11:29:03 GMT'      # 实测头，逐字节照抄
REAL_HREF = ('/4a4dd2/globalassets/newsroom/monthly-activity-reports/2026/'
             'august/tw-historical-adv-and-day-count-through-august-2026.xlsx')
OLD_HREF = ('/globalassets/newsroom/08.06.26-july-mar/'
            'tw-historical-adv-and-day-count-through-july-2026.xlsx')

_CORE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<cp:coreProperties '
         'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
         'xmlns:dcterms="http://purl.org/dc/terms/" '
         'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
         '<dcterms:modified xsi:type="dcterms:W3CDTF">%sT18:11:28Z</dcterms:modified>'
         '</cp:coreProperties>')


def book(modified='2026-09-02', with_core=True):
    """压一份够大的假工作簿。padding 是为了越过 MIN_XLSX_BYTES 那道体积判据。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        if with_core:
            z.writestr('docProps/core.xml', _CORE % modified)
        z.writestr('xl/worksheets/sheet1.xml', 'x' * (tw.MIN_XLSX_BYTES * 3))
    return buf.getvalue()


class _Patched:
    """把 _http_get 换成夹具，跑完还回去。测试全程不碰网络。"""

    def __init__(self, data, last_modified=REAL_LM):
        self.data, self.lm = data, last_modified

    def __enter__(self):
        self.orig = tw._http_get
        headers = {'Last-Modified': self.lm} if self.lm is not None else {}
        tw._http_get = lambda url, *a, **k: (self.data, headers)
        return self

    def __exit__(self, *exc):
        tw._http_get = self.orig
        return False


def resolve(month='2026-08', **kw):
    with _Patched(kw.pop('data', book()), **kw):
        return tw._resolve_published('https://example.invalid/x.xlsx', month)


# ═══════════════════════════════════════════════════════════════════════════
class TestHttpDate(unittest.TestCase):

    def test_real_header_parses(self):
        self.assertEqual(tw._http_date(REAL_LM), datetime.date(2026, 9, 4))

    def test_missing_or_garbage_is_none(self):
        for raw in (None, '', 'yesterday', 'Fri, 32 Xxx 2026 11:29:03 GMT'):
            self.assertIsNone(tw._http_date(raw), raw)


class TestAuthoredDate(unittest.TestCase):

    def test_reads_dcterms_modified(self):
        self.assertEqual(tw._authored_date(book()), datetime.date(2026, 9, 2))

    def test_absent_core_xml_is_none(self):
        self.assertIsNone(tw._authored_date(book(with_core=False)))

    def test_not_a_zip_is_none(self):
        # 拿到 HTML 错误页而不是工作簿时走这一支：返回 None（降级），不炸栈。
        self.assertIsNone(tw._authored_date(b'<html>404</html>'))


class TestPublishWindow(unittest.TestCase):
    """发布日必须落在数据月月末之后 1..75 天 —— 这道判据不依赖任何时间戳自述。

    ⚠ 全部**只降级不抛**：发布日在页面上一个字都印不出来（series/source_dates.csv
      至今没有 lseg 行），2026-09 那次整条腿停摆正是因为这个字段会抛。
      每条都顺带断言「数据还在」——「不阻断」是这套测试真正要钉住的东西。
    """

    def test_real_august_case_passes(self):
        data, published = resolve('2026-08')
        self.assertEqual(published, datetime.date(2026, 9, 4))
        self.assertTrue(len(data) > tw.MIN_XLSX_BYTES)

    def test_december_year_boundary(self):
        # 跨年是月末算法最容易写错的一格：2026-12 的月末必须是 2026-12-31。
        _, published = resolve('2026-12', last_modified='Mon, 04 Jan 2027 11:29:03 GMT',
                               data=book('2027-01-02'))
        self.assertEqual(published, datetime.date(2027, 1, 4))

    def test_published_inside_the_data_month_degrades(self):
        # 发布日落在数据月**之内** = 那个月还没走完就发了全月数，不可能 → 记未知。
        data, published = resolve('2026-08', last_modified='Mon, 24 Aug 2026 11:29:03 GMT',
                                  data=book('2026-08-24'))
        self.assertIsNone(published)
        self.assertTrue(len(data) > tw.MIN_XLSX_BYTES, '数据必须照常返回')

    def test_stale_last_modified_degrades(self):
        # 服务器把上架时间写成了别的东西（例如整站部署时间）→ 差得离谱就记未知。
        data, published = resolve('2026-08', last_modified='Wed, 04 Feb 2026 11:29:03 GMT',
                                  data=book('2026-02-02'))
        self.assertIsNone(published)
        self.assertTrue(len(data) > tw.MIN_XLSX_BYTES, '数据必须照常返回')

    def test_missing_last_modified_degrades_not_fails(self):
        # 这一条是 2026-09 那次停摆的正面回归签名：主源没了也**不许**打死数据腿。
        data, published = resolve('2026-08', last_modified=None)
        self.assertIsNone(published)
        self.assertTrue(len(data) > tw.MIN_XLSX_BYTES, '数据必须照常返回')


class TestDataGuardsStayHard(unittest.TestCase):
    """分界线：护发布日的降级，护**数据**的照旧硬抛。"""

    def test_undersized_download_still_raises(self):
        # 下到 HTML 错误页 / 半截文件 —— 这是数据问题，必须抛。
        with self.assertRaises(tw.TradewebFetchError) as cm:
            resolve('2026-08', data=b'<html>404</html>')
        self.assertIn('不像是正常的工作簿', str(cm.exception))


class TestCrossCheck(unittest.TestCase):
    """第二源：工作簿自述的 dcterms:modified。同样只降级不抛。"""

    def test_real_two_day_gap_passes(self):
        _, published = resolve('2026-08', data=book('2026-09-02'))
        self.assertEqual(published, datetime.date(2026, 9, 4))

    def test_wildly_disagreeing_authored_date_degrades(self):
        data, published = resolve('2026-08', data=book('2026-01-05'))
        self.assertIsNone(published)
        self.assertTrue(len(data) > tw.MIN_XLSX_BYTES, '数据必须照常返回')

    def test_authored_after_published_degrades(self):
        # 文件自称比它上架还晚 → 两个数字不是一回事，别猜，记未知。
        _, published = resolve('2026-08', data=book('2026-09-30'))
        self.assertIsNone(published)

    def test_absent_second_source_keeps_the_primary(self):
        # 第二源缺席只掉一档：窗口判据还在，主源仍然算数。
        _, published = resolve('2026-08', data=book(with_core=False))
        self.assertEqual(published, datetime.date(2026, 9, 4))


class TestHrefParsing(unittest.TestCase):
    """改版回归签名：数据月只能从**文件名**读，绝不能再从目录名读日期。"""

    def test_new_href_still_yields_the_data_month(self):
        m = tw._FILE_MONTH.search(REAL_HREF)
        self.assertIsNotNone(m, '新版 href 里读不出 through-<month>-<year>')
        self.assertEqual((m.group(1).capitalize(), m.group(2)), ('August', '2026'))

    def test_old_href_still_yields_the_data_month(self):
        # 旧链接万一还在页面上（或被镜像），文件名那一半的解析不该跟着改版一起坏。
        m = tw._FILE_MONTH.search(OLD_HREF)
        self.assertIsNotNone(m)
        self.assertEqual((m.group(1).capitalize(), m.group(2)), ('July', '2026'))

    def test_no_module_level_dependency_on_a_date_in_the_url(self):
        # 这一条是 2026-09 那次故障的直接回归签名：只要还有人从 URL 里抠日期，
        # 下一次改版就会以同样的方式把整条腿打死。
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                'lseg_tradeweb.py'), encoding='utf-8').read()
        self.assertNotIn('_FOLDER_DATE', src,
                         'URL 里已经没有日期了，不该再有从目录名抠发布日的正则')

    def test_hist_name_matches_the_new_filename(self):
        self.assertTrue(tw._HIST_NAME.search(REAL_HREF))


def main():
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    print('\n' + '=' * 72)
    if not result.wasSuccessful():
        print('FAILED —— %d 处失败 / %d 处错误'
              % (len(result.failures), len(result.errors)))
        return 1
    print('PASS —— 发布日仍然只认两处源头自述 + 一道数据月窗口；'
          '三道全失灵时数据照常入库（2026-09 停摆的回归签名）。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
