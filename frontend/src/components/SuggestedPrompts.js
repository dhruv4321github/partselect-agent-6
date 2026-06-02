import React from "react";
import "./SuggestedPrompts.css";

function SuggestedPrompts({ prompts, onPick, title, compact }) {
  if (!prompts || prompts.length === 0) return null;
  return (
    <div className={`suggest ${compact ? "compact" : ""}`}>
      {title && <div className="suggest-title">{title}</div>}
      <div className="suggest-chips">
        {prompts.map((p, i) => (
          <button key={i} className="chip" onClick={() => onPick(p)}>
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

export default SuggestedPrompts;
