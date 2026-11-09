# SLM（Sallie Mae）—— SMB 私人学生贷 ABS 信托：数据源、口径、映射与回源核对

2026-11-09 接入。页面 `/slm/`，生成走 `build/single.py` + `build/specs/slm.py`，抓取 `fetch/slm.py`。
本文所有数字都是当天实测；核对脚本在会话 scratchpad（`ref/slm_ref.py` 是与 `fetch/slm.py`
互相独立的第二份实现，`scripts/csv_vs_reports.py` 把 CSV 与服务报告原文逐列对）。

---

## 0. 判定

**可做，但页面上没有一个数是官方直接发布的合计 —— 全部自算。**
官方只发 41 个信托 × 19 个指标块的逐信托比率，没有任何合计 / 加权数。本页按日历月，
把当月仍在报告的信托按各比率**自己的分母**还原成金额、相加、再除。
还原是精确的：2026-08 / 2026-09 两个月把 38–40 份服务报告的分项金额逐份对过，
每个信托每一项「xlsx 还原值 − 报告原文」都是 $0.00；7 个月份的核对见 §6。

| 上页 | 不上页（理由见 §7） |
|---|---|
| 池余额合计（表内 / 表外）、P&I 还款余额合计、池余额加权发行后期数 | Since-issued CPR、Total / Voluntary CPR by Trust |
| P&I 还款占比、任意还款状态占比 | 累计违约、累计回收 |
| Forbearance、Deferment 占比 | 债券余额、超额抵押 |
| 30–59 / 60–89 / 90+ 天逾期、30+ 天合计 | 「同账龄对比」图（底座不产出横截面图型） |
| 当期违约本金、年化当期违约率、贷款修改占比 | |

---

## 1. 数据源

| 用途 | 文件 | 位置 |
|---|---|---|
| 全部信托月度表现（主源） | `Trust_Performance_MMDDYYYY.xlsx`（2026-09 那期 948 KB） | 来源页 https://www.salliemae.com/investors/asset-backed-securities/ 上「SMB Private Education Loan ABS Trusts Static Pool Information and Monthly Performance」链接；当期为 `…/Reports/investors/october-2026/Trust_Performance_09302026.xlsx` |
| 每个信托的交割日池余额（池因子分母，一次性） | 各信托最新一份 `DistRptXX-X_YYYYMMDD.pdf`（Monthly Servicing Report）第 2 页 I.A「Pool Balance」行、「Settlement Date」列 | 信托子页 `https://www.salliemae.com/investors/asset-backed-securities/smb/<2014-a>/` |
| 不用 | `Monthly_Trust_Performance_Report_09302026.pdf`（xlsx 的图表版）、`CPR20261015.xlsx`、`abdist_20261026.xlsx`、`Smart_Option_..._Historical_Performance_Data_2026Q2.xlsx` | 同一来源页 |

- 来源页链接里的月份文件夹（`october-2026/`）与文件名日期每月变 —— `fetch/slm.py` 只从来源页解析链接
  （正则认 `Trust_Performance_MMDDYYYY.xlsx`，恰好一个，否则抛），不拼 URL。
- 网络：`curl_cffi(impersonate='chrome')`，没装就 urllib；2026-11-09 实测 urllib / 裸 curl 也都 200（站点不拦）。
- 每期 xlsx 原始字节经 `fetch/rawkeep.py` 存进 `cache/raw/slm/`（来源页只挂最新一期）。
- 文件结构：`Orig. Characteristics On BS`（24 个信托）/ `Off BS`（17 个）第 6 行是信托名；
  `Performance` 表 19 个指标块。**表头两种**：期数 1..n（池因子、债券余额比、OC、P&I 占比、任意还款占比、
  累计违约、累计回收、贷款修改 by Period）与月末日期（其余 11 块）。
- 范围：41 个 SMB Private Education Loan Trust（2014-A … 2026-C，字母连续无缺号）。来源页另列的
  2020-PT-A / 2020-PT-B（pass-through，各有自己的服务报告）与 2024-R1（repackaging）**不在**这份 xlsx 里，
  也不进本页合计。

### 1.1 「Confidential and proprietary」

- **xlsx 本身没有任何保密 / 版权声明**：把 xlsx 解包、全文检索 `confidential|proprietary|copyright|all rights reserved|not be reproduced`，
  只命中两处 `proprietary`，都是正文用语（「proprietary or vocational school」与表头「Proprietary/Vocational」）。
  文件的 Microsoft 信息保护标签（`docProps/custom.xml` 的 `MSIP_Label_…_Name`）是 **`Public`**。
- 声明只出现在同期的图表版 PDF（`Monthly_Trust_Performance_Report_09302026.pdf`）封面页脚，
  pdftotext 抽出的原文是错位的两段：「Confidential and / proprietary information.©. ©2026」与「2024 Sallie Mae Bank. All rights reserved.」。
- 页面只放由 xlsx 数值画的图与自算表，**不转载 PDF 原件、不嵌任何 PDF 内容**。

---

## 2. 第 k 期 ↔ 日历月（brief 第 1 步）

