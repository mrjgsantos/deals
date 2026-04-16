import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Props = {
  token: string;
  onDone: () => void;
};

export function VerifyEmailPage({ token, onDone }: Props) {
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    api
      .verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="auth-header">
          <div className="auth-eyebrow">Deals</div>
          {status === "loading" && <h1 className="auth-title">Verifying your email…</h1>}
          {status === "success" && (
            <>
              <h1 className="auth-title">Email verified</h1>
              <p className="auth-copy">Your email is confirmed. You're all set.</p>
              <button className="auth-submit" style={{ marginTop: 16 }} onClick={onDone}>
                Go to deals
              </button>
            </>
          )}
          {status === "error" && (
            <>
              <h1 className="auth-title">Link invalid</h1>
              <p className="auth-copy">This verification link has expired or already been used.</p>
              <button className="auth-submit" style={{ marginTop: 16 }} onClick={onDone}>
                Back to deals
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
