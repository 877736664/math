export const HISTORY_STORAGE_KEY = 'math-ai-chat-history-v3'
export const MAX_HISTORY_ITEMS = 24
const SECONDARY_LEGACY_HISTORY_STORAGE_KEY = 'math-ai-chat-history-v2'
const LEGACY_HISTORY_STORAGE_KEY = 'math-ai-chat-history-v1'

export function createConversationId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createEmptyVideoState() {
  return {
    status: 'idle',
    title: '',
    scriptSteps: [],
    error: '',
    updatedAt: '',
  }
}

export function createEmptyPptState() {
  return {
    status: 'idle',
    title: '',
    slides: [],
    error: '',
    updatedAt: '',
  }
}

export function createEmptyAnimationGameState() {
  return {
    status: 'idle',
    title: '',
    summary: '',
    html: '',
    searchQueries: [],
    imageSources: [],
    error: '',
    updatedAt: '',
  }
}

function normalizeVideoState(item) {
  if (!item || typeof item !== 'object') {
    return createEmptyVideoState()
  }

  if (typeof item.status === 'string') {
    return {
      status: item.status,
      title: typeof item.title === 'string' ? item.title : '',
      scriptSteps: Array.isArray(item.scriptSteps)
        ? item.scriptSteps.map((step) => String(step))
        : [],
      error: typeof item.error === 'string' ? item.error : '',
      updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : '',
    }
  }

  return {
    status: 'done',
    title: typeof item.title === 'string' ? item.title : '',
    scriptSteps: Array.isArray(item.script_steps)
      ? item.script_steps.map((step) => String(step))
      : [],
    error: '',
    updatedAt: '',
  }
}

function normalizePptState(item) {
  if (!item || typeof item !== 'object') {
    return createEmptyPptState()
  }

  if (typeof item.status === 'string') {
    return {
      status: item.status,
      title: typeof item.title === 'string' ? item.title : '',
      slides: Array.isArray(item.slides)
        ? item.slides.map((slide) => ({
            title: typeof slide?.title === 'string' ? slide.title : '未命名页面',
            bullet_points: Array.isArray(slide?.bullet_points)
              ? slide.bullet_points.map((point) => String(point))
              : [],
          }))
        : [],
      error: typeof item.error === 'string' ? item.error : '',
      updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : '',
    }
  }

  return {
    status: 'done',
    title: typeof item.title === 'string' ? item.title : '',
    slides: Array.isArray(item.slides)
      ? item.slides.map((slide) => ({
          title: typeof slide?.title === 'string' ? slide.title : '未命名页面',
          bullet_points: Array.isArray(slide?.bullet_points)
            ? slide.bullet_points.map((point) => String(point))
            : [],
        }))
      : [],
    error: '',
    updatedAt: '',
  }
}

function normalizeAnimationGameState(item) {
  if (!item || typeof item !== 'object') {
    return createEmptyAnimationGameState()
  }

  if (typeof item.status === 'string') {
    return {
      status: item.status,
      title: typeof item.title === 'string' ? item.title : '',
      summary: typeof item.summary === 'string' ? item.summary : '',
      html: typeof item.html === 'string' ? item.html : '',
      searchQueries: Array.isArray(item.searchQueries)
        ? item.searchQueries.map((value) => String(value))
        : [],
      imageSources: Array.isArray(item.imageSources)
        ? item.imageSources.map((source) => ({
            query: typeof source?.query === 'string' ? source.query : '',
            image_url: typeof source?.image_url === 'string' ? source.image_url : '',
            source_page: typeof source?.source_page === 'string' ? source.source_page : '',
            source_host: typeof source?.source_host === 'string' ? source.source_host : '',
          }))
        : [],
      error: typeof item.error === 'string' ? item.error : '',
      updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : '',
    }
  }

  return {
    status: 'done',
    title: typeof item.title === 'string' ? item.title : '',
    summary: typeof item.summary === 'string' ? item.summary : '',
    html: typeof item.html === 'string' ? item.html : '',
    searchQueries: Array.isArray(item.search_queries)
      ? item.search_queries.map((value) => String(value))
      : [],
    imageSources: Array.isArray(item.image_sources)
      ? item.image_sources.map((source) => ({
          query: typeof source?.query === 'string' ? source.query : '',
          image_url: typeof source?.image_url === 'string' ? source.image_url : '',
          source_page: typeof source?.source_page === 'string' ? source.source_page : '',
          source_host: typeof source?.source_host === 'string' ? source.source_host : '',
        }))
      : [],
    error: '',
    updatedAt: '',
  }
}

