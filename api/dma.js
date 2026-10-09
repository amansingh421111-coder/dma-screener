// api/dma.js - one serverless function: accounts, Telegram connect/webhook, saving positions.
const crypto = require("crypto");
const { promisify } = require("util");
const scrypt = promisify(crypto.scrypt);

const E = Object.assign({}, process.env);
// match bot settings regardless of capitalization (Bot_token, bot_token, BOT_TOKEN ...)
for (const k of ["BOT_TOKEN", "BOT_USERNAME", "YOUTUBE_API_KEY"]) {
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

const HEX32 = /^[a-f0-9]{32}$/;
const HEX64 = /^[a-f0-9]{64}$/;
const SESSION_SECS = 60 * 60 * 24 * 30;
const sha = (s) => crypto.createHash("sha256").update(s).digest("hex");
const send = (res, body, code = 200, cookie) => {
  if (res.setHeader) {
    res.setHeader("Cache-Control", "no-store");
    if (cookie) res.setHeader("Set-Cookie", cookie);
  }
  return res.status(code).json(body);
};
const cookieFor = (token, maxAge) => `dma_s=${token}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${maxAge}`;
const clientIp = (req) => String((req.headers["x-forwarded-for"] || "").split(",")[0] || req.headers["x-real-ip"] || "unknown").trim();
const normName = (u) => String(u || "").trim().toLowerCase();
const NAME_RE = /^[a-z0-9_.-]{3,30}$/;

// rate limit: true while under the limit
const rl = async (key, max, secs) => {
  const n = await redis(["INCR", key]);
  if (n === 1) await redis(["EXPIRE", key, secs]);
  return n <= max;
};
const hashPw = async (pw, salt) => (await scrypt(pw, salt, 32)).toString("hex");
const sameHash = (a, b) => a.length === b.length && crypto.timingSafeEqual(Buffer.from(a, "hex"), Buffer.from(b, "hex"));

const parseCookies = (h) => Object.fromEntries(String(h || "").split(";").map((c) => c.trim().split(/=(.*)/s).slice(0, 2)).filter((p) => p[0]));
async function getSession(req) {
  const t = parseCookies(req.headers.cookie).dma_s;
  if (!t || !HEX64.test(t)) return null;
  const raw = await redis(["GET", "sess:" + sha(t)]);
  if (!raw) return null;
  let s; try { s = JSON.parse(raw); } catch (e) { return null; }
  const acct = await redis(["GET", "acct:" + s.u]);
  if (!acct) return null;
  const a = JSON.parse(acct);
  if (a.sv !== s.sv) return null;
  return { name: s.u, uid: a.uid, token: t };
}
async function newSession(name, sv) {
  const token = crypto.randomBytes(32).toString("hex");
  await redis(["SET", "sess:" + sha(token), JSON.stringify({ u: name, sv }), "EX", SESSION_SECS]);
  return token;
}
const checkPw = (pw) => (typeof pw !== "string" || pw.length < 8 ? "Password must be at least 8 characters." : pw.length > 128 ? "Password is too long." : null);

module.exports = async (req, res) => {
  try {
    const a = req.query.a;

    // Diagnostics (no secrets returned) and one-tap webhook registration
    if (a === "health" || a === "setup") {
      const host = req.headers["x-forwarded-host"] || req.headers.host;
      const out = { storage: !!(URL_ && TOK), bot_token: !!E.BOT_TOKEN, bot_username: E.BOT_USERNAME || null };
      if (E.BOT_TOKEN) {
        try {
          if (a === "setup") {
            const r = await fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/setWebhook`, { method: "POST", headers: { "content-type": "application/json" },
              body: JSON.stringify({ url: `https://${host}/api/dma`, allowed_updates: ["message"] }) });
            out.setWebhook = await r.json();
          }
          const w = await (await fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/getWebhookInfo`)).json();
          out.webhook_url = w.result && w.result.url; out.webhook_error = (w.result && w.result.last_error_message) || null;
          const me = await (await fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/getMe`)).json();
          out.bot_ok = !!me.ok; out.bot_real_username = me.ok ? me.result.username : null;
          out.username_matches = me.ok && String(E.BOT_USERNAME || "").replace("@", "").toLowerCase() === String(me.result.username).toLowerCase();
        } catch (e) { out.telegram_error = String(e.message || e); }
      }
      return send(res, out);
    }

    if (!URL_ || !TOK) return send(res, { error: "Storage is not connected to this project yet." }, 503);
    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};

    // Telegram calls this when someone messages the bot
    if (a === "hook" || body.update_id !== undefined) {
      const m = body.message;
      if (m && m.text && m.chat) {
        const chat = String(m.chat.id), text = m.text.trim();
        try { await redis(["SET", "cfg:bot", E.BOT_TOKEN]); } catch (e) {}
      const say = (t) => fetch(`https://api.telegram.org/bot${E.BOT_TOKEN}/sendMessage`, {
          method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ chat_id: chat, text: t }) });
        if (text.startsWith("/start")) {
          const tok = text.split(/\s+/)[1];
          const uid = tok && HEX32.test(tok) ? await redis(["GET", "link:" + tok]) : null;
          if (uid) {
            // one Telegram chat belongs to one account, and one account to one chat
            const prevUid = await redis(["GET", "uid:" + chat]);
            if (prevUid && prevUid !== uid) await redis(["DEL", "chat:" + prevUid]);
            const prevChat = await redis(["GET", "chat:" + uid]);
            if (prevChat && prevChat !== chat) await redis(["DEL", "uid:" + prevChat]);
            await redis(["SET", "chat:" + uid, chat]); await redis(["SET", "uid:" + chat, uid]); await redis(["DEL", "link:" + tok]);
            await say("✅ Connected. I'll message you here when a saved position hits its stop loss, target, or 44-DMA level. Send /stop to disconnect.");
          } else await say("To connect, open your 44-DMA Watch website, log in, go to My Positions and tap Connect Telegram.");
        } else if (text === "/stop") {
          const uid = await redis(["GET", "uid:" + chat]);
          if (uid) { await redis(["DEL", "chat:" + uid]); await redis(["DEL", "uid:" + chat]); }
          await say("Disconnected. You won't get position alerts here any more.");
        }
      }
      return send(res, { ok: true });
    }

    // everything below is called by the website itself
    if (req.method === "POST" && req.headers["x-dma"] !== "1") return send(res, { error: "Bad request." }, 400);
    const needPost = () => req.method !== "POST" && send(res, { error: "Use POST." }, 405);
    const ip = clientIp(req);

    if (a === "register") {
      if (needPost()) return;
      if (!(await rl("rl:reg:" + ip, 8, 3600))) return send(res, { error: "Too many sign-ups from here. Try again later." }, 429);
      const name = normName(body.username), pw = body.password;
      if (!NAME_RE.test(name)) return send(res, { error: "Username must be 3-30 characters: letters, numbers, . _ -" }, 400);
      const pe = checkPw(pw); if (pe) return send(res, { error: pe }, 400);
      if (await redis(["GET", "acct:" + name])) return send(res, { error: "That username is taken." }, 409);
      // carry over data created before accounts existed (key held only in this browser)
      let uid = null, claimed = false;
      const legacy = String(body.legacy_uid || "").toLowerCase();
      if (HEX32.test(legacy) && ((await redis(["GET", "pos:" + legacy])) || (await redis(["GET", "chat:" + legacy])))) {
        if ((await redis(["SET", "owner:" + legacy, name, "NX"])) === "OK") { uid = legacy; claimed = true; }
      }
      if (!uid) uid = crypto.randomBytes(16).toString("hex");
      const salt = crypto.randomBytes(16).toString("hex");
      const acct = { salt, hash: await hashPw(pw, salt), uid, sv: 1, created: Date.now() };
      if ((await redis(["SET", "acct:" + name, JSON.stringify(acct), "NX"])) !== "OK") {
        if (claimed) await redis(["DEL", "owner:" + uid]);
        return send(res, { error: "That username is taken." }, 409);
      }
      if (!claimed) await redis(["SET", "owner:" + uid, name]);
      await redis(["SADD", "users", uid]);
      const token = await newSession(name, 1);
      return send(res, { username: name, claimed }, 200, cookieFor(token, SESSION_SECS));
    }

    if (a === "login") {
      if (needPost()) return;
      if (!(await rl("rl:login:" + ip, 40, 900))) return send(res, { error: "Too many attempts. Try again in a few minutes." }, 429);
      const name = normName(body.username), pw = String(body.password || "");
      const failKey = "rl:fail:" + name;
      if (NAME_RE.test(name) && Number(await redis(["GET", failKey])) >= 8) return send(res, { error: "Too many wrong attempts for this account. Try again in 15 minutes." }, 429);
      const raw = NAME_RE.test(name) ? await redis(["GET", "acct:" + name]) : null;
      const acct = raw ? JSON.parse(raw) : null;
      const h = await hashPw(pw.slice(0, 128), acct ? acct.salt : "0".repeat(32));
      if (!acct || !sameHash(h, acct.hash)) {
        if (NAME_RE.test(name)) { const n = await redis(["INCR", failKey]); if (n === 1) await redis(["EXPIRE", failKey, 900]); }
        return send(res, { error: "Wrong username or password." }, 401);
      }
      await redis(["DEL", failKey]);
      const token = await newSession(name, acct.sv);
      return send(res, { username: name }, 200, cookieFor(token, SESSION_SECS));
    }

    if (a === "logout") {
      if (needPost()) return;
      const s = await getSession(req);
      if (s) await redis(["DEL", "sess:" + sha(s.token)]);
      return send(res, { ok: true }, 200, cookieFor("", 0));
    }

    const sess = await getSession(req);
    if (a === "me") return sess ? send(res, { username: sess.name }) : send(res, { error: "Not signed in." }, 401);
    if (!sess) return send(res, { error: "Please log in." }, 401);
    const uid = sess.uid;

    if (a === "passwd") {
      if (needPost()) return;
      const acct = JSON.parse(await redis(["GET", "acct:" + sess.name]));
      if (!sameHash(await hashPw(String(body.old || "").slice(0, 128), acct.salt), acct.hash)) return send(res, { error: "Current password is wrong." }, 401);
      const pe = checkPw(body.new); if (pe) return send(res, { error: pe }, 400);
      acct.salt = crypto.randomBytes(16).toString("hex"); acct.hash = await hashPw(body.new, acct.salt); acct.sv += 1;
      await redis(["SET", "acct:" + sess.name, JSON.stringify(acct)]);
      await redis(["DEL", "sess:" + sha(sess.token)]);
      const token = await newSession(sess.name, acct.sv);
      return send(res, { ok: true }, 200, cookieFor(token, SESSION_SECS));
    }

    if (a === "delete") {
      if (needPost()) return;
      const acct = JSON.parse(await redis(["GET", "acct:" + sess.name]));
      if (!sameHash(await hashPw(String(body.password || "").slice(0, 128), acct.salt), acct.hash)) return send(res, { error: "Password is wrong." }, 401);
      const chat = await redis(["GET", "chat:" + uid]);
      if (chat) await redis(["DEL", "uid:" + chat]);
      for (const k of ["chat:" + uid, "pos:" + uid, "ytnotes:" + uid, "owner:" + uid, "acct:" + sess.name, "sess:" + sha(sess.token)]) await redis(["DEL", k]);
      await redis(["SREM", "users", uid]);
      return send(res, { ok: true }, 200, cookieFor("", 0));
    }

    if (a === "status") return send(res, { connected: !!(await redis(["GET", "chat:" + uid])) });

    // ---- channel video list (YouTube Data API v3, official) + personal notes ----
    if (a === "yt") {
      if (!E.YOUTUBE_API_KEY) return send(res, { error: "YOUTUBE_API_KEY is not set in Vercel yet." }, 503);
      if (!(await rl("rl:yt:" + uid, 120, 3600))) return send(res, { error: "Too many requests this hour. Try again later." }, 429);
      const api = async (path, params) => {
        const u = new URL("https://www.googleapis.com/youtube/v3/" + path);
        for (const [k, v] of Object.entries({ ...params, key: E.YOUTUBE_API_KEY })) u.searchParams.set(k, v);
        const r = await fetch(u); const j = await r.json();
        if (!r.ok) throw Object.assign(new Error((j.error && j.error.message) || "YouTube API error"), { yt: true, code: r.status });
        return j;
      };
      try {
        let cid = String(req.query.channel || "").trim().slice(0, 200), uploads = String(req.query.uploads || "");
        if (!/^UU[\w-]{22}$/.test(uploads)) uploads = "";
        let ch = null;
        if (!uploads) {
          if (!cid) return send(res, { error: "Enter a channel link, @handle or channel ID." }, 400);
          let m;
          if ((m = cid.match(/(UC[\w-]{22})/))) ch = (await api("channels", { part: "snippet,contentDetails,statistics", id: m[1] })).items;
          else if ((m = cid.match(/@([\w.\-]{1,60})/))) ch = (await api("channels", { part: "snippet,contentDetails,statistics", forHandle: "@" + m[1] })).items;
          else {
            const sr = await api("search", { part: "snippet", type: "channel", q: cid.replace(/^https?:\/\/[^/]+\/(c\/|user\/)?/, ""), maxResults: 1 });
            const id = sr.items && sr.items[0] && sr.items[0].snippet.channelId;
            if (id) ch = (await api("channels", { part: "snippet,contentDetails,statistics", id })).items;
          }
          if (!ch || !ch[0]) return send(res, { error: "Channel not found. Try its @handle or the UC... channel ID." }, 404);
          ch = ch[0]; uploads = ch.contentDetails.relatedPlaylists.uploads;
        }
        const pl = await api("playlistItems", { part: "contentDetails", playlistId: uploads, maxResults: 50, ...(req.query.page ? { pageToken: String(req.query.page).slice(0, 100) } : {}) });
        const ids = pl.items.map((i) => i.contentDetails.videoId).filter((x) => /^[\w-]{11}$/.test(x));
        const vd = ids.length ? (await api("videos", { part: "snippet,contentDetails,statistics", id: ids.join(",") })).items : [];
        const videos = vd.map((v) => ({ id: v.id, title: v.snippet.title, published: v.snippet.publishedAt.slice(0, 10), duration: v.contentDetails.duration,
          views: +v.statistics.viewCount || 0, description: String(v.snippet.description || "").slice(0, 2500) }));
        return send(res, { channel: ch ? { id: ch.id, title: ch.snippet.title, uploads, videoCount: +ch.statistics.videoCount || 0 } : null, uploads, videos, next: pl.nextPageToken || null });
      } catch (e) {
        return send(res, { error: e.yt ? e.message : "Could not reach YouTube." }, e.yt && e.code === 403 ? 403 : 502);
      }
    }

    if (a === "ytnotes") {
      if (req.method === "GET") { const raw = await redis(["GET", "ytnotes:" + uid]); return send(res, raw ? JSON.parse(raw) : { notes: {} }); }
      if (needPost()) return;
      const n = body.notes;
      if (!n || typeof n !== "object" || Array.isArray(n)) return send(res, { error: "Invalid notes." }, 400);
      const clean = {}; let size = 0;
      for (const [k, v] of Object.entries(n)) {
        if (!/^[\w-]{11}$/.test(k)) continue;
        const o = { title: String(v.title || "").slice(0, 200), text: String(v.text || "").slice(0, 60000) };
        size += o.text.length + o.title.length; if (size > 900000) return send(res, { error: "Notes are too large (limit about 900 KB)." }, 413);
        clean[k] = o;
      }
      await redis(["SET", "ytnotes:" + uid, JSON.stringify({ notes: clean })]);
      return send(res, { saved: true });
    }

    if (a === "positions") {
      if (req.method === "GET") {
        const raw = await redis(["GET", "pos:" + uid]);
        return send(res, raw ? JSON.parse(raw) : { positions: [], ts: 0 });
      }
      const list = body.positions;
      if (!Array.isArray(list) || list.length > 200) return send(res, { error: "Invalid positions." }, 400);
      const clean = list.filter((p) => p && typeof p.symbol === "string").map((p) => ({
        id: String(p.id || "").replace(/[^a-z0-9]/gi, "").slice(0, 24),
        symbol: p.symbol.slice(0, 24).toUpperCase(), exchange: p.exchange === "BSE" ? "BSE" : "NSE",
        sellDate: /^\d{4}-\d{2}-\d{2}$/.test(String(p.sellDate || "")) ? String(p.sellDate) : "",
        sellPrice: +p.sellPrice > 0 ? +p.sellPrice : null,
        qty: +p.qty || 0, buy: +p.buy || 0, sl: p.sl == null ? null : +p.sl, target: p.target == null ? null : +p.target,
        date: String(p.date || "").slice(0, 10), thesis: String(p.thesis || "").slice(0, 120),
        alertMa: p.alertMa !== false, alertSl: p.alertSl !== false, alertTg: p.alertTg !== false }));
      await redis(["SET", "pos:" + uid, JSON.stringify({ positions: clean, ts: +body.ts || Date.now() })]);
      await redis(["SADD", "users", uid]);
      return send(res, { saved: true });
    }

    if (a === "link") {
      if (needPost()) return;
      if (!E.BOT_TOKEN || !E.BOT_USERNAME) return send(res, { error: "Telegram bot is not configured yet." }, 503);
      const t = crypto.randomBytes(16).toString("hex");
      await redis(["SET", "link:" + t, uid, "EX", 600]); await redis(["SADD", "users", uid]);
      // let the screener use the very same bot as this site (avoids a mismatched GitHub secret)
      await redis(["SET", "cfg:bot", E.BOT_TOKEN]);
      return send(res, { url: `https://t.me/${E.BOT_USERNAME.replace("@", "")}?start=${t}` });
    }

    if (a === "unlink") {
      if (needPost()) return;
      const chat = await redis(["GET", "chat:" + uid]);
      if (chat) { await redis(["DEL", "chat:" + uid]); await redis(["DEL", "uid:" + chat]); }
      return send(res, { connected: false });
    }
    return send(res, { error: "Unknown action." }, 404);
  } catch (e) {
    return send(res, { error: String(e.message || e) }, 500);
  }
};
