# -*- coding: utf-8 -*-
"""build/payload_guard.py + build/brief.py + build/single.py 三条护栏的单元测试。

跑法: python3 build/test_guards.py        （只用标准库 + numpy，不需要 pytest）

这套测试是为「把 MOPS 官方增减原因原文写进 brief」那次改造建的，守两件事（A、B 组）；
2026-09 加了第三件（H 组，`spike_cap()` 的端点护栏），理由写在那一组的组头上 ——
一句话：**那条缺陷现网一处都没命中，只能靠注入守**，真产出当不了判据。

 (a) **payload_guard 的 nan/inf 正则放宽之后，一个该拦的都没少拦。**
     必须拦的那一组（`$nanbn` / `nan%` / `+naNpp` / `inf` / `infinity` …）是
     模块头注释里逐条列过的既有用例，改正则最容易出的事故就是把它们一起放掉。
     必须放行的那一组是新加的：`NAND` / `info` / `nano` 这类**出现在中文句子里的
     正常英文词**，南亚科（DRAM）与世芯（ASIC）的备注原文里出现它们是常态。

 (b) **brief.render() 的引文豁免不改变不引用时的行为。**
     测法不是造夹具，是把仓库里 19 个 data/*.js 已发布的 brief **原文**取出来
     重新过一遍 render()，逐字节比对。夹具能证明的只是「代码与夹具自洽」
     （build/test_pools.py 的 TestRealFxTable 那一段吃过这个亏），
     只有拿真产出去撞才能证明「代码与仓库自洽」。
"""

import glob
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import brief as B                # noqa: E402
import payload_guard as PG       # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# A. payload_guard —— 必须拦 / 必须放
# ═══════════════════════════════════════════════════════════════════════════
# 必须拦：模块头「字符串匹配的误伤边界」逐条列过的既有用例 + 真实事故串。
MUST_BLOCK = [
    'nan%',                                   # f'{nan:+.1f}%'
    '$nanbn',                                 # f'${nan:,.1f}bn' —— 右侧紧跟单位字母
    'nanmn/日',
    '$nantn',
    'nank',
    '+nanpp',
    '+naNpp',                                 # 大小写混写照样是格式化产物
    'NaN',
    'nan',
    '-inf',
    'inf',
    'infinity',
    'Infinity',
    '客户资产 $nanbn（+nan% y/y）',            # 模块头原样引用的那条 headline
    '南亚科本月营收 NT$nanbn',                 # 中文串里夹坏值
    '南亚科（nanya）本月 NAND 需求回升，营收 $nanbn',  # 放行词在前、坏串在后
    'nanbp',
    'nanx',
]

# 必须放：正常英文词 / 专有名词，出现在中文句子里不许报 FAIL。
MUST_PASS = [
    'NAND',
    'nand',
    '3D NAND 与 DRAM 需求同步回升',
    '受 NAND 与 HBM 需求成长影响。',           # 南亚科式备注
    'info',
    'more info',
    'nano',
    'nanometer',
    '3nm nanosheet 制程',
    'infra',
    'infer',
    'inflection',
    'information',
    'inflows',
    'influence',
    'infrastructure',
    'financial',
    'nanya',                                  # ticker（既有白名单）
    'build/specs/nanya.py',
    '南亚科技（nanya，2408.TW）',
    'HBM',
    'AI',
    'ASIC',
    '本月營收較去年同期增加，係因量產產品增加所致。',   # 世芯備註原文（繁体）
    '海外子公司之營收係以當月平均匯率換算之',           # 联发科備註原文
    '受市場需求成長影響。',                             # 南亚科備註原文
    '主要為晶圓產品收入增加',                           # 创意備註原文
]


def _tripped(s):
    """把串塞进一个 payload 走真 check()，返回是否被拦。"""
    try:
        PG.check({'brief': s})
        return False
    except PG.PayloadGuardError:
        return True


class TestPayloadGuardBlocks(unittest.TestCase):
    def test_must_block(self):
        missed = [s for s in MUST_BLOCK if not _tripped(s)]
        self.assertEqual(missed, [], f'这些坏串被放过了：{missed}')


class TestPayloadGuardPasses(unittest.TestCase):
    def test_must_pass(self):
        hit = [s for s in MUST_PASS if _tripped(s)]
        self.assertEqual(hit, [], f'这些正常串被误伤：{hit}')


class TestPayloadGuardNumeric(unittest.TestCase):
    """数值型 NaN / Inf 与合法 null 的行为不因字符串规则改动而变。"""

    def test_float_nan_blocked(self):
        with self.assertRaises(PG.PayloadGuardError):
            PG.check({'exhibits': [{'n': 3, 'title': 'x', 'v': [1.0, float('nan')]}]})

    def test_float_inf_blocked(self):
        with self.assertRaises(PG.PayloadGuardError):
            PG.check({'v': float('inf')})

    def test_null_is_legal(self):
        PG.check({'v': [1.0, None, 3.0], 'brief': '缺月按规矩 3 断开'})

    def test_later_bad_string_not_masked_by_allowed_word(self):
        """白名单/放行词在前，不能掩盖同一串后段的真问题（finditer + continue 的性质）。"""
        self.assertTrue(_tripped('NAND 需求回升，但客户资产 $nanbn'))
        self.assertTrue(_tripped('nanya 南亚科，同比 +nan%'))


# ═══════════════════════════════════════════════════════════════════════════
# B. brief.render() —— 不引用时逐字节不变
# ═══════════════════════════════════════════════════════════════════════════
def _published_briefs():
    """从 data/*.js 里取出已发布的 brief，拆回 (页名, 标题, body)。"""
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'data', '*.js'))):
        with open(p, encoding='utf-8') as fh:
            m = re.search(r'window\.DASH = (.*);\n?$', fh.read(), re.S)
        if not m:
            continue
        try:
            b = json.loads(m.group(1)).get('brief')
        except ValueError:
            continue
        if not b:
            continue
        mm = re.match(r'^<h4>(.*?)</h4><p>(.*)</p>$', b, re.S)
        if mm:
            out.append((os.path.basename(p), mm.group(1), mm.group(2)))
    return out


def _remark_rows():
    """`series/mops_remarks.csv` → {(ticker, 'YYYY-MM'): remark 原文}。读不到返回 {}。"""
    import csv
    p = os.path.join(ROOT, 'series', 'mops_remarks.csv')
    try:
        with open(p, encoding='utf-8') as fh:
            return {(r['ticker'], r['month']): (r.get('remark') or '').strip()
                    for r in csv.DictReader(fh)}
    except OSError:
        return {}


def _data_through(page):
    """data/<page> 的 `data_through`（'YYYY-MM'）。取不到返回 None。"""
    try:
        with open(os.path.join(ROOT, 'data', page), encoding='utf-8') as fh:
            m = re.search(r'window\.DASH = (.*);\n?$', fh.read(), re.S)
        return json.loads(m.group(1)).get('data_through') if m else None
    except (OSError, ValueError, AttributeError):
        return None


class TestRenderRegression(unittest.TestCase):
    """19 个已发布页的 brief 原样重跑 render()，输出必须逐字节相同。"""

    def test_republish_identical(self):
        pages = _published_briefs()
        self.assertGreaterEqual(len(pages), 15, '没读到足够的已发布 brief，测试无效')
        for name, title, body in pages:
            with self.subTest(page=name):
                got = B.render([body], title=title)
                self.assertEqual(got, f'<h4>{title}</h4><p>{body}</p>')

    def test_quote_marker_only_where_the_csv_says_so(self):
        """哪几页带引文标记，必须与 `series/mops_remarks.csv` 逐页对得上。

        这条原来断言的是「今天没有任何一页用引文标记」——那在**接线之前**成立，
        接线之后它每个月都会误报（本轮 alchip / guc / mtk / nanya 四页正当地带上了）。
        直接删掉又会把这条路径变成无人看守的。所以改成断言真正的不变式：

          页面带引文  ⟺  该页 `data_through` 那个月在 CSV 里的 `remark` 非空

        它同时守住两个方向 —— 该有的没有（fetch 断流 / brief 那一支写坏了）
        与不该有的有（引了一个库里没有的字符串）。并且逐字比对引文内容，
        繁体被转成简体、标点被规整、原文被截断，这里都会当场失败。
        """
        rows = _remark_rows()
        if not rows:
            self.skipTest('series/mops_remarks.csv 不可读，跳过')
        pages = {t for t, _ in rows}           # 用这张表的那几页（=七家半导体页）
        newest = max(m for _, m in rows)
        seen, ahead = 0, []
        for name, _, body in _published_briefs():
            t = name[:-3]
            if t not in pages:
                continue                       # 交易所页等，本来就不在这张表里
            month = _data_through(name)
            if (t, month) not in rows:
                # 唯一合法的缺席：这一页跑在了共享 MOPS 表**前面**。
                # 各家自己的申报最早次月第 4 天就到，而 MOPS 全市场汇总要等最后一家
                # 申报完（实测第 13 天，见 monthly_run.mops_remarks 的 docstring）——
                # 中间那十天里，先披露的那一两页本来就比这张表新。
                # 2026-09-05 实测：umc 的 6-K 已到 2026-08，而 CSV 还停在 2026-07。
                # 原来这里写的是无条件 `continue` + 末尾 `seen >= 7`，于是那十天里
                # 每天都会误报一次「测试无效」——而 test_guards 是 preflight 闸门，
                # 误报一次就是整轮不发。
                if month > newest:
                    ahead.append((t, month))
                    continue
                self.fail(f'{name} 的 data_through={month} 不晚于 CSV 最新月 {newest}，'
                          f'却在 CSV 里找不到 ({t}, {month}) —— 接线多半断了'
                          f'（页面路径变了 / CSV 的 ticker 拼写变了）')
            seen += 1
            want = rows[(t, month)]
            with self.subTest(page=name):
                got = re.findall(r'<span class="mops-quote">(.*?)</span>', body)
                if want:
                    self.assertEqual(got, [want],
                                     f'{name} 的引文与 CSV 不符（逐字比对）')
                else:
                    self.assertEqual(got, [],
                                     f'{name} 本月 CSV 里备注为空，页面却印出了引文')
        # 每一页都要有着落：要么逐字对上了，要么明确是「跑在表前面」。
        # 这比原来的 `seen >= 7` 更严 —— 原来某页悄悄消失只会让计数少一个，
        # 而 7 这个数字自己是硬编码的，页数一变就得改。
        self.assertEqual(seen + len(ahead), len(pages),
                         f'用这张表的有 {len(pages)} 页，只扫到 {seen} 页对上 + '
                         f'{len(ahead)} 页跑在表前面 —— 有页面没被扫到，测试无效')


class TestRenderBounds(unittest.TestCase):
    """无引文时的上下限行为。"""

    def test_too_short_fails(self):
        with self.assertRaises(SystemExit):
            B.render(['短' * 229])

    def test_lo_edge_passes(self):
        B.render(['短' * 230])

    def test_hi_edge_passes(self):
        B.render(['长' * 380])

    def test_too_long_fails(self):
        with self.assertRaises(SystemExit):
            B.render(['长' * 381])

    def test_tags_not_counted(self):
        """HTML 标签不计入字数（既有口径）。"""
        B.render(['<b>' + '字' * 230 + '</b>'])


# ═══════════════════════════════════════════════════════════════════════════
# C. brief.quote() —— 引文豁免
# ═══════════════════════════════════════════════════════════════════════════
# 2026-07 期实测的四条 MOPS 備註原文（繁体原值，不转简体）。
REMARKS = {
    'mtk': '海外子公司之營收係以當月平均匯率換算之',
    'nanya': '受市場需求成長影響。',
    'alchip': '本月營收較去年同期增加，係因量產產品增加所致。',
    'guc': '主要為晶圓產品收入增加',
}


class TestQuoteHelper(unittest.TestCase):
    def test_real_remarks_all_fit(self):
        for t, r in REMARKS.items():
            with self.subTest(ticker=t):
                self.assertLessEqual(len(r), B.QUOTE_MAX)
                self.assertIn(r, B.quote(r))       # 原文逐字保留，未转简体、未截断

    def test_whitespace_folded_only(self):
        self.assertEqual(B.quote('  受市場需求\n 成長影響。 '),
                         B.quote('受市場需求 成長影響。'))

    def test_empty_remark_raises(self):
        for bad in ('', '   ', '\n'):
            with self.subTest(v=bad):
                with self.assertRaises(SystemExit):
                    B.quote(bad)

    def test_angle_brackets_raise(self):
        with self.assertRaises(SystemExit):
            B.quote('受<b>市場</b>需求成長影響。')

    def test_over_max_raises(self):
        with self.assertRaises(SystemExit):
            B.quote('原' * (B.QUOTE_MAX + 1))

    def test_quoted_len_matches_plain(self):
        r = REMARKS['alchip']
        self.assertEqual(B.quoted_len(B.quote(r)), len(r))


