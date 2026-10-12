# Separate centimetre-scale roadside lag and broken edge crumbs. These are scene
# objects, not enlarged copies of approved R5D material grains. Dimensions metres.
protos=json.loads((ROOT.parent/'discrete_grains_r5/prototypes/fracture_solids.json').read_text());verts=[];faces=[];colors=[];rough=[]
palette=np.array([[.33,.28,.21],[.48,.425,.33],[.20,.185,.16],[.27,.22,.155],[.13,.135,.13]])
for k in range(8500):
 x=rng.uniform(-8.0,-3.12);y=rng.uniform(-.4,30);d=abs(x)-3.2
 if x>float(edge_y(y,-1)):continue
 # Lag concentrated in irregular outer shoulder pockets and along the edge.
 pocket=np.clip(.30+.55*field(x,y,.48,657)+.30*field(x,y,2.2,651),.035,.8)
 if rng.random()>pocket:continue
 diameter=float(np.exp(rng.uniform(np.log(.007),np.log(.031))));p=protos[int(rng.integers(0,len(protos)))];vv=np.array(p['vertices']);vv[:,0]*=diameter;vv[:,1]*=diameter*rng.uniform(.35,.9);thick=diameter*rng.uniform(.21,.43);vv[:,2]*=thick;ang=rng.uniform(0,math.tau);rot=np.array([[math.cos(ang),-math.sin(ang)],[math.sin(ang),math.cos(ang)]]);vv[:,:2]=vv[:,:2]@rot.T;z=float(terrain(x,y))-thick*rng.uniform(.4,.74);vv+=np.array([x,y,z]);off=len(verts);verts.extend(vv);faces.extend(tuple(off+i for i in face) for face in p['faces']);cc=np.ones((len(vv),4));base=palette[int(rng.choice(5,p=[.30,.26,.12,.25,.07]))]*rng.uniform(.88,1.13);cc[:,:3]=base*.76+np.array([.29,.231,.16])*.24;colors.extend(cc);rough.extend([rng.uniform(.68,.84)]*len(vv))
ob=mesh('Sparse physical 7–31 mm roadside mineral lag',verts,faces,material=proto[0].data.materials[0],smooth=False);ca=ob.data.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');ca.data.foreach_set('color',np.asarray(colors,dtype='f4').ravel());ra=ob.data.attributes.new('grain_roughness','FLOAT','POINT');ra.data.foreach_set('value',np.asarray(rough,dtype='f4'))
print('ROADSIDE_LAG',len(faces),'triangles',flush=True)
