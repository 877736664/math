"""HTTP 接口使用的请求体与响应体模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class TextbookRequest(BaseModel):
    edition: str = Field(default="rjb", min_length=1, max_length=32)
    subject: str = Field(default="math", min_length=1, max_length=32)
    semester: str | None = Field(default="下册", max_length=8)


class ConversationMessageRequest(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=4000)


class Slide(BaseModel):
    title: str
    bullet_points: list[str]


class VideoScene(BaseModel):
    title: str
    narration: str
    duration_seconds: float


class VideoOutlineAsset(BaseModel):
    title: str
    script_steps: list[str]


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


class TeachingVideoAsset(BaseModel):
    title: str
    summary: str
    download_path: str
    duration_seconds: float
    video_spec: dict
    scenes: list[VideoScene]


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


class OnlineSearchResultPayload(BaseModel):
    source: str
    title: str
    summary: str
    url: str


class TeachingPreferencesRequest(BaseModel):
    teaching_goal: str | None = Field(default="", max_length=120)
    student_level: str | None = Field(default="班级标准水平", max_length=40)
    teaching_style: str | None = Field(default="老师课堂版", max_length=40)
    common_misconceptions: str | None = Field(default="", max_length=240)
    explanation_depth: str | None = Field(default="标准", max_length=20)


class QARequest(BaseModel):
    grade: int | None = Field(default=None, ge=1, le=6)
    question: str = Field(min_length=1, max_length=4000)
    messages: list[ConversationMessageRequest] = Field(default_factory=list, max_length=24)
    textbook: TextbookRequest | None = None
    teaching_preferences: TeachingPreferencesRequest | None = None
    animation_seed: str | None = Field(default=None, max_length=64)
    network_enabled: bool = False


class QAResponse(BaseModel):
    answer: str
    textbook: TextbookScopePayload
    knowledge_points: list[KnowledgePointPayload]
    online_results: list[OnlineSearchResultPayload] = Field(default_factory=list)


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


class LessonAssetsResponse(BaseModel):
    answer: str
    video: VideoOutlineAsset
    ppt: PPTAsset
    game: GameAsset
    textbook: TextbookScopePayload
    knowledge_points: list[KnowledgePointPayload]
    online_results: list[OnlineSearchResultPayload] = Field(default_factory=list)


class TextbookCatalogResponse(BaseModel):
    defaults: TextbookDefaults
    textbooks: list[TextbookOption]


class PPTExportRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slides: list[Slide] = Field(min_length=1, max_length=30)
