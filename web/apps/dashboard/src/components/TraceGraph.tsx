// ---------------------------------------------------------------------------
// TraceGraph — React Flow graph visualization for pipeline execution DAG
// ---------------------------------------------------------------------------

import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from '@xyflow/react'
import type { Edge, Node } from '@xyflow/react'

import { spansToGraphElements } from '@/lib/graph-layout'
import type { TraceSpan } from '@/lib/trace-utils'
import { getActionColor } from '@/lib/trace-utils'
import { nodeTypes } from '@/components/TraceGraphNode'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TraceGraphProps {
  spans: TraceSpan[]
  isLive: boolean
  onSpanSelect?: (span: TraceSpan | null) => void
  selectedSpanId?: string | null
}

// ---------------------------------------------------------------------------
// TraceGraphInner — must live inside ReactFlowProvider for useReactFlow
// ---------------------------------------------------------------------------

function TraceGraphInner({ spans, isLive, onSpanSelect, selectedSpanId }: TraceGraphProps) {
  const { fitView } = useReactFlow()
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[])
  const [edges, setEdges, onEdgesChange] = useEdgesState([] as Edge[])

  // Track the active span ID (last running span during live mode)
  const activeSpanId = useMemo(() => {
    if (!isLive || spans.length === 0) return null
    const lastSpan = spans[spans.length - 1]
    if (!lastSpan) return null
    return lastSpan.status === 'running' || lastSpan.status === 'completed'
      ? lastSpan.id
      : null
  }, [isLive, spans])

  // Track whether user has manually panned (to disable auto-pan)
  const userHasPannedRef = useRef(false)

  // Reset pan tracking when live mode ends
  useEffect(() => {
    if (!isLive) {
      userHasPannedRef.current = false
    }
  }, [isLive])

  // --- Layout: run dagre only when span COUNT changes ---
  // This avoids expensive layout thrashing during live streaming.
  const spanCount = spans.length
  useEffect(() => {
    if (spanCount === 0) {
      setNodes([])
      setEdges([])
      return
    }
    const { nodes: layoutedNodes, edges: layoutedEdges } = spansToGraphElements(spans, activeSpanId)
    setNodes(layoutedNodes)
    setEdges(layoutedEdges)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spanCount]) // intentionally only re-layout when count changes

  // --- Data update: update node data without re-running dagre ---
  // Fires on every spans change (status updates, isActive changes)
  // but preserves positions from the layout above.
  useEffect(() => {
    if (spans.length === 0) return
    setNodes((currentNodes) =>
      currentNodes.map((node) => {
        const span = spans.find((s) => s.id === node.id)
        if (!span) return node
        return {
          ...node,
          data: {
            ...node.data,
            status: span.status,
            durationMs: span.durationMs,
            isActive: isLive && span.id === activeSpanId,
            isSelected: span.id === selectedSpanId,
          },
        }
      }),
    )
  }, [spans, isLive, activeSpanId, selectedSpanId, setNodes])

  // --- Auto-pan to active node during live mode ---
  useEffect(() => {
    if (!isLive || !activeSpanId || userHasPannedRef.current) return
    fitView({
      nodes: [{ id: activeSpanId }],
      duration: 300,
      padding: 0.3,
    })
  }, [activeSpanId, isLive, fitView])

  // --- Node click handler ---
  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: { id: string }) => {
      if (!onSpanSelect) return
      const span = spans.find((s) => s.id === node.id)
      if (span) {
        onSpanSelect(selectedSpanId === span.id ? null : span)
      }
    },
    [onSpanSelect, spans, selectedSpanId],
  )

  // --- Manual pan tracking (disables auto-pan) ---
  const handleMoveEnd = useCallback(() => {
    userHasPannedRef.current = true
  }, [])

  // --- MiniMap node color based on action type ---
  const miniMapNodeColor = useCallback(
    (node: { data: Record<string, unknown> }) => {
      const action = typeof node.data['action'] === 'string' ? node.data['action'] : 'unknown'
      const color = getActionColor(action)
      // Extract the color name from bg-{color}-500 class to render in minimap
      // Map bg class to hex color for minimap
      return getBgColor(color.bg)
    },
    [],
  )

  // --- Empty state ---
  if (spans.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        No trace events
      </div>
    )
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={handleNodeClick}
      onMoveEnd={handleMoveEnd}
      fitView
      panOnScroll={true}
      minZoom={0.1}
      maxZoom={2}
      colorMode="dark"
    >
      <MiniMap
        nodeBorderRadius={4}
        nodeColor={miniMapNodeColor}
      />
      <Controls />
      <Background
        variant={BackgroundVariant.Dots}
        gap={16}
        size={1}
        color="rgb(63 63 70)"
      />
    </ReactFlow>
  )
}

// ---------------------------------------------------------------------------
// Color mapping — converts Tailwind bg class to hex for MiniMap rendering
// ---------------------------------------------------------------------------

const BG_COLOR_MAP: Record<string, string> = {
  'bg-blue-500': '#3b82f6',
  'bg-emerald-500': '#10b981',
  'bg-violet-500': '#8b5cf6',
  'bg-green-500': '#22c55e',
  'bg-cyan-500': '#06b6d4',
  'bg-amber-500': '#f59e0b',
  'bg-orange-500': '#f97316',
  'bg-slate-500': '#64748b',
  'bg-zinc-500': '#71717a',
}

function getBgColor(bgClass: string): string {
  return BG_COLOR_MAP[bgClass] ?? '#71717a'
}

// ---------------------------------------------------------------------------
// TraceGraph — exported component with ReactFlowProvider wrapper
// ---------------------------------------------------------------------------

/**
 * TraceGraph renders pipeline execution as a structural DAG.
 *
 * Features:
 * - Dagre LR auto-layout for span nodes
 * - Custom action node cards with icon, label, status, and duration
 * - Step (orthogonal) edges with arrowheads
 * - Minimap in bottom-right corner
 * - Auto-pan to active node during live mode (overridable by manual pan)
 * - Node click for span selection
 * - Zoom, pan, and viewport culling for 100+ nodes
 *
 * ReactFlowProvider is required for useReactFlow() in the inner component.
 */
export function TraceGraph(props: TraceGraphProps) {
  return (
    <ReactFlowProvider>
      <TraceGraphInner {...props} />
    </ReactFlowProvider>
  )
}
