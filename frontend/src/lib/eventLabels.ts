import type { RiskLevel } from '../types';

/** Human-readable names for integrity event kinds; unknown kinds fall back to the raw value. */
export const EVENT_LABEL: Record<string, string> = {
  ai_text: '回答疑似照读 AI 稿',
  latency_pattern: '回答前停顿模式异常',
  probe_gap: '追问表现落差',
  ai_similarity: '回答与 AI 答案高度相似',
  gaze_off_screen: '视线长时间离开屏幕',
  reading_motion: '疑似阅读动作',
  multi_person: '画面中出现多人',
  person_absent: '候选人离开画面',
  phone: '画面中出现手机',
  repeated_violation: '多次违规,面试被终止',
  suspicious_object: '画面中有可疑物品',
  keyboard_typing: '听到持续的键盘敲击声',
  other_voice: '听到其他人说话',
  background_noise: '环境嘈杂',
};

export const SEVERITY_LABEL: Record<RiskLevel, string> = { low: '低', medium: '中', high: '高' };

export function eventLabel(kind: string): string {
  return EVENT_LABEL[kind] ?? kind;
}

/** "14:32:05" from an ISO timestamp; the raw value when it cannot be parsed. */
export function clockTime(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? iso
    : date.toLocaleTimeString('zh-CN', { hour12: false });
}
