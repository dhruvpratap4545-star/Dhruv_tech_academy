import { useQuery } from "@tanstack/react-query";

import { Card, CardBody, CardHeader } from "@/components/Card";
import { Modal } from "@/components/Modal";
import { Spinner } from "@/components/Spinner";
import type { ContentItem } from "@/features/library/api";
import { fetchVersions, libraryKeys } from "@/features/library/api";
import { useT } from "@/features/i18n/useT";
import { formatDateTime } from "@/lib/format";

/** Earlier versions of one piece of material; one is kept on every edit. */
export function HistoryModal({ item, onClose }: { item: ContentItem; onClose: () => void }) {
  const { t } = useT();
  const versions = useQuery({
    queryKey: libraryKeys.versions(item.id),
    queryFn: ({ signal }) => fetchVersions(item.id, signal),
  });
  return (
    <Modal open onClose={onClose} title={`${t("library.review.history")}: ${item.title}`}>
      {versions.isLoading && <Spinner />}
      {versions.data && versions.data.length === 0 && (
        <p className="text-sm text-fg-2">{t("library.review.noHistory")}</p>
      )}
      <ul className="space-y-2">
        {(versions.data ?? []).map((v) => (
          <li key={v.id}>
            <Card>
              <CardHeader
                title={t("library.review.version", { version: v.version })}
                description={formatDateTime(v.created_at)}
              />
              <CardBody>
                <dl className="space-y-1 text-xs">
                  {Object.entries(v.fields)
                    .filter(([, value]) => value !== null && typeof value !== "object")
                    .map(([key, value]) => (
                      <div key={key} className="flex gap-2">
                        <dt className="w-24 shrink-0 text-fg-3">{key}</dt>
                        <dd className="min-w-0 break-words text-fg">{String(value)}</dd>
                      </div>
                    ))}
                </dl>
              </CardBody>
            </Card>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
