# -*- coding: utf-8 -*-
"""联发科（MediaTek，2454.TW）月度营收页配置 —— TSM 图列底座（`build/mrbase.py`）的一份 spec。

本文件只有**数据与本家专属的事实**，没有一行图型逻辑。位置 `build/mrspecs/mtk.py`。

━━ 结构：与 /tsm/ 那份 spec 的三处差别 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **没有 `fx`** ⇒ 底座整体不出 Ex5（NT$ vs US$ 单月同比）/ Ex6（汇率贡献）/
   Ex8（月均汇率），后面的图编号顺次前移。**不写进 `skip`**：`skip` 是给
   「腿在、口径上仍决定不画」用的，本页是这条腿根本不存在，底座的 `build_exhibits()`
   已按 `has_fx` 结构性排除、页尾也已印出「本页没有美元折算腿」那一条通稿；
   再写一遍 `skip` + `skip_note` 会让同一件事在页尾出现两次。本家专属的证据在 `_N_NOFX`。
2. **没有 `official_yoy`** —— 但**公司其实公告 y/y**（见 `_N_YOY`）。留空的理由是
   `series/mtk.csv` 只存了金额一列，y/y 是它的派生量，不是第二个独立事实。
3. **没有 `guidance` / `brief_extra`** —— 公司每季给的是新台币绝对区间 + 假设汇率
   （3Q26：NT$152.2bn–159.8bn，假设 32 NT$/US$），形式上够拼一条指引桥；不做的原因是
   `series/` 里没有一份可复跑的指引源表（见 `_N_NOGUIDE`）。

━━ 本轮逐条回原始文件核过的事实（每条都注明看的是哪一份、哪一行）━━━━━━━━━
· 年度合并营收 Net sales（千元）：2018/2017 → FY2018 合并财报 p.「Net sales」行
  238,057,346 / 238,216,318；2020/2019 → FY2020 同一行 322,145,988 / 246,221,731；
  2022/2021 → FY2022 同一行 548,796,030 / 493,414,582；2024/2023 → FY2024 同一行
  530,585,886 / 433,446,330。**2025 的审计年报本轮没拿到**，只从公司 IR 月营收表的
  全年累计读到百万元精度 595,966 —— 故与前七年分开登记、按百万元比（见 `_ANNUAL_*`）。
· 本表 103 个月与公司 IR 月营收表（mediatek.com「Financial Information」月度表，
  2008-01 起逐年一张，单位 NTD Million）**逐格相等，0 处不符**；同表印的
  YoY Changes% 与本页按 `build/yoy.py` 自算之差，91 个可比月份上最大 0.0095pp。
· 三条断点的日期与金额：FY2020 附注 (32)「Losses control of subsidiary」（奕力，
  2020-07-31 董事会决议 US$138mn、2020-11-30 完成股权移转、处分利益 206,451 千元）；
  FY2022 附注 (33)「Loss of control of subsidiary」+ 合并个体注记 31（星宸，2021-01-27
  决议 US$115mn、2021-02 丧失控制、处分标的资产负债表日 2021-02-28）；FY2024
  「企业合并」附注（IC+，2024-07-01 取得实质控制、并表期间贡献 338,827 千元、
  全年备考 530,891,100 vs 实际 530,585,886）。
· **「2018-01 是 IFRS 15 准则边界」这条站不住**，本轮从 FY2018 转换附注原文证伪，
  见 `_N_START`。上一版 `build/specs/mtk.py` 里那句话是错的，不要再继承。

━━ 图注里的数 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
能从 `series/mtk.csv` 算出来的**一个都不写死**，全部 import 期现算；读不到源退回不含
数字的定性版本，**绝不在 import 期抛异常**（一份 spec 炸掉会带走整批 `--all`）。
写成字面量的只有两类，且都注明出处：**外部披露事实**（审计年报的 Net sales、年报附注
给的子公司营收与并表贡献额）与**本轮的外部核对结果**（份数 + 覆盖区间，它们不在
`series/` 里，构建期复算不了 —— 所以带区间写，过期时看得出来）。

注：下面用了同包的 `_facts._rows` / `_facts._f` 两个下划线开头的读表器，理由是不想在
spec 里抄第四份 CSV 解析；所有调用都包在 try/except 里，它们哪天改名或挪走，
本文件只会退回定性版本，不会炸 import。
"""
from . import _facts

