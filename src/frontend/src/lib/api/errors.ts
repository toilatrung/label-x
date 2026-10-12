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
  REFERENCE_SCOPE_MISMATCH: 'Snapshot và nguồn GT phải thuộc cùng dataset.',
  REFERENCE_SOURCE_CHECKSUM_MISMATCH: 'Tệp GT không khớp mã kiểm tra. Vui lòng kiểm tra nguồn tệp.',
  REFERENCE_MAPPING_INVALID: 'Mapping hoặc cấu hình matching không hợp lệ. Vui lòng kiểm tra lại.',
  REFERENCE_REVIEW_REQUIRED: 'Reference chưa đủ bằng chứng duyệt. Vui lòng hoàn tất review trước khi khóa.',
  REFERENCE_SPLIT_UNVERIFIED: 'Phân chia dữ liệu chưa được xác minh hoặc có nhóm nguồn trùng nhau.',
  REFERENCE_TRAINING_OVERLAP: 'Chưa chứng minh dữ liệu độc lập với tập huấn luyện Detector.',
  REFERENCE_LOCKED: 'Version reference đã khóa. Muốn sửa, hãy tạo version mới.',
  REFERENCE_VERSION_CONFLICT: 'Version reference đã thay đổi. Vui lòng tải lại trước khi duyệt hoặc khóa.',
} satisfies Record<ErrorCode, string>;

export const CSRF_ERROR_MESSAGE = 'Mã bảo vệ của phiên không hợp lệ hoặc đã bị thay thế (ví dụ do cookie của ứng dụng khác cùng host). Vui lòng tải lại trang và thử lại.';
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

export function apiErrorMessage(status: number, code?: string, requestId?: string, reason?: string): string {
  let message: string;
  if (status >= 500 && status < 600) {
    // Do not surface server diagnostics or mislabel a server failure as validation.
    message = SERVER_ERROR_MESSAGE;
    if (requestId?.trim()) message += ` Mã yêu cầu: ${requestId.trim()}`;
  } else if (code === 'FORBIDDEN' && reason === 'csrf') {
    message = CSRF_ERROR_MESSAGE;
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
    const reason = typeof body?.details?.reason === 'string' ? body.details.reason : undefined;
    super(apiErrorMessage(status, body?.code, requestId, reason));
    this.name = 'ApiRequestError';
    this.detail = body;
    this.requestId = requestId;
  }
}

/** True when the server rejected the request for a missing or mismatched CSRF token. */
export function isCsrfError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 403 &&
    error.detail?.code === 'FORBIDDEN' && error.detail.details?.reason === 'csrf';
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiRequestError ? error.message : NETWORK_ERROR_MESSAGE;
}
