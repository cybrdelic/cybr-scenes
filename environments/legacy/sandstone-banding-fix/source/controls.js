/* Sandstone Walk navigation. GPL-2.0-only.
 * Z-up camera controller; independent of the immutable scene and lighting.
 * Pointer ownership is per ID: a held joystick never steals the look pointer.
 */
'use strict';
class SandstoneControls {
  constructor({camera, canvas, bounds, reference, onModeChange = () => {}}) {
    if (!camera?.isPerspectiveCamera || !canvas || !bounds || bounds.isEmpty()) {
      throw new TypeError('Navigation needs a perspective camera, canvas and nonempty bounds.');
    }
    this.camera = camera; this.canvas = canvas; this.bounds = bounds.clone();
    this.reference = reference; this.onModeChange = onModeChange;
    this.mode = 'walk'; this.yaw = 0; this.pitch = 0; this.tour = false;
    this.fast = false; this.walkY = reference.camera[1];
    this.keys = new Set(); this.pointers = new Map(); this.holds = new Map();
    this.stick = {id:null, x:0, y:0}; this.velocity = new THREE.Vector3();
    this.walkPose = null; this.orbitPose = null;
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    this.sceneRadius = Math.max(1, sphere.radius);
    this.target = sphere.center.clone();
    this.radius = this.sceneRadius * 2.6;
    this.minRadius = .35; this.maxRadius = this.sceneRadius * 24;
    this.orbitYaw = -.58; this.orbitPitch = .66;
    this.camera.far = Math.max(camera.far, this.maxRadius + this.sceneRadius * 3);
    this.abort = new AbortController();
    this.$ = id => document.getElementById(id);
    this.touch = matchMedia('(any-pointer: coarse)').matches || navigator.maxTouchPoints > 0;
    document.body.classList.toggle('touch-input', this.touch);
    const listen = (el, type, fn, options = {}) => {
      if (el) el.addEventListener(type, fn, {...options, signal:this.abort.signal});
    };
    this.listen = listen;
    listen(canvas, 'pointerdown', e => this.pointerDown(e));
    listen(canvas, 'pointermove', e => this.pointerMove(e));
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      listen(canvas, type, e => this.release(e.pointerId));
    }
    listen(canvas, 'contextmenu', e => e.preventDefault());
    listen(canvas, 'wheel', e => this.wheel(e), {passive:false});
    listen(window, 'keydown', e => this.keyDown(e));
    listen(window, 'keyup', e => this.keys.delete(e.code));
    listen(window, 'blur', () => this.suspend());
    listen(document, 'visibilitychange', () => {if (document.hidden) this.suspend();});
    listen(window, 'resize', () => this.clearInput());
    listen(window, 'pagehide', () => this.suspend());
    this.bindStick();
    for (const button of document.querySelectorAll('[data-hold]')) this.bindHold(button);
    listen(this.$('nav-walk'), 'click', () => this.setNavigationMode('walk'));
    listen(this.$('nav-orbit'), 'click', () => this.setNavigationMode('orbit'));
    listen(this.$('home'), 'click', () => this.setReference());
    listen(this.$('reset'), 'click', () => this.setReference());
    listen(this.$('frame-canyon'), 'click', () => this.fit());
    listen(this.$('walk'), 'click', () => this.toggleTour());
    listen(this.$('boost'), 'click', () => {
      this.fast = !this.fast; this.$('boost').setAttribute('aria-pressed', String(this.fast));
    });
    listen(this.$('zoom-in'), 'click', () => this.zoom(.8));
    listen(this.$('zoom-out'), 'click', () => this.zoom(1.25));
    this.setReference();
  }
  center(y) {
    const route=this.reference.centerline;
    if (Array.isArray(route) && route.length>1) {
      let low=0,high=route.length-1;
      while(high-low>1){const mid=(low+high)>>1;if(route[mid][0]<=y)low=mid;else high=mid;}
      const a=route[low],b=route[high],t=THREE.MathUtils.clamp((y-a[0])/(b[0]-a[0]),0,1);
      return a[1]+(b[1]-a[1])*t;
    }
    const t = THREE.MathUtils.clamp((y - 17) / 13, 0, 1);
    return .4*Math.sin(y*.21) + 1.35*Math.exp(-Math.pow((y-18)/6.8,2))
      - .9*Math.exp(-Math.pow((y-30)/4.8,2)) + 6.2*t*t*(3-2*t);
  }
  aim(target) {
    const d = new THREE.Vector3(...target).sub(this.camera.position);
    if (d.lengthSq() < 1e-10) return;
    d.normalize(); this.yaw = Math.atan2(d.x, d.y);
    this.pitch = Math.asin(THREE.MathUtils.clamp(d.z, -1, 1)); this.look();
  }
  look() {
    const c = Math.cos(this.pitch), p = this.camera.position;
    this.camera.lookAt(p.x+Math.sin(this.yaw)*c, p.y+Math.cos(this.yaw)*c, p.z+Math.sin(this.pitch));
  }
  applyOrbit() {
    this.radius = THREE.MathUtils.clamp(this.radius, this.minRadius, this.maxRadius);
    this.orbitPitch = THREE.MathUtils.clamp(this.orbitPitch, -1.50, 1.50);
    const c = Math.cos(this.orbitPitch), r = this.radius;
    this.camera.position.set(this.target.x+r*Math.sin(this.orbitYaw)*c,
      this.target.y+r*Math.cos(this.orbitYaw)*c, this.target.z+r*Math.sin(this.orbitPitch));
    this.camera.lookAt(this.target);
  }
  fit() {
    if (this.mode !== 'orbit') {this.setNavigationMode('orbit'); return;}
    this.clearInput(); this.stopTour();
    this.bounds.getCenter(this.target);
    const halfY = THREE.MathUtils.degToRad(this.camera.fov * .5);
    const halfX = Math.atan(Math.tan(halfY) * this.camera.aspect);
    this.radius = Math.min(this.maxRadius, 1.08*this.sceneRadius/Math.sin(Math.min(halfX, halfY)));
    this.orbitYaw = -.58; this.orbitPitch = .66; this.applyOrbit();
  }
  setNavigationMode(mode) {
    if (mode !== 'walk' && mode !== 'orbit') throw new TypeError('Unknown navigation mode.');
    if (mode === this.mode) return;
    if (this.mode === 'walk') this.walkPose = {eye:this.camera.position.clone(), yaw:this.yaw, pitch:this.pitch};
    else this.orbitPose = {target:this.target.clone(), radius:this.radius, yaw:this.orbitYaw, pitch:this.orbitPitch};
    this.clearInput(); this.stopTour(); this.mode = mode;
    this.onModeChange(mode); // Projection changes before the fit calculation.
    if (mode === 'orbit') {
      if (this.orbitPose) {
        this.target.copy(this.orbitPose.target); this.radius = this.orbitPose.radius;
        this.orbitYaw = this.orbitPose.yaw; this.orbitPitch = this.orbitPose.pitch; this.applyOrbit();
      } else this.fit();
    } else if (this.walkPose) {
      this.camera.position.copy(this.walkPose.eye); this.yaw = this.walkPose.yaw;
      this.pitch = this.walkPose.pitch; this.look();
    }
    this.syncUI();
  }
  setReference() {
    this.setNavigationMode('walk'); this.clearInput(); this.stopTour();
    this.camera.position.fromArray(this.reference.camera); this.aim(this.reference.target);
    this.walkY = this.reference.camera[1]; this.syncUI();
  }
  setPose(eye, target) {
    if (![...eye,...target].every(Number.isFinite) || eye.length!==3 || target.length!==3) {
      throw new TypeError('Camera poses must be finite 3D vectors.');
    }
    this.setNavigationMode('walk'); this.clearInput(); this.stopTour();
    this.camera.position.fromArray(eye); this.aim(target);
  }
  stopTour() {this.tour = false; this.$('walk')?.setAttribute('aria-pressed', 'false');}
  toggleTour() {
    const next = !this.tour; this.setNavigationMode('walk'); this.clearInput();
    this.tour = next; this.walkY = THREE.MathUtils.clamp(this.camera.position.y, -5.8, 27.8);
    this.$('walk')?.setAttribute('aria-pressed', String(next));
  }
  syncUI() {
    document.body.dataset.navigation = this.mode;
    this.$('nav-walk')?.setAttribute('aria-pressed', String(this.mode==='walk'));
    this.$('nav-orbit')?.setAttribute('aria-pressed', String(this.mode==='orbit'));
    if (this.$('frame-canyon')) this.$('frame-canyon').hidden = this.mode !== 'orbit';
    if (this.$('gesture-help')) this.$('gesture-help').textContent = this.mode==='walk'
      ? (this.touch ? 'Left thumb: move · drag scene: look' : 'Drag: look · WASD: move · Q/E: height')
      : (this.touch ? 'Drag: orbit · pinch: zoom · two fingers: pan' : 'Drag: orbit · wheel: zoom · right-drag: pan');
  }
  showTouch(e) {
    if (e.pointerType==='touch' && !this.touch) {
      this.touch=true; document.body.classList.add('touch-input'); this.syncUI();
    }
  }
  capture(element, e) {
    // Capture can be lost on browser interruption; never leave a held input behind.
    try {element.setPointerCapture(e.pointerId);} catch (error) {
      if (error.name !== 'NotFoundError') throw error;
    }
  }
  pointerDown(e) {
    if (e.pointerType==='mouse' && ![0,1,2].includes(e.button)) return;
    if (this.pointers.size >= 2) return;
    e.preventDefault(); this.showTouch(e); this.stopTour();
    this.canvas.focus({preventScroll:true}); this.capture(this.canvas,e);
    this.pointers.set(e.pointerId,{x:e.clientX,y:e.clientY,button:e.button,shift:e.shiftKey});
  }
  pointerMove(e) {
    const p = this.pointers.get(e.pointerId); if (!p) return;
    e.preventDefault();
    const previous = [...this.pointers.values()].map(p=>({...p}));
    const dx=e.clientX-p.x, dy=e.clientY-p.y; p.x=e.clientX; p.y=e.clientY;
    if (this.pointers.size===2) {
      if (this.mode!=='orbit') return; // Two canvas fingers never fight walk-look.
      const [a,b]=previous, [c,d]=[...this.pointers.values()];
      const before=Math.hypot(a.x-b.x,a.y-b.y), after=Math.hypot(c.x-d.x,c.y-d.y);
      if (before>4 && after>4) this.zoom(before/after);
      this.pan((c.x+d.x-a.x-b.x)*.5,(c.y+d.y-a.y-b.y)*.5);
    } else if (this.mode==='walk') {
      const sensitivity=Math.PI/Math.max(320,this.canvas.clientHeight);
      this.yaw+=dx*sensitivity; this.pitch=THREE.MathUtils.clamp(this.pitch-dy*sensitivity,-1.46,1.46); this.look();
    } else if (p.button===1 || p.button===2 || p.shift || e.shiftKey) this.pan(dx,dy);
    else {
      const sensitivity=2*Math.PI/Math.max(320,this.canvas.clientHeight);
      this.orbitYaw-=dx*sensitivity; this.orbitPitch+=dy*sensitivity; this.applyOrbit();
    }
  }
  pan(dx,dy) {
    if (this.mode!=='orbit') return;
    this.camera.updateMatrixWorld(true);
    const units=2*this.radius*Math.tan(THREE.MathUtils.degToRad(this.camera.fov*.5))/Math.max(1,this.canvas.clientHeight);
    const right=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,0);
    const up=new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld,1);
    this.target.addScaledVector(right,-dx*units).addScaledVector(up,dy*units); this.applyOrbit();
  }
  zoom(factor) {
    if (this.mode!=='orbit' || !Number.isFinite(factor) || factor<=0) return;
    this.radius*=THREE.MathUtils.clamp(factor,.2,5); this.applyOrbit();
  }
  wheel(e) {
    e.preventDefault(); this.stopTour();
    const pixels=e.deltaY*(e.deltaMode===1?16:e.deltaMode===2?this.canvas.clientHeight:1);
    if (this.mode==='orbit') this.zoom(Math.exp(THREE.MathUtils.clamp(pixels*.0015,-1,1)));
    else {
      const step=THREE.MathUtils.clamp(-pixels*.003,-2,2);
      this.camera.position.x+=Math.sin(this.yaw)*step; this.camera.position.y+=Math.cos(this.yaw)*step; this.look();
    }
  }
  bindStick() {
    const pad=this.$('joystick'); if (!pad) return;
    this.listen(pad,'pointerdown',e=>{
      if (this.stick.id!==null || this.mode!=='walk') return;
      e.preventDefault(); this.showTouch(e); this.stopTour(); this.capture(pad,e);
      this.stick.id=e.pointerId; this.updateStick(e);
    });
    this.listen(pad,'pointermove',e=>{if (this.stick.id===e.pointerId) {e.preventDefault();this.updateStick(e);}});
    for(const type of ['pointerup','pointercancel','lostpointercapture']) this.listen(pad,type,e=>this.release(e.pointerId));
  }
  updateStick(e) {
    const rect=this.$('joystick').getBoundingClientRect(), radius=rect.width*.32;
    let x=(e.clientX-rect.left-rect.width*.5)/radius, y=(e.clientY-rect.top-rect.height*.5)/radius;
    const distance=Math.hypot(x,y), scale=distance>1?1/distance:1; x*=scale; y*=scale;
    const strength=THREE.MathUtils.clamp((distance-.12)/.88,0,1), normal=Math.hypot(x,y)||1;
    this.stick.x=x/normal*strength; this.stick.y=y/normal*strength;
    this.$('joystick-knob').style.transform=`translate(${x*radius}px,${y*radius}px)`;
    this.$('joystick').setAttribute('data-direction',`Side ${this.stick.x.toFixed(2)}, forward ${(-this.stick.y).toFixed(2)}`);
  }
  bindHold(button) {
    this.listen(button,'pointerdown',e=>{
      if(this.mode!=='walk')return;
      e.preventDefault();this.showTouch(e);this.stopTour();this.capture(button,e);
      this.holds.set(e.pointerId,{key:button.dataset.hold,element:button});button.classList.add('held');
    });
    for(const type of ['pointerup','pointercancel','lostpointercapture'])this.listen(button,type,e=>this.release(e.pointerId));
  }
  release(id) {
    const element=this.pointers.has(id)?this.canvas:this.holds.get(id)?.element;
    this.pointers.delete(id);this.holds.delete(id);
    if(this.stick.id===id){
      const pad=this.$('joystick');this.stick={id:null,x:0,y:0};this.velocity.set(0,0,0);
      this.$('joystick-knob').style.transform='translate(0px,0px)';pad.setAttribute('data-direction','Centered');
      if(pad.hasPointerCapture(id))pad.releasePointerCapture(id);
    }
    if(element){
      if(![...this.holds.values()].some(h=>h.element===element))element.classList.remove('held');
      if(element.hasPointerCapture(id))element.releasePointerCapture(id);
    }
  }
  clearInput() {
    const ids=new Set([...this.pointers.keys(),...this.holds.keys(),this.stick.id]);
    for(const id of ids)if(id!==null)this.release(id);
    this.keys.clear();this.velocity.set(0,0,0);
  }
  suspend(){this.clearInput();this.stopTour();}
  keyDown(e) {
    if (e.target.closest?.('input,select,textarea,button,[contenteditable="true"]')) return;
    if(e.code==='KeyR'){e.preventDefault();this.setReference();return;}
    if(e.code==='KeyO'){e.preventDefault();this.setNavigationMode(this.mode==='walk'?'orbit':'walk');return;}
    if(e.code==='KeyF' && this.mode==='orbit'){e.preventDefault();this.fit();return;}
    const moves=['KeyW','KeyA','KeyS','KeyD','KeyQ','KeyE','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','ShiftLeft','ShiftRight'];
    if(moves.includes(e.code)){e.preventDefault();this.keys.add(e.code);this.stopTour();}
  }
  update(delta) {
    const dt=THREE.MathUtils.clamp(delta,0,.05);if(!dt)return;
    const held=new Set([...this.holds.values()].map(h=>h.key));
    const down=(...codes)=>codes.some(c=>this.keys.has(c)||held.has(c));
    let f=Number(down('KeyW','ArrowUp'))-Number(down('KeyS','ArrowDown'))-this.stick.y;
    let r=Number(down('KeyD','ArrowRight'))-Number(down('KeyA','ArrowLeft'))+this.stick.x;
    let z=Number(down('KeyE'))-Number(down('KeyQ'));
    const length=Math.hypot(f,r,z);
    if(length>1){f/=length;r/=length;z/=length;}
    if(length>0){
      this.stopTour();const speed=this.fast||down('ShiftLeft','ShiftRight')?5:1.8;
      if(this.mode==='orbit') {this.pan(-r*dt*180,f*dt*180);this.target.z+=z*speed*dt;this.applyOrbit();}
      else {
        const v=new THREE.Vector3((Math.sin(this.yaw)*f+Math.cos(this.yaw)*r)*speed,
          (Math.cos(this.yaw)*f-Math.sin(this.yaw)*r)*speed,z*speed);
        this.velocity.lerp(v,1-Math.exp(-18*dt));this.camera.position.addScaledVector(this.velocity,dt);this.look();
      }
    } else {
      this.velocity.set(0,0,0);
      if(this.tour){
        this.walkY=Math.min(28,this.walkY+dt*.6);if(this.walkY>=28)this.stopTour();
        this.camera.position.set(this.center(this.walkY)-.15,this.walkY,1.56+.012*(this.walkY+5.8));
        this.aim([this.center(this.walkY+5),this.walkY+5,2.3+.012*(this.walkY+5.8)]);
      }
    }
  }
  snapshot() {
    return {mode:this.mode,eye:this.camera.position.toArray(),target:this.target.toArray(),
      quaternion:this.camera.quaternion.toArray(),radius:this.radius,near:this.minRadius,far:this.maxRadius,
      stick:[this.stick.x,this.stick.y],pointers:this.pointers.size,holds:this.holds.size,keys:this.keys.size,tour:this.tour};
  }
  dispose(){this.suspend();this.abort.abort();}
}
window.SandstoneControls=SandstoneControls;
