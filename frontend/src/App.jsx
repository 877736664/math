// 主应用页面，负责对话、历史记录和教学素材生成流程。

import { useEffect, useRef, useState } from 'react'

import AssetLoadingCard from './components/AssetLoadingCard'
import AnswerMarkdown from './components/AnswerMarkdown'
import PreviewPage from './components/PreviewPage'
import ThinkingCard from './components/ThinkingCard'
import './App.css'
import { downloadAnimationHtml } from './lib/materialFiles'
import { splitAnswerSections } from './lib/answerMarkdown'
import {
  MAX_HISTORY_ITEMS,
  buildPreviewUrl,
  clearStoredHistory,
  createConversationId,
  createDefaultTeachingPreferences,
  createDefaultOnlineState,
  createEmptyAnimationGameState,
  createEmptyPptState,
  createVariationSeed,
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
const teachingGoalOptions = ['理解算理', '掌握解题步骤', '强化易错辨析', '学会举一反三']
const studentLevelOptions = ['班级标准水平', '基础偏弱', '基础较好']
const teachingStyleOptions = ['老师课堂版', '启发提问版', '家长辅导版']

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

function buildTeachingPreferencesPayload({ mode, teachingPreferences }) {
  return {
    teaching_goal: teachingPreferences.teachingGoal,
    student_level: teachingPreferences.studentLevel,
    teaching_style: teachingPreferences.teachingStyle,
    common_misconceptions: teachingPreferences.commonMisconceptions.trim(),
    explanation_depth: mode,
  }
}

function buildAnimationThinkingSummary(animationGame) {
  const plan = animationGame?.demoSpec?.animation_plan
  if (!plan || typeof plan !== 'object') {
    return '收到题目后，我会先判断这是一道什么情景题，再决定要用哪种互动方式把题意和数量关系讲清楚。'
  }

  const summary = typeof plan.scene_summary === 'string' ? plan.scene_summary : ''
  const goal = typeof plan.teaching_goal === 'string' ? plan.teaching_goal : ''
  const focus = typeof plan.teaching_focus === 'string' ? plan.teaching_focus : ''

  return [
    summary ? `先识别题目情景：${summary}` : '',
    focus ? `再提炼这道题最该突出的教学重点：${focus}。` : '',
    goal ? `最后把目标定成“${goal}”，保证动画不是只好看，而是真的能帮助学生理解。` : '',
  ]
    .filter(Boolean)
    .join(' ')
}

function buildAnimationDesignSummary(animationGame) {
  const plan = animationGame?.demoSpec?.animation_plan
  if (!plan || typeof plan !== 'object') {
    return '我会把题目拆成几个可观察、可操作的步骤，让学生先看懂题意，再顺着动画理解解析。'
  }

  const interactionModel =
    plan.interaction_model === 'timeline_scrub'
      ? '时间轴拖动'
      : plan.interaction_model === 'step_playback'
        ? '逐步播放'
        : plan.interaction_model === 'progressive_reveal'
          ? '逐层揭示'
          : '分步引导'
  const steps = Array.isArray(plan.storyboard_steps) ? plan.storyboard_steps.slice(0, 4) : []
  const entities = Array.isArray(plan.visual_entities) ? plan.visual_entities.map((item) => item?.name).filter(Boolean).slice(0, 4) : []

  return [
    entities.length ? `素材准备阶段，我会先把 ${entities.join('、')} 放进同一个场景，确保学生一眼能看懂谁和谁在发生关系。` : '',
    steps.length ? `接着把讲解顺序拆成“${steps.join(' → ')}”，让动画像老师一步一步带着学生走。` : '',
    `交互层会采用“${interactionModel}”的方式，让学生边观察边推理，而不是被动看结果。`,
  ]
    .filter(Boolean)
    .join(' ')
}

function getAnimationImageAssets(animationGame) {
  const items = animationGame?.demoSpec?.image_assets
  return Array.isArray(items) ? items.filter((item) => typeof item?.image_url === 'string' && item.image_url) : []
}

function getAnimationHtmlFileName(animationGame) {
  const baseName = String(animationGame?.title || '互动动画演示')
    .replace(/[\\/:*?"<>|]/g, '-')
    .trim()

  return `${baseName || '互动动画演示'}.html`
}

function getAnswerSectionTone(title) {
  if (title === '为什么这样做' || title === '讲解') {
    return 'thinking'
  }
  return 'default'
}

function getAnswerSectionLabel(title) {
  if (title === '为什么这样做' || title === '讲解') {
    return '专业思考'
  }
  return '讲解步骤'
}

function buildAnswerSectionLog(title, question) {
  const normalizedQuestion = String(question || '').trim()

  if (title === '结论') {
    return `我先把题目“${normalizedQuestion}”最终要落到的结果压缩成一句明确结论，方便老师先稳住课堂节奏。`
  }

  if (title === '为什么这样做' || title === '讲解') {
    return '接下来我会先抽出题目里的数量关系，判断这道题应该先讲概念、先讲图意，还是先讲算式。'
  }

  if (title === '分步讲解' || title === '解题步骤') {
    return '然后我按课堂上最自然的讲题顺序，把解题过程拆成几个连续步骤，让学生能一边听一边跟上。'
  }

  return '我会把这一部分整理成老师可以直接接着往下讲的内容。'
}

function getHistoryTaskLabel(item) {
  const text = String(item?.question || '')
    .replace(/\s+/g, ' ')
    .trim()
  if (!text) {
    return '未命名任务'
  }

  return text.length > 16 ? `${text.slice(0, 16)}...` : text
}

function getInitialSidebarWidth() {
  if (typeof window === 'undefined') {
    return 320
  }

  const raw = window.localStorage.getItem('math-ai-sidebar-width')
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? Math.min(420, Math.max(260, parsed)) : 320
}

function App() {
  // 所有主界面状态都集中在这里管理，便于历史记录与预览页共用一份数据源。
  const [route, setRoute] = useState(getRouteState)
  const [history, setHistory] = useState(loadStoredHistory)
  const [activeId, setActiveId] = useState(null)
  const [isDraftConversation, setIsDraftConversation] = useState(false)
  const [historyCollapsed, setHistoryCollapsed] = useState(false)
  const [sidebarWidth, setSidebarWidth] = useState(getInitialSidebarWidth)
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState('标准')
  const [networkEnabled, setNetworkEnabled] = useState(createDefaultOnlineState())
  const [teachingGoal, setTeachingGoal] = useState(createDefaultTeachingPreferences().teachingGoal)
  const [studentLevel, setStudentLevel] = useState(createDefaultTeachingPreferences().studentLevel)
  const [teachingStyle, setTeachingStyle] = useState(createDefaultTeachingPreferences().teachingStyle)
  const [commonMisconceptions, setCommonMisconceptions] = useState(createDefaultTeachingPreferences().commonMisconceptions)
  const [fileName, setFileName] = useState('')
  const [submittingQuestion, setSubmittingQuestion] = useState(false)
  const [composerError, setComposerError] = useState('')
  const [composerMenuOpen, setComposerMenuOpen] = useState(false)
  const [typingAnswer, setTypingAnswer] = useState(null)
  const [activeAnimationStudioId, setActiveAnimationStudioId] = useState(null)
  const fileInputRef = useRef(null)
  const questionInputRef = useRef(null)
  const composerMenuRef = useRef(null)
  const sidebarResizeRef = useRef({ dragging: false })

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
    if (typeof window === 'undefined') {
      return
    }

    window.localStorage.setItem('math-ai-sidebar-width', String(sidebarWidth))
  }, [sidebarWidth])

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
    const handlePointerMove = (event) => {
      if (!sidebarResizeRef.current.dragging || historyCollapsed) {
        return
      }

      const maxWidth = Math.min(460, Math.max(320, window.innerWidth * 0.42))
      const nextWidth = Math.min(maxWidth, Math.max(260, event.clientX))
      setSidebarWidth(nextWidth)
    }

    const stopDragging = () => {
      if (!sidebarResizeRef.current.dragging) {
        return
      }

      sidebarResizeRef.current.dragging = false
      document.body.classList.remove('is-resizing-sidebar')
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', stopDragging)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', stopDragging)
    }
  }, [historyCollapsed])

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
      setTeachingGoal(firstConversation.teachingPreferences?.teachingGoal || defaultTeachingPreferences.teachingGoal)
      setStudentLevel(firstConversation.teachingPreferences?.studentLevel || defaultTeachingPreferences.studentLevel)
      setTeachingStyle(firstConversation.teachingPreferences?.teachingStyle || defaultTeachingPreferences.teachingStyle)
      setCommonMisconceptions(
        firstConversation.teachingPreferences?.commonMisconceptions || defaultTeachingPreferences.commonMisconceptions,
      )
      setNetworkEnabled(Boolean(firstConversation.networkEnabled))
      setFileName(firstConversation.fileName || '')
      setActiveAnimationStudioId(null)
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
  const defaultTeachingPreferences = createDefaultTeachingPreferences()

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
    setTeachingGoal(conversation.teachingPreferences?.teachingGoal || defaultTeachingPreferences.teachingGoal)
    setStudentLevel(conversation.teachingPreferences?.studentLevel || defaultTeachingPreferences.studentLevel)
    setTeachingStyle(conversation.teachingPreferences?.teachingStyle || defaultTeachingPreferences.teachingStyle)
    setCommonMisconceptions(
      conversation.teachingPreferences?.commonMisconceptions || defaultTeachingPreferences.commonMisconceptions,
    )
    setNetworkEnabled(Boolean(conversation.networkEnabled))
    setFileName(conversation.fileName || '')
    setComposerError('')
    setComposerMenuOpen(false)
    setActiveAnimationStudioId(null)
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
    setTeachingGoal(defaultTeachingPreferences.teachingGoal)
    setStudentLevel(defaultTeachingPreferences.studentLevel)
    setTeachingStyle(defaultTeachingPreferences.teachingStyle)
    setCommonMisconceptions(defaultTeachingPreferences.commonMisconceptions)
    setNetworkEnabled(createDefaultOnlineState())
    setFileName('')
    setComposerError('')
    setComposerMenuOpen(false)
    setActiveAnimationStudioId(null)
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
    setTeachingGoal(defaultTeachingPreferences.teachingGoal)
    setStudentLevel(defaultTeachingPreferences.studentLevel)
    setTeachingStyle(defaultTeachingPreferences.teachingStyle)
    setCommonMisconceptions(defaultTeachingPreferences.commonMisconceptions)
    setNetworkEnabled(createDefaultOnlineState())
    setFileName('')
    setComposerError('')
    setComposerMenuOpen(false)
    setActiveAnimationStudioId(null)

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
    const teachingPreferences = {
      teachingGoal,
      studentLevel,
      teachingStyle,
      commonMisconceptions,
    }

    const baseConversation = shouldCreateConversation
      ? normalizeConversation({
          id: conversationId,
          question: finalQuestion,
          mode,
          teachingPreferences,
          networkEnabled,
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
        teachingPreferences,
        networkEnabled,
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
          teaching_preferences: buildTeachingPreferencesPayload({ mode, teachingPreferences }),
          network_enabled: networkEnabled,
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
        onlineResults: Array.isArray(data.online_results) ? data.online_results : item.onlineResults,
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

  const generateMaterial = async (conversationId, type, options = {}) => {
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
      const animationSeed = type === 'animation' ? options.animationSeed || createVariationSeed() : ''
      const response = await fetch(`${API_BASE_URL}/api/${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: getLatestUserQuestion(conversation),
          messages: buildRequestMessages(conversation),
          teaching_preferences: buildTeachingPreferencesPayload({
            mode: conversation.mode,
            teachingPreferences: conversation.teachingPreferences || defaultTeachingPreferences,
          }),
          network_enabled: Boolean(conversation.networkEnabled),
          animation_seed: animationSeed || undefined,
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
        onlineResults: Array.isArray(data.online_results) ? data.online_results : item.onlineResults,
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
                  variationSeed:
                    typeof data?.demo_spec?.variation_seed === 'string'
                      ? data.demo_spec.variation_seed
                      : animationSeed,
                  error: '',
                  updatedAt: new Date().toISOString(),
                },
        updatedAt: new Date().toISOString(),
      }))
      if (type === 'animation') {
        setActiveAnimationStudioId(conversationId)
      }
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
  const activeOnlineResults = Array.isArray(activeConversation?.onlineResults)
    ? activeConversation.onlineResults.slice(0, 6)
    : []
  const canSend = Boolean(question.trim()) && !submittingQuestion
  const recentHistory = history.slice(0, 3)
  const archivedHistory = history.slice(3)
  const effectiveSidebarWidth = historyCollapsed ? 96 : sidebarWidth

  const startSidebarResize = (event) => {
    if (historyCollapsed) {
      return
    }

    sidebarResizeRef.current.dragging = true
    document.body.classList.add('is-resizing-sidebar')
    event.preventDefault()
  }

  return (
    <main className={`layout ${historyCollapsed ? 'layout--history-collapsed' : ''}`} style={{ '--sidebar-width': `${effectiveSidebarWidth}px` }}>
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
            <div className="history-list">
              {history.length ? (
                <>
                  <div className="history-task-group">
                    {recentHistory.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`history-task-item ${item.id === activeId ? 'history-task-item--active' : ''}`}
                        onClick={() => selectConversation(item)}
                        title={item.question}
                      >
                        <span className="history-task-icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24" focusable="false">
                            <path d="M5 6.5h14a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 19 16.5H10.2L6.3 19.4c-.98.72-2.3.02-2.3-1.2V16.5H5A1.5 1.5 0 0 1 3.5 15V8A1.5 1.5 0 0 1 5 6.5Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
                            <path d="M8 10.2h8M8 13.3h4.8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                          </svg>
                        </span>
                        <span className="history-task-label">{getHistoryTaskLabel(item)}</span>
                      </button>
                    ))}
                  </div>

                  {archivedHistory.length ? (
                    <div className="history-task-group history-task-group--archived">
                      <div className="history-task-heading">历史任务</div>
                      {archivedHistory.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className={`history-task-item ${item.id === activeId ? 'history-task-item--active' : ''}`}
                          onClick={() => selectConversation(item)}
                          title={item.question}
                        >
                          <span className="history-task-icon" aria-hidden="true">
                            <svg viewBox="0 0 24 24" focusable="false">
                              <path d="M5 6.5h14a1.5 1.5 0 0 1 1.5 1.5v7A1.5 1.5 0 0 1 19 16.5H10.2L6.3 19.4c-.98.72-2.3.02-2.3-1.2V16.5H5A1.5 1.5 0 0 1 3.5 15V8A1.5 1.5 0 0 1 5 6.5Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
                              <path d="M8 10.2h8M8 13.3h4.8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
                            </svg>
                          </span>
                          <span className="history-task-label">{getHistoryTaskLabel(item)}</span>
                        </button>
                      ))}
                    </div>
                  ) : null}
                </>
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
        {!historyCollapsed ? (
          <button
            type="button"
            className="sidebar-resizer"
            onPointerDown={startSidebarResize}
            aria-label="拖动调整历史栏宽度"
          >
            <span className="sidebar-resizer-grip" aria-hidden="true" />
          </button>
        ) : null}
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
                            {activeConversation.networkEnabled ? <span>联网搜索：开启</span> : null}
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

                  const displayedAnswer = getDisplayedAssistantContent(turn) || activeConversation.answer
                  const answerSections = splitAnswerSections(displayedAnswer)
                  const isAnimationStudioOpen = activeAnimationStudioId === activeConversation.id

                  return (
                    <article key={turn.id} className="message-row message-row--assistant">
                      <div className="chat-message chat-message--assistant chat-message--rich">
                        <article className="content-card answer-card">
                          <div className="stream-shell answer-stream-shell">
                            {answerSections.length ? (
                              answerSections.map((section, index) => (
                                <section
                                  key={`${turn.id}-${section.title}-${index}`}
                                  className={`stream-card stream-card--answer stream-card--${getAnswerSectionTone(section.title)}`}
                                  data-step={Math.min(index + 1, 4)}
                                >
                                  <div className="stream-card-head">
                                    <span className={`stream-badge stream-badge--${getAnswerSectionTone(section.title)}`}>
                                      {getAnswerSectionLabel(section.title)}
                                    </span>
                                  </div>
                                  <div className="stream-section-head">
                                    <h4>{section.title === '讲解' ? '我会这样讲这道题' : section.title}</h4>
                                  </div>
                                  <p className="stream-log-copy">
                                    {buildAnswerSectionLog(section.title, activeConversation.question)}
                                  </p>
                                  <div className="stream-answer-markdown">
                                    <AnswerMarkdown content={section.content} />
                                  </div>
                                </section>
                              ))
                            ) : (
                              <section className="stream-card stream-card--answer stream-card--thinking" data-step="1">
                                <div className="stream-card-head">
                                  <span className="stream-badge">专业思考</span>
                                </div>
                                <div className="stream-section-head">
                                  <h4>我会这样讲这道题</h4>
                                </div>
                                <p className="stream-log-copy">
                                  接到题目后，我会先判断这道题最该先讲清哪个关系，再把答案整理成老师可以直接接着讲的课堂内容。
                                </p>
                                <div className="stream-answer-markdown">
                                  <AnswerMarkdown content={displayedAnswer} />
                                </div>
                              </section>
                            )}

                            {activeKnowledgePoints.length ? (
                              <section className="stream-card stream-card--answer stream-card--knowledge" data-step="4">
                                <div className="stream-card-head">
                                  <span className="stream-badge stream-badge--knowledge">已检索知识点</span>
                                </div>
                                <div className="curriculum-summary curriculum-summary--stream">
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
                              </section>
                            ) : null}

                            {activeConversation.networkEnabled && activeOnlineResults.length ? (
                              <section className="stream-card stream-card--answer stream-card--online" data-step="4">
                                <div className="stream-card-head">
                                  <span className="stream-badge stream-badge--online">联网参考</span>
                                </div>
                                <div className="stream-section-head">
                                  <h4>本次联网检索到的文档</h4>
                                </div>
                                <div className="online-result-list">
                                  {activeOnlineResults.map((item) => (
                                    <a key={item.id} className="online-result-card" href={item.url} target="_blank" rel="noreferrer">
                                      <div className="online-result-top">
                                        <span>{item.source}</span>
                                      </div>
                                      <strong>{item.title}</strong>
                                      {item.summary ? <p>{item.summary}</p> : null}
                                    </a>
                                  ))}
                                </div>
                              </section>
                            ) : null}
                          </div>
                          {isAssistantTyping(turn) ? <span className="typing-cursor" aria-hidden="true" /> : null}
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
                                  description="我会先理解题目情景，再生成图片素材和互动步骤，最后拼成一个当前页可直接体验的教学游戏。"
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
                                      <div className="stream-shell">
                                        <section className="stream-card stream-card--thinking" data-step="1">
                                          <div className="stream-card-head">
                                            <span className="stream-badge">专业思考</span>
                                          </div>
                                          <p className="stream-copy">
                                            {buildAnimationThinkingSummary(activeConversation.animationGame)}
                                          </p>
                                        </section>

                                        {getAnimationImageAssets(activeConversation.animationGame).length ? (
                                          <details className="stream-card stream-card--media" data-step="2" open>
                                            <summary className="stream-summary">
                                              <div>
                                                <span className="stream-badge stream-badge--sage">图片生成</span>
                                                <strong>AI 生成图片列表</strong>
                                              </div>
                                              <span className="stream-toggle-text">展开</span>
                                            </summary>
                                            <div className="stream-gallery">
                                              {getAnimationImageAssets(activeConversation.animationGame).map((item, index) => (
                                                <article
                                                  key={`${activeConversation.id}-animation-image-${index}`}
                                                  className="stream-gallery-card"
                                                >
                                                  <img src={item.image_url} alt={item.query || `动画素材 ${index + 1}`} />
                                                </article>
                                              ))}
                                            </div>
                                          </details>
                                        ) : null}

                                        <section className="stream-card stream-card--thinking" data-step="3">
                                          <div className="stream-card-head">
                                            <span className="stream-badge">专业思考</span>
                                          </div>
                                          <p className="stream-copy">
                                            {buildAnimationDesignSummary(activeConversation.animationGame)}
                                          </p>
                                          <div className="material-chip-list">
                                            {activeConversation.animationGame.demoSpec?.variation_label ? (
                                              <span className="material-chip">
                                                当前版本：{activeConversation.animationGame.demoSpec.variation_label}
                                              </span>
                                            ) : null}
                                            {activeConversation.animationGame.demoSpec?.knowledge_focus?.[0] ? (
                                              <span className="material-chip">
                                                知识点：{activeConversation.animationGame.demoSpec.knowledge_focus[0]}
                                              </span>
                                            ) : null}
                                            {activeConversation.animationGame.demoSpec?.variation_seed ? (
                                              <span className="material-chip">
                                                种子：{String(activeConversation.animationGame.demoSpec.variation_seed).slice(0, 10)}
                                              </span>
                                            ) : null}
                                          </div>
                                        </section>

                                        <section className="stream-card stream-card--playground" data-step="4">
                                          <div className={`artifact-browser artifact-browser--${isAnimationStudioOpen ? 'split' : 'list'}`}>
                                            {!isAnimationStudioOpen ? (
                                              <div className="artifact-browser-list">
                                                <div className="artifact-browser-head">
                                                  <div>
                                                    <span className="section-tag">生成文件</span>
                                                    <h4>已生成 1 个互动动画 HTML</h4>
                                                  </div>
                                                  <p>
                                                    点击后展开左右分栏：左侧查看 HTML/CSS/JS 代码，右侧直接预览运行效果。
                                                  </p>
                                                </div>

                                                <button
                                                  type="button"
                                                  className={`artifact-file-card${isAnimationStudioOpen ? ' is-active' : ''}`}
                                                  onClick={() => setActiveAnimationStudioId(isAnimationStudioOpen ? null : activeConversation.id)}
                                                >
                                                  <div className="artifact-file-card-copy">
                                                    <span className="artifact-file-badge">HTML</span>
                                                    <strong>{getAnimationHtmlFileName(activeConversation.animationGame)}</strong>
                                                    <p>{activeConversation.animationGame.summary || '点击后在右侧直接展开预览。'}</p>
                                                  </div>
                                                  <div className="artifact-file-card-actions">
                                                    <span>{isAnimationStudioOpen ? '收起预览' : '点击预览'}</span>
                                                  </div>
                                                </button>

                                                <div className="material-actions material-actions--artifact">
                                                  <button
                                                    type="button"
                                                    className="material-btn"
                                                    onClick={() => {
                                                      downloadAnimationHtml(activeConversation)
                                                    }}
                                                  >
                                                    下载 .html
                                                  </button>
                                                  <button
                                                    type="button"
                                                    className="material-btn material-btn--secondary"
                                                    onClick={() => {
                                                      void generateMaterial(activeConversation.id, 'animation', {
                                                        animationSeed: createVariationSeed(),
                                                      })
                                                    }}
                                                  >
                                                    换一版动画
                                                  </button>
                                                </div>
                                              </div>
                                            ) : (
                                              <div className="artifact-browser-split">
                                                <div className="artifact-browser-split-pane artifact-browser-split-pane--code">
                                                  <div className="html-studio-pane html-studio-pane--code">
                                                    <div className="html-studio-toolbar">
                                                      <div className="html-studio-tabs">
                                                        <span className="html-studio-tab html-studio-tab--active">HTML 源码</span>
                                                      </div>
                                                      <div className="artifact-preview-actions">
                                                        <button
                                                          type="button"
                                                          className="preview-action preview-action--ghost"
                                                          onClick={() => openPreviewPage('animation', activeConversation.id)}
                                                        >
                                                          新页面打开
                                                        </button>
                                                        <button
                                                          type="button"
                                                          className="preview-action preview-action--ghost"
                                                          onClick={() => setActiveAnimationStudioId(null)}
                                                        >
                                                          收起
                                                        </button>
                                                      </div>
                                                    </div>
                                                    <div className="html-studio-code-shell">
                                                      <pre className="html-studio-code"><code>{activeConversation.animationGame.html}</code></pre>
                                                    </div>
                                                    <div className="html-studio-footer">
                                                      <button
                                                        type="button"
                                                        className="material-btn material-btn--secondary"
                                                        onClick={() => {
                                                          void generateMaterial(activeConversation.id, 'animation', {
                                                            animationSeed: createVariationSeed(),
                                                          })
                                                        }}
                                                      >
                                                        换一版动画
                                                      </button>
                                                      <button
                                                        type="button"
                                                        className="material-btn"
                                                        onClick={() => {
                                                          downloadAnimationHtml(activeConversation)
                                                        }}
                                                      >
                                                        下载 .html
                                                      </button>
                                                    </div>
                                                  </div>
                                                </div>
                                                <div className="artifact-browser-split-pane artifact-browser-split-pane--preview">
                                                  <div className="html-studio-pane html-studio-pane--preview">
                                                    <div className="html-studio-toolbar">
                                                      <div className="html-studio-tabs">
                                                        <span className="html-studio-filetype">{getAnimationHtmlFileName(activeConversation.animationGame)}</span>
                                                      </div>
                                                      <div className="artifact-preview-actions">
                                                        <button
                                                          type="button"
                                                          className="preview-action preview-action--ghost"
                                                          onClick={() => openPreviewPage('animation', activeConversation.id)}
                                                        >
                                                          新页面打开
                                                        </button>
                                                        <button
                                                          type="button"
                                                          className="preview-action preview-action--ghost"
                                                          onClick={() => setActiveAnimationStudioId(null)}
                                                        >
                                                          收起
                                                        </button>
                                                      </div>
                                                    </div>
                                                    <div className="animation-playground-fullscreen">
                                                      <iframe
                                                        className="animation-playground-fullframe"
                                                        title={activeConversation.animationGame.title || '互动动画演示'}
                                                        sandbox="allow-scripts"
                                                        srcDoc={activeConversation.animationGame.html}
                                                      />
                                                    </div>
                                                  </div>
                                                </div>
                                              </div>
                                            )}
                                          </div>
                                        </section>
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

                      <label className="composer-menu-field">
                        <span>教学目标</span>
                        <select
                          className="composer-select"
                          value={teachingGoal}
                          onChange={(event) => setTeachingGoal(event.target.value)}
                          disabled={submittingQuestion}
                        >
                          {teachingGoalOptions.map((item) => (
                            <option key={item} value={item}>
                              {item}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="composer-menu-field">
                        <span>学生基础</span>
                        <select
                          className="composer-select"
                          value={studentLevel}
                          onChange={(event) => setStudentLevel(event.target.value)}
                          disabled={submittingQuestion}
                        >
                          {studentLevelOptions.map((item) => (
                            <option key={item} value={item}>
                              {item}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="composer-menu-field">
                        <span>讲解风格</span>
                        <select
                          className="composer-select"
                          value={teachingStyle}
                          onChange={(event) => setTeachingStyle(event.target.value)}
                          disabled={submittingQuestion}
                        >
                          {teachingStyleOptions.map((item) => (
                            <option key={item} value={item}>
                              {item}
                            </option>
                          ))}
                        </select>
                      </label>

                      <label className="composer-menu-field">
                        <span>易错点提醒</span>
                        <textarea
                          className="composer-textarea"
                          value={commonMisconceptions}
                          onChange={(event) => setCommonMisconceptions(event.target.value)}
                          placeholder="例如：学生容易把面积和周长混淆"
                          disabled={submittingQuestion}
                          rows={3}
                        />
                        <span className="composer-help">不填也可以，系统会按题型自动补一个常见误区。</span>
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

              <div className="composer-network-row">
                <button
                  type="button"
                  className={`composer-network-btn${networkEnabled ? ' is-active' : ''}`}
                  onClick={() => setNetworkEnabled((value) => !value)}
                  disabled={submittingQuestion}
                  aria-pressed={networkEnabled}
                >
                  <span className="composer-network-dot" aria-hidden="true" />
                  联网
                </button>
                <span className="composer-network-note">
                  开启后，这次问题会先补充在线文档搜索结果，再交给大模型生成回答。
                </span>
              </div>

              {mode !== '标准' || teachingGoal !== defaultTeachingPreferences.teachingGoal || studentLevel !== defaultTeachingPreferences.studentLevel || teachingStyle !== defaultTeachingPreferences.teachingStyle || commonMisconceptions.trim() || fileName || networkEnabled ? (
                <div className="composer-status">
                  {networkEnabled ? <span className="composer-status-chip">联网搜索：已开启</span> : null}
                  {mode !== '标准' ? <span className="composer-status-chip">讲解详略：{mode}</span> : null}
                  {teachingGoal !== defaultTeachingPreferences.teachingGoal ? (
                    <span className="composer-status-chip">教学目标：{teachingGoal}</span>
                  ) : null}
                  {studentLevel !== defaultTeachingPreferences.studentLevel ? (
                    <span className="composer-status-chip">学生基础：{studentLevel}</span>
                  ) : null}
                  {teachingStyle !== defaultTeachingPreferences.teachingStyle ? (
                    <span className="composer-status-chip">讲解风格：{teachingStyle}</span>
                  ) : null}
                  {commonMisconceptions.trim() ? <span className="composer-status-chip">已添加易错点提醒</span> : null}
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
