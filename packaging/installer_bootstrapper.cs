using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("Gestor de documental - Instalador")]
[assembly: AssemblyDescription("Instalador de Gestor de documental para Windows")]
[assembly: AssemblyCompany("Gestor de documental")]
[assembly: AssemblyProduct("Gestor de documental")]
[assembly: AssemblyVersion("@@ASSEMBLY_VERSION@@")]
[assembly: AssemblyFileVersion("@@ASSEMBLY_VERSION@@")]

internal static class GestorInstaller
{
    private const string ProductName = "Gestor de documental";
    private const string Magic = "GESTORDOCSFX010!";

    [STAThread]
    private static int Main(string[] args)
    {
        bool silent = false;
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
            var answer = MessageBox.Show(
                "Se instalará Gestor de documental @@VERSION@@ para este usuario.\n\n" +
                "La actualización conserva casos, configuración y modelos personalizados. " +
                "No requiere permisos de administrador y aparecerá en Aplicaciones instaladas.",
                ProductName,
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question,
                MessageBoxDefaultButton.Button1
            );
            if (answer != DialogResult.Yes)
                return 0;
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
                process.WaitForExit();
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
