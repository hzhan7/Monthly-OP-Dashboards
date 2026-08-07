# -*- coding: utf-8 -*-
"""ICE 与 Eurex 六个 pool_product 篮子常数的**可复算**取数脚本。

━━ 这个文件为什么存在 ━━
series/contract_specs.csv 里既有的 23 行常数是手工敲进去的，取数代码没留在仓里、
cache/ 又进了 .gitignore —— 仓库自己没法复算，验收员点名这是缺陷。
本脚本负责 ICE_ENERGY / ICE_STIR / ICE_MLTIR / EUREX_RATES / EUREX_INDEX / EUREX_EQUITY
六行，**填出来的每一个数字都能从官方一手 URL 现场重跑出来**，
跑完写 series/_specs_part_ice_eurex.csv。
（不直接改 contract_specs.csv：多个 agent 并行写同一文件会互相覆盖，由主线程合并。）

    python3 build/basefill/ice_eurex.py            # 有 cache/basefill/ 副本就用，没有才下载
    python3 build/basefill/ice_eurex.py --refresh  # 强制重下所有官方文件
    python3 build/basefill/ice_eurex.py --ice-probe # 额外跑 ICE 侧的「为什么算不出」实测
                                                    # （/report/7 单次约 2–4 分钟，默认不跑）

━━ 篮子常数的定义（照 contract_specs.csv 的 notes 列）━━
    篮子常数 = Σ(成员 2019-01 张数 × 乘数 × 基期价格) ÷ Σ(成员 2019-01 张数)
即按基期成交量加权，把一个品类里多个合约折成一个「等效单张名义额」。只算一次写死。
pool_product 行的 multiplier 恒为 1，所以这个常数直接就是 base_price_local
（build/notional.py: base_notional_per_unit_local = multiplier × base_price_local）。

━━ 本次实测结果：6 个里填出 3 个（全是 Eurex），ICE 三个全部留空 ━━
填出来的：
    EUREX_RATES    EUR    面值加权（不乘结算价，与 CME/MX/ASX 利率池同口径）
    EUREX_INDEX    EUR    Eurex 自己公布的 Capital Volume ÷ Traded Contracts
    EUREX_EQUITY   EUR    同上
留空的：
    ICE_ENERGY     ICE 官方月报只到「品类」层，且 TTF 没有固定合约量（见下方「坑 C」）
    ICE_STIR       ICE 官方月报把 STIR 与 MLTIR 合成一列「Interest Rates」，拆不开
    ICE_MLTIR      同上

════════════════════════════════════════════════════════════════════════════
一、Eurex：为什么走「Capital Volume ÷ Traded Contracts」而不是逐个指数取收盘价
════════════════════════════════════════════════════════════════════════════
Eurex 月度统计工作簿（monthlystat_201901.xls，官方一手）对**每一个产品**同时给
「Traded Contracts」与「Capital Volume EUR」两列。Capital Volume 就是名义额
（另有独立的 Paid Premiums 列，所以它不是权利金）。于是

    Capital Volume(2019-01) ÷ Traded Contracts(2019-01)
      = Σ(张数 × 乘数 × 该月价格) ÷ Σ(张数)
      = 篮子常数（基期恰好就是 2019-01）

这条路的三个好处：
  1. **覆盖率 100%**。Equity Index 一节 2019-01 有 194 个当月有量的产品（DAX、
     ESTX50、各国 MSCI、iSTOXX 因子…），Equity 一节有 859 个标的；逐个去找它们的
     2019-01 月均收盘既不现实、也必然大面积「📌 未找到」；
     db1.csv 里只有 4 条分品种列，覆盖 71%。
  2. **零假设**。不需要替任何一个产品猜乘数或猜标的。
  3. 分节合计与 series/db1.csv 的三条池列**逐位对上**（本脚本每次运行都核）：
        Equity Derivatives Sum       33,841,009 = adv_eurex_equity_contracts × 22
        Equity Index Derivatives Sum 68,472,084 = adv_eurex_index_contracts  × 22
        Interest Rate Derivatives Sum 40,980,235 = adv_eurex_rates_contracts × 22
     对不上就 raise —— 池列与篮子常数必须来自同一个分节，错配了图上看不出来。

⚠ **必须留痕的口径差**：contract_specs.csv 表头把实测基准定成
`base_price_basis=avg_close`＝「月内全部交易日**收盘价**的算术平均」。
Eurex 的 Capital Volume 隐含的价格项是**该月成交量加权的成交价**，不是等权收盘均值。
两者不是同一个东西。本脚本实测了能测的那一腿的差距：

    EURO STOXX 50 期货：Capital Volume/张 = 30,771.55 ⇒ 隐含点位 3,077.155（÷ EUR 10/点）
    ECB SDW 的 SX5E 2019-01 月均收盘                  = 3,088.654
    差 −0.372%

期权腿的差更大（ESTX50 期权隐含 2,942.04、DAX 期权隐含 10,755.34，
分别比同月期货隐含点位低 4.39% 与 1.87%）—— Eurex 没有在工作簿里写明期权的
Capital Volume 用标的价还是行权价，本脚本不猜。主线程若坚持全表单一 avg_close 基准，
这三行要么标一个新的 basis 值，要么接受这个量级的偏差；**不要默默当成 avg_close**。

━━ 为什么 EUREX_RATES 不用同一条路 ━━
Eurex 的 Capital Volume 对固定收益是**面值 × 结算价**（实测：Euro-Bund
2,300,547,262,980 ÷ 13,978,601 = 164,576.36 = EUR 100,000 × 164.58%，
2019-01 Bund 期货报价确实在 164 一线）。而本仓利率池的既定口径是
**按面值计名义额、不乘结算价**（build/notional.py 模块 docstring；
contract_specs_todo.csv 里 EUREX_FGBL_BUND 那条也写死了「取到面值即可直接填
base_price_local=1」）。CME_RATES / MX_STIR / MX_BOND / ICE_STIR 都要按面值算，
Eurex 这一池若改用价格加权，**同一张占比图里两种口径混着，份额就是假的**。
所以本脚本对利率池自己按面值重算：产品级张数照样取自同一个官方工作簿（覆盖率同样
100%），面值取自 Eurex 官方合约规格（见下）。代价：
    面值口径 100,082.98  vs  Eurex 价格口径 143,530.34   相差 43.4%
两个都是「对的」，但只能选一个，选的理由是**与本仓其它利率池可加**。

⚠ 名义额 ≠ 风险敞口（build/notional.py 二.1 的同一条告诫）：
同样 1 亿欧元名义额，Schatz（久期约 1.9 年）与 Buxl（久期约 20 年以上）的 DV01
差一个数量级。本池占比只能读作「名义额构成」。要升级到 DV01 需各合约 CTD 久期，
月度成交报表里没有（📌 未找到）。

════════════════════════════════════════════════════════════════════════════
二、ICE：三个都填不出来，卡点各不相同
════════════════════════════════════════════════════════════════════════════
ICE 的规格页本身**不是问题**（纯 urllib 全部 200，本脚本 --ice-probe 会现场证明）：
    Brent          1,000 barrels          https://www.ice.com/products/219/specs
    WTI            1,000 barrels          https://www.ice.com/products/213/specs
    Low Sulphur Gasoil  100 metric tonnes https://www.ice.com/products/34361119/specs
    Long Gilt      GBP 100,000 nominal    https://www.ice.com/products/37650336/specs
    3M Euribor     "EUR 2,500 * Rate Index"  https://www.ice.com/products/38527986/specs
    3M SONIA       "GBP 2,500 * Rate Index"  https://www.ice.com/products/68361266/specs
    Dutch TTF Gas  "1 MW per day in contract period" ← 没有固定合约量

真正的卡点是**权重**，三条各不相同：

坑 A（ICE_STIR / ICE_MLTIR）：ICE 官方唯一的历史月度分产品表把利率并成一列。
    ICE Futures Europe Historical Monthly Volume（https://www.ice.com/report/7，
    服务端渲染，纯 urllib 可读，1995 年至今 32 个年度表）2019 年那张表的列是：
        Futures : Brent | Gas Oil | WTI | Heating Oil & RBOB | Oil Products |
                  EU Nat Gas | Coal, Power & Emissions | **Interest Rates(*)** |
                  Equity Derivatives(*) | London Ags(*)
        Options : Brent | WTI | Gas Oil | Oil Products | **Interest Rates(*)** |
                  Equity Derivatives(*) | London Ags & Other Energy Options(*)
    2019-01：Interest Rates 期货 37,491,346 张、期权 7,632,263 张 —— **一个数**，
    既不拆 Euribor / Short Sterling / SONIA / Euroswiss，也不拆短端 vs 中长端。
    而 series/ice.csv 的 adv_stir / adv_mltir 两列来自 ICE 的 Monthly Statistics
    Tracking xlsx，那份只有池级合计。两边都没有分合约张数 ⇒ 权重无从谈起。
    这一步不能拍：Euribor 面值 EUR 1,000,000、Short Sterling GBP 500,000、
    SONIA GBP 1,000,000，权重错一点常数就差一倍以上。

坑 B（ICE_STIR 还多一层）：ICE 的短端合约页**不印面值**，只印
    "Unit of Trading: EUR 2,500 * Rate Index"。EUR 1,000,000 是从
    「每点 2,500 欧元 × 3 个月 / 1 年 = 面值 × 1bp 的 25 欧元」反推出来的，
    不是官方页面上的字。要么找 ICE 的 CONTRACT RULES PDF 把面值原文抠出来
    （https://www.ice.com/publicdocs/circulars/ 下的 "ICE FUTURES SHORT TERM
    INTEREST RATE INDEX FUTURES CONTRACTS" 合约规则），要么在 evidence 里
    写明这是推导值。本脚本不写推导值。

坑 C（ICE_ENERGY）：分子分母对不上 + TTF 没有固定合约量。
    · pools.py 把 ICE_ENERGY 挂在 ice.csv 的 adv_energy_kcontracts 上，
      2019-01 = 2,718 千张/日 × 21 个交易日 = 57,078,000 张（全球能源，
      含 ICE Endex / ICE Futures U.S. / ICE Futures Abu Dhabi）。
    · 而 /report/7 是**只有 ICE Futures Europe** 的表，2019-01 能源各列相加
      = 38,241,726 张，只占 67.0%。TTF 在 ICE Endex 上，根本不在这张表里
      （表里的 "EU Nat Gas" 1,915,161 张是 IFEU 的英国天然气那一支）。
      /report/147（Energy Products Historical Monthly Volume，跨所）只有
      Natural Gas / Power / Oil & Other 三列，更粗，同样拆不出 TTF。
    · 就算权重有了，TTF 也**没有固定乘数**：官方页原文
      "Contract Size 1 MW per day in contract period (i.e. month, quarter,
      season or year) x 23, 24 or 25 hours"，一张月度合约 672–744 MWh 不等。
    · 价格那一跳同样缺：Brent / WTI 的 2019-01 日度价可以走 EIA（官方）算
      月均，但 **ICE Low Sulphur Gasoil（西北欧 ARA，美元/公吨）EIA 没有**，
      ICE 自己的历史结算价在 Report Center 登录墙后面。

下一步的检索路径（写给下一个人，别再从头试一遍）：
  1. ICE 分合约月度张数 —— 试 ICE 的合约规则/费率 PDF 目录
     https://www.ice.com/publicdocs/futures/ 与 /publicdocs/circulars/；
     或 ICE 10-K（SEC 申报，允许）看有没有比「Interest rates」更细的口径
     （已知 10-K 的 ADV 表口径与月度 xlsx 同粒度，希望不大）。
  2. Gasoil 基期价 —— ICE Report Center 的 end-of-day 分类
     （https://www.ice.com/marketdata/reports 里 /report-center/category/end-of-day），
     需确认是否有免登录的历史结算价档案。
  3. TTF —— 若最终仍拿不到固定合约量，按 contract_specs_todo.csv 里已写的两条出路
     选一条；本次实测的结论是出路 (b)「把 TTF 从篮子里单列」**做不到**，
     因为官方月报根本不单列 TTF 张数。

━━ 依赖 ━━ 标准库 + xlrd（Eurex 的 .xls 是 BIFF/OLE2，openpyxl 打不开，
与 fetch/db1.py 同一个依赖）。不引 pandas。
"""

