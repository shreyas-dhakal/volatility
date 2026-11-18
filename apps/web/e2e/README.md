# Rendered chat acceptance test

From the repository root, install the locked dependencies and the Playwright Chromium browser, build the local account version of the workspace, and run the fixture.

```sh
npm ci
npx playwright install chromium
AUTH_MODE=legacy npm run build
npm run test:e2e --workspace @galvanise/web
```

The test starts a production Next.js server on an available loopback port. A browser-local API fixture handles every workspace request, including the multipart upload, streamed chat response, chunk lookup, revision history and planning result. The fixture exercises the browser workflow without a model, database, or hosted identity session.
