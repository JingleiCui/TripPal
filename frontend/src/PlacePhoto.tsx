import { useEffect, useState } from "react";
import { ImageOff } from "lucide-react";
import { safeImageSrc } from "./lib/safeUrl";

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
    new Set((photos || []).map(safeImageSrc).filter(Boolean)),
  ) as string[];
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
