'use client';
import type {ReactNode} from 'react';
import {Center} from '@astryxdesign/core/Center';
import {Theme} from '@astryxdesign/core/theme';
import {themes,defaultThemeSlug} from '../../../astryx-themes';
import {VStack,Card,Text} from './ui';
import {Brand} from './brand';

// Astryx login template: retain the centered column, gap 4 and card padding 8.
export default function AuthFrame({title,children}:{title:string;children:ReactNode}){
 return <Theme theme={themes[defaultThemeSlug]} mode="light"><Center axis="both" padding={6} style={{minHeight:'100dvh',backgroundColor:'var(--color-background-body)'}}><VStack gap={4} hAlign="center" style={{width:'100%',maxWidth:'calc(var(--spacing-10) * 10)'}}><VStack gap={2} hAlign="center"><Brand level={1}/><Text color="secondary">{title}</Text></VStack><Card padding={8} width="100%"><VStack gap={4} hAlign="stretch">{children}</VStack></Card></VStack></Center></Theme>;
}
