import { afterEach, vi, expect } from 'vitest';
import { cleanup } from '@testing-library/react';

declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface Assertion<R extends void | Promise<void> = void, T = unknown> {
    toBeInTheDocument(): R;
    toBeDisabled(): R;
    toHaveAttribute(attr: string, value?: string): R;
  }
  interface AsymmetricMatchersContaining {
    toBeInTheDocument(): void;
    toBeDisabled(): void;
    toHaveAttribute(attr: string, value?: string): void;
  }
}

expect.extend({
  toBeInTheDocument(received: Element | null) {
    const pass = received !== null && (received.ownerDocument?.body.contains(received) ?? false);
    return {
      pass,
      message: () =>
        pass
          ? 'expected element not to be in document'
          : 'expected element to be in document',
    };
  },
  toBeDisabled(received: Element | null) {
    const pass =
      received !== null &&
      ('disabled' in received
        ? Boolean((received as { disabled: boolean }).disabled)
        : received.hasAttribute('disabled') || received.getAttribute('aria-disabled') === 'true');
    return {
      pass,
      message: () =>
        pass ? 'expected element not to be disabled' : 'expected element to be disabled',
    };
  },
  toHaveAttribute(received: Element | null, attr: string, expectedValue?: string) {
    if (!received) {
      return {
        pass: false,
        message: () => `expected element to have attribute ${attr}, but element was null`,
      };
    }
    const hasAttr = received.hasAttribute(attr);
    const actualValue = received.getAttribute(attr);
    const pass = expectedValue !== undefined ? hasAttr && actualValue === expectedValue : hasAttr;
    return {
      pass,
      message: () =>
        pass
          ? `expected element not to have attribute ${attr}${expectedValue !== undefined ? `="${expectedValue}"` : ''}`
          : `expected element to have attribute ${attr}${expectedValue !== undefined ? `="${expectedValue}"` : ''}, but got ${actualValue}`,
    };
  },
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  document.cookie = 'labelx_csrftoken=; Max-Age=0; path=/';
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});
