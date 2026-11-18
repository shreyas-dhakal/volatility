import {expect,it} from 'vitest';
import {decisionBoundary,type Snapshot} from './design-engine';

it('compares the responsibility retained by the owner when its contract stays stable',()=>{
  const snapshot = (responsibility:string, rationale:string) => ({
    components:[{id:'billing',name:'Billing',owns:['tariff'],role:'manager',responsibility,rationale}],
    contracts:[],dependencies:[],
  } as unknown as Snapshot);
  const original=snapshot('Store the rate.','Site rates vary.');
  expect(decisionBoundary(original,'tariff')).not.toEqual(decisionBoundary(snapshot('Calculate the charge.','Site rates vary.'),'tariff'));
  expect(decisionBoundary(original,'tariff')).toEqual(decisionBoundary(snapshot('Store the rate.','The operator confirmed the rate.'),'tariff'));
});
