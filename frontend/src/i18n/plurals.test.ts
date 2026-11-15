import { describe, expect, it } from 'vite-plus/test';
import i18n from 'i18next';

type Messages = Record<string, unknown>;

const en = import.meta.glob<Messages>('./en/*.ts', { eager: true, import: 'default' });
const ru = import.meta.glob<Messages>('./ru/*.ts', { eager: true, import: 'default' });

function flatKeys(modules: Record<string, Messages>): Map<string, string> {
  const out = new Map<string, string>();
  for (const [path, messages] of Object.entries(modules)) {
    for (const [key, value] of Object.entries(messages)) {
      if (typeof value === 'string') out.set(`${path}:${key}`, value);
    }
  }
  return out;
}

/** 计数后面没有会变单复数的名词：括号里的数字、形容词、缩写单位、「N of M」这类。 */
const COUNT_WITHOUT_NOUN = new Set([
  'characters_count',
  'edit_render_blocked_view_issues',
  'notifications_trigger_unread',
  'usage_kpi_success_count',
  'usage_kpi_cancelled_count',
  'usage_kpi_unpriced_count',
  'usage_breakdown_unpriced',
  'agent_memory_index_stats',
  'agent_memory_index_over_limit',
  'segment_refs_stale_badge',
  'minutes_ago',
  'episode_available_videos_hint',
  'prompt_authoring_scope_pending',
  'prompt_authoring_scope_pending_prefill',
  'trash_restored_degraded_files',
  'ce_check_image_bytes',
  'market_entry_count_filtered',
  'replan_count_new_only',
  'edit_view_issues_title',
  'merge_count_script_plan',
  'merge_count_script',
  'merge_count_draft',
  'merge_count_prompt_text',
  'merge_count_speaker',
  'import_count',
  'sheet_batch_button.character',
  'sheet_batch_button.scene',
  'sheet_batch_button.prop',
  'sheet_batch_button.product',
  'sheet_batch_missing_description',
  'sheet_batch_targets',
  'sheet_batch_skipped',
  'sheet_batch_done',
  'sheet_batch_target_deleted',
  'trash_restored_degraded',
  // 分组通知只在条数大于 1 时出现，名词由 entity.* 以复数给出
  'group.generated',
  'group.created',
  'group.deleted',
  'group.updated',
  'group_deferred.generated',
  'group_deferred.created',
  'group_deferred.deleted',
  'group_deferred.updated',
]);

describe('plural forms', () => {
  it('gives every English count string a singular and a plural form', () => {
    const offenders = [...flatKeys(en)]
      .filter(([id, text]) => {
        const key = id.split(':')[1];
        return text.includes('{{count}}') && !/_(one|other)$/.test(key) && !COUNT_WITHOUT_NOUN.has(key);
      })
      .map(([id]) => id);
    expect(offenders).toEqual([]);
  });

  it('gives every Russian plural key all four forms', () => {
    const keys = flatKeys(ru);
    const offenders = [...keys.keys()]
      .filter((id) => id.endsWith('_one'))
      .flatMap((id) => ['_few', '_many', '_other'].map((s) => id.replace(/_one$/, s)))
      .filter((id) => !keys.has(id));
    expect(offenders).toEqual([]);
  });

  it('resolves English counts to the right noun form', async () => {
    const instance = i18n.createInstance();
    const dashboard = (en['./en/dashboard.ts'] ?? {}) as Messages;
    await instance.init({ lng: 'en', resources: { en: { dashboard } }, ns: ['dashboard'], defaultNS: 'dashboard' });
    expect(instance.t('storyboard_count', { count: 1 })).toBe('1 shot');
    expect(instance.t('storyboard_count', { count: 3 })).toBe('3 shots');
    expect(instance.t('lobby_hero_summary', { count: 1, completed: 1, inProduction: 2 })).toBe(
      '1 episode wrapped, 2 still in production.',
    );
  });
});
