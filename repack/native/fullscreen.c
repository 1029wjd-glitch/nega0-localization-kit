/* Keep the verified game's 800x600 render buffer. Only fullscreen requests
   use a desktop-sized windowed swap chain with aspect-preserving final copy.
   Keep native object/vtable identity and any driver-private entries intact.
   Only the public method slots below are redirected in this process. */
#define WIN32_LEAN_AND_MEAN
#define COBJMACROS
#include <windows.h>
#include <d3d9.h>
#include <string.h>
#include <stdio.h>

void WINAPI NegaOutputDebugStringW(LPCWSTR message);

typedef struct Factory {
    IDirect3D9 *object;
    const IDirect3D9Vtbl *original;
    struct Factory *next;
} Factory;
typedef struct Device {
    IDirect3DDevice9 *object;
    const IDirect3DDevice9Vtbl *original;
    struct Device *next;
    IDirect3DSwapChain9 *output;
    IDirect3DSurface9 *resolved;
    HWND window;
    UINT width, height, output_width, output_height;
    DWORD interval;
    UINT operation_depth;
    BOOL active, fullscreen, resizable, adjusting_window, filter_logged, error_logged, releasing;
} Device;

/* A native vtable can extend beyond the public COM interface. Never replace
   its pointer with a truncated public-interface copy. Snapshots here are only
   used to call original methods, and stay alive for the process lifetime. */
typedef struct FactoryTable {
    const IDirect3D9Vtbl *native;
    IDirect3D9Vtbl original;
    struct FactoryTable *next;
} FactoryTable;
typedef struct DeviceTable {
    const IDirect3DDevice9Vtbl *native;
    IDirect3DDevice9Vtbl original;
    struct DeviceTable *next;
} DeviceTable;
static FactoryTable *factory_tables;
static DeviceTable *device_tables;

static Factory *factories;
static Device *devices;
static SRWLOCK records_lock = SRWLOCK_INIT;

static const IDirect3D9Vtbl *FactoryOriginal(IDirect3D9 *object) {
    FactoryTable *t; const IDirect3D9Vtbl *result=NULL;
    AcquireSRWLockShared(&records_lock);
    for(t=factory_tables;t;t=t->next) if(t->native==object->lpVtbl) { result=&t->original; break; }
    ReleaseSRWLockShared(&records_lock);
    return result;
}
static const IDirect3DDevice9Vtbl *DeviceOriginal(IDirect3DDevice9 *object) {
    DeviceTable *t; const IDirect3DDevice9Vtbl *result=NULL;
    AcquireSRWLockShared(&records_lock);
    for(t=device_tables;t;t=t->next) if(t->native==object->lpVtbl) { result=&t->original; break; }
    ReleaseSRWLockShared(&records_lock);
    return result;
}

static Factory *FindFactory(IDirect3D9 *object) {
    Factory *p;
    AcquireSRWLockShared(&records_lock);
    for(p=factories;p && p->object!=object;p=p->next) {}
    ReleaseSRWLockShared(&records_lock);
    return p;
}
static Device *FindDevice(IDirect3DDevice9 *object) {
    Device *p;
    AcquireSRWLockShared(&records_lock);
    for(p=devices;p && p->object!=object;p=p->next) {}
    ReleaseSRWLockShared(&records_lock);
    return p;
}

static RECT FitRectangle(UINT sw, UINT sh, LONG dw, LONG dh) {
    RECT r={0,0,0,0}; LONG w,h;
    if(!sw || !sh || dw<=0 || dh<=0) return r;
    if((ULONGLONG)dw*sh <= (ULONGLONG)dh*sw) {
        w=dw; h=(LONG)((ULONGLONG)dw*sh/sw);
    } else {
        h=dh; w=(LONG)((ULONGLONG)dh*sw/sh);
    }
    r.left=(dw-w)/2; r.top=(dh-h)/2;
    r.right=r.left+w; r.bottom=r.top+h;
    return r;
}

static void DropOutput(Device *p) {
    IDirect3DSwapChain9 *chain=p->output;
    IDirect3DSurface9 *resolved=p->resolved;
    p->output=NULL; p->resolved=NULL;
    p->output_width=p->output_height=0;
    if(resolved) IDirect3DSurface9_Release(resolved);
    if(chain) IDirect3DSwapChain9_Release(chain);
}

