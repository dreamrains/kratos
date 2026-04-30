import { useState, type KeyboardEvent } from 'react'
import './ChatInput.css'

interface ChatInputProps {
  onSend: (message: string) => void
  isLoading: boolean
}

export function ChatInput({ onSend, isLoading }: ChatInputProps) {
  const [input, setInput] = useState('')

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || isLoading) return
    onSend(trimmed)
    setInput('')
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-input">
      <textarea
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={isLoading ? '分析中...' : '输入分析问题...'}
        disabled={isLoading}
        rows={1}
      />
      <button onClick={handleSend} disabled={isLoading || !input.trim()}>
        {isLoading ? '...' : '→'}
      </button>
    </div>
  )
}
