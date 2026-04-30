import { useCallback, useState } from 'react'
import type { Turn, SSEEvent, SuspendedEvent } from '../types'
import { streamChat, resumeChat } from '../api/client'

export function useChat() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [activeTurnId, setActiveTurnId] = useState<string | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const sendMessage = useCallback(async (message: string) => {
    const turnId = `t_${Date.now()}`
    const newTurn: Turn = {
      turn_id: turnId,
      user_message: message,
      events: [],
      status: 'active',
      text: '',
    }

    setTurns(prev => [...prev, newTurn])
    setActiveTurnId(turnId)
    setIsLoading(true)

    try {
      for await (const sseEvent of streamChat(message, sessionId || undefined)) {
        handleEvent(sseEvent, turnId)
      }
    } catch (err) {
      setTurns(prev =>
        prev.map(t =>
          t.turn_id === turnId ? { ...t, status: 'error' } : t
        )
      )
    } finally {
      setIsLoading(false)
    }
  }, [sessionId])

  const resumeConfirmation = useCallback(async (
    _turnId: string,
    suspensionId: string,
    userResponse: string,
  ) => {
    if (!sessionId) return

    setIsLoading(true)
    const resumeTurnId = `t_${Date.now()}`
    const resumeTurn: Turn = {
      turn_id: resumeTurnId,
      user_message: userResponse,
      events: [],
      status: 'active',
      text: '',
    }

    setTurns(prev => [...prev, resumeTurn])
    setActiveTurnId(resumeTurnId)

    try {
      for await (const sseEvent of resumeChat(sessionId, suspensionId, userResponse)) {
        handleEvent(sseEvent, resumeTurnId)
      }
    } catch (err) {
      setTurns(prev =>
        prev.map(t =>
          t.turn_id === resumeTurnId ? { ...t, status: 'error' } : t
        )
      )
    } finally {
      setIsLoading(false)
    }
  }, [sessionId])

  const handleEvent = useCallback((sseEvent: SSEEvent, turnId: string) => {
    setTurns(prev =>
      prev.map(t => {
        if (t.turn_id !== turnId) return t

        const updated = { ...t, events: [...t.events, { type: sseEvent.event, data: sseEvent.data }] }

        if (sseEvent.event === 'turn_start') {
          const data = sseEvent.data as { session_id: string }
          setSessionId(data.session_id)
        }
        if (sseEvent.event === 'text_delta') {
          const data = sseEvent.data as { text: string }
          updated.text = t.text + data.text
        }
        if (sseEvent.event === 'suspended') {
          updated.status = 'suspended'
          updated.suspension = sseEvent.data as SuspendedEvent
        }
        if (sseEvent.event === 'turn_end') {
          const data = sseEvent.data as { status: string }
          updated.status = data.status as Turn['status']
        }
        if (sseEvent.event === 'error') {
          updated.status = 'error'
        }

        return updated
      })
    )
  }, [])

  const clearTurns = useCallback(() => {
    setTurns([])
    setSessionId(null)
    setActiveTurnId(null)
  }, [])

  return {
    turns,
    activeTurnId,
    sessionId,
    isLoading,
    sendMessage,
    resumeConfirmation,
    clearTurns,
  }
}
