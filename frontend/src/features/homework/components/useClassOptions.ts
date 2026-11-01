import { useQueries, useQuery } from "@tanstack/react-query";

import { fetchClasses, fetchInstitutes, instituteKeys } from "@/features/admin/api";

export type ClassOption = { value: string; label: string; instituteId: string };

/**
 * Every class the signed-in person can see, across their institutes, as picker options.
 * The server narrows the lists (a teacher sees their own classes) and re-checks on save.
 */
export function useClassOptions(): { options: ClassOption[]; loading: boolean } {
  const institutes = useQuery({
    queryKey: instituteKeys.list(),
    queryFn: ({ signal }) => fetchInstitutes(signal),
  });
  const rows = institutes.data?.items ?? [];
  const classes = useQueries({
    queries: rows.map((institute) => ({
      queryKey: instituteKeys.classes(institute.id),
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        fetchClasses(institute.id, undefined, signal),
    })),
  });
  const many = rows.length > 1;
  const options = rows.flatMap((institute, index) =>
    (classes[index]?.data?.items ?? []).map((row) => ({
      value: row.id,
      instituteId: institute.id,
      label: [many ? institute.name : null, row.name, row.section].filter(Boolean).join(" · "),
    })),
  );
  return { options, loading: institutes.isLoading || classes.some((q) => q.isLoading) };
}
