import { useCallback, useEffect, useState } from 'react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'
import {
  BTN_PRIMARY,
  BTN_SECONDARY,
  CARD,
  INPUT,
  LABEL,
  LINK_ACTION,
  LINK_DANGER,
  LINK_MUTED,
  TD,
  TH,
} from '../components/styles'
import { formatDateTime } from '../utils/format'
import { confirmAction } from '../utils/confirm'

// One-time reveal dialog. The plaintext secret exists nowhere else after this closes.
function IssuedKeyModal({ issued, onClose }) {
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(issued.raw_key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="API key issued"
      footer={
        <>
          <button type="button" className={BTN_SECONDARY} onClick={handleCopy}>
            {copied ? 'Copied!' : 'Copy key'}
          </button>
          <button type="button" className={BTN_PRIMARY} onClick={onClose}>
            Done
          </button>
        </>
      }
    >
      <Alert tone="amber" title="Copy this key now">
        The gateway stores only a SHA-256 hash. Once you close this dialog the plaintext key cannot be
        recovered — you would have to rotate the key to issue a new one.
      </Alert>

      <p className={LABEL}>Owning hospital</p>
      <p className="mb-4 text-sm font-semibold text-slate-900">{issued.key.hospital_name}</p>

      <p className={LABEL}>Plaintext key</p>
      <code className="block break-all rounded-lg bg-slate-900 px-3 py-3 font-mono text-sm text-emerald-300">
        {issued.raw_key}
      </code>
    </Modal>
  )
}

