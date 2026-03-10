from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    doc_id: str
    title: str
    grades: tuple[int, ...]
    keywords: tuple[str, ...]
    summary: str
    key_points: tuple[str, ...]
    example: str
    practice_question: str


KNOWLEDGE_BASE: tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="word_problem_strategy",
        title="应用题通用拆题法",
        grades=(1, 2, 3, 4, 5, 6),
        keywords=("应用题", "题意", "步骤", "解题", "分析", "条件", "问题"),
        summary="先找已知条件和所求问题，再判断用什么运算，最后检查结果是否符合题意。",
        key_points=(
            "圈出题目中的数字、单位和关键词。",
            "判断是在求总数、剩余、平均分、几组相同数量，还是图形量。",
            "算完以后把答案代回原题读一遍，确认合理。",
        ),
        example="小明有12颗糖，平均分给3个同学，关键词是“平均分”，通常用除法。",
        practice_question="文具盒里有18支铅笔，平均分给3个同学，每人几支？",
    ),
    KnowledgeDocument(
        doc_id="addition",
        title="加法：求一共多少",
        grades=(1, 2, 3),
        keywords=("加法", "一共", "总共", "合起来", "共有", "+", "又来"),
        summary="当题目在问合起来一共有多少时，通常把几个部分相加。",
        key_points=(
            "“一共”“总共”“合起来”常常提示用加法。",
            "把同单位的数量相加。",
            "结果要带上原来的单位。",
        ),
        example="书架上有8本故事书，又放上7本，一共有15本。",
        practice_question="盒子里有9个苹果，又放进去6个，现在一共有多少个苹果？",
    ),
    KnowledgeDocument(
        doc_id="subtraction",
        title="减法：求还剩多少或相差多少",
        grades=(1, 2, 3),
        keywords=("减法", "还剩", "剩下", "拿走", "用去", "相差", "-", "少"),
        summary="当题目在问剩余数量或两个数量相差多少时，通常用减法。",
        key_points=(
            "“还剩”“剩下”常常提示从总数里减去一部分。",
            "“相差多少”是把较大的数减去较小的数。",
            "答案要说明剩下的是什么。",
        ),
        example="有15朵花，送走4朵，还剩11朵。",
        practice_question="一共有20张贴纸，送给同学8张，还剩多少张？",
    ),
    KnowledgeDocument(
        doc_id="multiplication",
        title="乘法：几个几相加",
        grades=(2, 3, 4),
        keywords=("乘法", "每", "几组", "几个几", "×", "x", "共多少"),
        summary="当题目出现几个相同数量时，可以用乘法更快地计算总数。",
        key_points=(
            "先找每份的数量，再找有几份。",
            "每份数量 × 份数 = 总数。",
            "乘完后检查单位是否正确。",
        ),
        example="每盒有6支蜡笔，4盒一共有24支蜡笔。",
        practice_question="每排有5盆花，一共4排，一共有多少盆花？",
    ),
    KnowledgeDocument(
        doc_id="division_equal_share",
        title="除法：平均分问题",
        grades=(2, 3, 4),
        keywords=("除法", "平均分", "平分", "均分", "每人", "每份", "÷", "/"),
        summary="当总数被平均分成几份，要求每份多少时，一般用除法。",
        key_points=(
            "总数 ÷ 份数 = 每份数量。",
            "关键词常见有“平均分”“每人”“每份”。",
            "算完后可以用“每份数量 × 份数”反过来检查。",
        ),
        example="12颗糖平均分给3个同学，每人4颗。",
        practice_question="24支铅笔平均分给6个小朋友，每人分到几支？",
    ),
    KnowledgeDocument(
        doc_id="rectangle_area",
        title="长方形面积公式",
        grades=(3, 4, 5),
        keywords=("长方形", "面积", "长", "宽", "平方厘米", "平方分米"),
        summary="长方形的面积等于长乘宽，表示平面一共覆盖了多少个面积单位。",
        key_points=(
            "面积公式：长 × 宽。",
            "面积单位常见有平方厘米、平方分米、平方米。",
            "不要和周长公式混淆。",
        ),
        example="长8厘米、宽5厘米的长方形，面积是40平方厘米。",
        practice_question="一个长方形长9厘米、宽4厘米，它的面积是多少平方厘米？",
    ),
    KnowledgeDocument(
        doc_id="rectangle_perimeter",
        title="长方形周长公式",
        grades=(3, 4, 5),
        keywords=("长方形", "周长", "长", "宽", "边长", "厘米"),
        summary="长方形的周长是四条边长度的总和，可以用（长 + 宽）× 2。",
        key_points=(
            "周长公式：（长 + 宽）× 2。",
            "周长表示一圈边线的总长度。",
            "周长单位是长度单位，不是平方单位。",
        ),
        example="长8厘米、宽5厘米的长方形，周长是26厘米。",
        practice_question="一个长方形长7厘米、宽3厘米，它的周长是多少厘米？",
    ),
    KnowledgeDocument(
        doc_id="fraction_meaning",
        title="分数的意义",
        grades=(3, 4, 5),
        keywords=("分数", "几分之几", "/", "平均分", "分成", "表示", "意义"),
        summary="分数表示把一个整体平均分成若干份，取其中的几份。",
        key_points=(
            "分母表示平均分成几份。",
            "分子表示取了其中几份。",
            "必须先强调“平均分”。",
        ),
        example="3/4 表示把一个整体平均分成4份，取其中的3份。",
        practice_question="把一个蛋糕平均分成5份，取其中2份，可以用哪个分数表示？",
    ),
    KnowledgeDocument(
        doc_id="fraction_decimal_equivalence",
        title="分数和小数的对应关系",
        grades=(4, 5, 6),
        keywords=("小数", "分数", "相等", "0.5", "0.25", "1/2", "1/4", "比较"),
        summary="有些小数和分数表示的是同一个数量，例如0.5和1/2都表示一半。",
        key_points=(
            "0.5 = 5/10 = 1/2。",
            "比较时要看它们是否表示同一个整体中的同样大小。",
            "可以借助图形或平均分来理解。",
        ),
        example="把一个圆平均分成2份，取1份是1/2，也可以写成0.5。",
        practice_question="为什么0.25和1/4相等？请你试着用平均分来解释。",
    ),
)


