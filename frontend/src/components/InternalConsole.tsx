import { useEffect, useState } from "react";

import { DealsPage } from "../pages/DealsPage";
import { PendingReviewsPage } from "../pages/PendingReviewsPage";
import { TrackedProductsPage } from "../pages/TrackedProductsPage";
import type { AuthUser } from "../types";

type Screen = "pending" | "deals" | "tracked";

function getScreenFromHash(hash: string): Screen {
  if (hash === "#deals") {
    return "deals";
  }
  if (hash === "#tracked") {
    return "tracked";
  }
  return "pending";
}

function getHashForScreen(screen: Screen): string {
  if (screen === "pending") {
    return "#pending";
  }
  return `#${screen}`;
}

type InternalConsoleProps = {
  currentUser: AuthUser;
  onLogout: () => void;
};

export function InternalConsole({ currentUser, onLogout }: InternalConsoleProps) {
  const [screen, setScreen] = useState<Screen>(() => getScreenFromHash(window.location.hash));

  useEffect(() => {
    function handleHashChange() {
      setScreen(getScreenFromHash(window.location.hash));
    }

    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function switchScreen(nextScreen: Screen) {
    setScreen(nextScreen);
    window.history.replaceState({}, "", `${window.location.pathname}${getHashForScreen(nextScreen)}`);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <div className="app-title">Deals Review Console</div>
          <div className="app-subtitle">Internal moderation workflow · {currentUser.email}</div>
        </div>
        <div className="app-header-actions">
          <nav className="app-nav" aria-label="Internal navigation">
            <button
              className={screen === "pending" ? "nav-button nav-button-active" : "nav-button"}
              onClick={() => switchScreen("pending")}
            >
              Pending Reviews
            </button>
            <button
              className={screen === "deals" ? "nav-button nav-button-active" : "nav-button"}
              onClick={() => switchScreen("deals")}
            >
              Deals
            </button>
            <button
              className={screen === "tracked" ? "nav-button nav-button-active" : "nav-button"}
              onClick={() => switchScreen("tracked")}
            >
              Tracked Products
            </button>
          </nav>
          <button type="button" className="nav-button" onClick={onLogout}>
            Logout
          </button>
        </div>
      </header>

      <main className="app-main">
        {screen === "pending" ? <PendingReviewsPage /> : null}
        {screen === "deals" ? <DealsPage /> : null}
        {screen === "tracked" ? <TrackedProductsPage /> : null}
      </main>
    </div>
  );
}
