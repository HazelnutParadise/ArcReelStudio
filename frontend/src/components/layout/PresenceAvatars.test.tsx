import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/stores/auth-store";
import { usePresenceStore } from "@/stores/presence-store";

import { PresenceAvatars } from "./PresenceAvatars";

describe("PresenceAvatars", () => {
  beforeEach(() => {
    useAuthStore.setState({ userId: "u-alice", username: "alice" });
    usePresenceStore.getState().clear();
  });

  it("只有自己在线时不显示", () => {
    usePresenceStore.getState().setMembers("demo", [{ user_id: "u-alice", username: "alice", views: [] }]);

    const { container } = render(<PresenceAvatars />);

    expect(container).toBeEmptyDOMElement();
  });

  it("列出自己以外的成员，点开可看到各自在看哪一集", async () => {
    const user = userEvent.setup();
    usePresenceStore.getState().setMembers("demo", [
      { user_id: "u-alice", username: "alice", views: ["episodes/1"] },
      { user_id: "u-bob", username: "bob", views: ["episodes/3", "characters"] },
      { user_id: "u-carol", username: "carol", views: [] },
    ]);

    render(<PresenceAvatars />);
    await user.click(screen.getByRole("button", { name: "也在这个项目的成员：bob、carol" }));

    expect(await screen.findByText("也在这个项目的成员")).toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(["Bbob · 正在看第 3 集、在项目里", "Ccarol · 在项目里"]);
  });

  it("关闭认证时没有账号身份，不显示", () => {
    useAuthStore.setState({ userId: null, username: null });
    usePresenceStore.getState().setMembers("demo", [{ user_id: "default", username: "local", views: [] }]);

    const { container } = render(<PresenceAvatars />);

    expect(container).toBeEmptyDOMElement();
  });

  it("超过三位时其余收进「+N」", () => {
    usePresenceStore.getState().setMembers(
      "demo",
      ["bob", "carol", "dave", "erin", "frank"].map((name) => ({ user_id: `u-${name}`, username: name, views: [] })),
    );

    render(<PresenceAvatars />);

    expect(screen.getByRole("button")).toHaveTextContent("BCD+2");
  });
});
