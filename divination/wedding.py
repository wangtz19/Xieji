"""嫁娶周堂图：判定婚日落在周堂八位的哪一位，警示需回避的人。

周堂八位：夫、姑、堂、翁、第、灶、妇、厨
- 夫日 → 新郎宜回避（或新郎方面有损）
- 妇日 → 新娘宜回避
- 翁日 → 公公宜回避
- 姑日 → 婆婆宜回避
- 堂、第、灶、厨 → 吉

推算法（《协纪辨方书》通行）:
- 大月（30 天）：从【夫】位起，顺数到婚日（农历日数）
- 小月（29 天）：从【妇】位起，逆数到婚日
"""
from __future__ import annotations

from datetime import date

from lunar_python import Solar


# 周堂八位，顺时针排列（夫→姑→堂→翁→第→灶→妇→厨）
ZHOUTANG_POSITIONS = ["夫", "姑", "堂", "翁", "第", "灶", "妇", "厨"]

# 各位置吉凶与说明
ZHOUTANG_MEANING = {
    "夫": ("凶", "新郎当避，否则不利夫"),
    "妇": ("凶", "新娘当避，否则不利妇"),
    "翁": ("凶", "公公（男方父）当避"),
    "姑": ("凶", "婆婆（男方母）当避"),
    "堂": ("吉", "厅堂吉位，宜行礼"),
    "第": ("吉", "门第吉位，主家宅平安"),
    "灶": ("吉", "灶位吉，主衣食丰足"),
    "厨": ("吉", "厨位吉，主烹饪顺利"),
}


def lunar_month_size(year: int, lunar_month: int, is_leap: bool = False) -> int:
    """获取农历月的天数：29 或 30。"""
    from lunar_python import Lunar
    m = -lunar_month if is_leap else lunar_month
    # 农历每月第 30 天能否构造，即可判断
    try:
        Lunar.fromYmd(year, m, 30)
        return 30
    except Exception:
        return 29


def zhoutang_for_wedding(d: date) -> dict:
    """给定公历婚日，返回周堂八位中所处位置 + 吉凶。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()
    lunar_month = l.getMonth()
    lunar_day = l.getDay()
    is_leap = lunar_month < 0

    # 月大小
    month_size = lunar_month_size(l.getYear(), abs(lunar_month), is_leap)
    is_big_month = month_size == 30

    if is_big_month:
        # 大月从 夫(index 0) 顺数 lunar_day
        idx = (lunar_day - 1) % 8
    else:
        # 小月从 妇(index 6) 逆数 lunar_day
        # 妇为起点(1), 厨(2 逆向 = 灶), 灶(3 逆=第)... 即每天往前一个
        idx = (6 - (lunar_day - 1)) % 8

    pos = ZHOUTANG_POSITIONS[idx]
    luck, desc = ZHOUTANG_MEANING[pos]

    return {
        "position": pos,
        "luck": luck,
        "desc": desc,
        "lunar_day": lunar_day,
        "lunar_month": abs(lunar_month),
        "is_leap_month": is_leap,
        "month_size": month_size,
        "is_big_month": is_big_month,
        "all_positions": ZHOUTANG_POSITIONS,
        "highlight_index": idx,
    }


def avoid_persons_for_zhoutang(pos: str) -> list[str]:
    """周堂落位 → 应回避的人。"""
    return {
        "夫": ["新郎"],
        "妇": ["新娘"],
        "翁": ["新郎父亲"],
        "姑": ["新郎母亲"],
    }.get(pos, [])
