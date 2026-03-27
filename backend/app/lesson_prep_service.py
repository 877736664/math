"""备课草案生成服务。"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_service import _create_llm
from app.rag_service import render_retrieved_context, retrieve_knowledge

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _build_lesson_prep_chain():
    """构建备课用 LLM 链，输出严格 JSON。"""

    llm = _create_llm(
        timeout=int(os.getenv("OPENAI_LESSON_PREP_TIMEOUT", "40")),
        max_tokens=int(os.getenv("OPENAI_LESSON_PREP_MAX_TOKENS", "1400")),
        enable_thinking=False,
        response_format={"type": "json_object"},
    )
    if llm is None:
        return None

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "你是小学数学备课助手。"
                    "请根据年级、章节、知识点和检索到的知识，输出严格 JSON，不要输出 markdown 代码块。"
                    "JSON 结构如下："
                    "{{"
                    '"title":"...",'
                    '"summary":"...",'
                    '"teaching_objectives":["...","...","..."],'
                    '"classroom_examples":[{{"title":"...","situation":"...","steps":["...","..."]}}],'
                    '"misconceptions":[{{"title":"...","explanation":"...","teacher_prompt":"..."}}],'
                    '"interactions":[{{"type":"...","title":"...","prompt":"...","expected_response":"..."}}]'
                    "}}"
                    "要求："
                    "1) 全部使用简体中文；"
                    "2) 面向小学{grade}年级；"
                    "3) teaching_objectives 返回3条；"
                    "4) classroom_examples 返回2条，每条 steps 返回3-4步；"
                    "5) misconceptions 返回3条；"
                    "6) interactions 返回2条，其中至少1条适合课堂小游戏或互动题；"
                    "7) 内容要让老师拿来就能微调使用，避免空话。"
                ),
            ),
            (
                "human",
                "年级：{grade}年级\n章节：{chapter}\n知识点：{knowledge_point}\n\n检索知识：\n{context}",
            ),
        ]
    )

    return prompt | llm | StrOutputParser()


def _fallback_lesson_prep(grade: int, chapter: str, knowledge_point: str, context_lines: list[str]) -> dict:
    """当 LLM 不可用时，基于检索内容返回一份可直接套用的备课模板。"""

    focus = knowledge_point.strip() or chapter.strip() or "本课知识"
    chapter_text = chapter.strip() or "本单元"
    context_hint = context_lines[0] if context_lines else f"围绕“{focus}”组织讲解。"

    return {
        "title": f"{grade}年级《{chapter_text}》一键备课",
        "summary": f"围绕“{focus}”快速生成一节可直接微调的课堂方案，适合 10 分钟内完成首版备课。",
        "teaching_objectives": [
            f"知道“{focus}”的核心概念，并能说出它解决什么问题。",
            f"能借助课堂例题完成“{focus}”的基本应用。",
            f"能识别与“{focus}”相关的常见错误，并进行简单纠正。",
        ],
        "classroom_examples": [
            {
                "title": "例题一：先理解，再列式",
                "situation": f"从《{chapter_text}》里挑一个最基础的“{focus}”情境题，先帮助学生看懂题意。",
                "steps": [
                    "先圈出题目中的数字、单位和关键词。",
                    f"把题目和“{focus}”的核心方法对应起来。",
                    "边列式边说理由，让学生知道为什么这样算。",
                ],
            },
            {
                "title": "例题二：换一个生活场景再练一次",
                "situation": f"把“{focus}”放进学生熟悉的购物、分东西或图形观察情境里做迁移练习。",
                "steps": [
                    "先让学生自己尝试判断用什么方法。",
                    "再请学生口头说明列式依据。",
                    "最后一起核对结果，并追问有没有别的想法。",
                ],
            },
        ],
        "misconceptions": [
            {
                "title": "只看数字，不看关键词",
                "explanation": f"学生容易一看到数字就计算，忽略“{focus}”真正考查的数量关系。",
                "teacher_prompt": "先别急着算，先说说这道题到底在求什么。",
            },
            {
                "title": "会列式，但理由说不清",
                "explanation": "学生可能能写出答案，但讲不清为什么要这样列式。",
                "teacher_prompt": "把你的想法完整说一遍：先看到了什么，再决定怎么做。",
            },
            {
                "title": "算完不检查",
                "explanation": "学生往往停留在算出结果，没有代回原题核对是否合理。",
                "teacher_prompt": "如果把答案带回题目里读一遍，还说得通吗？",
            },
        ],
        "interactions": [
            {
                "type": "课堂小游戏",
                "title": "一分钟抢答卡",
                "prompt": f"老师快速出 3 题与“{focus}”相关的口头小题，学生举卡片或拍手抢答。",
                "expected_response": "学生能快速说出方法或结果，并解释关键词依据。",
            },
            {
                "type": "互动题",
                "title": "找错误挑战",
                "prompt": f"老师故意展示一个关于“{focus}”的错误解法，请学生指出错在哪里。",
                "expected_response": "学生能说出错误步骤，并给出正确改法。",
            },
        ],
        "source_hint": context_hint,
    }


def _normalize_lesson_prep(raw: dict, fallback: dict) -> dict:
    """清洗模型输出，确保字段数量和结构满足前端约定。"""

    if not isinstance(raw, dict):
        return fallback

    def _list_strings(value: object, *, size: int, default: list[str]) -> list[str]:
        if not isinstance(value, list):
            return default
        items = [str(item).strip() for item in value if str(item).strip()]
        return items[:size] if items else default

    examples = []
    for index, item in enumerate(raw.get("classroom_examples", [])):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback["classroom_examples"][min(index, len(fallback["classroom_examples"]) - 1)]
        examples.append(
            {
                "title": str(item.get("title", fallback_item["title"]))[:40].strip() or fallback_item["title"],
                "situation": str(item.get("situation", fallback_item["situation"]))[:160].strip()
                or fallback_item["situation"],
                "steps": _list_strings(item.get("steps"), size=4, default=fallback_item["steps"]),
            }
        )
    if len(examples) < 2:
        examples = fallback["classroom_examples"]

    misconceptions = []
    for index, item in enumerate(raw.get("misconceptions", [])):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback["misconceptions"][min(index, len(fallback["misconceptions"]) - 1)]
        misconceptions.append(
            {
                "title": str(item.get("title", fallback_item["title"]))[:36].strip() or fallback_item["title"],
                "explanation": str(item.get("explanation", fallback_item["explanation"]))[:180].strip()
                or fallback_item["explanation"],
                "teacher_prompt": str(item.get("teacher_prompt", fallback_item["teacher_prompt"]))[:100].strip()
                or fallback_item["teacher_prompt"],
            }
        )
    if len(misconceptions) < 3:
        misconceptions = fallback["misconceptions"]

    interactions = []
    for index, item in enumerate(raw.get("interactions", [])):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback["interactions"][min(index, len(fallback["interactions"]) - 1)]
        interactions.append(
            {
                "type": str(item.get("type", fallback_item["type"]))[:16].strip() or fallback_item["type"],
                "title": str(item.get("title", fallback_item["title"]))[:36].strip() or fallback_item["title"],
                "prompt": str(item.get("prompt", fallback_item["prompt"]))[:180].strip() or fallback_item["prompt"],
                "expected_response": str(item.get("expected_response", fallback_item["expected_response"]))[:120].strip()
                or fallback_item["expected_response"],
            }
        )
    if len(interactions) < 2:
        interactions = fallback["interactions"]

    return {
        "title": str(raw.get("title", fallback["title"]))[:80].strip() or fallback["title"],
        "summary": str(raw.get("summary", fallback["summary"]))[:180].strip() or fallback["summary"],
        "teaching_objectives": _list_strings(
            raw.get("teaching_objectives"), size=3, default=fallback["teaching_objectives"]
        ),
        "classroom_examples": examples,
        "misconceptions": misconceptions,
        "interactions": interactions,
    }


def generate_lesson_prep(grade: int, chapter: str, knowledge_point: str) -> dict:
    """生成备课接口返回的数据。"""

    retrieval_query = f"{chapter.strip()} {knowledge_point.strip()}".strip() or knowledge_point.strip() or chapter.strip()
    documents = retrieve_knowledge(retrieval_query or "小学数学", grade)
    context = render_retrieved_context(documents)
    context_lines = [document.summary for document in documents[:2] if document.summary]
    fallback = _fallback_lesson_prep(grade, chapter, knowledge_point, context_lines)
    chain = _build_lesson_prep_chain()

    if chain is None:
        return fallback

    try:
        raw = chain.invoke(
            {
                "grade": grade,
                "chapter": chapter.strip() or "本单元",
                "knowledge_point": knowledge_point.strip() or chapter.strip() or "本课知识点",
                "context": context,
            }
        ).strip()
        return _normalize_lesson_prep(json.loads(raw), fallback)
    except Exception:
        logger.exception("Lesson prep generation failed, falling back to template.")
        return fallback
