import { NavLink, Outlet } from 'react-router-dom'
import { Activity, Building2, KeyRound, LayoutGrid, Repeat } from 'lucide-react'
import Topbar from './Topbar'
import { DOT_GRID_LIGHT, NAV_ACTIVE, NAV_BASE, NAV_IDLE } from './styles'
import irdssLogo from '../assets/irdss-logo.png'

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutGrid, end: true },
  { to: '/referrals', label: 'All Referrals', icon: Repeat },
  { to: '/hospitals', label: 'Health Facilities', icon: Building2 },
  { to: '/credentials', label: 'Facility Credentials', icon: KeyRound },
  { to: '/monitoring', label: 'Server Monitoring', icon: Activity },
]


// Persistent app shell: dark sidebar matching the mock_hospitals HIS exactly (gray-900,
// yellow-600 active pill), a light top bar for identity/sign-out, and the routed outlet.
export default function Layout() {
  return (
    <div className="flex min-h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800 bg-gray-900">
        <div className="flex items-center gap-3 border-b border-slate-800/80 p-6">
          <img src={irdssLogo} alt="IRDSS" className="h-10 w-10 object-contain" />
          <div>
            <h2 className="text-base font-bold leading-tight text-white">IRDSS</h2>
            <p className="text-xs text-slate-400">Admin Console</p>
          </div>
        </div>

        <nav className="space-y-1.5 p-4">
          <p className="px-4 pb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Menu</p>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `${NAV_BASE} ${isActive ? NAV_ACTIVE : NAV_IDLE}`}
            >
              <item.icon size={18} strokeWidth={2} />
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <div className="flex flex-1 flex-col overflow-x-hidden">
        <Topbar />
        <main className="flex-1 overflow-x-hidden bg-white px-8 py-8" style={DOT_GRID_LIGHT}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
