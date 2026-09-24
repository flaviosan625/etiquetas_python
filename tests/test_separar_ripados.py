"""
Separador dos ripados das duas DOCAN.

Nada aqui toca pasta real: o RIPLOG e as pastas de saida sao montados em
tmp_path, e a fixture autouse desvia PASTA_RIPADOS, CAMINHO_RIPLOG e
PASTA_RIPADOS_ANTIGA (o Desktop\\Ripados de verdade - a revisao de 24/09
pegou os testes varrendo a pasta real).

Os cenarios de perda vieram da revisao de 24/09/2026, que reproduziu cada um
em pasta temporaria antes de o separador ser ligado.
"""
import datetime
import errno
import os
import pathlib

import pytest

import ripados_para_nuvem
import separar_ripados as sr

MAQUINAS = {
    "DOCAN R5200": {"hot_folder": r"C:\x", "setup_sai": "Docan"},
    "DOCAN H2525": {"hot_folder": r"C:\y", "setup_sai": "Docan_H2525"},
    "SWJ320A": {"hot_folder": r"C:\z"},  # Mimaki: nao ripa aqui
}
QUANDO = datetime.datetime(2026, 9, 24, 7, 10, 0)
DEPOIS = QUANDO + datetime.timedelta(minutes=5)  # o arquivo ja parou ha 5 min


@pytest.fixture(autouse=True)
def isolar(tmp_path, monkeypatch):
    monkeypatch.setattr(ripados_para_nuvem, "PASTA_RIPADOS", tmp_path / "RIPADOS")
    monkeypatch.setattr(sr, "CAMINHO_RIPLOG", tmp_path / "RIPLOG.HTML")
    monkeypatch.setattr(sr, "PASTA_RIPADOS_ANTIGA", tmp_path / "Desktop_Ripados")
    (tmp_path / "RIPADOS" / "DOCAN H2525").mkdir(parents=True)
    return tmp_path


def bloco_saida(dispositivo, arquivo, fim):
    return f"""
<TABLE class="tab1" border="1">
<TR><TH align=left colspan=2 bgcolor=#0066CC><H1> &nbsp;Iniciar a impressão</H1>
</TH></TR>
<TR><TH align=left> &nbsp; &nbsp;Nome do dispositivo:
</TH><TD class="td1" align=left> &nbsp; &nbsp;{dispositivo}&nbsp; &nbsp;
</TD></TR>
<TR><TH align=left> &nbsp; &nbsp;Arquivo:
</TH><TD class="td1" align=left> &nbsp; &nbsp;{arquivo}&nbsp; &nbsp;
</TD></TR>
<TR><TH align=left> &nbsp; &nbsp;Data e Hora de Término da Saída:
</TH><TD class="td1" align=left> &nbsp; &nbsp;{fim:%H:%M:%S %d/%m/%Y}&nbsp; &nbsp;
</TD></TR>
</TABLE>"""


def bloco_rip(arquivo):
    """Bloco de RIP (nao de saida): nunca pode contar como prova."""
    return f"""
<TABLE><TR><TH colspan=2><H1> &nbsp;Iniciar Trabalho de RIP</H1></TH></TR>
<TR><TH> &nbsp;Arquivo:</TH><TD> &nbsp;{arquivo}</TD></TR></TABLE>"""


def escrever_log(tmp_path, *blocos):
    (tmp_path / "RIPLOG.HTML").write_text("<HTML><BODY>" + "".join(blocos) + "</BODY></HTML>",
                                          encoding="utf-8")


def ripado(pasta, nome, hora=QUANDO, tamanho=64):
    pasta.mkdir(parents=True, exist_ok=True)
    p = pasta / nome
    p.write_bytes(b"\0" * tamanho)
    ts = hora.timestamp()
    os.utime(p, (ts, ts))
    return p


def saida_do_sai(tmp_path):
    return tmp_path / "RIPADOS" / "DOCAN H2525"


def separar(**k):
    k.setdefault("maquinas", MAQUINAS)
    k.setdefault("agora", DEPOIS)
    return sr.separar(**k)


# ------------------------------------------------------- o log

def test_le_so_os_blocos_de_saida(tmp_path):
    escrever_log(tmp_path, bloco_rip(r"C:\x\ARTE.pdf"), bloco_saida("Docan_H2525", "ARTE.pdf", QUANDO))
    assert sr.saidas_do_riplog() == [{"dispositivo": "Docan_H2525", "trabalho": "ARTE", "fim": QUANDO}]


