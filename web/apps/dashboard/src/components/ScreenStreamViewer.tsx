import { useEffect, useRef, useState, useCallback } from "react";

// ---------------------------------------------------------------------------
// ScreenStreamViewer
// ---------------------------------------------------------------------------
// Renders a live remote desktop view for Windows VMs by receiving JPEG
// screenshots streamed over a WebSocket from the backend. Each message is
// a JSON frame: { type: "frame", data: "<base64 jpeg>" }.
//
// Mirrors the NoVNCViewer API so CUALiveView can swap them based on platform.
// ---------------------------------------------------------------------------

interface ScreenStreamViewerProps {
  wsUrl: string;
  onConnect?: () => void;
  onDisconnect?: (reason?: string) => void;
  className?: string;
}

type ConnectionState = "connecting" | "connected" | "disconnected" | "error";

export function ScreenStreamViewer({
  wsUrl,
  onConnect,
  onDisconnect,
  className,
}: ScreenStreamViewerProps) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connState, setConnState] = useState<ConnectionState>("connecting");
  const [errorDetail, setErrorDetail] = useState("");
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cleanup = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!wsUrl) return;

    let cancelled = false;

    function connect() {
      if (cancelled) return;

      setConnState("connecting");
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (cancelled) return;
        setConnState("connected");
        onConnect?.();
      };

      ws.onmessage = (evt) => {
        if (cancelled) return;
        try {
          const msg = JSON.parse(evt.data as string) as {
            type: string;
            data?: string;
            message?: string;
          };

          if (msg.type === "frame" && msg.data) {
            setFrameSrc(`data:image/jpeg;base64,${msg.data}`);
          } else if (msg.type === "ended") {
            setConnState("disconnected");
            onDisconnect?.("episode ended");
          } else if (msg.type === "error") {
            setErrorDetail(msg.message ?? "Screenshot capture error");
          }
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (cancelled) return;
        setConnState("disconnected");
        onDisconnect?.("connection closed");
      };

      ws.onerror = () => {
        if (cancelled) return;
        setConnState("error");
        setErrorDetail("WebSocket connection failed");
        // Auto-reconnect after 3s
        reconnectTimer.current = setTimeout(() => {
          if (!cancelled) connect();
        }, 3000);
      };
    }

    connect();

    return () => {
      cancelled = true;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wsUrl]);

  return (
    <div
      className={`relative w-full h-full bg-black overflow-hidden ${className ?? ""}`}
    >
      {/* Live screenshot frame */}
      {frameSrc && (
        <img
          src={frameSrc}
          alt="Windows Desktop"
          className="w-full h-full object-contain"
          draggable={false}
        />
      )}

      {/* Connection state overlays */}
      {connState === "connecting" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 text-white gap-3">
          <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          <span className="text-sm text-white/80">
            Connecting to Windows desktop...
          </span>
        </div>
      )}

      {connState === "disconnected" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-white gap-2">
          <div className="w-10 h-10 rounded-full border-2 border-white/30 flex items-center justify-center">
            <div className="w-5 h-0.5 bg-white/50 rotate-45 absolute" />
            <div className="w-5 h-0.5 bg-white/50 -rotate-45 absolute" />
          </div>
          <span className="text-sm text-white/70">Desktop disconnected</span>
        </div>
      )}

      {connState === "error" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-white gap-2">
          <div className="w-10 h-10 rounded-full border-2 border-red-500/60 flex items-center justify-center">
            <span className="text-red-400 text-lg font-bold leading-none">
              !
            </span>
          </div>
          <span className="text-sm text-red-300">Connection failed</span>
          {errorDetail && (
            <span className="text-xs text-white/40 max-w-xs text-center">
              {errorDetail}
            </span>
          )}
          <span className="text-xs text-white/30">Retrying...</span>
        </div>
      )}
    </div>
  );
}

export default ScreenStreamViewer;
