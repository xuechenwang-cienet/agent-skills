---
name: tokenplan-enterprise-bailian
description: >
  阿里云百炼 Token Plan 组织用量分析：从控制台导出全量用量明细，反推每个模型/时段/token 类型的
  Credits 结算系数，按项目组汇总用量，预测下月消耗与席位结余，生成部门报告 + 各组独立 HTML 报告。
  触发场景：用户提到"百炼用量"、"Token Plan"、"Credits 系数"、"token 兑换率"、"部门用量报告"、
  "项目组用量"、"席位结余"、"下月采购建议"、"tokenplan 分析"、"bailian usage report"。
  也可作为定时任务（--non-interactive）每周生成当月报告。
---

# Token Plan 用量分析

把「百炼 Token Plan 控制台」的原始用量数据，变成可发给各组 owner 的报告。

```
抓数 → 分析 → 渲染   （一条命令，约 30 秒）
```

## 何时使用

- 要一份**部门级**的用量与成本报告（模型横向对比、组维度汇总、下月采购测算）
- 要**按项目组**拆分的报告（细化到人、含席位结余与采购建议）
- 要推导 **token ↔ Credits 的结算系数**（精确到整数，可验证）
- 需要**每周自动**生成当月报告（配合 `--non-interactive`）

## 依赖

| 依赖 | 版本 / 安装 | 用途 | 缺失时 |
|---|---|---|---|
| **bsk**（browser-skill CLI） | 已安装且在 PATH | 驱动浏览器取数 | s0 直接失败（退出码 3） |
| **Chrome + browser-skill 扩展** | 已连接、**已登录百炼控制台** | 提供登录态 | s0 直接失败 |
| **Python** | ≥ 3.11 | 全流程 | s0 失败 |
| **PyYAML** | `uv pip install pyyaml` | 读 config | s0 失败 |
| **openpyxl** | 可选，`uv pip install openpyxl` | 生成系数 xlsx、导入名册 | 仅跳过 xlsx，流程继续 |
| 网络 | 控制台 + 阿里云 OSS | 取数与下载 | 重试后退出码 4 |

**不保存任何凭据**：登录态留在浏览器里，配置文件中没有 token / cookie / 密码。

## 快速开始

```bash
cd tokenplan-enterprise-bailian

# 0) 首次：从 sample 复制出真实配置（这两个文件不入库）
cp config/config.sample.yaml config/config.yaml
cp config/members.sample.csv config/members.csv

# 1) 首次：交互确认四项配置后跑当月
python3 scripts/run.py

# 2) 之后：配置在有效期内，可直接后台运行
python3 scripts/run.py --non-interactive

# 3) 回补历史月份
python3 scripts/run.py --month 2026-09

# 4) 已有原始数据，只重算 + 重渲染
python3 scripts/run.py --from s3

# 5) 同一天跑第二次，加后缀区分
python3 scripts/run.py --tag evening
```

产物落在 `output/<启动日期>/`。

## 流程

| 步骤 | 脚本 | 做什么 | 产物 |
|---|---|---|---|
| s0 | `steps/s0_preflight.py` | 依赖检查、四项确认校验、名册/日历一致性 | 控制台摘要 |
| s1 | `steps/s1_usage.py` | 打开用量页、捕获 `sec_token`、提交导出任务、轮询、下载 | `raw/usage_detail.csv` |
| s2 | `steps/s2_subscription.py` | 调订阅接口取席位/加油包 | `raw/subscription.json` |
| s3 | `steps/s3_analyze.py` | 系数、逐人、分组、模型、预测、结余、采购 | `data/analysis.json` |
| s4 | `steps/s4_render.py` | 部门报告 + 各组报告 + 系数表 + 收件人清单 | `*.html` `*.xlsx` `recipients.csv` |
| s5 | `steps/s5_manifest.py` | 10 项自检 + 清单 | `manifest.json` |

每一步都可单独重跑，`--from s3` 跳过抓数。

## 配置（`config/`）

| 文件 | 内容 |
|---|---|
| `config.yaml` | Web root / Org ID、导出参数、**价格**、预测参数、输出策略、TTL（**不入库**，由 sample 复制） |
| `members.csv` | 名册：姓名、邮箱、部门、P-code、**组长**、席位类型与额度、**共享人**、Bailian 账号（显示名 + acc_id）（**不入库**，由 sample 复制） |
| `holidays.yaml` | 法定节假日 + 调休工作日 + `verified_months` |
| `config.sample.yaml` / `members.sample.csv` | 模板，随仓库发布 |
| `state.json` | 四项确认的时间戳与内容哈希（自动生成，不入库） |

### 四项确认与后台模式

| 项 | 失效期 | 失效条件 |
|---|---|---|
| Web root / Org ID | 365 天 | 改 URL 或 org_id |
| 人员名册 | 30 天 | 改了 `members.csv` |
| 价格表 | 90 天 | 改了 `pricing` 段 |
| 节假日 / 工作日 | 365 天 | 改了 `holidays.yaml` |

- **交互模式**：缺项时逐项打印摘要并询问 `[Y/n]`，确认后写入 `state.json`
- **后台模式 `--non-interactive`**：四项都有效才继续，否则**退出码 2** 并打印缺什么
- 文件内容哈希一变，对应确认立即失效（与天数无关）

