import { useState, useEffect } from 'react'
import type { Session } from '../types'
import { fetchSessions } from '../api/sessions'
import './Sidebar.css'

interface SidebarProps {
  sessionId: string | null
  onNewSession: () => void
}

export function Sidebar({ sessionId, onNewSession }: SidebarProps) {
  const [sessions, setSessions] = useState<Session[]>([])

  useEffect(() => {
    fetchSessions().then(setSessions).catch(() => {})
  }, [sessionId])

  return (
    <div className="sidebar-content">
      <h3 className="sidebar-title">Data Agent</h3>

      <button className="new-session-btn" onClick={onNewSession}>
        + 新会话
      </button>

      <div className="sessions-list">
        <h4>会话历史</h4>
        {sessions.length === 0 && (
          <p className="no-sessions">暂无会话</p>
        )}
        {sessions.map(s => (
          <div
            key={s.session_id}
            className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
          >
            <div className="session-name">
              {s.tag || s.session_id}
            </div>
            <div className="session-meta">
              {s.message_count} 条消息 · {s.saved_at?.split('T')[0]}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
