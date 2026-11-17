import '@stylexswc/webpack-plugin/stylex.css';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@astryxdesign/theme-neutral/theme.css';
import '@fontsource/figtree/400.css';
import '@fontsource/figtree/500.css';
import '@fontsource/figtree/600.css';
import '@fontsource/figtree/700.css';
import '@xyflow/react/dist/style.css';
import {ClerkProvider} from '@clerk/nextjs';
import {clerkConfigured,legacyAuth} from '../lib/auth-config';
import type { Metadata } from 'next';
export const metadata: Metadata = {title:'Galvanise - architecture workspace',description:'Discover business change. Design boundaries with evidence.'};
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en" data-theme="light"><body>{!legacyAuth()&&clerkConfigured()?<ClerkProvider signInUrl="/sign-in" signUpUrl="/sign-up" signInFallbackRedirectUrl="/" signUpFallbackRedirectUrl="/">{children}</ClerkProvider>:children}</body></html>; }
