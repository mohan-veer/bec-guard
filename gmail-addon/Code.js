// BEC Guard for Gmail: sidebar card on open, a background scanner that labels risky mail, and a settings report.
// Talks only to the BEC Guard API (URL + key saved per user). Pure helpers live in Logic.js.

var SEEN_MAX = 300;          // message ids remembered as already sent
var PENDING_MAX = 100;       // results waited for at once (= the API's batch limit)
var SIDEBAR_WAIT_SECONDS = 24; // Google stops add-on actions at ~30 s; a full real-model check takes ~8-15 s
var TONE_COLORS = { verify: "#b45309", unusual: "#a16207", fine: "#047857", none: "#475569" };

// ---------- config & API ----------

function getConfig_() {
  var p = PropertiesService.getUserProperties();
  var baseUrl = p.getProperty("baseUrl"), apiKey = p.getProperty("apiKey");
  return baseUrl && apiKey ? { baseUrl: baseUrl, apiKey: apiKey } : null;
}

function request_(cfg, method, path, body) {
  var req = { url: cfg.baseUrl + path, method: method, headers: { "X-BEC-Key": cfg.apiKey }, muteHttpExceptions: true };
  if (body !== undefined) {
    req.contentType = "application/json";
    req.payload = JSON.stringify(body);
  }
  return req;
}

function parse_(resp) {
  var text = resp.getContentText();
  try { return { code: resp.getResponseCode(), body: JSON.parse(text) }; }
  catch (err) { return { code: resp.getResponseCode(), body: null }; }
}

function fetch_(r) { // network failures (DNS, server down) come back as code 0 instead of throwing
  try { return parse_(UrlFetchApp.fetch(r.url, r)); }
  catch (err) { return { code: 0, body: null, error: String(err) }; }
}

function api_(cfg, method, path, body) {
  return fetch_(request_(cfg, method, path, body));
}

function mailbox_() {
  var p = PropertiesService.getUserProperties();
  var m = p.getProperty("mailbox");
  if (!m) {
    m = Gmail.Users.getProfile("me").emailAddress;
    p.setProperty("mailbox", m);
  }
  return m;
}

function rawOf_(messageId) {
  return Utilities.base64EncodeWebSafe(GmailApp.getMessageById(messageId).getRawContent(), Utilities.Charset.UTF_8);
}

function submitRequest_(cfg, mailbox, id, folder) {
  return request_(cfg, "post", "/api/v1/messages",
    { provider: "gmail", mailbox: mailbox, message_id: id, raw: rawOf_(id), folder: folder });
}

function getResult_(cfg, mailbox, id) {
  return api_(cfg, "get", "/api/v1/messages/gmail/" + encodeURIComponent(id) + "?mailbox=" + encodeURIComponent(mailbox));
}

// ---------- sidebar: the card for the open email ----------

function onGmailMessageOpen(e) {
  GmailApp.setCurrentMessageAccessToken(e.gmail.accessToken);
  return resultCard_(normalizeMessageId(e.gmail.messageId), true);
}

function onRefresh(e) {
  var card = resultCard_(e.commonEventObject.parameters.messageId, false);
  return CardService.newActionResponseBuilder().setNavigation(CardService.newNavigation().updateCard(card)).build();
}

