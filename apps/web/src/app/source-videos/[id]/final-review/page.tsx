"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/** Legacy URL fallback — prefer next.config redirects / production hrefs. */
export default function Page() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;

  useEffect(() => {
    if (!id) return;
    router.replace(`/production/final-review/${encodeURIComponent(id)}`);
  }, [id, router]);

  return <div className="auth-loading">Redirecting…</div>;
}
