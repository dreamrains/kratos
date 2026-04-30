import { useState } from 'react'
import './ConfirmationCard.css'

interface ConfirmationCardProps {
  question: string
  options: { label: string; description?: string }[]
  onSelect: (response: string) => void
}

export function ConfirmationCard({ question, options, onSelect }: ConfirmationCardProps) {
  const [customInput, setCustomInput] = useState('')
  const [answered, setAnswered] = useState(false)

  const handleSelect = (label: string) => {
    setAnswered(true)
    onSelect(label)
  }

  const handleCustom = () => {
    if (!customInput.trim()) return
    setAnswered(true)
    onSelect(customInput.trim())
  }

  if (answered) {
    return (
      <div className="confirmation-card answered">
        <div className="confirmation-question">{question}</div>
        <div className="confirmation-answered">已回复</div>
      </div>
    )
  }

  return (
    <div className="confirmation-card">
      <div className="confirmation-question">{question}</div>
      <div className="confirmation-options">
        {options.map((opt, i) => (
          <button key={i} className="confirmation-option" onClick={() => handleSelect(opt.label)}>
            <span className="option-label">{opt.label}</span>
            {opt.description && <span className="option-desc">{opt.description}</span>}
          </button>
        ))}
      </div>
      <div className="confirmation-custom">
        <input
          type="text"
          value={customInput}
          onChange={e => setCustomInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleCustom() }}
          placeholder="或输入自定义回复..."
        />
        <button onClick={handleCustom} disabled={!customInput.trim()}>发送</button>
      </div>
    </div>
  )
}