export function normalizeConversation(item) {
  const answerStatus =
    typeof item?.answerStatus === 'string'
      ? item.answerStatus
      : item?.status === 'loading' || item?.status === 'error' || item?.status === 'done'
        ? item.status
        : typeof item?.answer === 'string' && item.answer
          ? 'done'
          : 'idle'

  return {
    id: typeof item?.id === 'string' ? item.id : createConversationId(),
    question: typeof item?.question === 'string' ? item.question : '',
    mode: typeof item?.mode === 'string' ? item.mode : '标准',
    fileName: typeof item?.fileName === 'string' ? item.fileName : '',
    answerStatus,
    answer: typeof item?.answer === 'string' ? item.answer : '',
    answerError:
      typeof item?.answerError === 'string'
        ? item.answerError
        : item?.status === 'error' && typeof item?.error === 'string'
          ? item.error
          : '',
    video: normalizeVideoState(item?.video ?? item?.assets?.video),
    ppt: normalizePptState(item?.ppt ?? item?.assets?.ppt),
    animationGame: normalizeAnimationGameState(item?.animationGame),
    createdAt: typeof item?.createdAt === 'string' ? item.createdAt : new Date().toISOString(),
    updatedAt:
      typeof item?.updatedAt === 'string'
        ? item.updatedAt
        : typeof item?.createdAt === 'string'
          ? item.createdAt
          : new Date().toISOString(),
  }
}

export function loadStoredHistory() {
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const raw =
      window.localStorage.getItem(HISTORY_STORAGE_KEY) ||
      window.localStorage.getItem(SECONDARY_LEGACY_HISTORY_STORAGE_KEY) ||
      window.localStorage.getItem(LEGACY_HISTORY_STORAGE_KEY)
    if (!raw) {
      return []
    }

    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }

    return parsed
      .map((item) => normalizeConversation(item))
      .filter((item) => item.question)
      .slice(0, MAX_HISTORY_ITEMS)
  } catch {
    return []
  }
}

export function persistHistory(history) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(
    HISTORY_STORAGE_KEY,
    JSON.stringify(history.slice(0, MAX_HISTORY_ITEMS)),
  )
}

export function clearStoredHistory() {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.removeItem(HISTORY_STORAGE_KEY)
  window.localStorage.removeItem(SECONDARY_LEGACY_HISTORY_STORAGE_KEY)
  window.localStorage.removeItem(LEGACY_HISTORY_STORAGE_KEY)
}

export function formatTime(value) {
  if (!value) {
    return ''
  }

  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return ''
  }
}

export function getPreviewText(item) {
  if (item.answerStatus === 'error') {
    return item.answerError || '这次提问没有成功。'
  }

  if (item.answerStatus === 'loading') {
    return '正在整理这道题的讲解思路。'
  }

  if (
    item.video.status === 'loading' ||
    item.ppt.status === 'loading' ||
    item.animationGame.status === 'loading'
  ) {
    return '正在继续生成教学素材，请稍等一下。'
  }

  if (item.video.status === 'done' || item.ppt.status === 'done' || item.animationGame.status === 'done') {
    return '已生成讲解答案，可继续预览视频脚本、PPT 提纲或动画游戏。'
  }

  if (!item.answer) {
    return '已保存这次提问。'
  }

  return item.answer.length > 44 ? `${item.answer.slice(0, 44)}...` : item.answer
}

export function getStatusLabel(item) {
  if (item.answerStatus === 'loading') {
    return '讲解中'
  }

  if (
    item.video.status === 'loading' ||
    item.ppt.status === 'loading' ||
    item.animationGame.status === 'loading'
  ) {
    return '素材生成中'
  }

  if (item.answerStatus === 'error') {
    return '失败'
  }

  if (item.video.status === 'done' || item.ppt.status === 'done' || item.animationGame.status === 'done') {
    return '素材已生成'
  }

  return '已保存'
}

export function getStatusTone(item) {
  if (
    item.answerStatus === 'loading' ||
    item.video.status === 'loading' ||
    item.ppt.status === 'loading' ||
    item.animationGame.status === 'loading'
  ) {
    return 'loading'
  }

  if (item.answerStatus === 'error') {
    return 'error'
  }

  if (item.video.status === 'done' || item.ppt.status === 'done' || item.animationGame.status === 'done') {
    return 'done'
  }

  return 'idle'
}

export function getRouteState() {
  if (typeof window === 'undefined') {
    return { previewType: '', previewId: '' }
  }

  const params = new URLSearchParams(window.location.search)
  const previewType = params.get('preview')
  const previewId = params.get('id')

  if ((previewType === 'video' || previewType === 'ppt' || previewType === 'animation') && previewId) {
    return { previewType, previewId }
  }

  return { previewType: '', previewId: '' }
}

export function buildPreviewUrl(type, conversationId) {
  if (typeof window === 'undefined') {
    return ''
  }

  const params = new URLSearchParams({
    preview: type,
    id: conversationId,
  })

  return `${window.location.origin}${window.location.pathname}?${params.toString()}`
}
