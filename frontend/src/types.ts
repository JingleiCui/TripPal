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
};
