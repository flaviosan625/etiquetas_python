"""
Gerenciador central de hardware gráfico e fábrica de drivers de RIP.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib
from typing import Any, Dict, List, Optional, Type, Union

from hardware.base import DriverRip, EntregaResultado, MaquinaInfo, StatusFila
from hardware.drivers.byhx import DriverByhx
from hardware.drivers.generico import DriverGenericoHotfolder
from hardware.drivers.rasterlink import DriverRasterLink
from hardware.drivers.sai import DriverSaiProductionManager


class GerenciadorHardware:
    """
    Gerenciador do catálogo de máquinas e equipamentos, atuando como fábrica de drivers
    e mantendo sincronização atômica com config.json, memória e banco relacional SQLite.
    """

    def __init__(
        self,
        caminho_config: Optional[Union[str, pathlib.Path]] = None,
        caminho_banco: Optional[Union[str, pathlib.Path]] = None,
        carregar_automatico: bool = True,
    ):
        self.caminho_config = pathlib.Path(caminho_config) if caminho_config else None
        self.caminho_banco = pathlib.Path(caminho_banco) if caminho_banco else None
        self._maquinas: Dict[str, MaquinaInfo] = {}

        # Fábrica de drivers registrada
        self._drivers_registrados: Dict[str, Type[DriverRip]] = {
            "generico": DriverGenericoHotfolder,
            "rasterlink": DriverRasterLink,
            "sai": DriverSaiProductionManager,
            "byhx": DriverByhx,
        }

        if carregar_automatico:
            self.recarregar()

    def registrar_driver(self, rip_tipo: str, classe_driver: Type[DriverRip]) -> None:
        """Permite plugar novos drivers de RIP dinamicamente."""
        if not issubclass(classe_driver, DriverRip):
            raise TypeError(f"A classe {classe_driver} deve herdar de DriverRip.")
        self._drivers_registrados[rip_tipo.lower()] = classe_driver

    def obter_classe_driver(self, rip_tipo: str) -> Type[DriverRip]:
        """Retorna a classe do driver registrado para o tipo de RIP especificado."""
        return self._drivers_registrados.get(rip_tipo.lower(), DriverGenericoHotfolder)

    def obter_driver(self, maquina_ou_nome: Union[str, MaquinaInfo]) -> DriverRip:
        """
        Fábrica de drivers: instancia e retorna o driver correto para a máquina solicitada.
        """
        if isinstance(maquina_ou_nome, str):
            info = self.obter_maquina(maquina_ou_nome)
            if not info:
                raise KeyError(f"Máquina '{maquina_ou_nome}' não encontrada no catálogo.")
        elif isinstance(maquina_ou_nome, MaquinaInfo):
            info = maquina_ou_nome
        else:
            raise TypeError("Argumento deve ser o nome da máquina (str) ou uma instância de MaquinaInfo.")

        classe_driver = self.obter_classe_driver(info.rip_tipo)
        return classe_driver(info)

    def listar_maquinas(self, apenas_ativas: bool = False) -> List[MaquinaInfo]:
        """Lista todas as máquinas cadastradas no catálogo."""
        maqs = list(self._maquinas.values())
        if apenas_ativas:
            maqs = [m for m in maqs if m.ativo]
        return sorted(maqs, key=lambda m: m.nome.lower())

    def obter_maquina(self, nome: str) -> Optional[MaquinaInfo]:
        """Retorna as informações de uma máquina pelo nome exato ou sem case."""
        if nome in self._maquinas:
            return self._maquinas[nome]
        for k, v in self._maquinas.items():
            if k.lower() == nome.lower():
                return v
        return None

    def cadastrar_maquina(self, maquina: MaquinaInfo, persistir: bool = True) -> MaquinaInfo:
        """Cadastra uma nova máquina no catálogo."""
        nome = maquina.nome.strip()
        if not nome:
            raise ValueError("O nome da máquina não pode ser vazio.")

        self._maquinas[nome] = maquina
        if persistir:
            self.persistir()
        return maquina

    def atualizar_maquina(self, nome_antigo: str, maquina: MaquinaInfo, persistir: bool = True) -> MaquinaInfo:
        """Atualiza a configuração de uma máquina existente, permitindo renomeação."""
        nome_novo = maquina.nome.strip()
        if not nome_novo:
            raise ValueError("O nome da máquina não pode ser vazio.")

        # Se renomeou, remove a chave antiga
        if nome_antigo in self._maquinas and nome_antigo != nome_novo:
            del self._maquinas[nome_antigo]
        else:
            for k in list(self._maquinas.keys()):
                if k.lower() == nome_antigo.lower() and k != nome_novo:
                    del self._maquinas[k]
                    break

        self._maquinas[nome_novo] = maquina
        if persistir:
            self.persistir()
        return maquina

    def remover_maquina(self, nome: str, persistir: bool = True) -> bool:
        """Remove uma máquina do catálogo."""
        alvo = None
        if nome in self._maquinas:
            alvo = nome
        else:
            for k in self._maquinas.keys():
                if k.lower() == nome.lower():
                    alvo = k
                    break

        if alvo:
            del self._maquinas[alvo]
            if persistir:
                self.persistir(remover_do_banco=alvo)
            return True
        return False

    def restaurar_padroes(self, persistir: bool = True) -> Dict[str, MaquinaInfo]:
        """Restaura as configurações de fábrica padrão do sistema."""
        try:
            import rasterlink_hotfolder
            padroes = copy.deepcopy(rasterlink_hotfolder.MAQUINAS_PADRAO)
        except Exception:
            padroes = {
                "UJV 100 UNY CV": {
                    "hot_folder": r"C:\MijCtrl\Hot\UJV 100 UNY CV",
                    "largura_util_m": 1.27,
                    "largura_montagem_m": 1.52,
                    "margem_montagem_m": 0.0,
                    "montagem": True,
                    "posto": "rip",
                    "rip_tipo": "rasterlink",
                },
                "SWJ320A": {
                    "hot_folder": r"C:\MijCtrl\Hot\SWJ320A",
                    "largura_util_m": 3.24,
                    "largura_montagem_m": 3.20,
                    "margem_montagem_m": 0.0,
                    "montagem": True,
                    "posto": "rip",
                    "rip_tipo": "rasterlink",
                },
                "DOCAN R5200": {
                    "hot_folder": r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\Jobs\Docan\Docan",
                    "largura_util_m": 5.04,
                    "largura_montagem_m": 5.00,
                    "margem_montagem_m": 0.0,
                    "montagem": True,
                    "posto": "sai",
                    "setup_sai": "Docan",
                    "girar": False,
                    "entrega_byhx": True,
                    "rip_tipo": "sai",
                },
                "DOCAN H2525": {
                    "hot_folder": r"C:\Program Files\SAi\SAi Production Suite 22\Jobs and Settings\Jobs\Docan\Docan_1",
                    "mesa_util_m": [2.50, 2.50],
                    "margem_montagem_m": 0.02,
                    "posto": "sai",
                    "setup_sai": "Docan_H2525",
                    "girar": False,
                    "rip_tipo": "sai",
                },
            }

        self._maquinas.clear()
        for nome, cfg in padroes.items():
            self._maquinas[nome] = MaquinaInfo.from_dict(nome, cfg)

        if persistir:
            self.persistir()
        return dict(self._maquinas)

    def recarregar(self) -> None:
        """
        Carrega as máquinas a partir de config.json, banco relacional ou MAQUINAS_PADRAO.
        """
        dados_maquinas: Dict[str, Any] = {}

        # 1. Tenta carregar do config.json
        caminho_cfg = self._resolver_caminho_config()
        if caminho_cfg and caminho_cfg.is_file():
            try:
                with open(caminho_cfg, "r", encoding="utf-8") as f:
                    dados = json.load(f)
                if isinstance(dados, dict) and "maquinas" in dados and isinstance(dados["maquinas"], dict):
                    dados_maquinas = dados["maquinas"]
            except Exception:
                dados_maquinas = {}

        # 2. Se não achou no config, tenta módulo rasterlink_hotfolder
        if not dados_maquinas:
            try:
                import rasterlink_hotfolder
                dados_maquinas = rasterlink_hotfolder.carregar_maquinas_config()
            except Exception:
                pass

        # 3. Fallback para padrões se vazio
        if not dados_maquinas:
            self.restaurar_padroes(persistir=False)
            return

        self._maquinas.clear()
        for nome, cfg in dados_maquinas.items():
            self._maquinas[nome] = MaquinaInfo.from_dict(nome, cfg)

    def persistir(self, remover_do_banco: Optional[str] = None) -> None:
        """
        Salva as máquinas cadastradas no config.json, atualiza rasterlink_hotfolder.MAQUINAS
        e persiste no banco relacional SQLite se disponível.
        """
        dict_maquinas = {nome: m.to_dict() for nome, m in self._maquinas.items()}

        # 1. Salva no config.json com gravação atômica (.tmp -> replace)
        caminho_cfg = self._resolver_caminho_config()
        if caminho_cfg:
            dados_completos = {}
            if caminho_cfg.is_file():
                try:
                    with open(caminho_cfg, "r", encoding="utf-8") as f:
                        dados_completos = json.load(f)
                except Exception:
                    dados_completos = {}

            dados_completos["maquinas"] = dict_maquinas

            caminho_tmp = caminho_cfg.with_suffix(".tmp")
            try:
                with open(caminho_tmp, "w", encoding="utf-8") as f:
                    json.dump(dados_completos, f, ensure_ascii=False, indent=2)
                caminho_tmp.replace(caminho_cfg)
            except Exception:
                # Fallback direto
                try:
                    with open(caminho_cfg, "w", encoding="utf-8") as f:
                        json.dump(dados_completos, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        # 2. Atualiza memória global de rasterlink_hotfolder
        try:
            import rasterlink_hotfolder
            rasterlink_hotfolder.atualizar_maquinas_em_memoria(dict_maquinas)
        except Exception:
            pass

        # 3. Persiste no banco relacional se disponível
        try:
            import banco
            repo = banco.obter_repositorio_maquinas(self.caminho_banco)
            if remover_do_banco:
                repo.remover_maquina(remover_do_banco)
            repo.salvar_lote(dict_maquinas)
        except Exception:
            # Banco opcional, não interrompe operação gráfica
            pass

    def _resolver_caminho_config(self) -> pathlib.Path:
        if self.caminho_config:
            return self.caminho_config
        # Busca config.json na raiz do projeto
        raiz = pathlib.Path(__file__).resolve().parent.parent
        c = raiz / "config.json"
        return c

    # --- Operações de Alto Nível ---

    def entregar(
        self,
        nome_maquina: str,
        caminho_origem: Union[str, pathlib.Path],
        metadados: Optional[Dict[str, Any]] = None,
    ) -> EntregaResultado:
        """
        Atalho para obter o driver da máquina e entregar o arquivo atomicamente.
        """
        driver = self.obter_driver(nome_maquina)
        return driver.entregar_arquivo(caminho_origem, metadados=metadados)

    def validar_conexao(self, nome_maquina: str) -> bool:
        """Verifica a conectividade e integridade da hot folder da máquina."""
        driver = self.obter_driver(nome_maquina)
        return driver.validar_conexao()

    def obter_status_fila(self, nome_maquina: str) -> StatusFila:
        """Obtém status detalhado da fila da máquina."""
        driver = self.obter_driver(nome_maquina)
        return driver.obter_status()

    def obter_status_todas(self) -> Dict[str, StatusFila]:
        """Obtém status das filas de todas as máquinas cadastradas."""
        resultados = {}
        for nome in self._maquinas:
            try:
                driver = self.obter_driver(nome)
                resultados[nome] = driver.obter_status()
            except Exception as e:
                resultados[nome] = StatusFila(
                    online=False,
                    pasta_acessivel=False,
                    mensagem=f"Erro ao obter status: {e}",
                )
        return resultados


_gerenciador_global: Optional[GerenciadorHardware] = None


def obter_gerenciador_hardware(
    recarregar: bool = False,
    caminho_config: Optional[Union[str, pathlib.Path]] = None,
    caminho_banco: Optional[Union[str, pathlib.Path]] = None,
) -> GerenciadorHardware:
    """
    Retorna a instância singleton do GerenciadorHardware para o processo.
    """
    global _gerenciador_global
    if _gerenciador_global is None or recarregar:
        _gerenciador_global = GerenciadorHardware(
            caminho_config=caminho_config,
            caminho_banco=caminho_banco,
        )
    return _gerenciador_global
