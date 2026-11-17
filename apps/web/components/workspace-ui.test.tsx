// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
vi.mock('@stylexjs/stylex',async original=>({...await original<object>(),create:(styles:Record<string,unknown>)=>Object.fromEntries(Object.keys(styles).map(k=>[k,{}]))}));
import {GitHubAction,NavigationItem,ReviewState} from './workspace-ui';
afterEach(cleanup);

it('keeps unavailable GitHub access disabled and explains how to enable it',()=>{
 render(<GitHubAction available={false}/>);
 const button=screen.getByRole('button',{name:'GitHub not set up'});
 expect(button.getAttribute('aria-disabled')).toBe('true');
 expect(button.getAttribute('href')).toBe(null);
 expect(screen.getByText('You can upload files now. GitHub can be set up later in Settings.')).toBeTruthy();
});

it('opens an available section and prevents navigation before a project exists',()=>{
 const open=vi.fn();const {rerender}=render(<NavigationItem view="Sources" active={false} available={false} onClick={open}/>);
 fireEvent.click(screen.getByRole('button',{name:'Files & code'}));expect(open).not.toHaveBeenCalled();
 rerender(<NavigationItem view="Sources" active available onClick={open}/>);
 const button=screen.getByRole('button',{name:'Files & code'});fireEvent.click(button);
 expect(open).toHaveBeenCalledOnce();expect(button.getAttribute('aria-current')).toBe('page');
 expect(button.querySelector('[data-color="blue"]')).toBeTruthy();
});

it('uses explicit review labels alongside status colors',()=>{
 const {rerender}=render(<ReviewState status="pending"/>);expect(screen.getByText('Needs review')).toBeTruthy();
 expect(screen.getByText('Needs review').closest('[data-review-state]')?.querySelector('[data-color="warning"]')).toBeTruthy();
 rerender(<ReviewState status="approved"/>);expect(screen.getByText('Approved')).toBeTruthy();
 rerender(<ReviewState status="rejected"/>);expect(screen.getByText('Not used')).toBeTruthy();
});

it('keeps the guided process and the original Designs navigation available independently',()=>{
 const open=vi.fn();render(<><NavigationItem view="Design process" active available onClick={open}/><NavigationItem view="Designs" active={false} available onClick={open}/></>);expect(screen.getByRole('button',{name:'Design process'}).getAttribute('aria-current')).toBe('page');expect(screen.getByRole('button',{name:'Designs'})).toBeTruthy();
});
