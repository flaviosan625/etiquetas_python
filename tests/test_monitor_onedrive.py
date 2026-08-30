import sys
import pathlib
import time
from datetime import datetime

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import os

from monitor_onedrive import (
    _deve_ignorar, _mensagem_evento, _mensagem_movido, _Handler, EstadoVigia, gerar_relatorio_atividade,
)


def test_ignora_arquivo_temporario_do_office_e_do_download():
    assert _deve_ignorar(r"C:\pasta\~$relatorio.docx")
    assert _deve_ignorar(r"C:\pasta\arte.pdf.crdownload")
    assert _deve_ignorar(r"C:\pasta\video.tmp")


def test_nao_ignora_arquivo_normal():
    assert not _deve_ignorar(r"C:\pasta\1UN LONA 2,00X1,00M_cliente.pdf")


def test_mensagem_evento_mostra_caminho_relativo_a_pasta_raiz():
    raiz = pathlib.Path(r"C:\Users\flavi\OneDrive\UNYCOMUNICACAO\EVENTOS")
    caminho = raiz / "Cliente X" / "arte.pdf"
    msg = _mensagem_evento("criado", str(caminho), raiz)
    assert msg == "Novo arquivo: Cliente X\\arte.pdf" or msg == "Novo arquivo: Cliente X/arte.pdf"


def test_mensagem_movido_mostra_origem_e_destino():
    raiz = pathlib.Path(r"C:\Users\flavi\OneDrive\UNYCOMUNICACAO\EVENTOS")
    origem = raiz / "rascunho.pdf"
    destino = raiz / "Cliente X" / "final.pdf"
    msg = _mensagem_movido(str(origem), str(destino), raiz)
    assert "rascunho.pdf" in msg
    assert "final.pdf" in msg


def test_debounce_suprime_avisos_repetidos_da_mesma_gravacao():
    """
    O SO costuma disparar vários eventos (criado + modificado, mais de
    uma vez) pra UMA gravação de arquivo só — sem debounce, isso vira
    notificação repetida sobre a mesma mudança.
    """
    avisos = []
    relogio = iter([0.0, 0.1, 0.3, 1.0, 5.0])  # 4 eventos rápidos + 1 depois da janela

    handler = _Handler("C:/pasta", notificar=avisos.append, agora=lambda: next(relogio))

    for _ in range(4):
        handler._avisar("modificado", "C:/pasta/arquivo.pdf")
    # essa é depois da janela de 2s (marca 5.0 vs a última marca 1.0) — deveria avisar de novo
    handler._avisar("modificado", "C:/pasta/arquivo.pdf")

    assert len(avisos) == 2, "só o primeiro evento e o que veio depois da janela deveriam avisar"


def test_debounce_e_por_caminho_nao_global():
    avisos = []
    handler = _Handler("C:/pasta", notificar=avisos.append, agora=lambda: 0.0)

    handler._avisar("criado", "C:/pasta/a.pdf")
    handler._avisar("criado", "C:/pasta/b.pdf")

    assert len(avisos) == 2, "arquivos diferentes nunca deveriam suprimir um ao outro"


def test_arquivo_temporario_nunca_avisa_mesmo_fora_da_janela():
    avisos = []
    handler = _Handler("C:/pasta", notificar=avisos.append, agora=lambda: 0.0)
    handler._avisar("modificado", "C:/pasta/~$relatorio.docx")
    assert avisos == []


def test_vigiar_de_verdade_detecta_criacao_e_modificacao(tmp_path):
    """
    Ponta a ponta com o watchdog de verdade (Observer real), só sem
    notificação real do Windows — confirma que o evento do sistema
    operacional realmente chega até o handler.
    """
    from watchdog.observers import Observer

    avisos = []

    def notificar_fake(msg):
        avisos.append(msg)

    handler = _Handler(tmp_path, notificar=notificar_fake)
    observer = Observer()
    observer.schedule(handler, str(tmp_path), recursive=True)
    observer.start()
    try:
        time.sleep(0.3)
        (tmp_path / "arte.pdf").write_bytes(b"conteudo")
        time.sleep(1.5)
    finally:
        observer.stop()
        observer.join()

    assert any("arte.pdf" in a for a in avisos), f"esperava aviso sobre arte.pdf, veio: {avisos}"


