import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StatsSection } from '@/components/StatsSection';
import * as statsService from '@/services/statsService';
import * as ingredientService from '@/services/ingredientService';
import type { PredictionsResponse, CopilotAnswerResponse, DashboardKPIsResponse } from '@/types/stats';
import type { IngredientConsumptionReport } from '@/types/ingredient';

vi.mock('@/services/statsService');
vi.mock('@/services/ingredientService');

const stats = vi.mocked(statsService);
const ingService = vi.mocked(ingredientService);

const MOCK_KPIS: DashboardKPIsResponse = {
  revenue: { current: 150000, previous: 120000, growth_pct: 25.0, trend: 'up', is_positive: true },
  orders_count: { current: 15, previous: 12, growth_pct: 25.0, trend: 'up', is_positive: true },
  completed_orders_count: 15,
  average_ticket: { current: 10000, previous: 10000, growth_pct: 0.0, trend: 'neutral', is_positive: true },
  cancellation_rate: { current: 6.25, previous: 14.28, growth_pct: -56.23, trend: 'down', is_positive: true },
  cogs: { current: 45000, previous: 40000, growth_pct: 12.5, trend: 'up', is_positive: false },
  gross_profit: { current: 105000, previous: 80000, growth_pct: 31.25, trend: 'up', is_positive: true },
  gross_margin_pct: 70.0,
  goal: {
    period_type: 'weekly',
    target_revenue: 200000,
    revenue_progress_pct: 75.0,
    revenue_remaining: 50000,
    target_orders: 20,
    orders_progress_pct: 80.0,
    orders_remaining: 4,
  },
  best_selling_day: { day: 'Viernes', revenue: 90000, growth_pct: 20.0, trend: 'up' },
  status_distribution: { Finalizado: 15, Cancelado: 1 },
  top_products: [],
};

const MOCK_PREDICTIONS: PredictionsResponse = {
  days: [
    { date: '2026-11-22', day_name: 'Domingo', is_weekend: true, projected_orders: 12, projected_revenue: 96000 },
    { date: '2026-11-23', day_name: 'Lunes', is_weekend: false, projected_orders: 5, projected_revenue: 40000 },
    { date: '2026-11-24', day_name: 'Martes', is_weekend: false, projected_orders: 6, projected_revenue: 48000 },
    { date: '2026-11-25', day_name: 'Miércoles', is_weekend: false, projected_orders: 6, projected_revenue: 48000 },
    { date: '2026-11-26', day_name: 'Jueves', is_weekend: false, projected_orders: 7, projected_revenue: 56000 },
    { date: '2026-11-27', day_name: 'Viernes', is_weekend: false, projected_orders: 10, projected_revenue: 80000 },
    { date: '2026-11-28', day_name: 'Sábado', is_weekend: true, projected_orders: 14, projected_revenue: 112000 },
  ],
  total_projected_orders: 60,
  total_projected_revenue: 480000,
  weekday_projected_orders: 34,
  weekday_projected_revenue: 272000,
  weekend_projected_orders: 26,
  weekend_projected_revenue: 208000,
  avg_daily_orders: 8.6,
  avg_daily_revenue: 68571.43,
  ingredient_demands: [
    {
      ingredient_id: 1,
      ingredient_name: 'Muzzarella Barra',
      unit: 'kg',
      projected_quantity: 18.5,
      unit_cost: 4000,
      estimated_cost: 74000,
      contributing_products: ['Pizza Muzzarella', 'Pizza Fugazzeta'],
    },
    {
      ingredient_id: 2,
      ingredient_name: 'Harina 000',
      unit: 'kg',
      projected_quantity: 22.0,
      unit_cost: 600,
      estimated_cost: 13200,
      contributing_products: ['Pizza Muzzarella'],
    },
  ],
  strategic_prescriptions: [
    'Reforzar personal de cocina y cadetes para sábado y domingo.',
    "Comprar 18.5 kg de 'Muzzarella Barra' antes del jueves.",
    'Revisar stock de materias primas no perecederas.',
  ],
  is_ai_generated: true,
  historical_weeks_analyzed: 8,
  generated_at: '2026-11-21T02:00:00Z',
};