// Mint form. Hospitals are picked from the registry via search, so a key can never be
// issued for a name that doesn't exist there, or duplicated for one that already has one.
function CreateKeyModal({ onClose, onIssued }) {
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState(null)
  const [options, setOptions] = useState([])
  const [searching, setSearching] = useState(false)
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const term = query.trim()
    if (!term || selected) {
      return undefined
    }

    let cancelled = false
    const timer = setTimeout(() => {
      setSearching(true)
      adminApi
        .listHospitals({ search: term })
        .then((data) => {
          if (cancelled) return
          setOptions(data)
          setSearching(false)
        })
        .catch(() => {
          if (cancelled) return
          setOptions([])
          setSearching(false)
        })
    }, 250)

    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, selected])

  function handleQueryChange(value) {
    setQuery(value)
    setSelected(null)
    setOpen(true)
  }

  function handlePick(hospital) {
    if (hospital.has_api_key) return
    setSelected(hospital)
    setQuery(hospital.hospital_name)
    setOpen(false)
  }

  async function handleSubmit() {
    if (!selected) {
      setError("Search for and select a hospital that doesn't already have an active key.")
      return
    }

    setSaving(true)
    setError('')
    try {
      const issued = await adminApi.createApiKey({ hospital_name: selected.hospital_name })
      onIssued(issued)
      onClose()
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Issue new API key"
      footer={
        <>
          <button type="button" className={BTN_SECONDARY} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={BTN_PRIMARY} onClick={handleSubmit} disabled={saving || !selected}>
            {saving ? 'Issuing…' : 'Issue key'}
          </button>
        </>
      }
    >
      {error ? <Alert tone="red">{error}</Alert> : null}

      <label className={LABEL} htmlFor="keyHospitalSearch">
        Hospital
      </label>
      <div className="relative">
        <input
          id="keyHospitalSearch"
          className={INPUT}
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          placeholder="Search registered hospitals…"
          autoComplete="off"
        />

        {open && query.trim() && !selected ? (
          <div className="absolute z-10 mt-1 max-h-56 w-full overflow-y-auto rounded-xl border border-slate-200 bg-white shadow-lg">
            {searching ? (
              <p className="px-3 py-2 text-sm text-slate-400">Searching…</p>
            ) : options.length === 0 ? (
              <p className="px-3 py-2 text-sm text-slate-400">
                No hospital found. Register it under Hospitals first.
              </p>
            ) : (
              options.map((hospital) => (
                <button
                  key={hospital.id}
                  type="button"
                  disabled={hospital.has_api_key}
                  onMouseDown={(e) => {
                    e.preventDefault()
                    handlePick(hospital)
                  }}
                  className={`flex w-full items-center justify-between px-3 py-2 text-left text-sm ${
                    hospital.has_api_key
                      ? 'cursor-not-allowed text-slate-300'
                      : 'text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  <span>{hospital.hospital_name}</span>
                  {hospital.has_api_key ? (
                    <span className="text-xs font-semibold text-slate-400">Already has a key</span>
                  ) : null}
                </button>
              ))
            )}
          </div>
        ) : null}
      </div>

      <p className="mt-2 text-xs text-slate-400">
        Only hospitals already registered under Hospitals, with no active key, can be selected —
        this rules out typos and duplicate credentials.
      </p>
    </Modal>
  )
}

export default function ApiKeys() {
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [issued, setIssued] = useState(null)

  const fetchKeys = useCallback(() => adminApi.listApiKeys({ search }), [search])
  const { data, loading, error, refresh, setError } = useApiResource(fetchKeys, [])
  const keys = data || []

  async function handleToggle(record) {
    if (record.is_active) {
      const confirmed = await confirmAction({
        title: `Deactivate the key for "${record.hospital_name}"?`,
        text: 'Their gateway requests will start failing immediately. You can reactivate it later without reissuing a new key.',
        confirmText: 'Deactivate',
      })
      if (!confirmed) return
    }

    setError('')
    setNotice('')
    try {
      await adminApi.updateApiKey(record.id, { is_active: !record.is_active })
      setNotice(
        `Key for "${record.hospital_name}" is now ${record.is_active ? 'deactivated' : 'active'}.`,
      )
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRotate(record) {
    const confirmed = await confirmAction({
      title: `Rotate the key for "${record.hospital_name}"?`,
      text: 'Their current key stops working immediately and their HIS must be reconfigured.',
      confirmText: 'Rotate key',
    })
    if (!confirmed) return

    setError('')
    setNotice('')
    try {
      setIssued(await adminApi.rotateApiKey(record.id))
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(record) {
    const confirmed = await confirmAction({
      title: `Permanently revoke the key for "${record.hospital_name}"?`,
      text: 'This cannot be undone. To take a node offline temporarily, deactivate it instead.',
      confirmText: 'Revoke',
    })
    if (!confirmed) return

    setError('')
    setNotice('')
    try {
      const result = await adminApi.deleteApiKey(record.id)
      setNotice(result.message)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <PageHeader
        title="API Key Management"
        subtitle="Issue, rotate, and revoke the credentials each hospital node uses to reach the gateway."
        actions={
          <>
            <button type="button" className={BTN_SECONDARY} onClick={refresh} disabled={loading}>
              Refresh
            </button>
            <button type="button" className={BTN_PRIMARY} onClick={() => setCreateOpen(true)}>
              + Issue key
            </button>
          </>
        }
      />

      {error ? (
        <Alert tone="red" title="Action failed" onDismiss={() => setError('')}>
          {error}
        </Alert>
      ) : null}
      {notice ? (
        <Alert tone="green" onDismiss={() => setNotice('')}>
          {notice}
        </Alert>
      ) : null}

      <div className={`${CARD} mb-4 p-4`}>
        <label className={LABEL} htmlFor="keySearch">
          Search
        </label>
        <input
          id="keySearch"
          className={INPUT}
          placeholder="Filter by hospital name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`${CARD} overflow-hidden`}>
        {loading ? (
          <Spinner label="Loading API keys…" />
        ) : keys.length === 0 ? (
          <EmptyState title="No API keys issued." hint="Use “Issue key” to onboard a hospital node." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className={TH}>ID</th>
                  <th className={TH}>Hospital</th>
                  <th className={TH}>API Key</th>
                  <th className={TH}>Status</th>
                  <th className={TH}>Issued</th>
                  <th className={TH}>Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {keys.map((record) => (
                  <tr key={record.id} className="hover:bg-slate-50">
                    <td className={TD}>{record.id}</td>
                    <td className={`${TD} font-semibold text-slate-900`}>{record.hospital_name}</td>
                    <td className={`${TD} font-mono text-xs text-slate-500`}>{record.api_key_display}</td>
                    <td className={TD}>
                      {record.is_active ? (
                        <Badge tone="green">Active</Badge>
                      ) : (
                        <Badge tone="slate">Disabled</Badge>
                      )}
                    </td>
                    <td className={TD}>{formatDateTime(record.created_at)}</td>
                    <td className={TD}>
                      <div className="flex gap-3">
                        <button type="button" className={LINK_MUTED} onClick={() => handleToggle(record)}>
                          {record.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                        <button type="button" className={LINK_ACTION} onClick={() => handleRotate(record)}>
                          Rotate
                        </button>
                        <button type="button" className={LINK_DANGER} onClick={() => handleDelete(record)}>
                          Revoke
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {createOpen ? (
        <CreateKeyModal onClose={() => setCreateOpen(false)} onIssued={setIssued} />
      ) : null}
      {issued ? <IssuedKeyModal issued={issued} onClose={() => setIssued(null)} /> : null}
    </>
  )
}
