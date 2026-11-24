"""
Testes do editor de cortes: tempos, legenda .srt do trecho e origem da legenda.

Uso (dentro de src/):   python tests/test_cortes.py
"""

import json
import sys
import tempfile
import types
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))

import fake_streamlit                                              # noqa: E402

fake_streamlit.instalar()

from admin import cortes                                           # noqa: E402
from ingestao import legenda_srt as L                              # noqa: E402
from ingestao.chunking import chunkar_transcricao                  # noqa: E402
from test_ingestao import FakeQdrant                               # noqa: E402


def seg(texto, inicio, duracao=3.0):
    return {"text": texto, "start": inicio, "duration": duracao}


def pasta():
    return Path(tempfile.mkdtemp())


# ============================================================

def teste_tempos():

    assert L.tempo_srt(0) == "00:00:00,000" and L.tempo_srt(3725.5) == "01:02:05,500"
    assert L.tempo_srt(59.9996) == "00:01:00,000"
    assert L.formatar_tempo(90.5) == "1:30.5" and L.formatar_tempo(3725) == "1:02:05.0"

    assert L.interpretar_tempo("1:02:03.5") == 3723.5
    assert L.interpretar_tempo("12:03") == 723 and L.interpretar_tempo("90,5") == 90.5

    for ruim in ("", "abc", "1:2:3:4", "-5", "1:75x"):
        try:
            L.interpretar_tempo(ruim)
            assert False, ruim
        except ValueError:
            pass


def teste_srt_do_trecho_corta_nas_bordas_e_desloca():

    segs = [seg("antes", 0, 4), seg("começa antes do corte", 8, 4), seg("no meio", 12, 3),
            seg("termina depois", 18, 5), seg("depois", 30, 3)]

    srt = L.montar_srt(segs, 10, 20, deslocar=True)

    assert srt == (
        "1\n00:00:00,000 --> 00:00:02,000\ncomeça antes do corte\n\n"
        "2\n00:00:02,000 --> 00:00:05,000\nno meio\n\n"
        "3\n00:00:08,000 --> 00:00:10,000\ntermina depois\n"
    ), srt

    original = L.montar_srt(segs, 10, 20, deslocar=False)
    assert "00:00:10,000 --> 00:00:12,000" in original and "00:00:18,000 --> 00:00:20,000" in original

    assert L.montar_srt(segs, 100, 120) == ""


def teste_srt_trata_sobreposicao_e_duracao_ausente():

    # legenda automática: a fala 1 dura até 10 s, mas a 2 começa em 6 s
    segs = [seg("um", 0, 10), seg("dois", 6, 4), {"text": "  três\n quatro ", "start": 10}]

    falas = L.falas_do_trecho(segs, 0, 30)

    assert falas[0] == (0.0, 6.0, "um")                       # termina quando a próxima começa
    assert falas[1] == (6.0, 10.0, "dois")
    assert falas[2][2] == "três quatro" and falas[2][1] == 12.0   # sem duração: +2 s


def teste_reconstrucao_aproximada_a_partir_dos_trechos():

    palavras = [f"p{i}" for i in range(1, 1001)]
    # 2 palavras por segundo, em falas de 10 palavras
    segs = [seg(" ".join(palavras[i:i + 10]), i / 2, 5.0) for i in range(0, 1000, 10)]

    chunks = chunkar_transcricao(segs)
    assert len(chunks) > 3

    payloads = [
        {"chunk_index": c["indice"], "texto_bruto": c["texto"],
         "timestamp_segundos": c["inicio_s"], "timestamp_fim_segundos": c["fim_s"]}
        for c in reversed(chunks)                              # fora de ordem de propósito
    ]

    aprox = L.segmentos_aproximados(payloads)

    # sem palavra repetida nem faltando: a sobreposição foi descartada
    assert " ".join(s["text"] for s in aprox).split() == palavras

    # tempos coerentes: a linha que começa em pN deve estar perto de N/2 segundos
    for s in aprox[::7]:
        primeira = int(s["text"].split()[0][1:]) - 1
        assert abs(s["start"] - primeira / 2) < 3.0, (s, primeira / 2)

    assert [s["start"] for s in aprox] == sorted(s["start"] for s in aprox)


def _acervo(origem, n=400, nome="ac"):
    """FakeQdrant com um vídeo V0000000001 de n palavras e a origem dada."""

    palavras = [f"w{i}" for i in range(n)]
    segs = [seg(" ".join(palavras[i:i + 10]), i / 2, 5.0) for i in range(0, n, 10)]

    q = FakeQdrant()
    q.colecoes[nome] = {"dim": 8, "pontos": {}}

    for c in chunkar_transcricao(segs):
        q.colecoes[nome]["pontos"][c["indice"]] = ([0] * 8, {
            "doc_id": "V0000000001", "video_id": "V0000000001", "chunk_index": c["indice"],
            "origem_transcricao": origem, "texto_bruto": c["texto"],
            "timestamp_segundos": c["inicio_s"], "timestamp_fim_segundos": c["fim_s"],
        })

    return q, segs


