// Dev-machine LAN IP ??update this if the network changes.
export const API_BASE_URL = "http://192.168.219.111:8000";

export interface RegisterRequest {
  nickname: string;
  login_id: string;
  password: string;
  password_confirm: string;
  // 실제 앱 플로우에서는 사용되지 않음 — 계정 생성 시점엔 아직 선택 화면을 거치지 않았고,
  // 선택은 nutrient-select.tsx가 별도로 updateNutrientPreferences()를 호출해 저장한다.
  // 백엔드 모델과 형태를 맞추기 위해 필드만 남겨둔다.
  selected_nutrients?: string[];
  // 실제 앱 플로우에서는 사용되지 않음 — 나이대는 input.tsx가 별도로
  // updatePregnancyInfo()를 통해 저장한다. 백엔드 모델과 형태를 맞추기 위해 필드만 남겨둔다.
  age_bracket?: '19-29' | '30-49';
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
  message: string;
}

export interface PregnancyUpdateRequest {
  pregnancy_week?: number;
  pregnancy_day?: number;
  due_date?: string;
  age_bracket?: '19-29' | '30-49';
}

export interface PregnancyUpdateResponse {
  user_id: number;
  pregnancy_week: number | null;
  pregnancy_day: number | null;
  due_date: string | null;
  pregnancy_entered_at: string | null;
  age_bracket: string | null;
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

export interface NutrientSummaryItem {
  key: string;
  label: string;
  total: number;
  unit: string;
  limit: number | null;
  percent: number | null;
  status: string;
  status_label: string;
}

export interface IntakeSummaryResponse {
  user_id: number;
  date: string;
  caffeine: NutrientSummaryItem;
  water: NutrientSummaryItem;
  selected_nutrients: NutrientSummaryItem[];
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
  calories_kcal: number | null;
  sugar_g: number;
  sodium_mg: number;
  caffeine_mg: number | null;
  protein_g: number;
  extra_nutrients: { name: string; value: string; unit?: string | null }[];
}

export interface FoodLogTodayResponse {
  user_id: number;
  date: string;
  count: number;
  logs: FoodLogEntry[];
}

export interface FoodLogCreateRequest {
  user_id: number;
  food_name: string;
  input_type: string;
  category?: string | null;
  amount?: number;
  unit?: string;
  caffeine_mg?: number | null;
  sugar_g?: number | null;
  sodium_mg?: number | null;
  calories_kcal?: number;
  carbohydrate_g?: number | null;
  protein_g?: number | null;
  food_id?: number | null;
  eaten_at?: string;
  extra_nutrients?: { name: string; value: string; unit?: string }[];
  needs_review?: boolean;
  serving_multiplier?: number;
}

export interface FoodLogCreateResponse {
  log_id: number;
  message: string;
}

export interface UserFoodItemCreateRequest {
  user_id: number;
  food_name: string;
  caffeine_mg?: number | null;
  sugar_g?: number;
  sodium_mg?: number;
  calories_kcal?: number;
  carbohydrate_g?: number | null;
  protein_g?: number | null;
}

export interface UserFoodItemCreateResponse {
  user_food_item_id: number;
  message: string;
}

export interface PersonalFoodData {
  user_food_item_id: number;
  user_id: number;
  food_name: string;
  caffeine_mg: number | null;
  sugar_g: number;
  sodium_mg: number;
  calories_kcal: number;
  carbohydrate_g: number | null;
  protein_g: number | null;
  created_at: string;
}

export interface DishDbFoodData {
  food_id: number;
  food_code: string | null;
  food_name: string;
  category: string | null;
  subcategory: string | null;
  serving_label: string | null;
  caffeine_mg: number | null;
  sugar_g: number | null;
  sodium_mg: number | null;
  carbohydrate_g: number | null;
  protein_g: number | null;
  fat_g: number | null;
  calories_kcal: number | null;
}

export interface FoodSearchResultItem {
  source: 'personal' | 'dish_db_download';
  food_id: number;
  data: PersonalFoodData | DishDbFoodData;
}

export interface FoodSearchResponse {
  query: string;
  count: number;
  page_no: number;
  num_of_rows: number;
  results: FoodSearchResultItem[];
}

export interface FoodLogCalendarDay {
  date: string;
  overall_status: 'safe' | 'caution' | 'avoid' | 'unknown';
}

export interface FoodLogCalendarResponse {
  user_id: number;
  year: number;
  month: number;
  days: FoodLogCalendarDay[];
}

export interface WaterLogEntry {
  log_id: number;
  amount_ml: number;
  logged_at: string;
  time: string | null;
}

export interface WaterTodayResponse {
  user_id: number;
  date: string;
  target_ml: number;
  total_ml: number;
  percent: number;
  logs: WaterLogEntry[];
}

export interface WaterWeekDay {
  label: string;
  date: string;
  amount_ml: number;
  hit_target: boolean;
  is_today: boolean;
}

export interface WaterWeekResponse {
  user_id: number;
  date_range: { start: string; end: string };
  target_ml: number;
  days: WaterWeekDay[];
}

export interface WaterLogCreateRequest {
  user_id: number;
  amount_ml: number;
  logged_at?: string;
}

export interface WaterLogCreateResponse {
  log_id: number;
  message: string;
}

export interface WaterLogDeleteResponse {
  log_id: number;
  message: string;
}

export class ApiError extends Error {
  field?: string;
}

function throwApiError(detail: unknown): never {
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const err = new ApiError((detail as { message: string }).message);
    const field = (detail as { field?: string }).field;
    if (field) err.field = field;
    throw err;
  }
  throw new ApiError(detail as string);
}

