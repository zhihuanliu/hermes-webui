// EID iframe parent notification bridge for /chatbot embed mode.
function _eidTurnNotifyLog(level, message, details) {
  const logger = (window.console && window.console[level]) || (window.console && window.console.log);
  if (!logger) return;
  logger.call(window.console, `[Hermes EID bridge] ${message}`, details || '');
}

function notifyEidParentTurnCompleted(payload) {
  const ctx = window.__HERMES_CHATBOT_CONTEXT__ || {};
  if (!ctx.turnNotifyEnabled || !ctx.recordId) {
    _eidTurnNotifyLog('warn', 'skip turn-completed postMessage: notification disabled or record missing', {
      turnNotifyEnabled: !!ctx.turnNotifyEnabled,
      hasRecordId: !!ctx.recordId,
    });
    return;
  }
  const recordId = String((payload && payload.recordId) || '').trim();
  if (!recordId || recordId !== String(ctx.recordId || '').trim()) {
    _eidTurnNotifyLog('warn', 'skip turn-completed postMessage: record mismatch', {
      payloadRecordId: recordId,
      contextRecordId: String(ctx.recordId || '').trim(),
    });
    return;
  }
  if (window.parent === window) {
    _eidTurnNotifyLog('warn', 'skip turn-completed postMessage: not running inside iframe');
    return;
  }
  const targetOrigin = String(ctx.parentPostMessageOrigin || '').trim();
  if (!targetOrigin) {
    _eidTurnNotifyLog('warn', 'skip turn-completed postMessage: parent target origin missing');
    return;
  }
  const sessionId = String((payload && payload.sessionId) || '').trim();
  if (!sessionId) {
    _eidTurnNotifyLog('warn', 'skip turn-completed postMessage: session id missing');
    return;
  }
  const messageCount = Number(payload && payload.messageCount);
  const completedAt = Number(payload && payload.completedAt);
  const canvasUpdated = !!(payload && payload.canvasUpdated);
  const message = {
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
  };
  _eidTurnNotifyLog('info', 'post turn-completed message to parent', {
    targetOrigin,
    recordId,
    sessionId,
    canvasUpdated,
    refreshTargets: message.refresh_targets,
  });
  window.parent.postMessage(message, targetOrigin);
}
