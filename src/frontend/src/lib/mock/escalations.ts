/**
 * Hằng số và type dùng chung của màn hình Escalations.
 * Dữ liệu minh họa (Guideline Gaps, Decision Cases) đã gỡ: các tab dùng API thật (MBE-02).
 */
export type EscalationsTabKey = 'gaps' | 'cases' | 'adj';
export type Tone = 'info' | 'warning' | 'success' | '';

export const LIST_TIP = 'Phân xử các case liên quan';

export interface ListRow { a: string; b: string; c: string; d: string; e: string; tone: Tone }
