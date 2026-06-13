---
name: site-experiences
description: "Use when interacting with a specific website, service, or platform repeatedly (social media, internal dashboards, niche APIs). Load or create a per-domain experience file under experiences/{domain}.md before doing non-trivial work on that site, and update it after each success/failure."
version: 1.0.0
author: Hermes Agent (pattern borrowed from eze-is/web-access references/site-patterns)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [social-media, site-knowledge, pattern-memory, cross-session, web-access-inspired]
    related_skills: [web-access]
---

# Site Experiences

A per-domain knowledge base for **operations the agent has done before** —
URL patterns that work, selectors that survive redesigns, anti-bot quirks,
rate limits, login states, and the pitfalls that bit you last time.

The shape is borrowed from `eze-is/web-access` (the
`references/site-patterns/{domain}.md` convention). The mechanism is
Hermes-native: this is just a **SKILL.md + a directory of free-form
markdown files** that the agent reads on demand, not a new code path.

## When to Use

Trigger on **any** of:

- User asks to do something on a named site ("post to Xiaohongshu",
  "scrape the ACME corp dashboard", "download a file from their CDN").
- User mentions a URL belonging to a site you have not worked on this session.
- A tool call returned an error, a CAPTCHA, a login wall, or an empty
  result on a site you've seen before — check the experience file
  **before** retrying the same path.
- You're about to do a non-trivial multi-step operation on a site for
  the second or later time in any session.

Do **not** use for:

- Generic web research where the site is incidental (use `web_search` /
  `web_extract` / `web-access` skill and forget about the site).
- Sites you have never interacted with AND will only touch once. The
  cost of reading + maintaining a file outweighs the benefit. Just do
  the task; if a second request for the same site comes, *then* create
  the file.

## Workflow

### 1. Discover

Before doing work on a site, list existing experience files:

```bash
ls ~/.hermes/skills/site-experiences/experiences/ 2>/dev/null
# or, from a fresh repo clone:
ls $(dirname $(which hermes))/../skills/site-experiences/experiences/ 2>/dev/null
```

Match by:

- **Exact domain** (`github.com`, `xiaohongshu.com`).
- **Alias tokens** in frontmatter (e.g. `aliases: [小红书, xhs, rednote]`
  — match the user's casual mention against the alias list).
- **Wildcard files** (`_default.md`, `_internal-tools.md`) for sites
  you don't yet have a dedicated file for. These carry only the
  *generic* anti-bot / session rules (cookies, rate-limit, etc.).

If a matching file exists → read it, note the `confidence` and
`updated` fields, then proceed. If `confidence: low` or `updated` is
older than 90 days, treat the contents as a hypothesis to test, not
truth.

If no file exists → proceed with the task, but **create one at the end**
(see step 4) — even if it's mostly empty, the next agent will thank
you.

### 2. Apply

Follow the **有效模式** section when it makes sense; ignore it when the
task is so trivial that the overhead of executing the recipe exceeds
the benefit (e.g. fetching one public URL → just curl it, don't run
the 4-step login dance).

Respect the **已知陷阱** section. If a recipe in the file says "X
fails because Y", do not waste a turn re-discovering that. Either work
around it, or escalate to the user immediately with a clear "this
site blocks automated access; manual step required" message — do not
silently retry.

### 3. Verify

After the operation, ask yourself three questions:

1. Did the recipe in the file actually work? → record in **Verification
   log** at the bottom of the file.
2. Did I learn something the file does not yet capture? → append to the
   appropriate section.
3. Did the recipe fail in a new way? → mark `stale: true` in frontmatter
   and append a "Suspected stale since YYYY-MM-DD" note at the top of
   the affected section.

### 4. Persist

Write or update the file. Frontmatter schema:

```yaml
---
domain: example.com        # canonical registrable domain
aliases: [别称, alias2]    # tokens users casually use for this site
updated: YYYY-MM-DD         # last time the file was actually edited
confidence: low|medium|high # agent's self-assessed reliability of contents
verified_on: YYYY-MM-DD     # last time a recipe in this file was tested end-to-end
stale: false                # flip to true if recipes have started failing
retire_after: YYYY-MM-DD    # optional: scheduled retirement (e.g. after a known redesign)
---
```

Body schema (any section may be empty, but the headers must exist so
the next agent knows where to write):

```markdown
## 平台特征
Architecture, anti-bot behavior, login requirement, content loading
mechanism (SSR/CSR/lazy), rate limits, geo-fences — facts only.

## 有效模式
Verified URL patterns, request shapes, selectors, auth flows,
session-cookie requirements. Each recipe must end with a single
sentence: "Verified on YYYY-MM-DD by <one-liner description of test>."

## 已知陷阱
What fails, why, and what to do instead. Format: "<symptom> → <root
cause> → <workaround>". Date each entry.

## When to retire
Conditions under which this entire file should be deleted / archived
(e.g. "site shut down", "platform switched to OAuth-only and the file
documents cookie auth"). The agent should treat a retired file as
"untrusted history" and start from scratch.

## Verification log
Append-only. One line per recipe trial:
  - 2026-06-13  POST /api/v2/note → 200, 12s, recipe in 有效模式 unchanged
  - 2026-06-13  GET /explore/x?token=... → 400, recipe no longer matches; investigating
```

## File Locations

The skill ships with this layout:

```
skills/social-media/site-experiences/
├── SKILL.md                    ← this file
├── experiences/                ← agent-managed per-domain files
│   ├── _default.md             ← generic rules that apply to any unknown site
│   ├── github.com.md           ← example: agent auto-created
│   └── <your-domain>.md        ← you create these as you work
└── templates/
    └── experience-template.md  ← the blank frontmatter + body skeleton
```

User-local additions live at `~/.hermes/skills/site-experiences/experiences/`
and are loaded by the same workflow (the user-local dir is checked
first, then the in-repo dir as a fallback for skills shipped with
Hermes).

## Conventions

- **Domain name in filename**: use the registrable domain
  (`xiaohongshu.com`, not `www.xiaohongshu.com` or
  `explore.xiaohongshu.com`). One file per site.
- **Subdomain or path-specific quirks** go in the same file, under a
  `## <subdomain or path>` sub-heading inside the relevant section.
- **Date every fact** — write the discovery date next to claims that
  may rot. Without dates, the next agent has no way to judge trust.
- **Cite the source** for non-obvious claims: "Confirmed in their
  developer changelog 2026-04-12", "Found by reading the JS bundle at
  /assets/main.abc123.js", "Stated by support email on 2026-05-03".
  An unverified recipe is a hypothesis, not a fact — and the file
  should make the difference visible.
- **Don't store secrets** in experience files. No API keys, no
  session cookies, no OAuth tokens. If a recipe needs a token,
  reference the env var name (`$GITHUB_TOKEN`) and let the user
  supply it.
- **Don't duplicate content** from other skills. If `web-access`
  already has a recipe for navigating Xiaohongshu, link to it, don't
  copy.

## Common Pitfalls

1. **Creating a file too early.** Don't open an experience file the
   first time you hear about a site. Only create one after you've
   actually done something non-trivial there — otherwise you'll end
   up with 50 empty `experiences/foo.com.md` files that all just say
   "TODO".
2. **Treating a file as truth.** The `confidence` and `updated`
   fields are there for a reason. A file with `confidence: low` and
   `updated: 2025-11-04` is a starting point, not gospel.
3. **Refusing to update `stale` files.** If a recipe stops working,
   flipping `stale: true` is the right move even if you don't have
   time to fix it. The next agent needs to know.
4. **Writing a recipe that worked *once*.** Single-shot success is
   anecdote. A recipe is "verified" only after the same code path
   succeeds ≥ 2 times across different sessions, or once with a clear
   record of the conditions (request shape, headers, expected
   response).
5. **Confusing "user-personal" with "agent-shared".** A recipe that
   works because *your* account has special permissions should be
   marked `confidence: low` for anyone else. Consider whether it
   belongs in a user-local file vs the in-repo file at all.

## Verification Checklist

Before claiming "I checked the experience file":

- [ ] I listed `~/.hermes/skills/site-experiences/experiences/` and
      matched by domain + alias, not just filename substring.
- [ ] I read the file's `confidence` and `updated` before applying any
      recipe from it.
- [ ] I noted the **Verification log** entries and respected any
      recent "this recipe no longer works" warnings.
- [ ] If I made the file dirty (added/changed a recipe), I committed
      the change in the same turn (for in-repo files) or noted that it
      lives in `~/.hermes/` (for user-local files).

Before closing the task:

- [ ] I either wrote/updated an experience file, or confirmed in the
      response why I deliberately didn't (e.g. "site touched once,
      not worth a file").
- [ ] Any `stale: true` flag I flipped is reflected in this turn's
      response, not silently buried in the file.
