import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import { Spinner } from "@/components/Spinner";
import { fetchSigninStats, statsKeys } from "@/features/admin/api";
import type { DailySignins } from "@/features/auth/types";
import { cn } from "@/lib/cn";

const DAYS = 14;

/**
 * Daily sign-ins, drawn as inline SVG.
 *
 * No chart library. This is one series of fourteen bars; a charting dependency would add
 * more to the bundle than the whole rest of this page and bring a styling system that
 * fights the one we have. Not a trade worth making for forty lines of `<rect>`.
 *
 * The numbers are real and scoped by the server: platform staff see the whole platform,
 * an institute admin sees their own institute only.
 */
export function SigninChart() {
  const stats = useQuery({
    queryKey: statsKeys.signins(DAYS),
    queryFn: ({ signal }) => fetchSigninStats(DAYS, signal),
  });

  if (stats.isLoading) {
    return (
      <Card className="flex h-56 items-center justify-center">
        <Spinner />
      </Card>
    );
  }
  if (stats.error || !stats.data) return null;

  const days = stats.data.days;
  const peak = Math.max(1, ...days.map((d) => d.successful + d.failed));
  const today = days.at(-1);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line p-4">
        <div>
          <h2 className="font-display text-base font-bold text-fg">Daily sign-ins</h2>
          <p className="mt-0.5 text-sm text-fg-2">
            Last {DAYS} days, in your scope. Failed attempts are shown above each bar.
          </p>
        </div>
        <Badge tone="accent">
          <span className="num">{today?.successful ?? 0}</span> today
        </Badge>
      </div>

      <div className="p-4">
        {/* A table for screen readers; the bars are decoration over it. A chart that is
            only a picture is a chart half the audience cannot read. */}
        <div className="sr-only">
          <table>
            <caption>Sign-ins per day for the last {DAYS} days</caption>
            <thead>
              <tr>
                <th>Day</th>
                <th>Successful</th>
                <th>Failed</th>
              </tr>
            </thead>
            <tbody>
              {days.map((day) => (
                <tr key={day.day}>
                  <td>{day.day}</td>
                  <td>{day.successful}</td>
                  <td>{day.failed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div aria-hidden className="flex h-40 items-end gap-1">
          {days.map((day) => (
            <Bar key={day.day} day={day} peak={peak} />
          ))}
        </div>

        <div aria-hidden className="mt-2 flex gap-1 text-[0.6rem] text-fg-3">
          {days.map((day, index) => (
            <span key={day.day} className="num flex-1 text-center">
              {/* Only every third label, or fourteen dates collide into a grey smear. */}
              {index % 3 === 0 || index === days.length - 1 ? shortDay(day.day) : " "}
            </span>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 border-t border-line pt-3 text-xs">
          <Stat label="Signed in" value={stats.data.total_successful} tone="text-accent-ink" />
          <Stat label="Failed" value={stats.data.total_failed} tone="text-warn" />
          <Stat label="Accounts locked" value={stats.data.total_locked} tone="text-bad" />
        </div>
      </div>
    </Card>
  );
}

function Bar({ day, peak }: { day: DailySignins; peak: number }) {
  const success = (day.successful / peak) * 100;
  const failed = (day.failed / peak) * 100;
  const label = `${day.day}: ${day.successful} signed in, ${day.failed} failed`;
  return (
    <div className="flex h-full flex-1 flex-col justify-end gap-px" title={label}>
      {day.failed > 0 && (
        <div
          className="w-full rounded-t-xs bg-warn"
          style={{ height: `${Math.max(failed, 2)}%` }}
        />
      )}
      <div
        className={cn(
          "w-full bg-accent",
          day.failed > 0 ? "rounded-b-xs" : "rounded-xs",
          day.successful === 0 && "bg-line",
        )}
        style={{ height: `${Math.max(success, 2)}%` }}
      />
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <span className="flex items-baseline gap-1.5">
      <span className={cn("num font-display text-base font-bold", tone)}>{value}</span>
      <span className="text-fg-3">{label}</span>
    </span>
  );
}

/** "08 Oct" — DD-MM order as the project uses, abbreviated to fit under a bar. */
function shortDay(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return `${String(date.getDate()).padStart(2, "0")} ${date.toLocaleString("en-IN", { month: "short" })}`;
}
