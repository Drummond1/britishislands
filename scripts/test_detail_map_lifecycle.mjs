/** Real async render entrypoint: only the latest still-open profile may create a map. */
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../app.js',import.meta.url),'utf8');
const start=source.indexOf('function renderDetailMap(');
const actual=source.slice(start,source.indexOf('\n}\n',start)+2);
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(){
  let resolve; const pending=new Promise(r=>{resolve=r});
  let host={style:{}}; const built=[];
  const state={activeId:'a',detailMap:null};
  const context=vm.createContext({state,Number,document:{getElementById:id=>id==='detail-map'?host:null},ensureProj4:()=>pending,renderDetailMapInner:island=>built.push(island.id)});
  vm.runInContext(actual,context);
  return {context,state,built,resolve,setHost:h=>{host=h}};
}
const a={id:'a',lat:54,lng:-3},b={id:'b',lat:55,lng:-4};
{
 const f=fixture(); f.context.renderDetailMap(a); f.context.renderDetailMap(a); f.resolve(); await flush();
 assert.deepEqual(f.built,['a'],'stub/full/learning refreshes must create one map');
}
{
 const f=fixture(); f.context.renderDetailMap(a); f.state.activeId='b'; f.setHost({style:{}}); f.context.renderDetailMap(b); f.resolve(); await flush();
 assert.deepEqual(f.built,['b'],'slow projection setup must not create an earlier island map in the new host');
}
{
 const f=fixture(); f.context.renderDetailMap(a); f.state.activeId=null; f.resolve(); await flush();
 assert.deepEqual(f.built,[],'closed profiles must not create a map after projection setup');
}
console.log('PASS detail map: repeated renders, island switches and close during async setup');
