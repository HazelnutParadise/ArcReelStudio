import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { useConnectionsStore } from "@/stores/connections-store";
import type { ProviderCredential } from "@/types";

import { ConnectionSelect } from "./ConnectionSelect";

const connection = (id: number, name: string, overrides: Partial<ProviderCredential> = {}): ProviderCredential => ({
  id,
  provider: "gemini-aistudio",
  name,
  api_key_masked: "AIza…abcd",
  credentials_filename: null,
  base_url: null,
  is_active: false,
  created_at: "2026-11-01T00:00:00Z",
  ...overrides,
});

describe("ConnectionSelect", () => {
  beforeEach(() => {
    useConnectionsStore.setState({
      loaded: true,
      connections: [
        connection(1, "公司帐", { is_active: true }),
        connection(2, "个人帐"),
        connection(3, "OpenAI", { provider: "openai" }),
      ],
    });
  });

  it("offers the provider's connections with its default first", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ConnectionSelect
        backendValue="gemini-aistudio/gemini-3-pro"
        value={null}
        onChange={onChange}
        label="图片的连线"
      />,
    );

    await user.click(screen.getByRole("combobox", { name: "图片的连线" }));
    const options = (await screen.findAllByRole("option")).map((option) => option.textContent);
    expect(options).toEqual(["默认（公司帐）", "公司帐", "个人帐"]);

    await user.click(screen.getByRole("option", { name: "个人帐" }));
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it("stays hidden when there is nothing to choose", () => {
    const { container, rerender } = render(
      <ConnectionSelect backendValue="openai/gpt-image-1" value={null} onChange={vi.fn()} label="连线" />,
    );
    expect(container).toBeEmptyDOMElement();

    // 自定义供应商的凭证就在供应商本身
    rerender(<ConnectionSelect backendValue="custom-3/model" value={null} onChange={vi.fn()} label="连线" />);
    expect(container).toBeEmptyDOMElement();

    // 没选模型时也没有连线可选
    rerender(<ConnectionSelect backendValue="" value={null} onChange={vi.fn()} label="连线" />);
    expect(container).toBeEmptyDOMElement();
  });
});
