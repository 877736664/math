"""互动动画生成服务，输出可直接嵌入页面的 HTML。"""

from __future__ import annotations

import html
import json
import random
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from app.services.animation_planning_service import build_animation_plan
from app.services.image_generation_service import generate_animation_images
from app.services.rag_service import retrieve_knowledge, solve_question_with_docs
from app.repositories.textbook_repository import KnowledgeDocument


SEARCH_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MAX_DISPLAY_TOKENS = 18


@dataclass(frozen=True)
class ThemeOption:
    """动画主题配置，包括关键词、展示名称和配色。"""

    keywords: tuple[str, ...]
    label: str
    english: str
    palette: tuple[str, str]


@dataclass(frozen=True)
class AnimationVariant:
    """控制同一道题不同版本动画外观和叙事风格。"""

    key: str
    label: str
    teacher_intro: str
    focus_prefix: str
    wrap_prefix: str


TOKEN_THEME_OPTIONS: tuple[ThemeOption, ...] = (
    ThemeOption(("糖", "糖果"), "糖果", "candy", ("#f7b7d7", "#ff8e6e")),
    ThemeOption(("苹果",), "苹果", "apple", ("#f9c86c", "#eb6d52")),
    ThemeOption(("花", "盆花"), "花朵", "flower", ("#ffc2da", "#f28db2")),
    ThemeOption(("球",), "小球", "ball", ("#b8f0d2", "#57b48d")),
    ThemeOption(("积木", "方块"), "积木", "blocks", ("#b7d6ff", "#8fd0b2")),
)
MOTION_THEME_OPTIONS: tuple[ThemeOption, ...] = (
    ThemeOption(("自行车", "骑车"), "骑行路线", "bicycle route", ("#8fc3ff", "#ffc58f")),
    ThemeOption(("小车", "汽车"), "行程地图", "car route", ("#9bd3c6", "#ffd39a")),
    ThemeOption(("火箭",), "太空航线", "rocket trail", ("#c2b4ff", "#92d8ff")),
)
GENERIC_THEME_OPTIONS: tuple[ThemeOption, ...] = (
    ThemeOption(("数字",), "数字积木", "math blocks", ("#b7d6ff", "#8fd0b2")),
    ThemeOption(("卡片",), "思维卡片", "thinking cards", ("#f6c38f", "#a7d6c9")),
    ThemeOption(("星星",), "星光提示", "star math", ("#f7d58b", "#9cc6ff")),
)
DEFAULT_THEME = GENERIC_THEME_OPTIONS[0]
ANIMATION_VARIANTS: tuple[AnimationVariant, ...] = (
    AnimationVariant("story", "故事讲解版", "我们先像讲故事一样把条件摆清楚。", "先抓住", "最后把"),
    AnimationVariant("challenge", "闯关挑战版", "这一版我们把题目拆成几个闯关观察点。", "本关先看", "通关后再检查"),
    AnimationVariant("coach", "老师带练版", "这一版更像老师边演示边带着学生说思路。", "老师先提醒", "收束时再回到"),
)


def generate_animation_game(
    grade: int,
    question: str,
    textbook: dict | None = None,
    variation_seed: str | None = None,
) -> dict:
    """优先让 LLM 直接生成双栏互动 HTML，失败时回退到内置双栏模板。"""

    from app.services.llm_service import complete_with_llm, user_message, system_message

    # 先做规划和检索，获取知识点
    preliminary_plan = build_animation_plan(question, grade)
    documents = retrieve_knowledge(preliminary_plan["retrieval_query"], grade, textbook=textbook)
    animation_plan = build_animation_plan(question, grade, documents)
    solution = solve_question_with_docs(question, documents)
    seed = (variation_seed or uuid4().hex).strip()[:64] or uuid4().hex
    rng = random.Random(seed)

    # 获取知识文本
    knowledge_text = ""
    if documents:
        knowledge_text = "\n\n".join([f"- {doc.title}: {doc.summary}" for doc in documents[:3]])

    # 让LLM直接生成完整HTML，左侧题目讲解 + 右侧实时动画预览的双栏布局
    system_prompt = """你是一位小学数学互动动画专家。用户会给一道小学数学题，请你直接输出一整个完整可用的 HTML 文件源码，包含全部 CSS 和 JavaScript。

要求：
1. HTML 必须自带左右双栏布局：左边是题目讲解区域，右边是互动动画预览区域。就像这样：
   - 左侧：题目文字 + 分步讲解 + 教师提示
   - 右侧：互动动画可以直接操作播放，宽度占满整栏
2. 整个 HTML 必须是**单个文件**，不引用外部 CSS/JS，全部代码内联。
3. 配色要温暖柔和，适合小学生课堂使用，风格简洁干净。
4. JavaScript 要实现完整的交互逻辑，比如分步播放、点击控制。
5. 严格只输出 HTML 代码，不要输出任何其他解释、markdown 标记、``` 包裹。直接输出完整代码。
6. 根据题目特点，自己设计最合适的互动方式，不要被固定模板限制。题目是啥就做成啥样的动画。
7. 页面要响应式，宽度自适应。"""

    user_prompt = f"""题目：{question}
年级：{grade} 年级

知识点参考（来自教材检索）：
{knowledge_text}

题目分析：
- 教学场景：{animation_plan.get('scene_summary', '小学数学互动练习')}
- 教学重点：{animation_plan.get('teaching_focus', '帮助学生理解题意')}
- 视觉元素：{', '.join([e.get('name', '') for e in animation_plan.get('visual_entities', [])[:4]])}

请直接生成完整的 HTML 文件，左边讲解、右边动画，全部代码在一个文件里。"""

    messages = [
        system_message(system_prompt),
        user_message(user_prompt),
    ]

    theme = _pick_theme(question, animation_plan.get("scene_type", "generic"), rng)
    images = _search_images(
        _build_search_queries(question, "generic", theme),
        theme,
        animation_plan,
        variation_seed=seed,
        variant_label="AI直生成",
    )

    title = f"互动动画演示·{question[:20]}"
    if len(question) > 20:
        title += "..."

    summary = f"AI 直接生成的完整互动动画HTML，左侧讲解+右侧预览双栏布局。基于知识点：{animation_plan.get('teaching_focus', '小学数学练习')}"

    try:
        html_content = complete_with_llm(messages, temperature=0.85)
        html_content = html_content.strip()
        if html_content.startswith("```html"):
            html_content = html_content[7:]
        if html_content.startswith("```"):
            html_content = html_content[3:]
        if html_content.endswith("```"):
            html_content = html_content[:-3]
        html_content = html_content.strip()
        if not _is_dual_column_html(html_content):
            raise ValueError("LLM did not return a valid dual-column HTML layout")
    except Exception:
        demo_spec, _ = _build_demo_spec(grade, question, documents, solution, rng, seed, animation_plan)
        demo_spec["image_assets"] = images
        html_content = _render_demo_html(demo_spec, images, theme)
        summary = f"已回退到内置双栏互动动画模板。基于知识点：{animation_plan.get('teaching_focus', '小学数学练习')}"

    demo_spec = {
        "version": "3.0",
        "demo_type": "full_direct",
        "title": title,
        "summary": summary,
        "grade": grade,
        "question": question,
        "variation_seed": seed,
        "variation_label": "AI直生成",
        "knowledge_focus": animation_plan.get("knowledge_focus", []),
        "animation_plan": animation_plan,
        "image_assets": images,
    }

    return {
        "title": title,
        "summary": summary,
        "html": html_content,
        "demo_spec": demo_spec,
    }