_CSV = 'mtk.csv'
_COL = 'revenue_ntd_mn'

# ══════════════════════════════════════════════════════════════════════════════
# 外部事实（字面量 = 官方文件上读到的数，逐条注明出处）
# ══════════════════════════════════════════════════════════════════════════════
#: 经会计师查核的合并财报综合损益表「Net sales」行（NT$ thousand）。
#: 四份合并财报：FY2018&2017、FY2020&2019、FY2022&2021、FY2024&2023。
_ANNUAL_AUDITED_K = {
    2018: 238_057_346, 2019: 246_221_731, 2020: 322_145_988, 2021: 493_414_582,
    2022: 548_796_030, 2023: 433_446_330, 2024: 530_585_886,
}
#: 2025 只拿到百万元精度（公司 IR 月营收表的全年累计 = 4Q25 业绩新闻稿的全年数），
#: 审计年报本轮未核 —— 与上面那批分开登记，按百万元比。
_ANNUAL_ANNOUNCED_MN = {2025: 595_966}

#: 公司公告的季度合并营收（NT$ bn，法说会讲稿口径，一位小数）。用来验「月度加总 = 季报营收」。
#: 2Q26 业绩电话会讲稿："Revenue for the quarter was NT$152.2 billion dollars"。
_QTR_ANNOUNCED_BN = {(2026, 2): 152.2}

#: 奕力（ILI）2019 年营业收入，NT$ thousand。出处：2019 年报「关系企业营运概况」表。
#: 被处分的是 ILI Technology Holding Corporation 这一整支，所以另记一个整支相加的数
#: （10,695,950 + 189,081 + 122,546 + 7,928，含集团内部交易的重复计算，只会更高）。
_ILI_FY2019_K = 10_695_950
_ILI_GROUP_FY2019_K = 11_015_505

#: 星宸（Sigmastar）2020 年营业收入合计，NT$ thousand。出处：2020 年报同一张表 ——
#: 厦门星宸 6,645,994 + 深圳芯辰 24,500 + 星宸科技（上海）100,558。
_SIGMA_FY2020_K = 6_771_052

#: IC PLUS（IC+）。出处：FY2024 合并财报「企业合并」附注 ——「From the acquisition date,
#: July 1, 2024, to December 31, 2024, IC+ has contributed NT$338,827 thousand to the
#: Company's revenue」；同附注的全年备考营收 530,891,100 千元 vs 实际 530,585,886 千元。
_ICPLUS_H2_2024_K = 338_827
_ICPLUS_PROFORMA_FY2024_K = 530_891_100

#: 本轮的外部核对结果（构建期复算不了：官方月表不在 series/ 里，所以带覆盖区间登记）。
#: 逐格比对公司 IR 月营收表：金额 0 处不符；官方 YoY Changes% 与自算值最大差 0.0095pp。
_XCHECK = {'months': 103, 'from': '2018-01', 'to': '2026-07',
           'mismatch': 0, 'yoy_n': 91, 'yoy_max_pp': 0.0095}


# ══════════════════════════════════════════════════════════════════════════════
# 构建期现算（拿不到一律 None，调用方退回定性版本）
# ══════════════════════════════════════════════════════════════════════════════
def _series():
    """{'YYYY-MM': NT$mn}。用同包的读表器，不在这里抄第四份 CSV 解析。"""
    try:
        rs = _facts._rows(_CSV)
        if not rs:
            return {}
        out = {}
        for r in rs:
            v = _facts._f(r.get(_COL))
            if v is not None:
                out[r['month']] = v
        return out
    except Exception:                        # noqa: BLE001 —— import 期一律不抛
        return {}


def _sum(s, months):
    return sum(s[m] for m in months) if all(m in s for m in months) else None


def _year(s, y):
    return _sum(s, [f'{y}-{k:02d}' for k in range(1, 13)])