结论：**期数块的第 1 期 = 同一信托在日期块里的首个有值月；第 k 期 = 首月 + (k−1)。**
首月是首个收款期所在的月，**不是**交割月，不能从 Orig 表的 Closing Date 推。三条互相独立的证据：

1. **官方内证**：贷款修改在 xlsx 里出两遍 ——「…by Period」（期数表头）与「…by Date」（日期表头）。
   41 个信托逐个比，两块的有值序列逐格相同、个数相同（2026-09 那期；2026-08、2026-03 两期同样成立）。
   `fetch/slm.py::parse_workbook` 每期都现验这一条，不过就抛。
2. **子页标签**：每个信托子页上最早一份服务报告的标签月 = 日期块首月，41/41。
   例：2014-A 交割 2014-08-07、最早报告「August 2014」= 2014-08；2026-A 交割 2026-03-11、最早报告「April 2026」= 2026-04；
   2021-D 交割 2021-08-18、最早「September 2021」。
3. **金额闭合**：每个信托最新一份服务报告两列池余额（上月末、本月末）= 按上述映射取到的池因子 × 交割日池余额，
   41/41 差 < $0.01（`series/slm_trusts.csv` 的 `factor_x_init_diff_usd` 列，全部 0.0000）。

其他一致性（每期现验）：各日期块里每个信托的首末月逐块相同、有值格连续；期数块第 1..n 期连续且 n = 日期块月数；
未带 `*` 的信托末月 = 截止月（2026-09），带 `*` 的 2015-A 末月 2026-07、2015-C 末月 2026-08。

⚠ Orig 表的 Closing Date 有笔误：2020-A 印成 2019-02-12（早于它自己的统计截止日 2019-12-12），
服务报告的 Settlement Date 是 2020-02-12，首期 2020-03。

---

## 3. 池因子的分母 = 交割日池余额（不是 Orig 表的截止日池余额）

服务报告第 2 页 I.A 有三列：Settlement Date / 上月末 / 本月末。2026-A（2026-09 那份，`october-2026/DistRpt26-A_20261015.pdf`）：

| | 值 |
|---|---|
| Orig 表「Pool Balance」（统计截止日 2026-01-28） | $650,062,490.87 |
| 报告「Pool Balance」Settlement Date 03/11/2026 列 | $646,508,148.26 |
| 报告「Pool Balance」09/30/2026 列 | $617,085,189.40 |
| xlsx 池因子（2026-A 第 6 期） | 0.954489423003889 |
| 0.954489423003889 × 646,508,148.26 | 617,085,189.40 ✓ |
| 0.954489423003889 × 650,062,490.87 | 620,477,792（高估 0.55%） |

41 个信托的交割日池余额全部取自各自最新一份报告的 Settlement Date 列，落 `series/slm_trusts.csv`
（连同报告 URL、现验月份、现验池余额、差额）。Orig 表的截止日池余额 41 个全都比交割日高，高 0.24%（2025-A）到 2.31%（2020-A）（截止日到交割日之间有还款、剔除不合格贷款），**不能拿 Orig 表顶替**。

---

## 4. 每个比率的分母（2026-A 2026-09 逐项还原）

报告第 4 页「Loans by Borrower Status」（09/30/2026 列，Pool Balance 栏）：IN SCHOOL 285,587,303.47 / GRACE 115,231,743.46 /
DEFERMENT 28,926,250.05 / P&I CURRENT 162,754,402.57 / 30-59 6,444,886.77 / 60-89 3,809,704.37 / 90+ 2,759,029.91 /
FORBEARANCE 11,571,868.80 / TOTAL 617,085,189.40；P&I = 当期 + 三档逾期 = 175,768,023.62。
第 5 页：Gross Principal Realized Loss - Periodic 850,260.90；Loans in Modification 19,432,125.15。

| xlsx 块 | xlsx 值 | 按报告金额现算 | 分母 |
|---|---|---|---|
| Loans in P&I Repayment as % of Current Pool Balance | 0.284835913 | 175,768,023.62 ÷ 617,085,189.40 | 池余额 |
| Loans in Any Type of Repayment as % of Current Pool Balance | 0.651072798 | (386,969,700.18+7,445,041.66+4,297,724.18+3,054,914.68) ÷ 池余额（第 4 页 Repayment Status 表） | 池余额 |
| 30-59 Day Delinquencies as % of Loans in P&I Repayment | 0.036667004 | 6,444,886.77 ÷ 175,768,023.62 | P&I（不含 forbearance） |
| Forbearance as % of Loans in P&I Repayment and Forbearance | 0.061769379 | 11,571,868.80 ÷ (175,768,023.62 + 11,571,868.80) | P&I + forbearance |
| Deferment as % of Loans in P&I Repayment, Forbearance and Deferment | 0.133753022 | 28,926,250.05 ÷ (187,339,892.42 + 28,926,250.05) | P&I + forb + deferment |
| Annualized Periodic Defaults as % of Loans in P&I Repayment | 0.058048845 | 850,260.90 × 12 ÷ 175,768,023.62 | 当期末 P&I（报告脚注：Periodic as a % of Loans in Repayment (P&I) × 12） |
| Loan Modification as % of P&I Repayment | 0.110555519 | 19,432,125.15 ÷ 175,768,023.62 | P&I |