static void BorderlessWindow(Device *p) {
    MONITORINFO info; RECT current; LONG style, extended;
    BOOL changed=FALSE;
    if(!p->fullscreen || p->adjusting_window || !IsWindow(p->window) || IsIconic(p->window)) return;
    info.cbSize=sizeof(info);
    if(!GetMonitorInfoW(MonitorFromWindow(p->window,MONITOR_DEFAULTTONEAREST),&info)) return;
    p->adjusting_window=TRUE;
    style=GetWindowLongW(p->window,GWL_STYLE);
    extended=GetWindowLongW(p->window,GWL_EXSTYLE);
    if(style & WS_OVERLAPPEDWINDOW) {
        SetWindowLongW(p->window,GWL_STYLE,(style & ~WS_OVERLAPPEDWINDOW) | WS_POPUP);
        changed=TRUE;
    }
    if(extended & (WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_TOPMOST)) {
        SetWindowLongW(p->window,GWL_EXSTYLE,extended & ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_TOPMOST));
        if(extended & WS_EX_TOPMOST)
            SetWindowPos(p->window,HWND_NOTOPMOST,0,0,0,0,SWP_NOACTIVATE | SWP_NOMOVE | SWP_NOSIZE);
        changed=TRUE;
    }
    GetWindowRect(p->window,&current);
    if(!EqualRect(&current,&info.rcMonitor) || changed)
        SetWindowPos(p->window,NULL,info.rcMonitor.left,info.rcMonitor.top,
            info.rcMonitor.right-info.rcMonitor.left,info.rcMonitor.bottom-info.rcMonitor.top,
            SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED);
    p->adjusting_window=FALSE;
}

static void EnableResize(Device *p) {
    LONG style,extended; RECT client,frame;
    if(!p->resizable || !IsWindow(p->window)) return;
    style=GetWindowLongW(p->window,GWL_STYLE);
    if((style & (WS_THICKFRAME | WS_MAXIMIZEBOX))==(WS_THICKFRAME | WS_MAXIMIZEBOX)) return;
    if(!GetClientRect(p->window,&client)) return;
    extended=GetWindowLongW(p->window,GWL_EXSTYLE);
    style |= WS_THICKFRAME | WS_MAXIMIZEBOX;
    frame=client;
    if(!AdjustWindowRectEx(&frame,(DWORD)style,GetMenu(p->window)!=NULL,(DWORD)extended)) return;
    SetWindowLongW(p->window,GWL_STYLE,style);
    SetWindowPos(p->window,NULL,0,0,frame.right-frame.left,frame.bottom-frame.top,
                 SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED);
    NegaOutputDebugStringW(L"Windowed: corner resize enabled; aspect fit and mouse mapping follow client size.\n");
}

static void UpdateWindowScaling(Device *p) {
    RECT client;
    if(p->fullscreen) { p->active=TRUE; return; }
    p->active=p->resizable && GetClientRect(p->window,&client) &&
              ((UINT)client.right!=p->width || (UINT)client.bottom!=p->height);
}

