"""Trava local da montagem e publicação conferida do lote de PDFs e fichas."""
import contextlib
import json
import math
import os
import pathlib
import tempfile
import threading

import pymupdf


class MontagemOcupada(RuntimeError):
    """Outra janela ou o monitor já está montando esta entrada."""


_TRAVAS = {}
_GUARDA_TRAVAS = threading.Lock()


@contextlib.contextmanager
def trava_montagem(pasta):
    """Impede o botão e o monitor de produzirem o mesmo lote simultaneamente."""
    pasta = pathlib.Path(pasta).resolve()
    if not pasta.is_dir():
        yield
        return
    chave = os.path.normcase(str(pasta))
    with _GUARDA_TRAVAS:
        trava = _TRAVAS.setdefault(chave, threading.Lock())
    if not trava.acquire(blocking=False):
        raise MontagemOcupada("Esta máquina já está montando. Aguarde e recalcule a prévia.")
    arquivo = None
    try:
        arquivo = (pasta / "_montagem.trava").open("a+b")
        arquivo.seek(0, os.SEEK_END)
        if arquivo.tell() == 0:
            arquivo.write(b"0")
            arquivo.flush()
        arquivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as erro:
            raise MontagemOcupada(
                "Outra montagem está usando esta pasta. Aguarde e recalcule a prévia.") from erro
        yield
    finally:
        if arquivo is not None:
            arquivo.close()
        trava.release()


class PublicacaoMontagem:
    """Prepara e relê o lote inteiro antes de expor as saídas finais.

    Não substitui PDFs anteriores. Em uma falha de publicação, desfaz somente
    os arquivos novos desta operação; os originais só podem ser arquivados
    pelo chamador depois de ``publicar`` concluir.
    """

    def __init__(self, pasta_saida):
        self.pasta = pathlib.Path(pasta_saida)
        self._temporario = None
        self._preparados = []
        self._reservados = set()

    def __enter__(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._temporario = tempfile.TemporaryDirectory(prefix=".montagem-", dir=self.pasta)
        return self

    def __exit__(self, tipo, erro, tb):
        if self._temporario is not None:
            self._temporario.cleanup()

    def _destino_livre(self, destino):
        destino = pathlib.Path(destino)
        if destino.parent.resolve() != self.pasta.resolve():
            raise ValueError("A folha deve ficar na saída deste lote.")
        candidato = destino
        numero = 2
        while (candidato in self._reservados or candidato.exists()
               or candidato.with_suffix(".json").exists()):
            candidato = destino.with_name(f"{destino.stem}__{numero:02d}{destino.suffix}")
            numero += 1
        self._reservados.add(candidato)
        return candidato

    def salvar(self, doc, destino, ficha):
        """Grava sem recomprimir imagens e confere PDF e ficha ainda temporários."""
        if self._temporario is None:
            raise RuntimeError("Use a publicação dentro de um contexto with.")
        destino = self._destino_livre(destino)
        provisoria = pathlib.Path(self._temporario.name) / f"{len(self._preparados):04d}.pdf"
        doc.save(str(provisoria), garbage=4, deflate=True, deflate_images=False)
        with pymupdf.open(provisoria) as gravado:
            if gravado.page_count != doc.page_count or gravado.page_count == 0:
                raise ValueError("A conferência do PDF montado falhou: páginas incompletas.")
            for pagina in gravado:
                medidas = (pagina.rect.width, pagina.rect.height)
                if any(not math.isfinite(v) or v <= 0 for v in medidas):
                    raise ValueError("O PDF montado ficou com uma medida inválida.")
        texto = json.dumps(ficha, ensure_ascii=False, indent=2, allow_nan=False)
        json_temporario = provisoria.with_suffix(".json")
        with json_temporario.open("w", encoding="utf-8") as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        if json.loads(json_temporario.read_text(encoding="utf-8")) != json.loads(texto):
            raise ValueError("A conferência da ficha de montagem falhou.")
        self._preparados.append((provisoria, destino))
        return destino

    def publicar(self):
        """Publica o lote conferido; desfaz o lote novo se uma gravação falhar."""
        publicados = []
        try:
            for provisoria, destino in self._preparados:
                for origem, alvo in ((provisoria, destino),
                                     (provisoria.with_suffix(".json"), destino.with_suffix(".json"))):
                    if alvo.exists():
                        raise FileExistsError(f"A saída já existe: {alvo.name}")
                    origem.rename(alvo)
                    publicados.append(alvo)
        except BaseException:
            for alvo in reversed(publicados):
                alvo.unlink(missing_ok=True)
            raise
        self._preparados.clear()
