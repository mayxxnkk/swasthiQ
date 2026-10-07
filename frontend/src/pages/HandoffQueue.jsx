import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import styles from './HandoffQueue.module.css'

const REASON_LABELS = {
  clinical_urgent:   { label: 'CLINICAL',           color: '#dc2626' },
  medical_advice:    { label: 'MEDICAL ADVICE',      color: '#d97706' },
  not_authorised:    { label: 'NOT AUTHORISED',      color: '#7c3aed' },
  ambiguous_patient: { label: 'AMBIGUOUS PATIENT',   color: '#2563eb' },
  out_of_scope:      { label: 'OUT OF SCOPE',        color: '#0f7173' },
}

const STATE_LABEL = {
  booked:      { label: 'Booked',      bg: '#dcfce7', color: '#16a34a' },
  rescheduled: { label: 'Rescheduled', bg: '#dbeafe', color: '#1d4ed8' },
  cancelled:   { label: 'Cancelled',   bg: '#fee2e2', color: '#dc2626' },
  escalated:   { label: 'Escalated',   bg: '#fef3c7', color: '#d97706' },
  refused:     { label: 'Refused',     bg: '#f3f4f6', color: '#6b7280' },
  abandoned:   { label: 'Abandoned',   bg: '#f3f4f6', color: '#6b7280' },
}

function fmt(ms) {
  if (!ms) return '—'
  const d = new Date(ms)
  return d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function Pill({ reason }) {
  const r = REASON_LABELS[reason] || { label: reason?.toUpperCase() || '—', color: '#6b7280' }
  return (
    <span
      className={styles.pill}
      style={{ color: r.color, borderColor: r.color + '44', background: r.color + '11' }}
    >
      {r.label}
    </span>
  )
}

function StatePill({ state }) {
  const s = STATE_LABEL[state] || { label: state, bg: '#f3f4f6', color: '#6b7280' }
  return (
    <span
      className={styles.statePill}
      style={{ background: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  )
}

export default function HandoffQueue() {
  const navigate = useNavigate()
  const [conversations, setConversations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [resolved, setResolved] = useState(new Set())

  const load = useCallback(async () => {
    try {
      const data = await api.listConversations()
      setConversations(data.conversations || [])
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const escalated = conversations.filter(c => c.terminal_state === 'escalated')
  const open = escalated.filter(c => !resolved.has(c.conversation_id))
  const urgent = open.filter(c => c.escalation_reason === 'clinical_urgent')
  const completedByAgent = conversations.filter(c => c.terminal_state !== 'escalated')

  const today = new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })

  if (loading) return <div className={styles.loading}>Loading conversations…</div>
  if (error) return <div className={styles.error}>⚠ {error}</div>

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        {/* Header */}
        <div className={styles.cardHeader}>
          <div>
            <h1 className={styles.title}>Handoff Queue</h1>
            <p className={styles.subtitle}>Sunrise Clinic, Dehradun — conversations the agent escalated</p>
          </div>
          <span className={styles.openBadge}>{open.length} OPEN</span>
        </div>

        {/* Counter row */}
        <div className={styles.counters}>
          <div className={styles.counter}>
            <div className={styles.counterVal}>{conversations.length}</div>
            <div className={styles.counterLbl}>CONVERSATIONS</div>
            <div className={styles.counterSub}>{today}</div>
          </div>
          <div className={styles.counterDivider} />
          <div className={styles.counter}>
            <div className={styles.counterVal}>{completedByAgent.length}</div>
            <div className={styles.counterLbl}>COMPLETED BY AGENT</div>
            <div className={styles.counterSub}>
              {conversations.length > 0
                ? Math.round((completedByAgent.length / conversations.length) * 100)
                : 0}%
            </div>
          </div>
          <div className={styles.counterDivider} />
          <div className={styles.counter}>
            <div className={styles.counterVal}>{escalated.length}</div>
            <div className={styles.counterLbl}>ESCALATED</div>
            <div className={styles.counterSub}>{open.length} still open</div>
          </div>
          <div className={styles.counterDivider} />
          <div className={styles.counter}>
            <div className={styles.counterValUrgent}>{urgent.length}</div>
            <div className={styles.counterLbl}>URGENT</div>
            <div className={styles.counterSub}>clinical, unresolved</div>
          </div>
        </div>

        {/* Open handoffs table */}
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Open handoffs</h2>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>CONVERSATION</th>
                <th>CALLER SAID</th>
                <th>REASON</th>
                <th>TIME</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {open.length === 0 && (
                <tr>
                  <td colSpan={5} className={styles.emptyRow}>No open handoffs</td>
                </tr>
              )}
              {open.map(c => (
                <tr
                  key={c.conversation_id}
                  className={styles.row}
                  onClick={() => navigate(`/conversation/${c.conversation_id}`)}
                >
                  <td className={styles.convId}>{c.conversation_id}</td>
                  <td className={styles.callerSaid}>
                    "{c.reply?.substring(0, 60)}{c.reply?.length > 60 ? '…' : ''}"
                  </td>
                  <td><Pill reason={c.escalation_reason} /></td>
                  <td className={styles.time}>
                    {fmt(c.metrics?.latency_ms)}
                  </td>
                  <td>
                    <button
                      className={styles.resolveBtn}
                      onClick={e => {
                        e.stopPropagation()
                        setResolved(prev => new Set([...prev, c.conversation_id]))
                      }}
                    >
                      Resolve
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* All conversations table */}
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>All conversations</h2>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>CONVERSATION</th>
                <th>STATE</th>
                <th>PATIENT</th>
                <th>TOOLS</th>
                <th>TURNS</th>
                <th>TOKENS</th>
                <th>LATENCY</th>
              </tr>
            </thead>
            <tbody>
              {conversations.length === 0 && (
                <tr>
                  <td colSpan={7} className={styles.emptyRow}>
                    No results yet — run the conversations against your agent first.
                  </td>
                </tr>
              )}
              {conversations.map(c => (
                <tr
                  key={c.conversation_id}
                  className={styles.row}
                  onClick={() => navigate(`/conversation/${c.conversation_id}`)}
                >
                  <td className={styles.convId}>{c.conversation_id}</td>
                  <td><StatePill state={c.terminal_state} /></td>
                  <td className={styles.gray}>{c.patient_id || '—'}</td>
                  <td className={styles.gray}>{c.tool_calls?.length ?? 0}</td>
                  <td className={styles.gray}>{c.metrics?.turns ?? '—'}</td>
                  <td className={styles.gray}>{c.metrics?.tokens?.toLocaleString() ?? '—'}</td>
                  <td className={styles.gray}>{c.metrics?.latency_ms ? `${c.metrics.latency_ms} ms` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
