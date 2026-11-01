import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Spinner } from "@/components/Spinner";
import { fetchInstituteModules, instituteKeys, setInstituteModule } from "@/features/admin/api";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

/**
 * Which optional modules an institute has (Phase 3). Everyone who can see the institute
 * sees the list; only holders of `module:enable` get switches, and the server still
 * refuses anyone below platform or organisation level.
 */
export function InstituteModules({ instituteId }: { instituteId: string }) {
  const { t } = useT();
  const canSwitch = useCan("module:enable");
  const queryClient = useQueryClient();
  const modules = useQuery({
    queryKey: instituteKeys.modules(instituteId),
    queryFn: ({ signal }) => fetchInstituteModules(instituteId, signal),
  });
  const toggle = useMutation({
    mutationFn: ({ key, enabled }: { key: string; enabled: boolean }) =>
      setInstituteModule(instituteId, key, enabled),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: instituteKeys.modules(instituteId) }),
  });

  return (
    <section className="border-t border-line">
      <div className="px-4 pt-4">
        <h3 className="text-sm font-semibold text-fg">{t("modules.title")}</h3>
        <p className="text-xs text-fg-2">{t("modules.description")}</p>
      </div>
      {modules.isLoading && <Spinner className="m-4" />}
      {toggle.error instanceof ApiError && (
        <Alert tone="danger" className="m-4">
          {toggle.error.message}
        </Alert>
      )}
      <ul className="divide-y divide-line">
        {(modules.data ?? []).map((module) => (
          <li key={module.key} className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-fg">{module.name}</p>
              {module.description && <p className="text-xs text-fg-2">{module.description}</p>}
            </div>
            {canSwitch ? (
              <button
                type="button"
                role="switch"
                aria-checked={module.enabled}
                aria-label={module.name}
                disabled={toggle.isPending}
                onClick={() => toggle.mutate({ key: module.key, enabled: !module.enabled })}
                className={cn(
                  "relative h-6 w-11 shrink-0 rounded-full transition-colors",
                  module.enabled ? "bg-accent" : "bg-surface-3",
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform",
                    module.enabled && "translate-x-5",
                  )}
                />
              </button>
            ) : (
              <Badge tone={module.enabled ? "success" : "neutral"}>
                {module.enabled ? t("common.on") : t("common.off")}
              </Badge>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
