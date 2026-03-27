"""教学视频生成服务，负责脚本转场景、音频占位和视频合成。"""

from __future__ import annotations

import math
import os
import struct
import subprocess
import textwrap
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

from app.teaching_workflow_service import generate_video_script


VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_FPS = 25
VIDEO_EXPORT_DIR = Path(os.getenv("VIDEO_EXPORT_DIR", "./tmp_exports/videos"))
TRANSITION_SECONDS = 0.55

PALETTES = (
    {"accent": "#b86f37", "soft": "#f3dfc9", "board": "#fffaf4", "ink": "#3f2d1f", "mint": "#dce8d8"},
    {"accent": "#7d8f53", "soft": "#e4ecd7", "board": "#fbfcf7", "ink": "#324027", "mint": "#f0e3cc"},
    {"accent": "#6a8db7", "soft": "#dbe7f4", "board": "#f8fbff", "ink": "#26384f", "mint": "#e9decc"},
)


@dataclass
class AudioSegment:
    """单个场景的音频片段及其时长。"""

    path: Path
    duration_seconds: float


class VideoScene(TypedDict):
    """视频场景在渲染阶段使用的标准结构。"""

    title: str
    narration: str
    layout: str
    subtitle_segments: list[str]


def generate_teaching_video(
    grade: int | None,
    question: str,
    textbook: dict | None = None,
    messages: list[dict] | None = None,
) -> dict:
    """生成教学视频文件，并返回下载路径与视频规格说明。"""

    video_script = generate_video_script(grade, question, textbook=textbook, messages=messages)
    script_steps = video_script.get("script_steps") or []
    title = str(video_script.get("title", "数学教学视频")).strip() or "数学教学视频"
    scenes = _build_video_scenes(title, question, script_steps)

    export_root = VIDEO_EXPORT_DIR
    export_root.mkdir(parents=True, exist_ok=True)
    asset_id = uuid4().hex
    work_dir = export_root / asset_id
    frames_dir = work_dir / "frames"
    audio_dir = work_dir / "audio"
    frames_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    audio_segments: list[AudioSegment] = []
    for index, scene in enumerate(scenes):
        audio_path = audio_dir / f"scene-{index:02d}.wav"
        audio_segments.append(_synthesize_placeholder_audio(audio_path, str(scene["narration"]), index))

    _render_video_frames(frames_dir, title, question, scenes, audio_segments)
    merged_audio_path = work_dir / "merged.wav"
    _merge_audio_segments(merged_audio_path, audio_segments)

    output_path = export_root / f"{asset_id}.mp4"
    _compose_mp4(output_path, frames_dir, merged_audio_path)
    video_spec = _build_video_spec(title, question, grade, scenes, audio_segments)

    return {
        "title": title,
        "summary": "已生成带字幕高亮和课件式转场的教学视频，当前仍使用可替换的占位 TTS 音频通路。",
        "download_path": f"/api/video-files/{output_path.name}",
        "duration_seconds": round(sum(segment.duration_seconds for segment in audio_segments), 1),
        "video_spec": video_spec,
        "scenes": [
            {
                "title": scene["title"],
                "narration": scene["narration"],
                "duration_seconds": round(audio_segments[index].duration_seconds, 1),
            }
            for index, scene in enumerate(scenes)
        ],
    }


def get_video_file_path(file_name: str) -> Path:
    """校验视频文件名并定位到导出目录中的 MP4 文件。"""

    safe_name = Path(file_name).name
    path = VIDEO_EXPORT_DIR / safe_name
    if not path.exists() or path.suffix.lower() != ".mp4":
        raise FileNotFoundError(safe_name)
    return path


