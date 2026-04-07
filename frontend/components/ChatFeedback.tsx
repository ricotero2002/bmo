import React, { useState } from 'react';
import { sendFeedback } from '../services/api';

interface ChatFeedbackProps {
  threadId: string;
  messageId?: string;
  userPrompt?: string;
  aiResponse?: string;
  toolsUsed?: any;
}

export default function ChatFeedback({
  threadId,
  messageId,
  userPrompt,
  aiResponse,
  toolsUsed,
}: ChatFeedbackProps) {
  const [submitted, setSubmitted] = useState<number | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [correction, setCorrection] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleVote = async (score: number) => {
    // If it's a thumbs down, just open the modal first, unless we want to submit -1 right away
    if (score === -1) {
      setShowModal(true);
      return;
    }
    
    // Thumbs up logic
    try {
      setIsSubmitting(true);
      await sendFeedback(threadId, score, messageId, userPrompt, aiResponse, toolsUsed);
      setSubmitted(score);
    } catch (error) {
      console.error(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCorrectionSubmit = async () => {
    try {
      setIsSubmitting(true);
      await sendFeedback(threadId, -1, messageId, userPrompt, aiResponse, toolsUsed, correction);
      setSubmitted(-1);
      setShowModal(false);
    } catch (error) {
      console.error(error);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (submitted !== null) {
    return (
      <div className="text-xs text-gray-500 mt-2 flex items-center gap-1 opacity-70">
        <span>{submitted === 1 ? '👍 Gracias por tu feedback' : '👎 Feedback registrado'}</span>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-2 mt-2 opacity-50 hover:opacity-100 transition-opacity">
        <button 
          onClick={() => handleVote(1)}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors text-xs"
          disabled={isSubmitting}
          title="Buena respuesta"
        >
          👍
        </button>
        <button 
          onClick={() => handleVote(-1)}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors text-xs"
          disabled={isSubmitting}
          title="Mala respuesta o le falta acción"
        >
          👎
        </button>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg p-5 w-full max-w-md shadow-xl border border-gray-200 dark:border-gray-700">
            <h3 className="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">¡Ups! ¿Cómo debería haber respondido BMO?</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              ¿Faltó realizar alguna acción? ¿La información era incorrecta? Tu corrección nos ayudará a mejorar el modelo.
            </p>
            <textarea
              className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded-md p-3 text-sm min-h-[100px] mb-4 text-gray-900 dark:text-gray-100"
              placeholder="Ej: Deberías haber buscado en internet en lugar de usar mis notas locales..."
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
              disabled={isSubmitting}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700 rounded-md transition-colors"
                disabled={isSubmitting}
              >
                Cancelar
              </button>
              <button
                onClick={handleCorrectionSubmit}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50"
                disabled={isSubmitting || !correction.trim()}
              >
                {isSubmitting ? 'Enviando...' : 'Enviar Feedback'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
