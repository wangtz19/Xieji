"""方位维度：太岁/岁破/三煞/二十四山向/九宫飞星/本命卦。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lunar_python import Solar


# 12 地支 → 方位（罗盘 24 山向中的支位）
ZHI_DIRECTION = {
    "子": "正北",  "丑": "北偏东", "寅": "东偏北",
    "卯": "正东",  "辰": "东偏南", "巳": "南偏东",
    "午": "正南",  "未": "南偏西", "申": "西偏南",
    "酉": "正西",  "戌": "西偏北", "亥": "北偏西",
}

# 三煞按年支三合局对宫
# 申子辰水局 -> 三煞在南(巳午未)
# 寅午戌火局 -> 三煞在北(亥子丑)
# 亥卯未木局 -> 三煞在西(申酉戌)
# 巳酉丑金局 -> 三煞在东(寅卯辰)
SAN_SHA = {
    frozenset({"申", "子", "辰"}): ("南方", ["巳", "午", "未"]),
    frozenset({"寅", "午", "戌"}): ("北方", ["亥", "子", "丑"]),
    frozenset({"亥", "卯", "未"}): ("西方", ["申", "酉", "戌"]),
    frozenset({"巳", "酉", "丑"}): ("东方", ["寅", "卯", "辰"]),
}

# 24 山向：8 天干（除戊己） + 12 地支 + 4 维（乾坤艮巽）
# 顺序：壬→子→癸→丑→艮→寅→甲→卯→乙→辰→巽→巳→丙→午→丁→未→坤→申→庚→酉→辛→戌→乾→亥
TWENTY_FOUR_SHAN = [
    "壬", "子", "癸",  "丑", "艮", "寅",  "甲", "卯", "乙",
    "辰", "巽", "巳",  "丙", "午", "丁",  "未", "坤", "申",
    "庚", "酉", "辛",  "戌", "乾", "亥",
]

# 24 山所属八卦宫位（用于本命卦匹配）
SHAN_TO_GUA = {
    "壬": "坎", "子": "坎", "癸": "坎",
    "丑": "艮", "艮": "艮", "寅": "艮",
    "甲": "震", "卯": "震", "乙": "震",
    "辰": "巽", "巽": "巽", "巳": "巽",
    "丙": "离", "午": "离", "丁": "离",
    "未": "坤", "坤": "坤", "申": "坤",
    "庚": "兑", "酉": "兑", "辛": "兑",
    "戌": "乾", "乾": "乾", "亥": "乾",
}

# 八卦方位
GUA_POSITION = {
    "坎": "正北", "艮": "东北", "震": "正东", "巽": "东南",
    "离": "正南", "坤": "西南", "兑": "正西", "乾": "西北",
}

# 东四命 / 西四命
DONG_SI_MING = {"坎", "震", "巽", "离"}
XI_SI_MING = {"乾", "坤", "艮", "兑"}

# 本命卦表：上元/中元/下元 + 男女，对应卦
# 上中下元划分（民国后通行）:
#   上元: 1864-1923; 中元: 1924-1983; 下元: 1984-2043
def _year_yuan(year: int) -> str:
    if 1864 <= year <= 1923:
        return "上元"
    if 1924 <= year <= 1983:
        return "中元"
    return "下元"


# 三元宫位起点表
YUAN_START_MALE = {"上元": "坎", "中元": "巽", "下元": "兑"}
YUAN_START_FEMALE = {"上元": "中", "中元": "坤", "下元": "艮"}

# 九宫飞行顺序（男逆女顺）
GUA_ORDER_MALE = ["坎", "离", "艮", "兑", "乾", "坤", "巽", "震", "中"]  # 男 倒推：坎9→离8→艮7→兑6→乾5→坤4→巽3→震2→中1
GUA_ORDER_FEMALE = ["坎", "坤", "震", "巽", "中", "乾", "兑", "艮", "离"]


@dataclass
class DirectionAdvice:
    year_gz: str
    tai_sui_zhi: str       # 太岁所在地支
    tai_sui_dir: str
    sui_po_zhi: str
    sui_po_dir: str
    san_sha_dir: str
    san_sha_zhi: list
    twenty_four_shan_yi: list   # 当年/当日宜的山向
    twenty_four_shan_ji: list   # 当年/当日忌的山向


def year_directions(year: int) -> DirectionAdvice:
    """计算指定农历年的太岁/岁破/三煞方位与忌动山向。"""
    # 用 lunar-python 取干支年
    solar = Solar.fromYmd(year, 6, 1)  # 取年中确保不跨春节
    l = solar.getLunar()
    year_gz = l.getYearInGanZhi()
    year_zhi = year_gz[-1]

    sui_po_map = {
        "子": "午", "丑": "未", "寅": "申", "卯": "酉",
        "辰": "戌", "巳": "亥", "午": "子", "未": "丑",
        "申": "寅", "酉": "卯", "戌": "辰", "亥": "巳",
    }
    sui_po_zhi = sui_po_map[year_zhi]

    san_sha_info = None
    for key, val in SAN_SHA.items():
        if year_zhi in key:
            san_sha_info = val
            break
    san_sha_dir, san_sha_zhi = san_sha_info if san_sha_info else ("", [])

    # 忌动山向：太岁、岁破、三煞所占的山
    ji_shan = []
    seen = set()
    for z in [year_zhi, sui_po_zhi] + san_sha_zhi:
        if z not in seen:
            ji_shan.append(z)
            seen.add(z)
    # 宜方向：与太岁三合的另外两支
    yi_shan = []
    sanhe_map = {
        "子": ["申", "辰"], "丑": ["巳", "酉"], "寅": ["午", "戌"],
        "卯": ["亥", "未"], "辰": ["申", "子"], "巳": ["酉", "丑"],
        "午": ["寅", "戌"], "未": ["亥", "卯"], "申": ["子", "辰"],
        "酉": ["巳", "丑"], "戌": ["寅", "午"], "亥": ["卯", "未"],
    }
    yi_shan = sanhe_map.get(year_zhi, [])

    return DirectionAdvice(
        year_gz=year_gz,
        tai_sui_zhi=year_zhi,
        tai_sui_dir=ZHI_DIRECTION[year_zhi],
        sui_po_zhi=sui_po_zhi,
        sui_po_dir=ZHI_DIRECTION[sui_po_zhi],
        san_sha_dir=san_sha_dir,
        san_sha_zhi=san_sha_zhi,
        twenty_four_shan_yi=yi_shan,
        twenty_four_shan_ji=ji_shan,
    )


def benming_gua(year: int, gender: int) -> dict:
    """本命卦推算（八宅派）。

    gender: 1=男, 0=女
    返回：本命卦 / 四吉方 / 四凶方 / 东四命 or 西四命
    """
    # 简化算法（适用于公元年）：
    # 男：(100 - 年后两位 - 出生世纪偏移) % 9 → 卦
    # 民间常用 1900 年之后通行公式
    last2 = year % 100
    if year < 2000:
        if gender == 1:  # 男
            n = (100 - last2) % 9
        else:  # 女
            n = (last2 + 4) % 9
    else:  # 2000+
        if gender == 1:
            n = (99 - last2) % 9
        else:
            n = (last2 + 5) % 9
    if n == 0:
        n = 9
    # 数字→卦（紫白九星）
    NUM_TO_GUA = {1: "坎", 2: "坤", 3: "震", 4: "巽",
                  6: "乾", 7: "兑", 8: "艮", 9: "离"}
    if n == 5:
        gua = "坤" if gender == 1 else "艮"
    else:
        gua = NUM_TO_GUA[n]

    # 八宅四吉四凶
    LUCK_MAP = {
        "坎": {"生气": "东南", "天医": "正东", "延年": "正南", "伏位": "正北",
              "祸害": "正西", "六煞": "西北", "五鬼": "东北", "绝命": "西南"},
        "离": {"生气": "正东", "天医": "东南", "延年": "正北", "伏位": "正南",
              "祸害": "东北", "六煞": "西南", "五鬼": "西北", "绝命": "正西"},
        "震": {"生气": "正南", "天医": "正北", "延年": "东南", "伏位": "正东",
              "祸害": "西南", "六煞": "东北", "五鬼": "正西", "绝命": "西北"},
        "巽": {"生气": "正北", "天医": "正南", "延年": "正东", "伏位": "东南",
              "祸害": "西北", "六煞": "正西", "五鬼": "东北", "绝命": "西南"},
        "乾": {"生气": "正西", "天医": "东北", "延年": "西南", "伏位": "西北",
              "祸害": "东南", "六煞": "正北", "五鬼": "正东", "绝命": "正南"},
        "坤": {"生气": "东北", "天医": "正西", "延年": "西北", "伏位": "西南",
              "祸害": "正东", "六煞": "正南", "五鬼": "东南", "绝命": "正北"},
        "艮": {"生气": "西南", "天医": "西北", "延年": "正西", "伏位": "东北",
              "祸害": "正南", "六煞": "东南", "五鬼": "正北", "绝命": "正东"},
        "兑": {"生气": "西北", "天医": "西南", "延年": "东北", "伏位": "正西",
              "祸害": "正北", "六煞": "正南", "五鬼": "东南", "绝命": "正东"},
    }
    return {
        "gua": gua,
        "category": "东四命" if gua in DONG_SI_MING else "西四命",
        "lucky": {k: v for k, v in LUCK_MAP[gua].items() if k in {"生气", "天医", "延年", "伏位"}},
        "unlucky": {k: v for k, v in LUCK_MAP[gua].items() if k in {"祸害", "六煞", "五鬼", "绝命"}},
    }


def nine_star_grid(year: int) -> dict:
    """流年九宫飞星图（玄空风水）：1-9 数字落在 9 个方位。"""
    # 中宫起星：100 - (年份后两位之和) ... 简化用 lunar-python
    solar = Solar.fromYmd(year, 6, 1)
    l = solar.getLunar()
    center_star_num = int_from_chinese(l.getYearNineStar().getNumber())

    # 九宫顺飞（洛书顺序）
    # 中宫开始 → 西北 → 正西 → 东北 → 正南 → 正北 → 西南 → 正东 → 东南
    flow = ["中", "西北", "正西", "东北", "正南", "正北", "西南", "正东", "东南"]
    grid = {}
    n = center_star_num
    for pos in flow:
        grid[pos] = n
        n = n % 9 + 1
    return grid


CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9}


def int_from_chinese(s: str) -> int:
    for k, v in CN_NUM.items():
        if k in s:
            return v
    return 5


# 九宫吉凶（基本判断）
STAR_LUCK = {
    1: ("一白贪狼", "吉", "桃花、文昌"),
    2: ("二黑巨门", "凶", "病符、是非"),
    3: ("三碧禄存", "凶", "口舌、官非"),
    4: ("四绿文曲", "吉", "文昌、考试"),
    5: ("五黄廉贞", "大凶", "灾病、勿动"),
    6: ("六白武曲", "吉", "升迁、权贵"),
    7: ("七赤破军", "凶", "破财、争斗"),
    8: ("八白左辅", "大吉", "财运旺"),
    9: ("九紫右弼", "吉", "喜庆、姻缘"),
}
