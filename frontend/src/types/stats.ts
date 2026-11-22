export interface TopProduct {
  product_name: string;
  total_quantity: number;
  total_revenue: number;
}

export interface BestSellingDayResponse {
  best_selling_day: string | null;
  total_revenue: number | null;
}

export interface StatsParams {
  dateFrom?: Date;
  dateTo?: Date;
}

export interface GrowthMetric {
  current: number;
  previous: number;
  growth_pct: number | null;
  trend: 'up' | 'down' | 'neutral';
  is_positive: boolean;
}

export interface GoalProgress {
  period_type: string;
  target_revenue: number;
  revenue_progress_pct: number;
  revenue_remaining: number;
  target_orders: number;
  orders_progress_pct: number;
  orders_remaining: number;
}

export interface TopProductKpi {
  product_name: string;
  total_quantity: number;
  total_revenue: number;
  estimated_cost: number;
  gross_profit: number;
  margin_pct: number;
  quantity_growth_pct?: number | null;
  revenue_growth_pct?: number | null;
}

export interface TopPromotionKpi {
  promotion_name: string;
  total_quantity: number;
  total_revenue: number;
}

export interface DashboardKPIsResponse {
  revenue: GrowthMetric;
  orders_count: GrowthMetric;
  completed_orders_count: number;
  average_ticket: GrowthMetric;
  cancellation_rate: GrowthMetric;
  cogs: GrowthMetric;
  gross_profit: GrowthMetric;
  gross_margin_pct: number;
  goal: GoalProgress | null;
  best_selling_day: {
    day: string | null;
    revenue: number | null;
    growth_pct: number | null;
    trend: string;
  };
  status_distribution: Record<string, number>;
  top_products: TopProductKpi[];
  top_promotions?: TopPromotionKpi[];
}

export interface BusinessGoalItem {
  period_type: string;
  target_revenue: number;
  target_orders: number;
  updated_at?: string | null;
}

export interface BusinessGoalsResponse {
  goals: BusinessGoalItem[];
}

export interface UpdateBusinessGoalsPayload {
  goals: BusinessGoalItem[];
}

export interface OperationalMetricsContext {
  avg_wait_minutes: number;
  max_wait_minutes: number;
  high_wait_count: number;
  high_wait_pct: number;
  peak_hour: number | null;
  peak_hour_orders: number;
  delivery_pct: number;
  pickup_pct: number;
}

export interface StrategicInsightResponse {
  summary: string;
  highlights: string[];
  warnings: string[];
  operational_weaknesses?: string[];
  recommendations: string[];
  spending_recommendations?: string[];
  operational_metrics?: OperationalMetricsContext | null;
  generated_at: string;
}

export interface DayProjectionItem {
  date: string;
  day_name: string;
  is_weekend: boolean;
  projected_orders: number;
  projected_revenue: number;
}

export interface IngredientDemandItem {
  ingredient_id: number;
  ingredient_name: string;
  unit: string;
  projected_quantity: number;
  unit_cost: number;
  estimated_cost: number;
  contributing_products: string[];
}

export interface PredictionsResponse {
  days: DayProjectionItem[];
  total_projected_orders: number;
  total_projected_revenue: number;
  weekday_projected_orders: number;
  weekday_projected_revenue: number;
  weekend_projected_orders: number;
  weekend_projected_revenue: number;
  avg_daily_orders: number;
  avg_daily_revenue: number;
  ingredient_demands: IngredientDemandItem[];
  strategic_prescriptions: string[];
  is_ai_generated: boolean;
  historical_weeks_analyzed: number;
  disclaimer?: string | null;
  generated_at: string;
}

export interface CopilotSuggestedAction {
  action_type: string;
  title: string;
  description: string;
  button_label: string;
  payload: Record<string, unknown>;
}

export interface CopilotActionExecutionResponse {
  success: boolean;
  message: string;
  executed_action: string;
  affected_entity_id?: number | null;
}

export interface CopilotChatMessage {
  role: 'user' | 'assistant';
  content: string;
  cited_period?: string;
  data_summary?: Record<string, unknown>;
  suggested_followups?: string[];
  suggested_action?: CopilotSuggestedAction | null;
  action_status?: 'idle' | 'executing' | 'executed' | 'discarded';
  action_result_message?: string;
  is_fallback?: boolean;
}

export interface CopilotAnswerResponse {
  answer: string;
  cited_period: string;
  data_summary?: Record<string, unknown> | null;
  suggested_followups?: string[];
  suggested_action?: CopilotSuggestedAction | null;
  is_fallback: boolean;
  generated_at: string;
}

