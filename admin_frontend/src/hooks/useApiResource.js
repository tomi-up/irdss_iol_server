import { useCallback, useEffect, useState } from 'react'

/**
 * Loads data from the admin API and tracks loading/error state.
 *
 * `fetcher` must be a `useCallback`-stabilised function; the request re-runs whenever
 * its identity changes (i.e. whenever the caller's filters change) or `refresh()` is
 * called. All state transitions happen inside async callbacks, never synchronously in
 * the effect body, so React never has to schedule a cascading re-render.
 */
export function useApiResource(fetcher, initialData = null) {
  const [state, setState] = useState({ data: initialData, loading: true, error: '' })
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    let cancelled = false

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ data, loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState((prev) => ({ ...prev, loading: false, error: err.message }))
      })

    return () => {
      cancelled = true
    }
  }, [fetcher, nonce])

  // Re-runs the fetcher without changing its identity (used by Refresh buttons and polling).
  const refresh = useCallback(() => setNonce((n) => n + 1), [])

  // Lets pages surface errors from their own mutations through the same banner.
  const setError = useCallback((error) => setState((prev) => ({ ...prev, error })), [])

  return { data: state.data, loading: state.loading, error: state.error, refresh, setError }
}
