import { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle, ArrowRight, Boxes, CheckCircle2, ChevronDown, Code2, Download,
  FileCode2, FlaskConical, GitBranch, GitCompareArrows, Search, ShieldCheck, XCircle,
} from 'lucide-react'
import { ImpactGraph } from './components/ImpactGraph'
import { EvidenceDrawer } from './components/EvidenceDrawer'
import { PrecisionDashboard } from './components/PrecisionDashboard'
import { api } from './lib/api'
import type { Analysis, Component, Evidence, Repository } from './types'

const demoPath = 'tests/evaluation/demo_repository'
const demoRequest = 'Add RETURNED as a new order state that can occur after shipment and allow refunds after successful warehouse inspection.'
type Tab = 'simulation' | 'impact' | 'risks' | 'evidence' | 'tests' | 'decision' | 'precision'

export default function App() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [request, setRequest] = useState(demoRequest)
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [repositoryId, setRepositoryId] = useState('')
  const [sourcePath, setSourcePath] = useState(demoPath)
  const [snapshot, setSnapshot] = useState<{ snapshot_id: string; commit_sha: string; status: string }>()
  const [selected, setSelected] = useState<Evidence>()
  const [selectedComponent, setSelectedComponent] = useState<Component>()
  const [diff, setDiff] = useState('')
  const [showDiff, setShowDiff] = useState(false)
  const [status, setStatus] = useState('READY')
  const [error, setError] = useState('')
  const [tab, setTab] = useState<Tab>('simulation')
  const [feedback, setFeedback] = useState<Record<string, string>>({})
  const [currentUser, setCurrentUser] = useState<{ user_id: string; organization_id: string; role: string; email?: string } | null>(null)

  useEffect(() => {
    api.me().then(setCurrentUser).catch(() => setCurrentUser(null))
    api.repositories().then((items) => {
      setRepositories(items)
      if (items[0]) { setRepositoryId(items[0].id); setSourcePath(items[0].source_path ?? '') }
    }).catch(() => undefined)
  }, [])

  const repository = repositories.find((item) => item.id === repositoryId)
  const evidenceById = useMemo(() => new Map(analysis?.evidence.map((item) => [item.id, item])), [analysis])
  const pickEvidence = (id?: string) => id && setSelected(evidenceById.get(id))
  const busy = !['READY', 'VERIFIED', 'FAILED'].includes(status)

  async function ensureRepository() {
    if (repositoryId) return repositoryId
    const created = await api.createRepository({ name: 'E-commerce Order Service', source_path: sourcePath })
    setRepositories((current) => [...current, created]); setRepositoryId(created.id)
    return created.id
  }

  async function sync() {
    setError(''); setStatus('SNAPSHOTTING')
    try { const repo = await ensureRepository(); setSnapshot(await api.syncRepository(repo)); setStatus('READY') }
    catch (reason) { setError(message(reason)); setStatus('FAILED') }
  }

  async function simulate() {
    setError(''); setStatus('PREPARING SNAPSHOT')
    try {
      const repo = await ensureRepository()
      const synced = await api.syncRepository(repo); setSnapshot(synced)
      setStatus('INTERPRETING CHANGE')
      const change = await api.createChange({ repository_id: repo, description: request, proposed_diff: diff.trim() || undefined })
      const job = await api.analyze(change.id)
      for (let attempt = 0; attempt < 120; attempt++) {
        const current = await api.job(job.id); setStatus(`${current.status} · ${current.progress}%`)
        if (current.status === 'FAILED') throw new Error(current.error ?? 'Analysis failed')
        if (current.analysis_id) {
          const result = await api.analysis(current.analysis_id)
          setAnalysis(result); setSnapshot({ snapshot_id: result.snapshot_id, commit_sha: result.commit_sha, status: 'ANALYZED' })
          setStatus('VERIFIED'); setTab('simulation'); return
        }
        await new Promise((resolve) => setTimeout(resolve, 500))
      }
      throw new Error('Analysis timed out')
    } catch (reason) { setError(message(reason)); setStatus('FAILED') }
  }

  function selectComponent(component: Component) { setSelectedComponent(component); pickEvidence(component.evidence_ids[0]) }
  async function recordFeedback(id: string, decision: string) {
    if (!analysis) return
    await api.feedback(analysis.analysis_id, id, decision); setFeedback((current) => ({ ...current, [id]: decision }))
  }
  async function exportReport(format: 'json' | 'markdown') {
    if (!analysis) return
    const result = await api.report(analysis.analysis_id, format)
    const content = format === 'json' ? JSON.stringify(result, null, 2) : (result as { content: string }).content
    const url = URL.createObjectURL(new Blob([content], { type: format === 'json' ? 'application/json' : 'text/markdown' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `changetrace-${analysis.analysis_id}.${format === 'json' ? 'json' : 'md'}`; anchor.click(); URL.revokeObjectURL(url)
  }

  async function handleLogout() {
    try {
      await api.logout()
      setCurrentUser(null)
    } catch {
      // ignore
    }
  }

  return <div className="app-shell">
    <header>
      <button className="brand brand-button" onClick={() => setTab('simulation')}><span>CT</span> ChangeTrace</button>
      <nav>{(['simulation', 'impact', 'risks', 'evidence', 'tests', 'decision', 'precision'] as Tab[]).map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)} disabled={!analysis && item !== 'simulation' && item !== 'precision'}>{item === 'tests' ? 'Test Gaps' : item === 'precision' ? 'Precision' : title(item)}</button>)}</nav>
      <div className="header-right">
        {currentUser ? (
          <div className="user-profile">
            <span className="user-email">{currentUser.email || currentUser.role}</span>
            <button className="auth-button logout" onClick={handleLogout}>Sign out</button>
          </div>
        ) : (
          <a className="auth-button login" href={api.loginUrl}>Sign in with GitHub</a>
        )}
        <div className={`snapshot ${snapshot ? 'ready' : ''}`}>{snapshot ? snapshot.commit_sha.slice(0, 8) : 'NOT INDEXED'} <i/></div>
      </div>
    </header>
    <main>
      {tab === 'simulation' && <>
        <section className="hero"><p className="eyebrow">BUSINESS CHANGE SIMULATOR</p><h1>Know what your change will<br/><em>break before you make it.</em></h1><p>Trace proposed behavior through code, rules, data, integrations, and tests—with source evidence behind every conclusion.</p></section>
        <section className="repository-card">
          <div className="repo-icon"><GitBranch/></div><div><p className="eyebrow">{repository ? 'SELECTED REPOSITORY' : 'DEMO REPOSITORY'}</p><h3>{repository?.name ?? 'E-commerce Order Service'}</h3><p>{sourcePath || 'Choose a repository path'} · Python / TypeScript / SQL</p></div>
          <div className="repo-actions"><select value={repositoryId} onChange={(event) => { setRepositoryId(event.target.value); const repo = repositories.find((item) => item.id === event.target.value); if (repo) setSourcePath(repo.source_path ?? '') }}><option value="">New local repository</option>{repositories.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button className="secondary" onClick={sync}>SYNC</button><span className={snapshot ? 'indexed' : 'unverified'}>● {snapshot ? snapshot.status : 'NOT INDEXED'}</span></div>
          {!repositoryId && <input className="path-input" aria-label="Repository path" value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} />}
          {snapshot && <div className="commit-line">snapshot {snapshot.snapshot_id} · commit {snapshot.commit_sha}</div>}
        </section>
        <section className="composer">
          <div className="composer-label"><span>What are you planning to change?</span><small>NATURAL LANGUAGE REQUIREMENT</small></div>
          <textarea aria-label="Change request" value={request} onChange={(event) => setRequest(event.target.value)} />
          <button className="diff-toggle" onClick={() => setShowDiff((value) => !value)}><GitCompareArrows size={16}/> Optional proposed Git diff <ChevronDown size={15}/></button>
          {showDiff && <div className="diff-panel"><textarea aria-label="Proposed Git diff" value={diff} onChange={(event) => setDiff(event.target.value)} placeholder={'diff --git a/path b/path\n--- a/path\n+++ b/path\n@@ ...'} /><p>The patch is parsed and applied in an isolated copy. Repository code is never executed.</p></div>}
          <div className="composer-footer"><span><ShieldCheck size={15}/> Deterministic analysis · evidence-bound</span><button onClick={simulate} disabled={busy || request.trim().length < 10}><Search size={17}/> SIMULATE CHANGE <ArrowRight size={17}/></button></div>
        </section>
        <div className={`run-status ${error ? 'error' : ''}`}><i/>{status}{error && ` — ${error}`}</div>
        {analysis && <Overview analysis={analysis} onTab={setTab}/>}
      </>}
      {analysis && tab === 'impact' && <ImpactView analysis={analysis} onSelect={selectComponent} selected={selectedComponent}/>}
      {analysis && tab === 'risks' && <RiskView analysis={analysis} pickEvidence={pickEvidence} feedback={feedback} onFeedback={recordFeedback}/>}
      {analysis && tab === 'evidence' && <EvidenceView analysis={analysis} onSelect={setSelected}/>}
      {analysis && tab === 'tests' && <TestView analysis={analysis} pickEvidence={pickEvidence}/>}
      {analysis && tab === 'decision' && <DecisionView analysis={analysis} exportReport={exportReport}/>}
      {tab === 'precision' && <PrecisionDashboard />}
    </main>
    <EvidenceDrawer evidence={selected} onClose={() => setSelected(undefined)}/>
  </div>
}

