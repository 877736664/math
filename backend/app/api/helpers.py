"""API 路由复用的小型辅助函数。"""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas.api import ConversationMessageRequest, TeachingPreferencesRequest, TextbookRequest


def require_question(question: str) -> str:
    """清洗并校验题目文本。"""

    cleaned = question.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    return cleaned


def require_lesson_prep_fields(chapter: str, knowledge_point: str) -> tuple[str, str]:
    """清洗并校验备课接口的必填字段。"""

    cleaned_chapter = chapter.strip()
    cleaned_knowledge_point = knowledge_point.strip()
    if not cleaned_chapter or not cleaned_knowledge_point:
        raise HTTPException(status_code=400, detail="chapter and knowledge_point cannot be empty")
    return cleaned_chapter, cleaned_knowledge_point


def dump_textbook(textbook: TextbookRequest | None) -> dict | None:
    """把教材请求对象转换为服务层使用的字典。"""

    return textbook.model_dump(exclude_none=True) if textbook else None


def dump_messages(messages: list[ConversationMessageRequest]) -> list[dict]:
    """把消息请求对象转换为服务层使用的普通字典列表。"""

    return [message.model_dump() for message in messages]


def dump_teaching_preferences(preferences: TeachingPreferencesRequest | None) -> dict | None:
    """把教学偏好请求对象转换为服务层使用的字典。"""

    return preferences.model_dump(exclude_none=True) if preferences else None
