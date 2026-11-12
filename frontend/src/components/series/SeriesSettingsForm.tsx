import { useId, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { API } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAppStore } from "@/stores/app-store";
import { errMsg } from "@/utils/async";
import type { Series } from "@/types/series";
import { SERIES_SETTING_MAX, changedFields, draftOf, type SeriesDraft } from "./series-settings";

interface SeriesSettingsFormProps {
  series: Series;
  onSaved: (series: Series) => void;
}

/** 系列的名称、简介、世界观与剧情设定。点「保存」才提交，且只提交有改动的字段。 */
export function SeriesSettingsForm({ series, onSaved }: SeriesSettingsFormProps) {
  const { t } = useTranslation(["dashboard", "common"]);
  const ids = { name: useId(), description: useId(), world: useId(), plot: useId() };
  const [draft, setDraft] = useState<SeriesDraft>(() => draftOf(series));
  const [saving, setSaving] = useState(false);
  const patch = changedFields(series, draft);
  const dirty = Object.keys(patch).length > 0;
  const set = (field: keyof SeriesDraft) => (value: string) => setDraft((prev) => ({ ...prev, [field]: value }));

  const save = async () => {
    if (!dirty || saving || !draft.name.trim()) return;
    setSaving(true);
    try {
      const next = await API.updateSeries(series.id, patch);
      setDraft(draftOf(next));
      onSaved(next);
      useAppStore.getState().pushToast(t("dashboard:series_saved"), "success");
    } catch (err) {
      useAppStore.getState().pushToast(t("dashboard:series_save_failed", { message: errMsg(err) }), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.name}>{t("dashboard:series_name_label")}</Label>
        <Input id={ids.name} value={draft.name} maxLength={100} onChange={(event) => set("name")(event.target.value)} />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={ids.description}>{t("dashboard:series_description_label")}</Label>
        <Textarea
          id={ids.description}
          rows={2}
          value={draft.description}
          onChange={(event) => set("description")(event.target.value)}
        />
      </div>
      <SettingField
        id={ids.world}
        label={t("dashboard:series_world_label")}
        value={draft.world_setting}
        onChange={set("world_setting")}
      />
      <SettingField
        id={ids.plot}
        label={t("dashboard:series_plot_label")}
        value={draft.plot_setting}
        onChange={set("plot_setting")}
      />
      <p className="text-xs text-muted-foreground">{t("dashboard:series_setting_hint", { max: SERIES_SETTING_MAX })}</p>
      <div>
        <Button type="submit" disabled={!dirty || saving || !draft.name.trim()}>
          {saving && <Loader2 aria-hidden data-icon="inline-start" className="animate-spin" />}
          {t("dashboard:series_save")}
        </Button>
      </div>
    </form>
  );
}

function SettingField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id}>{label}</Label>
        <span className="text-xs text-muted-foreground tabular-nums">
          {value.length} / {SERIES_SETTING_MAX}
        </span>
      </div>
      <Textarea
        id={id}
        rows={6}
        value={value}
        maxLength={SERIES_SETTING_MAX}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
