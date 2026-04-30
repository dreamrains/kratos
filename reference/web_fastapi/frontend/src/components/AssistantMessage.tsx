import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import './AssistantMessage.css'

interface AssistantMessageProps {
  content: string
}

export function AssistantMessage({ content }: AssistantMessageProps) {
  return (
    <div className="assistant-message">
      <div className="message-avatar agent">A</div>
      <div className="message-content markdown-body">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content}
        </ReactMarkdown>
      </div>
    </div>
  )
}
