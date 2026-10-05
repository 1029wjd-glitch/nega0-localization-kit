/* Controlled COM backend for routing/lifetime checks when GPU access is absent.
   It checks calls and surface descriptions, not the visual quality of filtering. */
typedef struct MockSurface { const IDirect3DSurface9Vtbl *table; ULONG refs; D3DSURFACE_DESC desc; } MockSurface;
typedef struct MockDevice { const IDirect3DDevice9Vtbl *table; ULONG refs; } MockDevice;
typedef struct MockChain { const IDirect3DSwapChain9Vtbl *table; ULONG refs; } MockChain;
typedef struct MockFactory { const IDirect3D9Vtbl *table; ULONG refs; } MockFactory;
static MockSurface mock_primary, mock_output, mock_resolve;
static MockDevice mock_device;
static MockChain mock_chain;
static MockFactory mock_factory;
static IDirect3DSurface9Vtbl mock_surface_table;
typedef struct MockExtendedDeviceTable { IDirect3DDevice9Vtbl public_methods; DWORD sentinel; } MockExtendedDeviceTable;
static MockExtendedDeviceTable mock_extended_device_table;
#define mock_device_table mock_extended_device_table.public_methods
static IDirect3DSwapChain9Vtbl mock_chain_table;
typedef struct MockExtendedFactoryTable { IDirect3D9Vtbl public_methods; DWORD sentinel; } MockExtendedFactoryTable;
static MockExtendedFactoryTable mock_extended_factory_table;
#define mock_factory_table mock_extended_factory_table.public_methods
static unsigned mock_windowed_presents, mock_output_presents, mock_copies, mock_resolves, mock_black_fills;
static BOOL mock_force_point, mock_reset_resources_released=TRUE;
static unsigned mock_native_parent_releases, mock_reset_callback_presents;
static BOOL mock_force_missing_output;
static RECT mock_last_destination;

