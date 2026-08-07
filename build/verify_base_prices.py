# -*- coding: utf-8 -*-
"""series/contract_specs.csv 里那几个**实测**基期价格的复算器 —— 联网，手动跑，不进 cron。

用法:
    python3 build/verify_base_prices.py            # 重下官方文件、重算、比对，不一致退 1
    python3 build/verify_base_prices.py --show     # 同上，另打印中间量（逐日序列的首末几笔）

━━ 为什么需要这个脚本 ━━
`base_price_local` 那一列的 6 个实测值原本是**手抄进表的字面量**：取数用的下载与求均值
代码没有留在仓里，`cache/` 又被 gitignore。于是仓库自己没有能力回答「这个数是怎么来的」。

`check_specs.py` 的 C5 只校验「冗余列 = 乘数 × 基期价」这个**内部一致性**，所以
「把基期价换成月末收盘 2704.1001 并同步改冗余列」这个变异它抓不住 —— 而那正是模块
docstring 点名的、代价 3.7% 的那种错（SPX 2019-01 月均 2607.39 vs 月末 2704.10）。
C5 守形状，本脚本守**事实**：数字与官方文件对不上就退 1。

本脚本**不进 cron**：它每跑一次要下 4 MB 官方文件，而这些常数按定义永不改变
（基期锁死 2019-01）。它是「改了这几行之后手动跑一次」和「验收时复核」用的。
cron 里跑的是 check_specs.py（monthly_run preflight），那个不联网。

━━ 覆盖范围与「新行必须自报家门」━━
WANT 覆盖表里全部 base_price_basis=avg_close 的行。脚本最后会反查一遍：
表里若出现了 WANT 之外的 avg_close 行，直接判失败 —— 一个**实测**值没有复算路径，
就等于又回到了「手抄字面量」的状态，这个脚本存在的意义正是不让那件事再发生。
（definitional 的行不在此列：它们的价格项按定义就是 1，没有什么可复算的。）

━━ 数据源（全部 Cboe 官方 CDN，无登录态、无 cookie、普通 UA）━━
指数日频收盘：https://cdn.cboe.com/api/global/us_indices/daily_prices/<SYM>_History.csv
    SPX 的值列叫 SPX，XSP / VIX 的叫 CLOSE（表头不一样，认字段名不认列序）。
    日期列 DATE 是 MM/DD/YYYY。
VX 期货逐合约历史：
    https://cdn.cboe.com/data/us/futures/market_statistics/historical_data/VX/VX_<最终结算日>.csv
    一个文件 = 一张合约的全部交易日，列 Trade Date / Futures / Open / High / Low /
    Close / Settle / …。**取 Settle 不取 Close**：Close 是最后一笔成交价，无成交日
    直接是 0.0000（实测：VX 周度合约多日 Close=0.0000，而 Settle 正常），
    拿 Close 求均值会把那些天当成 0 拉进去。

━━ VX 近月的两个判断，都在下面的代码里写死并自校验 ━━
1. **只用月度合约，不用周度合约。** Cboe 的周度 VX 与月度 VX 在文件里同名
   （标签都写 "F (Jan 2019)"），只能靠最终结算日区分。实测 2019-01 成交量：
   月度 Jan 合约 7-15 万张/日，周度 Jan-09 / Jan-23 合约 0-35 张/日 —— 差 4 个数量级。
   「近月」在市场惯例里指的就是近月**月度**合约。
2. **滚月在最终结算日当天。** 到期合约当天只交易到 8:00 CT，其 Settle 是最终结算价
   （SOQ），不是一个完整交易日的行情。实测这个选择只影响 21 天里的 1 天，
   两种约定的均值差 0.037%（脚本会把另一种约定的值一并打出来，不必靠记忆）。
"""

import argparse
import csv
import datetime
import io
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SPECS = os.path.join(ROOT, 'series', 'contract_specs.csv')

BASE_MONTH = '2019-01'          # 与 check_specs.BASE_MONTH / notional.BASE_MONTH 同源
BASE_YM = (2019, 1)
EXPECT_TRADING_DAYS = 21        # 2019-01 的美股交易日数（1/1 元旦、1/21 马丁路德金日）

INDEX_CDN = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/%s_History.csv'
VX_CDN = ('https://cdn.cboe.com/data/us/futures/market_statistics/'
          'historical_data/VX/VX_%s.csv')

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# product_id → (复算方法, 参数)。覆盖表里全部 base_price_basis=avg_close 的行。
WANT = {
    'CBOE_SPX_OPT':   ('index', ('SPX', 'SPX')),
    'CME_MES_SP500':  ('index', ('SPX', 'SPX')),
    'IDXREF_US_SPX':  ('index', ('SPX', 'SPX')),
    'CBOE_XSP_OPT':   ('index', ('XSP', 'CLOSE')),
    'CBOE_VIX_OPT':   ('index', ('VIX', 'CLOSE')),
    # VX 期货一张 = 1000 × **期货结算价**，不是 VIX 现货指数。两者 2019-01 差约 0.95%。
    'CBOE_VIX_FUT':   ('vx_front', ()),
}

