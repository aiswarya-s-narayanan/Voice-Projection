/* Portrait-specific head/hat motion. Coordinates match ambient_motion.py.
   The source renderer drives expressions only; this layer owns head rotation. */
(function (root) {
  'use strict';
  const radians = degrees => degrees * Math.PI / 180;
  const smoothstep = (a, b, x) => { const t = Math.max(0, Math.min(1, (x-a)/(b-a))); return t*t*(3-2*t); };
  class IdleBlink {
    constructor(random = Math.random) { this.random=random; this.next=null; }
    amount(seconds, idle=true) {
      if (!idle) { this.next=null; return 0; }
      if (this.next===null) this.next=seconds+2.5+3*this.random();
      const elapsed=seconds-this.next;
      if (elapsed<0) return 0;
      if (elapsed>=.24) {this.next=seconds+2.5+3*this.random();return 0;}
      if (elapsed<.08) return Math.sin(elapsed/.08*Math.PI/2)**2;
      if (elapsed<.12) return 1;
      return Math.cos((elapsed-.12)/.12*Math.PI/2)**2;
    }
  }
  // Close the original portrait's eyelids before the shared head/hat transform.
  // Speech frames never pass through this layer. No painted eyelid overlay.
  class BlinkRenderer {
    constructor() {this.canvas=document.createElement('canvas');this.context=this.canvas.getContext('2d',{willReadFrequently:true});}
    render(image, amount) {
      if (amount<=0) return image;
      const ctx=this.context, width=image.width,height=image.height;
      if (this.image!==image) {
        this.image=image;this.canvas.width=width;this.canvas.height=height;
        ctx.drawImage(image,0,0);
        const sx=width/1882,sy=height/3344;
        this.patches=[[844,357,45,18,34,-.10],[972,331,44,18,34,-.35]].map(([cx,cy,rx,ry,outer,slope])=>{
          const x0=Math.max(0,Math.floor((cx-rx-2)*sx)),x1=Math.min(width,Math.ceil((cx+rx+2)*sx));
          const y0=Math.max(0,Math.floor((cy-outer-rx*Math.abs(slope)-2)*sy)),y1=Math.min(height,Math.ceil((cy+outer+rx*Math.abs(slope)+2)*sy));
          return {cx,cy,rx,ry,outer,slope,sx,sy,x0,y0,pixels:ctx.getImageData(x0,y0,x1-x0,y1-y0),result:ctx.createImageData(x1-x0,y1-y0)};
        });
      }
      ctx.drawImage(image,0,0);
      for (const p of this.patches) {
        const {pixels,result}=p,w=pixels.width,h=pixels.height;
        for(let x=0;x<w;x++) {
          const u=((x+p.x0)/p.sx-p.cx)/p.rx;
          const closure=Math.min(1,amount)*Math.max(0,Math.min(1,(1-u*u)*2));
          const center=(p.cy+p.slope*((x+p.x0)/p.sx-p.cx))*p.sy;
          const inner=p.ry*p.sy,extent=p.outer*p.sy,compressed=inner*(1-.91*closure);
          for(let y=0;y<h;y++) {
            const dy=y+p.y0-center,absolute=Math.abs(dy);
            const distance=absolute>=extent?absolute:absolute<=compressed?
              absolute*inner/Math.max(compressed,.001):inner+(absolute-compressed)*(extent-inner)/(extent-compressed);
            const sourceY=Math.max(0,Math.min(h-1,center+Math.sign(dy)*distance-p.y0));
            const lo=Math.floor(sourceY),hi=Math.min(h-1,lo+1),mix=sourceY-lo,index=(y*w+x)*4;
            for(let channel=0;channel<4;channel++) result.data[index+channel]=pixels.data[(lo*w+x)*4+channel]*(1-mix)+pixels.data[(hi*w+x)*4+channel]*mix;
          }
        }
        ctx.putImageData(result,p.x0,p.y0);
      }
      this.canvas.avatarRevision=(this.canvas.avatarRevision||0)+1;
      return this.canvas;
    }
  }
  class MotionState {
    constructor() {
      this.last = null; this.activity = 0; this.tilt = 0; this.energy = 0;
      this.charm = 0; this.velocity = 0; this.gestureTime = 0; this.emotion = null; this.nod = 0; this.thinking = 0;
    }
    sample(seconds, speaking = false, emotion = 'neutral', energy = 0, preparing = false) {
      const dt = this.last === null ? 0 : Math.max(0, Math.min(.1, seconds-this.last));
      this.last = seconds;
      const ease = tau => 1-Math.exp(-dt/tau);
      this.activity += (Number(speaking)-this.activity)*ease(.7);
      this.thinking += (Number(preparing && !speaking)-this.thinking)*ease(.55);
      this.energy += ((speaking ? Math.max(0, Math.min(1, energy)) : 0)-this.energy)*ease(.18);
      if (speaking && this.emotion !== emotion) {this.gestureTime=0;this.emotion=emotion;}
      if (!speaking) this.emotion=null;
      this.gestureTime+=dt;
      const target = speaking ? ({thinking:-2.2,sad:1.1,happy:.9,suggestion:.65,curious:-1.4,
        concerned:.8,excited:-.7,reassuring:.5,skeptical:-2.4,surprise:-.5}[emotion] || 0) : this.thinking*(-1.8+.55*Math.sin(seconds*.85));
      this.tilt += (target-this.tilt)*ease(.55);
      // Phrase gesture rather than a constant repetitive bob. Both hat and face
      // receive this same transform, with speech energy providing small accents.
      const nodStrength={excited:.0032,reassuring:.0024,suggestion:.0022,happy:.0016,curious:.001}[emotion]||.0009;
      const nodTarget=speaking ? nodStrength*Math.sin(this.gestureTime*5)*Math.exp(-this.gestureTime/1.6) : 0;
      this.nod+=(nodTarget-this.nod)*ease(.18);
      const angle = radians(.5+.65*this.activity)*Math.sin(2*Math.PI*seconds/6.3)+radians(this.tilt)+radians(.25*this.thinking)*Math.sin(seconds*1.3);
      // Substeps keep the damped charm stable even after a slow/hidden frame.
      let remaining = dt;
      while (remaining > 1e-9) {
        const step = Math.min(.01, remaining);
        this.velocity += (42*(-angle-this.charm)-5.5*this.velocity)*step;
        this.charm += this.velocity*step;
        if (Math.abs(this.charm)>radians(8)) { this.charm = Math.sign(this.charm)*radians(8); this.velocity = 0; }
        remaining -= step;
      }
      return {
        angle, charm:this.charm,
        bob:.0006*this.activity*Math.sin(2*Math.PI*seconds/2.9)+.001*this.energy+this.nod+.0007*this.thinking*Math.sin(seconds*1.1),
        breath:Math.sin(2*Math.PI*seconds/4.8),
        lean:radians(.25)*(.75*Math.sin(2*Math.PI*seconds/8.7)+.25*Math.sin(2*Math.PI*seconds/13.1))
      };
    }
  }
  // Inverse mapping in normalized portrait coordinates; shared by both paths.
  function mapPoint(x, y, width, height, motion) {
    const aspect = width/height;
    const upper = 1-smoothstep(.65,.94,y), head = 1-smoothstep(.165,.235,y);
    const chest = Math.exp(-Math.pow((y-.285)/.12,2));
    let mx = x+motion.lean*(y-.91)*upper/aspect;
    let my = y-motion.lean*(x-.5)*upper*aspect;
    mx -= (x-.5)*.003*motion.breath*chest;
    my += .0011*motion.breath*upper;
    const dx = (mx-.49)*aspect, dy = my-.19;
    const hx = .49+(Math.cos(motion.angle)*dx+Math.sin(motion.angle)*dy)/aspect;
    const hy = .19-Math.sin(motion.angle)*dx+Math.cos(motion.angle)*dy+motion.bob;
    mx += (hx-mx)*head; my += (hy-my)*head;
    const cx=1118/1882, cy=345/3344, lx=(mx-cx)*aspect, ly=my-cy;
    const weight=(1-smoothstep(35/1882,72/1882,Math.abs(mx-cx)))*smoothstep(2/3344,25/3344,ly)*(1-smoothstep(195/3344,225/3344,ly));
    mx += ((Math.cos(motion.charm)*lx+Math.sin(motion.charm)*ly)/aspect+cx-mx)*weight;
    my += (-Math.sin(motion.charm)*lx+Math.cos(motion.charm)*ly+cy-my)*weight;
    return [mx,my];
  }
  class Renderer {
    constructor() {
      this.canvas = document.createElement('canvas');
      const gl = this.gl = this.canvas.getContext('webgl', {alpha:false, antialias:false, preserveDrawingBuffer:true});
      if (!gl) throw new Error('WebGL is unavailable');
      const vertex = `attribute vec2 position; varying vec2 uv;
        void main(){uv=vec2((position.x+1.0)*0.5,(1.0-position.y)*0.5);gl_Position=vec4(position,0,1);}`;
      const fragment = `precision highp float;
        varying vec2 uv; uniform sampler2D portrait; uniform vec4 crop;
        uniform float aspect, angle, charm, bob, breath, lean;
        void main(){
          vec2 p=crop.xy+uv*crop.zw;
          float upper=1.0-smoothstep(.65,.94,p.y), head=1.0-smoothstep(.165,.235,p.y);
          float chest=exp(-pow((p.y-.285)/.12,2.0));
          vec2 m=p+vec2(lean*(p.y-.91)*upper/aspect,-lean*(p.x-.5)*upper*aspect);
          m+=vec2(-(p.x-.5)*.003*breath*chest,.0011*breath*upper);
          vec2 d=vec2((m.x-.49)*aspect,m.y-.19);
          vec2 h=vec2(.49+(cos(angle)*d.x+sin(angle)*d.y)/aspect,.19-sin(angle)*d.x+cos(angle)*d.y+bob);
          m=mix(m,h,head);
          vec2 pivot=vec2(1118.0/1882.0,345.0/3344.0);
          vec2 local=vec2((m.x-pivot.x)*aspect,m.y-pivot.y);
          float weight=(1.0-smoothstep(35.0/1882.0,72.0/1882.0,abs(m.x-pivot.x)))
            *smoothstep(2.0/3344.0,25.0/3344.0,local.y)*(1.0-smoothstep(195.0/3344.0,225.0/3344.0,local.y));
          vec2 c=pivot+vec2((cos(charm)*local.x+sin(charm)*local.y)/aspect,-sin(charm)*local.x+cos(charm)*local.y);
          m=mix(m,c,weight);
          gl_FragColor=(m.x<0.0||m.y<0.0||m.x>1.0||m.y>1.0)?vec4(1):texture2D(portrait,m);
        }`;
      const shader = (type, code) => {
        const s=gl.createShader(type); gl.shaderSource(s,code); gl.compileShader(s);
        if (!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
        return s;
      };
      const program=this.program=gl.createProgram();
      gl.attachShader(program,shader(gl.VERTEX_SHADER,vertex)); gl.attachShader(program,shader(gl.FRAGMENT_SHADER,fragment));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
      gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,-1,1,1,-1,1,1]),gl.STATIC_DRAW);
      const position=gl.getAttribLocation(program,'position');
      gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position,2,gl.FLOAT,false,0,0);
      gl.bindTexture(gl.TEXTURE_2D,gl.createTexture());
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      this.locations=Object.fromEntries(['crop','aspect','angle','charm','bob','breath','lean'].map(name=>[name,gl.getUniformLocation(program,name)]));
      this.canvas.addEventListener('webglcontextlost', event=> {event.preventDefault(); this.lost=true;});
    }
    render(image, full, motion) {
      if (this.lost) throw new Error('Graphics context lost');
      const gl=this.gl, crop=full?[0,0,1,1]:[.24,0,.5,.35];
      const height=Math.round(720*image.height*crop[3]/(image.width*crop[2]));
      if (this.canvas.width!==720 || this.canvas.height!==height) {this.canvas.width=720;this.canvas.height=height;}
      gl.viewport(0,0,720,height);
      if (this.image!==image || this.imageRevision!==image.avatarRevision) {gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,image);this.image=image;this.imageRevision=image.avatarRevision;}
      gl.uniform4fv(this.locations.crop,crop); gl.uniform1f(this.locations.aspect,image.width/image.height);
      for (const name of ['angle','charm','bob','breath','lean']) gl.uniform1f(this.locations[name],motion[name]);
      gl.drawArrays(gl.TRIANGLES,0,6);
      return this.canvas;
    }
  }
  // Canvas fallback uses an inverse-mapped triangle mesh. It retains the same
  // attachment coordinates and pendulum when hardware acceleration is disabled.
  class CanvasRenderer {
    constructor() {this.canvas=document.createElement('canvas');this.context=this.canvas.getContext('2d');this.last=0;}
    render(image, full, motion) {
      const now=performance.now();
      if (this.image===image && this.full===full && now-this.last<40) return this.canvas;
      this.last=now; this.image=image; this.full=full;
      const crop=full?[0,0,1,1]:[.24,0,.5,.35], width=720;
      const height=Math.round(width*image.height*crop[3]/(image.width*crop[2]));
      if (this.canvas.width!==width || this.canvas.height!==height) {this.canvas.width=width;this.canvas.height=height;}
      const ctx=this.context;ctx.setTransform(1,0,0,1,0,0);ctx.fillStyle='white';ctx.fillRect(0,0,width,height);
      // Dense around the head/charm, coarser on the nearly stationary body.
      const columns=24, rows=full?48:32, vertices=[];
      for(let row=0;row<=rows;row++) {
        const fraction=row/rows;
        const v=full ? (fraction<.7 ? fraction/.7*.35 : .35+(fraction-.7)/.3*.65) : fraction;
        for(let col=0;col<=columns;col++) {
          const u=col/columns;
          const source=mapPoint(crop[0]+u*crop[2],crop[1]+v*crop[3],image.width,image.height,motion);
          vertices.push({x:u*width,y:v*height,sx:source[0]*image.width,sy:source[1]*image.height});
        }
      }
      const triangle=(a,b,c)=>{
        const sx=b.sx-a.sx,sy=b.sy-a.sy,tx=c.sx-a.sx,ty=c.sy-a.sy;
        const det=sx*ty-tx*sy;if(Math.abs(det)<1e-6)return;
        const dx=b.x-a.x,dy=b.y-a.y,ex=c.x-a.x,ey=c.y-a.y;
        const A=(dx*ty-ex*sy)/det,B=(dy*ty-ey*sy)/det,C=(ex*sx-dx*tx)/det,D=(ey*sx-dy*tx)/det;
        ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.beginPath();
        const mx=(a.x+b.x+c.x)/3,my=(a.y+b.y+c.y)/3;
        // Tiny overlap hides antialiasing seams between adjoining triangles.
        [a,b,c].forEach((p,i)=>{const length=Math.hypot(p.x-mx,p.y-my)||1;const x=p.x+1.5*(p.x-mx)/length,y=p.y+1.5*(p.y-my)/length;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});
        ctx.closePath();ctx.clip();
        ctx.setTransform(A,B,C,D,a.x-A*a.sx-C*a.sy,a.y-B*a.sx-D*a.sy);
        ctx.drawImage(image,0,0);ctx.restore();
      };
      for(let row=0;row<rows;row++)for(let col=0;col<columns;col++) {
        const i=row*(columns+1)+col;
        triangle(vertices[i],vertices[i+1],vertices[i+columns+1]);
        triangle(vertices[i+1],vertices[i+columns+2],vertices[i+columns+1]);
      }
      return this.canvas;
    }
  }
  root.AvatarMotion={IdleBlink,BlinkRenderer,MotionState,Renderer,CanvasRenderer,mapPoint};
  if (typeof module!=='undefined') module.exports=root.AvatarMotion;
})(globalThis);