class TestQuoteExemption(unittest.TestCase):
    """减法语义：豁免只对引文成立，上下限对自撰部分同时成立。"""

    def test_quote_buys_headroom_for_the_quote_only(self):
        """自撰 380（顶格）+ 引文 20 ⇒ 总长 400，通过。"""
        out = B.render(['我' * 380, B.quote(REMARKS['mtk'])])
        self.assertIn(REMARKS['mtk'], out)

    def test_quote_does_not_buy_headroom_for_prose(self):
        """自撰 381 ⇒ 无论引不引，都必须失败。"""
        with self.assertRaises(SystemExit):
            B.render(['我' * 381, B.quote(REMARKS['mtk'])])

    def test_long_quote_thin_prose_fails(self):
        """整条机制的要害：引文 100 字 + 自撰 200 字，总长 300 好看，但必须失败。

        「只把 hi 调大」的做法会放它过关 —— 那正是这条护栏本来要拦的东西。
        """
        with self.assertRaises(SystemExit):
            B.render(['我' * 200, B.quote('原' * 100)])

    def test_floor_rises_with_quote(self):
        """引 100 字，自撰仍须满 230（总长 330）才够格。"""
        with self.assertRaises(SystemExit):
            B.render(['我' * 229, B.quote('原' * 100)])
        B.render(['我' * 230, B.quote('原' * 100)])

    def test_quote_cap_enforced_in_render(self):
        """多段引文合计也要受 QUOTE_MAX 管，不能靠拆成两段绕过。"""
        half = '原' * (B.QUOTE_MAX // 2 + 1)
        with self.assertRaises(SystemExit):
            B.render(['我' * 300, B.quote(half), B.quote(half)])

    def test_lead_in_words_are_ours(self):
        """引号与引导语算我们自己的字（它们在标记外面）。"""
        r = REMARKS['nanya']
        body = '我' * 380 + '公司在备注栏填的是「' + B.quote(r) + '」。'
        with self.assertRaises(SystemExit):
            B.render([body])

    def test_payload_guard_accepts_a_quoted_brief_wired(self):
        """两条护栏串起来跑一遍：带引文、带 NAND 的 brief 能过 payload_guard。"""
        body = ('我' * 300 + '公司在备注栏填的是「'
                + B.quote('受 NAND 與 HBM 需求成長影響。') + '」。')
        PG.check({'brief': B.render([body])})


class TestProseLen(unittest.TestCase):
    """prose_len 与 render 的判据必须是同一个数（render 那两支没改，数法在两处）。"""

    def test_matches_render_at_both_edges(self):
        for q in ('', B.quote(REMARKS['mtk'])):
            with self.subTest(quoted=bool(q)):
                for n in (B.PROSE_LO, B.PROSE_HI):
                    s = ['我' * n, q]
                    self.assertEqual(B.prose_len(s), n)
                    B.render(s)
                for n in (B.PROSE_LO - 1, B.PROSE_HI + 1):
                    s = ['我' * n, q]
                    self.assertEqual(B.prose_len(s), n)
                    with self.assertRaises(SystemExit):
                        B.render(s)

    def test_tags_not_counted(self):
        self.assertEqual(B.prose_len(['<b>我我</b>', '我', '']), 3)


class TestFitOptional(unittest.TestCase):
    """可让位的句子：放得下原样、放不下换精简版、再放不下不写（2026-09-12 tsm 事故）。

    形状照抄事故现场：前文 + 钩子句 + 引文句，引导语「公司填的是「」」。」8 字照常计费。
    """

    LEAD = '公司填的是「' + B.quote('因先進製程產品需求增加所致。') + '」。'

    def test_fits_unchanged_and_compact_not_called(self):
        s = ['我' * 300, '钩' * 50, self.LEAD]            # 358
        called = []
        out = B.fit_optional(s, 1, compact=lambda: called.append(1) or '短')
        self.assertEqual(out, '钩' * 50)
        self.assertEqual(called, [])

    def test_overflow_takes_compact(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]            # 388
        out = B.fit_optional(s, 1, compact=lambda: '钩' * 60)
        self.assertEqual(out, '钩' * 60)                   # 368
        B.render([s[0], out, s[2]])

    def test_compact_still_overflows_drops_sentence(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]
        out = B.fit_optional(s, 1, compact=lambda: '钩' * 79)   # 387，仍超
        self.assertEqual(out, '')
        B.render([s[0], out, s[2]])

    def test_no_compact_drops_sentence(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]
        self.assertEqual(B.fit_optional(s, 1), '')

    def test_does_not_mask_overflow_elsewhere(self):
        """别的句子本身就超额：这一句让掉了，render 照样硬失败。"""
        s = ['我' * 390, '钩' * 10, self.LEAD]
        out = B.fit_optional(s, 1, compact=lambda: '钩')
        self.assertEqual(out, '')
        with self.assertRaises(SystemExit):
            B.render([s[0], out, s[2]])

    def test_input_list_not_mutated(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]
        before = list(s)
        B.fit_optional(s, 1, compact=lambda: '钩' * 60)
        self.assertEqual(s, before)


# ═══════════════════════════════════════════════════════════════════════════
# D. 打真表 —— series/mops_remarks.csv 的每一条备注原文
# ═══════════════════════════════════════════════════════════════════════════
# 上面 A/C 两组是我自己编的串，它们只能证明「代码与我的假设自洽」。
# 这一组把**公司真的填过的**每一条备注原文喂进两条护栏（同 test_pools.py 的
# TestRealFxTable）。实测 168 行里 65 条非空、最长 31 字，且 guc 的原文里真的夹着
# 半角括号与英文（`委託設計(NRE)`、`晶圓產品(Wafer production)`）—— 正是 B 组要防的形状。
REMARKS_CSV = os.path.join(ROOT, 'series', 'mops_remarks.csv')


@unittest.skipUnless(os.path.exists(REMARKS_CSV),
                     'series/mops_remarks.csv 还没落库（fetch/mops_remarks.py 未跑）')
class TestRealRemarks(unittest.TestCase):
    def _rows(self):
        import csv
        with open(REMARKS_CSV, encoding='utf-8') as f:
            return [r for r in csv.DictReader(f) if r.get('remark', '').strip()]

    def test_every_real_remark_survives_both_guards(self):
        rows = self._rows()
        self.assertGreater(len(rows), 20, '非空备注太少，测试无意义')
        for r in rows:
            with self.subTest(month=r['month'], ticker=r['ticker']):
                q = B.quote(r['remark'])                       # 不该被 quote() 拒绝
                body = '我' * 300 + '公司在备注栏填的是「' + q + '」。'
                PG.check({'brief': B.render([body])})          # 不该被 payload_guard 误伤

    def test_real_remarks_are_well_within_quote_max(self):
        longest = max(len(r['remark'].strip()) for r in self._rows())
        self.assertLessEqual(longest, B.QUOTE_MAX,
                             f'最长备注 {longest} 字已超 QUOTE_MAX，该重新审视上限与「不截断」的处理')

    def test_verbatim_not_transcoded(self):
        """原文逐字进出：不转简体、不改标点。"""
        for r in self._rows()[:40]:
            with self.subTest(month=r['month'], ticker=r['ticker']):
                self.assertIn(r['remark'].strip(), B.quote(r['remark']))


# ═══════════════════════════════════════════════════════════════════════════
# E. audit_overdue_headline —— 判据必须与首页红点逐字等价
# ═══════════════════════════════════════════════════════════════════════════
# 这一道守的不是「护栏会不会响」，而是**它和红点会不会各说各话**。两边一旦分家，
# cron 日志与首页就会在同一天给出相反的结论，而那种矛盾没人能一眼判出谁对。
#
# 测法照本文件 (b) 的规矩：不造夹具，拿**真判据**去撞 —— 把 index.html:70-85 的
# stale() 逐行移植成 Python，与 monthly_run.audit_overdue_headline 用的那条算术
# 在 28 家 × 6 个 data_through × 730 天上逐组对拍。
#
# ⚠ 移植时两处最容易写错，都在下面 _js_stale 里标了：
#   · end.getMonth() 是 **0-indexed**，JS 里 `mo = getMonth()===0 ? 12 : getMonth()`
#     算的是「end 的前一个月」= 候选月；
#   · JS 的门槛是 `now >= end + (lag+grace) 天`，而 _due_month(off) 的门槛是
#     `today >= end + (off-1) 天` —— 故 **off = lag + GRACE + 1**。写成 lag+GRACE
#     会让护栏比红点早一天开口。这个 ±1 有实测代价：见 docs/DELIVERY.md 里
#     同一处偏移漏写、让五家闸门整体晚开一天的那条。
import datetime  # noqa: E402

_MR = None
_ROSTER = None


def _load_once():
    global _MR, _ROSTER
    if _MR is None:
        import importlib.util
        for name, path in (('_mr_t', os.path.join(ROOT, 'monthly_run.py')),
                           ('_rost_t', os.path.join(ROOT, 'build', 'roster.py'))):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if name == '_mr_t':
                _MR = mod
            else:
                _ROSTER = mod
    return _MR, _ROSTER


def _js_stale(lag, through, now, grace):
    """index.html:70-85 stale() 的逐行移植。now 为 datetime.date。"""
    for k in range(6):
        n = now.year * 12 + now.month - 1 - k
        ey, em0 = n // 12, n % 12                      # em0 = end.getMonth()，0-indexed
        end = datetime.date(ey, em0 + 1, 1)            # 候选月的下月 1 号 = 月末 + 1
        mo = 12 if em0 == 0 else em0                   # 候选月 1-12
        due = end + datetime.timedelta(
            days=(lag[1] if mo % 3 == 0 else lag[0]) + grace)
        if now >= due:
            y = ey - 1 if em0 == 0 else ey
            return through < f'{y}-{mo:02d}'
    return False


class TestOverdueMatchesRedDot(unittest.TestCase):
    THROUGHS = ('2025-11', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09')
    DAYS = 730

    def _disagreements(self, bump):
        mr, rost = _load_once()
        grace, d0, bad = rost.GRACE, datetime.date(2026, 1, 1), []
        for t, lag in sorted(rost.LAG.items()):
            for through in self.THROUGHS:
                for i in range(self.DAYS):
                    today = d0 + datetime.timedelta(days=i)
                    due = mr._due_month(
                        (lag[0] + grace + bump, lag[1] + grace + bump), today)
                    if _js_stale(lag, through, today, grace) != bool(due and through < due):
                        bad.append((t, through, today))
        return bad

    def test_identical_to_red_dot(self):
        bad = self._disagreements(1)                   # 1 = 生产用的那个偏移
        self.assertEqual(bad, [], f'与首页红点分歧 {len(bad)} 组，前三：{bad[:3]}')

    def test_offset_actually_matters(self):
        """反向验：这个对拍不是空过的 —— 偏移写错一天，它必须抓到。"""
        for bump in (0, 2):
            with self.subTest(bump=bump):
                self.assertNotEqual(
                    self._disagreements(bump), [],
                    f'偏移 lag+GRACE+{bump} 竟无分歧 —— 对拍失去意义，先查 _js_stale')

    def test_no_false_alarm_today(self):
        """今天真跑一遍：仓库当前状态下不该有任何一家逾期（有就是真出事了）。"""
        mr, _ = _load_once()
        self.assertEqual(mr.audit_overdue_headline(), [])



# ═══════════════════════════════════════════════════════════════════════════
# F. fetch/msci.py 的缓存键池 —— 写小了护栏 A 会反过来咬人
# ═══════════════════════════════════════════════════════════════════════════
# 这里只测**纯函数**。护栏 A 的其余部分（render_age 阈值、重定向分支、缺头 WARN）
# 要发真请求才验得了，不进 preflight —— 那三条的实测结果记在提交信息里。
#
# 池长是本模块唯一一个「写错了会让护栏反过来咬人」的常数：边缘 s-maxage 是 30 天，
# 池长若 ≤ 30，键回环时会撞上自己 30 天前钉住的旧副本，于是每天误 FAIL。
class TestMsciCacheKeyPool(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            '_msci_t', os.path.join(ROOT, 'fetch', 'msci.py'))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    S_MAXAGE_DAYS = 30          # 响应头 s-maxage=2592000，见 fetch/msci.py 文件头

    def test_pool_outlasts_edge_ttl(self):
        self.assertGreater(
            len(self.m._KEY_POOL), self.S_MAXAGE_DAYS * 2,
            '缓存键池必须远大于边缘 TTL 的天数，否则回环会撞上自己钉住的旧副本')

    def test_no_repeat_within_a_full_cycle(self):
        d0 = datetime.date(2026, 1, 1)
        n = len(self.m._KEY_POOL)
        urls = [self.m._cache_key_url(d0 + datetime.timedelta(days=i)) for i in range(n)]
        self.assertEqual(len(set(urls)), n, '一个周期内出现了重复的缓存键')

    def test_retry_key_differs_and_is_long_unused(self):
        d0 = datetime.date(2026, 1, 1)
        shift = len(self.m._KEY_POOL) // 2
        self.assertNotEqual(self.m._cache_key_url(d0),
                            self.m._cache_key_url(d0, shift=shift))
        self.assertGreater(shift, self.S_MAXAGE_DAYS,
                           '重试用的键距上次使用不足一个 TTL，可能仍是热副本')

    def test_variant_differs_from_canonical_only_in_case(self):
        """变体只能改大小写 —— 改出别的字符就不是同一个页面了。"""
        d0 = datetime.date(2026, 1, 1)
        for i in range(0, len(self.m._KEY_POOL), 37):
            u = self.m._cache_key_url(d0 + datetime.timedelta(days=i))
            with self.subTest(i=i):
                self.assertEqual(u.lower(), self.m.URL.lower())
                self.assertNotEqual(u, self.m.URL)      # 必须真的换了键

    def test_max_render_age_is_over_a_day(self):
        """阈值必须大于一天：同一天人工重跑会复用当日键，最坏 24 小时。"""
        self.assertGreater(self.m.MAX_RENDER_AGE, 24 * 3600)
        self.assertLess(self.m.MAX_RENDER_AGE, self.S_MAXAGE_DAYS * 86400)



# ═══════════════════════════════════════════════════════════════════════════
# F2. fetch/sgx.py 的折行行标签 —— 上下两半都要接回数值行
# ═══════════════════════════════════════════════════════════════════════════
# 2025-09 起 SGX 月报把 Lump Premium 改名为
# `SGX Platts Iron Ore CFR China (Lump Premium) Index Futures`，版面上折成两行、数字夹在中间。
# `_parse_page` 当时只接下半截，标签读成 `Index Futures`，"Iron Ore" 在丢掉的上半截里 ——
# vol_iron_ore_contracts 连续 12 个月静默少加一行（fetch/sgx.py 口径坑 19）。
# 这里用**合成页面**复刻那一处的几何（上半截在数值行上方 ~5.5pt、下半截在下方 ~5.5pt、
# 行距 ~17pt），不依赖 cache/（gitignore 且会被 prune）；有原件时再加一道真 PDF 的对账。
class _FakeSgxPage:
    """只实现 `_page_lines()` 用到的两样：`rect` 与 `get_text('dict')`。"""

    def __init__(self, lines, w=595.0, h=842.0):
        self.rect = type('R', (), {'width': w, 'height': h})()
        self._lines = lines                           # [(x0, yc, text)]，行高固定 11.8pt

    def get_text(self, kind):
        assert kind == 'dict'
        return {'blocks': [{'type': 0, 'lines': [
            {'bbox': (x0, yc - 5.9, x0 + 6.0 * len(t), yc + 5.9), 'spans': [{'text': t}]}
            for x0, yc, t in self._lines]}]}


def _sgx_row(yc, label, nums, x0s=(300.0, 360.0, 420.0)):
    out = [(51.0, yc, label)] if label else []
    return out + [(x, yc, n) for x, n in zip(x0s, nums)]


class TestSgxWrappedLabel(unittest.TestCase):
    MON = '2026-08'

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            '_sgx_t', os.path.join(ROOT, 'fetch', 'sgx.py'))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def _page(self):
        lines = [(51.0, 300.0, 'Metal And Dry Bulk Volume'),
                 (300.0, 330.0, 'Jun 2026'), (360.0, 330.0, 'Jul 2026'), (420.0, 330.0, 'Aug 2026')]
        lines += _sgx_row(360.0, 'SGX IODEX Iron Ore Futures', ('4,774,524', '4,455,532', '4,127,939'))
        lines += _sgx_row(377.0, 'SGX Options On IODEX Iron Ore Swaps', ('0', '0', '0'))
        # 真 PDF（2026-08 期 p24）的排法：上半截、数值行、下半截三条各自独立的文字行
        lines += [(51.0, 388.7, 'SGX Platts Iron Ore CFR China (Lump Premium)')]
        lines += _sgx_row(394.2, '', ('28,774', '29,391', '35,016'))
        lines += [(51.0, 399.5, 'Index Futures')]
        lines += [(51.0, 411.0, 'SGX Platts Iron Ore CFR China (Lump Premium)')]
        lines += _sgx_row(416.5, '', ('0', '0', '0'))
        lines += [(51.0, 422.0, 'Swaps')]
        lines += _sgx_row(439.0, 'Total', ('7,000,000', '6,500,000', '6,000,000'))
        # 紧接着的下一张表：自己没有标题行、直接是表头 —— 它的 title 不许被上面某一行的碎片占掉
        lines += [(300.0, 480.0, 'Jun 2026'), (360.0, 480.0, 'Jul 2026'), (420.0, 480.0, 'Aug 2026')]
        lines += [(51.0, 509.5, 'SGX Platts Iron Ore CFR China (Lump Premium)')]
        lines += _sgx_row(515.0, '', ('1', '2', '3'))
        lines += [(51.0, 520.5, 'Index Futures')]
        return _FakeSgxPage(lines)

    def test_both_halves_rejoined(self):
        b = self.m._parse_page(self._page(), running_head=None)
        labs = [r['lab'] for r in b[0]['rows']]
        self.assertEqual(labs, [
            'SGX IODEX Iron Ore Futures',
            'SGX Options On IODEX Iron Ore Swaps',
            'SGX Platts Iron Ore CFR China (Lump Premium) Index Futures',
            'SGX Platts Iron Ore CFR China (Lump Premium) Swaps',
            'Total'])
        self.assertEqual(b[0]['rows'][2].get('lab_head'),
                         'SGX Platts Iron Ore CFR China (Lump Premium)')
        self.assertIsNone(b[0]['rows'][0].get('lab_head'))

    def test_upper_half_is_not_a_title_candidate(self):
        b = self.m._parse_page(self._page(), running_head=None)
        self.assertEqual(b[0]['title'], 'Metal And Dry Bulk Volume')
        self.assertIsNone(b[1]['title'],
                          '折行上半截被当成了下一张表的标题 —— 它已经补进了行标签，不许再用一次')

    def test_iron_ore_total_counts_the_wrapped_row(self):
        b = self.m._parse_page(self._page(), running_head=None)
        # 4,127,939 + 0 + 35,016 + 0；只修下半截的旧逻辑会得到 4,127,939
        self.assertEqual(self.m._read_iron_ore(b[:1], self.MON), 4127939 + 35016)

    def test_bottom_aligned_wrap(self):
        """第二种排法：数字与最后一行齐平，上半截在上方 ~10.8pt（2024-07 期 p12 实测）。"""
        lines = [(51.0, 250.0, 'Equity Index Futures Volume'),
                 (300.0, 280.0, 'Jun 2024'), (360.0, 280.0, 'Jul 2024')]
        lines += _sgx_row(316.6, 'FTSE Emerging Market Index Futures', ('5', '6'))
        lines += [(51.0, 332.8, 'FTSE Emerging Market inc Korea Net Total Return (USD)')]
        lines += _sgx_row(343.6, 'Index Futures', ('0', '0'))
        lines += _sgx_row(359.8, 'FTSE Emerging Markets ESG Index Futures', ('7', '8'))
        b = self.m._parse_page(_FakeSgxPage(lines), running_head=None)
        self.assertEqual([r['lab'] for r in b[0]['rows']], [
            'FTSE Emerging Market Index Futures',
            'FTSE Emerging Market inc Korea Net Total Return (USD) Index Futures',
            'FTSE Emerging Markets ESG Index Futures'])

    def test_orphan_text_between_rows_goes_to_nearer_row_only(self):
        """离上一行更近（但 ≥ 9pt，不够挂回去）的文字行，不许被下一行抢走。"""
        lines = [(51.0, 250.0, 'Energy Volume'),
                 (300.0, 280.0, 'Jul 2026'), (360.0, 280.0, 'Aug 2026')]
        lines += _sgx_row(310.0, 'Oil Futures', ('1', '2'))
        lines += [(51.0, 320.0, 'stray note')]            # 离上一行 10pt、离下一行 11pt
        lines += _sgx_row(331.0, 'Oil Swaps', ('3', '4'))
        b = self.m._parse_page(_FakeSgxPage(lines), running_head=None)
        self.assertEqual([r['lab'] for r in b[0]['rows']], ['Oil Futures', 'Oil Swaps'])

    def test_lower_half_only_unchanged(self):
        """老路径：标签与数字同一行、续行在下方 —— 修上半截不能把它改坏。"""
        lines = [(51.0, 300.0, 'Interest Rates Futures Volume'),
                 (300.0, 330.0, 'Jul 2026'), (360.0, 330.0, 'Aug 2026')]
        lines += _sgx_row(360.0, 'SGX FTSE 10-Year Indonesia Government', ('10', '20'))
        lines += [(51.0, 365.5, 'Bond Futures')]
        lines += _sgx_row(382.0, 'Total', ('10', '20'))
        b = self.m._parse_page(_FakeSgxPage(lines), running_head=None)
        self.assertEqual([r['lab'] for r in b[0]['rows']],
                         ['SGX FTSE 10-Year Indonesia Government Bond Futures', 'Total'])
        self.assertIsNone(b[0]['rows'][0].get('lab_head'))

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, 'cache', 'sgx_2026-08.pdf')),
                         'cache/sgx_2026-08.pdf 不在（cache/ gitignore 且会被 prune）')
    def test_real_pdf_2026_08_matches_hand_count(self):
        """所有者拿官方 PDF 手加的数：IODEX 期货 4,127,939 + IODEX 期货期权 552,512
        + Lump Premium 期货 35,016 + 65% 期货 33,740 = 4,749,207。"""
        blocks = self.m._load_blocks(os.path.join(ROOT, 'cache', 'sgx_2026-08.pdf'))
        self.assertEqual(self.m._read_iron_ore(blocks, self.MON), 4749207)



