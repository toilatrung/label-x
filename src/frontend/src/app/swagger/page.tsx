import type { Metadata } from 'next';
import { ApiExplorer } from './ApiExplorer';

export const metadata: Metadata = {
  title: 'API Explorer · LabelX',
  description: 'Danh mục API LabelX và trạng thái tích hợp backend.',
};

export default function SwaggerPage() {
  return <ApiExplorer />;
}
