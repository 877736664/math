"""基于 LangGraph 的教学工作流编排层。"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Literal, TypedDict, cast

from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.services.llm_service import _build_assets_chain, _build_qa_chain, _pick_game, build_history_messages, logger
from app.services.rag_service import (
    build_rag_fallback_answer,
    build_rag_fallback_assets,
    render_retrieved_context,
    retrieve_knowledge,
)
from app.repositories.textbook_repository import (
    KnowledgeDocument,
    TextbookScope,
    resolve_textbook_scope,
    serialize_knowledge_points,
    serialize_textbook_scope,
)
from app.services.teaching_quality_service import build_teaching_quality_context
from app.services.teaching_quality_service import answer_has_required_sections
from app.services.online_search_service import render_online_search_context, search_online_documents


WorkflowMode = Literal["answer", "assets"]


class TeachingWorkflowState(TypedDict, total=False):
    """工作流在节点之间传递的共享状态。"""

    mode: WorkflowMode
    grade: int
    question: str
    retrieval_question: str
    messages: list[dict]
    textbook: dict | None
    teaching_preferences: dict | None
    network_enabled: bool
    scope: TextbookScope
    documents: list[KnowledgeDocument]
    context: str
    teaching_context: dict
    online_results: list[dict]
    payload: dict


class TeachingWorkflowInputState(TypedDict):
    """进入图编排前已经确定的输入状态。"""

    mode: WorkflowMode
    grade: int
    question: str
    retrieval_question: str
    messages: list[dict]
    textbook: dict | None
    teaching_preferences: dict | None
    network_enabled: bool


class ResolvedTeachingWorkflowState(TypedDict):
    """节点内部使用的完整状态视图。"""

    mode: WorkflowMode
    grade: int
    question: str
    retrieval_question: str
    messages: list[dict]
    textbook: dict | None
    teaching_preferences: dict | None
    network_enabled: bool
    scope: TextbookScope
    documents: list[KnowledgeDocument]
    context: str
    teaching_context: dict
    online_results: list[dict]
    payload: dict


_GRADE_KEYWORD_RULES: tuple[tuple[int, tuple[str, ...]], ...] = (
    (1, ("20以内", "凑十法", "破十法", "个位", "十位")),
    (2, ("表内乘法", "厘米", "米", "元角分", "角钱")),
    (3, ("分数", "周长", "长方形", "面积", "小数初步")),
    (4, ("小数", "三角形", "平行四边形", "平均数", "鸡兔同笼")),
    (5, ("方程", "因数", "倍数", "分数加减", "体积")),
    (6, ("比例", "百分数", "圆柱", "圆锥", "负数")),
)
_CHINESE_GRADE_MAP = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6}


def _normalize_messages(messages: list[dict] | None) -> list[dict]:
    if not messages:
        return []

    normalized: list[dict] = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = str(item.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content})
    return normalized


def _extract_grade(text: str) -> int | None:
    digit_match = re.search(r"([1-6])\s*年级", text)
    if digit_match:
        return int(digit_match.group(1))

    chinese_match = re.search(r"([一二三四五六])\s*年级", text)
    if chinese_match:
        return _CHINESE_GRADE_MAP.get(chinese_match.group(1))

    for grade, keywords in _GRADE_KEYWORD_RULES:
        if any(keyword in text for keyword in keywords):
            return grade

    return None


def _build_retrieval_question(question: str, messages: list[dict]) -> str:
    """当用户只给补充要求时，尽量从历史消息中拼出更适合检索的问题。"""

    latest_question = question.strip()
    if not latest_question:
        return latest_question

    strong_signal = bool(re.search(r"\d", latest_question)) or any(
        token in latest_question for token in ("加", "减", "乘", "除", "分数", "小数", "长方形", "面积", "周长")
    )
    if strong_signal:
        return latest_question

    for item in reversed(messages):
        if item["role"] != "user":
            continue
        candidate = item["content"].strip()
        if not candidate or candidate == latest_question:
            continue
        if re.search(r"\d", candidate) or any(
            token in candidate for token in ("加", "减", "乘", "除", "分数", "小数", "长方形", "面积", "周长")
        ):
            return f"原题：{candidate}\n补充要求：{latest_question}"

    return latest_question


def resolve_conversation_inputs(
    grade: int | None,
    question: str,
    messages: list[dict] | None = None,
) -> tuple[int, str, str, list[dict]]:
    """统一解析年级、最新问题、检索问题和标准化对话历史。"""

    normalized_messages = _normalize_messages(messages)
    latest_question = question.strip()

    if not latest_question:
        for item in reversed(normalized_messages):
            if item["role"] == "user":
                latest_question = item["content"]
                break

    resolved_grade = grade
    if resolved_grade is None:
        text_candidates = [latest_question, *[item["content"] for item in normalized_messages if item["role"] == "user"]]
        for text in text_candidates:
            inferred_grade = _extract_grade(text)
            if inferred_grade is not None:
                resolved_grade = inferred_grade
                break

    if resolved_grade is None:
        resolved_grade = 3

    retrieval_question = _build_retrieval_question(latest_question, normalized_messages)
    return resolved_grade, latest_question, retrieval_question, normalized_messages


def _prepare_context(state: TeachingWorkflowInputState) -> TeachingWorkflowState:
    """工作流前置节点：完成教材范围解析、知识检索与上下文拼装。"""

    payload = cast(TeachingWorkflowInputState, state)
    grade = payload["grade"]
    question = payload["retrieval_question"]
    textbook = payload.get("textbook")
    scope = resolve_textbook_scope(grade, textbook)
    documents = retrieve_knowledge(question, grade, textbook=textbook)
    teaching_context = build_teaching_quality_context(grade, payload["question"], documents, payload.get("teaching_preferences"))
    online_results = search_online_documents(payload["question"]) if payload.get("network_enabled") else []
    online_context = render_online_search_context(online_results)
    merged_context = render_retrieved_context(documents)
    if online_context:
        merged_context = f"{merged_context}\n\n## 联网参考资料\n{online_context}" if merged_context else online_context

    return {
        "scope": scope,
        "documents": documents,
        "context": merged_context,
        "teaching_context": teaching_context,
        "online_results": online_results,
    }


def _latest_assistant_text(messages: list[dict] | None) -> str:
    if not messages:
        return ""

    for item in reversed(messages):
        if item.get("role") == "assistant" and item.get("content"):
            return str(item["content"]).strip()

    return ""


def _build_answer_fallback(
    state: TeachingWorkflowInputState,
    documents: list[KnowledgeDocument],
    teaching_context: dict | None = None,
) -> str:
    """构造答案兜底逻辑，并兼容“更短一点”这类压缩请求。"""

    payload = cast(TeachingWorkflowInputState, state)
    question = payload["question"]
    retrieval_question = payload["retrieval_question"]
    messages = payload.get("messages")
    previous_answer = _latest_assistant_text(messages)

    if previous_answer and any(token in question for token in ("简短", "更短", "精简", "一句话", "压缩")):
        compressed_lines = [line.strip() for line in previous_answer.splitlines() if line.strip()][:6]
        compressed_body = "\n".join(compressed_lines[:3])
        return (
            "## 结论\n"
            "下面给你一个更简短的版本。\n\n"
            "## 解题步骤\n"
            f"1. {compressed_body or '先按原题找数字和关键词，再列式计算。'}\n"
            "2. 如果还想继续压缩，我可以再改成 1-2 句话口播版。\n\n"
            "## 同类练习\n"
            "把题目中的数字换一组，再试着自己列式。"
        )

    return build_rag_fallback_answer(payload["grade"], retrieval_question, documents, teaching_context)


def _route_mode(state: TeachingWorkflowInputState) -> WorkflowMode:
    payload = cast(TeachingWorkflowInputState, state)
    return payload["mode"]


def _answer_payload(state: ResolvedTeachingWorkflowState) -> TeachingWorkflowState:
    """工作流问答分支：优先走 LLM，失败时退回规则模板。"""

    payload = cast(ResolvedTeachingWorkflowState, state)
    scope = payload["scope"]
    documents = payload["documents"]
    teaching_context = payload["teaching_context"]
    chain = _build_qa_chain()
    history = build_history_messages(payload.get("messages"), payload["question"])

    if chain is None:
        answer = _build_answer_fallback(state, documents, teaching_context)
    else:
        try:
            fallback_answer = _build_answer_fallback(state, documents, teaching_context)
            answer = chain.invoke(
                {
                    "grade": payload["grade"],
                    "question": payload["question"],
                    "context": payload["context"],
                    "history": history,
                    "textbook_label": scope.label,
                    "teaching_goal": teaching_context["teaching_goal"],
                    "student_profile": teaching_context["student_profile"],
                    "teaching_style_instruction": teaching_context["teaching_style_instruction"],
                    "depth_instruction": teaching_context["depth_instruction"],
                    "misconception_focus": teaching_context["misconception_focus"],
                    "teacher_prompt": teaching_context["teacher_prompt"],
                }
            )
            if not answer_has_required_sections(answer):
                answer = fallback_answer
        except Exception:
            logger.exception("LLM answer generation failed, falling back to RAG template.")
            answer = _build_answer_fallback(state, documents, teaching_context)

    return {
        "payload": {
            "answer": answer,
            "textbook": serialize_textbook_scope(scope),
            "knowledge_points": serialize_knowledge_points(documents),
            "online_results": payload.get("online_results", []),
        }
    }


def _assets_payload(state: ResolvedTeachingWorkflowState) -> TeachingWorkflowState:
    """工作流素材分支：生成答案、视频提纲、PPT 提纲和游戏推荐。"""

    payload = cast(ResolvedTeachingWorkflowState, state)
    scope = payload["scope"]
    documents = payload["documents"]
    teaching_context = payload["teaching_context"]
    history = build_history_messages(payload.get("messages"), payload["question"])
    game = _pick_game(payload["retrieval_question"])
    fallback_assets = build_rag_fallback_assets(
        payload["grade"], payload["retrieval_question"], documents, game, teaching_context
    )
    chain = _build_assets_chain()

    if chain is None:
        return {
            "payload": {
                **fallback_assets,
                "textbook": serialize_textbook_scope(scope),
                "knowledge_points": serialize_knowledge_points(documents),
                "online_results": payload.get("online_results", []),
            }
        }

    try:
        fallback_answer = fallback_assets["answer"]
        raw = chain.invoke(
                {
                    "grade": payload["grade"],
                    "question": payload["question"],
                    "context": payload["context"],
                    "history": history,
                    "textbook_label": scope.label,
                    "teaching_goal": teaching_context["teaching_goal"],
                    "student_profile": teaching_context["student_profile"],
                    "teaching_style_instruction": teaching_context["teaching_style_instruction"],
                    "depth_instruction": teaching_context["depth_instruction"],
                    "misconception_focus": teaching_context["misconception_focus"],
                    "teacher_prompt": teaching_context["teacher_prompt"],
                }
        ).strip()
    except Exception:
        logger.exception("LLM asset generation failed, falling back to RAG template.")
        return {
            "payload": {
                **fallback_assets,
                "textbook": serialize_textbook_scope(scope),
                "knowledge_points": serialize_knowledge_points(documents),
                "online_results": payload.get("online_results", []),
            }
        }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "payload": {
                **fallback_assets,
                "textbook": serialize_textbook_scope(scope),
                "knowledge_points": serialize_knowledge_points(documents),
                "online_results": payload.get("online_results", []),
            }
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
        "payload": {
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
            "online_results": payload.get("online_results", []),
        }
    }


@lru_cache(maxsize=1)
def _build_teaching_workflow():
    """构建并缓存教学工作流图，避免每次请求重复装配节点。"""

    workflow = StateGraph(TeachingWorkflowState)
    workflow.add_node("prepare_context", _prepare_context)
    workflow.add_node("answer", _answer_payload)
    workflow.add_node("assets", _assets_payload)
    workflow.add_edge(START, "prepare_context")
    workflow.add_conditional_edges(
        "prepare_context",
        _route_mode,
        {
            "answer": "answer",
            "assets": "assets",
        },
    )
    workflow.add_edge("answer", END)
    workflow.add_edge("assets", END)
    return workflow.compile()


def run_teaching_workflow(
    mode: WorkflowMode,
    grade: int | None,
    question: str,
    textbook: dict | None = None,
    messages: list[dict] | None = None,
    teaching_preferences: dict | None = None,
    network_enabled: bool = False,
) -> dict:
    """运行指定模式的教学工作流，并返回最终 payload。"""

    resolved_grade, latest_question, retrieval_question, normalized_messages = resolve_conversation_inputs(
        grade, question, messages
    )
    result = _build_teaching_workflow().invoke(
        {
            "mode": mode,
            "grade": resolved_grade,
            "question": latest_question,
            "retrieval_question": retrieval_question,
            "messages": normalized_messages,
            "textbook": textbook,
            "teaching_preferences": teaching_preferences,
            "network_enabled": network_enabled,
        }
    )
    return result["payload"]


def generate_answer(
    grade: int | None,
    question: str,
    textbook: dict | None = None,
    messages: list[dict] | None = None,
    teaching_preferences: dict | None = None,
    network_enabled: bool = False,
) -> dict:
    """工作流版问答入口。"""

    return run_teaching_workflow(
        "answer",
        grade,
        question,
        textbook=textbook,
        messages=messages,
        teaching_preferences=teaching_preferences,
        network_enabled=network_enabled,
    )


def generate_lesson_assets(
    grade: int | None,
    question: str,
    textbook: dict | None = None,
    messages: list[dict] | None = None,
    teaching_preferences: dict | None = None,
    network_enabled: bool = False,
) -> dict:
    """工作流版课程素材入口。"""

    return run_teaching_workflow(
        "assets",
        grade,
        question,
        textbook=textbook,
        messages=messages,
        teaching_preferences=teaching_preferences,
        network_enabled=network_enabled,
    )


def generate_video_script(
    grade: int | None,
    question: str,
    textbook: dict | None = None,
    messages: list[dict] | None = None,
    teaching_preferences: dict | None = None,
    network_enabled: bool = False,
) -> dict:
    """从课程素材里提取视频脚本。"""

    data = generate_lesson_assets(
        grade,
        question,
        textbook=textbook,
        messages=messages,
        teaching_preferences=teaching_preferences,
        network_enabled=network_enabled,
    )
    return data["video"]


def generate_ppt_outline(
    grade: int | None,
    question: str,
    textbook: dict | None = None,
    messages: list[dict] | None = None,
    teaching_preferences: dict | None = None,
    network_enabled: bool = False,
) -> dict:
    """从课程素材里提取 PPT 大纲。"""

    data = generate_lesson_assets(
        grade,
        question,
        textbook=textbook,
        messages=messages,
        teaching_preferences=teaching_preferences,
        network_enabled=network_enabled,
    )
    return data["ppt"]
