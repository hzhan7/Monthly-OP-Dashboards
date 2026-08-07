# -*- coding: utf-8 -*-
"""月度汇率序列（10 个币种对美元，月均 + 月末两条口径）—— 无人值守抓取。

本模块不属于任何一家公司，它是**横截面页的公共底座**：CME 报张数、HKEX 报港币金额、
Cboe 报张数，要放进同一张「谁在跑赢」的图，先得把币种统一到美元。统一时有两个口径，
两个都必须存在，混用哪一个都会把结论算歪：

  fx_avg_<ccy>usd —— 当月所有发布日的等权平均。**配流量**：成交额、营收、费用、
                     手续费收入 …… 凡是「整个月里陆续发生」的量，都该用月均折美元。
  fx_eom_<ccy>usd —— 当月最后一个发布日的即期值。**配存量**：AUM、托管资产、市值、
                     期末未平仓名义额 …… 凡是「某一时点的余额」，都该用月末折美元。

拿月末折成交额，等于把整月的流量按最后一天的汇率记账；拿月均折 AUM，等于给一个
时点余额安一个不存在的平均价。两种错误都不会报错，只会让同比里多出一段汇率噪声。

━━ 本批次的定基规则（口径由上游决定，本模块只提供原料）━━
主口径是**定基名义额** = 张数 × 乘数 × 基期价格 × **基期汇率**，基期锁 BASE_MONTH
（2019-01）。价格与汇率都是常数 ⇒ 增长与份额里既不含标的涨跌、也不含汇率波动，
剩下的才是量的胜负。另算一条**当期名义额**（当期价格 × 当期汇率）只回答「这个市场
现在多大」，不进增长图。

本模块**不提供**取基期汇率的函数（对外只留 latest_month / update 两个接口，
第三个接口会让「谁负责锁基期」变得含糊）。build/ 里的标准写法就四行：

    import csv
    rows = {r['month']: r for r in csv.DictReader(open('series/fx.csv'))}
    base = rows['2019-01']                                   # = fetch.fx.BASE_MONTH
    usd_fixed = qty * multiplier * px_2019_01 * float(base['fx_avg_brlusd'])

━━ 数据源 ━━
主通道 ECB SDMX 数据服务（欧洲央行官方，非聚合商）：
    https://data-api.ecb.europa.eu/service/data/EXR/D.<CCY>.EUR.SP00.A
        ?format=csvdata&detail=dataonly&startPeriod=YYYY-MM-DD
    EXR = 欧元参考汇率数据流；D = 日频；SP00 = 即期；A = 平均值型。
    返回「1 欧元 = 多少 <CCY>」。美元也是其中一个币种（D.USD.EUR.SP00.A），
    所以 10 个币种对美元的交叉汇率由 USD 那条与各币种那条**逐日相除**得到。
    普通 UA、无 cookie、无登录态，urllib 直下。实测 2026-08-06：10 条序列各 5527 个
    观测（2005-01-03 至 2026-08-05），本模块的串行取法同一天两次测到 17 秒与 32 秒
    （ECB 端延迟本身在波动，不是解析变慢）；改 10 线程并发是 6.2 秒 —— 省下的
    十几秒不值得，理由见 _fetch_sdmx。monthly_run 不给 fetch 模块设超时（已核查），
    所以这点抖动不会造成假 FAIL。

备用通道 ECB 静态历史文件：
    https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip
    一个 zip 里一张 eurofxref-hist.csv，全部币种 × 全部发布日（实测 7064 行、
    1999-01-04 起、636 KB）。主通道整体不可用时顶上，**只能维持尾部、不能冷启动**
    （原因见口径坑 7）。

没有用、以及为什么（都实测过，不是听说）：
  · **FRED / fred.stlouisfed.org 不能进生产。** 同一个 URL
    （graph/fredgraph.csv?id=DEXUSEU），urllib **挂住不返回**，curl 立刻
    200 / 127 861 字节 —— 是 Akamai 按 **TLS 指纹** 拦，换 UA 无效
    （与 fetch/hood.py 记的是同一类拦法）。
    ⚠ urllib 那一侧的**失败形态不稳定**，两次实测分别是「32 秒后 RemoteDisconnected」
    与「40 秒读超时」——所以别按异常类型去判断是不是被拦了，判据是「curl 秒回而
    urllib 卡住」。本模块只在**离线对账**时用 curl 拉它，见下面「交叉核对」。
  · **美联储 H.10 官方 DDP** (federalreserve.gov/datadownload/Output.aspx?rel=H10)
    要一个 32 位 series GUID 才出数；GUID 只能从它的交互式 Build 页点出来，
    猜的 ID 一律返回 HTTP 200 + **0 字节**（不是 404，会被误判成网络问题）。
    需要人工点击 = 违反无人值守，直接排除。
  · **BIS**：stats.bis.org 的 SDMX v2 端点对 `BIS,WS_XRU,1.0` 的 series key
    `M.USD.EUR.A` 返回 404（试过的检索路径：/api/v2/data/dataflow/BIS/WS_XRU/1.0/…
    与 lastNObservations 组合）；📌 **未找到**能直接命中的 key 写法。
    批量文件 data.bis.org/static/bulk/WS_XRU_csv_flat.zip 确实存在（10.3 MB），
    但实测 45 秒只下到 2.1 MB（≈48 KB/s），比 ECB 那条慢两个数量级，且只有月频。

━━ 发布节奏 ━━
ECB 每个 TARGET2 营业日 **14:15 CET 定盘、约 16:00 CET 发布**当日参考汇率。
所以「M 月这一行」在 **M 月最后一个营业日当天**就齐了 —— 全仓唯一一条在数据月内
就能定稿的序列，永远不会拖住任何一家的横截面页。

即便如此，本模块仍然**等到看见下个月的观测**才写这一行（见 _complete_months）。
代价：月末落在周五或周末时，这一行晚 1-3 天入库（monthly_run 每天跑，无实质影响）。
换来的：不用在本仓维护一张 TARGET2 假日表。TARGET2 关门日里有耶稣受难日和复活节
星期一两个**移动节日**，自己算就得抄一份复活节算法，而算错的表现是「某个月少算两天
均值」——一个不报错、只让数字偏一点点的错误，正是最贵的那种。

━━ 口径坑（按踩坑概率排序）━━
1. **两列不能混用**，见开头。这是本模块唯一一个「用错了不会报错」的坑，所以排第一。
2. **方向是「1 单位外币 = 多少美元」**，所以 `外币金额 × fx = 美元金额`（乘，不是除）。
   fx_avg_jpyusd 这一列是 0.0063 而不是 158；看到 158 就是有人取了倒数。
   列名后缀 `<ccy>usd` 读作外汇市场惯例的货币对（EURUSD = 一欧元换多少美元）。
3. **交叉汇率必须逐日相除再平均，不能拿两个月均相除。** 这是 Jensen 不等式，
   不是舍入。实测（ECB 原始日频，下面的「差」一律是**相对**差）：
       2008-10  JPY 逐日交叉均 0.01000052 vs 月均相除 0.00997769 → 差 2.29e-3
       2008-10  BRL 逐日交叉均 0.45901024 vs 月均相除 0.45761770 → 差 3.04e-3
       2026-07  JPY 同上两法 0.00615379 vs 0.00615368            → 差 1.80e-5
   差异随当月波动率放大 —— 也就是说，**你最需要它准的那个月，它错得最多**。
   本模块一律逐日相除。（EUR 那列不涉及交叉：它就是 D.USD.EUR.SP00.A 本身。）
4. **ECB 参考汇率是 14:15 CET 的定盘参考价**，不是可成交价、不是全日均价、也不是
   收盘价。与美联储 H.10（12:00 ET 快照）逐月对照 259 个月，月均相对差的中位数：
   HKD 3.5e-5、SGD 2.9e-4、CHF 4.8e-4、EUR 4.8e-4、JPY 4.8e-4、GBP 5.2e-4、
   CAD 5.5e-4、AUD 5.7e-4、SEK 6.3e-4、BRL 1.1e-3。
   每个币种的**最大**差及其月份（2026-08-06 复核实测）：
   HKD 4.1e-4 @2014-02、EUR 4.6e-3 @2008-12、GBP 4.7e-3 @2008-10、
   JPY 4.9e-3 @2009-02、CHF 8.9e-3 @2015-01、BRL 9.6e-3 @2008-09。
   除 HKD 外全部落在金融危机（2008-09 至 2009-02）或瑞郎脱钩（2015-01）——
   快照时点不同 × 当天巨幅波动，属于**两个正确数字的差**，不是解析错误。
   （HKD 那个 4.1e-4 的绝对量级本来就比别人小一个数量级，见口径坑 8。）
   要跟别人的表对数时先问对方用的是哪一家的快照。
5. **月内观测日 = TARGET2 营业日，不是美股交易日、更不是自然日。** 实测 259 个月
   在 18-23 天之间；三个 18 天的月份都是复活节落在 4 月那年（2006-04 / 2017-04 /
   2023-04）。因此「月均」是**营业日等权**平均，不是成交量加权。真要成交量加权，
   得自己按日算，本模块给不了。
6. **月末不是最后一个自然日。** eom 取的是「当月最后一个 ECB 发布日」：259 个月里
   5 个月落在 26/27 号（2009-02-27、2010-02-26 都是 2 月末撞周末），2005-12 落在
   12-30，2006-12 落在 12-29。所以 `eom_date` 单独入库 —— 你自己按「月末往前找
   工作日」推，迟早会在圣诞和复活节那几个月推错。
7. **BRL 在两条通道里的历史深度不一样。** SDMX 的 D.BRL.EUR.SP00.A 从 2000-01-13
   起有值；静态文件 eurofxref-hist.csv 里 BRL 从 **2008-01-02** 才有（那是巴西雷亚尔
   进入每日参考汇率名单的日子，此前整列是 N/A）。主通道选 SDMX 正是为了这 8 年 ——
   没有它，SERIES_START 就只能从 2008 起。备用通道因此只能维持尾部：拿它做冷启动，
   会在 update() 的「首月必须等于 SERIES_START」那道检查上被拦下，而不是悄悄少 3 年。
8. **HKD 是联系汇率，拿它当口径体检的探针。** fx_avg_hkdusd 在 259 个月里只在
   0.127388 - 0.129033 之间动 —— 正好是金管局 7.75-7.85 兑换保证区间的倒数
   （1/7.85 = 0.127389，1/7.75 = 0.129032）。这一列一旦跑出 PLAUSIBLE 给的
   0.1265-0.1300，一定是解析错了（取错列 / 忘了相除 / 取了倒数），不是市场动了。
   反过来说：PLAUSIBLE 对 CAD / CHF / AUD / EUR **抓不出取倒数**——这几个币种跟
   美元长期在 1 附近，倒数与原值的区间是重叠的。别把这道检查当成方向的证明。
9. **两个 ECB 主机名的证书链不一样。** data-api.ecb.europa.eu 把链发全到
   USERTrust ECC（在 macOS 自带的 /private/etc/ssl/cert.pem 那 128 个根里），
   Python 默认 context 直接通过；www.ecb.europa.eu **只发一级中间证书**
   （Sectigo Public Server Authentication CA OV E36），对应的 Sectigo 根不在那 128 个里，
   默认 context 当场 CERTIFICATE_VERIFY_FAILED（openssl s_client 和 curl 都说 OK，
   因为它们用的是另一套根库 —— 这个不一致会让人往网络方向排查半天）。
   所以备用通道要 certifi 才走得通，见 _ssl_ctx。
10. **本模块不写 series/source_dates.csv。** 理由见 update() 的 docstring，
    一句话版：ECB 在**数据月之内**就把这个月的最后一笔发完了，而 source_dates.record()
    有一道「发布日必须严格晚于数据月结束」的护栏。那道护栏是对的，冲突说明 fx 不在
    这张表的适用范围内。真正的发布证据改成入库到行里：`obs_days` 与 `eom_date`。
11. **「币种不齐就跳过这个月」这条规则对头部与尾部的含义完全相反。** 见 _check_tail。
    头部跳过是对的（BRL 2008 年以前不在 ECB 名单上，是事实不是故障）；尾部跳过是
    **静默失败**：最新完整月被丢掉，latest_month 无声退回上一个月，update 什么都不写
    （所以「缺列一律失败」那道护栏根本不会被触发 —— 它守的是写进去的东西，
    而这里是压根不写），而 fx 既没有页面也没有红点，故障不会留下任何信号。
    所以尾部单独立一道检查，判据见 _check_tail。

━━ 交叉核对（2026-08-06 实测，独立来源 = 美联储 H.10，经 FRED 分发，用 curl 取）━━
  · GBP 2011-01 月均：本模块 1.577022 USD/GBP；H.10 EXUSUK = 1.5782 → 相对差 -7.47e-4
  · JPY 2019-01 月均：本模块 0.00918169 USD/JPY；H.10 EXJPUS = 108.9605 JPY/USD
                      → 1/108.9605 = 0.00917764 → 相对差 +4.41e-4
  · BRL 2005-06 月均：本模块 0.414003；H.10 EXBZUS = 2.4148 → 0.414113 → -2.66e-4
  · HKD 2011-01 月均：本模块 0.128528；H.10 EXHKUS = 7.7803 → 0.128530 → -1.27e-5
  另外与 **ECB 自己发布的月频序列** M.<CCY>.EUR.SP00.A 对过账，验证「月均 = 当月
  所有发布日的算术平均」就是 ECB 自己的定义：USD / JPY / BRL 在 2018-11 至 2019-03
  共 15 个月，本模块重算值与官方月频值相对差 ≤ 3.2e-14（纯浮点噪声；这一档量级
  就是 fmean 的求和顺序，换个加法顺序即可上下浮动，不必当成阈值去卡）。
  再者，主备两条通道在重叠区间（2008-01 起）**逐格完全一致**：把主通道断掉、只用
  eurofxref-hist.zip 重跑 update()，_check_no_restatement 在 TOL_REL=1e-9 下一条不报，
  series/fx.csv 逐字节不变。所以备用通道顶上时不会在接缝处留下一段值被"改动"的假象。

━━ 依赖 ━━ 只用标准库。备用通道额外需要 certifi（requirements.txt 没有直接声明它，
它是 curl_cffi==0.16.0 的传递依赖，本机 2026.7.22）；没有 certifi 时备用通道自动放弃，
主通道不受影响。
"""

