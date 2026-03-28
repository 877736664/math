"""LLM 调用封装，负责问答与教学素材生成。"""

import json
import logging
import os
from functools import lru_cache

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from app.services.rag_service import (
    build_rag_fallback_answer,
    build_rag_fallback_assets,
    render_retrieved_context,
    retrieve_knowledge,
)
from app.repositories.textbook_repository import resolve_textbook_scope, serialize_knowledge_points, serialize_textbook_scope
from app.services.teaching_quality_service import answer_has_required_sections, build_teaching_quality_context


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


def system_message(content: str) -> dict:
    """为轻量级直接调用封装 system 消息。"""

    return {"role": "system", "content": str(content or "").strip()}


def user_message(content: str) -> dict:
    """为轻量级直接调用封装 user 消息。"""

    return {"role": "user", "content": str(content or "").strip()}


def complete_with_llm(messages: list[dict], temperature: float = 0.2, max_tokens: int = 3200) -> str:
    """直接调用兼容 OpenAI 的聊天模型并返回纯文本结果。"""

    llm = _create_llm(
        timeout=int(os.getenv("OPENAI_DIRECT_TIMEOUT", "90")),
        max_tokens=max_tokens,
        enable_thinking=_env_flag("OPENAI_DIRECT_ENABLE_THINKING", False),
    )
    if llm is None:
        raise RuntimeError("LLM is not configured")

    direct_messages: list[BaseMessage] = []
    for item in messages:
        role = item.get("role") if isinstance(item, dict) else None
        content = str(item.get("content", "")).strip() if isinstance(item, dict) else ""
        if not content:
            continue
        if role == "system":
            direct_messages.append(HumanMessage(content=f"[SYSTEM]\n{content}"))
        elif role == "assistant":
            direct_messages.append(AIMessage(content=content))
        else:
            direct_messages.append(HumanMessage(content=content))

    if not direct_messages:
        return ""

    bound_llm = llm.bind(temperature=temperature)
    response = bound_llm.invoke(direct_messages)
    content = response.content if hasattr(response, "content") else response
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content).strip()
    return str(content or "").strip()


def build_history_messages(messages: list[dict] | None, latest_question: str) -> list[BaseMessage]:
    """把前端传来的对话历史整理成 LangChain 消息列表。"""

    if not messages:
        return []

    normalized_messages: list[dict] = []
    for item in messages[-12:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized_messages.append({"role": role, "content": content})

    if normalized_messages and normalized_messages[-1]["role"] == "user":
        trailing_question = normalized_messages[-1]["content"]
        if trailing_question == latest_question.strip():
            normalized_messages = normalized_messages[:-1]

    history: list[BaseMessage] = []
    for item in normalized_messages:
        if item["role"] == "assistant":
            history.append(AIMessage(content=item["content"]))
        else:
            history.append(HumanMessage(content=item["content"]))

    return history


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
    """根据环境变量创建 OpenAI 兼容的聊天模型实例。"""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    model_kwargs = {}
    if response_format is not None:
        model_kwargs["response_format"] = response_format

    llm_kwargs = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "temperature": 0.2,
        "timeout": timeout,
        "max_tokens": max_tokens,
        "max_retries": 0,
        "extra_body": {"enable_thinking": enable_thinking},
        "model_kwargs": model_kwargs,
    }

    return ChatOpenAI(**llm_kwargs)


