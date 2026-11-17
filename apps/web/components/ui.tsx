'use client';
import {Children,type ReactNode} from 'react';
import {Text as AstryxText,type TextProps} from '@astryxdesign/core/Text';
import {Heading as AstryxHeading,type HeadingProps} from '@astryxdesign/core/Heading';
import {Markdown as AstryxMarkdown,type MarkdownProps} from '@astryxdesign/core/Markdown';
import {displayText} from '../lib/text';

// Normalize presentation without changing stored documents, names, or history.
function textChildren(children:ReactNode):ReactNode{
 return Children.map(children,child=>typeof child==='string'?displayText(child):child);
}
export function Text({children,...props}:TextProps){
 return <AstryxText {...props}>{textChildren(children)}</AstryxText>;
}
export function Heading({children,...props}:HeadingProps){
 return <AstryxHeading {...props}>{textChildren(children)}</AstryxHeading>;
}
const punctuationPlugin={pattern:/[\u2013\u2014]/g,render:()=>'-'};
export function Markdown({children,inlinePlugins=[],...props}:MarkdownProps){
 return <AstryxMarkdown {...props} inlinePlugins={[punctuationPlugin,...inlinePlugins]}>{children}</AstryxMarkdown>;
}
export {VStack} from '@astryxdesign/core/VStack';
export {HStack} from '@astryxdesign/core/HStack';
export {Button} from '@astryxdesign/core/Button';
export {TextInput} from '@astryxdesign/core/TextInput';
export {TextArea} from '@astryxdesign/core/TextArea';
export {Selector} from '@astryxdesign/core/Selector';
export {FileInput} from '@astryxdesign/core/FileInput';
export {Card} from '@astryxdesign/core/Card';