function Overview({ analysis, onTab }: { analysis: Analysis; onTab: (tab: Tab) => void }) {
  const highest = [...analysis.risks].sort((a, b) => b.risk_score - a.risk_score)[0]
  return <><section className="result-heading"><div><p className="eyebrow">CHANGE SIMULATION</p><h2>{analysis.intent.states_added.length ? `Introduce ${analysis.intent.states_added.join(', ')}` : 'Proposed business change'}</h2><p>{analysis.change_request}</p></div><button className={`decision-badge ${analysis.decision.status.toLowerCase()}`} onClick={() => onTab('decision')}><small>RECOMMENDATION</small>{decisionLabel(analysis.decision.status)}<ArrowRight size={17}/></button></section>
    {analysis.change_set && <section className="delta-strip"><GitCompareArrows/><div><strong>Before</strong><code>{analysis.change_set.before_commit_sha.slice(0, 10)}</code></div><ArrowRight/><div><strong>Proposed</strong><code>{analysis.change_set.after_commit_sha.slice(0, 18)}</code></div><span>{analysis.change_set.files.length} changed file{analysis.change_set.files.length === 1 ? '' : 's'} · {analysis.graph_delta?.added_components.length ?? 0} nodes added · {analysis.graph_delta?.modified_components.length ?? 0} modified</span></section>}
    <section className="metrics" aria-label="Impact summary"><Metric icon={<Boxes/>} value={analysis.impact_summary.affected_components} label="Affected components"/><Metric icon={<GitBranch/>} value={analysis.business_rules.length} label="Business rules"/><Metric icon={<FlaskConical/>} value={analysis.test_gaps.filter((item) => item.coverage === 'MISSING').length} label="Test gaps"/><Metric icon={<AlertTriangle/>} value={highest?.severity ?? 'LOW'} label={`${highest?.risk_score ?? 0} / 100 risk`} hot={highest?.severity === 'HIGH' || highest?.severity === 'CRITICAL'}/></section>
    <section className="quick-grid"><button onClick={() => onTab('impact')}><span>01</span><h3>Trace the impact</h3><p>Inspect {analysis.components.length} likely or confirmed nodes and {analysis.candidate_components.length} candidates.</p><ArrowRight/></button><button onClick={() => onTab('risks')}><span>02</span><h3>Review the risks</h3><p>Separate deterministic risk, confidence, and evidence strength.</p><ArrowRight/></button><button onClick={() => onTab('tests')}><span>03</span><h3>Close test gaps</h3><p>Verify behavior, authorization, integration, and consistency.</p><ArrowRight/></button></section>
  </>
}