def _build_video_scenes(title: str, question: str, script_steps: list[str]) -> list[VideoScene]:
    """把视频脚本拆成导入、讲解和收束几个标准场景。"""

    cleaned_steps = [str(step).strip() for step in script_steps if str(step).strip()]
    if not cleaned_steps:
        cleaned_steps = [
            "先带学生一起读题，找出关键数字和关键词。",
            "再根据题意判断用什么方法，并一步一步列式。",
            "最后带着学生回到原题检查答案是否合理。",
        ]

    scenes: list[VideoScene] = [
        {
            "title": "课程导入",
            "narration": f"这节课我们一起学习：{title}。先来看题目：{question}",
            "layout": "cover",
            "subtitle_segments": [],
        }
    ]

    for index, step in enumerate(cleaned_steps, start=1):
        scenes.append(
            {
                "title": _scene_title_from_step(step, index),
                "narration": step,
                "layout": "split" if index % 2 else "focus",
                "subtitle_segments": [],
            }
        )

    scenes.append(
        {
            "title": "课堂收束",
            "narration": "到这里，这道题的思路就讲完了。你可以暂停视频，再自己试着做一道同类型题。",
            "layout": "summary",
            "subtitle_segments": [],
        }
    )

    for scene in scenes:
        scene["subtitle_segments"] = _split_subtitle_segments(str(scene["narration"]))
    return scenes


def _build_video_spec(
    title: str,
    question: str,
    grade: int | None,
    scenes: list[VideoScene],
    audio_segments: list[AudioSegment],
) -> dict:
    """生成前端或外部工具可复用的视频规格描述。"""

    theme = _infer_video_theme(question)
    character = _pick_character(theme)
    scene_specs = []

    for index, scene in enumerate(scenes):
        scene_specs.append(
            {
                "id": f"scene_{index + 1:02d}",
                "template": _scene_template_for_layout(scene["layout"]),
                "duration_seconds": round(audio_segments[index].duration_seconds, 1),
                "transition_in": _transition_name(scene["layout"], entering=True),
                "transition_out": _transition_name(scene["layout"], entering=False),
                "title": scene["title"],
                "narration": scene["narration"],
                "subtitle_segments": scene["subtitle_segments"],
                "layout": {
                    "type": scene["layout"],
                    "show_question": scene["layout"] != "summary",
                    "show_character": True,
                },
                "animation": _animation_config_for_layout(scene["layout"]),
                "data": _scene_data_payload(question, scene),
            }
        )

    return {
        "version": "1.0",
        "video_type": "math_teaching",
        "theme": theme,
        "audience": {
            "grade": grade or 3,
            "age_range": _age_range_for_grade(grade or 3),
        },
        "style": {
            "visual_style": "primary-friendly",
            "character": character,
            "palette": "warm-classroom",
            "subtitle_mode": "phrase-highlight",
        },
        "meta": {
            "title": title,
            "subtitle": f"{grade or 3}年级数学微课",
            "question": question,
            "knowledge_points": _knowledge_points_from_question(question),
            "duration_target_seconds": round(sum(segment.duration_seconds for segment in audio_segments)),
        },
        "audio": {
            "voice_mode": "placeholder_tts",
            "bgm": "light_marimba",
            "pace": "medium",
        },
        "assets": {
            "props": _props_for_theme(theme),
            "background": "classroom-board",
        },
        "scenes": scene_specs,
    }


def _infer_video_theme(question: str) -> str:
    if any(token in question for token in ("平均分", "每人", "分给")):
        return "average_share"
    if any(token in question for token in ("分数", "几分之一", "几分之几")):
        return "fraction_intro"
    if any(token in question for token in ("面积", "长方形", "正方形")):
        return "shape_area"
    if any(token in question for token in ("加", "+", "一共")):
        return "addition"
    if any(token in question for token in ("减", "-", "还剩")):
        return "subtraction"
    return "general_math"


def _pick_character(theme: str) -> str:
    if theme in {"average_share", "addition", "subtraction"}:
        return "block_bear"
    if theme == "fraction_intro":
        return "fraction_rabbit"
    return "star_teacher"


def _scene_template_for_layout(layout: str) -> str:
    mapping = {
        "cover": "intro_story",
        "split": "split_groups",
        "focus": "equation_build",
        "summary": "summary_close",
    }
    return mapping.get(layout, "equation_build")


def _transition_name(layout: str, *, entering: bool) -> str:
    mapping = {
        "cover": ("fade_slide_up", "card_wipe"),
        "split": ("push_left", "fade"),
        "focus": ("zoom_in", "fade"),
        "summary": ("flash_card", "fade_out"),
    }
    enter, leave = mapping.get(layout, ("fade", "fade"))
    return enter if entering else leave


