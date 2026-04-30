import './ThinkingIndicator.css'

export function ThinkingIndicator() {
  return (
    <div className="thinking-indicator">
      <div className="thinking-dots">
        <span></span><span></span><span></span>
      </div>
      <span className="thinking-text">分析中...</span>
    </div>
  )
}
