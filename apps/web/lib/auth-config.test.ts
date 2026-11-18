import {afterEach,expect,it,vi} from 'vitest';
import {clerkConfigured} from './auth-config';
afterEach(()=>vi.unstubAllEnvs());
it('does not enable Clerk or keyless setup with missing keys',()=>{
 vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY','');vi.stubEnv('CLERK_SECRET_KEY','');
 expect(clerkConfigured()).toBe(false);
 vi.stubEnv('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY','synthetic-public');expect(clerkConfigured()).toBe(false);
 vi.stubEnv('CLERK_SECRET_KEY','synthetic-secret');expect(clerkConfigured()).toBe(true);
});
