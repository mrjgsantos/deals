import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { AuthUser } from "../types";

type AuthMode = "login" | "register";

type AuthPageProps = {
  initialMode?: AuthMode;
  title?: string;
  subtitle?: string;
  onAuthenticated: (payload: { accessToken: string; user: AuthUser }, mode: AuthMode) => void;
};

export function AuthPage({
  initialMode = "login",
  title = "Internal access",
  subtitle = "Sign in to review deals and monitor tracked products.",
  onAuthenticated,
}: AuthPageProps) {
  const [mode, setMode] = useState<AuthMode>(initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const googleButtonRef = useRef<HTMLDivElement | null>(null);
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() ?? "";
  const showGoogle = googleClientId.length > 0;

  const submitting = isSubmitting || isGoogleSubmitting;

  useEffect(() => {
    if (!showGoogle || googleButtonRef.current == null) {
      return;
    }

    let cancelled = false;
    const scriptId = "google-identity-services";

    function renderGoogleButton() {
      if (cancelled || googleButtonRef.current == null || window.google == null) {
        return;
      }

      googleButtonRef.current.innerHTML = "";
      window.google.accounts.id.initialize({
        client_id: googleClientId,
        callback: (response) => {
          const credential = response.credential?.trim();
          if (!credential) {
            setError("Google sign-in did not return a usable identity token.");
            return;
          }

          setIsGoogleSubmitting(true);
          setError(null);

          api
            .googleLogin(credential)
            .then((result) => {
              onAuthenticated(
                {
                  accessToken: result.access_token,
                  user: result.user,
                },
                result.is_new_user ? "register" : "login",
              );
            })
            .catch((submissionError) => {
              setError(
                getApiErrorMessage(submissionError, "Unable to continue with Google right now.", {
                  401: "Google sign-in could not be verified.",
                  409: "This Google account conflicts with an existing sign-in method.",
                  503: "Google sign-in is not configured yet.",
                }),
              );
            })
            .finally(() => {
              setIsGoogleSubmitting(false);
            });
        },
      });
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: "outline",
        size: "large",
        shape: "pill",
        text: "continue_with",
        width: 320,
      });
    }

    const existingScript = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (existingScript != null) {
      if (window.google != null) {
        renderGoogleButton();
      } else {
        existingScript.addEventListener("load", renderGoogleButton, { once: true });
      }
      return () => {
        cancelled = true;
      };
    }

    const script = document.createElement("script");
    script.id = scriptId;
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.addEventListener("load", renderGoogleButton, { once: true });
    document.head.appendChild(script);

    return () => {
      cancelled = true;
    };
  }, [googleClientId, onAuthenticated, showGoogle]);

  const authSubtitle = useMemo(() => {
    if (!showGoogle) {
      return subtitle;
    }
    return `${subtitle} Or continue with Google.`;
  }, [showGoogle, subtitle]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const result = mode === "register" ? await api.register(email, password) : await api.login(email, password);
      onAuthenticated(
        {
          accessToken: result.access_token,
          user: result.user,
        },
        mode,
      );
    } catch (submissionError) {
      const fallback = mode === "register" ? "Unable to create your account right now." : "Unable to sign in right now.";
      const byStatus =
        mode === "register"
          ? {
              409: "That email is already registered.",
            }
          : {
              401: "Email or password is incorrect.",
            };
      setError(getApiErrorMessage(submissionError, fallback, byStatus));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-eyebrow">Deals</div>
          <h1 className="auth-title">{title}</h1>
          <p className="auth-copy">{authSubtitle}</p>
        </div>

        <div className="auth-toggle" role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            className={mode === "login" ? "auth-toggle-button auth-toggle-button-active" : "auth-toggle-button"}
            onClick={() => setMode("login")}
          >
            Login
          </button>
          <button
            type="button"
            className={mode === "register" ? "auth-toggle-button auth-toggle-button-active" : "auth-toggle-button"}
            onClick={() => setMode("register")}
          >
            Register
          </button>
        </div>

        {showGoogle ? (
          <div className="auth-google-section">
            <div ref={googleButtonRef} className="auth-google-button" />
            <div className="auth-divider" aria-hidden="true">
              <span>or use email</span>
            </div>
          </div>
        ) : null}

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Email</span>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@example.com"
              required
            />
          </label>

          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="At least 8 characters"
              minLength={8}
              required
            />
          </label>

          {error ? <div className="auth-error">{error}</div> : null}

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting ? "Working..." : mode === "register" ? "Create account" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
