// BEC Guard for Gmail: sidebar card on open, a background scanner that labels risky mail, and a settings report.
// Talks only to the BEC Guard API (URL + key saved per user). Pure helpers live in Logic.js.

var SEEN_MAX = 300;          // message ids remembered as already sent
var PENDING_MAX = 100;       // results waited for at once (= the API's batch limit)
var SIDEBAR_WAIT_SECONDS = 10;
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

function api_(cfg, method, path, body) {
  var r = request_(cfg, method, path, body);
  return parse_(UrlFetchApp.fetch(r.url, r));
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
  return resultCard_(e.gmail.messageId, true);
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
    var sub = parse_(UrlFetchApp.fetch(s.url, s));
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
  var color = TONE_COLORS[m.tone];
  var head = CardService.newCardSection()
    .addWidget(CardService.newTextParagraph().setText('<font color="' + color + '"><b>' + esc(m.title) + "</b></font>"))
    .addWidget(CardService.newTextParagraph().setText("<b>" + esc(m.action) + "</b>"));
  if (m.callback && m.tone !== "fine") head.addWidget(CardService.newDecoratedText().setTopLabel("Call back on")
    .setText(esc(m.callback)).setWrapText(true));
  if (m.explanation) head.addWidget(CardService.newTextParagraph().setText(esc(m.explanation)));

  var card = CardService.newCardBuilder().setHeader(CardService.newCardHeader().setTitle("BEC Guard")
    .setSubtitle("Checked " + m.checksCount + " things")).addSection(head);
  if (m.unusual.length) card.addSection(listSection_("Looks unusual", m.unusual, "•"));
  if (m.fine.length) card.addSection(listSection_("Looks fine", m.fine, "✓").setCollapsible(true).setNumUncollapsibleWidgets(2));
  card.addSection(CardService.newCardSection().addWidget(refreshButton_(messageId)));
  return card.build();
}

function listSection_(title, lines, bullet) {
  var s = CardService.newCardSection().setHeader(title);
  lines.forEach(function (line) {
    s.addWidget(CardService.newDecoratedText().setText(bullet + " " + esc(line)).setWrapText(true));
  });
  return s;
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
  return (r.body && r.body.detail) ? String(r.body.detail) : "HTTP " + r.code;
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
  UrlFetchApp.fetchAll(items.map(function (it) { return submitRequest_(cfg, mailbox, it.id, it.folder); }));
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
