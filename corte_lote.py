"""
Junta num lote só tudo o que está esperando corte do mesmo material.

Por que existe: hoje cada pedido vai pra fresa sozinho. Encaixar cinco
peças numa chapa de 1220x2440 deixa chapa sobrando; encaixar as quarenta
que estão esperando aproveita o material de verdade. O desperdício não
está no encaixe — está em encaixar pouca coisa por vez.

O que este módulo NÃO faz: encaixar. O encaixe por forma real é do
Aspire (Nest Parts), e ele não é programável — é uma janela. Foi
verificado no programa instalado (07/09/2026): a linguagem do Aspire
expõe ImportDxfDwg, ImportSVG, ImportBitmap e ImportSTLDirect, e nada
de encaixe. Então aqui as peças são só REUNIDAS e postas lado a lado
sem se tocarem, que é o estado em que o Aspire consegue encaixar.

A disposição daqui é por prateleira (linha a linha), que é pior que o
encaixe do Aspire de propósito: ela existe pra dar um número honesto de
quantas chapas o lote pede, e pra que nada chegue sobreposto. Quem
aperta o lote é o Aspire, depois.
"""
import dataclasses
import pathlib

import corte_dxf
import corte_parametros

# Chapa cheia de PVC/MDF: 1220 x 2440 mm. Fica como padrão, mas entra
# por parâmetro porque acrílico costuma vir em outras medidas.
CHAPA_PADRAO_MM = (1220.0, 2440.0)

# Vão entre as linhas de corte de duas peças vizinhas. É o número que o
# Flávio pediu (07/09/2026): 15 mm "para não colidir uma linha da
# outra". No Aspire esse mesmo vão se digita como Tool Dia + Clearance
# (4 + 11 com a fresa de 4 mm) — ver corte_parametros.
FOLGA_ENTRE_PECAS_MM = 15.0

# Distância mínima da linha de corte até a borda da chapa. A fresa
# precisa caber inteira ali, e a chapa precisa ter onde ser presa.
FOLGA_DA_BORDA_MM = 15.0


@dataclasses.dataclass
class Peca:
    """Uma peça de corte lida de um PDF, já em milímetros."""

    pdf: pathlib.Path
    material: str
    espessura: int
    quantidade: int
    polilinhas: list
    camadas: list

    @property
    def caixa(self):
        return _caixa(self.polilinhas)

    @property
    def largura(self):
        x0, _, x1, _ = self.caixa
        return x1 - x0

    @property
    def altura(self):
        _, y0, _, y1 = self.caixa
        return y1 - y0

    @property
    def area_m2(self):
        """Área da CAIXA da peça, não da forma. Ver observação em resumo()."""
        return (self.largura / 1000.0) * (self.altura / 1000.0)


def _caixa(polilinhas):
    xs = [x for poli in polilinhas for x, _ in poli]
    ys = [y for poli in polilinhas for _, y in poli]
    return min(xs), min(ys), max(xs), max(ys)


def _mover(polilinhas, dx, dy):
    return [[(x + dx, y + dy) for x, y in poli] for poli in polilinhas]


def _girar90(polilinhas):
    """Gira 90° no sentido anti-horário: (x, y) -> (-y, x)."""
    return [[(-y, x) for x, y in poli] for poli in polilinhas]


def _encostar_na_origem(polilinhas):
    x0, y0, _, _ = _caixa(polilinhas)
    return _mover(polilinhas, -x0, -y0)


# Por que um PDF ficou de fora do lote. A diferença entre os dois
# primeiros é a diferença entre "normal" e "alguém precisa agir", e
# misturá-los foi o que atrapalhou no primeiro teste com a pasta da
# UMBRO (07/09/2026): a arte impressa aparecia na mesma lista de
# problemas que o arquivo de corte que só faltava cadastrar.
SEM_CORTE = "sem_corte"          # não tem linha de corte — deve ser a arte de impressão
SEM_CADASTRO = "sem_cadastro"    # TEM corte, mas não sei com que fresa cortar
ILEGIVEL = "ilegivel"            # nem abrir deu


