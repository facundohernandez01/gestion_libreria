using System;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;

namespace IntraShop.ServerManager;

public partial class App : Application
{
    private Mutex? _mutex;
    private EventWaitHandle? _showSignal;
    private MainWindow? _window;

    private void Application_Startup(object sender, StartupEventArgs e)
    {
        const string mutexName = @"Local\IntraShop.ServerManager.Singleton";
        _mutex = new Mutex(true, mutexName, out var first);
        if (!first)
        {
            try { using var signal = EventWaitHandle.OpenExisting(@"Local\IntraShop.ServerManager.Show"); signal.Set(); }
            catch (WaitHandleCannotBeOpenedException) { }
            Shutdown();
            return;
        }
        _showSignal = new EventWaitHandle(false, EventResetMode.AutoReset, @"Local\IntraShop.ServerManager.Show");
        _window = new MainWindow();
        MainWindow = _window;
        _window.Show();
        var signalRef = _showSignal;
        _ = Task.Run(() =>
        {
            while (true)
            {
                try { signalRef.WaitOne(); Dispatcher.BeginInvoke(() => _window?.RestoreFromTray()); }
                catch (ObjectDisposedException) { break; }
            }
        });
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _showSignal?.Dispose();
        _mutex?.Dispose();
        base.OnExit(e);
    }
}