import React from "react";
import "./cards.css";

function DiagnosisCard({ card, onSuggestion }) {
  const { model_number, symptom, parts = [] } = card;

  return (
    <div className="card diagnosis-card">
      <div className="card-head">
        <div className="card-head-icon" style={{ background: "var(--ps-teal)" }}>🔍</div>
        <div>
          <div className="card-head-title">{symptom}</div>
          <div className="card-head-sub">Model {model_number} — parts ranked by fix likelihood</div>
        </div>
      </div>
      <div className="card-content">
        {parts.map((p, i) => (
          <div className="diag-part" key={p.ps_number || i}>
            <div className="diag-rank">{i + 1}</div>
            <div className="diag-info">
              <div className="diag-name">{p.name}</div>
              <div className="diag-meta">
                <span className="ps">{p.ps_number}</span>
                {p.mfr_number && <span> · {p.mfr_number}</span>}
              </div>
            </div>
            <div className="diag-stats">
              <div className="diag-pct">{p.fix_pct}%</div>
              <div className="diag-pct-label">fix rate</div>
            </div>
            <div className="diag-price-col">
              {p.price ? <span className="diag-price">${Number(p.price).toFixed(2)}</span> : null}
              <span className={`pill ${p.in_stock ? "stock-in" : "stock-out"}`}>
                {p.in_stock ? "In Stock" : "Out of Stock"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default DiagnosisCard;
