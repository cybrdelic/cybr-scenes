"""Restore tagged roof form without inventing unobserved geographic layouts.

Footprints/courtyards and source IDs stay intact. Roof rise, eave construction
and missing orientation are explicit modeling estimates. Untagged roofs retain
the baseline flat massing representation.
"""
from dataclasses import replace
import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import split
from .geometry import Builder, polygons, triangulate_polygon
from .ingest import metres


class RoofBuilder(Builder):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.roof_adaptations=[]

    def building(self,feature,wall,roof):
        tags=feature.properties
        kind=tags.get('roof:shape','').lower()
        supported={'gabled','hipped','pyramidal','skillion'}
        if kind not in supported:
            return super().building(feature,wall,roof)
        # A tag for an entire multipart building does not resolve the structure
        # of every disconnected roof. Keep each footprint component anchored.
        for index,poly in enumerate(polygons(feature.geometry)):
            if poly.area<2:continue
            rectangle=np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:4,:2]
            edges=np.roll(rectangle,-1,axis=0)-rectangle
            u=edges[np.argmax(np.linalg.norm(edges,axis=1))];u=u/np.linalg.norm(u)
            v=np.array([-u[1],u[0]])
            if tags.get('roof:orientation')=='across':u,v=v,-u
            center=rectangle.mean(axis=0)
            halfu=float(np.max(abs((rectangle-center)@u)))
            halfv=float(np.max(abs((rectangle-center)@v)))
            if min(halfu,halfv)<.4:return super().building(feature,wall,roof)
            supplied=metres(tags.get('roof:height'))
            rise=supplied if supplied is not None and supplied>0 else min(3.2,max(.65,halfv*.38))
            rise=min(rise,float(tags['height_m'])*.7)
            total_height=tags['height_method'].startswith('explicit')
            wall_height=max(1.8,float(tags['height_m'])-rise) if total_height else float(tags['height_m'])
            sub=replace(feature,id=feature.id+f':roofcomponent:{index}',geometry=poly,
                        properties={**tags,'height_m':wall_height})
            before=len(self.geometry.assembly.parts)
            old_provenance=len(self.provenance)
            old_checks=len(self.footprint_checks)
            super().building(sub,wall,roof)
            added=self.geometry.assembly.parts[before:]
            for p in added:p.tags=(feature.id,)
            for p in self.provenance[old_provenance:]:p["source_ids"]=[feature.id]
            for p in self.footprint_checks[old_checks:]:p["source_id"]=feature.id
            old_roof=next(p for p in added if p.group=='roof')
            eave=float(old_roof.vertices[:,2].mean()*.001)
            self.geometry.assembly.parts=[p for p in self.geometry.assembly.parts if p is not old_roof]
            del self.geometry.attributes[old_roof.name]
            self.provenance=[x for x in self.provenance if x['part']!=old_roof.name]
            def height(xy):
                xy=np.asarray(xy);a=(xy-center)@u;b=(xy-center)@v
                if kind=='gabled':h=1-abs(b)/halfv
                elif kind=='skillion':h=(b/halfv+1)*.5
                elif kind=='pyramidal':h=np.minimum(1-abs(a)/halfu,1-abs(b)/halfv)
                else:h=np.minimum(halfu-abs(a),halfv-abs(b))/halfv
                return eave+rise*np.clip(h,0,1)
            # Insert all ridges/hip break-lines before triangulation. Raising
            # only a polygon's existing boundary vertices leaves a flat roof.
            cutlines=[]
            span=max(halfu,halfv)*4+4
            def line(origin,direction):return LineString([origin-direction*span,origin+direction*span])
            if kind!='skillion':cutlines.append(line(center,u))
            if kind in {'hipped','pyramidal'}:
                cutlines.append(line(center,v))
                for signu in [-1,1]:
                    for signv in [-1,1]:
                        corner=center+u*halfu*signu+v*halfv*signv
                        ridge=center if kind=='pyramidal' else center+u*(halfu-halfv)*signu
                        delta=ridge-corner
                        cutlines.append(line(corner,delta/np.linalg.norm(delta)))
            pieces=[poly]
            for cutter in cutlines:
                pieces=[q for p in pieces for q in split(p,cutter).geoms if q.area>1e-8]
            projected=0
            for k,p in enumerate(pieces):
                xy,faces=triangulate_polygon(p);projected+=p.area
                self.add(old_roof.name+f'_tagged_{k}',np.c_[xy,height(xy)],faces,roof,'roof',[feature.id],
                         f'OSM roof:shape={kind}; '+('tagged rise' if supplied else 'estimated roof rise/pitch')+'; footprint retained',uv=xy/1.25)
            assert np.isclose(projected,poly.area,rtol=1e-8,atol=1e-6)
            # Gable end and skillion high walls meet the roof instead of leaving
            # open triangular holes. These faces add no new footprint area.
            for ring_index,ring in enumerate([poly.exterior,*poly.interiors]):
                xy=np.asarray(ring.coords)[:,:2]
                for k,(a,b) in enumerate(zip(xy[:-1],xy[1:])):
                    samples=np.vstack([a,b])
                    if kind=='gabled':
                        da,db=(samples-center)@v
                        if da*db<0:samples=np.vstack([a,a+(b-a)*(-da/(db-da)),b])
                    for j,(aa,bb) in enumerate(zip(samples[:-1],samples[1:])):
                        top=height(np.vstack([aa,bb]))
                        if max(top)-eave<1e-6:continue
                        vv=np.array([[*aa,eave],[*bb,eave],[*bb,top[1]],[*aa,top[0]]])
                        ff=[]
                        for face in [[0,1,2],[0,2,3]]:
                            t=vv[face]
                            if np.linalg.norm(np.cross(t[1]-t[0],t[2]-t[0]))>1e-8:ff.append(face)
                        if ff:self.add(old_roof.name+f'_end_{ring_index}_{k}_{j}',vv,ff,wall,'building',[feature.id],
                                       'Roof-following end wall; rise/orientation partly estimated')
            self.roof_adaptations.append({'source_id':feature.id,'shape_tag':kind,'roof_rise_m':rise,
                'rise_source':'roof:height' if supplied else 'estimated 0.38 slope, bounded 0.65–3.2 m',
                'orientation_source':'roof:orientation' if tags.get('roof:orientation') else 'estimated from minimum rotated footprint rectangle',
                'explicit_total_height_preserved':total_height,'eave_z_m':eave,
                'source_footprint_m2':poly.area,'roof_projected_area_m2':projected,
                'limits':'Roof form is sourced; exact ridge topology, pitch, eaves and hidden construction remain unmeasured.'})
