import { useState } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { useHotkeys } from "react-hotkeys-hook";

import { AppSidebar } from "@/components/AppSidebar";
import { CommandPalette } from "@/components/CommandPalette";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { KeyboardShortcutsOverlay } from "@/components/KeyboardShortcutsOverlay";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import Home from "./routes/Home";
import Launcher from "@/routes/Launcher";
import Runs from "@/routes/Runs";
import RunDetail from "@/routes/RunDetail";
import SandboxDetail from "@/routes/SandboxDetail";
import BatchDetail from "@/routes/BatchDetail";
import EpisodeReplay from "@/routes/EpisodeReplay";
import Export from "@/routes/Export";
import PoolHealth from "@/routes/PoolHealth";
import CUALiveView from "@/routes/CUALiveView";

function AppShell() {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  useHotkeys(
    "mod+k",
    (e) => {
      e.preventDefault();
      setPaletteOpen((prev) => !prev);
    },
    {
      enableOnFormTags: false,
      ignoreEventWhen: (e) => {
        const target = e.target as HTMLElement;
        return (
          target.classList.contains("xterm-helper-textarea") ||
          !!target.closest(".xterm")
        );
      },
    },
  );

  useHotkeys(
    "shift+/",
    (e) => {
      e.preventDefault();
      setHelpOpen((prev) => !prev);
    },
    {
      enableOnFormTags: false,
      ignoreEventWhen: (e) => {
        const target = e.target as HTMLElement;
        return (
          target.classList.contains("xterm-helper-textarea") ||
          !!target.closest(".xterm")
        );
      },
    },
  );

  return (
    <TooltipProvider>
      <SidebarProvider>
        <AppSidebar />
        <div className="flex-1 flex flex-col min-h-screen">
          <header className="sticky top-0 z-30 flex h-12 items-center gap-3 bg-background px-4">
            <SidebarTrigger />
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
              <Route path="/cua/live/:id" element={<CUALiveView />} />
            </Routes>
          </main>
        </div>

        <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
        <KeyboardShortcutsOverlay open={helpOpen} onOpenChange={setHelpOpen} />
        <Toaster />
      </SidebarProvider>
    </TooltipProvider>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}

export default App;
