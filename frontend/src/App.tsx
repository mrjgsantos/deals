import { useCallback, useEffect, useMemo, useState } from "react";

import { EmailVerificationBanner } from "./components/EmailVerificationBanner";
import { InternalConsole } from "./components/InternalConsole";
import {
  ApiError,
  api,
  clearStoredSession,
  getStoredAuthToken,
  getStoredAuthUser,
  storeAuthSession,
  subscribeToAuthExpired,
} from "./lib/api";
import { AuthPage } from "./pages/AuthPage";
import { LegalPage } from "./pages/LegalPage";
import { VerifyEmailPage } from "./pages/VerifyEmailPage";
import { NewDealsPage } from "./pages/NewDealsPage";
import { PreferencesOnboardingPage } from "./pages/PreferencesOnboardingPage";
import { PublicDealDetailPage } from "./pages/PublicDealDetailPage";
import { PublicDealsFeedPage } from "./pages/PublicDealsFeedPage";
import { SavedDealsPage } from "./pages/SavedDealsPage";
import type { AuthUser, NewDealsResponse, PublishedDeal, SavedDealItem, UserPreferences } from "./types";

type AppRoute =
  | { kind: "public-feed" }
  | { kind: "public-detail"; dealId: string }
  | { kind: "internal" }
  | { kind: "auth" }
  | { kind: "reset-password"; token: string }
  | { kind: "verify-email"; token: string }
  | { kind: "terms" }
  | { kind: "privacy" }
  | { kind: "saved" }
  | { kind: "new" }
  | { kind: "onboarding" };

type AuthState =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: AuthUser };

function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

function createEmptyPreferences(): UserPreferences {
  return {
    categories: [],
    budget_preference: null,
    intent: [],
    has_pets: false,
    has_kids: false,
    context_flags: {},
    category_affinity: {},
    saved_count_by_category: {},
    clicked_count_by_category: {},
    negative_affinity: {},
    is_profile_initialized: false,
  };
}

function hasInitializedProfile(preferences: UserPreferences): boolean {
  return preferences.is_profile_initialized;
}