def _is_dual_column_html(html_content: str) -> bool:
    text = (html_content or "").lower()
    return all(token in text for token in ("<html", "<style", "<script", "display:grid")) and (
        ("题目讲解" in html_content and "互动动画预览" in html_content)
        or ("left" in text and "right" in text and "iframe" not in text)
        or ("sidebar" in text and "stage" in text)
    )



def _detect_operation(question: str) -> str:
    if any(word in question for word in ("平均分", "平分", "均分", "每人", "每份")):
        return "division"
    return "generic"


def _pick_theme(question: str, demo_type: str, rng: random.Random) -> ThemeOption:
    if demo_type == "average_share":
        pool = [option for option in TOKEN_THEME_OPTIONS if any(keyword in question for keyword in option.keywords)]
        pool = pool or list(TOKEN_THEME_OPTIONS)
    elif demo_type in {"meeting_journey", "journey_meeting"}:
        pool = [option for option in MOTION_THEME_OPTIONS if any(keyword in question for keyword in option.keywords)]
        pool = pool or list(MOTION_THEME_OPTIONS)
    else:
        pool = [option for option in GENERIC_THEME_OPTIONS if any(keyword in question for keyword in option.keywords)]
        pool = pool or list(GENERIC_THEME_OPTIONS)

    return pool[rng.randrange(len(pool))] if pool else DEFAULT_THEME


def _extract_numbers(question: str) -> list[int]:
    return [int(token) for token in re.findall(r"\d+", question)]


def _build_demo_spec(
    grade: int,
    question: str,
    documents: list[KnowledgeDocument],
    solution: dict | None,
    rng: random.Random,
    variation_seed: str,
    animation_plan: dict,
) -> tuple[dict, ThemeOption]:
    scene_type = animation_plan.get("scene_type", "generic_reasoning")
    theme = _pick_theme(question, scene_type, rng)
    variant = rng.choice(ANIMATION_VARIANTS)
    demo_type = "meeting_journey" if scene_type == "journey_meeting" else "average_share" if scene_type == "average_share" else "generic_math"

    return (
        {
            "version": "2.1",
            "demo_type": demo_type,
            "title": f"{animation_plan.get('teaching_focus', '数学互动动画')}·{variant.label}",
            "summary": f"按“左侧讲解 + 右侧互动预览”的方式展示。围绕 {animation_plan.get('teaching_goal', '理解题意')} 组织。",
            "grade": grade,
            "question": question,
            "equation": solution.get("conclusion", "跟着步骤理解题意") if isinstance(solution, dict) else "跟着步骤理解题意",
            "variation_seed": variation_seed,
            "variation_label": variant.label,
            "knowledge_focus": animation_plan.get("knowledge_focus", [document.title for document in documents[:3]]),
            "animation_plan": animation_plan,
            "teacher_panel": {
                "intro": variant.teacher_intro + animation_plan.get("scene_summary", ""),
                "focus": animation_plan.get("teaching_goal", "帮助学生理解题意和解题思路。"),
                "wrap_up": solution.get("conclusion", "把题目条件重新组织后得出答案。") if isinstance(solution, dict) else "把题目条件重新组织后得出答案。",
            },
            "teacher_controls": ["start", "previous_step", "next_step", "replay", "show_answer"],
            "demo_data": _build_demo_data(question, scene_type, solution, theme),
            "scenes": _build_demo_scenes(question, scene_type, animation_plan, solution),
        },
        theme,
    )


def _build_demo_data(question: str, scene_type: str, solution: dict | None, theme: ThemeOption) -> dict:
    numbers = _extract_numbers(question)
    if scene_type == "average_share":
        total = int(numbers[0]) if numbers else 12
        groups = int(numbers[1]) if len(numbers) > 1 and int(numbers[1]) > 0 else 3
        return {
            "total": total,
            "groups": groups,
            "answer": solution.get("conclusion", "平均分后每份一样多。") if isinstance(solution, dict) else "平均分后每份一样多。",
            "item_name": theme.label,
        }
    if scene_type == "journey_meeting":
        return {
            "total_distance": int(numbers[0]) if numbers else 18,
            "elapsed_minutes": int(numbers[1]) if len(numbers) > 1 else 10,
            "answer": solution.get("conclusion", "先读图，再根据路程关系推理。") if isinstance(solution, dict) else "先读图，再根据路程关系推理。",
        }
    return {
        "answer": solution.get("conclusion", "按步骤理解题意。") if isinstance(solution, dict) else "按步骤理解题意。",
        "item_name": theme.label,
    }


