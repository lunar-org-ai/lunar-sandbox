import { BrowserRouter, Route, Routes } from 'react-router'

import { AppSidebar } from '@/components/AppSidebar'
import { ConnectionStatus } from '@/components/ConnectionStatus'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import Home from '@/routes/Home'
import Launcher from '@/routes/Launcher'
import Runs from '@/routes/Runs'
import RunDetail from '@/routes/RunDetail'
import SandboxDetail from '@/routes/SandboxDetail'
import BatchDetail from '@/routes/BatchDetail'

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
              <Route path="/runs" element={<Runs />} />
              <Route path="/runs/:id" element={<RunDetail />} />
              <Route path="/sandboxes/:id" element={<SandboxDetail />} />
              <Route path="/batches/:id" element={<BatchDetail />} />
            </Routes>
          </main>
        </div>
      </SidebarProvider>
    </BrowserRouter>
  )
}

export default App
