import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField, TextField } from "@/components/Field";
import { Icon } from "@/components/Icon";
import { Modal } from "@/components/Modal";
import type { Column } from "@/components/Table";
import { Table } from "@/components/Table";
import type { AiModel } from "@/features/ai/api";
import { aiKeys, createModel, fetchModels, fetchProviders, updateModel } from "@/features/ai/api";
import { AiLayout } from "@/features/ai/components/AiLayout";
import { Switch } from "@/features/ai/components/widgets";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";

/** Providers (key configured or not — never the key) and the model registry with prices. */
export function AiModelsPage() {
  const { t } = useT();
  const queryClient = useQueryClient();
  const providers = useQuery({
    queryKey: aiKeys.providers,
    queryFn: ({ signal }) => fetchProviders(signal),
  });
  const models = useQuery({
    queryKey: aiKeys.models,
    queryFn: ({ signal }) => fetchModels(signal),
  });
  const [editing, setEditing] = useState<AiModel | "new" | null>(null);
  const toggle = useMutation({
    mutationFn: (m: AiModel) => updateModel(m.id, { enabled: !m.enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: aiKeys.models }),
  });
  const fakeMode = providers.data?.some((p) => p.fake_mode);

  const columns: Column<AiModel>[] = [
    {
      key: "name",
      header: "Model",
      primary: true,
      cell: (m) => (
        <div>
          <p className="font-medium text-fg">{m.display_name}</p>
          <p className="mono text-xs text-fg-3">{m.model_id}</p>
        </div>
      ),
    },
    { key: "provider", header: "Provider", cell: (m) => m.provider },
    {
      key: "in",
      header: "Input $/1M",
      cell: (m) => <span className="num">{m.input_price_per_mtok_usd}</span>,
    },
    {
      key: "out",
      header: "Output $/1M",
      cell: (m) => <span className="num">{m.output_price_per_mtok_usd}</span>,
    },
    {
      key: "enabled",
      header: "On",
      cell: (m) => (
        <Switch
          checked={m.enabled}
          label={m.display_name}
          disabled={toggle.isPending}
          onChange={() => toggle.mutate(m)}
        />
      ),
    },
    {
      key: "edit",
      header: "",
      cell: (m) => (
        <Button size="sm" variant="secondary" onClick={() => setEditing(m)}>
          {t("common.edit")}
        </Button>
      ),
    },
  ];

  return (
    <AiLayout
      title={t("ai.nav.models")}
      actions={
        <Button icon={<Icon name="plus" />} onClick={() => setEditing("new")}>
          Add model
        </Button>
      }
    >
      {fakeMode && (
        <Alert tone="warning" title="Fake provider is answering">
          AI_FAKE_PROVIDER is on, so no request reaches a real provider and costs are simulated.
        </Alert>
      )}
      <Card>
        <CardHeader
          title="Providers"
          description="API keys live in Secret Manager. Only whether one is set is shown."
        />
        <CardBody className="flex flex-wrap gap-2">
          {(providers.data ?? []).map((p) => (
            <Badge key={p.name} tone={p.configured ? "success" : "neutral"}>
              {p.name}: {p.configured ? "key configured" : "not configured"}
            </Badge>
          ))}
        </CardBody>
      </Card>
      <Card>
        <CardHeader
          title="Models and prices"
          description="Prices are USD per million tokens from the provider's pricing page. Costs are worked out with the platform's USD→INR rate."
        />
        <Table
          columns={columns}
          rows={models.data ?? []}
          rowKey={(m) => m.id}
          loading={models.isLoading}
        />
      </Card>
      {editing && (
        <ModelForm model={editing === "new" ? null : editing} onClose={() => setEditing(null)} />
      )}
    </AiLayout>
  );
}

function ModelForm({ model, onClose }: { model: AiModel | null; onClose: () => void }) {
  const { t } = useT();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    provider: model?.provider ?? "gemini",
    model_id: model?.model_id ?? "",
    display_name: model?.display_name ?? "",
    input: String(model?.input_price_per_mtok_usd ?? ""),
    output: String(model?.output_price_per_mtok_usd ?? ""),
  });
  const save = useMutation({
    mutationFn: () => {
      const prices = {
        display_name: form.display_name,
        input_price_per_mtok_usd: Number(form.input),
        output_price_per_mtok_usd: Number(form.output),
      };
      return model
        ? updateModel(model.id, prices)
        : createModel({
            ...prices,
            provider: form.provider as AiModel["provider"],
            model_id: form.model_id,
            enabled: true,
          });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: aiKeys.models });
      onClose();
    },
  });
  return (
    <Modal
      open
      onClose={onClose}
      title={model ? model.display_name : "Add model"}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button loading={save.isPending} onClick={() => save.mutate()}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="grid gap-3 sm:grid-cols-2">
        {!model && (
          <>
            <SelectField
              label="Provider"
              value={form.provider}
              onChange={(e) =>
                setForm({ ...form, provider: e.target.value as AiModel["provider"] })
              }
              options={[
                { value: "gemini", label: "Google Gemini" },
                { value: "anthropic", label: "Anthropic" },
              ]}
            />
            <TextField
              label="Model ID"
              value={form.model_id}
              onChange={(e) => setForm({ ...form, model_id: e.target.value })}
            />
          </>
        )}
        <TextField
          label="Display name"
          value={form.display_name}
          onChange={(e) => setForm({ ...form, display_name: e.target.value })}
        />
        <TextField
          label="Input price ($ / 1M tokens)"
          inputMode="decimal"
          value={form.input}
          onChange={(e) => setForm({ ...form, input: e.target.value })}
        />
        <TextField
          label="Output price ($ / 1M tokens)"
          inputMode="decimal"
          value={form.output}
          onChange={(e) => setForm({ ...form, output: e.target.value })}
        />
      </div>
      {save.error instanceof ApiError && (
        <Alert tone="danger" className="mt-3">
          {save.error.message}
        </Alert>
      )}
    </Modal>
  );
}
