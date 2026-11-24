export class AlbumBuffer {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
  }

  async fetch(request) {
    const item = await request.json();
    const state = (await this.ctx.storage.get("state")) || { chat_id: item.chat_id, buckets: {} };
    state.chat_id = item.chat_id;

    // Group images sent together in a Telegram album (media_group_id),
    // or sent sequentially within the 3-second batch window.
    const bucketKey = item.media_group_id ? `mg_${item.media_group_id}` : "seq_batch";
    if (!state.buckets[bucketKey]) {
      state.buckets[bucketKey] = [];
    }

    const exists = state.buckets[bucketKey].some((x) => x.message_id === item.message_id);
    if (!exists) {
      state.buckets[bucketKey].push(item);
    }

    await this.ctx.storage.put("state", state);
    await this.ctx.storage.setAlarm(Date.now() + 3000);
    return new Response("Buffered", { status: 200 });
  }

  async alarm() {
    const state = await this.ctx.storage.get("state");
    if (!state || !state.buckets) return;

    const buckets = state.buckets;
    // Clear storage atomically before network dispatch so late arrivals start cleanly
    await this.ctx.storage.delete("state");

    const bucketList = Object.values(buckets).filter((arr) => Array.isArray(arr) && arr.length > 0);
    // Process oldest bucket first
    bucketList.sort((a, b) => Math.min(...a.map((x) => x.message_id)) - Math.min(...b.map((x) => x.message_id)));

    for (const items of bucketList) {
      items.sort((a, b) => (a.message_id || 0) - (b.message_id || 0));
      const first = items[0];
      const combinedCaption = items
        .map((x) => (x.caption || "").trim())
        .filter(Boolean)
        .join("\n")
        .trim();

      const payload = {
        update_id: first.update_id || 0,
        message_id: first.message_id || 0,
        chat_id: String(state.chat_id || first.chat_id || ""),
        text: "",
        caption: combinedCaption,
        photo_file_id: items.length === 1 ? first.file_id : "",
        image_items: items.map((x, idx) => ({
          file_id: x.file_id,
          name: x.doc_name || `img_${idx + 1}.jpg`,
          caption: x.caption || ""
        }))
      };

      await dispatchToGitHub(this.env, payload);
    }
  }
}

async function dispatchToGitHub(env, payload) {
  const token = env?.GITHUB_TOKEN || "";
  const repo = env?.GITHUB_REPO || "SuperStricker/Auto_mail_bot";
  if (!token) {
    return { ok: false, status: 500, text: "Missing GITHUB_TOKEN secret in Cloudflare Worker" };
  }

  const githubUrl = `https://api.github.com/repos/${repo}/dispatches`;
  const dispatchBody = JSON.stringify({
    event_type: "telegram_job",
    client_payload: payload
  });

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
      return { ok: true, status: ghResponse.status, text: "OK" };
    }
    if (ghResponse.status !== 429 && ghResponse.status < 500) {
      break;
    }
    await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
  }

  const errText = ghResponse ? await ghResponse.text() : "No response";
  console.error("GitHub dispatch failed:", ghResponse?.status, errText);
  return { ok: false, status: ghResponse?.status || 500, text: errText };
}

function isImageDocument(doc) {
  if (!doc || !doc.file_id) return false;
  const mime = (doc.mime_type || "").toLowerCase();
  const fname = (doc.file_name || "").toLowerCase();
  return mime.startsWith("image/") || /\.(jpg|jpeg|png|webp|bmp|tiff)$/i.test(fname);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("🚀 Auto Mail Bot Telegram-to-GitHub Bridge (Album-Aware) is LIVE & ACTIVE!", {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" }
      });
    }

    try {
      const update = await request.json();
      const msg = update.message || update.channel_post;

      if (!msg) {
        return new Response("OK", { status: 200 });
      }

      const chatId = String(msg.chat?.id || "");
      const hasPhoto = Array.isArray(msg.photo) && msg.photo.length > 0;
      const hasImgDoc = isImageDocument(msg.document);

      // Buffer images through per-chat Durable Object so multi-screenshot albums merge into 1 job
      if ((hasPhoto || hasImgDoc) && env?.ALBUM_BUFFER && chatId) {
        const fileId = hasPhoto ? msg.photo[msg.photo.length - 1].file_id : msg.document.file_id;
        const item = {
          update_id: update.update_id || 0,
          message_id: msg.message_id || 0,
          media_group_id: msg.media_group_id || "",
          chat_id: chatId,
          file_id: fileId,
          doc_name: hasImgDoc ? (msg.document.file_name || "image.jpg") : "",
          caption: msg.caption || ""
        };
        const id = env.ALBUM_BUFFER.idFromName(chatId);
        const stub = env.ALBUM_BUFFER.get(id);
        await stub.fetch("https://album-buffer/add", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(item)
        });
        return new Response("Buffered image in album coordinator", { status: 200 });
      }

      // Text / Links dispatch immediately as separate independent jobs
      const slimPayload = {
        update_id: update.update_id || 0,
        message_id: msg.message_id || 0,
        chat_id: chatId,
        text: msg.text || "",
        caption: msg.caption || "",
        photo_file_id: hasPhoto ? msg.photo[msg.photo.length - 1].file_id : "",
        doc_file_id: msg.document?.file_id || "",
        doc_mime: msg.document?.mime_type || "",
        doc_name: msg.document?.file_name || ""
      };

      const res = await dispatchToGitHub(env, slimPayload);
      if (!res.ok) {
        return new Response(`GitHub dispatch error: ${res.text}`, { status: 500 });
      }
      return new Response("Dispatched to GitHub Actions successfully!", { status: 200 });
    } catch (err) {
      console.error("Worker error:", err.message);
      return new Response(`Worker internal error: ${err.message}`, { status: 500 });
    }
  }
};
