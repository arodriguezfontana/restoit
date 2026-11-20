export type DelayDeliveryMethod = 'retiro' | 'domicilio';

/** Regla de demora fija: con esa cantidad de pedidos en cola se promete `minutes` minutos. */
export interface DelayRule {
  id: number;
  delivery_method: DelayDeliveryMethod;
  min_orders: number;
  /** null: "o más". */
  max_orders: number | null;
  minutes: number;
}

export interface DelaySettings {
  smart_delay_enabled: boolean;
  pickup_rules: DelayRule[];
  delivery_rules: DelayRule[];
}

export interface DelayRulePayload {
  min_orders: number;
  max_orders: number | null;
  minutes: number;
}

/** Texto del rango de una regla: "hasta 10", "de 11 a 20" o "21 o más". */
export function delayRuleRangeLabel(rule: Pick<DelayRule, 'min_orders' | 'max_orders'>): string {
  if (rule.max_orders === null) return `${rule.min_orders} o más`;
  if (rule.min_orders === 0) return `hasta ${rule.max_orders}`;
  return `de ${rule.min_orders} a ${rule.max_orders}`;
}
