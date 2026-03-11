import { BrowserRouter, Routes, Route } from 'react-router'

import { ConnectionStatus } from '@/components/ConnectionStatus'
import Home from '@/routes/Home'

function App() {
  return (
    <BrowserRouter>
      {/* App shell */}
      <div className="min-h-screen bg-neutral-950 text-neutral-50">
        {/* Header */}
        <header className="sticky top-0 z-30 flex items-center justify-between bg-zinc-900 px-4 py-2 border-b border-zinc-800">
          <span className="text-sm font-semibold tracking-tight">
            LunarEngine
          </span>
          <ConnectionStatus />
        </header>

        {/* Main content */}
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
