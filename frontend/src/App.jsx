// 主应用页面，负责对话、历史记录和教学素材生成流程。

import { useEffect, useRef, useState } from 'react'

import AssetLoadingCard from './components/AssetLoadingCard'
import AnswerMarkdown from './components/AnswerMarkdown'
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

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

const sampleCases = [
  '8 + 7 为什么等于 15？请用图示思路讲解。',
  '长方形长 8 厘米、宽 5 厘米，面积怎么计算？',
  '把 3/4 讲给三年级学生听，要有生活例子。',
  '小明有 24 颗糖，平均分给 6 个人，每人多少颗？',
  '比较 0.5 和 1/2，为什么它们相等？',
  '两位数乘一位数怎么验算？给一道练习题。',
]

const modeOptions = ['简洁', '标准', '详细']

function normalizeMode(value) {
  // 兼容旧版本存量数据里的模式命名。
  if (value === '轻快') {
    return '简洁'
  }

  if (value === '深入') {
    return '详细'
  }

  return modeOptions.includes(value) ? value : '标准'
}

function createTurn(role, content, status = 'done') {
  // 统一创建一条对话消息，方便前后续状态更新时复用。
  return {
    id: createConversationId(),
    role,
    content,
    status,
    createdAt: new Date().toISOString(),
  }
}

function getLatestUserQuestion(conversation) {
  const turns = Array.isArray(conversation?.turns) ? conversation.turns : []

  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index]?.role === 'user' && turns[index]?.content) {
      return String(turns[index].content)
    }
  }

  return conversation?.question || ''
}

function buildRequestMessages(conversation, pendingUserContent = '') {
  // 只把已经完成的用户/助手消息发给后端，避免把 loading/error 状态传过去。
  const turns = Array.isArray(conversation?.turns) ? conversation.turns : []
  const messages = turns
    .filter((turn) => (turn.role === 'user' || turn.role === 'assistant') && turn.status === 'done' && turn.content)
    .map((turn) => ({
      role: turn.role,
      content: turn.content,
    }))

  const nextMessage = String(pendingUserContent || '').trim()
  if (nextMessage) {
    messages.push({ role: 'user', content: nextMessage })
  }

  return messages.slice(-12)
}

