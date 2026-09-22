using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("FORO - Instalador")]
[assembly: AssemblyDescription("Instalador de FORO para Windows")]
[assembly: AssemblyCompany("FORO")]
[assembly: AssemblyProduct("FORO")]
[assembly: AssemblyVersion("@@ASSEMBLY_VERSION@@")]
[assembly: AssemblyFileVersion("@@ASSEMBLY_VERSION@@")]

internal static class GestorInstaller
{
    private const string ProductName = "FORO";
    private const string Magic = "GESTORDOCSFX010!";

    [STAThread]
    private static int Main(string[] args)
    {
        bool silent = false;
        string installDirectory = "";
        InstallProgressForm progress = null;
        var forwarded = new List<string>();
        foreach (string arg in args)
        {
            if (string.Equals(arg, "/silent", StringComparison.OrdinalIgnoreCase))
                silent = true;
            else
                forwarded.Add(arg);
        }
        if (silent)
            forwarded.Add("-Quiet");

        if (!silent)
        {
            Application.EnableVisualStyles();
            string programs = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs"
            );
            string legacy = Path.Combine(programs, "Gestor de documental");
            string suggested = Directory.Exists(legacy) ? legacy : Path.Combine(programs, "FORO");
            using (var destination = new InstallDestinationForm(suggested))
            {
                if (destination.ShowDialog() != DialogResult.OK) return 0;
                installDirectory = destination.InstallDirectory;
            }
            forwarded.Add("-InstallDir");
            forwarded.Add(installDirectory);
            progress = new InstallProgressForm();
            progress.Show();
            progress.UpdateStep(5, "Preparando archivos…");
            Application.DoEvents();
        }

        string temporary = Path.Combine(
            Path.GetTempPath(),
            "GestorDocumentalInstalador-" + Guid.NewGuid().ToString("N")
        );

        try
        {
            Directory.CreateDirectory(temporary);
            string payload = Path.Combine(temporary, "payload.zip");
            string script = Path.Combine(temporary, "install.ps1");
            ExtractAttachedFiles(payload, script);
            if (progress != null) progress.UpdateStep(25, "Preparando archivos…");

            var command = new StringBuilder();
            command.Append("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ");
            command.Append(Quote(script));
            foreach (string arg in forwarded)
            {
                command.Append(' ');
                command.Append(Quote(arg));
            }

            var start = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = command.ToString(),
                WorkingDirectory = temporary,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            using (Process process = Process.Start(start))
            {
                if (progress != null) progress.UpdateStep(55, "Instalando FORO…");
                while (!process.WaitForExit(100)) Application.DoEvents();
                if (progress != null) progress.UpdateStep(90, "Creando accesos…");
                if (progress != null && process.ExitCode == 0)
                {
                    progress.UpdateStep(100, "Finalizando…");
                    MessageBox.Show(
                        progress,
                        "FORO se instaló correctamente.",
                        ProductName,
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );
                }
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "No pudimos iniciar la instalación.\n\n" + error.Message,
                ProductName,
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
            return 1;
        }
        finally
        {
            if (progress != null)
            {
                progress.UpdateStep(100, "Finalizando…");
                Application.DoEvents();
                progress.Close();
            }
            try { Directory.Delete(temporary, true); } catch { }
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static void ExtractAttachedFiles(string payloadPath, string scriptPath)
    {
        string executable = Assembly.GetExecutingAssembly().Location;
        byte[] expectedMagic = Encoding.ASCII.GetBytes(Magic);
        const int footerLength = 8 + 8 + 16;

        using (var source = new FileStream(executable, FileMode.Open, FileAccess.Read, FileShare.Read))
        using (var reader = new BinaryReader(source, Encoding.UTF8, true))
        {
            if (source.Length <= footerLength)
                throw new InvalidDataException("El instalador está incompleto.");

            source.Seek(-footerLength, SeekOrigin.End);
            long payloadLength = reader.ReadInt64();
            long scriptLength = reader.ReadInt64();
            byte[] actualMagic = reader.ReadBytes(expectedMagic.Length);
            if (Encoding.ASCII.GetString(actualMagic) != Magic || payloadLength <= 0 || scriptLength <= 0)
                throw new InvalidDataException("No pudimos validar el contenido del instalador.");

            long dataEnd = source.Length - footerLength;
            long payloadStart = dataEnd - scriptLength - payloadLength;
            if (payloadStart < 0)
                throw new InvalidDataException("El contenido del instalador está dañado.");

            source.Seek(payloadStart, SeekOrigin.Begin);
            CopyBytes(source, payloadPath, payloadLength);
            CopyBytes(source, scriptPath, scriptLength);
        }
    }

    private static void CopyBytes(Stream source, string destination, long length)
    {
        byte[] buffer = new byte[1024 * 1024];
        long remaining = length;
        using (var output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None))
        {
            while (remaining > 0)
            {
                int wanted = (int)Math.Min(buffer.Length, remaining);
                int read = source.Read(buffer, 0, wanted);
                if (read <= 0)
                    throw new EndOfStreamException("El instalador terminó antes de tiempo.");
                output.Write(buffer, 0, read);
                remaining -= read;
            }
        }
    }
}

internal sealed class InstallDestinationForm : Form
{
    private readonly TextBox path = new TextBox();
    public string InstallDirectory { get { return path.Text.Trim(); } }

