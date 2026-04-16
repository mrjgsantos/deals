type LegalPageProps = {
  page: "terms" | "privacy";
  onBack: () => void;
};

const TERMS_CONTENT = `
**Terms of Service**

Last updated: April 2026

By using Deals, you agree to these terms. We reserve the right to update them at any time.

**Use of the service**
Deals is provided for personal, non-commercial use. You may not scrape, redistribute, or resell content from this platform.

**Accounts**
You are responsible for maintaining the security of your account. We may suspend accounts that violate these terms.

**Content**
Deal prices and availability are sourced from third-party retailers and may change. We do not guarantee accuracy.

**Limitation of liability**
Deals is provided "as is". We are not liable for any loss arising from use of the service.

**Contact**
For questions, contact us at hello@deals.app.
`;

const PRIVACY_CONTENT = `
**Privacy Policy**

Last updated: April 2026

**What we collect**
We collect your email address, a hashed password, and optional display name. When you interact with deals (saves, clicks), we record those actions to personalise your experience.

**How we use it**
We use your data to provide and improve the service, and to send transactional emails (e.g. password reset, email verification). We do not sell your data.

**Cookies**
We use localStorage for authentication tokens. No third-party tracking cookies are used.

**Data retention**
You can delete your account at any time. Account deletion removes all your personal data within 30 days.

**Your rights (GDPR)**
You have the right to access, rectify, or erase your personal data. Contact us at hello@deals.app.

**Contact**
For privacy questions, contact us at hello@deals.app.
`;

function renderMarkdown(text: string) {
  return text
    .trim()
    .split("\n")
    .map((line, i) => {
      if (line.startsWith("**") && line.endsWith("**") && line.length > 4) {
        const content = line.slice(2, -2);
        return <h2 key={i} style={{ marginTop: 24, marginBottom: 8, fontSize: 18, fontWeight: 700 }}>{content}</h2>;
      }
      if (!line.trim()) return <br key={i} />;
      return <p key={i} style={{ margin: "6px 0", lineHeight: 1.6 }}>{line}</p>;
    });
}

export function LegalPage({ page, onBack }: LegalPageProps) {
  const content = page === "terms" ? TERMS_CONTENT : PRIVACY_CONTENT;

  return (
    <div className="auth-shell" style={{ alignItems: "flex-start" }}>
      <div className="auth-card" style={{ maxWidth: 640, width: "100%", marginTop: 32 }}>
        <button
          className="auth-link"
          onClick={onBack}
          style={{ marginBottom: 16, display: "block" }}
        >
          ← Back
        </button>
        <div style={{ fontSize: 15 }}>
          {renderMarkdown(content)}
        </div>
      </div>
    </div>
  );
}
