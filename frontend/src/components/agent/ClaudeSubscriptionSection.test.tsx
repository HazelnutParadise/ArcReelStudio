import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vite-plus/test";

import { API } from "@/api";
import type { CurrentAccount } from "@/types";
import type { ClaudeSubscriptionStatus } from "@/types/agent-credential";

import { ClaudeSubscriptionSection } from "./ClaudeSubscriptionSection";

const loggedOut: ClaudeSubscriptionStatus = {
  logged_in: false,
  token_masked: null,
  logged_in_at: null,
  mode: "prefer_subscription",
  has_api_key: true,
  subscription: { blocked: false, until: null },
  api_key: { blocked: false, until: null },
};

const loggedIn: ClaudeSubscriptionStatus = { ...loggedOut, logged_in: true, token_masked: "sk-a…wxyz" };

function asRole(role: CurrentAccount["role"]) {
  vi.spyOn(API, "getMe").mockResolvedValue({ id: "u1", username: "u1", role });
}

beforeEach(() => {
  vi.spyOn(API, "cancelClaudeLogin").mockResolvedValue();
});

describe("ClaudeSubscriptionSection", () => {
  it("lets an admin sign in by opening the Claude page and pasting the code", async () => {
    asRole("admin");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(loggedOut);
    vi.spyOn(API, "startClaudeLogin").mockResolvedValue({
      login_id: "L1",
      authorize_url: "https://claude.com/cai/oauth/authorize?state=x",
    });
    const finish = vi.spyOn(API, "finishClaudeLogin").mockResolvedValue(loggedIn);
    render(<ClaudeSubscriptionSection />);

    fireEvent.click(await screen.findByRole("button", { name: "用 Claude 账号登录" }));

    const link = await screen.findByRole("link", { name: /打开 Claude 授权页/ });
    expect(link).toHaveAttribute("href", "https://claude.com/cai/oauth/authorize?state=x");
    expect(link).toHaveAttribute("target", "_blank");
    fireEvent.change(screen.getByLabelText("2. 把验证码粘贴到这里"), { target: { value: "  the-code  " } });
    fireEvent.click(screen.getByRole("button", { name: "完成登录" }));

    await screen.findByText("已登录");
    expect(finish).toHaveBeenCalledWith("L1", "the-code");
    expect(screen.queryByRole("link", { name: /打开 Claude 授权页/ })).not.toBeInTheDocument();
  });

  it("shows why a rejected code failed and asks to start over", async () => {
    asRole("admin");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(loggedOut);
    vi.spyOn(API, "startClaudeLogin").mockResolvedValue({ login_id: "L1", authorize_url: "https://claude.com/x" });
    vi.spyOn(API, "finishClaudeLogin").mockRejectedValue(new Error("Claude 没有接受这个验证码"));
    render(<ClaudeSubscriptionSection />);

    fireEvent.click(await screen.findByRole("button", { name: "用 Claude 账号登录" }));
    fireEvent.change(await screen.findByLabelText("2. 把验证码粘贴到这里"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "完成登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Claude 没有接受这个验证码");
    // 登录已结束，回到可以重新开始的状态
    expect(screen.getByRole("button", { name: "用 Claude 账号登录" })).toBeEnabled();
  });

  it("changes the mode and keeps subscription-only off until signed in", async () => {
    asRole("admin");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(loggedOut);
    const setMode = vi.spyOn(API, "setAgentAuthMode").mockResolvedValue({ ...loggedOut, mode: "prefer_api_key" });
    render(<ClaudeSubscriptionSection />);

    expect(await screen.findByRole("radio", { name: /只用订阅/ })).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(screen.getByRole("radio", { name: /优先用 API Key/ }));

    await waitFor(() => expect(setMode).toHaveBeenCalledWith("prefer_api_key"));
    await waitFor(() => expect(screen.getByRole("radio", { name: /优先用 API Key/ })).toBeChecked());
  });

  it("shows when the subscription is out of usage", async () => {
    asRole("admin");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue({
      ...loggedIn,
      subscription: { blocked: true, until: null },
    });
    render(<ClaudeSubscriptionSection />);

    expect(await screen.findByRole("status")).toHaveTextContent("重新登录后才会再使用订阅");
  });

  it("lets members see the status but not change anything", async () => {
    asRole("user");
    vi.spyOn(API, "getClaudeSubscription").mockResolvedValue(loggedIn);
    render(<ClaudeSubscriptionSection />);

    await screen.findByText("已登录");
    expect(screen.queryByRole("button", { name: "退出登录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "重新登录" })).not.toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) expect(radio).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByText("只有管理员可以登录、退出或修改使用方式。")).toBeInTheDocument();
  });
});
