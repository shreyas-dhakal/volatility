import {beforeEach,afterEach} from 'vitest';
import {configureTokenGetter} from './lib/api';
// Mock only the token boundary; application requests and transports remain real.
beforeEach(()=>configureTokenGetter(async()=>'isolated-test-token'));
afterEach(()=>configureTokenGetter(undefined));
