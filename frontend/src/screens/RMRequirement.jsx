import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import TopBar from '../components/TopBar'

const fmt = (value) => Number(value).toLocaleString()

export default function RMRequirement() {
  const navigate = useNavigate()
  const [materials, setMaterials] = useState([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.rawMaterials()
      .then(setMaterials)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <section className="screen">
      <TopBar subtitle="Purchase › RM Requirement" />
      <div className="wrap">
        <div className="crumbs">
          <Link to="/departments">Home</Link> › <Link to="/purchase">Purchase</Link> › RM Requirement
        </div>
        <button className="backbtn" onClick={() => navigate('/purchase')}>← Back to Purchase</button>

        <div className="panel">
          <h3>Raw Material — Requirement to Purchase</h3>

          {loading && <div className="loading">Loading raw materials…</div>}
          {error && <div className="login-error">{error}</div>}

          {!loading && !error && (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Raw Material</th>
                    <th className="num">On Hand (kg)</th>
                    <th className="num">Reorder Level</th>
                    <th className="num">Reorder Qty</th>
                    <th className="num">To Purchase (kg)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {materials.map((material) => (
                    <tr key={material.id}>
                      <td>{material.name}</td>
                      <td className="num">{fmt(material.on_hand)}</td>
                      <td className="num">{fmt(material.reorder_level)}</td>
                      <td className="num">{fmt(material.reorder_qty)}</td>
                      <td className="num">
                        <b>{material.needs_purchase ? fmt(material.to_purchase) : '—'}</b>
                      </td>
                      <td>
                        <span className={`pill ${material.needs_purchase ? 'buy' : 'ok'}`}>
                          {material.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className="note">
            Rule shown: if <b>On Hand ≤ Reorder Level</b> → purchase the Reorder Qty; else nothing.
            In the real app these numbers come straight from the TCS iON stock export. This is the
            logic layer where an LPP/EBQ engine would plug in.
          </p>
        </div>
      </div>
    </section>
  )
}
