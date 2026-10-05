#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include "display_mapping.h"
#include "local_assets.h"

static INIT_ONCE font_once = INIT_ONCE_STATIC_INIT;
static BOOL font_ready = FALSE;
static INIT_ONCE log_once = INIT_ONCE_STATIC_INIT;
static HANDLE diagnostic_log = INVALID_HANDLE_VALUE;
static SRWLOCK log_lock = SRWLOCK_INIT;
void WINAPI NegaOutputDebugStringW(LPCWSTR message);
static BOOL CALLBACK OpenDiagnosticLog(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    WCHAR path[32768]; DWORD n, written; SYSTEMTIME time; char header[128]; int count;
    (void)once; (void)parameter; (void)context;
    n=GetEnvironmentVariableW(L"NEGA0_KOREAN_LOG",path,32768);
    if(!n) {
        n=GetTempPathW(32768,path);
        if(!n || n+32>=32768) return TRUE;
        lstrcatW(path,L"Nega0Korean-runtime.log");
    } else if(n>=32768) return TRUE;
    diagnostic_log=CreateFileW(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
    if(diagnostic_log==INVALID_HANDLE_VALUE) return TRUE;
    GetLocalTime(&time);
    count=sprintf_s(header,sizeof(header),"Nega0 Korean runtime / %04u-%02u-%02u %02u:%02u:%02u\r\n",
        time.wYear,time.wMonth,time.wDay,time.wHour,time.wMinute,time.wSecond);
    if(count>0) WriteFile(diagnostic_log,header,(DWORD)count,&written,NULL);
    return TRUE;
}

/* Full local data takes precedence over disc paths. Incomplete installations
   retain the game's original disc search and warning. No media files are copied. */
BOOL WINAPI NegaResolveLocalInstallation(LPCWSTR folder, LPWSTR voice_root, DWORD capacity) {
    WCHAR path[32768]; SIZE_T n, i; WIN32_FILE_ATTRIBUTE_DATA file;
    if(!folder || !voice_root || !capacity) return FALSE;
    n=(SIZE_T)lstrlenW(folder);
    if(!n || n+8>=capacity || n+64>=32768) return FALSE;
    lstrcpyW(path,folder);
    if(path[n-1]!=L'\\') path[n++]=L'\\';
    for(i=0;i<LOCAL_ASSET_COUNT;i++) {
        ULONGLONG bytes;
        lstrcpyW(path+n,local_assets[i].path);
        if(!GetFileAttributesExW(path,GetFileExInfoStandard,&file) || file.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY) return FALSE;
        bytes=((ULONGLONG)file.nFileSizeHigh<<32)|file.nFileSizeLow;
        if(bytes!=local_assets[i].size) return FALSE;
    }
    lstrcpyW(path+n,L"Voice\\");
    lstrcpyW(voice_root,path);
    return TRUE;
}

typedef BOOL (__cdecl *OriginalDiscSearch)(LPWSTR,LPCWSTR);
BOOL __cdecl NegaFindLocalGameDisc(LPWSTR root_out, LPCWSTR volume_name, LPWSTR voice_root) {
    WCHAR module[32768], *last=NULL, *p; DWORD n;
    n=GetModuleFileNameW(NULL,module,32768);
    if(n && n<32768 && root_out && volume_name && voice_root &&
       lstrcmpiW(volume_name,L"NegaZero")==0) {
        for(p=module;*p;p++) if(*p==L'\\') last=p;
        if(last) {
            *last=0;
            if(NegaResolveLocalInstallation(module,voice_root,260)) {
                root_out[0]=module[0]; root_out[1]=L':'; root_out[2]=L'\\'; root_out[3]=0;
                NegaOutputDebugStringW(L"Complete local installation verified (119 assets); local Voice path selected.\n");
                return TRUE;
            }
        }
    }
    /* Verified original executable retains this function unchanged. */
    return ((OriginalDiscSearch)((BYTE*)GetModuleHandleW(NULL)+0x000f5720))(root_out,volume_name);
}

/* Preserve the game's existing diagnostic output, also retaining its own
   source-file/line/HRESULT messages for the reported runtime failure. */
void WINAPI NegaOutputDebugStringW(LPCWSTR message) {
    DWORD saved_error=GetLastError(), written; int count; char text[16384];
    InitOnceExecuteOnce(&log_once,OpenDiagnosticLog,NULL,NULL);
    if(message && diagnostic_log!=INVALID_HANDLE_VALUE) {
        count=WideCharToMultiByte(CP_UTF8,0,message,-1,text,sizeof(text),NULL,NULL);
        if(count>0) {
            AcquireSRWLockExclusive(&log_lock);
            if(GetFileSize(diagnostic_log,NULL)<1024*1024) {
                WriteFile(diagnostic_log,text,(DWORD)count-1,&written,NULL);
                WriteFile(diagnostic_log,"\r\n",2,&written,NULL);
                FlushFileBuffers(diagnostic_log);
            }
            ReleaseSRWLockExclusive(&log_lock);
        }
    }
    SetLastError(saved_error);
    OutputDebugStringW(message);
}
static BOOL CALLBACK LoadPrivateFont(PINIT_ONCE once, PVOID parameter, PVOID *context) {
    WCHAR path[32768]; HMODULE self = NULL; DWORD n; WCHAR *last = NULL, *p;
    (void)once; (void)parameter; (void)context;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS |
        GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT, (LPCWSTR)&LoadPrivateFont, &self)) return TRUE;
    n=GetModuleFileNameW(self,path,32768);
    if(!n || n>=32768) return TRUE;
    for(p=path;*p;p++) if(*p==L'\\') last=p;
    if(!last || last-path+20>=32768) return TRUE;
    lstrcpyW(last+1,L"Nega0Korean.ttf");
    font_ready=AddFontResourceExW(path,FR_PRIVATE,0)>0;
    return TRUE;
}