static HRESULT ComposeOutput(Device *p) {
    IDirect3DSurface9 *src=NULL, *dst=NULL;
    D3DSURFACE_DESC desc; D3DPRESENT_PARAMETERS pp;
    RECT client, fit; HRESULT hr;
    if(!GetClientRect(p->window,&client) || client.right<=0 || client.bottom<=0) return D3DERR_DEVICELOST;
    p->operation_depth++;
    if(p->output && (p->output_width!=(UINT)client.right || p->output_height!=(UINT)client.bottom)) DropOutput(p);
    hr=p->original->GetBackBuffer(p->object,0,0,D3DBACKBUFFER_TYPE_MONO,&src);
    if(FAILED(hr)) goto done;
    if(!src) { hr=D3DERR_INVALIDCALL; goto done; }
    hr=IDirect3DSurface9_GetDesc(src,&desc);
    if(FAILED(hr)) goto done;
    if(desc.Width!=p->width || desc.Height!=p->height) { hr=D3DERR_INVALIDCALL; goto done; }
    if(!p->output) {
        WCHAR message[160];
        ZeroMemory(&pp,sizeof(pp));
        pp.BackBufferWidth=(UINT)client.right; pp.BackBufferHeight=(UINT)client.bottom;
        pp.BackBufferFormat=desc.Format; pp.BackBufferCount=1;
        pp.MultiSampleType=D3DMULTISAMPLE_NONE; pp.SwapEffect=D3DSWAPEFFECT_DISCARD;
        pp.hDeviceWindow=p->window; pp.Windowed=TRUE;
        pp.PresentationInterval=p->interval;
        hr=p->original->CreateAdditionalSwapChain(p->object,&pp,&p->output);
        if(FAILED(hr)) goto done;
        if(!p->output) { hr=D3DERR_INVALIDCALL; goto done; }
        p->output_width=pp.BackBufferWidth; p->output_height=pp.BackBufferHeight;
        swprintf_s(message,160,L"Fullscreen: output chain %ux%u, source %ux%u, aspect-preserving fit.\n",
            p->output_width,p->output_height,p->width,p->height);
        NegaOutputDebugStringW(message);
    }
    hr=IDirect3DSwapChain9_GetBackBuffer(p->output,0,D3DBACKBUFFER_TYPE_MONO,&dst);
    if(FAILED(hr)) goto done;
    hr=p->original->ColorFill(p->object,dst,NULL,D3DCOLOR_XRGB(0,0,0));
    if(FAILED(hr)) goto done;
    if(desc.MultiSampleType!=D3DMULTISAMPLE_NONE) {
        if(!p->resolved) {
            hr=p->original->CreateRenderTarget(p->object,p->width,p->height,desc.Format,
                D3DMULTISAMPLE_NONE,0,FALSE,&p->resolved,NULL);
            if(FAILED(hr)) goto done;
        }
        hr=p->original->StretchRect(p->object,src,NULL,p->resolved,NULL,D3DTEXF_NONE);
        if(FAILED(hr)) goto done;
        IDirect3DSurface9_Release(src); src=p->resolved; IDirect3DSurface9_AddRef(src);
    }
    fit=FitRectangle(p->width,p->height,(LONG)p->output_width,(LONG)p->output_height);
    hr=p->original->StretchRect(p->object,src,NULL,dst,&fit,D3DTEXF_LINEAR);
    if(FAILED(hr)) {
        hr=p->original->StretchRect(p->object,src,NULL,dst,&fit,D3DTEXF_POINT);
        if(SUCCEEDED(hr) && !p->filter_logged) {
            p->filter_logged=TRUE;
            NegaOutputDebugStringW(L"Fullscreen: linear filter unavailable; aspect-preserving point filter selected.\n");
        }
    }
done:
    if(dst) IDirect3DSurface9_Release(dst);
    if(src) IDirect3DSurface9_Release(src);
    p->operation_depth--;
    return hr;
}

static ULONG STDMETHODCALLTYPE DeviceRelease(IDirect3DDevice9 *object) {
    Device *p=FindDevice(object), **link; ULONG remaining;
    const IDirect3DDevice9Vtbl *original=DeviceOriginal(object);
    /* Native surface/chain destruction can Release its parent device while
       we are composing or resetting. That does not mean the game is done
       with the device; never destroy the current output from that callback. */
    if(!p || p->releasing || p->operation_depth) return original->Release(object);
    /* Releasing an output resource may recursively release its device. */
    p->releasing=TRUE;
    DropOutput(p);
    remaining=p->original->Release(object);
    if(remaining) p->releasing=FALSE;
    else {
        AcquireSRWLockExclusive(&records_lock);
        for(link=&devices;*link && *link!=p;link=&(*link)->next) {}
        if(*link) *link=p->next;
        ReleaseSRWLockExclusive(&records_lock);
        HeapFree(GetProcessHeap(),0,p);
    }
    return remaining;
}

static BOOL PrepareParameters(Device *p, D3DPRESENT_PARAMETERS *input, D3DPRESENT_PARAMETERS *output) {
    *output=*input;
    p->fullscreen=!input->Windowed && input->BackBufferWidth==800 && input->BackBufferHeight==600;
    p->resizable=input->Windowed && input->BackBufferWidth==800 && input->BackBufferHeight==600;
    p->active=p->fullscreen;
    p->window=input->hDeviceWindow ? input->hDeviceWindow : p->window;
    p->width=input->BackBufferWidth; p->height=input->BackBufferHeight;
    p->interval=input->PresentationInterval;
    if(p->fullscreen) {
        output->Windowed=TRUE;
        output->FullScreen_RefreshRateInHz=0;
        output->BackBufferFormat=D3DFMT_UNKNOWN;
    }
    return p->active;
}

static HRESULT STDMETHODCALLTYPE DeviceReset(IDirect3DDevice9 *object, D3DPRESENT_PARAMETERS *input) {
    Device *p=FindDevice(object); D3DPRESENT_PARAMETERS pp; HRESULT hr;
    if(!p) return DeviceOriginal(object)->Reset(object,input);
    if(!input) return p->original->Reset(object,input);
    if(p->operation_depth) return D3DERR_INVALIDCALL;
    p->operation_depth++;
    DropOutput(p);
    PrepareParameters(p,input,&pp);
    hr=p->original->Reset(object,&pp);
    if(SUCCEEDED(hr)) {
        if(p->fullscreen) {
            BorderlessWindow(p);
            NegaOutputDebugStringW(L"Fullscreen: reset to desktop borderless output; 800x600 rendering preserved.\n");
        } else { *input=pp; EnableResize(p); UpdateWindowScaling(p); }
    }
    p->operation_depth--;
    return hr;
}

