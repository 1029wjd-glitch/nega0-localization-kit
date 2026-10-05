/* One hidden-window GPU test of the same implementation linked into the DLL. */
#include "fullscreen.c"
#include "fullscreen_mock.h"

void WINAPI NegaOutputDebugStringW(LPCWSTR message) { (void)message; }

static int fail;
static void SizeClient(HWND window, LONG width, LONG height) {
    RECT frame={0,0,width,height};
    AdjustWindowRectEx(&frame,(DWORD)GetWindowLongW(window,GWL_STYLE),FALSE,
                      (DWORD)GetWindowLongW(window,GWL_EXSTYLE));
    SetWindowPos(window,NULL,0,0,frame.right-frame.left,frame.bottom-frame.top,
                 SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOZORDER);
}
static void Check(int condition, const char *label) {
    printf("%s: %s\n",label,condition?"PASS":"FAIL");
    if(!condition) fail++;
}
static BOOL PaintAndRead(Device *p) {
    IDirect3DSurface9 *src=NULL,*dst=NULL,*readback=NULL;
    D3DSURFACE_DESC desc; D3DLOCKED_RECT lock; RECT right={400,0,800,600},fit;
    HRESULT hr; DWORD red,green,bar=0; BOOL good=FALSE;
    hr=p->original->GetBackBuffer(p->object,0,0,D3DBACKBUFFER_TYPE_MONO,&src);
    if(FAILED(hr)) goto done;
    hr=IDirect3DSurface9_GetDesc(src,&desc);
    if(FAILED(hr) || desc.Width!=800 || desc.Height!=600) goto done;
    if(FAILED(p->original->ColorFill(p->object,src,NULL,D3DCOLOR_XRGB(255,0,0)))) goto done;
    if(FAILED(p->original->ColorFill(p->object,src,&right,D3DCOLOR_XRGB(0,255,0)))) goto done;
    IDirect3DSurface9_Release(src);src=NULL;
    hr=ComposeOutput(p);
    if(FAILED(hr)) { printf("Compose HRESULT %08lx\n",(ULONG)hr);goto done; }
    hr=IDirect3DSwapChain9_GetBackBuffer(p->output,0,D3DBACKBUFFER_TYPE_MONO,&dst);
    if(FAILED(hr)) goto done;
    hr=IDirect3DSurface9_GetDesc(dst,&desc);
    if(FAILED(hr) || (desc.Format!=D3DFMT_X8R8G8B8 && desc.Format!=D3DFMT_A8R8G8B8)) goto done;
    hr=p->original->CreateOffscreenPlainSurface(p->object,desc.Width,desc.Height,desc.Format,D3DPOOL_SYSTEMMEM,&readback,NULL);
    if(FAILED(hr)) goto done;
    hr=p->original->GetRenderTargetData(p->object,dst,readback);
    if(FAILED(hr)) goto done;
    hr=IDirect3DSurface9_LockRect(readback,&lock,NULL,D3DLOCK_READONLY);
    if(FAILED(hr)) goto done;
    fit=FitRectangle(800,600,(LONG)desc.Width,(LONG)desc.Height);
    red=*(DWORD*)((BYTE*)lock.pBits+(fit.top+(fit.bottom-fit.top)/2)*lock.Pitch+(fit.left+(fit.right-fit.left)/4)*4)&0xffffff;
    green=*(DWORD*)((BYTE*)lock.pBits+(fit.top+(fit.bottom-fit.top)/2)*lock.Pitch+(fit.left+(fit.right-fit.left)*3/4)*4)&0xffffff;
    if(fit.left>0) bar=*(DWORD*)((BYTE*)lock.pBits+desc.Height/2*lock.Pitch)&0xffffff;
    else if(fit.top>0) bar=*(DWORD*)((BYTE*)lock.pBits+desc.Width/2*4)&0xffffff;
    printf("GPU output %ux%u; fit %ld,%ld-%ld,%ld; RGB %06lx/%06lx; bar %06lx\n",
        desc.Width,desc.Height,fit.left,fit.top,fit.right,fit.bottom,red,green,bar);
    good=red==0xff0000 && green==0x00ff00 && bar==0;
    IDirect3DSurface9_UnlockRect(readback);
done:
    if(src) IDirect3DSurface9_Release(src);
    if(dst) IDirect3DSurface9_Release(dst);
    if(readback) IDirect3DSurface9_Release(readback);
    return good;
}

