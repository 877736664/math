"""教材范围与知识点序列化相关的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_EDITION = "rjb"
DEFAULT_SUBJECT = "math"
DEFAULT_GRADE = 3
DEFAULT_SEMESTER = "下册"
SEMESTER_OPTIONS = ("上册", "下册")
GRADE_OPTIONS = (1, 2, 3, 4, 5, 6)
DEFAULT_SUBJECT_URL = "https://www.dzkbw.org/subject/rjb/shuxue.html"

_GRADE_PAGE_SLUGS = {
    1: "yinianji",
    2: "ernianji",
    3: "sannianji",
    4: "sinianji",
    5: "wunianji",
    6: "liunianji",
}


@dataclass(frozen=True)
class TextbookCatalogItem:
    """教材目录项，供前端展示可选教材列表。"""

    edition: str
    edition_label: str
    subject: str
    subject_label: str
    publisher: str
    grades: tuple[int, ...]
    semesters: tuple[str, ...]
    source_label: str
    source_url: str

    @property
    def label(self) -> str:
        return f"{self.edition_label}小学{self.subject_label}"


@dataclass(frozen=True)
class TextbookScope:
    """一次请求实际命中的教材范围。"""

    edition: str
    edition_label: str
    subject: str
    subject_label: str
    publisher: str
    grade: int
    semester: str
    source_label: str
    source_url: str

    @property
    def label(self) -> str:
        return f"{self.edition_label}小学{self.subject_label}·{self.grade}年级{self.semester}"


@dataclass(frozen=True)
class KnowledgeDocument:
    """统一的知识片段结构，RAGFlow 检索结果会被映射成这个模型。"""

    doc_id: str
    title: str
    edition: str
    edition_label: str
    subject: str
    subject_label: str
    publisher: str
    grades: tuple[int, ...]
    semesters: tuple[str, ...]
    unit_title: str
    concept_tags: tuple[str, ...]
    keywords: tuple[str, ...]
    summary: str
    key_points: tuple[str, ...]
    example: str
    practice_question: str
    source_label: str
    source_url: str

    @property
    def curriculum_label(self) -> str:
        return f"{self.edition_label}{self.subject_label} {self._grade_text()} {self._semester_text()} · {self.unit_title}"

    def _grade_text(self) -> str:
        if len(self.grades) == 1:
            return f"{self.grades[0]}年级"
        return f"{self.grades[0]}-{self.grades[-1]}年级"

    def _semester_text(self) -> str:
        if len(self.semesters) == 1:
            return self.semesters[0]
        return "上下册"


SUPPORTED_TEXTBOOKS: tuple[TextbookCatalogItem, ...] = (
    TextbookCatalogItem(
        edition=DEFAULT_EDITION,
        edition_label="人教版",
        subject=DEFAULT_SUBJECT,
        subject_label="数学",
        publisher="人民教育出版社",
        grades=GRADE_OPTIONS,
        semesters=SEMESTER_OPTIONS,
        source_label="电子课本网",
        source_url=DEFAULT_SUBJECT_URL,
    ),
)


def _grade_url(grade: int) -> str:
    slug = _GRADE_PAGE_SLUGS.get(grade, _GRADE_PAGE_SLUGS[DEFAULT_GRADE])
    return f"https://www.dzkbw.org/grade/rjb/{slug}.html"


def resolve_textbook_scope(grade: int, textbook: dict | None = None) -> TextbookScope:
    """根据年级和可选教材参数，得到后续检索与展示使用的教材范围。"""

    item = SUPPORTED_TEXTBOOKS[0]
    requested_edition = str((textbook or {}).get("edition", item.edition)).strip().lower()
    requested_subject = str((textbook or {}).get("subject", item.subject)).strip().lower()
    requested_semester = str((textbook or {}).get("semester", DEFAULT_SEMESTER)).strip()

    if requested_edition != item.edition:
        requested_edition = item.edition
    if requested_subject != item.subject:
        requested_subject = item.subject
    if requested_semester not in item.semesters:
        requested_semester = DEFAULT_SEMESTER
    if grade not in item.grades:
        grade = DEFAULT_GRADE

    return TextbookScope(
        edition=requested_edition,
        edition_label=item.edition_label,
        subject=requested_subject,
        subject_label=item.subject_label,
        publisher=item.publisher,
        grade=grade,
        semester=requested_semester,
        source_label=item.source_label,
        source_url=_grade_url(grade),
    )


def get_textbook_catalog() -> dict:
    """返回教材目录与默认值配置。"""

    return {
        "defaults": {
            "edition": DEFAULT_EDITION,
            "subject": DEFAULT_SUBJECT,
            "grade": DEFAULT_GRADE,
            "semester": DEFAULT_SEMESTER,
        },
        "textbooks": [
            {
                "edition": item.edition,
                "edition_label": item.edition_label,
                "subject": item.subject,
                "subject_label": item.subject_label,
                "publisher": item.publisher,
                "label": item.label,
                "grades": list(item.grades),
                "semesters": list(item.semesters),
                "source_label": item.source_label,
                "source_url": item.source_url,
            }
            for item in SUPPORTED_TEXTBOOKS
        ],
    }


def serialize_textbook_scope(scope: TextbookScope) -> dict:
    """把教材范围对象转成接口响应可直接序列化的字典。"""

    return {
        "edition": scope.edition,
        "edition_label": scope.edition_label,
        "subject": scope.subject,
        "subject_label": scope.subject_label,
        "publisher": scope.publisher,
        "grade": scope.grade,
        "semester": scope.semester,
        "label": scope.label,
        "source_label": scope.source_label,
        "source_url": scope.source_url,
    }


def serialize_knowledge_points(documents: list[KnowledgeDocument]) -> list[dict]:
    """把知识片段列表转成前端使用的知识点结构。"""

    return [
        {
            "doc_id": document.doc_id,
            "title": document.title,
            "unit_title": document.unit_title,
            "curriculum_label": document.curriculum_label,
            "summary": document.summary,
            "example": document.example,
            "concept_tags": list(document.concept_tags),
            "source_label": document.source_label,
            "source_url": document.source_url,
        }
        for document in documents
    ]