import argparse
import csv
import os
import re
import sys
import urllib.request

import xlrd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERIES = os.path.join(ROOT, 'series')
CACHE = os.path.join(ROOT, 'cache', 'basefill')

BASE_MONTH = '2019-01'          # 与 build/notional.py / build/check_specs.py 同源
OUT = os.path.join(SERIES, '_specs_part_ice_eurex.csv')

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# ── Eurex 月度统计的官方翻页接口（与 fetch/db1.py 用的是同一个，别另发明一个）──
EUREX_SEARCH = ('https://www.eurex.com/ex-en/data/statistics/monthly-statistics/'
                '3848!search?pageNum=%d&hitsPerPage=50&sort=freshness%%20%%20desc')
EUREX_HOST = 'https://www.eurex.com'

# ── Eurex 官方合约规格：2018-04-02 生效的合并版（基期 2019-01 之前最近的一版）──
#    2021 年那几份 circular 附件只是**修订件**（6 页、只印改动段），不能当规格源。
EUREX_SPEC_PDF = ('https://www.eurexchange.com/resource/blob/259196/'
                  'd0ad030869f82de941673eac20a3eacf/data/2018_04_02_cs_1_history.pdf')

# 本脚本用到的每一个面值 / 每点欧元数，都在 EUREX_SPEC_PDF 里有一句原文。
# _verify_spec_pdf() 每次运行都把 PDF 下下来、抽文本、逐句核对 —— 常数是不是官方的，
# 不靠注释里的一句「我查过」，靠这一步现场证明。
# ⚠ PDF 抽出来的文本带硬换行（"The par \n value of..."），比对前必须先压空白。
_SPEC_QUOTES = [
    ('欧元区国债期货面值 EUR 100,000',
     'The par value of any such contract is EUR 100,000.',
     '§1.2.1(1)：Schatz / Bobl / Bund / Buxl / BTP / Mid-BTP / Short-BTP / '
     'OAT / Mid-OAT / Bono 十个 Euro Fixed Income Futures 之后紧跟这一句'),
    ('CONF 期货面值 CHF 100,000',
     'The par value of any such contract is CHF 100,000.',
     '§1.2.1(2) CONF Futures'),
    ('3M EURIBOR 期货 EUR 1,000,000',
     'The value of a contract shall be EUR 1,000,000.',
     '§1.1.1(1) Three-Month EURIBOR Future'),
    ('FDAX 每点 EUR 25',
     'EUR 25 per index point for Futures Contracts on the DAX',
     '§1.3.1(5) 指数期货的合约价值'),
    ('FESX 每点 EUR 10',
     'EUR 10 per index point for Futures Contracts on the TecDAX',
     '§1.3.1(5)，同一句里点名 "EURO STOXX 50® Index (Product ID: FESX)"'),
    ('ODAX 每点 EUR 5',
     'EUR 5 per index point for Options Contracts on DAX',
     '§Options 一节 (5) 指数期权的合约价值 —— ⚠ DAX 期权 EUR 5/点 与 '
     'DAX 期货 EUR 25/点 差 5 倍，同一个标的、同一家所，张数照样不可加'),
]

