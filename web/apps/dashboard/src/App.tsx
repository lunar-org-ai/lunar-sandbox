import { useState } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router'
import { useHotkeys } from 'react-hotkeys-hook'

import { AppSidebar } from '@/components/AppSidebar'
import { CommandPalette } from '@/components/CommandPalette'
import { ConnectionStatus } from '@/components/ConnectionStatus'
import { KeyboardShortcutsOverlay } from '@/components/KeyboardShortcutsOverlay'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import Home from '@/routes/Home'
import Launcher from '@/routes/Launcher'
import Runs from '@/routes/Runs'
import RunDetail from '@/routes/RunDetail'
import SandboxDetail from '@/routes/SandboxDetail'
import BatchDetail from '@/routes/BatchDetail'
import EpisodeReplay from '@/routes/EpisodeReplay'
import Export from '@/routes/Export'
import PoolHealth from '@/routes/PoolHealth'

// ---------------------------------------------------------------------------
// AppShell — needs to be inside BrowserRouter so CommandPalette can useNavigate
// ---------------------------------------------------------------------------

function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  // Cmd+K opens the command palette
  // Ignore if focus is inside an xterm terminal element
  useHotkeys(
    'mod+k',
    (e) => {
      e.preventDefault()
      setPaletteOpen((prev) => !prev)
    },
    {
      enableOnFormTags: false,
      ignoreEventWhen: (e) => {
        // Don't fire inside xterm/terminal elements
        const target = e.target as HTMLElement
        return (
          target.classList.contains('xterm-helper-textarea') ||
          !!target.closest('.xterm')
        )
      },
    },
  )

  // ? opens the keyboard shortcuts overlay
  useHotkeys(
    'shift+/',
    (e) => {
      e.preventDefault()
      setHelpOpen((prev) => !prev)
    },
    {
      enableOnFormTags: false,
      ignoreEventWhen: (e) => {
        const target = e.target as HTMLElement
        return (
          target.classList.contains('xterm-helper-textarea') ||
          !!target.closest('.xterm')
        )
      },
    },
  )

  return (
    <SidebarProvider>
      <AppSidebar />
      <div className="flex-1 flex flex-col min-h-screen">
        <header className="sticky top-0 z-30 flex h-12 items-center gap-3 border-b border-border/50 bg-background/80 backdrop-blur-xl px-4">
          <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
          <div className="ml-auto">
            <ConnectionStatus />
          </div>
        </header>
        <main className="flex-1 bg-background text-foreground">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/launcher" element={<Launcher />} />
            <Route path="/runs" element={<Runs />} />
            <Route path="/runs/:id" element={<RunDetail />} />
            <Route path="/sandboxes/:id" element={<SandboxDetail />} />
            <Route path="/batches/:id" element={<BatchDetail />} />
            <Route path="/replay/:id" element={<EpisodeReplay />} />
            <Route path="/export" element={<Export />} />
            <Route path="/pool" element={<PoolHealth />} />
          </Routes>
        </main>
      </div>

      {/* Global overlays */}
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <KeyboardShortcutsOverlay open={helpOpen} onOpenChange={setHelpOpen} />
    </SidebarProvider>
  )
}

// ---------------------------------------------------------------------------
// App — BrowserRouter wraps AppShell so hooks can use navigate/searchParams
// ---------------------------------------------------------------------------

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  )
}

export default App
