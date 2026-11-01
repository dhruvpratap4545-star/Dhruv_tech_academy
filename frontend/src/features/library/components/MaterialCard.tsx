import type { ReactNode } from "react";

import { Badge } from "@/components/Badge";
import { Card } from "@/components/Card";
import type { ContentItem, ItemStatus } from "@/features/library/api";
import { embedUrl, fileUrl, safeHref } from "@/features/library/material";
import { useT } from "@/features/i18n/useT";
import { formatDate } from "@/lib/format";

const STATUS_TONE: Record<ItemStatus, "neutral" | "warning" | "success" | "danger"> = {
  draft: "neutral",
  in_review: "warning",
  published: "success",
  archived: "danger",
};

/**
 * One piece of material, shown the way its kind needs. Everything a person typed is
 * rendered as text: notes are never HTML, links are https only, and videos are embedded
 * from the id the server validated rather than from a pasted address.
 */
export function MaterialCard({
  item,
  showStatus = false,
  actions,
}: {
  item: ContentItem;
  showStatus?: boolean;
  actions?: ReactNode;
}) {
  const { t } = useT();
  const video = item.kind === "video_link" ? embedUrl(item.video_provider, item.video_id) : null;
  const href = safeHref(item.url);
  return (
    <Card className="space-y-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-fg">{item.title}</h3>
          <p className="text-xs text-fg-2">
            {t(`library.kind.${item.kind}`)} · {t(`library.medium.${item.medium}`)}
            {item.published_at && ` · ${formatDate(item.published_at)}`}
          </p>
        </div>
        {showStatus && (
          <Badge tone={STATUS_TONE[item.status]}>{t(`library.status.${item.status}`)}</Badge>
        )}
      </div>

      {video && (
        <div className="aspect-video overflow-hidden rounded-md bg-surface-3">
          <iframe
            src={video}
            title={item.title}
            className="size-full"
            loading="lazy"
            referrerPolicy="strict-origin-when-cross-origin"
            allow="encrypted-media; picture-in-picture; fullscreen"
            sandbox="allow-scripts allow-same-origin allow-presentation"
          />
        </div>
      )}
      {item.kind === "text" && item.body && (
        <p className="text-sm whitespace-pre-wrap text-fg">{item.body}</p>
      )}
      {(item.kind === "pdf" || item.kind === "image") && item.file_id && (
        <a
          href={fileUrl(item.file_id)}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-sm font-medium text-accent hover:underline"
        >
          {t("library.openFile")}
          {item.file && ` · ${item.file.original_name}`}
        </a>
      )}
      {item.kind === "link" &&
        (href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium break-all text-accent hover:underline"
          >
            {t("library.openLink")}
          </a>
        ) : (
          <p className="text-sm break-all text-fg-2">{item.url}</p>
        ))}

      {(item.author || item.source) && (
        <p className="text-xs text-fg-3">
          {item.author && t("library.by", { author: item.author })}
          {item.author && item.source && " · "}
          {item.source && t("library.source", { source: item.source })}
        </p>
      )}
      {item.review_note && item.status === "draft" && (
        <p className="rounded-md bg-warn-soft p-2 text-xs text-warn">
          {t("library.review.noteFromReviewer", { note: item.review_note })}
        </p>
      )}
      {actions && <div className="flex flex-wrap gap-2 pt-1">{actions}</div>}
    </Card>
  );
}