@lru_cache(maxsize=1)
def _build_qa_chain():
    """构建问答链，要求模型严格围绕检索知识作答。"""

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
                    "如果提供了历史对话，要继承前文语境，但本次回答必须优先解决最后一个老师问题。"
                    "回答要求："
                    "1) 只使用简体中文；"
                    "2) 难度匹配{grade}年级；"
                    "3) 优先依据“检索知识”组织答案，不要脱离检索内容随意发挥；"
                    "4) 必须围绕教学目标组织讲解，并照顾学生基础；"
                    "5) 保持老师讲题口吻，先讲为什么，再讲怎么算；"
                    "6) 必须指出一个最容易出错的地方，并给出课堂追问；"
                    "7) 最后给1道同类型练习题，不带答案；"
                    "8) 使用 Markdown 输出，至少包含“## 结论”“## 为什么这样做”“## 分步讲解”“## 常见错误”“## 课堂提问”“## 同类练习”六个部分。"
                ),
            ),
            MessagesPlaceholder("history"),
            (
                "human",
                "教材范围：{textbook_label}\n"
                "教学目标：{teaching_goal}\n"
                "学生情况：{student_profile}\n"
                "讲解风格：{teaching_style_instruction}\n"
                "详略要求：{depth_instruction}\n"
                "易错点提醒：{misconception_focus}\n"
                "课堂追问建议：{teacher_prompt}\n\n"
                "检索知识：\n{context}\n\n老师当前问题：{question}",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


@lru_cache(maxsize=1)
def _build_assets_chain():
    """构建素材链，用于生成结构化的 JSON 教学素材。"""

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
                    "如果提供了历史对话，要结合上下文理解当前老师需求，但输出必须围绕最后一个老师问题。"
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
                    "3) answer 必须体现教学目标、常见误区和课堂提问；"
                    "4) video_script_steps 返回4-6条；"
                    "5) ppt_slides 返回5-8页，其中至少1页体现常见错误或提醒；"
                    "6) 每页 bullet_points 返回2-4条短句；"
                    "7) answer 字段使用 Markdown，至少包含“## 结论”“## 为什么这样做”“## 分步讲解”“## 常见错误”“## 课堂提问”“## 同类练习”六个部分。"
                ),
            ),
            MessagesPlaceholder("history"),
            (
                "human",
                "教材范围：{textbook_label}\n"
                "教学目标：{teaching_goal}\n"
                "学生情况：{student_profile}\n"
                "讲解风格：{teaching_style_instruction}\n"
                "详略要求：{depth_instruction}\n"
                "易错点提醒：{misconception_focus}\n"
                "课堂追问建议：{teacher_prompt}\n\n"
                "检索知识：\n{context}\n\n老师当前需求：{question}",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


def _pick_game(question: str):
    """根据题目关键词挑选最相关的外部互动练习。"""

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


def generate_answer(grade: int, question: str, textbook: dict | None = None, teaching_preferences: dict | None = None) -> dict:
    """生成问答接口需要的答案、教材范围和知识点列表。"""

    scope = resolve_textbook_scope(grade, textbook)
    documents = retrieve_knowledge(question, grade, textbook=textbook)
    context = render_retrieved_context(documents)
    teaching_context = build_teaching_quality_context(grade, question, documents, teaching_preferences)
    chain = _build_qa_chain()

    if chain is None:
        return {
            "answer": build_rag_fallback_answer(grade, question, documents, teaching_context),
            "textbook": serialize_textbook_scope(scope),
            "knowledge_points": serialize_knowledge_points(documents),
        }

    try:
        fallback_answer = build_rag_fallback_answer(grade, question, documents, teaching_context)
        answer = chain.invoke({
            "grade": grade,
            "question": question,
            "context": context,
            "textbook_label": scope.label,
            "teaching_goal": teaching_context["teaching_goal"],
            "student_profile": teaching_context["student_profile"],
            "teaching_style_instruction": teaching_context["teaching_style_instruction"],
            "depth_instruction": teaching_context["depth_instruction"],
            "misconception_focus": teaching_context["misconception_focus"],
            "teacher_prompt": teaching_context["teacher_prompt"],
        })
        if not answer_has_required_sections(answer):
            answer = fallback_answer
    except Exception:
        logger.exception("LLM answer generation failed, falling back to RAG template.")
        answer = build_rag_fallback_answer(grade, question, documents, teaching_context)

    return {
        "answer": answer,
        "textbook": serialize_textbook_scope(scope),
        "knowledge_points": serialize_knowledge_points(documents),
    }


def generate_lesson_assets(
    grade: int,
    question: str,
    textbook: dict | None = None,
    teaching_preferences: dict | None = None,
) -> dict:
    """生成课程素材接口需要的完整结果。"""

    scope = resolve_textbook_scope(grade, textbook)
    documents = retrieve_knowledge(question, grade, textbook=textbook)
    context = render_retrieved_context(documents)
    game = _pick_game(question)
    teaching_context = build_teaching_quality_context(grade, question, documents, teaching_preferences)
    fallback_assets = build_rag_fallback_assets(grade, question, documents, game, teaching_context)
    chain = _build_assets_chain()

    if chain is None:
        return {
            **fallback_assets,
            "textbook": serialize_textbook_scope(scope),
            "knowledge_points": serialize_knowledge_points(documents),
        }

    try:
        fallback_answer = fallback_assets["answer"]
        raw = chain.invoke({
            "grade": grade,
            "question": question,
            "context": context,
            "textbook_label": scope.label,
            "teaching_goal": teaching_context["teaching_goal"],
            "student_profile": teaching_context["student_profile"],
            "teaching_style_instruction": teaching_context["teaching_style_instruction"],
            "depth_instruction": teaching_context["depth_instruction"],
            "misconception_focus": teaching_context["misconception_focus"],
            "teacher_prompt": teaching_context["teacher_prompt"],
        }).strip()
    except Exception:
        logger.exception("LLM asset generation failed, falling back to RAG template.")
        return {
            **fallback_assets,
            "textbook": serialize_textbook_scope(scope),
            "knowledge_points": serialize_knowledge_points(documents),
        }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            **fallback_assets,
            "textbook": serialize_textbook_scope(scope),
            "knowledge_points": serialize_knowledge_points(documents),
        }

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
        "answer": str(data.get("answer", fallback_answer)) if answer_has_required_sections(str(data.get("answer", ""))) else fallback_answer,
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
        "textbook": serialize_textbook_scope(scope),
        "knowledge_points": serialize_knowledge_points(documents),
    }


def generate_video_script(
    grade: int,
    question: str,
    textbook: dict | None = None,
    teaching_preferences: dict | None = None,
) -> dict:
    """从课程素材结果中抽取视频脚本部分。"""

    data = generate_lesson_assets(grade, question, textbook=textbook, teaching_preferences=teaching_preferences)
    return data["video"]


def generate_ppt_outline(
    grade: int,
    question: str,
    textbook: dict | None = None,
    teaching_preferences: dict | None = None,
) -> dict:
    """从课程素材结果中抽取 PPT 提纲部分。"""

    data = generate_lesson_assets(grade, question, textbook=textbook, teaching_preferences=teaching_preferences)
    return data["ppt"]
