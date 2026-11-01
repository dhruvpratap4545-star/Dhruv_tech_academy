import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Spinner } from "@/components/Spinner";
import { fetchMyBoard, homeworkKeys } from "@/features/homework/api";
import { BoardList } from "@/features/homework/components/BoardList";
import { HomeworkLayout } from "@/features/homework/components/HomeworkLayout";
import { TABS } from "@/features/homework/logic";
import { useT } from "@/features/i18n/useT";
import { cn } from "@/lib/cn";

/** The student's board: four tabs, soonest due first. Redo work shows under Pending. */
export function StudentBoardPage() {
  const { t } = useT();
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("pending");
  const board = useQuery({
    queryKey: homeworkKeys.mine(tab),
    queryFn: ({ signal }) => fetchMyBoard(tab, signal),
  });
  return (
    <HomeworkLayout title={t("homework.mine.title")} description={t("homework.mine.description")}>
      <div
        role="tablist"
        aria-label={t("homework.mine.title")}
        className="-mx-1 flex gap-1 overflow-x-auto pb-1"
      >
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={tab === item.value}
            onClick={() => setTab(item.value)}
            className={cn(
              "rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap",
              tab === item.value
                ? "bg-accent text-accent-fg"
                : "text-fg-2 hover:bg-surface-2 hover:text-fg",
            )}
          >
            {t(item.label)}
          </button>
        ))}
      </div>
      {board.isLoading && <Spinner />}
      {board.error && <Alert tone="danger">{board.error.message}</Alert>}
      {board.data && <BoardList rows={board.data} empty={t("homework.mine.empty")} />}
    </HomeworkLayout>
  );
}
