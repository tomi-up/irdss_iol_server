import { useCallback, useState } from 'react'
import { KeyRound, Check, Copy, UserCheck, ShieldAlert } from 'lucide-react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'
import {
  BTN_PRIMARY,
  BTN_SECONDARY,
  CARD,
  INPUT,
  LABEL,
  TD,
  TH,
} from '../components/styles'

// Credentials Issuance & Reset Modal
function CredentialsModal({ facility, onClose, onIssued }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [issuing, setIssuing] = useState(false)
  const [error, setError] = useState('')
  const [issuedResult, setIssuedResult] = useState(null)
  const [copied, setCopied] = useState(false)

  async function handleIssue(e) {
    e.preventDefault()
    setIssuing(true)
    setError('')
    try {
      const payload = {}
      if (username.trim()) payload.username = username.trim()
      if (password.trim()) payload.password = password.trim()

      const res = await adminApi.issueFacilityCredentials(facility.facility_id, payload)
      setIssuedResult(res)
      if (onIssued) onIssued()
    } catch (err) {
      setError(err.message)
    } finally {
      setIssuing(false)
    }
  }

  function handleCopy() {
    if (!issuedResult) return
    const text = `Facility: ${issuedResult.facility_name}\nUsername: ${issuedResult.username}\nPassword: ${issuedResult.raw_password}\nRole: ${issuedResult.role}`
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={facility.has_credentials ? `Reset Credentials: ${facility.facility_name}` : `Issue Credentials: ${facility.facility_name}`}
      footer={
        issuedResult ? (
          <button type="button" className={BTN_PRIMARY} onClick={onClose}>
            Done & Close
          </button>
        ) : (
          <>
            <button type="button" className={BTN_SECONDARY} onClick={onClose}>
              Cancel
            </button>
            <button type="button" className={BTN_PRIMARY} onClick={handleIssue} disabled={issuing}>
              {issuing ? 'Processing…' : facility.has_credentials ? 'Reset Password' : 'Issue Credentials'}
            </button>
          </>
        )
      }
    >
      {error ? <Alert tone="red">{error}</Alert> : null}

      {issuedResult ? (
        <div className="space-y-4">
          <Alert tone="green" title="Credentials Issued Successfully!">
            These login credentials delegate facility admin access to the central IRDSS network.
          </Alert>

          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <p className="font-semibold text-amber-950">⚠️ One-Time Password Reveal</p>
            <p className="mt-1 text-xs">
              Copy the plaintext password below now. The server hashes it immediately and will never display it again.
            </p>

            <div className="mt-3 space-y-1.5 font-mono text-xs text-slate-800 bg-white p-3 rounded-lg border border-amber-200">
              <div><span className="text-slate-400">Facility:</span> {issuedResult.facility_name}</div>
              <div><span className="text-slate-400">Username:</span> <strong>{issuedResult.username}</strong></div>
              <div><span className="text-slate-400">Password:</span> <strong>{issuedResult.raw_password}</strong></div>
              <div><span className="text-slate-400">Role:</span> {issuedResult.role}</div>
            </div>

            <button
              type="button"
              onClick={handleCopy}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 transition"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? 'Copied to Clipboard!' : 'Copy Credentials'}
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={handleIssue} className="space-y-4">
          <p className="text-xs text-slate-500">
            Leave username or password blank to automatically generate secure defaults for this facility.
          </p>
          <div>
            <label className={LABEL} htmlFor="cred_username">Username (Optional)</label>
            <input
              id="cred_username"
              className={INPUT}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={facility.username || 'e.g. stjude_admin'}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="cred_password">Password (Optional)</label>
            <input
              id="cred_password"
              type="password"
              className={INPUT}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Leave blank to auto-generate hex password"
            />
          </div>
        </form>
      )}
    </Modal>
  )
}

export default function Credentials() {
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  const [targetFacility, setTargetFacility] = useState(null)

  const fetchCredentials = useCallback(() => adminApi.listCredentials({ search }), [search])
  const { data, loading, error, refresh, setError } = useApiResource(fetchCredentials, [])
  const items = data || []

  function formatDate(iso) {
    if (!iso) return 'Never'
    try {
      const d = new Date(iso)
      return d.toLocaleString()
    } catch {
      return iso
    }
  }

  return (
    <>
      <PageHeader
        title="Facility Credentials Management"
        subtitle="Issue and manage delegated administrator login identities for all registered health facilities."
        actions={
          <button type="button" className={BTN_SECONDARY} onClick={refresh} disabled={loading}>
            Refresh
          </button>
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
        <label className={LABEL} htmlFor="credSearch">
          Search Facility Credentials
        </label>
        <input
          id="credSearch"
          className={INPUT}
          placeholder="Filter by facility name, code, or username"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`${CARD} overflow-hidden`}>
        {loading ? (
          <Spinner label="Loading facility credentials…" />
        ) : items.length === 0 ? (
          <EmptyState
            title="No facility records found."
            hint="Register health facilities under the Health Facility Registry first."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className={TH}>Code</th>
                  <th className={TH}>Facility Name</th>
                  <th className={TH}>Tier / Type</th>
                  <th className={TH}>Username</th>
                  <th className={TH}>Role</th>
                  <th className={TH}>Account Status</th>
                  <th className={TH}>System Cryptographic Identity</th>
                  <th className={TH}>Last Login</th>
                  <th className={TH}>Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {items.map((item) => (
                  <tr key={item.facility_id} className="hover:bg-slate-50">
                    <td className={`${TD} font-mono text-xs text-slate-500`}>{item.facility_code}</td>
                    <td className={`${TD} font-semibold text-slate-900`}>{item.facility_name}</td>
                    <td className={TD}>{item.facility_type || '—'}</td>
                    <td className={`${TD} font-mono text-xs font-semibold`}>
                      {item.username ? (
                        <span className="text-slate-800">{item.username}</span>
                      ) : (
                        <span className="text-slate-400 font-normal italic">Not Issued</span>
                      )}
                    </td>
                    <td className={TD}>{item.role || '—'}</td>
                    <td className={TD}>
                      {item.has_credentials ? (
                        <Badge tone="green">
                          <UserCheck size={12} className="mr-1 inline" /> Active
                        </Badge>
                      ) : (
                        <Badge tone="amber">
                          <ShieldAlert size={12} className="mr-1 inline" /> Not Issued
                        </Badge>
                      )}
                    </td>
                    <td className={TD}>
                      <Badge tone="blue">
                        <KeyRound size={12} className="mr-1 inline" /> RSA-2048 Active
                      </Badge>
                    </td>
                    <td className={`${TD} text-xs text-slate-500`}>{formatDate(item.last_login)}</td>

                    <td className={TD}>
                      <button
                        type="button"
                        className={item.has_credentials ? BTN_SECONDARY : BTN_PRIMARY}
                        onClick={() => setTargetFacility(item)}
                      >
                        <KeyRound size={14} className="mr-1.5 inline" />
                        {item.has_credentials ? 'Reset Credentials' : 'Issue Credentials'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {targetFacility ? (
        <CredentialsModal
          facility={targetFacility}
          onClose={() => setTargetFacility(null)}
          onIssued={() => {
            setNotice(`Credentials successfully updated for "${targetFacility.facility_name}".`)
            refresh()
          }}
        />
      ) : null}
    </>
  )
}
