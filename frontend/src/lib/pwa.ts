/**
 * Installing the app, and knowing when the network is gone.
 *
 * The service worker is registered only in a production build. In development Vite serves
 * modules over the network and a worker sitting in front of them turns every save into a
 * guess about which copy you are looking at.
 */

export function registerServiceWorker(): void {
  if (!import.meta.env.PROD) return;
  if (!("serviceWorker" in navigator)) return;

  // After load, not during: registration competes with the first render for the same
  // connection, and the app appearing quickly matters more than being installable 400ms
  // sooner.
  window.addEventListener("load", () => {
    void navigator.serviceWorker.register("/sw.js").catch(() => {
      // An unregistered worker costs the install prompt and the offline shell, and
      // nothing else. The app works; there is nothing to tell the person about.
    });
  });
}