static ULONG STDMETHODCALLTYPE MockSurfaceAdd(IDirect3DSurface9 *s) {
    if(s==(IDirect3DSurface9*)&mock_primary || s==(IDirect3DSurface9*)&mock_output)
        mock_device.refs++;
    return ++((MockSurface*)s)->refs;
}
static ULONG STDMETHODCALLTYPE MockSurfaceRelease(IDirect3DSurface9 *s) {
    ULONG n=--((MockSurface*)s)->refs;
    if(s==(IDirect3DSurface9*)&mock_primary || s==(IDirect3DSurface9*)&mock_output) {
        mock_native_parent_releases++;
        IDirect3DDevice9_Release((IDirect3DDevice9*)&mock_device);
    }
    return n;
}
static HRESULT STDMETHODCALLTYPE MockDesc(IDirect3DSurface9 *s, D3DSURFACE_DESC *d) { *d=((MockSurface*)s)->desc;return D3D_OK; }
static ULONG STDMETHODCALLTYPE MockDeviceAdd(IDirect3DDevice9 *d) { (void)d;return ++mock_device.refs; }
static ULONG STDMETHODCALLTYPE MockFactoryRelease(IDirect3D9 *f) { return --((MockFactory*)f)->refs; }
static ULONG STDMETHODCALLTYPE MockDeviceRelease(IDirect3DDevice9 *d) {
    ULONG n;n=--((MockDevice*)d)->refs;
    if(!n && d==(IDirect3DDevice9*)&mock_device) IDirect3D9_Release((IDirect3D9*)&mock_factory);
    return n;
}
static ULONG STDMETHODCALLTYPE MockChainRelease(IDirect3DSwapChain9 *c) {
    ULONG n;(void)c;n=--mock_chain.refs;
    if(!n) IDirect3DDevice9_Release((IDirect3DDevice9*)&mock_device);
    return n;
}
static HRESULT STDMETHODCALLTYPE MockPrimary(IDirect3DDevice9 *d,UINT chain,UINT index,D3DBACKBUFFER_TYPE type,IDirect3DSurface9 **s) {
    (void)d;(void)chain;(void)index;(void)type;
    *s=(IDirect3DSurface9*)&mock_primary;MockSurfaceAdd(*s);return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockOutput(IDirect3DSwapChain9 *c,UINT index,D3DBACKBUFFER_TYPE type,IDirect3DSurface9 **s) {
    (void)c;(void)index;(void)type;
    *s=(IDirect3DSurface9*)&mock_output;MockSurfaceAdd(*s);return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockSwap(IDirect3DDevice9 *d,D3DPRESENT_PARAMETERS *pp,IDirect3DSwapChain9 **c) {
    if(!pp->Windowed || pp->MultiSampleType!=D3DMULTISAMPLE_NONE || pp->EnableAutoDepthStencil || mock_chain.refs) return D3DERR_INVALIDCALL;
    if(mock_force_missing_output) { *c=NULL; return D3D_OK; }
    mock_chain.refs=1;IDirect3DDevice9_AddRef(d);
    mock_output.desc=mock_primary.desc;mock_output.desc.Width=pp->BackBufferWidth;mock_output.desc.Height=pp->BackBufferHeight;
    mock_output.desc.MultiSampleType=D3DMULTISAMPLE_NONE;
    *c=(IDirect3DSwapChain9*)&mock_chain;return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockFill(IDirect3DDevice9 *d,IDirect3DSurface9 *s,const RECT *r,D3DCOLOR color) {
    (void)d;(void)r;
    if(s==(IDirect3DSurface9*)&mock_output && color==D3DCOLOR_XRGB(0,0,0)) mock_black_fills++;
    return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockStretch(IDirect3DDevice9 *d,IDirect3DSurface9 *s,const RECT *sr,IDirect3DSurface9 *t,const RECT *tr,D3DTEXTUREFILTERTYPE filter) {
    MockSurface *source=(MockSurface*)s;(void)d;(void)sr;
    if(source->desc.Width!=800 || source->desc.Height!=600) return D3DERR_INVALIDCALL;
    if(t==(IDirect3DSurface9*)&mock_resolve && filter==D3DTEXF_NONE) { mock_resolves++;return D3D_OK; }
    if(t!=(IDirect3DSurface9*)&mock_output || !tr) return D3DERR_INVALIDCALL;
    if(filter==D3DTEXF_LINEAR && mock_force_point) return D3DERR_INVALIDCALL;
    mock_last_destination=*tr;mock_copies++;return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockRenderTarget(IDirect3DDevice9 *d,UINT w,UINT h,D3DFORMAT fmt,D3DMULTISAMPLE_TYPE ms,DWORD quality,BOOL lockable,IDirect3DSurface9 **s,HANDLE *shared) {
    (void)d;(void)quality;(void)lockable;(void)shared;
    mock_resolve.refs=1;mock_resolve.desc=mock_primary.desc;
    mock_resolve.desc.Width=w;mock_resolve.desc.Height=h;mock_resolve.desc.Format=fmt;mock_resolve.desc.MultiSampleType=ms;
    *s=(IDirect3DSurface9*)&mock_resolve;return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockReset(IDirect3DDevice9 *d,D3DPRESENT_PARAMETERS *pp) {
    if(d->lpVtbl!=&mock_device_table || mock_extended_device_table.sentinel!=0x1234abcd) return E_FAIL;
    if(mock_chain.refs || mock_resolve.refs) mock_reset_resources_released=FALSE;
    if(!pp->Windowed || pp->FullScreen_RefreshRateInHz) return D3DERR_INVALIDCALL;
    if(SUCCEEDED(IDirect3DDevice9_Present(d,NULL,NULL,NULL,NULL))) mock_reset_callback_presents++;
    mock_primary.desc.Width=pp->BackBufferWidth;mock_primary.desc.Height=pp->BackBufferHeight;
    mock_primary.desc.MultiSampleType=pp->MultiSampleType;
    return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockPresent(IDirect3DDevice9 *d,const RECT *s,const RECT *t,HWND h,const RGNDATA *r) {
    (void)d;(void)s;(void)t;(void)h;(void)r;mock_windowed_presents++;return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockChainPresent(IDirect3DSwapChain9 *c,const RECT *s,const RECT *t,HWND h,const RGNDATA *r,DWORD flags) {
    (void)c;(void)s;(void)t;(void)h;(void)r;(void)flags;mock_output_presents++;return D3D_OK;
}
static HRESULT STDMETHODCALLTYPE MockCreate(IDirect3D9 *f,UINT adapter,D3DDEVTYPE type,HWND focus,DWORD behavior,D3DPRESENT_PARAMETERS *pp,IDirect3DDevice9 **device) {
    (void)adapter;(void)type;(void)focus;(void)behavior;
    if(f->lpVtbl!=&mock_factory_table || mock_extended_factory_table.sentinel!=0x5678abcd) return E_FAIL;
    if(!pp->Windowed || pp->FullScreen_RefreshRateInHz) return D3DERR_INVALIDCALL;
    mock_factory.refs++;mock_device.refs=1;
    mock_primary.desc.Width=pp->BackBufferWidth;mock_primary.desc.Height=pp->BackBufferHeight;
    mock_primary.desc.Format=D3DFMT_X8R8G8B8;mock_primary.desc.MultiSampleType=pp->MultiSampleType;
    *device=(IDirect3DDevice9*)&mock_device;return D3D_OK;
}
static IDirect3D9 *MockFactoryCreate(void) {
    mock_extended_factory_table.sentinel=0x5678abcd;
    mock_extended_device_table.sentinel=0x1234abcd;
    mock_surface_table.AddRef=MockSurfaceAdd;mock_surface_table.Release=MockSurfaceRelease;mock_surface_table.GetDesc=MockDesc;
    mock_primary.table=mock_output.table=mock_resolve.table=&mock_surface_table;
    mock_device_table.AddRef=MockDeviceAdd;mock_device_table.Release=MockDeviceRelease;
    mock_device_table.GetBackBuffer=MockPrimary;mock_device_table.CreateAdditionalSwapChain=MockSwap;
    mock_device_table.ColorFill=MockFill;mock_device_table.StretchRect=MockStretch;
    mock_device_table.CreateRenderTarget=MockRenderTarget;mock_device_table.Reset=MockReset;mock_device_table.Present=MockPresent;
    mock_device.table=&mock_device_table;
    mock_chain_table.Release=MockChainRelease;mock_chain_table.GetBackBuffer=MockOutput;mock_chain_table.Present=MockChainPresent;
    mock_chain.table=&mock_chain_table;
    mock_factory_table.Release=MockFactoryRelease;mock_factory_table.CreateDevice=MockCreate;
    mock_factory.table=&mock_factory_table;mock_factory.refs=1;
    return HookFactory((IDirect3D9*)&mock_factory);
}
