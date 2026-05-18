"""时辰择吉：当日 12 时辰的吉凶/喜财神/真太阳时校正。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from lunar_python import Solar

from core.almanac import HUANGDAO_STARS, ZHI_SHENGXIAO


# 时辰名（13 段：含早子时与晚子时）
SHICHEN_NAMES_13 = [
    "早子时", "丑时", "寅时", "卯时", "辰时", "巳时",
    "午时", "未时", "申时", "酉时", "戌时", "亥时", "晚子时",
]


@dataclass
class HourSlot:
    """一个时辰。"""
    name: str
    start_hm: str       # 00:00
    end_hm: str         # 00:59
    ganzhi: str         # 甲子
    gan: str
    zhi: str
    shengxiao: str      # 时辰冲煞生肖
    tianshen: str
    tianshen_type: str  # 黄道/黑道
    tianshen_luck: str  # 吉/凶
    chong_desc: str
    sha: str
    xi_dir: str         # 喜神方位
    cai_dir: str        # 财神方位
    fu_dir: str         # 福神方位
    yang_gui_dir: str   # 阳贵神
    yin_gui_dir: str    # 阴贵神
    nayin: str
    xun: str
    xun_kong: str
    yi: list = field(default_factory=list)
    ji: list = field(default_factory=list)
    score: int = 0


def get_hour_slots(d: date) -> list[HourSlot]:
    """返回当日 13 时辰（含晚子时）完整信息。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()
    out = []
    for i, t in enumerate(l.getTimes()):
        slot = HourSlot(
            name=SHICHEN_NAMES_13[i] if i < len(SHICHEN_NAMES_13) else f"时{i}",
            start_hm=t.getMinHm(),
            end_hm=t.getMaxHm(),
            ganzhi=t.getGanZhi(),
            gan=t.getGan(),
            zhi=t.getZhi(),
            shengxiao=t.getShengXiao(),
            tianshen=t.getTianShen(),
            tianshen_type=t.getTianShenType(),
            tianshen_luck=t.getTianShenLuck(),
            chong_desc=t.getChongDesc(),
            sha=t.getSha(),
            xi_dir=t.getPositionXiDesc(),
            cai_dir=t.getPositionCaiDesc(),
            fu_dir=t.getPositionFuDesc(),
            yang_gui_dir=t.getPositionYangGuiDesc(),
            yin_gui_dir=t.getPositionYinGuiDesc(),
            nayin=t.getNaYin(),
            xun=t.getXun(),
            xun_kong=t.getXunKong(),
            yi=list(t.getYi()),
            ji=list(t.getJi()),
        )
        slot.score = score_hour(slot)
        out.append(slot)
    return out


def score_hour(slot: HourSlot) -> int:
    """单时辰评分（0-100）。"""
    s = 50
    if slot.tianshen in HUANGDAO_STARS:
        s += 15
    else:
        s -= 15
    if slot.tianshen_luck == "吉":
        s += 5
    else:
        s -= 5
    # 旬空大凶
    if slot.zhi in slot.xun_kong:
        s -= 10
    return max(0, min(100, s))


def best_hours_for_event(slots: list[HourSlot], event: Optional[str] = None) -> list[HourSlot]:
    """从 12 时辰中筛出宜某事的吉时。"""
    if not event:
        return [s for s in slots if s.tianshen_type == "黄道"]
    # 用与 almanac 同一套同义词
    from almanac import EVENT_KEYWORDS
    keywords = EVENT_KEYWORDS.get(event, [event])
    result = []
    for s in slots:
        if any(k in s.yi for k in keywords):
            result.append(s)
        elif s.tianshen_type == "黄道" and not any(k in s.ji for k in keywords):
            result.append(s)
    return result


# === 真太阳时校正 ===
def true_solar_time(
    standard_dt: datetime,
    longitude: float,
    standard_meridian: float = 120.0,
) -> datetime:
    """北京时间(东 8 区, 东经 120°)→当地真太阳时。

    包含经度修正与时差方程（equation of time, 近似公式）。
    """
    # 经度修正：每偏离标准经线 1°，差 4 分钟
    lon_correction_min = (longitude - standard_meridian) * 4

    # 时差方程（分钟）近似公式（Spencer 简化版）
    import math
    day_of_year = standard_dt.timetuple().tm_yday
    B = 2 * math.pi * (day_of_year - 81) / 364
    eot_min = 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)

    return standard_dt + timedelta(minutes=lon_correction_min + eot_min)


# 国内主要城市经度（便于用户选择）
CITY_LONGITUDE = {
    "北京": 116.41, "上海": 121.47, "广州": 113.27, "深圳": 114.06,
    "杭州": 120.15, "南京": 118.78, "成都": 104.07, "重庆": 106.55,
    "武汉": 114.30, "西安": 108.95, "天津": 117.20, "苏州": 120.62,
    "青岛": 120.38, "长沙": 112.94, "哈尔滨": 126.64, "沈阳": 123.43,
    "济南": 117.00, "郑州": 113.62, "厦门": 118.08, "福州": 119.30,
    "昆明": 102.83, "贵阳": 106.71, "拉萨": 91.13, "乌鲁木齐": 87.62,
    "兰州": 103.83, "西宁": 101.78, "银川": 106.27, "呼和浩特": 111.75,
    "南宁": 108.37, "海口": 110.32, "三亚": 109.51, "香港": 114.16,
    "澳门": 113.55, "台北": 121.51,
}


def correct_birth_to_true_solar(dt: datetime, city: Optional[str] = None,
                                longitude: Optional[float] = None) -> datetime:
    """将出生时间从北京时间转为真太阳时（影响时柱）。"""
    if longitude is None and city:
        longitude = CITY_LONGITUDE.get(city, 120.0)
    if longitude is None:
        return dt
    return true_solar_time(dt, longitude)
