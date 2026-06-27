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

def capture_screen(description=""):
    """
    Captura a tela e salva em cerebro/cortex/parietal/inbox/visual/.
    Usa powershell.exe se estiver em WSL, mss como primário nativo e scrot como fallback.
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
                # Captura todos os monitores em uma imagem ou apenas o monitor 1
                # sct.shot salva o monitor 1 por padrão
                sct.shot(output=str(filepath))
                if filepath.exists():
                    success = True
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
        desc = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
        path = capture_screen(desc)
        print(path)
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