TOL_REL = 1e-12                 # 「比对到 1e-12」：留的是求和顺序那点末位余地，不是精度声明


class VerifyError(RuntimeError):
    """下载失败 / 官方文件改版 / 交易日数不对 —— 一律炸，不返回一个「差不多」的值。"""


# ── 网络 ──────────────────────────────────────────────────────────────────
def _get(url):
    req = urllib.request.Request(url, headers={'User-Agent': _UA, 'Accept': '*/*'})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception as e:                                  # noqa: BLE001
        raise VerifyError('下载失败 %s: %r' % (url, e)) from e


# ── 指数日频收盘 ──────────────────────────────────────────────────────────
def index_series(sym, col):
    """{'YYYY-MM-DD': 收盘} —— 只取 BASE_MONTH 那个月。"""
    rd = csv.DictReader(io.StringIO(_get(INDEX_CDN % sym)))
    if not rd.fieldnames or 'DATE' not in rd.fieldnames or col not in rd.fieldnames:
        raise VerifyError('%s_History.csv 缺 DATE/%s 列，拿到表头 %r'
                          % (sym, col, rd.fieldnames))
    y, m = BASE_YM
    out = {}
    for r in rd:
        d = (r['DATE'] or '').strip()          # MM/DD/YYYY
        if len(d) != 10 or d[2] != '/' or d[5] != '/':
            raise VerifyError('%s_History.csv 的 DATE 不是 MM/DD/YYYY：%r' % (sym, d))
        if int(d[6:]) == y and int(d[:2]) == m:
            out['%04d-%02d-%02d' % (y, m, int(d[3:5]))] = float(r[col])
    return out


# ── VX 近月结算价 ─────────────────────────────────────────────────────────
def vx_settlement_date(year, month):
    """VX 月度合约的最终结算日：**次月**第三个周五往前数 30 个日历日（Cboe 规格页）。

    结果必然落在周三（第三个周五 − 30 天 = 周三），下面 assert 掉 —— 这是这条
    规则唯一一个免费的自校验点，规则抄错了它会当场响。
    """
    y, m = (year + 1, 1) if month == 12 else (year, month + 1)
    d = datetime.date(y, m, 1)
    d += datetime.timedelta(days=(4 - d.weekday()) % 7)      # 当月第一个周五
    third_friday = d + datetime.timedelta(days=14)
    settle = third_friday - datetime.timedelta(days=30)
    if settle.weekday() != 2:
        raise VerifyError('%04d-%02d 的 VX 最终结算日算出来是 %s（星期 %d），不是周三 ——'
                          '规则抄错了' % (year, month, settle, settle.weekday()))
    return settle


def vx_contract(settle_date):
    """一张 VX 月度合约的 {'YYYY-MM-DD': Settle}，只保留 BASE_MONTH 那个月。"""
    txt = _get(VX_CDN % settle_date.isoformat())
    rd = csv.DictReader(io.StringIO(txt))
    need = ('Trade Date', 'Settle', 'Total Volume')
    if not rd.fieldnames or any(c not in rd.fieldnames for c in need):
        raise VerifyError('VX_%s.csv 缺 %s 列，拿到表头 %r'
                          % (settle_date, list(need), rd.fieldnames))
    out, vol = {}, {}
    for r in rd:
        d = (r['Trade Date'] or '').strip()
        if d.startswith(BASE_MONTH):
            out[d] = float(r['Settle'])
            vol[d] = float(r['Total Volume'] or 0)
    if not out:
        raise VerifyError('VX_%s.csv 里没有 %s 的交易日 —— 合约选错了？'
                          % (settle_date, BASE_MONTH))
    return out, vol


def vx_front_series(show=False):
    """基期月每个交易日的**近月月度合约结算价**，外加另一种滚月约定的值（只为打印）。

    滚月：最终结算日**当天**就换到次月合约。理由见模块 docstring 判断 2。
    """
    e1 = vx_settlement_date(*BASE_YM)                       # 本月到期的那张
    y, m = BASE_YM
    e2 = vx_settlement_date(*((y + 1, 1) if m == 12 else (y, m + 1)))
    near, near_vol = vx_contract(e1)
    nxt, nxt_vol = vx_contract(e2)

    cut = e1.isoformat()
    rolled, held = {}, {}
    for d in sorted(set(near) | set(nxt)):
        rolled[d] = near[d] if d < cut else nxt[d]          # 约定 A：结算日当天滚
        held[d] = near[d] if d <= cut else nxt[d]           # 约定 B：结算日之后滚
    if show:
        print('  VX 月度合约：本月到期 %s（%d 个交易日，当月成交 %d 张），'
              '次月到期 %s（%d 个交易日，当月成交 %d 张）'
              % (e1, len(near), sum(near_vol.values()),
                 e2, len(nxt), sum(nxt_vol.values())))
    return rolled, held


