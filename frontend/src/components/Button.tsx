import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-accent-fg shadow-card hover:bg-accent-hover active:bg-accent-hover",
  secondary: "bg-surface text-fg border border-line hover:bg-surface-2 active:bg-surface-3",
  ghost: "text-fg-2 hover:bg-surface-2 hover:text-fg active:bg-surface-3",
  danger: "bg-bad text-white shadow-card hover:brightness-110 active:brightness-95",
};

const SIZES: Record<Size, string> = {
  // 44px tall at md: a comfortable touch target without a dedicated mobile variant.
  sm: "h-8 px-3 text-xs gap-1.5 rounded-md",
  md: "h-11 px-4 text-sm gap-2 rounded-lg",
  lg: "h-12 px-6 text-base gap-2 rounded-lg",
};

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  /** Fills the width of its container — the default on narrow screens for form submits. */
  block?: boolean;
  icon?: ReactNode;
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  block = false,
  icon,
  className,
  children,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;

  return (
    <button
      type={type}
      disabled={isDisabled}
      // Tells assistive tech the control is working, not broken.
      aria-busy={loading || undefined}
      className={cn(
        "relative inline-flex items-center justify-center font-semibold whitespace-nowrap",
        "transition-[background-color,box-shadow,opacity] duration-(--duration-fast)",
        "disabled:pointer-events-none disabled:opacity-55",
        VARIANTS[variant],
        SIZES[size],
        block && "w-full",
        className,
      )}
      {...rest}
    >
      {loading && <Spinner />}
      {/* The label stays mounted and reserves its width, so the button does not resize
          when it starts loading and shift everything beside it. */}
      <span className={cn("inline-flex items-center gap-2", loading && "invisible")}>
        {icon}
        {children}
      </span>
    </button>
  );
}

function Spinner() {
  return (
    <svg
      className="absolute size-4 animate-spin"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.25" />
      <path
        d="M22 12a10 10 0 0 1-10 10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
