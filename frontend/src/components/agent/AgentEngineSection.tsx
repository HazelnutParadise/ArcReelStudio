import { useCallback, useEffect, useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAppStore } from "@/stores/app-store";
import { connectionsOf, useConnectionsStore } from "@/stores/connections-store";
import type { AgentEngine, AgentEngineRequest, AgentEngineStatus } from "@/types/agent-credential";
import type { CurrentAccount } from "@/types";
import { errMsg, voidCall } from "@/utils/async";

const ENGINES: readonly AgentEngine[] = ["claude", "codex", "grok"];

/** 每个非 Claude 引擎能用的连线：订阅在前、API Key 在后（与后端的预设顺序一致），以及设定栏位与连线名称的文案键 */
const ENGINE_CONNECTIONS = {
  codex: {
    subscription: "chatgpt-subscription",
    apiKey: "openai",
    credentialField: "codex_credential_id",
    effectiveField: "codex_effective_credential_id",
    modelField: "codex_model",
    modelsField: "codex_models",
  },
  grok: {
    subscription: "grok-subscription",
    apiKey: "grok",
    credentialField: "grok_credential_id",
    effectiveField: "grok_effective_credential_id",
    modelField: "grok_model",
    modelsField: "grok_models",
  },
} as const;

type ConnectedEngine = keyof typeof ENGINE_CONNECTIONS;

/** 引擎设定与当前账号；组件卸载后到达的结果直接丢弃。 */
function useEngineStatus() {
  const pushToast = useAppStore((s) => s.pushToast);
  const [status, setStatus] = useState<AgentEngineStatus | null>(null);
  const [me, setMe] = useState<CurrentAccount | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const [s, account] = await Promise.all([
          API.getAgentEngine({ signal: controller.signal }),
          API.getMe({ signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        setStatus(s);
        setMe(account);
      } catch (err) {
        if (!controller.signal.aborted) pushToast(errMsg(err), "error");
      }
    };
    voidCall(load());
    return () => controller.abort();
  }, [pushToast]);

  return { status, setStatus, isAdmin: me?.role === "admin" };
}

/**
 * Agent 用哪个引擎跑新会话：Claude，或 Codex（用 ChatGPT 订阅或 OpenAI API Key）。已经开始的会话照它当初的引擎继续。
 * 整个工作区共用，只有管理员能改。
 */
export function AgentEngineSection() {
  const { t } = useTranslation("dashboard");
  const pushToast = useAppStore((s) => s.pushToast);
  const titleId = useId();
  const { status, setStatus, isAdmin } = useEngineStatus();
  const [busy, setBusy] = useState(false);

  const save = useCallback(
    async (patch: Partial<AgentEngineRequest>) => {
      if (status === null) return;
      setBusy(true);
      try {
        setStatus(
          await API.setAgentEngine({
            engine: status.engine,
            codex_credential_id: status.codex_credential_id,
            codex_model: status.codex_model,
            grok_credential_id: status.grok_credential_id,
            grok_model: status.grok_model,
            ...patch,
          }),
        );
      } catch (err) {
        pushToast(errMsg(err), "error");
      } finally {
        setBusy(false);
      }
    },
    [pushToast, setStatus, status],
  );

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h3 id={titleId} className="text-base font-medium">
          {t("agent_engine_title")}
        </h3>
        <p className="text-sm text-muted-foreground">{t("agent_engine_desc")}</p>
      </header>
      {status === null ? (
        <Loader2 aria-label={t("loading_placeholder")} className="size-4 animate-spin text-muted-foreground" />
      ) : (
        <>
          <EnginePicker
            engine={status.engine}
            disabled={!isAdmin || busy}
            onChange={(engine) => voidCall(save({ engine }))}
          />
          {status.engine !== "claude" && (
            <EngineConnectionOptions
              engine={status.engine}
              status={status}
              disabled={!isAdmin || busy}
              onChange={(patch) => voidCall(save(patch))}
            />
          )}
          {!isAdmin && <p className="text-xs text-muted-foreground">{t("agent_engine_admin_only")}</p>}
        </>
      )}
    </section>
  );
}

