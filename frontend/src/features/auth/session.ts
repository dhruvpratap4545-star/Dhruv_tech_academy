import { meKey } from "@/features/auth/api";
import { queryClient } from "@/lib/queryClient";

/**
 * End the signed-in session on this device.
 *
 * One function, two callers: the Log out button, and the API layer when a 401 survives a
 * refresh attempt. Both mean the same thing — there is no session any more — and both
 * previously left the person looking at a fully rendered console whose every request was
 * failing.
 *
 * The order matters. `removeQueries` drops everything, *then* the current user is written
 * as `null` rather than left absent. Absent and null are not the same to a route guard:
 * absent reads as "still loading, wait", which is what kept bouncing a logged-out user
 * back to the dashboard. Null is a definite answer — nobody is signed in — and the guards
 * act on it immediately.
 */
export function endSession(): void {
  // Only act if somebody is actually signed in. A signed-out visitor's first `/me` is a
  // 401 by design, and without this guard that 401 would clear the very query that is
  // still in flight, which restarts it, which 401s again — the login page never renders.
  if (queryClient.getQueryData(meKey) == null) return;

  // Order matters, and not in the obvious way. Removing every query first — including
  // this one — detaches the live observer in `AuthProvider`; the `setQueryData` that
  // follows then writes into a cache entry nothing is listening to, so the UI never hears
  // that the user is gone and the console stays on screen. Write the null answer first,
  // while the observer is still attached, and only then drop everything else.
  queryClient.setQueryData(meKey, null);
  queryClient.removeQueries({
    predicate: (query) => query.queryKey[0] !== meKey[0],
  });
}