⚠ 报告「% of Loans in P&I Repay」那一栏的分母**含** forbearance（30-59 印的是 3.440% = 6,444,886.77 ÷ 187,339,892.42），
与 xlsx 标题明写的「Forbearance is not included」不同。本页只用 xlsx 的定义。

---

## 5. 自算公式与列（`series/slm.csv`，146 行，2014-08 → 2026-09）

对每个日历月 m、只对当月在报告的信托 i：

```
池余额_i   = 池因子_i × 交割日池余额_i
P&I_i      = P&I 占比_i × 池余额_i
Forb_i     = f_i × P&I_i ÷ (1 − f_i)                f = Forbearance 块
Defer_i    = d_i × (P&I_i + Forb_i) ÷ (1 − d_i)    d = Deferment 块
逾期X_i    = 逾期率X_i × P&I_i
违约_i     = 年化违约率_i × P&I_i ÷ 12
修改_i     = 修改占比_i × P&I_i
任意还款_i = 任意还款占比_i × 池余额_i
合计比率   = Σ分子 ÷ Σ分母；30+ 天 = (Σ30-59 + Σ60-89 + Σ90+) ÷ ΣP&I
发行后期数 = Σ(期数_i × 池余额_i) ÷ Σ池余额_i
```

| 列 | 单位 / 写盘精度 | 页面 |
|---|---|---|
| `n_trusts` | 个 | 不画图（页尾说明现算点名） |
| `pool_bal_usdbn` = `pool_bal_onbs_usdbn` + `pool_bal_offbs_usdbn` | $bn / 6 位 | mix：合计柱 + 表内 / 表外占比（底座逐月复算恒等式） |
| `pi_bal_usdbn` | $bn / 6 位 | 存量图 |
| `age_wavg_periods` | 月 / 2 位 | 存量图（专门交代账龄结构漂移） |
| `pi_share_pct`、`anyrepay_share_pct` | % / 4 位 | 同分母两线 |
| `forbearance_pct`、`deferment_pct` | % / 4 位 | 各一张 |
| `dq30_59_pct`、`dq60_89_pct`、`dq90p_pct` | % / 4 位 | 三线 |
| `dq30p_pct`、`ann_default_pct` | % / 4 位 | 头条（全历史折线 + 季节性） |
| `defaults_usdmn` | $mn / 3 位 | 柱 + 次轴单月同比 |
| `loan_mod_pct` | % / 4 位 | 一张 |

独立复算：`ref/slm_ref.py`（另写的一份解析与合计，交割日池余额直接从 41 份 PDF 现读）按写盘精度取整后与 `series/slm.csv` 146 行 × 17 列逐格相同；
`fetch/slm.py` 在空目录从头跑一遍（重下 41 份报告），产出的 `slm.csv` / `slm_trusts.csv` 与库内逐字节相同。

---

## 6. 回源核对（brief 第 2 条：7 个月份 × 15 列）

做法：取该月**全部**在报告信托的服务报告，第 2 页 I.A「Pool Balance」行（当月列）、第 4 页 III「Loans by Repayment Status」
与「Loans by Borrower Status」两表（当月列 Pool Balance 栏，逐行）、第 5 页「Gross Principal Realized Loss - Periodic」与
「Loans in Modification」两行，金额逐份相加，再按 §5 的分母算比率，与 `series/slm.csv` 在写盘精度上比。
2026-08 用的是各信托 2026-09 报告的「08/31/2026」列（2015-C 用它自己 2026-08 的报告）。
报告 URL 全表见文末附录。

两条限制，表里逐格标出：
- **2014-A**（Navient 子服务）的报告**没有 Borrower Status 表**、也没有「Loans in Modification」行，
  它的 P&I / 逾期 / forbearance / deferment / 修改五项只能用 xlsx 还原值补进加总（标「2014-A 该项取 xlsx」）；
  它的池余额、任意还款（Repayment Status 表）、当期违约照报告。
- **2017 年以前**的报告状态表只列本金（TOTAL = 本金合计，不等于池余额），xlsx 的比率是池余额口径，
  两者不可比（标「—」）。2018-06 起状态表 TOTAL = 池余额。

| 月份 | 信托数 | 池余额 / 表内 / 表外 | 当期违约本金 | P&I 余额与占比、任意还款、forb、defer、三档逾期、30+、年化违约 | 贷款修改 |
|---|---|---|---|---|---|
| 2014-08 | 1 | ✓ 0.378892 | ✓ 0.028 | 报告无（单一信托，比率全来自 xlsx） | — |
| 2016-03 | 4 | ✓ 2.476235 / 0.714180 / 1.762055 | ✓ 1.231 | —（本金口径，不可比） | — |
| 2018-06 | 10 | ✓ 5.576112 / 4.336108 / 1.240004 | ✓ 4.675 | ✓ 11 列全等 | 差 +0.0027pp |
| 2020-04 | 15 | ✓ 6.666758 / 5.832977 / 0.833781 | ✓ 4.674 | ✓ 11 列全等（forb 19.8212%，COVID 那一格） | 差 +0.0106pp |
| 2023-06 | 27 | ✓ 13.899901 / 5.705979 / 8.193922 | ✓ 28.494 | ✓ 11 列全等 | 差 +0.0066pp |
| 2026-08 | 40 | ✓ 19.996826 / 6.341818 / 13.655008 | ✓ 46.800 | ✓ 11 列全等 | ✓ 17.8837 |
| 2026-09 | 39 | ✓ 19.639056 / 6.242407 / 13.396650 | ✓ 44.817 | ✓ 11 列全等 | ✓ 18.6951 |

