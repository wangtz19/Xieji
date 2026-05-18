"""传统择吉的"硬规则"：凶日/特殊日的判定。

凡命中"诸事不宜"级凶日，应在评分中标记 fatal 或重扣分。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from lunar_python import Solar


# 农历月支对照（正月=寅）
LUNAR_MONTH_ZHI = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"]

# 三娘煞：农历每月固定 6 天，相传月老与三娘有怨，专破嫁娶
SAN_NIANG_LUNAR_DAYS = {3, 7, 13, 18, 22, 27}

# 十恶大败日（干支组合）：百事不利，尤忌开市、上任
SHI_E_DA_BAI_GANZHI = {
    "甲辰", "乙巳", "丙申", "丁亥", "戊戌",
    "己丑", "庚辰", "辛巳", "壬申", "癸亥",
}

# 杨公十三忌：农历日，{月: 日}
YANG_GONG_13_JI = {
    1: 13, 2: 11, 3: 9, 4: 7, 5: 5, 6: 3,
    7: 1, 8: 27, 9: 25, 10: 23, 11: 21, 12: 19,
}
# 七月还有一日廿九
YANG_GONG_EXTRA_7 = 29

# 月忌日（农历）：初五、十四、廿三
MONTH_JI_LUNAR_DAYS = {5, 14, 23}

# 月厌日：按农历月支 → 厌日地支
YUE_YAN = {
    "寅": "戌", "卯": "酉", "辰": "申", "巳": "未",
    "午": "午", "未": "巳", "申": "辰", "酉": "卯",
    "戌": "寅", "亥": "丑", "子": "子", "丑": "亥",
}

# 红沙日：孟月酉 / 仲月巳 / 季月丑
# 孟=寅巳申亥，仲=卯午酉子，季=辰未戌丑
MENG_ZHI = {"寅", "巳", "申", "亥"}
ZHONG_ZHI = {"卯", "午", "酉", "子"}
JI_ZHI = {"辰", "未", "戌", "丑"}

# 重丧日：月支 → 重丧日的日干
CHONG_SANG = {
    "寅": "甲", "卯": "乙", "辰": "戊", "巳": "丙",
    "午": "丁", "未": "己", "申": "庚", "酉": "辛",
    "戌": "戊", "亥": "壬", "子": "癸", "丑": "己",
}

# 归忌日：季节 → 忌归之日支
# 春(寅卯辰月)→丑日，夏(巳午未月)→寅日，秋(申酉戌月)→子日，冬(亥子丑月)→卯日
GUI_JI = {
    "寅": "丑", "卯": "丑", "辰": "丑",
    "巳": "寅", "午": "寅", "未": "寅",
    "申": "子", "酉": "子", "戌": "子",
    "亥": "卯", "子": "卯", "丑": "卯",
}

# 往亡日：每节气后的固定天数。key=节气名 → 立春起算往亡日的偏移天数
WANG_WANG_OFFSET = {
    "立春": 7, "惊蛰": 14, "清明": 21, "立夏": 8,
    "芒种": 16, "小暑": 24, "立秋": 9, "白露": 18,
    "寒露": 27, "立冬": 10, "大雪": 20, "小寒": 30,
}

# 四绝日：立春/立夏/立秋/立冬 前一天
# 四离日：春分/秋分/夏至/冬至 前一天
SI_JUE_BEFORE = {"立春", "立夏", "立秋", "立冬"}
SI_LI_BEFORE = {"春分", "秋分", "夏至", "冬至"}

# 嫁娶周堂图：女家娶日宜避"翁堂、姑堂"（按月大月小推算，此处简化为日忌）
# 实际算法复杂，作占位


def is_san_niang_sha(lunar_day: int) -> bool:
    return lunar_day in SAN_NIANG_LUNAR_DAYS


def is_shi_e_da_bai(day_ganzhi: str) -> bool:
    return day_ganzhi in SHI_E_DA_BAI_GANZHI


def is_yang_gong_ji(lunar_month: int, lunar_day: int) -> bool:
    if YANG_GONG_13_JI.get(lunar_month) == lunar_day:
        return True
    if lunar_month == 7 and lunar_day == YANG_GONG_EXTRA_7:
        return True
    return False


def is_month_ji(lunar_day: int) -> bool:
    return lunar_day in MONTH_JI_LUNAR_DAYS


def is_yue_yan(month_zhi: str, day_zhi: str) -> bool:
    return YUE_YAN.get(month_zhi) == day_zhi


def is_hong_sha(month_zhi: str, day_zhi: str) -> bool:
    if month_zhi in MENG_ZHI and day_zhi == "酉":
        return True
    if month_zhi in ZHONG_ZHI and day_zhi == "巳":
        return True
    if month_zhi in JI_ZHI and day_zhi == "丑":
        return True
    return False


def is_chong_sang(month_zhi: str, day_gan: str) -> bool:
    return CHONG_SANG.get(month_zhi) == day_gan


def is_gui_ji(month_zhi: str, day_zhi: str) -> bool:
    return GUI_JI.get(month_zhi) == day_zhi


def is_si_li_or_si_jue(d: date) -> Optional[str]:
    """判定是否为四离或四绝日（在节气前一天）。"""
    nxt = d + timedelta(days=1)
    solar = Solar.fromYmd(nxt.year, nxt.month, nxt.day)
    l = solar.getLunar()
    jq = l.getCurrentJieQi()
    if jq:
        name = jq.getName()
        if name in SI_JUE_BEFORE:
            # 节气当日才属于四绝前夕
            jq_solar = l.getJieQiTable().get(name)
            if jq_solar and jq_solar.toYmd() == nxt.isoformat():
                return f"四绝（{name}前一日）"
        if name in SI_LI_BEFORE:
            jq_solar = l.getJieQiTable().get(name)
            if jq_solar and jq_solar.toYmd() == nxt.isoformat():
                return f"四离（{name}前一日）"
    return None


def is_tu_wang(d: date) -> bool:
    """土王用事：立春/立夏/立秋/立冬 前 18 天进入，期间忌动土。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()
    jq_table = l.getJieQiTable()
    for name in ["立春", "立夏", "立秋", "立冬"]:
        jq_solar = jq_table.get(name)
        if not jq_solar:
            continue
        jq_date = date(jq_solar.getYear(), jq_solar.getMonth(), jq_solar.getDay())
        if 0 < (jq_date - d).days <= 18:
            return True
    return False


