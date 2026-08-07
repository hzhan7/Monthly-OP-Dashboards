# -*- coding: utf-8 -*-
"""TMX Group 单公司页配置。

━━ 这份文件的全部职责 ━━
声明「series/tmx.csv 的哪些列上页面」。不算数、不画图、不碰公共代码。
整份文件可以直接删掉，别的页一行都不受影响。

━━ 本页最容易犯的错：把两段完全不同的历史当成一段 ━━
series/tmx.csv 里躺着**两条互相独立的官方序列**，起点差 19 年、每月到货时间也差几天：

    Montréal Exchange 衍生品（mx_*）   2002-01 → 2026-07   实测 295 个月，零断档
    加拿大现货（tmx_/tsx_/tsxv_/alpha_）2021-08 → 2026-06   实测  59 个月，零断档

写这份配置的当天（2026-08-06）就正是「MX 已有 2026-07、现货还停在 2026-06」的状态。
两条结论直接来自这个事实：

  1. `headline` **只能放 MX 那条**。把现货放进头条，本页的共同最新月会被拖回 6 月，
     而且 2021-08 之前的 19 年历史会因为「共同历史」被整段砍掉。
  2. 全部 17 条现货列进 `slow_cols`。它们比 MX 晚一档发布，最新月留空是**正常状态**，
     不是解析失败，绝不能参与发布门槛判定。

现货那半边为什么只到 2021-08：更早的数据只存在于 tmx.com/en/resource/<id> 的 PDF 里，
而整个 tmx.com 对本网络返回 CloudFront 403（实测 curl / urllib / nscurl / curl_cffi /
本机真实 Chrome 全部 403），没有合规通道。这是数据可得性问题，不是本页的选择。

━━ BOX 期权：本页做不出来 ━━
TMX 官方**只按季度**披露 BOX（季度 MD&A 里的「最近八个季度」表），没有任何月度口径，
BOX 自己的站点也不发月度统计。它落在 series/tmx_box_q.csv（quarter 列，
实测 8 行：2024-Q3 → 2026-Q2），与本页契约的月频 groups 不兼容。
硬塞进来要么改契约、要么在底座里为 TMX 开一条季频分支 —— 两者都违背
「删掉不留残渣、不许 if ticker == 'tmx'」。要做就另起一页，不缠这一页。

━━ 有意不上页面的其他列 ━━
· mx_adv_index_options_contracts —— 实测最后一个非零月是 2020-10，此后 68 个月全是 0。
  一条归零五年多的死线不提供信息。

━━ BAX 未平仓在窗口内恒为 0：这一列照常声明，不在本文件里做特殊处理 ━━
mx_oi_bax_contracts 最后一个非零月是 2024-05（86,729 张），此后逐月为 0，
2026-06 起整个图窗口恒为 0。恒为 0 的柱图会让引擎的纵轴量程（`0 .. 最大值×1.22`）
上下界重合、坐标算成 0÷0，把图画出卡片外 —— 但**这件事已由底座统一处理**
（`build/single.py` 的 `flat_zero()` / `flat0_skip()`：窗口内全零的图不出，
并在「口径与方法说明」里点名，而**该列仍留在末尾核对表里**）。
所以本文件按常规声明这一列即可，不要在这里摘列：摘了核对表也会跟着少一列，
而「官方报的就是 0」与「本页没有这个指标」是两回事。
· trading_days_rates / trading_days_equity —— 两套分母（每年 9 月、11 月两者不等），
  ADV 官方直接给，本页不做除法。
"""

import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'tmx.csv')


# ── 断点从 CSV 读，不写死 ──────────────────────────────────────────────
# 内联而不抽公共函数：本页要能整份删掉不留残渣。两个函数都只做逐行扫描，
# 不含任何统计口径。读不到就返回 None —— 缺文件不许在 import 期抛异常。
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _first_present(col):
    for r in _rows():
        if col in r and r[col].strip():
            return r['month']
    return None


