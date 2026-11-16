"""
Abstração base para hardware gráfico e drivers de RIP.

Define os modelos de dados (MaquinaInfo, EntregaResultado, StatusFila, StatusTrabalho)
e o contrato abstrato DriverRip com implementação segura de entrega atômica.
"""
from __future__ import annotations

import abc
import datetime
import os
import pathlib
import shutil
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class MaquinaInfo:
    """
    Informações cadastrais e capacidades técnicas de uma impressora/máquina de corte.
    """
    nome: str
    tipo: str = "rolo"  # "rolo" ou "mesa"
    largura_util_m: Optional[float] = None
    mesa_util_m: Optional[Tuple[float, float]] = None
    hot_folder: Optional[str] = None
    pasta_entrada: Optional[str] = None
    rip_tipo: str = "generico"  # "rasterlink", "sai", "byhx", "generico"
    posto: str = "local"  # "rip", "sai", "local"
    setup_sai: Optional[str] = None
    montagem: bool = True
    largura_montagem_m: Optional[float] = None
    margem_montagem_m: float = 0.0
    girar: bool = True
    entrega_byhx: bool = False
    ativo: bool = True
    metadados: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_mesa(self) -> bool:
        """Indica se é máquina de mesa plana (impressão em chapa rígida)."""
        return self.tipo == "mesa" or self.mesa_util_m is not None

    @property
    def is_rolo(self) -> bool:
        """Indica se é máquina de rolo/bobina contínua."""
        return not self.is_mesa

    @property
    def limite_largura(self) -> Optional[float]:
        """Largura máxima em metros (rolo ou primeiro eixo da mesa)."""
        if self.is_rolo:
            return self.largura_util_m
        if self.mesa_util_m:
            return self.mesa_util_m[0]
        return None

    @property
    def area_mesa_m2(self) -> Optional[float]:
        """Área total útil da mesa em metros quadrados, se aplicável."""
        if self.mesa_util_m:
            return round(self.mesa_util_m[0] * self.mesa_util_m[1], 4)
        return None

    @property
    def descricao_dimensoes(self) -> str:
        """Descrição legível das dimensões úteis para exibição."""
        if self.is_mesa and self.mesa_util_m:
            x, y = self.mesa_util_m
            return f"Mesa {x:.2f} × {y:.2f} m".replace(".", ",")
        if self.largura_util_m:
            return f"Rolo {self.largura_util_m:.2f} m".replace(".", ",")
        return "Sem limite definido"

    def cabe(self, largura_m: float, altura_m: float, tolerancia_m: float = 0.001) -> bool:
        """
        Verifica se uma arte de dimensões (largura, altura) cabe na máquina,
        considerando tanto a orientação normal quanto girada 90°.
        """
        if largura_m <= 0 or altura_m <= 0:
            return False

        if self.is_mesa:
            if not self.mesa_util_m:
                return True
            mx, my = self.mesa_util_m
            normal = (largura_m <= mx + tolerancia_m) and (altura_m <= my + tolerancia_m)
            girada = (altura_m <= mx + tolerancia_m) and (largura_m <= my + tolerancia_m)
            return normal or girada

        # Rolo/Bobina
        if not self.largura_util_m:
            return True
        limite = self.largura_util_m + tolerancia_m
        return (largura_m <= limite) or (altura_m <= limite)

    def to_dict(self) -> Dict[str, Any]:
        """Converte a configuração para formato compatível com config.json e MAQUINAS."""
        d: Dict[str, Any] = {
            "tipo": self.tipo,
            "rip_tipo": self.rip_tipo,
            "posto": self.posto,
            "montagem": self.montagem,
            "girar": self.girar,
            "entrega_byhx": self.entrega_byhx,
            "ativo": self.ativo,
        }
        if self.hot_folder:
            d["hot_folder"] = self.hot_folder
        if self.pasta_entrada:
            d["pasta_entrada"] = self.pasta_entrada
        if self.largura_util_m is not None:
            d["largura_util_m"] = self.largura_util_m
        if self.mesa_util_m is not None:
            d["mesa_util_m"] = list(self.mesa_util_m)
        if self.setup_sai:
            d["setup_sai"] = self.setup_sai
        if self.largura_montagem_m is not None:
            d["largura_montagem_m"] = self.largura_montagem_m
        if self.margem_montagem_m:
            d["margem_montagem_m"] = self.margem_montagem_m
        if self.metadados:
            d["metadados"] = self.metadados
        return d

    @classmethod
    def from_dict(cls, nome: str, d: Union[Dict[str, Any], str]) -> "MaquinaInfo":
        """Reconstrói MaquinaInfo a partir de dicionário ou caminho string legado."""
        if not isinstance(d, dict):
            hf_str = str(d) if d else ""
            rip_tipo = "generico"
            if "MijCtrl" in hf_str or "rasterlink" in hf_str.lower():
                rip_tipo = "rasterlink"
            elif "SAi" in hf_str:
                rip_tipo = "sai"
            elif "byhx" in hf_str.lower():
                rip_tipo = "byhx"

            return cls(
                nome=nome,
                hot_folder=hf_str if hf_str else None,
                tipo="rolo",
                rip_tipo=rip_tipo,
            )

        # Trata dimensões de mesa
        mesa = None
        if "mesa_util_m" in d and d["mesa_util_m"]:
            try:
                m = d["mesa_util_m"]
                mesa = (float(m[0]), float(m[1]))
            except (ValueError, TypeError, IndexError):
                mesa = None

        largura_util = None
        if "largura_util_m" in d and d["largura_util_m"] is not None:
            try:
                largura_util = float(d["largura_util_m"])
            except (ValueError, TypeError):
                largura_util = None

        largura_mont = None
        if "largura_montagem_m" in d and d["largura_montagem_m"] is not None:
            try:
                largura_mont = float(d["largura_montagem_m"])
            except (ValueError, TypeError):
                largura_mont = None

        margem_mont = 0.0
        if "margem_montagem_m" in d and d["margem_montagem_m"] is not None:
            try:
                margem_mont = float(d["margem_montagem_m"])
            except (ValueError, TypeError):
                margem_mont = 0.0

        tipo = d.get("tipo")
        if not tipo:
            tipo = "mesa" if mesa is not None else "rolo"

        rip_tipo = d.get("rip_tipo")
        if not rip_tipo:
            hf = str(d.get("hot_folder", ""))
            if "SAi" in hf or d.get("setup_sai"):
                rip_tipo = "sai"
            elif "MijCtrl" in hf or "rasterlink" in hf.lower():
                rip_tipo = "rasterlink"
            elif "byhx" in hf.lower() or "printermanager" in hf.lower():
                rip_tipo = "byhx"
            else:
                rip_tipo = "generico"

        return cls(
            nome=nome,
            tipo=tipo,
            largura_util_m=largura_util,
            mesa_util_m=mesa,
            hot_folder=d.get("hot_folder"),
            pasta_entrada=d.get("pasta_entrada"),
            rip_tipo=rip_tipo,
            posto=d.get("posto", "local"),
            setup_sai=d.get("setup_sai"),
            montagem=bool(d.get("montagem", True)),
            largura_montagem_m=largura_mont,
            margem_montagem_m=margem_mont,
            girar=bool(d.get("girar", True)),
            entrega_byhx=bool(d.get("entrega_byhx", False)),
            ativo=bool(d.get("ativo", True)),
            metadados=d.get("metadados", {}) if isinstance(d.get("metadados"), dict) else {},
        )


