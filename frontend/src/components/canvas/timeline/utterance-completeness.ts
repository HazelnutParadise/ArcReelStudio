import type { Utterance } from "@/types";

/**
 * 发声条目还没填完：文本为空，或台词没写说话人。服务端解析发声内容时会拒收这样的条目
 * （见 lib/speech/speech_composition），编辑区据此提示先填完，而不是报保存失败。
 */
export function isUtteranceIncomplete(utterance: Utterance): boolean {
  if (!utterance.text.trim()) return true;
  return utterance.kind === "dialogue" && !(utterance.speaker ?? "").trim();
}

/** 服务端因发声条目没填完而拒收的问题代码：文本为空解析失败，或台词没写说话人。 */
const INCOMPLETE_SPEECH_CODES: ReadonlySet<string> = new Set(["parse_failed", "empty_speaker"]);

/** 这次保存失败是不是正因为发声条目没填完；网络、服务端错误、修订冲突等都不是。 */
export function isIncompleteSpeechRejection(code: string | null | undefined): boolean {
  return code != null && INCOMPLETE_SPEECH_CODES.has(code);
}
