"""
Módulo de Análise Sintática e Desacoplamento de Regras de Nomenclatura (ISSUE-08).

Permite configurar perfis encadeados com prioridade para identificar
metadados (quantidade, medidas, material, categoria, variante, cliente,
OS, descrição) a partir de nomes de arquivos.

Suporta:
- Templates declarativos simples com tokens amigáveis:
  {QTD}, {MATERIAL}, {LARG}, {ALT}, {UNIDADE}, {CLIENTE}, {DESCRICAO}, {OS}, {ESPESSURA}.
- Conversão automática de templates para Expressões Regulares com Named Groups.
- Perfis customizados por Regex pura.
- Perfil flexível universal (fallback) compatível com convenções legadas.
- Exportação e importação de perfis para persistência no config.json.
- Status "PRONTO" ou "PENDENTE_TRIAGEM" resiliente a falhas (sem exceções não tratadas).
"""
import copy
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Union

from dimensoes import (
    FATORES_UNIDADE,
    extrair_dimensoes,
    extrair_quantidade,
    identificar_categoria,
    identificar_variante,
    nome_sem_prefixo_reconhecido,
    remover_palavra,
)

# Tokens declarativos reconhecidos no conversor de templates
TOKENS_DECLARATIVOS = {
    "QTD",
    "MATERIAL",
    "LARG",
    "ALT",
    "UNIDADE",
    "CLIENTE",
    "DESCRICAO",
    "OS",
    "ESPESSURA",
}

# Regex dos tokens individuais para grupos nomeados
MAPA_TOKENS_REGEX = {
    "QTD": r'(?P<qtd>\d+)',
    "LARG": r'(?P<larg>\d+(?:[.,]\d+)?)',
    "ALT": r'(?P<alt>\d+(?:[.,]\d+)?)',
    "UNIDADE": r'(?P<unidade>METROS|METRO|MTS|MTR|MM|CM|MT|M|XM|[A-Za-z]+)?',
    "OS": r'(?P<os>[A-Za-z0-9_-]+?)',
    "CLIENTE": r'(?P<cliente>.+?)',
    "MATERIAL": r'(?P<material>.+?)',
    "DESCRICAO": r'(?P<descricao>.+?)',
    "ESPESSURA": r'(?P<espessura>\d+(?:[.,]\d+)?\s*(?:MM|mm)?)',
}


@dataclass
class ResultadoParse:
    """Resultado estruturado da análise sintática do nome de arquivo."""
    sucesso: bool
    qtd: int = 1
    largura_m: Optional[float] = None
    altura_m: Optional[float] = None
    unidade_original: str = "M"
    material: Optional[str] = None
    categoria: Optional[str] = None
    variante: Optional[Dict[str, str]] = None
    cliente: Optional[str] = None
    descricao: Optional[str] = None
    os: Optional[str] = None
    perfil_usado: Optional[str] = None
    status: str = "PRONTO"  # "PRONTO" ou "PENDENTE_TRIAGEM"

    @property
    def area_m2(self) -> float:
        if self.largura_m is not None and self.altura_m is not None:
            return round(self.largura_m * self.altura_m, 4)
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sucesso": self.sucesso,
            "qtd": self.qtd,
            "largura_m": self.largura_m,
            "altura_m": self.altura_m,
            "area_m2": self.area_m2,
            "unidade_original": self.unidade_original,
            "material": self.material,
            "categoria": self.categoria,
            "variante": self.variante,
            "cliente": self.cliente,
            "descricao": self.descricao,
            "os": self.os,
            "perfil_usado": self.perfil_usado,
            "status": self.status,
        }

    def as_dimensao_dict(self) -> Optional[Dict[str, Any]]:
        """Retorna formato compatível com extrair_dimensoes() de dimensoes.py."""
        if not self.sucesso or self.largura_m is None or self.altura_m is None:
            return None
        return {
            "largura_m": self.largura_m,
            "altura_m": self.altura_m,
            "area_m2": self.area_m2,
            "unidade_usada": self.unidade_original,
            "medida_bruta": f"{self.largura_m}x{self.altura_m}",
            "unidade_corrigida": False,
            "unidade_bruta": self.unidade_original,
            "origem": "nome",
        }


