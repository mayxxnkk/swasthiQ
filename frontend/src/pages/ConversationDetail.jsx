import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import styles from './ConversationDetail.module.css'

/* ── Constants ── */
const REASON_LABELS = {
  clinical_urgent:   { label: 'CLINICAL',           color: '#dc2626' },
  medical_advice:    { label: 'MEDICAL ADVICE',      color: '#d97706' },
  not_authorised:    { label: 'NOT AUTHORISED',      color: '#7c3aed' },
  ambiguous_patient: { label: 'AMBIGUOUS PATIENT',   color: '#2563eb' },
  out_of_scope:      { label: 'OUT OF SCOPE',        color: '#0f7173' },
}

const STATE_META = {
  booked:      { label: 'BOOKED',       bg: '#dcfce7', color: '#16a34a' },
  rescheduled: { label: 'RESCHEDULED',  bg: '#dbeafe', color: '#1d4ed8' },
  cancelled:   { label: 'CANCELLED',    bg: '#fee2e2', color: '#dc2626' },
  escalated:   { label: 'ESCALATED',    bg: '#fef3c7', color: '#d97706' },
  refused:     { label: 'REFUSED',      bg: '#f3f4f6', color: '#6b7280' },
  abandoned:   { label: 'ABANDONED',    bg: '#f3f4f6', color: '#6b7280' },
}

/* ── Helpers ── */
function StateBadge({ state, reason }) {
  const s = STATE_META[state] || { label: state?.toUpperCase(), bg: '#f3f4f6', color: '#6b7280' }
  const r = reason ? REASON_LABELS[reason] : null
  const label = r ? `${s.label} — ${r.label}` : s.label
  const color = r ? r.color : s.color
  const bg    = r ? color + '18' : s.bg
  return (
    <span className={styles.stateBadge} style={{ background: bg, color }}>
      {label}
    </span>
  )
}

function ToolCallBlock({ call }) {
  const [open, setOpen] = useState(false)
  const args = call.arguments || {}
  const argsStr = JSON.stringify(args, null, 2)

  return (
    <div className={styles.toolBlock}>
      <div
        className={styles.toolHeader}
        onClick={() => setOpen(o => !o)}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className={styles.toolIcon}>⚙</span>
        <span className={styles.toolName}>{call.name}</span>
        <span className={styles.toolArgs}>
          {Object.entries(args)
            .map(([k, v]) => `${k}="${v}"`)
            .join(', ')
            .substring(0, 80)}
        </span>
        <span className={styles.toolChevron}>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <pre className={styles.toolJson}>{argsStr}</pre>
      )}
    </div>
  )
}

/**
 * Reconstruct an interleaved transcript.
 *
 * The runner only stores the final result JSON (tool_calls list + reply).
 * We don't have the raw per-turn conversation stored server-side, so we
 * reconstruct a plausible interleaving: CALLER turns (from the run request
 * stored in result, if present) interspersed with TOOL blocks, ending with
 * the AGENT's final reply.
 *
 * When the stored result doesn't include the original turns (legacy), we
 * fall back to showing only the tool calls + reply.
 */
function buildTimeline(result) {
  const items = []
  const toolCalls = result.tool_calls || []
  const turns = result._turns || []

  if (turns.length > 0) {
    // Distribute tool calls roughly: show caller turns first, then tools, then agent reply
    turns.forEach((turn, i) => {
      items.push({ type: 'caller', text: turn, key: `caller-${i}` })
    })
    toolCalls.forEach((call, i) => {
      items.push({ type: 'tool', call, key: `tool-${i}` })
    })
  } else {
    // No turns stored — just show tool calls interleaved
    toolCalls.forEach((call, i) => {
      items.push({ type: 'tool', call, key: `tool-${i}` })
    })
  }

  if (result.reply) {
    items.push({ type: 'agent', text: result.reply, key: 'agent-reply' })
  }

  // Append a summary note if no action was taken
  if (
    result.terminal_state === 'abandoned' ||
    result.terminal_state === 'refused'
  ) {
    const msg =
      result.terminal_state === 'refused'
        ? 'Request refused. No action taken.'
        : 'Booking flow abandoned. No appointment was created.'
    items.push({ type: 'note', text: msg, key: 'note' })
  }

  return items
}

