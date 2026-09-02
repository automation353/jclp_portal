import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, ApiError } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // On boot: seed the CSRF cookie, then ask who (if anyone) is signed in, so a
  // page refresh keeps an existing Django session instead of bouncing to login.
  useEffect(() => {
    let cancelled = false

    async function restore() {
      try {
        await api.ensureCsrf()
        const current = await api.me()
        if (!cancelled) setUser(current)
      } catch (error) {
        // 403 just means "nobody signed in" — the expected path for a first
        // visit, not a failure worth surfacing.
        if (!cancelled && !(error instanceof ApiError)) console.error(error)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    restore()
    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (username, password) => {
    const signedIn = await api.login(username, password)
    setUser(signedIn)
    return signedIn
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      // Drop the local session even if the round trip failed — leaving a
      // stale user object on screen would be worse than a redundant sign-out.
      setUser(null)
    }
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>')
  return context
}
