import json
import os
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


GAME_CATALOG = [
    {
        "keywords": ["加法", "减法", "口算", "算术", "乘法", "除法"],
        "title": "算术训练游戏",
        "url": "https://www.abcya.com/games/math_facts",
    },
    {
        "keywords": ["分数", "小数", "百分数"],
        "title": "分数与小数互动练习",
        "url": "https://www.mathplayground.com/ASB_PenguinJumpMultiplication.html",
    },
    {
        "keywords": ["几何", "图形", "面积", "周长", "角"],
        "title": "几何图形互动游戏",
        "url": "https://www.geogebra.org/m/zf9f7k7h",
    },
]


def _create_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.getenv("OPENAI_BASE_URL") or None
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.2,
        timeout=45,
    )


@lru_cache(maxsize=1)
def _build_qa_chain():
    llm = _create_llm()
    if llm is None:
        return None

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "你是小学数学AI助教。回答要求："
                    "1) 使用简体中文；"
                    "2) 难度匹配{grade}年级；"
                    "3) 先给结论，再分步骤讲解；"
                    "4) 最后给1道同类型练习题（不带答案）。"
                ),
            ),
            ("human", "学生问题：{question}"),
        ]
    )

    return prompt | llm | StrOutputParser()


@lru_cache(maxsize=1)
def _build_assets_chain():
    llm = _create_llm()
    if llm is None:
        return None

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "你是小学数学课程设计助手。"
                    "请严格输出 JSON，不要输出 markdown 代码块。"
                    "JSON 结构如下："
                    "{"
                    "\"answer\":\"...\","
                    "\"video_title\":\"...\","
                    "\"video_script_steps\":[\"...\",\"...\"],"
                    "\"ppt_title\":\"...\","
                    "\"ppt_slides\":["
                    "{\"title\":\"...\",\"bullet_points\":[\"...\",\"...\"]}"
                    "],"
                    "\"game_title\":\"...\","
                    "\"game_reason\":\"...\""
                    "}"
                    "要求："
                    "1) 面向小学{grade}年级；"
                    "2) video_script_steps 返回4-6条；"
                    "3) ppt_slides 返回5-8页；"
                    "4) 每页 bullet_points 返回2-4条，短句。"
                ),
            ),
            ("human", "问题：{question}"),
        ]
    )

    return prompt | llm | StrOutputParser()


def _pick_game(question: str):
    for item in GAME_CATALOG:
        if any(keyword in question for keyword in item["keywords"]):
            return {
                "title": item["title"],
                "url": item["url"],
                "reason": "根据题目关键词匹配到最相关的互动练习。",
            }
    default_game = GAME_CATALOG[0]
    return {
        "title": default_game["title"],
        "url": default_game["url"],
        "reason": "未命中特定题型，默认推荐通用口算练习。",
    }


def _fallback_answer(grade: int, question: str) -> str:
    return (
        f"结论：这是一道适合小学{grade}年级的数学问题。\n\n"
        "步骤讲解：\n"
        "1. 先圈出已知条件，明确题目要求什么。\n"
        "2. 把计算拆成最小步骤，按顺序逐步完成。\n"
        "3. 每一步检查数字和单位是否正确。\n"
        "4. 把结果代回题目语境，判断是否合理。\n\n"
        f"你的原题：{question}\n\n"
        "同类型练习：一支铅笔2元，买4支需要多少钱？"
    )


def _fallback_assets(grade: int, question: str):
    game = _pick_game(question)
    return {
        "answer": _fallback_answer(grade, question),
        "video": {
            "title": f"{grade}年级数学微课：题目拆解训练",
            "script_steps": [
                "开场：老师用生活场景引入题目，激发兴趣。",
                "步骤1：一起找已知条件与问题。",
                "步骤2：把解题过程拆成2-3个可执行步骤。",
                "步骤3：演示验算与结果检查。",
                "结尾：布置1道同类型练习题。",
            ],
        },
        "ppt": {
            "title": f"{grade}年级数学讲解课件",
            "slides": [
                {"title": "封面", "bullet_points": ["课程主题", "适用年级"]},
                {"title": "题目展示", "bullet_points": ["原题重述", "关键条件标注"]},
                {"title": "解题思路", "bullet_points": ["先做什么", "再做什么"]},
                {"title": "步骤演示", "bullet_points": ["计算过程", "常见错误提醒"]},
                {"title": "课堂练习", "bullet_points": ["同类型练习1", "同类型练习2"]},
                {"title": "总结", "bullet_points": ["本课知识点", "回家练习建议"]},
            ],
        },
        "game": game,
    }


def generate_answer(grade: int, question: str) -> str:
    chain = _build_qa_chain()
    if chain is None:
        return _fallback_answer(grade, question)
    return chain.invoke({"grade": grade, "question": question})


def generate_lesson_assets(grade: int, question: str):
    chain = _build_assets_chain()
    if chain is None:
        return _fallback_assets(grade, question)

    raw = chain.invoke({"grade": grade, "question": question}).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _fallback_assets(grade, question)

    slides = data.get("ppt_slides", [])
    if not isinstance(slides, list):
        slides = []

    normalized_slides = []
    for slide in slides[:8]:
        title = str(slide.get("title", "未命名页面")).strip() if isinstance(slide, dict) else "未命名页面"
        points = slide.get("bullet_points", []) if isinstance(slide, dict) else []
        if not isinstance(points, list):
            points = []
        normalized_slides.append(
            {"title": title or "未命名页面", "bullet_points": [str(p) for p in points[:4]]}
        )

    game = _pick_game(question)
    if isinstance(data.get("game_title"), str) and data["game_title"].strip():
        game["title"] = data["game_title"].strip()
    if isinstance(data.get("game_reason"), str) and data["game_reason"].strip():
        game["reason"] = data["game_reason"].strip()

    return {
        "answer": str(data.get("answer", _fallback_answer(grade, question))),
        "video": {
            "title": str(data.get("video_title", f"{grade}年级数学微课")).strip() or f"{grade}年级数学微课",
            "script_steps": [str(s) for s in data.get("video_script_steps", [])[:6]]
            or _fallback_assets(grade, question)["video"]["script_steps"],
        },
        "ppt": {
            "title": str(data.get("ppt_title", f"{grade}年级数学讲解课件")).strip() or f"{grade}年级数学讲解课件",
            "slides": normalized_slides or _fallback_assets(grade, question)["ppt"]["slides"],
        },
        "game": game,
    }