def _animation_config_for_layout(layout: str) -> dict:
    mapping = {
        "cover": {
            "entrance": "character_pop_in",
            "emphasis": "question_keywords",
        },
        "split": {
            "item_motion": "token_fly_to_groups",
            "highlight_result": True,
        },
        "focus": {
            "equation_motion": "step_build",
            "keyword_highlight": True,
        },
        "summary": {
            "answer_effect": "bounce_highlight",
        },
    }
    return mapping.get(layout, {"entrance": "fade_in"})


def _scene_data_payload(question: str, scene: VideoScene) -> dict:
    if scene["layout"] == "split":
        return {
            "question": question,
            "subtitle_segments": scene["subtitle_segments"],
        }
    if scene["layout"] == "focus":
        return {
            "equation_steps": scene["subtitle_segments"],
        }
    if scene["layout"] == "summary":
        return {
            "review_prompt": "暂停视频，再自己说一遍解题思路。",
        }
    return {
        "question": question,
    }


def _age_range_for_grade(grade: int) -> str:
    mapping = {
        1: "6-7",
        2: "7-8",
        3: "8-9",
        4: "9-10",
        5: "10-11",
        6: "11-12",
    }
    return mapping.get(grade, "8-9")


def _knowledge_points_from_question(question: str) -> list[str]:
    candidates = []
    for token in ("平均分", "除法", "分数", "面积", "长方形", "加法", "减法", "乘法", "小数"):
        if token in question:
            candidates.append(token)
    return candidates[:3] or ["数学思维", "列式讲解"]


def _props_for_theme(theme: str) -> list[str]:
    mapping = {
        "average_share": ["candy", "student", "number_card"],
        "fraction_intro": ["pizza", "fraction_card", "rabbit"],
        "shape_area": ["grid_board", "rectangle_card", "ruler"],
        "addition": ["block", "number_card", "star"],
        "subtraction": ["apple", "basket", "number_card"],
    }
    return mapping.get(theme, ["number_card", "blackboard", "star"])


def _scene_title_from_step(step: str, index: int) -> str:
    parts = step.split("：", 1)
    if len(parts) == 2 and len(parts[0].strip()) <= 12:
        return parts[0].strip()
    short_line = step.split("。", 1)[0].strip()
    if short_line and len(short_line) <= 16:
        return short_line
    return f"讲解步骤 {index:02d}"


def _split_subtitle_segments(text: str) -> list[str]:
    normalized = " ".join(str(text).split())
    if not normalized:
        return [""]

    parts = [segment.strip() for segment in textwrap.wrap(normalized, width=14, break_long_words=False) if segment.strip()]
    return parts[:4] or [normalized]


def _synthesize_placeholder_audio(output_path: Path, text: str, index: int) -> AudioSegment:
    """生成占位语音波形，当前用于打通完整视频导出链路。"""

    sample_rate = 22050
    duration_seconds = min(max(len(text) * 0.14, 3.0), 8.5)
    total_frames = int(sample_rate * duration_seconds)
    base_frequency = 220 + index * 24
    amplitude = 0.15

    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)

        frames = bytearray()
        for frame_index in range(total_frames):
            progress = frame_index / sample_rate
            envelope = min(progress / 0.24, 1.0) * min((duration_seconds - progress) / 0.28, 1.0)
            envelope = max(0.0, min(envelope, 1.0))
            pulse = 0.55 + 0.45 * math.sin(progress * math.pi * 1.2)
            value = math.sin(2 * math.pi * base_frequency * progress) * amplitude * envelope * pulse
            frames.extend(struct.pack("<h", int(value * 32767)))

        wav_file.writeframes(frames)

    return AudioSegment(path=output_path, duration_seconds=duration_seconds)


def _render_video_frames(
    frames_dir: Path,
    title: str,
    question: str,
    scenes: list[VideoScene],
    audio_segments: list[AudioSegment],
) -> None:
    """按场景时长逐帧渲染视频画面。"""

    frame_index = 0
    for scene_index, scene in enumerate(scenes):
        frame_count = max(1, int(math.ceil(audio_segments[scene_index].duration_seconds * VIDEO_FPS)))
        for local_index in range(frame_count):
            progress = local_index / max(frame_count - 1, 1)
            output_path = frames_dir / f"frame-{frame_index:05d}.png"
            _render_scene_frame(output_path, title, question, scene, scene_index, len(scenes), progress)
            frame_index += 1


