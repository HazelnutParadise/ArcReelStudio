import { useState, type ReactNode } from "react";
import { Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import type { ProjectSummary } from "@/types";
import type { Series } from "@/types/series";
import { DeleteSeriesDialog } from "./DeleteSeriesDialog";
import { SeriesAssetsPanel } from "./SeriesAssetsPanel";
import { SeriesProjectsPanel } from "./SeriesProjectsPanel";
import { SeriesSettingsForm } from "./SeriesSettingsForm";

interface SeriesDetailProps {
  series: Series;
  allSeries: Series[];
  projects: ProjectSummary[];
  onChange: (series: Series) => void;
  onDeleted: (series: Series) => void;
}

/** 一个系列的详情：设定、项目、共用资产与删除。切换系列时表单随 `key` 重置。 */
export function SeriesDetail({ series, allSeries, projects, onChange, onDeleted }: SeriesDetailProps) {
  const { t } = useTranslation("dashboard");
  const [deleting, setDeleting] = useState(false);

  return (
    <div className="flex flex-col gap-8">
      <Section title={t("series_settings_title")}>
        <SeriesSettingsForm key={series.id} series={series} onSaved={onChange} />
      </Section>
      <Section title={t("series_projects_title")}>
        <SeriesProjectsPanel series={series} allSeries={allSeries} projects={projects} onChange={onChange} />
      </Section>
      <Section title={t("series_assets_title")}>
        <SeriesAssetsPanel key={series.id} series={series} onChange={onChange} />
      </Section>
      <div>
        <Button variant="destructive" onClick={() => setDeleting(true)}>
          <Trash2 aria-hidden data-icon="inline-start" />
          {t("series_delete")}
        </Button>
      </div>
      <DeleteSeriesDialog
        series={series}
        open={deleting}
        onClose={() => setDeleting(false)}
        onDeleted={(removed) => {
          setDeleting(false);
          onDeleted(removed);
        }}
      />
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-base font-medium">{title}</h2>
      {children}
    </section>
  );
}
