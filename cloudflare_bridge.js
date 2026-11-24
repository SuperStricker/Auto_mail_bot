export default {
  async fetch(request, env) {
    // 1. Health check for GET requests
    if (request.method !== "POST") {
      return new Response("🚀 Auto Mail Bot Telegram-to-GitHub Bridge is LIVE & ACTIVE!", {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" }
      });
    }

    try {
      const update = await request.json();
      const msg = update.message || update.channel_post;

      // Ignore non-message updates cleanly
      if (!msg) {
        return new Response("OK", { status: 200 });
      }

      // Slim, shell-safe payload containing all fields needed for text, links, photos & image documents
      const slimPayload = {
        update_id: update.update_id || 0,
        message_id: msg.message_id || 0,
        chat_id: String(msg.chat?.id || ""),
        text: msg.text || "",
        caption: msg.caption || "",
        photo_file_id: msg.photo?.length ? msg.photo[msg.photo.length - 1].file_id : "",
        doc_file_id: msg.document?.file_id || "",
        doc_mime: msg.document?.mime_type || "",
        doc_name: msg.document?.file_name || ""
      };

      const token = env?.GITHUB_TOKEN || "";
      const repo = env?.GITHUB_REPO || "SuperStricker/Auto_mail_bot";
      if (!token) {
        return new Response("Missing GITHUB_TOKEN secret in Cloudflare Worker", { status: 500 });
      }

      const githubUrl = `https://api.github.com/repos/${repo}/dispatches`;
      const dispatchBody = JSON.stringify({
        event_type: "telegram_job",
        client_payload: slimPayload
      });

      // Retry up to 3 times on transient GitHub 429 / 5xx errors during message bursts
      let ghResponse = null;
      for (let attempt = 0; attempt < 3; attempt++) {
        ghResponse = await fetch(githubUrl, {
          method: "POST",
          headers: {
            "Accept": "application/vnd.github+json",
            "Authorization": `Bearer ${token}`,
            "User-Agent": "Telegram-GitHub-Bridge",
            "X-GitHub-Api-Version": "2022-11-28"
          },
          body: dispatchBody
        });

        if (ghResponse.ok) {
          return new Response("Dispatched to GitHub Actions successfully!", { status: 200 });
        }
        if (ghResponse.status !== 429 && ghResponse.status < 500) {
          break;
        }
        await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
      }

      const errText = ghResponse ? await ghResponse.text() : "No response";
      console.error("GitHub dispatch failed:", ghResponse?.status, errText);
      return new Response(`GitHub dispatch error: ${errText}`, { status: 500 });
    } catch (err) {
      console.error("Worker error:", err.message);
      return new Response(`Worker internal error: ${err.message}`, { status: 500 });
    }
  }
};