static HRESULT STDMETHODCALLTYPE DevicePresent(IDirect3DDevice9 *object, const RECT *src,
    const RECT *dst, HWND override, const RGNDATA *dirty) {
    Device *p=FindDevice(object); HRESULT hr;
    if(!p) return DeviceOriginal(object)->Present(object,src,dst,override,dirty);
    /* Reset/SetWindowPos can synchronously dispatch window callbacks. D3D
       must not be called again from such a callback during the operation. */
    if(p->operation_depth) return D3D_OK;
    UpdateWindowScaling(p);
    if(!p->active && p->output) { p->operation_depth++; DropOutput(p); p->operation_depth--; }
    if(!p->active || (override && override!=p->window))
        return p->original->Present(object,src,dst,override,dirty);
    if(IsIconic(p->window)) return D3D_OK;
    p->operation_depth++;
    BorderlessWindow(p);
    hr=ComposeOutput(p);
    if(SUCCEEDED(hr)) hr=p->output ? IDirect3DSwapChain9_Present(p->output,NULL,NULL,p->window,dirty,0) : D3DERR_DEVICELOST;
    if(FAILED(hr) && !p->error_logged) {
        WCHAR message[160]; p->error_logged=TRUE;
        swprintf_s(message,160,L"Fullscreen: output failure HRESULT %08lx.\n",(ULONG)hr);
        NegaOutputDebugStringW(message);
    }
    p->operation_depth--;
    return hr;
}

static ULONG STDMETHODCALLTYPE FactoryRelease(IDirect3D9 *object) {
    Factory *p=FindFactory(object), **link; ULONG remaining;
    if(!p) return FactoryOriginal(object)->Release(object);
    remaining=p->original->Release(object);
    if(!remaining) {
        AcquireSRWLockExclusive(&records_lock);
        for(link=&factories;*link && *link!=p;link=&(*link)->next) {}
        if(*link) *link=p->next;
        ReleaseSRWLockExclusive(&records_lock);
        HeapFree(GetProcessHeap(),0,p);
    }
    return remaining;
}

static const IDirect3DDevice9Vtbl *HookDeviceTable(IDirect3DDevice9 *object) {
    DeviceTable *t; DWORD protect,unused;
    AcquireSRWLockExclusive(&records_lock);
    for(t=device_tables;t;t=t->next) if(t->native==object->lpVtbl) break;
    if(!t) {
        t=(DeviceTable*)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*t));
        if(t && VirtualProtect((void*)object->lpVtbl,sizeof(t->original),PAGE_READWRITE,&protect)) {
            IDirect3DDevice9Vtbl *slots=(IDirect3DDevice9Vtbl*)object->lpVtbl;
            t->native=object->lpVtbl; t->original=*slots;
            t->next=device_tables; device_tables=t;
            InterlockedExchangePointer((PVOID volatile*)&slots->Release,(PVOID)DeviceRelease);
            InterlockedExchangePointer((PVOID volatile*)&slots->Reset,(PVOID)DeviceReset);
            InterlockedExchangePointer((PVOID volatile*)&slots->Present,(PVOID)DevicePresent);
            VirtualProtect(slots,sizeof(t->original),protect,&unused);
        } else { if(t) HeapFree(GetProcessHeap(),0,t); t=NULL; }
    }
    ReleaseSRWLockExclusive(&records_lock);
    return t ? &t->original : NULL;
}

