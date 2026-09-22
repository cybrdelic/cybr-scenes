precision highp float;
in vec3 position;
uniform mat4 uInvVP;
uniform vec3 uEye;
out vec3 vDirection;
void main(){
 vec4 q=uInvVP*vec4(position.xy,1.0,1.0);
 vDirection=q.xyz/q.w-uEye;
 gl_Position=vec4(position.xy,1.0,1.0);
}
