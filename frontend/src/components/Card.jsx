/**
 * A tile on the Departments / Work Portals grids.
 *
 * Rendered as a real <button> rather than the prototype's clickable <div> so
 * it's reachable by keyboard and announced as actionable by screen readers.
 */
export default function Card({ icon, title, description, tag, onClick }) {
  return (
    <button type="button" className="card" onClick={onClick}>
      <div className="ic">{icon}</div>
      {tag && <span className={`tag ${tag.kind}`}>{tag.label}</span>}
      <h3>{title}</h3>
      <p>{description}</p>
    </button>
  )
}
