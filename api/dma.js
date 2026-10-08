// Save this file in your GitHub repo as:  api/dma.js
// One serverless function that handles: Telegram connect, Telegram webhook, saving positions.
const crypto = require("crypto");
const E = Object.assign({}, process.env);
// match bot settings regardless of capitalization (Bot_token, bot_token, BOT_TOKEN ...)
for (const k of ["BOT_TOKEN", "BOT_USERNAME"]) {
  const name = Object.keys(process.env).find((n) => n.toUpperCase() === k);
  if (name && process.env[name]) E[k] = process.env[name].trim();
}
const URL_ = E.KV_REST_API_URL || E.UPSTASH_REDIS_REST_URL;
const TOK = E.KV_REST_API_TOKEN || E.UPSTASH_REDIS_REST_TOKEN;
const redis = async (cmd) => {
  const r = await fetch(URL_, { method: "POST", headers: { Authorization: "Bearer " + TOK }, body: JSON.stringify(cmd) });
  const j = await r.json();
  if (j.error) throw new Error(j.error);
  return j.result;
};
const send = (res, body, code = 200) => res.status(code).json(body);
const HEX32 = /^[a-f0-9]{32}$/;

module.exports = async (req, res) => {
  try {
    if (req.query.a === "health" && (!URL_ || !TOK)) return send(res, { storage: false, bot_token: !!E.BOT_TOKEN, bot_username: E.BOT_USERNAME || null });
    if (!URL_ || !TOK) return send(res, { error: "Storage is not connected to this project yet." }, 503);
    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    const a = req.query.a;

    // Telegram calls this when someone messages the bot
    if (a === "hook" || body.update_id !== undefined) {
      const m = body.message;
      if (m && m.text && m.chat) {
        const chat = String(m.chat.id), text = m.text.trim();
        const say = (t) => fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/sendMessage`, {
          method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ chat_id: chat, text: t }) });
        if (text.startsWith("/start")) {
          const tok = text.split(/\s+/)[1];
          const uid = tok && HEX32.test(tok) ? await redis(["GET", "link:" + tok]) : null;
          if (uid) {
            await redis(["SET", "chat:" + uid, chat]); await redis(["SET", "uid:" + chat, uid]); await redis(["DEL", "link:" + tok]);
            await say("✅ Connected. I'll message you here when a saved position hits its stop loss, target, or 44-DMA level. Send /stop to disconnect.");
          } else await say("To connect, open your 44-DMA Watch website, go to My Positions and tap Connect Telegram.");
        } else if (text === "/stop") {
          const uid = await redis(["GET", "uid:" + chat]);
          if (uid) { await redis(["DEL", "chat:" + uid]); await redis(["DEL", "uid:" + chat]); }
          await say("Disconnected. You won't get position alerts here any more.");
        }
      }
      return send(res, { ok: true });
    }

    // Diagnostics (no secrets returned) and one-tap webhook registration
    if (a === "health" || a === "setup") {
      const host = req.headers["x-forwarded-host"] || req.headers.host;
      const out = { storage: true, bot_token: !!E.BOT_TOKEN, bot_username: E.BOT_USERNAME || null };
      if (E.BOT_TOKEN) {
        try {
          if (a === "setup") {
            const r = await fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/setWebhook`, { method: "POST", headers: { "content-type": "application/json" },
              body: JSON.stringify({ url: `https://${host}/api/dma`, allowed_updates: ["message"] }) });
            out.setWebhook = await r.json();
          }
          const w = await (await fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/getWebhookInfo`)).json();
          out.webhook_url = w.result && w.result.url; out.webhook_error = w.result && w.result.last_error_message || null;
          const me = await (await fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/getMe`)).json();
          out.bot_ok = !!me.ok; out.bot_real_username = me.ok ? me.result.username : null;
          out.username_matches = me.ok && String(E.BOT_USERNAME || "").replace("@", "").toLowerCase() === String(me.result.username).toLowerCase();
        } catch (e) { out.telegram_error = String(e.message || e); }
      }
      return send(res, out);
    }

    const uid = String(req.headers["x-uid"] || "");
    if (!HEX32.test(uid)) return send(res, { error: "Missing or invalid sync key." }, 400);

    if (a === "status") return send(res, { connected: !!(await redis(["GET", "chat:" + uid])) });

    if (a === "positions") {
      if (req.method === "GET") {
        const raw = await redis(["GET", "pos:" + uid]);
        return send(res, raw ? JSON.parse(raw) : { positions: [], ts: 0 });
      }
      const list = body.positions;
      if (!Array.isArray(list) || list.length > 200) return send(res, { error: "Invalid positions." }, 400);
      const clean = list.filter((p) => p && typeof p.symbol === "string").map((p) => ({
        symbol: p.symbol.slice(0, 24).toUpperCase(), exchange: p.exchange === "BSE" ? "BSE" : "NSE",
        qty: +p.qty || 0, buy: +p.buy || 0, sl: p.sl == null ? null : +p.sl, target: p.target == null ? null : +p.target,
        date: String(p.date || "").slice(0, 10), thesis: String(p.thesis || "").slice(0, 120),
        alertMa: p.alertMa !== false, alertSl: p.alertSl !== false, alertTg: p.alertTg !== false }));
      await redis(["SET", "pos:" + uid, JSON.stringify({ positions: clean, ts: +body.ts || Date.now() })]);
      await redis(["SADD", "users", uid]);
      return send(res, { saved: true });
    }

    if (a === "link") {
      if (!E.BOT_TOKEN || !E.BOT_USERNAME) return send(res, { error: "Telegram bot is not configured yet." }, 503);
      const t = crypto.randomBytes(16).toString("hex");
      await redis(["SET", "link:" + t, uid, "EX", 600]); await redis(["SADD", "users", uid]);
      return send(res, { url: `https://t.me/${E.BOT_USERNAME.replace("@", "")}?start=${t}` });
    }

    if (a === "unlink") {
      const chat = await redis(["GET", "chat:" + uid]);
      if (chat) { await redis(["DEL", "chat:" + uid]); await redis(["DEL", "uid:" + chat]); }
      return send(res, { connected: false });
    }
    return send(res, { error: "Unknown action." }, 404);
  } catch (e) {
    return send(res, { error: String(e.message || e) }, 500);
  }
};
