import Image from 'next/image';
import {HStack, Heading} from './ui';

export function Brand({level = 2}: {level?: 1 | 2}) {
  return (
    <HStack gap={2} vAlign="center">
      <Image src="/brand/galvanise.svg" alt="" width={370} height={540} unoptimized
        style={{width: 'var(--spacing-6)', height: 'auto', flexShrink: 0}} />
      <Heading level={level} weight="normal" style={{
        fontFamily: 'Stardom, Georgia, serif',
        fontSize: level === 1 ? 'var(--font-size-4xl)' : 'var(--font-size-2xl)',
        letterSpacing: '-0.025em',
      }}>Galvanise</Heading>
    </HStack>
  );
}
