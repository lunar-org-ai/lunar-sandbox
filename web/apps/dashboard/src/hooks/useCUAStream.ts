import { useEffect, useRef, useState } from "react";

import { useEventStream } from "@/hooks/useEventStream";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CUAEvent {
  id: string;
  type: "start" | "step" | "end";
  timestamp: number;
  /** Model reasoning text (step events only) */
  reasoning: string | null;
  /** Action name (step events only) */
  action: string | null;
  /** Action parameters (step events only) */
  actionParams: Record<string, unknown>;
  /** Step index (step events only) */
  step: number | null;
  /** Task instruction (start events only) */
  instruction: string | null;
  /** Episode outcome (end events only) */
  outcome: string | null;
  /** Step count (end events only) */
  stepCount: number | null;
  /** Duration ms (end events only) */
  durationMs: number | null;
  /** Error message (end events only) */
  error: string | null;
  /** Screenshot URL for this step */
  screenshotUrl: string | null;
}

export interface UseCUAStreamReturn {
  events: CUAEvent[];
  isLive: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

const LIVE_THRESHOLD_MS = 5000;

export function useCUAStream(episodeId: string | null): UseCUAStreamReturn {
  const topic = episodeId ? `cua:${episodeId}` : null;
  const { events: rawEvents } = useEventStream({ topic });

  const cuaEventsRef = useRef<CUAEvent[]>([]);
  const lastEventTimeRef = useRef<number>(0);
  const [cuaEvents, setCuaEvents] = useState<CUAEvent[]>([]);
  const [isLive, setIsLive] = useState(false);

  // Reset on episode change
  useEffect(() => {
    cuaEventsRef.current = [];
    setCuaEvents([]);
    setIsLive(false);
  }, [episodeId]);

  // Process incoming events
  useEffect(() => {
    if (!episodeId || rawEvents.length === 0) return;

    const last = rawEvents[rawEvents.length - 1];
    if (!last) return;

    const payload = last.payload as Record<string, unknown>;
    let event: CUAEvent | null = null;

    if (last.type === "cua_episode_start") {
      event = {
        id: `start-${episodeId}`,
        type: "start",
        timestamp: last.timestamp,
        reasoning: null,
        action: null,
        actionParams: {},
        step: null,
        instruction: (payload["instruction"] as string) ?? null,
        outcome: null,
        stepCount: null,
        durationMs: null,
        error: null,
        screenshotUrl: null,
      };
    } else if (last.type === "cua_step") {
      const step = (payload["step"] as number) ?? 0;
      const screenshotFile = `step_${String(step).padStart(3, "0")}.jpg`;
      event = {
        id: `step-${step}`,
        type: "step",
        timestamp: last.timestamp,
        reasoning: (payload["reasoning"] as string) ?? null,
        action: (payload["action"] as string) ?? null,
        actionParams:
          (payload["action_params"] as Record<string, unknown>) ?? {},
        step,
        instruction: null,
        outcome: null,
        stepCount: null,
        durationMs: null,
        error: null,
        screenshotUrl: `/api/cua/episodes/${episodeId}/screenshots/${screenshotFile}`,
      };
    } else if (last.type === "cua_episode_end") {
      event = {
        id: `end-${episodeId}`,
        type: "end",
        timestamp: last.timestamp,
        reasoning: null,
        action: null,
        actionParams: {},
        step: null,
        instruction: null,
        outcome: (payload["outcome"] as string) ?? null,
        stepCount: (payload["step_count"] as number) ?? null,
        durationMs: (payload["duration_ms"] as number) ?? null,
        error: (payload["error"] as string) ?? null,
        screenshotUrl: null,
      };
    }

    if (event) {
      // Deduplicate by id
      const existing = cuaEventsRef.current.find((e) => e.id === event!.id);
      if (!existing) {
        cuaEventsRef.current = [...cuaEventsRef.current, event];
      } else {
        // Update in place (step events may update)
        cuaEventsRef.current = cuaEventsRef.current.map((e) =>
          e.id === event!.id ? event! : e,
        );
      }
      lastEventTimeRef.current = Date.now();
      setCuaEvents([...cuaEventsRef.current]);
      setIsLive(true);
    }
  }, [episodeId, rawEvents]);

  // Decay isLive
  useEffect(() => {
    if (!isLive) return;
    const timer = setTimeout(() => {
      if (Date.now() - lastEventTimeRef.current >= LIVE_THRESHOLD_MS) {
        setIsLive(false);
      }
    }, LIVE_THRESHOLD_MS);
    return () => clearTimeout(timer);
  }, [isLive, rawEvents]);

  return { events: cuaEvents, isLive };
}
