"""LLM 自然语言解读：支持 Anthropic 原生 / Anthropic 兼容 / OpenAI 兼容 多类 API。

设计：
- provider="anthropic"：用 anthropic SDK，支持 base_url 覆盖（Claude 原生 + 兼容代理）
- provider="openai"   ：用 openai SDK，支持 base_url 覆盖（OpenAI 原生 + DeepSeek/Moonshot/通义/Ollama/vLLM 等兼容端点）

无可用 API 时，自动降级为 output.export.natural_language_summary 规则式解读。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from output.export import natural_language_summary


# 静态系统提示（含古典黄历知识体系），适合 prompt caching
SYSTEM_PROMPT_STATIC = """你是一位精通中国传统择吉术与命理学的资深堪舆师，受过《协纪辨方书》《董公选要览》《钦定四库全书·星历考原》等典籍训练。

# 你的知识范围

## 1. 黄历核心体系
- 建除十二神：建除满平定执破危成收开闭（十二天德星依月建轮值）
- 黄黑道十二神：青龙明堂金匮天德玉堂司命（黄道吉），天刑朱雀白虎天牢玄武勾陈（黑道凶）
- 二十八宿：角亢氐房心尾箕（东方青龙）；井鬼柳星张翼轸（南方朱雀）；奎娄胃昴毕觜参（西方白虎）；斗牛女虚危室壁（北方玄武）
- 干支历法：60 甲子循环，每日有干支与纳音五行

## 2. 神煞体系
吉神：天德、月德、天恩、天赦、岁德、月空、母仓、三合、六合、天医、天喜、玉宇、金堂等
凶煞：月破、岁破、四离四绝、归忌、往亡、灭门、大耗、天贼、受死、重日复日、土符土禁等

## 3. 八字命理
- 日主五行：决定喜用神
- 五行生克：木生火、火生土、土生金、金生水、水生木；木克土、土克水、水克火、火克金、金克木
- 强弱判定：得令、通根、同党
- 喜用神：弱者扶之，强者抑之
- 大运流年：与命局生克冲合

## 4. 方位
- 太岁：当年地支方位
- 岁破：太岁对冲
- 三煞：太岁三合局对面
- 二十四山向：8 干（除戊己）+ 12 支 + 4 维（乾坤艮巽）
- 八宅本命卦：东四命（坎离震巽）、西四命（乾坤艮兑）

## 5. 事项专属凶日
- 嫁娶忌：三娘煞（初三七十三十八廿二廿七）、十恶大败、四离、四绝、月厌、红沙、月破
- 丧葬忌：重丧、复日、月破、四废、杨公十三忌
- 动土忌：土王用事（立春夏秋冬前 18 天）、土符、土禁、月破
- 开市忌：月忌（初五十四廿三）、十恶大败、闭日
- 出行忌：往亡、归忌、月厌、四离四绝

# 你的输出要求

