import { useCallback, useMemo, useState } from 'react';
import { useStats } from '@/hooks/useStats';
import type { DateRangePreset } from '@/utils/dateRange';
import { parseDateInputValue, presetLabel, rangeForPreset } from '@/utils/dateRange';
import { PanelNote } from '@/components/ui/PanelNote';
import { BusinessGoalsModal } from '@/components/BusinessGoalsModal';
import { StrategicInsightModal } from '@/components/StrategicInsightModal';
import { fetchStrategicInsight } from '@/services/statsService';
import type { StrategicInsightResponse } from '@/types/stats';
import { RefreshIcon, SparklesIcon } from '@/components/Icons';

import { AiAdviceSection } from '@/components/stats/AiAdviceSection';
import { GoalsProgress } from '@/components/stats/GoalsProgress';
import { KpiCards } from '@/components/stats/KpiCards';
import { TopProductsTable } from '@/components/stats/TopProductsTable';
import { InsumosRecetasTab } from '@/components/stats/InsumosRecetasTab';
import { PredictiveAnalyticsTab } from '@/components/stats/PredictiveAnalyticsTab';
import { CopilotDrawer } from '@/components/stats/CopilotDrawer';

const PRESETS: DateRangePreset[] = ['today', 'week', 'month', 'all', 'custom'];

type AnalyticsTab = 'rendimiento' | 'insumos' | 'pronosticos';

export function StatsSection() {
  const [activeTab, setActiveTab] = useState<AnalyticsTab>('rendimiento');
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [predictionsRefreshKey, setPredictionsRefreshKey] = useState(0);

  const [preset, setPreset] = useState<DateRangePreset>('month');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');

  const [goalsModalOpen, setGoalsModalOpen] = useState(false);
  const [insightModalOpen, setInsightModalOpen] = useState(false);

  const [aiData, setAiData] = useState<StrategicInsightResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const range = useMemo(
    () =>
      rangeForPreset(preset, {
        from: customFrom ? parseDateInputValue(customFrom) : undefined,
        to: customTo ? parseDateInputValue(customTo) : undefined,
      }),
    [preset, customFrom, customTo]
  );

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

  const { statusDistribution, topProducts, bestDay, kpis, loading, error, reload } = useStats({
    dateFrom: range.from,
    dateTo: range.to,
  });

  const hasActivity = kpis
    ? kpis.orders_count.current > 0 || kpis.completed_orders_count > 0 || kpis.revenue.current > 0
    : true;

  return (
    <div className="flex flex-col gap-6 lg:h-full pb-28">
      {/* Barra superior con encabezado, pestañas y botón del Asistente */}
      <div className="shrink-0 flex flex-col gap-4 bg-white rounded-2xl shadow-md p-6 border border-gray-100">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-bold text-gray-900">Estadísticas</h3>
            <p className="text-xs text-gray-500 mt-0.5">
              Panel de Rendimiento y Ventas
            </p>
          </div>
        </div>

        {/* Selector de Vistas / Pestañas de Analítica */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-gray-100">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab('rendimiento')}
              className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                activeTab === 'rendimiento'
                  ? 'bg-black text-white shadow-xs'
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
              }`}
            >
              Rendimiento y Metas
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('insumos')}
              className={`rounded-xl px-3.5 py-2 text-xs font-bold transition ${
                activeTab === 'insumos'
                  ? 'bg-black text-white shadow-xs'
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-700'
              }`}
            >
              Ingredientes y gastos
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('pronosticos')}
              className={`rounded-xl px-3.5 py-2 text-xs font-bold transition flex items-center gap-1.5 cursor-pointer ${
                activeTab === 'pronosticos'
                  ? 'bg-violet-700 text-white shadow-xs'
                  : 'bg-violet-50 hover:bg-violet-100 text-violet-900 border border-violet-200/60'
              }`}
            >
              <SparklesIcon
                className={`w-3.5 h-3.5 ${activeTab === 'pronosticos' ? 'text-violet-200' : 'text-violet-600'}`}
              />
              <span>Predicciones</span>
            </button>
            <button
              type="button"
              onClick={() => setCopilotOpen(true)}
              className="rounded-xl px-3.5 py-2 text-xs font-bold transition flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-900 border border-emerald-200/60 cursor-pointer"
            >
              <SparklesIcon className="w-3.5 h-3.5 text-emerald-600" />
              <span>Asistente Q&A</span>
            </button>
          </div>

          {/* Filtros de fecha para las pestañas de Rendimiento e Insumos */}
          {(activeTab === 'rendimiento' || activeTab === 'insumos') && (
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
          )}

          {/* Botón de actualizar pronóstico a la derecha en la fila de pestañas */}
          {activeTab === 'pronosticos' && (
            <button
              type="button"
              onClick={() => setPredictionsRefreshKey((k) => k + 1)}
              className="rounded-xl border border-gray-300 hover:bg-gray-50 bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 transition shadow-2xs cursor-pointer flex items-center gap-1.5"
            >
              <RefreshIcon className="w-3.5 h-3.5 text-gray-500" />
              <span>Actualizar pronóstico</span>
            </button>
          )}
        </div>
      </div>

      {(activeTab === 'rendimiento' || activeTab === 'insumos') && preset === 'custom' && (
        <div className="shrink-0 flex items-center gap-2 bg-white p-4 rounded-2xl shadow-md border border-gray-100">
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

      {/* Contenido según pestaña activa */}
      {activeTab === 'rendimiento' && (
        <>
          {loading ? (
            <PanelNote>Cargando métricas y estadísticas...</PanelNote>
          ) : error ? (
            <div className="shrink-0 rounded-xl bg-red-50 text-red-700 px-4 py-3 text-sm">{error}</div>
          ) : (
            <div className="flex flex-col gap-6 lg:flex-1 lg:min-h-0 pb-16">
              <AiAdviceSection
                aiData={aiData}
                aiLoading={aiLoading}
                aiError={aiError}
                handleRequestAi={handleRequestAi}
                hasActivity={hasActivity}
              />
              <GoalsProgress kpis={kpis} setGoalsModalOpen={setGoalsModalOpen} />
              <KpiCards kpis={kpis} bestDay={bestDay} statusDistribution={statusDistribution} />
              <TopProductsTable kpis={kpis} topProducts={topProducts} />
              <div className="h-10 shrink-0" aria-hidden="true" />
            </div>
          )}
        </>
      )}

      {activeTab === 'insumos' && <InsumosRecetasTab range={range} />}

      {activeTab === 'pronosticos' && <PredictiveAnalyticsTab refreshKey={predictionsRefreshKey} />}

      {/* Drawer del Copilot Q&A Comercial (accesible desde todas las pestañas) */}
      <CopilotDrawer isOpen={copilotOpen} onClose={() => setCopilotOpen(false)} />

      {/* Modales existentes */}
      <BusinessGoalsModal
        isOpen={goalsModalOpen}
        onClose={() => setGoalsModalOpen(false)}
        onSaved={reload}
      />

      <StrategicInsightModal
        isOpen={insightModalOpen}
        onClose={() => setInsightModalOpen(false)}
        params={{ dateFrom: range.from, dateTo: range.to }}
      />
    </div>
  );
}
