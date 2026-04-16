import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { AuthUser } from "../types";

type AuthMode = "login" | "register" | "forgot" | "reset";

type AuthPageProps = {
  initialMode?: AuthMode;
  title?: string;
  subtitle?: string;
  resetToken?: string;
  onAuthenticated: (payload: { accessToken: string; user: AuthUser }, mode: AuthMode) => void;
};

export function AuthPage({
  initialMode = "login",
  title = "Welcome back",
  subtitle = "Sign in to see today's best deals.",
  resetToken,
  onAuthenticated,
}: AuthPageProps) {
  const [mode, setMode] = useState<AuthMode>(resetToken ? "reset" : initialMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isGoogleSubmitting, setIsGoogleSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const googleButtonRef = useRef<HTMLDivElement | null>(null);
  const googleClientId = import.meta.env.VITE_GOOGLE_CLIENT_ID?.trim() ?? "";
  const showGoogle = googleClientId.length > 0 && (mode === "login" || mode === "register");

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
    if (mode === "forgot") return "Enter your email and we'll send you a reset link.";
    if (mode === "reset") return "Choose a new password for your account.";
    if (!showGoogle) return subtitle;
    return `${subtitle} Or continue with Google.`;
  }, [mode, showGoogle, subtitle]);

  const headingTitle = useMemo(() => {
    if (mode === "forgot") return "Forgot password";
    if (mode === "reset") return "Reset password";
    return title;
  }, [mode, title]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setSuccessMessage(null);

    try {
      if (mode === "forgot") {
        await api.forgotPassword(email);
        setSuccessMessage("If that email is registered, you'll receive a reset link shortly.");
        setEmail("");
        return;
      }

      if (mode === "reset") {
        await api.resetPassword(resetToken ?? "", newPassword);
        setSuccessMessage("Password updated. You can now sign in.");
        setMode("login");
        return;
      }

      const result = mode === "register" ? await api.register(email, password) : await api.login(email, password);
      onAuthenticated({ accessToken: result.access_token, user: result.user }, mode);
    } catch (submissionError) {
      const messages: Record<AuthMode, string> = {
        register: "Unable to create your account right now.",
        login: "Unable to sign in right now.",
        forgot: "Unable to send the reset link right now.",
        reset: "Unable to reset your password right now.",
      };
      const byStatus: Record<AuthMode, Record<number, string>> = {
        register: { 409: "That email is already registered." },
        login: { 401: "Email or password is incorrect." },
        forgot: {},
        reset: { 400: "This reset link is invalid or has already been used." },
      };
      setError(getApiErrorMessage(submissionError, messages[mode], byStatus[mode]));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-eyebrow">Deals</div>
          <h1 className="auth-title">{headingTitle}</h1>
          <p className="auth-copy">{authSubtitle}</p>
        </div>

        {mode !== "forgot" && mode !== "reset" ? (
          <div className="auth-toggle" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              className={mode === "login" ? "auth-toggle-button auth-toggle-button-active" : "auth-toggle-button"}
              onClick={() => { setMode("login"); setError(null); setSuccessMessage(null); }}
            >
              Login
            </button>
            <button
              type="button"
              className={mode === "register" ? "auth-toggle-button auth-toggle-button-active" : "auth-toggle-button"}
              onClick={() => { setMode("register"); setError(null); setSuccessMessage(null); }}
            >
              Register
            </button>
          </div>
        ) : null}

        {showGoogle ? (
          <div className="auth-google-section">
            <div ref={googleButtonRef} className="auth-google-button" />
            <div className="auth-divider" aria-hidden="true">
              <span>or use email</span>
            </div>
          </div>
        ) : null}

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode !== "reset" ? (
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
          ) : null}

          {mode === "login" || mode === "register" ? (
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
          ) : null}

          {mode === "reset" ? (
            <label className="auth-field">
              <span>New password</span>
              <input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
                placeholder="At least 8 characters"
                minLength={8}
                required
              />
            </label>
          ) : null}

          {error ? <div className="auth-error">{error}</div> : null}
          {successMessage ? <div className="auth-success">{successMessage}</div> : null}

          <button type="submit" className="auth-submit" disabled={submitting}>
            {submitting
              ? "Working..."
              : mode === "register"
                ? "Create account"
                : mode === "forgot"
                  ? "Send reset link"
                  : mode === "reset"
                    ? "Set new password"
                    : "Sign in"}
          </button>

          {mode === "login" ? (
            <button
              type="button"
              className="auth-link"
              onClick={() => { setMode("forgot"); setError(null); setSuccessMessage(null); }}
            >
              Forgot password?
            </button>
          ) : mode === "forgot" ? (
            <button
              type="button"
              className="auth-link"
              onClick={() => { setMode("login"); setError(null); setSuccessMessage(null); }}
            >
              Back to sign in
            </button>
          ) : null}
        </form>
      </div>
    </div>
  );
}
