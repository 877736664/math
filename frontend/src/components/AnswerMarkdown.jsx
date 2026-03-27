import ReactMarkdown from 'react-markdown'

import { normalizeAnswerMarkdown } from '../lib/answerMarkdown'

function ExternalLink(props) {
  // 所有外链统一新开标签页，避免覆盖当前备课上下文。
  const linkProps = { ...props }
  delete linkProps.node

  return <a {...linkProps} target="_blank" rel="noreferrer" />
}

export default function AnswerMarkdown({ content }) {
  // 先对后端返回内容做轻量标准化，再交给 Markdown 渲染器。
  const markdown = normalizeAnswerMarkdown(content)

  if (!markdown) {
    return null
  }

  return (
    <div className="answer-markdown">
      <ReactMarkdown components={{ a: ExternalLink }}>{markdown}</ReactMarkdown>
    </div>
  )
}
