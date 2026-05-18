"""大运 / 流年深度解读。

针对每步大运（10 年）与年内流年：
- 大运五行 vs 日主 → 帮身/抑身/泄身/克身
- 大运五行 vs 喜用神 → 助益/逆背
- 流年组合 → 是否冲合大运
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from lunar_python import Solar

from core.almanac import GAN_WUXING, ZHI_WUXING, ZHI_CHONG, ZHI_LIUHE, ZHI_SANHE
from core.bazi import BaZi, SHENG, KE, WUXING_LIST


def _ten_god(day_gan_wx: str, other_wx: str, same_yin_yang: bool = True) -> str:
    """简化十神判定。"""
    if not day_gan_wx or not other_wx:
        return ""
    if day_gan_wx == other_wx:
        return "比肩" if same_yin_yang else "劫财"
    if SHENG.get(other_wx) == day_gan_wx:
        return "偏印" if same_yin_yang else "正印"
    if SHENG.get(day_gan_wx) == other_wx:
        return "食神" if same_yin_yang else "伤官"
    if KE.get(day_gan_wx) == other_wx:
        return "偏财" if same_yin_yang else "正财"
    if KE.get(other_wx) == day_gan_wx:
        return "七杀" if same_yin_yang else "正官"
    return ""


def evaluate_dayun(bz: BaZi) -> list[dict]:
    """对每步大运评分 + 文字批语。

    返回每步：{ganzhi, start_age, end_age, score, verdict, reasons, narrative}
    """
    me = bz.day_gan_wuxing
    yong = set(bz.yong_shen)
    ji = set(bz.ji_shen)

    out = []
    for dy in bz.da_yun:
        gz = dy.ganzhi
        if not gz or len(gz) < 2:
            continue
        gan, zhi = gz[0], gz[1]
        gan_wx = GAN_WUXING.get(gan, "")
        zhi_wx = ZHI_WUXING.get(zhi, "")

        score = 50
        reasons = []

        # 大运天干与日主关系
        if gan_wx in yong:
            score += 12
            reasons.append(f"+12 大运天干【{gan}({gan_wx})】为喜用神")
        elif gan_wx in ji:
            score -= 10
            reasons.append(f"−10 大运天干【{gan}({gan_wx})】为忌神")
        elif gan_wx == me:
            score += 6
            reasons.append(f"+6 大运天干与日主同气，比肩")

        # 大运地支与日主关系
        if zhi_wx in yong:
            score += 14
            reasons.append(f"+14 大运地支【{zhi}({zhi_wx})】为喜用神（地支力量大于天干）")
        elif zhi_wx in ji:
            score -= 12
            reasons.append(f"−12 大运地支【{zhi}({zhi_wx})】为忌神")

        # 大运地支与日支冲合
        day_zhi = bz.day.zhi
        if ZHI_CHONG.get(day_zhi) == zhi:
            score -= 15
            reasons.append(f"−15 大运冲日支（{zhi}↔{day_zhi}），主变动")
        elif ZHI_LIUHE.get(day_zhi) == zhi:
            score += 8
            reasons.append(f"+8 大运合日支，主和顺")
        elif zhi in ZHI_SANHE.get(day_zhi, set()):
            score += 6
            reasons.append(f"+6 大运与日支三合")

        # 大运地支与月令的关系：影响整体格局
        month_zhi = bz.month.zhi
        if zhi == month_zhi:
            score += 4
            reasons.append(f"+4 大运地支同月令")
        elif ZHI_CHONG.get(month_zhi) == zhi:
            score -= 8
            reasons.append(f"−8 大运冲月令（{zhi}↔{month_zhi}），格局动摇")

        score = max(0, min(100, score))

        # 评语
        if score >= 75:
            verdict = "佳运"
        elif score >= 60:
            verdict = "顺运"
        elif score >= 45:
            verdict = "平运"
        elif score >= 30:
            verdict = "蹇运"
        else:
            verdict = "厄运"

        # 叙事
        narrative = _narrative_for_dayun(dy, gan, zhi, gan_wx, zhi_wx, me, yong, ji, verdict)

        out.append({
            "ganzhi": gz,
            "start_age": dy.start_age,
            "end_age": dy.end_age,
            "start_year": dy.start_year,
            "score": score,
            "verdict": verdict,
            "reasons": reasons,
            "narrative": narrative,
            "gan_wuxing": gan_wx,
            "zhi_wuxing": zhi_wx,
        })

    return out


def _narrative_for_dayun(dy, gan, zhi, gan_wx, zhi_wx, me, yong, ji, verdict) -> str:
    parts = []
    if zhi_wx in yong:
        parts.append("此运地支为喜用神，根基稳固，凡事易得贵人助力。")
    elif zhi_wx in ji:
        parts.append("此运地支为忌神，根基不实，宜守不宜进，避免重大投资与变动。")
    elif zhi_wx == me:
        parts.append("此运地支助身，自身能力增强，适合主动求进、立业开拓。")

    if gan_wx in yong:
        parts.append("天干透出喜用，主表面际遇佳，名声地位有助。")
    elif gan_wx in ji:
        parts.append("天干透出忌神，外缘多扰，宜低调行事。")

    if verdict == "佳运":
        parts.append("综合而言，此运为人生重要顺境，宜把握机遇。")
    elif verdict == "厄运" or verdict == "蹇运":
        parts.append("综合而言，此运多见阻滞，应以韬光养晦为主，保健康守财气。")
    else:
        parts.append("综合而言，此运中平，常事可行，大事宜审慎。")

    return " ".join(parts)


def evaluate_liunian(bz: BaZi, dayun: dict, year: int) -> dict:
    """对某流年（年）评分，需先确定所在大运。"""
    solar = Solar.fromYmd(year, 6, 1)
    l = solar.getLunar()
    year_gz = l.getYearInGanZhi()
    gan, zhi = year_gz[0], year_gz[1]
    gan_wx = GAN_WUXING.get(gan, "")
    zhi_wx = ZHI_WUXING.get(zhi, "")

    me = bz.day_gan_wuxing
    yong = set(bz.yong_shen)
    ji = set(bz.ji_shen)

    score = 50
    reasons = []

    if gan_wx in yong:
        score += 6
        reasons.append(f"+6 流年干【{gan}】为喜用")
    elif gan_wx in ji:
        score -= 5
        reasons.append(f"−5 流年干【{gan}】为忌神")

    if zhi_wx in yong:
        score += 8
        reasons.append(f"+8 流年支【{zhi}】为喜用")
    elif zhi_wx in ji:
        score -= 7
        reasons.append(f"−7 流年支【{zhi}】为忌神")

    # 流年与日支
    day_zhi = bz.day.zhi
    if ZHI_CHONG.get(day_zhi) == zhi:
        score -= 10
        reasons.append(f"−10 流年冲日支（值年冲日主，主变动）")
    elif ZHI_LIUHE.get(day_zhi) == zhi:
        score += 5
        reasons.append("+5 流年合日支")

    # 流年与大运
    dy_gz = dayun["ganzhi"]
    if dy_gz:
        dy_zhi = dy_gz[1]
        if ZHI_CHONG.get(dy_zhi) == zhi:
            score -= 12
            reasons.append(f"−12 流年冲大运（{zhi}↔{dy_zhi}），主重大转折")
        elif zhi in ZHI_SANHE.get(dy_zhi, set()):
            score += 5
            reasons.append("+5 流年与大运三合，相辅相成")

    # 太岁本命：本年地支等于年柱地支
    if zhi == bz.year_zhi:
        score -= 8
        reasons.append("−8 值太岁本命年，事多反复")
    if ZHI_CHONG.get(zhi) == bz.year_zhi:
        score -= 10
        reasons.append("−10 冲太岁，主大变动")

    score = max(0, min(100, score))
    if score >= 70:
        v = "吉年"
    elif score >= 55:
        v = "顺年"
    elif score >= 40:
        v = "平年"
    else:
        v = "凶年"

    return {
        "year": year,
        "ganzhi": year_gz,
        "score": score,
        "verdict": v,
        "reasons": reasons,
    }
