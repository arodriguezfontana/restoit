import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchIngredientConsumption } from '@/services/ingredientService';
import { fetchStrategicInsight } from '@/services/statsService';
import type { IngredientConsumptionReport } from '@/types/ingredient';
import type { StrategicInsightResponse } from '@/types/stats';
import type { DateRange } from '@/utils/dateRange';
import { rangeForPreset } from '@/utils/dateRange';
import { formatCurrency } from '@/utils/currency';
import { formatQuantity } from '@/utils/ingredients';
import { PanelNote } from '@/components/ui/PanelNote';
import { SparklesIcon } from '@/components/Icons';

interface InsumosRecetasTabProps {
  range?: DateRange;
}

export function InsumosRecetasTab({ range: externalRange }: InsumosRecetasTabProps = {}) {
  const [searchTerm, setSearchTerm] = useState('');

  const [report, setReport] = useState<IngredientConsumptionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [aiData, setAiData] = useState<StrategicInsightResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const internalRange = useMemo(() => rangeForPreset('month'), []);
  const range = externalRange ?? internalRange;

  const [currentPage, setCurrentPage] = useState(1);
  const [prevFilter, setPrevFilter] = useState<{ searchTerm: string; from?: Date; to?: Date }>({
    searchTerm,
    from: range.from,
    to: range.to,
  });
  if (searchTerm !== prevFilter.searchTerm || range.from !== prevFilter.from || range.to !== prevFilter.to) {
    setPrevFilter({ searchTerm, from: range.from, to: range.to });
    if (range.from !== prevFilter.from || range.to !== prevFilter.to) {
      setLoading(true);
    }
    setCurrentPage(1);
  }

  const handleRequestAi = useCallback(async () => {
    setAiLoading(true);
    setAiError(null);
    try {
      const res = await fetchStrategicInsight({
        dateFrom: range.from,
        dateTo: range.to,
      });
      setAiData(res);
    } catch {
      setAiError('El servicio de Inteligencia Artificial tardó demasiado o no pudo responder. Podés reintentar.');
    } finally {
      setAiLoading(false);
    }
  }, [range.from, range.to]);

  useEffect(() => {
    let cancelled = false;

    fetchIngredientConsumption({
      dateFrom: range.from,
      dateTo: range.to,
    })
      .then((data) => {
        if (!cancelled) {
          setReport(data);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError('No se pudo cargar el consumo de insumos.');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [range.from, range.to]);

  const items = useMemo(() => report?.items ?? [], [report?.items]);

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

  const PAGE_SIZE = 6;
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE));
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredItems.slice(start, start + PAGE_SIZE);
  }, [filteredItems, currentPage]);

  return (
    <div className="flex flex-col gap-6">
      {/* Consejos de IA para Insumos y Compras */}
      <div className="shrink-0 bg-white p-5 rounded-2xl shadow-xs border border-gray-100 space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-gray-900">Consejos de IA</span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              Análisis operativo para compras, rotación de platos e insumos.
            </p>
          </div>
          {aiData && (
            <button
              type="button"
              onClick={handleRequestAi}
              className="text-xs font-semibold text-gray-600 hover:text-black transition self-start sm:self-auto cursor-pointer"
            >
              Actualizar consejos
            </button>
          )}
        </div>

        {aiError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <span>{aiError}</span>
            <button
              type="button"
              onClick={handleRequestAi}
              className="px-3 py-1.5 bg-red-700 hover:bg-red-800 text-white rounded-lg font-bold text-xs transition shrink-0 cursor-pointer"
            >
              Reintentar
            </button>
          </div>
        )}

        {aiLoading ? (
          <div className="py-8 flex flex-col items-center justify-center text-center space-y-2 bg-gray-50/60 rounded-xl border border-gray-100">
            <div className="w-7 h-7 border-3 border-gray-300 border-t-violet-600 rounded-full animate-spin" />
            <p className="text-xs font-bold text-gray-800">Analizando compras y consumo con IA...</p>
            <p className="text-[11px] text-gray-500">Evaluando rotación en recetas, gasto unitario y uso total.</p>
          </div>
        ) : aiData ? (
          (() => {
            const gastos = (aiData.spending_recommendations ?? []).slice(0, 6);
            return gastos.length === 0 ? (
              <div className="py-6 px-4 bg-gray-50/70 rounded-xl border border-gray-200 text-center">
                <p className="text-xs font-bold text-gray-800">Sin recomendaciones disponibles</p>
                <p className="text-xs text-gray-600 mt-1">
                  No hay suficiente consumo de ingredientes en este período para generar sugerencias de abastecimiento.
                </p>
              </div>
            ) : (
              <div className="bg-violet-50/70 border border-violet-200/70 rounded-xl p-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 mb-1">
                  <span className="text-xs font-bold uppercase tracking-wide text-violet-900">
                    Compras y Control de Gastos
                  </span>
                  <span className="text-[11px] text-violet-700 font-semibold">Insumos y rotación de platos</span>
                </div>
                <p className="text-[11px] text-violet-800/80 mb-2.5">
                  Sugerencias de abastecimiento según el consumo de ingredientes y la demanda de tus productos:
                </p>
                <ul className="space-y-2.5 text-xs text-violet-950 font-medium">
                  {gastos.map((g, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-violet-600 font-bold shrink-0">•</span>
                      <span>{g}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()
        ) : (
          <div className="py-6 px-4 bg-gray-50/50 rounded-xl border border-dashed border-gray-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left">
            <div>
              <p className="text-xs font-semibold text-gray-700">Consejos inteligentes para optimizar compras y materias primas</p>
              <p className="text-[11px] text-gray-400 mt-0.5">
                Elegí el rango de fechas arriba y presioná el botón para obtenersugerencias prácticas basadas en recetas, costos unitarios, gasto total y demanda de platos.
              </p>
            </div>
            <button
              type="button"
              onClick={handleRequestAi}
              aria-label="Consejos con IA"
              style={{ backgroundColor: 'var(--primary-color, #18181b)' }}
              className="px-3.5 py-1.5 text-white rounded-xl text-xs font-semibold hover:opacity-90 transition shrink-0 cursor-pointer flex items-center gap-1.5 active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black"
            >
              <SparklesIcon className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Consejos con IA</span>
            </button>
          </div>
        )}
      </div>

      {/* KPI Cards de Insumos y Recetas */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Gasto Total Acumulado</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{formatCurrency(totalSpent)}</div>
          <span className="text-xs text-gray-400 mt-1">Costo de mercadería consumida</span>
        </div>

        <div className="bg-white p-5 rounded-2xl shadow-xs border border-gray-100 flex flex-col justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Ingrediente Mayor Gasto</span>
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
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Ingredientes en Recetas</span>
          <div className="mt-2 text-2xl font-black text-gray-900">{items.length}</div>
          <span className="text-xs text-gray-400 mt-1">Ingredientes consumidos</span>
        </div>
      </div>

      {/* Buscador y Tabla de Insumos */}
      <div className="bg-white rounded-2xl shadow-xs border border-gray-100 overflow-hidden">
        <div className="p-5 border-b border-gray-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h4 className="text-base font-bold text-gray-900">Consumo y Gastos de Ingredientes</h4>
            <p className="text-xs text-gray-500 mt-0.5">
              Detalle de cada ingrediente utilizado en pedidos completados del período según recetas
            </p>
          </div>
          <input
            type="text"
            placeholder="Buscar ingrediente..."
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
          <>
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
                {paginatedItems.map((item) => (
                  <tr key={item.ingredient_id} className="hover:bg-gray-50/50 transition">
                    <td className="py-3 px-4 font-bold text-gray-900">{item.ingredient_name}</td>
                    <td className="py-3 px-4 text-gray-500">{item.unit}</td>
                    <td className="py-3 px-4 text-right font-medium text-gray-700">
                      {formatCurrency(item.unit_cost ?? 0)}
                    </td>
                    <td className="py-3 px-4 text-right font-semibold text-gray-900">
                      {formatQuantity(item.total_quantity, item.unit)}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-gray-900">
                      {formatCurrency(item.total_cost ?? item.total_quantity * (item.unit_cost ?? 0))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {filteredItems.length > PAGE_SIZE && (
            <div className="p-4 border-t border-gray-100 flex flex-col sm:flex-row items-center justify-between gap-3 bg-gray-50/50">
              <span className="text-xs text-gray-500 font-medium">
                Mostrando {(currentPage - 1) * PAGE_SIZE + 1} a {Math.min(currentPage * PAGE_SIZE, filteredItems.length)} de {filteredItems.length} insumos
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
                >
                  Anterior
                </button>
                <span className="text-xs font-bold text-gray-800 px-2">
                  {currentPage} de {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs font-semibold text-gray-700 hover:bg-gray-100 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
                >
                  Siguiente
                </button>
              </div>
            </div>
          )}
        </>
        )}
      </div>
    </div>
  );
}