def _render_scene_frame(
    output_path: Path,
    title: str,
    question: str,
    scene: VideoScene,
    index: int,
    total: int,
    progress: float,
) -> None:
    """渲染单帧画面，根据场景布局绘制不同版式。"""

    palette = PALETTES[index % len(PALETTES)]
    image = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), "#f6efe5")
    draw = ImageDraw.Draw(image)

    title_font = _load_font(42, bold=True)
    heading_font = _load_font(34, bold=True)
    body_font = _load_font(24)
    meta_font = _load_font(20)
    subtitle_font = _load_font(28, bold=True)

    _draw_background(draw, palette, progress, index)
    _draw_top_banner(draw, title, index, total, title_font, meta_font, palette)

    offset_x = _transition_offset(scene["layout"], progress)
    offset_y = _transition_lift(progress)
    board_box = (72 + offset_x, 190 + offset_y, 1208 + offset_x, 600 + offset_y)
    _draw_board(draw, board_box, palette)

    if scene["layout"] == "cover":
        _draw_cover_layout(draw, board_box, question, scene, heading_font, body_font, meta_font, palette)
    elif scene["layout"] == "summary":
        _draw_summary_layout(draw, board_box, question, scene, heading_font, body_font, meta_font, palette)
    elif scene["layout"] == "focus":
        _draw_focus_layout(draw, board_box, question, scene, heading_font, body_font, meta_font, palette, progress)
    else:
        _draw_split_layout(draw, board_box, question, scene, heading_font, body_font, meta_font, palette, progress)

    _draw_subtitle_panel(draw, scene, progress, subtitle_font, meta_font, palette)
    image.save(output_path)


