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

      // Ignore updates that don't have a message or post
      if (!update.message && !update.channel_post) {
        return new Response("OK", { status: 200 });
      }

      // GitHub Credentials from Environment Variable
      const token = env?.GITHUB_TOKEN || "";
      const repo = env?.GITHUB_REPO || "SuperStricker/Auto_mail_bot";

      // Forward to GitHub Actions via repository_dispatch
      const githubUrl = `https://api.github.com/repos/${repo}/dispatches`;

      const ghResponse = await fetch(githubUrl, {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${token}`,
          "User-Agent": "Telegram-GitHub-Bridge",
          "X-GitHub-Api-Version": "2022-11-28"
        },
        body: JSON.stringify({
          event_type: "telegram_job",
          client_payload: update
        })
      });

      if (!ghResponse.ok) {
        const errText = await ghResponse.text();
        console.error("GitHub dispatch failed:", errText);
        return new Response(`GitHub dispatch error: ${errText}`, { status: 500 });
      }

      return new Response("Dispatched to GitHub Actions successfully!", { status: 200 });
    } catch (err) {
      console.error("Worker error:", err.message);
      return new Response(`Worker internal error: ${err.message}`, { status: 500 });
    }
  }
};
