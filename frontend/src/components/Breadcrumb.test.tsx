import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Breadcrumb } from "@/components/Breadcrumb";

const path = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ label: `Level ${i + 1}`, onSelect: vi.fn() }));

describe("Breadcrumb", () => {
  it("shows a short path in full", () => {
    render(<Breadcrumb items={path(3)} />);
    expect(screen.getByText("Level 1")).toBeInTheDocument();
    expect(screen.getByText("Level 3")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /hidden levels/i })).not.toBeInTheDocument();
  });

  it("folds the middle of a long path, keeping the first and last", () => {
    // Those two are what people navigate by: where this sits overall, and what they are
    // looking at now. Anything between can wait until asked for.
    render(<Breadcrumb items={path(5)} />);

    expect(screen.getByText("Level 1")).toBeInTheDocument();
    expect(screen.getByText("Level 5")).toBeInTheDocument();
    expect(screen.queryByText("Level 2")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /show 2 hidden levels/i })).toBeInTheDocument();
  });

  it("expands when the fold is tapped", () => {
    render(<Breadcrumb items={path(6)} />);
    fireEvent.click(screen.getByRole("button", { name: /hidden levels/i }));

    for (let i = 1; i <= 6; i++) {
      expect(screen.getByText(`Level ${i}`)).toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: /hidden levels/i })).not.toBeInTheDocument();
  });

  it("makes ancestors navigable and the current item not", () => {
    const items = path(3);
    items[2]!.onSelect = undefined as never;
    render(<Breadcrumb items={items} />);

    fireEvent.click(screen.getByText("Level 1"));
    expect(items[0]!.onSelect).toHaveBeenCalled();

    const current = screen.getByText("Level 3");
    expect(current.tagName).not.toBe("BUTTON");
    expect(current).toHaveAttribute("aria-current", "page");
  });

  it("keeps its overflow to itself", () => {
    // The containment chain is the whole point: without `min-w-0` a flex child refuses to
    // shrink below its content and the overflow escapes onto the document, which is what
    // made the page slide sideways on a phone.
    const { container } = render(<Breadcrumb items={path(8)} />);
    const nav = container.querySelector("nav")!;
    expect(nav.className).toContain("min-w-0");
    expect(nav.className).toContain("overflow-x-auto");
  });
});
