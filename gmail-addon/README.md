# BEC Guard for Gmail (Apps Script add-on)

What it does, inside Gmail:
- **Sidebar**: open an email → the BEC Guard card (what to do first, what looks unusual, what looks fine).
- **Automatic checking**: every minute, new mail in Inbox and Spam is sent to BEC Guard; risky mail gets a label
  `BEC Guard/Verify before paying` or `BEC Guard/Looks unusual`. Clean mail is left alone.
- **Mailbox settings**: daily (or on demand) check of filters and forwarding for signs of a hacked account.

It talks only to the BEC Guard API (`/api/v1`), authenticated with your organization's API key.

## Install (unpublished test deployment, on the organization's Gmail account)

The public path is a Google Workspace Marketplace listing (one-click install). That needs Google review, so for now
the add-on is installed as a test deployment.

1. Sign in to https://script.google.com as the organization account → **New project** → name it "BEC Guard".
2. **Project Settings** (gear) → tick **Show "appsscript.json" manifest file in editor**.
3. **Editor**: replace the contents of `appsscript.json` with [appsscript.json](appsscript.json).
   Replace the contents of `Code.gs` with [Code.js](Code.js), and add a script file (**+ → Script**) named `Logic`
   with the contents of [Logic.js](Logic.js).
   The Gmail advanced service is enabled by the manifest.
4. **Deploy → Test deployments → Install**, then **Done**.
5. Open Gmail (refresh the tab). In the right-hand side panel click the **BEC Guard** shield → **Authorize access**.
   Google shows the permissions (read the open message, read/label mail, read mail settings, call an external URL,
   run on a schedule).
6. In the BEC Guard panel: paste the **BEC Guard URL** (the current `https://…trycloudflare.com` URL, later the
   Hugging Face URL) and the **API key** (the part after `riverbend:` in `BEC_API_KEYS` in `bec-guard/.env`) →
   **Save and test**.
7. Click **Turn on** (automatic checking). If Google refuses because add-on timers are limited, open the script
   editor, choose the function `installScanner` and click **Run** once.

## Develop
- Pure logic is in `Logic.js` and tested with Node's built-in runner: `node --test gmail-addon/tests/logic.test.js`
- Everything that touches Gmail, cards or triggers is in `Code.js` (only runs inside Apps Script).
