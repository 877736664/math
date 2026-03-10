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
    keywords: tuple[str, ...]
    label: str
    english: str
    palette: tuple[str, str]


THEME_OPTIONS: tuple[ThemeOption, ...] = (
    ThemeOption(("糖", "糖果"), "糖果", "candy", ("#f7b7d7", "#ff8e6e")),
    ThemeOption(("苹果",), "苹果", "apple", ("#f9c86c", "#eb6d52")),
    ThemeOption(("铅笔", "蜡笔"), "铅笔", "pencil", ("#f4d06f", "#6c8cff")),
    ThemeOption(("书", "作业本", "故事书"), "书本", "book", ("#b7d6ff", "#7b9cde")),
    ThemeOption(("花", "盆花"), "花朵", "flower", ("#ffc2da", "#f28db2")),
    ThemeOption(("球",), "小球", "ball", ("#b8f0d2", "#57b48d")),
    ThemeOption(("鱼",), "小鱼", "fish", ("#9ed9ff", "#4d87d9")),
)


def generate_animation_game(grade: int, question: str) -> dict:
    documents = retrieve_knowledge(question, grade)
    solution = solve_question_with_docs(question, documents)
    spec = _build_game_spec(grade, question, solution)
    images = _search_images(spec["search_queries"], spec["theme"])
    html_content = _build_game_html(spec, images)

    return {
        "title": spec["title"],
        "summary": spec["summary"],
        "html": html_content,
        "search_queries": spec["search_queries"],
        "image_sources": images,
    }


def _build_game_spec(grade: int, question: str, solution: dict | None) -> dict:
    numbers = _extract_numbers(question)
    theme = _pick_theme(question)
    operation = _detect_operation(question)

    primary = numbers[0] if numbers else 8
    secondary = numbers[1] if len(numbers) > 1 else 4
    answer_label = "答案"

    if operation == "addition":
        result = primary + secondary
        title = f"{theme.label}加法动画游戏"
        summary = f"跟着动画把 {theme.label}合在一起，再判断最后一共有多少。"
        equation = f"{_format_number(primary)} + {_format_number(secondary)} = {_format_number(result)}"
        answer_label = "一共"
    elif operation == "subtraction":
        result = primary - secondary
        title = f"{theme.label}减法动画游戏"
        summary = f"先看清楚原来有多少，再用动画观察拿走以后还剩多少。"
        equation = f"{_format_number(primary)} - {_format_number(secondary)} = {_format_number(result)}"
        answer_label = "还剩"
    elif operation == "multiplication":
        result = primary * secondary
        title = f"{theme.label}乘法动画游戏"
        summary = f"把相同数量的 {theme.label}分成几组，用动画理解“几个几”。"
        equation = f"{_format_number(primary)} × {_format_number(secondary)} = {_format_number(result)}"
        answer_label = "一共"
    elif operation == "division":
        divisor = secondary if secondary else 1
        result = primary / divisor
        title = f"{theme.label}平均分动画游戏"
        summary = f"把 {theme.label}平均分开，观察每一份最后有多少。"
        equation = f"{_format_number(primary)} ÷ {_format_number(divisor)} = {_format_number(result)}"
        answer_label = "每份"
    else:
        result = solution["conclusion"] if solution else "观察动画"
        title = f"{theme.label}数字动画游戏"
        summary = "先跟着动画看数字变化，再在最后一关完成判断。"
        equation = solution["steps"][0] if solution and solution.get("steps") else "先读题，再找数字和关键词。"

    steps = solution["steps"][:4] if solution and solution.get("steps") else [
        "先把题目里的数字找出来。",
        "再根据关键词判断应该用什么方法。",
        "跟着动画看数字变化。",
        "最后选出正确答案。",
    ]

    correct_answer = _format_number(result) if isinstance(result, (int, float)) else str(result)
    quiz_options = (
        _build_quiz_options(result)
        if isinstance(result, (int, float))
        else ["看动画", "再想一想", "答案出现了"]
    )
    search_queries = _build_search_queries(question, theme, operation)

    return {
        "title": title,
        "summary": summary,
        "question": question,
        "grade": grade,
        "theme": theme,
        "operation": operation,
        "primary": primary,
        "secondary": secondary,
        "result": result,
        "equation": equation,
        "steps": steps,
        "answer_label": answer_label,
        "correct_answer": correct_answer,
        "quiz_options": quiz_options,
        "search_queries": search_queries,
    }


