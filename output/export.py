"""导出与分享：iCal / JSON / 自然语言解读。"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional
import json


def export_ical(results: list[dict], event_name: str = "黄道吉日") -> str:
    """将推荐结果导出为 iCal 字符串，可保存为 .ics 文件。"""
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//协纪 黄历择吉工具//ZH//",
        "CALSCALE:GREGORIAN",
    ]
    for i, r in enumerate(results):
        d = r["date"]
        a = r["almanac"]
        uid = f"huangli-{d.isoformat()}-{i}@local"
        dtstart = d.strftime("%Y%m%d")
        dtend = (d + timedelta(days=1)).strftime("%Y%m%d")
        summary = f"【{r['verdict']} {r['score']}/100】{event_name} 吉日"
        desc_lines = [
            f"农历: {a.lunar_str}",
            f"干支: {a.ganzhi_year} {a.ganzhi_month} {a.ganzhi_day}",
            f"建除: {a.jianchu}  黄黑道: {a.tianshen}({a.tianshen_type})  星宿: {a.xiu}({a.xiu_luck})",
            f"宜: {' '.join(a.yi)}",
            f"忌: {' '.join(a.ji)}",
            f"冲煞: {a.chong_desc} 煞{a.sha}",
            f"喜神方位: {a.xi_shen_fang}  财神方位: {a.cai_shen_fang}",
        ]
        desc = "\\n".join(desc_lines)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{dtstart}",
            f"DTEND;VALUE=DATE:{dtend}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def export_json(results: list[dict]) -> str:
    """将推荐结果导出为 JSON。"""
    payload = []
    for r in results:
        a = r["almanac"]
        payload.append({
            "date": r["date"].isoformat(),
            "score": r["score"],
            "verdict": r["verdict"],
            "lunar": a.lunar_str,
            "ganzhi": {"year": a.ganzhi_year, "month": a.ganzhi_month, "day": a.ganzhi_day},
            "jianchu": a.jianchu,
            "tianshen": {"name": a.tianshen, "type": a.tianshen_type, "luck": a.tianshen_luck},
            "xiu": {"name": a.xiu, "luck": a.xiu_luck},
            "yi": a.yi,
            "ji": a.ji,
            "jishen": a.jishen,
            "xiongsha": a.xiongsha,
            "chong": a.chong_desc,
            "sha": a.sha,
            "directions": {"xi": a.xi_shen_fang, "cai": a.cai_shen_fang},
            "reasons": r["reasons"],
            "taboos": list(r.get("taboos", {}).keys()),
        })
    return json.dumps(payload, ensure_ascii=False, indent=2)


def natural_language_summary(result: dict) -> str:
    """把单日评分明细翻译成一段自然语言（规则式，无需 LLM）。"""
    a = result["almanac"]
    score = result["score"]
    v = result["verdict"]
    reasons = result["reasons"]
    pos = [r for r in reasons if r.startswith("+")]
    neg = [r for r in reasons if r.startswith("-")]
    taboos = list(result.get("taboos", {}).keys())

    parts = []
    parts.append(f"📅 **{a.solar_date.isoformat()}（{a.lunar_str}）** —— 综合评分 **{score}/100，{v}**。")

    if a.tianshen in {"青龙", "明堂", "金匮", "天德", "玉堂", "司命"}:
        parts.append(f"当日为**黄道日**（{a.tianshen}当值），建除值【{a.jianchu}】。")
    else:
        parts.append(f"当日为**黑道日**（{a.tianshen}当值），建除值【{a.jianchu}】。")

    if a.yi:
        parts.append(f"通书宜：**{'、'.join(a.yi[:6])}**。")
    if a.ji:
        parts.append(f"通书忌：**{'、'.join(a.ji[:6])}**。")

    parts.append(f"今日冲【{a.chong_desc}】，煞方在{a.sha}，建议属此生肖者回避。")
    parts.append(f"喜神位居【{a.xi_shen_fang}】，财神位居【{a.cai_shen_fang}】。")

    if taboos:
        parts.append(f"⚠️ 命中传统凶日：{'、'.join(taboos)}。")

    if v.startswith("大凶"):
        parts.append("**结论：本日不宜，请另择吉日。**")
    elif "上吉" in v:
        parts.append("**结论：诸事皆宜，可放心进行。**")
    elif "吉" in v:
        parts.append("**结论：吉中带平，常事可行；如属大事，可再求更佳之日。**")
    else:
        parts.append("**结论：中平之日，无大碍亦无大助。**")

    return "\n\n".join(parts)
