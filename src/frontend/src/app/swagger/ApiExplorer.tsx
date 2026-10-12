'use client';

import React from 'react';
import Link from 'next/link';
import { API_ENDPOINTS, API_NAVIGATION, type ApiConnection, type ApiEndpoint } from '@/lib/api-explorer/catalog';
import styles from './swagger.module.css';

type StatusFilter = 'all' | ApiConnection;

const STATUS_LABEL: Record<ApiConnection, string> = {
  backend: 'Đã kết nối BE',
  mock: 'Mockup · Chưa nối BE',
};

const ORIGIN_LABEL = { openapi: 'OpenAPI', design: 'Design' } as const;

function EndpointCard({ endpoint }: { endpoint: ApiEndpoint }) {
  const [copied, setCopied] = React.useState(false);
  const payload = JSON.stringify(endpoint.response, null, 2);

  async function copyPayload() {
    await navigator.clipboard.writeText(payload);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return <article className={styles.endpoint} id={endpoint.id}>
    <div className={styles.endpointHead}>
      <span className={`${styles.method} ${styles[`method${endpoint.method}`]}`}>{endpoint.method}</span>
      <code className={styles.path}>{endpoint.path}</code>
      <span className={`${styles.status} ${endpoint.connection === 'backend' ? styles.connected : styles.mock}`}>
        <span aria-hidden="true" />{STATUS_LABEL[endpoint.connection]}
      </span>
    </div>
    <div className={styles.endpointBody}>
      <div>
        <p className={styles.summary}>{endpoint.summary}</p>
        <p className={styles.operation}>operationId: <code>{endpoint.id}</code>
          <span className={styles.origin}>{ORIGIN_LABEL[endpoint.origin ?? 'openapi']}</span></p>
      </div>
      <div className={styles.response}>
        <div className={styles.responseHead}>
          <div><span>Response mẫu</span><strong>{endpoint.responseStatus}</strong></div>
          <button type="button" onClick={() => void copyPayload()} aria-label={`Sao chép payload ${endpoint.id}`}>
            {copied ? 'Đã sao chép' : 'Sao chép'}
          </button>
        </div>
        <pre><code>{payload}</code></pre>
      </div>
    </div>
  </article>;
}
export function ApiExplorer() {
  const [query, setQuery] = React.useState('');
  const [status, setStatus] = React.useState<StatusFilter>('all');
  const connectedCount = API_ENDPOINTS.filter(endpoint => endpoint.connection === 'backend').length;
  const mockCount = API_ENDPOINTS.length - connectedCount;
  const normalizedQuery = query.trim().toLocaleLowerCase('vi');
  const filtered = API_ENDPOINTS.filter(endpoint => {
    const matchesStatus = status === 'all' || endpoint.connection === status;
    const haystack = `${endpoint.method} ${endpoint.path} ${endpoint.group} ${endpoint.section ?? ''} ${endpoint.summary} ${endpoint.id}`.toLocaleLowerCase('vi');
    return matchesStatus && (!normalizedQuery || haystack.includes(normalizedQuery));
  });
  const groups = API_NAVIGATION.map(group => ({
    ...group,
    sections: group.sections.map(currentSection => ({
      ...currentSection,
      endpoints: filtered.filter(endpoint => endpoint.group === group.label && endpoint.section === currentSection.label),
    })).filter(currentSection => currentSection.endpoints.length > 0),
  })).filter(group => group.sections.length > 0);

  return <main className={styles.shell}>
    <header className={styles.topbar}>
      <Link href="/" className={styles.brand} aria-label="Về trang chủ LabelX">Label<span>X</span></Link>
      <div className={styles.product}><span>Developer tools</span><strong>API Explorer</strong></div>
      <a className={styles.schemaLink} href="/api/schema/" target="_blank" rel="noreferrer">OpenAPI schema <span aria-hidden="true">↗</span></a>
    </header>

    <section className={styles.hero}>
      <div>
        <p className={styles.eyebrow}>LABELX API · OPENAPI + DESIGN INVENTORY</p>
        <h1>API Explorer</h1>
        <p className={styles.intro}>Theo dõi mức độ triển khai backend ngay trong frontend. Danh mục hợp nhất OpenAPI contract và nhu cầu từ các màn hình design; mỗi operation có một response mẫu.</p>
      </div>
      <div className={styles.metrics} aria-label="Tổng quan API">
        <div><strong>{API_ENDPOINTS.length}</strong><span>Operations</span></div>
        <div><strong className={styles.good}>{connectedCount}</strong><span>Đã có BE</span></div>
        <div><strong className={styles.warn}>{mockCount}</strong><span>Đang mockup</span></div>
      </div>
    </section>

    <section className={styles.controls} aria-label="Bộ lọc API">
      <label className={styles.search}>
        <span className={styles.srOnly}>Tìm API</span>
        <span aria-hidden="true">⌕</span>
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm theo path, operation hoặc nhóm..." />
        {query && <button type="button" onClick={() => setQuery('')} aria-label="Xóa từ khóa">×</button>}
      </label>
      <div className={styles.filters} role="group" aria-label="Lọc theo trạng thái kết nối">
        {([
          ['all', `Tất cả ${API_ENDPOINTS.length}`],
          ['backend', `Đã kết nối ${connectedCount}`],
          ['mock', `Chưa nối BE ${mockCount}`],
        ] as const).map(([value, label]) => <button key={value} type="button" className={status === value ? styles.activeFilter : ''}
          aria-pressed={status === value} onClick={() => setStatus(value)}>{label}</button>)}
      </div>
      <span className={styles.resultCount}>{filtered.length} kết quả</span>
    </section>

    <div className={styles.content}>
      <aside className={styles.sidebar} aria-label="Nhóm API">
        <p>Nhóm API</p>
        {groups.map(group => <div className={styles.sidebarGroup} key={group.key}>
          <a href={`#group-${group.key}`}>
            <span>{group.label}</span><b>{group.sections.reduce((total, currentSection) => total + currentSection.endpoints.length, 0)}</b>
          </a>
          {group.sections.length > 1 && <div className={styles.sidebarSections}>
            {group.sections.map(currentSection => <a key={currentSection.key} href={`#section-${group.key}-${currentSection.key}`}>
              <span>{currentSection.label}</span><b>{currentSection.endpoints.length}</b>
            </a>)}
          </div>}
        </div>)}
      </aside>

      <section className={styles.catalog} aria-live="polite">
        {groups.map(group => <section className={styles.group} key={group.key} id={`group-${group.key}`}>
          <div className={styles.groupTitle}><h2>{group.label}</h2><span>{group.sections.reduce((total, currentSection) => total + currentSection.endpoints.length, 0)} operations</span></div>
          {group.sections.map(currentSection => <section className={styles.section} key={currentSection.key} id={`section-${group.key}-${currentSection.key}`}>
            {group.sections.length > 1 && <div className={styles.sectionTitle}><h3>{currentSection.label}</h3><span>{currentSection.endpoints.length} operations</span></div>}
            <div className={styles.endpointList}>{currentSection.endpoints
              .map(endpoint => <EndpointCard endpoint={endpoint} key={endpoint.id} />)}</div>
          </section>)}
        </section>)}
        {!filtered.length && <div className={styles.empty}><strong>Không tìm thấy API phù hợp</strong><span>Thử đổi từ khóa hoặc bộ lọc trạng thái.</span></div>}
      </section>
    </div>

    <footer className={styles.footer}>
      <span>Trạng thái được đối chiếu từ OpenAPI, design và Django URL + HTTP handler trên nhánh <code>develop-fe</code>. Nhãn Design chưa đồng nghĩa contract đã được duyệt.</span>
      <a href="#top" onClick={event => { event.preventDefault(); window.scrollTo({ top: 0, behavior: 'smooth' }); }}>Lên đầu trang ↑</a>
    </footer>
  </main>;
}
