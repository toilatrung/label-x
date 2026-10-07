import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  ApiRequestError, ERROR_MESSAGES, FALLBACK_ERROR_MESSAGE, NETWORK_ERROR_MESSAGE,
  SERVER_ERROR_MESSAGE, apiErrorMessage, errorMessage,
} from '@/lib/api/errors';

// npm pretest regenerates this file from openapi.yaml. Never duplicate the enum here.
const contract = readFileSync(path.resolve(import.meta.dirname, '../lib/api/contract.d.ts'), 'utf8');
const union = contract.match(/\bErrorCode:\s*([^;]+);/)?.[1];
const contractCodes = [...(union?.matchAll(/"([^"]+)"/g) ?? [])].map((match) => match[1]);

describe('T-010 error messages from the generated contract', () => {
  it('maps exactly every contract code', () => {
    expect(contractCodes.length).toBeGreaterThan(0);
    expect(Object.keys(ERROR_MESSAGES).sort()).toEqual([...contractCodes].sort());
  });

  it.each(contractCodes)('provides a Vietnamese message for %s', (code) => {
    const message = apiErrorMessage(400, code);
    expect(message).not.toBe(FALLBACK_ERROR_MESSAGE);
    expect(message.trim().length).toBeGreaterThan(0);
    expect(message).toMatch(/[À-ỹ]/u);
    expect(message).not.toContain(code);
  });
});

describe('Error response fallbacks and trace identifiers', () => {
  it.each([400, 401, 403, 404, 409, 422])('has a readable fallback at HTTP %s', (status) => {
    expect(apiErrorMessage(status)).not.toBe(FALLBACK_ERROR_MESSAGE);
    expect(apiErrorMessage(status, 'FUTURE_CODE')).toBe(apiErrorMessage(status));
  });

  it.each(['FUTURE_CODE', 'toString', '__proto__', 'constructor'])('safely handles unknown code %s', (code) => {
    expect(apiErrorMessage(418, code)).toBe(FALLBACK_ERROR_MESSAGE);
  });

  it.each([500, 502, 503, 599])('shows the request identifier for HTTP %s', (status) => {
    const error = new ApiRequestError(status, {
      code: 'VALIDATION_ERROR', message: 'Internal database credentials', request_id: ' body-id ',
    });
    expect(error.message).toBe(`${SERVER_ERROR_MESSAGE} Mã yêu cầu: body-id`);
    expect(error.message).not.toContain('credentials');
    expect(error.requestId).toBe('body-id');
  });

  it.each([undefined, null, '<html>Error</html>', [], { request_id: 12 }, { request_id: '  ' }])
    ('takes a trace identifier from the header with an invalid body %j', (body) => {
      const error = new ApiRequestError(502, body, new Headers({ 'X-Request-ID': 'header-id' }));
      expect(error.message).toBe(`${SERVER_ERROR_MESSAGE} Mã yêu cầu: header-id`);
    });

  it('still shows a safe server message when there is no trace identifier', () => {
    expect(new ApiRequestError(500).message).toBe(SERVER_ERROR_MESSAGE);
  });

  it('uses the code rather than raw API text and retains structured field details', () => {
    const fields = { fields: { username: ['required'] } };
    const error = new ApiRequestError(400, { code: 'VALIDATION_ERROR', message: 'raw diagnostics', details: fields });
    expect(error.message).toBe(ERROR_MESSAGES.VALIDATION_ERROR);
    expect(error.detail?.details).toEqual(fields);
  });

  it('only displays request identifiers for server failures', () => {
    expect(new ApiRequestError(403, { code: 'OUT_OF_SCOPE', request_id: 'private-id' }).message)
      .toBe(ERROR_MESSAGES.OUT_OF_SCOPE);
  });

  it('handles transport failures consistently without exposing exception diagnostics', () => {
    expect(errorMessage(new TypeError('failed transport details'))).toBe(NETWORK_ERROR_MESSAGE);
    expect(errorMessage(null)).toBe(NETWORK_ERROR_MESSAGE);
    expect(errorMessage(new ApiRequestError(409, { code: 'SCOPE_BUSY' }))).toBe(ERROR_MESSAGES.SCOPE_BUSY);
  });
});
