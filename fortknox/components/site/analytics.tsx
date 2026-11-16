"use client";

import Script from "next/script";
import { usePathname, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

// Google Analytics 4, the same property as lknox.web.app. Keep
// app/privacy/page.tsx in step with this.
//
// The config call sends the first page view. Later ones are sent here, because
// GA4's enhanced measurement ("page changes based on browser history events")
// never sees this site's navigations: Next's App Router wraps
// history.pushState and drives it from its own reference, so gtag's hook on it
// isn't called, and back/forward weren't counted either (checked with Next 15
// in November 2026). Turn that enhanced measurement option off in the GA data
// stream so a future fix there can't double-count these.
export const GA_ID = "G-6DDQCV2HKQ";

declare global {
  interface Window { gtag?: (...args: unknown[]) => void }
}

function PageViews() {
  const path = usePathname();
  const search = useSearchParams().toString();
  const last = useRef<string | null>(null);
  useEffect(() => {
    const key = search ? `${path}?${search}` : path;
    // The first render is the page load, which the config call already counted.
    if (last.current !== null && last.current !== key) {
      window.gtag?.("event", "page_view", { page_location: window.location.href, page_title: document.title });
    }
    last.current = key;
  }, [path, search]);
  return null;
}

export function Analytics() {
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
      <Script id="ga-init" strategy="afterInteractive">
        {`window.dataLayer = window.dataLayer || [];
function gtag(){dataLayer.push(arguments);}
gtag('js', new Date());
gtag('config', '${GA_ID}');`}
      </Script>
      {/* useSearchParams needs a Suspense boundary in a static export. */}
      <Suspense fallback={null}><PageViews /></Suspense>
    </>
  );
}
