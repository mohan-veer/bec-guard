// Run: node --test gmail-addon/tests/
const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../Logic.js");

test("base URL must be https and loses trailing slashes", () => {
  assert.equal(L.normalizeBaseUrl(" https://x.trycloudflare.com/// "), "https://x.trycloudflare.com");
  assert.throws(() => L.normalizeBaseUrl("http://x.com"), /https/);
  assert.throws(() => L.normalizeBaseUrl(""), /https/);
});

test("scan queries cover inbox and spam since the last run, with overlap", () => {
  const q = L.scanQueries(1000000, 2000000);
  assert.deepEqual(q, [
    { folder: "inbox", q: "in:inbox after:999880" },
    { folder: "spam", q: "in:spam after:999880" },
  ]);
  // first run: look back one hour
  assert.equal(L.scanQueries(null, 2000000)[0].q, "in:inbox after:1996400");
});

test("only unseen ids are sent, and the seen list stays bounded", () => {
  assert.deepEqual(L.selectNew(["a", "b", "c"], ["b"]), ["a", "c"]);
  const seen = L.updateSeen(["x"], Array.from({ length: 400 }, (_, i) => "m" + i), 300);
  assert.equal(seen.length, 300);
  assert.equal(seen[seen.length - 1], "m399"); // newest kept
});

test("label names only for risky results", () => {
  assert.equal(L.labelNameFor("verify"), "BEC Guard/Verify before paying");
  assert.equal(L.labelNameFor("unusual"), "BEC Guard/Looks unusual");
  assert.equal(L.labelNameFor("none"), null);
  assert.equal(L.labelNameFor(null), null);
});

test("status results split into done, still pending, and lost (server restarted)", () => {
  const r = L.splitStatus({
    a: { status: "done", label: "verify" },
    b: { status: "processing" },
    c: { status: "unknown" },
    d: { status: "error" },
    e: { status: "done", label: "none" },
  });
  assert.deepEqual(r.done, [{ id: "a", label: "verify" }, { id: "e", label: "none" }]);
  assert.deepEqual(r.pending, ["b"]);
  assert.deepEqual(r.resubmit, ["c", "d"]);
});

test("card model: action first, unusual before fine, lists capped", () => {
  const m = L.cardModel({
    decision: "VERIFY_BEFORE_PAYING", headline: "Verify before paying",
    action: "Bank details changed. Before paying, call Acme.", explanation: "Because.",
    looks_unusual: ["u1", "u2"], looks_fine: Array.from({ length: 12 }, (_, i) => "f" + i),
    callback: { name: "Acme Supply", phone: "(503) 555-0142", from: "your vendor records" },
    checks: [{}, {}, {}],
  });
  assert.equal(m.title, "Verify before paying");
  assert.equal(m.tone, "verify");
  assert.equal(m.action, "Bank details changed. Before paying, call Acme.");
  assert.deepEqual(m.unusual, ["u1", "u2"]);
  assert.equal(m.fine.length, 8);
  assert.equal(m.callback, "Acme Supply · (503) 555-0142 (from your vendor records)");
  assert.equal(m.checksCount, 3);
});

test("card model for a no-request email", () => {
  const m = L.cardModel({ decision: null, headline: "No money or data request found", action: "No money or data request found.",
    looks_unusual: [], looks_fine: [], callback: null, checks: [{}] });
  assert.equal(m.tone, "none");
  assert.equal(m.callback, null);
});

test("html in card text is escaped (email content can't inject markup)", () => {
  assert.equal(L.esc('<b>x</b> & "y"'), "&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;");
});