def _detect_operation(question: str) -> str:
    if any(word in question for word in ("平均分", "平分", "均分", "每人", "每份")):
        return "division"
    if "每" in question and any(word in question for word in ("一共", "共", "多少", "几组")):
        return "multiplication"
    if any(word in question for word in ("还剩", "剩下", "拿走", "用去", "少")):
        return "subtraction"
    if any(word in question for word in ("一共", "总共", "合起来", "共有", "又")):
        return "addition"
    return "generic"


def _pick_theme(question: str) -> ThemeOption:
    for option in THEME_OPTIONS:
        if any(keyword in question for keyword in option.keywords):
            return option

    return ThemeOption(("数字",), "数字积木", "math blocks", ("#b7d6ff", "#8fd0b2"))


def _build_search_queries(question: str, theme: ThemeOption, operation: str) -> list[str]:
    base_queries = [f"{theme.english} cartoon png", f"{theme.english} clipart transparent"]

    if operation == "division":
        base_queries.append("kids sharing classroom cartoon")
    elif operation == "multiplication":
        base_queries.append("math grouping cartoon png")
    elif operation == "addition":
        base_queries.append("school math cartoon objects")
    elif operation == "subtraction":
        base_queries.append("counting objects cartoon png")
    else:
        base_queries.append("math manipulatives cartoon png")

    if "长方形" in question or "面积" in question or "周长" in question:
        return ["geometry shapes cartoon png", "math shapes clipart transparent", "classroom geometry cartoon"]

    return base_queries


def _search_images(queries: list[str], theme: ThemeOption) -> list[dict]:
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
    url = f"https://cn.bing.com/images/search?q={quote(query)}"
    request = Request(url, headers={"User-Agent": SEARCH_USER_AGENT})

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


def _build_quiz_options(result: int | float) -> list[str]:
    correct = float(result)
    offsets = (0, 1, -1, 2)
    options: list[str] = []

    for offset in offsets:
        value = max(correct + offset, 0)
        formatted = _format_number(value)
        if formatted not in options:
            options.append(formatted)

    return options[:4]


def _extract_numbers(question: str) -> list[float]:
    return [float(token) for token in re.findall(r"\d+(?:\.\d+)?", question)]


