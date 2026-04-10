import { useEffect, useMemo, useState } from "react";

import { InternalConsole } from "./components/InternalConsole";
import { PublicDealDetailPage } from "./pages/PublicDealDetailPage";
import { PublicDealsFeedPage } from "./pages/PublicDealsFeedPage";

type AppRoute =
  | { kind: "public-feed" }
  | { kind: "public-detail"; dealId: string }
  | { kind: "internal" };

function parseRoute(pathname: string): AppRoute {
  if (pathname === "/internal") {
    return { kind: "internal" };
  }

  if (pathname === "/" || pathname === "/deals") {
    return { kind: "public-feed" };
  }

  const detailMatch = pathname.match(/^\/deals\/([^/]+)$/);
  if (detailMatch) {
    return { kind: "public-detail", dealId: decodeURIComponent(detailMatch[1]) };
  }

  return { kind: "public-feed" };
}

export function App() {
  const [pathname, setPathname] = useState(() => window.location.pathname);

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  function navigate(path: string) {
    if (path === pathname) {
      return;
    }

    window.history.pushState({}, "", path);
    window.scrollTo({ top: 0, behavior: "auto" });
    setPathname(path);
  }

  const route = useMemo(() => parseRoute(pathname), [pathname]);

  if (route.kind === "internal") {
    return <InternalConsole />;
  }

  return (
    <div className="public-app-shell">
      <header className="public-header">
        <button type="button" className="public-brand" onClick={() => navigate("/")}>
          Deals
        </button>
        <nav className="public-nav" aria-label="Public navigation">
          <button
            type="button"
            className={route.kind === "public-feed" ? "public-nav-link public-nav-link-active" : "public-nav-link"}
            onClick={() => navigate("/")}
          >
            Latest deals
          </button>
        </nav>
      </header>

      <main className="public-main">
        {route.kind === "public-feed" ? (
          <PublicDealsFeedPage navigate={navigate} />
        ) : (
          <PublicDealDetailPage dealId={route.dealId} navigate={navigate} />
        )}
      </main>
    </div>
  );
}
