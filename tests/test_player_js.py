"""
Testa o player de corte (componentes/player_corte/index.html) num Chromium de verdade, com o player
do YouTube trocado por um de mentira. Precisa do Playwright; sem ele, o teste é pulado.

Uso (dentro de src/):   python tests/test_player_js.py [--imagens pasta]
"""

import sys
from pathlib import Path

HTML = Path(__file__).resolve().parents[1] / "componentes" / "player_corte" / "index.html"

YT_FALSO = """
window.__yt = {players: [], calls: []};
class Player {
  constructor(el, opts) {
    this.opts = opts; this.t = (opts.playerVars || {}).start || 0; this.state = -1; this.rate = 1; this.dur = 600;
    window.__yt.players.push(this);
    const f = document.createElement('div'); f.id = 'ytfalso';
    f.style.cssText = 'width:100%;height:100%;background:#234;color:#fff;display:flex;align-items:center;justify-content:center';
    f.textContent = '[player do YouTube de mentira]';
    document.getElementById(el).appendChild(f);
    setInterval(() => { if (this.state === 1) { this.t += 0.1 * this.rate; } }, 100);
    setTimeout(() => opts.events.onReady({target: this}), 50);
  }
  getCurrentTime() { return this.t; }  getDuration() { return this.dur; }
  seekTo(t) { this.t = t; window.__yt.calls.push(['seekTo', t]); }
  playVideo() { this.state = 1; this.opts.events.onStateChange({data: 1}); }
  pauseVideo() { this.state = 2; this.opts.events.onStateChange({data: 2}); }
  getPlayerState() { return this.state; }  setPlaybackRate(r) { this.rate = r; }  destroy() {}
}
window.YT = {Player};
setTimeout(() => window.onYouTubeIframeAPIReady && window.onYouTubeIframeAPIReady(), 0);
"""

COLETOR = "window.__msgs = []; addEventListener('message', e => { if (e.data && e.data.isStreamlitMessage) __msgs.push(e.data); });"