import csv
import io
import os
import ssl
import statistics
import urllib.request
import zipfile

# ── 币种与列 ────────────────────────────────────────────────────────────────
# 顺序就是 CSV 里的列序，别改：改了列序 = 既有 fx.csv 全表重排，
# 而重排后的文件与旧文件逐行都不一样，幂等检查（monthly_run 的字节比较）当场失效。
CURRENCIES = ['EUR', 'GBP', 'HKD', 'JPY', 'SGD', 'AUD', 'CAD', 'BRL', 'CHF', 'SEK']

SERIES_START = '2005-01'   # 入库起点。ICE 序列从 2011-01 起，这里多给 6 年余量。
BASE_MONTH = '2019-01'     # 定基名义额锁死的基期，见模块开头
MIN_OBS_DAYS = 15          # 一个月的 ECB 发布日少于这么多天 = 数据残缺（实测最少 18 天）
# 10 个币种的**最新观测日**互相最多差这么多个发布日。它们出自同一场 14:15 CET 定盘，
# 正常情况下这个差是 0；给到 3 是留出「某币种当天恰好未定盘」的余地（口径坑 5 说的
# 那种个别空值）。见 _check_tail 的第二段。
MAX_TAIL_LAG_DAYS = 3

# 重述/漂移容差（相对）。CSV 写的是 repr(float) 的完整往返表示，所以同一份源数据
# 重算出来应当**逐位相同**；给到 1e-9 只是留一点浮点求和顺序的余地。
TOL_REL = 1e-9

