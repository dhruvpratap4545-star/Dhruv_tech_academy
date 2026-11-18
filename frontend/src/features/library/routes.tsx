import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";

import type { NavItem } from "@/app/navigation";
import { LibraryPage } from "@/features/library/pages/LibraryPage";
import { SyllabusManagerPage } from "@/features/library/pages/SyllabusManagerPage";
import type { Permission } from "@/lib/permissions";

/** Routes for the library screens, mounted inside the signed-in shell by app/routes.tsx. */
export const LIBRARY_ROUTES: { path: string; permission?: Permission; element: ReactElement }[] = [
  { path: "/library", permission: "library:read", element: <LibraryPage /> },
  { path: "/library/node/:nodeId", permission: "library:read", element: <LibraryPage /> },
  // Material is added from the section it belongs to; there is no review queue any more.
  { path: "/library/review", element: <Navigate to="/library" replace /> },
  { path: "/library/manage", permission: "library:manage", element: <SyllabusManagerPage /> },
];

/**
 * Sidebar entries, shown under the "Learning" group. One entry for the library itself;
 * the syllabus manager is a tab inside it, offered to those who may use it.
 * The sidebar labels are English like the rest of the sidebar, which is not translated
 * in Milestone 1.
 */
export const LIBRARY_NAV: NavItem[] = [
  {
    id: "library",
    to: "/library",
    label: "Library",
    icon: "book",
    permission: "library:read",
    blurb: "Browse your syllabus and the study material on each topic.",
  },
];
