import { useOnline } from "@/lib/useOnline";

/**
 * A strip across the top of the app when the browser has lost the network.
 *
 * It warns and does nothing else. Nothing is disabled, no button is greyed out, no form is
 * blocked — because `navigator.onLine` is a guess. A captive hotel portal reports online
 * while swallowing every request; a phone on a weak signal flips to offline for a second
 * and back. Disabling the interface on that signal means somebody who *could* have saved
 * their work is told they may not, which is a worse failure than letting the request go
 * and showing them what came back.
 *
 * So the deal is: this says what the browser thinks, and `apiFetch` turns a request that
 * actually fails into a sentence that names the reason.
 */
export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-2 bg-warn-soft px-4 py-2 text-center text-sm font-medium text-warn"
    >
      <svg viewBox="0 0 20 20" className="size-4 shrink-0" fill="none" aria-hidden>
        <path
          d="M10 14.5h.01M3 7.5a11 11 0 0 1 14 0M5.5 10.5a7 7 0 0 1 9 0M2.5 2.5l15 15"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
      <span>
        You are offline. You can keep working, but nothing will be saved until the connection is
        back.
      </span>
    </div>
  );
}
