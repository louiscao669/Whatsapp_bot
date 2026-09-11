import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { homePathForRole } from '../auth/homePath'

export function LoginPage() {
  const { user, loading, sendCode, verifyCode, tokenLogin } = useAuth()
  const navigate = useNavigate()
  const redirectTo = homePathForRole(user?.role)

  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [token, setToken] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Token login stays enabled on the server (ADMIN_ALLOW_TOKEN_LOGIN) as a way
  // back in if SMTP fails, but it is not advertised on a login page that is
  // reachable from the open internet. Reach it with /login?token=1.
  const showTokenForm = new URLSearchParams(window.location.search).has('token')

  if (!loading && user) {
    return <Navigate to={redirectTo} replace />
  }

  async function handleSendCode(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      const info = await sendCode(email.trim())
      setCodeSent(true)
      setMessage(info)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not send login code')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleVerify(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const session = await verifyCode(email.trim(), code.trim())
      navigate(homePathForRole(session.user.role), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Verification failed')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleTokenLogin(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const session = await tokenLogin(token.trim())
      navigate(homePathForRole(session.user.role), { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Token login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <section className="panel login-panel">
        <h1>Admin login</h1>
        {error ? <p className="error-message">{error}</p> : null}
        {message ? <p className="success-message">{message}</p> : null}

        {!codeSent ? (
          <form onSubmit={handleSendCode}>
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
            <button type="submit" disabled={submitting}>
              Send login code
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerify}>
            <label htmlFor="code">Verification code</label>
            <input
              id="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
            />
            <button type="submit" disabled={submitting}>
              Verify code
            </button>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                setCodeSent(false)
                setCode('')
                setMessage('')
                setError('')
              }}
            >
              Use a different email
            </button>
          </form>
        )}

        {showTokenForm ? (
          <>
            <hr />
            <p className="hint">Token fallback for development or emergency access:</p>
            <form onSubmit={handleTokenLogin}>
              <label htmlFor="token">Admin or expert token</label>
              <input
                id="token"
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="current-password"
              />
              <button type="submit" disabled={submitting}>
                Log in with token
              </button>
            </form>
          </>
        ) : (
          <p className="hint">
            Access is limited to approved study accounts. Ask the study lead to add
            your address if you cannot sign in.
          </p>
        )}
      </section>
    </main>
  )
}
