# Rendered chat acceptance test

From the repository root, configure Clerk and a Playwright storage-state file for a signed-in user, install the locked dependencies and Playwright Chromium browser, build the workspace, and run the fixture.

```sh
npm ci
npx playwright install chromium
npm run build
npm run test:e2e --workspace @galvanise/web
```

Set `CLERK_E2E_STORAGE_STATE` to the storage-state JSON created by signing in to the configured Clerk instance on `http://localhost`. The test starts a production Next.js server on an available loopback port. A browser-local API fixture handles every workspace request, including the multipart upload, streamed chat response, chunk lookup, revision history and planning result. The fixture exercises the workspace without a model or database while Clerk handles authentication.
