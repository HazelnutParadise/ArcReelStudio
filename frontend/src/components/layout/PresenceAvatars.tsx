import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useAuthStore } from "@/stores/auth-store";
import { usePresenceStore } from "@/stores/presence-store";
import type { ProjectPresenceMember } from "@/types";

/** 顶栏最多直接显示的头像数，其余收进「+N」。 */
const MAX_VISIBLE = 3;

function initialOf(username: string): string {
  return Array.from(username.trim())[0]?.toUpperCase() ?? "?";
}

/** 正在看的集号；不在某一集里时为 null。 */
function episodeOf(view: string): string | null {
  return /^episodes\/(\d+)/.exec(view)?.[1] ?? null;
}

function MemberViews({ member }: { member: ProjectPresenceMember }) {
  const { t } = useTranslation(["dashboard", "events"]);
  const labels = new Set(
    (member.views.length > 0 ? member.views : [""]).map((view) => {
      const episode = episodeOf(view);
      return episode ? t("presence_view_episode", { episode }) : t("presence_view_project");
    }),
  );
  return <span className="text-muted-foreground">{Array.from(labels).join(t("events:list.separator"))}</span>;
}

/** 顶栏的在线成员：只列出自己以外、也打开了这个项目的成员，点开看各自正在看哪里。 */
export function PresenceAvatars() {
  const { t } = useTranslation(["dashboard", "events"]);
  // 关闭认证时没有账号身份，也就无从区分成员，不显示
  const me = useAuthStore((s) => s.userId);
  const members = usePresenceStore((s) => s.members);
  const others = members.filter((member) => member.user_id !== me);
  if (me === null || others.length === 0) return null;

  const visible = others.slice(0, MAX_VISIBLE);
  const hidden = others.length - visible.length;
  const names = others.map((member) => member.username).join(t("events:list.separator"));

  return (
    <Popover>
      <PopoverTrigger render={<Button variant="ghost" size="sm" aria-label={t("presence_trigger", { names })} />}>
        <span aria-hidden className="flex -space-x-1.5">
          {visible.map((member) => (
            <span
              key={member.user_id}
              className="flex size-6 items-center justify-center rounded-full border-2 border-background bg-muted text-xs font-medium text-foreground"
            >
              {initialOf(member.username)}
            </span>
          ))}
          {hidden > 0 ? (
            <span className="flex size-6 items-center justify-center rounded-full border-2 border-background bg-muted text-xs text-muted-foreground">
              +{hidden}
            </span>
          ) : null}
        </span>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64">
        <p className="mb-2 text-xs font-medium text-muted-foreground">{t("presence_title")}</p>
        <ul className="flex flex-col gap-2 text-sm">
          {others.map((member) => (
            <li key={member.user_id} className="flex min-w-0 items-center gap-2">
              <span
                aria-hidden
                className="flex size-6 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium"
              >
                {initialOf(member.username)}
              </span>
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">{member.username}</span> · <MemberViews member={member} />
              </span>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
