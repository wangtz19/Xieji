"""节令与特殊日历：节气精确时刻 / 三伏数九 / 月相 / 法定节假日。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from lunar_python import Solar


JIEQI_ORDER = [
    "立春", "雨水", "惊蛰", "春分", "清明", "谷雨",
    "立夏", "小满", "芒种", "夏至", "小暑", "大暑",
    "立秋", "处暑", "白露", "秋分", "寒露", "霜降",
    "立冬", "小雪", "大雪", "冬至", "小寒", "大寒",
]


@dataclass
class JieQiInfo:
    name: str
    moment: datetime  # 精确时刻
    days_to: int      # 距今天数（负数=已过）


def get_jieqi_table(year: int) -> list[JieQiInfo]:
    """返回该公历年的 24 节气精确时刻。"""
    solar = Solar.fromYmd(year, 6, 15)
    l = solar.getLunar()
    raw = l.getJieQiTable()
    today = date.today()
    out = []
    for name in JIEQI_ORDER:
        jq = raw.get(name)
        if not jq:
            # 可能落在前后一年的拼音 key 上
            for k in ["LI_CHUN", "YU_SHUI", "JING_ZHE", "CHUN_FEN",
                      "QING_MING", "GU_YU", "LI_XIA", "XIAO_MAN",
                      "MANG_ZHONG", "XIA_ZHI", "XIAO_SHU", "DA_SHU",
                      "LI_QIU", "CHU_SHU", "BAI_LU", "QIU_FEN",
                      "HAN_LU", "SHUANG_JIANG", "LI_DONG", "XIAO_XUE",
                      "DA_XUE", "DONG_ZHI", "XIAO_HAN", "DA_HAN"]:
                if raw.get(k):
                    pass
            continue
        moment = datetime(
            jq.getYear(), jq.getMonth(), jq.getDay(),
            jq.getHour(), jq.getMinute(), jq.getSecond(),
        )
        out.append(JieQiInfo(
            name=name, moment=moment,
            days_to=(moment.date() - today).days,
        ))
    return out


def next_jieqi(from_date: date) -> Optional[JieQiInfo]:
    """从指定日期算起，下一个节气。"""
    qs = get_jieqi_table(from_date.year) + get_jieqi_table(from_date.year + 1)
    for jq in qs:
        if jq.moment.date() >= from_date:
            return JieQiInfo(jq.name, jq.moment, (jq.moment.date() - from_date).days)
    return None


def current_jieqi_phase(d: date) -> dict:
    """当前节气期信息。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()
    cur = l.getCurrentJieQi()
    next_jq = next_jieqi(d)
    return {
        "current": cur.getName() if cur else "",
        "next": next_jq.name if next_jq else "",
        "next_moment": next_jq.moment if next_jq else None,
        "days_to_next": next_jq.days_to if next_jq else None,
    }


def san_fu(year: int) -> dict:
    """三伏（夏季三个庚日）。

    初伏：夏至后第三个庚日
    中伏：夏至后第四个庚日（或第五，跨立秋）
    末伏：立秋后第一个庚日
    """
    solar = Solar.fromYmd(year, 6, 21)
    l = solar.getLunar()
    jq_table = l.getJieQiTable()
    xia_zhi_s = jq_table.get("夏至")
    li_qiu_s = jq_table.get("立秋")
    if not xia_zhi_s or not li_qiu_s:
        return {}
    xia_zhi = date(xia_zhi_s.getYear(), xia_zhi_s.getMonth(), xia_zhi_s.getDay())
    li_qiu = date(li_qiu_s.getYear(), li_qiu_s.getMonth(), li_qiu_s.getDay())

    def find_geng_after(base: date, n: int) -> date:
        d = base
        count = 0
        while count < n:
            d += timedelta(days=1)
            ss = Solar.fromYmd(d.year, d.month, d.day).getLunar()
            if ss.getDayGan() == "庚":
                count += 1
        return d

    chu_fu = find_geng_after(xia_zhi - timedelta(days=1), 3)
    zhong_fu = find_geng_after(xia_zhi - timedelta(days=1), 4)
    mo_fu = find_geng_after(li_qiu - timedelta(days=1), 1)
    # 中伏长度：末伏 - 中伏（10 或 20 天）
    zhong_fu_days = (mo_fu - zhong_fu).days
    return {
        "初伏": (chu_fu, chu_fu + timedelta(days=9), 10),
        "中伏": (zhong_fu, mo_fu - timedelta(days=1), zhong_fu_days),
        "末伏": (mo_fu, mo_fu + timedelta(days=9), 10),
    }


def shu_jiu(year: int) -> list[tuple[str, date, date]]:
    """数九：冬至开始九个九。"""
    solar = Solar.fromYmd(year, 12, 22)
    l = solar.getLunar()
    dz = l.getJieQiTable().get("冬至")
    if not dz:
        return []
    start = date(dz.getYear(), dz.getMonth(), dz.getDay())
    names = ["一九", "二九", "三九", "四九", "五九", "六九", "七九", "八九", "九九"]
    out = []
    for i, n in enumerate(names):
        s = start + timedelta(days=i * 9)
        e = s + timedelta(days=8)
        out.append((n, s, e))
    return out


def moon_phase(d: date) -> str:
    """月相（朔/上弦/望/下弦 + 既朔等中间相）。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()
    return l.getYueXiang() or ""


# === 法定节假日 (2024-2027 简表) ===
PUBLIC_HOLIDAYS = {
    # 元旦
    date(2026, 1, 1): "元旦",
    # 春节
    date(2026, 2, 17): "春节·除夕", date(2026, 2, 18): "春节·初一",
    date(2026, 2, 19): "春节·初二", date(2026, 2, 20): "春节·初三",
    # 清明
    date(2026, 4, 4): "清明", date(2026, 4, 5): "清明", date(2026, 4, 6): "清明",
    # 劳动节
    date(2026, 5, 1): "劳动节", date(2026, 5, 2): "劳动节", date(2026, 5, 3): "劳动节",
    # 端午
    date(2026, 6, 19): "端午", date(2026, 6, 20): "端午",
    # 中秋
    date(2026, 9, 25): "中秋", date(2026, 9, 26): "中秋", date(2026, 9, 27): "中秋",
    # 国庆
    date(2026, 10, 1): "国庆", date(2026, 10, 2): "国庆", date(2026, 10, 3): "国庆",
    date(2026, 10, 4): "国庆", date(2026, 10, 5): "国庆", date(2026, 10, 6): "国庆",
    date(2026, 10, 7): "国庆",
    # 2027 简表
    date(2027, 1, 1): "元旦",
    date(2027, 2, 6): "春节·除夕", date(2027, 2, 7): "春节·初一",
    date(2027, 2, 8): "春节·初二", date(2027, 2, 9): "春节·初三",
    date(2027, 4, 5): "清明",
    date(2027, 5, 1): "劳动节", date(2027, 5, 2): "劳动节", date(2027, 5, 3): "劳动节",
    date(2027, 6, 9): "端午",
    date(2027, 9, 15): "中秋",
    date(2027, 10, 1): "国庆", date(2027, 10, 2): "国庆", date(2027, 10, 3): "国庆",
}


def holiday_of(d: date) -> Optional[str]:
    return PUBLIC_HOLIDAYS.get(d)
