import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Field, SelectField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import {
  bulkInvite,
  downloadInviteTemplate,
  fetchInstitutes,
  instituteKeys,
  userKeys,
} from "@/features/admin/api";
import type { BulkInviteReport, BulkInviteRow } from "@/features/admin/api";
import { useCurrentUser } from "@/features/auth/useAuth";
import { isPlatformStaff } from "@/lib/permissions";

/**
 * Invite a whole class from a spreadsheet.
 *
 * Two steps, and the first one is not optional. The preview runs the same code on the
 * server with nothing written, so what this screen promises and what the import does
 * cannot disagree — and an administrator about to create five hundred accounts gets to
 * read the list first. There is no undo for the other order.
 */
export function BulkInviteModal({
  open,
  onClose,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  /** Called with the finished report, so the page can confirm what was sent. */
  onDone?: (report: BulkInviteReport) => void;
}) {
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const platformStaff = isPlatformStaff(user);
  const fileInput = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [instituteId, setInstituteId] = useState("");
  const [preview, setPreview] = useState<BulkInviteReport | null>(null);
  const [done, setDone] = useState<BulkInviteReport | null>(null);

  // Platform staff pick an institute; anybody with exactly one is pinned to it by the
  // server, so they are not asked a question with one answer.
  const needsInstitute = platformStaff || (user?.institute_ids.length ?? 0) > 1;
  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
    enabled: open && needsInstitute,
  });

  const template = useMutation({ mutationFn: downloadInviteTemplate });

  const check = useMutation({
    mutationFn: () => bulkInvite(file!, instituteId || null, true),
    onSuccess: setPreview,
  });

  const send = useMutation({
    mutationFn: () => bulkInvite(file!, instituteId || null, false),
    onSuccess: async (report) => {
      await queryClient.invalidateQueries({ queryKey: userKeys.all });
      setDone(report);
      onDone?.(report);
    },
  });

  const reset = () => {
    setFile(null);
    setPreview(null);
    setDone(null);
    setInstituteId("");
    check.reset();
    send.reset();
    template.reset();
    if (fileInput.current) fileInput.current.value = "";
  };

  const close = () => {
    reset();
    onClose();
  };

  const report = done ?? preview;
  const error = check.error ?? send.error ?? template.error;

  return (
    <Modal
      open={open}
      onClose={close}
      size="lg"
      title="Invite from a spreadsheet"
      description={
        done
          ? undefined
          : "One row per learner, with the parent's email beside the child's. Nothing is " +
            "sent until you have seen what the file says."
      }
      footer={
        done ? (
          <Button onClick={close}>Close</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            {preview ? (
              <Button
                loading={send.isPending}
                disabled={countReady(preview) === 0}
                onClick={() => send.mutate()}
              >
                {countReady(preview) === 1
                  ? "Invite 1 learner"
                  : `Invite ${countReady(preview)} learners`}
              </Button>
            ) : (
              <Button
                loading={check.isPending}
                disabled={!file || (needsInstitute && !instituteId)}
                onClick={() => check.mutate()}
              >
                Check the file
              </Button>
            )}
          </>
        )
      }
    >
      <div className="space-y-5">
        {error && (
          <Alert tone="danger" title="That file could not be used">
            <p>{error.message}</p>
          </Alert>
        )}

        {!report && (
          <>
            <div className="rounded-lg border border-line bg-surface-2 p-3.5">
              <p className="text-sm font-semibold text-fg">Start from the template</p>
              <p className="mt-0.5 text-sm text-fg-2">
                Only <strong className="font-semibold">Full Name</strong> and{" "}
                <strong className="font-semibold">Email</strong> are required. Branch, class,
                section and the parent&rsquo;s details are used when they are filled in. Up to 500
                learners per file.
              </p>
              <Button
                className="mt-2.5"
                size="sm"
                variant="secondary"
                loading={template.isPending}
                onClick={() => template.mutate()}
              >
                Download the template
              </Button>
            </div>

            {needsInstitute && (
              <SelectField
                label="Institute"
                hint="Which institute these learners belong to."
                placeholder="Choose an institute"
                required
                value={instituteId}
                onChange={(event) => setInstituteId(event.target.value)}
                options={(institutes.data?.items ?? []).map((row) => ({
                  value: row.id,
                  label: row.name,
                }))}
              />
            )}

            <Field label="Your filled-in file" hint="An .xlsx file saved from Excel." required>
              {({ controlId, describedBy }) => (
                <input
                  id={controlId}
                  aria-describedby={describedBy}
                  ref={fileInput}
                  type="file"
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-fg-2 file:mr-3 file:rounded-sm file:border file:border-line-strong file:bg-surface-2 file:px-3 file:py-2 file:text-sm file:font-semibold file:text-fg hover:file:bg-surface-3"
                />
              )}
            </Field>
          </>
        )}

        {report && <Summary report={report} />}

        {report && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-120 border-collapse text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="py-2 pr-3 font-semibold text-fg-2">Row</th>
                  <th className="py-2 pr-3 font-semibold text-fg-2">Learner</th>
                  <th className="py-2 pr-3 font-semibold text-fg-2">Parent</th>
                  <th className="py-2 font-semibold text-fg-2">What happens</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {report.rows.map((row) => (
                  <Row key={row.row} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {preview && !done && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setPreview(null);
              setFile(null);
              if (fileInput.current) fileInput.current.value = "";
            }}
          >
            Choose a different file
          </Button>
        )}
      </div>
    </Modal>
  );
}

