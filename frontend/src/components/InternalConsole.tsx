import { useState } from "react";

import { DealsPage } from "../pages/DealsPage";
import { PendingReviewsPage } from "../pages/PendingReviewsPage";
import { TrackedProductsPage } from "../pages/TrackedProductsPage";

type Screen = "pending" | "deals" | "tracked";

export function InternalConsole() {
  const [screen, setScreen] = useState<Screen>("pending");

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-title">Deals Review Console</div>
          <div className="app-subtitle">Internal moderation workflow</div>
        </div>
        <nav className="app-nav" aria-label="Internal navigation">
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
          <button
            className={screen === "tracked" ? "nav-button nav-button-active" : "nav-button"}
            onClick={() => setScreen("tracked")}
          >
            Tracked Products
          </button>
        </nav>
      </header>

      <main className="app-main">
        {screen === "pending" ? <PendingReviewsPage /> : null}
        {screen === "deals" ? <DealsPage /> : null}
        {screen === "tracked" ? <TrackedProductsPage /> : null}
      </main>
    </div>
  );
}