# 粗筛区间：只抓「取错列 / 忘了相除 / 小数点挪位」这类粗错，抓不出取倒数
# （见口径坑 8）。上下界给得比 259 个月的实测极值宽得多，正常市场波动不会碰到。
PLAUSIBLE = {
    'EUR': (0.50, 2.50),      # 实测 0.9748 - 1.5812
    'GBP': (0.80, 3.00),      # 实测 1.1040 - 2.0718
    'HKD': (0.1265, 0.1300),  # 实测 0.127388 - 0.129033（= 7.85 / 7.75 的倒数）
    'JPY': (0.0020, 0.0300),  # 实测 0.006154 - 0.013094
    'SGD': (0.35, 1.10),      # 实测 0.588773 - 0.831463
    'AUD': (0.30, 1.40),      # 实测 0.609785 - 1.095870
    'CAD': (0.40, 1.30),      # 实测 0.691254 - 1.053751
    'BRL': (0.03, 1.00),      # 实测 0.161689 - 0.639485
    'CHF': (0.40, 2.00),      # 实测 0.758253 - 1.301627
    'SEK': (0.04, 0.30),      # 实测 0.089437 - 0.168266
}

META_COLS = ['obs_days', 'eom_date']
AVG_COLS = ['fx_avg_%susd' % c.lower() for c in CURRENCIES]
EOM_COLS = ['fx_eom_%susd' % c.lower() for c in CURRENCIES]
# 先排完 10 个 avg 再排 10 个 eom，而不是按币种把 avg/eom 两两挨着放。
# 理由就是口径坑 1：两个口径挨着放，切片时手一滑就串了口径，而串了不报错。
HEADER = ['month'] + META_COLS + AVG_COLS + EOM_COLS

