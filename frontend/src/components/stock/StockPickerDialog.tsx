import { ExternalLink, Loader2, Search } from "lucide-react";
import { useEffect, useId, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppStore } from "@/stores/app-store";
import type { StockItem, StockKind, StockSearchResult, StockSource } from "@/types/stock";
import { errMsg, voidCall } from "@/utils/async";

interface StockPickerDialogProps {
  kind: StockKind;
  /** 把选中的素材存进项目；抛错时对话框留着，错误以提示显示。 */
  onPick: (item: StockItem) => Promise<void>;
  onClose: () => void;
}

/**
 * 免版权素材库的挑选对话框（docs/adr/0128）：搜索所有提供这种素材的来源，试听或看缩略图，选一条存进项目。
 * 只列不用署名就能商用的素材；还没设置密钥的来源在结果上方列出，能设的人可以当场填。
 */
export function StockPickerDialog({ kind, onPick, onClose }: StockPickerDialogProps) {
  const { t } = useTranslation("dashboard");
  const queryId = useId();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<StockSearchResult | null>(null);
  const [searching, setSearching] = useState(false);
  const [pickingId, setPickingId] = useState<string | null>(null);
  const [sources, setSources] = useState<StockSource[]>([]);

  useEffect(() => {
    let active = true;
    API.listStockSources()
      .then((response) => {
        if (active) setSources(response.sources);
      })
      .catch(() => {
        // 来源清单取不到时照常能搜索，只是看不到设置密钥的入口
      });
    return () => {
      active = false;
    };
  }, []);

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const text = query.trim();
    if (!text || searching) return;
    setSearching(true);
    try {
      setResult(await API.searchStock(kind, text));
    } catch (cause) {
      useAppStore.getState().pushToast(t("stock_search_failed", { message: errMsg(cause) }), "error");
    } finally {
      setSearching(false);
    }
  };

  const pick = async (item: StockItem) => {
    if (pickingId !== null) return;
    setPickingId(`${item.source}:${item.id}`);
    try {
      await onPick(item);
      onClose();
    } catch (cause) {
      useAppStore.getState().pushToast(t("stock_import_failed", { message: errMsg(cause) }), "error");
    } finally {
      setPickingId(null);
    }
  };

  const relevant = sources.filter((source) => source.kinds.includes(kind));
  const names = new Map(sources.map((source) => [source.id, source.display_name]));
  const failed = (result?.sources ?? []).filter(
    (entry) => entry.status === "failed" || entry.status === "key_rejected",
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent size="xl">
        <DialogHeader>
          <DialogTitle>{t(`stock_title_${kind}`)}</DialogTitle>
          <DialogDescription>{t("stock_desc")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="flex flex-col gap-4">
            <form className="flex items-end gap-2" onSubmit={(event) => voidCall(search(event))}>
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <Label htmlFor={queryId}>{t("stock_query")}</Label>
                <Input
                  id={queryId}
                  value={query}
                  maxLength={200}
                  placeholder={t(`stock_query_placeholder_${kind}`)}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
              <Button type="submit" disabled={!query.trim() || searching}>
                {searching ? <Loader2 aria-hidden className="animate-spin" /> : <Search aria-hidden />}
                {t("stock_search")}
              </Button>
            </form>
            <SourceKeys sources={relevant} onChange={setSources} />
            {failed.length > 0 && (
              <p role="status" className="text-xs text-muted-foreground">
                {t("stock_sources_failed", {
                  sources: failed.map((entry) => names.get(entry.source) ?? entry.source).join("、"),
                })}
              </p>
            )}
            {result !== null &&
              (result.items.length === 0 ? (
                <p role="status" className="text-sm text-muted-foreground">
                  {t("stock_no_results")}
                </p>
              ) : (
                <ul
                  aria-label={t("stock_results")}
                  className={kind === "image" ? "grid grid-cols-3 gap-3" : "flex flex-col gap-2"}
                >
                  {result.items.map((item) => (
                    <StockResult
                      key={`${item.source}:${item.id}`}
                      item={item}
                      sourceName={names.get(item.source) ?? item.source}
                      picking={pickingId === `${item.source}:${item.id}`}
                      disabled={pickingId !== null}
                      onPick={() => voidCall(pick(item))}
                    />
                  ))}
                </ul>
              ))}
          </div>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

interface StockResultProps {
  item: StockItem;
  sourceName: string;
  picking: boolean;
  disabled: boolean;
  onPick: () => void;
}

function StockResult({ item, sourceName, picking, disabled, onPick }: StockResultProps) {
  const { t } = useTranslation("dashboard");
  const meta = (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      <Badge variant="outline">{t(`stock_license_${item.license}`)}</Badge>
      <a
        href={item.page_url}
        target="_blank"
        rel="noreferrer noopener"
        className="inline-flex items-center gap-1 underline underline-offset-2"
      >
        {sourceName}
        <ExternalLink aria-hidden className="size-3" />
      </a>
      {item.creator && <span className="min-w-0 truncate">{item.creator}</span>}
      {item.duration_seconds !== null && (
        <span>{t("stock_seconds", { seconds: Math.round(item.duration_seconds) })}</span>
      )}
    </div>
  );
  const use = (
    <Button size="sm" disabled={disabled} onClick={onPick}>
      {picking && <Loader2 aria-hidden className="animate-spin" />}
      {t("stock_use")}
    </Button>
  );
  if (item.kind === "image") {
    return (
      <li className="flex min-w-0 flex-col gap-2 rounded-lg border border-border p-2">
        <div className="flex aspect-video items-center justify-center overflow-hidden rounded-md bg-muted">
          {item.preview_url && (
            <img src={item.preview_url} alt={item.title} loading="lazy" className="size-full object-cover" />
          )}
        </div>
        <p className="truncate text-sm" title={item.title}>
          {item.title}
        </p>
        {meta}
        {use}
      </li>
    );
  }
  return (
    <li className="flex min-w-0 flex-col gap-2 rounded-lg border border-border p-3">
      <div className="flex min-w-0 items-center gap-3">
        <p className="min-w-0 flex-1 truncate text-sm font-medium" title={item.title}>
          {item.title}
        </p>
        {use}
      </div>
      {meta}
      {item.preview_url && (
        // eslint-disable-next-line jsx-a11y/media-has-caption -- 音乐与音效的试听档，没有对白，无字幕源
        <audio
          controls
          preload="none"
          src={item.preview_url}
          aria-label={t("stock_preview", { title: item.title })}
          className="h-8 w-full"
        />
      )}
    </li>
  );
}

/** 还不能用的来源：能设置密钥的人当场填，不能设的人看到该找谁。 */
function SourceKeys({ sources, onChange }: { sources: StockSource[]; onChange: (sources: StockSource[]) => void }) {
  const { t } = useTranslation("dashboard");
  const missing = sources.filter((source) => !source.available);
  if (missing.length === 0) return null;
  return (
    <ul
      aria-label={t("stock_sources_need_key")}
      className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-3"
    >
      {missing.map((source) => (
        <SourceKeyRow key={source.id} source={source} onChange={onChange} />
      ))}
    </ul>
  );
}

function SourceKeyRow({ source, onChange }: { source: StockSource; onChange: (sources: StockSource[]) => void }) {
  const { t } = useTranslation("dashboard");
  const inputId = useId();
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!value.trim() || saving) return;
    setSaving(true);
    try {
      onChange((await API.setStockSourceKey(source.id, value.trim())).sources);
    } catch (cause) {
      useAppStore.getState().pushToast(errMsg(cause), "error");
    } finally {
      setSaving(false);
    }
  };

  if (!source.can_set_key) {
    return (
      <li className="text-xs text-muted-foreground">{t("stock_key_ask_admin", { source: source.display_name })}</li>
    );
  }
  return (
    <li>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(event) => voidCall(save(event))}>
        <div className="flex min-w-48 flex-1 flex-col gap-1.5">
          <Label htmlFor={inputId}>
            {t(source.key_scope === "member" ? "stock_key_label_member" : "stock_key_label_workspace", {
              source: source.display_name,
            })}
          </Label>
          <Input
            id={inputId}
            type="password"
            autoComplete="off"
            value={value}
            maxLength={512}
            onChange={(event) => setValue(event.target.value)}
          />
        </div>
        {source.key_url && (
          <a
            href={source.key_url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex h-8 items-center text-sm underline underline-offset-2"
          >
            {t("stock_key_get")}
          </a>
        )}
        <Button type="submit" variant="outline" size="sm" disabled={!value.trim() || saving}>
          {saving && <Loader2 aria-hidden className="animate-spin" />}
          {t("stock_key_save")}
        </Button>
      </form>
    </li>
  );
}