function resultCard_(messageId, submitIfNew) {
  var cfg = getConfig_();
  if (!cfg) return setupCard_("Connect BEC Guard to start checking emails.");
  var mailbox = mailbox_();
  var r = getResult_(cfg, mailbox, messageId);
  if (r.code === 404 && submitIfNew) {
    var s = submitRequest_(cfg, mailbox, messageId, "inbox");
    var sub = fetch_(s);
    if (sub.code >= 400) return messageCard_("Couldn't check this email", errorText_(sub));
    for (var i = 0; i < SIDEBAR_WAIT_SECONDS / 2; i++) { // a short wait often gets the full result
      Utilities.sleep(2000);
      r = getResult_(cfg, mailbox, messageId);
      if (r.code === 200 && (r.body.status === "done" || r.body.status === "error")) break;
    }
  }
  if (r.code === 401) return setupCard_("The saved API key was rejected. Please enter it again.");
  if (r.code !== 200) return messageCard_("Couldn't reach BEC Guard", errorText_(r), messageId);
  if (r.body.status === "error") return messageCard_("Check failed", "BEC Guard couldn't analyze this email.", messageId);
  if (r.body.status !== "done") return messageCard_("Checking this email…", "This usually takes a few seconds.", messageId);
  return renderResult_(cardModel(r.body.card), messageId);
}

function renderResult_(m, messageId) {
  var head = CardService.newCardSection()
    .addWidget(CardService.newTextParagraph().setText('<font color="' + TONE_COLORS[m.tone] + '"><b>' + esc(m.title) +
      "</b></font>"));
  if (m.intro) head.addWidget(CardService.newTextParagraph().setText(esc(m.intro)));
  if (m.action) head.addWidget(CardService.newTextParagraph().setText("<b>" + esc(m.action) + "</b>"));
  var card = CardService.newCardBuilder().setHeader(CardService.newCardHeader().setTitle("BEC Guard")
    .setSubtitle("Checked " + m.checksCount + " things")).addSection(head);
  m.sections.forEach(function (s) {
    var section = CardService.newCardSection().setHeader(esc(s.title));
    s.lines.forEach(function (line, i) {
      section.addWidget(CardService.newDecoratedText().setText(esc(line)).setWrapText(true));
      if (s.sources[i].length) { // the pages that supported this line, like citations
        section.addWidget(CardService.newTextParagraph().setText("Source: " + s.sources[i].map(function (src) {
          return '<a href="' + esc(src.url) + '">' + esc(src.label) + "</a>";
        }).join(", ")));
      }
    });
    var visible = s.lines.slice(0, s.important).length +
      s.sources.slice(0, s.important).filter(function (x) { return x.length; }).length;
    if (s.lines.length > s.important) { // keep warnings, notes and their sources visible; checks can be expanded
      section.setCollapsible(true).setNumUncollapsibleWidgets(Math.max(1, visible));
    }
    card.addSection(section);
  });
  card.addSection(CardService.newCardSection().addWidget(refreshButton_(messageId)));
  return card.build();
}

function refreshButton_(messageId) {
  return CardService.newTextButton().setText("Refresh")
    .setOnClickAction(CardService.newAction().setFunctionName("onRefresh").setParameters({ messageId: messageId }));
}

function messageCard_(title, text, messageId) {
  var s = CardService.newCardSection().addWidget(CardService.newTextParagraph().setText(esc(text)));
  if (messageId) s.addWidget(refreshButton_(messageId));
  return CardService.newCardBuilder().setHeader(CardService.newCardHeader().setTitle(title)).addSection(s).build();
}

function errorText_(r) {
  return errorMessage(r);
}

// ---------- homepage: connection, automatic checking, mailbox settings ----------

function onHomepage(e) {
  var cfg = getConfig_();
  if (!cfg) return setupCard_("Paste the BEC Guard URL and your organization's API key.");
  var props = PropertiesService.getUserProperties();
  var on = scannerInstalled_();
  var last = props.getProperty("lastScan");
  var s = CardService.newCardSection()
    .addWidget(CardService.newDecoratedText().setTopLabel("Connected to").setText(esc(cfg.baseUrl)).setWrapText(true))
    .addWidget(CardService.newDecoratedText().setTopLabel("Automatic checking")
      .setText(on ? "On: new mail is checked every minute" : "Off").setWrapText(true));
  if (last) s.addWidget(CardService.newDecoratedText().setTopLabel("Last scan")
    .setText(new Date(Number(last) * 1000).toLocaleString()));
  s.addWidget(CardService.newButtonSet()
    .addButton(CardService.newTextButton().setText(on ? "Turn off" : "Turn on")
      .setOnClickAction(CardService.newAction().setFunctionName(on ? "onScannerOff" : "onScannerOn")))
    .addButton(CardService.newTextButton().setText("Check mailbox settings")
      .setOnClickAction(CardService.newAction().setFunctionName("onSettingsCheck")))
    .addButton(CardService.newTextButton().setText("Edit connection")
      .setOnClickAction(CardService.newAction().setFunctionName("onEditConnection"))));
  return CardService.newCardBuilder().setHeader(CardService.newCardHeader().setTitle("BEC Guard")
    .setSubtitle("Checks payment and data requests before you act")).addSection(s).build();
}

