import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { PageHeader } from "@/components/PageHeader";
import { createInstituteWithAdmin, instituteKeys } from "@/features/admin/api";
import { email as emailSchema } from "@/features/auth/schemas";

const schema = z.object({
  name: z.string().min(2, "Enter the institute name.").max(120, "That name is too long."),
  code: z
    .string()
    .trim()
    .min(2, "Enter a short code.")
    .max(40, "That code is too long.")
    .regex(/^[A-Za-z0-9][A-Za-z0-9 _-]*$/, "Use letters, numbers, hyphen or underscore."),
  type: z.enum(["school", "college", "coaching", "academy"]),
  contact_email: z.union([emailSchema, z.literal("")]),
  admin_full_name: z.string().min(2, "Enter the administrator's name."),
  admin_email: emailSchema,
});

type Values = z.infer<typeof schema>;

/**
 * Create an institute together with its first Institute Admin (PRD §12).
 *
 * One call, one transaction on the server. Creating the institute and then failing to
 * invite its administrator would leave an institute nobody can run.
 */
export function CreateInstitutePage() {
  const queryClient = useQueryClient();

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      code: "",
      type: "college",
      contact_email: "",
      admin_full_name: "",
      admin_email: "",
    },
  });

  const submit = useMutation({
    mutationFn: (values: Values) =>
      createInstituteWithAdmin({
        institute: {
          name: values.name,
          code: values.code,
          type: values.type,
          contact_email: values.contact_email || undefined,
        },
        admin_full_name: values.admin_full_name,
        admin_email: values.admin_email,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: instituteKeys.all });
      form.reset();
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Add an institute"
        description="Create a school, college or coaching institute and invite the person who will run it."
      />

      {submit.isSuccess && (
        <Alert tone="success" title="Institute created">
          <p>
            {submit.data.institute.name} is ready. We have emailed {submit.data.admin_email} a code
            to set their password.
          </p>
        </Alert>
      )}

      <form
        noValidate
        className="grid gap-6 lg:grid-cols-2"
        onSubmit={form.handleSubmit((values) => submit.mutate(values))}
      >
        <Card>
          <CardHeader title="Institute details" />
          <CardBody className="space-y-4">
            {submit.error && (
              <Alert tone="danger">
                <p>{submit.error.message}</p>
              </Alert>
            )}

            <TextField
              label="Institute name"
              required
              autoFocus
              placeholder="ABC College"
              error={form.formState.errors.name?.message}
              {...form.register("name")}
            />

            <TextField
              label="Short code"
              required
              hint="A unique identifier, for example ABC. Saved in capitals."
              placeholder="ABC"
              error={form.formState.errors.code?.message}
              {...form.register("code")}
            />

            <SelectField
              label="Type"
              required
              options={[
                { value: "college", label: "College" },
                { value: "school", label: "School" },
                { value: "coaching", label: "Coaching institute" },
                { value: "academy", label: "Academy" },
              ]}
              error={form.formState.errors.type?.message}
              {...form.register("type")}
            />

            <TextField
              label="Contact email"
              type="email"
              placeholder="office@abccollege.edu"
              hint="Optional. Used for official correspondence."
              error={form.formState.errors.contact_email?.message}
              {...form.register("contact_email")}
            />
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="First Institute Admin"
            description="They will manage branches, classes, faculty and students."
          />
          <CardBody className="space-y-4">
            <TextField
              label="Full name"
              required
              placeholder="Priya Shah"
              error={form.formState.errors.admin_full_name?.message}
              {...form.register("admin_full_name")}
            />

            <TextField
              label="Email address"
              type="email"
              required
              placeholder="priya@abccollege.edu"
              hint="We will email a code so they can set their own password."
              error={form.formState.errors.admin_email?.message}
              {...form.register("admin_email")}
            />

            <Button type="submit" block size="lg" loading={submit.isPending}>
              Create institute
            </Button>
          </CardBody>
        </Card>
      </form>
    </div>
  );
}