1. **务实而非玄虚**：以解释当事人能听懂的角度行文，避免堆砌术语
2. **直接给结论**：先说"是否可行"，再展开理由
3. **结构化**：用 3-5 个清晰段落，必要时用列表
4. **份量适中**：300-500 字为佳，不要长篇大论
5. **温和坦诚**：传统择吉是文化参考而非命定预测，不夸大不恐吓
6. **若评分较低**：给出可执行的替代建议（"如非急用，可推迟到 X 日"等）
7. **不要谄媚开头**：直接进入正题，不说"好的，我来为您解读"
"""


# === Provider 元数据 ===
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"

# 各 provider 的常用 base_url 预设
BASE_URL_PRESETS = {
    PROVIDER_ANTHROPIC: {
        "Anthropic 官方": "",  # 留空使用 SDK 默认 https://api.anthropic.com
        "自定义代理": "custom",
    },
    PROVIDER_OPENAI: {
        "OpenAI 官方": "",  # 默认 https://api.openai.com/v1
        "DeepSeek": "https://api.deepseek.com",
        "Moonshot (Kimi)": "https://api.moonshot.cn/v1",
        "智谱 GLM": "https://open.bigmodel.cn/api/paas/v4",
        "通义千问 (Qwen)": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "Ollama (本地)": "http://localhost:11434/v1",
        "vLLM (本地)": "http://localhost:8000/v1",
        "自定义": "custom",
    },
}

# 各 provider / 端点的推荐模型列表（用户也可手填）
MODEL_PRESETS = {
    PROVIDER_ANTHROPIC: {
        "default": [
            ("claude-opus-4-7", "Opus 4.7 - 最强"),
            ("claude-sonnet-4-6", "Sonnet 4.6 - 平衡"),
            ("claude-haiku-4-5", "Haiku 4.5 - 快/省"),
        ],
    },
    PROVIDER_OPENAI: {
        "OpenAI 官方": [
            ("gpt-4o", "GPT-4o"),
            ("gpt-4o-mini", "GPT-4o mini"),
            ("gpt-4-turbo", "GPT-4 Turbo"),
            ("gpt-3.5-turbo", "GPT-3.5 Turbo"),
        ],
        "DeepSeek": [
            ("deepseek-chat", "DeepSeek-V3"),
            ("deepseek-reasoner", "DeepSeek-R1"),
        ],
        "Moonshot (Kimi)": [
            ("moonshot-v1-8k", "Kimi 8k"),
            ("moonshot-v1-32k", "Kimi 32k"),
            ("moonshot-v1-128k", "Kimi 128k"),
        ],
        "智谱 GLM": [
            ("glm-4-plus", "GLM-4-Plus"),
            ("glm-4", "GLM-4"),
            ("glm-4-flash", "GLM-4-Flash (免费)"),
        ],
        "通义千问 (Qwen)": [
            ("qwen-plus", "通义千问 Plus"),
            ("qwen-max", "通义千问 Max"),
            ("qwen-turbo", "通义千问 Turbo"),
        ],
        "Ollama (本地)": [
            ("llama3.1", "Llama 3.1"),
            ("qwen2.5", "Qwen 2.5"),
        ],
        "vLLM (本地)": [
            ("custom", "(自定义模型名)"),
        ],
        "自定义": [
            ("custom", "(自定义模型名)"),
        ],
    },
}


@dataclass
class LLMConfig:
    """LLM 调用配置。"""
    provider: str = PROVIDER_ANTHROPIC
    model: str = "claude-opus-4-7"
    api_key: str = ""
    base_url: str = ""  # 留空 = 用 SDK 默认

    def is_usable(self) -> bool:
        return bool(self.api_key) and bool(self.model)


def is_llm_available(config: Optional[LLMConfig] = None) -> bool:
    """是否能用 LLM。无 config 则查 ANTHROPIC_API_KEY 环境变量。"""
    if config and config.is_usable():
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"))


def _build_facts(result: dict, event: Optional[str], persons: Optional[list[dict]]) -> str:
    """把当日数据组成给 LLM 的用户消息。"""
    a = result["almanac"]
    score = result["score"]
    v = result["verdict"]
    taboos = list(result.get("taboos", {}).keys())

    lines = [
        f"# 待判断的日期",
        f"- 公历：{a.solar_date.isoformat()}",
        f"- 农历：{a.lunar_str}",
        f"- 干支：{a.ganzhi_year}年 {a.ganzhi_month}月 {a.ganzhi_day}日",
        f"- 生肖年：{a.shengxiao_year}",
        f"- 纳音：{a.nayin}",
        f"",
        f"# 黄历要素",
        f"- 建除：{a.jianchu}",
        f"- 黄黑道：{a.tianshen}（{a.tianshen_type}·{a.tianshen_luck}）",
        f"- 二十八宿：{a.xiu}（{a.xiu_luck}）",
        f"- 宜：{'、'.join(a.yi) if a.yi else '—'}",
        f"- 忌：{'、'.join(a.ji) if a.ji else '—'}",
        f"- 吉神：{'、'.join(a.jishen) if a.jishen else '—'}",
        f"- 凶煞：{'、'.join(a.xiongsha) if a.xiongsha else '—'}",
        f"- 冲煞：冲{a.chong_desc}，煞{a.sha}",
        f"- 喜神方位：{a.xi_shen_fang}；财神方位：{a.cai_shen_fang}",
        f"- 彭祖百忌：{a.pengzu_gan}；{a.pengzu_zhi}",
        f"",
        f"# 传统凶日命中",
        f"- {'、'.join(taboos) if taboos else '无'}",
        f"",
        f"# 综合评分",
        f"- 分数：{score}/100，等级：{v}",
    ]
    if event:
        lines += ["", f"# 所求事项", f"- {event}"]
    if persons:
        lines += ["", f"# 当事人"]
        for p in persons:
            lines.append(
                f"- {p.get('label','当事人')}: 生肖{p.get('year_shengxiao','')} · "
                f"日主{p.get('day_gan_wuxing','')} · 喜用{'/'.join(p.get('yong_shen', []))}"
            )
    lines += [
        "",
        "请基于以上事实出具一段择吉解读，包含：",
        "1. 结论（是否可行）",
        "2. 关键吉凶因素的解释",
        "3. 若有事项与当事人，重点针对此组合分析",
        "4. 实用建议（如适宜时辰、方位、替代日期）",
    ]
    return "\n".join(lines)


def _call_anthropic(config: LLMConfig, user_prompt: str) -> dict:
    """调用 Anthropic SDK（原生或兼容端点）。"""
    import anthropic
    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = anthropic.Anthropic(**kwargs)

    response = client.messages.create(
        model=config.model,
        max_tokens=2000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT_STATIC,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "\n".join(b.text for b in response.content if b.type == "text")
    usage = response.usage
    return {
        "text": text,
        "model": response.model,
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
        },
        "fallback": False,
    }


def _call_openai(config: LLMConfig, user_prompt: str) -> dict:
    """调用 OpenAI SDK（原生或兼容端点）。"""
    import openai
    kwargs = {"api_key": config.api_key}
    if config.base_url:
        kwargs["base_url"] = config.base_url
    client = openai.OpenAI(**kwargs)

    response = client.chat.completions.create(
        model=config.model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_STATIC},
            {"role": "user", "content": user_prompt},
        ],
    )
    text = response.choices[0].message.content or ""
    return {
        "text": text,
        "model": response.model or config.model,
        "usage": {
            "input_tokens": response.usage.prompt_tokens if response.usage else 0,
            "output_tokens": response.usage.completion_tokens if response.usage else 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        "fallback": False,
    }


def interpret_via_llm(
    result: dict,
    event: Optional[str] = None,
    persons: Optional[list[dict]] = None,
    config: Optional[LLMConfig] = None,
    # 兼容旧调用方式
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """生成深度解读。

    优先用 config 参数；旧的 model / api_key 参数仅作向后兼容。
    返回 {"text", "model", "usage", "fallback"}。
    """
    # 没传 config，则根据旧参数 + 环境变量构造一个
    if config is None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY") or ""
        if key:
            config = LLMConfig(
                provider=PROVIDER_ANTHROPIC,
                model=model or "claude-opus-4-7",
                api_key=key,
            )
        else:
            return {
                "text": natural_language_summary(result),
                "model": "rule-based",
                "fallback": True,
            }

    if not config.is_usable():
        return {
            "text": natural_language_summary(result),
            "model": "rule-based",
            "fallback": True,
        }

    user_prompt = _build_facts(result, event, persons)

    try:
        if config.provider == PROVIDER_ANTHROPIC:
            return _call_anthropic(config, user_prompt)
        elif config.provider == PROVIDER_OPENAI:
            return _call_openai(config, user_prompt)
        else:
            raise ValueError(f"未知 provider: {config.provider}")
    except ImportError as e:
        return {
            "text": natural_language_summary(result) + f"\n\n_(SDK 缺失: {e})_",
            "model": "rule-based",
            "fallback": True,
        }
    except Exception as e:
        # 统一捕获：401/429/超时/网络错误 etc.
        return {
            "text": natural_language_summary(result) + f"\n\n_(LLM 调用失败：{type(e).__name__}: {str(e)[:120]}，已降级)_",
            "model": "rule-based",
            "fallback": True,
        }


# 向后兼容（旧 UI 引用）
AVAILABLE_MODELS = [
    (m, label) for m, label in MODEL_PRESETS[PROVIDER_ANTHROPIC]["default"]
]