def _build_demo_scenes(question: str, scene_type: str, animation_plan: dict, solution: dict | None) -> list[dict]:
    steps = animation_plan.get("storyboard_steps", []) if isinstance(animation_plan.get("storyboard_steps"), list) else []
    details = solution.get("steps", []) if isinstance(solution, dict) and isinstance(solution.get("steps"), list) else []
    merged_steps = steps or ["先读题", "找条件", "看方法", "回到答案"]

    scenes: list[dict] = []
    for index, title in enumerate(merged_steps[:4]):
        detail = details[index] if index < len(details) else f"围绕“{title}”理解这道题。"
        if scene_type == "journey_meeting":
            scenes.append(
                {
                    "id": f"scene_{index + 1}",
                    "title": title,
                    "narration": detail,
                    "teacher_tip": "先观察位置变化，再说数量关系。",
                    "focus_text": detail,
                    "journey": {
                        "leftProgress": min(0.4, index * 0.1),
                        "rightProgress": min(0.4, index * 0.1),
                        "leftLabel": "左侧角色",
                        "rightLabel": "右侧角色",
                        "caption": title,
                        "leftDistance": "先看左边这段变化",
                        "rightDistance": "再看右边这段变化",
                    },
                }
            )
        elif scene_type == "average_share":
            scenes.append(
                {
                    "id": f"scene_{index + 1}",
                    "title": title,
                    "narration": detail,
                    "teacher_tip": "轮流分，才能保证每份一样多。",
                    "focus_text": detail,
                    "distribution": [min(index + 1, 4), min(index + 1, 4), min(index + 1, 4)],
                }
            )
        else:
            scenes.append(
                {
                    "id": f"scene_{index + 1}",
                    "title": title,
                    "narration": detail,
                    "teacher_tip": "先把这一段看懂，再进入下一步。",
                    "focus_text": detail,
                }
            )
    return scenes


def _build_search_queries(question: str, demo_type: str, theme: ThemeOption) -> list[str]:
    if demo_type == "average_share":
        return [
            f"{theme.english} cartoon png",
            "kids sharing classroom cartoon",
            "school manipulatives cartoon png",
        ]
    if demo_type == "meeting_journey":
        return [
            f"{theme.english} classroom cartoon",
            "road map cartoon transparent",
            "distance line illustration classroom",
        ]
    if any(token in question for token in ("长方形", "面积", "周长")):
        return ["geometry shapes cartoon png", "math shapes clipart transparent", "classroom geometry cartoon"]
    return [
        f"{theme.english} cartoon png",
        f"{theme.english} clipart transparent",
        "math manipulatives cartoon png",
    ]


def _search_images(
    queries: list[str],
    theme: ThemeOption,
    animation_plan: dict,
    variation_seed: str,
    variant_label: str,
) -> list[dict]:
    """优先生成贴题图片素材；失败时退回外部检索和内置 SVG。"""

    generated_images = generate_animation_images(
        _build_image_generation_prompts(animation_plan, theme, variant_label),
        variation_seed=variation_seed,
    )
    if generated_images:
        return generated_images

    results: list[dict] = []
    seen_urls: set[str] = set()

    for query in queries:
        for item in _search_bing_image_results(query):
            image_url = item["image_url"]
            if image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            results.append(item)
            if len(results) >= 4:
                return results

    if results:
        return results

    return [
        {
            "query": theme.english,
            "image_url": _build_svg_data_uri(theme.label, theme.palette[0], theme.palette[1]),
            "source_page": "",
            "source_host": "内置 SVG",
        }
    ]


def _build_image_generation_prompts(animation_plan: dict, theme: ThemeOption, variant_label: str) -> list[str]:
    scene_type = animation_plan.get("scene_type", "generic_reasoning")
    teaching_goal = animation_plan.get("teaching_goal", "帮助小学生理解题意")
    summary = animation_plan.get("scene_summary", "小学数学互动动画")
    entities = animation_plan.get("visual_entities", [])
    entity_names = "、".join(entity.get("name", "数学对象") for entity in entities[:4]) or "数学对象"
    prompt_base = (
        f"Create a clean educational illustration for a Chinese elementary math interactive animation. "
        f"Variant style: {variant_label}. Theme: {theme.label}. Scene summary: {summary}. "
        f"Teaching goal: {teaching_goal}. Visual entities: {entity_names}. "
        "Flat cartoon style, child-friendly, clean background, warm lighting, classroom-safe, no text, no watermark."
    )

    if scene_type == "journey_meeting":
        return [
            prompt_base + " Two riders moving toward each other on a simple route map, side-view, clear motion feeling.",
            prompt_base + " A line-route classroom scene with two starting points and travel progress markers.",
        ]
    if scene_type == "average_share":
        return [
            prompt_base + " Cute manipulatives arranged for equal sharing, grouped clearly for children.",
            prompt_base + " Classroom tabletop with shareable math objects and group containers.",
        ]
    if scene_type == "area_cover":
        return [
            prompt_base + " Rectangle covered by small square tiles, geometric teaching illustration.",
            prompt_base + " Math classroom geometry board with rectangle grid and highlight blocks.",
        ]
    if scene_type == "fraction_partition":
        return [
            prompt_base + " A whole shape split into equal parts, some parts highlighted for fraction teaching.",
            prompt_base + " Fraction teaching visual with clear partitioned objects and bright highlights.",
        ]
    return [
        prompt_base + " A modular educational math illustration suitable for an interactive lesson.",
        prompt_base + " A clean child-friendly teaching scene with math props and focus objects.",
    ]


