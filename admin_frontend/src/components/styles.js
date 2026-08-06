// Repeated Tailwind class strings, extracted per project guidelines so every admin
// page renders identically. Mirrors the mock_hospitals HIS design language — Inter
// type, solid red-600 as the one brand color (no gradients, per the TailAdmin-style
// flat design this panel now follows) — with rounded-2xl cards, rounded-xl controls,
// rounded-full badges. Kept in a component-free module so Fast Refresh works.

// Subtle dot-grid texture used instead of a flat background on the login form and
// the main app shell — a plain inline style since Tailwind has no dot-pattern utility.
export const DOT_GRID_LIGHT = {
  backgroundImage: 'radial-gradient(#cbd5e1 1px, transparent 1px)',
  backgroundSize: '22px 22px',
}

export const CARD = 'rounded-2xl border border-slate-200/80 bg-white shadow-sm'
export const CARD_HOVER = `${CARD} transition-shadow hover:shadow-md`
export const INPUT =
  'w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2.5 text-sm text-slate-800 outline-none transition-all placeholder-slate-400 focus:bg-white focus:border-red-600 focus:ring-4 focus:ring-red-600/10 disabled:bg-slate-100'
export const LABEL = 'mb-1.5 block text-xs font-semibold text-slate-700'

// Primary = the constructive commit action per page (sign in, save, issue, create).
export const BTN_PRIMARY =
  'inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:bg-red-700 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50'
export const BTN_SECONDARY =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-all hover:bg-slate-50 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50'
// Danger is a lighter red tint (not filled) so it never gets confused with BTN_PRIMARY
// at a glance — both are "red", but only the constructive action is solid.
export const BTN_DANGER =
  'inline-flex items-center justify-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm font-semibold text-red-700 transition-all hover:border-red-300 hover:bg-red-100 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50'
export const LINK_ACTION = 'text-sm font-semibold text-red-600 transition hover:text-red-700'
export const LINK_DANGER = 'text-sm font-semibold text-rose-600 transition hover:text-rose-700'
export const LINK_MUTED = 'text-sm font-semibold text-slate-500 transition hover:text-slate-800'
export const TH =
  'whitespace-nowrap px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500'
export const TD = 'whitespace-nowrap px-4 py-3 text-sm text-slate-700'
export const CHECKBOX = 'h-4 w-4 rounded border-slate-300 text-red-600 focus:ring-red-600/30'

// Dark sidebar nav, matching the mock_hospitals HIS sidebar exactly: gray-900 panel,
// solid yellow-600 pill on the active item, slate-400 idle text/icons.
export const NAV_BASE = 'group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-all'
export const NAV_ACTIVE = 'bg-yellow-600 text-white shadow-md shadow-yellow-600/20'
export const NAV_IDLE = 'text-slate-400 hover:bg-slate-800/60 hover:text-white'

// Icon-in-rounded-square badge used on stat cards, matching the reference dashboard.
export const ICON_BADGE = 'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-slate-500'

export const BADGE_TONES = {
  slate: 'bg-slate-100 text-slate-700',
  green: 'bg-emerald-100 text-emerald-700',
  amber: 'bg-amber-100 text-amber-700',
  red: 'bg-rose-100 text-rose-700',
  blue: 'bg-indigo-100 text-indigo-700',
  violet: 'bg-violet-100 text-violet-700',
  yellow: 'bg-yellow-100 text-yellow-800',
}

export const STAT_TONES = {
  slate: 'text-slate-900',
  green: 'text-emerald-600',
  amber: 'text-amber-600',
  red: 'text-rose-600',
  blue: 'text-indigo-600',
  violet: 'text-violet-600',
}

export const ALERT_TONES = {
  red: 'border-rose-200 bg-rose-50 text-rose-800',
  green: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  amber: 'border-amber-200 bg-amber-50 text-amber-800',
  blue: 'border-indigo-200 bg-indigo-50 text-indigo-800',
}

// Maps a referral lifecycle status (and log severity level) onto a consistent colour.
export const STATUS_TONE = {
  PENDING: 'amber',
  SEEN: 'blue',
  ACCEPTED: 'green',
  REDIRECTED: 'violet',
  CANCELLED: 'red',
  NOT_SELECTED: 'slate',
  INFO: 'slate',
  WARNING: 'amber',
  ERROR: 'red',
}