def _annual_recon(s):
    """逐年「月度加总 vs 官方年度营收」→ (年数, 最大 diff NT$mn, 最大相对偏差 %)。"""
    n, worst, worst_pct = 0, 0.0, 0.0
    for y, k in _ANNUAL_AUDITED_K.items():
        tot = _year(s, y)
        if tot is None:
            continue
        off = k / 1000.0
        n += 1
        d = tot - off
        if abs(d) > abs(worst):
            worst = d
        worst_pct = max(worst_pct, abs(d) / off * 100.0)
    for y, mn in _ANNUAL_ANNOUNCED_MN.items():
        tot = _year(s, y)
        if tot is None:
            continue
        n += 1
        d = tot - mn
        if abs(d) > abs(worst):
            worst = d
        worst_pct = max(worst_pct, abs(d) / mn * 100.0)
    return (n, worst, worst_pct) if n else None


def _qtr_recon(s):
    """逐季「月度加总 vs 公司公告季度营收」→ [(季标签, 加总 NT$bn, 公告 NT$bn)]。"""
    out = []
    for (y, q), bn in sorted(_QTR_ANNOUNCED_BN.items()):
        tot = _sum(s, [f'{y}-{k:02d}' for k in range(3 * q - 2, 3 * q + 1)])
        if tot is not None:
            out.append((f'{y}Q{q}', tot / 1000.0, bn))
    return out


def _pct(numer_k, denom_k):
    return numer_k / denom_k * 100.0 if denom_k else None


def _plus(month, k):
    """'YYYY-MM' + k 个月。断点污染的同比窗口由它现算，不写死区间。"""
    y, m = int(month[:4]), int(month[5:7])
    t = (y * 12 + m - 1) + k
    return f'{t // 12:04d}-{t % 12 + 1:02d}'


_S = _series()
_M0 = min(_S) if _S else None
_M1 = max(_S) if _S else None
_RECON = _annual_recon(_S)
_QREC = _qtr_recon(_S)
try:
    _D = _facts.days_effect(_CSV, _COL)
    _YX = _facts.yoy_extremes(_CSV, _COL)
except Exception:                            # noqa: BLE001
    _D = _YX = None

# ── 三条断点的量级：分子是上面登记的外部事实，分母现算或取官方年度数，比值**不写死**。
_ILI_PCT = _pct(_ILI_FY2019_K, _ANNUAL_AUDITED_K[2019])
_ILI_GRP_PCT = _pct(_ILI_GROUP_FY2019_K, _ANNUAL_AUDITED_K[2019])
_SIGMA_PCT = _pct(_SIGMA_FY2020_K, _ANNUAL_AUDITED_K[2020])
_H2_2024 = _sum(_S, [f'2024-{k:02d}' for k in range(7, 13)])          # NT$mn
_ICPLUS_PCT = (_ICPLUS_H2_2024_K / 1000.0 / _H2_2024 * 100.0) if _H2_2024 else None
#: 备考差额 = IC+ 在 2024 上半年本来会贡献的营收；加上下半年实际贡献 = 它的全年规模。
_ICPLUS_FY_K = _ICPLUS_PROFORMA_FY2024_K - _ANNUAL_AUDITED_K[2024] + _ICPLUS_H2_2024_K
_ICPLUS_FY_PCT = _pct(_ICPLUS_FY_K, _ANNUAL_AUDITED_K[2024])


# ══════════════════════════════════════════════════════════════════════════════
# 断点标签：图上只挂月份，这句 zh 由底座的 break_note() 印进图注；整段量化在 _N_BRK。
# 三句都保持一行长度 —— 它们会被「；」串成一段接在 Ex2/Ex3/Ex4/Ex5 四张图的图注后面。
# ══════════════════════════════════════════════════════════════════════════════
def _b_ili():
    s = '奕力科技（ILI）出表 —— 2020-11-30 完成股权移转，自本月起不再并表'
    return s + (f'；规模<b>上界</b> ≈ 上年合并营收的 {_ILI_PCT:.1f}%'
                if _ILI_PCT else '；规模见页尾断点条')


def _b_sigma():
    s = ('星宸科技（Sigmastar）出表 —— 2021-02-24 移转完成、丧失控制，'
         '线画在<b>最早可能受影响</b>的月份')
    return s + (f'；规模<b>上界</b> ≈ 上年合并营收的 {_SIGMA_PCT:.1f}%'
                if _SIGMA_PCT else '；规模见页尾断点条')


def _b_icplus():
    s = 'IC PLUS（IC+）并表 —— 2024-07-01 取得实质控制，自本月起并入'
    return s + (f'；并表期间贡献 = 同期月营收的 {_ICPLUS_PCT:.2f}%（附注给的准数，不是上界）'
                if _ICPLUS_PCT else '；规模见页尾断点条')


