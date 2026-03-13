import { BrowserRouter, Route, Routes } from 'react-router'

import { AppSidebar } from '@/components/AppSidebar'
import { ConnectionStatus } from '@/components/ConnectionStatus'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import Home from '@/routes/Home'
import Launcher from '@/routes/Launcher'
import SandboxDetail from '@/routes/SandboxDetail'

function App() {
  return (
    <BrowserRouter>
      <SidebarProvider>
        <AppSidebar />
        <div className="flex-1 flex flex-col min-h-screen">
          <header className="sticky top-0 z-30 flex items-center justify-between bg-zinc-900 px-4 py-2 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              <SidebarTrigger />
              <span className="text-sm font-semibold tracking-tight">LunarEngine</span>
            </div>
            <ConnectionStatus />
          </header>
          <main className="flex-1 bg-neutral-950 text-neutral-50">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/launcher" element={<Launcher />} />
              <Route path="/runs" element={<PlaceholderPage title="Runs" />} />
              <Route path="/runs/:id" element={<PlaceholderPage title="Run Detail" />} />
              <Route path="/sandboxes/:id" element={<SandboxDetail />} />
            </Routes>
          </main>
        </div>
      </SidebarProvider>
    </BrowserRouter>
  )
}

// Temporary placeholder for routes not yet implemented
function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold">{title}</h1>
      <p className="text-neutral-400 mt-2">Coming soon...</p>
    </div>
  )
}

export default App
