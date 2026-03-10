import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.animation_game_service import generate_animation_game
from app.llm_service import (
    generate_answer,
    generate_lesson_assets,
    generate_ppt_outline,
    generate_video_script,
)
from app.ppt_service import build_pptx_file

load_dotenv()

app = FastAPI(title="小学数学 AI 教学问答 API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QARequest(BaseModel):
    grade: int = Field(ge=1, le=6)
    question: str = Field(min_length=1, max_length=2000)


class QAResponse(BaseModel):
    answer: str


class Slide(BaseModel):
    title: str
    bullet_points: list[str]


class VideoAsset(BaseModel):
    title: str
    script_steps: list[str]


class PPTAsset(BaseModel):
    title: str
    slides: list[Slide]


class GameAsset(BaseModel):
    title: str
    url: str
    reason: str


class AnimationImageSource(BaseModel):
    query: str
    image_url: str
    source_page: str
    source_host: str


class AnimationGameAsset(BaseModel):
    title: str
    summary: str
    html: str
    search_queries: list[str]
    image_sources: list[AnimationImageSource]


class LessonAssetsResponse(BaseModel):
    answer: str
    video: VideoAsset
    ppt: PPTAsset
    game: GameAsset


class PPTExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slides: list[Slide] = Field(min_length=1, max_length=30)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/qa", response_model=QAResponse)
def ask_math_qa(payload: QARequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    return QAResponse(answer=generate_answer(payload.grade, question))


@app.post("/api/lesson-assets", response_model=LessonAssetsResponse)
def build_lesson_assets(payload: QARequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    data = generate_lesson_assets(payload.grade, question)
    return LessonAssetsResponse(**data)


@app.post("/api/video-script", response_model=VideoAsset)
def build_video_script(payload: QARequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    return VideoAsset(**generate_video_script(payload.grade, question))


@app.post("/api/ppt-outline", response_model=PPTAsset)
def build_ppt_outline(payload: QARequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    return PPTAsset(**generate_ppt_outline(payload.grade, question))


@app.post("/api/animation-game", response_model=AnimationGameAsset)
def build_animation_game(payload: QARequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question cannot be empty")
    return AnimationGameAsset(**generate_animation_game(payload.grade, question))


@app.post("/api/pptx")
def export_pptx(payload: PPTExportRequest, background_tasks: BackgroundTasks):
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
