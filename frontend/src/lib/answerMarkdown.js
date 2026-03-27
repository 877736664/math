// 把后端可能返回的普通文本答案整理成更稳定的 Markdown 结构。

const SECTION_TITLES = new Set(['已检索知识点', '结论', '解题步骤', '可参考的知识摘要', '同类练习'])

function looksLikeMarkdown(text) {
  return /(^|\n)\s{0,3}(#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s|```)/.test(text)
}

function normalizeListItems(value) {
  return value
    .split(/[、,，]\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function normalizeAnswerMarkdown(answer) {
  // 如果内容本身已经是 Markdown，就直接透传；否则尝试补出标题和列表结构。
  const text = String(answer || '')
    .replace(/\r\n?/g, '\n')
    .trim()

  if (!text) {
    return ''
  }

  if (looksLikeMarkdown(text)) {
    return text
  }

  const blocks = []
  const paragraph = []
  const listItems = []
  let listType = ''

  const flushParagraph = () => {
    if (!paragraph.length) {
      return
    }

    blocks.push(paragraph.join('\n'))
    paragraph.length = 0
  }

  const flushList = () => {
    if (!listItems.length) {
      return
    }

    blocks.push(listItems.join('\n'))
    listItems.length = 0
    listType = ''
  }

  const pushSection = (title, body) => {
    blocks.push(`## ${title}`)

    if (!body) {
      return
    }

    if (title === '已检索知识点') {
      const items = normalizeListItems(body)
      if (items.length > 1) {
        blocks.push(items.map((item) => `- ${item}`).join('\n'))
        return
      }
    }

    blocks.push(body)
  }

  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim()

    if (!line) {
      flushParagraph()
      flushList()
      continue
    }

    const sectionMatch = line.match(/^([^：:]+)[：:]\s*(.*)$/)
    if (sectionMatch) {
      const title = sectionMatch[1].trim()
      const body = sectionMatch[2].trim()

      if (SECTION_TITLES.has(title)) {
        flushParagraph()
        flushList()
        pushSection(title, body)
        continue
      }
    }

    const orderedMatch = line.match(/^(\d+)[.)、]\s*(.+)$/)
    if (orderedMatch) {
      flushParagraph()
      if (listType && listType !== 'ordered') {
        flushList()
      }
      listType = 'ordered'
      listItems.push(`${orderedMatch[1]}. ${orderedMatch[2].trim()}`)
      continue
    }

    const unorderedMatch = line.match(/^[-*•]\s+(.+)$/)
    if (unorderedMatch) {
      flushParagraph()
      if (listType && listType !== 'unordered') {
        flushList()
      }
      listType = 'unordered'
      listItems.push(`- ${unorderedMatch[1].trim()}`)
      continue
    }

    flushList()
    paragraph.push(line)
  }

  flushParagraph()
  flushList()

  return blocks.join('\n\n')
}