逐月逐列明细（CSV 值 / 报告加总现算值 / 判定）：

<details><summary>展开 7 个月 × 15 列</summary>

**2014-08（1 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 0.378892 | 0.378892 | ✓ 相等 |
| pool_bal_onbs_usdbn | 0.000000 | 0.000000 | ✓ 相等 |
| pool_bal_offbs_usdbn | 0.378892 | 0.378892 | ✓ 相等 |
| pi_bal_usdbn | 0.048280 | 0.048280 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| pi_share_pct | 12.7425 | 12.7425 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| anyrepay_share_pct | 62.8858 | 62.8858 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| deferment_pct | 11.5334 | 11.5334 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| forbearance_pct | 5.6240 | 5.6240 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| dq30_59_pct | 3.6438 | 3.6438 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| dq60_89_pct | 0.0000 | 0.0000 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| dq90p_pct | 0.0000 | 0.0000 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| dq30p_pct | 3.6438 | 3.6438 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| defaults_usdmn | 0.028 | 0.028 | ✓ 相等 |
| ann_default_pct | 0.6958 | 0.6958 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |
| loan_mod_pct | 0.0000 | 0.0000 | —（唯一信托 2014-A 该项只有 xlsx，不构成核对） |

**2016-03（4 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 2.476235 | 2.476235 | ✓ 相等 |
| pool_bal_onbs_usdbn | 0.714180 | 0.714180 | ✓ 相等 |
| pool_bal_offbs_usdbn | 1.762055 | 1.762055 | ✓ 相等 |
| pi_bal_usdbn | 0.971155 | 0.971155 | —（报告无池余额口径的状态表，不可比） |
| pi_share_pct | 39.2190 | 39.2190 | —（报告无池余额口径的状态表，不可比） |
| anyrepay_share_pct | 69.1606 | 69.1606 | —（报告无池余额口径的状态表，不可比） |
| deferment_pct | 12.2552 | 12.2552 | —（报告无池余额口径的状态表，不可比） |
| forbearance_pct | 7.0414 | 7.0414 | —（报告无池余额口径的状态表，不可比） |
| dq30_59_pct | 1.7799 | 1.7799 | —（报告无池余额口径的状态表，不可比） |
| dq60_89_pct | 1.2432 | 1.2432 | —（报告无池余额口径的状态表，不可比） |
| dq90p_pct | 0.8643 | 0.8643 | —（报告无池余额口径的状态表，不可比） |
| dq30p_pct | 3.8873 | 3.8873 | —（报告无池余额口径的状态表，不可比） |
| defaults_usdmn | 1.231 | 1.231 | ✓ 相等 |
| ann_default_pct | 1.5213 | 1.5213 | —（报告无池余额口径的状态表，不可比） |
| loan_mod_pct | 2.1830 | 2.1830 | —（报告无池余额口径的状态表，不可比） |

**2018-06（10 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 5.576112 | 5.576112 | ✓ 相等 |
| pool_bal_onbs_usdbn | 4.336108 | 4.336108 | ✓ 相等 |
| pool_bal_offbs_usdbn | 1.240004 | 1.240004 | ✓ 相等 |
| pi_bal_usdbn | 2.975590 | 2.975590 | ✓ 相等（2014-A 该项取 xlsx） |
| pi_share_pct | 53.3632 | 53.3632 | ✓ 相等（2014-A 该项取 xlsx） |
| anyrepay_share_pct | 74.9816 | 74.9816 | ✓ 相等 |
| deferment_pct | 12.8398 | 12.8398 | ✓ 相等（2014-A 该项取 xlsx） |
| forbearance_pct | 5.8690 | 5.8690 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30_59_pct | 1.9749 | 1.9749 | ✓ 相等（2014-A 该项取 xlsx） |
| dq60_89_pct | 1.0384 | 1.0384 | ✓ 相等（2014-A 该项取 xlsx） |
| dq90p_pct | 0.6559 | 0.6559 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30p_pct | 3.6693 | 3.6693 | ✓ 相等（2014-A 该项取 xlsx） |
| defaults_usdmn | 4.675 | 4.675 | ✓ 相等 |
| ann_default_pct | 1.8852 | 1.8852 | ✓ 相等（2014-A 该项取 xlsx） |
| loan_mod_pct | 7.7433 | 7.7406 | 差 +0.0027（2014-A 该项取 xlsx） |

