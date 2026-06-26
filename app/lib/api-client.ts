// Dev-machine LAN IP — update this if the network changes.
export const API_BASE_URL = 'http://192.168.45.220:8000';

export interface RegisterRequest {
  nickname: string;
  login_id: string;
  password: string;
  password_confirm: string;
}

export interface RegisterResponse {
  user_id: number;
  nickname: string;
  login_id: string;
  message: string;
}

export interface LoginRequest {
  login_id: string;
  password: string;
}

export interface LoginResponse {
  user_id: number;
  nickname: string;
  login_id: string;
  pregnancy_week: number | null;
  due_date: string | null;
  allergy_info: string | null;
  message: string;
}

export interface PregnancyUpdateRequest {
  pregnancy_week: number;
  pregnancy_day: number;
  due_date: string;
}

export interface PregnancyUpdateResponse {
  user_id: number;
  pregnancy_week: number | null;
  pregnancy_day: number | null;
  due_date: string | null;
  pregnancy_entered_at: string | null;
  message: string;
}

export class ApiError extends Error {}

async function request<TReq, TRes>(method: 'POST' | 'PUT', path: string, body: TReq): Promise<TRes> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('서버에 연결할 수 없습니다');
  }

  const data = await res.json();

  if (!res.ok) {
    throw new ApiError(data.detail);
  }

  return data as TRes;
}

function post<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  return request('POST', path, body);
}

function put<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  return request('PUT', path, body);
}

export function registerUser(body: RegisterRequest): Promise<RegisterResponse> {
  return post('/auth/register', body);
}

export function loginUser(body: LoginRequest): Promise<LoginResponse> {
  return post('/auth/login', body);
}

export function updatePregnancyInfo(
  userId: number,
  body: PregnancyUpdateRequest
): Promise<PregnancyUpdateResponse> {
  return put(`/users/${userId}/pregnancy`, body);
}