const MOCK_CONSUMPTION: IngredientConsumptionReport = {
  completed_orders: 15,
  items: [
    {
      ingredient_id: 1,
      ingredient_name: 'Muzzarella Barra',
      unit: 'kg',
      total_quantity: 12.5,
      unit_cost: 4000,
      total_cost: 50000,
    },
    {
      ingredient_id: 2,
      ingredient_name: 'Tomate Triturado',
      unit: 'kg',
      total_quantity: 8.0,
      unit_cost: 1200,
      total_cost: 9600,
    },
  ],
  products_without_recipe: [],
};

const MOCK_COPILOT_RESPONSE: CopilotAnswerResponse = {
  answer: 'Los 3 insumos con mayor gasto acumulado este mes son Muzzarella Barra ($50.000) y Tomate Triturado ($9.600).',
  cited_period: 'Mes actual (01/11/2026 al 21/11/2026)',
  data_summary: {
    total_spent: 59600,
    items: [{ ingredient_name: 'Muzzarella Barra', total_spent: 50000 }],
  },
  suggested_followups: [
    '¿Qué insumos debería comprar antes del fin de semana?',
    '¿Qué día tuvimos más cancelaciones?',
  ],
  is_fallback: false,
  generated_at: '2026-11-21T02:00:00Z',
};