# ═══════════════════════════════════════════════════════════════════════════
# G. docs/CRON_WIRING.md 的闸门表 vs 代码真值
# ═══════════════════════════════════════════════════════════════════════════
# 这张表是「下一个人查闸门时会去看的地方」，而它漂过：2026-08-30 给 umc / ase 加
# EARLY_BY 那次没回写，表里那两行的闸门（9 / 10）比真值（4 / 8）晚了 5 与 2 天，
# 直到 2026-09-07 才被撞见。文档漂移的坏处不是「不准」，是**它看起来很准** ——
# 有人照着它算余量，得出的结论全是错的，而表本身不会报错。
#
# 判据就是 monthly_run 自己那条算术：闸门 = max(0, LAG − EARLY)。表里两张（§2.2 的
# 13 家交易所、§2.3 的其余 15 家）列数不同，所以按「最后一列 = 闸门」取，而不是按
# 固定下标 —— 后者正是本测试第一版写错的地方。
class TestCronWiringTableMatchesCode(unittest.TestCase):
    def test_every_gate_cell_matches(self):
        import re
        mr, rost = _load_once()
        doc_path = os.path.join(ROOT, 'docs', 'CRON_WIRING.md')
        with open(doc_path, encoding='utf-8') as f:
            doc = f.read()
        bad = []
        for t, lag in sorted(rost.LAG.items()):
            early = mr.EARLY_BY.get(t, (mr.EARLY, mr.EARLY))
            a, b = max(0, lag[0] - early[0]), max(0, lag[1] - early[1])
            m = re.search(r'^\| `' + t + r'`\s*\|(.*)$', doc, re.M)
            if m is None:
                bad.append(f'{t}: 闸门表里没有这一行')
                continue
            cells = [c.strip() for c in m.group(1).split('|')]
            got = cells[-2] if cells[-1] == '' else cells[-1]
            if t in mr.FACT_GATE:
                ok = '事实闸门' in got      # 不吃日历闸门的家，表里必须这么写
            else:
                nums = re.findall(r'\d+', got)
                ok = nums[:1] == [str(a)] if a == b else nums[:2] == [str(a), str(b)]
            if not ok:
                bad.append(f'{t}: 文档写 {got!r}，代码算出 {a}/{b}')
        self.assertEqual(bad, [], '闸门表与代码不一致：\n  ' + '\n  '.join(bad))



# ═══════════════════════════════════════════════════════════════════════════
# H. spike_cap 的端点护栏 —— 盲带哨兵
# ═══════════════════════════════════════════════════════════════════════════
# 这一组守的是一个**潜伏**缺陷：`spike_cap()` 的护栏一度写成 `end_hi > cap`（越界才抬），
# 而引擎真正的失败门槛在**像素**上 —— `assets/charts.js` 的 `spreadY()` 里
# `lo = M.t + 7`，而 `lines_endlabels` 的端点标签落笔在 `Y(值) + 3.2`。末点落在轴顶下方
# 不到 3.8px 时标签跌进 `lo` 之下，触发「从上边界顺排」的兜底：**整列端点标签被重排成
# 一摞**，与各自的线对不上号，而且没有任何东西报错。
# 换算成读数：cap 至少要比末点高约 1.63%（半栏）/ 1.64%（通栏）。`nice_max` 抬完仍落进
# 这条盲带的比例实测 6.37%；末点本身正好是整刻度（150 / 250 / 300 / 400 …）时**必然**触发。
# 现网 9 页一处都没命中，所以这里不能靠真产出当判据 —— 只能注入。
class TestSpikeCapEndGuard(unittest.TestCase):
    """引擎几何复刻 + 盲带注入。判据与 `assets/charts.js` 的行号一一对应。"""

    def setUp(self):
        import single
        self.S = single

    # ── charts.js 的最小复刻（只复刻本条要用的那几行）──
    @staticmethod
    def _spreadY_falls_back(ys, Mt, ph, gap):
        """charts.js:1291 `spreadY()` 的逐行复刻 → 是否走了顶边兜底。"""
        lo, hi = Mt + 7, Mt + ph + 3
        a = sorted(ys)
        for k in range(1, len(a)):
            if a[k] - a[k - 1] < gap:
                a[k] = a[k - 1] + gap
        over = (a[-1] - hi) if a else 0
        if over > 0:
            a = [y - over for y in a]
        return bool(a and a[0] < lo)

    def _endlabels_fall_back(self, ends, cap, y0, fs):
        S = self.S
        Mt = S._fscale(30, fs)                              # charts.js:814（capOn）
        ph = S._plot_h('lines_endlabels', fs, True, None)   # charts.js:783/823
        # charts.js:975 Y(v) + :1517/:1518 的 `+ 3.2`
        ys = [Mt + ph - ((v - y0) / (cap - y0)) * ph + 3.2 for v in ends]
        return self._spreadY_falls_back(ys, Mt, ph, S._fscale(9.6, fs))

    def test_plot_height_matches_engine(self):
        """绘区高：半栏 236.5 / 通栏 235.0（**不是** 268−30=238，FS=1 那一档不存在）。"""
        S = self.S
        self.assertAlmostEqual(S._plot_h('lines_endlabels', S.FS_MIN), 236.5, places=6)
        self.assertAlmostEqual(S._plot_h('lines_endlabels', S.FS_MAX), 235.0, places=6)
        self.assertLess(S._plot_h_min('lines_endlabels'), 235.0)   # 台阶右端更小

    def test_known_blind_band_cases_are_lifted(self):
        """红队实算的四例：末点 149/cap 150、396→400、300→300、250→250。

        判据分两半 —— ① 旧写法（`end_hi > cap`）不抬时引擎**真的**走顶边兜底；
        ② 新护栏解出来的 `need` 高于旧 cap（所以会抬）。
        """
        S = self.S
        head_px = 7 - 3.2
        ph = S._plot_h_min('lines_endlabels')
        for ends, cap in ([149., 20., 8.], 150.), ([396., 120.], 400.), \
                         ([300., 44., 12.], 300.), ([250., 90., 30., 9.], 250.):
            with self.subTest(cap=cap):
                end_hi = max(ends)
                self.assertFalse(end_hi > cap, '这一例本来就不在盲带里，样例选错了')
                for fs in (S.FS_MIN, S.FS_MAX):
                    self.assertTrue(self._endlabels_fall_back(ends, cap, 0.0, fs),
                                    f'cap={cap} FS={fs}：引擎复刻没走顶边兜底，样例失效')
                need = 0.0 + (end_hi - 0.0) / (1 - head_px / ph)
                self.assertGreater(need, cap, f'cap={cap}：新护栏没有抬 —— 盲带回来了')

    def test_integer_tick_endpoint_always_in_band(self):
        """末点本身正好落在 `nice_max` 的整刻度上时，旧写法**必然**留在盲带里。"""
        S = self.S
        ph = S._plot_h_min('lines_endlabels')
        for v in (10, 25, 100, 150, 250, 300, 400, 600, 800, 1000, 2500, 30000):
            with self.subTest(v=v):
                self.assertEqual(float(S.nice_max(v)), float(v))
                self.assertGreater(v / (1 - (7 - 3.2) / ph), float(S.nice_max(v)))

    def test_guard_output_clears_the_band(self):
        """护栏抬完之后，注入的那一批端点全部离顶边够远（引擎复刻不再兜底）。"""
        S = self.S
        head_px, ph = 7 - 3.2, S._plot_h_min('lines_endlabels')
        for end_hi in (149., 250., 298., 396., 1234.5, 98765.):
            with self.subTest(end_hi=end_hi):
                cap = float(S.nice_max(end_hi / (1 - head_px / ph)))
                for fs in (S.FS_MIN, S.FS_MAX):
                    self.assertFalse(
                        self._endlabels_fall_back([end_hi, end_hi * .3, end_hi * .08],
                                                  cap, 0.0, fs),
                        f'end_hi={end_hi} FS={fs}：抬完仍然走顶边兜底')

    def test_real_spike_cap_clears_the_band(self):
        """**注入真的 `spike_cap()`**：末点 298（栅栏内最大值）+ 中段一个 3,000 的尖刺。

        旧护栏给出 `nice_max(298) = 300`，末点离轴顶只剩 0.67% —— 落在盲带里。
        这一条直接把造出来的 exhibit 喂进 `Page.spike_cap()`，拿引擎复刻验它的产出：
        护栏必须把上界抬到兜底门槛之外，而且那一个尖刺仍然是越界点（截轴没白截）。
        """
        S = self.S
        vals = [80 + (i * 7) % 180 for i in range(60)]
        vals[30], vals[-1] = 3000., 298.
        ex = {'n': 4, 'kind': 'lines_endlabels', 'yfloor': 0,
              'xlabels': [f'M{i}' for i in range(60)],
              'series': [{'name': 'A', 'values': [float(v) for v in vals]},
                         {'name': 'B', 'values': [float(40 + (i * 5) % 120)
                                                  for i in range(60)]}]}
        page = S.Page.__new__(S.Page)
        page.ticker, page.cap_ns = 'band', []
        zh = page.spike_cap(4, ex, [{'fmt': 'f0c', 'unit': 'units'}])
        self.assertTrue(zh and ex.get('ycap'), 'spike_cap 没有截轴 —— 样例失效')
        self.assertGreater(ex['ycap'], float(S.nice_max(298.)),
                           '上界停在 nice_max(末点) 上 —— 端点护栏的盲带回来了')
        self.assertEqual([v for s in ex['series'] for v in s['values'] if v > ex['ycap']],
                         [3000.], '越界点不再只是那个尖刺 —— 上界抬过头了')
        ends = [s['values'][0] for s in ex['series']] + \
               [s['values'][-1] for s in ex['series']]
        for fs in (S.FS_MIN, S.FS_MAX):
            self.assertFalse(self._endlabels_fall_back(ends, float(ex['ycap']), 0.0, fs),
                             f'FS={fs}：截完仍然会把整列端点标签重排成一摞')

    def test_spike_cap_rejects_a_third_kind(self):
        """`kind` 不是 lines_endlabels / lines 时必须当场停机（那句 raise 不是死代码）。"""
        S = self.S
        page = S.Page.__new__(S.Page)
        page.ticker = 't'
        with self.assertRaises(S.SpecError):
            page.spike_cap(9, {'kind': 'gs_bar', 'series': [], 'xlabels': []},
                           [{'fmt': 'f0c', 'unit': 'u'}])



# ═══════════════════════════════════════════════════════════════════════════
# I. 2026-09 给 build/single.py 加的三样东西 —— 它们失败时都**不出声**
# ═══════════════════════════════════════════════════════════════════════════
# 判据照 README「第四类：不出声的失败」那一节：
#     「它连续失败十天，和成功十天，在日志里长得一样吗？一样，就缺一道护栏。」
#
# · `no_yoy` 落点守卫：守卫本身若失效，声明被吞、payload 一字不改、rc=0、
#   五道闸门全绿 —— 正是它写出来要消灭的那个形状。而且它在两轮里**被漏了两次**
#   （先漏 decomp 四个列位，再漏「mix 落空时分项回到桶里」这条路由），
#   两次都是人复核抓到的，没有任何自动判据会响。
# · `prior12()`：verify_pages 只查 gs_bar 有没有 `avg12`，**不查值**。
#   切片从 [-13:-1] 改成 [-12:] 照样返回一个数、照样过闸门，虚线悄悄挪一格。
# · `monthly_total(bucket=)`：分岔的是一句印在图注里的口径断言，没有闸门读它；
#   而它的年度支现在**零活体覆盖**（全仓再没有 spec 传 weight_col / *_total_col）。
class TestNoYoyGuard(unittest.TestCase):
    """`no_yoy` 只有 `ex_single` 读得到 —— 写在别处必须硬失败，写对了必须生效。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls.spec = single.load_spec('jpx')

    def _spec(self):
        import copy
        return copy.deepcopy(self.spec)

    def test_norm_col_call_sites_still_seven(self):
        """`_norm_col` 的调用点数量 —— 守卫注释自称「共 7 个」，这是那句话的看门人。

        加了第 8 个调用点却忘了扩守卫，是这道守卫最可能的失效方式（已发生过一次：
        decomp 的四个列位就是这么漏的）。用 AST 数，不用 grep —— 注释里出现
        `_norm_col(` 不算调用。
        """
        import ast
        src = open(os.path.join(ROOT, 'build', 'single.py'), encoding='utf-8').read()
        n = sum(1 for node in ast.walk(ast.parse(src))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == '_norm_col')
        self.assertEqual(n, 7,
                         f'_norm_col 的调用点从 7 个变成了 {n} 个 —— '
                         f'新增/删除一个落点时必须同步改 Page.__init__ 里的 no_yoy 守卫'
                         f'与 docs/SINGLE_SPEC.md §4 那一行的**左右两格**')

    def test_blocks_headline(self):
        sp = self._spec()
        sp['headline'][0]['no_yoy'] = True
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('headline', str(cm.exception))

    def test_blocks_stock_col(self):
        sp = self._spec()
        for g in sp['groups']:
            for c in g['cols']:
                if c['col'] == 'mktcap_eom_jpytn':
                    c['no_yoy'] = True
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('stock=True', str(cm.exception))

    def test_blocks_multi_col_bucket(self):
        """2 列以上的同单位桶走 ex_lines / ex_heat，都不读这个开关。"""
        sp = self._spec()
        for g in sp['groups']:
            for c in g['cols']:
                if c['col'] == 'adv_deriv_index_lgeq_kcontracts':
                    c['no_yoy'] = True
        with self.assertRaises(self.S.SpecError):
            self.S.Page(sp)

    def test_blocks_mix_total_and_parts(self):
        sp = self._spec()
        for g in sp['groups']:
            if g.get('mix'):
                for c in g['cols']:
                    if c['col'] == g['mix']['total']:
                        c['no_yoy'] = True
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('mix', str(cm.exception))

    def test_blocks_decomp_columns(self):
        """decomp 的四个列位也走 _norm_col —— 语法上写得进去，而 ex_decomp 不读它。

        漏了这一条时的实测症状：rc=0、payload 逐字节不变、五道闸门全绿。
        """
        for key in ('value', 'qty'):
            with self.subTest(key=key):
                sp = self._spec()
                sp['decomp'][0][key]['no_yoy'] = True
                with self.assertRaises(self.S.SpecError) as cm:
                    self.S.Page(sp)
                self.assertIn('decomp', str(cm.exception))

    def test_blocks_when_mix_may_fall_through(self):
        """mix 那张图没出成时，被「声明扣掉」的分项会回到桶里 —— 桶一超 MAX_LINES
        就走 ex_heat（画同比）。守卫必须按**最坏情形**分桶，不能照抄 payload()
        那份「按真画出来的图扣列」的算法（两处天生不同源）。
        """
        sp = self._spec()
        unit = 'k contracts/day'
        cols = [{'col': c, 'zh': z, 'unit': unit, 'fmt': 'f1'} for c, z in [
            ('adv_deriv_total_raw_kcontracts', 'T'),
            ('adv_deriv_index_raw_kcontracts', 'P1'),
            ('adv_deriv_rates_raw_kcontracts', 'P2'),
            ('adv_deriv_cmdty_raw_kcontracts', 'P3'),
            ('adv_n225_futures_kcontracts', 'P4'),
            ('adv_n225_mini_kcontracts', 'P5'),
            ('adv_topix_futures_kcontracts', 'F'),
        ]]
        cols[-1]['no_yoy'] = True          # ← 只有它带开关，且它不是 mix 的成员
        drop = {'衍生品分类 ADV（原始张数，仅供口径对照）',
                '迷你化：大型合约 vs mini（原始张数）',
                '衍生品总量：大合约当量 vs 原始张数'}
        sp['groups'] = [g for g in sp['groups'] if g['zh'] not in drop]
        sp['groups'].append({'zh': 'G_fallthrough', 'cols': cols, 'mix': {
            'total': 'adv_deriv_total_raw_kcontracts',
            'parts': [c['col'] for c in cols[1:6]],
            'residual_zh': '其他', 'abs_stack': True}})
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('mix 落空', str(cm.exception))

    def test_allows_and_takes_effect_on_single_bucket(self):
        """写对了必须**生效**：撤掉 yoy 与右轴、改画 avg12。只拦不生效等于白拦。"""
        page = self.S.Page(self._spec())
        pay, why = page.payload()
        self.assertIsNotNone(pay, f'jpx payload 没产出来：{why}')
        # `_cols` 是内部字段，落盘前会被剔掉 —— 按标题认这张图。
        ex = [e for e in pay['exhibits']
              if e.get('title', '').endswith('当月公开募集件数')]
        self.assertEqual(len(ex), 1)
        self.assertIsNone(ex[0].get('yoy'))
        self.assertIsNone(ex[0].get('ylab2'))
        self.assertIsNotNone(ex[0].get('avg12'))

    def test_all_live_specs_still_construct(self):
        """过杀的唯一整页护栏：现网每一页都必须还能构造出来。"""
        import glob as _glob
        for f in sorted(_glob.glob(os.path.join(ROOT, 'build', 'specs', '*.py'))):
            t = os.path.splitext(os.path.basename(f))[0]
            if t.startswith('_'):
                continue
            with self.subTest(ticker=t):
                self.S.Page(self.S.load_spec(t))

    def test_bench_absent_does_not_trip_guard(self):
        """不给 bench 时两键归一化成 None —— 守卫的 isinstance 那半句不是冗余。"""
        d = self.S._norm_decomp(
            {k: v for k, v in self.spec['decomp'][0].items()}, 'decomp[0]')
        self.assertIsNone(d['bench_value'])
        self.assertIsNone(d['bench_qty'])
        self.S.Page(self._spec())          # 不抛 TypeError


class TestPrior12(unittest.TestCase):
    """`avg12` 那条虚线的值。verify_pages 只查它在不在，**不查它是多少**。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single

    def test_slice_is_prior_twelve_not_trailing_twelve(self):
        """口径是「最新月**之前**的 12 个月」= [-13:-1]，不是 [-12:]。

        两种切法都返回一个数、都过闸门，差别只有虚线挪一格 —— 所以这条要同时
        断言「等于前者」与「不等于后者」，把「口径写错也算过」堵死。
        """
        v = [float(i) for i in range(1, 27)]        # 1..26
        got = self.S.prior12(v)
        self.assertAlmostEqual(got, sum(v[-13:-1]) / 12.0, places=9)
        self.assertNotAlmostEqual(got, sum(v[-12:]) / 12.0, places=9)

    def test_excludes_latest_month(self):
        """最新月是 NaN 而之前 12 个月有值 → 仍算得出（定义就是不含最新月）。"""
        import numpy as np
        v = [float(i) for i in range(1, 26)] + [float('nan')]
        self.assertIsNotNone(self.S.prior12(v))
        self.assertTrue(np.isfinite(self.S.prior12(v)))

    def test_all_nan_returns_none(self):
        self.assertIsNone(self.S.prior12([float('nan')] * 20))

    def test_matches_lpla_implementation(self):
        """四处同源：与 build/lpla.py 的 avg_prior12 同口径（同样 round 到 6 位）。"""
        import importlib.util
        sp = importlib.util.spec_from_file_location(
            'lpla_mod', os.path.join(ROOT, 'build', 'lpla.py'))
        try:
            mod = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(mod)
        except Exception:                       # noqa: BLE001
            self.skipTest('build/lpla.py 需要 pandas 之外的依赖，跳过跨实现比对')
        if not hasattr(mod, 'avg_prior12'):
            self.skipTest('build/lpla.py 没有 avg_prior12')
        import pandas as pd
        v = [float(i) * 1.7 for i in range(1, 27)]
        self.assertAlmostEqual(self.S.prior12(v),
                               mod.avg_prior12(pd.Series(v)), places=6)