function setupCard_(note) {
  var cfg = getConfig_() || {};
  var s = CardService.newCardSection()
    .addWidget(CardService.newTextParagraph().setText(esc(note)))
    .addWidget(CardService.newTextInput().setFieldName("baseUrl").setTitle("BEC Guard URL (https://…)").setValue(cfg.baseUrl || ""))
    .addWidget(CardService.newTextInput().setFieldName("apiKey").setTitle("API key"))
    .addWidget(CardService.newTextButton().setText("Save and test")
      .setOnClickAction(CardService.newAction().setFunctionName("onSaveConnection")));
  return CardService.newCardBuilder().setHeader(CardService.newCardHeader().setTitle("Connect BEC Guard")).addSection(s).build();
}

function input_(e, name) {
  var f = e.commonEventObject.formInputs || {};
  return f[name] ? f[name].stringInputs.value[0] : "";
}

function onSaveConnection(e) {
  var cfg;
  try {
    cfg = { baseUrl: normalizeBaseUrl(input_(e, "baseUrl")), apiKey: input_(e, "apiKey").trim() };
  } catch (err) {
    return notify_(err.message);
  }
  if (!cfg.apiKey) return notify_("Please enter the API key.");
  // An empty batch status call checks the URL and the key without sending any email.
  var r = api_(cfg, "post", "/api/v1/messages/status", { provider: "gmail", mailbox: mailbox_(), ids: [] });
  if (r.code !== 200) return notify_("Connection failed: " + errorText_(r));
  PropertiesService.getUserProperties().setProperties({ baseUrl: cfg.baseUrl, apiKey: cfg.apiKey });
  return CardService.newActionResponseBuilder().setNotification(CardService.newNotification().setText("Connected"))
    .setNavigation(CardService.newNavigation().updateCard(onHomepage())).build();
}

function onEditConnection() {
  return CardService.newActionResponseBuilder()
    .setNavigation(CardService.newNavigation().pushCard(setupCard_("Update the URL or the key."))).build();
}

function notify_(text) {
  return CardService.newActionResponseBuilder().setNotification(CardService.newNotification().setText(text)).build();
}

// ---------- background scanner ----------

function scannerInstalled_() {
  return ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === "scanInbox"; });
}

function installScanner() { // can also be run once from the script editor
  uninstallScanner();
  ScriptApp.newTrigger("scanInbox").timeBased().everyMinutes(1).create();
  ScriptApp.newTrigger("reportSettings").timeBased().everyDays(1).create();
}

function uninstallScanner() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (["scanInbox", "reportSettings"].indexOf(t.getHandlerFunction()) >= 0) ScriptApp.deleteTrigger(t);
  });
}

function onScannerOn() {
  try { installScanner(); } catch (err) {
    return notify_("Couldn't turn on automatic checking here: " + err.message + ". Run installScanner from the script editor.");
  }
  return CardService.newActionResponseBuilder().setNavigation(CardService.newNavigation().updateCard(onHomepage())).build();
}

function onScannerOff() {
  uninstallScanner();
  return CardService.newActionResponseBuilder().setNavigation(CardService.newNavigation().updateCard(onHomepage())).build();
}

