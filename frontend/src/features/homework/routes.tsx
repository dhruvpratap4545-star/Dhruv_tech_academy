import type { ReactElement } from "react";

import type { NavItem } from "@/app/navigation";
import { ChildrenPage } from "@/features/homework/pages/ChildrenPage";
import { HomeworkDetailPage } from "@/features/homework/pages/HomeworkDetailPage";
import { HomeworkFormPage } from "@/features/homework/pages/HomeworkFormPage";
import { HomeworkHomePage } from "@/features/homework/pages/HomeworkHomePage";
import { ReportsPage } from "@/features/homework/pages/ReportsPage";
import { StudentBoardPage } from "@/features/homework/pages/StudentBoardPage";
import type { Permission } from "@/lib/permissions";

/** Routes for the homework screens, mounted inside the signed-in shell by app/routes.tsx. */
export const HOMEWORK_ROUTES: { path: string; permission?: Permission; element: ReactElement }[] = [
  { path: "/homework", permission: "homework:read", element: <HomeworkHomePage /> },
  { path: "/homework/new", permission: "homework:manage", element: <HomeworkFormPage /> },
  { path: "/homework/mine", permission: "homework:submit", element: <StudentBoardPage /> },
  { path: "/homework/children", permission: "homework:read", element: <ChildrenPage /> },
  { path: "/homework/reports", permission: "homework:report", element: <ReportsPage /> },
  { path: "/homework/:id", permission: "homework:read", element: <HomeworkDetailPage /> },
  { path: "/homework/:id/edit", permission: "homework:manage", element: <HomeworkFormPage /> },
];

/**
 * Sidebar entries, shown under the "Learning" group. One "Homework" entry serves every
 * audience — `/homework` sends teachers, students and parents to their own screen — so
 * nobody sees a link meant for someone else. English labels: the sidebar is not translated.
 */
export const HOMEWORK_NAV: NavItem[] = [
  {
    id: "homework",
    to: "/homework",
    label: "Homework",
    icon: "clipboard",
    permission: "homework:read",
    blurb: "Set, submit and check homework; parents follow their children.",
  },
  {
    id: "homework-reports",
    to: "/homework/reports",
    label: "Homework reports",
    icon: "log",
    permission: "homework:report",
    blurb: "Completion rate by class, subject and teacher.",
  },
];
