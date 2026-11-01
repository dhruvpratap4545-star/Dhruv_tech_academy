import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Button } from "@/components/Button";
import type { LinkedNode } from "@/features/library/api";
import { fetchClassSyllabus, libraryKeys, setClassSyllabus } from "@/features/library/api";
import { TopicPicker } from "@/features/library/components/TopicPicker";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * Which parts of the syllabus a class follows ("Class 10-A uses CBSE › Class 10").
 * Students and parents see only the subtrees linked here. Saving needs `class:update`;
 * the server refuses anyone else.
 */
export function ClassSyllabusPicker({ classId }: { classId: string }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const linked = useQuery({
    queryKey: libraryKeys.classSyllabus(classId),
    queryFn: ({ signal }) => fetchClassSyllabus(classId, signal),
  });
  const [draft, setDraft] = useState<LinkedNode[] | null>(null);
  const nodes = draft ?? linked.data?.nodes ?? [];
  const save = useMutation({
    mutationFn: () =>
      setClassSyllabus(
        classId,
        nodes.map((n) => n.id),
      ),
    onSuccess: (data) => {
      queryClient.setQueryData(libraryKeys.classSyllabus(classId), data);
      setDraft(null);
    },
  });

  if (linked.error instanceof ApiError) return <Alert tone="danger">{linked.error.message}</Alert>;
  return (
    <div className="space-y-3">
      <TopicPicker
        label={t("library.classSyllabus.linked")}
        hint={nodes.length === 0 ? t("library.classSyllabus.none") : undefined}
        value={nodes}
        onChange={setDraft}
      />
      {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
      <Button disabled={draft === null} loading={save.isPending} onClick={() => save.mutate()}>
        {t("common.save")}
      </Button>
    </div>
  );
}
