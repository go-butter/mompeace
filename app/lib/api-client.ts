// Dev-machine LAN IP ??update this if the network changes.
export const API_BASE_URL = 'http://192.168.219.107:8000';

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

export interface IntakeTodayResponse {
  user_id: number;
  date: string;
  pregnancy_week: number;
  pregnancy_day: number;
  due_date: string | null;
  days_until_due: number | null;
  trimester: string;
  trimester_label: string;
  water_cups: number;
  intake: {
    total_caffeine: number;
    total_sugar: number;
    total_sodium: number;
    total_calories: number;
  };
  limits: {
    caffeine_limit_mg: number;
    sugar_limit_g: number;
    sodium_limit_mg: number;
  };
  remaining: {
    remaining_caffeine: number;
    remaining_sugar: number;
    remaining_sodium: number;
  };
  progress: {
    caffeine_percent: number;
    sugar_percent: number;
    sodium_percent: number;
  };
  status: {
    overall_status: string;
    caffeine_status: string;
    sugar_status: string;
    sodium_status: string;
  };
  status_label: {
    overall: string;
    caffeine: string;
    sugar: string;
    sodium: string;
  };
  summary: {
    title: string;
    messages: string[];
  };
  note: string | null;
}

export interface FoodLogEntry {
  log_id: number;
  user_id: number;
  food_id: number | null;
  food_name: string;
  category: string | null;
  input_type: string | null;
  amount: number | null;
  unit: string | null;
  eaten_at: string;
  time: string;
  risk_level: string;
  calories_kcal: number | null;
  sugar_g: number;
  sodium_mg: number;
  caffeine_mg: number | null;
  protein_g: number;
  allergens: string[];
}

export interface FoodLogTodayResponse {
  user_id: number;
  date: string;
  count: number;
  logs: FoodLogEntry[];
}

export interface RiskDetailEntry {
  value: number | null;
  unit: string;
  status: 'safe' | 'caution' | 'avoid' | 'unknown' | 'check_required';
  label: string;
  standard: string;
  keywords?: string[];
}

export interface RiskAllergyEntry {
  allergens: string[];
  status: 'check_required' | 'safe';
  label: string;
}

export interface BarcodeFoodData {
  barcode: string;
  food_name: string;
  food_category: string | null;
  food_type: string | null;
  serving_size: string | null;
  calories_kcal: number;
  sodium_mg: number;
  sugar_g: number;
  carbohydrate_g: number;
  protein_g: number;
  allergens: string[];
  warnings: string[];
}

export interface BarcodeRisk {
  pregnancy_week: number;
  trimester: 'early' | 'middle' | 'late';
  trimester_label: string;
  overall_status: 'safe' | 'caution' | 'avoid';
  overall_label: string;
  title: string;
  details: {
    caffeine: RiskDetailEntry;
    sugar: RiskDetailEntry;
    sodium: RiskDetailEntry;
    allergy: RiskAllergyEntry;
  };
  messages: string[];
}

export interface BarcodeFoodResponse {
  source: string;
  food_id: number;
  data: BarcodeFoodData;
  risk: BarcodeRisk;
}

export interface FoodLogCreateRequest {
  user_id: number;
  food_name: string;
  input_type: string;
  category?: string | null;
  amount?: number;
  unit?: string;
  caffeine_mg?: number | null;
  sugar_g?: number;
  sodium_mg?: number;
  calories_kcal?: number;
  carbohydrate_g?: number | null;
  protein_g?: number | null;
  food_id?: number | null;
}

export interface FoodLogCreateResponse {
  log_id: number;
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
    throw new Error('?�버???�결?????�습?�다');
  }

  const data = await res.json();

  if (!res.ok) {
    throw new ApiError(data.detail);
  }

  return data as TRes;
}

async function get<TRes>(path: string): Promise<TRes> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    throw new Error('?�버???�결?????�습?�다');
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

export function getIntakeToday(userId: number): Promise<IntakeTodayResponse> {
  return get(`/intake/today/${userId}`);
}

export function getFoodLogToday(userId: number): Promise<FoodLogTodayResponse> {
  return get(`/food-log/today/${userId}`);
}

export function getFoodByBarcode(
  barcode: string,
  pregnancyWeek: number
): Promise<BarcodeFoodResponse> {
  return get(`/foods/barcode/${encodeURIComponent(barcode)}?pregnancy_week=${pregnancyWeek}`);
}

export function createFoodLog(body: FoodLogCreateRequest): Promise<FoodLogCreateResponse> {
  return post('/food-log', body);
}
