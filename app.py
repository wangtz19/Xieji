"""协纪 · 黄历择吉工具 · Streamlit 前端（完整版）。

Tab 划分：
  1. 单日吉凶      日级 + 时辰表 + 凶日命中 + 节令信息
  2. 择吉推荐      多事项 + 多当事人 + 流派 + 排除工作日 + iCal/JSON 导出
  3. 月历视图      月格染色 / 鼠标悬停查详情
  4. 八字排盘      四柱 / 十神 / 藏干 / 强弱 / 喜用神 / 大运
  5. 方位罗盘      太岁岁破三煞 / 二十四山向 / 九宫飞星 / 本命卦
  6. 合婚          双人八字合参
  7. 节令          24 节气 / 三伏 / 数九 / 月相 / 法定节假日
  8. 设置          流派与权重说明
"""
from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

# 暂固定为东八区（北京时间）。Streamlit Cloud 服务器是 UTC，直接 today_cn()
# 会在 UTC 21:00~23:59 期间比中国"今天"早一天。
CN_TZ = ZoneInfo("Asia/Shanghai")


def today_cn() -> date:
    """以东八区为准的"今天"。"""
    return datetime.now(CN_TZ).date()

from core.almanac import get_day_almanac, EVENT_KEYWORDS
from core.hours import (
    get_hour_slots,
    correct_birth_to_true_solar, CITY_LONGITUDE,
)
from core.bazi import build_bazi, hehun_score
from core.directions import (
    year_directions, benming_gua, nine_star_grid, STAR_LUCK,
    TWENTY_FOUR_SHAN,
)
from core.calendars import (
    get_jieqi_table, current_jieqi_phase,
    san_fu, shu_jiu, moon_phase, holiday_of,
)

from divination.scoring import score_day, verdict, recommend_days, SCHOOL_WEIGHTS
from divination.wedding import zhoutang_for_wedding, avoid_persons_for_zhoutang, ZHOUTANG_POSITIONS
from divination.dayun import evaluate_dayun, evaluate_liunian
from divination.ziwei import build_ziwei, interpret_ming_gong, PALACES_REVERSE
from divination.sources import source_for

from output.export import export_ical, export_json, natural_language_summary
from output.pdf_export import render_huangli_pdf
from output.png_export import render_share_poster
from output.llm import (
    interpret_via_llm, LLMConfig,
    PROVIDER_ANTHROPIC, PROVIDER_OPENAI,
    BASE_URL_PRESETS, MODEL_PRESETS,
)


LOGO_PATH = str(Path(__file__).parent / "assets" / "logo.png")

st.set_page_config(
    page_title="协纪 · 黄历择吉工具",
    page_icon=LOGO_PATH,
    layout="wide",
)

# === JS 注入：把日历弹层的英文（周名/月名/Today）替换为中文 ===
# Streamlit 未暴露 locale 配置（issue #4076），baseweb 的日历用 <p>Su</p> 这种
# 元素渲染周名，CSS ::after 无法可靠覆盖。改用 MutationObserver 监听 DOM 变化，
# 在日历弹出时遍历文本节点替换。组件在 iframe 内，通过 window.parent.document
# 操作主页（同源，浏览器允许）。
st.components.v1.html(
    """
<script>
(function () {
    const doc = window.parent.document;
    if (doc.__xieji_cal_i18n__) return;     // 整个会话只装一次 observer
    doc.__xieji_cal_i18n__ = true;

    const map = {
        // 周名缩写（baseweb 默认 2 字母）
        'Su':'日','Mo':'一','Tu':'二','We':'三','Th':'四','Fr':'五','Sa':'六',
        // 周名全称（aria-label 或 tooltip 可能用到）
        'Sun':'日','Mon':'一','Tue':'二','Wed':'三','Thu':'四','Fri':'五','Sat':'六',
        'Sunday':'星期日','Monday':'星期一','Tuesday':'星期二',
        'Wednesday':'星期三','Thursday':'星期四','Friday':'星期五','Saturday':'星期六',
        // 月份
        'January':'一月','February':'二月','March':'三月','April':'四月',
        'May':'五月','June':'六月','July':'七月','August':'八月',
        'September':'九月','October':'十月','November':'十一月','December':'十二月',
        // 按钮
        'Today':'今日','today':'今日',
    };

    function sweep() {
        const cals = doc.querySelectorAll('[data-baseweb="calendar"]');
        cals.forEach(cal => {
            const walker = doc.createTreeWalker(cal, NodeFilter.SHOW_TEXT);
            let node;
            while ((node = walker.nextNode())) {
                const t = node.textContent.trim();
                if (map[t]) node.textContent = map[t];
            }
        });
    }

    new MutationObserver(() => requestAnimationFrame(sweep))
        .observe(doc.body, { childList: true, subtree: true });
    sweep();
})();
</script>
""",
    height=0,
)

# 侧边栏 logo（折叠态也会显示一个小图）
st.logo(LOGO_PATH, size="large")

# 主页面：logo + 标题横向并排
_header_cols = st.columns([1, 6])
with _header_cols[0]:
    st.image(LOGO_PATH, width=130)
with _header_cols[1]:
    st.title("协纪")
    st.caption("黄历择吉综合工具 · 建除黄黑道 · 二十八宿 · 神煞 · 时辰 · 方位 · 八字 · 合婚 · 紫微")
st.markdown("")  # 与下方 sidebar/tab 留一行间距

