"""
Janela "ver corte" — a marca de corte numa IMAGEM (TIFF, JPG, PNG, PSD).

Decisão do usuário (2026-09-21): "propõe e eu aprovo". A imagem não
declara onde a arte acaba (o PDF declara); o sistema acha a linha de corte
pelas marcas, desenha a proposta por cima da imagem e espera o OK. Nada é
cortado aqui — aprovar só guarda o retângulo; quem corta, no Photoshop e
conferindo, é o arquivamento (receber_artes.arquivar).

O retângulo VERMELHO é o que fica: a linha de corte mais a sangria. O
TRACEJADO AZUL é a linha de corte — a arte, cuja medida vai no nome. A
sangria é o único número que ele pode ajustar: a linha de corte vem das
marcas e não é palpite.

A lógica está em marcas_de_corte (propor_corte_imagem, retangulo_do_corte,
medidas_da_proposta); aqui é só tela.
"""
import concurrent.futures
import queue
import tkinter as tk

import marcas_de_corte as mc
from gui import (
    COR_ACENTO, COR_ALERTA, COR_BORDA_CARTAO, COR_CARTAO, COR_FUNDO_JANELA, COR_POSITIVO,
    COR_RIP_PARADO, COR_TEXTO, COR_TEXTO_SECUNDARIO,
)

AREA_MAXIMA = (1000, 600)


def _m(medida):
    """Duas casas e vírgula: igual ao que vai no nome do arquivo."""
    return ("%.2f x %.2f m" % medida).replace(".", ",") if medida else "?"


