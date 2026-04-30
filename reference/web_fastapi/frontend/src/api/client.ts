import type { SSEEvent } from '../types'

const API_BASE = '/api'

export async function* streamChat(
  message: string,
  sessionId?: string,
  modelId?: string,
): AsyncGenerator<SSEEvent> {
  const body: Record<string, string> = { message }
  if (sessionId) body.session_id = sessionId
  if (modelId) body.model_id = modelId

  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = ''
    let currentData = ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        currentData = line.slice(6)
      } else if (line === '' && currentEvent && currentData) {
        try {
          yield { event: currentEvent, data: JSON.parse(currentData) } as SSEEvent
        } catch {
          // skip malformed data
        }
        currentEvent = ''
        currentData = ''
      }
    }
  }
}

export async function* resumeChat(
  sessionId: string,
  suspensionId: string,
  userResponse: string,
): AsyncGenerator<SSEEvent> {
  const response = await fetch(`${API_BASE}/chat/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      suspension_id: suspensionId,
      user_response: userResponse,
    }),
  })

  if (!response.ok) {
    throw new Error(`Resume request failed: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    let currentEvent = ''
    let currentData = ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim()
      } else if (line.startsWith('data: ')) {
        currentData = line.slice(6)
      } else if (line === '' && currentEvent && currentData) {
        try {
          yield { event: currentEvent, data: JSON.parse(currentData) } as SSEEvent
        } catch {
          // skip
        }
        currentEvent = ''
        currentData = ''
      }
    }
  }
}
