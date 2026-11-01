import { useId, useRef, useState } from "react";

import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { useT } from "@/features/i18n/useT";
import { MAX_UPLOAD_MB, screenFiles } from "@/lib/uploads";

/**
 * Pick PDFs and photos, or take a photo straight from the phone camera.
 *
 * Controlled: the parent holds the `File[]` and sends it as multipart when the form is
 * submitted. Two buttons rather than one because `capture` forces the camera on phones —
 * a student photographing their notebook wants that, but someone attaching a PDF does not.
 */
export function FileUpload({
  label,
  files,
  onChange,
  max = 5,
  camera = true,
  disabled = false,
}: {
  label: string;
  files: File[];
  onChange: (files: File[]) => void;
  max?: number;
  camera?: boolean;
  disabled?: boolean;
}) {
  const { t } = useT();
  const id = useId();
  const pickRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [errors, setErrors] = useState<string[]>([]);

  function add(list: FileList | null) {
    if (!list) return;
    const result = screenFiles(files, Array.from(list), max, t);
    setErrors(result.errors);
    onChange(result.files);
  }

  return (
    <div className="space-y-2">
      <p id={`${id}-label`} className="text-sm font-medium text-fg">
        {label}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          icon={<Icon name="plus" />}
          disabled={disabled || files.length >= max}
          onClick={() => pickRef.current?.click()}
        >
          {t("upload.choose")}
        </Button>
        {camera && (
          <Button
            variant="secondary"
            size="sm"
            disabled={disabled || files.length >= max}
            onClick={() => cameraRef.current?.click()}
          >
            {t("upload.camera")}
          </Button>
        )}
      </div>
      <input
        ref={pickRef}
        type="file"
        multiple
        accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png"
        className="sr-only"
        aria-labelledby={`${id}-label`}
        data-testid="file-input"
        onChange={(event) => {
          add(event.target.files);
          event.target.value = "";
        }}
      />
      {camera && (
        <input
          ref={cameraRef}
          type="file"
          accept="image/*"
          capture="environment"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => {
            add(event.target.files);
            event.target.value = "";
          }}
        />
      )}
      <p className="text-xs text-fg-2">{t("upload.hint", { mb: MAX_UPLOAD_MB, max })}</p>
      {errors.length > 0 && (
        <ul role="alert" className="space-y-0.5 text-xs text-bad">
          {errors.map((error) => (
            <li key={error}>{error}</li>
          ))}
        </ul>
      )}
      {files.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {files.map((file, index) => (
            <li
              key={`${file.name}-${index}`}
              className="flex max-w-full items-center gap-1.5 rounded-full bg-surface-3 py-1 pr-1 pl-3 text-xs text-fg"
            >
              <span className="truncate">{file.name}</span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onChange(files.filter((_, i) => i !== index))}
                aria-label={t("upload.remove", { name: file.name })}
                className="rounded-full p-1 text-fg-2 hover:bg-surface-2 hover:text-fg"
              >
                <Icon name="close" className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