# ══════════════════════════════════════════════════════════════════════════════
# 页尾说明（底座把 spec['notes'] 追加在它自己那几条之后）
# ══════════════════════════════════════════════════════════════════════════════
_N_SRC = (
    '<b>数据源与落库精度。</b>主源是联发科投资人关系页的<b>月度营收新闻稿 PDF</b>'
    '（<code>Monthly Sales Revenue &lt;Month&gt;, &lt;YYYY&gt;.pdf</code>），公告的是'
    '<b>合并营收、新台币百万元整数、未经会计师查核</b>，正文注明合并个体为联发科及其'
    '子公司；同一页的<b>年度月营收表</b>（2008 年起逐年一张）与年度汇总 PDF 作回补与交叉'
    '核对，另与 TWSE OpenAPI／MOPS 月营收月表对读。'
    f'本轮把本表 {_XCHECK["months"]} 个月（{_XCHECK["from"]} 至 {_XCHECK["to"]}）'
    f'逐格与公司 IR 月营收表比对：<b>{_XCHECK["mismatch"]} 处不符</b>。'
    'MOPS 与 TWSE OpenAPI 给的是<b>千元</b>精度，但千元只有较新的月份拿得到 —— 主源与'
    '年度表都只印到百万元；混着存会让序列的有效位随月份跳变、而任何一张图都看不出来，'
    '所以统一存整数百万元，代价在下一条里量化。'
    '台湾《证券交易法》要求上市公司次月 10 日前公告上月营收（遇假日顺延），'
    '所以本页的更新节奏由法定披露日决定，不由任何抓取排程决定。')

if _RECON:
    _n, _w, _wp = _RECON
    _qtxt = ('季度桥另有一处直接对读：'
             + '；'.join(f'{lab} 月度加总 NT${tot:,.1f}bn vs 公告 NT${off:,.1f}bn'
                         for lab, tot, off in _QREC) + '。') if _QREC else ''
    _N_ADD = (
        '<b>本页的季度聚合、YTD 与 12 个月滚动同比是实测过的，不是推定。</b>'
        f'{_n} 个完整年度可与官方年度营收逐年对账（2018–2024 取经会计师查核的合并报表 '
        'Net sales，2025 取公司公告的全年累计）：月度加总与官方数最大只差 '
        f'<b>{abs(_w):,.3f} NT$mn</b>（{_wp:.5f}%），残差正负都有，'
        '全部落在「12 个月各带 ±0.5 百万元舍入」的理论上界 ±6 之内 —— '
        '也就是说这点残差<b>全部</b>来自公司只公告到百万元整数，一分钱都不是口径缺口。'
        + _qtxt +
        '联发科合并财报附注写明母公司的功能货币与表达货币<b>均为新台币</b>，'
        '月营收是<b>原生记账数</b>而不是折算值 —— 这一点与世芯-KY（3661）相反，'
        '那家同一检验差 +0.378%（功能货币是美元、新台币月营收是逐月折算值），'
        '季度聚合与 YTD 在那一页是非法的。'
        '⇒ 本页把主序列声明为可加总（<code>value.summable=True</code>）是有据的。'
        '⚠️ 一个副作用说清楚：本页的 QTD／YTD 由百万元整数相加而来，与公司公告的累计数'
        '可能差 1 NT$mn（公司是先加千元再舍入），量级 0.0005% 以内。')
else:
    _N_ADD = (
        '<b>本页的季度聚合、YTD 与 12 个月滚动同比是合法的。</b>月度加总与官方年度营收'
        '逐年对得上，残差只来自「公司公告到百万元整数」的逐月舍入；联发科合并财报附注'
        '写明母公司功能货币与表达货币均为新台币，月营收是原生记账数、不是折算值。'
        '（本次未能从 CSV 现算出对账残差，故只作定性表述。）')