function ImpactView({ analysis, onSelect, selected }: { analysis: Analysis; onSelect: (component: Component) => void; selected?: Component }) { return <section className="page-section"><PageTitle number="01" eyebrow="IMPACT DISCOVERY" title="Why these components are affected" subtitle={`${analysis.components.length} traced nodes across ${analysis.impact_summary.affected_files} files`}/><div className="impact-layout"><ImpactGraph components={analysis.components} edges={analysis.graph_edges} onSelect={onSelect}/><aside className="node-inspector"><p className="eyebrow">WHY IS THIS AFFECTED?</p>{selected ? <><span className="type-tag">{selected.type}</span><h3>{selected.name}</h3><p>{selected.reason}</p><dl><dt>File</dt><dd>{selected.location.file}:{selected.location.line_start}</dd><dt>Impact status</dt><dd>{selected.impact_status}</dd><dt>Strength</dt><dd>{selected.evidence_strength}</dd><dt>Path</dt><dd>{selected.reasoning_path.join(' → ') || 'Direct source evidence'}</dd><dt>Evidence</dt><dd>{selected.evidence_ids.length}</dd></dl></> : <p>Select a graph node to inspect its source, relationship, evidence strength, and reasoning path.</p>}</aside></div>{analysis.state_machines.map((machine) => <div className="state-machine" key={machine.id}><p className="eyebrow">STATE MACHINE / {machine.entity}</p><div className="state-row">{machine.states.map((state) => <span key={state}>{state}</span>)}</div><p>{machine.transitions.length} deterministic transition{machine.transitions.length === 1 ? '' : 's'} discovered</p></div>)}</section> }