class TestMonthlyTotalBucket(unittest.TestCase):
    """`monthly_total()` 的口径断言按 bucket 分岔 —— 没有任何闸门读那句话。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls.page = single.Page(single.load_spec('jpx'))

    def _how(self, bucket):
        c = {'col': 'adt_cash_dom_stocks_jpytn', 'zh': '内国株成交额',
             'unit': '¥tn/day', 'fmt': 'f1', 'stock': False,
             'scale': 1.0, 'ratio': None, 'no_yoy': False}
        _s, how = self.page.monthly_total(c, None, None, 'daily_avg',
                                          'test', bucket=bucket)
        return how

    def test_monthly_bucket_has_no_equal_weight_warning(self):
        """月度桶一格就是一个月，全程不跨月相加 —— 那句代价在这张图上是假的。"""
        how = self._how('monthly')
        self.assertNotIn('等权', how)          # 年度支那句代价不许出现在月度图上
        self.assertIn('不做任何跨月相加', how)   # 月度支必须把「为什么不需要」说出来
        # 「权重偏差」这四个字在月度支里是被**否定**掉的（「也没有…权重偏差」），
        # 所以不能断言它不出现 —— 只能断言它不是以「带着一个…偏差」的肯定形式出现。
        self.assertNotIn('带一个', how)

    def test_year_bucket_keeps_equal_weight_warning(self):
        """年度桶必须仍然把话说满。两支互斥，否则分岔等于没分。"""
        how = self._how('year')
        self.assertIn('等权', how)

    def test_series_returned_unchanged_in_monthly_bucket(self):
        """月度桶不做任何还原：返回的就是原序列，没乘任何东西。"""
        import numpy as np
        c = {'col': 'adt_cash_dom_stocks_jpytn', 'zh': 'x', 'unit': 'u',
             'fmt': 'f1', 'stock': False, 'scale': 1.0, 'ratio': None,
             'no_yoy': False}
        s, _ = self.page.monthly_total(c, None, None, 'daily_avg',
                                       'test', bucket='monthly')
        base = self.page.ser(c)
        self.assertTrue(np.allclose(s.dropna().values, base.dropna().values))


class TestMixAbsStack(unittest.TestCase):
    """`abs_stack` 的绝对值堆叠：柱高声称等于合计，所以负分项必须硬失败。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single

    def test_negative_segment_is_rejected(self):
        """引擎把正段自 0 上堆、负段削成零高度不画 ⇒ 柱顶落在正段之和上，
        而「各段之和 = 合计」那道收尾自检**照样通过**（一负一正互相抵消）。
        verify_pages 的负段 ERROR 只覆盖 gs_bar，接不住 stacked_dual。
        """
        page = self.S.Page(self.S.load_spec('jpx'))
        g = [x for x in page.groups if x['zh'] == '东证现货成交'][0]
        i = page.df.index[-1]
        page.df.loc[i, 'adt_cash_etfreit_jpytn'] = \
            -page.df.loc[i, 'adt_cash_etfreit_jpytn']
        page.df.loc[i, 'adt_cash_stocks_jpytn'] = (
            page.df.loc[i, 'adt_cash_total_jpytn']
            - page.df.loc[i, 'adt_cash_etfreit_jpytn'])
        with self.assertRaises(self.S.SpecError) as cm:
            page.mix_pair(9, g)
        self.assertIn('负值', str(cm.exception))

    def test_abs_stack_excludes_rhs_share(self):
        """abs_stack 不出 100% 占比那张 ⇒ rhs_share / share_note 是死配置。"""
        with self.assertRaises(self.S.SpecError):
            self.S._norm_mix({'total': 'a', 'parts': ['b'],
                              'abs_stack': True, 'rhs_share': 'b'}, 'test')


class TestMixTotalPlainPerGroup(unittest.TestCase):
    """「同一列不许被画成两根柱」—— 「被吃掉」必须逐组算，不能先并成全页集合再减。

    `payload()` 里的 `eaten` 是每组各自一份：一组的常规分桶只看**这一组自己的**
    mix 吃没吃这一列。守卫若按全页并集减，同一列声明在两组、只被其中一组的 mix
    吃掉时，它会从「常规列」里被整页减掉 ⇒ 守卫放行 ⇒ 另一组照样给它画一张常规图。
    现网每一页仍然构造得出来，由 `TestNoYoyGuard.test_all_live_specs_still_construct` 守。
    """

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls.spec = single.load_spec('jpx')

    def test_eaten_in_one_group_still_plain_in_another(self):
        import copy
        sp = copy.deepcopy(self.spec)
        g = [x for x in sp['groups'] if x.get('mix')][0]
        tot = g['mix']['total']
        col = [c for c in g['cols'] if c['col'] == tot][0]
        # 同一列在第二组里再声明一次，第二组没有 mix ⇒ 在第二组是常规列。
        sp['groups'].append({'zh': 'G_plain', 'cols': [copy.deepcopy(col)]})
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        msg = str(cm.exception)
        self.assertIn('既是某条 mix 的 total', msg)
        self.assertIn(tot, msg)
        self.assertIn('G_plain', msg)       # 报错要点名是哪一组把它当常规列


class TestMixRuleNote(unittest.TestCase):
    """页尾「图型选择规则」⑤ 按**真画出来的图**说话（`Page.mix_rule_zh`）。

    从前那句按「页上有没有 stacked_dual」无条件印「声明了 mix 的组出两张」，
    而 abs_stack 那张绝对值堆叠柱也是 stacked_dual —— /jpx/ 唯一的 mix 就是它：
    页面上一张图，页尾说两张。四道闸门看结构与数值，看不见散文。
    """

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single

    def _rule(self, t):
        page = self.S.Page(self.S.load_spec(t))
        pay, why = page.payload()
        self.assertIsNotNone(pay, f'{t} payload 没产出来：{why}')
        hit = [s for s in pay['notes'] if isinstance(s, str) and '图型选择规则' in s]
        self.assertEqual(len(hit), 1)
        return page, pay, hit[0]

    @staticmethod
    def _d(gz, abs_=False, total=False, share=False, stack=False, folded=False):
        return {'gz': gz, 'abs': abs_, 'total': total, 'share': share,
                'stack': stack, 'folded': folded}

    def _ledger_page(self, ledger):
        page = self.S.Page(self.S.load_spec('jpx'))
        page.mix_drawn, page.mix_folded = ledger, []
        return page

    def test_abs_stack_page_says_one_chart(self):
        page, pay, s = self._rule('jpx')
        abs_gz = [g['zh'] for g in page.groups if g.get('mix') and g['mix']['abs_stack']]
        self.assertTrue(abs_gz, 'jpx 不再有 abs_stack 的组 —— 这条换一页测')
        self.assertTrue(all(not g['mix']['abs_stack'] for g in page.groups
                            if g.get('mix') and g['zh'] not in abs_gz))
        self.assertNotIn('出<b>两张</b>', s)
        self.assertIn('只出<b>一张</b>', s)
        for gz in abs_gz:
            self.assertIn(f'「{gz}」', s)

    def test_two_chart_page_unchanged(self):
        """普通 mix 的页：规则句仍是「两张」，折叠档的例外照旧由 mix_folded_zh 点名。"""
        page, _pay, s = self._rule('tmx')
        self.assertIn('出<b>两张</b>', s)
        self.assertNotIn('abs_stack', s)
        self.assertEqual(bool(page.mix_folded), '⚠️ <b>例外</b>' in s)

    def test_nothing_drawn_says_nothing(self):
        self.assertEqual(self._ledger_page([]).mix_rule_zh(), '')
        self.assertEqual(self._ledger_page([self._d('A')]).mix_rule_zh(), '')

    def test_mixed_page_names_both_kinds(self):
        s = self._ledger_page([self._d('A', total=True, share=True),
                               self._d('B', abs_=True, stack=True)]).mix_rule_zh()
        self.assertIn('出<b>两张</b>', s)
        self.assertIn('但写了 <code>abs_stack</code> 的组（「B」）只出<b>一张</b>', s)
        self.assertNotIn('「A」', s)
        self.assertNotIn('没出齐', s)

    def test_shortfall_is_named_not_swallowed(self):
        """画不成（不是有意不出）的组不许藏在「两张 / 一张」那句规则后面。"""
        s = self._ledger_page([self._d('A', total=True, share=True),
                               self._d('C', total=True),
                               self._d('B', abs_=True, stack=True),
                               self._d('D', abs_=True)]).mix_rule_zh()
        self.assertIn('「C」只出了合计柱', s)
        self.assertIn('「D」那张绝对值堆叠柱没画成', s)
        self.assertIn('本轮未出的派生图', s)


# ═══════════════════════════════════════════════════════════════════════════
# J. exchanges12 的缺月闸门 —— gate_holes()
# ═══════════════════════════════════════════════════════════════════════════
# 2026-09 加。这道闸门原来是「窗口内有洞就整页 raise」，把 /exchanges12/ 从 31c335c
# 起冻了整整四天：ASX 2020-01 的官方印错值被 series/ 那边主动置空，页面却因此再也
# 构建不出来，于是线上那一版**恰好还印着要删掉的那个错值**。改成「登记才放行」之后，
# 放行的口子必须自己有网兜着 —— 它现在是全页唯一能抓到源列损坏的地方。
#
# 四条各守一个方向：未登记的必须炸（口子不能变成默认放行）、登记过的必须放行
#（否则等于没改）、登记但洞已经补上必须炸（页面不能继续解释一个不存在的空格）、
# 病因指错腿必须炸（图注会把空格归给一条其实有值的腿）。
class TestExchanges12HoleGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        cls.pd = pd
        import exchanges12 as E
        cls.E = E
        idx = pd.period_range('2019-01', '2019-06', freq='M')
        s = pd.Series(1.0, index=idx)
        holed = s.copy()
        holed[pd.Period('2019-03')] = float('nan')
        # 两个成员各一块；'asx' 的 ASX_ETO 在 2019-03 缺值，'cme' 齐备。
        cls.BLK = {'asx': {'ASX_ETO': holed}, 'cme': {'CME_ALL': s}}
        cls.WHY = ('ASX_ETO', '测试用病因')

    def test_registered_hole_passes(self):
        got = self.E.gate_holes({'asx': ['2019-03']}, self.BLK, 'Jan-19', 'Jun-19',
                                known={('asx', '2019-03'): self.WHY})
        self.assertEqual(got, [('asx', '2019-03')])

    def test_unregistered_hole_raises(self):
        """没登记的洞必须炸 —— 否则这道闸门等于被拆了。"""
        with self.assertRaises(SystemExit) as cm:
            self.E.gate_holes({'asx': ['2019-03']}, self.BLK, 'Jan-19', 'Jun-19', known={})
        self.assertIn('未登记', str(cm.exception))

    def test_stale_registration_raises(self):
        """洞补上了而登记还在 ⇒ 炸，逼人把图注里那句解释一起删掉。"""
        with self.assertRaises(SystemExit) as cm:
            self.E.gate_holes({}, self.BLK, 'Jan-19', 'Jun-19',
                              known={('asx', '2019-03'): self.WHY})
        self.assertIn('已经不是洞', str(cm.exception))

    def test_noncanonical_month_says_format_not_stale(self):
        """月份写成 '2019-3' / Period 时要报格式错，不能报「数据补上了」。

        stale 判据是纯字符串比对，非规范写法会静静落进那个分支，把人指去翻 series/，
        而问题在登记这一行自己的写法上 —— Period 打印出来还和字符串一模一样。
        """
        for bad in ('2019-3', self.pd.Period('2019-03', freq='M')):
            with self.assertRaises(SystemExit) as cm:
                self.E.gate_holes({'asx': ['2019-03']}, self.BLK, 'Jan-19', 'Jun-19',
                                  known={('asx', bad): self.WHY})
            msg = str(cm.exception)
            self.assertIn('YYYY-MM', msg)
            self.assertNotIn('数据补上了', msg)

    def test_reason_pointing_at_a_healthy_block_raises(self):
        """病因指到一条其实有值的腿 ⇒ 炸。图注会照着这个块名点名，指错就是印错话。"""
        BLK = {'asx': {'ASX_ETO': self.BLK['asx']['ASX_ETO'],
                       'ASX_DERIV': self.pd.Series(1.0, index=self.BLK['cme']['CME_ALL'].index)}}
        with self.assertRaises(SystemExit) as cm:
            self.E.gate_holes({'asx': ['2019-03']}, BLK, 'Jan-19', 'Jun-19',
                              known={('asx', '2019-03'): ('ASX_DERIV', '指错腿')})
        self.assertIn('指错了腿', str(cm.exception))


