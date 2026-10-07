import type { components } from './contract';

export type ErrorCode = components['schemas']['ErrorCode'];

// The contract is the source of codes. TypeScript rejects missing or extra entries.
export const ERROR_MESSAGES = {
  VALIDATION_ERROR: 'Dữ liệu không hợp lệ. Vui lòng kiểm tra và thử lại.',
  INVALID_CREDENTIALS: 'Tên đăng nhập hoặc mật khẩu không chính xác.',
  NOT_AUTHENTICATED: 'Phiên đăng nhập đã hết hạn hoặc bạn chưa đăng nhập. Vui lòng đăng nhập lại.',
  FORBIDDEN: 'Bạn không có quyền thực hiện thao tác này.',
  OUT_OF_SCOPE: 'Dataset nằm ngoài phạm vi được cấp quyền của bạn.',
  SELF_REVIEW_FORBIDDEN: 'Bạn không được review annotation do chính mình thực hiện.',
  SAME_REQUESTER_APPROVER: 'Người duyệt phải khác người yêu cầu, kể cả khi dùng tài khoản khác.',
  IDENTITY_MAPPING_MISSING: 'Tài khoản chưa được liên kết với CVAT. Vui lòng liên hệ quản trị viên.',
  NOT_FOUND: 'Không tìm thấy tài nguyên yêu cầu. Vui lòng kiểm tra thông tin và thử lại.',
  LEASE_CONFLICT: 'Quyền giữ frame đã hết hạn hoặc thuộc người khác. Vui lòng tải lại.',
  INVALID_TRANSITION: 'Không thể thực hiện thao tác ở trạng thái hiện tại. Vui lòng tải lại.',
  REVISION_UNCHANGED: 'Revision chưa thay đổi. Vui lòng hoàn tất sửa annotation trước khi thử lại.',
  IDEMPOTENCY_KEY_REUSED: 'Mã yêu cầu đã được dùng với nội dung khác. Vui lòng tải lại và thử lại.',
  SCOPE_BUSY: 'Phạm vi này đang được xử lý. Vui lòng chờ rồi thử lại.',
  ISSUE_EXISTS: 'Issue đã tồn tại cho annotation và rule này. Vui lòng kiểm tra Issue hiện có.',
  BUSINESS_RULE_UNMET: 'Chưa đủ điều kiện thực hiện thao tác. Vui lòng kiểm tra các yêu cầu liên quan.',
  INSUFFICIENT_SAMPLE: 'Chưa đủ mẫu để đánh giá. Vui lòng bổ sung mẫu và thử lại.',
} satisfies Record<ErrorCode, string>;

export const NETWORK_ERROR_MESSAGE = 'Không kết nối được máy chủ. Vui lòng thử lại.';
export const FALLBACK_ERROR_MESSAGE = 'Không thể xử lý yêu cầu. Vui lòng thử lại.';
export const SERVER_ERROR_MESSAGE = 'Máy chủ gặp lỗi. Vui lòng thử lại sau.';

type ErrorDetail = Partial<Omit<components['schemas']['Error'], 'code'>> & { code?: string };

/** A response can come from a proxy or a newer server, outside the typed contract. */
export function readErrorDetail(value: unknown): ErrorDetail | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const body = value as Record<string, unknown>;
  return {
    code: typeof body.code === 'string' ? body.code : undefined,
    message: typeof body.message === 'string' ? body.message : undefined,
    request_id: typeof body.request_id === 'string' ? body.request_id : undefined,
    details: body.details && typeof body.details === 'object' && !Array.isArray(body.details)
      ? body.details as Record<string, unknown> : undefined,
  };
}

export function apiErrorMessage(status: number, code?: string, requestId?: string): string {
  let message: string;
  if (status >= 500 && status < 600) {
    // Do not surface server diagnostics or mislabel a server failure as validation.
    message = SERVER_ERROR_MESSAGE;
    if (requestId?.trim()) message += ` Mã yêu cầu: ${requestId.trim()}`;
  } else if (code && Object.hasOwn(ERROR_MESSAGES, code)) {
    message = ERROR_MESSAGES[code as ErrorCode];
  } else {
    switch (status) {
      case 0: message = NETWORK_ERROR_MESSAGE; break;
      case 400: message = ERROR_MESSAGES.VALIDATION_ERROR; break;
      case 401: message = ERROR_MESSAGES.NOT_AUTHENTICATED; break;
      case 403: message = ERROR_MESSAGES.FORBIDDEN; break;
      case 404: message = ERROR_MESSAGES.NOT_FOUND; break;
      case 409: message = ERROR_MESSAGES.INVALID_TRANSITION; break;
      case 422: message = ERROR_MESSAGES.BUSINESS_RULE_UNMET; break;
      default: message = FALLBACK_ERROR_MESSAGE;
    }
  }
  return message;
}

export class ApiRequestError extends Error {
  public detail?: ErrorDetail;
  public requestId?: string;

  constructor(public status: number, detail?: unknown, headers?: Headers) {
    const body = readErrorDetail(detail);
    const requestId = body?.request_id?.trim() || headers?.get('X-Request-ID')?.trim() || undefined;
    super(apiErrorMessage(status, body?.code, requestId));
    this.name = 'ApiRequestError';
    this.detail = body;
    this.requestId = requestId;
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError ? error.message : NETWORK_ERROR_MESSAGE;
}