// Runs every minute. Must stay fast (Apps Script: 90 trigger-minutes/day): it only sends new mail and collects
// finished results; the analysis itself happens on the BEC Guard server.
function scanInbox() {
  var lock = LockService.getUserLock();
  if (!lock.tryLock(5000)) return;
  try {
    var cfg = getConfig_();
    if (!cfg) return;
    var props = PropertiesService.getUserProperties();
    var now = Math.floor(Date.now() / 1000);
    var seen = JSON.parse(props.getProperty("seen") || "[]");
    var pending = JSON.parse(props.getProperty("pending") || "{}"); // id -> folder
    var mailbox = mailbox_();

    var found = {};
    scanQueries(Number(props.getProperty("lastScan")) || null, now).forEach(function (s) {
      var res = Gmail.Users.Messages.list("me", { q: s.q, maxResults: 50, includeSpamTrash: s.folder === "spam" });
      (res.messages || []).forEach(function (m) { found[m.id] = s.folder; });
    });
    var fresh = selectNew(Object.keys(found), seen).slice(0, PENDING_MAX - Object.keys(pending).length);
    send_(cfg, mailbox, fresh.map(function (id) { return { id: id, folder: found[id] }; }));
    fresh.forEach(function (id) { pending[id] = found[id]; });
    seen = updateSeen(seen, fresh, SEEN_MAX);

    var ids = Object.keys(pending);
    if (ids.length) {
      var st = api_(cfg, "post", "/api/v1/messages/status", { provider: "gmail", mailbox: mailbox, ids: ids });
      if (st.code === 200) {
        var split = splitStatus(st.body.results);
        split.done.forEach(function (d) {
          var name = labelNameFor(d.label);
          if (name) addLabel_(d.id, name);
          delete pending[d.id];
        });
        send_(cfg, mailbox, split.resubmit.map(function (id) { return { id: id, folder: pending[id] }; }));
      }
    }
    props.setProperties({ lastScan: String(now), seen: JSON.stringify(seen), pending: JSON.stringify(pending) });
  } finally {
    lock.releaseLock();
  }
}

function send_(cfg, mailbox, items) {
  if (!items.length) return;
  try {
    UrlFetchApp.fetchAll(items.map(function (it) { return submitRequest_(cfg, mailbox, it.id, it.folder); }));
  } catch (err) { // server unreachable: the ids stay pending and are resent on the next run
    Logger.log("BEC Guard unreachable: " + err);
  }
}

var LABEL_COLORS = { "BEC Guard/Verify before paying": "#cc3a21", "BEC Guard/Looks unusual": "#ffad47" };

function labelId_(name) {
  var props = PropertiesService.getUserProperties();
  var cached = props.getProperty("label:" + name);
  if (cached) return cached;
  var existing = (Gmail.Users.Labels.list("me").labels || []).filter(function (l) { return l.name === name; })[0];
  var id = existing ? existing.id : createLabel_(name);
  props.setProperty("label:" + name, id);
  return id;
}

function createLabel_(name) {
  var parent = name.split("/")[0];
  if (parent !== name) labelId_(parent); // nested labels need their parent
  var label = { name: name, labelListVisibility: "labelShow", messageListVisibility: "show" };
  try {
    if (LABEL_COLORS[name]) label.color = { backgroundColor: LABEL_COLORS[name], textColor: "#ffffff" };
    return Gmail.Users.Labels.create(label, "me").id;
  } catch (err) { // colour not accepted: create it plain
    delete label.color;
    return Gmail.Users.Labels.create(label, "me").id;
  }
}

function addLabel_(messageId, name) {
  Gmail.Users.Messages.modify({ addLabelIds: [labelId_(name)] }, "me", messageId);
}

// ---------- mailbox settings report (rules & forwarding) ----------

