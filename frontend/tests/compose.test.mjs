// Run: node --test frontend/tests/compose.test.mjs (Node 22.18+ strips the TypeScript types).
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildEml, TO } from "../src/compose.ts";

const NOW = new Date("2026-10-28T17:05:00Z");
const base = { fromName: "Sam Ortiz", fromAddr: "ar@acmesupply.com", subject: "New bank", body: "Hi Jordan,\nPlease use our new account.", delivery: "pass" };

const header = (eml, name) => eml.split("\r\n\r\n")[0].split("\r\n").find((l) => l.startsWith(name + ":"));

test("plain email has the sender, Jordan as recipient, and a demo marker", () => {
  const eml = buildEml(base, NOW, "abc");
  assert.equal(header(eml, "From"), 'From: "Sam Ortiz" <ar@acmesupply.com>');
  assert.equal(header(eml, "To"), `To: ${TO}`);
  assert.equal(header(eml, "Subject"), "Subject: New bank");
  assert.equal(header(eml, "Date"), "Date: Wed, 28 Oct 2026 17:05:00 +0000");
  assert.equal(header(eml, "Message-ID"), "Message-ID: <composed-abc@bec-guard.demo>");
  assert.equal(header(eml, "X-BEC-Guard-Demo"), "X-BEC-Guard-Demo: composed");
  assert.ok(eml.endsWith("Hi Jordan,\r\nPlease use our new account.\r\n"));
});

test("delivery choice becomes the simulated Authentication-Results for the sender's domain", () => {
  assert.equal(header(buildEml(base, NOW, "a"), "Authentication-Results"),
    "Authentication-Results: mx.riverbenddental.com; spf=pass smtp.mailfrom=acmesupply.com; dkim=pass header.d=acmesupply.com; dmarc=pass header.from=acmesupply.com");
  assert.match(header(buildEml({ ...base, delivery: "fail" }, NOW, "a"), "Authentication-Results"), /spf=fail .*dkim=fail .*dmarc=fail/);
});

test("line breaks in header fields can't inject extra headers", () => {
  const eml = buildEml({ ...base, fromName: 'Sam\r\nBcc: x@y.z', subject: "Hi\nX-Evil: 1" }, NOW, "a");
  const headers = eml.split("\r\n\r\n")[0];
  assert.ok(!/^Bcc:/m.test(headers) && !/^X-Evil:/m.test(headers));
});

test("quotes in the display name are escaped; non-ASCII subject is encoded", () => {
  const eml = buildEml({ ...base, fromName: 'Sam "AR" Ortiz', subject: "Facture réglée" }, NOW, "a");
  assert.equal(header(eml, "From"), 'From: "Sam \\"AR\\" Ortiz" <ar@acmesupply.com>');
  assert.equal(header(eml, "Subject"), "Subject: =?utf-8?B?RmFjdHVyZSByw6lnbMOpZQ==?=");
});

test("a PDF makes a multipart email with the file base64-encoded", () => {
  const eml = buildEml({ ...base, pdf: { name: "remit.pdf", base64: "JVBERi0xLjQ=" } }, NOW, "a");
  const ct = header(eml, "Content-Type");
  const boundary = ct.match(/boundary="([^"]+)"/)[1];
  assert.match(ct, /^Content-Type: multipart\/mixed;/);
  assert.ok(eml.includes(`--${boundary}\r\nContent-Type: application/pdf; name="remit.pdf"`));
  assert.ok(eml.includes('Content-Disposition: attachment; filename="remit.pdf"'));
  assert.ok(eml.includes("JVBERi0xLjQ="));
  assert.ok(eml.trimEnd().endsWith(`--${boundary}--`));
});

test("a non-ASCII display name is encoded without quotes, so mail parsers decode it", () => {
  const eml = buildEml({ ...base, fromName: "José Ortiz" }, NOW, "a");
  assert.equal(header(eml, "From"), "From: =?utf-8?B?Sm9zw6kgT3J0aXo=?= <ar@acmesupply.com>");
});