def _format_number(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _build_svg_data_uri(label: str, color_a: str, color_b: str) -> str:
    safe_label = html.escape(label)
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="320" height="320" viewBox="0 0 320 320">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="{color_a}" />
          <stop offset="100%" stop-color="{color_b}" />
        </linearGradient>
      </defs>
      <rect width="320" height="320" rx="44" fill="url(#g)" />
      <circle cx="94" cy="100" r="42" fill="rgba(255,255,255,0.34)" />
      <circle cx="230" cy="84" r="24" fill="rgba(255,255,255,0.22)" />
      <circle cx="228" cy="220" r="58" fill="rgba(255,255,255,0.18)" />
      <text x="160" y="148" text-anchor="middle" font-size="38" font-family="Arial, sans-serif" fill="#ffffff">
        {safe_label}
      </text>
      <text x="160" y="198" text-anchor="middle" font-size="66" font-family="Arial, sans-serif" fill="#ffffff">
        123
      </text>
    </svg>
    """.strip()
    return "data:image/svg+xml;charset=UTF-8," + quote(svg)


def _build_game_html(spec: dict, images: list[dict]) -> str:
    palette_a, palette_b = spec["theme"].palette
    image_urls = [item["image_url"] for item in images]
    fallback_images = [
        _build_svg_data_uri(spec["theme"].label, palette_a, palette_b),
        _build_svg_data_uri(spec["theme"].label, palette_b, palette_a),
    ]
    source_items = [
        {
            "host": item["source_host"],
            "page": item["source_page"],
        }
        for item in images
    ]

    config = {
        "title": spec["title"],
        "summary": spec["summary"],
        "question": spec["question"],
        "operation": spec["operation"],
        "equation": spec["equation"],
        "steps": spec["steps"],
        "answerLabel": spec["answer_label"],
        "primary": int(round(spec["primary"])) if isinstance(spec["primary"], (int, float)) else 8,
        "secondary": int(round(spec["secondary"])) if isinstance(spec["secondary"], (int, float)) else 4,
        "result": spec["correct_answer"],
        "quizOptions": spec["quiz_options"],
        "images": image_urls,
        "fallbackImages": fallback_images,
        "sources": source_items,
        "maxDisplayTokens": MAX_DISPLAY_TOKENS,
    }

    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\" />"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />"
        f"<title>{html.escape(spec['title'])}</title><style>{_game_css(palette_a, palette_b)}</style></head>"
        "<body><div class=\"shell\">"
        "<section class=\"hero\">"
        "<span class=\"eyebrow\">数字动画游戏</span>"
        "<h1 id=\"title\"></h1>"
        "<p class=\"summary\" id=\"summary\"></p>"
        "<div class=\"hero-meta\">"
        "<span class=\"hero-pill\" id=\"question-pill\"></span>"
        "<span class=\"hero-pill\" id=\"equation-pill\"></span>"
        "</div></section>"
        "<div class=\"layout\">"
        "<section class=\"stage\">"
        "<div class=\"spark\" style=\"left:10%;bottom:18%;animation-delay:0s;\"></div>"
        "<div class=\"spark\" style=\"left:72%;bottom:14%;animation-delay:1.4s;\"></div>"
        "<div class=\"spark\" style=\"left:58%;bottom:24%;animation-delay:3.2s;\"></div>"
        "<div class=\"progress\"><div class=\"progress-bar\"><div class=\"progress-fill\" id=\"progress-fill\"></div></div>"
        "<div class=\"helper-text\" id=\"progress-text\"></div></div>"
        "<h2 class=\"scene-title\" id=\"scene-title\"></h2>"
        "<p class=\"scene-copy\" id=\"scene-copy\"></p>"
        "<div class=\"scene-surface\" id=\"scene-surface\"></div>"
        "<div class=\"controls\"><div class=\"control-group\">"
        "<button class=\"nav-btn secondary\" id=\"prev-btn\" type=\"button\">上一步</button>"
        "<button class=\"nav-btn\" id=\"next-btn\" type=\"button\">下一步</button>"
        "</div><span class=\"helper-text\">点击按钮，按动画流程一步一步看懂这道题。</span></div>"
        "</section>"
        "<aside class=\"sidebar\">"
        "<section class=\"side-card\"><span class=\"eyebrow\">解题提醒</span><ol class=\"steps\" id=\"step-list\"></ol></section>"
        "<section class=\"side-card\"><span class=\"eyebrow\">图片来源</span><ul class=\"source-list\" id=\"source-list\"></ul></section>"
        "</aside></div></div>"
        f"<script>const config = {json.dumps(config, ensure_ascii=False)};{_game_script()}</script>"
        "</body></html>"
    )


def _game_css(color_a: str, color_b: str) -> str:
    return f"""
    :root {{
      --peach: {color_a};
      --mint: {color_b};
      --ink: #2a241d;
      --soft: #6d6054;
      --panel: rgba(255, 250, 244, 0.92);
      --line: rgba(110, 87, 61, 0.14);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.48), transparent 28%),
        linear-gradient(160deg, rgba(255,245,235,0.98), rgba(239,247,242,0.98));
    }}
    .shell {{ max-width: 1100px; margin: 0 auto; padding: 24px 18px 40px; }}
    .hero, .stage, .side-card {{
      border: 1px solid var(--line);
      border-radius: 28px;
      background: var(--panel);
      box-shadow: 0 18px 38px rgba(85, 65, 44, 0.08);
    }}
    .hero {{ padding: 24px; }}
    .stage {{ padding: 22px; min-height: 640px; position: relative; overflow: hidden; }}
    .side-card {{ padding: 18px; }}
    .eyebrow, .hero-pill, .count-chip, .lane-note, .helper-text {{
      color: var(--soft);
      font-size: 13px;
    }}
    .eyebrow {{
      display: inline-flex; padding: 5px 10px; border-radius: 999px;
      background: rgba(255,255,255,0.7); font-size: 12px; font-weight: 700;
      letter-spacing: 0.08em; text-transform: uppercase;
    }}
    h1 {{ margin: 14px 0 0; font-size: clamp(30px, 4vw, 46px); line-height: 1.12; }}
    .summary {{ margin: 16px 0 0; max-width: 760px; line-height: 1.8; font-size: 16px; }}
    .hero-meta, .controls, .lane-head, .preview {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .hero-meta {{ margin-top: 18px; }}
    .hero-pill, .count-chip {{
      display: inline-flex; align-items: center; justify-content: center;
      min-height: 34px; padding: 0 12px; border-radius: 999px; background: rgba(255,255,255,0.78); font-weight: 700;
    }}
    .layout {{ margin-top: 20px; display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 18px; }}
    .sidebar, .progress, .math-lanes, .formula-card, .bucket-card, .question-card, .result-card {{ display: grid; gap: 18px; }}
    .progress-bar {{ height: 10px; border-radius: 999px; background: rgba(125, 105, 78, 0.12); overflow: hidden; }}
    .progress-fill {{ height: 100%; width: 25%; border-radius: 999px; background: linear-gradient(90deg, var(--peach), var(--mint)); transition: width 0.35s ease; }}
    .scene-title {{ margin: 18px 0 0; font-size: 28px; font-family: "STKaiti", "KaiTi", serif; }}
    .scene-copy, .steps, .source-list {{ margin: 10px 0 0; line-height: 1.8; }}
    .scene-surface {{ margin-top: 22px; min-height: 420px; display: grid; gap: 18px; align-content: start; }}
    .hero-strip {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }}
    .hero-image-card, .formula-card, .bucket-card, .question-card, .result-card, .math-lane {{
      border: 1px solid rgba(110, 87, 61, 0.12); border-radius: 22px; background: rgba(255,255,255,0.72); padding: 16px;
    }}
    .hero-image {{ width: 100%; aspect-ratio: 1 / 1; object-fit: cover; border-radius: 18px; background: linear-gradient(160deg, rgba(255,255,255,0.84), rgba(235,238,236,0.84)); }}
    .image-caption {{ margin-top: 10px; color: var(--soft); font-size: 13px; line-height: 1.6; }}
    .token-grid {{ display: flex; flex-wrap: wrap; gap: 12px; }}
    .token {{ width: 72px; display: grid; gap: 8px; justify-items: center; animation: tokenFloat 3.6s ease-in-out infinite; animation-delay: calc(var(--delay) * 0.08s); }}
    .token-image {{ width: 72px; height: 72px; object-fit: cover; border-radius: 18px; background: rgba(255,255,255,0.8); box-shadow: 0 12px 22px rgba(91, 70, 48, 0.1); }}
    .token-label {{ font-size: 12px; color: var(--soft); text-align: center; }}
    .lane-head {{ align-items: center; justify-content: space-between; }}
    .lane-head strong, .bucket-card h3 {{ font-size: 16px; margin: 0; }}
    .division-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; }}
    .equation {{ font-size: clamp(28px, 4vw, 42px); font-family: "STKaiti", "KaiTi", serif; }}
    .steps {{ padding-left: 18px; display: grid; gap: 10px; }}
    .source-list {{ padding-left: 18px; display: grid; gap: 8px; }}
    .source-list a {{ color: var(--soft); }}
    .quiz-options {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .quiz-btn, .nav-btn {{
      border: 0; border-radius: 18px; min-height: 48px; padding: 0 16px;
      background: linear-gradient(135deg, var(--peach), #f3ae7a); color: #fff; font-weight: 700;
      cursor: pointer; transition: transform 0.2s ease, opacity 0.2s ease;
    }}
    .quiz-btn.secondary, .nav-btn.secondary {{ background: rgba(255,255,255,0.76); color: var(--ink); border: 1px solid rgba(110, 87, 61, 0.12); }}
    .quiz-btn.correct {{ background: linear-gradient(135deg, #8fd0b2, #56b38a); }}
    .quiz-btn.wrong {{ background: linear-gradient(135deg, #f4a09a, #d86666); }}
    .quiz-btn:hover, .nav-btn:hover {{ transform: translateY(-1px); }}
    .result-value {{ font-size: 42px; font-family: "STKaiti", "KaiTi", serif; }}
    .controls {{ margin-top: 22px; justify-content: space-between; align-items: center; }}
    .control-group {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .spark {{ position: absolute; width: 16px; height: 16px; border-radius: 50%; background: rgba(255,255,255,0.52); animation: sparkFloat 7s linear infinite; pointer-events: none; }}
    @keyframes tokenFloat {{ 0%, 100% {{ transform: translateY(0) rotate(0deg); }} 50% {{ transform: translateY(-10px) rotate(2deg); }} }}
    @keyframes sparkFloat {{ from {{ transform: translateY(0) translateX(0) scale(0.9); opacity: 0; }} 15% {{ opacity: 1; }} to {{ transform: translateY(-260px) translateX(34px) scale(1.2); opacity: 0; }} }}
    @media (max-width: 880px) {{
      .layout, .hero-strip {{ grid-template-columns: 1fr; }}
      .quiz-options {{ grid-template-columns: 1fr; }}
      .controls {{ flex-direction: column; align-items: stretch; }}
      .control-group {{ width: 100%; }}
      .nav-btn {{ width: 100%; }}
    }}
    """


def _game_script() -> str:
    return """
    const state = { sceneIndex: 0, answered: false, answerState: '' };
    const scenes = [
      { title: '出发：先看题目场景', copy: '先用图片把题目里的主角和数量感受一遍，再进入正式解题。', render: renderIntroScene },
      { title: '找数字：把数量看见', copy: '动画里会先把关键数量排出来，帮助学生看见数字变化。', render: renderCountScene },
      { title: '看方法：跟着动画算一遍', copy: '根据题型不同，动画会演示合并、拿走、分组或平均分。', render: renderOperationScene },
      { title: '最后一关：点出正确答案', copy: '看完动画以后，试着自己选出正确答案。', render: renderQuizScene },
    ];
    const titleEl = document.getElementById('title');
    const summaryEl = document.getElementById('summary');
    const questionPillEl = document.getElementById('question-pill');
    const equationPillEl = document.getElementById('equation-pill');
    const progressFillEl = document.getElementById('progress-fill');
    const progressTextEl = document.getElementById('progress-text');
    const sceneTitleEl = document.getElementById('scene-title');
    const sceneCopyEl = document.getElementById('scene-copy');
    const sceneSurfaceEl = document.getElementById('scene-surface');
    const stepListEl = document.getElementById('step-list');
    const sourceListEl = document.getElementById('source-list');
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    titleEl.textContent = config.title;
    summaryEl.textContent = config.summary;
    questionPillEl.textContent = `题目：${config.question}`;
    equationPillEl.textContent = `算式线索：${config.equation}`;
    config.steps.forEach((step) => { const li = document.createElement('li'); li.textContent = step; stepListEl.appendChild(li); });
    (config.sources || []).forEach((source) => {
      const li = document.createElement('li');
      if (source.page) { const link = document.createElement('a'); link.href = source.page; link.target = '_blank'; link.rel = 'noreferrer'; link.textContent = source.host || '图片来源'; li.appendChild(link); }
      else { li.textContent = source.host || '内置 SVG'; }
      sourceListEl.appendChild(li);
    });
    if (!config.sources || !config.sources.length) { const li = document.createElement('li'); li.textContent = '本页使用了内置 SVG 素材。'; sourceListEl.appendChild(li); }
    function assetUrl(index) { return (config.images[index % Math.max(config.images.length, 1)] || '') || config.fallbackImages[index % config.fallbackImages.length]; }
    function createToken(index, label) {
      const token = document.createElement('div'); token.className = 'token'; token.style.setProperty('--delay', String(index));
      const image = document.createElement('img'); image.className = 'token-image'; image.src = assetUrl(index); image.alt = label;
      image.onerror = () => { image.onerror = null; image.src = config.fallbackImages[index % config.fallbackImages.length]; };
      const caption = document.createElement('span'); caption.className = 'token-label'; caption.textContent = label;
      token.appendChild(image); token.appendChild(caption); return token;
    }
    function createTokenGrid(count, label, note) {
      const wrapper = document.createElement('div'); wrapper.className = 'math-lane';
      const head = document.createElement('div'); head.className = 'lane-head';
      const strong = document.createElement('strong'); strong.textContent = label;
      const chip = document.createElement('span'); chip.className = 'count-chip'; chip.textContent = `×${count}`;
      head.appendChild(strong); head.appendChild(chip); wrapper.appendChild(head);
      if (note) { const helper = document.createElement('div'); helper.className = 'lane-note'; helper.textContent = note; wrapper.appendChild(helper); }
      const grid = document.createElement('div'); grid.className = 'token-grid';
      const displayCount = Math.min(Math.max(Number(count) || 0, 1), config.maxDisplayTokens || 18);
      for (let index = 0; index < displayCount; index += 1) { grid.appendChild(createToken(index, label)); }
      if (Number(count) > displayCount) { const more = document.createElement('span'); more.className = 'count-chip'; more.textContent = `还有 ${Number(count) - displayCount} 个`; grid.appendChild(more); }
      wrapper.appendChild(grid); return wrapper;
    }
    function renderIntroScene() {
      const container = document.createElement('div'); container.className = 'hero-strip';
      for (let index = 0; index < 2; index += 1) {
        const card = document.createElement('div'); card.className = 'hero-image-card';
        const image = document.createElement('img'); image.className = 'hero-image'; image.src = assetUrl(index); image.alt = config.title;
        image.onerror = () => { image.onerror = null; image.src = config.fallbackImages[index % config.fallbackImages.length]; };
        const caption = document.createElement('p'); caption.className = 'image-caption';
        caption.textContent = index === 0 ? `先看场景：${config.question}` : `这道题的核心数量变化是：${config.equation}`;
        card.appendChild(image); card.appendChild(caption); container.appendChild(card);
      }
      return container;
    }
    function renderCountScene() {
      const container = document.createElement('div'); container.className = 'math-lanes';
      container.appendChild(createTokenGrid(config.primary, `关键数量 ${config.primary}`, '第一步先把题目里的第一个数字看清楚。'));
      if (config.secondary) { container.appendChild(createTokenGrid(config.secondary, `第二个数量 ${config.secondary}`, '第二步把另一个关键数字也圈出来。')); }
      return container;
    }
    function renderOperationScene() {
      const container = document.createElement('div'); container.className = 'math-lanes';
      const formulaCard = document.createElement('div'); formulaCard.className = 'formula-card';
      formulaCard.innerHTML = `<span class="eyebrow">动画演示</span><div class="equation">${config.equation}</div>`; container.appendChild(formulaCard);
      if (config.operation === 'division') {
        const grid = document.createElement('div'); grid.className = 'division-grid';
        const parts = Math.max(config.secondary, 1);
        for (let index = 0; index < parts; index += 1) {
          const bucket = document.createElement('div'); bucket.className = 'bucket-card';
          const title = document.createElement('h3'); title.textContent = `第 ${index + 1} 份`; bucket.appendChild(title);
          bucket.appendChild(createTokenGrid(config.result, config.answerLabel, '平均分以后，每一份都一样多。')); grid.appendChild(bucket);
        }
        container.appendChild(grid);
      } else if (config.operation === 'multiplication') {
        for (let index = 0; index < Math.max(config.secondary, 1); index += 1) { container.appendChild(createTokenGrid(config.primary, `第 ${index + 1} 组`, '先看每一组有多少，再看一共有几组。')); }
      } else if (config.operation === 'subtraction') {
        container.appendChild(createTokenGrid(config.primary, '原来的数量', '先把原来有多少排出来。'));
        container.appendChild(createTokenGrid(config.secondary, '拿走的数量', '这些会在题目情境里被拿走或用掉。'));
        container.appendChild(createTokenGrid(config.result, config.answerLabel, '剩下的就是最后要回答的数量。'));
      } else {
        container.appendChild(createTokenGrid(config.primary, '第一部分', '先观察第一部分的数量。'));
        container.appendChild(createTokenGrid(config.secondary, config.operation === 'addition' ? '第二部分' : config.answerLabel, '再看另一部分如何变化。'));
        if (config.operation !== 'generic') { container.appendChild(createTokenGrid(config.result, config.answerLabel, '最后得到动画演示后的结果。')); }
      }
      return container;
    }
    function renderQuizScene() {
      const wrapper = document.createElement('div'); wrapper.className = 'question-card';
      const prompt = document.createElement('p'); prompt.className = 'scene-copy'; prompt.textContent = `问题：${config.answerLabel}是多少？`; wrapper.appendChild(prompt);
      const options = document.createElement('div'); options.className = 'quiz-options';
      config.quizOptions.forEach((option) => {
        const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'quiz-btn secondary'; btn.textContent = option;
        if (state.answered) { btn.className = `quiz-btn ${option === config.result ? 'correct' : option === state.answerState ? 'wrong' : 'secondary'}`; }
        btn.addEventListener('click', () => { state.answered = true; state.answerState = option === config.result ? 'correct' : option; renderScene(); });
        options.appendChild(btn);
      });
      wrapper.appendChild(options);
      const resultCard = document.createElement('div'); resultCard.className = 'result-card';
      const status = document.createElement('span'); status.className = 'eyebrow';
      status.textContent = state.answered ? (state.answerState === 'correct' ? '答对了' : '再试试看') : '准备答题'; resultCard.appendChild(status);
      const resultValue = document.createElement('div'); resultValue.className = 'result-value'; resultValue.textContent = state.answered ? config.result : '？'; resultCard.appendChild(resultValue);
      const tip = document.createElement('p'); tip.className = 'scene-copy';
      tip.textContent = state.answered ? (state.answerState === 'correct' ? `恭喜你，${config.answerLabel}是 ${config.result}。` : `正确答案其实是 ${config.result}，再回到上一幕看看动画。`) : '先根据前面的动画观察，再点选一个答案。';
      resultCard.appendChild(tip); wrapper.appendChild(resultCard); return wrapper;
    }
    function renderScene() {
      const scene = scenes[state.sceneIndex];
      const progress = ((state.sceneIndex + 1) / scenes.length) * 100;
      progressFillEl.style.width = `${progress}%`; progressTextEl.textContent = `第 ${state.sceneIndex + 1} 步 / 共 ${scenes.length} 步`;
      sceneTitleEl.textContent = scene.title; sceneCopyEl.textContent = scene.copy; sceneSurfaceEl.innerHTML = ''; sceneSurfaceEl.appendChild(scene.render());
      prevBtn.disabled = state.sceneIndex === 0; nextBtn.disabled = state.sceneIndex === scenes.length - 1;
      nextBtn.textContent = state.sceneIndex === scenes.length - 1 ? '已经到最后一幕' : '下一步';
    }
    prevBtn.addEventListener('click', () => { state.sceneIndex = Math.max(state.sceneIndex - 1, 0); renderScene(); });
    nextBtn.addEventListener('click', () => { state.sceneIndex = Math.min(state.sceneIndex + 1, scenes.length - 1); renderScene(); });
    renderScene();
    """
