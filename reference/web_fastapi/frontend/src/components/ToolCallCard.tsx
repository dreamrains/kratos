import { useState } from 'react'
import './ToolCallCard.css'

interface ToolCallCardProps {
  name: string
  arguments: Record<string, unknown>
  result?: string
  durationMs?: number
}

export function ToolCallCard({ name, arguments: args, result, durationMs }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={`tool-call-card ${result ? 'completed' : 'running'}`}>
      <div className="tool-call-header" onClick={() => setExpanded(!expanded)}>
        <span className="tool-status">{result ? '✓' : '◎'}</span>
        <span className="tool-name">{name}</span>
        {durationMs != null && (
          <span className="tool-duration">{durationMs}ms</span>
        )}
        <span className="tool-expand">{expanded ? '▾' : '▸'}</span>
      </div>

      {expanded && (
        <div className="tool-call-body">
          <div className="tool-args">
            <strong>参数:</strong>
            <pre>{JSON.stringify(args, null, 2)}</pre>
          </div>
          {result && (
            <div className="tool-result">
              <strong>结果:</strong>
              <pre>{result}</pre>
            </div>
          )}
        </div>
      )}

      {!expanded && result && (
        <div className="tool-result-summary" onClick={() => setExpanded(true)}>
          {result.length > 120 ? result.slice(0, 120) + '...' : result}
        </div>
      )}
    </div>
  )
}
