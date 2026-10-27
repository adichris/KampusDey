/* KampusDey: small progressive-enhancement helpers. No framework, CSP friendly. */
(function () {
  "use strict";
  var THEME_KEY = "kd-theme";
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");

  function csrf() {
    var el = document.querySelector("meta[name=csrf-token]");
    return el ? el.content : "";
  }

  // ---------------------------------------------------------------- theme
  function resolve(theme) {
    if (!theme || theme === "system") return media.matches ? "kampusdey-dark" : "kampusdey";
    return theme;
  }
  function chosenTheme() {
    var server = root.getAttribute("data-user-theme");
    if (server) return server;
    try { return localStorage.getItem(THEME_KEY) || "system"; } catch (e) { return "system"; }
  }
  function applyTheme(theme) {
    root.setAttribute("data-theme", resolve(theme));
    root.setAttribute("data-chosen-theme", theme || "system");
    document.querySelectorAll("[data-theme-choice]").forEach(function (btn) {
      var on = btn.getAttribute("data-theme-choice") === (theme || "system");
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.classList.toggle("ring-2", on);
      btn.classList.toggle("ring-primary", on);
    });
  }
  media.addEventListener("change", function () {
    if ((root.getAttribute("data-chosen-theme") || "system") === "system") applyTheme("system");
  });
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-theme-choice]");
    if (!btn) return;
    var theme = btn.getAttribute("data-theme-choice");
    if (root.hasAttribute("data-user-theme")) {
      root.setAttribute("data-user-theme", theme);
      var body = new URLSearchParams({ theme: theme });
      fetch(btn.getAttribute("data-theme-url") || "/accounts/theme/", {
        method: "POST",
        headers: { "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" },
        body: body,
        credentials: "same-origin",
      });
    } else {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* private mode */ }
    }
    applyTheme(theme);
    toast(btn.getAttribute("data-saved-text") || "Theme saved");
  });

  // ---------------------------------------------------------------- dialogs / bottom sheets
  document.addEventListener("click", function (ev) {
    var opener = ev.target.closest("[data-open-dialog]");
    if (opener) {
      var dlg = document.getElementById(opener.getAttribute("data-open-dialog"));
      if (dlg && dlg.showModal) { ev.preventDefault(); dlg.showModal(); }
    }
    var closer = ev.target.closest("[data-close-dialog]");
    if (closer) {
      var d = closer.closest("dialog");
      if (d) d.close();
    }
  });

  // ---------------------------------------------------------------- toasts
  var TOAST_CLASS = { error: "alert-error", warning: "alert-warning", info: "alert-info", success: "alert-success" };

  function dismissToast(el) {
    if (!el || el.dataset.leaving) return;
    el.dataset.leaving = "1";
    el.classList.add("kd-toast-leave");
    setTimeout(function () { el.remove(); }, 200);
  }
  function scheduleToast(el) {
    // Errors and warnings stay longer so there is time to read them.
    var kind = el.getAttribute("data-toast") || "success";
    var ms = kind === "error" || kind === "warning" ? 7000 : 4000;
    setTimeout(function () { dismissToast(el); }, ms);
  }
  function toast(message, kind) {
    var box = document.getElementById("toasts");
    if (!box || !message) return;
    kind = TOAST_CLASS[kind] ? kind : "success";
    var el = document.createElement("div");
    el.className = "alert " + TOAST_CLASS[kind] + " shadow-lg text-sm kd-toast";
    el.setAttribute("role", kind === "error" ? "alert" : "status");
    el.setAttribute("data-toast", kind);
    var text = document.createElement("span");
    text.textContent = message;
    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn btn-ghost btn-xs btn-circle";
    close.setAttribute("data-toast-close", "");
    close.setAttribute("aria-label", "Close");
    close.textContent = "✕";
    el.appendChild(text);
    el.appendChild(close);
    box.appendChild(el);
    scheduleToast(el);
  }
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-toast-close]");
    if (btn) dismissToast(btn.closest("[data-toast]"));
  });
  // Django messages are rendered server-side into #toasts; give them the same lifetime.
  document.querySelectorAll("#toasts [data-toast]").forEach(scheduleToast);

  // ---------------------------------------------------------------- loading feedback
  // A spinner on the clicked button (forms, HTMX requests, button-style links) and a thin
  // progress bar for page navigations. Opt out with data-no-spinner.
  function setBusy(el, on) {
    if (!el || el.hasAttribute("data-no-spinner")) return;
    if (on) {
      if (el.dataset.kdBusy) return;
      el.dataset.kdBusy = "1";
      el.setAttribute("aria-busy", "true");
      el.classList.add("kd-busy");
      var spin = document.createElement("span");
      spin.className = "loading loading-spinner loading-sm kd-spinner";
      spin.setAttribute("aria-hidden", "true");
      el.prepend(spin);
      // Disable on the next tick so the clicked button's name/value is still submitted.
      setTimeout(function () { if (el.dataset.kdBusy && el.tagName === "BUTTON") el.disabled = true; }, 0);
    } else {
      if (!el.dataset.kdBusy) return;
      delete el.dataset.kdBusy;
      el.removeAttribute("aria-busy");
      el.classList.remove("kd-busy");
      var s = el.querySelector(":scope > .kd-spinner");
      if (s) s.remove();
      if (el.tagName === "BUTTON") el.disabled = false;
    }
  }
  window.kdSetBusy = setBusy;

  var bar = null;
  function progress(on) {
    bar = bar || document.getElementById("kd-progress");
    if (!bar) return;
    bar.classList.toggle("kd-progress-active", !!on);
  }

  function isPlainNavigation(ev, a) {
    if (ev.defaultPrevented || ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return false;
    if (!a.href || a.target === "_blank" || a.hasAttribute("download") || a.hasAttribute("data-share")) return false;
    if (a.hasAttribute("hx-get") || a.hasAttribute("hx-post") || a.hasAttribute("data-open-dialog")) return false;
    var url = new URL(a.href, location.href);
    if (url.origin !== location.origin) return false;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return false;
    return url.protocol === "http:" || url.protocol === "https:";
  }

  // Full-page form submits (HTMX forms are handled by the htmx events below).
  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    if (ev.defaultPrevented || form.hasAttribute("hx-post") || form.hasAttribute("hx-get")) return;
    if (form.method && form.method.toLowerCase() === "dialog") return;
    if (form.target === "_blank") return;  // e.g. WhatsApp/Telegram open a new tab
    setBusy(ev.submitter || form.querySelector("[type=submit]"), true);
    progress(true);
  });

  // Links: the progress bar for every same-tab navigation, a spinner on button-style links.
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest("a[href]");
    if (!a || !isPlainNavigation(ev, a)) return;
    // Let other click handlers (share, dialogs) decide first.
    setTimeout(function () {
      if (ev.defaultPrevented) return;
      if (a.classList.contains("btn")) setBusy(a, true);
      progress(true);
    }, 0);
  });

  // HTMX: spinner on the element the user clicked; background polling stays silent.
  function htmxTrigger(ev) {
    var elt = ev.detail && ev.detail.elt;
    if (!elt) return null;
    if (elt.tagName === "FORM") return elt.querySelector("[type=submit]");
    if (elt.matches("button, .btn")) return elt;
    return null;
  }
  document.addEventListener("htmx:beforeRequest", function (ev) {
    var trig = ev.detail.requestConfig && ev.detail.requestConfig.triggeringEvent;
    if (trig && trig.type !== "click" && trig.type !== "submit") return;
    setBusy(htmxTrigger(ev), true);
  });
  document.addEventListener("htmx:afterRequest", function (ev) { setBusy(htmxTrigger(ev), false); });
  // When HTMX swaps a busy button out, its settle step can copy the old classes onto the new
  // element; anything carrying the busy class without our marker is stale.
  document.addEventListener("htmx:afterSettle", function () {
    document.querySelectorAll(".kd-busy:not([data-kd-busy])").forEach(function (el) {
      el.classList.remove("kd-busy");
      el.removeAttribute("aria-busy");
    });
  });

  // Coming back with the Back button restores the page from cache: clear busy states.
  window.addEventListener("pageshow", function () {
    progress(false);
    document.querySelectorAll("[data-kd-busy]").forEach(function (el) { setBusy(el, false); });
  });
  window.kdToast = toast;
  document.body && document.body.addEventListener("showToast", function (ev) {
    var d = ev.detail || {};
    toast(d.value || d.message, d.kind);
  });
  document.addEventListener("htmx:responseError", function (ev) {
    var xhr = ev.detail.xhr;
    if (xhr && xhr.status === 429) toast("Too many requests — please wait a minute.", "error");
  });

  // ---------------------------------------------------------------- share
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-share]");
    if (!btn) return;
    ev.preventDefault();
    var url = btn.getAttribute("data-share");
    var title = btn.getAttribute("data-share-title") || document.title;
    var log = btn.getAttribute("data-share-log");
    function logged(channel) {
      if (log) fetch(log, { method: "POST", headers: { "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" }, body: "channel=" + channel, credentials: "same-origin" });
    }
    if (navigator.share) {
      navigator.share({ title: title, url: url }).then(function () { logged("native"); }).catch(function () {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(function () { toast(btn.getAttribute("data-copied-text") || "Link copied"); logged("copy"); });
    }
  });
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest("[data-share-log-click]");
    if (!a) return;
    fetch(a.getAttribute("data-share-log-click"), { method: "POST", headers: { "X-CSRFToken": csrf(), "Content-Type": "application/x-www-form-urlencoded" }, body: "channel=" + (a.getAttribute("data-channel") || "link"), credentials: "same-origin" });
  });

  // ---------------------------------------------------------------- geolocation
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-geolocate]");
    if (!btn) return;
    ev.preventDefault();
    if (!navigator.geolocation) { toast(btn.getAttribute("data-unsupported") || "Location not available", "error"); return; }
    setBusy(btn, true);
    navigator.geolocation.getCurrentPosition(function (pos) {
      setBusy(btn, false);
      var lat = pos.coords.latitude.toFixed(5), lng = pos.coords.longitude.toFixed(5);
      var url = btn.getAttribute("data-geolocate");
      var target = btn.getAttribute("data-target");
      var sep = url.indexOf("?") === -1 ? "?" : "&";
      if (target && window.htmx) {
        window.htmx.ajax("GET", url + sep + "lat=" + lat + "&lng=" + lng, { target: target, swap: "innerHTML" });
      } else {
        window.location = url + sep + "lat=" + lat + "&lng=" + lng;
      }
    }, function () {
      setBusy(btn, false);
      toast(btn.getAttribute("data-denied") || "We couldn't get your location", "error");
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 });
  });

  // ---------------------------------------------------------------- photo uploader (client-side resize)
  function resize(file, maxEdge) {
    return new Promise(function (resolve) {
      if (!file.type || file.type.indexOf("image/") !== 0 || !window.createImageBitmap) return resolve(file);
      createImageBitmap(file).then(function (bmp) {
        var scale = Math.min(1, maxEdge / Math.max(bmp.width, bmp.height));
        if (scale === 1 && file.size < 1500000) return resolve(file);
        var canvas = document.createElement("canvas");
        canvas.width = Math.round(bmp.width * scale);
        canvas.height = Math.round(bmp.height * scale);
        canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (blob) { resolve(blob ? new File([blob], "photo.jpg", { type: "image/jpeg" }) : file); }, "image/jpeg", 0.85);
      }).catch(function () { resolve(file); });
    });
  }
  function uploadFiles(zone, files) {
    var url = zone.getAttribute("data-upload-url");
    var status = zone.querySelector("[data-upload-status]");
    var list = Array.prototype.slice.call(files);
    var chain = Promise.resolve();
    list.forEach(function (file) {
      chain = chain.then(function () { return resize(file, 2000); }).then(function (f) {
        var fd = new FormData();
        fd.append("photo", f, f.name || "photo.jpg");
        if (status) status.textContent = (zone.getAttribute("data-uploading") || "Uploading…");
        return fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf(), "HX-Request": "true" }, body: fd, credentials: "same-origin" })
          .then(function (r) { return r.text().then(function (t) { return { ok: r.ok, text: t }; }); })
          .then(function (res) {
            var target = document.getElementById(zone.getAttribute("data-target"));
            if (res.ok && target) { target.innerHTML = res.text; if (window.htmx) window.htmx.process(target); }
            else if (!res.ok) { toast(res.text.replace(/<[^>]+>/g, "").trim() || "Upload failed", "error"); }
          });
      });
    });
    chain.then(function () { if (status) status.textContent = ""; });
  }
  document.addEventListener("change", function (ev) {
    var input = ev.target.closest("[data-photo-input]");
    if (input && input.files.length) {
      uploadFiles(input.closest("[data-upload-url]"), input.files);
      input.value = "";
    }
  });
  document.addEventListener("dragover", function (ev) {
    var zone = ev.target.closest("[data-upload-url]");
    if (zone) { ev.preventDefault(); zone.classList.add("border-primary"); }
  });
  document.addEventListener("dragleave", function (ev) {
    var zone = ev.target.closest("[data-upload-url]");
    if (zone) zone.classList.remove("border-primary");
  });
  document.addEventListener("drop", function (ev) {
    var zone = ev.target.closest("[data-upload-url]");
    if (zone && ev.dataTransfer && ev.dataTransfer.files.length) {
      ev.preventDefault();
      zone.classList.remove("border-primary");
      uploadFiles(zone, ev.dataTransfer.files);
    }
  });

  // ---------------------------------------------------------------- service worker + push opt-in
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); });
  }
  document.addEventListener("click", function (ev) {
    var btn = ev.target.closest("[data-enable-push]");
    if (!btn || !("serviceWorker" in navigator) || !window.PushManager) return;
    ev.preventDefault();
    var key = btn.getAttribute("data-vapid");
    function b64(s) { var p = "=".repeat((4 - (s.length % 4)) % 4); var raw = atob((s + p).replace(/-/g, "+").replace(/_/g, "/")); return Uint8Array.from(raw, function (c) { return c.charCodeAt(0); }); }
    navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
    }).then(function (sub) {
      var json = sub.toJSON();
      var browser = (navigator.userAgent.match(/(firefox|edg|chrome|safari)/i) || ["chrome"])[0].toLowerCase();
      return fetch("/webpush/save_information", {
        method: "POST", credentials: "same-origin",
        headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" },
        body: JSON.stringify({ status_type: "subscribe", subscription: json, browser: browser, user_agent: navigator.userAgent }),
      });
    }).then(function () { toast(btn.getAttribute("data-done") || "Push notifications on"); })
      .catch(function () { toast("Push notifications are blocked in this browser", "error"); });
  });

  // ---------------------------------------------------------------- searchable selects
  // Long <select>s (campus, town, area, category…) become a type-to-search combobox. The
  // original select stays in the form, hidden, and is kept in sync, so server code is unchanged.
  // Applies to selects with more than 12 options or data-searchable; opt out with data-no-search.
  var COMBO_MIN_OPTIONS = 12;
  var COMBO_MAX_RESULTS = 60;

  function fold(text) {
    return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function enhanceSelect(sel) {
    if (sel.dataset.kdCombo || sel.hasAttribute("data-no-search")) return;
    var options = Array.prototype.filter.call(sel.options, function (o) { return o.value !== ""; });
    if (options.length <= COMBO_MIN_OPTIONS && !sel.hasAttribute("data-searchable")) return;
    sel.dataset.kdCombo = "1";
    var multiple = sel.multiple;
    var uid = (sel.id || "kd-select-" + Math.random().toString(36).slice(2)) + "-combo";
    var emptyOption = Array.prototype.find.call(sel.options, function (o) { return o.value === ""; });
    var items = options.map(function (o) {
      var group = o.parentElement && o.parentElement.tagName === "OPTGROUP" ? o.parentElement.label : "";
      return { opt: o, text: o.text, group: group, key: fold(o.text + " " + group) };
    });

    var wrap = document.createElement("div");
    wrap.className = "kd-combo relative w-full";
    var chips = document.createElement("div");
    chips.className = "flex flex-wrap gap-1 mb-1 hidden";
    var input = document.createElement("input");
    input.type = "text";
    input.id = uid;
    input.autocomplete = "off";
    input.className = "input input-bordered w-full";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-controls", uid + "-list");
    input.placeholder = sel.getAttribute("data-placeholder") || (multiple ? "Type to search and add…" : "Type to search…");
    var list = document.createElement("ul");
    list.id = uid + "-list";
    list.setAttribute("role", "listbox");
    list.className = "kd-combo-list absolute z-40 left-0 right-0 mt-1 max-h-64 overflow-y-auto rounded-box border border-base-300 bg-base-100 shadow-lg p-1 hidden";
    if (multiple) list.setAttribute("aria-multiselectable", "true");

    // Point the field's <label> at the new input, and move "required" to it so the hidden
    // select never blocks submission with an unfocusable validation error.
    if (sel.id) {
      var label = document.querySelector('label[for="' + sel.id + '"]');
      if (label) label.htmlFor = uid;
    }
    if (sel.required && !multiple) { input.required = true; sel.required = false; }
    sel.classList.add("hidden");
    sel.tabIndex = -1;
    sel.setAttribute("aria-hidden", "true");
    wrap.appendChild(chips);
    wrap.appendChild(input);
    wrap.appendChild(list);
    sel.insertAdjacentElement("afterend", wrap);

    var active = -1;
    var shown = [];

    function selectedText() {
      var o = sel.options[sel.selectedIndex];
      return o && o.value !== "" ? o.text : "";
    }
    function renderChips() {
      if (!multiple) return;
      chips.innerHTML = "";
      items.forEach(function (it) {
        if (!it.opt.selected) return;
        var chip = document.createElement("button");
        chip.type = "button";
        chip.className = "badge badge-primary gap-1 h-auto py-1";
        chip.setAttribute("aria-label", "Remove " + it.text);
        chip.textContent = it.text + " ✕";
        chip.addEventListener("click", function () { it.opt.selected = false; changed(); renderChips(); });
        chips.appendChild(chip);
      });
      chips.classList.toggle("hidden", !chips.childElementCount);
    }
    function changed() { sel.dispatchEvent(new Event("change", { bubbles: true })); }
    function open() { list.classList.remove("hidden"); input.setAttribute("aria-expanded", "true"); }
    function close() {
      list.classList.add("hidden");
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      active = -1;
    }
    function render() {
      var q = fold(input.value.trim());
      var terms = q.split(/\s+/).filter(Boolean);
      // When the box shows the current choice, list everything rather than just that option.
      if (!multiple && input.value === selectedText()) terms = [];
      shown = items.filter(function (it) {
        return terms.every(function (t) { return it.key.indexOf(t) !== -1; });
      }).slice(0, COMBO_MAX_RESULTS);
      list.innerHTML = "";
      if (!shown.length) {
        var none = document.createElement("li");
        none.className = "px-3 py-2 text-sm opacity-60";
        none.textContent = "No matches";
        list.appendChild(none);
      }
      var lastGroup = null;
      shown.forEach(function (it, i) {
        if (it.group && it.group !== lastGroup) {
          var head = document.createElement("li");
          head.className = "px-3 pt-2 pb-1 text-xs font-bold uppercase opacity-60";
          head.setAttribute("role", "presentation");
          head.textContent = it.group;
          list.appendChild(head);
          lastGroup = it.group;
        }
        var li = document.createElement("li");
        li.id = uid + "-opt-" + i;
        li.setAttribute("role", "option");
        li.setAttribute("aria-selected", it.opt.selected ? "true" : "false");
        li.className = "kd-combo-option flex items-center justify-between gap-2 rounded-field px-3 py-2 text-sm cursor-pointer" +
          (i === active ? " bg-primary text-primary-content" : " hover:bg-base-200") + (it.opt.selected ? " font-semibold" : "");
        li.textContent = it.text;
        if (it.opt.selected) {
          var tick = document.createElement("span");
          tick.textContent = "✓";
          tick.setAttribute("aria-hidden", "true");
          li.appendChild(tick);
        }
        li.addEventListener("mousedown", function (ev) { ev.preventDefault(); choose(it); });
        list.appendChild(li);
      });
      if (active >= 0 && shown[active]) {
        input.setAttribute("aria-activedescendant", uid + "-opt-" + active);
        var el = document.getElementById(uid + "-opt-" + active);
        if (el) el.scrollIntoView({ block: "nearest" });
      }
    }
    function choose(it) {
      if (multiple) {
        it.opt.selected = !it.opt.selected;
        input.value = "";
        renderChips();
        changed();
        render();
        input.focus();
      } else {
        sel.value = it.opt.value;
        input.value = it.text;
        close();
        changed();
      }
    }
    function restore() {
      if (multiple) { input.value = ""; return; }
      if (input.value.trim() === "" && emptyOption) {
        if (sel.value !== "") { sel.value = ""; changed(); }
        return;
      }
      input.value = selectedText();
    }

    input.addEventListener("focus", function () { active = -1; render(); open(); });
    input.addEventListener("input", function () { active = 0; open(); render(); });
    input.addEventListener("blur", function () { setTimeout(function () { close(); restore(); }, 120); });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        if (list.classList.contains("hidden")) { open(); render(); }
        if (!shown.length) return;
        active = ev.key === "ArrowDown" ? Math.min(active + 1, shown.length - 1) : Math.max(active - 1, 0);
        render();
      } else if (ev.key === "Enter") {
        if (!list.classList.contains("hidden") && shown[active]) { ev.preventDefault(); choose(shown[active]); }
      } else if (ev.key === "Escape") {
        if (!list.classList.contains("hidden")) { ev.preventDefault(); close(); restore(); }
      } else if (ev.key === "Backspace" && multiple && input.value === "") {
        var last = items.filter(function (it) { return it.opt.selected; }).pop();
        if (last) { last.opt.selected = false; renderChips(); changed(); }
      }
    });
    // Keep in sync if code (or a form reset) changes the hidden select.
    sel.addEventListener("change", function () { if (document.activeElement !== input) { input.value = multiple ? "" : selectedText(); renderChips(); } });

    input.value = multiple ? "" : selectedText();
    renderChips();
  }

  function enhanceSelects(scope) {
    (scope || document).querySelectorAll("select").forEach(enhanceSelect);
  }
  document.addEventListener("htmx:afterSettle", function (ev) { enhanceSelects(ev.target); });
  enhanceSelects();

  // Selects that submit their form on change (e.g. "Sort").
  document.addEventListener("change", function (ev) {
    var sel = ev.target.closest && ev.target.closest("select[data-autosubmit]");
    if (sel && sel.form) sel.form.requestSubmit();
  });

  // ---------------------------------------------------------------- Photo gallery
  // Fixed-height frame with swipe (native scroll-snap), arrows, thumbnails, keys and full screen.
  function galleryIndex(track) {
    return Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
  }
  function galleryGo(gallery, i) {
    var track = gallery.querySelector("[data-gallery-track]");
    var n = track.children.length;
    i = (i + n) % n;
    track.scrollTo({ left: i * track.clientWidth });
    gallerySync(gallery, i);
  }
  function gallerySync(gallery, i) {
    var count = gallery.querySelector("[data-gallery-count]");
    if (count) count.textContent = i + 1;
    gallery.querySelectorAll("[data-gallery-thumb]").forEach(function (t) {
      var on = Number(t.dataset.galleryThumb) === i;
      t.setAttribute("aria-current", on ? "true" : "false");
      if (on) t.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }
  function galleryFull(gallery, on) {
    var track = gallery.querySelector("[data-gallery-track]");
    var i = galleryIndex(track);
    gallery.classList.toggle("kd-gallery-full", on);
    gallery.querySelector("[data-gallery-close]").classList.toggle("hidden", !on);
    document.documentElement.classList.toggle("kd-no-scroll", on);
    // the frame changed width: stay on the same photo
    track.style.scrollBehavior = "auto";
    track.scrollLeft = i * track.clientWidth;
    track.style.scrollBehavior = "";
    if (on) track.focus();
  }
  document.querySelectorAll("[data-gallery]").forEach(function (gallery) {
    var track = gallery.querySelector("[data-gallery-track]");
    var timer;
    track.addEventListener("scroll", function () {
      clearTimeout(timer);
      timer = setTimeout(function () { gallerySync(gallery, galleryIndex(track)); }, 80);
    }, { passive: true });
    gallery.addEventListener("click", function (ev) {
      var t = ev.target.closest("[data-gallery-prev],[data-gallery-next],[data-gallery-thumb],[data-gallery-zoom],[data-gallery-close]");
      if (!t) return;
      var i = galleryIndex(track);
      if (t.hasAttribute("data-gallery-prev")) galleryGo(gallery, i - 1);
      else if (t.hasAttribute("data-gallery-next")) galleryGo(gallery, i + 1);
      else if (t.hasAttribute("data-gallery-thumb")) galleryGo(gallery, Number(t.dataset.galleryThumb));
      else if (t.hasAttribute("data-gallery-close")) galleryFull(gallery, false);
      else galleryFull(gallery, !gallery.classList.contains("kd-gallery-full"));
    });
    gallery.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowLeft") { ev.preventDefault(); galleryGo(gallery, galleryIndex(track) - 1); }
      else if (ev.key === "ArrowRight") { ev.preventDefault(); galleryGo(gallery, galleryIndex(track) + 1); }
      else if (ev.key === "Escape" && gallery.classList.contains("kd-gallery-full")) galleryFull(gallery, false);
    });
  });

  // ---------------------------------------------------------------- Alpine (CSP build) components
  document.addEventListener("alpine:init", function () {
    window.Alpine.data("disclosure", function () {
      return {
        open: false,
        toggle: function () { this.open = !this.open; },
        close: function () { this.open = false; },
      };
    });
  });

  applyTheme(chosenTheme());
})();