def ler_peca(caminho_pdf):
    """
    Lê um PDF de corte e devolve (Peca, None), ou (None, (codigo, motivo)).

    Nunca escreve nada. Recusa em vez de chutar: sem material e
    espessura no nome não dá pra saber com que fresa cortar, e um lote
    com a peça errada dentro só se descobre com a chapa na máquina.
    """
    caminho_pdf = pathlib.Path(caminho_pdf)

    try:
        polilinhas, relatorio = corte_dxf.extrair_contornos(caminho_pdf)
    except Exception as e:
        return None, (ILEGIVEL, f"não consegui ler: {e}")

    if not polilinhas:
        return None, (SEM_CORTE, "nenhuma linha de corte encontrada")

    combinacao = corte_parametros.material_e_espessura(caminho_pdf.name)
    if combinacao is None:
        return None, (SEM_CADASTRO,
                      f"tem {len(polilinhas)} contorno(s) de corte, mas o nome não "
                      f"diz um material e espessura cadastrados")

    import dimensoes

    quantidade, _ = dimensoes.extrair_quantidade(caminho_pdf.name)
    material, espessura = combinacao

    return Peca(
        pdf=caminho_pdf,
        material=material,
        espessura=espessura,
        quantidade=quantidade,
        polilinhas=_encostar_na_origem(polilinhas),
        camadas=corte_dxf.classificar_aninhamento(polilinhas),
    ), None


def juntar(pasta):
    """
    Varre a pasta e devolve (lotes, recusados).

    'lotes' é {(material, espessura): [Peca, ...]} e 'recusados' é uma
    lista de (caminho, codigo, motivo) — que é tão importante quanto o
    resto: peça que ficou de fora sem ninguém ver é peça que não vai ser
    cortada e ninguém vai lembrar. O 'codigo' é SEM_CORTE, SEM_CADASTRO
    ou ILEGIVEL, pra quem mostra a lista poder separar o que é normal do
    que precisa de alguém.

    Só lê. Nunca escreve, nunca move, nunca renomeia.
    """
    pasta = pathlib.Path(pasta)
    lotes, recusados = {}, []
    if not pasta.is_dir():
        return lotes, recusados

    for pdf in sorted(pasta.rglob("*.pdf")):
        if any(p.upper() == "ENVIADOS" for p in pdf.relative_to(pasta).parts[:-1]):
            continue
        peca, recusa = ler_peca(pdf)
        if peca is None:
            recusados.append((pdf,) + recusa)
            continue
        lotes.setdefault((peca.material, peca.espessura), []).append(peca)

    return lotes, recusados


def cabe_na_chapa(peca, chapa=CHAPA_PADRAO_MM, folga_borda=FOLGA_DA_BORDA_MM):
    """
    A peça cabe na chapa, em pé ou deitada?

    Devolve (cabe, precisa_girar). Existe porque isso já mordeu: o
    arquivo de teste tem 1244,9 mm de largura e a chapa tem 1220 —
    deitado não cabe por 25 mm, girado sobra. Descobrir isso aqui é de
    graça; descobrir na máquina custa uma chapa.
    """
    larg = chapa[0] - 2 * folga_borda
    alt = chapa[1] - 2 * folga_borda
    if peca.largura <= larg and peca.altura <= alt:
        return True, False
    if peca.altura <= larg and peca.largura <= alt:
        return True, True
    return False, False


def dispor(pecas, chapa=CHAPA_PADRAO_MM, folga=FOLGA_ENTRE_PECAS_MM,
           folga_borda=FOLGA_DA_BORDA_MM):
    """
    Põe todas as cópias de todas as peças lado a lado, sem se tocarem.

    Devolve (polilinhas, camadas, chapas_usadas, nao_couberam).

    As chapas ficam uma ao lado da outra no eixo X, do jeito que o
    próprio Aspire mostra as folhas extras do encaixe — assim dá pra
    ver o lote inteiro de uma vez ao abrir o arquivo.

    Prateleira simples: as peças mais altas primeiro, enchendo a linha
    da esquerda pra direita e subindo quando a linha lota. É pior que o
    encaixe do Aspire, e é pra ser mesmo — ver o cabeçalho do módulo.
    """
    largura_util = chapa[0] - 2 * folga_borda
    altura_util = chapa[1] - 2 * folga_borda

    copias, nao_couberam = [], []
    for peca in pecas:
        cabe, girar = cabe_na_chapa(peca, chapa, folga_borda)
        if not cabe:
            nao_couberam.append(peca)
            continue
        forma = _encostar_na_origem(_girar90(peca.polilinhas)) if girar else peca.polilinhas
        for _ in range(peca.quantidade):
            copias.append((forma, peca.camadas))

    # Mais altas primeiro: é o que faz a prateleira não desperdiçar
    # faixa de chapa embaixo de peça baixinha.
    copias.sort(key=lambda c: _caixa(c[0])[3] - _caixa(c[0])[1], reverse=True)

    saida_polis, saida_camadas = [], []
    chapa_indice = 0
    x_linha = 0.0
    y_linha = 0.0
    altura_linha = 0.0

    for forma, camadas in copias:
        _, _, larg, alt = _caixa(forma)

        if x_linha > 0 and x_linha + larg > largura_util:
            # Linha cheia: sobe pra próxima prateleira.
            y_linha += altura_linha + folga
            x_linha = 0.0
            altura_linha = 0.0

        if y_linha + alt > altura_util:
            # Chapa cheia: começa a próxima, ao lado.
            chapa_indice += 1
            x_linha = y_linha = altura_linha = 0.0

        dx = chapa_indice * (chapa[0] + folga_borda) + folga_borda + x_linha
        dy = folga_borda + y_linha
        saida_polis.extend(_mover(forma, dx, dy))
        saida_camadas.extend(camadas)

        x_linha += larg + folga
        altura_linha = max(altura_linha, alt)

    return saida_polis, saida_camadas, chapa_indice + 1 if copias else 0, nao_couberam


