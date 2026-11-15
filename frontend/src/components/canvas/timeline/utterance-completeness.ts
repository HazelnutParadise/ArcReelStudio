import type { Utterance } from "@/types";

/**
 * 发声条目还没填完：文本为空，或台词没写说话人。服务端解析发声内容时会拒收这样的条目
 * （见 lib/speech/speech_composition），编辑区据此提示先填完，而不是报保存失败。
 */
export function isUtteranceIncomplete(utterance: Utterance): boolean {
  if (!utterance.text.trim()) return true;
  return utterance.kind === "dialogue" && !(utterance.speaker ?? "").trim();
}
