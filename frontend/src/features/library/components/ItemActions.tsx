import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { TextField } from "@/components/Field";
import type { ContentItem } from "@/features/library/api";
import { itemAction, libraryKeys } from "@/features/library/api";
import { useCan } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/** The workflow buttons an item offers, given its status and what the reader may do. */
export function ItemActions({ item, onHistory }: { item: ContentItem; onHistory: () => void }) {
  const { t } = useT();
  const canPublish = useCan("library:publish");
  const canManage = useCan("library:manage");
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const act = useMutation({
    mutationFn: (action: "submit" | "publish" | "reject" | "archive") =>
      itemAction(item.id, action, note),
    onSuccess: () => {
      setNote("");
      void queryClient.invalidateQueries({ queryKey: libraryKeys.all });
    },
  });
  return (
    <div className="w-full space-y-2">
      {item.status === "in_review" && canPublish && (
        <TextField
          label={t("library.review.note")}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          maxLength={500}
        />
      )}
      <div className="flex flex-wrap gap-2">
        {item.status === "draft" && (
          <Button size="sm" loading={act.isPending} onClick={() => act.mutate("submit")}>
            {t("library.review.submit")}
          </Button>
        )}
        {item.status === "in_review" && canPublish && (
          <>
            <Button size="sm" loading={act.isPending} onClick={() => act.mutate("publish")}>
              {t("library.review.publish")}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              disabled={act.isPending}
              onClick={() => act.mutate("reject")}
            >
              {t("library.review.reject")}
            </Button>
          </>
        )}
        {item.status !== "archived" && canManage && (
          <Button
            size="sm"
            variant="ghost"
            disabled={act.isPending}
            onClick={() => act.mutate("archive")}
          >
            {t("library.review.archive")}
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onHistory}>
          {t("library.review.history")}
        </Button>
      </div>
      {act.error instanceof ApiError && <Alert tone="danger">{act.error.message}</Alert>}
    </div>
  );
}