# ============================================================
# 全局设置（侧边栏）
# ============================================================
with st.sidebar:
    st.header("⚙️ 全局设置")
    school = st.selectbox(
        "择吉流派", list(SCHOOL_WEIGHTS.keys()),
        help="不同流派对神煞/宜忌的权重不同，结果会有差异。",
    )
    city = st.selectbox(
        "出生地（真太阳时校正）", ["不校正"] + list(CITY_LONGITUDE.keys()),
        index=0,
        help="非北京时间地区，出生时柱会因经度有所偏移；选择城市自动校正。",
    )
    st.markdown("---")
    st.subheader("🤖 AI 解读")
    use_llm = st.checkbox(
        "启用 LLM 深度解读",
        value=False,
        help="使用 Claude / OpenAI 兼容 API 生成深度解读；未配置时降级为规则式。",
    )

    llm_config: Optional[LLMConfig] = None
    if use_llm:
        # 1. 选 provider
        provider_label = st.selectbox(
            "API 类型",
            ["Anthropic (Claude)", "OpenAI 兼容"],
            help="Anthropic：Claude 原生 + 兼容代理。OpenAI 兼容：覆盖 OpenAI / DeepSeek / Moonshot / 智谱 / 通义 / Ollama / vLLM 等。",
        )
        provider = PROVIDER_ANTHROPIC if provider_label.startswith("Anthropic") else PROVIDER_OPENAI

        # 2. 选预设端点
        endpoint_options = list(BASE_URL_PRESETS[provider].keys())
        endpoint_label = st.selectbox(
            "端点 / 服务商",
            endpoint_options,
            help="选预设端点会自动填好 base_url；选'自定义'后手填。",
        )
        preset_url = BASE_URL_PRESETS[provider][endpoint_label]

        # 3. base_url 输入（自定义时显示）
        if preset_url == "custom":
            base_url = st.text_input(
                "Base URL", value="",
                placeholder="https://your-endpoint.com/v1",
                help="兼容 OpenAI/Anthropic 协议的完整 API 地址。",
            )
        else:
            base_url = preset_url
            if base_url:
                st.caption(f"📍 base_url: `{base_url}`")

        # 4. API key
        env_key = (
            os.environ.get("ANTHROPIC_API_KEY", "") if provider == PROVIDER_ANTHROPIC
            else os.environ.get("OPENAI_API_KEY", "")
        )
        api_key_input = st.text_input(
            "API Key",
            value=env_key,
            type="password",
            help="留空将报错；填入后会临时使用。",
        )

        # 5. 模型选择（按 provider + endpoint 决定预设列表）
        if provider == PROVIDER_ANTHROPIC:
            model_presets = MODEL_PRESETS[PROVIDER_ANTHROPIC]["default"]
        else:
            model_presets = MODEL_PRESETS[PROVIDER_OPENAI].get(
                endpoint_label, [("custom", "(自定义)")]
            )
        model_options = [m[0] for m in model_presets] + ["(自定义模型名)"]
        model_format = {m[0]: f"{m[0]} - {m[1]}" for m in model_presets}
        model_format["(自定义模型名)"] = "(自定义模型名)"
        model_choice = st.selectbox(
            "模型",
            model_options,
            format_func=lambda x: model_format.get(x, x),
        )
        if model_choice == "(自定义模型名)":
            model = st.text_input("自定义模型名", value="", placeholder="如 gpt-4o-2024-08-06")
        else:
            model = model_choice

        llm_config = LLMConfig(
            provider=provider,
            model=model,
            api_key=api_key_input,
            base_url=base_url,
        )
        if llm_config.is_usable():
            st.caption(f"✓ {provider_label} · {model}")
        else:
            st.caption("⚠ 配置不完整，将降级为规则式")

    st.markdown("---")

    # === 查询历史与收藏 ===
    if "query_history" not in st.session_state:
        st.session_state.query_history = []  # list of ISO date strings, newest first
    if "favorites" not in st.session_state:
        st.session_state.favorites = []      # list of ISO date strings

    with st.expander("📚 历史 / 收藏", expanded=False):
        if st.session_state.favorites:
            st.markdown("**⭐ 收藏**")
            for fav in st.session_state.favorites[:10]:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"[`{fav}`](?date={fav})")
                if c2.button("✕", key=f"unfav_{fav}", help="移除收藏"):
                    st.session_state.favorites.remove(fav)
                    st.rerun()
            st.markdown("---")

        if st.session_state.query_history:
            st.markdown("**🕘 最近查询**")
            for h in st.session_state.query_history[:8]:
                c1, c2 = st.columns([4, 1])
                c1.code(h, language=None)
                if c2.button("⭐", key=f"fav_{h}", help="加入收藏"):
                    if h not in st.session_state.favorites:
                        st.session_state.favorites.insert(0, h)
                        st.rerun()
        else:
            st.caption("尚无查询记录")

        if st.session_state.query_history or st.session_state.favorites:
            if st.button("🗑 清空历史", key="clear_hist"):
                st.session_state.query_history = []
                st.rerun()

    st.markdown("---")

    # === 我的生辰（用于个人每日运势） ===
    with st.expander("👤 我的生辰（用于个人评分）", expanded=False):
        if "my_birth" not in st.session_state:
            st.session_state.my_birth = None
        _my_enabled = st.checkbox(
            "启用个人每日运势",
            value=(st.session_state.my_birth is not None),
            key="my_birth_enabled",
        )
        if _my_enabled:
            _mc1, _mc2 = st.columns(2)
            with _mc1:
                _my_date = st.date_input(
                    "出生日期", value=date(1990, 1, 1),
                    min_value=date(1900, 1, 1), max_value=today_cn(),
                    key="my_birth_date",
                )
            with _mc2:
                _my_time = st.time_input(
                    "出生时间", value=time(12, 0),
                    key="my_birth_time",
                )
            _my_gender = st.selectbox("性别", ["男", "女"], key="my_birth_gender")
            _my_dt = datetime.combine(_my_date, _my_time)
            if city != "不校正":
                _my_dt = correct_birth_to_true_solar(_my_dt, city)
            try:
                _my_bz = build_bazi(_my_dt, gender=1 if _my_gender == "男" else 0)
                st.session_state.my_birth = {
                    "label": "本人",
                    "year_zhi": _my_bz.year_zhi,
                    "year_shengxiao": _my_bz.shengxiao,
                    "day_gan_wuxing": _my_bz.day_gan_wuxing,
                    "yong_shen": _my_bz.yong_shen,
                }
                st.caption(
                    f"✓ {_my_bz.year.ganzhi} {_my_bz.month.ganzhi} {_my_bz.day.ganzhi} {_my_bz.hour.ganzhi}　·　"
                    f"{_my_bz.shengxiao}　·　日主 {_my_bz.day_gan}({_my_bz.day_gan_wuxing})"
                )
            except Exception as e:
                st.session_state.my_birth = None
                st.caption(f"⚠ 排盘失败：{e}")
        else:
            st.session_state.my_birth = None

    st.markdown("---")
    st.caption("💡 本工具为文化参考，非命定预测。")


def maybe_correct(dt: datetime) -> datetime:
    if city != "不校正":
        return correct_birth_to_true_solar(dt, city)
    return dt


def llm_or_rule_summary(result: dict, event: Optional[str] = None,
                       persons: Optional[list[dict]] = None) -> str:
    """根据 sidebar 设置选择 LLM 或规则式解读。"""
    if use_llm and llm_config is not None:
        r = interpret_via_llm(result, event=event, persons=persons, config=llm_config)
        text = r["text"]
        if r.get("fallback"):
            return text
        usage = r.get("usage", {})
        cache_info = ""
        if usage.get("cache_read_input_tokens", 0) > 0:
            cache_info = f" · 缓存命中 {usage['cache_read_input_tokens']} tokens"
        return f"{text}\n\n_(模型: {r['model']} · 输入 {usage.get('input_tokens',0)} / 输出 {usage.get('output_tokens',0)}{cache_info})_"
    return natural_language_summary(result)


# ============================================================
# 今日速览 hero（在 tabs 之上，打开即见）
# ============================================================
_today = today_cn()
_today_a = get_day_almanac(_today)

# 如果用户在侧栏配置了"我的生辰"，hero 评分就以个人视角计算
_my_persons = [st.session_state["my_birth"]] if st.session_state.get("my_birth") else []
_today_sb = score_day(_today_a, persons=_my_persons, school=school)
_today_v = verdict(_today_sb.score, _today_sb.fatal)

_HERO_COLOR_MAP = {
    "上吉": "#1b5e20", "吉": "#2e7d32", "中平": "#f9a825",
    "次": "#ef6c00", "凶": "#b71c1c", "大凶 · 不取": "#7f0000",
}
_hero_color = _HERO_COLOR_MAP.get(_today_v, "#555")

# === 节气主题：按当前节气期判定季节，给 hero 上色 ===
# 春青、夏赤、秋白、冬玄
_SEASON_THEMES = {
    "春": {"bg": "#eef7ee", "border": "#2e7d32", "name": "春 · 木青"},
    "夏": {"bg": "#fdecea", "border": "#c62828", "name": "夏 · 火赤"},
    "秋": {"bg": "#f8f5f0", "border": "#a98c5d", "name": "秋 · 金白"},
    "冬": {"bg": "#eaf1f7", "border": "#1565c0", "name": "冬 · 水玄"},
}
_SPRING_JQ = {"立春", "雨水", "惊蛰", "春分", "清明", "谷雨"}
_SUMMER_JQ = {"立夏", "小满", "芒种", "夏至", "小暑", "大暑"}
_AUTUMN_JQ = {"立秋", "处暑", "白露", "秋分", "寒露", "霜降"}
_WINTER_JQ = {"立冬", "小雪", "大雪", "冬至", "小寒", "大寒"}


def _season_of(jq_name: str) -> str:
    if jq_name in _SPRING_JQ:
        return "春"
    if jq_name in _SUMMER_JQ:
        return "夏"
    if jq_name in _AUTUMN_JQ:
        return "秋"
    if jq_name in _WINTER_JQ:
        return "冬"
    return ""


_phase = current_jieqi_phase(_today)
_season = _season_of(_phase.get("current") or _phase.get("next") or "")
_theme = _SEASON_THEMES.get(_season)

# 主题色 CSS 注入（仅作用于 hero 容器，避免影响其它部分）
if _theme:
    st.markdown(
        f"""
<style>
[data-testid="stMainBlockContainer"] div[data-testid="stVerticalBlockBorderWrapper"]:first-of-type {{
    background: {_theme['bg']};
    border-color: {_theme['border']} !important;
}}
</style>
""",
        unsafe_allow_html=True,
    )

