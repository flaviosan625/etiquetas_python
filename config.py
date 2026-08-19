"""
Carrega e salva o config.json — onde ficam as medidas de rolos/chapas,
os sinônimos de categoria, os erros de digitação de unidade conhecidos,
a ordem das seções no PDF unificado, e os últimos gerente/produtor
usados.

A ideia é que tudo que pode mudar com o tempo (uma medida de rolo nova,
uma categoria de material nova, um novo erro de digitação comum) fique
aqui, editável pela tela de configurações do programa — sem precisar
mexer em código.
"""
import copy
import json
import pathlib

BASE_DIR = pathlib.Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

CONFIG_PADRAO = {
    "materiais": {
        "LONA": {"tipo": "rolo", "largura_cm": 320, "comprimento_cm": 5000},
        "ADESIVO": {"tipo": "rolo", "largura_cm": 127, "comprimento_cm": 5000},
        "PS": {
            "tipo": "chapa", "largura_cm": 200, "comprimento_cm": 100,
            "variantes": [
                {"espessura": "1MM", "cor": "BRANCO"}, {"espessura": "1MM", "cor": "PRETO"},
                {"espessura": "2MM", "cor": "BRANCO"}, {"espessura": "2MM", "cor": "PRETO"},
                {"espessura": "3MM", "cor": "BRANCO"}, {"espessura": "3MM", "cor": "PRETO"},
            ],
        },
        "ACRILICO": {
            "tipo": "chapa", "largura_cm": 300, "comprimento_cm": 200,
            "variantes": [
                {"espessura": e, "cor": c}
                for e in ["2MM", "3MM", "4MM", "5MM", "6MM", "8MM", "10MM"]
                for c in ["CRISTAL", "LEITOSO"]
            ],
        },
        "PVC": {
            "tipo": "chapa", "largura_cm": 122, "comprimento_cm": 244,
            "variantes": [
                {"espessura": "10MM", "cor": "BRANCO"}, {"espessura": "10MM", "cor": "PRETO"},
                {"espessura": "20MM", "cor": "BRANCO"}, {"espessura": "20MM", "cor": "PRETO"},
            ],
        },
        "MDF": {
            "tipo": "chapa", "largura_cm": 185, "comprimento_cm": 270,
            "variantes": [
                {"espessura": "6MM"}, {"espessura": "9MM"}, {"espessura": "15MM"}, {"espessura": "18MM"},
                {"espessura": "6MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
                {"espessura": "9MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
                {"espessura": "15MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
                {"espessura": "18MM", "cor": "VERDE", "rotulo": "MDF HIDRO"},
            ],
        },
    },
    # Sinônimos: se o nome do arquivo contiver a chave, é tratado como a
    # categoria do valor (que precisa existir em "materiais").
    "sinonimos_categoria": {
        "VINIL": "ADESIVO",
        "XPS": "PVC",
        "ACRÍLICO": "ACRILICO",
    },
    # Erros de digitação comuns no lugar da unidade de medida (MM/CM/M).
    # "XM" normalmente é "CM" digitado errado (X e C são vizinhos no
    # teclado). Adicione mais entradas aqui se aparecerem outros casos.
    "typos_unidade": {
        "XM": "CM",
    },
    # Ordem fixa em que as categorias devem aparecer no PDF unificado.
    # Categorias que existirem em "materiais" mas não estiverem nessa
    # lista ainda aparecem no unificado (no final, automaticamente) —
    # isso evita que uma seção "suma" silenciosamente por ter sido
    # esquecida aqui.
    "ordem_unificado": ["LONA", "ADESIVO", "PVC", "PS", "MDF", "ACRILICO"],
    "ultimo_gerente": "",
    "ultimo_produtor": "",
}


def carregar_config():
    """
    Carrega o config.json. Se não existir, cria um novo com os valores
    padrão. Se existir mas estiver faltando alguma chave (por exemplo,
    de uma versão antiga do arquivo), completa com o valor padrão sem
    apagar o que já estava configurado. Se o arquivo estiver corrompido
    (JSON inválido), guarda uma cópia de segurança e recria do zero, em
    vez de travar o programa.
    """
    if not CONFIG_PATH.exists():
        config_novo = copy.deepcopy(CONFIG_PADRAO)
        salvar_config(config_novo)
        return config_novo

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        backup = CONFIG_PATH.with_suffix(".json.bak")
        try:
            CONFIG_PATH.replace(backup)
        except OSError:
            pass
        config_novo = copy.deepcopy(CONFIG_PADRAO)
        salvar_config(config_novo)
        return config_novo

    alterado = False
    for chave, valor_padrao in CONFIG_PADRAO.items():
        if chave not in config:
            config[chave] = copy.deepcopy(valor_padrao)
            alterado = True
    if alterado:
        salvar_config(config)

    return config


def salvar_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def atualizar_ultimo_uso(config, gerente, produtor):
    """Atualiza e já salva o último gerente/produtor usados."""
    config["ultimo_gerente"] = gerente
    config["ultimo_produtor"] = produtor
    salvar_config(config)
    return config