function App() {
  // 所有主界面状态都集中在这里管理，便于历史记录与预览页共用一份数据源。
  const [route, setRoute] = useState(getRouteState)
  const [history, setHistory] = useState(loadStoredHistory)
  const [activeId, setActiveId] = useState(null)
  const [isDraftConversation, setIsDraftConversation] = useState(false)
  const [historyCollapsed, setHistoryCollapsed] = useState(false)
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState('标准')
  const [fileName, setFileName] = useState('')
  const [submittingQuestion, setSubmittingQuestion] = useState(false)
  const [composerError, setComposerError] = useState('')
  const [composerMenuOpen, setComposerMenuOpen] = useState(false)
  const [typingAnswer, setTypingAnswer] = useState(null)
  const fileInputRef = useRef(null)
  const questionInputRef = useRef(null)
  const composerMenuRef = useRef(null)

  useEffect(() => {
    const element = questionInputRef.current
    if (!element) {
      return
    }

    element.style.height = '40px'
    const nextHeight = Math.min(element.scrollHeight, 224)
    element.style.height = `${Math.max(nextHeight, 40)}px`
    element.style.overflowY = element.scrollHeight > 224 ? 'auto' : 'hidden'
  }, [question])

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
    const handlePointerDown = (event) => {
      if (!composerMenuRef.current?.contains(event.target)) {
        setComposerMenuOpen(false)
      }
    }

    window.addEventListener('pointerdown', handlePointerDown)
    return () => {
      window.removeEventListener('pointerdown', handlePointerDown)
    }
  }, [])

  useEffect(() => {
    if (!typingAnswer?.fullContent) {
      return
    }

    const timer = window.setInterval(() => {
      setTypingAnswer((current) => {
        if (!current) {
          return null
        }

        const nextLength = Math.min(current.length + 3, current.fullContent.length)
        if (nextLength >= current.fullContent.length) {
          return null
        }

        return {
          ...current,
          length: nextLength,
        }
      })
    }, 24)

    return () => {
      window.clearInterval(timer)
    }
  }, [typingAnswer])

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
      if (!history.length && isDraftConversation) {
        setIsDraftConversation(false)
      }
      return
    }

    const hasActiveConversation = history.some((item) => item.id === activeId)
    if (!hasActiveConversation) {
      if (isDraftConversation) {
        return
      }

      const firstConversation = history[0]
      setActiveId(firstConversation.id)
      setQuestion('')
      setMode(normalizeMode(firstConversation.mode))
      setFileName(firstConversation.fileName || '')
    }
  }, [activeId, history, isDraftConversation, route.previewType])

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
    // 对指定对话做原子更新，并始终保持最新记录排在最前面。
    setHistory((previousHistory) => {
      const currentConversation = previousHistory.find((item) => item.id === conversationId)
      if (!currentConversation) {
        return previousHistory
      }

      const nextItem = typeof updater === 'function' ? updater(currentConversation) : updater
      const normalizedConversation = normalizeConversation(nextItem)
      const remainingHistory = previousHistory.filter((item) => item.id !== conversationId)
      return [normalizedConversation, ...remainingHistory].slice(0, MAX_HISTORY_ITEMS)
    })
  }

  const getDisplayedAssistantContent = (turn) => {
    if (!turn?.content) {
      return ''
    }

    if (typingAnswer?.turnId === turn.id) {
      return typingAnswer.fullContent.slice(0, typingAnswer.length)
    }

    return turn.content
  }

  const isAssistantTyping = (turn) => typingAnswer?.turnId === turn?.id
  const isLegacyAnimationResult = (conversation) =>
    Boolean(conversation?.animationGame?.status === 'done' && !conversation?.animationGame?.demoSpec)

  const openFilePicker = () => {
    setComposerMenuOpen(false)
    fileInputRef.current?.click()
  }

  const onPickFile = (event) => {
    const targetFile = event.target.files?.[0]
    setFileName(targetFile ? targetFile.name : '')
  }

  const selectConversation = (conversation) => {
    setActiveId(conversation.id)
    setIsDraftConversation(false)
    setTypingAnswer(null)
    setQuestion('')
    setMode(normalizeMode(conversation.mode))
    setFileName(conversation.fileName || '')
    setComposerError('')
    setComposerMenuOpen(false)
  }

  const clearHistory = () => {
    if (submittingQuestion) {
      return
    }

    setHistory([])
    setActiveId(null)
    setIsDraftConversation(false)
    setTypingAnswer(null)
    setQuestion('')
    setFileName('')
    setComposerError('')
    setComposerMenuOpen(false)
    clearStoredHistory()
  }

  const startNewConversation = () => {
    if (submittingQuestion) {
      return
    }

    setActiveId(null)
    setIsDraftConversation(true)
    setTypingAnswer(null)
    setQuestion('')
    setFileName('')
    setComposerError('')
    setComposerMenuOpen(false)

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const submitQuestion = async (nextQuestion) => {
    // 提问总入口：先落本地历史，再请求问答接口，并把返回结果写回当前会话。
    const finalQuestion = (nextQuestion ?? question).trim()

    if (!finalQuestion || submittingQuestion) {
      if (!finalQuestion) {
        setComposerError('请输入一个具体的问题。')
      }
      return
    }

    const timestamp = new Date().toISOString()
    const shouldCreateConversation = !activeConversation
    const conversationId = shouldCreateConversation ? createConversationId() : activeConversation.id
    const userTurn = createTurn('user', finalQuestion)
    const assistantTurn = createTurn('assistant', '', 'loading')

    const baseConversation = shouldCreateConversation
      ? normalizeConversation({
          id: conversationId,
          question: finalQuestion,
          mode,
          turns: [userTurn, assistantTurn],
          knowledgePoints: [],
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
      : null
    const messages = shouldCreateConversation
      ? buildRequestMessages(null, finalQuestion)
      : buildRequestMessages(activeConversation, finalQuestion)

    setSubmittingQuestion(true)
    setComposerError('')
    setComposerMenuOpen(false)
    setIsDraftConversation(false)
    setTypingAnswer(null)
    setActiveId(conversationId)
    setQuestion('')
    setFileName('')

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }

    if (shouldCreateConversation) {
      setHistory((previousHistory) => [baseConversation, ...previousHistory].slice(0, MAX_HISTORY_ITEMS))
    } else {
      updateConversation(conversationId, (item) => ({
        ...item,
        question: finalQuestion,
        mode,
        fileName,
        answerStatus: 'loading',
        answerError: '',
        turns: [...(Array.isArray(item.turns) ? item.turns : []), userTurn, assistantTurn],
        updatedAt: timestamp,
      }))
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/qa`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: finalQuestion,
          messages,
        }),
      })

      if (!response.ok) {
        throw new Error(`请求失败，HTTP ${response.status}`)
      }

      const data = await response.json()
      const finalAnswer = data.answer || '已生成讲解答案。'

      setTypingAnswer({
        turnId: assistantTurn.id,
        fullContent: finalAnswer,
        length: 0,
      })

      updateConversation(conversationId, (item) => ({
        ...item,
        answerStatus: 'done',
        answer: finalAnswer,
        turns: (Array.isArray(item.turns) ? item.turns : []).map((turn) =>
          turn.id === assistantTurn.id
            ? {
                ...turn,
                content: finalAnswer,
                status: 'done',
                createdAt: new Date().toISOString(),
              }
            : turn,
        ),
        textbook: data.textbook || item.textbook,
        knowledgePoints: Array.isArray(data.knowledge_points) ? data.knowledge_points : item.knowledgePoints,
        answerError: '',
        updatedAt: new Date().toISOString(),
      }))
    } catch (error) {
      updateConversation(conversationId, (item) => ({
        ...item,
        answerStatus: 'error',
        answerError: error instanceof Error ? error.message : '请求失败，请稍后重试。',
        answer: '',
        turns: (Array.isArray(item.turns) ? item.turns : []).map((turn) =>
          turn.id === assistantTurn.id
            ? {
                ...turn,
                content: error instanceof Error ? error.message : '请求失败，请稍后重试。',
                status: 'error',
                createdAt: new Date().toISOString(),
              }
            : turn,
        ),
        updatedAt: new Date().toISOString(),
      }))
    } finally {
      setSubmittingQuestion(false)
    }
  }

  const generateMaterial = async (conversationId, type) => {
    // 素材生成入口：根据类型调用不同接口，但都写回同一条对话记录。
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
          ? 'teaching-video'
          : type === 'ppt'
            ? 'ppt-outline'
            : 'animation-game'
      const response = await fetch(`${API_BASE_URL}/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: getLatestUserQuestion(conversation),
          messages: buildRequestMessages(conversation),
        }),
      })

      if (!response.ok) {
        throw new Error(`请求失败，HTTP ${response.status}`)
      }

      const data = await response.json()

      updateConversation(conversationId, (item) => ({
        ...item,
        textbook: data.textbook || item.textbook,
        knowledgePoints: Array.isArray(data.knowledge_points) ? data.knowledge_points : item.knowledgePoints,
        [materialKey]:
          type === 'video'
            ? {
                status: 'done',
                title: data.title || '教学视频',
                summary: data.summary || '已生成可播放的教学视频。',
                downloadPath: typeof data.download_path === 'string' ? data.download_path : '',
                durationSeconds: Number.isFinite(Number(data.duration_seconds)) ? Number(data.duration_seconds) : 0,
                videoSpec: data.video_spec && typeof data.video_spec === 'object' ? data.video_spec : null,
                scenes: Array.isArray(data.scenes)
                  ? data.scenes.map((scene, index) => ({
                      title: typeof scene?.title === 'string' ? scene.title : `镜头 ${index + 1}`,
                      narration: typeof scene?.narration === 'string' ? scene.narration : '',
                      duration_seconds: Number.isFinite(Number(scene?.duration_seconds))
                        ? Number(scene.duration_seconds)
                        : 0,
                    }))
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
                  title: data.title || '互动动画演示',
                  summary: data.summary || '已生成可在线预览的互动动画演示。',
                  html: data.html || '',
                  demoSpec: data.demo_spec && typeof data.demo_spec === 'object' ? data.demo_spec : null,
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
    // 预览前先持久化历史，保证新标签页能从本地存储读到最新结果。
    if (type === 'animation') {
      const conversation = history.find((item) => item.id === conversationId)
      if (isLegacyAnimationResult(conversation)) {
        updateConversation(conversationId, (item) => ({
          ...item,
          animationGame: {
            ...item.animationGame,
            status: 'error',
            error: '这个互动动画是旧版本结果，请重新点击“生成互动动画”。',
            updatedAt: new Date().toISOString(),
          },
          updatedAt: new Date().toISOString(),
        }))
        return
      }
    }

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

  const activeTurns = Array.isArray(activeConversation?.turns) ? activeConversation.turns : []
  const latestAssistantTurnId = [...activeTurns]
    .reverse()
    .find((turn) => turn.role === 'assistant')?.id
  const activeKnowledgePoints = Array.isArray(activeConversation?.knowledgePoints)
    ? activeConversation.knowledgePoints.slice(0, 4)
    : []
  const canSend = Boolean(question.trim()) && !submittingQuestion

  return (
    <main className={`layout ${historyCollapsed ? 'layout--history-collapsed' : ''}`}>
      <aside className={`sidebar ${historyCollapsed ? 'sidebar--collapsed' : ''}`}>
        <div className="sidebar-toolbar sidebar-toolbar--top">
          <div className="sidebar-toolbar-copy">
            <p className="sidebar-kicker">拾光备课</p>
            {!historyCollapsed ? <span className="history-count">{history.length ? `已保存 ${history.length} 条记录` : '还没有保存的对话'}</span> : null}
          </div>

          <div className="sidebar-toolbar-actions">
            {!historyCollapsed ? (
              <>
                <button type="button" className="history-action" onClick={startNewConversation} disabled={submittingQuestion}>
                  新对话
                </button>
                <button type="button" className="history-clear" onClick={clearHistory} disabled={submittingQuestion}>
                  清空
                </button>
              </>
            ) : null}
            <button
              type="button"
              className={`history-toggle ${historyCollapsed ? 'history-toggle--collapsed' : ''}`}
              onClick={() => setHistoryCollapsed((value) => !value)}
              aria-label={historyCollapsed ? '展开历史对话' : '收起历史对话'}
              aria-expanded={!historyCollapsed}
            >
              <span className="history-toggle-icon" aria-hidden="true" />
              <span>{historyCollapsed ? '展开' : '收起'}</span>
            </button>
          </div>
        </div>

        {!historyCollapsed ? (
          <>
            <div className="sidebar-header">
              <h1>历史对话</h1>
              <p>每次提问都会自动保存。点击历史记录，可以继续生成教学视频、PPT 提纲或互动动画演示。</p>
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
          </>
        ) : (
          <div className="sidebar-collapsed-note">
            <strong>{history.length}</strong>
            <span>条历史对话</span>
          </div>
        )}
      </aside>

      <section className="workspace">
        <div className="workspace-shell workspace-shell--chat">
          <section className="chat-shell">
            <header className="chat-header">
              <p className="hero-kicker">小学数学 AI 教学平台</p>
              <h2>像对话一样开始备课</h2>
              <p>直接把题目发给我。我会先给出讲解答案，再继续生成教学视频、PPT 提纲和互动动画演示。</p>
            </header>

            <section className="conversation-panel conversation-panel--chat">
              {!activeConversation ? (
                <article className="message-row message-row--assistant">
                  <div className="chat-message chat-message--assistant chat-message--welcome">
                    <div className="section-head section-head--compact">
                      <span className="section-tag">AI 助教</span>
                      <h3>先发一道题，我来陪你一步步备课。</h3>
                    </div>
                    <p className="welcome-copy">
                      你可以直接发数学题，也可以说“把这道题讲给三年级学生听”。我会先生成讲解，再按需扩展成素材。
                    </p>
                    <div className="section-head section-head--compact">
                      <span className="section-tag">灵感问题</span>
                      <h3>也可以从这些问题开始</h3>
                    </div>
                    <div className="case-grid case-grid--compact">
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
                  </div>
                </article>
              ) : (
                activeTurns.map((turn) => {
                  if (turn.role === 'user') {
                    return (
                      <article key={turn.id} className="message-row message-row--user">
                        <div className="chat-message chat-message--user">
                          <div className="bubble-top">
                            <span>你</span>
                            <time>{formatTime(turn.createdAt)}</time>
                          </div>
                          <p>{turn.content}</p>
                          <div className="bubble-meta">
                            <span>讲解方式：{normalizeMode(activeConversation.mode)}</span>
                            <span>{activeConversation.fileName ? `附件：${activeConversation.fileName}` : '未添加附件'}</span>
                          </div>
                        </div>
                      </article>
                    )
                  }

                  if (turn.status === 'loading') {
                    return (
                      <article key={turn.id} className="message-row message-row--assistant">
                        <div className="chat-message chat-message--assistant chat-message--loading">
                          <ThinkingCard />
                        </div>
                      </article>
                    )
                  }

                  if (turn.status === 'error') {
                    return (
                      <article key={turn.id} className="message-row message-row--assistant">
                        <div className="chat-message chat-message--assistant content-card error-card">
                          <div className="section-head">
                            <span className="section-tag">请求失败</span>
                            <h3>这次讲解没有生成成功</h3>
                          </div>
                          <p>{turn.content || activeConversation.answerError || '请稍后再试一次。'}</p>
                        </div>
                      </article>
                    )
                  }

                  if (turn.id !== latestAssistantTurnId) {
                    return (
                      <article key={turn.id} className="message-row message-row--assistant">
                        <div className="chat-message chat-message--assistant chat-message--history-answer">
                          <div className="bubble-top">
                            <span>AI 助教</span>
                            <time>{formatTime(turn.createdAt)}</time>
                          </div>
                          <AnswerMarkdown content={getDisplayedAssistantContent(turn)} />
                          {isAssistantTyping(turn) ? <span className="typing-cursor" aria-hidden="true" /> : null}
                        </div>
                      </article>
                    )
                  }

                  return (
                    <article key={turn.id} className="message-row message-row--assistant">
                      <div className="chat-message chat-message--assistant chat-message--rich">
                        <article className="content-card answer-card">
                          <div className="section-head">
                            <span className="section-tag">讲解答案</span>
                            <h3>我会这样讲这道题</h3>
                          </div>
                          <AnswerMarkdown content={getDisplayedAssistantContent(turn) || activeConversation.answer} />
                          {isAssistantTyping(turn) ? <span className="typing-cursor" aria-hidden="true" /> : null}
                          {activeKnowledgePoints.length ? (
                            <div className="curriculum-summary">
                              <div className="curriculum-hit-list">
                                {activeKnowledgePoints.map((item) => (
                                  <article key={item.docId} className="curriculum-hit-card">
                                    <div className="curriculum-hit-top">
                                      <strong>{item.title}</strong>
                                      <span>{item.unitTitle}</span>
                                    </div>
                                    <p>{item.summary}</p>
                                  </article>
                                ))}
                              </div>
                            </div>
                          ) : null}
                          <div className="answer-tools">
                            <div className="section-head section-head--compact">
                              <span className="section-tag">继续生成</span>
                              <h3>按这次提问，一键扩展成课堂素材</h3>
                            </div>
                            <div className="material-action-row">
                              <button
                                type="button"
                                className={`material-trigger${activeConversation.video.status === 'done' ? ' is-ready' : ''}`}
                                onClick={() => {
                                  void generateMaterial(activeConversation.id, 'video')
                                }}
                                disabled={activeConversation.video.status === 'loading'}
                              >
                                {activeConversation.video.status === 'loading' ? '教学视频生成中…' : '生成教学视频'}
                              </button>
                              <button
                                type="button"
                                className={`material-trigger${activeConversation.ppt.status === 'done' ? ' is-ready' : ''}`}
                                onClick={() => {
                                  void generateMaterial(activeConversation.id, 'ppt')
                                }}
                                disabled={activeConversation.ppt.status === 'loading'}
                              >
                                {activeConversation.ppt.status === 'loading' ? 'PPT 提纲生成中…' : '生成 PPT 提纲'}
                              </button>
                              <button
                                type="button"
                                className={`material-trigger${activeConversation.animationGame.status === 'done' ? ' is-ready' : ''}`}
                                onClick={() => {
                                  void generateMaterial(activeConversation.id, 'animation')
                                }}
                                disabled={activeConversation.animationGame.status === 'loading'}
                              >
                                {activeConversation.animationGame.status === 'loading' ? '互动动画生成中…' : '生成互动动画'}
                              </button>
                            </div>

                            <div className="material-inline-stack">
                              {activeConversation.video.status === 'loading' ? (
                                <AssetLoadingCard
                                  title="正在生成教学视频"
                                  description="我会把这道题整理成画面分镜，并用占位 TTS 音频合成成可播放视频。"
                                />
                              ) : null}

                              {activeConversation.video.status === 'error' ? (
                                <div className="material-inline-card">
                                  <div className="section-head section-head--compact">
                                    <span className="section-tag">教学视频</span>
                                    <h3>生成失败</h3>
                                  </div>
                                  <p className="material-error">{activeConversation.video.error || '生成失败，请稍后重试。'}</p>
                                </div>
                              ) : null}

                              {activeConversation.video.status === 'done' ? (
                                <div className="material-inline-card">
                                  <div className="section-head section-head--compact">
                                    <span className="section-tag">教学视频</span>
                                    <h3>{activeConversation.video.title || '教学视频'}</h3>
                                  </div>
                                  <p className="material-copy">{activeConversation.video.summary || '教学视频已经生成完成。'}</p>
                                  <div className="material-chip-list">
                                    <span className="material-chip">
                                      时长约 {Math.max(1, Math.round(activeConversation.video.durationSeconds || 0))} 秒
                                    </span>
                                    <span className="material-chip">
                                      {(activeConversation.video.scenes || []).length} 个分镜
                                    </span>
                                  </div>
                                  <ol className="steps-list">
                                    {(activeConversation.video.scenes || []).slice(0, 3).map((scene, index) => (
                                      <li key={`${activeConversation.id}-video-scene-${index}`}>
                                        <strong>{scene.title}</strong>：{scene.narration}
                                      </li>
                                    ))}
                                  </ol>
                                  <div className="material-actions">
                                    <button
                                      type="button"
                                      className="material-btn"
                                      onClick={() => openPreviewPage('video', activeConversation.id)}
                                    >
                                      新页面预览或下载
                                    </button>
                                  </div>
                                </div>
                              ) : null}

                              {activeConversation.ppt.status === 'loading' ? (
                                <AssetLoadingCard
                                  title="正在生成 PPT 提纲"
                                  description="我会把讲题步骤拆成适合课件排版的页面结构。"
                                />
                              ) : null}

                              {activeConversation.ppt.status === 'error' ? (
                                <div className="material-inline-card">
                                  <div className="section-head section-head--compact">
                                    <span className="section-tag">PPT 提纲</span>
                                    <h3>生成失败</h3>
                                  </div>
                                  <p className="material-error">{activeConversation.ppt.error || '生成失败，请稍后重试。'}</p>
                                </div>
                              ) : null}

                              {activeConversation.ppt.status === 'done' ? (
                                <div className="material-inline-card">
                                  <div className="section-head section-head--compact">
                                    <span className="section-tag">PPT 提纲</span>
                                    <h3>{activeConversation.ppt.title || 'PPT 提纲'}</h3>
                                  </div>
                                  <div className="slide-list">
                                    {activeConversation.ppt.slides.slice(0, 3).map((slide, index) => (
                                      <div key={`${activeConversation.id}-ppt-snippet-${index}`} className="slide-card">
                                        <strong>{slide.title}</strong>
                                        <p>{slide.bullet_points.join(' / ')}</p>
                                      </div>
                                    ))}
                                  </div>
                                  <div className="material-actions">
                                    <button
                                      type="button"
                                      className="material-btn"
                                      onClick={() => openPreviewPage('ppt', activeConversation.id)}
                                    >
                                      新页面预览或下载
                                    </button>
                                  </div>
                                </div>
                              ) : null}

                              {activeConversation.animationGame.status === 'loading' ? (
                                <AssetLoadingCard
                                  title="正在生成互动动画演示"
                                  description="我会按题意生成可交互的 HTML 动画，用来上课演示。"
                                />
                              ) : null}

                              {activeConversation.animationGame.status === 'error' ? (
                                <div className="material-inline-card">
                                  <div className="section-head section-head--compact">
                                    <span className="section-tag">互动动画演示</span>
                                    <h3>生成失败</h3>
                                  </div>
                                  <p className="material-error">
                                    {activeConversation.animationGame.error || '生成失败，请稍后重试。'}
                                  </p>
                                </div>
                              ) : null}

                              {activeConversation.animationGame.status === 'done' ? (
                                <div className="material-inline-card">
                                  <div className="section-head section-head--compact">
                                    <span className="section-tag">互动动画演示</span>
                                    <h3>{activeConversation.animationGame.title || '互动动画演示'}</h3>
                                  </div>
                                  {isLegacyAnimationResult(activeConversation) ? (
                                    <div className="material-actions">
                                      <p className="material-error">这个互动动画是旧版本结果，请重新生成后再预览。</p>
                                      <button
                                        type="button"
                                        className="material-btn"
                                        onClick={() => {
                                          void generateMaterial(activeConversation.id, 'animation')
                                        }}
                                      >
                                        重新生成互动动画
                                      </button>
                                    </div>
                                  ) : (
                                    <>
                                      <p className="material-copy">
                                        {activeConversation.animationGame.summary || '互动动画演示已经生成完成。'}
                                      </p>
                                      <div className="material-actions">
                                        <button
                                          type="button"
                                          className="material-btn"
                                          onClick={() => openPreviewPage('animation', activeConversation.id)}
                                        >
                                          新页面演示或下载
                                        </button>
                                      </div>
                                    </>
                                  )}
                                </div>
                              ) : null}
                            </div>
                          </div>
                        </article>
                      </div>
                    </article>
                  )
                })
              )}
            </section>

            <form className="input-shell composer-shell" onSubmit={onSubmit}>
              <label className="input-label input-label--sr-only" htmlFor="question-input">
                给 AI 发一条消息
              </label>
              <div className="composer-main">
                <textarea
                  ref={questionInputRef}
                  id="question-input"
                  className="question-input question-input--chat"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={onQuestionKeyDown}
                  placeholder="给 AI 发消息"
                  disabled={submittingQuestion}
                  rows={1}
                />

                <div className="composer-menu-wrap" ref={composerMenuRef}>
                  <button
                    type="button"
                    className={`composer-menu-btn${composerMenuOpen ? ' is-active' : ''}`}
                    onClick={() => setComposerMenuOpen((value) => !value)}
                    disabled={submittingQuestion}
                    aria-label="更多选项"
                    aria-expanded={composerMenuOpen}
                  >
                    +
                  </button>

                  {composerMenuOpen ? (
                    <div className="composer-menu" role="menu" aria-label="更多选项">
                      <div className="composer-menu-head">
                        <strong>工具面板</strong>
                        <span>调整讲解方式，或补充一份附件。</span>
                      </div>

                      <label className="composer-menu-field">
                        <span>讲解方式</span>
                        <div className="mode-pill-group" role="group" aria-label="讲解方式">
                          {modeOptions.map((item) => (
                            <button
                              key={item}
                              type="button"
                              className={`mode-pill${mode === item ? ' is-active' : ''}`}
                              onClick={() => setMode(item)}
                              disabled={submittingQuestion}
                              aria-pressed={mode === item}
                            >
                              {item}
                            </button>
                          ))}
                        </div>
                      </label>

                      <div className="composer-menu-group">
                        <span className="composer-menu-group-title">附件</span>
                        <button
                          type="button"
                          className="composer-menu-action"
                          onClick={openFilePicker}
                          disabled={submittingQuestion}
                        >
                          {fileName ? `已选择：${fileName}` : '添加附件'}
                        </button>
                      </div>
                    </div>
                  ) : null}
                </div>

                <button
                  type="submit"
                  className="send-btn send-btn--round"
                  disabled={!canSend}
                  aria-label="开始生成讲解"
                >
                  <svg className="send-icon" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      d="M4 11.5L18.2 5.6c.8-.3 1.6.4 1.3 1.3l-5.9 14.2c-.4.9-1.6.9-2 0l-2.1-5.1-5.1-2.1c-.9-.4-.9-1.6 0-2Z"
                      fill="currentColor"
                    />
                  </svg>
                </button>
              </div>

              {mode !== '标准' || fileName ? (
                <div className="composer-status">
                  {mode !== '标准' ? <span className="composer-status-chip">讲解方式：{mode}</span> : null}
                  {fileName ? <span className="composer-status-chip">附件：{fileName}</span> : null}
                </div>
              ) : null}

              {composerError ? <p className="error-hint">{composerError}</p> : null}
            </form>

            <input
              ref={fileInputRef}
              type="file"
              onChange={onPickFile}
              hidden
              aria-hidden="true"
            />
          </section>
        </div>
      </section>
    </main>
  )
}

export default App
