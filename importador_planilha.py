"""
importador_planilha.py — Leitor e cruzador robusto de planilhas de corte e pedidos (ISSUE-09).

Suporta:
- Arquivos CSV com detecção automática de delimitadores (',', ';', '\t', '|')
  e detecção de encodings ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252').
- Arquivos XLSX/XLSM via openpyxl com leitura segura de valores calculados.
- Normalização inteligente de cabeçalhos (arquivo, quantidade, material, largura, altura, unidade, cliente, os).
- Extração de dimensões e unidades embutidas (ex: 'Largura (cm)', '120 cm', '1.50m').
- Algoritmo de cruzamento (matching) entre lista de arquivos da pasta e linhas da planilha
  (correspondência exata, sem extensão, substring ou não encontrado).
"""

from __future__ import annotations

import csv
import io
import os
import pathlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

# Mapeamento de termos normalizados para nomes canônicos de colunas
MAPA_CABECALHOS_CANONICOS = {
    # Arquivo / Arte
    "arquivo": "arquivo",
    "arquivopdf": "arquivo",
    "arquivo_pdf": "arquivo",
    "nomearquivo": "arquivo",
    "nome_arquivo": "arquivo",
    "nomedoarquivo": "arquivo",
    "nome_do_arquivo": "arquivo",
    "nome": "arquivo",
    "pdf": "arquivo",
    "file": "arquivo",
    "filename": "arquivo",
    "item": "arquivo",
    "arte": "arquivo",
    "artes": "arquivo",
    "peca": "arquivo",
    "peça": "arquivo",
    "desenho": "arquivo",
    "corte": "arquivo",
    "imagem": "arquivo",

    # Quantidade
    "quantidade": "quantidade",
    "qtd": "quantidade",
    "qtde": "quantidade",
    "quant": "quantidade",
    "qnt": "quantidade",
    "unidades": "quantidade",
    "unidade_qtd": "quantidade",
    "unidadeqtd": "quantidade",
    "unid": "quantidade",
    "un": "quantidade",
    "qty": "quantidade",
    "copias": "quantidade",
    "cópias": "quantidade",
    "numerodecopias": "quantidade",
    "numcopias": "quantidade",
    "quantidadedecopias": "quantidade",
    "reps": "quantidade",

    # Material / Substrato
    "material": "material",
    "substrato": "material",
    "midia": "material",
    "mídia": "material",
    "tipomaterial": "material",
    "tipo_material": "material",
    "tipodematerial": "material",
    "tipo": "material",
    "produto": "material",
    "suporte": "material",

    # Largura
    "largura": "largura",
    "larg": "largura",
    "larguracm": "largura",
    "larguramm": "largura",
    "larguram": "largura",
    "larg_cm": "largura",
    "larg_mm": "largura",
    "larg_m": "largura",
    "largcm": "largura",
    "largmm": "largura",
    "largm": "largura",
    "width": "largura",
    "w": "largura",
    "base": "largura",
    "l": "largura",

    # Altura / Comprimento
    "altura": "altura",
    "alt": "altura",
    "alturacm": "altura",
    "alturamm": "altura",
    "alturam": "altura",
    "alt_cm": "altura",
    "alt_mm": "altura",
    "alt_m": "altura",
    "altcm": "altura",
    "altmm": "altura",
    "altm": "altura",
    "height": "altura",
    "h": "altura",
    "comp": "altura",
    "comprimento": "altura",
    "comprimentocm": "altura",
    "comprimentomm": "altura",
    "comprimentom": "altura",
    "a": "altura",

    # Unidade de medida
    "unidade": "unidade",
    "unid_medida": "unidade",
    "unidmedida": "unidade",
    "unit": "unidade",
    "medida": "unidade",
    "dimensao": "unidade",
    "dimensão": "unidade",
    "u": "unidade",

    # Cliente
    "cliente": "cliente",
    "client": "cliente",
    "empresa": "cliente",
    "comprador": "cliente",
    "solicitante": "cliente",
    "contato": "cliente",
    "nomecliente": "cliente",
    "nome_cliente": "cliente",

    # OS / Pedido
    "os": "os",
    "o.s.": "os",
    "o.s": "os",
    "ordemservico": "os",
    "ordemdeservico": "os",
    "ordem_servico": "os",
    "ordem_de_servico": "os",
    "ordem": "os",
    "pedido": "os",
    "numeropedido": "os",
    "numero_pedido": "os",
    "numpedido": "os",
    "num_pedido": "os",
    "codpedido": "os",
    "cod_pedido": "os",
    "numos": "os",

    # Descrição / Observação
    "descricao": "descricao",
    "descrição": "descricao",
    "desc": "descricao",
    "obs": "descricao",
    "observacao": "descricao",
    "observação": "descricao",
    "observacoes": "descricao",
    "observações": "descricao",
    "detalhes": "descricao",
    "nota": "descricao",

    # Escala
    "escala": "escala",
    "scale": "escala",
    "proporcao": "escala",
    "proporção": "escala",
}

