const TOKEN_KEY = "arcreel_auth_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  // react-doctor-disable-next-line react-doctor/auth-token-in-web-storage -- 后端为 OAuth2 Bearer，浏览器外的客户端共用同一 token；改 httpOnly cookie 需另建 cookie 认证与 CSRF 防护，XSS 防线在输出转义与 CSP
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function getAuthHeader(): string | null {
  const token = getToken();
  return token ? `Bearer ${token}` : null;
}

/** 登录令牌里的账号身份：`uid` 是账号 id，`sub` 是规范化后的用户名。 */
export interface TokenIdentity {
  userId: string;
  username: string;
}

/**
 * 从登录令牌（JWT）读出账号身份，只解码不验签，用于界面区分自己与其他成员；
 * 不是登录令牌、或缺 `uid` / `sub` 时返回 null。
 */
export function tokenIdentity(token: string | null): TokenIdentity | null {
  const payload = token?.split(".")[1];
  if (!payload) return null;
  try {
    const base64 = payload
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(payload.length / 4) * 4, "=");
    const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
    const claims: unknown = JSON.parse(new TextDecoder().decode(bytes));
    if (typeof claims !== "object" || claims === null) return null;
    const { uid, sub } = claims as { uid?: unknown; sub?: unknown };
    return typeof uid === "string" && typeof sub === "string" ? { userId: uid, username: sub } : null;
  } catch {
    return null;
  }
}