def converter_template_para_regex(template: str) -> str:
    """
    Converte um template declarativo com tokens ({QTD}, {MATERIAL}, etc.)
    em uma expressão regular com Named Groups (?P<grupo>...).

    Exemplos de templates suportados:
    - "{QTD}UN_{MATERIAL}_{LARG}x{ALT}{UNIDADE}_{DESCRICAO}"
    - "OS{OS}_{CLIENTE}_{MATERIAL}_{LARG}x{ALT}{UNIDADE}"
    - "{CLIENTE}_{MATERIAL}_{LARG}x{ALT}{UNIDADE}"
    - "{QTD}UN {MATERIAL} {LARG}x{ALT}{UNIDADE} {DESCRICAO}"
    - "[_{DESCRICAO}]" (blocos opcionais com colchetes)
    """
    raw = template.strip()

    # 1. Tratar blocos opcionais [...] -> (?:...)?
    raw = re.sub(r'\[([^\]]+)\]', r'(?:\1)?', raw)

    # 2. Dividir em tokens {TOKEN} e partes literais/separadores
    partes = re.split(r'(\{[\w]+\})', raw)
    resultado_partes: List[str] = []
    i = 0
    while i < len(partes):
        p = partes[i]
        if not p:
            i += 1
            continue

        m_tok = re.fullmatch(r'\{([A-Za-z]+)\}', p)
        if m_tok:
            tok = m_tok.group(1).upper()

            # Checar se é {QTD} seguido de literal que começa com UN
            if tok == "QTD" and i + 1 < len(partes) and re.match(r'^\s*UN(?![A-Za-z])', partes[i + 1], re.IGNORECASE):
                resultado_partes.append(r'(?P<qtd>\d+)(?:[\s._\-]*)?UN(?![A-Za-z])')
                resto_literal = re.sub(r'^\s*UN', '', partes[i + 1], flags=re.IGNORECASE)
                partes[i + 1] = resto_literal
                i += 1
                continue

            # Checar se é {LARG} seguido de x e {ALT}
            if tok == "LARG" and i + 2 < len(partes):
                prox_lit = partes[i + 1]
                prox_tok = re.fullmatch(r'\{([A-Za-z]+)\}', partes[i + 2])
                if prox_tok and prox_tok.group(1).upper() == "ALT" and re.fullmatch(r'[\s._\-]*[xX][\s._\-]*', prox_lit):
                    resultado_partes.append(r'(?P<larg>\d+(?:[.,]\d+)?)(?:[\s._\-]*)?[xX](?:[\s._\-]*)?(?P<alt>\d+(?:[.,]\d+)?)')
                    i += 3
                    continue

            # Checar se é {DESCRICAO} no final precedido por separador (torna o bloco de descrição opcional)
            if tok == "DESCRICAO" and (i == len(partes) - 1 or (i == len(partes) - 2 and not partes[-1])):
                if resultado_partes and resultado_partes[-1] in (r'[\s._\-]+', r'\s*[._\-]\s*'):
                    resultado_partes.pop()
                    resultado_partes.append(r'(?:[\s._\-]+(?P<descricao>.+?))?')
                    i += 1
                    continue

            reg = MAPA_TOKENS_REGEX.get(tok, rf'(?P<{tok.lower()}>.+?)')
            resultado_partes.append(reg)
            i += 1
        else:
            # Parte literal / separador
            if re.fullmatch(r'_+', p):
                # Se estiver entre {CLIENTE} e {MATERIAL}, usa \s*[._\-]\s* para preservar espaços dentro de nomes
                ant_e_cliente = (i > 0 and partes[i - 1].upper() == "{CLIENTE}")
                dep_e_material = (i + 1 < len(partes) and partes[i + 1].upper() == "{MATERIAL}")
                ant_e_material = (i > 0 and partes[i - 1].upper() == "{MATERIAL}")
                dep_e_cliente = (i + 1 < len(partes) and partes[i + 1].upper() == "{CLIENTE}")

                if (ant_e_cliente and dep_e_material) or (ant_e_material and dep_e_cliente):
                    resultado_partes.append(r'\s*[._\-]\s*')
                else:
                    resultado_partes.append(r'[\s._\-]+')
            elif re.fullmatch(r'\s+-\s+', p):
                resultado_partes.append(r'[\s._\-]+')
            elif re.fullmatch(r'\s+', p):
                resultado_partes.append(r'\s+')
            else:
                resultado_partes.append(re.escape(p))
            i += 1

    padrao = "".join(resultado_partes)
    if not padrao.startswith('^'):
        padrao = r'^(?:\[[^\]]+\][\s._\-]*)?' + padrao
    if not padrao.endswith('$'):
        padrao = padrao + r'(?:\.[a-zA-Z0-9]{2,5})?$'

    return padrao


