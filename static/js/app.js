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
  function toast(message, kind) {
    var box = document.getElementById("toasts");
    if (!box || !message) return;
    var el = document.createElement("div");
    el.className = "alert " + (kind === "error" ? "alert-error" : "alert-success") + " shadow-lg text-sm";
    el.setAttribute("role", "status");
    el.textContent = message;
    box.appendChild(el);
    setTimeout(function () { el.remove(); }, 3500);
  }
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
    btn.classList.add("loading");
    navigator.geolocation.getCurrentPosition(function (pos) {
      btn.classList.remove("loading");
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
      btn.classList.remove("loading");
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
