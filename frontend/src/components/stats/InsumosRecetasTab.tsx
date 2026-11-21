import { useEffect, useMemo, useState } from 'react';
import { fetchIngredientConsumption } from '@/services/ingredientService';
import type { IngredientConsumptionResponse } from '@/types/ingredient';
import type { DateRangePreset } from '@/utils/dateRange';
import { parseDateInputValue, rangeForPreset, presetLabel } from '@/utils/dateRange';
import { formatCurrency } from '@/utils/currency';
import { formatQuantity } from '@/utils/ingredients';
import { PanelNote } from '@/components/ui/PanelNote';

const PRESETS: DateRangePreset[] = ['today', 'week', 'month', 'all', 'custom'];

export function InsumosRecetasTab() {
  const [preset, setPreset] = useState<DateRangePreset>('month');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  const [report, setReport] = useState<IngredientConsumptionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const range = useMemo(
    () =>
      rangeForPreset(preset, {
        from: customFrom ? parseDateInputValue(customFrom) : undefined,
        to: customTo ? parseDateInputValue(customTo) : undefined,
      }),
    [preset, customFrom, customTo]
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchIngredientConsumption({
      dateFrom: range.from,
      dateTo: range.to,
    })
      .then((data) => {
        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('No se pudo cargar el consumo de insumos.');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [range.from, range.to]);

  const items = report?.items ?? [];

  const totalSpent = useMemo(() => {
    return items.reduce((acc, item) => acc + (item.total_cost ?? item.total_quantity * (item.unit_cost ?? 0)), 0);
  }, [items]);

  const highestSpentItem = useMemo(() => {
    if (!items.length) return null;
    return [...items].sort((a, b) => (b.total_cost ?? 0) - (a.total_cost ?? 0))[0];
  }, [items]);

  const highestUnitCostItem = useMemo(() => {
    if (!items.length) return null;
    return [...items].sort((a, b) => (b.unit_cost ?? 0) - (a.unit_cost ?? 0))[0];
  }, [items]);

  const filteredItems = useMemo(() => {
    if (!searchTerm.trim()) return items;
    const term = searchTerm.toLowerCase();
    return items.filter((item) => item.ingredient_name.toLowerCase().includes(term));
  }, [items, searchTerm]);

  return (
    <div className="flex flex-col gap-6">
      {/* Barra de Filtros */}
      <div className="shrink-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white rounded-2xl shadow-xs p-5 border border-gray-100">
        <div>
          <h4 className="text-sm font-bold text-gray-900">Período de Insumos</h4>
          <p className="text-xs text-gray-500">Filtrá el consumo y gasto acumulado según el rango de ventas</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {PRESETS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPreset(p)}
              className={`rounded-xl px-3 py-1.5 text-xs font-semibold transition ${
                preset === p ? 'bg-black text-white' : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-100'
              }`}
            >
              {presetLabel(p)}
            </button>
          ))}
        </div>
      </div>

      {preset === 'custom' && (
        <div className="shrink-0 flex items-center gap-2 bg-white p-4 rounded-2xl shadow-xs border border-gray-100">
          <input
            type="date"
            value={customFrom}
            onChange={(e) => setCustomFrom(e.target.value)}
            className="flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"
          />
          <span className="text-gray-400 text-sm font-medium">a</span>
          <input
            type="date"
            value={customTo}
            onChange={(e) => setCustomTo(e.target.value)}
            className="flex-1 rounded-xl border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-black"
          />
        </div>
      )}

      {/* KPI Cards de Insumos y Recetas */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Gasto Total Acumulado</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(totalSpent)}</div>
          <span className="text-xs text-gray-400 mt-1">Costo de mercadería consumida</span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Insumo Mayor Gasto</span>
          <div className="mt-2 text-base font-bold text-gray-900 truncate">
            {highestSpentItem ? highestSpentItem.ingredient_name : 'Sin datos'}
          </div>
          <span className="text-xs text-amber-600 font-semibold mt-1">
            {highestSpentItem ? formatCurrency(highestSpentItem.total_cost ?? 0) : '-'}
          </span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Mayor Costo Unitario</span>
          <div className="mt-2 text-base font-bold text-gray-900 truncate">
            {highestUnitCostItem ? highestUnitCostItem.ingredient_name : 'Sin datos'}
          </div>
          <span className="text-xs text-gray-500 mt-1">
            {highestUnitCostItem ? `${formatCurrency(highestUnitCostItem.unit_cost ?? 0)} / ${highestUnitCostItem.unit}` : '-'}
          </span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Insumos en Recetas</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{items.length}</div>
          <span className="text-xs text-gray-400 mt-1">Ingredientes consumidos</span>
        </div>
      </div>

      {/* Buscador y Tabla de Insumos */}
      <div className="bg-white rounded-2xl shadow-xs border border-gray-100 overflow-hidden">
        <div className="p-5 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h4 className="text-base font-bold text-gray-900">Consumo y Costos de Insumos</h4>
            <p className="text-xs text-gray-500 mt-0.5">
              Detalle de cada insumo utilizado en pedidos completados del período según recetas
            </p>
          </div>
          <input
            type="text"
            placeholder="Buscar insumo..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="rounded-xl border border-gray-300 px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-black w-full sm:w-64"
          />
        </div>

        {loading ? (
          <div className="p-8">
            <PanelNote>Cargando reporte de insumos...</PanelNote>
          </div>
        ) : error ? (
          <div className="p-5 text-sm text-red-600 bg-red-50">{error}</div>
        ) : filteredItems.length === 0 ? (
          <div className="p-8 text-center text-sm text-gray-500">
            No se registraron consumos de insumos para este rango de fechas.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-gray-50/75 border-b border-gray-100 text-gray-600 font-semibold">
                  <th className="py-3 px-4">Insumo</th>
                  <th className="py-3 px-4">Unidad</th>
                  <th className="py-3 px-4 text-right">Costo Unitario</th>
                  <th className="py-3 px-4 text-right">Consumo Total</th>
                  <th className="py-3 px-4 text-right">Gasto Acumulado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredItems.map((item) => (
                  <tr key={item.ingredient_id} className="hover:bg-gray-50/50 transition">
                    <td className="py-3 px-4 font-bold text-gray-900">{item.ingredient_name}</td>
                    <td className="py-3 px-4 text-gray-500">{item.unit}</td>
                    <td className="py-3 px-4 text-right font-medium text-gray-700">
                      {formatCurrency(item.unit_cost ?? 0)}
                    </td>
                    <td className="py-3 px-4 text-right font-semibold text-gray-900">
                      {formatQuantity(item.total_quantity)} {item.unit}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-gray-900">
                      {formatCurrency(item.total_cost ?? item.total_quantity * (item.unit_cost ?? 0))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
