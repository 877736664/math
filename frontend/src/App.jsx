import { useEffect, useRef, useState } from 'react'

import AssetLoadingCard from './components/AssetLoadingCard'
import PreviewPage from './components/PreviewPage'
import ThinkingCard from './components/ThinkingCard'
import './App.css'
import {
  MAX_HISTORY_ITEMS,
  buildPreviewUrl,
  clearStoredHistory,
  createConversationId,
  createEmptyAnimationGameState,
  createEmptyPptState,
  createEmptyVideoState,
  formatTime,
  getPreviewText,
  getRouteState,
  getStatusLabel,
  getStatusTone,
  loadStoredHistory,
  normalizeConversation,
  persistHistory,
} from './lib/chatStorage'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const sampleCases = [
  '8 + 7 为什么等于 15？请用图示思路讲解。',
  '长方形长 8 厘米、宽 5 厘米，面积怎么计算？',
  '把 3/4 讲给三年级学生听，要有生活例子。',
  '小明有 24 颗糖，平均分给 6 个人，每人多少颗？',
  '比较 0.5 和 1/2，为什么它们相等？',
  '两位数乘一位数怎么验算？给一道练习题。',
]

const modeOptions = ['轻快', '标准', '深入']

function App() {
  const [route, setRoute] = useState(getRouteState)
  const [history, setHistory] = useState(loadStoredHistory)
  const [activeId, setActiveId] = useState(null)
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState('标准')
  const [fileName, setFileName] = useState('')
  const [submittingQuestion, setSubmittingQuestion] = useState(false)
  const [composerError, setComposerError] = useState('')
  const fileInputRef = useRef(null)

  useEffect(() => {
    const handlePopState = () => {
      setRoute(getRouteState())
    }

    window.addEventListener('popstate', handlePopState)
    return () => {
      window.removeEventListener('popstate', handlePopState)
    }
  }, [])

  useEffect(() => {
    if (!route.previewType) {
      persistHistory(history)
    }
  }, [history, route.previewType])

  useEffect(() => {
    if (route.previewType || !history.length) {
      if (!history.length && activeId !== null) {
        setActiveId(null)
      }
      return
    }

    const hasActiveConversation = history.some((item) => item.id === activeId)
    if (!hasActiveConversation) {
      const firstConversation = history[0]
      setActiveId(firstConversation.id)
      setQuestion(firstConversation.question)
      setMode(firstConversation.mode || '标准')
      setFileName(firstConversation.fileName || '')
    }
  }, [activeId, history, route.previewType])

  if (route.previewType) {
    return (
      <PreviewPage
        key={`${route.previewType}:${route.previewId}`}
        previewType={route.previewType}
        previewId={route.previewId}
      />
    )
  }

  const activeConversation = history.find((item) => item.id === activeId) || null

  const updateConversation = (conversationId, updater) => {
    setHistory((previousHistory) =>
      previousHistory.map((item) => {
        if (item.id !== conversationId) {
          return item
        }

        const nextItem = typeof updater === 'function' ? updater(item) : updater
        return normalizeConversation(nextItem)
      }),
    )
  }

  const openFilePicker = () => {
    fileInputRef.current?.click()
  }

  const onPickFile = (event) => {
    const targetFile = event.target.files?.[0]
    setFileName(targetFile ? targetFile.name : '')
  }

  const selectConversation = (conversation) => {
    setActiveId(conversation.id)
    setQuestion(conversation.question)
    setMode(conversation.mode || '标准')
    setFileName(conversation.fileName || '')
    setComposerError('')
  }

  const clearHistory = () => {
    if (submittingQuestion) {
      return
    }

    setHistory([])
    setActiveId(null)
    setQuestion('')
    setFileName('')
    setComposerError('')
    clearStoredHistory()
  }

  const submitQuestion = async (nextQuestion) => {
    const finalQuestion = (nextQuestion ?? question).trim()
    if (!finalQuestion || submittingQuestion) {
      if (!finalQuestion) {
        setComposerError('请输入一个具体的问题。')
      }
      return
    }

    const conversationId = createConversationId()
    const timestamp = new Date().toISOString()
    const conversation = normalizeConversation({
      id: conversationId,
      question: finalQuestion,
      mode,
      fileName,
      answerStatus: 'loading',
      answer: '',
      answerError: '',
      video: createEmptyVideoState(),
      ppt: createEmptyPptState(),
      animationGame: createEmptyAnimationGameState(),
      createdAt: timestamp,
      updatedAt: timestamp,
    })

    setSubmittingQuestion(true)
    setComposerError('')
    setActiveId(conversationId)
    setQuestion('')
    setFileName('')

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }

    setHistory((previousHistory) => [conversation, ...previousHistory].slice(0, MAX_HISTORY_ITEMS))

    try {
      const response = await fetch(`${API_BASE_URL}/api/qa`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade: 3,
          question: finalQuestion,
        }),
      })

      if (!response.ok) {
        throw new Error(`请求失败，HTTP ${response.status}`)
      }

      const data = await response.json()

      updateConversation(conversationId, (item) => ({
        ...item,
        answerStatus: 'done',
        answer: data.answer || '已生成讲解答案。',
        answerError: '',
        updatedAt: new Date().toISOString(),
      }))
    } catch (error) {
      updateConversation(conversationId, (item) => ({
        ...item,
        answerStatus: 'error',
        answerError: error instanceof Error ? error.message : '请求失败，请稍后重试。',
        answer: '',
        updatedAt: new Date().toISOString(),
      }))
    } finally {
      setSubmittingQuestion(false)
    }
  }

  const generateMaterial = async (conversationId, type) => {
    const conversation = history.find((item) => item.id === conversationId)
    if (!conversation) {
      return
    }

    const materialKey =
      type === 'video' ? 'video' : type === 'ppt' ? 'ppt' : 'animationGame'
    if (conversation[materialKey].status === 'loading') {
      return
    }

    updateConversation(conversationId, (item) => ({
      ...item,
      [materialKey]: {
        ...item[materialKey],
        status: 'loading',
        error: '',
      },
      updatedAt: new Date().toISOString(),
    }))

    try {
      const endpoint =
        type === 'video'
          ? 'video-script'
          : type === 'ppt'
            ? 'ppt-outline'
            : 'animation-game'
      const response = await fetch(`${API_BASE_URL}/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade: 3,
          question: conversation.question,
        }),
      })

      if (!response.ok) {
        throw new Error(`请求失败，HTTP ${response.status}`)
      }

      const data = await response.json()

      updateConversation(conversationId, (item) => ({
        ...item,
        [materialKey]:
          type === 'video'
            ? {
                status: 'done',
                title: data.title || '视频脚本',
                scriptSteps: Array.isArray(data.script_steps)
                  ? data.script_steps.map((step) => String(step))
                  : [],
                error: '',
                updatedAt: new Date().toISOString(),
              }
            : type === 'ppt'
              ? {
                  status: 'done',
                  title: data.title || 'PPT 提纲',
                  slides: Array.isArray(data.slides)
                    ? data.slides.map((slide) => ({
                        title:
                          typeof slide?.title === 'string' && slide.title
                            ? slide.title
                            : '未命名页面',
                        bullet_points: Array.isArray(slide?.bullet_points)
                          ? slide.bullet_points.map((point) => String(point))
                          : [],
                      }))
                    : [],
                  error: '',
                  updatedAt: new Date().toISOString(),
                }
              : {
                  status: 'done',
                  title: data.title || '数字动画游戏',
                  summary: data.summary || '已生成可在线预览的动画游戏。',
                  html: data.html || '',
                  searchQueries: Array.isArray(data.search_queries)
                    ? data.search_queries.map((query) => String(query))
                    : [],
                  imageSources: Array.isArray(data.image_sources)
                    ? data.image_sources.map((source) => ({
                        query: typeof source?.query === 'string' ? source.query : '',
                        image_url: typeof source?.image_url === 'string' ? source.image_url : '',
                        source_page: typeof source?.source_page === 'string' ? source.source_page : '',
                        source_host: typeof source?.source_host === 'string' ? source.source_host : '',
                      }))
                    : [],
                  error: '',
                  updatedAt: new Date().toISOString(),
                },
        updatedAt: new Date().toISOString(),
      }))
    } catch (error) {
      updateConversation(conversationId, (item) => ({
        ...item,
        [materialKey]: {
          ...item[materialKey],
          status: 'error',
          error: error instanceof Error ? error.message : '生成失败，请稍后重试。',
          updatedAt: new Date().toISOString(),
        },
        updatedAt: new Date().toISOString(),
      }))
    }
  }

  const openPreviewPage = (type, conversationId) => {
    persistHistory(history)
    window.open(buildPreviewUrl(type, conversationId), '_blank', 'noopener,noreferrer')
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    await submitQuestion()
  }

  const onUseCase = async (caseQuestion) => {
    setQuestion(caseQuestion)
    await submitQuestion(caseQuestion)
  }

  const onQuestionKeyDown = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submitQuestion()
    }
  }

  return (
    <main className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <p className="sidebar-kicker">拾光备课</p>
          <h1>历史对话</h1>
          <p>每次提问都会自动保存。点击历史记录，可以继续生成视频脚本、PPT 提纲或数字动画游戏。</p>
        </div>

        <div className="sidebar-toolbar">
          <span className="history-count">
            {history.length ? `已保存 ${history.length} 条记录` : '还没有保存的对话'}
          </span>
          <button type="button" className="history-clear" onClick={clearHistory} disabled={submittingQuestion}>
            清空
          </button>
        </div>

        <div className="history-list">
          {history.length ? (
            history.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`history-card ${item.id === activeId ? 'history-card--active' : ''}`}
                onClick={() => selectConversation(item)}
              >
                <div className="history-card-top">
                  <span className={`history-status history-status--${getStatusTone(item)}`}>
                    {getStatusLabel(item)}
                  </span>
                  <time>{formatTime(item.updatedAt || item.createdAt)}</time>
                </div>

                <p className="history-question">{item.question}</p>
                <p className="history-preview">{getPreviewText(item)}</p>
              </button>
            ))
          ) : (
            <div className="history-empty">
              <p>还没有历史记录。</p>
              <span>提一个问题后，它会自动出现在这里。</span>
            </div>
          )}
        </div>
      </aside>

      <section className="workspace">
        <div className="workspace-shell">
          <header className="hero">
            <p className="hero-kicker">小学数学 AI 教学平台</p>
            <h2>先生成讲解答案，再按需生成视频脚本、PPT 提纲和动画游戏。</h2>
            <p>
              这样你可以先确认这道题讲得对不对，再决定要不要继续产出教学素材。动画游戏会自动按题意搜图，并组合成可以在线试玩的 HTML。
            </p>
          </header>

          <form className="input-shell" onSubmit={onSubmit}>
            <label className="input-label" htmlFor="question-input">
              今天想讲哪一道题？
            </label>
            <textarea
              id="question-input"
              className="question-input"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={onQuestionKeyDown}
              placeholder="输入一道数学题，或者让它生成一段适合课堂讲解的内容。"
              disabled={submittingQuestion}
              rows={3}
            />

            <div className="toolbar">
              <div className="toolbar-left">
                <select
                  value={mode}
                  onChange={(event) => setMode(event.target.value)}
                  disabled={submittingQuestion}
                  aria-label="讲解节奏"
                >
                  {modeOptions.map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>

                <button
                  type="button"
                  className="attach-btn"
                  onClick={openFilePicker}
                  disabled={submittingQuestion}
                >
                  {fileName ? `附件：${fileName}` : '添加附件'}
                </button>
              </div>

              <button
                type="submit"
                className="send-btn"
                disabled={submittingQuestion}
                aria-label="开始生成讲解"
              >
                {submittingQuestion ? '整理中…' : '先生成讲解'}
              </button>
            </div>

            {composerError ? <p className="error-hint">{composerError}</p> : null}
          </form>

          <input
            ref={fileInputRef}
            type="file"
            onChange={onPickFile}
            hidden
            aria-hidden="true"
          />

          <section className="conversation-panel">
            {activeConversation ? (
              <>
                <article className="message-bubble question-bubble">
                  <div className="bubble-top">
                    <span>本次提问</span>
                    <time>{formatTime(activeConversation.createdAt)}</time>
                  </div>
                  <p>{activeConversation.question}</p>
                  <div className="bubble-meta">
                    <span>{activeConversation.mode || '标准'}模式</span>
                    <span>{activeConversation.fileName ? `附件：${activeConversation.fileName}` : '未添加附件'}</span>
                  </div>
                </article>

                {activeConversation.answerStatus === 'loading' ? <ThinkingCard /> : null}

                {activeConversation.answerStatus === 'error' ? (
                  <article className="content-card error-card">
                    <div className="section-head">
                      <span className="section-tag">请求失败</span>
                      <h3>这次讲解没有生成成功</h3>
                    </div>
                    <p>{activeConversation.answerError || '请稍后再试一次。'}</p>
                  </article>
                ) : null}

                {activeConversation.answerStatus === 'done' ? (
                  <div className="response-grid">
                    <article className="content-card answer-card">
                      <div className="section-head">
                        <span className="section-tag">讲解答案</span>
                        <h3>适合直接讲给学生听</h3>
                      </div>
                      <p className="answer-text">{activeConversation.answer}</p>
                    </article>

                    <article className="content-card material-card">
                      <div className="section-head">
                        <span className="section-tag">视频脚本</span>
                        <h3>
                          {activeConversation.video.status === 'done'
                            ? activeConversation.video.title
                            : '按这道题生成可录制的视频脚本'}
                        </h3>
                      </div>

                      {activeConversation.video.status === 'idle' ? (
                        <div className="material-actions">
                          <p className="material-copy">
                            需要口播脚本、分镜步骤或短视频台词时，再生成这一份内容。
                          </p>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => {
                              void generateMaterial(activeConversation.id, 'video')
                            }}
                          >
                            生成视频脚本
                          </button>
                        </div>
                      ) : null}

                      {activeConversation.video.status === 'loading' ? (
                        <AssetLoadingCard
                          title="正在生成视频脚本"
                          description="我会把这道题整理成适合录屏、配音或老师口播的步骤。"
                        />
                      ) : null}

                      {activeConversation.video.status === 'error' ? (
                        <div className="material-actions">
                          <p className="material-error">{activeConversation.video.error || '生成失败，请稍后重试。'}</p>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => {
                              void generateMaterial(activeConversation.id, 'video')
                            }}
                          >
                            重新生成
                          </button>
                        </div>
                      ) : null}

                      {activeConversation.video.status === 'done' ? (
                        <div className="material-actions">
                          <ol className="steps-list">
                            {activeConversation.video.scriptSteps.slice(0, 3).map((step, index) => (
                              <li key={`${activeConversation.id}-video-snippet-${index}`}>{step}</li>
                            ))}
                          </ol>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => openPreviewPage('video', activeConversation.id)}
                          >
                            新页面预览或下载
                          </button>
                        </div>
                      ) : null}
                    </article>

                    <article className="content-card material-card">
                      <div className="section-head">
                        <span className="section-tag">PPT 提纲</span>
                        <h3>
                          {activeConversation.ppt.status === 'done'
                            ? activeConversation.ppt.title
                            : '按这道题生成课堂演示用的 PPT 提纲'}
                        </h3>
                      </div>

                      {activeConversation.ppt.status === 'idle' ? (
                        <div className="material-actions">
                          <p className="material-copy">
                            需要课件结构时，再生成这一份内容。生成后可在新页面预览并下载 `.pptx`。
                          </p>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => {
                              void generateMaterial(activeConversation.id, 'ppt')
                            }}
                          >
                            生成 PPT 提纲
                          </button>
                        </div>
                      ) : null}

                      {activeConversation.ppt.status === 'loading' ? (
                        <AssetLoadingCard
                          title="正在生成 PPT 提纲"
                          description="我会把讲题步骤拆成适合课件排版的页面结构。"
                        />
                      ) : null}

                      {activeConversation.ppt.status === 'error' ? (
                        <div className="material-actions">
                          <p className="material-error">{activeConversation.ppt.error || '生成失败，请稍后重试。'}</p>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => {
                              void generateMaterial(activeConversation.id, 'ppt')
                            }}
                          >
                            重新生成
                          </button>
                        </div>
                      ) : null}

                      {activeConversation.ppt.status === 'done' ? (
                        <div className="material-actions">
                          <div className="slide-list">
                            {activeConversation.ppt.slides.slice(0, 3).map((slide, index) => (
                              <div key={`${activeConversation.id}-ppt-snippet-${index}`} className="slide-card">
                                <strong>{slide.title}</strong>
                                <p>{slide.bullet_points.join(' / ')}</p>
                              </div>
                            ))}
                          </div>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => openPreviewPage('ppt', activeConversation.id)}
                          >
                            新页面预览或下载
                          </button>
                        </div>
                      ) : null}
                    </article>

                    <article className="content-card material-card">
                      <div className="section-head">
                        <span className="section-tag">数字动画游戏</span>
                        <h3>
                          {activeConversation.animationGame.status === 'done'
                            ? activeConversation.animationGame.title
                            : '按这道题生成带搜图素材的 HTML 动画游戏'}
                        </h3>
                      </div>

                      {activeConversation.animationGame.status === 'idle' ? (
                        <div className="material-actions">
                          <p className="material-copy">
                            需要把题目做成可以边看边点的数字动画游戏时，再生成这一份内容。系统会根据题目自动搜几张图片，并合成单文件 HTML。
                          </p>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => {
                              void generateMaterial(activeConversation.id, 'animation')
                            }}
                          >
                            生成动画游戏
                          </button>
                        </div>
                      ) : null}

                      {activeConversation.animationGame.status === 'loading' ? (
                        <AssetLoadingCard
                          title="正在生成数字动画游戏"
                          description="我会先判断题型，再按题意搜图，最后拼成可以在线试玩的 HTML 动画流程。"
                        />
                      ) : null}

                      {activeConversation.animationGame.status === 'error' ? (
                        <div className="material-actions">
                          <p className="material-error">
                            {activeConversation.animationGame.error || '生成失败，请稍后重试。'}
                          </p>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => {
                              void generateMaterial(activeConversation.id, 'animation')
                            }}
                          >
                            重新生成
                          </button>
                        </div>
                      ) : null}

                      {activeConversation.animationGame.status === 'done' ? (
                        <div className="material-actions">
                          <p className="material-copy">
                            {activeConversation.animationGame.summary || '动画游戏已经生成完成。'}
                          </p>
                          <div className="material-chip-list">
                            {(activeConversation.animationGame.searchQueries || []).slice(0, 3).map((query) => (
                              <span
                                key={`${activeConversation.id}-animation-query-${query}`}
                                className="material-chip"
                              >
                                {query}
                              </span>
                            ))}
                          </div>
                          <button
                            type="button"
                            className="material-btn"
                            onClick={() => openPreviewPage('animation', activeConversation.id)}
                          >
                            新页面试玩或下载
                          </button>
                        </div>
                      ) : null}
                    </article>
                  </div>
                ) : null}
              </>
            ) : (
              <section className="empty-state">
                <div className="empty-orbit" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
                <h3>从一道题开始今天的备课。</h3>
                <p>先确认讲解答案，再按需要单独生成视频脚本、PPT 提纲和数字动画游戏，最后到新页面里预览或下载。</p>
              </section>
            )}
          </section>

          <section className="cases">
            <div className="section-head">
              <span className="section-tag">灵感问题</span>
              <h3>你也可以从这些题目开始</h3>
            </div>
            <div className="case-grid">
              {sampleCases.map((item) => (
                <button
                  key={item}
                  className="case-card"
                  type="button"
                  onClick={() => onUseCase(item)}
                  disabled={submittingQuestion}
                  title={item}
                >
                  {item}
                </button>
              ))}
            </div>
          </section>
        </div>
      </section>
    </main>
  )
}

export default App
