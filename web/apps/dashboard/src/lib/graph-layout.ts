// ---------------------------------------------------------------------------
// Graph layout utility using dagre for React Flow LR layout
// ---------------------------------------------------------------------------

import dagre from '@dagrejs/dagre'
import { MarkerType, Position } from '@xyflow/react'
import type { Edge, Node } from '@xyflow/react'

import type { TraceSpan } from '@/lib/trace-utils'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const NODE_WIDTH = 220
export const NODE_HEIGHT = 64

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ActionNodeData = {
  action: string
  status: TraceSpan['status']
  durationMs: number
  isActive: boolean
  stepIdx: number
}

// ---------------------------------------------------------------------------
// Internal layout function
// ---------------------------------------------------------------------------

/**
 * Applies dagre LR layout to nodes and edges.
 * Creates a new dagre.graphlib.Graph() each call to avoid stale state
 * (per pitfall 4: dagre graph instance must be recreated between layouts).
 */
function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction = 'LR',
): { nodes: Node[]; edges: Edge[] } {
  // Create a NEW graph instance each time to avoid stale accumulated state
  const dagreGraph = new dagre.graphlib.Graph()
  dagreGraph.setDefaultEdgeLabel(() => ({}))
  dagreGraph.setGraph({ rankdir: direction, nodesep: 40, ranksep: 80 })

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target)
  })

  dagre.layout(dagreGraph)

  const layoutedNodes: Node[] = nodes.map((node) => {
    const pos = dagreGraph.node(node.id)
    return {
      ...node,
      // LR layout: handles on left and right
      targetPosition: Position.Left,
      sourcePosition: Position.Right,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Converts a TraceSpan[] into dagre-layouted React Flow nodes and edges.
 *
 * Spans are connected sequentially: span[i] -> span[i+1] (linear chain).
 *
 * Performance note: Only run dagre layout when span COUNT changes.
 * For live status updates (running → completed), update node data
 * in-place via setNodes without calling this function again.
 * The caller should memoize by spans.length to avoid layout thrashing.
 *
 * @param spans - Array of trace spans to render as graph nodes
 * @param activeSpanId - Currently active span ID (or null)
 */
export function spansToGraphElements(
  spans: TraceSpan[],
  activeSpanId: string | null,
): { nodes: Node[]; edges: Edge[] } {
  if (spans.length === 0) {
    return { nodes: [], edges: [] }
  }

  const nodes: Node[] = spans.map((span) => ({
    id: span.id,
    type: 'action',
    position: { x: 0, y: 0 }, // dagre will override
    data: {
      action: span.action,
      status: span.status,
      durationMs: span.durationMs,
      isActive: span.id === activeSpanId,
      stepIdx: span.stepIdx,
    } satisfies ActionNodeData,
  }))

  // Sequential chain: spans[i] -> spans[i+1]
  const edges: Edge[] = spans.slice(0, spans.length - 1).map((span, i) => ({
    id: `e-${span.id}-${spans[i + 1].id}`,
    source: span.id,
    target: spans[i + 1].id,
    type: 'step',
    markerEnd: { type: MarkerType.ArrowClosed },
    animated: false,
  }))

  return getLayoutedElements(nodes, edges, 'LR')
}
