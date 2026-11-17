// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {Heading,Markdown,Text} from './ui';

afterEach(cleanup);

it('shows saved names, notes, and chat without long dashes',()=>{
 render(<><Heading level={1}>{'Existing project\u2014suppliers'}</Heading><Text>{'Plan'}{'\u2014'}{'expand'}</Text><Markdown>{'**Saved reply**\u2014review [source](https://example.com/source\u2014one)'}</Markdown></>);
 expect(screen.getByRole('heading').textContent).toBe('Existing project-suppliers');
 expect(screen.getByText('Plan-expand')).toBeTruthy();
 expect(document.body.textContent).not.toMatch(/[\u2013\u2014]/);
 expect(screen.getByRole('link',{name:'source'}).getAttribute('href')).toBe('https://example.com/source\u2014one');
});
