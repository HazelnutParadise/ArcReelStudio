import { useEffect, useId, useState, type ReactNode } from "react";
import { Play } from "lucide-react";
import { useTranslation } from "react-i18next";

import { API } from "@/api";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { LANGUAGE_DISPLAY_LABELS, SUPPORTED_LANGUAGES, type SupportedLanguage } from "@/i18n";
import { useAppStore } from "@/stores/app-store";
import { useOnboardingStore } from "@/stores/onboarding-store";
import { isThemePreference, setThemePreference, THEME_PREFERENCES, useThemePreference } from "@/theme";
import { errMsg } from "@/utils/async";

const LANGUAGE_ITEMS = SUPPORTED_LANGUAGES.map((lang) => ({ value: lang, label: LANGUAGE_DISPLAY_LABELS[lang] }));

function isSupportedLanguage(value: unknown): value is SupportedLanguage {
  return SUPPORTED_LANGUAGES.includes(value as SupportedLanguage);
}

/**
 * 全局设置「通用」：界面语言、主题、成片 GPU 编码与重看新手引导。
 * 各项都立即生效，因此这个视图没有保存栏：界面语言与主题是本机偏好，不经后端保存，选中后整页随即切换；
 * GPU 编码是服务端系统设置，切换时立即保存，保存失败则回到原值。
 */
export function GeneralSection() {
  const { t, i18n } = useTranslation(["dashboard", "onboarding"]);
  const startTour = useOnboardingStore((s) => s.start);
  const languageLabelId = useId();
  const themeLabelId = useId();
  const currentLanguage = i18n.resolvedLanguage ?? i18n.language;
  const theme = useThemePreference();
  const themeItems = THEME_PREFERENCES.map((value) => ({ value, label: t(`dashboard:settings_theme_${value}`) }));

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-medium">{t("dashboard:settings_general")}</h2>
      <div className="flex flex-col divide-y divide-border rounded-lg border border-border bg-card">
        <SettingRow
          label={
            <span id={languageLabelId} className="text-sm font-medium">
              {t("dashboard:settings_interface_language")}
            </span>
          }
        >
          <Select
            items={LANGUAGE_ITEMS}
            value={isSupportedLanguage(currentLanguage) ? currentLanguage : null}
            onValueChange={(value) => {
              if (isSupportedLanguage(value)) void i18n.changeLanguage(value);
            }}
          >
            <SelectTrigger aria-labelledby={languageLabelId} className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LANGUAGE_ITEMS.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingRow>
        <SettingRow
          label={
            <span id={themeLabelId} className="text-sm font-medium">
              {t("dashboard:settings_theme")}
            </span>
          }
        >
          <Select
            items={themeItems}
            value={theme}
            onValueChange={(value) => {
              if (isThemePreference(value)) setThemePreference(value);
            }}
          >
            <SelectTrigger aria-labelledby={themeLabelId} className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {themeItems.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </SettingRow>
        <GpuEncodingRow />
        <SettingRow
          label={<span className="text-sm font-medium">{t("onboarding:replay_title")}</span>}
          description={t("onboarding:replay_desc")}
        >
          <Button variant="outline" onClick={startTour}>
            <Play aria-hidden data-icon="inline-start" />
            {t("onboarding:replay_action")}
          </Button>
        </SettingRow>
      </div>
    </div>
  );
}

interface GpuEncodingState {
  enabled: boolean;
  encoder: string | null;
}

/** 成片 GPU 编码开关：服务端检测不到可用的 GPU 时禁用，成片始终用 CPU 编码。读取配置失败时不显示这一行。 */
function GpuEncodingRow() {
  const { t } = useTranslation("dashboard");
  const labelId = useId();
  const [state, setState] = useState<GpuEncodingState | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    API.getSystemConfig({ signal: controller.signal })
      .then(({ settings, options }) => {
        if (controller.signal.aborted) return;
        setState({ enabled: settings.gpu_encoding_enabled, encoder: options.gpu_encoder ?? null });
      })
      .catch(() => {
        // 读取失败只是不显示这一行；其他设置页会给出配置读取错误。
      });
    return () => controller.abort();
  }, []);

  if (state === null) return null;

  const available = state.encoder !== null;
  const toggle = async (checked: boolean) => {
    const previous = state.enabled;
    setState({ ...state, enabled: checked });
    setSaving(true);
    try {
      const { settings } = await API.updateSystemConfig({ gpu_encoding_enabled: checked });
      setState((current) => (current ? { ...current, enabled: settings.gpu_encoding_enabled } : current));
    } catch (err) {
      setState((current) => (current ? { ...current, enabled: previous } : current));
      useAppStore.getState().pushToast(t("settings_gpu_encoding_save_failed", { message: errMsg(err) }), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <SettingRow
      label={
        <span id={labelId} className="text-sm font-medium">
          {t("settings_gpu_encoding")}
        </span>
      }
      description={t(available ? "settings_gpu_encoding_desc_available" : "settings_gpu_encoding_desc_unavailable")}
    >
      <Switch
        aria-labelledby={labelId}
        checked={available && state.enabled}
        disabled={!available || saving}
        onCheckedChange={(checked) => void toggle(checked)}
      />
    </SettingRow>
  );
}

function SettingRow({ label, description, children }: { label: ReactNode; description?: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 px-4 py-3">
      <div className="flex min-w-0 flex-col gap-0.5">
        {label}
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
