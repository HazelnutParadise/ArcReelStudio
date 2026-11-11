import { useCallback, useEffect, useState } from "react";
import { Layers, Loader2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import { CreateSeriesDialog } from "@/components/series/CreateSeriesDialog";
import { SeriesDetail } from "@/components/series/SeriesDetail";
import { SeriesList } from "@/components/series/SeriesList";
import { replaceSeries } from "@/components/series/series-settings";
import { PageHeader } from "@/components/shared/page-shell/PageHeader";
import { PageShell } from "@/components/shared/page-shell/PageShell";
import { useReturnTo } from "@/components/shared/page-shell/return-to";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { useAppStore } from "@/stores/app-store";
import { errMsg } from "@/utils/async";
import type { ProjectSummary } from "@/types";
import type { Series } from "@/types/series";

/**
 * 系列：项目之上的一层。左边是系列列表，右边是选中系列的设定、项目与共用资产。
 * 项目标题读不到时（项目列表加载失败）退回显示项目 ID，不影响系列本身的操作。
 */
export function SeriesPage() {
  const { t } = useTranslation(["dashboard", "common"]);
  const goBack = useReturnTo();
  const [list, setList] = useState<Series[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  const fetchSeries = useCallback((signal?: AbortSignal) => {
    API.listSeries().then(
      ({ series }) => {
        if (!signal?.aborted) setList(series);
      },
      (err: unknown) => {
        if (!signal?.aborted) setLoadError(errMsg(err));
      },
    );
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    fetchSeries(controller.signal);
    API.listProjects({ signal: controller.signal }).then(
      ({ projects: all }) => {
        if (!controller.signal.aborted) setProjects(all);
      },
      () => {
        // 取不到项目标题时退回显示项目 ID
      },
    );
    return () => controller.abort();
  }, [fetchSeries]);

  const replace = useCallback((next: Series) => setList((prev) => (prev ? replaceSeries(prev, next) : prev)), []);
  const selected = list?.find((item) => item.id === selectedId) ?? list?.[0] ?? null;

  let body;
  if (loadError) {
    body = (
      <div className="flex flex-col items-center gap-3 py-24 text-center">
        <p role="alert" className="text-sm text-destructive">
          {t("dashboard:series_load_failed", { message: loadError })}
        </p>
        <Button
          variant="outline"
          onClick={() => {
            setLoadError(null);
            fetchSeries();
          }}
        >
          {t("common:retry")}
        </Button>
      </div>
    );
  } else if (list === null) {
    body = (
      <div role="status" className="flex items-center justify-center gap-2 py-24 text-sm text-muted-foreground">
        <Loader2 aria-hidden className="size-4 animate-spin" />
        {t("common:loading")}
      </div>
    );
  } else if (list.length === 0) {
    body = (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Layers aria-hidden />
          </EmptyMedia>
          <EmptyTitle>{t("dashboard:series_list_empty")}</EmptyTitle>
          <EmptyDescription>{t("dashboard:series_list_empty_hint")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  } else {
    body = (
      <div className="flex flex-col gap-6 @3xl/page:flex-row @3xl/page:items-start">
        <div className="@3xl/page:w-72 @3xl/page:shrink-0">
          <SeriesList series={list} selectedId={selected?.id ?? null} onSelect={setSelectedId} />
        </div>
        <div className="min-w-0 flex-1">
          {selected ? (
            <SeriesDetail
              series={selected}
              allSeries={list}
              projects={projects}
              onChange={replace}
              onDeleted={(removed) => {
                setList((prev) => prev?.filter((item) => item.id !== removed.id) ?? prev);
                setSelectedId(null);
              }}
            />
          ) : (
            <p className="text-sm text-muted-foreground">{t("dashboard:series_select_prompt")}</p>
          )}
        </div>
      </div>
    );
  }

  return (
    <PageShell
      tier="full"
      header={
        <PageHeader
          back={{ label: t("common:back"), onClick: goBack }}
          title={t("dashboard:series_title")}
          subtitle={t("dashboard:series_subtitle")}
          actions={
            <Button disabled={list === null} onClick={() => setCreating(true)}>
              <Plus aria-hidden data-icon="inline-start" />
              {t("dashboard:series_new")}
            </Button>
          }
        />
      }
    >
      {body}
      {creating && (
        <CreateSeriesDialog
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setList((prev) => [...(prev ?? []), created]);
            setSelectedId(created.id);
            useAppStore.getState().pushToast(t("dashboard:series_created", { name: created.name }), "success");
          }}
        />
      )}
    </PageShell>
  );
}
