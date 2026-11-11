import { useState } from "react";
import { Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import { ASSET_TYPES, ASSET_TYPE_ICON } from "@/components/assets/asset-type-icons";
import { AssetPickerModal } from "@/components/assets/AssetPickerModal";
import { AssetThumb } from "@/components/assets/AssetThumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAppStore } from "@/stores/app-store";
import { errMsg } from "@/utils/async";
import type { AssetType } from "@/types/asset";
import type { Series } from "@/types/series";
import { useSeriesAssets } from "./useSeriesAssets";

interface SeriesAssetsPanelProps {
  series: Series;
  onChange: (series: Series) => void;
}

/** 系列共用的资产库条目：先选类型，再从资产库挑选加入；每条可移出。资产本身留在资产库。 */
export function SeriesAssetsPanel({ series, onChange }: SeriesAssetsPanelProps) {
  const { t } = useTranslation(["dashboard", "common", "assets"]);
  const assets = useSeriesAssets(series.asset_ids);
  const [pickerType, setPickerType] = useState<AssetType | null>(null);
  const [busy, setBusy] = useState(false);

  const existingNames = new Set(
    series.asset_ids.flatMap((id) => {
      const asset = assets[id];
      return asset && asset.type === pickerType ? [asset.name] : [];
    }),
  );

  const toast = (text: string, tone: "success" | "error", action?: { label: string; onClick: () => void }) =>
    useAppStore.getState().pushToast(text, tone, action ? { action } : undefined);

  const addAll = async (ids: string[]) => {
    setPickerType(null);
    setBusy(true);
    let added = 0;
    try {
      for (const id of ids) {
        onChange(await API.addSeriesAsset(series.id, id));
        added += 1;
      }
      toast(t("dashboard:series_asset_added", { count: added }), "success");
    } catch (err) {
      toast(t("dashboard:series_asset_failed", { message: errMsg(err) }), "error");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string, name: string) => {
    setBusy(true);
    try {
      onChange(await API.removeSeriesAsset(series.id, id));
      toast(t("dashboard:series_asset_removed", { name }), "success", {
        label: t("common:undo"),
        onClick: () => {
          API.addSeriesAsset(series.id, id).then(onChange, (err: unknown) =>
            toast(t("dashboard:series_asset_failed", { message: errMsg(err) }), "error"),
          );
        },
      });
    } catch (err) {
      toast(t("dashboard:series_asset_failed", { message: errMsg(err) }), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {series.asset_ids.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dashboard:series_assets_empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
          {series.asset_ids.map((id) => {
            const asset = assets[id];
            const name = asset?.name ?? id;
            const Icon = asset ? ASSET_TYPE_ICON[asset.type] : null;
            return (
              <li key={id} className="flex items-center gap-3 px-3 py-2">
                <AssetThumb
                  imageUrl={asset ? API.getGlobalAssetUrl(asset.image_path, asset.updated_at) : null}
                  alt=""
                  fallback={Icon && <Icon aria-hidden className="size-4" />}
                  className="w-16 shrink-0 rounded-md"
                />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{name}</span>
                  <span className="truncate text-xs text-muted-foreground">
                    {asset
                      ? t(`assets:type.${asset.type}`)
                      : asset === null
                        ? t("dashboard:series_asset_unavailable")
                        : t("common:loading")}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("dashboard:series_asset_remove", { name })}
                  disabled={busy}
                  onClick={() => void remove(id, name)}
                >
                  <X aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <div>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="outline" disabled={busy} />}>
            <Plus aria-hidden data-icon="inline-start" />
            {t("dashboard:series_assets_add")}
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {ASSET_TYPES.map((type) => {
              const Icon = ASSET_TYPE_ICON[type];
              return (
                <DropdownMenuItem key={type} onClick={() => setPickerType(type)}>
                  <Icon aria-hidden />
                  {t(`assets:type.${type}`)}
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {pickerType && (
        <AssetPickerModal
          type={pickerType}
          existingNames={existingNames}
          onClose={() => setPickerType(null)}
          onImport={(ids) => void addAll(ids)}
        />
      )}
    </div>
  );
}
