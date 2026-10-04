"""
O que o programa da impressora (BYHX) diz, e o que o vigia faz com isso.

Tudo aqui saiu de arquivo de verdade, lido na máquina DOCAN em
03/10/2026: 446 linhas de PrintedArea.Log desde janeiro e 13 trabalhos
na lista. Os pedaços copiados aqui são os que ensinaram as regras —
inclusive os formatos estranhos (duas raízes no XML, caminho em chinês,
percentual e área zerados), que são justamente o que quebra leitor
escrito de cabeça.
"""
import datetime
import json
import pathlib

import pytest

import rasterlink_hotfolder as rl_hf


# Duas linhas de janeiro (quando o programa ainda preenchia percentual e
# área) e três de setembro, já com os dois zerados. A primeira tem o
# caminho em chinês da montagem da máquina — ela existe pra provar que
# nada aqui tenta entender o nome do arquivo.
LOG_DE_VERDADE = (
    "[2026-01-06 10:40:03.401][TID 1952] D:\\\u56fe\u7247\\G6\u5e73\u7248726-900.prt; "
    "1/6/2026-10:06 AM; 0:33:13; 100; 3.922329 \u33a2\n"
    "[2026-01-06 10:05:26.680][TID 1952] D:\\\u56fe\u7247\\G6\u5e73\u7248726-900.prt; "
    "1/6/2026-10:05 AM; 0:0:9; 0; 0 \u33a2\n"
    "[2026-09-30 19:05:06.347][TID 8852] D:\\1UN LONA IMPRESSA 3.15X3.77M_B_PAREDE_379x347cm.prt; "
    "9/30/2026-6:45 PM; 0:20:1; 0; 0 m2\n"
    "[2026-09-30 20:23:11.236][TID 8852] D:\\1UN LONA IMPRESSA 3.15X3.77M_B_PAREDE_379x347cm.prt; "
    "9/30/2026-8:10 PM; 0:12:47; 0; 0 m2\n"
)

# O XML como ele é: um <Hash> ANTES do <JobList>, ou seja, duas raízes —
# e dentro de cada trabalho uma lista sem nome de campo. Os dois <float>
# são POLEGADAS (196,961426 pol = 5,003 m no arquivo que se chama
# "5.00X0.50M").
def _job(nome, status, quando, caminho, copias, largura_pol, altura_pol):
    return (
        "  <UIJob>\n"
        f"    <JobStatus>{status}</JobStatus>\n"
        f"    <string>{nome}</string>\n"
        f"    <int>{copias}</int>\n"
        "    <int>0</int>\n"
        f"    <dateTime>{quando}</dateTime>\n"
        f"    <string>{caminho}</string>\n"
        "    <double>0</double>\n"
        f"    <float>{largura_pol}</float>\n"
        f"    <float>{altura_pol}</float>\n"
        "    <float>0</float>\n"
        "  </UIJob>\n"
    )


XML_DE_VERDADE = (
    '\ufeff<Hash CRCVers="V1.0">916E892A</Hash>\n'
    "<JobList>\n"
    + _job("5.00X0.50M_AMOSTRA.prt", "Idle", "2026-10-01T17:37:38.6304556-03:00",
           "C:\\Ripados\\5.00X0.50M_AMOSTRA.prt", 1, "196.961426", "19.6888885")
    + _job("1UN LONA IMPRESSA 3.15X3.77M_A_PAREDE_379x347cm.prt", "Printed",
           "2026-09-30T18:27:13.1234567-03:00",
           "C:\\Ripados\\1UN LONA IMPRESSA 3.15X3.77M_A_PAREDE_379x347cm.prt",
           1, "94.0625", "148.625")
    + "</JobList>\n"
)