_N_YOY = (
    '<b>补一句：公司的月度公告其实印了 y/y，本页留空 <code>official_yoy</code> 是因为'
    '本表只存金额一列。</b>月度新闻稿正文表格与 IR 的年度月营收表都有 YoY Changes% 一列'
    '（例：2026-07 印 12.16%）。y/y 是金额这一列的<b>派生量</b>、不是第二个独立事实，'
    '存进 <code>series/mtk.csv</code> 等于把同一个事实存两遍，所以本页统一走 '
    '<code>build/yoy.py</code> 自算。'
    f'两者本轮逐月核过：{_XCHECK["yoy_n"]} 个可比月份'
    f'（{_plus(_XCHECK["from"], 12)} 至 {_XCHECK["to"]}）上最大差 '
    f'<b>{_XCHECK["yoy_max_pp"]:.4f}pp</b>，差的那点是公告只印两位小数的舍入。'
    '⇒ 页内确实没有「公司原值 vs 自算值」的分歧，但理由是<b>两者本来就是同一个算式</b>，'
    '不是「公司没公告过 y/y」。')

_N_BRK = (
    '<b>2018-01 之后的三次合并范围变动，逐条量化后登记成红色竖虚线。</b>'
    '三次都是<b>当期起生效、比较期不重编</b>，所以受影响的是跨断点那 12 个月的<b>同比</b>，'
    '不是水平值本身。'
    '<br>① <b>2020-12 奕力科技（ILI Technology）出表</b> —— 2020-07-31 董事会决议以 '
    'US$138mn 出售 ILI Technology Holding Corporation，2020-11-30 完成股权移转、'
    '认列处分利益 NT$206,451 千元（FY2020 合并财报附注「Losses control of subsidiary」：'
    '"On November 30, 2020, the Company has completed the transfer of shareholding rights '
    'of ILI Technology Holding Corporation."）。规模：2019 年报「关系企业营运概况」表里，'
    '营运主体 ILI Technology Corporation 的营业收入 NT$10,696mn'
    + (f'，约当当年合并营收的 <b>{_ILI_PCT:.1f}%</b>' if _ILI_PCT else '')
    + '；被处分的是它上面那整支控股，同表四家相加 NT$11,016mn'
    + (f'（{_ILI_GRP_PCT:.1f}%）' if _ILI_GRP_PCT else '')
    + '，但那个和里含集团内部交易的重复计算。'
      f'受污染的单月同比窗口：{_plus("2020-12", 0)} 至 {_plus("2020-12", 11)}。'
      '<br>② <b>2021-02 星宸科技（Sigmastar）出表</b> —— 2021-01-27 董事会决议以 US$115mn '
      '出售 16% 股权，2021-02-24 完成移转、丧失控制，剩余 34% 改按权益法（合并个体注记：'
      '"…had been deconsolidated by the Company since February 2021 as the Company lost '
      'control over them."）。规模：2020 年报同一张表，厦门星宸 NT$6,646mn + 深圳芯辰 '
      'NT$25mn + 星宸（上海）NT$101mn = NT$6,771mn'
    + (f'，约当当年合并营收的 <b>{_SIGMA_PCT:.1f}%</b>' if _SIGMA_PCT else '')
    + f'。受污染的单月同比窗口：{_plus("2021-02", 0)} 至 {_plus("2021-02", 11)}。'
      '⚠️ <b>这条线的月份有一格的不确定</b>：附注一边说「自 2021 年 2 月起不再合并」，'
      '一边把处分标的的资产负债表日期写成 <b>2021-02-28</b>（照后者读，2 月损益仍在合并数里，'
      '第一个干净的月份是 2021-03）。断点线的语义是「从这一期起与左侧不可比」，'
      '所以按<b>最早可能受影响</b>的月份放在 2021-02（同一条规则用在奕力身上给出 2020-12、'
      '用在 IC+ 身上给出 2024-07，三条一致）；若按「第一个干净月」读，这条线应右移一个月。'
      '<br>③ <b>2024-07 IC PLUS（IC+）并表</b> —— 子公司络达持股自 0.94% 增至 29.26%、'
      '加上联发科自持 13.61%，并因过半董事席次自 2024-07-01 取得实质控制'
      '（FY2024 合并财报「企业合并」附注）。规模：同附注给的<b>并表期间贡献额</b> NT$339mn'
    + (f'，= 2024 下半年月营收合计的 <b>{_ICPLUS_PCT:.2f}%</b>' if _ICPLUS_PCT else '')
    + '；同附注另给全年备考营收 530,891mn vs 实际 530,586mn，两者反推 IC+ 全年规模约 '
      f'NT${_ICPLUS_FY_K / 1000.0:,.0f}mn'
    + (f'（{_ICPLUS_FY_PCT:.2f}%）' if _ICPLUS_FY_PCT else '')
    + f'。受污染的单月同比窗口：{_plus("2024-07", 0)} 至 {_plus("2024-07", 11)}。'
      '<br>⚠️ <b>①② 的百分比是上界，不是净影响</b>：分子取的是这些子公司<b>自身</b>的'
      '营业收入（年报「关系企业营运概况」表），<b>未扣除对集团内其他公司的销货冲销</b>，'
      '而合并营收里本来就没有那部分。公司从未披露这两家对合并营收的净贡献额，'
      '所以这里只给得出上界 —— 真实缺口 ≤ 这个数，<b>不要拿它去减增速</b>。'
      '③ 不同：那是企业合并附注直接给的并表期间贡献额，是准数，所以它的标签写等号。'
      '<br>季度图上这三条线由底座按「断点月所在季」映射到 2020Q4 / 2021Q1 / 2024Q3，'
      '与「最早可能受影响」的约定一致 —— 读季度图时请记得 2020Q4 的前两个月仍含奕力。')

