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

  function doctorName(term) {
    const doctor = term?.doctor || {};
    return [doctor.academicTitle, doctor.firstName, doctor.lastName]
      .map((part) => String(part || "").trim())
      .filter(Boolean)
      .join(" ");
  }

  function summarizeTermsResponse(payload) {
    const service = payload?.termsForService;
    if (!service || typeof service !== "object") {
      return null;
    }

    const terms = [];
    for (const day of service.termsForDays || []) {
      for (const term of day?.terms || []) {
        terms.push({
          dateTimeFrom: term.dateTimeFrom,
          dateTimeTo: term.dateTimeTo,
          doctorName: doctorName(term),
          doctorId: term.doctor?.id ?? null,
          clinic: term.clinic,
          clinicGroup: term.clinicGroup,
          clinicId: term.clinicId,
          roomId: term.roomId,
          serviceId: term.serviceId ?? service.serviceVariantId,
          scheduleId: term.scheduleId,
          isTelemedicine: Boolean(term.isTelemedicine),
          correlationId: day?.correlationId ?? payload?.correlationId ?? null,
        });
      }
    }

    const dayStatuses = (service.termsInfoForDays || []).map((day) => ({
      day: day.day,
      termsStatus: day.termsStatus,
      termsNumber: day.termsCounter?.termsNumber ?? null,
      message: day.message,
    }));

    return {
      success: payload?.success ?? null,
      correlationId: payload?.correlationId ?? null,
      serviceVariantId: service.serviceVariantId,
      termsCount: terms.length,
      termsPreview: terms.slice(0, 20),
      dayStatuses,
    };
  }

  function buildExport(url, source, responsePayload = null) {
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
      source,
      requestUrl: url,
      cookieHeader,
      visibleCookieNames: cookieNames,
      missingVisibleCookies,
      tokenExpiresAt,
      importantParams: queryObject(url),
      responseSummary: summarizeTermsResponse(responsePayload),
      note:
        missingVisibleCookies.includes("Authorization-Token")
          ? "Authorization-Token is not visible to this userscript. If the bot returns 401/403, copy the full Cookie header manually from DevTools."
          : "Use this as .env on the VM. Refresh it after logging in again or when Luxmed session expires.",
    };
  }

  function toEnv(config) {
    const lines = [`LUXMED_REQUEST_URL='${envQuote(config.requestUrl)}'`];
    if (config.cookieHeader) {
      lines.push(
        "",
        "# Optional fallback only. Prefer LUXMED_LOGIN/LUXMED_PASSWORD; uncomment only if Luxmed blocks login/fetch without browser session cookies.",
        `# LUXMED_COOKIE_HEADER='${envQuote(config.cookieHeader)}'`
      );
    }
    return lines.join("\n");
  }

  function saveRequest(url, source = "network", responsePayload = null) {
    if (!url) return false;

    const config = buildExport(url, source, responsePayload);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    renderButton(config);
    console.info("[Luxmed exporter] captured terms request", config);
    return true;
  }

  function findTermsRequestInPerformance() {
    const entries = performance.getEntriesByType("resource");
    for (let index = entries.length - 1; index >= 0; index -= 1) {
      const url = entries[index].name;
      if (isTermsUrl(url)) {
        return absoluteUrl(url);
      }
    }
    return null;
  }

  function scanAlreadyLoadedRequests() {
    const url = findTermsRequestInPerformance();
    if (url) {
      saveRequest(url, "performance");
      return true;
    }
    return false;
  }

  function copyConfig() {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      scanAlreadyLoadedRequests();
    }

    const updatedRaw = localStorage.getItem(STORAGE_KEY);
    if (!updatedRaw) {
      alert("Luxmed cookies are visible, but appointment request URL was not captured. Click Search in Luxmed again, then press Alt+L.");
      return;
    }

    const config = JSON.parse(updatedRaw);
    if (!config.requestUrl) {
      alert("Appointment request URL is missing. Click Search in Luxmed again, then press Alt+L.");
      return;
    }

    const responseNote = config.responseSummary
      ? `\n# Captured terms: ${config.responseSummary.termsCount}`
      : "\n# Captured terms: not available yet; click Search again if you want response summary.";
    const output = `${toEnv(config)}${responseNote}\n\n# JSON backup:\n# ${JSON.stringify(config)}`;
    GM_setClipboard(output, "text");
    alert(`Luxmed request URL copied. Terms in last response: ${config.responseSummary?.termsCount ?? "unknown"}. Cookie header is included only as a commented fallback.`);
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
    const hasRequest = Boolean(config.requestUrl);
    button.textContent = hasRequest
      ? hasAuth
        ? "Copy Luxmed VM env"
        : "Copy Luxmed env (check auth)"
      : "Luxmed: click Search";
    button.title = hasAuth
        ? "Copies Docker .env request URL for Luxmed monitor"
        : "Cookie header is optional fallback; login/password should generate Authorization-Token";
  }

  const originalFetch = window.fetch;
  window.fetch = function (...args) {
    const input = args[0];
    const url = typeof input === "string" ? input : input?.url;
    const termsUrl = isTermsUrl(url) ? absoluteUrl(url) : null;
    return originalFetch.apply(this, args).then((response) => {
      if (termsUrl) {
        response
          .clone()
          .json()
          .then((payload) => saveRequest(termsUrl, "fetch", payload))
          .catch(() => saveRequest(termsUrl, "fetch"));
      }
      return response;
    });
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    const termsUrl = isTermsUrl(url) ? absoluteUrl(url) : null;
    if (termsUrl) {
      this.addEventListener("load", () => {
        let payload = null;
        try {
          payload = JSON.parse(this.responseText);
        } catch {
          payload = null;
        }
        saveRequest(termsUrl, "xmlhttprequest", payload);
      });
      saveRequest(termsUrl, "xmlhttprequest-open");
    }
    return originalOpen.call(this, method, url, ...rest);
  };

  if ("PerformanceObserver" in window) {
    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (isTermsUrl(entry.name)) {
            saveRequest(absoluteUrl(entry.name), "performance-observer");
          }
        }
      });
      observer.observe({ entryTypes: ["resource"] });
    } catch (error) {
      console.debug("[Luxmed exporter] PerformanceObserver unavailable", error);
    }
  }

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
  } else {
    renderButton({ requestUrl: null, missingVisibleCookies: IMPORTANT_COOKIES });
    scanAlreadyLoadedRequests();
  }
})();
