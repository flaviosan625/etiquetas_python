"""
Driver de integração com o software RIP Mimaki RasterLink (RasterLink 6 / 7).
"""
from __future__ import annotations

import datetime
import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Set, Union

from hardware.base import DriverRip, EntregaResultado, MaquinaInfo, StatusFila, StatusTrabalho


class DriverRasterLink(DriverRip):
    """
    Driver especializado para Mimaki RasterLink via spooler MijCtrl ou Hot Folder.

    Implementa validações estritas de extensões suportadas pelo RIP Mimaki,
    sanitização de nomes de arquivos para evitar erros no parser do RasterLink,
    e acompanhamento do ciclo de consumo do job.
    """

    EXTENSOES_SUPORTADAS: Set[str] = {
        ".pdf", ".eps", ".ps", ".tif", ".tiff", ".jpg", ".jpeg"
    }

    # Caracteres que podem travar ou corromper a importação no RasterLink
    _CARACTERES_INVALIDOS = re.compile(r'[<>:"/\\|?*%;#&]')

    def sanitizar_nome_arquivo(self, nome: str) -> str:
        """
        Remove caracteres problemáticos para o parser de nomes de arquivo do RasterLink.
        """
        base = self._CARACTERES_INVALIDOS.sub("_", nome).strip()
        # RasterLink prefere nomes sem pontos múltiplos antes da extensão
        partes = base.rsplit(".", 1)
        if len(partes) == 2:
            stem, ext = partes
            stem_limpo = stem.replace(".", "_")
            return f"{stem_limpo}.{ext}"
        return base

    def validar_conexao(self) -> bool:
        """
        Verifica se a hot folder do RasterLink está ativa e acessível para gravação.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf:
            return False
        try:
            if not hf.exists() or not hf.is_dir():
                return False
            teste = hf / f".teste_rasterlink_{os.getpid()}.tmp"
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
        Entrega atômica para o RasterLink com validação de extensão e sanitização de nome.
        """
        origem = pathlib.Path(caminho_origem)
        ext = origem.suffix.lower()

        if ext not in self.EXTENSOES_SUPORTADAS:
            return EntregaResultado(
                sucesso=False,
                mensagem=f"Extensão '{ext}' não suportada pelo Mimaki RasterLink. "
                         f"Extensões válidas: {', '.join(sorted(self.EXTENSOES_SUPORTADAS))}",
                metadados=dict(metadados or {}),
            )

        # Sanitiza nome se não fornecido explicitamente
        meta = dict(metadados or {})
        nome_destino = meta.get("nome_destino") or origem.name
        meta["nome_destino"] = self.sanitizar_nome_arquivo(nome_destino)

        return super().entregar_arquivo(caminho_origem, meta)

    def detectar_conclusao(self) -> List[StatusTrabalho]:
        """
        No RasterLink, uma vez consumido pela hot folder, o arquivo é movido/deletado
        pelo RIP para seu banco interno de jobs. Se houver pasta 'Enviados' na fila,
        inspeciona o histórico de arquivos despachados.
        """
        concluidos: List[StatusTrabalho] = []

        # Inspeciona pasta 'Enviados' na pasta de entrada da máquina, se existir
        pe = self.obter_pasta_entrada()
        if pe:
            pasta_env = pe / "Enviados"
            if pasta_env.is_dir():
                try:
                    for f in pasta_env.iterdir():
                        if f.is_file() and not f.name.startswith("."):
                            stat = f.stat()
                            concluidos.append(
                                StatusTrabalho(
                                    identificador=f.stem,
                                    nome_arquivo=f.name,
                                    estado="concluido",
                                    data_conclusao=datetime.datetime.fromtimestamp(stat.st_mtime),
                                    detalhes="Arquivo enviado ao spooler do RasterLink com sucesso",
                                )
                            )
                except Exception:
                    pass

        return concluidos

    def obter_status(self) -> StatusFila:
        """
        Obtém status da fila do RasterLink, arquivos aguardando processamento e espaço em disco.
        """
        hf = self.obter_pasta_hotfolder()
        if not hf:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                mensagem=f"Hot folder do RasterLink não configurada para '{self.maquina.nome}'.",
            )

        acessivel = self.validar_conexao()
        espaco = self.obter_espaco_livre(hf)

        if not acessivel:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco,
                mensagem=f"Hot folder do RasterLink inacessível em '{hf}'. Verifique se o RIP está ativo.",
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
                            detalhes=f"No spool de entrada do RasterLink ({stat.st_size} bytes)",
                        )
                    )
        except Exception as e:
            return StatusFila(
                online=False,
                pasta_acessivel=False,
                espaco_livre_bytes=espaco,
                mensagem=f"Erro ao ler spool do RasterLink: {e}",
            )

        return StatusFila(
            online=True,
            pasta_acessivel=True,
            total_pendentes=len(trabalhos),
            espaco_livre_bytes=espaco,
            mensagem="Spooler Mimaki RasterLink online.",
            trabalhos=trabalhos,
        )