@pytest.fixture
def byhx(tmp_path):
    """Uma pasta com os dois arquivos do programa da impressora."""
    pasta = tmp_path / "_printermanager"
    pasta.mkdir()
    (pasta / "PrintedArea.Log").write_text(LOG_DE_VERDADE, encoding="utf-8")
    (pasta / "Joblist_His.xml").write_text(XML_DE_VERDADE, encoding="utf-8")
    return pasta


@pytest.fixture(autouse=True)
def _isolar(tmp_path, monkeypatch):
    """Nada aqui pode encostar no OneDrive, no C:\\PrinterManager nem no ripado de verdade."""
    monkeypatch.setattr(rl_hf, "PASTA_RELATORIOS", tmp_path / "_relatorios")
    monkeypatch.setattr(rl_hf, "CAMINHO_LOG", tmp_path / "hotfolder.log")
    monkeypatch.setattr(rl_hf, "CAMINHO_ESTADO_AVISOS", tmp_path / "avisos.json")
    monkeypatch.setattr(rl_hf, "CAMINHO_IMPRESSAO_PENDENTE", tmp_path / "pendente.jsonl")
    monkeypatch.setattr(rl_hf, "CAMINHO_MARCA_BYHX", tmp_path / "marca.json")
    monkeypatch.setattr(rl_hf, "PASTA_BYHX", tmp_path / "_sem_programa")
    monkeypatch.setattr(rl_hf, "PASTAS_RIPADOS_LOCAIS", (tmp_path / "_ripados",))
    rl_hf._ultimo_erro_por_arquivo.clear()


def _calado(nivel, mensagem):
    pass


# --- ler o log de passadas -----------------------------------------


def test_passada_traz_arquivo_pasta_e_tempo_de_maquina(byhx):
    passadas = rl_hf.passadas_do_byhx(byhx)
    assert len(passadas) == 4
    ultima = passadas[-1]
    assert ultima["tipo"] == "passada"
    assert ultima["quando"] == "2026-09-30T20:23:11"
    assert ultima["arquivo"] == "1UN LONA IMPRESSA 3.15X3.77M_B_PAREDE_379x347cm.prt"
    assert ultima["pasta"] == "D:\\"
    # 0:12:47 — é esse o tempo de máquina de verdade, o único que não é estimativa
    assert ultima["segundos"] == 767


def test_caminho_em_chines_nao_derruba_a_leitura(byhx):
    """A linha mais velha do log tem o caminho da montagem da máquina, em chinês."""
    primeira = rl_hf.passadas_do_byhx(byhx)[0]
    assert primeira["arquivo"].endswith(".prt")
    assert primeira["segundos"] == 33 * 60 + 13


def test_desde_descarta_o_que_ja_foi_anotado(byhx):
    """O log tem 446 linhas na máquina de verdade; reler tudo por minuto é desperdício."""
    passadas = rl_hf.passadas_do_byhx(byhx, desde="2026-09-30 19:05:06")
    assert [p["quando"] for p in passadas] == ["2026-09-30T20:23:11"]


def test_linha_de_formato_estranho_e_pulada_em_silencio(byhx):
    caminho = byhx / "PrintedArea.Log"
    caminho.write_text("isto nao e linha de log\n" + LOG_DE_VERDADE, encoding="utf-8")
    assert len(rl_hf.passadas_do_byhx(byhx)) == 4


def test_sem_programa_na_maquina_nao_levanta(tmp_path):
    assert rl_hf.passadas_do_byhx(tmp_path / "nao_existe") == []
    assert rl_hf.trabalhos_do_byhx(tmp_path / "nao_existe") == []
    assert rl_hf.ripados_ja_impressos(tmp_path / "nao_existe") == set()


# --- ler a lista de trabalhos --------------------------------------