function reportSettings() {
  var cfg = getConfig_();
  if (!cfg) return null;
  var payload = {
    provider: "gmail", mailbox: mailbox_(),
    filters: Gmail.Users.Settings.Filters.list("me") || {},
    forwarding: Gmail.Users.Settings.ForwardingAddresses.list("me") || {},
    auto_forwarding: Gmail.Users.Settings.getAutoForwarding("me") || {},
  };
  var r = api_(cfg, "post", "/api/v1/mailbox-settings", payload);
  return r.code === 200 ? r.body : null;
}

function onSettingsCheck() {
  var report = reportSettings();
  if (!report) return notify_("Couldn't check mailbox settings. Is BEC Guard reachable?");
  var card = CardService.newCardBuilder().setHeader(CardService.newCardHeader().setTitle("Mailbox settings")
    .setSubtitle("Checked " + report.rules_checked + " filters and forwarding"));
  if (!report.findings.length) {
    card.addSection(CardService.newCardSection().addWidget(CardService.newTextParagraph()
      .setText('<font color="#047857"><b>No risky filters or forwarding found.</b></font>')));
  }
  report.findings.forEach(function (f) {
    var s = CardService.newCardSection().setHeader((f.severity === "high" ? "Act now: " : "Review: ") + esc(f.rule_name));
    f.reasons.forEach(function (r) { s.addWidget(CardService.newDecoratedText().setText("• " + esc(r)).setWrapText(true)); });
    if (f.explanation) s.addWidget(CardService.newTextParagraph().setText(esc(f.explanation)));
    s.addWidget(CardService.newTextParagraph().setText("<b>" + esc(f.next_step) + "</b>"));
    card.addSection(s);
  });
  return CardService.newActionResponseBuilder().setNavigation(CardService.newNavigation().pushCard(card.build())).build();
}

// ---------- demo history (run once from the script editor) ----------
// Imports the backdated demo mailbox (Jun–Oct 2026, generated by scripts/make_demo_data.py) into THIS mailbox.
// Imported mail keeps its own dates, so the scanner (which only looks at mail newer than its last run) ignores it.
// Every message carries the header X-BEC-Guard-Demo: seeded-history. removeDemoHistory() moves it all to Trash.

function seedDemoHistory() {
  var cfg = getConfig_();
  if (!cfg) throw new Error("Connect BEC Guard in the Gmail side panel first.");
  var r = api_(cfg, "get", "/api/v1/demo/history");
  if (r.code !== 200) throw new Error("Couldn't load the demo history: " + errorText_(r));
  var props = PropertiesService.getUserProperties();
  var seeded = JSON.parse(props.getProperty("demoSeeded") || "{}"); // key -> Gmail message id
  var added = 0;
  r.body.messages.forEach(function (m) {
    if (seeded[m.key]) return; // already imported: safe to re-run
    var blob = Utilities.newBlob(Utilities.base64DecodeWebSafe(m.raw), "message/rfc822");
    var args = { internalDateSource: "dateHeader", neverMarkSpam: true };
    var res;
    try {
      res = Gmail.Users.Messages.import({ labelIds: m.labels }, "me", blob, args);
    } catch (err) { // a system label wasn't accepted: import without labels rather than skip the message
      res = Gmail.Users.Messages.import({}, "me", blob, args);
    }
    seeded[m.key] = res.id;
    added++;
  });
  props.setProperty("demoSeeded", JSON.stringify(seeded));
  Logger.log("Imported " + added + " demo emails (" + Object.keys(seeded).length + " in total).");
}

function removeDemoHistory() {
  var props = PropertiesService.getUserProperties();
  var seeded = JSON.parse(props.getProperty("demoSeeded") || "{}");
  Object.keys(seeded).forEach(function (key) {
    try { Gmail.Users.Messages.trash("me", seeded[key]); } catch (err) { /* already gone */ }
  });
  props.deleteProperty("demoSeeded");
  Logger.log("Moved " + Object.keys(seeded).length + " demo emails to Trash.");
}
