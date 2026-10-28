# CHANGELOG

`npx skills update` 会整体覆盖安装目录，本文件用于说明每个版本改了什么。

版本号按技能独立演进；标题未标技能名的条目属于 `long-task-session`（早期所有条目都是它）。

## doc-review 0.1.0 — 2026-10-27

新增 [`doc-review`](./doc-review/)：通用文档评审与受控修订技能。方法论为主、工具为辅，不针对特定文档
（文档族差异通过 `review-config.md` 注入，结构语义判断由评审者按标准执行）。

- **流程**：六阶段五闸门（基线快照 → 初审 → 独立复核 → 人工决策 → 受控修复 → diff 审计），
  两轮封顶；闸门可用 `gate_artifacts.py` 可执行校验。
- **角色职责**：六份职责书（协调者 / 初审评审 / 复核评估 / 决策者（人）/ 修复执行 / 终审审计）——
  评审只读、复核只标注不重写、执行照单（不符即停）、治理决策必须问人。
- **评审标准**：12 维（结构 / 声明 / 引用 / 事实 / 一致性 / 覆盖 / 语义 / 治理 / 交付 / 回归），
  固定"机械→语义→治理"顺序；P0–P3 + 决策点分级；声明登记表与发现八字段的证据契约；
  19 条真实失败模式案例库。
- **通用工具**（8 个脚本，跨文档通用，不含文档特定判断）：链接核验（区分真 404 与反爬拦截）、
  快照与差异审计、docx/xlsx 只读盘点（含 ECMA-376 单元格-行引用一致性检查）、声明登记表初稿、
  阶段闸门、交付门禁、编辑工具残留清理。
- **校准**：4 个已知答案用例（换评审模型/提示词后必跑）。
- **验证记录**：GLM-5.3#high 校准 4/4 通过；4 个评测代理（with/without skill × 2 任务）对比，
  with-skill 在工件结构、声明登记、决策闸门上稳定占优；验证中发现的两类先例
  （整行移动后的单元格引用残留、批量"全部失效"链接声明未逐条实测）已沉淀进案例库。
- 离线自测 `doc-review/tests/selftest.sh`（11 项，PASS=11）。

## tokenplan-enterprise-bailian 0.3.0 — 2026-10-28

报告按受众分层，权限边界即文件边界。

- **部门报告拆分为两份**：
  - `token_credits_report.html`（基础版，所有人）：系数总表、高峰/平峰、三种 cache、上下文分档、
    原始类型、配套文件——不含任何组名、人名与金额
  - `management_report.html`（管理版，仅 boss）：部门组总览、人员行为总览（含个人报告索引）、
    模型横向、组×模型矩阵、订阅容量、席位结余、技术诊断与采购测算，每节带「限管理者」徽章
- **个人画像分角色渲染**：发本人为裁剪版（相似同事匿名化为「另有 N 位结构相近」、无组报告链接、
  页脚只挂基础版）；完整版供管理者使用
- **分发**：recipients.csv 列改为 `basic_report / report / mgmt_report / member_report`（替代
  `dept_report/send_dept`，邮件合并脚本需同步调整）；boss 行由 `notify.boss_recipients`
  配置生成（支持邮箱字符串或 {name, email}）
- **自检**：新增「基础版报告不含管理节」哨兵扫描（警告级）
- **顺带修复**：个人报告「选型降级」省钱估算把 token 数当单价用，数额虚高数个量级——改为
  `tokens × 单价差 / 1e6`，并验证所有人估算 ≤ 本人总消耗
- `render_dept.render(A, cfg, role)` 按节函数化组装（`basic`/`boss`），上线后按登录身份传
  role 即可复用为访问控制点；`config.sample.yaml` 新增 `output.management_report` 与
  `notify.boss_recipients`

## tokenplan-enterprise-bailian 0.2.1 — 2026-10-28

成员身份 key 改为「**中文名 > 钉联名 > 邮箱前缀 > hrid > 英文名**」回退链，撞名自动加 `-2` 后缀并告警。