EURO_FI_PAR = 100000.0          # EUR，欧元区国债期货（及其期权）面值
CONF_PAR = 100000.0             # CHF，瑞士 CONF 期货面值
MM_NOMINAL_EUR = 1000000.0      # EUR，3M EURIBOR 期货
# 3M SARON：官方规格页写的是「CHF 2,500 per index point」，与 EURIBOR 的
# 「EUR 2,500 per index point ⇒ EUR 1,000,000」同构 ⇒ CHF 1,000,000。
# 这是**推导值**，所以下面 _RATES_PAR 里单独标出来；2019-01 只有 74 张，
# 敏感度实测见 main() 的打印（改成 CHF 100,000 只动常数 1.42 欧元 = 0.0014%）。
MM_NOMINAL_CHF = 1000000.0
SARON_SPEC_URL = ('https://www.eurex.com/ex-en/markets/int/mon/saron-futures/'
                  'saron/3M-SARON-Futures-1405958')

# EURO STOXX 50 的 2019-01 月均收盘（= contract_specs.csv 表头定义的 avg_close 基准）。
# 只用来量化「Capital Volume 隐含的价格项 vs avg_close」的差距，不参与任何常数计算。
# 来源是 ECB 统计数据仓库（fetch/fx.py 已经在用同一个 SDMX 域），系列
# FM.M.U2.EUR.DS.EI.DJES50I.HSTA「EURO STOXX 50 Equity Index - Historical close,
# average of observations through period」。⚠ ECB 这条系列的 PROVIDER_FM=DS
# （DataStream），是 ECB 转发的商业数据，不是 STOXX 一手；STOXX 自己的
# h_sx5e.txt 实测 403（同目录的 h_v2tx.txt 是 200，所以是按指数授权挡的，不是被反爬）。
ECB_SX5E_URL = ('https://data-api.ecb.europa.eu/service/data/FM/'
                'M.U2.EUR.DS.EI.DJES50I.HSTA?startPeriod=2019-01&endPeriod=2019-01'
                '&format=csvdata')
ECB_SX5E_AVG_CLOSE = 3088.6543636363635

# Eurex 工作簿里「Interest Rate Derivatives」一节 2019-01 出现过成交量的每一行，
# 逐行登记面值与计价币。**不许有兜底分支**：出现没登记过的产品名就 raise，
# 否则将来 Eurex 加一个新品种，它会被静默按 EUR 100,000 算进去，图上看不出来。
_RATES_PAR = {
    # Fixed Income Futures（面值 EUR 100,000，规格 §1.2.1(1)）
    'Euro-Schatz Futures':          (EURO_FI_PAR, 'EUR'),
    'Euro-Bobl Futures':            (EURO_FI_PAR, 'EUR'),
    'Euro-Bund Futures':            (EURO_FI_PAR, 'EUR'),
    'Euro-Buxl® Futures':           (EURO_FI_PAR, 'EUR'),
    'Euro-BTP Futures':             (EURO_FI_PAR, 'EUR'),
    'Mid term Euro-BTP-Futures':    (EURO_FI_PAR, 'EUR'),
    'Short Term Euro-BTP-Futures':  (EURO_FI_PAR, 'EUR'),
    'Euro-OAT-Futures':             (EURO_FI_PAR, 'EUR'),
    'Mid-Term Euro-OAT-Futures':    (EURO_FI_PAR, 'EUR'),
    'Euro-Bono Futures':            (EURO_FI_PAR, 'EUR'),
    'CONF Futures':                 (CONF_PAR,    'CHF'),
    # Options on Fixed Income Futures：一张期权对应一张标的期货 ⇒ 面值相同
    'Bund Weekly Options - Week1':  (EURO_FI_PAR, 'EUR'),
    'Bund Weekly Options - Week2':  (EURO_FI_PAR, 'EUR'),
    'Bund Weekly Options - Week3':  (EURO_FI_PAR, 'EUR'),
    'Bund Weekly Options - Week4':  (EURO_FI_PAR, 'EUR'),
    'Bund Weekly Options - Week5':  (EURO_FI_PAR, 'EUR'),
    'Options on Euro-Bund Futures':   (EURO_FI_PAR, 'EUR'),
    'Options on Euro-Bobl Futures':   (EURO_FI_PAR, 'EUR'),
    'Options on Euro-Schatz Futures': (EURO_FI_PAR, 'EUR'),
    'Options on Euro BTP Futures':    (EURO_FI_PAR, 'EUR'),
    'Options on Euro-OAT Futures':    (EURO_FI_PAR, 'EUR'),
    # Money Market
    'Three-Month EURIBOR Futures':  (MM_NOMINAL_EUR, 'EUR'),
    'Three-Month SARON Futures':    (MM_NOMINAL_CHF, 'CHF'),
}
# 明确排除、不参与加权的行（同时从分子与分母里剔掉，并在 note 里写明影响量级）
_RATES_EXCLUDE = {
    # 公司债指数期货，不是「面值型」合约（每点 EUR 1,000 × 指数），
    # Eurex 规格 §1.2.1 的面值那一句管不到它。2019-01 只有 10 张。
    'EUR STX 50 CorpBond (PI)': '公司债指数期货，非面值型合约；2019-01 仅 10 张',
}

