"""题目驱动的动画规划服务。"""

from __future__ import annotations

import re

from app.repositories.textbook_repository import KnowledgeDocument


def build_animation_plan(question: str, grade: int, documents: list[KnowledgeDocument] | None = None) -> dict:
    """根据题目情景和检索内容生成动画规划结果。"""

    docs = documents or []
    normalized_question = str(question or "").strip()
    concept_tags = _collect_concept_tags(docs)
    keywords = _build_keywords(normalized_question, concept_tags)
    scene_type = _detect_scene_type(normalized_question, concept_tags)
    entities = _extract_visual_entities(normalized_question, scene_type)
    teaching_focus = docs[0].title if docs else _default_teaching_focus(scene_type)

    return {
        "scene_type": scene_type,
        "scene_summary": _scene_summary(scene_type, normalized_question),
        "retrieval_keywords": keywords,
        "retrieval_query": _build_retrieval_query(normalized_question, keywords),
        "teaching_focus": teaching_focus,
        "teaching_goal": _teaching_goal(scene_type, normalized_question, concept_tags),
        "interaction_model": _interaction_model(scene_type),
        "visual_entities": entities,
        "storyboard_steps": _storyboard_steps(scene_type, normalized_question),
        "knowledge_focus": [document.title for document in docs[:3]],
        "question_goal": _question_goal(normalized_question),
        "grade": grade,
    }


def _collect_concept_tags(documents: list[KnowledgeDocument]) -> set[str]:
    return {tag for document in documents for tag in document.concept_tags}


def _build_keywords(question: str, concept_tags: set[str]) -> list[str]:
    keywords: list[str] = []

    def add(value: str):
        item = value.strip()
        if item and item not in keywords:
            keywords.append(item)

    for token in re.findall(r"[\u4e00-\u9fff]{2,}", question):
        if token in {"多少千米", "多少分钟", "应用题", "数学问题"}:
            continue
        if any(flag in token for flag in ("相向", "平均", "长方形", "周长", "面积", "分数", "小数", "路程", "速度", "时间")):
            add(token)

    if any(word in question for word in ("相向", "同时从家出发", "相距", "路程", "自行车")):
        for token in ("相向而行", "路程问题", "线段图", "速度时间路程", "数量关系"):
            add(token)
    if any(word in question for word in ("平均分", "平分", "均分", "每人", "每份")):
        for token in ("平均分", "除法意义", "份数", "每份数量"):
            add(token)
    if "rectangle_area" in concept_tags or ("长方形" in question and "面积" in question):
        for token in ("长方形面积", "面积公式", "长乘宽"):
            add(token)
    if "rectangle_perimeter" in concept_tags or ("长方形" in question and "周长" in question):
        for token in ("长方形周长", "周长公式", "一圈长度"):
            add(token)
    if "fraction_meaning" in concept_tags or re.search(r"\d+\s*/\s*\d+", question):
        for token in ("分数意义", "整体与部分", "平均分"):
            add(token)

    return keywords[:10]


def _detect_scene_type(question: str, concept_tags: set[str]) -> str:
    if any(word in question for word in ("相向", "同时出发", "相距", "速度和", "路程", "骑自行车")):
        return "journey_meeting"
    if "division_equal_share" in concept_tags or any(word in question for word in ("平均分", "平分", "均分", "每人", "每份")):
        return "average_share"
    if "rectangle_area" in concept_tags or ("长方形" in question and "面积" in question):
        return "area_cover"
    if "rectangle_perimeter" in concept_tags or ("长方形" in question and "周长" in question):
        return "perimeter_walk"
    if "fraction_meaning" in concept_tags or re.search(r"\d+\s*/\s*\d+", question):
        return "fraction_partition"
    return "generic_reasoning"