def _first_zero_after_nonzero(col):
    """该列**由正数转为 0** 的第一个月（产品停发/迁移用这条）。"""
    seen = False
    for r in _rows():
        if col not in r or not r[col].strip():
            continue
        try:
            v = float(r[col])
        except ValueError:
            continue
        if v > 0:
            seen = True
        elif seen:
            return r['month']
    return None


def _breaks():
    out = []
    # CDOR 停用 → 短端利率基准迁到 CORRA。BAX 的 ADV 转 0 的那个月就是迁移完成月。
    # 实测 = 2024-07（BAX 最后一个非零月是 2024-06，CRA 同月接棒）。
    m = _first_zero_after_nonzero('mx_adv_bax_contracts')
    if m:
        out.append({'month': m,
                    'zh': 'CDOR 停用，短端利率合约由 BAX 迁至 CORRA（CRA）'})
    # tmx_all_* 的覆盖范围在 Alpha-X & Alpha DRK 单列之后变大。
    # 实测恒等式：2023-10 及之前 tmx_all = TSX + TSXV + Alpha（差恰为 0）；
    # 2023-11 起 tmx_all = 三家 + Alpha-X&DRK（差恰为 0，2026-06 该项 33,865,231 股）。
    m = _first_present('alphax_drk_volume_shares')
    if m:
        out.append({'month': m,
                    'zh': 'TMX 合计口径纳入 Alpha-X & Alpha DRK，与此前不可直连'})
    # 两条断点的推导顺序与时间顺序不同（BAX 那条在前推出、月份却在后），
    # 底座画红虚线时按索引取月份，乱序会让标签配错断点 —— 这里统一按月份排。
    return sorted(out, key=lambda b: b['month'])


