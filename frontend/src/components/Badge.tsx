import { toSentenceCase } from "../lib/format";

type BadgeTone = "neutral" | "success" | "danger" | "warning";

const toneClassName: Record<BadgeTone, string> = {
  neutral: "badge badge-neutral",
  success: "badge badge-success",
  danger: "badge badge-danger",
  warning: "badge badge-warning",
};

export function Badge({
  value,
  tone = "neutral",
}: {
  value: string | boolean;
  tone?: BadgeTone;
}) {
  return <span className={toneClassName[tone]}>{typeof value === "boolean" ? String(value) : toSentenceCase(value)}</span>;
}
