/**
 * Cloudflare Worker: Zero-Server Telegram-to-GitHub Bridge
 * 
 * 100% Free Forever (Cloudflare Free Tier gives 100,000 requests/day).
 * 
 * Flow:
 * 1. You send a photo or link to @Shuaib_Job_Mailer_bot on Telegram.
 * 2. Telegram instantly sends a webhook to this Cloudflare Worker (takes ~50ms).
 * 3. This Worker forwards the message to GitHub API (repository_dispatch).
 * 4. GitHub Actions wakes up, processes the job, sends the email, and STOPS!
 * 
 * SETUP INSTRUCTIONS:
 * 1. Go to https://dash.cloudflare.com/ -> Workers & Pages -> Create Worker.
 * 2. Paste this code and click Save & Deploy.
 * 3. Go to Worker Settings -> Variables -> Add these secrets:
 *    - GITHUB_TOKEN: Your GitHub Personal Access Token (classic or fine-grained with 'repo' / 'contents: write' scope)
 *    - GITHUB_REPO: Your GitHub repo in format "username/Auto_mail_bot"
 * 4. Connect Telegram Webhook (run once in browser):
 *    https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<YOUR_WORKER_NAME>.workers.dev
 */

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Auto Mail Bot Telegram-to-GitHub Bridge Online", { status: 200 });
    }

    try {
      const update = await request.json();

      // Ensure it contains a message
      if (!update.message && !update.channel_post) {
        return new Response("OK", { status: 200 });
      }

      // Forward to GitHub Actions via repository_dispatch
      const githubUrl = `https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`;

      const ghResponse = await fetch(githubUrl, {
        method: "POST",
        headers: {
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
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

      return new Response("Dispatched to GitHub Actions", { status: 200 });
    } catch (err) {
      console.error("Worker error:", err.message);
      return new Response(err.message, { status: 500 });
    }
  }
};