int main(int argc, char **argv) {
    IDirect3D9 *factory; IDirect3DDevice9 *device=NULL;
    D3DPRESENT_PARAMETERS pp; HRESULT hr; Device *state; HWND window;
    RECT r,client; POINT pt,expected,origin; int i;
    BOOL mock=argc>1 && strcmp(argv[1],"--mock")==0;
    const LONG outputs[4][6]={{1920,1080,240,0,1680,1080},{2560,1440,320,0,2240,1440},
                             {800,600,0,0,800,600},{1080,1920,0,555,1080,1365}};
    setvbuf(stdout,NULL,_IONBF,0);
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    for(i=0;i<4;i++) {
        r=FitRectangle(800,600,outputs[i][0],outputs[i][1]);
        Check(r.left==outputs[i][2] && r.top==outputs[i][3] && r.right==outputs[i][4] && r.bottom==outputs[i][5],"Aspect rectangle");
    }
    window=CreateWindowExW(0,L"STATIC",L"Nega0 fullscreen hidden test",WS_OVERLAPPEDWINDOW,
                          40,40,800,600,NULL,NULL,GetModuleHandleW(NULL),NULL);
    if(!window) return 20;
    SizeClient(window,800,600);
    factory=mock ? MockFactoryCreate() : NegaDirect3DCreate9(D3D_SDK_VERSION);
    if(!factory) { DestroyWindow(window);return 21; }
    ZeroMemory(&pp,sizeof(pp));pp.BackBufferWidth=800;pp.BackBufferHeight=600;
    pp.BackBufferCount=1;pp.BackBufferFormat=D3DFMT_UNKNOWN;pp.SwapEffect=D3DSWAPEFFECT_DISCARD;
    pp.hDeviceWindow=window;pp.Windowed=TRUE;pp.PresentationInterval=D3DPRESENT_INTERVAL_IMMEDIATE;
    hr=IDirect3D9_CreateDevice(factory,D3DADAPTER_DEFAULT,D3DDEVTYPE_HAL,window,
        D3DCREATE_SOFTWARE_VERTEXPROCESSING,&pp,&device);
    if(FAILED(hr)) { printf("CreateDevice HRESULT %08lx\n",(ULONG)hr);IDirect3D9_Release(factory);DestroyWindow(window);return 22; }
    state=FindDevice(device);
    if(mock) {
        MockFactory other_factory={&mock_factory_table,2};
        MockDevice other_device={&mock_device_table,2};
        Check(factory->lpVtbl==&mock_factory_table && mock_extended_factory_table.sentinel==0x5678abcd,
              "Native factory identity and private tail preserved");
        Check(device->lpVtbl==&mock_device_table && mock_extended_device_table.sentinel==0x1234abcd,
              "Native device identity and private tail preserved");
        Check(IDirect3D9_Release((IDirect3D9*)&other_factory)==1,
              "Untracked factory sharing native table calls original Release");
        Check(IDirect3DDevice9_Release((IDirect3DDevice9*)&other_device)==1,
              "Untracked device sharing native table calls original Release");
    }
    Check(state && !state->active,"Windowed passthrough");
    Check(SUCCEEDED(IDirect3DDevice9_Present(device,NULL,NULL,NULL,NULL)) &&
          (!mock || mock_windowed_presents==1),"Windowed Present passthrough");
    pt.x=100;pt.y=150;expected=pt;
    ClientToScreen(window,&expected);NegaClientToScreen(window,&pt);
    Check(pt.x==expected.x && pt.y==expected.y,"Windowed coordinate passthrough");
    if(mock) {
        Check((GetWindowLongW(window,GWL_STYLE)&WS_THICKFRAME)!=0 && state->resizable,
              "Windowed corner sizing border enabled");
        SizeClient(window,1500,900);
        GetClientRect(window,&client); r=FitRectangle(800,600,client.right,client.bottom);
        Check(SUCCEEDED(IDirect3DDevice9_Present(device,NULL,NULL,NULL,NULL)) && state->active &&
              !state->fullscreen && EqualRect(&r,&mock_last_destination),
              "Windowed resized picture uses aspect-preserving output");
        pt.x=400;pt.y=300;NegaClientToScreen(window,&pt);NegaScreenToClient(window,&pt);
        Check(pt.x==400 && pt.y==300,"Resized window mouse coordinate roundtrip");
        SizeClient(window,800,600);
        Check(SUCCEEDED(IDirect3DDevice9_Present(device,NULL,NULL,NULL,NULL)) && !state->active && !state->output,
              "Original window size restores native Present and releases output");
        mock_black_fills=mock_copies=mock_native_parent_releases=0;
    }
    pp.Windowed=FALSE;pp.BackBufferFormat=D3DFMT_X8R8G8B8;pp.FullScreen_RefreshRateInHz=60;
    hr=IDirect3DDevice9_Reset(device,&pp);
    Check(SUCCEEDED(hr) && state->active && !pp.Windowed,"Fullscreen request redirected without changing game mode flag");
    if(SUCCEEDED(hr)) {
        Check(!IsWindowVisible(window),"Test window stays hidden");
        if(mock) {
            GetClientRect(window,&client);r=FitRectangle(800,600,client.right,client.bottom);
            Check(SUCCEEDED(ComposeOutput(state)) && mock_black_fills==1 && mock_copies==1 &&
                EqualRect(&r,&mock_last_destination),"COM routing: native source, aspect copy and black fill");
            Check(state->output!=NULL && mock_native_parent_releases>=2,
                  "Native surface parent Release preserves composed output");
            Check(mock_reset_callback_presents==1 && mock_windowed_presents==2 && mock_output_presents==1,
                  "Present callback during Reset skips unfinished D3D state");
            Check(state->operation_depth==0,"Compose and Reset leave operation guard balanced");
            mock_force_point=TRUE;
            Check(SUCCEEDED(ComposeOutput(state)) && state->filter_logged,"Unsupported linear filter fallback");
        } else Check(PaintAndRead(state),"Actual GPU upscale and black bars");
        Check(SUCCEEDED(IDirect3DDevice9_Present(device,NULL,NULL,NULL,NULL)),"Hooked fullscreen Present");
        GetClientRect(window,&client);r=FitRectangle(800,600,client.right,client.bottom);
        pt.x=400;pt.y=300;origin.x=0;origin.y=0;ClientToScreen(window,&origin);
        NegaClientToScreen(window,&pt);
        Check(pt.x==origin.x+r.left+(r.right-r.left)/2 && pt.y==origin.y+r.top+(r.bottom-r.top)/2,"Logical-to-screen center");
        NegaScreenToClient(window,&pt);
        Check(pt.x==400 && pt.y==300,"Screen-to-logical center");
        pt=origin;pt.x+=r.left-10;pt.y+=r.top+(r.bottom-r.top)/2;
        NegaScreenToClient(window,&pt);Check(pt.x<0,"Black bar stays outside logical picture");
        pp.Windowed=TRUE;pp.BackBufferFormat=D3DFMT_UNKNOWN;pp.FullScreen_RefreshRateInHz=0;
        SetWindowLongW(window,GWL_STYLE,WS_OVERLAPPEDWINDOW);
        SizeClient(window,800,600);
        hr=IDirect3DDevice9_Reset(device,&pp);
        Check(SUCCEEDED(hr) && !state->active && !state->output && !state->resolved,"Reset releases fullscreen resources");
        if(mock) {
            mock_force_missing_output=TRUE; state->active=TRUE; state->fullscreen=TRUE;
            Check(FAILED(IDirect3DDevice9_Present(device,NULL,NULL,NULL,NULL)) && state->operation_depth==0,
                  "Missing output chain returns failure without null dereference");
            mock_force_missing_output=FALSE; state->error_logged=FALSE; state->active=FALSE; state->fullscreen=FALSE;
        }
        pp.Windowed=FALSE;pp.BackBufferFormat=D3DFMT_X8R8G8B8;pp.FullScreen_RefreshRateInHz=60;
        hr=IDirect3DDevice9_Reset(device,&pp);
        Check(SUCCEEDED(hr) && (mock ? SUCCEEDED(ComposeOutput(state)) : PaintAndRead(state)),"Repeat fullscreen transition");
        if(mock) {
            pp.MultiSampleType=D3DMULTISAMPLE_2_SAMPLES;
            hr=IDirect3DDevice9_Reset(device,&pp);
            Check(SUCCEEDED(hr) && SUCCEEDED(ComposeOutput(state)) && mock_resolves==1,"Multisample resolve before scaling");
            Check(mock_reset_resources_released,"Output resources released before every Reset");
            Check(mock_output_presents==2 && mock_windowed_presents==2,"Fullscreen uses output chain, windowed uses original Present");
        }
    }
    Check(IDirect3DDevice9_Release(device)==0 && devices==NULL,"Device and swap chain lifetime");
    Check(IDirect3D9_Release(factory)==0 && factories==NULL,"Factory lifetime");
    DestroyWindow(window);
    printf("Fullscreen checks: %s (%d failures)\n",fail?"FAIL":"PASS",fail);
    return fail?1:0;
}
