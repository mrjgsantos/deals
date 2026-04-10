import { useEffect, useState } from "react";

import { DealsPage } from "../pages/DealsPage";
import { PendingReviewsPage } from "../pages/PendingReviewsPage";
import { TrackedProductsPage } from "../pages/TrackedProductsPage";

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

export function InternalConsole() {
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
          <div className="app-subtitle">Internal moderation workflow</div>
        </div>
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
      </header>

      <main className="app-main">
        {screen === "pending" ? <PendingReviewsPage /> : null}
        {screen === "deals" ? <DealsPage /> : null}
        {screen === "tracked" ? <TrackedProductsPage /> : null}
      </main>
    </div>
  );
}
