import { useRef, useEffect } from 'react'
import type { Turn } from '../types'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'

interface ChatViewProps {
  turns: Turn[]
  isLoading: boolean
  onSend: (message: string) => void
  onResume: (turnId: string, suspensionId: string, response: string) => void
}

export function ChatView({ turns, isLoading, onSend, onResume }: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  return (
    <div className="chat-view">
      <div className="chat-messages">
        {turns.length === 0 && (
          <div className="empty-state">
            <h2>Data Agent</h2>
            <p>数据分析专家 — 输入问题开始分析</p>
          </div>
        )}
        <MessageList turns={turns} onResume={onResume} />
        <div ref={bottomRef} />
      </div>
      <ChatInput onSend={onSend} isLoading={isLoading} />
    </div>
  )
}
