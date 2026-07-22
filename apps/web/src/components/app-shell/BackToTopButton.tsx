"use client";

import { useEffect, useState } from "react";

export const BACK_TO_TOP_THRESHOLD = 600;

export function BackToTopButton() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const updateVisibility = () => setVisible(window.scrollY >= BACK_TO_TOP_THRESHOLD);
    updateVisibility();
    window.addEventListener("scroll", updateVisibility, { passive: true });
    return () => window.removeEventListener("scroll", updateVisibility);
  }, []);

  if (!visible) return null;

  function scrollToTop() {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const behavior: ScrollBehavior = reduceMotion ? "auto" : "smooth";
    window.scrollTo({ top: 0, behavior });
  }

  return (
    <button
      aria-label="Back to top"
      className="app-back-to-top"
      onClick={scrollToTop}
      title="Back to top"
      type="button"
    >
      <svg aria-hidden="true" viewBox="0 0 20 20">
        <path d="m5.5 11.5 4.5-4.5 4.5 4.5M10 7v7" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
      </svg>
    </button>
  );
}