@dataclass
class PerfilRegra:
    """Perfil declarativo de nomenclatura."""
    nome: str
    descricao: str = ""
    prioridade: int = 100
    tipo: str = "template"  # "template", "regex", "flexivel"
    template: Optional[str] = None
    regex: Optional[str] = None
    ativo: bool = True
    _regex_compilado: Optional[re.Pattern] = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        self.compilar()

    def compilar(self):
        """Compila a regex do perfil conforme seu tipo."""
        if self.tipo == "template" and self.template:
            self.regex = converter_template_para_regex(self.template)
            self._regex_compilado = re.compile(self.regex, re.IGNORECASE)
        elif self.tipo == "regex" and self.regex:
            self._regex_compilado = re.compile(self.regex, re.IGNORECASE)
        else:
            self._regex_compilado = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "nome": self.nome,
            "descricao": self.descricao,
            "prioridade": self.prioridade,
            "tipo": self.tipo,
            "ativo": self.ativo,
        }
        if self.template is not None:
            d["template"] = self.template
        if self.regex is not None:
            d["regex"] = self.regex
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PerfilRegra":
        return cls(
            nome=d["nome"],
            descricao=d.get("descricao", ""),
            prioridade=d.get("prioridade", 100),
            tipo=d.get("tipo", "template"),
            template=d.get("template"),
            regex=d.get("regex"),
            ativo=d.get("ativo", True),
        )


# Perfis padrão embutidos de fábrica
PERFIS_PADRAO_NOMENCLATURA: List[Dict[str, Any]] = [
    {
        "nome": "comunicacao_visual_classico",
        "descricao": "Padrão clássico: Quantidade, Material, Medidas e Descrição",
        "prioridade": 10,
        "tipo": "template",
        "template": "{QTD}UN_{MATERIAL}_{LARG}x{ALT}{UNIDADE}_{DESCRICAO}",
        "ativo": True,
    },
    {
        "nome": "erp_os",
        "descricao": "Padrão ERP: OS, Cliente, Material e Medida (ex: OS1234_CLIENTE_MATERIAL_2x1M)",
        "prioridade": 20,
        "tipo": "template",
        "template": "OS{OS}_{CLIENTE}_{MATERIAL}_{LARG}x{ALT}{UNIDADE}",
        "ativo": True,
    },
    {
        "nome": "padrao_flexivel",
        "descricao": "Padrão flexível: busca dimensões e material em qualquer posição",
        "prioridade": 30,
        "tipo": "flexivel",
        "ativo": True,
    },
]


