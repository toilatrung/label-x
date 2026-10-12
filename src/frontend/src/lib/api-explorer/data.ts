import { API_ENDPOINTS } from './catalog';

export type JsonObject = Record<string, unknown>;

export function apiEndpoint(id: string) {
  const endpoint = API_ENDPOINTS.find(item => item.id === id);
  if (!endpoint) throw new Error(`Thiếu API Explorer endpoint: ${id}`);
  return endpoint;
}

export function apiObject(value: unknown): JsonObject {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as JsonObject : {};
}

export function apiArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function apiExample(id: string, label?: string): unknown {
  const endpoint = apiEndpoint(id);
  if (!endpoint.responseExamples?.length) return endpoint.response;
  if (label === undefined) return endpoint.responseExamples[0].response;
  return endpoint.responseExamples.find(example => example.label === label)?.response ?? endpoint.response;
}
