import { useCallback, useEffect, useMemo, useState } from 'react'
import { adminApi, clearStoredKey, getStoredKey, setStoredKey } from '../api/client'
import { AuthContext } from './auth-context'

// Holds the operator's admin credential and revalidates it against /admin/me on load.
export function AuthProvider({ children }) {
  const [apiKey, setApiKey] = useState(getStoredKey)
  const [identity, setIdentity] = useState(null)
  const [checking, setChecking] = useState(() => Boolean(getStoredKey()))

  useEffect(() => {
    if (!apiKey) return undefined

    let cancelled = false

    adminApi
      .verifyKey(apiKey)
      .then((data) => {
        if (cancelled) return
        setIdentity(data)
        setChecking(false)
      })
      .catch(() => {
        // A stored key that no longer authenticates is dropped so the login gate reappears.
        if (cancelled) return
        clearStoredKey()
        setApiKey('')
        setIdentity(null)
        setChecking(false)
      })

    return () => {
      cancelled = true
    }
  }, [apiKey])

  // Validates a pasted key before persisting it, so a bad key never reaches localStorage.
  const login = useCallback(async (candidateKey) => {
    const data = await adminApi.verifyKey(candidateKey)
    setStoredKey(candidateKey)
    setApiKey(candidateKey)
    setIdentity(data)
    setChecking(false)
    return data
  }, [])

  const logout = useCallback(() => {
    clearStoredKey()
    setApiKey('')
    setIdentity(null)
    setChecking(false)
  }, [])

  const value = useMemo(
    () => ({ apiKey, identity, checking, isAuthenticated: Boolean(identity), login, logout }),
    [apiKey, identity, checking, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
