import { ExternalLink, Loader2, Search } from "lucide-react";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
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
import type { StockItem, StockKind, StockSource, StockSourceStatus } from "@/types/stock";
import { errMsg, voidCall } from "@/utils/async";

interface StockPickerDialogProps {
  kind: StockKind;
  /** 把选中的素材存进项目；抛错时对话框留着，错误以提示显示。 */
  onPick: (item: StockItem) => Promise<void>;
  onClose: () => void;
}

/** 一个来源这次搜索走到哪一步：还在等、已取消，或者来源回报的状态。 */
type SourceProgress = { status: "searching" | "cancelled" } | { status: StockSourceStatus; items: StockItem[] };

/** 各来源的结果轮流排列，与一次问所有来源时服务端的排法一致。 */
function interleave(lists: StockItem[][]): StockItem[] {
  const out: StockItem[] = [];
  const longest = Math.max(0, ...lists.map((list) => list.length));
  for (let index = 0; index < longest; index += 1) {
    for (const list of lists) {
      const item = list[index];
      if (item) out.push(item);
    }
  }
  return out;
}

/**
 * 免版权素材库的挑选对话框（docs/adr/0128）：搜索所有提供这种素材的来源，试听或看缩略图，选一条存进项目。
 * 只列不用署名就能商用的素材。搜索前先说明哪些来源能直接用、哪些要先填密钥；搜索时逐个来源发请求，
 * 每个来源各自显示进度与结果，可以中途取消。
 */
export function StockPickerDialog({ kind, onPick, onClose }: StockPickerDialogProps) {
  const { t } = useTranslation("dashboard");
  const queryId = useId();
  const [query, setQuery] = useState("");
  const [progress, setProgress] = useState<Map<string, SourceProgress> | null>(null);
  const [pickingId, setPickingId] = useState<string | null>(null);
  const [sources, setSources] = useState<StockSource[]>([]);
  const controllerRef = useRef<AbortController | null>(null);

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
      controllerRef.current?.abort();
    };
  }, []);

  const relevant = sources.filter((source) => source.kinds.includes(kind));
  const usable = relevant.filter((source) => source.available);
  const locked = relevant.filter((source) => !source.available);
  const names = new Map(sources.map((source) => [source.id, source.display_name]));
  const nameOf = (id: string) => names.get(id) ?? id;
  const searching = progress !== null && [...progress.values()].some((entry) => entry.status === "searching");

  const settle = (sourceId: string, next: SourceProgress) => {
    setProgress((current) => {
      if (current === null || current.get(sourceId)?.status !== "searching") return current;
      return new Map(current).set(sourceId, next);
    });
  };

  const search = (event: FormEvent) => {
    event.preventDefault();
    const text = query.trim();
    if (!text || searching) return;
    const controller = new AbortController();
    controllerRef.current = controller;
    if (usable.length === 0 && sources.length > 0) {
      setProgress(new Map());
      return;
    }
    // 来源清单没取到时退回一次问所有来源
    const targets = usable.length > 0 ? usable.map((source) => source.id) : [null];
    setProgress(new Map(targets.map((id) => [id ?? "", { status: "searching" as const }])));
    for (const id of targets) {
      API.searchStock(kind, text, 1, { signal: controller.signal, source: id ?? undefined }).then(
        (result) => {
          if (controller.signal.aborted) return;
          if (id === null) {
            setProgress(
              new Map(
                result.sources.map((entry) => [
                  entry.source,
                  { status: entry.status, items: result.items.filter((item) => item.source === entry.source) },
                ]),
              ),
            );
            return;
          }
          settle(id, { status: result.sources[0]?.status ?? "ok", items: result.items });
        },
        (cause: unknown) => {
          if (controller.signal.aborted) return;
          if (id === null) {
            setProgress(null);
            useAppStore.getState().pushToast(t("stock_search_failed", { message: errMsg(cause) }), "error");
            return;
          }
          settle(id, { status: "failed", items: [] });
        },
      );
    }
  };

  const cancel = () => {
    controllerRef.current?.abort();
    setProgress((current) => {
      if (current === null) return current;
      const next = new Map(current);
      for (const [id, entry] of next) {
        if (entry.status === "searching") next.set(id, { status: "cancelled" });
      }
      return next;
    });
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

  const entries = progress === null ? [] : [...progress.entries()];
  const items = interleave(entries.map(([, entry]) => ("items" in entry ? entry.items : [])));
  const finished = progress !== null && !searching;
  const allEmpty =
    finished && items.length === 0 && entries.length > 0 && entries.every(([, entry]) => entry.status === "ok");

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent size="xl">
        <DialogHeader>
          <DialogTitle>{t(`stock_title_${kind}`)}</DialogTitle>
          <DialogDescription>{t("stock_desc")}</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <div className="flex flex-col gap-4">
            <form className="flex items-end gap-2" onSubmit={search}>
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
              {searching ? (
                <Button type="button" variant="outline" onClick={cancel}>
                  <Loader2 aria-hidden className="animate-spin" />
                  {t("stock_search_cancel")}
                </Button>
              ) : (
                <Button type="submit" disabled={!query.trim()}>
                  <Search aria-hidden />
                  {t("stock_search")}
                </Button>
              )}
            </form>
            {relevant.length > 0 && (
              <div className="flex flex-col gap-1 text-xs text-muted-foreground">
                <p>
                  {usable.length > 0
                    ? t("stock_sources_ready", { sources: usable.map((source) => source.display_name).join("、") })
                    : t("stock_sources_none_ready")}
                </p>
                {locked.length > 0 && (
                  <p>
                    {t("stock_sources_locked", { sources: locked.map((source) => source.display_name).join("、") })}
                  </p>
                )}
              </div>
            )}
            <SourceKeys sources={relevant} onChange={setSources} />
            {entries.length > 0 && (
              <ul aria-label={t("stock_progress")} aria-live="polite" className="flex flex-col gap-1 text-xs">
                {entries.map(([id, entry]) => (
                  <SourceProgressRow key={id} name={nameOf(id)} entry={entry} />
                ))}
              </ul>
            )}
            {finished && progress.size === 0 && (
              <p role="status" className="text-sm text-muted-foreground">
                {t("stock_sources_none_ready")}
              </p>
            )}
            {allEmpty && (
              <p role="status" className="text-sm text-muted-foreground">
                {t("stock_no_results")}
              </p>
            )}
            {items.length > 0 && (
              <ul
                aria-label={t("stock_results")}
                className={kind === "image" ? "grid grid-cols-3 gap-3" : "flex flex-col gap-2"}
              >
                {items.map((item) => (
                  <StockResult
                    key={`${item.source}:${item.id}`}
                    item={item}
                    sourceName={nameOf(item.source)}
                    picking={pickingId === `${item.source}:${item.id}`}
                    disabled={pickingId !== null}
                    onPick={() => voidCall(pick(item))}
                  />
                ))}
              </ul>
            )}
          </div>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}

