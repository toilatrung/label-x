import type { ApiEndpoint } from './types';
import { API_NAVIGATION } from './features';

export type { ApiConnection, ApiEndpoint, ApiMethod, ApiNavigationGroup, ApiOrigin, ApiSection } from './types';
export { API_FEATURES, API_NAVIGATION } from './features';

/**
 * Contract inventory from docs/04-api/openapi.yaml, split by product feature.
 * `backend` means a Django URL and matching HTTP handler exist on develop-fe.
 * `mock` means the operation is contract-only; its example is intentionally marked as mock data.
 */
export const API_ENDPOINTS: ApiEndpoint[] = API_NAVIGATION.flatMap(group =>
  group.sections.flatMap(currentSection =>
    currentSection.endpoints.map(endpoint => ({
      ...endpoint,
      group: group.label,
      section: currentSection.label,
    })),
  ),
);
