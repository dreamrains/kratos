import { Layout } from './components/Layout'
import { Sidebar } from './components/Sidebar'
import { ChatView } from './components/ChatView'
import { useChat } from './hooks/useChat'
import './App.css'

function App() {
  const { turns, sessionId, isLoading, sendMessage, resumeConfirmation, clearTurns } = useChat()

  return (
    <Layout
      sidebar={
        <Sidebar
          sessionId={sessionId}
          onNewSession={clearTurns}
        />
      }
      main={
        <ChatView
          turns={turns}
          isLoading={isLoading}
          onSend={sendMessage}
          onResume={resumeConfirmation}
        />
      }
    />
  )
}

export default App
