"""Verify process-local jemalloc retention policy; no renderer/scene mutation."""
import ctypes,os
EXPECTED='narenas:2,dirty_decay_ms:0,muzzy_decay_ms:0,abort_conf:true'
def inspect(required=False):
 lib=ctypes.CDLL(None);ctl=getattr(lib,'mallctl',None)
 if ctl is None:raise ValueError('Active process does not expose jemalloc mallctl')
 ctl.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_size_t),ctypes.c_void_p,ctypes.c_size_t];ctl.restype=ctypes.c_int
 def read(name,kind):
  value=kind();size=ctypes.c_size_t(ctypes.sizeof(value));code=ctl(name.encode(),ctypes.byref(value),ctypes.byref(size),None,0)
  if code:raise ValueError('jemalloc read failed: '+name+' code='+str(code))
  return value.value.decode() if kind is ctypes.c_char_p else value.value
 class DlInfo(ctypes.Structure):_fields_=[('file',ctypes.c_char_p),('base',ctypes.c_void_p),('symbol',ctypes.c_char_p),('address',ctypes.c_void_p)]
 info=DlInfo();dladdr=lib.dladdr;dladdr.argtypes=[ctypes.c_void_p,ctypes.POINTER(DlInfo)];dladdr.restype=ctypes.c_int
 assert dladdr(ctypes.cast(lib.malloc,ctypes.c_void_p),ctypes.byref(info))!=0
 provider=info.file.decode();assert 'jemalloc' in provider,'malloc is not supplied by inspected jemalloc'
 cfg={'narenas':read('opt.narenas',ctypes.c_uint),'dirty_decay_ms':read('opt.dirty_decay_ms',ctypes.c_ssize_t),'muzzy_decay_ms':read('opt.muzzy_decay_ms',ctypes.c_ssize_t),'abort_conf':read('opt.abort_conf',ctypes.c_bool)}
 if required:
  assert os.environ.get('MALLOC_CONF')==EXPECTED and cfg=={'narenas':2,'dirty_decay_ms':0,'muzzy_decay_ms':0,'abort_conf':True},'Requested process-local allocator policy not active'
  assert len(os.sched_getaffinity(0))<=2,'More than two CPU affinity slots'
 epoch=ctypes.c_uint64(1);length=ctypes.c_size_t(ctypes.sizeof(epoch));assert ctl(b'epoch',ctypes.byref(epoch),ctypes.byref(length),ctypes.byref(epoch),ctypes.sizeof(epoch))==0
 return {'malloc_provider':provider,'version':read('version',ctypes.c_char_p),'environment':os.environ.get('MALLOC_CONF'),'options':cfg,'CPU_affinity':sorted(os.sched_getaffinity(0)),'bytes':{k:read('stats.'+k,ctypes.c_size_t) for k in ('allocated','active','resident','retained')},'scope':'Process-local allocation retention only; geometry, image resolution, shader values, sampling and CPU thread cap unchanged. The guard remains4480MiB.','documentation':'https://jemalloc.net/jemalloc.3.html'}