def test_trabalho_traz_o_tamanho_que_a_maquina_usou(byhx):
    trabalhos = rl_hf.trabalhos_do_byhx(byhx)
    assert len(trabalhos) == 2
    impresso = trabalhos[1]
    assert impresso["status"] == "Printed"
    assert impresso["quando"] == "2026-09-30T18:27:13"
    assert impresso["copias"] == 1
    # o nome diz 3,15 x 3,77 e a máquina imprimiu 2,39 x 3,77: quem
    # ripou mudou o tamanho lá dentro, que é o combinado com ele.
    # É exatamente por isso que esta medida vale mais que a do nome.
    assert impresso["tamanho_m"] == [2.389, 3.775]


def test_duas_raizes_no_xml_sao_lidas(byhx):
    """O arquivo começa com <Hash> antes do <JobList>: nenhum leitor de XML aceita isso cru."""
    assert "<Hash" in (byhx / "Joblist_His.xml").read_text(encoding="utf-8")
    assert rl_hf.trabalhos_do_byhx(byhx)


def test_xml_quebrado_nao_derruba(byhx):
    (byhx / "Joblist_His.xml").write_text("<JobList><UIJob>sem fechar", encoding="utf-8")
    assert rl_hf.trabalhos_do_byhx(byhx) == []


def test_campo_a_mais_no_meio_nao_perde_o_tamanho(byhx):
    """
    A leitura é por TAG, não por posição: o programa pode ganhar um
    campo numa versão nova, e o que importa (data, caminho, polegadas)
    continua sendo achado.
    """
    texto = (byhx / "Joblist_His.xml").read_text(encoding="utf-8")
    texto = texto.replace("    <double>0</double>\n",
                          "    <double>0</double>\n    <boolean>true</boolean>\n")
    (byhx / "Joblist_His.xml").write_text(texto, encoding="utf-8")
    assert rl_hf.trabalhos_do_byhx(byhx)[1]["tamanho_m"] == [2.389, 3.775]


def test_maquina_vem_da_pasta_quando_a_pasta_diz(byhx):
    """
    Na máquina da DOCAN o SAi grava os dois juntos (C:\\Ripados), e aí
    ninguém sabe de qual máquina é — quem sabe é o PC principal, pela
    entrega. Chutar aqui seria número deduzido se passando por declarado.
    """
    assert rl_hf.trabalhos_do_byhx(byhx)[0]["maquina"] is None
    texto = (byhx / "Joblist_His.xml").read_text(encoding="utf-8")
    texto = texto.replace("C:\\Ripados\\", "D:\\RIPADOS\\DOCAN R5200\\")
    (byhx / "Joblist_His.xml").write_text(texto, encoding="utf-8")
    assert rl_hf.trabalhos_do_byhx(byhx)[0]["maquina"] == "DOCAN R5200"



# --- achar o arquivo, em vez de supor onde ele está ----------------
#
# O defeito de 04/10/2026: o registro de impressão passou a noite sem
# anotar uma linha porque o PrintedArea.Log não está na RAIZ de
# C:\PrinterManager. O coletor que rodou na máquina já procurava
# recursivamente; o vigia não.


def test_acha_o_arquivo_em_subpasta(byhx):
    dentro = byhx / "Log" / "2026"
    dentro.mkdir(parents=True)
    (byhx / "PrintedArea.Log").rename(dentro / "PrintedArea.Log")

    assert rl_hf.arquivo_do_byhx("PrintedArea.Log", byhx) == dentro / "PrintedArea.Log"
    assert len(rl_hf.passadas_do_byhx(byhx)) == 4, "a leitura tem que seguir achando"


def test_entre_homonimos_fica_com_o_maior(byhx):
    """Há mais de um Setting.xml e mais de um Print.log lá dentro; o que presta é o maior."""
    pequeno = byhx / "backup"
    pequeno.mkdir()
    (pequeno / "PrintedArea.Log").write_text("[2026-01-01 00:00:00][TID 1] D:\\x.prt; a; 0:0:1; 0; 0 m2\n",
                                             encoding="utf-8")
    grande = byhx / "PrintedArea.Log"
    grande.unlink()
    (byhx / "atual").mkdir()
    (byhx / "atual" / "PrintedArea.Log").write_text(LOG_DE_VERDADE, encoding="utf-8")

    assert rl_hf.arquivo_do_byhx("PrintedArea.Log", byhx) == byhx / "atual" / "PrintedArea.Log"


