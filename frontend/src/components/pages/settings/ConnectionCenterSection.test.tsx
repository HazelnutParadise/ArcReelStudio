import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import { API } from "@/api";
import { useConnectionsStore } from "@/stores/connections-store";
import type { ProviderCredential, ProviderInfo } from "@/types";

import { ConnectionCenterSection } from "./ConnectionCenterSection";

function provider(id: string, name: string, loginKind: ProviderInfo["login_kind"] = null): ProviderInfo {
  return {
    id,
    display_name: name,
    description: "",
    status: "ready",
    media_types: [],
    capabilities: [],
    credential_count: 0,
    models: {},
    login_kind: loginKind,
  };
}

function connection(overrides: Partial<ProviderCredential>): ProviderCredential {
  return {
    id: 1,
    provider: "openai",
    name: "Work key",
    api_key_masked: "sk-…abcd",
    credentials_filename: null,
    base_url: null,
    is_active: true,
    created_at: "2026-11-08T00:00:00Z",
    ...overrides,
  };
}

function renderCenter() {
  return render(
    <Router hook={memoryLocation({ path: "/settings" }).hook}>
      <ConnectionCenterSection />
    </Router>,
  );
}

beforeEach(() => {
  const credentials = [
    connection({}),
    connection({ id: 2, provider: "chatgpt-subscription", name: "me@x.com (plus)", api_key_masked: null }),
  ];
  useConnectionsStore.setState({ connections: credentials, loaded: true });
  vi.spyOn(API, "listAllCredentials").mockResolvedValue({ credentials });
  vi.spyOn(API, "getProviders").mockResolvedValue({
    providers: [provider("openai", "OpenAI"), provider("chatgpt-subscription", "ChatGPT 订阅", "device_code")],
  });
});

describe("ConnectionCenterSection", () => {
  it("shows when a subscription connection was signed in instead of a masked key", async () => {
    renderCenter();

    expect(await screen.findByText("sk-…abcd")).toBeInTheDocument();
    expect(await screen.findByText(/登录/)).toBeInTheDocument();
  });

  it("signs in a subscription from the add menu", async () => {
    const start = vi.spyOn(API, "startSubscriptionLogin").mockResolvedValue({
      login_id: "L1",
      provider_id: "chatgpt-subscription",
      kind: "device_code",
      url: "https://auth.openai.com/codex/device",
      user_code: "ABCD-1234",
      expires_at: "2026-11-08T01:00:00Z",
      status: "pending",
      credential_id: null,
      error: null,
    });
    vi.spyOn(API, "cancelSubscriptionLogin").mockResolvedValue();
    const user = userEvent.setup();
    renderCenter();

    await user.click(await screen.findByRole("button", { name: "新增连线" }));
    await user.click(await screen.findByRole("menuitem", { name: "ChatGPT 订阅" }));

    expect(await screen.findByText("ABCD-1234")).toBeInTheDocument();
    expect(start).toHaveBeenCalledWith("chatgpt-subscription");
  });
});
