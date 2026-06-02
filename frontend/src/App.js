import React from "react";
import "./theme.css";
import "./App.css";
import ChatWindow from "./components/ChatWindow";

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
              <path
                d="M4 7.5 12 3l8 4.5v9L12 21l-8-4.5v-9Z"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinejoin="round"
              />
              <path d="m8 9.8 4 2.2 4-2.2M12 12v6.4" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
            </svg>
          </span>
          <div className="brand-text">
            <span className="brand-name">PartSelect</span>
            <span className="brand-sub">Parts Assistant</span>
          </div>
        </div>
        <div className="header-scope">Refrigerator &amp; Dishwasher</div>
      </header>
      <main className="app-main">
        <ChatWindow />
      </main>
    </div>
  );
}

export default App;