class ParserRegrasNomes:
    """
    Engine de análise sintática baseada em perfis encadeados com prioridade.
    Permite desacoplar regras de nomenclatura e tolerar convenções variadas
    de clientes e ERPs de forma configurável.
    """

    _instancia_global: Optional["ParserRegrasNomes"] = None

    def __init__(
        self,
        config: Optional[dict] = None,
        perfis: Optional[List[Union[PerfilRegra, dict]]] = None,
    ):
        self._config = config
        self.perfis: List[PerfilRegra] = []

        if perfis is not None:
            for p in perfis:
                self.adicionar_perfil(p)
        elif config and "perfis_nomenclatura" in config:
            self.importar_regras(config["perfis_nomenclatura"])
        else:
            self.importar_regras(PERFIS_PADRAO_NOMENCLATURA)

    @classmethod
    def obter_instancia(cls, config: Optional[dict] = None) -> "ParserRegrasNomes":
        """Retorna instância singleton ou atualizada com config."""
        if config is not None:
            return cls(config=config)
        if cls._instancia_global is None:
            cls._instancia_global = cls()
        return cls._instancia_global

    def adicionar_perfil(self, perfil: Union[PerfilRegra, dict]) -> PerfilRegra:
        """Adiciona ou atualiza um perfil na lista encadeada."""
        if isinstance(perfil, dict):
            obj = PerfilRegra.from_dict(perfil)
        else:
            obj = perfil

        for i, p in enumerate(self.perfis):
            if p.nome == obj.nome:
                self.perfis[i] = obj
                return obj

        self.perfis.append(obj)
        return obj

    def adicionar_perfil_template(
        self,
        nome: str,
        template: str,
        prioridade: int = 50,
        descricao: str = "",
        ativo: bool = True,
    ) -> PerfilRegra:
        """Cria e adiciona um perfil baseado em template declarativo."""
        perfil = PerfilRegra(
            nome=nome,
            template=template,
            prioridade=prioridade,
            tipo="template",
            descricao=descricao,
            ativo=ativo,
        )
        return self.adicionar_perfil(perfil)

    def adicionar_perfil_regex(
        self,
        nome: str,
        regex: str,
        prioridade: int = 50,
        descricao: str = "",
        ativo: bool = True,
    ) -> PerfilRegra:
        """Cria e adiciona um perfil baseado em Regex pura."""
        perfil = PerfilRegra(
            nome=nome,
            regex=regex,
            prioridade=prioridade,
            tipo="regex",
            descricao=descricao,
            ativo=ativo,
        )
        return self.adicionar_perfil(perfil)

    def obter_perfil(self, nome: str) -> Optional[PerfilRegra]:
        for p in self.perfis:
            if p.nome == nome:
                return p
        return None

    def remover_perfil(self, nome: str) -> bool:
        tam_antes = len(self.perfis)
        self.perfis = [p for p in self.perfis if p.nome != nome]
        return len(self.perfis) < tam_antes

    def exportar_regras(self) -> List[Dict[str, Any]]:
        """Exporta perfis em formato serializável para JSON."""
        return [p.to_dict() for p in self.perfis]

    def importar_regras(self, regras: List[Dict[str, Any]]):
        """Importa lista de perfis serializados."""
        self.perfis = [PerfilRegra.from_dict(r) for r in regras]

    def parsear(self, nome_arquivo: str, config: Optional[dict] = None) -> ResultadoParse:
        """
        Executa a análise sintática de nome_arquivo testando os perfis ativos
        em ordem crescente de prioridade (menor número = maior prioridade).

        Se nenhum perfil casar ou faltarem medidas essenciais (largura e altura),
        retorna ResultadoParse com status="PENDENTE_TRIAGEM" e sucesso=False
        sem levantar exceção.
        """
        cfg = config or self._config or {}
        materiais = cfg.get("materiais", {})
        sinonimos = cfg.get("sinonimos_categoria", {})
        typos_unidade = cfg.get("typos_unidade", {})

        nome_str = str(nome_arquivo or "").strip()
        if not nome_str:
            return ResultadoParse(sucesso=False, status="PENDENTE_TRIAGEM")

        perfis_ordenados = sorted(
            [p for p in self.perfis if p.ativo],
            key=lambda p: p.prioridade,
        )

        for perfil in perfis_ordenados:
            try:
                res = self._executar_perfil(perfil, nome_str, materiais, sinonimos, typos_unidade)
                if res is not None and res.sucesso:
                    return res
            except Exception:
                continue

        # Fallback definitivo quando todos os perfis falharem
        qtd_padrao, _ = extrair_quantidade(nome_str)
        cat_tentativa, _ = identificar_categoria(nome_str.upper(), materiais, sinonimos)
        return ResultadoParse(
            sucesso=False,
            qtd=qtd_padrao,
            largura_m=None,
            altura_m=None,
            unidade_original="M",
            material=cat_tentativa,
            categoria=cat_tentativa,
            variante=None,
            cliente=None,
            descricao=None,
            os=None,
            perfil_usado=None,
            status="PENDENTE_TRIAGEM",
        )

    def _executar_perfil(
        self,
        perfil: PerfilRegra,
        nome_str: str,
        materiais: dict,
        sinonimos: dict,
        typos_unidade: dict,
    ) -> Optional[ResultadoParse]:
        """Tenta casamento de um perfil específico."""
        if perfil.tipo == "flexivel":
            return self._executar_flexivel(perfil, nome_str, materiais, sinonimos, typos_unidade)

        if not perfil._regex_compilado:
            return None

        # Tenta casar contra o stem (sem extensão) primeiro, ou contra o nome_str completo
        stem = re.sub(r'\.[a-zA-Z0-9]{2,5}$', '', nome_str)
        m = perfil._regex_compilado.search(stem) or perfil._regex_compilado.search(nome_str)
        if not m:
            return None

        grupos = m.groupdict()

        # Extrair quantidade
        qtd_str = grupos.get("qtd")
        if qtd_str and qtd_str.isdigit():
            qtd = int(qtd_str)
        else:
            qtd, _ = extrair_quantidade(nome_str)

        # Extrair dimensões
        larg_str = grupos.get("larg")
        alt_str = grupos.get("alt")
        if not larg_str or not alt_str:
            return None

        try:
            v_larg = float(larg_str.replace(',', '.'))
            v_alt = float(alt_str.replace(',', '.'))
        except ValueError:
            return None

        if v_larg <= 0 or v_alt <= 0:
            return None

        # Tratar unidade
        unidade_raw = (grupos.get("unidade") or "").upper().strip()
        if not unidade_raw:
            unidade_usada = "CM"  # Padrão da indústria de CV
        elif unidade_raw in typos_unidade:
            unidade_usada = typos_unidade[unidade_raw]
        elif unidade_raw in FATORES_UNIDADE:
            unidade_usada = unidade_raw
        else:
            unidade_usada = "CM"

        fator = FATORES_UNIDADE.get(unidade_usada, 0.01)
        largura_m = v_larg * fator
        altura_m = v_alt * fator

        # Metadados adicionais
        material_extraido = grupos.get("material")
        if material_extraido:
            material_extraido = material_extraido.strip(" ._-")

        cliente_extraido = grupos.get("cliente")
        if cliente_extraido:
            cliente_extraido = cliente_extraido.strip(" ._-")

        descricao_extraida = grupos.get("descricao")
        if descricao_extraida:
            desc_strip = descricao_extraida.strip(" ._-")
            if desc_strip.lower() in ("pdf", "tif", "tiff", "jpg", "jpeg", "png", "eps", "cdr", "ai"):
                descricao_extraida = None
            else:
                descricao_extraida = desc_strip

        os_extraida = grupos.get("os")
        if os_extraida:
            os_extraida = os_extraida.strip(" ._-")

        # Identificação de categoria e variante usando config
        texto_busca_cat = (material_extraido or nome_str).upper()
        cat, _ = identificar_categoria(texto_busca_cat, materiais, sinonimos)
        if not cat and material_extraido:
            cat, _ = identificar_categoria(nome_str.upper(), materiais, sinonimos)

        variante = None
        if cat and cat in materiais:
            variante = identificar_variante(nome_str, materiais[cat].get("variantes", []))

        return ResultadoParse(
            sucesso=True,
            qtd=qtd,
            largura_m=largura_m,
            altura_m=altura_m,
            unidade_original=unidade_usada,
            material=material_extraido or cat,
            categoria=cat,
            variante=variante,
            cliente=cliente_extraido,
            descricao=descricao_extraida,
            os=os_extraida,
            perfil_usado=perfil.nome,
            status="PRONTO",
        )

    def _executar_flexivel(
        self,
        perfil: PerfilRegra,
        nome_str: str,
        materiais: dict,
        sinonimos: dict,
        typos_unidade: dict,
    ) -> Optional[ResultadoParse]:
        """Implementação do perfil universal flexível (dimensões LxA em qualquer posição)."""
        dim = extrair_dimensoes(nome_str, typos_unidade)
        if not dim or dim["largura_m"] <= 0 or dim["altura_m"] <= 0:
            return None

        qtd, _ = extrair_quantidade(nome_str)
        cat, _ = identificar_categoria(nome_str.upper(), materiais, sinonimos)

        variante = None
        if cat and cat in materiais:
            variante = identificar_variante(nome_str, materiais[cat].get("variantes", []))

        descricao = nome_sem_prefixo_reconhecido(nome_str, typos_unidade)
        if cat and descricao:
            descricao = remover_palavra(descricao, cat).strip(" ._-")

        if descricao and descricao.lower() in ("pdf", "tif", "tiff", "jpg", "jpeg", "png", "eps", "cdr", "ai"):
            descricao = None

        # Tentar extrair OS se houver padrão OS\d+
        m_os = re.search(r'(?:OS|PEDIDO)[\s._\-]*(\d+)', nome_str, re.IGNORECASE)
        os_val = m_os.group(1) if m_os else None

        return ResultadoParse(
            sucesso=True,
            qtd=qtd,
            largura_m=dim["largura_m"],
            altura_m=dim["altura_m"],
            unidade_original=dim["unidade_usada"],
            material=cat,
            categoria=cat,
            variante=variante,
            cliente=None,
            descricao=descricao or None,
            os=os_val,
            perfil_usado=perfil.nome,
            status="PRONTO",
        )
