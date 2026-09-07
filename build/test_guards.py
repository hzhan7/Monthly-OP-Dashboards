# -*- coding: utf-8 -*-
"""build/payload_guard.py + build/brief.py 两条护栏的单元测试。

跑法: python3 build/test_guards.py        （只用标准库 + numpy，不需要 pytest）

这套测试是为「把 MOPS 官方增减原因原文写进 brief」那次改造建的，守两件事：

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



if __name__ == '__main__':
    unittest.main(verbosity=2)
