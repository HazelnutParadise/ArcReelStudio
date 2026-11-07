import { afterEach, describe, expect, it } from "vitest";

import { useAuthStore } from "@/stores/auth-store";

import { clearToken, setToken, tokenIdentity } from "./auth";

/** 只拼出载荷的测试令牌：界面只解码、不验签。 */
function fakeJwt(claims: Record<string, unknown>): string {
  const encode = (value: unknown) =>
    btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(value))))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode(claims)}.signature`;
}

describe("tokenIdentity", () => {
  it("读出账号 id 与规范化后的用户名，非 ASCII 用户名同样可读", () => {
    expect(tokenIdentity(fakeJwt({ sub: "小明", uid: "u-1", ver: 0 }))).toEqual({ userId: "u-1", username: "小明" });
  });

  it.each([null, "", "not-a-jwt", "a.!!!.c", fakeJwt({ sub: "alice" }), fakeJwt({ uid: 1, sub: "alice" })])(
    "不是带账号的登录令牌时返回 null：%s",
    (token) => {
      expect(tokenIdentity(token)).toBeNull();
    },
  );
});

describe("auth store 的账号身份", () => {
  afterEach(() => {
    clearToken();
    useAuthStore.setState(useAuthStore.getInitialState(), true);
  });

  it("登录时以令牌里的规范写法为准，而不是输入框里的大小写", () => {
    useAuthStore.getState().login(fakeJwt({ sub: "alice", uid: "u-alice" }), "Alice");

    expect(useAuthStore.getState()).toMatchObject({ userId: "u-alice", username: "alice" });
  });

  it("刷新页面后从保存的令牌还原身份", () => {
    setToken(fakeJwt({ sub: "alice", uid: "u-alice" }));

    useAuthStore.getState().initialize();

    expect(useAuthStore.getState()).toMatchObject({ userId: "u-alice", username: "alice", isAuthenticated: true });
  });
});
