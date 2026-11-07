import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { KeyRound, Loader2, LogOut, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { TruncatedText } from "@/components/shared/TruncatedText";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import type { AccountRole, CurrentAccount, MemberInfo } from "@/types";
import { errMsg } from "@/utils/async";
import { formatDate } from "@/utils/date-format";

/** 与后端 `server/services/accounts.py` 的 `MIN_PASSWORD_LENGTH` 一致。 */
const MIN_PASSWORD_LENGTH = 8;
const ROLES: AccountRole[] = ["admin", "user"];
const DATE_OPTS: Intl.DateTimeFormatOptions = { year: "numeric", month: "2-digit", day: "2-digit" };

type LoadState<T> = { status: "loading" } | { status: "error"; message: string } | { status: "ready"; value: T };

/**
 * 全局设置「账号与成员」：每个人都能看到自己的账号、修改密码与登出；管理员另外管理成员。
 * 所有成员共用同一个工作区，这里不划分项目权限。
 */
export function AccountSection() {
  const { t } = useTranslation(["dashboard", "common"]);
  const [me, setMe] = useState<LoadState<CurrentAccount>>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    API.getMe({ signal: controller.signal })
      .then((account) => {
        if (!controller.signal.aborted) setMe({ status: "ready", value: account });
      })
      .catch((err) => {
        if (!controller.signal.aborted) setMe({ status: "error", message: errMsg(err) });
      });
    return () => controller.abort();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-medium">{t("dashboard:settings_account")}</h2>
        <p className="max-w-[40em] text-sm text-muted-foreground">{t("dashboard:account_desc")}</p>
      </div>
      {me.status === "loading" ? (
        <Loading />
      ) : me.status === "error" ? (
        <p role="alert" className="text-sm text-destructive">
          {t("dashboard:account_load_failed", { message: me.message })}
        </p>
      ) : (
        <>
          <MyAccountCard account={me.value} />
          {me.value.role === "admin" && <MembersPanel selfId={me.value.id} />}
        </>
      )}
    </div>
  );
}

function Loading() {
  const { t } = useTranslation("common");
  return (
    <p role="status" className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
      <Loader2 aria-hidden className="size-4 animate-spin" />
      {t("loading")}
    </p>
  );
}

function MyAccountCard({ account }: { account: CurrentAccount }) {
  const { t } = useTranslation(["dashboard", "common"]);
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-0.5">
          <h3 className="text-sm font-medium">{t("dashboard:account_mine_title")}</h3>
          <div className="flex items-center gap-2">
            <span className="truncate text-sm">{account.username}</span>
            <Badge variant="secondary">{t(`dashboard:account_role_${account.role}`)}</Badge>
          </div>
        </div>
        <Button variant="outline" onClick={() => useAuthStore.getState().logout()} className="shrink-0">
          <LogOut aria-hidden data-icon="inline-start" />
          {t("common:logout")}
        </Button>
      </div>
      <ChangePasswordForm username={account.username} />
    </section>
  );
}

