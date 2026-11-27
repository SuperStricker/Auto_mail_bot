/**
 * Gmail Read Labeler for shuaib.ali6347@gmail.com
 * 100% Free — Runs on Google Apps Script (script.google.com) every 5 minutes.
 * Automatically adds a "✓✓ Read" label to Sent emails opened by recipients.
 */

const TRACKER_BASE_URL = "https://auto-mail-bot-bridge.uto-mail-bot.workers.dev";
const TRACKER_SECRET = ""; // Optional: set same TRACKER_SECRET if configured in Cloudflare
const LABEL_NAME = "✓✓ Read";

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

  for (const item of items) {
    const toEmail = (item.to_email || "").trim();
    const subject = (item.subject || "").trim();
    if (!toEmail) continue;

    // Search Sent folder for matching recipient
    const query = `in:sent to:${toEmail}`;
    const threads = GmailApp.search(query, 0, 5);

    let matched = false;
    for (const thread of threads) {
      const threadSubj = (thread.getFirstMessageSubject() || "").trim();
      if (!subject || threadSubj === subject || threadSubj.includes(subject) || subject.includes(threadSubj)) {
        thread.addLabel(label);
        matched = true;
        break;
      }
    }

    // Mark labeled even if thread was deleted/archived so it doesn't loop forever
    if (matched || threads.length === 0) {
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
