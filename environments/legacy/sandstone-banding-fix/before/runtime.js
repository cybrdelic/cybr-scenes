/* SPDX-License-Identifier: GPL-2.0-only
 * Verified, metric photographic receiving materials. Original geometry and
 * broad spectral irradiance buffers are retained. See docs/DETAIL_RENDERING.md.
 */
'use strict';
window.SandstoneDetail = class SandstoneDetail {
  static async create(renderer,{fragment,uniforms,status}) {
    const self=new SandstoneDetail();self.renderer=renderer;self.textures=[];
    const embedded=window.SW_DETAIL_ASSETS;
    const manifest=embedded?.manifest || await (async()=>{
      const r=await fetch('web/detail/manifest.json');if(!r.ok)throw new Error('Missing photographic material manifest');return r.json();
    })();
    if(manifest.schema!=='sandstone-walk-photographic-detail/1')throw new Error('Unsupported detail schema');
    const requested=Number(embedded?.resolution || 4096);
    self.resolution=Math.min(requested,renderer.capabilities.maxTextureSize)>=4096?4096:2048;
    if(embedded && self.resolution!==requested)throw new Error('This GPU needs the explicitly labelled 2K compact viewer. The 4K offline file has no hidden network fallback.');
    self.anisotropy=Math.min(Number(embedded?.anisotropy||16),renderer.capabilities.getMaxAnisotropy());
    self.manifest=manifest;
    self.uniforms={uDetail:{value:1},uParallax:{value:1},uMicroShadows:{value:1},uLinearOutput:{value:0},uSunViewRotation:{value:new THREE.Matrix3()},uGeometricSun:{value:0},uSunDepth:{value:null},uSunVP:{value:new THREE.Matrix4()},uSunExtent:{value:new THREE.Vector3(1,1,1)},uSunTexel:{value:1/4096},uNearSunDepth:{value:null},uNearSunVP:{value:new THREE.Matrix4()},uNearSunExtent:{value:new THREE.Vector3(1,1,1)}};
    async function read(entry) {
      if(embedded?.images?.[entry.url]){
        const text=embedded.images[entry.url];
        const binary=atob(text),bytes=new Uint8Array(binary.length);
        for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);
        delete embedded.images[entry.url];
        return bytes.buffer;
      }
      const r=await fetch(entry.url);if(!r.ok)throw new Error('Material map unavailable: '+entry.url);
      return r.arrayBuffer();
    }
    async function texture(entry,srgb) {
      const raw=await read(entry);if(raw.byteLength!==entry.bytes)throw new Error('Truncated material map');
      if(crypto?.subtle){
        const sum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',raw)),x=>x.toString(16).padStart(2,'0')).join('');
        if(sum!==entry.sha256)throw new Error('Material map hash mismatch: '+entry.url);
      }
      const bitmap=await createImageBitmap(new Blob([raw],{type:'image/webp'}),{
        imageOrientation:'flipY',premultiplyAlpha:'none',colorSpaceConversion:'none'});
      if(bitmap.width!==self.resolution||bitmap.height!==self.resolution){bitmap.close();throw new Error('Material size mismatch');}
      const t=new THREE.Texture(bitmap);t.flipY=false;t.colorSpace=srgb?THREE.SRGBColorSpace:THREE.NoColorSpace;
      t.wrapS=t.wrapT=THREE.RepeatWrapping;t.minFilter=THREE.LinearMipmapLinearFilter;t.magFilter=THREE.LinearFilter;
      t.anisotropy=self.anisotropy;t.generateMipmaps=true;t.needsUpdate=true;
      renderer.initTexture(t);
      t.userData.uploadedSize=[bitmap.width,bitmap.height];
      // All mip levels have been uploaded explicitly. The app treats context loss
      // as reload-required and never reuploads these images. Release CPU pixels.
      bitmap.close();t.userData.cpuBitmapReleased=true;
      self.textures.push(t);return t;
    }
    for(const [id,prefix] of [['rock_face_03','Rock'],['sandy_gravel','Sand']]) {
      if(status)status.textContent=`Loading ${self.resolution}² ${id.replaceAll('_',' ')} material`;
      const e=manifest.textures[id],maps=e.levels[String(self.resolution)];
      self.uniforms['u'+prefix+'Scale']={value:e.width_metres};
      self.uniforms['u'+prefix+'Relief']={value:e.parallax_height_metres};
      self.uniforms['u'+prefix+'Mean']={value:new THREE.Vector3(...e.linear_color_mean)};
      self.uniforms['u'+prefix+'ColorRough']={value:await texture(maps.color_rough,true)};
      self.uniforms['u'+prefix+'NormalHeightAO']={value:await texture(maps.normal_height_ao,false)};
    }
    const source=embedded?.shader || await (async()=>{const r=await fetch('web/detail/material.glsl');if(!r.ok)throw new Error('Detail shader unavailable');return r.text();})();
    if(globalThis.crypto?.subtle){
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(source))),x=>x.toString(16).padStart(2,'0')).join('');
      if(digest!==manifest.shader_sha256)throw new Error('Detail shader does not match its material manifest');
    }
    function patch(a,b){if(fragment.split(a).length!==2)throw new Error('Material integration anchor mismatch');fragment=fragment.replace(a,b);}
    patch('float fresnel(float c){',source+'\nfloat fresnel(float c){');
    patch(' SWMaterial material=swMaterial(vWorld,geometric,family,footprint);',
      ' float cavity,microVisibility;\n SWMaterial material=swPhotographicMaterial(vWorld,geometric,family,footprint,dx,dy,V,cavity,microVisibility);');
    patch('visibility=clamp(vSurface.x,0.0,1.0);','visibility=swSunVisibility(vWorld,geometric,clamp(vSurface.x,0.0,1.0))*microVisibility;');
    patch(' vec3 radiance=direct+indirect;',' indirect*=cavity;\n vec3 radiance=direct+indirect;');
    patch(' outColor=vec4(encodeNative(radiance),1.0);',' outColor=vec4(uLinearOutput==1?radiance*.25:encodeNative(radiance),1.0);');
    self.fragmentShader=fragment;Object.assign(uniforms,self.uniforms);
    self.ready=true;return self;
  }
  setEnabled(enabled){this.uniforms.uDetail.value=enabled?1:0;}
  dispose(){for(const t of this.textures){t.dispose();t.image.close?.();}this.textures=[];}
  report(){return {resolution:this.resolution,anisotropy:this.anisotropy,maps:this.textures.length,
    uncompressed_mip_bytes:Math.round(this.resolution*this.resolution*4*4*4/3),
    parallax:this.uniforms.uParallax.value===1,micro_shadows:this.uniforms.uMicroShadows.value===1,
    scan_enabled:this.uniforms.uDetail.value===1,geometry_changed:false,
    indirect_transport:'Reused macro spectral response; fine-scale scanned receiving material is not rebaked transport.'};}
};