def test_arquivo_que_nao_existe_avisa_uma_vez(tmp_path):
    vazia = tmp_path / "_printermanager_vazio"
    vazia.mkdir()
    avisos = []

    assert rl_hf.arquivo_do_byhx("PrintedArea.Log", vazia, lambda n, m: avisos.append(m)) is None
    rl_hf.arquivo_do_byhx("PrintedArea.Log", vazia, lambda n, m: avisos.append(m))

    assert len(avisos) == 1, "o mesmo aviso não repete a cada minuto"
    assert "faxina do ripado não apaga nada" in avisos[0]


def test_arquivo_que_existe_e_nao_abre_e_noticia(byhx, monkeypatch):
    """
    Silêncio aqui é o pior resultado: o programa pode estar segurando o
    arquivo sem deixar ninguém ler, e isso tem que aparecer no log.
    """
    def nega(self, *a, **k):
        raise PermissionError(32, "em uso por outro processo")

    monkeypatch.setattr(pathlib.Path, "read_text", nega)
    avisos = []

    # a ordem importa: o mesmo aviso não repete, então quem pergunta
    # primeiro é quem recolhe a mensagem
    assert rl_hf._texto_do_byhx("PrintedArea.Log", byhx, lambda n, m: avisos.append(m)) is None
    assert any("não consegui ler" in a for a in avisos)
    assert rl_hf.passadas_do_byhx(byhx) == []


def test_sem_o_log_os_trabalhos_impressos_ainda_entram(byhx, tmp_path):
    """
    Era o que faltava: sem PrintedArea.Log a função voltava vazia e nem a
    lista de trabalhos era lida — e o trabalho 'Printed' é prova
    independente, com o tamanho que a máquina usou.
    """
    (byhx / "PrintedArea.Log").unlink()

    resultado = rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                           logger=_calado)

    assert resultado["anotadas"] == 1
    linha = _linhas(tmp_path / "rel", "2026-09")[0]
    assert linha["tipo"] == "trabalho"
    assert linha["tamanho_m"] == [2.389, 3.775]


def test_sem_o_log_a_faxina_ainda_sabe_o_que_imprimiu(byhx, tmp_path):
    (byhx / "PrintedArea.Log").unlink()
    impresso = _ripado(tmp_path / "rip", "1UN LONA IMPRESSA 3.15X3.77M_A_PAREDE_379x347cm.prt",
                       dias_atras=5)
    idle = _ripado(tmp_path / "rip", "5.00X0.50M_AMOSTRA.prt", dias_atras=5)
    monkey = rl_hf.ripados_ja_impressos(byhx)

    rl_hf.faxina_dos_ripados(pastas=[tmp_path / "rip"], logger=_calado, impressos=monkey)

    assert not impresso.exists(), "a lista de trabalhos diz que imprimiu"
    assert idle.exists()


# --- a faxina dos ripados ------------------------------------------


def _ripado(pasta, nome, dias_atras, tamanho=1024):
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_bytes(b"x" * tamanho)
    quando = (datetime.datetime.now() - datetime.timedelta(days=dias_atras)).timestamp()
    import os

    os.utime(arquivo, (quando, quando))
    return arquivo


def test_apaga_o_impresso_que_passou_do_prazo(tmp_path):
    velho = _ripado(tmp_path / "rip", "impresso.prt", dias_atras=5)
    quantos, bytes_livres = rl_hf.faxina_dos_ripados(
        pastas=[tmp_path / "rip"], logger=_calado, impressos={"impresso.prt"})
    assert (quantos, bytes_livres) == (1, 1024)
    assert not velho.exists()


