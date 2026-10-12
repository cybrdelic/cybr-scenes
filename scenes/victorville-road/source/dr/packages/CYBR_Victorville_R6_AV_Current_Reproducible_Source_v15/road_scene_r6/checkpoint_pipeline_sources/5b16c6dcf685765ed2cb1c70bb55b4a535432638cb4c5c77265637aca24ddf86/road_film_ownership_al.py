"""AL: assign the preserved Z film inventory to its actual source substrate.

Z stores both soil and pavement stock. Reconstructed pavement must not inherit
an older soil bank's film solely because it is now visible at that world XY.
This is a representation ownership correction, not a new transport solve or a
smoothing operation. All source inventories and their full ledger are retained.
The original 25 mm ownership grid is still a bounded approximation.
"""
from pathlib import Path
import hashlib
import numpy as np

IMAGE = 'Z finite surface-film inventory / metres'

def split_inventory(fields):
    x=np.asarray(fields['x_m']);y=np.asarray(fields['y_m'])
    stock=np.asarray(fields['remaining_mobile_class_thickness_m'])
    p=np.asarray(fields['pavement'])
    if stock.shape!=(len(y),len(x),3) or p.shape!=stock.shape[:2]:raise ValueError('Z stock and ownership shapes differ')
    if not np.isfinite(stock).all() or np.any(stock<0):raise ValueError('Stock must be finite and nonnegative')
    if not np.all((p==0)|(p==1)):raise ValueError('Use the actual binary Z substrate classification')
    if len(x)<2 or len(y)<2 or not np.allclose(np.diff(x),np.diff(x)[0]) or not np.allclose(np.diff(y),np.diff(y)[0]) or min(np.diff(x).min(),np.diff(y).min())<=0:raise ValueError('Finite uniform metre axes required')
    road=np.where(p[...,None],stock,0);soil=stock-road
    assert np.array_equal(road+soil,stock)
    area=float((x[1]-x[0])*(y[1]-y[0]))
    receipt=dict(total_by_class_m3=(stock.sum((0,1))*area).tolist(),pavement_owned_by_class_m3=(road.sum((0,1))*area).tolist(),soil_owned_by_class_m3=(soil.sum((0,1))*area).tolist(),road_cells=int(p.sum()),soil_cells=int((~p.astype(bool)).sum()),soil_matrix_cells_removed_from_asphalt_representation=int(((~p.astype(bool))&(stock[...,0]>0)).sum()),conserved_split=True,transport_inventory_modified=False,grid_spacing_m=[float(x[1]-x[0]),float(y[1]-y[0])],limits='Historical source ownership at 25 mm grid resolution, not new transport or exact subcell coverage. Soil stock remains in its ledger; this does not promise every grain has a separate visible representation.')
    return road,soil,receipt

def apply(scene,config):
    import bpy
    path=Path(config['fields_path']);f=dict(np.load(path,allow_pickle=False))
    road,soil,report=split_inventory(f);original=bpy.data.images.get(IMAGE)
    if original is None:raise ValueError('Pinned Z film image is missing')
    ny,nx=road.shape[:2]
    if tuple(original.size)!=(nx,ny):raise ValueError('Z film image size changed')
    data=np.empty(nx*ny*4,dtype=np.float32);original.pixels.foreach_get(data);data=data.reshape(ny,nx,4)
    if not np.array_equal(data[:,:,0],f['remaining_mobile_class_thickness_m'][:,:,0].astype(np.float32)):raise ValueError('Image film stock does not match its retained source ledger')
    if not np.array_equal(data[:,:,2],f['pavement'].astype(np.float32)):raise ValueError('Image ownership differs from source classification')
    # Premultiply source stock by ownership before interpolation. Multiplying
    # separately filtered stock and coverage would still bleed soil inventory.
    corrected=data.copy();corrected[:,:,0]=road[:,:,0]
    image=bpy.data.images.new('AL pavement-owned Z film / metres',width=nx,height=ny,float_buffer=True,alpha=True);image.colorspace_settings.name='Non-Color';image.alpha_mode='CHANNEL_PACKED';image.pixels.foreach_set(corrected.ravel());image.update();image.pack()
    targets=[]
    for ob in scene.objects:
        if ob.type!='MESH' or not(ob.name=='Crowned asphalt crust / longitudinal rise' or ob.name.startswith('Original asphalt native tile ')):continue
        for material in ob.data.materials:
            if material and material.use_nodes and material not in targets:targets.append(material)
    linked=[]
    for material in targets:
        nodes=[n for n in material.node_tree.nodes if n.bl_idname=='ShaderNodeTexImage' and n.image==original]
        if not nodes:continue
        for node in nodes:node.image=image
        linked.append(dict(material=material.name,nodes=[n.name for n in nodes]))
    if not linked:raise ValueError('No actual pavement material uses the Z image')
    report.update(source_field_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),original_image_retained=original.name,corrected_image=image.name,changed_material_nodes=linked,geometry_modified=False,approved_intrinsic_images_modified=False,output_matrix_sha256=hashlib.sha256(corrected[:,:,0].tobytes()).hexdigest(),correction='Source soil stock is no longer shaded as pavement film on newly exposed asphalt; pavement-owned stock is unchanged, no blur/noise/rescaling.')
    print('AL_FILM_OWNERSHIP',report,flush=True);return report
