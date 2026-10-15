import { OfflineBanner } from "@/components/OfflineBanner";
import { Providers } from "@/app/providers";
import { AppRoutes } from "@/app/routes";

export function App() {
  return (
    <Providers>
      {/* Above the routes rather than inside the console shell, so it also shows on the
          sign-in and password screens — which is where losing the network is most
          confusing, because the failure there looks like a wrong password. */}
      <OfflineBanner />
      <AppRoutes />
    </Providers>
  );
}
