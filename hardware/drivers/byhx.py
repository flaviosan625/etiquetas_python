"""
Driver de integração com o BYHX Printer Manager (Docan / UVs Chinesas).
"""
from __future__ import annotations

import datetime
import os
import pathlib
import re
import xml.etree.ElementTree as ElementTree
from typing import Any, Dict, List, Optional, Set, Union

from hardware.base import DriverRip, EntregaResultado, MaquinaInfo, StatusFila, StatusTrabalho

METRO_POR_POLEGADA = 0.0254

_LINHA_IMPRESSA = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[^\]]*\]\[[^\]]*\]\s*"
    r"(.+?);\s*([^;]+);\s*(\d+):(\d+):(\d+);\s*(\d+);\s*([\d.]+)"
)


class DriverByhx(DriverRip):
    """
    Driver para BYHX Printer Manager (comum em impressoras Docan e UV flatbed/rolo chinesas).

    Gerencia o spool de arquivos .prt / .prn e realiza a leitura de telemetria
    diretamente do log de passadas (PrintedArea.Log) e histórico de trabalhos (Joblist_His.xml).
    """

    EXTENSOES_BYHX: Set[str] = {".prt", ".prn"}

    def __init__(self, maquina: MaquinaInfo, pasta_programa: Optional[Union[str, pathlib.Path]] = None):
        super().__init__(maquina)
        self.pasta_programa = pathlib.Path(pasta_programa) if pasta_programa else None

    def _obter_pasta_byhx(self) -> Optional[pathlib.Path]:
        """Localiza a pasta do programa BYHX (ou a própria hot folder configurada)."""
        if self.pasta_programa and self.pasta_programa.is_dir():
            return self.pasta_programa

        meta_byhx = self.maquina.metadados.get("pasta_byhx")
        if meta_byhx:
            p = pathlib.Path(meta_byhx)
            if p.is_dir():
                return p

        # Fallback para a própria hot folder
        hf = self.obter_pasta_hotfolder()
        if hf and hf.is_dir():
            return hf

        # Caminho padrão comum no Windows
        padrao = pathlib.Path(r"C:\PrinterManager")
        if padrao.is_dir():
            return padrao

        return None

    def validar_conexao(self) -> bool:
        """
        Verifica se a pasta de entrega ou diretório do BYHX está acessível para gravação.
        """
        hf = self.obter_pasta_hotfolder() or self._obter_pasta_byhx()
        if not hf:
            return False
        try:
            if not hf.exists() or not hf.is_dir():
                return False
            teste = hf / f".teste_byhx_{os.getpid()}.tmp"
            teste.touch(exist_ok=True)
            teste.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def entregar_arquivo(
        self,
        caminho_origem: Union[str, pathlib.Path],
        metadados: Optional[Dict[str, Any]] = None,
    ) -> EntregaResultado:
        """
        Entrega atômica de arquivo pronto de impressão (.prt / .prn) para a fila do BYHX.
        """
        origem = pathlib.Path(caminho_origem)
        ext = origem.suffix.lower()

        # Alerta se não for .prt ou .prn, a menos que metadados ignorem a checagem
        meta = dict(metadados or {})
        if not meta.get("ignorar_extensao") and ext not in self.EXTENSOES_BYHX:
            return EntregaResultado(
                sucesso=False,
                mensagem=f"O BYHX Printer Manager requer arquivos prontos de impressão (.prt ou .prn). "
                         f"Arquivo fornecido possui extensão '{ext}'.",
                metadados=meta,
            )

        return super().entregar_arquivo(caminho_origem, meta)

    def _ler_arquivo_byhx(self, nome_arquivo: str) -> Optional[str]:
        """Busca e lê arquivo de log/xml na pasta do BYHX recursivamente."""
        pasta = self._obter_pasta_byhx()
        if not pasta or not pasta.is_dir():
            return None

        direto = pasta / nome_arquivo
        if direto.is_file():
            try:
                return direto.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None

        try:
            achados = [c for c in pasta.rglob(nome_arquivo) if c.is_file()]
            if not achados:
                return None
            maior = max(achados, key=lambda c: c.stat().st_size)
            return maior.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    def detectar_conclusao(self) -> List[StatusTrabalho]:
        """
        Interpreta PrintedArea.Log e Joblist_His.xml do BYHX para identificar
        trabalhos efetivamente impressos pela máquina.
        """
        concluidos: List[StatusTrabalho] = []
        processados_nomes = set()

        # 1. Leitura de passadas no PrintedArea.Log
        log_texto = self._ler_arquivo_byhx("PrintedArea.Log")
        if log_texto:
            for linha in log_texto.splitlines():
                m = _LINHA_IMPRESSA.match(linha.strip())
                if m:
                    quando, ripado_caminho, comeco, h, m_min, s, pct, area = m.groups()
                    nome_arq = pathlib.PurePath(ripado_caminho).name
                    segundos = int(h) * 3600 + int(m_min) * 60 + int(s)
                    dt = None
                    try:
                        dt = datetime.datetime.strptime(quando, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        pass

                    processados_nomes.add(nome_arq.lower())
                    concluidos.append(
                        StatusTrabalho(
                            identificador=nome_arq,
                            nome_arquivo=nome_arq,
                            estado="concluido",
                            data_conclusao=dt,
                            detalhes=f"Impresso no BYHX: {segundos}s de máquina ({area} m²)",
                            metadados={
                                "segundos_impressao": segundos,
                                "area_m2": float(area) if area else 0.0,
                                "pct_concluido": int(pct),
                            },
                        )
                    )

        # 2. Leitura de JobList_His.xml
        xml_texto = self._ler_arquivo_byhx("Joblist_His.xml")
        if xml_texto:
            corte = xml_texto.find("<JobList>")
            if corte >= 0:
                try:
                    raiz = ElementTree.fromstring(xml_texto[corte:])
                    for job in raiz:
                        campos: Dict[str, List[str]] = {}
                        for filho in job:
                            campos.setdefault(filho.tag, []).append((filho.text or "").strip())

                        status = (campos.get("JobStatus") or [""])[0]
                        caminhos = [v for v in campos.get("string", []) if ":" in v or "\\" in v]
                        quando_str = (campos.get("dateTime") or [""])[0][:19]

                        if caminhos and status == "Printed":
                            nome_arq = pathlib.PurePath(caminhos[0]).name
                            if nome_arq.lower() not in processados_nomes:
                                dt = None
                                try:
                                    dt = datetime.datetime.fromisoformat(quando_str)
                                except Exception:
                                    pass

                                concluidos.append(
                                    StatusTrabalho(
                                        identificador=nome_arq,
                                        nome_arquivo=nome_arq,
                                        estado="concluido",
                                        data_conclusao=dt,
                                        detalhes="Marcado como Printed no JobList_His.xml",
                                    )
                                )
                except Exception:
                    pass

        return concluidos

    def obter_status(self) -> StatusFila:
        """
        Retorna o status da fila e do spooler do BYHX Printer Manager.
        """
        hf = self.obter_pasta_hotfolder() or self._obter_pasta_byhx()
        if not hf:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                mensagem=f"Pasta do BYHX não configurada para '{self.maquina.nome}'.",
            )

        acessivel = self.validar_conexao()
        espaco = self.obter_espaco_livre(hf)

        if not acessivel:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco,
                mensagem=f"Pasta do BYHX inacessível em '{hf}'.",
            )

        trabalhos: List[StatusTrabalho] = []
        try:
            for item in hf.iterdir():
                if item.is_file() and not item.name.startswith((".", "~")) and not item.suffix.endswith(".tmp"):
                    stat = item.stat()
                    trabalhos.append(
                        StatusTrabalho(
                            identificador=item.stem,
                            nome_arquivo=item.name,
                            estado="pendente",
                            data_envio=datetime.datetime.fromtimestamp(stat.st_ctime),
                            detalhes=f"Pronto para envio/impressão BYHX ({stat.st_size} bytes)",
                        )
                    )
        except Exception as e:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco,
                mensagem=f"Erro ao ler pasta do BYHX: {e}",
            )

        return StatusFila(
            online=True,
            pasta_acessivel=True,
            total_pendentes=len(trabalhos),
            espaco_livre_bytes=espaco,
            mensagem="BYHX Printer Manager pronto.",
            trabalhos=trabalhos,
        )
