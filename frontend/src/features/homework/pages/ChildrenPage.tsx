import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Card } from "@/components/Card";
import { SelectField } from "@/components/Field";
import { Spinner } from "@/components/Spinner";
import { fetchUsers, userKeys } from "@/features/admin/api";
import { useCurrentUser } from "@/features/auth/useAuth";
import { fetchChildBoard, homeworkKeys } from "@/features/homework/api";
import { BoardList } from "@/features/homework/components/BoardList";
import { HomeworkLayout } from "@/features/homework/components/HomeworkLayout";
import { useT } from "@/features/i18n/useT";

/**
 * A parent's view. The users list already confines a parent to the children they are the
 * recorded guardian of, and the homework endpoint checks the link again on every request.
 */
export function ChildrenPage() {
  const { t } = useT();
  const me = useCurrentUser();
  const filters = { role_key: "student", limit: 50 };
  const people = useQuery({
    queryKey: userKeys.list(filters),
    queryFn: ({ signal }) => fetchUsers(filters, signal),
  });
  const children = (people.data?.items ?? []).filter((person) => person.id !== me?.id);
  const [chosen, setChosen] = useState("");
  const childId = chosen || children[0]?.id || "";
  const board = useQuery({
    queryKey: homeworkKeys.child(childId),
    queryFn: ({ signal }) => fetchChildBoard(childId, signal),
    enabled: Boolean(childId),
  });

  return (
    <HomeworkLayout
      title={t("homework.children.title")}
      description={t("homework.children.description")}
    >
      {people.isLoading && <Spinner />}
      {people.data && children.length === 0 && (
        <Alert tone="info">{t("homework.children.none")}</Alert>
      )}
      {children.length > 1 && (
        <Card className="p-4">
          <SelectField
            label={t("homework.children.child")}
            value={childId}
            onChange={(e) => setChosen(e.target.value)}
            options={children.map((child) => ({ value: child.id, label: child.full_name }))}
          />
        </Card>
      )}
      {board.isLoading && <Spinner />}
      {board.error && <Alert tone="danger">{board.error.message}</Alert>}
      {board.data && <BoardList rows={board.data} empty={t("homework.mine.empty")} />}
    </HomeworkLayout>
  );
}
