import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { TextField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import { PageHeader } from "@/components/PageHeader";
import { Spinner } from "@/components/Spinner";
import {
  archiveOrganisation,
  createOrganisation,
  fetchOrganisations,
  organisationKeys,
  updateOrganisation,
} from "@/features/admin/api";
import type { Organisation } from "@/features/auth/types";
import { useCan } from "@/features/auth/useAuth";

/**
 * Organisations: a group of institutes under one owner.
 *
 * "JSPM Group of Institutes", "MIT" — a university with several colleges, a trust running
 * several schools, a coaching brand with centres. Most institutes belong to none of these,
 * which is why the level is optional and why this screen says so rather than presenting an
 * empty table as though something were missing.
 */
export function OrganisationsPage() {
  const canCreate = useCan("organisation:create");
  const canArchive = useCan("organisation:archive");
  const canEdit = useCan("organisation:update");

  const [editing, setEditing] = useState<Organisation | "new" | null>(null);
  const [archiving, setArchiving] = useState<Organisation | null>(null);

  const queryClient = useQueryClient();
  const organisations = useQuery({
    queryKey: organisationKeys.list(),
    queryFn: ({ signal }) => fetchOrganisations(signal),
  });

  const archive = useMutation({
    mutationFn: (row: Organisation) => archiveOrganisation(row.id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: organisationKeys.all });
      setArchiving(null);
    },
  });

  // Clear the error with the dialog, or a refusal lingers over the next organisation.
  const stopArchiving = () => {
    setArchiving(null);
    archive.reset();
  };

  if (organisations.error) {
    return (
      <Alert tone="danger">
        <p>{organisations.error.message}</p>
      </Alert>
    );
  }

  const rows = organisations.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Administration"
        title="Organisations"
        description="A group of institutes under one owner. An administrator given a role here can run every institute inside it, and none outside."
        actions={
          canCreate && (
            <Button onClick={() => setEditing("new")}>
              <Icon name="plus" className="size-4" />
              New organisation
            </Button>
          )
        }
      />

      {organisations.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : rows.length === 0 ? (
        <Card className="px-4 py-12 text-center">
          <p className="text-sm font-medium text-fg">No organisations yet</p>
          <p className="mx-auto mt-1 max-w-lg text-sm text-fg-2">
            Most institutes stand alone and need nothing here. Create one when several institutes
            share an owner — a university with four colleges, or a trust running several schools —
            so one administrator can look after all of them.
          </p>
          {canCreate && (
            <Button variant="secondary" className="mt-4" onClick={() => setEditing("new")}>
              <Icon name="plus" className="size-4" />
              New organisation
            </Button>
          )}
        </Card>
      ) : (
        <Card>
          <ul className="divide-y divide-line">
            {rows.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-fg">
                    {row.name}
                    {row.status === "archived" && (
                      <Badge tone="neutral" className="ml-2">
                        archived
                      </Badge>
                    )}
                  </p>
                  <p className="mono text-xs text-fg-3">{row.code}</p>
                  <p className="num mt-1 text-xs text-fg-2">
                    {row.institute_count} {row.institute_count === 1 ? "institute" : "institutes"}
                    {row.contact_email ? ` · ${row.contact_email}` : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  {canEdit && (
                    <Button
                      size="sm"
                      variant="secondary"
                      className="press"
                      onClick={() => setEditing(row)}
                    >
                      Edit
                    </Button>
                  )}
                  {/* Only when it is empty. The server refuses otherwise, and a button
                      that always fails is worse than one that is not there. */}
                  {canArchive && row.status === "active" && row.institute_count === 0 && (
                    <Button
                      size="sm"
                      variant="danger"
                      className="press"
                      onClick={() => setArchiving(row)}
                    >
                      Archive
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {editing && (
        <OrganisationEditor
          organisation={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
        />
      )}

      <ConfirmDialog
        open={archiving !== null}
        onClose={stopArchiving}
        onConfirm={() => archiving && archive.mutate(archiving)}
        title={`Archive ${archiving?.name ?? "this organisation"}?`}
        confirmLabel="Archive it"
        pending={archive.isPending}
        error={archive.error?.message ?? null}
      >
        <p>It stops being offered when giving somebody an organisation-wide role.</p>
        <p>
          Nothing is deleted, and anybody already holding a role across it keeps that role until it
          is taken away.
        </p>
      </ConfirmDialog>
    </div>
  );
}

/** Create a new organisation, or rename one that exists. */
function OrganisationEditor({
  organisation,
  onClose,
}: {
  organisation: Organisation | null;
  onClose: () => void;
}) {
  const editing = organisation !== null;
  const queryClient = useQueryClient();

  const [name, setName] = useState(organisation?.name ?? "");
  const [code, setCode] = useState(organisation?.code ?? "");
  const [contactEmail, setContactEmail] = useState(organisation?.contact_email ?? "");
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: () =>
      editing
        ? updateOrganisation(organisation.id, {
            name,
            contact_email: contactEmail || undefined,
          })
        : createOrganisation({
            name,
            code,
            contact_email: contactEmail || undefined,
          }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: organisationKeys.all });
      onClose();
    },
    onError: (err: Error) => setError(err.message),
  });

  const valid = name.trim().length >= 2 && (editing || code.trim().length >= 2);

  return (
    <Modal
      open
      onClose={onClose}
      title={editing ? `Edit ${organisation.name}` : "New organisation"}
      description={
        editing
          ? "The code cannot change — records elsewhere refer to it."
          : "A group of institutes under one owner. You can add institutes to it afterwards."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!valid} loading={save.isPending} onClick={() => save.mutate()}>
            {editing ? "Save changes" : "Create organisation"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <Alert tone="danger">
            <p>{error}</p>
          </Alert>
        )}

        <TextField
          label="Name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="JSPM Group of Institutes"
          required
        />

        {!editing && (
          <TextField
            label="Short code"
            hint="A few letters, used in lists and reports. Cannot be changed afterwards."
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase())}
            placeholder="JSPM"
            required
          />
        )}

        <TextField
          label="Contact email"
          type="email"
          hint="Optional. Who to reach about the organisation as a whole."
          value={contactEmail}
          onChange={(event) => setContactEmail(event.target.value)}
          placeholder="office@jspm.example"
        />
      </div>
    </Modal>
  );
}
