function ThinkingCard() {
  return (
    <section className="thinking-card" aria-live="polite">
      <div className="thinking-visual" aria-hidden="true">
        <div className="thinking-orb" />
        <div className="thinking-ring thinking-ring-one" />
        <div className="thinking-ring thinking-ring-two" />
        <div className="thinking-ring thinking-ring-three" />
        <span className="thinking-petal thinking-petal-one" />
        <span className="thinking-petal thinking-petal-two" />
        <span className="thinking-petal thinking-petal-three" />
      </div>

      <div className="thinking-copy">
        <p className="thinking-title">我先把讲解答案理清楚</p>
        <p className="thinking-text">
          先给出适合课堂讲解的答案。等答案准备好之后，你可以再决定要不要生成视频脚本或 PPT 提纲。
        </p>
        <div className="thinking-dots" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
      </div>
    </section>
  )
}

export default ThinkingCard
