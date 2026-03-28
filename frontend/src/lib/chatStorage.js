// 对话历史、本地存储和前后端数据结构兼容逻辑都集中在这里。

export const HISTORY_STORAGE_KEY = 'math-ai-chat-history-v4'
export const MAX_HISTORY_ITEMS = 24
const TERTIARY_LEGACY_HISTORY_STORAGE_KEY = 'math-ai-chat-history-v3'
const SECONDARY_LEGACY_HISTORY_STORAGE_KEY = 'math-ai-chat-history-v2'
const LEGACY_HISTORY_STORAGE_KEY = 'math-ai-chat-history-v1'
const DEFAULT_GRADE = 3
const DEFAULT_SEMESTER = '下册'
const DEFAULT_TEXTBOOK_LABEL = '人教版小学数学'

export function createDefaultTeachingPreferences() {
  return {
    teachingGoal: '理解算理',
    studentLevel: '班级标准水平',
    teachingStyle: '老师课堂版',
    commonMisconceptions: '',
  }
}

export function createDefaultOnlineState() {
  return false
}

function normalizeMode(value) {
  if (value === '轻快') {
    return '简洁'
  }

  if (value === '深入') {
    return '详细'
  }

  return value === '简洁' || value === '标准' || value === '详细' ? value : '标准'
}

export function createDefaultTextbookState(grade = DEFAULT_GRADE, semester = DEFAULT_SEMESTER) {
  // 在后端尚未返回教材信息时，先给前端一个稳定的默认教材范围。
  return {
    edition: 'rjb',
    editionLabel: '人教版',
    subject: 'math',
    subjectLabel: '数学',
    publisher: '人民教育出版社',
    grade,
    semester,
    label: `${DEFAULT_TEXTBOOK_LABEL}·${grade}年级${semester}`,
    sourceLabel: '电子课本网',
    sourceUrl: '',
  }
}

function normalizeTextbookState(item, grade = DEFAULT_GRADE, semester = DEFAULT_SEMESTER) {
  const fallback = createDefaultTextbookState(grade, semester)

  if (!item || typeof item !== 'object') {
    return fallback
  }

  const parsedGrade = Number(item.grade)

  return {
    edition: typeof item.edition === 'string' ? item.edition : fallback.edition,
    editionLabel: typeof item.edition_label === 'string' ? item.edition_label : fallback.editionLabel,
    subject: typeof item.subject === 'string' ? item.subject : fallback.subject,
    subjectLabel: typeof item.subject_label === 'string' ? item.subject_label : fallback.subjectLabel,
    publisher: typeof item.publisher === 'string' ? item.publisher : fallback.publisher,
    grade: Number.isInteger(parsedGrade) && parsedGrade >= 1 && parsedGrade <= 6 ? parsedGrade : grade,
    semester: item.semester === '上册' || item.semester === '下册' ? item.semester : semester,
    label: typeof item.label === 'string' && item.label ? item.label : fallback.label,
    sourceLabel: typeof item.source_label === 'string' ? item.source_label : fallback.sourceLabel,
    sourceUrl: typeof item.source_url === 'string' ? item.source_url : fallback.sourceUrl,
  }
}

function normalizeKnowledgePoints(items) {
  // 把后端返回的知识点字段统一成前端内部使用的驼峰结构。
  if (!Array.isArray(items)) {
    return []
  }

  return items.map((item, index) => ({
    docId: typeof item?.doc_id === 'string' ? item.doc_id : `knowledge-${index}`,
    title: typeof item?.title === 'string' ? item.title : '未命名知识点',
    unitTitle: typeof item?.unit_title === 'string' ? item.unit_title : '',
    curriculumLabel: typeof item?.curriculum_label === 'string' ? item.curriculum_label : '',
    summary: typeof item?.summary === 'string' ? item.summary : '',
    example: typeof item?.example === 'string' ? item.example : '',
    conceptTags: Array.isArray(item?.concept_tags) ? item.concept_tags.map((tag) => String(tag)) : [],
    sourceLabel: typeof item?.source_label === 'string' ? item.source_label : '',
    sourceUrl: typeof item?.source_url === 'string' ? item.source_url : '',
  }))
}

function normalizeOnlineResults(items) {
  if (!Array.isArray(items)) {
    return []
  }

  return items.map((item, index) => ({
    id: `${item?.source || 'online'}-${index}`,
    source: typeof item?.source === 'string' ? item.source : '在线搜索',
    title: typeof item?.title === 'string' ? item.title : '未命名文档',
    summary: typeof item?.summary === 'string' ? item.summary : '',
    url: typeof item?.url === 'string' ? item.url : '',
  }))
}

