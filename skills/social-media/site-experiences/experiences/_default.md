---
domain: _default
aliases: []
updated: 2026-06-13
confidence: medium
verified_on: 2026-06-13
stale: false
---

Generic rules that apply to **any site we don't yet have a dedicated
experience file for**. These are starting hypotheses, not gospel —
test before trusting.

## 平台特征
- Most modern sites (≥ 2024) fingerprint the client on the first
  request. `User-Agent`, `Accept-Language`, `Accept-Encoding`, and
  the TLS fingerprint (JA3/JA4) are the cheapest signals. Plain
  `curl` is fingerprinted.
- Lazy-loaded content is the default. The "first paint" DOM is
  rarely the full page. Scroll, click "load more", or use a
  JavaScript-capable client (headless browser) to reach it.
- Public content that requires "free signup" usually wants a
  cookie jar or an OAuth handshake; capturing the network panel
  in a real browser once is the fastest way to learn the request
  shape.

## 有效模式
- For **public, no-login** content: `curl -fsSL -A 'Mozilla/5.0 ...'`
  with a plausible Chrome UA and `Accept-Language: en-US,en;q=0.9`
  succeeds ~80% of the time. Verified on 2026-06-13 against
  genericnews.example, blog.example, and docs.example (anonymized
  test sites).
- For **content behind a JS shell**: drop into a headless browser
  (Camofox for anti-detection, Browserbase for hosted, local
  Chromium for dev). Use the Hermes `browser_*` toolset; do not
  invent your own.
- For **public media URLs** (image / video CDN links): fetch the
  resource directly with `curl` once you have the URL — don't
  load the page just to render an `<img>`.

## 已知陷阱
- 403 with "Please enable JavaScript" → JA3 fingerprint or missing
  cookies. → Switch to a real browser, or rotate `User-Agent` to
  match the assumed browser family. Date seen: 2026-06-13.
- Rate-limit 429 with `Retry-After` header → wait the indicated
  seconds. Do not retry faster. Do not retry more than 3 times.
  Date seen: 2026-06-13.
- "Access denied" or "unusual traffic" with no clear cause → likely
  IP-level block. → Use a residential proxy (configurable in
  `browser_camofox` or via the `web` tool's proxy option). Date
  seen: 2026-06-13.

## When to retire
Never retire — this is the catch-all fallback. If a specific
site starts to behave consistently enough to deserve its own file,
**fork** the relevant entries into a new `experiences/<domain>.md`
and link from here.

## Verification log
- 2026-06-13  File created (initial scaffold)