DEFAULT_DOC_IDS = ("word_problem_strategy", "addition", "division_equal_share")


def retrieve_knowledge(question: str, grade: int, top_k: int = 3) -> list[KnowledgeDocument]:
    normalized_question = question.lower()
    scored_docs: list[tuple[float, KnowledgeDocument]] = []

    for document in KNOWLEDGE_BASE:
        score = 0.0

        if grade in document.grades:
            score += 1.0

        for keyword in document.keywords:
            if keyword.lower() in normalized_question:
                score += 3.0 if len(keyword) > 1 else 1.0

        score += _pattern_bonus(document.doc_id, normalized_question)

        if document.doc_id == "word_problem_strategy":
            score += 0.3

        if score > 0:
            scored_docs.append((score, document))

    scored_docs.sort(key=lambda item: (-item[0], item[1].title))
    documents = [document for _, document in scored_docs[:top_k]]

    if documents:
        return documents

    return [document for document in KNOWLEDGE_BASE if document.doc_id in DEFAULT_DOC_IDS][:top_k]


def render_retrieved_context(documents: list[KnowledgeDocument]) -> str:
    sections: list[str] = []
    for index, document in enumerate(documents, start=1):
        points = "\n".join(f"- {point}" for point in document.key_points)
        sections.append(
            f"[知识{index}] {document.title}\n"
            f"适用年级：{_format_grades(document.grades)}\n"
            f"摘要：{document.summary}\n"
            f"关键要点：\n{points}\n"
            f"示例：{document.example}"
        )
    return "\n\n".join(sections)


