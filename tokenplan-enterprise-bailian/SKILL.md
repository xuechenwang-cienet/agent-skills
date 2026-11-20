---
name: tokenplan-enterprise-bailian
description: >
  阿里云百炼 Token Plan 组织用量分析：从控制台导出全量用量明细，反推每个模型/时段/token 类型的
  Credits 结算系数，按项目组汇总用量，预测下月消耗与席位结余。以成员管理页的席位分配为统计口径：
  未分配席位的成员不计入统计（仅管理版列名单），席位额度取控制台本周期实际额度。报告按角色分层：
  基础版（系数口径，所有人）、管理版（组/人/成本，限老板）、组报告（限组长）、个人画像（人手一份）。
  数据来源分两类控制台——企业版组织门户与个人控制台，运行前必须先问客户收集哪个（当前仅实现企业版）。
  触发场景：用户提到"百炼用量"、"Token Plan"、"Credits 系数"、"token 兑换率"、"部门用量报告"、
  "项目组用量"、"席位结余"、"席位分配"、"剩余未分配席位"、"下月采购建议"、"个人用量画像"、
  "员工使用统计"、"报告权限分层"、"tokenplan 分析"、"bailian usage report"、"企业版控制台"、
  "个人版控制台"。也可作为定时任务（--non-interactive）每周生成当月报告。
---

# Token Plan 用量分析

把「百炼 Token Plan 控制台」的原始用量数据，变成可发给各组 owner 的报告。

```
抓数 → 分析 → 渲染   （一条命令，约 30 秒）
```

## 数据来源：先问客户收集哪个控制台

百炼的管理页面有两类，数据不互通，**采集流程也完全不同**。运行前必须先问清楚：

| 类型 | 入口 URL | 状态 |
|---|---|---|
| 企业版组织门户 | `https://tokenplan-enterprise.bailian.aliyunportal.com` | ✅ 已实现（本 skill 全部能力） |
| 个人控制台 | `https://bailian.console.aliyun.com` | ⛔ 尚未支持 |

- **企业版**：管理员为组织成员购买席位，可导出整个组织的用量明细、席位与加油包——本 skill 的全部报告（组/人/行为画像）都基于它
- **个人版**：账号各自登录个人控制台，用量口径是单账号的，采集接口与组织版不同；在确认个人版的采集模型（单账号还是多成员各自账号的聚合）之前不做实现

**落地方式（三层保障）**：
1. **对话里先问**：agent 在运行前先问客户「收集企业版还是个人版控制台」，答案写入 `config/config.yaml` 的 `web.console_type`
2. **s0 预检兜底**：`console_type: personal` 时直接打印不支持提示并停止（退出码 2），不做任何后续检查
3. **确认机制**：「数据来源控制台」是五项确认之一，首次交互运行会给出两个 URL 让选择 `[1/2]`，确认后记录到 `state.json`；`--non-interactive` 模式只认已确认的配置

## 何时使用

- 要一份**部门级**的用量与成本报告（模型横向对比、组维度汇总、下月采购测算）
- 要**按项目组**拆分的报告（细化到人、含席位结余与采购建议）
- 要**每个人**的使用画像（偏好哪个模型及占比、几点在用、活跃天数与时长、夜间/周末占比、给 ta 的建议）
- 要推导 **token ↔ Credits 的结算系数**（精确到整数，可验证）
- 需要**每周自动**生成当月报告（配合 `--non-interactive`）

## 依赖

| 依赖 | 版本 / 安装 | 用途 | 缺失时 |
|---|---|---|---|
| **bsk**（browser-skill CLI） | 已安装且在 PATH | 驱动浏览器取数 | s0 直接失败（退出码 3） |
| **Chrome + browser-skill 扩展** | 已连接、**已登录企业版组织门户** | 提供登录态 | s0 直接失败 |
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