_N_START = (
    f'<b>序列起点 {_M0 or "2018-01"} 是上游的落库边界，不是「最早可得」。</b>'
    '公司 IR 页的年度月营收表一直回溯到 2008 年，MOPS 月表也存着 2016-01 起的更早月份'
    '（本轮核过：2017 年 12 个月相加 = NT$238,216mn，与 FY2018 合并财报里 2017 年的'
    '比较数 238,216,318 千元<b>逐字相等</b>），所以「取不到」不是理由。'
    '<br>⚠️ 有一种说法是「2018-01 是 IFRS 15 的准则边界」，本轮核下来<b>站不住</b>，'
    '本页不再沿用：FY2018 合并财报的转换附注原文写着「IFRS 15 has <b>no impact</b> on '
    "the Company's revenue recognition from sale of goods」；实际影响是（a）预收款重分类"
    '到合约负债 NT$1,058mn（纯资产负债表科目搬家）、（b）劳务收入按完工比例的差异使'
    '期初保留盈余减少 NT$211mn（≈ 一年营收的 0.09%，且进的是权益不是营收）。'
    '同一份报表里 2017 与 2018 的 Net sales 并排列示、未重编。'
    '<br>真正让 2016–2017 与 2018 之后不可比的是<b>合并范围</b>：立錡科技并入、傑發科技'
    '（AutoChips）出表都发生在那两年（2019 年报「重要契约」表有「Ralink (Samoa) 处分 '
    'AutoChips 约 82.9% 股权，协议自 2016-05-13 起」这一行）。'
    '<b>但这两次变动的确切并表／出表月份本轮没有从官方原文核到</b>，所以它只作为'
    '「本页不往前接」的动机记录在这里，<b>不写成已核实的事实断言</b>，也没有登记进 '
    '<code>breaks</code> —— 登记一条自己没核实月份、而且左右两侧都不在本页上的断点线，'
    '比不登记更容易误导。'
    '<br>因此 <code>window.x_from</code> 显式写 <code>None</code>（= 用序列自己的起点），'
    '不是漏写：副标题里的「共 N 个月」与各图首格因此天然一致，'
    f'全历史图标题里的 {(_M0 or "2018-01")[:4]} 年是<b>本页口径的起点</b>，'
    '不是公司历史的起点。')

if _D:
    _N_DAYS = (
        '<b>读单月读数之前先看农历年落在哪个月，并且本页不做日均化。</b>'
        '农历年（连同台湾年假与下游拉货节奏）在 1 月与 2 月之间来回移动，把出货整块搬运，'
        '2 月本身天数还少 2-3 天 —— 这是台股月营收单月同比毛刺的第一大来源。'
        '看上去正该按天数归一化把这一层除掉，但这个假设被本页数据自己否掉：'
        f'<code>(m/m) ~ (天数变化%)</code> 在本序列 {_D["n"]} 个月上的回归斜率是 '
        f'<b>{_D["slope"]:.2f}</b> 而不是 1；2 月对相邻 1、3 月均值的实际比值 '
        f'<b>{_D["feb"]:.2f}</b>（{_D["feb_n"]} 个年度平均），同口径的天数比值却是 '
        f'{_D["feb_days"]:.2f} —— 2 月掉下去的幅度远超它少的那两三天。'
        '联发科是无晶圆厂设计公司，营收按出货认列，日历日与产出之间本来就没有机械关系；'
        '天数只是农历年与季末拉货日历的<b>代理变量</b>，按天数除一遍会把农历年效应'
        '算成「经营性走弱」。这也是月营收柱图右轴走 12 个月滚动合计同比、'
        '而不是单月同比的理由之一：任意连续 12 个月覆盖同样的日历，农历年错位自己抵消掉。')
