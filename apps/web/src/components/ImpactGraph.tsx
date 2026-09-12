import { Background, Controls, ReactFlow, type Edge, type Node } from '@xyflow/react'
import type { Component } from '../types'

const colors: Record<string, string> = { API: '#5eead4', BUSINESS_RULE: '#fbbf24', DATABASE: '#a78bfa', JOB: '#fb7185', TEST: '#60a5fa', INTEGRATION: '#f97316' }

export function ImpactGraph({ components, edges, onSelect }: { components: Component[]; edges: { source: string; target: string; relationship: string }[]; onSelect: (component: Component) => void }) {
  const nodes: Node[] = components.slice(0, 30).map((component, index) => ({
    id: component.id,
    position: { x: (index % 5) * 210, y: Math.floor(index / 5) * 120 },
    data: { label: `${component.type}\n${component.name}` },
    style: { background: '#10201b', color: '#e8f5ef', border: `1px solid ${colors[component.type] ?? '#436056'}`, borderRadius: 8, fontSize: 11, width: 170 },
  }))
  const allowed = new Set(nodes.map((node) => node.id))
  const flowEdges: Edge[] = edges.filter((edge) => allowed.has(edge.source) && allowed.has(edge.target)).map((edge, index) => ({ id: `e-${index}`, source: edge.source, target: edge.target, label: edge.relationship, style: { stroke: '#436056' }, labelStyle: { fill: '#8ba39a', fontSize: 9 } }))
  return <div className="graph"><ReactFlow nodes={nodes} edges={flowEdges} fitView onNodeClick={(_, node) => { const component = components.find((item) => item.id === node.id); if (component) onSelect(component) }}><Background color="#203a31" gap={24}/><Controls /></ReactFlow></div>
}
