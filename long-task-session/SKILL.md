---
name: long-task-session
description: >
  把预计超过 40 分钟的长任务从想法推进到可验收结果：六阶段流程（对账→定界量噪→方案筛选→夯实→执行→验收沉淀）、
  四份会话文档、机器状态 state.json、长任务三件套（幂等 launcher / 可重挂 watcher / reconciler）。
  第一目标是"任何新上下文都能零依赖接手"，不依赖 harness 的通知或后台任务存活。
  两种执行形态：无人值守（pipeline 串阶段 + 子代理判读）与 agent 在环（sessionctl observe 到点唤醒 agent，
  按 state.next_action.decision 自动推进或请示用户）。
  触发：长任务、跑一晚上、多阶段任务、session plan、session log、验收红线、轮训器、watcher、断点续跑、
  交叉会话接手、这个实验怎么排、先量再改。
  Trigger: long task, overnight run, multi-stage plan, session plan, session log, acceptance gates,
  watcher, resume after context loss, "how should I sequence this".
  不适用：预计 40 分钟以内的一次性任务、单次问答、纯代码修改（用 debugging/refactor 类技能）。
---

# 长任务会话（long-task-session）

长任务的失败很少是"算不出来"，多半是**中断后没人能接手**、**一次改两个变量说不清归因**、
**指标涨了真实质量却降了**。本技能把这几件事变成流程与文件。

## 一句话边界（先读这条）

**本技能保证"能接上"（Pull），并通过 `pipeline.sh` / `sessionctl observe` 保证"会继续"（Push）——但两者机制不同：**

| 你要的 | 机制 | 谁来做 |
|---|---|---|
| 断了能接手 | 四份文档 + `state.json` + `resume` | 任意新上下文 |
| 阶段跑完自动往下走 | `pipeline.sh`（各阶段串成一条 detached 管道） | 宿主机长进程 |
| **到了检查点，agent 醒来判读并决定继续/请示** | `sessionctl observe`（退出即唤醒）+ `state.next_action.decision` | agent（框架后台任务，可重挂） |
| 有人拍板才继续 | `decision=user` | 用户 |

两条不可违反的边界：

1. **执行体与观察者必须分开住**：执行体 `setsid nohup`（跨重启存活），观察者放框架后台任务（它被杀不丢状态，重挂幂等）。反过来做 = 重启时任务一起断。
2. **"自动执行"到"跑完并落盘"为止**；`decision=user` 的门和口径变更仍等下一次交互。这不是缺陷，是设计选择。

## 何时用

| 条件 | 处理 |
|---|---|
| 预计 **≥40 分钟**，或"不确定但可能超过" | 用本技能（宁可多写两份 md） |
| 跨多轮/跨会话、占远端或 GPU、含不可逆动作 | **full 模式**：四份文档 + `logs/` + `artifacts/` + 结束备份 |
| 单阶段、可即时重跑 | **lite 模式**：`SESSION_PLAN.md` + `SESSION_LOG.md` + `state.json` |
| 预计 <40 分钟 | 不用本技能 |

时长判断：`单步耗时 × 步数`；拿不准就按长任务处理。

## 六阶段

| 阶段 | 名称 | 做什么 | 退出条件 |
|---|---|---|---|
| S0 | 对账 | 读上一轮 `NEXT_PLAN.md` + 日志末尾状态块；核对产物哈希、进程/服务/资源版本 | `sessionctl reconcile` 有结论，且 `status` 的检查项 1–2 通过 |
| S1 | 定界与量噪 | 用当前工具**复现一个历史数字**；同一输入重复 ≥3 次得到噪声带 | 复现值落在噪声带内；无历史基准则先做小样基线（记录 n/参数/版本） |
| S2 | 方案与筛选 | 出 2–4 个方案，逐个用历史模式否/留 | 每个被否方案都写了"被哪条模式否掉" |
| S3 | 夯实 | 写 `SESSION_PLAN.md`：七件硬内容 + 单变量表 + 预注册阈值 + DECISIONS | `sessionctl status` 检查项 1 通过 |
| S4 | 执行 | 长任务三件套；里程碑写 `CKPT`；心跳进 `logs/heartbeat.log` | 终态标记 + 产物哈希 + `state.json` 三者一致 |
| S5 | 验收与沉淀 | 三张表（通过/不通过/中性）+ gap 归因 + `NEXT_PLAN.md` | `sessionctl status` 全部通过；`close` 成功 |