function countReady(report: BulkInviteReport): number {
  return report.rows.filter((row) => row.outcome === "ready").length;
}

function Summary({ report }: { report: BulkInviteReport }) {
  const ready = countReady(report);

  if (report.dry_run) {
    return (
      <Alert
        tone={report.skipped > 0 ? "warning" : "info"}
        title={
          ready === 0
            ? "Nothing in this file can be invited"
            : `${ready} ${ready === 1 ? "learner" : "learners"} ready to invite`
        }
      >
        <p>
          {report.skipped > 0
            ? `${report.skipped} ${report.skipped === 1 ? "row is" : "rows are"} listed below with the reason. ` +
              "Fix them in the file and upload it again, or go ahead without them."
            : "Nothing has been sent yet."}
        </p>
      </Alert>
    );
  }

  return (
    <Alert
      tone={report.skipped > 0 ? "warning" : "success"}
      title={`${report.invited} ${report.invited === 1 ? "learner" : "learners"} invited`}
    >
      <p>
        {report.parents > 0 &&
          `${report.parents} ${report.parents === 1 ? "parent was" : "parents were"} linked. `}
        Each of them gets an email with a 6-digit code, valid for 48 hours, which they use to set
        their own password.
      </p>
      {report.skipped > 0 && (
        <p className="mt-1">
          {report.skipped} {report.skipped === 1 ? "row was" : "rows were"} skipped — the reason is
          beside each one below.
        </p>
      )}
    </Alert>
  );
}

const TONE = {
  invited: "success",
  linked: "success",
  ready: "accent",
  skipped: "warning",
} as const;

function Row({ row }: { row: BulkInviteRow }) {
  const place = [row.branch, row.class_name].filter(Boolean).join(" · ");

  return (
    <tr className={row.outcome === "skipped" ? "text-fg-2" : undefined}>
      <td className="py-2 pr-3 align-top tabular-nums text-fg-2">{row.row}</td>
      <td className="py-2 pr-3 align-top">
        <p className="font-medium text-fg">{row.full_name || "—"}</p>
        <p className="truncate text-xs text-fg-2">{row.email || "no email address"}</p>
        {place && <p className="text-xs text-fg-3">{place}</p>}
      </td>
      <td className="py-2 pr-3 align-top">
        {row.parent_email ? (
          <>
            <p className="truncate text-xs text-fg-2">{row.parent_email}</p>
            {row.parent_outcome && row.parent_outcome !== "ready" && (
              <Badge tone={TONE[row.parent_outcome]}>{row.parent_outcome}</Badge>
            )}
            {row.parent_reason && <p className="text-xs text-warn">{row.parent_reason}</p>}
          </>
        ) : (
          <span className="text-xs text-fg-3">—</span>
        )}
      </td>
      <td className="py-2 align-top">
        <Badge tone={TONE[row.outcome]}>
          {row.outcome === "ready" ? "will invite" : row.outcome}
        </Badge>
        {row.reason && <p className="mt-0.5 text-xs text-warn">{row.reason}</p>}
      </td>
    </tr>
  );
}
