import { useState } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { useAuth } from '../context/auth-context'
import { adminApi } from '../api/client'
import { Alert } from '../components/ui'
import { BTN_PRIMARY, DOT_GRID_LIGHT, INPUT, LABEL, LINK_MUTED } from '../components/styles'
import irdssLogo from '../assets/irdss-logo.png'

// Credential gate, in up to two phases:
//   1. Raw admin key -> POST /admin/login tells us whether to bypass 2FA (root),
//      enroll for the first time (QR + confirm code), or just prompt for a code.
//   2. TOTP code -> POST /admin/2fa/verify issues a session token, which is what
//      AuthContext actually stores and validates against /admin/me from then on.
// Layout follows the TailAdmin sign-in template (split screen, solid brand panel)
// restyled with mock_hospitals' solid red-600 and the real IRDSS logo.
export default function Login() {
  const { login } = useAuth()
  const [phase, setPhase] = useState('key') // 'key' | 'setup' | 'code'
  const [key, setKey] = useState('')
  const [code, setCode] = useState('')
  const [adminName, setAdminName] = useState('')
  const [enrollment, setEnrollment] = useState(null) // { provisioningUri, secret }
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  function resetToKeyPhase() {
    setPhase('key')
    setCode('')
    setEnrollment(null)
    setError('')
  }

  async function handleKeySubmit(event) {
    event.preventDefault()
    const rawKey = key.trim()
    if (!rawKey) {
      setError('Enter your administrator API key.')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const result = await adminApi.login(rawKey)

      if (result.root) {
        // Root break-glass credential is exempt from 2FA — log straight in.
        await login(rawKey)
        return
      }

      setAdminName(result.admin_name)

      if (result.needs_setup) {
        const setup = await adminApi.setup2fa(rawKey)
        setEnrollment({ provisioningUri: setup.provisioning_uri, secret: setup.secret })
        setPhase('setup')
      } else {
        setPhase('code')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleCodeSubmit(event) {
    event.preventDefault()
    if (!code.trim()) {
      setError('Enter the 6-digit code from your authenticator app.')
      return
    }

    setSubmitting(true)
    setError('')
    try {
      const { token } = await adminApi.verify2fa(key.trim(), code.trim())
      await login(token)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-full bg-white">
      {/* Left panel: credential form */}
      <div
        className="flex w-full flex-col justify-center bg-white px-6 py-12 sm:px-12 lg:w-1/2 lg:px-20"
        style={DOT_GRID_LIGHT}
      >
        <div className="mx-auto w-full max-w-sm">
          <img src={irdssLogo} alt="IRDSS" className="mb-8 h-14 w-auto lg:hidden" />

          {phase === 'key' ? (
            <>
              <h1 className="text-3xl font-bold text-slate-900">Sign In</h1>
              <p className="mt-2 text-sm text-slate-500">
                Enter your administrator key to continue.
              </p>

              <form onSubmit={handleKeySubmit} className="mt-8 space-y-4">
                {error ? <Alert tone="red">{error}</Alert> : null}

                <div>
                  <label className={LABEL} htmlFor="adminKey">
                    Administrator  Key
                  </label>
                  <input
                    id="adminKey"
                    type="password"
                    className={INPUT}
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder="irdss_admin_key_…"
                    autoComplete="off"
                    autoFocus
                  />
                </div>

                <button type="submit" className={`${BTN_PRIMARY} mt-2 w-full`} disabled={submitting}>
                  {submitting ? 'Checking…' : 'Continue'}
                </button>
              </form>
            </>
          ) : null}

          {phase === 'setup' ? (
            <>
              <h1 className="text-3xl font-bold text-slate-900">Set up 2FA</h1>
              <p className="mt-2 text-sm text-slate-500">
                Hi <strong className="text-slate-700">{adminName}</strong> — scan this QR code with
                Google Authenticator (or any TOTP app), then enter the code it shows.
              </p>

              <form onSubmit={handleCodeSubmit} className="mt-8 space-y-4">
                {error ? <Alert tone="red">{error}</Alert> : null}

                <div className="flex justify-center rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <QRCodeSVG value={enrollment.provisioningUri} size={176} />
                </div>

                <details className="text-xs text-slate-500">
                  <summary className="cursor-pointer font-semibold text-slate-600">
                    Can&apos;t scan? Enter this code manually
                  </summary>
                  <code className="mt-2 block break-all rounded-lg bg-slate-100 p-2 font-mono text-slate-700">
                    {enrollment.secret}
                  </code>
                </details>

                <div>
                  <label className={LABEL} htmlFor="totpCode">
                    6-digit code
                  </label>
                  <input
                    id="totpCode"
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    className={`${INPUT} text-center text-lg tracking-[0.3em]`}
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="••••••"
                    autoComplete="off"
                    autoFocus
                  />
                </div>

                <button type="submit" className={`${BTN_PRIMARY} mt-2 w-full`} disabled={submitting}>
                  {submitting ? 'Confirming…' : 'Confirm & Enable 2FA'}
                </button>
                <button type="button" className={`${LINK_MUTED} block w-full text-center`} onClick={resetToKeyPhase}>
                  Back
                </button>
              </form>
            </>
          ) : null}

          {phase === 'code' ? (
            <>
              <h1 className="text-3xl font-bold text-slate-900">Enter your code</h1>
              <p className="mt-2 text-sm text-slate-500">
                Hi <strong className="text-slate-700">{adminName}</strong> — enter the current 6-digit
                code from your authenticator app.
              </p>

              <form onSubmit={handleCodeSubmit} className="mt-8 space-y-4">
                {error ? <Alert tone="red">{error}</Alert> : null}

                <div>
                  <label className={LABEL} htmlFor="totpCode">
                    6-digit code
                  </label>
                  <input
                    id="totpCode"
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    className={`${INPUT} text-center text-lg tracking-[0.3em]`}
                    value={code}
                    onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                    placeholder="••••••"
                    autoComplete="off"
                    autoFocus
                  />
                </div>

                <button type="submit" className={`${BTN_PRIMARY} mt-2 w-full`} disabled={submitting}>
                  {submitting ? 'Verifying…' : 'Verify & Sign in'}
                </button>
                <button type="button" className={`${LINK_MUTED} block w-full text-center`} onClick={resetToKeyPhase}>
                  Back
                </button>
              </form>
            </>
          ) : null}

          <p className="mt-8 text-center text-xs leading-relaxed text-slate-400">
            Each admin has their own key and their own authenticator entry — 2FA is enrolled
            automatically the first time you sign in.
          </p>
        </div>
      </div>

      {/* Right panel: solid brand color, dot-grid backdrop, IRDSS branding */}
      <div className="relative hidden w-1/2 items-center justify-center overflow-hidden bg-red-600 lg:flex">
        <div
          className="pointer-events-none absolute inset-0 opacity-15"
          style={{
            backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)',
            backgroundSize: '24px 24px',
            WebkitMaskImage: 'radial-gradient(ellipse 60% 60% at 50% 40%, black, transparent)',
            maskImage: 'radial-gradient(ellipse 60% 60% at 50% 40%, black, transparent)',
          }}
        />

        <div className="relative flex flex-col items-center px-8 text-center">
          <div className="flex h-28 w-28 items-center justify-center rounded-2xl bg-white shadow-lg">
            <img src={irdssLogo} alt="IRDSS" className="h-20 w-20 object-contain" />
          </div>
          <p className="mt-6 text-2xl font-bold text-white">IRDSS Admin Console</p>
          <p className="mt-2 max-w-xs text-sm text-red-100">
            Interoperability Layer control plane for the Mindanao-wide Intelligent Referral
            Decision Support System.
          </p>
        </div>
      </div>
    </div>
  )
}
