import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import type { AiFeature } from "@/features/ai/api";
import { aiKeys, fetchFeatures, fetchModels, updateFeature } from "@/features/ai/api";
import { AiLayout } from "@/features/ai/components/AiLayout";
import { Switch } from "@/features/ai/components/widgets";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/**
 * One card per AI feature: model, backup model, answer length, prompt, safety level,
 * caching and on/off. Prompts are data, so they can be tuned without a release.
 */
export function AiFeaturesPage() {
  const { t } = useT();
  const features = useQuery({
    queryKey: aiKeys.features,
    queryFn: ({ signal }) => fetchFeatures(signal),
  });
  const models = useQuery({
    queryKey: aiKeys.models,
    queryFn: ({ signal }) => fetchModels(signal),
  });
  const options = (models.data ?? []).map((m) => ({
    value: m.model_id,
    label: `${m.display_name} (${m.model_id})`,
  }));
  return (
    <AiLayout title={t("ai.nav.features")}>
      {(features.data ?? []).map((feature) => (
        <FeatureCard key={feature.key} feature={feature} modelOptions={options} />
      ))}
    </AiLayout>
  );
}

function FeatureCard({
  feature,
  modelOptions,
}: {
  feature: AiFeature;
  modelOptions: { value: string; label: string }[];
}) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [form, setForm] = useState(feature);
  const save = useMutation({
    mutationFn: (body: Partial<AiFeature>) => updateFeature(feature.key, body),
    onSuccess: (data) => {
      setForm(data);
      void queryClient.invalidateQueries({ queryKey: aiKeys.features });
    },
  });
  return (
    <Card>
      <CardHeader
        title={feature.name}
        description={<span className="mono text-xs">{feature.key}</span>}
        actions={
          <>
            {feature.safety_level === "kids" && <Badge tone="warning">Kids safety</Badge>}
            <Switch
              checked={feature.enabled}
              label={feature.name}
              disabled={save.isPending}
              onChange={(enabled) => save.mutate({ enabled })}
            />
          </>
        }
      />
      <CardBody className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <SelectField
            label="Model"
            value={form.model_id}
            options={modelOptions}
            onChange={(e) => setForm({ ...form, model_id: e.target.value })}
          />
          <SelectField
            label="Backup model"
            value={form.fallback_model_id ?? ""}
            options={[{ value: "", label: t("common.none") }, ...modelOptions]}
            onChange={(e) => setForm({ ...form, fallback_model_id: e.target.value || null })}
          />
          <TextField
            label="Max answer tokens"
            type="number"
            min={16}
            value={String(form.max_output_tokens)}
            onChange={(e) => setForm({ ...form, max_output_tokens: Number(e.target.value) })}
          />
          <TextField
            label="Cache answers (hours)"
            type="number"
            min={0}
            hint="0 turns caching off."
            value={String(form.cache_ttl_hours)}
            onChange={(e) => setForm({ ...form, cache_ttl_hours: Number(e.target.value) })}
          />
          <SelectField
            label="Safety level"
            value={form.safety_level}
            options={[
              { value: "standard", label: "Standard" },
              { value: "kids", label: "Kids (strictest)" },
            ]}
            onChange={(e) =>
              setForm({ ...form, safety_level: e.target.value as AiFeature["safety_level"] })
            }
          />
        </div>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-fg">System prompt</span>
          <textarea
            rows={4}
            value={form.system_prompt}
            onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
            className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-fg"
          />
        </label>
        {save.error instanceof ApiError && <Alert tone="danger">{save.error.message}</Alert>}
        <Button
          loading={save.isPending}
          onClick={() =>
            save.mutate({
              model_id: form.model_id,
              fallback_model_id: form.fallback_model_id ?? "",
              max_output_tokens: form.max_output_tokens,
              cache_ttl_hours: form.cache_ttl_hours,
              safety_level: form.safety_level,
              system_prompt: form.system_prompt,
            })
          }
        >
          {t("common.save")}
        </Button>
      </CardBody>
    </Card>
  );
}
