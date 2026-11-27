/**
 * Gmail Read Labeler for Auto_mail_bot
 * 100% Free — Runs inside the user's Gmail account via Google Apps Script (script.google.com).
 * Automatically adds a "✓✓ Read" label to Sent emails opened by recruiters (2 min, 10 hr, or 30 days later).
 */

const TRACKER_BASE_URL = "https://auto-mail-bot-bridge.uto-mail-bot.workers.dev";
const TRACKER_SECRET = ""; // Optional: set same TRACKER_SECRET if configured in Cloudflare
const LABEL_NAME = "✓✓ Read";

function normalizeSubj_(s) {
  return String(s || "").replace(/\s+/g, " ").trim().toLowerCase();
}

/**
 * Run this function ONCE from the Apps Script editor to install the 5-minute background trigger.
 */
function setupTrigger() {
  const triggers = ScriptApp.getProjectTriggers();
  for (const t of triggers) {
    if (t.getHandlerFunction() === "syncOpenedEmailsToGmailLabels") {
      ScriptApp.deleteTrigger(t);
    }
  }
  ScriptApp.newTrigger("syncOpenedEmailsToGmailLabels")
    .timeBased()
    .everyMinutes(5)
    .create();
  syncOpenedEmailsToGmailLabels();
  Logger.log("5-minute trigger installed and initial sync completed.");
}

function syncOpenedEmailsToGmailLabels() {
  const secretParam = TRACKER_SECRET ? `?secret=${encodeURIComponent(TRACKER_SECRET)}` : "";
  const resp = UrlFetchApp.fetch(`${TRACKER_BASE_URL}/track/opened${secretParam}`, {
    method: "get",
    muteHttpExceptions: true
  });

  if (resp.getResponseCode() !== 200) {
    Logger.log("Tracker fetch error: " + resp.getResponseCode() + " " + resp.getContentText());
    return;
  }

  const data = JSON.parse(resp.getContentText());
  const items = data.items || [];
  if (items.length === 0) return;

  let label = GmailApp.getUserLabelByName(LABEL_NAME);
  if (!label) {
    label = GmailApp.createLabel(LABEL_NAME);
  }

  const labeledIds = [];
  const now = Date.now();

  for (const item of items) {
    const toEmail = (item.to_email || "").trim();
    const targetSubj = normalizeSubj_(item.subject);
    if (!toEmail) continue;

    // Search up to 15 Sent threads for this recipient (handles repeat HR contacts & 10hr+ delays)
    const threads = GmailApp.search(`in:sent to:${toEmail}`, 0, 15);

    let matched = false;
    for (const thread of threads) {
      const threadSubj = normalizeSubj_(thread.getFirstMessageSubject());
      if (!targetSubj || threadSubj === targetSubj || threadSubj.includes(targetSubj) || targetSubj.includes(threadSubj)) {
        thread.addLabel(label);
        matched = true;
        break;
      }
    }

    // Mark labeled once applied, or expire unfindable threads only after 6+ hours so transient indexing delays don't drop labels
    if (matched || (threads.length === 0 && (now - Number(item.sent_at || now)) > 6 * 3600 * 1000)) {
      labeledIds.push(item.track_id);
    }
  }

  if (labeledIds.length > 0) {
    UrlFetchApp.fetch(`${TRACKER_BASE_URL}/track/mark-labeled${secretParam}`, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ track_ids: labeledIds }),
      muteHttpExceptions: true
    });
    Logger.log("Labeled " + labeledIds.length + " opened email(s) with " + LABEL_NAME);
  }
}
