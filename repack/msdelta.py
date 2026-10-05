"""Windows MSDelta RAW format, used only by the package builder."""
import ctypes as c
from ctypes import wintypes as w

class Input(c.Structure):
    _fields_=[('data',c.c_void_p),('size',c.c_size_t),('editable',w.BOOL)]

class Output(c.Structure):
    _fields_=[('data',c.c_void_p),('size',c.c_size_t)]

api=c.WinDLL('msdelta',use_last_error=True)
api.CreateDeltaB.argtypes=[c.c_int64,c.c_int64,c.c_int64,Input,Input,Input,Input,Input,c.c_void_p,w.DWORD,c.POINTER(Output)]
api.CreateDeltaB.restype=w.BOOL
api.ApplyDeltaB.argtypes=[c.c_int64,Input,Input,c.POINTER(Output)]
api.ApplyDeltaB.restype=w.BOOL
api.DeltaFree.argtypes=[c.c_void_p]
api.DeltaFree.restype=w.BOOL

def invoke(source, target, create):
    a=c.create_string_buffer(source); b=c.create_string_buffer(target)
    aa=Input(c.cast(a,c.c_void_p),len(source),False)
    bb=Input(c.cast(b,c.c_void_p),len(target),False); result=Output()
    if create:
        # SDK msdelta.h: default file limit 32 MiB; gd.arc is ~43 MiB.
        # This creation option is stored in the delta. Apply flags stay zero.
        flags=0x20000 if max(len(source),len(target))>32*1024*1024 else 0
        ok=api.CreateDeltaB(1,flags,0,aa,bb,Input(),Input(),Input(),None,0,c.byref(result))
    else:
        ok=api.ApplyDeltaB(0,aa,bb,c.byref(result))
    if not ok: raise c.WinError(c.get_last_error())
    try: return c.string_at(result.data,result.size)
    finally: api.DeltaFree(result.data)

def create(source,target):
    delta=invoke(source,target,True)
    if invoke(source,delta,False)!=target: raise ValueError('delta roundtrip mismatch')
    return delta
