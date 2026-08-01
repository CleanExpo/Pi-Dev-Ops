'use client'

// src/components/command-centre/wiki-graph/WikiGraphCanvas.tsx
//
// Obsidian-style interactive force-directed graph of the wiki knowledge base
// (UNI-2304). Canvas renderer (chosen over SVG for the ~460-node / thousands-
// of-edge real wiki). d3-force drives the layout and stays warm so the graph
// gently drifts; d3-zoom owns pan/zoom; node drag + hover + click are handled
// on the same canvas with a single owner per event type (zoom's filter yields
// pointer-downs that land on a node to the manual drag handler).

import { useEffect, useRef, useState, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCenter,
  forceCollide,
  type Simulation,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from 'd3-force'
import { select } from 'd3-selection'
import { zoom as d3zoom, zoomIdentity, type ZoomTransform, type D3ZoomEvent } from 'd3-zoom'

export interface WikiGraphNode {
  id: string
  title: string
  slug: string
  tags: string[]
  degree: number
}
export interface WikiGraphEdge {
  source: string
  target: string
}

type SimNode = WikiGraphNode & SimulationNodeDatum
type SimLink = SimulationLinkDatum<SimNode>

// Candy-deck palette (matches command-deck.module.css tokens).
const COL = {
  node: '#2dbb57',
  nodeDim: 'rgba(45,187,87,0.18)',
  link: 'rgba(90,107,98,0.28)',
  linkDim: 'rgba(90,107,98,0.06)',
  linkHi: '#f4820f',
  focus: '#15803d',
  label: '#14241b',
  labelDim: 'rgba(20,36,27,0.28)',
}

/** Keep the simulation perpetually warm for gentle, living motion. */
const KEEP_ALIVE = 0.012
/** Screen-pixels of slop added to a node's hit radius. */
const HIT_PADDING = 6

function nodeRadius(degree: number): number {
  return 3 + Math.sqrt(degree) * 1.6
}

interface Props {
  nodes: WikiGraphNode[]
  edges: WikiGraphEdge[]
}

interface Tooltip {
  x: number
  y: number
  title: string
  tags: string[]
  degree: number
}

export function WikiGraphCanvas({ nodes, edges }: Props) {
  const router = useRouter()
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [tooltip, setTooltip] = useState<Tooltip | null>(null)

  // Mutable refs shared across the render loop and event handlers.
  const simNodesRef = useRef<SimNode[]>([])
  const simLinksRef = useRef<SimLink[]>([])
  const adjacencyRef = useRef<Map<string, Set<string>>>(new Map())
  const transformRef = useRef<ZoomTransform>(zoomIdentity)
  const hoverRef = useRef<SimNode | null>(null)
  const draggingRef = useRef<SimNode | null>(null)
  const sizeRef = useRef({ w: 0, h: 0 })
  const simRef = useRef<Simulation<SimNode, SimLink> | null>(null)

  /** World-space node under a screen pointer (canvas-relative px), or null. */
  const nodeAtScreen = useCallback((px: number, py: number): SimNode | null => {
    const t = transformRef.current
    const wx = t.invertX(px)
    const wy = t.invertY(py)
    let best: SimNode | null = null
    let bestD = Infinity
    for (const n of simNodesRef.current) {
      if (n.x === undefined || n.y === undefined) continue
      const r = nodeRadius(n.degree) + HIT_PADDING / t.k
      const dx = n.x - wx
      const dy = n.y - wy
      const d = dx * dx + dy * dy
      if (d < r * r && d < bestD) {
        bestD = d
        best = n
      }
    }
    return best
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    const wrap = wrapRef.current
    if (!canvas || !wrap) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // Build simulation datasets (clone so d3 can mutate freely).
    const simNodes: SimNode[] = nodes.map((n) => ({ ...n }))
    const byId = new Map(simNodes.map((n) => [n.id, n]))
    const simLinks: SimLink[] = edges
      .filter((e) => byId.has(e.source) && byId.has(e.target))
      .map((e) => ({ source: e.source, target: e.target }))
    simNodesRef.current = simNodes
    simLinksRef.current = simLinks

    // Adjacency for hover-neighbour highlighting.
    const adjacency = new Map<string, Set<string>>()
    for (const n of simNodes) adjacency.set(n.id, new Set())
    for (const e of edges) {
      adjacency.get(e.source)?.add(e.target)
      adjacency.get(e.target)?.add(e.source)
    }
    adjacencyRef.current = adjacency

    // Size + HiDPI backing store.
    function resize() {
      const rect = wrap!.getBoundingClientRect()
      const dpr = Math.min(window.devicePixelRatio || 1, 2)
      sizeRef.current = { w: rect.width, h: rect.height }
      canvas!.width = Math.floor(rect.width * dpr)
      canvas!.height = Math.floor(rect.height * dpr)
      canvas!.style.width = `${rect.width}px`
      canvas!.style.height = `${rect.height}px`
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0)
      // World-space centroid stays at the origin — the initial zoom transform
      // below already translates that origin to the screen centre. Centring
      // the force here too would double-translate and start the cluster
      // off-centre.
      sim.force('center', forceCenter(0, 0))
    }

    const sim = forceSimulation(simNodes)
      .force('charge', forceManyBody().strength(-42).distanceMax(320))
      .force('link', forceLink<SimNode, SimLink>(simLinks).id((d) => d.id).distance(46).strength(0.35))
      .force('collide', forceCollide<SimNode>().radius((d) => nodeRadius(d.degree) + 2))
      .force('center', forceCenter(0, 0))
      .alphaTarget(KEEP_ALIVE)
    simRef.current = sim
    resize()

    function draw() {
      const { w, h } = sizeRef.current
      const t = transformRef.current
      ctx!.save()
      ctx!.clearRect(0, 0, w, h)
      ctx!.translate(t.x, t.y)
      ctx!.scale(t.k, t.k)

      const hover = hoverRef.current
      const neighbours = hover ? adjacencyRef.current.get(hover.id) : null

      // Links.
      ctx!.lineWidth = 1 / t.k
      for (const l of simLinksRef.current) {
        const s = l.source as SimNode
        const tg = l.target as SimNode
        if (s.x === undefined || tg.x === undefined) continue
        const touchesHover = hover && (s.id === hover.id || tg.id === hover.id)
        ctx!.strokeStyle = hover ? (touchesHover ? COL.linkHi : COL.linkDim) : COL.link
        ctx!.beginPath()
        ctx!.moveTo(s.x, s.y!)
        ctx!.lineTo(tg.x, tg.y!)
        ctx!.stroke()
      }

      // Nodes.
      for (const n of simNodesRef.current) {
        if (n.x === undefined || n.y === undefined) continue
        const isHover = hover?.id === n.id
        const isNeighbour = neighbours?.has(n.id) ?? false
        const active = !hover || isHover || isNeighbour
        ctx!.beginPath()
        ctx!.arc(n.x, n.y, nodeRadius(n.degree), 0, Math.PI * 2)
        ctx!.fillStyle = active ? (isHover ? COL.focus : COL.node) : COL.nodeDim
        ctx!.fill()
        if (isHover) {
          ctx!.lineWidth = 2 / t.k
          ctx!.strokeStyle = COL.focus
          ctx!.stroke()
        }
      }

      // Labels — only when zoomed in enough, or for the hovered subgraph.
      const showAllLabels = t.k > 1.6
      if (showAllLabels || hover) {
        ctx!.font = `${11 / t.k}px var(--font-chakra), system-ui, sans-serif`
        ctx!.textAlign = 'center'
        ctx!.textBaseline = 'top'
        for (const n of simNodesRef.current) {
          if (n.x === undefined || n.y === undefined) continue
          const isHover = hover?.id === n.id
          const isNeighbour = neighbours?.has(n.id) ?? false
          if (hover && !isHover && !isNeighbour) continue
          if (!hover && !showAllLabels) continue
          ctx!.fillStyle = hover && !isHover && !isNeighbour ? COL.labelDim : COL.label
          ctx!.fillText(n.title, n.x, n.y + nodeRadius(n.degree) + 1)
        }
      }

      ctx!.restore()
    }

    sim.on('tick', draw)

    // ── Pan / zoom (d3-zoom). Filter yields node-hits to the drag handler. ──
    const zoomBehavior = d3zoom<HTMLCanvasElement, unknown>()
      .scaleExtent([0.15, 6])
      .filter((event: Event) => {
        // Block the browser context menu / right-click; allow wheel + dblclick.
        if (event.type === 'wheel' || event.type === 'dblclick') return true
        const me = event as MouseEvent
        if (me.button != null && me.button !== 0) return false
        // Pointer/mouse down: only pan when NOT starting on a node.
        const rect = canvas!.getBoundingClientRect()
        return nodeAtScreen(me.clientX - rect.left, me.clientY - rect.top) === null
      })
      .on('zoom', (event: D3ZoomEvent<HTMLCanvasElement, unknown>) => {
        transformRef.current = event.transform
        draw()
      })

    const selection = select(canvas)
    selection.call(zoomBehavior)
    // Start centred with a gentle initial zoom.
    const rect0 = wrap.getBoundingClientRect()
    selection.call(zoomBehavior.transform, zoomIdentity.translate(rect0.width / 2, rect0.height / 2).scale(0.85))

    // ── Node drag (manual, pointer-captured). ──
    function pointerToScreen(e: PointerEvent): { x: number; y: number } {
      const rect = canvas!.getBoundingClientRect()
      return { x: e.clientX - rect.left, y: e.clientY - rect.top }
    }

    function onPointerDown(e: PointerEvent) {
      if (e.button !== 0) return
      const { x, y } = pointerToScreen(e)
      const hit = nodeAtScreen(x, y)
      if (!hit) return // empty space → zoom handles panning
      e.preventDefault()
      canvas!.setPointerCapture(e.pointerId)
      draggingRef.current = hit
      sim.alphaTarget(0.3).restart()
      const t = transformRef.current
      hit.fx = t.invertX(x)
      hit.fy = t.invertY(y)
    }

    function onPointerMove(e: PointerEvent) {
      const { x, y } = pointerToScreen(e)
      const drag = draggingRef.current
      if (drag) {
        const t = transformRef.current
        drag.fx = t.invertX(x)
        drag.fy = t.invertY(y)
        return
      }
      // Hover.
      const hit = nodeAtScreen(x, y)
      if (hit !== hoverRef.current) {
        hoverRef.current = hit
        canvas!.style.cursor = hit ? 'pointer' : 'grab'
        draw()
      }
      if (hit) {
        setTooltip({ x, y, title: hit.title, tags: hit.tags, degree: hit.degree })
      } else {
        setTooltip(null)
      }
    }

    function onPointerUp(e: PointerEvent) {
      const drag = draggingRef.current
      if (!drag) return
      draggingRef.current = null
      try {
        canvas!.releasePointerCapture(e.pointerId)
      } catch {
        /* pointer already released */
      }
      sim.alphaTarget(KEEP_ALIVE)
      // Release the pin so the node rejoins the living simulation.
      drag.fx = null
      drag.fy = null
    }

    // Click-to-navigate: a clean tap on a node (no meaningful drag).
    let downPt: { x: number; y: number } | null = null
    function onClickDown(e: PointerEvent) {
      downPt = pointerToScreen(e)
    }
    function onClickUp(e: PointerEvent) {
      if (!downPt) return
      const up = pointerToScreen(e)
      const moved = Math.hypot(up.x - downPt.x, up.y - downPt.y)
      downPt = null
      if (moved > 4) return
      const hit = nodeAtScreen(up.x, up.y)
      if (hit) router.push(`/founder/wiki/${encodeURIComponent(hit.slug)}`)
    }

    canvas.addEventListener('pointerdown', onPointerDown)
    canvas.addEventListener('pointerdown', onClickDown)
    canvas.addEventListener('pointermove', onPointerMove)
    canvas.addEventListener('pointerup', onPointerUp)
    canvas.addEventListener('pointerup', onClickUp)
    canvas.addEventListener('pointerleave', () => {
      hoverRef.current = null
      setTooltip(null)
      draw()
    })
    canvas.style.cursor = 'grab'

    const ro = new ResizeObserver(() => {
      resize()
      draw()
    })
    ro.observe(wrap)

    return () => {
      sim.stop()
      ro.disconnect()
      selection.on('.zoom', null)
      canvas.removeEventListener('pointerdown', onPointerDown)
      canvas.removeEventListener('pointerdown', onClickDown)
      canvas.removeEventListener('pointermove', onPointerMove)
      canvas.removeEventListener('pointerup', onPointerUp)
      canvas.removeEventListener('pointerup', onClickUp)
    }
  }, [nodes, edges, nodeAtScreen, router])

  return (
    <div
      ref={wrapRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minHeight: 0,
        overflow: 'hidden',
        borderRadius: 2,
        border: '1px solid rgba(45,187,87,0.20)',
        background: '#fffdf7',
      }}
    >
      <canvas ref={canvasRef} style={{ display: 'block', touchAction: 'none' }} />
      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(tooltip.x + 14, (sizeRef.current.w || 0) - 220),
            top: tooltip.y + 14,
            pointerEvents: 'none',
            maxWidth: 220,
            padding: '8px 10px',
            borderRadius: 2,
            border: '1px solid rgba(45,187,87,0.25)',
            background: '#ffffff',
            boxShadow: '0 6px 18px rgba(20,36,27,0.12)',
            fontSize: 12,
            color: '#14241b',
            zIndex: 5,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{tooltip.title}</div>
          <div style={{ color: '#5a6b62', fontSize: 11 }}>
            {tooltip.degree} {tooltip.degree === 1 ? 'link' : 'links'}
          </div>
          {tooltip.tags.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, marginTop: 4 }}>
              {tooltip.tags.slice(0, 6).map((tag) => (
                <span
                  key={tag}
                  style={{
                    fontSize: 10,
                    padding: '1px 5px',
                    borderRadius: 2,
                    background: 'rgba(45,187,87,0.10)',
                    color: '#15803d',
                    border: '1px solid rgba(45,187,87,0.18)',
                  }}
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