static HRESULT STDMETHODCALLTYPE FactoryCreateDevice(IDirect3D9 *object, UINT adapter,
    D3DDEVTYPE type, HWND focus, DWORD behavior, D3DPRESENT_PARAMETERS *input,
    IDirect3DDevice9 **device) {
    Factory *factory=FindFactory(object); Device *p;
    D3DPRESENT_PARAMETERS pp; HRESULT hr;
    const IDirect3D9Vtbl *original=factory ? factory->original : FactoryOriginal(object);
    if(!input || !device) return original->CreateDevice(object,adapter,type,focus,behavior,input,device);
    p=(Device*)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*p));
    if(!p) return E_OUTOFMEMORY;
    p->window=focus;
    PrepareParameters(p,input,&pp);
    NegaOutputDebugStringW(L"Fullscreen: entering native CreateDevice with original object/vtable identity.\n");
    hr=original->CreateDevice(object,adapter,type,focus,behavior,&pp,device);
    if(FAILED(hr)) { HeapFree(GetProcessHeap(),0,p); return hr; }
    p->object=*device; p->original=HookDeviceTable(*device);
    if(!p->original) { IDirect3DDevice9_Release(*device); *device=NULL; HeapFree(GetProcessHeap(),0,p); return E_FAIL; }
    AcquireSRWLockExclusive(&records_lock);
    p->next=devices; devices=p;
    ReleaseSRWLockExclusive(&records_lock);
    p->operation_depth++;
    if(p->fullscreen) {
        BorderlessWindow(p);
        NegaOutputDebugStringW(L"Fullscreen: 800x600 -> desktop, aspect preserved, linear upscale and mouse mapping enabled.\n");
    } else { *input=pp; EnableResize(p); UpdateWindowScaling(p); }
    p->operation_depth--;
    return hr;
}

static IDirect3D9 *HookFactory(IDirect3D9 *object) {
    Factory *p; FactoryTable *t; DWORD protect,unused;
    if(!object) return NULL;
    p=(Factory*)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*p));
    if(!p) { IDirect3D9_Release(object); return NULL; }
    p->object=object;
    AcquireSRWLockExclusive(&records_lock);
    for(t=factory_tables;t;t=t->next) if(t->native==object->lpVtbl) break;
    if(!t) {
        t=(FactoryTable*)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*t));
        if(t && VirtualProtect((void*)object->lpVtbl,sizeof(t->original),PAGE_READWRITE,&protect)) {
            IDirect3D9Vtbl *slots=(IDirect3D9Vtbl*)object->lpVtbl;
            t->native=object->lpVtbl; t->original=*slots;
            t->next=factory_tables; factory_tables=t;
            InterlockedExchangePointer((PVOID volatile*)&slots->Release,(PVOID)FactoryRelease);
            InterlockedExchangePointer((PVOID volatile*)&slots->CreateDevice,(PVOID)FactoryCreateDevice);
            VirtualProtect(slots,sizeof(t->original),protect,&unused);
        } else { if(t) HeapFree(GetProcessHeap(),0,t); t=NULL; }
    }
    if(!t) { ReleaseSRWLockExclusive(&records_lock); HeapFree(GetProcessHeap(),0,p); IDirect3D9_Release(object); return NULL; }
    p->original=&t->original;
    p->next=factories; factories=p;
    ReleaseSRWLockExclusive(&records_lock);
    return object;
}

IDirect3D9* WINAPI NegaDirect3DCreate9(UINT version) {
    return HookFactory(Direct3DCreate9(version));
}

static BOOL WindowMapping(HWND window, RECT *fit, UINT *width, UINT *height) {
    Device *p; RECT client; BOOL found=FALSE;
    AcquireSRWLockShared(&records_lock);
    for(p=devices;p;p=p->next) if((p->fullscreen || p->resizable) && p->window==window) {
        *width=p->width; *height=p->height; found=TRUE; break;
    }
    ReleaseSRWLockShared(&records_lock);
    if(!found || !GetClientRect(window,&client)) return FALSE;
    *fit=FitRectangle(*width,*height,client.right,client.bottom);
    return fit->right>fit->left && fit->bottom>fit->top;
}

BOOL WINAPI NegaScreenToClient(HWND window, LPPOINT point) {
    BOOL result=ScreenToClient(window,point); RECT fit; UINT w,h;
    if(result && point && WindowMapping(window,&fit,&w,&h)) {
        point->x=point->x<fit.left ? -1 : point->x>=fit.right ? (LONG)w :
            (LONG)(((LONGLONG)point->x-fit.left)*w/(fit.right-fit.left));
        point->y=point->y<fit.top ? -1 : point->y>=fit.bottom ? (LONG)h :
            (LONG)(((LONGLONG)point->y-fit.top)*h/(fit.bottom-fit.top));
    }
    return result;
}
BOOL WINAPI NegaClientToScreen(HWND window, LPPOINT point) {
    RECT fit; UINT w,h;
    if(point && WindowMapping(window,&fit,&w,&h)) {
        point->x=fit.left+(LONG)((LONGLONG)point->x*(fit.right-fit.left)/w);
        point->y=fit.top+(LONG)((LONGLONG)point->y*(fit.bottom-fit.top)/h);
    }
    return ClientToScreen(window,point);
}
