import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, CheckCircle2, Clock3, Info } from "lucide-react";
import { cn } from "@/lib/utils";
export function Card({
  title,
  icon: Icon,
  aside,
  children,
  className = "",
}: {
  title: string;
  icon?: LucideIcon;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("clinical-card", className)}>
      <header className="card-head">
        <h3>
          {Icon && <Icon size={17} />} {title}
        </h3>
        {aside}
      </header>
      {children}
    </section>
  );
}
export function Badge({
  children,
  tone = "neutral",
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "teal" | "amber" | "red" | "blue";
  className?: string;
}) {
  return (
    <span className={cn("status-badge", `badge-${tone}`, className)}>
      {children}
    </span>
  );
}
export function Notice({
  children,
  tone = "amber",
  title,
}: {
  children: ReactNode;
  tone?: "amber" | "red" | "teal" | "neutral";
  title?: string;
}) {
  const Icon =
    tone === "red" ? AlertTriangle : tone === "teal" ? CheckCircle2 : Info;
  return (
    <div
      className={cn("notice", `notice-${tone}`)}
      role={tone === "red" ? "alert" : undefined}
    >
      <Icon size={17} />
      <div>
        {title && <strong>{title}</strong>}
        {children}
      </div>
    </div>
  );
}
export const labels: Record<string, string> = {
  pending_clinician_review: "Draft pending review",
  edited: "Edited · pending approval",
  approved_for_documentation: "Approved for documentation",
  rejected: "Rejected",
};
export function Status({ status }: { status?: string }) {
  return (
    <Badge
      tone={
        status === "approved_for_documentation"
          ? "teal"
          : status === "rejected"
            ? "red"
            : "amber"
      }
    >
      {status === "approved_for_documentation" ? (
        <CheckCircle2 size={12} />
      ) : (
        <Clock3 size={12} />
      )}{" "}
      {status ? labels[status] || status : "Not started"}
    </Badge>
  );
}
export function formatDate(value: string) {
  if (!value) return "Not documented";
  const d = new Date(value);
  return Number.isNaN(d.valueOf())
    ? value
    : d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        timeZone: "UTC",
      });
}