- **动机**：名册 hrid 列混入错数据（如 `12434`），此前 `member-<hrid>.html` 的文件名与
  manifest 的 waste/upgrades 清单里出现无意义工号。现在全部显示中文姓名，名册无需修正。
- **实现**：`lib/model.py` 中 P 字典与 key_of 统一走全局解析的 key_map（撞名检测需要跨成员视野）；
  hrid 仅作最后兜底，`import_roster.py` 照常导入该列作参考。
- 重算重渲染：`--from s3 --tag names` 复用已有原始明细，不动配置确认；
  `run.py` 的 `--from s4` 在 analysis.json 缺失时也会自动从本地明细重跑 s3。

## tokenplan-enterprise-bailian 0.2.0 — 2026-10-28

新增**每成员行为画像**：模型偏好占比、作息热力图、使用节奏与个人建议。

- **个人报告** `member-<工号>.html`（每人一份，默认开启，`output.member_reports` 可关）：
  01 概览 / 02 模型偏好（占比条 + 混合单价 + 集中度）/ 03 工作时段（24h 点数 vs 活跃分钟双图、
  周内×24 热力图、核心/晚间/夜间/周末占比）/ 04 使用节奏（整月「日×小时」日历热力图、活跃天数、
  最长连击、峰值日、会话切分）/ 05 Token 效率 / 06 部门分位对比 + 组内模型结构相似同事 / 07 建议。
- **组报告**新增「成员作息与选型对比」：人×24h 热力图、人×模型占比矩阵、作息表，成员名可点进个人页。
- **部门报告**新增「人员行为总览」（第 07 节，后续章节顺延）：部门 24h 点数/在线人数曲线、
  夜间/周末/最活跃时段、活跃度分档、模式分布、主力模型人群聚类、分位阈值，以及可搜索的
  **个人报告索引**；部门级刻意只给分布与分位，不做个人排名。
- **数据层**（`lib/model.py`）：逐人采集小时/分钟/逐日/周内×小时/逐模型计数，派生画像
  （活跃分钟、会话、典型作息中位数、集中度、混合单价、模式标签、部门分位、相似同事）；
  新增 `behavior` 部门/组级行为汇总；`peak`/`offpeak` 后缀与时间戳小时一致性哨兵（s5 新自检）。
  老字段零改动——对 2026-10 真实数据逐字段比对，除名册变动外与 0.1.0 产物完全一致。
- **口径**：作息由分钟级计费桶推断（该分钟有调用即活跃，非考勤）；占比基于完整日，
  自动剔除不完整的最后一天；`behavior:` 配置段可选且不参与确认哈希。
- **配套**：`recipients.csv` 新增 `member_report` 列；xlsx 逐人 sheet 新增活跃天数/夜间%/典型时段/模式；
  `--from s4` 读到旧版 analysis.json 时自动用本地明细重跑 s3；
  组报告修复「auto」等仅按次计费模型导致的空档位崩溃（预先存在的边界 bug）。

## tokenplan-enterprise-bailian 0.1.0 — 2026-10-26

从 `cienet-ai/tokenplan-enterprise-bailian-skills` 导入为 `agent-skills` 的顶层技能目录，功能无改动。

- 新目录 `tokenplan-enterprise-bailian/`（24 个文件）：`SKILL.md` + 说明 + `config/*.sample.*` + `scripts/`
  （含 `lib/`、`steps/`、`tools/`）。
- 目录名由 `tokenplan-enterprise-bailian-skills` 改为 `tokenplan-enterprise-bailian`，与 frontmatter
  `name` 及仓库命名约定一致；`SKILL.md` / `README.md` 中 4 处路径引用同步更新。
- 只导入 git 跟踪文件：`config/config.yaml`、`config/members.csv`、`config/state.json`、`output/`、
  `logs/` 不进仓库（技能自带的 `.gitignore` 继续生效）。
## 0.1.7 — 2026-10-26

把"任务结束"这件事自动落进 `state.json`，并给终态标记加上"原文/正则"两种匹配模式。

