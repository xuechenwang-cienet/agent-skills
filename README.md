# agent-skills

可复用的 agent 技能集合。每个技能是一个顶层目录，内含 `SKILL.md`（YAML frontmatter + 正文）与按需的 `references/`、`templates/`、`scripts/`、`tests/`。

## 技能列表

| 技能 | 用途 | 触发 |
|---|---|---|
| [`long-task-session`](./long-task-session/) | 把预计超过 40 分钟的长任务从想法推进到可验收结果：六阶段流程 + 四份会话文档 + 长任务三件套 | "长任务""跑一晚上""session plan""验收红线" |
| [`tokenplan-enterprise-bailian`](./tokenplan-enterprise-bailian/) | 阿里云百炼 Token Plan 组织用量分析：导出全量明细、反推 Credits 结算系数、按项目组汇总、预测下月采购与席位结余，生成部门 + 各组 HTML 报告 | "百炼用量""Token Plan""Credits 系数""token 兑换率""项目组用量" |

## 安装

```bash
# 安装单个技能（全局，claude-code + opencode）
npx -y skills@latest add xuechenwang-cienet/agent-skills -g -s long-task-session \
    -a claude-code opencode -y

# 换 -s 即可装其它技能，例如：
npx -y skills@latest add xuechenwang-cienet/agent-skills -g -s tokenplan-enterprise-bailian \
    -a claude-code opencode -y

# 更新（整体覆盖，改动请回本仓库做）
npx -y skills@latest update -g
```

GitHub 走代理时给 `npx` 加环境变量（本机 mihomo 监听在 LAN 地址上，不是 127.0.0.1）：

```bash
HTTPS_PROXY=http://10.10.11.13:7897 HTTP_PROXY=http://10.10.11.13:7897 \
  npx -y skills@latest add xuechenwang-cienet/agent-skills \
    -g -s tokenplan-enterprise-bailian -a claude-code opencode -y
```

## 开发约定

- **单一事实源**：改技能只改本仓库，不要改安装目录（`~/.agents/skills/...`）——`npx skills update` 会整体覆盖。
- **开发期不安装**：逻辑自测直接跑 `python3 long-task-session/scripts/sessionctl.py ...`（用 `--root /tmp/...` 隔离）。
- **`tokenplan-enterprise-bailian` 的本机配置不入库**：`config/config.yaml`、`config/members.csv`、`config/state.json` 与 `output/`、`logs/` 由该技能目录下的 `.gitignore` 挡住；只提交 `*.sample.*`。
- **触发测试用软链**：临时 `ln -s <repo>/long-task-session ~/.agents/skills/long-task-session`，测完删除；软链保证只有一份代码。
- **发布彩排**：`git push` → `npx skills add ...`（scoped，只装这一个技能）→ 逐文件 diff 安装副本与源仓库 → 新会话触发一次。
- 不要用 `npx skills update -g` 做单技能更新：它会连带覆盖其它全局技能。

## 自测

```bash
bash long-task-session/tests/selftest.sh
```

覆盖 32 组断言（71 个检查点）：创建/幂等/冲突、lite 模式、status 四项检查、ckpt 与哈希校验（含篡改、目录产物、
外部哈希）、ckpt 去重、note 去重、resume 与三条禁止事项及其退出码、close 与备份（含 `--backup` 无值、
`--force`、stage 推进、归档前四项检查）、launcher 实跑与幂等、watcher 心跳消毒、list/reconcile、
心跳判活（running/stale）、state 白名单与 blockers 类型、`{{` 误报、py_compile 与纯 stdlib、
`TZ=UTC` 复跑、`list` 两种输出模式、目录产物打包提示、README 安装命令 owner 拼写。

最近一次结果（2026-10-26，Linux，Python 3.13）：

```
==== 结果：PASS=71 FAIL=0 ====      # 仓库内运行
==== 结果：PASS=70 FAIL=0 ====      # 安装副本运行（无仓库根 README，跳过该条）
```

`tokenplan-enterprise-bailian` 没有离线单测（真实取数依赖 bsk + 浏览器登录态），只做语法与入口自检：

```bash
python3 -m compileall -q tokenplan-enterprise-bailian/scripts
python3 tokenplan-enterprise-bailian/scripts/run.py --help
```

真实跑一次需要 `cp config/*.sample.*` 出本机配置并在浏览器登录百炼控制台，见该技能 `SKILL.md`。

## 发布彩排记录

| 日期 | 内容 | 结果 |
|---|---|---|
| 2026-10-26 | `git push` → `npx skills add … -g -s long-task-session` | 安装到 `~/.agents/skills/long-task-session`，Claude Code 侧自动软链 |
| 2026-10-26 | `diff -r --exclude=__pycache__` 源仓库 vs 安装副本 | **完全一致**（15 个文件） |
| 2026-10-26 | 用安装副本跑 `new` / `status` / `doctor` | 正常（新会话 `status: FAIL 2/4` 属预期：plan 有 TODO、gates 为空） |
| 2026-10-26 | 技能发现 | 新会话的技能列表已出现 `long-task-session` |

## 版本

变更记录见 [`CHANGELOG.md`](./CHANGELOG.md)。