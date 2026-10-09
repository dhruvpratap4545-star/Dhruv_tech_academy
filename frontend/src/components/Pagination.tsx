import { Button } from "@/components/Button";

/**
 * Previous / Next, with the two numbers that make them mean something.
 *
 * "Page 2" on its own tells a reader nothing: there is no way to know whether they are
 * nearly finished or have forty pages left, and the only way to find out is to keep
 * clicking Next until it stops. "Page 2 of 7" answers that in four characters, and
 * "Showing 21–40 of 134" answers the question underneath it — how many people are there.
 *
 * The total comes from the server. Cursor paging cannot produce one by itself, so the API
 * counts the filtered set separately and returns it alongside the rows.
 */
export function Pagination({
  pageIndex,
  pageSize,
  total,
  shown,
  hasNext,
  onPrevious,
  onNext,
  noun = "results",
}: {
  /** Zero-based, as the caller holds it. Shown to people as `pageIndex + 1`. */
  pageIndex: number;
  pageSize: number;
  total: number;
  /** Rows actually on screen. The last page is usually shorter than `pageSize`. */
  shown: number;
  hasNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
  /** What is being counted, for the summary line: "users", "institutes", "entries". */
  noun?: string;
}) {
  // Never smaller than the page being looked at. Rows can disappear between requests —
  // somebody else suspends four people, or a filter narrows while a cursor trail is held —
  // and `total` drops while `pageIndex` does not. "Page 3 of 1" reads as a bug in the
  // product rather than as a list that changed underneath.
  const pageCount = Math.max(1, pageIndex + 1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : pageIndex * pageSize + 1;
  const last = pageIndex * pageSize + shown;

  // Nothing to page through and nothing to say about it.
  if (pageIndex === 0 && !hasNext && total <= shown) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3">
      <Button
        size="sm"
        variant="secondary"
        className="press"
        disabled={pageIndex === 0}
        onClick={onPrevious}
      >
        Previous
      </Button>

      {/* Polite, not assertive: the count changing as somebody pages is worth announcing,
          but not worth interrupting whatever is being read at that moment. */}
      <p className="num text-xs text-fg-2" aria-live="polite">
        <span className="font-medium text-fg">
          Page {pageIndex + 1} of {pageCount}
        </span>
        {total > 0 && (
          <span className="hidden sm:inline">
            {" · "}
            Showing {first}–{last} of {total} {noun}
          </span>
        )}
      </p>

      <Button size="sm" variant="secondary" className="press" disabled={!hasNext} onClick={onNext}>
        Next
      </Button>
    </div>
  );
}