def is_wang_wang(d: date) -> bool:
    """往亡日：每节气后第 N 天。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()
    jq_table = l.getJieQiTable()
    for name, offset in WANG_WANG_OFFSET.items():
        jq_solar = jq_table.get(name)
        if not jq_solar:
            continue
        jq_date = date(jq_solar.getYear(), jq_solar.getMonth(), jq_solar.getDay())
        if jq_date + timedelta(days=offset - 1) == d:
            return True
    return False


def is_bu_jiang_ri(month_zhi: str, day_ganzhi: str) -> bool:
    """不将日（嫁娶吉日）：阴阳调和无相争之日，传统嫁娶首选。

    简化版：按《协纪辨方书》月支对应的不将干支表（节选常见）。
    """
    # 不将日完整表很长，这里给出每月几个代表性日，供加分参考
    # 月支 → 不将日干支列表（节选）
    BU_JIANG = {
        "寅": {"丙寅", "丁卯", "丙子", "丁丑", "戊寅", "己卯"},
        "卯": {"乙丑", "丙寅", "丁卯", "丙子", "戊寅", "己卯"},
        "辰": {"甲子", "乙丑", "甲戌", "丙子", "丁丑", "戊寅"},
        "巳": {"甲子", "甲戌", "丙戌", "乙酉", "丙子", "戊子"},
        "午": {"癸酉", "甲戌", "癸未", "甲申", "乙酉", "丙戌"},
        "未": {"壬申", "癸酉", "壬午", "癸未", "甲申", "乙酉"},
        "申": {"壬申", "癸酉", "壬午", "甲午", "乙未", "甲申"},
        "酉": {"庚午", "辛未", "壬申", "庚辰", "壬午", "甲午"},
        "戌": {"庚辰", "辛巳", "庚午", "壬午", "壬辰", "癸巳"},
        "亥": {"戊辰", "己巳", "庚午", "戊寅", "庚辰", "辛巳"},
        "子": {"丁卯", "戊辰", "己巳", "戊寅", "庚辰", "辛巳"},
        "丑": {"丙寅", "丁卯", "戊辰", "丙子", "戊寅", "己卯"},
    }
    return day_ganzhi in BU_JIANG.get(month_zhi, set())


# === 事项 → 必避凶日清单 ===
EVENT_HARD_TABOOS = {
    "婚嫁": [
        ("三娘煞", "san_niang"),
        ("十恶大败", "shi_e"),
        ("四离", "si_li"),
        ("四绝", "si_jue"),
        ("月厌", "yue_yan"),
        ("红沙", "hong_sha"),
        ("月破", None),  # 由 almanac.xiongsha 直接判定
    ],
    "丧葬": [
        ("重丧", "chong_sang"),
        ("复日", None),
        ("月破", None),
        ("四废", None),
        ("杨公十三忌", "yang_gong"),
    ],
    "动土": [
        ("土王用事", "tu_wang"),
        ("土符", None),
        ("土禁", None),
        ("月破", None),
    ],
    "上梁": [
        ("月破", None),
        ("四离", "si_li"),
        ("四绝", "si_jue"),
    ],
    "开市": [
        ("月忌", "month_ji"),
        ("十恶大败", "shi_e"),
        ("月破", None),
        ("闭日", None),
    ],
    "出行": [
        ("往亡", "wang_wang"),
        ("归忌", "gui_ji"),
        ("月厌", "yue_yan"),
        ("四离", "si_li"),
        ("四绝", "si_jue"),
    ],
    "搬家": [
        ("归忌", "gui_ji"),
        ("月厌", "yue_yan"),
        ("月破", None),
    ],
    "祈福": [
        ("四离", "si_li"),
        ("四绝", "si_jue"),
    ],
    "求嗣": [
        ("月厌", "yue_yan"),
    ],
    "签约": [
        ("月破", None),
        ("十恶大败", "shi_e"),
    ],
}


def evaluate_taboos(
    d: date,
    lunar_day: int,
    lunar_month: int,
    month_zhi: str,
    day_gan: str,
    day_zhi: str,
    day_ganzhi: str,
    xiongsha: list[str],
) -> dict:
    """计算当日命中的所有硬性凶日，返回 {名称: 是否命中}。"""
    si = is_si_li_or_si_jue(d)
    hits = {
        "san_niang":  is_san_niang_sha(lunar_day),
        "shi_e":      is_shi_e_da_bai(day_ganzhi),
        "yang_gong":  is_yang_gong_ji(lunar_month, lunar_day),
        "month_ji":   is_month_ji(lunar_day),
        "yue_yan":    is_yue_yan(month_zhi, day_zhi),
        "hong_sha":   is_hong_sha(month_zhi, day_zhi),
        "chong_sang": is_chong_sang(month_zhi, day_gan),
        "gui_ji":     is_gui_ji(month_zhi, day_zhi),
        "si_li":      bool(si and "四离" in si),
        "si_jue":     bool(si and "四绝" in si),
        "tu_wang":    is_tu_wang(d),
        "wang_wang":  is_wang_wang(d),
        "bu_jiang":   is_bu_jiang_ri(month_zhi, day_ganzhi),  # 嫁娶吉
    }
    # 与 lunar-python 自带 xiongsha 整合
    for name in xiongsha:
        if name == "月破":
            hits["yue_po"] = True
        if name == "复日":
            hits["fu_ri"] = True
        if name == "四废":
            hits["si_fei"] = True
    return hits


HIT_LABEL = {
    "san_niang":  "三娘煞",
    "shi_e":      "十恶大败",
    "yang_gong":  "杨公十三忌",
    "month_ji":   "月忌日",
    "yue_yan":    "月厌",
    "hong_sha":   "红沙日",
    "chong_sang": "重丧日",
    "gui_ji":     "归忌",
    "si_li":      "四离",
    "si_jue":     "四绝",
    "tu_wang":    "土王用事",
    "wang_wang":  "往亡",
    "bu_jiang":   "不将日(嫁娶吉)",
    "yue_po":     "月破",
    "fu_ri":      "复日",
    "si_fei":     "四废",
}
