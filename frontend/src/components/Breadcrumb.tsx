import { useState } from "react";

import { Icon } from "@/components/Icon";
import { cn } from "@/lib/cn";

export type Crumb = {
  label: string;
  /** Omit for the current item, which is not a link to anywhere. */
  onSelect?: () => void;
};

/** Beyond this, the middle is folded away. First and last always stay visible. */
const MAX_VISIBLE = 4;

/**
 * The path through the hierarchy: Platform → Institute → Branch → Session → Class.
 *
 * Two things make this harder than it looks, and both only show up on a phone.
 *
 * **It must scroll without taking the page with it.** A long path is wider than 360px
 * whatever you do, so it scrolls — but inside its own container. `min-w-0` on the wrapper
 * is what actually makes that work: without it a flex child refuses to shrink below its
 * content, the overflow escapes, and the whole page slides sideways instead.
 *
 * **It must not need scrolling for the common case.** So past four levels the middle
 * collapses to a "…" button. The first and last are always visible, because those are the
 * two people navigate by — where this sits overall, and what they are looking at now.
 * Tapping the button expands it rather than opening a menu: a menu would be a second thing
 * to learn, and the expanded path is the thing they wanted anyway.
 */
export function Breadcrumb({ items, className }: { items: Crumb[]; className?: string }) {
  const [expanded, setExpanded] = useState(false);

  // Collapse again when the trail changes. "Expanded" is a decision about *this* path —
  // somebody wanted to see the middle of where they were standing. Carrying it to the next
  // page means every trail afterwards opens fully, including the ones short enough that the
  // control is not even on screen to put back.
  const signature = items.map((item) => item.label).join(" › ");
  const [lastSignature, setLastSignature] = useState(signature);
  if (signature !== lastSignature) {
    setLastSignature(signature);
    if (expanded) setExpanded(false);
  }

  const collapsible = items.length > MAX_VISIBLE;

  // Keep the first and the last two; fold everything between them.
  const shown: (Crumb | "ellipsis")[] =
    collapsible && !expanded ? [items[0]!, "ellipsis", ...items.slice(-2)] : items;

  return (
    <nav
      aria-label="Hierarchy"
      className={cn(
        // The containment chain: `min-w-0` lets this shrink inside a flex parent, and
        // `overflow-x-auto` keeps the overflow here instead of on the document.
        "min-w-0 overflow-x-auto",
        // No visible scrollbar on a one-line strip; it would cost more height than it
        // earns. The content still scrolls by touch and by shift-wheel.
        "[scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
        className,
      )}
    >
      <ol className="flex w-max items-center gap-1 text-sm">
        {shown.map((item, index) => (
          <li
            key={item === "ellipsis" ? "ellipsis" : `${item.label}-${index}`}
            className="flex items-center gap-1"
          >
            {index > 0 && <Icon name="chevron" className="size-3 shrink-0 text-fg-3" aria-hidden />}

            {item === "ellipsis" ? (
              <button
                type="button"
                onClick={() => setExpanded(true)}
                aria-label={`Show ${items.length - 3} hidden levels`}
                className="rounded-xs px-1.5 py-0.5 font-semibold text-fg-3 hover:bg-surface-2 hover:text-fg"
              >
                …
              </button>
            ) : item.onSelect ? (
              <button
                type="button"
                onClick={item.onSelect}
                className="rounded-xs px-1 py-0.5 whitespace-nowrap text-fg-2 hover:bg-surface-2 hover:text-fg"
              >
                {item.label}
              </button>
            ) : (
              <span
                aria-current="page"
                className="px-1 py-0.5 font-semibold whitespace-nowrap text-fg"
              >
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
