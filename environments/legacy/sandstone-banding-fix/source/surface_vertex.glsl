precision highp float;
uniform mat4 uVP;
in vec3 position;
in vec3 bakeNormal;
in vec3 giR;
in vec3 giG;
in vec3 giB;
in vec2 surface;
out vec3 vWorld;
out vec3 vNormal;
out vec3 vGiR;
out vec3 vGiG;
out vec3 vGiB;
out vec2 vSurface;
void main(){
 vWorld=position;vNormal=bakeNormal;
 vGiR=giR;vGiG=giG;vGiB=giB;vSurface=surface;
 gl_Position=uVP*vec4(position,1.0);
}
