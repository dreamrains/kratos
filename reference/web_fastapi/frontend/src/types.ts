// SSE event types from backend
export interface TurnStartEvent {
  session_id: string
  turn_id: string
}

export interface LLMCallStartEvent {
  round: number
}

export interface ToolCallEvent {
  tool_call_id: string
  name: string
  arguments: Record<string, unknown>
  round: number
}

export interface ToolResultEvent {
  tool_call_id: string
  name: string
  web: {
    summary: string
    data?: Record<string, unknown> | null
    artifacts?: { path: string; type: string; description: string }[] | null
  }
  duration_ms: number
}

export interface TextDeltaEvent {
  text: string
  turn_id: string
}

export interface SuspendedEvent {
  suspension_id: string
  question: string
  options: { label: string; description?: string }[]
  context: string
}

export interface ErrorEvent {
  message: string
}

export interface TurnEndEvent {
  session_id: string
  turn_id: string
  status: 'completed' | 'suspended' | 'interrupted' | 'error'
}

export type SSEEvent =
  | { event: 'turn_start'; data: TurnStartEvent }
  | { event: 'llm_call_start'; data: LLMCallStartEvent }
  | { event: 'tool_call'; data: ToolCallEvent }
  | { event: 'tool_result'; data: ToolResultEvent }
  | { event: 'text_delta'; data: TextDeltaEvent }
  | { event: 'suspended'; data: SuspendedEvent }
  | { event: 'error'; data: ErrorEvent }
  | { event: 'turn_end'; data: TurnEndEvent }

// Chat state
export interface TurnEvent {
  type: string
  data: unknown
}

export interface Turn {
  turn_id: string
  user_message: string
  events: TurnEvent[]
  status: 'active' | 'completed' | 'suspended' | 'error'
  text: string
  suspension?: SuspendedEvent
}

export interface Session {
  session_id: string
  saved_at: string
  tag: string
  data_file: string
  message_count: number
  summary: string
}
