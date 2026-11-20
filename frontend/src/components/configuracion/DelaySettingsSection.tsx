import { useCallback, useState } from 'react';
import type { FormEvent } from 'react';
import { useAsyncData } from '@/hooks/useAsyncData';
import {
  createDelayRule,
  deleteDelayRule,
  fetchDelaySettings,
  setSmartDelayEnabled,
  updateDelayRule,
} from '@/services/delayRuleService';
import { delayRuleRangeLabel } from '@/types/delayRule';
import type { DelayDeliveryMethod, DelayRule } from '@/types/delayRule';
import { getErrorMessage } from '@/utils/errors';

const inputClass =
  'w-full rounded-xl border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900';

interface RulesEditorProps {
  title: string;
  method: DelayDeliveryMethod;
  rules: DelayRule[];
  onChanged: () => void;
}

/** Reglas de demora fija de un método de entrega: listado y alta/edición. Se guardan al instante. */
function RulesEditor({ title, method, rules, onChanged }: RulesEditorProps) {
  const [editingId, setEditingId] = useState<number | null>(null);
  const [minOrders, setMinOrders] = useState('0');
  const [maxOrders, setMaxOrders] = useState('');
  const [openEnded, setOpenEnded] = useState(false);
  const [minutes, setMinutes] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setEditingId(null);
    setMinOrders('0');
    setMaxOrders('');
    setOpenEnded(false);
    setMinutes('');
    setError(null);
  };

  const startEditing = (rule: DelayRule) => {
    setEditingId(rule.id);
    setMinOrders(String(rule.min_orders));
    setMaxOrders(rule.max_orders === null ? '' : String(rule.max_orders));
    setOpenEnded(rule.max_orders === null);
    setMinutes(String(rule.minutes));
    setError(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const min = Number(minOrders);
    const max = Number(maxOrders);
    const mins = Number(minutes);
    if (minOrders.trim() === '' || !Number.isInteger(min) || min < 0) {
      setError('Indicá desde cuántos pedidos en cola aplica la regla.');
      return;
    }
    if (!openEnded && (maxOrders.trim() === '' || !Number.isInteger(max) || max < min)) {
      setError('Indicá hasta cuántos pedidos (igual o mayor al inicio) o marcá "o más".');
      return;
    }
    if (minutes.trim() === '' || !Number.isInteger(mins) || mins <= 0) {
      setError('Los minutos deben ser mayores a 0.');
      return;
    }
    const payload = { min_orders: min, max_orders: openEnded ? null : max, minutes: mins };
    setSaving(true);
    try {
      if (editingId === null) await createDelayRule(method, payload);
      else await updateDelayRule(editingId, payload);
      reset();
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo guardar la regla.'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (rule: DelayRule) => {
    setError(null);
    try {
      await deleteDelayRule(rule.id);
      if (editingId === rule.id) reset();
      onChanged();
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo eliminar la regla.'));
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-gray-100 p-4" role="group" aria-label={`Reglas de ${title}`}>
      <h3 className="text-sm font-bold text-gray-900">{title}</h3>

      {rules.length === 0 ? (
        <p className="text-xs text-gray-500">
          Sin reglas: los pedidos entran sin demora estimada (o con la del historial, si está activa).
        </p>
      ) : (
        <ul className="space-y-1.5">
          {rules.map((rule) => (
            <li
              key={rule.id}
              className="flex items-center justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-gray-800"
            >
              <span>
                <span className="font-semibold">{delayRuleRangeLabel(rule)}</span> pedidos en cola →{' '}
                <span className="font-semibold">{rule.minutes} min</span>
              </span>
              <span className="flex gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => startEditing(rule)}
                  aria-label={`Editar regla ${delayRuleRangeLabel(rule)} de ${title}`}
                  className="text-xs font-semibold text-gray-700 underline hover:text-gray-900"
                >
                  Editar
                </button>
                <button
                  type="button"
                  onClick={() => void handleDelete(rule)}
                  aria-label={`Eliminar regla ${delayRuleRangeLabel(rule)} de ${title}`}
                  className="text-xs font-semibold text-red-600 underline hover:text-red-800"
                >
                  Eliminar
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      <form noValidate onSubmit={(e) => void handleSubmit(e)} className="space-y-2" aria-label={`Regla de ${title}`}>
        <p className="text-xs font-semibold text-gray-700">{editingId === null ? 'Agregar regla' : 'Editar regla'}</p>
        <div className="grid grid-cols-3 gap-2">
          <label className="space-y-1 text-[11px] font-semibold text-gray-600">
            Desde (pedidos)
            <input
              type="number"
              min={0}
              step={1}
              value={minOrders}
              onChange={(e) => setMinOrders(e.target.value)}
              aria-label={`Desde cuántos pedidos (${title})`}
              className={inputClass}
            />
          </label>
          <label className="space-y-1 text-[11px] font-semibold text-gray-600">
            Hasta (pedidos)
            <input
              type="number"
              min={0}
              step={1}
              value={openEnded ? '' : maxOrders}
              disabled={openEnded}
              onChange={(e) => setMaxOrders(e.target.value)}
              aria-label={`Hasta cuántos pedidos (${title})`}
              className={`${inputClass} disabled:bg-gray-100`}
            />
          </label>
          <label className="space-y-1 text-[11px] font-semibold text-gray-600">
            Minutos
            <input
              type="number"
              min={1}
              step={1}
              value={minutes}
              onChange={(e) => setMinutes(e.target.value)}
              aria-label={`Minutos de demora (${title})`}
              className={inputClass}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={openEnded}
            onChange={(e) => setOpenEnded(e.target.checked)}
            aria-label={`O más (${title})`}
            className="w-4 h-4 rounded text-zinc-900 focus:ring-zinc-900"
          />
          O más (sin tope superior; solo en la última regla)
        </label>
        {error && (
          <p role="alert" className="text-xs font-semibold text-red-600">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={saving}
            className="rounded-xl bg-zinc-900 px-4 py-2 text-xs font-bold text-white hover:opacity-90 disabled:opacity-50"
          >
            {editingId === null ? 'Agregar regla' : 'Guardar regla'}
          </button>
          {editingId !== null && (
            <button
              type="button"
              onClick={reset}
              className="rounded-xl border border-gray-200 px-4 py-2 text-xs font-semibold text-gray-700 hover:bg-gray-50"
            >
              Cancelar
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

/** Cómo se calcula la demora de los pedidos: demora inteligente y reglas de demora fija por método de entrega. */
export function DelaySettingsSection() {
  const load = useCallback(() => fetchDelaySettings(), []);
  const { data, error, reload, update } = useAsyncData(load, 'No se pudo cargar la configuración de demoras.');
  const [toggleError, setToggleError] = useState<string | null>(null);

  const handleToggle = async (enabled: boolean) => {
    setToggleError(null);
    try {
      const saved = await setSmartDelayEnabled(enabled);
      update(() => saved);
    } catch (err) {
      setToggleError(getErrorMessage(err, 'No se pudo cambiar la demora inteligente.'));
    }
  };

  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
      <div>
        <h2 className="text-base font-bold text-gray-900">Demora de los pedidos</h2>
        <p className="text-xs text-gray-500 mt-1">
          Definí cómo se calcula la demora que se promete al cliente. Los cambios se guardan al instante y no afectan a los
          pedidos ya tomados. Si la demora inteligente no tiene datos suficientes se usa la regla fija que corresponda a
          la cantidad de pedidos en cola; si no hay ninguna, el pedido entra sin demora y el cliente no recibe un tiempo
          estimado (el personal puede cargarla a mano desde el detalle del pedido).
        </p>
      </div>

      {error && !data && (
        <p role="alert" className="text-xs font-semibold text-red-600">
          {error}
        </p>
      )}

      {data && (
        <>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              role="switch"
              checked={data.smart_delay_enabled}
              onChange={(e) => void handleToggle(e.target.checked)}
              className="w-4 h-4 rounded text-zinc-900 focus:ring-zinc-900"
            />
            <span className="text-sm font-semibold text-gray-800">Demora inteligente (según el historial del local)</span>
          </label>
          {toggleError && (
            <p role="alert" className="text-xs font-semibold text-red-600">
              {toggleError}
            </p>
          )}
          {!data.smart_delay_enabled && (
            <p className="text-xs text-gray-500">
              Desactivada: el sistema no calcula ni sugiere demoras por historial.
            </p>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <RulesEditor title="Retiro" method="retiro" rules={data.pickup_rules} onChanged={reload} />
            <RulesEditor title="Envío" method="domicilio" rules={data.delivery_rules} onChanged={reload} />
          </div>
        </>
      )}
    </section>
  );
}