**2020-04（15 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 6.666758 | 6.666758 | ✓ 相等 |
| pool_bal_onbs_usdbn | 5.832977 | 5.832977 | ✓ 相等 |
| pool_bal_offbs_usdbn | 0.833781 | 0.833781 | ✓ 相等 |
| pi_bal_usdbn | 3.413541 | 3.413541 | ✓ 相等（2014-A 该项取 xlsx） |
| pi_share_pct | 51.2024 | 51.2024 | ✓ 相等（2014-A 该项取 xlsx） |
| anyrepay_share_pct | 68.1836 | 68.1836 | ✓ 相等 |
| deferment_pct | 14.4890 | 14.4890 | ✓ 相等（2014-A 该项取 xlsx） |
| forbearance_pct | 19.8212 | 19.8212 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30_59_pct | 2.6180 | 2.6180 | ✓ 相等（2014-A 该项取 xlsx） |
| dq60_89_pct | 1.3282 | 1.3282 | ✓ 相等（2014-A 该项取 xlsx） |
| dq90p_pct | 0.7240 | 0.7240 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30p_pct | 4.6702 | 4.6702 | ✓ 相等（2014-A 该项取 xlsx） |
| defaults_usdmn | 4.674 | 4.674 | ✓ 相等 |
| ann_default_pct | 1.6433 | 1.6433 | ✓ 相等（2014-A 该项取 xlsx） |
| loan_mod_pct | 12.0298 | 12.0192 | 差 +0.0106（2014-A 该项取 xlsx） |

**2023-06（27 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 13.899901 | 13.899901 | ✓ 相等 |
| pool_bal_onbs_usdbn | 5.705979 | 5.705979 | ✓ 相等 |
| pool_bal_offbs_usdbn | 8.193922 | 8.193922 | ✓ 相等 |
| pi_bal_usdbn | 8.755152 | 8.755152 | ✓ 相等（2014-A 该项取 xlsx） |
| pi_share_pct | 62.9871 | 62.9871 | ✓ 相等（2014-A 该项取 xlsx） |
| anyrepay_share_pct | 80.6864 | 80.6864 | ✓ 相等 |
| deferment_pct | 12.2214 | 12.2214 | ✓ 相等（2014-A 该项取 xlsx） |
| forbearance_pct | 1.5249 | 1.5249 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30_59_pct | 2.9260 | 2.9260 | ✓ 相等（2014-A 该项取 xlsx） |
| dq60_89_pct | 1.4931 | 1.4931 | ✓ 相等（2014-A 该项取 xlsx） |
| dq90p_pct | 1.4062 | 1.4062 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30p_pct | 5.8253 | 5.8253 | ✓ 相等（2014-A 该项取 xlsx） |
| defaults_usdmn | 28.494 | 28.494 | ✓ 相等 |
| ann_default_pct | 3.9054 | 3.9054 | ✓ 相等（2014-A 该项取 xlsx） |
| loan_mod_pct | 7.5156 | 7.5090 | 差 +0.0066（2014-A 该项取 xlsx） |

**2026-08（40 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 19.996826 | 19.996826 | ✓ 相等 |
| pool_bal_onbs_usdbn | 6.341818 | 6.341818 | ✓ 相等 |
| pool_bal_offbs_usdbn | 13.655008 | 13.655008 | ✓ 相等 |
| pi_bal_usdbn | 12.440415 | 12.440415 | ✓ 相等（2014-A 该项取 xlsx） |
| pi_share_pct | 62.2119 | 62.2119 | ✓ 相等（2014-A 该项取 xlsx） |
| anyrepay_share_pct | 79.9607 | 79.9607 | ✓ 相等 |
| deferment_pct | 12.9164 | 12.9164 | ✓ 相等（2014-A 该项取 xlsx） |
| forbearance_pct | 2.8596 | 2.8596 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30_59_pct | 3.7580 | 3.7580 | ✓ 相等（2014-A 该项取 xlsx） |
| dq60_89_pct | 1.8888 | 1.8888 | ✓ 相等（2014-A 该项取 xlsx） |
| dq90p_pct | 1.4183 | 1.4183 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30p_pct | 7.0651 | 7.0651 | ✓ 相等（2014-A 该项取 xlsx） |
| defaults_usdmn | 46.800 | 46.800 | ✓ 相等 |
| ann_default_pct | 4.5143 | 4.5143 | ✓ 相等（2014-A 该项取 xlsx） |
| loan_mod_pct | 17.8837 | 17.8837 | ✓ 相等（2014-A 该项取 xlsx） |

**2026-09（39 个信托）**

| 列 | CSV | 报告加总现算 | 判定 |
|---|---|---|---|
| pool_bal_usdbn | 19.639056 | 19.639056 | ✓ 相等 |
| pool_bal_onbs_usdbn | 6.242407 | 6.242407 | ✓ 相等 |
| pool_bal_offbs_usdbn | 13.396650 | 13.396650 | ✓ 相等 |
| pi_bal_usdbn | 12.047605 | 12.047605 | ✓ 相等（2014-A 该项取 xlsx） |
| pi_share_pct | 61.3451 | 61.3451 | ✓ 相等（2014-A 该项取 xlsx） |
| anyrepay_share_pct | 79.4175 | 79.4175 | ✓ 相等 |
| deferment_pct | 13.5872 | 13.5872 | ✓ 相等（2014-A 该项取 xlsx） |
| forbearance_pct | 3.1740 | 3.1740 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30_59_pct | 3.7225 | 3.7225 | ✓ 相等（2014-A 该项取 xlsx） |
| dq60_89_pct | 1.8781 | 1.8781 | ✓ 相等（2014-A 该项取 xlsx） |
| dq90p_pct | 1.7163 | 1.7163 | ✓ 相等（2014-A 该项取 xlsx） |
| dq30p_pct | 7.3169 | 7.3169 | ✓ 相等（2014-A 该项取 xlsx） |
| defaults_usdmn | 44.817 | 44.817 | ✓ 相等 |
| ann_default_pct | 4.4640 | 4.4640 | ✓ 相等（2014-A 该项取 xlsx） |
| loan_mod_pct | 18.6951 | 18.6951 | ✓ 相等（2014-A 该项取 xlsx） |