def _extract_visual_entities(question: str, scene_type: str) -> list[dict]:
    entities: list[dict] = []

    person_names = re.findall(r"([\u4e00-\u9fff]{1,4}(?:叔叔|阿姨|老师|同学|小朋友|哥哥|姐姐|弟弟|妹妹))", question)
    for name in person_names[:4]:
        entities.append({"type": "person", "name": name})

    if scene_type == "journey_meeting":
        entities.append({"type": "route", "name": "线段路程图"})
    elif scene_type == "average_share":
        entities.append({"type": "group", "name": "平均分组"})
    elif scene_type in {"area_cover", "perimeter_walk"}:
        entities.append({"type": "shape", "name": "长方形"})
    elif scene_type == "fraction_partition":
        entities.append({"type": "whole", "name": "整体切分图"})

    if not entities:
        entities.append({"type": "concept", "name": "数学关系"})

    return entities


def _scene_summary(scene_type: str, question: str) -> str:
    if scene_type == "journey_meeting":
        return "把行程关系做成线段图和运动过程，让学生先看懂谁从哪里出发、什么时候相遇。"
    if scene_type == "average_share":
        return "把平均分过程变成逐轮分配动画，让学生看到每份为什么一样多。"
    if scene_type == "area_cover":
        return "把面积理解成方格铺满，帮助学生从图形直观过渡到公式。"
    if scene_type == "perimeter_walk":
        return "把周长理解成沿边走一圈，帮助学生分清周长和面积。"
    if scene_type == "fraction_partition":
        return "把整体平均分并高亮其中几份，帮助学生理解分母和分子的含义。"
    return f"围绕题目“{question[:24]}”生成分步讲解动画。"


def _build_retrieval_query(question: str, keywords: list[str]) -> str:
    if not keywords:
        return question
    return f"{question}\n动画检索关键词：{'、'.join(keywords)}"


def _teaching_goal(scene_type: str, question: str, concept_tags: set[str]) -> str:
    if scene_type == "journey_meeting":
        return "先读懂题目中的运动情景，再建立路程、时间和速度之间的数量关系。"
    if scene_type == "average_share":
        return "通过逐轮分配看懂平均分的意义，再连接到除法算式。"
    if scene_type == "area_cover":
        return "先理解面积表示图形表面的大小，再理解为什么用长乘宽。"
    if scene_type == "perimeter_walk":
        return "先理解周长是一圈的长度，再判断四条边怎样合起来计算。"
    if scene_type == "fraction_partition":
        return "先从整体平均分理解分数，再连接到符号表达。"
    if "multiplication" in concept_tags:
        return "先看清几个几，再用乘法表示数量关系。"
    return f"帮助学生先读懂题意，再顺着步骤完成“{_question_goal(question)}”。"


def _interaction_model(scene_type: str) -> str:
    if scene_type == "journey_meeting":
        return "timeline_scrub"
    if scene_type == "average_share":
        return "step_playback"
    if scene_type in {"area_cover", "fraction_partition"}:
        return "progressive_reveal"
    return "guided_stepper"


def _storyboard_steps(scene_type: str, question: str) -> list[str]:
    if scene_type == "journey_meeting":
        return ["展示两端起点和总路程", "推进到关键时间点", "高亮路程关系", "回到问题做推理"]
    if scene_type == "average_share":
        return ["展示总数和份数", "逐轮分配", "观察每份变化", "回到除法算式"]
    if scene_type == "area_cover":
        return ["展示图形", "用方格铺满", "数行和列", "连接到面积公式"]
    if scene_type == "fraction_partition":
        return ["展示整体", "平均分成若干份", "高亮其中几份", "连接到分数读法"]
    return ["先读题", "找条件", "看方法", "回到答案"]


def _question_goal(question: str) -> str:
    match = re.search(r"(求|问|还要|需要|一共|每人|每份|面积|周长|相距)(.*)", question)
    if match:
        return match.group(0).strip("。？！!? ")
    return "题目中的关键问题"


def _default_teaching_focus(scene_type: str) -> str:
    return {
        "journey_meeting": "相向而行",
        "average_share": "平均分",
        "area_cover": "面积理解",
        "perimeter_walk": "周长理解",
        "fraction_partition": "分数意义",
    }.get(scene_type, "分步讲解")
