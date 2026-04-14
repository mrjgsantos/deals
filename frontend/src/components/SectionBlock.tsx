import type { ReactNode } from "react";

export function SectionBlock({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <section className="d-section">
      <div className="d-section-header">
        <div>
          <h2 className="d-section-title">{title}</h2>
          {subtitle ? <p className="d-section-subtitle">{subtitle}</p> : null}
        </div>
        {action ? (
          <button type="button" className="d-section-action" onClick={action.onClick}>
            {action.label} →
          </button>
        ) : null}
      </div>
      {children}
    </section>
  );
}
