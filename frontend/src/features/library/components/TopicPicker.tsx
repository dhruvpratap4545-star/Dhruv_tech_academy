import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Icon } from "@/components/Icon";
import type { LinkedNode } from "@/features/library/api";
import { libraryKeys, searchLibrary } from "@/features/library/api";
import { useT } from "@/features/i18n/useT";

/**
 * Pick syllabus nodes by searching for them. Used to link material to topics and to link
 * a class to its syllabus. Controlled: the parent holds the chosen nodes.
 */
export function TopicPicker({
  label,
  hint,
  value,
  onChange,
  max = 20,
}: {
  label: string;
  hint?: string;
  value: LinkedNode[];
  onChange: (nodes: LinkedNode[]) => void;
  max?: number;
}) {
  const { t } = useT();
  const [term, setTerm] = useState("");
  const q = term.trim();
  const results = useQuery({
    queryKey: libraryKeys.search({ q }),
    queryFn: ({ signal }) => searchLibrary({ q }, signal),
    enabled: q.length >= 2,
  });
  const chosen = new Set(value.map((n) => n.id));

  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-fg">{label}</p>
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {value.map((node) => (
            <li
              key={node.id}
              className="flex max-w-full items-center gap-1.5 rounded-full bg-accent-subtle py-1 pr-1 pl-3 text-xs text-accent"
            >
              <span className="truncate" title={node.path}>
                {node.name}
              </span>
              <button
                type="button"
                onClick={() => onChange(value.filter((n) => n.id !== node.id))}
                aria-label={t("library.classSyllabus.remove", { name: node.name })}
                className="rounded-full p-1 hover:bg-surface-2"
              >
                <Icon name="close" className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        type="search"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={t("library.form.findTopic")}
        aria-label={t("library.form.findTopic")}
        disabled={value.length >= max}
        className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-sm text-fg"
      />
      {hint && <p className="text-xs text-fg-2">{hint}</p>}
      {q.length >= 2 && results.data && (
        <ul className="max-h-56 divide-y divide-line overflow-y-auto rounded-lg border border-line">
          {results.data.nodes.length === 0 && (
            <li className="px-3 py-2 text-sm text-fg-2">{t("library.noResults")}</li>
          )}
          {results.data.nodes
            .filter((node) => !chosen.has(node.id))
            .map((node) => (
              <li key={node.id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange([...value, node]);
                    setTerm("");
                  }}
                  className="block w-full px-3 py-2 text-left hover:bg-surface-2"
                >
                  <span className="block text-sm text-fg">{node.name}</span>
                  <span className="block truncate text-xs text-fg-3">{node.path}</span>
                </button>
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
