import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth'
import BrandLogo from '../components/BrandLogo'
import { homeRouteFor } from '../roleHome'

export default function Login() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (loading) return null
  if (user) return <Navigate to={homeRouteFor(user)} replace />

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const signedIn = await login(username, password)
      // Land Sales on the OEM screen, Ops on the Operations screen (Change 1).
      navigate(homeRouteFor(signedIn), { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="screen">
      <div className="landing-hero">
        <div className="login-card">
          <div className="logo-wrap">
            <BrandLogo variant="login" />
          </div>
          <h1>Sign in</h1>
          <div className="co">JCPL — Jolly Clamps Pvt. Ltd.</div>

          {/* The prototype said "type anything" — this portal authenticates
              against real JCPL accounts, so the hint says so instead. */}
          <div className="hint">Use your JCPL workspace user ID and password.</div>

          {error && <div className="login-error">{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="field">
              <label htmlFor="uid">User ID</label>
              <input
                id="uid"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="e.g. rajeev.j"
                autoComplete="username"
                autoFocus
              />
            </div>
            <div className="field">
              <label htmlFor="pwd">Password</label>
              <input
                id="pwd"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>
            <button className="btn-primary" type="submit" disabled={submitting}>
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <div style={{ textAlign: 'center', marginTop: 14 }}>
            <Link to="/" style={{ color: 'var(--muted)', fontSize: 12 }}>
              ← Back to organisations
            </Link>
          </div>
        </div>
      </div>
    </section>
  )
}
