import type { MessageKey } from "@/lib/i18n";

/** Must match the backend's MAX_UPLOAD_MB. The server is the real check; this saves a
 * wasted upload of a file it would refuse. */
export const MAX_UPLOAD_MB = 10;
const ALLOWED = ["application/pdf", "image/jpeg", "image/png"];

/** Decide which picked files to keep, and say why the others were refused. */
export function screenFiles(
  current: File[],
  picked: File[],
  max: number,
  t: (key: MessageKey, vars?: Record<string, string | number>) => string,
): { files: File[]; errors: string[] } {
  const errors: string[] = [];
  const files = [...current];
  for (const file of picked) {
    // Some phones report an empty type for camera photos; the server sniffs the bytes.
    if (file.type && !ALLOWED.includes(file.type)) {
      errors.push(t("upload.wrongType", { name: file.name }));
      continue;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      errors.push(t("upload.tooBig", { name: file.name, mb: MAX_UPLOAD_MB }));
      continue;
    }
    if (files.length >= max) {
      errors.push(t("upload.tooMany", { max }));
      break;
    }
    files.push(file);
  }
  return { files, errors };
}
