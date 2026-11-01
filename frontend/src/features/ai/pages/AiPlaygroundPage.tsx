import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Alert } from "@/components/Alert";
import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { Card, CardBody, CardHeader } from "@/components/Card";
import { SelectField } from "@/components/Field";
import { aiKeys, fetchInstituteBudgets, runPlayground } from "@/features/ai/api";
import { AiLayout } from "@/features/ai/components/AiLayout";
import { useT } from "@/features/i18n/useT";
import { ApiError } from "@/lib/api";
import { formatRupees } from "@/lib/format";

/** Run a test prompt through the full gateway. Used for acceptance tests 1–3. */
export function AiPlaygroundPage() {
  const { t } = useT();
  const [prompt, setPrompt] = useState("");
  const [instituteId, setInstituteId] = useState("");
  const institutes = useQuery({
    queryKey: aiKeys.instituteBudgets,
    queryFn: ({ signal }) => fetchInstituteBudgets(signal),
  });
  const run = useMutation({
    mutationFn: () => runPlayground({ prompt, institute_id: instituteId || undefined }),
  });
  const result = run.data;

  return (
    <AiLayout title={t("ai.playground.title")} description={t("ai.playground.description")}>
      <Card>
        <CardBody className="space-y-3">
          <SelectField
            label={t("ai.playground.institute")}
            value={instituteId}
            onChange={(e) => setInstituteId(e.target.value)}
            options={[
              { value: "", label: t("ai.playground.platform") },
              ...(institutes.data ?? []).map((b) => ({
                value: b.institute_id ?? "",
                label: b.institute_name ?? "",
              })),
            ]}
          />
          <label className="block space-y-1.5">
            <span className="text-sm font-medium text-fg">{t("ai.playground.prompt")}</span>
            <textarea
              rows={5}
              maxLength={20000}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface p-3 text-sm text-fg"
            />
          </label>
          <Button disabled={!prompt.trim()} loading={run.isPending} onClick={() => run.mutate()}>
            {t("ai.playground.run")}
          </Button>
          {run.error instanceof ApiError && (
            <Alert
              tone={run.error.status === 429 || run.error.status === 403 ? "warning" : "danger"}
            >
              {run.error.message}
            </Alert>
          )}
        </CardBody>
      </Card>
      {result && (
        <Card>
          <CardHeader
            title={t("ai.playground.answer")}
            actions={
              <div className="flex flex-wrap gap-1.5">
                <Badge tone="accent">{result.model_id}</Badge>
                {result.fallback_used && <Badge tone="warning">Backup model</Badge>}
                {result.status === "cached" && <Badge>Cached</Badge>}
                {result.safety_blocked && <Badge tone="danger">Safety filter</Badge>}
                {result.redactions > 0 && (
                  <Badge tone="warning">{result.redactions} redacted</Badge>
                )}
              </div>
            }
          />
          <CardBody className="space-y-3">
            {/* Rendered as text, never HTML: model output is untrusted (OWASP LLM05). */}
            <p className="text-sm whitespace-pre-wrap text-fg">{result.text}</p>
            <p className="num text-xs text-fg-2">
              {result.input_tokens} in · {result.output_tokens} out ·{" "}
              {formatRupees(result.cost_paise)}
            </p>
          </CardBody>
        </Card>
      )}
    </AiLayout>
  );
}
