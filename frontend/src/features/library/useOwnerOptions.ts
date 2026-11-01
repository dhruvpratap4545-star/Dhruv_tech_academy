import { useQuery } from "@tanstack/react-query";

import { fetchInstitutes, instituteKeys } from "@/features/admin/api";
import { useCurrentUser } from "@/features/auth/useAuth";
import { useT } from "@/features/i18n/useT";
import { isPlatformStaff } from "@/lib/permissions";

/**
 * Which library a new node or item belongs to. Platform staff may write the master
 * library ("" here, sent as no institute); everyone else writes their own institute's.
 * The list of institutes is already scoped by the server.
 */
export function useOwnerOptions(): { value: string; label: string }[] {
  const { t } = useT();
  const user = useCurrentUser();
  const platform = isPlatformStaff(user);
  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
  });
  return [
    ...(platform ? [{ value: "", label: t("library.manage.master") }] : []),
    ...(institutes.data?.items ?? [])
      .filter((i) => i.status === "active")
      .map((i) => ({ value: i.id, label: i.name })),
  ];
}
