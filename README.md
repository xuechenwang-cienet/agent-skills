# agent-skills

可复用的 agent 技能集合。每个技能是一个顶层目录，内含 `SKILL.md`（YAML frontmatter + 正文）与按需的 `references/`、`templates/`、`scripts/`。

## 技能列表

| 技能 | 用途 | 触发 |
|---|---|---|
| [`long-task-session`](./long-task-session/) | 把预计超过 40 分钟的长任务从想法推进到可验收结果：六阶段流程 + 四份会话文档 + 长任务三件套 | "长任务""跑一晚上""session plan""验收红线" |

## 安装

```bash
# 安装单个技能（全局，claude-code + opencode）
npx -y skills@latest add xuechenwang-cienet/agent-skills -g -s long-task-session \
    -a claude-code opencode -y

# 更新（整体覆盖，改动请回本仓库做）
npx -y skills@latest update -g
```

GitHub 走代理时给 `npx` 加环境变量：

```bash
HTTPS_PROXY=http://127.0.0.1:7897 npx -y skills@latest add xuechenwang-cienet/agent-skills \
    -g -s long-task-session -a claude-code opencode -y
```

## 开发约定

- **单一事实源**：改技能只改本仓库，不要改安装目录（`~/.agents/skills/...`）——`npx skills update` 会整体覆盖。
- **开发期不安装**：逻辑自测直接跑 `python3 long-task-session/scripts/sessionctl.py ...`（用 `--root /tmp/...` 隔离）。
- **触发测试用软链**：临时 `ln -s <repo>/long-task-session ~/.agents/skills/long-task-session`，测完删除；软链保证只有一份代码。
- **发布彩排**：`git push` → `npx skills add ...` → 逐文件 diff 安装副本与源仓库 → 新会话触发一次。

## 版本

变更记录见 [`CHANGELOG.md`](./CHANGELOG.md)。