"""Gera vídeo de teste AUTORIZADO (sintético): fala PT-BR via espeak-ng + vídeo testsrc2 16:9.

Uso: python scripts/make_test_video.py saida.mp4
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

PARTS = [
    "Fala galera, sejam bem-vindos ao canal. Hoje eu trouxe três assuntos rápidos.",
    "Você sabia que o maior erro de quem começa a investir é não ter uma reserva de emergência? "
    "Muita gente coloca todo o dinheiro em ações e, quando aparece uma conta inesperada, precisa vender no prejuízo. "
    "A reserva protege você do pânico. O ideal é guardar de seis a doze meses do seu custo de vida "
    "em uma aplicação segura e com liquidez diária. Então a lição é simples: primeiro a reserva, depois o risco.",
    "Por que você não consegue terminar o que começa? O problema quase nunca é preguiça. "
    "É excesso de tarefas abertas ao mesmo tempo. O cérebro paga um custo enorme cada vez que troca de contexto. "
    "Escolha uma única tarefa importante por manhã e proteja esse horário como se fosse uma reunião. "
    "Resultado: você termina mais coisas trabalhando menos horas!",
    "Qual é o segredo para dormir melhor? Não é remédio, é luz. "
    "A luz forte da manhã regula o seu relógio biológico e a tela do celular à noite atrasa o sono. "
    "Tome sol nos primeiros trinta minutos do dia e desligue as telas uma hora antes de deitar. "
    "Parece simples demais, mas funciona de verdade.",
    "Se inscreva no canal e deixa o like. Até a próxima!",
]


def main(out: Path) -> Path:
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        listing = []
        for k, text in enumerate(PARTS):
            wav = tdp / f"p{k}.wav"
            subprocess.run(["espeak-ng", "-v", "pt-br", "-s", "150", "-w", str(wav), text], check=True)
            listing.append(f"file '{wav.as_posix()}'")
            sil = tdp / f"s{k}.wav"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono", "-t", "1.2",
                            str(sil)], check=True)
            listing.append(f"file '{sil.as_posix()}'")
        (tdp / "list.txt").write_text("\n".join(listing))
        audio = tdp / "voice.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(tdp / "list.txt"),
                        "-ar", "44100", str(audio)], check=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
                        "-i", str(audio), "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", str(out)], check=True)
    return out


if __name__ == "__main__":
    print(main(Path(sys.argv[1] if len(sys.argv) > 1 else "test_video.mp4")))
