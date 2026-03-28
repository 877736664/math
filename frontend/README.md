# 前端说明

小学数学 AI 教学平台前端基于 `Vite + React`，负责对话式提问、历史记录、视频/PPT/动画预览与下载。

## 目录结构

```text
frontend/src/
  components/   # 预览页、Markdown、加载卡片等组件
  lib/          # 本地存储、下载、Markdown 处理等工具函数
  App.jsx       # 主界面与对话流程
  main.jsx      # 应用入口
```

## 开发启动

```powershell
npm install
copy .env.example .env
npm run dev
```

默认访问地址：`http://127.0.0.1:5173`

## 环境变量

- `VITE_API_BASE_URL`：后端接口地址，默认指向 `http://127.0.0.1:8000`

示例：

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 主要页面与能力

- 对话问答：发送题目并展示讲解答案
- 历史记录：自动保存最近对话，可继续生成素材
- 视频预览：播放后端生成的教学视频并支持下载
- PPT 预览：按页查看提纲并导出 `.pptx`
- 动画预览：加载互动动画 HTML 并支持下载

## 开发提示

- 主流程入口在 `frontend/src/App.jsx`
- 预览页逻辑在 `frontend/src/components/PreviewPage.jsx`
- 本地历史兼容逻辑在 `frontend/src/lib/chatStorage.js`
- 如果后端接口字段变化，优先同步更新 `frontend/src/lib/chatStorage.js`

## 打包

```powershell
npm run build
```

构建产物输出到 `frontend/dist`
