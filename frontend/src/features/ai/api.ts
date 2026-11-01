/** AI Control Room API (`/ai`). Shapes mirror backend/app/modules/ai/schemas.py. */

import type { Page } from "@/lib/api";
import { apiDownload, apiFetch, query } from "@/lib/api";

export type AiSettings = {
  global_enabled: boolean;
  alert_thresholds: number[];
  usd_to_inr: number;
  log_prompts: boolean;
  updated_at: string;
};

export type AiProviderInfo = { name: string; configured: boolean; fake_mode: boolean };

export type AiModel = {
  id: string;
  provider: "gemini" | "anthropic" | "fake";
  model_id: string;
  display_name: string;
  input_price_per_mtok_usd: number;
  output_price_per_mtok_usd: number;
  enabled: boolean;
};

export type AiFeature = {
  key: string;
  name: string;
  model_id: string;
  fallback_model_id: string | null;
  max_output_tokens: number;
  system_prompt: string;
  safety_level: "standard" | "kids";
  cache_ttl_hours: number;
  enabled: boolean;
};

export type AiBudget = {
  scope: "platform" | "institute";
  institute_id: string | null;
  institute_name: string | null;
  month: string;
  limit_tokens: number | null;
  limit_paise: number | null;
  used_tokens: number;
  used_paise: number;
  percent_used: number | null;
  on_exceed: "block" | "fallback";
  alerts_sent: number[];
  feature_limits: Record<string, number>;
  feature_used_paise: Record<string, number>;
  disabled_features: string[];
  enabled: boolean;
  configured: boolean;
};

export type AiRoleLimit = {
  role_key: string;
  platform_default: number;
  institute_value: number | null;
  effective: number;
};

export type AiUsageRow = {
  id: string;
  created_at: string;
  institute_id: string | null;
  user_id: string;
  role_key: string | null;
  feature_key: string;
  provider: string | null;
  model_id: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_paise: number;
  latency_ms: number;
  status: "ok" | "blocked" | "error" | "cached";
  block_reason: string | null;
  fallback_used: boolean;
};

export type UsageTotals = {
  requests: number;
  tokens: number;
  cost_paise: number;
  blocked: number;
  errors: number;
};

export type UsageGroup = {
  key: string | null;
  label: string;
  requests: number;
  tokens: number;
  cost_paise: number;
};

export type UsageSummary = {
  today: UsageTotals;
  month: UsageTotals;
  by_feature: UsageGroup[];
  by_institute: UsageGroup[];
  trend: { day: string; requests: number; cost_paise: number }[];
  budget: AiBudget | null;
};

export type PlaygroundResult = {
  text: string;
  status: string;
  model_id: string;
  input_tokens: number;
  output_tokens: number;
  cost_paise: number;
  fallback_used: boolean;
  safety_blocked: boolean;
  redactions: number;
  usage_id: string | null;
};

export type UsageFilters = {
  institute_id?: string;
  feature?: string;
  status?: string;
  date_from?: string;
  date_to?: string;
  cursor?: string;
  limit?: number;
};

export const aiKeys = {
  all: ["ai"] as const,
  settings: ["ai", "settings"] as const,
  providers: ["ai", "providers"] as const,
  models: ["ai", "models"] as const,
  features: ["ai", "features"] as const,
  platformBudget: ["ai", "budgets", "platform"] as const,
  instituteBudgets: ["ai", "budgets", "institutes"] as const,
  roleLimits: (instituteId?: string) => ["ai", "role-limits", instituteId ?? "platform"] as const,
  usage: (filters: UsageFilters) => ["ai", "usage", filters] as const,
  summary: (instituteId?: string) => ["ai", "summary", instituteId ?? "all"] as const,
};

export const fetchSettings = (signal?: AbortSignal) =>
  apiFetch<AiSettings>("/ai/settings", { signal });
export const updateSettings = (body: Partial<AiSettings>) =>
  apiFetch<AiSettings>("/ai/settings", { method: "PUT", body });

export const fetchProviders = (signal?: AbortSignal) =>
  apiFetch<AiProviderInfo[]>("/ai/providers", { signal });

export const fetchModels = (signal?: AbortSignal) => apiFetch<AiModel[]>("/ai/models", { signal });
export const createModel = (body: Omit<AiModel, "id">) =>
  apiFetch<AiModel>("/ai/models", { method: "POST", body });
export const updateModel = (
  id: string,
  body: Partial<Omit<AiModel, "id" | "provider" | "model_id">>,
) => apiFetch<AiModel>(`/ai/models/${id}`, { method: "PATCH", body });

export const fetchFeatures = (signal?: AbortSignal) =>
  apiFetch<AiFeature[]>("/ai/features", { signal });
export const updateFeature = (key: string, body: Partial<Omit<AiFeature, "key" | "name">>) =>
  apiFetch<AiFeature>(`/ai/features/${key}`, { method: "PATCH", body });

export const fetchPlatformBudget = (signal?: AbortSignal) =>
  apiFetch<AiBudget>("/ai/budgets/platform", { signal });
export const updatePlatformBudget = (body: {
  limit_tokens: number | null;
  limit_paise: number | null;
  on_exceed: "block" | "fallback";
}) => apiFetch<AiBudget>("/ai/budgets/platform", { method: "PUT", body });

export const fetchInstituteBudgets = (signal?: AbortSignal) =>
  apiFetch<AiBudget[]>("/ai/budgets/institutes", { signal });
export const updateInstituteBudget = (
  instituteId: string,
  body: Partial<
    Pick<
      AiBudget,
      | "limit_tokens"
      | "limit_paise"
      | "on_exceed"
      | "enabled"
      | "feature_limits"
      | "disabled_features"
    >
  >,
) => apiFetch<AiBudget>(`/ai/budgets/institutes/${instituteId}`, { method: "PUT", body });

export const fetchRoleLimits = (instituteId?: string, signal?: AbortSignal) =>
  apiFetch<AiRoleLimit[]>(`/ai/role-limits${query({ institute_id: instituteId })}`, { signal });
export const updateRoleLimits = (body: { institute_id?: string; limits: Record<string, number> }) =>
  apiFetch<AiRoleLimit[]>("/ai/role-limits", { method: "PUT", body });

export const fetchUsage = (filters: UsageFilters, signal?: AbortSignal) =>
  apiFetch<Page<AiUsageRow>>(`/ai/usage${query(filters)}`, { signal });
export const fetchSummary = (instituteId?: string, signal?: AbortSignal) =>
  apiFetch<UsageSummary>(`/ai/usage/summary${query({ institute_id: instituteId })}`, { signal });
export const downloadUsage = (filters: UsageFilters) =>
  apiDownload(
    `/ai/usage/export${query({ ...filters, cursor: undefined, limit: undefined })}`,
    "ai-usage.xlsx",
  );

export const runPlayground = (body: { prompt: string; institute_id?: string }) =>
  apiFetch<PlaygroundResult>("/ai/playground", { method: "POST", body });
