import React from "react";
import "./ModelPin.css";

function ModelPin({ model, onClear }) {
  return (
    <div className="model-pin">
      <span className="model-pin-label">Your model</span>
      <span className="model-pin-value">{model}</span>
      <button className="model-pin-clear" onClick={onClear} aria-label="Clear model">
        ✕
      </button>
    </div>
  );
}

export default ModelPin;
