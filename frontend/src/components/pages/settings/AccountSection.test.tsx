import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useAuthStore } from "@/stores/auth-store";
import type { CurrentAccount, MemberInfo } from "@/types";

import { AccountSection } from "./AccountSection";

const ADMIN: CurrentAccount = { id: "default", username: "admin", role: "admin" };
const MEMBER: CurrentAccount = { id: "u2", username: "editor", role: "user" };

function member(overrides: Partial<MemberInfo>): MemberInfo {
  return { id: "u2", username: "editor", role: "user", is_active: true, created_at: "2026-11-01T00:00:00Z", ...overrides };
}

describe("AccountSection", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useAppStore.setState(useAppStore.getInitialState(), true);
    useAuthStore.setState({ token: "old-token", username: "admin", isAuthenticated: true, isLoading: false });
  });

  it("普通成员只看到自己的账号，看不到成员管理", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(MEMBER);
    const listMembers = vi.spyOn(API, "listMembers");
    render(<AccountSection />);

    expect(await screen.findByText("editor")).toBeInTheDocument();
    expect(screen.getByText("成员", { selector: "[data-slot=badge]" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "成员列表" })).not.toBeInTheDocument();
    expect(listMembers).not.toHaveBeenCalled();
  });

  it("修改密码后换上新的登录 token", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(MEMBER);
    const change = vi.spyOn(API, "changePassword").mockResolvedValue({ access_token: "new-token" });
    const user = userEvent.setup();
    render(<AccountSection />);

    await user.type(await screen.findByLabelText("当前密码"), "old-password");
    await user.type(screen.getByLabelText("新密码"), "new-password");
    await user.type(screen.getByLabelText("确认新密码"), "new-password");
    await user.click(screen.getByRole("button", { name: "修改密码" }));

    expect(change).toHaveBeenCalledWith("old-password", "new-password");
    await waitFor(() => expect(useAuthStore.getState().token).toBe("new-token"));
    expect(useAppStore.getState().toast?.text).toBe("密码已修改");
  });

  it("两次输入的新密码不一致时不能提交", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(MEMBER);
    const user = userEvent.setup();
    render(<AccountSection />);

    await user.type(await screen.findByLabelText("当前密码"), "old-password");
    await user.type(screen.getByLabelText("新密码"), "new-password");
    await user.type(screen.getByLabelText("确认新密码"), "other-password");

    expect(screen.getByText("两次输入的新密码不一致")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "修改密码" })).toBeDisabled();
  });

  it("登出后回到未登录状态", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(MEMBER);
    const user = userEvent.setup();
    render(<AccountSection />);

    await user.click(await screen.findByRole("button", { name: "登出" }));

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });

  it("管理员可以停用其他成员，自己的那一行不可改", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(ADMIN);
    vi.spyOn(API, "listMembers").mockResolvedValue([
      member({ id: "default", username: "admin", role: "admin" }),
      member({}),
    ]);
    const update = vi.spyOn(API, "updateMember").mockResolvedValue(member({ is_active: false }));
    const user = userEvent.setup();
    render(<AccountSection />);

    const table = await screen.findByRole("table", { name: "成员列表" });
    expect(within(table).getByRole("switch", { name: "启用 admin" })).toHaveAttribute("aria-disabled", "true");

    const toggle = within(table).getByRole("switch", { name: "启用 editor" });
    await user.click(toggle);

    expect(update).toHaveBeenCalledWith("u2", { is_active: false });
    await waitFor(() => expect(toggle).not.toBeChecked());
  });

  it("管理员新增成员后出现在列表里", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(ADMIN);
    vi.spyOn(API, "listMembers").mockResolvedValue([member({ id: "default", username: "admin", role: "admin" })]);
    const create = vi.spyOn(API, "createMember").mockResolvedValue(member({ id: "u3", username: "writer" }));
    const user = userEvent.setup();
    render(<AccountSection />);

    await user.click(await screen.findByRole("button", { name: "新增成员" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("用户名"), "writer");
    await user.type(within(dialog).getByLabelText("初始密码"), "writer-pass");
    await user.click(within(dialog).getByRole("button", { name: "新增" }));

    expect(create).toHaveBeenCalledWith({ username: "writer", password: "writer-pass", role: "user" });
    const table = await screen.findByRole("table", { name: "成员列表" });
    expect(await within(table).findByText("writer")).toBeInTheDocument();
  });

  it("管理员替成员重设密码", async () => {
    vi.spyOn(API, "getMe").mockResolvedValue(ADMIN);
    vi.spyOn(API, "listMembers").mockResolvedValue([member({})]);
    const update = vi.spyOn(API, "updateMember").mockResolvedValue(member({}));
    const user = userEvent.setup();
    render(<AccountSection />);

    await user.click(await screen.findByRole("button", { name: "重设 editor 的密码" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("新密码"), "reset-pass-1");
    await user.click(within(dialog).getByRole("button", { name: "重设密码" }));

    expect(update).toHaveBeenCalledWith("u2", { password: "reset-pass-1" });
    await waitFor(() => expect(useAppStore.getState().toast?.text).toBe("已重设 editor 的密码"));
  });
});