/* Game byte walkers understand one/two-byte CP932, including its private slots.
   Decode normally, then replace only source-audited private display characters.
   This also works for individual characters and split backlog substrings. */
BOOL WINAPI NegaIsDBCSLeadByte(BYTE value) {
    /* CP932 resources must use the same lead-byte definition as conversion.
       The original API consults CP_ACP (949 on a Korean system). */
    return IsDBCSLeadByteEx(932,value);
}

typedef int (__cdecl *OriginalEsoTextureLoad)(LPCWSTR,void*,BYTE*,BYTE*);
int __cdecl NegaLoadEsoTexture(LPCWSTR name,void *context,BYTE *deferred,BYTE *created) {
    BYTE *base=(BYTE*)GetModuleHandleW(NULL);
    WCHAR message[640]; int index; DWORD count; void *pool;
    /* Two verified callers immediately feed this result to the engine's
       texture lookup before the reported crash. Preserve every argument. */
    swprintf_s(message,640,L"ESO texture begin: %.240ls\n",name ? name : L"(null)");
    NegaOutputDebugStringW(message);
    index=((OriginalEsoTextureLoad)(base+0x1ebbc0))(name,context,deferred,created);
    count=*(DWORD*)(base+0x38f66c);
    pool=*(void**)(base+0x38f670);
    swprintf_s(message,640,L"ESO texture end: index=%d count=%lu pool=%p valid=%d name=%.240ls\n",
        index,count,pool,index>=0 && (DWORD)index<count && pool!=NULL,name ? name : L"(null)");
    NegaOutputDebugStringW(message);
    return index;
}