function normalizeTeachingPreferences(item) {
  const fallback = createDefaultTeachingPreferences()

  if (!item || typeof item !== 'object') {
    return fallback
  }

  return {
    teachingGoal:
      typeof item.teachingGoal === 'string'
        ? item.teachingGoal
        : typeof item.teaching_goal === 'string'
          ? item.teaching_goal
          : fallback.teachingGoal,
    studentLevel:
      typeof item.studentLevel === 'string'
        ? item.studentLevel
        : typeof item.student_level === 'string'
          ? item.student_level
          : fallback.studentLevel,
    teachingStyle:
      typeof item.teachingStyle === 'string'
        ? item.teachingStyle
        : typeof item.teaching_style === 'string'
          ? item.teaching_style
          : fallback.teachingStyle,
    commonMisconceptions:
      typeof item.commonMisconceptions === 'string'
        ? item.commonMisconceptions
        : typeof item.common_misconceptions === 'string'
          ? item.common_misconceptions
          : fallback.commonMisconceptions,
  }
}

function normalizeTurns(items, fallbackQuestion, fallbackAnswer, fallbackStatus, fallbackError, createdAt, updatedAt) {
  if (Array.isArray(items) && items.length) {
    return items
      .map((item, index) => {
        const role = item?.role === 'assistant' ? 'assistant' : 'user'
        const status =
          item?.status === 'loading' || item?.status === 'error' || item?.status === 'done'
            ? item.status
            : role === 'assistant'
              ? 'done'
              : 'done'

        return {
          id: typeof item?.id === 'string' ? item.id : `turn-${index}`,
          role,
          content: typeof item?.content === 'string' ? item.content : '',
          status,
          createdAt: typeof item?.createdAt === 'string' ? item.createdAt : role === 'assistant' ? updatedAt : createdAt,
        }
      })
      .filter((item) => item.content || item.status === 'loading' || item.status === 'error')
  }

  const turns = []
  if (fallbackQuestion) {
    turns.push({
      id: 'turn-user-initial',
      role: 'user',
      content: fallbackQuestion,
      status: 'done',
      createdAt,
    })
  }

  if (fallbackStatus === 'loading') {
    turns.push({
      id: 'turn-assistant-loading',
      role: 'assistant',
      content: '',
      status: 'loading',
      createdAt: updatedAt,
    })
  } else if (fallbackStatus === 'error') {
    turns.push({
      id: 'turn-assistant-error',
      role: 'assistant',
      content: typeof fallbackError === 'string' ? fallbackError : '请求失败，请稍后重试。',
      status: 'error',
      createdAt: updatedAt,
    })
  } else if (fallbackAnswer) {
    turns.push({
      id: 'turn-assistant-answer',
      role: 'assistant',
      content: fallbackAnswer,
      status: 'done',
      createdAt: updatedAt,
    })
  }

  return turns
}

