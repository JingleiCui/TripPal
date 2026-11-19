import { BRAND } from "../brand";
/**
 * TripPal 旅伴 —— 唯一官方 Logo 组件（对应设计稿 page1 slogan 旁的版本）。
 *
 * 全站任何需要展示 Logo 的地方都必须引用本组件，禁止再用 Compass 等图标
 * 临时代替，以保证「方形微圆角行李箱 + 黄色星光 + 居中五官」完全一致。
 *
 * - TripalMark   纯图形（页眉、加载态、路由书封面等）
 * - TripalBrand  图形 + 中英文品牌字标（登录页、页脚等）
 */
export function TripalMark({
  size = 40,
  className,
  title = BRAND.fullName,
}: {
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 120 120"
      role="img"
      aria-label={title}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* 落地阴影 */}
      <ellipse cx="60" cy="108" rx="39" ry="5.5" fill="#F2E3DA" />
      {/* 提手 */}
      <path
        d="M45 34V20a15 15 0 0 1 30 0v14"
        fill="none"
        stroke="#EA6E4E"
        strokeWidth="9"
        strokeLinecap="round"
      />
      <path
        d="M47.5 33V20a12.5 12.5 0 0 1 25 0v13"
        fill="none"
        stroke="#FFB49A"
        strokeWidth="3"
        strokeLinecap="round"
      />
      {/* 箱体：方形 + 微圆角，Jellycat 毛绒质感 */}
      <rect x="19" y="31" width="82" height="70" rx="25" fill="#FF8A6B" />
      <rect
        x="19"
        y="31"
        width="82"
        height="70"
        rx="25"
        fill="none"
        stroke="#F27A5A"
        strokeWidth="1.5"
        strokeDasharray="3 4"
        opacity="0.55"
      />
      {/* 两只小脚 */}
      <rect x="36" y="96" width="17" height="13" rx="6.5" fill="#E9704F" />
      <rect x="67" y="96" width="17" height="13" rx="6.5" fill="#E9704F" />
      {/* 腮红 */}
      <ellipse cx="33" cy="75" rx="7.5" ry="4.2" fill="#FFC2AD" />
      <ellipse cx="87" cy="75" rx="7.5" ry="4.2" fill="#FFC2AD" />
      {/* 眼睛（居中对称于中线 60） */}
      <ellipse cx="47" cy="65" rx="4.3" ry="5.6" fill="#3B3432" />
      <ellipse cx="73" cy="65" rx="4.3" ry="5.6" fill="#3B3432" />
      <circle cx="45.5" cy="63" r="1.4" fill="#FFFFFF" />
      <circle cx="71.5" cy="63" r="1.4" fill="#FFFFFF" />
      {/* 微笑 */}
      <path
        d="M55 76q5 6 10 0"
        fill="none"
        stroke="#3B3432"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      {/* 黄色四角星光 —— 必须是黄色 #FFCE73，不是薄荷绿 */}
      <path
        d="M101 8l3.4 8.6L113 20l-8.6 3.4L101 32l-3.4-8.6L89 20l8.6-3.4z"
        fill="#FFCE73"
      />
    </svg>
  );
}

export function TripalBrand({
  size = 40,
  showSlogan = false,
  light = false,
  className,
}: {
  size?: number;
  showSlogan?: boolean;
  light?: boolean;
  className?: string;
}) {
  return (
    <span className={"tripal-brand" + (light ? " tripal-brand-light" : "") + (className ? " " + className : "")}>
      <TripalMark size={size} />
      <span className="tripal-brand-text">
        <b>
          {BRAND.name}<span className="tripal-brand-cn">{BRAND.nameCn}</span>
        </b>
        {showSlogan && <small>{BRAND.slogan}</small>}
      </span>
    </span>
  );
}
