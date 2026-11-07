/** 账号角色：`admin` 可以管理成员，`user` 只能使用工作区。 */
export type AccountRole = "admin" | "user";

/** 当前登录的账号（`GET /auth/me`）。 */
export interface CurrentAccount {
  id: string;
  username: string;
  role: AccountRole;
}

/** 成员列表中的一个账号（`GET /users`）。 */
export interface MemberInfo {
  id: string;
  username: string;
  role: AccountRole;
  is_active: boolean;
  created_at: string;
}

export interface CreateMemberRequest {
  username: string;
  password: string;
  role: AccountRole;
}

/** 管理员修改成员：只提交改动的字段；`password` 为替成员重设的新密码。 */
export interface UpdateMemberRequest {
  role?: AccountRole;
  is_active?: boolean;
  password?: string;
}
