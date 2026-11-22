import { api } from './api';
import type { DelayDeliveryMethod, DelayRule, DelayRulePayload, DelaySettings } from '@/types/delayRule';

/** Demora inteligente (activada o no) y reglas de demora fija de retiro y envío. */
export async function fetchDelaySettings(signal?: AbortSignal): Promise<DelaySettings> {
  const { data } = await api.get<DelaySettings>('/delay-settings', { signal });
  return data;
}

export async function setSmartDelayEnabled(enabled: boolean): Promise<DelaySettings> {
  const { data } = await api.put<DelaySettings>('/delay-settings/smart', { enabled });
  return data;
}

export async function createDelayRule(deliveryMethod: DelayDeliveryMethod, payload: DelayRulePayload): Promise<DelayRule> {
  const { data } = await api.post<DelayRule>('/delay-settings/rules', { delivery_method: deliveryMethod, ...payload });
  return data;
}

export async function updateDelayRule(id: number, payload: DelayRulePayload): Promise<DelayRule> {
  const { data } = await api.put<DelayRule>(`/delay-settings/rules/${id}`, payload);
  return data;
}

export async function deleteDelayRule(id: number): Promise<void> {
  await api.delete(`/delay-settings/rules/${id}`);
}
