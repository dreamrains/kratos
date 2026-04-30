import { useState, type ReactNode } from 'react'
import './Layout.css'

interface LayoutProps {
  sidebar: ReactNode
  main: ReactNode
}

export function Layout({ sidebar, main }: LayoutProps) {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="layout">
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
        <button className="sidebar-toggle" onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? '→' : '←'}
        </button>
        {!collapsed && sidebar}
      </aside>
      <main className="main-content">
        {main}
      </main>
    </div>
  )
}
