using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;

namespace NegaPatch {
    public class Entry {
        public string path, action, source_sha256, target_sha256, payload, payload_sha256;
        public long source_size, target_size, payload_size;
    }
    public class Guard { public string path, sha256; }
    public class Manifest {
        public int manifest_version;
        public string patch_id, patch_version, display_name, description;
        public Entry[] files;
        public Guard[] guards;
    }
    public class State { public string status; public Manifest manifest; }

    public static class Delta {
        [StructLayout(LayoutKind.Sequential)] struct Input { public IntPtr data; public UIntPtr size; public int editable; }
        [StructLayout(LayoutKind.Sequential)] struct Output { public IntPtr data; public UIntPtr size; }
        [DllImport("msdelta.dll",SetLastError=true)] static extern bool ApplyDeltaB(long flags,Input source,Input delta,out Output output);
        [DllImport("msdelta.dll")] static extern bool DeltaFree(IntPtr data);
        public static byte[] Apply(byte[] source,byte[] patch) {
            var a=GCHandle.Alloc(source,GCHandleType.Pinned); var b=GCHandle.Alloc(patch,GCHandleType.Pinned);
            Output output=new Output();
            try {
                var aa=new Input{data=a.AddrOfPinnedObject(),size=(UIntPtr)(ulong)source.Length};
                var bb=new Input{data=b.AddrOfPinnedObject(),size=(UIntPtr)(ulong)patch.Length};
                if(!ApplyDeltaB(0,aa,bb,out output)) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                long size=(long)output.size.ToUInt64();
                if(size>256*1024*1024) throw new IOException("패치 출력 크기가 허용 범위를 넘었습니다.");
                byte[] result=new byte[(int)size]; Marshal.Copy(output.data,result,0,result.Length); return result;
            } finally { if(output.data!=IntPtr.Zero) DeltaFree(output.data); a.Free(); b.Free(); }
        }
    }

