"""
Ponto de entrada do programa.

  - Sem argumentos (ex: clicando duas vezes / rodando "python main.py"):
    abre a interface gráfica.
  - Com --cliente, --gerente e --produtor: roda no modo linha de
    comando, do jeito que a versão anterior do script funcionava
    (útil para automatizar em outro programa ou script no futuro).
"""
import argparse
import sys

from config import carregar_config
from processamento import processar_etiquetas


def parse_argumentos():
    parser = argparse.ArgumentParser(
        description="Gera etiquetas separadas por categoria a partir de PDFs de uma pasta de "
                    "entrada, e monta um PDF unificado. Rode sem argumentos para abrir a "
                    "interface gráfica."
    )
    parser.add_argument(
        "--pasta-entrada", dest="pasta_entrada", default="entrada",
        help="Pasta com os PDFs de origem (padrão: 'entrada')",
    )
    parser.add_argument("--cliente", dest="cliente", help="Nome do cliente")
    parser.add_argument("--gerente", dest="gerente", help="Nome do gerente operacional")
    parser.add_argument("--produtor", dest="produtor", help="Nome do produtor responsável")
    parser.add_argument(
        "--cli", action="store_true",
        help="Força o modo linha de comando (normalmente já é detectado automaticamente "
             "quando --cliente/--gerente/--produtor são informados).",
    )
    return parser.parse_args()


def rodar_cli(args):
    if not (args.cliente and args.gerente and args.produtor):
        print("Modo linha de comando requer --cliente, --gerente e --produtor.")
        print("Exemplo: python main.py --cliente \"Fulano\" --gerente \"Ciclano\" --produtor \"Beltrano\"")
        sys.exit(1)

    config = carregar_config()
    resultado = processar_etiquetas(
        args.pasta_entrada, args.cliente, args.gerente, args.produtor, config,
    )
    if resultado is None:
        print("\n❌ Processamento não concluído — veja as mensagens acima.")
        sys.exit(1)
    print(f"\n✅ Concluído. Arquivos em: {resultado['pasta_saida']}")


def rodar_gui():
    from gui import JanelaPrincipal
    app = JanelaPrincipal()
    app.mainloop()


if __name__ == "__main__":
    try:
        args = parse_argumentos()
        if args.cliente or args.gerente or args.produtor or args.cli:
            rodar_cli(args)
        else:
            rodar_gui()
    except SystemExit:
        raise
    except Exception as e:
        # Isso evita que a janela do terminal feche sozinha (por exemplo,
        # quando o programa é aberto com duplo clique num .bat) antes de
        # dar tempo de ler a mensagem de erro.
        print(f"\n❌ Erro inesperado: {e}")
        input("Pressione Enter para sair...")
        sys.exit(1)
