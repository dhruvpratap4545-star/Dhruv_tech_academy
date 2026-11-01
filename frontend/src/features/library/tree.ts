import type { NodeKind } from "@/features/library/api";

const KINDS: NodeKind[] = ["track", "level", "subject", "unit", "chapter", "topic"];

/** Kinds that may sit directly below `parent`. A unit is optional, so a subject can hold
 * chapters directly. */
export function childKinds(parent: NodeKind): NodeKind[] {
  const index = KINDS.indexOf(parent);
  if (parent === "subject") return ["unit", "chapter"];
  return index >= 0 && index < KINDS.length - 1 ? [KINDS[index + 1]!] : [];
}
