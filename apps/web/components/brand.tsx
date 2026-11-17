import Image from 'next/image';
import {HStack,Heading} from './ui';

/** Local vector artwork adapted from galvanise.dev/logo, independent of remote availability. */
export function Brand({level=2}:{level?:1|2}){
 return <HStack gap={3} vAlign="center"><Image src="/brand/galvanise.svg" alt="" width={370} height={540} unoptimized style={{width:'var(--spacing-6)',height:'auto',flexShrink:0}}/><Heading level={level}>Galvanise</Heading></HStack>;
}