细节见 `references/stages.md`。

## 三条硬规则

1. **单变量**：一次运行相对参考版本只能有一个格子不同，否则结果不可归因。第二个改动排到下一轮。
2. **预注册**：阈值与判定规则在收数据之前写死；事后只允许"通过 / 不通过 / 中性"，不允许重新解释。
3. **先量噪再改**：阈值 ≥2×实测标准误；单条样本的涨跌不得作为结论（n<30 时用极差代替 SE）。

阈值与算法见 `references/metrics.md`。

## 恢复优先（第一目标）

任务必须能被**零上下文的新模型**接手。四条机制：

| 机制 | 作用 |
|---|---|
| `state.json` | 唯一机器状态源（阶段/进行中的 run/下一条命令/阻塞/阈值），只允许经 `sessionctl` 修改 |
| 日志顶部状态块 | `SESSION_LOG.md` 的 `<!-- STATE:BEGIN -->` 区块，由 `sessionctl` 每次重写；读 20 行就能接上 |
| `CKPT` 记录 | 不可再生动作完成后写：产物路径 + sha256 + 验证命令 + 体积 |
| `resume --prompt` | 打印可直接粘贴给新会话的开场白（含三条禁止事项） |

**完成判定不看通知，看产物**：`terminal_marker` 出现 + 产物哈希匹配 + `state.json` 一致，三者不一致时以产物为准并记冲突。

## 长任务三件套

| 组件 | 要求 |
|---|---|
| launcher | 幂等；前置自检（数据/配置/依赖/端口/设备）；失败立即非零退出；日志路径固定 |
| watcher | 心跳 ≤60s 写 `logs/heartbeat.log`（纯文本）；窗口 ≤2h 可重挂；退出条件绑定**真实终态标记**；**上岗前必须过 `sessionctl watch` 自检**（夹具日志验证正则真能抓到进度） |
| reconciler | 会话一接手就跑：`state.json` + 心跳 mtime + 产物哈希，判 running / stale / done |

五条反模式（完整 16 条：13 条主模式 + 3 条变体，见 `references/patterns.md`）：

1. 用输出里的百分比判断终态（别的阶段会打印同名百分比）。
2. 把"进程还活着"当成任务健康。
3. 会话一断就没人管 watcher（应可重挂，且状态以文件为准）。
4. 直接相信远端/容器时间戳（时区与时钟都可能偏）。
5. 用 `pkill -f "<含自身命令行的字符串>"`（会杀掉执行命令的 shell）。

规范与模板见 `references/long-running.md`、`templates/launcher.sh`、`templates/watcher.sh`。

### 托管监控（省上下文）

多阶段任务不要每阶段手写 watcher，也不要让子代理"盯着直到结束"（会提前返回）：

```bash
# 一条命令托管整条链；自检不过会拒绝启动（exit 4）
python3 sessionctl.py watch --session sessions/<slug> --log logs/train.log \
    --marker train_runtime --regex '\| [0-9]+/[0-9]+ \[' --pid "$PID"

# 只跑自检（10 秒内验证正则/终态是否可用）
python3 sessionctl.py watch --selftest-only --log logs/train.log --marker train_runtime \
    --regex '\| [0-9]+/[0-9]+ \['
```

- 多阶段用 `templates/pipeline.sh`：脱离会话、幂等、失败短路、**stdout 只有一行结论**；
- 判读交给子代理（只回一行 VERDICT），细节见 `references/delegation.md`。

## 快速开始