else:
    _N_DAYS = (
        '<b>读单月读数之前先看农历年落在哪个月，并且本页不做日均化。</b>农历年在 1 月与 '
        '2 月之间来回移动，把出货在这两个月之间整块搬运，2 月天数还少 2-3 天 —— 这是台股'
        '月营收单月同比毛刺的第一大来源。天数只是农历年与季末拉货日历的代理变量，'
        '不是产出的线性驱动，按天数除一遍会把农历年效应算成「经营性走弱」。'
        '（本次未能从 CSV 现算出斜率，故只作定性表述。）')

_N_NOFX = (
    '<b>补一句证据：本页「没有美元腿」是核过的「没有」，不是「没找到」。</b>'
    '联发科从不公告<b>美元营收金额</b> —— 月度营收公告全部只有新台币；季度业绩新闻稿的'
    '合并损益表里确实有一行 <code>Average Exchange Rate - USD/NTD</code>'
    '（2Q26 法说会讲稿：「the average exchange rate for the second quarter was NT$31.6 '
    'to US$1」），但那是<b>汇率</b>不是美元营收；法说会上其余的美元只出现在'
    '<b>成长率</b>或<b>目标</b>口径里（全年目标是「high-single digit percentage growth '
    'in US dollars」）。这三样都不是可对账的美元营收实绩。'
    '⇒ 拿新台币月营收除以外部牌价折出来的是<b>分析师构造值</b>，没有任何官方数可以对账，'
    '页上任何一处都不会出现那种冒充官方值的线 —— 这与 <code>/tsm/</code> 页不同，'
    '那家每季自报美元营收，所以那一页才有「NT$ vs US$ 单月同比」「汇率贡献」「月均汇率」'
    '三张图。MOPS 上 2454 那行的备注「海外子公司之營收係以當月平均匯率換算之」说的是'
    '海外子公司那一层的折算，不代表公司按美元计价；上面逐年对账的残差只有舍入量级，'
    '正说明这层折算<b>不产生</b>月度与年度之间的口径缺口。')

_N_NOGUIDE = (
    '<b>本页没有指引桥，尽管公司给指引。</b>联发科每季法说会给的是<b>新台币绝对区间 + '
    '假设汇率</b>（3Q26：NT$152.2bn–159.8bn、假设 32 NT$/US$），形式上完全够拼一句'
    '「当季 QTD 已实现 X、距指引中值还差 Y」。不做的原因不是没数据，是仓库里没有一份'
    '可复跑的源表：<code>/tsm/</code> 页那条桥的六列全部来自 '
    '<code>series/tsm_guidance.csv</code>，不是写在配置里的手抄数。把一组季度区间手敲进'
    '配置，等于给构建期加一个没有更新路径、没人复核、也不会随下季自动更新的输入 —— '
    '拼一半的桥比没有桥更容易被读成官方口径。'
    '⇒ 页顶 brief 的第 5 句退回底座自带的趋势位置判断（三月均值同比 vs 单月同比），'
    '它只用本表自己的数。哪天 <code>series/mtk_guidance.csv</code> 落了地，'
    '在本配置里加 <code>guidance</code> + <code>brief_extra</code> 两个字段即可接上。')

if _YX:
    _N_HEAT = (
        '<b>热力矩阵在本页读得出来 —— 这一条是算过的，结论是「勉强」。</b>'
        '引擎的色阶是<b>线性</b>的（t =（v − p5）/（p95 − p5），没有 log 入口），'
        f'所以读不读得出来取决于格子在 t 轴上摊不摊得开。本序列 {_YX["n"]} 个单月同比：'
        f'最低 {_YX["min"]:.1f}%、最高 {_YX["max"]:.1f}%，5/95 分位 {_YX["p5"]:.1f}% / '
        f'{_YX["p95"]:.1f}%；最挤的一段是「最宽 20% 色带里塞了 {_YX["dull"]} 格」，'
        f'占 {_YX["dull_share"]:.0f}% —— 即约三分之一的格子彼此色差不到两成、肉眼分不开，'
        '其余读得出深浅。⇒ 矩阵照出，但<b>请按格内数字读，不要只看颜色排序</b>。')
