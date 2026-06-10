#!/usr/bin/env python3
import mss
import datetime
import os
import sys
import subprocess
from pathlib import Path

def capture_screen(description=""):
    """
    Captura a tela e salva em cerebro/inbox/visual/.
    Usa mss como primário e scrot como fallback.
    """
    # Configuração de caminhos
    project_root = Path(__file__).resolve().parent.parent
    output_dir = project_root / "cerebro" / "inbox" / "visual"
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

    # 1. Tentativa com mss
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
