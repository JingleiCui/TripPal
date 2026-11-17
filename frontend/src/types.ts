export type Requirements = {
  city_stays?: { city: string; days: number }[];
  city: string;
  origin: string;
  start_date: string | null;
  days: number;
  people: number;
  budget: number | null;
  transport: "public_transit" | "walk" | "drive";
  style: "city" | "outdoor";
  max_walk_meters: number;
  interests: string;
  locked_ids: string[];
  excluded_ids: string[];
  indoor_only: boolean;
  needs_accommodation?: boolean | null;
};
export type Source = {
  provider: string;
  url?: string;
  retrieved_at: string;
  synthetic?: boolean;
};
export type Stop = {
  city?: string;
  guide_url?: string;
  booking_url?: string;
  guide_checked_at?: string;
  id: string;
  name: string;
  lon: number;
  lat: number;
  photos: string[];
  description: string;
  address: string;
  opening_text?: string;
  price_text?: string;
  source: Source;
  planned_start: string;
  planned_end: string;
  locked: boolean;
};
export type Route = {
  from_id: string;
  to_id: string;
  minutes?: number;
  walking_meters?: number;
  polyline: number[][];
  source?: Source;
  error?: string;
};
export type Day = {
  city?: string;
  arrival_route?: Route;
  day: number;
  date: string;
  stops: Stop[];
  routes: Route[];
  known_route_walking_meters: number;
  walking_note: string;
};
export type Plan = {
  hotels?: Hotel[];
  transfers?: {
    from_city: string;
    to_city: string;
    status: string;
    note: string;
  }[];
  title: string;
  days: Day[];
  fixture: boolean;
  requirements: Requirements;
  warnings: string[];
  rationale: string;
  budget: {
    known_subtotal_cny: number;
    limit_cny: number | null;
    unknown_items: string[];
    status: string;
  };
  /** 高德预报：forecasts[].casts[]。预测期外无数据属正常，UI 需诚实回退。 */
  weather?: {
    forecasts?: {
      city?: string;
      reporttime?: string;
      casts?: {
        date?: string;
        week?: string;
        dayweather?: string;
        nightweather?: string;
        daytemp?: string;
        nighttemp?: string;
      }[];
    }[];
    note?: string;
  };
  lodging?: { raw_text?: string };
  diff?: { added: string[]; removed: string[]; retained: string[] };
  findings?: { domain: string; text: string }[];
};
export type Hotel = Omit<Stop, "planned_start" | "planned_end" | "locked">;
export type Trip = {
  role?: "owner" | "editor" | "viewer";
  id: string;
  title: string;
  version: number;
  plan: Plan | Record<string, never>;
  updated: string;
};
export type Task = {
  id: string;
  trip_id: string;
  status: string;
  result: { error?: string; code?: string };
  requirements: Requirements;
  message: string;
  fixture: boolean;
  created: string;
};
export type Trace = {
  kind: string;
  data: Record<string, unknown>;
  created: string;
};
export type Health = {
  services: Record<string, string>;
  providers: Record<string, string>;
  fixture_enabled: boolean;
  voice_enabled: boolean;
  voice_ready?: boolean;
  vision_enabled?: boolean;
  vision_status?: string;
  model_provider?: string; // 当前对话供应商，来自 /api/v1/health；逐槽位状态见 /api/v1/models
};
export type Account = {
  name: string;
  csrf: string;
  preferences: Record<string, string>;
};
export type PendingChange = {
  id: string;
  kind: string;
  summary: string;
  changes: Record<string, unknown>;
  expires_at: string;
  expired: boolean;
  applied_plan_version: number;
  previous_plan_version: number;
};
export type ScreenshotFacts = {
  status: "ok" | "synthetic" | "unavailable" | "error";
  fields?: {
    cities: string[];
    dates: string[];
    places: string[];
    days: string | null;
    budget_text: string | null;
    notes: string[];
    raw_text: string;
  };
  unknowns?: string[];
  requires_confirmation?: boolean;
  synthetic?: boolean;
  source?: { provider: string; model?: string; retrieved_at?: string };
  note?: string;
  error?: string;
};
export type Attachment = {
  id: string;
  name: string;
  kind: string;
  parsed?: ScreenshotFacts | Record<string, unknown>;
  suggestion: string;
  created: string;
};