def test_nao_apaga_o_que_ainda_esta_no_prazo(tmp_path):
    novo = _ripado(tmp_path / "rip", "impresso.prt", dias_atras=1)
    assert rl_hf.faxina_dos_ripados(pastas=[tmp_path / "rip"], logger=_calado,
                                    impressos={"impresso.prt"}) == (0, 0)
    assert novo.exists()


def test_velho_mas_nao_impresso_fica_e_vira_aviso(tmp_path):
    """
    Os 302 GB achados em 03/10/2026 eram isto: seis arquivos de 02/10
    que o programa nunca imprimiu. Apagar por data sozinha jogaria fora
    trabalho que ainda vai rodar, e ripar de novo custa horas de máquina.
    """
    esperando = _ripado(tmp_path / "rip", "nunca_rodou.prt", dias_atras=9)
    avisos = []
    quantos, _ = rl_hf.faxina_dos_ripados(
        pastas=[tmp_path / "rip"], logger=lambda n, m: avisos.append(m),
        impressos={"outro.prt"})
    assert quantos == 0
    assert esperando.exists()
    assert any("nunca_rodou.prt" in a and "não apaguei" in a for a in avisos)


def test_sem_lista_de_impressos_nao_apaga_nada(tmp_path):
    """
    Programa da impressora ausente ou log ilegível devolve lista vazia.
    Nesse caso a faxina não é "apague tudo", é "não toque em nada".
    """
    velho = _ripado(tmp_path / "rip", "qualquer.prt", dias_atras=30)
    assert rl_hf.faxina_dos_ripados(pastas=[tmp_path / "rip"], logger=_calado, impressos=set()) == (0, 0)
    assert velho.exists()


def test_so_toca_em_prt(tmp_path):
    outro = _ripado(tmp_path / "rip", "ripado.prn", dias_atras=30)
    rl_hf.faxina_dos_ripados(pastas=[tmp_path / "rip"], logger=_calado,
                             impressos={"ripado.prn", "ripado.prt"})
    assert outro.exists(), "o .prn da Epson (setup XLF) não é nosso e não se toca"


def test_a_faxina_usa_o_que_o_programa_diz(byhx, tmp_path, monkeypatch):
    """Ponta a ponta: a prova de impressão vem do log/lista, não de palpite."""
    monkeypatch.setattr(rl_hf, "PASTA_BYHX", byhx)
    impresso = _ripado(tmp_path / "rip", "1UN LONA IMPRESSA 3.15X3.77M_B_PAREDE_379x347cm.prt",
                       dias_atras=5)
    idle = _ripado(tmp_path / "rip", "5.00X0.50M_AMOSTRA.prt", dias_atras=5)
    rl_hf.faxina_dos_ripados(pastas=[tmp_path / "rip"], logger=_calado)
    assert not impresso.exists(), "estava no PrintedArea.Log: imprimiu"
    assert idle.exists(), "o trabalho está 'Idle': está na fila, não é prova de nada"


def test_avisa_disco_apertado(tmp_path, monkeypatch):
    (tmp_path / "rip").mkdir()
    avisos = []
    import shutil

    monkeypatch.setattr(shutil, "disk_usage", lambda _: type("U", (), {"free": 10 * 1024 ** 3})())
    rl_hf.avisar_disco_cheio(pastas=[tmp_path / "rip"], logger=lambda n, m: avisos.append(m))
    assert any("Disco cheio para a máquina inteira" in a for a in avisos)
    # o mesmo aviso não repete a cada minuto
    rl_hf.avisar_disco_cheio(pastas=[tmp_path / "rip"], logger=lambda n, m: avisos.append(m))
    assert len(avisos) == 1


# --- o registro do que imprimiu ------------------------------------


