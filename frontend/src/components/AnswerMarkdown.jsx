import ReactMarkdown from 'react-markdown'

import { normalizeAnswerMarkdown } from '../lib/answerMarkdown'

function ExternalLink(props) {
  const linkProps = { ...props }
  delete linkProps.node

  return <a {...linkProps} target="_blank" rel="noreferrer" />
}

export default function AnswerMarkdown({ content }) {
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
