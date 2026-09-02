import { useState } from 'react'

/**
 * The Jolly Clamps mark, with the prototype's fallback behaviour: if the image
 * can't load, a "JC" badge takes its place rather than leaving a blank gap.
 *
 * variant: 'topbar' (small, knocked out to white by CSS) | 'launcher' | 'login'
 */
export default function BrandLogo({ variant = 'launcher' }) {
  const [failed, setFailed] = useState(false)

  if (failed) {
    if (variant === 'topbar') return <div className="logo">JC</div>
    if (variant === 'login') {
      return <div className="big-logo" style={{ width: 56, height: 56, fontSize: 20 }}>JC</div>
    }
    return <div className="big-logo">JC</div>
  }

  return (
    <img
      className={variant === 'topbar' ? 'brandlogo-w' : 'brandlogo'}
      src="/jolly-clamps-logo.png"
      alt="Jolly Clamps"
      onError={() => setFailed(true)}
    />
  )
}
