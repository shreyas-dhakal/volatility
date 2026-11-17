import {Suspense} from 'react';
import {SignUp} from '@clerk/nextjs';
import {redirect} from 'next/navigation';
import AuthFrame from '../../../components/auth-frame';
import AuthConfiguration from '../../../components/auth-configuration';
import {clerkConfigured,legacyAuth} from '../../../lib/auth-config';
export default function SignUpPage(){
 if(legacyAuth())redirect('/');
 if(!clerkConfigured())return <AuthConfiguration/>;
 return <AuthFrame title="Create your workspace account"><Suspense fallback={null}><SignUp appearance={{elements:{rootBox:{width:'100%'},cardBox:{width:'100%'},card:{width:'100%'}}}}/></Suspense></AuthFrame>;
}
