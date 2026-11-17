import {clerkMiddleware} from '@clerk/nextjs/server';
import {NextResponse,type NextRequest,type NextFetchEvent} from 'next/server';
import {clerkConfigured,legacyAuth} from './lib/auth-config';
const withClerk=clerkMiddleware({signInUrl:'/sign-in',signUpUrl:'/sign-up'});
export default function proxy(request:NextRequest,event:NextFetchEvent){
 // Never invoke Clerk's development keyless path when host keys are absent.
 if(legacyAuth()||!clerkConfigured())return NextResponse.next();
 return withClerk(request,event);
}
export const config={matcher:[
 '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
 '/(api|trpc)(.*)',
 '/__clerk/(.*)',
]};
