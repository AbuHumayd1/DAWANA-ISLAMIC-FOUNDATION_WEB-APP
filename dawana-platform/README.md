# React + Vite

## Local DIC visual preview (no orders or payments)

The normal Vite server uses `/api/v1` and proxies to local Django at
`http://127.0.0.1:8000` unless `DJANGO_API_PROXY_TARGET` is set in its process.
Local and deployed Django have separate edition/category records. A closed local
edition does not indicate that deployed registration is closed.

To preview with the existing public staging categories and backend-selected fees:

```powershell
cd dawana-platform
node scripts/preview-dic-registration.mjs
```

Open **http://127.0.0.1:5179/dic/register**. This separate loopback-only server
fetches the public staging registration-options endpoint once using GET with no
credentials. It serves that unchanged response from memory and blocks all other
API, Admin and backend static requests before the Vite proxy. Participant entry,
review, editing and grouped checkout remain normal frontend behaviour; submitting
an order displays a read-only preview error. Recovery and real payment testing
are unavailable. This uses a separate browser origin/draft from port 5173.
Restart to refresh the pricing snapshot. Close the preview tab and press Ctrl+C
to stop. No settings, environment files, database records or build paths change.

If the script cannot reach Render, save only the JSON body of a successful public
`/api/v1/dic/registration-options/` GET response to a local file outside the repo
(no cookies, headers or tokens), then run:

```powershell
node scripts/preview-dic-registration.mjs --options-file "$env:TEMP\dic-registration-options.json"
```

The response must already say registration is open and contain categories. The
preview does not override availability, calculate prices, or grant tester access.
Do not use a direct Render API base or repoint the ordinary Vite proxy for this
preview: deployed tester cookies are not shared with localhost, Secure cookies
require HTTPS, and cross-origin cookie requests require compatible CORS, cookie
SameSite and CSRF trusted-origin settings. Real staging checkout should continue
through its existing deployed HTTPS frontend and tester login.

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend using TypeScript with type-aware lint rules enabled. Check out the [TS template](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) for information on how to integrate TypeScript and Oxlint's TypeScript related rules in your project.
