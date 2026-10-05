using System;
using System.IO;
using System.Text;
using System.Drawing;
using System.Windows.Forms;
using System.Threading.Tasks;
using System.Diagnostics;
using System.Web.Script.Serialization;

namespace NegaPatch {
    class Window : Form {
        TextBox folder=new TextBox(),log=new TextBox();
        Button browse=new Button(),apply=new Button(),restore=new Button(),cancel=new Button();
        Label info=new Label(),status=new Label(); bool busy; volatile bool cancelRequested;
        Manifest manifest;
        readonly string package=AppDomain.CurrentDomain.BaseDirectory;
        public Window(string initial) {
            Text="Nega0 한글패치"; Size=new Size(780,540); MinimumSize=new Size(680,480);
            StartPosition=FormStartPosition.CenterScreen; Font=new Font("Malgun Gothic",10);
            var layout=new TableLayoutPanel{Dock=DockStyle.Fill,Padding=new Padding(18),ColumnCount=2,RowCount=6};
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,100));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,84)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute,40));
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,60)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute,52));
            layout.RowStyles.Add(new RowStyle(SizeType.Percent,100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute,40));
            try {
                manifest=new JavaScriptSerializer().Deserialize<Manifest>(File.ReadAllText(Path.Combine(package,"manifest.json"),Encoding.UTF8));
                info.Text=manifest.display_name+" / "+manifest.patch_version+"\r\n"+manifest.description+"\r\n게임을 종료한 뒤 설치 폴더를 선택하세요.";
            } catch(Exception ex) { info.Text="패치 데이터를 읽지 못했습니다: "+ex.Message; }
            info.Dock=DockStyle.Fill; layout.Controls.Add(info,0,0); layout.SetColumnSpan(info,2);
            folder.Dock=DockStyle.Fill; folder.Text=String.IsNullOrEmpty(initial)?@"C:\Program Files (x86)\Will\Nega 0":initial;
            browse.Text="폴더 선택"; browse.Dock=DockStyle.Fill;
            browse.Click+=delegate { using(var d=new FolderBrowserDialog{Description="NegaZero.exe가 있는 게임 폴더",SelectedPath=folder.Text}) if(d.ShowDialog()==DialogResult.OK) folder.Text=d.SelectedPath; };
            layout.Controls.Add(folder,0,1); layout.Controls.Add(browse,1,1);
            status.Dock=DockStyle.Fill; layout.Controls.Add(status,0,2); layout.SetColumnSpan(status,2);
            var buttons=new FlowLayoutPanel{Dock=DockStyle.Fill};
            apply.Text="한글패치 적용"; apply.AutoSize=true; apply.Height=36;
            restore.Text="원본 복원"; restore.AutoSize=true; restore.Height=36;
            cancel.Text="준비 취소"; cancel.AutoSize=true; cancel.Height=36; cancel.Enabled=false;
            buttons.Controls.Add(apply); buttons.Controls.Add(restore); buttons.Controls.Add(cancel); layout.Controls.Add(buttons,0,3); layout.SetColumnSpan(buttons,2);
            log.Multiline=true; log.ReadOnly=true; log.ScrollBars=ScrollBars.Vertical; log.Dock=DockStyle.Fill;
            layout.Controls.Add(log,0,4); layout.SetColumnSpan(log,2);
            var note=new Label{Text="원본은 자동 백업됩니다. 세이브·설정은 유지됩니다.\r\n작업 기록: 게임 폴더의 .nega0-korean / operations.log",Dock=DockStyle.Fill};
            layout.Controls.Add(note,0,5); layout.SetColumnSpan(note,2); Controls.Add(layout);
            apply.Click+=delegate { Run(false); }; restore.Click+=delegate { Run(true); };
            cancel.Click+=delegate { cancelRequested=true; cancel.Enabled=false; Append("취소 요청을 처리하고 있습니다."); };
            folder.Leave+=delegate { RefreshStatus(); }; Shown+=delegate { RefreshStatus(); };
            apply.Enabled=manifest!=null;
            FormClosing+=delegate(object sender,FormClosingEventArgs e) { if(busy) { e.Cancel=true; MessageBox.Show("진행 중인 파일 작업을 마친 뒤 닫을 수 있습니다."); } };
        }
        void Append(string text) { log.AppendText(text+Environment.NewLine); }
        void RefreshStatus() {
            if(busy) return;
            try {
                var engine=new Engine(folder.Text,package);
                string detected=File.Exists(Path.Combine(engine.Root,"NegaZero.exe"))?engine.Status():"게임 실행 파일이 없는 폴더";
                string space="";
                if(manifest!=null) {
                    var checkedManifest=engine.LoadManifest();
                    long available=new DriveInfo(Path.GetPathRoot(engine.Root)).AvailableFreeSpace;
                    space=String.Format("\r\n필요한 공간: 약 {0:N0} MB / 남은 공간: {1:N0} MB",Math.Ceiling(Engine.RequiredSpace(checkedManifest)/1048576.0),Math.Floor(available/1048576.0));
                }
                status.Text=detected+space;
            } catch(Exception ex) { status.Text="폴더 확인: "+ex.Message; }
        }
        void Run(bool restoring) {
            string target=folder.Text;
            busy=true; cancelRequested=false; apply.Enabled=restore.Enabled=browse.Enabled=folder.Enabled=false; cancel.Enabled=true;
            Append(restoring?"원본 복원을 준비합니다.":"원본과 패치 데이터를 확인합니다.");
            Task.Factory.StartNew(delegate {
                Exception failure=null;
                try {
                    var engine=new Engine(target,package);
                    engine.Progress=message=>Invoke(new Action(()=>Append(message)));
                    engine.CancelRequested=()=>cancelRequested;
                    engine.CommitStarted=()=>Invoke(new Action(delegate { cancel.Enabled=false; Append("파일 교체 중입니다. 완료될 때까지 기다려 주세요."); }));
                    if(restoring) engine.Restore(); else engine.Apply();
                } catch(Exception ex) { failure=ex; }
                Invoke(new Action(delegate {
                    busy=false; apply.Enabled=manifest!=null; restore.Enabled=browse.Enabled=folder.Enabled=true; cancel.Enabled=false; RefreshStatus();
                    if(failure!=null) {
                        Append((failure is OperationCanceledException?"취소: ":"완료하지 못했습니다: ")+failure.Message);
                        if(failure is UnauthorizedAccessException) {
                            if(MessageBox.Show(this,"선택한 게임 폴더에 쓰기 권한이 필요합니다. 관리자 권한으로 패치 프로그램을 다시 열까요?","폴더 쓰기 권한",MessageBoxButtons.YesNo)==DialogResult.Yes) {
                                try { Process.Start(new ProcessStartInfo(Application.ExecutablePath,"--folder \""+target+"\""){UseShellExecute=true,Verb="runas"}); Close(); }
                                catch(Exception ex) { Append("권한 요청을 완료하지 못했습니다: "+ex.Message); }
                            }
                        }
                    }
                }));
            });
        }
    }
    static class Program {
        [STAThread] static void Main(string[] args) {
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            string folder=args.Length==2 && args[0]=="--folder"?args[1]:null;
            Application.Run(new Window(folder));
        }
    }
}
