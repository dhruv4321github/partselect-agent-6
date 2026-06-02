import React from "react";
import "./cards.css";

function WrenchIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
      <path
        d="M9 3a5 5 0 0 0 6 6l4 4a2.5 2.5 0 0 1-3.5 3.5l-4-4a5 5 0 0 1-6-6l2.5 2.5L11 6 8.5 3.5 9 3Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function RepairHelp({ card, onSuggestion }) {
  const { appliance_type, symptom, overview, causes = [], quick_checks = [] } = card;

  const ask = (q) => onSuggestion && onSuggestion(q);

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-head-icon" style={{ background: "var(--warn)" }}>
          <WrenchIcon />
        </span>
        <div>
          <div className="card-head-title">{symptom}</div>
          <div className="card-head-sub">{appliance_type} troubleshooting</div>
        </div>
      </div>

      <div className="card-content">
        {overview && <div className="repair-overview">{overview}</div>}

        {causes.map((c, i) => (
          <div className="cause" key={i}>
            <div className="cause-title">
              <span className="cause-rank">{i + 1}</span>
              {c.title}
            </div>
            {c.detail && <div className="cause-detail">{c.detail}</div>}
            {c.parts && c.parts.length > 0 && (
              <div className="cause-parts">
                {c.parts.map((p, j) => (
                  <button
                    key={j}
                    className="part-chip"
                    onClick={() => ask(`Tell me about ${p.ps_number || p}`)}
                    title={p.name || ""}
                  >
                    {p.name ? `${p.name} · ${p.ps_number}` : p.ps_number || p}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {quick_checks.length > 0 && (
          <div className="quick-checks">
            <div className="quick-checks-title">Quick checks first</div>
            <ul>
              {quick_checks.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export default RepairHelp;
