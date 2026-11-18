import { useMutation, useQueryClient } from "@tanstack/react-query";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import type { ContentItem } from "@/features/library/api";
import { itemAction, libraryKeys } from "@/features/library/api";
import { useCan, useCurrentUser } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * What can be done to one piece of material. It is published as soon as it is added, so
 * there is no review step: the person who added it, or a library manager, may remove it.
 * Material left as a draft by the old review flow can still be published by a reviewer.
 */
export function ItemActions({ item, onHistory }: { item: ContentItem; onHistory?: () => void }) {
  const { t } = useT();
  const canPublish = useCan("library:publish");
  const canManage = useCan("library:manage");
  const own = useCurrentUser()?.id === item.created_by;
  const queryClient = useQueryClient();
  const act = useMutation({
    mutationFn: (action: "publish" | "archive") => itemAction(item.id, action),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: libraryKeys.all }),
  });
  const pending = item.status === "draft" || item.status === "in_review";
  return (
    <div className="w-full space-y-2">
      <div className="flex flex-wrap gap-2">
        {pending && canPublish && (
          <Button size="sm" loading={act.isPending} onClick={() => act.mutate("publish")}>
            {t("library.review.publish")}
          </Button>
        )}
        {item.status !== "archived" && (own || canManage) && (
          <Button
            size="sm"
            variant="ghost"
            disabled={act.isPending}
            onClick={() => act.mutate("archive")}
          >
            {t("library.review.archive")}
          </Button>
        )}
        {onHistory && (
          <Button size="sm" variant="ghost" onClick={onHistory}>
            {t("library.review.history")}
          </Button>
        )}
      </div>
      {act.error instanceof ApiError && <Alert tone="danger">{act.error.message}</Alert>}
    </div>
  );
}