function EnginePicker({
  engine,
  disabled,
  onChange,
}: Readonly<{ engine: AgentEngine; disabled: boolean; onChange: (engine: AgentEngine) => void }>) {
  const { t } = useTranslation("dashboard");
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="sr-only">{t("agent_engine_title")}</legend>
      <RadioGroup
        aria-label={t("agent_engine_title")}
        value={engine}
        onValueChange={(next) => onChange(next as AgentEngine)}
      >
        {ENGINES.map((option) => (
          // eslint-disable-next-line jsx-a11y/label-has-associated-control -- 控件是嵌套的 RadioGroupItem（Base UI 单选），规则识别不到
          <label
            key={option}
            className="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-fast hover:bg-muted/50 has-data-checked:border-primary has-data-disabled:cursor-not-allowed has-data-disabled:opacity-60"
          >
            <RadioGroupItem value={option} className="mt-0.5" disabled={disabled} />
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-medium">{t(`agent_engine_${option}`)}</span>
              <span className="text-xs text-muted-foreground">{t(`agent_engine_${option}_hint`)}</span>
            </span>
          </label>
        ))}
      </RadioGroup>
    </fieldset>
  );
}

function EngineConnectionOptions({
  engine,
  status,
  disabled,
  onChange,
}: Readonly<{
  engine: ConnectedEngine;
  status: AgentEngineStatus;
  disabled: boolean;
  onChange: (patch: Partial<AgentEngineRequest>) => void;
}>) {
  const { t } = useTranslation("dashboard");
  const connections = useConnectionsStore((s) => s.connections);
  const fetchConnections = useConnectionsStore((s) => s.fetch);
  useEffect(() => {
    void fetchConnections();
  }, [fetchConnections]);

  const spec = ENGINE_CONNECTIONS[engine];
  const own = [spec.subscription, spec.apiKey].flatMap((provider) => connectionsOf(connections, provider));
  const effective = own.find((connection) => connection.id === status[spec.effectiveField]);
  const connectionItems = [
    {
      value: null,
      label: effective ? t("connection_default_named", { name: effective.name }) : t("connection_default"),
    },
    ...own.map((connection) => ({
      value: connection.id,
      label: t(
        `agent_engine_${engine}_connection_${connection.provider === spec.apiKey ? "api_key" : "subscription"}`,
        { name: connection.name },
      ),
    })),
  ];
  const modelItems = status[spec.modelsField].map((model) => ({ value: model, label: model }));

  return (
    <div className="flex flex-col gap-3 rounded-lg border px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="w-16 shrink-0 text-xs text-muted-foreground">{t("connection_label")}</span>
        <Select
          items={connectionItems}
          value={status[spec.credentialField]}
          disabled={disabled}
          onValueChange={(next) => onChange({ [spec.credentialField]: next ?? null })}
        >
          <SelectTrigger size="sm" aria-label={t(`agent_engine_${engine}_connection_label`)} className="min-w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false} align="start">
            {connectionItems.map((item) => (
              <SelectItem key={item.value ?? "default"} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="w-16 shrink-0 text-xs text-muted-foreground">{t("agent_engine_codex_model")}</span>
        <Select
          items={modelItems}
          value={status[spec.modelField]}
          disabled={disabled}
          onValueChange={(next) => {
            if (next) onChange({ [spec.modelField]: next });
          }}
        >
          <SelectTrigger size="sm" aria-label={t("agent_engine_codex_model")} className="min-w-56">
            <SelectValue />
          </SelectTrigger>
          <SelectContent alignItemWithTrigger={false} align="start">
            {modelItems.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <p className="text-xs text-muted-foreground">{t(`agent_engine_${engine}_limits`)}</p>
    </div>
  );
}
