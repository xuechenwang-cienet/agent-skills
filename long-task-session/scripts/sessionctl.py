#!/usr/bin/env python3
"""sessionctl — 长任务会话的状态与文档管理器（仅标准库）。

设计要点
  * state.json 是唯一机器状态源，只允许经本工具修改（原子写）。
  * 日志是追加式叙述；watcher 的心跳写 logs/heartbeat.log（纯文本），不进 state.json。
  * 一切时间同时写"本地时间+偏移"与 epoch，避免远端/容器时钟偏移造成误读。
  * status 只做确定性检查（固定标题存在性 + 文件哈希），不做语义解析。

退出码：0 = 通过；1 = 检查未通过/预期未满足；2 = 用法错误。

常用：
  sessionctl.py new <slug> [--root DIR] [--lite] [--suffix] [--force-in-repo]
  sessionctl.py status  [--session DIR]
  sessionctl.py note "文本" [--key K]
  sessionctl.py ckpt <name> --artifact PATH [--sha256 HEX] [--note TEXT]
  sessionctl.py state stage S4 | state gates.caseWt.threshold ">=87.2"
  sessionctl.py verify | resume [--prompt] | reconcile | list | close [--backup] | doctor
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

SCHEMA = 1
STAGES = ["S0", "S1", "S2", "S3", "S4", "S5"]
STATUSES = ["idle", "running", "blocked", "done"]
MODES = ["full", "lite"]
RUN_STATES = ["running", "done", "failed", "stale"]
VERDICTS = ["pass", "fail", "neutral"]

PLAN_REQUIRED = [
    "## 1. 问题",
    "## 2. 当前证据",
    "## 3. 候选方案与裁决",
    "## 4. 单变量表",
    "## 5. 预注册判定",
    "## 6. 成本与资源",
    "## 7. 回退点",
    "## 8. 决策记录（DECISIONS）",
]
ACC_REQUIRED = ["## 验收：通过", "## 验收：不通过", "## 验收：中性", "## Gap 归因"]

STATE_BEGIN = "<!-- STATE:BEGIN -->"
STATE_END = "<!-- STATE:END -->"

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
PLACEHOLDERS = {
    "{{SLUG}}": "slug",
    "{{SESSION}}": "session",
    "{{CREATED_AT}}": "created_at",
    "{{CREATED_SHORT}}": "created_short",
    "{{MODE}}": "mode",
    "{{GIT_COMMIT}}": "git_commit",
}


# ---------------------------------------------------------------- helpers
def now_pair() -> tuple[str, int]:
    local = dt.datetime.now().astimezone()
    epoch = int(local.timestamp())
    return local.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + local.strftime("%z")[
        -2:
    ], epoch


def stamp_short() -> tuple[str, int]:
    local = dt.datetime.now().astimezone()
    epoch = int(local.timestamp())
    return local.strftime("%H:%M:%S%z")[:-2] + ":" + local.strftime("%z")[-2:], epoch


def fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"


def sha256_file(path: Path) -> str:
    if path.is_dir():
        raise ValueError(f"is a directory: {path}（目录产物不做哈希，见 check_artifacts）")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def die(msg: str, code: int = 2) -> "NoReturn":  # type: ignore[name-defined]
    print(f"error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def state_path(session: Path) -> Path:
    return session / "state.json"


def load_state(session: Path) -> dict:
    p = state_path(session)
    if not p.exists():
        die(f"state.json not found in {session}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        die(f"state.json is not valid JSON: {exc}")


def save_state(session: Path, state: dict) -> None:
    """原子写：临时文件 + os.replace + fsync。"""
    iso, epoch = now_pair()
    state["updated_at"] = f"{iso} ({epoch})"
    p = state_path(session)
    fd, tmp = tempfile.mkstemp(dir=str(session), prefix=".state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    fsync_dir(session)


def fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_DIRECTORY)
        os.fsync(fd)
        os.close(fd)
    except Exception:  # noqa: BLE001
        pass


def resolve_session(args) -> Path:
    if getattr(args, "session", None):
        p = Path(args.session).expanduser().resolve()
        if not p.exists():
            die(f"session not found: {p}")
        return p
    # 若 cwd 在某个会话目录内，自动识别
    cur = Path.cwd().resolve()
    for cand in [cur, *cur.parents]:
        if (cand / "state.json").exists() and (cand / "SESSION_LOG.md").exists():
            return cand
    die("cannot determine session; pass --session DIR")


def session_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        [p for p in root.iterdir() if p.is_dir() and (p / "state.json").exists()]
    )


def sections(text: str) -> dict[str, str]:
    """按二级标题切分，返回 {heading: body}。"""
    out: dict[str, str] = {}
    cur = None
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur = line.strip()
            buf = []
        else:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def has_todo(text: str) -> bool:
    return any(ln.strip().startswith("TODO:") for ln in text.splitlines())


def replace_state_block(log_path: Path, state: dict) -> None:
    if not log_path.exists():
        return
    text = log_path.read_text(encoding="utf-8")
    if STATE_BEGIN not in text or STATE_END not in text:
        return
    body = render_state_block(state)
    pattern = re.compile(re.escape(STATE_BEGIN) + r".*?" + re.escape(STATE_END), re.S)
    new = pattern.sub(f"{STATE_BEGIN}\n{body}\n{STATE_END}", text)
    if new != text:
        log_path.write_text(new, encoding="utf-8")


def render_state_block(state: dict) -> str:
    runs = state.get("runs") or []
    running = [r for r in runs if r.get("state") == "running"]
    lines = [
        f"- 会话：`{state.get('session')}`　模式：**{state.get('mode')}**　阶段：**{state.get('stage')}**　状态：**{state.get('status')}**",
        f"- 更新时间：{state.get('updated_at')}",
    ]
    if running:
        for r in running:
            lines.append(
                f"- 进行中：`{r.get('id')}`（心跳间隔 {r.get('heartbeat_interval_s')}s，终态标记 `{r.get('terminal_marker')}`）"
            )
    else:
        lines.append("- 进行中：无")
    na = state.get("next_action") or {}
    lines.append(
        f"- 下一条命令：`{na.get('cmd') or '未设置'}`（预期：{na.get('expect') or '-'}；见 {na.get('doc') or '-'}）"
    )
    blockers = state.get("blockers") or []
    if isinstance(blockers, str):  # 兼容历史会话里被写成字符串的情况
        blockers = [blockers]
    lines.append(f"- 阻塞：{'；'.join(str(b) for b in blockers) if blockers else '无'}")
    gates = state.get("gates") or {}
    if gates:
        parts = [
            f"{k}={v.get('measured') if v.get('measured') is not None else '未测'}/{v.get('threshold')}"
            for k, v in gates.items()
        ]
        lines.append("- 阈值：" + "；".join(parts))
    return "\n".join(lines)


def append_log(log_path: Path, line: str) -> None:
    text = (
        log_path.read_text(encoding="utf-8")
        if log_path.exists()
        else "# 会话日志\n\n## 日志\n\n"
    )
    if "\n## 日志" in text:
        head, _, tail = text.partition("\n## 日志")
        block_end = tail.find("\n---")
        insert_at = block_end if block_end != -1 else len(tail)
        tail = tail[:insert_at].rstrip("\n") + "\n" + line + "\n" + tail[insert_at:]
        text = head + "\n## 日志" + tail
    else:
        text = text.rstrip("\n") + "\n\n## 日志\n\n" + line + "\n"
    log_path.write_text(text, encoding="utf-8")


def log_has_key(log_path: Path, key: str) -> bool:
    if not log_path.exists():
        return False
    return f"[key:{key}]" in log_path.read_text(encoding="utf-8")


def artifacts_rows(artifacts_md: Path) -> list[dict]:
    rows = []
    if not artifacts_md.exists():
        return rows
    for line in artifacts_md.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|") or s.startswith("|---") or "路径" in s.split("|")[1]:
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 5 or cells[0].startswith("（暂无）"):
            continue
        rows.append(
            {
                "path": cells[0].strip("`"),
                "type": cells[1],
                "sha256": cells[2].strip("`"),
                "size": cells[3],
                "note": cells[4],
                "backup": cells[5] if len(cells) > 5 else "-",
            }
        )
    return rows


def append_artifact_row(
    artifacts_md: Path,
    path: str,
    kind: str,
    sha: str,
    size: str,
    note: str,
    source: str,
) -> None:
    text = (
        artifacts_md.read_text(encoding="utf-8")
        if artifacts_md.exists()
        else "# 产物索引\n\n"
    )
    row = f"| `{path}` | {kind} | `{sha}` | {size} | {note}（source: {source}） | - |"
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("| （暂无）")]
    lines.append(row)
    artifacts_md.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")


# ---------------------------------------------------------------- commands
def cmd_new(args) -> int:
    root = Path(args.root).expanduser().resolve()
    slug = args.slug
    today = dt.datetime.now().astimezone().date().isoformat()
    session_id = f"{today}-{slug}"
    target = root / session_id

    if target.exists():
        if (target / "state.json").exists() and not args.suffix:
            print(f"already exists: {target} (no-op)")
            return 0
        if args.suffix:
            i = 2
            while (root / f"{session_id}-{i}").exists():
                i += 1
            target = root / f"{session_id}-{i}"
            session_id = target.name
        else:
            die(f"directory exists but is not a session: {target}")

    if not args.force_in_repo:
        repo = (
            Path(args.repo).expanduser().resolve()
            if args.repo
            else repo_root(Path.cwd())
        )
        if repo and str(repo) in str(target) and "agent-skills" in str(repo):
            die(
                "refusing to create a session inside the skill repo; pass --force-in-repo or --root elsewhere"
            )

    target.mkdir(parents=True, exist_ok=False)
    mode = "lite" if args.lite else "full"
    iso, epoch = now_pair()
    created = f"{iso} ({epoch})"
    git_commit = git_short(target)

    short, short_epoch = stamp_short()
    values = {
        "slug": slug,
        "session": session_id,
        "created_at": created,
        "created_short": f"{short} ({short_epoch})",
        "mode": mode,
        "git_commit": git_commit,
    }
    for tpl in ("SESSION_PLAN.md", "SESSION_LOG.md", "NEXT_PLAN.md", "ARTIFACTS.md"):
        src = TEMPLATE_DIR / tpl
        if not src.exists():
            die(f"template missing: {src}")
        text = src.read_text(encoding="utf-8")
        for ph, key in PLACEHOLDERS.items():
            text = text.replace(ph, str(values[key]))
        (target / tpl).write_text(text, encoding="utf-8")

    if mode == "full":
        (target / "logs").mkdir(exist_ok=True)
        (target / "artifacts").mkdir(exist_ok=True)

    state = {
        "schema": SCHEMA,
        "session": session_id,
        "slug": slug,
        "mode": mode,
        "created_at": created,
        "updated_at": created,
        "stage": "S0",
        "status": "idle",
        "runs": [],
        "next_action": {"cmd": None, "expect": None, "doc": "NEXT_PLAN §6"},
        "blockers": [],
        "gates": {},
    }
    save_state(target, state)
    replace_state_block(target / "SESSION_LOG.md", state)

    print(f"created {target}")
    print(
        f"  mode={mode} stage=S0 files=SESSION_PLAN.md SESSION_LOG.md NEXT_PLAN.md ARTIFACTS.md state.json"
    )
    missing = gitignore_missing(target)
    if missing:
        print("\n提示：目标仓库的 .gitignore 建议补充（未自动修改）：")
        for ln in (
            (TEMPLATE_DIR / "gitignore-snippet")
            .read_text(encoding="utf-8")
            .strip()
            .splitlines()
        ):
            print("  " + ln)
    return 0


def repo_root(start: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return Path(out.stdout.strip())
    except Exception:  # noqa: BLE001
        pass
    return None


def git_short(path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "n/a"
    except Exception:  # noqa: BLE001
        return "n/a"


def gitignore_missing(session: Path) -> bool:
    repo = repo_root(session)
    if not repo:
        return False
    gi = repo / ".gitignore"
    need = ["sessions/*/logs/", "sessions/*/artifacts/", "sessions/*/backup/"]
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    return any(n not in text for n in need)


def cmd_list(args) -> int:
    root = Path(args.root).expanduser().resolve()
    dirs = session_dirs(root)
    if not dirs:
        print(f"(no sessions under {root})")
        return 0
    if getattr(args, "paths", False):
        for d in dirs:
            print(d)
        return 0
    print(f"root: {root}")
    print(f"{'session':<40}{'stage':<8}{'status':<10}{'mode':<7}{'updated_at'}")
    for d in dirs:
        try:
            st = load_state(d)
        except SystemExit:
            continue
        print(
            f"{d.name:<40}{st.get('stage', ''):<8}{st.get('status', ''):<10}{st.get('mode', ''):<7}{st.get('updated_at', '')}"
        )
    return 0


def check_plan(session: Path) -> tuple[bool, list[str]]:
    p = session / "SESSION_PLAN.md"
    if not p.exists():
        return False, ["SESSION_PLAN.md 不存在"]
    text = p.read_text(encoding="utf-8")
    problems = []
    for h in PLAN_REQUIRED:
        if h not in text:
            problems.append(f"缺少小节 {h}")
    if re.search(r"\{\{[A-Z_][A-Z0-9_]*\}\}", text):
        problems.append("存在未替换的占位符 {{…}}")
    if has_todo(text):
        problems.append("存在未清理的 TODO:")
    return (not problems), problems


def check_state(session: Path) -> tuple[bool, list[str], dict]:
    p = state_path(session)
    if not p.exists():
        return False, ["state.json 不存在"], {}
    try:
        st = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, [f"state.json 解析失败: {exc}"], {}
    problems = []
    if st.get("schema") != SCHEMA:
        problems.append(f"schema 应为 {SCHEMA}")
    if st.get("stage") not in STAGES:
        problems.append(f"stage 非法: {st.get('stage')}")
    if st.get("status") not in STATUSES:
        problems.append(f"status 非法: {st.get('status')}")
    if st.get("mode") not in MODES:
        problems.append(f"mode 非法: {st.get('mode')}")
    for r in st.get("runs") or []:
        if r.get("state") not in RUN_STATES:
            problems.append(f"run {r.get('id')} state 非法: {r.get('state')}")
    for name, g in (st.get("gates") or {}).items():
        if not isinstance(g, dict):
            problems.append(f"gate {name} 结构非法")
        elif g.get("verdict") not in VERDICTS + [None]:
            problems.append(f"gate {name} verdict 非法: {g.get('verdict')}")
    return (not problems), problems, st


def check_artifacts(session: Path, st: dict) -> tuple[bool, list[str], list[str]]:
    """返回 (通过?, 错误, 提示)。lite 或无产物时通过。"""
    if st.get("mode") == "lite":
        return True, [], ["lite 模式：跳过产物校验"]
    rows = artifacts_rows(session / "ARTIFACTS.md")
    if not rows:
        return True, [], ["暂无登记产物"]
    errors, notes = [], []
    for r in rows:
        path = session / r["path"]
        if not Path(r["path"]).is_absolute() and not path.exists():
            path = Path(r["path"])
        if "source: caller" in r.get("note", ""):
            notes.append(f"{r['path']}：调用方哈希，未本地校验")
            continue
        if not path.exists():
            errors.append(f"{r['path']} 不存在")
            continue
        if path.is_dir():
            if r["sha256"].strip("`") not in ("dir", ""):
                errors.append(f"{r['path']} 是目录但记录了文件哈希 {r['sha256'][:16]}…")
            else:
                notes.append(
                    f"{r['path']}：目录产物未做哈希（内容以 CKPT 记录为准）；"
                    "建议 tar 打包后用 ckpt 登记归档文件，才能被校验"
                )
            continue
        actual = sha256_file(path)
        if r["sha256"] and not actual.startswith(r["sha256"].strip("`")[:64]):
            errors.append(
                f"{r['path']} 哈希不匹配（记录 {r['sha256'][:16]}… 实际 {actual[:16]}…）"
            )
    return (not errors), errors, notes


def check_acceptance(session: Path, st: dict) -> tuple[bool, list[str]]:
    p = session / "SESSION_LOG.md"
    if not p.exists():
        return False, ["SESSION_LOG.md 不存在"]
    text = p.read_text(encoding="utf-8")
    secs = sections(text)
    problems = []
    for h in ACC_REQUIRED:
        if h not in secs:
            problems.append(f"缺少小节 {h}")
        elif not secs[h].strip():
            problems.append(f"{h} 为空（没有内容请写「无」）")
        elif has_todo(secs[h]):
            problems.append(f"{h} 仍有 TODO")
    gates = st.get("gates") or {}
    if not gates:
        problems.append(
            "state.gates 为空：请用 `sessionctl state gates.<指标>.threshold …` 登记预注册阈值"
        )
    else:
        for name, g in gates.items():
            if not g.get("verdict"):
                problems.append(f"gate {name} 尚无判定（pass/fail/neutral）")
    return (not problems), problems


def heartbeat_status(session: Path, st: dict) -> str:
    hb = session / "logs" / "heartbeat.log"
    if not hb.exists():
        return "心跳：无（尚未启动长任务）"
    age = int(dt.datetime.now().timestamp() - hb.stat().st_mtime)
    interval = 60
    for r in st.get("runs") or []:
        if r.get("state") == "running" and r.get("heartbeat_interval_s"):
            interval = int(r["heartbeat_interval_s"])
            break
    verdict = "running" if age <= 3 * interval else "stale"
    msg = f"心跳：{age}s 前（间隔 {interval}s）→ {verdict}"
    # 假推进体检：声明了进度正则、但最近一条心跳 progress=- → 正则没抓到任何东西
    declared = any(r.get("progress_regex") for r in st.get("runs") or [])
    if declared:
        try:
            last = hb.read_text(encoding="utf-8").strip().splitlines()[-1]
        except Exception:
            last = ""
        if "progress=-" in last:
            msg += "  ⚠ 最近一次 progress=-（声明了进度正则却抓不到：检查是否写死了总量，或日志格式变了）"
        if "stale_progress" in last:
            msg += "  ⚠ 最近一次失速（stale_progress）"
    return msg


def cmd_status(args) -> int:
    session = resolve_session(args)
    ok1, p1 = check_plan(session)
    ok2, p2, st = check_state(session)
    if st:
        ok3, p3, notes3 = check_artifacts(session, st)
        ok4, p4 = check_acceptance(session, st)
    else:
        ok3, p3, notes3, ok4, p4 = (
            False,
            ["无法检查：state.json 不可用"],
            [],
            False,
            ["无法检查：state.json 不可用"],
        )

    checks = [
        ("plan 七件硬内容", ok1, p1),
        ("state.json 自洽", ok2, p2),
        ("产物哈希可验", ok3, p3),
        ("验收表与判定", ok4, p4),
    ]
    print(f"session: {session}")
    for name, ok, problems in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        for msg in problems:
            print(f"      - {msg}")
    for note in notes3:
        print(f"  ℹ️  {note}")
    if st:
        print(f"  ℹ️  {heartbeat_status(session, st)}")
        decision = (st.get("next_action") or {}).get("decision") or "agent"
        if decision == "user" and st.get("status") != "done":
            print("  ⏸ 推进权在用户（next_action.decision=user）：判读后先请示，不要自动进入下一阶段")
        else:
            print(f"  ▶ 推进权：{decision}（判读后可直接推进，并重新挂 observe）")
    passed = sum(1 for _, ok, _ in checks if ok)
    print(f"status: {'PASS' if passed == 4 else 'FAIL'} {passed}/4")
    return 0 if passed == 4 else 1


def cmd_note(args) -> int:
    session = resolve_session(args)
    log = session / "SESSION_LOG.md"
    if args.key and log_has_key(log, args.key):
        print(f"skip: key '{args.key}' already recorded")
        return 0
    ts, epoch = stamp_short()
    suffix = f" [key:{args.key}]" if args.key else ""
    line = f"- {ts} ({epoch}) · {args.text}{suffix}"
    append_log(log, line)
    st = load_state(session)
    replace_state_block(log, st)
    print(f"noted: {line}")
    return 0


def cmd_ckpt(args) -> int:
    session = resolve_session(args)
    artifact = Path(args.artifact).expanduser()
    resolved = artifact if artifact.is_absolute() else (session / artifact)
    if not resolved.exists():
        # 允许登记尚不存在但已由调用方提供哈希的远端产物
        if not args.sha256:
            die(
                f"artifact not found: {resolved}（若为远端产物，请用 --sha256 提供哈希）"
            )
        size, sha, source = "?", args.sha256, "caller"
    else:
        size = fmt_bytes(resolved.stat().st_size) if resolved.is_file() else "dir"
        if args.sha256:
            sha, source = args.sha256, "caller"
        elif resolved.is_file():
            sha, source = sha256_file(resolved), "local"
        else:
            sha, source = "dir", "local"
    rel = (
        str(resolved.relative_to(session))
        if str(resolved).startswith(str(session))
        else str(resolved)
    )

    st = load_state(session)
    for r in st.get("runs") or []:
        if r.get("id") == args.name:
            if r.get("artifact") == rel:
                print(f"skip: ckpt '{args.name}' already registered")
                return 0
            die(f"ckpt '{args.name}' 已用于其他产物 {r.get('artifact')}；请换名字")
    iso, epoch = now_pair()
    kind = args.note or "artifact"
    block = [
        f"### CKPT {args.name} · {iso} ({epoch})",
        f"- 产物: {rel}",
        f"- sha256: {sha}（source: {source}）",
        f"- 大小: {size}",
        f"- 验证: sha256sum {rel}",
        "",
    ]
    append_log(session / "SESSION_LOG.md", "\n".join(block).rstrip())

    st.setdefault("runs", []).append(
        {
            "id": args.name,
            "kind": "long" if args.long else "checkpoint",
            "started_at": f"{iso} ({epoch})",
            "heartbeat_interval_s": args.heartbeat_interval,
            "terminal_marker": args.terminal_marker,
            "progress_regex": getattr(args, "progress_regex", None),
            "state": args.state,
            "artifact": rel,
            "sha256": sha,
            "sha256_source": source,
        }
    )
    save_state(session, st)
    append_artifact_row(
        session / "ARTIFACTS.md", rel, kind, sha, size, args.note or "-", source
    )
    replace_state_block(session / "SESSION_LOG.md", st)
    print(f"ckpt {args.name}: {rel} sha256={sha[:16]}… source={source}")
    if resolved.is_dir():
        name = Path(rel).name
        script = Path(sys.argv[0]).resolve()
        archive = f"artifacts/{name}.tar.gz"
        print("→ 目录产物无法做哈希校验；建议打包后登记归档文件：")
        if not Path(rel).is_absolute():
            print(f"  tar -czf {session}/{archive} -C {session} {rel}")
        else:
            print(f"  tar -czf {session}/{archive} {rel}")
        print(
            f"  python3 {script} ckpt {args.name}-archive --artifact {archive} "
            f"--session {session}"
        )
    return 0


STATE_WHITELIST_EXACT = {
    "stage",
    "status",
    "next_action.cmd",
    "next_action.expect",
    "next_action.doc",
    "next_action.decision",
    "blockers",
}
STATE_WHITELIST_PREFIX = ("gates.",)


def cmd_state(args) -> int:
    session = resolve_session(args)
    key, value = args.key, args.value
    if key not in STATE_WHITELIST_EXACT and not key.startswith(STATE_WHITELIST_PREFIX):
        die(
            f"key not allowed: {key}（允许：{sorted(STATE_WHITELIST_EXACT)} 或 gates.<name>.<field>）"
        )
    if args.json:
        try:
            value = json.loads(args.value)
        except Exception as exc:  # noqa: BLE001
            die(f"--json 解析失败: {exc}")
    st = load_state(session)
    if key == "stage" and value not in STAGES:
        die(f"stage must be one of {STAGES}")
    if key == "status" and value not in STATUSES:
        die(f"status must be one of {STATUSES}")
    if key == "next_action.decision" and value not in DECISIONS:
        die(f"next_action.decision must be one of {DECISIONS}")
    if key == "blockers" and (
        not isinstance(value, list) or not all(isinstance(x, str) for x in value)
    ):
        die("""blockers 必须是字符串数组：state blockers '["等待用户拍板"]' --json""")
    parts = key.split(".")
    if key.startswith("gates."):
        if len(parts) < 3:
            die("gates key 形如 gates.<name>.<field>")
        name, field = parts[1], ".".join(parts[2:])
        if field not in ("threshold", "measured", "verdict"):
            die("gate field 只能是 threshold / measured / verdict")
        if field == "verdict" and value is not None and value not in VERDICTS:
            die(f"verdict must be one of {VERDICTS}")
        st.setdefault("gates", {}).setdefault(name, {})[field] = value
    elif key.startswith("next_action."):
        st.setdefault("next_action", {})[key.split(".", 1)[1]] = value
    else:
        st[key] = value
    save_state(session, st)
    replace_state_block(session / "SESSION_LOG.md", st)
    print(f"state {key} = {value}")
    return 0


def cmd_verify(args) -> int:
    session = resolve_session(args)
    ok, errors, notes = check_artifacts(session, load_state(session))
    for n in notes:
        print(f"  ℹ️  {n}")
    if ok:
        print("verify: PASS")
        return 0
    for e in errors:
        print(f"  ❌ {e}")
    print("verify: FAIL")
    return 1


def cmd_resume(args) -> int:
    session = resolve_session(args)
    st = load_state(session)
    ok_v, errors, notes = check_artifacts(session, st)
    hb = heartbeat_status(session, st)
    na = st.get("next_action") or {}
    blockers = st.get("blockers") or []

    if args.prompt:
        print("请先读以下三个文件，然后按「下一条命令」继续，不要重新规划：")
        print(f"  1) {session}/state.json")
        print(f"  2) {session}/NEXT_PLAN.md（§5 不要做什么、§6 下一条命令）")
        print(f"  3) {session}/SESSION_LOG.md 顶部状态块 + 末尾")
        print()
        print("当前状态：")
        print(
            f"  阶段 {st.get('stage')} / 状态 {st.get('status')} / 模式 {st.get('mode')}"
        )
        print(f"  {hb}")
        print(
            f"  产物校验：{'PASS' if ok_v else 'FAIL'}"
            + (f"（{'; '.join(errors)}）" if errors else "")
        )
        print(f"  推进权：{na.get('decision') or 'agent'}（decision=user 时先请示再执行）")
        print(
            f"  下一条命令：{na.get('cmd') or '未设置（请先补 state.next_action.cmd）'}"
        )
        print(f"  预期：{na.get('expect') or '-'}　依据：{na.get('doc') or '-'}")
        print(f"  阻塞：{'；'.join(blockers) if blockers else '无'}")
        print()
        print("禁止事项（硬约束）：")
        print("  1. 不要重新评估 DECISIONS 里已否决的方案（见 SESSION_PLAN.md §8）。")
        print("  2. 不要改动 gold / 已验收产物；如需改动，先写新的决策记录。")
        print(
            "  3. 不要用单条样本的涨跌下结论（见 references/metrics.md 的噪声带规则）。"
        )
        # 文本始终打印；退出码与 verify 一致，便于调用方感知产物已损坏
        return 0 if ok_v else 1

    print(render_state_block(st))
    print(f"- 产物校验：{'PASS' if ok_v else 'FAIL'}")
    for e in errors:
        print(f"    ❌ {e}")
    for n in notes:
        print(f"    ℹ️  {n}")
    print(f"- {hb}")
    return 0 if ok_v else 1


def cmd_reconcile(args) -> int:
    root = Path(args.root).expanduser().resolve()
    dirs = session_dirs(root)
    if not dirs:
        print(f"(no sessions under {root})")
        return 0
    session = dirs[-1]
    st = load_state(session)
    ok_v, errors, _ = check_artifacts(session, st)
    print(f"最新会话：{session}")
    print(render_state_block(st))
    print(f"- 产物校验：{'PASS' if ok_v else 'FAIL'}")
    for e in errors:
        print(f"    ❌ {e}")
    print(f"- {heartbeat_status(session, st)}")

    plan = session / "NEXT_PLAN.md"
    if plan.exists():
        secs = sections(plan.read_text(encoding="utf-8"))
        cmd = secs.get("## 6. 下一条命令", "").strip()
        if cmd:
            print("- NEXT_PLAN §6：")
            for ln in cmd.splitlines():
                print("    " + ln)
    log = session / "SESSION_LOG.md"
    if log.exists():
        records = [
            ln
            for ln in log.read_text(encoding="utf-8").splitlines()
            if re.match(r"^- \d{2}:\d{2}:\d{2}", ln)
        ]
        print("- 日志末尾：")
        for ln in records[-3:]:
            print("    " + ln[:200])
    return 0


def cmd_close(args) -> int:
    """归档前跑完四项检查（N1）；--force 可跳过但会写日志。"""
    session = resolve_session(args)
    ok2, p2, st = check_state(session)
    if not st:
        print("close: 拒绝归档，state.json 不可用：")
        for msg in p2:
            print("  - " + msg)
        return 1
    ok1, p1 = check_plan(session)
    ok3, p3, _ = check_artifacts(session, st)
    ok4, p4 = check_acceptance(session, st)
    failed = [
        (name, problems)
        for name, ok, problems in (
            ("plan 七件硬内容", ok1, p1),
            ("state.json 自洽", ok2, p2),
            ("产物哈希可验", ok3, p3),
            ("验收表与判定", ok4, p4),
        )
        if not ok
    ]
    if failed and not args.force:
        print("close: 拒绝归档，以下检查未通过：")
        for name, problems in failed:
            print(f"  ❌ {name}")
            for msg in problems:
                print("      - " + msg)
        print("如需强制归档：close --backup --force（会记入日志）")
        return 1
    if failed:
        ts, ep = stamp_short()
        append_log(
            session / "SESSION_LOG.md",
            f"- {ts} ({ep}) · 强制归档 · 证据: close --force · "
            f"结果: 跳过 {len(failed)} 项检查（{[n for n, _ in failed]}） · 决策: 已知不完整仍归档",
        )
        print(f"warn: --force 跳过 {len(failed)} 项检查（已记入日志）")

    logs = session / "logs"
    arts = session / "artifacts"
    backup_dir = Path(
        args.backup or os.environ.get("SESSION_BACKUP_DIR", "~/backups/agent-sessions")
    ).expanduser()
    backup_dir.mkdir(parents=True, exist_ok=True)
    iso, epoch = now_pair()

    # zstd 压缩走外部 tar（Python tarfile 不支持 zstd），缺失时自动降级 gzip
    use_zstd = shutil.which("zstd") is not None and shutil.which("tar") is not None
    suffix = "tar.zst" if use_zstd else "tar.gz"
    name = f"{session.name}-logs-artifacts-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.{suffix}"
    pkg = backup_dir / name

    members = [d for d in (logs, arts) if d.exists()]
    if not members:
        # lite 模式没有 logs/artifacts：改为归档会话文档，保证备份包非空且可校验
        print("note: 无 logs/artifacts，归档会话文档（lite 模式）")
        members = [p for p in (session / "SESSION_PLAN.md", session / "SESSION_LOG.md",
                               session / "NEXT_PLAN.md", session / "ARTIFACTS.md",
                               session / "state.json") if p.exists()]

    arc = [f"{session.name}/{p.name}" for p in members]
    try:
        if use_zstd:
            cmd = ["tar", "--zstd", "-cf", str(pkg)] + arc
            rc = subprocess.run(cmd, cwd=str(session.parent), capture_output=True, text=True)
            if rc.returncode != 0:
                raise RuntimeError(rc.stderr.strip()[:200])
        else:
            with tarfile.open(pkg, "w:gz") as tar:
                for name in arc:
                    tar.add(session.parent / name, arcname=name)
    except Exception as exc:  # noqa: BLE001
        die(f"backup failed: {exc}", 1)

    sha = sha256_file(pkg)
    (backup_dir / f"{name}.sha256").write_text(f"{sha}  {name}\n", encoding="utf-8")

    remote_note = ""
    if args.remote:
        rsync = shutil.which("rsync")
        if not rsync:
            print("warn: rsync 未安装，跳过远端备份")
        else:
            rc = subprocess.run(
                [rsync, "-a", str(pkg), args.remote], capture_output=True, text=True
            )
            if rc.returncode != 0:
                print(f"warn: 远端备份失败：{rc.stderr.strip()[:200]}")
            else:
                remote_note = f"；远端：{args.remote.rstrip('/')}/{name}"

    # 写回文档
    art_md = session / "ARTIFACTS.md"
    text = art_md.read_text(encoding="utf-8") if art_md.exists() else "# 产物索引\n\n"
    text += f"\n备份：`{pkg}`（{fmt_bytes(pkg.stat().st_size)}，sha256 `{sha[:16]}…`{remote_note}）\n"
    art_md.write_text(text, encoding="utf-8")

    plan = session / "NEXT_PLAN.md"
    if plan.exists():
        ptext = plan.read_text(encoding="utf-8").rstrip("\n")
        ptext += f"\n\n备份位置：`{pkg}`（sha256 `{sha[:16]}…`{remote_note}）\n"
        plan.write_text(ptext, encoding="utf-8")

    ts, ep = stamp_short()
    append_log(
        session / "SESSION_LOG.md",
        f"- {ts} ({ep}) · 归档备份 · 证据: {pkg} · 结果: {fmt_bytes(pkg.stat().st_size)} · 决策: 会话可归档",
    )
    st["status"] = "done"
    st["stage"] = "S5"
    for r in st.get("runs") or []:
        if r.get("state") == "running":
            r["state"] = "done"
    save_state(session, st)
    replace_state_block(session / "SESSION_LOG.md", st)

    print(f"backup: {pkg} ({fmt_bytes(pkg.stat().st_size)}) sha256={sha[:16]}…")
    print(
        "next: 把 SESSION_PLAN.md / SESSION_LOG.md / NEXT_PLAN.md / ARTIFACTS.md 提交到 git（logs/artifacts 已 gitignore）"
    )
    return 0


WATCHER_HINT = """检查这几项：
  1) PROGRESS_REGEX 是否写死了总量（例如 \\| [0-9]+/172 \\[）—— 不同批次步数不同，必须只匹配形状
  2) 日志里的进度行格式是否与正则一致（tqdm 的进度条用 \\r 分隔，本工具已做 tr '\\r' '\\n'）
  3) 若该阶段本来就没有进度输出，去掉 --regex（只保留终态标记）"""


def watcher_selftest(regex: str) -> tuple[bool, str]:
    """用两份夹具日志验证 watcher 模板"真的能看见"进度与终态。

    夹具刻意使用与具体批次无关的通用进度行（`| 5/207 [...]`）：任何写死总量的正则都会在
    这里失败，而不是在真实长任务里安静地写 10 分钟 `progress=-`。
    """
    tpl = TEMPLATE_DIR / "watcher.sh"
    if not tpl.exists():
        return False, f"模板缺失: {tpl}"
    base = Path("/tmp/opencode") if Path("/tmp/opencode").is_dir() else Path(tempfile.gettempdir())
    prog = "| 5/207 [00:12<01:30:00, 40.5s/it]"
    problems: list[str] = []
    with tempfile.TemporaryDirectory(prefix="lts-watch-selftest.", dir=str(base)) as td:
        root = Path(td)
        want_progress = bool(regex)
        for tag, marker_line, want_code in (
            ("a", None, 3),          # 无终态 -> 窗口到期，但进度必须抓到
            ("b", "TERMINAL_OK", 0),  # 有终态 -> 立刻退出 0
        ):
            d = root / tag
            (d / "logs").mkdir(parents=True)
            log = d / "stage.log"
            log.write_text("stage started\n" + prog + "\n" + ((marker_line + "\n") if marker_line else ""), encoding="utf-8")
            env = dict(os.environ)
            env.update(
                SESSION_DIR=str(d),
                LOG=str(log),
                TERMINAL_MARKER="TERMINAL_OK",
                PROGRESS_REGEX=regex,
                INTERVAL="1",
                MAX_WINDOW="1",
                RUN_ID="selftest",
            )
            try:
                r = subprocess.run(["bash", str(tpl)], env=env, capture_output=True, text=True, timeout=20)
            except subprocess.TimeoutExpired:
                problems.append(f"夹具{tag} 超时（watcher 没退出）")
                continue
            if r.returncode != want_code:
                problems.append(f"夹具{tag} 退出码 {r.returncode}（期望 {want_code}）")
            hb = d / "logs" / "heartbeat.log"
            text = hb.read_text(encoding="utf-8") if hb.exists() else ""
            if not text.strip():
                problems.append(f"夹具{tag} 没有写出心跳")
            elif want_progress and tag == "a" and "5/207" not in text:
                problems.append(f"夹具{tag} 进度未被抓取（progress 恒为 -）：正则与日志格式不匹配或被写死")
    if problems:
        return False, "; ".join(problems)
    return True, "ok"


OBSERVE_EVENTS = ("marker", "checkpoint", "stale", "timeout")
DECISIONS = ("agent", "user")
TAIL_BYTES = 262144


def _tail_text(path: Path) -> str:
    """读文件末尾 TAIL_BYTES，避免把几 GB 的训练日志读进内存。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - TAIL_BYTES))
            return f.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return ""


