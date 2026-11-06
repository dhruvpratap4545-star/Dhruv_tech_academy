import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Checkbox, SelectField, TextField } from "@/components/Field";
import { Spinner } from "@/components/Spinner";
import {
  assignClassFaculty,
  enrolStudent,
  fetchClassFaculty,
  fetchClassStudents,
  fetchUsers,
  instituteKeys,
  removeClassFaculty,
  removeStudent,
  userKeys,
} from "@/features/admin/api";
import type { ClassRow } from "@/features/auth/types";
import { useCan } from "@/features/auth/useAuth";

/**
 * Who teaches a class, and who is enrolled in it.
 *
 * The pickers list people who already hold the Faculty or Student role in this institute,
 * because those are the only people the server will accept — offering anybody else would
 * just produce a refusal.
 */
export function ClassMembers({ row }: { row: ClassRow }) {
  const canReadFaculty = useCan("class:read");
  const canManageFaculty = useCan("class_faculty:manage");
  // The roster endpoint needs enrollment:manage, so nobody else asks for it.
  const canManageStudents = useCan("enrollment:manage");
  return (
    <>
      {canReadFaculty && <FacultySection row={row} canManage={canManageFaculty} />}
      {canManageStudents && <StudentSection row={row} />}
    </>
  );
}

function FacultySection({ row, canManage }: { row: ClassRow; canManage: boolean }) {
  const queryClient = useQueryClient();
  const key = instituteKeys.faculty(row.id);
  const members = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchClassFaculty(row.id, signal),
  });
  const filters = { institute_id: row.institute_id, role_key: "faculty", limit: 100 };
  const candidates = useQuery({
    queryKey: userKeys.list(filters),
    queryFn: ({ signal }) => fetchUsers(filters, signal),
    enabled: canManage,
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });

  const [userId, setUserId] = useState("");
  const [subject, setSubject] = useState("");
  const [classTeacher, setClassTeacher] = useState(false);

  const assign = useMutation({
    mutationFn: () =>
      assignClassFaculty(row.id, {
        user_id: userId,
        subject: subject || undefined,
        is_class_teacher: classTeacher,
      }),
    onSuccess: async () => {
      await refresh();
      setUserId("");
      setSubject("");
      setClassTeacher(false);
    },
  });
  const remove = useMutation({
    mutationFn: (memberId: string) => removeClassFaculty(row.id, memberId),
    onSuccess: refresh,
  });

  const taken = new Set((members.data ?? []).map((member) => member.user_id));
  const error = members.error ?? assign.error ?? remove.error;

  return (
    <Roster title="Faculty" loading={members.isLoading} error={error?.message}>
      {members.data?.length === 0 && <p className="text-sm text-fg-2">Nobody teaches it yet.</p>}
      {members.data && members.data.length > 0 && (
        <ul className="divide-y divide-line rounded-md border border-line">
          {members.data.map((member) => (
            <Member
              key={member.user_id}
              name={member.full_name}
              detail={[member.email, member.subject].filter(Boolean).join(" · ")}
              badge={member.is_class_teacher ? <Badge tone="accent">Class teacher</Badge> : null}
              onRemove={canManage ? () => remove.mutate(member.user_id) : undefined}
              removing={remove.isPending && remove.variables === member.user_id}
            />
          ))}
        </ul>
      )}
      {canManage && (
        <div className="space-y-3 rounded-md bg-surface-2 p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <SelectField
              label="Faculty member"
              placeholder={candidates.isLoading ? "Loading…" : "Choose a teacher"}
              value={userId}
              onChange={(event) => setUserId(event.target.value)}
              options={(candidates.data?.items ?? [])
                .filter((person) => !taken.has(person.id))
                .map((person) => ({ value: person.id, label: person.full_name }))}
            />
            <TextField
              label="Subject"
              placeholder="Mathematics"
              value={subject}
              onChange={(event) => setSubject(event.target.value)}
            />
          </div>
          <Checkbox
            label="Class teacher"
            checked={classTeacher}
            onChange={(event) => setClassTeacher(event.target.checked)}
          />
          <Button
            size="sm"
            disabled={!userId}
            loading={assign.isPending}
            onClick={() => assign.mutate()}
          >
            Assign faculty
          </Button>
        </div>
      )}
    </Roster>
  );
}

