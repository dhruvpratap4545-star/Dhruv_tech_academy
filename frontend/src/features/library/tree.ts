import type { Level, NodeKind } from "@/features/library/api";
import { LEVELS } from "@/features/library/api";

/** The one level that sits directly below `parent` (`null` for the top), or none below a
 * topic. A section from before the four levels (a unit or chapter) takes nothing new. */
export function nextLevel(parent: NodeKind | null): Level | null {
  if (parent === null) return "track";
  const index = LEVELS.indexOf(parent as Level);
  return index >= 0 && index < LEVELS.length - 1 ? LEVELS[index + 1]! : null;
}
