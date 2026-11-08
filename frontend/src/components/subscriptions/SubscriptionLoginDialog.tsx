import { ExternalLink, Loader2 } from "lucide-react";
import { useCallback, useEffect, useEffectEvent, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/stores/app-store";
import { useConnectionsStore } from "@/stores/connections-store";
import type { SubscriptionLogin } from "@/types";
import { errMsg, voidCall } from "@/utils/async";

/** device code 登录多久问一次结果 */
const POLL_MS = 2000;

/**
 * 进行中的登录：挂载时向后端要网址与代码，卸载（关掉对话框）时取消还没完成的登录，device code 登录轮询结果。
 * 对话框关闭时内容会卸载，所以每次打开都是一次新的登录。
 */
function useSubscriptionLogin(providerId: string, onSucceeded: (credentialId: number) => void) {
  const pushToast = useAppStore((s) => s.pushToast);
  const refreshConnections = useConnectionsStore((s) => s.refresh);
  const [login, setLogin] = useState<SubscriptionLogin | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const activeRef = useRef<SubscriptionLogin | null>(null);
  const reportSucceeded = useEffectEvent((credentialId: number) => onSucceeded(credentialId));

  const finish = useCallback((next: SubscriptionLogin) => {
    // 登录不论成败都已结束：不必再在卸载时取消
    if (next.status !== "pending") activeRef.current = null;
    setLogin(next);
  }, []);

  // 登录成功：更新各处的连线清单，再回报新连线
  const succeededId = login?.status === "succeeded" ? login.credential_id : null;
  useEffect(() => {
    if (succeededId === null) return;
    voidCall(refreshConnections());
    reportSucceeded(succeededId);
  }, [refreshConnections, succeededId]);

  // 挂载时开始登录；卸载时取消还没完成的登录，后台的 CLI 进程随之结束
  useEffect(() => {
    let cancelled = false;
    const start = async () => {
      try {
        const started = await API.startSubscriptionLogin(providerId);
        if (cancelled) {
          voidCall(API.cancelSubscriptionLogin(providerId, started.login_id));
          return;
        }
        activeRef.current = started;
        setLogin(started);
      } catch (err) {
        if (!cancelled) setStartError(errMsg(err));
      }
    };
    voidCall(start());
    return () => {
      cancelled = true;
      const active = activeRef.current;
      activeRef.current = null;
      if (active) voidCall(API.cancelSubscriptionLogin(providerId, active.login_id));
    };
  }, [providerId]);

  // device code：轮询到成功或失败为止
  useEffect(() => {
    if (login?.kind !== "device_code" || login.status !== "pending") return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      const poll = async () => {
        try {
          const next = await API.getSubscriptionLogin(providerId, login.login_id, { signal: controller.signal });
          if (controller.signal.aborted || next.status === "pending") return;
          finish(next);
        } catch (err) {
          if (!controller.signal.aborted) pushToast(errMsg(err), "error");
        }
      };
      voidCall(poll());
    }, POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [finish, login, providerId, pushToast]);

  const submitCode = useCallback(
    async (code: string) => {
      if (!login) return;
      // 贴码后登录不论成败都结束：失败要重新开始
      finish(await API.submitSubscriptionLoginCode(providerId, login.login_id, code));
    },
    [finish, login, providerId],
  );

  return { login, startError, submitCode };
}

/**
 * 登录订阅账号并存成连线。Claude 是开授权页、把验证码贴回来；ChatGPT 与 Grok 是开网址、输入页面上的一次性代码，
 * 完成后这里自动看到结果。登录成功就关掉对话框并回报新连线。
 */
export function SubscriptionLoginDialog({
  providerId,
  providerName,
  open,
  onOpenChange,
  onSucceeded,
}: Readonly<{
  providerId: string;
  providerName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSucceeded?: (credentialId: number) => void;
}>) {
  const { t } = useTranslation("dashboard");
  const pushToast = useAppStore((s) => s.pushToast);
  const handleSucceeded = useCallback(
    (credentialId: number) => {
      pushToast(t("subscription_login_succeeded", { name: providerName }), "success");
      onOpenChange(false);
      onSucceeded?.(credentialId);
    },
    [onOpenChange, onSucceeded, providerName, pushToast, t],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("subscription_login_title", { name: providerName })}</DialogTitle>
          <DialogDescription>{t("subscription_login_desc")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <LoginSession providerId={providerId} onSucceeded={handleSucceeded} />
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("cancel")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** 对话框内容：随对话框打开挂载、关闭卸载，登录的生命周期跟着它。 */
function LoginSession({
  providerId,
  onSucceeded,
}: Readonly<{ providerId: string; onSucceeded: (credentialId: number) => void }>) {
  const { login, startError, submitCode } = useSubscriptionLogin(providerId, onSucceeded);
  return <LoginBody login={login} startError={startError} onSubmitCode={submitCode} />;
}

function LoginBody({
  login,
  startError,
  onSubmitCode,
}: Readonly<{
  login: SubscriptionLogin | null;
  startError: string | null;
  onSubmitCode: (code: string) => Promise<void>;
}>) {
  const { t } = useTranslation("dashboard");
  if (startError !== null) {
    return (
      <p role="alert" className="text-sm text-destructive">
        {startError}
      </p>
    );
  }
  if (login === null) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 aria-hidden className="size-4 animate-spin" />
        {t("subscription_login_starting")}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {login.kind === "device_code" ? (
        <DeviceCodeSteps login={login} />
      ) : (
        <PasteCodeForm login={login} onSubmit={onSubmitCode} />
      )}
      {login.status === "failed" && (
        <p role="alert" className="text-sm text-destructive">
          {login.error ?? t("subscription_login_failed")}
        </p>
      )}
    </div>
  );
}

function OpenLink({ url, label }: Readonly<{ url: string; label: string }>) {
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex w-fit items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
    >
      {label}
      <ExternalLink aria-hidden className="size-3.5" />
    </a>
  );
}

function DeviceCodeSteps({ login }: Readonly<{ login: SubscriptionLogin }>) {
  const { t } = useTranslation("dashboard");
  return (
    <>
      {login.provider_id === "chatgpt-subscription" && (
        <p className="text-xs text-muted-foreground">{t("subscription_login_chatgpt_hint")}</p>
      )}
      <p className="text-sm">{t("subscription_login_device_step_open")}</p>
      <OpenLink url={login.url} label={t("subscription_login_open_link")} />
      <p className="text-sm">{t("subscription_login_device_step_code")}</p>
      <output
        aria-label={t("subscription_login_code_label")}
        className="w-fit rounded-md border bg-muted px-3 py-2 font-mono text-lg tracking-widest select-all"
      >
        {login.user_code}
      </output>
      {login.status === "pending" && (
        <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 aria-hidden className="size-4 animate-spin" />
          {t("subscription_login_waiting")}
        </p>
      )}
    </>
  );
}

function PasteCodeForm({
  login,
  onSubmit,
}: Readonly<{ login: SubscriptionLogin; onSubmit: (code: string) => Promise<void> }>) {
  const { t } = useTranslation("dashboard");
  const pushToast = useAppStore((s) => s.pushToast);
  const codeId = useId();
  const [code, setCode] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const trimmed = code.trim();
  const ended = login.status !== "pending";
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (!trimmed) return;
        setSubmitting(true);
        const send = async () => {
          try {
            await onSubmit(trimmed);
          } catch (err) {
            pushToast(errMsg(err), "error");
          } finally {
            setSubmitting(false);
          }
        };
        voidCall(send());
      }}
    >
      <p className="text-sm">{t("subscription_login_paste_step_open")}</p>
      <OpenLink url={login.url} label={t("subscription_login_open_link")} />
      <label htmlFor={codeId} className="text-sm">
        {t("subscription_login_paste_step_code")}
      </label>
      <Input
        id={codeId}
        value={code}
        autoComplete="off"
        spellCheck={false}
        disabled={ended}
        onChange={(event) => setCode(event.target.value)}
        placeholder={t("subscription_login_code_placeholder")}
      />
      <Button type="submit" size="sm" className="w-fit" disabled={ended || submitting || !trimmed}>
        {submitting && <Loader2 aria-hidden className="size-3.5 animate-spin" />}
        {t("subscription_login_submit")}
      </Button>
    </form>
  );
}
