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
    run(["navigate", url, "--session", sid, "--wait-until", "domcontentloaded",
         f"--timeout={timeout_ms // 1000}s"], timeout=timeout_ms // 1000 + 30)


def reload(sid: str):
    run(["reload", "--session", sid], check=False)


def evaluate(sid: str, expr: str, timeout: int = 180):
    """执行 JS，返回解析后的值（尝试 JSON 解析，失败则返回原始字符串）。"""
    out = run(["evaluate", expr, "--session", sid, "--json"], timeout=timeout)
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