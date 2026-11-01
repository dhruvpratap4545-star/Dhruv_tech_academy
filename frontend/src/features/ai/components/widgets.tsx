import { Card } from "@/components/Card";
import { cn } from "@/lib/cn";
import { formatRupees } from "@/lib/format";

export function StatTile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <p className="eyebrow">{label}</p>
      <p className="num mt-1 font-display text-2xl font-extrabold text-fg">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-fg-2">{sub}</p>}
    </Card>
  );
}

/** Spend against a limit. Turns amber at 80% and red at 100%, the alert thresholds. */
export function BudgetBar({ percent }: { percent: number | null }) {
  const value = Math.min(100, Math.max(0, percent ?? 0));
  const tone = (percent ?? 0) >= 100 ? "bg-bad" : (percent ?? 0) >= 80 ? "bg-warn" : "bg-accent";
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className="h-2.5 w-full overflow-hidden rounded-full bg-surface-3"
    >
      <div className={cn("h-full rounded-full", tone)} style={{ width: `${value}%` }} />
    </div>
  );
}

/**
 * Thirty days of spend as inline SVG bars, in the style of `SigninChart`. A table for
 * screen readers sits underneath; the bars are decoration over it.
 */
export function TrendChart({
  days,
  caption,
}: {
  days: { day: string; requests: number; cost_paise: number }[];
  caption: string;
}) {
  const peak = Math.max(1, ...days.map((d) => d.cost_paise));
  return (
    <div>
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {days.map((d) => (
            <tr key={d.day}>
              <td>{d.day}</td>
              <td>{d.requests}</td>
              <td>{formatRupees(d.cost_paise)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div aria-hidden className="flex h-36 items-end gap-0.5">
        {days.map((d) => (
          <div
            key={d.day}
            title={`${d.day}: ${d.requests} requests, ${formatRupees(d.cost_paise)}`}
            className="flex-1 rounded-t-sm bg-accent/80 hover:bg-accent"
            style={{ height: `${Math.max(2, (d.cost_paise / peak) * 100)}%` }}
          />
        ))}
      </div>
      <div aria-hidden className="mt-1 flex justify-between text-[10px] text-fg-3">
        <span>{days[0]?.day}</span>
        <span>{days.at(-1)?.day}</span>
      </div>
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-55",
        checked ? "bg-accent" : "bg-surface-3",
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform",
          checked && "translate-x-5",
        )}
      />
    </button>
  );
}