SPEC = {
    'ticker': 'tmx',
    'name': 'TMX Group',
    'title': '多伦多交易所集团（TMX）月度经营指标',
    'csv': 'tmx.csv',
    'ccy': 'CAD',
    'source': ('Source: Montréal Exchange monthly statistics (m-x.ca) and '
               'TMX Group Consolidated Trading Statistics press releases; '
               'format after Goldman Sachs GIR'),

    # 头条只有 MX 一条 —— 见文件抬头第 1 条。
    # 2002-01 起逐月无洞（实测 295/295），次月第 1–4 个工作日发布，是本页最快、最长的序列。
    'headline': [
        {'col': 'mx_adv_contracts', 'zh': 'MX 衍生品 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        {'zh': 'MX 衍生品总量（2002-01 起）', 'cols': [
            {'col': 'mx_adv_contracts', 'zh': '日均成交',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_volume_contracts', 'zh': '当月成交',
             'unit': 'contracts/month', 'fmt': 'f0c'},
            {'col': 'mx_oi_contracts', 'zh': '月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': 'MX：期货 vs 期权', 'cols': [
            {'col': 'mx_adv_futures_contracts', 'zh': '期货 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_options_contracts', 'zh': '期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        # 本页第二重要的一张：基准利率换代时旗舰合约的整体搬迁。
        {'zh': '短端利率 ADV：BAX → CORRA 迁移', 'cols': [
            {'col': 'mx_adv_stir_futures_contracts', 'zh': '短端利率合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_bax_contracts', 'zh': 'BAX（CDOR，已停）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cra_contracts', 'zh': 'CRA（CORRA）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '短端利率月末未平仓', 'cols': [
            {'col': 'mx_oi_stir_futures_contracts', 'zh': '短端利率合计',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_bax_contracts', 'zh': 'BAX（CDOR，已停）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cra_contracts', 'zh': 'CRA（CORRA）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '国债期货 ADV', 'cols': [
            {'col': 'mx_adv_bond_futures_contracts', 'zh': '国债期货合计',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgb_contracts', 'zh': 'CGB（10 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgf_contracts', 'zh': 'CGF（5 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_cgz_contracts', 'zh': 'CGZ（2 年）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '国债期货月末未平仓', 'cols': [
            {'col': 'mx_oi_bond_futures_contracts', 'zh': '国债期货合计',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_cgb_contracts', 'zh': 'CGB（10 年）',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '股指期货', 'cols': [
            {'col': 'mx_adv_index_futures_contracts', 'zh': '股指期货合计 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_sxf_contracts', 'zh': 'SXF（S&P/TSX 60）ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_oi_sxf_contracts', 'zh': 'SXF 月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        {'zh': '个股与 ETF 期权', 'cols': [
            {'col': 'mx_adv_equity_options_contracts', 'zh': '个股期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_etf_options_contracts', 'zh': 'ETF 期权 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_adv_share_futures_contracts', 'zh': '个股期货 ADV',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'mx_oi_equity_options_contracts', 'zh': '个股期权月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'mx_oi_etf_options_contracts', 'zh': 'ETF 期权月末未平仓',
             'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # ── 以下全是慢腿（2021-08 起，比 MX 晚一档发布）────────────────
        {'zh': '加拿大现货成交额（2021-08 起，慢腿）', 'cols': [
            {'col': 'tmx_all_value_cad', 'zh': 'TMX 合计',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'tsx_value_cad', 'zh': 'TSX',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'tsxv_value_cad', 'zh': 'TSX Venture',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
            {'col': 'alpha_value_cad', 'zh': 'TSX Alpha',
             'unit': 'C$bn/month', 'fmt': 'f1', 'scale': 1e-9},
        ]},

        {'zh': '加拿大现货成交股数（2021-08 起，慢腿）', 'cols': [
            {'col': 'tmx_all_volume_shares', 'zh': 'TMX 合计',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'tsx_volume_shares', 'zh': 'TSX',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'tsxv_volume_shares', 'zh': 'TSX Venture',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'alpha_volume_shares', 'zh': 'TSX Alpha',
             'unit': 'bn shares/month', 'fmt': 'f2', 'scale': 1e-9},
        ]},

        {'zh': '加拿大现货成交笔数（2021-08 起，慢腿）', 'cols': [
            {'col': 'tmx_all_transactions', 'zh': 'TMX 合计',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'tsx_transactions', 'zh': 'TSX',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'tsxv_transactions', 'zh': 'TSX Venture',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
            {'col': 'alpha_transactions', 'zh': 'TSX Alpha',
             'unit': 'mn trades/month', 'fmt': 'f1', 'scale': 1e-6},
        ]},

        {'zh': '月末指数点位（2021-08 起，慢腿）', 'cols': [
            {'col': 'tsx_composite_close', 'zh': 'S&P/TSX Composite',
             'unit': 'index level', 'fmt': 'f0c', 'stock': True},
            {'col': 'tsxv_composite_close', 'zh': 'S&P/TSX Venture Composite',
             'unit': 'index level', 'fmt': 'f1', 'stock': True},
        ]},

        {'zh': 'Alpha-X & Alpha DRK（2023-11 起，慢腿）', 'cols': [
            {'col': 'alphax_drk_value_cad', 'zh': '成交额',
             'unit': 'C$bn/month', 'fmt': 'f2', 'scale': 1e-9},
            {'col': 'alphax_drk_volume_shares', 'zh': '成交股数',
             'unit': 'bn shares/month', 'fmt': 'f3', 'scale': 1e-9},
            {'col': 'alphax_drk_transactions', 'zh': '成交笔数',
             'unit': 'mn trades/month', 'fmt': 'f3', 'scale': 1e-6},
        ]},
    ],

    # 17 条现货列全部是慢腿：它们与 MX 不同源、晚一档发布，最新月留空是正常状态。
    # 不这么标，整页的发布门槛会被现货那半边永久拖住一个月。
    'slow_cols': [
        'tmx_all_volume_shares', 'tmx_all_value_cad', 'tmx_all_transactions',
        'tsx_volume_shares', 'tsx_value_cad', 'tsx_transactions', 'tsx_composite_close',
        'tsxv_volume_shares', 'tsxv_value_cad', 'tsxv_transactions', 'tsxv_composite_close',
        'alpha_volume_shares', 'alpha_value_cad', 'alpha_transactions',
        'alphax_drk_volume_shares', 'alphax_drk_value_cad', 'alphax_drk_transactions',
    ],

    'breaks': _breaks(),

    'notes': [
        '本页有**两段起点差 19 年的历史**：MX 衍生品自 2002-01（实测 295 个月零断档），'
        '加拿大现货自 2021-08（实测 59 个月零断档）。两者不是同一段历史，'
        '任何「TMX 从 2002 年以来如何」的说法只对 MX 成立。'
        '现货更早的数据只存在于 tmx.com/en/resource 的 PDF 里，'
        '而该域对本网络返回 CloudFront 403（curl / urllib / nscurl / curl_cffi / '
        '本机真实 Chrome 实测全部 403），没有合规通道，属数据不可得而非本页取舍。',

        '现货比 MX 晚一档发布：写这份配置的 2026-08-06，MX 已有 2026-07、现货仍停在 2026-06。'
        '所以 17 条现货列全部标为 slow_cols，最新月留空是正常状态，不参与发布门槛。',

        '短端利率合约在 2024-07 完成基准换代：CDOR 停用，BAX 的 ADV 自该月起为 0'
        '（最后一个非零月是 2024-06），CORRA 合约 CRA 接棒。'
        '实测 2026-07：CRA ADV 191,902 张/日、BAX 0、短端利率合计 192,122 张/日。'
        '本页把 BAX 与 CRA 画在一起而不是各画各的 —— 只看其中一条会得到「短端利率业务'
        '归零」或「凭空长出一个新产品」两个都不对的结论。断点月份由 series/tmx.csv '
        '里 BAX 转 0 的那一月读出，没有写死。',

        'TMX 合计口径在 2023-11 变大：Alpha-X & Alpha DRK 自该月起单独披露并计入合计。'
        '实测恒等式核过 —— 2023-10 及之前 tmx_all_volume_shares 恰等于 TSX + TSXV + Alpha 三家之和'
        '（差为 0）；2023-11 起恰等于三家 + Alpha-X&DRK（2026-06 该项 33,865,231 股）。'
        '所以合计序列跨 2023-11 不可直连。',

        '**现货三类列在 series/tmx.csv 里是原始单位**：实测 2026-06 '
        'tsx_value_cad = 456,631,843,665（加元）、tsx_volume_shares = 10,796,096,148（股）、'
        'tsx_transactions = 29,942,529（笔）。直接上图轴刻度会是 11–12 位数，'
        '所以本页用 spec 的 scale 字段做**纯显示换算**：金额 ×1e-9 → C$bn、'
        '股数 ×1e-9 → bn shares、笔数 ×1e-6 → mn trades。'
        'scale 只影响本页的显示，series/tmx.csv 与 build/notional.py 读到的仍是原值，'
        '删掉本文件这些除数即随之消失，不碰任何公共代码。'
        'MX 那半边的张数（2026-07 ADV 918,716 张/日）量级本来就可读，不做换算。',

        'BOX 期权做不出月度序列：TMX 官方只在季度 MD&A 里按季披露（series/tmx_box_q.csv，'
        '实测 8 行 2024-Q3 → 2026-Q2），BOX 自身站点也不发月度统计。'
        '本页是月频页，不收季频列。',

        '本页全部金额为加元。跨币种比较由 build/notional.py 统一换算：'
        '流量（成交额、成交股数/笔数）配月均汇率，存量（月末未平仓、月末指数点位）配月末汇率。',

        '未上页面的月频列：mx_adv_index_options_contracts（最后一个非零月 2020-10，'
        '此后 68 个月全为 0 的死列）、trading_days_rates 与 trading_days_equity'
        '（两套分母，每年 9 月与 11 月两者不等；ADV 官方直接给，本页不做除法）。',
    ],
}
