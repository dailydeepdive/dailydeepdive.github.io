// Daily Deep Dive (3D): Your Call poll API.
// Runs as a Cloudflare Worker with a D1 database bound as "DB" (database: dd-polls).
//
// GET  /results?q=<id>&voter=<id>  -> { count, voted, mine?, buckets?, median?, mean?, closed }
// POST /vote  { q, voter, prob }    -> same shape as /results after the vote is stored
//
// Question ids look like "13-20270315": the Your Call number, then the date the question
// resolves (YYYYMMDD). Voting closes at the end of that day (UTC). Results are only
// returned to a browser that has voted, or once the question has closed.

const ALLOWED_ORIGINS = ["https://dailydeepdive.github.io", "http://localhost:8765"];
const QUESTION_RE = /^(\d{1,4})-(\d{8})$/;
const VOTER_RE = /^[a-zA-Z0-9-]{16,64}$/;
const MAX_VOTES_PER_IP = 5; // per question: allows a household or office, blocks easy stuffing

function cors(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function json(body, status, origin) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...cors(origin) },
  });
}

function closesAt(q) {
  const m = QUESTION_RE.exec(q);
  if (!m) return null;
  const d = m[2];
  return Date.UTC(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8), 23, 59, 59);
}

async function sha256(text) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function summary(env, q, voter) {
  const closed = Date.now() > closesAt(q);
  const total = await env.DB.prepare("SELECT COUNT(*) AS n FROM votes WHERE question = ?").bind(q).first();
  const mineRow = voter
    ? await env.DB.prepare("SELECT prob FROM votes WHERE question = ? AND voter = ?").bind(q, voter).first()
    : null;
  const out = { count: total.n, voted: !!mineRow, closed };
  if (!mineRow && !closed) return out; // results stay hidden until this browser votes

  const rows = await env.DB.prepare(
    "SELECT prob, COUNT(*) AS n FROM votes WHERE question = ? GROUP BY prob ORDER BY prob"
  ).bind(q).all();
  const buckets = Array(21).fill(0);
  let sum = 0;
  for (const r of rows.results) { buckets[r.prob / 5] = r.n; sum += r.prob * r.n; }
  // median from the bucket counts
  let median = null;
  if (total.n > 0) {
    const half = (total.n - 1) / 2;
    let seen = 0, lo = null, hi = null;
    for (let i = 0; i < 21; i++) {
      const next = seen + buckets[i];
      if (lo === null && next > Math.floor(half)) lo = i * 5;
      if (hi === null && next > Math.ceil(half)) hi = i * 5;
      seen = next;
    }
    median = (lo + hi) / 2;
  }
  return { ...out, mine: mineRow ? mineRow.prob : null, buckets, median, mean: total.n ? sum / total.n : null };
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get("Origin") || "";
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(origin) });

    try {
      if (request.method === "GET" && url.pathname === "/results") {
        const q = url.searchParams.get("q") || "";
        const voter = url.searchParams.get("voter") || "";
        if (!QUESTION_RE.test(q)) return json({ error: "bad question id" }, 400, origin);
        if (voter && !VOTER_RE.test(voter)) return json({ error: "bad voter id" }, 400, origin);
        return json(await summary(env, q, voter), 200, origin);
      }

      if (request.method === "POST" && url.pathname === "/vote") {
        if (origin && !ALLOWED_ORIGINS.includes(origin)) return json({ error: "origin not allowed" }, 403, origin);
        const body = await request.json().catch(() => ({}));
        const q = String(body.q || "");
        const voter = String(body.voter || "");
        const prob = Number(body.prob);
        if (!QUESTION_RE.test(q)) return json({ error: "bad question id" }, 400, origin);
        if (!VOTER_RE.test(voter)) return json({ error: "bad voter id" }, 400, origin);
        if (!Number.isInteger(prob) || prob < 0 || prob > 100 || prob % 5 !== 0)
          return json({ error: "probability must be 0-100 in steps of 5" }, 400, origin);
        if (Date.now() > closesAt(q)) return json({ error: "voting has closed", ...(await summary(env, q, voter)) }, 409, origin);

        const ip = request.headers.get("CF-Connecting-IP") || "unknown";
        const ipHash = await sha256(q + "|" + ip);
        const perIp = await env.DB.prepare("SELECT COUNT(*) AS n FROM votes WHERE question = ? AND ip_hash = ?")
          .bind(q, ipHash).first();
        const existing = await env.DB.prepare("SELECT 1 FROM votes WHERE question = ? AND voter = ?").bind(q, voter).first();
        if (!existing && perIp.n >= MAX_VOTES_PER_IP)
          return json({ error: "vote limit reached from this network", ...(await summary(env, q, voter)) }, 429, origin);

        // One vote per browser per question; the first vote stands.
        await env.DB.prepare("INSERT INTO votes (question, voter, ip_hash, prob) VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING")
          .bind(q, voter, ipHash, prob).run();
        return json(await summary(env, q, voter), 200, origin);
      }

      return json({ error: "not found" }, 404, origin);
    } catch (err) {
      return json({ error: "server error" }, 500, origin);
    }
  },
};
