import { BRAND } from "./brand";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  BedDouble,
  BookOpen,
  Compass,
  Loader2,
  MapPin,
  Mountain,
  Route,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Utensils,
} from "lucide-react";
import { TripalMark } from "./components/TripalLogo";

const INTERESTS = [
  { icon: Compass, label: "随心探索", category: "all" },
  { icon: BedDouble, label: "住得舒服", category: "stays" },
  { icon: Utensils, label: "寻找美食", category: "food" },
  { icon: Mountain, label: "走进自然", category: "nature" },
  { icon: BookOpen, label: "人文与艺术", category: "art" },
];
const DESTINATIONS = [
  {
    city: "杭州",
    image: "hangzhou",
    theme: "湖山与茶香",
    copy: "沿着西湖走走，喝一杯龙井。",
  },
  {
    city: "北京",
    image: "beijing",
    theme: "古都漫游",
    copy: "在胡同与古迹之间，慢慢走。",
  },
  {
    city: "上海",
    image: "shanghai",
    theme: "城市新发现",
    copy: "沿着江岸，遇见城市的另一面。",
  },
];

export function HomeDiscovery({
  workspace,
  onOpenBrief,
  city,
}: {
  workspace: ReactNode;
  onOpenBrief: () => void;
  city: string;
}) {
  const navigate = useNavigate();
  return (
    <section className="discovery-home travel-home" aria-label="旅行灵感">
      <header className="planning-home-heading">
        <h1>一句话，安排好下一程。</h1>
        <p>边聊边完善计划，灵感和方案都留在这里。</p>
      </header>
      {workspace}
      <button className="planning-brief-link text-link" onClick={onOpenBrief}>
        <SlidersHorizontal size={16} /> 按条件规划
      </button>

      <div className="travel-home-discover">
        <div className="discovery-section-title">
          <div>
            <h2>把好奇，变成下一站。</h2>
            <p>先找喜欢的地方，再安排合适的路线。</p>
          </div>
          <Link to="/explore" className="text-link">
            探索更多 <ArrowRight size={16} />
          </Link>
        </div>
        <div className="discovery-categories" aria-label="旅行兴趣">
          {INTERESTS.map(({ icon: Icon, label, category }, index) => (
            <button
              key={category}
              className={`category-chip tone-${index}`}
              onClick={() =>
                navigate("/explore?" + new URLSearchParams({ city, category }))
              }
            >
              <Icon size={18} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
        <div className="destination-grid">
          {DESTINATIONS.map((destination) => (
            <button
              className="destination-card"
              key={destination.city}
              aria-label={`规划${destination.city}旅行`}
              onClick={() =>
                navigate(
                  "/explore?" +
                    new URLSearchParams({ city: destination.city, category: "all" }),
                )
              }
            >
              <img
                src={`/images/${destination.image}.jpg`}
                alt={`${destination.city}旅行风景`}
                loading="lazy"
              />
              <div className="destination-info">
                <div>
                  <span>{destination.theme}</span>
                  <h3>{destination.city}</h3>
                  <p>{destination.copy}</p>
                </div>
                <ArrowUpRight size={20} aria-hidden="true" />
              </div>
            </button>
          ))}
        </div>
      </div>
      <div className="travel-home-principles">
        <span>
          <Route size={19} />
          <b>路线，顺着走</b>
          <small>把地点、时间和交通连起来</small>
        </span>
        <span>
          <ShieldCheck size={19} />
          <b>依据，看得见</b>
          <small>来源与待核实信息清楚展示</small>
        </span>
        <span>
          <SlidersHorizontal size={19} />
          <b>安排，随时改</b>
          <small>按你的偏好调整每一天</small>
        </span>
      </div>
    </section>
  );
}
