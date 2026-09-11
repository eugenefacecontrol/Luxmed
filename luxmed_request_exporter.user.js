// ==UserScript==
// @name Luxmed request exporter
// @namespace http://tampermonkey.net/
// @version 2026-09-11
// @description Copy Luxmed appointment search request config for the VM monitor.
// @author You
// @match https://portalpacjenta.luxmed.pl/*
// @require https://jolly-newton-babd42.netlify.app/UsefulScripts.js
// @icon https://www.google.com/s2/favicons?sz=64&domain=luxmed.pl
// @grant GM_setClipboard
// ==/UserScript==

/* global GM_setClipboard */

(function () {
  "use strict";

  const TARGET_PATH = "/PatientPortal/NewPortal/terms/index";
  const STORAGE_KEY = "luxmed:lastTermsRequest";
  const IMPORTANT_COOKIES = [
    "Authorization-Token",
    "XSRF-TOKEN",
    "RefreshToken",
    "LXToken",
    "PatientPortalDeviceId",
    "ASP.NET_SessionId",
    "__RequestVerificationToken_L1BhdGllbnRQb3J0YWw1",
    "incap_ses_688_2269135",
    "incap_ses_692_2269135",
    "nlbi_2269135",
    "visid_incap_2269135",
  ];

  function absoluteUrl(input) {
    try {
      return new URL(input, window.location.origin).toString();
    } catch {
      return null;
    }
  }

  function isTermsUrl(input) {
    const url = absoluteUrl(input);
    return Boolean(url && new URL(url).pathname === TARGET_PATH);
  }

  function parseCookies(header) {
    return Object.fromEntries(
      header
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean)
        .map((part) => {
          const index = part.indexOf("=");
          if (index === -1) return [part, ""];
          return [part.slice(0, index), part.slice(index + 1)];
        })
    );
  }

  function queryObject(url) {
    const params = new URL(url).searchParams;
    const result = {};
    for (const [key, value] of params.entries()) {
      result[key] = value;
    }
    return result;
  }

  function decodeJwtPayload(token) {
    const parts = String(token || "").split(".");
    if (parts.length < 2) return null;
    try {
      const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
      const padded = payload.padEnd(Math.ceil(payload.length / 4) * 4, "=");
      return JSON.parse(atob(padded));
    } catch {
      return null;
    }
  }

  function envQuote(value) {
    return String(value ?? "").replace(/'/g, "'\"'\"'");
  }

  function buildExport(url) {
    const cookieHeader = document.cookie || "";
    const cookies = parseCookies(cookieHeader);
    const cookieNames = Object.keys(cookies);
    const missingVisibleCookies = IMPORTANT_COOKIES.filter((name) => !cookieNames.includes(name));
    const authPayload = decodeJwtPayload(cookies["Authorization-Token"]);
    const tokenExpiresAt =
      authPayload && Number.isInteger(authPayload.exp)
        ? new Date(authPayload.exp * 1000).toISOString()
        : null;

    return {
      capturedAt: new Date().toISOString(),
      requestUrl: url,
      cookieHeader,
      visibleCookieNames: cookieNames,
      missingVisibleCookies,
      tokenExpiresAt,
      importantParams: queryObject(url),
      note:
        missingVisibleCookies.includes("Authorization-Token")
          ? "Authorization-Token is not visible to this userscript. If the bot returns 401/403, copy the full Cookie header manually from DevTools."
          : "Use this as .env on the VM. Refresh it after logging in again or when Luxmed session expires.",
    };
  }

  function toEnv(config) {
    return [
      "TELEGRAM_BOT_TOKEN=",
      "TELEGRAM_CHAT_ID=",
      `LUXMED_REQUEST_URL='${envQuote(config.requestUrl)}'`,
      `LUXMED_COOKIE_HEADER='${envQuote(config.cookieHeader)}'`,
      "LUXMED_DOCTOR_REGEX=",
      "LUXMED_MATCH_TEXT_REGEX=",
      "POLL_INTERVAL_SECONDS=60",
      "NOTIFY_ON_EVERY_MATCH=false",
      "AUTH_EXPIRY_WARN_MINUTES=2",
    ].join("\n");
  }

  function saveRequest(url) {
    const config = buildExport(url);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    renderButton(config);
    console.info("[Luxmed exporter] captured terms request", config);
  }

  function copyConfig() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      alert("Luxmed request not captured yet. Open appointment search results first.");
      return;
    }

    const config = JSON.parse(raw);
    const output = `${toEnv(config)}\n\n# JSON backup:\n# ${JSON.stringify(config)}`;
    GM_setClipboard(output, "text");
    alert("Luxmed .env copied. Paste it on the VM.");
  }

  function renderButton(config) {
    let button = document.getElementById("luxmed-request-exporter-button");
    if (!button) {
      button = document.createElement("button");
      button.id = "luxmed-request-exporter-button";
      button.type = "button";
      button.addEventListener("click", copyConfig);
      Object.assign(button.style, {
        position: "fixed",
        right: "16px",
        bottom: "16px",
        zIndex: "2147483647",
        padding: "10px 12px",
        border: "1px solid #0f766e",
        borderRadius: "6px",
        background: "#0f766e",
        color: "#fff",
        font: "13px/1.2 system-ui, sans-serif",
        boxShadow: "0 4px 16px rgba(0,0,0,.2)",
        cursor: "pointer",
      });
      document.documentElement.appendChild(button);
    }

    const hasAuth = !config.missingVisibleCookies.includes("Authorization-Token");
    button.textContent = hasAuth ? "Copy Luxmed VM env" : "Copy Luxmed env (check auth)";
    button.title = hasAuth
      ? "Copies Docker .env values for Luxmed monitor"
      : "Authorization-Token was not visible; DevTools Cookie header may be needed";
  }

  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const input = args[0];
    const url = typeof input === "string" ? input : input?.url;
    if (isTermsUrl(url)) {
      saveRequest(absoluteUrl(url));
    }
    return originalFetch.apply(this, args);
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    if (isTermsUrl(url)) {
      saveRequest(absoluteUrl(url));
    }
    return originalOpen.call(this, method, url, ...rest);
  };

  document.addEventListener("keydown", (event) => {
    if (typeof event.getHelp === "function") {
      event.getHelp();
    }

    if (event.altKey && event.code === "KeyL") {
      event.preventDefault();
      copyConfig();
    }
  });

  const existing = localStorage.getItem(STORAGE_KEY);
  if (existing) {
    renderButton(JSON.parse(existing));
  }
})();