def _observe_selftest(regex: str) -> tuple[bool, str]:
    """用临时日志做自检：标记命中退出 0；无标记但 checkpoint 到点退出 3。"""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "t.log"
        log.write_text("boot\n| 5/207 [00:10<01:00, 2.0s/it]\n", encoding="utf-8")
        args = argparse.Namespace(
            log=str(log), marker="TRAIN_DONE", regex=regex, interval=0.05,
            checkpoint=0.3, window=5, stale_limit=0, exit_on_stale=False, run_id="selftest",
        )
        rc = cmd_observe(args, _return_only=True)
        if rc != 3:
            return False, f"无标记时应因 checkpoint 退出 3，实际 {rc}"
        log.write_text(log.read_text(encoding="utf-8") + "TRAIN_DONE\n", encoding="utf-8")
        args.checkpoint = 5
        rc = cmd_observe(args, _return_only=True)
        if rc != 0:
            return False, f"标记出现时应退出 0，实际 {rc}"
        if regex and not re.search(regex, _tail_text(log)):
            return False, f"正则抓不到进度行：{regex}"
    return True, "ok"


def cmd_observe(args, _return_only: bool = False) -> int:
    """观察者（闹钟）：睡到事件发生就退出，把控制权交回 agent。

    与 watch 的区别：
      * watch   —— 阶段内的监视器，写心跳，通常作为 detached pipeline 的子进程长期运行；
      * observe —— 框架后台任务里的"闹钟"，**只退出、不判读、不写 state**；退出即唤醒 agent。
    契约：agent 每次被唤醒后，先 `status`/`resume` 判读，再按 next_action 推进或请示用户，
    然后**重新挂一个新的 observe**（观察者死亡是正常事件，状态在磁盘上）。
    退出码：0=marker 3=checkpoint 5=stale 2=timeout 4=自检失败
    """
    if args.regex:
        try:
            re.compile(args.regex)
        except re.error as exc:
            die(f"invalid --regex: {exc}")
        if not getattr(args, "no_selftest", False):
            ok, detail = watcher_selftest(args.regex)
            if not ok:
                print(f"observe regex selftest: FAIL — {detail}", file=sys.stderr)
                print(WATCHER_HINT, file=sys.stderr)
                return 4
    if getattr(args, "selftest", False):
        ok, detail = _observe_selftest(args.regex or "")
        if ok:
            print("observe selftest: PASS（marker→0 / checkpoint→3 / 正则可抓进度）")
            return 0
        print(f"observe selftest: FAIL — {detail}", file=sys.stderr)
        return 4
    log = Path(args.log).expanduser()
    if not log.is_absolute():
        log = (Path.cwd() / log).resolve()
    if not log.exists():
        die(f"log not found: {log}")
    if args.checkpoint <= 0 and args.window <= 0 and not args.marker:
        die("observe 至少要有 marker / --checkpoint / --window 之一，否则会永不返回")

    start = time.time()
    last_progress = None
    identical = 0
    while True:
        text = _tail_text(log)
        progress = None
        if args.regex:
            found = list(re.finditer(args.regex, text))
            if found:
                progress = found[-1].group(0).strip()
        elapsed = int(time.time() - start)
        if args.marker and args.marker in text:
            event = "marker"
            rc = 0
        elif progress is not None:
            identical = identical + 1 if progress == last_progress else 0
            last_progress = progress
            if args.exit_on_stale and args.stale_limit and identical >= args.stale_limit:
                event, rc = "stale", 5
            else:
                event = rc = None
        else:
            event = rc = None
        if event is None and args.checkpoint and elapsed >= args.checkpoint:
            event, rc = "checkpoint", 3
        if event is None and args.window and elapsed >= args.window:
            event, rc = "timeout", 2
        if event:
            if not _return_only:
                print(
                    f'OBSERVE event={event} session={getattr(args, "session", None) or "-"} '
                    f'run={args.run_id or "-"} elapsed={elapsed}s marker={int(bool(args.marker and args.marker in text))} '
                    f'progress="{progress or "-"}"'
                )
            return rc
        time.sleep(args.interval)


