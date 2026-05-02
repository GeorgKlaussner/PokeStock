(() => {
  const prefetched = new Set();
  const idle = window.requestIdleCallback || ((callback) => window.setTimeout(callback, 250));

  function linkURL(link) {
    try {
      return new URL(link.href, window.location.href);
    } catch {
      return null;
    }
  }

  function isPageLink(link) {
    const url = linkURL(link);
    if (!url || url.origin !== window.location.origin) {
      return false;
    }
    if (link.target && link.target !== "_self") {
      return false;
    }
    if (link.hasAttribute("download") || url.pathname.startsWith("/csv/export/")) {
      return false;
    }
    return url.pathname !== window.location.pathname || url.search !== window.location.search;
  }

  function isPrimaryNavigationLink(link) {
    return Boolean(link.closest(".side-nav, .mobile-tabbar"));
  }

  function prefetch(link) {
    if (!isPrimaryNavigationLink(link) || !isPageLink(link)) {
      return;
    }

    const url = linkURL(link);
    const href = url.toString();
    if (prefetched.has(href)) {
      return;
    }
    prefetched.add(href);

    const hint = document.createElement("link");
    hint.rel = "prefetch";
    hint.as = "document";
    hint.href = href;
    document.head.append(hint);
  }

  function prefetchFromEvent(event) {
    if (!(event.target instanceof Element)) {
      return;
    }

    const link = event.target.closest("a[href]");
    if (link) {
      prefetch(link);
    }
  }

  function markNavigating(event) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }

    if (!(event.target instanceof Element)) {
      return;
    }

    const link = event.target.closest("a[href]");
    if (!link || !isPageLink(link)) {
      return;
    }

    document.body.classList.add("is-navigating");
    link.classList.add("is-loading");
    link.setAttribute("aria-busy", "true");
  }

  document.addEventListener("pointerover", prefetchFromEvent);
  document.addEventListener("focusin", prefetchFromEvent);
  document.addEventListener("touchstart", prefetchFromEvent, { passive: true });
  document.addEventListener("click", markNavigating);

  idle(() => {
    document.querySelectorAll(".side-nav a[href], .mobile-tabbar a[href]").forEach(prefetch);
  });
})();