export function createConversationId() {
  // 优先使用浏览器原生 UUID，回退时再用时间戳 + 随机串。
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return globalThis.crypto.randomUUID()
  }

  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function createVariationSeed() {
  if (typeof globalThis.crypto?.randomUUID === 'function') {
    return `variant-${globalThis.crypto.randomUUID()}`
  }

  return `variant-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
}

export function createEmptyVideoState() {
  return {
    status: 'idle',
    title: '',
    summary: '',
    downloadPath: '',
    durationSeconds: 0,
    videoSpec: null,
    scenes: [],
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
    demoSpec: null,
    variationSeed: '',
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
      summary: typeof item.summary === 'string' ? item.summary : '',
      downloadPath: typeof item.downloadPath === 'string' ? item.downloadPath : '',
      durationSeconds: Number.isFinite(Number(item.durationSeconds)) ? Number(item.durationSeconds) : 0,
      videoSpec: item.videoSpec && typeof item.videoSpec === 'object' ? item.videoSpec : null,
      scenes: Array.isArray(item.scenes)
        ? item.scenes.map((scene, index) => ({
            title: typeof scene?.title === 'string' ? scene.title : `镜头 ${index + 1}`,
            narration: typeof scene?.narration === 'string' ? scene.narration : '',
            duration_seconds: Number.isFinite(Number(scene?.duration_seconds ?? scene?.durationSeconds))
              ? Number(scene.duration_seconds ?? scene.durationSeconds)
              : 0,
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
    downloadPath: typeof item.download_path === 'string' ? item.download_path : '',
    durationSeconds: Number.isFinite(Number(item.duration_seconds)) ? Number(item.duration_seconds) : 0,
    videoSpec: item.video_spec && typeof item.video_spec === 'object' ? item.video_spec : null,
    scenes: Array.isArray(item.scenes)
      ? item.scenes.map((scene, index) => ({
          title: typeof scene?.title === 'string' ? scene.title : `镜头 ${index + 1}`,
          narration: typeof scene?.narration === 'string' ? scene.narration : '',
          duration_seconds: Number.isFinite(Number(scene?.duration_seconds)) ? Number(scene.duration_seconds) : 0,
        }))
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
        demoSpec: item.demoSpec && typeof item.demoSpec === 'object' ? item.demoSpec : null,
        variationSeed:
          typeof item.variationSeed === 'string'
            ? item.variationSeed
            : typeof item?.demoSpec?.variation_seed === 'string'
              ? item.demoSpec.variation_seed
              : '',
        error: typeof item.error === 'string' ? item.error : '',
        updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : '',
      }
  }

    return {
      status: 'done',
      title: typeof item.title === 'string' ? item.title : '',
      summary: typeof item.summary === 'string' ? item.summary : '',
      html: typeof item.html === 'string' ? item.html : '',
      demoSpec: item.demo_spec && typeof item.demo_spec === 'object' ? item.demo_spec : null,
      variationSeed:
        typeof item.variation_seed === 'string'
          ? item.variation_seed
          : typeof item?.demo_spec?.variation_seed === 'string'
            ? item.demo_spec.variation_seed
            : '',
      error: '',
      updatedAt: '',
    }
  }

export function normalizeConversation(item) {
  // 统一兼容老版本历史记录、当前版本状态字段和后端 snake_case 响应。
  const parsedGrade = Number(item?.grade)
  const normalizedGrade = Number.isInteger(parsedGrade) && parsedGrade >= 1 && parsedGrade <= 6 ? parsedGrade : DEFAULT_GRADE
  const normalizedSemester = item?.semester === '上册' || item?.semester === '下册' ? item.semester : DEFAULT_SEMESTER
  const normalizedGradeMode = item?.gradeMode === 'auto' || item?.gradeMode === 'manual' ? item.gradeMode : 'manual'

  const answerStatus =
    typeof item?.answerStatus === 'string'
      ? item.answerStatus
      : item?.status === 'loading' || item?.status === 'error' || item?.status === 'done'
        ? item.status
        : typeof item?.answer === 'string' && item.answer
          ? 'done'
          : 'idle'

  const createdAt = typeof item?.createdAt === 'string' ? item.createdAt : new Date().toISOString()
  const updatedAt =
    typeof item?.updatedAt === 'string'
      ? item.updatedAt
      : typeof item?.createdAt === 'string'
        ? item.createdAt
        : new Date().toISOString()

  return {
    id: typeof item?.id === 'string' ? item.id : createConversationId(),
    question: typeof item?.question === 'string' ? item.question : '',
    mode: normalizeMode(typeof item?.mode === 'string' ? item.mode : '标准'),
    gradeMode: normalizedGradeMode,
    grade: normalizedGrade,
    semester: normalizedSemester,
    turns: normalizeTurns(
      item?.turns,
      typeof item?.question === 'string' ? item.question : '',
      typeof item?.answer === 'string' ? item.answer : '',
      answerStatus,
      typeof item?.answerError === 'string'
        ? item.answerError
        : item?.status === 'error' && typeof item?.error === 'string'
          ? item.error
          : '',
      createdAt,
      updatedAt,
    ),
    textbook: normalizeTextbookState(item?.textbook, normalizedGrade, normalizedSemester),
    teachingPreferences: normalizeTeachingPreferences(item?.teachingPreferences ?? item?.teaching_preferences),
    networkEnabled: typeof item?.networkEnabled === 'boolean' ? item.networkEnabled : Boolean(item?.network_enabled),
    knowledgePoints: normalizeKnowledgePoints(item?.knowledgePoints ?? item?.knowledge_points),
    onlineResults: normalizeOnlineResults(item?.onlineResults ?? item?.online_results),
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
    createdAt,
    updatedAt,
  }
}

export function loadStoredHistory() {
  // 读取当前版本和历史版本的缓存，尽量无感迁移旧数据。
  if (typeof window === 'undefined') {
    return []
  }

  try {
    const raw =
      window.localStorage.getItem(HISTORY_STORAGE_KEY) ||
      window.localStorage.getItem(TERTIARY_LEGACY_HISTORY_STORAGE_KEY) ||
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
  // 只保留最近 MAX_HISTORY_ITEMS 条，避免本地缓存无限增长。
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
  window.localStorage.removeItem(TERTIARY_LEGACY_HISTORY_STORAGE_KEY)
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
    if (item.animationGame.status === 'done' && !item.animationGame.demoSpec) {
      return '互动动画是旧版本结果，请重新生成。'
    }

    return '已生成讲解答案，可继续预览教学视频、PPT 提纲或互动动画演示。'
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
    if (item.animationGame.status === 'done' && !item.animationGame.demoSpec) {
      return '需要重生成'
    }

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
    if (item.animationGame.status === 'done' && !item.animationGame.demoSpec) {
      return 'error'
    }

    return 'done'
  }

  return 'idle'
}

export function getRouteState() {
  // 主页面和预览页共用一个入口，所以需要从查询参数判断当前路由状态。
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
  // 用查询参数拼出预览页地址，方便新标签页直接打开对应素材。
  if (typeof window === 'undefined') {
    return ''
  }

  const params = new URLSearchParams({
    preview: type,
    id: conversationId,
  })

  return `${window.location.origin}${window.location.pathname}?${params.toString()}`
}
