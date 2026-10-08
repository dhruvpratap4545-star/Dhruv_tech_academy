import type { ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Skeleton } from "./Spinner";

export type Column<T> = {
  key: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Hidden below `sm` in the table view. Secondary detail still shows in the stacked view. */
  secondary?: boolean;
  /** Short label for the stacked view. Falls back to `header` when it is plain text. */
  label?: string;
  /** The identifying column — rendered first and unlabelled when stacked. */
  primary?: boolean;
  className?: string;
};

export type TableProps<T> = {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  empty?: ReactNode;
  caption?: string;
  onRowClick?: (row: T) => void;
};

/**
 * Data table with the three states a real one needs — loading, empty, populated — and two
 * layouts.
 *
 * **Below `sm` each row is stacked as a labelled block instead of a table row.** A table
 * wide enough to be useful cannot fit a 360px screen: it either scrolls sideways, which
 * hides the actions column where nobody looks for it, or it drags the whole page with it.
 * Stacking keeps every cell reachable without a single horizontal scrollbar.
 */
export function Table<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  empty,
  caption,
  onRowClick,
}: TableProps<T>) {
  if (loading) return <TableSkeleton columns={columns.length} />;
  if (rows.length === 0) return <>{empty ?? <EmptyState title="Nothing to show yet" />}</>;

  const primary = columns.find((column) => column.primary) ?? columns[0]!;
  const rest = columns.filter((column) => column !== primary);

  return (
    <>
      {/* Stacked, below sm */}
      <ul className="divide-y divide-line sm:hidden">
        {rows.map((row) => (
          <li
            key={rowKey(row)}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            className={cn("space-y-2.5 px-4 py-3.5", onRowClick && "cursor-pointer")}
          >
            <div className="min-w-0">{primary.cell(row)}</div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
              {rest.map((column) => {
                const label = columnLabel(column);
                return (
                  <div key={column.key} className="contents">
                    <dt className="eyebrow pt-0.5">{label}</dt>
                    <dd className="min-w-0 text-sm text-fg">{column.cell(row)}</dd>
                  </div>
                );
              })}
            </dl>
          </li>
        ))}
      </ul>

      {/* Table, from sm up */}
      <div className="hidden w-full min-w-0 overflow-x-auto sm:block">
        <table className="w-full border-collapse text-sm">
          {caption && <caption className="sr-only">{caption}</caption>}
          <thead>
            <tr className="border-b border-line text-left">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "px-3 py-2.5 text-xs font-semibold tracking-wide text-fg-2 uppercase",
                    column.secondary && "hidden md:table-cell",
                    column.className,
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={cn(
                  "border-b border-line last:border-0",
                  onRowClick && "cursor-pointer transition-colors hover:bg-surface-2",
                )}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn(
                      "px-3 py-3 align-middle text-fg",
                      column.secondary && "hidden md:table-cell",
                      column.className,
                    )}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** The stacked view needs a plain-text label; most headers already are one. */
function columnLabel<T>(column: Column<T>): string {
  if (column.label) return column.label;
  if (typeof column.header === "string") return column.header;
  return "";
}

function TableSkeleton({ columns }: { columns: number }) {
  return (
    <div className="space-y-2 p-3" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: 5 }, (_, row) => (
        <div key={row} className="flex gap-3">
          {Array.from({ length: columns }, (_, column) => (
            <Skeleton key={column} className="h-8 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div className="flex size-11 items-center justify-center rounded-full bg-surface-2 text-fg-3">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
          <path
            d="M4 7h16M4 12h16M4 17h10"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </div>
      <div className="space-y-1">
        <p className="font-semibold text-fg">{title}</p>
        {description && <p className="mx-auto max-w-sm text-sm text-fg-2">{description}</p>}
      </div>
      {action}
    </div>
  );
}