function parseRoute(pathname: string): AppRoute {
  if (pathname === "/internal") {
    return { kind: "internal" };
  }

  if (pathname === "/login") {
    return { kind: "auth" };
  }

  if (pathname === "/reset-password") {
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    return { kind: "reset-password", token };
  }

  if (pathname === "/verify-email") {
    const token = new URLSearchParams(window.location.search).get("token") ?? "";
    return { kind: "verify-email", token };
  }

  if (pathname === "/terms") return { kind: "terms" };
  if (pathname === "/privacy") return { kind: "privacy" };

  if (pathname === "/saved") {
    return { kind: "saved" };
  }

  if (pathname === "/new") {
    return { kind: "new" };
  }

  if (pathname === "/onboarding") {
    return { kind: "onboarding" };
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
  const [authState, setAuthState] = useState<AuthState>(() => {
    const token = getStoredAuthToken();
    const storedUser = getStoredAuthUser();
    if (token && storedUser) {
      return { status: "authenticated", user: storedUser };
    }
    if (token) {
      return { status: "loading", user: null };
    }
    return { status: "anonymous", user: null };
  });
  const [savedDeals, setSavedDeals] = useState<SavedDealItem[]>([]);
  const [savedDealsLoading, setSavedDealsLoading] = useState(false);
  const [savedDealsError, setSavedDealsError] = useState<string | null>(null);
  const [pendingSaveDealIds, setPendingSaveDealIds] = useState<Set<string>>(new Set());
  const [preferences, setPreferences] = useState<UserPreferences>(createEmptyPreferences);
  const [preferencesLoading, setPreferencesLoading] = useState(false);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);
  const [preferencesSaving, setPreferencesSaving] = useState(false);
  const [newDeals, setNewDeals] = useState<NewDealsResponse>({
    new_count: 0,
    fallback_used: false,
    last_seen_at: null,
    deals: [],
  });
  const [newDealsLoading, setNewDealsLoading] = useState(false);
  const [newDealsError, setNewDealsError] = useState<string | null>(null);
  const [newDealsLoaded, setNewDealsLoaded] = useState(false);
  const [feedRefreshToken, setFeedRefreshToken] = useState(0);

  useEffect(() => {
    function handlePopState() {
      setPathname(window.location.pathname);
    }

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    return subscribeToAuthExpired(() => {
      setAuthState({ status: "anonymous", user: null });
    });
  }, []);

  useEffect(() => {
    if (authState.status !== "authenticated") {
      setSavedDeals([]);
      setSavedDealsLoading(false);
      setSavedDealsError(null);
      setPendingSaveDealIds(new Set());
      setPreferences(createEmptyPreferences());
      setPreferencesLoading(false);
      setPreferencesError(null);
      setNewDeals({ new_count: 0, fallback_used: false, last_seen_at: null, deals: [] });
      setNewDealsLoading(false);
      setNewDealsError(null);
      setNewDealsLoaded(false);
      return;
    }

    let cancelled = false;
    setSavedDealsLoading(true);
    setSavedDealsError(null);

    api
      .getSavedDeals()
      .then((items) => {
        if (!cancelled) {
          setSavedDeals(items);
        }
      })
      .catch((error) => {
        if (!cancelled && !isUnauthorizedError(error)) {
          setSavedDealsError("Could not load your saved deals.");
          console.error(error);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setSavedDealsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authState.status]);

  useEffect(() => {
    if (authState.status !== "authenticated") {
      return;
    }

    let cancelled = false;
    setNewDealsLoading(true);
    setNewDealsError(null);
    setNewDealsLoaded(false);

    api
      .getNewDeals()
      .then((items) => {
        if (!cancelled) {
          setNewDeals(items);
        }
      })
      .catch((error) => {
        if (!cancelled && !isUnauthorizedError(error)) {
          setNewDealsError("Could not load your new deals.");
          console.error(error);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setNewDealsLoading(false);
          setNewDealsLoaded(true);
        }
      });

    return () => {
      cancelled = true;
    };
  // Fires on auth transitions and once when profile initializes; backend personalizes server-side.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authState.status, preferences.is_profile_initialized]);

  useEffect(() => {
    if (authState.status !== "authenticated") {
      return;
    }

    let cancelled = false;
    setPreferencesLoading(true);
    setPreferencesError(null);

    api
      .getPreferences()
      .then((result) => {
        if (!cancelled) {
          setPreferences(result);
        }
      })
      .catch((error) => {
        if (!cancelled && !isUnauthorizedError(error)) {
          setPreferencesError("Could not load your preferences.");
          console.error(error);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPreferencesLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [authState.status]);

  useEffect(() => {
    const token = getStoredAuthToken();
    const storedUser = getStoredAuthUser();
    if (!token) {
      setAuthState({ status: "anonymous", user: null });
      return;
    }

    let cancelled = false;
    if (storedUser == null) {
      setAuthState({ status: "loading", user: null });
    }

    api
      .getCurrentUser()
      .then((user) => {
        if (!cancelled) {
          storeAuthSession(token, user);
          setAuthState({ status: "authenticated", user });
        }
      })
      .catch(() => {
        clearStoredSession();
        if (!cancelled) {
          setAuthState({ status: "anonymous", user: null });
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const navigate = useCallback((path: string) => {
    if (path === pathname) {
      return;
    }

    window.history.pushState({}, "", path);
    window.scrollTo({ top: 0, behavior: "auto" });
    setPathname(path);
  }, [pathname]);

  const route = useMemo(() => parseRoute(pathname), [pathname]);
  const savedDealIds = useMemo(() => new Set(savedDeals.map((item) => item.deal.id)), [savedDeals]);

  function applyAuthenticatedSession(payload: { accessToken: string; user: AuthUser }) {
    storeAuthSession(payload.accessToken, payload.user);
    setAuthState({ status: "authenticated", user: payload.user });
  }

  function handleInternalAuthenticated(payload: { accessToken: string; user: AuthUser }) {
    applyAuthenticatedSession(payload);
    navigate("/internal");
  }

  function handlePublicAuthenticated(payload: { accessToken: string; user: AuthUser }, mode: string) {
    applyAuthenticatedSession(payload);
    if (mode === "register") {
      navigate("/onboarding");
      return;
    }
    if (route.kind === "saved") {
      navigate("/saved");
      return;
    }
    navigate("/");
  }

  function handleLogout() {
    clearStoredSession();
    setAuthState({ status: "anonymous", user: null });
    if (route.kind === "internal") {
      navigate("/login");
      return;
    }
    if (route.kind === "saved" || route.kind === "onboarding") {
      navigate("/");
    }
  }

  function updatePendingSaveState(dealId: string, isPending: boolean) {
    setPendingSaveDealIds((current) => {
      const next = new Set(current);
      if (isPending) {
        next.add(dealId);
      } else {
        next.delete(dealId);
      }
      return next;
    });
  }

  function requestFeedRefresh() {
    setFeedRefreshToken((current) => current + 1);
  }

  async function handleToggleSavedDeal(deal: PublishedDeal) {
    if (authState.status !== "authenticated") {
      navigate("/login");
      return;
    }
    if (pendingSaveDealIds.has(deal.id)) {
      return;
    }

    const wasSaved = savedDealIds.has(deal.id);
    const previousItems = savedDeals;
    updatePendingSaveState(deal.id, true);
    setSavedDeals((current) => {
      if (wasSaved) {
        return current.filter((item) => item.deal.id !== deal.id);
      }
      return [{ saved_at: new Date().toISOString(), deal }, ...current.filter((item) => item.deal.id !== deal.id)];
    });

    try {
      if (wasSaved) {
        await api.unsaveDeal(deal.id);
      } else {
        await api.saveDeal(deal.id);
      }
      requestFeedRefresh();
    } catch (error) {
      setSavedDeals(previousItems);
      console.error(error);
    } finally {
      updatePendingSaveState(deal.id, false);
    }
  }

  async function handleSavePreferences(preferencesInput: {
    categories: string[];
    budget_preference: "low" | "medium" | "high" | null;
    intent: string[];
    has_pets: boolean;
    has_kids: boolean;
    context_flags?: Record<string, boolean>;
  }) {
    setPreferencesSaving(true);
    setPreferencesError(null);
    try {
      const result = await api.savePreferences(preferencesInput);
      setPreferences(result);
      requestFeedRefresh();
      navigate("/");
    } catch (error) {
      setPreferencesError("Could not save your preferences.");
      console.error(error);
    } finally {
      setPreferencesSaving(false);
    }
  }

  async function handleSkipPreferences() {
    await handleSavePreferences({
      categories: preferences.categories,
      budget_preference: preferences.budget_preference,
      intent: preferences.intent,
      has_pets: preferences.has_pets,
      has_kids: preferences.has_kids,
      context_flags: preferences.context_flags,
    });
  }

  const handleDealOutboundClick = useCallback((deal: PublishedDeal, context: "feed" | "recommended" = "feed") => {
    if (authState.status !== "authenticated") {
      return;
    }
    const tracker = context === "recommended" ? api.trackRecommendedDealClick : api.trackDealClick;
    void tracker(deal.id)
      .then(() => {
        requestFeedRefresh();
      })
      .catch(() => {
        // Personalization click tracking should never block navigation.
      });
  }, [authState.status]);

  const handleDealImpressions = useCallback((deals: PublishedDeal[], context: "feed" | "recommended") => {
    if (authState.status !== "authenticated" || deals.length === 0) {
      return;
    }
    void api.trackDealImpressions(
      deals.map((deal) => deal.id),
      context,
    ).catch(() => {
      // Analytics should never block the user experience.
    });
  }, [authState.status]);

  const handleFeedOutboundClick = useCallback(
    (deal: PublishedDeal) => handleDealOutboundClick(deal, "feed"),
    [handleDealOutboundClick],
  );

  const handleRecommendedOutboundClick = useCallback(
    (deal: PublishedDeal) => handleDealOutboundClick(deal, "recommended"),
    [handleDealOutboundClick],
  );

  const handleFeedImpressions = useCallback(
    (deals: PublishedDeal[]) => handleDealImpressions(deals, "feed"),
    [handleDealImpressions],
  );

  const handleRecommendedImpressions = useCallback(
    (deals: PublishedDeal[]) => handleDealImpressions(deals, "recommended"),
    [handleDealImpressions],
  );

  async function markNewDealsSeen() {
    if (authState.status !== "authenticated") {
      return;
    }

    setNewDeals((current) => ({
      ...current,
      new_count: 0,
    }));

    try {
      const result = await api.markNewDealsSeen();
      setNewDeals((current) => ({
        ...current,
        new_count: 0,
        last_seen_at: result.last_seen_at,
      }));
    } catch (error) {
      console.error(error);
      setNewDealsError("Could not mark your new deals as seen.");
    }
  }

  useEffect(() => {
    if (route.kind !== "new" || authState.status !== "authenticated" || newDealsLoading || !newDealsLoaded) {
      return;
    }
    void markNewDealsSeen();
  }, [route.kind, authState.status, newDealsLoading, newDealsLoaded]);

  if (route.kind === "internal") {
    if (authState.status === "loading") {
      return (
        <div className="auth-shell">
          <div className="auth-card auth-card-compact">
            <div className="auth-title">A verificar sessão...</div>
          </div>
        </div>
      );
    }
    if (authState.status !== "authenticated") {
      return (
        <AuthPage
          title="Internal sign in"
          subtitle="Sign in to access the review console."
          onAuthenticated={(payload) => handleInternalAuthenticated(payload)}
        />
      );
    }
    if (!authState.user.is_staff) {
      return (
        <div className="auth-shell">
          <div className="auth-card" style={{ textAlign: "center" }}>
            <div className="auth-eyebrow">Acesso negado</div>
            <h1 className="auth-title" style={{ marginBottom: 12 }}>Sem permissão</h1>
            <p className="auth-copy" style={{ marginBottom: 24 }}>
              A tua conta não tem acesso à consola interna.
            </p>
            <button className="auth-submit" onClick={() => navigate("/")}>
              Voltar aos deals
            </button>
          </div>
        </div>
      );
    }
    return <InternalConsole currentUser={authState.user} onLogout={handleLogout} />;
  }

  if (route.kind === "reset-password") {
    return (
      <AuthPage
        initialMode="reset"
        resetToken={route.token}
        onAuthenticated={handlePublicAuthenticated}
      />
    );
  }

  if (route.kind === "verify-email") {
    return <VerifyEmailPage token={route.token} onDone={() => navigate("/")} />;
  }

  if (route.kind === "terms") {
    return <LegalPage page="terms" onBack={() => window.history.back()} />;
  }

  if (route.kind === "privacy") {
    return <LegalPage page="privacy" onBack={() => window.history.back()} />;
  }

  if (route.kind === "auth") {
    if (authState.status === "authenticated") {
      if (!preferencesLoading && !hasInitializedProfile(preferences)) {
        return (
          <PreferencesOnboardingPage
            initialPreferences={preferences}
            isSaving={preferencesSaving}
            error={preferencesError}
            onSave={handleSavePreferences}
            onSkip={() => void handleSkipPreferences()}
          />
        );
      }
      return (
        <div className="public-app-shell">
          <header className="public-header">
            <div className="public-header-left">
              <button type="button" className="public-brand" onClick={() => navigate("/")}>Deals</button>
            </div>
            <nav className="public-nav" aria-label="Public navigation">
              <button type="button" className="public-nav-link" onClick={() => navigate("/")}>Deals</button>
              <button type="button" className="public-nav-link public-nav-link-active" onClick={() => navigate("/saved")}>Guardados</button>
              <button type="button" className="public-nav-link" onClick={handleLogout}>Sair</button>
            </nav>
          </header>

          <main className="public-main">
            <SavedDealsPage
              items={savedDeals}
              isLoading={savedDealsLoading}
              error={savedDealsError}
              navigate={navigate}
              savedDealIds={savedDealIds}
              pendingDealIds={pendingSaveDealIds}
              onToggleSave={handleToggleSavedDeal}
            />
          </main>
        </div>
      );
    }
    return <AuthPage onAuthenticated={handlePublicAuthenticated} />;
  }

  if (route.kind === "saved") {
    if (authState.status === "loading") {
      return (
        <div className="auth-shell">
          <div className="auth-card auth-card-compact">
            <div className="auth-title">A verificar sessão...</div>
          </div>
        </div>
      );
    }
    if (authState.status !== "authenticated") {
      return (
        <AuthPage
          title="Guarda os teus deals favoritos"
          subtitle="Inicia sessão para guardar os deals que queres revisitar."
          onAuthenticated={handlePublicAuthenticated}
        />
      );
    }
    if (!preferencesLoading && !hasInitializedProfile(preferences)) {
      return (
        <PreferencesOnboardingPage
          initialPreferences={preferences}
          isSaving={preferencesSaving}
          error={preferencesError}
          onSave={handleSavePreferences}
          onSkip={() => void handleSkipPreferences()}
        />
      );
    }
    return (
      <div className="public-app-shell">
        <header className="public-header">
          <div className="public-header-left">
            <button type="button" className="public-brand" onClick={() => navigate("/")}>Deals</button>
          </div>
          <nav className="public-nav" aria-label="Public navigation">
            <button type="button" className="public-nav-link" onClick={() => navigate("/")}>Deals</button>
            <button type="button" className="public-nav-link public-nav-link-active" onClick={() => navigate("/saved")}>Guardados</button>
            <button type="button" className="public-nav-link" onClick={handleLogout}>Sair</button>
          </nav>
        </header>

        <main className="public-main">
          <SavedDealsPage
            items={savedDeals}
            isLoading={savedDealsLoading}
            error={savedDealsError}
            navigate={navigate}
            savedDealIds={savedDealIds}
            pendingDealIds={pendingSaveDealIds}
            onToggleSave={handleToggleSavedDeal}
          />
        </main>
      </div>
    );
  }

  if (route.kind === "new") {
    if (authState.status === "loading") {
      return (
        <div className="auth-shell">
          <div className="auth-card auth-card-compact">
            <div className="auth-title">A verificar sessão...</div>
          </div>
        </div>
      );
    }
    if (authState.status !== "authenticated") {
      return (
        <AuthPage
          title="Novidades para ti"
          subtitle="Inicia sessão para ver o que é novo desde a tua última visita."
          onAuthenticated={handlePublicAuthenticated}
        />
      );
    }
    if (!preferencesLoading && !hasInitializedProfile(preferences)) {
      return (
        <PreferencesOnboardingPage
          initialPreferences={preferences}
          isSaving={preferencesSaving}
          error={preferencesError}
          onSave={handleSavePreferences}
          onSkip={() => void handleSkipPreferences()}
        />
      );
    }
    return (
      <div className="public-app-shell">
        <header className="public-header">
          <div className="public-header-left">
            <button type="button" className="public-brand" onClick={() => navigate("/")}>Deals</button>
          </div>
          <nav className="public-nav" aria-label="Public navigation">
            <button type="button" className="public-nav-link" onClick={() => navigate("/")}>Deals</button>
            <button type="button" className="public-nav-link public-nav-link-active" onClick={() => navigate("/new")}>
              Para ti
              {newDeals.new_count > 0 ? <span className="public-nav-pill">{newDeals.new_count}</span> : null}
            </button>
            <button type="button" className="public-nav-link" onClick={() => navigate("/saved")}>Guardados</button>
            <button type="button" className="public-nav-link" onClick={handleLogout}>Sair</button>
          </nav>
        </header>

        <main className="public-main">
          <NewDealsPage
            deals={newDeals.deals}
            newCount={newDeals.new_count}
            fallbackUsed={newDeals.fallback_used}
            lastSeenAt={newDeals.last_seen_at}
            isLoading={newDealsLoading}
            error={newDealsError}
            navigate={navigate}
            savedDealIds={savedDealIds}
            pendingDealIds={pendingSaveDealIds}
            onToggleSave={handleToggleSavedDeal}
            onOutboundClick={handleRecommendedOutboundClick}
            onImpression={handleRecommendedImpressions}
            preferences={preferences}
          />
        </main>
      </div>
    );
  }

  if (route.kind === "onboarding") {
    if (authState.status === "loading" || preferencesLoading) {
      return (
        <div className="auth-shell">
          <div className="auth-card auth-card-compact">
            <div className="auth-title">A carregar preferências...</div>
          </div>
        </div>
      );
    }
    if (authState.status !== "authenticated") {
      return (
        <AuthPage
          title="Personaliza o teu feed"
          subtitle="Inicia sessão para escolher os tipos de deals que queres ver primeiro."
          onAuthenticated={handlePublicAuthenticated}
        />
      );
    }
    return (
      <PreferencesOnboardingPage
        initialPreferences={preferences}
        isSaving={preferencesSaving}
        error={preferencesError}
        onSave={handleSavePreferences}
        onSkip={() => void handleSkipPreferences()}
      />
    );
  }

  const shouldShowOnboarding =
    authState.status === "authenticated" &&
    !preferencesLoading &&
    !hasInitializedProfile(preferences) &&
    route.kind === "public-feed";

  if (shouldShowOnboarding) {
    return (
      <PreferencesOnboardingPage
        initialPreferences={preferences}
        isSaving={preferencesSaving}
        error={preferencesError}
        onSave={handleSavePreferences}
        onSkip={() => void handleSkipPreferences()}
      />
    );
  }

  return (
    <div className="public-app-shell">
      <header className="public-header">
        <div className="public-header-left">
          {route.kind === "public-detail" ? (
            <button type="button" className="public-back-nav-btn" onClick={() => navigate("/")}>
              ← Deals
            </button>
          ) : (
            <button type="button" className="public-brand" onClick={() => navigate("/")}>
              Deals
            </button>
          )}
        </div>
        <nav className="public-nav" aria-label="Public navigation">
          {route.kind !== "public-detail" ? (
            <button
              type="button"
              className={route.kind === "public-feed" ? "public-nav-link public-nav-link-active" : "public-nav-link"}
              onClick={() => navigate("/")}
            >
              Deals
            </button>
          ) : null}
          {authState.status === "authenticated" ? (
            <button
              type="button"
              className="public-nav-link"
              onClick={() => navigate("/new")}
            >
              Para ti
              {newDeals.new_count > 0 ? <span className="public-nav-pill">{newDeals.new_count}</span> : null}
            </button>
          ) : null}
          <button
            type="button"
            className="public-nav-link"
            onClick={() => navigate("/saved")}
          >
            Guardados
          </button>
          {authState.status === "authenticated" ? (
            <button type="button" className="public-nav-link" onClick={handleLogout}>
              Sair
            </button>
          ) : (
            <button type="button" className="public-nav-link public-nav-link-cta" onClick={() => navigate("/login")}>
              Entrar
            </button>
          )}
        </nav>
      </header>

      {authState.status === "authenticated" && !authState.user.email_verified ? (
        <EmailVerificationBanner email={authState.user.email} />
      ) : null}

      <main className="public-main">
        {route.kind === "public-feed" ? (
          <PublicDealsFeedPage
            navigate={navigate}
            savedDealIds={savedDealIds}
            pendingDealIds={pendingSaveDealIds}
            onToggleSave={handleToggleSavedDeal}
            onOutboundClick={handleFeedOutboundClick}
            onImpression={handleFeedImpressions}
            preferences={authState.status === "authenticated" ? preferences : null}
            refreshToken={feedRefreshToken}
          />
        ) : (
          <PublicDealDetailPage
            dealId={route.dealId}
            navigate={navigate}
            isSaved={savedDealIds.has(route.dealId)}
            isSavePending={pendingSaveDealIds.has(route.dealId)}
            onToggleSave={handleToggleSavedDeal}
            onOutboundClick={handleDealOutboundClick}
          />
        )}
      </main>
    </div>
  );
}