with st.container(border=True):
    if _theme:
        st.caption(f"🍃 当前节气期 · {_theme['name']}")
    hc1, hc2, hc3, hc4 = st.columns([1.3, 2.5, 3.5, 1.7])
    with hc1:
        st.markdown(
            f"<div style='text-align:center'>"
            f"<div style='color:#888;font-size:12px;margin-bottom:2px'>今　日</div>"
            f"<div style='color:{_hero_color};font-size:30px;font-weight:bold;line-height:1.2'>{_today_v}</div>"
            f"<div style='color:#666;font-size:13px;margin-top:4px'>{_today_sb.score} / 100</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with hc2:
        st.markdown(f"### {_today.isoformat()}")
        st.caption(f"{_today_a.lunar_str}")
        st.caption(f"{_today_a.ganzhi_year}年 {_today_a.ganzhi_month}月 **{_today_a.ganzhi_day}日**　·　{_today_a.shengxiao_year}年")
        st.caption(f"建除【{_today_a.jianchu}】 · {_today_a.tianshen}（{_today_a.tianshen_type}） · {_today_a.xiu}宿（{_today_a.xiu_luck}）")
    with hc3:
        _yi_text = "　".join(_today_a.yi[:8]) if _today_a.yi else "—"
        _ji_text = "　".join(_today_a.ji[:8]) if _today_a.ji else "—"
        st.markdown(
            f"<div style='line-height:1.7'>"
            f"<span style='color:#2e7d32;font-weight:bold'>宜　</span>"
            f"<span style='color:#1b5e20'>{_yi_text}</span><br>"
            f"<span style='color:#c62828;font-weight:bold'>忌　</span>"
            f"<span style='color:#7f0000'>{_ji_text}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
    with hc4:
        st.markdown(f"**冲煞**　{_today_a.chong_desc}")
        st.caption(f"煞 {_today_a.sha}")
        st.caption(f"喜神 {_today_a.xi_shen_fang}　财神 {_today_a.cai_shen_fang}")

st.markdown("")  # 与下方 tabs 留一行

# 9 个 Tab
TABS = st.tabs([
    "📅 单日吉凶", "💍 择吉推荐", "🗓 月历视图",
    "🎴 八字排盘", "🧭 方位罗盘", "❤️ 合婚",
    "🌿 节令", "⭐ 紫微斗数", "📊 并排比较", "⚙️ 设置说明",
])


# ============================================================
# Helper: 渲染单日完整卡片
# ============================================================
def render_almanac_card(a, score: int, v: str):
    color_map = {
        "上吉": "#1b5e20", "吉": "#2e7d32", "中平": "#f9a825",
        "次": "#ef6c00", "凶": "#b71c1c", "大凶 · 不取": "#7f0000",
    }
    color = color_map.get(v, "#555")
    st.markdown(
        f"<h2 style='color:{color};margin-bottom:0'>{v}　·　{score}/100</h2>",
        unsafe_allow_html=True,
    )
    st.markdown(f"### {a.solar_date.isoformat()} · {a.lunar_str}")

    hol = holiday_of(a.solar_date)
    if hol:
        st.info(f"🏮 公历节假日：{hol}")

    info = {
        "干支": f"{a.ganzhi_year}年 {a.ganzhi_month}月 {a.ganzhi_day}日",
        "生肖年": a.shengxiao_year,
        "日主": f"{a.day_gan}({a.day_gan_wuxing}) · 日支 {a.day_zhi}({a.day_zhi_wuxing})",
        "纳音": a.nayin,
        "建除": a.jianchu,
        "黄黑道": f"{a.tianshen}({a.tianshen_type}·{a.tianshen_luck})",
        "二十八宿": f"{a.xiu}({a.xiu_luck})",
        "冲煞": f"冲 {a.chong_desc}，煞 {a.sha}",
        "喜神方位": a.xi_shen_fang,
        "财神方位": a.cai_shen_fang,
        "彭祖百忌": f"{a.pengzu_gan}；{a.pengzu_zhi}",
    }
    cols = st.columns(3)
    for i, (k, v_) in enumerate(info.items()):
        cols[i % 3].markdown(f"**{k}**：{v_}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 宜")
        if a.yi:
            st.success("　".join(a.yi))
        else:
            st.write("—")
    with c2:
        st.markdown("#### 忌")
        if a.ji:
            st.error("　".join(a.ji))
        else:
            st.write("—")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 吉神")
        st.write("、".join(a.jishen) if a.jishen else "—")
    with c2:
        st.markdown("#### 凶煞")
        st.write("、".join(a.xiongsha) if a.xiongsha else "—")


def render_breakdown(reasons: list[str]):
    pos = [r for r in reasons if r.startswith("+")]
    neg = [r for r in reasons if r.startswith("-")]
    fatal = [r for r in reasons if r.startswith("⚠")]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**加分项**")
        for r in pos:
            st.markdown(f"<span style='color:#2e7d32'>{r}</span>", unsafe_allow_html=True)
    with c2:
        st.markdown("**扣分项**")
        for r in neg:
            st.markdown(f"<span style='color:#c62828'>{r}</span>", unsafe_allow_html=True)
    if fatal:
        st.error("　".join(fatal))


def render_taboos(taboos: dict):
    if not taboos:
        return
    bad = {k: v for k, v in taboos.items() if k != "不将日(嫁娶吉)"}
    good = {k: v for k, v in taboos.items() if k == "不将日(嫁娶吉)"}
    if bad:
        st.warning("**传统凶日命中**：" + "、".join(bad.keys()))
    if good:
        st.success("**传统吉日命中**：" + "、".join(good.keys()))


def render_sources(a, taboos: dict):
    """展开查看当日各项规则的典籍出处。"""
    with st.expander("📖 算法 / 典籍依据（点开查看引文）", expanded=False):
        rows = []
        s = source_for("huangdao", a.tianshen)
        if s:
            rows.append(("黄黑道", a.tianshen, s))
        s = source_for("jianchu", a.jianchu)
        if s:
            rows.append(("建除十二神", a.jianchu, s))
        s = source_for("xiu", a.xiu)
        if s:
            rows.append(("二十八宿", a.xiu, s))
        for name in a.jishen:
            s = source_for("jishen", name)
            if s:
                rows.append(("吉神", name, s))
        for name in (taboos or {}):
            s = source_for("taboo", name)
            if s:
                rows.append(("凶日 / 神煞", name, s))
        if not rows:
            st.caption("当日命中规则均为通行常识，无典籍引文。")
            return
        for kind, name, src in rows:
            st.markdown(f"**【{kind} · {name}】**　{src}")


def render_hour_table(d: date):
    slots = get_hour_slots(d)
    df = pd.DataFrame([
        {
            "时辰": s.name,
            "时段": f"{s.start_hm}-{s.end_hm}",
            "干支": s.ganzhi,
            "黄黑道": f"{s.tianshen}({s.tianshen_type})",
            "冲": s.shengxiao,
            "喜神": s.xi_dir,
            "财神": s.cai_dir,
            "贵神": s.yang_gui_dir,
            "评分": s.score,
        }
        for s in slots
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


def persons_input(prefix: str, count: int = 1) -> list[dict]:
    """通用多当事人输入控件。"""
    out = []
    for i in range(count):
        with st.expander(f"当事人 {i+1}", expanded=(i == 0)):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                label = st.text_input(
                    "称谓", value=["主当事人", "配偶/伙伴", "其他亲属", "其他"][i] if i < 4 else f"人{i+1}",
                    key=f"{prefix}_label_{i}",
                )
            with c2:
                b_date = st.date_input(
                    "出生日期", value=date(1990, 1, 1),
                    min_value=date(1900, 1, 1), max_value=today_cn(),
                    key=f"{prefix}_bd_{i}",
                )
            with c3:
                b_time = st.time_input(
                    "出生时间", value=time(12, 0),
                    key=f"{prefix}_bt_{i}",
                )
            with c4:
                gender = st.selectbox(
                    "性别", ["男", "女"], key=f"{prefix}_g_{i}",
                )
            dt = maybe_correct(datetime.combine(b_date, b_time))
            bz = build_bazi(dt, gender=1 if gender == "男" else 0)
            out.append({
                "label": label,
                "year_zhi": bz.year_zhi,
                "year_shengxiao": bz.shengxiao,
                "day_gan_wuxing": bz.day_gan_wuxing,
                "yong_shen": bz.yong_shen,
                "_bazi": bz,
                "_gender": gender,
                "_dt": dt,
            })
            st.caption(
                f"四柱：{bz.year.ganzhi} {bz.month.ganzhi} {bz.day.ganzhi} {bz.hour.ganzhi}　"
                f"日主：{bz.day_gan}({bz.day_gan_wuxing})　生肖：{bz.shengxiao}　"
                f"强弱：{bz.strength}　喜用：{'/'.join(bz.yong_shen)}"
            )
    return out


# ============================================================
# Tab 1: 单日吉凶
# ============================================================
with TABS[0]:
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        query_date = st.date_input(
            "查询日期", value=today_cn(),
            min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
            key="single_date",
        )
    with c2:
        event_opt = st.selectbox(
            "事项（可选）", ["（不指定·通用吉凶）"] + list(EVENT_KEYWORDS.keys()),
            key="single_event",
        )
    with c3:
        person_count = st.number_input("当事人数", min_value=0, max_value=4, value=0, step=1, key="single_pc")

    persons = persons_input("single", person_count) if person_count > 0 else []
    event_arg = None if event_opt.startswith("（不") else event_opt

    a = get_day_almanac(query_date)
    sb = score_day(a, event=event_arg, persons=persons, school=school)
    v = verdict(sb.score, sb.fatal)

    render_almanac_card(a, sb.score, v)
    render_taboos(sb.taboos)
    render_sources(a, sb.taboos)

    # 记录查询历史 + 收藏按钮
    _q_iso = query_date.isoformat()
    if _q_iso in st.session_state.query_history:
        st.session_state.query_history.remove(_q_iso)
    st.session_state.query_history.insert(0, _q_iso)
    st.session_state.query_history = st.session_state.query_history[:20]

    _fav_c1, _fav_c2 = st.columns([1, 4])
    with _fav_c1:
        _is_fav = _q_iso in st.session_state.favorites
        if st.button(
            "⭐ 已收藏" if _is_fav else "☆ 收藏此日",
            key="single_fav_btn",
        ):
            if _is_fav:
                st.session_state.favorites.remove(_q_iso)
            else:
                st.session_state.favorites.insert(0, _q_iso)
            st.rerun()
    with _fav_c2:
        if st.session_state.favorites and not _is_fav:
            st.caption(f"已收藏 {len(st.session_state.favorites)} 个日期")

    st.markdown("---")
    st.markdown("### ⏰ 12 时辰盘")
    render_hour_table(query_date)

    st.markdown("---")
    st.markdown("### 📊 评分明细")
    render_breakdown(sb.reasons)

    # 节令信息
    phase = current_jieqi_phase(query_date)
    if phase["next"]:
        st.info(
            f"🌿 节令：当前节气期【{phase['current'] or '—'}】，"
            f"下个节气【{phase['next']}】在 {phase['next_moment']:%Y-%m-%d %H:%M}（{phase['days_to_next']} 天后）。"
            f"　月相：{moon_phase(query_date)}"
        )

    st.markdown("### 📝 自然语言解读")
    result = {
        "almanac": a, "score": sb.score, "verdict": v,
        "reasons": sb.reasons, "taboos": sb.taboos, "date": query_date,
    }
    with st.spinner("生成解读中…" if use_llm else None):
        st.markdown(llm_or_rule_summary(result, event=event_arg, persons=persons))

    # 导出
    st.markdown("---")
    exp_c1, exp_c2 = st.columns(2)
    with exp_c1:
        if st.button("📄 生成传统老黄历 PDF", key="single_pdf_btn", use_container_width=True):
            with st.spinner("生成 PDF 中…"):
                pdf_bytes = render_huangli_pdf(query_date)
            st.download_button(
                "📥 下载 PDF",
                data=pdf_bytes,
                file_name=f"huangli_{query_date.isoformat()}.pdf",
                mime="application/pdf",
                key="single_pdf_dl",
                use_container_width=True,
            )
    with exp_c2:
        if st.button("🖼️ 生成分享海报 PNG", key="single_png_btn", use_container_width=True):
            with st.spinner("生成海报中…"):
                png_bytes = render_share_poster(query_date, event=event_arg, school=school)
            st.download_button(
                "📥 下载海报",
                data=png_bytes,
                file_name=f"xieji_{query_date.isoformat()}.png",
                mime="image/png",
                key="single_png_dl",
                use_container_width=True,
            )
            st.image(png_bytes, caption="海报预览", width=320)


# ============================================================
# Tab 2: 择吉推荐
# ============================================================
with TABS[1]:
    st.markdown("**为重大事项推荐吉日，支持多当事人合参、流派切换、工作日筛选、iCal 导出。**")

    c1, c2, c3 = st.columns(3)
    with c1:
        event = st.selectbox("事项类型", list(EVENT_KEYWORDS.keys()), key="rec_event")
    with c2:
        top_n = st.slider("展示数量", min_value=5, max_value=50, value=10, key="rec_topn")
    with c3:
        person_count2 = st.number_input("当事人数", min_value=0, max_value=4, value=1, step=1, key="rec_pc")

    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input(
            "搜索起点", value=today_cn(),
            min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
            key="rec_start",
        )
    with c2:
        search_days = st.slider("搜索天数", min_value=30, max_value=365, value=365, step=30, key="rec_days")

    weekday_filter = st.multiselect(
        "排除星期（不希望事项落在某些星期可勾选）",
        ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        default=[],
        placeholder="留空 = 不排除任何星期",
        key="rec_wd",
    )
    weekday_map = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
    exclude_weekdays = {weekday_map[w] for w in weekday_filter}

    persons2 = persons_input("rec", person_count2) if person_count2 > 0 else []

    if st.button("🔮 推算吉日", type="primary", key="rec_btn"):
        with st.spinner(f"正在排算 {search_days} 天黄历…"):
            results = recommend_days(
                event=event, persons=persons2,
                start=start_date, days=search_days, top_n=top_n,
                school=school, exclude_weekdays=exclude_weekdays or None,
            )
        st.session_state["last_results"] = results
        st.session_state["last_event"] = event

    results = st.session_state.get("last_results", [])
    if not results:
        st.caption("点击上方按钮开始推算。")
    else:
        # 概览表（婚嫁事件时多加一列周堂）
        rows = []
        for r in results:
            row = {
                "公历": r["date"].isoformat(),
                "星期": ["一", "二", "三", "四", "五", "六", "日"][r["date"].weekday()],
                "农历": r["almanac"].lunar_str,
                "干支日": r["almanac"].ganzhi_day,
                "评分": r["score"],
                "等级": r["verdict"],
                "明确宜": "✓" if r["hit_yi"] else "",
                "冲": r["almanac"].chong_shengxiao,
                "节假": holiday_of(r["date"]) or "",
                "凶日": "、".join(k for k in r.get("taboos", {}).keys() if k != "不将日(嫁娶吉)")[:30],
            }
            if st.session_state.get("last_event") == "婚嫁":
                zt = zhoutang_for_wedding(r["date"])
                row["周堂"] = f"{zt['position']}({zt['luck']})"
            row["宜"] = "、".join(r["almanac"].yi[:5])
            rows.append(row)
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # 导出
        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "📥 iCal (日历)",
                data=export_ical(results, st.session_state.get("last_event", "黄道吉日")),
                file_name=f"jiri_{today_cn().isoformat()}.ics",
                mime="text/calendar",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "📥 JSON",
                data=export_json(results),
                file_name=f"jiri_{today_cn().isoformat()}.json",
                mime="application/json",
                use_container_width=True,
            )
        with c3:
            if st.button("📄 头名 PDF 老黄历", use_container_width=True, key="rec_pdf_btn"):
                top_date = results[0]["date"]
                pdf_bytes = render_huangli_pdf(top_date)
                st.download_button(
                    "📥 下载 PDF",
                    data=pdf_bytes,
                    file_name=f"huangli_{top_date.isoformat()}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )

        st.markdown("---")
        st.markdown("### 详细解读")
        for i, r in enumerate(results[:min(5, len(results))], 1):
            with st.expander(
                f"#{i}　{r['date'].isoformat()} ({r['almanac'].ganzhi_day}日) · {r['verdict']} · {r['score']}/100",
                expanded=(i == 1),
            ):
                render_almanac_card(r["almanac"], r["score"], r["verdict"])
                render_taboos(r.get("taboos", {}))
                if st.session_state.get("last_event") == "婚嫁":
                    zt = zhoutang_for_wedding(r["date"])
                    avoid = avoid_persons_for_zhoutang(zt["position"])
                    if zt["luck"] == "凶":
                        msg = f"🌀 嫁娶周堂落【{zt['position']}】 — {zt['desc']}"
                        if avoid:
                            msg += f"，建议 {' / '.join(avoid)} 短暂回避礼堂"
                        st.warning(msg)
                    else:
                        st.success(f"🌀 嫁娶周堂落【{zt['position']}】 — {zt['desc']}")
                st.markdown("**时辰盘**")
                render_hour_table(r["date"])
                st.markdown("**评分明细**")
                render_breakdown(r["reasons"])
                st.markdown("**解读**")
                st.markdown(llm_or_rule_summary(r, event=st.session_state.get("last_event")))


# ============================================================
# Tab 3: 月历视图
# ============================================================
with TABS[2]:
    st.markdown("**整月吉凶速览**：单元格按事项评分上色，鼠标悬停查看农历。")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        m_year = st.number_input("年", value=today_cn().year, min_value=1900, max_value=2100, key="mv_y")
    with c2:
        m_month = st.number_input("月", value=today_cn().month, min_value=1, max_value=12, key="mv_m")
    with c3:
        m_event = st.selectbox("评分按事项", ["（通用吉凶）"] + list(EVENT_KEYWORDS.keys()), key="mv_e")
    m_event_arg = None if m_event.startswith("（") else m_event

    # 计算该月每日评分
    first = date(int(m_year), int(m_month), 1)
    if first.month == 12:
        next_m = date(first.year + 1, 1, 1)
    else:
        next_m = date(first.year, first.month + 1, 1)
    days_in_month = (next_m - first).days

    rows = []
    for day in range(1, days_in_month + 1):
        d = date(first.year, first.month, day)
        a = get_day_almanac(d)
        sb = score_day(a, event=m_event_arg, school=school)
        rows.append({
            "date": d, "weekday": d.weekday(),
            "score": sb.score, "fatal": sb.fatal,
            "verdict": verdict(sb.score, sb.fatal),
            "lunar": a.lunar_str.split("年")[-1],
            "ganzhi": a.ganzhi_day,
            "chong": a.chong_shengxiao,
        })

    # 渲染日历表（6 周 × 7 天）
    leading_blanks = (first.weekday() + 1) % 7  # 周日为第一列（西历惯例）
    # 这里用周一作第一列，匹配国内惯例
    leading_blanks = first.weekday()

    cells = [None] * leading_blanks + rows
    while len(cells) % 7 != 0:
        cells.append(None)

    def color_for(r):
        if r is None:
            return "transparent"
        if r["fatal"]:
            return "#ffcdd2"
        if r["score"] >= 80:
            return "#c8e6c9"
        if r["score"] >= 65:
            return "#dcedc8"
        if r["score"] >= 50:
            return "#fff9c4"
        if r["score"] >= 35:
            return "#ffe0b2"
        return "#ffccbc"

    header = ["一", "二", "三", "四", "五", "六", "日"]
    html = ["<table style='width:100%;border-collapse:collapse;text-align:center;font-size:13px;'>"]
    html.append("<tr>" + "".join(
        f"<th style='padding:6px;border:1px solid #ddd;background:#fafafa'>周{h}</th>"
        for h in header
    ) + "</tr>")
    for w in range(0, len(cells), 7):
        html.append("<tr>")
        for r in cells[w:w + 7]:
            if r is None:
                html.append("<td style='border:1px solid #eee;padding:6px;height:60px'></td>")
            else:
                col = color_for(r)
                badge = "⚠" if r["fatal"] else ""
                tooltip = f"{r['ganzhi']}日 冲{r['chong']} {r['verdict']} {r['score']}/100"
                html.append(
                    f"<td title='{tooltip}' style='border:1px solid #ddd;padding:4px;background:{col};height:60px;vertical-align:top'>"
                    f"<div style='font-size:16px;font-weight:bold'>{r['date'].day}{badge}</div>"
                    f"<div style='color:#555;font-size:11px'>{r['lunar']}</div>"
                    f"<div style='color:#777;font-size:10px'>{r['score']}</div>"
                    f"</td>"
                )
        html.append("</tr>")
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.caption("色阶：深绿=上吉、浅绿=吉、米黄=中平、橙=次、橙红=凶、粉红=大凶")


# ============================================================
# Tab 4: 八字排盘
# ============================================================
with TABS[3]:
    st.markdown("**输入生辰，输出完整四柱、十神、藏干、纳音、强弱、喜用神、大运。**")
    c1, c2, c3 = st.columns(3)
    with c1:
        bz_date = st.date_input("出生日期", value=date(1990, 1, 1),
                                min_value=date(1900, 1, 1), max_value=today_cn(),
                                key="bz_date")
    with c2:
        bz_time = st.time_input("出生时间", value=time(12, 0), key="bz_time")
    with c3:
        bz_gender = st.selectbox("性别", ["男", "女"], key="bz_gender")

    dt = maybe_correct(datetime.combine(bz_date, bz_time))
    if city != "不校正":
        st.caption(f"已按【{city}】校正真太阳时：{bz_time} → {dt:%H:%M:%S}")
    bz = build_bazi(dt, gender=1 if bz_gender == "男" else 0)

    st.markdown(f"### 四柱：{bz.year.ganzhi}　{bz.month.ganzhi}　{bz.day.ganzhi}　{bz.hour.ganzhi}")

    df = pd.DataFrame([
        {"项": "天干", "年柱": bz.year.gan, "月柱": bz.month.gan, "日柱": bz.day.gan + "(日主)", "时柱": bz.hour.gan},
        {"项": "地支", "年柱": bz.year.zhi, "月柱": bz.month.zhi, "日柱": bz.day.zhi, "时柱": bz.hour.zhi},
        {"项": "天干十神", "年柱": bz.year.shi_shen_gan, "月柱": bz.month.shi_shen_gan, "日柱": "—", "时柱": bz.hour.shi_shen_gan},
        {"项": "地支十神", "年柱": "/".join(bz.year.shi_shen_zhi), "月柱": "/".join(bz.month.shi_shen_zhi),
         "日柱": "/".join(bz.day.shi_shen_zhi), "时柱": "/".join(bz.hour.shi_shen_zhi)},
        {"项": "藏干", "年柱": "/".join(bz.year.hide_gan), "月柱": "/".join(bz.month.hide_gan),
         "日柱": "/".join(bz.day.hide_gan), "时柱": "/".join(bz.hour.hide_gan)},
        {"项": "纳音", "年柱": bz.year.nayin, "月柱": bz.month.nayin, "日柱": bz.day.nayin, "时柱": bz.hour.nayin},
        {"项": "旬空", "年柱": bz.year.xun_kong, "月柱": bz.month.xun_kong, "日柱": bz.day.xun_kong, "时柱": bz.hour.xun_kong},
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("生肖", bz.shengxiao)
    c2.metric("胎元 / 命宫 / 身宫", f"{bz.tai_yuan} / {bz.ming_gong} / {bz.shen_gong}")
    c3.metric("起运", bz.start_yun)

    st.markdown("### 五行强弱")
    wx_df = pd.DataFrame([
        {"五行": k, "权重": v} for k, v in bz.wuxing_count.items()
    ])
    c1, c2 = st.columns([2, 3])
    with c1:
        st.bar_chart(wx_df.set_index("五行"))
    with c2:
        st.markdown(f"**日主**：{bz.day_gan}（{bz.day_gan_wuxing}）")
        st.markdown(f"**强弱**：{bz.strength}　（综合评分 {bz.strength_score}）")
        st.markdown(f"**喜用神**：{'、'.join(bz.yong_shen)}")
        st.markdown(f"**忌神**：{'、'.join(bz.ji_shen)}")

    st.markdown("### 大运排列 + 深度解读")
    yun_eval = evaluate_dayun(bz)
    yun_df = pd.DataFrame([
        {
            "起始年龄": d["start_age"],
            "结束年龄": d["end_age"],
            "起始公历年": d["start_year"],
            "大运干支": d["ganzhi"],
            "五行": f"{d['gan_wuxing']}/{d['zhi_wuxing']}",
            "评分": d["score"],
            "等级": d["verdict"],
        }
        for d in yun_eval
    ])
    st.dataframe(yun_df, use_container_width=True, hide_index=True)

    # 可视化：横向时间线（柱长 = 10 年，色深 = 评分）
    st.markdown("##### 大运时间线（色深=评分高低）")
    _verdict_color = {
        "佳运": "#1b5e20", "顺运": "#558b2f", "平运": "#f9a825",
        "蹇运": "#ef6c00", "厄运": "#b71c1c",
    }
    if yun_eval:
        _min_year = yun_eval[0]["start_year"]
        _max_year = yun_eval[-1]["start_year"] + 10
        _span = max(1, _max_year - _min_year)
        _tl_w = 900
        _tl_h = 70
        _seg_h = 36
        _tl_html = [
            f'<svg viewBox="0 0 {_tl_w} {_tl_h}" '
            f'style="width:100%;max-width:{_tl_w}px;background:#fafafa;border:1px solid #ddd;border-radius:4px">'
        ]
        for d in yun_eval:
            x = int((d["start_year"] - _min_year) / _span * (_tl_w - 40)) + 20
            w = int(10 / _span * (_tl_w - 40))
            opacity = 0.3 + (d["score"] / 100) * 0.7
            color = _verdict_color.get(d["verdict"], "#888")
            _tl_html.append(
                f'<rect x="{x}" y="20" width="{w}" height="{_seg_h}" '
                f'fill="{color}" fill-opacity="{opacity:.2f}" stroke="{color}" stroke-width="0.5"/>'
            )
            _tl_html.append(
                f'<text x="{x + w // 2}" y="{20 + _seg_h // 2 + 4}" text-anchor="middle" '
                f'fill="#fff" font-size="11" font-weight="bold">{d["ganzhi"]}</text>'
            )
            _tl_html.append(
                f'<text x="{x + w // 2}" y="14" text-anchor="middle" fill="#666" font-size="10">'
                f'{d["start_age"]}岁</text>'
            )
            _tl_html.append(
                f'<text x="{x + w // 2}" y="{20 + _seg_h + 12}" text-anchor="middle" '
                f'fill="#888" font-size="10">{d["start_year"]}</text>'
            )
        _tl_html.append("</svg>")
        st.markdown("".join(_tl_html), unsafe_allow_html=True)

    # 评分柱状图
    st.markdown("##### 大运评分分布")
    chart_df = pd.DataFrame([
        {"大运": f"{d['start_age']}岁 {d['ganzhi']}", "评分": d["score"], "等级": d["verdict"]}
        for d in yun_eval
    ])
    st.bar_chart(chart_df.set_index("大运")["评分"], height=200)

    for i, d in enumerate(yun_eval[:6]):
        col_map = {"佳运": "#1b5e20", "顺运": "#388e3c", "平运": "#f9a825",
                   "蹇运": "#ef6c00", "厄运": "#b71c1c"}
        col = col_map.get(d["verdict"], "#555")
        with st.expander(
            f"{d['start_age']}–{d['end_age']}岁　{d['ganzhi']}　·　{d['verdict']}　({d['score']}/100)",
            expanded=(i == 0),
        ):
            st.markdown(f"<p style='color:{col}'>{d['narrative']}</p>", unsafe_allow_html=True)
            for r in d["reasons"]:
                st.markdown(f"- {r}")

    # 流年评估
    st.markdown("### 流年评估")
    c1, c2 = st.columns([1, 3])
    with c1:
        ly_year = st.number_input(
            "流年", value=today_cn().year, min_value=1900, max_value=2100, key="ly_y",
        )
    target_dy = None
    for d in yun_eval:
        if d["start_year"] <= int(ly_year) < d["start_year"] + 10:
            target_dy = d
            break
    if target_dy:
        ly = evaluate_liunian(bz, target_dy, int(ly_year))
        with c2:
            st.markdown(f"**{ly_year} 年（{ly['ganzhi']}）流年评分**：{ly['score']}/100 [{ly['verdict']}]　"
                        f"（所在大运 {target_dy['ganzhi']} {target_dy['start_age']}–{target_dy['end_age']}岁）")
            for r in ly["reasons"]:
                st.markdown(f"- {r}")


# ============================================================
# Tab 5: 方位罗盘
# ============================================================
with TABS[4]:
    st.markdown("**年度方位忌宜 + 个人本命卦 + 流年九宫飞星。**")
    c1, c2 = st.columns([1, 2])
    with c1:
        dir_year = st.number_input("年份", value=today_cn().year, min_value=1900, max_value=2100, key="dir_y")
    da = year_directions(int(dir_year))

    st.markdown(f"### {dir_year} 年（{da.year_gz}）方位")
    cols = st.columns(4)
    cols[0].metric("太岁", f"{da.tai_sui_zhi}（{da.tai_sui_dir}）")
    cols[1].metric("岁破", f"{da.sui_po_zhi}（{da.sui_po_dir}）")
    cols[2].metric("三煞", f"{da.san_sha_dir}")
    cols[3].metric("三煞地支", "/".join(da.san_sha_zhi))
    st.warning(f"**忌动山向**：{'、'.join(da.twenty_four_shan_ji)} —— 此方向不宜兴工动土")
    st.success(f"**宜动山向**：{'、'.join(da.twenty_four_shan_yi)} —— 与太岁三合，主吉")

    st.markdown("### 二十四山向罗盘（环形）")
    # 简单 HTML 环形展示
    spans = []
    for s in TWENTY_FOUR_SHAN:
        cls = ""
        if s in da.twenty_four_shan_ji:
            cls = "background:#ffcdd2;"
        elif s in da.twenty_four_shan_yi:
            cls = "background:#c8e6c9;"
        spans.append(
            f"<span style='display:inline-block;width:34px;height:34px;line-height:34px;text-align:center;"
            f"margin:2px;border:1px solid #999;border-radius:50%;{cls}'>{s}</span>"
        )
    st.markdown(
        "<div style='text-align:center'>" + "".join(spans) + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### 本命卦（八宅派）")
    c1, c2, c3 = st.columns(3)
    with c1:
        bg_year = st.number_input("出生年份", value=1990, min_value=1900, max_value=2100, key="bg_y")
    with c2:
        bg_gender = st.selectbox("性别", ["男", "女"], key="bg_g")
    with c3:
        st.write(" ")

    bg = benming_gua(int(bg_year), 1 if bg_gender == "男" else 0)
    st.markdown(f"**本命卦：{bg['gua']}卦（{bg['category']}）**")
    c1, c2 = st.columns(2)
    with c1:
        st.success("**四吉方**")
        for k, v in bg["lucky"].items():
            st.markdown(f"- {k}：**{v}**")
    with c2:
        st.error("**四凶方**")
        for k, v in bg["unlucky"].items():
            st.markdown(f"- {k}：{v}")

    st.markdown("---")
    st.markdown("### 流年九宫飞星")
    grid = nine_star_grid(int(dir_year))
    # 3x3 显示，按洛书方位
    layout = [
        ["东南", "正南", "西南"],
        ["正东", "中",   "正西"],
        ["东北", "正北", "西北"],
    ]
    html = ["<table style='width:60%;margin:auto;border-collapse:collapse;text-align:center'>"]
    for row in layout:
        html.append("<tr>")
        for pos in row:
            n = grid[pos]
            name, luck, desc = STAR_LUCK[n]
            col = {"大吉": "#a5d6a7", "吉": "#dcedc8", "凶": "#ffccbc", "大凶": "#ffab91"}.get(luck, "#fff")
            html.append(
                f"<td style='border:1px solid #aaa;padding:8px;background:{col};vertical-align:top;width:33%'>"
                f"<div style='font-weight:bold'>{pos}</div>"
                f"<div style='font-size:22px;margin:4px 0'>{n}</div>"
                f"<div>{name}</div>"
                f"<div style='font-size:11px;color:#555'>{desc}</div>"
                f"</td>"
            )
        html.append("</tr>")
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)


# ============================================================
# Tab 6: 合婚
# ============================================================
with TABS[5]:
    st.markdown("**双人八字合参：生肖六合冲、日支合冲、五行互补。**")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 男方")
        m_date = st.date_input("出生日期", value=date(1990, 1, 1),
                               min_value=date(1900, 1, 1), max_value=today_cn(),
                               key="hh_m_date")
        m_time = st.time_input("出生时间", value=time(12, 0), key="hh_m_time")
    with c2:
        st.markdown("#### 女方")
        f_date = st.date_input("出生日期", value=date(1992, 1, 1),
                               min_value=date(1900, 1, 1), max_value=today_cn(),
                               key="hh_f_date")
        f_time = st.time_input("出生时间", value=time(12, 0), key="hh_f_time")

    if st.button("💞 合婚分析", type="primary", key="hh_btn"):
        groom = build_bazi(maybe_correct(datetime.combine(m_date, m_time)), gender=1)
        bride = build_bazi(maybe_correct(datetime.combine(f_date, f_time)), gender=0)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**男方**：{groom.year.ganzhi} {groom.month.ganzhi} {groom.day.ganzhi} {groom.hour.ganzhi}")
            st.caption(f"日主 {groom.day_gan}({groom.day_gan_wuxing}) · {groom.shengxiao} · {groom.strength} · 喜用 {'/'.join(groom.yong_shen)}")
        with c2:
            st.markdown(f"**女方**：{bride.year.ganzhi} {bride.month.ganzhi} {bride.day.ganzhi} {bride.hour.ganzhi}")
            st.caption(f"日主 {bride.day_gan}({bride.day_gan_wuxing}) · {bride.shengxiao} · {bride.strength} · 喜用 {'/'.join(bride.yong_shen)}")

        res = hehun_score(bride, groom)
        col_map = {"上等婚": "#1b5e20", "中上婚": "#388e3c", "中等婚": "#f9a825",
                   "下中婚": "#ef6c00", "不宜婚": "#b71c1c"}
        col = col_map.get(res['verdict'], "#555")
        st.markdown(
            f"<h2 style='color:{col};text-align:center'>"
            f"合婚评分：{res['score']}/100　·　{res['verdict']}</h2>",
            unsafe_allow_html=True,
        )
        for r in res["reasons"]:
            st.markdown(r)
        if not res["reasons"]:
            st.info("无明显合冲，属常规配对。")

    st.markdown("---")
    st.markdown("### 嫁娶周堂图")
    st.caption("传统嫁娶择日另需校验：婚日落在周堂八位（夫姑堂翁第灶妇厨）何位？落凶位则当事人短暂回避。")
    zt_date = st.date_input(
        "拟定婚日", value=today_cn(),
        min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
        key="zt_date",
    )
    zt = zhoutang_for_wedding(zt_date)
    avoid = avoid_persons_for_zhoutang(zt["position"])

    # 8 个位置可视化
    cols = st.columns(8)
    for i, pos in enumerate(ZHOUTANG_POSITIONS):
        with cols[i]:
            is_hit = (i == zt["highlight_index"])
            bg = "#ffcdd2" if (is_hit and zt["luck"] == "凶") else ("#c8e6c9" if is_hit else "#f5f5f5")
            star = "★" if is_hit else ""
            st.markdown(
                f"<div style='border:1px solid #999;padding:8px;text-align:center;background:{bg};border-radius:4px'>"
                f"<div style='font-size:18px;font-weight:bold'>{pos} {star}</div>"
                f"<div style='font-size:11px;color:#555'>{'凶' if pos in '夫妇翁姑' else '吉'}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    st.markdown(
        f"**{zt_date}（农历 {zt['lunar_month']}月{zt['lunar_day']}，"
        f"{'大' if zt['is_big_month'] else '小'}月）落 【{zt['position']}】位** — {zt['desc']}"
    )
    if zt["luck"] == "凶" and avoid:
        st.warning(f"⚠ 建议 {' / '.join(avoid)} 在拜堂礼前短暂回避，过此时辰即可。")
    elif zt["luck"] == "吉":
        st.success("✓ 周堂落吉位，无需回避。")


# ============================================================
# Tab 7: 节令
# ============================================================
with TABS[6]:
    c1, c2 = st.columns([1, 3])
    with c1:
        cal_year = st.number_input("年份", value=today_cn().year, min_value=1900, max_value=2100, key="cal_y")

    st.markdown("### 二十四节气")
    jq_df = pd.DataFrame([
        {"节气": j.name, "精确时刻": j.moment.strftime("%Y-%m-%d %H:%M:%S"),
         "距今": f"{j.days_to} 天"}
        for j in get_jieqi_table(int(cal_year))
    ])
    st.dataframe(jq_df, use_container_width=True, hide_index=True)

    st.markdown("### 三伏")
    fu = san_fu(int(cal_year))
    if fu:
        fu_df = pd.DataFrame([
            {"伏": k, "起": s.isoformat(), "止": e.isoformat(), "天数": days}
            for k, (s, e, days) in fu.items()
        ])
        st.dataframe(fu_df, use_container_width=True, hide_index=True)

    st.markdown("### 数九（前一年冬至起）")
    sj_df = pd.DataFrame([
        {"九": n, "起": s.isoformat(), "止": e.isoformat()}
        for n, s, e in shu_jiu(int(cal_year))
    ])
    st.dataframe(sj_df, use_container_width=True, hide_index=True)

    st.markdown("### 月相速查")
    c1, c2 = st.columns([1, 2])
    with c1:
        moon_date = st.date_input("查询日期", value=today_cn(), key="moon_d")
    with c2:
        st.metric("月相", moon_phase(moon_date))
# ============================================================
# Tab 8: 紫微斗数
# ============================================================
with TABS[7]:
    st.markdown("**输入生辰，输出 12 宫 14 主星紫微命盘 + 命宫批注。**")
    c1, c2, c3 = st.columns(3)
    with c1:
        zw_date = st.date_input("出生日期", value=date(1990, 1, 1),
                                min_value=date(1900, 1, 1), max_value=today_cn(),
                                key="zw_date")
    with c2:
        zw_time = st.time_input("出生时间", value=time(12, 0), key="zw_time")
    with c3:
        zw_gender = st.selectbox("性别", ["男", "女"], key="zw_gender")

    zw_dt = maybe_correct(datetime.combine(zw_date, zw_time))
    chart = build_ziwei(zw_dt, gender=1 if zw_gender == "男" else 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("年柱", chart.bazi_year_gz)
    c2.metric("命宫", f"{chart.ming_gong_gan}{chart.ming_gong_zhi}")
    c3.metric("纳音五行", chart.nayin)
    c4.metric("五行局", chart.ju_name)

    # 12 宫盘（3x4 网格，按地支位置排列，命宫高亮）
    st.markdown("### 12 宫位命盘")
    # 紫微斗数排盘惯例：巳午未在上行，辰中酉，卯中戌，寅丑子在下行
    layout = [
        ["巳", "午", "未", "申"],
        ["辰", None, None, "酉"],
        ["卯", None, None, "戌"],
        ["寅", "丑", "子", "亥"],
    ]
    # 反查 地支 → 宫名
    zhi_to_palace = {v: k for k, v in chart.palace_zhi.items()}

    html = ["<table style='width:100%;border-collapse:collapse;text-align:center'>"]
    for row in layout:
        html.append("<tr>")
        for cell in row:
            if cell is None:
                html.append("<td style='border:0;background:#fafafa'></td>")
                continue
            palace = zhi_to_palace.get(cell, "")
            stars = chart.palace_stars.get(palace, []) if palace else []
            is_ming = palace == "命宫"
            bg = "#fff3e0" if is_ming else "#fff"
            border = "2px solid #d84315" if is_ming else "1px solid #ccc"
            star_html = "<br>".join(stars) if stars else "—"
            html.append(
                f"<td style='border:{border};padding:8px;background:{bg};min-width:80px;vertical-align:top;height:100px'>"
                f"<div style='font-size:11px;color:#999'>{cell}宫</div>"
                f"<div style='font-weight:bold;color:#5d4037;margin:4px 0'>{palace}</div>"
                f"<div style='font-size:13px;color:#1b5e20'>{star_html}</div>"
                f"</td>"
            )
        html.append("</tr>")
    html.append("</table>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("### 命宫批注")
    st.info(interpret_ming_gong(chart))

    st.markdown("### 12 宫详表")
    df = pd.DataFrame([
        {"宫位": p, "地支": chart.palace_zhi[p],
         "主星": " ".join(chart.palace_stars[p]) if chart.palace_stars[p] else "—"}
        for p in PALACES_REVERSE
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


# ============================================================
# Tab 9: 并排比较
# ============================================================
with TABS[8]:
    st.markdown("**输入 2-5 个候选日，并排打分；高亮最佳。**适合婚嫁、动土在几个备选日之间决断。")

    cmp_c1, cmp_c2 = st.columns(2)
    with cmp_c1:
        cmp_event = st.selectbox(
            "事项类型（用于打分）",
            ["（通用吉凶）"] + list(EVENT_KEYWORDS.keys()),
            key="cmp_event",
        )
    with cmp_c2:
        cmp_person_count = st.number_input(
            "当事人数", min_value=0, max_value=4, value=0, step=1, key="cmp_pc"
        )

    cmp_event_arg = None if cmp_event.startswith("（") else cmp_event

    st.markdown("##### 候选日期")
    cmp_date_cols = st.columns(5)
    cmp_default_dates = [
        _today,
        _today + timedelta(days=1),
        _today + timedelta(days=7),
        _today + timedelta(days=14),
        _today + timedelta(days=30),
    ]
    cmp_dates: list[date] = []
    cmp_enable: list[bool] = []
    for i in range(5):
        with cmp_date_cols[i]:
            enable = st.checkbox(f"候选 {i + 1}", value=(i < 3), key=f"cmp_en_{i}")
            d_pick = st.date_input(
                "日期", value=cmp_default_dates[i],
                min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
                key=f"cmp_d_{i}", label_visibility="collapsed",
            )
            cmp_dates.append(d_pick)
            cmp_enable.append(enable)

    cmp_persons = persons_input("cmp", cmp_person_count) if cmp_person_count > 0 else []

    if st.button("⚖️ 比较打分", type="primary", key="cmp_btn"):
        active = [(i, d) for i, (d, e) in enumerate(zip(cmp_dates, cmp_enable)) if e]
        if len(active) < 2:
            st.warning("请至少勾选 2 个候选日。")
        else:
            cmp_results = []
            for idx, d_pick in active:
                a_pick = get_day_almanac(d_pick)
                sb_pick = score_day(
                    a_pick, event=cmp_event_arg,
                    persons=cmp_persons, school=school,
                )
                v_pick = verdict(sb_pick.score, sb_pick.fatal)
                keywords = EVENT_KEYWORDS.get(cmp_event_arg, [cmp_event_arg]) if cmp_event_arg else []
                hit_yi = [k for k in keywords if k in a_pick.yi] if cmp_event_arg else []
                hit_ji = [k for k in keywords if k in a_pick.ji] if cmp_event_arg else []
                cmp_results.append({
                    "候选": f"#{idx + 1}",
                    "公历": d_pick.isoformat(),
                    "星期": ["一", "二", "三", "四", "五", "六", "日"][d_pick.weekday()],
                    "农历": a_pick.lunar_str.split("年")[-1],
                    "干支": a_pick.ganzhi_day,
                    "评分": sb_pick.score,
                    "等级": v_pick,
                    "fatal": sb_pick.fatal,
                    "宜本事": "✓" + "/".join(hit_yi) if hit_yi else "",
                    "忌本事": "✗" + "/".join(hit_ji) if hit_ji else "",
                    "冲煞": a_pick.chong_desc,
                    "凶日": "、".join(k for k in sb_pick.taboos.keys() if k != "不将日(嫁娶吉)")[:30],
                    "宜": "、".join(a_pick.yi[:5]),
                    "_almanac": a_pick,
                    "_sb": sb_pick,
                    "_date": d_pick,
                })

            # 找最佳（fatal 不计；按 score 降序）
            non_fatal = [r for r in cmp_results if not r["fatal"]]
            best_idx = None
            if non_fatal:
                best_score = max(r["评分"] for r in non_fatal)
                for i, r in enumerate(cmp_results):
                    if r in non_fatal and r["评分"] == best_score:
                        best_idx = i
                        break

            # 显示表
            display_rows = []
            for i, r in enumerate(cmp_results):
                marker = "🏆" if i == best_idx else ("⛔" if r["fatal"] else "　")
                display_rows.append({
                    "": marker,
                    "候选": r["候选"],
                    "公历": r["公历"],
                    "周": r["星期"],
                    "农历": r["农历"],
                    "干支": r["干支"],
                    "评分": r["评分"],
                    "等级": r["等级"],
                    "宜本事": r["宜本事"],
                    "忌本事": r["忌本事"],
                    "冲煞": r["冲煞"],
                    "凶日": r["凶日"],
                    "宜": r["宜"],
                })
            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)

            if best_idx is not None:
                best = cmp_results[best_idx]
                st.success(
                    f"🏆 推荐：**{best['公历']}**（{best['干支']}日，{best['等级']}，{best['评分']}/100）"
                )

            # 雷达图：可视化各候选维度
            st.markdown("##### 五维评分雷达图")
            import math
            radar_html = ['<svg viewBox="0 0 600 400" style="width:100%;max-width:800px">']
            # 5 个维度：黄黑道、建除、星宿、宜本事、神煞
            dims = ["黄黑道", "建除", "二十八宿", "宜忌匹配", "神煞净"]
            cx, cy, r = 300, 200, 130
            angles = [-math.pi / 2 + i * 2 * math.pi / 5 for i in range(5)]

            # 外圈刻度
            for level in [0.25, 0.5, 0.75, 1.0]:
                pts = [
                    (cx + r * level * math.cos(a), cy + r * level * math.sin(a))
                    for a in angles
                ]
                pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                radar_html.append(
                    f'<polygon points="{pts_str}" fill="none" stroke="#ddd" stroke-width="0.5"/>'
                )
            # 维度轴
            for a in angles:
                radar_html.append(
                    f'<line x1="{cx}" y1="{cy}" x2="{cx + r * math.cos(a):.1f}" '
                    f'y2="{cy + r * math.sin(a):.1f}" stroke="#ccc" stroke-width="0.5"/>'
                )
            # 标签
            for i, name in enumerate(dims):
                a = angles[i]
                lx = cx + (r + 22) * math.cos(a)
                ly = cy + (r + 22) * math.sin(a)
                radar_html.append(
                    f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
                    f'dominant-baseline="middle" font-size="12" fill="#555">{name}</text>'
                )

            colors = ["#1976d2", "#388e3c", "#f57c00", "#c2185b", "#7b1fa2"]
            for i, rs in enumerate(cmp_results):
                a_pick = rs["_almanac"]
                sb_pick = rs["_sb"]
                vals = [
                    1.0 if a_pick.tianshen in {"青龙", "明堂", "金匮", "天德", "玉堂", "司命"} else 0.2,
                    {"建": 0.5, "除": 0.85, "满": 0.5, "平": 0.5, "定": 0.9,
                     "执": 0.85, "破": 0.1, "危": 0.85, "成": 0.95, "收": 0.5,
                     "开": 0.85, "闭": 0.3}.get(a_pick.jianchu, 0.5),
                    0.9 if a_pick.xiu_luck == "吉" else 0.2,
                    (1.0 if rs["宜本事"] else (0.0 if rs["忌本事"] else 0.5)) if cmp_event_arg else 0.5,
                    max(0, min(1, 0.5 + 0.1 * (len(a_pick.jishen) - len(a_pick.xiongsha)))),
                ]
                pts = [
                    (cx + r * v * math.cos(a), cy + r * v * math.sin(a))
                    for v, a in zip(vals, angles)
                ]
                pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                c = colors[i % len(colors)]
                radar_html.append(
                    f'<polygon points="{pts_str}" fill="{c}" fill-opacity="0.15" '
                    f'stroke="{c}" stroke-width="1.5"/>'
                )
                # 图例
                radar_html.append(
                    f'<rect x="{460}" y="{60 + i * 22}" width="14" height="14" fill="{c}" fill-opacity="0.4" stroke="{c}"/>'
                )
                radar_html.append(
                    f'<text x="{482}" y="{72 + i * 22}" font-size="12" fill="#333">'
                    f'{rs["候选"]} {rs["公历"]} ({rs["评分"]})</text>'
                )
            radar_html.append('</svg>')
            st.markdown("".join(radar_html), unsafe_allow_html=True)

            # 详情：top 2 完整卡片
            st.markdown("##### 前两名详情")
            sorted_results = sorted(non_fatal, key=lambda x: -x["评分"])[:2]
            for r in sorted_results:
                with st.expander(
                    f"{r['公历']} · {r['干支']}日 · {r['等级']} · {r['评分']}/100",
                    expanded=False,
                ):
                    render_almanac_card(r["_almanac"], r["评分"], r["等级"])


# ============================================================
# Tab 10: 设置说明
# ============================================================
with TABS[9]:
    st.markdown("### 各流派权重对照")
    rows = []
    for sch, w in SCHOOL_WEIGHTS.items():
        rows.append({"流派": sch, **w})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.markdown("""
**流派说明**：
- **综合**：默认配置，平衡神煞与宜忌
- **协纪辨方**：清代官修《协纪辨方书》体系，重神煞，凶煞扣分更高
- **董公选日**：民间通行《董公选要览》体系，重通书宜忌
- **宽松模式**：仅作参考，不一票否决；适合非传统人士

---

### 凶日/特殊日规则覆盖

| 名称 | 命中条件 |
|---|---|
| 三娘煞 | 农历初三、初七、十三、十八、廿二、廿七 |
| 十恶大败 | 甲辰、乙巳、丙申、丁亥、戊戌、己丑、庚辰、辛巳、壬申、癸亥 |
| 杨公十三忌 | 农历正月十三、二月十一…十二月十九（共 13 日） |
| 月忌日 | 农历初五、十四、廿三 |
| 月厌 | 按月支对应的厌日地支 |
| 红沙日 | 孟月酉 / 仲月巳 / 季月丑 |
| 重丧日 | 月支对应的日干 |
| 归忌 | 按季节对应的日支 |
| 四离 | 春分/秋分/夏至/冬至 前一日 |
| 四绝 | 立春/立夏/立秋/立冬 前一日 |
| 土王用事 | 立春/夏/秋/冬 前 18 天 |
| 往亡 | 每节气后第 N 天 |
| 不将日 | 嫁娶吉日（按月查表） |

---

### 数据来源与算法依据
- **节气、农历、干支、神煞、宜忌**：lunar-python（对齐紫金山天文台历法）
- **八字十神、纳音、藏干、大运**：同上
- **凶日规则表、本命卦、九宫飞星**：本工具实现（依据《协纪辨方书》《董公选要览》等）
- **真太阳时**：经度修正 + 时差方程近似公式

### 重要说明
1. 本工具综合多家算法，结果**仅供文化参考**。
2. 重大事项建议结合专业课择与当事人完整八字综合判断。
3. 历史/古代日期可能与各地实际通书略有出入，以官方通书为准。
""")
