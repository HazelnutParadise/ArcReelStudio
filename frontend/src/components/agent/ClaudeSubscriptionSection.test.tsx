import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { useConnectionsStore } from "@/stores/connections-store";
import type { CurrentAccount, ProviderCredential } from "@/types";
import type { ClaudeSubscriptionStatus } from "@/types/agent-credential";

import { ClaudeSubscriptionSection } from "./ClaudeSubscriptionSection";

const none: ClaudeSubscriptionStatus = {
  credential_id: null,
  credential_name: null,
  chosen_credential_id: null,
  mode: "prefer_subscription",
  has_api_key: true,
  subscription: { blocked: false, until: null },
  api_key: { blocked: false, until: null },
};

const connected: ClaudeSubscriptionStatus = { ...none, credential_id: 3, credential_name: "Claude 2026-11-08" };

function claudeConnection(id: number, name: string, isActive: boolean): ProviderCredential {
  return {
    id,
    provider: "claude-subscription",
    name,
    api_key_masked: null,
    credentials_filename: null,
    base_url: null,
    access_key_masked: null,
    secret_key_masked: null,
    is_active: isActive,
    created_at: "2026-11-08T00:00:00Z",
  };
}

function asRole(role: CurrentAccount["role"]) {
  vi.spyOn(API, "getMe").mockResolvedValue({ id: "u1", username: "u1", role });
}

beforeEach(() => {
  useConnectionsStore.setState({ connections: [], loaded: true });
  vi.spyOn(API, "listAllCredentials").mockResolvedValue({ credentials: [] });
  vi.spyOn(API, "cancelSubscriptionLogin").mockResolvedValue();
});

describe("ClaudeSubscriptionSection", () => {
  it("shows the connection the agent uses", async () => {
    asRole("admin");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(connected);
    render(<ClaudeSubscriptionSection />);

    expect(await screen.findByText("Claude 2026-11-08")).toBeInTheDocument();
  });

  it("lets an admin sign in a Claude account from here", async () => {
    asRole("admin");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(none);
    const start = vi.spyOn(API, "startSubscriptionLogin").mockResolvedValue({
      login_id: "L1",
      provider_id: "claude-subscription",
      kind: "code_paste",
      url: "https://claude.com/cai/oauth/authorize?state=x",
      user_code: null,
      expires_at: "2026-11-08T01:00:00Z",
      status: "pending",
      credential_id: null,
      error: null,
    });
    render(<ClaudeSubscriptionSection />);

    fireEvent.click(await screen.findByRole("button", { name: /Claude/ }));

    await waitFor(() => expect(start).toHaveBeenCalledWith("claude-subscription"));
    expect(await screen.findByRole("link")).toHaveAttribute("href", "https://claude.com/cai/oauth/authorize?state=x");
  });

  it("lets an admin pick another Claude connection for the agent", async () => {
    asRole("admin");
    useConnectionsStore.setState({
      connections: [claudeConnection(3, "Work", true), claudeConnection(4, "Personal", false)],
      loaded: true,
    });
    vi.spyOn(API, "listAllCredentials").mockResolvedValue({
      credentials: [claudeConnection(3, "Work", true), claudeConnection(4, "Personal", false)],
    });
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue({ ...connected, credential_name: "Work" });
    const choose = vi
      .spyOn(API, "setAgentSubscriptionConnection")
      .mockResolvedValue({ ...connected, credential_id: 4, credential_name: "Personal", chosen_credential_id: 4 });
    const user = userEvent.setup();
    render(<ClaudeSubscriptionSection />);

    await user.click(await screen.findByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Personal" }));

    await waitFor(() => expect(choose).toHaveBeenCalledWith(4));
  });

  it("only shows the status to members", async () => {
    asRole("user");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(connected);
    render(<ClaudeSubscriptionSection />);

    expect(await screen.findByText("Claude 2026-11-08")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Claude|帳號|账号|account/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
