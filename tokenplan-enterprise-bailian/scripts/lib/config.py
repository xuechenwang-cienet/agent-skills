"""配置加载 + 确认状态机。

设计要点：
  · 配置与代码分离，全部在 config/ 下
  · 四项确认（web_root / roster / pricing / calendar）各自记录「时间戳 + 内容哈希」
  · 文件内容变化 → 哈希变化 → 该确认项立即失效（与 TTL 无关）
  · 后台模式：四项都有效才继续，否则退出码 2
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import yaml

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(BASE, "config")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")

CONFIRM_KEYS = ("web_root", "roster", "pricing", "calendar")
KEY_LABEL = {
    "web_root": "Web root / Org ID",
    "roster": "人员名册",
    "pricing": "价格表",
    "calendar": "节假日 / 工作日",
}


def _sha(*parts) -> str:
    h = hashlib.sha256()
    for p in parts:
        if isinstance(p, bytes):
            h.update(p)
        else:
            h.update(str(p).encode("utf-8"))
        h.update(b"\x00")
    return "sha256:" + h.hexdigest()[:32]


@dataclass
class Member:
    hrid: str
    name_en: str
    name_zh: str
    dept: str
    pcode: str
    email: str
    team_owner: str
    seat_type: str
    seat_credits: int
    sharing_with: str
    accounts: list = field(default_factory=list)       # Bailian 显示名
    account_ids: list = field(default_factory=list)    # acc_xxx，运行时按此匹配
    active: bool = True

    @property
    def premium(self) -> bool:
        return self.seat_type == "premium"

    @property
    def label(self) -> str:
        """展示名：共享席位显示两个人。"""
        return f"{self.name_zh} / {self.sharing_with}" if self.sharing_with else self.name_zh


class Config:
    def __init__(self, base: str = BASE):
        self.base = base
        self.dir = os.path.join(base, "config")
        for name, sample in (("config.yaml", "config.sample.yaml"), ("members.csv", "members.sample.csv")):
            if not os.path.exists(os.path.join(self.dir, name)):
                raise SystemExit(
                    f"缺少 config/{name}。\n"
                    f"  cp config/{sample} config/{name}\n"
                    f"然后按注释修改（这两个文件已被 .gitignore 忽略，不会进版本库）。")
        self.raw = yaml.safe_load(open(os.path.join(self.dir, "config.yaml"), encoding="utf-8"))
        self.holidays_raw = yaml.safe_load(open(os.path.join(self.dir, "holidays.yaml"), encoding="utf-8"))
        self.members = self._load_members()
        self.state = self._load_state()

    # ---------------- basic blocks ----------------
    @property
    def web(self):        return self.raw["web"]
    @property
    def export(self):     return self.raw["export"]
    @property
    def pricing(self):    return self.raw["pricing"]
    @property
    def forecast(self):   return self.raw["forecast"]
    @property
    def output(self):     return self.raw["output"]
    @property
    def notify(self):     return self.raw.get("notify", {})
    @property
    def ttl(self):        return self.raw["confirmation"]["ttl_days"]

    @property
    def root(self) -> str:   return self.web["root"].rstrip("/")
    @property
    def org_id(self) -> str: return self.web["org_id"]

    def url(self, key: str) -> str:
        return self.root + self.web["paths"][key].format(org_id=self.org_id)

    # ---------------- members ----------------
    def _load_members(self) -> list[Member]:
        path = os.path.join(self.dir, "members.csv")
        out = []
        with open(path, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if (r.get("active") or "true").strip().lower() in ("false", "0", "no"):
                    continue
                accs = [a.strip() for a in (r.get("bailian_accounts") or "").split(";") if a.strip()]
                aids = [a.strip() for a in (r.get("bailian_account_ids") or "").split(";") if a.strip()]
                out.append(Member(
                    hrid=(r.get("hrid") or "").strip(),
                    name_en=(r.get("name_en") or "").strip(),
                    name_zh=(r.get("name_zh") or "").strip(),
                    dept=(r.get("dept") or "—").strip(),
                    pcode=(r.get("pcode") or "—").strip(),
                    email=(r.get("email") or "").strip(),
                    team_owner=(r.get("team_owner") or "").strip(),
                    seat_type=(r.get("seat_type") or "standard").strip(),
                    seat_credits=int(float(r.get("seat_credits") or 25000)),
                    sharing_with=(r.get("sharing_with") or "").strip(),
                    accounts=accs,
                    account_ids=aids,
                ))
        return out

    def member_by_owner(self):
        out = {}
        for m in self.members:
            out.setdefault(m.team_owner, []).append(m)
        return out

    # ---------------- hashes ----------------
    def hashes(self) -> dict:
        return {
            "web_root": _sha(self.root, self.org_id),
            "roster": _sha(open(os.path.join(self.dir, "members.csv"), "rb").read()),
            "pricing": _sha(json.dumps(self.pricing, sort_keys=True, ensure_ascii=False, default=str)),
            "calendar": _sha(open(os.path.join(self.dir, "holidays.yaml"), "rb").read()),
        }

    # ---------------- state ----------------
    def _load_state(self) -> dict:
        if os.path.exists(STATE_FILE):
            try:
                return json.load(open(STATE_FILE, encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_state(self):
        os.makedirs(self.dir, exist_ok=True)
        json.dump(self.state, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def confirm(self, key: str, by: str = ""):
        self.state.setdefault("confirmed", {})[key] = {
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "by": by,
            "hash": self.hashes()[key],
        }
        self.save_state()

    def confirmation_status(self, now: datetime | None = None) -> list[dict]:
        now = now or datetime.now().astimezone()
        h = self.hashes()
        out = []
        for key in CONFIRM_KEYS:
            rec = (self.state.get("confirmed") or {}).get(key)
            ttl = int(self.ttl[key])
            if not rec:
                out.append(dict(key=key, ok=False, reason="从未确认", age_days=None, ttl=ttl))
                continue
            if rec.get("hash") != h[key]:
                out.append(dict(key=key, ok=False, reason="配置文件已变更，需重新确认", age_days=None, ttl=ttl))
                continue
            try:
                at = datetime.fromisoformat(rec["at"])
            except Exception:
                out.append(dict(key=key, ok=False, reason="确认时间无法解析", age_days=None, ttl=ttl))
                continue
            age = (now - at).total_seconds() / 86400
            if age > ttl:
                out.append(dict(key=key, ok=False, reason=f"确认已过期（{age:.0f} 天 > {ttl} 天）", age_days=age, ttl=ttl))
                continue
            out.append(dict(key=key, ok=True, reason=f"{age:.0f} 天前确认", age_days=age, ttl=ttl, by=rec.get("by", ""), at=rec["at"]))
        return out

    # ---------------- calendar ----------------
    def calendar_for(self, year: int) -> dict:
        return (self.holidays_raw.get("years") or {}).get(year) or {}

    def verified_months(self, year: int) -> list:
        return list(self.calendar_for(year).get("verified_months") or [])