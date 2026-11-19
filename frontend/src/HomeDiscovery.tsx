import { BRAND } from "./brand";
import type { FormEvent } from "react";
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
  idea,
  setIdea,
  onPlan,
  starting,
  error,
  city,
  onOpenBrief,
}: {
  idea: string;
  setIdea: (value: string) => void;
  onPlan: (event: FormEvent) => void;
  starting: boolean;
  error: string;
  city: string;
  onOpenBrief: () => void;
}) {
  const navigate = useNavigate();
  return (
    <section className="discovery-home travel-home" aria-label="旅行灵感">
      <div className="travel-home-hero">
        <div className="travel-home-intro">
          <p className="travel-home-role">
            <Sparkles size={16} aria-hidden="true" /> AI 旅行规划智能体助手
          </p>
          <h1>一句话，安排好下一程。</h1>
          <p className="travel-home-description">
            说出目的地、时间和偏好，
            <br />
            把想去的地方，变成每天的安排。
          </p>
          <form className="home-composer" onSubmit={onPlan}>
            <label htmlFor="home-trip-idea">这一次，想怎么旅行？</label>
            <textarea
              id="home-trip-idea"
              aria-label="旅行想法"
              value={idea}
              onChange={(event) => setIdea(event.target.value)}
              rows={3}
              maxLength={4000}
              required
              placeholder="比如：杭州三天，逛西湖、喝好茶，安排轻松一点。"
            />
            <div className="home-composer-bottom">
              <span>景点、美食、住宿与路线，一起安排。</span>
              <button
                type="submit"
                aria-label="开始规划旅行"
                disabled={starting || !idea.trim()}
              >
                {starting ? (
                  <Loader2 size={17} className="spin" />
                ) : (
                  <Sparkles size={17} />
                )}
                {starting ? "准备中…" : "开始规划"}
              </button>
            </div>
            {error && (
              <p className="notice error" role="alert">
                {error}
              </p>
            )}
          </form>
          <div className="home-ideas">
            <button
              onClick={() =>
                setIdea("周末去上海两天，想吃本地美食，找一家交通方便的酒店。")
              }
            >
              周末吃好住好
            </button>
            <button
              onClick={() =>
                setIdea("想去北京玩三天，带父母，少走路，景点之间交通方便，直接规划。")
              }
            >
              带父母轻松走走
            </button>
            <button className="home-brief-link" onClick={onOpenBrief}>
              <SlidersHorizontal size={14} /> 按条件规划
            </button>
          </div>
        </div>
        <figure className="travel-home-postcard">
          <img
            src="/images/hangzhou.jpg"
            alt="杭州旅行灵感：湖山与茶园风景"
            fetchPriority="high"
          />
          <figcaption>
            <MapPin size={15} /> 灵感目的地 · 杭州
          </figcaption>
          <div className="travel-home-ticket">
            <TripalMark size={96} />
            <div>
              <b>想法交给 {BRAND.name}，</b>
              <span>行程按你的节奏安排。</span>
            </div>
          </div>
        </figure>
      </div>

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