- **`run --marker <str>` 自动收尾**：`run` 会在后台挂一个 detached 的收尾监视器，
  标记出现 → `state.runs[].state=done`（`close_reason=marker`）；进程消失但标记未出现 → `failed`
  （`close_reason=process_gone`）。此前 `run` 只管"生"不管"收"，命令跑完后记录永远停在 `running`，
  会误导 `status`/`resume` 的读者（实测：交接时 `wait_train` 就得手工 `stop-run --mark-only`）。
  `--no-autoclose` 保留旧行为；`--autoclose-interval` 调整轮询（默认 15s）。
- **终态标记的匹配模式分开**：
  - `watch --marker-fixed`：按原文 `grep -F` 匹配（默认仍是正则，兼容 `^batches:` 这类锚点）；
  - `observe` 的 `--marker`：**默认原文**，要正则加 `--marker-regex`。
  动机：`. [ ] ( )` 在正则里有含义。实测 marker 写 `done[0]` 时，正则模式把 `[0]` 当字符类，
  永远匹配不到字面行 → 闹钟不响、阶段挂到超时（自测 M1/M2 固化了这个对照）。
- 自测 96 → **101 条**：marker 两种模式对照（M1/M2）、`run --marker` 自动收尾（A1）、无 marker 保持 running（A2）。

## 0.1.6 — 2026-10-26

补齐"起/停"与"回溯"三个缺口，并把产物校验改成与 cwd 无关（跨会话接手必需）。

- **新增 `sessionctl run --stage <id> --cmd … --log …`**：`setsid` 起一条命令并把 `pid/cmd/log` 登记进
  `state.runs`。**新增 `sessionctl stop-run <id>`**：按登记的 pid 精确停（含进程组），
  避免 `pgrep -f … | xargs kill` 误杀执行者自己（本项目踩过两次）。
  `stop-run --mark-only --state stopped|failed|done|stale` 用于没有 pid 的旧登记（例如被宿主杀掉的 watcher）。
- **新增 `status --expect-stage S3|S4`**：这两期"验收表未判定"是预期状态，只允许第 4 项失败；
  匹配时打印 `status: EXPECTED 3/4` 且退出码 0，不再把"计划已冻结、阈值待测"误报成故障。
- **新增 `new --date YYYY-MM-DD`**：回溯/迁移历史会话时目录名用历史日期（配合已有的四份模板与 state）。
- **修复 `status`/`verify` 的 cwd 依赖**：相对产物路径现在依次按 `session/`、仓库根、`cwd/` 解析，
  在哪个目录执行结果都一样（此前换个目录就报"产物不存在"）。
- 自测 86 → **96 条**（仓库口径；安装副本 95 条，差一条为跳过的 README 检查）（run/stop-run、expect-stage、new --date 各一组）。

## 0.1.5 — 2026-10-26

补齐"agent 在环"模式（观察者唤醒 agent、由 agent 判读并决定推进或请示），修掉 pipeline 模板的两个真实 bug。

- **新增 `sessionctl observe`**：观察者"闹钟"。睡到 `marker` / `checkpoint`（默认 40 分钟）/ `stale` / `timeout`
  就退出并打印一行 `OBSERVE event=…`，**不判读、不写 state.json**；退出即把控制权交回 agent。
  退出码：0=marker、3=checkpoint、5=stale、2=timeout、4=自检失败。
  契约：agent 每次唤醒后先 `status`/`resume` 判读，再按 `next_action.decision` 推进或请示，**然后必须重新挂 observe**。
- **新增 `state.next_action.decision`**（`agent` | `user`）：`status`/`resume` 会打印
  `▶ 推进权：agent` 或 `⏸ 推进权在用户`；`decision=user` 时阶段完成后不自动进入下一阶段。
- **`references/delegation.md` 新增 §7「两种判读模式」**：无人值守（子代理判读）vs agent 在环（主 agent 判读），
  含选择规则与三条硬契约（重挂、观察者死亡是正常事件、执行体与观察者分离）。