</details>

逐信托层面：2020-04、2023-06、2026-08、2026-09 四个月，每个信托的池余额、P&I、任意还款、forbearance、deferment、
三档逾期、当期违约「报告原文 − xlsx 还原值」最大绝对差都是 **$0.00**（38–40 个信托 × 9 项）。

### 6.1 贷款修改：xlsx 与当年报告不完全一致（已知差异，页面照 xlsx）

2026-08 / 2026-09 逐分相等；2018-06 / 2020-04 / 2023-06 每个信托的「xlsx 修改占比 × P&I」都比当年报告的
「Loans in Modification」**高** $6k–$79k（相对约 0.1%；如 2020-04 的 2015-C：报告 $43,282,295.76 / 印 19.88%，
xlsx 还原 $43,325,157.63 / 19.9041%），合计层面高 0.003–0.011pp。方向一致、量级稳定，像是 xlsx 对历史月份的修改余额
用了与当年报告略有不同的口径（例如含不含当月新进修改的待资本化利息），官方没有说明。
两边都是官方数：页面照**当期 xlsx**（与本页其余各列同一来源、且与最新报告逐分相等），差异写在页尾说明与这里。

### 6.2 信托子页的标签会错

2015-C 子页标「April 2020」的链接指向 `DistRpt15-C_20200415.pdf`（与「March 2020」同一份，实为 3 月），4 月那份
`DistRpt15-C_20200515.pdf` 页上没挂（按同一命名直接取得到）。所以核对与 `fetch/slm.py` 的现验一律以报告第 I.A 节
自己的列头日期认月份，不信链接标签。

---

## 7. 不上页的指标与理由

- **CPR**（Total / Voluntary since-issued、Total / Voluntary CPR by Trust）：since-issued 是「自发行以来」的累计年化量，
  跨账龄不同的信托相加没有指称；by Trust 是季度。
- **累计违约 / 累计回收**：同上，自发行以来的累计量。
- **债券余额 / 超额抵押**：可用「池余额 ×（1 − OC%）」反推债券余额，但 OC 的债券口径不统一 ——
  2014-A 报告注明「Based on the Rated debt securities (Class A and Class B Bonds)」，不含 $42mn 的 C 级。
  反推的债券合计会少算一块大小不定的东西，误差不可控。
- **同账龄对比图**：`build/single.py` 只产出日历月横轴的图；按发行后第 k 期对齐的横截面图型（`bars_labeled` 等）
  引擎里有、底座不产出。为一张图把本页改成手写生成器不划算，本轮不做。页面用「池余额加权的发行后期数」一张存量图
  交代账龄结构。

---

## 8. 口径断点与读法

- **断点只画清仓赎回**：2015-A 末期 2026-07 → 2026-08 起退出；2015-C 末期 2026-08 → 2026-09 起退出
  （xlsx 信托名带 `*`，表尾脚注：Optional Purchase / clean-up call 后全部资产负债清偿，指标停在最后一期）。
  `fetch/slm.py` 每轮按 `*` 标记重写 `series/slm_breaks.csv`。
- **新信托加入不画断点**（每年 1–6 个，2021 年起每年 3–6 个），但它们是合计比率漂移的主因：新信托池子年轻、在校借款人多、P&I 占比低。
  例：2025-08 加入 2025-B / 2025-C（交割日合计 $2.4bn），池余额加权期数从 34.64 跳到 31.22、P&I 占比从 66.2% 掉到 61.4%。
- **表内 / 表外**按当期文件归属回溯（官方只给当前归属）；2025-09 / 2026-03 / 2026-08 / 2026-09 四期文件归属逐个相同。
- **2014-A** 由 Navient 子服务，212 天核销（其余 120 天），其 90+ 天逾期含 120–212 天段；2014-08..2015-04 合计只有它一家。
- **2014-08..2015-12** 合计只有 1–4 个信托，比率噪声大；页面窗口除开篇两张全历史折线外都从 2016-01 起。

---

## 9. 官方重述（实测）

拿同一 URL 规则探到的旧期文件（仅为核对；fetcher 不拼 URL）与 2026-09 那期逐格比：

| 旧期 | 比对格数 | 不同格 | 最大差 |
|---|---|---|---|
| 2026-08（`september-2026/Trust_Performance_08312026.xlsx`） | 每块 ~2,600 | 0 | — |
| 2026-03（`april-2026/Trust_Performance_03312026.xlsx`） | 每块 ~2,400 | 6（全是 2021-C 的 2026-03 那一格：P&I、任意还款、defer、forb、三档逾期） | 3.2e-06 |
| 2025-09（`october-2025/Trust_Performance_09302025.xlsx`） | 每块 ~2,200 | 2（2024-A 第 1 期累计违约 9.77e-06 → 0 等） | 9.8e-06 |

