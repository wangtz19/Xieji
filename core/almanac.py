"""黄历核心模块：包装 lunar-python，输出某日完整的择吉信息。"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime

from lunar_python import Solar


GAN_WUXING = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

ZHI_WUXING = {
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
    "申": "金", "酉": "金",
    "亥": "水", "子": "水",
}

ZHI_SHENGXIAO = {
    "子": "鼠", "丑": "牛", "寅": "虎", "卯": "兔",
    "辰": "龙", "巳": "蛇", "午": "马", "未": "羊",
    "申": "猴", "酉": "鸡", "戌": "狗", "亥": "猪",
}

SHENGXIAO_ZHI = {v: k for k, v in ZHI_SHENGXIAO.items()}

# 地支六冲（相隔六位）
ZHI_CHONG = {
    "子": "午", "丑": "未", "寅": "申", "卯": "酉",
    "辰": "戌", "巳": "亥", "午": "子", "未": "丑",
    "申": "寅", "酉": "卯", "戌": "辰", "亥": "巳",
}

# 地支三合局
ZHI_SANHE = {
    "申": {"子", "辰"}, "子": {"申", "辰"}, "辰": {"申", "子"},
    "亥": {"卯", "未"}, "卯": {"亥", "未"}, "未": {"亥", "卯"},
    "寅": {"午", "戌"}, "午": {"寅", "戌"}, "戌": {"寅", "午"},
    "巳": {"酉", "丑"}, "酉": {"巳", "丑"}, "丑": {"巳", "酉"},
}

# 地支六合
ZHI_LIUHE = {
    "子": "丑", "丑": "子", "寅": "亥", "亥": "寅",
    "卯": "戌", "戌": "卯", "辰": "酉", "酉": "辰",
    "巳": "申", "申": "巳", "午": "未", "未": "午",
}

# 地支相害
ZHI_HAI = {
    "子": "未", "丑": "午", "寅": "巳", "卯": "辰",
    "辰": "卯", "巳": "寅", "午": "丑", "未": "子",
    "申": "亥", "酉": "戌", "戌": "酉", "亥": "申",
}

# 黄道吉星 / 黑道凶星
HUANGDAO_STARS = {"青龙", "明堂", "金匮", "天德", "玉堂", "司命"}
HEIDAO_STARS = {"天刑", "朱雀", "白虎", "天牢", "玄武", "勾陈"}

# 建除十二神
JIANCHU_LUCKY = {"除", "危", "定", "执", "成", "开"}
JIANCHU_NEUTRAL = {"建", "满", "平", "收"}
JIANCHU_BAD = {"破", "闭"}

# 重要吉神（加权更高）
MAJOR_JISHEN = {
    "天德", "月德", "天德合", "月德合", "天恩", "天赦",
    "岁德", "岁德合", "月空", "母仓", "三合", "六合",
    "天医", "天喜", "天富", "天贵", "玉宇", "金堂",
}

# 重要凶煞（扣权更高，部分为"诸事不宜"级）
MAJOR_XIONGSHA = {
    "月破", "岁破", "四离", "四绝", "归忌", "往亡",
    "灭门", "大耗", "天贼", "受死", "重日", "复日",
    "天罡", "河魁", "土符", "土府", "土忌", "土禁",
    "杨公忌",
}

# 事项同义词映射：用户事项 -> 黄历"宜/忌"中的关键词
EVENT_KEYWORDS = {
    "婚嫁": ["嫁娶", "纳采", "订婚", "纳婿", "结婚"],
    "丧葬": ["安葬", "破土", "启攒", "入殓", "成服除服"],
    "动土": ["动土", "修造", "起基", "竖柱"],
    "上梁": ["上梁", "盖屋"],
    "开市": ["开市", "开业", "立券", "交易", "纳财"],
    "出行": ["出行", "远行"],
    "搬家": ["入宅", "移徙", "搬家"],
    "祈福": ["祈福", "祭祀", "斋醮"],
    "求嗣": ["求嗣"],
    "签约": ["立券", "交易", "纳财"],
}


@dataclass
class DayAlmanac:
    """单日黄历完整信息。"""
    solar_date: date
    lunar_str: str          # 二〇二六年四月初二
    ganzhi_year: str        # 丙午
    ganzhi_month: str       # 癸巳
    ganzhi_day: str         # 壬辰
    shengxiao_year: str     # 马
    day_gan: str
    day_zhi: str
    day_gan_wuxing: str
    day_zhi_wuxing: str
    nayin: str              # 长流水
    jianchu: str            # 建除十二神当日
    tianshen: str           # 当值黄黑道神
    tianshen_type: str      # 黄道/黑道
    tianshen_luck: str      # 吉/凶
    xiu: str                # 二十八宿
    xiu_luck: str           # 吉/凶
    yi: list                # 宜
    ji: list                # 忌
    jishen: list            # 吉神
    xiongsha: list          # 凶煞
    chong_shengxiao: str    # 冲哪个生肖
    chong_desc: str         # (丙戌)狗
    sha: str                # 煞方位
    pengzu_gan: str
    pengzu_zhi: str
    xi_shen_fang: str       # 喜神方位
    cai_shen_fang: str      # 财神方位

    def as_dict(self) -> dict:
        d = asdict(self)
        d["solar_date"] = self.solar_date.isoformat()
        return d


def get_day_almanac(d: date) -> DayAlmanac:
    """计算指定公历日期的完整黄历。"""
    solar = Solar.fromYmd(d.year, d.month, d.day)
    l = solar.getLunar()

    day_gan = l.getDayGan()
    day_zhi = l.getDayZhi()

    return DayAlmanac(
        solar_date=d,
        lunar_str=f"{l.getYearInChinese()}年{l.getMonthInChinese()}月{l.getDayInChinese()}",
        ganzhi_year=l.getYearInGanZhi(),
        ganzhi_month=l.getMonthInGanZhi(),
        ganzhi_day=l.getDayInGanZhi(),
        shengxiao_year=l.getYearShengXiao(),
        day_gan=day_gan,
        day_zhi=day_zhi,
        day_gan_wuxing=GAN_WUXING.get(day_gan, ""),
        day_zhi_wuxing=ZHI_WUXING.get(day_zhi, ""),
        nayin=l.getDayNaYin(),
        jianchu=l.getZhiXing(),
        tianshen=l.getDayTianShen(),
        tianshen_type=l.getDayTianShenType(),
        tianshen_luck=l.getDayTianShenLuck(),
        xiu=l.getXiu(),
        xiu_luck=l.getXiuLuck(),
        yi=list(l.getDayYi()),
        ji=list(l.getDayJi()),
        jishen=list(l.getDayJiShen()),
        xiongsha=list(l.getDayXiongSha()),
        chong_shengxiao=l.getDayChongShengXiao(),
        chong_desc=l.getDayChongDesc(),
        sha=l.getDaySha(),
        pengzu_gan=l.getPengZuGan(),
        pengzu_zhi=l.getPengZuZhi(),
        xi_shen_fang=l.getDayPositionXiDesc(),
        cai_shen_fang=l.getDayPositionCaiDesc(),
    )


def get_birth_chart(birth_dt: datetime) -> dict:
    """从公历生辰（年月日时）计算当事人八字关键信息：日主、生肖、日支。"""
    solar = Solar.fromYmdHms(
        birth_dt.year, birth_dt.month, birth_dt.day,
        birth_dt.hour, birth_dt.minute, 0,
    )
    l = solar.getLunar()
    day_gan = l.getDayGan()
    day_zhi = l.getDayZhi()
    year_shengxiao = l.getYearShengXiao()
    return {
        "bazi": l.getBaZi(),
        "day_gan": day_gan,
        "day_zhi": day_zhi,
        "day_gan_wuxing": GAN_WUXING.get(day_gan, ""),
        "day_zhi_wuxing": ZHI_WUXING.get(day_zhi, ""),
        "year_shengxiao": year_shengxiao,
        "year_zhi": SHENGXIAO_ZHI.get(year_shengxiao, ""),
    }
