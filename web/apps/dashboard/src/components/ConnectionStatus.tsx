import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useEventStream } from "@/hooks/useEventStream";
import type { ReadyState } from "@/lib/ws";

const stateConfig: Record<
  ReadyState,
  { variant: "secondary" | "destructive"; label: string; tooltip: string }
> = {
  connected: {
    variant: "secondary",
    label: "Live",
    tooltip: "Connected",
  },
  connecting: {
    variant: "secondary",
    label: "Connecting",
    tooltip: "Connecting...",
  },
  reconnecting: {
    variant: "secondary",
    label: "Reconnecting",
    tooltip: "Reconnecting...",
  },
  disconnected: {
    variant: "destructive",
    label: "Offline",
    tooltip: "Disconnected",
  },
};

export function ConnectionStatus() {
  const { readyState } = useEventStream({ topic: null });
  const prevStateRef = useRef<ReadyState | null>(null);

  useEffect(() => {
    if (prevStateRef.current === null) {
      prevStateRef.current = readyState;
      return;
    }

    if (readyState === prevStateRef.current) return;
    prevStateRef.current = readyState;

    switch (readyState) {
      case "connected":
        toast.success("Connected to live updates");
        break;
      case "reconnecting":
        toast.warning("Connection lost, reconnecting...");
        break;
      case "disconnected":
        toast.error("Disconnected from live updates");
        break;
    }
  }, [readyState]);

  const { variant, label, tooltip } = stateConfig[readyState];
  const showBanner =
    readyState === "disconnected" || readyState === "reconnecting";

  return (
    <>
      <Badge
        variant={variant}
        title={tooltip}
        className="h-6 px-2 text-xs font-medium"
      >
        {label}
      </Badge>
      {showBanner && (
        <Alert className="fixed top-12 left-4 right-4 z-40 border-0">
          <AlertDescription>
            Live updates are temporarily unavailable. Reconnection is in
            progress.
          </AlertDescription>
        </Alert>
      )}
    </>
  );
}
