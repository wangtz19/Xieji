"""紫微斗数排盘（简化版）：12 宫位 + 14 主星定位 + 五行局。

仅实现核心算法：
- 命宫定位（月支顺、时支逆）
- 五行局（命宫干支纳音）
- 紫微星 + 天府星（按局数查表）
- 12 主星（紫微系 + 天府系）
- 命宫主星批注
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from lunar_python import Solar


# 地支顺序（顺时针）
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
ZHI_INDEX = {z: i for i, z in enumerate(ZHI)}

# 12 宫位（命宫起点，逆时针排列：兄弟→夫妻→子女→财帛→疾厄→迁移→奴仆→官禄→田宅→福德→父母）
PALACES_REVERSE = [
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "奴仆", "官禄", "田宅", "福德", "父母",
]

# 五虎遁起月：年干 → 正月（寅月）天干
YEAR_GAN_START_MONTH_GAN = {
    "甲": "丙", "己": "丙",
    "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}
GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]

# 60 甲子纳音对应五行
NAYIN_WUXING = {
    "甲子": "金", "乙丑": "金", "丙寅": "火", "丁卯": "火", "戊辰": "木", "己巳": "木",
    "庚午": "土", "辛未": "土", "壬申": "金", "癸酉": "金", "甲戌": "火", "乙亥": "火",
    "丙子": "水", "丁丑": "水", "戊寅": "土", "己卯": "土", "庚辰": "金", "辛巳": "金",
    "壬午": "木", "癸未": "木", "甲申": "水", "乙酉": "水", "丙戌": "土", "丁亥": "土",
    "戊子": "火", "己丑": "火", "庚寅": "木", "辛卯": "木", "壬辰": "水", "癸巳": "水",
    "甲午": "金", "乙未": "金", "丙申": "火", "丁酉": "火", "戊戌": "木", "己亥": "木",
    "庚子": "土", "辛丑": "土", "壬寅": "金", "癸卯": "金", "甲辰": "火", "乙巳": "火",
    "丙午": "水", "丁未": "水", "戊申": "土", "己酉": "土", "庚戌": "金", "辛亥": "金",
    "壬子": "木", "癸丑": "木", "甲寅": "水", "乙卯": "水", "丙辰": "土", "丁巳": "土",
    "戊午": "火", "己未": "火", "庚申": "木", "辛酉": "木", "壬戌": "水", "癸亥": "水",
}

# 五行 → 局数
WUXING_TO_JU = {"水": 2, "木": 3, "金": 4, "土": 5, "火": 6}
JU_NAME = {2: "水二局", 3: "木三局", 4: "金四局", 5: "土五局", 6: "火六局"}

# 紫微星 (局数, 日) → 所落地支 索引(子=0...亥=11)
# 标准表
ZIWEI_TABLE = {
    2: ["丑", "寅", "寅", "卯", "卯", "辰", "辰", "巳", "巳", "午",
        "午", "未", "未", "申", "申", "酉", "酉", "戌", "戌", "亥",
        "亥", "子", "子", "丑", "丑", "寅", "寅", "卯", "卯", "辰"],
    3: ["辰", "丑", "寅", "巳", "寅", "卯", "午", "卯", "辰", "未",
        "辰", "巳", "申", "巳", "午", "酉", "午", "未", "戌", "未",
        "申", "亥", "申", "酉", "子", "酉", "戌", "丑", "戌", "亥"],
    4: ["亥", "辰", "丑", "寅", "子", "巳", "寅", "卯", "丑", "午",
        "卯", "辰", "寅", "未", "辰", "巳", "卯", "申", "巳", "午",
        "辰", "酉", "午", "未", "巳", "戌", "未", "申", "午", "亥"],
    5: ["午", "亥", "辰", "丑", "寅", "未", "子", "巳", "寅", "卯",
        "申", "丑", "午", "卯", "辰", "酉", "寅", "未", "辰", "巳",
        "戌", "卯", "申", "巳", "午", "亥", "辰", "酉", "午", "未"],
    6: ["酉", "午", "亥", "辰", "丑", "寅", "戌", "未", "子", "巳",
        "寅", "卯", "亥", "申", "丑", "午", "卯", "辰", "子", "酉",
        "寅", "未", "辰", "巳", "丑", "戌", "卯", "申", "巳", "午"],
}

# 主星批注（命宫坐主星时的特性，节选）
MAIN_STAR_DESC = {
    "紫微": "帝王之星，主刚强果断、领导欲强；逢吉则尊贵，逢凶则孤傲。",
    "天机": "智慧之星，主聪明灵敏、善谋略；性多虑，宜文职。",
    "太阳": "贵气之星，主热情博爱、光明磊落；庙旺主名望，落陷则劳碌。",
    "武曲": "财星，主刚直、行动力强、善理财；女命较硬，宜晚婚。",
    "天同": "福星，主温和乐观、随遇而安；偏感性，少争斗心。",
    "廉贞": "次桃花、囚星，主多变化、情感丰富；化禄则佳，化忌则祸。",
    "天府": "宝库星，主稳重保守、积蓄丰厚；贵人多，少灾祸。",
    "太阴": "母星、田宅，主温柔细腻、重感情；女命尤吉，男命阴柔。",
    "贪狼": "桃花、欲望，主多才多艺、风流不羁；逢吉则艺术，逢凶则放纵。",
    "巨门": "暗星、口舌，主口才好但易招是非；做销售、传媒佳。",
    "天相": "印星、辅佐，主端正诚信、易得他人扶持；逢吉则贵。",
    "天梁": "荫星、寿星，主清高正直、解厄能力强；适宗教、医卜。",
    "七杀": "将星、肃杀，主独立强势、敢冲敢拼；动荡较多。",
    "破军": "耗星、变革，主开创破立、不安于现状；起伏大。",
}


@dataclass
class ZiweiChart:
    bazi_year_gz: str
    lunar_month: int     # 农历月 1-12
    lunar_day: int       # 农历日 1-30
    time_zhi: str        # 出生时辰
    gender: int          # 1=男 0=女
    ming_gong_zhi: str   # 命宫地支
    ming_gong_gan: str   # 命宫天干
    nayin: str           # 命宫纳音
    ju: int              # 局数 2-6
    ju_name: str         # 五行局名称
    palace_zhi: dict = field(default_factory=dict)   # 宫名 → 地支
    palace_stars: dict = field(default_factory=dict) # 宫名 → [主星]


def _time_to_zhi(hour: int) -> str:
    """小时数 → 时支。子时 23-1，丑时 1-3 ..."""
    if hour == 23:
        return "子"
    return ZHI[((hour + 1) // 2) % 12]


def build_ziwei(birth_dt: datetime, gender: int = 1) -> ZiweiChart:
    """构建紫微斗数命盘。"""
    solar = Solar.fromYmdHms(birth_dt.year, birth_dt.month, birth_dt.day,
                             birth_dt.hour, birth_dt.minute, birth_dt.second)
    l = solar.getLunar()
    year_gz = l.getYearInGanZhi()
    year_gan = year_gz[0]
    # 农历月，正月=1
    lunar_month = l.getMonth() if l.getMonth() > 0 else l.getMonth() + 12
    lunar_day = l.getDay()
    time_zhi = _time_to_zhi(birth_dt.hour)

    # === 命宫定位 ===
    # 从 寅(index 2) 起 顺数到 lunar_month (正月=寅, 二月=卯, ...)
    month_pos = (2 + (lunar_month - 1)) % 12
    # 逆数 时支
    time_idx = ZHI_INDEX[time_zhi]
    ming_pos = (month_pos - time_idx) % 12
    ming_zhi = ZHI[ming_pos]

    # === 命宫天干（五虎遁）===
    start_gan = YEAR_GAN_START_MONTH_GAN[year_gan]
    start_gan_idx = GAN.index(start_gan)
    # 从 寅 起到 命宫支，相差几位
    offset_from_yin = (ming_pos - 2) % 12
    ming_gan = GAN[(start_gan_idx + offset_from_yin) % 10]

    nayin = NAYIN_WUXING.get(ming_gan + ming_zhi, "金")
    ju = WUXING_TO_JU[nayin]

    # === 紫微星定位 ===
    ziwei_zhi = ZIWEI_TABLE[ju][lunar_day - 1]
    ziwei_idx = ZHI_INDEX[ziwei_zhi]

    # === 天府星定位（紫微 + 天府 = 4 mod 12, 即天府 = (4 - ziwei) mod 12）===
    tianfu_idx = (4 - ziwei_idx) % 12

    # === 紫微系 (逆数) ===
    star_pos = {}
    star_pos["紫微"] = ziwei_idx
    star_pos["天机"] = (ziwei_idx - 1) % 12
    star_pos["太阳"] = (ziwei_idx - 3) % 12
    star_pos["武曲"] = (ziwei_idx - 4) % 12
    star_pos["天同"] = (ziwei_idx - 5) % 12
    star_pos["廉贞"] = (ziwei_idx - 8) % 12

    # === 天府系 (顺数) ===
    star_pos["天府"] = tianfu_idx
    star_pos["太阴"] = (tianfu_idx + 1) % 12
    star_pos["贪狼"] = (tianfu_idx + 2) % 12
    star_pos["巨门"] = (tianfu_idx + 3) % 12
    star_pos["天相"] = (tianfu_idx + 4) % 12
    star_pos["天梁"] = (tianfu_idx + 5) % 12
    star_pos["七杀"] = (tianfu_idx + 6) % 12
    star_pos["破军"] = (tianfu_idx + 10) % 12

    # === 12 宫位（从命宫起，逆时针顺序）===
    palace_zhi = {}
    palace_stars = {p: [] for p in PALACES_REVERSE}
    for i, p in enumerate(PALACES_REVERSE):
        idx = (ming_pos - i) % 12
        z = ZHI[idx]
        palace_zhi[p] = z
        # 反查这一宫里有什么星
        for star, sidx in star_pos.items():
            if sidx == idx:
                palace_stars[p].append(star)

    return ZiweiChart(
        bazi_year_gz=year_gz,
        lunar_month=lunar_month,
        lunar_day=lunar_day,
        time_zhi=time_zhi,
        gender=gender,
        ming_gong_zhi=ming_zhi,
        ming_gong_gan=ming_gan,
        nayin=nayin,
        ju=ju,
        ju_name=JU_NAME[ju],
        palace_zhi=palace_zhi,
        palace_stars=palace_stars,
    )


def interpret_ming_gong(chart: ZiweiChart) -> str:
    """命宫主星批注。"""
    stars = chart.palace_stars.get("命宫", [])
    if not stars:
        return f"命宫无主星（坐{chart.ming_gong_gan}{chart.ming_gong_zhi}，借对宫迁移星看）。"
    lines = [f"命宫主星：{' / '.join(stars)}"]
    for s in stars:
        if s in MAIN_STAR_DESC:
            lines.append(f"・{s}：{MAIN_STAR_DESC[s]}")
    return "\n".join(lines)