def resumo(material, espessura, pecas, chapa=CHAPA_PADRAO_MM):
    """
    Os números do lote, pra caber numa linha de tela ou numa folha.

    A área é sempre POR MATERIAL — nunca somada com a de outro. É a
    regra da casa: 3 m² de PVC 10 e 3 m² de MDF 9 não são 6 m² de nada,
    são duas compras diferentes.

    'area_m2' é a área das CAIXAS das peças, não das formas: é o que se
    paga de chapa se cada peça fosse cortada sozinha num retângulo. A
    diferença entre ela e a área de chapa gasta é justamente o que o
    encaixe economiza.
    """
    _, _, chapas_prateleira, nao_couberam = dispor(pecas, chapa)

    # A área das peças que NÃO cabem fica separada de propósito. Somar
    # tudo junto deu 87% de aproveitamento no primeiro teste (07/09/2026)
    # contando dois castelos de 3,5 m que nem entraram na chapa — número
    # bonito e mentiroso, do tipo que faz comprar chapa a menos.
    dentro = [p for p in pecas if cabe_na_chapa(p, chapa)[0]]
    fora = [p for p in pecas if not cabe_na_chapa(p, chapa)[0]]

    area_chapa = (chapa[0] / 1000.0) * (chapa[1] / 1000.0)
    area = sum(p.area_m2 * p.quantidade for p in dentro)
    area_fora = sum(p.area_m2 * p.quantidade for p in fora)

    # Duas contas, e nenhuma delas é "a" resposta: o encaixe do Aspire
    # cai em algum lugar entre as duas. O mínimo é só a área (nem o
    # melhor encaixe do mundo faz melhor); a prateleira é o pior caso.
    chapas_minimo = int(-(-area // area_chapa)) if area else 0
    return {
        "material": material,
        "espessura": espessura,
        "arquivos": len(dentro),
        "unidades": sum(p.quantidade for p in dentro),
        "area_m2": area,
        "chapas_minimo": chapas_minimo,
        "chapas_prateleira": chapas_prateleira,
        "area_chapa_m2": area_chapa,
        "nao_couberam": nao_couberam,
        "unidades_fora": sum(p.quantidade for p in fora),
        "area_fora_m2": area_fora,
        "atalho": corte_parametros.atalho_do_menu(f"{material} {espessura}MM"),
    }


def escrever_lote(material, espessura, pecas, caminho_dxf, chapa=CHAPA_PADRAO_MM):
    """
    Escreve UM dxf com todas as cópias de todas as peças do lote.

    Devolve o resumo, com 'dxf' preenchido. O arquivo é sempre novo —
    nenhum PDF de origem é tocado, movido ou renomeado.
    """
    polilinhas, camadas, chapas, nao_couberam = dispor(pecas, chapa)
    if not polilinhas:
        dados = resumo(material, espessura, pecas, chapa)
        dados["dxf"] = None
        return dados

    caminho_dxf = pathlib.Path(caminho_dxf)
    corte_dxf.escrever_dxf(polilinhas, caminho_dxf, camadas)

    dados = resumo(material, espessura, pecas, chapa)
    dados["dxf"] = str(caminho_dxf)
    dados["contornos"] = len(polilinhas)
    return dados
