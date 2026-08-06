import { useCallback, useState } from 'react'
import { Pencil, Trash2 } from 'lucide-react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'
import { confirmAction } from '../utils/confirm'
import {
  BTN_PRIMARY,
  BTN_SECONDARY,
  CARD,
  CHECKBOX,
  INPUT,
  LABEL,
  TD,
  TH,
} from '../components/styles'

const LEVELS = ['Level 1', 'Level 2', 'Level 3']
const ENVIRONMENTS = ['Urban', 'Rural']

const BLANK_FORM = {
  hospital_name: '',
  hospital_level: 'Level 1',
  hospital_environment: 'Urban',
  latitude: 0,
  longitude: 0,
  available_beds: 0,
  emergency_equipment: false,
  medical_equipment: false,
  communication_systems: false,
  medical_specialists_count: 0,
  pso_daily_routing_limit: 5,
}

const NUMERIC_FIELDS = [
  'latitude',
  'longitude',
  'available_beds',
  'medical_specialists_count',
  'pso_daily_routing_limit',
]

// Maps an existing hospital record onto the editable form shape.
function formFromHospital(hospital) {
  if (!hospital) return BLANK_FORM
  return {
    hospital_name: hospital.hospital_name ?? '',
    hospital_level: hospital.hospital_level ?? 'Level 1',
    hospital_environment: hospital.hospital_environment ?? 'Urban',
    latitude: hospital.latitude ?? 0,
    longitude: hospital.longitude ?? 0,
    available_beds: hospital.available_beds ?? 0,
    emergency_equipment: Boolean(hospital.emergency_equipment),
    medical_equipment: Boolean(hospital.medical_equipment),
    communication_systems: Boolean(hospital.communication_systems),
    medical_specialists_count: hospital.medical_specialists_count ?? 0,
    pso_daily_routing_limit: hospital.pso_daily_routing_limit ?? 5,
  }
}

// Small labelled checkbox used for the boolean capability flags.
function CheckboxField({ name, label, checked, onChange }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-700">
      <input
        type="checkbox"
        className={CHECKBOX}
        checked={checked}
        onChange={(e) => onChange(name, e.target.checked)}
      />
      {label}
    </label>
  )
}