/** 一个来源这次搜索的进度：等待中、找到几条、没找到、连不上、密钥被拒或已取消，各用一句白话。 */
function SourceProgressRow({ name, entry }: { name: string; entry: SourceProgress }) {
  const { t } = useTranslation("dashboard");
  if (entry.status === "searching") {
    return (
      <li className="flex items-center gap-1.5 text-muted-foreground">
        <Loader2 aria-hidden className="size-3 animate-spin" />
        {t("stock_source_searching", { source: name })}
      </li>
    );
  }
  if (entry.status === "cancelled") {
    return <li className="text-muted-foreground">{t("stock_source_cancelled", { source: name })}</li>;
  }
  if (entry.status === "key_rejected") {
    return <li className="text-destructive">{t("stock_source_key_rejected", { source: name })}</li>;
  }
  if (entry.status === "failed" || entry.status === "key_missing") {
    return (
      <li className="text-muted-foreground">
        {t(entry.status === "failed" ? "stock_source_failed" : "stock_source_key_missing", { source: name })}
      </li>
    );
  }
  const found = "items" in entry ? entry.items.length : 0;
  return (
    <li className="text-muted-foreground">
      {found > 0 ? t("stock_source_found", { source: name, count: found }) : t("stock_source_empty", { source: name })}
    </li>
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

/** 需要密钥的来源：还不能用的当场填密钥（不能设的人看到该找谁），已经设好的可以移除后重填。 */
function SourceKeys({ sources, onChange }: { sources: StockSource[]; onChange: (sources: StockSource[]) => void }) {
  const { t } = useTranslation("dashboard");
  const missing = sources.filter((source) => !source.available);
  const configured = sources.filter((source) => source.available && source.can_set_key && source.key_masked);
  if (missing.length === 0 && configured.length === 0) return null;
  return (
    <ul
      aria-label={t("stock_sources_keys")}
      className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-3"
    >
      {missing.map((source) => (
        <SourceKeyRow key={source.id} source={source} onChange={onChange} />
      ))}
      {configured.map((source) => (
        <ConfiguredKeyRow key={source.id} source={source} onChange={onChange} />
      ))}
    </ul>
  );
}

function ConfiguredKeyRow({ source, onChange }: { source: StockSource; onChange: (sources: StockSource[]) => void }) {
  const { t } = useTranslation("dashboard");
  const [removing, setRemoving] = useState(false);

  const remove = async () => {
    setRemoving(true);
    try {
      onChange((await API.deleteStockSourceKey(source.id)).sources);
    } catch (cause) {
      useAppStore.getState().pushToast(errMsg(cause), "error");
    } finally {
      setRemoving(false);
    }
  };

  return (
    <li className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span className="min-w-0 flex-1">
        {t("stock_key_configured", { source: source.display_name, key: source.key_masked })}
      </span>
      <Button variant="outline" size="sm" disabled={removing} onClick={() => voidCall(remove())}>
        {removing && <Loader2 aria-hidden className="animate-spin" />}
        {t("stock_key_remove", { source: source.display_name })}
      </Button>
    </li>
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
