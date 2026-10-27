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
    // archived by a filter (what an attacker's hidden rule does): still checked
    { folder: "other", q: "after:999880 -in:inbox -in:spam -in:sent -in:drafts -in:trash -in:chats" },
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

test("card model: headline, intro, optional action, then the three sections with icons", () => {
  const m = L.cardModel({
    decision: "VERIFY_BEFORE_PAYING", headline: "Verify before paying", intro: "We found the following reasons:",
    action: "Before paying, confirm the new bank details with Acme Supply at (503) 555-0142 (from your vendor records), not a number from this email.",
    sections: [
      { title: "The sender", items: [{ tone: "ok", text: "Confirmed as sent from a@b.com" }] },
      { title: "The request", items: [{ tone: "warn", text: "New account" }, { tone: "note", text: "fyi" }] },
    ],
    checks: [{}, {}, {}],
  });
  assert.equal(m.title, "Verify before paying");
  assert.equal(m.tone, "verify");
  assert.equal(m.intro, "We found the following reasons:");
  assert.match(m.action, /^Before paying, confirm/);
  assert.deepEqual(m.sections.map((s) => s.title), ["The sender", "The request"]);
  assert.deepEqual(m.sections[1].lines, ["⚠ New account", "ℹ fyi"]);
  assert.deepEqual(m.sections[0].lines, ["✓ Confirmed as sent from a@b.com"]);
  assert.equal(m.sections[1].important, 2);   // warn + note stay visible; ok lines can collapse
  assert.equal(m.sections[0].important, 0);
  assert.equal(m.checksCount, 3);
});

test("card model for a no-request email", () => {
  const m = L.cardModel({ decision: null, headline: "No money or data request found",
    intro: "This email doesn't ask for money or data.", action: "", sections: [], checks: [{}] });
  assert.equal(m.tone, "none");
  assert.equal(m.action, "");
  assert.deepEqual(m.sections, []);
});

test("html in card text is escaped (email content can't inject markup)", () => {
  assert.equal(L.esc('<b>x</b> & "y"'), "&lt;b&gt;x&lt;/b&gt; &amp; &quot;y&quot;");
});

test("sidebar message ids (msg-f:<decimal>) become the Gmail API's hex ids, so sidebar and scanner share one result", () => {
  assert.equal(L.normalizeMessageId("msg-f:1880178171196826142"), "1a17bc15c8a1621e");
  assert.equal(L.normalizeMessageId("1a17bc15c8a1621e"), "1a17bc15c8a1621e");
  assert.equal(L.normalizeMessageId("msg-f:18"), "12");
});

test("unreachable server gives a clear message, not a stack trace", () => {
  assert.match(L.errorMessage({ code: 0, body: null, error: "DNS error: https://x.trycloudflare.com/..." }),
               /can't reach BEC Guard.*Edit connection/i);
  assert.equal(L.errorMessage({ code: 401, body: { detail: "Missing or invalid API key" } }), "Missing or invalid API key");
  assert.equal(L.errorMessage({ code: 502, body: null }), "BEC Guard returned an error (HTTP 502).");
});

test("source links: shown under their line, only http(s), labelled by site and page", () => {
  const m = L.cardModel({ decision: "VERIFY_BEFORE_PAYING", headline: "h", checks: [], sections: [{ title: "The company", items: [
    { tone: "warn", text: "Says it's Henry Schein…", sources: [{ title: "Henry Schein Dental", url: "https://www.henryschein.com/" }] },
    { tone: "warn", text: "bad link", sources: [{ title: "x", url: "javascript:alert(1)" }] },
  ] }] });
  assert.deepEqual(m.sections[0].sources[0], [{ label: "henryschein.com", url: "https://www.henryschein.com/" }]);
  assert.deepEqual(m.sections[0].sources[1], []);
  assert.equal(L.sourceLabel("https://www.henryschein.com/us-en/contact"), "henryschein.com/us-en/contact");
});

test("records evidence under a line: title, one row per record, the new value flagged", () => {
  const ev = { title: "From your vendor records · Acme Supply", headers: ["Invoice", "Date", "Amount", "Paid to"],
    rows: [["ACM-10436", "2026-09-01", "$19,800.00", "••••4821"], ["This email", "", "$18,400.00", "••••7731"]],
    flag_row: 1, more: "+ 3 earlier, all paid to ••••4821" };
  assert.deepEqual(L.evidenceView(ev), {
    title: "From your vendor records · Acme Supply",
    rows: [{ text: "ACM-10436 · 2026-09-01 · $19,800.00 · ••••4821", flag: false },
           { text: "This email · $18,400.00 · ••••7731", flag: true }],
    more: "+ 3 earlier, all paid to ••••4821" });
  const kv = L.evidenceView({ title: "t", headers: [], rows: [["Contact on file", "Sam, s@y.com"]], flag_row: null, more: "" });
  assert.deepEqual(kv.rows, [{ text: "Contact on file: Sam, s@y.com", flag: false }]);
  assert.equal(L.evidenceView(null), null);
  const m = L.cardModel({ decision: "VERIFY_BEFORE_PAYING", headline: "h", checks: [], sections: [{ title: "The request",
    items: [{ tone: "warn", text: "x", evidence: ev }] }] });
  assert.equal(m.sections[0].evidence[0].rows.length, 2);
});