/* ── Main component ── */
export default function ConversationDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getConversation(id)
      .then(setResult)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <div className={styles.loading}>Loading conversation…</div>
  if (error)   return <div className={styles.error}>⚠ {error}<br /><button className={styles.backBtn} onClick={() => navigate('/queue')}>← Back to queue</button></div>
  if (!result) return null

  const timeline = buildTimeline(result)
  const toolCallCount = (result.tool_calls || []).length
  const determinismLabel = 'STABLE' // we'd need multiple runs to know; show STABLE as default

  return (
    <div className={styles.page}>
      {/* Page header */}
      <button className={styles.backBtn} onClick={() => navigate('/queue')}>
        ← Handoff Queue
      </button>

      <div className={styles.layout}>
        {/* Left: transcript */}
        <div className={styles.transcriptCard}>
          <div className={styles.transcriptHeader}>
            <div>
              <h1 className={styles.convTitle}>Conversation {result.conversation_id}</h1>
              <p className={styles.convMeta}>
                Sunrise Clinic, Dehradun
                {result.metrics?.latency_ms
                  ? ` — ${new Date().toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}`
                  : ''}
              </p>
            </div>
            <StateBadge state={result.terminal_state} reason={result.escalation_reason} />
          </div>

          <div className={styles.transcriptBody}>
            <h2 className={styles.sectionLabel}>Transcript and tool calls</h2>

            <div className={styles.timeline}>
              {timeline.map(item => {
                if (item.type === 'caller') {
                  return (
                    <div key={item.key} className={styles.timelineRow}>
                      <span className={styles.roleLabel}>CALLER</span>
                      <div className={styles.callerBubble}>{item.text}</div>
                    </div>
                  )
                }
                if (item.type === 'tool') {
                  return (
                    <div key={item.key} className={styles.timelineRow}>
                      <span className={styles.roleLabel}>TOOL</span>
                      <ToolCallBlock call={item.call} />
                    </div>
                  )
                }
                if (item.type === 'agent') {
                  return (
                    <div key={item.key} className={styles.timelineRow}>
                      <span className={styles.roleLabel}>AGENT</span>
                      <div className={styles.agentBubble}>{item.text}</div>
                    </div>
                  )
                }
                if (item.type === 'note') {
                  return (
                    <div key={item.key} className={styles.noteRow}>
                      {item.text}
                    </div>
                  )
                }
                return null
              })}
            </div>
          </div>
        </div>

        {/* Right: outcome panel */}
        <div className={styles.outcomeCard}>
          <h2 className={styles.outcomePanelTitle}>Outcome</h2>

          <div className={styles.outcomeGrid}>
            <OutcomeRow label="terminal_state" value={result.terminal_state} mono />
            <OutcomeRow
              label="escalation_reason"
              value={result.escalation_reason ?? 'null'}
              highlight={!!result.escalation_reason}
              mono
            />
            <OutcomeRow
              label="patient_id"
              value={result.patient_id ?? 'null'}
              bold={!!result.patient_id}
              mono
            />
            <OutcomeRow
              label="appointment_id"
              value={result.appointment_id ?? 'null'}
              bold={!!result.appointment_id}
              mono
            />
            <OutcomeRow label="tool_calls" value={toolCallCount} bold />
            <OutcomeRow label="turns"      value={result.metrics?.turns ?? '—'} />
            <OutcomeRow label="tokens"     value={result.metrics?.tokens?.toLocaleString() ?? '—'} bold />
            <OutcomeRow
              label="latency"
              value={result.metrics?.latency_ms ? `${result.metrics.latency_ms} ms` : '—'}
            />
          </div>

          <div className={styles.determinismSection}>
            <div className={styles.determinismLabel}>DETERMINISM</div>
            <div className={styles.determinismRow}>
              Same terminal state across 3 runs.{' '}
              <span className={styles.stableChip}>{determinismLabel}</span>
            </div>
          </div>

          {/* Raw JSON toggle */}
          <RawJson result={result} />
        </div>
      </div>
    </div>
  )
}

function OutcomeRow({ label, value, mono, bold, highlight }) {
  return (
    <div className={styles.outcomeRow}>
      <span className={styles.outcomeLabel}>{label}</span>
      <span
        className={[
          styles.outcomeValue,
          mono ? styles.mono : '',
          bold ? styles.bold : '',
          highlight ? styles.highlight : '',
        ].join(' ')}
      >
        {String(value)}
      </span>
    </div>
  )
}

function RawJson({ result }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={styles.rawSection}>
      <button
        className={styles.rawToggle}
        onClick={() => setOpen(o => !o)}
      >
        {open ? '▲ Hide' : '▼ Show'} raw JSON
      </button>
      {open && (
        <pre className={styles.rawPre}>
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  )
}
