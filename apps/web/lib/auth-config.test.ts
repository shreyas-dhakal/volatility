import {afterEach,expect,it,vi} from 'vitest';
import {clerkConfigured,legacyAuth} from './auth-config';
afterEach(()=>vi.unstubAllEnvs());
it('does not enable Clerk or keyless setup with missing keys',()=>{
 vi.stubEnv('AUTH_MODE','clerk');vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY','');vi.stubEnv('CLERK_SECRET_KEY','');
 expect(legacyAuth()).toBe(false);expect(clerkConfigured()).toBe(false);
 vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY','synthetic-public');expect(clerkConfigured()).toBe(false);
 vi.stubEnv('CLERK_SECRET_KEY','synthetic-secret');expect(clerkConfigured()).toBe(true);
});
it('requires an explicit legacy deployment mode for rollback',()=>{
 vi.stubEnv('AUTH_MODE','');expect(legacyAuth()).toBe(false);
 vi.stubEnv('AUTH_MODE','legacy');expect(legacyAuth()).toBe(true);
});