def test_log_ausente_nao_e_prova_de_nada(tmp_path):
    assert sr.saidas_do_riplog(tmp_path / "nao_existe.html") == []


def test_o_nome_do_trabalho_vem_sem_a_pasta(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan", r"C:\Program Files\SAi\Jobs\Docan\Docan\LONA 4X3.pdf", QUANDO))
    assert sr.saidas_do_riplog()[0]["trabalho"] == "LONA 4X3"


# ------------------------------------------------------- a separacao

def test_ripado_da_r5200_sai_da_pasta_da_h2525(tmp_path):
    """A porta e do dispositivo: as duas DOCAN gravam na mesma pasta."""
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "LONA.prt")

    r = separar()

    assert [m for _, _, m in r["movidos"]] == ["DOCAN R5200"]
    assert not p.exists()
    assert (tmp_path / "RIPADOS" / "DOCAN R5200" / "LONA.prt").exists()


def test_ripado_da_h2525_fica_onde_ja_esta(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan_H2525", "CHAPA.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "CHAPA.prt")

    assert separar()["movidos"] == []
    assert p.exists()


def test_se_a_porta_voltar_pra_pasta_da_r5200_o_da_h2525_e_achado(tmp_path):
    """Trocar a porta de uma DOCAN troca a das duas: todas as pastas de maquina sao vigiadas."""
    escrever_log(tmp_path, bloco_saida("Docan_H2525", "CHAPA.pdf", QUANDO))
    p = ripado(tmp_path / "RIPADOS" / "DOCAN R5200", "CHAPA.prt")

    r = separar()

    assert [m for _, _, m in r["movidos"]] == ["DOCAN H2525"]
    assert not p.exists()


def test_ripado_antigo_no_c_vai_pro_d(tmp_path, monkeypatch):
    """Trabalho antigo reenviado grava no destino velho (Desktop\\Ripados, no C:)."""
    escrever_log(tmp_path, bloco_saida("Docan", "VELHO.pdf", QUANDO))
    velho = ripado(tmp_path / "Desktop_Ripados", "VELHO.prt")

    r = separar()

    assert [m for _, _, m in r["movidos"]] == ["DOCAN R5200"]
    assert not velho.exists()


def test_sem_bloco_no_log_nao_se_mexe(tmp_path):
    escrever_log(tmp_path)
    p = ripado(saida_do_sai(tmp_path), "SEM_LOG.prt")

    assert separar()["sem_prova"] == [p]
    assert p.exists()


def test_arquivo_sendo_gravado_nao_herda_prova_de_saida_anterior(tmp_path):
    """
    O defeito ALTO da revisao: o SAi grava com o nome final e a hora do arquivo
    acompanha o relogio. A saida ANTERIOR de mesmo nome (outra DOCAN, 71 s antes)
    nao pode servir de prova pro arquivo que ainda esta crescendo.
    """
    agora = QUANDO + datetime.timedelta(seconds=71)
    escrever_log(tmp_path, bloco_saida("Docan", "ARTE.pdf", QUANDO))
    crescendo = ripado(saida_do_sai(tmp_path), "ARTE.prt", hora=agora)

    r = separar(agora=agora)

    assert r["sem_prova"] == [crescendo]
    assert crescendo.exists()


def test_arquivo_parado_ha_menos_de_30_s_ainda_espera(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan", "ARTE.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "ARTE.prt")

    assert separar(agora=QUANDO + datetime.timedelta(seconds=10))["sem_prova"] == [p]
    assert p.exists()


def test_termino_a_10_s_da_hora_do_arquivo_nao_e_prova(tmp_path):
    """A folga medida no log real e menor que 1 s; 90 s era largo demais."""
    escrever_log(tmp_path, bloco_saida("Docan", "ARTE.pdf", QUANDO - datetime.timedelta(seconds=10)))
    p = ripado(saida_do_sai(tmp_path), "ARTE.prt")

    assert separar()["sem_prova"] == [p]


def test_mesma_arte_nas_duas_maquinas_no_mesmo_segundo_e_ambiguo(tmp_path):
    """Ripado de plana mandado pra maquina de rolo e chapa perdida: na duvida, fica."""
    escrever_log(tmp_path,
                 bloco_saida("Docan", "ARTE.pdf", QUANDO),
                 bloco_saida("Docan_H2525", "ARTE.pdf", QUANDO + datetime.timedelta(seconds=2)))
    p = ripado(saida_do_sai(tmp_path), "ARTE.prt")

    assert separar()["sem_prova"] == [p]
    assert p.exists()


