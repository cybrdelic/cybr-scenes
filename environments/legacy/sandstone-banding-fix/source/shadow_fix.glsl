// Depth must be sampled at high precision independently of float arithmetic.
// Compare at the actual texel centres, THEN interpolate comparison outcomes.
// Interpolating raw depths across occluder edges is not percentage-closer filtering.
vec4 swReceiverGaps(highp sampler2D depthMap,vec2 uv,vec3 receiver,vec2 slope,out vec2 f){
 ivec2 size=textureSize(depthMap,0);
 vec2 p=uv*vec2(size)-0.5;
 ivec2 b=ivec2(floor(p)); f=fract(p);
 ivec2 hi=size-ivec2(1);
 ivec2 c0=clamp(b,ivec2(0),hi),c1=clamp(b+ivec2(1,0),ivec2(0),hi);
 ivec2 c2=clamp(b+ivec2(0,1),ivec2(0),hi),c3=clamp(b+ivec2(1),ivec2(0),hi);
 vec4 z=vec4(texelFetch(depthMap,c0,0).r,texelFetch(depthMap,c1,0).r,
              texelFetch(depthMap,c2,0).r,texelFetch(depthMap,c3,0).r);
 vec4 r=receiver.zzzz+vec4(
   dot(slope,(vec2(c0)+0.5)/vec2(size)-receiver.xy),
   dot(slope,(vec2(c1)+0.5)/vec2(size)-receiver.xy),
   dot(slope,(vec2(c2)+0.5)/vec2(size)-receiver.xy),
   dot(slope,(vec2(c3)+0.5)/vec2(size)-receiver.xy));
 return r-z; // positive: actual occluder in front of the receiving plane
}
float swBilinear(vec4 v,vec2 f){return mix(mix(v.x,v.y,f.x),mix(v.z,v.w,f.x),f.y);}
float swShadow(highp sampler2D depthMap,mat4 sunVP,vec3 extent,vec3 P,vec3 Ng,float fallback){
 vec3 planeNormal=uSunViewRotation*Ng;
 // Faces turned away from the emitter cannot receive direct sunlight.
 if(planeNormal.z<=0.0)return 0.0;
 float cosSun=clamp(planeNormal.z,0.0,1.0);
 float texelMetres=max(extent.x,extent.y)*uSunTexel;
 // Offset by the depth footprint, not a display-space amount. This covers the
 // receiver's finite shadow texel without inflating bias with camera distance.
 float normalOffset=0.0015+min(0.010,0.5*texelMetres)*sqrt(max(0.0,1.0-cosSun*cosSun));
 vec4 projected=sunVP*vec4(P+Ng*normalOffset,1.0);
 vec3 q=projected.xyz/projected.w*0.5+0.5;
 if(any(lessThan(q,vec3(0)))||any(greaterThan(q,vec3(1))))return fallback;
 // Ng is the raster triangle's plane normal, not the smooth shading normal.
 // The latter gives a false depth slope and produces periodic self-shadow stripes.
 float z=(planeNormal.z<0.0?-1.0:1.0)*max(abs(planeNormal.z),0.06);
 vec2 slope=planeNormal.xy*extent.xy/(z*extent.z);
 q.z-=0.0015/extent.z+4.0/16777216.0;
 float weight=0.0,separationSum=0.0;
 for(int i=0;i<8;i++){
  float a=float(i)*2.39996323,r=sqrt((float(i)+0.5)/8.0);
  vec2 offset=vec2(cos(a),sin(a))*r*(0.10/extent.xy),f;
  vec4 gap=swReceiverGaps(depthMap,q.xy+offset,q,slope,f)*extent.z;
  // Continuous weighted blocker search avoids penumbra-size jumps when a
  // blocker enters a nearest-sampled texel or an eight-point search stencil.
  vec4 blocked=smoothstep(vec4(0.0001),vec4(0.004),gap);
  weight+=swBilinear(blocked,f);
  separationSum+=swBilinear(max(gap,vec4(0.0))*blocked,f);
 }
 float separation=weight>1e-5?separationSum/weight:0.0;
 vec2 radius=clamp(vec2(separation*0.00465)/extent.xy,vec2(uSunTexel*0.9),vec2(0.085)/extent.xy);
 float visible=0.0;
 for(int i=0;i<16;i++){
  float a=float(i)*2.39996323,r=sqrt((float(i)+0.5)/16.0);
  vec2 offset=vec2(cos(a),sin(a))*r*radius,f;
  vec4 gap=swReceiverGaps(depthMap,q.xy+offset,q,slope,f);
  visible+=swBilinear(step(gap,vec4(0.0)),f);
 }
 // Not restricted to 17 visibility values: each sample has fractional coverage.
 return visible/16.0;
}