def _linhas(pasta, mes):
    arquivo = pathlib.Path(pasta) / rl_hf.NOME_SUBPASTA_IMPRESSAO / f"{mes}.jsonl"
    return [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_registra_passadas_e_trabalhos_impressos(byhx, tmp_path):
    resultado = rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                           logger=_calado)
    assert resultado == {"anotadas": 5, "pendentes": 0}
    setembro = _linhas(tmp_path / "rel", "2026-09")
    assert [l["tipo"] for l in setembro] == ["passada", "passada", "trabalho"]
    assert _linhas(tmp_path / "rel", "2026-01")  # a linha de janeiro foi pro mês dela


def test_trabalho_na_fila_nao_entra_no_registro(byhx, tmp_path):
    """"Idle" é trabalho esperando — registrar isso como impressão seria mentira."""
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    todas = _linhas(tmp_path / "rel", "2026-09") + _linhas(tmp_path / "rel", "2026-01")
    assert not any("AMOSTRA" in l["arquivo"] for l in todas)


def test_passada_seguinte_nao_repete_linha(byhx, tmp_path):
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    antes = _linhas(tmp_path / "rel", "2026-09")
    assert rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                      logger=_calado) == {"anotadas": 0, "pendentes": 0}
    assert _linhas(tmp_path / "rel", "2026-09") == antes


def test_linha_nova_no_log_entra_na_passada_seguinte(byhx, tmp_path):
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    with open(byhx / "PrintedArea.Log", "a", encoding="utf-8") as f:
        f.write("[2026-10-03 21:10:00.000][TID 8852] C:\\Ripados\\nova.prt; "
                "10/3/2026-9:00 PM; 0:10:0; 0; 0 m2\n")
    assert rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                      logger=_calado)["anotadas"] == 1
    assert [l["arquivo"] for l in _linhas(tmp_path / "rel", "2026-10")] == ["nova.prt"]


def test_log_zerado_e_relido_sem_duplicar(byhx, tmp_path):
    """
    Se o programa trocar ou zerar o log, a marca não vale mais — e reler
    tudo não pode duplicar linha. Quem garante isso é a chave do
    registro, não a marca.
    """
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    antes = _linhas(tmp_path / "rel", "2026-09")
    (byhx / "PrintedArea.Log").write_text(LOG_DE_VERDADE[:120], encoding="utf-8")
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    assert _linhas(tmp_path / "rel", "2026-09") == antes


def test_registro_de_impressao_nao_encosta_no_de_entregas(byhx, tmp_path):
    """
    Quem lê "_registro" conta cada linha como uma entrega. Uma linha de
    impressão caída ali dobraria o m² do relatório do dia.
    """
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    entregas = tmp_path / "rel" / rl_hf.NOME_SUBPASTA_REGISTRO
    assert not entregas.exists()


def test_a_linha_guarda_fato_bruto(byhx, tmp_path):
    """Nada interpretado: material, m² e cliente são do PC principal."""
    rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    trabalho = [l for l in _linhas(tmp_path / "rel", "2026-09") if l["tipo"] == "trabalho"][0]
    assert set(trabalho) == {"tipo", "quando", "arquivo", "pasta", "maquina", "status",
                             "copias", "tamanho_m", "pc"}
    assert "material" not in trabalho and "m2" not in trabalho


def test_nada_a_anotar_nao_cria_arquivo(tmp_path):
    assert rl_hf.registrar_impressoes(pasta_relatorios=tmp_path / "rel",
                                      pasta_byhx=tmp_path / "nao_existe",
                                      logger=_calado) == {"anotadas": 0, "pendentes": 0}
    assert not (tmp_path / "rel").exists()


# --- a cópia de diagnóstico ----------------------------------------


def test_leva_os_dois_arquivos_e_so_quando_mudam(byhx, tmp_path):
    copiados = rl_hf.levar_historico_do_byhx(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                             logger=_calado)
    assert sorted(copiados) == ["Joblist_His.xml", "PrintedArea.Log"]
    assert rl_hf.levar_historico_do_byhx(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                         logger=_calado) == []
    (byhx / "PrintedArea.Log").write_text(LOG_DE_VERDADE + "mudou\n", encoding="utf-8")
    assert rl_hf.levar_historico_do_byhx(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx,
                                         logger=_calado) == ["PrintedArea.Log"]


