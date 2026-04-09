export function StatusMessage({
  tone,
  title,
  detail,
}: {
  tone: "error" | "success" | "info";
  title: string;
  detail?: string;
}) {
  return (
    <div className={`status-message status-message-${tone}`} role="status">
      <div className="status-message-title">{title}</div>
      {detail ? <div className="status-message-detail">{detail}</div> : null}
    </div>
  );
}