# 工作簿里三个分节的行位置**不写死**，按 col0 的标题文字定位（见 _sections）。
_SECTIONS = {
    'EUREX_EQUITY': 'Equity Derivatives',
    'EUREX_INDEX':  'Equity Index Derivatives',
    'EUREX_RATES':  'Interest Rate Derivatives',
}
# 各分节合计必须等于 series/db1.csv 这几列 × 当月交易日数
_POOL_COL = {
    'EUREX_EQUITY': 'adv_eurex_equity_contracts',
    'EUREX_INDEX':  'adv_eurex_index_contracts',
    'EUREX_RATES':  'adv_eurex_rates_contracts',
}

# ICE 侧 --ice-probe 要现场打的官方页（证明「不是抓不到，是源头没有那个数」）
_ICE_SPEC_PAGES = [
    ('Brent Crude Futures',        'https://www.ice.com/products/219/specs'),
    ('WTI Crude Futures',          'https://www.ice.com/products/213/specs'),
    ('Low Sulphur Gasoil Futures', 'https://www.ice.com/products/34361119/specs'),
    ('Dutch TTF Gas Futures',      'https://www.ice.com/products/27996665/specs'),
    ('Long Gilt Future',           'https://www.ice.com/products/37650336/specs'),
    ('Three Month Euribor Futures', 'https://www.ice.com/products/38527986/specs'),
    ('Three Month SONIA Futures',  'https://www.ice.com/products/68361266/specs'),
]
ICE_MONTHLY_REPORT = 'https://www.ice.com/report/7'


class BasefillError(RuntimeError):
    """源站结构变化 / 下载失败 / 对账不上。一律炸掉，绝不静默写一个看不出错的常数。"""


# ────────────────────────────────────────────────────────────────────────────
# 下载
# ────────────────────────────────────────────────────────────────────────────
def _get(url, timeout=120):
    req = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': '*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _cached(name, url, refresh, timeout=120):
    """下到 cache/basefill/<name>；已有且未 --refresh 就直接用。"""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and not refresh:
        return path
    data = _get(url, timeout=timeout)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def _eurex_monthlystat(month, refresh):
    """按官方翻页接口找 monthlystat_YYYYMM.xls 的 blob 直链 —— blob id 每月都变，不可拼。"""
    name = 'eurex_monthlystat_%s.xls' % month.replace('-', '')
    path = os.path.join(CACHE, name)
    if os.path.exists(path) and not refresh:
        return path, '(cache/basefill/%s)' % name
    ym = month.replace('-', '')
    for page in range(0, 14):
        html = _get(EUREX_SEARCH % page).decode('utf8', 'replace')
        hits = re.findall(
            r'(/resource/blob/\d+/[0-9a-f]+/data/monthlystat_(\d{6})\.xls)', html)
        for href, got in hits:
            if got == ym:
                url = EUREX_HOST + href
                os.makedirs(CACHE, exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(_get(url, timeout=180))
                return path, url
    raise BasefillError(
        'Eurex 月度统计列表页 13 页翻完没找到 monthlystat_%s.xls；'
        '源站可能改版，检查 %s' % (ym, EUREX_SEARCH % 0))


# ────────────────────────────────────────────────────────────────────────────
# 解析
# ────────────────────────────────────────────────────────────────────────────
def _label(sheet, row):
    """产品名在 A..E 五列里缩进排版：返回 (层级, 文字)。"""
    for c in range(5):
        v = str(sheet.cell_value(row, c)).strip()
        if v:
            return c, v
    return 9, ''


def _num(v):
    return float(v) if isinstance(v, float) else None


def _sections(sheet):
    """定位三个 col0 分节的 [起, 止) 与它们的 Sum 行。"""
    heads = []
    for r in range(11, sheet.nrows):
        lvl, txt = _label(sheet, r)
        if lvl == 0 and txt:
            heads.append((r, txt))
    out = {}
    for pid, title in _SECTIONS.items():
        starts = [r for r, t in heads if t == title]
        if not starts:
            raise BasefillError('工作簿里找不到分节标题「%s」' % title)
        start = starts[0]
        after = [r for r, _ in heads if r > start]
        end = min(after) if after else sheet.nrows
        # 分节内最后一个 col1 == 'Sum' 的行就是该节合计
        sums = [r for r in range(start, end) if _label(sheet, r) == (1, 'Sum')]
        if not sums:
            raise BasefillError('分节「%s」里没有 col1=Sum 的合计行' % title)
        out[pid] = (start, end, sums[-1])
    return out


def _verify_spec_pdf(refresh):
    """把 _SPEC_QUOTES 的每一句拿去 Eurex 官方规格 PDF 里现场核。核不到就 raise。"""
    path = _cached('eurex_contract_specs_2018_04_02.pdf', EUREX_SPEC_PDF,
                   refresh, timeout=300)
    try:
        import fitz                                   # PyMuPDF
    except ImportError:
        print('  ⚠ 本机没有 PyMuPDF，跳过规格 PDF 的原文复核（常数照算，但这一跑'
              '没有把「面值是官方的」证出来）。装 pymupdf 后重跑即可。')
        return path, False
    doc = fitz.open(path)
    text = ' '.join(p.get_text() for p in doc)
    flat = ' '.join(text.split())
    for tag, quote, where in _SPEC_QUOTES:
        needle = ' '.join(quote.split())
        if needle not in flat:
            raise BasefillError(
                '规格 PDF 里核不到「%s」的原文：%r（%s）。'
                'Eurex 可能改了措辞或换了版本 —— 在把常数写进 CSV 之前先人工确认，'
                '不要放宽这条检查。' % (tag, quote, where))
        print('    ✓ %-28s ← "%s"' % (tag, quote[:62]))
    print('  规格 PDF %d 页，%d 句原文全部核到' % (doc.page_count, len(_SPEC_QUOTES)))
    return path, True


def _db1_pool_contracts(month):
    """series/db1.csv 的池列 × 当月交易日数 —— 与工作簿分节合计对账用。"""
    rows = {r['month']: r for r in
            csv.DictReader(open(os.path.join(SERIES, 'db1.csv'), encoding='utf8'))}
    if month not in rows:
        raise BasefillError('series/db1.csv 里没有 %s' % month)
    row = rows[month]
    days = float(row['trading_days_eurex'])
    return {pid: float(row[col]) * days for pid, col in _POOL_COL.items()}, days


def _base_fx(ccy):
    """series/fx.csv 的基期月均汇率（本币 → 美元）。"""
    rows = {r['month']: r for r in
            csv.DictReader(open(os.path.join(SERIES, 'fx.csv'), encoding='utf8'))}
    key = 'fx_avg_%susd' % ccy.lower()
    base = rows[BASE_MONTH]
    if not base.get(key):
        raise BasefillError('series/fx.csv 的 %s 没有 %s 列' % (BASE_MONTH, key))
    return float(base[key])


# ────────────────────────────────────────────────────────────────────────────
# 三个常数
# ────────────────────────────────────────────────────────────────────────────
def eurex_capital_volume_constant(sheet, sum_row):
    """Capital Volume EUR ÷ Traded Contracts —— 用于 EUREX_INDEX / EUREX_EQUITY。"""
    tc = _num(sheet.cell_value(sum_row, 5))
    cv = _num(sheet.cell_value(sum_row, 15))
    if not tc or cv is None:
        raise BasefillError('分节合计行 %d 的张数或 Capital Volume 是空的' % sum_row)
    return cv / tc, tc, cv


def eurex_rates_face_constant(sheet, start, end, chf_per_eur):
    """按**面值**加权重算利率池（不乘结算价），跨币种先折成 EUR。"""
    legs, total_qty, total_notional = [], 0.0, 0.0
    skipped = []
    for r in range(start, end):
        lvl, txt = _label(sheet, r)
        # 只吃最细一层的产品行。⚠ 工作簿把**小节合计也排在 col3**（例如第 2464 行
        # 「Fixed Income Futures / Sum」），按缩进层级筛不掉，必须按文字剔 —— 漏剔
        # 就会把整节的量重复计一遍，而常数只是「看起来偏了一点」，图上完全看不出来。
        if lvl != 3 or not txt or txt == 'Sum':
            continue
        qty = _num(sheet.cell_value(r, 5))
        if not qty:
            continue                       # 该月没量
        if txt in _RATES_EXCLUDE:
            skipped.append((txt, qty, _RATES_EXCLUDE[txt]))
            continue
        if txt not in _RATES_PAR:
            raise BasefillError(
                '利率节里出现未登记面值的产品「%s」（第 %d 行，%d 张）。'
                '去 Eurex 合约规格把它的面值查出来加进 _RATES_PAR，不要给兜底值。'
                % (txt, r + 1, qty))
        par, ccy = _RATES_PAR[txt]
        par_eur = par if ccy == 'EUR' else par * chf_per_eur
        legs.append((txt, qty, par, ccy, par_eur))
        total_qty += qty
        total_notional += qty * par_eur
    if not total_qty:
        raise BasefillError('利率节一条有量的产品都没解析出来')
    return total_notional / total_qty, total_qty, legs, skipped


# ────────────────────────────────────────────────────────────────────────────
# ICE 侧实测（只为把「卡在哪一步」变成可复现的证据，不产出任何常数）
# ────────────────────────────────────────────────────────────────────────────
def ice_probe(refresh):
    print('── ICE 规格页实测（纯 urllib，无浏览器）──')
    for name, url in _ICE_SPEC_PAGES:
        try:
            body = _cached('ice_%s.html' % re.sub(r'\W+', '_', name).lower(),
                           url, refresh, timeout=180)
            t = open(body, encoding='utf8', errors='replace').read()
        except Exception as exc:                       # noqa: BLE001
            print('  %-28s ✗ %s' % (name, exc))
            continue
        hit = re.search(r'\{"name":"(?:Contract Size|Unit of Trading)","value":"'
                        r'([^"]{0,160})', t)
        import html as _h
        val = (_h.unescape(hit.group(1).replace('\\n', ' ')).strip()
               if hit else '（页面里没有该字段）')
        print('  %-28s %s' % (name, val[:96]))
    print()
    print('── ICE Futures Europe 历史月度成交表（%s）──' % ICE_MONTHLY_REPORT)
    print('  ⏳ 这一页服务端渲染 1995-2026 全部 32 张年表，单次约 2–4 分钟…')
    path = _cached('ice_report7.html', ICE_MONTHLY_REPORT, refresh, timeout=600)
    t = open(path, encoding='utf8', errors='replace').read()
    i = t.find('data-partial="/historical-volumes-ifeu"')
    if i < 0:
        raise BasefillError('/report/7 的返回里没有 historical-volumes-ifeu 分块，源站改版')
    seg = t[i:]
    j = seg.find('<h2 class="section-header">2019</h2>')
    k = seg.find('<h2 class="section-header">2018</h2>')
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', seg[j:k], re.S)
    import html as _html
    for row in rows[:3]:
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S)
        cells = [' '.join(_html.unescape(re.sub(r'<[^>]+>', ' ', c)).split())
                 for c in cells]
        print('   ', ' | '.join(cells))
    print('  ⇒ 利率只有一列 "Interest Rates"，STIR / MLTIR 拆不开；'
          'TTF 在 ICE Endex 上，根本不在这张表里。')
    print()


