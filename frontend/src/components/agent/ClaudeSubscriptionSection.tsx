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

/**
 * Claude 订阅：在网页上登录（开授权页、贴回验证码），并选择 Agent 用订阅还是 API Key、谁优先。
 * 订阅是整个工作区共用的，登录、登出与切换方式只有管理员能做，其他成员只看得到状态。
 */
export function ClaudeSubscriptionSection() {
  const { t, i18n } = useTranslation("dashboard");
  const pushToast = useAppStore((s) => s.pushToast);
  const titleId = useId();
  const codeId = useId();

  const [status, setStatus] = useState<ClaudeSubscriptionStatus | null>(null);
  const [me, setMe] = useState<CurrentAccount | null>(null);
  const [login, setLogin] = useState<ClaudeLoginStart | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"start" | "code" | "logout" | "mode" | null>(null);
  const [loginError, setLoginError] = useState<string | null>(null);
  const loginRef = useRef<ClaudeLoginStart | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([API.getClaudeSubscription({ signal: controller.signal }), API.getMe({ signal: controller.signal })])
      .then(([s, account]) => {
        setStatus(s);
        setMe(account);
      })
      .catch((err: unknown) => {
        if (!controller.signal.aborted) pushToast(errMsg(err), "error");
      });
    return () => controller.abort();
  }, [pushToast]);

  // 离开页面时放弃进行到一半的登录，后台的 CLI 进程随之结束
  useEffect(
    () => () => {
      if (loginRef.current) voidCall(API.cancelClaudeLogin());
    },
    [],
  );

  const isAdmin = me?.role === "admin";

  const startLogin = useCallback(async () => {
    setBusy("start");
    setLoginError(null);
    try {
      const started = await API.startClaudeLogin();
      loginRef.current = started;
      setLogin(started);
      setCode("");
    } catch (err) {
      pushToast(errMsg(err), "error");
    } finally {
      setBusy(null);
    }
  }, [pushToast]);

  const submitCode = useCallback(async () => {
    if (!login || !code.trim()) return;
    setBusy("code");
    setLoginError(null);
    try {
      const next = await API.finishClaudeLogin(login.login_id, code.trim());
      loginRef.current = null;
      setLogin(null);
      setCode("");
      setStatus(next);
      pushToast(t("claude_subscription_logged_in_toast"), "success");
    } catch (err) {
      // 登录不论成败都已结束：要再试得重新开始
      loginRef.current = null;
      setLogin(null);
      setLoginError(errMsg(err));
    } finally {
      setBusy(null);
    }
  }, [code, login, pushToast, t]);

  const cancelLogin = useCallback(async () => {
    loginRef.current = null;
    setLogin(null);
    setCode("");
    try {
      await API.cancelClaudeLogin();
    } catch (err) {
      pushToast(errMsg(err), "error");
    }
  }, [pushToast]);

  const logout = useCallback(async () => {
    setBusy("logout");
    try {
      setStatus(await API.logoutClaudeSubscription());
    } catch (err) {
      pushToast(errMsg(err), "error");
    } finally {
      setBusy(null);
    }
  }, [pushToast]);

  const changeMode = useCallback(
    async (mode: AgentAuthMode) => {
      setBusy("mode");
      try {
        setStatus(await API.setAgentAuthMode(mode));
      } catch (err) {
        pushToast(errMsg(err), "error");
      } finally {
        setBusy(null);
      }
    },
    [pushToast],
  );

  const formatUntil = (until: number | null) =>
    until === null
      ? t("claude_subscription_blocked_until_relogin")
      : t("claude_subscription_blocked_until", {
          time: new Date(until * 1000).toLocaleString(i18n.language),
        });

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
          <div className="flex flex-wrap items-center gap-3 rounded-lg border px-4 py-3">
            {status.logged_in ? (
              <>
                <Badge variant="secondary">{t("claude_subscription_status_logged_in")}</Badge>
                <span className="font-mono text-sm text-muted-foreground">{status.token_masked}</span>
                {isAdmin && (
                  <span className="ml-auto flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy !== null || login !== null}
                      onClick={() => voidCall(startLogin())}
                    >
                      {t("claude_subscription_relogin")}
                    </Button>
                    <Button variant="ghost" size="sm" disabled={busy !== null} onClick={() => voidCall(logout())}>
                      {busy === "logout" && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
                      {t("claude_subscription_logout")}
                    </Button>
                  </span>
                )}
              </>
            ) : (
              <>
                <Badge variant="outline">{t("claude_subscription_status_logged_out")}</Badge>
                {isAdmin && login === null && (
                  <Button className="ml-auto" size="sm" disabled={busy !== null} onClick={() => voidCall(startLogin())}>
                    {busy === "start" && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
                    {t("claude_subscription_login")}
                  </Button>
                )}
              </>
            )}
          </div>

          {status.subscription.blocked && (
            <p role="status" className="text-sm text-muted-foreground">
              {t("claude_subscription_blocked")} {formatUntil(status.subscription.until)}
            </p>
          )}

          {login !== null && (
            <form
              className="flex flex-col gap-3 rounded-lg border px-4 py-3"
              onSubmit={(event) => {
                event.preventDefault();
                voidCall(submitCode());
              }}
            >
              <p className="text-sm">{t("claude_subscription_login_step_open")}</p>
              <a
                href={login.authorize_url}
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
                <Button type="submit" size="sm" disabled={busy !== null || !code.trim()}>
                  {busy === "code" && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
                  {t("claude_subscription_login_submit")}
                </Button>
                <Button type="button" variant="ghost" size="sm" onClick={() => voidCall(cancelLogin())}>
                  {t("cancel")}
                </Button>
              </div>
            </form>
          )}

          {loginError !== null && (
            <p role="alert" className="text-sm text-destructive">
              {loginError}
            </p>
          )}

          <fieldset className="flex flex-col gap-2" disabled={!isAdmin || busy !== null}>
            <legend className="mb-2 text-sm font-medium">{t("claude_subscription_mode_title")}</legend>
            <RadioGroup
              aria-label={t("claude_subscription_mode_title")}
              value={status.mode}
              onValueChange={(next) => voidCall(changeMode(next as AgentAuthMode))}
            >
              {MODES.map((mode) => (
                // eslint-disable-next-line jsx-a11y/label-has-associated-control -- 控件是嵌套的 RadioGroupItem（Base UI 单选），规则识别不到
                <label
                  key={mode}
                  className="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors duration-fast hover:bg-muted/50 has-data-checked:border-primary has-data-disabled:cursor-not-allowed has-data-disabled:opacity-60"
                >
                  <RadioGroupItem
                    value={mode}
                    className="mt-0.5"
                    disabled={!isAdmin || (mode === "subscription" && !status.logged_in)}
                  />
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="text-sm font-medium">{t(`claude_auth_mode_${mode}`)}</span>
                    <span className="text-xs text-muted-foreground">{t(`claude_auth_mode_${mode}_hint`)}</span>
                  </span>
                </label>
              ))}
            </RadioGroup>
          </fieldset>
          {!isAdmin && <p className="text-xs text-muted-foreground">{t("claude_subscription_admin_only")}</p>}
        </>
      )}
    </section>
  );
}
