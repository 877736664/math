# 小学数学 AI 教学平台（MVP）

# 小学数学 AI 教学平台（MVP）

这个仓库包含两个独立部分：

- `backend`：Python + FastAPI + LangChain + LangGraph
- `frontend`：Vite + React

建议分别查看各自说明：

- 后端文档：`backend/README.md`
- 前端文档：`frontend/README.md`

## 功能

输入一道小学数学题，后端一次返回 4 类产物：

1. `answer`：面向年级的分步讲解
2. `video`：可直接给剪辑/配音使用的视频脚本（分镜+口播步骤）
3. `ppt`：课件页纲（页标题 + 要点），并支持导出 `.pptx`
4. `game`：匹配题型的网页游戏入口

## 快速启动

先启动后端，再启动前端。

后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

访问地址：

- 前端：`http://127.0.0.1:5173`
- 后端文档：`http://127.0.0.1:8000/docs`

## 架构图

- [飞象老师式工作流技术架构图](./docs/feixiang_workflow_architecture.md)