else:
    _N_HEAT = (
        '<b>热力矩阵请按格内数字读，不要只看颜色排序</b>：引擎的色阶是线性的'
        '（没有 log 入口），同比分布密集的那一段色差不足以逐格分辨。'
        '（本次未能从 CSV 现算出分位与密集度，故只作定性表述。）')


SPEC = {
    'ticker': 'mtk',
    'name': 'MediaTek',
    'tracker': 'MediaTek Monthly Revenue Tracker',
    'title': '联发科 MediaTek (2454.TW)：月度营收跟踪',
    'source': 'Source: MediaTek monthly sales report press releases (mediatek.com), '
              'cross-checked line by line against the company annual monthly-revenue '
              'tables and TWSE MOPS filings; format after Goldman Sachs GIR',
    # 「次月 10 日前」后面那半句不是客套：实测有月份的公告发在 11-12 日（10 日撞假日）。
    'source_zh': '联发科 IR 月度营收新闻稿（合并营收，NT$mn 整数，未经会计师查核，'
                 '台湾法定次月 10 日前公布、遇假日顺延），'
                 '并与公司 IR 年度月营收表、TWSE MOPS 月营收月表逐月交叉核对',
    'csv': _CSV,

    # 唯一的官方披露字段。月营收 / 3MMA / QTD / YTD / 占 TTM 比重全部由它派生。
    'value': {
        'col': _COL, 'div': 1000.0, 'label': 'NT$bn', 'sym': 'NT$',
        'dec': 1, 'raw_label': 'NT$mn', 'raw_dec': 0, 'zh': 'NT$ revenue',
        'ccy_zh': '新台币',
        # 显式 True 有实测撑着（见 _N_ADD）：母公司功能货币与表达货币都是新台币，
        # 月值是原生记账数；逐年加总与合并报表 Net sales 只差舍入。
        'summable': True,
    },

    # 'official_yoy' 不给：公司确实公告 y/y，但本表只存金额一列（见 _N_YOY）。
    # 'alt' / 'segments' 不给：月度披露就是一个合并营收数，没有第二计价列、没有月度分部。
    # 'fx' 不给：没有官方美元营收实绩，不造分析师构造值（见 _N_NOFX）。
    # 'guidance' / 'brief_extra' 不给：series/ 里没有可复跑的指引源表（见 _N_NOGUIDE）。

    'window': {
        # **显式 None = 用序列自己的起点**（2018-01），不是漏写。不设 /tsm/ 那样的 2016
        # 起点：更早的月份取得到，但那段与 2018 之后的合并范围不同，而本轮没核到立錡／
        # 傑發的确切并表出表月份（见 _N_START）。
        'x_from': None,
        # 单月同比要 12 个月 lag ⇒ y/y 自 2019-01 起，今天只有 8 个年度行；
        # 9 是**上限**（与 /tsm/ 同一档），明年自然长到 9 行再开始滚动。
        'heat_years': 9,
        'check_rows': 13,
    },

    'breaks': [
        {'month': '2020-12', 'zh': _b_ili()},
        {'month': '2021-02', 'zh': _b_sigma()},
        {'month': '2024-07', 'zh': _b_icplus()},
    ],
    # 'continuity' 不给：本页有断点，走 breaks 分支，「口径连续」那句事实断言在这一家上
    # 本来就不成立。

    'format_source':
        '版式仿 Goldman Sachs GIR 台股月营收报告（与本站 /tsm/ 同一套图列；'
        '图列、图注与同比口径的规矩见 build/CONTRACT.md）',

    'notes': [_N_SRC, _N_ADD, _N_YOY, _N_BRK, _N_START, _N_DAYS,
              _N_NOFX, _N_NOGUIDE, _N_HEAT],

    'footer': '图表与派生算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
              '仅供个人研究，不构成投资建议',
}
