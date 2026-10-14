import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { useAuth } from './context/auth-context'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Referrals from './pages/Referrals'
import Hospitals from './pages/Hospitals'
import Credentials from './pages/Credentials'
import Monitoring from './pages/Monitoring'

// Renders the console only once a stored admin key has been revalidated against the gateway.
function AuthGate() {
  const { isAuthenticated, checking } = useAuth()

  if (checking) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Spinner label="Verifying administrator credentials…" />
      </div>
    )
  }

  if (!isAuthenticated) return <Login />

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="referrals" element={<Referrals />} />
        <Route path="hospitals" element={<Hospitals />} />
        <Route path="credentials" element={<Credentials />} />
        <Route path="api-keys" element={<Navigate to="/credentials" replace />} />
        <Route path="monitoring" element={<Monitoring />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}


export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AuthGate />
      </AuthProvider>
    </BrowserRouter>
  )
}
