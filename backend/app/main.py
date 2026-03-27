"""FastAPI 入口，负责暴露后端 HTTP 接口与数据模型。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.animation_game_service import generate_animation_game
from app.lesson_prep_service import generate_lesson_prep
from app.teaching_video_service import generate_teaching_video, get_video_file_path
from app.teaching_workflow_service import (
    generate_answer,
    generate_lesson_assets,
    generate_ppt_outline,
    resolve_conversation_inputs,
)
from app.ppt_service import build_pptx_file
from app.textbook_repository import get_textbook_catalog

load_dotenv()

app = FastAPI(title="小学数学 AI 教学问答 API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextbookRequest(BaseModel):
    edition: str = Field(default="rjb", min_length=1, max_length=32)
    subject: str = Field(default="math", min_length=1, max_length=32)
    semester: str | None = Field(default="下册", max_length=8)


class QARequest(BaseModel):
    grade: int | None = Field(default=None, ge=1, le=6)
    question: str = Field(min_length=1, max_length=4000)
    messages: list["ConversationMessageRequest"] = Field(default_factory=list, max_length=24)
    textbook: TextbookRequest | None = None


class ConversationMessageRequest(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class QAResponse(BaseModel):
    answer: str
    textbook: "TextbookScopePayload"
    knowledge_points: list["KnowledgePointPayload"]


class LessonPrepRequest(BaseModel):
    grade: int = Field(ge=1, le=6)
    chapter: str = Field(min_length=1, max_length=120)
    knowledge_point: str = Field(min_length=1, max_length=120)


class LessonPrepExample(BaseModel):
    title: str
    situation: str
    steps: list[str]


class LessonPrepMisconception(BaseModel):
    title: str
    explanation: str
    teacher_prompt: str


class LessonPrepInteraction(BaseModel):
    type: str
    title: str
    prompt: str
    expected_response: str


class LessonPrepResponse(BaseModel):
    title: str
    summary: str
    teaching_objectives: list[str]
    classroom_examples: list[LessonPrepExample]
    misconceptions: list[LessonPrepMisconception]
    interactions: list[LessonPrepInteraction]


class Slide(BaseModel):
    title: str
    bullet_points: list[str]


class VideoOutlineAsset(BaseModel):
    title: str
    script_steps: list[str]


class VideoScene(BaseModel):
    title: str
    narration: str
    duration_seconds: float


class TeachingVideoAsset(BaseModel):
    title: str
    summary: str
    download_path: str
    duration_seconds: float
    video_spec: dict
    scenes: list[VideoScene]


class PPTAsset(BaseModel):
    title: str
    slides: list[Slide]


class GameAsset(BaseModel):
    title: str
    url: str
    reason: str


class AnimationGameAsset(BaseModel):
    title: str
    summary: str
    html: str
    demo_spec: dict


class LessonAssetsResponse(BaseModel):
    answer: str
    video: VideoOutlineAsset
    ppt: PPTAsset
    game: GameAsset
    textbook: "TextbookScopePayload"
    knowledge_points: list["KnowledgePointPayload"]


class TextbookDefaults(BaseModel):
    edition: str
    subject: str
    grade: int
    semester: str


class TextbookOption(BaseModel):
    edition: str
    edition_label: str
    subject: str
    subject_label: str
    publisher: str
    label: str
    grades: list[int]
    semesters: list[str]
    source_label: str
    source_url: str


class TextbookScopePayload(BaseModel):
    edition: str
    edition_label: str
    subject: str
    subject_label: str
    publisher: str
    grade: int
    semester: str
    label: str
    source_label: str
    source_url: str


class KnowledgePointPayload(BaseModel):
    doc_id: str
    title: str
    unit_title: str
    curriculum_label: str
    summary: str
    example: str
    concept_tags: list[str]
    source_label: str
    source_url: str


class TextbookCatalogResponse(BaseModel):
    defaults: TextbookDefaults
    textbooks: list[TextbookOption]


class PPTExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slides: list[Slide] = Field(min_length=1, max_length=30)


@app.get("/api/health")
def health():
    """返回服务健康状态，供前端和部署脚本探活使用。"""
    return {"status": "ok"}


@app.get("/api/textbook-catalog", response_model=TextbookCatalogResponse)
def textbook_catalog():
    """返回前端教材选择器需要的教材目录与默认值。"""
    return TextbookCatalogResponse(**get_textbook_catalog())


@app.post("/api/qa", response_model=QAResponse)
def ask_math_qa(payload: QARequest):
    """处理问答请求，返回答案与检索到的知识点。"""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    textbook = payload.textbook.model_dump(exclude_none=True) if payload.textbook else None
    messages = [message.model_dump() for message in payload.messages]
    data = generate_answer(payload.grade, question, textbook, messages=messages)
    return QAResponse(**data)


@app.post("/api/lesson-prep", response_model=LessonPrepResponse)
def build_lesson_prep(payload: LessonPrepRequest):
    """根据章节与知识点生成一份可直接修改的备课草案。"""
    chapter = payload.chapter.strip()
    knowledge_point = payload.knowledge_point.strip()
    if not chapter or not knowledge_point:
        raise HTTPException(status_code=400, detail="chapter and knowledge_point cannot be empty")
    return LessonPrepResponse(**generate_lesson_prep(payload.grade, chapter, knowledge_point))


@app.post("/api/lesson-assets", response_model=LessonAssetsResponse)
def build_lesson_assets(payload: QARequest):
    """一次性生成问答、视频提纲、PPT 提纲和互动游戏推荐。"""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    textbook = payload.textbook.model_dump(exclude_none=True) if payload.textbook else None
    messages = [message.model_dump() for message in payload.messages]
    data = generate_lesson_assets(payload.grade, question, textbook, messages=messages)
    return LessonAssetsResponse(**data)


@app.post("/api/video-script", response_model=TeachingVideoAsset)
@app.post("/api/teaching-video", response_model=TeachingVideoAsset)
def build_video_script(payload: QARequest):
    """生成教学视频脚本，并进一步产出可下载的视频文件。"""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    textbook = payload.textbook.model_dump(exclude_none=True) if payload.textbook else None
    messages = [message.model_dump() for message in payload.messages]
    return TeachingVideoAsset(**generate_teaching_video(payload.grade, question, textbook, messages=messages))


@app.get("/api/video-files/{file_name}")
def get_video_file(file_name: str):
    """按文件名返回已经生成的视频文件。"""
    try:
        file_path = get_video_file_path(file_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="video file not found") from error

    return FileResponse(path=file_path, media_type="video/mp4", filename=file_path.name)


@app.post("/api/ppt-outline", response_model=PPTAsset)
def build_ppt_outline(payload: QARequest):
    """生成 PPT 大纲，供前端预览或后续导出。"""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    textbook = payload.textbook.model_dump(exclude_none=True) if payload.textbook else None
    messages = [message.model_dump() for message in payload.messages]
    return PPTAsset(**generate_ppt_outline(payload.grade, question, textbook, messages=messages))


@app.post("/api/animation-game", response_model=AnimationGameAsset)
def build_animation_game(payload: QARequest):
    """生成互动动画 HTML 和对应的演示配置。"""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    messages = [message.model_dump() for message in payload.messages]
    resolved_grade, latest_question, retrieval_question, _ = resolve_conversation_inputs(payload.grade, question, messages)
    textbook = payload.textbook.model_dump(exclude_none=True) if payload.textbook else None
    target_question = retrieval_question or latest_question
    return AnimationGameAsset(**generate_animation_game(resolved_grade, target_question, textbook))


@app.post("/api/pptx")
def export_pptx(payload: PPTExportRequest, background_tasks: BackgroundTasks):
    """把前端传来的 PPT 大纲导出成临时 PPTX 文件。"""
    export_dir = Path(os.getenv("PPT_EXPORT_DIR", "./tmp_exports"))
    file_path = build_pptx_file(
        title=payload.title,
        slides=[slide.model_dump() for slide in payload.slides],
        output_dir=export_dir,
    )
    background_tasks.add_task(file_path.unlink, missing_ok=True)
    return FileResponse(
        path=file_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=f"{payload.title}.pptx",
        background=background_tasks,
    )
