import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Checkbox, SelectField, TextField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import {
  archiveInstitute,
  createBranch,
  createClass,
  createSession,
  instituteKeys,
  organisationKeys,
  restoreInstitute,
  updateBranch,
  updateClass,
  updateInstitute,
  updateSession,
} from "@/features/admin/api";
import type { Branch, ClassRow, Institute, Organisation, Session } from "@/features/auth/types";
import { useCan, useCurrentUser } from "@/features/auth/useAuth";
import { formatDate } from "@/lib/format";
import { isPlatformStaff } from "@/lib/permissions";

/**
 * The management actions beside each node of the hierarchy (PRD §12).
 *
 * Every button is gated on the permission the server will check, so people are not offered
 * things that can only fail — but the server's scope check is still the answer, and its
 * refusals are shown as they come back rather than reworded.
 */

/** Everything on the hierarchy page hangs off "institutes"; organisations carry counts. */
function useRefreshHierarchy() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: instituteKeys.all }),
      queryClient.invalidateQueries({ queryKey: organisationKeys.all }),
    ]);
}

function ActionBar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap gap-2 border-b border-line px-4 py-3">{children}</div>;
}

/** A create-or-edit dialog: the fields, a save button, and the server's answer. */
function FormModal({
  title,
  description,
  submitLabel,
  valid,
  save,
  onClose,
  children,
}: {
  title: string;
  description?: string;
  submitLabel: string;
  valid: boolean;
  save: () => Promise<unknown>;
  onClose: () => void;
  children: ReactNode;
}) {
  const refresh = useRefreshHierarchy();
  const mutation = useMutation({
    mutationFn: save,
    onSuccess: async () => {
      await refresh();
      onClose();
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!valid} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {submitLabel}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {mutation.error && (
          <Alert tone="danger">
            <p>{mutation.error.message}</p>
          </Alert>
        )}
        {children}
      </div>
    </Modal>
  );
}

/** Archive, or bring back. Both ask first: either one changes who can see what. */
function ArchiveToggle({
  name,
  status,
  archive,
  restore,
  consequence,
}: {
  name: string;
  status: "active" | "archived";
  archive: () => Promise<unknown>;
  restore: () => Promise<unknown>;
  consequence: string;
}) {
  const refresh = useRefreshHierarchy();
  const [confirming, setConfirming] = useState(false);
  const archived = status === "archived";
  const mutation = useMutation({
    mutationFn: () => (archived ? restore() : archive()),
    onSuccess: async () => {
      await refresh();
      setConfirming(false);
    },
  });
  const close = () => {
    setConfirming(false);
    mutation.reset();
  };
  return (
    <>
      <Button
        size="sm"
        variant={archived ? "secondary" : "danger"}
        onClick={() => setConfirming(true)}
      >
        {archived ? "Restore" : "Archive"}
      </Button>
      <ConfirmDialog
        open={confirming}
        onClose={close}
        onConfirm={() => mutation.mutate()}
        title={`${archived ? "Restore" : "Archive"} ${name}?`}
        confirmLabel={archived ? "Restore it" : "Archive it"}
        tone={archived ? "primary" : "danger"}
        pending={mutation.isPending}
        error={mutation.error?.message ?? null}
      >
        <p>
          {archived ? "It becomes active again and shows up wherever it used to." : consequence}
        </p>
        {!archived && <p>Nothing is deleted. It can be restored later.</p>}
      </ConfirmDialog>
    </>
  );
}

const INSTITUTE_TYPES = [
  { value: "college", label: "College" },
  { value: "school", label: "School" },
  { value: "coaching", label: "Coaching institute" },
  { value: "academy", label: "Academy" },
];

// ------------------------------------------------------------------------ institute

export function InstituteActions({
  institute,
  organisations,
}: {
  institute: Institute;
  organisations: Organisation[];
}) {
  const canEdit = useCan("institute:update");
  // The platform's own institute holds the master library and platform roles; it is never
  // archived, and the server refuses it.
  const canArchive = useCan("institute:archive") && !institute.is_system;
  const canAddBranch = useCan("branch:create");
  const canAddSession = useCan("session:create");
  const [dialog, setDialog] = useState<"edit" | "branch" | "session" | null>(null);
  const active = institute.status === "active";

  return (
    <>
      {(canEdit || canArchive || canAddBranch || canAddSession) && (
        <ActionBar>
          {canEdit && (
            <Button size="sm" variant="secondary" onClick={() => setDialog("edit")}>
              Edit institute
            </Button>
          )}
          {canAddBranch && active && (
            <Button size="sm" variant="secondary" onClick={() => setDialog("branch")}>
              <Icon name="plus" className="size-3.5" />
              Add branch
            </Button>
          )}
          {canAddSession && active && (
            <Button size="sm" variant="secondary" onClick={() => setDialog("session")}>
              <Icon name="plus" className="size-3.5" />
              Add session
            </Button>
          )}
          {canArchive && (
            <ArchiveToggle
              name={institute.name}
              status={institute.status}
              archive={() => archiveInstitute(institute.id)}
              restore={() => restoreInstitute(institute.id)}
              consequence="Everybody's access inside it ends straight away — administrators, teachers, students and parents alike."
            />
          )}
        </ActionBar>
      )}

      {dialog === "edit" && (
        <InstituteEditor
          institute={institute}
          organisations={organisations}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "branch" && (
        <BranchEditor instituteId={institute.id} branch={null} onClose={() => setDialog(null)} />
      )}
      {dialog === "session" && (
        <SessionEditor instituteId={institute.id} session={null} onClose={() => setDialog(null)} />
      )}
    </>
  );
}

function InstituteEditor({
  institute,
  organisations,
  onClose,
}: {
  institute: Institute;
  organisations: Organisation[];
  onClose: () => void;
}) {
  // Moving an institute between organisations changes who runs it, so only platform staff
  // may; the server refuses anybody else with a 403.
  const platformStaff = isPlatformStaff(useCurrentUser());
  const [name, setName] = useState(institute.name);
  const [type, setType] = useState<Institute["type"]>(institute.type);
  const [contactEmail, setContactEmail] = useState(institute.contact_email ?? "");
  const [organisationId, setOrganisationId] = useState(institute.organisation_id ?? "");

  return (
    <FormModal
      title={`Edit ${institute.name}`}
      description="The code cannot change — records elsewhere refer to it."
      submitLabel="Save changes"
      valid={name.trim().length >= 2}
      onClose={onClose}
      save={() =>
        updateInstitute(institute.id, {
          name,
          type,
          contact_email: contactEmail || undefined,
          ...(platformStaff && organisationId !== (institute.organisation_id ?? "")
            ? { organisation_id: organisationId || null }
            : {}),
        })
      }
    >
      <TextField
        label="Institute name"
        required
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <SelectField
        label="Type"
        value={type}
        onChange={(event) => setType(event.target.value as Institute["type"])}
        options={INSTITUTE_TYPES}
      />
      <TextField
        label="Contact email"
        type="email"
        value={contactEmail}
        onChange={(event) => setContactEmail(event.target.value)}
      />
      {platformStaff && (
        <SelectField
          label="Organisation"
          hint="Moving it changes which Organisation Admins can run it."
          value={organisationId}
          onChange={(event) => setOrganisationId(event.target.value)}
          options={[
            { value: "", label: "None — standalone" },
            ...organisations
              .filter((row) => row.status === "active" || row.id === institute.organisation_id)
              .map((row) => ({ value: row.id, label: row.name })),
          ]}
        />
      )}
    </FormModal>
  );
}

// ------------------------------------------------------------------------- sessions

/** The institute's academic sessions, with edit and "make current" for those who may. */
export function SessionList({
  institute,
  sessions,
}: {
  institute: Institute;
  sessions: Session[];
}) {
  const canUpdate = useCan("session:update");
  const refresh = useRefreshHierarchy();
  const [editing, setEditing] = useState<Session | null>(null);
  const makeCurrent = useMutation({
    mutationFn: (session: Session) => updateSession(institute.id, session.id, { is_current: true }),
    onSuccess: refresh,
  });

  return (
    <section className="space-y-2 border-t border-line p-4">
      <h3 className="text-sm font-semibold text-fg">Academic sessions</h3>
      {makeCurrent.error && (
        <Alert tone="danger">
          <p>{makeCurrent.error.message}</p>
        </Alert>
      )}
      {sessions.length === 0 ? (
        <p className="text-sm text-fg-2">None yet.</p>
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line">
          {sessions.map((session) => (
            <li key={session.id} className="flex flex-wrap items-center gap-2 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-fg">
                  {session.name}
                  {session.is_current && (
                    <Badge tone="accent" className="ml-2">
                      Current
                    </Badge>
                  )}
                </p>
                <p className="num text-xs text-fg-2">
                  {formatDate(session.start_date)} – {formatDate(session.end_date)}
                </p>
              </div>
              {canUpdate && (
                <>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(session)}>
                    Edit
                  </Button>
                  {!session.is_current && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={makeCurrent.isPending && makeCurrent.variables?.id === session.id}
                      onClick={() => makeCurrent.mutate(session)}
                    >
                      Make current
                    </Button>
                  )}
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <SessionEditor
          instituteId={institute.id}
          session={editing}
          onClose={() => setEditing(null)}
        />
      )}
    </section>
  );
}

function SessionEditor({
  instituteId,
  session,
  onClose,
}: {
  instituteId: string;
  session: Session | null;
  onClose: () => void;
}) {
  const [name, setName] = useState(session?.name ?? "");
  const [start, setStart] = useState(session?.start_date ?? "");
  const [end, setEnd] = useState(session?.end_date ?? "");
  const [current, setCurrent] = useState(session?.is_current ?? false);
  const body = { name, start_date: start, end_date: end, is_current: current };

  return (
    <FormModal
      title={session ? `Edit ${session.name}` : "Add an academic session"}
      description="A school or college year, for example 2026-27. Classes belong to one."
      submitLabel={session ? "Save changes" : "Add session"}
      valid={name.trim().length >= 2 && Boolean(start) && Boolean(end) && end >= start}
      onClose={onClose}
      save={() =>
        session ? updateSession(instituteId, session.id, body) : createSession(instituteId, body)
      }
    >
      <TextField
        label="Name"
        required
        placeholder="2026-27"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          label="Starts"
          type="date"
          required
          value={start}
          onChange={(event) => setStart(event.target.value)}
        />
        <TextField
          label="Ends"
          type="date"
          required
          value={end}
          onChange={(event) => setEnd(event.target.value)}
        />
      </div>
      <Checkbox
        label="This is the current session"
        checked={current}
        onChange={(event) => setCurrent(event.target.checked)}
      />
    </FormModal>
  );
}

// --------------------------------------------------------------------------- branch

export function BranchActions({ branch, sessions }: { branch: Branch; sessions: Session[] }) {
  const canEdit = useCan("branch:update");
  const canArchive = useCan("branch:archive");
  const canAddClass = useCan("class:create");
  const [dialog, setDialog] = useState<"edit" | "class" | null>(null);

  if (!canEdit && !canArchive && !canAddClass) return null;
  return (
    <>
      <ActionBar>
        {canEdit && (
          <Button size="sm" variant="secondary" onClick={() => setDialog("edit")}>
            Edit branch
          </Button>
        )}
        {canAddClass && branch.status === "active" && (
          <Button size="sm" variant="secondary" onClick={() => setDialog("class")}>
            <Icon name="plus" className="size-3.5" />
            Add class
          </Button>
        )}
        {canArchive && (
          <ArchiveToggle
            name={branch.name}
            status={branch.status}
            archive={() => updateBranch(branch.institute_id, branch.id, { status: "archived" })}
            restore={() => updateBranch(branch.institute_id, branch.id, { status: "active" })}
            consequence="Its classes stop being offered, and roles given within it no longer apply."
          />
        )}
      </ActionBar>
      {dialog === "edit" && (
        <BranchEditor
          instituteId={branch.institute_id}
          branch={branch}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog === "class" && (
        <ClassEditor
          branch={branch}
          row={null}
          sessions={sessions}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}

function BranchEditor({
  instituteId,
  branch,
  onClose,
}: {
  instituteId: string;
  branch: Branch | null;
  onClose: () => void;
}) {
  const [name, setName] = useState(branch?.name ?? "");
  const [code, setCode] = useState(branch?.code ?? "");
  const [city, setCity] = useState(branch?.city ?? "");
  const [address, setAddress] = useState(branch?.address ?? "");

  return (
    <FormModal
      title={branch ? `Edit ${branch.name}` : "Add a branch"}
      description={
        branch
          ? "The code cannot change — records elsewhere refer to it."
          : "A campus, department or programme inside this institute."
      }
      submitLabel={branch ? "Save changes" : "Add branch"}
      valid={name.trim().length >= 2 && (Boolean(branch) || code.trim().length >= 2)}
      onClose={onClose}
      save={() =>
        branch
          ? updateBranch(instituteId, branch.id, {
              name,
              city: city || undefined,
              address: address || undefined,
            })
          : createBranch(instituteId, {
              name,
              code,
              city: city || undefined,
              address: address || undefined,
            })
      }
    >
      <TextField
        label="Branch name"
        required
        placeholder="MCA"
        value={name}
        onChange={(event) => setName(event.target.value)}
      />
      {!branch && (
        <TextField
          label="Short code"
          required
          placeholder="MCA"
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
        />
      )}
      <TextField label="City" value={city} onChange={(event) => setCity(event.target.value)} />
      <TextField
        label="Address"
        value={address}
        onChange={(event) => setAddress(event.target.value)}
      />
    </FormModal>
  );
}

// ---------------------------------------------------------------------------- class

export function ClassActions({ row }: { row: ClassRow }) {
  const canEdit = useCan("class:update");
  const canArchive = useCan("class:archive");
  const [editing, setEditing] = useState(false);

  if (!canEdit && !canArchive) return null;
  return (
    <>
      <ActionBar>
        {canEdit && (
          <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
            Edit class
          </Button>
        )}
        {canArchive && (
          <ArchiveToggle
            name={row.name}
            status={row.status}
            archive={() => updateClass(row.id, { status: "archived" })}
            restore={() => updateClass(row.id, { status: "active" })}
            consequence="It stops being offered for homework, enrolment and invitations."
          />
        )}
      </ActionBar>
      {editing && (
        <ClassEditor branch={null} row={row} sessions={[]} onClose={() => setEditing(false)} />
      )}
    </>
  );
}

function ClassEditor({
  branch,
  row,
  sessions,
  onClose,
}: {
  /** Set when creating: the branch the class goes into. */
  branch: Branch | null;
  /** Set when editing. */
  row: ClassRow | null;
  sessions: Session[];
  onClose: () => void;
}) {
  const [name, setName] = useState(row?.name ?? "");
  const [code, setCode] = useState("");
  const [section, setSection] = useState(row?.section ?? "");
  const [sessionId, setSessionId] = useState(
    sessions.find((session) => session.is_current)?.id ?? sessions[0]?.id ?? "",
  );
  const creating = row === null;
  const noSessions = creating && sessions.length === 0;

  return (
    <FormModal
      title={row ? `Edit ${row.name}` : `Add a class to ${branch?.name ?? "this branch"}`}
      submitLabel={row ? "Save changes" : "Add class"}
      valid={
        name.trim().length >= 2 && (!creating || (code.trim().length >= 2 && Boolean(sessionId)))
      }
      onClose={onClose}
      save={() =>
        row
          ? updateClass(row.id, { name, section: section || undefined })
          : createClass(branch!.id, {
              name,
              code,
              academic_session_id: sessionId,
              section: section || undefined,
            })
      }
    >
      {noSessions ? (
        <Alert tone="warning" title="There is no academic session yet">
          <p>
            Every class belongs to an academic session. Ask your Institute Admin to create one, then
            come back and add the class.
          </p>
        </Alert>
      ) : (
        <>
          <TextField
            label="Class name"
            required
            placeholder="MCA 1st Year"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          {creating && (
            <TextField
              label="Short code"
              required
              placeholder="MCA1A"
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
            />
          )}
          <TextField
            label="Section"
            placeholder="A"
            value={section}
            onChange={(event) => setSection(event.target.value)}
          />
          {creating && (
            <SelectField
              label="Academic session"
              required
              value={sessionId}
              onChange={(event) => setSessionId(event.target.value)}
              options={sessions.map((session) => ({
                value: session.id,
                label: `${session.name}${session.is_current ? " (current)" : ""}`,
              }))}
            />
          )}
        </>
      )}
    </FormModal>
  );
}
