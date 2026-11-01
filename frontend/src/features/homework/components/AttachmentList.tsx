import { Icon } from "@/components/Icon";
import type { FileInfo } from "@/features/homework/api";
import { fileUrl } from "@/features/homework/api";

/**
 * Links to files through `GET /files/{id}`, which checks access and redirects to a
 * short-lived signed link. Opened in a new tab so the page the person is on stays put.
 */
export function AttachmentList({ files, empty }: { files: FileInfo[]; empty?: string }) {
  if (files.length === 0) return empty ? <p className="text-sm text-fg-3">{empty}</p> : null;
  return (
    <ul className="flex flex-wrap gap-2">
      {files.map((file) => (
        <li key={file.id}>
          <a
            href={fileUrl(file.id)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex max-w-full items-center gap-1.5 rounded-full bg-surface-3 px-3 py-1.5 text-xs text-fg hover:bg-surface-2"
          >
            <Icon name="log" className="size-3.5" />
            <span className="truncate">{file.original_name}</span>
          </a>
        </li>
      ))}
    </ul>
  );
}
