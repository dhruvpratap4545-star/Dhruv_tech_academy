import type { IconName } from "@/components/Icon";
import type { CurrentUser } from "@/features/auth/types";
import type { Permission } from "@/lib/permissions";
import { can } from "@/lib/permissions";

/**
 * Every destination in the console, declared once (ADR-018).
 *
 * The sidebar and the "My access" screen both render from this list. They used to be two
 * hand-written lists, which is exactly how `/audit` ended up linked from two places with
 * no route behind it — a defect nobody could see by reading either file alone.
 *
 * `permission` is what the UI uses to decide whether to *offer* the destination. It is
 * never the authorization decision: the backend re-checks every request against the target
 * scope, and a page reached by typing its URL still returns an empty or forbidden result.
 */
export type NavItem = {
  id: string;
  to: string;
  label: string;
  icon: IconName;
  /** Omitted means everyone with an account can reach it. */
  permission?: Permission;
  /** One line explaining what the page is for, shown on "My access". */
  blurb: string;
};

export type NavGroup = { label: string; items: NavItem[] };

export const NAVIGATION: NavGroup[] = [
  {
    label: "Overview",
    items: [
      {
        id: "dashboard",
        to: "/",
        label: "Dashboard",
        icon: "home",
        blurb: "Activity and counts for everything you can see.",
      },
      {
        id: "my-access",
        to: "/my-access",
        label: "My access",
        icon: "key",
        blurb: "Your roles, where they apply, and exactly what they let you do.",
      },
    ],
  },
  {
    label: "Administration",
    items: [
      {
        id: "hierarchy",
        to: "/institutes",
        label: "Hierarchy",
        icon: "org",
        permission: "institute:read",
        blurb: "Institutes, branches, academic sessions and classes.",
      },
      {
        id: "users",
        to: "/users",
        label: "Users",
        icon: "users",
        permission: "user:read",
        blurb: "Everyone in your scope: invite, change role, suspend.",
      },
      {
        id: "roles",
        to: "/roles",
        label: "Roles & permissions",
        icon: "lock",
        permission: "role:read",
        blurb: "What each role allows, and the roles your institute has defined.",
      },
      {
        id: "audit",
        to: "/audit",
        label: "Audit log",
        icon: "log",
        permission: "audit:read",
        blurb: "Every security and administrative event, newest first.",
      },
    ],
  },
  {
    label: "Account",
    items: [
      {
        id: "settings",
        to: "/settings",
        label: "Settings",
        icon: "gear",
        blurb: "Your profile, password and appearance.",
      },
    ],
  },
];

/** Flat list, for anything that does not care about grouping. */
export const ALL_NAV_ITEMS: NavItem[] = NAVIGATION.flatMap((group) => group.items);

export function isReachable(user: CurrentUser | null | undefined, item: NavItem): boolean {
  return !item.permission || can(user, item.permission);
}

/**
 * The groups this person can actually use, with empty groups dropped.
 *
 * Nothing is returned as "present but locked". A list of doors you cannot open teaches
 * nobody anything except that the product is full of things they are not trusted with —
 * and "My access" already explains the boundary properly, in words.
 */
export function visibleNavigation(user: CurrentUser | null | undefined): NavGroup[] {
  return NAVIGATION.map((group) => ({
    ...group,
    items: group.items.filter((item) => isReachable(user, item)),
  })).filter((group) => group.items.length > 0);
}
