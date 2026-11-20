"""bsk CLI 封装。

只依赖 bsk 可执行文件；所有浏览器动作都通过它完成。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time


class BskError(RuntimeError):
    pass


def _which() -> str:
    p = shutil.which("bsk")
    if not p:
        raise BskError("找不到 bsk 命令。请先安装 browser-skill 并确保 bsk 在 PATH 中。")
    return p


def run(args, timeout=120, check=True) -> str:
    cmd = [_which()] + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode != 0:
        raise BskError(f"bsk {' '.join(args[:2])} 失败（{p.returncode}）：{(p.stderr or p.stdout).strip()[:400]}")
    return p.stdout


def status() -> dict:
    try:
        out = run(["status", "--json"], check=False)
        return json.loads(out)
    except Exception:
        out = run(["status"], check=False)
        return {"raw": out}


def browser_connected() -> tuple[bool, str]:
    st = status()
    if isinstance(st, dict) and "browsers" in st:
        n = st.get("browsers") or 0
        if isinstance(n, list):
            n = len(n)
        if n:
            return True, f"{n} 个浏览器已连接"
    raw = st.get("raw", "") if isinstance(st, dict) else str(st)
    if "browsers connected" in raw:
        try:
            n = int(raw.split("browsers connected")[1].split()[0])
            if n:
                return True, f"{n} 个浏览器已连接"
        except Exception:
            pass
    return False, "没有已连接的浏览器（请在 Chrome 中确认 browser-skill 扩展为绿色）"


def first_browser() -> str | None:
    """返回第一个已连接浏览器的实例 id。"""
    try:
        st = status()
        for k in ("browsers", "instances"):
            v = st.get(k)
            if isinstance(v, list) and v:
                b = v[0]
                return b.get("instance") or b.get("id") or b.get("instance_id")
    except Exception:
        pass
    return None


def session_start(browser: str | None = None) -> str:
    args = ["session", "start"]
    if browser:
        args += ["--browser", browser]
    out = run(args, check=False)
    sid = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if len(sid) != 4:
        raise BskError(f"无法开启 bsk 会话：{out.strip()[:200]}")
    return sid


def session_stop(sid: str):
    if sid:
        run(["session", "stop", sid], check=False)


def navigate(sid: str, url: str, timeout_ms: int = 60000):
    _action(["navigate", url, "--session", sid, "--wait-until", "domcontentloaded",
             f"--timeout={timeout_ms // 1000}s"], sid, timeout=timeout_ms // 1000 + 30)


def reload(sid: str):
    _action(["reload", "--session", sid], sid, timeout=60, attempts=2)


# ------------------------------------------------------------------
# browser-skill 0.5.0+ 兼容层
# 0.5.0 起默认为「人工协作」控制模型（target policy）：动作前需要
# cooperate sync 取得 observation，并随动作传入 --observation。
# 页面持续变化时可能报 document_changed，需要重新 sync 后重试。
# 旧版 CLI 没有 cooperate 命令时自动退回旧行为（不带 observation）。
# ------------------------------------------------------------------
_COOP_RETRY_CODES = {
    "cooperation_sync_required",
    "observation_required",
    "document_changed",
    "ref_not_found",
    "stale_observation",
    "control_context_invalid",
    # 人工触碰窗口会撤销进行中的动作；等人工停手后重新 sync 再试
    "human_intervention",
}


def _parse_error(out: str) -> dict | None:
    """bsk 出错时 stdout 是 JSON 错误对象（含 code）；成功时是普通文本或 {"ok": true,...}。"""
    s = out.strip()
    if not s.startswith("{"):
        return None
    try:
        env = json.loads(s)
    except Exception:
        return None
    if isinstance(env, dict) and env.get("code") and env.get("ok") is not True:
        return env
    return None


def _sync_observation(sid: str, attempts: int = 8) -> str | None:
    """cooperate sync 取得动作授权 observation；等页面 ready 后返回。

    sync 回复里的 ready 为 false 说明页面仍在被采集/占用（busy），
    立刻发动作会被判定 human_intervention 撤销，因此等 ready 再返回。
    旧版 CLI 或始终拿不到 observation 时返回 None（退回旧行为）。
    """
    for i in range(attempts):
        out = run(["cooperate", "sync", "--session", sid, "--settle", "--quiet", "--json"],
                  check=False, timeout=90)
        try:
            env = json.loads(out)
        except Exception:
            return None  # 旧版 CLI：没有 cooperate 命令
        obs = env.get("observation_id") if isinstance(env, dict) else None
        if obs:
            if env.get("ready") is False and i < attempts - 1:
                wait(1.5)   # 页面仍 busy：等一拍重新 sync
                continue
            wait(0.8)       # 让 sync 自身的采集落定，避免与动作撞车
            return str(obs)
        wait(2)
    return None


def _action(args: list[str], sid: str, timeout: int, attempts: int = 5) -> str:
    """执行一条浏览器动作：自动带 cooperate observation，状态失步时自动重试。

    人工活动（哪怕只是鼠标在窗口上移动）会撤销进行中的动作，
    重试间隔递增以吸收间断的人工活动。
    """
    last = ""
    for i in range(attempts):
        obs = _sync_observation(sid)
        full = list(args)
        if obs:
            full += ["--observation", obs]
        p = subprocess.run([_which()] + full, capture_output=True, text=True, timeout=timeout)
        out = p.stdout or ""
        err = _parse_error(out)
        if err is None and p.returncode == 0:
            return out
        last = (p.stderr or out).strip()
        code = (err or {}).get("code", "")
        reason = (err.get("data") or {}).get("reason", "") if isinstance(err, dict) else ""
        if code in _COOP_RETRY_CODES or reason in _COOP_RETRY_CODES:
            wait(10 * (i + 1) if "human_intervention" in (code, reason) else 1.5 * (i + 1))
            continue
        raise BskError(f"bsk {args[0]} 失败（{p.returncode}）：{last[:400]}")
    raise BskError(f"bsk {args[0]} 重试 {attempts} 次后仍失败：{last[:400]}")


def evaluate(sid: str, expr: str, timeout: int = 180):
    """执行 JS，返回解析后的值（尝试 JSON 解析，失败则返回原始字符串）。"""
    out = _action(["evaluate", expr, "--session", sid, "--json"], sid, timeout=timeout)
    try:
        env = json.loads(out)
    except Exception:
        return out.strip()
    if isinstance(env, dict):
        if env.get("ok") is False:
            raise BskError(f"页面脚本执行失败：{env}")
        v = env.get("value")
    else:
        v = env
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def wait(seconds: float):
    time.sleep(seconds)