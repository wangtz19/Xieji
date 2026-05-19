"""PDF 老黄历：竖排传统样式单日页。"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from core.almanac import get_day_almanac


# 注册 CJK 字体（系统已安装思源宋体）
_FONT_REG = False
FONT_NAME = "SourceHanSerifSC"
FONT_PATH_CANDIDATES = [
    # Linux - 思源 / Noto / 微雅黑（含 Debian bookworm 实际命名）
    "/usr/share/fonts/sourcehan/SourceHanSerifSC-Regular.otf",
    "/usr/share/fonts/sourcehan/SourceHanSerifSC-Bold.otf",
    "/usr/share/fonts/opentype/source-han-serif/SourceHanSerifSC-Regular.otf",
    "/usr/share/fonts/opentype/noto-cjk/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
    "/root/.fonts/MSYH.TTC",
    # macOS
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/Library/Fonts/Songti.ttc",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]

LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.png"
_LOGO_CACHE: ImageReader | None = None


def _get_logo() -> ImageReader | None:
    """加载 logo 并按需缩到 256×256（避免原图过大撑大 PDF 体积），结果缓存复用。"""
    global _LOGO_CACHE
    if _LOGO_CACHE is not None:
        return _LOGO_CACHE
    if not LOGO_PATH.exists():
        return None
    try:
        from PIL import Image
        img = Image.open(LOGO_PATH)
        img.thumbnail((256, 256))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        _LOGO_CACHE = ImageReader(buf)
        return _LOGO_CACHE
    except Exception:
        try:
            _LOGO_CACHE = ImageReader(str(LOGO_PATH))
            return _LOGO_CACHE
        except Exception:
            return None


def _ensure_font():
    global _FONT_REG, FONT_NAME
    if _FONT_REG:
        return
    for path in FONT_PATH_CANDIDATES:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, path))
            _FONT_REG = True
            return
        except Exception:
            continue
    # 兜底
    FONT_NAME = "Helvetica"
    _FONT_REG = True


def _draw_vertical_text(c, x: float, y_top: float, text: str, font_size: float, gap: float = 2):
    """从上往下竖排写一段文字。"""
    c.setFont(FONT_NAME, font_size)
    y = y_top
    for ch in text:
        c.drawCentredString(x, y, ch)
        y -= font_size + gap


def render_huangli_pdf(d: date) -> bytes:
    """渲染单日老黄历样式 PDF，返回字节流。"""
    _ensure_font()
    a = get_day_almanac(d)

    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont(FONT_NAME, 12)

    # 整体边框
    margin = 20 * mm
    c.setStrokeColorRGB(0.4, 0.2, 0.2)
    c.setLineWidth(2.5)
    c.rect(margin, margin, W - 2 * margin, H - 2 * margin)
    c.setLineWidth(0.7)
    c.rect(margin + 5, margin + 5, W - 2 * margin - 10, H - 2 * margin - 10)

    # 顶部 logo（左侧，宛如钤印；置于内边框之内）
    img = _get_logo()
    if img is not None:
        try:
            logo_size = 48
            c.drawImage(
                img, margin + 15, H - margin - logo_size - 10,
                width=logo_size, height=logo_size, mask="auto",
            )
        except Exception:
            pass

    # 顶部横题（baseline 下移 26pt，避开 inner border 上沿）
    c.setFont(FONT_NAME, 24)
    c.setFillColorRGB(0.4, 0.1, 0.1)
    c.drawCentredString(W / 2, H - margin - 48, "协　纪　黄　历")
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT_NAME, 11)
    c.drawCentredString(W / 2, H - margin - 68, f"—— {a.solar_date.isoformat()} ——")

    # 左侧 大日字（公历日 + 农历）
    c.setFont(FONT_NAME, 70)
    c.setFillColorRGB(0.6, 0.05, 0.05)
    c.drawString(margin + 18, H - margin - 130, f"{a.solar_date.day:02d}")
    c.setFont(FONT_NAME, 14)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(margin + 18, H - margin - 150, f"{a.solar_date.year}年{a.solar_date.month}月")
    c.drawString(margin + 18, H - margin - 170, a.lunar_str.split("年")[-1])

    # 干支
    c.setFont(FONT_NAME, 13)
    c.drawString(margin + 18, H - margin - 200, f"{a.ganzhi_year}年  {a.shengxiao_year}")
    c.drawString(margin + 18, H - margin - 218, f"{a.ganzhi_month}月")
    c.setFillColorRGB(0.6, 0.05, 0.05)
    c.drawString(margin + 18, H - margin - 236, f"{a.ganzhi_day}日")
    c.setFillColorRGB(0, 0, 0)

    # 右侧 竖排 五柱信息
    right_col_x = W - margin - 50
    c.setFont(FONT_NAME, 12)
    _draw_vertical_text(c, right_col_x, H - margin - 60,
                        f"建除 {a.jianchu}", 14, 2)
    _draw_vertical_text(c, right_col_x - 30, H - margin - 60,
                        f"{a.tianshen}{a.tianshen_type}", 12, 1)
    _draw_vertical_text(c, right_col_x - 60, H - margin - 60,
                        f"{a.xiu}宿({a.xiu_luck})", 12, 1)
    _draw_vertical_text(c, right_col_x - 90, H - margin - 60,
                        a.nayin, 12, 1)

    # 中部"宜"框
    yi_y = H - margin - 280
    c.setFillColorRGB(0.85, 0.95, 0.85)
    c.rect(margin + 15, yi_y - 90, W - 2 * margin - 30, 90, fill=1, stroke=0)
    c.setFillColorRGB(0.05, 0.4, 0.05)
    c.setFont(FONT_NAME, 22)
    c.drawString(margin + 28, yi_y - 28, "宜")
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT_NAME, 12)
    yi_text = "　".join(a.yi) if a.yi else "—"
    # 长文本自动换行
    _wrapped_text(c, margin + 60, yi_y - 26, yi_text, W - 2 * margin - 80, 12, 5)

    # "忌"框
    ji_y = yi_y - 100
    c.setFillColorRGB(0.97, 0.85, 0.85)
    c.rect(margin + 15, ji_y - 90, W - 2 * margin - 30, 90, fill=1, stroke=0)
    c.setFillColorRGB(0.5, 0.05, 0.05)
    c.setFont(FONT_NAME, 22)
    c.drawString(margin + 28, ji_y - 28, "忌")
    c.setFillColorRGB(0, 0, 0)
    c.setFont(FONT_NAME, 12)
    ji_text = "　".join(a.ji) if a.ji else "—"
    _wrapped_text(c, margin + 60, ji_y - 26, ji_text, W - 2 * margin - 80, 12, 5)

    # 底部 神煞 + 冲煞 + 方位
    bot_y = ji_y - 110
    c.setFont(FONT_NAME, 11)
    rows = [
        ("吉神", "、".join(a.jishen) or "—"),
        ("凶煞", "、".join(a.xiongsha) or "—"),
        ("冲煞", f"冲 {a.chong_desc}　煞 {a.sha}"),
        ("方位", f"喜神 {a.xi_shen_fang}　财神 {a.cai_shen_fang}"),
        ("彭祖", f"{a.pengzu_gan}；{a.pengzu_zhi}"),
    ]
    for i, (k, v) in enumerate(rows):
        y = bot_y - i * 18
        c.setFillColorRGB(0.4, 0.1, 0.1)
        c.drawString(margin + 22, y, k + "：")
        c.setFillColorRGB(0, 0, 0)
        c.drawString(margin + 60, y, v[:80])

    # 落款
    c.setFont(FONT_NAME, 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(W / 2, margin + 12, "协纪 · 黄历择吉工具 · 文化参考 · 非吉凶决定论")

    c.save()
    buf.seek(0)
    return buf.getvalue()


def _wrapped_text(c, x, y, text, max_width, font_size, gap):
    """简易换行：按可用宽度切分。"""
    c.setFont(FONT_NAME, font_size)
    line = ""
    cur_y = y
    for ch in text:
        line_w = c.stringWidth(line + ch, FONT_NAME, font_size)
        if line_w > max_width and line:
            c.drawString(x, cur_y, line)
            cur_y -= font_size + gap
            line = ch
        else:
            line += ch
    if line:
        c.drawString(x, cur_y, line)
