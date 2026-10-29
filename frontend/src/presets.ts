import type { ComposeFields } from "./compose";

/** Starting points for "Write an email". All fictional (Riverbend's sample records). */
export const PRESETS: { id: string; label: string; fields: ComposeFields }[] = [
  {
    id: "hacked-vendor",
    label: "Sam's real address, new bank",
    fields: {
      fromName: "Sam Ortiz",
      fromAddr: "ar@acmesupply.com",
      subject: "Re: Invoice ACM-10437",
      body: "Hi Jordan,\n\nQuick update: we moved our banking. Please use our new account for ACM-10437 ($18,400.00):\n" +
        "Bank: Pacific Crest Bank\nRouting: 999000222\nAccount: 000058127731\n\nPlease process today, by wire.\n\nThanks,\nSam",
      delivery: "pass",
    },
  },
  {
    id: "lookalike",
    label: "Lookalike address",
    fields: {
      fromName: "Sam Ortiz",
      fromAddr: "ar@acmesuppIy.com",
      subject: "Invoice ACM-10437 - urgent",
      body: "Hi Jordan,\n\nOur bank flagged the ACH for ACM-10437. Please send the $18,400.00 today by wire to our new account:\n" +
        "Bank: Lakeshore Commerce Bank\nRouting: 999000666\nAccount: 000044019055\n\nThanks,\nSam",
      delivery: "fail",
    },
  },
  {
    id: "fake-ceo",
    label: "Fake CEO, gift cards",
    fields: {
      fromName: "Dana Whitfield",
      fromAddr: "dana.whitfield.office@gmail.com",
      subject: "Quick favor",
      body: "Jordan,\n\nAre you at your desk? I need you to buy 5 Apple gift cards ($200 each) for a client today. " +
        "Send me the codes by email. I'm in meetings all day, so don't call.\n\nDana",
      delivery: "pass",
    },
  },
  {
    id: "normal",
    label: "Normal invoice",
    fields: {
      fromName: "Sam Ortiz",
      fromAddr: "ar@acmesupply.com",
      subject: "Invoice ACM-10438",
      body: "Hi Jordan,\n\nAttached is invoice ACM-10438 for $17,200.00 (PO-2026-0125), payable by ACH to the usual account.\n\n" +
        "Thanks,\nSam",
      delivery: "pass",
    },
  },
];
