import json
import re
import sys
from pathlib import Path

from yt_dlp import YoutubeDL


# -------------------------------------------------------
# CONFIGURAÇÕES
# -------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/138.0 Safari/537.36"
    )
}


# -------------------------------------------------------
# UTILIDADES
# -------------------------------------------------------

def srt_time_to_seconds(timestamp: str) -> float:

    hora, minuto, resto = timestamp.split(":")
    segundo, milesimo = resto.split(",")

    return (
        int(hora) * 3600
        + int(minuto) * 60
        + int(segundo)
        + int(milesimo) / 1000
    )


def obter_titulo(video_id):

    url = f"https://www.youtube.com/watch?v={video_id}"

    try:

        with YoutubeDL({"quiet": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title")

    except Exception:
        return None


# -------------------------------------------------------
# PARSER SRT
# -------------------------------------------------------

def parse_srt(srt_file: Path):

    with open(
        srt_file,
        encoding="utf-8-sig"
    ) as f:

        content = f.read().strip()

    blocks = re.split(r"\n\s*\n", content)

    transcript = []

    for block in blocks:

        lines = block.splitlines()

        if len(lines) < 3:
            continue

        tempo = lines[1]

        m = re.match(
            r"(.+?)\s*-->\s*(.+)",
            tempo
        )

        if not m:
            continue

        start = srt_time_to_seconds(m.group(1))
        end = srt_time_to_seconds(m.group(2))

        texto = " ".join(
            l.strip()
            for l in lines[2:]
        )

        transcript.append(
            {
                "text": texto,
                "start": round(start, 3),
                "duration": round(end - start, 3),
            }
        )

    return transcript


# -------------------------------------------------------
# CONVERSÃO
# -------------------------------------------------------

def converter(srt_path: Path):

    video_id = srt_path.stem

    print(f"\nConvertendo: {video_id}")

    titulo = obter_titulo(video_id)

    if titulo:
        print(f"Título: {titulo}")
    else:
        print("Título: não encontrado")

    dados = {

        "video_id": video_id,
        "titulo": titulo,
        "data_publicacao": None,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "transcript": parse_srt(srt_path)

    }

    destino = srt_path.with_suffix(".json")

    with open(
        destino,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            dados,
            f,
            ensure_ascii=False,
            indent=4
        )

    print(f"✔ Salvo em {destino.name}")



# -------------------------------------------------------
# MAIN
# -------------------------------------------------------


def main():

    if len(sys.argv) != 2:
        print("Uso:")
        print("    python str_to_json.py <arquivo.srt ou diretório>")
        return

    caminho = Path(sys.argv[1])

    if not caminho.exists():
        print(f"Não encontrado: {caminho}")
        return

    if caminho.is_file():

        if caminho.suffix.lower() != ".srt":
            print("O arquivo deve ser .srt")
            return

        arquivos = [caminho]

    else:

        arquivos = sorted(caminho.glob("*.srt"))

    print(f"{len(arquivos)} arquivo(s) encontrado(s)\n")

    for i, arquivo in enumerate(arquivos, start=1):

        print(f"[{i}/{len(arquivos)}] {arquivo.name}")

        try:
            converter(arquivo)
        except Exception as e:
            print(e)

    print("\nConcluído.")

if __name__ == "__main__":
    main()