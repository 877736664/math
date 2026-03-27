"""RAGFlow 检索适配层，以及基于检索结果的兜底讲解逻辑。"""

from __future__ import annotations

import json
import logging
import os
import re
from html import unescape
from urllib import error, request

from app.textbook_repository import KnowledgeDocument, TextbookScope, resolve_textbook_scope


logger = logging.getLogger(__name__)

def _ragflow_base_url() -> str:
    return os.getenv("RAGFLOW_BASE_URL", "").strip().rstrip("/")


def _ragflow_api_key() -> str:
    return os.getenv("RAGFLOW_API_KEY", "").strip()


def _ragflow_dataset_ids() -> list[str]:
    raw = os.getenv("RAGFLOW_DATASET_IDS", "")
    values = [item.strip() for item in re.split(r"[,\s]+", raw) if item.strip()]
    return list(dict.fromkeys(values))


def _ragflow_ready() -> bool:
    return bool(_ragflow_base_url() and _ragflow_api_key() and _ragflow_dataset_ids())


def _retrieve_knowledge_from_ragflow(
    question: str,
    grade: int,
    textbook: dict | None = None,
    top_k: int = 4,
) -> list[KnowledgeDocument]:
    """调用 RAGFlow 检索接口，并把返回 chunk 转成统一知识片段。"""

    if not _ragflow_ready():
        return []

    scope = resolve_textbook_scope(grade, textbook)
    payload = {
        "question": question,
        "dataset_ids": _ragflow_dataset_ids(),
        "page": 1,
        "page_size": max(top_k, int(os.getenv("RAGFLOW_PAGE_SIZE", "8"))),
        "similarity_threshold": float(os.getenv("RAGFLOW_SIMILARITY_THRESHOLD", "0.2")),
        "vector_similarity_weight": float(os.getenv("RAGFLOW_VECTOR_SIMILARITY_WEIGHT", "0.3")),
        "top_k": max(top_k, int(os.getenv("RAGFLOW_TOP_K", "8"))),
        "keyword": os.getenv("RAGFLOW_KEYWORD_SEARCH", "true").strip().lower() in {"1", "true", "yes", "on"},
        "highlight": False,
    }

    endpoint = f"{_ragflow_base_url()}/api/v1/retrieval"
    http_request = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_ragflow_api_key()}",
        },
        method="POST",
    )

    timeout = float(os.getenv("RAGFLOW_TIMEOUT", "15"))

    try:
        with request.urlopen(http_request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.warning("RAGFlow retrieval failed with HTTP %s: %s", exc.code, detail)
        return []
    except Exception:
        logger.exception("RAGFlow retrieval request failed")
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("RAGFlow retrieval returned non-JSON response")
        return []

    if data.get("code") != 0:
        logger.warning("RAGFlow retrieval returned error: %s", data.get("message", "unknown error"))
        return []

    chunks = data.get("data", {}).get("chunks", [])
    if not isinstance(chunks, list) or not chunks:
        return []

    documents = [_chunk_to_document(chunk, scope, grade, question) for chunk in chunks if isinstance(chunk, dict)]
    return documents[:top_k]


def _chunk_to_document(chunk: dict, scope: TextbookScope, grade: int, question: str) -> KnowledgeDocument:
    """把单条 RAGFlow chunk 映射成项目内部的 KnowledgeDocument。"""

    title = _coerce_text(
        chunk.get("document_name")
        or chunk.get("document_keyword")
        or chunk.get("doc_name")
        or chunk.get("kb_id")
        or "RAGFlow 检索结果"
    )
    content = _strip_html(_coerce_text(chunk.get("content") or chunk.get("highlight")))
    summary = _truncate_text(content or f"围绕“{question}”从 RAGFlow 检索到相关片段。", 180)
    key_points = _split_key_points(content)
    concept_tags = _infer_concept_tags(question, f"{title}\n{content}")
    doc_id = _coerce_text(chunk.get("id") or chunk.get("document_id") or title).replace(" ", "_")

    return KnowledgeDocument(
        doc_id=f"ragflow_{doc_id}",
        title=title,
        edition=scope.edition,
        edition_label=scope.edition_label,
        subject=scope.subject,
        subject_label=scope.subject_label,
        publisher=scope.publisher,
        grades=(grade,),
        semesters=(scope.semester,),
        unit_title="RAGFlow 检索结果",
        concept_tags=concept_tags,
        keywords=_extract_keywords(f"{title}\n{content}", question),
        summary=summary,
        key_points=key_points,
        example=_truncate_text(content or summary, 120),
        practice_question="请根据检索内容，换一个相近数字再说一遍解题思路。",
        source_label="RAGFlow",
        source_url=_ragflow_base_url(),
    )


def _build_ragflow_placeholder_document(scope: TextbookScope, grade: int, question: str) -> KnowledgeDocument:
    """当 RAGFlow 未返回有效结果时，生成一条排障用占位知识片段。"""

    return KnowledgeDocument(
        doc_id="ragflow_empty_result",
        title="RAGFlow 未返回有效检索结果",
        edition=scope.edition,
        edition_label=scope.edition_label,
        subject=scope.subject,
        subject_label=scope.subject_label,
        publisher=scope.publisher,
        grades=(grade,),
        semesters=(scope.semester,),
        unit_title="RAGFlow 检索结果",
        concept_tags=(),
        keywords=_extract_keywords(question),
        summary="当前问题没有从 RAGFlow 返回可用知识片段，请检查 API key、dataset_ids 或数据集内容。",
        key_points=(
            "确认 RAGFlow API key 是否有效。",
            "确认 dataset_ids 是否填写正确。",
            "确认知识库中已经导入并解析了相关教学内容。",
        ),
        example=question,
        practice_question="请先补齐 RAGFlow 数据集后再重试。",
        source_label="RAGFlow",
        source_url=_ragflow_base_url(),
    )


def _coerce_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(value or "")).strip()


