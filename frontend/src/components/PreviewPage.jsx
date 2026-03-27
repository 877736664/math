// 预览页负责单独展示视频、动画和 PPT 三类已生成素材。

import { useState } from 'react'

import { loadStoredHistory } from '../lib/chatStorage'
import {
  downloadTeachingVideo,
  downloadAnimationHtml,
  downloadPptFile,
} from '../lib/materialFiles'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

function getStoryboardTitle(step, index) {
  const text = String(step || '').trim()
  const parts = text.split(/[：:]/)
  if (parts.length > 1 && parts[0].trim().length <= 12) {
    return parts[0].trim()
  }

  const shortLine = text.split(/[。！？!?]/)[0]?.trim() || ''
  if (shortLine && shortLine.length <= 18) {
    return shortLine
  }

  return `镜头 ${String(index + 1).padStart(2, '0')}`
}

function getStoryboardPhase(index, total) {
  if (index === 0) {
    return '开场设问'
  }

  if (index === total - 1) {
    return '课堂收束'
  }

  if (index === 1) {
    return '条件定位'
  }

  if (index === 2) {
    return '方法判断'
  }

  return '步骤演示'
}

function getStoryboardCue(index, total) {
  if (index === 0) {
    return '画面建议：先把题目场景、人物或关键问题放到镜头前。'
  }

  if (index === total - 1) {
    return '画面建议：回到题目本身，做结果检查或留一个练习题。'
  }

  return '画面建议：镜头聚焦数字、关键词、算式和操作过程。'
}

