import { createContext, useContext } from 'react'

// Split out from AuthContext.jsx so that file exports only the provider component,
// which is what React Fast Refresh requires.
export const AuthContext = createContext(null)

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside an <AuthProvider>')
  return ctx
}
