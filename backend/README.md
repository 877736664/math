# 后端说明

小学数学 AI 教学平台后端基于 `FastAPI + LangChain + LangGraph`，当前检索链路接入 `RAGFlow`。

## 目录结构

```text
backend/
  app/
    api/            # HTTP 路由、接口辅助函数
    core/           # 应用创建与基础配置
    repositories/   # 数据访问与目录仓储
    schemas/        # Pydantic 请求/响应模型
    services/       # 检索、问答、动画、视频、PPT 等服务
    workflows/      # LangGraph 工作流编排
    main.py         # Uvicorn 启动入口
  requirements.txt
  .env.example
```

主要职责：

- `app/api/routes`：按系统、教材、问答、素材拆分接口
- `app/services/rag_service.py`：负责 RAGFlow 检索适配
- `app/services/llm_service.py`：负责 LLM 调用封装
- `app/workflows/teaching_workflow.py`：统一编排问答与素材生成
- `app/repositories/textbook_repository.py`：维护教材范围与知识点序列化结构

## 开发启动

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

如果已经装好依赖：

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

默认地址：

- 服务：`http://127.0.0.1:8000`
- 文档：`http://127.0.0.1:8000/docs`

## 环境变量

示例 `.env`：

```dotenv
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=qwen3.5-plus
OPENAI_BASE_URL=https://coding.dashscope.aliyuncs.com/v1

RAGFLOW_BASE_URL=http://192.168.2.224
RAGFLOW_API_KEY=your_ragflow_api_key
RAGFLOW_DATASET_IDS=dataset_id_1,dataset_id_2
```

说明：

- 不配置 `OPENAI_API_KEY` 也能运行，系统会走内置降级模板
- 当前后端代码主要读取 `OPENAI_*` 和 `RAGFLOW_*`
- RAGFlow 当前接的是 `POST /api/v1/retrieval`
- `RAGFLOW_DATASET_IDS` 支持多个，使用英文逗号分隔

## 常用接口

- `GET /api/health`：健康检查
- `GET /api/textbook-catalog`：教材目录与默认值
- `POST /api/qa`：生成讲解答案
- `POST /api/lesson-prep`：生成备课草案
- `POST /api/lesson-assets`：一次生成答案、视频提纲、PPT 提纲、游戏推荐
- `POST /api/teaching-video`：生成教学视频文件
- `POST /api/ppt-outline`：生成 PPT 提纲
- `POST /api/animation-game`：生成互动动画 HTML
- `POST /api/pptx`：把 PPT 提纲导出成 `.pptx`

### `POST /api/qa`

```json
{
  "grade": 3,
  "question": "小明有12颗糖，平均分给3个同学，每人几颗？"
}
```

### `POST /api/lesson-assets`

```json
{
  "answer": "...",
  "video": {
    "title": "...",
    "script_steps": ["...", "..."]
  },
  "ppt": {
    "title": "...",
    "slides": [
      {
        "title": "封面",
        "bullet_points": ["课程主题", "适用年级"]
      }
    ]
  },
  "game": {
    "title": "...",
    "url": "https://...",
    "reason": "..."
  }
}
```

## 开发提示

- 修改环境变量后记得重启 `uvicorn`
- 如果改了接口结构，记得同步前端的 `frontend/src/lib/chatStorage.js`
- 架构图见：`docs/feixiang_workflow_architecture.md`
