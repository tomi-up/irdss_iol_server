import { useCallback, useEffect, useState } from 'react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, PageHeader, Spinner, StatCard } from '../components/ui'
import {
  BTN_DANGER,
  BTN_SECONDARY,
  CARD,
  CHECKBOX,
  INPUT,
  LABEL,
  STATUS_TONE,
  TD,
  TH,
} from '../components/styles'
import { formatDateTime, formatUptime, latencyToneClass, statusCodeTone } from '../utils/format'

const AUTO_REFRESH_MS = 10000
const HEALTH_WINDOW_MINUTES = 60
const LEVELS = ['', 'INFO', 'WARNING', 'ERROR']

export default function Monitoring() {
  const [filters, setFilters] = useState({ level: '', path: '', hospital: '' })
  const [autoRefresh, setAutoRefresh] = useState(true)

  const fetchHealth = useCallback(
    () => adminApi.getHealth({ window_minutes: HEALTH_WINDOW_MINUTES }),
    [],
  )
  const fetchLogs = useCallback(
    () =>
      adminApi.getLogs({
        level: filters.level,
        path: filters.path,
        hospital: filters.hospital,
        limit: 200,
      }),
    [filters],
  )

  const health = useApiResource(fetchHealth)
  const logs = useApiResource(fetchLogs)

  const refreshHealth = health.refresh
  const refreshLogs = logs.refresh

  useEffect(() => {
    if (!autoRefresh) return undefined
    const timer = setInterval(() => {
      refreshHealth()
      refreshLogs()
    }, AUTO_REFRESH_MS)
    return () => clearInterval(timer)
  }, [autoRefresh, refreshHealth, refreshLogs])

  async function handleFlush() {
    if (!window.confirm('Clear the in-memory log buffer? Buffered entries are lost permanently.')) {
      return
    }
    try {
      await adminApi.flushLogs()
      refreshLogs()
      refreshHealth()
    } catch (err) {
      logs.setError(err.message)
    }
  }

  function updateFilter(name, value) {
    setFilters((prev) => ({ ...prev, [name]: value }))
  }

  function refreshAll() {
    refreshHealth()
    refreshLogs()
  }

  const healthData = health.data
  const logData = logs.data
  const error = health.error || logs.error

  return (
    <>
      <PageHeader
        title="Server Monitoring"
        subtitle="Gateway health, live traffic metrics, and the in-memory request log."
        actions={
          <>
            <label className="flex items-center gap-2 text-sm font-medium text-slate-600">
              <input
                type="checkbox"
                className={CHECKBOX}
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto-refresh (10s)
            </label>
            <button type="button" className={BTN_SECONDARY} onClick={refreshAll}>
              Refresh
            </button>
            <button type="button" className={BTN_DANGER} onClick={handleFlush}>
              Flush log buffer
            </button>
          </>
        }
      />

      {error ? (
        <Alert tone="red" title="Monitoring unavailable">
          {error}
        </Alert>
      ) : null}

      {health.loading ? <Spinner label="Probing gateway…" /> : null}

      {healthData ? (
        <>
          <div className={`${CARD} mb-4 flex flex-wrap items-center gap-x-8 gap-y-3 p-4`}>
            <div className="flex items-center gap-2">
              <span
                className={`h-3 w-3 rounded-full ${
                  healthData.status === 'healthy' ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
              <span className="text-sm font-semibold text-slate-900">
                Gateway {healthData.status === 'healthy' ? 'healthy' : 'degraded'}
              </span>
            </div>
            <div className="text-sm text-slate-600">
              <span className="font-semibold">Uptime:</span> {formatUptime(healthData.uptime_seconds)}
            </div>
            <div className="text-sm text-slate-600">
              <span className="font-semibold">Started:</span>{' '}
              {formatDateTime(healthData.server_started_at)}
            </div>
            <div className="text-sm text-slate-600">
              <span className="font-semibold">PostgreSQL:</span>{' '}
              {healthData.database_connected ? (
                <span className="text-emerald-600">connected ({healthData.database_latency_ms} ms)</span>
              ) : (
                <span className="text-rose-600">unreachable</span>
              )}
            </div>
          </div>

          {healthData.database_error ? (
            <Alert tone="red" title="Database error">
              {healthData.database_error}
            </Alert>
          ) : null}

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
              label="Requests (last hour)"
              value={healthData.requests_in_window}
              hint={`${healthData.lifetime_requests} since process start`}
            />
            <StatCard
              label="Errors (last hour)"
              value={healthData.errors_in_window}
              tone={healthData.errors_in_window ? 'red' : 'green'}
              hint={`${healthData.lifetime_server_errors} server errors lifetime`}
            />
            <StatCard label="Avg. response" value={`${healthData.avg_response_ms} ms`} tone="blue" />
            <StatCard
              label="Slowest response"
              value={`${healthData.slowest_response_ms} ms`}
              tone="amber"
            />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <div className={`${CARD} p-5 lg:col-span-2`}>
              <p className="mb-4 text-sm font-semibold text-slate-900">Busiest endpoints (last hour)</p>
              {healthData.top_endpoints.length === 0 ? (
                <p className="text-sm text-slate-400">No traffic recorded yet.</p>
              ) : (
                <ul className="space-y-2">
                  {healthData.top_endpoints.map((item) => (
                    <li key={item.endpoint} className="flex items-center justify-between gap-4 text-sm">
                      <code className="truncate font-mono text-xs text-slate-600">{item.endpoint}</code>
                      <span className="shrink-0 font-semibold text-slate-900">{item.count}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className={`${CARD} p-5`}>
              <p className="mb-4 text-sm font-semibold text-slate-900">Database tables</p>
              <ul className="space-y-2">
                {Object.entries(healthData.table_counts).map(([table, count]) => (
                  <li key={table} className="flex items-center justify-between gap-4 text-sm">
                    <code className="font-mono text-xs text-slate-600">{table}</code>
                    <span className="font-semibold text-slate-900">{count}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </>
      ) : null}

      <div className="mt-8">
        <h2 className="mb-3 text-lg font-bold text-slate-900">Request log</h2>

        <div className={`${CARD} mb-4 grid gap-3 p-4 sm:grid-cols-3`}>
          <div>
            <label className={LABEL} htmlFor="logLevel">
              Level
            </label>
            <select
              id="logLevel"
              className={INPUT}
              value={filters.level}
              onChange={(e) => updateFilter('level', e.target.value)}
            >
              {LEVELS.map((level) => (
                <option key={level} value={level}>
                  {level || 'All levels'}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={LABEL} htmlFor="logPath">
              Path contains
            </label>
            <input
              id="logPath"
              className={INPUT}
              placeholder="/api/v1/referral"
              value={filters.path}
              onChange={(e) => updateFilter('path', e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="logHospital">
              Hospital
            </label>
            <input
              id="logHospital"
              className={INPUT}
              placeholder="Authenticated caller"
              value={filters.hospital}
              onChange={(e) => updateFilter('hospital', e.target.value)}
            />
          </div>
        </div>

        <div className={`${CARD} overflow-hidden`}>
          {logs.loading ? (
            <Spinner label="Loading log buffer…" />
          ) : !logData || logData.items.length === 0 ? (
            <EmptyState
              title="No log entries match these filters."
              hint="The buffer only holds requests received since the server started."
            />
          ) : (
            <div className="max-h-[32rem] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    <th className={TH}>Time</th>
                    <th className={TH}>Level</th>
                    <th className={TH}>Method</th>
                    <th className={TH}>Path</th>
                    <th className={TH}>Status</th>
                    <th className={TH}>Duration</th>
                    <th className={TH}>Caller</th>
                    <th className={TH}>Client IP</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {logData.items.map((entry) => (
                    <tr key={entry.id} className="hover:bg-slate-50">
                      <td className={`${TD} text-xs text-slate-500`}>{formatDateTime(entry.timestamp)}</td>
                      <td className={TD}>
                        <Badge tone={STATUS_TONE[entry.level] || 'slate'}>{entry.level}</Badge>
                      </td>
                      <td className={`${TD} font-mono text-xs font-semibold`}>{entry.method}</td>
                      <td className={`${TD} font-mono text-xs`}>
                        {entry.path}
                        {entry.error ? <span className="ml-2 text-rose-600">{entry.error}</span> : null}
                      </td>
                      <td className={TD}>
                        <Badge tone={statusCodeTone(entry.status_code)}>{entry.status_code}</Badge>
                      </td>
                      <td className={`${TD} ${latencyToneClass(entry.duration_ms)}`}>
                        {entry.duration_ms} ms
                      </td>
                      <td className={TD}>
                        {entry.hospital_name || <span className="text-slate-400">—</span>}
                      </td>
                      <td className={`${TD} font-mono text-xs text-slate-500`}>{entry.client_ip || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {logData ? (
            <div className="border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
              Showing {logData.items.length} of {logData.buffered_entries} buffered entries (buffer holds
              up to {logData.max_entries}).
            </div>
          ) : null}
        </div>
      </div>
    </>
  )
}
