using System.Diagnostics;
using System.Net.Http;
using System.Windows;
using System.Windows.Threading;

namespace IntraShop.ServerManager;

public partial class MainWindow : Window
{
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(2) };
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(4) };
    private Process? _ownedProcess;
    private int _port = 8000;

    public MainWindow()
    {
        InitializeComponent();
        BackendPathInput.Text = System.IO.Path.Combine(AppContext.BaseDirectory, "backend", "pos_server.exe");
        _timer.Tick += async (_, _) => await RefreshStatusAsync();
        _timer.Start();
        Loaded += async (_, _) => await RefreshStatusAsync();
        Closed += (_, _) => { _timer.Stop(); _http.Dispose(); };
    }

    private bool ReadPort()
    {
        if (!int.TryParse(PortInput.Text, out var port) || port < 1 || port > 65535)
        {
            MessageText.Text = "Ingresá un puerto válido entre 1 y 65535.";
            return false;
        }
        _port = port;
        return true;
    }

    private async Task<bool> IsHealthyAsync()
    {
        try
        {
            using var response = await _http.GetAsync($"http://127.0.0.1:{_port}/health");
            if (!response.IsSuccessStatusCode) return false;
            var body = await response.Content.ReadAsStringAsync();
            return body.Contains("pos-lan", StringComparison.OrdinalIgnoreCase);
        }
        catch (HttpRequestException) { return false; }
        catch (TaskCanceledException) { return false; }
    }

    private async Task RefreshStatusAsync()
    {
        if (!ReadPort()) return;
        var healthy = await IsHealthyAsync();
        StatusText.Text = healthy ? $"Activo · http://127.0.0.1:{_port}" : "Detenido o inaccesible";
        StartButton.IsEnabled = !healthy && (_ownedProcess is null || _ownedProcess.HasExited);
        StopButton.IsEnabled = _ownedProcess is { HasExited: false };
        if (_ownedProcess is { HasExited: true }) { _ownedProcess.Dispose(); _ownedProcess = null; }
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (!ReadPort() || await IsHealthyAsync()) return;
        if (_ownedProcess is { HasExited: false }) return;
        var backend = BackendPathInput.Text.Trim();
        if (!System.IO.File.Exists(backend))
        {
            MessageText.Text = "No se encontró el backend: " + backend;
            return;
        }
        try
        {
            var isPython = System.IO.Path.GetFileNameWithoutExtension(backend).StartsWith("python", StringComparison.OrdinalIgnoreCase);
            var workdir = isPython
                ? System.IO.Path.GetFullPath(System.IO.Path.Combine(AppContext.BaseDirectory, "..", "..", "..", ".."))
                : System.IO.Path.GetDirectoryName(backend)!;
            var info = new ProcessStartInfo(backend)
            {
                WorkingDirectory = workdir,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            if (isPython) info.ArgumentList.Add("pos_server.py");
            info.ArgumentList.Add("--headless");
            info.ArgumentList.Add("--port");
            info.ArgumentList.Add(_port.ToString());
            _ownedProcess = Process.Start(info) ?? throw new InvalidOperationException("No se inició el backend.");
            MessageText.Text = "Servidor iniciado. Esperando respuesta HTTP…";
            await Task.Delay(1200);
            await RefreshStatusAsync();
        }
        catch (Exception ex) { MessageText.Text = "Error al iniciar: " + ex.Message; }
    }

    private async void Stop_Click(object sender, RoutedEventArgs e)
    {
        if (_ownedProcess is not { HasExited: false } process) return;
        if (MessageBox.Show("¿Detener el servidor? Los tótems conectados perderán acceso.", "Confirmar", MessageBoxButton.YesNo, MessageBoxImage.Warning) != MessageBoxResult.Yes) return;
        try
        {
            // Prototipo: solo detiene procesos que lanzó este administrador.
            process.Kill(entireProcessTree: true);
            await process.WaitForExitAsync();
            MessageText.Text = "Servidor detenido.";
        }
        catch (Exception ex) { MessageText.Text = "Error al detener: " + ex.Message; }
        await RefreshStatusAsync();
    }

    private void OpenShop_Click(object sender, RoutedEventArgs e)
    {
        if (!ReadPort()) return;
        Process.Start(new ProcessStartInfo($"http://127.0.0.1:{_port}/intrashop/") { UseShellExecute = true });
    }
}
