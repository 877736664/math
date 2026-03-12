import json
import logging
import os
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.rag_service import (
    build_rag_fallback_answer,
    build_rag_fallback_assets,
    render_retrieved_context,
    retrieve_knowledge,
)


GAME_CATALOG = [
    {
        "keywords": ["加法", "减法", "口算", "算术", "乘法", "除法"],
        "title": "算术训练游戏",
        "url": "https://www.abcya.com/games/math_facts",
    },
    {
        "keywords": ["分数", "小数", "百分数"],
        "title": "分数与小数互动练习",
        "url": "https://www.mathplayground.com/ASB_PenguinJumpMultiplication.html",
    },
    {
        "keywords": ["几何", "图形", "面积", "周长", "角"],
        "title": "几何图形互动游戏",
        "url": "https://www.geogebra.org/m/zf9f7k7h",
    },
]

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _create_llm(
    *,
    timeout: int,
    max_tokens: int,
    enable_thinking: bool,
    response_format: dict | None = None,
):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    model_kwargs = {}
    if response_format is not None:
        model_kwargs["response_format"] = response_format

    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.2,
        timeout=timeout,
        max_tokens=max_tokens,
        max_retries=0,
        extra_body={"enable_thinking": enable_thinking},
        model_kwargs=model_kwargs,
    )


@lru_cache(maxsize=1)
def _build_qa_chain():
    llm = _create_llm(
        timeout=int(os.getenv("OPENAI_QA_TIMEOUT", "30")),
        max_tokens=int(os.getenv("OPENAI_QA_MAX_TOKENS", "600")),
        enable_thinking=_env_flag("OPENAI_QA_ENABLE_THINKING", False),
    )
    if llm is None:
        return None

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "你是小学数学AI助教。你必须先阅读检索到的知识库内容，再回答学生问题。"
                    "回答要求："
                    "1) 只使用简体中文；"
                    "2) 难度匹配{grade}年级；"
                    "3) 优先依据“检索知识”组织答案，不要脱离检索内容随意发挥；"
                    "4) 先给结论，再分步骤讲解；"
                    "5) 最后给1道同类型练习题，不带答案；"
                    "6) 使用 Markdown 输出，至少包含“## 结论”“## 解题步骤”“## 同类练习”三个部分。"
                ),
            ),
            (
                "human",
                "检索知识：\n{context}\n\n学生问题：{question}",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


@lru_cache(maxsize=1)
def _build_assets_chain():
    llm = _create_llm(
        timeout=int(os.getenv("OPENAI_ASSETS_TIMEOUT", "35")),
        max_tokens=int(os.getenv("OPENAI_ASSETS_MAX_TOKENS", "1200")),
        enable_thinking=_env_flag("OPENAI_ASSETS_ENABLE_THINKING", False),
        response_format={"type": "json_object"},
    )
    if llm is None:
        return None

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "你是小学数学课程设计助手。"
                    "请先阅读检索到的知识库内容，再输出严格的 JSON，不要输出 markdown 代码块。"
                    "JSON 结构如下："
                    "{{"
                    "\"answer\":\"...\","
                    "\"video_title\":\"...\","
                    "\"video_script_steps\":[\"...\",\"...\"],"
                    "\"ppt_title\":\"...\","
                    "\"ppt_slides\":["
                    "{{\"title\":\"...\",\"bullet_points\":[\"...\",\"...\"]}}"
                    "],"
                    "\"game_title\":\"...\","
                    "\"game_reason\":\"...\""
                    "}}"
                    "要求："
                    "1) 内容必须基于检索知识；"
                    "2) 面向小学{grade}年级；"
                    "3) video_script_steps 返回4-6条；"
                    "4) ppt_slides 返回5-8页；"
                    "5) 每页 bullet_points 返回2-4条短句；"
                    "6) answer 字段使用 Markdown，至少包含“## 结论”“## 解题步骤”“## 同类练习”三个部分。"
                ),
            ),
            (
                "human",
                "检索知识：\n{context}\n\n问题：{question}",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


def _pick_game(question: str):
    for item in GAME_CATALOG:
        if any(keyword in question for keyword in item["keywords"]):
            return {
                "title": item["title"],
                "url": item["url"],
                "reason": "根据题目关键词匹配到最相关的互动练习。",
            }

    default_game = GAME_CATALOG[0]
    return {
        "title": default_game["title"],
        "url": default_game["url"],
        "reason": "未命中特定题型，默认推荐通用算术练习。",
    }


def generate_answer(grade: int, question: str) -> str:
    documents = retrieve_knowledge(question, grade)
    context = render_retrieved_context(documents)
    chain = _build_qa_chain()

    if chain is None:
        return build_rag_fallback_answer(grade, question, documents)

    try:
        return chain.invoke({"grade": grade, "question": question, "context": context})
    except Exception:
        logger.exception("LLM answer generation failed, falling back to RAG template.")
        return build_rag_fallback_answer(grade, question, documents)


def generate_lesson_assets(grade: int, question: str):
    documents = retrieve_knowledge(question, grade)
    context = render_retrieved_context(documents)
    game = _pick_game(question)
    fallback_assets = build_rag_fallback_assets(grade, question, documents, game)
    chain = _build_assets_chain()

    if chain is None:
        return fallback_assets

    try:
        raw = chain.invoke({"grade": grade, "question": question, "context": context}).strip()
    except Exception:
        logger.exception("LLM asset generation failed, falling back to RAG template.")
        return fallback_assets

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return fallback_assets

    slides = data.get("ppt_slides", [])
    if not isinstance(slides, list):
        slides = []

    normalized_slides = []
    for slide in slides[:8]:
        title = str(slide.get("title", "未命名页面")).strip() if isinstance(slide, dict) else "未命名页面"
        points = slide.get("bullet_points", []) if isinstance(slide, dict) else []
        if not isinstance(points, list):
            points = []
        normalized_slides.append(
            {"title": title or "未命名页面", "bullet_points": [str(point) for point in points[:4]]}
        )

    if isinstance(data.get("game_title"), str) and data["game_title"].strip():
        game["title"] = data["game_title"].strip()
    if isinstance(data.get("game_reason"), str) and data["game_reason"].strip():
        game["reason"] = data["game_reason"].strip()

    return {
        "answer": str(data.get("answer", fallback_assets["answer"])),
        "video": {
            "title": str(data.get("video_title", fallback_assets["video"]["title"])).strip()
            or fallback_assets["video"]["title"],
            "script_steps": [str(step) for step in data.get("video_script_steps", [])[:6]]
            or fallback_assets["video"]["script_steps"],
        },
        "ppt": {
            "title": str(data.get("ppt_title", fallback_assets["ppt"]["title"])).strip()
            or fallback_assets["ppt"]["title"],
            "slides": normalized_slides or fallback_assets["ppt"]["slides"],
        },
        "game": game,
    }


def generate_video_script(grade: int, question: str) -> dict:
    data = generate_lesson_assets(grade, question)
    return data["video"]


def generate_ppt_outline(grade: int, question: str) -> dict:
    data = generate_lesson_assets(grade, question)
    return data["ppt"]