def main():

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("pulado: Playwright não está instalado")
        return 0

    imagens = Path(sys.argv[sys.argv.index("--imagens") + 1]) if "--imagens" in sys.argv else None
    falhas = []

    def conferir(condicao, texto):
        print(("  ok  " if condicao else "FALHOU ") + texto)
        if not condicao:
            falhas.append(texto)

    with sync_playwright() as pw:

        navegador = pw.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 760, "height": 900})
        erros = []
        pagina.on("pageerror", lambda e: erros.append(str(e)))
        pagina.route("https://www.youtube.com/iframe_api",
                     lambda r: r.fulfill(status=200, content_type="application/javascript", body=YT_FALSO))
        pagina.add_init_script(COLETOR)
        pagina.goto(HTML.as_uri())

        pagina.evaluate("""window.postMessage({type: 'streamlit:render', theme: {},
            args: {chave: 'k1', video_id: 'abcdefghijk', posicao: 120, duracao_inicial: 60}}, '*')""")
        pagina.wait_for_function("document.getElementById('tempo').textContent.includes('10:00.0')")

        valor = lambda i: pagina.input_value(i)
        def msgs():
            pagina.wait_for_timeout(80)          # postMessage entrega de forma assíncrona
            return pagina.evaluate("__msgs")

        ultimo = lambda: [m for m in msgs() if m["type"] == "streamlit:setComponentValue"][-1]["value"]
        jogador = lambda js: pagina.evaluate(f"__yt.players[0].{js}")

        tipos = [m["type"] for m in msgs()]
        conferir("streamlit:componentReady" in tipos and "streamlit:setFrameHeight" in tipos, "avisa o Streamlit que está pronto e a altura")
        conferir(valor("#t-ini") == "2:00.0" and valor("#t-fim") == "3:00.0", "marcadores iniciais: posição do trecho e +60 s")
        conferir(jogador("opts.playerVars.start") == 120, "o player abre posicionado no ponto exato (start=120)")

        largura = pagina.eval_on_selector("#reg", "e => e.style.width")
        conferir(abs(float(largura.rstrip('%')) - 10.0) < 0.01, f"faixa ocupa 10% da linha do tempo ({largura})")

        # --- tocar só o trecho: encurta para 3 s para o teste ser rápido ---
        pagina.fill("#t-fim", "2:03"); pagina.press("#t-fim", "Enter")
        conferir(valor("#t-fim") == "2:03.0" and ultimo()["fim"] == 123.0, "digitar o fim atualiza e avisa o Python (123.0)")
        pagina.click("#p-trecho")
        pagina.wait_for_function("__yt.players[0].state === 2", timeout=8000)
        conferir(abs(jogador("t") - 123.0) < 0.5, f"'Tocar o trecho' pausa no fim ({jogador('t'):.1f} s)")

        # --- marcar início/fim pela posição atual ---
        pagina.evaluate("__yt.players[0].t = 300")
        pagina.wait_for_timeout(250)
        pagina.click("#m-ini")
        v = ultimo()
        conferir(v["inicio"] == 300.0 and v["fim"] == 305.0, f"marcar início em 300 s empurra o fim para 305 ({v['inicio']}-{v['fim']})")
        pagina.evaluate("__yt.players[0].t = 360")
        pagina.wait_for_timeout(250)
        pagina.click("#m-fim")
        v = ultimo()
        conferir(v["inicio"] == 300.0 and v["fim"] == 360.0 and v["duracao_video"] == 600, "marcar fim em 360 s")

        # --- arrastar a alça do fim ---
        caixa = pagina.eval_on_selector("#bar", "e => { const r = e.getBoundingClientRect(); return [r.left, r.width, r.top + r.height / 2]; }")
        x = lambda t: caixa[0] + caixa[1] * t / 600
        alca = pagina.eval_on_selector("#hf", "e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }")
        pagina.mouse.move(*alca); pagina.mouse.down(); pagina.mouse.move(x(450), alca[1], steps=6); pagina.mouse.up()
        v = ultimo()
        tol = 600 / caixa[1] * 1.5
        conferir(abs(v["fim"] - 450) <= tol and v["inicio"] == 300.0, f"arrastar a alça do fim até ~450 s ({v['fim']})")
        conferir(abs(jogador("t") - v["fim"]) < 1, "o vídeo acompanha a alça (mostra o quadro do fim)")

        # --- arrastar a faixa inteira, mantendo o tamanho ---
        tamanho = v["fim"] - v["inicio"]
        meio = x((v["inicio"] + v["fim"]) / 2)
        pagina.mouse.move(meio, caixa[2]); pagina.mouse.down(); pagina.mouse.move(meio - 100, caixa[2], steps=6); pagina.mouse.up()
        w = ultimo()
        conferir(abs((w["fim"] - w["inicio"]) - tamanho) < 0.3 and w["inicio"] < 300, f"arrastar a faixa mantém a duração ({w['inicio']}-{w['fim']})")

        # --- limites: faixa não sai do vídeo ---
        pagina.fill("#t-ini", "9:50"); pagina.press("#t-ini", "Enter")
        pagina.fill("#t-fim", "15:00"); pagina.press("#t-fim", "Enter")
        v = ultimo()
        conferir(v["fim"] == 600.0 and v["inicio"] == 590.0, f"fim não passa da duração ({v['inicio']}-{v['fim']})")

        # --- entrada inválida ---
        antes = len(msgs())
        pagina.fill("#t-fim", "abc"); pagina.press("#t-fim", "Enter")
        conferir(pagina.eval_on_selector("#t-fim", "e => e.classList.contains('ruim')") and len(msgs()) == antes, "tempo inválido é recusado sem avisar o Python")
        pagina.wait_for_timeout(1000)

        # --- ajuste fino e zoom ---
        pagina.fill("#t-ini", "5:00"); pagina.press("#t-ini", "Enter")
        pagina.fill("#t-fim", "5:30"); pagina.press("#t-fim", "Enter")
        pagina.click("#i-p1")
        conferir(ultimo()["inicio"] == 301.0, "botão +1s do início")
        rotulos_antes = pagina.eval_on_selector_all("#ticks span", "els => els.map(e => e.textContent)")
        pagina.click("#z-in")
        rotulos = pagina.eval_on_selector_all("#ticks span", "els => els.map(e => e.textContent)")
        conferir(rotulos != rotulos_antes and rotulos[0] != "0:00", f"ampliar muda a escala da linha do tempo {rotulos[0]}…{rotulos[-1]}")
        pct_ini = float(pagina.eval_on_selector("#hi", "e => e.style.left").rstrip('%'))
        conferir(0 < pct_ini < 100, f"alça visível na janela ampliada ({pct_ini:.1f}%)")
        pagina.click("#z-out")

        # --- clique na linha do tempo = ir para o ponto ---
        pagina.mouse.click(x(100), caixa[2] + 0)
        conferir(abs(jogador("t") - 100) <= tol, f"clicar na linha do tempo posiciona o vídeo ({jogador('t'):.1f} s)")

        # --- visual ---
        if imagens:
            imagens.mkdir(parents=True, exist_ok=True)
            pagina.screenshot(path=str(imagens / "player_760.png"), full_page=True)
            movel = navegador.new_page(viewport={"width": 380, "height": 900})
            movel.route("https://www.youtube.com/iframe_api",
                        lambda r: r.fulfill(status=200, content_type="application/javascript", body=YT_FALSO))
            movel.goto(HTML.as_uri())
            movel.evaluate("""window.postMessage({type: 'streamlit:render', theme: {},
                args: {chave: 'k2', video_id: 'abcdefghijk', posicao: 120, duracao_inicial: 60}}, '*')""")
            movel.wait_for_function("document.getElementById('tempo').textContent.includes('10:00.0')")
            movel.screenshot(path=str(imagens / "player_380.png"), full_page=True)

        # --- erro do YouTube: avisa, mas deixa marcar os tempos ---
        pagina.evaluate("__yt.players[0].opts.events.onError({data: 153})")
        conferir("erro 153" in pagina.inner_text("#aviso") and "Abrir no YouTube" in pagina.inner_text("#aviso"), "erro do player mostra aviso com link")

        conferir(not erros, f"sem erros de JavaScript {erros}")
        navegador.close()

    print(f"\n{'FALHOU' if falhas else 'tudo certo'}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
