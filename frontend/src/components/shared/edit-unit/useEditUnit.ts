import { useCallback, useContext, useEffect, useState } from "react";

import type { CollabPeer, CollabRef } from "@/collab/collab-client";
import type { CollabFieldProps } from "@/collab/useLiveFields";
import type { UnitJson } from "@/collab/ydoc-json";
import { errMsg } from "@/utils/async";

import { EditUnitRetentionContext, useRetainWhile } from "./edit-unit-retention";

import { useLeaveGuard } from "./LeaveGuard";
import { useLiveEditUnit } from "./useLiveEditUnit";

/** 保存状态：「已保存」短暂显示后回到 idle。 */
export type SaveStatus = "idle" | "saving" | "saved" | "error";

/** 「已保存」在保存栏或提示条上停留的时长。 */
const SAVED_DISPLAY_MS = 2000;

export interface EditUnitOptions<T> {
  /**
   * 已保存的内容：加载结果，以及之后 SSE 推送、Agent 改写带来的新值。
   * 没有未保存修改时新值直接生效；有未保存修改时保留修改，并标出外部更新。
   */
  source: T;
  /**
   * 提交未保存修改。`savedValue` 是提交前的已保存内容，供按字段生成增量 PATCH。
   * 返回服务端保存后的内容；不返回时以提交的内容为准。抛错即保存失败，错误信息显示在保存栏或提示条上。
   * 一次保存分几步提交、前几步已经落盘时抛 `PartialSaveError`。需传稳定引用（`useCallback`）。
   */
  save: (value: T, savedValue: T) => Promise<T | void>;
  /** 判断两份内容是否相同，默认按 JSON 序列化比较。需传稳定引用（或模块级函数）。 */
  isEqual?: (a: T, b: T) => boolean;
  /** 离开拦截对话框的标题，如「分镜 3 有未保存的修改」；缺省为通用标题。 */
  leaveTitle?: string;
  /**
   * 对返回 true 的应用内导航不拦截，用于不会卸载本编辑单元的跳转（如同一编辑单元的分页切换）。
   * 参数是带查询串的目标路径。需传稳定引用。
   */
  allowNavigation?: (to: string) => boolean;
  /**
   * 有未保存修改时收到外部更新（如其他成员保存），按顶层字段合并：自己没改的字段采用新内容，
   * 自己改过的字段保留修改；只有双方改了同一字段且结果不同时才标出外部更新。
   * 只用于字段相互独立的对象；缺省时整份保留自己的修改并标出外部更新。
   */
  mergeExternalFields?: boolean;
  /**
   * 多人即时协作：给出单元在协作房间里的位置与内容互转。连上后单元内容就是房间里的文档，每个人的输入即时出现在
   * 其他人那里、由服务端合并写回，没有「未保存修改」与保存按钮；连不上时照旧用 `save` 改完保存。
   */
  collab?: CollabOptions<T>;
}

export interface CollabOptions<T> {
  /** 房间位置；为 null 时不协作（如只读或单元还没建立）。 */
  ref: CollabRef | null;
  /**
   * 编辑区内容 → 房间文档的内容（存储里的字段名）。`current` 是房间文档当前的内容：编辑区只负责其中几个字段时，
   * 其余字段从这里原样带上，不会被清掉。
   */
  toUnit: (value: T, current: UnitJson) => UnitJson;
  /** 房间文档的内容 → 编辑区内容；`fallback` 是当前已保存内容，补齐文档里没有的部分。 */
  fromUnit: (unit: UnitJson, fallback: T) => T;
}

/** 编辑单元处在多人即时协作中时的额外能力。 */
export interface LiveEditing {
  /** `synced` 即时同步中；`offline` 断线，修改留在本机，重连后补送。 */
  connection: "synced" | "offline";
  /** 同一单元里的其他成员。 */
  peers: CollabPeer[];
  /** 绑到输入框上：回报自己的光标位置、远端改动时保住光标、Ctrl/⌘+Z 只撤销自己的修改。 */
  fieldProps: (path: string) => CollabFieldProps;
  undo: () => void;
  redo: () => void;
  /** 绑定了 `fieldProps(path)` 的输入框，用来画其他人的光标。 */
  fieldElement: (path: string) => HTMLInputElement | HTMLTextAreaElement | null;
}

export interface SaveAndGenerateOptions {
  /** 保存前的确认（如「重新生成会让下游失效」），返回 false 时什么都不保存、不生成。 */
  confirm?: () => boolean | Promise<boolean>;
}

