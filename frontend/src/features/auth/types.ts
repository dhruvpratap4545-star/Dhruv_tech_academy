/** Shapes the API returns. Mirrors the backend Pydantic schemas (PRD §8). */

/**
 * The six built-in role keys.
 *
 * Not a closed set any more: an institute can define its own roles, whose keys
 * are namespaced like `abc.lab_assistant`. `RoleKey` is therefore a *hint* — it gives
 * autocomplete and catches typos on the built-ins while still accepting a custom key.
 */
export type BuiltInRoleKey =
  | "super_admin"
  | "platform_admin"
  | "institute_admin"
  | "branch_admin"
  | "faculty"
  | "parent"
  | "student";

export type RoleKey = BuiltInRoleKey | (string & {});

export type UserStatus = "invited" | "active" | "suspended";

export type Theme = "light" | "dark" | "system";

export type RoleAssignment = {
  role_key: RoleKey;
  role_name: string;
  /** Comes from the server. A custom role has a key this build has never seen, so rank
   * can never be looked up locally. */
  rank: number;
  institute_id: string | null;
  branch_id: string | null;
  /** Names travel with the ids so a list needs no lookup request per row. */
  institute_name: string | null;
  branch_name: string | null;
};

/** `GET /me/overview` — real counts for the dashboard, scoped to the caller. */
export type Overview = {
  users_total: number;
  users_active: number;
  users_invited: number;
  users_suspended: number;
  institutes_total: number;
  security_events_24h: number;
};

export type AuditEntry = {
  id: string;
  action: string;
  actor_user_id: string | null;
  target_type: string | null;
  target_id: string | null;
  institute_id: string | null;
  ip: string | null;
  metadata: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string;
};

export type Preferences = {
  theme: Theme;
  language: string;
};

/** `GET /me` — identity, what the UI may offer, and where. */
export type CurrentUser = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  status: UserStatus;
  permissions: string[];
  roles: RoleAssignment[];
  institute_ids: string[];
  preferences: Preferences;
};

export type LoginResponse = {
  user_id: string;
  full_name: string;
  requires_institute_choice: boolean;
};

export type MessageResponse = { message: string };

export type VerifyOtpResponse = {
  reset_token: string;
  expires_in_seconds: number;
};

/** `PATCH /me` and the user list rows return this — note it carries no permissions. */
export type UserProfile = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  status: UserStatus;
  last_login_at: string | null;
  created_at: string;
};

export type UserSummary = UserProfile & { roles: RoleAssignment[] };

export type Institute = {
  id: string;
  name: string;
  code: string;
  type: "school" | "college" | "coaching" | "academy";
  status: "active" | "archived";
  contact_email: string | null;
  logo_url: string | null;
  is_system: boolean;
  created_at: string;
};

export type Branch = {
  id: string;
  institute_id: string;
  name: string;
  code: string;
  city: string | null;
  address: string | null;
  status: "active" | "archived";
  created_at: string;
};

export type Session = {
  id: string;
  institute_id: string;
  name: string;
  start_date: string;
  end_date: string;
  is_current: boolean;
  created_at: string;
};

export type ClassRow = {
  id: string;
  institute_id: string;
  branch_id: string;
  academic_session_id: string;
  name: string;
  code: string;
  section: string | null;
  status: "active" | "archived";
  created_at: string;
};

export type AssignableRole = {
  key: RoleKey;
  name: string;
  scope_level: "platform" | "institute" | "branch";
  rank: number;
};


// ----------------------------------------------------------------- access control

/** `GET /roles` — the catalogue, with what each role allows. */
export type Role = {
  id: string;
  key: RoleKey;
  name: string;
  description: string | null;
  scope_level: "platform" | "institute" | "branch";
  rank: number;
  is_system: boolean;
  is_active: boolean;
  institute_id: string | null;
  /** The effective set for the institute being viewed. */
  permissions: string[];
  /** True when this institute's view differs from the role's own definition. */
  customised_here: boolean;
  holder_count: number;
  /** May the caller edit the role's own definition? Custom roles only. */
  editable: boolean;
  /** May the caller adjust it for the institute being viewed? Built-ins included. */
  customisable: boolean;
};

/** `GET /permissions` */
export type PermissionInfo = {
  key: string;
  description: string;
  group: string;
  module_key: string;
  resource: string;
  action: string;
};

/** One exception that applies to one person. */
export type Grant = {
  id: string;
  permission: string;
  description: string;
  effect: "allow" | "deny";
  institute_id: string | null;
  branch_id: string | null;
  scope_label: string;
  reason: string;
  expires_at: string | null;
  expired: boolean;
  granted_by_name: string | null;
  created_at: string;
};

export type EffectivePermission = {
  key: string;
  description: string;
  group: string;
  granted: boolean;
  scope_label: string;
  source: "role" | "direct" | "blocked" | "none";
};

/** `GET /me/access` */
export type MyAccess = {
  roles: {
    key: RoleKey;
    name: string;
    rank: number;
    scope_level: string;
    scope_label: string;
    institute_id: string | null;
    branch_id: string | null;
  }[];
  permissions: EffectivePermission[];
  granted_count: number;
  total_count: number;
  can_grant_roles: string[];
  direct_grants: Grant[];
};

// ------------------------------------------------------------------------ search

export type SearchHit = { id: string; title: string; subtitle: string | null; href: string };
export type SearchGroup = { kind: string; label: string; items: SearchHit[] };
export type SearchResults = { query: string; groups: SearchGroup[] };

// ------------------------------------------------------------------- sign-in stats

export type DailySignins = {
  day: string;
  successful: number;
  failed: number;
  locked: number;
};

export type SigninStats = {
  days: DailySignins[];
  total_successful: number;
  total_failed: number;
  total_locked: number;
};