@dataclass
class EntregaResultado:
    """Resultado da operação de entrega de um arquivo à hot folder ou fila."""
    sucesso: bool
    arquivo_destino: Optional[pathlib.Path] = None
    mensagem: str = ""
    bytes_transferidos: int = 0
    tempo_segundos: float = 0.0
    metadados: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StatusTrabalho:
    """Estado de um trabalho de impressão submetido ao RIP ou fila."""
    identificador: str
    nome_arquivo: str
    estado: str  # "pendente", "processando", "concluido", "erro"
    data_envio: Optional[datetime.datetime] = None
    data_conclusao: Optional[datetime.datetime] = None
    detalhes: str = ""
    metadados: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StatusFila:
    """Telemetria da fila ou hot folder de uma máquina."""
    online: bool
    pasta_acessivel: bool
    total_pendentes: int = 0
    total_processando: int = 0
    total_concluidos: int = 0
    espaco_livre_bytes: Optional[int] = None
    mensagem: str = ""
    trabalhos: List[StatusTrabalho] = field(default_factory=list)
    metadados: Dict[str, Any] = field(default_factory=dict)


class DriverRip(abc.ABC):
    """
    Classe base abstrata para comunicação com softwares RIP e spoolers de impressão.
    """

    def __init__(self, maquina: MaquinaInfo):
        self.maquina = maquina

    @property
    def nome(self) -> str:
        return self.maquina.nome

    @abc.abstractmethod
    def validar_conexao(self) -> bool:
        """
        Verifica se a pasta de hot folder/comunicação está acessível e com permissão de escrita.
        """
        pass

    def obter_pasta_hotfolder(self) -> Optional[pathlib.Path]:
        """Retorna o objeto Path da hot folder configurada, se houver."""
        if self.maquina.hot_folder:
            return pathlib.Path(self.maquina.hot_folder)
        return None

    def obter_pasta_entrada(self) -> Optional[pathlib.Path]:
        """Retorna o objeto Path da pasta de entrada configurada, se houver."""
        if self.maquina.pasta_entrada:
            return pathlib.Path(self.maquina.pasta_entrada)
        return None

    def obter_espaco_livre(self, caminho: Optional[pathlib.Path] = None) -> Optional[int]:
        """Retorna o espaço livre em bytes na unidade do caminho fornecido."""
        alvo = caminho or self.obter_pasta_hotfolder() or self.obter_pasta_entrada()
        if not alvo:
            return None
        try:
            alvo = alvo.resolve()
            if not alvo.exists():
                alvo = alvo.parent
            if alvo.exists():
                return shutil.disk_usage(alvo).free
        except Exception:
            pass
        return None

    def entregar_arquivo(
        self,
        caminho_origem: Union[str, pathlib.Path],
        metadados: Optional[Dict[str, Any]] = None,
    ) -> EntregaResultado:
        """
        Executa a entrega atômica e segura do arquivo para a hot folder.

        Garante integridade gravando primeiro com prefixo temporário `~montando~`
        e extensão `.tmp`, seguido de flush e os.fsync determinísticos, e renomeação
        atômica final apenas quando 100% dos bytes estiverem persistidos no disco.
        Evita que o RIP tente processar um arquivo parcialmente copiado.
        """
        metadados = dict(metadados or {})
        origem = pathlib.Path(caminho_origem)

        if not origem.is_file():
            return EntregaResultado(
                sucesso=False,
                mensagem=f"Arquivo de origem não encontrado: {origem}",
                metadados=metadados,
            )

        # Determina pasta de destino (hot folder por padrão, ou pasta_entrada se solicitado)
        pasta_destino = None
        if metadados.get("usar_pasta_entrada") and self.obter_pasta_entrada():
            pasta_destino = self.obter_pasta_entrada()
        elif metadados.get("pasta_destino"):
            pasta_destino = pathlib.Path(metadados["pasta_destino"])
        else:
            pasta_destino = self.obter_pasta_hotfolder()

        if not pasta_destino:
            return EntregaResultado(
                sucesso=False,
                mensagem=f"Hot folder não configurada para a máquina '{self.maquina.nome}'",
                metadados=metadados,
            )

        inicio = time.time()
        caminho_temp = None

        try:
            pasta_destino.mkdir(parents=True, exist_ok=True)

            nome_final = metadados.get("nome_destino") or origem.name
            destino_final = pasta_destino / nome_final

            # Nome temporário seguro no mesmo diretório de destino para garantir rename atômico
            prefixo_temp = metadados.get("prefixo_temp", "~montando~")
            identificador = uuid.uuid4().hex[:8]
            nome_temp = f"{prefixo_temp}{origem.stem}_{identificador}{origem.suffix}.tmp"
            caminho_temp = pasta_destino / nome_temp

            bytes_totais = 0
            tam_bloco = 64 * 1024  # 64 KB

            with open(origem, "rb") as f_in, open(caminho_temp, "wb") as f_out:
                while True:
                    bloco = f_in.read(tam_bloco)
                    if not bloco:
                        break
                    f_out.write(bloco)
                    bytes_totais += len(bloco)

                # Força escrita em disco antes de expor ao RIP
                f_out.flush()
                os.fsync(f_out.fileno())

            # Preserva timestamp de modificação original se possível
            try:
                stat_origem = origem.stat()
                os.utime(caminho_temp, (stat_origem.st_atime, stat_origem.st_mtime))
            except Exception:
                pass

            # Renomeação atômica
            caminho_temp.replace(destino_final)

            duracao = max(0.001, time.time() - inicio)
            return EntregaResultado(
                sucesso=True,
                arquivo_destino=destino_final,
                bytes_transferidos=bytes_totais,
                tempo_segundos=round(duracao, 4),
                mensagem=f"Arquivo entregue com sucesso em '{destino_final}'.",
                metadados=metadados,
            )

        except Exception as e:
            # Limpa arquivo temporário em caso de falha
            if caminho_temp and caminho_temp.exists():
                try:
                    caminho_temp.unlink(missing_ok=True)
                except Exception:
                    pass

            duracao = max(0.001, time.time() - inicio)
            return EntregaResultado(
                sucesso=False,
                arquivo_destino=None,
                bytes_transferidos=0,
                tempo_segundos=round(duracao, 4),
                mensagem=f"Falha na entrega segura para '{self.maquina.nome}': {e}",
                metadados=metadados,
            )

    @abc.abstractmethod
    def detectar_conclusao(self) -> List[StatusTrabalho]:
        """
        Detecta trabalhos concluídos ou em andamento na fila do RIP.
        """
        pass

    @abc.abstractmethod
    def obter_status(self) -> StatusFila:
        """
        Inspeciona a fila e retorna o status atual e telemetria.
        """
        pass