def _draw_background(draw: ImageDraw.ImageDraw, palette: dict, progress: float, index: int) -> None:
    draw.rectangle((0, 0, VIDEO_WIDTH, VIDEO_HEIGHT), fill="#f6efe5")
    shift = int((1 - math.cos(progress * math.pi)) * 34)
    draw.ellipse((880 - shift, 42, 1220 - shift, 382), fill=palette["soft"])
    draw.ellipse((30, 468 - shift // 3, 300, 738 - shift // 3), fill=palette["mint"])
    draw.rounded_rectangle((918 + shift // 2, 110, 1128 + shift // 2, 154), radius=22, fill="#efe2d1")
    draw.rounded_rectangle((968 - shift // 3, 172, 1182 - shift // 3, 214), radius=20, fill="#ffffff")
    draw.rounded_rectangle((84, 82, 240, 118), radius=18, fill="#ffffff")
    accent_width = int(220 + 40 * math.sin((progress + index * 0.15) * math.pi))
    draw.rounded_rectangle((72, 640, 72 + accent_width, 652), radius=6, fill=palette["accent"])


def _draw_top_banner(
    draw: ImageDraw.ImageDraw,
    title: str,
    index: int,
    total: int,
    title_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
) -> None:
    draw.rounded_rectangle((72, 58, 254, 102), radius=22, fill=palette["soft"])
    draw.text((96, 69), "AI 教学视频", fill=palette["accent"], font=meta_font)
    draw.text((72, 126), title, fill=palette["ink"], font=title_font)
    footer = f"第 {index + 1} 幕 / 共 {total} 幕"
    draw.text((72, 664), footer, fill="#8e7764", font=meta_font)
    draw.text((968, 664), "字幕高亮 · 课件式转场", fill="#8e7764", font=meta_font)


def _draw_board(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], palette: dict) -> None:
    draw.rounded_rectangle(box, radius=40, fill=palette["board"], outline="#e7d7c6", width=2)
    draw.rounded_rectangle((box[0] + 24, box[1] + 24, box[2] - 24, box[1] + 36), radius=6, fill=palette["soft"])


def _draw_cover_layout(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    question: str,
    scene: VideoScene,
    heading_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
) -> None:
    draw.text((box[0] + 54, box[1] + 58), scene["title"], fill=palette["accent"], font=heading_font)
    draw.text((box[0] + 56, box[1] + 128), "本节题目", fill="#8b6f58", font=meta_font)
    draw.multiline_text(
        (box[0] + 56, box[1] + 168),
        "\n".join(_wrap_text(question, 24)[:4]),
        fill=palette["ink"],
        font=body_font,
        spacing=12,
    )
    draw.rounded_rectangle((box[0] + 714, box[1] + 80, box[2] - 56, box[1] + 320), radius=32, fill=palette["soft"])
    draw.text((box[0] + 756, box[1] + 126), "课堂主线", fill=palette["accent"], font=meta_font)
    draw.multiline_text(
        (box[0] + 756, box[1] + 168),
        "\n".join(_wrap_text(scene["narration"], 18)[:5]),
        fill=palette["ink"],
        font=body_font,
        spacing=12,
    )


def _draw_split_layout(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    question: str,
    scene: VideoScene,
    heading_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
    progress: float,
) -> None:
    draw.text((box[0] + 56, box[1] + 48), scene["title"], fill=palette["accent"], font=heading_font)
    left_box = (box[0] + 52, box[1] + 112, box[0] + 500, box[1] + 320)
    right_box = (box[0] + 544, box[1] + 112, box[2] - 52, box[1] + 320)
    draw.rounded_rectangle(left_box, radius=28, fill="#ffffff")
    draw.rounded_rectangle(right_box, radius=28, fill=palette["soft"])
    draw.text((left_box[0] + 28, left_box[1] + 24), "题目聚焦", fill="#8b6f58", font=meta_font)
    draw.text((right_box[0] + 28, right_box[1] + 24), "讲解推进", fill=palette["accent"], font=meta_font)
    draw.multiline_text((left_box[0] + 28, left_box[1] + 62), "\n".join(_wrap_text(question, 17)[:5]), fill=palette["ink"], font=body_font, spacing=10)
    draw.multiline_text(
        (right_box[0] + 28, right_box[1] + 62),
        "\n".join(_wrap_text(scene["narration"], 17)[:5]),
        fill=palette["ink"],
        font=body_font,
        spacing=10,
    )
    _draw_progress_steps(draw, box, scene["subtitle_segments"], progress, meta_font, palette)


def _draw_focus_layout(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    question: str,
    scene: VideoScene,
    heading_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
    progress: float,
) -> None:
    draw.text((box[0] + 56, box[1] + 50), scene["title"], fill=palette["accent"], font=heading_font)
    focus_box = (box[0] + 54, box[1] + 118, box[2] - 54, box[1] + 292)
    draw.rounded_rectangle(focus_box, radius=28, fill="#ffffff")
    draw.text((focus_box[0] + 30, focus_box[1] + 26), "本幕讲解", fill="#8b6f58", font=meta_font)
    draw.multiline_text(
        (focus_box[0] + 30, focus_box[1] + 70),
        "\n".join(_wrap_text(scene["narration"], 32)[:3]),
        fill=palette["ink"],
        font=body_font,
        spacing=12,
    )

    note_box = (box[0] + 54, box[1] + 326, box[0] + 470, box[1] + 524)
    question_box = (box[0] + 512, box[1] + 326, box[2] - 54, box[1] + 524)
    draw.rounded_rectangle(note_box, radius=28, fill=palette["soft"])
    draw.rounded_rectangle(question_box, radius=28, fill="#fff7ee")
    draw.text((note_box[0] + 24, note_box[1] + 22), "课堂提示", fill=palette["accent"], font=meta_font)
    draw.text((question_box[0] + 24, question_box[1] + 22), "回到题目", fill="#8b6f58", font=meta_font)
    draw.multiline_text((note_box[0] + 24, note_box[1] + 58), "\n".join(_wrap_text("跟着字幕节奏，一句一句带学生理解思路。", 15)), fill=palette["ink"], font=body_font, spacing=10)
    draw.multiline_text((question_box[0] + 24, question_box[1] + 58), "\n".join(_wrap_text(question, 20)[:4]), fill=palette["ink"], font=body_font, spacing=10)
    _draw_progress_steps(draw, box, scene["subtitle_segments"], progress, meta_font, palette)


def _draw_summary_layout(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    question: str,
    scene: VideoScene,
    heading_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
) -> None:
    draw.text((box[0] + 56, box[1] + 54), scene["title"], fill=palette["accent"], font=heading_font)
    draw.text((box[0] + 56, box[1] + 118), "本节课回顾", fill="#8b6f58", font=meta_font)
    draw.multiline_text((box[0] + 56, box[1] + 154), "\n".join(_wrap_text(scene["narration"], 30)[:4]), fill=palette["ink"], font=body_font, spacing=12)
    draw.rounded_rectangle((box[0] + 54, box[1] + 298, box[2] - 54, box[1] + 520), radius=32, fill="#ffffff")
    draw.text((box[0] + 84, box[1] + 334), "课后延伸", fill=palette["accent"], font=meta_font)
    draw.multiline_text(
        (box[0] + 84, box[1] + 376),
        "\n".join(_wrap_text(f"请再试着独立完成一道同类题：{question}", 36)[:3]),
        fill=palette["ink"],
        font=body_font,
        spacing=12,
    )


def _draw_progress_steps(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    segments: list[str],
    progress: float,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
) -> None:
    start_y = box[1] + 350
    active_index = min(int(progress * max(len(segments), 1)), max(len(segments) - 1, 0))
    for index, segment in enumerate(segments[:4]):
        top = start_y + index * 46
        fill = palette["accent"] if index <= active_index else "#efe3d7"
        text_fill = "#fffaf4" if index <= active_index else "#8b6f58"
        draw.rounded_rectangle((box[0] + 56, top, box[2] - 56, top + 34), radius=17, fill=fill)
        draw.text((box[0] + 76, top + 7), segment, fill=text_fill, font=meta_font)


def _draw_subtitle_panel(
    draw: ImageDraw.ImageDraw,
    scene: VideoScene,
    progress: float,
    subtitle_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    meta_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    palette: dict,
) -> None:
    panel_box = (120, 564, 1160, 646)
    draw.rounded_rectangle(panel_box, radius=28, fill="#2a211a")
    draw.text((150, 584), "字幕高亮", fill="#d8c1aa", font=meta_font)
    segments = scene["subtitle_segments"]
    active_index = min(int(progress * max(len(segments), 1)), max(len(segments) - 1, 0))
    cursor_x = 150
    subtitle_y = 610
    for index, segment in enumerate(segments):
        fill = palette["accent"] if index == active_index else ("#f3e7dc" if index < active_index else "#aa9380")
        draw.text((cursor_x, subtitle_y), segment, fill=fill, font=subtitle_font)
        bbox = draw.textbbox((cursor_x, subtitle_y), segment, font=subtitle_font)
        cursor_x = bbox[2] + 18


def _transition_offset(layout: str, progress: float) -> int:
    transition_ratio = min(TRANSITION_SECONDS * VIDEO_FPS, 14)
    enter_progress = min(progress * VIDEO_FPS / max(transition_ratio, 1), 1.0)
    if layout == "focus":
        return int((1 - enter_progress) * 140)
    if layout == "summary":
        return int((1 - enter_progress) * -90)
    return int((1 - enter_progress) * 110)


def _transition_lift(progress: float) -> int:
    transition_ratio = min(TRANSITION_SECONDS * VIDEO_FPS, 14)
    enter_progress = min(progress * VIDEO_FPS / max(transition_ratio, 1), 1.0)
    return int((1 - enter_progress) * 22)


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_candidates = []
    if os.name == "nt":
        if bold:
            font_candidates.extend([
                r"C:\Windows\Fonts\msyhbd.ttc",
                r"C:\Windows\Fonts\simhei.ttf",
            ])
        font_candidates.extend([
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simsun.ttc",
        ])

    for candidate in font_candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue

    return ImageFont.load_default()


def _wrap_text(text: str, width: int) -> list[str]:
    normalized = " ".join(str(text).split())
    if not normalized:
        return [""]
    return textwrap.wrap(normalized, width=width, break_long_words=True, break_on_hyphens=False)


def _merge_audio_segments(output_path: Path, audio_segments: list[AudioSegment]) -> None:
    with wave.open(str(output_path), "wb") as output_wav:
        output_wav.setnchannels(1)
        output_wav.setsampwidth(2)
        output_wav.setframerate(22050)

        for segment in audio_segments:
            with wave.open(str(segment.path), "rb") as segment_wav:
                output_wav.writeframes(segment_wav.readframes(segment_wav.getnframes()))


def _compose_mp4(output_path: Path, frames_dir: Path, audio_path: Path) -> None:
    ffmpeg_executable = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg_executable,
        "-y",
        "-framerate",
        str(VIDEO_FPS),
        "-i",
        str(frames_dir / "frame-%05d.png"),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