function RiskView({ analysis, pickEvidence, feedback, onFeedback }: { analysis: Analysis; pickEvidence: (id?: string) => void; feedback: Record<string, string>; onFeedback: (id: string, decision: string) => void }) { return <section className="page-section"><PageTitle number="02" eyebrow="EVIDENCE-LINKED RISKS" title="What could break" subtitle="Numeric risk is deterministic. Confidence and evidence strength are independent."/><div className="risk-grid">{analysis.risks.map((risk) => <article className="risk" key={risk.risk_id}><div><span className={`pill ${risk.severity.toLowerCase()}`}>{risk.severity}</span><span className="score">{risk.risk_score} / 100</span><span className="confidence">Confidence {Math.round(risk.confidence * 100)}%</span><span className="strength">Evidence {risk.evidence_strength}</span></div><h3>{risk.title}</h3><p>{risk.claim}</p><div className="reasoning-chain"><strong>WHY</strong><span>{analysis.intent.states_added[0] ?? 'CHANGE'}</span><ArrowRight/><span>{risk.affected_components.length} COMPONENTS</span><ArrowRight/><span>{risk.support_status}</span></div><p className="reason">{risk.reasoning}</p><div className="evidence-links">{risk.evidence.slice(0, 5).map((id) => <button key={id} onClick={() => pickEvidence(id)}>{evidenceName(analysis, id)}</button>)}</div><footer><strong>Recommended</strong>{risk.recommended_action}</footer><div className="feedback"><span>Is this finding useful?</span>{[['CONFIRM','Confirm'],['REJECT','Reject'],['NOT_RELEVANT','Not relevant']].map(([value,label]) => <button className={feedback[risk.risk_id] === value ? 'selected' : ''} onClick={() => onFeedback(risk.risk_id, value)} key={value}>{label}</button>)}</div></article>)}</div>{analysis.contradictions.length > 0 && <section className="contradictions"><h3>Contradictions requiring review</h3>{analysis.contradictions.map((item) => <article key={item.id}><AlertTriangle/><div><strong>CONTRADICTION · {Math.round(item.confidence * 100)}% confidence</strong><p>{item.claim}</p><div className="evidence-links">{item.evidence_ids.map((id) => <button onClick={() => pickEvidence(id)} key={id}>{evidenceName(analysis,id)}</button>)}</div></div></article>)}</section>}</section> }

function EvidenceView({ analysis, onSelect }: { analysis: Analysis; onSelect: (evidence: Evidence) => void }) { return <section className="page-section"><PageTitle number="03" eyebrow="EVIDENCE" title="Inspect every conclusion" subtitle={`${analysis.evidence.length} immutable references · snapshot ${analysis.snapshot_id}`}/><div className="evidence-table"><div className="table-head"><span>Source</span><span>Type</span><span>Strength</span><span>Quality</span><span>Status</span></div>{analysis.evidence.map((item) => <button key={item.id} onClick={() => onSelect(item)}><span><FileCode2/>{item.location.file}<small>lines {item.location.line_start}–{item.location.line_end}</small></span><span>{item.type.replace('_REFERENCE','')}</span><span>{item.strength}</span><span>{Math.round(item.quality_score * 100)}%</span><span className="valid">● {item.status}</span></button>)}</div></section> }

