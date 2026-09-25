import { useEffect, useState } from 'react'
import { CheckCircle2, RefreshCw, ShieldAlert, Sliders, Target, XCircle } from 'lucide-react'
import { api } from '../lib/api'

interface FeedbackMetrics {
  total_feedback_count: number
  accepted_count: number
  rejected_count: number
  overall_precision: number
  precision_by_kind: Record<string, { precision: number; total: number; accepted: number; multiplier: number; penalty: number }>
  precision_by_version: Record<string, { precision: number; total: number; accepted: number }>
  calibrations_active: number
}

interface FeedbackSummary {
  rejection_reasons: Record<string, number>
  calibrated_penalties: Record<string, number>
  calibrated_multipliers: Record<string, number>
  rules: Record<string, string>
}

export function PrecisionDashboard() {
  const [metrics, setMetrics] = useState<FeedbackMetrics | null>(null)
  const [summary, setSummary] = useState<FeedbackSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function loadData() {
    setLoading(true)
    setError('')
    try {
      const [m, s] = await Promise.all([api.feedbackMetrics(), api.feedbackSummary()])
      setMetrics(m)
      setSummary(s)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load precision metrics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  return (
    <div className="precision-dashboard">
      <div className="precision-header">
        <div>
          <p className="eyebrow">QUALITY & EVALUATION</p>
          <h2>Precision & Feedback Dashboard</h2>
          <p>Deterministic empirical calibration derived from code-review feedback without unverified model retraining.</p>
        </div>
        <button className="secondary refresh-button" onClick={loadData} disabled={loading}>
          <RefreshCw size={15} className={loading ? 'spinning' : ''} /> Refresh
        </button>
      </div>

      {error && <div className="run-status error">{error}</div>}

      {metrics && (
        <>
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-icon"><Target size={20} /></div>
              <div className="kpi-value">{Math.round(metrics.overall_precision * 100)}%</div>
              <div className="kpi-label">Empirical Precision</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-icon"><CheckCircle2 size={20} color="#22c55e" /></div>
              <div className="kpi-value">{metrics.accepted_count}</div>
              <div className="kpi-label">True Positives (Accepted)</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-icon"><XCircle size={20} color="#ef4444" /></div>
              <div className="kpi-value">{metrics.rejected_count}</div>
              <div className="kpi-label">False Positives (Rejected)</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-icon"><Sliders size={20} color="#3b82f6" /></div>
              <div className="kpi-value">{metrics.calibrations_active}</div>
              <div className="kpi-label">Active Calibration Rules</div>
            </div>
          </div>

          <div className="dashboard-section">
            <h3>Precision by Finding Category</h3>
            {Object.keys(metrics.precision_by_kind).length === 0 ? (
              <p className="empty-text">No category feedback recorded yet. Accept or reject findings to calibrate.</p>
            ) : (
              <div className="table-wrapper">
                <table className="precision-table">
                  <thead>
                    <tr>
                      <th>Finding Type</th>
                      <th>Reviewed</th>
                      <th>Accepted</th>
                      <th>Precision</th>
                      <th>Confidence Multiplier</th>
                      <th>Threshold Penalty</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(metrics.precision_by_kind).map(([cat, item]) => (
                      <tr key={cat}>
                        <td><strong>{cat}</strong></td>
                        <td>{item.total}</td>
                        <td>{item.accepted}</td>
                        <td>
                          <span className={`status-pill ${item.precision >= 0.8 ? 'green' : item.precision >= 0.6 ? 'yellow' : 'red'}`}>
                            {Math.round(item.precision * 100)}%
                          </span>
                        </td>
                        <td>{item.multiplier}x</td>
                        <td>+{item.penalty}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {summary && Object.keys(summary.rules).length > 0 && (
            <div className="dashboard-section">
              <h3>Active Calibration Explanations</h3>
              <div className="rules-list">
                {Object.entries(summary.rules).map(([cat, rule]) => (
                  <div key={cat} className="rule-card">
                    <div className="rule-kind">{cat}</div>
                    <div className="rule-text">{rule}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {summary && Object.keys(summary.rejection_reasons).length > 0 && (
            <div className="dashboard-section">
              <h3>Top Rejection Reasons Reported</h3>
              <div className="rejection-reasons-list">
                {Object.entries(summary.rejection_reasons).map(([reason, count]) => (
                  <div key={reason} className="rejection-reason-pill">
                    <ShieldAlert size={14} />
                    <span>{reason}</span>
                    <strong>{count}</strong>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
