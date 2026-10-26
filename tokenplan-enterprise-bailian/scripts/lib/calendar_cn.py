"""中国大陆工作日 / 节假日计算。

规则：
    workday  = 周一~周五 且 不是法定假日
    workday += 调休上班的周末
    holiday  = 法定假日（不论星期几）
    weekend  = 其余周六周日
"""
from __future__ import annotations

from datetime import date, timedelta


class Calendar:
    def __init__(self, cfg, year: int):
        self.year = year
        cal = cfg.calendar_for(year)
        self.holidays = {d for v in (cal.get("holidays") or {}).values() for d in v}
        self.makeups = set(cal.get("makeup_workdays") or [])
        self.verified_months = list(cal.get("verified_months") or [])
        self.holiday_names = {}
        for name, days in (cal.get("holidays") or {}).items():
            for d in days:
                self.holiday_names[d] = name

    def kind(self, d: date) -> str:
        s = d.isoformat()
        if s in self.holidays:
            return "holiday"
        if s in self.makeups:
            return "workday"
        return "workday" if d.weekday() < 5 else "weekend"

    def is_workday(self, d: date) -> bool:
        return self.kind(d) == "workday"

    def days(self, start: date, end: date) -> list[date]:
        out, d = [], start
        while d <= end:
            out.append(d)
            d += timedelta(days=1)
        return out

    def month_range(self, year: int, month: int):
        first = date(year, month, 1)
        nxt = date(year + (month == 12), (month % 12) + 1, 1)
        return first, nxt - timedelta(days=1)

    def tally(self, start: date, end: date) -> dict:
        t = {"workday": 0, "weekend": 0, "holiday": 0}
        for d in self.days(start, end):
            t[self.kind(d)] += 1
        t["total"] = sum(t.values())
        return t

    def month_tally(self, year: int, month: int) -> dict:
        a, b = self.month_range(year, month)
        return self.tally(a, b)

    def holiday_list(self, year: int, month: int) -> list:
        a, b = self.month_range(year, month)
        return [(d.isoformat(), self.holiday_names.get(d.isoformat(), "假日"))
                for d in self.days(a, b) if self.kind(d) == "holiday"]

    def makeup_list(self, year: int, month: int) -> list:
        a, b = self.month_range(year, month)
        return [d.isoformat() for d in self.days(a, b) if self.kind(d) == "workday" and d.weekday() >= 5]

    def is_verified(self, year: int, month: int) -> bool:
        return f"{year:04d}-{month:02d}" in self.verified_months


def next_month(year: int, month: int):
    return (year + (month == 12), (month % 12) + 1)