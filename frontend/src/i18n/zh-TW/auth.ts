import type enAuth from '../en/auth';

export default {
  'login': '登入',
  'logging_in': '登入中…',
  'login_failed': '登入失敗',
  'username': '使用者名稱',
  'password': '密碼',
  'login_subtitle': '使用帳號登入',
} satisfies Record<keyof typeof enAuth, string>;