    internal InstallDestinationForm(string suggested)
    {
        Text = "Instalar FORO";
        ClientSize = new System.Drawing.Size(590, 205);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new System.Drawing.Font("Segoe UI", 9F);
        var title = new Label { Text = "FORO", AutoSize = true, Font = new System.Drawing.Font("Segoe UI", 20F, System.Drawing.FontStyle.Bold), Location = new System.Drawing.Point(22, 16), ForeColor = System.Drawing.Color.FromArgb(43, 87, 72) };
        var version = new Label { Text = "Versión @@VERSION@@", AutoSize = true, Location = new System.Drawing.Point(122, 31), ForeColor = System.Drawing.Color.DimGray };
        var note = new Label { Text = "Elegí dónde instalar FORO. No requiere permisos de administrador.", AutoSize = true, Location = new System.Drawing.Point(24, 60) };
        path.Text = suggested;
        path.Location = new System.Drawing.Point(24, 91);
        path.Size = new System.Drawing.Size(430, 25);
        var browse = new Button { Text = "Examinar…", Location = new System.Drawing.Point(464, 89), Size = new System.Drawing.Size(100, 28) };
        browse.Click += delegate
        {
            using (var dialog = new FolderBrowserDialog { Description = "Elegí dónde instalar FORO", SelectedPath = path.Text })
                if (dialog.ShowDialog(this) == DialogResult.OK) path.Text = dialog.SelectedPath;
        };
        var install = new Button { Text = "Instalar", DialogResult = DialogResult.OK, Location = new System.Drawing.Point(376, 151), Size = new System.Drawing.Size(90, 30) };
        var cancel = new Button { Text = "Cancelar", DialogResult = DialogResult.Cancel, Location = new System.Drawing.Point(474, 151), Size = new System.Drawing.Size(90, 30) };
        AcceptButton = install;
        CancelButton = cancel;
        Controls.AddRange(new Control[] { title, version, note, path, browse, install, cancel });
    }
}

internal sealed class InstallProgressForm : Form
{
    private readonly Label status = new Label();
    private readonly ProgressBar bar = new ProgressBar();

    internal InstallProgressForm()
    {
        Text = "Instalando FORO";
        ClientSize = new System.Drawing.Size(500, 125);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        ControlBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        Font = new System.Drawing.Font("Segoe UI", 9F);
        status.AutoSize = true;
        status.Location = new System.Drawing.Point(22, 24);
        bar.Location = new System.Drawing.Point(24, 57);
        bar.Size = new System.Drawing.Size(452, 22);
        Controls.Add(status);
        Controls.Add(bar);
    }

    internal void UpdateStep(int value, string text)
    {
        bar.Value = Math.Max(0, Math.Min(100, value));
        status.Text = text;
        Refresh();
    }
}
