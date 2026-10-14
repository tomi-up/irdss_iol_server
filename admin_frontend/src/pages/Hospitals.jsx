import { useCallback, useEffect, useState } from 'react'
import { Pencil, Trash2, FileText } from 'lucide-react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, Modal, PageHeader, Spinner } from '../components/ui'
import { confirmAction } from '../utils/confirm'
import {
  BTN_PRIMARY,
  BTN_SECONDARY,
  CARD,
  INPUT,
  LABEL,
  TD,
  TH,
} from '../components/styles'

const FACILITY_TYPES = [
  'BHS',
  'RHU',
  'Level 1 Hospital',
  'Level 2 Hospital',
  'Level 3 Hospital',
]
const OWNERSHIP_OPTIONS = ['Government', 'Private']
const LTO_STATUS_OPTIONS = ['Active', 'Expired', 'Suspended', 'Pending']
const FACILITY_STATUS_OPTIONS = ['Active', 'Inactive']

const LEGACY_FACILITY_TYPE_MAP = {
  'Hospital Level 1': 'Level 1 Hospital',
  'Hospital Level 2': 'Level 2 Hospital',
  'Hospital Level 3': 'Level 3 Hospital',
}

function normalizeFacilityType(value) {
  return LEGACY_FACILITY_TYPE_MAP[value] ?? value ?? ''
}

const BLANK_FORM = {
  facility_name: '',
  facility_type: 'Level 1 Hospital',
  ownership: 'Government',
  facility_head: '',
  region: 'Region XI',
  province: 'Davao del Sur',
  municipality: 'Davao City',
  barangay: '',
  address: '',
  latitude: 0,
  longitude: 0,
  contact_number: '',
  email: '',
  lto_number: '',
  lto_type: '',
  lto_issue_date: '',
  lto_expiration_date: '',
  lto_status: 'Active',
  facility_status: 'Active',
  pso_daily_routing_limit: 5,
}

function formFromFacility(facility) {
  if (!facility) return BLANK_FORM
  return {
    facility_name: facility.facility_name ?? '',
    facility_type: normalizeFacilityType(facility.facility_type) || 'Level 1 Hospital',
    ownership: facility.ownership ?? 'Government',
    facility_head: facility.facility_head ?? '',
    region: facility.region ?? 'Region XI',
    province: facility.province ?? 'Davao del Sur',
    municipality: facility.municipality ?? 'Davao City',
    barangay: facility.barangay ?? '',
    address: facility.address ?? '',
    latitude: facility.latitude ?? 0,
    longitude: facility.longitude ?? 0,
    contact_number: facility.contact_number ?? '',
    email: facility.email ?? '',
    lto_number: facility.lto_number ?? '',
    lto_type: normalizeFacilityType(facility.lto_type),
    lto_issue_date: facility.lto_issue_date ?? '',
    lto_expiration_date: facility.lto_expiration_date ?? '',
    lto_status: facility.lto_status ?? 'Active',
    facility_status: facility.facility_status ?? 'Active',
    pso_daily_routing_limit: facility.pso_daily_routing_limit ?? 5,
  }
}

