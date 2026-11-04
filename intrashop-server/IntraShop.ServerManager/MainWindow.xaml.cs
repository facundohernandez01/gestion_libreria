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

    private async Task<bool> IsShopAvailableAsync()
    {
        try
        {
            using var response = await _http.GetAsync($"http://127.0.0.1:{_port}/intrashop/");
            if (!response.IsSuccessStatusCode) return false;
            var type = response.Content.Headers.ContentType?.MediaType;
            return type is not null && type.Contains("html", StringComparison.OrdinalIgnoreCase);
        }
        catch (HttpRequestException) { return false; }
        catch (TaskCanceledException) { return false; }
    }

    private async Task RefreshStatusAsync()
    {
        if (!ReadPort()) return;
        var healthy = await IsHealthyAsync();
        if (healthy)
        {
            var shop = await IsShopAvailableAsync();
            StatusText.Text = shop
                ? $"API y tienda activas · http://127.0.0.1:{_port}/intrashop/"
                : "API activa, pero tienda Astro no disponible (404 o error).";
            MessageText.Text = shop ? "Servidor listo." : "Reconstruí la distribución con build-release.ps1 para incluir Astro.";
        }
        else StatusText.Text = "Detenido o inaccesible";
        StartButton.IsEnabled = !healthy && (_ownedProcess is null || _ownedProcess.HasExited);
        StopButton.IsEnabled = _ownedProcess is { HasExited: false };
        if (_ownedProcess is { HasExited: true }) { _ownedProcess.Dispose(); _ownedProcess = null; }
    }

    private static string FindRepoRoot()
    {
        var current = new System.IO.DirectoryInfo(AppContext.BaseDirectory);
        while (current is not null)
        {
            if (System.IO.File.Exists(System.IO.Path.Combine(current.FullName, "pos_server.py")))
                return current.FullName;
            current = current.Parent;
        }
        throw new System.IO.DirectoryNotFoundException(
            "No se encontró pos_server.py. Ejecutá el administrador dentro del repositorio o usá el backend empaquetado.");
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
            var workdir = isPython ? FindRepoRoot() : System.IO.Path.GetDirectoryName(backend)!;
            var info = new ProcessStartInfo(backend)
            {
                WorkingDirectory = workdir,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            if (!isPython)
            {
                var persistentDirectory = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
                    "Kiosmico", "IntraShop");
                var persistentDb = System.IO.Path.Combine(persistentDirectory, "libreria.db");
                if (System.IO.File.Exists(persistentDb))
                {
                    // No migrar ni crear una DB en forma implícita.
                    info.Environment["DB_PATH"] = persistentDb;
                }
            }
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
