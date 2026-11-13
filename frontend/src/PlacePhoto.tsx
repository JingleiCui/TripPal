import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";

function imageUrl(value: string) {
  try {
    const url = new URL(value.startsWith("//") ? "https:" + value : value);
    if (
      url.protocol === "http:" &&
      [
        "store.is.autonavi.com",
        "aos-comment.amap.com",
        "aos-cdn-image.amap.com",
      ].includes(url.hostname)
    )
      url.protocol = "https:";
    return url.protocol === "https:" || url.origin === location.origin
      ? url.href
      : "";
  } catch {
    return "";
  }
}

/** Use only the actual place's provider photos; a failed URL advances to its next photo. */
export function PlacePhoto({
  photos,
  alt,
  className = "",
  loading = "lazy",
}: {
  photos?: string[];
  alt: string;
  className?: string;
  loading?: "lazy" | "eager";
}) {
  const urls = Array.from(
    new Set((photos || []).map(imageUrl).filter(Boolean)),
  );
  const photoKey = urls.join("|");
  const [index, setIndex] = useState(0);
  useEffect(() => setIndex(0), [photoKey]);
  const src = urls[index];
  return src ? (
    <img
      key={src}
      className={className}
      src={src}
      alt={alt}
      loading={loading}
      referrerPolicy="no-referrer"
      onError={() => setIndex((i) => i + 1)}
    />
  ) : (
    <span
      className="source-image-fallback"
      role="img"
      aria-label={alt + "暂无实景照片"}
    >
      <ImageOff size={24} />
      <small>暂无实景照片</small>
    </span>
  );
}
