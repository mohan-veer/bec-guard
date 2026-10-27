// Pure logic for the BEC Guard Gmail add-on. No Apps Script services here, so it runs (and is tested) in Node too.
// In Apps Script all files share one global scope; the module.exports line at the bottom is ignored there.

var LABEL_NAMES = { verify: "BEC Guard/Verify before paying", unusual: "BEC Guard/Looks unusual" };
var SCAN_OVERLAP_SECONDS = 120; // re-query a little before the last run so nothing slips between runs
var FIRST_RUN_LOOKBACK_SECONDS = 3600;

function normalizeBaseUrl(url) {
  var u = String(url || "").trim().replace(/\/+$/, "");
  if (!/^https:\/\/[^\s/]+/.test(u)) throw new Error("The BEC Guard URL must start with https://");
  return u;
}

// Gmail search queries for new mail since the last scan (epoch seconds). Spam is included (scam mail often lands
// there), and so is new mail that skipped the inbox: a hacker's hidden filter archives payment emails on arrival.
function scanQueries(lastScanEpoch, nowEpoch) {
  var since = lastScanEpoch ? lastScanEpoch - SCAN_OVERLAP_SECONDS : nowEpoch - FIRST_RUN_LOOKBACK_SECONDS;
  return [
    { folder: "inbox", q: "in:inbox after:" + since },
    { folder: "spam", q: "in:spam after:" + since },
    { folder: "other", q: "after:" + since + " -in:inbox -in:spam -in:sent -in:drafts -in:trash -in:chats" },
  ];
}

// Gmail gives the sidebar "msg-f:<decimal>" ids; the Gmail API (scanner) uses the same number in hex.
function normalizeMessageId(id) {
  var s = String(id);
  return s.indexOf("msg-f:") === 0 ? BigInt(s.slice(6)).toString(16) : s;
}

function selectNew(ids, seen) {
  var s = {};
  (seen || []).forEach(function (id) { s[id] = true; });
  return ids.filter(function (id) { return !s[id]; });
}

// Keeps the newest `max` ids (script properties are small).
function updateSeen(seen, newIds, max) {
  var all = (seen || []).concat(newIds);
  return all.slice(Math.max(0, all.length - max));
}

function labelNameFor(label) {
  return LABEL_NAMES[label] || null;
}

// Batch status -> what to do next. "unknown" means the server lost it (e.g. restarted), "error" failed: resubmit both.
function splitStatus(results) {
  var out = { done: [], pending: [], resubmit: [] };
  Object.keys(results).forEach(function (id) {
    var r = results[id];
    if (r.status === "done") out.done.push({ id: id, label: r.label });
    else if (r.status === "unknown" || r.status === "error") out.resubmit.push(id);
    else out.pending.push(id);
  });
  return out;
}

var TONES = { VERIFY_BEFORE_PAYING: "verify", LOOKS_UNUSUAL: "unusual", NO_ISSUES_FOUND: "fine" };
var ICONS = { warn: "⚠", note: "ℹ", ok: "✓" };

// API result card -> what the sidebar shows: the decision and why, an optional call-back line (only when a vendor or
// colleague on file is involved), then The sender / The company / The request (warnings, notes, then checks).
function cardModel(card) {
  return {
    title: card.headline,
    tone: TONES[card.decision] || "none",
    intro: card.intro || "",
    action: card.action || "",
    sections: (card.sections || []).map(function (s) {
      return {
        title: s.title,
        lines: s.items.map(function (i) { return (ICONS[i.tone] || "•") + " " + i.text; }),
        sources: s.items.map(function (i) {
          return (i.sources || []).filter(function (src) { return /^https?:\/\/[^\s/]+\.[^\s]+$/.test(src.url); })
            .map(function (src) { return { label: sourceLabel(src.url), url: src.url }; });
        }),
        important: s.items.filter(function (i) { return i.tone !== "ok"; }).length,
      };
    }),
    checksCount: (card.checks || []).length,
  };
}

// "https://www.henryschein.com/us-en/contact" -> "henryschein.com/us-en/contact" (short, readable link text)
function sourceLabel(url) {
  var m = String(url).match(/^https?:\/\/(?:www\.)?([^/?#]+)([^?#]*)/);
  if (!m) return url;
  var path = m[2].replace(/\/+$/, "");
  return (m[1] + path).slice(0, 60);
}

// What the user sees when a call to BEC Guard fails. code 0 = no answer at all (DNS error, server or tunnel down).
function errorMessage(r) {
  if (r.code === 0) return "Can't reach BEC Guard at the saved address. The server or its URL may have changed: " +
    "use Edit connection on the BEC Guard home card.";
  if (r.body && r.body.detail) return String(r.body.detail);
  return "BEC Guard returned an error (HTTP " + r.code + ").";
}

// Card text accepts a little HTML; everything that comes from an email or the API is escaped first.
function esc(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

if (typeof module !== "undefined") {
  module.exports = { normalizeBaseUrl, normalizeMessageId, scanQueries, selectNew, updateSeen, labelNameFor, splitStatus, cardModel, sourceLabel, errorMessage, esc };
}
