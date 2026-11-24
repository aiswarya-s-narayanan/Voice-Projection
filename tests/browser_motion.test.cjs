const test = require('node:test');
const assert = require('node:assert/strict');
const {MotionState,mapPoint} = require('../avatar_kiosk/web/motion.js');
const neutral = {angle:0,charm:0,bob:0,breath:0,lean:0};

test('hat and face share one rigid head rotation; feet stay anchored', () => {
  const state={...neutral,angle:.025,bob:.001};
  const hat=[.35,.05], face=[.48,.12], width=1882,height=3344;
  const a=mapPoint(...hat,width,height,state), b=mapPoint(...face,width,height,state);
  const distance=(p,q)=>Math.hypot((p[0]-q[0])*width,(p[1]-q[1])*height);
  assert.ok(Math.abs(distance(a,b)-distance(hat,face))<1e-8);
  assert.notDeepEqual(a,hat); assert.notDeepEqual(b,face);
  assert.deepEqual(mapPoint(.5,.99,width,height,state),[.5,.99]);
});
test('charm pivots at its attachment and does not distort face', () => {
  const state={...neutral,charm:.05}, anchor=[1118/1882,345/3344];
  assert.deepEqual(mapPoint(...anchor,1882,3344,state),anchor);
  assert.notDeepEqual(mapPoint(anchor[0],anchor[1]+.04,1882,3344,state),[anchor[0],anchor[1]+.04]);
  assert.deepEqual(mapPoint(.48,.12,1882,3344,state),[.48,.12]);
});
test('sentence changes and Stop ease motion instead of resetting it', () => {
  const state=new MotionState();
  for(let i=0;i<120;i++) state.sample(i/60,true,'happy',.5);
  const before=state.sample(2,true,'happy',.5);
  const changed=state.sample(2+1/60,true,'thinking',1);
  assert.ok(Math.abs(changed.angle-before.angle)<.003);
  const stopped=state.sample(2+2/60,false);
  assert.ok(Math.abs(stopped.angle-changed.angle)<.003);
  assert.ok(state.activity>.9);
  for(let i=123;i<720;i++) state.sample(i/60,false);
  assert.ok(state.activity<.00001);
});
test('pendulum lags the head and remains bounded across cadence changes', () => {
  for(const fps of [25,60,120]) {
    const state=new MotionState(); let lag=false;
    for(let i=0;i<fps*20;i++) {
      const motion=state.sample(i/fps,true,i<fps*10?'thinking':'happy',1);
      assert.ok(Number.isFinite(motion.charm));
      assert.ok(Math.abs(motion.charm)<=8*Math.PI/180);
      if(Math.abs(motion.charm+motion.angle)>.002) lag=true;
    }
    assert.ok(lag);
    assert.ok(Number.isFinite(state.sample(5000,false).charm));
  }
});

test('idle blink has a fast close, slower reopening and randomized rest', () => {
  const {IdleBlink}=require('../avatar_kiosk/web/motion.js');
  const blink=new IdleBlink(()=>.5);
  assert.equal(blink.amount(0),0);
  assert.equal(blink.next,4);
  assert.equal(blink.amount(3.99),0);
  assert.ok(Math.abs(blink.amount(4.04)-.5)<1e-10);
  assert.equal(blink.amount(4.1),1);
  assert.ok(Math.abs(blink.amount(4.18)-.5)<1e-10);
  assert.equal(blink.amount(4.25),0);
  assert.equal(blink.next,8.25);
});
test('speech cancels a blink and the next idle period waits before blinking', () => {
  const {IdleBlink}=require('../avatar_kiosk/web/motion.js');
  const blink=new IdleBlink(()=>0);
  blink.amount(0);
  assert.equal(blink.amount(2.6),1);
  assert.equal(blink.amount(2.61,false),0);
  assert.equal(blink.next,null);
  assert.equal(blink.amount(20),0);
  assert.equal(blink.next,22.5);
  assert.equal(blink.amount(1000),0); // no frozen blink after a hidden tab resumes
});

test('phrase gestures distinguish excitement and reassurance and settle after Stop', () => {
  const excited=new MotionState(),neutralState=new MotionState();
  let maximumDifference=0;
  for(let i=0;i<120;i++) {
    const a=excited.sample(i/60,true,'excited',.5),b=neutralState.sample(i/60,true,'neutral',.5);
    maximumDifference=Math.max(maximumDifference,Math.abs(a.bob-b.bob));
  }
  assert.ok(maximumDifference>.0005);
  for(let i=120;i<720;i++)excited.sample(i/60,false);
  assert.ok(Math.abs(excited.nod)<1e-8);
});

test('preparation has a distinct thinking tilt without speech activity, and eases away', () => {
  const thinking=new MotionState(),idle=new MotionState();
  for(let i=0;i<180;i++) {
    thinking.sample(i/60,false,'neutral',0,true);
    idle.sample(i/60,false);
  }
  assert.ok(thinking.tilt < -1);
  assert.equal(idle.tilt,0);
  assert.equal(thinking.activity,0);
  assert.equal(thinking.energy,0);
  assert.ok(thinking.thinking>.99);
  const before=thinking.sample(3,false,'neutral',0,true);
  const after=thinking.sample(3+1/60,true,'happy',.5,true);
  assert.ok(Math.abs(after.angle-before.angle)<.003);
  for(let i=182;i<720;i++)thinking.sample(i/60,false);
  assert.ok(thinking.thinking<.00001);
  assert.ok(Math.abs(thinking.tilt)<.00001);
});
