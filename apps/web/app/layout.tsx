import '@stylexswc/webpack-plugin/stylex.css';
import '@astryxdesign/core/reset.css';
import '@astryxdesign/core/astryx.css';
import '@xyflow/react/dist/style.css';
import {defaultThemeSlug} from '../../../astryx-themes';
import {ClerkProvider} from '@clerk/nextjs';
import {clerkConfigured} from '../lib/auth-config';
import type { Metadata } from 'next';
export const metadata: Metadata = {title:'Galvanise - architecture workspace',description:'Discover business change. Design boundaries with evidence.',icons:{icon:{url:'/brand/galvanise.svg',type:'image/svg+xml'}}};
export default function RootLayout({children}:{children:React.ReactNode}) { return <html lang="en" data-theme="light" data-astryx-theme={defaultThemeSlug}><body>{clerkConfigured()?<ClerkProvider appearance={{variables:{fontFamily:'var(--font-family-body)'}}} signInUrl="/sign-in" signUpUrl="/sign-up" signInFallbackRedirectUrl="/" signUpFallbackRedirectUrl="/">{children}</ClerkProvider>:children}</body></html>; }