export interface EditUnit<T> {
  /** 当前内容，包含未保存修改。 */
  value: T;
  /** 已保存的内容。按字段子集判断修改（如侧栏分页的修改标记）时与 `value` 比较。 */
  savedValue: T;
  setValue: (next: T | ((prev: T) => T)) => void;
  /** 有未保存修改。 */
  dirty: boolean;
  status: SaveStatus;
  /** 最近一次保存失败的原因；再次编辑、放弃或保存成功时清除。 */
  error: string | null;
  /** 有未保存修改期间，已保存内容被外部更新。放弃修改即采用新内容。 */
  externallyUpdated: boolean;
  /** 外部移除或替换了当前单元，保留可见内容时的说明。 */
  externalChangeMessage?: string;
  /** 提交未保存修改，返回是否成功；没有修改时直接返回 true。 */
  save: () => Promise<boolean>;
  /** 丢弃未保存修改，回到最新的已保存内容。 */
  discard: () => void;
  /**
   * 调用方绕过 `save` 自己写入了已保存内容（如在提示上一键切换），随后重读会得到 `expected`。
   * 传函数时以上一个仍在等待的预期为底（没有时为当前已保存内容）推出新的预期：前一次重读还没回来就又写了一次，
   * 两次写入都算进去。之后 `source` 等于其中某个预期时当作自己的写入：成为已保存内容，未保存修改按字段保留，
   * 不标出外部更新；都不等时（重读还带来了别人的修改）照常按外部更新处理。需在触发重读之前调用。
   */
  expectSource: (expected: T | ((pending: T) => T)) => void;
  /**
   * 「保存并生成」：确认（如需要）→ 保存（有修改时）→ 生成。
   * 确认被取消时什么都不保存，保存失败时不生成；返回是否执行了生成。
   */
  saveAndGenerate: (generate: () => unknown, options?: SaveAndGenerateOptions) => Promise<boolean>;
  /** 多人即时协作中时的状态与输入框绑定；不在协作中（连不上或未开启）时为 null。 */
  live: LiveEditing | null;
}

interface UnitState<T> {
  value: T;
  saved: T;
  /** 最近一次见到的 `source`，用来识别外部更新。 */
  seenSource: T;
  status: SaveStatus;
  error: string | null;
  externallyUpdated: boolean;
  /** `expectSource` 登记的、之后的重读应当得到的已保存内容，按写入顺序。 */
  expected: T[];
}

/**
 * 保存只落盘了一部分（如项目 PATCH 成功、随后的参考图上传失败）：`saved` 成为新的已保存内容，
 * 放弃修改回到它，再次保存也以它为基准；`value` 是仍未保存的内容，缺省保留提交的内容。
 * 只抛普通错误会让已保存内容停在保存前，放弃修改后表单显示旧值，下次保存再把旧值写回。
 */
export class PartialSaveError<T> extends Error {
  readonly saved: T;
  readonly value: T | undefined;

  constructor(message: string, { saved, value, cause }: { saved: T; value?: T; cause?: unknown }) {
    super(message, { cause });
    this.name = "PartialSaveError";
    this.saved = saved;
    this.value = value;
  }
}

