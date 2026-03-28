"""教学风格与课堂化表达增强逻辑。"""

from __future__ import annotations

from app.repositories.textbook_repository import KnowledgeDocument


REQUIRED_ANSWER_SECTIONS = (
    "## 结论",
    "## 为什么这样做",
    "## 分步讲解",
    "## 常见错误",
    "## 课堂提问",
    "## 同类练习",
)


def normalize_teaching_preferences(preferences: dict | None = None) -> dict:
    """归一化前端传入的教学偏好。"""

    raw = preferences if isinstance(preferences, dict) else {}
    return {
        "teaching_goal": str(raw.get("teaching_goal", "")).strip(),
        "student_level": str(raw.get("student_level", "班级标准水平")).strip() or "班级标准水平",
        "teaching_style": str(raw.get("teaching_style", "老师课堂版")).strip() or "老师课堂版",
        "common_misconceptions": str(raw.get("common_misconceptions", "")).strip(),
        "explanation_depth": str(raw.get("explanation_depth", "标准")).strip() or "标准",
    }


def build_teaching_quality_context(
    grade: int,
    question: str,
    documents: list[KnowledgeDocument],
    preferences: dict | None = None,
) -> dict:
    """生成提示词和兜底答案都会用到的教学化上下文。"""

    normalized = normalize_teaching_preferences(preferences)
    concept_tags = {tag for document in documents for tag in document.concept_tags}
    teaching_goal = normalized["teaching_goal"] or _default_teaching_goal(question, concept_tags)
    misconception_focus = normalized["common_misconceptions"] or _default_misconceptions(question, concept_tags)
    teacher_prompt = _default_teacher_prompt(question, concept_tags)

    return {
        **normalized,
        "teaching_goal": teaching_goal,
        "misconception_focus": misconception_focus,
        "teacher_prompt": teacher_prompt,
        "student_profile": _student_profile_text(grade, normalized["student_level"]),
        "teaching_style_instruction": _teaching_style_instruction(normalized["teaching_style"]),
        "depth_instruction": _depth_instruction(normalized["explanation_depth"]),
        "teaching_strategy": _teaching_strategy(grade, concept_tags),
    }


def answer_has_required_sections(answer: str) -> bool:
    """检查答案是否已经具备课堂化讲解所需的关键章节。"""

    text = str(answer or "")
    return all(section in text for section in REQUIRED_ANSWER_SECTIONS)


def _default_teaching_goal(question: str, concept_tags: set[str]) -> str:
    if "division_equal_share" in concept_tags:
        return "理解平均分的意义，并能用除法表达每份是多少"
    if "rectangle_area" in concept_tags:
        return "理解长方形面积公式，并知道为什么要用长乘宽"
    if "rectangle_perimeter" in concept_tags:
        return "分清周长和面积，避免公式混用"
    if "fraction_meaning" in concept_tags:
        return "理解分数表示把整体平均分后的其中几份"
    if "fraction_decimal_equivalence" in concept_tags:
        return "理解分数和小数可以表示同一个数量"
    if "multiplication" in concept_tags:
        return "理解几个几的数量关系，并能正确列乘法算式"
    if "subtraction" in concept_tags:
        return "先分清原来有多少、拿走多少、还剩多少，再正确列式"
    if "addition" in concept_tags:
        return "理解合起来一共是多少，并说清加法的数量关系"
    if any(token in question for token in ("面积", "周长", "分数", "小数", "平均分")):
        return "结合题目关键词理解概念，再用合适方法解题"
    return "先读懂题意，再说清数量关系和解题思路"


