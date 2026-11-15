import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { useRecentChange } from "./useRecentChange";

describe("useRecentChange", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("is true right after the value changes and false once it has been idle", () => {
    const { result, rerender } = renderHook(({ value }) => useRecentChange(value, 1000), {
      initialProps: { value: "a" },
    });
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(false);

    rerender({ value: "b" });
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(600));
    rerender({ value: "c" });
    act(() => vi.advanceTimersByTime(600));
    expect(result.current).toBe(true);

    act(() => vi.advanceTimersByTime(400));
    expect(result.current).toBe(false);
  });
});
