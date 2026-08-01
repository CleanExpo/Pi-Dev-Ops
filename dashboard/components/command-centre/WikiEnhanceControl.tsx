'use client'

import { useState } from 'react'
import { BookOpenCheck, RefreshCw } from 'lucide-react'
import styles from './command-deck.module.css'

interface WikiEnhanceJob {
  id?: string
  status?: string
  updated_at?: string
}

interface EnqueueResponse {
  job?: WikiEnhanceJob
  deduped?: boolean
  error?: string
}

interface StatusResponse {
  job?: WikiEnhanceJob | null
  events?: Array<{ event_type: string; detail: string }>
  error?: string
}

async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const data = (await res.json()) as { error?: string }
    if (typeof data.error === 'string' && data.error) return data.error
  } catch {
    // fall through to HTTP status
  }
  return `${fallback} (HTTP ${res.status})`
}

export function WikiEnhanceControl() {
  const [status, setStatus] = useState<string | null>(null)
  const [detail, setDetail] = useState<string | null>(null)
  const [busy, setBusy] = useState<'run' | 'refresh' | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function runEnhancement() {
    if (busy) return
    setBusy('run')
    setError(null)
    try {
      const res = await fetch('/api/command-centre/lanes/wiki/enhance', {
        method: 'POST',
        cache: 'no-store',
        credentials: 'include',
      })
      if (!res.ok) {
        setError(await readError(res, 'Could not queue wiki enhancement'))
        return
      }
      const data = (await res.json()) as EnqueueResponse
      setStatus(data.job?.status ?? 'queued')
      setDetail(data.deduped ? 'run already in flight' : 'queued for the Mac runner')
    } catch {
      setError('Network error')
    } finally {
      setBusy(null)
    }
  }

  async function refreshStatus() {
    if (busy) return
    setBusy('refresh')
    setError(null)
    try {
      const res = await fetch('/api/command-centre/lanes/wiki/enhance', {
        cache: 'no-store',
        credentials: 'include',
      })
      if (!res.ok) {
        setError(await readError(res, 'Could not read wiki enhancement status'))
        return
      }
      const data = (await res.json()) as StatusResponse
      if (!data.job) {
        setStatus(null)
        setDetail('no runs yet')
        return
      }
      setStatus(data.job.status ?? null)
      setDetail(data.events?.[0]?.detail ?? null)
    } catch {
      setError('Network error')
    } finally {
      setBusy(null)
    }
  }

  const disabled = busy !== null

  return (
    <div className={styles.integrationActions} aria-live="polite">
      <button
        type="button"
        className={styles.iconCommand}
        onClick={refreshStatus}
        disabled={disabled}
        aria-label="Refresh wiki enhancement status"
        title="Refresh wiki enhancement status"
      >
        <RefreshCw size={14} aria-hidden="true" />
      </button>
      <button
        type="button"
        className={styles.queueCommand}
        onClick={runEnhancement}
        disabled={disabled}
        aria-label="Run a Wiki Knowledge Base enhancement"
      >
        <BookOpenCheck size={14} aria-hidden="true" />
        <span>{busy === 'run' ? 'Queueing' : 'Enhance Wiki KB'}</span>
      </button>
      <span className={styles.integrationActionStatus}>
        {error ? error : status ? `${status}${detail ? ` — ${detail}` : ''}` : detail ?? 'Ready'}
      </span>
    </div>
  )
}
