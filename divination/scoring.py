"""评分与事项推荐：基于 DayAlmanac + 凶日规则 + 多当事人 + 流派权重。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from lunar_python import Solar

from core.almanac import (
    DayAlmanac, get_day_almanac,
    HUANGDAO_STARS, JIANCHU_LUCKY, JIANCHU_BAD,
    MAJOR_JISHEN, MAJOR_XIONGSHA, EVENT_KEYWORDS,
    ZHI_CHONG, ZHI_SANHE, ZHI_LIUHE, ZHI_HAI,
)
from divination.rules import evaluate_taboos, EVENT_HARD_TABOOS, HIT_LABEL


# 五行生克
WUXING_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


def wuxing_relation(self_wx: str, other_wx: str) -> str:
    if not self_wx or not other_wx:
        return "无"
    if self_wx == other_wx:
        return "比和"
    if WUXING_SHENG.get(other_wx) == self_wx:
        return "生我"
    if WUXING_SHENG.get(self_wx) == other_wx:
        return "我生"
    if WUXING_KE.get(other_wx) == self_wx:
        return "克我"
    if WUXING_KE.get(self_wx) == other_wx:
        return "我克"
    return "无"


# === 流派权重 ===
SCHOOL_WEIGHTS = {
    "综合": {  # 默认
        "huangdao": 8, "jianchu_lucky": 5, "jianchu_bad": -10,
        "xiu": 4, "major_jishen": 3, "minor_jishen": 1,
        "major_xiongsha": -5, "minor_xiongsha": -1,
        "yi_match": 20, "ji_match": -30, "no_match": -2,
        "chong_birth": -30, "sanhe": 6, "liuhe": 5, "hai": -8,
        "wuxing_yong": 5, "wuxing_ji": -5,
        "taboo_fatal_majority": True,  # 命中"诸事不宜"凶日是否标 fatal
    },
    "协纪辨方": {  # 清官修 偏重神煞
        "huangdao": 10, "jianchu_lucky": 6, "jianchu_bad": -12,
        "xiu": 5, "major_jishen": 4, "minor_jishen": 1,
        "major_xiongsha": -6, "minor_xiongsha": -1,
        "yi_match": 18, "ji_match": -35, "no_match": -1,
        "chong_birth": -30, "sanhe": 5, "liuhe": 4, "hai": -6,
        "wuxing_yong": 3, "wuxing_ji": -3,
        "taboo_fatal_majority": True,
    },
    "董公选日": {  # 民间通行 偏重宜忌
        "huangdao": 6, "jianchu_lucky": 4, "jianchu_bad": -8,
        "xiu": 3, "major_jishen": 2, "minor_jishen": 1,
        "major_xiongsha": -4, "minor_xiongsha": -1,
        "yi_match": 25, "ji_match": -40, "no_match": -3,
        "chong_birth": -25, "sanhe": 8, "liuhe": 6, "hai": -10,
        "wuxing_yong": 4, "wuxing_ji": -4,
        "taboo_fatal_majority": True,
    },
    "宽松模式": {  # 仅参考 适合"差不多就行"
        "huangdao": 5, "jianchu_lucky": 3, "jianchu_bad": -5,
        "xiu": 2, "major_jishen": 2, "minor_jishen": 0,
        "major_xiongsha": -3, "minor_xiongsha": 0,
        "yi_match": 15, "ji_match": -20, "no_match": -1,
        "chong_birth": -15, "sanhe": 4, "liuhe": 3, "hai": -5,
        "wuxing_yong": 2, "wuxing_ji": -2,
        "taboo_fatal_majority": False,
    },
}


@dataclass
class ScoreBreakdown:
    score: int = 50
    raw_score: int = 50
    reasons: list = field(default_factory=list)
    fatal: bool = False
    taboos: dict = field(default_factory=dict)

    def add(self, delta: int, reason: str):
        self.score += delta
        self.raw_score += delta
        sign = "+" if delta >= 0 else ""
        self.reasons.append(f"{sign}{delta}　{reason}")

    def mark_fatal(self, reason: str):
        self.fatal = True
        self.reasons.append(f"⚠　{reason}")


def score_day(
    almanac: DayAlmanac,
    event: Optional[str] = None,
    persons: Optional[list[dict]] = None,
    school: str = "综合",
) -> ScoreBreakdown:
    """对单日进行评分。

    persons: [{"day_gan_wuxing":..., "year_zhi":..., "year_shengxiao":..., "label":"新郎"}, ...]
    school: 流派
    """
    w = SCHOOL_WEIGHTS.get(school, SCHOOL_WEIGHTS["综合"])
    sb = ScoreBreakdown()

    # 1. 黄黑道
    if almanac.tianshen in HUANGDAO_STARS:
        sb.add(+w["huangdao"], f"黄道吉星【{almanac.tianshen}】当值")
    else:
        sb.add(-w["huangdao"], f"黑道凶星【{almanac.tianshen}】当值")

    # 2. 建除
    jc = almanac.jianchu
    if jc in JIANCHU_LUCKY:
        sb.add(+w["jianchu_lucky"], f"建除【{jc}】主吉")
    elif jc in JIANCHU_BAD:
        sb.add(w["jianchu_bad"], f"建除【{jc}】主凶")
        if jc == "破":
            sb.mark_fatal("月破日，诸事不宜")
    else:
        sb.add(0, f"建除【{jc}】中平")

    # 3. 二十八宿
    if almanac.xiu_luck == "吉":
        sb.add(+w["xiu"], f"星宿【{almanac.xiu}】吉")
    else:
        sb.add(-w["xiu"], f"星宿【{almanac.xiu}】凶")

    # 4. 吉神
    for js in almanac.jishen:
        if js in MAJOR_JISHEN:
            sb.add(+w["major_jishen"], f"吉神【{js}】临")
        else:
            sb.add(+w["minor_jishen"], f"吉神【{js}】")

    # 5. 凶煞
    for xs in almanac.xiongsha:
        if xs in MAJOR_XIONGSHA:
            sb.add(w["major_xiongsha"], f"凶煞【{xs}】当值")
            if xs in {"月破", "岁破", "四离", "四绝", "灭门", "受死"} and w["taboo_fatal_majority"]:
                sb.mark_fatal(f"逢【{xs}】，传统视为大凶")
        else:
            sb.add(w["minor_xiongsha"], f"凶煞【{xs}】")

    # 6. 事项匹配
    if event:
        keywords = EVENT_KEYWORDS.get(event, [event])
        hit_yi = [k for k in keywords if k in almanac.yi]
        hit_ji = [k for k in keywords if k in almanac.ji]
        if hit_yi:
            sb.add(+w["yi_match"], f"当日宜【{' / '.join(hit_yi)}】，正合所求")
        if hit_ji:
            sb.add(w["ji_match"], f"当日忌【{' / '.join(hit_ji)}】，犯本事")
            sb.mark_fatal(f"通书明列今日忌【{event}】")
        if not hit_yi and not hit_ji:
            sb.add(w["no_match"], f"宜忌未直接涉及【{event}】")

    # 7. 多当事人冲煞与生肖合化
    persons = persons or []
    for p in persons:
        label = p.get("label", "当事人")
        person_zhi = p.get("year_zhi", "")
        person_sx = p.get("year_shengxiao", "")
        day_zhi = almanac.day_zhi

        if person_zhi and ZHI_CHONG.get(day_zhi) == person_zhi:
            sb.add(w["chong_birth"], f"日支{day_zhi}冲【{label}】生肖{person_sx}")
            if w["taboo_fatal_majority"]:
                sb.mark_fatal(f"今日正冲【{label}】({person_sx})")
        elif person_zhi and day_zhi in ZHI_SANHE.get(person_zhi, set()):
            sb.add(+w["sanhe"], f"日支与【{label}】本命{person_zhi}三合")
        elif person_zhi and ZHI_LIUHE.get(person_zhi) == day_zhi:
            sb.add(+w["liuhe"], f"日支与【{label}】本命{person_zhi}六合")
        elif person_zhi and ZHI_HAI.get(person_zhi) == day_zhi:
            sb.add(w["hai"], f"日支害【{label}】本命{person_zhi}")

        # 五行匹配
        person_wx = p.get("day_gan_wuxing", "")
        yong = p.get("yong_shen", [])
        day_wx = almanac.day_gan_wuxing
        if yong and day_wx in yong:
            sb.add(+w["wuxing_yong"], f"日柱【{day_wx}】是【{label}】喜用神")
        elif person_wx:
            rel = wuxing_relation(person_wx, day_wx)
            if rel == "生我":
                sb.add(+max(2, w["wuxing_yong"] // 2), f"日柱【{day_wx}】生【{label}】日主")
            elif rel == "克我":
                sb.add(w["wuxing_ji"], f"日柱【{day_wx}】克【{label}】日主")

    # 8. 传统凶日表
    solar = Solar.fromYmd(almanac.solar_date.year, almanac.solar_date.month, almanac.solar_date.day)
    l = solar.getLunar()
    lunar_month = l.getMonth() if l.getMonth() > 0 else l.getMonth() + 12
    hits = evaluate_taboos(
        almanac.solar_date, l.getDay(), lunar_month, l.getMonthZhi(),
        l.getDayGan(), l.getDayZhi(), l.getDayInGanZhi(),
        almanac.xiongsha,
    )
    sb.taboos = {HIT_LABEL[k]: v for k, v in hits.items() if v}

    # 事项相关凶日
    if event:
        relevant = EVENT_HARD_TABOOS.get(event, [])
        for name, key in relevant:
            if key and hits.get(key):
                sb.add(-15, f"犯【{name}】（事项忌）")
                if w["taboo_fatal_majority"] and name in {
                    "三娘煞", "十恶大败", "重丧", "杨公十三忌",
                    "四离", "四绝", "月破", "土王用事", "往亡",
                }:
                    sb.mark_fatal(f"【{event}】犯【{name}】")
    # 不将日（嫁娶专属吉）
    if hits.get("bu_jiang") and event == "婚嫁":
        sb.add(+8, "不将日（嫁娶大吉）")

    sb.score = max(0, min(100, sb.score))
    return sb


def verdict(score: int, fatal: bool) -> str:
    if fatal:
        return "大凶 · 不取"
    if score >= 80:
        return "上吉"
    if score >= 65:
        return "吉"
    if score >= 50:
        return "中平"
    if score >= 35:
        return "次"
    return "凶"


def recommend_days(
    event: str,
    persons: Optional[list[dict]],
    start: date,
    days: int = 365,
    top_n: int = 20,
    school: str = "综合",
    exclude_weekdays: Optional[set[int]] = None,
) -> list:
    """在 [start, start+days) 内为某事项推荐吉日，可指定多个当事人。"""
    results = []
    for i in range(days):
        d = start + timedelta(days=i)
        if exclude_weekdays and d.weekday() in exclude_weekdays:
            continue
        almanac = get_day_almanac(d)
        sb = score_day(almanac, event=event, persons=persons, school=school)
        if sb.fatal:
            continue
        keywords = EVENT_KEYWORDS.get(event, [event])
        hit_yi = any(k in almanac.yi for k in keywords)
        results.append({
            "date": d,
            "almanac": almanac,
            "score": sb.score,
            "raw_score": sb.raw_score,
            "reasons": sb.reasons,
            "taboos": sb.taboos,
            "verdict": verdict(sb.score, sb.fatal),
            "hit_yi": hit_yi,
        })
    results.sort(key=lambda r: (-int(r["hit_yi"]), -r["raw_score"], r["date"]))
    return results[:top_n]