用 `fetch/slm.py` 的解析器把 2026-08 与 2026-03 两期整表重算，与库内 `slm.csv` 在写盘精度上 0 格不同。
2025-09 那期**没有贷款修改块**（块是后来加的），解析器按「缺块」抛 —— 对未来的文件这正是要的行为。
块标题也改过：2026-03 那期「年化当期违约」无括号后缀、贷款修改两块叫「Loan Modification Since Issuance」与
「… as a % of P&I Repayment」，所以解析器按标题开头认块、按表头类型分日期 / 期数。
重述处理：已入库的月份不覆盖，差超过写盘精度的记 `cache/slm/restatements.csv`（`monthly_run.report_restatement_logs()` 会点名）。

---

## 10. 发布节奏与闸门

xlsx 不自述发布日（只有数据截止日），不写 `series/source_dates.csv`。按同一命名探到的 13 期 HTTP Last-Modified：

| 数据月 | 文件夹 | Last-Modified (GMT) | 月末后第几天 |
|---|---|---|---|
| 2025-09 | october-2025 | 2025-10-24 17:41 | 24 |
| 2025-10 | november-2025 | 2025-11-13 14:11 | 13 |
| 2025-11 | december-2025 | 2025-12-08 21:29 | 8 |
| 2025-12 | january-2026 | 2026-01-13 14:43 | 13 |
| 2026-01 | february-2026 | 2026-02-27 16:02 | 27 |
| 2026-02 | march-2026 | 2026-03-19 20:39 | 19 |
| 2026-03 | april-2026 | 2026-04-08 20:46 | 8 |
| 2026-04 | may-2026 | 2026-05-12 21:05 | 12 |
| 2026-05 | june-2026 | 2026-06-11 13:44 | 11 |
| 2026-06 | july-2026 | 2026-07-13 14:27 | 13 |
| 2026-07 | august-2026 | 2026-08-13 14:22 | 13 |
| 2026-08 | september-2026 | 2026-09-14 16:43 | 14 |
| 2026-09 | october-2026 | 2026-10-13 14:37 | 13 |

中位第 13 天、最早第 8 天（2 次）、最晚第 27 天。2025-08 及更早按同一命名探不到。
⚠ Last-Modified 是资产最后一次被改的时间，重传过的期次会显得更晚（第 24 / 27 天两期可能就是），分不出来；
2026-09 那期 xlsx 自身 `docProps/core.xml` 的修改时间是 2026-10-07，比上传早 6 天。
各信托服务报告每月 15 日（撞休息日顺延）分发，与 xlsx 不是同一个发布动作。

⇒ `build/roster.py` `LAG['slm'] = (27, 27)`（红点要上界；季末月 2026-03 / 06 / 09 第 8 / 13 / 13 天，不另分档）；
`monthly_run.EARLY_BY['slm'] = (20, 20)` → 闸门第 7 天开，比实测最早再早一天（默认 27−5 = 第 22 天会让 13 期里 11 期迟到）。
代价是追平前每天一个来源页请求（约 100 KB）。

---

## 11. 交叉印证

同日另一会话（误 resume 出的本任务复制品，已停）独立摸出的几条与本文一致：期次 ↔ 日历月由日期块首月钉死、
池因子分母 = 交割日池余额（2026-A 650.06mn vs 646.51mn）、各比率分母、2015-A / 2015-C 的清仓赎回月份、
xlsx 上传日落在月末后第 8–27 天（它的探测记录与 §10 表逐期相同）。

---

## 12. 没解决的

- 贷款修改的历史值 xlsx 比当年报告高约 0.1%（§6.1），原因官方没说明。
- 表内 / 表外的历史归属只能按当期文件回溯（§8）。
- 发布日只有 Last-Modified 可依（§10），LAG 的 27 可能偏宽。
- 同账龄对比图没做（§7）。

---

## 附录：核对用到的服务报告 URL（当期列 = 报告自己那个月；上期列 = 下一个月报告里的上月末列）