# ── 比对 ──────────────────────────────────────────────────────────────────
def mean(series, label):
    """算术平均。刻意用 sum()/len() 而不是 statistics.fmean —— 表里那几个字面量就是
    这么算出来的，换一种求和顺序会改动末位，而比对容差只有 1e-12。"""
    if len(series) != EXPECT_TRADING_DAYS:
        raise VerifyError('%s 在 %s 只有 %d 个交易日（应为 %d）—— 官方文件改版，'
                          '或日期过滤写错了' % (label, BASE_MONTH, len(series),
                                              EXPECT_TRADING_DAYS))
    v = [series[d] for d in sorted(series)]
    return sum(v) / len(v)


def load_specs():
    with open(SPECS, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--show', action='store_true', help='打印中间量')
    a = ap.parse_args(argv)

    rows = {(r['product_id'] or '').strip(): r for r in load_specs()}
    print('== 重算 %s 的实测基期价格（源：cdn.cboe.com 官方文件）==' % BASE_MONTH)

    # 先把要用的官方序列各下一次，别在循环里重复下同一个文件
    idx_cache, computed = {}, {}
    for pid, (how, arg) in sorted(WANT.items()):
        if how == 'index':
            sym, col = arg
            if (sym, col) not in idx_cache:
                s = index_series(sym, col)
                idx_cache[(sym, col)] = s
                if a.show:
                    ds = sorted(s)
                    print('  %s 取 %s 列：%s=%s … %s=%s'
                          % (sym, col, ds[0], s[ds[0]], ds[-1], s[ds[-1]]))
            computed[pid] = mean(idx_cache[(sym, col)], '%s %s' % (sym, col))
        elif how == 'vx_front':
            rolled, held = vx_front_series(show=a.show)
            computed[pid] = mean(rolled, 'VX 近月结算价')
            alt = mean(held, 'VX 近月结算价(另一种滚月)')
            print('  VX 近月滚月约定：结算日当天滚 = %r，结算日之后滚 = %r（差 %.4f%%）'
                  % (computed[pid], alt, (alt / computed[pid] - 1) * 100))
            spot = mean(idx_cache.get(('VIX', 'CLOSE')) or index_series('VIX', 'CLOSE'),
                        'VIX CLOSE')
            print('  VX 近月结算价 vs VIX 现货月均 %r：%+.4f%% —— '
                  'VX 一张 = 1000 × 期货结算价，用现货会把这一截误差写进定基常数'
                  % (spot, (computed[pid] / spot - 1) * 100))

    # 反查：表里不许出现 WANT 之外的 avg_close 行（见模块 docstring）
    orphan = sorted(pid for pid, r in rows.items()
                    if (r['base_price_basis'] or '').strip() == 'avg_close'
                    and pid not in WANT)

    bad = []
    print('\n%-16s %-24s %-24s %s' % ('product_id', '重算值', '表内值', '判定'))
    for pid in sorted(WANT):
        got = computed[pid]
        r = rows.get(pid)
        if r is None:
            bad.append('%s 不在 %s 里 —— WANT 与表已经对不上了' % (pid, SPECS))
            print('%-16s %-24r %-24s MISSING' % (pid, got, '(无此行)'))
            continue
        have = float(r['base_price_local'])
        ok = abs(have - got) <= TOL_REL * abs(got)
        # 顺带把冗余列也复核一遍：C5 只保证它 = 乘数 × 表内价，这里保证那个价是真的
        unit = float(r['base_notional_per_unit_local'])
        mult = float(r['multiplier'])
        ok_unit = abs(unit - mult * got) <= 1e-9 * abs(mult * got)
        print('%-16s %-24r %-24r %s' % (pid, got, have, 'OK' if ok and ok_unit else 'MISMATCH'))
        if not ok:
            bad.append('%s base_price_local 表内 %r ≠ 重算 %r（相对差 %.3e）'
                       % (pid, have, got, abs(have - got) / abs(got)))
        if not ok_unit:
            bad.append('%s base_notional_per_unit_local 表内 %r ≠ 乘数 %r × 重算价 %r'
                       % (pid, unit, mult, got))

    for pid in orphan:
        bad.append('%s 的 base_price_basis=avg_close，却不在本脚本的 WANT 里 —— '
                   '一个实测值没有复算路径，等于又回到了手抄字面量的状态' % pid)

    if bad:
        print('\nFAIL %d 条：' % len(bad))
        for b in bad:
            print('  · %s' % b)
        return 1
    print('\nOK %d 行基期价格与官方文件逐位相符（容差 %g 相对），'
          '表里没有第 %d 个无复算路径的 avg_close 行' % (len(WANT), TOL_REL, len(WANT) + 1))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except VerifyError as e:
        print('FAIL %s' % e)
        sys.exit(1)