```bash
# 1) 新建会话（full 模式）；自测或试跑时用 --root 隔离
python3 <skill>/scripts/sessionctl.py new <slug> --root ./sessions

# 2) 填 SESSION_PLAN.md（七件硬内容）与单变量表，然后自检
python3 <skill>/scripts/sessionctl.py status --session ./sessions/2026-01-01-<slug>
#    S3/S4 期（gates 还没测）用 --expect-stage 避免把“待测”误报成故障：
#    python3 <skill>/scripts/sessionctl.py status --expect-stage S4

# 2.5) 找会话（默认给人看；--paths 给脚本用，一行一个绝对路径）
python3 <skill>/scripts/sessionctl.py list --paths

# 3) 执行期：起长任务（登记 pid，便于精确停）、里程碑登记产物、随手记录
python3 <skill>/scripts/sessionctl.py run --stage train --cmd "bash scripts/train.sh" \
    --log logs/train.log --marker train_runtime               # 标记出现后自动把 run 标成 done
python3 <skill>/scripts/sessionctl.py stop-run train          # 需要提前停时按 pid 停，不要用 pgrep|kill
python3 <skill>/scripts/sessionctl.py ckpt train-done --artifact artifacts/model/
python3 <skill>/scripts/sessionctl.py note --key fix-1 "把 X 改成 Y，因为 Z"

# 3.5) 需要“到点醒来判读”时：挂 observe（框架后台任务），退出即唤醒 agent
python3 <skill>/scripts/sessionctl.py observe --session ./sessions/<slug> \
    --log logs/train.log --marker train_runtime --regex '\| [0-9]+/[0-9]+ \[' --checkpoint 2400
#      判读后按 next_action.decision 决定自动推进还是请示：
python3 <skill>/scripts/sessionctl.py state next_action.decision user

# 4) 接手时（新上下文）；产物校验失败时退出码为 1（文本仍会打印）
python3 <skill>/scripts/sessionctl.py resume --prompt

# 5) 验收完成、归档备份
python3 <skill>/scripts/sessionctl.py close --backup
```

`status` 打印四行检查表，**任一项失败退出码为 1**，最后一行是 `status: PASS|FAIL x/4`。

`watch` 与 `observe` 的分工：`watch` 是**阶段内的监视器**（写心跳、通常作为 detached pipeline 的子进程）；
`observe` 是**闹钟**（不写 state、睡到 marker/checkpoint/stale/timeout 就退出，把控制权交回 agent）。
两者都强制正则"只匹配形状"：写死总量（如 `[0-9]+/172`）会在上岗自检被拒（退出码 4）。

## 文档职责与 git 归属

| 文档 | 职责 | 进 git |
|---|---|---|
| `SESSION_PLAN.md` | 预注册：问题/证据/方案裁决/单变量表/阈值/成本/回退/决策记录 | ✅ 冻结，只追加修订 |
| `SESSION_LOG.md` | 追加式记录 + 顶部状态块 + 结尾验收三张表 | ✅ |
| `NEXT_PLAN.md` | 交接唯一入口：已完成/未完成/未解问题/下阶段候选/不要做什么 | ✅ |
| `ARTIFACTS.md` | 产物索引：路径/sha256/说明/备份位置 | ✅ |
| `logs/`、`artifacts/`、`backup/` | 原始日志、少量大文件、备份包 | ❌（见 `templates/gitignore-snippet`） |

`new` 会检查目标仓库的 `.gitignore` 是否包含这三行，缺了会打印片段但不自动改文件。

## 计划模式（harness 限制）

opencode 的 plan 模式只允许写 `~/.opencode/plan`。规则：**草稿写那里，批准后落到项目 `sessions/`**，
项目内 `sessions/<date>-<slug>/` 是唯一事实来源；草稿与正式文件同名，便于对照。

## 参考

| 文件 | 内容 |
|---|---|
| `references/stages.md` | 六阶段逐条：输入/动作/产出/退出条件/常见错误 |
| `references/documents.md` | 四份文档的固定小节、`state.json` schema、记录格式、无记忆读者写作要求 |
| `references/long-running.md` | launcher/watcher/reconciler 规范、watcher 自检与失速检测、40 分钟检查点、反模式 |
| `references/metrics.md` | 口径复现、噪声带、单变量表、预注册、防过拟合护栏 |
| `references/delegation.md` | 托管监控：pipeline + watcher 自检 + 子代理判读 + 单行通知契约 |
| `references/patterns.md` | 16 条抽象模式（13 主 + 3 变体；症状/为什么错/对策），不含真实项目数据 |