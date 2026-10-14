import { useCallback, useState } from 'react'
import { adminApi } from '../api/client'
import { useApiResource } from '../hooks/useApiResource'
import { Alert, Badge, EmptyState, PageHeader, Spinner, StatCard } from '../components/ui'
import { BTN_SECONDARY, CARD, STATUS_TONE } from '../components/styles'

// Horizontal bar list used for the status/severity/facility breakdowns.
function BreakdownList({ title, items, asStatus = false }) {
  const max = Math.max(1, ...items.map((i) => i.count))

  return (
    <div className={`${CARD} p-5`}>
      <p className="mb-4 text-sm font-semibold text-slate-900">{title}</p>
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">No data yet.</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.label}>
              <div className="mb-1 flex items-center justify-between gap-3">
                <span className="truncate text-sm text-slate-600">
                  {asStatus ? (
                    <Badge tone={STATUS_TONE[item.label] || 'slate'}>{item.label}</Badge>
                  ) : (
                    item.label
                  )}
                </span>
                <span className="shrink-0 text-sm font-semibold text-slate-900">{item.count}</span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-red-600"
                  style={{ width: `${(item.count / max) * 100}%` }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Rounds a chart max up to a clean tick value so axis labels read as round numbers.
function niceMax(value) {
  if (value <= 10) return Math.ceil(value / 2) * 2 || 2
  if (value <= 50) return Math.ceil(value / 10) * 10
  if (value <= 200) return Math.ceil(value / 20) * 20
  return Math.ceil(value / 50) * 50
}

// Analytics-style hero chart for the 7-day referral volume series. Single series,
// so no legend box (the title names it) — the axis carries values that aren't
// directly labeled, and a real hover/focus tooltip carries the rest.
function VolumeChart({ data }) {
  const [activeIndex, setActiveIndex] = useState(null)
  const rawMax = Math.max(1, ...data.map((d) => d.count))
  const axisMax = niceMax(rawMax)
  const lastIndex = data.length - 1
  const ticks = [axisMax, Math.round(axisMax / 2), 0]

  return (
    <div className={`${CARD} p-6`}>
      <p className="text-sm font-semibold text-slate-900">Referral Volume</p>
      <p className="mt-1 text-xs text-slate-400">Daily referrals created, last 7 days</p>

      <div className="mt-6 flex h-64 gap-3">
        <div className="flex flex-col justify-between pb-6 text-right text-[11px] text-slate-400">
          {ticks.map((t) => (
            <span key={t}>{t}</span>
          ))}
        </div>

        <div className="relative flex flex-1 items-stretch">
          {/* Recessive gridlines, one-step-off-surface, hairline */}
          <div className="absolute inset-x-0 top-0 bottom-6 flex flex-col justify-between">
            {ticks.map((t) => (
              <div key={t} className="h-px bg-slate-100" />
            ))}
          </div>

          <div className="relative flex flex-1 items-end gap-3">
            {data.map((point, index) => {
              const isLast = index === lastIndex
              const isActive = activeIndex === index
              const heightPct = Math.max((point.count / axisMax) * 100, point.count > 0 ? 3 : 0)

              return (
                <div key={point.date} className="flex flex-1 flex-col items-center">
                  <div className="relative flex h-56 w-full items-end justify-center">
                    {isActive ? (
                      <div className="absolute -top-8 z-10 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white shadow-lg">
                        {point.count} · {point.date}
                      </div>
                    ) : null}

                    {isLast ? (
                      <span className="mb-1.5 text-xs font-semibold text-slate-700">{point.count}</span>
                    ) : null}

                    <button
                      type="button"
                      className="w-full max-w-6 rounded-t bg-red-600 outline-none transition-all hover:bg-red-700 focus-visible:ring-2 focus-visible:ring-red-600/40"
                      style={{ height: `${heightPct}%` }}
                      onMouseEnter={() => setActiveIndex(index)}
                      onMouseLeave={() => setActiveIndex(null)}
                      onFocus={() => setActiveIndex(index)}
                      onBlur={() => setActiveIndex(null)}
                      aria-label={`${point.date}: ${point.count} referrals`}
                    />
                  </div>
                  <span className="mt-2 text-[11px] text-slate-400">{point.date.slice(5)}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const fetchStats = useCallback(() => adminApi.getStats(), [])
  const { data: stats, loading, error, refresh } = useApiResource(fetchStats)

  return (
    <>
      <PageHeader
        title="Network Dashboard"
        subtitle="Live snapshot of referral traffic across every connected facility."
        actions={
          <button type="button" className={BTN_SECONDARY} onClick={refresh} disabled={loading}>
            Refresh
          </button>
        }
      />

      {error ? (
        <Alert tone="red" title="Could not load statistics">
          {error}
        </Alert>
      ) : null}

      {loading ? <Spinner label="Crunching network statistics…" /> : null}

      {stats ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Total Referrals" value={stats.total_referrals} hint="All time" />
            <StatCard
              label="Created Today"
              value={stats.referrals_today}
              tone="blue"
              hint={`${stats.referrals_last_7_days} in the last 7 days`}
            />
            <StatCard
              label="Awaiting Decision"
              value={stats.active_referrals}
              tone="amber"
              hint="Pending or seen, not yet resolved"
            />
            <StatCard
              label="Completed Transfers"
              value={stats.completed_referrals}
              tone="green"
              hint={`${stats.cancelled_referrals} cancelled`}
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Connected Hospitals" value={stats.total_hospitals} />
            <StatCard
              label="Available Beds"
              value={stats.total_available_beds}
              tone="green"
              hint="Network-wide capacity"
            />
            <StatCard
              label="Issued Credentials"
              value={stats.issued_credentials ?? stats.active_api_keys ?? 0}
              tone="blue"
              hint={`${stats.total_hospitals ?? 0} facilities registered`}
            />

            <StatCard
              label="Avg. First Response"
              value={stats.avg_response_minutes !== null ? `${stats.avg_response_minutes}m` : '—'}
              tone="violet"
              hint="Referral created → first hospital decision"
            />
          </div>

          <div className="mt-6">
            <VolumeChart data={stats.daily_volume} />
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-2">
            <BreakdownList title="Referrals by status" items={stats.status_breakdown} asStatus />
            <BreakdownList title="Referrals by severity" items={stats.severity_breakdown} />
            <BreakdownList title="Top referring facilities" items={stats.top_referring_facilities} />
            <BreakdownList title="Top receiving facilities" items={stats.top_receiving_facilities} />
          </div>
        </>
      ) : null}

      {!loading && !stats && !error ? <EmptyState title="No data available." /> : null}
    </>
  )
}
