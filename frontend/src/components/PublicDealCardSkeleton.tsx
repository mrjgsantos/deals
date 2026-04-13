export function PublicDealCardSkeleton() {
  return (
    <article className="public-card public-card-skeleton" aria-hidden="true">
      <div className="public-card-topline">
        <div className="badge-cluster badge-cluster-wrap">
          <span className="skeleton-pill skeleton-block" />
          <span className="skeleton-pill skeleton-block" />
        </div>
        <span className="skeleton-meta skeleton-block" />
      </div>

      <div className="skeleton-title skeleton-block" />
      <div className="skeleton-title skeleton-block skeleton-title-short" />

      <div className="public-price-block">
        <span className="skeleton-badge skeleton-block" />
        <span className="skeleton-price skeleton-block" />
        <span className="skeleton-copy skeleton-block" />
      </div>

      <div className="skeleton-copy skeleton-block" />
      <div className="skeleton-copy skeleton-block skeleton-copy-short" />

      <div className="public-card-footer">
        <div className="public-card-source">
          <span className="skeleton-copy skeleton-block skeleton-copy-medium" />
          <span className="skeleton-copy skeleton-block skeleton-copy-short" />
        </div>
        <div className="public-card-actions">
          <span className="skeleton-button skeleton-block" />
          <span className="skeleton-button skeleton-block skeleton-button-primary" />
        </div>
      </div>
    </article>
  );
}
