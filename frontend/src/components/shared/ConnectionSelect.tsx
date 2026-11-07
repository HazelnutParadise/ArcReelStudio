import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { connectionsOf, useConnectionsStore } from "@/stores/connections-store";

/**
 * 模型下拉下方的「连线」下拉：同一个供应商存了好几个帐号时，选这里用哪一个。
 *
 * 只对内置供应商出现；该供应商只有一个连线、也没有指定过时不出现（没有可选的）。`value` 为 null 即该供应商的默认连线。
 */
export function ConnectionSelect({
  backendValue,
  value,
  onChange,
  label,
}: {
  /** 同一字段选中的 `provider/model`；连线跟着它的供应商走。 */
  backendValue: string;
  value: number | null | undefined;
  onChange: (next: number | null) => void;
  /** 无障碍标签，例如「图片默认模型的连线」。 */
  label: string;
}) {
  const { t } = useTranslation("dashboard");
  const connections = useConnectionsStore((s) => s.connections);
  const fetchConnections = useConnectionsStore((s) => s.fetch);
  useEffect(() => {
    void fetchConnections();
  }, [fetchConnections]);

  const provider = backendValue.split("/", 1)[0] ?? "";
  if (!provider || provider.startsWith("custom-")) return null;
  const own = connectionsOf(connections, provider);
  const selected = value ?? null;
  if (own.length < 2 && selected === null) return null;

  const fallback = own.find((connection) => connection.is_active);
  const items = [
    {
      value: null,
      label: fallback ? t("connection_default_named", { name: fallback.name }) : t("connection_default"),
    },
    ...own.map((connection) => ({ value: connection.id, label: connection.name })),
  ];
  if (selected !== null && !own.some((connection) => connection.id === selected)) {
    items.push({ value: selected, label: t("connection_missing") });
  }

  return (
    <div className="flex items-center gap-2">
      <span className="shrink-0 text-xs text-muted-foreground">{t("connection_label")}</span>
      <Select items={items} value={selected} onValueChange={(next) => onChange(next ?? null)}>
        <SelectTrigger size="sm" aria-label={label} className="min-w-40">
          <SelectValue />
        </SelectTrigger>
        <SelectContent alignItemWithTrigger={false} align="start">
          {items.map((item) => (
            <SelectItem key={item.value ?? "default"} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