function jsonEqual<T>(a: T, b: T): boolean {
  return a === b || JSON.stringify(a) === JSON.stringify(b);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * 三方合并：`base` 是收到更新前的已保存内容，`mine` 是带未保存修改的内容，`theirs` 是新的已保存内容。
 * 返回合并结果，以及是否有双方都改过、结果又不同的字段。
 */
export function mergeExternalFields<T>(base: T, mine: T, theirs: T): { value: T; conflict: boolean } {
  if (!isPlainObject(base) || !isPlainObject(mine) || !isPlainObject(theirs)) {
    return { value: mine, conflict: !jsonEqual(mine, theirs) };
  }
  const merged: Record<string, unknown> = { ...theirs };
  let conflict = false;
  for (const key of new Set([...Object.keys(base), ...Object.keys(mine), ...Object.keys(theirs)])) {
    if (jsonEqual(mine[key], base[key])) continue;
    merged[key] = mine[key];
    if (!jsonEqual(theirs[key], base[key]) && !jsonEqual(mine[key], theirs[key])) conflict = true;
  }
  return { value: merged as T, conflict };
}

/** 把新到的已保存内容并入单元状态：自己写入的回显保留未保存修改，别人的修改按合并规则或标为外部更新。 */
function adoptSource<T>(
  state: UnitState<T>,
  source: T,
  isEqual: (a: T, b: T) => boolean,
  mergeFields: boolean,
): UnitState<T> {
  // 命中某个预期时，它和更早的预期都已兑现，只留下之后的；没命中说明掺进了别人的修改，预期全部作废
  const hit = state.expected.findIndex((expected) => isEqual(source, expected));
  const ownWrite = hit >= 0;
  const next = { ...state, seenSource: source, expected: ownWrite ? state.expected.slice(hit + 1) : [] };
  if (isEqual(source, state.saved)) return next;
  if (isEqual(state.value, state.saved)) {
    return { ...next, saved: source, value: source, externallyUpdated: false };
  }
  if (mergeFields || ownWrite) {
    const { value: merged, conflict } = mergeExternalFields(state.saved, state.value, source);
    // 先前标出的冲突仍未解决（保存或放弃才清除），本次合并没有新冲突也保留标记
    return { ...next, saved: source, value: merged, externallyUpdated: state.externallyUpdated || conflict };
  }
  return { ...next, saved: source, externallyUpdated: !isEqual(state.value, source) };
}

/**
 * 编辑单元：一次显式保存所提交的界面范围（一个设置视图、一张资产、一个分镜详情、一个记忆文件等）。
 * 单元内的字段先进入未保存修改，由 `save` 统一提交；挂载期间自动登记到离开拦截。
 */
export function useEditUnit<T>({
  source,
  save: submit,
  isEqual = jsonEqual,
  leaveTitle,
  allowNavigation,
  mergeExternalFields: mergeFields = false,
  collab,
}: EditUnitOptions<T>): EditUnit<T> {
  const [state, setState] = useState<UnitState<T>>(() => ({
    value: source,
    saved: source,
    seenSource: source,
    status: "idle",
    error: null,
    externallyUpdated: false,
    expected: [],
  }));

  // 已保存内容来自外部的变化：在渲染期同步（React 的「随 props 调整 state」写法），
  // 避免先用旧内容渲染一帧。与当前已保存内容相同的推送（如自己保存后的回显）不算外部更新。
  let current = state;
  if (!isEqual(source, state.seenSource)) {
    current = adoptSource(state, source, isEqual, mergeFields);
    setState(current);
  }

  const { value, saved, status, error } = current;
  const dirty = !isEqual(value, saved);
  const retention = useContext(EditUnitRetentionContext);

  useEffect(() => {
    if (status !== "saved") return;
    const timer = setTimeout(() => {
      setState((prev) => (prev.status === "saved" ? { ...prev, status: "idle" } : prev));
    }, SAVED_DISPLAY_MS);
    return () => clearTimeout(timer);
  }, [status]);

  const setValue = useCallback((next: T | ((prev: T) => T)) => {
    setState((prev) => ({
      ...prev,
      value: typeof next === "function" ? (next as (prev: T) => T)(prev.value) : next,
      status: prev.status === "saving" ? prev.status : "idle",
      error: null,
    }));
  }, []);

  const expectSource = useCallback(
    (expected: T | ((pending: T) => T)) => {
      setState((prev) => {
        const base = prev.expected.at(-1) ?? prev.seenSource;
        const value = typeof expected === "function" ? (expected as (pending: T) => T)(base) : expected;
        return isEqual(value, base) ? prev : { ...prev, expected: [...prev.expected, value] };
      });
    },
    [isEqual],
  );

  const discard = useCallback(() => {
    setState((prev) => ({ ...prev, value: prev.saved, status: "idle", error: null, externallyUpdated: false }));
  }, []);

  const save = useCallback(async () => {
    if (!dirty) return true;
    const submitted = value;
    setState((prev) => ({ ...prev, status: "saving", error: null }));
    try {
      const result = await submit(submitted, saved);
      const next = result === undefined ? submitted : (result as T);
      setState((prev) => ({
        ...prev,
        saved: next,
        // 保存期间没有继续编辑时，采用服务端规范化后的内容；继续编辑过的保留新修改
        value: isEqual(prev.value, submitted) ? next : prev.value,
        status: "saved",
        error: null,
        // 坚持保存时后写者生效，外部更新的标记随之清除
        externallyUpdated: false,
      }));
      return true;
    } catch (err) {
      if (err instanceof PartialSaveError) {
        const { saved: partial, value: unsaved } = err as PartialSaveError<T>;
        setState((prev) => ({
          ...prev,
          saved: partial,
          value: unsaved !== undefined && isEqual(prev.value, submitted) ? unsaved : prev.value,
          status: "error",
          error: errMsg(err),
          externallyUpdated: false,
        }));
        return false;
      }
      setState((prev) => ({ ...prev, status: "error", error: errMsg(err) }));
      return false;
    }
  }, [dirty, value, saved, submit, isEqual]);

  const saveAndGenerate = useCallback(
    async (generate: () => unknown, options?: SaveAndGenerateOptions) => {
      if (options?.confirm && !(await options.confirm())) return false;
      if (!(await save())) return false;
      await generate();
      return true;
    },
    [save],
  );

  // ── 多人即时协作：连上后内容就是房间里的文档 ──
  const live = useLiveEditUnit({ collab, source, saved, value, isEqual, onJoined: discard });

  // 协作中没有「未保存修改」，离开时等待的是背景写回
  const pending = live
    ? { dirty: false, saving: live.saving, save: live.unit.save }
    : { dirty, saving: status === "saving", save };
  // 外部替换后，可见单元已与真实视图分离，旧视图的放行规则不能继续用于主动跳转。
  const discarding = useLeaveGuard({
    ...pending,
    discard,
    title: leaveTitle,
    allowNavigation: retention?.message ? undefined : allowNavigation,
  });
  // 放弃修改后等待落定的删除自己移除了本单元，不当作外部移除保留
  useRetainWhile((pending.dirty || pending.saving) && !discarding);

  if (live) return { ...live.unit, expectSource, externalChangeMessage: retention?.message };

  return {
    value,
    savedValue: saved,
    setValue,
    dirty,
    status,
    error,
    externallyUpdated: (current.externallyUpdated || Boolean(retention?.message)) && dirty,
    externalChangeMessage: retention?.message,
    save,
    discard,
    expectSource,
    saveAndGenerate,
    live: null,
  };
}
