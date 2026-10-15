import type { ReactNode } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Modal } from "@/components/Modal";

/**
 * A stop before something that affects another person.
 *
 * Reserved for actions whose damage lands on somebody else and is not obvious from the
 * screen afterwards — suspending an account signs that person out mid-task and refuses
 * their next sign-in. A misclick on a small button in a crowded row should not be able to
 * do that silently.
 *
 * Deliberately *not* used for reversible, self-evident actions. A confirmation on
 * everything is a confirmation on nothing: people learn to dismiss the dialog without
 * reading it, and then the one that mattered goes the same way.
 */
export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  confirmLabel,
  tone = "danger",
  pending = false,
  error,
  children,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  confirmLabel: string;
  tone?: "danger" | "primary";
  pending?: boolean;
  error?: string | null;
  /** What actually happens, in plain words. Name the person and the consequence. */
  children: ReactNode;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="sm"
      title={title}
      footer={
        <div className="ml-auto flex gap-2">
          <Button variant="secondary" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button
            variant={tone === "danger" ? "danger" : "primary"}
            onClick={onConfirm}
            loading={pending}
          >
            {confirmLabel}
          </Button>
        </div>
      }
    >
      <div className="space-y-3 text-sm text-fg-2">
        {children}
        {error && (
          <Alert tone="danger">
            <p>{error}</p>
          </Alert>
        )}
      </div>
    </Modal>
  );
}
