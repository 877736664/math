// 与素材下载相关的浏览器侧工具函数。

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

export function sanitizeFileName(value, fallback) {
  // 清理 Windows 不允许的文件名字符，避免下载时报错。
  const normalized = String(value || '')
    .replace(/[<>:"/\\|?*]/g, ' ')
    .split('')
    .filter((char) => char.charCodeAt(0) >= 32)
    .join('')
    .replace(/\s+/g, ' ')
    .trim()

  return (normalized || fallback).slice(0, 64)
}

export async function downloadTeachingVideo(conversation) {
  // 视频文件由后端生成并托管，这里通过 downloadPath 拉取二进制内容。
  if (!conversation.video.downloadPath) {
    throw new Error('视频文件还没有准备好。')
  }

  const response = await fetch(`${API_BASE_URL}${conversation.video.downloadPath}`)
  if (!response.ok) {
    throw new Error(`下载失败，HTTP ${response.status}`)
  }

  const blob = await response.blob()
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${sanitizeFileName(conversation.video.title, '教学视频')}.mp4`
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export function downloadAnimationHtml(conversation) {
  // 动画 HTML 已经完整保存在历史记录里，因此可以直接本地导出。
  const blob = new Blob([conversation.animationGame.html], { type: 'text/html;charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${sanitizeFileName(conversation.animationGame.title, '互动动画演示')}.html`
  anchor.click()
  window.URL.revokeObjectURL(url)
}

export async function downloadPptFile(conversation) {
  // PPT 下载不是取现成文件，而是把当前提纲重新提交给后端导出成 PPTX。
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
