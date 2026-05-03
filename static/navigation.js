(() => {
  const prefetched = new Set();
  const idle = window.requestIdleCallback || ((callback) => window.setTimeout(callback, 250));
  const scrollKey = `pokestock:scroll:${window.location.pathname}${window.location.search}`;

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

  function rememberScroll(event) {
    if (!(event.target instanceof Element)) {
      return;
    }

    const form = event.target.closest("form[data-preserve-scroll]");
    if (!form) {
      return;
    }

    sessionStorage.setItem(scrollKey, String(Math.max(0, Math.round(window.scrollY))));
  }

  function restoreScroll() {
    const value = sessionStorage.getItem(scrollKey);
    if (value === null) {
      return;
    }
    sessionStorage.removeItem(scrollKey);

    const offset = Number.parseInt(value, 10);
    if (!Number.isFinite(offset)) {
      return;
    }

    const scrollToOffset = () => window.scrollTo({ top: offset, left: 0, behavior: "instant" });
    window.requestAnimationFrame(scrollToOffset);
    window.setTimeout(scrollToOffset, 80);
  }

  document.addEventListener("pointerover", prefetchFromEvent);
  document.addEventListener("focusin", prefetchFromEvent);
  document.addEventListener("touchstart", prefetchFromEvent, { passive: true });
  document.addEventListener("click", markNavigating);
  document.addEventListener("submit", rememberScroll);

  idle(() => {
    document.querySelectorAll(".side-nav a[href], .mobile-tabbar a[href]").forEach(prefetch);
  });

  restoreScroll();
})();
