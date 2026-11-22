import type { PaymentSettings } from '@/hooks/useStoreSettingsForm';
import type { CardAppliesTo } from '@/types/storeConfig';

interface PaymentMethodsSectionProps {
  payments: PaymentSettings;
  setPayments: (payments: PaymentSettings) => void;
  /** Si el sistema tiene credenciales de MercadoPago: sin ellas no se puede activar. */
  mercadopagoAvailable: boolean;
}

const INPUT_CLASS = 'w-full px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900';

const CARD_OPTIONS: { value: CardAppliesTo; label: string }[] = [
  { value: 'pickup', label: 'Solo retiro' },
  { value: 'delivery', label: 'Solo envío' },
  { value: 'both', label: 'Retiro y envío' },
];

function Toggle({
  label,
  checked,
  onChange,
  disabled,
  hint,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  hint?: string;
}) {
  return (
    <div>
      <label className={`flex items-center gap-3 ${disabled ? 'opacity-60' : 'cursor-pointer'}`}>
        <input
          type="checkbox"
          role="switch"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 rounded text-zinc-900 focus:ring-zinc-900"
        />
        <span className="text-sm font-semibold text-gray-800">{label}</span>
      </label>
      {hint && <p className="text-[11px] text-gray-500 ml-7 mt-0.5">{hint}</p>}
    </div>
  );
}

function Field({ id, label, value, onChange, placeholder }: { id: string; label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-xs font-semibold text-gray-700">
        {label}
      </label>
      <input id={id} type="text" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} className={INPUT_CLASS} />
    </div>
  );
}

/** Qué medios de pago acepta el local y los datos de cobro de cada uno. */
export function PaymentMethodsSection({ payments, setPayments, mercadopagoAvailable }: PaymentMethodsSectionProps) {
  const update = (changes: Partial<PaymentSettings>) => setPayments({ ...payments, ...changes });
  const activeCount = [payments.acceptsCash, payments.acceptsTransfer, payments.acceptsCard, payments.acceptsMercadopago].filter(Boolean).length;
  // El último medio activo no se puede apagar: siempre tiene que quedar al menos uno.
  const isLastActive = (checked: boolean) => checked && activeCount === 1;

  return (
    <section className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-4">
      <div>
        <h2 className="text-base font-bold text-gray-900">Medios de pago</h2>
        <p className="text-xs text-gray-500 mt-1">
          Los clientes (web y bot) y el mostrador solo ofrecen los medios que actives acá. Siempre tiene que quedar al menos uno.
        </p>
      </div>

      <div className="space-y-4">
        <Toggle
          label="Efectivo"
          checked={payments.acceptsCash}
          disabled={isLastActive(payments.acceptsCash)}
          onChange={(acceptsCash) => update({ acceptsCash })}
        />

        <div className="space-y-3">
          <Toggle
            label="Transferencia"
            checked={payments.acceptsTransfer}
            disabled={isLastActive(payments.acceptsTransfer)}
            onChange={(acceptsTransfer) => update({ acceptsTransfer })}
          />
          {payments.acceptsTransfer && (
            <div className="grid sm:grid-cols-3 gap-3 ml-7">
              <Field id="transfer-alias" label="Alias" value={payments.transferAlias} onChange={(transferAlias) => update({ transferAlias })} placeholder="mi.local.mp" />
              <Field id="transfer-cbu" label="CBU / CVU" value={payments.transferCbu} onChange={(transferCbu) => update({ transferCbu })} placeholder="22 dígitos" />
              <Field id="transfer-holder" label="Titular" value={payments.transferHolder} onChange={(transferHolder) => update({ transferHolder })} placeholder="Nombre del titular" />
              <p className="sm:col-span-3 text-[11px] text-gray-500">Cargá el alias o el CBU, y el titular de la cuenta.</p>
              <div className="space-y-1 sm:col-span-3 max-w-xs">
                <label htmlFor="proof-retention" className="block text-xs font-semibold text-gray-700">
                  Horas que se guarda el comprobante
                </label>
                <input
                  id="proof-retention"
                  type="number"
                  min={1}
                  max={720}
                  value={payments.proofRetentionHours}
                  onChange={(e) => update({ proofRetentionHours: e.target.value })}
                  className={INPUT_CLASS}
                />
                <p className="text-[11px] text-gray-500">Pasado ese plazo desde que se sube, el comprobante se elimina solo (por defecto 48 h).</p>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3">
          <Toggle
            label="Tarjeta"
            checked={payments.acceptsCard}
            disabled={isLastActive(payments.acceptsCard)}
            onChange={(acceptsCard) => update({ acceptsCard })}
          />
          {payments.acceptsCard && (
            <div className="ml-7 space-y-1">
              <label htmlFor="card-applies-to" className="block text-xs font-semibold text-gray-700">
                Se cobra con tarjeta en
              </label>
              <select
                id="card-applies-to"
                value={payments.cardAppliesTo}
                onChange={(e) => update({ cardAppliesTo: e.target.value as CardAppliesTo })}
                className={`${INPUT_CLASS} max-w-xs bg-white`}
              >
                {CARD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <Toggle
          label="MercadoPago"
          checked={payments.acceptsMercadopago}
          disabled={!mercadopagoAvailable || isLastActive(payments.acceptsMercadopago)}
          hint={mercadopagoAvailable ? undefined : 'No hay credenciales de MercadoPago configuradas en el sistema.'}
          onChange={(acceptsMercadopago) => update({ acceptsMercadopago })}
        />
      </div>
    </section>
  );
}
