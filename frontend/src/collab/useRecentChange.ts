import { useEffect, useState } from "react";

/**
 * `value` 最近 `idleMs` 内变过就为 true，停住超过 `idleMs` 后为 false。
 * 用来让其他成员的名字标签在对方停下后淡出，不长时间盖住正文。
 */
export function useRecentChange(value: string, idleMs: number): boolean {
  const [idleValue, setIdleValue] = useState<string | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => setIdleValue(value), idleMs);
    return () => clearTimeout(timer);
  }, [value, idleMs]);
  return idleValue !== value;
}
