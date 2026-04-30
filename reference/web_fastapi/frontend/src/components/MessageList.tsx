import type { Turn } from '../types'
import { AssistantMessage } from './AssistantMessage'
import { ToolCallCard } from './ToolCallCard'
import { ConfirmationCard } from './ConfirmationCard'
import { ThinkingIndicator } from './ThinkingIndicator'

interface MessageListProps {
  turns: Turn[]
  onResume: (turnId: string, suspensionId: string, response: string) => void
}

export function MessageList({ turns, onResume }: MessageListProps) {
  return (
    <div className="message-list">
      {turns.map(turn => (
        <div key={turn.turn_id} className="turn">
          <div className="user-message">
            <div className="message-avatar user">U</div>
            <div className="message-content">{turn.user_message}</div>
          </div>

          {turn.events.map((event, idx) => {
            if (event.type === 'tool_call') {
              const data = event.data as { tool_call_id: string; name: string; arguments: Record<string, unknown>; round: number }
              // Find matching tool_result
              const resultEvent = turn.events.find(
                e => e.type === 'tool_result' && (e.data as { tool_call_id: string }).tool_call_id === data.tool_call_id
              )
              const resultData = resultEvent?.data as { web: { summary: string }; duration_ms: number } | undefined
              return (
                <ToolCallCard
                  key={data.tool_call_id}
                  name={data.name}
                  arguments={data.arguments}
                  result={resultData?.web?.summary}
                  durationMs={resultData?.duration_ms}
                />
              )
            }

            if (event.type === 'llm_call_start') {
              // Only show thinking indicator if there's no text yet
              if (!turn.text) {
                return <ThinkingIndicator key={`think-${idx}`} />
              }
              return null
            }

            if (event.type === 'suspended' && turn.suspension) {
              return (
                <ConfirmationCard
                  key={`susp-${turn.suspension.suspension_id}`}
                  question={turn.suspension.question}
                  options={turn.suspension.options}
                  onSelect={(response) =>
                    onResume(turn.turn_id, turn.suspension!.suspension_id, response)
                  }
                />
              )
            }

            if (event.type === 'error') {
              const data = event.data as { message: string }
              return (
                <div key={`err-${idx}`} className="error-message">
                  Error: {data.message}
                </div>
              )
            }

            return null
          })}

          {turn.text && <AssistantMessage content={turn.text} />}

          {turn.status === 'active' && !turn.text && !turn.suspension && (
            <ThinkingIndicator />
          )}
        </div>
      ))}
    </div>
  )
}