    public class Engine {
        public const string Manage=".nega0-korean";
        public string Root,Package;
        public Action<string> Progress=delegate{};
        public Action<int> AfterReplace=delegate{}; // Test harness fault injection; GUI never sets it.
        public Func<bool> CancelRequested=delegate { return false; };
        public Action CommitStarted=delegate{};
        void CheckCancellation() { if(CancelRequested()) throw new OperationCanceledException("파일 교체 전에 취소했습니다."); }
        readonly JavaScriptSerializer json=new JavaScriptSerializer{MaxJsonLength=1024*1024};
        void Notify(string message) {
            // Logs contain file names and outcomes, never game dialogue or API data.
            try { File.AppendAllText(Managed("operations.log"),DateTime.Now.ToString("s")+" "+message+Environment.NewLine,new UTF8Encoding(false)); }
            catch(IOException) { } catch(UnauthorizedAccessException) { }
            Progress(message);
        }
        public Engine(string root,string package) {
            Root=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
            Package=Path.GetFullPath(package);
            if(!Directory.Exists(Root)) throw new IOException("게임 폴더가 없습니다.");
            CheckTree(Root);
        }
        static void CheckTree(string path) {
            string at=Path.GetFullPath(path);
            while(!String.IsNullOrEmpty(at)) {
                if((File.Exists(at)||Directory.Exists(at)) && (File.GetAttributes(at)&FileAttributes.ReparsePoint)!=0)
                    throw new IOException("연결된 폴더/파일은 적용 대상으로 사용할 수 없습니다: "+at);
                at=Path.GetDirectoryName(at);
            }
        }
        string Safe(string relative,bool managed=false) {
            if(String.IsNullOrEmpty(relative)||Path.IsPathRooted(relative)||relative.Contains(':')) throw new IOException("잘못된 상대 경로");
            string[] parts=relative.Replace('\\','/').Split('/');
            if(parts.Any(x=>x==".."||x=="."||x.Length==0||x.EndsWith(".")||x.EndsWith(" "))) throw new IOException("잘못된 상대 경로");
            if(!managed && parts[0].Equals(Manage,StringComparison.OrdinalIgnoreCase)) throw new IOException("관리 폴더 충돌");
            string full=Path.GetFullPath(Path.Combine(Root,relative));
            if(!full.StartsWith(Root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)) throw new IOException("폴더 밖 경로");
            CheckTree(full); return full;
        }
        string Managed(string name) { return Safe(Manage+"/"+name,true); }
        public static string Hash(byte[] b) { using(var h=SHA256.Create()) return BitConverter.ToString(h.ComputeHash(b)).Replace("-","").ToLowerInvariant(); }
        public static string HashFile(string p) { using(var h=SHA256.Create()) using(var f=File.OpenRead(p)) return BitConverter.ToString(h.ComputeHash(f)).Replace("-","").ToLowerInvariant(); }
        static bool ValidHash(string s) { return s!=null && s.Length==64 && s.All(c=>"0123456789abcdef".Contains(c)); }
        void Validate(Manifest m) {
            if(m==null||m.manifest_version!=1||m.patch_id!="nega0-ko"||String.IsNullOrEmpty(m.patch_version)||m.files==null||m.files.Length==0||m.files.Length>32)
                throw new IOException("지원하지 않는 패치 명세입니다.");
            var paths=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach(var e in m.files) {
                string target=Safe(e.path);
                if(!paths.Add(target)||!ValidHash(e.target_sha256)||!ValidHash(e.payload_sha256)||e.target_size<0||e.target_size>256*1024*1024||e.payload_size<0)
                    throw new IOException("패치 명세가 잘못되었습니다.");
                if(e.action!="replace" && e.action!="add") throw new IOException("지원하지 않는 파일 동작");
                if(e.action=="replace" && (!ValidHash(e.source_sha256)||e.source_size<0)) throw new IOException("원본 해시 누락");
                if(e.action=="add" && (e.source_sha256!=null||e.source_size!=0)) throw new IOException("신규 파일 명세 오류");
                if(String.IsNullOrEmpty(e.payload)||Path.GetFileName(e.payload)!=e.payload||e.payload.IndexOfAny(new[]{':','/','\\'})>=0) throw new IOException("패치 데이터 경로 오류");
            }
            if(m.guards==null) throw new IOException("기준 파일 명세 누락");
            foreach(var g in m.guards) { Safe(g.path); if(!ValidHash(g.sha256)) throw new IOException("기준 파일 해시 오류"); }
        }
        public Manifest LoadManifest() {
            CheckTree(Package); string p=Path.Combine(Package,"manifest.json"); CheckTree(p);
            var m=json.Deserialize<Manifest>(File.ReadAllText(p,Encoding.UTF8)); Validate(m); return m;
        }
        State ReadState() {
            var p=Managed("state.json"); if(!File.Exists(p)) return null;
            var s=json.Deserialize<State>(File.ReadAllText(p,Encoding.UTF8));
            if(s==null) throw new IOException("설치 상태 파일 오류"); Validate(s.manifest); return s;
        }
        void Save(State s) {
            string path=Managed("state.json"),tmp=Managed("state.pending");
            byte[] bytes=new UTF8Encoding(false).GetBytes(json.Serialize(s));
            using(var f=new FileStream(tmp,FileMode.Create,FileAccess.Write,FileShare.None)) { f.Write(bytes,0,bytes.Length); f.Flush(true); }
            if(File.Exists(path)) File.Replace(tmp,path,null); else File.Move(tmp,path);
        }
        public string Status() {
            var s=ReadState();
            if(s==null||s.status=="restored") return "원본 상태";
            if(s.status=="installed") return "한글패치 적용됨 / "+s.manifest.patch_version;
            return "중단된 작업이 있습니다. 원본 복원 필요 / "+s.manifest.patch_version;
        }
        public static long RequiredSpace(Manifest m) { return m.files.Sum(e=>e.source_size+e.target_size)+32L*1024*1024; }
        FileStream Lock() {
            Directory.CreateDirectory(Safe(Manage,true));
            return new FileStream(Managed("operation.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
        }
        void CheckGuards(Manifest m) {
            foreach(var g in m.guards) if(!File.Exists(Safe(g.path))||HashFile(Safe(g.path))!=g.sha256)
                throw new IOException("지원하는 원본과 다른 파일: "+g.path);
        }
        void CheckGameClosed() {
            if(System.Diagnostics.Process.GetProcessesByName("NegaZero").Length>0)
                throw new IOException("Nega0 게임을 종료한 뒤 다시 진행해 주세요.");
        }
        void Expected(Entry e,bool patched) {
            string p=Safe(e.path); string hash=patched?e.target_sha256:e.source_sha256;
            if(hash==null) { if(File.Exists(p)||Directory.Exists(p)) throw new IOException("기존 파일과 충돌: "+e.path); }
            else if(!File.Exists(p)||HashFile(p)!=hash) throw new IOException("예상한 버전과 다른 파일: "+e.path);
        }
        void EnsureSpace(Manifest m) {
            long required=RequiredSpace(m);
            if(new DriveInfo(Path.GetPathRoot(Root)).AvailableFreeSpace<required) throw new IOException("임시 출력과 백업을 위한 공간이 부족합니다.");
        }
        public void Apply() {
            Manifest m=LoadManifest(); CheckGameClosed();
            using(Lock()) {
                var previous=ReadState();
                if(previous!=null && previous.status!="restored") {
                    if(previous.status=="installed" && previous.manifest.patch_version==m.patch_version) {
                        foreach(var e in m.files) Expected(e,true);
                        Notify("이미 같은 버전이 적용되어 있습니다."); return;
                    }
                    throw new IOException("기존 패치 또는 중단된 작업이 있습니다. 먼저 원본 복원을 실행해 주세요.");
                }
                CheckGuards(m); EnsureSpace(m);
                foreach(var e in m.files) Expected(e,false);
                Directory.CreateDirectory(Managed("backups")); Directory.CreateDirectory(Managed("stage"));
                var prepared=new List<int>();
                try {
                for(int i=0;i<m.files.Length;i++) {
                    CheckCancellation();
                    var e=m.files[i]; Notify("준비 중: "+e.path);
                    byte[] source=e.action=="replace"?File.ReadAllBytes(Safe(e.path)):new byte[0];
                    if(e.action=="replace" && Hash(source)!=e.source_sha256) throw new IOException("작업 중 원본 변경: "+e.path);
                    string payloadPath=Path.Combine(Package,e.payload); CheckTree(payloadPath);
                    byte[] payload=File.ReadAllBytes(payloadPath);
                    if(payload.LongLength!=e.payload_size||Hash(payload)!=e.payload_sha256) throw new IOException("패치 데이터 손상: "+e.payload);
                    byte[] output=Delta.Apply(source,payload);
                    if(output.LongLength!=e.target_size||Hash(output)!=e.target_sha256) throw new IOException("출력 검증 실패: "+e.path);
                    File.WriteAllBytes(Managed("stage/"+i+".new"),output);
                    prepared.Add(i);
                    if(e.action=="replace") {
                        string backup=Managed("backups/"+e.source_sha256+".bin");
                        if(!File.Exists(backup)) using(var f=new FileStream(backup,FileMode.CreateNew,FileAccess.Write,FileShare.None)) { f.Write(source,0,source.Length); f.Flush(true); }
                        if(HashFile(backup)!=e.source_sha256) throw new IOException("원본 백업 손상: "+e.path);
                    }
                }
                CheckCancellation();
                } catch(OperationCanceledException) {
                    foreach(int i in prepared) {
                        string stage=Managed("stage/"+i+".new");
                        if(File.Exists(stage) && HashFile(stage)==m.files[i].target_sha256) File.Delete(stage);
                    }
                    Notify("취소 완료. 게임 파일은 교체하지 않았습니다."); throw;
                }
                CommitStarted();
                var state=new State{status="applying",manifest=m}; Save(state);
                try {
                    CheckGameClosed();
                    for(int i=0;i<m.files.Length;i++) {
                        var e=m.files[i]; Expected(e,false);
                        string stage=Managed("stage/"+i+".new"),dest=Safe(e.path);
                        if(HashFile(stage)!=e.target_sha256) throw new IOException("준비 파일 변경: "+e.path);
                        Directory.CreateDirectory(Path.GetDirectoryName(dest));
                        if(e.action=="replace") File.Replace(stage,dest,null); else File.Move(stage,dest);
                        AfterReplace(i); Notify("적용 중: "+e.path);
                    }
                    foreach(var e in m.files) Expected(e,true);
                    state.status="installed"; Save(state); Notify("적용 완료. 게임을 실행해 확인해 주세요.");
                } catch(Exception installError) {
                    // Keep the durable journal/backups; recovery preflights all files.
                    // Never overwrite a conflicting file to claim a successful rollback.
                    try { RestoreLocked(state); }
                    catch(Exception restoreError) {
                        Notify("적용 실패: "+installError.Message+" / 자동 복원 실패: "+restoreError.Message);
                        throw new IOException("적용에 실패했고 자동 복원도 완료하지 못했습니다. 원본 백업은 유지됩니다. 적용 오류: "+installError.Message+" / 복원 오류: "+restoreError.Message,restoreError);
                    }
                    Notify("적용 실패 후 원본 복원 완료: "+installError.Message);
                    throw;
                }
            }
        }
        public void Restore() {
            CheckGameClosed(); using(Lock()) {
                var state=ReadState();
                if(state==null||state.status=="restored") { Notify("복원할 패치가 없습니다."); return; }
                RestoreLocked(state,true);
            }
        }
        void RestoreLocked(State state,bool canCancel=false) {
            foreach(var e in state.manifest.files) {
                if(canCancel) CheckCancellation();
                string p=Safe(e.path);
                if(e.action=="replace") {
                    string backup=Managed("backups/"+e.source_sha256+".bin");
                    if(!File.Exists(backup)||HashFile(backup)!=e.source_sha256) throw new IOException("복원용 백업이 없거나 손상됨: "+e.path);
                }
                if(File.Exists(p)) {
                    string h=HashFile(p);
                    if(h!=e.target_sha256 && h!=e.source_sha256) throw new IOException("복원 충돌: 다른 내용으로 변경된 "+e.path);
                } else if(Directory.Exists(p)) throw new IOException("복원 충돌: 폴더가 된 "+e.path);
            }
            if(canCancel) { CheckCancellation(); CommitStarted(); }
            state.status="restoring"; Save(state);
            for(int i=state.manifest.files.Length-1;i>=0;i--) {
                var e=state.manifest.files[i]; string p=Safe(e.path);
                if(File.Exists(p)) {
                    string h=HashFile(p);
                    if(h!=e.target_sha256 && h!=e.source_sha256) throw new IOException("복원 중 파일 변경: "+e.path);
                    if(h==e.source_sha256) continue;
                }
                if(e.action=="add") { if(File.Exists(p)) File.Delete(p); }
                else {
                    string temp=Managed("stage/restore-"+i+".new");
                    Directory.CreateDirectory(Path.GetDirectoryName(temp));
                    File.Copy(Managed("backups/"+e.source_sha256+".bin"),temp,true);
                    if(HashFile(temp)!=e.source_sha256) throw new IOException("복원 준비 파일 손상");
                    if(File.Exists(p)) File.Replace(temp,p,null); else File.Move(temp,p);
                }
                Notify("복원 중: "+e.path);
            }
            foreach(var e in state.manifest.files) Expected(e,false);
            state.status="restored"; Save(state); Notify("원본 복원 완료. 세이브와 설정은 유지됩니다.");
        }
    }
}