def _truncate_text(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def _split_key_points(text: str) -> tuple[str, ...]:
    raw_parts = [part.strip(" -\t") for part in re.split(r"[\n。！？；;]", text) if part.strip()]
    points = tuple(_truncate_text(part, 80) for part in raw_parts[:3])
    return points or ("请结合检索内容进一步确认解题要点。",)


def _extract_keywords(*texts: str) -> tuple[str, ...]:
    seen: list[str] = []
    for text in texts:
        for token in re.findall(r"[\u4e00-\u9fff]{2,}|\d+(?:\.\d+)?", text or ""):
            if token not in seen:
                seen.append(token)
    return tuple(seen[:12])


def _infer_concept_tags(question: str, context: str) -> tuple[str, ...]:
    """从题目和检索文本中提取少量概念标签，供规则解题和动画生成复用。"""

    text = f"{question}\n{context}"
    tags: list[str] = []

    def add(tag: str):
        if tag not in tags:
            tags.append(tag)

    if any(word in text for word in ("平均分", "平分", "均分", "每人", "每份", "除法")):
        add("division_equal_share")
    if "长方形" in text and "面积" in text:
        add("rectangle_area")
    if "长方形" in text and "周长" in text:
        add("rectangle_perimeter")
    if re.search(r"\d+\s*/\s*\d+", text):
        add("fraction_meaning")
    if ("0.5" in text and "1/2" in text) or ("0.25" in text and "1/4" in text):
        add("fraction_decimal_equivalence")
    if any(word in text for word in ("一共", "总共", "合起来", "共有", "又")):
        add("addition")
    if any(word in text for word in ("还剩", "剩下", "拿走", "用去", "相差", "少")):
        add("subtraction")
    if any(word in text for word in ("每", "几组", "乘法", "×", "x", "X")):
        add("multiplication")

    return tuple(tags)


def retrieve_knowledge(question: str, grade: int, textbook: dict | None = None, top_k: int = 4) -> list[KnowledgeDocument]:
    """统一的知识检索入口；当前版本只走 RAGFlow。"""

    scope = resolve_textbook_scope(grade, textbook)
    documents = _retrieve_knowledge_from_ragflow(question, grade, textbook=textbook, top_k=top_k)
    if documents:
        return documents
    return [_build_ragflow_placeholder_document(scope, grade, question)]


def render_retrieved_context(documents: list[KnowledgeDocument]) -> str:
    """把知识片段整理成适合喂给 LLM 的上下文文本。"""

    sections: list[str] = []

    for index, document in enumerate(documents, start=1):
        points = "\n".join(f"- {point}" for point in document.key_points)
        sections.append(
            f"[知识{index}] {document.title}\n"
            f"教材定位：{document.curriculum_label}\n"
            f"适用册次：{_format_semesters(document.semesters)}\n"
            f"摘要：{document.summary}\n"
            f"关键要点：\n{points}\n"
            f"示例：{document.example}\n"
            f"来源：{document.source_label} {document.source_url}"
        )

    return "\n\n".join(sections)


def solve_question_with_docs(question: str, documents: list[KnowledgeDocument]) -> dict | None:
    """基于概念标签做少量规则化求解，供兜底答案和动画模块使用。"""

    concept_tags = {tag for document in documents for tag in document.concept_tags}
    numbers = _extract_numbers(question)

    if "rectangle_area" in concept_tags and "面积" in question and len(numbers) >= 2:
        length, width = numbers[0], numbers[1]
        result = length * width
        return {
            "conclusion": f"面积是{_format_number(result)}。",
            "steps": [
                "根据检索到的教材知识，长方形面积 = 长 × 宽。",
                f"把题目里的长 {_format_number(length)} 和宽 {_format_number(width)} 代入。",
                f"计算 {_format_number(length)} × {_format_number(width)} = {_format_number(result)}。",
                "最后记得把单位写成平方单位。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "rectangle_perimeter" in concept_tags and "周长" in question and len(numbers) >= 2:
        length, width = numbers[0], numbers[1]
        result = (length + width) * 2
        return {
            "conclusion": f"周长是{_format_number(result)}。",
            "steps": [
                "根据检索到的教材知识，长方形周长 = （长 + 宽）× 2。",
                f"先算 {_format_number(length)} + {_format_number(width)} = {_format_number(length + width)}。",
                f"再算 {_format_number(length + width)} × 2 = {_format_number(result)}。",
                "周长表示一圈的长度，所以单位还是普通长度单位。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "fraction_decimal_equivalence" in concept_tags and (("0.5" in question and "1/2" in question) or ("0.25" in question and "1/4" in question)):
        return {
            "conclusion": "这些分数和小数相等，因为它们表示的是同一个数量。",
            "steps": [
                "先把小数改写成十分之几或百分之几。",
                "再把对应的分数约分成最简形式。",
                "如果改写后的结果相同，就说明它们表示同一个数量。",
                "也可以借助平均分图形来验证。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "fraction_meaning" in concept_tags:
        fraction_match = re.search(r"(\d+)\s*/\s*(\d+)", question)
        if fraction_match and any(word in question for word in ("表示", "意义", "讲", "解释")):
            numerator = int(fraction_match.group(1))
            denominator = int(fraction_match.group(2))
            return {
                "conclusion": f"{numerator}/{denominator} 表示把一个整体平均分成 {denominator} 份，取其中的 {numerator} 份。",
                "steps": [
                    "先看分母，分母表示平均分成几份。",
                    f"这里分母是 {denominator}，表示平均分成 {denominator} 份。",
                    f"再看分子，分子 {numerator} 表示取其中的 {numerator} 份。",
                    "所以这个分数说的是“平均分后取其中几份”。",
                ],
                "practice": _pick_practice_question(documents),
            }

    if "division_equal_share" in concept_tags and _contains_any(question, ("平均分", "平分", "均分", "每人", "每份")) and len(numbers) >= 2:
        total, parts = numbers[0], numbers[1]
        if parts == 0:
            return None

        quotient = total / parts
        label = "每人" if "每人" in question else "每份"

        if _is_close_to_integer(total) and _is_close_to_integer(parts) and int(total) % int(parts) == 0:
            return {
                "conclusion": f"{label}{_format_number(quotient)}。",
                "steps": [
                    "这是平均分问题，用总数 ÷ 份数 = 每份数量。",
                    f"题目中的总数是 {_format_number(total)}，份数是 {_format_number(parts)}。",
                    f"计算 {_format_number(total)} ÷ {_format_number(parts)} = {_format_number(quotient)}。",
                    f"所以{label}{_format_number(quotient)}。",
                ],
                "practice": _pick_practice_question(documents),
            }

        return {
            "conclusion": f"{label}{_format_number(quotient)}。",
            "steps": [
                "先确定这是平均分，再用总数除以份数。",
                f"计算 {_format_number(total)} ÷ {_format_number(parts)} = {_format_number(quotient)}。",
                "如果题目要求写余数或小数，还要继续结合题意判断。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "multiplication" in concept_tags and "每" in question and len(numbers) >= 2:
        each_count, group_count = numbers[0], numbers[1]
        result = each_count * group_count
        return {
            "conclusion": f"一共是{_format_number(result)}。",
            "steps": [
                "先找每份数量和份数，再判断用乘法。",
                f"题目里每份是 {_format_number(each_count)}，一共有 {_format_number(group_count)} 份。",
                f"用乘法计算：{_format_number(each_count)} × {_format_number(group_count)} = {_format_number(result)}。",
                "所以总数就是这个乘积。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "subtraction" in concept_tags and _contains_any(question, ("还剩", "剩下", "拿走", "用去", "少")) and len(numbers) >= 2:
        first_number, second_number = numbers[0], numbers[1]
        result = first_number - second_number
        return {
            "conclusion": f"结果是{_format_number(result)}。",
            "steps": [
                "这是在求剩余或减少后的数量，所以用减法。",
                f"用原来的数量 {_format_number(first_number)} 减去减少的数量 {_format_number(second_number)}。",
                f"计算 {_format_number(first_number)} - {_format_number(second_number)} = {_format_number(result)}。",
                "最后把结果带回题目，看看是不是在求“还剩多少”。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "addition" in concept_tags and _contains_any(question, ("一共", "总共", "合起来", "共有", "又")) and len(numbers) >= 2:
        first_number, second_number = numbers[0], numbers[1]
        result = first_number + second_number
        return {
            "conclusion": f"结果是{_format_number(result)}。",
            "steps": [
                "这是在求合起来一共有多少，所以用加法。",
                f"把两个同单位的数量相加：{_format_number(first_number)} + {_format_number(second_number)}。",
                f"计算得到 {_format_number(result)}。",
                "答案要带上题目中的单位。",
            ],
            "practice": _pick_practice_question(documents),
        }

    expression_solution = _solve_explicit_expression(question)
    if expression_solution:
        return expression_solution

    return None


def build_rag_fallback_answer(grade: int, question: str, documents: list[KnowledgeDocument]) -> str:
    """在 LLM 不可用或生成失败时，输出一份带教材定位的 Markdown 答案。"""

    curriculum_labels = "\n".join(f"- {label}" for label in _collect_curriculum_labels(documents))
    document_titles = "\n".join(f"- {document.title}（{document.curriculum_label}）" for document in documents)
    solution = solve_question_with_docs(question, documents)

    if solution:
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(solution["steps"], start=1))
        return (
            "## 教材定位\n"
            f"{curriculum_labels}\n\n"
            "## 已检索知识点\n"
            f"{document_titles}\n\n"
            "## 结论\n"
            f"{solution['conclusion']}\n\n"
            "## 解题步骤\n"
            f"{steps}\n\n"
            "## 同类练习\n"
            f"{solution['practice']}"
        )

    summaries = "\n".join(f"- {document.title}：{document.summary}" for document in documents)
    return (
        "## 教材定位\n"
        f"{curriculum_labels}\n\n"
        "## 已检索知识点\n"
        f"{document_titles}\n\n"
        "## 结论\n"
        f"这道题建议先按小学{grade}年级对应教材的知识点拆题，再决定具体算法。\n\n"
        "## 可参考的知识摘要\n"
        f"{summaries}\n\n"
        "## 解题步骤\n"
        "1. 先圈出题目中的数字、单位和关键词。\n"
        "2. 根据关键词判断是加法、减法、乘法、除法还是图形公式。\n"
        "3. 对照教材知识点列式并计算。\n"
        "4. 把结果代回原题检查是否合理。\n\n"
        "## 同类练习\n"
        f"{_pick_practice_question(documents)}"
    )


def build_rag_fallback_assets(
    grade: int,
    question: str,
    documents: list[KnowledgeDocument],
    game: dict,
) -> dict:
    """基于检索结果构造视频、PPT、游戏推荐等素材的兜底结构。"""

    answer = build_rag_fallback_answer(grade, question, documents)
    solution = solve_question_with_docs(question, documents)
    lead_document = documents[0]
    curriculum_labels = _collect_curriculum_labels(documents)

    if solution:
        video_steps = [
            f"开场：先定位到教材知识《{lead_document.title}》。",
            *solution["steps"][:3],
            f"收尾：布置同类练习——{solution['practice']}",
        ]
    else:
        video_steps = [
            f"开场：回顾教材中的《{lead_document.title}》。",
            "步骤1：圈出题目里的数字、单位和关键词。",
            "步骤2：根据关键词匹配到正确的知识点和公式。",
            "步骤3：列式计算，并把结果代回原题检查。",
            f"收尾：练习同类型题目——{_pick_practice_question(documents)}",
        ]

    slides = [
        {
            "title": "封面",
            "bullet_points": [f"人教版小学数学 {grade}年级讲解", question],
        },
        {
            "title": "教材定位",
            "bullet_points": curriculum_labels[:4],
        },
        {
            "title": "检索到的知识点",
            "bullet_points": [document.title for document in documents[:4]],
        },
        {
            "title": "知识摘要",
            "bullet_points": [document.summary for document in documents[:3]],
        },
        {
            "title": "解题步骤",
            "bullet_points": solution["steps"][:4] if solution else list(lead_document.key_points[:3]),
        },
        {
            "title": "同类练习",
            "bullet_points": [_pick_practice_question(documents), "先说题型，再尝试自己列式。"],
        },
    ]

    return {
        "answer": answer,
        "video": {
            "title": f"人教版{grade}年级数学：{lead_document.title}",
            "script_steps": video_steps[:6],
        },
        "ppt": {
            "title": f"人教版{grade}年级数学：{lead_document.unit_title}",
            "slides": slides,
        },
        "game": game,
    }


def _collect_curriculum_labels(documents: list[KnowledgeDocument]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    for document in documents:
        if document.curriculum_label in seen:
            continue
        seen.add(document.curriculum_label)
        labels.append(document.curriculum_label)

    return labels


def _solve_explicit_expression(question: str) -> dict | None:
    expression_match = re.search(r"(\d+(?:\.\d+)?)\s*([+\-xX×*/÷])\s*(\d+(?:\.\d+)?)", question)
    if not expression_match:
        return None

    left = float(expression_match.group(1))
    operator = expression_match.group(2)
    right = float(expression_match.group(3))

    if operator == "+":
        result = left + right
        explanation = "加法表示把两个部分合起来。"
    elif operator == "-":
        result = left - right
        explanation = "减法表示求剩下多少或相差多少。"
    elif operator in ("x", "X", "×"):
        result = left * right
        explanation = "乘法表示几个相同数量相加。"
    else:
        if right == 0:
            return None
        result = left / right
        explanation = "除法表示平均分或包含关系。"

    return {
        "conclusion": f"结果是{_format_number(result)}。",
        "steps": [
            f"先识别算式：{_format_number(left)} {operator} {_format_number(right)}。",
            explanation,
            f"计算得到 {_format_number(result)}。",
            "把结果放回题目语境里再读一遍，确认合理。",
        ],
        "practice": "试着计算：9 + 6，并说一说为什么用加法。",
    }


def _extract_numbers(question: str) -> list[float]:
    return [float(token) for token in re.findall(r"\d+(?:\.\d+)?", question)]


def _pick_practice_question(documents: list[KnowledgeDocument]) -> str:
    for document in documents:
        if document.practice_question:
            return document.practice_question
    return "学校买来15支铅笔，平均分给3个同学，每人几支？"


def _format_semesters(semesters: tuple[str, ...]) -> str:
    return "、".join(semesters)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_close_to_integer(value: float) -> bool:
    return abs(value - round(value)) < 1e-9


def _format_number(value: float) -> str:
    if _is_close_to_integer(value):
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")
