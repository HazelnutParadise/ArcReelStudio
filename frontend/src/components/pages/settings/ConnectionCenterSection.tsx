import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "wouter";
import { Check, Loader2, LogIn, Plus, Settings2, Trash2 } from "lucide-react";

import { API } from "@/api";
import { providerSettingsPath } from "@/app-routes";
import { TruncatedText } from "@/components/shared/TruncatedText";
import { SubscriptionLoginDialog } from "@/components/subscriptions/SubscriptionLoginDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAppStore } from "@/stores/app-store";
import { useConnectionsStore } from "@/stores/connections-store";
import type { ProviderCredential, ProviderInfo } from "@/types";
import { errMsg } from "@/utils/async";

import { DeleteCredentialDialog } from "../CredentialList";

/**
 * 连线中心：全部供应商的帐号与金钥集中在这里看。同一个供应商可以有好几个连线，各处用模型的地方（默认模型、
 * 项目设置）可以各自指定用哪一个；没指定的用该供应商的「默认连线」。新增与编辑在供应商详情里进行。
 */
export function ConnectionCenterSection() {
  const { t, i18n } = useTranslation(["dashboard", "common"]);
  const connections = useConnectionsStore((s) => s.connections);
  const loaded = useConnectionsStore((s) => s.loaded);
  const refresh = useConnectionsStore((s) => s.refresh);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [deleting, setDeleting] = useState<ProviderCredential | null>(null);
  const [signingIn, setSigningIn] = useState<ProviderInfo | null>(null);

  useEffect(() => {
    let cancelled = false;
    void refresh().catch((err: unknown) => useAppStore.getState().pushToast(errMsg(err), "error"));
    void API.getProviders()
      .then((res) => {
        if (!cancelled) setProviders(res.providers);
      })
      .catch(() => {
        // 读不到供应商清单时只少了显示名，连线照常列出
      });
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const providerName = (id: string) => providers.find((provider) => provider.id === id)?.display_name ?? id;
  const isLoginBased = (id: string) => Boolean(providers.find((provider) => provider.id === id)?.login_kind);
  const keyProviders = providers.filter((provider) => !provider.login_kind);
  const subscriptionProviders = providers.filter((provider) => provider.login_kind);
  const groups = groupByProvider(connections);

  const makeDefault = async (connection: ProviderCredential) => {
    try {
      await API.activateCredential(connection.provider, connection.id);
      await refresh();
    } catch (err) {
      useAppStore.getState().pushToast(errMsg(err), "error");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 className="text-lg font-medium">{t("connection_center_title")}</h2>
          <p className="text-sm text-muted-foreground">{t("connection_center_desc")}</p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button size="sm" />}>
            <Plus aria-hidden data-icon="inline-start" />
            {t("connection_center_add")}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="relative max-h-80 overflow-y-auto">
            {subscriptionProviders.length > 0 && (
              <>
                <DropdownMenuGroup label={t("connection_center_add_subscription")}>
                  {subscriptionProviders.map((provider) => (
                    <DropdownMenuItem key={provider.id} onClick={() => setSigningIn(provider)}>
                      <LogIn aria-hidden />
                      {provider.display_name}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuGroup label={subscriptionProviders.length > 0 ? t("connection_center_add_key") : undefined}>
              {keyProviders.map((provider) => (
                <DropdownMenuItem
                  key={provider.id}
                  render={<Link href={providerSettingsPath({ preset: provider.id })} />}
                >
                  {provider.display_name}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      {!loaded ? (
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 aria-hidden className="size-4 animate-spin" />
          {t("common:loading")}
        </p>
      ) : groups.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          {t("connection_center_empty")}
        </p>
      ) : (
        groups.map(([provider, own]) => (
          <section key={provider} aria-label={providerName(provider)} className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-medium">{providerName(provider)}</h3>
              <span className="text-xs text-muted-foreground">
                {t("connection_center_count", { count: own.length })}
              </span>
              <Button
                variant="ghost"
                size="xs"
                className="ml-auto"
                render={<Link href={providerSettingsPath({ preset: provider })} />}
              >
                <Settings2 aria-hidden data-icon="inline-start" />
                {t("connection_center_manage")}
              </Button>
            </div>
            <ul className="flex flex-col divide-y divide-border rounded-lg border border-border bg-card">
              {own.map((connection) => (
                <li key={connection.id} className="flex items-center gap-3 px-3 py-2.5">
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="flex min-w-0 items-center gap-2 text-sm">
                      <TruncatedText text={connection.name} />
                      {connection.is_active && <Badge variant="secondary">{t("connection_default")}</Badge>}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {isLoginBased(connection.provider)
                        ? t("connection_center_signed_in_at", {
                            date: new Date(connection.created_at).toLocaleDateString(i18n.language),
                          })
                        : (connection.api_key_masked ??
                          connection.credentials_filename ??
                          connection.access_key_masked ??
                          "")}
                    </span>
                  </div>
                  {!connection.is_active && (
                    <Button variant="ghost" size="sm" onClick={() => void makeDefault(connection)}>
                      <Check aria-hidden data-icon="inline-start" />
                      {t("connection_center_make_default")}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={t("connection_center_delete", { name: connection.name })}
                    onClick={() => setDeleting(connection)}
                  >
                    <Trash2 aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {signingIn !== null && (
        <SubscriptionLoginDialog
          providerId={signingIn.id}
          providerName={signingIn.display_name}
          open
          onOpenChange={(open) => {
            if (!open) setSigningIn(null);
          }}
        />
      )}

      <DeleteCredentialDialog
        cred={deleting}
        providerId={deleting?.provider ?? ""}
        onClose={() => setDeleting(null)}
        onDeleted={() => setDeleting(null)}
      />
    </div>
  );
}

function groupByProvider(connections: readonly ProviderCredential[]): [string, ProviderCredential[]][] {
  const groups = new Map<string, ProviderCredential[]>();
  for (const connection of connections) {
    const own = groups.get(connection.provider) ?? [];
    own.push(connection);
    groups.set(connection.provider, own);
  }
  return [...groups.entries()];
}