FATORES_PARA_METRO = {
    "M": 1.0,
    "MT": 1.0,
    "MTS": 1.0,
    "METRO": 1.0,
    "METROS": 1.0,
    "CM": 0.01,
    "CENTIMETRO": 0.01,
    "CENTIMETROS": 0.01,
    "MM": 0.001,
    "MILIMETRO": 0.001,
    "MILIMETROS": 0.001,
    "POL": 0.0254,
    "POLLEGADA": 0.0254,
    "IN": 0.0254,
}


def remover_acentos(texto: str) -> str:
    """Remove marcas diacríticas e converte para string simples ascii."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def limpar_texto_chave(texto: str) -> str:
    """Normaliza um texto para busca de cabeçalho (minúsculo, sem pontuação/acentos)."""
    t = remover_acentos(texto).lower().strip()
    return re.sub(r'[^a-z0-9]+', '', t)


def normalizar_cabecalho(cabecalho_bruto: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Identifica o nome canônico do campo e detecta eventual unidade embutida no cabeçalho.
    Exemplos:
      'Largura (cm)' -> ('largura', 'CM')
      'ALTURA [MM]' -> ('altura', 'MM')
      'Nome do Arquivo' -> ('arquivo', None)
      'Qtd.' -> ('quantidade', None)
    """
    if not cabecalho_bruto:
        return None, None

    texto_limpo = str(cabecalho_bruto).strip()
    unidade_detectada: Optional[str] = None

    # Tenta detectar unidade entre parênteses, colchetes ou sufixo
    m_unid = re.search(r'[\(\[\s_](CM|MM|MTS?|METROS?|POL|IN)[\)\]\s_]?$', texto_limpo, re.IGNORECASE)
    if m_unid:
        unidade_detectada = m_unid.group(1).upper()
        if unidade_detectada.startswith("M") and not unidade_detectada.startswith("MM"):
            unidade_detectada = "M"

    chave = limpar_texto_chave(texto_limpo)
    if chave in MAPA_CABECALHOS_CANONICOS:
        return MAPA_CABECALHOS_CANONICOS[chave], unidade_detectada

    # Tenta casamento sem sufixos de unidade
    chave_sem_unid = re.sub(r'(?:cm|mm|m|mts|metros)$', '', chave)
    if chave_sem_unid in MAPA_CABECALHOS_CANONICOS:
        return MAPA_CABECALHOS_CANONICOS[chave_sem_unid], unidade_detectada

    # Checagem específica para 'os' com fronteiras de palavra para não casar em 'metros' ou 'blocos'
    if re.search(r'(?:^|[\s._\-])os(?:$|[\s._\-])', texto_limpo, re.IGNORECASE):
        return "os", unidade_detectada

    # Mapeamento de substrings seguras para campos canônicos no fallback
    GRUPOS_SUBSTRINGS = [
        ("os", ("pedido", "ordem", "numos", "codos")),
        ("arquivo", ("arquivo", "pdf", "file", "arte", "peca", "desenho", "corte")),
        ("quantidade", ("quantidade", "qtd", "copia", "reps")),
        ("material", ("material", "substrat", "midia", "produto")),
        ("largura", ("largura", "width", "base")),
        ("altura", ("altura", "height", "comprimento")),
        ("cliente", ("cliente", "client", "empresa", "comprador")),
        ("descricao", ("descricao", "obs", "observacao", "detalhe")),
        ("escala", ("escala", "scale", "proporcao")),
    ]

    for campo_alvo, padroes in GRUPOS_SUBSTRINGS:
        for p in padroes:
            if p in chave:
                return campo_alvo, unidade_detectada

    return None, unidade_detectada