def test_estado_vigia_liga_desliga_religa(tmp_path):
    """
    O ícone da bandeja usa EstadoVigia pra Pausar/Retomar sem fechar o
    programa — confirma que mudança só é percebida enquanto ativo, e
    que religar depois de pausar volta a perceber (o Observer do
    watchdog não pode ser reiniciado, precisa recriar por baixo).
    """
    avisos = []
    handler = _Handler(tmp_path, notificar=avisos.append)
    vigia = EstadoVigia(tmp_path, handler)

    assert not vigia.ativo
    vigia.iniciar()
    assert vigia.ativo
    time.sleep(0.3)
    (tmp_path / "a.pdf").write_bytes(b"1")
    time.sleep(1.0)

    vigia.parar()
    assert not vigia.ativo
    (tmp_path / "b.pdf").write_bytes(b"2")
    time.sleep(0.5)

    vigia.iniciar()
    time.sleep(0.3)
    (tmp_path / "c.pdf").write_bytes(b"3")
    time.sleep(1.0)
    vigia.parar()

    nomes_avisados = {pathlib.Path(a.split(": ", 1)[1]).name for a in avisos}
    assert "a.pdf" in nomes_avisados, f"deveria ter avisado sobre a.pdf (criado enquanto ativo): {avisos}"
    assert "b.pdf" not in nomes_avisados, f"não deveria avisar sobre b.pdf (criado enquanto pausado): {avisos}"
    assert "c.pdf" in nomes_avisados, f"deveria ter avisado sobre c.pdf (criado depois de religar): {avisos}"


def _tocar_arquivo_com_data(caminho, dias_atras):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"conteudo")
    momento = (time.time()) - dias_atras * 86400
    os.utime(caminho, (momento, momento))


def test_relatorio_de_hoje_so_pega_arquivo_modificado_hoje(tmp_path):
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "arte_hoje.pdf", dias_atras=0)
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "arte_ontem.pdf", dias_atras=1.2)
    _tocar_arquivo_com_data(tmp_path / "Cliente B" / "arte_velha.pdf", dias_atras=10)

    relatorio = gerar_relatorio_atividade(tmp_path, dias=1)

    assert "Cliente A" in relatorio
    assert "arte_hoje.pdf" in relatorio
    assert "arte_ontem.pdf" not in relatorio
    assert "Cliente B" not in relatorio
    assert "arte_velha.pdf" not in relatorio


def test_relatorio_da_semana_inclui_arquivo_de_ontem_mas_nao_o_antigo(tmp_path):
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "arte_hoje.pdf", dias_atras=0)
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "arte_ontem.pdf", dias_atras=1.2)
    _tocar_arquivo_com_data(tmp_path / "Cliente B" / "arte_velha.pdf", dias_atras=10)

    relatorio = gerar_relatorio_atividade(tmp_path, dias=7)

    assert "arte_hoje.pdf" in relatorio
    assert "arte_ontem.pdf" in relatorio
    assert "arte_velha.pdf" not in relatorio


def test_relatorio_ignora_arquivo_temporario(tmp_path):
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "~$rascunho.docx", dias_atras=0)
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "arte.pdf", dias_atras=0)

    relatorio = gerar_relatorio_atividade(tmp_path, dias=1)

    assert "arte.pdf" in relatorio
    assert "rascunho" not in relatorio


def test_relatorio_sem_nenhuma_mudanca_avisa_isso_claramente(tmp_path):
    _tocar_arquivo_com_data(tmp_path / "Cliente A" / "arte_velha.pdf", dias_atras=30)

    relatorio = gerar_relatorio_atividade(tmp_path, dias=1)

    assert "Nenhum arquivo modificado" in relatorio


def _tocar_arquivo_no_dia(caminho, data):
    """Como _tocar_arquivo_com_data, mas ancorado num dia-calendário exato (meio-dia), sem depender da hora atual."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(b"conteudo")
    momento = datetime.combine(data, datetime.min.time()).timestamp() + 12 * 3600
    os.utime(caminho, (momento, momento))


def test_relatorio_com_data_especifica_ignora_dias(tmp_path):
    """
    Pedido do usuário (2026-08-30): "se eu precisar de um relatório de
    outro dia específico peço aqui diretamente" — data_inicio/data_fim
    dão um período exato do passado, sem depender de 'dias' contado a
    partir de hoje.
    """
    import datetime as dt

    hoje = dt.date.today()
    dia_alvo = hoje - dt.timedelta(days=5)
    dia_fora = hoje - dt.timedelta(days=6)

    _tocar_arquivo_no_dia(tmp_path / "Cliente A" / "arte_do_dia_alvo.pdf", dia_alvo)
    _tocar_arquivo_no_dia(tmp_path / "Cliente A" / "arte_de_outro_dia.pdf", dia_fora)

    relatorio = gerar_relatorio_atividade(tmp_path, data_inicio=dia_alvo)

    assert dia_alvo.strftime("%d/%m/%Y") in relatorio
    assert "arte_do_dia_alvo.pdf" in relatorio
    assert "arte_de_outro_dia.pdf" not in relatorio