# ═══════════════════════════════════════════════════════════════════════════
# K. exchanges12 的三个同比函数 —— pct_change 不许前向填充
# ═══════════════════════════════════════════════════════════════════════════
# 同一次改动挖出来的真缺陷：pandas ≤ 2.x 的 pct_change 默认 fill_method='pad'，
# 序列中间缺一个月**不会**留空，而是拿上一个月冒充它算出一个假读数 —— 不报错、
# 不留 null。这正是「洞看不出来」的那种坏法，而且它是本页那道 hull 自检
#（加权平均必落在分量 min/max 之间）唯一一次真的被撞响的原因。
# 三个函数各测一次：留空的必须是 null，不能是数。
class TestExchanges12NoPadOnPctChange(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        import exchanges12 as E
        cls.E, cls.pd = E, pd
        idx = pd.period_range('2019-01', '2021-12', freq='M')
        s = pd.Series(range(1, len(idx) + 1), index=idx, dtype=float)
        s[pd.Period('2020-01')] = float('nan')
        cls.s = s

    def test_yoy_leaves_the_hole_empty(self):
        v = self.E.yoy(self.s)
        for m in ('2020-01', '2021-01'):
            self.assertTrue(self.pd.isna(v[self.pd.Period(m)]),
                            f'{m} 被前向填充算出了 {v[self.pd.Period(m)]}')

    def test_mom_leaves_the_hole_empty(self):
        v = self.E.f_mom(self.s)
        for m in ('2020-01', '2020-02'):
            self.assertTrue(self.pd.isna(v[self.pd.Period(m)]),
                            f'{m} 被前向填充算出了 {v[self.pd.Period(m)]}')

    def test_ttm_yoy_leaves_the_hole_empty(self):
        """滚动合计口径上，一格缺值影响其后 12 个月，同比再影响 12 个月。"""
        v = self.E.ttm_yoy(self.s)
        for m in ('2020-12', '2021-01'):
            self.assertTrue(self.pd.isna(v[self.pd.Period(m)]),
                            f'{m} 被前向填充算出了 {v[self.pd.Period(m)]}')


# ═══════════════════════════════════════════════════════════════════════════
# L. /sgx/ 改版（页面所有者 2026-09-12 的四条指令）—— 三个底座新开关 + 页面本身
# ═══════════════════════════════════════════════════════════════════════════
# 所有者的四条指令（图号一律是改版前的「原 Exhibit N」，明文冻结，不跟着新编号动）：
#   ① 删开篇四张（原 Exhibit 2–5：SDAV / DDAV 的分位带图与单月同比图）；
#   ② 原 Exhibit 11 / 12 / 15 / 16 四张折线改成「合计柱 + 100% 占比堆叠」；
#   ③ 原 Exhibit 25（衍生品月末未平仓）挪到原 Exhibit 11 的替代图之后；
#   ④ 新增一张 SGX 业务占比（衍生品当月成交按资产类别切），与 ② 那张共用分母。
# 底座为此加三个开关：`headline_style='none'`、`groups[].stock_inline`、
# `groups[].mix.alt_splits` + `split_zh`。三个都是**加性、可选、缺省逐字节不变**，
# 与 `spike_cap` / `ratio_rhs` / `after_group` 同一条纪律 —— 也会吃同一类亏：
#
#   · **开关失效时一声不出。** 'none' 悄悄落回 band_yoy ⇒ 页面多出四张图、闸门全绿；
#     stock_inline 被吞 ⇒ 那张存量图照样出、只是排回季节性之后，图还在、数没错，
#     只有对着页面数图号的人看得出所有者要的位置没生效（`after_group` 立锚点校验
#     时记过同一笔账）；alt_splits 只画了主切法 ⇒ 第二张占比图凭空不见。
#   · **页尾散文跟着变假。** 'none' 下「汇总表读法」那句只有 band / bar_yoy 两支，
#     哪一支都在指一张页面上没有的开篇图；一组出三张图时 ⑤「声明了 mix 的组出两张」
#     与折叠档的「只出占比那一张」当场失真。四道闸门看结构与数值闭合，看不见这几句话。
#
# 测法分两半，各守一件事：
#   · 前三组守**开关本身**，**不读 build/specs/sgx.py**（那份文件与本组同时在改写）：
#     在 `series/sgx.csv` 上现搭一份最小 spec（`_sgx_fixture()`），每条反例只改一处。
#     反例一律带「线索词」断言（`_raises_spec`），挡的是「SpecError 抛了、但是被别的
#     护栏抛的」；夹具依赖的数据事实（各切法残差逐月非负、USD/CNH ≤ 外汇期货合计）
#     由同组的正例在运行时现验 —— 数据哪天破了是正例先红，反例不会跟着空过。
#     要借「合计是存量列的 mix」与现网标题形状时，只借 sgx 以外的活 spec。
#   · TestSgxOwnerLayout 守**所有者要的那张页面**：只读活的 sgx spec、建到临时目录。
#     本文件是 preflight 闸门、跑在抓数之前，所以全组**不读也不写 data/**。
import contextlib  # noqa: E402
import copy        # noqa: E402
import csv         # noqa: E402
import io          # noqa: E402
import shutil      # noqa: E402
import tempfile    # noqa: E402
import warnings    # noqa: E402

_SGX_U = 'contracts/month'
_TOT, _FUT, _OPT, _SWP = ('deriv_vol_contracts', 'deriv_futures_vol_contracts',
                          'deriv_options_vol_contracts', 'deriv_swaps_vol_contracts')
_EQX, _FXF, _CMD = ('vol_equity_index_futures_contracts', 'vol_fx_futures_contracts',
                    'vol_commodities_contracts')
_A50, _N225, _MSG, _CNH = ('vol_a50_futures_contracts', 'vol_nikkei225_futures_contracts',
                           'vol_msci_singapore_futures_contracts',
                           'vol_usdcnh_futures_contracts')
_LINE_KINDS = ('lines', 'lines_endlabels', 'heat_matrix')
# 夹具的组名带天干前缀是故意的：撞不上活页的组名，报错里一眼认得出是夹具。
_GZ_SEC, _GZ_DD, _GZ_DER, _GZ_AST, _GZ_CAP = ('甲·证券成交', '乙·衍生品日均', '丙·衍生品',
                                              '丁·资产类别', '戊·市值')
_SPLIT_ZH = '按期货 / 期权 / 掉期'
_ALT_ASSET = {'zh': '按资产类别', 'parts': [_EQX, _FXF, _CMD], 'residual_zh': '其他'}
_ALT_EQ = {'zh': '股指 vs 其余', 'parts': [_EQX], 'residual_zh': '股指以外'}


def _c(col, zh, unit=_SGX_U, **kw):
    """夹具里的一条列配置。fmt 一律 f0c —— 本组不测格式器。"""
    d = {'col': col, 'zh': zh, 'unit': unit, 'fmt': 'f0c'}
    d.update(kw)
    return d


def _sgx_fixture():
    """`series/sgx.csv` 上的最小 spec，形状照着活页挑。

    头条 = SDAV + DDAV，两条都在组里声明过；「丙·衍生品」= 合计 / 期货 / 期权 + 月末未平仓
    （存量）；三条资产类别合计另成「丁」组；「戊·市值」是一组纯存量，当对照 ——
    它**不开** stock_inline，用来证明开关只挪声明了它的那一组。
    """
    return {
        'ticker': 'sgx', 'name': 'SGX guard fixture', 'title': '夹具', 'csv': 'sgx.csv',
        'ccy': 'SGD', 'source': 'Source: test fixture over series/sgx.csv',
        'headline': [_c('sdav_sgdmn', '证券市场 SDAV', 'S$mn/day'),
                     _c('ddav_contracts', '衍生品 DDAV', 'contracts/day')],
        'groups': [
            {'zh': _GZ_SEC, 'cols': [_c('sdav_sgdmn', '日均成交额 SDAV', 'S$mn/day')]},
            {'zh': _GZ_DD, 'cols': [_c('ddav_contracts', '日均成交 DDAV', 'contracts/day')]},
            {'zh': _GZ_DER, 'cols': [
                _c(_TOT, '当月成交合计'), _c(_FUT, '其中：期货'), _c(_OPT, '其中：期权'),
                _c('deriv_oi_contracts', '月末未平仓', 'contracts', stock=True)]},
            {'zh': _GZ_AST, 'cols': [
                _c(_EQX, '股指期货合计'), _c(_FXF, '外汇期货合计'),
                _c(_CMD, '商品合计（不含加密）')]},
            {'zh': _GZ_CAP, 'cols': [_c('mktcap_sgdmn', '月末总市值', 'S$mn', stock=True)]},
        ],
    }


def _decomp_fixture(after_group):
    """一条年度桶的量价分解（SGX 证券侧那一对同口径列），就地排在 after_group 之后。"""
    return {'zh': '证券市场成交额', 'kind': 'share_price', 'granularity': 'monthly_total',
            'value': _c('sec_turnover_sgdmn', '当月成交额', 'S$mn/month'),
            'qty': _c('sec_turnover_mnshares', '当月成交股数', 'mn shares/month'),
            'price_zh': '加权平均成交价', 'price_unit': 'S$/share', 'price_fmt': 'f3',
            'years': 4, 'after_group': after_group}


def _grp(spec, zh):
    return next(g for g in spec['groups'] if g['zh'] == zh)


def _live_tickers(exclude=()):
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'build', 'specs', '*.py'))):
        t = os.path.splitext(os.path.basename(f))[0]
        if not t.startswith('_') and t not in exclude:
            out.append(t)
    return out


def _page_payload(spec, series_dir=None):
    """spec（深拷贝）→ (page, payload)。门槛没到直接判失败：夹具是全历史，不存在「等数据」。"""
    import single as S
    page = (S.Page(copy.deepcopy(spec)) if series_dir is None
            else S.Page(copy.deepcopy(spec), series_dir))
    pay, why = page.payload()
    if pay is None:
        raise AssertionError(f'门槛没到：{why}')
    return page, pay


def _json(pay):
    return json.dumps(pay, ensure_ascii=False, sort_keys=True)


def _titles(pay):
    return [(e['kind'], e['title']) for e in pay['exhibits']]


def _idx(pay, title, kind=None):
    """标题逐字等于 title（且 kind 相符）的那几张的下标。"""
    return [i for i, e in enumerate(pay['exhibits'])
            if e['title'] == title and (kind is None or e['kind'] == kind)]


def _season0(pay):
    """第一张季节性图的下标（④ 段的起点）；一张都没有返回 None。"""
    return next((i for i, e in enumerate(pay['exhibits']) if e['kind'] == 'seasonality'), None)


def _in_group(e, gz):
    return e['title'].startswith(gz + '：')


def _gpos(order, title):
    """标题属于 spec 里的第几组（最长组名前缀匹配 —— 组名本身可以带「：」）；认不出返回 None。"""
    best = None
    for j, gz in enumerate(order):
        if title.startswith(gz + '：') and (best is None or len(gz) > len(order[best])):
            best = j
    return best


def _n_head_charts(spec):
    """开篇段有几张图。只给 band_yoy / bar_yoy 两种既有写法记数，'none' 记 0。"""
    per = {'band_yoy': 2, 'bar_yoy': 1, 'none': 0}[spec.get('headline_style') or 'band_yoy']
    return per * len(spec['headline'])


_EXREF = re.compile(r'Exhibit\s*(\d+(?:\s*(?:[、,，/]|与|和|及|或)\s*(?:Exhibit\s*)?\d+)*)')


def _ex_refs(text):
    """一段散文里指到的全部图号（认「Exhibit 5、6」「Exhibit 5 与 Exhibit 6」几种写法）。

    只拿来做「必须包含」的断言：误收一个数（「Exhibit 5，6 个月」）只会多、不会漏。
    """
    out = set()
    for m in _EXREF.finditer(text or ''):
        out |= {int(x) for x in re.findall(r'\d+', m.group(1))}
    return out


def _notes_txt(pay):
    return '\n'.join(str(x) for x in pay.get('notes') or [])


def _build_log(spec, out_dir):
    """跑一遍真 `build()`（写到临时目录），把 stdout / stderr / warnings 全收回来。

    契约只说「打一行构建日志」，没说走 print 还是 warnings、在 Page 里还是 build() 里 ——
    三个出口都收，免得用例替实现挑了出口。
    """
    import single as S
    buf = io.StringIO()
    with warnings.catch_warnings(record=True) as got, \
            contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        warnings.simplefilter('always')
        S.build(copy.deepcopy(spec), out_dir=out_dir, quiet=False)
    return buf.getvalue() + ''.join(f'{w.message}\n' for w in got)


def _raises_spec(tc, spec, tokens, series_dir=None, unknown_ok=False):
    """构造 + 组装，必须 SpecError；且报错里至少出现一个线索词。返回报错全文。

    线索词不是在考措辞（契约没定措辞）：反例只改了一处，报错里连那一处的名字都没有，
    多半是被**别的**护栏拦下的 —— 那这条用例就没测到它要测的那道闸。
    Page() 与 payload() 包在同一个 assertRaises 里：契约没定哪条校验落在构造期、
    哪条落在组装期（主切法今天是两处都有）。

    ⚠️ 「有未知字段」那一句**默认不算数**（`unknown_ok=False`）。新键还没登记进白名单时，
    `_check_keys` 的报错恰好把键名印出来 —— 线索词照样对得上，反例在一行实现都没有的
    代码上成片全绿（本组写完在改动前的 single.py 上实测撞到过）。只有专测「未知字段」的那一条放行。
    """
    import single as S
    with tc.assertRaises(S.SpecError) as cm:
        _page_payload(spec, series_dir)
    msg = str(cm.exception)
    if not unknown_ok:
        tc.assertNotIn('有未知字段', msg,
                       f'拦下它的是「未知字段」—— 新键多半还没登记进白名单，'
                       f'要测的那道闸根本没走到：{msg[:400]}')
    tc.assertTrue(any(t and t in msg for t in tokens),
                  f'SpecError 抛了，但报错里一个线索词 {tokens} 都没有 —— 多半是被别的'
                  f'护栏拦下的，这条用例没测到它要测的那道：{msg[:400]}')
    return msg


class TestHeadlineStyleNone(unittest.TestCase):
    """`headline_style='none'`：开篇一张图都不出，头条列其余四份职责一样不少。

    头条列在本底座里管五件事：①② 开篇图、`data_through` 与发布门槛、页顶数据条、
    汇总表「头条指标」那几行、④ 季节性。'none' 只拿掉第一件。
    """

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls._memo = {}

    def _pay(self, style):
        """按 headline_style 取夹具的 payload（None = 不写这个键）。同一种只建一次。"""
        if style not in self._memo:
            sp = _sgx_fixture()
            if style is not None:
                sp['headline_style'] = style
            self._memo[style] = _page_payload(sp)[1]
        return self._memo[style]

    @staticmethod
    def _opener_titles():
        """三种开篇图的标题（与 `ex_history` / `ex_head_bar` / `ex_yoy` 的 f-string 逐字同源）。"""
        out = set()
        for c in _sgx_fixture()['headline']:
            out |= {f'{c["zh"]}：全历史与近 3 年分位带', f'{c["zh"]}：全历史水平值与单月同比',
                    f'{c["zh"]}：单月同比'}
        return out

    def test_none_is_the_third_style(self):
        self.assertEqual(set(self.S.HEADLINE_STYLES), {'band_yoy', 'bar_yoy', 'none'})
        sp = _sgx_fixture()
        sp['headline_style'] = 'none'
        self.assertEqual(self.S.Page(sp).headline_style, 'none')

    def test_no_opening_chart_and_first_exhibit_is_first_group(self):
        pay = self._pay('none')
        hit = [t for _k, t in _titles(pay) if t in self._opener_titles()]
        self.assertEqual(hit, [], f"'none' 下还出了开篇图：{hit}")
        bands = [e['n'] for e in pay['exhibits']
                 if any('P90' in str(s.get('name')) for s in e.get('series') or [])]
        self.assertEqual(bands, [], f"'none' 下还画着分位带：Exhibit {bands}")
        first = pay['exhibits'][0]
        self.assertEqual(first['n'], 2, 'Exhibit 1 是汇总表，图必须仍从 2 起编号')
        self.assertTrue(_in_group(first, _GZ_SEC), f'第一张图不是第一组的图：{first["title"]}')

    def test_rest_of_page_is_band_yoy_minus_the_openers(self):
        """开篇段以外逐张不变（kind + 标题）；图号从 2 起连续、不留洞，核对表紧跟其后。"""
        band, none = self._pay(None), self._pay('none')
        k = _n_head_charts(_sgx_fixture())
        self.assertEqual(_titles(none), _titles(band)[k:])
        self.assertEqual([e['n'] for e in none['exhibits']],
                         list(range(2, 2 + len(none['exhibits']))))
        self.assertEqual(none['table']['n'], 2 + len(none['exhibits']))

    def test_headline_duties_kept(self):
        """门槛 / 页顶数据条 / 汇总表头条行 / ④ 季节性：四件一件不少，且与 band_yoy 逐字相同。"""
        band, none = self._pay(None), self._pay('none')
        for key in ('data_through', 'headline', 'hub_line', 'summary'):
            with self.subTest(key=key):
                self.assertEqual(none[key], band[key])
        self.assertIn('头条指标（决定本页数据月）',
                      [r['label'] for r in none['summary']['rows']])
        for c in _sgx_fixture()['headline']:
            with self.subTest(season=c['zh']):
                self.assertEqual(len(_idx(none, f'{c["zh"]}：与同月常态比', 'seasonality')), 1)

    def test_notes_do_not_point_at_a_missing_opening_chart(self):
        """「汇总表读法」那句今天两支：有分位带 → 点它的图号；没有 → 说「开篇图是柱 + 次轴」。
        'none' 下两支都是假话（没有带，也没有开篇图）。既有两支必须原样留着。"""
        none = self._pay('none')
        txt = _notes_txt(none) + json.dumps(none['summary'], ensure_ascii=False)
        self.assertIsNone(re.search(r'Exhibit\s*\d+\s*的灰色分位带', txt))
        self.assertNotIn('分位带与它同窗口同口径', txt)
        self.assertNotIn('开篇图是', txt)
        self.assertIn('Y %ile', _notes_txt(none), '分位那一列还在，读法那句不能跟着整条消失')
        self.assertIn('Exhibit 2 的灰色分位带与它同窗口同口径', _notes_txt(self._pay('band_yoy')))
        self.assertIn('开篇图是「柱 + 次轴同比」', _notes_txt(self._pay('bar_yoy')))

    def test_invalid_value_still_raises_and_lists_all_three(self):
        for bad in ('bogus', 'None', 'NONE'):
            with self.subTest(v=bad):
                sp = _sgx_fixture()
                sp['headline_style'] = bad
                with self.assertRaises(self.S.SpecError) as cm:
                    self.S.Page(sp)
                for want in ('band_yoy', 'bar_yoy', 'none'):
                    self.assertIn(want, str(cm.exception))

    def test_explicit_band_yoy_is_byte_identical_to_absent(self):
        self.assertEqual(_json(self._pay('band_yoy')), _json(self._pay(None)))

    def test_headline_section_is_dead_config_under_none(self):
        """'none' 下 ①② 那一段是空的，`headline_section` 没有图可命名 —— 硬失败。"""
        sp = _sgx_fixture()
        sp['headline_style'] = 'none'
        sp['headline_section'] = '开篇头条'
        _raises_spec(self, sp, ('那一段是空的',))

    def test_no_yoy_on_headline_names_paths_that_exist_under_none(self):
        """头条列上的 no_yoy 在 'none' 下照样拦，但报错不许把人指到这一档根本不跑的
        ex_head_bar / ex_yoy 上（2026-09-12 审稿）。"""
        sp = _sgx_fixture()
        sp['headline_style'] = 'none'
        sp['headline'][0]['no_yoy'] = True
        msg = _raises_spec(self, sp, ('ex_season',))
        self.assertNotIn('ex_head_bar', msg)
        self.assertNotIn('ex_yoy', msg)

    def test_headline_col_used_only_by_an_alt_split_is_not_an_orphan(self):
        """头条列只在某条 mix 的 `alt_splits[].parts` 里被引用：它画在那张占比堆叠里，
        告警行那句「组图里也没有它」对它是假话，不许响。对照组：同一列从 alt 里拿掉就要响。"""
        def spec(alt):
            sp = _sgx_fixture()
            sp['headline_style'] = 'none'
            sp['headline'] = [_c('sdav_sgdmn', '证券市场 SDAV', 'S$mn/day'), _c(_EQX, '股指期货合计')]
            sp['groups'] = [g for g in sp['groups'] if g['zh'] != _GZ_DD]
            d = _grp(sp, _GZ_AST)
            d['cols'] = [c for c in d['cols'] if c['col'] != _EQX]
            _grp(sp, _GZ_DER)['mix'] = {'total': _TOT, 'parts': [_FUT, _OPT], 'residual_zh': '掉期',
                                       'split_zh': _SPLIT_ZH, 'alt_splits': [alt]}
            return sp
        with self.subTest(case='只在 alt_splits 里'):
            page, pay = _page_payload(spec(dict(_ALT_ASSET)))
            self.assertEqual([c['col'] for c in page.head_orphans], [])
            self.assertTrue(any(s['name'] == '股指期货合计' for e in pay['exhibits']
                                for s in e.get('stacks') or []), '样例失效：那张占比图上没有这一段')
        with self.subTest(case='对照：哪里都没引用'):
            page = self.S.Page(spec({'zh': '外汇 vs 其余', 'parts': [_FXF], 'residual_zh': '外汇以外'}))
            self.assertEqual([c['col'] for c in page.head_orphans], [_EQX])

    def test_undeclared_headline_col_warns_but_builds(self):
        """'none' 下头条列若没在任何组里声明，页面上就**一张水平值图都没有**了（只剩季节性）
        —— 契约定为构建日志响一行、不停机。判据是对照：拿「声明了」那一版的日志当底，
        多出来的行里必须点到这一列（列名或中文名皆可）；band_yoy 下它有开篇图，不许响。
        比对前把数字抹掉：去掉一组之后后面的图号、张数、KB 都会变，那些不是这一行。"""
        tmp = tempfile.mkdtemp(prefix='tg_none_')
        try:
            logs = {}
            for style in ('none', 'band_yoy'):
                for declared in (True, False):
                    sp = _sgx_fixture()
                    sp['headline_style'] = style
                    if not declared:
                        sp['groups'] = [g for g in sp['groups'] if g['zh'] != _GZ_DD]
                    out = os.path.join(tmp, f'{style}_{int(declared)}')
                    logs[style, declared] = _build_log(sp, out)      # 不许抛
                    self.assertTrue(os.path.exists(os.path.join(out, 'sgx.js')),
                                    f'{style} / declared={declared} 没写出页面')
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        def extra(style):
            norm = lambda s: re.sub(r'\d+', '#', s)                   # noqa: E731
            base = {norm(x) for x in logs[style, True].splitlines()}
            return [x for x in logs[style, False].splitlines() if norm(x) not in base]

        def about_ddav(lines):
            return [x for x in lines if 'ddav_contracts' in x or '衍生品 DDAV' in x]

        self.assertTrue(about_ddav(extra('none')),
                        f"'none' 下 ddav_contracts 没在任何组里声明，构建日志却一句都没说：{extra('none')}")
        self.assertEqual(about_ddav(extra('band_yoy')), [],
                         'band_yoy 下头条列有开篇图，不该响这一行')