def converter_valor_numerico(val: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Converte uma célula numérica ou textual para float, tratando vírgula decimal
    e extraindo unidade se estiver no texto (ex: '120 cm' -> (120.0, 'CM')).
    """
    if val is None:
        return None, None

    if isinstance(val, (int, float)):
        return float(val), None

    s = str(val).strip()
    if not s:
        return None, None

    # Tenta detectar unidade no texto
    unidade = None
    m_unid = re.search(r'([A-Za-z]+)\s*$', s)
    if m_unid:
        u_cand = m_unid.group(1).upper()
        if u_cand in FATORES_PARA_METRO:
            unidade = "M" if (u_cand.startswith("M") and not u_cand.startswith("MM")) else u_cand
            s = s[:m_unid.start()].strip()

    # Normalizar números brasileiros com vírgula e possíveis pontos de milhar
    s = s.replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # Ex: 1.250,50 -> 1250.50
            s = s.replace(".", "").replace(",", ".")
        else:
            # Ex: 1,250.50 -> 1250.50
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return float(s), unidade
    except ValueError:
        return None, None


def converter_inteiro(val: Any, padrao: int = 1) -> int:
    """Converte valor para inteiro >= 1 de quantidade."""
    if val is None:
        return padrao
    if isinstance(val, (int, float)):
        v = int(val)
        return max(1, v)
    num, _ = converter_valor_numerico(val)
    if num is not None:
        return max(1, int(round(num)))
    return padrao


def detectar_encoding(caminho_ou_bytes: Union[str, pathlib.Path, bytes]) -> str:
    """
    Detecta encoding de arquivo de texto (CSV):
    Testa UTF-8 com BOM, UTF-8 padrão, Latin-1 e CP1252.
    """
    if isinstance(caminho_ou_bytes, (str, pathlib.Path)):
        with open(caminho_ou_bytes, "rb") as f:
            amostra = f.read(65536)
    else:
        amostra = bytes(caminho_ou_bytes)[:65536]

    if amostra.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"

    try:
        amostra.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    try:
        amostra.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        pass

    return "latin-1"


def detectar_delimitador(texto: str) -> str:
    """
    Detecta delimitador em CSV (',', ';', '\t', '|').
    Prioriza sniffer estatístico e faz fallback seguro para a primeira linha.
    """
    linhas = [l for l in texto.splitlines() if l.strip()]
    if not linhas:
        return ","

    amostra = "\n".join(linhas[:15])
    try:
        sniffer = csv.Sniffer()
        dialeto = sniffer.sniff(amostra, delimiters=";,|\t")
        return dialeto.delimiter
    except Exception:
        pass

    # Contagem na primeira linha com dados
    primeira = linhas[0]
    contagens = {
        ";": primeira.count(";"),
        ",": primeira.count(","),
        "\t": primeira.count("\t"),
        "|": primeira.count("|"),
    }
    delimitador = max(contagens, key=contagens.get)
    if contagens[delimitador] > 0:
        return delimitador
    return ","


def ler_csv(caminho_ou_dados: Union[str, pathlib.Path, bytes, io.StringIO]) -> List[Dict[str, Any]]:
    """Lê arquivo CSV e retorna linhas normalizadas com cabeçalhos canônicos."""
    if isinstance(caminho_ou_dados, io.StringIO):
        conteudo = caminho_ou_dados.getvalue()
    elif isinstance(caminho_ou_dados, bytes):
        enc = detectar_encoding(caminho_ou_dados)
        conteudo = caminho_ou_dados.decode(enc, errors="replace")
    else:
        p = pathlib.Path(caminho_ou_dados)
        enc = detectar_encoding(p)
        conteudo = p.read_text(encoding=enc, errors="replace")

    delimitador = detectar_delimitador(conteudo)
    leitor = csv.reader(io.StringIO(conteudo), delimiter=delimitador)
    linhas_brutas = [linha for linha in leitor if any(c.strip() for c in linha)]
    if not linhas_brutas:
        return []

    return _processar_matriz_tabular(linhas_brutas)


def ler_xlsx(caminho_ou_dados: Union[str, pathlib.Path, bytes, io.BytesIO]) -> List[Dict[str, Any]]:
    """Lê arquivo Excel (.xlsx, .xlsm) usando openpyxl."""
    import openpyxl

    if isinstance(caminho_ou_dados, (str, pathlib.Path)):
        wb = openpyxl.load_workbook(str(caminho_ou_dados), data_only=True, read_only=True)
    elif isinstance(caminho_ou_dados, bytes):
        wb = openpyxl.load_workbook(io.BytesIO(caminho_ou_dados), data_only=True, read_only=True)
    else:
        wb = openpyxl.load_workbook(caminho_ou_dados, data_only=True, read_only=True)

    ws = wb.active
    linhas_brutas: List[List[Any]] = []
    for linha in ws.iter_rows(values_only=True):
        if any(v is not None and str(v).strip() != "" for v in linha):
            linhas_brutas.append(list(linha))

    wb.close()
    if not linhas_brutas:
        return []

    return _processar_matriz_tabular(linhas_brutas)


def _processar_matriz_tabular(linhas: List[List[Any]]) -> List[Dict[str, Any]]:
    """
    Processa linhas de uma matriz (primeira linha = cabeçalho) e gera dicionários estruturados.
    """
    cabecalho_bruto = linhas[0]
    mapa_colunas: Dict[int, Tuple[str, Optional[str]]] = {}

    for idx, col in enumerate(cabecalho_bruto):
        if col is None:
            continue
        canonico, unid_cab = normalizar_cabecalho(str(col))
        if canonico:
            mapa_colunas[idx] = (canonico, unid_cab)

    dados: List[Dict[str, Any]] = []
    for num_linha, linha in enumerate(linhas[1:], start=2):
        item: Dict[str, Any] = {
            "arquivo": None,
            "quantidade": 1,
            "largura": None,
            "altura": None,
            "unidade": "M",
            "largura_m": None,
            "altura_m": None,
            "material": None,
            "cliente": None,
            "os": None,
            "descricao": None,
            "escala": None,
            "numero_linha": num_linha,
            "linha_original": {},
        }

        unidade_linha = None

        for idx, valor in enumerate(linha):
            if idx >= len(cabecalho_bruto):
                continue
            col_nome_original = str(cabecalho_bruto[idx] or f"col_{idx}")
            item["linha_original"][col_nome_original] = valor

            if idx not in mapa_colunas or valor is None:
                continue

            canonico, unid_cab = mapa_colunas[idx]
            val_str = str(valor).strip()

            if canonico == "arquivo":
                item["arquivo"] = val_str or None
            elif canonico == "quantidade":
                item["quantidade"] = converter_inteiro(valor, padrao=1)
            elif canonico in ("largura", "altura"):
                num, u_num = converter_valor_numerico(valor)
                item[canonico] = num
                if u_num:
                    unidade_linha = u_num
                elif unid_cab:
                    unidade_linha = unid_cab
            elif canonico == "unidade":
                u_str = val_str.upper()
                if u_str in FATORES_PARA_METRO:
                    unidade_linha = "M" if (u_str.startswith("M") and not u_str.startswith("MM")) else u_str
            elif canonico == "material":
                item["material"] = val_str or None
            elif canonico == "cliente":
                item["cliente"] = val_str or None
            elif canonico == "os":
                item["os"] = val_str or None
            elif canonico == "descricao":
                item["descricao"] = val_str or None
            elif canonico == "escala":
                item["escala"] = val_str or None

        # Se detectou unidade, define; caso contrário, infere
        if unidade_linha:
            item["unidade"] = unidade_linha
        else:
            # Heurística: se largura > 15 e altura > 15 e sem unidade, muito provável ser CM
            larg = item.get("largura")
            alt = item.get("altura")
            if larg and alt and larg > 15 and alt > 15:
                item["unidade"] = "CM"
            else:
                item["unidade"] = "M"

        # Calcular largura_m e altura_m
        fator = FATORES_PARA_METRO.get(item["unidade"], 1.0)
        if item["largura"] is not None:
            item["largura_m"] = round(item["largura"] * fator, 4)
        if item["altura"] is not None:
            item["altura_m"] = round(item["altura"] * fator, 4)

        dados.append(item)

    return dados


def ler_planilha(caminho: Union[str, pathlib.Path]) -> List[Dict[str, Any]]:
    """
    Lê uma planilha nos formatos .csv, .xlsx ou .xlsm de forma resiliente.
    """
    caminho_p = pathlib.Path(caminho)
    if not caminho_p.exists():
        raise FileNotFoundError(f"Arquivo de planilha não encontrado: {caminho_p}")

    sufixo = caminho_p.suffix.lower()
    if sufixo in (".xlsx", ".xlsm"):
        return ler_xlsx(caminho_p)
    elif sufixo in (".csv", ".txt", ".tsv"):
        return ler_csv(caminho_p)
    else:
        # Tenta ler como CSV por padrão
        try:
            return ler_csv(caminho_p)
        except Exception:
            return ler_xlsx(caminho_p)


@dataclass
class ResultadoMatch:
    """Resultado de matching para um arquivo."""
    arquivo_nome: str
    arquivo_caminho: Optional[pathlib.Path] = None
    linha_planilha: Optional[Dict[str, Any]] = None
    tipo_match: str = "nao_encontrado"  # 'exato', 'sem_extensao', 'substring', 'nao_encontrado'
    confianca: float = 0.0              # 1.0, 0.9, 0.7, 0.0
    detalhes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arquivo_nome": self.arquivo_nome,
            "arquivo_caminho": str(self.arquivo_caminho) if self.arquivo_caminho else None,
            "linha_planilha": self.linha_planilha,
            "tipo_match": self.tipo_match,
            "confianca": self.confianca,
            "detalhes": self.detalhes,
        }


def _normalizar_slug(texto: str) -> str:
    """Normaliza nome para correspondência flexível."""
    if not texto:
        return ""
    t = remover_acentos(texto).lower().strip()
    # Substitui separadores comuns por espaço
    t = re.sub(r'[\s._\-]+', ' ', t)
    return t.strip()


def cruzar_arquivos_com_planilha(
    arquivos: List[Union[str, pathlib.Path]],
    linhas_planilha: List[Dict[str, Any]],
) -> List[ResultadoMatch]:
    """
    Algoritmo de cruzamento em cascata entre arquivos e linhas de planilha:
    1. Correspondência exata de nome completo de arquivo (sensível ou insensível a maiúsculas).
    2. Correspondência sem extensão (ex: 'banner_loja' == 'banner_loja.pdf').
    3. Correspondência por substring de stem (ex: planilha 'banner_loja' contida em '01_banner_loja_2x1.pdf').
    4. Não encontrado (quando não há correspondência plausível).
    """
    resultados: List[ResultadoMatch] = []
    linhas_usadas: set[int] = set()

    # Prepara lista de arquivos como pathlib.Path
    caminhos: List[pathlib.Path] = []
    for a in arquivos:
        if isinstance(a, pathlib.Path):
            caminhos.append(a)
        else:
            caminhos.append(pathlib.Path(str(a)))

    for cam in caminhos:
        nome_completo = cam.name
        stem_arquivo = cam.stem
        slug_arquivo = _normalizar_slug(stem_arquivo)

        match_encontrado: Optional[ResultadoMatch] = None

        # 1. Correspondência exata com nome_completo
        for idx, linha in enumerate(linhas_planilha):
            arq_plan = str(linha.get("arquivo") or "").strip()
            if not arq_plan:
                continue

            if arq_plan.lower() == nome_completo.lower():
                match_encontrado = ResultadoMatch(
                    arquivo_nome=nome_completo,
                    arquivo_caminho=cam,
                    linha_planilha=linha,
                    tipo_match="exato",
                    confianca=1.0,
                    detalhes="Correspondência exata de nome de arquivo",
                )
                linhas_usadas.add(idx)
                break

        if match_encontrado:
            resultados.append(match_encontrado)
            continue

        # 2. Correspondência sem extensão
        for idx, linha in enumerate(linhas_planilha):
            arq_plan = str(linha.get("arquivo") or "").strip()
            if not arq_plan:
                continue

            stem_plan = pathlib.Path(arq_plan).stem
            if stem_plan.lower() == stem_arquivo.lower() or _normalizar_slug(stem_plan) == slug_arquivo:
                match_encontrado = ResultadoMatch(
                    arquivo_nome=nome_completo,
                    arquivo_caminho=cam,
                    linha_planilha=linha,
                    tipo_match="sem_extensao",
                    confianca=0.9,
                    detalhes="Correspondência sem extensão",
                )
                linhas_usadas.add(idx)
                break

        if match_encontrado:
            resultados.append(match_encontrado)
            continue

        # 3. Correspondência por substring
        melhor_match = None
        melhor_tam = 0
        melhor_idx = -1

        for idx, linha in enumerate(linhas_planilha):
            arq_plan = str(linha.get("arquivo") or "").strip()
            if not arq_plan:
                continue

            slug_plan = _normalizar_slug(pathlib.Path(arq_plan).stem)
            if len(slug_plan) < 3 and len(slug_arquivo) < 3:
                continue

            if slug_plan in slug_arquivo or slug_arquivo in slug_plan:
                tam_comum = min(len(slug_plan), len(slug_arquivo))
                if tam_comum > melhor_tam:
                    melhor_tam = tam_comum
                    melhor_match = linha
                    melhor_idx = idx

        if melhor_match and melhor_tam >= 3:
            resultados.append(
                ResultadoMatch(
                    arquivo_nome=nome_completo,
                    arquivo_caminho=cam,
                    linha_planilha=melhor_match,
                    tipo_match="substring",
                    confianca=0.7,
                    detalhes=f"Correspondência por substring ('{melhor_match.get('arquivo')}')",
                )
            )
            linhas_usadas.add(melhor_idx)
            continue

        # 4. Não encontrado
        resultados.append(
            ResultadoMatch(
                arquivo_nome=nome_completo,
                arquivo_caminho=cam,
                linha_planilha=None,
                tipo_match="nao_encontrado",
                confianca=0.0,
                detalhes="Nenhuma linha correspondente na planilha",
            )
        )

    return resultados
