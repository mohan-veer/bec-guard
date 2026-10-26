// Pure logic for the BEC Guard Gmail add-on. No Apps Script services here, so it runs (and is tested) in Node too.
// In Apps Script all files share one global scope; the module.exports line at the bottom is ignored there.

var LABEL_NAMES = { verify: "BEC Guard/Verify before paying", unusual: "BEC Guard/Looks unusual" };
var SCAN_OVERLAP_SECONDS = 120; // re-query a little before the last run so nothing slips between runs
var FIRST_RUN_LOOKBACK_SECONDS = 3600;
var MAX_FINE_LINES = 8;

function normalizeBaseUrl(url) {
  var u = String(url || "").trim().replace(/\/+$/, "");
  if (!/^https:\/\/[^\s/]+/.test(u)) throw new Error("The BEC Guard URL must start with https://");
  return u;
}

// Gmail search queries for new mail since the last scan (epoch seconds). Spam is included: scam mail often lands there.
function scanQueries(lastScanEpoch, nowEpoch) {
  var since = lastScanEpoch ? lastScanEpoch - SCAN_OVERLAP_SECONDS : nowEpoch - FIRST_RUN_LOOKBACK_SECONDS;
  return [
    { folder: "inbox", q: "in:inbox after:" + since },
    { folder: "spam", q: "in:spam after:" + since },
  ];
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

// API result card -> what the sidebar shows: the required action first, then what looks unusual, then what's fine.
function cardModel(card) {
  var cb = card.callback;
  return {
    title: card.headline,
    tone: TONES[card.decision] || "none",
    action: card.action,
    explanation: card.explanation || null,
    callback: cb ? cb.name + " · " + cb.phone + " (from " + cb.from + ")" : null,
    unusual: card.looks_unusual || [],
    fine: (card.looks_fine || []).slice(0, MAX_FINE_LINES),
    checksCount: (card.checks || []).length,
  };
}

// Card text accepts a little HTML; everything that comes from an email or the API is escaped first.
function esc(text) {
  return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

if (typeof module !== "undefined") {
  module.exports = { normalizeBaseUrl, scanQueries, selectNew, updateSeen, labelNameFor, splitStatus, cardModel, esc };
}
