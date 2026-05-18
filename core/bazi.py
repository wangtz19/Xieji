"""完整八字排盘：四柱/十神/藏干/纳音/五行强弱/喜用神/大运。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

from lunar_python import Solar

from core.almanac import GAN_WUXING, ZHI_WUXING, ZHI_SHENGXIAO


WUXING_LIST = ["木", "火", "土", "金", "水"]

# 月令旺相对照（简化）：月支 → 当令五行
MONTH_WANG = {
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "申": "金", "酉": "金",
    "亥": "水", "子": "水",
    # 四季月土旺：辰戌丑未
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

# 五行生克
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}


@dataclass
class Pillar:
    gan: str
    zhi: str
    gan_wuxing: str
    zhi_wuxing: str
    shi_shen_gan: str
    shi_shen_zhi: list
    hide_gan: list
    nayin: str
    xun: str
    xun_kong: str

    @property
    def ganzhi(self) -> str:
        return f"{self.gan}{self.zhi}"


@dataclass
class DaYun:
    start_age: int
    end_age: int
    start_year: int
    ganzhi: str


@dataclass
class BaZi:
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar
    gender: int           # 1=男, 0=女
    shengxiao: str
    tai_yuan: str         # 胎元
    ming_gong: str        # 命宫
    shen_gong: str        # 身宫

    # 五行统计
    wuxing_count: dict = field(default_factory=dict)
    strength: str = ""    # 强 / 中和 / 弱
    strength_score: int = 0
    yong_shen: list = field(default_factory=list)   # 喜用神五行
    ji_shen: list = field(default_factory=list)     # 忌神五行

    da_yun: list = field(default_factory=list)
    start_yun: str = ""   # 起运日期

    @property
    def day_gan(self) -> str:
        return self.day.gan

    @property
    def day_gan_wuxing(self) -> str:
        return self.day.gan_wuxing

    @property
    def year_zhi(self) -> str:
        return self.year.zhi


def build_bazi(birth_dt: datetime, gender: int = 1) -> BaZi:
    """从公历生辰（真太阳时）+ 性别构建完整八字。

    gender: 1=男, 0=女
    """
    solar = Solar.fromYmdHms(
        birth_dt.year, birth_dt.month, birth_dt.day,
        birth_dt.hour, birth_dt.minute, birth_dt.second,
    )
    l = solar.getLunar()
    ec = l.getEightChar()

    def _pillar(gan: str, zhi: str, ss_gan: str, ss_zhi: list,
                hide: list, nayin: str, xun: str, xunkong: str) -> Pillar:
        return Pillar(
            gan=gan, zhi=zhi,
            gan_wuxing=GAN_WUXING.get(gan, ""),
            zhi_wuxing=ZHI_WUXING.get(zhi, ""),
            shi_shen_gan=ss_gan,
            shi_shen_zhi=ss_zhi,
            hide_gan=hide,
            nayin=nayin, xun=xun, xun_kong=xunkong,
        )

    year_p = _pillar(
        ec.getYear()[0], ec.getYear()[1],
        ec.getYearShiShenGan(), ec.getYearShiShenZhi(),
        ec.getYearHideGan(), ec.getYearNaYin(),
        ec.getYearXun(), ec.getYearXunKong(),
    )
    month_p = _pillar(
        ec.getMonth()[0], ec.getMonth()[1],
        ec.getMonthShiShenGan(), ec.getMonthShiShenZhi(),
        ec.getMonthHideGan(), ec.getMonthNaYin(),
        ec.getMonthXun(), ec.getMonthXunKong(),
    )
    day_p = _pillar(
        ec.getDay()[0], ec.getDay()[1],
        ec.getDayShiShenGan(), ec.getDayShiShenZhi(),
        ec.getDayHideGan(), ec.getDayNaYin(),
        ec.getDayXun(), ec.getDayXunKong(),
    )
    hour_p = _pillar(
        ec.getTime()[0], ec.getTime()[1],
        ec.getTimeShiShenGan(), ec.getTimeShiShenZhi(),
        ec.getTimeHideGan(), ec.getTimeNaYin(),
        ec.getTimeXun(), ec.getTimeXunKong(),
    )

    bz = BaZi(
        year=year_p, month=month_p, day=day_p, hour=hour_p,
        gender=gender,
        shengxiao=l.getYearShengXiao(),
        tai_yuan=ec.getTaiYuan(),
        ming_gong=ec.getMingGong(),
        shen_gong=ec.getShenGong(),
    )

    # 五行计数（天干 +1，地支 +1，藏干各 +0.5）
    bz.wuxing_count = _count_wuxing(bz)
    bz.strength, bz.strength_score = _judge_strength(bz)
    bz.yong_shen, bz.ji_shen = _pick_yong_shen(bz)

    # 大运
    yun = ec.getYun(gender)
    bz.start_yun = yun.getStartSolar().toYmd()
    bz.da_yun = []
    for d in yun.getDaYun()[:8]:
        gz = d.getGanZhi()
        if gz:
            bz.da_yun.append(DaYun(
                start_age=d.getStartAge(),
                end_age=d.getEndAge(),
                start_year=d.getStartYear(),
                ganzhi=gz,
            ))

    return bz


def _count_wuxing(bz: BaZi) -> dict:
    cnt = {wx: 0.0 for wx in WUXING_LIST}
    for p in [bz.year, bz.month, bz.day, bz.hour]:
        if p.gan_wuxing:
            cnt[p.gan_wuxing] += 1
        if p.zhi_wuxing:
            cnt[p.zhi_wuxing] += 1
        # 藏干每个 0.3 权重（主气/中气/余气精确分配是 0.5/0.3/0.2，此处简化）
        for hg in p.hide_gan:
            wx = GAN_WUXING.get(hg, "")
            if wx:
                cnt[wx] += 0.3
    return {k: round(v, 1) for k, v in cnt.items()}


def _judge_strength(bz: BaZi) -> tuple[str, int]:
    """日主强弱判定（简化）：得令 + 通根 + 同党。"""
    me = bz.day_gan_wuxing
    if not me:
        return "中和", 0

    score = 0
    # 1. 得令：月支当令五行是否同我或生我
    month_wang = MONTH_WANG.get(bz.month.zhi, "")
    if month_wang == me:
        score += 3
    elif SHENG.get(month_wang) == me:
        score += 2
    elif month_wang == SHENG.get(me):
        score -= 1  # 我生月令（泄气）
    elif KE.get(month_wang) == me:
        score -= 1  # 月令克我（弱）但等下会从通根回扣
    elif month_wang == KE.get(me):
        score += 1  # 我克月令（小帮）

    # 2. 通根：日主五行在其它三支或藏干中出现
    for p in [bz.year, bz.month, bz.hour]:
        if p.zhi_wuxing == me:
            score += 2
        for hg in p.hide_gan:
            if GAN_WUXING.get(hg, "") == me:
                score += 0.5

    # 3. 同党：天干（除日主外）同我或生我
    for p in [bz.year, bz.month, bz.hour]:
        if p.gan_wuxing == me:
            score += 1
        elif SHENG.get(p.gan_wuxing) == me:
            score += 0.5

    # 综合判断
    score = int(score)
    if score >= 6:
        return "偏强", score
    if score >= 4:
        return "中和偏强", score
    if score >= 2:
        return "中和", score
    if score >= 0:
        return "中和偏弱", score
    return "偏弱", score


def _pick_yong_shen(bz: BaZi) -> tuple[list, list]:
    """喜用神推断（极简）：弱者扶之，强者抑之。

    弱 → 用印(生我) + 比劫(同我)
    强 → 用食伤(我生) + 财(我克) + 官杀(克我)
    """
    me = bz.day_gan_wuxing
    if not me:
        return [], []

    me_set = {me}
    sheng_me = {k for k, v in SHENG.items() if v == me}  # 生我
    me_sheng = {SHENG[me]} if me in SHENG else set()      # 我生
    ke_me = {k for k, v in KE.items() if v == me}         # 克我
    me_ke = {KE[me]} if me in KE else set()               # 我克

    if "弱" in bz.strength:
        yong = list(sheng_me | me_set)
        ji = list(me_sheng | me_ke | ke_me)
    elif "强" in bz.strength:
        yong = list(me_sheng | me_ke | ke_me)
        ji = list(sheng_me | me_set)
    else:
        # 中和：取最少的五行作调候用神
        cnt = bz.wuxing_count
        sorted_wx = sorted(cnt.items(), key=lambda x: x[1])
        yong = [sorted_wx[0][0], sorted_wx[1][0]]
        ji = [sorted_wx[-1][0]]
    return yong, ji


def hehun_score(bride: BaZi, groom: BaZi) -> dict:
    """新人合婚评分（简化）。

    考虑：生肖合冲、日柱合冲、五行互补。
    """
    score = 50
    reasons = []

    # 生肖合冲
    from almanac import ZHI_CHONG, ZHI_LIUHE, ZHI_SANHE, ZHI_HAI, SHENGXIAO_ZHI
    b_zhi = SHENGXIAO_ZHI.get(bride.shengxiao, "")
    g_zhi = SHENGXIAO_ZHI.get(groom.shengxiao, "")
    if b_zhi and g_zhi:
        if ZHI_CHONG.get(b_zhi) == g_zhi:
            score -= 25
            reasons.append(f"−25　生肖六冲（{bride.shengxiao}↔{groom.shengxiao}）")
        elif ZHI_LIUHE.get(b_zhi) == g_zhi:
            score += 15
            reasons.append(f"+15　生肖六合（{bride.shengxiao}+{groom.shengxiao}）")
        elif g_zhi in ZHI_SANHE.get(b_zhi, set()):
            score += 12
            reasons.append(f"+12　生肖三合")
        elif ZHI_HAI.get(b_zhi) == g_zhi:
            score -= 10
            reasons.append(f"−10　生肖相害")

    # 日柱
    if bride.day.zhi == groom.day.zhi:
        score += 5
        reasons.append(f"+5　日支同（{bride.day.zhi}）")
    elif ZHI_CHONG.get(bride.day.zhi) == groom.day.zhi:
        score -= 15
        reasons.append(f"−15　日支冲")
    elif ZHI_LIUHE.get(bride.day.zhi) == groom.day.zhi:
        score += 8
        reasons.append(f"+8　日支六合")

    # 五行互补
    b_yong = set(bride.yong_shen)
    g_yong = set(groom.yong_shen)
    overlap = b_yong & g_yong
    if overlap:
        score += 6
        reasons.append(f"+6　双方喜用神有共通（{'/'.join(overlap)}）")

    # 一方喜用神是对方的强项（互补）
    if bride.yong_shen:
        for wx in bride.yong_shen:
            if groom.wuxing_count.get(wx, 0) >= 2 and bride.wuxing_count.get(wx, 0) < 1:
                score += 4
                reasons.append(f"+4　夫供给妻所需【{wx}】")
                break
    if groom.yong_shen:
        for wx in groom.yong_shen:
            if bride.wuxing_count.get(wx, 0) >= 2 and groom.wuxing_count.get(wx, 0) < 1:
                score += 4
                reasons.append(f"+4　妻供给夫所需【{wx}】")
                break

    score = max(0, min(100, score))
    if score >= 75:
        verdict = "上等婚"
    elif score >= 60:
        verdict = "中上婚"
    elif score >= 45:
        verdict = "中等婚"
    elif score >= 30:
        verdict = "下中婚"
    else:
        verdict = "不宜婚"
    return {"score": score, "verdict": verdict, "reasons": reasons}
