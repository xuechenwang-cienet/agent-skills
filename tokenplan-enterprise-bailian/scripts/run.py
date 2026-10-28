#!/usr/bin/env python3
"""Token Plan 用量分析 — 唯一入口。

    python3 scripts/run.py                       # 交互：确认后可跑
    python3 scripts/run.py --non-interactive     # 后台：配置齐全即静默跑
    python3 scripts/run.py --month 2026-09       # 指定报表月份
    python3 scripts/run.py --from s3             # 复用已有 CSV，只重算+重渲染
    python3 scripts/run.py --tag evening         # 输出目录加后缀
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from lib import bsk  # noqa: E402
from lib.config import Config  # noqa: E402
from lib.calendar_cn import Calendar  # noqa: E402

import steps.s0_preflight as s0  # noqa: E402
import steps.s1_usage as s1  # noqa: E402
import steps.s2_subscription as s2  # noqa: E402
import steps.s3_analyze as s3  # noqa: E402
import steps.s4_render as s4  # noqa: E402
import steps.s5_manifest as s5  # noqa: E402

EXIT_OK, EXIT_CONFIG, EXIT_BROWSER, EXIT_DATA, EXIT_RENDER = 0, 2, 3, 4, 5


class Logger:
    def __init__(self, path=None):
        self.path = path
        self.fh = open(path, "a", encoding="utf-8") if path else None
        if self.fh:
            self.fh.write("\n" + "=" * 68 + "\n")

    def __call__(self, msg=""):
        line = str(msg)
        print(line, flush=True)
        if self.fh:
            self.fh.write(line + "\n")
            self.fh.flush()

    def close(self):
        if self.fh:
            self.fh.close()


def parse_month(s):
    if not s:
        t = dt.date.today()
        return (t.year, t.month)
    y, m = s.split("-")[:2]
    return (int(y), int(m))


def main():
    ap = argparse.ArgumentParser(description="Token Plan 用量分析")
    ap.add_argument("--month", help="报表月份 YYYY-MM（默认当前月）")
    ap.add_argument("--non-interactive", action="store_true", help="后台模式：不做任何交互")
    ap.add_argument("--from", dest="from_step", default="s1",
                    choices=["s1", "s2", "s3", "s4"], help="从哪一步开始（默认 s1）")
    ap.add_argument("--tag", default="", help="输出目录后缀，如 evening")
    ap.add_argument("--no-fetch", action="store_true", help="等价于 --from s3")
    a = ap.parse_args()
    if a.no_fetch:
        a.from_step = "s3"

    month = parse_month(a.month)
    a.month = month          # s0 需要 (year, month) 元组
    run_date = dt.date.today().isoformat()
    out_name = run_date + (f"-{a.tag}" if a.tag else "")
    out_dir = os.path.join(ROOT, "output", out_name)
    os.makedirs(os.path.join(ROOT, "logs"), exist_ok=True)
    log = Logger(os.path.join(ROOT, "logs", f"{out_name}.log"))

    t0 = dt.datetime.now()
    log("═" * 68)
    log(f"Token Plan 用量分析  ·  报表月份 {month[0]}-{month[1]:02d}  ·  {run_date}")
    log(f"模式 {'后台（非交互）' if a.non_interactive else '交互'}  ·  起始步骤 {a.from_step}")
    log(f"输出 {out_dir}")

    cfg = Config(ROOT)
    session = None
    try:
        # ---------- s0 ----------
        pre = s0.run(cfg, a, log)
        if not pre.get("ok"):
            log(f"✗ 预检失败，退出码 {pre.get('exit', EXIT_CONFIG)}")
            return pre.get("exit", EXIT_CONFIG)

        os.makedirs(out_dir, exist_ok=True)

        # ---------- s1 / s2 ----------
        usage = sub = None
        if a.from_step in ("s1", "s2"):
            session = bsk.session_start(bsk.first_browser())
            log(f"  · bsk 会话 {session}")

        if a.from_step == "s1":
            usage = s1.run(cfg, session, month, out_dir, log)
        if a.from_step in ("s1", "s2"):
            sub = s2.run(cfg, session, out_dir, log)

        if session:
            bsk.session_stop(session)
            session = None

        csv_path = os.path.join(out_dir, "raw", "usage_detail.csv")
        sub_path = os.path.join(out_dir, "raw", "subscription.json")
        if a.from_step in ("s3", "s4"):
            if not os.path.exists(csv_path):
                log(f"✗ 找不到 {csv_path}，请先跑 s1")
                return EXIT_DATA
            sub = json.load(open(sub_path, encoding="utf-8"))

        # ---------- s3 ----------
        if a.from_step in ("s1", "s2", "s3"):
            A = s3.run(cfg, csv_path, sub, month, out_dir, log)
        else:
            a_path = os.path.join(out_dir, "data", "analysis.json")
            # analysis.json 缺失或为旧版本产物（无行为画像字段）→ 用本地明细重跑 s3
            need_s3 = True
            if os.path.exists(a_path):
                try:
                    A = json.load(open(a_path, encoding="utf-8"))
                    need_s3 = not A.get("behavior") or not A["people"] or "profile" not in A["people"][0]
                except (json.JSONDecodeError, KeyError, IndexError):
                    need_s3 = True
            if need_s3:
                log("· analysis.json " + ("缺失" if not os.path.exists(a_path) else "缺少行为画像字段")
                    + "，用本地明细重跑 s3 …")
                A = s3.run(cfg, csv_path, sub, month, out_dir, log)

        # ---------- s4 ----------
        files = s4.run(cfg, A, out_dir, log)

        # ---------- s5 ----------
        manifest = s5.run(cfg, A, files, out_dir, log,
                          extra={"usage": usage, "session": session})

        dur = (dt.datetime.now() - t0).total_seconds()
        log("═" * 68)
        log(f"{'✓ 完成' if manifest['ok'] else '⚠ 完成（有失败项）'}  用时 {dur:.0f}s  ·  {out_dir}")
        log(f"  部门报告 token_credits_report.html")
        log(f"  组报告  {len(A['groups'])} 份")
        return EXIT_OK if manifest["ok"] else EXIT_DATA

    except bsk.BskError as e:
        log(f"✗ 浏览器错误：{e}")
        return EXIT_BROWSER
    except RuntimeError as e:
        log(f"✗ 数据/流程错误：{e}")
        log(traceback.format_exc())
        return EXIT_DATA
    except Exception as e:
        log(f"✗ 未预期错误：{e}")
        log(traceback.format_exc())
        return EXIT_RENDER
    finally:
        if session:
            bsk.session_stop(session)
        log.close()


if __name__ == "__main__":
    sys.exit(main())