"""
Driver genérico para softwares RIP baseados em Hot Folder (Caldera, Onyx, VersaWorks, Wasatch, Fiery XF, etc.).
"""
from __future__ import annotations

import datetime
import os
import pathlib
from typing import List, Optional

from hardware.base import DriverRip, MaquinaInfo, StatusFila, StatusTrabalho


class DriverGenericoHotfolder(DriverRip):
    """
    Driver padrão de comunicação via Hot Folder monitorada.

    Compatível com os principais RIPs do mercado que operam vigiando um diretório de arquivos.
    """

    SUBPASTAS_CONCLUIDO = ("Enviados", "Done", "Finished")

    def validar_conexao(self) -> bool:
        """
        Verifica se a hot folder existe e possui permissão de leitura/escrita.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf:
            return False
        try:
            if not hf.exists() or not hf.is_dir():
                return False
            # Testa permissão de escrita de forma segura
            teste_arq = hf / f".teste_conexao_{os.getpid()}.tmp"
            teste_arq.touch(exist_ok=True)
            teste_arq.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def detectar_conclusao(self) -> List[StatusTrabalho]:
        """
        Inspeciona subpastas de conclusão (Enviados/Done) se existirem, listando trabalhos finalizados.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf or not hf.exists():
            return []

        concluidos: List[StatusTrabalho] = []
        arquivos_vistos = set()

        # Procura em subpastas conhecidas de concluídos
        for sub in self.SUBPASTAS_CONCLUIDO:
            pasta_sub = hf / sub
            if pasta_sub.is_dir():
                try:
                    for f in pasta_sub.iterdir():
                        if f.is_file() and not f.name.startswith((".", "~")):
                            if f.name.lower() in arquivos_vistos:
                                continue
                            arquivos_vistos.add(f.name.lower())
                            stat = f.stat()
                            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)
                            concluidos.append(
                                StatusTrabalho(
                                    identificador=f.stem,
                                    nome_arquivo=f.name,
                                    estado="concluido",
                                    data_conclusao=mtime,
                                    detalhes=f"Concluído em '{sub}'",
                                )
                            )
                except Exception:
                    pass

        return concluidos

    def obter_status(self) -> StatusFila:
        """
        Retorna a contagem de itens aguardando na hot folder e espaço em disco disponível.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                mensagem=f"Hot folder não configurada para a máquina '{self.maquina.nome}'.",
            )

        acessivel = self.validar_conexao()
        espaco_livre = self.obter_espaco_livre(hf)

        if not acessivel:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco_livre,
                mensagem=f"Hot folder inacessível ou sem permissão de escrita em '{hf}'.",
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
                            detalhes=f"Aguardando processamento pelo RIP ({stat.st_size} bytes)",
                        )
                    )
        except Exception as e:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco_livre,
                mensagem=f"Erro ao listar hot folder: {e}",
            )

        return StatusFila(
            online=True,
            pasta_acessivel=True,
            total_pendentes=len(trabalhos),
            espaco_livre_bytes=espaco_livre,
            mensagem="Fila operando normalmente.",
            trabalhos=trabalhos,
        )
