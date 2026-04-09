import { useState } from "react";

import { DealsPage } from "./pages/DealsPage";
import { PendingReviewsPage } from "./pages/PendingReviewsPage";

type Screen = "pending" | "deals";

export function App() {
  const [screen, setScreen] = useState<Screen>("pending");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-title">Deals Review Console</div>
          <div className="app-subtitle">Internal moderation workflow</div>
        </div>
        <nav className="app-nav" aria-label="Primary">
          <button
            className={screen === "pending" ? "nav-button nav-button-active" : "nav-button"}
            onClick={() => setScreen("pending")}
          >
            Pending Reviews
          </button>
          <button
            className={screen === "deals" ? "nav-button nav-button-active" : "nav-button"}
            onClick={() => setScreen("deals")}
          >
            Deals
          </button>
        </nav>
      </header>

      <main className="app-main">{screen === "pending" ? <PendingReviewsPage /> : <DealsPage />}</main>
    </div>
  );
}
