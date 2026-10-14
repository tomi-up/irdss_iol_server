import { useCallback, useState } from 'react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'
import {
  BTN_DANGER,
  BTN_SECONDARY,
  CARD,
  INPUT,
  LABEL,
  LINK_ACTION,
  STATUS_TONE,
  TD,
  TH,
} from '../components/styles'
import { formatDateTime } from '../utils/format'

const STATUS_OPTIONS = ['', 'PENDING', 'SEEN', 'ACCEPTED', 'REDIRECTED', 'CANCELLED']
const PAGE_SIZE = 25
const EMPTY_RESULT = { items: [], total: 0, page: 1, page_size: PAGE_SIZE }

// Read-only detail drawer showing a referral's full per-hospital response timeline.
// Mounted only while a row is selected, so `referralId` is always present.
function ReferralDetailModal({ referralId, onClose, onCancelled }) {
  const fetchDetail = useCallback(() => adminApi.getReferral(referralId), [referralId])
  const { data: detail, loading, error, setError } = useApiResource(fetchDetail)
  const [cancelling, setCancelling] = useState(false)

  async function handleForceCancel() {
    if (!window.confirm(`Force-cancel referral ${referralId}? This closes it for every hospital.`)) {
      return
    }

    setCancelling(true)
    setError('')
    try {
      await adminApi.cancelReferral(referralId)
      onCancelled()
      onClose()
    } catch (err) {
      setError(err.message)
      setCancelling(false)
    }
  }

  const canCancel = detail && !['CANCELLED', 'ACCEPTED'].includes(detail.status)

  return (
    <Modal
      open
      onClose={onClose}
      wide
      title={`Referral ${referralId}`}
      footer={
        <>
          {canCancel ? (
            <button type="button" className={BTN_DANGER} onClick={handleForceCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling…' : 'Force-cancel referral'}
            </button>
          ) : null}
          <button type="button" className={BTN_SECONDARY} onClick={onClose}>
            Close
          </button>
        </>
      }
    >
      {error ? <Alert tone="red">{error}</Alert> : null}
      {loading ? <Spinner /> : null}

      {detail ? (
        <>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            <div>
              <dt className={LABEL}>Status</dt>
              <dd>
                <Badge tone={STATUS_TONE[detail.status] || 'slate'}>{detail.status}</Badge>
              </dd>
            </div>
            <div>
              <dt className={LABEL}>Patient</dt>
              <dd className="font-mono text-slate-800">{detail.patient_id}</dd>
            </div>
            <div>
              <dt className={LABEL}>Age / Gender</dt>
              <dd className="text-slate-800">
                {detail.patient_age ?? '—'} / {detail.patient_gender || '—'}
              </dd>
            </div>
            <div>
              <dt className={LABEL}>Referring facility</dt>
              <dd className="text-slate-800">{detail.referring_facility}</dd>
            </div>
            <div>
              <dt className={LABEL}>Receiving facility</dt>
              <dd className="text-slate-800">{detail.receiving_facility || 'Not yet selected'}</dd>
            </div>
            <div>
              <dt className={LABEL}>Severity</dt>
              <dd className="text-slate-800">
                {detail.disease_severity}
                {detail.patient_severity !== null ? ` (triage ${detail.patient_severity})` : ''}
              </dd>
            </div>
            <div>
              <dt className={LABEL}>Created</dt>
              <dd className="text-slate-800">{formatDateTime(detail.created_at)}</dd>
            </div>
            <div>
              <dt className={LABEL}>First seen</dt>
              <dd className="text-slate-800">{formatDateTime(detail.seen_at)}</dd>
            </div>
            <div>
              <dt className={LABEL}>Evaluated</dt>
              <dd className="text-slate-800">{formatDateTime(detail.evaluated_at)}</dd>
            </div>
          </dl>

          <div className="mt-4">
            <p className={LABEL}>Clinical reason</p>
            <p className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
              {detail.clinical_reason || 'No reason provided.'}
            </p>
          </div>

          <div className="mt-6">
            <p className="mb-2 text-sm font-semibold text-slate-900">
              Broadcast timeline ({detail.responses.length} facilities)
            </p>
            {detail.responses.length === 0 ? (
              <p className="text-sm text-slate-400">No hospitals were broadcast to.</p>
            ) : (
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className={TH}>Hospital</th>
                      <th className={TH}>Decision</th>
                      <th className={TH}>Seen at</th>
                      <th className={TH}>Responded at</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 bg-white">
                    {detail.responses.map((row) => (
                      <tr key={`${row.hospital_name}-${row.responded_at}`}>
                        <td className={TD}>{row.hospital_name}</td>
                        <td className={TD}>
                          <Badge tone={STATUS_TONE[row.response_status] || 'slate'}>
                            {row.response_status}
                          </Badge>
                        </td>
                        <td className={TD}>{formatDateTime(row.seen_at)}</td>
                        <td className={TD}>{formatDateTime(row.responded_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}
    </Modal>
  )
}

export default function Referrals() {
  const [filters, setFilters] = useState({ status: '', facility: '', search: '' })
  const [page, setPage] = useState(1)
  const [selectedId, setSelectedId] = useState(null)

  const fetchReferrals = useCallback(
    () =>
      adminApi.listReferrals({
        status: filters.status,
        facility: filters.facility,
        search: filters.search,
        page,
        page_size: PAGE_SIZE,
      }),
    [filters, page],
  )

  const { data, loading, error, refresh } = useApiResource(fetchReferrals, EMPTY_RESULT)
  const result = data || EMPTY_RESULT

  // Any filter change resets pagination, otherwise page 3 of a 1-page result renders empty.
  function updateFilter(name, value) {
    setPage(1)
    setFilters((prev) => ({ ...prev, [name]: value }))
  }

  const totalPages = Math.max(1, Math.ceil(result.total / PAGE_SIZE))

  return (
    <>
      <PageHeader
        title="All Referrals"
        subtitle="Every referral in the network, across all facilities."
        actions={
          <button type="button" className={BTN_SECONDARY} onClick={refresh} disabled={loading}>
            Refresh
          </button>
        }
      />

      {error ? (
        <Alert tone="red" title="Could not load referrals">
          {error}
        </Alert>
      ) : null}

      <div className={`${CARD} mb-4 grid gap-3 p-4 sm:grid-cols-3`}>
        <div>
          <label className={LABEL} htmlFor="filterStatus">
            Status
          </label>
          <select
            id="filterStatus"
            className={INPUT}
            value={filters.status}
            onChange={(e) => updateFilter('status', e.target.value)}
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt || 'All statuses'}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={LABEL} htmlFor="filterFacility">
            Facility
          </label>
          <input
            id="filterFacility"
            className={INPUT}
            placeholder="Referring or receiving hospital"
            value={filters.facility}
            onChange={(e) => updateFilter('facility', e.target.value)}
          />
        </div>
        <div>
          <label className={LABEL} htmlFor="filterSearch">
            Search
          </label>
          <input
            id="filterSearch"
            className={INPUT}
            placeholder="Referral ID or clinical reason"
            value={filters.search}
            onChange={(e) => updateFilter('search', e.target.value)}
          />
        </div>
      </div>

      <div className={`${CARD} overflow-hidden`}>
        {loading ? (
          <Spinner label="Loading referrals…" />
        ) : result.items.length === 0 ? (
          <EmptyState title="No referrals match these filters." hint="Try clearing the search box." />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className={TH}>Referral ID</th>
                  <th className={TH}>Patient</th>
                  <th className={TH}>Referring</th>
                  <th className={TH}>Receiving</th>
                  <th className={TH}>Severity</th>
                  <th className={TH}>Status</th>
                  <th className={TH}>Accepts</th>
                  <th className={TH}>Created</th>
                  <th className={TH} />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {result.items.map((row) => (
                  <tr key={row.referral_id} className="hover:bg-slate-50">
                    <td className={`${TD} font-mono text-xs`}>{row.referral_id}</td>
                    <td className={`${TD} font-mono text-xs`}>{row.patient_id}</td>
                    <td className={TD}>{row.referring_facility}</td>
                    <td className={TD}>
                      {row.receiving_facility || <span className="text-slate-400">—</span>}
                    </td>
                    <td className={TD}>{row.disease_severity}</td>
                    <td className={TD}>
                      <Badge tone={STATUS_TONE[row.status] || 'slate'}>{row.status}</Badge>
                    </td>
                    <td className={TD}>
                      {row.accepted_count} / {row.broadcast_count}
                    </td>
                    <td className={TD}>{formatDateTime(row.created_at)}</td>
                    <td className={TD}>
                      <button
                        type="button"
                        className={LINK_ACTION}
                        onClick={() => setSelectedId(row.referral_id)}
                      >
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
          <p className="text-sm text-slate-500">
            {result.total} referral{result.total === 1 ? '' : 's'} · page {result.page} of {totalPages}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className={BTN_SECONDARY}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1 || loading}
            >
              Previous
            </button>
            <button
              type="button"
              className={BTN_SECONDARY}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || loading}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {selectedId ? (
        <ReferralDetailModal
          referralId={selectedId}
          onClose={() => setSelectedId(null)}
          onCancelled={refresh}
        />
      ) : null}
    </>
  )
}