- **2014-08**（1 份）：2014-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt14-A_20140915rev.pdf
- **2016-03**（4 份）：2014-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt14-A_20160415.pdf；2015-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-A_20160415.pdf；2015-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-B_20160415.pdf；2015-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-C_20160415.pdf
- **2018-06**（10 份）：2014-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt14-A_20180716.pdf；2015-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-A_20180716.pdf；2015-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-B_20180716.pdf；2015-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-C_20180716.pdf；2016-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt16-A_20180716.pdf；2016-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt16-B_20180716.pdf；2016-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt16-C_20180716.pdf；2017-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt17-A_20180716.pdf；2017-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt17-B_20180716.pdf；2018-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt18-A_20180716.pdf
- **2020-04**（15 份）：2014-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt14-A_20200515.pdf；2015-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-A_20200515.pdf；2015-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-B_20200515.pdf；2015-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt15-C_20200515.pdf；2016-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt16-A_20200515.pdf；2016-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt16-B_20200515.pdf；2016-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt16-C_20200515.pdf；2017-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt17-A_20200515.pdf；2017-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt17-B_20200515.pdf；2018-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt18-A_20200515.pdf；2018-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt18-B_20200515.pdf；2018-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt18-C_20200515.pdf；2019-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt19-A_20200515.pdf；2019-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt19-B_20200515.pdf；2020-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/DistRpt20-A_20200515.pdf
- **2023-06**（27 份）：2014-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt14-A_20230717.pdf；2015-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt15-A_20230717.pdf；2015-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt15-B_20230717.pdf；2015-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt15-C_20230717.pdf；2016-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt16-A_20230717.pdf；2016-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt16-B_20230717.pdf；2016-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt16-C_20230717.pdf；2017-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt17-A_20230717.pdf；2017-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt17-B_20230717.pdf；2018-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt18-A_20230717.pdf；2018-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt18-B_20230717.pdf；2018-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt18-C_20230717.pdf；2019-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt19-A_20230717.pdf；2019-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt19-B_20230717.pdf；2020-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt20-A_20230717.pdf；2020-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt20-B_20230717.pdf；2021-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt21-A_20230717.pdf；2021-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt21-B_20230717.pdf；2021-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt21-C_20230717.pdf；2021-D（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt21-D_20230717.pdf；2021-E（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt21-E_20230717.pdf；2022-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/nov-2023/DistRpt22-A_20230717.pdf；2022-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt22-B_20230717.pdf；2022-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt22-C_20230717.pdf；2022-D（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt22-D_20230717.pdf；2023-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt23-A_20230717.pdf；2023-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/july-2023/DistRpt23-B_20230717.pdf
- **2026-08**（40 份）：2014-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt14-A_20261015.pdf；2015-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt15-B_20261015.pdf；2015-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/september-2026/DistRpt15-C_20260915.pdf；2016-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt16-A_20261015.pdf；2016-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt16-B_20261015.pdf；2016-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt16-C_20261015.pdf；2017-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt17-A_20261015.pdf；2017-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt17-B_20261015.pdf；2018-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt18-A_20261015.pdf；2018-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt18-B_20261015.pdf；2018-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt18-C_20261015.pdf；2019-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt19-A_20261015.pdf；2019-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt19-B_20261015.pdf；2020-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt20-A_20261015.pdf；2020-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt20-B_20261015.pdf；2021-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-A_20261015.pdf；2021-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-B_20261015.pdf；2021-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-C_20261015.pdf；2021-D（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-D_20261015.pdf；2021-E（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-E_20261015.pdf；2022-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-A_20261015.pdf；2022-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-B_20261015.pdf；2022-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-C_20261015.pdf；2022-D（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-D_20261015.pdf；2023-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-A_20261015.pdf；2023-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-B_20261015.pdf；2023-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-C_20261015.pdf；2023-D（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-D_20261015.pdf；2024-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-A_20261015.pdf；2024-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-B_20261015.pdf；2024-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-C_20261015.pdf；2024-D（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-D_20261015.pdf；2024-E（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-E_20261015.pdf；2024-F（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-F_20261015.pdf；2025-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt25-A_20261015.pdf；2025-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt25-B_20261015.pdf；2025-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt25-C_20261015.pdf；2026-A（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt26-A_20261015.pdf；2026-B（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt26-B_20261015.pdf；2026-C（上期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt26-C_20261015.pdf
- **2026-09**（39 份）：2014-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt14-A_20261015.pdf；2015-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt15-B_20261015.pdf；2016-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt16-A_20261015.pdf；2016-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt16-B_20261015.pdf；2016-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt16-C_20261015.pdf；2017-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt17-A_20261015.pdf；2017-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt17-B_20261015.pdf；2018-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt18-A_20261015.pdf；2018-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt18-B_20261015.pdf；2018-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt18-C_20261015.pdf；2019-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt19-A_20261015.pdf；2019-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt19-B_20261015.pdf；2020-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt20-A_20261015.pdf；2020-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt20-B_20261015.pdf；2021-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-A_20261015.pdf；2021-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-B_20261015.pdf；2021-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-C_20261015.pdf；2021-D（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-D_20261015.pdf；2021-E（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt21-E_20261015.pdf；2022-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-A_20261015.pdf；2022-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-B_20261015.pdf；2022-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-C_20261015.pdf；2022-D（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt22-D_20261015.pdf；2023-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-A_20261015.pdf；2023-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-B_20261015.pdf；2023-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-C_20261015.pdf；2023-D（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt23-D_20261015.pdf；2024-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-A_20261015.pdf；2024-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-B_20261015.pdf；2024-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-C_20261015.pdf；2024-D（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-D_20261015.pdf；2024-E（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-E_20261015.pdf；2024-F（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt24-F_20261015.pdf；2025-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt25-A_20261015.pdf；2025-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt25-B_20261015.pdf；2025-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt25-C_20261015.pdf；2026-A（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt26-A_20261015.pdf；2026-B（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt26-B_20261015.pdf；2026-C（当期列）https://www.salliemae.com/content/dam/slm/writtencontent/Reports/investors/october-2026/DistRpt26-C_20261015.pdf