def test_o_prn_da_epson_nunca_e_tocado(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan", "EPSON.pdf", QUANDO))
    prn = ripado(tmp_path / "Desktop_Ripados", "EPSON.prn")

    r = separar()

    assert r == {"movidos": [], "sem_prova": [], "em_uso": [], "erros": []}
    assert prn.exists()


def test_dispositivo_que_nao_e_docan_nao_e_separado(tmp_path):
    escrever_log(tmp_path, bloco_saida("XLF_HS_NET_EPS3200UV_LM", "EPSON.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "EPSON.prt")

    assert separar()["sem_prova"] == [p]
    assert p.exists()


# ------------------------------------------------------- nunca perde arquivo

def test_nunca_sobrescreve_ripado_que_ja_esta_la(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    ja_estava = ripado(tmp_path / "RIPADOS" / "DOCAN R5200", "LONA.prt", tamanho=10)
    ripado(saida_do_sai(tmp_path), "LONA.prt", tamanho=20)

    (_, destino, _), = separar()["movidos"]

    assert destino != ja_estava
    assert ja_estava.stat().st_size == 10
    assert destino.stat().st_size == 20


def test_dois_homonimos_na_mesma_passada_nao_se_apagam(tmp_path):
    """Reproduzido na revisao: o sufixo _<epoch> repetia no mesmo segundo e um sumia."""
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    ripado(tmp_path / "RIPADOS" / "DOCAN R5200", "LONA.prt", tamanho=10)
    ripado(saida_do_sai(tmp_path), "LONA.prt", tamanho=20)
    ripado(tmp_path / "RIPADOS", "LONA.prt", tamanho=30)

    separar()

    tamanhos = sorted(f.stat().st_size for f in (tmp_path / "RIPADOS" / "DOCAN R5200").glob("LONA*.prt"))
    assert tamanhos == [10, 20, 30], "nenhum dos tres pode sumir"


def test_copia_identica_ja_na_pasta_certa_nao_e_copiada_de_novo(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    ripado(tmp_path / "RIPADOS" / "DOCAN R5200", "LONA.prt", tamanho=20)
    ripado(saida_do_sai(tmp_path), "LONA.prt", tamanho=20)

    assert separar()["movidos"] == []
    assert len(list((tmp_path / "RIPADOS" / "DOCAN R5200").glob("LONA*.prt"))) == 1


def test_ensaio_nao_mexe_em_nada(tmp_path):
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "LONA.prt")

    r = separar(mover=False)

    assert len(r["movidos"]) == 1
    assert p.exists()
    assert not (tmp_path / "RIPADOS" / "DOCAN R5200").exists()


def test_arquivo_aberto_por_alguem_fica(tmp_path):
    """No Windows de verdade: qualquer handle aberto (mesmo compartilhando) = em uso."""
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "LONA.prt")
    with open(p, "rb"):
        assert sr._em_uso(p) is True
        r = separar()
    assert r["em_uso"] == [p]
    assert p.exists()
    assert sr._em_uso(p) is False


def test_erro_que_nao_e_outro_disco_nao_vira_copia(tmp_path, monkeypatch):
    """Reproduzido na revisao: arquivo em uso (erro 32) caia na copia e copiava GB a cada minuto."""
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    p = ripado(saida_do_sai(tmp_path), "LONA.prt")
    copiou = []
    monkeypatch.setattr(sr.os, "rename", lambda de, para: (_ for _ in ()).throw(PermissionError(13, "em uso")))
    monkeypatch.setattr(sr, "_levar_entre_discos", lambda *a: copiou.append(a))

    r = separar()

    assert r["em_uso"] == [p] and copiou == []
    assert p.exists()


def _so_montagem_renomeia(monkeypatch):
    """Simula C: -> D:: rename da origem falha com 'outro disco'; o da montagem funciona."""
    rename_real = os.rename

    def rename(de, para):
        if pathlib.Path(de).name.startswith("~montando~"):
            return rename_real(de, para)
        raise OSError(errno.EXDEV, "outro disco")

    monkeypatch.setattr(sr.os, "rename", rename)


def test_entre_discos_passa_pela_montagem(tmp_path, monkeypatch):
    escrever_log(tmp_path, bloco_saida("Docan", "VELHO.pdf", QUANDO))
    velho = ripado(tmp_path / "Desktop_Ripados", "VELHO.prt")
    _so_montagem_renomeia(monkeypatch)

    (_, destino, _), = separar()["movidos"]

    assert destino.exists() and not velho.exists()
    assert not list(destino.parent.glob("~montando~*"))


def test_copiou_mas_a_origem_nao_saiu_desfaz_a_copia(tmp_path, monkeypatch):
    """Reproduzido na revisao: contar isso como sucesso fazia uma copia inteira nova por passada."""
    escrever_log(tmp_path, bloco_saida("Docan", "VELHO.pdf", QUANDO))
    velho = ripado(tmp_path / "Desktop_Ripados", "VELHO.prt")
    _so_montagem_renomeia(monkeypatch)
    unlink_real = pathlib.Path.unlink

    def unlink(self, *a, **k):
        if self == velho:
            raise PermissionError(13, "presa")
        return unlink_real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)

    r = separar()

    assert r["movidos"] == [] and len(r["erros"]) == 1
    assert velho.exists()
    assert not list((tmp_path / "RIPADOS" / "DOCAN R5200").glob("*.prt")), "a copia tem que ser desfeita"


def test_sem_espaco_no_d_nao_copia(tmp_path, monkeypatch):
    escrever_log(tmp_path, bloco_saida("Docan", "VELHO.pdf", QUANDO))
    velho = ripado(tmp_path / "Desktop_Ripados", "VELHO.prt")
    _so_montagem_renomeia(monkeypatch)
    monkeypatch.setattr(sr.shutil, "disk_usage", lambda p: type("U", (), {"free": 100})())

    r = separar()

    assert r["movidos"] == [] and "livres" in r["erros"][0][1]
    assert velho.exists()


def test_montagem_esquecida_e_limpa(tmp_path):
    velha = ripado(tmp_path / "RIPADOS" / "DOCAN R5200", "~montando~X.prt.parcial",
                   hora=DEPOIS - datetime.timedelta(hours=3))
    nova = ripado(tmp_path / "RIPADOS" / "DOCAN R5200", "~montando~Y.prt.parcial", hora=DEPOIS)
    escrever_log(tmp_path)

    separar()

    assert not velha.exists() and nova.exists()


def test_o_cadastro_de_verdade_liga_cada_docan_ao_seu_nome_no_sai():
    assert sr.maquina_do_dispositivo() == {"Docan": "DOCAN R5200", "Docan_H2525": "DOCAN H2525"}


# ------------------------------------------------------- o gancho no vigia

def test_o_vigia_move_e_avisa_sem_prova_uma_vez_so(tmp_path, monkeypatch):
    """
    O gancho roda a cada minuto: o ripado sem prova vira aviso UMA vez (e so
    depois de parado 10 min), nao 1.440 linhas por dia.
    """
    import rasterlink_hotfolder as rl_hf

    monkeypatch.setattr(rl_hf, "_ultimo_erro_por_arquivo", {})
    escrever_log(tmp_path, bloco_saida("Docan", "LONA.pdf", QUANDO))
    ripado(saida_do_sai(tmp_path), "LONA.prt")
    sem = ripado(saida_do_sai(tmp_path), "SEM_LOG.prt")
    linhas = []
    log = lambda nivel, texto: linhas.append((nivel, texto))

    for _ in range(3):
        rl_hf._separar_ripados_da_docan(logger=log, agora=DEPOIS.timestamp() + 3600)

    assert (tmp_path / "RIPADOS" / "DOCAN R5200" / "LONA.prt").exists()
    avisos = [t for n, t in linhas if "sem prova" in t]
    assert len(avisos) == 1 and sem.name in avisos[0]


def test_o_vigia_nao_cai_se_o_separador_quebrar(monkeypatch):
    import rasterlink_hotfolder as rl_hf

    monkeypatch.setattr(rl_hf, "_ultimo_erro_por_arquivo", {})
    monkeypatch.setattr(sr, "separar", lambda **k: (_ for _ in ()).throw(RuntimeError("D: sumiu")))
    linhas = []

    rl_hf._separar_ripados_da_docan(logger=lambda n, t: linhas.append(t))

    assert any("D: sumiu" in t for t in linhas)
