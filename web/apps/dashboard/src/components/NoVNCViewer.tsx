import { useEffect, useRef, useState } from 'react'

// ---------------------------------------------------------------------------
// NoVNCViewer
// ---------------------------------------------------------------------------
// Renders a live remote desktop view by wrapping the noVNC RFB class.
// The RFB class is dynamically imported from /novnc/core/rfb.js which is
// served as a static asset bundle by FastAPI -- NOT bundled by Vite.
//
// Decision: view-only by default, scaleViewport fills available width,
// resizeSession disabled (remote resolution unchanged).
// ---------------------------------------------------------------------------

interface NoVNCViewerProps {
  wsUrl: string
  viewOnly?: boolean
  onConnect?: () => void
  onDisconnect?: (reason?: string) => void
  className?: string
}

type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

// RFB is loaded from an external JS module (no @types available) -- use any.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type RFBClass = any

export function NoVNCViewer({
  wsUrl,
  viewOnly = true,
  onConnect,
  onDisconnect,
  className,
}: NoVNCViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const rfbRef = useRef<any>(null)
  const rfbClassRef = useRef<RFBClass | null>(null)
  const [connState, setConnState] = useState<ConnectionState>('connecting')
  const [errorDetail, setErrorDetail] = useState<string>('')

  // -------------------------------------------------------------------------
  // Load RFB class once, then connect
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current || !wsUrl) return

    let cancelled = false

    async function connect() {
      // Dynamically import RFB from the locally-served static bundle.
      // @vite-ignore prevents Vite from trying to analyse/bundle this import.
      if (!rfbClassRef.current) {
        // Use a variable so Vite's static import analysis skips this entirely.
        // The file is served by FastAPI at runtime, not bundled by Vite.
        const rfbUrl = '/novnc/core/rfb.js'
        const mod = await import(/* @vite-ignore */ rfbUrl)
        rfbClassRef.current = mod.default
      }

      if (cancelled || !containerRef.current) return

      const RFB = rfbClassRef.current
      setConnState('connecting')

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const rfb: any = new RFB(containerRef.current, wsUrl)
      rfb.viewOnly = viewOnly
      rfb.scaleViewport = true
      rfb.resizeSession = false

      rfb.addEventListener('connect', () => {
        if (cancelled) return
        setConnState('connected')
        onConnect?.()
      })

      rfb.addEventListener('disconnect', (evt: CustomEvent) => {
        if (cancelled) return
        setConnState('disconnected')
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        onDisconnect?.(evt.detail?.reason as string | undefined)
      })

      rfb.addEventListener('securityfailure', (evt: CustomEvent) => {
        if (cancelled) return
        setConnState('error')
        // eslint-disable-next-line @typescript-eslint/no-unsafe-member-access
        setErrorDetail((evt.detail?.reason as string | undefined) ?? 'Security negotiation failed')
      })

      rfbRef.current = rfb
    }

    connect().catch((err: unknown) => {
      if (cancelled) return
      setConnState('error')
      setErrorDetail(err instanceof Error ? err.message : String(err))
    })

    return () => {
      cancelled = true
      if (rfbRef.current) {
        try {
          rfbRef.current.disconnect()
        } catch {
          // ignore errors during cleanup
        }
        rfbRef.current = null
      }
    }
    // Re-run only when wsUrl changes; viewOnly handled by separate effect below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsUrl])

  // -------------------------------------------------------------------------
  // Sync viewOnly prop changes to active RFB session
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (rfbRef.current) {
      rfbRef.current.viewOnly = viewOnly
    }
  }, [viewOnly])

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div
      className={`relative w-full h-full bg-black overflow-hidden ${className ?? ''}`}
    >
      {/* RFB mounts a canvas directly into this div */}
      <div ref={containerRef} className="w-full h-full" />

      {/* Connection state overlays */}
      {connState === 'connecting' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 text-white gap-3">
          <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          <span className="text-sm text-white/80">Connecting to desktop...</span>
        </div>
      )}

      {connState === 'disconnected' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-white gap-2">
          <div className="w-10 h-10 rounded-full border-2 border-white/30 flex items-center justify-center">
            <div className="w-5 h-0.5 bg-white/50 rotate-45 absolute" />
            <div className="w-5 h-0.5 bg-white/50 -rotate-45 absolute" />
          </div>
          <span className="text-sm text-white/70">Desktop disconnected</span>
        </div>
      )}

      {connState === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-white gap-2">
          <div className="w-10 h-10 rounded-full border-2 border-red-500/60 flex items-center justify-center">
            <span className="text-red-400 text-lg font-bold leading-none">!</span>
          </div>
          <span className="text-sm text-red-300">Connection failed</span>
          {errorDetail && (
            <span className="text-xs text-white/40 max-w-xs text-center">{errorDetail}</span>
          )}
        </div>
      )}
    </div>
  )
}

export default NoVNCViewer
