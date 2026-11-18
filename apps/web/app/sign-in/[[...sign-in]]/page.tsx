import {Suspense} from 'react';
import {SignIn} from '@clerk/nextjs';
import {redirect} from 'next/navigation';
import AuthFrame from '../../../components/auth-frame';
import AuthConfiguration from '../../../components/auth-configuration';
import {clerkConfigured} from '../../../lib/auth-config';
export default function SignInPage(){
 if(!clerkConfigured())return <AuthConfiguration/>;
 return <AuthFrame title="Sign in to your workspace"><Suspense fallback={null}><SignIn appearance={{elements:{rootBox:{width:'100%'},cardBox:{width:'100%'},card:{width:'100%'}}}}/></Suspense></AuthFrame>;
}
