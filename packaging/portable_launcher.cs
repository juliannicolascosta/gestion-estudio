using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("FORO portable")]
[assembly: AssemblyDescription("FORO en modo portable, sin instalacion")]
[assembly: AssemblyCompany("FORO")]
[assembly: AssemblyProduct("FORO")]
[assembly: AssemblyVersion("@@ASSEMBLY_VERSION@@")]
[assembly: AssemblyFileVersion("@@ASSEMBLY_VERSION@@")]

internal static class ForoPortable
{
    private const string ProductName = "FORO";

    [STAThread]
    private static int Main(string[] args)
    {
        string root = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        string python = Path.Combine(root, "runtime", "pythonw.exe");
        string app = Path.Combine(root, "app");
        string entry = Path.Combine(app, "run.py");
        string data = Path.Combine(root, "Datos");

        if (!File.Exists(python) || !File.Exists(entry))
        {
            MessageBox.Show(
                "La carpeta portable esta incompleta.\n\n" +
                "Descomprimi el ZIP entero antes de abrir " + ProductName + ": " +
                "el programa necesita las carpetas runtime y app junto a este archivo.",
                ProductName,
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return 1;
        }

        try
        {
            Directory.CreateDirectory(data);
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "No se pudo preparar la carpeta de datos junto al programa.\n\n" +
                "Copia " + ProductName + " a una carpeta con permisos de escritura, " +
                "por ejemplo el Escritorio.\n\nDetalle: " + error.Message,
                ProductName,
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return 1;
        }

        var start = new ProcessStartInfo(python);
        start.Arguments = "\"" + entry + "\"";
        foreach (string arg in args)
        {
            start.Arguments += " \"" + arg + "\"";
        }
        start.WorkingDirectory = app;
        start.UseShellExecute = false;
        // Configuracion, modelos, cache y registro viajan con el programa.
        start.EnvironmentVariables["FORO_DATA_DIR"] = data;
        start.EnvironmentVariables["PYTHONPATH"] = app;
        start.EnvironmentVariables["PYTHONHOME"] = Path.Combine(root, "runtime");

        try
        {
            Process process = Process.Start(start);
            return process == null ? 1 : 0;
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "No se pudo iniciar " + ProductName + ".\n\nDetalle: " + error.Message,
                ProductName,
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
    }
}