- **`SKILL.md` 新增「一句话边界」**：明确 Pull（能接上）与 Push（会继续）是两套机制，并写死
  "自动执行到跑完并落盘为止，decision=user 的门仍等交互"。
- **修复 `templates/pipeline.sh` bug A**：阶段表用 `|` 分隔时，进度正则里的 `\|` 会把字段切碎
  （实测 `timeout: invalid time interval ' [0-9]+/[0-9]+ \\[|9000'`）。改为 **制表符分隔**，并在解析阶段对空字段快速失败。
- **修复 `templates/pipeline.sh` bug B**：`wait "$child" 2>/dev/null || true` 会吞掉阶段命令的退出码，
  导致"终态标记已出现但命令失败"的阶段被标 done。改为 `wait` 后检查 `rc`，非零即 `STATUS=fail`。
- 自测从 22 条扩到 **86 条**：新增 observe 的四种事件、写死总量被拒、`decision` 校验与 status 提示、pipeline 阶段表解析。

## 0.1.4 — 2026-10-26

文档修正：把"宿主的后台任务时限"从传闻改成实测事实。无代码改动、无 schema 改动。

- `references/long-running.md` 新增 §2.1「宿主限制与版本差异」：opencode ≤2.0.x 的
  **60 分钟空闲驱逐**（与运行时长无关，SIGTERM + 完成通知丢失，issue #51828）、
  ≥2.1.3 的修复（PR #57416 / `experimental.location_idle_timeout`）、以及
  "升级或重启宿主会杀全部托管后台 shell"这条跨版本规则；并说明 watcher 的
  "窗口 ≤2 小时"是可重挂性设计，不是宿主上限。
- `references/delegation.md` 兜底表补两行：宿主升级/重启、宿主空闲驱逐。
- 结论未变：`setsid` + 状态落盘 + 可重挂 watcher 仍是唯一稳妥做法。

## 0.1.3 — 2026-10-26

监视环节的"自证可用" + 上下文降载。向后兼容（不改 schema、既有会话无需迁移）。

- **`sessionctl watch`（新）**：包装 watcher 模板；启动前用两份夹具日志做**上岗自检**——
  正则必须能抓到与批次无关的 `| 5/207 [...]`，写死总量（如 `/172`）会直接拒绝启动（exit 4）
  并给出定向提示。`--selftest-only` 可单独跑（<10 秒）。
- **`templates/watcher.sh`**：新增失速检测 `STALE_LIMIT`（默认 3）→ 心跳追加
  `note=stale_progress`；`FAIL_ON_STALE=N` 达到阈值以**退出码 5** 结束；头注释明确
  "总步数/总量不要写死"。
- **`sessionctl status`**：心跳行新增"假推进体检"——声明了 `progress_regex` 但最近一次
  `progress=-` 时给出 ⚠ 提示。
- **`sessionctl ckpt --progress-regex`**：把进度正则记进 `runs[]`，供 status 体检。
- **`templates/pipeline.sh`（新）**：多阶段管道模板（幂等 done 标记、失败短路、单行通知契约）。
- **`references/delegation.md`（新）**：托管监控——等待交给管道、判读交给子代理、单行通知契约、
  子代理 prompt 模板与兜底规则。
- **patterns.md**：新增第 16 条"监视器写死总量"（按 16 条同步计数）；
  `long-running.md` / `SKILL.md` 补自检与失速规则。
- 自测：新增 W1–W4（自检通过 / 写死被拒 / 失速记录 / 退出码 5）→ 76 个检查点全绿。

## 0.1.2 — 2026-10-26

两处可用性改进，向后兼容（不改 schema、不改退出码语义）。

- 目录产物：`ckpt` 登记目录时直接打印可复制的打包 + 重新登记命令（含 session 与脚本绝对路径）；
  `status`/`verify` 的提示补上"建议打包后用 ckpt 登记归档文件，才能被校验"。
