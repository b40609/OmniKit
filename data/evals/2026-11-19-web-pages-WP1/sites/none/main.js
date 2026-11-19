(() => {
  const root = document.documentElement;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  root.classList.add("js");

  /* hero: entrance, then the screenshot tilts flat as you scroll */
  const shot = document.getElementById("heroShot");
  if (!reduce) {
    root.classList.add("is-ready");
    requestAnimationFrame(() => requestAnimationFrame(() => root.classList.add("is-loaded")));
    if (shot) {
      let ticking = false;
      const tilt = () => {
        ticking = false;
        const p = Math.min(1, Math.max(0, window.scrollY / (window.innerHeight * 0.55)));
        const small = window.innerWidth <= 734;
        const deg = small ? 0 : (1 - p) * 10;
        const sc = small ? 1 : 0.94 + p * 0.06;
        shot.style.transform = `perspective(2200px) rotateX(${deg.toFixed(2)}deg) scale(${sc.toFixed(4)})`;
      };
      const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(tilt); } };
      window.addEventListener("scroll", onScroll, { passive: true });
      window.addEventListener("resize", onScroll);
      tilt();
    }
  }

  /* reveal on scroll */
  const reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && !reduce) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
      });
    }, { rootMargin: "0px 0px -10% 0px", threshold: 0.06 });
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("is-in"));
  }

  /* tabs with roving tabindex + arrow keys */
  function tabs(list, onChange) {
    const btns = Array.from(list.querySelectorAll('[role="tab"]'));
    const select = (btn, focus) => {
      btns.forEach((b) => {
        const on = b === btn;
        b.setAttribute("aria-selected", String(on));
        b.tabIndex = on ? 0 : -1;
        const pane = document.getElementById(b.getAttribute("aria-controls"));
        if (pane) pane.hidden = !on;
      });
      if (focus) btn.focus();
      if (onChange) onChange(btn);
    };
    btns.forEach((b, i) => {
      b.addEventListener("click", () => select(b));
      b.addEventListener("keydown", (e) => {
        if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
        e.preventDefault();
        select(btns[(i + (e.key === "ArrowRight" ? 1 : btns.length - 1)) % btns.length], true);
      });
    });
    return select;
  }

  /* screenshot showcases (detail types; ask / search / filter) */
  document.querySelectorAll(".showcase__tabs").forEach((list) => {
    tabs(list, (btn) => {
      if (reduce) return;
      const pane = document.getElementById(btn.getAttribute("aria-controls"));
      if (pane) { pane.classList.remove("is-swap"); void pane.offsetWidth; pane.classList.add("is-swap"); }
    });
  });

  /* install OS tabs — default to the visitor's platform */
  const osList = document.querySelector(".term__tabs");
  if (osList) {
    const select = tabs(osList);
    const plat = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "";
    const mobile = /android|iphone|ipad/i.test(navigator.userAgent);
    if (!mobile && /mac|linux|x11|cros/i.test(plat)) select(document.getElementById("os-unix"));
  }

  /* carousel: dots + arrows */
  const rail = document.getElementById("rail");
  if (rail) {
    const cards = Array.from(rail.children);
    const dotsBox = document.querySelector(".rail-ctrl .dots");
    const prev = document.querySelector('.arrow[data-dir="-1"]');
    const next = document.querySelector('.arrow[data-dir="1"]');
    const dots = cards.map((card, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-label", `第 ${i + 1} 張：${card.querySelector(".card__k").textContent}`);
      b.addEventListener("click", () => go(i));
      dotsBox.appendChild(b);
      return b;
    });
    const step = () => cards[1].offsetLeft - cards[0].offsetLeft;
    const current = () => Math.round(rail.scrollLeft / step());
    const go = (i) => rail.scrollTo({ left: Math.max(0, Math.min(cards.length - 1, i)) * step(), behavior: reduce ? "auto" : "smooth" });
    const update = () => {
      const max = rail.scrollWidth - rail.clientWidth - 2;
      const atEnd = rail.scrollLeft >= max;
      const idx = atEnd ? cards.length - 1 : current();
      dots.forEach((d, i) => d.setAttribute("aria-current", String(i === idx)));
      prev.disabled = rail.scrollLeft <= 2;
      next.disabled = atEnd;
    };
    prev.addEventListener("click", () => go(current() - 1));
    next.addEventListener("click", () => go(current() + 1));
    rail.addEventListener("scroll", () => requestAnimationFrame(update), { passive: true });
    window.addEventListener("resize", update);
    update();
  }

  /* copy buttons */
  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
      ta.remove();
      return ok;
    }
  }
  document.querySelectorAll(".copy").forEach((btn) => {
    const label = btn.textContent;
    btn.addEventListener("click", async () => {
      let text = btn.dataset.copy;
      if (!text && btn.dataset.copyFrom) {
        const cmd = document.querySelector(`#${btn.dataset.copyFrom} .cmd`);
        text = cmd ? cmd.textContent : "";
      }
      const ok = await copyText(text || "");
      btn.textContent = ok ? "已複製" : "請手動選取";
      btn.classList.toggle("is-done", ok);
      setTimeout(() => { btn.textContent = label; btn.classList.remove("is-done"); }, 1800);
    });
  });
})();
