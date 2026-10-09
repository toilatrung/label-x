import React from 'react';

/** Supplied LabelX reference symbols, shared by navigation and review controls. */
export function Icon({ name, className = 'lx-menu__ico' }: { name: string; className?: string }) {
  return <svg className={className} aria-hidden="true"><use href={`/icons/labelx.svg#i-${name}`} /></svg>;
}