function StudentSection({ row }: { row: ClassRow }) {
  const queryClient = useQueryClient();
  const key = instituteKeys.students(row.id);
  const members = useQuery({
    queryKey: key,
    queryFn: ({ signal }) => fetchClassStudents(row.id, signal),
  });
  const filters = { institute_id: row.institute_id, role_key: "student", limit: 100 };
  const candidates = useQuery({
    queryKey: userKeys.list(filters),
    queryFn: ({ signal }) => fetchUsers(filters, signal),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: key });

  const [userId, setUserId] = useState("");
  const [rollNo, setRollNo] = useState("");

  const enrol = useMutation({
    mutationFn: () => enrolStudent(row.id, { user_id: userId, roll_no: rollNo || undefined }),
    onSuccess: async () => {
      await refresh();
      setUserId("");
      setRollNo("");
    },
  });
  const remove = useMutation({
    mutationFn: (studentId: string) => removeStudent(row.id, studentId),
    onSuccess: refresh,
  });

  const taken = new Set((members.data ?? []).map((member) => member.user_id));
  const error = members.error ?? enrol.error ?? remove.error;

  return (
    <Roster title="Students" loading={members.isLoading} error={error?.message}>
      {members.data?.length === 0 && <p className="text-sm text-fg-2">Nobody is enrolled yet.</p>}
      {members.data && members.data.length > 0 && (
        <ul className="divide-y divide-line rounded-md border border-line">
          {members.data.map((member) => (
            <Member
              key={member.user_id}
              name={member.full_name}
              detail={[member.roll_no && `Roll ${member.roll_no}`, member.email]
                .filter(Boolean)
                .join(" · ")}
              onRemove={() => remove.mutate(member.user_id)}
              removing={remove.isPending && remove.variables === member.user_id}
            />
          ))}
        </ul>
      )}
      <div className="space-y-3 rounded-md bg-surface-2 p-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField
            label="Student"
            placeholder={candidates.isLoading ? "Loading…" : "Choose a student"}
            value={userId}
            onChange={(event) => setUserId(event.target.value)}
            options={(candidates.data?.items ?? [])
              .filter((person) => !taken.has(person.id))
              .map((person) => ({
                value: person.id,
                label: `${person.full_name} (${person.email})`,
              }))}
          />
          <TextField
            label="Roll no"
            hint="Optional."
            value={rollNo}
            onChange={(event) => setRollNo(event.target.value)}
          />
        </div>
        <Button
          size="sm"
          disabled={!userId}
          loading={enrol.isPending}
          onClick={() => enrol.mutate()}
        >
          Enrol student
        </Button>
      </div>
    </Roster>
  );
}

function Roster({
  title,
  loading,
  error,
  children,
}: {
  title: string;
  loading: boolean;
  error?: string;
  children: ReactNode;
}) {
  return (
    <section aria-label={title} className="space-y-3 border-t border-line p-4">
      <h3 className="text-sm font-semibold text-fg">{title}</h3>
      {error && (
        <Alert tone="danger">
          <p>{error}</p>
        </Alert>
      )}
      {loading ? (
        <div className="flex justify-center py-4">
          <Spinner />
        </div>
      ) : (
        children
      )}
    </section>
  );
}

function Member({
  name,
  detail,
  badge,
  onRemove,
  removing,
}: {
  name: string;
  detail: string;
  badge?: ReactNode;
  onRemove?: () => void;
  removing: boolean;
}) {
  return (
    <li className="flex flex-wrap items-center gap-2 px-3 py-2">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-fg">
          {name} {badge}
        </p>
        <p className="truncate text-xs text-fg-2">{detail}</p>
      </div>
      {onRemove && (
        <Button
          size="sm"
          variant="ghost"
          aria-label={`Remove ${name}`}
          loading={removing}
          onClick={onRemove}
        >
          Remove
        </Button>
      )}
    </li>
  );
}