int WINAPI NegaMultiByteToWideChar(UINT page, DWORD flags, LPCCH src, int bytes,
                                  LPWSTR dst, int capacity) {
    int result, i;
    if (page == 932 && src && (bytes == -1 || bytes > 3) &&
        (unsigned char)src[0] == 0xef &&
        (unsigned char)src[1] == 0xbb &&
        (unsigned char)src[2] == 0xbf) {
        return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, src + 3,
                                  bytes == -1 ? -1 : bytes - 3, dst, capacity);
    }
    result=MultiByteToWideChar(page, flags, src, bytes, dst, capacity);
    if(page==932 && result>0 && dst && capacity>0) {
        for(i=0;i<result;i++) {
            unsigned slot=(unsigned)dst[i]-0xe000;
            if(slot<NEGA_DISPLAY_COUNT) dst[i]=display_unicode[slot];
        }
    }
    return result;
}

static WCHAR ToPrivateSlot(WCHAR c) {
    int low=0, high=NEGA_DISPLAY_COUNT;
    while(low<high) {
        int mid=low+(high-low)/2;
        if(display_unicode[mid]<c) low=mid+1; else high=mid;
    }
    return low<NEGA_DISPLAY_COUNT && display_unicode[low]==c ? (WCHAR)(0xe000+low) : c;
}

int WINAPI NegaWideCharToMultiByte(UINT page, DWORD flags, LPCWCH src, int chars,
    LPSTR dst, int capacity, LPCCH default_char, LPBOOL used_default) {
    int n, i, result; DWORD error; WCHAR *mapped; BOOL changed=FALSE;
    if(page!=932 || !src || chars==0 || chars<-1)
        return WideCharToMultiByte(page,flags,src,chars,dst,capacity,default_char,used_default);
    n=chars==-1 ? lstrlenW(src)+1 : chars;
    for(i=0;i<n;i++) if(ToPrivateSlot(src[i])!=src[i]) { changed=TRUE; break; }
    if(!changed) return WideCharToMultiByte(page,flags,src,chars,dst,capacity,default_char,used_default);
    mapped=(WCHAR*)HeapAlloc(GetProcessHeap(),0,(SIZE_T)n*sizeof(WCHAR));
    if(!mapped) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
    for(i=0;i<n;i++) mapped[i]=ToPrivateSlot(src[i]);
    result=WideCharToMultiByte(page,flags,mapped,chars,dst,capacity,default_char,used_default);
    error=GetLastError();
    HeapFree(GetProcessHeap(),0,mapped);
    SetLastError(error);
    return result;
}

HFONT WINAPI NegaCreateFontW(int height, int width, int escapement, int orientation,
    int weight, DWORD italic, DWORD underline, DWORD strikeout, DWORD charset,
    DWORD outprecision, DWORD clipprecision, DWORD quality, DWORD pitch,
    LPCWSTR face) {
    (void)charset; (void)face;
    InitOnceExecuteOnce(&font_once,LoadPrivateFont,NULL,NULL);
    if(!font_ready) { SetLastError(ERROR_FILE_NOT_FOUND); return NULL; }
    /* Slightly larger dialogue ink, without changing the game's line origins.
       Keep positive cell heights; -24 previously grew the cell to 35. */
    if(height==24) height=26;
    return CreateFontW(height, width, escapement, orientation, weight, italic,
        underline, strikeout, HANGEUL_CHARSET, outprecision, clipprecision,
        quality, pitch, L"Noto Sans KR");
}

BOOL WINAPI NegaGetCharABCWidthsW(HDC dc, UINT first, UINT last, LPABC widths) {
    BOOL result=GetCharABCWidthsW(dc,first,last,widths);
    LOGFONTW font;
    /* The game consumes A+B+C to lay out characters at its audited call site.
       Add whitespace advance only; glyph bearings and non-space metrics stay
       identical to GDI for the selected font. Other UI sizes are unchanged. */
    if(result && widths && first<=0x20 && last>=0x20 &&
       GetObjectW(GetCurrentObject(dc,OBJ_FONT),sizeof(font),&font)==sizeof(font) &&
       font.lfHeight==26 && lstrcmpiW(font.lfFaceName,L"Noto Sans KR")==0) {
        widths[0x20-first].abcC+=2;
    }
    return result;
}
