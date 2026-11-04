using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;

namespace IntraShop.ServerManager;

public partial class MercadoPagoWindow : Window
{
    private readonly HttpClient _http = new() { Timeout = TimeSpan.FromSeconds(20) };
    private readonly string _baseUrl;
    private string? _token;

    public MercadoPagoWindow(int port)
    {
        InitializeComponent();
        _baseUrl = $"http://127.0.0.1:{port}";
        Closed += (_, _) => _http.Dispose();
        BindingsGrid.SelectionChanged += (_, _) =>
        {
            if (BindingsGrid.SelectedItem is not BindingRow row) return;
            TerminalInput.Text = row.terminal_id;
            TypeInput.SelectedIndex = row.terminal_type == "caja" ? 1 : 0;
            NameInput.Text = row.nombre;
            PosInput.Text = row.pos_external_id;
            StoreInput.Text = row.store_external_id;
            QrInput.Text = row.qr_url;
        };
    }

    private sealed class BindingRow
    {
        public string terminal_id { get; set; } = "";
        public string terminal_type { get; set; } = "";
        public string nombre { get; set; } = "";
        public string pos_external_id { get; set; } = "";
        public string store_external_id { get; set; } = "";
        public string qr_url { get; set; } = "";
    }

    private async Task<JsonElement> RequestAsync(HttpMethod method, string path, object? body = null)
    {
        using var request = new HttpRequestMessage(method, _baseUrl + path);
        if (_token is not null)
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _token);
        if (body is not null) request.Content = JsonContent.Create(body);
        using var response = await _http.SendAsync(request);
        var content = await response.Content.ReadAsStringAsync();
        if (!response.IsSuccessStatusCode)
            throw new InvalidOperationException($"HTTP {(int)response.StatusCode}: {content}");
        using var document = JsonDocument.Parse(content);
        return document.RootElement.Clone();
    }

    private async void Login_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            var result = await RequestAsync(HttpMethod.Post, "/pos/auth/login",
                new { usuario = UserInput.Text.Trim(), clave = PasswordInput.Password });
            _token = result.GetProperty("access_token").GetString();
            PasswordInput.Clear();
            await RefreshAsync();
        }
        catch (Exception ex) { StatusText.Text = ex.Message; }
    }

    private async Task RefreshAsync()
    {
        if (string.IsNullOrEmpty(_token))
        {
            StatusText.Text = "Iniciá sesión primero.";
            return;
        }
        var bindings = await RequestAsync(HttpMethod.Get, "/tienda/admin/mp-bindings");
        BindingsGrid.ItemsSource = JsonSerializer.Deserialize<BindingRow[]>(bindings.GetRawText());
        try
        {
            var pos = await RequestAsync(HttpMethod.Get, "/tienda/admin/mp-oauth/pos");
            PosGrid.ItemsSource = pos.GetProperty("results").EnumerateArray()
                .Select(x => new { Nombre = x.TryGetProperty("name", out var n) ? n.ToString() : "",
                    Id = x.TryGetProperty("external_id", out var id) ? id.ToString() : "",
                    Tienda = x.TryGetProperty("external_store_id", out var st) ? st.ToString() : "" }).ToArray();
            StatusText.Text = "Asignaciones y POS actualizados.";
        }
        catch (Exception ex) { StatusText.Text = "Asignaciones cargadas. Consulta de POS: " + ex.Message; }
    }

    private async void Refresh_Click(object sender, RoutedEventArgs e)
    {
        try { await RefreshAsync(); }
        catch (Exception ex) { StatusText.Text = ex.Message; }
    }

    private async void SaveBinding_Click(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrEmpty(_token)) { StatusText.Text = "Iniciá sesión primero."; return; }
        var type = ((ComboBoxItem)TypeInput.SelectedItem).Content.ToString()!;
        try
        {
            await RequestAsync(HttpMethod.Put, "/tienda/admin/mp-bindings", new
            {
                terminal_id = TerminalInput.Text.Trim(),
                terminal_type = type,
                nombre = NameInput.Text.Trim(),
                pos_external_id = PosInput.Text.Trim(),
                store_external_id = StoreInput.Text.Trim(),
                qr_url = QrInput.Text.Trim()
            });
            await RefreshAsync();
            StatusText.Text = "Asignación guardada.";
        }
        catch (Exception ex) { StatusText.Text = ex.Message; }
    }
}
