import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import type { SubscriptionLogin } from "@/types";

import { SubscriptionLoginDialog } from "./SubscriptionLoginDialog";

function login(overrides: Partial<SubscriptionLogin>): SubscriptionLogin {
  return {
    login_id: "L1",
    provider_id: "chatgpt-subscription",
    kind: "device_code",
    url: "https://auth.openai.com/codex/device",
    user_code: "ABCD-1234",
    expires_at: "2026-11-08T01:00:00Z",
    status: "pending",
    credential_id: null,
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  vi.spyOn(API, "listAllCredentials").mockResolvedValue({ credentials: [] });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("SubscriptionLoginDialog", () => {
  it("shows the device code and reports the new connection once the sign-in finishes", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(API, "startSubscriptionLogin").mockResolvedValue(login({}));
    vi.spyOn(API, "getSubscriptionLogin").mockResolvedValue(login({ status: "succeeded", credential_id: 9 }));
    const onSucceeded = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <SubscriptionLoginDialog
        providerId="chatgpt-subscription"
        providerName="ChatGPT"
        open
        onOpenChange={onOpenChange}
        onSucceeded={onSucceeded}
      />,
    );

    expect(await screen.findByText("ABCD-1234")).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });

    await waitFor(() => expect(onSucceeded).toHaveBeenCalledWith(9));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("sends the pasted code for a Claude sign-in", async () => {
    vi.spyOn(API, "startSubscriptionLogin").mockResolvedValue(
      login({ provider_id: "claude-subscription", kind: "code_paste", user_code: null, url: "https://claude.com/x" }),
    );
    const submit = vi
      .spyOn(API, "submitSubscriptionLoginCode")
      .mockResolvedValue(
        login({ provider_id: "claude-subscription", kind: "code_paste", status: "succeeded", credential_id: 3 }),
      );
    const onSucceeded = vi.fn();
    render(
      <SubscriptionLoginDialog
        providerId="claude-subscription"
        providerName="Claude"
        open
        onOpenChange={() => {}}
        onSucceeded={onSucceeded}
      />,
    );

    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "  code-123  " } });
    fireEvent.submit(screen.getByRole("textbox").closest("form") as HTMLFormElement);

    await waitFor(() => expect(submit).toHaveBeenCalledWith("claude-subscription", "L1", "code-123"));
    await waitFor(() => expect(onSucceeded).toHaveBeenCalledWith(3));
  });

  it("shows why a sign-in failed", async () => {
    vi.spyOn(API, "startSubscriptionLogin").mockResolvedValue(
      login({ provider_id: "claude-subscription", kind: "code_paste", user_code: null }),
    );
    vi.spyOn(API, "submitSubscriptionLoginCode").mockResolvedValue(
      login({ kind: "code_paste", status: "failed", error: "The code wasn't accepted" }),
    );
    render(
      <SubscriptionLoginDialog providerId="claude-subscription" providerName="Claude" open onOpenChange={() => {}} />,
    );

    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "bad" } });
    fireEvent.submit(screen.getByRole("textbox").closest("form") as HTMLFormElement);

    expect(await screen.findByRole("alert")).toHaveTextContent("The code wasn't accepted");
  });

  it("cancels an unfinished sign-in when closed", async () => {
    vi.spyOn(API, "startSubscriptionLogin").mockResolvedValue(login({}));
    vi.spyOn(API, "getSubscriptionLogin").mockResolvedValue(login({}));
    const cancel = vi.spyOn(API, "cancelSubscriptionLogin").mockResolvedValue();
    const { rerender } = render(
      <SubscriptionLoginDialog providerId="chatgpt-subscription" providerName="ChatGPT" open onOpenChange={() => {}} />,
    );
    await screen.findByText("ABCD-1234");

    rerender(
      <SubscriptionLoginDialog
        providerId="chatgpt-subscription"
        providerName="ChatGPT"
        open={false}
        onOpenChange={() => {}}
      />,
    );

    await waitFor(() => expect(cancel).toHaveBeenCalledWith("chatgpt-subscription", "L1"));
  });

  it("shows why the sign-in couldn't start", async () => {
    vi.spyOn(API, "startSubscriptionLogin").mockRejectedValue(new Error("CLI missing"));
    render(<SubscriptionLoginDialog providerId="grok-subscription" providerName="Grok" open onOpenChange={() => {}} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("CLI missing");
  });
});
