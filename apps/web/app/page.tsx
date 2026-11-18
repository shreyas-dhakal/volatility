import {Suspense} from 'react';
import {auth} from '@clerk/nextjs/server';
import ClerkWorkspace from '../components/clerk-workspace';
import AuthConfiguration from '../components/auth-configuration';
import {clerkConfigured} from '../lib/auth-config';

async function ProtectedWorkspace(){await auth.protect();return <ClerkWorkspace/>}
export default function Page(){
 if(!clerkConfigured())return <AuthConfiguration/>;
 return <Suspense fallback={null}><ProtectedWorkspace/></Suspense>;
}