class JanelaCorteImagem(tk.Toplevel):
    def __init__(self, master, peca, ao_aprovar):
        super().__init__(master)
        self.peca = peca
        self.ao_aprovar = ao_aprovar
        self.proposta = peca.proposta_corte
        self.title("Marca de corte na imagem — %s" % peca.arquivo.nome)
        self.configure(bg=COR_FUNDO_JANELA)
        self.transient(master)
        self._fila = queue.Queue()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._foto = None

        tk.Label(self, text=peca.arquivo.nome, font=("Segoe UI", 12, "bold"), bg=COR_FUNDO_JANELA,
                 fg=COR_TEXTO).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(self, text="Vermelho: o que FICA (arte + sangria).   Tracejado azul: a linha de corte — "
                            "a medida que vai no nome.",
                 font=("Segoe UI", 8), bg=COR_FUNDO_JANELA, fg=COR_TEXTO_SECUNDARIO).pack(anchor="w", padx=16)
        self.canvas = tk.Canvas(self, width=AREA_MAXIMA[0], height=AREA_MAXIMA[1], bg="#dfe3e8",
                                highlightthickness=1, highlightbackground=COR_BORDA_CARTAO)
        self.canvas.pack(padx=16, pady=8)

        info = tk.Frame(self, bg=COR_CARTAO, highlightbackground=COR_BORDA_CARTAO, highlightthickness=1)
        info.pack(fill="x", padx=16)
        self.lbl_info = tk.Label(info, text="Procurando a marca de corte...", font=("Segoe UI", 10, "bold"),
                                 bg=COR_CARTAO, fg=COR_TEXTO, anchor="w", justify="left")
        self.lbl_info.pack(fill="x", padx=12, pady=(8, 2))
        self.lbl_detalhe = tk.Label(info, text="", font=("Segoe UI", 9), bg=COR_CARTAO,
                                    fg=COR_TEXTO_SECUNDARIO, anchor="w", justify="left", wraplength=980)
        self.lbl_detalhe.pack(fill="x", padx=12)
        linha = tk.Frame(info, bg=COR_CARTAO)
        linha.pack(fill="x", padx=12, pady=(4, 8))
        tk.Label(linha, text="Sangria que fica, em cada lado:", font=("Segoe UI", 9, "bold"),
                 bg=COR_CARTAO, fg=COR_TEXTO).pack(side="left")
        self.var_sangria = tk.StringVar(value="0")
        self.spin = tk.Spinbox(linha, from_=0, to=200, increment=1, width=5, textvariable=self.var_sangria,
                               font=("Segoe UI", 9), relief="solid", bd=1, justify="center", state="disabled")
        self.spin.pack(side="left", padx=6)
        tk.Label(linha, text="mm", font=("Segoe UI", 9), bg=COR_CARTAO, fg=COR_TEXTO).pack(side="left")
        self.var_sangria.trace_add("write", lambda *a: self._desenhar())

        botoes = tk.Frame(self, bg=COR_FUNDO_JANELA)
        botoes.pack(fill="x", padx=16, pady=12)
        tk.Button(botoes, text="Não cortar", font=("Segoe UI", 10), relief="solid", bd=1, bg=COR_CARTAO,
                  fg=COR_TEXTO, padx=14, pady=5, cursor="hand2", command=self._fechar).pack(side="left")
        self.btn_aprovar = tk.Button(botoes, text="Aprovar o corte", bg=COR_ACENTO, fg="white",
                                     font=("Segoe UI", 10, "bold"), relief="flat", padx=18, pady=6,
                                     cursor="hand2", state="disabled", command=self._aprovar)
        self.btn_aprovar.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.grab_set()
        self._bombear()
        if self.proposta and self.proposta.get("previa") is not None:
            self._mostrar()
        else:
            # imagem grande: a proposta ainda não existe — o Photoshop reduz agora
            self.lbl_detalhe.configure(text="Imagem grande: o Photoshop está reduzindo uma cópia pra "
                                            "procurar a marca. Pode levar um minuto.")
            self._executor.submit(self._propor)

    def _propor(self):
        try:
            proposta = mc.propor_corte_imagem(self.peca.local)
        except Exception as e:   # noqa: BLE001
            proposta = {"ok": False, "motivo": str(e), "corte_px": None, "previa": None}
        self._fila.put(proposta)

    def _bombear(self):
        try:
            while True:
                self.proposta = self._fila.get_nowait()
                self.peca.proposta_corte = self.proposta
                self._mostrar()
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(80, self._bombear)

    def _mostrar(self):
        p = self.proposta
        if p.get("previa") is not None:
            from PIL import ImageTk
            previa = p["previa"].copy()
            previa.thumbnail(AREA_MAXIMA)
            self._escala = previa.width / p["largura_px"]
            self._foto = ImageTk.PhotoImage(previa)
            self.canvas.configure(width=previa.width, height=previa.height)
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, image=self._foto, anchor="nw")
        if not p.get("corte_px"):
            self.lbl_info.configure(text="Não achei marca de corte nesta imagem — ela entra como veio.",
                                    fg=COR_POSITIVO)
            self.lbl_detalhe.configure(text=p.get("motivo") or "")
            return
        dpi = p.get("dpi")
        if dpi:
            self.var_sangria.set(str(round(p["sangria_px"] * 25.4 / dpi)))
            self.spin.configure(state="normal")
        cor = COR_POSITIVO if p["ok"] else COR_ALERTA
        self.lbl_info.configure(text=("Marca de corte encontrada — confira o retângulo e aprove." if p["ok"]
                                      else "Achei marcas, mas algo não bate — confira com cuidado."), fg=cor)
        self.btn_aprovar.configure(state="normal")
        self._desenhar()

    def _sangria_px(self):
        dpi = self.proposta.get("dpi")
        try:
            mm = max(0.0, float(self.var_sangria.get().replace(",", ".")))
        except ValueError:
            return self.proposta["sangria_px"]
        return mm / 25.4 * dpi if dpi else self.proposta["sangria_px"]

    def _desenhar(self):
        p = self.proposta
        if not p or not p.get("corte_px") or not hasattr(self, "_escala"):
            return
        self.canvas.delete("corte")
        e = self._escala
        x0, y0, x1, y1 = p["corte_px"]
        self.canvas.create_rectangle(x0 * e, y0 * e, x1 * e, y1 * e, outline="#1f6feb", dash=(4, 3),
                                     width=1, tags="corte")
        r = mc.retangulo_do_corte(p, self._sangria_px())
        self.canvas.create_rectangle(r[0] * e, r[1] * e, r[2] * e, r[3] * e, outline=COR_RIP_PARADO,
                                     width=2, tags="corte")
        arte, fica = mc.medidas_da_proposta(p, self._sangria_px())
        partes = ["A arte (entre as marcas): %s" % _m(arte) if arte else "A imagem não tem DPI gravado",
                  "o que fica, com a sangria: %s" % _m(fica) if fica else ""]
        if p.get("desacordo_mm") is not None:
            partes.append(("marcas de lados opostos batendo com %.1f mm de diferença"
                           % p["desacordo_mm"]).replace(".", ","))
        if not p["ok"]:
            partes.append(p.get("motivo", ""))
        self.lbl_detalhe.configure(text="   ·   ".join(t for t in partes if t))

    def _aprovar(self):
        retangulo = mc.retangulo_do_corte(self.proposta, self._sangria_px())
        arte, fica = mc.medidas_da_proposta(self.proposta, self._sangria_px())
        self.ao_aprovar(retangulo, arte, fica)
        self._fechar()

    def _fechar(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
