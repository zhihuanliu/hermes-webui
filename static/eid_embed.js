// EID iframe parent notification bridge for /chatbot embed mode.
function notifyEidParentTurnCompleted(payload) {
  const ctx = window.__HERMES_CHATBOT_CONTEXT__ || {};
  if (!ctx.turnNotifyEnabled || !ctx.recordId) return;
  const recordId = String((payload && payload.recordId) || '').trim();
  if (!recordId || recordId !== String(ctx.recordId || '').trim()) return;
  if (window.parent === window) return;
  const targetOrigin = String(ctx.parentPostMessageOrigin || '').trim();
  if (!targetOrigin) return;
  const sessionId = String((payload && payload.sessionId) || '').trim();
  if (!sessionId) return;
  const messageCount = Number(payload && payload.messageCount);
  const completedAt = Number(payload && payload.completedAt);
  const canvasUpdated = !!(payload && payload.canvasUpdated);
  window.parent.postMessage({
    type: 'hermes.chat.turn.completed',
    version: 1,
    record_id: recordId,
    session_id: sessionId,
    message_count: Number.isFinite(messageCount) ? messageCount : 0,
    completed_at: Number.isFinite(completedAt) ? completedAt : (Date.now() / 1000),
    effects: {
      canvas_updated: canvasUpdated,
    },
    refresh_targets: canvasUpdated ? ['canvas'] : [],
  }, targetOrigin);
}
