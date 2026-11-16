# ISSUE-11: Gerenciador de Máquinas e Abstração de RIPs (`hardware.py`)

**Ordem de Execução:** 11º  
**Status:** Pronta para Início  
**Dependência:** ISSUE-10  
**Módulos a Criar:** `hardware/gerenciador.py`, `hardware/drivers/`.  
**Módulos a Refatorar:** `rasterlink_hotfolder.py`, `sai_setups.py`, `separar_ripados.py`.

---

## 1. Contexto

Atualmente, caminhos de pastas como `C:\RasterLink`, `D:\RIPADOS` e `C:\VigiaDocan` estão fortemente acoplados à infraestrutura interna da empresa.

Em um ambiente comercial:
- Uma gráfica pode possuir plotters Roland rodando **VersaWorks**, impressoras EFI rodando **Fiery XF**, máquinas UV chinesas rodando **Photoprint / SAi**, ou impressoras têxteis rodando **Caldera / Onyx**.
- O sistema deve permitir que o usuário cadastre suas máquinas livremente através de uma interface visual, sem editar código.

---

## 2. Requisitos Técnicos

### 2.1. Modelo de Driver de RIP Universal
Criar uma interface base abstrata `DriverRip`:
* `entregar_arquivo(caminho_pdf, metadados)`: Copia segura via arquivo temporário `~montando~` e renomeação atômica.
* `detectar_conclusao()`: Monitora a pasta de saída ou lê os logs do RIP para identificar quando a impressão foi concluída.
* `obter_status()`: Reporta se a fila está ativa, parada ou com erros.

### 2.2. Drivers Nativos Implementados
1. **Driver Hotfolder Genérico:** Compatível com qualquer RIP que suporte pastas vigiadas (Caldera, Onyx, VersaWorks, Wasatch).
2. **Driver Mimaki RasterLink:** Suporte às convenções de hot folder e rotação inteligente para economia de bobina.
3. **Driver SAi Production Manager:** Suporte a portas `FILE:`, separação automática de arquivos `.prt` por equipamento e cruzamento de dados com `RIPLOG.HTML`.

### 2.3. Painel de Cadastro de Máquinas
- Adicionar/Editar/Remover máquinas.
- Definir dimensões (Largura útil de rolo ou área de mesa plana).
- Definir margens de segurança e políticas de rotação permitidas.

---

## 3. Critérios de Aceite

1. Qualquer cliente deve conseguir configurar uma impressora em menos de 2 minutos apontando apenas a largura da mídia e a pasta de entrada do RIP.
2. O sistema deve operar corretamente em computadores que possuam apenas um único disco (`C:`).
