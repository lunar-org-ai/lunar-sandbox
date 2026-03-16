import type { VariantProps } from "class-variance-authority";

import { Badge, badgeVariants } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

const SANDBOX_VARIANTS: Record<string, BadgeVariant> = {
  Running: "secondary",
  Idle: "secondary",
  Starting: "secondary",
  Finished: "secondary",
  Error: "destructive",
};

const OUTCOME_VARIANTS: Record<string, BadgeVariant> = {
  pass: "secondary",
  completed: "secondary",
  fail: "destructive",
  failed: "destructive",
  error: "destructive",
  timeout: "destructive",
  running: "secondary",
  pending: "secondary",
};

interface StatusBadgeProps {
  status: string;
  type: "sandbox" | "outcome";
  className?: string;
}

export function StatusBadge({ status, type, className }: StatusBadgeProps) {
  const variant =
    type === "sandbox"
      ? (SANDBOX_VARIANTS[status] ?? "secondary")
      : (OUTCOME_VARIANTS[status.toLowerCase()] ?? "secondary");

  return (
    <Badge variant={variant} className={cn("text-xs font-medium", className)}>
      {status}
    </Badge>
  );
}
