import { useAuth } from '../context/auth-context'
import { BTN_SECONDARY } from './styles'

// Header bar above the routed page content — houses the signed-in admin's identity
// and sign-out control, matching the TailAdmin reference's top navbar structure.
export default function Topbar() {
  const { identity, logout } = useAuth()
  const name = identity?.hospital_name || '—'
  const initial = name.charAt(0).toUpperCase()

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
      <p className="text-sm font-semibold text-slate-900">IRDSS Admin Console</p>

      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-red-50 text-sm font-semibold text-red-600">
            {initial}
          </span>
          <span className="text-sm font-semibold text-slate-700">{name}</span>
        </div>
        <button type="button" onClick={logout} className={BTN_SECONDARY}>
          Sign out
        </button>
      </div>
    </header>
  )
}
