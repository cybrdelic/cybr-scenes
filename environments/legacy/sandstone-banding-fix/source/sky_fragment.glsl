precision highp float;
uniform sampler2D uSky;
uniform vec3 uWhite;
uniform vec3 uSun;
uniform vec3 uSolar;
uniform float uExposure;
in vec3 vDirection;
out vec4 outColor;
vec3 encodeNative(vec3 rgb){
 vec3 a=max(rgb/uWhite*uExposure,vec3(0.0));a=a*a/(a+vec3(.035));float p=max(max(a.r,a.g),max(a.b,.0000001));a*=(1.0-exp(-p))/p;
 a=clamp(a,0.0,1.0);return mix(12.92*a,1.055*pow(a,vec3(1.0/2.4))-.055,step(vec3(.0031308),a));
}
void main(){
 vec3 d=normalize(vDirection);vec2 uv=vec2(fract(atan(d.y,d.x)/6.28318530718+1.0),acos(clamp(d.z,-1.0,1.0))/3.14159265359);
 vec3 c=texture(uSky,uv).rgb;
 if(dot(d,uSun)>=.999989189)c+=uSolar/.000067928;
 outColor=vec4(encodeNative(c),1.0);
}
