import { useQuery } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Icon } from "@/components/Icon";
import { globalSearch, searchKeys } from "@/features/admin/api";
import type { SearchHit } from "@/features/auth/types";
import { cn } from "@/lib/cn";

/**
 * One search box over people, institutes, branches and classes.
 *
 * The server does the scoping — it returns only what this person is already entitled to
 * see, and omits whole groups they have no permission for. Nothing is filtered here, both
 * because client-side filtering of server data is not a control, and because an empty
 * group would itself leak that the category exists.
 *
 * Keyboard first: Ctrl/Cmd+K to open, arrows to move, Enter to go, Escape to dismiss.
 * Administrators live in this box, and reaching for the mouse for every lookup is the
 * difference between a tool and a chore.
 */
export function GlobalSearch() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();

  // Debounced so a four-letter name is one request, not four.
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(term.trim()), 200);
    return () => clearTimeout(timer);
  }, [term]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const results = useQuery({
    queryKey: searchKeys.query(debounced),
    queryFn: ({ signal }) => globalSearch(debounced, signal),
    enabled: debounced.length >= 2,
    staleTime: 15_000,
  });

  const hits: SearchHit[] = results.data?.groups.flatMap((group) => group.items) ?? [];

  // Keep the highlight in range as results change, without an effect writing state.
  const [lastHitCount, setLastHitCount] = useState(hits.length);
  if (hits.length !== lastHitCount) {
    setLastHitCount(hits.length);
    if (active >= hits.length) setActive(0);
  }

  const showPanel = open && debounced.length >= 2;

  function go(hit: SearchHit | undefined) {
    if (!hit) return;
    setOpen(false);
    setTerm("");
    inputRef.current?.blur();
    navigate(hit.href);
  }

  return (
    <div className="relative min-w-0 flex-1 sm:max-w-md">
      <div className="relative">
        <Icon
          name="search"
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-3"
        />
        <input
          ref={inputRef}
          type="search"
          value={term}
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label="Search people, institutes and classes"
          placeholder="Search people, institutes, classes…"
          onChange={(event) => {
            setTerm(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          // A click inside the panel moves focus before the click lands, so the close is
          // deferred a tick rather than cancelling the navigation that is about to happen.
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setOpen(false);
              inputRef.current?.blur();
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((index) => Math.min(index + 1, hits.length - 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((index) => Math.max(index - 1, 0));
            } else if (event.key === "Enter") {
              event.preventDefault();
              go(hits[active]);
            }
          }}
          className={cn(
            "h-9 w-full rounded-sm border border-line bg-surface-2 pr-10 pl-9 text-sm text-fg",
            "placeholder:text-fg-3 focus:border-accent focus:bg-surface focus:outline-none",
            "[&::-webkit-search-cancel-button]:hidden",
          )}
        />
        <kbd className="pointer-events-none absolute top-1/2 right-2.5 hidden -translate-y-1/2 rounded-xs border border-line px-1.5 py-0.5 text-[0.65rem] font-medium text-fg-3 sm:block">
          Ctrl K
        </kbd>
      </div>

      {showPanel && (
        <div
          id={listId}
          role="listbox"
          className={cn(
            "z-50 max-h-[22rem] overflow-y-auto rounded-md border border-line bg-surface shadow-lg",
            // On a phone the input is squeezed between the menu button and the account
            // controls, so a panel the width of the input truncates every name to
            // "Rohit Me…". There it is pinned to the viewport instead, just under the
            // topbar — anchoring it to the input would push it off one edge or the other.
            "fixed inset-x-3 top-14",
            // From `sm` the input is wide enough to hang the panel off directly.
            "sm:absolute sm:inset-x-0 sm:top-full sm:mt-1.5",
          )}
        >
          {results.isLoading && <p className="px-3 py-3 text-sm text-fg-3">Searching…</p>}

          {!results.isLoading && hits.length === 0 && (
            <p className="px-3 py-3 text-sm text-fg-3">
              Nothing matching “{debounced}” that you can see.
            </p>
          )}

          {results.data?.groups.map((group) => (
            <div key={group.kind}>
              <p className="eyebrow border-b border-line bg-surface-2 px-3 py-1.5">{group.label}</p>
              <ul>
                {group.items.map((hit) => {
                  const index = hits.indexOf(hit);
                  return (
                    <li key={`${group.kind}-${hit.id}`}>
                      <button
                        type="button"
                        role="option"
                        aria-selected={index === active}
                        onMouseEnter={() => setActive(index)}
                        onClick={() => go(hit)}
                        className={cn(
                          "flex w-full items-center gap-2.5 px-3 py-2 text-left",
                          index === active ? "bg-accent-soft" : "hover:bg-surface-2",
                        )}
                      >
                        <Icon
                          name={ICON_FOR[group.kind] ?? "search"}
                          className="size-4 text-fg-3"
                        />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-fg">
                            {hit.title}
                          </span>
                          {hit.subtitle && (
                            <span className="mono block truncate text-xs text-fg-3">
                              {hit.subtitle}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const ICON_FOR: Record<string, "user" | "building" | "org" | "class"> = {
  user: "user",
  institute: "building",
  branch: "org",
  class: "class",
};
