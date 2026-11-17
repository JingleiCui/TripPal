import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { BedDouble, X, MapPin, Search, Check } from "lucide-react";
import { api, post } from "./api";
import type { Trip, Plan, Hotel } from "./types";
import { Button } from "./components/ui/button";

export function HotelSelector({ trip }: { trip: Trip }) {
  const client = useQueryClient(),
    plan = trip.plan as Plan,
    cities = Array.from(
      new Set(plan.days?.map((d) => d.city || plan.requirements.city) || []),
    );
  const [open, setOpen] = useState(false),
    [city, setCity] = useState(cities[0] || ""),
    [query, setQuery] = useState(""),
    [items, setItems] = useState<Hotel[]>([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  if (!trip.version) return null;
  return (
    <>
      <Button
        size="sm"
        variant="secondary"
        disabled={trip.role === "viewer"}
        onClick={() => setOpen(true)}
      >
        <BedDouble size={14} />
        住宿地点
      </Button>
      {open && (
        <div className="modal-scrim" onClick={() => setOpen(false)}>
          <div className="modal hotel-modal" onClick={(e) => e.stopPropagation()}>
            <Button
              variant="ghost"
              size="icon"
              className="modal-close"
              onClick={() => setOpen(false)}
            >
              <X size={17} />
            </Button>
            <h2>把住宿地点放到地图上</h2>
            <p className="muted">
              只记录你选择的地点，不代表已经预订。费用与库存请到平台确认。
            </p>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError("");
                try {
                  const result = await api<{ items: Hotel[] }>(
                    `/trips/${trip.id}/hotels?city=${encodeURIComponent(city)}&query=${encodeURIComponent(query)}`,
                  );
                  setItems(result.items);
                } catch (e) {
                  setError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              <label>
                城市
                <select value={city} onChange={(e) => setCity(e.target.value)}>
                  {cities.map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              <label>
                酒店或区域
                <input
                  aria-label="酒店查询"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="比如：北京站附近"
                  required
                />
              </label>
              <Button size="sm" disabled={busy}>
                <Search size={14} />
                查询地点
              </Button>
            </form>
            {items.map((item) => (
              <div className="hotel-choice" key={item.id}>
                <MapPin size={16} />
                <div>
                  <b>{item.name}</b>
                  <small>{item.address}</small>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={busy}
                  onClick={async () => {
                    try {
                      await post(`/trips/${trip.id}/hotel`, {
                        place_id: item.id,
                        city,
                        base_version: trip.version,
                      });
                      await client.invalidateQueries({
                        queryKey: ["trip", trip.id],
                      });
                      setOpen(false);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <Check size={14} />
                  选择
                </Button>
              </div>
            ))}
            {error && (
              <div role="alert" className="notice error">
                {error}
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
