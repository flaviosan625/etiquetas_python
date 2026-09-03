"""
Ponte entre o sistema de etiquetas e o RIP da Docan (PrintFactory) via
hot folder — a automação mais simples possível: só copiar o arquivo
pronto pra uma pasta que o PrintFactory fica vigiando e importa
sozinho (visto configurado no BYHX PrintSetting, aba Preference,
com "Print Immediately" já marcado).

Essa primeira versão manda só o arquivo puro (sem XML de job ticket
— copiar/cortar, cores, prioridade), que é o que a maioria dos hot
folder de RIP aceita por padrão, importando com as configurações já
salvas na fila. O formato exato do XML (se formos usar depois pra
controlar cópias/prioridade) só fica confirmado depois da instalação
da máquina (2026-09-07/08 — ver "Software necessario - Automacao
Docan R5200.pdf", seção 5) — não dá pra adivinhar o schema sem ver a
conta/ferramenta real.
"""
import pathlib
import shutil

# Caminho real da hot folder só sai confirmado na instalação da Docan
# (segunda-feira) — preencher aqui (ou passar 'pasta_hot_folder' em
# cada chamada) assim que o técnico informar.
PASTA_HOT_FOLDER_PADRAO = None


def enviar_para_hot_folder(caminho_arquivo, pasta_hot_folder=None):
    """
    Copia 'caminho_arquivo' pra dentro da hot folder do PrintFactory —
    NUNCA move: o original do pedido continua intacto na pasta de
    saída de sempre, essa cópia é só o "envio" pra fila de impressão.
    """
    pasta_str = pasta_hot_folder or PASTA_HOT_FOLDER_PADRAO
    if not pasta_str:
        raise RuntimeError(
            "Hot folder da Docan ainda não configurada — preencha "
            "PASTA_HOT_FOLDER_PADRAO em printfactory.py (ou passe "
            "'pasta_hot_folder') com o caminho real depois da "
            "instalação de segunda-feira."
        )

    pasta = pathlib.Path(pasta_str)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Hot folder não encontrada: {pasta}")

    origem = pathlib.Path(caminho_arquivo)
    if not origem.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {origem}")

    destino = pasta / origem.name
    shutil.copy2(origem, destino)
    return destino
