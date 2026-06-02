import React from "react";
import "./cards.css";

function ToolIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
      <path
        d="M14.7 6.3a4 4 0 0 1-5.4 5.4l-5 5a1.8 1.8 0 0 0 2.5 2.5l5-5a4 4 0 0 0 5.4-5.4l-2 2-2-2 2-2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const diffColor = (d) => {
  const k = (d || "").toLowerCase();
  if (k.includes("easy")) return "stock-in";
  if (k.includes("hard") || k.includes("diff")) return "stock-out";
  return "rating";
};

function InstallGuide({ card }) {
  const { part, difficulty, time_estimate, tools_required = [], steps = [], video_url } = card;

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-head-icon" style={{ background: "var(--ps-teal)" }}>
          <ToolIcon />
        </span>
        <div>
          <div className="card-head-title">Installation — {part?.name || "Part"}</div>
          {part?.ps_number && <div className="card-head-sub">{part.ps_number}</div>}
        </div>
      </div>

      <div className="card-content">
        <div className="install-badges">
          {difficulty && <span className={`pill ${diffColor(difficulty)}`}>{difficulty}</span>}
          {time_estimate && <span className="pill neutral">⏱ {time_estimate}</span>}
          {video_url && (
            <a
              className="pill rating"
              href={video_url}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: "none" }}
            >
              ▶ Video guide
            </a>
          )}
        </div>

        <ol className="steps">
          {steps.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>

        {tools_required.length > 0 && (
          <div className="tools-needed">
            <b>Tools:</b> {tools_required.join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}

export default InstallGuide;