def cmd_watch(args) -> int:
    """包装 watcher 模板：先自检，再托管；退出码透传（0/2/3/5）。"""
    session = resolve_session(args)
    log = Path(args.log).expanduser()
    if not log.is_absolute():
        log = (Path.cwd() / log).resolve()
    if not log.exists():
        die(f"log not found: {log}")

    if not args.selftest_only and not args.no_selftest:
        ok, detail = watcher_selftest(args.regex or "")
        if not ok:
            print("watcher selftest: FAIL", file=sys.stderr)
            print(f"  {detail}", file=sys.stderr)
            print(WATCHER_HINT, file=sys.stderr)
            return 4
        print("watcher selftest: PASS（夹具 | 5/207 [...] 能被正则抓到，终态路径可退出）")
    elif args.selftest_only:
        ok, detail = watcher_selftest(args.regex or "")
        if ok:
            print("watcher selftest: PASS")
            return 0
        print(f"watcher selftest: FAIL — {detail}", file=sys.stderr)
        print(WATCHER_HINT, file=sys.stderr)
        return 4

    run_id = args.run_id or log.stem
    st = load_state(session)
    if not any(r.get("id") == run_id for r in st.get("runs") or []):
        iso, epoch = now_pair()
        st.setdefault("runs", []).append(
            {
                "id": run_id,
                "kind": "watch",
                "started_at": f"{iso} ({epoch})",
                "heartbeat_interval_s": args.interval,
                "terminal_marker": args.marker,
                "progress_regex": args.regex,
                "state": "running",
                "artifact": None,
                "sha256": None,
                "sha256_source": None,
            }
        )
        save_state(session, st)

    tpl = TEMPLATE_DIR / "watcher.sh"
    env = dict(os.environ)
    env.update(
        SESSION_DIR=str(session),
        LOG=str(log),
        TERMINAL_MARKER=args.marker,
        PROGRESS_REGEX=args.regex or "",
        INTERVAL=str(args.interval),
        MAX_WINDOW=str(args.window),
        STALE_LIMIT=str(args.stale_limit),
        FAIL_ON_STALE=str(args.fail_on_stale),
        RUN_ID=run_id,
    )
    if args.pid:
        env["PID"] = str(args.pid)
    rc = subprocess.call(["bash", str(tpl)], env=env)

    st = load_state(session)
    for r in st.get("runs") or []:
        if r.get("id") == run_id and r.get("state") == "running":
            r["state"] = "done" if rc == 0 else ("stale" if rc in (2, 5) else "failed")
    save_state(session, st)
    return rc


