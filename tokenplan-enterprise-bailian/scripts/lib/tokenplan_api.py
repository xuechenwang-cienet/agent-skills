"""百炼 Token Plan 控制台的数据获取。

原理（已在真实环境验证）：
  · 导出接口 UacSubmitUsageExportTask 的 params 不带 AccountId 时，导出整个组织；
  · 返回的 FileUrl 是 OSS 预签名链接，可用普通 HTTP 下载，不需要 cookie；
  · 请求需要 sec_token，它不在 cookie/localStorage 里，而是前端请求层拼到 POST body 上的，
    因此在页面里 hook XMLHttpRequest.send，触发任意一次数据刷新即可捕获；
  · 「用量统计」↔「订阅概览」是 SPA 路由，hook 不会因跳转而丢失。
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from . import bsk

API = "/data/api.json"

# ---- 安装 hook（幂等） ----
JS_HOOK = r"""
(function(){
  window.__tp_cap = window.__tp_cap || [];
  if (window.__tp_hooked) return 'already';
  var os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.send = function(d){
    try { if (d) window.__tp_cap.push(String(d)); } catch(e){}
    return os.apply(this, arguments);
  };
  var of = window.fetch;
  window.fetch = function(){
    try {
      var a = arguments;
      var b = a[1] && a[1].body;
      if (b) window.__tp_cap.push(typeof b === 'string' ? b : new URLSearchParams(b).toString());
    } catch(e){}
    return of.apply(this, arguments);
  };
  window.__tp_hooked = true;
  return 'hooked';
})()
"""

# ---- 触发一次数据刷新（两种模式都试，避免当前已处于其中一种状态而不发请求） ----
JS_TRIGGER = r"""
(async function(){
  var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  function clickText(txt){
    var nodes = [].slice.call(document.querySelectorAll('label,button,div,span'));
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.textContent.trim() === txt && n.offsetParent !== null) {
        n.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
        n.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
        n.click();
        return true;
      }
    }
    return false;
  }
  var before = window.__tp_cap.length;
  var tries = ['按天查询', '按小时查询'];
  for (var i = 0; i < tries.length; i++) {
    clickText(tries[i]);
    await sleep(2200);
    if (window.__tp_cap.length > before) return 'ok:' + tries[i];
  }
  return 'no-request';
})()
"""

JS_READ_CAP = r"""
(function(){
  var cap = window.__tp_cap || [];
  var token = null, account = null, actions = [];
  for (var i = 0; i < cap.length; i++) {
    var raw = cap[i], d = raw;
    try { d = decodeURIComponent(raw); } catch (e) { d = raw; }
    var m = d.match(/sec_token=([^&]+)/);
    if (m) token = m[1];
    var a = d.match(/"AccountId"\s*:\s*"(acc_[0-9a-f]+)"/);
    if (a) account = a[1];
    var act = d.match(/action=([A-Za-z]+)/);
    if (act && actions.indexOf(act[1]) < 0) actions.push(act[1]);
  }
  return JSON.stringify({token: token, account: account, actions: actions});
})()
"""

# ---- 在页面里调用 API ----
JS_CALL = r"""
(async function(){
  var args = %s;
  var out = {};
  for (var i = 0; i < args.calls.length; i++) {
    var c = args.calls[i];
    var body = new URLSearchParams({
      product: 'ModelStudio',
      action: c.action,
      params: JSON.stringify(c.params),
      sec_token: args.token,
      collina: '',
      region: ''
    });
    try {
      var r = await fetch('/data/api.json', {method:'POST', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body: body});
      out[c.action] = await r.json();
    } catch (e) {
      out[c.action] = {error: String(e)};
    }
  }
  return JSON.stringify(out);
})()
"""


class TokenPlanClient:
    def __init__(self, cfg, session: str, log=print):
        self.cfg = cfg
        self.sid = session
        self.log = log
        self.token = None
        self.account = None

    # ---------------- 基础设施 ----------------
    def open_usage(self):
        bsk.navigate(self.sid, self.cfg.url("usage"))
        bsk.wait(6)

    def open_overview(self):
        bsk.navigate(self.sid, self.cfg.url("overview"))
        bsk.wait(7)

    def _hook(self):
        return bsk.evaluate(self.sid, JS_HOOK)

    def capture(self, trigger: bool = True) -> dict:
        """确保拿到 sec_token（和当前的 AccountId）。"""
        if self.token and self.account:
            return {"token": self.token, "account": self.account}
        self._hook()
        if trigger:
            r = bsk.evaluate(self.sid, JS_TRIGGER)
            if isinstance(r, str) and r.startswith("no-request"):
                self.log("  ! 触发刷新未产生请求，尝试直接读取已捕获内容")
        cap = bsk.evaluate(self.sid, JS_READ_CAP) or {}
        self.token = cap.get("token") or self.token
        self.account = cap.get("account") or self.account
        if not self.token:
            raise RuntimeError("未能捕获 sec_token（页面可能未登录或结构变化）")
        return {"token": self.token, "account": self.account, "actions": cap.get("actions")}

    # ---------------- 通用 API 调用 ----------------
    def call(self, calls: list) -> dict:
        self.capture(trigger=False)
        expr = JS_CALL % json.dumps({"token": self.token, "calls": calls}, ensure_ascii=False)
        res = bsk.evaluate(self.sid, expr, timeout=240)
        if not isinstance(res, dict):
            raise RuntimeError(f"API 返回解析失败：{str(res)[:300]}")
        return res

    @staticmethod
    def unwrap(resp: dict):
        """剥掉 {requestId, data:{Data,Success}} 外壳。"""
        if not isinstance(resp, dict):
            return None
        d = resp.get("data")
        if isinstance(d, dict) and "Data" in d:
            return d["Data"]
        return d

    # ---------------- 导出明细 ----------------
    # 导出接口单次上限 100,000 行，超过会返回
    #   {"Status":"FAILED","ErrorMessage":"导出失败: 导出数据量超过限制（N > 100000），请缩小筛选范围"}
    # 因此按日期二分递归，直到每一段都在限制内，最后合并去重。
    EXPORT_LIMIT_HINT = ("超过限制", "> 100000", ">100000")

    def export_usage(self, start: str, end: str, out_dir: str) -> dict:
        parts = []
        self._export_recursive(start, end, out_dir, parts, depth=0)

        path = os.path.join(out_dir, "usage_detail.csv")
        n = self._merge_csv(parts, path)
        for p in parts:
            try:
                os.remove(p)
            except OSError:
                pass
        return {"file": path, "records": n, "filename": os.path.basename(path),
                "range": [start, end], "parts": len(parts)}

    def _export_recursive(self, start: str, end: str, out_dir: str, parts: list, depth: int):
        import datetime as _dt

        params = {
            "TimeGranularity": self.cfg.export["granularity"],
            "StartDate": start,
            "EndDate": end,
            "Locale": "zh-CN",
        }
        indent = "  " * (depth + 1)
        self.log(f"{indent}提交导出 {start[:10]} ~ {end[:10]}")
        r = self.call([{"action": "UacSubmitUsageExportTask", "params": params}])
        task = self.unwrap(r.get("UacSubmitUsageExportTask")) or {}
        tid = task if isinstance(task, str) else task.get("Data") or task.get("TaskId")
        if not tid:
            raise RuntimeError(f"导出任务提交失败：{json.dumps(r, ensure_ascii=False)[:400]}")

        info = self.poll_task(tid)
        status = (info.get("Status") or "").upper()

        if status == "FAILED":
            msg = info.get("ErrorMessage") or ""
            if any(h in msg for h in self.EXPORT_LIMIT_HINT) and depth < 8:
                a = _dt.datetime.fromisoformat(start)
                b = _dt.datetime.fromisoformat(end)
                days = (b - a).days
                if days < 2:
                    raise RuntimeError(f"单日导出仍超过限制：{msg}")
                mid = a + _dt.timedelta(days=days // 2)
                self.log(f"{indent}超出上限，二分：{a.date()} ~ {mid.date()} / {mid.date()} ~ {b.date()}")
                self._export_recursive(start, mid.strftime("%Y-%m-%d %H:%M:%S"), out_dir, parts, depth + 1)
                self._export_recursive(mid.strftime("%Y-%m-%d %H:%M:%S"), end, out_dir, parts, depth + 1)
                return
            raise RuntimeError(f"导出失败：{msg or info}")

        url = info.get("FileUrl")
        if not url:
            raise RuntimeError(f"导出任务未返回 FileUrl：{info}")
        n = info.get("RecordCount")
        part = os.path.join(out_dir, f"part{depth}_{len(parts):02d}.csv")
        self.download(url, part)
        parts.append(part)
        self.log(f"{indent}✓ {n:,} 条" if isinstance(n, int) else f"{indent}✓ 已下载")

    @staticmethod
    def _merge_csv(parts: list, out_path: str) -> int:
        import csv as _csv

        if len(parts) == 1:
            os.replace(parts[0], out_path)
            with open(out_path, encoding="utf-8-sig") as f:
                return max(sum(1 for _ in f) - 1, 0)

        seen, rows, header = set(), [], None
        for p in parts:
            with open(p, encoding="utf-8-sig") as f:
                rd = _csv.reader(f)
                h = next(rd, None)
                if header is None:
                    header = h
                for row in rd:
                    key = "\x1f".join(row)
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append(row)
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = _csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
        return len(rows)

    def poll_task(self, tid: int | str) -> dict:
        interval = float(self.cfg.export.get("poll_interval_s", 1.5))
        timeout = float(self.cfg.export.get("poll_timeout_s", 120))
        waited = 0.0
        while waited <= timeout:
            r = self.call([{"action": "UacGetUsageExportTask",
                            "params": {"TaskId": tid, "Locale": "zh-CN"}}])
            d = self.unwrap(r.get("UacGetUsageExportTask")) or {}
            if isinstance(d, dict) and d.get("Status") and d["Status"] != "RUNNING":
                return d
            bsk.wait(interval)
            waited += interval
        raise RuntimeError(f"导出任务超时（>{timeout}s）")

    @staticmethod
    def download(url: str, path: str):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
        if os.path.getsize(path) < 1024:
            raise RuntimeError(f"下载文件异常：{os.path.getsize(path)} 字节")

    # ---------------- 订阅 / 席位 / 加油包 ----------------
    def fetch_subscription(self) -> dict:
        # 订阅页的请求里带 AccountId，先 SPA 走一遍用量统计 → 订阅概览 以捕获它
        self.open_overview()
        self._hook()
        bsk.evaluate(self.sid, r"""
        (async function(){
          var sleep = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
          function clickText(txt){
            var nodes = [].slice.call(document.querySelectorAll('a,div,span,button'));
            for (var i=0;i<nodes.length;i++){ var n=nodes[i];
              if (n.textContent.trim()===txt && n.offsetParent!==null){
                n.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}));
                n.click(); return true; } }
            return false;
          }
          window.__tp_cap = window.__tp_cap || [];
          clickText('用量统计'); await sleep(2500);
          clickText('订阅概览'); await sleep(3500);
          return 'ok';
        })()
        """)
        cap = bsk.evaluate(self.sid, JS_READ_CAP) or {}
        self.token = cap.get("token") or self.token
        self.account = cap.get("account") or self.account
        if not (self.token and self.account):
            raise RuntimeError("未能捕获 sec_token / AccountId")

        org = self.cfg.org_id
        r = self.call([
            {"action": "QuerySubscription", "params": {"OrgId": org, "Locale": "zh-CN", "AccountId": self.account}},
            {"action": "QuerySubscriptionPackInfo", "params": {"OrgId": org, "Locale": "zh-CN", "AccountId": self.account}},
            {"action": "UacGetOrgMemberStatsWithSeat", "params": {"OrgId": org, "Locale": "zh-CN"}},
        ])
        sub = self.unwrap(r.get("QuerySubscription")) or {}
        pack = self.unwrap(r.get("QuerySubscriptionPackInfo")) or {}
        mem = self.unwrap(r.get("UacGetOrgMemberStatsWithSeat")) or {}

        seats = []
        for it in (sub.get("Items") or []):
            seats.append({
                "type": it.get("SeatType"),
                "total_seats": it.get("TotalSeats"),
                "assigned": it.get("AssignedSeats"),
                "cap": it.get("SeatCredits"),
                "remaining": it.get("SeatRemainingCredits"),
                "used": (it.get("SeatCredits") or 0) - (it.get("SeatRemainingCredits") or 0),
            })
        out = {
            "fetched_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"),
            "start": sub.get("SubscriptionStartTime"),
            "end": sub.get("SubscriptionEndTime"),
            "refresh": (sub.get("Items") or [{}])[0].get("SeatRefreshTime"),
            "seats": seats,
            "pack": {
                "count": pack.get("TotalCount"),
                "cap": pack.get("PackCredits"),
                "remaining": pack.get("PackSurplusCredits"),
                "used": (pack.get("PackCredits") or 0) - (pack.get("PackSurplusCredits") or 0),
                "nearest_expire": pack.get("NearestExpireDate"),
            },
            "org": {
                "total_members": mem.get("TotalMemberCount"),
                "seated": mem.get("SeatedMemberCount"),
                "unseated": mem.get("UnseatedMemberCount"),
            },
            "account_id": self.account,
        }
        return out