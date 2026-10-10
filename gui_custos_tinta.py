"""Cadastro de preço e consumo estimado das tintas das Docan."""
import copy
import tkinter as tk
from tkinter import messagebox, ttk

import custos_tinta
import estoque
from config import carregar_config, salvar_config
from custos import formatar_reais


class JanelaCustosTinta(tk.Toplevel):
    def __init__(self, mestre, on_salvar):
        super().__init__(mestre)
        self.title("Centro de custos · Tintas Docan")
        self.geometry("730x670")
        self.transient(mestre)
        self.on_salvar = on_salvar
        cfg = carregar_config()
        self.configuracao = copy.deepcopy(cfg["centro_custos_tintas"])
        self.campos = {}
        self.provisoria = tk.BooleanVar(value=self.configuracao["maquinas"][custos_tinta.H2525]["referencia_provisoria"])
        ttk.Label(self, text="Centro de custos de tinta", font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=18, pady=(14,4))
        ttk.Label(self, text="Preço por frasco e consumo por cor. Os gastos estimados aparecem apenas na OS.").pack(anchor="w", padx=18)
        abas = ttk.Notebook(self)
        abas.pack(fill="x", padx=18, pady=12)
        for maquina in (custos_tinta.R5200, custos_tinta.H2525):
            painel = ttk.Frame(abas, padding=12)
            abas.add(painel, text=maquina)
            for coluna, titulo in enumerate(["Tinta", "Frasco (mL)", "Preço do frasco (R$)", "Consumo (mL/m²)"]):
                ttk.Label(painel, text=titulo).grid(row=0, column=coluna, sticky="w", padx=6, pady=5)
            for linha, (cor, nome) in enumerate(custos_tinta.CORES.items(), 1):
                ttk.Label(painel, text=nome).grid(row=linha, column=0, sticky="w", padx=6, pady=5)
                dados = self.configuracao["maquinas"][maquina]["cores"][cor]
                campos = {}
                for coluna, chave in enumerate(["capacidade_ml", "preco_frasco", "consumo_ml_m2"], 1):
                    valor = dados[chave]
                    var = tk.StringVar(value="" if valor is None else str(valor).replace(".", ","))
                    ttk.Entry(painel, textvariable=var, width=17).grid(row=linha, column=coluna, padx=6, pady=5)
                    campos[chave] = var
                self.campos[maquina, cor] = campos
            ttk.Label(painel, text="Referência: 5,00 × 0,50 m = 2,50 m² · R5200 · ICC Eterna_R5200_6Pass.icc").grid(row=5, column=0, columnspan=4, sticky="w", pady=(9,4))
            if maquina == custos_tinta.H2525:
                ttk.Checkbutton(painel, text="Identificar como referência provisória da R5200", variable=self.provisoria).grid(row=6, column=0, columnspan=4, sticky="w")
        bloco = ttk.LabelFrame(self, text="Máquina prevista por material", padding=9)
        bloco.pack(fill="x", padx=18, pady=(0,8))
        ttk.Label(bloco, text="A máquina da peça tem prioridade. Chapas entram apenas com IMPRESSO no nome.").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0,8))
        self.materiais = {}
        for indice, categoria in enumerate(cfg["materiais"]):
            linha, coluna = indice // 2 + 1, (indice % 2) * 2
            ttk.Label(bloco, text=categoria).grid(row=linha, column=coluna, sticky="w", padx=6, pady=4)
            var = tk.StringVar(value=self.configuracao["maquinas_por_material"].get(categoria, ""))
            ttk.Combobox(bloco, textvariable=var, values=("", custos_tinta.R5200, custos_tinta.H2525), state="readonly", width=20).grid(row=linha, column=coluna+1, sticky="w", padx=6, pady=4)
            self.materiais[categoria] = var
        self.previa = tk.StringVar()
        ttk.Label(self, textvariable=self.previa, wraplength=680).pack(anchor="w", padx=18, pady=6)
        botoes = ttk.Frame(self)
        botoes.pack(fill="x", padx=18, pady=12)
        ttk.Button(botoes, text="Simular 5,00 × 0,50 m", command=self._simular).pack(side="left")
        ttk.Button(botoes, text="Salvar", command=self._salvar).pack(side="right")
        self._simular()

    def _ler_campos(self):
        cfg = copy.deepcopy(self.configuracao)
        for (maquina, cor), campos in self.campos.items():
            for chave, var in campos.items():
                texto = var.get().strip()
                if chave == "preco_frasco" and not texto:
                    cfg["maquinas"][maquina]["cores"][cor][chave] = None
                    continue
                numero = custos_tinta._numero(texto, zero=chave == "consumo_ml_m2")
                if numero is None:
                    raise ValueError(
                        f"{maquina} / {custos_tinta.CORES[cor]}: confira o frasco, o preço e o consumo. "
                        "Deixe o preço em branco se ainda não estiver cadastrado.")
                cfg["maquinas"][maquina]["cores"][cor][chave] = float(numero)
        cfg["maquinas"][custos_tinta.H2525]["referencia_provisoria"] = self.provisoria.get()
        cfg["maquinas"][custos_tinta.H2525]["referencia_consumo"] = custos_tinta.R5200 if self.provisoria.get() else custos_tinta.H2525
        cfg["maquinas_por_material"] = {cat: var.get() for cat, var in self.materiais.items() if var.get()}
        return cfg

    def _simular(self):
        try:
            cfg = self._ler_campos()
            itens = [dict(maquina=m, arquivo="SIMULAÇÃO", quantidade=1, dimensao={"area_m2":2.5}) for m in (custos_tinta.R5200, custos_tinta.H2525)]
            contas = custos_tinta.calcular(itens, cfg)
            if not contas["completo"]:
                self.previa.set("Informe os preços por frasco para calcular os custos estimados.")
                return
            self.previa.set("Para a arte de 2,50 m²: " + " · ".join(
                f"{m}: " + f"{c['volume_ml']:.2f}".replace('.', ',') + f" mL / {formatar_reais(c['valor'])}"
                for m, c in contas["por_maquina"].items()))
        except ValueError as erro:
            self.previa.set(str(erro))

    def _salvar(self):
        try:
            tintas = self._ler_campos()
        except ValueError as erro:
            messagebox.showwarning("Confira os valores", str(erro), parent=self)
            return
        cfg = carregar_config()
        cfg["centro_custos_tintas"] = tintas
        cadastro = estoque.carregar_estoque()
        custos_tinta.sincronizar_catalogo(cadastro, tintas)
        estoque.salvar_estoque(cadastro)
        salvar_config(cfg)
        self.on_salvar(cfg)
        self.destroy()
