import { useId, useState } from "react";
import { Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAppStore } from "@/stores/app-store";
import { errMsg } from "@/utils/async";
import type { ProjectSummary } from "@/types";
import type { Series } from "@/types/series";

interface SeriesProjectsPanelProps {
  series: Series;
  /** 全部系列，用来标出候选项目当前属于哪个系列。 */
  allSeries: Series[];
  projects: ProjectSummary[];
  onChange: (series: Series) => void;
}

/** 系列里的项目：加入（不在本系列的项目，已属其他系列的会被移过来）、移出、套用系列资产。 */
export function SeriesProjectsPanel({ series, allSeries, projects, onChange }: SeriesProjectsPanelProps) {
  const { t } = useTranslation(["dashboard", "common"]);
  const labelId = useId();
  const [candidate, setCandidate] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);

  const titleOf = (name: string) => projects.find((project) => project.name === name)?.title.trim() || name;
  const owner = (name: string) =>
    allSeries.find((other) => other.id !== series.id && other.project_names.includes(name));
  const options = projects
    .filter((project) => !series.project_names.includes(project.name))
    .map((project) => {
      const title = project.title.trim() || project.name;
      const from = owner(project.name);
      return {
        value: project.name,
        label: from ? t("dashboard:series_project_option_moves", { title, series: from.name }) : title,
      };
    });
  const hasAssets = series.asset_ids.length > 0;

  const run = async (action: () => Promise<Series>) => {
    setBusy(true);
    try {
      const next = await action();
      onChange(next);
      return next;
    } catch (err) {
      useAppStore.getState().pushToast(t("dashboard:series_project_failed", { message: errMsg(err) }), "error");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const add = async (name: string) => {
    const next = await run(() => API.addSeriesProject(series.id, name));
    if (next) {
      setCandidate(null);
      useAppStore.getState().pushToast(t("dashboard:series_project_added", { title: titleOf(name) }), "success");
    }
  };

  const remove = async (name: string) => {
    const next = await run(() => API.removeSeriesProject(series.id, name));
    if (next) {
      useAppStore.getState().pushToast(t("dashboard:series_project_removed", { title: titleOf(name) }), "success", {
        action: {
          label: t("common:undo"),
          onClick: () => void run(() => API.addSeriesProject(series.id, name)),
        },
      });
    }
  };

  const apply = async (name: string) => {
    setApplying(name);
    const project = titleOf(name);
    try {
      const result = await API.applyAssetsToProject({
        asset_ids: series.asset_ids,
        target_project: name,
        conflict_policy: "skip",
      });
      const counts = { project, copied: result.succeeded.length, skipped: result.skipped.length };
      const failed = result.failed.length;
      useAppStore
        .getState()
        .pushToast(
          failed > 0
            ? t("dashboard:series_apply_result_failed", { ...counts, failed })
            : t("dashboard:series_apply_result", counts),
          failed > 0 ? "warning" : "success",
        );
    } catch (err) {
      useAppStore.getState().pushToast(t("dashboard:series_apply_failed", { message: errMsg(err) }), "error");
    } finally {
      setApplying(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {series.project_names.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dashboard:series_projects_empty")}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border rounded-lg border border-border">
          {series.project_names.map((name) => {
            const title = titleOf(name);
            return (
              <li key={name} className="flex items-center gap-2 px-3 py-2">
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{title}</span>
                  {title !== name && <span className="truncate text-xs text-muted-foreground">{name}</span>}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  aria-label={t("dashboard:series_apply_to", { project: title })}
                  disabled={!hasAssets || applying !== null}
                  onClick={() => void apply(name)}
                >
                  {applying === name && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
                  {t("dashboard:series_apply")}
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={t("dashboard:series_project_remove", { title })}
                  disabled={busy}
                  onClick={() => void remove(name)}
                >
                  <X aria-hidden />
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      {!hasAssets && series.project_names.length > 0 && (
        <p className="text-xs text-muted-foreground">{t("dashboard:series_apply_needs_assets")}</p>
      )}
      <div className="flex flex-col gap-1.5">
        <span id={labelId} className="text-sm font-medium">
          {t("dashboard:series_project_add_label")}
        </span>
        {options.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("dashboard:series_project_none_available")}</p>
        ) : (
          <div className="flex items-center gap-2">
            <Select items={options} value={candidate} onValueChange={(value: string | null) => setCandidate(value)}>
              <SelectTrigger aria-labelledby={labelId} className="min-w-0 flex-1" disabled={busy}>
                <SelectValue placeholder={t("dashboard:series_project_add_placeholder")} />
              </SelectTrigger>
              <SelectContent>
                {options.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button disabled={!candidate || busy} onClick={() => candidate && void add(candidate)}>
              {busy && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
              {t("dashboard:series_project_add_button")}
            </Button>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t("dashboard:series_project_add_hint")}</p>
      </div>
    </div>
  );
}