async function request<TReq, TRes>(method: 'POST' | 'PUT', path: string, body: TReq): Promise<TRes> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error('서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.');
  }

  const data = await res.json();

  if (!res.ok) {
    throwApiError(data.detail);
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
    throw new Error('서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.');
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

async function del<TRes>(path: string): Promise<TRes> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
    });
  } catch {
    throw new Error('서버에 연결할 수 없습니다. 인터넷 연결을 확인해 주세요.');
  }

  const data = await res.json();

  if (!res.ok) {
    throw new ApiError(data.detail);
  }

  return data as TRes;
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

export interface NutrientPreferenceUpdateResponse {
  user_id: number;
  selected_nutrients: string[];
  message: string;
}

// selectedNutrients=null이면 값을 바꾸지 않고 현재 선택을 그대로 조회한다 (부분 업데이트와
// 동일한 방식) — 마이페이지 화면에서 현재 선택을 불러올 때도 이 함수를 그대로 재사용한다.
export function updateNutrientPreferences(
  userId: number,
  selectedNutrients: string[] | null
): Promise<NutrientPreferenceUpdateResponse> {
  return put(`/users/${userId}/nutrient-preferences`, { selected_nutrients: selectedNutrients });
}

export function getIntakeToday(userId: number): Promise<IntakeTodayResponse> {
  return get(`/intake/today/${userId}`);
}

export function getIntakeSummary(userId: number): Promise<IntakeSummaryResponse> {
  return get(`/intake/summary/${userId}`);
}

export function getFoodLogToday(userId: number): Promise<FoodLogTodayResponse> {
  return get(`/food-log/today/${userId}`);
}

export function createFoodLog(body: FoodLogCreateRequest): Promise<FoodLogCreateResponse> {
  return post('/food-log', body);
}

export interface OcrScanRequest {
  image: string; // base64, no data URI prefix
}

export type OcrScaleMethod =
  | 'total_content'
  | 'per_basis_with_total'
  | 'per_serving_with_count'
  | 'unknown';

export interface OcrScanResponse {
  product_name: string | null;
  sugar_g: number | null;
  sodium_mg: number | null;
  scale_method: OcrScaleMethod;
  scale_factor_applied: number | null;
  basis_amount_value: number | null;
  needs_review: boolean;
}

export function scanNutritionLabel(body: OcrScanRequest): Promise<OcrScanResponse> {
  return post('/ocr/scan', body);
}

export interface FoodLogDeleteResponse {
  log_id: number;
  message: string;
}

export function deleteFoodLog(logId: number, userId: number): Promise<FoodLogDeleteResponse> {
  return del(`/food-log/${logId}?user_id=${userId}`);
}

export function getIntakeByDate(userId: number, date: string): Promise<IntakeTodayResponse> {
  return get(`/intake/by-date/${userId}?date=${date}`);
}

export function getFoodLogByDate(userId: number, date: string): Promise<FoodLogTodayResponse> {
  return get(`/food-log/by-date/${userId}?date=${date}`);
}

