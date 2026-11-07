import { useCallback, useEffect, useId, useRef, useState } from "react";
import { ExternalLink, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { useAppStore } from "@/stores/app-store";
import type { AgentAuthMode, ClaudeLoginStart, ClaudeSubscriptionStatus } from "@/types/agent-credential";
import type { CurrentAccount } from "@/types";
import { errMsg, voidCall } from "@/utils/async";

const MODES: readonly AgentAuthMode[] = ["prefer_subscription", "prefer_api_key", "subscription", "api_key"];

type Busy = "start" | "code" | "logout" | "mode" | null;

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
 * Claude 订阅：在网页上登录（开授权页、贴回验证码），并选择 Agent 用订阅还是 API Key、谁优先。
 * 订阅是整个工作区共用的，登录、登出与切换方式只有管理员能做，其他成员只看得到状态。
 */
export function ClaudeSubscriptionSection() {
  const { t } = useTranslation("dashboard");
  const pushToast = useAppStore((s) => s.pushToast);
  const titleId = useId();
  const { status, setStatus, isAdmin } = useSubscriptionStatus();

  const [login, setLogin] = useState<ClaudeLoginStart | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const loginRef = useRef<ClaudeLoginStart | null>(null);

  // 离开页面时放弃进行到一半的登录，后台的 CLI 进程随之结束
  useEffect(
    () => () => {
      if (loginRef.current) voidCall(API.cancelClaudeLogin());
    },
    [],
  );

  const endLogin = useCallback(() => {
    loginRef.current = null;
    setLogin(null);
  }, []);

  const startLogin = useCallback(async () => {
    setBusy("start");
    setLoginError(null);
    try {
      const started = await API.startClaudeLogin();
      loginRef.current = started;
      setLogin(started);
    } catch (err) {
      pushToast(errMsg(err), "error");
    } finally {
      setBusy(null);
    }
  }, [pushToast]);

  const submitCode = useCallback(
    async (code: string) => {
      if (!login) return;
      setBusy("code");
      setLoginError(null);
      try {
        setStatus(await API.finishClaudeLogin(login.login_id, code));
        pushToast(t("claude_subscription_logged_in_toast"), "success");
      } catch (err) {
        setLoginError(errMsg(err));
      } finally {
        // 登录不论成败都已结束：要再试得重新开始
        endLogin();
        setBusy(null);
      }
    },
    [endLogin, login, pushToast, setStatus, t],
  );

  const cancelLogin = useCallback(async () => {
    endLogin();
    try {
      await API.cancelClaudeLogin();
    } catch (err) {
      pushToast(errMsg(err), "error");
    }
  }, [endLogin, pushToast]);

  const runStatusAction = useCallback(
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
          <SubscriptionStatusRow
            status={status}
            isAdmin={isAdmin}
            busy={busy}
            loginOpen={login !== null}
            onLogin={() => voidCall(startLogin())}
            onLogout={() => voidCall(runStatusAction("logout", () => API.logoutClaudeSubscription()))}
          />
          {status.subscription.blocked && <BlockedNotice until={status.subscription.until} />}
          {login !== null && (
            <LoginCodeForm
              authorizeUrl={login.authorize_url}
              submitting={busy === "code"}
              disabled={busy !== null}
              onSubmit={(code) => voidCall(submitCode(code))}
              onCancel={() => voidCall(cancelLogin())}
            />
          )}
          {loginError !== null && (
            <p role="alert" className="text-sm text-destructive">
              {loginError}
            </p>
          )}
          <AuthModePicker
            mode={status.mode}
            loggedIn={status.logged_in}
            disabled={!isAdmin || busy !== null}
            onChange={(mode) => voidCall(runStatusAction("mode", () => API.setAgentAuthMode(mode)))}
          />
          {!isAdmin && <p className="text-xs text-muted-foreground">{t("claude_subscription_admin_only")}</p>}
        </>
      )}
    </section>
  );
}

function SubscriptionStatusRow({
  status,
  isAdmin,
  busy,
  loginOpen,
  onLogin,
  onLogout,
}: Readonly<{
  status: ClaudeSubscriptionStatus;
  isAdmin: boolean;
  busy: Busy;
  loginOpen: boolean;
  onLogin: () => void;
  onLogout: () => void;
}>) {
  const { t } = useTranslation("dashboard");
  if (!status.logged_in) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3">
        <Badge variant="outline">{t("claude_subscription_status_logged_out")}</Badge>
        {isAdmin && !loginOpen && (
          <Button className="ml-auto" size="sm" disabled={busy !== null} onClick={onLogin}>
            {busy === "start" && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
            {t("claude_subscription_login")}
          </Button>
        )}
      </div>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3">
      <Badge variant="secondary">{t("claude_subscription_status_logged_in")}</Badge>
      <span className="font-mono text-sm text-muted-foreground">{status.token_masked}</span>
      {isAdmin && (
        <span className="ml-auto flex gap-2">
          <Button variant="outline" size="sm" disabled={busy !== null || loginOpen} onClick={onLogin}>
            {t("claude_subscription_relogin")}
          </Button>
          <Button variant="ghost" size="sm" disabled={busy !== null} onClick={onLogout}>
            {busy === "logout" && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
            {t("claude_subscription_logout")}
          </Button>
        </span>
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

function LoginCodeForm({
  authorizeUrl,
  submitting,
  disabled,
  onSubmit,
  onCancel,
}: Readonly<{
  authorizeUrl: string;
  submitting: boolean;
  disabled: boolean;
  onSubmit: (code: string) => void;
  onCancel: () => void;
}>) {
  const { t } = useTranslation("dashboard");
  const codeId = useId();
  const [code, setCode] = useState("");
  const trimmed = code.trim();
  return (
    <form
      className="flex flex-col gap-3 rounded-lg border px-4 py-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (trimmed) onSubmit(trimmed);
      }}
    >
      <p className="text-sm">{t("claude_subscription_login_step_open")}</p>
      <a
        href={authorizeUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex w-fit items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
      >
        {t("claude_subscription_login_open_link")}
        <ExternalLink aria-hidden className="size-3.5" />
      </a>
      <label htmlFor={codeId} className="text-sm">
        {t("claude_subscription_login_step_code")}
      </label>
      <Input
        id={codeId}
        value={code}
        autoComplete="off"
        spellCheck={false}
        onChange={(event) => setCode(event.target.value)}
        placeholder={t("claude_subscription_code_placeholder")}
      />
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={disabled || !trimmed}>
          {submitting && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
          {t("claude_subscription_login_submit")}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          {t("cancel")}
        </Button>
      </div>
    </form>
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
