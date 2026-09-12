import { X } from 'lucide-react'
import type { Evidence } from '../types'

export function EvidenceDrawer({ evidence, onClose }: { evidence?: Evidence; onClose: () => void }) {
  if (!evidence) return null
  return <aside className="drawer" aria-label="Evidence viewer">
    <button className="icon-button" onClick={onClose} aria-label="Close evidence"><X size={18}/></button>
    <p className="eyebrow">PROVENANCE / {evidence.type}</p>
    <h2>{evidence.location.file}</h2>
    <div className="evidence-meta"><span>Lines {evidence.location.line_start}–{evidence.location.line_end}</span><span>{evidence.location.symbol}</span></div>
    <div className="evidence-badges"><span>{evidence.strength}</span><span>Quality {Math.round(evidence.quality_score * 100)}%</span></div>
    <p>{evidence.reason}</p>
    <pre><code>{evidence.snippet}</code></pre>
    <dl>
      <dt>Repository</dt><dd>{evidence.repository_id}</dd>
      <dt>Snapshot</dt><dd>{evidence.repository_snapshot_id}</dd>
      <dt>Commit</dt><dd className="hash">{evidence.commit_sha}</dd>
      <dt>Content hash</dt><dd className="hash">{evidence.content_hash}</dd>
      <dt>Status</dt><dd className="valid">● {evidence.status}</dd>
    </dl>
  </aside>
}