export function getFoodLogCalendar(
  userId: number,
  year: number,
  month: number
): Promise<FoodLogCalendarResponse> {
  return get(`/food-log/calendar/${userId}?year=${year}&month=${month}`);
}

export function getWaterToday(userId: number): Promise<WaterTodayResponse> {
  return get(`/water-log/today/${userId}`);
}

export function getWaterByDate(userId: number, date: string): Promise<WaterTodayResponse> {
  return get(`/water-log/by-date/${userId}?date=${date}`);
}

export function getWaterWeek(userId: number, date?: string): Promise<WaterWeekResponse> {
  return get(`/water-log/week/${userId}${date ? `?date=${date}` : ''}`);
}

export function createWaterLog(body: WaterLogCreateRequest): Promise<WaterLogCreateResponse> {
  return post('/water-log', body);
}

export function deleteWaterLog(logId: number, userId: number): Promise<WaterLogDeleteResponse> {
  return del(`/water-log/${logId}?user_id=${userId}`);
}

// TODO: getPremiumReport() — added in a separate task, wires premium-report.tsx to live data.

export function createPersonalFoodItem(
  body: UserFoodItemCreateRequest
): Promise<UserFoodItemCreateResponse> {
  return post('/foods/personal', body);
}

export interface RecommendationRequest {
  user_id: number;
  query?: string | null;
  category?: string | null;
  limit?: number;
}

export interface RecommendationNutrients {
  caffeine_mg: number | null;
  sugar_g: number | null;
  sodium_mg: number | null;
  carbohydrate_g: number | null;
  protein_g: number | null;
}

export interface RecommendationDataConfidence {
  score: number;
  label: string;
  reasons: string[];
}

export interface RecommendationAlternative {
  food_id: number;
  food_name: string;
  reason: string;
}

export interface RecommendationItem {
  food_id: number;
  food_name: string;
  source: string | null;
  category: string | null;
  status: 'possible' | 'caution' | 'avoid';
  label: string;
  reason: string;
  reason_nutrient: 'caffeine' | 'sugar' | 'sodium' | null;
  nutrients: RecommendationNutrients;
  data_confidence: RecommendationDataConfidence;
  alternative: RecommendationAlternative | null;
}

export interface RecommendationWeekPattern {
  avg_caffeine_mg: number;
  avg_sugar_g: number;
  avg_sodium_mg: number;
  unknown_caffeine_days: number;
  unknown_sugar_days: number;
  unknown_sodium_days: number;
}

export interface RecommendationTodayIntake {
  caffeine_mg: number;
  sugar_g: number;
  sodium_mg: number;
  unknown_caffeine_count: number;
  unknown_sugar_count: number;
  unknown_sodium_count: number;
}

export interface RecommendationResponse {
  user_id: number;
  pregnancy_week: number;
  trimester: string;
  today_intake: RecommendationTodayIntake;
  week_pattern: RecommendationWeekPattern;
  recommendations: RecommendationItem[];
  message?: string;
}

export interface FoodCategoriesResponse {
  categories: string[];
}

export function getRecommendations(
  body: RecommendationRequest
): Promise<RecommendationResponse> {
  return post('/recommendations', body);
}

export function getFoodCategories(): Promise<FoodCategoriesResponse> {
  return get('/categories');
}

const SEARCH_NUM_OF_ROWS = 30;

export function searchFoods(
  query: string,
  userId: number
): Promise<FoodSearchResponse> {
  return get(
    `/foods/search?query=${encodeURIComponent(query)}&user_id=${userId}&num_of_rows=${SEARCH_NUM_OF_ROWS}`
  );
}

export interface CoffeeCaffeineEntry {
  brand: string;
  menu: string;
  size: string | null;
  volume_ml: number | null;
  hot_or_ice: 'hot' | 'ice';
  is_decaf: boolean;
  caffeine_mg: number;
  source_tier: number;
  source_url: string;
  verified_date: string;
  note?: string;
}

export interface HomeCoffeePreset {
  brand: string;
  menu: string;
  serving: string;
  caffeine_mg: number;
  source_tier: number;
  source_url: string;
  verified_date: string;
  note?: string;
}

export interface CoffeeOptionsResponse {
  brands: CoffeeCaffeineEntry[];
  home_presets: HomeCoffeePreset[];
}

export function getCoffeeOptions(): Promise<CoffeeOptionsResponse> {
  return get('/coffee/options');
}
