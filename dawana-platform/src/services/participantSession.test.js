import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { participantSessionKey,participantSessionClosed,reopenParticipantSession,notifyParticipantSessionClosed,subscribeParticipantSessionClosed,revokeParticipantSession } from './participantSession.js'
import { createRequestScope,assertParticipantAccess } from './requestScope.js'

function browserHarness() {
  const tabs=[],values=new Map(),channels=[]
  return {tab(){
    const listeners=new Map()
    const tab={listeners,addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name)},localStorage:{
      getItem:key=>values.get(key)??null,setItem(key,value){values.set(key,value);for(const other of tabs)if(other!==tab)other.listeners.get('storage')?.({key,newValue:value})},
      removeItem(key){values.delete(key);for(const other of tabs)if(other!==tab)other.listeners.get('storage')?.({key,newValue:null})}},
      BroadcastChannel:class{constructor(name){this.name=name;channels.push(this)}postMessage(data){for(const channel of channels)if(channel!==this&&channel.name===this.name&&!channel.closed)channel.onmessage?.({data})}close(){this.closed=true}},}
    tabs.push(tab);return tab
  },values,channels}
}

test('cross-tab closure carries no sensitive values, persists only a marker and cleans listeners',()=>{
  const env=browserHarness(),first=env.tab(),second=env.tab();let cleared=0
  const stop=subscribeParticipantSessionClosed(()=>cleared++,second)
  notifyParticipantSessionClosed(first)
  assert.ok(cleared>0);assert.equal(participantSessionClosed(second),true)
  assert.deepEqual([...env.values.keys()],[participantSessionKey])
  assert.match(env.values.get(participantSessionKey),/^\d+:[\d.]+$/)
  stop();const count=cleared;notifyParticipantSessionClosed(first);assert.equal(cleared,count)
  assert.equal(second.listeners.size,0);assert.ok(env.channels.every(channel=>channel.closed))
  reopenParticipantSession(first);assert.equal(participantSessionClosed(second),false)
})

test('logout broadcast does not invalidate its own tab or abort its revocation request', () => {
  const env = browserHarness(), first = env.tab(), second = env.tab()
  let own = 0, other = 0
  const stopOwn = subscribeParticipantSessionClosed(() => own++, first)
  const stopOther = subscribeParticipantSessionClosed(() => other++, second)
  notifyParticipantSessionClosed(first)
  assert.equal(own, 0)
  assert.ok(other > 0)
  stopOwn(); stopOther()
})
test('storage fallback works without BroadcastChannel and ignores Operations/Admin keys',()=>{
  const env=browserHarness(),first=env.tab(),second=env.tab();first.BroadcastChannel=undefined;second.BroadcastChannel=undefined
  let cleared=0;const stop=subscribeParticipantSessionClosed(()=>cleared++,second)
  first.localStorage.setItem('operations-session','marker');assert.equal(cleared,0)
  notifyParticipantSessionClosed(first);assert.equal(cleared,1);stop()
})
test('blocked storage still allows broadcast and never throws',()=>{
  const env=browserHarness(),first=env.tab(),second=env.tab();first.localStorage.setItem=()=>{throw Error('blocked')}
  let cleared=0;const stop=subscribeParticipantSessionClosed(()=>cleared++,second)
  notifyParticipantSessionClosed(first);assert.equal(cleared,1);stop()
})
test('failed server logout clears first and reports failure without a success claim',async()=>{
  const calls=[]
  await revokeParticipantSession({clear:()=>calls.push('clear'),revoke:async()=>{calls.push('revoke');throw Error('offline')},success:()=>calls.push('success'),failure:()=>calls.push('failure')})
  assert.deepEqual(calls,['clear','revoke','failure'])
  calls.length=0
  await revokeParticipantSession({clear:()=>calls.push('clear'),revoke:async()=>calls.push('revoke'),success:()=>calls.push('success'),failure:()=>calls.push('failure')})
  assert.deepEqual(calls,['clear','revoke','success'])
})
test('closure and camper switch invalidate responses even if transport ignores abort',async()=>{
  const scope=createRequestScope();const old=scope.begin();let resolve
  const pending=new Promise(done=>{resolve=done}).then(()=>scope.assert(old))
  scope.invalidate();const next=scope.begin();resolve()
  await assert.rejects(pending,{name:'AbortError'});assert.equal(scope.current(next),true)
})
test('expiry invalidates before invoking clearing and prevents stale publication',()=>{
  const scope=createRequestScope(),ticket=scope.begin();let cleared=false
  assert.throws(()=>assertParticipantAccess(scope,ticket,0,()=>{cleared=true}),{name:'AbortError'})
  assert.equal(cleared,true);assert.equal(scope.current(ticket),false)
})
test('participant and feedback pages subscribe without touching Operations authentication',()=>{
  const portal=fs.readFileSync(new URL('../pages/ParticipantPortal.jsx',import.meta.url),'utf8')
  const feedback=fs.readFileSync(new URL('../pages/CamperFeedback.jsx',import.meta.url),'utf8')
  assert.match(portal,/subscribeParticipantSessionClosed/);assert.match(feedback,/subscribeParticipantSessionClosed/)
  assert.match(portal,/Retry server sign-out/);assert.match(portal,/server sign-out could not be confirmed/)
  const operations=fs.readFileSync(new URL('./operationsApi.js',import.meta.url),'utf8')
  assert.doesNotMatch(operations,/participantSession/)
})
