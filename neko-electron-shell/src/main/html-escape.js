'use strict';

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function safeScriptJson(value) {
  // JSON.stringify returns undefined for undefined / function / symbol values,
  // which would crash the .replace() chain. Coerce to 'null' so callers that
  // accidentally pass an unstringifiable value still emit valid script JSON.
  const json = JSON.stringify(value);
  if (typeof json !== 'string') return 'null';
  return json
    .replace(/</g, '\\u003C')
    .replace(/>/g, '\\u003E')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

module.exports = { escapeHtml, safeScriptJson };
