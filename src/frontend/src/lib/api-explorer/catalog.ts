import type { ApiEndpoint } from './types';
import { API_NAVIGATION } from './features';
import { STATUS_RESPONSE_EXAMPLES } from './status-examples';

export type { ApiConnection, ApiEndpoint, ApiMethod, ApiNavigationGroup, ApiOrigin, ApiResponseExample, ApiSection } from './types';
export { API_FEATURES, API_NAVIGATION } from './features';

/**
 * Contract inventory from docs/04-api/openapi.yaml, split by product feature.
 * `backend` identifies runtime endpoints; `mock` identifies contract examples supplied by PR #252.
 */
export const API_ENDPOINTS: ApiEndpoint[] = API_NAVIGATION.flatMap(group =>
  group.sections.flatMap(currentSection =>
    currentSection.endpoints.map(endpoint => ({
      ...endpoint,
      group: group.label,
      section: currentSection.label,
      responseExamples: STATUS_RESPONSE_EXAMPLES[endpoint.id],
    })),
  ),
);
