# 小学数学 AI 教学平台（MVP）

当前仓库结构：

- `backend`：Python + FastAPI + LangChain + LangGraph
- `frontend`：Vite + React

## 功能

输入一道小学数学题，后端一次返回 4 类产物：

1. `answer`：面向年级的分步讲解
2. `video`：可直接给剪辑/配音使用的视频脚本（分镜+口播步骤）
3. `ppt`：课件页纲（页标题 + 要点），并支持导出 `.pptx`
4. `game`：匹配题型的网页游戏入口

## 启动后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

示例 `.env`（DashScope 兼容端点）：

```dotenv
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=qwen3.5-plus
OPENAI_BASE_URL=https://coding.dashscope.aliyuncs.com/v1

ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_AUTH_TOKEN=your_key_here
ANTHROPIC_MODEL=qwen3.5-plus
ANTHROPIC_BASE_URL=https://coding.dashscope.aliyuncs.com/apps/anthropic
```

说明：

- 不配置 `OPENAI_API_KEY` 也能运行，系统会使用内置降级模板。
- 配置后会通过 `LangChain + ChatOpenAI` 生成更完整内容，并由 `LangGraph` 统一编排问答与素材工作流。
- 当前后端代码只读取 `OPENAI_*`，所以运行本项目时至少需要 `OPENAI_API_KEY`、`OPENAI_MODEL`、`OPENAI_BASE_URL`。
- `ANTHROPIC_*` 变量已写入示例配置，供 Claude Code、Anthropic SDK 或其他兼容工具使用，但当前仓库代码不会直接读取它们。

### 接入 RAGFlow 检索

项目已移除内置本地知识库，后端现在只走 RAGFlow 检索。请在 `backend/.env` 中补充：

```dotenv
RAGFLOW_BASE_URL=http://192.168.2.224
RAGFLOW_API_KEY=your_ragflow_api_key
RAGFLOW_DATASET_IDS=dataset_id_1,dataset_id_2
```

说明：

- 当前接的是 RAGFlow HTTP API 的 `POST /api/v1/retrieval`，需要有效的 `API key` 和 `dataset_ids`。
- 如果 RAGFlow 没有返回有效片段，后端会返回占位知识点，方便排查 `API key`、`dataset_ids` 或数据集内容是否正确。

## 启动前端

新开一个终端：

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端文档：`http://127.0.0.1:8000/docs`

## API

### `POST /api/qa`

仅返回问答文本。

请求体：

```json
{
  "grade": 3,
  "question": "小明有12颗糖，平均分给3个同学，每人几颗？"
}
```

### `POST /api/lesson-assets`

返回问答 + 视频脚本 + PPT页纲 + 游戏链接。

响应体示例：

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

### `POST /api/pptx`

将 `lesson-assets` 返回的 `ppt` 结构导出为真实 `.pptx` 文件（二进制下载）。

## 架构图

- [飞象老师式工作流技术架构图](./docs/feixiang_workflow_architecture.md)