# ────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true', help='强制重下官方文件')
    ap.add_argument('--ice-probe', action='store_true',
                    help='额外跑 ICE 侧实测（慢，约 2–4 分钟）')
    args = ap.parse_args()

    print('基期 %s ｜ 输出 %s' % (BASE_MONTH, os.path.relpath(OUT, ROOT)))
    print()

    # ── Eurex ──────────────────────────────────────────────────────────────
    xls, src = _eurex_monthlystat(BASE_MONTH, args.refresh)
    book = xlrd.open_workbook(xls)
    sheet = book.sheet_by_name('Eurex Monthly Statistics')
    print('── Eurex 官方月度统计 ──')
    print('  源  %s' % src)
    print('  表头 %s ｜ 交易日 %s' % (str(sheet.cell_value(6, 0)).strip(),
                                    str(sheet.cell_value(7, 5)).strip()))

    print()
    print('── Eurex 官方合约规格（面值 / 每点欧元数）原文复核 ──')
    print('  源  %s' % EUREX_SPEC_PDF)
    _verify_spec_pdf(args.refresh)
    print()

    secs = _sections(sheet)
    pool, days = _db1_pool_contracts(BASE_MONTH)
    print('  分节合计 vs series/db1.csv 池列 × %g 个交易日：' % days)
    for pid, (start, end, srow) in sorted(secs.items()):
        tc = _num(sheet.cell_value(srow, 5))
        want = pool[pid]
        ok = abs(tc - want) < 0.5
        print('    %-13s 工作簿 %14s ｜ db1.csv %14s ｜ %s'
              % (pid, f'{tc:,.0f}', f'{want:,.0f}', '✓' if ok else '✗ 不一致'))
        if not ok:
            raise BasefillError(
                '%s 的分节合计与 %s 对不上（%.0f vs %.0f）：篮子常数与池列必须来自'
                '同一个分节，错配了图上看不出来' % (pid, _POOL_COL[pid], tc, want))
    print()

    eur_usd = _base_fx('EUR')
    chf_usd = _base_fx('CHF')
    chf_per_eur = chf_usd / eur_usd
    print('  基期汇率（series/fx.csv，%s 月均）：EUR/USD %.12f ｜ CHF/USD %.12f '
          '⇒ 1 CHF = %.12f EUR' % (BASE_MONTH, eur_usd, chf_usd, chf_per_eur))
    print()

    rows = []

    # EUREX_INDEX / EUREX_EQUITY：Capital Volume ÷ 张数
    # per_contract 收集几个乘数已知的产品，用来把「乘数对不对」当场验掉：
    # 单张 Capital Volume ÷ 官方乘数 = 隐含点位，四条腿必须落在同一个量级上。
    per_contract = {}
    cvtc = {}          # pid → (Capital Volume, Traded Contracts)，note 里要逐池引用，
                       # 不能靠循环结束后残留的那一份（会把 EQUITY 的数印进 INDEX 的 note）
    nlegs = {}         # pid → 当月有成交量的产品个数（note 里的「覆盖率」不许口头说）
    for pid in ('EUREX_INDEX', 'EUREX_EQUITY'):
        start, end, srow = secs[pid]
        const, tc, cv = eurex_capital_volume_constant(sheet, srow)
        cvtc[pid] = (cv, tc)
        print('── %s ──' % pid)
        print('  Capital Volume EUR %s ÷ Traded Contracts %s = **%.6f EUR/张**'
              % (f'{cv:,.2f}', f'{tc:,.0f}', const))
        # 打印本节最大的几个产品，方便人工对着官方工作簿逐位核
        legs = []
        for r in range(start, end):
            lvl, txt = _label(sheet, r)
            if lvl == 3 and txt and txt != 'Sum':   # 同上：col3 里混着小节合计
                q = _num(sheet.cell_value(r, 5))
                c = _num(sheet.cell_value(r, 15))
                if q and c:
                    legs.append((q, txt, c / q))
                    per_contract[txt] = c / q
        nlegs[pid] = len(legs)
        legs.sort(reverse=True)
        print('  当月有成交量的产品 %d 个' % nlegs[pid])
        for q, txt, per in legs[:5]:
            print('    %-46s %12s 张 ｜ %14.2f EUR/张' % (txt[:46], f'{q:,.0f}', per))
        rows.append({
            'product_id': pid,
            'base_price_local': '%.6f' % const,
            'base_ccy': 'EUR',
            'basket_constant': '%.6f' % const,
            'source_url': src if src.startswith('http') else
                          'https://www.eurex.com/ex-en/data/statistics/monthly-statistics',
            'computed_note': '',        # 下面统一填
        })
        print()

    # ── 乘数交叉验证：单张 Capital Volume ÷ 官方乘数 = 隐含点位 ──────────────
    # 这一步是「Capital Volume 这条路到底对不对」的唯一实证。四条腿的乘数取自
    # Eurex 官方合约规格（EUREX_SPEC_PDF）：FESX 期货/期权 EUR 10/点、
    # FDAX 期货 EUR 25/点、ODAX 期权 EUR 5/点。若乘数猜错，隐含点位会差整数倍，
    # 一眼看得出来；落在同一量级才说明这条路成立。
    implied = {}
    for label, mult, tag in (
            ('EURO STOXX 50® Index Futures', 10.0, 'FESX 期货'),
            ('EURO STOXX 50® Index Options', 10.0, 'ESTX50 期权'),
            ('DAX® Futures', 25.0, 'FDAX 期货'),
            ('DAX® Options', 5.0, 'ODAX 期权')):
        if label not in per_contract:
            raise BasefillError('工作簿里找不到用于乘数交叉验证的产品「%s」' % label)
        implied[tag] = per_contract[label] / mult
    print('── 乘数交叉验证（乘数出处：%s）──' % EUREX_SPEC_PDF)
    for tag, lvl_ in implied.items():
        print('    %-14s 隐含点位 %10.3f' % (tag, lvl_))
    print('    ECB SDW 的 SX5E %s 月均收盘 = %.6f（%s）'
          % (BASE_MONTH, ECB_SX5E_AVG_CLOSE, ECB_SX5E_URL))
    print('    ⇒ FESX 期货隐含点位比 avg_close 低 %.3f%%；期权腿再低一截'
          '（Eurex 未写明期权用标的价还是行权价）'
          % ((1 - implied['FESX 期货'] / ECB_SX5E_AVG_CLOSE) * 100))
    print()

    # EUREX_RATES：面值加权
    start, end, srow = secs['EUREX_RATES']
    const_face, qty_face, legs, skipped = eurex_rates_face_constant(
        sheet, start, end, chf_per_eur)
    const_cv, tc_r, cv_r = eurex_capital_volume_constant(sheet, srow)
    print('── EUREX_RATES（面值口径，不乘结算价）──')
    for txt, q, par, ccy, par_eur in sorted(legs, key=lambda x: -x[1])[:8]:
        print('    %-34s %12s 张 ｜ 面值 %s %s' %
              (txt[:34], f'{q:,.0f}', ccy, f'{par:,.0f}'))
    for txt, q, why in skipped:
        print('    （剔除）%-28s %12s 张 ｜ %s' % (txt[:28], f'{q:,.0f}', why))
    print('  Σ张数 %s（官方分节 Sum %s，差 %s 张 = 被剔除项）'
          % (f'{qty_face:,.0f}', f'{tc_r:,.0f}', f'{tc_r - qty_face:,.0f}'))
    print('  面值加权常数 = **%.6f EUR/张**' % const_face)
    print('  对照：Eurex 自己的 Capital Volume 口径 = %.6f EUR/张（含结算价，'
          '高 %.1f%%）—— 本仓利率池按面值，不用它' % (const_cv,
                                                (const_cv / const_face - 1) * 100))
    # SARON 面值是推导值，给出敏感度
    saron_qty = next((q for t, q, _p, _c, _e in legs
                      if t == 'Three-Month SARON Futures'), 0.0)
    if saron_qty:
        alt = (const_face * qty_face
               - saron_qty * MM_NOMINAL_CHF * chf_per_eur
               + saron_qty * 100000.0 * chf_per_eur) / qty_face
        print('  敏感度：3M SARON 的 CHF 1,000,000 是从「CHF 2,500/点」推导的；'
              '若改按 CHF 100,000 算，常数变 %.6f（差 %.4f EUR = %.4f%%）'
              % (alt, const_face - alt, (const_face / alt - 1) * 100))
    print()
    rows.append({
        'product_id': 'EUREX_RATES',
        'base_price_local': '%.6f' % const_face,
        'base_ccy': 'EUR',
        'basket_constant': '%.6f' % const_face,
        'source_url': EUREX_SPEC_PDF,
        'computed_note': '',
    })

    # ── 三行 computed_note（写全口径与告诫，主线程合并时直接用）──
    note = {}
    note['EUREX_INDEX'] = (
        'kind=contract, level=pool_product, multiplier=1 ⇒ base_price_local = 篮子常数。'
        '算法：Eurex 官方月度统计 monthlystat_201901.xls「Equity Index Derivatives」'
        '分节 Sum 行的 Capital Volume EUR ÷ Traded Contracts '
        '= %s ÷ %s。该分节张数与 series/db1.csv 的 adv_eurex_index_contracts × %g '
        '个交易日逐位相等（本脚本每次运行都核，对不上就 raise）。'
        '覆盖率 100%%：该分节当月有成交量的 %d 个指数产品全含，'
        '不是 db1.csv 那 4 条分品种列（ESTX50 期货/期权 + DAX 期货/期权）的 71%%。'
        '乘数交叉验证（乘数出处 Eurex 合约规格 %s）：单张 Capital Volume ÷ 官方乘数 '
        '= 隐含点位 —— FESX 期货 %.3f（÷EUR 10/点）、FDAX 期货 %.3f（÷EUR 25/点）、'
        'ODAX 期权 %.3f（÷EUR 5/点）、ESTX50 期权 %.3f（÷EUR 10/点）。'
        '同标的的期货腿与期权腿互差在 5%% 以内、FESX 腿与 ECB 的 SX5E 月均收盘互差 '
        '0.4%%（若乘数错，差的会是整数倍而不是零点几个百分点）⇒ 乘数没猜错。'
        '⚠ 口径差必须留痕：本常数隐含的价格项是**成交量加权的成交价**，'
        '不是表头定义的 avg_close（月内交易日收盘价等权算术平均）。实测差距：'
        'FESX 隐含点位 %.3f vs ECB SDW 的 SX5E %s 月均收盘 %.6f（%+.3f%%，来源 %s）；'
        '期权腿差更大（ESTX50 期权隐含 %.2f、DAX 期权隐含 %.2f，比同月期货隐含点位低 '
        '%.2f%% / %.2f%%），Eurex 未在工作簿里写明期权的 Capital Volume 用标的价'
        '还是行权价。主线程决定 base_price_basis 时不要默默填 avg_close。'
        '📌 走这条路的原因：canonical 算法要这 %d 个指数各自的 2019-01 月均收盘，'
        '其中 DAX 一项本会话在官方一手源里就没拿到（stoxx.com 的 h_dax.txt / '
        'h_sx5e.txt 均 403 而同目录 h_v2tx.txt 是 200，属按指数授权挡；ECB SDW 的 FM '
        '库只有欧元区 U2 指数、没有 DE；Bundesbank statistic-rmi 试了 5 个 tsId 全部'
        '「nicht gültig」；api.boerse-frankfurt.de 的 price_history 返回空 {}）。'
        '拿到的只有 VSTOXX（stoxx.com/document/Indices/Current/HistoricalData/'
        'h_v2tx.txt，HTTP 200）与 SX5E（ECB SDW）。'
        % (f'{cvtc["EUREX_INDEX"][0]:,.2f}', f'{cvtc["EUREX_INDEX"][1]:,.0f}',
           days, nlegs['EUREX_INDEX'], EUREX_SPEC_PDF,
           implied['FESX 期货'], implied['FDAX 期货'],
           implied['ODAX 期权'], implied['ESTX50 期权'],
           implied['FESX 期货'], BASE_MONTH, ECB_SX5E_AVG_CLOSE,
           (implied['FESX 期货'] / ECB_SX5E_AVG_CLOSE - 1) * 100, ECB_SX5E_URL,
           implied['ESTX50 期权'], implied['ODAX 期权'],
           (1 - implied['ESTX50 期权'] / implied['FESX 期货']) * 100,
           (1 - implied['ODAX 期权'] / implied['FDAX 期货']) * 100,
           nlegs['EUREX_INDEX']))
    note['EUREX_EQUITY'] = (
        'kind=contract, level=pool_product, multiplier=1 ⇒ base_price_local = 篮子常数。'
        '算法与来源同 EUREX_INDEX，取「Equity Derivatives」分节（Single Stock Futures '
        '+ Equity Options，含单股期货 —— 与美国的纯期权列不同源，图注必须点名）：'
        'Capital Volume EUR %s ÷ Traded Contracts %s。'
        '分节张数与 adv_eurex_equity_contracts × %g 个交易日逐位相等。'
        '覆盖率 100%%：2019-01 该节 %d 个当月有成交量的标的逐个列出（BMW / Santander / '
        'Total 等），若走 canonical 算法要为每个标的取 2019-01 月均收盘，'
        '官方一手源不可能无人值守拿齐 —— 这正是本行原先空着的原因。'
        '⚠ 同 EUREX_INDEX 的 avg_close 口径差告诫。'
        % (f'{cvtc["EUREX_EQUITY"][0]:,.2f}', f'{cvtc["EUREX_EQUITY"][1]:,.0f}',
           days, nlegs['EUREX_EQUITY']))
    note['EUREX_RATES'] = (
        'kind=contract, level=pool_product, multiplier=1 ⇒ base_price_local = 篮子常数。'
        'base_price_basis 应填 **definitional**：利率合约按面值计名义额、不乘结算价，'
        '与 CME_RATES / MX_STIR / MX_BOND / JPX_JGB10Y 同口径（混口径的池占比是假的）。'
        '算法：Eurex 官方月度统计 monthlystat_201901.xls「Interest Rate Derivatives」'
        '分节逐产品张数 × 官方面值，跨币种先用 series/fx.csv 的 2019-01 月均汇率'
        '折成 EUR（1 CHF = %.12f EUR），再按张数加权。'
        '面值出处：Eurex《Contract Specifications…》2018-04-02 合并版（基期前最近一版）'
        '§1.2.1(1)「The par value of any such contract is EUR 100,000.」覆盖 Schatz/'
        'Bobl/Bund/Buxl/BTP/Mid-BTP/Short-BTP/OAT/Mid-OAT/Bono；§1.2.1(2) CONF = '
        'CHF 100,000；§1.1.1(1) Three-Month EURIBOR = EUR 1,000,000。'
        '固定收益期权按其标的期货的面值计（一张期权对应一张期货）。'
        'Σ张数 %s，与官方分节 Sum %s 差 %s 张（= 被剔除的 EUR STX 50 CorpBond (PI)，'
        '公司债指数期货不是面值型合约，影响 < 0.0001%%）。'
        '3M SARON 面值 CHF 1,000,000 是从官方规格「CHF 2,500 per index point」'
        '按与 EURIBOR 同构推导的（%s），2019-01 仅 74 张；改按 CHF 100,000 只动常数 '
        '%.4f EUR = %.4f%%。'
        '⚠ 名义额 ≠ 风险敞口：同样名义额下 Schatz（久期约 1.9 年）与 Buxl（20 年以上）'
        'DV01 差一个数量级，本池占比只能读作「名义额构成」。升级到 DV01 需各合约 CTD '
        '久期，月度成交报表里没有（📌 未找到）。'
        '对照：若改用 Eurex 自己的 Capital Volume ÷ 张数 = %.6f EUR/张（面值 × 结算价，'
        '2019-01 Bund 报价 164.58 ⇒ 单张 164,576.36），比面值口径高 %.1f%% —— '
        '两个都对，但只能选一个，选面值是为了与本仓其它利率池可加。'
        % (chf_per_eur, f'{qty_face:,.0f}', f'{tc_r:,.0f}',
           f'{tc_r - qty_face:,.0f}', SARON_SPEC_URL,
           const_face - alt if saron_qty else 0.0,
           (const_face / alt - 1) * 100 if saron_qty else 0.0,
           const_cv, (const_cv / const_face - 1) * 100))
    for row in rows:
        row['computed_note'] = note[row['product_id']]

    # ── ICE：三行留空，卡点写进 computed_note ────────────────────────────────
    if args.ice_probe:
        ice_probe(args.refresh)

    ice_common = (
        '本会话实测：ICE 的**合约规格页不是障碍**（纯 urllib 全部 HTTP 200，'
        '见 build/basefill/ice_eurex.py --ice-probe）。卡点是**基期权重**。')
    rows.append({
        'product_id': 'ICE_ENERGY', 'base_price_local': '', 'base_ccy': 'USD',
        'basket_constant': '', 'source_url': ICE_MONTHLY_REPORT,
        'computed_note': ice_common + (
            '📌 未填。三处同时缺，缺一处都算不出来：'
            '(1) 分母对不上 —— pools.py 把本行挂在 ice.csv 的 adv_energy_kcontracts 上，'
            '2019-01 = 2,718 千张/日 × 21 日 = 57,078,000 张（全球能源，含 ICE Endex / '
            'ICE Futures U.S. / ICE Futures Abu Dhabi）；而官方唯一的历史分产品表 '
            'https://www.ice.com/report/7 只覆盖 ICE Futures Europe，2019-01 能源各列'
            '相加 = 38,241,726 张，仅占 67.0%。'
            '(2) TTF 张数官方不单列 —— TTF 在 ICE Endex 上，不在 /report/7 里'
            '（表里 "EU Nat Gas" 1,915,161 张是 IFEU 的英国气）；跨所的 '
            'https://www.ice.com/report/147 只有 Natural Gas / Power / Oil & Other '
            '三列，更粗。⇒ contract_specs_todo.csv 里给的出路 (b)「把 TTF 单列」'
            '**做不到**，本次实测证伪。'
            '(3) TTF 没有固定乘数 —— 官方页原文 "Contract Size 1 MW per day in '
            'contract period (i.e. month, quarter, season or year) x 23, 24 or 25 '
            'hours"，一张月度合约 672–744 MWh 不等。'
            '另外基期价格也只齐了一半：Brent / WTI 可走 EIA 官方日度价算 2019-01 月均，'
            '但 ICE Low Sulphur Gasoil（西北欧 ARA，美元/公吨）EIA 没有，'
            'ICE 自己的历史结算价在 Report Center 登录墙后。'
            '已实测到的乘数（可直接入 contract 层）：Brent 1,000 barrels'
            '（ice.com/products/219/specs）、WTI 1,000 barrels（/213/specs）、'
            'Low Sulphur Gasoil 100 metric tonnes（/34361119/specs）。'
            '检索路径：ICE 合约规则 PDF 目录 ice.com/publicdocs/futures/ 与 '
            '/publicdocs/circulars/；Report Center 的 end-of-day 分类看有无免登录的'
            '历史结算价档案；ICE 10-K（SEC 申报）确认有无更细的量口径。'),
    })
    for pid, zh in (('ICE_STIR', '短端内部的 Euribor / Short Sterling / SONIA / '
                                 'Euroswiss'),
                    ('ICE_MLTIR', '中长端内部的 Long Gilt / Medium Gilt / '
                                  'Short Gilt / Swapnote')):
        rows.append({
            'product_id': pid, 'base_price_local': '', 'base_ccy': 'USD',
            'basket_constant': '', 'source_url': ICE_MONTHLY_REPORT,
            'computed_note': ice_common + (
                '📌 未填。ICE 官方唯一的历史分产品表 https://www.ice.com/report/7 '
                '把利率并成**一列** "Interest Rates"（2019-01：期货 37,491,346 张、'
                '期权 7,632,263 张），既不拆 %s，也不拆短端 vs 中长端；'
                'series/ice.csv 的 adv_stir / adv_mltir 来自 ICE Monthly Statistics '
                'Tracking xlsx，同样只有池级合计。⇒ 跨合约权重无从谈起，而这一步不能拍：'
                'Euribor 面值 EUR 1,000,000、Short Sterling GBP 500,000、'
                'SONIA GBP 1,000,000、Long Gilt GBP 100,000，权重错一点常数差一倍以上；'
                '本篮子还是跨币种（EUR + GBP + CHF），记账币 USD，折算要用 '
                'series/fx.csv 的 2019-01 月均。'
                '⚠ 第二层坑：ICE 的短端合约页**不印面值**，只印 "Unit of Trading: '
                'EUR 2,500 * Rate Index"（Euribor，/38527986/specs）与 '
                '"GBP 2,500 * Rate Index"（SONIA，/68361266/specs）—— '
                'EUR/GBP 1,000,000 是反推值不是官方原文，本脚本不写推导值。'
                '已实测到的官方原文：Long Gilt "GBP 100,000 nominal value notional '
                'Gilt with 4%% coupon"（ice.com/products/37650336/specs）。'
                '⚠ 名义额 ≠ 风险敞口：同名义额下 2 年期与 10 年期 DV01 差 5 倍以上'
                '（久期约 1.9 年 vs 约 8 年）。本池占比只能读作「名义额构成」，'
                '不可读作「谁承担了更多利率风险」。将来升级到 DV01 需各合约 CTD 久期，'
                '月度成交报表里没有（📌 未找到，见 build/notional.py 模块 docstring）。'
                '检索路径：ice.com/publicdocs/circulars/ 下的 "CONTRACT RULES: ICE '
                'FUTURES SHORT TERM INTEREST RATE INDEX FUTURES CONTRACTS" 抠面值原文；'
                '分合约张数试 ICE Report Center 其余分类或 ICE 10-K（SEC 申报）。'
                % zh),
        })

    # ── 落盘 ────────────────────────────────────────────────────────────────
    cols = ['product_id', 'base_price_local', 'base_ccy', 'basket_constant',
            'source_url', 'computed_note']
    order = {p: i for i, p in enumerate(
        ['EUREX_RATES', 'EUREX_INDEX', 'EUREX_EQUITY',
         'ICE_ENERGY', 'ICE_STIR', 'ICE_MLTIR'])}
    rows.sort(key=lambda r: order[r['product_id']])
    with open(OUT, 'w', encoding='utf8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    filled = sum(1 for r in rows if r['basket_constant'])
    print('已写出 %s（%d 行：%d 填 / %d 留空）'
          % (os.path.relpath(OUT, ROOT), len(rows), filled, len(rows) - filled))
    return 0


if __name__ == '__main__':
    sys.exit(main())
