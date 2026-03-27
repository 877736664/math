"""互动动画生成服务，输出可直接嵌入页面的 HTML。"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app.rag_service import retrieve_knowledge, solve_question_with_docs


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


THEME_OPTIONS: tuple[ThemeOption, ...] = (
    ThemeOption(("糖", "糖果"), "糖果", "candy", ("#f7b7d7", "#ff8e6e")),
    ThemeOption(("苹果",), "苹果", "apple", ("#f9c86c", "#eb6d52")),
    ThemeOption(("花", "盆花"), "花朵", "flower", ("#ffc2da", "#f28db2")),
    ThemeOption(("球",), "小球", "ball", ("#b8f0d2", "#57b48d")),
)
DEFAULT_THEME = ThemeOption(("数字",), "数字积木", "math blocks", ("#b7d6ff", "#8fd0b2"))


def generate_animation_game(grade: int, question: str, textbook: dict | None = None) -> dict:
    """基于检索结果生成互动动画的配置和 HTML 页面。"""

    documents = retrieve_knowledge(question, grade, textbook=textbook)
    solution = solve_question_with_docs(question, documents)
    demo_spec = _build_demo_spec(grade, question, solution)
    theme = _pick_theme(question)
    images = _search_images(_build_search_queries(question, demo_spec["demo_type"], theme), theme)
    html_content = _render_demo_html(demo_spec, images, theme)

    return {
        "title": demo_spec["title"],
        "summary": demo_spec["summary"],
        "html": html_content,
        "demo_spec": demo_spec,
    }


def _build_demo_spec(grade: int, question: str, solution: dict | None) -> dict:
    """根据题型选择平均分动画或通用讲解动画。"""

    operation = _detect_operation(question)
    if operation == "division":
        return _build_average_share_demo(grade, question, solution)
    return _build_generic_demo(grade, question, solution)


def _build_average_share_demo(grade: int, question: str, solution: dict | None) -> dict:
    numbers = _extract_numbers(question)
    total = int(numbers[0]) if numbers else 12
    groups = int(numbers[1]) if len(numbers) > 1 and int(numbers[1]) > 0 else 3
    answer = total // groups if groups else 0
    theme = _pick_theme(question)

    distributions: list[list[int]] = [[0 for _ in range(groups)]]
    current = [0 for _ in range(groups)]
    for _ in range(answer):
        current = [value + 1 for value in current]
        distributions.append(current[:])

    scenes = [
        {
            "id": "scene_intro",
            "title": "先读题目",
            "narration": f"一共有 {total} 个{theme.label}，要平均分给 {groups} 个同学。",
            "teacher_tip": "先说出总数，再说要分成几份。",
            "distribution": distributions[0],
            "focus_text": f"总数 {total}，分成 {groups} 份",
        }
    ]

    for index, distribution in enumerate(distributions[1:], start=1):
        scenes.append(
            {
                "id": f"scene_step_{index}",
                "title": f"第 {index} 轮平均分",
                "narration": f"第 {index} 轮轮流分下去，现在每个同学手里都有 {index} 个{theme.label}。",
                "teacher_tip": "每次都轮流分，所以每份一直一样多。",
                "distribution": distribution,
                "focus_text": f"每份现在有 {index} 个",
            }
        )

    scenes.append(
        {
            "id": "scene_answer",
            "title": "得到答案",
            "narration": f"平均分完以后，每个同学分到 {answer} 个{theme.label}。",
            "teacher_tip": "最后再回到题目，确认每份是多少。",
            "distribution": distributions[-1],
            "focus_text": f"{total} ÷ {groups} = {answer}",
        }
    )

    practice_total = total + groups
    practice_answer = practice_total // groups if groups else 0

    return {
        "version": "2.0",
        "demo_type": "average_share",
        "title": f"{theme.label}平均分互动动画",
        "summary": "这是可交互动画 HTML，适合老师投屏演示。可以一步一步播放平均分过程，也可以随时显示答案。",
        "grade": grade,
        "question": question,
        "equation": f"{total} ÷ {groups} = {answer}",
        "teacher_controls": ["start", "previous_step", "next_step", "replay", "show_answer"],
        "teacher_panel": {
            "intro": f"今天我们用{theme.label}来理解平均分。",
            "focus": "关键不是分得快，而是每一份都一样多。",
            "wrap_up": f"分完以后，每份都是 {answer} 个{theme.label}。",
        },
        "demo_data": {
            "item_name": theme.label,
            "total": total,
            "groups": groups,
            "answer": answer,
            "practice_question": f"如果有 {practice_total} 个{theme.label}平均分给 {groups} 个同学，每人几个？",
            "practice_equation": f"{practice_total} ÷ {groups} = {practice_answer}",
            "practice_answer": practice_answer,
        },
        "scenes": scenes,
    }


def _build_generic_demo(grade: int, question: str, solution: dict | None) -> dict:
    theme = _pick_theme(question)
    steps = solution.get("steps", [])[:3] if solution else []
    if not steps:
        steps = [
            "先看清题目里的数字和关键词。",
            "再判断应该用什么方法。",
            "最后根据算式得出答案。",
        ]

    equation = steps[0] if solution and solution.get("steps") else "先读题，再观察数量变化。"
    answer = solution.get("conclusion", "请根据演示说出答案") if solution else "请根据演示说出答案"
    scenes = [
        {
            "id": "scene_intro",
            "title": "先看题目",
            "narration": question,
            "teacher_tip": "先带学生复述题目。",
            "focus_text": "先读题，再想条件和问题。",
        },
        {
            "id": "scene_method",
            "title": "再看方法",
            "narration": steps[1] if len(steps) > 1 else steps[0],
            "teacher_tip": "讲清楚为什么用这种方法。",
            "focus_text": equation,
        },
        {
            "id": "scene_answer",
            "title": "最后得到答案",
            "narration": str(answer),
            "teacher_tip": "最后再检查答案是否合理。",
            "focus_text": str(answer),
        },
    ]

    return {
        "version": "2.0",
        "demo_type": "generic_math",
        "title": f"{theme.label}互动动画演示",
        "summary": "这是可交互动画 HTML，老师可以点击开始、上一步、下一步、重播和显示答案，按步骤讲解题目。",
        "grade": grade,
        "question": question,
        "equation": equation,
        "teacher_controls": ["start", "previous_step", "next_step", "replay", "show_answer"],
        "teacher_panel": {
            "intro": "先把题目说清楚，再进入演示。",
            "focus": "引导学生边看动画边说思路。",
            "wrap_up": str(answer),
        },
        "demo_data": {
            "item_name": theme.label,
            "answer": str(answer),
        },
        "scenes": scenes,
    }


def _detect_operation(question: str) -> str:
    if any(word in question for word in ("平均分", "平分", "均分", "每人", "每份")):
        return "division"
    return "generic"


def _pick_theme(question: str) -> ThemeOption:
    for option in THEME_OPTIONS:
        if any(keyword in question for keyword in option.keywords):
            return option
    return DEFAULT_THEME


def _extract_numbers(question: str) -> list[int]:
    return [int(token) for token in re.findall(r"\d+", question)]


def _build_search_queries(question: str, demo_type: str, theme: ThemeOption) -> list[str]:
    if demo_type == "average_share":
        return [
            f"{theme.english} cartoon png",
            "kids sharing classroom cartoon",
            "school manipulatives cartoon png",
        ]
    if any(token in question for token in ("长方形", "面积", "周长")):
        return ["geometry shapes cartoon png", "math shapes clipart transparent", "classroom geometry cartoon"]
    return [
        f"{theme.english} cartoon png",
        f"{theme.english} clipart transparent",
        "math manipulatives cartoon png",
    ]


def _search_images(queries: list[str], theme: ThemeOption) -> list[dict]:
    """尝试抓取外部图片素材；失败时回退到内置 SVG。"""

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
        "<section class=\"stage\">"
        "<div class=\"stage-top\"><div><span class=\"mini-tag\">当前步骤</span><h2 id=\"scene-title\"></h2></div><div class=\"scene-progress\"><strong id=\"scene-index\"></strong><span id=\"scene-focus\"></span></div></div>"
        "<div class=\"question-board\"><span class=\"mini-tag\">题目</span><p id=\"question-copy\"></p></div>"
        "<div class=\"demo-stage\" id=\"demo-stage\"><div class=\"stage-backdrop\"></div><div class=\"stage-floor\"></div><div class=\"demo-board\"><div class=\"source-card\"><span class=\"mini-tag\">动画舞台</span><h3 id=\"source-title\"></h3><div class=\"token-grid\" id=\"source-grid\"></div></div><div class=\"target-card\"><span class=\"mini-tag\">分配结果</span><div class=\"group-grid\" id=\"group-grid\"></div></div></div></div>"
        "<div class=\"control-panel\"><div class=\"control-row\"><button class=\"control-btn\" id=\"start-btn\" type=\"button\">开始</button><button class=\"control-btn control-btn--soft\" id=\"prev-btn\" type=\"button\">上一步</button><button class=\"control-btn control-btn--soft\" id=\"next-btn\" type=\"button\">下一步</button><button class=\"control-btn control-btn--soft\" id=\"replay-btn\" type=\"button\">重播</button><button class=\"control-btn\" id=\"answer-btn\" type=\"button\">显示答案</button></div><div class=\"teacher-grid\"><article class=\"teacher-card\"><span class=\"mini-tag\">讲解旁白</span><p id=\"scene-copy\"></p></article><article class=\"teacher-card\"><span class=\"mini-tag\">教师提示</span><p id=\"scene-tip\"></p></article><article class=\"teacher-card\"><span class=\"mini-tag\">答案线索</span><div class=\"equation-box\" id=\"equation-box\"></div><p id=\"teacher-wrap\"></p></article></div></div>"
        "</section>"
        "<aside class=\"sidebar\"><section class=\"side-card\"><span class=\"eyebrow\">课堂提醒</span><p id=\"teacher-intro\"></p></section></aside>"
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
    .layout {{ position:relative; display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:18px; }}
    .stage {{ padding:22px; display:grid; gap:18px; overflow:hidden; }}
    .stage-top {{ display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap; align-items:flex-end; }}
    .stage-top h2 {{ margin:10px 0 0; font-size:30px; font-family:"STKaiti","KaiTi",serif; }}
    .scene-progress {{ display:grid; gap:8px; color:var(--soft); max-width:360px; }}
    .question-board,.source-card,.target-card,.teacher-card {{ border:1px solid rgba(123,101,77,0.12); border-radius:24px; background:rgba(255,255,255,0.78); padding:18px; }}
    .question-board p,.teacher-card p {{ margin:12px 0 0; line-height:1.8; }}
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
    .control-panel {{ display:grid; gap:16px; }}
    .control-row {{ display:flex; flex-wrap:wrap; gap:12px; }}
    .control-btn {{ border:0; border-radius:18px; min-height:48px; padding:0 18px; background:linear-gradient(135deg,var(--peach),#f3ae7a); color:#fff; font-weight:700; cursor:pointer; transition:transform .2s ease, opacity .2s ease, box-shadow .2s ease; box-shadow:0 12px 22px rgba(188,127,71,0.16); }}
    .control-btn:hover {{ transform:translateY(-1px); }}
    .control-btn--soft {{ background:rgba(255,255,255,0.84); color:var(--ink); border:1px solid rgba(123,101,77,0.12); box-shadow:none; }}
    .control-btn:disabled {{ opacity:.6; cursor:not-allowed; transform:none; box-shadow:none; }}
    .teacher-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
    .equation-box {{ margin-top:12px; min-height:54px; display:flex; align-items:center; justify-content:center; border-radius:18px; background:rgba(255,248,239,0.9); font-family:"STKaiti","KaiTi",serif; font-size:34px; }}
    .sidebar {{ display:grid; gap:18px; align-content:start; }}
    .side-card {{ padding:18px; }}
    @keyframes tokenFloat {{ 0%,100% {{ transform:translateY(0) translateZ(0); }} 50% {{ transform:translateY(-8px) translateZ(10px); }} }}
    @keyframes tokenEnter {{ from {{ opacity:0; transform:translateY(26px) scale(.84) rotateX(-28deg); }} to {{ opacity:1; transform:translateY(0) scale(1) rotateX(0deg); }} }}
    @keyframes stageFlash {{ from {{ opacity:0; transform:translateY(18px) scale(.98); }} to {{ opacity:1; transform:translateY(0) scale(1); }} }}
    .demo-stage.is-changing .demo-board {{ animation:stageFlash .42s ease; }}
    @media (max-width:960px) {{ .hero,.layout,.demo-board,.teacher-grid {{ grid-template-columns:1fr; }} .control-row {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); }} .control-btn {{ width:100%; }} }}
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
    const demoStageEl = document.getElementById('demo-stage');
    const startBtn = document.getElementById('start-btn');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const replayBtn = document.getElementById('replay-btn');
    const answerBtn = document.getElementById('answer-btn');

    titleEl.textContent = config.title;
    summaryEl.textContent = config.summary;
    questionPillEl.textContent = `题目：${config.question}`;
    focusPillEl.textContent = `控制：${(config.teacherControls || []).join(' / ')}`;
    questionCopyEl.textContent = config.question;
    teacherIntroEl.textContent = config.teacherPanel?.intro || '今天我们一起看这道题。';
    heroImageEl.src = config.images[0] || config.fallbackImages[0];
    heroImageEl.onerror = () => { heroImageEl.onerror = null; heroImageEl.src = config.fallbackImages[0]; };
    function currentScene() { return (config.scenes || [])[state.sceneIndex] || (config.scenes || [])[0] || {}; }
    function assetUrl(index) { return (config.images[index % Math.max(config.images.length, 1)] || '') || config.fallbackImages[index % config.fallbackImages.length]; }
    function stopAutoPlay() { clearInterval(state.timer); state.timer = null; state.autoPlaying = false; startBtn.textContent = '开始'; }
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
      if (config.demoType === 'average_share') renderAverageShare(scene, showAnswer); else renderGeneric(scene, showAnswer);
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