function ChangePasswordForm({ username }: { username: string }) {
  const { t } = useTranslation("dashboard");
  const currentId = useId();
  const nextId = useId();
  const confirmId = useId();
  const hintId = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mismatch = confirm.length > 0 && confirm !== next;
  const canSubmit = current.length > 0 && next.length >= MIN_PASSWORD_LENGTH && confirm === next && !saving;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const { access_token } = await API.changePassword(current, next);
      // 改密码让旧 token 失效，换上新 token 才能留在登录状态
      useAuthStore.getState().login(access_token, username);
      setCurrent("");
      setNext("");
      setConfirm("");
      useAppStore.getState().pushToast(t("account_password_changed"), "success");
    } catch (err) {
      setError(t("account_password_change_failed", { message: errMsg(err) }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={(e) => void submit(e)} className="flex max-w-sm flex-col gap-3">
      <h4 className="text-sm font-medium">{t("account_change_password")}</h4>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={currentId}>{t("account_current_password")}</Label>
        <Input
          id={currentId}
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={nextId}>{t("account_new_password")}</Label>
        <Input
          id={nextId}
          type="password"
          autoComplete="new-password"
          aria-describedby={hintId}
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
        <p id={hintId} className="text-xs text-muted-foreground">
          {t("account_password_hint", { min: MIN_PASSWORD_LENGTH })}
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={confirmId}>{t("account_confirm_password")}</Label>
        <Input
          id={confirmId}
          type="password"
          autoComplete="new-password"
          aria-invalid={mismatch || undefined}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {mismatch && <p className="text-xs text-destructive">{t("account_password_mismatch")}</p>}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div>
        <Button type="submit" disabled={!canSubmit}>
          {saving && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
          {t("account_change_password")}
        </Button>
      </div>
    </form>
  );
}

function MembersPanel({ selfId }: { selfId: string }) {
  const { t } = useTranslation(["dashboard", "common"]);
  const [members, setMembers] = useState<LoadState<MemberInfo[]>>({ status: "loading" });
  const [adding, setAdding] = useState(false);
  const [resetting, setResetting] = useState<MemberInfo | null>(null);
  const loadController = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    loadController.current?.abort();
    const controller = new AbortController();
    loadController.current = controller;
    try {
      const listed = await API.listMembers({ signal: controller.signal });
      if (!controller.signal.aborted) setMembers({ status: "ready", value: listed });
    } catch (err) {
      if (!controller.signal.aborted) setMembers({ status: "error", message: errMsg(err) });
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks-js/set-state-in-effect -- 挂载时拉取成员列表后回写，属于受控的初始化加载
    void load();
    return () => loadController.current?.abort();
  }, [load]);

  const replace = (updated: MemberInfo) =>
    setMembers((prev) =>
      prev.status === "ready"
        ? { status: "ready", value: prev.value.map((member) => (member.id === updated.id ? updated : member)) }
        : prev,
    );

  const update = async (member: MemberInfo, body: { role?: AccountRole; is_active?: boolean }) => {
    try {
      replace(await API.updateMember(member.id, body));
    } catch (err) {
      useAppStore.getState().pushToast(t("dashboard:members_update_failed", { message: errMsg(err) }), "error");
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-sm font-medium">{t("dashboard:members_title")}</h3>
        <Button onClick={() => setAdding(true)} className="shrink-0">
          <Plus aria-hidden data-icon="inline-start" />
          {t("dashboard:members_add")}
        </Button>
      </div>
      {members.status === "loading" ? (
        <Loading />
      ) : members.status === "error" ? (
        <div
          role="alert"
          className="flex items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/10 p-4"
        >
          <p className="min-w-0 text-sm text-destructive">
            {t("dashboard:members_load_failed", { message: members.message })}
          </p>
          <Button variant="outline" size="sm" onClick={() => void load()} className="shrink-0">
            {t("common:retry")}
          </Button>
        </div>
      ) : (
        <MembersTable
          members={members.value}
          selfId={selfId}
          onRoleChange={(member, role) => void update(member, { role })}
          onActiveChange={(member, isActive) => void update(member, { is_active: isActive })}
          onResetPassword={setResetting}
        />
      )}
      <AddMemberDialog
        open={adding}
        onOpenChange={setAdding}
        onAdded={(member) =>
          setMembers((prev) => (prev.status === "ready" ? { status: "ready", value: [...prev.value, member] } : prev))
        }
      />
      <ResetPasswordDialog member={resetting} onClose={() => setResetting(null)} />
    </section>
  );
}

function MembersTable({
  members,
  selfId,
  onRoleChange,
  onActiveChange,
  onResetPassword,
}: {
  members: MemberInfo[];
  selfId: string;
  onRoleChange: (member: MemberInfo, role: AccountRole) => void;
  onActiveChange: (member: MemberInfo, isActive: boolean) => void;
  onResetPassword: (member: MemberInfo) => void;
}) {
  const { t, i18n } = useTranslation("dashboard");
  const roleItems = ROLES.map((role) => ({ value: role, label: t(`account_role_${role}`) }));
  return (
    <div className="rounded-lg border border-border bg-card px-2">
      <Table aria-label={t("members_list")} className="table-fixed">
        <colgroup>
          <col />
          <col className="w-36" />
          <col className="w-20" />
          <col className="w-28" />
          <col className="w-12" />
        </colgroup>
        <TableHeader>
          <TableRow>
            <TableHead>
              <span className="text-muted-foreground">{t("members_col_username")}</span>
            </TableHead>
            <TableHead>
              <span className="text-muted-foreground">{t("members_col_role")}</span>
            </TableHead>
            <TableHead>
              <span className="text-muted-foreground">{t("members_col_active")}</span>
            </TableHead>
            <TableHead>
              <span className="text-muted-foreground">{t("members_col_created")}</span>
            </TableHead>
            <TableHead>
              <span className="sr-only">{t("members_col_actions")}</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((member) => {
            const isSelf = member.id === selfId;
            return (
              <TableRow key={member.id}>
                <TableCell>
                  <TruncatedText
                    text={isSelf ? t("members_you_named", { name: member.username }) : member.username}
                    className="font-medium"
                  />
                </TableCell>
                <TableCell>
                  <Select
                    items={roleItems}
                    value={member.role}
                    disabled={isSelf}
                    onValueChange={(value) => {
                      if (value === "admin" || value === "user") onRoleChange(member, value);
                    }}
                  >
                    <SelectTrigger aria-label={t("members_role_select", { name: member.username })} className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {roleItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </TableCell>
                <TableCell>
                  <Switch
                    aria-label={t("members_active_toggle", { name: member.username })}
                    checked={member.is_active}
                    disabled={isSelf}
                    onCheckedChange={(checked) => onActiveChange(member, checked)}
                  />
                </TableCell>
                <TableCell>
                  <span className="text-subtle-foreground tabular-nums">
                    {formatDate(member.created_at, i18n.language, DATE_OPTS)}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => onResetPassword(member)}
                      aria-label={t("members_reset_password_named", { name: member.username })}
                    >
                      <KeyRound aria-hidden />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

function AddMemberDialog({
  open,
  onOpenChange,
  onAdded,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAdded: (member: MemberInfo) => void;
}) {
  const { t } = useTranslation(["dashboard", "common"]);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dashboard:members_add")}</DialogTitle>
        </DialogHeader>
        {/* 每次打开都从空表单开始：表单只在打开期间挂载 */}
        <AddMemberForm
          onAdded={(member) => {
            onAdded(member);
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function AddMemberForm({ onAdded }: { onAdded: (member: MemberInfo) => void }) {
  const { t } = useTranslation(["dashboard", "common"]);
  const formId = useId();
  const usernameId = useId();
  const usernameHintId = useId();
  const passwordId = useId();
  const passwordHintId = useId();
  const roleId = useId();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AccountRole>("user");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const roleItems = ROLES.map((value) => ({ value, label: t(`dashboard:account_role_${value}`) }));
  const canSubmit = username.trim().length > 0 && password.length >= MIN_PASSWORD_LENGTH && !saving;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const member = await API.createMember({ username: username.trim(), password, role });
      useAppStore.getState().pushToast(t("dashboard:members_added", { name: member.username }), "success");
      onAdded(member);
    } catch (err) {
      setError(t("dashboard:members_add_failed", { message: errMsg(err) }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <DialogBody>
        <form id={formId} onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={usernameId}>{t("dashboard:members_username")}</Label>
            <Input
              id={usernameId}
              autoComplete="off"
              aria-describedby={usernameHintId}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <p id={usernameHintId} className="text-xs text-muted-foreground">
              {t("dashboard:members_username_hint")}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={passwordId}>{t("dashboard:members_password")}</Label>
            <Input
              id={passwordId}
              type="password"
              autoComplete="new-password"
              aria-describedby={passwordHintId}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p id={passwordHintId} className="text-xs text-muted-foreground">
              {t("dashboard:members_password_hint", { min: MIN_PASSWORD_LENGTH })}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label id={roleId}>{t("dashboard:members_role")}</Label>
            <Select
              items={roleItems}
              value={role}
              onValueChange={(value) => {
                if (value === "admin" || value === "user") setRole(value);
              }}
            >
              <SelectTrigger aria-labelledby={roleId} className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roleItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </form>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button variant="outline" />}>{t("common:cancel")}</DialogClose>
        <Button type="submit" form={formId} disabled={!canSubmit}>
          {saving && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
          {t("dashboard:members_add_submit")}
        </Button>
      </DialogFooter>
    </>
  );
}

function ResetPasswordDialog({ member, onClose }: { member: MemberInfo | null; onClose: () => void }) {
  return (
    <Dialog
      open={member !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>{member && <ResetPasswordForm member={member} onDone={onClose} />}</DialogContent>
    </Dialog>
  );
}

function ResetPasswordForm({ member, onDone }: { member: MemberInfo; onDone: () => void }) {
  const { t } = useTranslation(["dashboard", "common"]);
  const formId = useId();
  const passwordId = useId();
  const hintId = useId();
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canSubmit = password.length >= MIN_PASSWORD_LENGTH && !saving;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      await API.updateMember(member.id, { password });
      useAppStore
        .getState()
        .pushToast(t("dashboard:members_password_reset_done", { name: member.username }), "success");
      onDone();
    } catch (err) {
      setError(t("dashboard:members_update_failed", { message: errMsg(err) }));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <DialogHeader>
        <DialogTitle>{t("dashboard:members_reset_password_title", { name: member.username })}</DialogTitle>
        <DialogDescription>{t("dashboard:members_reset_password_desc", { name: member.username })}</DialogDescription>
      </DialogHeader>
      <DialogBody>
        <form id={formId} onSubmit={(e) => void submit(e)} className="flex flex-col gap-1.5">
          <Label htmlFor={passwordId}>{t("dashboard:account_new_password")}</Label>
          <Input
            id={passwordId}
            type="password"
            autoComplete="new-password"
            aria-describedby={hintId}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p id={hintId} className="text-xs text-muted-foreground">
            {t("dashboard:members_password_hint", { min: MIN_PASSWORD_LENGTH })}
          </p>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </form>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button variant="outline" />}>{t("common:cancel")}</DialogClose>
        <Button type="submit" form={formId} disabled={!canSubmit}>
          {saving && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
          {t("dashboard:members_reset_password_submit")}
        </Button>
      </DialogFooter>
    </>
  );
}
