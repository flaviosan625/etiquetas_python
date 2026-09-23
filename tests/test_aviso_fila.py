"""
Testes do aviso de fila parada.

A fixture isola `caminhos.PASTA_PROGRAMA` em tmp_path: o estado do aviso é
gravado lá, e sem isso o teste escreveria um `_aviso_fila.json` na pasta do
programa de verdade.
"""
import datetime

import pytest

import aviso_fila
import caminhos


@pytest.fixture(autouse=True)
def pasta_isolada(tmp_path, monkeypatch):
    monkeypatch.setattr(caminhos, "PASTA_PROGRAMA", tmp_path)
    return tmp_path


AGORA = datetime.datetime(2026, 9, 23, 19, 30)


def notificador():
    """Guarda o que seria notificado, em vez de chamar o Windows."""
    recebidos = []

    def notificar(mensagem, titulo=None):
        recebidos.append((mensagem, titulo))

    return notificar, recebidos


def test_fila_vazia_nao_avisa_nada():
    notificar, recebidos = notificador()
    assert aviso_fila.conferir(agora=AGORA, notificar=notificar, paradas={}) == {}
    assert recebidos == []


def test_avisa_quando_tem_arquivo_parado():
    notificar, recebidos = notificador()
    paradas = {"UJV 100 UNY CV": (2, 95)}

    assert aviso_fila.conferir(agora=AGORA, notificar=notificar, paradas=paradas) == paradas

    (mensagem, titulo), = recebidos
    assert titulo == aviso_fila.TITULO
    assert "UJV 100 UNY CV" in mensagem
    assert "2 arquivo(s)" in mensagem


def test_nao_repete_o_aviso_no_minuto_seguinte():
    notificar, recebidos = notificador()
    paradas = {"UJV 100 UNY CV": (2, 95)}
    aviso_fila.conferir(agora=AGORA, notificar=notificar, paradas=paradas)

    daqui_um_minuto = AGORA + datetime.timedelta(minutes=1)
    assert aviso_fila.conferir(agora=daqui_um_minuto, notificar=notificar,
                               paradas=paradas) == {}
    assert len(recebidos) == 1


def test_volta_a_avisar_depois_do_intervalo():
    notificar, recebidos = notificador()
    paradas = {"UJV 100 UNY CV": (2, 95)}
    aviso_fila.conferir(agora=AGORA, notificar=notificar, paradas=paradas)

    depois = AGORA + datetime.timedelta(minutes=aviso_fila.MINUTOS_ENTRE_AVISOS)
    assert aviso_fila.conferir(agora=depois, notificar=notificar, paradas=paradas) == paradas
    assert len(recebidos) == 2


def test_maquina_nova_avisa_na_hora_mesmo_com_outra_em_silencio():
    """
    A UJV já foi avisada há pouco; a SWJ acabou de parar. Esperar a hora
    fechar por causa da outra deixaria o material parado calado.
    """
    notificar, recebidos = notificador()
    aviso_fila.conferir(agora=AGORA, notificar=notificar,
                        paradas={"UJV 100 UNY CV": (2, 95)})

    daqui_um_minuto = AGORA + datetime.timedelta(minutes=1)
    aviso_fila.conferir(agora=daqui_um_minuto, notificar=notificar,
                        paradas={"UJV 100 UNY CV": (2, 96), "SWJ320A": (1, 21)})

    assert len(recebidos) == 2
    assert "SWJ320A" in recebidos[1][0]


def test_fila_que_anda_zera_o_silencio():
    """Resolvido o problema, o PRÓXIMO tem que ser anunciado na hora."""
    notificar, recebidos = notificador()
    paradas = {"UJV 100 UNY CV": (2, 95)}
    aviso_fila.conferir(agora=AGORA, notificar=notificar, paradas=paradas)

    andou = AGORA + datetime.timedelta(minutes=2)
    aviso_fila.conferir(agora=andou, notificar=notificar, paradas={})

    parou_de_novo = AGORA + datetime.timedelta(minutes=3)
    assert aviso_fila.conferir(agora=parou_de_novo, notificar=notificar,
                               paradas=paradas) == paradas
    assert len(recebidos) == 2


def test_notificacao_que_falha_nao_marca_como_avisado():
    """Ninguém foi avisado: a próxima passada tem que tentar de novo."""
    paradas = {"UJV 100 UNY CV": (2, 95)}

    def notificar_quebrado(mensagem, titulo=None):
        raise RuntimeError("PowerShell falhou")

    with pytest.raises(RuntimeError):
        aviso_fila.conferir(agora=AGORA, notificar=notificar_quebrado, paradas=paradas)

    notificar, recebidos = notificador()
    daqui_um_minuto = AGORA + datetime.timedelta(minutes=1)
    assert aviso_fila.conferir(agora=daqui_um_minuto, notificar=notificar,
                               paradas=paradas) == paradas
    assert len(recebidos) == 1


def test_estado_ilegivel_nao_derruba_e_avisa():
    aviso_fila.caminho_estado().write_text("{isso não é json", encoding="utf-8")
    notificar, recebidos = notificador()

    assert aviso_fila.conferir(agora=AGORA, notificar=notificar,
                               paradas={"UJV 100 UNY CV": (2, 95)})
    assert len(recebidos) == 1


def test_relogio_pra_tras_nao_cala_o_aviso():
    """Estado com data no futuro (relógio corrigido) não pode silenciar tudo."""
    notificar, recebidos = notificador()
    futuro = AGORA + datetime.timedelta(hours=5)
    aviso_fila.conferir(agora=futuro, notificar=notificar,
                        paradas={"UJV 100 UNY CV": (2, 95)})

    assert aviso_fila.conferir(agora=AGORA, notificar=notificar,
                               paradas={"UJV 100 UNY CV": (2, 95)})
    assert len(recebidos) == 2


def test_mensagem_diz_a_medida_e_o_que_ela_significa():
    texto = aviso_fila.mensagem({"UJV 100 UNY CV": (2, 95)})
    # "1 h" e não "95 min": é a mesma régua de envio_impressao._quanto_faz
    # que a tela usa. Duas maneiras de dizer o mesmo tempo fariam a
    # notificação e a tela discordarem na frente de quem lê.
    assert "2 arquivo(s) esperando há 1 h" in texto
    assert "PC do RIP" in texto


def test_o_vigia_nao_cai_quando_o_aviso_quebra(monkeypatch):
    """
    O gancho no vigia é conforto: nunca pode atrapalhar a entrega.
    """
    import rasterlink_hotfolder

    registrado = []
    monkeypatch.setattr(rasterlink_hotfolder, "logger_arquivo",
                        lambda nivel, texto, **k: registrado.append((nivel, texto)))
    monkeypatch.setattr(aviso_fila, "conferir",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sem OneDrive")))

    rasterlink_hotfolder._avisar_fila_parada()  # não levanta

    assert any("aviso de fila parada" in texto for _, texto in registrado)