def cmd_doctor(args) -> int:
    print(f"python3 : {sys.version.split()[0]}")
    for tool in ("tar", "zstd", "rsync", "git"):
        path = shutil.which(tool)
        if path:
            try:
                out = subprocess.run(
                    [tool, "--version"], capture_output=True, text=True, timeout=10
                )
                ver = out.stdout.splitlines()[0] if out.stdout else ""
            except Exception:  # noqa: BLE001
                ver = ""
            print(f"{tool:<8}: {path}  {ver[:60]}")
        else:
            extra = (
                "（缺失：备份将降级为 tar.gz / 远端备份跳过）"
                if tool in ("zstd", "rsync")
                else "（缺失）"
            )
            print(f"{tool:<8}: not found {extra}")
    return 0


# ---------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="sessionctl", description="long-task-session 状态与文档管理"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_common(p, need_session=True):
        if need_session:
            p.add_argument("--session", help="会话目录（省略时按 cwd 自动识别）")

    p = sub.add_parser("new", help="新建会话目录与四份文档")
    p.add_argument("slug")
    p.add_argument("--root", default="./sessions")
    p.add_argument("--lite", action="store_true")
    p.add_argument("--suffix", action="store_true")
    p.add_argument("--force-in-repo", action="store_true")
    p.add_argument("--repo", default=None)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("list", help="列出会话")
    p.add_argument("--root", default="./sessions")
    p.add_argument("--paths", action="store_true", help="只输出绝对路径，一行一个")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="四项检查（任一失败退出码 1）")
    add_common(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("note", help="追加一条日志记录")
    p.add_argument("text")
    p.add_argument("--key", default=None)
    add_common(p)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("ckpt", help="登记里程碑产物")
    p.add_argument("name")
    p.add_argument("--artifact", required=True)
    p.add_argument("--sha256", default=None)
    p.add_argument("--note", default=None)
    p.add_argument("--long", action="store_true")
    p.add_argument("--state", default="done", choices=RUN_STATES)
    p.add_argument("--terminal-marker", default=None)
    p.add_argument("--progress-regex", default=None, help="进度抓取正则（给 status 做假推进体检）")
    p.add_argument("--heartbeat-interval", type=int, default=60)
    add_common(p)
    p.set_defaults(func=cmd_ckpt)

    p = sub.add_parser("state", help="修改 state.json（白名单键）")
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--json", action="store_true")
    add_common(p)
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("verify", help="校验产物哈希")
    add_common(p)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("resume", help="打印接手信息")
    p.add_argument("--prompt", action="store_true")
    add_common(p)
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("reconcile", help="摘要最新会话")
    p.add_argument("--root", default="./sessions")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("close", help="验收后归档备份")
    p.add_argument(
        "--backup",
        nargs="?",
        const="",
        default=None,
        help="归档备份；不跟值时用 SESSION_BACKUP_DIR 或默认目录",
    )
    p.add_argument("--remote", default=None)
    p.add_argument("--force", action="store_true", help="跳过未通过的检查并归档（写入日志）")
    add_common(p)
    p.set_defaults(func=cmd_close)

    p = sub.add_parser("watch", help="自检并托管 watcher 模板（推荐替代手写 watcher）")
    p.add_argument("--log", required=True, help="被监视的日志文件")
    p.add_argument("--marker", required=True, help="终态标记字符串（唯一、非百分比）")
    p.add_argument("--regex", default=None, help="进度抓取正则；只匹配形状，禁止写死总量")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--window", type=int, default=7200)
    p.add_argument("--stale-limit", type=int, default=3)
    p.add_argument("--fail-on-stale", type=int, default=0, help=">0 时失速达到该次数以退出码 5 结束")
    p.add_argument("--pid", type=int, default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument("--no-selftest", action="store_true", help="跳过上岗自检（仅排查用）")
    p.add_argument("--selftest-only", action="store_true", help="只跑自检，不启动监视")
    add_common(p)
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("observe", help="观察者闹钟：睡到事件就退出并唤醒 agent（不判读）")
    p.add_argument("--session", default=None)
    p.add_argument("--log", required=False, default="")
    p.add_argument("--marker", default="", help="终态标记字符串（唯一、非百分比）")
    p.add_argument("--regex", default="", help="进度正则；只匹配形状，禁止写死总量")
    p.add_argument("--interval", type=float, default=30.0)
    p.add_argument("--checkpoint", type=float, default=2400.0, help="每 N 秒醒一次（默认 40 分钟）")
    p.add_argument("--window", type=float, default=14400.0, help="总窗口（默认 4h），到点退出 2")
    p.add_argument("--stale-limit", type=int, default=0, help=">0 且配 --exit-on-stale 时，进度不变 N 次退出 5")
    p.add_argument("--exit-on-stale", action="store_true")
    p.add_argument("--run-id", default=None)
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--no-selftest", action="store_true")
    p.set_defaults(func=cmd_observe)

    p = sub.add_parser("doctor", help="检查依赖工具")
    p.set_defaults(func=cmd_doctor)
    return ap


def main(argv: list[str]) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