- `list`：默认首行打印 `root: <绝对路径>`（表格保持窄）；新增 `--paths`，只输出绝对路径、一行一个，
  便于 `$(sessionctl list --paths | tail -1)` 取最新会话。
- 文档：`references/documents.md` §4 补"目录产物规则"；`SKILL.md` 快速开始补 `list --paths`。
- 自测：30 组 → 32 组断言 / 71 个检查点（新增目录产物打包命令、list 输出两种模式）。

## 0.1.1 — 2026-10-26

修复实测发现的 4 个 bug + 7 处小问题，并补 5 条健壮性改动。向后兼容：不改 `state.json` schema、
不改命令面、无需迁移既有会话。

**Bug**
- B1 目录产物导致 `verify`/`status`/`resume` 崩（`IsADirectoryError`）：哈希前先判目录，
  目录在 `ARTIFACTS.md` 记为 `dir` 并输出"目录产物"提示；`sha256_file` 对目录显式报错。
- B2 `close --backup`（文档教的用法）因 argparse 必带值而报错：改为 `nargs="?"`，缺值时用
  `SESSION_BACKUP_DIR` 或默认目录。
- B3 `templates/launcher.sh` 在 early-signal 成功路径上因 `${_ }` 报 `bad substitution`：循环变量改名并修正输出。
- B4 `templates/launcher.sh` 的 `STRICT_IDEMPOTENT` 用 `NAME` 做 pgrep，首跑必然自匹配被拒：
  删除该启发式，幂等只信 PIDFILE。

**小问题**
- S1 `ckpt` 同名重复登记会双写 `runs[]` 与 `ARTIFACTS.md`：改为同产物 skip、异产物报错。
- S2 删除 `close` 里创建后从不使用的 `session/backup/`。
- S3 `close` 归档后 `stage` 推进到 `S5`。
- S4 `blockers` 未校验类型，字符串会被逐字拆开渲染：写入端要求字符串数组（`--json`），渲染端兼容历史字符串。
- S5 文档计数与实际不符（12 → 15 条模式：12 主 + 3 变体）。
- S6 `resume --prompt` 恒返回 0：改为与 `verify` 一致（产物校验失败返回 1，文本仍打印）。
- S7 计划正文里合法的 `{{`（如代码示例）被误报占位符：改用 `\{\{[A-Z_][A-Z0-9_]*\}\}` 精确匹配。

**健壮性补充**
- N1 `close` 归档前跑完四项检查（plan/state/产物/验收），任一失败即拒绝；`--force` 可跳过并记入日志。
- N2 watcher 的进度改写为单行并限长 120 字，避免心跳行被多行污染。
- N3 会话创建行与 `note` 记录统一为 `HH:MM:SS+08:00 (epoch)` 短格式。
- N4 自测新增目录产物、`--backup` 无值、launcher 实跑、`ckpt` 去重、stage 推进、blockers、
  `{{` 误报、`close` 全检查、watcher 消毒、`resume --prompt` 退出码等用例。
- N5 发布流程改为 scoped 重装（`npx skills add … -s long-task-session`），避免 `update -g` 连带更新其它技能。

**自测**：18 组 → 30 组断言 / 67 个检查点，全绿。

## 0.1.0 — 2026-10-26

首个版本：`long-task-session` 技能。

- 六阶段流程（S0 对账 → S1 定界与量噪 → S2 方案与筛选 → S3 夯实 → S4 执行 → S5 验收与沉淀）
- 四份会话文档（SESSION_PLAN / SESSION_LOG / NEXT_PLAN / ARTIFACTS）+ 机器状态 `state.json`
- `sessionctl`：new / list / status / note / ckpt / state / verify / resume / reconcile / close / doctor
- 长任务三件套模板：幂等 launcher、可重挂 watcher（心跳写纯文本文件）、reconciler
- 15 条抽象模式（12 主 + 3 变体，`references/patterns.md`），不含任何真实项目数据
- 自测 `tests/selftest.sh`：18 组断言 / 41 个检查点，全部通过
