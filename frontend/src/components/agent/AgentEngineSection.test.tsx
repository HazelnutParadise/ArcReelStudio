import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import { useConnectionsStore } from "@/stores/connections-store";
import type { CurrentAccount, ProviderCredential } from "@/types";
import type { AgentEngineStatus } from "@/types/agent-credential";

import { AgentEngineSection } from "./AgentEngineSection";

const claude: AgentEngineStatus = {
  engine: "claude",
  codex_credential_id: null,
  codex_effective_credential_id: 5,
  codex_model: "gpt-5.5",
  codex_models: ["gpt-5.5", "gpt-6-sol", "gpt-6-luna"],
};

function connection(id: number, provider: string, name: string): ProviderCredential {
  return {
    id,
    provider,
    name,
    api_key_masked: null,
    credentials_filename: null,
    base_url: null,
    access_key_masked: null,
    secret_key_masked: null,
    is_active: true,
    created_at: "2026-11-08T00:00:00Z",
  };
}

function asRole(role: CurrentAccount["role"]) {
  vi.spyOn(API, "getMe").mockResolvedValue({ id: "u1", username: "u1", role });
}

beforeEach(() => {
  const connections = [connection(5, "chatgpt-subscription", "me@example.com"), connection(6, "openai", "team key")];
  useConnectionsStore.setState({ connections, loaded: true });
  vi.spyOn(API, "listAllCredentials").mockResolvedValue({ credentials: connections });
});

describe("AgentEngineSection", () => {
  it("lets an admin switch new conversations to Codex", async () => {
    asRole("admin");
    vi.spyOn(API, "getAgentEngine").mockResolvedValue(claude);
    const setEngine = vi.spyOn(API, "setAgentEngine").mockResolvedValue({ ...claude, engine: "codex" });
    render(<AgentEngineSection />);

    await userEvent.click(await screen.findByRole("radio", { name: /Codex/ }));

    await waitFor(() =>
      expect(setEngine).toHaveBeenCalledWith({ engine: "codex", codex_credential_id: null, codex_model: "gpt-5.5" }),
    );
    expect(await screen.findByRole("combobox", { name: "Codex 用的连线" })).toBeInTheDocument();
  });

  it("lists ChatGPT subscription and OpenAI connections for Codex", async () => {
    asRole("admin");
    vi.spyOn(API, "getAgentEngine").mockResolvedValue({ ...claude, engine: "codex" });
    const setEngine = vi.spyOn(API, "setAgentEngine").mockResolvedValue({ ...claude, engine: "codex" });
    render(<AgentEngineSection />);

    await userEvent.click(await screen.findByRole("combobox", { name: "Codex 用的连线" }));
    expect(await screen.findByRole("option", { name: "ChatGPT 订阅 · me@example.com" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "OpenAI API Key · team key" }));

    await waitFor(() =>
      expect(setEngine).toHaveBeenCalledWith({ engine: "codex", codex_credential_id: 6, codex_model: "gpt-5.5" }),
    );
  });

  it("is read-only for members", async () => {
    asRole("user");
    vi.spyOn(API, "getAgentEngine").mockResolvedValue({ ...claude, engine: "codex" });
    render(<AgentEngineSection />);

    expect(await screen.findByText("只有管理员可以更换引擎。")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Codex/ })).toHaveAttribute("aria-disabled", "true");
  });
});
