import { Navigate } from "react-router-dom";

import { useCan } from "@/features/auth/useAuth";
import { TeacherListPage } from "@/features/homework/pages/TeacherListPage";

/**
 * One sidebar entry, three audiences: teachers and admins get the class list, students
 * their board, parents their children's homework.
 */
export function HomeworkHomePage() {
  const canManage = useCan("homework:manage");
  const canSubmit = useCan("homework:submit");
  if (canManage) return <TeacherListPage />;
  if (canSubmit) return <Navigate to="/homework/mine" replace />;
  return <Navigate to="/homework/children" replace />;
}
