import { useEffect, useRef, useState } from 'react';
import { askCopilot } from '@/services/statsService';
import type { CopilotChatMessage } from '@/types/stats';
import { SparklesIcon } from '@/components/Icons';

interface CopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

const QUICK_QUESTIONS = [
  '¿Cuáles son los 3 insumos con más gasto este mes?',
  '¿Qué día tuvimos más cancelaciones?',
  '¿Qué insumos debería comprar antes del fin de semana?',
  '¿Cuánto facturamos la última semana?',
  '¿Cuáles son los platos más rentables?',
  '¿Cómo viene el cumplimiento de metas?',
];

export function CopilotDrawer({ isOpen, onClose }: CopilotDrawerProps) {
  const [messages, setMessages] = useState<CopilotChatMessage[]>([
    {
      role: 'assistant',
      content:
        '¡Hola! Soy tu Copilot Comercial gastronómico. Podés consultarme sobre ventas, facturación, ingredientes con mayor gasto, días con cancelaciones o proyecciones de compras. Mis respuestas se basan directamente en los datos reales del negocio.',
      suggested_followups: [
        '¿Cuáles son los 3 insumos con más gasto este mes?',
        '¿Qué día tuvimos más cancelaciones?',
        '¿Qué insumos debería comprar antes del fin de semana?',
      ],
    },
  ]);
  const [inputQuestion, setInputQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, loading]);

  if (!isOpen) return null;

  const handleSend = async (questionToSend?: string) => {
    const q = (questionToSend || inputQuestion).trim();
    if (!q || loading) return;

    setInputQuestion('');
    setError(null);

    const userMsg: CopilotChatMessage = { role: 'user', content: q };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);

    try {
      const historyPayload = messages.map((m) => ({ role: m.role, content: m.content }));
      const response = await askCopilot(q, historyPayload);

      const assistantMsg: CopilotChatMessage = {
        role: 'assistant',
        content: response.answer,
        cited_period: response.cited_period,
        data_summary: response.data_summary ?? undefined,
        suggested_followups: response.suggested_followups,
        is_fallback: response.is_fallback,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      setError('El asistente no pudo procesar tu consulta en este momento. Podés reintentar.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/40 backdrop-blur-xs transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer Container */}
      <div className="relative w-full max-w-md bg-white shadow-2xl flex flex-col h-full z-10 animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-4 border-b border-gray-100 flex items-center justify-between bg-gray-50/75">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-black text-white">
              <SparklesIcon className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-gray-900">Copilot Q&A Comercial</h3>
              <p className="text-[11px] text-gray-500">Consultas ad-hoc sobre datos reales del negocio</p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar panel de Copilot"
            className="rounded-lg p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-200/60 transition"
          >
            ✕
          </button>
        </div>

        {/* Botones de Acceso Rápido / Preguntas Frecuentes */}
        <div className="px-4 py-3 border-b border-gray-100 bg-white">
          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block mb-2">
            Preguntas frecuentes sugeridas
          </span>
          <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto pr-1">
            {QUICK_QUESTIONS.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => handleSend(q)}
                disabled={loading}
                className="text-[11px] font-medium bg-gray-100 hover:bg-gray-200 text-gray-800 rounded-lg px-2.5 py-1 text-left transition disabled:opacity-50"
              >
                {q}
              </button>
            ))}
          </div>
        </div>

        {/* Historial de Mensajes */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50/40">
          {messages.map((msg, index) => (
            <div
              key={index}
              className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              <div
                className={`max-w-[90%] rounded-2xl px-4 py-3 text-xs leading-relaxed ${
                  msg.role === 'user'
                    ? 'bg-black text-white rounded-br-none font-medium'
                    : 'bg-white text-gray-800 border border-gray-200/80 shadow-xs rounded-bl-none space-y-2'
                }`}
              >
                {/* Contenido en markdown simple */}
                <div className="whitespace-pre-wrap">{msg.content}</div>

                {/* Período citado */}
                {msg.cited_period && (
                  <div className="pt-1.5 border-t border-gray-100 flex items-center justify-between text-[10px] text-gray-500 font-medium">
                    <span className="bg-gray-100 px-2 py-0.5 rounded-full text-gray-700">
                      📅 {msg.cited_period}
                    </span>
                    {msg.is_fallback && (
                      <span className="text-amber-600 font-semibold" title="Degradación controlada por alta demanda">
                        Modo directo
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Sugerencias de seguimiento después de respuesta */}
              {msg.role === 'assistant' && msg.suggested_followups && msg.suggested_followups.length > 0 && (
                <div className="mt-2 flex flex-col gap-1 w-full pl-2">
                  <span className="text-[10px] text-gray-400 font-bold uppercase">Preguntas relacionadas:</span>
                  <div className="flex flex-wrap gap-1.5">
                    {msg.suggested_followups.map((followup, fIdx) => (
                      <button
                        key={fIdx}
                        type="button"
                        onClick={() => handleSend(followup)}
                        disabled={loading}
                        className="text-[11px] font-medium bg-white hover:bg-gray-100 text-gray-700 border border-gray-200 rounded-lg px-2 py-0.5 transition text-left disabled:opacity-50"
                      >
                        {followup}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 p-3 bg-white border border-gray-200 rounded-2xl w-fit shadow-xs">
              <div className="animate-spin h-3.5 w-3.5 border-2 border-black border-t-transparent rounded-full" />
              <span className="text-xs text-gray-600 font-medium">Consultando datos del negocio...</span>
            </div>
          )}

          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex justify-between items-center">
              <span>{error}</span>
              <button
                type="button"
                onClick={() => handleSend()}
                className="underline font-bold text-red-800 ml-2"
              >
                Reintentar
              </button>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Footer */}
        <div className="p-3 border-t border-gray-100 bg-white">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex items-center gap-2"
          >
            <input
              ref={inputRef}
              type="text"
              value={inputQuestion}
              onChange={(e) => setInputQuestion(e.target.value)}
              placeholder="Hacé una pregunta sobre tu negocio..."
              disabled={loading}
              className="flex-1 rounded-xl border border-gray-300 px-3.5 py-2 text-xs focus:outline-none focus:ring-2 focus:ring-black disabled:bg-gray-100"
            />
            <button
              type="submit"
              disabled={loading || !inputQuestion.trim()}
              className="rounded-xl bg-black text-white px-3.5 py-2 text-xs font-bold hover:bg-gray-800 transition disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center shrink-0"
            >
              Enviar
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
