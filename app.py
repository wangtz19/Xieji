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
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

from core.almanac import get_day_almanac, get_birth_chart, EVENT_KEYWORDS
from core.hours import (
    get_hour_slots, best_hours_for_event,
    correct_birth_to_true_solar, CITY_LONGITUDE,
)
from core.bazi import build_bazi, hehun_score
from core.directions import (
    year_directions, benming_gua, nine_star_grid, STAR_LUCK,
    TWENTY_FOUR_SHAN, ZHI_DIRECTION,
)
from core.calendars import (
    get_jieqi_table, next_jieqi, current_jieqi_phase,
    san_fu, shu_jiu, moon_phase, holiday_of,
)

from divination.rules import HIT_LABEL
from divination.scoring import score_day, verdict, recommend_days, SCHOOL_WEIGHTS
from divination.wedding import zhoutang_for_wedding, avoid_persons_for_zhoutang, ZHOUTANG_POSITIONS
from divination.dayun import evaluate_dayun, evaluate_liunian
from divination.ziwei import build_ziwei, interpret_ming_gong, PALACES_REVERSE

from output.export import export_ical, export_json, natural_language_summary
from output.pdf_export import render_huangli_pdf
from output.llm import (
    interpret_via_llm, is_llm_available, LLMConfig,
    PROVIDER_ANTHROPIC, PROVIDER_OPENAI,
    BASE_URL_PRESETS, MODEL_PRESETS,
)


LOGO_PATH = str(Path(__file__).parent / "assets" / "logo.png")

st.set_page_config(
    page_title="协纪 · 黄历择吉工具",
    page_icon=LOGO_PATH,
    layout="wide",
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


# 9 个 Tab
TABS = st.tabs([
    "📅 单日吉凶", "💍 择吉推荐", "🗓 月历视图",
    "🎴 八字排盘", "🧭 方位罗盘", "❤️ 合婚",
    "🌿 节令", "⭐ 紫微斗数", "⚙️ 设置说明",
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
                    min_value=date(1900, 1, 1), max_value=date.today(),
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
            "查询日期", value=date.today(),
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

    # PDF 下载
    st.markdown("---")
    if st.button("📄 生成传统老黄历 PDF", key="single_pdf_btn"):
        with st.spinner("生成 PDF 中…"):
            pdf_bytes = render_huangli_pdf(query_date)
        st.download_button(
            "📥 下载 PDF",
            data=pdf_bytes,
            file_name=f"huangli_{query_date.isoformat()}.pdf",
            mime="application/pdf",
            key="single_pdf_dl",
        )


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
            "搜索起点", value=date.today(),
            min_value=date(1900, 1, 1), max_value=date(2100, 12, 31),
            key="rec_start",
        )
    with c2:
        search_days = st.slider("搜索天数", min_value=30, max_value=365, value=365, step=30, key="rec_days")

    weekday_filter = st.multiselect(
        "排除星期（不希望事项落在某些星期可勾选）",
        ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        default=[],
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
                file_name=f"jiri_{date.today().isoformat()}.ics",
                mime="text/calendar",
                use_container_width=True,
            )
        with c2:
            st.download_button(
                "📥 JSON",
                data=export_json(results),
                file_name=f"jiri_{date.today().isoformat()}.json",
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
        m_year = st.number_input("年", value=date.today().year, min_value=1900, max_value=2100, key="mv_y")
    with c2:
        m_month = st.number_input("月", value=date.today().month, min_value=1, max_value=12, key="mv_m")
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
                                min_value=date(1900, 1, 1), max_value=date.today(),
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
            "流年", value=date.today().year, min_value=1900, max_value=2100, key="ly_y",
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
        dir_year = st.number_input("年份", value=date.today().year, min_value=1900, max_value=2100, key="dir_y")
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
                               min_value=date(1900, 1, 1), max_value=date.today(),
                               key="hh_m_date")
        m_time = st.time_input("出生时间", value=time(12, 0), key="hh_m_time")
    with c2:
        st.markdown("#### 女方")
        f_date = st.date_input("出生日期", value=date(1992, 1, 1),
                               min_value=date(1900, 1, 1), max_value=date.today(),
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
        "拟定婚日", value=date.today(),
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
        cal_year = st.number_input("年份", value=date.today().year, min_value=1900, max_value=2100, key="cal_y")

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
        moon_date = st.date_input("查询日期", value=date.today(), key="moon_d")
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
                                min_value=date(1900, 1, 1), max_value=date.today(),
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
# Tab 9: 设置说明
# ============================================================
with TABS[8]:
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
