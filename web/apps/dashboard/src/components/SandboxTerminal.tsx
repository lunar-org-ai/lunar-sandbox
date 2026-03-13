import { useEffect, useRef, useState } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import { AttachAddon } from '@xterm/addon-attach'

import { Button } from '@/components/ui/button'

// ---------------------------------------------------------------------------
// SandboxTerminal
// ---------------------------------------------------------------------------
// Renders an xterm.js terminal connected to the backend PTY via WebSocket.
// When sandboxStatus is "Running" the terminal starts in read-only mode
// to show agent stdout/stderr without accepting keyboard input, with a
// button to switch to interactive mode.
//
// IMPORTANT: The parent must NOT unmount this component when the drawer
// collapses. Use CSS to hide it instead so the terminal session persists.
// ---------------------------------------------------------------------------

interface SandboxTerminalProps {
  sandboxId: string
  sandboxStatus?: string
}

export function SandboxTerminal({ sandboxId, sandboxStatus }: SandboxTerminalProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Read-only mode: start read-only when sandbox is currently running
  const initialReadOnly = sandboxStatus === 'Running'
  const [readOnly, setReadOnly] = useState(initialReadOnly)

  useEffect(() => {
    if (!containerRef.current) return

    // -----------------------------------------------------------------------
    // Create terminal
    // -----------------------------------------------------------------------
    const term = new Terminal({
      theme: {
        background: '#09090b',
        foreground: '#fafafa',
        cursor: '#fafafa',
        cursorAccent: '#09090b',
        selectionBackground: '#3f3f46',
      },
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'ui-monospace, "Cascadia Code", "Source Code Pro", Menlo, monospace',
      scrollback: 5000,
    })
    termRef.current = term

    const fitAddon = new FitAddon()
    fitAddonRef.current = fitAddon
    term.loadAddon(fitAddon)
    term.open(containerRef.current)

    // -----------------------------------------------------------------------
    // WebSocket + AttachAddon
    // -----------------------------------------------------------------------
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/api/sandboxes/${encodeURIComponent(sandboxId)}/terminal`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws
    ws.binaryType = 'arraybuffer'

    const attachAddon = new AttachAddon(ws)
    term.loadAddon(attachAddon)

    // Helper: send terminal dimensions to backend as JSON control frame
    function sendResize() {
      if (ws.readyState === WebSocket.OPEN) {
        const encoder = new TextEncoder()
        ws.send(
          encoder.encode(
            JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }),
          ),
        )
      }
    }

    // -----------------------------------------------------------------------
    // Read-only guard: suppress all keyboard input when read-only
    // -----------------------------------------------------------------------
    if (initialReadOnly) {
      term.attachCustomKeyEventHandler(() => false)
      term.writeln(
        '\x1b[33m[Read-only mode - agent is running. Click "Switch to Interactive" to take control.]\x1b[0m',
      )
    }

    // Defer initial fit to next tick so the DOM has settled
    const fitTimer = setTimeout(() => {
      fitAddon.fit()
      sendResize()
    }, 0)

    // -----------------------------------------------------------------------
    // ResizeObserver -- refit when container dimensions change
    // -----------------------------------------------------------------------
    const observer = new ResizeObserver(() => {
      fitAddon.fit()
      sendResize()
    })
    observer.observe(containerRef.current!)

    // -----------------------------------------------------------------------
    // Cleanup
    // -----------------------------------------------------------------------
    return () => {
      clearTimeout(fitTimer)
      observer.disconnect()
      ws.close(1000)
      term.dispose()
      termRef.current = null
      fitAddonRef.current = null
      wsRef.current = null
    }
    // Only re-run when sandboxId changes -- not on readOnly state change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sandboxId])

  // -----------------------------------------------------------------------
  // Switch to interactive mode
  // -----------------------------------------------------------------------
  function handleSwitchToInteractive() {
    setReadOnly(false)
    if (termRef.current) {
      // Allow all key events through
      termRef.current.attachCustomKeyEventHandler(() => true)
      termRef.current.focus()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {readOnly && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-950/40 border-b border-amber-500/20 text-amber-300 text-xs shrink-0">
          <span className="flex-1">Read-only: agent is running</span>
          <Button
            size="sm"
            variant="outline"
            className="h-6 text-xs border-amber-500/40 text-amber-300 hover:bg-amber-900/40"
            onClick={handleSwitchToInteractive}
          >
            Switch to Interactive
          </Button>
        </div>
      )}
      <div ref={containerRef} className="flex-1 min-h-0 overflow-hidden" />
    </div>
  )
}
