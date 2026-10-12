export type ApiConnection = 'backend' | 'mock';
export type ApiMethod = 'GET' | 'POST' | 'PATCH';
export type ApiOrigin = 'openapi' | 'design';

export interface ApiEndpoint {
  id: string;
  method: ApiMethod;
  path: string;
  group: string;
  section?: string;
  summary: string;
  connection: ApiConnection;
  origin?: ApiOrigin;
  responseStatus: number;
  response: unknown;
}

export interface ApiSection {
  key: string;
  label: string;
  endpoints: readonly ApiEndpoint[];
}

export interface ApiNavigationGroup {
  key: string;
  label: string;
  sections: readonly ApiSection[];
}
