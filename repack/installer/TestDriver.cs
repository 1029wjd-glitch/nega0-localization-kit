using System;
namespace NegaPatch {
    class TestDriver {
        static int Main(string[] args) {
            try {
                var engine=new Engine(args[1],args[2]); engine.Progress=Console.WriteLine;
                if(args[0]=="stop") engine.AfterReplace=i=>{if(i==0) Environment.Exit(99);};
                bool cancel=false;
                if(args[0]=="cancel") { engine.Progress=message=>{Console.WriteLine(message); if(message.StartsWith("준비 중:")) cancel=true;}; engine.CancelRequested=()=>cancel; }
                if(args[0]=="cancel_restore") engine.CancelRequested=()=>true;
                if(args[0]=="restore"||args[0]=="cancel_restore") engine.Restore(); else engine.Apply();
                return 0;
            } catch(OperationCanceledException e) { Console.WriteLine(e.Message); return 2; }
            catch(Exception e) { Console.WriteLine(e.GetType().Name+": "+e.Message); return 1; }
        }
    }
}
