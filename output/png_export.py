"""分享海报：把单日黄历渲染成竖版 PNG，适合微信/朋友圈传播。

输出 720×1280 竖图，元素：
  - 顶部 logo + "协纪"标题
  - 大字日期 + 农历 + 干支
  - 醒目评分等级（颜色随等级变化）
  - 宜（绿色块）/ 忌（红色块）
  - 冲煞 / 喜神财神
  - 底部水印
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from core.almanac import get_day_almanac
from divination.scoring import score_day, verdict


# 字体探测
FONT_CANDIDATES = [
    "/usr/share/fonts/sourcehan/SourceHanSerifSC-Bold.otf",
    "/usr/share/fonts/sourcehan/SourceHanSerifSC-Regular.otf",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/root/.fonts/MSYH.TTC",
    "/root/.fonts/MSYHBD.TTC",
]
LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.png"


def _font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


# 评分等级 → 配色
VERDICT_COLORS = {
    "上吉":      ("#1b5e20", "#e8f5e9"),
    "吉":        ("#2e7d32", "#f1f8e9"),
    "中平":      ("#f9a825", "#fffde7"),
    "次":        ("#ef6c00", "#fff3e0"),
    "凶":        ("#b71c1c", "#ffebee"),
    "大凶 · 不取": ("#7f0000", "#ffcdd2"),
}


def render_share_poster(d: date, event: Optional[str] = None,
                        school: str = "综合") -> bytes:
    """渲染指定日期的海报 PNG，返回字节流。"""
    a = get_day_almanac(d)
    sb = score_day(a, event=event, school=school)
    v = verdict(sb.score, sb.fatal)

    W, H = 720, 1280
    fg = (40, 30, 30)
    bg = (244, 232, 200)  # 米黄
    border = (140, 60, 40)

    img = Image.new("RGB", (W, H), bg)
    d_ = ImageDraw.Draw(img)

    # 双层边框
    d_.rectangle([20, 20, W - 20, H - 20], outline=border, width=3)
    d_.rectangle([30, 30, W - 30, H - 30], outline=border, width=1)

    # === 顶部 logo + 协纪标题 ===
    if LOGO_PATH.exists():
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo.thumbnail((90, 90))
            img.paste(logo, (60, 65), logo)
        except Exception:
            pass

    d_.text((W // 2, 90), "协纪", font=_font(46), fill=border, anchor="mm")
    d_.text((W // 2, 135), "·　黄历择吉　·", font=_font(20), fill=(120, 80, 60), anchor="mm")

    # 分隔线
    d_.line([(80, 175), (W - 80, 175)], fill=border, width=1)

    # === 中部公历大字 ===
    d_.text((W // 2, 235), str(d.day), font=_font(180), fill=border, anchor="mm")
    d_.text((W // 2, 345), f"{d.year} 年 {d.month} 月", font=_font(26), fill=fg, anchor="mm")
    d_.text((W // 2, 385), a.lunar_str, font=_font(24), fill=fg, anchor="mm")

    # === 干支行 ===
    gz_text = f"{a.ganzhi_year}年　{a.ganzhi_month}月　{a.ganzhi_day}日"
    d_.text((W // 2, 435), gz_text, font=_font(22), fill=(100, 50, 50), anchor="mm")
    d_.text((W // 2, 470), f"{a.shengxiao_year}年 · {a.jianchu}日 · {a.tianshen}（{a.tianshen_type}）",
            font=_font(18), fill=(120, 90, 70), anchor="mm")

    # === 评分卡 ===
    v_fg, v_bg = VERDICT_COLORS.get(v, ("#555", "#eee"))
    v_fg_rgb = tuple(int(v_fg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    v_bg_rgb = tuple(int(v_bg.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))

    card_x1, card_y1, card_x2, card_y2 = 60, 510, W - 60, 620
    d_.rounded_rectangle([card_x1, card_y1, card_x2, card_y2], radius=12,
                         fill=v_bg_rgb, outline=v_fg_rgb, width=2)
    d_.text((W // 2 - 80, (card_y1 + card_y2) // 2), v, font=_font(54), fill=v_fg_rgb, anchor="mm")
    d_.text((W // 2 + 100, (card_y1 + card_y2) // 2 - 12),
            f"{sb.score}", font=_font(48), fill=v_fg_rgb, anchor="mm")
    d_.text((W // 2 + 100, (card_y1 + card_y2) // 2 + 28),
            "/ 100", font=_font(18), fill=v_fg_rgb, anchor="mm")
    if event:
        d_.text((W // 2, card_y2 + 20), f"· 所求事项：{event} ·",
                font=_font(16), fill=(100, 70, 50), anchor="mm")

    # === 宜 框 ===
    yi_y1, yi_y2 = 680, 800
    d_.rounded_rectangle([60, yi_y1, W - 60, yi_y2], radius=8,
                         fill=(212, 235, 208), outline=(46, 125, 50), width=1)
    d_.text((90, yi_y1 + 35), "宜", font=_font(42), fill=(27, 94, 32), anchor="lm")
    yi_text = _wrap_text(d_, "　".join(a.yi[:10]) if a.yi else "—", 18, W - 250)
    _draw_multiline(d_, yi_text, (170, yi_y1 + 15), 18, (27, 94, 32), line_h=28)

    # === 忌 框 ===
    ji_y1, ji_y2 = 820, 940
    d_.rounded_rectangle([60, ji_y1, W - 60, ji_y2], radius=8,
                         fill=(247, 217, 217), outline=(183, 28, 28), width=1)
    d_.text((90, ji_y1 + 35), "忌", font=_font(42), fill=(127, 0, 0), anchor="lm")
    ji_text = _wrap_text(d_, "　".join(a.ji[:10]) if a.ji else "—", 18, W - 250)
    _draw_multiline(d_, ji_text, (170, ji_y1 + 15), 18, (127, 0, 0), line_h=28)

    # === 底部信息：冲煞 / 方位 / 彭祖 ===
    y0 = 980
    rows = [
        ("冲　煞", f"冲 {a.chong_desc}　煞 {a.sha}"),
        ("方　位", f"喜神 {a.xi_shen_fang}　财神 {a.cai_shen_fang}"),
        ("彭　祖", f"{a.pengzu_gan}；{a.pengzu_zhi}"),
    ]
    for i, (k, val) in enumerate(rows):
        y = y0 + i * 36
        d_.text((85, y), k, font=_font(18), fill=(140, 60, 40), anchor="lm")
        d_.text((180, y), val[:30], font=_font(17), fill=fg, anchor="lm")

    # === 落款 ===
    d_.line([(80, H - 110), (W - 80, H - 110)], fill=border, width=1)
    d_.text((W // 2, H - 75), "协纪　黄历择吉工具",
            font=_font(20), fill=border, anchor="mm")
    d_.text((W // 2, H - 50), "传统文化参考　·　非吉凶决定论",
            font=_font(14), fill=(120, 100, 80), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf.getvalue()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, size: int, max_w: int) -> list[str]:
    """按像素宽度切行。"""
    f = _font(size)
    lines = []
    cur = ""
    for ch in text:
        bbox = draw.textbbox((0, 0), cur + ch, font=f)
        if bbox[2] - bbox[0] > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def _draw_multiline(draw: ImageDraw.ImageDraw, lines: list[str],
                    xy: tuple[int, int], size: int,
                    fill: tuple, line_h: int = 28):
    x, y = xy
    f = _font(size)
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += line_h
