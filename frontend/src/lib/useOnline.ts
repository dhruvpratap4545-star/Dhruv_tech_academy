import { useSyncExternalStore } from "react";

/**
 * Whether the browser believes it has a network.
 *
 * `useSyncExternalStore` rather than `useState` plus two listeners: the browser already
 * holds this value, and subscribing to it is exactly what this hook is for. It also means
 * every component asking the question gets the same answer in the same render.
 *
 * `navigator.onLine` is not a promise that requests will succeed — a captive hotel portal
 * reports "online" while dropping everything — which is why the app only ever *warns* on
 * the strength of it and never blocks a button. A false "you are offline" that stops
 * somebody working is worse than the failed request it was trying to save them from.
 */
function subscribe(callback: () => void): () => void {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
}

function snapshot(): boolean {
  return navigator.onLine;
}

/** The server render has no navigator, and nothing is offline before it has loaded. */
function serverSnapshot(): boolean {
  return true;
}

export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot);
}