describe('US-67: Inteligencia de Negocio con Analítica Predictiva y Copilot Q&A Comercial', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    stats.fetchDashboardKPIs.mockResolvedValue(MOCK_KPIS);
    stats.fetchStatusDistribution.mockResolvedValue({ Finalizado: 15 });
    stats.fetchTopProducts.mockResolvedValue([]);
    stats.fetchBestSellingDay.mockResolvedValue({ best_selling_day: 'Viernes', total_revenue: 90000 });
    stats.fetchBusinessGoals.mockResolvedValue({ goals: [] });
    stats.fetchPredictions.mockResolvedValue(MOCK_PREDICTIONS);
    stats.askCopilot.mockResolvedValue(MOCK_COPILOT_RESPONSE);
    ingService.fetchIngredientConsumption.mockResolvedValue(MOCK_CONSUMPTION);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('organiza la información en las 3 vistas requeridas y permite navegar entre ellas', async () => {
    render(<StatsSection />);
    const user = userEvent.setup();

    // Vistas visibles en el encabezado
    expect(screen.getByRole('button', { name: /Rendimiento y Metas/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ingredientes y gastos/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Predicciones/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Asistente Q&A/i })).toBeInTheDocument();

    // 1. Pestaña inicial: Rendimiento y Metas
    expect(await screen.findByText('Seguimiento de Metas')).toBeInTheDocument();
    expect(screen.getByText('Ticket Promedio')).toBeInTheDocument();

    // 2. Navegar a Ingredientes y gastos
    const insumosTabBtn = screen.getByRole('button', { name: /Ingredientes y gastos/i });
    await user.click(insumosTabBtn);

    expect(await screen.findByText('Gasto Total Acumulado')).toBeInTheDocument();
    expect(screen.getByText('Ingrediente Mayor Gasto')).toBeInTheDocument();
    expect((await screen.findAllByText('Muzzarella Barra')).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Tomate Triturado')).toBeInTheDocument();
    expect(screen.getByText('Consejos de IA')).toBeInTheDocument();
    expect(screen.getByText('Consejos inteligentes para optimizar compras y materias primas')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Consejos con IA/i })).toBeInTheDocument();

    // 3. Navegar a Predicciones
    const prediccionesTabBtn = screen.getByRole('button', { name: /Predicciones/i });
    await user.click(prediccionesTabBtn);

    expect(await screen.findByRole('button', { name: /Actualizar pronóstico/i })).toBeInTheDocument();
    expect(screen.getByText('Total Próximos 7 Días')).toBeInTheDocument();
    expect(screen.getByText('Promedio Diario')).toBeInTheDocument();
    expect(screen.getByText('Día con Más Ventas')).toBeInTheDocument();
    expect(screen.getByText('Días de Semana')).toBeInTheDocument();
    expect(screen.getByText('Fin de Semana')).toBeInTheDocument();
    expect(screen.getByText('Demanda Proyectada de Insumos Principales')).toBeInTheDocument();
  });

  it('el panel lateral de Asistente Q&A se abre desde el botón y permite consultar datos ad-hoc', async () => {
    render(<StatsSection />);
    const user = userEvent.setup();

    // Botón de Asistente Q&A accesible
    const assistantBtn = screen.getByRole('button', { name: /Asistente Q&A/i });
    await user.click(assistantBtn);

    // Se abre el drawer
    expect(await screen.findByRole('heading', { name: 'Asistente Q&A' })).toBeInTheDocument();
    expect(screen.getByText('Consultas sobre datos reales del negocio en los últimos 30 días')).toBeInTheDocument();

    // Consulta enviada desde el input
    const input = screen.getByPlaceholderText(/Hacé una pregunta sobre tu negocio/i);
    await user.type(input, '¿Cuáles son los 3 insumos con más gasto este mes?');
    const sendBtn = screen.getByRole('button', { name: 'Enviar' });
    await user.click(sendBtn);

    await waitFor(() => {
      expect(stats.askCopilot).toHaveBeenCalledWith(
        '¿Cuáles son los 3 insumos con más gasto este mes?',
        expect.any(Array)
      );
    });

    // Muestra la respuesta fundamentada con cita de período
    expect(await screen.findByText(/Los 3 insumos con mayor gasto acumulado/i)).toBeInTheDocument();
    expect(screen.getByText(/Mes actual \(01\/11\/2026 al 21\/11\/2026\)/i)).toBeInTheDocument();

    // Permite cerrar el drawer
    const closeBtn = screen.getByRole('button', { name: 'Cerrar panel de Asistente' });
    await user.click(closeBtn);
    expect(screen.queryByRole('heading', { name: 'Asistente Q&A' })).not.toBeInTheDocument();
  });

  it('el Asistente permite hacer preguntas personalizadas y muestra estado de degradación controlada', async () => {
    stats.askCopilot.mockResolvedValueOnce({
      answer: 'En los últimos 30 días se registraron 2 cancelaciones.',
      cited_period: 'Últimos 30 días',
      is_fallback: true,
      suggested_followups: [],
      generated_at: '2026-11-21T02:00:00Z',
    });

    render(<StatsSection />);
    const user = userEvent.setup();

    const assistantBtn = screen.getByRole('button', { name: /Asistente Q&A/i });
    await user.click(assistantBtn);

    const input = screen.getByPlaceholderText(/Hacé una pregunta sobre tu negocio/i);
    await user.type(input, '¿Qué día tuvimos más cancelaciones?');

    const sendBtn = screen.getByRole('button', { name: 'Enviar' });
    await user.click(sendBtn);

    expect(await screen.findByText('En los últimos 30 días se registraron 2 cancelaciones.')).toBeInTheDocument();
    expect(screen.getByText('Modo directo')).toBeInTheDocument();
  });

  it('el Asistente muestra tarjeta de acción sugerida y permite ejecutarla o descartarla', async () => {
    stats.askCopilot.mockResolvedValueOnce({
      answer: 'Podrías considerar pausar Pizza Fugazzeta por baja rotación.',
      cited_period: 'Últimos 30 días',
      is_fallback: false,
      suggested_followups: [],
      suggested_action: {
        action_type: 'deactivate_product',
        title: 'Pausar Pizza Fugazzeta de la carta',
        description: 'Ocultar temporalmente del menú digital.',
        button_label: 'Pausar de la carta',
        payload: { product_id: 2, product_name: 'Pizza Fugazzeta' },
      },
      generated_at: '2026-11-21T02:00:00Z',
    });
    stats.executeCopilotAction.mockResolvedValueOnce({
      success: true,
      message: "El producto 'Pizza Fugazzeta' fue pausado correctamente.",
      executed_action: 'deactivate_product',
      affected_entity_id: 2,
    });

    render(<StatsSection />);
    const user = userEvent.setup();

    const assistantBtn = screen.getByRole('button', { name: /Asistente Q&A/i });
    await user.click(assistantBtn);

    const input = screen.getByPlaceholderText(/Hacé una pregunta sobre tu negocio/i);
    await user.type(input, 'qué producto eliminar?');

    const sendBtn = screen.getByRole('button', { name: 'Enviar' });
    await user.click(sendBtn);

    // Aparece la tarjeta de acción sugerida
    expect(await screen.findByText('Pausar Pizza Fugazzeta de la carta')).toBeInTheDocument();
    expect(screen.getByText('Ocultar temporalmente del menú digital.')).toBeInTheDocument();
    const actionBtn = screen.getByRole('button', { name: 'Pausar de la carta' });
    const discardBtn = screen.getByRole('button', { name: 'Descartar' });
    expect(actionBtn).toBeInTheDocument();
    expect(discardBtn).toBeInTheDocument();

    // Ejecutar acción
    await user.click(actionBtn);
    await waitFor(() => {
      expect(stats.executeCopilotAction).toHaveBeenCalledWith('deactivate_product', {
        product_id: 2,
        product_name: 'Pizza Fugazzeta',
      });
    });

    // Muestra confirmación de ejecución
    expect(await screen.findByText(/El producto 'Pizza Fugazzeta' fue pausado correctamente/i)).toBeInTheDocument();
  });

  it('el Asistente permite descartar una acción sugerida', async () => {
    stats.askCopilot.mockResolvedValueOnce({
      answer: 'Te recomiendo crear una promo.',
      cited_period: 'Últimos 30 días',
      is_fallback: false,
      suggested_followups: [],
      suggested_action: {
        action_type: 'create_promotion',
        title: 'Crear Promo Fin de Semana',
        description: 'Combo especial con 15% de descuento.',
        button_label: 'Crear promoción',
        payload: { name: 'Promo Fin de Semana', price: 15000 },
      },
      generated_at: '2026-11-21T02:00:00Z',
    });

    render(<StatsSection />);
    const user = userEvent.setup();

    const assistantBtn = screen.getByRole('button', { name: /Asistente Q&A/i });
    await user.click(assistantBtn);

    const input = screen.getByPlaceholderText(/Hacé una pregunta sobre tu negocio/i);
    await user.type(input, 'qué promo armar?');

    const sendBtn = screen.getByRole('button', { name: 'Enviar' });
    await user.click(sendBtn);

    expect(await screen.findByText('Crear Promo Fin de Semana')).toBeInTheDocument();
    const discardBtn = screen.getByRole('button', { name: 'Descartar' });
    await user.click(discardBtn);

    expect(await screen.findByText('Acción descartada')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Crear promoción' })).not.toBeInTheDocument();
  });

  it('la sección predictiva muestra degradación controlada y opción de reintentar si el servicio falla', async () => {
    stats.fetchPredictions.mockRejectedValueOnce(new Error('Falla de red o timeout'));

    render(<StatsSection />);
    const user = userEvent.setup();

    const prediccionesTabBtn = screen.getByRole('button', { name: /Predicciones/i });
    await user.click(prediccionesTabBtn);

    expect(await screen.findByText(/No se pudieron calcular las predicciones/i)).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: /Reintentar predicción/i });
    expect(retryBtn).toBeInTheDocument();

    // Reintento exitoso
    stats.fetchPredictions.mockResolvedValueOnce(MOCK_PREDICTIONS);
    await user.click(retryBtn);

    expect(await screen.findByText('Total Próximos 7 Días')).toBeInTheDocument();
    expect(screen.getByText('Muzzarella Barra')).toBeInTheDocument();
  });

  it('las tablas de insumos y recetas y predicciones paginan de a 6 ingredientes', async () => {
    // Mock con 8 insumos en consumo
    const manyIngredients = Array.from({ length: 8 }, (_, i) => ({
      ingredient_id: i + 1,
      ingredient_name: `Ingrediente ${i + 1}`,
      unit: 'kg',
      total_quantity: 10 + i,
      unit_cost: 100,
      total_cost: (10 + i) * 100,
    }));

    ingService.fetchIngredientConsumption.mockResolvedValueOnce({
      completed_orders: 15,
      items: manyIngredients,
      products_without_recipe: [],
    });

    render(<StatsSection />);
    const user = userEvent.setup();

    // Navegar a Ingredientes y gastos
    const insumosTabBtn = screen.getByRole('button', { name: /Ingredientes y gastos/i });
    await user.click(insumosTabBtn);

    expect((await screen.findAllByText('Ingrediente 1')).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('cell', { name: 'Ingrediente 6' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'Ingrediente 7' })).not.toBeInTheDocument();
    expect(screen.getByText('Mostrando 1 a 6 de 8 insumos')).toBeInTheDocument();

    // Siguiente página
    const nextBtn = screen.getByRole('button', { name: 'Siguiente' });
    await user.click(nextBtn);

    expect(await screen.findByRole('cell', { name: 'Ingrediente 7' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'Ingrediente 8' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'Ingrediente 1' })).not.toBeInTheDocument();
  });
});
