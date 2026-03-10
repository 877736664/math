const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export function sanitizeFileName(value, fallback) {
  const normalized = String(value || '')
    .replace(/[<>:"/\\|?*]/g, ' ')
    .split('')
    .filter((char) => char.charCodeAt(0) >= 32)
    .join('')
    .replace(/\s+/g, ' ')
    .trim()

  return (normalized || fallback).slice(0, 64)
}

export function buildVideoScriptText(conversation) {
  const lines = [
    conversation.video.title || '视频脚本',
    '',
    `原问题：${conversation.question}`,
    '',
    '脚本步骤：',
    ...conversation.video.scriptSteps.map((step, index) => `${index + 1}. ${step}`),
  ]

  return lines.join('\n')
}

export function triggerTextDownload(fileName, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export function downloadAnimationHtml(conversation) {
  const blob = new Blob([conversation.animationGame.html], { type: 'text/html;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${sanitizeFileName(conversation.animationGame.title, '数字动画游戏')}.html`
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export async function downloadPptFile(conversation) {
  const response = await fetch(`${API_BASE_URL}/api/pptx`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: conversation.ppt.title,
      slides: conversation.ppt.slides,
    }),
  })

  if (!response.ok) {
    throw new Error(`下载失败，HTTP ${response.status}`)
  }

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${sanitizeFileName(conversation.ppt.title, '数学课件')}.pptx`
  anchor.click()
  window.URL.revokeObjectURL(url)
}
