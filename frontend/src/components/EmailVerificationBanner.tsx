import { useState } from "react";
import { api } from "../lib/api";

type Props = {
  email: string;
};

export function EmailVerificationBanner({ email }: Props) {
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

  async function handleResend() {
    setSending(true);
    try {
      await api.resendVerification();
      setSent(true);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="email-verification-banner">
      <span>
        Please verify your email address (<strong>{email}</strong>).
      </span>
      {sent ? (
        <span className="email-verification-banner-sent">Link sent!</span>
      ) : (
        <button
          className="email-verification-banner-btn"
          onClick={handleResend}
          disabled={sending}
        >
          {sending ? "Sending…" : "Resend link"}
        </button>
      )}
    </div>
  );
}