# 1) 首次：交互确认五项配置后跑当月
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
| s0 | `steps/s0_preflight.py` | 依赖检查、数据来源判定、五项确认校验、名册/日历一致性 | 控制台摘要 |
| s1 | `steps/s1_usage.py` | 打开用量页、捕获 `sec_token`、提交导出任务、轮询、下载 | `raw/usage_detail.csv` |
| s2 | `steps/s2_subscription.py` | 调订阅接口取席位/加油包；抓成员管理页的席位分配 | `raw/subscription.json` `raw/organization_members.json` |
| s3 | `steps/s3_analyze.py` | 系数、逐人、分组、模型、预测、结余、采购（按席位分配过滤） | `data/analysis.json` |
| s4 | `steps/s4_render.py` | 部门报告 + 各组报告 + 个人画像报告 + 系数表 + 收件人清单 | `*.html` `*.xlsx` `recipients.csv` |
| s5 | `steps/s5_manifest.py` | 自检 + 清单 | `manifest.json` |

每一步都可单独重跑，`--from s3` 跳过抓数。

## 配置（`config/`）

| 文件 | 内容 |
|---|---|
| `config.yaml` | **数据来源控制台（`console_type`）**、Web root / Org ID、导出参数、**价格**、预测参数、**统计口径（`stats`）**、输出策略（含 `member_reports`）、行为口径 `behavior`（可选）、TTL（**不入库**，由 sample 复制） |
| `members.csv` | 名册：姓名、邮箱、部门、P-code、**组长**、席位类型与额度、**共享人**、Bailian 账号（显示名 + acc_id）（**不入库**，由 sample 复制） |
| `holidays.yaml` | 法定节假日 + 调休工作日 + `verified_months` |
| `config.sample.yaml` / `members.sample.csv` | 模板，随仓库发布 |
| `state.json` | 五项确认的时间戳与内容哈希（自动生成，不入库） |

### 五项确认与后台模式

| 项 | 失效期 | 失效条件 |
|---|---|---|
| 数据来源控制台 | 365 天 | 改了 `web.console_type` |
| Web root / Org ID | 365 天 | 改 URL 或 org_id |
| 人员名册 | 30 天 | 改了 `members.csv` |
| 价格表 | 90 天 | 改了 `pricing` 段 |
| 节假日 / 工作日 | 365 天 | 改了 `holidays.yaml` |

- **交互模式**：缺项时逐项打印摘要并询问；「数据来源控制台」单独给两个 URL 选 `[1/2]`（选个人版会提示尚未支持并停止）
- **后台模式 `--non-interactive`**：五项都有效才继续，否则**退出码 2** 并打印缺什么
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

### 席位分配口径（成员管理页）

s2 会抓成员管理页（`/organization/members/list`）的 `UacListOrgMembersWithSeat` 接口
（分页拉全组织成员），落盘 `raw/organization_members.json`，s3 按它过滤统计：

- **未分配席位的成员不计入任何统计**（组汇总、行为、结余、采购测算），不产个人报告、
  不进 `recipients.csv`，仅在管理版订阅节列名单。开关 `stats.exclude_unseated_members`（默认 true）
- **「有席位」以接口的 `SeatId`/`SpecType` 为准**——成员可能有历史 API Key 但席位已被回收，不能当依据
- **席位额度 = 控制台本周期实际额度**（`CycleTotalValue`，按席位分配日折算，与订阅页
  「剩 X / 共 Y」一致），名册 `seat_credits` 仅在缺接口数据时兜底。月中新分配的席位额度是折算值
