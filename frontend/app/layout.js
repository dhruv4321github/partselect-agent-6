import "../src/theme.css";
import "../src/App.css";

export const metadata = {
  title: "PartSelect Assistant",
  description:
    "PartSelect parts assistant — find, verify, and install Refrigerator and Dishwasher parts.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <meta name="theme-color" content="#337778" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body suppressHydrationWarning>
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
                  <path
                    d="m8 9.8 4 2.2 4-2.2M12 12v6.4"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinejoin="round"
                  />
                </svg>
              </span>
              <div className="brand-text">
                <span className="brand-name">PartSelect</span>
                <span className="brand-sub">Parts Assistant</span>
              </div>
            </div>
            <div className="header-scope">Refrigerator &amp; Dishwasher</div>
          </header>
          <main className="app-main">{children}</main>
        </div>
      </body>
    </html>
  );
}
