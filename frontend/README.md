# Frontend

Next.js App Router frontend for the AI Career Intelligence Platform.

## Running

```bash
cp .env.example .env.local
npm install
npm run dev
```

Requires the backend on `BACKEND_ORIGIN` (default `http://localhost:8000`). All browser traffic
goes to `localhost:3000`; `/api/*` is proxied to the backend, which is what makes the refresh
cookie same-site and lets it use `SameSite=Strict`.

## Scripts

| Script                 | Purpose                       |
| ---------------------- | ----------------------------- |
| `npm run dev`          | Development server            |
| `npm run lint`         | ESLint                        |
| `npm run format:check` | Prettier check (CI runs this) |
| `npm run test`         | Vitest over `lib/`            |
| `npm run build`        | Production build              |

## Auth model

The access token lives in a module variable in `lib/auth.ts` — never `localStorage`, never a
cookie this app sets. The refresh token is an httpOnly `__Host-` cookie the browser sends
automatically. On load the app calls `/auth/refresh`; a 401 there means "not signed in" and is the
normal first-visit path, not an error.

`lib/` is three modules with an acyclic dependency chain:

| Module    | Responsibility                                                          |
| --------- | ----------------------------------------------------------------------- |
| `http.ts` | The only place `fetch` is called. Returns `ApiResult<T>`, never throws. |
| `auth.ts` | Token store, single-flight refresh, login/register/logout.              |
| `api.ts`  | Attaches the bearer token, retries a 401 once, typed endpoints.         |

## Known limitation: multi-tab refresh

The backend rotates refresh tokens and treats a reused token as theft, revoking the whole token
family. `refreshAccessToken()` deduplicates concurrent refreshes, but only within one tab — two
tabs are two module instances.

If two tabs' access tokens expire and both refresh at the same moment, the second presents an
already-consumed token, reuse detection fires, and **the user is signed out everywhere**.

The window is narrow, because tokens issued at different times expire at different times and a new
tab's startup refresh does not disturb a tab holding a valid token. This is accepted for now.

The correct fix is server-side: a short grace window where the immediately-previous token is
accepted once without tripping reuse detection. That is a backend change and a deliberate security
trade-off, not a frontend workaround.