def solve_question_with_docs(question: str, documents: list[KnowledgeDocument]) -> dict | None:
    doc_ids = {document.doc_id for document in documents}
    numbers = _extract_numbers(question)

    if "rectangle_area" in doc_ids and "面积" in question and len(numbers) >= 2:
        length, width = numbers[0], numbers[1]
        result = length * width
        return {
            "conclusion": f"面积是{_format_number(result)}。",
            "steps": [
                f"根据检索到的“长方形面积公式”，面积 = 长 × 宽。",
                f"把题目里的长 {_format_number(length)} 和宽 {_format_number(width)} 代入。",
                f"计算 {_format_number(length)} × {_format_number(width)} = {_format_number(result)}。",
                "最后记得把单位写成平方单位。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "rectangle_perimeter" in doc_ids and "周长" in question and len(numbers) >= 2:
        length, width = numbers[0], numbers[1]
        result = (length + width) * 2
        return {
            "conclusion": f"周长是{_format_number(result)}。",
            "steps": [
                "根据检索到的“长方形周长公式”，周长 = （长 + 宽）× 2。",
                f"先算 {_format_number(length)} + {_format_number(width)} = {_format_number(length + width)}。",
                f"再算 {_format_number(length + width)} × 2 = {_format_number(result)}。",
                "周长表示一圈的长度，所以单位还是普通长度单位。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "fraction_decimal_equivalence" in doc_ids and ("0.5" in question and "1/2" in question):
        return {
            "conclusion": "0.5 和 1/2 相等，它们都表示一半。",
            "steps": [
                "根据检索到的“分数和小数的对应关系”，0.5 表示五个十分之一。",
                "五个十分之一可以写成 5/10。",
                "把 5/10 约分后得到 1/2。",
                "所以 0.5 和 1/2 表示的是同一个数量。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "fraction_meaning" in doc_ids:
        fraction_match = re.search(r"(\d+)\s*/\s*(\d+)", question)
        if fraction_match and any(word in question for word in ("表示", "意义", "讲", "解释")):
            numerator = int(fraction_match.group(1))
            denominator = int(fraction_match.group(2))
            return {
                "conclusion": f"{numerator}/{denominator} 表示把一个整体平均分成 {denominator} 份，取其中的 {numerator} 份。",
                "steps": [
                    "根据检索到的“分数的意义”，先看分母。",
                    f"分母 {denominator} 表示把整体平均分成 {denominator} 份。",
                    f"分子 {numerator} 表示取其中的 {numerator} 份。",
                    "因此这个分数描述的是“平均分后取其中几份”。",
                ],
                "practice": _pick_practice_question(documents),
            }

    if "division_equal_share" in doc_ids and _contains_any(question, ("平均分", "平分", "均分", "每人", "每份")) and len(numbers) >= 2:
        total, parts = numbers[0], numbers[1]
        if parts == 0:
            return None

        quotient = total / parts
        label = "每人" if "每人" in question else "每份"

        if _is_close_to_integer(total) and _is_close_to_integer(parts) and int(total) % int(parts) == 0:
            return {
                "conclusion": f"{label}{_format_number(quotient)}。",
                "steps": [
                    "根据检索到的“平均分问题”，总数 ÷ 份数 = 每份数量。",
                    f"题目中的总数是 {_format_number(total)}，份数是 {_format_number(parts)}。",
                    f"计算 {_format_number(total)} ÷ {_format_number(parts)} = {_format_number(quotient)}。",
                    f"所以{label}{_format_number(quotient)}。",
                ],
                "practice": _pick_practice_question(documents),
            }

        return {
            "conclusion": f"{label}{_format_number(quotient)}。",
            "steps": [
                "根据检索到的“平均分问题”，用总数除以份数。",
                f"计算 {_format_number(total)} ÷ {_format_number(parts)} = {_format_number(quotient)}。",
                "如果题目要求按小数表示，就直接写出商；如果要求按余数表示，还需要结合题意判断。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "multiplication" in doc_ids and "每" in question and len(numbers) >= 2:
        each_count, group_count = numbers[0], numbers[1]
        result = each_count * group_count
        return {
            "conclusion": f"一共是{_format_number(result)}。",
            "steps": [
                "根据检索到的“几个几相加”，先找每份数量和份数。",
                f"题目里每份是 {_format_number(each_count)}，一共有 {_format_number(group_count)} 份。",
                f"用乘法计算：{_format_number(each_count)} × {_format_number(group_count)} = {_format_number(result)}。",
                "所以总数是这个乘积。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "subtraction" in doc_ids and _contains_any(question, ("还剩", "剩下", "拿走", "用去", "少")) and len(numbers) >= 2:
        first_number, second_number = numbers[0], numbers[1]
        result = first_number - second_number
        return {
            "conclusion": f"结果是{_format_number(result)}。",
            "steps": [
                "根据检索到的“减法”知识点，这是在求剩余或减少后的数量。",
                f"用原来的数量 {_format_number(first_number)} 减去减少的数量 {_format_number(second_number)}。",
                f"计算 {_format_number(first_number)} - {_format_number(second_number)} = {_format_number(result)}。",
                "最后带回题目看看是不是在求“还剩多少”。",
            ],
            "practice": _pick_practice_question(documents),
        }

    if "addition" in doc_ids and _contains_any(question, ("一共", "总共", "合起来", "共有", "又")) and len(numbers) >= 2:
        first_number, second_number = numbers[0], numbers[1]
        result = first_number + second_number
        return {
            "conclusion": f"结果是{_format_number(result)}。",
            "steps": [
                "根据检索到的“加法”知识点，这是在求合起来一共有多少。",
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
    document_titles = "、".join(document.title for document in documents)
    solution = solve_question_with_docs(question, documents)

    if solution:
        steps = "\n".join(f"{index}. {step}" for index, step in enumerate(solution["steps"], start=1))
        return (
            f"已检索知识点：{document_titles}\n\n"
            f"结论：{solution['conclusion']}\n\n"
            f"解题步骤：\n{steps}\n\n"
            f"同类练习：{solution['practice']}"
        )

    summaries = "\n".join(
        f"- {document.title}：{document.summary}" for document in documents
    )
    return (
        f"已检索知识点：{document_titles}\n\n"
        f"结论：这道题建议先按小学{grade}年级的应用题方法拆题，再决定具体算法。\n\n"
        f"可参考的知识摘要：\n{summaries}\n\n"
        "解题步骤：\n"
        "1. 先圈出题目中的数字、单位和关键词。\n"
        "2. 根据关键词判断是加法、减法、乘法、除法还是图形公式。\n"
        "3. 按检索到的知识点列式并计算。\n"
        "4. 把结果代回原题检查是否合理。\n\n"
        f"同类练习：{_pick_practice_question(documents)}"
    )


def build_rag_fallback_assets(
    grade: int,
    question: str,
    documents: list[KnowledgeDocument],
    game: dict,
) -> dict:
    answer = build_rag_fallback_answer(grade, question, documents)
    solution = solve_question_with_docs(question, documents)
    lead_document = documents[0]

    if solution:
        video_steps = [
            f"开场：这道题先从检索到的《{lead_document.title}》入手。",
            *solution["steps"][:3],
            f"收尾：布置同类练习——{solution['practice']}",
        ]
    else:
        video_steps = [
            f"开场：回顾知识点《{lead_document.title}》。",
            "步骤1：圈出题目里的数字、单位和关键词。",
            "步骤2：根据关键词匹配到正确的知识点和公式。",
            "步骤3：列式计算，并把结果代回原题检查。",
            f"收尾：练习同类型题目——{_pick_practice_question(documents)}",
        ]

    slides = [
        {
            "title": "封面",
            "bullet_points": [f"小学{grade}年级数学讲解", question],
        },
        {
            "title": "检索到的知识点",
            "bullet_points": [document.title for document in documents[:3]],
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
        {
            "title": "课堂总结",
            "bullet_points": [
                f"遇到这类题优先想到《{lead_document.title}》",
                "先检索相关知识，再按步骤解题。",
            ],
        },
    ]

    return {
        "answer": answer,
        "video": {
            "title": f"小学{grade}年级数学微课：基于RAG的讲解",
            "script_steps": video_steps[:6],
        },
        "ppt": {
            "title": f"小学{grade}年级数学检索式讲解课件",
            "slides": slides,
        },
        "game": game,
    }


def _pattern_bonus(doc_id: str, question: str) -> float:
    if doc_id == "division_equal_share" and _contains_any(question, ("平均分", "平分", "均分", "每人", "每份")):
        return 4.0
    if doc_id == "multiplication" and "每" in question and _contains_any(question, ("一共", "共", "多少", "几组")):
        return 3.5
    if doc_id == "addition" and _contains_any(question, ("一共", "总共", "合起来", "共有")):
        return 3.0
    if doc_id == "subtraction" and _contains_any(question, ("还剩", "剩下", "相差", "拿走", "用去")):
        return 3.0
    if doc_id == "rectangle_area" and "长方形" in question and "面积" in question:
        return 4.0
    if doc_id == "rectangle_perimeter" and "长方形" in question and "周长" in question:
        return 4.0
    if doc_id == "fraction_meaning" and re.search(r"\d+\s*/\s*\d+", question):
        return 3.0
    if doc_id == "fraction_decimal_equivalence" and (
        ("0.5" in question and "1/2" in question) or ("0.25" in question and "1/4" in question)
    ):
        return 4.0
    return 0.0


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


def _format_grades(grades: tuple[int, ...]) -> str:
    return "、".join(f"{grade}年级" for grade in grades)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _is_close_to_integer(value: float) -> bool:
    return abs(value - round(value)) < 1e-9


def _format_number(value: float) -> str:
    if _is_close_to_integer(value):
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")
