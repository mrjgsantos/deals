export function EmptyStatePanel({
  title,
  detail,
  actionLabel,
  onAction,
}: {
  title: string;
  detail: string;
  actionLabel: string;
  onAction: () => void;
}) {
  return (
    <div className="empty-state-panel" role="status">
      <div className="empty-state-title">{title}</div>
      <div className="empty-state-detail">{detail}</div>
      <button type="button" className="secondary-button" onClick={onAction}>
        {actionLabel}
      </button>
    </div>
  );
}
