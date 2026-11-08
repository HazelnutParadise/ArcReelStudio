import { useCallback, useEffect, useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useAppStore } from "@/stores/app-store";
import { ConnectionSelect } from "@/components/shared/ConnectionSelect";
import { SubscriptionLoginDialog } from "@/components/subscriptions/SubscriptionLoginDialog";
import type { AgentAuthMode, ClaudeSubscriptionStatus } from "@/types/agent-credential";
import type { CurrentAccount } from "@/types";
import { errMsg, voidCall } from "@/utils/async";

const MODES: readonly AgentAuthMode[] = ["prefer_subscription", "prefer_api_key", "subscription", "api_key"];

type Busy = "mode" | "connection" | null;

/** 订阅连线的供应商 id；连线下拉按它找这家的连线 */
const CLAUDE_SUBSCRIPTION = "claude-subscription";

/** 订阅状态与当前账号；组件卸载后到达的结果直接丢弃。 */
function useSubscriptionStatus() {
  const pushToast = useAppStore((s) => s.pushToast);
  const [status, setStatus] = useState<ClaudeSubscriptionStatus | null>(null);
  const [me, setMe] = useState<CurrentAccount | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      try {
        const [s, account] = await Promise.all([
          API.getClaudeSubscription({ signal: controller.signal }),
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
 * Agent 的 Claude 订阅：用哪一条 Claude 订阅连线、Agent 用订阅还是 API Key、谁优先。订阅连线在连线中心登录，这里也能
 * 直接登录新账号。认证方式与连线是整个工作区共用的，只有管理员能改，其他成员只看得到状态。
 */
export function ClaudeSubscriptionSection() {
  const { t } = useTranslation("dashboard");
  const pushToast = useAppStore((s) => s.pushToast);
  const titleId = useId();
  const { status, setStatus, isAdmin } = useSubscriptionStatus();
  const [busy, setBusy] = useState<Busy>(null);
  const [loginOpen, setLoginOpen] = useState(false);

  const run = useCallback(
    async (kind: Busy, action: () => Promise<ClaudeSubscriptionStatus>) => {
      setBusy(kind);
      try {
        setStatus(await action());
      } catch (err) {
        pushToast(errMsg(err), "error");
      } finally {
        setBusy(null);
      }
    },
    [pushToast, setStatus],
  );

  const refresh = useCallback(() => voidCall(run(null, () => API.getClaudeSubscription())), [run]);

  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h3 id={titleId} className="text-base font-medium">
          {t("claude_subscription_title")}
        </h3>
        <p className="text-sm text-muted-foreground">{t("claude_subscription_desc")}</p>
      </header>

      {status === null ? (
        <Loader2 aria-label={t("loading_placeholder")} className="size-4 animate-spin text-muted-foreground" />
      ) : (
        <>
          <SubscriptionConnectionRow
            status={status}
            isAdmin={isAdmin}
            busy={busy}
            onLogin={() => setLoginOpen(true)}
            onChoose={(credentialId) =>
              voidCall(run("connection", () => API.setAgentSubscriptionConnection(credentialId)))
            }
          />
          {status.subscription.blocked && <BlockedNotice until={status.subscription.until} />}
          <AuthModePicker
            mode={status.mode}
            loggedIn={status.credential_id !== null}
            disabled={!isAdmin || busy !== null}
            onChange={(mode) => voidCall(run("mode", () => API.setAgentAuthMode(mode)))}
          />
          {!isAdmin && <p className="text-xs text-muted-foreground">{t("claude_subscription_admin_only")}</p>}
        </>
      )}
      {isAdmin && (
        <SubscriptionLoginDialog
          providerId={CLAUDE_SUBSCRIPTION}
          providerName={t("claude_subscription_title")}
          open={loginOpen}
          onOpenChange={setLoginOpen}
          onSucceeded={refresh}
        />
      )}
    </section>
  );
}

function SubscriptionConnectionRow({
  status,
  isAdmin,
  busy,
  onLogin,
  onChoose,
}: Readonly<{
  status: ClaudeSubscriptionStatus;
  isAdmin: boolean;
  busy: Busy;
  onLogin: () => void;
  onChoose: (credentialId: number | null) => void;
}>) {
  const { t } = useTranslation("dashboard");
  const loggedIn = status.credential_id !== null;
  return (
    <div className="flex flex-col gap-3 rounded-lg border px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        {loggedIn ? (
          <>
            <Badge variant="secondary">{t("claude_subscription_status_logged_in")}</Badge>
            <span className="min-w-0 truncate text-sm">{status.credential_name}</span>
          </>
        ) : (
          <Badge variant="outline">{t("claude_subscription_status_logged_out")}</Badge>
        )}
        {isAdmin && (
          <Button
            className="ml-auto"
            variant={loggedIn ? "outline" : "default"}
            size="sm"
            disabled={busy !== null}
            onClick={onLogin}
          >
            {loggedIn ? t("claude_subscription_add_account") : t("claude_subscription_login")}
          </Button>
        )}
      </div>
      {isAdmin && loggedIn && (
        <ConnectionSelect
          backendValue={`${CLAUDE_SUBSCRIPTION}/agent`}
          value={status.chosen_credential_id}
          onChange={onChoose}
          label={t("claude_subscription_connection_label")}
        />
      )}
    </div>
  );
}

function BlockedNotice({ until }: Readonly<{ until: number | null }>) {
  const { t, i18n } = useTranslation("dashboard");
  const when =
    until === null
      ? t("claude_subscription_blocked_until_relogin")
      : t("claude_subscription_blocked_until", { time: new Date(until * 1000).toLocaleString(i18n.language) });
  return (
    <p role="status" className="text-sm text-muted-foreground">
      {t("claude_subscription_blocked")} {when}
    </p>
  );
}

function AuthModePicker({
  mode,
  loggedIn,
  disabled,
  onChange,
}: Readonly<{
  mode: AgentAuthMode;
  loggedIn: boolean;
  disabled: boolean;
  onChange: (mode: AgentAuthMode) => void;
}>) {
  const { t } = useTranslation("dashboard");
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="mb-2 text-sm font-medium">{t("claude_subscription_mode_title")}</legend>
      <RadioGroup
        aria-label={t("claude_subscription_mode_title")}
        value={mode}
        onValueChange={(next) => onChange(next as AgentAuthMode)}
      >
        {MODES.map((option) => (
          // eslint-disable-next-line jsx-a11y/label-has-associated-control -- 控件是嵌套的 RadioGroupItem（Base UI 单选），规则识别不到
          <label
            key={option}
            className="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-fast hover:bg-muted/50 has-data-checked:border-primary has-data-disabled:cursor-not-allowed has-data-disabled:opacity-60"
          >
            <RadioGroupItem
              value={option}
              className="mt-0.5"
              disabled={disabled || (option === "subscription" && !loggedIn)}
            />
            <span className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-medium">{t(`claude_auth_mode_${option}`)}</span>
              <span className="text-xs text-muted-foreground">{t(`claude_auth_mode_${option}_hint`)}</span>
            </span>
          </label>
        ))}
      </RadioGroup>
    </fieldset>
  );
}
