"""
Facade raiz para o subsistema de abstração de hardware gráfico e drivers de RIP.

Permite importação direta no nível do projeto:
    from hardware import obter_gerenciador_hardware, MaquinaInfo, DriverRip
"""
from hardware import (
    DriverByhx,
    DriverGenericoHotfolder,
    DriverRasterLink,
    DriverRip,
    DriverSaiProductionManager,
    EntregaResultado,
    GerenciadorHardware,
    MaquinaInfo,
    StatusFila,
    StatusTrabalho,
    obter_gerenciador_hardware,
)

__all__ = [
    "GerenciadorHardware",
    "DriverRip",
    "MaquinaInfo",
    "EntregaResultado",
    "StatusFila",
    "StatusTrabalho",
    "DriverGenericoHotfolder",
    "DriverRasterLink",
    "DriverSaiProductionManager",
    "DriverByhx",
    "obter_gerenciador_hardware",
]
