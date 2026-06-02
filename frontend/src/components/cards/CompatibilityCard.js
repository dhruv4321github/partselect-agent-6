import React from "react";
import "./cards.css";
import ProductCard from "./ProductCard";

function CompatibilityCard({ card, onSuggestion, onPinModel }) {
  const { compatible, model_known, model_number, reason, alternative } = card;

  // Three-state verdict: yes / no / unknown (model not in catalog).
  const state = compatible === true ? "yes" : compatible === false ? "no" : "unknown";
  const label = state === "yes" ? "✓" : state === "no" ? "✕" : "?";
  const heading =
    state === "yes"
      ? "Compatible"
      : state === "no"
      ? "Not compatible"
      : "Couldn't confirm";

  return (
    <div className={`card compat ${state}`}>
      <div className="compat-verdict">
        <span className={`verdict-badge ${state}`}>{label}</span>
        <div>
          <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 2 }}>{heading}</div>
          <div className="verdict-text">{reason}</div>
        </div>
      </div>

      {state === "no" && alternative && (
        <div className="compat-alt">
          <div className="compat-alt-label">A part that fits {model_number} instead</div>
          <ProductCard card={alternative} onSuggestion={onSuggestion} />
        </div>
      )}

      {!model_known && model_number && onPinModel && (
        <div className="compat-alt">
          <div className="compat-alt-label">Don't see your model in our data?</div>
          <button className="btn btn-ghost" onClick={() => onPinModel(model_number)}>
            Pin {model_number} to this chat
          </button>
        </div>
      )}
    </div>
  );
}

export default CompatibilityCard;