function TestView({ analysis, pickEvidence }: { analysis: Analysis; pickEvidence: (id?: string) => void }) { const missing = analysis.test_gaps.filter((item) => item.coverage === 'MISSING'); return <section className="page-section"><PageTitle number="04" eyebrow="TEST-GAP GENERATION" title="Verification coverage" subtitle={`${missing.length} confirmed missing scenarios; uncertain coverage is shown separately`}/><div className="scenario-list">{analysis.test_gaps.map((scenario) => <article key={scenario.scenario_id}><span className={`pill ${scenario.priority.toLowerCase()}`}>{scenario.priority}</span><div><p className="category">{scenario.category} · {scenario.coverage.replaceAll('_',' ')}</p><h3>{scenario.behavior}</h3><p><b>Given</b> {scenario.preconditions[0]}</p><p><b>When</b> {scenario.action}</p><p><b>Then</b> {scenario.expected_result}</p><p className="why-missing">{scenario.why_missing}</p><small>Why it matters: {scenario.reason_it_matters}</small></div><button className="evidence-button" onClick={() => pickEvidence(scenario.evidence[0])}>View evidence</button></article>)}</div></section> }

function DecisionView({ analysis, exportReport }: { analysis: Analysis; exportReport: (format: 'json' | 'markdown') => void }) { return <section className="page-section"><PageTitle number="05" eyebrow="CHANGE DECISION" title={decisionLabel(analysis.decision.status)} subtitle="Derived from configured, deterministic release policy"/><article className={`decision-card ${analysis.decision.status.toLowerCase()}`}><div className="decision-icon">{analysis.decision.status === 'GO' ? <CheckCircle2/> : analysis.decision.status === 'BLOCK' ? <XCircle/> : <AlertTriangle/>}</div><div><p className="eyebrow">RECOMMENDATION</p><h2>{decisionLabel(analysis.decision.status)}</h2><h4>Why</h4><ul>{analysis.decision.rationale.map((reason) => <li key={reason}>{reason}</li>)}</ul></div></article><section className="plan"><p className="eyebrow">REQUIRED ACTIONS</p><ol>{analysis.change_plan.map((step, index) => <li key={step}><span>{String(index + 1).padStart(2,'0')}</span>{step}<CheckCircle2/></li>)}</ol><div className="report-actions"><button onClick={() => exportReport('markdown')}><Download/> Export Markdown</button><button onClick={() => exportReport('json')}><Code2/> Export JSON</button></div><div className="provenance">Analysis {analysis.analysis_id} · Snapshot {analysis.snapshot_id} · Commit {analysis.commit_sha} · Analyzer {analysis.analyzer_version} · Semantic mode {analysis.semantic_analysis}</div></section></section> }

function PageTitle({ number, eyebrow, title: heading, subtitle }: { number: string; eyebrow: string; title: string; subtitle: string }) { return <div className="page-title"><span>{number}</span><div><p className="eyebrow">{eyebrow}</p><h1>{heading}</h1><p>{subtitle}</p></div></div> }
function Metric({ icon, value, label, hot = false }: { icon: React.ReactNode; value: React.ReactNode; label: string; hot?: boolean }) { return <article className={hot ? 'hot' : ''}><span>{icon}</span><strong>{value}</strong><p>{label}</p></article> }
function title(value: string) { return value.charAt(0).toUpperCase() + value.slice(1) }
function message(reason: unknown) { return reason instanceof Error ? reason.message : 'Analysis failed' }
function decisionLabel(status: string) { return status === 'GO' ? 'GO TO IMPLEMENTATION' : status === 'BLOCK' ? 'BLOCK CHANGE' : 'REVIEW BEFORE IMPLEMENTATION' }
function evidenceName(analysis: Analysis, id: string) { const item = analysis.evidence.find((evidence) => evidence.id === id); return item ? `${item.location.file}:${item.location.line_start}` : id }
