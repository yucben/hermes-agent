---
domain: github.com
aliases: [gh, GitHub]
updated: 2026-06-13
confidence: medium
verified_on: 2026-06-13
stale: false
---

This file captures the **shape** of GitHub operations, not the latest
feature set. APIs change; the next agent should sanity-check
endpoints against current docs (`https://docs.github.com/rest`) before
relying on a recipe here.

## 平台特征
- **Architecture**: REST API at `api.github.com` (v3) + GraphQL at
  `api.github.com/graphql` (v4). Most CI-style operations have a REST
  equivalent.
- **Anti-bot**: very low. `gh` CLI works unauthenticated for public
  data; authenticated for everything else. Date observed: 2026-06-13.
- **Login requirement**: read public → no auth. Read private / write →
  PAT or `gh auth login`. OAuth app for user-facing apps.
- **Content loading**: fully SSR, no JS-shell traps on `api.github.com`.
  The website itself is a SPA but the data is the data.
- **Geo-fence**: none for public content. Some enterprise instances
  (`*.ghe.com`) have their own rate limits and base URLs.
- **Rate limit**: 60 req/h unauthenticated, 5000 req/h authenticated.
  GraphQL has a points-based limit (5000 points/h). Source:
  docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting,
  verified on 2026-06-13.

## 有效模式
- **List PRs on a repo**: `gh pr list -R owner/repo --state all --json
  number,title,url,author,state` — much faster than hitting
  `api.github.com/repos/{r}/pulls` directly. Verified on 2026-06-13
  against hermes-agent, langchain, and django repos.
- **Get file from default branch**: `gh api repos/{o}/{r}/contents/{path}
  --jq '.content' | base64 -d` — works without cloning. Verified on
  2026-06-13.
- **Create / update a file via API**:
  `PUT /repos/{o}/{r}/contents/{path}` with `message`, `content`
  (base64), `sha` (required for update, omit for create), `branch`.
  See `github-pr-workflow` skill for the full shell flow. Verified
  on 2026-06-13.
- **Clone, branch, commit, push, PR via `gh`** is the preferred path
  for any workflow that touches the working tree. Use the
  `github-pr-workflow` skill — it has the exact commands.

## 已知陷阱
- "API rate limit exceeded" with `X-RateLimit-Remaining: 0` → wait
  until `X-RateLimit-Reset` (unix seconds). Authenticate if
  unauthenticated. Date seen: 2026-06-13.
- 404 on `repos/{o}/{r}` despite the repo existing → typo, or the
  repo is private and the token doesn't have access. Try
  `gh repo view owner/repo` to get a clearer error. Date seen:
  2026-06-13.
- "Resource not accessible by integration" on a fine-grained PAT →
  the token's resource owner is wrong, or the repo is in an
  org that hasn't approved the integration. → re-create the PAT
  with the right resource owner, or use a classic PAT. Date seen:
  2026-06-13.
- `gh pr create` hangs at "Authentication required" → no SSH key or
  HTTPS credentials configured. → `gh auth login` first, or pass
  `--head` / `--base` to make it not push. Date seen: 2026-06-13.

## When to retire
- If GitHub ships a v2 REST API that deprecates v3 endpoints, the
  recipes here need a major rewrite, not a retirement. The shape
  (REST + GraphQL, token auth, `gh` CLI wrapper) has been stable
  for > 5 years and shows no signs of changing.
- If you find this file is more than 50% wrong on a re-read, that's
  a sign GitHub has shipped a major change — archive and rewrite
  from `docs.github.com`.

## Verification log
- 2026-06-13  Initial scaffold. Recipes marked medium confidence —
  these are well-documented public APIs and unlikely to rot
  quickly, but exact response shapes can drift.
