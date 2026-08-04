"use client";

import { useEffect, useState } from "react";

type TileMediaThumbnailProps = {
  alt: string;
  placeholderDetail?: string;
  placeholderLabel?: string;
  src: string | null | undefined;
};

export function TileMediaThumbnail({
  alt,
  placeholderDetail,
  placeholderLabel = "No thumbnail",
  src
}: TileMediaThumbnailProps) {
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [src]);

  const showImage = Boolean(src) && !failed;

  if (!showImage) {
    return (
      <span className="capture-inbox-thumbnail-placeholder is-missing-media">
        <span aria-hidden="true" className="capture-inbox-thumbnail-placeholder__glyph">
          <svg fill="none" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
            <rect height="28" rx="4" stroke="currentColor" strokeWidth="2" width="36" x="6" y="10" />
            <path d="M14 28l6.5-7 5 5.5 4-3.5L34 28" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
            <circle cx="17.5" cy="17.5" r="2.25" fill="currentColor" />
          </svg>
        </span>
        <strong>{placeholderLabel}</strong>
        {placeholderDetail ? <small>{placeholderDetail}</small> : null}
      </span>
    );
  }

  return <img alt={alt} onError={() => setFailed(true)} src={src!} />;
}
