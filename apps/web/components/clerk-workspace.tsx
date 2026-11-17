'use client';
import {useEffect,useState} from 'react';
import {useAuth,useClerk,UserButton} from '@clerk/nextjs';
import {configureTokenGetter} from '../lib/api';
import Workspace from './workspace';
import {VStack,Text,Button,Heading} from './ui';

export default function ClerkWorkspace(){
 const {isLoaded,isSignedIn,userId,getToken}=useAuth();
 const {signOut}=useClerk();
 const [readyFor,setReadyFor]=useState<string|null>(null);
 useEffect(()=>{
  if(!isLoaded||!isSignedIn||!userId){setReadyFor(null);return}
  // A new getter identity also invalidates in-flight requests on account changes.
  configureTokenGetter(()=>getToken());setReadyFor(userId);
  return()=>configureTokenGetter(undefined);
 },[isLoaded,isSignedIn,userId,getToken]);
 if(!isLoaded)return <VStack padding={6}><Text>Checking your session…</Text></VStack>;
 if(!isSignedIn||!userId)return <VStack padding={6} gap={4}><Heading level={1}>Sign in to Galvanise</Heading><Button href="/sign-in" label="Sign in"/><Button href="/sign-up" label="Create account"/></VStack>;
 if(readyFor!==userId)return <VStack padding={6}><Text>Opening your workspace…</Text></VStack>;
 return <Workspace key={userId} clerkMode onSignOut={()=>signOut({redirectUrl:'/sign-in'})} accountControl={<UserButton/>}/>;
}