function PreviewPage({ previewType, previewId }) {
  // 预览页直接从本地历史中取素材，避免重复请求主对话接口。
  const [history] = useState(loadStoredHistory)
  const [downloadState, setDownloadState] = useState({
    busy: false,
    error: '',
  })
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0)

  const conversation = history.find((item) => item.id === previewId) || null
  const mainUrl =
    typeof window === 'undefined'
      ? '/'
      : `${window.location.origin}${window.location.pathname}`

  if (!conversation) {
    return (
      <main className="preview-page">
        <section className="preview-shell preview-shell--empty">
          <p className="preview-kicker">预览页</p>
          <h1>没有找到这条记录</h1>
          <p>这通常是因为浏览器里已经清空了历史记录，或者当前预览链接对应的内容还没有保存。</p>
          <a className="preview-action" href={mainUrl}>
            返回主页面
          </a>
        </section>
      </main>
    )
  }

  const isVideoPreview = previewType === 'video'
  const isAnimationPreview = previewType === 'animation'
  const material = isVideoPreview
    ? conversation.video
    : isAnimationPreview
      ? conversation.animationGame
      : conversation.ppt
  const isMissing = material.status !== 'done'
  const slides = conversation?.ppt?.slides || []
  const clampedSlideIndex = Math.min(currentSlideIndex, Math.max(slides.length - 1, 0))
  const currentSlide = slides[clampedSlideIndex] || null
  const storyboardCards = (conversation?.video?.scenes || []).map((scene, index, allSteps) => ({
    id: `${conversation.id}-story-${index}`,
    stepNumber: index + 1,
    phase: getStoryboardPhase(index, allSteps.length),
    title: scene?.title || getStoryboardTitle(scene?.narration, index),
    body: scene?.narration || '',
    cue: getStoryboardCue(index, allSteps.length),
    duration: Math.round(Number(scene?.duration_seconds || 0)),
  }))

  const downloadMaterial = async () => {
    // 不同素材走不同下载逻辑，但这里统一做交互状态管理。
    setDownloadState({ busy: true, error: '' })

    try {
      if (isVideoPreview) {
        await downloadTeachingVideo(conversation)
      } else if (isAnimationPreview) {
        downloadAnimationHtml(conversation)
      } else {
        await downloadPptFile(conversation)
      }

      setDownloadState({ busy: false, error: '' })
    } catch (error) {
      setDownloadState({
        busy: false,
        error: error instanceof Error ? error.message : '下载失败，请稍后重试。',
      })
    }
  }

  return (
    <main className="preview-page">
      <section className="preview-shell">
        <header className="preview-header">
          <div>
            <p className="preview-kicker">
              {isVideoPreview ? '教学视频预览' : isAnimationPreview ? '互动动画演示预览' : 'PPT 提纲预览'}
            </p>
            <h1>
              {isVideoPreview
                ? conversation.video.title || '教学视频'
                : isAnimationPreview
                  ? conversation.animationGame.title || '互动动画演示'
                  : conversation.ppt.title || 'PPT 提纲'}
            </h1>
            <p className="preview-question">原问题：{conversation.question}</p>
          </div>

          <div className="preview-actions">
            <a className="preview-action preview-action--secondary" href={mainUrl}>
              返回主页面
            </a>
            {!isMissing ? (
              <button
                type="button"
                className="preview-action"
                onClick={() => {
                  void downloadMaterial()
                }}
                disabled={downloadState.busy}
              >
                {downloadState.busy
                  ? '准备下载中…'
                  : isVideoPreview
                    ? '下载 .mp4'
                    : isAnimationPreview
                      ? '下载 .html'
                      : '下载 .pptx'}
              </button>
            ) : null}
          </div>
        </header>

        {downloadState.error ? <p className="preview-error">{downloadState.error}</p> : null}

        {isMissing ? (
          <section className="preview-empty">
            <p>这份内容还没有生成完成。</p>
            <span>请回到主页面，先点击对应的生成按钮。</span>
          </section>
        ) : isVideoPreview ? (
          <section className="preview-document preview-document--storyboard">
            <div className="preview-storyboard-head">
              <div className="preview-storyboard-stat">
                <strong>{Math.max(1, Math.round(conversation.video.durationSeconds || 0))}</strong>
                <span>秒视频时长</span>
              </div>
              <p>
                这是一段已经合成好的教学视频。当前版本使用可替换 TTS 占位音频通路，后续接入正式语音服务后即可升级为真实讲题配音。
              </p>
            </div>

            <div className="preview-video-player-shell">
              <video
                className="preview-video-player"
                controls
                preload="metadata"
                src={`${API_BASE_URL}${conversation.video.downloadPath}`}
              />
            </div>

            <div className="preview-storyboard-grid">
              {storyboardCards.map((card) => (
                <article key={card.id} className="preview-shot-card">
                  <div className="preview-shot-top">
                    <span className="preview-shot-number">{String(card.stepNumber).padStart(2, '0')}</span>
                    <span className="preview-shot-phase">{card.phase}</span>
                  </div>

                  <h2 className="preview-shot-title">{card.title}</h2>
                  <p className="preview-shot-copy">{card.body}</p>

                  <div className="preview-shot-foot">
                    <span className="preview-shot-cue-label">镜头提示</span>
                    <p className="preview-shot-cue">{card.cue}</p>
                    <p className="preview-shot-cue">建议时长：约 {Math.max(1, card.duration)} 秒</p>
                  </div>
                </article>
              ))}
            </div>

            {conversation.video.videoSpec ? (
              <section className="preview-json-card">
                <div className="section-head section-head--compact">
                  <span className="section-tag">模板 JSON</span>
                  <h3>这一版视频使用的结构化模板</h3>
                </div>
                <pre className="preview-json-block">
                  {JSON.stringify(conversation.video.videoSpec, null, 2)}
                </pre>
              </section>
            ) : null}
          </section>
        ) : isAnimationPreview ? (
          <section className="preview-animation">
            <div className="preview-animation-meta">
              <div className="preview-animation-card">
                <span className="preview-animation-label">课堂玩法</span>
                <h2>{conversation.animationGame.summary || '点击按钮，按动画流程一步一步看。'}</h2>
                <p>
                  这份 HTML 是可交互动画演示页。老师可以现场点击开始、上一步、下一步、重播和显示答案，也可以下载成单文件直接带进课堂。
                </p>
              </div>
            </div>

            <div className="preview-animation-stage">
              <iframe
                className="preview-animation-frame"
                title={conversation.animationGame.title || '互动动画演示'}
                sandbox="allow-scripts"
                srcDoc={conversation.animationGame.html}
              />
            </div>
          </section>
        ) : (
          <section className="preview-slide-deck">
            <div className="preview-deck-toolbar">
              <div className="preview-deck-progress">
                <strong>
                  第 {clampedSlideIndex + 1} / {slides.length} 页
                </strong>
                <span>更接近正式幻灯片的翻页预览</span>
              </div>

              <div className="preview-deck-nav">
                <button
                  type="button"
                  className="preview-nav-btn"
                  onClick={() => setCurrentSlideIndex((value) => Math.max(value - 1, 0))}
                  disabled={clampedSlideIndex === 0}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="preview-nav-btn"
                  onClick={() =>
                    setCurrentSlideIndex((value) => Math.min(value + 1, Math.max(slides.length - 1, 0)))
                  }
                  disabled={clampedSlideIndex === slides.length - 1}
                >
                  下一页
                </button>
              </div>
            </div>

            <div className="preview-slide-stage">
              {currentSlide ? (
                <article className="preview-slide-canvas">
                  <div className="preview-slide-surface">
                    <div className="preview-slide-label-row">
                      <span className="preview-slide-label">课堂演示页</span>
                      <span className="preview-slide-page">#{String(clampedSlideIndex + 1).padStart(2, '0')}</span>
                    </div>

                    <h2 className="preview-slide-heading">{currentSlide.title}</h2>

                    <ul className="preview-slide-points">
                      {currentSlide.bullet_points.map((point, pointIndex) => (
                        <li key={`${conversation.id}-preview-point-${clampedSlideIndex}-${pointIndex}`}>
                          <span className="preview-point-index">{pointIndex + 1}</span>
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>

                    <div className="preview-slide-footer">
                      <span>{conversation.ppt.title}</span>
                      <span>适合课堂翻页讲解</span>
                    </div>
                  </div>
                </article>
              ) : null}

              <aside className="preview-thumb-list">
                {slides.map((slide, index) => (
                  <button
                    key={`${conversation.id}-thumb-${index}`}
                    type="button"
                    className={`preview-thumb-card ${index === clampedSlideIndex ? 'preview-thumb-card--active' : ''}`}
                    onClick={() => setCurrentSlideIndex(index)}
                  >
                    <span className="preview-thumb-index">{String(index + 1).padStart(2, '0')}</span>
                    <strong>{slide.title}</strong>
                    <p>{slide.bullet_points[0] || '点击查看这一页内容'}</p>
                  </button>
                ))}
              </aside>
            </div>
          </section>
        )}
      </section>
    </main>
  )
}

export default PreviewPage