def _default_misconceptions(question: str, concept_tags: set[str]) -> str:
    if "division_equal_share" in concept_tags:
        return "学生容易把总数、份数和每份数量搞混，或者把除法方向写反。"
    if "rectangle_area" in concept_tags:
        return "学生容易把面积和周长混淆，只看到长和宽就直接套错公式。"
    if "rectangle_perimeter" in concept_tags:
        return "学生容易把四条边没有全部算进去，或者误用面积公式。"
    if "fraction_meaning" in concept_tags:
        return "学生容易只看分子，不看分母表示把整体平均分成几份。"
    if "fraction_decimal_equivalence" in concept_tags:
        return "学生容易把 0.5 和 1/5 混淆，没有建立图形或数量对应关系。"
    if "multiplication" in concept_tags:
        return "学生容易把“几个几”看成加法乱加，或者漏掉组数。"
    if "subtraction" in concept_tags:
        return "学生容易没有分清楚谁是原来的数量，谁是减少的数量。"
    if "addition" in concept_tags:
        return "学生容易漏掉单位，或者没有先判断是不是求总数。"
    if any(token in question for token in ("面积", "周长")):
        return "学生容易看到图形就直接套公式，没有先判断题目到底在求什么。"
    return "学生容易只算数字，不先说清题目中的条件、问题和数量关系。"


def _default_teacher_prompt(question: str, concept_tags: set[str]) -> str:
    if "division_equal_share" in concept_tags:
        return "可以先追问：一共多少个？平均分成几份？每份应该一样多吗？"
    if "rectangle_area" in concept_tags:
        return "可以先追问：这道题求的是占地大小，还是边一圈有多长？"
    if "fraction_meaning" in concept_tags:
        return "可以先追问：整体被平均分成了几份？现在取了其中几份？"
    if "fraction_decimal_equivalence" in concept_tags:
        return "可以先追问：如果把同一个整体分一分，0.5 和 1/2 画出来会不会一样大？"
    if concept_tags & {"addition", "subtraction", "multiplication"}:
        return "可以先追问：题目里的数量之间是什么关系，是合起来、剩下，还是几个几？"
    if any(token in question for token in ("面积", "周长", "分数", "小数")):
        return "可以先让学生先说概念，再说算式。"
    return "可以先让学生复述题意，再说出先做什么、为什么这样做。"


def _student_profile_text(grade: int, student_level: str) -> str:
    base = {
        1: "更适合短句、口语化、可操作的表达。",
        2: "需要结合生活场景和直观动作理解数量变化。",
        3: "可以开始强调数量关系，但仍需要具体例子托底。",
        4: "可以在具体例子基础上加入概念归纳。",
        5: "可以适度提升抽象概括和方法比较。",
        6: "可以加强迁移、辨析和总结。",
    }.get(grade, "表达应清楚、分步且便于课堂复述。")
    return f"学生基础：{student_level}。{base}"


def _teaching_style_instruction(teaching_style: str) -> str:
    if teaching_style == "启发提问版":
        return "多用追问句，引导学生自己说出下一步，不要一路直接给答案。"
    if teaching_style == "家长辅导版":
        return "像家长在家辅导孩子一样，说话温和、步骤更细、提醒更明确。"
    return "保持老师课堂讲解风格，语言自然，适合直接口播或板书展开。"


def _depth_instruction(explanation_depth: str) -> str:
    if explanation_depth == "简洁":
        return "整体控制在较短篇幅，用最少步骤说清楚关键思路。"
    if explanation_depth == "详细":
        return "步骤更完整，每一步都要解释为什么这样做，并补一个直观例子。"
    return "篇幅适中，既讲清楚思路，也保留课堂可直接使用的节奏。"


def _teaching_strategy(grade: int, concept_tags: set[str]) -> str:
    if grade <= 2:
        return "先用生活场景或动手操作帮助学生理解，再过渡到算式。"
    if "rectangle_area" in concept_tags or "rectangle_perimeter" in concept_tags:
        return "先判断求的是什么量，再决定用哪个公式，最后回到图形检查结果是否合理。"
    if concept_tags & {"fraction_meaning", "fraction_decimal_equivalence"}:
        return "先借助图形或整体-部分关系理解概念，再连接到符号表达。"
    return "先读题定位条件和问题，再说数量关系，最后列式并检查答案。"