- 控制台有席位但名册未映射的账号 → s5 警告 + 管理版披露（需补名册或修账号映射）
- 成员与席位的匹配：账号 id 精确匹配优先，名册缺 id 时按显示名兜底；导入名册时可用
  `import_roster.py --members-json` 自动补全账号映射

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
├── raw/organization_members.json  组织成员与席位分配快照（103 人/35 席位级明细）
├── data/analysis.json             结构化分析结果（可单独消费）
├── token_credits_report.html      基础版：系数与计费口径（所有人可阅）
├── management_report.html         管理版：组/人/成本管理节（仅部门老板）
├── team-<组长>.html               每个项目组一份（限本组负责人）
├── member-<姓名>.html             每人一份行为画像报告（发本人为裁剪版）
├── token_credits_coefficients.xlsx / .md
├── recipients.csv                 分发清单（含角色与各报告列）
├── manifest.json                  清单 + 自检结果
└── logs/2026-10-20.log
```

## 权限分层

报告按受众分三层，权限边界即文件边界（每份文件只含该角色该看的数据）：

| 内容 | member（所有人） | owner（组长） | boss（部门老板） |
|---|---|---|---|
| 基础版：系数总表、高峰/平峰、三种 cache、上下文分档、原始类型 | ✓ | ✓ | ✓ |
| 自己的画像 member-*.html | ✓ 仅自己 | ✓ | ✓ |
| 组报告 team-*.html（成员明细/作息对比/采购结余） | ✗ | ✓ 仅本组 | ✓ |
| 管理版 management_report.html（组总览/人员行为/矩阵/订阅/结余/诊断） | ✗ | ✗ | ✓ |

- **基础版**不含任何组名、人名与金额；s5 自检会扫描管理节哨兵防泄漏
- **个人画像**发本人为裁剪版：相似同事匿名化（姓名仅管理者可见），无组报告链接
- 管理版收件人在 `notify.boss_recipients` 配置（邮箱或 {name, email}），以 role=boss 写入 recipients.csv
- 将来上线按登录身份传 role 即可复用同一套渲染代码做访问控制

成员身份 key 的回退链：**中文名 > 钉联名（bailian_accounts 首项）> 邮箱前缀 > hrid > 英文名**；
撞名自动加 `-2` 后缀并在 manifest 打 warning。`hrid` 仅作最后兜底，不参与文件名逻辑
（名册里 hrid 可能是错数据，无需修正即可正常出报告）。

`recipients.csv` 按行列出每人该收的文件：`basic_report`（所有人）、`report`（owner 行 = 本组报告）、
`member_report`（本人画像）、`mgmt_report`（仅 boss 行）——可直接做邮件合并。
个人报告默认开启（`output.member_reports: true`），未开通账号的席位自动跳过。

## 行为画像口径

个人报告与「人员行为总览」全部由**分钟级计费桶**推断：某分钟有调用发生即计为「活跃」，
**不等同于考勤**；所有占比基于完整日（数据不完整的最后一天自动剔除，避免早晚占比被半天数据拉偏）。

| 指标 | 定义 |
|---|---|
| 活跃分钟 | 有调用的去重分钟数（同一分钟多个模型/类型只算 1） |
| 会话 | 相邻活跃分钟间隔 ≤ `behavior.session_gap_min`（默认 15）算同一段 |
| 典型作息 | 全月每日首次/末次活跃时刻的**中位数**；跨度 = 末次 − 首次 + 1 分钟 |
| 夜间 / 晚间 / 核心 | 点数落在 22:00–07:59 / 18:00–21:59 / 09:00–17:59 的占比（时段可在 `behavior` 段改） |
| 模式标签 | 单标签规则，按序命中：轻量偶发（活跃 ≤3 天或 < 组均 5%）→ 夜间型（夜间 ≥25%）→ 早晚型 → 白天型（核心 ≥70%）→ 集中攻坚（活跃天数 ≤ 部门中位一半且单日集中度 ≥25%）→ 持续稳定（活跃 ≥85% 工作日样本且峰值 <20%）→ 混合型 |
| 分位 | 与部门内有用量的人比较的百分位（P50=中位），刻意不做排行榜 |
| 相似同事 | 组内模型结构向量的余弦相似度 Top3 |
| 混合单价 | 点数 ÷ tokens × 1e6，衡量选型贵贱（与模型选择强相关，与效率弱相关） |

`behavior:` 配置段可选（`night` / `core` / `session_gap_min`），**不参与确认哈希**，改动不触发重新确认。

## 退出码

| 码 | 含义 | 排查 |
|---|---|---|
| 0 | 成功 | — |
| 2 | 配置需确认（缺失/过期/哈希变化），或数据来源选了尚未支持的个人控制台 | 跑一次交互模式确认，或把 `web.console_type` 改回 `enterprise` |
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
4. **成员管理页**：`UacListOrgMembersWithSeat`（`{OrgId, Locale, PageNum, PageSize}`，分页拉全）。
   行字段：`AccountId` / `AccountName` / `Roles`；已分配席位的行另有 `SeatId` / `SpecType`
   （standard｜pro）/ `SubscriptionInfo.EquityList[0].CycleSurplusValue|CycleTotalValue`
   （该席位本周期剩余/总额度）。页面顶部「剩余未分配席位」= 订阅席位总数 − 已分配。
   注意**不能用 unwrap**（`data.Data` 就是成员列表，会把 `Total` 层剥掉）。
5. **导出上限**：接口单次最多 **100,000 行**，超出会返回
   `Status=FAILED / 导出数据量超过限制（N > 100000）`。
   脚本会自动**按日期二分递归**，直到每段都在限制内，最后合并并按整行去重
   （合并时打印每段的条数，例如 `52,506 + 55,512 → 107,794`）。
6. **兜底**：捕获不到 token 时先重试触发，仍失败则退出码 3 并在日志写明卡点。

## 自检（s5）

每次运行都会验，任一必需项失败 → 退出码 4：

1. 系数全部为整数
2. 系数组合无重复行（`(模型, 档位, 时段)` 唯一）
3. 各组点数之和 = 部门总点数
4. 所有已计入统计的席位都归属某个组
5. Bailian 账号全部映射到名册（**警告级**，未映射的单独列「未归属」）
6. 控制台已分配席位的账号全部映射到名册（**警告级**，含零用量的席位账号）
7. 席位容量与订阅一致（额度口径 = 控制台本周期额度之和，缺数据时回退名册额度）
8. 目标月份 / 下月日历已核对（**警告级**）
9. 所有报告文件已生成
10. 组报告数量 = 项目组数
11. 个人报告数量 = 有账号席位数（**警告级**，`member_reports` 关闭时跳过）
12. 行为分布（24h / 逐日）合计 = 部门总点数（**警告级**）
13. `peak`/`offpeak` 后缀与时间戳小时一致率 ≥98%（**警告级**，异常说明导出时区或时段口径变了，作息图不可信）
14. 基础版报告不含管理内容（**警告级**，扫描管理节哨兵 + 未分配席位成员名字，防权限泄漏）

## 故障排查

| 现象 | 处理 |
|---|---|
| `未能捕获 sec_token` | 页面可能停在登录页；`bsk status` 后重试，或手动打开控制台再跑 |
| 导出记录数为 0 | 当月刚开始，数据还没产生；换 `--month 上月` |
| 日志出现「超出上限，二分」 | 正常现象：单月明细超过 10 万行，已自动分段导出并合并 |
| `未能捕获 sec_token` 且页面停在 `/login` | 登录态失效（Chrome 重启常见），需在该标签页重新登录后再跑 |
| 系数不是整数 | 数据里出现了新的计费口径，检查 `manifest.json` 的 `unmapped` 与 `rates` |
| 组报告缺人 | 名册里没有该 Bailian 账号，或该成员**未分配席位**被过滤；查 `manifest.json.seat_filter` 与 `excluded_members` |
| 席位容量对不上 | 优先看是不是席位分配口径差异：某成员没被分配席位（`raw/organization_members.json`）却保留了名册额度；确认成员管理页后再改 `members.csv` |
| 控制台席位账号未映射 | 名册缺该成员或账号映射缺失；用 `import_roster.py --members-json` 补全 |

## 已知边界

- 平峰系数目前只有 `deepseek-v4.1-flash` 有真实数据；其余模型不按×0.5 推断
- 上下文分档只报告本月实际出现过的档位
- 采购测算是**单月口径**，未考虑跨月加油包结转到更远的月份
- 报告里的「折算 ¥」是用于横向比较的成本口径，**不等于财务账单分摊**
- 作息与活跃时长是**计费桶推断**：反映「何时有调用」，受批处理任务影响大，不能当考勤或绩效依据
- 明细导出若换成非 MINUTE 粒度（HOUR/DAY），活跃分钟与会话指标会失真，需同步调大 `session_gap_min`
- 未分配席位的成员**完全不在统计里**：若某人月中被回收席位但月初有用量，其用量只以
  「未计入统计」口径披露在管理版，不进组/人明细（避免额度口径混乱）
- 席位分配快照是 s2 运行时刻的状态：月中分配变动后需重跑 s2（`--from s2`）才会反映
- `--from s4` 读到旧版本 analysis.json（无画像字段）时会自动用同目录明细重跑 s3