def teste_origem_da_legenda_em_ordem_de_preferencia():

    cache, trans = pasta(), pasta()
    chamadas = []

    def youtube(video_id, traduzir_de):
        chamadas.append((video_id, traduzir_de))
        return [seg("do youtube", 0)]

    # 1) legenda do YouTube: busca, guarda cópia e depois usa a cópia (sem nova chamada)
    q, _ = _acervo("youtube")
    s, fonte = cortes.segmentos_do_video("V0000000001", "ac", q, youtube, cache, trans)
    assert fonte == "youtube" and s[0]["text"] == "do youtube" and chamadas == [("V0000000001", None)]

    s, fonte = cortes.segmentos_do_video("V0000000001", "ac", q, youtube, cache, trans)
    assert fonte == "cache" and len(chamadas) == 1

    # 2) vídeo traduzido: pede a legenda no idioma de origem
    cache = pasta()
    q, _ = _acervo("youtube:traduzido(en→pt)")
    cortes.segmentos_do_video("V0000000001", "ac", q, youtube, cache, trans)
    assert chamadas[-1][1] == ["en"]

    # 3) Whisper: usa a transcrição guardada, sem ir ao YouTube
    cache = pasta()
    q, _ = _acervo("whisper:medium")
    (trans / "V0000000001.json").write_text(json.dumps({"transcript": [seg("do whisper", 1)]}), encoding="utf-8")
    antes = len(chamadas)
    s, fonte = cortes.segmentos_do_video("V0000000001", "ac", q, youtube, cache, trans)
    assert fonte == "whisper" and s[0]["text"] == "do whisper" and len(chamadas) == antes

    # 4) YouTube falha (bloqueio): cai na reconstrução aproximada
    def bloqueado(video_id, traduzir_de):
        raise RuntimeError("IP bloqueado")

    cache = pasta()
    q, _ = _acervo("youtube")
    s, fonte = cortes.segmentos_do_video("V0000000001", "ac", q, bloqueado, cache, trans)
    assert fonte == "aproximada" and len(s) > 10
    assert not (cache / "V0000000001.json").exists()          # o que é aproximado não vira cópia

    # 5) áudio sem Whisper guardado nem YouTube (transcrição importada): também reconstrói
    q, _ = _acervo("arquivo")
    s, fonte = cortes.segmentos_do_video("V0000000001", "ac", q, bloqueado, pasta(), pasta())
    assert fonte == "aproximada"


def teste_video_fora_do_acervo():

    chamadas = []

    def youtube(video_id, traduzir_de):
        chamadas.append(traduzir_de)
        return [seg("x", 0)]

    s, fonte = cortes.segmentos_do_video("ZZZZZZZZZZZ", None, None, youtube, pasta(), pasta())
    assert fonte == "youtube" and chamadas == [["en", "es"]]     # aceita legendas traduzidas

    def nada(video_id, traduzir_de):
        raise RuntimeError("sem legenda")

    try:
        cortes.segmentos_do_video("ZZZZZZZZZZZ", None, None, nada, pasta(), pasta())
        assert False
    except cortes.SemLegenda:
        pass


def teste_nomes_e_lista_de_cortes():

    assert cortes.nome_do_arquivo("Geopolítica: o Brasil & a China!", "abcDEF12345", 3725, 3790) == \
        "geopolitica-o-brasil-a-china_abcDEF12345_01h02m05s-01h03m10s"
    assert cortes.nome_do_arquivo(None, "abcDEF12345", 0, 5) == "abcDEF12345_00h00m00s-00h00m05s"
    assert len(cortes.nome_do_arquivo("a" * 300, "abcDEF12345", 0, 5)) < 100

    d = pasta()
    (d / "a.mp4").write_bytes(b"1234")
    (d / "a.srt").write_text("x")
    (d / "b.mp4").write_bytes(b"12")
    (d / "lixo.txt").write_text("x")
    (d / "a.mp4.part").write_bytes(b"x")

    itens = cortes.listar_cortes(d)
    assert sorted(i["nome"] for i in itens) == ["a", "b"]
    assert {i["nome"]: bool(i["legenda"]) for i in itens} == {"a": True, "b": False}

    cortes.remover_corte("a", d)
    assert not (d / "a.mp4").exists() and not (d / "a.srt").exists() and (d / "b.mp4").exists()

    try:
        cortes.remover_corte("../fora", d)
        assert False
    except ValueError:
        pass


def teste_seletor_de_formato_do_yt_dlp():

    from ingestao import youtube

    assert youtube.formato_para(None) == "bv*+ba/b"
    assert youtube.formato_para(720).startswith("bv*[height<=720]+ba/b[height<=720]")


# ============================================================

if __name__ == "__main__":

    testes = [(n, f) for n, f in sorted(globals().items()) if n.startswith("teste_")]
    falhas = 0

    for nome, func in testes:
        try:
            func()
            print(f"  ok  {nome}")
        except Exception as e:
            import traceback
            falhas += 1
            print(f"FALHOU {nome}: {type(e).__name__}: {e}")
            traceback.print_exc()

    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    sys.exit(1 if falhas else 0)