// PSGC-backed Region -> Province -> City/Municipality -> Barangay cascade, mirroring
// the mock_hospitals HIS location selector. Also runs each cascade step's resolved
// address through Nominatim to auto-fill Latitude/Longitude, since facility admins
// otherwise have no easy way to know a barangay's coordinates offhand.
function usePsgcLocationCascade(form, setField) {
  const [regions, setRegions] = useState([])
  const [provinces, setProvinces] = useState([])
  const [cities, setCities] = useState([])
  const [barangays, setBarangays] = useState([])
  const [codes, setCodes] = useState({ region: null, province: null, city: null })
  const [geocoding, setGeocoding] = useState(false)

  // Load regions once, then try to resolve the facility's existing text values (edit
  // mode) to PSGC codes so the cascade starts pre-populated instead of blank.
  useEffect(() => {
    let cancelled = false
    fetch('https://psgc.cloud/api/regions')
      .then((r) => r.json())
      .then((data) => {
        if (cancelled || !Array.isArray(data)) return
        setRegions(data)
        // "Region XI" (the plain default/legacy text) won't exact-match the PSGC API's
        // full name (e.g. "Region XI (Davao Region)") -- fall back to the known code.
        const match = data.find((r) => r.name === form.region) || data.find((r) => r.code === '1100000000')
        if (match) setCodes((c) => ({ ...c, region: match.code }))
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!codes.region) return
    let cancelled = false
    fetch(`https://psgc.cloud/api/regions/${codes.region}/provinces`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled || !Array.isArray(data)) return
        setProvinces(data)
        const match = data.find((p) => p.name === form.province)
        if (match) setCodes((c) => ({ ...c, province: match.code }))
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.region])

  useEffect(() => {
    if (!codes.province) return
    let cancelled = false
    fetch(`https://psgc.cloud/api/provinces/${codes.province}/cities-municipalities`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled || !Array.isArray(data)) return
        setCities(data)
        const match = data.find((c) => c.name === form.municipality)
        if (match) setCodes((c) => ({ ...c, city: match.code }))
      })
      .catch(() => {})
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codes.province])

  useEffect(() => {
    if (!codes.city) return
    let cancelled = false
    fetch(`https://psgc.cloud/api/cities-municipalities/${codes.city}/barangays`)
      .then((r) => r.json())
      .then((data) => { if (!cancelled && Array.isArray(data)) setBarangays(data) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [codes.city])

  async function runGeocode(barangayName, cityName, provinceName) {
    if (!cityName) return
    const query = [barangayName, cityName, provinceName, 'Philippines'].filter(Boolean).join(', ')
    setGeocoding(true)
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&limit=1&q=${encodeURIComponent(query)}`
      )
      const results = await res.json()
      if (Array.isArray(results) && results.length > 0) {
        setField('latitude', parseFloat(results[0].lat))
        setField('longitude', parseFloat(results[0].lon))
      }
    } catch {
      // best-effort only -- leave whatever lat/lng was already in the form untouched
    } finally {
      setGeocoding(false)
    }
  }

  function selectRegion(code) {
    const match = regions.find((r) => r.code === code)
    setCodes({ region: code || null, province: null, city: null })
    setProvinces([])
    setCities([])
    setBarangays([])
    setField('region', match?.name || '')
    setField('province', '')
    setField('municipality', '')
    setField('barangay', '')
  }

  function selectProvince(code) {
    const match = provinces.find((p) => p.code === code)
    setCodes((c) => ({ ...c, province: code || null, city: null }))
    setCities([])
    setBarangays([])
    setField('province', match?.name || '')
    setField('municipality', '')
    setField('barangay', '')
  }

  function selectCity(code) {
    const match = cities.find((c) => c.code === code)
    setCodes((c) => ({ ...c, city: code || null }))
    setBarangays([])
    setField('municipality', match?.name || '')
    setField('barangay', '')
    if (match) runGeocode('', match.name, form.province)
  }

  function selectBarangay(name) {
    setField('barangay', name)
    runGeocode(name, form.municipality, form.province)
  }

  return { regions, provinces, cities, barangays, codes, selectRegion, selectProvince, selectCity, selectBarangay, geocoding }
}

// 5-Section Grouped Facility Form Modal
function FacilityFormModal({ facility, onClose, onSaved }) {
  const [form, setForm] = useState(() => formFromFacility(facility))
  const [ltoFile, setLtoFile] = useState(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  function setField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  const location = usePsgcLocationCascade(form, setField)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!form.facility_name.trim()) {
      setError('Facility name is required.')
      return
    }

    setSaving(true)
    setError('')
    try {
      if (facility) {
        // Edit mode: send a true partial PATCH so untouched values remain exactly
        // as stored, including optional fields that the user does not want to edit.
        const normalizedForm = {
          ...form,
          facility_name: form.facility_name.trim(),
          latitude: Number(form.latitude) || 0,
          longitude: Number(form.longitude) || 0,
          pso_daily_routing_limit: Number(form.pso_daily_routing_limit) || 5,
        }
        const original = formFromFacility(facility)
        const normalizedOriginal = {
          ...original,
          facility_name: original.facility_name.trim(),
          latitude: Number(original.latitude) || 0,
          longitude: Number(original.longitude) || 0,
          pso_daily_routing_limit: Number(original.pso_daily_routing_limit) || 5,
        }
        const payload = Object.fromEntries(
          Object.entries(normalizedForm).filter(([key, value]) => value !== normalizedOriginal[key])
        )

        if (Object.keys(payload).length === 0) {
          onClose()
          return
        }
        await adminApi.updateFacility(facility.id, payload)
      } else {
        // Create mode (Multipart FormData for optional file upload)
        const formData = new FormData()
        Object.entries(form).forEach(([key, value]) => {
          if (value !== undefined && value !== null) {
            formData.append(key, value)
          }
        })
        if (ltoFile) {
          formData.append('lto_file', ltoFile)
        }
        await adminApi.createFacility(formData)
      }
      onSaved(facility ? 'updated' : 'registered', form.facility_name)
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
      title={facility ? `Edit ${facility.facility_name}` : 'Register New Health Facility'}
      footer={
        <>
          <button type="button" className={BTN_SECONDARY} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={BTN_PRIMARY} onClick={handleSubmit} disabled={saving}>
            {saving ? 'Saving…' : facility ? 'Save Changes' : 'Create Facility'}
          </button>
        </>
      }
    >
      {error ? <Alert tone="red">{error}</Alert> : null}

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* SECTION 1: FACILITY INFORMATION */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
            1. Facility Information
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL} htmlFor="facility_name">Facility Name *</label>
              <input
                id="facility_name"
                className={INPUT}
                value={form.facility_name}
                onChange={(e) => setField('facility_name', e.target.value)}
                placeholder="e.g. St. Jude General Hospital"
              />
            </div>
            <div>
              <label className={LABEL} htmlFor="facility_type">Facility Tier / Type</label>
              <select
                id="facility_type"
                className={INPUT}
                value={form.facility_type}
                onChange={(e) => setField('facility_type', e.target.value)}
              >
                {FACILITY_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="ownership">Ownership</label>
              <select
                id="ownership"
                className={INPUT}
                value={form.ownership}
                onChange={(e) => setField('ownership', e.target.value)}
              >
                {OWNERSHIP_OPTIONS.map((o) => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className={LABEL} htmlFor="facility_head">Facility Head / Medical Director</label>
              <input
                id="facility_head"
                className={INPUT}
                value={form.facility_head}
                onChange={(e) => setField('facility_head', e.target.value)}
                placeholder="e.g. Dr. Corazon Ibarra"
              />
            </div>
          </div>
        </div>

        {/* SECTION 2: LOCATION */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
            2. Geographic Location
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={LABEL} htmlFor="region">Region</label>
              <select
                id="region"
                className={INPUT}
                value={location.codes.region || ''}
                onChange={(e) => location.selectRegion(e.target.value)}
              >
                <option value="">Select region…</option>
                {location.regions.map((r) => (
                  <option key={r.code} value={r.code}>{r.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="province">Province</label>
              <select
                id="province"
                className={INPUT}
                value={location.codes.province || ''}
                onChange={(e) => location.selectProvince(e.target.value)}
                disabled={!location.codes.region}
              >
                <option value="">Select province…</option>
                {location.provinces.map((p) => (
                  <option key={p.code} value={p.code}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="municipality">City / Municipality</label>
              <select
                id="municipality"
                className={INPUT}
                value={location.codes.city || ''}
                onChange={(e) => location.selectCity(e.target.value)}
                disabled={!location.codes.province}
              >
                <option value="">Select city / municipality…</option>
                {location.cities.map((c) => (
                  <option key={c.code} value={c.code}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="barangay">Barangay</label>
              <select
                id="barangay"
                className={INPUT}
                value={form.barangay || ''}
                onChange={(e) => location.selectBarangay(e.target.value)}
                disabled={!location.codes.city}
              >
                <option value="">Select barangay…</option>
                {location.barangays.map((b) => (
                  <option key={b.code} value={b.name}>{b.name}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className={LABEL} htmlFor="address">Street Address</label>
              <input
                id="address"
                className={INPUT}
                value={form.address}
                onChange={(e) => setField('address', e.target.value)}
                placeholder="Complete street address"
              />
            </div>
            <div>
              <label className={LABEL} htmlFor="latitude">
                Latitude {location.geocoding ? <span className="font-normal text-slate-400">(resolving…)</span> : null}
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
                Longitude {location.geocoding ? <span className="font-normal text-slate-400">(resolving…)</span> : null}
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
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Latitude/Longitude auto-fill from the selected City/Barangay via OpenStreetMap — adjust manually if the pin looks off.
          </p>
        </div>

        {/* SECTION 3: CONTACT INFORMATION */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
            3. Contact Information
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={LABEL} htmlFor="contact_number">Contact Number</label>
              <input
                id="contact_number"
                className={INPUT}
                value={form.contact_number}
                onChange={(e) => setField('contact_number', e.target.value)}
                placeholder="+639171234567"
              />
            </div>
            <div>
              <label className={LABEL} htmlFor="email">Official Email</label>
              <input
                id="email"
                type="email"
                className={INPUT}
                value={form.email}
                onChange={(e) => setField('email', e.target.value)}
                placeholder="admin@facility.ph"
              />
            </div>
          </div>
        </div>

        {/* SECTION 4: LICENSING (LTO) */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
            4. Licensing (DOH LTO)
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={LABEL} htmlFor="lto_number">LTO Number</label>
              <input
                id="lto_number"
                className={INPUT}
                value={form.lto_number}
                onChange={(e) => setField('lto_number', e.target.value)}
                placeholder="LTO-11-2026-001"
              />
            </div>
            <div>
              <label className={LABEL} htmlFor="lto_type">LTO License Type</label>
              <select
                id="lto_type"
                className={INPUT}
                value={form.lto_type}
                onChange={(e) => setField('lto_type', e.target.value)}
              >
                <option value="">Select license type…</option>
                {FACILITY_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="lto_issue_date">Issue Date</label>
              <input
                id="lto_issue_date"
                type="date"
                className={INPUT}
                value={form.lto_issue_date}
                onChange={(e) => setField('lto_issue_date', e.target.value)}
              />
            </div>
            <div>
              <label className={LABEL} htmlFor="lto_expiration_date">Expiration Date</label>
              <input
                id="lto_expiration_date"
                type="date"
                className={INPUT}
                value={form.lto_expiration_date}
                onChange={(e) => setField('lto_expiration_date', e.target.value)}
              />
            </div>
            <div>
              <label className={LABEL} htmlFor="lto_status">LTO Status</label>
              <select
                id="lto_status"
                className={INPUT}
                value={form.lto_status}
                onChange={(e) => setField('lto_status', e.target.value)}
              >
                {LTO_STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            {!facility ? (
              <div>
                <label className={LABEL} htmlFor="lto_file">LTO Document Upload (PDF/Image)</label>
                <input
                  id="lto_file"
                  type="file"
                  accept=".pdf,.png,.jpg,.jpeg"
                  className={INPUT}
                  onChange={(e) => setLtoFile(e.target.files[0] || null)}
                />
              </div>
            ) : facility.lto_file_path ? (
              <div>
                <label className={LABEL}>Current LTO File</label>
                <a
                  href={facility.lto_file_path}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-600 underline hover:text-blue-800"
                >
                  <FileText size={14} /> View Attached Document
                </a>
              </div>
            ) : null}
          </div>
          {form.lto_type && form.facility_type && form.lto_type !== form.facility_type ? (
            <div className="mt-4 rounded-lg bg-amber-50 px-3.5 py-2.5 text-xs text-amber-800">
              <p className="font-semibold">License type doesn't match facility tier</p>
              <p className="mt-0.5 text-amber-700">
                Hospital Level is <strong>{form.facility_type}</strong>, but LTO License Type is{' '}
                <strong>{form.lto_type}</strong>. This can be legitimate (e.g. a level upgrade with a pending LTO
                renewal) — just confirm it's intentional before saving.
              </p>
            </div>
          ) : null}
        </div>

        {/* SECTION 5: SYSTEM & ROUTING CONFIG */}
        <div className="rounded-xl border border-slate-200 bg-slate-50/50 p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-500">
            5. Operational & AI System Parameters
          </h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={LABEL} htmlFor="facility_status">Operational Status</label>
              <select
                id="facility_status"
                className={INPUT}
                value={form.facility_status}
                onChange={(e) => setField('facility_status', e.target.value)}
              >
                {FACILITY_STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="pso_daily_routing_limit">PSO Daily Referral Cap</label>
              <input
                id="pso_daily_routing_limit"
                type="number"
                min="1"
                className={INPUT}
                value={form.pso_daily_routing_limit}
                onChange={(e) => setField('pso_daily_routing_limit', e.target.value)}
              />
              <p className="mt-1 text-xs text-slate-400">
                Max daily accepted referrals before AI penalizes load score.
              </p>
            </div>
          </div>
        </div>
      </form>
    </Modal>
  )
}

export default function Hospitals() {
  const [search, setSearch] = useState('')
  const [notice, setNotice] = useState('')
  const [formTarget, setFormTarget] = useState(null)

  const fetchFacilities = useCallback(() => adminApi.listFacilities({ search }), [search])
  const { data, loading, error, refresh, setError } = useApiResource(fetchFacilities, [])
  const facilities = data || []

  function handleFormSaved(action, facilityName) {
    setNotice(`Facility "${facilityName}" was ${action}.`)
    refresh()
  }

  async function handleDelete(facility) {
    const confirmed = await confirmAction({
      title: `Delete "${facility.facility_name}"?`,
      text: 'This cannot be undone. Facilities with active referral history cannot be deleted — set status to Inactive instead.',
      confirmText: 'Delete',
    })
    if (!confirmed) return

    setError('')
    setNotice('')
    try {
      const result = await adminApi.deleteFacility(facility.id)
      setNotice(result.message)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <PageHeader
        title="Health Facility Registry"
        subtitle="Manage facility identities, contact details, and LTO licensing."
        actions={
          <>
            <button type="button" className={BTN_SECONDARY} onClick={refresh} disabled={loading}>
              Refresh
            </button>
            <button type="button" className={BTN_PRIMARY} onClick={() => setFormTarget({ facility: null })}>
              + Register Facility
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
        <label className={LABEL} htmlFor="facilitySearch">
          Search Facilities
        </label>
        <input
          id="facilitySearch"
          className={INPUT}
          placeholder="Filter by facility name"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className={`${CARD} overflow-hidden`}>
        {loading ? (
          <Spinner label="Loading health facilities…" />
        ) : facilities.length === 0 ? (
          <EmptyState
            title="No health facilities registered."
            hint="Use “Register Facility” to add the first facility node."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th className={TH}>Code</th>
                  <th className={TH}>Facility Name</th>
                  <th className={TH}>Tier / Type</th>
                  <th className={TH}>Ownership</th>
                  <th className={TH}>LTO Licensing</th>
                  <th className={TH}>Status</th>
                  <th className={TH}>Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {facilities.map((f) => (
                  <tr key={f.id} className="hover:bg-slate-50">
                    <td className={`${TD} font-mono text-xs text-slate-500`}>{f.facility_code || `FAC-${f.id}`}</td>
                    <td className={`${TD} font-semibold text-slate-900`}>{f.facility_name}</td>
                    <td className={TD}>{f.facility_type || '—'}</td>
                    <td className={TD}>{f.ownership || '—'}</td>
                    <td className={TD}>
                      <div className="flex flex-col gap-0.5 text-xs">
                        <span>{f.lto_number || 'No LTO'}</span>
                        {f.lto_status ? (
                          <Badge tone={f.lto_status === 'Active' ? 'green' : 'amber'}>
                            {f.lto_status}
                          </Badge>
                        ) : null}
                      </div>
                    </td>
                    <td className={TD}>
                      <Badge tone={f.facility_status === 'Active' ? 'green' : 'slate'}>
                        {f.facility_status || 'Active'}
                      </Badge>
                    </td>
                    <td className={TD}>
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          title="Edit Facility"
                          aria-label="Edit Facility"
                          className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                          onClick={() => setFormTarget({ facility: f })}
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          type="button"
                          title="Delete Facility"
                          aria-label="Delete Facility"
                          className="rounded-lg p-2 text-slate-500 transition hover:bg-red-50 hover:text-red-600"
                          onClick={() => handleDelete(f)}
                        >
                          <Trash2 size={16} />
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
        <FacilityFormModal
          key={formTarget.facility ? `edit-${formTarget.facility.id}` : 'create'}
          facility={formTarget.facility}
          onClose={() => setFormTarget(null)}
          onSaved={handleFormSaved}
        />
      ) : null}
    </>
  )
}
