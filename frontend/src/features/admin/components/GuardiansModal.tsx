import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Checkbox, TextField } from "@/components/Field";
import { Modal } from "@/components/Modal";
import {
  fetchGuardians,
  guardianKeys,
  linkGuardian,
  unlinkGuardian,
  userKeys,
} from "@/features/admin/api";
import type { UserSummary } from "@/features/auth/types";

/**
 * Who is responsible for a learner.
 *
 * The adult is named by email rather than chosen from a list, because the person doing
 * this is reading a school admission form, not browsing user accounts. If no account
 * exists for that address one is invited; if one does — the elder child is already here —
 * it is linked, so a parent with two children at the school keeps one password.
 */
export function GuardiansModal({
  student,
  open,
  onClose,
}: {
  student: UserSummary | null;
  open: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);

  const guardians = useQuery({
    queryKey: guardianKeys.of(student?.id ?? ""),
    queryFn: ({ signal }) => fetchGuardians(student!.id, signal),
    enabled: open && Boolean(student),
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: guardianKeys.of(student!.id) }),
      queryClient.invalidateQueries({ queryKey: userKeys.all }),
    ]);
  };

  const reset = () => {
    setEmail("");
    setFullName("");
    setRelationship("");
    setIsPrimary(false);
  };

  const add = useMutation({
    mutationFn: () =>
      linkGuardian(student!.id, {
        email,
        full_name: fullName || undefined,
        relationship: relationship || undefined,
        is_primary: isPrimary,
      }),
    onSuccess: async () => {
      await refresh();
      reset();
    },
  });

  const remove = useMutation({
    mutationFn: (parentId: string) => unlinkGuardian(student!.id, parentId),
    onSuccess: refresh,
  });

  const close = () => {
    reset();
    add.reset();
    remove.reset();
    onClose();
  };

  const error = add.error ?? remove.error;
  const rows = guardians.data ?? [];

  return (
    <Modal
      open={open}
      onClose={close}
      title="Parents and guardians"
      description={student ? `${student.full_name} · ${student.email}` : undefined}
      footer={
        <>
          <Button variant="secondary" onClick={close}>
            Close
          </Button>
          <Button
            disabled={email.trim().length < 3}
            loading={add.isPending}
            onClick={() => add.mutate()}
          >
            Add guardian
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        {error && (
          <Alert tone="danger" title="Could not change the guardians">
            <p>{error.message}</p>
          </Alert>
        )}

        <section className="space-y-2">
          <h3 className="text-sm font-semibold text-fg">Recorded guardians</h3>
          {rows.length > 0 ? (
            <ul className="space-y-2">
              {rows.map((row) => (
                <li
                  key={row.user_id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-fg">
                      {row.full_name}
                      {row.is_primary && (
                        <Badge tone="accent" className="ml-2">
                          first contact
                        </Badge>
                      )}
                    </p>
                    <p className="truncate text-xs text-fg-2">
                      {row.email}
                      {row.relationship ? ` · ${row.relationship}` : ""}
                    </p>
                    {/* Said plainly, because "invited" and "verified" are different
                        things and only one of them is consent. */}
                    {row.verified_at === null && (
                      <p className="mt-0.5 text-xs text-warn">
                        Has not signed in yet — they will confirm this themselves when they set
                        their password.
                      </p>
                    )}
                  </div>
                  <Button
                    size="sm"
                    variant="danger"
                    loading={remove.isPending && remove.variables === row.user_id}
                    onClick={() => remove.mutate(row.user_id)}
                  >
                    Remove
                  </Button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-fg-2">
              Nobody is recorded yet. A guardian can sign in to follow this learner&rsquo;s
              progress, and sees no other learner.
            </p>
          )}
        </section>

        <section className="space-y-3 border-t border-line pt-4">
          <TextField
            label="Their email address"
            type="email"
            hint="If they already have an account it is linked, not duplicated."
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="parent@example.com"
            required
          />
          <TextField
            label="Their name"
            hint="Only used when the account is new."
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Meera Sharma"
          />
          <TextField
            label="Relationship"
            hint="Mother, Father, Guardian — whatever is accurate."
            value={relationship}
            onChange={(event) => setRelationship(event.target.value)}
            placeholder="Mother"
          />
          <Checkbox
            checked={isPrimary}
            onChange={(event) => setIsPrimary(event.target.checked)}
            label="Contact this person first"
          />
        </section>
      </div>
    </Modal>
  );
}