// Create/edit form shared by both modes; `hospital` being null means "create new".
// The parent remounts this via a `key` so state resets without a syncing effect.
function HospitalFormModal({ hospital, onClose, onSaved }) {
  const [form, setForm] = useState(() => formFromHospital(hospital))
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function setField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.hospital_name.trim()) {
      setError('Hospital name is required.')
      return
    }

    // Number inputs hand back strings; coerce before the payload hits Pydantic.
    const payload = { ...form, hospital_name: form.hospital_name.trim() }
    NUMERIC_FIELDS.forEach((field) => {
      payload[field] = Number(payload[field]) || 0
    })

    setSaving(true)
    setError('')
    try {
      if (hospital) {
        await adminApi.updateHospital(hospital.id, payload)
      } else {
        await adminApi.createHospital(payload)
      }
      // Neither endpoint returns a message like /delete does — build one client-side.
      onSaved(hospital ? 'updated' : 'registered', payload.hospital_name)
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
      wide
      title={hospital ? `Edit ${hospital.hospital_name}` : 'Register new hospital'}
      footer={
        <>
          <button type="button" className={BTN_SECONDARY} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={BTN_PRIMARY} onClick={handleSubmit} disabled={saving}>
            {saving ? 'Saving…' : hospital ? 'Save changes' : 'Create hospital'}
          </button>
        </>
      }
    >
      {error ? <Alert tone="red">{error}</Alert> : null}

      <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="hospital_name">
            Hospital name
          </label>
          <input
            id="hospital_name"
            className={INPUT}
            value={form.hospital_name}
            onChange={(e) => setField('hospital_name', e.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="hospital_level">
            Service level
          </label>
          <select
            id="hospital_level"
            className={INPUT}
            value={form.hospital_level}
            onChange={(e) => setField('hospital_level', e.target.value)}
          >
            {LEVELS.map((level) => (
              <option key={level} value={level}>
                {level}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="hospital_environment">
            Environment
          </label>
          <select
            id="hospital_environment"
            className={INPUT}
            value={form.hospital_environment}
            onChange={(e) => setField('hospital_environment', e.target.value)}
          >
            {ENVIRONMENTS.map((env) => (
              <option key={env} value={env}>
                {env}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className={LABEL} htmlFor="latitude">
            Latitude
          </label>
          <input
            id="latitude"
            type="number"
            step="0.0001"
            className={INPUT}
            value={form.latitude}
            onChange={(e) => setField('latitude', e.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="longitude">
            Longitude
          </label>
          <input
            id="longitude"
            type="number"
            step="0.0001"
            className={INPUT}
            value={form.longitude}
            onChange={(e) => setField('longitude', e.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="available_beds">
            Available beds
          </label>
          <input
            id="available_beds"
            type="number"
            min="0"
            className={INPUT}
            value={form.available_beds}
            onChange={(e) => setField('available_beds', e.target.value)}
          />
        </div>

        <div>
          <label className={LABEL} htmlFor="medical_specialists_count">
            Specialists on staff
          </label>
          <input
            id="medical_specialists_count"
            type="number"
            min="0"
            className={INPUT}
            value={form.medical_specialists_count}
            onChange={(e) => setField('medical_specialists_count', e.target.value)}
          />
        </div>

        <div className="sm:col-span-2">
          <label className={LABEL} htmlFor="pso_daily_routing_limit">
            PSO daily routing limit
          </label>
          <input
            id="pso_daily_routing_limit"
            type="number"
            min="1"
            className={INPUT}
            value={form.pso_daily_routing_limit}
            onChange={(e) => setField('pso_daily_routing_limit', e.target.value)}
          />
          <p className="mt-1 text-xs text-slate-400">
            Maximum referrals the AI engine will route here per day before the facility is penalised.
          </p>
        </div>

        <div className="sm:col-span-2">
          <p className={LABEL}>Capabilities</p>
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <CheckboxField
              name="emergency_equipment"
              label="Emergency equipment"
              checked={form.emergency_equipment}
              onChange={setField}
            />
            <CheckboxField
              name="medical_equipment"
              label="Medical equipment"
              checked={form.medical_equipment}
              onChange={setField}
            />
            <CheckboxField
              name="communication_systems"
              label="Communication systems"
              checked={form.communication_systems}
              onChange={setField}
            />
          </div>
        </div>
      </form>
    </Modal>
  )
}

export default function Hospitals() {
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  // null = closed; { hospital: null } = create mode; { hospital: {...} } = edit mode
  const [formTarget, setFormTarget] = useState(null)

  const fetchHospitals = useCallback(() => adminApi.listHospitals({ search }), [search])
  const { data, loading, error, refresh, setError } = useApiResource(fetchHospitals, [])
  const hospitals = data || []

  function handleFormSaved(action, hospitalName) {
    setNotice(`Hospital "${hospitalName}" was ${action}.`)
    refresh()
  }

  async function handleDelete(hospital) {
    const confirmed = await confirmAction({
      title: `Delete "${hospital.hospital_name}"?`,
      text: 'This cannot be undone. Hospitals with referral history on file cannot be deleted — deactivate their API key instead.',
      confirmText: 'Delete',
    })
    if (!confirmed) return

    setError('')
    setNotice('')
    try {
      const result = await adminApi.deleteHospital(hospital.id)
      setNotice(result.message)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <PageHeader
        title="Hospital Management"
        subtitle="Register facilities and tune the resource parameters the AI routing engine reads."
        actions={
          <>
            <button type="button" className={BTN_SECONDARY} onClick={refresh} disabled={loading}>
              Refresh
            </button>
            <button type="button" className={BTN_PRIMARY} onClick={() => setFormTarget({ hospital: null })}>
              + New hospital
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
        <label className={LABEL} htmlFor="hospitalSearch">
          Search
        </label>
        <input
          id="hospitalSearch"
          className={INPUT}
          placeholder="Filter by hospital name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`${CARD} overflow-hidden`}>
        {loading ? (
          <Spinner label="Loading hospitals…" />
        ) : hospitals.length === 0 ? (
          <EmptyState
            title="No hospitals registered."
            hint="Use “New hospital” to add the first facility."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className={TH}>Hospital</th>
                  <th className={TH}>Level</th>
                  <th className={TH}>Environment</th>
                  <th className={TH}>Beds</th>
                  <th className={TH}>Specialists</th>
                  <th className={TH}>PSO load</th>
                  <th className={TH}>Capabilities</th>
                  <th className={TH}>API key</th>
                  <th className={TH}>Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {hospitals.map((h) => (
                  <tr key={h.id} className="hover:bg-slate-50">
                    <td className={`${TD} font-semibold text-slate-900`}>{h.hospital_name}</td>
                    <td className={TD}>{h.hospital_level || '—'}</td>
                    <td className={TD}>{h.hospital_environment || '—'}</td>
                    <td className={TD}>{h.available_beds ?? 0}</td>
                    <td className={TD}>{h.medical_specialists_count ?? 0}</td>
                    <td className={TD}>
                      {h.referrals_accepted_today ?? 0} / {h.pso_daily_routing_limit ?? 0}
                    </td>
                    <td className={TD}>
                      <div className="flex gap-1">
                        {h.emergency_equipment ? <Badge tone="green">ER</Badge> : null}
                        {h.medical_equipment ? <Badge tone="blue">MED</Badge> : null}
                        {h.communication_systems ? <Badge tone="violet">COMM</Badge> : null}
                        {!h.emergency_equipment && !h.medical_equipment && !h.communication_systems ? (
                          <span className="text-slate-400">—</span>
                        ) : null}
                      </div>
                    </td>
                    <td className={TD}>
                      {h.has_api_key ? <Badge tone="green">Active</Badge> : <Badge tone="amber">None</Badge>}
                    </td>
                    <td className={TD}>
                      <div className="flex gap-1">
                        <button
                          type="button"
                          title="Delete"
                          aria-label="Delete"
                          className="rounded-lg p-2 text-slate-500 transition hover:bg-red-50 hover:text-red-600"
                          onClick={() => handleDelete(h)}
                        >
                          <Trash2 size={16} />
                        </button>
                        <button
                          type="button"
                          title="Edit"
                          aria-label="Edit"
                          className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                          onClick={() => setFormTarget({ hospital: h })}
                        >
                          <Pencil size={16} />
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

      {formTarget ? (
        <HospitalFormModal
          key={formTarget.hospital ? `edit-${formTarget.hospital.id}` : 'create'}
          hospital={formTarget.hospital}
          onClose={() => setFormTarget(null)}
          onSaved={handleFormSaved}
        />
      ) : null}
    </>
  )
}