def test_a_copia_nao_deixa_arquivo_pela_metade(byhx, tmp_path):
    rl_hf.levar_historico_do_byhx(pasta_relatorios=tmp_path / "rel", pasta_byhx=byhx, logger=_calado)
    pasta = tmp_path / "rel" / rl_hf.NOME_SUBPASTA_IMPRESSAO / rl_hf.NOME_PASTA_BYHX
    assert not list(pasta.rglob("~copiando~*"))



# --- a pasta de saída de cada máquina -------------------------------


def test_prepara_uma_pasta_por_maquina_do_posto(tmp_path, monkeypatch):
    """
    O instalador da máquina da impressora chama isto. A pasta precisa
    existir ANTES de o primeiro ripado chegar: a porta do SAi não cria
    pasta e falha depois de ripar, e quem precisa saber o caminho de
    antemão é gente, pra abrir a pasta e pegar o arquivo.
    """
    import ripados_para_nuvem

    monkeypatch.setattr(ripados_para_nuvem, "PASTA_RIPADOS", tmp_path / "RIPADOS")

    raiz, pastas = rl_hf.preparar_pastas_do_ripado(posto=rl_hf.POSTO_SAI, logger=_calado)

    assert raiz == tmp_path / "RIPADOS"
    assert sorted(p.name for p in pastas) == ["DOCAN H2525", "DOCAN R5200"]
    assert all(p.is_dir() for p in pastas)


def test_nao_prepara_pasta_de_maquina_de_outro_posto(tmp_path, monkeypatch):
    """As Mimaki ripam no outro PC: pasta delas aqui seria pasta vazia pra sempre."""
    import ripados_para_nuvem

    monkeypatch.setattr(ripados_para_nuvem, "PASTA_RIPADOS", tmp_path / "RIPADOS")

    _, pastas = rl_hf.preparar_pastas_do_ripado(posto=rl_hf.POSTO_SAI, logger=_calado)

    assert not any("UJV" in p.name or "SWJ" in p.name for p in pastas)


def test_preparar_nao_levanta_quando_a_pasta_nao_da_pra_criar(tmp_path, monkeypatch):
    import ripados_para_nuvem

    # um ARQUIVO no lugar da raiz: mkdir não tem como criar nada aí dentro
    raiz_tomada = tmp_path / "RIPADOS"
    raiz_tomada.write_text("não sou pasta", encoding="utf-8")
    monkeypatch.setattr(ripados_para_nuvem, "PASTA_RIPADOS", raiz_tomada)
    avisos = []

    raiz, pastas = rl_hf.preparar_pastas_do_ripado(posto=rl_hf.POSTO_SAI,
                                                   logger=lambda n, m: avisos.append(m))

    assert pastas == []
    assert len(avisos) == 2, "um aviso por máquina, e nenhuma exceção"


# --- a passada inteira ---------------------------------------------


def test_uma_tarefa_quebrada_nao_para_as_outras(monkeypatch):
    """
    O programa da impressora fechado, o log em outro formato ou o
    OneDrive engasgado não podem impedir o resto — e muito menos a
    entrega da arte, que é o trabalho de verdade.
    """
    chamadas = []

    def explode(**kwargs):
        raise RuntimeError("programa fechado")

    monkeypatch.setattr(rl_hf, "registrar_impressoes", explode)
    monkeypatch.setattr(rl_hf, "faxina_dos_ripados", lambda **k: chamadas.append("faxina"))
    monkeypatch.setattr(rl_hf, "avisar_disco_cheio", lambda **k: chamadas.append("disco"))
    avisos = []
    rl_hf._cuidar_do_ripado(logger=lambda n, m: avisos.append(m))
    assert chamadas == ["faxina", "disco"]
    assert any("programa fechado" in a for a in avisos)