def _search_bing_image_results(query: str) -> list[dict]:
    request = Request(f"https://cn.bing.com/images/search?q={quote(query)}", headers={"User-Agent": SEARCH_USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            html_content = response.read().decode("utf-8", errors="ignore")
    except Exception:
        return []

    image_urls = re.findall(r"murl&quot;:&quot;(.*?)&quot;", html_content)
    source_pages = re.findall(r"purl&quot;:&quot;(.*?)&quot;", html_content)
    results: list[dict] = []

    for index, image_url in enumerate(image_urls[:10]):
        clean_image_url = html.unescape(image_url)
        if not clean_image_url.startswith("http"):
            continue
        source_page = html.unescape(source_pages[index]) if index < len(source_pages) else ""
        source_host = urlparse(source_page).netloc or urlparse(clean_image_url).netloc
        if source_host.startswith("www."):
            source_host = source_host[4:]
        results.append(
            {
                "query": query,
                "image_url": clean_image_url,
                "source_page": source_page,
                "source_host": source_host or "Bing 图片",
            }
        )
    return results


def _build_svg_data_uri(label: str, color_a: str, color_b: str) -> str:
    safe_label = html.escape(label)
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">
      <defs><linearGradient id="g" x1="0" x2="1" y1="0" y2="1"><stop offset="0%" stop-color="{color_a}" /><stop offset="100%" stop-color="{color_b}" /></linearGradient></defs>
      <rect width="320" height="320" rx="44" fill="url(#g)" />
      <circle cx="94" cy="100" r="42" fill="rgba(255,255,255,0.34)" />
      <circle cx="230" cy="84" r="24" fill="rgba(255,255,255,0.22)" />
      <circle cx="228" cy="220" r="58" fill="rgba(255,255,255,0.18)" />
      <text x="160" y="148" text-anchor="middle" font-size="38" font-family="Arial, sans-serif" fill="#ffffff">{safe_label}</text>
      <text x="160" y="198" text-anchor="middle" font-size="66" font-family="Arial, sans-serif" fill="#ffffff">123</text>
    </svg>
    """.strip()
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def _render_demo_html(demo_spec: dict, images: list[dict], theme: ThemeOption) -> str:
    """把动画配置和图片素材拼成单文件 HTML。"""

    palette_a, palette_b = theme.palette
    image_urls = [item["image_url"] for item in images]
    fallback_images = [
        _build_svg_data_uri(theme.label, palette_a, palette_b),
        _build_svg_data_uri(theme.label, palette_b, palette_a),
    ]
    config = {
        "title": demo_spec["title"],
        "summary": demo_spec["summary"],
        "question": demo_spec["question"],
        "equation": demo_spec["equation"],
        "variationLabel": demo_spec.get("variation_label", "标准版"),
        "variationSeed": demo_spec.get("variation_seed", ""),
        "knowledgeFocus": demo_spec.get("knowledge_focus", []),
        "animationPlan": demo_spec.get("animation_plan", {}),
        "teacherPanel": demo_spec.get("teacher_panel", {}),
        "teacherControls": demo_spec.get("teacher_controls", []),
        "demoType": demo_spec["demo_type"],
        "demoData": demo_spec.get("demo_data", {}),
        "scenes": demo_spec.get("scenes", []),
        "images": image_urls,
        "fallbackImages": fallback_images,
        "maxDisplayTokens": MAX_DISPLAY_TOKENS,
    }

    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />"
        f"<title>{html.escape(demo_spec['title'])}</title><style>{_demo_css(palette_a, palette_b)}</style></head>"
        "<body><div class=\"shell\">"
        "<section class=\"hero\">"
        "<div class=\"hero-copy\"><span class=\"eyebrow\">互动动画演示</span><h1 id=\"title\"></h1><p class=\"summary\" id=\"summary\"></p><div class=\"hero-meta\"><span class=\"hero-pill\" id=\"question-pill\"></span><span class=\"hero-pill\" id=\"focus-pill\"></span></div></div>"
        "<div class=\"hero-visual\"><img id=\"hero-image\" alt=\"动画素材\" /></div></section>"
        "<section class=\"stage-shell\">"
        "<div class=\"stage-lights\" aria-hidden=\"true\"><span></span><span></span><span></span></div>"
        "<div class=\"layout\">"
        "<aside class=\"sidebar explain-sidebar\">"
        "<section class=\"side-card\"><span class=\"eyebrow\">题目讲解</span><h2 class=\"side-title\">先看题意，再跟着动画一步步理解</h2><p id=\"teacher-intro\"></p></section>"
        "<section class=\"side-card question-card\"><span class=\"mini-tag\">题目</span><p id=\"question-copy\"></p></section>"
        "<section class=\"side-card\"><span class=\"mini-tag\">分步说明</span><div class=\"step-list\" id=\"step-list\"></div></section>"
        "<section class=\"side-card teacher-card-stack\"><article class=\"teacher-card\"><span class=\"mini-tag\">当前讲解</span><h3 id=\"scene-title\"></h3><strong id=\"scene-index\"></strong><p id=\"scene-copy\"></p></article><article class=\"teacher-card\"><span class=\"mini-tag\">教师提示</span><p id=\"scene-tip\"></p></article><article class=\"teacher-card\"><span class=\"mini-tag\">答案线索</span><div class=\"equation-box\" id=\"equation-box\"></div><p id=\"teacher-wrap\"></p></article></section>"
        "</aside>"
        "<section class=\"stage preview-stage\">"
        "<div class=\"stage-top\"><div><span class=\"mini-tag\">互动动画预览</span><h2>右侧舞台</h2></div><div class=\"scene-progress\"><strong>当前焦点</strong><span id=\"scene-focus\"></span></div></div>"
        "<div class=\"demo-stage\" id=\"demo-stage\"><div class=\"stage-backdrop\"></div><div class=\"stage-floor\"></div><div class=\"demo-board\"><div class=\"source-card\"><span class=\"mini-tag\">动画舞台</span><h3 id=\"source-title\"></h3><div class=\"token-grid\" id=\"source-grid\"></div></div><div class=\"target-card\"><span class=\"mini-tag\">互动观察区</span><div class=\"group-grid\" id=\"group-grid\"></div></div></div></div>"
        "<div class=\"control-panel\"><div class=\"control-row\"><button class=\"control-btn\" id=\"start-btn\" type=\"button\">开始</button><button class=\"control-btn control-btn--soft\" id=\"prev-btn\" type=\"button\">上一步</button><button class=\"control-btn control-btn--soft\" id=\"next-btn\" type=\"button\">下一步</button><button class=\"control-btn control-btn--soft\" id=\"replay-btn\" type=\"button\">重播</button><button class=\"control-btn\" id=\"answer-btn\" type=\"button\">显示答案</button></div></div>"
        "</section>"
        "</div></section>"
        "</div></div>"
        f"<script>const config = {json.dumps(config, ensure_ascii=False)};{_demo_script()}</script>"
        "</body></html>"
    )


def _demo_css(color_a: str, color_b: str) -> str:
    return f"""
    :root {{ --peach:{color_a}; --mint:{color_b}; --ink:#2f241d; --soft:#6d5c4f; --panel:rgba(255,251,245,0.96); --line:rgba(123,101,77,0.16); --spot:rgba(255,255,255,0.72); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Microsoft YaHei","PingFang SC",sans-serif; color:var(--ink); background:radial-gradient(circle at top, rgba(255,255,255,0.6), transparent 24%), linear-gradient(180deg,#fbf3e6,#edf3ec); }}
    .shell {{ max-width:1220px; margin:0 auto; padding:24px 18px 40px; }}
    .hero,.stage,.side-card {{ border:1px solid var(--line); border-radius:28px; background:var(--panel); box-shadow:0 18px 38px rgba(85,65,44,0.08); }}
    .hero {{ display:grid; grid-template-columns:minmax(0,1fr) 280px; gap:18px; align-items:center; padding:24px; }}
    .eyebrow,.mini-tag,.hero-pill {{ display:inline-flex; align-items:center; justify-content:center; border-radius:999px; }}
    .eyebrow,.mini-tag {{ padding:5px 10px; background:rgba(255,255,255,0.78); color:var(--soft); font-size:12px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; width:fit-content; }}
    .hero h1 {{ margin:12px 0 0; font-size:clamp(32px,4vw,48px); line-height:1.12; }}
    .summary {{ margin:14px 0 0; line-height:1.8; font-size:16px; }}
    .hero-meta {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:18px; }}
    .hero-pill {{ min-height:34px; padding:0 12px; background:rgba(255,255,255,0.84); color:var(--soft); font-size:13px; font-weight:700; }}
    .hero-visual img {{ width:100%; max-width:240px; aspect-ratio:1/1; object-fit:cover; border-radius:26px; background:linear-gradient(160deg,rgba(255,255,255,0.84),rgba(235,238,236,0.84)); box-shadow:0 14px 26px rgba(85,65,44,0.12); }}
    .stage-shell {{ position:relative; margin-top:22px; padding:18px; border-radius:36px; background:linear-gradient(180deg, rgba(93,63,41,0.1), rgba(255,255,255,0.36)); box-shadow:inset 0 1px 0 rgba(255,255,255,0.6); }}
    .stage-lights {{ position:absolute; inset:0 0 auto; height:130px; pointer-events:none; overflow:hidden; }}
    .stage-lights span {{ position:absolute; top:-80px; width:220px; height:220px; border-radius:50%; background:radial-gradient(circle, var(--spot), transparent 68%); filter:blur(6px); opacity:0.65; }}
    .stage-lights span:nth-child(1) {{ left:8%; }}
    .stage-lights span:nth-child(2) {{ left:38%; width:260px; height:260px; opacity:0.8; }}
    .stage-lights span:nth-child(3) {{ right:10%; }}
    .layout {{ position:relative; display:grid; grid-template-columns:380px minmax(0,1fr); gap:18px; align-items:start; }}
    .stage {{ padding:22px; display:grid; gap:18px; overflow:hidden; }}
    .explain-sidebar {{ position:sticky; top:18px; }}
    .side-title {{ margin:12px 0 0; font-size:28px; line-height:1.3; font-family:"STKaiti","KaiTi",serif; }}
    .stage-top {{ display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; align-items:flex-end; }}
    .stage-top h2 {{ margin:10px 0 0; font-size:30px; font-family:"STKaiti","KaiTi",serif; }}
    .scene-progress {{ display:grid; gap:8px; color:var(--soft); max-width:360px; }}
    .question-board,.source-card,.target-card,.teacher-card {{ border:1px solid rgba(123,101,77,0.12); border-radius:24px; background:rgba(255,255,255,0.78); padding:18px; }}
    .question-board p,.teacher-card p {{ margin:12px 0 0; line-height:1.8; }}
    .question-card p {{ margin:12px 0 0; font-size:16px; line-height:1.85; }}
    .step-list {{ display:grid; gap:12px; margin-top:14px; }}
    .step-chip {{ display:grid; gap:6px; padding:14px 16px; border-radius:18px; border:1px solid rgba(123,101,77,0.12); background:rgba(255,255,255,0.78); cursor:pointer; transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease, background .18s ease; text-align:left; }}
    .step-chip:hover {{ transform:translateY(-1px); border-color:rgba(188,127,71,0.24); box-shadow:0 10px 20px rgba(89,68,47,0.08); }}
    .step-chip.is-active {{ border-color:rgba(188,127,71,0.3); background:rgba(255,247,238,0.94); box-shadow:0 12px 24px rgba(188,127,71,0.1); }}
    .step-chip strong {{ font-size:14px; }}
    .step-chip span {{ color:var(--soft); font-size:13px; line-height:1.6; }}
    .teacher-card-stack {{ display:grid; gap:14px; }}
    .teacher-card h3 {{ margin:12px 0 0; font-size:24px; font-family:"STKaiti","KaiTi",serif; }}
    .demo-stage {{ position:relative; min-height:430px; padding:28px 22px 34px; border-radius:30px; background:linear-gradient(180deg, rgba(255,255,255,0.64), rgba(245,232,218,0.76)); perspective:1600px; overflow:hidden; }}
    .stage-backdrop {{ position:absolute; inset:18px 18px auto; height:58%; border-radius:28px; background:radial-gradient(circle at top, rgba(255,255,255,0.78), transparent 55%), linear-gradient(180deg, rgba(255,255,255,0.48), rgba(231,217,198,0.88)); border:1px solid rgba(123,101,77,0.08); }}
    .stage-floor {{ position:absolute; left:7%; right:7%; bottom:20px; height:112px; border-radius:50%; background:radial-gradient(circle, rgba(163,122,89,0.22), rgba(163,122,89,0.04) 58%, transparent 75%); transform:rotateX(72deg); transform-origin:center top; }}
    .demo-board {{ position:relative; z-index:1; display:grid; grid-template-columns:320px minmax(0,1fr); gap:18px; align-items:start; transform-style:preserve-3d; }}
    .source-card h3 {{ margin:12px 0 0; font-size:20px; }}
    .source-card,.target-card {{ box-shadow:0 22px 34px rgba(97,71,45,0.1); transform:translateZ(24px) rotateX(3deg); transform-style:preserve-3d; backdrop-filter:blur(6px); }}
    .source-card {{ transform:translateZ(28px) rotateY(-4deg) rotateX(3deg); }}
    .target-card {{ transform:translateZ(16px) rotateY(3deg) rotateX(3deg); }}
    .token-grid {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; min-height:88px; align-items:flex-start; }}
    .token {{ width:64px; display:grid; gap:6px; justify-items:center; transition:transform .45s cubic-bezier(.22,.61,.36,1), opacity .45s ease; animation:tokenFloat 3.4s ease-in-out infinite, tokenEnter .48s cubic-bezier(.2,.8,.2,1); animation-delay:calc(var(--delay) * .08s), calc(var(--delay) * .04s); transform-origin:center bottom; }}
    .token img {{ width:64px; height:64px; object-fit:cover; border-radius:16px; background:rgba(255,255,255,0.86); box-shadow:0 14px 26px rgba(89,68,47,0.14); }}
    .token span {{ font-size:12px; color:var(--soft); text-align:center; }}
    .group-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-top:14px; }}
    .group-card {{ position:relative; border:1px dashed rgba(123,101,77,0.18); border-radius:22px; background:linear-gradient(180deg, rgba(255,255,255,0.92), rgba(248,240,229,0.9)); padding:16px; min-height:220px; display:grid; gap:10px; align-content:start; transition:transform .32s ease, box-shadow .32s ease, border-color .32s ease; transform:translateZ(8px) rotateX(6deg); box-shadow:0 18px 22px rgba(125,86,50,0.08); }}
    .group-card::after {{ content:''; position:absolute; left:10%; right:10%; bottom:-10px; height:22px; border-radius:50%; background:radial-gradient(circle, rgba(120,90,60,0.18), transparent 70%); }}
    .group-card.is-highlight {{ transform:translateY(-6px) translateZ(20px) rotateX(3deg); border-color:rgba(188,127,71,0.32); box-shadow:0 20px 28px rgba(125,86,50,0.12); }}
    .group-card.is-answer {{ border-color:rgba(79,140,104,0.34); box-shadow:0 0 0 2px rgba(79,140,104,0.08) inset; }}
    .group-card strong {{ font-size:16px; }}
    .journey-stage {{ display:grid; gap:16px; margin-top:14px; }}
    .journey-track {{ position:relative; min-height:150px; border-radius:24px; padding:28px 18px 20px; background:linear-gradient(180deg, rgba(255,255,255,0.92), rgba(248,240,229,0.92)); border:1px solid rgba(123,101,77,0.12); overflow:hidden; }}
    .journey-line {{ position:absolute; left:10%; right:10%; top:72px; height:10px; border-radius:999px; background:linear-gradient(90deg, rgba(130,173,219,0.42), rgba(255,197,143,0.58)); }}
    .journey-home {{ position:absolute; top:48px; font-size:13px; font-weight:700; color:var(--soft); }}
    .journey-home--left {{ left:8%; }}
    .journey-home--right {{ right:8%; }}
    .journey-rider {{ position:absolute; top:28px; width:82px; display:grid; justify-items:center; gap:8px; transform:translateX(-50%); }}
    .journey-rider img {{ width:64px; height:64px; object-fit:cover; border-radius:18px; background:rgba(255,255,255,0.88); box-shadow:0 14px 26px rgba(89,68,47,0.14); }}
    .journey-rider span {{ font-size:12px; color:var(--soft); text-align:center; }}
    .journey-caption {{ display:grid; gap:10px; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); }}
    .journey-stat {{ min-height:72px; border-radius:18px; padding:14px; background:rgba(255,255,255,0.78); border:1px solid rgba(123,101,77,0.12); }}
    .journey-stat strong {{ display:block; font-size:14px; }}
    .journey-stat span {{ display:block; margin-top:8px; color:var(--soft); line-height:1.6; }}
    .control-panel {{ display:grid; gap:16px; }}
    .control-row {{ display:flex; flex-wrap:wrap; gap:12px; }}
    .control-btn {{ border:0; border-radius:18px; min-height:48px; padding:0 18px; background:linear-gradient(135deg,var(--peach),#f3ae7a); color:#fff; font-weight:700; cursor:pointer; transition:transform .2s ease, opacity .2s ease, box-shadow .2s ease; box-shadow:0 12px 22px rgba(188,127,71,0.16); }}
    .control-btn:hover {{ transform:translateY(-1px); }}
    .control-btn--soft {{ background:rgba(255,255,255,0.84); color:var(--ink); border:1px solid rgba(123,101,77,0.12); box-shadow:none; }}
    .control-btn:disabled {{ opacity:.6; cursor:not-allowed; transform:none; box-shadow:none; }}
    .equation-box {{ margin-top:12px; min-height:54px; display:flex; align-items:center; justify-content:center; border-radius:18px; background:rgba(255,248,239,0.9); font-family:"STKaiti","KaiTi",serif; font-size:34px; }}
    .sidebar {{ display:grid; gap:18px; align-content:start; }}
    .side-card {{ padding:18px; }}
    @keyframes tokenFloat {{ 0%,100% {{ transform:translateY(0) translateZ(0); }} 50% {{ transform:translateY(-8px) translateZ(10px); }} }}
    @keyframes tokenEnter {{ from {{ opacity:0; transform:translateY(26px) scale(.84) rotateX(-28deg); }} to {{ opacity:1; transform:translateY(0) scale(1) rotateX(0deg); }} }}
    @keyframes stageFlash {{ from {{ opacity:0; transform:translateY(18px) scale(.98); }} to {{ opacity:1; transform:translateY(0) scale(1); }} }}
    .demo-stage.is-changing .demo-board {{ animation:stageFlash .42s ease; }}
    @media (max-width:960px) {{ .hero,.layout,.demo-board {{ grid-template-columns:1fr; }} .explain-sidebar {{ position:static; }} .control-row {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }} .control-btn {{ width:100%; }} }}
    """


def _demo_script() -> str:
    return """
    const state = { sceneIndex: 0, autoPlaying: false, timer: null };
    const titleEl = document.getElementById('title');
    const summaryEl = document.getElementById('summary');
    const questionPillEl = document.getElementById('question-pill');
    const focusPillEl = document.getElementById('focus-pill');
    const heroImageEl = document.getElementById('hero-image');
    const sceneTitleEl = document.getElementById('scene-title');
    const sceneIndexEl = document.getElementById('scene-index');
    const sceneFocusEl = document.getElementById('scene-focus');
    const questionCopyEl = document.getElementById('question-copy');
    const sourceTitleEl = document.getElementById('source-title');
    const sourceGridEl = document.getElementById('source-grid');
    const groupGridEl = document.getElementById('group-grid');
    const sceneCopyEl = document.getElementById('scene-copy');
    const sceneTipEl = document.getElementById('scene-tip');
    const equationBoxEl = document.getElementById('equation-box');
    const teacherWrapEl = document.getElementById('teacher-wrap');
    const teacherIntroEl = document.getElementById('teacher-intro');
    const stepListEl = document.getElementById('step-list');
    const demoStageEl = document.getElementById('demo-stage');
    const startBtn = document.getElementById('start-btn');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const replayBtn = document.getElementById('replay-btn');
    const answerBtn = document.getElementById('answer-btn');

    titleEl.textContent = config.title;
    summaryEl.textContent = config.summary;
    questionPillEl.textContent = `题目：${config.question}`;
    focusPillEl.textContent = `版本：${config.variationLabel || '标准版'}`;
    questionCopyEl.textContent = config.question;
    teacherIntroEl.textContent = config.teacherPanel?.intro || '今天我们一起看这道题。';
    heroImageEl.src = config.images[0] || config.fallbackImages[0];
    heroImageEl.onerror = () => { heroImageEl.onerror = null; heroImageEl.src = config.fallbackImages[0]; };
    function currentScene() { return (config.scenes || [])[state.sceneIndex] || (config.scenes || [])[0] || {}; }
    function assetUrl(index) { return (config.images[index % Math.max(config.images.length, 1)] || '') || config.fallbackImages[index % config.fallbackImages.length]; }
    function stopAutoPlay() { clearInterval(state.timer); state.timer = null; state.autoPlaying = false; startBtn.textContent = '开始'; }
    function renderStepList() {
      if (!stepListEl) { return; }
      stepListEl.innerHTML = '';
      (config.scenes || []).forEach((scene, index) => {
        const item = document.createElement('button');
        item.type = 'button';
        item.className = `step-chip${index === state.sceneIndex ? ' is-active' : ''}`;
        item.innerHTML = `<strong>第 ${index + 1} 步：${scene.title || '互动步骤'}</strong><span>${scene.narration || scene.focus_text || '跟着这一段动画理解题意。'}</span>`;
        item.addEventListener('click', () => { stopAutoPlay(); stepTo(index); });
        stepListEl.appendChild(item);
      });
    }
    function triggerStageChange() {
      if (!demoStageEl) { return; }
      demoStageEl.classList.remove('is-changing');
      void demoStageEl.offsetWidth;
      demoStageEl.classList.add('is-changing');
      window.setTimeout(() => demoStageEl.classList.remove('is-changing'), 430);
    }
    function createToken(index, label) {
      const token = document.createElement('div'); token.className = 'token'; token.style.setProperty('--delay', String(index));
      const image = document.createElement('img'); image.src = assetUrl(index); image.alt = label; image.onerror = () => { image.onerror = null; image.src = config.fallbackImages[index % config.fallbackImages.length]; };
      const caption = document.createElement('span'); caption.textContent = label;
      token.appendChild(image); token.appendChild(caption); return token;
    }
    function renderAverageShare(scene, showAnswer = false) {
      const total = Number(config.demoData?.total || 0);
      const itemName = config.demoData?.item_name || '物品';
      const distributed = (scene.distribution || []).reduce((sum, value) => sum + Number(value || 0), 0);
      const left = Math.max(total - distributed, 0);
      sourceTitleEl.textContent = `还剩 ${left} 个${itemName}`;
      sourceGridEl.innerHTML = '';
      groupGridEl.innerHTML = '';
      const visible = Math.min(left, config.maxDisplayTokens || 18);
      for (let index = 0; index < visible; index += 1) { sourceGridEl.appendChild(createToken(index, itemName)); }
      if (left > visible) { const more = document.createElement('span'); more.className = 'hero-pill'; more.textContent = `还有 ${left - visible} 个`; sourceGridEl.appendChild(more); }
      (scene.distribution || []).forEach((count, groupIndex) => {
        const card = document.createElement('div');
        card.className = `group-card${count > 0 ? ' is-highlight' : ''}${showAnswer ? ' is-answer' : ''}`;
        const title = document.createElement('strong'); title.textContent = `第 ${groupIndex + 1} 组`;
        const status = document.createElement('span'); status.className = 'hero-pill'; status.textContent = `现在有 ${count} 个`;
        const grid = document.createElement('div'); grid.className = 'token-grid';
        for (let tokenIndex = 0; tokenIndex < Math.min(Number(count || 0), config.maxDisplayTokens || 18); tokenIndex += 1) {
          grid.appendChild(createToken(tokenIndex + groupIndex, itemName));
        }
        card.appendChild(title); card.appendChild(status); card.appendChild(grid); groupGridEl.appendChild(card);
      });
    }
    function renderGeneric(scene, showAnswer = false) {
      sourceTitleEl.textContent = '当前演示';
      sourceGridEl.innerHTML = '';
      groupGridEl.innerHTML = '';
      const card = document.createElement('div'); card.className = 'group-card';
      card.innerHTML = `<strong>${showAnswer ? '答案' : '观察重点'}</strong><p>${showAnswer ? (config.teacherPanel?.wrap_up || config.demoData?.answer || '') : (scene.focus_text || '')}</p>`;
      groupGridEl.appendChild(card);
    }
    function renderMeetingJourney(scene, showAnswer = false) {
      const journey = scene.journey || {};
      sourceTitleEl.textContent = journey.caption || '相向而行';
      sourceGridEl.innerHTML = '';
      groupGridEl.innerHTML = '';
      const knowledge = document.createElement('span');
      knowledge.className = 'hero-pill';
      knowledge.textContent = `知识点：${(config.knowledgeFocus || [])[0] || '行程关系'}`;
      sourceGridEl.appendChild(knowledge);
      const seed = document.createElement('span');
      seed.className = 'hero-pill';
      seed.textContent = `变体：${(config.variationSeed || '').slice(0, 8) || '默认'}`;
      sourceGridEl.appendChild(seed);

      const stage = document.createElement('div');
      stage.className = 'journey-stage';
      stage.innerHTML = `
        <div class="journey-track">
          <div class="journey-line"></div>
          <span class="journey-home journey-home--left">${journey.leftLabel || '左边出发点'}</span>
          <span class="journey-home journey-home--right">${journey.rightLabel || '右边出发点'}</span>
          <div class="journey-rider" style="left:${10 + Math.max(0, Math.min(80, Number(journey.leftProgress || 0) * 80))}%">
            <img src="${assetUrl(0)}" alt="${journey.leftLabel || '左侧角色'}" />
            <span>${journey.leftLabel || '左侧角色'}</span>
          </div>
          <div class="journey-rider" style="left:${90 - Math.max(0, Math.min(80, Number(journey.rightProgress || 0) * 80))}%">
            <img src="${assetUrl(1)}" alt="${journey.rightLabel || '右侧角色'}" />
            <span>${journey.rightLabel || '右侧角色'}</span>
          </div>
        </div>
      `;
      const caption = document.createElement('div');
      caption.className = 'journey-caption';
      caption.innerHTML = `
        <div class="journey-stat"><strong>左侧观察</strong><span>${journey.leftDistance || '先看左侧信息'}</span></div>
        <div class="journey-stat"><strong>右侧观察</strong><span>${journey.rightDistance || '再看右侧信息'}</span></div>
        <div class="journey-stat"><strong>${showAnswer ? '答案线索' : '课堂提醒'}</strong><span>${showAnswer ? (config.teacherPanel?.wrap_up || config.demoData?.answer || '') : (scene.focus_text || '')}</span></div>
      `;
      stage.appendChild(caption);
      groupGridEl.appendChild(stage);
    }
    function renderScene(showAnswer = false) {
      const scene = currentScene();
      triggerStageChange();
      sceneTitleEl.textContent = scene.title || '互动动画演示';
      sceneIndexEl.textContent = `第 ${state.sceneIndex + 1} 步 / 共 ${(config.scenes || []).length} 步`;
      sceneFocusEl.textContent = scene.focus_text || config.equation || '';
      sceneCopyEl.textContent = scene.narration || '';
      sceneTipEl.textContent = scene.teacher_tip || config.teacherPanel?.focus || '';
      teacherWrapEl.textContent = showAnswer ? (config.teacherPanel?.wrap_up || config.demoData?.answer || '') : (config.teacherPanel?.focus || '');
      equationBoxEl.textContent = showAnswer ? (config.equation || config.demoData?.answer || '') : (scene.focus_text || '跟着动画观察变化');
      renderStepList();
      if (config.demoType === 'average_share') renderAverageShare(scene, showAnswer);
      else if (config.demoType === 'meeting_journey') renderMeetingJourney(scene, showAnswer);
      else renderGeneric(scene, showAnswer);
      prevBtn.disabled = state.sceneIndex === 0;
      nextBtn.disabled = state.sceneIndex >= (config.scenes || []).length - 1;
    }
    function stepTo(index) { state.sceneIndex = Math.max(0, Math.min(index, (config.scenes || []).length - 1)); renderScene(); }
    function autoPlay() {
      if (state.autoPlaying) { stopAutoPlay(); return; }
      stopAutoPlay(); state.autoPlaying = true; startBtn.textContent = '暂停';
      state.timer = window.setInterval(() => {
        if (state.sceneIndex >= (config.scenes || []).length - 1) { stopAutoPlay(); renderScene(); return; }
        state.sceneIndex += 1; renderScene();
      }, 1200);
    }
    startBtn.addEventListener('click', autoPlay);
    prevBtn.addEventListener('click', () => { stopAutoPlay(); stepTo(state.sceneIndex - 1); });
    nextBtn.addEventListener('click', () => { stopAutoPlay(); stepTo(state.sceneIndex + 1); });
    replayBtn.addEventListener('click', () => { stopAutoPlay(); stepTo(0); });
    answerBtn.addEventListener('click', () => { stopAutoPlay(); stepTo((config.scenes || []).length - 1); renderScene(true); });
    renderScene();
    """
