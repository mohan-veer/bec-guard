/** Builds an .eml from the "Write an email" form. Nothing is sent: the file is checked or downloaded. */

export const TO = "Jordan Ellis <jordan.ellis@riverbenddental.com>";

export type Delivery = "pass" | "fail";

export interface ComposeFields {
  fromName: string;
  fromAddr: string;
  subject: string;
  body: string;
  delivery: Delivery; // simulated SPF/DKIM/DMARC result (a pasted email has no real one)
  pdf?: { name: string; base64: string };
}

const oneLine = (s: string) => s.replace(/[\r\n]+/g, " ").trim();

function base64Utf8(s: string): string {
  let bin = "";
  for (const b of new TextEncoder().encode(s)) bin += String.fromCharCode(b);
  return btoa(bin);
}

function encodeHeader(s: string): string {
  return /^[\x20-\x7e]*$/.test(s) ? s : `=?utf-8?B?${base64Utf8(s)}?=`;
}

function rfc2822Date(d: Date): string {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const p = (n: number) => String(n).padStart(2, "0");
  return `${days[d.getUTCDay()]}, ${p(d.getUTCDate())} ${months[d.getUTCMonth()]} ${d.getUTCFullYear()} ` +
    `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())} +0000`;
}

function authResults(domain: string, delivery: Delivery): string {
  return `mx.riverbenddental.com; spf=${delivery} smtp.mailfrom=${domain}; dkim=${delivery} header.d=${domain}; ` +
    `dmarc=${delivery} header.from=${domain}`;
}

// randomUUID exists only on https or localhost; the id just has to be unique-ish.
const newId = () => (typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2));

export function buildEml(f: ComposeFields, now: Date = new Date(), id: string = newId()): string {
  const addr = oneLine(f.fromAddr);
  const rawName = oneLine(f.fromName);
  // Encoded words aren't decoded inside quotes, so a non-ASCII name is encoded bare, an ASCII one quoted.
  const name = !rawName ? "" : /^[\x20-\x7e]*$/.test(rawName) ? `"${rawName.replace(/["\\]/g, "\\$&")}"` : encodeHeader(rawName);
  const domain = addr.split("@")[1] ?? "";
  const body = f.body.replace(/\r?\n/g, "\r\n") + "\r\n";
  const headers = [
    `Message-ID: <composed-${id}@bec-guard.demo>`,
    `Date: ${rfc2822Date(now)}`,
    `From: ${name ? `${name} ` : ""}<${addr}>`,
    `To: ${TO}`,
    `Subject: ${encodeHeader(oneLine(f.subject))}`,
    `Authentication-Results: ${authResults(domain, f.delivery)}`,
    "X-BEC-Guard-Demo: composed",
    "MIME-Version: 1.0",
  ];
  const text = 'Content-Type: text/plain; charset="utf-8"\r\nContent-Transfer-Encoding: 8bit';
  if (!f.pdf) return [...headers, text, "", body].join("\r\n");

  const boundary = `bec-guard-${id}`;
  const pdfName = oneLine(f.pdf.name).replace(/["\\]/g, "");
  const b64 = f.pdf.base64.replace(/.{1,76}/g, "$&\r\n");
  return [
    ...headers,
    `Content-Type: multipart/mixed; boundary="${boundary}"`,
    "",
    `--${boundary}`, text, "", body,
    `--${boundary}`,
    `Content-Type: application/pdf; name="${pdfName}"`,
    "Content-Transfer-Encoding: base64",
    `Content-Disposition: attachment; filename="${pdfName}"`,
    "", b64,
    `--${boundary}--`, "",
  ].join("\r\n");
}