CSV_NAME = 'fx.csv'

SDMX_TMPL = ('https://data-api.ecb.europa.eu/service/data/EXR/D.%s.EUR.SP00.A'
             '?format=csvdata&detail=dataonly&startPeriod=%s-01')
HIST_ZIP = 'https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip'

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')


class FxFetchError(RuntimeError):
    """下载失败 / 源站结构变化 / 解析结果不完整。一律炸掉，绝不静默写空列或 NaN。"""


# ── 网络 ────────────────────────────────────────────────────────────────────
def _ssl_ctx():
    """给 www.ecb.europa.eu 用的 context：优先 certifi 的根库。

    见口径坑 9 —— 该主机只发一级中间证书，macOS 自带根库里没有对应的 Sectigo 根，
    默认 context 必然 CERTIFICATE_VERIFY_FAILED。这里**不降级成 CERT_NONE**：
    宁可让备用通道整体缺席（主通道照常工作），也不要为了一条备用路径把校验关掉。
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _http_get(url, timeout=90, context=None):
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as r:
            return r.read()
    except Exception as e:                                # noqa: BLE001
        raise FxFetchError('下载失败 %s: %r' % (url, e)) from e


def _write_bytes(path, data):
    with open(path, 'wb') as f:
        f.write(data)


# ── 取数：主通道（SDMX）─────────────────────────────────────────────────────
def _parse_sdmx_csv(text, ccy):
    """SDMX csvdata → {'YYYY-MM-DD': float}。列名认字段名，不认列序。"""
    rd = csv.DictReader(io.StringIO(text))
    if not rd.fieldnames or 'TIME_PERIOD' not in rd.fieldnames \
            or 'OBS_VALUE' not in rd.fieldnames:
        raise FxFetchError('%s 的 SDMX 响应缺 TIME_PERIOD/OBS_VALUE 列，'
                           '拿到表头 %r' % (ccy, rd.fieldnames))
    out = {}
    for row in rd:
        day, raw = row['TIME_PERIOD'], (row['OBS_VALUE'] or '').strip()
        if not day or raw in ('', 'NaN', 'N/A'):
            continue          # ECB 用空值表示当天未定盘，不是解析失败
        try:
            v = float(raw)
        except ValueError:
            raise FxFetchError('%s %s 的观测值不是数字：%r' % (ccy, day, raw))
        if v <= 0:
            raise FxFetchError('%s %s 的观测值非正：%r' % (ccy, day, raw))
        out[day] = v
    if not out:
        raise FxFetchError('%s 的 SDMX 响应里一个观测都没有' % ccy)
    return out


def _fetch_sdmx(cache_dir):
    """主通道：逐币种拉日频序列，返回 {'CCY': {'YYYY-MM-DD': 1 欧元 = 多少 CCY}}。

    串行而非并发：10 个请求实测合计十几秒，对一个月跑一次的 cron 完全够用，
    而并发的代价是「哪一条失败了」这件事会被 futures 的异常包装糊掉一层。
    """
    os.makedirs(cache_dir, exist_ok=True)
    out = {}
    for ccy in ['USD'] + [c for c in CURRENCIES if c != 'EUR']:
        raw = _http_get(SDMX_TMPL % (ccy, SERIES_START))
        _write_bytes(os.path.join(cache_dir, 'fx_ecb_%s.csv' % ccy), raw)
        out[ccy] = _parse_sdmx_csv(raw.decode('utf-8', 'replace'), ccy)
    return out


# ── 取数：备用通道（静态历史文件）───────────────────────────────────────────
def _fetch_hist_zip(cache_dir):
    """备用通道：一个 zip 拿全部币种。只能维持尾部，不能冷启动（口径坑 7）。"""
    os.makedirs(cache_dir, exist_ok=True)
    blob = _http_get(HIST_ZIP, context=_ssl_ctx())
    _write_bytes(os.path.join(cache_dir, 'fx_ecb_hist.zip'), blob)
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = [n for n in zf.namelist() if n.lower().endswith('.csv')]
        if len(names) != 1:
            raise FxFetchError('eurofxref-hist.zip 里的 csv 不是一个：%r' % zf.namelist())
        text = zf.read(names[0]).decode('utf-8', 'replace')
    except zipfile.BadZipFile as e:
        raise FxFetchError('eurofxref-hist.zip 不是合法 zip：%r' % e) from e

    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    if not header or header[0].strip() != 'Date':
        raise FxFetchError('eurofxref-hist.csv 表头不以 Date 开头：%r' % (header,))
    want = ['USD'] + [c for c in CURRENCIES if c != 'EUR']
    idx = {}
    for c in want:
        if c not in header:
            raise FxFetchError('eurofxref-hist.csv 里没有 %s 列（表头 %r）' % (c, header))
        idx[c] = header.index(c)

    out = {c: {} for c in want}
    for row in rd:
        if not row or not row[0].strip():
            continue
        day = row[0].strip()
        if day[:7] < SERIES_START:
            continue
        for c in want:
            raw = row[idx[c]].strip()
            if raw in ('', 'N/A'):
                continue      # 该币种当天/当年尚未纳入参考汇率名单
            out[c][day] = float(raw)
    if not out['USD']:
        raise FxFetchError('eurofxref-hist.csv 里 %s 之后没有 USD 观测' % SERIES_START)
    return out


def fetch_daily(cache_dir):
    """拿日频欧元参考汇率。主通道失败才走备用通道，两条都失败就抛。

    两条错误信息一起抛出来：只报后一条的话，日志上会显示成「证书校验失败」，
    而真正的故障多半在前一条（SDMX 超时 / 改版），排查方向整个错。
    """
    try:
        return _fetch_sdmx(cache_dir)
    except FxFetchError as primary:
        try:
            return _fetch_hist_zip(cache_dir)
        except FxFetchError as backup:
            raise FxFetchError(
                'ECB 两条通道都失败。主(SDMX): %s ‖ 备(hist.zip): %s'
                % (primary, backup)) from primary


# ── 折算与聚合 ──────────────────────────────────────────────────────────────
def _cross(daily, ccy, day):
    """当日「1 单位 <ccy> = 多少美元」。

    ECB 全部报价都是「1 欧元 = 多少 X」，所以：
        EUR → 直接就是 USD 那条（1 欧元 = 多少美元）
        其余 → USD 那条 ÷ 该币种那条，**同一天**相除（口径坑 3）
    """
    usd = daily['USD'][day]
    return usd if ccy == 'EUR' else usd / daily[ccy][day]


def _scope(daily):
    """算出「10 个币种齐备」的月份集合，以及每月的发布日列表。

    齐备的判据有两条，缺一不可：
      · 该月每个币种的**发布日集合与 USD 那条完全相同** —— 少一天就会让那个币种的
        月均建立在与别人不同的样本上，而 21 天里少 1 天造成的偏差只有千分之几，
        小到不会有人发现，正好落在「错得刚好看不出来」的区间里；
      · 发布日不少于 MIN_OBS_DAYS 天。
    不齐备的月份**跳过而不是抛异常** —— BRL 之类的币种是某年才纳入参考汇率名单的，
    「它还没开始」是源数据的事实，不是故障。真正会出问题的情形（冷启动却只拿到
    备用通道的浅历史）由 update() 的首月检查兜住，见口径坑 7。

    ⚠ 这条「跳过」只对**头部**成立。尾部同样被跳过就是静默失败，由 _check_tail 单独
    拦下 —— 本函数只管算，不区分头尾，区分是 _check_tail 的职责（口径坑 11）。
    """
    # 先把每个币种按月分桶，再逐月比集合。不这么做的话，「本月这个币种有哪些天」
    # 每问一次都要扫一遍该币种的全部 5550 个观测，10 币种 × 259 个月 = 1400 万次比较。
    buckets = {}
    for ccy, series in daily.items():
        b = {}
        for day in series:
            b.setdefault(day[:7], set()).add(day)
        buckets[ccy] = b

    good = {}
    for mon, ref in buckets['USD'].items():
        if mon < SERIES_START or len(ref) < MIN_OBS_DAYS:
            continue
        if any(buckets[c].get(mon) != ref for c in buckets if c != 'USD'):
            continue
        good[mon] = sorted(ref)
    return good


def _day_counts(daily, mon):
    """{'CCY': 该币种在 mon 月的发布日集合}。只为组装错误信息，不参与聚合。"""
    return {ccy: {d for d in series if d[:7] == mon} for ccy, series in daily.items()}


def _check_tail(daily, scope):
    """尾部齐备检查 —— _scope 的「不齐就跳过」在这一端必须反过来判。

    ━━ 为什么头尾要用相反的判据 ━━
    _scope 对「10 个币种发布日集合不一致」的月份一律跳过。对**头部**这是对的：
    BRL 2008-01 才进 ECB 每日参考汇率名单，在那之前它没有值是**事实**。
    对**尾部**同样跳过，则是把唯一一种「只可能是故障」的情形当成了正常：
    最新完整月缺币种，只能是 ECB 改版、某币种被移出名单，或响应被截断。

    这个故障的形态是**静默的**，所以值得单开一道检查：
      · compute_monthly 少算一个月，_validate 一条都不报（它只体检算出来的那些月，
        算都没算的月份不在它视野里）；
      · latest_month 无声退回上一个月；
      · update 因此一行都不写 —— README 那条「缺列一律失败」的护栏守的是**写进去的
        东西**，什么都不写正好绕过它，也不会留下 NaN 让人看见；
      · fx 不上任何页面，首页没有它的红点，roster 也不给它判新鲜度。
    四件事叠起来 = 一个不报错、不留痕、只让序列停在旧月份的故障。
    实测复现：删掉 SEK 的 2026-06 起观测，修复前 compute_monthly + _validate 全过，
    latest_month 从 2026-07 退回 2026-05（见 fetch/test_fx.py::test_tail_gap_*）。

    判据一：USD 最新观测所在月的**前一个月**（= 应当已经完整的那个月）必须在 scope 里。
    头部那些合法缺席的月份都远早于它，不受影响。

    判据二（加固）：10 个币种的最新观测日互相不差超过 MAX_TAIL_LAG_DAYS 个发布日。
    判据一盯的是「最新完整月」，若某币种是在**当前未完月**中途开始缺失，最新完整月仍
    齐备，故障要拖到下个月才暴露。这一条把发现时间提前到当天。
    「发布日」用**全部币种观测日的并集**当日历，不自己算 TARGET2 假日 —— 理由与
    _complete_months 一样：复活节是移动节日，自己算错的表现是一个不报错的偏差。
    """
    newest_day = max(daily['USD'])
    prev = _prev_month(newest_day[:7])

    # 序列刚起步时没有「前一个月」可查（真实数据里不会发生：SERIES_START 是 2005-01）。
    if prev >= SERIES_START:
        cnt = _day_counts(daily, prev)
        ref = cnt.get('USD', set())
        if len(ref) < MIN_OBS_DAYS:
            raise FxFetchError(
                '尾部月份 %s 的 USD 只有 %d 个发布日（下限 %d，实测正常区间 18-23）——'
                'USD 最新观测是 %s，说明这个月本该是完整的。响应被截断或源站改版了，'
                '不是「这个月还没过完」。' % (prev, len(ref), MIN_OBS_DAYS, newest_day))
        if prev not in scope:
            short = sorted((c, len(v)) for c, v in cnt.items()
                           if c != 'USD' and v != ref)
            raise FxFetchError(
                '尾部月份 %s 的 10 个币种发布日不一致：该月 USD 有 %d 个发布日，'
                '而 %s。头部缺币种是事实（某币种当年尚未纳入 ECB 名单），'
                '尾部缺币种只可能是故障（ECB 改版 / 币种被移出名单 / 响应被截断）。'
                '放行的话这个月会被静默跳过，latest_month 无声退回上一个月，'
                'update 一行都不写，而 fx 没有页面也没有红点 —— 不会有任何信号。'
                % (prev, len(ref),
                   '、'.join('%s 只有 %d 个' % (c, n) for c, n in short)))

    # 判据二
    all_days = sorted({d for series in daily.values() for d in series})
    rank = {d: i for i, d in enumerate(all_days)}
    last = len(all_days) - 1
    lagging = sorted((c, max(s), last - rank[max(s)]) for c, s in daily.items()
                     if last - rank[max(s)] > MAX_TAIL_LAG_DAYS)
    if lagging:
        raise FxFetchError(
            '这些币种的最新观测比全表最新发布日 %s 落后超过 %d 个发布日：%s。'
            '10 个币种出自同一场 14:15 CET 定盘，正常应当完全对齐 —— '
            '落后说明该币种的那条序列被截断或已被移出名单。'
            % (all_days[-1], MAX_TAIL_LAG_DAYS,
               '、'.join('%s 停在 %s（落后 %d 个发布日）' % x for x in lagging)))


def _complete_months(months, daily):
    """只保留**已经完整**的月份：存在一个更晚月份的观测，才算这个月收完了。

    判据不用「今天是几号」，因为那要求本机时钟和 TARGET2 日历都对；
    用源数据自己的最新观测则是源头自己说的话。代价见「发布节奏」那一节。
    """
    newest_day = max(daily['USD'])
    return [m for m in sorted(months) if m < newest_day[:7]]


def compute_monthly(daily):
    """日频 → 月频，返回 {'YYYY-MM': {列名: 值}}（只含完整月，按月升序）。"""
    scope = _scope(daily)
    _check_tail(daily, scope)      # 尾部缺币种只可能是故障，不许像头部那样静默跳过
    out = {}
    for mon in _complete_months(scope, daily):
        days = scope[mon]
        rec = {'obs_days': len(days), 'eom_date': days[-1]}
        for ccy in CURRENCIES:
            series = [_cross(daily, ccy, d) for d in days]
            rec['fx_avg_%susd' % ccy.lower()] = statistics.fmean(series)
            rec['fx_eom_%susd' % ccy.lower()] = series[-1]
        out[mon] = rec
    if not out:
        raise FxFetchError('聚合后没有任何一个完整月 —— 源数据只覆盖了当前未完月？')
    return dict(sorted(out.items()))


def _validate(monthly):
    """任何一格缺失或跑出粗筛区间 → 抛异常。宁可整月不更新，也不写半行。"""
    for mon, rec in sorted(monthly.items()):
        missing = [c for c in HEADER[1:] if rec.get(c) is None]
        if missing:
            raise FxFetchError('%s 缺列 %s —— 解析异常，拒绝写入' % (mon, missing))
        if rec['obs_days'] < MIN_OBS_DAYS:
            raise FxFetchError('%s 只有 %d 个发布日（下限 %d）'
                               % (mon, rec['obs_days'], MIN_OBS_DAYS))
        if rec['eom_date'][:7] != mon:
            raise FxFetchError('%s 的 eom_date 是 %s，不在本月内'
                               % (mon, rec['eom_date']))
        for ccy in CURRENCIES:
            lo, hi = PLAUSIBLE[ccy]
            for col in ('fx_avg_%susd' % ccy.lower(), 'fx_eom_%susd' % ccy.lower()):
                v = rec[col]
                if not (lo <= v <= hi):
                    raise FxFetchError(
                        '%s %s = %r 跑出粗筛区间 [%s, %s] —— 多半是取错列或取了倒数'
                        % (mon, col, v, lo, hi))
    # 月份必须连续：中间断一个月，build 里做同比时会静默拿错基数
    ms = sorted(monthly)
    for a, b in zip(ms, ms[1:]):
        if _next_month(a) != b:
            raise FxFetchError('聚合结果在 %s 与 %s 之间断月' % (a, b))
    return ms[-1]


def _next_month(mon):
    y, m = int(mon[:4]), int(mon[5:7])
    return '%04d-01' % (y + 1) if m == 12 else '%04d-%02d' % (y, m + 1)


def _prev_month(mon):
    y, m = int(mon[:4]), int(mon[5:7])
    return '%04d-12' % (y - 1) if m == 1 else '%04d-%02d' % (y, m - 1)


# ── CSV 读写 ────────────────────────────────────────────────────────────────
def _fmt(v):
    """写回 CSV 用最短往返表示（repr(float)），与 series/cboe.csv 的风格一致。

    小数点后那一长串**不是精度声明**，是往返保真：ECB 的原始报价只有 4-6 位有效
    数字，月均的真实不确定度在 1e-5 相对量级（见口径坑 4）。留全位数换来的是
    「重跑必然逐字节相同」和「重述必然被 TOL_REL 抓到」这两件事同时成立。
    显示格式由 build/ 决定，别在这里截。
    """
    return repr(float(v))


def _read_csv(path):
    if not os.path.exists(path):
        return list(HEADER), []
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if not rows:
        return list(HEADER), []
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    missing = [c for c in HEADER if c not in header]
    if missing:
        raise FxFetchError('series/%s 里没有这些列：%s' % (CSV_NAME, missing))
    return header, body


def _check_no_restatement(monthly, have, idx):
    """重算既有月份，与已入库值逐格比对；对不上就抛。

    为什么值得为此多写一段：本模块与其他家不同 —— 别人每月拿到的是**一份新文件**，
    历史被改了通常连同新文件一起来；ECB 是一条**一直在原地的长序列**，某一天悄悄
    改掉 2015 年某天的定盘价，下次重算就会与已入库值不一致，而「只填空不覆盖」的
    写法会让这件事永远不被发现。所以这里主动去撞它。

    撞到之后本模块会连续失败（fx 那一家 FAIL，其余十一家不受影响）。这是故意的：
    定基名义额的基期汇率一旦被重述，全站跨币种口径都得重算，那是人该做的决定。
    人工处置：核对 ECB 的修订说明，确认后手工改 series/fx.csv 对应行再重跑。
    """
    bad = []
    for mon, rec in sorted(monthly.items()):
        row = have.get(mon)
        if row is None:
            continue
        if row[idx['obs_days']].strip() and \
                row[idx['obs_days']].strip() != str(rec['obs_days']):
            bad.append((mon, 'obs_days', row[idx['obs_days']], rec['obs_days']))
        if row[idx['eom_date']].strip() and \
                row[idx['eom_date']].strip() != rec['eom_date']:
            bad.append((mon, 'eom_date', row[idx['eom_date']], rec['eom_date']))
        for col in AVG_COLS + EOM_COLS:
            old = row[idx[col]].strip()
            if not old:
                continue
            new = rec[col]
            if abs(float(old) - new) > TOL_REL * abs(new):
                bad.append((mon, col, old, new))
    if bad:
        raise FxFetchError(
            'ECB 重述或口径漂移：已入库值与重算值不符（前 5 条）%r —— '
            '本模块不自动覆盖历史，请人工核对 ECB 修订说明后改 series/%s 再重跑'
            % (bad[:5], CSV_NAME))


# ── 对外接口 ────────────────────────────────────────────────────────────────
def latest_month(cache_dir):
    """ECB 源当前**已完整**的最新月 'YYYY-MM'。

    抓不到 / 校验不过一律抛 FxFetchError，不返回 None 掩盖故障。
    注意它可能比日历上「上个月」再晚一步：月末落在周五或周末时，要等下个月的第一个
    TARGET2 营业日出数才算完整（见「发布节奏」）。
    """
    return _validate(compute_monthly(fetch_daily(cache_dir)))


def update(series_dir, cache_dir):
    """把新月份追加进 series/fx.csv，返回新增月份列表（升序）。

    幂等保证：
      · 已存在的月份不重复追加；
      · 已经有值的单元格**永不覆盖**（ECB 若重述，由 _check_no_restatement 拦下来
        交给人，而不是本模块自作主张吞掉）；
      · 只对既有行里原本为空的格子回补（正常情况下不会有空格，这条是为手工补过表
        的情形留的），回补不计入返回值；
      · 未触碰的单元格是原样字符串搬运，所以「什么都没变」时文件逐字节不变。

    ═══ 为什么本模块不写 series/source_dates.csv ═══
    那张表答的是「官方把这个月的数据发出来的那一天」，而 source_dates.record() 有一道
    护栏：发布日必须**严格晚于数据月结束**（source_dates.py 里那段注释说得很清楚 ——
    月还没过完就「发布」了当月数据，是取错字段的典型症状）。

    ECB 恰恰在数据月**之内**就把这个月发完了：7 月这一行的最后一笔是 7 月最后一个
    TARGET2 营业日当天 16:00 CET 发的。真按事实填 2026-07-31，护栏会拒收；为了绕过
    护栏改填 8 月的某一天，那就是编造。护栏是对的，冲突只说明 fx 不在这张表的
    适用范围内 —— 它不是「一期报告」，是一条连续序列。

    所以发布证据改成入库到行里，比台账更硬：`eom_date` 是这一行最后一笔观测的**实际
    日期**（源头自述），`obs_days` 是这一行由多少个发布日平均而来。两者都能拿去跟 ECB
    的日历逐日核对。fx.csv 也不上任何页面抬头，没有「官方发布于」那半句要印。
    """
    csv_path = os.path.join(series_dir, CSV_NAME)
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    have = {r[0]: r for r in body}

    monthly = compute_monthly(fetch_daily(cache_dir))
    _validate(monthly)
    _check_no_restatement(monthly, have, idx)

    added = []
    for mon in sorted(monthly):
        rec = monthly[mon]
        if mon in have:
            row = have[mon]
            for col in META_COLS + AVG_COLS + EOM_COLS:      # 只填空，不覆盖
                if not row[idx[col]].strip():
                    row[idx[col]] = (str(rec[col]) if col in META_COLS
                                     else _fmt(rec[col]))
            continue
        row = [''] * len(header)
        row[idx['month']] = mon
        for col in META_COLS:
            row[idx[col]] = str(rec[col])
        for col in AVG_COLS + EOM_COLS:
            row[idx[col]] = _fmt(rec[col])
        have[mon] = row
        body.append(row)
        added.append(mon)

    body.sort(key=lambda r: r[0])

    # 落盘前的最后两道闸门 —— 这两条只有在合并了既有行之后才成立，所以放在这里而不是
    # _validate 里（那里只看本次抓到的部分）。
    if body[0][idx['month']] != SERIES_START:
        raise FxFetchError(
            'series/%s 的首月是 %s，不是 SERIES_START=%s —— 多半是冷启动时走了备用通道'
            '（它拿不到 BRL 的 2008 年以前，见口径坑 7）。请等主通道恢复后重跑，'
            '不要在这个状态下发布。' % (CSV_NAME, body[0][idx['month']], SERIES_START))
    for a, b in zip(body, body[1:]):
        if _next_month(a[idx['month']]) != b[idx['month']]:
            raise FxFetchError('series/%s 在 %s 与 %s 之间断月'
                               % (CSV_NAME, a[idx['month']], b[idx['month']]))
    if BASE_MONTH not in have:
        raise FxFetchError('series/%s 里没有基期 %s 那一行，定基口径无从算起'
                           % (CSV_NAME, BASE_MONTH))

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)
    return sorted(added)


if __name__ == '__main__':
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print('latest:', latest_month(os.path.join(_here, 'cache')))
    print('added :', update(os.path.join(_here, 'series'),
                            os.path.join(_here, 'cache')))
