// Mirrors the FastAPI response models (app/main.py, app/phase_a/card.py).

export type Decision = "VERIFY_BEFORE_PAYING" | "LOOKS_UNUSUAL" | "NO_ISSUES_FOUND";
export type Group = "gate" | "entity" | "org" | "content";

export interface ScenarioItem {
  id: string;
  title: string;
  from_name: string;
  from_addr: string;
  subject: string;
  date: string | null;
  has_attachments: boolean;
}

export interface EmailView {
  message_id: string;
  from_name: string;
  from_addr: string;
  reply_to: string | null;
  to: string[];
  subject: string;
  date: string | null;
  body_text: string;
  attachments: { filename: string; content_type: string; size: number }[];
}

export interface Signal {
  code: string;
  group: Group;
  verdict: "fine" | "unusual" | "info";
  weight: "strong" | "medium" | "low" | "none";
  message: string;
  source: string;
  data: Record<string, unknown>;
}

export interface Callback {
  name: string;
  phone: string;
  from: string;
  url: string | null;
}

export interface CardItem {
  tone: "warn" | "note" | "ok";
  text: string;
  code: string;
  sources: { title: string; url: string }[];
  evidence: { title: string; headers: string[]; rows: string[][]; flag_row: number | null; more: string } | null;
}

export interface CardSection {
  title: string;
  items: CardItem[];
}

export interface Card {
  message_id: string;
  decision: Decision | null;
  rule: string | null;
  intent: string;
  headline: string;
  intro: string;
  action: string;
  sections: CardSection[];
  explanation: string | null;
  looks_fine: string[];
  looks_unusual: string[];
  notes: string[];
  callback: Callback | null;
  callbacks: Callback[];
  checks: Signal[];
}

export type CheckEvent =
  | { type: "email"; email: EmailView }
  | { type: "gate"; intent: string; claimed_company: string | null }
  | { type: "signals"; group: Group; signals: Signal[] }
  | { type: "early"; decision: Decision; reason: string }
  | { type: "result"; card: Card }
  | { type: "error"; message: string };

// GET /api/sample-records (app/phase_a/models.py: VendorLedger, OrgDirectory)
export interface SampleRecords {
  org: { org_name: string; domains: string[]; people: { name: string; role: string; email: string; phone: string }[] };
  vendors: {
    name: string;
    domains: string[];
    official_phone: string;
    contacts: { name: string; email: string; role: string }[];
    bank_account: { bank_name: string; account_last4: string };
    payment_method: string;
    usual_amount: { min: number | string; max: number | string };
    past_invoices: { number: string; date: string; amount: number | string; bank_last4: string; method: string; status: string }[];
    past_emails: { from_addr: string; date: string; subject: string; body: string }[];
  }[];
}
