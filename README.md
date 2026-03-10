# 小学数学 AI 教学平台（MVP）

当前仓库结构：

- `backend`：Python + FastAPI + LangChain
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

说明：

- 不配置 `OPENAI_API_KEY` 也能运行，系统会使用内置降级模板。
- 配置后会通过 `LangChain + ChatOpenAI` 生成更完整内容。

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
