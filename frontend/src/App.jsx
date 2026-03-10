import { useRef, useState } from 'react'
import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

const sampleCases = [
  '8 + 7 为什么等于 15？请用图示思路讲解。',
  '长方形长 8 厘米、宽 5 厘米，面积怎么算？',
  '把 3/4 讲给三年级学生听，要有生活例子。',
  '小明有 24 颗糖，平均分给 6 人，每人多少颗？',
  '比较 0.5 和 1/2，为什么它们相等？',
  '两位数乘一位数怎么验算？给一题练习。',
]

function App() {
  const [question, setQuestion] = useState('')
  const [mode, setMode] = useState('极速')
  const [fileName, setFileName] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [latestResult, setLatestResult] = useState('')
  const fileInputRef = useRef(null)

  const openFilePicker = () => {
    fileInputRef.current?.click()
  }

  const onPickFile = (event) => {
    const targetFile = event.target.files?.[0]
    setFileName(targetFile ? targetFile.name : '')
  }

  const submitQuestion = async (nextQuestion) => {
    const finalQuestion = (nextQuestion ?? question).trim()
    if (!finalQuestion) {
      setError('请输入问题')
      return
    }

    setLoading(true)
    setError('')
    setLatestResult('')

    try {
      const response = await fetch(`${API_BASE_URL}/api/lesson-assets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          grade: 3,
          question: finalQuestion,
        }),
      })

      if (!response.ok) {
        throw new Error(`请求失败：HTTP ${response.status}`)
      }

      const data = await response.json()
      setLatestResult(data.answer || '已生成内容。')
    } catch (requestError) {
      setError(requestError.message || '请求失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  const onSubmit = async (event) => {
    event.preventDefault()
    await submitQuestion()
  }

  const onUseCase = async (caseQuestion) => {
    setQuestion(caseQuestion)
    await submitQuestion(caseQuestion)
  }

  return (
    <main className="layout">
      <aside className="sidebar" />

      <section className="workspace">
        <header className="welcome">
          <h1>下午好，数学AI教学平台</h1>
          <p>我有什么可以帮助你</p>
        </header>

        <form className="input-shell" onSubmit={onSubmit}>
          <input
            className="question-input"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="请输入"
            disabled={loading}
          />

          <div className="toolbar">
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value)}
              disabled={loading}
              aria-label="推理模式"
            >
              <option value="极速">极速</option>
              <option value="平衡">平衡</option>
              <option value="深入">深入</option>
            </select>

            <div className="toolbar-right">
              <button
                type="button"
                className="attach-btn"
                onClick={openFilePicker}
                disabled={loading}
              >
                📎 附件
              </button>
              <button
                type="submit"
                className="send-btn"
                aria-label="发送"
                disabled={loading}
                title="发送"
              >
                {loading ? '…' : ''}
              </button>
            </div>
          </div>
        </form>

        <input
          ref={fileInputRef}
          type="file"
          onChange={onPickFile}
          hidden
          aria-hidden="true"
        />

        {fileName ? <p className="file-hint">已选择附件：{fileName}</p> : null}
        {error ? <p className="error-hint">{error}</p> : null}
        {latestResult ? <section className="result-hint">{latestResult}</section> : null}

        <section className="cases">
          <h2>精选案例</h2>
          <div className="case-grid">
            {sampleCases.map((item) => (
              <button
                key={item}
                className="case-card"
                type="button"
                onClick={() => onUseCase(item)}
                disabled={loading}
                title={item}
              >
                {item}
              </button>
            ))}
          </div>
        </section>
      </section>
    </main>
  )
}

export default App
