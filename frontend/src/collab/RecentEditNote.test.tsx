import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";

import type { RemoteEdit } from "./collab-client";
import { RecentEditNote } from "./RecentEditNote";

const bobEdit = (at: number): RemoteEdit => ({ userId: "u-bob", name: "bob", color: "#2563eb", at });

describe("RecentEditNote", () => {
  beforeEach(() => vi.useFakeTimers({ now: 100_000 }));
  afterEach(() => vi.useRealTimers());

  it("names the member who just changed the field, then goes away", () => {
    const { rerender } = render(<RecentEditNote edits={{}} path="aspect_ratio" />);
    expect(screen.queryByText("bob 刚改了这项")).not.toBeInTheDocument();

    rerender(<RecentEditNote edits={{ aspect_ratio: bobEdit(Date.now()) }} path="aspect_ratio" />);
    expect(screen.getByText("bob 刚改了这项")).toBeInTheDocument();

    act(() => vi.advanceTimersByTime(8000));
    expect(screen.queryByText("bob 刚改了这项")).not.toBeInTheDocument();
  });

  it("counts changes inside the field, such as one line of a list", () => {
    render(<RecentEditNote edits={{ "utterances.2.text": bobEdit(Date.now()) }} path="utterances" />);
    expect(screen.getByText("bob 刚改了这项")).toBeInTheDocument();
  });

  it("does not bring back an old change when the field shows up again", () => {
    render(<RecentEditNote edits={{ aspect_ratio: bobEdit(Date.now() - 60_000) }} path="aspect_ratio" />);
    expect(screen.queryByText("bob 刚改了这项")).not.toBeInTheDocument();
  });
});
