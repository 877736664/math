"""问答与备课相关接口。"""

from fastapi import APIRouter

from app.api.helpers import dump_messages, dump_teaching_preferences, dump_textbook, require_lesson_prep_fields, require_question
from app.services.lesson_prep_service import generate_lesson_prep
from app.schemas.api import LessonPrepRequest, LessonPrepResponse, QARequest, QAResponse
from app.workflows.teaching_workflow import generate_answer


router = APIRouter(tags=["teaching"])


@router.post("/qa", response_model=QAResponse)
def ask_math_qa(payload: QARequest):
    """处理问答请求，返回答案与检索到的知识点。"""

    question = require_question(payload.question)
    data = generate_answer(
        payload.grade,
        question,
        dump_textbook(payload.textbook),
        messages=dump_messages(payload.messages),
        teaching_preferences=dump_teaching_preferences(payload.teaching_preferences),
        network_enabled=payload.network_enabled,
    )
    return QAResponse(**data)


@router.post("/lesson-prep", response_model=LessonPrepResponse)
def build_lesson_prep(payload: LessonPrepRequest):
    """根据章节与知识点生成一份可直接修改的备课草案。"""

    chapter, knowledge_point = require_lesson_prep_fields(payload.chapter, payload.knowledge_point)
    return LessonPrepResponse(**generate_lesson_prep(payload.grade, chapter, knowledge_point))
