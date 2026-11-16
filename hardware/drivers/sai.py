"""
Driver de integração com o SAi Production Manager / FlexiSIGN.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Union

from hardware.base import DriverRip, EntregaResultado, MaquinaInfo, StatusFila, StatusTrabalho


class DriverSaiProductionManager(DriverRip):
    """
    Driver para SAi Production Manager (FlexiSIGN Suite).

    Suporta setups dedicados por máquina (ex: Docan, Docan_H2525), detecção de
    arquivos ripados (.prt), portas FILE: e telemetria de processamento.
    """

    CAMINHO_PADRAO_SAI = pathlib.Path(
        r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings"
    )

    def obter_pasta_hotfolder(self) -> Optional[pathlib.Path]:
        """
        Retorna a hot folder configurada diretamente ou resolve pelo setup do SAi.
        """
        if self.maquina.hot_folder:
            return pathlib.Path(self.maquina.hot_folder)

        # Tenta resolver via PMSetups.ini se disponível
        if self.maquina.setup_sai:
            try:
                import sai_setups
                hf = sai_setups.hot_folder_de(self.maquina.setup_sai)
                if hf:
                    return pathlib.Path(hf)
            except Exception:
                pass

        return None

    def validar_conexao(self) -> bool:
        """
        Verifica se a pasta do Setup do SAi existe e aceita gravação.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf:
            return False
        try:
            if not hf.exists() or not hf.is_dir():
                return False
            teste = hf / f".teste_sai_{os.getpid()}.tmp"
            teste.touch(exist_ok=True)
            teste.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def detectar_conclusao(self) -> List[StatusTrabalho]:
        """
        Detecta trabalhos ripados pelo SAi (.prt). Inspeciona logs do RIPLOG ou pastas de saída.
        """
        concluidos: List[StatusTrabalho] = []
        riplog = self.CAMINHO_PADRAO_SAI / "RIPLOG.HTML"

        if riplog.is_file():
            try:
                texto = riplog.read_text(encoding="utf-8", errors="ignore")
                # Procura blocos associados ao dispositivo
                setup_alvo = self.maquina.setup_sai or self.maquina.nome
                # Regex simplificada procurando trabalhos do dispositivo
                padrao = re.compile(
                    rf"Nome do dispositivo:\s*(?:Docan-)?{re.escape(setup_alvo)}.*?Nome do trabalho:\s*([^<\n\r]+).*?Término da Saída:\s*([^<\n\r]+)",
                    re.IGNORECASE | re.DOTALL,
                )
                for match in padrao.finditer(texto):
                    trab, data_str = match.groups()
                    concluidos.append(
                        StatusTrabalho(
                            identificador=trab.strip(),
                            nome_arquivo=trab.strip(),
                            estado="concluido",
                            detalhes=f"Ripado pelo SAi ({setup_alvo}) em {data_str.strip()}",
                        )
                    )
            except Exception:
                pass

        return concluidos

    def obter_status(self) -> StatusFila:
        """
        Retorna o status da fila do SAi Production Manager para a máquina.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                mensagem=f"Hot folder do Setup SAi não encontrada para '{self.maquina.nome}'.",
            )

        acessivel = self.validar_conexao()
        espaco = self.obter_espaco_livre(hf)

        if not acessivel:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco,
                mensagem=f"Pasta do SAi inacessível em '{hf}'. Verifique o Production Manager.",
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
                            detalhes=f"Aguardando RIP pelo SAi ({stat.st_size} bytes)",
                        )
                    )
        except Exception as e:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco,
                mensagem=f"Erro ao ler fila do SAi: {e}",
            )

        return StatusFila(
            online=True,
            pasta_acessivel=True,
            total_pendentes=len(trabalhos),
            espaco_livre_bytes=espaco,
            mensagem="Setup SAi Production Manager online.",
            trabalhos=trabalhos,
            metadados={"setup_sai": self.maquina.setup_sai or ""},
        )
