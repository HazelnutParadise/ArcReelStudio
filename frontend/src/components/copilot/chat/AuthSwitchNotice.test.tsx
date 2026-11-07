import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vite-plus/test";

import { ContentBlockRenderer } from "./ContentBlockRenderer";

describe("auth switch notice", () => {
  it("says the subscription ran out and when it switches back", () => {
    render(
      <ContentBlockRenderer
        block={{ type: "auth_switch_notice", auth_switch: { from: "subscription", to: "api_key", until: null } }}
        index={0}
      />,
    );

    expect(
      screen.getByText(/订阅额度用完了，下一条消息改用 API Key。.*重新登录 Claude 订阅后改回/),
    ).toBeInTheDocument();
  });
});