class TestStockInline(unittest.TestCase):
    """`groups[].stock_inline`：这一组的存量图就地排在它自己的流量图之后，不再排到 ⑤。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single

    @staticmethod
    def _inline(*names):
        sp = _sgx_fixture()
        for g in sp['groups']:
            if g['zh'] in names:
                g['stock_inline'] = True
        return sp

    def _assert_moved(self, spec, base, moved, gz):
        """moved 的图列 = base 的图列把「gz 在 ⑤ 里那一段」原样挪进 ③ 的本组位置。

        四条一起判：那一段张数与次序不变且连续；落在季节性之前；其余图一张不增、不减、
        不换序；落点在「本组及之前各组的图」之后、「之后各组的图」之前。
        """
        s0 = _season0(base)
        block = [t for i, t in enumerate(_titles(base))
                 if i > s0 and t[1].startswith(gz + '：')]
        self.assertTrue(block, f'「{gz}」在缺省版的 ⑤ 里一张存量图都没有 —— 样例选错了')
        tm = _titles(moved)
        pos = [i for i, t in enumerate(tm) if t in block]
        self.assertEqual([tm[i] for i in pos], block, '挪过去的那一段张数或次序变了')
        self.assertEqual(pos, list(range(pos[0], pos[0] + len(block))), '挪过去的那一段不连续')
        self.assertLess(pos[-1], _season0(moved), '还排在季节性之后（开关没生效）')
        self.assertEqual([t for t in tm if t not in block],
                         [t for t in _titles(base) if t not in block],
                         '除了挪位的那一段，别的图也变了')
        order = [g['zh'] for g in spec['groups']]
        gi = order.index(gz)
        for i in range(_n_head_charts(spec), _season0(moved)):
            j = _gpos(order, tm[i][1])
            if j is None or i in pos:
                continue                       # 分解图不带组名前缀；那一段自己不算
            if i < pos[0]:
                self.assertLessEqual(j, gi, f'挪早了：排在「{order[j]}」的图之前')
            else:
                self.assertGreater(j, gi, f'挪晚了：排在「{order[j]}」的图之后')
        self.assertEqual([e['n'] for e in moved['exhibits']], list(range(2, 2 + len(tm))))

    def test_dead_config_raises(self):
        """一列存量都没声明的组开这个开关 = 死配置（没有东西可挪），硬失败。"""
        _raises_spec(self, self._inline(_GZ_SEC), ('没有任何存量图可挪',))

    def test_dead_config_raises_on_a_flow_total_mix(self):
        """有 mix、但合计是**流量**列、本组又没有存量列 —— 同样无物可挪。
        判据是「mix 的合计是存量列」而不是「有 mix」：写成后者，这一种会静默建出页来。"""
        sp = _sgx_fixture()
        g = _grp(sp, _GZ_DER)
        g['cols'] = [c for c in g['cols'] if not c.get('stock')]
        g['mix'] = {'total': _TOT, 'parts': [_FUT, _OPT], 'residual_zh': '掉期'}
        g['stock_inline'] = True
        _raises_spec(self, sp, ('没有任何存量图可挪',))

    def test_only_true_or_false(self):
        for bad in ('yes', 1, 'True'):
            with self.subTest(v=bad):
                sp = _sgx_fixture()
                _grp(sp, _GZ_DER)['stock_inline'] = bad
                _raises_spec(self, sp, ('stock_inline',))

    def test_stock_chart_right_after_its_flow_charts(self):
        _p, pay = _page_payload(self._inline(_GZ_DER))
        flow = _idx(pay, f'{_GZ_DER}：当月成交合计 / 其中：期货 / 其中：期权')
        oi = _idx(pay, f'{_GZ_DER}：月末未平仓（存量，期末口径）', 'gs_bar')
        cap = _idx(pay, f'{_GZ_CAP}：月末总市值（存量，期末口径）', 'gs_bar')
        s0 = _season0(pay)
        self.assertEqual(len(flow), 1)
        self.assertEqual(len(oi), 1, '存量图要么丢了，要么 ③ ⑤ 各出了一张')
        self.assertEqual(oi[0], flow[0] + 1, '没有紧跟本组的流量图')
        self.assertLess(oi[0], s0)
        self.assertEqual(len(cap), 1)
        self.assertGreater(cap[0], s0, '没开开关的组被一起挪了')
        # 页尾「存量与流量分开读」那句排序说明（`stock_order_zh`）：图号全部现算、逐张点全。
        # 删掉这句、或只点第一张流量图，读者在组图中间撞见一张存量图就不知道那是有意的。
        ex = pay['exhibits']
        j = lambda ns: '、'.join(str(k) for k in ns)                    # noqa: E731
        flow_ns = [e['n'] for e in ex[:oi[0]] if _in_group(e, _GZ_DER)]
        tail_ns = [e['n'] for e in ex[s0:] if e['title'].endswith('（存量，期末口径）')]
        notes = _notes_txt(pay)
        self.assertIn(f'「{_GZ_DER}」组的存量图（Exhibit {ex[oi[0]]["n"]}）按组的顺序就地排列，'
                      f'紧跟本组的流量图（Exhibit {j(flow_ns)}）', notes)
        self.assertIn(f'其余存量图（Exhibit {j(tail_ns)}）集中排在季节性图之后', notes)
        _p, base = _page_payload(_sgx_fixture())
        self.assertNotIn('按组的顺序就地排列', _notes_txt(base), '开关没开，排序那句不该出现')

    def test_is_a_pure_move(self):
        _p, base = _page_payload(_sgx_fixture())
        _p, moved = _page_payload(self._inline(_GZ_DER))
        self._assert_moved(_sgx_fixture(), base, moved, _GZ_DER)

    def test_inline_block_precedes_after_group_decomp(self):
        """契约的落点是「本组流量图之后、`_mark_section` / `_decomp_here` 之前」：
        就地排在本组之后的分解图，必须排在挪进来的存量图后面。"""
        sp = self._inline(_GZ_DER)
        sp['decomp'] = [_decomp_fixture(_GZ_DER)]
        _p, pay = _page_payload(sp)
        oi = _idx(pay, f'{_GZ_DER}：月末未平仓（存量，期末口径）', 'gs_bar')
        dec = [i for i, e in enumerate(pay['exhibits']) if e['kind'] == 'bridge_bar']
        self.assertEqual(len(oi), 1)
        self.assertEqual(dec, [oi[0] + 1])

    def test_stock_total_mix_pair_moves_too(self):
        """合计是存量列的 mix（「合计柱 + 占比堆叠」）跟存量柱一起挪。

        series/sgx.csv 里没有能拆出分项的存量列，所以这一支借一份活 spec（不借 sgx）。
        借到的组若**只有存量列**（写这条时 tmx 那几组都是这个形状），`_assert_moved` 的
        落点判据就顺带守住「本组没有流量图时，那一段落在本组自己的位置上」。
        """
        hit = sp = None
        for t in _live_tickers(exclude=('sgx',)):
            sp = self.S.load_spec(t)
            decl = {c['col']: c for c in sp['headline']}
            for g in sp['groups']:
                decl.update({c['col']: c for c in g['cols']})
            hit = next((g for g in sp['groups'] if g.get('mix')
                        and decl[g['mix']['total']].get('stock')
                        and not g['mix'].get('abs_stack')), None)
            if hit:
                break
        if hit is None:
            self.skipTest('现网 spec 里没有合计是存量列的 mix，这一支暂无活体可借')
        _p, base = _page_payload(sp)
        sp2 = copy.deepcopy(sp)
        _grp(sp2, hit['zh'])['stock_inline'] = True
        _p, moved = _page_payload(sp2)
        kinds = [e['kind'] for e in moved['exhibits'] if _in_group(e, hit['zh'])]
        self.assertIn('stacked_dual', kinds, 'mix 那张占比堆叠没跟着出来')
        self._assert_moved(sp, base, moved, hit['zh'])

    def test_absent_is_byte_identical_to_explicit_false(self):
        for label, sp in (('夹具', _sgx_fixture()), ('jpx', self.S.load_spec('jpx'))):
            with self.subTest(spec=label):
                off = copy.deepcopy(sp)
                for g in off['groups']:
                    g['stock_inline'] = False
                self.assertEqual(_json(_page_payload(off)[1]), _json(_page_payload(sp)[1]))


class TestMixAltSplits(unittest.TestCase):
    """`groups[].mix.alt_splits`：同一个合计的第二种（第 k 种）切法。合计柱只画一次。"""

    _TOTAL_TITLE = f'{_GZ_DER}：当月成交合计 —— 水平值与单月同比'
    _ALT_TOK = ('alt_splits', '第三刀')

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls._memo = {}

    @staticmethod
    def _spec(alts=None, same_group=False, **mix):
        """丙组挂「期货 / 期权 / 掉期」主切法 + alt_splits；mix 的键可逐个覆盖（给 None = 删键）。

        same_group=False：资产类别三列留在丁组、跨组借来当分项（丁组自己的折线照出）；
        True：三列并进丙组（它们该被丙组吃掉）。
        """
        sp = _sgx_fixture()
        g = _grp(sp, _GZ_DER)
        if same_group:
            d = _grp(sp, _GZ_AST)
            sp['groups'].remove(d)
            g['cols'][3:3] = d['cols']
        m = {'total': _TOT, 'parts': [_FUT, _OPT], 'residual_zh': '掉期', 'rhs_share': _OPT,
             'split_zh': _SPLIT_ZH,
             'alt_splits': copy.deepcopy(alts) if alts is not None else [dict(_ALT_ASSET)]}
        for k, v in mix.items():
            if v is None:
                m.pop(k, None)
            else:
                m[k] = v
        g['mix'] = m
        return sp

    @staticmethod
    def _share_title(label, tot='当月成交合计', gz=_GZ_DER):
        return f'{gz}：{label}（分母 = {tot}，堆叠 = 100%）'

    def _built(self, key, **kw):
        if key not in self._memo:
            self._memo[key] = _page_payload(self._spec(**kw))
        return self._memo[key]

    # ── 反例：两个键的配对、与 abs_stack 互斥、名字与分项集合不许重复 ──────────────
    def test_split_zh_and_alt_splits_come_together(self):
        """只给 split_zh = 给一张不存在的「主切法」起名；只给 alt_splits = 主切法那张还叫
        「各分项占比」，读者分不出两张占比图各是哪一刀。"""
        with self.subTest(only='split_zh'):
            _raises_spec(self, self._spec(alt_splits=None), ('却没有 alt_splits',))
        with self.subTest(only='alt_splits'):
            _raises_spec(self, self._spec(split_zh=None), ('却没写 split_zh',))

    def test_abs_stack_excludes_alt_splits(self):
        """abs_stack 只出一张绝对值堆叠、不出 100% 占比 —— 第二刀没有地方画。
        rhs_share 先摘掉：它与 abs_stack 另有一道互斥，不摘就测到那一道上去了。"""
        _raises_spec(self, self._spec(abs_stack=True, rhs_share=None),
                     ('同时写了 abs_stack 与 alt_splits',))

    def test_alt_zh_unique_and_not_split_zh(self):
        """名字进标题：两张同名的占比图，读者分不出谁是谁。线索词用那道护栏独有的「重名」。"""
        with self.subTest(case='两条 alt 同名'):
            two = [dict(_ALT_ASSET), dict(_ALT_EQ, zh=_ALT_ASSET['zh'])]
            msg = _raises_spec(self, self._spec(alts=two), ('重名',))
            self.assertIn('alt_splits[1]', msg)
        with self.subTest(case='alt 与主切法同名'):
            msg = _raises_spec(self, self._spec(alts=[dict(_ALT_ASSET, zh=_SPLIT_ZH)]), ('重名',))
            self.assertIn('alt_splits[0]', msg)

    def test_blank_or_empty_alt_config_raises(self):
        """三道死配置 / 空标签护栏（`_norm_mix`）：`alt_splits=[]`、alt 的 zh 是空串或纯空白。
        关掉任何一道，那种 spec 都能建出页来（`[]` 静默当没写；空 zh 出一张标题叫「各分项占比」
        的 alt 图，⑤ 里印着 Exhibit k「」）。"""
        with self.subTest(case='alt_splits=[]'):
            _raises_spec(self, self._spec(alts=[], split_zh=None), ('必须是非空列表',))
        for blank in ('', '  '):
            with self.subTest(case=f'zh={blank!r}'):
                msg = _raises_spec(self, self._spec(alts=[dict(_ALT_ASSET, zh=blank)]),
                                   ('zh 是空的',))
                self.assertIn('alt_splits[0]', msg)

    def test_same_part_set_twice_raises(self):
        """分项集合相同 = 同一张图画两遍（换个声明顺序也一样）：与主切法撞、与另一条 alt 撞都算。"""
        with self.subTest(case='与主切法同集合'):
            alt = {'zh': '第三刀', 'parts': [_OPT, _FUT], 'residual_zh': '掉期'}
            msg = _raises_spec(self, self._spec(alts=[alt]), ('同一张图画两遍',))
            self.assertIn('主切法', msg)
        with self.subTest(case='与另一条 alt 同集合'):
            alt = {'zh': '第三刀', 'parts': [_CMD, _EQX, _FXF], 'residual_zh': '其他'}
            msg = _raises_spec(self, self._spec(alts=[dict(_ALT_ASSET), alt]), ('同一张图画两遍',))
            self.assertIn(_ALT_ASSET['zh'], msg)

    def test_each_alt_gets_the_main_parts_mechanical_checks(self):
        """`_norm_mix` 对主切法的机械校验，每条 alt 逐条再过一遍（外加必填与未知字段）。

        ⚠️ 线索词必须是**那一道护栏独有**的措辞，另外再要求报错指到 `alt_splits[1]`。
        上一版每条都拿 ('alt_splits', '第三刀') 当线索词 —— alt 这一支的每一条报错都带着
        `alt_splits`，任何一道**后面的**护栏拦下都算过：把其中五道对 alt 单独关掉，全套照绿
        （2026-09-12 变异测试实测；「分项重复」那条靠的是两倍股指期货恰好超过合计，
        换成两倍商品就会带着一张同列堆两遍的图上页）。
        所以：重复分项用两倍商品（和仍小于合计，残差复算拦不住）；超配色那条的六列全部先声明，
        免得被「列没声明」那道拦下。
        """
        six = [_EQX, _FXF, _CMD, _A50, _N225, _MSG]
        cases = {
            '分项为空': ({'zh': '第三刀', 'parts': []}, '一项都没有'),
            '分项重复': ({'zh': '第三刀', 'parts': [_CMD, _CMD], 'residual_zh': '其他'}, '重复列名'),
            '合计混进分项': ({'zh': '第三刀', 'parts': [_TOT, _EQX], 'residual_zh': '其他'},
                           '同时出现在 parts 里'),
            '超过配色上限': ({'zh': '第三刀', 'parts': six, 'residual_zh': '其他'}, '配色能分开'),
            'rhs_share 不是分项': ({'zh': '第三刀', 'parts': [_EQX, _FXF],
                                   'residual_zh': '其他', 'rhs_share': _CMD},
                                  '既不是 parts 里的列名'),
            "rhs_share='residual' 却没有残差段": ({'zh': '第三刀', 'parts': [_EQX, _FXF],
                                                 'rhs_share': 'residual'},
                                                '没有残差段就没有那条线可画'),
            '缺 zh': ({'parts': [_EQX, _FXF], 'residual_zh': '其他'}, '缺必填字段'),
            '缺 parts': ({'zh': '第三刀', 'residual_zh': '其他'}, '缺必填字段'),
            # 合计柱的 note 只有一份、挂在主切法上；写进 alt 就是死配置
            '未知字段': ({'zh': '第三刀', 'parts': [_EQX, _FXF], 'residual_zh': '其他',
                         'note': '合计柱只有一张'}, '有未知字段'),
        }
        for why, (alt, tok) in cases.items():
            with self.subTest(case=why):
                sp = self._spec(alts=[dict(_ALT_ASSET), alt])
                _grp(sp, _GZ_AST)['cols'] += [_c(_A50, 'A50 期货'), _c(_N225, '日経225 期货'),
                                              _c(_MSG, 'MSCI 新加坡期货')]
                msg = _raises_spec(self, sp, (tok,), unknown_ok=(why == '未知字段'))
                self.assertIn('alt_splits[1]', msg, f'报错没指到出错的那一条 alt：{msg[:300]}')

    def test_alt_part_must_be_a_declared_column(self):
        """前者在 CSV 里、只是本 spec 没声明；后者连 CSV 里都没有。两种都不许静默丢图。"""
        for col in ('vol_rates_futures_contracts', 'no_such_col'):
            with self.subTest(col=col):
                alt = {'zh': '第三刀', 'parts': [_EQX, col], 'residual_zh': '其他'}
                msg = _raises_spec(self, self._spec(alts=[alt]), ('没有在本 spec 里声明的列',))
                self.assertIn('alt_splits（第三刀）', msg)
                self.assertIn(col, msg)

    def test_alt_part_same_unit_same_kind_not_ratio(self):
        """Page 构造期对主切法的三条列级校验，alt 的分项同样要过。线索词逐条是那一道独有的措辞。"""
        cases = {
            '单位不同': (_c('vol_rates_futures_contracts', '利率期货', 'lots/month'), '单位不同'),
            '一流量一存量': (_c('vol_rates_futures_contracts', '利率期货', stock=True),
                          '一个是流量一个是存量'),
            '比率列': (_c('turnover_velocity_pct', '整体换手率', fmt='pct0'), '是比率列'),
        }
        for why, (extra, tok) in cases.items():
            with self.subTest(case=why):
                sp = self._spec(alts=[{'zh': '第三刀', 'parts': [_EQX, extra['col']],
                                       'residual_zh': '其他'}])
                _grp(sp, _GZ_AST)['cols'].append(extra)
                msg = _raises_spec(self, sp, (tok,))
                self.assertIn('alt_splits（第三刀）', msg)
                self.assertIn(extra['zh'], msg)

    def test_alt_residual_is_recomputed_monthly(self):
        """主切法那三条加总复算（`ex_mix_share`），换成 alt 的分项逐条再撞一遍。

        报错必须指到 `mix.alt_splits「第三刀」`（`where`），「请给 … 加一个 residual_zh」必须
        说「这条 alt_splits」（`who`）—— 指成 `groups「…」.mix`，改错的人会去改主切法。
        """
        where = f'groups「{_GZ_DER}」.mix.alt_splits「第三刀」'
        with self.subTest(case='分项之和超过合计'):
            # 期货合计本身就含股指期货，两条相加必然超过当月成交合计
            alt = {'zh': '第三刀', 'parts': [_FUT, _EQX], 'residual_zh': '其他'}
            msg = _raises_spec(self, self._spec(alts=[alt]), ('**超过**合计',))
            self.assertIn(where, msg)
        with self.subTest(case='有残差却没起名'):
            # 三条资产类别合计之外还有利率期货等，残差逐月为正
            alt = {'zh': '第三刀', 'parts': [_EQX, _FXF, _CMD]}
            msg = _raises_spec(self, self._spec(alts=[alt]),
                               ("请给 这条 alt_splits 加一个 'residual_zh'",))
            self.assertIn(where, msg)
        with self.subTest(case='起了名而残差恒为 0'):
            # 把掉期列改写成「合计 − 期货 − 期权」，三项之和逐月恰等于合计。
            # 改的是构造好的 page.df（同 TestMixAbsStack 的注入法），CSV 一个字节不动。
            sp = self._spec(alts=[{'zh': '第三刀', 'parts': [_FUT, _OPT, _SWP],
                                   'residual_zh': '其他'}])
            _grp(sp, _GZ_DER)['cols'].insert(3, _c(_SWP, '掉期列'))
            page = self.S.Page(copy.deepcopy(sp))
            page.df[_SWP] = page.df[_TOT] - page.df[_FUT] - page.df[_OPT]
            with self.assertRaises(self.S.SpecError) as cm:
                page.payload()
            self.assertIn(f'{where} 声明了 residual_zh', str(cm.exception),
                          str(cm.exception)[:400])

    def test_alt_that_cannot_be_drawn_is_named_in_the_skipped_reason(self):
        """某一刀画不成（窗口不足 24 个月）：只丢那一刀，「本轮未出的派生图」必须点到**这一刀**
        （`组名「切法名」：…`）。只写组名时，页尾说「这一组的占比堆叠不出」而页上明明有两张。"""
        alt = {'zh': '加密 vs 其余', 'parts': ['vol_crypto_contracts'], 'residual_zh': '加密以外'}
        sp = self._spec(alts=[dict(_ALT_ASSET), alt])
        _grp(sp, _GZ_AST)['cols'].append(_c('vol_crypto_contracts', 'BTC / ETH 永续期货'))
        page, pay = _page_payload(sp)
        shares = [e['title'] for e in pay['exhibits']
                  if e['kind'] == 'stacked_dual' and _in_group(e, _GZ_DER)]
        self.assertEqual(shares, [self._share_title(_SPLIT_ZH), self._share_title(_ALT_ASSET['zh'])])
        hit = [w for w in page.skipped if w.startswith(f'{_GZ_DER}「{alt["zh"]}」：')]
        self.assertEqual(len(hit), 1, f'画不成的那一刀没被点名：{page.skipped}')
        self.assertIn('占比堆叠不出', hit[0])
        self.assertIn(f'{_GZ_DER}「{alt["zh"]}」', _notes_txt(pay))

    def test_alt_on_an_empty_column_is_dropped_alone(self):
        """整列为空是「等数据」：只丢那一刀并记进 `mix_skipped`，主切法与其余切法照出。
        拿一份临时 series 目录把商品合计整列抹空（仓库里的 CSV 一个字节不动）。"""
        tmp = tempfile.mkdtemp(prefix='tg_alt_')
        try:
            with open(os.path.join(ROOT, 'series', 'sgx.csv'), encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
            k = rows[0].index(_CMD)
            for r in rows[1:]:
                r[k] = ''
            with open(os.path.join(tmp, 'sgx.csv'), 'w', encoding='utf-8', newline='') as f:
                csv.writer(f).writerows(rows)
            page, pay = _page_payload(self._spec(alts=[dict(_ALT_ASSET), dict(_ALT_EQ)]), tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        shares = [e['title'] for e in pay['exhibits']
                  if e['kind'] == 'stacked_dual' and _in_group(e, _GZ_DER)]
        self.assertEqual(shares, [self._share_title(_SPLIT_ZH), self._share_title(_ALT_EQ['zh'])])
        self.assertIn(_ALT_ASSET['zh'], '；'.join(page.mix_skipped))
        self.assertIn(_ALT_ASSET['zh'], _notes_txt(pay), '页尾「本轮未出的派生图」没点名这一刀')
        # 先丢掉的那一刀仍算在「声明了几种」里：spec 写着 3 种，页面不许说 2 种
        self.assertIn('（当月成交合计）的 3 种切法，本轮画成其中 2 种', _notes_txt(pay))

    def test_page_notes_count_declared_and_drawn_splits_separately(self):
        """某一刀画不成（窗口不足 24 个月）时，⑤ 那句「声明了 N 种切法」的 N 必须是 spec 上的刀数，
        画成几张另外说 —— 从前两处都印画成的张数，与同页「本轮未出的派生图」当场打架。"""
        alt = {'zh': '加密 vs 其余', 'parts': ['vol_crypto_contracts'], 'residual_zh': '加密以外'}
        sp = self._spec(alts=[dict(_ALT_ASSET), alt])
        _grp(sp, _GZ_AST)['cols'].append(_c('vol_crypto_contracts', 'BTC / ETH 永续期货'))
        _p, pay = _page_payload(sp)
        m = re.search(r'⑤(.*?)(?:⑥|\n|$)', _notes_txt(pay), re.S)
        self.assertIsNotNone(m)
        seg = m.group(1)
        self.assertIn('（当月成交合计）的 3 种切法，本轮画成其中 2 种（其余 1 种没画成', seg)
        self.assertIn('<b>2 张</b>', seg)
        with self.subTest(case='全画成时措辞不变'):
            _p, pay1 = self._built('one')
            self.assertIn('（当月成交合计）的 2 种切法，合计柱（Exhibit', _notes_txt(pay1))
            self.assertNotIn('本轮画成其中', _notes_txt(pay1))

    def test_empty_main_part_drops_the_whole_mix_and_names_every_share(self):
        """合计或主切法缺列 → 整条 mix 落空，连同本来画得出来的 alt 占比图。那是有意的不对称，
        但 `mix_skipped` 那一行必须逐张点名没出的占比图，不许只说「占比堆叠」。没有 alt 时措辞不变。"""
        tmp = tempfile.mkdtemp(prefix='tg_alt_main_')
        try:
            with open(os.path.join(ROOT, 'series', 'sgx.csv'), encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
            rows[0].append('x_empty_flow')
            for r in rows[1:]:
                r.append('')
            with open(os.path.join(tmp, 'sgx.csv'), 'w', encoding='utf-8', newline='') as f:
                csv.writer(f).writerows(rows)
            variants = {}
            for key, kw in (('alt', {}), ('plain', {'alt_splits': None, 'split_zh': None})):
                sp = self._spec(**kw)
                g = _grp(sp, _GZ_DER)
                g['cols'].insert(3, _c('x_empty_flow', '空列'))
                g['mix']['parts'] = [_FUT, 'x_empty_flow']
                g['mix'].pop('rhs_share', None)
                variants[key] = _page_payload(sp, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        page, pay = variants['alt']
        self.assertEqual([e for e in pay['exhibits']
                          if e['kind'] == 'stacked_dual' and _in_group(e, _GZ_DER)], [])
        why = '；'.join(page.mix_skipped)
        self.assertIn('全部 2 张占比堆叠', why)
        self.assertIn(f'「{_SPLIT_ZH}」', why)
        self.assertIn(f'「{_ALT_ASSET["zh"]}」', why)
        self.assertIn(f'「{_ALT_ASSET["zh"]}」', _notes_txt(pay))
        page, _pay = variants['plain']
        self.assertEqual(page.mix_skipped, [f'{_GZ_DER}：x_empty_flow 整列为空，总量柱与占比堆叠都不出'])

    def test_dup_part_still_searches_main_parts_only(self):
        """`ratio_rhs.dup_part` 认的「那一段」只在主切法里找 —— 报错必须把这件事说出来，
        不然写 spec 的人会以为 alt 的分项也能认领。"""
        sp = self._spec()
        sp['groups'].append({'zh': '己·A50', 'cols': [_c(_A50, 'A50 期货'), _c(_EQX, '股指期货合计')],
                             'ratio_rhs': {'num': _A50, 'den': _EQX, 'zh': 'A50 占股指期货',
                                           'dup_part': _EQX}})
        msg = _raises_spec(self, sp, ('dup_part',))
        self.assertTrue('alt_splits' in msg or '主' in msg,
                        f'报错没说明 dup_part 只在主切法的 parts 里找：{msg[:400]}')

    # ── 正例：一张合计柱 + 连续的占比图，互指现算 ────────────────────────────────
    def test_one_total_bar_then_consecutive_share_charts(self):
        _p, pay = self._built('one')
        ex = pay['exhibits']
        tot = _idx(pay, self._TOTAL_TITLE, 'gs_bar')
        self.assertEqual(len(tot), 1, '合计柱必须恰好画一次')
        i = tot[0]
        self.assertEqual(_titles(pay)[i + 1:i + 3],
                         [('stacked_dual', self._share_title(_SPLIT_ZH)),
                          ('stacked_dual', self._share_title(_ALT_ASSET['zh']))])
        self.assertEqual(sum(1 for e in ex if e['kind'] == 'stacked_dual' and _in_group(e, _GZ_DER)),
                         2)
        self.assertEqual([s['name'] for s in ex[i + 1]['stacks']], ['其中：期货', '其中：期权', '掉期'])
        self.assertEqual([s['name'] for s in ex[i + 2]['stacks']],
                         ['股指期货合计', '外汇期货合计', '商品合计（不含加密）', '其他'])
        for e in ex[i + 1:i + 3]:
            sums = [sum(v) for v in zip(*(s['values'] for s in e['stacks']))]
            self.assertLess(max(abs(x - 100.0) for x in sums), 1e-3, e['title'])
        self.assertIn('其中：期权', (ex[i + 1].get('line') or {}).get('name', ''),
                      '主切法的 rhs_share 没画')
        self.assertIsNone(ex[i + 2].get('line'), 'alt 没声明 rhs_share，却画了右轴线')
        # 跨组借来的三列，水平值仍归丁组自己（与主切法跨组引用同一条语义）
        self.assertEqual(len([e for e in ex if _in_group(e, _GZ_AST) and e['kind'] in _LINE_KINDS]),
                         1)

    def test_back_references_are_computed(self):
        """合计柱点名每一张占比图；每张占比图点名合计柱与它的兄弟切法。图号一律现算。"""
        variants = {'一条 alt': ('one', {}),
                    '两条 alt（声明顺序）': ('two', {'alts': [dict(_ALT_ASSET), dict(_ALT_EQ)]})}
        for why, (key, kw) in variants.items():
            with self.subTest(case=why):
                _p, pay = self._built(key, **kw)
                ex = pay['exhibits']
                i = _idx(pay, self._TOTAL_TITLE, 'gs_bar')[0]
                labels = [_SPLIT_ZH] + [a['zh'] for a in (kw.get('alts') or [_ALT_ASSET])]
                shares = ex[i + 1:i + 1 + len(labels)]
                self.assertEqual([e['title'] for e in shares],
                                 [self._share_title(z) for z in labels])
                self.assertEqual(len({e['title'] for e in shares}), len(labels))
                ns = {e['n'] for e in shares}
                self.assertLessEqual(ns, _ex_refs(ex[i]['note']),
                                     '合计柱的图注没把每一张占比图都点到')
                names = lambda x: '、'.join(s['name'] for s in x['stacks'])   # noqa: E731
                for e in shares:
                    refs = _ex_refs(e['note'])
                    self.assertIn(ex[i]['n'], refs, f'{e["title"]} 没指回合计柱')
                    self.assertLessEqual(ns - {e['n']}, refs,
                                         f'{e["title"]} 没指到同分母的另几刀')
                    # 兄弟那句的**内容**也要对：本图自己的段名、每张兄弟图各自的段名、
                    # 窗口相同就不许说「不一样长」。只查图号时，把段名换成兄弟的、或把窗口判据写反，
                    # 全套照绿而活页上印着假话（2026-09-12 变异测试实测）。
                    self.assertIn(f'本图是「{names(e)}」', e['note'])
                    for o in shares:
                        if o is not e:
                            self.assertIn(f'Exhibit {o["n"]} 是「{names(o)}」', e['note'])
                    self.assertNotIn('窗口不一样长', e['note'], '几张窗口相同，却印了「窗口不一样长」')
                    # 「spec 没有声明包含关系」是底座替 spec 说话：spec 完全可以在 share_note 里写明
                    self.assertNotIn('spec 没有声明', e['note'])

    def test_sibling_sentence_prints_both_windows_when_they_differ(self):
        """每张占比图各取「合计与本张分项都有值」的末端连续段 —— 分项起点晚的那一刀窗口更短。
        窗口不同就必须照实印出两边各自的窗口（图号与起止都现读 exhibit）。"""
        tw = 'vol_ftse_taiwan_futures_contracts'
        alt = {'zh': '台湾 vs 其余', 'parts': [tw], 'residual_zh': '台湾以外'}
        sp = self._spec(alts=[alt])
        _grp(sp, _GZ_AST)['cols'].append(_c(tw, 'FTSE 台湾期货'))
        _p, pay = _page_payload(sp)
        ex = pay['exhibits']
        main = ex[_idx(pay, self._share_title(_SPLIT_ZH))[0]]
        late = ex[_idx(pay, self._share_title(alt['zh']))[0]]
        span = lambda x: f'{x["xlabels"][0]} → {x["xlabels"][-1]}（{len(x["xlabels"])} 个月）'  # noqa: E731
        self.assertNotEqual(span(main), span(late), '样例选错了：两刀窗口一样长')
        for e, o in ((main, late), (late, main)):
            with self.subTest(chart=e['title']):
                self.assertIn('窗口不一样长', e['note'])
                self.assertIn(f'本图 {span(e)}', e['note'])
                self.assertIn(f'Exhibit {o["n"]} {span(o)}', e['note'])

    def test_alt_parts_are_eaten_in_their_own_group(self):
        """三列并进丙组之后不再另出一张折线：结构由第二张占比交代、各自的绝对量在核对表。"""
        _p, pay = _page_payload(self._spec(same_group=True))
        own = [e['title'] for e in pay['exhibits'] if _in_group(e, _GZ_DER)]
        self.assertEqual(own, [self._TOTAL_TITLE, self._share_title(_SPLIT_ZH),
                               self._share_title(_ALT_ASSET['zh']),
                               f'{_GZ_DER}：月末未平仓（存量，期末口径）'])

    def test_alt_parts_count_as_eaten_for_ratio_rhs_bucket(self):
        """`ratio_rhs`「本桶恰好是 num 与 den」按吃掉之后的列算 —— alt 的分项也要扣。"""
        sp = self._spec(same_group=True,
                        alts=[{'zh': '股指 + 商品', 'parts': [_EQX, _CMD], 'residual_zh': '其他'}])
        g = _grp(sp, _GZ_DER)
        g['cols'].insert(6, _c(_CNH, 'USD/CNH 期货'))
        g['ratio_rhs'] = {'num': _CNH, 'den': _FXF, 'zh': 'USD/CNH 占外汇期货'}
        _p, pay = _page_payload(sp)
        rr = [e for e in pay['exhibits'] if _in_group(e, _GZ_DER) and e['kind'] == 'grouped_bars']
        self.assertEqual(len(rr), 1, '外汇期货 / USD/CNH 那一桶没画成并排柱 + 右轴比值线')
        self.assertIsNotNone(rr[0].get('line'))

    def test_alt_part_counts_as_eaten_for_the_two_bars_guard(self):
        """被丙组 alt 吃掉的列拿去当别组 mix 的合计，不算「同一列两根柱」（eaten_max 要算 alt）。"""
        sp = self._spec(same_group=True)
        sp['groups'].append({'zh': '己·股指', 'cols': [
            _c(_A50, 'A50 期货'), _c(_N225, '日経225 期货'), _c(_MSG, 'MSCI 新加坡期货')],
            'mix': {'total': _EQX, 'parts': [_A50, _N225, _MSG], 'residual_zh': '其他指数'}})
        _p, pay = _page_payload(sp)
        bars = [e['title'] for e in pay['exhibits']
                if e['kind'] == 'gs_bar' and '股指期货合计' in e['title']]
        self.assertEqual(bars, ['己·股指：股指期货合计 —— 水平值与单月同比'])

    def test_rhs_share_and_share_note_belong_to_their_own_split(self):
        alt = dict(_ALT_ASSET, rhs_share='residual', share_note='【alt 的注】')
        _p, pay = _page_payload(self._spec(alts=[alt], share_note='【主切法的注】'))
        ex = pay['exhibits']
        main = ex[_idx(pay, self._share_title(_SPLIT_ZH))[0]]
        second = ex[_idx(pay, self._share_title(alt['zh']))[0]]
        self.assertIn('【主切法的注】', main['note'])
        self.assertNotIn('【alt 的注】', main['note'])
        self.assertIn('【alt 的注】', second['note'])
        self.assertNotIn('【主切法的注】', second['note'])
        self.assertIn('其中：期权', (main.get('line') or {}).get('name', ''))
        self.assertIn('其他', (second.get('line') or {}).get('name', ''))

    def test_page_notes_stay_true_when_a_group_has_several_shares(self):
        """⑤「声明了 mix 的组出两张」对一组三张的页是假话 —— 还说「两张」就得现算点名例外。"""
        _p, pay = self._built('one')
        m = re.search(r'⑤(.*?)(?:⑥|\n|$)', _notes_txt(pay), re.S)
        self.assertIsNotNone(m, '页上有占比堆叠，图型选择规则里却没有 ⑤')
        seg = m.group(1)
        if '两张' in seg:
            self.assertTrue(any(t in seg for t in (_GZ_DER, _SPLIT_ZH, _ALT_ASSET['zh'], 'alt_splits')),
                            f'⑤ 仍说「两张」，却没点名多出占比图的那一组：{seg[:300]}')
        # 例外句要把**每一张**真画出来的占比图都点到（图号 + 切法名），只点第一张时张数照样对得上
        shares = [e for e in pay['exhibits'] if e['kind'] == 'stacked_dual' and _in_group(e, _GZ_DER)]
        for e, lb in zip(shares, (_SPLIT_ZH, _ALT_ASSET['zh'])):
            self.assertIn(f'Exhibit {e["n"]}「{lb}」', seg)
        self.assertIn(f'<b>{len(shares)} 张</b>', seg)

    def test_folded_total_notes_stay_true(self):
        """bar_yoy 开篇图画的就是合计列 ⇒ 合计柱折叠（`total_drawn_wider`），这一组只剩占比图，
        而且不止一张。`mix_folded_zh()` 原来写死「所以只出占比那一张」。"""
        sp = self._spec()
        sp['headline_style'] = 'bar_yoy'
        sp['headline'] = [_c(_TOT, '衍生品当月成交合计')]
        page, pay = _page_payload(sp)
        ex = pay['exhibits']
        self.assertEqual(_idx(pay, self._TOTAL_TITLE), [], '合计列已由开篇图画过，合计柱不该再出')
        shares = [e for e in ex if e['kind'] == 'stacked_dual' and _in_group(e, _GZ_DER)]
        self.assertEqual([e['title'] for e in shares],
                         [self._share_title(_SPLIT_ZH), self._share_title(_ALT_ASSET['zh'])])
        self.assertEqual(shares[1]['n'], shares[0]['n'] + 1)
        for e in shares:
            self.assertIn(ex[0]['n'], _ex_refs(e['note']), f'{e["title"]} 没指回开篇那张更宽的柱')
        self.assertEqual([d['gz'] for d in page.mix_folded], [_GZ_DER])
        self.assertNotIn('只出占比那一张', _notes_txt(pay))
        # 张数对、而且逐张点名（图号 + 切法名）：只点第一张时「那 2 张」照样对得上
        notes = _notes_txt(pay)
        self.assertIn(f'所以只出占比那 {len(shares)} 张', notes)
        for e, lb in zip(shares, (_SPLIT_ZH, _ALT_ASSET['zh'])):
            self.assertIn(f'Exhibit {e["n"]}「{lb}」', notes)

    def test_folded_mix_with_no_share_drawn_does_not_claim_the_group_is_empty(self):
        """合计柱折叠、占比图又一张都没画成：那条 mix 是 0 张图，但这一组别的列照样出图
        （分项回到本组常规分桶、存量列照出）。页尾只许说「合计柱与占比堆叠一张都没有」，
        不许说「这一组一张图都没有」—— 后者在这种页面上一数就拆穿（2026-09-12 审稿实测）。"""
        tmp = tempfile.mkdtemp(prefix='tg_alt_fold0_')
        try:
            with open(os.path.join(ROOT, 'series', 'sgx.csv'), encoding='utf-8', newline='') as f:
                rows = list(csv.reader(f))
            mk = rows[0].index('month')
            for col in (_FUT, _EQX):                       # 两刀的窗口都砍到 24 个月以下
                k = rows[0].index(col)
                for r in rows[1:]:
                    if r[mk] < '2025-09':
                        r[k] = ''
            with open(os.path.join(tmp, 'sgx.csv'), 'w', encoding='utf-8', newline='') as f:
                csv.writer(f).writerows(rows)
            sp = self._spec()
            sp['headline_style'] = 'bar_yoy'
            sp['headline'] = [_c(_TOT, '衍生品当月成交合计')]
            # 第二条 mix 让 ⑤ 那一段印出来；外汇期货合计从丁组挪进这一组声明
            d = _grp(sp, _GZ_AST)
            d['cols'] = [c for c in d['cols'] if c['col'] != _FXF]
            sp['groups'].append({'zh': '己·外汇',
                                 'cols': [_c(_FXF, '外汇期货合计'), _c(_CNH, 'USD/CNH 期货')],
                                 'mix': {'total': _FXF, 'parts': [_CNH], 'residual_zh': '其他外汇'}})
            page, pay = _page_payload(sp, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual([(d['gz'], d['share_drawn']) for d in page.mix_folded], [(_GZ_DER, False)])
        own = [e['title'] for e in pay['exhibits'] if _in_group(e, _GZ_DER)]
        self.assertTrue(own, '样例失效：这一组真的一张图都没有了')
        notes = _notes_txt(pay)
        self.assertIn('2 张占比堆叠（同一个合计的 2 种切法）本轮一张也没画成', notes)
        self.assertIn('这一组的合计柱与占比堆叠这一次一张都没有', notes)
        self.assertNotIn('这一组这一次一张图都没有', notes)

    # ── 缺省逐字节不变 ──────────────────────────────────────────────────────────
    def test_plain_mix_text_unchanged(self):
        """不写 alt_splits 的 mix：标题、合计柱的反向指引、页尾 ⑤ 三处逐字是原样。"""
        _p, pay = _page_payload(self._spec(alt_splits=None, split_zh=None))
        i = _idx(pay, self._TOTAL_TITLE, 'gs_bar')[0]
        share = pay['exhibits'][i + 1]
        self.assertEqual(share['title'], f'{_GZ_DER}：各分项占比（分母 = 当月成交合计，堆叠 = 100%）')
        self.assertIn(f'各分项的构成见 Exhibit {share["n"]}（100% 占比堆叠）—— 本图只讲规模，'
                      f'那张只讲结构。', pay['exhibits'][i]['note'])
        self.assertIn('⑤ 声明了 <code>mix</code> 的组出<b>两张</b>：', _notes_txt(pay))

    def test_live_pages_without_alt_splits_keep_share_titles(self):
        pat_share = re.compile(r'^.+：各分项占比（分母 = .+，堆叠 = 100%）$')
        pat_abs = re.compile(r'^.+：各分项绝对值堆叠（柱高 = .+）$')
        seen = 0
        for t in _live_tickers(exclude=('sgx',)):
            sp = self.S.load_spec(t)
            if any((g.get('mix') or {}).get('alt_splits') for g in sp['groups']):
                continue
            _p, pay = _page_payload(sp)
            for e in pay['exhibits']:
                if e['kind'] != 'stacked_dual':
                    continue
                seen += 1
                with self.subTest(page=t, n=e['n']):
                    self.assertTrue(pat_share.match(e['title']) or pat_abs.match(e['title']),
                                    e['title'])
        self.assertGreater(seen, 0, '现网没扫到一张占比堆叠 —— 测试无效')


class TestSgxOwnerLayout(unittest.TestCase):
    """活的 /sgx/：页面所有者 2026-09-12 要的那几处布局。只读 spec、建到临时目录。

    按**列名**找组、按 spec 里的中文名拼标题 —— 组名与图号一个都不写死：组名随时可能
    带现算后缀，图号随任何一次增删图整体位移，两样写死都会在下一轮改版时静默过期。
    """

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls.pay, cls.err = None, None
        cls.tmp = tempfile.mkdtemp(prefix='tg_sgx_')
        # SpecError 是 SystemExit：在 setUpClass 里漏出去会越过 unittest 的 `except Exception`
        # 把整个 preflight 进程带走，一条结果都不留。所以接住、留到 setUp 里以失败报出来。
        # 接的是 SystemExit 而不只是 SpecError：brief.render() 的字数护栏与量价分解的
        # 恒等式护栏抛的都是裸 SystemExit，spec 哪天加了 brief 就会走到那一支。
        try:
            cls.spec = single.load_spec('sgx')
            out = single.build(copy.deepcopy(cls.spec), out_dir=cls.tmp, quiet=True)
            if out:
                with open(out, encoding='utf-8') as fh:
                    m = re.search(r'window\.DASH = (.*);\n?$', fh.read(), re.S)
                cls.pay = json.loads(m.group(1))
        except SystemExit as e:
            cls.err = str(e)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        if self.err is not None:
            self.fail(f'活的 sgx spec 建不出来：{self.err[:600]}')
        if self.pay is None:
            self.skipTest('sgx 本轮门槛没到（等数据，不是 spec 写错）')

    def _by_name(self):
        """列名 → 列配置，与 Page 的 `by_name` 同序（headline 在前、后声明的覆盖先声明的）。"""
        d = {c['col']: c for c in self.spec['headline']}
        for g in self.spec['groups']:
            d.update({c['col']: c for c in g['cols']})
        return d

    def _group_of_total(self, col):
        hits = [g for g in self.spec['groups'] if (g.get('mix') or {}).get('total') == col]
        self.assertEqual(len(hits), 1, f'以 {col} 为合计的 mix 组应恰好一个，实有 {len(hits)} 个')
        return hits[0]

    def test_owner_switches_declared(self):
        self.assertEqual(self.spec.get('headline_style'), 'none')
        self.assertIs(self._group_of_total(_TOT).get('stock_inline'), True)

    def test_no_opening_headline_charts(self):
        ex = self.pay['exhibits']
        openers = {f'{c["zh"]}：{s}' for c in self.spec['headline']
                   for s in ('全历史与近 3 年分位带', '全历史水平值与单月同比', '单月同比')}
        self.assertEqual([e['title'] for e in ex if e['title'] in openers], [])
        self.assertEqual([e['n'] for e in ex
                          if any('P90' in str(s.get('name')) for s in e.get('series') or [])], [])
        self.assertEqual(ex[0]['n'], 2)
        self.assertTrue(_in_group(ex[0], self.spec['groups'][0]['zh']), ex[0]['title'])
        for c in self.spec['headline']:
            with self.subTest(season=c['zh']):
                self.assertEqual(len(_idx(self.pay, f'{c["zh"]}：与同月常态比', 'seasonality')), 1)
        txt = _notes_txt(self.pay)
        self.assertIsNone(re.search(r'Exhibit\s*\d+\s*的灰色分位带', txt))
        self.assertNotIn('开篇图是', txt)

    def test_deriv_group_block(self):
        """合计柱 → 按期货 / 期权 / 掉期 → 按资产类别 → 月末未平仓，四张连号，都在季节性之前。"""
        g = self._group_of_total(_TOT)
        gz, m, by = g['zh'], g['mix'], self._by_name()
        self.assertTrue(gz.startswith('衍生品成交与未平仓'), gz)
        tot, oi = by[_TOT]['zh'], by['deriv_oi_contracts']['zh']
        split = m.get('split_zh') or ''
        for w in ('期货', '期权', '掉期'):
            self.assertIn(w, split)
        alts = [a for a in m.get('alt_splits') or [] if '资产类别' in a['zh']]
        self.assertEqual(len(alts), 1, '「按资产类别」那一刀应恰好一条')
        self.assertEqual(set(alts[0]['parts']), {_EQX, _FXF, _CMD})
        self.assertTrue(alts[0].get('residual_zh'))
        i = _idx(self.pay, f'{gz}：{tot} —— 水平值与单月同比', 'gs_bar')
        self.assertEqual(len(i), 1, '衍生品当月成交合计柱应恰好一张')
        i = i[0]
        self.assertEqual(_titles(self.pay)[i:i + 4], [
            ('gs_bar', f'{gz}：{tot} —— 水平值与单月同比'),
            ('stacked_dual', f'{gz}：{split}（分母 = {tot}，堆叠 = 100%）'),
            ('stacked_dual', f'{gz}：{alts[0]["zh"]}（分母 = {tot}，堆叠 = 100%）'),
            ('gs_bar', f'{gz}：{oi}（存量，期末口径）')])
        self.assertLess(i + 3, _season0(self.pay), '月末未平仓还排在季节性之后')
        ex = self.pay['exhibits']
        self.assertEqual(sum(1 for e in ex if e['title'].endswith(f'：{oi}（存量，期末口径）')), 1)
        self.assertEqual(len(ex[i + 1]['stacks']), 3)
        # 2026-09-12 审稿后删了期权那条右轴线：SINGLE_SPEC §1.5 第 5 条的 tmx 反面判例
        # （常年 3%–12% 的一段在堆叠里量得出来 ⇒ 不给线），期权这一段与它同一量级。
        self.assertIsNone(ex[i + 1].get('line'),
                          '「按期货 / 期权 / 掉期」那张又画了右轴线 —— 期权段在堆叠里读得出来，'
                          '按 §1.5 第 5 条不给线')
        self.assertEqual(len(ex[i + 2]['stacks']), 4)
        self.assertEqual([e['title'] for e in ex if _in_group(e, gz) and e['kind'] in _LINE_KINDS], [])
        # 页尾排序那句要把本组**全部** 3 张流量图点到（夹具那一组只有一张流量图，只点第一张
        # 的变体在夹具上测不出来 —— 2026-09-12 变异测试实测，所以在活页上钉）。
        notes = _notes_txt(self.pay)
        self.assertIn(f'「{gz}」组的存量图（Exhibit {ex[i + 3]["n"]}）按组的顺序就地排列，'
                      f'紧跟本组的流量图（Exhibit {ex[i]["n"]}、{ex[i + 1]["n"]}、{ex[i + 2]["n"]}）',
                      notes)
        # 两张占比图互指的那句不许替 spec 说「没有声明包含关系」—— 本页 spec 恰恰写明了
        for e in ex[i + 1:i + 3]:
            self.assertNotIn('spec 没有声明', e['note'])

    def test_eqidx_fx_commodity_groups_are_total_bar_plus_share(self):
        by = self._by_name()
        for col in (_EQX, _FXF, _CMD):
            with self.subTest(total=col):
                g = self._group_of_total(col)
                gz, tot = g['zh'], by[col]['zh']
                i = _idx(self.pay, f'{gz}：{tot} —— 水平值与单月同比', 'gs_bar')
                self.assertEqual(len(i), 1, f'「{gz}」的合计柱应恰好一张')
                nxt = self.pay['exhibits'][i[0] + 1]
                self.assertEqual(nxt['kind'], 'stacked_dual')
                self.assertTrue(nxt['title'].startswith(gz + '：')
                                and nxt['title'].endswith(f'（分母 = {tot}，堆叠 = 100%）'),
                                nxt['title'])
                self.assertEqual([e['title'] for e in self.pay['exhibits']
                                  if _in_group(e, gz) and e['kind'] in _LINE_KINDS], [])
        m = self._group_of_total(_CMD)['mix']
        self.assertEqual(m['parts'], ['vol_iron_ore_contracts'], '商品那张是「铁矿石 vs 其他商品」')
        self.assertTrue(m.get('residual_zh'))

    def test_rates_futures_is_its_own_single_bar(self):
        col = 'vol_rates_futures_contracts'
        gs = [g for g in self.spec['groups'] if any(c['col'] == col for c in g['cols'])]
        self.assertEqual(len(gs), 1)
        g = gs[0]
        self.assertTrue(g['zh'].startswith('利率期货'), g['zh'])
        self.assertEqual([c['col'] for c in g['cols'] if not c.get('stock')], [col],
                         '利率期货那一组只能有它一条流量列（单桶 ⇒ gs_bar）')
        zh = next(c['zh'] for c in g['cols'] if c['col'] == col)
        self.assertEqual(len(_idx(self.pay, f'{g["zh"]}：{zh}', 'gs_bar')), 1)

    def test_no_lines_chart_left_for_the_four_groups(self):
        """原 Exhibit 11 / 12 / 15 / 16 那四张折线一张不剩 —— 按组名、也按序列名各查一遍
        （组名哪天改了，序列名那一道仍然兜得住）。"""
        by = self._by_name()
        cols = (_TOT, _FUT, _OPT, _EQX, _FXF, _CMD, _A50, _N225, _MSG, _CNH,
                'vol_inrusd_futures_contracts', 'vol_iron_ore_contracts',
                'vol_rates_futures_contracts')
        names = {by[c]['zh'] for c in cols if c in by}
        gzs = [self._group_of_total(c)['zh'] for c in (_TOT, _EQX, _FXF, _CMD)]
        bad = [(e['n'], e['title']) for e in self.pay['exhibits'] if e['kind'] in _LINE_KINDS
               and (any(_in_group(e, gz) for gz in gzs)
                    or any(s.get('name') in names for s in e.get('series') or []))]
        self.assertEqual(bad, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