### 名册里的特殊字段

```csv
# 一个人对应两个 Bailian 账号：用 ; 分隔，两个都要写
bailian_accounts:     高军辉;Gao_Junhui
bailian_account_ids:  acc_9e8e...;acc_901b...

# 两人共享一个席位：额度按整席算，报告里显示两个人的名字
sharing_with:         Zhang_Han

# 没有 Bailian 账号的席位：active=true 但 accounts 为空，会显示「未开通」
```

> 运行时**只按 `bailian_account_ids` 匹配**，不猜名字。名册缺 ids 时会退化为按显示名匹配并告警。

### 节假日

`holidays.yaml` 用 `verified_months` 标记已核对过的月份。目标月份未核对时：
- 交互模式：列入确认项
- 后台模式：退出码 2

每年 11 月国务院公布次年安排后，更新本文件并把新月份加进 `verified_months`。

## 输出

```
output/2026-10-20/
├── raw/usage_detail.csv           全量明细（几分钟到十几 MB）
├── raw/subscription.json          订阅/席位/加油包快照
├── data/analysis.json             结构化分析结果（可单独消费）
├── token_credits_report.html      部门报告
├── team-<组长>.html               每个项目组一份
├── token_credits_coefficients.xlsx / .md
├── recipients.csv                 收件人清单（group/owner/name/email/role/report）
├── manifest.json                  清单 + 自检结果
└── logs/2026-10-20.log
```

`recipients.csv` 里 owner 行 `send_dept=true`（附部门报告），member 行只附本组报告——可直接做邮件合并。

## 退出码

| 码 | 含义 | 排查 |
|---|---|---|
| 0 | 成功 | — |
| 2 | 配置需确认（缺失/过期/哈希变化） | 跑一次交互模式确认，或更新配置 |
| 3 | 浏览器或登录态异常 | `bsk status`；确认扩展绿色、已登录控制台 |
| 4 | 数据异常（行数不符/系数非整数/分组对不上） | 看 `manifest.json` 的 `checks` |
| 5 | 渲染失败 | 看 `logs/*.log` |

## 数据获取原理

1. **导出接口**：`POST /data/api.json?action=UacSubmitUsageExportTask`
   - `params` = `{TimeGranularity, StartDate, EndDate, Locale}`
   - **不带 AccountId ⇒ 导出整个组织**
   - 返回 `TaskId` → 轮询 `UacGetUsageExportTask` → 得到 OSS 预签名 `FileUrl`
   - `FileUrl` 用普通 HTTP 下载即可，**不需要 cookie**，也不触发保存对话框
2. **`sec_token`**：不在 cookie / localStorage / 全局变量里，是前端请求层拼进 POST body 的。
   在页面里 hook `XMLHttpRequest.prototype.send`，触发一次粒度切换即可捕获。
3. **订阅页**：「用量统计」↔「订阅概览」是 SPA 路由，hook 不丢，一次 hook 即可抓到
   `QuerySubscription` / `QuerySubscriptionPackInfo` / `UacGetOrgMemberStatsWithSeat` 的参数并直接调用。
4. **导出上限**：接口单次最多 **100,000 行**，超出会返回
   `Status=FAILED / 导出数据量超过限制（N > 100000）`。
   脚本会自动**按日期二分递归**，直到每段都在限制内，最后合并并按整行去重
   （合并时打印每段的条数，例如 `52,506 + 55,512 → 107,794`）。
5. **兜底**：捕获不到 token 时先重试触发，仍失败则退出码 3 并在日志写明卡点。

## 自检（s5）

每次运行都会验，任一必需项失败 → 退出码 4：

1. 系数全部为整数
2. 系数组合无重复行（`(模型, 档位, 时段)` 唯一）
3. 各组点数之和 = 部门总点数
4. 所有席位都归属某个组
5. Bailian 账号全部映射到名册（**警告级**，未映射的单独列「未归属」）
6. 席位容量与订阅快照一致
7. 目标月份 / 下月日历已核对（**警告级**）
8. 所有报告文件已生成
9. 组报告数量 = 项目组数

## 故障排查

| 现象 | 处理 |
|---|---|
| `未能捕获 sec_token` | 页面可能停在登录页；`bsk status` 后重试，或手动打开控制台再跑 |
| 导出记录数为 0 | 当月刚开始，数据还没产生；换 `--month 上月` |
| 日志出现「超出上限，二分」 | 正常现象：单月明细超过 10 万行，已自动分段导出并合并 |
| `未能捕获 sec_token` 且页面停在 `/login` | 登录态失效（Chrome 重启常见），需在该标签页重新登录后再跑 |
| 系数不是整数 | 数据里出现了新的计费口径，检查 `manifest.json` 的 `unmapped` 与 `rates` |
| 组报告缺人 | 名册里没有该 Bailian 账号；查 `manifest.json.unmapped` |
| 席位容量对不上 | 名册的 `seat_credits` 与订阅不一致，更新 `members.csv` |

## 已知边界

- 平峰系数目前只有 `deepseek-v4.1-flash` 有真实数据；其余模型不按×0.5 推断
- 上下文分档只报告本月实际出现过的档位
- 采购测算是**单月口径**，未考虑跨月加油包结转到更远的月份
- 报告里的「折算 ¥」是用于横向比较的成本口径，**不等于财务账单分摊**