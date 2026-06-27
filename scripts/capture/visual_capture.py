#!/usr/bin/env python3
import mss
import datetime
import os
import sys
import subprocess
from pathlib import Path

def is_wsl():
    """Detecta se está rodando dentro do Windows Subsystem for Linux (WSL)."""
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False

def capture_screen(description="", monitor=None):
    """
    Captura a tela e salva em cerebro/cortex/parietal/inbox/visual/.
    Usa powershell.exe se estiver em WSL, mss como primário nativo e scrot como fallback.

    Em setups multi-monitor (mais de um monitor real), ``monitor`` é obrigatório:
    informe o índice mss (1 = primário, 2 = segundo, ...). Sem ele, levanta erro
    explicativo em vez de capturar o monitor errado silenciosamente.
    """
    # Configuração de caminhos (anatômico: cortex/parietal/inbox/visual)
    project_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(project_root))
    from core import paths as cp
    output_dir = cp.INBOX_VISUAL
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    
    # Limpa a descrição para ser usada em nome de arquivo
    if description:
        safe_desc = "".join([c if c.isalnum() else "-" for c in description]).strip("-")
        # Remove hifens duplicados
        while "--" in safe_desc:
            safe_desc = safe_desc.replace("--", "-")
        filename = f"CAP-{timestamp}-{safe_desc}.png"
    else:
        filename = f"CAP-{timestamp}.png"
        
    filepath = output_dir / filename
    
    success = False
    error_log = []

    # 0. Se estiver no WSL, tenta capturar a tela do host Windows via powershell.exe
    if is_wsl():
        try:
            # Converte o caminho do WSL para o caminho do Windows
            try:
                win_path = subprocess.check_output(["wslpath", "-w", str(filepath)], text=True).strip()
            except Exception:
                # Fallback manual de conversão (/mnt/c/... -> C:\...)
                p = str(filepath.resolve())
                if p.startswith("/mnt/"):
                    drive = p[5].upper()
                    win_path = f"{drive}:{p[6:].replace('/', '\\')}"
                else:
                    win_path = p

            # Comando PowerShell para tirar screenshot sem clipboard
            ps_cmd = (
                f"Add-Type -AssemblyName System.Drawing; "
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                f"$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height; "
                f"$graphics = [System.Drawing.Graphics]::FromImage($bmp); "
                f"$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size); "
                f"$bmp.Save('{win_path}'); "
                f"$graphics.Dispose(); $bmp.Dispose();"
            )
            # Executa o powershell.exe do host
            subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], check=True, capture_output=True)
            if filepath.exists():
                success = True
        except Exception as e:
            error_log.append(f"WSL powershell screen capture error: {e}")

    # 1. Tentativa com mss (se não obteve sucesso ou não é WSL)
    if not success:
        try:
            with mss.mss() as sct:
                # sct.monitors[0] é o "monitor virtual" (todos juntos); os reais
                # começam no índice 1. >1 real = setup multi-monitor.
                real_count = max(len(sct.monitors) - 1, 0)
                if monitor is None and real_count > 1:
                    raise ValueError(
                        f"Setup multi-monitor detectado ({real_count} monitores). "
                        f"Informe monitor=N (1..{real_count}) para escolher qual capturar."
                    )
                mon_index = monitor if monitor is not None else 1
                sct.shot(mon=mon_index, output=str(filepath))
                if filepath.exists():
                    success = True
        except ValueError:
            # Guarda multi-monitor deve propagar (não virar "failed to capture").
            raise
        except Exception as e:
            error_log.append(f"mss error: {e}")

    # 2. Fallback com scrot
    if not success:
        try:
            # -z para modo silencioso (no beep)
            subprocess.run(["scrot", "-z", str(filepath)], check=True, capture_output=True)
            if filepath.exists():
                success = True
        except Exception as e:
            error_log.append(f"scrot error: {e}")

    if success:
        return str(filepath.resolve())
    else:
        raise Exception(f"Failed to capture screen. Logs: {'; '.join(error_log)}")

if __name__ == "__main__":
    try:
        args = sys.argv[1:]
        monitor = None
        if "--monitor" in args:
            i = args.index("--monitor")
            try:
                monitor = int(args[i + 1])
                del args[i:i + 2]
            except (IndexError, ValueError):
                del args[i:i + 1]
        desc = " ".join(args)
        path = capture_screen(desc, monitor=monitor)
        print(path)
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
