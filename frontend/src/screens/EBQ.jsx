import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

const DEFAULTS = { annualDemand: '48000', orderingCost: '1200', holdingCost: '15' }

export default function EBQ() {
  const navigate = useNavigate()
  const [inputs, setInputs] = useState(DEFAULTS)
  const [result, setResult] = useState(null)
  const [message, setMessage] = useState('')
  // Guards against a slow earlier response overwriting a newer one.
  const requestId = useRef(0)

  const calculate = useCallback(async (annualDemand, orderingCost, holdingCost) => {
    const id = ++requestId.current
    try {
      const data = await api.ebq({ annualDemand, orderingCost, holdingCost })
      if (id !== requestId.current) return
      setResult(data)
      setMessage('')
    } catch (err) {
      if (id !== requestId.current) return
      setResult(null)
      setMessage(err.message)
    }
  }, [])

  const parsed = {
    D: Number(inputs.annualDemand),
    S: Number(inputs.orderingCost),
    H: Number(inputs.holdingCost),
  }
  const valid = parsed.D > 0 && parsed.S > 0 && parsed.H > 0

  useEffect(() => {
    // Reject bad input locally for instant feedback — no point round-tripping
    // a request we already know the server will refuse.
    if (!valid) {
      requestId.current++
      setResult(null)
      setMessage('Enter positive values.')
      return
    }
    // The formula itself stays server-side (single source of truth); debouncing
    // keeps it feeling live without a request per keystroke.
    const timer = setTimeout(() => calculate(parsed.D, parsed.S, parsed.H), 250)
    return () => clearTimeout(timer)
  }, [inputs, valid, parsed.D, parsed.S, parsed.H, calculate])

  const update = (field) => (event) =>
    setInputs((current) => ({ ...current, [field]: event.target.value }))

  return (
    <section className="screen">
      <TopBar subtitle="Purchase › Economic Batch Qty" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/purchase">Purchase</Link> › Economic Batch Qty
        </div>
        <button className="backbtn" onClick={() => navigate('/purchase')}>← Back to Purchase</button>

        <div className="panel">
          <h3>Economic Batch / Order Quantity (EBQ)</h3>
          <div className="formula">EBQ = √( 2 · D · S / H )</div>

          <div className="calc-grid">
            <div className="field">
              <label htmlFor="d">Annual Demand D (kg/year)</label>
              <input id="d" type="number" value={inputs.annualDemand} onChange={update('annualDemand')} />
            </div>
            <div className="field">
              <label htmlFor="s">Ordering / Setup cost S (₹ per order)</label>
              <input id="s" type="number" value={inputs.orderingCost} onChange={update('orderingCost')} />
            </div>
            <div className="field">
              <label htmlFor="h">Holding cost H (₹ per kg per year)</label>
              <input id="h" type="number" value={inputs.holdingCost} onChange={update('holdingCost')} />
            </div>
            <div className="field">
              <label>&nbsp;</label>
              <button
                className="btn-primary"
                onClick={() => valid && calculate(parsed.D, parsed.S, parsed.H)}
              >
                Calculate
              </button>
            </div>
          </div>

          <div className="result-box">
            <div className="lab">Economic Batch Quantity</div>
            <div className="val">
              {result ? `${Math.round(result.ebq).toLocaleString()} kg` : '—'}
            </div>
            <div className="foot">
              {result
                ? `≈ ${result.orders_per_year.toFixed(1)} orders/year · total order+holding cost ≈ ₹${Math.round(result.total_annual_cost).toLocaleString()}/yr`
                : message}
            </div>
          </div>

          <p className="note">
            EBQ is the order size where <b>ordering cost</b> and <b>holding cost</b> balance — the
            cheapest quantity to buy each time. D=annual usage, S=cost to place one order, H=cost to
            hold 1 kg for a year.
          </p>
        </div>
      </div>
    </section>
  )
}
