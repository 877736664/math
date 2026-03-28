"""教学素材生成与文件导出接口。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from app.services.animation_game_service import generate_animation_game
from app.api.helpers import dump_messages, dump_teaching_preferences, dump_textbook, require_question
from app.services.image_generation_service import get_generated_image_path
from app.services.ppt_service import build_pptx_file
from app.schemas.api import AnimationGameAsset, LessonAssetsResponse, PPTAsset, PPTExportRequest, QARequest, TeachingVideoAsset
from app.services.teaching_video_service import generate_teaching_video, get_video_file_path
from app.workflows.teaching_workflow import generate_lesson_assets, generate_ppt_outline, resolve_conversation_inputs


router = APIRouter(tags=["assets"])


@router.post("/lesson-assets", response_model=LessonAssetsResponse)
def build_lesson_assets(payload: QARequest):
    """一次性生成问答、视频提纲、PPT 提纲和互动游戏推荐。"""

    question = require_question(payload.question)
    data = generate_lesson_assets(
        payload.grade,
        question,
        dump_textbook(payload.textbook),
        messages=dump_messages(payload.messages),
        teaching_preferences=dump_teaching_preferences(payload.teaching_preferences),
        network_enabled=payload.network_enabled,
    )
    return LessonAssetsResponse(**data)


@router.post("/video-script", response_model=TeachingVideoAsset)
@router.post("/teaching-video", response_model=TeachingVideoAsset)
def build_video_script(payload: QARequest):
    """生成教学视频脚本，并进一步产出可下载的视频文件。"""

    question = require_question(payload.question)
    return TeachingVideoAsset(
        **generate_teaching_video(
            payload.grade,
            question,
            dump_textbook(payload.textbook),
            messages=dump_messages(payload.messages),
            teaching_preferences=dump_teaching_preferences(payload.teaching_preferences),
            network_enabled=payload.network_enabled,
        )
    )


@router.get("/video-files/{file_name}")
def get_video_file(file_name: str):
    """按文件名返回已经生成的视频文件。"""

    try:
        file_path = get_video_file_path(file_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="video file not found") from error

    return FileResponse(path=file_path, media_type="video/mp4", filename=file_path.name)


@router.get("/generated-images/{file_name}")
def get_generated_image(file_name: str):
    """按文件名返回本地缓存的动画图片素材。"""

    try:
        file_path = get_generated_image_path(file_name)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail="generated image not found") from error

    media_type = "image/webp" if file_path.suffix.lower() == ".webp" else "image/png" if file_path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(path=file_path, media_type=media_type, filename=file_path.name)


@router.post("/ppt-outline", response_model=PPTAsset)
def build_ppt_outline(payload: QARequest):
    """生成 PPT 大纲，供前端预览或后续导出。"""

    question = require_question(payload.question)
    return PPTAsset(
        **generate_ppt_outline(
            payload.grade,
            question,
            dump_textbook(payload.textbook),
            messages=dump_messages(payload.messages),
            teaching_preferences=dump_teaching_preferences(payload.teaching_preferences),
            network_enabled=payload.network_enabled,
        )
    )


@router.post("/animation-game", response_model=AnimationGameAsset)
def build_animation_game(payload: QARequest):
    """生成互动动画 HTML 和对应的演示配置。"""

    question = require_question(payload.question)
    messages = dump_messages(payload.messages)
    resolved_grade, latest_question, retrieval_question, _ = resolve_conversation_inputs(payload.grade, question, messages)
    target_question = retrieval_question or latest_question
    return AnimationGameAsset(
        **generate_animation_game(
            resolved_grade,
            target_question,
            dump_textbook(payload.textbook),
            variation_seed=payload.animation_seed,
        )
    )


@router.post("/pptx")
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
