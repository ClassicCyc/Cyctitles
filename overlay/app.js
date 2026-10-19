/* Cyctitles overlay renderer. */
(() => {
  "use strict";

  const box = document.getElementById("box");
  const tgtEl = document.getElementById("tgt");
  const srcEl = document.getElementById("src");
  const wrap = document.getElementById("wrap");
  const root = document.documentElement;

  const DEFAULT_CONFIG = {
    opacity: 0.75,
    font_scale: 1.0,
    show_original: false,
    original_scale: 0.6,
    auto_hide_sec: 6.0,
    bottom_margin: 6.0,
    position: "bottom",
    text_color: "#ffffff",
    background: "#000000",
    max_lines: 2,
    outline_width: 0.0,
    outline_color: "#000000",
    shadow: false,
    font_weight: 600,
    animation: "fade",
    animation_duration: 0.25,
  };

  let config = { ...DEFAULT_CONFIG };
  let hideTimer = null;

  function hexToRgb(hex) {
    const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex || "");
    if (!m) return "0, 0, 0";
    return `${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}`;
  }

  function applyConfig() {
    root.style.setProperty("--opacity", config.opacity);
    root.style.setProperty("--bottom", config.bottom_margin);
    root.style.setProperty("--max-lines", config.max_lines);
    root.style.setProperty("--text-color", config.text_color);
    root.style.setProperty("--bg-rgb", hexToRgb(config.background));
    root.style.setProperty("--src-color", `rgba(${hexToRgb(config.text_color)}, 0.72)`);
    root.style.setProperty("--enter-shift", config.position === "top" ? "-10px" : "10px");
    root.style.setProperty("--outline-width", (config.outline_width || 0) + "px");
    root.style.setProperty("--outline-color", config.outline_color || "#000");
    root.style.setProperty("--font-weight", config.font_weight || 600);
    root.style.setProperty("--anim-duration", (config.animation_duration || 0.25) + "s");
    wrap.classList.toggle("bottom", config.position !== "top");
    wrap.classList.toggle("top", config.position === "top");
    box.className = "anim-" + (config.animation || "fade");
    srcEl.hidden = !config.show_original;
    if (tgtEl.textContent) fit();
  }

  function baseSize() {
    return Math.max(18, Math.round(window.innerHeight * 0.045));
  }

  function fit() {
    // Temporarily remove the 2-line clamp so we can measure the natural height.
    tgtEl.style.maxHeight = "none";
    tgtEl.style.setProperty("-webkit-line-clamp", "unset");
    tgtEl.style.setProperty("line-clamp", "unset");

    const maxLines = Math.max(1, config.max_lines || 2);
    const base = baseSize() * config.font_scale;
    const minSize = Math.max(14, Math.round(base * 0.55));
    let size = base;

    while (size > minSize) {
      tgtEl.style.fontSize = size + "px";
      const lineHeight = size * 1.25;
      if (tgtEl.scrollHeight <= lineHeight * maxLines + 2) break;
      size -= 1;
    }
    tgtEl.style.fontSize = size + "px";

    // Restore the CSS clamp.
    tgtEl.style.maxHeight = "";
    tgtEl.style.removeProperty("-webkit-line-clamp");
    tgtEl.style.removeProperty("line-clamp");

    const origSize = Math.max(12, Math.round(baseSize() * config.font_scale * config.original_scale));
    srcEl.style.fontSize = origSize + "px";
  }

  function resetTimer() {
    box.classList.add("visible");
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => box.classList.remove("visible"), config.auto_hide_sec * 1000);
  }

  function showCaption(caption) {
    if (!caption) {
      hide();
      return;
    }
    tgtEl.textContent = caption.tgt || "";
    srcEl.textContent = caption.src || "";
    srcEl.hidden = !config.show_original;
    fit();
    resetTimer();
  }

  function hide() {
    box.classList.remove("visible");
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    let socket;
    try {
      socket = new WebSocket(`${proto}://${location.host}/ws`);
    } catch (err) {
      setTimeout(connect, 1000);
      return;
    }
    let retry = 0;

    socket.onopen = () => {
      retry = 0;
    };
    socket.onmessage = (event) => {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (err) {
        return;
      }
      if (msg.type === "config") {
        config = { ...config, ...msg.config };
        applyConfig();
      } else if (msg.type === "caption") {
        showCaption(msg);
      } else if (msg.type === "clear") {
        hide();
      } else if (msg.type === "state") {
        if (msg.config) {
          config = { ...config, ...msg.config };
          applyConfig();
        }
        if (msg.caption) showCaption(msg.caption);
      }
    };
    socket.onclose = () => {
      retry = Math.min(retry + 1, 8);
      setTimeout(connect, 400 * retry);
    };
    socket.onerror = () => {
      try {
        socket.close();
      } catch (err) {
        /* ignore */
      }
    };
  }

  window.addEventListener("resize", () => {
    if (tgtEl.textContent) fit();
  });

  applyConfig();

  // Preview helper: open with ?text=Some+sample+line
  const params = new URLSearchParams(location.search);
  if (params.has("text")) {
    const sample = params.get("text");
    config.show_original = params.get("original") !== "0";
    applyConfig();
    showCaption({ tgt: sample, src: sample });
  }

  connect();
})();
